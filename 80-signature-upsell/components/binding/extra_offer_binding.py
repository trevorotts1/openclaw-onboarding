"""S80-06 - Signature Launch extra-offer native binding integration (CORE).

Interface-level (L1) implementation of S80's side of the S79/S06 shared
extra-offer action/disclosure interface
(rooms/S79/work/binding/extra_offer_interface.md, DRAFT, fixture level).

Governing sources:
  * Interface section 3 (inputs): a BindingContext is presentable only on
    a VERIFIED parent purchase, with a verified native product/price
    mapping, disclosure data derived from integer minor units, approved
    next routes, and a REQUIRED capability evidence reference. F2
    repair: it also carries the distinct launch revision, the approved
    copy references, and a structured reference to the offer's full
    disclosure data (the disclosure data itself lives in the
    adapters/pages layer).
  * Interface section 4 (outputs): the action result uses the doc 09
    section 8 purchase-state vocabulary exactly, and only a verified
    native success counts as paid - here, "verified" means the driver's
    invoke result is CONFIRMED by a native read-back. A bare invoke
    result of paid is pending_confirmation, never paid.
  * Interface section 5 (disclosure): where one-click support is not
    VERIFIED (capability False or unknown/None), the one-click route is
    disabled and the decision records the approved-fallback requirement
    (standard checkout fallback with clear disclosure and user choice).
    Unknown capability is never silently treated as supported; the
    S79 capability doctrine (capability_matrix.py) is the same rule.
    F1 repair: the gate is enforced by the binding itself - accept()
    refuses unless a presentation decision offering one-click has been
    recorded on this binding first.
  * Interface section 6 (no-rollback): the parent purchase is a
    read-only input. This module exposes no method that mutates parent
    state, never gates or delays parent fulfillment, and every
    AttemptOutcome carries parent_purchase_unaffected=True with the
    parent state it observed. Retry of an extra offer reconciles
    against native records FIRST (unknown-outcome discipline).
  * Interface section 7 (open questions): Q1..Q9 are carried as data in
    OPEN_QUESTIONS with status "unresolved". Nothing here invents a
    native action ID, element name, or vendor fact; binding_record()
    reports native_action_id=None and
    binding_status="interface_conformant_pending_s06".
  * Spec 10 section 6: the guarded action is single-flight (processing
    disables repeat triggering, via routing_state.PaymentAttemptGuard);
    decline is a visible, normal routed outcome that never charges.

Composition: this module reuses the adapters' verified-purchase
vocabulary (adapter_common.ADAPTER_VERIFICATION_SOURCES - a client-side
claim is never accepted as a verification source) and the adapters'
single-flight guard (routing_state.PaymentAttemptGuard). It performs
no network calls and no charges; the NativeDriver is supplied by the
caller (in production, by S06's installed binding - pending Q1..Q6).
"""

from __future__ import annotations

import copy
import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Mapping, Optional, Protocol, Tuple

# Compose with the existing S80 adapters (sibling tree, read-only).
_ADAPTERS_DIR = Path(__file__).resolve().parent.parent / "adapters"
if _ADAPTERS_DIR.is_dir() and str(_ADAPTERS_DIR) not in sys.path:
    sys.path.insert(0, str(_ADAPTERS_DIR))

from adapter_common import ADAPTER_VERIFICATION_SOURCES  # noqa: E402
from routing_state import PaymentAttemptGuard  # noqa: E402

# ---------------------------------------------------------------------------
# Purchase-state vocabulary (doc 09 section 8, via interface section 4)
# ---------------------------------------------------------------------------

READY = "ready"
VALIDATING = "validating"
SUBMITTING = "submitting"
PENDING_CONFIRMATION = "pending_confirmation"
PAID = "paid"
FAILED = "failed"
REQUIRES_CUSTOMER_ACTION = "requires_customer_action"
CANCELLED = "cancelled"

PURCHASE_STATES = (
    READY,
    VALIDATING,
    SUBMITTING,
    PENDING_CONFIRMATION,
    PAID,
    FAILED,
    REQUIRES_CUSTOMER_ACTION,
    CANCELLED,
)

