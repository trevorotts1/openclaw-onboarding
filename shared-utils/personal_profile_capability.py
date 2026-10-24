#!/usr/bin/env python3
"""personal_profile_capability.py — T-22 honest personal-profile capability
and assisted contract.

ONE source of truth: 35-social-media-planner/config/profile-capabilities.json.
This module is the consumer used by the assisted workflow, the status surface,
the refusal path and the truth guard. Nothing here guesses: a channel/account
type is unattended only when the declaration says so, and a personal profile is
always assisted (or unavailable), never automated.

Assisted contract:
  1. request_placement(unattended=True) on a personal profile is REFUSED with a
     plain limitation and an explicit assisted offer. No silent downgrade and no
     fake success.
  2. prepare_assisted_placement() builds the exact placement (text, asset,
     keyword, CTA, timing) and a one-step operator instruction. Status is
     "awaiting-operator"; there is no receipt.
  3. record_operator_confirmation() turns it into "operator-confirmed" ONLY when
     the operator explicitly confirms. The receipt is the only proof.
  4. status_surface() reports awaiting-operator / operator-confirmed and never
     published-by-system for an assisted placement.
  5. assert_truthful_publication() raises UntruthfulPublication when a record
     claims a system publication without an operator receipt.

STDLIB ONLY. No network.
"""

from __future__ import annotations

import copy
import datetime as _dt
import hashlib
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
    capability: dict,
    offer_assisted: bool,
) -> dict:
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
            capability,
            offer_assisted=bool(capability["operator_action"]),
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
            capability,
            offer_assisted=False,
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
            capability,
            offer_assisted=action_id in capability["operator_action"],
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


