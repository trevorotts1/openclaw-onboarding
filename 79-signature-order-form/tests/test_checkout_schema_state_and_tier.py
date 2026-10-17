"""Second-batch S79 fixture tests: tier-change bump re-evaluation (D4 iii),
checkout schema draft (S79-01), purchase state machine (S79-07).
L1 deterministic evidence only."""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
SKILL_ROOT = HERE.parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
sys.path.insert(0, str(HERE.parent))

from bump_fixture_model import BumpConfig, BumpError, PriceChoice, change_main_tier, initial_quote, set_bump_selected  # noqa: E402
from purchase_state import PurchaseAttempt, StateError  # noqa: E402

import jsonschema  # noqa: E402

SCHEMA = json.loads((SKILL_ROOT / "references" / "checkout.schema.json").read_text())


def price(amount, currency="USD"):
    return PriceChoice(f"P-{amount}", currency, amount)


def cfg(**kw):
    base = dict(component_id="B1", enabled=True, offer_id="BUMP", price=price(2700),
                entitlement_ids=frozenset({"workbook"}),
                applicable_main_offer_ids=frozenset({"MAIN-A", "MAIN-B", "MAIN-C"}),
                native_product_id="TEST-PROD-BUMP", native_price_id="TEST-PRICE-BUMP")
    base.update(kw)
    return BumpConfig(**base)


class TierChangeTests(unittest.TestCase):
    def test_selected_bump_survives_tier_change_when_still_eligible(self):
        c = cfg()
        q = initial_quote("MAIN-A", price(9700), 1, frozenset({"base-a"}), c)
        q = set_bump_selected(q, c, True)
        q2 = change_main_tier(q, c, "MAIN-B", price(19700), frozenset({"base-b"}))
        self.assertEqual(q2.bump_state, "selected")
        self.assertEqual(q2.total_minor, 19700 + 2700)

    def test_tier_change_to_including_tier_removes_line_no_double_charge(self):
        c = cfg()
        q = initial_quote("MAIN-A", price(9700), 1, frozenset({"base-a"}), c)
        q = set_bump_selected(q, c, True)
        q2 = change_main_tier(q, c, "MAIN-C", price(29700), frozenset({"base-c", "workbook"}))
        self.assertEqual(q2.bump_state, "suppressed_included")
        self.assertEqual(q2.suppression_source, "included_in_package")
        self.assertEqual(q2.line_items, ())
        self.assertEqual(q2.total_minor, 29700)

    def test_tier_change_to_inapplicable_tier_removes_line_base_intact(self):
        c = cfg(applicable_main_offer_ids=frozenset({"MAIN-A"}))
        q = initial_quote("MAIN-A", price(9700), 1, frozenset({"base-a"}), c)
        q = set_bump_selected(q, c, True)
        q2 = change_main_tier(q, c, "MAIN-B", price(19700), frozenset({"base-b"}))
        self.assertEqual(q2.bump_state, "disabled_unavailable")
        self.assertEqual(q2.total_minor, 19700)

    def test_previously_purchased_suppression_is_distinct_source(self):
        c = cfg()
        q = initial_quote("MAIN-A", price(9700), 1, frozenset({"base-a"}), c,
                          previously_purchased_entitlement_ids=frozenset({"workbook"}))
        self.assertEqual(q.bump_state, "suppressed_included")
        self.assertEqual(q.suppression_source, "previously_purchased")

    def test_expired_price_mapping_disables_bump_base_usable(self):
        c = cfg(price_mapping_expires_at="2026-10-01T00:00:00Z")
        q = initial_quote("MAIN-A", price(9700), 1, frozenset({"base-a"}), c,
                          now="2026-10-15T00:00:00Z")
        self.assertEqual(q.bump_state, "disabled_unavailable")
        self.assertEqual(q.total_minor, 9700)
        q_ok = initial_quote("MAIN-A", price(9700), 1, frozenset({"base-a"}), c,
                             now="2026-09-01T00:00:00Z")
        self.assertEqual(q_ok.bump_state, "offered_unchecked")