# Legal transitions. paid and cancelled are terminal. failed may start a
# NEW attempt (validating) only after its outcome is known - an attempt
# whose outcome is unknown sits in pending_confirmation and cannot
# transition back to validating/submitting until reconcile resolves it.
TRANSITIONS = {
    READY: frozenset({VALIDATING, CANCELLED}),
    VALIDATING: frozenset({SUBMITTING, FAILED, CANCELLED}),
    SUBMITTING: frozenset(
        {PENDING_CONFIRMATION, PAID, FAILED, REQUIRES_CUSTOMER_ACTION, CANCELLED}
    ),
    PENDING_CONFIRMATION: frozenset(
        {PAID, FAILED, REQUIRES_CUSTOMER_ACTION, CANCELLED}
    ),
    REQUIRES_CUSTOMER_ACTION: frozenset({SUBMITTING, FAILED, CANCELLED}),
    FAILED: frozenset({VALIDATING}),
    PAID: frozenset(),
    CANCELLED: frozenset(),
}

# Verified parent-purchase sources (adapter_common): a client-side claim
# such as acceptedU1=true is NEVER in this set and is never accepted.
VERIFIED_SOURCES = ADAPTER_VERIFICATION_SOURCES

ENTRY_CONTEXTS = frozenset({"from_upsell_1", "from_downsell_1"})
BILLING_TYPES = frozenset({"one_time", "recurring"})

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
# A structured evidence reference: a scheme-prefixed ref (ledger:...,
# provider-event:..., s44:..., native:..., catalog:..., https://...) or a
# separator-structured id (path-like or dashed). A bare assertion word
# ("yes", "verified") is not structured evidence and is rejected.
_STRUCTURED_REF_RE = re.compile(r"^(?:[a-z][a-z0-9+.-]*:[^\s]+|[^\s]+[/][^\s]+|[^\s]+-[^\s]+)$")

# Capability evidence refs (F6 repair, review-S80-06-binding-core): the
# house evidence standard the S80 copy validator already uses. The ref
# must carry one of these recognized scheme prefixes; a bare dashed or
# path-like string ("a-b", "some/path") is NOT evidence and is rejected.
# The check stays syntactic - authenticity of the ref remains S06's
# evidence to provide (open question S06-Q2).
EVIDENCE_REF_PREFIXES = (
    "native:", "ledger:", "provider-event:", "s44:", "catalog:",
    "request:", "graph:", "https://",
)
_CAPABILITY_EVIDENCE_RE = re.compile(
    r"^(?:native|ledger|provider-event|s44|catalog|request|graph):[^\s]+$"
    r"|^https://[^\s]+$"
)

INTERFACE_REF = "S79 extra_offer_interface.md DRAFT (fixture level)"
BINDING_STATUS = "interface_conformant_pending_s06"
FALLBACK_STANDARD_CHECKOUT = (
    "approved_standard_checkout_fallback_with_clear_disclosure_and_user_choice"
)


class BindingError(ValueError):
    """Raised for any context, transition, or attempt the contract forbids."""


def can_transition(from_state: str, to_state: str) -> bool:
    return to_state in TRANSITIONS.get(from_state, frozenset())


