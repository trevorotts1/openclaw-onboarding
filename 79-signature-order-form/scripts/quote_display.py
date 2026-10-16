"""S79-02 normalized offer/quote display + billing display audit (fixture level).

Doc 09 section 3: displayed and submitted purchase terms must match the
verified native product/price objects; record amount due now, future
installments/renewal, trial period, currency, and discount/tax/shipping
policy. Doc 02 section 3: integer minor units, never floating-point dollars,
never hardcode two decimal places for every currency, the processor's quote
is authoritative for tax/discount/shipping/final charge (this module formats
and audits display state only; it never computes a processor total).
"""
from __future__ import annotations

from dataclasses import dataclass


class DisplayError(ValueError):
    pass


def format_minor(amount_minor: int, currency: str, exponent: int) -> str:
    """Format integer minor units using the currency's own exponent.
    USD exponent 2: 12400 -> 'USD 124.00'. JPY exponent 0: 12400 -> 'JPY 12,400'.
    KWD exponent 3: 12400 -> 'KWD 12.400'."""
    if not isinstance(amount_minor, int) or isinstance(amount_minor, bool):
        raise DisplayError("amount must be integer minor units")
    if exponent not in (0, 1, 2, 3):
        raise DisplayError("currency exponent must be 0 to 3")
    sign = "-" if amount_minor < 0 else ""
    digits = str(abs(amount_minor))
    if exponent == 0:
        whole, frac = digits, ""
    else:
        digits = digits.rjust(exponent + 1, "0")
        whole, frac = digits[:-exponent], digits[-exponent:]
    whole_fmt = f"{int(whole):,}"
    return f"{currency} {sign}{whole_fmt}" + (f".{frac}" if exponent else "")


@dataclass(frozen=True)
class DisplayPrice:
    """A price as verified from the native product/price object."""
    offer_id: str
    currency: str
    currency_exponent: int
    amount_minor: int
    billing_type: str = "one_time"
    amount_due_now_minor: int | None = None
    schedule: tuple = ()  # ((sequence, due, amount_minor), ...)
    recurring_interval: str | None = None
    trial_period: str | None = None
    tax_policy_ref: str | None = None
    shipping_policy_ref: str | None = None
    discount_policy_ref: str | None = None
    source_verified: bool = False

    def __post_init__(self) -> None:
        if not self.source_verified:
            raise DisplayError(
                "display may only be built from verified native price objects (doc 09 section 3)")
        if not isinstance(self.amount_minor, int) or isinstance(self.amount_minor, bool):
            raise DisplayError("amount_minor must be an integer")
        if self.amount_minor < 0:
            raise DisplayError("amount_minor cannot be negative (review defect B3)")
        if self.amount_due_now_minor is None:
            object.__setattr__(self, "amount_due_now_minor",
                               self.amount_minor if self.billing_type == "one_time" else 0)
        if self.amount_due_now_minor < 0:
            raise DisplayError("amount due now cannot be negative (review defect B3)")
        if any(entry[2] < 0 for entry in self.schedule):
            # Review defect N1: a negative installment is not a price,
            # even when the schedule sum happens to balance.
            raise DisplayError("schedule entries cannot be negative")
        scheduled = sum(entry[2] for entry in self.schedule)
        if self.schedule and self.amount_due_now_minor + scheduled != self.amount_minor:
            # Review defect B2: this consistency check must run for every
            # billing type, not only one_time.
            raise DisplayError("schedule plus due-now must equal the total contract amount")
        if self.billing_type in ("recurring", "trial_then_recurring") and not self.recurring_interval:
            raise DisplayError("recurring price requires a recurring interval for display")
        if self.billing_type == "trial_then_recurring" and not self.trial_period:
            raise DisplayError("trial price requires a trial period for display")


@dataclass(frozen=True)
class BillingDisplay:
    lines: tuple  # ((label, formatted_amount), ...)
    due_now_formatted: str
    future_formatted: tuple
    disclosures: tuple
    currency: str

    def as_dict(self) -> dict:
        return {"lines": list(self.lines), "due_now": self.due_now_formatted,
                "future": list(self.future_formatted),
                "disclosures": list(self.disclosures), "currency": self.currency}


def build_billing_display(main: DisplayPrice, bump: DisplayPrice | None,
                          bump_selected: bool) -> BillingDisplay:
    if bump is not None and bump.currency != main.currency:
        raise DisplayError("bump currency does not match main offer currency")
    if bump is not None and bump.currency_exponent != main.currency_exponent:
        # Review defect B1: same currency code with a different exponent
        # means the two minor-unit scales differ; adding them would
        # produce a wrong displayed total.
        raise DisplayError("bump currency exponent does not match main offer exponent")
    fmt = lambda amt, p=main: format_minor(amt, p.currency, p.currency_exponent)  # noqa: E731
    lines = [(main.offer_id, fmt(main.amount_minor))]
    due_now = main.amount_due_now_minor
    future_entries = [entry for entry in main.schedule if entry[1] != "now"]
    if bump is not None and bump_selected:
        lines.append((bump.offer_id, fmt(bump.amount_minor, bump)))
        due_now += bump.amount_due_now_minor
        # Review defect B2: a selected bump's own future installments are
        # part of the display, not silently dropped.
        future_entries += [entry for entry in bump.schedule if entry[1] != "now"]
    future = tuple(fmt(entry[2]) for entry in future_entries)
    disclosures = []
    if main.billing_type == "trial_then_recurring":
        disclosures.append(f"trial:{main.trial_period}")
    if main.billing_type in ("recurring", "trial_then_recurring"):
        disclosures.append(f"recurring:{main.recurring_interval}")
    if bump is not None and bump_selected and bump.billing_type != "one_time":
        disclosures.append(f"bump_recurring:{bump.recurring_interval}")
    for ref, label in ((main.tax_policy_ref, "tax"), (main.shipping_policy_ref, "shipping"),
                       (main.discount_policy_ref, "discount")):
        if ref:
            disclosures.append(f"{label}_policy:{ref}")
    return BillingDisplay(lines=tuple(lines), due_now_formatted=fmt(due_now),
                          future_formatted=future, disclosures=tuple(disclosures),
                          currency=main.currency)


def audit_display(display: BillingDisplay, native_main: DisplayPrice,
                  native_bump: DisplayPrice | None, bump_selected: bool) -> list:
    """Billing display audit (doc 09 section 9): rebuild the expected display
    from the native records and diff. Returns mismatch descriptions; an
    empty list is a pass."""
    try:
        expected = build_billing_display(native_main, native_bump, bump_selected)
    except DisplayError as exc:
        return [f"native record cannot build a display: {exc}"]
    mismatches = []
    if display.currency != expected.currency:
        mismatches.append(f"currency differs: displayed {display.currency} vs native {expected.currency}")
    if display.lines != expected.lines:
        mismatches.append(f"lines differ: displayed {display.lines} vs native {expected.lines}")
    if display.due_now_formatted != expected.due_now_formatted:
        mismatches.append(f"due-now differs: displayed {display.due_now_formatted} vs native {expected.due_now_formatted}")
    if display.future_formatted != expected.future_formatted:
        mismatches.append("future installment display differs from native schedule")
    if display.disclosures != expected.disclosures:
        mismatches.append(f"disclosures differ: displayed {display.disclosures} vs native {expected.disclosures}")
    return mismatches
