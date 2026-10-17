"""S79 fixture-level order-bump model (L0/L1 only, NOT production payment code).

Implements the pure contract rules from:
- Doc 02 section 3: bump references an approved offer, default unchecked,
  suppress/explain when its entitlement is already included, never charge
  twice, integer minor units, processor quote authoritative in production
  (this module only tests UI/fixture arithmetic).
- Doc 09 section 6: bump config fields, default_selected=false enforced,
  select adds the native line item, deselect removes it and restores quote,
  currency mismatch and included-entitlement cases must fail closed.

No GHL calls, no card handling, no charges. Test-only amounts come from the
packet launch-example.json (BUMP-USD 2700 minor units).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Tuple


class BumpError(ValueError):
    pass


@dataclass(frozen=True)
class PriceChoice:
    price_choice_id: str
    currency: str
    amount_minor: int
    billing_type: str = "one_time"  # one_time | recurring | trial_then_recurring

    def __post_init__(self) -> None:
        if not isinstance(self.amount_minor, int) or isinstance(self.amount_minor, bool):
            raise BumpError("amount_minor must be integer minor units, never float dollars")
        if self.amount_minor < 0:
            raise BumpError("amount_minor cannot be negative; unknown price is not zero")


@dataclass(frozen=True)
class BumpConfig:
    component_id: str
    enabled: bool
    offer_id: str
    price: PriceChoice
    entitlement_ids: FrozenSet[str]
    applicable_main_offer_ids: FrozenSet[str]
    default_selected: bool = False
    quantity_policy: str = "fixed_1"  # fixed_1 | match_main_quantity
    recurring_disclosure_required: bool = False
    # Review gap D4(ii): the bump object must carry its native product/price
    # mapping and that mapping can expire (doc 09 sections 6 and 11).
    native_product_id: str | None = None
    native_price_id: str | None = None
    price_mapping_expires_at: str | None = None  # ISO-8601, compared lexicographically only when caller supplies `now` in the same format

    def __post_init__(self) -> None:
        if self.default_selected is not False:
            raise BumpError("bump must be unchecked by default (doc 09 section 6)")
        if self.price.billing_type != "one_time" and not self.recurring_disclosure_required:
            raise BumpError("recurring/trial bump requires explicit recurring disclosure")


@dataclass(frozen=True)
class Quote:
    main_offer_id: str
    main_price: PriceChoice
    main_quantity: int = 1
    main_entitlement_ids: FrozenSet[str] = frozenset()
    line_items: Tuple[Tuple[str, int], ...] = ()  # (label, amount_minor)
    bump_state: str = "not_offered"  # not_offered | offered_unchecked | selected | suppressed_included | disabled_unavailable
    suppression_source: str | None = None  # included_in_package | previously_purchased (doc 02 section 3 keeps these distinct)

    def __post_init__(self) -> None:
        # Review defect D1 (2026-10-15): quantity was never validated, so a
        # zero-quantity main produced total 0 and a bump could still be
        # charged against zero main units. Doc 02 section 3: unknown is not
        # zero. Fail closed at construction.
        if not isinstance(self.main_quantity, int) or isinstance(self.main_quantity, bool):
            raise BumpError("main_quantity must be an integer")
        if self.main_quantity < 1:
            raise BumpError("main_quantity must be at least 1")

    @property
    def total_minor(self) -> int:
        base = self.main_price.amount_minor * self.main_quantity
        return base + sum(amount for _, amount in self.line_items)

    @property
    def currency(self) -> str:
        return self.main_price.currency


def bump_quantity(config: BumpConfig, main_quantity: int) -> int:
    if config.quantity_policy == "fixed_1":
        return 1
    if config.quantity_policy == "match_main_quantity":
        if main_quantity < 1:
            raise BumpError("main quantity must be at least 1")
        return main_quantity
    raise BumpError(f"unknown quantity policy: {config.quantity_policy}")


def initial_quote(main_offer_id: str, main_price: PriceChoice, main_quantity: int,
                  main_entitlement_ids: FrozenSet[str], config: BumpConfig | None,
                  previously_purchased_entitlement_ids: FrozenSet[str] = frozenset(),
                  now: str | None = None) -> Quote:
    """Build the starting quote. Inclusion suppresses the purchase checkbox.

    `previously_purchased_entitlement_ids` is a DISTINCT input from the main
    package's own entitlements (review gap D4(i), doc 02 section 3): a bump
    whose entitlement was already bought in an earlier order is suppressed
    for a different reason than one included in the selected package, and
    the two sources are recorded separately in `suppression_source`.
    """
    q = Quote(main_offer_id=main_offer_id, main_price=main_price, main_quantity=main_quantity,
              main_entitlement_ids=main_entitlement_ids)
    if config is None or not config.enabled:
        return q
    # Review defect D3 (2026-10-15): a currency mismatch was only detected
    # on a toggle attempt. Fail closed at quote construction instead, per
    # doc 09 section 3 (displayed terms must match verified price objects).
    if config.price.currency != main_price.currency:
        raise BumpError("bump currency does not match main offer currency")
    if main_offer_id not in config.applicable_main_offer_ids:
        return Quote(**{**q.__dict__, "bump_state": "disabled_unavailable"})
    if now is not None and config.price_mapping_expires_at is not None and now > config.price_mapping_expires_at:
        # Expired native price mapping: bump unavailable, base purchase stays
        # usable when permitted (doc 09 section 6 unavailable rule).
        return Quote(**{**q.__dict__, "bump_state": "disabled_unavailable"})
    if config.entitlement_ids & main_entitlement_ids:
        # Doc 02 section 3 / doc 09 section 6: already included, never charge twice.
        return Quote(**{**q.__dict__, "bump_state": "suppressed_included",
                        "suppression_source": "included_in_package"})
    if config.entitlement_ids & previously_purchased_entitlement_ids:
        return Quote(**{**q.__dict__, "bump_state": "suppressed_included",
                        "suppression_source": "previously_purchased"})
    return Quote(**{**q.__dict__, "bump_state": "offered_unchecked"})


def change_main_tier(quote: Quote, config: BumpConfig | None,
                     new_main_offer_id: str, new_main_price: PriceChoice,
                     new_main_entitlement_ids: FrozenSet[str],
                     previously_purchased_entitlement_ids: FrozenSet[str] = frozenset(),
                     now: str | None = None) -> Quote:
    """Re-evaluate bump eligibility after a main-tier change (D4(iii), doc 09
    section 11 required test). A bump that was selected stays selected only
    if it is still offered on the new tier; if the new tier includes it, or
    it no longer applies, or its mapping expired, the line is removed and
    the new state explains why. The selection is never silently carried
    onto a tier where it would double-charge.
    """
    was_selected = quote.bump_state == "selected"
    fresh = initial_quote(new_main_offer_id, new_main_price, quote.main_quantity,
                          new_main_entitlement_ids, config,
                          previously_purchased_entitlement_ids, now)
    if was_selected and config is not None and fresh.bump_state == "offered_unchecked":
        return set_bump_selected(fresh, config, True)
    return fresh


def set_bump_selected(quote: Quote, config: BumpConfig, selected: bool) -> Quote:
    """Toggle the bump. Idempotent: selecting twice adds one line; deselect restores."""
    if quote.bump_state == "suppressed_included":
        if selected:
            raise BumpError("bump already included in selected package; no purchase checkbox")
        return quote
    if quote.bump_state not in ("offered_unchecked", "selected"):
        raise BumpError(f"bump cannot be toggled from state {quote.bump_state}")
    if config.price.currency != quote.currency:
        raise BumpError("bump currency does not match main offer currency")
    without_bump = tuple(li for li in quote.line_items if li[0] != config.offer_id)
    if not selected:
        return Quote(**{**quote.__dict__, "line_items": without_bump, "bump_state": "offered_unchecked"})
    qty = bump_quantity(config, quote.main_quantity)
    amount = config.price.amount_minor * qty
    return Quote(**{**quote.__dict__, "line_items": without_bump + ((config.offer_id, amount),),
                    "bump_state": "selected"})
