"""RFX-015: the upsell wrapper accepts an offer approved at two prices (monthly AND yearly).

`_select_price` used to refuse any offer carrying two approved prices, so a membership approved at
8900 a month and 50000 a year could never reach Skill 80. It now names the lead price choice (the
copy's `lead_price_choice_id`, else the first price) in the disclosure block and checks that the
second choice is disclosable too; three choices, an installment or trial choice, or an unknown lead
still refuse, and a single-price offer is unchanged.

Run: python3 49-signature-funnel/scripts/test_upsell_two_prices.py
"""

import importlib.util
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("upsell_wrapper_two_prices", HERE / "upsell_wrapper.py")
uw = importlib.util.module_from_spec(spec)
sys.path.insert(0, str(HERE))
spec.loader.exec_module(uw)


def price(pid, amount, interval=None, billing="recurring", status="approved"):
    p = {"price_choice_id": pid, "currency": "USD", "amount_minor": amount, "billing_type": billing,
         "native_price_id": None, "schedule": [], "approval_status": status}
    if interval:
        p["recurring_interval"] = interval
    return p


MONTH, YEAR = price("U2-USD", 8900, "month"), price("U2-USD-YEAR", 50000, "year")


def offer(*prices):
    return {"offer_id": "U2", "slot": "upsell_2", "prices": list(prices)}


class TwoApprovedPriceChoices(unittest.TestCase):
    def test_monthly_and_yearly_disclose_the_lead_first_price_by_default(self):
        problems = []
        block = uw._disclosure_block(offer(MONTH, YEAR), {}, problems)
        self.assertEqual(problems, [])
        self.assertEqual((block["amount_minor"], block["recurring_terms"]["interval"]), (8900, "month"))
        self.assertIn("USD 89.00 per month until cancelled", block["disclosure_text"])

    def test_the_lead_field_selects_the_yearly_price(self):
        problems = []
        block = uw._disclosure_block(offer(MONTH, YEAR), {}, problems, "U2-USD-YEAR")
        self.assertEqual(problems, [])
        self.assertEqual((block["amount_minor"], block["recurring_terms"]["interval"]), (50000, "year"))
        self.assertIn("USD 500.00 per year until cancelled", block["disclosure_text"])

    def test_an_unknown_lead_refuses(self):
        problems = []
        self.assertIsNone(uw._disclosure_block(offer(MONTH, YEAR), {}, problems, "NOPE"))
        self.assertTrue(any("lead_price_choice_id" in p for p in problems), problems)

    def test_three_price_choices_refuse(self):
        problems = []
        self.assertIsNone(uw._disclosure_block(offer(MONTH, YEAR, price("U2-W", 2900, "week")), {}, problems))
        self.assertTrue(any("3 price choices" in p for p in problems), problems)

    def test_an_installment_or_trial_choice_refuses(self):
        for kind in ("installment", "trial"):
            problems = []
            bad = price("U2-PLAN", 25000, billing=kind)
            self.assertIsNone(uw._disclosure_block(offer(MONTH, bad), {}, problems), kind)
            self.assertTrue(any("never an installment or a trial" in p for p in problems), (kind, problems))

    def test_a_second_choice_with_no_disclosable_terms_refuses(self):
        problems = []
        self.assertIsNone(uw._disclosure_block(offer(MONTH, price("U2-USD-YEAR", 50000)), {}, problems))
        self.assertTrue(any("disclosure.recurring_terms" in p for p in problems), problems)


class SinglePriceUnchanged(unittest.TestCase):
    def test_one_price_is_that_price(self):
        self.assertIs(uw._select_price(offer(MONTH), []), MONTH)

    def test_one_approved_among_an_unapproved_is_the_approved_one(self):
        self.assertIs(uw._select_price(offer(dict(MONTH, approval_status="unknown"), YEAR), []), YEAR)

    def test_two_unapproved_prices_still_refuse(self):
        problems = []
        u = lambda p: dict(p, approval_status="recommended_unapproved")  # noqa: E731
        self.assertIsNone(uw._select_price(offer(u(MONTH), u(YEAR)), problems))
        self.assertTrue(any("never guesses" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
