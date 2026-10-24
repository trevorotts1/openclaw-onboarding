#!/usr/bin/env python3
"""route_adapter.py - the supported Instagram comment and direct routes.

Contract basis: Purple-Billboard DATA-CONTRACTS.md sections 2-4 and SPEC.md
lines 21 and 26. Python 3 standard library only; no network; no model.

What this module exists to guarantee (task T-21 acceptance):

SEPARATE ACCOUNT.  An Instagram account is its own record: tenant_id,
account_id, ig_user_id and binding_revision. A Facebook page id never
resolves an Instagram account and never satisfies an Instagram binding.
A changed binding quarantines queued work; it is never rerouted silently.

SEPARATE FILTER.  Comment filters are Instagram-scoped and account-scoped.
A filter bound to another account or declared for Facebook matches nothing
here, and own reveal/outgoing events are excluded by verified actor.

SEPARATE EVENT.  Only the two supported routes are normalised: an inbound
Instagram COMMENT and an inbound Instagram DIRECT message. Facebook Page
comments, Messenger events and unknown kinds are refused, not adapted.

SEPARATE ELIGIBILITY.  Instagram eligibility is computed from Instagram
facts only. A comment public reply has its own basis. A comment private
opener has its own platform permission, and a comment alone is NOT a normal
inbound-DM window (`inbound_dm_window` is False). A direct message needs an
actual inbound customer DM. Outbound and cross-channel messages never
refresh Instagram eligibility, and an eligibility basis carried over from
Facebook is refused.

IGNORED OPENER, NO DRIP.  Once a private opener is recorded for a thread,
every follow-up direct message is suppressed until the customer actually
interacts (a verified inbound DM on that thread). There is no timed drip and
no second opener. The state is durable, so a restart changes nothing.

No second send guard is written here: outbound_gate.dispatch() remains the
only dispatcher and durable_store remains the only durable outbox. This
module supplies the Instagram-specific evaluator and route state; the gate
still runs fresh on every attempt.

Import (repo root on sys.path or this directory inserted):

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from route_adapter import (
        InstagramAccount, InstagramCommentFilter, InstagramEvent,
        InstagramRouteStore, make_gate_evaluator, evaluate_eligibility,
    )

Assert-based self-check:  python3 -I route_adapter.py
"""

from __future__ import annotations

import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

SCHEMA_VERSION = 1

PLATFORM_IG = "IG"
PROVIDER_IG = "instagram"

CHANNEL_IG_PUBLIC = "IG_PUBLIC"
CHANNEL_IG_DM = "IG_DM"
IG_CHANNELS = (CHANNEL_IG_PUBLIC, CHANNEL_IG_DM)

# Supported routes. Anything else is refused: this adapter does not guess.
ROUTE_COMMENT = "comment"
ROUTE_DIRECT = "direct"
ROUTES = (ROUTE_COMMENT, ROUTE_DIRECT)

EVENT_COMMENT = "COMMENT"
EVENT_DIRECT = "DIRECT"
EVENT_KINDS = (EVENT_COMMENT, EVENT_DIRECT)
DIRECTION_INBOUND = "inbound"
DIRECTION_OUTBOUND = "outbound"
DIRECTIONS = (DIRECTION_INBOUND, DIRECTION_OUTBOUND)

PURPOSE_PUBLIC_REPLY = "PUBLIC_REPLY"
PURPOSE_COMMENT_PRIVATE_OPENER = "COMMENT_PRIVATE_OPENER"
PURPOSE_AI_REPLY = "AI_REPLY"
PURPOSE_ORIGINAL_GIFT = "ORIGINAL_GIFT"
PURPOSE_ACCESS_PASS = "ACCESS_PASS"
PURPOSE_EMAIL_BACKUP = "EMAIL_BACKUP"
PURPOSE_CAPTURE_REMINDER = "CAPTURE_REMINDER"
PURPOSE_BOOKING_CONFIRMATION = "BOOKING_CONFIRMATION"
PURPOSE_HANDOFF_NOTICE = "HANDOFF_NOTICE"

PUBLIC_REPLY_PURPOSES = (PURPOSE_PUBLIC_REPLY,)
# Direct (DM) purposes. COMMENT_PRIVATE_OPENER is the comment's own private
# reply permission; the rest are ordinary person-directed DM follow-ups.
DM_PURPOSES = (
    PURPOSE_COMMENT_PRIVATE_OPENER,
    PURPOSE_AI_REPLY,
    PURPOSE_ORIGINAL_GIFT,
    PURPOSE_ACCESS_PASS,
    PURPOSE_EMAIL_BACKUP,
    PURPOSE_CAPTURE_REMINDER,
    PURPOSE_BOOKING_CONFIRMATION,
    PURPOSE_HANDOFF_NOTICE,
)
FOLLOW_UP_DM_PURPOSES = tuple(p for p in DM_PURPOSES
                              if p != PURPOSE_COMMENT_PRIVATE_OPENER)

