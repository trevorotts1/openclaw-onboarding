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

Stdlib only. Loaded by path (the skill folders are not importable package names).
"""

from __future__ import annotations

from typing import Optional

BILLING_TYPES = ("one_time", "recurring", "installment", "trial")

# record billing_type -> Skill 79 price_choice billing_type. None = 79 has no such type.
CHECKOUT_BILLING = {"one_time": "one_time", "recurring": "recurring", "trial": "trial_then_recurring",
                    "installment": None}

PAYMENT_PLANS_UNSUPPORTED = "payment plans are not supported in this release"

# D-D: installment and trial billing are not carried by the Skill 79 checkout request in this
# release, so the plan is refused when it is built, not at checkout after the client approved it.
PLAN_TIME_REFUSED = ("installment", "trial")


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
