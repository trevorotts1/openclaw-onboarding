#!/usr/bin/env python3
"""access_adapter.py - T-15 real bonus access adapter and failed-step resume.

Contract basis: Purple-Billboard SPEC.md ("GHL membership is a candidate pending
mobile-only identity, entitlement, credential, SMS and return/recovery proof"),
DATA-CONTRACTS.md section 6, TODO.md T-15, requirement R-13 and check C-15.
Python 3 standard library only. No network, no provider, no model, no secrets.

Acceptance, verbatim: "Separate identity/grant/credential/SMS/resource
authorization; return access and email-later same member."

SEPARATE.    Five authorization dimensions -- identity, grant, credential, SMS
             and resource -- are evaluated one at a time and reported one at a
             time. A verdict is about its own dimension and nothing else: a
             pass on one never mints a pass on another, and a denial on one
             never marks another denied. `authorize()` is pure; sweeping one
             dimension through every state leaves the other four byte-identical.
             Credential is not resource: an expired credential is not expired
             guides. SMS permission is not identity: being allowed to text a
             handle says nothing about who the member is.

SAME MEMBER. A member is one identity across both channels. An SMS handle and
             an email handle are bound to a member id, and each binding refuses
             to move to a different member. A failed step is recorded against
             the member the channel resolved to, and a resume is refused unless
             the returning channel resolves to that same member. Email-later is
             a deferral of the SAME member, not a second member created by
             collecting an address.

RESUME.      A failed step is kept with its dimension and its reason, so a
             return resumes the exact step that failed instead of restarting
             the flow or re-sending blind.

WHAT THIS IS NOT. It is not a provider client. No automated bonus-access route
             is proved (T-14 `bonus-access-capability-decision`, candidate
             origin/pb/PBB-356/t-14-repair3@dc5c25aa5, decision BLOCKED), so no
             vendor operation, URL or verb lives here and `automated` is False
             on every result. Authorization is not transport: even with all five
             dimensions authorized, the next action is an operator step and the
             module issues no credential and claims no grant. The T-14 module is
             not imported -- it is not on main -- so the same five-step
             vocabulary is restated here rather than coupled to an unmerged
             branch. When T-14 lands, its per-step states are passed into
             `authorize(states=...)` unchanged.

Independent original gift (D-28 / C-F07): this module exposes no original-lane
             field and imports no fulfillment module, so a blocked bonus lane
             cannot gate the original promise.

Import:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from access_adapter import AccessLedger, authorize

Assert-based self-check:  python3 -I access_adapter.py
"""

from __future__ import annotations

import dataclasses
from typing import Dict, List, Mapping, Optional, Tuple

# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------

# The five authorization questions. Each one can fail alone.
DIMENSIONS: Tuple[str, ...] = ("identity", "grant", "credential", "sms", "resource")

AUTHORIZED = "authorized"
DENIED = "denied"
UNVERIFIED = "unverified"

_STATES: Tuple[str, ...] = (AUTHORIZED, DENIED, UNVERIFIED)

# The channels a member can be reached on. They map to ONE member.
CHANNELS: Tuple[str, ...] = ("sms", "email")

# How a member comes back. The returning channel must be the one named here.
RETURN_VIAS: Tuple[str, ...] = ("sms_return", "email")

_VIA_CHANNEL: Dict[str, str] = {"sms_return": "sms", "email": "email"}

BLOCK_REASON = "BONUS_ACCESS_AUTOMATION_UNAVAILABLE"


class AccessAdapterError(ValueError):
    """An input or state this adapter does not support."""


class MemberContinuityError(AccessAdapterError):
    """A channel handle already belongs to a different member."""


def _text(value: object, name: str) -> str:
    """A required non-empty string, refused rather than coerced."""
    if not isinstance(value, str):
        raise AccessAdapterError(f"{name} must be a str, got {type(value).__name__}")
    cleaned = value.strip()
    if not cleaned:
        raise AccessAdapterError(f"{name} must not be empty")
    return cleaned


def _state(value: object, dimension: str) -> str:
    """Normalise one dimension's state; an unknown state is refused."""
    state = _text(value, f"state[{dimension}]").lower()
    if state not in _STATES:
        raise AccessAdapterError(
            f"state[{dimension}] must be one of {list(_STATES)}, got {value!r}"
        )
    return state


# --------------------------------------------------------------------------
# Per-dimension authorization
# --------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class DimensionVerdict:
    """What is known about ONE authorization dimension, and nothing else."""

    dimension: str
    state: str
    reason: str

    @property
    def authorized(self) -> bool:
        return self.state == AUTHORIZED

    def as_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "state": self.state,
            "reason": self.reason,
            "authorized": self.authorized,
        }


