"""Native order-component execution for GHL delivery — Skill 06 (stream W8, W8C).

Binds REAL checkout component IDs to REAL product/price IDs during managed
builder execution, and verifies every mutation by component read-back.
Governing sources:

  * GHL-DELIVERY-SPEC.md, "Commerce (W8) — native reality, no counterfeit
    controls": products/prices attach their returned native IDs to native
    checkout components; catalog creation is NOT checkout binding; bumps
    attach to the right native checkout with accurate terms and intentional
    selection state (never silently preselected extra purchase); native
    totals add/remove; the selected component family's multiple-bump and
    recurring-product limits are respected; NO raw card collection/storage,
    token copying, replayed charges, or simulated payment success.
  * GHL-DELIVERY-SPEC.md, "Confirmed gaps" #2: states must be SET to the
    requested true/false AND read back — never blind-toggle.
  * shared-utils/ghl/products_prices.py (W8D): `ComponentIO` names THIS
    module as its managed-builder execution side. `CheckoutComponentIO`
    here implements that exact surface (`get_checkout_price` /
    `set_checkout_price`) so `ProductsPricesAdapter.bind_price_to_checkout`
    can verify attachment against real component state. Price references
    carry exactly `NativePrice.as_price_ref_fields()` keys.
  * skills/79-checkout/order_bumps.py (W8A): billing-type vocabulary,
    approved-catalog/accurate-terms law, family bump limits and explicit
    selection semantics; mirrored structurally here because unit branches
    do not import each other (single-writer merge process).
  * shared-utils/browser/iframe_router.py (W3B): every operation targets an
    EXPLICIT tab + frame; an ambiguous frame or duplicate component id is a
    refusal, never a first-match pick.

This module performs no network calls and no charges. The native side is
supplied by the caller as an `OrderComponentDriver` (managed browser
execution: W3B frame safeguards + W3C runtime adapters). Execution without
a wired driver is reported as capability incomplete, never as done.

Run the assert-based self-check:

    python3 -I skills/06-ghl-delivery/order_components.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Protocol, Sequence, Tuple

__all__ = [
    "OrderComponentError",
    "SpecError",
    "ComponentNotFound",
    "AmbiguousTarget",
    "ReadbackMismatch",
    "UnsupportedState",
    "CardDataRefused",
    "PRICE_REF_FIELDS",
    "BILLING_TYPES",
    "FrameScope",
    "PriceRef",
    "BumpAttach",
    "ComponentFamily",
    "OpRecord",
    "BindRecord",
    "OrderComponentDriver",
    "CheckoutComponentIO",
    "OrderComponentExecutor",
    "validate_price_ref",
    "assert_no_card_data",
]

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class OrderComponentError(Exception):
    """Base: any execution the order-component contract forbids."""

class SpecError(OrderComponentError):
    """Malformed input: field sets, billing terms, booleans, identities."""

class ComponentNotFound(OrderComponentError):
    """The requested native component id does not exist in the target frame."""

class AmbiguousTarget(OrderComponentError):
    """More than one component matches (duplicate ids across frames/components).
    Refused rather than resolved by first-match."""

class ReadbackMismatch(OrderComponentError):
    """Component state after a set does not equal the requested state.
    The mismatch is never persisted as success and never claimed bound."""

class UnsupportedState(OrderComponentError):
    """Family limits or requested states the declared capability forbids."""

class CardDataRefused(OrderComponentError):
    """Raw card data must never be collected, stored, or written."""

# ---------------------------------------------------------------------------
# Price references — exactly W8D NativePrice.as_price_ref_fields() keys
# ---------------------------------------------------------------------------

PRICE_REF_FIELDS = (
    "native_product_id",
    "native_price_id",
    "amount_minor",
    "currency",
    "billing_type",
    "recurring_interval",
    "trial_days",
)

BILLING_TYPES = ("one_time", "recurring", "trial_then_recurring")

_CARD_KEY_FRAGMENTS = (
    "card_number", "cardnumber", "pan", "cvv", "cvc", "cvv2", "cvc2",
    "security_code", "expiry", "exp_month", "exp_year", "track1", "track2",
)


def _require_text(value: Any, what: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise SpecError(f"{what} must be a non-empty string")


def _require_bool(value: Any, what: str) -> None:
    if not isinstance(value, bool):
        raise SpecError(f"{what} must be an explicit boolean, never {value!r}")


def _require_minor_units(value: Any, what: str) -> None:
    # bool is an int subclass; a boolean amount is always a mistake.
    if not isinstance(value, int) or isinstance(value, bool):
        raise SpecError(f"{what} must be integer minor units, never float dollars")
    if value < 0:
        raise SpecError(f"{what} cannot be negative; unknown price is not zero")


# ---------------------------------------------------------------------------
# Core value types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FrameScope:
    """Explicit tab + frame identity (W3B). No defaults: an operation that
    does not know where it points has no business executing."""

    tab_id: str
    frame_id: str

    def __post_init__(self) -> None:
        _require_text(self.tab_id, "tab_id")
        _require_text(self.frame_id, "frame_id")


@dataclass(frozen=True)
class PriceRef:
    """A real native product/price reference with exact verified terms.
    Field set is exactly the W8D `NativePrice.as_price_ref_fields()` contract;
    extras are refused so invented fields can never reach a native component."""

    native_product_id: str
    native_price_id: str
    amount_minor: int
    currency: str
    billing_type: str = "one_time"
    recurring_interval: Optional[str] = None
    trial_days: Optional[int] = None

    def __post_init__(self) -> None:
        _require_text(self.native_product_id, "native_product_id")
        _require_text(self.native_price_id, "native_price_id")
        _require_minor_units(self.amount_minor, "amount_minor")
        _require_text(self.currency, "currency")
        if self.billing_type not in BILLING_TYPES:
            raise SpecError(f"unknown billing_type: {self.billing_type}")
        if self.billing_type == "recurring":
            _require_text(self.recurring_interval or "", "recurring_interval for recurring price")
            if self.trial_days is not None:
                raise SpecError("recurring price must not carry trial_days")
        elif self.billing_type == "trial_then_recurring":
            _require_text(self.recurring_interval or "",
                          "recurring_interval for trial_then_recurring price")
            if not isinstance(self.trial_days, int) or isinstance(self.trial_days, bool) \
                    or self.trial_days < 1:
                raise SpecError("trial_then_recurring price requires trial_days >= 1")
        else:
            if self.recurring_interval is not None or self.trial_days is not None:
                raise SpecError("one_time price must not carry recurrence terms")

    @property
    def is_recurring(self) -> bool:
        return self.billing_type != "one_time"

    def as_fields(self) -> Dict[str, Any]:
        """Exactly the wire mapping W8D writes to a checkout component."""
        return {
            "native_product_id": self.native_product_id,
            "native_price_id": self.native_price_id,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "billing_type": self.billing_type,
            "recurring_interval": self.recurring_interval,
            "trial_days": self.trial_days,
        }


def validate_price_ref(ref: Mapping[str, Any]) -> PriceRef:
    """Accept exactly PRICE_REF_FIELDS — no missing keys, no invented keys."""
    if not isinstance(ref, Mapping):
        raise SpecError("price ref must be a mapping")
    missing = [k for k in PRICE_REF_FIELDS if k not in ref]
    extra = [k for k in ref if k not in PRICE_REF_FIELDS]
    if missing:
        raise SpecError(f"price ref missing fields: {missing}")
    if extra:
        raise SpecError(f"price ref carries invented fields: {extra}")
    return PriceRef(**{k: ref[k] for k in PRICE_REF_FIELDS})


@dataclass(frozen=True)
class BumpAttach:
    """One order-bump attachment. No selection field on purpose: a bump is
    attached UNSELECTED; selection is explicit later state (W8A law)."""

    offer_id: str
    headline: str
    benefit_explanation: str
    price: PriceRef
    disclosure_text: Optional[str] = None  # required for recurring/trial bumps

    def __post_init__(self) -> None:
        _require_text(self.offer_id, "offer_id")
        _require_text(self.headline, "headline")
        _require_text(self.benefit_explanation, "benefit_explanation")
        if self.price.is_recurring:
            _require_text(self.disclosure_text or "", "disclosure_text for recurring/trial bump")

    def as_fields(self) -> Dict[str, Any]:
        return {
            "offer_id": self.offer_id,
            "headline": self.headline,
            "benefit_explanation": self.benefit_explanation,
            "disclosure_text": self.disclosure_text,
            "price": self.price.as_fields(),
            "selected": False,
        }


@dataclass(frozen=True)
class ComponentFamily:
    """Native checkout component family limits, declared by the caller from
    the W2 capability inventory. This module never invents platform limits
    (structural twin of skills/79-checkout ComponentFamily)."""

    name: str
    max_bumps: int
    allows_recurring_bumps: bool

    def __post_init__(self) -> None:
        _require_text(self.name, "family name")
        if not isinstance(self.max_bumps, int) or isinstance(self.max_bumps, bool) \
                or self.max_bumps < 0:
            raise SpecError("max_bumps must be an integer >= 0 (0 = bumps unsupported)")
        _require_bool(self.allows_recurring_bumps, "allows_recurring_bumps")


@dataclass(frozen=True)
class OpRecord:
    """Every execution operation recorded: route, location, target, readback."""

    route: str  # e.g. "component.set_state"
    tab_id: str
    frame_id: str
    target: str  # native component id addressed
    readback: str  # "verified" | "mismatch-refused" | "not-attempted"


@dataclass(frozen=True)
class BindRecord:
    """Outcome of one bind/attach. `state` is "bound-verified" ONLY after
    component read-back verification succeeded."""

    checkout_component_id: str
    state: str
    op: OpRecord


# ---------------------------------------------------------------------------
# Driver seam — managed builder execution supplied by the caller
# ---------------------------------------------------------------------------

class OrderComponentDriver(Protocol):
    """Native component read/write on ONE explicit tab + frame. Implementations
    live in managed browser execution (W3B iframe safeguards, W3C runtime
    adapters). Ambiguity is surfaced by raising, never by picking."""

    def list_components(self, scope: FrameScope) -> Sequence[Mapping[str, Any]]:
        """All components in the frame, each at least {"component_id", "kind"}."""
        ...

    def get_state(self, scope: FrameScope, component_id: str) -> Optional[Mapping[str, Any]]:
        """Full component state, or None when the id does not exist."""
        ...

    def set_state(self, scope: FrameScope, component_id: str, patch: Mapping[str, Any]) -> None:
        """Apply a patch to the component. Verification is NOT the driver's job."""
        ...


