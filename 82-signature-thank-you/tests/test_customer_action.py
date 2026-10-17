"""Skill 82 tests — DOC-07: `requires_customer_action` end to end.

Branch-matrix row DOC-07 (doc 18 section 4): an item whose payment
requires customer authentication renders as "Action needed" — neither
paid nor failed — with no access until authentication completes. The
resolver maps the status and buckets it with the pending items, and
the renderer labels it "Action needed"; before this file, no shipped
test constructed such a snapshot (the string appeared only in
test_repairs.py's hand-built-view status table).

This file builds a verified snapshot carrying a
`requires_customer_action` line and proves the full path:
snapshot -> resolver view -> rendered fragment -> validators.

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

from test_thank_you import IDENTITY, make_fulfillment, make_snapshot  # noqa: E402
from thank_you_resolver import resolve_order_view  # noqa: E402
from validate_thank_you import validate_thank_you  # noqa: E402
from validate_entitlements import validate_entitlements  # noqa: E402
from render_thank_you import format_amount, render_thank_you  # noqa: E402

BRAND = {
    "brand_name": "TEST ONLY BRAND",
    "colors": {"primary": "#123456", "accent": "#057a55",
               "background": "#ffffff", "text": "#111111"},
    "support": {"label": "Contact TEST ONLY support",
                "email": "support@example.test"},
    "manage_purchase_url": "https://example.test/manage",
}


def action_snapshot():
    """MAIN-A paid; U1 stuck at requires_customer_action."""
    snapshot = make_snapshot(
        ["MAIN-A", "U1"], statuses={"U1": "requires_customer_action"})
    return snapshot, make_fulfillment(snapshot)


class RequiresCustomerActionResolverTest(unittest.TestCase):
    def test_action_item_buckets_with_pending_not_paid_not_failed(self):
        snapshot, fulfillment = action_snapshot()
        view = resolve_order_view(snapshot, fulfillment,
                                  expected_identity=IDENTITY)
        statuses = {i["offer_id"]: i["display_status"]
                    for i in view["items"]}
        self.assertEqual(statuses["U1"], "requires_customer_action")
        self.assertEqual(statuses["MAIN-A"], "paid")
        # Bucketed as unresolved money: in pending_items and the
        # pending total, in neither the paid total nor failed_items.
        self.assertEqual(view["pending_items"], ["U1"])
        self.assertEqual(view["failed_items"], [])
        self.assertEqual(view["totals"]["paid_total_minor"], 9700)
        self.assertEqual(view["totals"]["pending_total_minor"], 6700)
        # Never "all set" while an item needs customer action.
        self.assertFalse(view["confirmation"]["all_set"])
        self.assertEqual(view["confirmation"]["status"], "partially_pending")
        self.assertNotIn("all set",
                         view["confirmation"]["headline"].lower())

    def test_action_item_gets_no_access_base_access_preserved(self):
        snapshot, fulfillment = action_snapshot()
        view = resolve_order_view(snapshot, fulfillment,
                                  expected_identity=IDENTITY)
        access = {b["entitlement_id"] for b in view["access_blocks"]}
        self.assertIn("base-a", access)
        self.assertNotIn("extra-full", access)
        # No CTA points at the action-needed item's entitlement either.
        self.assertFalse(any(
            c.get("entitlement_id") == "extra-full" for c in view["ctas"]))

    def test_action_needed_main_only_confirms_nothing(self):
        # The whole order is waiting on the customer: no paid total,
        # no access blocks, no confirmation claim.
        snapshot = make_snapshot(
            ["MAIN-A"], statuses={"MAIN-A": "requires_customer_action"})
        fulfillment = make_fulfillment(snapshot)
        view = resolve_order_view(snapshot, fulfillment,
                                  expected_identity=IDENTITY)
        self.assertEqual(view["items"][0]["display_status"],
                         "requires_customer_action")
        self.assertEqual(view["pending_items"], ["MAIN-A"])
        self.assertEqual(view["totals"]["paid_total_minor"], 0)
        self.assertEqual(view["totals"]["pending_total_minor"], 9700)
        self.assertEqual(view["access_blocks"], [])
        self.assertFalse(view["confirmation"]["all_set"])


class RequiresCustomerActionRenderTest(unittest.TestCase):
    def test_renders_action_needed_label_and_keeps_base_access(self):
        snapshot, fulfillment = action_snapshot()
        view = resolve_order_view(snapshot, fulfillment,
                                  expected_identity=IDENTITY)
        html_out = render_thank_you(view, BRAND)
        # The DOC-07 label, with its own status pill class.
        self.assertIn("Action needed", html_out)
        self.assertIn("ty82-status--requires_customer_action", html_out)
        # Honest page-level state: partly pending, never "all set".
        self.assertIn("Partly pending", html_out)
        self.assertNotIn("You are all set", html_out)
        # The action-needed item is named, its money sits in the
        # pending row, and base access renders while its does not.
        self.assertIn("TEST ONLY U1", html_out)
        self.assertIn("Pending (not yet confirmed)", html_out)
        self.assertIn(format_amount(6700, "USD"), html_out)
        self.assertIn("https://example.test/access/base-a", html_out)
        self.assertNotIn("https://example.test/access/extra-full",
                         html_out)
        # What-happens-next names it as still being confirmed.
        self.assertIn("TEST ONLY U1 is still being confirmed", html_out)


class RequiresCustomerActionValidatorTest(unittest.TestCase):
    def test_honest_action_view_validates_clean(self):
        snapshot, fulfillment = action_snapshot()
        view = resolve_order_view(snapshot, fulfillment,
                                  expected_identity=IDENTITY)
        self.assertEqual(validate_thank_you(view, snapshot, fulfillment), [])
        self.assertEqual(validate_entitlements(view, snapshot, fulfillment),
                         [])

    def test_action_view_relabelled_all_set_rejected(self):
        # The validator's unresolved set names requires_customer_action
        # explicitly: relabeling such a view "all set" fails closed.
        snapshot, fulfillment = action_snapshot()
        view = resolve_order_view(snapshot, fulfillment,
                                  expected_identity=IDENTITY)
        tampered = copy.deepcopy(view)
        tampered["confirmation"] = {
            "status": "confirmed", "all_set": True,
            "headline": "You are all set. Your purchase is confirmed.",
        }
        errors = validate_thank_you(tampered, snapshot, fulfillment)
        self.assertTrue(any("false_confirmation" in e for e in errors),
                        errors)

    def test_action_view_is_schema_valid(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not available")
        import json
        schema = json.loads(
            (SKILL_DIR / "schemas" / "order-view.schema.json").read_text())
        snapshot, fulfillment = action_snapshot()
        view = resolve_order_view(snapshot, fulfillment,
                                  expected_identity=IDENTITY)
        jsonschema.validate(view, schema)


if __name__ == "__main__":
    unittest.main()
