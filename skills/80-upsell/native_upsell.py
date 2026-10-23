"""Native upsell/downsell actions for GHL delivery — Skills 80/81 (stream W8, W8B).

Configuration/execution contract for the native extra-offer actions on the
Signature Launch chain: Upsell 1 (U1), Downsell 1 (D1) and the single
canonical Upsell 2 (U2). Governing sources:

  * GHL-DELIVERY-SPEC.md, "Commerce (W8) — native reality, no counterfeit
    controls": preserve native purchase context; bind accept/decline/
    failure/confirmation correctly; the documented native one-click upsell
    flow is V2-Funnel-ONLY (websites route purchases into a supported V2
    purchase funnel); verify checkout family, processor/payment mode,
    domain continuity, quantity/product constraints; reconcile
    pending/unknown payments from authoritative state; NEVER grant access
    from a front-end click alone; NO raw card collection/storage, token
    copying, replayed charges, or simulated payment success.
  * 81-signature-downsell/references/native-action-states.md: action
    states, entry guards, decline/abandon semantics.
  * 80-signature-upsell/components/binding/extra_offer_binding.py and
    adapters/routing_state.py: the shared purchase-state vocabulary
    (doc 09 section 8) and the route law this module binds actions to.
    This module performs NO charges and no network calls; the native side
    is supplied by the caller as a driver, exactly as the shared component
    does. It copies no charge implementation.

Fail closed everywhere: a client-side claim is never purchase proof, an
unknown capability is never assumed supported, a timeout is never a
decline, and a paid outcome settles only when authoritative native
read-back confirms it.

Run the assert-based self-check:

    python3 -I skills/80-upsell/native_upsell.py
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Mapping, Optional, Protocol, Tuple

__all__ = [
    "UpsellContractError",
    "PURCHASE_STATES",
    "TRANSITIONS",
    "can_transition",
    "VERIFIED_PURCHASE_SOURCES",
    "ENTRY_CONTEXTS",
    "ROLES",
    "OUTCOMES",
    "ONE_CLICK_CHECKOUT_FAMILY",
    "CHECKOUT_FAMILIES",
    "PurchaseEvidence",
    "Journey",
    "LaunchFlags",
    "PurchaseContext",
    "PlatformReport",
    "RouteDecision",
    "AttemptOutcome",
    "NativeDriver",
    "NativeUpsellAction",
    "validate_launch_flags",
    "check_entry",
    "resolve_next",
    "verify_platform",
    "one_click_allowed",
    "check_domain_continuity",
    "assert_no_card_data",
]


# ---------------------------------------------------------------------------
# Errors and shared vocabulary
# ---------------------------------------------------------------------------


class UpsellContractError(ValueError):
    """Raised for any context, transition, guard or attempt the contract forbids."""


# Purchase-state vocabulary: doc 09 section 8, identical to the shared
# extra-offer component (80-signature-upsell/components/binding). paid and
# cancelled are terminal. failed may start a NEW attempt (validating) only
# after its outcome is known — an attempt whose outcome is unknown sits in
# pending_confirmation and cannot restart until reconcile resolves it.
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

TRANSITIONS = {
    READY: frozenset({VALIDATING, CANCELLED}),
    VALIDATING: frozenset({SUBMITTING, FAILED, CANCELLED}),
    SUBMITTING: frozenset(
        {PENDING_CONFIRMATION, PAID, FAILED, REQUIRES_CUSTOMER_ACTION, CANCELLED}
    ),
    PENDING_CONFIRMATION: frozenset({PAID, FAILED, REQUIRES_CUSTOMER_ACTION, CANCELLED}),
    REQUIRES_CUSTOMER_ACTION: frozenset({SUBMITTING, FAILED, CANCELLED}),
    FAILED: frozenset({VALIDATING}),
    PAID: frozenset(),
    CANCELLED: frozenset(),
}


def can_transition(from_state: str, to_state: str) -> bool:
    return to_state in TRANSITIONS.get(from_state, frozenset())


# Verified purchase evidence sources (adapter_common.ADAPTER_VERIFICATION_SOURCES).
# A client-side claim such as acceptedU1=true is NEVER in this set.
VERIFIED_PURCHASE_SOURCES = frozenset(
    {"native_purchase_ledger", "provider_event_readback", "s44_event_adapter"}
)

ENTRY_CONTEXTS = frozenset({"from_upsell_1", "from_downsell_1"})

ROLES = ("upsell_1", "downsell_1", "upsell_2")

# Action/route outcomes bound per role (accept/decline/failure/confirmation).
ACCEPT = "accept"
EXPLICIT_DECLINE = "explicit_decline"
FAILURE = "failure"
PENDING = "pending"
UNKNOWN_OUTCOME = "unknown_outcome"
ABANDONED = "abandoned"
CONFIRMATION = "confirmation"

OUTCOMES = (ACCEPT, EXPLICIT_DECLINE, FAILURE, PENDING, UNKNOWN_OUTCOME, ABANDONED, CONFIRMATION)

# Route destinations.
THANK_YOU = "thank_you"
SAME_U2 = "upsell_2"
STAY_RECOVER = "stay_recoverable"

# The documented native one-click upsell flow is V2-Funnel-ONLY. Websites
# route purchases into a supported V2 purchase funnel instead.
ONE_CLICK_CHECKOUT_FAMILY = "v2_funnel"
CHECKOUT_FAMILIES = frozenset({"v2_funnel", "website"})
WEBSITE_PURCHASE_ROUTE = "route_purchase_into_supported_v2_purchase_funnel"
FALLBACK_STANDARD_CHECKOUT = (
    "approved_standard_checkout_fallback_with_clear_disclosure_and_user_choice"
)

BILLING_TYPES = frozenset({"one_time", "recurring"})

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")
_STRUCTURED_REF_RE = re.compile(
    r"^(?:[a-z][a-z0-9+.-]*:[^\s]+|[^\s]+[/][^\s]+|[^\s]+-[^\s]+)$"
)
_CAPABILITY_EVIDENCE_RE = re.compile(
    r"^(?:native|ledger|provider-event|s44|catalog|request|graph):[^\s]+$"
    r"|^https://[^\s]+$"
)

# Raw card data is refused at the contract boundary. No card collection,
# no token copying, no replayed charges — this module never sees PAN data.
_FORBIDDEN_CARD_KEY_RE = re.compile(
    r"(?:^|[_\-\s])(?:pan|card[_\-]?number|cardnumber|cvc|cvv|cid|security[_\-]?code|"
    r"exp(?:iry|iration)?[_\-]?(?:month|year|date|mm|yy|yyyy)?|track[12]|magstripe|"
    r"iban|routing[_\-]?number|account[_\-]?number)(?:$|[_\-\s])",
    re.IGNORECASE,
)


def assert_no_card_data(payload: object, _path: str = "payload") -> None:
    """Refuse any raw card/bank credential material in a request payload."""
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if _FORBIDDEN_CARD_KEY_RE.search(str(key)):
                raise UpsellContractError(
                    "Raw card/credential field %r at %s is refused: no raw card "
                    "collection, storage, token copying or replayed charges."
                    % (key, _path)
                )
            assert_no_card_data(value, "%s.%s" % (_path, key))
    elif isinstance(payload, (list, tuple)):
        for i, item in enumerate(payload):
            assert_no_card_data(item, "%s[%d]" % (_path, i))


def _require_ref(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise UpsellContractError("%s is required and must be a non-empty reference." % name)


def _require_structured_ref(name: str, value: object) -> None:
    _require_ref(name, value)
    if not _STRUCTURED_REF_RE.match(value):  # type: ignore[arg-type]
        raise UpsellContractError(
            "%s must be a structured evidence reference, not a bare assertion: %r"
            % (name, value)
        )


def _require_capability_evidence_ref(name: str, value: object) -> None:
    _require_ref(name, value)
    if not _CAPABILITY_EVIDENCE_RE.match(value):  # type: ignore[arg-type]
        raise UpsellContractError(
            "%s must carry a recognized evidence scheme prefix "
            "(native:/ledger:/provider-event:/s44:/catalog:/request:/graph:/https://): %r"
            % (name, value)
        )


# ---------------------------------------------------------------------------
# Purchase context (the context is preserved; the parent purchase is read-only)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PurchaseEvidence:
    """One verified purchase record. A client-side claim is never accepted."""

    evidence_ref: str
    verification_source: str

    def __post_init__(self) -> None:
        _require_structured_ref("evidence_ref", self.evidence_ref)
        if self.verification_source not in VERIFIED_PURCHASE_SOURCES:
            raise UpsellContractError(
                "verification_source %r is not a verified source %s; a client-side "
                "claim is never purchase proof."
                % (self.verification_source, sorted(VERIFIED_PURCHASE_SOURCES))
            )


@dataclass(frozen=True)
class Journey:
    """Verified journey facts the entry guards read (never page-load claims)."""

    main_purchase: Optional[PurchaseEvidence] = None
    u1_event: Optional[str] = None  # "purchased" | "explicit_decline" | "failure" | "pending" | None
    u1_purchase: Optional[PurchaseEvidence] = None
    d1_purchase: Optional[PurchaseEvidence] = None
    u2_product_already_owned: bool = False

    def __post_init__(self) -> None:
        if self.u1_event is not None and self.u1_event not in (
            "purchased",
            "explicit_decline",
            "failure",
            "pending",
        ):
            raise UpsellContractError("u1_event %r is not a known U1 outcome." % (self.u1_event,))
        if self.u1_purchase is not None and self.u1_event != "purchased":
            raise UpsellContractError(
                "u1_purchase evidence requires u1_event 'purchased'; a failed or "
                "pending U1 payment is never a purchase."
            )


@dataclass(frozen=True)
class LaunchFlags:
    """Launch-level enablement (route law inputs, not journey facts)."""

    u1_enabled: bool
    d1_enabled: bool
    u2_enabled: bool

    def __post_init__(self) -> None:
        for name in ("u1_enabled", "d1_enabled", "u2_enabled"):
            if type(getattr(self, name)) is not bool:
                raise UpsellContractError("%s must be a bool." % name)


def validate_launch_flags(launch: LaunchFlags) -> None:
    """Route law: when U1 is disabled, D1 and U2 cannot remain enabled."""
    if not launch.u1_enabled and (launch.d1_enabled or launch.u2_enabled):
        raise UpsellContractError(
            "Route law violated: U1 disabled means D1 and U2 cannot remain enabled."
        )


@dataclass(frozen=True)
class PurchaseContext:
    """Everything one native upsell/downsell action binds against.

    The parent purchase is referenced, never carried as mutable state:
    parent_order_ref plus the verified source that proved it. The action
    layer never mutates parent state (no-rollback): fulfillment of the
    original order (main plus any bump) is untouched by every outcome.
    """

    tenant_ref: str
    location_ref: str
    launch_ref: str
    launch_revision: str
    parent_order_ref: str
    parent_verification_source: str
    role: str
    offer_id: str
    native_product_ref: str
    native_price_ref: str
    capability_evidence_ref: str
    disclosure_terms_ref: str
    amount_minor: int
    currency: str
    success_route_ref: str
    decline_route_ref: str
    failure_route_ref: str
    confirmation_route_ref: str
    checkout_family: str
    processor_ref: str
    payment_mode: str
    domain_ref: str
    quantity: int = 1
    max_quantity: Optional[int] = None
    billing_type: str = "one_time"
    recurring_terms: Optional[Mapping] = None
    entry_context: Optional[str] = None
    extras: Mapping = field(default_factory=dict)

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
            "failure_route_ref",
            "confirmation_route_ref",
            "processor_ref",
            "payment_mode",
            "domain_ref",
        ):
            _require_ref(name, getattr(self, name))
        if self.launch_revision == self.launch_ref:
            raise UpsellContractError(
                "launch_revision must be a distinct revision reference, not a repeat of launch_ref."
            )
        if self.role not in ROLES:
            raise UpsellContractError("role must be one of %s." % (ROLES,))
        if self.parent_verification_source not in VERIFIED_PURCHASE_SOURCES:
            raise UpsellContractError(
                "parent_verification_source %r is not a verified source %s; the "
                "purchase context is preserved only on verified purchase evidence."
                % (self.parent_verification_source, sorted(VERIFIED_PURCHASE_SOURCES))
            )
        _require_capability_evidence_ref("capability_evidence_ref", self.capability_evidence_ref)
        _require_structured_ref("disclosure_terms_ref", self.disclosure_terms_ref)
        if type(self.amount_minor) is not int or self.amount_minor < 0:
            raise UpsellContractError("amount_minor must be a non-negative integer (minor units).")
        if not _CURRENCY_RE.match(self.currency or ""):
            raise UpsellContractError("currency must be a three-letter uppercase code.")
        if self.checkout_family not in CHECKOUT_FAMILIES:
            raise UpsellContractError(
                "checkout_family must be one of %s." % sorted(CHECKOUT_FAMILIES)
            )
        if type(self.quantity) is not int or self.quantity < 1:
            raise UpsellContractError("quantity must be an integer >= 1.")
        if self.max_quantity is not None and (
            type(self.max_quantity) is not int or self.max_quantity < 1
        ):
            raise UpsellContractError("max_quantity must be an integer >= 1 when set.")
        if self.max_quantity is not None and self.quantity > self.max_quantity:
            raise UpsellContractError(
                "quantity/product constraint violated: quantity %d exceeds max_quantity %d."
                % (self.quantity, self.max_quantity)
            )
        if self.billing_type not in BILLING_TYPES:
            raise UpsellContractError("billing_type must be one of %s." % sorted(BILLING_TYPES))
        if self.billing_type == "recurring":
            if not isinstance(self.recurring_terms, Mapping) or not self.recurring_terms:
                raise UpsellContractError(
                    "billing_type 'recurring' requires recurring_terms so the "
                    "obligation can be disclosed before authorization."
                )
        elif self.recurring_terms is not None:
            raise UpsellContractError("A one_time action must not carry recurring terms.")
        if self.entry_context is not None and self.entry_context not in ENTRY_CONTEXTS:
            raise UpsellContractError(
                "entry_context must be one of %s (verified journey state), or None."
                % sorted(ENTRY_CONTEXTS)
            )
        assert_no_card_data(dict(self.extras), "extras")


# ---------------------------------------------------------------------------
# Platform verification (checkout family, processor/payment mode,
# domain continuity, quantity/product constraints)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlatformReport:
    checkout_family: str
    one_click_supported: bool
    fallback_required: bool
    fallback: Optional[str]
    reason: str


def one_click_allowed(context: PurchaseContext, capability: Optional[bool]) -> PlatformReport:
    """Decide whether the native V2 one-click route may be offered.

    The documented native one-click upsell flow is V2-Funnel-ONLY: a
    website context never gets one-click; its purchases route into a
    supported V2 purchase funnel. capability True/False/None is the
    recorded support for the processor/payment mode; unknown is never
    assumed supported.
    """
    if capability is not None and type(capability) is not bool:
        raise UpsellContractError("capability must be True, False, or None (unknown).")
    if context.checkout_family != ONE_CLICK_CHECKOUT_FAMILY:
        return PlatformReport(
            checkout_family=context.checkout_family,
            one_click_supported=False,
            fallback_required=True,
            fallback=WEBSITE_PURCHASE_ROUTE,
            reason="V2 one-click upsell is Funnel-only; website purchases route "
            "into a supported V2 purchase funnel",
        )
    if capability is True:
        return PlatformReport(
            checkout_family=context.checkout_family,
            one_click_supported=True,
            fallback_required=False,
            fallback=None,
            reason="one-click support verified for processor/payment mode by "
            "capability evidence",
        )
    reason = (
        "one-click support is recorded unsupported for processor %r / payment mode %r"
        % (context.processor_ref, context.payment_mode)
        if capability is False
        else "one-click support is unknown; unknown capability is never assumed supported"
    )
    return PlatformReport(
        checkout_family=context.checkout_family,
        one_click_supported=False,
        fallback_required=True,
        fallback=FALLBACK_STANDARD_CHECKOUT,
        reason=reason,
    )


def check_domain_continuity(context: PurchaseContext, page_domain_ref: str) -> None:
    """Domain continuity: the offer page must live on the purchase domain."""
    _require_ref("page_domain_ref", page_domain_ref)
    if page_domain_ref != context.domain_ref:
        raise UpsellContractError(
            "Domain continuity violated: offer page domain %r is not the purchase "
            "context domain %r; the native purchase context is not preserved."
            % (page_domain_ref, context.domain_ref)
        )


def verify_platform(context: PurchaseContext, page_domain_ref: str) -> PlatformReport:
    """Full platform verification before any action is attempted.

    Verifies checkout family, processor/payment mode capability evidence,
    domain continuity and quantity/product constraints (already enforced
    at context construction). Fail closed on every violation.
    """
    check_domain_continuity(context, page_domain_ref)
    if context.native_product_ref == context.native_price_ref:
        raise UpsellContractError(
            "Product/price constraint violated: native_product_ref and "
            "native_price_ref must be distinct bindings (catalog creation alone "
            "is not checkout binding)."
        )
    if type(context.amount_minor) is not int or context.amount_minor < 0:
        raise UpsellContractError("amount_minor must be a non-negative integer.")
    return one_click_allowed(context, capability=None)


# ---------------------------------------------------------------------------
# Entry guards (81 native-action-states.md entry guards; 80 U2 eligibility)
# ---------------------------------------------------------------------------


def check_entry(role: str, journey: Journey, launch: LaunchFlags) -> None:
    """Entry guards for U1 / D1 / U2. Refuse and route safely on violation."""
    if role not in ROLES:
        raise UpsellContractError("role must be one of %s." % (ROLES,))
    validate_launch_flags(launch)
    if journey.main_purchase is None:
        raise UpsellContractError(
            "Entry refused (%s): no verified original purchase. Direct access "
            "without an eligible original purchase is refused." % role
        )
    if role == "upsell_1":
        if not launch.u1_enabled:
            raise UpsellContractError("Entry refused: upsell_1 is not enabled.")
        return
    if role == "downsell_1":
        if not launch.u1_enabled or not launch.d1_enabled:
            raise UpsellContractError("Entry refused: downsell_1 requires enabled U1 and D1.")
        # D1 renders only after an EXPLICIT U1 decline. A failed or pending
        # U1 payment is neither acceptance nor decline and never routes to D1
        # as a decline. An accepted U1 buyer is mutually exclusive with D1.
        if journey.u1_event != "explicit_decline":
            raise UpsellContractError(
                "Entry refused (downsell_1): u1_event %r is not an explicit "
                "decline; a failed or pending U1 payment never qualifies."
                % (journey.u1_event,)
            )
        if journey.u1_purchase is not None:
            raise UpsellContractError(
                "Entry refused (downsell_1): U1 was accepted; U1 and D1 are "
                "mutually exclusive."
            )
        return
    # upsell_2
    if not launch.u2_enabled:
        raise UpsellContractError("Entry refused: upsell_2 is not enabled.")
    # U2 is offered after a VERIFIED accepted U1 or D1 purchase. A bump
    # alone never qualifies for U2 and a client-side claim is never proof.
    if journey.u1_purchase is None and journey.d1_purchase is None:
        raise UpsellContractError(
            "Entry refused (upsell_2): no verified accepted U1 or D1 purchase; "
            "a bump alone never qualifies and a client-side claim is never proof."
        )
    if journey.u2_product_already_owned:
        raise UpsellContractError(
            "Entry refused (upsell_2): the buyer already owns this product; "
            "no duplicate purchase is offered."
        )


# ---------------------------------------------------------------------------
# Route resolution: accept / decline / failure / confirmation edges
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RouteDecision:
    destination: str
    entry_context: Optional[str]
    original_order_preserved: bool
    reason: str


def resolve_next(role: str, outcome: str, launch: LaunchFlags) -> RouteDecision:
    """Bind the next route for a role/outcome pair (route law, fail closed)."""
    if role not in ROLES:
        raise UpsellContractError("role must be one of %s." % (ROLES,))
    if outcome not in OUTCOMES:
        raise UpsellContractError("outcome must be one of %s." % (OUTCOMES,))
    validate_launch_flags(launch)
    preserved = True  # the original order (main plus any bump) is preserved on every branch
    if outcome == ABANDONED:
        # Abandonment is never recorded as a fabricated decline; base-order
        # fulfillment proceeds independently.
        return RouteDecision(
            "base_fulfillment_proceeds_independently", None, preserved,
            "abandonment is never a decline and never purchases anything",
        )
    if outcome == CONFIRMATION:
        return RouteDecision(THANK_YOU, None, preserved, "confirmation routes to thank-you")
    if outcome in (FAILURE, PENDING, UNKNOWN_OUTCOME):
        # A failure is NEVER recorded as acceptance or decline; pending and
        # unknown are neither. Stay recoverable; never traverse a decline edge.
        return RouteDecision(
            STAY_RECOVER, None, preserved,
            "%s is not an acceptance and not a decline; stay recoverable and "
            "reconcile unknown outcomes before any retry" % outcome,
        )
    if role == "upsell_1":
        if outcome == ACCEPT:
            if launch.u2_enabled:
                return RouteDecision(
                    SAME_U2, "from_upsell_1", preserved,
                    "accepted U1 routes to the SAME canonical U2 when enabled",
                )
            return RouteDecision(THANK_YOU, None, preserved, "U2 disabled after accepted U1")
        # explicit_decline
        if launch.d1_enabled:
            return RouteDecision(
                "downsell_1", None, preserved,
                "explicit U1 decline routes to D1 when enabled",
            )
        return RouteDecision(THANK_YOU, None, preserved, "D1 disabled after explicit U1 decline")
    if role == "downsell_1":
        if outcome == ACCEPT:
            if launch.u2_enabled:
                return RouteDecision(
                    SAME_U2, "from_downsell_1", preserved,
                    "paid D1 routes to the SAME canonical U2 when enabled; never "
                    "a D1-specific duplicate U2",
                )
            return RouteDecision(THANK_YOU, None, preserved, "U2 disabled after paid D1")
        return RouteDecision(
            THANK_YOU, None, preserved,
            "explicit D1 decline routes to final thank-you; no charge and no "
            "removal of existing access",
        )
    # upsell_2 terminal: accept or explicit decline both end at confirmation.
    return RouteDecision(
        THANK_YOU, None, preserved,
        "U2 is the final extra offer; %s routes to the final thank-you" % outcome,
    )


# ---------------------------------------------------------------------------
# Transaction-state handling (single-flight; paid only from verified evidence)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NativeResult:
    state: str
    native_txn_ref: Optional[str] = None
    failure_kind: Optional[str] = None

    def __post_init__(self) -> None:
        if self.state not in PURCHASE_STATES:
            raise UpsellContractError(
                "NativeResult state %r is not in the purchase-state vocabulary." % (self.state,)
            )
        if self.state == PAID and not self.native_txn_ref:
            raise UpsellContractError(
                "A paid result must carry a native transaction reference; "
                "simulated payment success is refused."
            )


class NativeDriver(Protocol):
    """The native side of the action (installed binding; supplied by caller)."""

    def invoke(self, context: PurchaseContext, idempotency_key: str) -> NativeResult:
        ...

    def read_back(self, context: PurchaseContext, native_txn_ref: Optional[str]) -> NativeResult:
        ...


@dataclass(frozen=True)
class AttemptOutcome:
    action: str  # "accept" | "decline" | "reconcile" | "abandon"
    state: str
    route_ref: Optional[str]
    native_txn_ref: Optional[str]
    failure_kind: Optional[str]
    read_back_confirmed: bool
    attempt_number: int
    idempotency_key: Optional[str]
    parent_purchase_unaffected: bool
    entitlement_granted: bool


class NativeUpsellAction:
    """One native upsell/downsell action bound to one preserved purchase context.

    Transaction-state laws enforced here:
      * single-flight: processing disables repeat triggering; a double
        click cannot double-charge;
      * paid settles ONLY when an authoritative native read-back confirms
        it — a front-end click, a redirect, or a bare invoke result of
        paid never grants access;
      * an unknown outcome blocks every retry until reconcile() resolves
        it against authoritative native records (read-back FIRST); a
        timeout is never a decline and never justifies a blind second
        charge;
      * decline is terminal, charges nothing and removes no existing
        access; abandonment is recorded as abandonment, never a decline;
      * the parent purchase is read-only: every outcome reports
        parent_purchase_unaffected=True.
    """

    def __init__(self, context: PurchaseContext) -> None:
        if not isinstance(context, PurchaseContext):
            raise UpsellContractError("NativeUpsellAction requires a PurchaseContext.")
        self._context = context
        self._state = READY
        self._attempt_count = 0
        self._in_flight = False
        self._unresolved = False
        self._declined = False
        self._abandoned = False
        self._read_back_confirmed = False
        self._last_txn_ref: Optional[str] = None
        self._outcomes: list = []

    # -- read-only views ----------------------------------------------------

    @property
    def context(self) -> PurchaseContext:
        return self._context

    @property
    def state(self) -> str:
        return self._state

    @property
    def outcomes(self) -> Tuple[AttemptOutcome, ...]:
        return tuple(self._outcomes)

    @property
    def entitlement_granted(self) -> bool:
        """Access exists only from verified native success evidence."""
        return self._state == PAID and self._read_back_confirmed

    # -- internals ----------------------------------------------------------

    def _transition(self, to_state: str) -> None:
        if not can_transition(self._state, to_state):
            raise UpsellContractError(
                "Illegal purchase-state transition %s -> %s." % (self._state, to_state)
            )
        self._state = to_state

    def _idempotency_key(self, attempt_number: int) -> str:
        material = "|".join(
            [
                self._context.tenant_ref,
                self._context.location_ref,
                self._context.launch_ref,
                self._context.parent_order_ref,
                self._context.role,
                self._context.offer_id,
                self._context.native_product_ref,
                self._context.native_price_ref,
                str(attempt_number),
            ]
        )
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
        return "w8b-action-%s-a%d" % (digest, attempt_number)

    def _record(self, action: str, route_ref: Optional[str]) -> AttemptOutcome:
        outcome = AttemptOutcome(
            action=action,
            state=self._state,
            route_ref=route_ref,
            native_txn_ref=self._last_txn_ref,
            failure_kind=None,
            read_back_confirmed=self._read_back_confirmed,
            attempt_number=self._attempt_count,
            idempotency_key=None,
            parent_purchase_unaffected=True,
            entitlement_granted=self.entitlement_granted,
        )
        self._outcomes.append(outcome)
        return outcome

    def _route_for(self, state: str) -> Optional[str]:
        if state == PAID:
            return self._context.success_route_ref
        return self._context.failure_route_ref

    # -- accept (guarded native one-click action) ---------------------------

    def accept(self, driver: NativeDriver, request_payload: Optional[Mapping] = None) -> AttemptOutcome:
        """Attempt the guarded native purchase, single-flight.

        Refuses raw card material in the request payload, refuses retry
        while an outcome is unknown, and settles paid only on read-back.
        """
        assert_no_card_data(request_payload or {}, "request_payload")
        if self._abandoned:
            raise UpsellContractError(
                "This action was abandoned; abandonment never purchases and "
                "never records a decline. A fresh presentation requires a fresh action."
            )
        if self._unresolved:
            raise UpsellContractError(
                "A prior attempt's outcome is unknown; retry is refused until "
                "reconcile() resolves it against authoritative native records. "
                "A timeout is not a decline and never justifies a second blind charge."
            )
        if self._declined:
            raise UpsellContractError(
                "This action was declined; decline is terminal. A fresh "
                "presentation requires a fresh action."
            )
        if self._state == PAID:
            raise UpsellContractError("This offer is already paid; no duplicate charge.")
        if self._in_flight:
            raise UpsellContractError(
                "A purchase attempt is already processing; repeat purchase "
                "attempts are disabled (a double click cannot double-charge)."
            )
        if self._state not in (READY, FAILED, REQUIRES_CUSTOMER_ACTION):
            raise UpsellContractError(
                "accept() cannot start from purchase state %r." % (self._state,)
            )
        self._in_flight = True
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
                # Unknown outcome: the charge may or may not exist. Never call
                # it failed, never retry blind — reconcile first.
                self._transition(PENDING_CONFIRMATION)
                self._unresolved = True
                outcome = self._record("accept", self._context.failure_route_ref)
                return _with(outcome, failure_kind="unknown_outcome", idempotency_key=key)
            if result.native_txn_ref is not None:
                self._last_txn_ref = result.native_txn_ref
            return self._settle("accept", result, attempt_number, key, driver)
        finally:
            self._in_flight = False

    def _settle(self, action: str, result: NativeResult, attempt_number: int,
                key: Optional[str], driver: Optional[NativeDriver],
                *, confirmed: bool = False) -> AttemptOutcome:
        """Settle a driver result; paid is only ever settled by read-back."""
        self._attempt_count = max(self._attempt_count, attempt_number)
        if result.state == PAID:
            if confirmed:
                confirmation = result
            else:
                if driver is None:
                    raise UpsellContractError("A paid result cannot be settled without read-back.")
                confirmation = driver.read_back(self._context, result.native_txn_ref)
            if confirmation.state == PAID:
                if self._state != PAID:
                    self._transition(PAID)
                self._unresolved = False
                self._read_back_confirmed = True
                self._last_txn_ref = confirmation.native_txn_ref or result.native_txn_ref
                outcome = self._record(action, self._context.success_route_ref)
                return _with(
                    outcome,
                    native_txn_ref=self._last_txn_ref,
                    read_back_confirmed=True,
                    idempotency_key=key,
                    entitlement_granted=True,
                )
            # A claim of paid that native records do not confirm: not paid and
            # not a known failure — unresolved until authoritative state settles.
            if self._state != PENDING_CONFIRMATION:
                self._transition(PENDING_CONFIRMATION)
            self._unresolved = True
            self._read_back_confirmed = False
            outcome = self._record(action, self._context.failure_route_ref)
            return _with(
                outcome,
                failure_kind="paid_not_confirmed_by_readback",
                native_txn_ref=result.native_txn_ref,
                idempotency_key=key,
            )
        if result.state in (READY, VALIDATING, SUBMITTING, PENDING_CONFIRMATION):
            if self._state != PENDING_CONFIRMATION:
                self._transition(PENDING_CONFIRMATION)
            self._unresolved = True
            outcome = self._record(action, self._context.failure_route_ref)
            return _with(
                outcome,
                failure_kind=result.failure_kind,
                native_txn_ref=result.native_txn_ref,
                idempotency_key=key,
            )
        # Definitive non-paid outcomes: failed / requires_customer_action /
        # cancelled. The outcome is KNOWN; a failure is never an acceptance
        # and never a decline.
        if self._state != result.state:
            self._transition(result.state)
        self._unresolved = False
        self._read_back_confirmed = False
        outcome = self._record(action, self._route_for(result.state))
        return _with(
            outcome,
            failure_kind=result.failure_kind,
            native_txn_ref=result.native_txn_ref,
            idempotency_key=key,
        )

    # -- decline ------------------------------------------------------------

    def decline(self) -> AttemptOutcome:
        """Explicit decline: no charge, no removal of existing access, terminal."""
        if self._unresolved:
            raise UpsellContractError(
                "A prior attempt's outcome is unknown; reconcile() before routing "
                "onward, so a possibly-paid attempt is never recorded as a decline."
            )
        if self._state == PAID:
            raise UpsellContractError("A paid offer cannot be declined after the fact.")
        if self._declined or self._abandoned:
            raise UpsellContractError(
                "This presentation already reached a terminal routed outcome."
            )
        self._declined = True
        return self._record("decline", self._context.decline_route_ref)

    # -- reconcile (authoritative state FIRST) ------------------------------

    def reconcile(self, driver: NativeDriver) -> AttemptOutcome:
        """Resolve a pending/unknown outcome from authoritative native records.

        Read-back happens FIRST and is its own confirmation; until it
        resolves the attempt, every retry stays refused.
        """
        if self._attempt_count == 0:
            raise UpsellContractError("No attempt exists to reconcile.")
        result = driver.read_back(self._context, self._last_txn_ref)
        if result.native_txn_ref is not None:
            self._last_txn_ref = result.native_txn_ref
        return self._settle("reconcile", result, self._attempt_count, None, driver, confirmed=True)

    # -- abandon ------------------------------------------------------------

    def abandon(self) -> AttemptOutcome:
        """Session abandonment: never a fabricated decline, never a purchase."""
        if self._state == PAID:
            raise UpsellContractError("A paid offer cannot be abandoned after the fact.")
        if self._declined:
            raise UpsellContractError("This presentation was already declined.")
        self._abandoned = True
        return self._record("abandon", None)


def _with(outcome: AttemptOutcome, **overrides) -> AttemptOutcome:
    """Frozen-dataclass field override helper for outcome reporting."""
    data = {
        "action": outcome.action,
        "state": outcome.state,
        "route_ref": outcome.route_ref,
        "native_txn_ref": outcome.native_txn_ref,
        "failure_kind": outcome.failure_kind,
        "read_back_confirmed": outcome.read_back_confirmed,
        "attempt_number": outcome.attempt_number,
        "idempotency_key": outcome.idempotency_key,
        "parent_purchase_unaffected": outcome.parent_purchase_unaffected,
        "entitlement_granted": outcome.entitlement_granted,
    }
    data.update(overrides)
    return AttemptOutcome(**data)


# ---------------------------------------------------------------------------
# Assert-based self-check (runnable: python3 -I skills/80-upsell/native_upsell.py)
# ---------------------------------------------------------------------------


class _FakeDriver:
    """Self-check driver: deterministic results, no network, no charges."""

    def __init__(self, script) -> None:
        self._script = list(script)
        self.invocations = 0
        self.read_backs = 0

    def invoke(self, context: PurchaseContext, idempotency_key: str) -> NativeResult:
        self.invocations += 1
        step = self._script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step

    def read_back(self, context: PurchaseContext, native_txn_ref: Optional[str]) -> NativeResult:
        self.read_backs += 1
        return self._script.pop(0)


def _self_check() -> None:
    checks = 0

    def ok(condition: bool, label: str) -> None:
        nonlocal checks
        assert condition, "self-check failed: %s" % label
        checks += 1

    evidence = PurchaseEvidence("ledger:MAIN-1", "native_purchase_ledger")
    journey_ok = Journey(main_purchase=evidence, u1_event="purchased",
                         u1_purchase=PurchaseEvidence("ledger:U1-1", "native_purchase_ledger"))
    journey_declined = Journey(main_purchase=evidence, u1_event="explicit_decline")
    journey_failed_u1 = Journey(main_purchase=evidence, u1_event="failure")
    journey_bump_only = Journey(main_purchase=evidence)
    flags = LaunchFlags(u1_enabled=True, d1_enabled=True, u2_enabled=True)

    # Entry guards
    check_entry("upsell_1", journey_ok, flags)
    checks += 1
    try:
        check_entry("downsell_1", journey_declined, flags)
        ok(True, "d1 entry on explicit decline")
    except UpsellContractError:
        ok(False, "d1 entry on explicit decline")
    for bad_journey, label in (
        (journey_failed_u1, "d1 entry refuses failed U1"),
        (journey_bump_only, "d1 entry refuses bump-only"),
    ):
        try:
            check_entry("downsell_1", bad_journey, flags)
            ok(False, label)
        except UpsellContractError:
            ok(True, label)
    try:
        check_entry("downsell_1", journey_ok, flags)  # accepted U1 buyer
        ok(False, "d1 entry refuses accepted-U1 buyer")
    except UpsellContractError:
        ok(True, "d1 entry refuses accepted-U1 buyer")
    try:
        check_entry("upsell_2", journey_bump_only, flags)
        ok(False, "u2 entry refuses bump-only")
    except UpsellContractError:
        ok(True, "u2 entry refuses bump-only")
    check_entry("upsell_2", journey_ok, flags)
    checks += 1
    try:
        check_entry("upsell_2", Journey(main_purchase=evidence, u1_event="purchased",
                                        u1_purchase=PurchaseEvidence("ledger:U1-2", "provider_event_readback"),
                                        u2_product_already_owned=True), flags)
        ok(False, "u2 entry refuses already-owned")
    except UpsellContractError:
        ok(True, "u2 entry refuses already-owned")

    # Route law
    try:
        validate_launch_flags(LaunchFlags(u1_enabled=False, d1_enabled=True, u2_enabled=False))
        ok(False, "launch law: U1 off disables D1")
    except UpsellContractError:
        ok(True, "launch law: U1 off disables D1")
    r = resolve_next("upsell_1", ACCEPT, flags)
    ok(r.destination == SAME_U2 and r.entry_context == "from_upsell_1", "U1 accept -> same U2")
    r = resolve_next("downsell_1", ACCEPT, flags)
    ok(r.destination == SAME_U2 and r.entry_context == "from_downsell_1", "D1 accept -> same U2")
    ok(resolve_next("upsell_1", EXPLICIT_DECLINE, flags).destination == "downsell_1",
       "U1 decline -> D1")
    for bad in (FAILURE, PENDING, UNKNOWN_OUTCOME):
        ok(resolve_next("upsell_1", bad, flags).destination == STAY_RECOVER,
           "U1 %s never routes to D1" % bad)
    ok(resolve_next("downsell_1", EXPLICIT_DECLINE, flags).destination == THANK_YOU,
       "D1 decline -> thank-you")
    ok(resolve_next("upsell_1", ABANDONED, flags).original_order_preserved, "abandon preserves order")

    # Platform: V2 one-click is Funnel-only; domain continuity; quantity.
    base_kwargs = dict(
        tenant_ref="tenant-1", location_ref="loc-1", launch_ref="launch-1",
        launch_revision="rev-1", parent_order_ref="order-1",
        parent_verification_source="native_purchase_ledger", role="upsell_1",
        offer_id="offer-u1", native_product_ref="product-1", native_price_ref="price-1",
        capability_evidence_ref="native:CAP-1", disclosure_terms_ref="catalog:DISC-1",
        amount_minor=4900, currency="USD", success_route_ref="route:u2",
        decline_route_ref="route:d1", failure_route_ref="route:recover",
        confirmation_route_ref="route:thanks", checkout_family="v2_funnel",
        processor_ref="processor-1", payment_mode="saved_card_one_click",
        domain_ref="buy.example.com", quantity=1, max_quantity=2,
    )
    ctx = PurchaseContext(**base_kwargs)
    report = one_click_allowed(ctx, True)
    ok(report.one_click_supported, "v2 funnel + verified capability allows one-click")
    report = one_click_allowed(ctx, None)
    ok(not report.one_click_supported and report.fallback_required,
       "unknown capability never assumed supported")
    site_ctx = PurchaseContext(**dict(base_kwargs, checkout_family="website",
                                      native_product_ref="product-2"))
    report = one_click_allowed(site_ctx, True)
    ok(not report.one_click_supported and report.fallback == WEBSITE_PURCHASE_ROUTE,
       "V2 one-click is Funnel-only; website routes into supported V2 funnel")
    check_domain_continuity(ctx, "buy.example.com")
    checks += 1
    try:
        check_domain_continuity(ctx, "other.example.com")
        ok(False, "domain continuity fail-closed")
    except UpsellContractError:
        ok(True, "domain continuity fail-closed")
    try:
        PurchaseContext(**dict(base_kwargs, quantity=3))
        ok(False, "quantity constraint enforced")
    except UpsellContractError:
        ok(True, "quantity constraint enforced")
    try:
        PurchaseContext(**dict(base_kwargs, extras={"card_number": "4111111111111111"}))
        ok(False, "card data refused")
    except UpsellContractError:
        ok(True, "card data refused")

    # Transaction state: paid only from read-back; double-click guard;
    # unknown outcome blocks retry until reconcile.
    action = NativeUpsellAction(ctx)
    driver = _FakeDriver([NativeResult(PAID, "txn-1"), NativeResult(PENDING_CONFIRMATION)])
    out = action.accept(driver)
    ok(out.state == PENDING_CONFIRMATION and not out.entitlement_granted,
       "bare invoke paid is never paid (no read-back confirmation yet)")
    ok(driver.read_backs == 1 and not action.entitlement_granted,
       "read-back did not confirm: no entitlement")
    try:
        action.accept(_FakeDriver([NativeResult(FAILED)]))
        ok(False, "retry refused while outcome unknown")
    except UpsellContractError:
        ok(True, "retry refused while outcome unknown")
    out = action.reconcile(_FakeDriver([NativeResult(FAILED, failure_kind="declined_by_bank")]))
    ok(out.state == FAILED and not action.entitlement_granted,
       "reconcile settles failed from authoritative state")
    out = action.accept(_FakeDriver([NativeResult(PAID, "txn-2"), NativeResult(PAID, "txn-2")]))
    ok(action.entitlement_granted and out.entitlement_granted,
       "paid with read-back confirmation grants entitlement")
    try:
        action.accept(_FakeDriver([]))
        ok(False, "no duplicate charge after paid")
    except UpsellContractError:
        ok(True, "no duplicate charge after paid")

    action2 = NativeUpsellAction(ctx)
    driver2 = _FakeDriver([RuntimeError("timeout"), NativeResult(PAID, "txn-9")])
    out = action2.accept(driver2)
    ok(out.failure_kind == "unknown_outcome" and out.state == PENDING_CONFIRMATION,
       "invoke exception is an unknown outcome, never failed, never a decline")
    out = action2.reconcile(driver2)
    ok(action2.entitlement_granted and out.read_back_confirmed,
       "reconcile with confirming read-back settles paid")
    ok(driver2.read_backs == 1, "reconcile paid performs exactly one read-back")

    action3 = NativeUpsellAction(ctx)
    out = action3.decline()
    ok(out.state == READY and not action3.entitlement_granted and out.parent_purchase_unaffected,
       "decline charges nothing and preserves the parent purchase")
    try:
        action3.accept(_FakeDriver([]))
        ok(False, "decline is terminal")
    except UpsellContractError:
        ok(True, "decline is terminal")
    action4 = NativeUpsellAction(ctx)
    action4.abandon()
    ok(not action4.entitlement_granted, "abandonment never purchases")
    try:
        action4.decline()
        ok(False, "abandonment never converts to decline")
    except UpsellContractError:
        ok(True, "abandonment never converts to decline")

    # Single-flight: a second accept during processing is refused.
    action5 = NativeUpsellAction(ctx)

    class _ReentrantDriver:
        def __init__(self) -> None:
            self.entered = False
            self.inner_error: Optional[Exception] = None

        def invoke(self, context, idempotency_key):
            self.entered = True
            try:
                action5.accept(self)
            except UpsellContractError as exc:
                self.inner_error = exc
            return NativeResult(FAILED, failure_kind="test")

        def read_back(self, context, native_txn_ref):
            return NativeResult(FAILED)

    reentrant = _ReentrantDriver()
    action5.accept(reentrant)
    ok(reentrant.entered and isinstance(reentrant.inner_error, UpsellContractError),
       "processing disables repeat triggering (double-click cannot double-charge)")

    # Purchase context preservation + never grant from front-end click alone.
    ok(all(o.parent_purchase_unaffected for o in action.outcomes),
       "every outcome reports the parent purchase unaffected")
    click_only = NativeUpsellAction(ctx)
    ok(not click_only.entitlement_granted,
       "a front-end click alone never grants access")

    print("native_upsell self-check: %d assertions OK" % checks)


if __name__ == "__main__":
    _self_check()
