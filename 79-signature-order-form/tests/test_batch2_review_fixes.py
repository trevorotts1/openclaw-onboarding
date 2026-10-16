"""Batch #2 review fixes: schema C1-C5 (via schema + validate_checkout.py)
and state-machine D-new1/D-new2. L1 only."""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
SKILL_ROOT = HERE.parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
sys.path.insert(0, str(HERE.parent))

from purchase_state import PurchaseAttempt, StateError  # noqa: E402
from validate_checkout import CheckoutValidationError, validate_request, validate_result  # noqa: E402
from test_checkout_schema_state_and_tier import valid_request  # noqa: E402


class SchemaCompletenessTests(unittest.TestCase):
    def test_schedule_and_policy_fields_accepted_on_price_choice(self):
        req = valid_request()
        req["main_price"].update({
            "schedule": [{"sequence": 1, "due": "now", "amount_minor": 9700}],
            "amount_due_now_minor": 9700,
            "tax_policy_ref": "TEST-TAX", "shipping_policy_ref": None,
            "discount_policy_ref": None})
        validate_request(req)

    def test_request_without_failed_pending_requirements_rejected(self):
        req = valid_request()
        del req["failed_pending_requirements"]
        with self.assertRaises(CheckoutValidationError):
            validate_request(req)

    def test_verified_result_with_self_review_rejected(self):
        result = {"request_input_hash": "H", "status": "locally_verified",
                  "test_record_refs": [], "producer_id": "SAME-PERSON",
                  "reviewer_id": "SAME-PERSON", "known_blockers": [],
                  "copy_hash": "C", "artifact_hashes": []}
        with self.assertRaises(CheckoutValidationError):
            validate_result(result)

    def test_verified_result_with_distinct_reviewer_accepted(self):
        result = {"request_input_hash": "H", "status": "locally_verified",
                  "test_record_refs": [], "producer_id": "AUTHOR-1",
                  "reviewer_id": "REVIEWER-2", "known_blockers": [],
                  "copy_hash": "C", "artifact_hashes": ["A1"]}
        validate_result(result)

    def test_verified_result_without_reviewer_rejected(self):
        result = {"request_input_hash": "H", "status": "locally_verified",
                  "test_record_refs": [], "producer_id": "AUTHOR-1",
                  "reviewer_id": None, "known_blockers": [], "copy_hash": "C"}
        with self.assertRaises(CheckoutValidationError):
            validate_result(result)

    def test_production_request_requires_native_ids(self):
        req = valid_request()
        req["test_only"] = False
        with self.assertRaises(CheckoutValidationError):
            validate_request(req)
        req["main_price"]["native_product_id"] = "PROD-1"
        req["main_price"]["native_price_id"] = "PRICE-1"
        req["bump"]["native_product_id"] = "PROD-B"
        req["bump"]["native_price_id"] = "PRICE-B"
        validate_request(req)


class StateMachineReviewFixTests(unittest.TestCase):
    def drive_to_submitting(self):
        a = PurchaseAttempt()
        a.apply("begin_validation")
        a.apply("submit")
        return a

    def test_bogus_state_construction_rejected(self):
        for bogus in ("bogus", "not_a_state", "PAID", ""):
            with self.subTest(state=bogus), self.assertRaises(StateError):
                PurchaseAttempt(state=bogus)

    def test_direct_native_failure_while_pending_clears_reconcile_flag(self):
        a = self.drive_to_submitting()
        a.apply("timeout_unknown_outcome")
        self.assertTrue(a.reconcile_required)
        a.apply("native_failed")  # direct native resolution, other order
        self.assertFalse(a.reconcile_required)
        a.apply("retry_after_reconciliation")
        self.assertEqual(a.state, "ready")

    def test_record_reconciliation_from_failed_does_not_mutate_then_raise(self):
        a = self.drive_to_submitting()
        a.apply("timeout_unknown_outcome")
        a.record_reconciliation(found_paid=False)
        self.assertEqual(a.state, "failed")
        flags_before = (a.reconcile_required, a.reconciled)
        with self.assertRaises(StateError):
            a.record_reconciliation(found_paid=True)
        self.assertEqual((a.reconcile_required, a.reconciled), flags_before)


if __name__ == "__main__":
    unittest.main(verbosity=2)
