"""S80-07 - Signature Launch extra-offer routing state logic (LOCAL part).

Deterministic, stdlib-only implementation of the route edges in
02_SHARED_CONTRACTS_AND_ARCHITECTURE.md section 4 for the purchase stages
checkout / upsell_1 / downsell_1 / upsell_2, cross-checked against
packet/reference/reference_contracts.py (resolve_after + Extras) and the 64
packet acceptance cases.

Governing sources: doc 02 section 4 and spec 10 (Skill 80) win over the
reference helper wherever they differ. Recorded differences (see
BUILD-NOTES-ADAPTERS.md, "Semantic differences"):

  D1. reference_contracts has no `continue_without_extra` event (unknown
      events raise). Doc 02 section 4 explicitly requires that a deliberate
      'continue without this extra offer' action after a payment failure is
      an explicit decline RECORDED SEPARATELY. This module therefore adds
      CONTINUE_WITHOUT: it routes exactly like explicit_decline, but its
      history record is a distinct kind so the earlier failure record and
      the later decline record never merge.
  D2. reference_contracts has no `tab_closed` event (it would raise).
      Doc 02 section 4: closing a tab is abandonment, not a fabricated
      decline event. This module adds TAB_CLOSED -> stay in place, record
      kind "abandonment", and it NEVER records a decline.
  D3. Reference returns bare (stage, purchased) pairs. This module returns
      page-ID-resolved transitions (one canonical U2 page ID for both U2
      entry paths), the U2 entry context, and an auditable event history.
      Transition semantics are otherwise unchanged.
  Aligned (not differences): the Extras invariant (U1 disabled => D1 and U2
  must also be disabled) is doc 02 section 4 verbatim; checkout
  payment_succeeded requires pre-existing trusted main-purchase evidence
  (a MAIN-* token recorded by the trusted S44/S06 adapter) and never mints
  purchase tokens itself; payment_verified=False on a claimed success is
  an error, never a transition.

Safety invariants enforced here:
  * A pending or failed payment, or a payment requiring customer action,
    remains in a recoverable state. It traverses NO acceptance edge and NO
    decline edge, and grants NO entitlement (doc 02 section 4, spec 10
    section 10: "Failure never becomes an implicit decline or successful
    entitlement").
  * Decline-both can never reach upsell_2: upsell_2 is reachable only
    after a verified upsell_1 or downsell_1 purchase.
  * U1 and D1 are mutually exclusive in this profile.
  * No auto-purchase: page load, scroll, timer expiry and close-icon
    clicks can never purchase (spec 10 section 6). Only an explicit CTA
    click on the guarded native action may even attempt a purchase.
  * This module performs no charges, no network calls and no native
    binding. It consumes verified journey state supplied by trusted
    adapters; a client-side claim is never purchase proof.
"""

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Mapping, Optional, Tuple

# ---------------------------------------------------------------------------
# Vocabulary (doc 02 section 4 events, specialised for the extra-offer stages)
# ---------------------------------------------------------------------------

CHECKOUT = "checkout"
UPSELL_1 = "upsell_1"
DOWNSELL_1 = "downsell_1"
UPSELL_2 = "upsell_2"
THANK_YOU = "thank_you"

PURCHASE_STAGES = (CHECKOUT, UPSELL_1, DOWNSELL_1, UPSELL_2)
TERMINAL_STAGE = THANK_YOU

PAYMENT_SUCCEEDED = "payment_succeeded"
EXPLICIT_DECLINE = "explicit_decline"
CONTINUE_WITHOUT = "continue_without_extra"
PAYMENT_PENDING = "payment_pending"
PAYMENT_FAILED = "payment_failed"
REQUIRES_CUSTOMER_ACTION = "requires_customer_action"
TAB_CLOSED = "tab_closed"

STAY_EVENTS = (PAYMENT_PENDING, PAYMENT_FAILED, REQUIRES_CUSTOMER_ACTION)
ALL_EVENTS = (
    PAYMENT_SUCCEEDED,
    EXPLICIT_DECLINE,
    CONTINUE_WITHOUT,
    PAYMENT_PENDING,
    PAYMENT_FAILED,
    REQUIRES_CUSTOMER_ACTION,
    TAB_CLOSED,
)

# Slot tokens recorded in the purchased set. Main purchases keep the
# reference convention: the trusted adapter records the concrete main
# offer token (e.g. "MAIN-A"); extras use these fixed slot codes, exactly
# as in reference_contracts.resolve_after and acceptance-cases.json.
SLOT_BY_STAGE = {UPSELL_1: "U1", DOWNSELL_1: "D1", UPSELL_2: "U2"}
BUMP_TOKEN = "BUMP"