@dataclasses.dataclass(frozen=True)
class AccessAuthorization:
    """Five independent verdicts for one member."""

    member_id: str
    verdicts: Tuple[DimensionVerdict, ...]

    def verdict(self, dimension: str) -> DimensionVerdict:
        name = _text(dimension, "dimension").lower()
        for verdict in self.verdicts:
            if verdict.dimension == name:
                return verdict
        raise AccessAdapterError(f"unknown dimension {dimension!r}")

    @property
    def blocked_dimensions(self) -> List[str]:
        return [v.dimension for v in self.verdicts if not v.authorized]

    @property
    def authorized(self) -> bool:
        """True only when every dimension is authorized on its own evidence."""
        return not self.blocked_dimensions

    def next_action(self) -> str:
        """The operator step. There is no automated transport in this module."""
        if self.authorized:
            return "operator_issue_credential"
        return "operator_grant_required"

    def as_dict(self) -> dict:
        return {
            "task_id": "T-15",
            "member_id": self.member_id,
            "dimensions": list(DIMENSIONS),
            "verdicts": [v.as_dict() for v in self.verdicts],
            "blocked_dimensions": self.blocked_dimensions,
            "authorized": self.authorized,
            "next_action": self.next_action(),
            "automated": False,
            "reason_code": None if self.authorized else BLOCK_REASON,
            "system_claimed_grant": False,
        }


def authorize(
    *,
    member_id: str,
    states: Mapping[str, str],
    reasons: Optional[Mapping[str, str]] = None,
) -> AccessAuthorization:
    """Build five independent verdicts from five independent states.

    `states` must name exactly the five dimensions. A missing dimension is
    refused rather than defaulted, because a default is an authorization
    nobody granted. Reasons are per dimension and are never borrowed.
    """
    member = _text(member_id, "member_id")
    if not isinstance(states, Mapping):
        raise AccessAdapterError(
            f"states must be a mapping, got {type(states).__name__}"
        )
    given = {_text(k, "states key").lower() for k in states}
    missing = [d for d in DIMENSIONS if d not in given]
    extra = sorted(given - set(DIMENSIONS))
    if missing:
        raise AccessAdapterError(f"states is missing dimensions {missing}")
    if extra:
        raise AccessAdapterError(f"states names unknown dimensions {extra}")

    reason_map: Dict[str, str] = {}
    if reasons is not None:
        if not isinstance(reasons, Mapping):
            raise AccessAdapterError(
                f"reasons must be a mapping, got {type(reasons).__name__}"
            )
        for key, value in reasons.items():
            reason_map[_text(key, "reasons key").lower()] = _text(value, "reason")

    normalized = {str(k).strip().lower(): v for k, v in states.items()}
    verdicts = tuple(
        DimensionVerdict(
            dimension=dimension,
            state=_state(normalized[dimension], dimension),
            reason=reason_map.get(dimension, ""),
        )
        for dimension in DIMENSIONS
    )
    return AccessAuthorization(member_id=member, verdicts=verdicts)


# --------------------------------------------------------------------------
# Failed-step resume, channel bindings and email-later
# --------------------------------------------------------------------------


