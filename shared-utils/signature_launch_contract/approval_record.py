#!/usr/bin/env python3
"""approval_record.py -- verify an owner approval against the Command Center (stdlib only).

WHY THIS EXISTS (ENF-01 / S06-06 / S44-16)
------------------------------------------
Every earlier "approval" was a JSON file the AI session itself wrote, so the
session could approve its own plan. This module is the ONE verifier: it trusts
only a record fetched live from the Command Center API (the approval is minted
there from the client's own reply carrying the plan-hash prefix; the AI session
cannot write that service). A file path or a dict handed in as "the approval"
is refused unless the caller says ``test_only=True``.

    verify(approval_id, kind, plan_hash, scope, *, client_identity=None,
           cap=None, test_only=False, record=None, env=None, now=None,
           identity_kind=None) -> dict

Returns a dict with ``ok: True`` only when kind, plan hash, identity, scope
(and cap, when a spend is requested) match, the record is unexpired and not
revoked. Every failure RAISES (a caller that ignores the return value cannot
slip past):

    ApprovalRefused.code  APPROVAL-KIND | APPROVAL-KIND-UNKNOWN | APPROVAL-HASH |
                          APPROVAL-IDENTITY | APPROVAL-IDENTITY-KIND |
                          APPROVAL-EXPIRED | APPROVAL-REVOKED | APPROVAL-SCOPE |
                          APPROVAL-NOT-FROM-AUTHORITY
    ApprovalUnavailable   Command Center unconfigured or unreachable (fail closed;
                          never treated as "approved" and never as "not approved")

A spend cap that is too large, in another currency, or absent from the record
is an APPROVAL-SCOPE refusal (the cap is part of the approved scope).

THE VERSIONED CONTRACT (F20 / S1 Pair C, W12)
---------------------------------------------
The Command Center mints ``launch_approvals`` rows in a shape this module did
not read: kinds ``plan_build``/``publish`` (not ``launch_plan_build``/
``page_publication``), ``scope`` as one string (not a list), ``cap_minor`` and
``currency`` flat (not nested under ``cap``), ``client_identity_ref`` (the
verified person) and ``tenant_id`` (the routing company), no
``schema_version`` and no ``verification_class``. A genuine owner approval was
therefore refused at the application boundary. This module now NORMALIZES that
wire shape through an explicit, enumerated mapping and refuses anything the
mapping does not name -- it does not guess, and it does not widen a meaning.

Contract versions accepted (``SCHEMA_VERSIONS``):
  * ``"2.0"``           -- this canonical shape (see approval-record.schema.json)
  * ``"1.0"``           -- the previous shared shape (``client_identity``,
                           list ``scope``, nested ``cap``)
  * ``"cc-unversioned"``-- a live Command Center row, which carries no version

IDENTITY IS TWO THINGS, NEVER ONE (F20 item 11)
-----------------------------------------------
``consenting_actor_ref`` is the authenticated PERSON who said approve
(Command Center stores it as ``client_identity_ref``). ``tenant_ref`` is the
COMPANY/tenant used for routing (Command Center stores it as ``tenant_id``).
They are not interchangeable and a field rename is not a mapping: a caller that
hands in a tenant slug where an actor is required is refused with
``APPROVAL-IDENTITY-KIND``, not quietly accepted. Pass ``identity_kind="tenant"``
to bind the routing identity on purpose, or ``identity_kind="actor"`` (the
default) to bind the person.

A legacy 1.0 record carries a single ``client_identity`` field that cannot say
which of the two it means. It is read as the actor and the result is marked
``identity_binding="legacy_unclassified"`` so no consumer can mistake the
marker for a verified distinction.

WHAT A STORED APPROVAL DOES NOT AUTHORIZE (F20 item 8; task item 3)
-------------------------------------------------------------------
No kind implies another. ``IMPLIED_KINDS`` is empty for every kind, as data,
so a later reader cannot "helpfully" widen it. In particular a stored
``publish``/``page_publication`` approval does NOT authorize
``customer_send_activation``, ``automation_write``, ``release_publication``,
``fleet_rollout`` or any other live effect -- see
``LEGACY_PUBLISH_DOES_NOT_AUTHORIZE`` and ``record_authorizes_effect``.

Environment (same names cc_board.py uses): MISSION_CONTROL_URL (base URL),
MC_API_TOKEN (bearer), CC_BOARD_TIMEOUT (seconds, default 8). When
``client_identity`` is omitted, COMPANY_SLUG is used as the TENANT identity
(``identity_kind="tenant"``), never silently as the consenting person. Never
prints a value.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# The Command Center read-only GET the approval endpoint (U-approval-01) serves.
APPROVAL_PATH = "/api/launch-approvals/{approval_id}"

#: The contract this module implements. Version 2 adds the Command Center wire
#: normalization and the actor/tenant split. A call that succeeds is a v2 call.
APPROVAL_CONTRACT_VERSION = "2.0"

#: Record versions this verifier will normalize. Anything else is refused: an
#: unknown version is an unknown meaning, not a newer one.
SCHEMA_VERSIONS = ("2.0", "1.0", "cc-unversioned")

#: The canonical kinds. These are the ONLY meanings the verifier acts on.
KINDS = (
    "launch_plan_build", "paid_asset_budget", "page_publication",
    "automation_write", "design_board", "pin_rotation",
    "test_location_use", "live_payment_test", "customer_send_activation",
    "batch_merge", "release_publication", "fleet_rollout",
)

#: The kinds Command Center's ``launch-approvals.ts`` mints today.
COMMAND_CENTER_KINDS = (
    "plan_build", "paid_asset_budget", "publish",
    "automation_write", "pin_rotation", "design_board",
)

#: Explicit Command Center -> canonical mapping. One entry per CC kind; a CC
#: kind absent from this table is an unknown meaning and is refused. No alias
#: maps several CC kinds onto one canonical kind, and no alias widens scope.
COMMAND_CENTER_KIND_ALIASES = {
    "plan_build": "launch_plan_build",
    "paid_asset_budget": "paid_asset_budget",
    "publish": "page_publication",
    "automation_write": "automation_write",
    "pin_rotation": "pin_rotation",
    "design_board": "design_board",
}

#: Every spelling the verifier accepts, canonical plus legacy aliases. A kind
#: not in this table is refused as APPROVAL-KIND-UNKNOWN.
LEGACY_KIND_ALIASES = {kind: kind for kind in KINDS}
LEGACY_KIND_ALIASES.update(COMMAND_CENTER_KIND_ALIASES)

#: Nothing is implied by anything. Kept as data so the emptiness is explicit.
IMPLIED_KINDS = {kind: frozenset() for kind in KINDS}

#: Effects that change the outside world. A stored approval never authorizes
#: all of them; it authorizes exactly its own kind.
LIVE_EFFECTS = (
    "page_publication", "customer_send_activation", "automation_write",
    "release_publication", "fleet_rollout", "live_payment_test",
    "test_location_use", "paid_asset_budget", "design_board", "pin_rotation",
)

#: What a stored legacy publish / page_publication approval must NOT authorize.
LEGACY_PUBLISH_DOES_NOT_AUTHORIZE = tuple(
    effect for effect in LIVE_EFFECTS if effect != "page_publication"
) + ("launch_plan_build", "batch_merge")

#: Canonical fields the verifier requires after normalization.
REQUIRED = (
    "schema_version", "record_version", "approval_id", "kind", "plan_hash",
    "consenting_actor_ref", "source_message_ref", "scope", "expires_at",
    "revoked", "verification_class", "authority",
)

#: ``local_test_record`` is assigned by THIS verifier to a test-only local
#: read; a record fetched live from Command Center is always
#: ``authenticated_platform_record``.
VERIFICATION_CLASSES = (
    "authenticated_platform_record",
    "recorded_consent_not_cryptographically_sealed",
    "local_test_record",
)

#: Which identity a caller is binding. ``None`` means "infer, refusing the
#: ambiguous case".
IDENTITY_BINDINGS = ("actor", "tenant")

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_LOOPBACK = ("localhost", "127.0.0.1", "::1")
_PLAN_HASH_RE = re.compile(r"^(?:sha256:)?([0-9a-fA-F]{64})$")


class ApprovalRefused(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__("%s: %s" % (code, message) if message else code)
        self.code = code


class ApprovalUnavailable(Exception):
    """Command Center unconfigured or unreachable; the approval could not be checked."""


def _refuse(code: str, message: str = ""):
    raise ApprovalRefused(code, message)


def _same(left: str, right: str) -> bool:
    """Constant-time comparison of two strings (encodes so unicode is safe)."""
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


def _clean_ref(value) -> "str | None":
    return value.strip().lower() if isinstance(value, str) and value.strip() else None


def canonical_kind(kind) -> "str | None":
    """The canonical kind for any accepted spelling, or None when unknown."""
    if not isinstance(kind, str):
        return None
    return LEGACY_KIND_ALIASES.get(kind.strip())


def canonical_plan_hash(value) -> "str | None":
    """Bare lowercase 64-hex digest from ``<hex>`` or ``sha256:<hex>``, else None."""
    if not isinstance(value, str):
        return None
    match = _PLAN_HASH_RE.match(value.strip())
    return match.group(1).lower() if match else None


def normalize_scope(value):
    """Scope as a list, from a v2 list or a Command Center single string.

    A Command Center scope is one free string (``"images, pages"``). It is split
    on commas; the whole original string is also kept as a member so an entry
    that legitimately contains a comma still matches. Returns None when the
    value is not a recognized representation.
    """
    entries = []
    if isinstance(value, str):
        entries.append(value)
    elif isinstance(value, (list, tuple)):
        if not value:
            return None
        for item in value:
            if not isinstance(item, str) or not item.strip():
                return None
            entries.append(item)
    else:
        return None
    normalized = []
    for entry in entries:
        normalized.append(entry.strip())
        normalized.extend(part.strip() for part in entry.split(",") if part.strip())
    ordered = list(dict.fromkeys(item for item in normalized if item))
    return ordered or None


def record_authorizes_effect(record, effect) -> bool:
    """True only when the record's own canonical kind IS the effect's kind.

    No kind implies another (``IMPLIED_KINDS`` is empty everywhere). A stored
    publish approval therefore does not authorize a customer send, an
    automation write, a release publication or a fleet rollout.
    """
    if not isinstance(record, dict):
        return False
    wanted = canonical_kind(effect)
    if wanted is None:
        return False
    have = canonical_kind(record.get("kind"))
    if have is None or have != wanted:
        return False
    return wanted not in IMPLIED_KINDS.get(have, frozenset())


def _fetch(approval_id: str, env) -> dict:
    base = (env.get("MISSION_CONTROL_URL") or "").strip().rstrip("/")
    token = (env.get("MC_API_TOKEN") or "").strip()
    if not base or not token:
        raise ApprovalUnavailable("MISSION_CONTROL_URL and MC_API_TOKEN must both be set")
    parts = urllib.parse.urlsplit(base)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ApprovalUnavailable("MISSION_CONTROL_URL is not an http(s) URL")
    if parts.scheme != "https" and parts.hostname not in _LOOPBACK:
        raise ApprovalUnavailable("refusing to send the bearer token over plain http to a non-loopback host")
    try:
        timeout = int(env.get("CC_BOARD_TIMEOUT") or 8)
    except (TypeError, ValueError):
        timeout = 8
    req = urllib.request.Request(
        base + APPROVAL_PATH.format(approval_id=urllib.parse.quote(approval_id, safe="")),
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            _refuse("APPROVAL-NOT-FROM-AUTHORITY", "Command Center has no such approval record")
        raise ApprovalUnavailable("Command Center answered HTTP %d" % exc.code)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise ApprovalUnavailable("Command Center unreachable (%s)" % type(exc).__name__)
    try:
        rec = json.loads(body)
    except ValueError:
        _refuse("APPROVAL-NOT-FROM-AUTHORITY", "Command Center reply is not JSON")
    return rec["approval"] if isinstance(rec, dict) and isinstance(rec.get("approval"), dict) else rec


def _local_record(approval_id, record):
    src = record if record is not None else approval_id
    if isinstance(src, dict):
        return src
    if isinstance(src, (str, Path)) and Path(src).is_file():
        try:
            return json.loads(Path(src).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    _refuse("APPROVAL-NOT-FROM-AUTHORITY", "test_only needs a local record (dict or JSON file)")


def _normalize_cap(rec: dict):
    """Nested ``cap`` or flat ``cap_minor``/``currency`` -> ``{cap_minor, currency}``.

    Returns ``None`` (no cap granted) or the string ``"conflict"`` when the two
    representations disagree or half a cap is supplied. A half cap is never a
    cap: it is refused rather than completed by guesswork.
    """
    nested = rec.get("cap")
    flat_minor = rec.get("cap_minor")
    flat_currency = rec.get("currency")
    if nested is not None:
        if not isinstance(nested, dict):
            return "conflict"
        if flat_minor is not None and flat_minor != nested.get("cap_minor"):
            return "conflict"
        if flat_currency is not None and flat_currency != nested.get("currency"):
            return "conflict"
        return dict(nested)
    if flat_minor is None and flat_currency is None:
        return None
    if flat_minor is None or flat_currency is None:
        return "conflict"
    return {"cap_minor": flat_minor, "currency": flat_currency}


def normalize_record(rec, *, authority: str) -> dict:
    """Return the canonical v2 record for a Command Center, v1 or legacy row.

    ``authority`` is the transport that produced ``rec``: ``"command-center"``
    for a live fetch, ``"local-test-record"`` for a test-only local read. It is
    DERIVED here, never read from the record: a local file cannot declare
    itself authenticated.
    """
    if not isinstance(rec, dict):
        _refuse("APPROVAL-NOT-FROM-AUTHORITY", "record is not an object")

    declared_version = rec.get("record_version", rec.get("schema_version"))
    if declared_version is None:
        declared_version = "cc-unversioned"
    if declared_version not in SCHEMA_VERSIONS:
        _refuse("APPROVAL-NOT-FROM-AUTHORITY",
                "record version %r is not one of %s" % (declared_version, ", ".join(SCHEMA_VERSIONS)))

    declared_kind = rec.get("kind")
    kind = canonical_kind(declared_kind)
    if kind is None:
        _refuse("APPROVAL-KIND-UNKNOWN",
                "%r is not a supported approval kind; supported spellings are %s"
                % (declared_kind, ", ".join(sorted(LEGACY_KIND_ALIASES))))

    wire_hash = rec.get("plan_hash")
    plan_hash = canonical_plan_hash(wire_hash) or (wire_hash.strip() if isinstance(wire_hash, str) else None)
    if not plan_hash:
        _refuse("APPROVAL-NOT-FROM-AUTHORITY", "record carries no plan hash")

    # The consenting PERSON and the routing COMPANY are separate fields.
    actor = _clean_ref(rec.get("consenting_actor_ref")) or _clean_ref(rec.get("client_identity_ref"))
    tenant = _clean_ref(rec.get("tenant_ref")) or _clean_ref(rec.get("tenant_id"))
    legacy_single = False
    if actor is None and tenant is None:
        actor = _clean_ref(rec.get("client_identity"))
        legacy_single = actor is not None
    if actor is None:
        _refuse("APPROVAL-NOT-FROM-AUTHORITY", "record names no consenting actor")

    cap = _normalize_cap(rec)
    if cap == "conflict":
        _refuse("APPROVAL-NOT-FROM-AUTHORITY",
                "record carries a conflicting or half spend cap (nested cap vs flat cap_minor/currency)")

    scope = normalize_scope(rec.get("scope"))
    if not scope:
        _refuse("APPROVAL-NOT-FROM-AUTHORITY", "record grants no scope")

    declared_class = rec.get("verification_class")
    if declared_class is not None and declared_class not in VERIFICATION_CLASSES:
        _refuse("APPROVAL-NOT-FROM-AUTHORITY", "record verification_class is not recognized")
    if authority == "command-center":
        if declared_class not in (None, "authenticated_platform_record"):
            _refuse("APPROVAL-NOT-FROM-AUTHORITY",
                    "a Command Center record cannot declare %r" % (declared_class,))
        verification_class = "authenticated_platform_record"
    else:
        verification_class = "local_test_record"

    return {
        "schema_version": APPROVAL_CONTRACT_VERSION,
        "record_version": declared_version,
        "approval_id": rec.get("approval_id"),
        "kind": kind,
        "kind_wire": declared_kind,
        "plan_hash": plan_hash,
        "plan_hash_wire": wire_hash,
        "tenant_ref": tenant,
        "consenting_actor_ref": actor,
        "source_message_ref": rec.get("source_message_ref"),
        "scope": scope,
        "cap": cap,
        "expires_at": rec.get("expires_at"),
        "revoked": rec.get("revoked"),
        "verification_class": verification_class,
        "authority": authority,
        "legacy_single_identity": legacy_single,
    }


def _when(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _bind_identity(rec: dict, value, identity_kind) -> str:
    """Bind the caller's identity to the record; return the binding that held."""
    if identity_kind not in (None,) + IDENTITY_BINDINGS:
        _refuse("APPROVAL-NOT-FROM-AUTHORITY",
                "identity_kind must be one of %s" % ", ".join(IDENTITY_BINDINGS))
    wanted = _clean_ref(value)
    if not wanted:
        _refuse("APPROVAL-IDENTITY", "no client identity was supplied for the check")
    actor = rec.get("consenting_actor_ref")
    tenant = rec.get("tenant_ref")

    if identity_kind == "tenant":
        if tenant and _same(tenant, wanted):
            return "tenant"
        # A 1.0 record carries one field that cannot say which it is. Binding it
        # as the tenant is allowed, but the result is marked unclassified so no
        # consumer can mistake the marker for a verified distinction.
        if rec.get("legacy_single_identity") and actor and _same(actor, wanted):
            return "legacy_unclassified"
        _refuse("APPROVAL-IDENTITY", "the approval belongs to a different client")

    if identity_kind == "actor":
        if actor and _same(actor, wanted):
            return "actor"
        _refuse("APPROVAL-IDENTITY", "the approval was given by a different person")

    # Undeclared: the person wins. Matching only the company is REFUSED, because
    # a tenant slug is not a consenting person and silently accepting it is the
    # wrong mapping this contract exists to stop.
    if actor and _same(actor, wanted):
        return "legacy_unclassified" if rec.get("legacy_single_identity") else "actor"
    if tenant and _same(tenant, wanted):
        _refuse("APPROVAL-IDENTITY-KIND",
                "that value is the record's tenant/company identity, not the consenting person; "
                "pass identity_kind='tenant' to bind the routing identity on purpose")
    _refuse("APPROVAL-IDENTITY", "the approval belongs to a different client")


