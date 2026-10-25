#!/usr/bin/env python3
"""facebook_routes.py - supported Page comment and Messenger routes (T-20).

Contract basis: Purple Billboard DATA-CONTRACTS.md sections 2, 3 and 4;
SPEC.md lines 21-26; fixtures/contract-traces.json F-04 and F-08.

This module owns exactly four things.

ELIGIBILITY. Three routes, three independent contracts. Evidence for one
never authorises another:

  PUBLIC_REPLY            public comment reply to a person (FB_PUBLIC). The
                          reader is named, so it is person-directed, but its
                          transport is public and it needs no DM window.
  COMMENT_PRIVATE_OPENER  the one private reply opened from that comment
                          (FB_DM). A comment is not a normal inbound-DM
                          window and does not grant one.
  INBOUND_DM              an ordinary Messenger reply (FB_DM) inside the
                          customer's own inbound window, refreshed only by an
                          actual inbound message or platform eligibility.

AUTHOR EXCLUSION. Own outgoing and reveal events are excluded by verified
direction/actor before admission. The guard is durable_store.admit_event; this
module calls it and does not restate it.

KEYWORD FALLBACK. Tested m.me refs were not surfaced in the inspected
normalized fields (D-05), so a typed keyword is the fallback entry. An absent
or unknown ref never invents attribution. When nothing matches, the only
permitted effect is one welcome asking which keyword the reader saw - a drip
to an ignored opener is not permitted.

HONEST PROOF. Ordinary-reader proof of the Page route is deferred. The
capability record says so and nothing here may report it as proven.

Python 3 standard library only. Connect the eligibility verdict to the common
send gate (outbound_gate.dispatch) rather than calling it directly for a send.
"""

from __future__ import annotations

import string
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

# Skill 38 tools are siblings of this repository tree, not of this directory.
_TOOLS_DIR = Path(__file__).resolve().parents[3] / "38-conversational-ai-system" / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from outbound_gate import GateVerdict  # noqa: E402  (shared verdict vocabulary)

ROUTE_PUBLIC_REPLY = "PUBLIC_REPLY"
ROUTE_COMMENT_PRIVATE_OPENER = "COMMENT_PRIVATE_OPENER"
ROUTE_INBOUND_DM = "INBOUND_DM"

ROUTES = (ROUTE_PUBLIC_REPLY, ROUTE_COMMENT_PRIVATE_OPENER, ROUTE_INBOUND_DM)

# One route <-> one action purpose <-> one transport. The schema's purpose
# enum is the authority (schemas/outbound-action.schema.json); these are the
# three this adapter owns.
ROUTE_PURPOSE = {
    ROUTE_PUBLIC_REPLY: "PUBLIC_REPLY",
    ROUTE_COMMENT_PRIVATE_OPENER: "COMMENT_PRIVATE_OPENER",
    ROUTE_INBOUND_DM: "AI_REPLY",
}
ROUTE_CHANNEL = {
    ROUTE_PUBLIC_REPLY: "FB_PUBLIC",
    ROUTE_COMMENT_PRIVATE_OPENER: "FB_DM",
    ROUTE_INBOUND_DM: "FB_DM",
}

# A ref is a LINK, and a link lives on exactly one channel. The only refs with
# any evidence here are m.me Messenger links (D-05), so link attribution is
# credited only on the Messenger channel. An entry on another channel is never
# credited with a Messenger link ("never assume link attribution", SPEC): such
# a ref is recorded UNRECOGNIZED and falls through to the keyword, exactly like
# an unknown ref (ponytail: one channel of link evidence; add per-ref channel
# scoping when a client ships a non-Messenger link table).
MESSENGER_CHANNEL = "FB_DM"

# The single fact that authorises each route. Deliberately not shared.
ROUTE_PERMISSION_KEY = {
    ROUTE_PUBLIC_REPLY: "public_reply_permission",
    ROUTE_COMMENT_PRIVATE_OPENER: "comment_private_opener_permission",
    ROUTE_INBOUND_DM: "inbound_dm_window",
}
# Why the gate refuses when that one fact is not true. Paired with the key
# above so the gate has no second spelling of either.
ROUTE_PERMISSION_REFUSED = {
    ROUTE_PUBLIC_REPLY: "NO_PUBLIC_REPLY_PERMISSION",
    ROUTE_COMMENT_PRIVATE_OPENER: "NO_COMMENT_OPENER_PERMISSION",
    ROUTE_INBOUND_DM: "NO_INBOUND_DM_WINDOW",
}

