"""Issues 77 and 78: the selection hand-off carries one time shape and the billing terms.

77. Skill 78 keeps its session clock in epoch seconds; Skill 79 compared ISO strings lexicographically,
    which CHK-07 (bump_fixture_model.parse_aware) already calls wrong across offsets. The Selection now
    holds an aware ISO-8601 `expires_at`, `resolve_selection` compares instants, and an integer, a naive
    or a junk time is refused by name (SelectionTimeError).
78. The selection intent's billing type and schedule rows `{sequence, due, amount_minor}` used to stop at
    the adapter. The Selection carries them and `billing_summary` is what the post-selection page renders.
"""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "scripts"))

from selection_flow import (  # noqa: E402
    Selection, SelectionBillingError, SelectionTimeError, billing_summary, resolve_selection,
    selection_from_intent,
)

INTENT = {
    "schema_version": "1.0", "kind": "selection_intent_not_payment_evidence", "tenant_id": "T1",
    "location_id": "L1", "launch_id": "LA1", "revision": 3, "offer_id": "MAIN-B",
    "price_choice_id": "MAIN-B-INST", "native_product_id": "PROD-B", "native_price_id": "PRICE-B",
    "currency": "USD", "amount_minor_snapshot": 19700, "billing_type": "installment",
    "schedule": [{"sequence": 1, "due": "today", "amount_minor": 9850},
                 {"sequence": 2, "due": "in 30 days", "amount_minor": 9850}],
    "quantity": 1, "selected_at": "2026-10-15T10:00:00Z", "source_page_id": "SEL-1", "session_ref": "opaque",
}
CURRENT = dict(current_launch_revision=3, current_offer_revision=3, current_native_price_id="PRICE-B",
               current_amount_minor=19700, current_currency="USD", expected_tenant_id="T1",
               expected_location_id="L1", expected_launch_id="LA1")


def intent(**changes):
    return {**INTENT, **changes}


def decide(selection, now):
    return resolve_selection(selection, now=now, **CURRENT)


class ExpiryIsAnInstantComparison(unittest.TestCase):
    def test_an_expiry_in_another_offset_is_compared_as_an_instant(self):
        # 2026-10-16T00:00+14:00 is 2026-10-15T10:00Z: expired at 12:00Z. As strings it sorts AFTER "2026-10-15...".
        sel = selection_from_intent(INTENT, expires_at="2026-10-16T00:00:00+14:00")
        self.assertEqual(decide(sel, "2026-10-15T12:00:00Z").action, "recovery_choice")

    def test_a_later_instant_with_an_earlier_looking_string_is_not_expired(self):
        # 2026-10-15T23:00-10:00 is 2026-10-16T09:00Z: still live at 00:00Z on the 16th. As strings it looks past.
        sel = selection_from_intent(INTENT, expires_at="2026-10-15T23:00:00-10:00")
        self.assertEqual(decide(sel, "2026-10-16T00:00:00Z").action, "proceed")

    def test_now_in_another_offset_is_compared_as_an_instant(self):
        sel = selection_from_intent(INTENT, expires_at="2026-10-16T00:00:00Z")
        self.assertEqual(decide(sel, "2026-10-16T01:00:00+05:00").action, "proceed")   # 20:00Z on the 15th
        self.assertEqual(decide(sel, "2026-10-15T19:30:00-05:00").action, "recovery_choice")  # 00:30Z on the 16th

    def test_no_expiry_never_expires(self):
        self.assertEqual(decide(selection_from_intent(INTENT), "2099-01-01T00:00:00Z").action, "proceed")


