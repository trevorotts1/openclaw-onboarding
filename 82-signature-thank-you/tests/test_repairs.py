"""Regression tests for the S82-01..03 independent-review repairs.

Each test reproduces the reviewer's failing probe for one defect
(review-s82-01-03.md, probes P3b / P6 / P8 / P10 / P11 / P14):

- D-01: CTA entitlement targets must be paid purchased entitlements.
- D-02: U2 without a paid U1 or D1 in the same journey is rejected by
  the resolver AND by both validators.
- D-03: view order_ref / order_number / journey_id must match the
  snapshot's verified order identity.
- D-04: refunded / partially refunded items are unresolved for
  confirmation: never "all set", honestly labeled, access withheld.
- D-05: the resolver fails closed on an S44 next_action outside the
  approved classification enum.

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

from test_thank_you import IDENTITY, OFFERS, make_fulfillment, make_snapshot  # noqa: E402
from thank_you_resolver import ResolverError, resolve_order_view  # noqa: E402
from validate_thank_you import validate_thank_you  # noqa: E402
from validate_entitlements import validate_entitlements  # noqa: E402

DISPLAY_STATUS = {
    "succeeded": "paid",
    "pending": "pending",
    "failed": "failed",
    "requires_customer_action": "requires_customer_action",
    "refunded": "refunded",
    "partially_refunded": "partially_refunded",
    "unknown": "unknown",
}


def build_view_by_hand(snapshot, fulfillment):
    """Mirror of the resolver's view shape, for snapshots the resolver
    (correctly) refuses — used to prove the validators also fail closed."""
    items, access_blocks, ctas = [], [], []
    paid_total = 0
    for line in snapshot["line_items"]:
        status = DISPLAY_STATUS[line["payment_status"]]
        items.append({
            "offer_id": line["offer_id"],
            "slot": line["slot"],
            "display_name": line["display_name"],
            "amount_minor": line["amount_minor"],
            "currency": line["currency"],
            "display_status": status,
            "entitlement_ids": list(line["entitlement_ids"]),
            "native_line_ref": line["native_line_ref"],
            "event_id": line["event_id"],
            "billing": copy.deepcopy(line["billing"]),
        })
        if status != "paid":
            continue
        paid_total += line["amount_minor"]
        for ent in line["entitlement_ids"]:
            entry = (fulfillment or {}).get(ent) or {}
            if entry.get("state") != "granted":
                continue
            action = entry.get("next_action") or "access"
            access_blocks.append({
                "entitlement_id": ent,
                "offer_id": line["offer_id"],
                "slot": line["slot"],
                "next_action": action,
                "delivery_url": entry.get("delivery_url"),
                "fulfillment_state": "granted",
            })
            ctas.append({
                "classification": action,
                "label": f"Access: {line['display_name']}",
                "offer_id": line["offer_id"],
                "entitlement_id": ent,
                "initiates_new_charge": False,
            })
    ctas.append({"classification": "support", "label": "Contact support",
                 "offer_id": None, "entitlement_id": None,
                 "initiates_new_charge": False})
    ctas.append({"classification": "manage_purchase",
                 "label": "Manage your purchase", "offer_id": None,
                 "entitlement_id": None, "initiates_new_charge": False})
    return {
        "schema_version": "1.0",
        "tenant_id": snapshot["tenant_id"],
        "location_id": snapshot["location_id"],
        "launch_id": snapshot["launch_id"],
        "revision": snapshot["revision"],
        "order_ref": snapshot["native_order_ref"],
        "order_number": snapshot["native_order_ref"],
        "journey_id": snapshot["journey_id"],
        "confirmation": {
            "status": "confirmed",
            "all_set": True,
            "headline": "You are all set. Your purchase is confirmed.",
        },
        "items": items,
        "totals": {
            "currency": snapshot["line_items"][0]["currency"],
            "paid_total_minor": paid_total,
            "pending_total_minor": 0,
        },
        "access_blocks": access_blocks,
        "ctas": ctas,
        "pending_items": [],
        "failed_items": [],
        "recommendations": [],
        "provenance": {
            "source": "verified_normalized_purchase_snapshot",
            "built_from_verified_snapshot": True,
            "event_ids": list(snapshot.get("event_ids") or []),
        },
        "test_only": True,
    }


class RepairD01CtaEntitlementTargetTest(unittest.TestCase):
    def test_repair_d01_cta_entitlement_unpurchased_rejected(self):
        # Reviewer probe P3b: access CTA, offer_id null, entitlement of
        # an UNPURCHASED offer — passed both validators before the repair.
        snapshot = make_snapshot(["MAIN-A"])
        fulfillment = make_fulfillment(snapshot)
        view = resolve_order_view(snapshot, fulfillment,
                                  expected_identity=IDENTITY)
        tampered = copy.deepcopy(view)
        tampered["ctas"].append({
            "classification": "access",
            "label": "Open your implementation workspace",
            "offer_id": None,
            "entitlement_id": "implementation",  # U2's entitlement, not bought
            "initiates_new_charge": False,
        })
        ty_errors = validate_thank_you(tampered, snapshot, fulfillment)
        ent_errors = validate_entitlements(tampered, snapshot, fulfillment)
        self.assertTrue(
            any("unpurchased_cta_target" in e for e in ty_errors), ty_errors)
        self.assertTrue(
            any("unpurchased_cta_target" in e for e in ent_errors), ent_errors)

    def test_repair_d01_cta_entitlement_wrong_offer_rejected(self):
        # Entitlement is paid, but the CTA pairs it with a different offer.
        snapshot = make_snapshot(["MAIN-A", "U1"])
        fulfillment = make_fulfillment(snapshot)
        view = resolve_order_view(snapshot, fulfillment,
                                  expected_identity=IDENTITY)
        tampered = copy.deepcopy(view)
        tampered["ctas"].append({
            "classification": "download",
            "label": "Download: TEST ONLY MAIN-A",
            "offer_id": "U1",
            "entitlement_id": "base-a",  # belongs to MAIN-A, not U1
            "initiates_new_charge": False,
        })
        errors = validate_thank_you(tampered, snapshot, fulfillment)
        self.assertTrue(
            any("cta_target_mismatch" in e for e in errors), errors)

    def test_repair_d01_cta_entitlement_paid_passes(self):
        snapshot = make_snapshot(["MAIN-A", "U1"])
        fulfillment = make_fulfillment(snapshot)
        view = resolve_order_view(snapshot, fulfillment,
                                  expected_identity=IDENTITY)
        view["ctas"].append({
            "classification": "download",
            "label": "Download: TEST ONLY MAIN-A",
            "offer_id": "MAIN-A",
            "entitlement_id": "base-a",
            "initiates_new_charge": False,
        })
        self.assertEqual(validate_thank_you(view, snapshot, fulfillment), [])
        self.assertEqual(validate_entitlements(view, snapshot, fulfillment), [])

    def test_repair_d01_pending_entitlement_cta_rejected(self):
        # A pending item's entitlement is purchased but NOT paid: an
        # access CTA to it is still an unpurchased (unpaid) target.
        snapshot = make_snapshot(["MAIN-A", "U1"], statuses={"U1": "pending"})
        fulfillment = make_fulfillment(snapshot)
        view = resolve_order_view(snapshot, fulfillment,
                                  expected_identity=IDENTITY)
        tampered = copy.deepcopy(view)
        tampered["ctas"].append({
            "classification": "access",
            "label": "Open TEST ONLY U1 now",
            "offer_id": "U1",
            "entitlement_id": "extra-full",
            "initiates_new_charge": False,
        })
        errors = validate_thank_you(tampered, snapshot, fulfillment)
        self.assertTrue(
            any("unpurchased_cta_target" in e for e in errors), errors)


class RepairD02U2QualificationTest(unittest.TestCase):
    def test_repair_d02_resolver_rejects_u2_without_qualification(self):
        # Reviewer probe P6: MAIN+U2, no U1 and no D1 at all.
        snapshot = make_snapshot(["MAIN-A", "U2"])
        fulfillment = make_fulfillment(snapshot)
        with self.assertRaises(ResolverError) as ctx:
            resolve_order_view(snapshot, fulfillment,
                              expected_identity=IDENTITY)
        self.assertIn("u2_without_qualification", str(ctx.exception))

    def test_repair_d02_resolver_rejects_u2_with_pending_qualifier(self):
        # U1 was attempted but never paid; that does not qualify U2.
        snapshot = make_snapshot(["MAIN-A", "U1", "U2"],
                                 statuses={"U1": "pending"})
        with self.assertRaises(ResolverError) as ctx:
            resolve_order_view(snapshot, make_fulfillment(snapshot),
                              expected_identity=IDENTITY)
        self.assertIn("u2_without_qualification", str(ctx.exception))

    def test_repair_d02_validator_rejects_u2_without_qualification(self):
        snapshot = make_snapshot(["MAIN-A", "U2"])
        fulfillment = make_fulfillment(snapshot)
        view = build_view_by_hand(snapshot, fulfillment)
        # Sanity: the hand-built view really does carry U2 access.
        self.assertIn("implementation",
                      {b["entitlement_id"] for b in view["access_blocks"]})
        ty_errors = validate_thank_you(view, snapshot, fulfillment)
        ent_errors = validate_entitlements(view, snapshot, fulfillment)
        self.assertTrue(
            any("u2_without_qualification" in e for e in ty_errors), ty_errors)
        self.assertTrue(
            any("u2_without_qualification" in e for e in ent_errors),
            ent_errors)

    def test_repair_d02_u2_with_paid_qualifier_still_passes(self):
        for offers in (["MAIN-A", "U1", "U2"], ["MAIN-A", "D1", "U2"]):
            with self.subTest(offers=offers):
                snapshot = make_snapshot(offers)
                fulfillment = make_fulfillment(snapshot)
                view = resolve_order_view(snapshot, fulfillment,
                                          expected_identity=IDENTITY)
                self.assertIn(
                    "implementation",
                    {b["entitlement_id"] for b in view["access_blocks"]})
                self.assertEqual(
                    validate_thank_you(view, snapshot, fulfillment), [])
                self.assertEqual(
                    validate_entitlements(view, snapshot, fulfillment), [])


class RepairD03OrderIdentityTest(unittest.TestCase):
    def _honest(self):
        snapshot = make_snapshot(["MAIN-A", "BUMP"])
        fulfillment = make_fulfillment(snapshot)
        view = resolve_order_view(snapshot, fulfillment,
                                  expected_identity=IDENTITY)
        self.assertEqual(validate_thank_you(view, snapshot, fulfillment), [])
        return snapshot, fulfillment, view

    def test_repair_d03_order_ref_mismatch_rejected(self):
        # Reviewer probe P8: another buyer's order identity in the view.
        snapshot, fulfillment, view = self._honest()
        tampered = copy.deepcopy(view)
        tampered["order_ref"] = "TEST-ORDER-SOMEONE-ELSE"
        errors = validate_thank_you(tampered, snapshot, fulfillment)
        self.assertTrue(
            any("order_ref_mismatch" in e for e in errors), errors)

    def test_repair_d03_order_number_mismatch_rejected(self):
        snapshot, fulfillment, view = self._honest()
        tampered = copy.deepcopy(view)
        tampered["order_number"] = "TEST-ORDER-SOMEONE-ELSE"
        errors = validate_thank_you(tampered, snapshot, fulfillment)
        self.assertTrue(
            any("order_number_mismatch" in e for e in errors), errors)

    def test_repair_d03_journey_mismatch_rejected(self):
        snapshot, fulfillment, view = self._honest()
        tampered = copy.deepcopy(view)
        tampered["journey_id"] = "TEST-JOURNEY-SOMEONE-ELSE"
        errors = validate_thank_you(tampered, snapshot, fulfillment)
        self.assertTrue(
            any("journey_mismatch" in e for e in errors), errors)


class RepairD04RefundHonestyTest(unittest.TestCase):
    def test_repair_d04_fully_refunded_main_not_all_set(self):
        # Reviewer probe P14: the sole purchase was fully refunded.
        snapshot = make_snapshot(["MAIN-A"], statuses={"MAIN-A": "refunded"})
        fulfillment = make_fulfillment(snapshot)
        view = resolve_order_view(snapshot, fulfillment,
                                  expected_identity=IDENTITY)
        self.assertFalse(view["confirmation"]["all_set"])
        self.assertEqual(view["confirmation"]["status"], "refund_applied")
        self.assertNotIn("all set",
                         view["confirmation"]["headline"].lower())
        # Historical receipt row stays, honestly labeled; no access.
        self.assertEqual(view["items"][0]["display_status"], "refunded")
        self.assertEqual(view["access_blocks"], [])
        self.assertEqual(view["totals"]["paid_total_minor"], 0)
        # The honest refund view itself validates clean.
        self.assertEqual(validate_thank_you(view, snapshot, fulfillment), [])
        self.assertEqual(validate_entitlements(view, snapshot, fulfillment),
                         [])

    def test_repair_d04_tampered_refund_confirmation_rejected(self):
        snapshot = make_snapshot(["MAIN-A"], statuses={"MAIN-A": "refunded"})
        fulfillment = make_fulfillment(snapshot)
        view = resolve_order_view(snapshot, fulfillment,
                                  expected_identity=IDENTITY)
        tampered = copy.deepcopy(view)
        tampered["confirmation"] = {
            "status": "confirmed",
            "all_set": True,
            "headline": "You are all set. Your purchase is confirmed.",
        }
        errors = validate_thank_you(tampered, snapshot, fulfillment)
        self.assertTrue(
            any("false_confirmation" in e for e in errors), errors)

    def test_repair_d04_partially_refunded_extra_not_all_set(self):
        # Reviewer probe P11: U1 partially refunded; base stays intact.
        snapshot = make_snapshot(["MAIN-A", "U1"],
                                 statuses={"U1": "partially_refunded"})
        fulfillment = make_fulfillment(snapshot)
        view = resolve_order_view(snapshot, fulfillment,
                                  expected_identity=IDENTITY)
        self.assertFalse(view["confirmation"]["all_set"])
        self.assertEqual(view["confirmation"]["status"],
                         "partially_refunded")
        self.assertNotIn("all set",
                         view["confirmation"]["headline"].lower())
        statuses = {i["offer_id"]: i["display_status"]
                    for i in view["items"]}
        self.assertEqual(statuses["U1"], "partially_refunded")
        self.assertEqual(statuses["MAIN-A"], "paid")
        # Base access preserved; refunded item gets none; paid total is
        # the still-in-effect main only.
        access = {b["entitlement_id"] for b in view["access_blocks"]}
        self.assertIn("base-a", access)
        self.assertNotIn("extra-full", access)
        self.assertEqual(view["totals"]["paid_total_minor"], 9700)
        self.assertEqual(validate_thank_you(view, snapshot, fulfillment), [])

    def test_repair_d04_refunded_extra_keeps_paid_main_confirmation_honest(self):
        # Fully refunded extra next to a paid main: refund status wins
        # over plain "confirmed", main access is untouched.
        snapshot = make_snapshot(["MAIN-A", "U1"],
                                 statuses={"U1": "refunded"})
        fulfillment = make_fulfillment(snapshot)
        view = resolve_order_view(snapshot, fulfillment,
                                  expected_identity=IDENTITY)
        self.assertFalse(view["confirmation"]["all_set"])
        self.assertEqual(view["confirmation"]["status"], "refund_applied")
        self.assertIn("base-a",
                      {b["entitlement_id"] for b in view["access_blocks"]})
        self.assertEqual(validate_thank_you(view, snapshot, fulfillment), [])

    def test_repair_d04_refund_view_is_schema_valid(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not available")
        import json
        schema = json.loads(
            (SKILL_DIR / "schemas" / "order-view.schema.json").read_text())
        jsonschema.Draft202012Validator.check_schema(schema)
        snapshot = make_snapshot(["MAIN-A"], statuses={"MAIN-A": "refunded"})
        view = resolve_order_view(snapshot, make_fulfillment(snapshot),
                                  expected_identity=IDENTITY)
        jsonschema.validate(view, schema)


class RepairD05NextActionFailClosedTest(unittest.TestCase):
    def test_repair_d05_resolver_rejects_unknown_next_action(self):
        # Reviewer probe P10: S44 map says next_action "buy_more".
        snapshot = make_snapshot(["MAIN-A"])
        fulfillment = {
            "base-a": {
                "state": "granted",
                "delivery_url": "https://example.test/access/base-a",
                "next_action": "buy_more",
            },
        }
        with self.assertRaises(ResolverError) as ctx:
            resolve_order_view(snapshot, fulfillment,
                              expected_identity=IDENTITY)
        self.assertIn("invalid_next_action", str(ctx.exception))

    def test_repair_d05_all_approved_actions_accepted(self):
        for action in ("access", "download", "manage_purchase", "support",
                       "schedule_included_service",
                       "noncommercial_next_step"):
            with self.subTest(action=action):
                snapshot = make_snapshot(["MAIN-A"])
                fulfillment = {
                    "base-a": {
                        "state": "granted",
                        "delivery_url": "https://example.test/access/base-a",
                        "next_action": action,
                    },
                }
                view = resolve_order_view(snapshot, fulfillment,
                                          expected_identity=IDENTITY)
                self.assertEqual(view["access_blocks"][0]["next_action"],
                                 action)
                self.assertTrue(
                    any(c["classification"] == action
                        and c["entitlement_id"] == "base-a"
                        for c in view["ctas"]))
                self.assertEqual(
                    validate_thank_you(view, snapshot, fulfillment), [])


if __name__ == "__main__":
    unittest.main()