def assert_no_card_data(payload: Mapping[str, Any]) -> None:
    """Fail closed: raw card data never reaches a native component."""
    for key, value in payload.items():
        lowered = str(key).lower()
        for fragment in _CARD_KEY_FRAGMENTS:
            if fragment in lowered:
                raise CardDataRefused(f"card-data field refused: {key}")
        if isinstance(value, Mapping):
            assert_no_card_data(value)


# ---------------------------------------------------------------------------
# W8D ComponentIO surface (managed-builder side named W8C)
# ---------------------------------------------------------------------------

class CheckoutComponentIO:
    """Implements shared-utils/ghl/products_prices.py `ComponentIO`
    (`get_checkout_price` / `set_checkout_price`) over the driver seam, so
    `ProductsPricesAdapter.bind_price_to_checkout` attaches real prices to a
    real checkout component id and verifies them against real read-back."""

    def __init__(self, executor: "OrderComponentExecutor") -> None:
        self._ex = executor

    def get_checkout_price(self, checkout_component_id: str) -> Optional[Mapping[str, Any]]:
        state = self._ex.read_component(checkout_component_id)
        if state is None:
            return None
        ref = state.get("main_price")
        return ref if isinstance(ref, Mapping) else None

    def set_checkout_price(self, checkout_component_id: str, price_ref: Mapping[str, Any]) -> None:
        self._ex.bind_main_price(checkout_component_id, validate_price_ref(price_ref))


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------

