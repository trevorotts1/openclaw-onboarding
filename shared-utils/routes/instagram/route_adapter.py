#!/usr/bin/env python3
"""route_adapter.py - the supported Instagram comment and direct routes.

Contract basis: Purple-Billboard DATA-CONTRACTS.md sections 2-4 and SPEC.md
lines 21 and 26. Python 3 standard library only; no network; no model.

What this module exists to guarantee (task T-21 acceptance):

SEPARATE ACCOUNT.  An Instagram account is its own record: tenant_id,
account_id, ig_user_id and binding_revision. A Facebook page id never
resolves an Instagram account and never satisfies an Instagram binding.
When both Instagram identity keys are supplied they must name the same
binding; a disagreeing pair is refused, never silently narrowed to one key.
A changed binding quarantines queued work; it is never rerouted silently.

SEPARATE FILTER.  Comment filters are Instagram-scoped and account-scoped.
A filter bound to another account or declared for Facebook matches nothing
here, and own reveal/outgoing events are excluded by verified actor.

SEPARATE EVENT.  Only the two supported routes are normalised: an inbound
Instagram COMMENT and an inbound Instagram DIRECT message. Facebook Page
comments, Messenger events and unknown kinds are refused, not adapted.

SEPARATE ELIGIBILITY.  Instagram eligibility is computed from Instagram
facts only. Each route carries its own basis AND its own granted Instagram
capability: a public comment reply needs IG_PUBLIC_REPLY, a comment private
opener needs IG_COMMENT_PRIVATE_OPENER, a DM needs IG_DM_SEND, and a
capability whose `granted` flag is False is no permission at all. A comment
alone is NOT a normal inbound-DM window (`inbound_dm_window` is False). A
direct message needs an actual inbound customer DM, and the DM window opens
only on a row the DURABLE INBOX holds for that event: an event object on its
own is never proof, at dispatch or at record. Outbound and cross-channel
messages never refresh Instagram eligibility, and an eligibility basis
carried over from Facebook is refused.

IGNORED OPENER, NO DRIP.  Once a private opener is recorded for a thread,
every follow-up direct message is suppressed until the customer actually
interacts: a verified inbound DM on that thread, proven by the event AND by
the durable inbox row this module re-reads for it -- never by a dict a caller
hands over. There is no timed drip at any age. There is at most one opener
per (tenant, account, thread) FOR THE LIFE OF THE OPENER CLAIM: the claim is
taken before dispatch and released after it, its lease is
DEFAULT_OPENER_CLAIM_S (300 s) by default, and a worker that stalls inside
the provider call past that lease may be taken over and a second opener may
then be sent. "No second opener" is therefore a claim about that window, not
an unconditional invariant; the bound is stated in the same sentence because
a probe can falsify the unqualified one. The state is durable, so a restart
changes nothing. The mutual exclusion itself is an atomic claim in the
durable store BEFORE dispatch, not the eligibility read alone: four workers
racing the same thread inside the claim window produce one send, not four.

OWNERSHIP.  "Our own actor" is derived from the authoritative account record
(its `ig_user_id`), never from a hand-kept id list a caller might forget. A
caller may add further ids; it can never subtract the account's own. The
supplementary ids are a list, tuple, set or frozenset of actor ids and
NOTHING ELSE: a bare string is not a list of letters, a mapping's KEYS are
never read as ids (so a caller cannot make a real customer look like our own
actor), and every other value is a domain refusal, never a raw TypeError out
of this boundary.

BASIS HONESTY.  A verdict reports the eligibility basis the CALLER supplied.
It never substitutes a basis the caller did not offer.

STOP AND HUMAN OWNER.  The upstream consent gate (consent_gate) decides every
Instagram dispatch first: a global stop or a human taking the conversation
suppresses these routes exactly as it does every other one. This adapter
never decides consent and never sends without that gate's answer.

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
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

SCHEMA_VERSION = 2  # v2 adds ig_opener_claims (the opener mutual exclusion)

# How long one worker's opener claim survives before another worker may take
# the thread over. A crashed worker must not wedge a thread forever, and a
# live worker's claim must outlast one provider call.
DEFAULT_OPENER_CLAIM_S = 300.0

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
R_ACCOUNT_IDENTITY_CONFLICT = "ig:account_identity_conflict"
R_UNKNOWN_ROUTE = "ig:unsupported_route"
R_UNSUPPORTED_EVENT = "ig:unsupported_event"
R_EVENT_ACCOUNT_MISMATCH = "ig:event_account_mismatch"
R_EVENT_WRONG_KIND = "ig:event_wrong_kind"
R_FILTER_ACCOUNT_MISMATCH = "ig:filter_account_mismatch"
R_FILTER_NOT_MATCHED = "ig:comment_filter_not_matched"
R_CAPABILITY_MISSING = "ig:capability_missing"
R_CAPABILITY_NOT_GRANTED = "ig:capability_not_granted"
R_CAPABILITY_FB = "ig:no_inferred_fb_parity"
R_CONSENT_GATE_REQUIRED = "ig:consent_gate_required"
R_UNVERIFIED_INTERACTION = "ig:unverified_inbound_interaction"
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
    """A timestamp, or now. Anything else is a domain error, never float().

    Provider payloads are untrusted: `float("abc")` raises a raw ValueError
    and `float([])` a raw TypeError. Both would escape this adapter's own
    error class at the provider trust boundary.
    """
    if value is None:
        return time.time()
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InstagramRouteError(
            "bad_input: timestamp must be a number, not %r" % (value,))
    return float(value)


def _revision(value: Any, name: str) -> str:
    return _id(value, name)


def _extra_own_actor_ids(value: Any) -> Tuple[str, ...]:
    """Validate caller-SUPPLIED extra own-actor ids (never the whole set).

    This is only the supplementary collection: the authoritative own actor is
    the bound account's own `ig_user_id`, added in `_own_actor_set`.

    One rule closes the whole input CLASS, not the examples that happened to
    be named:

    * a bare `str`/`bytes`/`bytearray` is iterated as its characters, so the
      exclusion set would hold single letters and our own actor would pass as
      a customer;
    * a MAPPING is iterated as its KEYS, so `{"customer-7": "x"}` would put a
      real customer in the own-actor set and exclude them as one of us;
    * any other non-collection (`3`, `None`, `1.5`, a stream, an object) is
      iterated or not at all and used to raise a RAW `TypeError`, which is not
      this boundary's contract;
    * a member that is not a non-empty string is refused rather than coerced,
      because `str(3)` turns a number into an actor id.

    So the only accepted shapes are list, tuple, set and frozenset of
    non-empty strings. Everything else is `InstagramRouteError("bad_input: ...")`.
    """
    if value is None:
        raise InstagramRouteError(
            "bad_input: own_actor_ids must be a collection of actor ids,"
            " not None")
    if isinstance(value, (str, bytes, bytearray)):
        raise InstagramRouteError(
            "bad_input: own_actor_ids must be a collection of actor ids,"
            " not one bare value")
    if not isinstance(value, (list, tuple, set, frozenset)):
        # dict, int, float, object(), generators, ... -- a mapping's keys are
        # never the own-actor set, and nothing else may leak a raw TypeError.
        raise InstagramRouteError(
            "bad_input: own_actor_ids must be a list, tuple, set or frozenset"
            " of actor ids, not %s" % type(value).__name__)
    out: List[str] = []
    for actor in value:
        out.append(_id(actor, "own_actor_ids[]"))
    return tuple(out)


def _own_actor_set(account: "InstagramAccount",
                   extra_own_actor_ids: Any = ()) -> frozenset:
    """The set of OUR OWN actor ids, derived from the authoritative record.

    The bound account's own `ig_user_id` is the account record's statement of
    who we are on Instagram. It is always in the set, so a caller cannot
    forget it, cannot omit it, and cannot hand over a stale hand-kept list and
    thereby admit our own outbound activity as a customer's. `own_actor_ids`
    only ADDS further ids (for accounts behind a shared inbox); it can never
    remove the authoritative one.
    """
    if not isinstance(account, InstagramAccount):
        raise InstagramRouteError("bad_input: account must be InstagramAccount")
    extra = _extra_own_actor_ids(extra_own_actor_ids)
    return frozenset((account.ig_user_id,) + extra)


def _assert_event_matches_account(account: "InstagramAccount",
                                  event: Any) -> None:
    """An event may only ever be judged against ITS OWN account record."""
    if not isinstance(event, InstagramEvent):
        raise InstagramRouteError("bad_input: event must be InstagramEvent")
    if event.tenant_id != account.tenant_id or event.account_id != account.account_id:
        raise InstagramRouteError(
            "bad_input: %s (event %r/%r is not account %r/%r)"
            % (R_EVENT_ACCOUNT_MISMATCH, event.tenant_id, event.account_id,
               account.tenant_id, account.account_id))


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
    accepting it would infer parity from a Facebook identity. When both
    Instagram keys are supplied they must name the SAME binding; a pair that
    disagrees is refused, never silently narrowed to whichever key matched.
    """
    if fb_page_id is not None:
        raise InstagramRouteError(
            "bad_input: %s (facebook page %r cannot resolve an Instagram"
            " account)" % (R_ACCOUNT_FB, fb_page_id))
    if account_id is None and ig_user_id is None:
        raise InstagramRouteError(
            "bad_input: account_id or ig_user_id is required")
    rows: List[InstagramAccount] = []
    for account in accounts:
        if not isinstance(account, InstagramAccount):
            raise InstagramRouteError("bad_input: accounts must be InstagramAccount")
        rows.append(account)
    if account_id is not None and ig_user_id is not None:
        for account in rows:
            if account.account_id == account_id and account.ig_user_id != ig_user_id:
                raise InstagramRouteError(
                    "bad_input: %s (account_id %r is bound to ig_user_id %r,"
                    " not %r)" % (R_ACCOUNT_IDENTITY_CONFLICT, account_id,
                                  account.ig_user_id, ig_user_id))
            if account.ig_user_id == ig_user_id and account.account_id != account_id:
                raise InstagramRouteError(
                    "bad_input: %s (ig_user_id %r is bound to account_id %r,"
                    " not %r)" % (R_ACCOUNT_IDENTITY_CONFLICT, ig_user_id,
                                  account.account_id, account_id))
    matches = [account for account in rows
               if (account_id is None or account.account_id == account_id)
               and (ig_user_id is None or account.ig_user_id == ig_user_id)]
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

    This is a trust boundary: the payload comes from the provider. Every
    malformed shape leaves as InstagramRouteError, never as a raw KeyError,
    TypeError, AttributeError or ValueError, so a caller that catches this
    adapter's own error class cannot be surprised by an unclassified one.
    """
    if not isinstance(raw, dict):
        raise InstagramRouteError("bad_input: event must be a dict")
    try:
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
    except InstagramRouteError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        # `sorted()` on mixed-typed keys, a payload object that lies about
        # being a mapping, and anything else the provider shape can do to
        # Python. Still this adapter's error, still a refusal, never adapted.
        raise InstagramRouteError(
            "bad_input: %s (malformed provider payload: %s: %s)"
            % (R_UNSUPPORTED_EVENT, type(exc).__name__, exc)) from None


def admit_instagram_event(store: Any, event: InstagramEvent, *,
                          account: InstagramAccount,
                          own_actor_ids: Any = (),
                          now: Optional[float] = None) -> Dict[str, Any]:
    """Persist the event identity before any ACK, via durable_store.

    Returns durable_store.admit_event()'s dict. A duplicate event is not
    admitted twice; an outgoing event or one of our own actors is excluded,
    never decided on.

    `account` is REQUIRED and is the authoritative ownership record: our own
    `ig_user_id` comes from it, so no caller can forget to exclude us.
    `own_actor_ids` only adds further ids.
    """
    _assert_event_matches_account(account, event)
    own_actor_ids = _own_actor_set(account, own_actor_ids)
    _upstream("durable_store")
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
        if not isinstance(self.granted, bool):
            # "false" is truthy: only a real bool may grant or withhold.
            raise InstagramRouteError(
                "bad_input: granted must be a bool, not %r" % (self.granted,))
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
    inbox: Any = None,
    own_actor_ids: Any = (),
    now: Optional[float] = None,
) -> EligibilityVerdict:
    """Compute Instagram eligibility from Instagram facts only.

    Called fresh on every dispatch. It has no cache and no default ALLOW.

    `inbox` is the durable store that owns `inbox_events`. It is what proves a
    customer's inbound DM; without it the inbound-DM window is closed, because
    an event object alone is a claim, not evidence.
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
        denied = _capability_denied(capability, CAP_COMMENT_PUBLIC_REPLY,
                                    purpose, channel, basis, now=ts)
        if denied is not None:
            return denied
        return _comment_eligibility(
            account=account, purpose=purpose, channel=channel, route=route,
            event=event, filter_=filter_, opener=opener, basis=basis, now=ts)

    if purpose == PURPOSE_COMMENT_PRIVATE_OPENER:
        denied = _capability_denied(capability, CAP_COMMENT_PRIVATE_OPENER,
                                    purpose, channel, basis, now=ts)
        if denied is not None:
            return denied
        if opener is not None and opener.opener_sent:
            return _denied(R_OPENER_ALREADY_SENT, purpose, channel, basis,
                           now=ts,
                           detail={"opener_action_id": opener.opener_action_id})
        return _comment_eligibility(
            account=account, purpose=purpose, channel=channel, route=route,
            event=event, filter_=filter_, opener=opener, basis=basis, now=ts,
            inbound_dm_window=False)

    # Follow-up direct messages.
    denied = _capability_denied(capability, CAP_DM_SEND, purpose, channel,
                                basis, now=ts)
    if denied is not None:
        return denied

    if opener is not None and opener.opener_sent and not opener.customer_responded:
        # The opener was ignored: no drip, no second attempt, no timer.
        return _denied(R_IGNORED_OPENER, purpose, channel, basis, now=ts,
                       detail={"opener_action_id": opener.opener_action_id,
                               "sent_at": opener.sent_at})

    inbound_dm = _has_inbound_dm(account, event, inbox, own_actor_ids)
    if not inbound_dm and not (opener is not None and opener.customer_responded):
        return _denied(R_NO_INBOUND_DM, purpose, channel, basis, now=ts)

    return EligibilityVerdict(
        allowed=True,
        reason="ig:inbound_dm_window",
        purpose=purpose,
        channel=channel,
        route=route,
        basis=basis,
        inbound_dm_window=True,
        refreshed_by=basis,
        evidence={
            "account_id": account.account_id,
            "binding_revision": account.binding_revision,
            "event_id": event.provider_event_id if event else None,
            "opener_action_id": opener.opener_action_id if opener else None,
            "checked_at": ts,
        },
    )