# DATA-CONTRACTS section 3: eligibility evidence bases. Only the first three
# can REFRESH platform eligibility; outbound and cross-channel cannot.
BASIS_INBOUND_MESSAGE = "INBOUND_MESSAGE"
BASIS_CONSENT_RECORD = "CONSENT_RECORD"
BASIS_PLATFORM_ELIGIBILITY = "PLATFORM_ELIGIBILITY"
BASIS_OUTBOUND_MESSAGE = "OUTBOUND_MESSAGE"
BASIS_CROSS_CHANNEL_MESSAGE = "CROSS_CHANNEL_MESSAGE"
ELIGIBILITY_BASES = (
    BASIS_INBOUND_MESSAGE,
    BASIS_CONSENT_RECORD,
    BASIS_PLATFORM_ELIGIBILITY,
    BASIS_OUTBOUND_MESSAGE,
    BASIS_CROSS_CHANNEL_MESSAGE,
)
REFRESHING_BASES = (
    BASIS_INBOUND_MESSAGE,
    BASIS_CONSENT_RECORD,
    BASIS_PLATFORM_ELIGIBILITY,
)
NON_REFRESHING_BASES = (BASIS_OUTBOUND_MESSAGE, BASIS_CROSS_CHANNEL_MESSAGE)

# Facebook capability names that must never be borrowed for Instagram. This
# is an explicit deny list, not a mapping: there is no FB-to-IG table here.
FB_ONLY_CAPABILITIES = (
    "FB_PAGE_PUBLIC_COMMENT",
    "FB_PAGE_PRIVATE_REPLY",
    "FB_MESSENGER_STANDARD_WINDOW",
    "FB_MESSENGER_HUMAN_AGENT_WINDOW",
)

CAP_COMMENT_PUBLIC_REPLY = "IG_PUBLIC_REPLY"
CAP_COMMENT_PRIVATE_OPENER = "IG_COMMENT_PRIVATE_OPENER"
CAP_DM_SEND = "IG_DM_SEND"
IG_CAPABILITIES = (CAP_COMMENT_PUBLIC_REPLY, CAP_COMMENT_PRIVATE_OPENER,
                   CAP_DM_SEND)

# Eligibility refusal reasons. Stable strings so tests and logs can pin them.
R_ACCOUNT_FB = "ig:no_inferred_fb_parity"
R_ACCOUNT_BINDING = "ig:account_rebinding"
R_UNKNOWN_ROUTE = "ig:unsupported_route"
R_UNSUPPORTED_EVENT = "ig:unsupported_event"
R_EVENT_ACCOUNT_MISMATCH = "ig:event_account_mismatch"
R_EVENT_WRONG_KIND = "ig:event_wrong_kind"
R_FILTER_ACCOUNT_MISMATCH = "ig:filter_account_mismatch"
R_FILTER_NOT_MATCHED = "ig:comment_filter_not_matched"
R_CAPABILITY_MISSING = "ig:capability_missing"
R_CAPABILITY_FB = "ig:no_inferred_fb_parity"
R_CHANNEL_PURPOSE_MISMATCH = "ig:channel_purpose_mismatch"
R_BASIS_NOT_REFRESHING = "ig:eligibility_not_refreshed_by_outbound_or_cross_channel"
R_OPENER_ALREADY_SENT = "ig:opener_already_sent"
R_IGNORED_OPENER = "ig:ignored_opener_no_drip"
R_NO_INBOUND_DM = "ig:no_inbound_dm_window"

ALLOW = "ALLOW"
SUPPRESSED = "SUPPRESSED"
QUARANTINED = "QUARANTINED"
WAIT_UNTIL = "WAIT_UNTIL"
RECONCILE_UNKNOWN = "RECONCILE_UNKNOWN"
GATE_VERDICTS = (ALLOW, WAIT_UNTIL, SUPPRESSED, QUARANTINED, RECONCILE_UNKNOWN)


class InstagramRouteError(ValueError):
    """Malformed, foreign-platform or unsupported Instagram route input."""


def _id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InstagramRouteError("bad_input: %s must be a non-empty string" % name)
    return value


def _text(value: Any, name: str, *, allow_none: bool = False) -> Optional[str]:
    if value is None and allow_none:
        return None
    if not isinstance(value, str):
        raise InstagramRouteError("bad_input: %s must be a string" % name)
    return value


def _ts(value: Optional[float]) -> float:
    return time.time() if value is None else float(value)


def _revision(value: Any, name: str) -> str:
    return _id(value, name)


# ── separate account ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class InstagramAccount:
    """An Instagram professional account binding. Never a Facebook page."""

    tenant_id: str
    account_id: str
    ig_user_id: str
    binding_revision: str
    platform: str = PLATFORM_IG

    def __post_init__(self) -> None:
        for name in ("tenant_id", "account_id", "ig_user_id",
                     "binding_revision"):
            _id(getattr(self, name), name)
        if self.platform != PLATFORM_IG:
            raise InstagramRouteError(
                "bad_input: %s (an Instagram account cannot be %r; pass the"
                " Instagram binding, never a Facebook page)"
                % (R_ACCOUNT_FB, self.platform))