def _check(rec: dict, approval_id, kind, plan_hash, scope, client_identity, cap, now,
           identity_kind):
    missing = [key for key in REQUIRED if key not in rec]
    if missing or not isinstance(rec.get("scope"), list) or not isinstance(rec.get("revoked"), bool):
        _refuse("APPROVAL-NOT-FROM-AUTHORITY",
                "record is malformed (missing %s)" % ", ".join(missing or ["scope/revoked types"]))
    if rec["schema_version"] != APPROVAL_CONTRACT_VERSION:
        _refuse("APPROVAL-NOT-FROM-AUTHORITY", "normalized record is not contract %s" % APPROVAL_CONTRACT_VERSION)
    if rec["record_version"] not in SCHEMA_VERSIONS:
        _refuse("APPROVAL-NOT-FROM-AUTHORITY", "record version is not recognized")
    if rec["verification_class"] not in VERIFICATION_CLASSES:
        _refuse("APPROVAL-NOT-FROM-AUTHORITY", "record verification_class is not recognized")
    if not isinstance(rec["source_message_ref"], str) or not rec["source_message_ref"].strip():
        _refuse("APPROVAL-NOT-FROM-AUTHORITY", "record carries no source_message_ref (the client's own reply)")
    if isinstance(approval_id, str) and rec["approval_id"] != approval_id:
        _refuse("APPROVAL-NOT-FROM-AUTHORITY", "record id does not match the requested approval_id")

    wanted_kind = canonical_kind(kind)
    if wanted_kind is None:
        _refuse("APPROVAL-KIND-UNKNOWN", "%r is not a supported approval kind" % (kind,))
    if rec["kind"] != wanted_kind:
        _refuse("APPROVAL-KIND", "approved %r, asked for %r" % (rec["kind"], wanted_kind))

    have_hash = rec["plan_hash"]
    want_hash = canonical_plan_hash(plan_hash)
    if want_hash and canonical_plan_hash(have_hash):
        same_hash = _same(canonical_plan_hash(have_hash), want_hash)
    else:
        same_hash = bool(plan_hash) and isinstance(have_hash, str) and _same(
            str(have_hash).strip(), str(plan_hash).strip())
    if not same_hash:
        _refuse("APPROVAL-HASH", "the approval is bound to a different plan hash")

    binding = _bind_identity(rec, client_identity, identity_kind)

    if rec["revoked"] is not False:
        _refuse("APPROVAL-REVOKED", "the approval was revoked")
    expires = _when(rec["expires_at"])
    if expires is None or expires <= now:
        _refuse("APPROVAL-EXPIRED", "the approval expired or has no valid expiry")

    wanted = normalize_scope(scope)
    if not wanted or not set(wanted) <= set(rec["scope"]):
        _refuse("APPROVAL-SCOPE", "requested scope is not covered by the approval")

    if cap is not None:
        have_cap = rec.get("cap")
        if not (isinstance(have_cap, dict) and isinstance(have_cap.get("cap_minor"), int)
                and not isinstance(have_cap.get("cap_minor"), bool)
                and have_cap.get("currency") == cap.get("currency")
                and isinstance(cap.get("cap_minor"), int)
                and not isinstance(cap.get("cap_minor"), bool)
                and 0 <= cap["cap_minor"] <= have_cap["cap_minor"]):
            _refuse("APPROVAL-SCOPE",
                    "requested spend is over, or in another currency than, the approved cap")
    return binding