class TimeShapesAreRefusedByName(unittest.TestCase):
    def test_an_integer_expiry_is_refused_by_name(self):
        for bad in (1760000000, 1760000000.5, True):
            with self.subTest(bad), self.assertRaises(SelectionTimeError):
                selection_from_intent(INTENT, expires_at=bad)

    def test_a_naive_or_junk_expiry_is_refused_by_name(self):
        for bad in ("2026-10-16T00:00:00", "tomorrow", "", "2026-13-45T00:00:00Z"):
            with self.subTest(bad), self.assertRaises(SelectionTimeError):
                selection_from_intent(INTENT, expires_at=bad)

    def test_a_selection_built_by_hand_cannot_carry_a_bad_expiry(self):
        base = dict(offer_id="M", native_price_id="P", amount_minor=1, currency="USD", quantity=1,
                    launch_revision=1, offer_revision=1)
        with self.assertRaises(SelectionTimeError):
            Selection(**base, expires_at=1760000000)
        self.assertIsNone(Selection(**base, expires_at=None).expires_at)

    def test_now_must_be_an_aware_time_too(self):
        sel = selection_from_intent(INTENT, expires_at="2026-10-16T00:00:00Z")
        for bad in (1760000000, "2026-10-15T12:00:00", "noon", None):
            with self.subTest(bad), self.assertRaises(SelectionTimeError):
                decide(sel, bad)

    def test_the_refusal_is_a_value_error_with_a_stable_code(self):
        with self.assertRaises(ValueError) as ctx:
            selection_from_intent(INTENT, expires_at=1760000000)
        self.assertEqual(ctx.exception.code, "S79-SELECTION-TIME")
        self.assertIn("CHK-07", str(ctx.exception))


class BillingTermsSurviveTheAdapter(unittest.TestCase):
    def test_the_selection_carries_billing_type_and_schedule_rows(self):
        sel = selection_from_intent(INTENT)
        self.assertEqual(sel.billing_type, "installment")
        self.assertEqual(sel.schedule, ((1, "today", 9850), (2, "in 30 days", 9850)))

    def test_a_one_time_selection_carries_an_empty_schedule(self):
        sel = selection_from_intent(intent(billing_type="one_time", schedule=[]))
        self.assertEqual((sel.billing_type, sel.schedule), ("one_time", ()))

    def test_an_intent_with_no_or_unknown_billing_type_is_refused_by_name(self):
        for bad in (None, "", "weekly", 3):
            with self.subTest(bad), self.assertRaises(SelectionBillingError):
                selection_from_intent(intent(billing_type=bad))
        no_type = dict(INTENT)
        del no_type["billing_type"]
        with self.assertRaises(SelectionBillingError):
            selection_from_intent(no_type)

    def test_schedule_rows_must_have_the_checkout_shape(self):
        bad_rows = (
            [{"due": "today", "amount_minor": 9850}],                                    # no sequence (78's old shape)
            [{"sequence": 1, "due": "today"}],                                            # no amount
            [{"sequence": 1, "due": "", "amount_minor": 1}],                              # blank due
            [{"sequence": 0, "due": "today", "amount_minor": 1}],                         # sequence below 1
            [{"sequence": 1, "due": "today", "amount_minor": -1}],                        # negative
            [{"sequence": 1, "due": "today", "amount_minor": 1.5}],                       # not minor units
            [{"sequence": 1, "due": "a", "amount_minor": 1}, {"sequence": 1, "due": "b", "amount_minor": 1}],  # repeated
            [{"sequence": 2, "due": "a", "amount_minor": 1}, {"sequence": 1, "due": "b", "amount_minor": 1}],  # unordered
            [{"sequence": 1, "due": "today", "amount_minor": 1, "note": "x"}],            # unknown key
            "monthly", {"sequence": 1})
        for rows in bad_rows:
            with self.subTest(rows), self.assertRaises(SelectionBillingError):
                selection_from_intent(intent(schedule=rows))

    def test_billing_summary_is_what_the_post_selection_page_renders(self):
        summary = billing_summary(selection_from_intent(INTENT), currency_exponent=2)
        self.assertEqual(summary["billing_type"], "installment")
        self.assertEqual(summary["rows"], [
            {"sequence": 1, "due": "today", "amount": "USD 98.50"},
            {"sequence": 2, "due": "in 30 days", "amount": "USD 98.50"}])

    def test_billing_summary_uses_the_currency_exponent(self):
        yen = selection_from_intent(intent(currency="JPY", billing_type="one_time", schedule=[]))
        self.assertEqual(billing_summary(yen, currency_exponent=0)["rows"], [])
        paid = selection_from_intent(intent(currency="JPY", schedule=[{"sequence": 1, "due": "today", "amount_minor": 9850}]))
        self.assertEqual(billing_summary(paid, currency_exponent=0)["rows"][0]["amount"], "JPY 9,850")

    def test_a_selection_with_no_billing_terms_cannot_be_summarised(self):
        bare = Selection(offer_id="M", native_price_id="P", amount_minor=1, currency="USD", quantity=1,
                         launch_revision=1, offer_revision=1, expires_at=None)
        with self.assertRaises(SelectionBillingError):
            billing_summary(bare, currency_exponent=2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