def resolve_account(accounts: Iterable[InstagramAccount], *,
                    account_id: Optional[str] = None,
                    ig_user_id: Optional[str] = None,
                    fb_page_id: Optional[str] = None) -> InstagramAccount:
    """Resolve an Instagram account by Instagram identity only.

    A facebook page id is refused even when an account is otherwise supplied:
    accepting it would infer parity from a Facebook identity.
    """
    if fb_page_id is not None:
        raise InstagramRouteError(
            "bad_input: %s (facebook page %r cannot resolve an Instagram"
            " account)" % (R_ACCOUNT_FB, fb_page_id))
    if account_id is None and ig_user_id is None:
        raise InstagramRouteError(
            "bad_input: account_id or ig_user_id is required")
    matches: List[InstagramAccount] = []
    for account in accounts:
        if not isinstance(account, InstagramAccount):
            raise InstagramRouteError("bad_input: accounts must be InstagramAccount")
        if account_id is not None and account.account_id == account_id:
            matches.append(account)
        elif ig_user_id is not None and account.ig_user_id == ig_user_id:
            matches.append(account)
    if len(matches) != 1:
        raise InstagramRouteError(
            "not_found: expected exactly one Instagram account, got %d"
            % len(matches))
    return matches[0]


# ── separate filter ────────────────────────────────────────────────────────

FILTER_EXACT = "exact"
FILTER_CONTAINS = "contains"
FILTER_MODES = (FILTER_EXACT, FILTER_CONTAINS)


@dataclass(frozen=True)
class InstagramCommentFilter:
    """A keyword filter owned by one Instagram account."""

    filter_id: str
    account_id: str
    revision: str
    keywords: Tuple[str, ...]
    match_mode: str = FILTER_EXACT
    case_sensitive: bool = False
    enabled: bool = True
    platform: str = PLATFORM_IG

    def __post_init__(self) -> None:
        for name in ("filter_id", "account_id", "revision"):
            _id(getattr(self, name), name)
        if self.platform != PLATFORM_IG:
            raise InstagramRouteError(
                "bad_input: %s (a %r filter is not an Instagram filter)"
                % (R_ACCOUNT_FB, self.platform))
        if self.match_mode not in FILTER_MODES:
            raise InstagramRouteError(
                "bad_input: match_mode %r not in %s"
                % (self.match_mode, FILTER_MODES))
        if not isinstance(self.keywords, tuple):
            raise InstagramRouteError("bad_input: keywords must be a tuple")
        for kw in self.keywords:
            _id(kw, "keywords[]")
        if not self.keywords:
            # No keywords is not "match everything".
            raise InstagramRouteError(
                "bad_input: a filter requires at least one keyword")


def match_filter(filter_: InstagramCommentFilter, text: Optional[str], *,
                 account_id: Optional[str] = None) -> bool:
    """True only for a literal keyword match on this account's own filter."""
    if not isinstance(filter_, InstagramCommentFilter):
        raise InstagramRouteError("bad_input: filter must be InstagramCommentFilter")
    if not filter_.enabled:
        return False
    if account_id is not None and filter_.account_id != account_id:
        return False
    if not isinstance(text, str) or not text.strip():
        return False
    if filter_.case_sensitive:
        haystack = text.strip()
        needles = [kw for kw in filter_.keywords]
    else:
        haystack = text.strip().casefold()
        needles = [kw.casefold() for kw in filter_.keywords]
    if filter_.match_mode == FILTER_EXACT:
        return any(haystack == kw for kw in needles)
    return any(kw in haystack for kw in needles)


# ── separate event ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class InstagramEvent:
    """A normalised Instagram route event.

    `kind` is the route (COMMENT or DIRECT), not a free-form provider label.
    `thread_key` is the durable conversation key for the route: the comment
    id for a comment, the direct thread id for a DM.
    """

    provider: str
    provider_event_id: str
    tenant_id: str
    account_id: str
    kind: str
    direction: str
    actor_id: str
    text: str
    thread_key: str
    received_at: float
    comment_id: Optional[str] = None
    payload_sha256: Optional[str] = None
    platform: str = PLATFORM_IG

    def __post_init__(self) -> None:
        if self.provider != PROVIDER_IG:
            raise InstagramRouteError(
                "bad_input: %s (provider %r is not Instagram)"
                % (R_UNSUPPORTED_EVENT, self.provider))
        if self.platform != PLATFORM_IG:
            raise InstagramRouteError(
                "bad_input: %s (event platform %r is not Instagram)"
                % (R_ACCOUNT_FB, self.platform))
        for name in ("provider_event_id", "tenant_id", "account_id",
                     "actor_id", "thread_key"):
            _id(getattr(self, name), name)
        if self.kind not in EVENT_KINDS:
            raise InstagramRouteError(
                "bad_input: %s (kind %r not in %s; Page comments and"
                " Messenger are not Instagram routes)"
                % (R_UNSUPPORTED_EVENT, self.kind, EVENT_KINDS))
        if self.direction not in DIRECTIONS:
            raise InstagramRouteError(
                "bad_input: direction %r not in %s"
                % (self.direction, DIRECTIONS))
        _text(self.text, "text")
        _ts(self.received_at)
        if self.comment_id is not None:
            _id(self.comment_id, "comment_id")


def normalise_event(raw: Dict[str, Any]) -> InstagramEvent:
    """Map one provider payload onto a supported Instagram route.

    The adapter refuses anything that is not an Instagram COMMENT or DIRECT
    event. It never adapts a Facebook shape.
    """
    if not isinstance(raw, dict):
        raise InstagramRouteError("bad_input: event must be a dict")
    unknown = set(raw) - {
        "provider", "provider_event_id", "tenant_id", "account_id", "kind",
        "direction", "actor_id", "text", "thread_key", "received_at",
        "comment_id", "payload_sha256",
    }
    if unknown:
        raise InstagramRouteError(
            "bad_input: %s (unknown event fields: %s)"
            % (R_UNSUPPORTED_EVENT, sorted(unknown)))
    return InstagramEvent(
        provider=raw.get("provider"),
        provider_event_id=raw.get("provider_event_id"),
        tenant_id=raw.get("tenant_id"),
        account_id=raw.get("account_id"),
        kind=raw.get("kind"),
        direction=raw.get("direction"),
        actor_id=raw.get("actor_id"),
        text=raw.get("text", ""),
        thread_key=raw.get("thread_key"),
        received_at=_ts(raw.get("received_at")),
        comment_id=raw.get("comment_id"),
        payload_sha256=raw.get("payload_sha256"),
    )


