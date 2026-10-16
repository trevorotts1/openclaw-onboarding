"""S79-06 native binding preparation: location capability matrix (fixture level).

Sources: doc 09 section 7 (native transaction boundary and capability
matrix), doc 09 section 6 (an unavailable bump is disabled clearly while
the base purchase stays usable when permitted), doc 09 section 11
(out-of-stock add-on is a required case), doc 05 sections 3 and 9
(capability discovery contract; unknown live behavior is never a pass),
doc 16 sections 1 and 6 (native-element boundary).

Doctrine: a capability that the checkout plan actually uses must be
VERIFIED supported. Unknown or missing values are never assumed
supported: for the native checkout itself and for the main offer's
purchasability that means fail closed; for an optional feature (the bump,
a planned coupon) it means that feature is off; for the authoritative
total display it means the display must not present a final total as
processor-authoritative. A capability the plan does not use is recorded
as unverified-unused and neither blocks nor enables anything.

This is a fixture model of the decision S06's capability evidence feeds.
It performs no native calls and proves nothing about a real location.
"""
from __future__ import annotations

from dataclasses import dataclass


class CapabilityError(ValueError):
    pass


def _check_bool(name: str, value) -> None:
    if value is not None and not isinstance(value, bool):
        raise CapabilityError(f"capability {name} must be true, false, or unknown (None)")


@dataclass(frozen=True)
class LocationCapabilityRecord:
    """Capability evidence for one location, as supplied by S06.
    Every field defaults to None = unknown."""
    native_checkout_present: bool | None = None
    order_bump_supported: bool | None = None
    coupons_supported: bool | None = None
    tax_shipping_native: bool | None = None
    out_of_stock_signaling: bool | None = None
    main_offer_in_stock: bool | None = None
    bump_in_stock: bool | None = None

    def __post_init__(self) -> None:
        for name in ("native_checkout_present", "order_bump_supported",
                     "coupons_supported", "tax_shipping_native",
                     "out_of_stock_signaling", "main_offer_in_stock",
                     "bump_in_stock"):
            _check_bool(name, getattr(self, name))


@dataclass(frozen=True)
class CapabilityDecision:
    verdict: str  # render | render_degraded | fail_closed
    submission_allowed: bool
    bump_state: str  # offered_unchecked | disabled_unavailable | not_configured
    features_off: tuple
    reasons: tuple
    unverified_unused: tuple


def evaluate_capabilities(record: LocationCapabilityRecord, *,
                          bump_configured: bool,
                          coupon_planned: bool = False) -> CapabilityDecision:
    fail_reasons: list[str] = []
    features_off: list[str] = []
    degrade_reasons: list[str] = []
    unverified_unused: list[str] = []

    # The native checkout is the transaction boundary itself (doc 09
    # section 7). Absent or unknown means there is nothing lawful to
    # render: never substitute a homemade form.
    if record.native_checkout_present is not True:
        fail_reasons.append(
            "native checkout is not verified present; checkout fails closed "
            "rather than rendering a substitute payment form")

    # Stock facts count only when the location can actually signal them.
    # Without verified signaling, recorded stock values are not evidence.
    if record.out_of_stock_signaling is True:
        main_stock = record.main_offer_in_stock
        bump_stock = record.bump_in_stock
    else:
        main_stock = None
        bump_stock = None
        if record.main_offer_in_stock is not None or record.bump_in_stock is not None:
            degrade_reasons.append(
                "stock values recorded but out-of-stock signaling is not "
                "verified; stock values are treated as unknown")

    # The main offer's purchasability gates submission rendering: a known
    # out-of-stock main offer blocks it, and unknown stock is never
    # assumed in stock.
    if main_stock is False:
        fail_reasons.append("main offer is out of stock; submission rendering is blocked")
    elif main_stock is not True:
        fail_reasons.append("main offer stock is unknown; purchasability is never assumed")

    # The bump is optional (doc 09 section 6): unsupported, unknown, or
    # out-of-stock degrades the bump alone to its disabled state and
    # leaves the base purchase usable.
    bump_state = "not_configured"
    if bump_configured:
        bump_state = "offered_unchecked"
        if record.order_bump_supported is not True:
            features_off.append("order_bump")
            bump_state = "disabled_unavailable"
            degrade_reasons.append(
                "order bump support is not verified; the bump renders in "
                "its disabled state and the base purchase stays usable")
        elif bump_stock is not True:
            features_off.append("order_bump")
            bump_state = "disabled_unavailable"
            if bump_stock is False:
                degrade_reasons.append("bump is out of stock; only the bump is disabled")
            else:
                degrade_reasons.append("bump stock is unknown; the bump is never assumed available")

    # Coupons matter only when the approved plan uses one. A planned
    # coupon that is not verified supported is removed from the checkout;
    # it is never promised and silently dropped at the native form.
    if coupon_planned:
        if record.coupons_supported is not True:
            features_off.append("coupons")
            degrade_reasons.append(
                "coupon support is not verified; the coupon feature is off "
                "and no coupon may be promised in checkout copy")
    elif record.coupons_supported is not True:
        unverified_unused.append("coupons_supported")

    # Tax/shipping: the processor quote is authoritative (doc 09 section
    # 3). If native handling is not verified, the checkout may render but
    # must not present a final total as authoritative.
    if record.tax_shipping_native is not True:
        features_off.append("authoritative_total_display")
        degrade_reasons.append(
            "native tax/shipping handling is not verified; the display "
            "must not present a final total as processor-authoritative")

    if record.order_bump_supported is not True and not bump_configured:
        unverified_unused.append("order_bump_supported")

    if fail_reasons:
        # Review defect CM-1: a fail_closed decision must still report the
        # degrade reasons computed in the same pass (fail reasons first,
        # then degrade reasons). Dropping them hid, for example, a
        # simultaneously out-of-stock bump behind a main-offer failure.
        # Verdict, features_off, and submission are unchanged.
        return CapabilityDecision("fail_closed", False, bump_state,
                                  tuple(features_off),
                                  tuple(fail_reasons) + tuple(degrade_reasons),
                                  tuple(unverified_unused))
    if features_off:
        return CapabilityDecision("render_degraded", True, bump_state,
                                  tuple(features_off), tuple(degrade_reasons),
                                  tuple(unverified_unused))
    return CapabilityDecision("render", True, bump_state, (),
                              ("all capabilities the plan uses are verified supported",),
                              tuple(unverified_unused))