# Only these prove the reader is inside a window we may answer. An outbound or
# cross-channel message does not refresh FB eligibility (DATA-CONTRACTS 3).
INBOUND_REFRESH_BASES = ("INBOUND_MESSAGE", "PLATFORM_ELIGIBILITY")

PROOF_SUPPORTED = "SUPPORTED"
PROOF_DEFERRED = "DEFERRED"
PROOF_NOT_PROVEN = "NOT_PROVEN"

# Actions the opener gate may report. F-08 expects the no-drip outcome by name.
OPENER_ONLY_NO_DRIP = "OPENER_ONLY_NO_DRIP"
OPENER_NO_DRIP = "NO_DRIP"
OPENER_SUPPORTED_PATH = "SUPPORTED_PATH"

# Entry bases. A keyword is a fallback, never attribution.
BASIS_REF = "REF"
BASIS_KEYWORD_FALLBACK = "KEYWORD_FALLBACK"
BASIS_NONE = "NONE"
ATTRIBUTION_PRESENT = "PRESENT"
ATTRIBUTION_ABSENT = "ABSENT"
ATTRIBUTION_UNRECOGNIZED = "UNRECOGNIZED"


class RouteError(ValueError):
    """Malformed route input. Fail closed: nothing is dispatched."""


@dataclass(frozen=True)
class EntryResult:
    """How an inbound/entry event resolves to a route."""

    route: Optional[str]
    basis: str
    attribution: str
    keyword: Optional[str] = None
    prompt_keyword: bool = False
    reason: str = ""

    @property
    def routed(self) -> bool:
        return self.route is not None

    @property
    def may_send(self) -> bool:
        """The only effect an unresolved entry permits is one keyword prompt."""
        return not self.routed and self.prompt_keyword


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RouteError(f"bad_input: {field} must be a non-empty string")
    return value.strip()


def normalise_keyword(value: Any) -> str:
    """Casefold, collapse whitespace, trim surrounding punctuation.

    Never substring-matches: 'GUIDED' is not 'GUIDE'. Interior punctuation is
    part of the literal keyword and is kept (ponytail: exact tokens only; add
    a lexicon when a real client keyword carries punctuation).
    """
    if not isinstance(value, str):
        return ""
    collapsed = " ".join(value.casefold().split())
    return collapsed.strip(string.punctuation)


def _approved_table(table: Mapping[Any, Any], *, label: str,
                    key_normaliser: Any = normalise_keyword) -> Dict[str, str]:
    """Index an approval table by the key the lookup will compare against.

    The caller reads one event and normalises what it read (a keyword is
    casefolded, a ref is trimmed). Comparing that against a table indexed by
    the raw approved spelling means an approved keyword of "GUIDE" never
    matches the reader who typed "GUIDE" -- the routing table would decide the
    contract instead of the reader. So the table is normalised the same way,
    before any lookup.

    Two approved keys that normalise to one lookup value must agree on the
    route. If they disagree the table is ambiguous and no reading of it can be
    honest, so it is refused outright rather than silently picking one.
    """
    if not isinstance(table, Mapping):
        raise RouteError(f"bad_input: {label} must be a mapping")
    indexed: Dict[str, str] = {}
    for raw_key, route in table.items():
        if not isinstance(raw_key, str):
            raise RouteError(f"bad_input: {label} keys must be strings,"
                             f" got {type(raw_key).__name__}")
        key = key_normaliser(raw_key)
        if not key:
            raise RouteError(f"bad_input: {label} key {raw_key!r} normalises"
                             " to nothing")
        if not isinstance(route, str) or not route.strip():
            raise RouteError(f"bad_input: {label} route for {raw_key!r} must"
                             " be a non-empty string")
        if key in indexed and indexed[key] != route:
            # Name the two APPROVED KEYS that collide, not their route values:
            # an operator cannot find the conflicting approvals otherwise.
            prior_key = next(k for k, v in table.items()
                             if key_normaliser(k) == key)
            raise RouteError(f"bad_input: {label} keys {prior_key!r} and"
                             f" {raw_key!r} both normalise to {key!r}")
        indexed[key] = route
    return indexed