class OrderComponentExecutor:
    """Executes order-component configuration on one explicit frame.

    Every mutation: validate -> set the requested state -> READ BACK ->
    compare -> record. A read-back mismatch raises ReadbackMismatch and is
    recorded "mismatch-refused"; nothing is ever claimed bound on drift."""

    def __init__(self, driver: OrderComponentDriver, scope: FrameScope,
                 family: ComponentFamily) -> None:
        if not all(hasattr(driver, m) for m in ("list_components", "get_state", "set_state")):
            raise SpecError("driver must implement the OrderComponentDriver surface")
        if not isinstance(scope, FrameScope):
            raise SpecError("scope must be an explicit FrameScope (never a first tab)")
        if not isinstance(family, ComponentFamily):
            raise SpecError("family limits must be declared (W2 capability inventory)")
        self._driver = driver
        self._scope = scope
        self._family = family
        self._ops: list = []

    @property
    def ops(self) -> Tuple[OpRecord, ...]:
        """Every executed operation, in order, success and refusal alike."""
        return tuple(self._ops)

    # -- targeting ----------------------------------------------------------

    def resolve_component(self, component_id: str, kind: str = "checkout") -> Mapping[str, Any]:
        """Exactly one match on the real native id inside the explicit frame.
        Zero -> ComponentNotFound. Duplicates -> AmbiguousTarget. Wrong kind
        -> SpecError. The first listed component is never picked."""
        _require_text(component_id, "checkout_component_id")
        _require_text(kind, "component kind")
        matches = [c for c in self._driver.list_components(self._scope)
                   if isinstance(c, Mapping) and c.get("component_id") == component_id]
        if not matches:
            raise ComponentNotFound(
                f"component {component_id!r} not present in frame {self._scope.frame_id!r}")
        if len(matches) > 1:
            raise AmbiguousTarget(
                f"{len(matches)} components share id {component_id!r} in frame "
                f"{self._scope.frame_id!r}; refusing first-match")
        found = matches[0]
        if found.get("kind") != kind:
            raise SpecError(
                f"component {component_id!r} is kind {found.get('kind')!r}, not {kind!r}")
        return found

    def read_component(self, component_id: str) -> Optional[Mapping[str, Any]]:
        return self._driver.get_state(self._scope, component_id)

    # -- verified writes ----------------------------------------------------

    def _write_verified(self, route: str, component_id: str,
                        patch: Mapping[str, Any],
                        verify: Any) -> BindRecord:
        """Set -> read back -> verify. Every attempt is recorded; a mismatch
        re-raises its precise cause after recording "mismatch-refused", and
        success is claimed "bound-verified" only on exact read-back."""
        assert_no_card_data(patch)
        self._driver.set_state(self._scope, component_id, dict(patch))
        observed = self._driver.get_state(self._scope, component_id)
        try:
            verify(observed)
        except OrderComponentError:
            self._ops.append(OpRecord(
                route, self._scope.tab_id, self._scope.frame_id,
                component_id, "mismatch-refused"))
            raise
        record = OpRecord(
            route, self._scope.tab_id, self._scope.frame_id,
            component_id, "verified")
        self._ops.append(record)
        return BindRecord(component_id, "bound-verified", record)

    @staticmethod
    def _verify_fields(component_id: str, observed: Optional[Mapping[str, Any]],
                       want: Mapping[str, Any], where: str) -> None:
        if not isinstance(observed, Mapping):
            raise ReadbackMismatch(
                f"component {component_id} readback missing after set ({where})")
        got = observed.get(where)
        if not isinstance(got, Mapping):
            raise ReadbackMismatch(
                f"component {component_id} {where} readback missing after set")
        for key, value in want.items():
            if got.get(key) != value:
                raise ReadbackMismatch(
                    f"component {component_id} {where}.{key} readback "
                    f"{got.get(key)!r} != {value!r}")

    # -- main price binding -------------------------------------------------

    def bind_main_price(self, checkout_component_id: str,
                        price: PriceRef) -> BindRecord:
        """Attach a real readback-verified price to a real checkout component
        id and verify the attachment by component read-back. Catalog IDs
        alone are never binding; a readback mismatch raises and binds nothing."""
        self.resolve_component(checkout_component_id, "checkout")
        if not isinstance(price, PriceRef):
            raise SpecError("bind_main_price requires a validated PriceRef")
        want = price.as_fields()
        return self._write_verified(
            "component.bind_main_price", checkout_component_id,
            {"main_price": want},
            lambda observed: self._verify_fields(
                checkout_component_id, observed, want, "main_price"))

    # -- order bumps --------------------------------------------------------

    def _current_bumps(self, checkout_component_id: str) -> Tuple[Mapping[str, Any], ...]:
        state = self.read_component(checkout_component_id)
        if not isinstance(state, Mapping):
            return ()
        bumps = state.get("bumps")
        if not isinstance(bumps, Sequence) or isinstance(bumps, (str, bytes)):
            return ()
        return tuple(b for b in bumps if isinstance(b, Mapping))

    def attach_bump(self, checkout_component_id: str, bump: BumpAttach) -> BindRecord:
        """Attach an approved bump to the right native checkout, UNSELECTED.
        Family limits (multiple-bump, recurring-product) are enforced here."""
        self.resolve_component(checkout_component_id, "checkout")
        if not isinstance(bump, BumpAttach):
            raise SpecError("attach_bump requires a BumpAttach")
        current = self._current_bumps(checkout_component_id)
        if len(current) >= self._family.max_bumps:
            raise UnsupportedState(
                f"family {self._family.name} allows at most {self._family.max_bumps} "
                f"bump(s); refusing attach of {bump.offer_id}")
        if bump.price.is_recurring and not self._family.allows_recurring_bumps:
            raise UnsupportedState(
                f"family {self._family.name} does not allow recurring-product bumps "
                f"(bump {bump.offer_id})")
        state = self.read_component(checkout_component_id) or {}
        main = state.get("main_price") if isinstance(state, Mapping) else None
        if isinstance(main, Mapping) and main.get("currency") not in (None, bump.price.currency):
            raise SpecError(
                f"bump {bump.offer_id} currency {bump.price.currency} does not match "
                f"checkout currency {main.get('currency')}")
        seen_prices = {b.get("price", {}).get("native_price_id") for b in current
                       if isinstance(b.get("price"), Mapping)}
        seen_offers = {b.get("offer_id") for b in current}
        if bump.offer_id in seen_offers:
            raise SpecError(f"duplicate bump offer_id {bump.offer_id}; never charge twice")
        if bump.price.native_price_id in seen_prices:
            raise SpecError(
                f"duplicate native price {bump.price.native_price_id}; never charge twice")
        new_bumps = [dict(b) for b in current] + [bump.as_fields()]
        return self._write_verified(
            "component.attach_bump", checkout_component_id,
            {"bumps": new_bumps},
            lambda observed: self._verify_bumps(
                checkout_component_id, observed, new_bumps))

    @staticmethod
    def _verify_bumps(component_id: str, observed: Optional[Mapping[str, Any]],
                      new_bumps: Sequence[Mapping[str, Any]]) -> None:
        if not isinstance(observed, Mapping):
            raise ReadbackMismatch(f"component {component_id} readback missing after set")
        got_list = observed.get("bumps")
        if not isinstance(got_list, Sequence) or isinstance(got_list, (str, bytes)):
            raise ReadbackMismatch(f"component {component_id} bumps readback missing")
        if len(got_list) != len(new_bumps):
            raise ReadbackMismatch(
                f"component {component_id} bump count {len(got_list)} != {len(new_bumps)}")
        for got, expect in zip(got_list, new_bumps):
            if not isinstance(got, Mapping):
                raise ReadbackMismatch("bump readback entry is not a mapping")
            for key, value in expect.items():
                if key == "selected":
                    continue  # intentional selection verified below
                if got.get(key) != value:
                    raise ReadbackMismatch(
                        f"component {component_id} bump {expect.get('offer_id')} "
                        f"{key} readback {got.get(key)!r} != {value!r}")
            if got.get("selected") is not expect.get("selected"):
                if expect.get("selected") is False:
                    # intentional selection state: never silently preselected
                    raise ReadbackMismatch(
                        f"bump {expect.get('offer_id')} attached preselected "
                        f"({got.get('selected')!r}); extra purchase refused")
                raise ReadbackMismatch(
                    f"bump {expect.get('offer_id')} selected readback "
                    f"{got.get('selected')!r} != {expect.get('selected')!r}")

    def set_bump_selected(self, checkout_component_id: str, offer_id: str,
                          selected: bool) -> BindRecord:
        """Explicit, intentional select/deselect with read-back. Idempotent
        by state; unknown offers are refused, never silently ignored."""
        self.resolve_component(checkout_component_id, "checkout")
        _require_text(offer_id, "offer_id")
        _require_bool(selected, "selection change")
        current = self._current_bumps(checkout_component_id)
        target = [b for b in current if b.get("offer_id") == offer_id]
        if not target:
            raise SpecError(f"offer {offer_id} is not a bump of {checkout_component_id}")
        new_bumps = []
        for bump in current:
            entry = dict(bump)
            if entry.get("offer_id") == offer_id:
                entry["selected"] = selected
            new_bumps.append(entry)
        return self._write_verified(
            "component.set_bump_selected", checkout_component_id,
            {"bumps": new_bumps},
            lambda observed: self._verify_bumps(checkout_component_id, observed, new_bumps))

    # -- required/hidden field states (set AND read back, never blind) -------

    def set_field_state(self, checkout_component_id: str, field_key: str,
                        required: Optional[bool] = None,
                        hidden: Optional[bool] = None) -> BindRecord:
        """Set requested Required/Hidden states to the given true/false AND
        read them back. A blind toggle is impossible: nothing is written
        without an explicit requested value, nothing is accepted without
        read-back equality."""
        self.resolve_component(checkout_component_id, "checkout")
        _require_text(field_key, "field_key")
        if required is None and hidden is None:
            raise SpecError("set_field_state requires at least one requested state")
        patch: Dict[str, Any] = {"field_states": {field_key: {}}}
        want: Dict[str, Any] = {}
        if required is not None:
            _require_bool(required, "required")
            want["required"] = required
        if hidden is not None:
            _require_bool(hidden, "hidden")
            want["hidden"] = hidden
        patch["field_states"][field_key] = dict(want)

        def verify(observed: Optional[Mapping[str, Any]]) -> None:
            if not isinstance(observed, Mapping):
                raise ReadbackMismatch(f"component {checkout_component_id} readback missing")
            states = observed.get("field_states")
            if not isinstance(states, Mapping) or field_key not in states:
                raise ReadbackMismatch(
                    f"component {checkout_component_id} field {field_key} state missing")
            got = states.get(field_key)
            if not isinstance(got, Mapping):
                raise ReadbackMismatch(f"field {field_key} state is not a mapping")
            for key, value in want.items():
                if got.get(key) is not value:
                    raise ReadbackMismatch(
                        f"field {field_key} {key} readback {got.get(key)!r} != {value!r}")

        return self._write_verified(
            "component.set_field_state", checkout_component_id, patch, verify)

    # -- native totals ------------------------------------------------------

    def read_native_totals(self, checkout_component_id: str,
                           quantity: int = 1) -> Dict[str, Any]:
        """Read the component's native totals and reconcile them against the
        approved prices actually bound + explicitly selected bumps. A
        mismatch is refused; totals are never recomputed into existence and
        no payment outcome is ever simulated."""
        self.resolve_component(checkout_component_id, "checkout")
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
            raise SpecError("quantity must be an integer >= 1")
        state = self.read_component(checkout_component_id)
        if not isinstance(state, Mapping):
            raise ReadbackMismatch(f"component {checkout_component_id} state missing")
        main = state.get("main_price")
        if not isinstance(main, Mapping):
            raise ReadbackMismatch(f"component {checkout_component_id} main_price unbound")
        main_ref = validate_price_ref(main)
        expected_items: list = [("main", main_ref.amount_minor * quantity)]
        expected_total = expected_items[0][1]
        for bump in self._current_bumps(checkout_component_id):
            price = bump.get("price")
            if not isinstance(price, Mapping):
                raise ReadbackMismatch(f"bump {bump.get('offer_id')} price unbound")
            if bump.get("selected") is True:
                ref = validate_price_ref(price)
                expected_items.append((bump.get("offer_id"), ref.amount_minor))
                expected_total += ref.amount_minor
        totals = state.get("native_totals")
        if not isinstance(totals, Mapping):
            raise ReadbackMismatch(f"component {checkout_component_id} native_totals missing")
        if totals.get("currency") != main_ref.currency:
            raise ReadbackMismatch(
                f"native totals currency {totals.get('currency')!r} != {main_ref.currency!r}")
        if totals.get("total_minor") != expected_total:
            raise ReadbackMismatch(
                f"native totals {totals.get('total_minor')!r} != expected {expected_total}")
        return {"currency": main_ref.currency,
                "line_items": tuple(expected_items),
                "total_minor": expected_total}


