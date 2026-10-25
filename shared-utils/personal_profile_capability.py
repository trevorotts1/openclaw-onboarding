#!/usr/bin/env python3
"""personal_profile_capability.py — T-22 honest personal-profile capability
and assisted contract.

ONE source of truth: 35-social-media-planner/config/profile-capabilities.json.
This module is the consumer used by the assisted workflow, the status surface,
the refusal path and the truth guard. Nothing here guesses: a channel/account
type is unattended only when the declaration says so, and a personal profile is
always assisted (or unavailable), never automated.

Provenance, not shape (B-27). A capability, a status claim or an operator
receipt binds only when it carries the marker minted here: an HMAC over the
record's own claim fields, produced by prepare_assisted_placement() and renewed
by record_operator_confirmation(). A hand-built dict, a hand-edited JSON file, or
a dict whose keys/types the sanctioned constructor never produced cannot mint
one: _require_sanctioned() refuses a confirmation that lacks it, _truth_of()
refuses an unsealed operator-confirmed record instead of labelling it verified,
and every record is resolved against the declaration, so an undeclared channel,
account type or action cannot be rendered at all.

Coverage honesty (B-04). The only test behind this contract is NARROW: it reads
the declaration and exercises the assisted prepare/confirm/status/guard paths
in-process and through the CLI. No public monitoring of any channel or account is
run, observed or claimed here, so unattended coverage is UNPROVED and
_truth_of() refuses every unattended publication claim rather than asserting one.
The proof that would be required, and the owner who must decide to fund it, are
declared in policy.unattended_coverage and reported by unattended_coverage().

Assisted contract:
  1. request_placement(unattended=True) on a personal profile is REFUSED with a
     plain limitation and an explicit assisted offer. No silent downgrade and no
     fake success.
  2. prepare_assisted_placement() builds the exact placement (text, asset,
     keyword, CTA, timing) and a one-step operator instruction. Status is
     "awaiting-operator"; there is no receipt.
  3. record_operator_confirmation() turns it into "operator-confirmed" ONLY when
     the operator explicitly confirms. The receipt is the only proof, and it is
     proof only for a placement whose id recomputes from that placement's own
     (channel, account_type, action, placement) — a carried placement_id is never
     trusted on its own.
  4. status_surface() reports awaiting-operator / operator-confirmed and never
     published-by-system for an assisted placement.
  5. assert_truthful_publication() raises UntruthfulPublication when a record
     claims a system publication without an operator receipt.

4 and 5 are ONE code path: both delegate to _truth_of(), so the read path and
the guard cannot disagree about any record. The personal-profile/ unattended
rule is likewise written once (_reject_personal_on_unattended) and called by
both.

STDLIB ONLY. No network.
"""

from __future__ import annotations

import copy
import datetime as _dt
import hashlib
import hmac
import json
import os
from typing import Any, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
CAPABILITIES_PATH = os.path.join(
    _HERE, "..", "35-social-media-planner", "config", "profile-capabilities.json"
)

_MODES = ("unattended", "assisted", "unavailable")
_ASSISTED_STATUSES = ("awaiting-operator", "operator-confirmed")
_REQUIRED_PLACEMENT_FIELDS = ("text", "asset", "keyword", "cta", "timing")

_CACHE: dict = {}
_CACHE_PATH: Optional[str] = None


class CapabilityError(ValueError):
    """A capability request the declaration does not support."""


class UntruthfulPublication(CapabilityError):
    """A record claims a publication that never had an operator receipt."""


def _cap_path(path: Optional[str] = None) -> str:
    return os.path.abspath(path or CAPABILITIES_PATH)


# --- provenance marker (B-27) ------------------------------------------------
#
# The marker is an HMAC over a record's own claim fields, keyed from the
# declaration the record is checked against. It is minted ONLY by
# prepare_assisted_placement() and record_operator_confirmation(), and it travels
# with the record (so a prepared package read back from disk still verifies),
# while a caller cannot produce one from a hand-built dict: the key never appears
# in the record, and the MAC covers route/channel/account/action/placement/
# status/receipt, so a copied marker does not fit an edited record.
#
# ponytail: the key is derived from source-visible material, so code that imports
# this module and calls the private sealer can still mint. The ceiling is an
# unprivileged caller handing in dicts; the upgrade is an operator-held signing
# key when unattended coverage is proved (see policy.unattended_coverage).