def resolve_entry(*, channel: Any, text: Any = None, ref: Any = None,
                  ref_routes: Optional[Mapping[str, str]] = None,
                  keyword_routes: Optional[Mapping[str, str]] = None
                  ) -> EntryResult:
    """Resolve a typed message to a route: ref first, keyword as fallback.

    An unknown ref is recorded honestly as UNRECOGNIZED and falls through to
    the keyword. A known ref wins over a contradictory keyword: the keyword is
    a fallback, not a second attribution source.

    Ref attribution is channel-bound. A ref is a link, and the only link
    evidence here is an m.me Messenger link (D-05), so an entry that did not
    arrive on Messenger is never credited with one -- an Instagram entry is
    not attributed to a Messenger link ("never assume link attribution").
    Such a ref is recorded UNRECOGNIZED and falls through to the keyword.
    """
    channel_value = _text(channel, "channel")
    # An absent field (None) carries no claim. A field that IS present but is
    # not text cannot be read, and reporting it as absent would invent an
    # absence -- the mirror image of inventing attribution. Refuse it.
    if ref is not None and not isinstance(ref, str):
        raise RouteError(f"bad_input: ref must be a string when present,"
                         f" got {type(ref).__name__}")
    if text is not None and not isinstance(text, str):
        raise RouteError(f"bad_input: text must be a string when present,"
                         f" got {type(text).__name__}")
    refs = _approved_table({} if ref_routes is None else ref_routes,
                           label="ref_routes",
                           key_normaliser=lambda k: k.strip())
    words = _approved_table({} if keyword_routes is None else keyword_routes,
                            label="keyword_routes")

    ref_value = ref.strip() if isinstance(ref, str) and ref.strip() else ""
    matched_ref = (ref_value in refs
                   and channel_value == MESSENGER_CHANNEL)
    if matched_ref:
        return EntryResult(route=refs[ref_value], basis=BASIS_REF,
                           attribution=ATTRIBUTION_PRESENT, reason="ref_matched")
    attribution = ATTRIBUTION_ABSENT
    if ref_value:
        # Present in the event, but not attribution this channel may claim.
        attribution = ATTRIBUTION_UNRECOGNIZED

    keyword = normalise_keyword(text)
    if keyword and keyword in words:
        return EntryResult(route=words[keyword],
                           basis=BASIS_KEYWORD_FALLBACK,
                           attribution=attribution, keyword=keyword,
                           reason="keyword_fallback")

    # No route. The single permitted effect is the welcome asking the keyword.
    return EntryResult(route=None, basis=BASIS_NONE, attribution=attribution,
                       keyword=keyword or None, prompt_keyword=True,
                       reason="NO_ROUTE_EVIDENCE")