def _require_ref(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise BindingError("%s is required and must be a non-empty reference." % name)


def _require_structured_ref(name: str, value: object) -> None:
    _require_ref(name, value)
    if not _STRUCTURED_REF_RE.match(value):  # type: ignore[arg-type]
        raise BindingError(
            "%s must be a structured evidence reference (scheme-prefixed or "
            "separator-structured), not a bare assertion: %r" % (name, value)
        )


def _require_capability_evidence_ref(name: str, value: object) -> None:
    """F6: capability evidence must carry a recognized scheme prefix
    (EVIDENCE_REF_PREFIXES), not merely be separator-structured."""
    _require_ref(name, value)
    if not _CAPABILITY_EVIDENCE_RE.match(value):  # type: ignore[arg-type]
        raise BindingError(
            "%s must be an evidence reference with a recognized scheme "
            "prefix %s, not a bare or merely dashed/path-like string: %r"
            % (name, list(EVIDENCE_REF_PREFIXES), value)
        )


# ---------------------------------------------------------------------------
# Binding context (interface section 3 inputs)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BindingContext:
    """Everything one extra-offer presentation binds against.

    The parent purchase is referenced, never carried as mutable state:
    parent_order_ref plus the adapter verification source that proved it.
    capability_evidence_ref is REQUIRED (interface section 3): without
    recorded capability evidence there is nothing lawful to bind.
    recurring_terms is required iff billing_type == "recurring", and
    forbidden for one_time (mirrors adapter_common.render_disclosure).

    F2 repair (interface section 3, full list): launch_revision is the
    launch revision as its OWN field, distinct from launch_ref;
    copy_refs are the approved copy references for the offer and its
    disclosures (each a structured ref; the field must be stated -
    pass () explicitly when a presentation has no copy refs);
    disclosure_terms_ref is a structured ref to the offer's full
    disclosure data (discount/tax/shipping policy, trial, installments).
    The disclosure data itself lives in the adapters/pages layer; this
    binding records the reference so the presented terms are the terms
    the binding was made against.
    """

    tenant_ref: str
    location_ref: str
    launch_ref: str
    launch_revision: str
    parent_order_ref: str
    parent_verification_source: str
    offer_id: str
    native_product_ref: str
    native_price_ref: str
    capability_evidence_ref: str
    amount_minor: int
    currency: str
    success_route_ref: str
    decline_route_ref: str
    error_route_ref: str
    disclosure_terms_ref: str
    copy_refs: Tuple[str, ...]
    billing_type: str = "one_time"
    recurring_terms: Optional[Mapping] = None
    entry_context: Optional[str] = None

    def __post_init__(self) -> None:
        for name in (
            "tenant_ref",
            "location_ref",
            "launch_ref",
            "launch_revision",
            "parent_order_ref",
            "offer_id",
            "native_product_ref",
            "native_price_ref",
            "success_route_ref",
            "decline_route_ref",
            "error_route_ref",
        ):
            _require_ref(name, getattr(self, name))
        if self.launch_revision == self.launch_ref:
            raise BindingError(
                "launch_revision must be a distinct revision reference, "
                "not a repeat of launch_ref."
            )
        if self.parent_verification_source not in VERIFIED_SOURCES:
            raise BindingError(
                "parent_verification_source %r is not a verified adapter "
                "source %s; a client-side claim is never purchase proof."
                % (self.parent_verification_source, sorted(VERIFIED_SOURCES))
            )
        _require_capability_evidence_ref(
            "capability_evidence_ref", self.capability_evidence_ref
        )
        _require_structured_ref("disclosure_terms_ref", self.disclosure_terms_ref)
        if not isinstance(self.copy_refs, tuple):
            raise BindingError(
                "copy_refs must be a tuple of approved copy references "
                "(pass () explicitly when there are none)."
            )
        for ref in self.copy_refs:
            _require_structured_ref("copy_refs entry", ref)
        if type(self.amount_minor) is not int or self.amount_minor < 0:
            raise BindingError("amount_minor must be a non-negative integer (minor units).")
        if not _CURRENCY_RE.match(self.currency or ""):
            raise BindingError("currency must be a three-letter uppercase code.")
        if self.billing_type not in BILLING_TYPES:
            raise BindingError("billing_type must be one of %s." % sorted(BILLING_TYPES))
        if self.billing_type == "recurring":
            if not isinstance(self.recurring_terms, Mapping) or not self.recurring_terms:
                raise BindingError(
                    "billing_type 'recurring' requires recurring_terms so the "
                    "obligation can be disclosed before authorization."
                )
        elif self.recurring_terms is not None:
            raise BindingError("A one_time binding must not carry recurring terms.")
        if self.entry_context is not None and self.entry_context not in ENTRY_CONTEXTS:
            raise BindingError(
                "entry_context must be one of %s (verified journey state), "
                "or None." % sorted(ENTRY_CONTEXTS)
            )


# ---------------------------------------------------------------------------
# Native driver boundary (implemented by S06 in production; fixture in tests)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NativeResult:
    state: str
    native_txn_ref: Optional[str] = None
    failure_kind: Optional[str] = None

    def __post_init__(self) -> None:
        if self.state not in PURCHASE_STATES:
            raise BindingError("NativeResult state %r is not in the doc 09 section 8 vocabulary." % (self.state,))


class NativeDriver(Protocol):
    """The native side of the binding. How a verified native success is
    surfaced (synchronous result, read-back, or both) is open question
    S06-Q1; this binding therefore treats read_back as mandatory proof
    and never trusts a bare invoke result of paid."""

    def invoke(self, context: BindingContext, idempotency_key: str) -> NativeResult:
        ...

    def read_back(self, context: BindingContext, native_txn_ref: Optional[str]) -> NativeResult:
        ...


# ---------------------------------------------------------------------------
# Outcomes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PresentationDecision:
    one_click_offered: bool
    capability: Optional[bool]
    route: str  # "one_click" | "one_click_disabled"
    fallback_required: bool
    fallback: Optional[str]
    reason: str
    open_question_ref: Optional[str]


@dataclass(frozen=True)
class AttemptOutcome:
    action: str  # "accept" | "decline" | "reconcile"
    state: str
    route_ref: Optional[str]
    native_txn_ref: Optional[str]
    failure_kind: Optional[str]
    read_back_confirmed: bool
    attempt_number: int
    idempotency_key: Optional[str]
    parent_purchase_unaffected: bool
    parent_state_observed: object


# ---------------------------------------------------------------------------
# Open interface questions (interface section 7) - unresolved, never invented
# ---------------------------------------------------------------------------

OPEN_QUESTIONS = (
    {"id": "S06-Q1", "owner": "S06", "status": "unresolved",
     "text": "What are the exact native element and event names for the one-click extra-offer action in the current Skill 06 builder, and how is a verified native success for an extra purchase surfaced to the caller (synchronous result, native read-back, or both)?"},
    {"id": "S06-Q2", "owner": "S06", "status": "unresolved",
     "text": "How is capability evidence represented per payment method and billing type (the doc 05 section 3 environment-capabilities.json shape, a per-form record, or another artifact), and who signs it?"},
    {"id": "S06-Q3", "owner": "S06", "status": "unresolved",
     "text": "What exactly may the wrapper style or configure for extra-offer native elements, per the doc 16 section 6 native-element styling map, and which properties are native-theme-only?"},
    {"id": "S06-Q4", "owner": "S06", "status": "unresolved",
     "text": "How are decline, error and pending destinations for an extra offer configured in the native funnel, and can they be set per offer or only per funnel step?"},
    {"id": "S06-Q5", "owner": "S06", "status": "unresolved",
     "text": "When one-click is unsupported for the buyer's payment method, what is the approved standard-checkout fallback flow S06 installs, and where is the required disclosure shown?"},
    {"id": "S06-Q6", "owner": "S06", "status": "unresolved",
     "text": "Does the native session context impose an expiry on extra-offer eligibility after the initial purchase, and how is expiry surfaced?"},
    {"id": "S44-Q7", "owner": "S44", "status": "unresolved",
     "text": "What field links an extra-purchase event to its parent initial order, and does S44 want extra events on the same normalized purchase-event schema as the initial event or a sibling schema?"},
    {"id": "S44-Q8", "owner": "S44", "status": "unresolved",
     "text": "Which extra-offer outcomes must S44 record for refund/chargeback handling, and in what shape?"},
    {"id": "S49-Q9", "owner": "S49", "status": "unresolved",
     "text": "Are decline-then-downsell chains (S80 decline routing to S81) approved per launch in the route plan, and where is that approval recorded so this interface can check it instead of assuming it?"},
)

OPEN_QUESTION_IDS = [q["id"] for q in OPEN_QUESTIONS]


# ---------------------------------------------------------------------------
# The binding
# ---------------------------------------------------------------------------


class ExtraOfferBinding:
    """One extra offer bound to one verified parent purchase.

    The parent purchase is held as a read-only observation only: the
    binding snapshots it (deep copy) at construction and re-observes it
    for each outcome; it exposes no method that mutates it, and no code
    path here writes to it (interface section 6 no-rollback).
    """

    def __init__(self, context: BindingContext, parent_purchase: object = None,
                 guard: Optional[PaymentAttemptGuard] = None) -> None:
        """guard (F4 repair): an optional pre-built single-flight guard.
        Default None composes the binding's own PaymentAttemptGuard,
        exactly as before; integrators/tests may inject one (e.g. an
        already-held guard) to isolate guard behavior. If the guard
        refuses an attempt it raises routing_state.RouteError, which
        propagates out of accept() unchanged - integrators must expect
        BOTH BindingError and RouteError from this API."""
        if not isinstance(context, BindingContext):
            raise BindingError("ExtraOfferBinding requires a BindingContext.")
        self._context = context
        self._parent_purchase = parent_purchase
        self._parent_snapshot = copy.deepcopy(parent_purchase)
        self._state = READY
        self._guard = guard if guard is not None else PaymentAttemptGuard()
        self._attempts: List[AttemptOutcome] = []
        self._attempt_count = 0
        self._unresolved = False
        self._declined = False
        self._last_txn_ref: Optional[str] = None
        self._presentation: Optional[PresentationDecision] = None

    # -- read-only views ----------------------------------------------------

    @property
    def context(self) -> BindingContext:
        return self._context

    @property
    def state(self) -> str:
        return self._state

    @property
    def attempts(self) -> Tuple[AttemptOutcome, ...]:
        return tuple(self._attempts)

    @property
    def unresolved(self) -> bool:
        return self._unresolved

    # -- internals ----------------------------------------------------------

    def _transition(self, to_state: str) -> None:
        if not can_transition(self._state, to_state):
            raise BindingError(
                "Illegal purchase-state transition %s -> %s." % (self._state, to_state)
            )
        self._state = to_state

    def _parent_observed(self) -> object:
        return copy.deepcopy(self._parent_purchase)

    def _parent_unaffected(self) -> bool:
        return self._parent_snapshot == self._parent_purchase

    def _idempotency_key(self, attempt_number: int) -> str:
        material = "|".join(
            [
                self._context.tenant_ref,
                self._context.location_ref,
                self._context.launch_ref,
                self._context.parent_order_ref,
                self._context.offer_id,
                self._context.native_product_ref,
                self._context.native_price_ref,
                str(attempt_number),
            ]
        )
        return "s80-binding-%s-a%d" % (hashlib.sha256(material.encode("utf-8")).hexdigest()[:16], attempt_number)

    def _outcome(self, action: str, state: str, route_ref: Optional[str],
                 native_txn_ref: Optional[str], failure_kind: Optional[str],
                 read_back_confirmed: bool, attempt_number: int,
                 idempotency_key: Optional[str]) -> AttemptOutcome:
        outcome = AttemptOutcome(
            action=action,
            state=state,
            route_ref=route_ref,
            native_txn_ref=native_txn_ref,
            failure_kind=failure_kind,
            read_back_confirmed=read_back_confirmed,
            attempt_number=attempt_number,
            idempotency_key=idempotency_key,
            parent_purchase_unaffected=self._parent_unaffected(),
            parent_state_observed=self._parent_observed(),
        )
        self._attempts.append(outcome)
        return outcome

    def _route_for(self, state: str) -> Optional[str]:
        if state == PAID:
            return self._context.success_route_ref
        return self._context.error_route_ref

    # -- presentation (interface section 5) ---------------------------------

    def presentation_decision(self, capability: Optional[bool]) -> PresentationDecision:
        """Decide whether the one-click route may be offered.

        capability is the recorded one-click support for the selected
        native form / payment method / billing type: True, False, or
        None (unknown). Unknown is never assumed supported: False and
        None both DISABLE the one-click route and record the
        approved-fallback requirement (interface section 5; the approved
        fallback flow itself is open question S06-Q5).
        """
        if capability is not None and type(capability) is not bool:
            raise BindingError("capability must be True, False, or None (unknown).")
        if capability is True:
            decision = PresentationDecision(
                one_click_offered=True,
                capability=True,
                route="one_click",
                fallback_required=False,
                fallback=None,
                reason="one-click support is verified by capability evidence",
                open_question_ref=None,
            )
        else:
            reason = (
                "one-click support is recorded unsupported for this payment "
                "method/billing type"
                if capability is False
                else "one-click support is unknown; unknown capability is "
                "never assumed supported"
            )
            decision = PresentationDecision(
                one_click_offered=False,
                capability=capability,
                route="one_click_disabled",
                fallback_required=True,
                fallback=FALLBACK_STANDARD_CHECKOUT,
                reason=reason,
                open_question_ref="S06-Q5",
            )
        self._presentation = decision
        return decision

    # -- accept (interface sections 4 and 6; spec 10 section 6) -------------

    def accept(self, driver: NativeDriver) -> AttemptOutcome:
        """Attempt the guarded native one-click purchase, single-flight.

        Requires a recorded presentation decision that offered
        one-click (F1 repair: the capability gate is enforced here,
        not left to caller discipline). Only a driver result of paid
        CONFIRMED BY read_back counts as paid; a bare invoke paid
        without read-back confirmation yields pending_confirmation.
        An invoke that raises is an UNKNOWN outcome: the attempt
        becomes unresolved and no retry is allowed until reconcile()
        resolves it against native records.
        """
        if self._unresolved:
            raise BindingError(
                "A prior attempt's outcome is unknown; retry is refused "
                "until reconcile() resolves it against native records "
                "(unknown-outcome discipline, interface section 6)."
            )
        if self._declined:
            raise BindingError(
                "This presentation was declined; decline is terminal for "
                "the binding instance (F7 repair). A fresh presentation "
                "requires a fresh binding."
            )
        if self._presentation is None:
            raise BindingError(
                "No presentation decision has been recorded on this "
                "binding; the capability gate is binding-enforced (F1 "
                "repair): call presentation_decision() first so one-click "
                "support is decided from capability evidence before any "
                "accept is attempted."
            )
        if not self._presentation.one_click_offered:
            raise BindingError(
                "The one-click route is disabled for this presentation "
                "(capability not verified); use the approved fallback "
                "recorded in the presentation decision instead."
            )
        if self._state == PAID:
            raise BindingError("This extra offer is already paid; no duplicate charge.")
        if self._state not in (READY, FAILED, REQUIRES_CUSTOMER_ACTION):
            raise BindingError(
                "accept() cannot start from purchase state %r." % (self._state,)
            )
        self._guard.begin_attempt()
        self._attempt_count += 1
        attempt_number = self._attempt_count
        key = self._idempotency_key(attempt_number)
        try:
            if self._state == REQUIRES_CUSTOMER_ACTION:
                self._transition(SUBMITTING)
            else:
                self._transition(VALIDATING)
                self._transition(SUBMITTING)
            try:
                result = driver.invoke(self._context, key)
            except Exception:
                # Unknown outcome: the charge may or may not exist. Never
                # call it failed, never retry blind - reconcile first.
                self._transition(PENDING_CONFIRMATION)
                self._unresolved = True
                return self._outcome(
                    "accept", PENDING_CONFIRMATION, self._context.error_route_ref,
                    self._last_txn_ref, "unknown_outcome", False, attempt_number, key,
                )
            if result.native_txn_ref is not None:
                self._last_txn_ref = result.native_txn_ref
            return self._settle("accept", result, attempt_number, key, driver)
        finally:
            if self._guard.state == PaymentAttemptGuard.PROCESSING:
                self._guard.release_attempt()

    def _settle(self, action: str, result: NativeResult, attempt_number: int,
                key: Optional[str], driver: Optional[NativeDriver],
                *, confirmed: bool = False) -> AttemptOutcome:
        """Settle a driver result; paid is only ever settled by read-back.

        confirmed=True (F8 repair) means `result` IS itself a read-back
        result (reconcile passes its read-back straight in), so it is
        its own confirmation and no second read-back is performed. The
        invariant is unchanged: a paid settle still requires a result
        that came from read_back, never a bare invoke result.
        """
        if result.state == PAID:
            if confirmed:
                confirmation = result
            else:
                if driver is None:
                    raise BindingError("A paid result cannot be settled without read-back.")
                confirmation = driver.read_back(self._context, result.native_txn_ref)
            if confirmation.state == PAID:
                if self._state != PAID:
                    self._transition(PAID)
                self._unresolved = False
                txn = confirmation.native_txn_ref or result.native_txn_ref
                self._last_txn_ref = txn
                return self._outcome(
                    action, PAID, self._context.success_route_ref, txn, None,
                    True, attempt_number, key,
                )
            # Invoke claimed paid but native records do not confirm it:
            # not paid, and not a known failure either - unresolved.
            if self._state != PENDING_CONFIRMATION:
                self._transition(PENDING_CONFIRMATION)
            self._unresolved = True
            return self._outcome(
                action, PENDING_CONFIRMATION, self._context.error_route_ref,
                result.native_txn_ref, "paid_not_confirmed_by_readback",
                False, attempt_number, key,
            )
        if result.state in (READY, VALIDATING, SUBMITTING, PENDING_CONFIRMATION):
            if self._state != PENDING_CONFIRMATION:
                self._transition(PENDING_CONFIRMATION)
            self._unresolved = True
            return self._outcome(
                action, PENDING_CONFIRMATION, self._context.error_route_ref,
                result.native_txn_ref, result.failure_kind, False,
                attempt_number, key,
            )
        # Definitive non-paid outcomes: failed / requires_customer_action /
        # cancelled. The outcome is KNOWN, so the attempt is resolved.
        if self._state != result.state:
            self._transition(result.state)
        self._unresolved = False
        return self._outcome(
            action, result.state, self._route_for(result.state),
            result.native_txn_ref, result.failure_kind, False,
            attempt_number, key,
        )

    # -- decline (interface section 5; spec 10 section 6) --------------------

    def decline(self) -> AttemptOutcome:
        """Decline is a normal routed outcome: no driver call, no charge,
        and the parent purchase is untouched. Decline is TERMINAL for
        this binding instance (F7 repair): after decline(), accept()
        raises BindingError and a second decline() raises BindingError;
        a fresh presentation requires a fresh binding."""
        if self._unresolved:
            raise BindingError(
                "A prior attempt's outcome is unknown; reconcile() before "
                "routing onward, so a possibly-paid attempt is never "
                "recorded as a decline."
            )
        if self._state == PAID:
            raise BindingError("A paid extra offer cannot be declined after the fact.")
        if self._declined:
            raise BindingError(
                "This presentation was already declined; decline is "
                "terminal for the binding instance (F7 repair)."
            )
        self._declined = True
        return self._outcome(
            "decline", self._state, self._context.decline_route_ref, None,
            None, False, self._attempt_count, None,
        )

    # -- reconcile (interface section 6: read-back FIRST) --------------------

    def reconcile(self, driver: NativeDriver) -> AttemptOutcome:
        """Resolve an unknown/pending outcome against native records.

        Read-back happens FIRST; only its result may settle the attempt.
        Until reconcile resolves the attempt, accept() retries stay
        refused.
        """
        if not self._attempts and self._state == READY:
            raise BindingError("No attempt exists to reconcile.")
        result = driver.read_back(self._context, self._last_txn_ref)
        if result.native_txn_ref is not None:
            self._last_txn_ref = result.native_txn_ref
        # F8: the read-back above IS the confirmation; pass it into the
        # settle path so a paid reconcile performs exactly one read-back.
        return self._settle(
            "reconcile", result, self._attempt_count, None, driver,
            confirmed=True,
        )

    # -- integration record (parallel worker depends on this exact shape) ---

    def binding_record(self) -> dict:
        return {
            "kind": "extra_offer_binding",
            "interface_ref": INTERFACE_REF,
            "binding_status": BINDING_STATUS,
            "native_action_id": None,
            "capability_evidence_ref": self._context.capability_evidence_ref,
            "open_questions": list(OPEN_QUESTION_IDS),
        }
