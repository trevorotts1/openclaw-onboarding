"""Batch #4 review fixes: N1, N2, N3, N4. L1 only."""
import dataclasses
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
SKILL_ROOT = HERE.parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))
sys.path.insert(0, str(HERE.parent))

from quote_display import DisplayError, DisplayPrice  # noqa: E402
from purchase_event import EntitlementGrantor, HandoffError, build_purchase_event  # noqa: E402
from purchase_state import PurchaseAttempt  # noqa: E402
from selection_flow import Selection, resolve_selection  # noqa: E402


def paid_attempt():
    a = PurchaseAttempt()
    a.apply("begin_validation")
    a.apply("submit")
    a.apply("native_paid_verified")
    return a


LINE = {"native_line_ref": "L1", "offer_id": "MAIN-A", "slot": "main", "currency": "USD",
        "amount_minor": 9700, "entitlement_ids": ["base-a"]}


class Batch4FixTests(unittest.TestCase):
    def test_n2_refund_shaped_event_grants_nothing(self):
        event = build_purchase_event(
            attempt=paid_attempt(), tenant_id="T1", location_id="LOC", launch_id="LA",
            native_order_ref="O1", native_transaction_ref="TX",
            occurred_at="2026-10-15T16:00:00Z", received_at="2026-10-15T16:00:05Z",
            evidence_ref="EV", line_items=[LINE])
        refund_shaped = {**event, "event_type": "refund_observed"}
        with self.assertRaises(HandoffError):
            EntitlementGrantor().apply(refund_shaped)
        updated = {**event, "event_type": "payment_updated"}
        with self.assertRaises(HandoffError):
            EntitlementGrantor().apply(updated)
        self.assertEqual(EntitlementGrantor().apply(event), ["base-a"])

    def test_n1_negative_schedule_entry_rejected(self):
        with self.assertRaises(DisplayError):
            DisplayPrice("MAIN-A", "USD", 2, 9700, amount_due_now_minor=10700,
                         schedule=((1, "later", -1000),), source_verified=True)

    def test_n3_expected_identity_is_required(self):
        sel = Selection(offer_id="MAIN-B", native_price_id="P", amount_minor=100,
                        currency="USD", quantity=1, launch_revision=1, offer_revision=1,
                        expires_at=None, tenant_id="T1", location_id="L1", launch_id="LA1")
        with self.assertRaises(TypeError):
            resolve_selection(sel, current_launch_revision=1, current_offer_revision=1,
                              current_native_price_id="P", current_amount_minor=100,
                              current_currency="USD", now="2026-10-15T00:00:00Z")

    def test_r1_explicit_none_identity_refused(self):
        sel = Selection(offer_id="MAIN-B", native_price_id="P", amount_minor=100,
                        currency="USD", quantity=1, launch_revision=1, offer_revision=1,
                        expires_at=None, tenant_id="T1", location_id="L1", launch_id="LA1")
        with self.assertRaises(ValueError):
            resolve_selection(sel, current_launch_revision=1, current_offer_revision=1,
                              current_native_price_id="P", current_amount_minor=100,
                              current_currency="USD", now="2026-10-15T00:00:00Z",
                              expected_tenant_id=None, expected_location_id="L1",
                              expected_launch_id="LA1")

    def test_n4_state_not_mutable_after_construction(self):
        a = PurchaseAttempt()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            a.state = "paid"
        self.assertFalse(a.can_traverse_paid_edge())
        a.apply("begin_validation")
        a.apply("submit")
        a.apply("native_paid_verified")
        self.assertTrue(a.can_traverse_paid_edge())


if __name__ == "__main__":
    unittest.main(verbosity=2)