# Spec 10 section 6: these triggers must never purchase anything.
NON_PURCHASE_TRIGGERS = frozenset(
    {"page_load", "scroll", "timer_expiry", "close_icon_click"}
)
PURCHASE_TRIGGER = "cta_click"


class RouteError(ValueError):
    """Raised for any transition the route contract does not allow."""


def ensure_trigger_may_purchase(trigger: str) -> None:
    """Guard: only an explicit CTA click may attempt a purchase."""
    if trigger in NON_PURCHASE_TRIGGERS:
        raise RouteError(
            "Trigger %r can never purchase (spec 10 section 6: no "
            "auto-purchase on page load, scroll, timer expiry or "
            "close-icon click)." % (trigger,)
        )
    if trigger != PURCHASE_TRIGGER:
        raise RouteError("Unknown purchase trigger %r." % (trigger,))


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RouteConfig:
    """Enabled extra-offer slots plus the canonical page-ID map.

    page_ids maps role -> page_id for every purchase stage and thank_you.
    There is exactly ONE upsell_2 entry: the same canonical U2 page serves
    the from_upsell_1 and from_downsell_1 paths (spec 10 section 5).
    """

    upsell_1: bool = True
    downsell_1: bool = True
    upsell_2: bool = True
    page_ids: Mapping[str, str] = field(
        default_factory=lambda: {
            CHECKOUT: "TEST-CHECKOUT",
            UPSELL_1: "TEST-UPSELL_1",
            DOWNSELL_1: "TEST-DOWNSELL_1",
            UPSELL_2: "TEST-UPSELL_2",
            THANK_YOU: "TEST-THANK_YOU",
        }
    )

    def __post_init__(self) -> None:
        for name, value in (
            ("upsell_1", self.upsell_1),
            ("downsell_1", self.downsell_1),
            ("upsell_2", self.upsell_2),
        ):
            if type(value) is not bool:
                raise RouteError("Extra-offer flag %s must be a boolean." % name)
        # Doc 02 section 4 / reference Extras invariant.
        if not self.upsell_1 and (self.downsell_1 or self.upsell_2):
            raise RouteError(
                "This launch profile requires U1 for D1/U2 qualification: "
                "when upsell_1 is disabled, downsell_1 and upsell_2 "
                "cannot remain enabled."
            )
        required = {CHECKOUT, UPSELL_1, DOWNSELL_1, UPSELL_2, THANK_YOU}
        missing = required - set(self.page_ids)
        if missing:
            raise RouteError("page_ids is missing roles: %s" % sorted(missing))
        u2_ids = [pid for role, pid in self.page_ids.items() if role == UPSELL_2]
        if len(u2_ids) != 1 or not u2_ids[0]:
            raise RouteError("Exactly one canonical upsell_2 page ID is required.")

    def enabled(self, stage: str) -> bool:
        return {
            UPSELL_1: self.upsell_1,
            DOWNSELL_1: self.downsell_1,
            UPSELL_2: self.upsell_2,
        }.get(stage, True)

    def page_id(self, stage: str) -> str:
        return self.page_ids[stage]