def verify(approval_id, kind, plan_hash, scope, *, client_identity=None, cap=None,
           test_only=False, record=None, env=None, now=None, identity_kind=None) -> dict:
    if not isinstance(test_only, bool):  # None/0/""/[] must never flip a mode (ENF-05)
        _refuse("APPROVAL-NOT-FROM-AUTHORITY", "test_only must be exactly True or False")
    env = os.environ if env is None else env
    if not client_identity:
        client_identity = (env.get("COMPANY_SLUG") or "").strip()
        # COMPANY_SLUG is the routing tenant, never the consenting person.
        if client_identity and identity_kind is None:
            identity_kind = "tenant"
    now = now or datetime.now(timezone.utc)
    if test_only:
        rec = normalize_record(_local_record(approval_id, record), authority="local-test-record")
        authority = "local-test-record"
    else:
        if record is not None or not isinstance(approval_id, str) or not _ID_RE.match(approval_id):
            _refuse("APPROVAL-NOT-FROM-AUTHORITY",
                    "a file, dict or malformed id is not an approval; it must be minted in Command Center")
        rec = normalize_record(_fetch(approval_id, env), authority="command-center")
        authority = "command-center"
    binding = _check(rec, approval_id if (not test_only or record is not None) else None,
                     kind, plan_hash, scope, client_identity, cap, now, identity_kind)
    return {
        "ok": True,
        "contract_version": APPROVAL_CONTRACT_VERSION,
        "record_version": rec["record_version"],
        "approval_id": rec["approval_id"],
        "kind": rec["kind"],
        "kind_wire": rec["kind_wire"],
        "plan_hash": rec["plan_hash"],
        "plan_hash_wire": rec["plan_hash_wire"],
        "client_identity": rec["consenting_actor_ref"],
        "consenting_actor_ref": rec["consenting_actor_ref"],
        "tenant_ref": rec["tenant_ref"],
        "identity_binding": binding,
        "scope": list(rec["scope"]),
        "cap": rec["cap"],
        "expires_at": rec["expires_at"],
        "verification_class": rec["verification_class"],
        "authority": authority,
        "test_only": test_only,
    }