# ---------------------------------------------------------------------------
# Assert-based self-check (offline; fake driver — no network, no charges)
# ---------------------------------------------------------------------------

class _FakeDriver:
    """In-memory native components. `drift` simulates a component that stores
    the wrong value (read-back differs from what was written)."""

    def __init__(self, catalog: Sequence[Mapping[str, Any]],
                 states: Optional[Mapping[str, Mapping[str, Any]]] = None) -> None:
        self.catalog = [dict(c) for c in catalog]
        self.states: Dict[str, Dict[str, Any]] = {
            k: dict(v) for k, v in (states or {}).items()
        }
        self.drift: Dict[str, Dict[str, Any]] = {}
        self.calls: list = []

    def list_components(self, scope: FrameScope) -> Sequence[Mapping[str, Any]]:
        self.calls.append(("list", scope.tab_id, scope.frame_id))
        return tuple(dict(c) for c in self.catalog)

    def get_state(self, scope: FrameScope, component_id: str) -> Optional[Mapping[str, Any]]:
        self.calls.append(("get", scope.tab_id, scope.frame_id, component_id))
        stored = self.states.get(component_id)
        if stored is None:
            return None
        return {**stored, **self.drift.get(component_id, {})}

    def set_state(self, scope: FrameScope, component_id: str,
                  patch: Mapping[str, Any]) -> None:
        self.calls.append(("set", scope.tab_id, scope.frame_id, component_id, dict(patch)))
        self.states.setdefault(component_id, {}).update(dict(patch))
        self._recompute_totals(component_id)

    def _recompute_totals(self, component_id: str) -> None:
        """A well-behaved native checkout owns its totals: main line plus
        explicitly selected bumps, recomputed on every state change."""
        st = self.states[component_id]
        main = st.get("main_price")
        if not isinstance(main, Mapping) or not isinstance(main.get("amount_minor"), int):
            return
        total = main["amount_minor"]
        for bump in st.get("bumps") or []:
            price = bump.get("price") if isinstance(bump, Mapping) else None
            if isinstance(price, Mapping) and bump.get("selected") is True \
                    and isinstance(price.get("amount_minor"), int):
                total += price["amount_minor"]
        st["native_totals"] = {"currency": main.get("currency"), "total_minor": total}


