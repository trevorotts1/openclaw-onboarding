"""L14/UL-020 billing conversion: the bridge preserves supplied billing facts.

Requested by audit lane L02 (UL-005): offer id, price id, minor units, currency,
billing schedule and provenance survive per package. Synthetic fixtures only;
no network, no provider, no live effect.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = SKILL_ROOT / "fixtures"
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "routes"))

import substrate  # noqa: E402
from launcher_core import image_plan, intake, launch_bridge, route  # noqa: E402


def payload(**price_extra):
    doc = json.loads((FIXTURES / "elevation" / "intake.json").read_text(encoding="utf-8"))
    doc["offers"][0]["price"].update(price_extra)
    doc["image_plan"] = {"brand_file": "/tmp/test-brand.json", "brand_owner": "TEST-ONLY Client"}
    return doc


def record(doc):
    normalized = intake.validate(doc)
    inputs, _ = image_plan.resolve(normalized.get("image_plan"), test_only=True)
    return launch_bridge.to_launch_record(
        normalized, route.compile_route(normalized), inputs,
        raw_offers=doc.get("offers") or [])


def first_price(doc):
    return record(doc)["offers"][0]["prices"][0]


class BillingConversionTests(unittest.TestCase):
    def test_absent_billing_facts_keep_the_historical_one_time_shape(self):
        price = first_price(payload())
        self.assertEqual(price, {
            "price_choice_id": "MAIN-ESS-USD",
            "currency": "USD",
            "amount_minor": 9700,
            "billing_type": "one_time",
            "native_price_id": None,
            "schedule": [],
            "approval_status": "approved",
        })

    def test_supplied_installment_schedule_and_price_id_are_preserved(self):
        schedule = [{"amount_minor": 3300, "due": "2026-11-27"},
                    {"amount_minor": 3300, "due": "2026-12-27"},
                    {"amount_minor": 3300, "due": "2027-01-27"}]
        price = first_price(payload(price_choice_id="ESS-3PAY", billing_type="installment",
                                    schedule=schedule, native_price_id="price_test_3pay",
                                    terms_source="approved checkout manuscript 3-pay",
                                    approval_status="provided"))
        self.assertEqual(price["price_choice_id"], "ESS-3PAY")
        self.assertEqual(price["billing_type"], "installment")
        self.assertEqual(price["schedule"], schedule)
        self.assertEqual(price["native_price_id"], "price_test_3pay")
        self.assertEqual(price["terms_source"], "approved checkout manuscript 3-pay")
        self.assertEqual(price["approval_status"], "provided")
        # money facts are the validated ones, never re-derived from the schedule
        self.assertEqual(price["amount_minor"], 9700)
        self.assertEqual(price["currency"], "USD")

    def test_recurring_and_trial_are_carried_not_collapsed(self):
        for billing in ("recurring", "trial"):
            price = first_price(payload(billing_type=billing))
            self.assertEqual(price["billing_type"], billing)

    def test_one_time_with_a_schedule_is_refused(self):
        with self.assertRaises(launch_bridge.BridgeError) as ctx:
            first_price(payload(billing_type="one_time",
                                schedule=[{"amount_minor": 100, "due": "2026-11-27"}]))
        self.assertIn("AF-LAUNCH-BRIDGE-BILLING", str(ctx.exception))

    def test_installment_without_a_schedule_is_refused(self):
        with self.assertRaises(launch_bridge.BridgeError) as ctx:
            first_price(payload(billing_type="installment"))
        self.assertIn("never invented", str(ctx.exception))

    def test_unknown_billing_type_is_refused(self):
        with self.assertRaises(launch_bridge.BridgeError) as ctx:
            first_price(payload(billing_type="layaway"))
        self.assertIn("AF-LAUNCH-BRIDGE-BILLING", str(ctx.exception))

    def test_malformed_schedule_row_is_refused(self):
        with self.assertRaises(launch_bridge.BridgeError):
            first_price(payload(billing_type="installment",
                                schedule=[{"amount_minor": "3300", "due": "2026-11-27"}]))

    def test_per_package_provenance_is_preserved(self):
        # The bridge conversion preserves offer-level provenance once the
        # intake forwards it. intake.py is another lane's file: this test drives
        # the conversion seam directly, and the minimal intake patch is recorded
        # in the lane folder as PATCH-PROPOSAL-intake-provenance.md.
        doc = payload()
        normalized = intake.validate(doc)
        inputs, _ = image_plan.resolve(normalized.get("image_plan"), test_only=True)
        raw = json.loads(json.dumps(doc["offers"]))
        raw[0].update({"source_kind": "existing_verified_catalog",
                       "source_ref": "verified-catalog:ESS-v3",
                       "native_product_id": "prod_test_ess"})
        launch = launch_bridge.to_launch_record(
            normalized, route.compile_route(normalized), inputs, raw_offers=raw)
        offer = launch["offers"][0]
        self.assertEqual(offer["source_kind"], "existing_verified_catalog")
        self.assertEqual(offer["source_ref"], "verified-catalog:ESS-v3")
        self.assertEqual(offer["native_product_id"], "prod_test_ess")

    def test_mode_is_explicit_in_the_bridge(self):
        import tempfile
        doc = payload()
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "never-created"
            with self.assertRaises(launch_bridge.BridgeError) as ctx:
                launch_bridge.run(doc, out, approval={}, client_identity_ref="c",
                                  worker_identity_ref="w", mode="turnkey")
            self.assertIn("AF-LAUNCH-BRIDGE-MODE", str(ctx.exception))
            self.assertFalse(out.exists())


if __name__ == "__main__":
    unittest.main()
