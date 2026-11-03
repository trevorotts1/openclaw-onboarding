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
           cap=None, test_only=False, record=None, env=None, now=None) -> dict

Returns a dict with ``ok: True`` only when kind, plan hash, client identity,
scope (and cap, when a spend is requested) match, the record is unexpired and
not revoked. Every failure RAISES (a caller that ignores the return value
cannot slip past):

    ApprovalRefused.code  APPROVAL-KIND | APPROVAL-HASH | APPROVAL-IDENTITY |
                          APPROVAL-EXPIRED | APPROVAL-REVOKED | APPROVAL-SCOPE |
                          APPROVAL-NOT-FROM-AUTHORITY
    ApprovalUnavailable   Command Center unconfigured or unreachable (fail closed;
                          never treated as "approved" and never as "not approved")

A spend cap that is too large, in another currency, or absent from the record
is an APPROVAL-SCOPE refusal (the cap is part of the approved scope).

Environment (same names cc_board.py uses): MISSION_CONTROL_URL (base URL),
MC_API_TOKEN (bearer), CC_BOARD_TIMEOUT (seconds, default 8). The expected
client identity defaults to COMPANY_SLUG, the tenant variable Command Center
already uses. Never prints a value.
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

KINDS = (
    "launch_plan_build", "paid_asset_budget", "test_location_use", "live_payment_test",
    "customer_send_activation", "page_publication", "batch_merge", "release_publication",
    "fleet_rollout",
)
# Keep in lockstep with approval-record.schema.json (a test enforces it).
REQUIRED = (
    "schema_version", "approval_id", "kind", "plan_hash", "client_identity",
    "source_message_ref", "scope", "expires_at", "revoked", "verification_class",
)

VERIFICATION_CLASSES = ("authenticated_platform_record",
                        "recorded_consent_not_cryptographically_sealed")
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_LOOPBACK = ("localhost", "127.0.0.1", "::1")


class ApprovalRefused(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__("%s: %s" % (code, message) if message else code)
        self.code = code


class ApprovalUnavailable(Exception):
    """Command Center unconfigured or unreachable; the approval could not be checked."""


def _refuse(code: str, message: str = ""):
    raise ApprovalRefused(code, message)


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


def _when(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _check(rec, approval_id, kind, plan_hash, scope, client_identity, cap, now):
    missing = [k for k in REQUIRED if not isinstance(rec, dict) or k not in rec]
    if missing or not isinstance(rec.get("scope"), list) or not isinstance(rec.get("revoked"), bool):
        _refuse("APPROVAL-NOT-FROM-AUTHORITY", "record is malformed (missing %s)" % ", ".join(missing or ["scope/revoked types"]))
    if rec["schema_version"] != "1.0":
        _refuse("APPROVAL-NOT-FROM-AUTHORITY", "record schema_version is not 1.0")
    if rec["verification_class"] not in VERIFICATION_CLASSES:
        _refuse("APPROVAL-NOT-FROM-AUTHORITY", "record verification_class is not recognized")
    if not isinstance(rec["source_message_ref"], str) or not rec["source_message_ref"].strip():
        _refuse("APPROVAL-NOT-FROM-AUTHORITY", "record carries no source_message_ref (the client's own reply)")
    if isinstance(approval_id, str) and rec["approval_id"] != approval_id:
        _refuse("APPROVAL-NOT-FROM-AUTHORITY", "record id does not match the requested approval_id")
    if kind not in KINDS or rec["kind"] != kind:
        _refuse("APPROVAL-KIND", "approved %r, asked for %r" % (rec["kind"], kind))
    if not plan_hash or not isinstance(rec["plan_hash"], str) or not hmac.compare_digest(rec["plan_hash"], str(plan_hash)):
        _refuse("APPROVAL-HASH", "the approval is bound to a different plan hash")
    if not client_identity or rec["client_identity"] != client_identity:
        _refuse("APPROVAL-IDENTITY", "the approval belongs to a different client")
    if rec["revoked"] is not False:
        _refuse("APPROVAL-REVOKED", "the approval was revoked")
    expires = _when(rec["expires_at"])
    if expires is None or expires <= now:
        _refuse("APPROVAL-EXPIRED", "the approval expired or has no valid expiry")
    wanted = [scope] if isinstance(scope, str) else list(scope or [])
    if not wanted or not set(wanted) <= set(rec["scope"]):
        _refuse("APPROVAL-SCOPE", "requested scope is not covered by the approval")
    if cap is not None:
        have = rec.get("cap")
        if not (isinstance(have, dict) and isinstance(have.get("cap_minor"), int)
                and have.get("currency") == cap.get("currency")
                and isinstance(cap.get("cap_minor"), int) and 0 <= cap["cap_minor"] <= have["cap_minor"]):
            _refuse("APPROVAL-SCOPE", "requested spend is over, or in another currency than, the approved cap")


def verify(approval_id, kind, plan_hash, scope, *, client_identity=None, cap=None,
           test_only=False, record=None, env=None, now=None) -> dict:
    if not isinstance(test_only, bool):  # None/0/""/[] must never flip a mode (ENF-05)
        _refuse("APPROVAL-NOT-FROM-AUTHORITY", "test_only must be exactly True or False")
    env = os.environ if env is None else env
    client_identity = client_identity or (env.get("COMPANY_SLUG") or "").strip()
    now = now or datetime.now(timezone.utc)
    if test_only:
        rec = _local_record(approval_id, record)
        authority = "local-test-record"
    else:
        if record is not None or not isinstance(approval_id, str) or not _ID_RE.match(approval_id):
            _refuse("APPROVAL-NOT-FROM-AUTHORITY",
                    "a file, dict or malformed id is not an approval; it must be minted in Command Center")
        rec = _fetch(approval_id, env)
        authority = "command-center"
    _check(rec, approval_id if (not test_only or record is not None) else None, kind, plan_hash, scope, client_identity, cap, now)
    return {"ok": True, "approval_id": rec["approval_id"], "kind": rec["kind"], "plan_hash": rec["plan_hash"],
            "client_identity": rec["client_identity"], "scope": list(rec["scope"]),
            "expires_at": rec["expires_at"], "authority": authority, "test_only": test_only}