class _PreselectDriver(_FakeDriver):
    """A buggy platform component that reports every bump as selected —
    the silent-extra-purchase failure the contract must refuse."""

    def get_state(self, scope: FrameScope, component_id: str) -> Optional[Mapping[str, Any]]:
        state = super().get_state(scope, component_id)
        if state is None:
            return None
        bumps = state.get("bumps") or []
        return {**state, "bumps": [{**b, "selected": True} for b in bumps]}


def _price(product: str = "prod_1", price_id: str = "price_1",
           amount: int = 4900, currency: str = "USD",
           billing: str = "one_time", interval: Optional[str] = None,
           trial: Optional[int] = None) -> PriceRef:
    return PriceRef(product, price_id, amount, currency, billing, interval, trial)


def _self_check() -> int:
    checks = 0

    def ok(cond: bool, what: str) -> None:
        nonlocal checks
        assert cond, f"FAIL: {what}"
        checks += 1

    def refused(exc: type, fn: Any, what: str) -> None:
        nonlocal checks
        try:
            fn()
        except exc:
            checks += 1
            return
        except Exception as other:  # noqa: BLE001
            raise AssertionError(f"FAIL: {what}: wrong error {other!r}")
        raise AssertionError(f"FAIL: {what}: accepted, expected {exc.__name__}")

    scope = FrameScope("tab_1", "frame_1")

    # 1 — price reference contract (exact W8D field set)
    ref = _price()
    ok(set(ref.as_fields()) == set(PRICE_REF_FIELDS), "price ref fields == W8D as_price_ref_fields")
    ok(validate_price_ref(ref.as_fields()) == ref, "round trip via validate_price_ref")
    refused(SpecError, lambda: validate_price_ref({k: v for k, v in ref.as_fields().items()
                                                   if k != "trial_days"}), "missing field refused")
    refused(SpecError, lambda: validate_price_ref({**ref.as_fields(), "surcharge": 1}),
            "invented field refused")
    refused(SpecError, lambda: _price(amount=True), "boolean amount refused")
    refused(SpecError, lambda: _price(amount=-1), "negative amount refused")
    refused(SpecError, lambda: _price(billing="recurring"), "recurring without interval refused")
    refused(SpecError, lambda: _price(billing="trial_then_recurring"),
            "trial without trial_days refused")
    refused(SpecError, lambda: _price(billing="weekly"), "unknown billing_type refused")
    refused(SpecError, lambda: _price(billing="one_time", trial=7), "one_time with trial refused")

    # 2 — raw card data never accepted
    ok(assert_no_card_data({"main_price": ref.as_fields()}) is None, "clean payload passes")
    refused(CardDataRefused, lambda: assert_no_card_data({"card_number": "4111"}),
            "card_number refused")
    refused(CardDataRefused, lambda: assert_no_card_data({"payment": {"cvv": "123"}}),
            "nested cvv refused")

    # 3 — explicit scope only
    refused(SpecError, lambda: FrameScope("", "frame_1"), "empty tab_id refused")
    refused(SpecError, lambda: OrderComponentExecutor(_FakeDriver([]), "tab_1",
                                                      ComponentFamily("f", 2, False)),
            "non-FrameScope refused")

    # 4 — targeting: real ids, no first-match
    catalog = [{"component_id": "chk_real_1", "kind": "checkout"},
               {"component_id": "form_real_9", "kind": "order_form"}]
    driver = _FakeDriver(catalog, {"chk_real_1": {"main_price": ref.as_fields(), "bumps": []}})
    ex = OrderComponentExecutor(driver, scope, ComponentFamily("checkout_v2", 2, False))
    ok(ex.resolve_component("chk_real_1")["kind"] == "checkout", "unique real id resolves")
    refused(ComponentNotFound, lambda: ex.resolve_component("chk_missing"),
            "missing component id refused")
    refused(SpecError, lambda: ex.resolve_component("form_real_9", "checkout"),
            "wrong component kind refused")
    dup = _FakeDriver(catalog + [{"component_id": "chk_real_1", "kind": "checkout"}])
    ex_dup = OrderComponentExecutor(dup, scope, ComponentFamily("checkout_v2", 2, False))
    refused(AmbiguousTarget, lambda: ex_dup.resolve_component("chk_real_1"),
            "duplicate component id refused, never first-match")

    # 5 — bind real price to real checkout component id, verified by read-back
    rec = ex.bind_main_price("chk_real_1", _price())
    ok(rec.state == "bound-verified", "bind claims bound-verified")
    ok(rec.op.readback == "verified" and rec.op.target == "chk_real_1",
      "op record names real target + verified readback")
    ok(driver.states["chk_real_1"]["main_price"]["native_price_id"] == "price_1",
      "real price id persisted on real component id")
    refused(SpecError, lambda: ex.bind_main_price("chk_real_1", ref.as_fields()),
            "raw mapping refused by bind (must be PriceRef)")

    # 6 — read-back drift is refused and never claimed bound
    drift = _FakeDriver(catalog, {"chk_real_1": {"main_price": ref.as_fields(), "bumps": []}})
    drift.drift["chk_real_1"] = {
        "main_price": {**ref.as_fields(), "native_price_id": "price_EVIL"}}
    ex_drift = OrderComponentExecutor(drift, scope, ComponentFamily("checkout_v2", 2, False))
    refused(ReadbackMismatch, lambda: ex_drift.bind_main_price("chk_real_1", _price()),
            "drifted main price readback refused")
    ok(ex_drift.ops[-1].readback == "mismatch-refused", "mismatch recorded, not verified")

    # 7 — bump attach: unselected, family limits, accurate terms
    bump = BumpAttach("offer_a", "Headline", "Because reasons", _price("prod_2", "price_2", 900))
    rec = ex.attach_bump("chk_real_1", bump)
    ok(rec.state == "bound-verified", "bump attach verified")
    stored_bumps = driver.states["chk_real_1"]["bumps"]
    ok(stored_bumps[0]["selected"] is False, "bump attached UNSELECTED (never preselected)")
    ok(stored_bumps[0]["price"]["native_price_id"] == "price_2", "bump carries real price id")
    refused(SpecError, lambda: ex.attach_bump(
        "chk_real_1", BumpAttach("offer_a", "H", "B", _price("prod_3", "price_3", 500))),
        "duplicate offer_id refused")
    refused(SpecError, lambda: ex.attach_bump(
        "chk_real_1", BumpAttach("offer_b", "H", "B", _price("prod_2", "price_2", 900))),
        "duplicate native price refused (never charge twice)")
    refused(SpecError, lambda: ex.attach_bump(
        "chk_real_1", BumpAttach("offer_b", "H", "B", _price("prod_3", "price_3", 500, "EUR"))),
        "bump currency mismatch refused")
    refused(SpecError, lambda: BumpAttach("offer_b", "H", "B",
                                          _price("prod_3", "price_3", 500, billing="recurring",
                                                 interval="month")),
            "recurring bump without disclosure refused")
    refused(UnsupportedState, lambda: ex.attach_bump(
        "chk_real_1", BumpAttach("offer_b", "H", "B",
                                 _price("prod_3", "price_3", 500, billing="recurring",
                                        interval="month", trial=None),
                                 disclosure_text="Recurring terms")),
            "recurring bump on non-recurring family refused")
    ex1 = OrderComponentExecutor(_FakeDriver(
        catalog, {"chk_real_1": {"main_price": ref.as_fields(), "bumps": []}}),
        scope, ComponentFamily("checkout_v1", 1, False))
    ex1.attach_bump("chk_real_1", bump)
    refused(UnsupportedState, lambda: ex1.attach_bump(
        "chk_real_1", BumpAttach("offer_b", "H", "B", _price("prod_3", "price_3", 500))),
        "family max_bumps=1 second attach refused")
    ok(OrderComponentExecutor(_FakeDriver(catalog), scope,
                              ComponentFamily("checkout_v2", 2, False))._family.max_bumps == 2,
       "family limits taken as declared (never invented)")

    # 8 — a component that attaches preselected is refused
    pre = _PreselectDriver(catalog, {"chk_real_1": {"main_price": ref.as_fields(), "bumps": []}})
    ex_pre = OrderComponentExecutor(pre, scope, ComponentFamily("checkout_v2", 2, False))
    refused(ReadbackMismatch, lambda: ex_pre.attach_bump("chk_real_1", bump),
            "preselected bump readback refused (no silent extra purchase)")

    # 9 — explicit selection state, read back
    rec = ex.set_bump_selected("chk_real_1", "offer_a", True)
    ok(rec.state == "bound-verified", "explicit select verified")
    ok(driver.states["chk_real_1"]["bumps"][0]["selected"] is True, "selection state persisted")
    refused(SpecError, lambda: ex.set_bump_selected("chk_real_1", "offer_zzz", True),
            "unknown offer select refused")
    refused(SpecError, lambda: ex.set_bump_selected("chk_real_1", "offer_a", "yes"),
            "non-boolean selection refused")
    flip = _FakeDriver(catalog, {"chk_real_1": {
        "main_price": ref.as_fields(), "bumps": [bump.as_fields()]}})
    ex_flip = OrderComponentExecutor(flip, scope, ComponentFamily("checkout_v2", 2, False))
    flip.drift["chk_real_1"] = {"bumps": [bump.as_fields()]}
    refused(ReadbackMismatch, lambda: ex_flip.set_bump_selected("chk_real_1", "offer_a", True),
            "selection readback drift refused")

    # 10 — Required/Hidden set AND read back; blind toggle impossible
    rec = ex.set_field_state("chk_real_1", "email", required=True, hidden=False)
    ok(rec.state == "bound-verified", "field state set+readback verified")
    ok(driver.states["chk_real_1"]["field_states"]["email"] == {"required": True, "hidden": False},
       "explicit true/false persisted for both states")
    refused(SpecError, lambda: ex.set_field_state("chk_real_1", "email"),
            "no requested state refused (blind toggle impossible)")
    refused(SpecError, lambda: ex.set_field_state("chk_real_1", "email", required="true"),
            "non-boolean required refused")
    hid = _FakeDriver(catalog, {"chk_real_1": {"main_price": ref.as_fields(), "bumps": []}})
    ex_hid = OrderComponentExecutor(hid, scope, ComponentFamily("checkout_v2", 2, False))
    hid.drift["chk_real_1"] = {"field_states": {"email": {"required": False, "hidden": False}}}
    refused(ReadbackMismatch,
            lambda: ex_hid.set_field_state("chk_real_1", "email", required=True),
            "field state readback drift refused")

    # 11 — native totals reconciled, never simulated
    totals = ex.read_native_totals("chk_real_1")
    ok(totals["total_minor"] == 4900 + 900 and totals["currency"] == "USD",
       "totals = main + selected bump, minor units")
    ok(totals["line_items"] == (("main", 4900), ("offer_a", 900)), "native line items exact")
    ex.set_bump_selected("chk_real_1", "offer_a", False)
    ok(ex.read_native_totals("chk_real_1")["total_minor"] == 4900,
       "deselect removes the bump line (native add/remove)")
    tot_drift = _FakeDriver(catalog, {"chk_real_1": {
        "main_price": ref.as_fields(), "bumps": [],
        "native_totals": {"currency": "USD", "total_minor": 1}}})
    ex_tot = OrderComponentExecutor(tot_drift, scope, ComponentFamily("checkout_v2", 2, False))
    refused(ReadbackMismatch, lambda: ex_tot.read_native_totals("chk_real_1"),
            "drifted native totals refused")
    refused(SpecError, lambda: ex.read_native_totals("chk_real_1", 0), "quantity 0 refused")

    # 12 — W8D ComponentIO interop (products_prices.bind_price_to_checkout seam)
    io = CheckoutComponentIO(ex)
    ok(io.get_checkout_price("chk_real_1") == ref.as_fields(),
       "ComponentIO get returns the real bound price fields")
    ok(io.get_checkout_price("chk_absent") is None, "ComponentIO get on unknown id returns None")
    io.set_checkout_price("chk_real_1", _price("prod_1", "price_9", 7700).as_fields())
    observed = io.get_checkout_price("chk_real_1")
    # exact comparison loop W8D runs after set_checkout_price:
    want = _price("prod_1", "price_9", 7700).as_fields()
    ok(isinstance(observed, Mapping) and all(observed.get(k) == v for k, v in want.items()),
       "W8D bind comparison loop passes against real component state")
    io_drift = CheckoutComponentIO(OrderComponentExecutor(
        _FakeDriver(catalog, {"chk_real_1": {"main_price": ref.as_fields()}}), scope,
        ComponentFamily("checkout_v2", 2, False)))
    io_drift._ex._driver.drift["chk_real_1"] = {
        "main_price": {**want, "amount_minor": 1}}
    got = io_drift.get_checkout_price("chk_real_1")
    drift_caught = not all(got.get(k) == v for k, v in want.items())
    ok(drift_caught, "W8D bind comparison loop catches component drift")

    # 13 — every executed operation is recorded
    ok(all(op.readback in ("verified", "mismatch-refused", "not-attempted")
           for op in ex.ops), "op readback vocabulary honored")
    ok(any(op.readback == "mismatch-refused" for op in ex_drift.ops),
       "refusals recorded, not silently dropped")

    print(f"OK order_components self-check: {checks} assertions")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_check())