def edges(config: RouteConfig) -> List[Dict[str, str]]:
    """The explicit doc 02 section 4 edge list for the extra-offer stages.

    Includes the checkout entry edge, every success/decline edge, the
    recoverable stay edges for pending/failed/requires-action payments,
    and the separately-recorded continue-without edges. Disabled slots
    produce no edges (a disabled U2 creates no orphan node, spec 10
    section 10).
    """
    out: List[Dict[str, str]] = []

    def add(frm: str, event: str, condition: str, to: str, guard: str) -> None:
        out.append(
            {"from": frm, "event": event, "condition": condition, "to": to, "guard": guard}
        )

    # checkout --payment_succeeded--> upsell_1 OR thank_you
    add(
        CHECKOUT,
        PAYMENT_SUCCEEDED,
        "verified_main_payment",
        UPSELL_1 if config.upsell_1 else THANK_YOU,
        "trusted_adapter_main_purchase_token",
    )
    for stage, slot in ((UPSELL_1, "U1"), (DOWNSELL_1, "D1"), (UPSELL_2, "U2")):
        if not config.enabled(stage):
            continue
        # Recoverable stays: pending/failed/requires-action never traverse.
        for ev in STAY_EVENTS:
            add(
                stage,
                ev,
                "remain_on_page_recoverable",
                stage,
                "no_acceptance_no_decline_no_entitlement",
            )
        add(stage, TAB_CLOSED, "abandonment_not_decline", stage, "no_event_fabricated")
    if config.upsell_1:
        add(
            UPSELL_1,
            PAYMENT_SUCCEEDED,
            "verified_u1_payment",
            UPSELL_2 if config.upsell_2 else THANK_YOU,
            "trusted_adapter_payment_verified",
        )
        add(
            UPSELL_1,
            EXPLICIT_DECLINE,
            "no_charge_decline",
            DOWNSELL_1 if config.downsell_1 else THANK_YOU,
            "visible_decline_action",
        )
        add(
            UPSELL_1,
            CONTINUE_WITHOUT,
            "explicit_decline_recorded_separately_after_failure",
            DOWNSELL_1 if config.downsell_1 else THANK_YOU,
            "deliberate_continue_without_action",
        )
    if config.downsell_1:
        add(
            DOWNSELL_1,
            PAYMENT_SUCCEEDED,
            "verified_d1_payment",
            UPSELL_2 if config.upsell_2 else THANK_YOU,
            "trusted_adapter_payment_verified",
        )
        add(DOWNSELL_1, EXPLICIT_DECLINE, "no_charge_decline", THANK_YOU, "visible_decline_action")
        add(
            DOWNSELL_1,
            CONTINUE_WITHOUT,
            "explicit_decline_recorded_separately_after_failure",
            THANK_YOU,
            "deliberate_continue_without_action",
        )
    if config.upsell_2:
        add(
            UPSELL_2,
            PAYMENT_SUCCEEDED,
            "verified_u2_payment",
            THANK_YOU,
            "trusted_adapter_payment_verified",
        )
        add(UPSELL_2, EXPLICIT_DECLINE, "no_charge_decline", THANK_YOU, "visible_decline_action")
        add(
            UPSELL_2,
            CONTINUE_WITHOUT,
            "explicit_decline_recorded_separately_after_failure",
            THANK_YOU,
            "deliberate_continue_without_action",
        )
    return out


# ---------------------------------------------------------------------------
# Journey state and transitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JourneyState:
    """Verified journey state at a purchase stage.

    purchased holds purchase tokens recorded ONLY by trusted adapters
    (doc 02 section 8): the concrete main offer token ("MAIN-A" style),
    optionally "BUMP", and the extra slot codes "U1" / "D1" / "U2".
    history is the auditable, append-only tuple of transition records.
    """

    stage: str
    purchased: FrozenSet[str] = frozenset()
    history: Tuple[Mapping[str, object], ...] = ()

    def has_main_purchase(self) -> bool:
        return any(t.startswith("MAIN-") for t in self.purchased)

    def visited_stages(self) -> List[str]:
        stages = [str(rec["to_stage"]) for rec in self.history]
        return stages


@dataclass(frozen=True)
class Transition:
    from_stage: str
    to_stage: str
    from_page_id: str
    to_page_id: str
    event: str
    kind: str  # transition | stay_recoverable | abandonment | recorded_decline
    purchased_after: FrozenSet[str]
    entry_context: Optional[str]  # set when entering upsell_2
    record: Mapping[str, object]
    state: JourneyState  # the new journey state


def _check_stage_enterable(state: JourneyState, config: RouteConfig) -> None:
    stage = state.stage
    if stage == THANK_YOU:
        raise RouteError("thank_you is terminal; no further purchase-stage events.")
    if stage not in PURCHASE_STAGES:
        raise RouteError("Unknown purchase stage %r." % (stage,))
    if stage != CHECKOUT and not state.has_main_purchase():
        raise RouteError("A verified main purchase is required before extras.")
    if stage == UPSELL_1 and not config.upsell_1:
        raise RouteError("U1 is disabled.")
    if stage == DOWNSELL_1 and (not config.downsell_1 or "U1" in state.purchased):
        raise RouteError("D1 is disabled or incompatible with accepted U1.")
    if stage == UPSELL_2 and (
        not config.upsell_2 or not ({"U1", "D1"} & state.purchased)
    ):
        raise RouteError(
            "U2 requires enabled status and a successful verified U1 or D1 "
            "purchase. Decline-both, a bump alone, and client-side claims "
            "never qualify."
        )


