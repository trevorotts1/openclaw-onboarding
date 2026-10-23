"""S79 native checkout/order-bump configuration contract (W8A, stream W8).

Rules enforced here (GHL-DELIVERY-SPEC.md "Commerce (W8)"; S79 docs 02 §3 and
09 §6):

1. Approved products/prices only: every product/price attached to a native
   checkout or order bump must resolve to an approved catalog entry. Catalog
   creation alone is not checkout binding — the binding is the explicit
   `CheckoutConfig` below, keyed by native checkout component id.
2. Accurate terms: the price terms shown to the buyer must match the verified
   approved price object exactly (amount in integer minor units, currency,
   billing type, recurrence). Unknown price is never zero; dollars floats are
   never accepted.
3. Intentional selection: a bump starts unselected and changes state only
   through an explicit select/deselect action. There is no API here that
   attaches an already-selected bump to a fresh checkout — a silently
   preselected extra purchase is unrepresentable.
4. Native totals: totals are built from native line items in integer minor
   units; selecting a bump adds its native line item, deselecting removes it.
   No simulated payment, no charges, no card handling — configuration and
   arithmetic only.
5. Component-family limits: the selected component family declares its
   multiple-bump and recurring-product limits (from the W2 capability
   inventory, never invented here); configurations exceeding them fail closed.

Run `python3 skills/79-checkout/order_bumps.py` for the assert-based self-check.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, Mapping, Optional, Tuple

BILLING_TYPES = ("one_time", "recurring", "trial_then_recurring")


class OrderBumpError(ValueError):
    """Contract violation: unapproved product/price, inaccurate terms,
    non-intentional selection, bad totals arithmetic, or family limit breach."""


def _require_text(value: str, what: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise OrderBumpError(f"{what} must be a non-empty string")


def _require_minor_units(amount_minor: int, what: str) -> None:
    # bool is an int subclass; a boolean amount is always a mistake.
    if not isinstance(amount_minor, int) or isinstance(amount_minor, bool):
        raise OrderBumpError(f"{what} must be integer minor units, never float dollars")
    if amount_minor < 0:
        raise OrderBumpError(f"{what} cannot be negative; unknown price is not zero")


@dataclass(frozen=True)
class PriceRef:
    """A native product/price reference with its exact verified terms."""

    native_product_id: str
    native_price_id: str
    amount_minor: int
    currency: str
    billing_type: str = "one_time"  # one_time | recurring | trial_then_recurring
    recurring_interval: Optional[str] = None  # e.g. "month", required iff recurring
    trial_days: Optional[int] = None  # required iff trial_then_recurring

    def __post_init__(self) -> None:
        _require_text(self.native_product_id, "native_product_id")
        _require_text(self.native_price_id, "native_price_id")
        _require_minor_units(self.amount_minor, "amount_minor")
        _require_text(self.currency, "currency")
        if self.billing_type not in BILLING_TYPES:
            raise OrderBumpError(f"unknown billing_type: {self.billing_type}")
        if self.billing_type == "recurring":
            _require_text(self.recurring_interval or "", "recurring_interval for recurring price")
            if self.trial_days is not None:
                raise OrderBumpError("recurring price must not carry trial_days")
        elif self.billing_type == "trial_then_recurring":
            _require_text(self.recurrent_interval_or_empty(), "recurring_interval for trial_then_recurring price")
            if not isinstance(self.trial_days, int) or isinstance(self.trial_days, bool) or self.trial_days < 1:
                raise OrderBumpError("trial_then_recurring price requires trial_days >= 1")
        else:
            if self.recurring_interval is not None or self.trial_days is not None:
                raise OrderBumpError("one_time price must not carry recurrence terms")

    def recurrent_interval_or_empty(self) -> str:
        return self.recurring_interval or ""

    @property
    def is_recurring(self) -> bool:
        return self.billing_type != "one_time"


@dataclass(frozen=True)
class ApprovedCatalog:
    """Approved products/prices. Only entries recorded here may bind to a
    native checkout; the recorded terms are the accurate-terms source of truth."""

    approval_ref: str
    prices: Mapping[Tuple[str, str], PriceRef]  # (native_product_id, native_price_id) -> approved terms

    def __post_init__(self) -> None:
        _require_text(self.approval_ref, "approval_ref")
        for key, price in self.prices.items():
            if key != (price.native_product_id, price.native_price_id):
                raise OrderBumpError(f"catalog key {key} does not match price identity")

    def verify_approved(self, price: PriceRef) -> None:
        """Fail closed: unapproved products and inaccurate terms are both refusals."""
        approved = self.prices.get((price.native_product_id, price.native_price_id))
        if approved is None:
            raise OrderBumpError(
                f"product/price not in approved catalog {self.approval_ref}: "
                f"{price.native_product_id}/{price.native_price_id}"
            )
        if approved != price:
            raise OrderBumpError(
                f"inaccurate terms for {price.native_price_id}: displayed terms do not "
                f"match the verified approved price object"
            )


@dataclass(frozen=True)
class ComponentFamily:
    """Native checkout component family limits, declared by the caller from the
    W2 capability inventory. This module never invents platform limits."""

    name: str
    max_bumps: int
    allows_recurring_bumps: bool

    def __post_init__(self) -> None:
        _require_text(self.name, "family name")
        if not isinstance(self.max_bumps, int) or isinstance(self.max_bumps, bool) or self.max_bumps < 0:
            raise OrderBumpError("max_bumps must be an integer >= 0 (0 = bumps unsupported)")


@dataclass(frozen=True)
class BumpConfig:
    """One order-bump attachment to a native checkout. No selection field on
    purpose: selection is explicit state, never baked into configuration."""

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


@dataclass(frozen=True)
class CheckoutConfig:
    """A native checkout with its main purchase and its approved bumps."""

    checkout_component_id: str
    family: ComponentFamily
    main_price: PriceRef
    bumps: Tuple[BumpConfig, ...]
    main_quantity: int = 1

    def __post_init__(self) -> None:
        _require_text(self.checkout_component_id, "checkout_component_id")
        if not isinstance(self.main_quantity, int) or isinstance(self.main_quantity, bool) or self.main_quantity < 1:
            raise OrderBumpError("main_quantity must be an integer >= 1")
        seen: set = {self.main_price.native_price_id}
        for bump in self.bumps:
            if bump.offer_id in {b.offer_id for b in self.bumps if b is not bump}:
                raise OrderBumpError(f"duplicate bump offer_id {bump.offer_id}; never charge twice")
            if bump.price.native_price_id in seen:
                raise OrderBumpError(
                    f"duplicate native price {bump.price.native_price_id}; never charge twice"
                )
            seen.add(bump.price.native_price_id)


def validate_checkout(config: CheckoutConfig, catalog: ApprovedCatalog) -> None:
    """Full contract check. Raises OrderBumpError naming the first violation."""
    catalog.verify_approved(config.main_price)
    for bump in config.bumps:
        catalog.verify_approved(bump.price)
        if bump.price.currency != config.main_price.currency:
            raise OrderBumpError(
                f"bump {bump.offer_id} currency {bump.price.currency} does not match "
                f"checkout currency {config.main_price.currency}"
            )
    if len(config.bumps) > config.family.max_bumps:
        raise OrderBumpError(
            f"family {config.family.name} allows at most {config.family.max_bumps} bump(s), "
            f"got {len(config.bumps)}"
        )
    for bump in config.bumps:
        if bump.price.is_recurring and not config.family.allows_recurring_bumps:
            raise OrderBumpError(
                f"family {config.family.name} does not allow recurring-product bumps "
                f"(bump {bump.offer_id})"
            )


# --- Intentional selection ---------------------------------------------------

@dataclass(frozen=True)
class Selection:
    """Explicit per-bump selection flags. Constructed fresh (all unselected) or
    changed only through `select`; a checkout is never born with a chosen bump."""

    flags: Mapping[str, bool]

    @classmethod
    def fresh(cls, config: CheckoutConfig) -> "Selection":
        return cls(flags={bump.offer_id: False for bump in config.bumps})

    def selected_offer_ids(self) -> Tuple[str, ...]:
        return tuple(offer for offer, on in self.flags.items() if on)


def select(config: CheckoutConfig, selection: Selection, offer_id: str, selected: bool) -> Selection:
    """Explicit select/deselect of one bump. Idempotent, and unknown offers are
    refused rather than silently ignored."""
    if offer_id not in selection.flags:
        raise OrderBumpError(f"offer {offer_id} is not a bump of this checkout")
    if not isinstance(selected, bool):
        raise OrderBumpError("selection change must be an explicit boolean")
    return Selection(flags={**selection.flags, offer_id: selected})


# --- Native totals -----------------------------------------------------------


@dataclass(frozen=True)
class NativeTotals:
    """Native line items and the total, all integer minor units."""

    currency: str
    line_items: Tuple[Tuple[str, int], ...]  # (label, amount_minor)
    total_minor: int


def native_totals(config: CheckoutConfig, selection: Selection, catalog: ApprovedCatalog) -> NativeTotals:
    """Build native totals from approved prices only: main line plus one line
    per explicitly selected bump. Add/remove of a bump is add/remove of its
    native line item."""
    validate_checkout(config, catalog)
    lines = [("main", config.main_price.amount_minor * config.main_quantity)]
    total = lines[0][1]
    for bump in config.bumps:
        if selection.flags.get(bump.offer_id):
            amount = bump.price.amount_minor
            lines.append((bump.offer_id, amount))
            total += amount
    return NativeTotals(currency=config.main_price.currency, line_items=tuple(lines), total_minor=total)


# --- Assert-based self-check -------------------------------------------------

def _self_check() -> int:
    checks = 0

    def ok(cond: bool, what: str) -> None:
        nonlocal checks
        assert cond, what
        checks += 1

    def refused(fn, what: str) -> None:
        nonlocal checks
        try:
            fn()
        except OrderBumpError:
            checks += 1
            return
        raise AssertionError(f"expected refusal: {what}")

    def raised(fn, what: str) -> None:
        nonlocal checks
        try:
            fn()
        except OrderBumpError:
            checks += 1
            return
        raise AssertionError(f"expected OrderBumpError: {what}")

    main = PriceRef("prod_main", "price_main", 9700, "USD")
    bump_price = PriceRef("prod_bump", "price_bump", 2700, "USD")
    catalog = ApprovedCatalog(
        approval_ref="approval-2026-10-23",
        prices={("prod_main", "price_main"): main, ("prod_bump", "price_bump"): bump_price},
    )
    family = ComponentFamily("order_form_v2", max_bumps=1, allows_recurring_bumps=False)
    bump = BumpConfig("offer_bump", "Add the vault", "Lifetime access", bump_price)
    config = CheckoutConfig("chk_1", family, main, (bump,))

    # Approved products/prices + accurate terms: clean config validates.
    validate_checkout(config, catalog)
    ok(True, "clean config validates")

    # Unapproved product is refused.
    unapproved = BumpConfig("offer_x", "X", "Y", PriceRef("prod_x", "price_x", 100, "USD"))
    refused(lambda: validate_checkout(CheckoutConfig("chk_1", family, main, (unapproved,)), catalog),
            "unapproved bump product")

    # Inaccurate terms (amount drift vs approved price) are refused.
    drifted = replace(bump, price=replace(bump_price, amount_minor=2600))
    refused(lambda: validate_checkout(CheckoutConfig("chk_1", family, main, (drifted,)), catalog),
            "inaccurate bump terms")

    # Accurate-terms drift on the main price is refused too.
    refused(lambda: validate_checkout(replace(config, main_price=replace(main, currency="EUR")), catalog),
            "inaccurate main terms")

    # Intentional selection: fresh selection is all unselected, explicit select
    # adds the native line, explicit deselect removes it.
    sel = Selection.fresh(config)
    ok(sel.selected_offer_ids() == (), "fresh selection is unselected")
    totals0 = native_totals(config, sel, catalog)
    ok(totals0.total_minor == 9700 and totals0.line_items == (("main", 9700),), "native totals without bump")
    sel_on = select(config, sel, "offer_bump", True)
    totals1 = native_totals(config, sel_on, catalog)
    ok(totals1.total_minor == 12400, "select adds the native line item")
    ok(totals1.line_items[-1] == ("offer_bump", 2700), "bump line item amount is approved minor units")
    sel_off = select(config, sel_on, "offer_bump", False)
    totals2 = native_totals(config, sel_off, catalog)
    ok(totals2.total_minor == 9700 and len(totals2.line_items) == 1, "deselect removes the native line item")
    ok(select(config, sel_on, "offer_bump", True) == sel_on, "select is idempotent")

    # Unknown offer toggles are refused, never silently ignored.
    refused(lambda: select(config, sel, "offer_ghost", True), "select of unknown offer")

    # Family multiple-bump limit fails closed.
    bump2 = BumpConfig("offer_bump2", "Second", "Also useful", replace(bump_price, native_price_id="price_bump2"))
    catalog2 = ApprovedCatalog(catalog.approval_ref, {**catalog.prices,
                                ("prod_bump", "price_bump2"): replace(bump_price, native_price_id="price_bump2")})
    two = CheckoutConfig("chk_1", family, main, (bump, bump2))
    refused(lambda: validate_checkout(two, catalog2), "family max_bumps=1 exceeded")

    # Family recurring-product limit fails closed; disclosure required either way.
    rec_price = PriceRef("prod_bump", "price_rec", 2700, "USD", "recurring", recurring_interval="month")
    rec_bump = BumpConfig("offer_rec", "Subscribe", "Monthly", rec_price, disclosure_text="Billed $27/month")
    raised(lambda: BumpConfig("offer_rec", "Subscribe", "Monthly", rec_price),
           "recurring bump without disclosure")
    catalog3 = ApprovedCatalog(catalog.approval_ref, {**catalog.prices, ("prod_bump", "price_rec"): rec_price})
    refused(lambda: validate_checkout(CheckoutConfig("chk_1", family, main, (rec_bump,)), catalog3),
            "family forbids recurring bumps")
    family_rec = ComponentFamily("order_form_rec", max_bumps=1, allows_recurring_bumps=True)
    validate_checkout(CheckoutConfig("chk_1", family_rec, main, (rec_bump,)), catalog3)
    ok(True, "recurring bump allowed by family with disclosure")

    # Duplicate native price (double charge) refused at construction;
    # currency mismatch refused at validation.
    raised(lambda: CheckoutConfig("chk_1", family_rec, main, (bump, replace(bump, offer_id="offer_bump_dup"))),
           "duplicate native price")
    eur_bump = BumpConfig("offer_eur", "EUR", "Mismatch", replace(bump_price, native_price_id="price_eur", currency="EUR"))
    catalog4 = ApprovedCatalog(catalog.approval_ref, {**catalog.prices, ("prod_bump", "price_eur"): replace(bump_price, native_price_id="price_eur", currency="EUR")})
    refused(lambda: validate_checkout(CheckoutConfig("chk_1", family_rec, main, (eur_bump,)), catalog4),
            "currency mismatch")

    # Price construction guards: floats/bools/negatives and bad recurrence refused.
    raised(lambda: PriceRef("p", "q", 27.0, "USD"), "float amount")
    raised(lambda: PriceRef("p", "q", True, "USD"), "bool amount")
    raised(lambda: PriceRef("p", "q", -1, "USD"), "negative amount")
    raised(lambda: PriceRef("p", "q", 100, "USD", "recurring"), "recurring without interval")
    raised(lambda: PriceRef("p", "q", 100, "USD", "trial_then_recurring", recurring_interval="month"),
           "trial without trial_days")
    raised(lambda: PriceRef("p", "q", 100, "USD", "one_time", recurring_interval="month"),
           "one_time with recurrence terms")

    return checks


if __name__ == "__main__":
    n = _self_check()
    print(f"self-check OK ({n} assertions)")
