"""One billing vocabulary for the launch family (Skills 49, 78, 79, 83).

Before this file the same facts lived in four places: the record's billing types, the
record -> Skill 79 translation (offer_mapper), Skill 83's own payment-plan refusal text and
Skill 83's raw ``billing_type`` copy at checkout. They disagreed (an ``installment`` price
was legal in 49/71/78 and impossible in 79/83, and a client learned it at checkout).

  BILLING_TYPES              what a launch record price may say
  CHECKOUT_BILLING           record billing_type -> Skill 79 price_choice billing_type.
                             None means Skill 79 has no such type, so it is refused.
  PAYMENT_PLANS_UNSUPPORTED  the client-facing refusal sentence, said once
  PLAN_TIME_REFUSED          the types refused when the launch plan is built (before approval)
  plan_time_refusal(t)       the refusal sentence for a plan-time-refused type, else None
  checkout_billing(t)        the one translation; raises BillingError for an unmapped type
  RECURRING_INTERVALS        the billing intervals a recurring price may name (week, month, quarter, year)
  stated_billing(word)       a cadence word ("monthly", "every three months") -> (billing_type, interval)
  interval_word(i)           "month" -> "monthly" (how a buyer reads the cadence)
  price_per_interval(m, i)   "$49" + "month" -> "$49/month" (the one place a recurring price is phrased)
  terms_for_interval(i)      "quarter" -> ("month", 3): the unit + count a billing platform takes

Stdlib only. Loaded by path (the skill folders are not importable package names).
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

BILLING_TYPES = ("one_time", "recurring", "installment", "trial")

# record billing_type -> Skill 79 price_choice billing_type. None = 79 has no such type.
CHECKOUT_BILLING = {"one_time": "one_time", "recurring": "recurring", "trial": "trial_then_recurring",
                    "installment": None}

PAYMENT_PLANS_UNSUPPORTED = "payment plans are not supported in this release"

# D-D: installment and trial billing are not carried by the Skill 79 checkout request in this
# release, so the plan is refused when it is built, not at checkout after the client approved it.
PLAN_TIME_REFUSED = ("installment", "trial")

# A recurring price names how often it bills. The interval is material disclosure (Skill 78 / 79 refuse a
# recurring price without one), so it is carried beside the billing type from the client's own words to the
# checkout, never guessed.
RECURRING_INTERVALS = ("week", "month", "quarter", "year")

# The cadence words a client may say for one offer. A stated word outside this table is refused by name by the
# caller: reading "every other month" as one payment (or as monthly) would invent a commercial fact.
# `installment` is recognised so it can be refused with the shared sentence, not misread as one payment.
_CADENCE_WORDS = {
    "all at once": ("one_time", None), "one time": ("one_time", None), "one-time": ("one_time", None),
    "once": ("one_time", None), "single payment": ("one_time", None), "one payment": ("one_time", None),
    "weekly": ("recurring", "week"), "every week": ("recurring", "week"),
    "monthly": ("recurring", "month"), "every month": ("recurring", "month"),
    "quarterly": ("recurring", "quarter"), "every three months": ("recurring", "quarter"),
    "every quarter": ("recurring", "quarter"),
    "yearly": ("recurring", "year"), "annually": ("recurring", "year"), "annual": ("recurring", "year"),
    "every year": ("recurring", "year"),
    "installment": ("installment", None), "installments": ("installment", None),
    "in parts": ("installment", None), "in parts or trial first": ("installment", None),
    "in parts / trial first": ("installment", None), "trial first": ("installment", None),
}

_INTERVAL_WORDS = {"week": "weekly", "month": "monthly", "quarter": "quarterly", "year": "yearly"}


def stated_billing(word: object) -> Tuple[Optional[str], Optional[str]]:
    """(billing_type, recurring_interval) for a client's cadence word; (None, None) when the word is not
    one this release can carry (the caller refuses it by name; it is never flattened to one payment)."""
    if not isinstance(word, str):
        return None, None
    return _CADENCE_WORDS.get(re.sub(r"\s+", " ", word.strip().casefold()), (None, None))


def interval_word(interval: object) -> str:
    """The interval as a buyer reads it ("monthly"), or the raw value when this module does not know it."""
    if not interval:
        return ""
    return _INTERVAL_WORDS.get(str(interval).strip().casefold(), str(interval))


# The unit and count a billing platform takes for each interval (the native price shape has day/week/month/year
# and a count, no "quarter" unit): a quarter is three months.
_INTERVAL_TERMS = {"week": ("week", 1), "month": ("month", 1), "quarter": ("month", 3), "year": ("year", 1)}


def terms_for_interval(interval: object) -> Tuple[str, int]:
    """(unit, count) for a recurring_interval. Raises BillingError for an interval this release does not carry."""
    key = str(interval or "").strip().casefold()
    if key not in _INTERVAL_TERMS:
        raise BillingError("AF-RECURRING-INTERVAL", f"{interval!r} is not one of {RECURRING_INTERVALS}")
    return _INTERVAL_TERMS[key]


def price_per_interval(money: str, interval: object) -> str:
    """The one phrasing of a recurring price: "$49/month". Raises BillingError for an interval this
    release does not carry, so a page never prints a cadence nobody approved."""
    key = str(interval or "").strip().casefold()
    if key not in RECURRING_INTERVALS:
        raise BillingError("AF-RECURRING-INTERVAL", f"{interval!r} is not one of {RECURRING_INTERVALS}")
    return f"{money}/{key}"


class BillingError(ValueError):
    """A billing type the checkout cannot carry. ``code`` is the stable autofail code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


def plan_time_refusal(billing_type: object) -> Optional[str]:
    """The client-facing sentence when this billing type is refused at plan time, else None."""
    if billing_type in PLAN_TIME_REFUSED:
        return f"{billing_type!r}: {PAYMENT_PLANS_UNSUPPORTED}"
    return None


def checkout_billing(billing_type: object) -> str:
    """The Skill 79 billing type for a record billing type. Unknown or unmapped is refused by name."""
    if billing_type not in CHECKOUT_BILLING:
        raise BillingError("AF-CHECKOUT-BILLING", f"{billing_type!r} is not one of {BILLING_TYPES}")
    mapped = CHECKOUT_BILLING[billing_type]
    if mapped is None:
        raise BillingError("AF-CHECKOUT-BILLING",
                           f"Skill 79 has no checkout billing type for {billing_type!r}; "
                           "refused rather than shown as something else")
    return mapped
