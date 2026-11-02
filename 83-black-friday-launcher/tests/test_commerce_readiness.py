"""S44-13: 83 refuses 'ready' while a launch-plan commerce unit has a null native id."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "commerce_rule", SKILL_ROOT / "launcher_core/check_rules/commerce.py")
commerce = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(commerce)

GOOD = [
    {"id": "main_offer", "kind": "product",
     "native_product_id": "prod_1", "native_price_id": "price_1"},
    {"id": "bump", "kind": "order_bump",
     "native_product_id": "prod_2", "native_price_id": "price_2"},
    {"id": "stripe", "kind": "payment_provider", "operator_confirmed": True},
]


def run_rule(plan: dict) -> list:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        manifest = {"launch_plan": {"plan": {"path": "plan.json"}}}
        return commerce.violations(manifest, root, SKILL_ROOT)


class CommerceReadinessTests(unittest.TestCase):
    def test_complete_units_pass(self):
        self.assertEqual(run_rule({"commerce_units": GOOD}), [])

    def test_null_native_ids_fail(self):
        for field in ("native_product_id", "native_price_id"):
            for bad in (None, "", "TBD"):
                units = [dict(GOOD[0]), *GOOD[1:]]
                units[0][field] = bad
                fails = run_rule({"commerce_units": units})
                self.assertEqual(len(fails), 1, (field, bad, fails))
                self.assertIn("AF-LAUNCH-COMMERCE-NATIVE-ID", fails[0])
                self.assertIn(field, fails[0])

    def test_missing_native_id_key_fails(self):
        unit = {"id": "upsell_1", "kind": "upsell", "native_product_id": "prod_3"}
        fails = run_rule({"commerce_units": [unit, GOOD[2]]})
        self.assertTrue(any("AF-LAUNCH-COMMERCE-NATIVE-ID" in f and "native_price_id" in f
                            for f in fails), fails)

    def test_unconfirmed_payment_provider_fails(self):
        fails = run_rule({"commerce_units": [GOOD[0], {"id": "stripe", "kind": "payment_provider"}]})
        self.assertEqual([f.split(":")[0] for f in fails], ["AF-LAUNCH-COMMERCE-PROVIDER"])

    def test_unknown_kind_fails(self):
        fails = run_rule({"commerce_units": [{"id": "x", "kind": "coupon"}]})
        self.assertEqual([f.split(":")[0] for f in fails], ["AF-LAUNCH-COMMERCE-KIND"])

    def test_checkout_plan_without_commerce_unit_fails(self):
        plan = {"pages": [{"id": "order_page", "kind": "order"}]}
        fails = run_rule(plan)
        self.assertEqual([f.split(":")[0] for f in fails], ["AF-LAUNCH-COMMERCE-MISSING"])
        self.assertEqual(run_rule({**plan, "commerce_units": []})[0].split(":")[0],
                         "AF-LAUNCH-COMMERCE-MISSING")

    def test_plan_that_sells_nothing_and_page_only_package_pass(self):
        self.assertEqual(run_rule({"pages": [{"id": "lp", "kind": "landing"}]}), [])
        self.assertEqual(commerce.violations({}, Path("."), SKILL_ROOT), [])


if __name__ == "__main__":
    unittest.main()