_SEAL_DOMAIN = b"personal-profile-capability/seal-v1"
_SEAL_ALGORITHM = "hmac-sha256"
_SEAL_VERSION = 1
_SEAL_RECEIPT_FIELDS = ("placement_id", "operator", "confirmed_at", "method", "evidence")
_SEAL_KEYS: dict = {}


def _seal_key(path: Optional[str] = None) -> bytes:
    resolved = _cap_path(path)
    cached = _SEAL_KEYS.get(resolved)
    if cached:
        return cached
    try:
        with open(resolved, "rb") as handle:
            declaration = handle.read()
    except OSError as exc:
        raise CapabilityError(f"cannot read capability declaration: {exc}") from exc
    key = hashlib.sha256(_SEAL_DOMAIN + b"\x00" + declaration).digest()
    _SEAL_KEYS[resolved] = key
    return key


def _seal_payload(record: dict) -> bytes:
    receipt = record.get("receipt") if isinstance(record.get("receipt"), dict) else None
    core = (
        {field: receipt.get(field) for field in _SEAL_RECEIPT_FIELDS}
        if receipt is not None
        else None
    )
    return json.dumps(
        {
            "route": record.get("route"),
            "channel": record.get("channel"),
            "account_type": record.get("account_type"),
            "action": record.get("action"),
            "placement": record.get("placement"),
            "status": record.get("status"),
            "receipt": core,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")


def _seal(record: dict, path: Optional[str] = None) -> dict:
    """Stamp a record with the provenance marker (constructor-side only)."""
    mac = hmac.new(_seal_key(path), _seal_payload(record), hashlib.sha256).hexdigest()
    record["provenance"] = {
        "algorithm": _SEAL_ALGORITHM,
        "version": _SEAL_VERSION,
        "mac": mac,
    }
    return record


def _is_sanctioned(record: Any, path: Optional[str] = None) -> bool:
    """True only when the record carries a marker that fits its own fields."""
    if not isinstance(record, dict):
        return False
    provenance = record.get("provenance")
    if not isinstance(provenance, dict):
        return False
    if provenance.get("algorithm") != _SEAL_ALGORITHM:
        return False
    if provenance.get("version") != _SEAL_VERSION:
        return False
    mac = provenance.get("mac")
    if not isinstance(mac, str) or len(mac) != 64:
        return False
    expected = hmac.new(_seal_key(path), _seal_payload(record), hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, expected)


def _require_sanctioned(record: Any, path: Optional[str] = None, what: str = "this package") -> None:
    if not _is_sanctioned(record, path):
        raise CapabilityError(
            f"{what} carries no sanctioned provenance marker, so it cannot mint "
            "authority. A placement id is minted only by "
            "prepare_assisted_placement(), and an operator receipt only by "
            "record_operator_confirmation(); a hand-built dict, a hand-edited file "
            "or a dict whose keys/types the constructor did not produce is refused."
        )


def _resolve_declared(caps: dict, channel: Any, account_type: Any) -> dict:
    """Resolve a record's channel + account type against the declaration."""
    channel_id = channel.strip().lower() if isinstance(channel, str) else ""
    account_id = account_type.strip().lower() if isinstance(account_type, str) else ""
    channel_block = (caps.get("channels") or {}).get(channel_id)
    if channel_block is None:
        raise CapabilityError(
            f"record names no declared channel '{channel}' (declared: "
            f"{sorted(caps.get('channels') or {})}); an undeclared channel cannot "
            "carry a capability or a status claim"
        )
    account = (channel_block.get("account_types") or {}).get(account_id)
    if account is None:
        raise CapabilityError(
            f"record names no declared account type '{account_type}' for channel "
            f"'{channel_id}' (declared: {sorted(channel_block['account_types'])}); "
            "an undeclared account type cannot carry a capability or a status claim"
        )
    return account


def load_capabilities(path: Optional[str] = None) -> dict:
    """Load and validate the capability declaration (cached per path)."""
    global _CACHE, _CACHE_PATH
    resolved = _cap_path(path)
    if _CACHE_PATH == resolved and _CACHE:
        return _CACHE
    try:
        with open(resolved, encoding="utf-8") as handle:
            caps = json.load(handle)
    except (OSError, ValueError) as exc:
        raise CapabilityError(f"cannot read capability declaration {resolved}: {exc}") from exc
    _validate_capabilities(caps)
    _CACHE = caps
    _CACHE_PATH = resolved
    return caps


def _validate_capabilities(caps: dict) -> None:
    policy = caps.get("policy")
    if not isinstance(policy, dict):
        raise CapabilityError("capability declaration missing policy block")
    if not str(policy.get("version") or "").strip():
        raise CapabilityError("capability declaration missing policy.version")
    assisted = policy.get("assisted_statuses") or {}
    if sorted(assisted) != sorted(_ASSISTED_STATUSES):
        raise CapabilityError(
            "policy.assisted_statuses must declare exactly "
            f"{list(_ASSISTED_STATUSES)}, got {sorted(assisted)}"
        )
    forbidden = policy.get("assisted_forbidden_statuses") or {}
    for status in ("published-by-system", "published"):
        if status not in forbidden:
            raise CapabilityError(
                f"policy.assisted_forbidden_statuses must forbid '{status}'"
            )
    if not policy.get("no_system_publication_without_receipt"):
        raise CapabilityError("policy.no_system_publication_without_receipt must be true")
    if not policy.get("refusal_language") or not policy.get("assisted_offer_language"):
        raise CapabilityError("policy refusal/offer language must be present")

    coverage = policy.get("unattended_coverage")
    if not isinstance(coverage, dict):
        raise CapabilityError(
            "policy.unattended_coverage must be declared: what is NOT proved about "
            "unattended publication, the proof required, and the owner who decides it"
        )
    if not str(coverage.get("status") or "").strip():
        raise CapabilityError("policy.unattended_coverage.status must be declared")
    proof = coverage.get("required_proof")
    if not isinstance(proof, list) or not proof or not all(
        isinstance(item, str) and item.strip() for item in proof
    ):
        raise CapabilityError(
            "policy.unattended_coverage.required_proof must list the proof required "
            "before an unattended publication could be claimed"
        )
    decision = coverage.get("owner_decision")
    if not isinstance(decision, dict):
        raise CapabilityError("policy.unattended_coverage.owner_decision must be declared")
    for field in ("owner", "decision", "status"):
        if not str(decision.get(field) or "").strip():
            raise CapabilityError(
                f"policy.unattended_coverage.owner_decision.{field} must be declared"
            )

    channels = caps.get("channels")
    if not isinstance(channels, dict) or not channels:
        raise CapabilityError("capability declaration has no channels")
    for channel_id, channel in channels.items():
        if not isinstance(channel, dict) or not channel.get("account_types"):
            raise CapabilityError(f"channel '{channel_id}' has no account_types")
        if not channel.get("checked_at"):
            raise CapabilityError(f"channel '{channel_id}' missing checked_at")
        for account_id, account in channel["account_types"].items():
            where = f"{channel_id}.{account_id}"
            mode = account.get("mode")
            if mode not in _MODES:
                raise CapabilityError(f"{where} has invalid mode '{mode}'")
            for bucket in ("unattended", "operator_action", "unavailable"):
                if not isinstance(account.get(bucket), list):
                    raise CapabilityError(f"{where} missing list '{bucket}'")
            overlap = set(account["unattended"]) & set(account["operator_action"])
            if overlap:
                raise CapabilityError(
                    f"{where} lists actions in both unattended and operator_action: "
                    f"{sorted(overlap)}"
                )
            personal = bool(account.get("personal_profile"))
            if personal:
                if account["unattended"]:
                    raise CapabilityError(
                        f"{where} is a personal profile and MUST NOT declare "
                        f"unattended actions: {account['unattended']}"
                    )
                if mode == "unattended":
                    raise CapabilityError(
                        f"{where} is a personal profile and MUST NOT be mode "
                        "'unattended'"
                    )
            if mode == "unattended" and not account["unattended"]:
                raise CapabilityError(f"{where} mode unattended has no unattended actions")
            if mode == "assisted" and not account["operator_action"]:
                raise CapabilityError(f"{where} mode assisted has no operator_action")
            if mode == "unavailable" and (account["unattended"] or account["operator_action"]):
                raise CapabilityError(
                    f"{where} mode unavailable must not offer unattended or assisted actions"
                )


def get_capability(
    channel: str,
    account_type: str,
    path: Optional[str] = None,
) -> dict:
    """Return the declared capability for one channel + account type."""
    caps = load_capabilities(path)
    channel_id = (channel or "").strip().lower()
    account_id = (account_type or "").strip().lower()
    channel_block = (caps.get("channels") or {}).get(channel_id)
    if channel_block is None:
        raise CapabilityError(
            f"no capability declaration for channel '{channel}' "
            f"(known: {sorted(caps.get('channels') or {})})"
        )
    account = (channel_block.get("account_types") or {}).get(account_id)
    if account is None:
        raise CapabilityError(
            f"no capability declaration for {channel_id} account type "
            f"'{account_type}' (known: {sorted(channel_block['account_types'])})"
        )
    return {
        "channel": channel_id,
        "channel_label": channel_block.get("channel_label"),
        "account_type": account_id,
        "label": account.get("label"),
        "mode": account.get("mode"),
        "personal_profile": bool(account.get("personal_profile")),
        "path": account.get("path"),
        "platform_api": account.get("platform_api"),
        "unattended": list(account.get("unattended") or []),
        "operator_action": list(account.get("operator_action") or []),
        "unavailable": list(account.get("unavailable") or []),
        "operator_instruction": account.get("operator_instruction") or "",
        "notes": account.get("notes") or "",
        "checked_at": channel_block.get("checked_at"),
        "source_urls": list(channel_block.get("source_urls") or []),
    }


def _refusal(
    caps: dict,
    channel: str,
    account_type: str,
    action: str,
    reason_code: str,
    reason: str,
    offer_assisted: bool,
    path: Optional[str] = None,
) -> dict:
    """Build a refusal. The capability block is resolved HERE, from the declaration.

    It is never accepted as a caller argument: a refusal that echoed a caller's own
    capability dict would mint an authority the declaration never granted.
    """
    capability = get_capability(channel, account_type, path)
    offer = None
    if offer_assisted:
        offer = {
            "route": "assisted",
            "message": caps["policy"]["assisted_offer_language"],
            "next": "prepare_assisted_placement",
        }
    return {
        "ok": False,
        "refused": True,
        "route": "refused",
        "reason_code": reason_code,
        "reason": reason,
        "channel": channel,
        "account_type": account_type,
        "action": action,
        "capability": capability,
        "offer": offer,
        "no_silent_downgrade": True,
    }


def request_placement(
    channel: str,
    account_type: str,
    action: str = "post",
    placement: Optional[dict] = None,
    unattended: bool = False,
    path: Optional[str] = None,
) -> dict:
    """Request a placement and resolve the honest route.

    - unattended=True on anything not declared unattended is REFUSED, never
      quietly rerouted.
    - an assisted route returns a prepared placement with status
      awaiting-operator and no receipt.
    """
    caps = load_capabilities(path)
    capability = get_capability(channel, account_type, path)
    action_id = (action or "post").strip().lower()
    known_actions = set(capability["unattended"]) | set(capability["operator_action"]) | set(
        capability["unavailable"]
    )
    if action_id not in known_actions:
        return _refusal(
            caps,
            capability["channel"],
            capability["account_type"],
            action_id,
            "action_not_declared",
            (
                f"Action '{action_id}' is not declared for {capability['channel_label']} "
                f"{capability['label']}. The declaration covers: {sorted(known_actions)}."
            ),
            offer_assisted=bool(capability["operator_action"]),
            path=path,
        )

    if action_id in capability["unavailable"] or capability["mode"] == "unavailable":
        return _refusal(
            caps,
            capability["channel"],
            capability["account_type"],
            action_id,
            "capability_unavailable",
            (
                f"{capability['label']} cannot perform '{action_id}' in this system. "
                f"{capability['notes']}"
            ).strip(),
            offer_assisted=False,
            path=path,
        )

    if unattended:
        if capability["mode"] == "unattended" and action_id in capability["unattended"]:
            return {
                "ok": True,
                "route": "unattended",
                "channel": capability["channel"],
                "account_type": capability["account_type"],
                "action": action_id,
                "capability": capability,
            }
        return _refusal(
            caps,
            capability["channel"],
            capability["account_type"],
            action_id,
            "unattended_not_supported",
            caps["policy"]["refusal_language"],
            offer_assisted=action_id in capability["operator_action"],
            path=path,
        )

    if action_id in capability["operator_action"] or capability["mode"] == "assisted":
        if placement is None:
            raise CapabilityError(
                f"assisted placement for {capability['channel']}/{capability['account_type']} "
                "requires placement (text, asset, keyword, cta, timing)"
            )
        package = prepare_assisted_placement(
            capability["channel"],
            capability["account_type"],
            placement,
            action=action_id,
            path=path,
        )
        return {"ok": True, "route": "assisted", "package": package}

    # action is unattended but the caller did not demand unattended; the
    # declaration still wins: it is a system action, not an operator action.
    return {
        "ok": True,
        "route": "unattended",
        "channel": capability["channel"],
        "account_type": capability["account_type"],
        "action": action_id,
        "capability": capability,
    }


def _placement_id(channel: str, account_type: str, action: str, placement: dict) -> str:
    payload = json.dumps(
        {
            "channel": channel,
            "account_type": account_type,
            "action": action,
            "placement": placement,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return "plc_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _placement_provenance(package: Any) -> str:
    """Recompute the placement digest — the ONE source of truth for a placement_id.

    prepare_assisted_placement() mints its id through here and
    record_operator_confirmation() re-derives it through here, so the two cannot
    drift. Nothing is ever accepted on a carried placement_id alone: the caller
    must supply what the digest is computed from (channel, account_type, action,
    placement) and the id must be the digest of exactly that.
    """
    if not isinstance(package, dict):
        raise CapabilityError("placement package must be an object")
    for field in ("channel", "account_type", "action"):
        value = package.get(field)
        if not isinstance(value, str) or not value.strip():
            raise CapabilityError(
                f"placement package carries no '{field}'; without the digest "
                "inputs there is no placement_id this receipt could prove"
            )
    if "placement" not in package:
        raise CapabilityError(
            "placement package carries no 'placement'; without the digest "
            "inputs there is no placement_id this receipt could prove"
        )
    clean = _validate_placement(package["placement"])
    return _placement_id(
        package["channel"].strip(),
        package["account_type"].strip(),
        package["action"].strip().lower(),
        clean,
    )


def _validate_placement(placement: dict) -> dict:
    if not isinstance(placement, dict):
        raise CapabilityError("placement must be an object")
    for field in _REQUIRED_PLACEMENT_FIELDS:
        if field not in placement:
            raise CapabilityError(f"placement missing required field '{field}'")
        value = placement[field]
        if not isinstance(value, (str, dict, list)):
            raise CapabilityError(
                f"placement field '{field}' must be a string, object or list, "
                f"not {type(value).__name__}"
            )
        empty = (isinstance(value, str) and not value.strip()) or (
            isinstance(value, (list, dict)) and not value
        )
        if empty:
            raise CapabilityError(f"placement field '{field}' must not be empty")
    # ponytail: shape is checked shallowly (top-level type per field); deepen to
    # per-field schemas if a placement ever carries nested operator input.
    return copy.deepcopy(placement)


def prepare_assisted_placement(
    channel: str,
    account_type: str,
    placement: dict,
    action: str = "post",
    path: Optional[str] = None,
) -> dict:
    """Prepare the exact placement and the one-step operator handoff."""
    capability = get_capability(channel, account_type, path)
    action_id = (action or "post").strip().lower()
    if capability["mode"] != "assisted":
        raise CapabilityError(
            f"{capability['channel']}/{capability['account_type']} is "
            f"'{capability['mode']}' and has no assisted placement route"
        )
    if action_id not in capability["operator_action"]:
        if action_id in capability["unattended"]:
            raise CapabilityError(
                f"'{action_id}' is declared unattended for "
                f"{capability['channel']}/{capability['account_type']}; do not route "
                "an unattended action through the assisted workflow"
            )
        raise CapabilityError(
            f"'{action_id}' is not an operator action for "
            f"{capability['channel']}/{capability['account_type']}"
        )
    clean = _validate_placement(placement)
    package = {
        "channel": capability["channel"],
        "channel_label": capability["channel_label"],
        "account_type": capability["account_type"],
        "account_label": capability["label"],
        "action": action_id,
        "placement": clean,
    }
    placement_id = _placement_provenance(package)
    result = {
        "placement_id": placement_id,
        "channel": package["channel"],
        "channel_label": package["channel_label"],
        "account_type": package["account_type"],
        "account_label": package["account_label"],
        "action": package["action"],
        "route": "assisted",
        "status": "awaiting-operator",
        "placement": package["placement"],
        "operator_action": {
            "step": "one-step-manual-action",
            "instruction": capability["operator_instruction"],
            "expected_action": action_id,
        },
        "receipt": None,
        "published_by_system": False,
        "capability_ref": {
            "checked_at": capability["checked_at"],
            "source_urls": capability["source_urls"],
        },
    }
    # The only place an awaiting-operator package becomes authoritative.
    return _seal(result, path)


def _now_utc() -> str:
    return (
        _dt.datetime.now(_dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _valid_receipt(receipt: Any, record: Any, path: Optional[str] = None) -> bool:
    """A receipt is proof only when it binds to a placement that is REAL.

    Real means provenance, not self-consistency: the record's placement_id must
    be the digest recomputed from the record's own (channel, account_type,
    action, placement), and the receipt must name exactly that id. A receipt
    that merely agrees with the record's own field proves nothing and is
    refused, as does a receipt naming no placement or offered for a record that
    names none. The binding is NOT optional.
    """
    if not isinstance(receipt, dict) or not isinstance(record, dict):
        return False
    caps = load_capabilities(path)
    for field in caps["policy"]["receipt_required_fields"]:
        value = receipt.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            return False
    bound = record.get("placement_id")
    if not isinstance(bound, str) or not bound.strip():
        return False
    try:
        provenance = _placement_provenance(record)
    except CapabilityError:
        return False
    if provenance != bound:
        return False
    return receipt.get("placement_id") == bound


def _parse_timestamp(value: Any):
    """Return the parsed ISO-8601 instant, or None when it is not one."""
    try:
        return _dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def record_operator_confirmation(
    package: dict,
    operator: str,
    confirmed_at: Optional[str] = None,
    evidence: Optional[Any] = None,
) -> dict:
    """Record an explicit operator confirmation as the receipt.

    Refuses without a named operator. Never produces 'published-by-system', and
    never launders a publication claim into a receipt: a package that already
    claims publication is refused, not relabelled. The result is checked against
    _truth_of() before it is returned, so a confirmation can never mint a record
    that the status surface or the guard would refuse.
    """
    if not isinstance(package, dict) or package.get("route") != "assisted":
        raise CapabilityError("only an assisted placement can receive an operator confirmation")
    if package.get("status") != "awaiting-operator":
        raise CapabilityError(
            f"placement {package.get('placement_id')} is '{package.get('status')}', "
            "not awaiting-operator"
        )
    _require_sanctioned(package)
    name = (operator or "").strip()
    if not name:
        raise CapabilityError(
            "operator confirmation requires a named operator; the system cannot "
            "confirm on the operator's behalf"
        )
    placement_id = package.get("placement_id")
    if not isinstance(placement_id, str) or not placement_id.strip():
        raise CapabilityError(
            "an operator confirmation must bind to a placement_id; there is no "
            "placement for this receipt to be proof of"
        )
    if package.get("published_by_system") is True or package.get("published") is True:
        raise CapabilityError(
            f"placement {placement_id} claims a publication; a claim cannot be "
            "turned into an operator receipt"
        )
    provenance_id = _placement_provenance(package)
    if provenance_id != placement_id:
        raise CapabilityError(
            f"placement_id '{placement_id}' is not the digest of this placement "
            f"(it recomputes to '{provenance_id}'); an operator confirmation "
            "binds only to a placement the id can be recomputed from"
        )
    stamp = confirmed_at or _now_utc()
    if _parse_timestamp(stamp) is None:
        raise CapabilityError(f"confirmed_at '{stamp}' is not an ISO-8601 timestamp")
    confirmed = copy.deepcopy(package)
    receipt = {
        "placement_id": placement_id,
        "operator": name,
        "confirmed_at": stamp,
        "method": "operator-asserted",
        "evidence": evidence,
    }
    confirmed["receipt"] = receipt
    confirmed["status"] = "operator-confirmed"
    confirmed["published_by_system"] = False
    # The only place an operator receipt becomes authoritative.
    _seal(confirmed)
    _truth_of(confirmed)
    return confirmed


def _reject_personal_on_unattended(record: dict, personal: Optional[bool] = None) -> None:
    """The ONE honesty rule the read path and the guard must both enforce.

    PROFILE-CAPABILITIES.md lists "a personal profile record uses the unattended
    route at all" as fail closed. This is its only implementation: status_surface
    and assert_truthful_publication both call it, so the two cannot drift apart.
    `personal` is the resolved verdict (record flag, account_type, or the
    declaration's own personal_profile) so a renamed account type cannot launder
    a personal profile past the rule.
    """
    if personal is None:
        personal = _is_personal_record(record)
    if record.get("route") == "unattended" and personal:
        raise UntruthfulPublication(
            f"record {record.get('placement_id')} is a personal profile on the "
            "unattended route; a personal profile can never use the unattended "
            "publication route"
        )


def _is_personal_record(record: dict) -> bool:
    """The ONE predicate for "this record is a personal profile / personal account"."""
    return bool(record.get("personal_profile")) or record.get("account_type") == "personal"


def _truth_of(record: dict, path: Optional[str] = None) -> dict:
    """The ONE truth evaluator behind both the status surface and the guard.

    status_surface() returns what this returns; assert_truthful_publication()
    only checks that it does not raise. One record therefore gets one verdict and
    one exception, in both directions. Nothing here relabels a claim: an
    untruthful or malformed record is refused.
    """
    caps = load_capabilities(path)
    policy = caps["policy"]
    if not isinstance(record, dict):
        raise CapabilityError("a placement record is required")
    route = record.get("route")
    status = record.get("status")
    channel = record.get("channel")
    account_type = record.get("account_type")
    placement_id = record.get("placement_id")
    receipt = record.get("receipt") if isinstance(record.get("receipt"), dict) else None

    if route not in ("assisted", "unattended"):
        raise UntruthfulPublication(
            f"record {placement_id} has no declared route; publication "
            "cannot be claimed"
        )

    # The declaration is the only source of capability. An undeclared channel,
    # account type or action is refused before any claim is rendered, so a
    # hand-built record cannot invent a capability the declaration never granted.
    declared = _resolve_declared(caps, channel, account_type)
    personal = _is_personal_record(record) or bool(declared.get("personal_profile"))
    _reject_personal_on_unattended(record, personal)

    if route == "assisted":
        if declared.get("mode") != "assisted":
            raise CapabilityError(
                f"record {placement_id} claims the assisted route for "
                f"{channel}/{account_type}, but the declaration gives that account "
                f"type mode '{declared.get('mode')}'; a route the declaration does "
                "not grant cannot be rendered"
            )
        action = record.get("action")
        if isinstance(action, str) and action.strip():
            action_id = action.strip().lower()
            if action_id not in declared.get("operator_action", []):
                raise CapabilityError(
                    f"record {placement_id} claims action '{action_id}' for "
                    f"{channel}/{account_type}, which the declaration does not list "
                    f"as an operator action (declared: {declared.get('operator_action')})"
                )
        forbidden = policy["assisted_forbidden_statuses"]
        if status in forbidden:
            raise UntruthfulPublication(
                f"record {placement_id} claims '{status}' for an "
                f"assisted/personal placement: {forbidden[status]}"
            )
        allowed = policy["assisted_statuses"]
        if status not in allowed:
            raise CapabilityError(
                f"assisted placement status '{status}' is not in the truthful "
                f"vocabulary {sorted(allowed)}"
            )
        if record.get("published_by_system") is True or record.get("published") is True:
            raise UntruthfulPublication(
                f"record {placement_id} claims a system publication; an "
                "assisted/personal placement requires an operator receipt and may "
                "never be reported as published by the system"
            )
        # A claim must bind to a placement its own inputs can reproduce.
        try:
            provenance = _placement_provenance(record)
        except CapabilityError as exc:
            raise UntruthfulPublication(
                f"record {placement_id} cannot reproduce its own placement, so its "
                f"status claim proves nothing: {exc}"
            ) from exc
        if provenance != placement_id:
            raise UntruthfulPublication(
                f"record {placement_id} does not recompute to its own placement "
                f"(digest '{provenance}'); a status claim is proof only for the "
                "placement it can be derived from"
            )
        if status == "operator-confirmed":
            if not _is_sanctioned(record, path):
                raise UntruthfulPublication(
                    f"record {placement_id} is operator-confirmed without the "
                    "sanctioned provenance marker; an operator receipt is minted only "
                    "by record_operator_confirmation(), and a hand-built dict cannot "
                    "be rendered as a verified approval"
                )
            if not _valid_receipt(receipt, record, path):
                raise UntruthfulPublication(
                    f"record {placement_id} is operator-confirmed without a "
                    "valid operator receipt"
                )
            claim = "operator-confirmed"
        else:
            if receipt is not None:
                raise UntruthfulPublication(
                    f"record {placement_id} is awaiting-operator but carries "
                    "a receipt"
                )
            claim = "nothing-posted"
        return {
            "placement_id": placement_id,
            "channel": channel,
            "account_type": account_type,
            "route": "assisted",
            "status": status,
            "label": allowed[status],
            "claim": claim,
            "provenance": "sanctioned" if _is_sanctioned(record, path) else "unverified",
            "published_by_system": False,
            "receipt": receipt,
        }

    # Unattended. The declaration may grant the route, but this contract collects
    # and verifies NO public-monitor evidence, so an unattended publication is
    # never claimed. Refusing here is what keeps "published-by-system" honest.
    if declared.get("mode") != "unattended":
        raise CapabilityError(
            f"record {placement_id} claims the unattended route for "
            f"{channel}/{account_type}, but the declaration gives that account type "
            f"mode '{declared.get('mode')}'; a route the declaration does not grant "
            "cannot be rendered"
        )
    action = record.get("action")
    if isinstance(action, str) and action.strip():
        action_id = action.strip().lower()
        if action_id not in declared.get("unattended", []):
            raise CapabilityError(
                f"record {placement_id} claims unattended action '{action_id}' for "
                f"{channel}/{account_type}, which the declaration does not list as "
                f"unattended (declared: {declared.get('unattended')})"
            )
    coverage = policy["unattended_coverage"]
    decision = coverage["owner_decision"]
    raise UntruthfulPublication(
        f"record {placement_id} claims '{status}' on the unattended route, but no "
        f"public-monitor evidence exists for {channel}/{account_type} in this "
        f"contract: coverage is '{coverage['status']}', so no system publication may "
        "be reported. Required proof before the claim is allowed: "
        f"{'; '.join(coverage['required_proof'])}. Owner who must decide it: "
        f"{decision['owner']} (decision: {decision['decision']}; status: "
        f"{decision['status']})."
    )


def status_surface(record: dict, path: Optional[str] = None) -> dict:
    """Render the truthful status. Assisted never reports published-by-system."""
    return _truth_of(record, path)


def assert_truthful_publication(record: dict, path: Optional[str] = None) -> bool:
    """Guard: a publication claim without an operator receipt is a failure."""
    _truth_of(record, path)
    return True


def unattended_coverage(path: Optional[str] = None) -> dict:
    """Report what is NOT proved about unattended publication.

    This never returns a monitoring claim. It states the coverage status, the
    proof that would be required, and the owner who must decide it, straight from
    the declaration, so a consumer cannot mistake "declared unattended" for
    "observed and monitored".
    """
    caps = load_capabilities(path)
    coverage = copy.deepcopy(caps["policy"]["unattended_coverage"])
    coverage["monitoring"] = False
    coverage["claim"] = "coverage-unproved"
    coverage["note"] = (
        "No public monitor runs in this contract. An unattended publication may "
        "not be reported until the required proof exists and the named owner "
        "approves it."
    )
    return coverage


def capability_summary(path: Optional[str] = None) -> dict:
    """Compact machine-readable summary for Command Center consumption."""
    caps = load_capabilities(path)
    rows = []
    for channel_id, channel in caps["channels"].items():
        for account_id, account in channel["account_types"].items():
            rows.append(
                {
                    "channel": channel_id,
                    "channel_label": channel.get("channel_label"),
                    "account_type": account_id,
                    "label": account.get("label"),
                    "mode": account.get("mode"),
                    "personal_profile": bool(account.get("personal_profile")),
                    "path": account.get("path"),
                    "unattended": list(account.get("unattended") or []),
                    "operator_action": list(account.get("operator_action") or []),
                    "unavailable": list(account.get("unavailable") or []),
                    "checked_at": channel.get("checked_at"),
                }
            )
    return {
        "version": caps["policy"]["version"],
        "declared_at": caps["policy"]["declared_at"],
        "source": caps["policy"]["single_source_of_truth"],
        "assisted_statuses": list(caps["policy"]["assisted_statuses"]),
        "forbidden_assisted_statuses": list(
            caps["policy"]["assisted_forbidden_statuses"]
        ),
        "unattended_coverage": unattended_coverage(path),
        "records": rows,
    }