def admit_instagram_event(store: Any, event: InstagramEvent, *,
                          own_actor_ids: Iterable[str] = (),
                          now: Optional[float] = None) -> Dict[str, Any]:
    """Persist the event identity before any ACK, via durable_store.

    Returns durable_store.admit_event()'s dict. A duplicate event is not
    admitted twice; an outgoing event or one of our own actors is excluded,
    never decided on.
    """
    if not isinstance(event, InstagramEvent):
        raise InstagramRouteError("bad_input: event must be InstagramEvent")
    durable_store = _upstream("durable_store")
    return store.admit_event(
        provider=PROVIDER_IG,
        tenant_id=event.tenant_id,
        provider_event_id=event.provider_event_id,
        direction=event.direction,
        actor_id=event.actor_id,
        payload_sha256=event.payload_sha256,
        own_actor_ids=own_actor_ids,
        now=now,
    )


# ── separate eligibility ───────────────────────────────────────────────────

@dataclass(frozen=True)
class InstagramCapability:
    """One Instagram platform capability. Platform is part of its identity."""

    name: str
    platform: str = PLATFORM_IG
    granted: bool = True

    def __post_init__(self) -> None:
        _id(self.name, "name")
        if self.name in FB_ONLY_CAPABILITIES or self.platform != PLATFORM_IG:
            raise InstagramRouteError(
                "bad_input: %s (capability %r on platform %r cannot stand in"
                " for an Instagram capability)"
                % (R_CAPABILITY_FB, self.name, self.platform))


@dataclass(frozen=True)
class OpenerState:
    """The durable state of one thread's comment private opener."""

    thread_key: str
    opener_action_id: Optional[str]
    sent_at: Optional[float]
    customer_responded_at: Optional[float]

    @property
    def opener_sent(self) -> bool:
        return self.opener_action_id is not None

    @property
    def customer_responded(self) -> bool:
        return self.customer_responded_at is not None


@dataclass(frozen=True)
class EligibilityVerdict:
    allowed: bool
    reason: str
    purpose: str
    channel: str
    route: str
    basis: str
    inbound_dm_window: bool
    refreshed_by: str
    evidence: Dict[str, Any] = field(default_factory=dict)

    @property
    def decision(self) -> str:
        return ALLOW if self.allowed else SUPPRESSED

    def as_gate_evidence(self) -> Dict[str, Any]:
        out = dict(self.evidence)
        out.update({
            "reason": self.reason,
            "purpose": self.purpose,
            "channel": self.channel,
            "route": self.route,
            "basis": self.basis,
            "inbound_dm_window": self.inbound_dm_window,
            "eligibility_refreshed_by": self.refreshed_by,
        })
        return out


def _route_for(purpose: str, channel: str) -> str:
    if channel == CHANNEL_IG_PUBLIC and purpose in PUBLIC_REPLY_PURPOSES:
        return ROUTE_COMMENT
    if channel == CHANNEL_IG_DM and purpose in DM_PURPOSES:
        return ROUTE_DIRECT if purpose != PURPOSE_COMMENT_PRIVATE_OPENER else ROUTE_COMMENT
    raise InstagramRouteError(
        "bad_input: %s (purpose %r is not a supported %s purpose)"
        % (R_CHANNEL_PURPOSE_MISMATCH, purpose, channel))