def _capability_denied(capability: Optional[InstagramCapability],
                       required: str, purpose: str, channel: str, basis: str,
                       *, now: float) -> Optional[EligibilityVerdict]:
    """The refusal when the ONE Instagram capability this route needs is off.

    A capability is its name AND its grant: an ungranted capability is not a
    lesser permission, it is no permission. Returns None when it is granted.
    """
    if (not isinstance(capability, InstagramCapability)
            or capability.name != required):
        return _denied(R_CAPABILITY_MISSING, purpose, channel, basis, now=now,
                       detail={"required": required})
    if not capability.granted:
        return _denied(R_CAPABILITY_NOT_GRANTED, purpose, channel, basis,
                       now=now, detail={"required": required,
                                        "granted": False})
    return None


def _comment_eligibility(*, account: InstagramAccount, purpose: str,
                         channel: str, route: str,
                         event: Optional[InstagramEvent],
                         filter_: Optional[InstagramCommentFilter],
                         opener: Optional[OpenerState], basis: str, now: float,
                         inbound_dm_window: bool = False) -> EligibilityVerdict:
    """The comment route's verdict. `basis` is the caller's OWN offered basis.

    It is carried through unchanged on every path, so the gate record never
    asserts a basis the caller did not offer.
    """
    if event is None:
        return _denied(R_UNSUPPORTED_EVENT, purpose, channel, basis, now=now,
                       detail={"missing": "comment event"})
    if event.kind != EVENT_COMMENT:
        return _denied(R_EVENT_WRONG_KIND, purpose, channel, basis, now=now,
                       detail={"kind": event.kind})
    if event.direction != DIRECTION_INBOUND:
        return _denied(R_EVENT_WRONG_KIND, purpose, channel, basis, now=now,
                       detail={"direction": event.direction})
    if event.account_id != account.account_id:
        return _denied(R_EVENT_ACCOUNT_MISMATCH, purpose, channel, basis,
                       now=now,
                       detail={"event_account_id": event.account_id})
    if event.tenant_id != account.tenant_id:
        return _denied(R_EVENT_ACCOUNT_MISMATCH, purpose, channel, basis,
                       now=now,
                       detail={"event_tenant_id": event.tenant_id})
    if filter_ is None:
        return _denied(R_FILTER_NOT_MATCHED, purpose, channel, basis, now=now,
                       detail={"missing": "comment filter"})
    if filter_.account_id != account.account_id:
        return _denied(R_FILTER_ACCOUNT_MISMATCH, purpose, channel, basis,
                       now=now,
                       detail={"filter_account_id": filter_.account_id})
    if not match_filter(filter_, event.text, account_id=account.account_id):
        return _denied(R_FILTER_NOT_MATCHED, purpose, channel, basis, now=now,
                       detail={"filter_id": filter_.filter_id,
                               "filter_revision": filter_.revision})
    return EligibilityVerdict(
        allowed=True,
        reason="ig:comment_route_eligible",
        purpose=purpose,
        channel=channel,
        route=route,
        basis=basis,
        inbound_dm_window=inbound_dm_window,
        refreshed_by=basis,
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


def _durable_inbox_row(inbox: Any,
                       event: InstagramEvent) -> Optional[Dict[str, Any]]:
    """RE-READ this event's row from the durable inbox. None when it is not there.

    The inbox is the ONLY authority for "this event exists and was admitted".
    A dict a caller hands over is never consulted here, so a hand-written
    `admission` cannot conjure a row that `inbox_events` does not hold.

    A missing store answers None (fail closed); a store that cannot answer an
    inbox query at all is a domain error, not a silent pass.
    """
    if inbox is None:
        return None
    read = getattr(inbox, "inbox_row", None)
    if not callable(read):
        raise InstagramRouteError(
            "bad_input: %s (inbox must be the durable store that owns"
            " inbox_events, not %r)" % (R_UNVERIFIED_INTERACTION,
                                        type(inbox).__name__))
    try:
        row = read(provider=PROVIDER_IG, tenant_id=event.tenant_id,
                   provider_event_id=event.provider_event_id)
    except ValueError:
        # durable_store.DurableStoreError("unknown inbox event"): the inbox
        # has never seen this event id. That is an absent row, not a crash.
        return None
    return dict(row) if isinstance(row, dict) else None


def _durable_row_proves_customer(account: InstagramAccount,
                                 event: InstagramEvent, inbox: Any,
                                 own_actor_ids: Any = ()) -> bool:
    """True only when the durable inbox holds a customer's inbound row for it.

    The row must be there, inbound, not excluded by the inbox, and not one of
    our own actors (the account's authoritative `ig_user_id` plus whatever the
    caller adds). Without a store there is no proof, so this is False: an
    event object alone never opens the inbound-DM window.
    """
    row = _durable_inbox_row(inbox, event)
    if row is None:
        return False
    if row.get("provider_event_id") != event.provider_event_id:
        return False
    if row.get("tenant_id") != event.tenant_id:
        return False
    if row.get("direction") != DIRECTION_INBOUND:
        return False
    if str(row.get("decision_ref") or "").startswith("excluded:"):
        return False
    own = _own_actor_set(account, own_actor_ids)
    if row.get("actor_id") is not None and row.get("actor_id") in own:
        return False
    return True


def _has_inbound_dm(account: InstagramAccount,
                    event: Optional[InstagramEvent],
                    inbox: Any = None,
                    own_actor_ids: Any = ()) -> bool:
    """An inbound customer DM window, proven against the durable inbox.

    Shape alone is not proof: an `InstagramEvent` says what a payload claimed,
    while `inbox_events` says what this system actually admitted. Both must
    agree, so an event the durable inbox never admitted is never proof here.
    """
    if not (event is not None
            and event.kind == EVENT_DIRECT
            and event.direction == DIRECTION_INBOUND
            and event.account_id == account.account_id
            and event.tenant_id == account.tenant_id):
        return False
    return _durable_row_proves_customer(account, event, inbox, own_actor_ids)


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


def _consent_verdict(consent_evaluator: Any, ctx: Dict[str, Any], *,
                     now: float,
                     binding_revision: Optional[str] = None
                     ) -> Optional[Dict[str, Any]]:
    """The upstream consent gate's suppression, or None when it says ALLOW.

    The global STOP and the human-ownership fence live upstream in
    consent_gate; this adapter never decides consent itself. It never sends
    without that answer either: no evaluator, or an answer that is not the
    gate's own ALLOW, fails closed to SUPPRESSED.
    """
    raw = consent_evaluator(ctx) if callable(consent_evaluator) else None
    if isinstance(raw, dict) and raw.get("verdict") == ALLOW:
        return None
    evidence = (dict(raw.get("evidence"))
                if isinstance(raw, dict) and isinstance(raw.get("evidence"), dict)
                else {})
    evidence.setdefault("reason", R_CONSENT_GATE_REQUIRED)
    return {"verdict": SUPPRESSED, "checked_at": now,
            "binding_revision": binding_revision, "evidence": evidence}


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
CREATE TABLE IF NOT EXISTS ig_opener_claims (
    tenant_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    thread_key TEXT NOT NULL,
    claim_token TEXT NOT NULL,
    action_id TEXT NOT NULL,
    acquired_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    released_at REAL,
    PRIMARY KEY (tenant_id, account_id, thread_key)
);
"""


def _verified_inbound_interaction(*, tenant_id: str, account_id: str,
                                  thread_key: str, provider_event_id: str,
                                  event: Optional[InstagramEvent],
                                  admission: Any,
                                  inbox: Any = None,
                                  own_actor_ids: Any = ()) -> InstagramEvent:
    """Return the event only when the DURABLE inbox proves it is a customer's.

    Proof is required, not caller convention -- and the proof is not the
    `admission` dict. `admission` is the answer admit_instagram_event() got
    from durable_store, and its SHAPE is checked below so a malformed one is
    refused with the reason that names it. But a shape is forgeable: a caller
    can write `{"admitted": True, "row": {...}}` by hand. So the LAST word is
    always the durable store itself, re-read here through `inbox`: unless
    `inbox_events` really holds a row for this very event that is inbound, not
    excluded and not one of our own actors, the record is refused.

    `own_actor_ids` is already the authoritative set: `_own_actor_set` derives
    our own `ig_user_id` from the account record, so the caller cannot leave
    us out.
    """
    def refuse(why: str) -> InstagramRouteError:
        return InstagramRouteError(
            "bad_input: %s (%s)" % (R_UNVERIFIED_INTERACTION, why))

    if not isinstance(event, InstagramEvent):
        raise refuse("an Instagram event plus its inbox admission is required")
    if (event.provider_event_id != provider_event_id
            or event.tenant_id != tenant_id or event.account_id != account_id
            or event.thread_key != thread_key):
        raise refuse("the event does not describe this interaction")
    if event.direction != DIRECTION_INBOUND:
        raise refuse("direction %r is not a customer's inbound message"
                     % event.direction)
    own = {str(actor) for actor in own_actor_ids}
    if event.actor_id in own:
        raise refuse("actor %r is one of our own" % event.actor_id)
    if not isinstance(admission, dict):
        raise refuse("no durable inbox admission was supplied")
    row = admission.get("row")
    if admission.get("reason") not in ("admitted", "duplicate"):
        raise refuse("the inbox did not admit this event: %r"
                     % admission.get("reason"))
    if not isinstance(row, dict):
        raise refuse("the inbox admission carries no event row")
    if (row.get("provider_event_id") != provider_event_id
            or row.get("tenant_id") != tenant_id):
        raise refuse("the admission belongs to another event")
    if row.get("direction") != DIRECTION_INBOUND:
        raise refuse("the inbox recorded direction %r" % row.get("direction"))
    if str(row.get("decision_ref") or "").startswith("excluded:"):
        raise refuse("the inbox excluded this event: %s" % row.get("decision_ref"))
    if row.get("actor_id") is not None and row.get("actor_id") in own:
        raise refuse("the inbox recorded our own actor")
    # LAST WORD: the durable store, not the dict. Everything above judged the
    # shape the caller handed over; this judges what `inbox_events` actually
    # holds, so a hand-written admission cannot release a suppressed thread.
    if inbox is None:
        raise refuse("no durable inbox store was supplied to prove this event")
    durable_row = _durable_inbox_row(inbox, event)
    if durable_row is None:
        raise refuse("the durable inbox holds no row for this event")
    if (durable_row.get("provider_event_id") != provider_event_id
            or durable_row.get("tenant_id") != tenant_id):
        raise refuse("the durable inbox row belongs to another event")
    if durable_row.get("direction") != DIRECTION_INBOUND:
        raise refuse("the durable inbox recorded direction %r"
                     % durable_row.get("direction"))
    if str(durable_row.get("decision_ref") or "").startswith("excluded:"):
        raise refuse("the durable inbox excluded this event: %s"
                     % durable_row.get("decision_ref"))
    if durable_row.get("actor_id") is not None and durable_row.get("actor_id") in own:
        raise refuse("the durable inbox recorded our own actor")
    return event


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
                      now: Optional[float] = None
                      ) -> Tuple[OpenerState, bool]:
        """Record the ONE private opener for a thread. Idempotent.

        Returns exactly ``(OpenerState, created)`` on EVERY path: the durable
        opener row for the thread and whether THIS call created it. A second
        opener for the same thread returns the existing row with
        created=False. The opener is never replaced by a newer action id.

        The write is a single conditional INSERT (`ON CONFLICT ... DO NOTHING`
        on the thread primary key), never a read-then-write: two workers that
        race here cannot both insert, and neither can overwrite the other's
        action id.
        """
        for name, value in (("tenant_id", tenant_id),
                            ("account_id", account_id),
                            ("thread_key", thread_key),
                            ("opener_action_id", opener_action_id)):
            _id(value, name)
        ts = _ts(now)
        cur = self._db.execute(
            "INSERT INTO ig_openers (tenant_id, account_id, thread_key,"
            " opener_action_id, comment_id, sent_at, customer_responded_at)"
            " VALUES (?,?,?,?,?,?,NULL)"
            " ON CONFLICT(tenant_id, account_id, thread_key) DO NOTHING",
            (tenant_id, account_id, thread_key, opener_action_id,
             comment_id, ts),
        )
        created = cur.rowcount == 1
        state = self.opener_state(tenant_id, account_id, thread_key)
        if state is None:  # the row vanished between insert and read
            raise InstagramRouteError(
                "not_found: the opener row for thread %r is missing" % thread_key)
        return state, created

    def claim_opener(self, *, tenant_id: str, account_id: str, thread_key: str,
                     claim_token: str, action_id: str,
                     now: Optional[float] = None,
                     lease_seconds: float = DEFAULT_OPENER_CLAIM_S) -> bool:
        """Atomically take this thread's ONE opener slot. True if we won it.

        This is the mutual exclusion behind "one opener per thread", and its
        guarantee has an exact bound. Eligibility alone is read-then-act: four
        workers can each read "no opener" and all four send. The claim is ONE
        conditional statement whose WHERE decides the winner inside SQLite's
        write lock, so exactly one concurrent worker can hold a thread at a
        time -- FOR AS LONG AS ITS LEASE LASTS (`lease_seconds`, 300 s by
        default). A holder that stalls past `expires_at` is indistinguishable
        from a crashed one, so a later worker may take the claim over and send
        a second opener; that is the ceiling, and it is stated rather than
        hidden. Making it an invariant needs a lease heartbeat across the
        provider call, which is a change to the dispatch loop, not to this
        claim.

        The claim is refused outright once an opener row exists, and it may
        only be taken over from a claim that was released or has expired (a
        crashed worker must not wedge a thread forever).
        """
        for name, value in (("tenant_id", tenant_id),
                            ("account_id", account_id),
                            ("thread_key", thread_key),
                            ("claim_token", claim_token),
                            ("action_id", action_id)):
            _id(value, name)
        ts = _ts(now)
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds,
                                                            (int, float)):
            raise InstagramRouteError("bad_input: lease_seconds must be a number")
        if float(lease_seconds) <= 0:
            raise InstagramRouteError("bad_input: lease_seconds must be positive")
        expires = ts + float(lease_seconds)
        cur = self._db.execute(
            "INSERT INTO ig_opener_claims (tenant_id, account_id, thread_key,"
            " claim_token, action_id, acquired_at, expires_at, released_at)"
            " SELECT ?,?,?,?,?,?,?,NULL"
            " WHERE NOT EXISTS (SELECT 1 FROM ig_openers"
            "  WHERE tenant_id=? AND account_id=? AND thread_key=?)"
            " ON CONFLICT(tenant_id, account_id, thread_key) DO UPDATE SET"
            "  claim_token=excluded.claim_token,"
            "  action_id=excluded.action_id,"
            "  acquired_at=excluded.acquired_at,"
            "  expires_at=excluded.expires_at,"
            "  released_at=NULL"
            " WHERE ig_opener_claims.released_at IS NOT NULL"
            "  OR ig_opener_claims.expires_at <= excluded.acquired_at",
            (tenant_id, account_id, thread_key, claim_token, action_id, ts,
             expires, tenant_id, account_id, thread_key),
        )
        return cur.rowcount == 1

    def release_opener_claim(self, *, tenant_id: str, account_id: str,
                             thread_key: str, claim_token: str,
                             now: Optional[float] = None) -> bool:
        """Release OUR claim only; another worker's claim is left alone."""
        for name, value in (("tenant_id", tenant_id),
                            ("account_id", account_id),
                            ("thread_key", thread_key),
                            ("claim_token", claim_token)):
            _id(value, name)
        ts = _ts(now)
        cur = self._db.execute(
            "UPDATE ig_opener_claims SET released_at=?"
            " WHERE tenant_id=? AND account_id=? AND thread_key=?"
            " AND claim_token=? AND released_at IS NULL",
            (ts, tenant_id, account_id, thread_key, claim_token),
        )
        return cur.rowcount == 1

    def record_customer_interaction(self, *, tenant_id: str, account_id: str,
                                    thread_key: str, provider_event_id: str,
                                    account: InstagramAccount,
                                    event: Optional[InstagramEvent] = None,
                                    admission: Any = None,
                                    inbox: Any = None,
                                    own_actor_ids: Any = (),
                                    now: Optional[float] = None) -> bool:
        """Record a VERIFIED inbound customer interaction for a thread.

        Proof is required, not caller convention: pass the customer's own
        inbound `event`, the `admission` record admit_instagram_event()
        returned for it, AND `inbox` -- the durable store that owns
        `inbox_events`. The store is what proves it: its row for this event is
        re-read here, and a dict handed over as `admission` is never enough on
        its own. Anything else is refused and NEVER ends the ignored-opener
        state. Deduped by provider event id, so the same delivered event keeps
        one row and returns False from then on.

        `account` is REQUIRED: it is the authoritative ownership record, so
        our own actor can never be mistaken for a customer. `own_actor_ids`
        only adds further ids.
        """
        for name, value in (("tenant_id", tenant_id),
                            ("account_id", account_id),
                            ("thread_key", thread_key),
                            ("provider_event_id", provider_event_id)):
            _id(value, name)
        if (tenant_id != account.tenant_id or account_id != account.account_id):
            raise InstagramRouteError(
                "bad_input: %s (account %r/%r is not this record's %r/%r)"
                % (R_EVENT_ACCOUNT_MISMATCH, tenant_id, account_id,
                   account.tenant_id, account.account_id))
        own_actor_ids = _own_actor_set(account, own_actor_ids)
        proven = _verified_inbound_interaction(
            tenant_id=tenant_id, account_id=account_id, thread_key=thread_key,
            provider_event_id=provider_event_id, event=event,
            admission=admission, inbox=inbox, own_actor_ids=own_actor_ids)
        ts = _ts(now)
        self._db.execute("BEGIN IMMEDIATE")
        try:
            cur = self._db.execute(
                "INSERT OR IGNORE INTO ig_customer_interactions"
                " (tenant_id, account_id, thread_key, provider_event_id,"
                " kind, received_at) VALUES (?,?,?,?,?,?)",
                (tenant_id, account_id, thread_key, provider_event_id,
                 proven.kind, ts),
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
    inbox: Any = None,
    own_actor_ids: Any = (),
    now_fn: Any = None,
):
    """Build the outbound_gate evaluator for one Instagram action.

    The evaluator reads durable opener state on every call, so a customer
    reply or an ignored opener changes the answer without a restart. It never
    caches a verdict and never returns ALLOW by default.

    `inbox` is the durable store that owns `inbox_events`; it is the only
    thing that can prove an inbound customer DM, so a direct-message window
    without it is closed.

    `consent_evaluator` is the upstream consent gate (`consent_gate.
    make_gate_evaluator`): the global STOP and the human-ownership fence
    decide first. This adapter never decides consent itself and never sends
    without that answer — none, or anything but its ALLOW, is SUPPRESSED.
    """
    if not isinstance(account, InstagramAccount):
        raise InstagramRouteError("bad_input: account must be InstagramAccount")
    if not isinstance(route_store, InstagramRouteStore):
        raise InstagramRouteError("bad_input: route_store must be InstagramRouteStore")
    if consent_evaluator is not None and not callable(consent_evaluator):
        raise InstagramRouteError("bad_input: consent_evaluator must be callable")
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
        blocked = _consent_verdict(
            consent_evaluator, dict(ctx, channel=channel), now=ts,
            binding_revision=account.binding_revision)
        if blocked is not None:
            return blocked
        opener = route_store.opener_state(
            account.tenant_id, account.account_id, thread_key)
        verdict = evaluate_eligibility(
            account=account, purpose=purpose, channel=channel, event=event,
            filter_=filter_, capability=capability, opener=opener,
            inbox=inbox, own_actor_ids=own_actor_ids, now=ts)
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
    own_actor_ids: Any = (),
    context: Optional[Dict[str, Any]] = None,
    now: Optional[float] = None,
    lease_seconds: Optional[float] = None,
    opener_claim_seconds: float = DEFAULT_OPENER_CLAIM_S,
) -> Any:
    """Send one Instagram action through the common fresh gate.

    The only dispatcher is outbound_gate.dispatch(). A recorded opener is
    written only after the provider accepted the send, so a blocked or
    failed attempt never creates ignored-opener state.

    For a private opener the thread's ONE opener slot is claimed from the
    durable store BEFORE dispatch. Eligibility is read-then-act; four workers
    can each read "no opener" and all four send. The claim is one conditional
    write, so exactly one worker proceeds and the others send nothing. The
    claim is held across the whole send and released on every non-send path,
    so a blocked or failed attempt neither wedges the thread nor creates
    opener state. The guarantee is bounded by the claim lease
    (`opener_claim_seconds`, DEFAULT_OPENER_CLAIM_S = 300 s): a worker that
    stalls inside the provider call past that lease may be taken over and a
    second opener may then be sent. Holding the claim for the life of the
    send is what the lease buys; an unconditional "never a second opener"
    would need a lease heartbeat across the provider call.

    `store` is also the eligibility proof for a direct-message window: the
    evaluator re-reads `inbox_events` through it, so an event the durable
    inbox never admitted cannot authorise a send here.
    """
    outbound_gate = _upstream("outbound_gate")
    evaluator = make_gate_evaluator(
        account=account, route_store=route_store, purpose=purpose,
        channel=channel, thread_key=thread_key, event=event, filter_=filter_,
        capability=capability, consent_evaluator=consent_evaluator,
        inbox=store, own_actor_ids=own_actor_ids)
    kwargs: Dict[str, Any] = {
        "now": now,
        "context": dict(context or {}, channel=channel,
                        ig_purpose=purpose, ig_thread_key=thread_key),
    }
    if lease_seconds is not None:
        kwargs["lease_seconds"] = lease_seconds

    claim_token: Optional[str] = None
    if purpose == PURPOSE_COMMENT_PRIVATE_OPENER:
        claim_token = uuid.uuid4().hex
        if not route_store.claim_opener(
                tenant_id=account.tenant_id, account_id=account.account_id,
                thread_key=thread_key, claim_token=claim_token,
                action_id=action_id, now=now,
                lease_seconds=opener_claim_seconds):
            existing = route_store.opener_state(
                account.tenant_id, account.account_id, thread_key)
            note = ("this thread already has a recorded opener"
                    if existing is not None and existing.opener_sent
                    else "another worker holds this thread's opener claim")
            return outbound_gate.DispatchOutcome(
                outbound_gate.ST_REFUSED_RACE, action_id,
                note=note + "; nothing sent")
    try:
        outcome = outbound_gate.dispatch(
            store, evaluator, sender, action_id, worker_id, **kwargs)
        if (outcome.status == outbound_gate.ST_SENT
                and purpose == PURPOSE_COMMENT_PRIVATE_OPENER):
            route_store.record_opener(
                tenant_id=account.tenant_id, account_id=account.account_id,
                thread_key=thread_key, opener_action_id=action_id,
                comment_id=event.comment_id if event else None,
                now=now)
    finally:
        if claim_token is not None:
            route_store.release_opener_claim(
                tenant_id=account.tenant_id, account_id=account.account_id,
                thread_key=thread_key, claim_token=claim_token)
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

    # separate account: two identity keys that disagree are refused.
    try:
        resolve_account([account], account_id="ig-acct-1",
                        ig_user_id="1784-DOES-NOT-MATCH")
        ok(False, "disagreeing identity keys refused")
    except InstagramRouteError as exc:
        ok(R_ACCOUNT_IDENTITY_CONFLICT in str(exc),
           "disagreeing identity keys refused")
    ok(resolve_account([account], account_id="ig-acct-1",
                       ig_user_id="17841400000000001") is account,
       "agreeing identity keys still resolve")

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
        channel=CHANNEL_IG_PUBLIC, event=event, filter_=filter_,
        capability=InstagramCapability(CAP_COMMENT_PUBLIC_REPLY))
    ok(v_public.allowed and v_public.inbound_dm_window is False,
       "public reply allowed without a DM window")
    ungranted = evaluate_eligibility(
        account=account, purpose=PURPOSE_PUBLIC_REPLY,
        channel=CHANNEL_IG_PUBLIC, event=event, filter_=filter_,
        capability=InstagramCapability(CAP_COMMENT_PUBLIC_REPLY,
                                       granted=False))
    ok(not ungranted.allowed
       and ungranted.reason == R_CAPABILITY_NOT_GRANTED,
       "an ungranted capability authorizes nothing")
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

    # ignored opener: no drip until a VERIFIED customer interaction.
    workdir = Path(tempfile.mkdtemp(prefix="ig-route-selfcheck-"))
    inbox = _upstream("durable_store").DurableStore(str(workdir / "inbox.sqlite"))
    route_store = InstagramRouteStore(str(workdir / "r.sqlite"))
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
    try:
        route_store.record_customer_interaction(
            tenant_id="t1", account_id="ig-acct-1", thread_key="th1",
            provider_event_id="dm-1", account=account, now=35)
        ok(False, "an unverified interaction is refused")
    except InstagramRouteError as exc:
        ok(R_UNVERIFIED_INTERACTION in str(exc),
           "an unverified interaction is refused")
    dm = normalise_event({
        "provider": "instagram", "provider_event_id": "dm-1", "tenant_id": "t1",
        "account_id": "ig-acct-1", "kind": "DIRECT", "direction": "inbound",
        "actor_id": "customer-1", "text": "yes", "thread_key": "th1",
        "received_at": 38})
    admission = admit_instagram_event(inbox, dm, account=account)
    ok(route_store.record_customer_interaction(
        tenant_id="t1", account_id="ig-acct-1", thread_key="th1",
        provider_event_id="dm-1", account=account,
        event=dm, admission=admission, inbox=inbox, now=40),
       "a verified interaction ends the ignored state")
    state = route_store.opener_state("t1", "ig-acct-1", "th1")
    ok(state.opener_sent and state.customer_responded,
       "the verified interaction is on the thread's durable state")
    second_opener, created_again = route_store.record_opener(
        tenant_id="t1", account_id="ig-acct-1", thread_key="th1",
        opener_action_id="act-2", now=50)
    ok(created_again is False
       and second_opener.opener_action_id == "act-1"
       and isinstance(second_opener, OpenerState),
       "a thread never gets a second opener and the return type is stable")

    # ownership comes from the account record, not from a hand-kept list.
    ours = normalise_event({
        "provider": "instagram", "provider_event_id": "own-1", "tenant_id": "t1",
        "account_id": "ig-acct-1", "kind": "DIRECT", "direction": "inbound",
        "actor_id": account.ig_user_id, "text": "hi", "thread_key": "th1",
        "received_at": 60})
    ok(admit_instagram_event(inbox, ours, account=account)["reason"]
       == "excluded:own_actor",
       "our own ig_user_id is excluded without any caller-supplied list")

    # ownership CLASS: a mapping's keys are never the own-actor set, and no
    # non-collection leaks a raw TypeError out of this boundary.
    for bad in (3, None, 1.5, {"customer-1": "x"}, [3], object()):
        try:
            admit_instagram_event(inbox, dm, account=account,
                                  own_actor_ids=bad)
            ok(False, "own_actor_ids %r refused as a domain error" % (bad,))
        except InstagramRouteError:
            ok(True, "own_actor_ids %r refused as a domain error" % (bad,))

    # proof is the durable inbox ROW, never a dict the caller hands over.
    ghost = normalise_event({
        "provider": "instagram", "provider_event_id": "ghost-1", "tenant_id": "t1",
        "account_id": "ig-acct-1", "kind": "DIRECT", "direction": "inbound",
        "actor_id": "customer-1", "text": "hi", "thread_key": "th2",
        "received_at": 74})
    try:
        route_store.record_customer_interaction(
            tenant_id="t1", account_id="ig-acct-1", thread_key="th2",
            provider_event_id="ghost-1", account=account,
            event=ghost, admission={"admitted": True, "reason": "admitted",
                                    "row": {"provider_event_id": "ghost-1",
                                            "tenant_id": "t1",
                                            "direction": "inbound",
                                            "actor_id": "customer-1"}},
            inbox=inbox, now=75)
        ok(False, "a hand-written admission is not proof")
    except InstagramRouteError as exc:
        ok("the durable inbox holds no row for this event" in str(exc),
           "a hand-written admission is not proof")

    # a malformed provider payload leaves as this adapter's own error.
    for bad in ({"received_at": "not-a-number"},
                {"received_at": [1]}, {1: "x", "provider": "instagram"}):
        raw = {"provider": "instagram", "provider_event_id": "bad",
               "tenant_id": "t1", "account_id": "ig-acct-1",
               "kind": "COMMENT", "direction": "inbound", "actor_id": "c",
               "text": "x", "thread_key": "c1"}
        raw.update(bad)
        try:
            normalise_event(raw)
            ok(False, "a malformed payload is a domain error: %r" % (bad,))
        except InstagramRouteError:
            ok(True, "a malformed payload is a domain error: %r" % (bad,))

    # the ALLOW record asserts the basis the caller actually offered.
    candidate = normalise_event({
        "provider": "instagram", "provider_event_id": "e2", "tenant_id": "t1",
        "account_id": "ig-acct-1", "kind": "COMMENT", "direction": "inbound",
        "actor_id": "customer-1", "text": "billboard", "thread_key": "c2",
        "comment_id": "c2", "received_at": 70})
    offered = evaluate_eligibility(
        account=account, purpose=PURPOSE_PUBLIC_REPLY,
        channel=CHANNEL_IG_PUBLIC, event=candidate, filter_=filter_,
        capability=InstagramCapability(CAP_COMMENT_PUBLIC_REPLY),
        basis=BASIS_CONSENT_RECORD, now=80)
    ok(offered.allowed and offered.basis == BASIS_CONSENT_RECORD
       and offered.refreshed_by == BASIS_CONSENT_RECORD,
       "the ALLOW record asserts only the basis the caller offered")

    # the opener claim is one conditional write: four racers, one winner.
    import threading
    claims = []
    lock = threading.Lock()
    ready = threading.Barrier(5)

    def race(i: int) -> None:
        store_i = InstagramRouteStore(str(workdir / "r.sqlite"))
        try:
            ready.wait()
            won = store_i.claim_opener(
                tenant_id="t1", account_id="ig-acct-1", thread_key="race",
                claim_token="tok-%d" % i, action_id="act-%d" % i, now=100)
            with lock:
                claims.append(won)
        finally:
            store_i.close()

    threads = [threading.Thread(target=race, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    ready.wait()
    for t in threads:
        t.join()
    ok(sorted(claims) == [False, False, False, True],
       "four concurrent claims on one thread have exactly one winner")

    route_store.close()
    inbox.close()

    print("OK %d PASS" % passed)
    return 0


if __name__ == "__main__":
    sys.exit(_selfcheck())