def _validate_placement(placement: dict) -> dict:
    if not isinstance(placement, dict):
        raise CapabilityError("placement must be an object")
    for field in _REQUIRED_PLACEMENT_FIELDS:
        if field not in placement:
            raise CapabilityError(f"placement missing required field '{field}'")
        value = placement[field]
        empty = value is None or (
            isinstance(value, str) and not value.strip()
        ) or (isinstance(value, (list, dict)) and not value)
        if empty:
            raise CapabilityError(f"placement field '{field}' must not be empty")
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
    if capability["mode"] not in ("assisted", "unattended"):
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
    placement_id = _placement_id(
        capability["channel"], capability["account_type"], action_id, clean
    )
    return {
        "placement_id": placement_id,
        "channel": capability["channel"],
        "channel_label": capability["channel_label"],
        "account_type": capability["account_type"],
        "account_label": capability["label"],
        "action": action_id,
        "route": "assisted",
        "status": "awaiting-operator",
        "placement": clean,
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


def _now_utc() -> str:
    return (
        _dt.datetime.now(_dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _valid_receipt(receipt: Any, placement_id: Optional[str] = None) -> bool:
    if not isinstance(receipt, dict):
        return False
    caps = load_capabilities()
    for field in caps["policy"]["receipt_required_fields"]:
        value = receipt.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            return False
    if placement_id is not None and receipt.get("placement_id") != placement_id:
        return False
    return True


def record_operator_confirmation(
    package: dict,
    operator: str,
    confirmed_at: Optional[str] = None,
    evidence: Optional[Any] = None,
) -> dict:
    """Record an explicit operator confirmation as the receipt.

    Refuses without a named operator. Never produces 'published-by-system'.
    """
    if not isinstance(package, dict) or package.get("route") != "assisted":
        raise CapabilityError("only an assisted placement can receive an operator confirmation")
    if package.get("status") != "awaiting-operator":
        raise CapabilityError(
            f"placement {package.get('placement_id')} is '{package.get('status')}', "
            "not awaiting-operator"
        )
    name = (operator or "").strip()
    if not name:
        raise CapabilityError(
            "operator confirmation requires a named operator; the system cannot "
            "confirm on the operator's behalf"
        )
    confirmed = copy.deepcopy(package)
    receipt = {
        "placement_id": confirmed.get("placement_id"),
        "operator": name,
        "confirmed_at": confirmed_at or _now_utc(),
        "method": "operator-asserted",
        "evidence": evidence,
    }
    confirmed["receipt"] = receipt
    confirmed["status"] = "operator-confirmed"
    confirmed["published_by_system"] = False
    return confirmed


def status_surface(record: dict, path: Optional[str] = None) -> dict:
    """Render the truthful status. Assisted never reports published-by-system."""
    caps = load_capabilities(path)
    policy = caps["policy"]
    if not isinstance(record, dict):
        raise CapabilityError("status_surface requires a placement record")
    route = record.get("route")
    status = record.get("status")
    channel = record.get("channel")
    account_type = record.get("account_type")
    label = None
    if route == "assisted":
        forbidden = policy["assisted_forbidden_statuses"]
        if status in forbidden:
            raise UntruthfulPublication(
                f"assisted placement {record.get('placement_id')} cannot report "
                f"'{status}': {forbidden[status]}"
            )
        allowed = policy["assisted_statuses"]
        if status not in allowed:
            raise CapabilityError(
                f"assisted placement status '{status}' is not in the truthful "
                f"vocabulary {sorted(allowed)}"
            )
        receipt = record.get("receipt")
        if status == "operator-confirmed":
            if not _valid_receipt(receipt, record.get("placement_id")):
                raise UntruthfulPublication(
                    f"placement {record.get('placement_id')} reports operator-confirmed "
                    "without a valid operator receipt"
                )
            claim = "operator-confirmed"
        else:
            if receipt is not None:
                raise UntruthfulPublication(
                    f"placement {record.get('placement_id')} is awaiting-operator and "
                    "must not carry a receipt"
                )
            claim = "nothing-posted"
        label = allowed[status]
        return {
            "placement_id": record.get("placement_id"),
            "channel": channel,
            "account_type": account_type,
            "route": "assisted",
            "status": status,
            "label": label,
            "claim": claim,
            "published_by_system": False,
            "receipt": receipt,
        }
    if route == "unattended":
        if status != "published-by-system":
            raise CapabilityError(
                f"unattended placement status '{status}' is not supported"
            )
        return {
            "placement_id": record.get("placement_id"),
            "channel": channel,
            "account_type": account_type,
            "route": "unattended",
            "status": status,
            "label": "Published by the system through the declared unattended path.",
            "claim": "published-by-system",
            "published_by_system": True,
            "receipt": record.get("receipt"),
        }
    raise CapabilityError(f"unknown placement route '{route}'")


def assert_truthful_publication(record: dict, path: Optional[str] = None) -> bool:
    """Guard: a publication claim without an operator receipt is a failure."""
    if not isinstance(record, dict):
        raise CapabilityError("publication guard requires a record")
    route = record.get("route")
    status = record.get("status")
    personal = bool(record.get("personal_profile")) or (
        record.get("account_type") == "personal"
    )
    claims_publication = (
        record.get("published_by_system") is True
        or record.get("published") is True
        or status in ("published-by-system", "published")
    )
    receipt = record.get("receipt") if isinstance(record.get("receipt"), dict) else None

    if route == "assisted" or personal:
        caps = load_capabilities(path)
        forbidden = caps["policy"]["assisted_forbidden_statuses"]
        if status in forbidden:
            raise UntruthfulPublication(
                f"record {record.get('placement_id')} claims '{status}' for an "
                f"assisted/personal placement: {forbidden[status]}"
            )
        if record.get("published_by_system") is True or record.get("published") is True:
            raise UntruthfulPublication(
                f"record {record.get('placement_id')} claims a system publication; "
                "an assisted/personal placement requires an operator receipt and may "
                "never be reported as published by the system"
            )
        if claims_publication and not _valid_receipt(receipt, record.get("placement_id")):
            raise UntruthfulPublication(
                f"record {record.get('placement_id')} claims publication without an "
                "operator receipt"
            )
        if status == "operator-confirmed" and not _valid_receipt(
            receipt, record.get("placement_id")
        ):
            raise UntruthfulPublication(
                f"record {record.get('placement_id')} is operator-confirmed without a "
                "valid operator receipt"
            )
        if status == "awaiting-operator" and receipt is not None:
            raise UntruthfulPublication(
                f"record {record.get('placement_id')} is awaiting-operator but carries "
                "a receipt"
            )
        return True

    if route == "unattended":
        if record.get("personal_profile") or record.get("account_type") == "personal":
            raise UntruthfulPublication(
                "a personal profile can never use the unattended publication route"
            )
        return True

    raise UntruthfulPublication(
        f"record {record.get('placement_id')} has no declared route; publication "
        "cannot be claimed"
    )


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
        "records": rows,
    }