def evaluate_eligibility(
    *,
    account: InstagramAccount,
    purpose: str,
    channel: str,
    event: Optional[InstagramEvent] = None,
    filter_: Optional[InstagramCommentFilter] = None,
    capability: Optional[InstagramCapability] = None,
    opener: Optional[OpenerState] = None,
    basis: str = BASIS_INBOUND_MESSAGE,
    now: Optional[float] = None,
) -> EligibilityVerdict:
    """Compute Instagram eligibility from Instagram facts only.

    Called fresh on every dispatch. It has no cache and no default ALLOW.
    """
    if not isinstance(account, InstagramAccount):
        raise InstagramRouteError("bad_input: account must be InstagramAccount")
    ts = _ts(now)
    if basis not in ELIGIBILITY_BASES:
        raise InstagramRouteError(
            "bad_input: basis %r not in %s" % (basis, ELIGIBILITY_BASES))
    if basis in NON_REFRESHING_BASES:
        return _denied(R_BASIS_NOT_REFRESHING, purpose, channel,
                       BASIS_PLATFORM_ELIGIBILITY, now=ts,
                       detail={"offered_basis": basis})

    try:
        route = _route_for(purpose, channel)
    except InstagramRouteError as exc:
        return _denied(str(exc).replace("bad_input: ", ""), purpose, channel,
                       basis, now=ts,
                       detail={"purpose": purpose, "channel": channel})

    if channel not in IG_CHANNELS:
        return _denied("ig:unsupported_channel", purpose, channel, basis,
                       now=ts, detail={"channel": channel})

    if purpose in PUBLIC_REPLY_PURPOSES:
        return _comment_eligibility(
            account=account, purpose=purpose, channel=channel, route=route,
            event=event, filter_=filter_, opener=opener, now=ts,
            require_capability=None)

    if purpose == PURPOSE_COMMENT_PRIVATE_OPENER:
        if capability is None or capability.name != CAP_COMMENT_PRIVATE_OPENER:
            return _denied(R_CAPABILITY_MISSING, purpose, channel, basis,
                           now=ts,
                           detail={"required": CAP_COMMENT_PRIVATE_OPENER})
        if opener is not None and opener.opener_sent:
            return _denied(R_OPENER_ALREADY_SENT, purpose, channel, basis,
                           now=ts,
                           detail={"opener_action_id": opener.opener_action_id})
        return _comment_eligibility(
            account=account, purpose=purpose, channel=channel, route=route,
            event=event, filter_=filter_, opener=opener, now=ts,
            require_capability=None, inbound_dm_window=False)

    # Follow-up direct messages.
    if capability is None or capability.name != CAP_DM_SEND:
        return _denied(R_CAPABILITY_MISSING, purpose, channel, basis,
                       now=ts, detail={"required": CAP_DM_SEND})

    if opener is not None and opener.opener_sent and not opener.customer_responded:
        # The opener was ignored: no drip, no second attempt, no timer.
        return _denied(R_IGNORED_OPENER, purpose, channel, basis, now=ts,
                       detail={"opener_action_id": opener.opener_action_id,
                               "sent_at": opener.sent_at})

    inbound_dm = _has_inbound_dm(account, event)
    if not inbound_dm and not (opener is not None and opener.customer_responded):
        return _denied(R_NO_INBOUND_DM, purpose, channel, basis, now=ts)

    return EligibilityVerdict(
        allowed=True,
        reason="ig:inbound_dm_window",
        purpose=purpose,
        channel=channel,
        route=route,
        basis=BASIS_INBOUND_MESSAGE,
        inbound_dm_window=True,
        refreshed_by=BASIS_INBOUND_MESSAGE,
        evidence={
            "account_id": account.account_id,
            "binding_revision": account.binding_revision,
            "event_id": event.provider_event_id if event else None,
            "opener_action_id": opener.opener_action_id if opener else None,
            "checked_at": ts,
        },
    )


def _comment_eligibility(*, account: InstagramAccount, purpose: str,
                         channel: str, route: str,
                         event: Optional[InstagramEvent],
                         filter_: Optional[InstagramCommentFilter],
                         opener: Optional[OpenerState], now: float,
                         require_capability: Optional[str],
                         inbound_dm_window: bool = False) -> EligibilityVerdict:
    if event is None:
        return _denied(R_UNSUPPORTED_EVENT, purpose, channel,
                       BASIS_INBOUND_MESSAGE, now=now,
                       detail={"missing": "comment event"})
    if event.kind != EVENT_COMMENT:
        return _denied(R_EVENT_WRONG_KIND, purpose, channel,
                       BASIS_INBOUND_MESSAGE, now=now,
                       detail={"kind": event.kind})
    if event.direction != DIRECTION_INBOUND:
        return _denied(R_EVENT_WRONG_KIND, purpose, channel,
                       BASIS_INBOUND_MESSAGE, now=now,
                       detail={"direction": event.direction})
    if event.account_id != account.account_id:
        return _denied(R_EVENT_ACCOUNT_MISMATCH, purpose, channel,
                       BASIS_INBOUND_MESSAGE, now=now,
                       detail={"event_account_id": event.account_id})
    if event.tenant_id != account.tenant_id:
        return _denied(R_EVENT_ACCOUNT_MISMATCH, purpose, channel,
                       BASIS_INBOUND_MESSAGE, now=now,
                       detail={"event_tenant_id": event.tenant_id})
    if filter_ is None:
        return _denied(R_FILTER_NOT_MATCHED, purpose, channel,
                       BASIS_INBOUND_MESSAGE, now=now,
                       detail={"missing": "comment filter"})
    if filter_.account_id != account.account_id:
        return _denied(R_FILTER_ACCOUNT_MISMATCH, purpose, channel,
                       BASIS_INBOUND_MESSAGE, now=now,
                       detail={"filter_account_id": filter_.account_id})
    if not match_filter(filter_, event.text, account_id=account.account_id):
        return _denied(R_FILTER_NOT_MATCHED, purpose, channel,
                       BASIS_INBOUND_MESSAGE, now=now,
                       detail={"filter_id": filter_.filter_id,
                               "filter_revision": filter_.revision})
    return EligibilityVerdict(
        allowed=True,
        reason="ig:comment_route_eligible",
        purpose=purpose,
        channel=channel,
        route=route,
        basis=BASIS_INBOUND_MESSAGE,
        inbound_dm_window=inbound_dm_window,
        refreshed_by=BASIS_INBOUND_MESSAGE,
        evidence={
            "account_id": account.account_id,
            "binding_revision": account.binding_revision,
            "event_id": event.provider_event_id,
            "thread_key": event.thread_key,
            "comment_id": event.comment_id,
            "filter_id": filter_.filter_id,
            "filter_revision": filter_.revision,
            "opener_action_id": opener.opener_action_id if opener else None,
            "checked_at": now,
        },
    )