def valid_request(mode="combined_single_offer"):
    req = {
        "tenant_id": "TEST-TENANT", "location_id": "TEST-LOCATION",
        "launch_id": "TEST-LAUNCH", "launch_revision": 1,
        "launch_plan_approval_ref": "TEST-APPROVAL", "approved_plan_hash": "TEST-HASH",
        "checkout_mode": mode, "main_offer_id": "MAIN-A",
        "main_price": {"price_choice_id": "MAIN-A-USD", "currency": "USD",
                       "currency_exponent": 2, "amount_minor": 9700,
                       "billing_type": "one_time", "native_product_id": None,
                       "native_price_id": None, "approval_status": "test_only"},
        "quantity": 1, "selection_ref": None, "selection_revision": None,
        "main_entitlement_ids": ["base-a"],
        "previously_purchased_entitlement_ids": [],
        "bump": {"component_id": "B1", "component_version": "0.1",
                 "enabled": True, "offer_id": "BUMP",
                 "applicable_main_offer_ids": ["MAIN-A"],
                 "entitlement_ids": ["workbook"],
                 "incompatible_entitlement_ids": [],
                 "headline": "TEST ONLY", "benefit_explanation": "TEST ONLY",
                 "price": {"price_choice_id": "BUMP-USD", "currency": "USD",
                           "currency_exponent": 2, "amount_minor": 2700,
                           "billing_type": "one_time", "native_product_id": None,
                           "native_price_id": None, "approval_status": "test_only"},
                 "default_selected": False, "quantity_policy": "fixed_1",
                 "fulfillment_rule_ref": "TEST-RULE",
                 "native_product_id": None, "native_price_id": None,
                 "price_mapping_expires_at": None},
        "brand_ref": "TEST-BRAND", "brand_revision": "1",
        "terms_ref": "TEST-TERMS", "consent_ref": "TEST-CONSENT",
        "failed_pending_requirements": {
            "failed_state_copy_ref": "TEST-FAILED-COPY",
            "pending_state_copy_ref": "TEST-PENDING-COPY",
            "retry_policy": "reconcile_native_records_first",
            "requires_customer_action_copy_ref": None},
        "native_capability_evidence_ref": "TEST-CAP",
        "successful_payment_next_route": "upsell_1",
        "fulfillment_mapping_ref": "TEST-FULFILL", "test_only": True,
    }
    if mode == "post_selection":
        req["selection_ref"] = "TEST-OPAQUE-SESSION-REF"
        req["selection_revision"] = 1
    return req


def validate_def(name, instance):
    subschema = {"$schema": SCHEMA["$schema"], "$defs": SCHEMA["$defs"],
                 "$ref": f"#/$defs/{name}"}
    jsonschema.validate(instance, subschema)


class CheckoutSchemaTests(unittest.TestCase):
    def test_combined_mode_request_valid(self):
        validate_def("checkout_request", valid_request())

    def test_post_selection_request_valid(self):
        validate_def("checkout_request", valid_request("post_selection"))

    def test_combined_mode_rejects_selection_ref(self):
        req = valid_request()
        req["selection_ref"] = "SHOULD-NOT-BE-HERE"
        with self.assertRaises(jsonschema.ValidationError):
            validate_def("checkout_request", req)

    def test_post_selection_requires_selection_ref(self):
        req = valid_request()
        req["checkout_mode"] = "post_selection"
        with self.assertRaises(jsonschema.ValidationError):
            validate_def("checkout_request", req)

    def test_prechecked_bump_rejected_by_schema(self):
        req = valid_request()
        req["bump"]["default_selected"] = True
        with self.assertRaises(jsonschema.ValidationError):
            validate_def("checkout_request", req)

    def test_float_amount_and_zero_quantity_rejected(self):
        req = valid_request()
        req["main_price"]["amount_minor"] = 97.5  # 97.0 would pass: JSON Schema treats zero-fraction numbers as integers
        with self.assertRaises(jsonschema.ValidationError):
            validate_def("checkout_request", req)
        req2 = valid_request()
        req2["quantity"] = 0
        with self.assertRaises(jsonschema.ValidationError):
            validate_def("checkout_request", req2)

    def test_result_requires_reviewer_separate_field_and_status_enum(self):
        result = {"request_input_hash": "TEST-HASH", "status": "authored",
                  "test_record_refs": [], "producer_id": "S79-AUTHOR",
                  "reviewer_id": None, "known_blockers": []}
        validate_def("checkout_result", result)
        result["status"] = "totally_done"
        with self.assertRaises(jsonschema.ValidationError):
            validate_def("checkout_result", result)