def resolve(
    state: JourneyState,
    config: RouteConfig,
    event: str,
    *,
    payment_verified: bool = False,
) -> Transition:
    """Resolve one event at the current stage, doc 02 section 4 exactly.

    payment_verified may only be supplied True by a trusted adapter with
    native purchase evidence (S44/S06); a click or redirect never proves
    payment (reference_contracts.resolve_after parity).
    """
    _check_stage_enterable(state, config)
    stage = state.stage
    purchased = state.purchased

    def finish(to_stage: str, kind: str, new_purchased: FrozenSet[str],
               entry_context: Optional[str] = None,
               classification: Optional[str] = None) -> Transition:
        record: Dict[str, object] = {
            "event": event,
            "kind": kind,
            "from_stage": stage,
            "to_stage": to_stage,
            "from_page_id": config.page_id(stage),
            "to_page_id": config.page_id(to_stage),
            "purchased_after": sorted(new_purchased),
        }
        if classification is not None:
            record["classification"] = classification
        if entry_context is not None:
            record["entry_context"] = entry_context
        new_state = JourneyState(
            stage=to_stage,
            purchased=new_purchased,
            history=state.history + (record,),
        )
        return Transition(
            from_stage=stage,
            to_stage=to_stage,
            from_page_id=config.page_id(stage),
            to_page_id=config.page_id(to_stage),
            event=event,
            kind=kind,
            purchased_after=new_purchased,
            entry_context=entry_context,
            record=record,
            state=new_state,
        )

    # --- Recoverable stays: neither acceptance nor decline, no entitlement.
    if event in STAY_EVENTS:
        return finish(
            stage,
            "stay_recoverable",
            purchased,
            classification="neither_acceptance_nor_decline",
        )

    # --- Abandonment: doc 02 section 4, never a fabricated decline.
    if event == TAB_CLOSED:
        return finish(
            stage,
            "abandonment",
            purchased,
            classification="abandonment_not_decline",
        )

    # --- Verified successful payment traverses the acceptance edge.
    if event == PAYMENT_SUCCEEDED:
        if not payment_verified:
            raise RouteError(
                "A clicked button or redirect does not prove payment; "
                "payment_verified must come from a trusted adapter."
            )
        if stage == CHECKOUT:
            if not state.has_main_purchase():
                raise RouteError("Native main purchase evidence is missing.")
            return finish(UPSELL_1 if config.upsell_1 else THANK_YOU, "transition", purchased)
        updated = purchased | {SLOT_BY_STAGE[stage]}
        if {"U1", "D1"} <= updated:
            raise RouteError("U1 and D1 are mutually exclusive in this profile.")
        if stage in (UPSELL_1, DOWNSELL_1) and config.upsell_2:
            ctx = "from_upsell_1" if stage == UPSELL_1 else "from_downsell_1"
            return finish(UPSELL_2, "transition", frozenset(updated), entry_context=ctx)
        return finish(THANK_YOU, "transition", frozenset(updated))

    # --- Declines: immediate, or the separately-recorded continue-without.
    if event in (EXPLICIT_DECLINE, CONTINUE_WITHOUT):
        if stage == CHECKOUT:
            raise RouteError("Abandoned initial checkout is not a paid thank-you path.")
        kind = "transition" if event == EXPLICIT_DECLINE else "recorded_decline"
        if stage == UPSELL_1:
            target = DOWNSELL_1 if config.downsell_1 else THANK_YOU
        else:
            target = THANK_YOU
        classification = (
            None
            if event == EXPLICIT_DECLINE
            else "explicit_decline_recorded_separately_after_failure"
        )
        return finish(target, kind, purchased, classification=classification)

    raise RouteError("Unknown event; do not infer a decline or success.")


# ---------------------------------------------------------------------------
# Payment attempt guard (spec 10 section 6: processing state, no double charge)
# ---------------------------------------------------------------------------


class PaymentAttemptGuard:
    """Single-flight guard for the guarded native one-click action.

    While an attempt is processing, repeat triggering is disabled. This is
    a local state machine only; it never charges anything.
    """

    IDLE = "idle"
    PROCESSING = "processing"

    def __init__(self) -> None:
        self.state = self.IDLE
        self.attempts = 0

    def begin_attempt(self, trigger: str = PURCHASE_TRIGGER) -> None:
        ensure_trigger_may_purchase(trigger)
        if self.state == self.PROCESSING:
            raise RouteError(
                "A payment attempt is already processing; repeat triggering "
                "is disabled while pending."
            )
        self.state = self.PROCESSING
        self.attempts += 1

    def complete_attempt(self) -> None:
        if self.state != self.PROCESSING:
            raise RouteError("No payment attempt is processing.")
        self.state = self.IDLE

    # A failed or still-pending attempt also releases the guard back to a
    # recoverable idle state; the routing layer decides what happens next
    # (stay recoverable, retry, or an explicit continue-without decline).
    def release_attempt(self) -> None:
        self.complete_attempt()