def _has_inbound_dm(account: InstagramAccount,
                    event: Optional[InstagramEvent]) -> bool:
    return bool(
        event is not None
        and event.kind == EVENT_DIRECT
        and event.direction == DIRECTION_INBOUND
        and event.account_id == account.account_id
        and event.tenant_id == account.tenant_id
    )


def _denied(reason: str, purpose: str, channel: str, basis: str, *,
            now: float, detail: Optional[Dict[str, Any]] = None) -> EligibilityVerdict:
    evidence = {"checked_at": now}
    if detail:
        evidence.update(detail)
    return EligibilityVerdict(
        allowed=False,
        reason=reason,
        purpose=purpose,
        channel=channel,
        route=ROUTE_COMMENT if channel == CHANNEL_IG_PUBLIC else ROUTE_DIRECT,
        basis=basis,
        inbound_dm_window=False,
        refreshed_by=basis,
        evidence=evidence,
    )


# ── durable route state (openers and customer interactions) ────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ig_openers (
    tenant_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    thread_key TEXT NOT NULL,
    opener_action_id TEXT NOT NULL,
    comment_id TEXT,
    sent_at REAL NOT NULL,
    customer_responded_at REAL,
    PRIMARY KEY (tenant_id, account_id, thread_key)
);
CREATE TABLE IF NOT EXISTS ig_customer_interactions (
    tenant_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    thread_key TEXT NOT NULL,
    provider_event_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    received_at REAL NOT NULL,
    PRIMARY KEY (tenant_id, account_id, provider_event_id)
);
"""


class InstagramRouteStore:
    """Durable Instagram route state beside the shared outbox.

    Own tables, additive: the same SQLite file as durable_store may be used.
    This is route state, not a send guard; outbound_gate still decides sends.
    """

    def __init__(self, path: str) -> None:
        self.path = str(path)
        self._db = sqlite3.connect(self.path, timeout=30.0,
                                   isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA busy_timeout=30000")
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.executescript(_SCHEMA)

    def close(self) -> None:
        self._db.close()

    def record_opener(self, *, tenant_id: str, account_id: str,
                      thread_key: str, opener_action_id: str,
                      comment_id: Optional[str] = None,
                      now: Optional[float] = None) -> Tuple[Dict[str, Any], bool]:
        """Record the ONE private opener for a thread. Idempotent.

        A second opener for the same thread returns the existing row with
        created=False. The opener is never replaced by a newer action id.
        """
        for name, value in (("tenant_id", tenant_id),
                            ("account_id", account_id),
                            ("thread_key", thread_key),
                            ("opener_action_id", opener_action_id)):
            _id(value, name)
        ts = _ts(now)
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._db.execute(
                "SELECT * FROM ig_openers WHERE tenant_id=? AND account_id=?"
                " AND thread_key=?", (tenant_id, account_id, thread_key)
            ).fetchone()
            if row is not None:
                self._db.execute("COMMIT")
                return dict(row), False
            self._db.execute(
                "INSERT INTO ig_openers (tenant_id, account_id, thread_key,"
                " opener_action_id, comment_id, sent_at, customer_responded_at)"
                " VALUES (?,?,?,?,?,?,NULL)",
                (tenant_id, account_id, thread_key, opener_action_id,
                 comment_id, ts),
            )
            self._db.execute("COMMIT")
        except Exception:
            self._db.execute("ROLLBACK")
            raise
        return self.opener_state(tenant_id, account_id, thread_key), True

    def record_customer_interaction(self, *, tenant_id: str, account_id: str,
                                    thread_key: str, provider_event_id: str,
                                    kind: str = EVENT_DIRECT,
                                    now: Optional[float] = None) -> bool:
        """Record a verified inbound customer interaction for a thread.

        Deduped by provider event id. Returns True only for the first record.
        This is the only thing that ends the ignored-opener state.
        """
        for name, value in (("tenant_id", tenant_id),
                            ("account_id", account_id),
                            ("thread_key", thread_key),
                            ("provider_event_id", provider_event_id)):
            _id(value, name)
        if kind not in EVENT_KINDS:
            raise InstagramRouteError(
                "bad_input: %s (interaction kind %r not in %s)"
                % (R_UNSUPPORTED_EVENT, kind, EVENT_KINDS))
        ts = _ts(now)
        self._db.execute("BEGIN IMMEDIATE")
        try:
            cur = self._db.execute(
                "INSERT OR IGNORE INTO ig_customer_interactions"
                " (tenant_id, account_id, thread_key, provider_event_id,"
                " kind, received_at) VALUES (?,?,?,?,?,?)",
                (tenant_id, account_id, thread_key, provider_event_id, kind, ts),
            )
            created = cur.rowcount == 1
            if created:
                self._db.execute(
                    "UPDATE ig_openers SET customer_responded_at=?"
                    " WHERE tenant_id=? AND account_id=? AND thread_key=?"
                    " AND customer_responded_at IS NULL",
                    (ts, tenant_id, account_id, thread_key),
                )
            self._db.execute("COMMIT")
        except Exception:
            self._db.execute("ROLLBACK")
            raise
        return created

    def opener_state(self, tenant_id: str, account_id: str,
                     thread_key: str) -> Optional[OpenerState]:
        row = self._db.execute(
            "SELECT * FROM ig_openers WHERE tenant_id=? AND account_id=?"
            " AND thread_key=?", (tenant_id, account_id, thread_key)
        ).fetchone()
        if row is None:
            return None
        return OpenerState(
            thread_key=row["thread_key"],
            opener_action_id=row["opener_action_id"],
            sent_at=row["sent_at"],
            customer_responded_at=row["customer_responded_at"],
        )


# ── fresh gate evaluator and dispatch (reuses outbound_gate) ───────────────

def make_gate_evaluator(
    *,
    account: InstagramAccount,
    route_store: InstagramRouteStore,
    purpose: str,
    channel: str,
    thread_key: str,
    event: Optional[InstagramEvent] = None,
    filter_: Optional[InstagramCommentFilter] = None,
    capability: Optional[InstagramCapability] = None,
    consent_evaluator: Optional[Any] = None,
    now_fn: Any = None,
):
    """Build the outbound_gate evaluator for one Instagram action.

    The evaluator reads durable opener state on every call, so a customer
    reply or an ignored opener changes the answer without a restart. It never
    caches a verdict and never returns ALLOW by default.
    """
    if not isinstance(account, InstagramAccount):
        raise InstagramRouteError("bad_input: account must be InstagramAccount")
    if not isinstance(route_store, InstagramRouteStore):
        raise InstagramRouteError("bad_input: route_store must be InstagramRouteStore")
    _id(thread_key, "thread_key")
    _route_for(purpose, channel)  # fail loudly on an unsupported pairing
    clock = now_fn or time.time

    def evaluator(ctx: Dict[str, Any]) -> Dict[str, Any]:
        ts = float(ctx.get("now") if ctx.get("now") is not None else clock())
        action = ctx.get("action") or {}
        bound = action.get("binding_revision")
        if bound is not None and bound != account.binding_revision:
            # A changed account binding quarantines queued work; never reroute.
            return {
                "verdict": QUARANTINED,
                "checked_at": ts,
                "binding_revision": bound,
                "evidence": {"reason": R_ACCOUNT_BINDING,
                             "action_binding_revision": bound,
                             "current_binding_revision": account.binding_revision},
            }
        if consent_evaluator is not None:
            consent = consent_evaluator(dict(ctx, channel=channel))
            if consent.get("verdict") != ALLOW:
                return consent
        opener = route_store.opener_state(
            account.tenant_id, account.account_id, thread_key)
        verdict = evaluate_eligibility(
            account=account, purpose=purpose, channel=channel, event=event,
            filter_=filter_, capability=capability, opener=opener, now=ts)
        return {
            "verdict": verdict.decision,
            "checked_at": ts,
            "binding_revision": account.binding_revision,
            "evidence": verdict.as_gate_evidence(),
        }

    return evaluator


def dispatch_instagram_action(
    store: Any,
    *,
    account: InstagramAccount,
    route_store: InstagramRouteStore,
    action_id: str,
    worker_id: str,
    purpose: str,
    channel: str,
    thread_key: str,
    sender: Any,
    event: Optional[InstagramEvent] = None,
    filter_: Optional[InstagramCommentFilter] = None,
    capability: Optional[InstagramCapability] = None,
    consent_evaluator: Optional[Any] = None,
    context: Optional[Dict[str, Any]] = None,
    now: Optional[float] = None,
    lease_seconds: Optional[float] = None,
) -> Any:
    """Send one Instagram action through the common fresh gate.

    The only dispatcher is outbound_gate.dispatch(). A recorded opener is
    written only after the provider accepted the send, so a blocked or
    failed attempt never creates ignored-opener state.
    """
    outbound_gate = _upstream("outbound_gate")
    evaluator = make_gate_evaluator(
        account=account, route_store=route_store, purpose=purpose,
        channel=channel, thread_key=thread_key, event=event, filter_=filter_,
        capability=capability, consent_evaluator=consent_evaluator)
    kwargs: Dict[str, Any] = {
        "now": now,
        "context": dict(context or {}, channel=channel,
                        ig_purpose=purpose, ig_thread_key=thread_key),
    }
    if lease_seconds is not None:
        kwargs["lease_seconds"] = lease_seconds
    outcome = outbound_gate.dispatch(
        store, evaluator, sender, action_id, worker_id, **kwargs)
    if outcome.status == outbound_gate.ST_SENT and purpose == PURPOSE_COMMENT_PRIVATE_OPENER:
        route_store.record_opener(
            tenant_id=account.tenant_id, account_id=account.account_id,
            thread_key=thread_key, opener_action_id=action_id,
            comment_id=event.comment_id if event else None,
            now=now)
    return outcome


# ── upstream module resolution ─────────────────────────────────────────────

_UPSTREAM_CACHE: Dict[str, Any] = {}


def _upstream(name: str) -> Any:
    """Import an accepted upstream module from 38-conversational-ai-system.

    There is exactly one copy of the durable store, the send gate and the
    consent gate. This adapter never re-implements them.
    """
    if name in _UPSTREAM_CACHE:
        return _UPSTREAM_CACHE[name]
    here = Path(__file__).resolve()
    candidates = []
    for parent in here.parents:
        candidates.append(parent / "38-conversational-ai-system" / "tools")
    for tools in candidates:
        if (tools / (name + ".py")).is_file():
            if str(tools) not in sys.path:
                sys.path.insert(0, str(tools))
            module = __import__(name)
            _UPSTREAM_CACHE[name] = module
            return module
    raise InstagramRouteError(
        "missing_upstream: %s.py was not found in 38-conversational-ai-system/tools;"
        " refusing to invent a second guard" % name)


# ── assert-based self-check (stdlib only, no network) ──────────────────────

def _selfcheck() -> int:
    import tempfile

    passed = 0

    def ok(cond: bool, label: str) -> None:
        nonlocal passed
        if not cond:
            raise AssertionError("FAIL: " + label)
        passed += 1

    account = InstagramAccount(
        tenant_id="t1", account_id="ig-acct-1", ig_user_id="17841400000000001",
        binding_revision="bind-1")
    filter_ = InstagramCommentFilter(
        filter_id="f1", account_id="ig-acct-1", revision="frev-1",
        keywords=("billboard",), match_mode=FILTER_CONTAINS)

    # separate account: a Facebook identity never resolves one.
    try:
        resolve_account([account], fb_page_id="1234")
        ok(False, "fb page id refused")
    except InstagramRouteError as exc:
        ok(R_ACCOUNT_FB in str(exc), "fb page id refused")

    # separate filter: foreign platform and foreign account match nothing.
    try:
        InstagramCommentFilter(filter_id="x", account_id="a", revision="r",
                               keywords=("k",), platform="FB")
        ok(False, "fb filter refused")
    except InstagramRouteError as exc:
        ok(R_ACCOUNT_FB in str(exc), "fb filter refused")
    ok(not match_filter(filter_, "billboard", account_id="other"),
       "foreign-account filter does not match")

    # separate event: Page comment shape is not an Instagram route.
    try:
        normalise_event({"provider": "facebook", "provider_event_id": "e",
                         "tenant_id": "t1", "account_id": "ig-acct-1",
                         "kind": "PAGE_COMMENT", "direction": "inbound",
                         "actor_id": "u", "text": "billboard",
                         "thread_key": "c1", "received_at": 1})
        ok(False, "fb event refused")
    except InstagramRouteError as exc:
        ok(R_UNSUPPORTED_EVENT in str(exc), "fb event refused")

    # separate eligibility: comment alone is not an inbound DM window.
    event = normalise_event({
        "provider": "instagram", "provider_event_id": "e1", "tenant_id": "t1",
        "account_id": "ig-acct-1", "kind": "COMMENT",
        "direction": "inbound", "actor_id": "customer-1", "text": "billboard",
        "thread_key": "c1", "comment_id": "c1", "received_at": 10})
    v_public = evaluate_eligibility(
        account=account, purpose=PURPOSE_PUBLIC_REPLY,
        channel=CHANNEL_IG_PUBLIC, event=event, filter_=filter_)
    ok(v_public.allowed and v_public.inbound_dm_window is False,
       "public reply allowed without a DM window")
    v_open = evaluate_eligibility(
        account=account, purpose=PURPOSE_COMMENT_PRIVATE_OPENER,
        channel=CHANNEL_IG_DM, event=event, filter_=filter_,
        capability=InstagramCapability(CAP_COMMENT_PRIVATE_OPENER))
    ok(v_open.allowed and v_open.inbound_dm_window is False,
       "opener allowed, comment is not a DM window")
    v_fb_basis = evaluate_eligibility(
        account=account, purpose=PURPOSE_AI_REPLY, channel=CHANNEL_IG_DM,
        event=event, capability=InstagramCapability(CAP_DM_SEND),
        basis=BASIS_OUTBOUND_MESSAGE)
    ok(not v_fb_basis.allowed and v_fb_basis.reason == R_BASIS_NOT_REFRESHING,
       "outbound basis never refreshes eligibility")

    # ignored opener: no drip until a verified customer interaction.
    route_path = Path(tempfile.mkdtemp(prefix="ig-route-selfcheck-")) / "r.sqlite"
    route_store = InstagramRouteStore(str(route_path))
    route_store.record_opener(tenant_id="t1", account_id="ig-acct-1",
                              thread_key="th1", opener_action_id="act-1",
                              comment_id="c1", now=20)
    state = route_store.opener_state("t1", "ig-acct-1", "th1")
    drip = evaluate_eligibility(
        account=account, purpose=PURPOSE_CAPTURE_REMINDER,
        channel=CHANNEL_IG_DM, opener=state,
        capability=InstagramCapability(CAP_DM_SEND), now=30)
    ok(not drip.allowed and drip.reason == R_IGNORED_OPENER,
       "ignored opener blocks every follow-up")
    route_store.record_customer_interaction(
        tenant_id="t1", account_id="ig-acct-1", thread_key="th1",
        provider_event_id="dm-1", now=40)
    state = route_store.opener_state("t1", "ig-acct-1", "th1")
    ok(state.opener_sent and state.customer_responded,
       "customer interaction ends the ignored state")
    second_opener = route_store.record_opener(
        tenant_id="t1", account_id="ig-acct-1", thread_key="th1",
        opener_action_id="act-2", now=50)
    ok(second_opener[1] is False and second_opener[0]["opener_action_id"] == "act-1",
       "a thread never gets a second opener")
    route_store.close()

    print("OK %d PASS" % passed)
    return 0


if __name__ == "__main__":
    sys.exit(_selfcheck())
