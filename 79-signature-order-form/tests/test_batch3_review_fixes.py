"""Batch #3 review fixes: A1, A2, B1-B4, C1, C2, D-1/D-2/D-3, paid-state
construction residual. L1 only."""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
SKILL_ROOT = HERE.parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
sys.path.insert(0, str(HERE.parent))

from quote_display import DisplayError, DisplayPrice, audit_display, build_billing_display  # noqa: E402
from purchase_event import EntitlementGrantor, HandoffError, build_purchase_event  # noqa: E402
from purchase_state import PurchaseAttempt, StateError  # noqa: E402
from selection_flow import Selection, resolve_selection  # noqa: E402
from validate_checkout import CheckoutValidationError, validate_request, validate_result  # noqa: E402
from test_checkout_schema_state_and_tier import valid_request  # noqa: E402


def paid_attempt():
    a = PurchaseAttempt()
    a.apply("begin_validation")
    a.apply("submit")
    a.apply("native_paid_verified")
    return a


LINE = {"native_line_ref": "L1", "offer_id": "MAIN-A", "slot": "main", "currency": "USD",
        "amount_minor": 9700, "entitlement_ids": ["base-a"]}


def event_for(tenant):
    return build_purchase_event(
        attempt=paid_attempt(), tenant_id=tenant, location_id="LOC", launch_id="LAUNCH",
        native_order_ref="ORDER-1", native_transaction_ref="TXN-1",
        occurred_at="2026-10-15T16:00:00Z", received_at="2026-10-15T16:00:05Z",
        evidence_ref="EV", line_items=[LINE])


class Batch3FixTests(unittest.TestCase):
    def test_b1_mixed_exponent_bump_rejected(self):
        main = DisplayPrice("MAIN-A", "USD", 2, 9700, source_verified=True)
        bump = DisplayPrice("BUMP", "USD", 3, 2700, source_verified=True)
        with self.assertRaises(DisplayError):
            build_billing_display(main, bump, True)

    def test_b2_recurring_schedule_sum_checked_and_bump_future_shown(self):
        with self.assertRaises(DisplayError):
            DisplayPrice("MAIN-R", "USD", 2, 2900, billing_type="recurring",
                         recurring_interval="month", amount_due_now_minor=2900,
                         schedule=((1, "later", 99999),), source_verified=True)
        main = DisplayPrice("MAIN-A", "USD", 2, 9700, source_verified=True)
        bump = DisplayPrice("BUMP", "USD", 2, 2700, billing_type="recurring",
                            recurring_interval="month", amount_due_now_minor=900,
                            schedule=((1, "later", 900), (2, "later", 900)),
                            source_verified=True)
        d = build_billing_display(main, bump, True)
        self.assertEqual(len(d.future_formatted), 2)

    def test_b3_negative_amount_rejected(self):
        with self.assertRaises(DisplayError):
            DisplayPrice("MAIN-A", "USD", 2, -500, source_verified=True)

    def test_b4_audit_compares_currency(self):
        main = DisplayPrice("MAIN-A", "USD", 2, 9700, source_verified=True)
        good = build_billing_display(main, None, False)
        wrong_currency = type(good)(lines=good.lines, due_now_formatted=good.due_now_formatted,
                                    future_formatted=good.future_formatted,
                                    disclosures=good.disclosures, currency="EUR")
        self.assertTrue(audit_display(wrong_currency, main, None, False))

    def test_c1_dedupe_is_tenant_scoped(self):
        grantor = EntitlementGrantor()
        self.assertEqual(grantor.apply(event_for("TENANT-A")), ["base-a"])
        self.assertEqual(grantor.apply(event_for("TENANT-B")), ["base-a"])
        self.assertEqual(grantor.apply(event_for("TENANT-A")), [])

    def test_c2_forged_bare_dict_grants_nothing(self):
        forged = {"payment_status": "succeeded",
                  "line_items": [{"entitlement_ids": ["premium"]}]}
        with self.assertRaises(HandoffError):
            EntitlementGrantor().apply(forged)

    def test_a1_null_copy_hash_and_empty_artifacts_rejected(self):
        base = {"request_input_hash": "H", "status": "locally_verified",
                "test_record_refs": [], "producer_id": "A", "reviewer_id": "R",
                "known_blockers": [], "copy_hash": None, "artifact_hashes": ["X"]}
        with self.assertRaises(CheckoutValidationError):
            validate_result(base)
        base["copy_hash"] = "C"
        base["artifact_hashes"] = []
        with self.assertRaises(CheckoutValidationError):
            validate_result(base)

    def test_a2_expiry_checked_in_all_schema_locations(self):
        req = valid_request()
        req["main_price"]["price_mapping_expires_at"] = "2020-01-01T00:00:00Z"
        with self.assertRaises(CheckoutValidationError):
            validate_request(req, now="2026-10-15T00:00:00Z")
        req2 = valid_request()
        req2["bump"]["price"]["price_mapping_expires_at"] = "2020-01-01T00:00:00Z"
        with self.assertRaises(CheckoutValidationError):
            validate_request(req2, now="2026-10-15T00:00:00Z")

    def test_paid_state_not_directly_constructible(self):
        with self.assertRaises(StateError):
            PurchaseAttempt(state="paid")

    def _sel(self, **kw):
        base = dict(offer_id="MAIN-B", native_price_id="P-B", amount_minor=19700,
                    currency="USD", quantity=1, launch_revision=3, offer_revision=2,
                    expires_at="2026-10-16T00:00:00Z", tenant_id="T1", location_id="L1",
                    launch_id="LA1")
        base.update(kw)
        return Selection(**base)

    _CUR = dict(current_launch_revision=3, current_offer_revision=2,
                current_native_price_id="P-B", current_amount_minor=19700,
                current_currency="USD", now="2026-10-15T12:00:00Z",
                expected_tenant_id="T1", expected_location_id="L1", expected_launch_id="LA1")

    def test_d1_quantity_zero_is_recovery_even_when_price_changed(self):
        d = resolve_selection(self._sel(quantity=0),
                              **{**self._CUR, "current_amount_minor": 21700})
        self.assertEqual(d.action, "recovery_choice")

    def test_d2_cross_tenant_selection_is_recovery(self):
        d = resolve_selection(self._sel(tenant_id="OTHER"), **self._CUR)
        self.assertEqual(d.action, "recovery_choice")

    def test_d3_change_package_reachable(self):
        d = resolve_selection(self._sel(), visitor_action="change_package", **self._CUR)
        self.assertEqual(d.action, "change_package")


if __name__ == "__main__":
    unittest.main(verbosity=2)