class PurchaseStateMachineTests(unittest.TestCase):
    def drive_to_submitting(self):
        a = PurchaseAttempt()
        a.apply("begin_validation")
        a.apply("submit")
        return a

    def test_happy_path_to_paid_and_paid_edge(self):
        a = self.drive_to_submitting()
        self.assertFalse(a.can_traverse_paid_edge())
        a.apply("native_paid_verified")
        self.assertEqual(a.state, "paid")
        self.assertTrue(a.can_traverse_paid_edge())

    def test_click_or_redirect_alone_cannot_pay(self):
        a = self.drive_to_submitting()
        with self.assertRaises(StateError):
            a.apply("button_clicked")
        with self.assertRaises(StateError):
            a.apply("redirect_seen")
        self.assertEqual(a.state, "submitting")
        self.assertFalse(a.can_traverse_paid_edge())

    def test_failed_and_pending_never_traverse_paid_edge(self):
        for event, expected in (("native_failed", "failed"),
                                ("native_pending", "pending_confirmation"),
                                ("native_requires_customer_action", "requires_customer_action")):
            with self.subTest(event=event):
                a = self.drive_to_submitting()
                a.apply(event)
                self.assertEqual(a.state, expected)
                self.assertFalse(a.can_traverse_paid_edge())

    def test_repeated_submit_rejected_while_processing(self):
        a = self.drive_to_submitting()
        with self.assertRaises(StateError):
            a.apply("submit")
        a.apply("native_pending")
        with self.assertRaises(StateError):
            a.apply("submit")

    def test_unknown_timeout_requires_reconciliation_before_retry(self):
        a = self.drive_to_submitting()
        a.apply("timeout_unknown_outcome")
        self.assertEqual(a.state, "pending_confirmation")
        self.assertTrue(a.reconcile_required)
        # Reconciliation finds no charge: becomes a known failure, retry opens.
        a.record_reconciliation(found_paid=False)
        self.assertEqual(a.state, "failed")
        a.apply("retry_after_reconciliation")
        self.assertEqual(a.state, "ready")

    def test_unknown_timeout_reconciled_as_paid(self):
        a = self.drive_to_submitting()
        a.apply("timeout_unknown_outcome")
        a.record_reconciliation(found_paid=True)
        self.assertEqual(a.state, "paid")

    def test_retry_from_known_failure_allowed(self):
        a = self.drive_to_submitting()
        a.apply("native_failed")
        a.apply("retry_after_reconciliation")
        self.assertEqual(a.state, "ready")

    def test_paid_is_terminal_no_rollback_transition(self):
        a = self.drive_to_submitting()
        a.apply("native_paid_verified")
        for event in ("native_failed", "cancel", "retry_after_reconciliation", "submit"):
            with self.subTest(event=event), self.assertRaises(StateError):
                a.apply(event)
        self.assertEqual(a.state, "paid")

    def test_cancel_only_before_submission_or_abandoned_action(self):
        a = PurchaseAttempt()
        a.apply("cancel")
        self.assertEqual(a.state, "cancelled")
        b = self.drive_to_submitting()
        with self.assertRaises(StateError):
            b.apply("cancel")


if __name__ == "__main__":
    unittest.main(verbosity=2)
