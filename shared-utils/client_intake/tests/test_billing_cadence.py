#!/usr/bin/env python3
"""A billing answer in the client's own words ("weekly", "quarterly", "every year") is read as a recurring
price with its interval, never flattened to one payment and never dropped to "not understood".
Neutral values. Run: python3 -m pytest shared-utils/client_intake/tests/test_billing_cadence.py -q
"""
import sys
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG))
import engine as e  # noqa: E402


def doc_with(billing_value, minor=4900):
    return {"meta": {}, "answers": {
        "billing": {"value": billing_value, "status": "provided", "source": "client"},
        "price": {"value": {"amount_minor": minor, "currency": "USD"}, "status": "provided", "source": "client"}}}


class CadenceWords(unittest.TestCase):
    def test_the_banks_three_answers_keep_their_meaning(self):
        self.assertEqual(e._billing_key("All at once"), "one_time")
        self.assertEqual(e._billing_key("Monthly"), "recurring")
        self.assertEqual(e._billing_key("In parts or trial first"), "installment")

    def test_cadence_words_are_recurring_and_name_their_interval(self):
        for word, interval in (("weekly", "week"), ("Quarterly", "quarter"), ("every year", "year"),
                               ("annually", "year"), ("every three months", "quarter"), ("monthly", "month")):
            self.assertEqual(e._billing_key(word), "recurring", word)
            self.assertEqual(e._billing_cadence(word), interval, word)

    def test_a_word_nobody_carries_is_still_not_guessed(self):
        for word in ("every other month", "biweekly", "", None, 5):
            self.assertIsNone(e._billing_key(word), word)

    def test_the_billing_terms_use_the_cadence_not_a_default_month(self):
        terms = e.billing_terms(doc_with("quarterly"))
        self.assertEqual((terms["billing_type"], terms["interval"], terms["interval_count"]), ("recurring", "quarter", 1))
        self.assertEqual(e.billing_terms(doc_with("Monthly"))["interval"], "month")
        self.assertEqual(e.billing_terms(doc_with("yearly"))["interval"], "year")

    def test_a_cadence_answer_derives_the_payment_plan_flag(self):
        doc = doc_with("weekly")
        self.assertTrue(e.derive_payment_plans(doc)["value"])


if __name__ == "__main__":
    unittest.main()
