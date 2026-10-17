"""Skill 82 tests — DOC-04 + DOC-05: trial and recurring billing display.

Branch-matrix rows DOC-04 (trial terms) and DOC-05 (recurring /
multiple payment schedules) were contract-only because the packet
catalog carries no trial or recurring price to build a fixture from.
That gates a packet-derived fixture, not these tests: the resolver
and renderer consume the *snapshot's* billing terms, and snapshot
billing terms here are hand-authored TEST ONLY data — the same basis
as every other fixture in this suite. No packet-catalog price is
used or needed.

Proved here, end to end (snapshot -> resolver -> render -> validate):

- recurring terms pass through the resolver verbatim and render
  exactly as the snapshot states them: interval plus every schedule
  entry with its own amount (DOC-05, incl. one product whose later
  schedule entries differ in amount);
- a trial-then-recurring item renders its trial length and its
  first-charge and renewal dates/amounts exactly as stated (DOC-04);
- trial terms are never invented: a snapshot carrying none renders
  no trial text at all (DOC-04, "shown only when the verified
  snapshot carries them").

All data is TEST ONLY. Stdlib unittest only.
"""

import copy
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SKILL_DIR = TESTS_DIR.parent
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from test_thank_you import (  # noqa: E402
    IDENTITY,
    OFFERS,
    make_fulfillment,
    make_snapshot,
)
from thank_you_resolver import resolve_order_view  # noqa: E402
from validate_thank_you import validate_thank_you  # noqa: E402
from render_thank_you import format_amount, render_thank_you  # noqa: E402

BRAND = {
    "brand_name": "TEST ONLY BRAND",
    "colors": {"primary": "#123456", "accent": "#057a55",
               "background": "#ffffff", "text": "#111111"},
    "support": {"label": "Contact TEST ONLY support",
                "email": "support@example.test"},
    "manage_purchase_url": "https://example.test/manage",
}

# Hand-authored TEST ONLY billing terms. Amounts/dates below exist
# only in these terms; nothing is read from a packet price.
RECURRING_BILLING = {
    "billing_type": "recurring",
    "recurring_interval": "month",
    "schedule": [
        {"label": "First charge", "amount_minor": 9700},
        {"label": "Renews 2026-11-15", "amount_minor": 9700},
        {"label": "Renews 2026-12-15", "amount_minor": 10700},
    ],
    "terms_source": "TEST-ONLY snapshot billing terms",
}
RECURRING_TEXT = (
    "Recurring — every month (First charge: $97.00; "
    "Renews 2026-11-15: $97.00; Renews 2026-12-15: $107.00)"
)

TRIAL_BILLING = {
    "billing_type": "trial_then_recurring",
    "recurring_interval": "month",
    "schedule": [
        {"label": "Free trial — 14 days, $0 due today"},
        {"label": "First charge 2026-10-30", "amount_minor": 4700},
        {"label": "Renews 2026-11-30", "amount_minor": 4700},
    ],
    "terms_source": "TEST-ONLY snapshot billing terms",
}
TRIAL_TEXT = (
    "Recurring — every month (Free trial — 14 days, $0 due today; "
    "First charge 2026-10-30: $47.00; Renews 2026-11-30: $47.00)"
)


def snapshot_with_billing(offer_ids, billing_by_offer):
    snapshot = make_snapshot(offer_ids)
    for line in snapshot["line_items"]:
        if line["offer_id"] in billing_by_offer:
            line["billing"] = copy.deepcopy(billing_by_offer[line["offer_id"]])
    return snapshot


class RecurringBillingDisplayTest(unittest.TestCase):
    def test_recurring_terms_pass_through_resolver_verbatim(self):
        snapshot = snapshot_with_billing(["MAIN-A"],
                                         {"MAIN-A": RECURRING_BILLING})
        view = resolve_order_view(snapshot, make_fulfillment(snapshot),
                                  expected_identity=IDENTITY)
        self.assertEqual(view["items"][0]["billing"], RECURRING_BILLING)
        # Schedule entries are display terms only: the paid total is
        # still the verified line amount, never a schedule sum.
        self.assertEqual(view["totals"]["paid_total_minor"], 9700)

    def test_recurring_schedule_renders_exactly_as_stated(self):
        snapshot = snapshot_with_billing(["MAIN-A"],
                                         {"MAIN-A": RECURRING_BILLING})
        view = resolve_order_view(snapshot, make_fulfillment(snapshot),
                                  expected_identity=IDENTITY)
        html_out = render_thank_you(view, BRAND)
        # Interval and every entry, each with its own amount — the
        # third entry's different amount proves entries render
        # individually, not as a repeated first amount.
        self.assertIn(RECURRING_TEXT, html_out)
        self.assertNotIn("One-time charge", html_out)

    def test_recurring_view_validates_clean(self):
        snapshot = snapshot_with_billing(["MAIN-A"],
                                         {"MAIN-A": RECURRING_BILLING})
        fulfillment = make_fulfillment(snapshot)
        view = resolve_order_view(snapshot, fulfillment,
                                  expected_identity=IDENTITY)
        self.assertEqual(validate_thank_you(view, snapshot, fulfillment), [])


class TrialBillingDisplayTest(unittest.TestCase):
    def _trial_view(self):
        # DOC-04's case shape: a trial D1 with renewal, next to the
        # ordinary one-time main purchase.
        snapshot = snapshot_with_billing(["MAIN-A", "D1"],
                                         {"D1": TRIAL_BILLING})
        fulfillment = make_fulfillment(snapshot)
        view = resolve_order_view(snapshot, fulfillment,
                                  expected_identity=IDENTITY)
        return snapshot, fulfillment, view

    def test_trial_terms_pass_through_resolver_verbatim(self):
        _snapshot, _fulfillment, view = self._trial_view()
        d1 = next(i for i in view["items"] if i["offer_id"] == "D1")
        self.assertEqual(d1["billing"], TRIAL_BILLING)

    def test_trial_then_recurring_renders_exactly_as_stated(self):
        _snapshot, _fulfillment, view = self._trial_view()
        html_out = render_thank_you(view, BRAND)
        # Trial length, first-charge date and amount, renewal date
        # and amount — exactly the snapshot's stated terms.
        self.assertIn(TRIAL_TEXT, html_out)
        self.assertIn("14 days", html_out)
        # The item's own verified amount still renders in its row,
        # and the one-time main keeps its own billing line.
        d1_amount = OFFERS["D1"]["prices"][0]["amount_minor"]
        self.assertIn(format_amount(d1_amount, "USD"), html_out)
        self.assertIn("One-time charge", html_out)

    def test_trial_view_validates_clean(self):
        snapshot, fulfillment, view = self._trial_view()
        self.assertEqual(validate_thank_you(view, snapshot, fulfillment), [])

    def test_trial_terms_never_invented(self):
        # Same purchase set with NO trial terms in the snapshot: no
        # trial wording may appear anywhere in the render.
        snapshot = make_snapshot(["MAIN-A", "D1"])
        view = resolve_order_view(snapshot, make_fulfillment(snapshot),
                                  expected_identity=IDENTITY)
        html_out = render_thank_you(view, BRAND)
        self.assertNotIn("trial", html_out.lower())
        self.assertNotIn("14 days", html_out)


if __name__ == "__main__":
    unittest.main()