def evaluate_eligibility(route: Any, facts: Mapping[str, Any], *,
                         now: Optional[float] = None) -> GateVerdict:
    """Return the gate verdict for ONE route. Never a shared permission check.

    The returned GateVerdict plugs straight into outbound_gate.dispatch:
        dispatch(store, lambda ctx: evaluate_eligibility(route, facts), ...)

    The every-send facts ride in `facts`: a recorded `global_stop` and an
    `owner_current` that is not true are consumed here, so this composition
    cannot send what the C-F04 fixtures require suppressed.
    """
    if route not in ROUTES:
        raise RouteError(f"bad_input: unknown route {route!r}")
    if not isinstance(facts, Mapping):
        raise RouteError("bad_input: facts must be a mapping")
    try:
        ts = time.time() if now is None else float(now)
    except (TypeError, ValueError):
        # Malformed input is RouteError everywhere else in this module; a bare
        # ValueError here would slip past a caller's RouteError handler.
        raise RouteError("bad_input: now must be a number,"
                         f" got {type(now).__name__}") from None

    def refuse(reason: str, **evidence: Any) -> GateVerdict:
        payload = {"reason": reason, "route": route}
        payload.update(evidence)
        return GateVerdict(verdict="SUPPRESSED", checked_at=ts, evidence=payload)

    channel = facts.get("channel")
    if channel != ROUTE_CHANNEL[route]:
        return refuse("UNSUPPORTED_CHANNEL", channel=channel,
                      expected=ROUTE_CHANNEL[route])

    purpose = facts.get("action_purpose")
    if purpose != ROUTE_PURPOSE[route]:
        return refuse("PURPOSE_NOT_PERMITTED", action_purpose=purpose,
                      expected=ROUTE_PURPOSE[route])

    # C-F04 every-send gate: the STOP and ownership facts this adapter is
    # handed are load-bearing, not decoration (fixtures F-04B, F-04C). A
    # recorded global STOP suppresses every route, and an owner that is not
    # current means a human owns the conversation and the bot is fenced out
    # (DATA-CONTRACTS 3/7). A fact that is absent carries no claim, so a route
    # evaluated on its own minimal facts is not refused here. These run before
    # the binding quarantine on purpose: a stopped or human-owned thread must
    # never come back to life through a later reconcile.
    stop = facts.get("global_stop")
    if stop:
        return refuse("GLOBAL_STOP", global_stop=stop)
    owner = facts.get("owner_current")
    if owner is not None and owner is not True:
        return refuse("OWNER_NOT_CURRENT", owner_current=owner)

    # A changed account binding quarantines old queued work; never reroute it
    # silently (DATA-CONTRACTS 2/3). A binding that cannot be checked against a
    # current value is not a passing binding: it quarantines too, and the
    # evidence says which of the two it was.
    bound = facts.get("account_binding_revision")
    current = facts.get("current_binding_revision")
    if bound is not None and (current is None or bound != current):
        changed = current is not None and bound != current
        return GateVerdict(
            verdict="QUARANTINED", checked_at=ts,
            binding_revision=current,
            evidence={"reason": "BINDING_CHANGED" if changed
                      else "BINDING_UNVERIFIED",
                      "route": route,
                      "account_binding_revision": bound,
                      "current_binding_revision": current})
    if bound is None and current is not None:
        # The action carries no binding to check against the current one. The
        # outbound-action schema requires account_binding_revision on every
        # action, so this is a malformed or unverifiable binding, and an
        # unverifiable binding is not a passing one. (This is the PROBE-MIRROR
        # shape PBB-186 observed passing ALLOW.)
        return GateVerdict(
            verdict="QUARANTINED", checked_at=ts,
            binding_revision=current,
            evidence={"reason": "BINDING_UNVERIFIED",
                      "route": route,
                      "account_binding_revision": bound,
                      "current_binding_revision": current})

    permission_key = ROUTE_PERMISSION_KEY[route]
    if route == ROUTE_PUBLIC_REPLY:
        basis = "PLATFORM_ELIGIBILITY"
    elif route == ROUTE_COMMENT_PRIVATE_OPENER:
        # The opener needs the comment that opened it, not a DM window.
        if not facts.get("comment_event_id"):
            return refuse("NO_COMMENT_EVENT")
        basis = "PLATFORM_ELIGIBILITY"
    else:  # ROUTE_INBOUND_DM
        if not facts.get("inbound_message_id"):
            return refuse("NO_INBOUND_MESSAGE")
        refreshed_by = facts.get("eligibility_refreshed_by")
        if refreshed_by not in INBOUND_REFRESH_BASES:
            return refuse("ELIGIBILITY_NOT_REFRESHED",
                          eligibility_refreshed_by=refreshed_by)
        basis = "INBOUND_MESSAGE"

    # The single fact that authorises this route, named by the map above. No
    # second spelling of either the key or the refusal reason lives in here.
    if facts.get(permission_key) is not True:
        return refuse(ROUTE_PERMISSION_REFUSED[route], missing=permission_key)

    return GateVerdict(
        verdict="ALLOW", checked_at=ts,
        binding_revision=current,
        evidence={"reason": "ROUTE_ELIGIBLE", "route": route,
                  "channel": channel, "action_purpose": purpose,
                  "basis": basis})


@dataclass(frozen=True)
class AdmissionResult:
    admitted: bool
    reason: str
    row: Dict[str, Any]