class AccessLedger:
    """Channel bindings, failed steps and email deferrals for one tenant.

    The ledger is the only place a member id is associated with a channel
    handle, so "same member" is decided once instead of by each caller. State
    is in memory: the caller owns durability, and the SQLite ledger of record
    for outbound effects stays `direct_fulfillment.FulfillmentLedger`. A
    process restart therefore loses pending resume state -- that is the stated
    ceiling of this class, not a hidden one.
    """

    def __init__(self) -> None:
        self._bindings: Dict[Tuple[str, str], str] = {}
        self._failures: Dict[str, Dict[str, dict]] = {}
        self._deferred: Dict[str, dict] = {}

    # -- bindings ---------------------------------------------------------

    def bind(self, *, member_id: str, channel: str, handle: str) -> dict:
        """Bind one channel handle to one member, refusing to move it."""
        member = _text(member_id, "member_id")
        chan = _text(channel, "channel").lower()
        if chan not in CHANNELS:
            raise AccessAdapterError(f"channel must be one of {list(CHANNELS)}, got {channel!r}")
        value = _text(handle, "handle")
        key = (chan, value)
        owner = self._bindings.get(key)
        if owner is not None and owner != member:
            raise MemberContinuityError(
                f"{chan} handle is already bound to a different member"
            )
        self._bindings[key] = member
        return {
            "member_id": member,
            "channel": chan,
            "handle": value,
            "already_bound": owner == member,
        }

    def member_for(self, *, channel: str, handle: str) -> Optional[str]:
        """The member a channel handle resolves to, or None when unbound."""
        chan = _text(channel, "channel").lower()
        if chan not in CHANNELS:
            raise AccessAdapterError(f"channel must be one of {list(CHANNELS)}, got {channel!r}")
        return self._bindings.get((chan, _text(handle, "handle")))

    # -- failed steps -----------------------------------------------------

    def record_failed_step(
        self,
        *,
        member_id: str,
        dimension: str,
        reason: str,
        channel: str,
        handle: str,
    ) -> dict:
        """Record which step failed, for which member, reached over which channel.

        The handle must already resolve to this member: a failure is never
        attributed to a member the record cannot prove was reached.
        """
        member = _text(member_id, "member_id")
        dim = _text(dimension, "dimension").lower()
        if dim not in DIMENSIONS:
            raise AccessAdapterError(f"dimension must be one of {list(DIMENSIONS)}, got {dimension!r}")
        why = _text(reason, "reason")
        chan = _text(channel, "channel").lower()
        value = _text(handle, "handle")
        owner = self.member_for(channel=chan, handle=value)
        if owner is None:
            raise AccessAdapterError(f"{chan} handle is not bound to any member")
        if owner != member:
            raise MemberContinuityError("the failure channel resolves to a different member")

        record = {
            "member_id": member,
            "dimension": dim,
            "reason": why,
            "channel": chan,
            "handle": value,
        }
        self._failures.setdefault(member, {})[dim] = record
        return dict(record)

    def failed_steps(self, *, member_id: str) -> List[dict]:
        member = _text(member_id, "member_id")
        return [dict(r) for r in self._failures.get(member, {}).values()]

    # -- email later ------------------------------------------------------

    def defer_to_email(self, *, member_id: str, handle: str) -> dict:
        """Defer to email for the SAME member; never create a second one."""
        member = _text(member_id, "member_id")
        value = _text(handle, "handle")
        owner = self.member_for(channel="email", handle=value)
        if owner is not None and owner != member:
            raise MemberContinuityError(
                "the email handle already belongs to a different member"
            )
        self._bindings[("email", value)] = member
        record = {
            "member_id": member,
            "channel": "email",
            "handle": value,
            "deferred": True,
            "pending_dimensions": sorted(self._failures.get(member, {})),
        }
        self._deferred[member] = record
        return dict(record)

    def deferral(self, *, member_id: str) -> Optional[dict]:
        member = _text(member_id, "member_id")
        record = self._deferred.get(member)
        return dict(record) if record else None

    # -- resume -----------------------------------------------------------

    def resume(self, *, channel: str, handle: str, via: str) -> dict:
        """Resume the exact failed steps for the member who came back.

        The returning channel and the return path must agree, and both must
        resolve to the member whose step failed. A member returning over a
        channel that proves a different identity is refused: this is the whole
        point of keeping the bindings in one place.
        """
        chan = _text(channel, "channel").lower()
        if chan not in CHANNELS:
            raise AccessAdapterError(f"channel must be one of {list(CHANNELS)}, got {channel!r}")
        route = _text(via, "via").lower()
        if route not in RETURN_VIAS:
            raise AccessAdapterError(f"via must be one of {list(RETURN_VIAS)}, got {via!r}")
        if _VIA_CHANNEL[route] != chan:
            raise MemberContinuityError(
                f"return path {route!r} cannot arrive over the {chan!r} channel"
            )

        value = _text(handle, "handle")
        member = self.member_for(channel=chan, handle=value)
        if member is None:
            raise AccessAdapterError(f"{chan} handle is not bound to any member")

        steps = self.failed_steps(member_id=member)
        if not steps:
            return {
                "member_id": member,
                "via": route,
                "channel": chan,
                "status": "nothing_to_resume",
                "resumed_dimensions": [],
                "same_member": True,
            }
        return {
            "member_id": member,
            "via": route,
            "channel": chan,
            "status": "resumed",
            "resumed_dimensions": sorted(s["dimension"] for s in steps),
            "same_member": True,
        }


# --------------------------------------------------------------------------
# Self-check
# --------------------------------------------------------------------------

if __name__ == "__main__":  # pragma: no cover
    import json
    import sys

    ok = authorize(
        member_id="m-1",
        states={d: UNVERIFIED for d in DIMENSIONS},
        reasons={"identity": "no mobile-only identity is proved"},
    )
    ledger = AccessLedger()
    ledger.bind(member_id="m-1", channel="sms", handle="sms-1")
    ledger.record_failed_step(
        member_id="m-1",
        dimension="identity",
        reason="no mobile-only identity is proved",
        channel="sms",
        handle="sms-1",
    )
    resumed = ledger.resume(channel="sms", handle="sms-1", via="sms_return")
    assert ok.blocked_dimensions == list(DIMENSIONS)
    assert ok.authorized is False and ok.next_action() == "operator_grant_required"
    assert resumed["same_member"] is True and resumed["status"] == "resumed"
    print(json.dumps({"authorization": ok.as_dict(), "resume": resumed}, indent=2, sort_keys=True))
    sys.exit(0)