def admit_inbound(store: Any, *, tenant_id: str, provider_event_id: str,
                  actor_id: Optional[str] = None,
                  own_actor_ids: Iterable[str] = (),
                  direction: str = "inbound",
                  payload_sha256: Optional[str] = None,
                  now: Optional[float] = None) -> AdmissionResult:
    """Admit a Page/Messenger event through the T-12 inbox guard.

    Own outgoing/reveal events are excluded there by verified direction and
    actor. This wrapper only pins the provider name so a Page event can never
    be admitted under another provider's identity namespace.

    own_actor_ids is a collection of ids. A bare string is rejected outright:
    it would be read as its own characters, the exclusion set would hold
    single letters, and our own actor would stop being excluded.
    """
    if isinstance(own_actor_ids, (str, bytes, bytearray)):
        raise RouteError("bad_input: own_actor_ids must be a collection of"
                         " actor ids, not one bare value")
    try:
        iter(own_actor_ids)
    except TypeError:
        # A non-collection reaches the store, where the set comprehension
        # raises TypeError after the caller already expects a refusal. Same
        # defect as the bare string: refuse it here, write nothing.
        raise RouteError("bad_input: own_actor_ids must be a collection of"
                         " actor ids") from None
    result = store.admit_event(
        provider="facebook", tenant_id=_text(tenant_id, "tenant_id"),
        provider_event_id=_text(provider_event_id, "provider_event_id"),
        direction=direction, actor_id=actor_id, payload_sha256=payload_sha256,
        own_actor_ids=own_actor_ids, now=now)
    return AdmissionResult(admitted=result["admitted"], reason=result["reason"],
                           row=result["row"])


@dataclass(frozen=True)
class OpenerDecision:
    action: str
    allowed: bool
    reason: str


def opener_decision(*, channel: Any, comment_only: Any,
                    customer_reply: Any, opener_sent: bool = False) -> OpenerDecision:
    """The minimal customer-interaction rule for a comment private opener.

    F-08: a comment alone permits at most ONE private opener and never a drip.
    An actual customer reply enables the ordinary supported inbound path. The
    rule is channel-agnostic; IG-specific eligibility belongs to T-21.
    """
    _text(channel, "channel")
    if isinstance(comment_only, str) or not isinstance(comment_only, bool):
        raise RouteError("bad_input: comment_only must be a bool")
    if isinstance(customer_reply, str) or not isinstance(customer_reply, bool):
        raise RouteError("bad_input: customer_reply must be a bool")
    # opener_sent decides whether a second opener would be a drip (F-08), so it
    # is typed like its two siblings: a falsy non-bool must not silently read
    # as "no opener sent yet" and permit the drip.
    if isinstance(opener_sent, str) or not isinstance(opener_sent, bool):
        raise RouteError("bad_input: opener_sent must be a bool")

    if customer_reply:
        return OpenerDecision(action=OPENER_SUPPORTED_PATH, allowed=True,
                              reason="CUSTOMER_REPLIED")
    if not comment_only:
        return OpenerDecision(action="NOT_A_COMMENT", allowed=False,
                              reason="OPENER_REQUIRES_COMMENT")
    if opener_sent:
        return OpenerDecision(action=OPENER_NO_DRIP, allowed=False,
                              reason="OPENER_ALREADY_SENT_NO_DRIP")
    return OpenerDecision(action=OPENER_ONLY_NO_DRIP, allowed=True,
                          reason="ONE_OPENER_ONLY")


def capability_status() -> Dict[str, Any]:
    """What this adapter may honestly claim, including what it cannot.

    Ordinary-reader proof is deferred: no live Page reader trace exists yet.
    Consumers must surface DEFERRED rather than reporting the route as proven.
    """
    return {
        "surface": "page",
        "routes": {route: PROOF_SUPPORTED for route in ROUTES},
        "ordinary_reader_proof": PROOF_DEFERRED,
        "public_monitoring": PROOF_NOT_PROVEN,
        "ref_attribution": PROOF_NOT_PROVEN,
        "keyword_fallback": PROOF_SUPPORTED,
        "author_exclusion": PROOF_SUPPORTED,
        "notes": [
            "tested m.me refs were absent from inspected normalized fields"
            " (D-05); keyword is the fallback entry",
            "ordinary-reader Page proof is deferred until a live trace exists",
            "public monitoring of old threads is a separate contract (T-26)",
        ],
    }
