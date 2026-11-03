"""S44-13: 83 refuses 'ready' while a launch-plan commerce unit has a null native id."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILL_ROOT))

from launcher_core.constants import resolve_ref  # noqa: E402

SIGLAUNCH = resolve_ref("44-convert-and-flow-operator/tools/siglaunch")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


commerce = _load("commerce_rule", SKILL_ROOT / "launcher_core/check_rules/commerce.py")
provisioning = _load("siglaunch_provisioning", SIGLAUNCH / "provisioning/provisioning.py")
caf_executor = _load("siglaunch_caf_executor", SIGLAUNCH / "receiver/caf_executor.py")

GOOD = [
    {"id": "main_offer", "kind": "product",
     "native_product_id": "prod_1", "native_price_id": "price_1"},
    {"id": "bump", "kind": "order_bump",
     "native_product_id": "prod_2", "native_price_id": "price_2"},
    {"id": "stripe", "kind": "payment_provider", "operator_confirmed": True},
]


def run_rule(plan: dict, test_only: bool = False) -> list:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        manifest = {"launch_plan": {"plan": {"path": "plan.json"}}, "test_only": test_only}
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
        # an offline test_only package is not claimed sellable, so it may omit the list
        self.assertEqual(run_rule({"pages": [{"id": "o", "kind": "order"}]}, test_only=True), [])
        # ...but a present list is always validated
        self.assertEqual(len(run_rule({"commerce_units": [{"id": "p", "kind": "product"}]},
                                      test_only=True)), 2)
        self.assertEqual(commerce.violations({}, Path("."), SKILL_ROOT), [])


LOC = "LOC1"
OFFER = {"logical_id": "bf_main", "name": "Black Friday Bundle",
         "price": {"amount_minor": 19700, "currency": "USD"}}


class FakeCatalog:
    """Live product store: every read returns the current native object."""

    def __init__(self, products=None):
        self.products = dict(products or {})
        self.creates = 0

    def native(self, pid, name, amount, loc=LOC):
        self.products[pid] = {"native_product_id": pid, "location_id": loc, "name": name,
                              "prices": [{"native_price_id": "pr_" + pid,
                                          "amount_minor": amount, "currency": "USD"}]}

    def list_product_objects(self, loc):
        return list(self.products.values())

    def get_product(self, loc, pid):
        return self.products.get(pid)

    def create_product_with_price(self, loc, name, price):
        self.creates += 1
        pid = f"new{self.creates}"
        self.native(pid, name, price["amount_minor"], loc)
        return pid


class ProvisioningCommerceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Path(self.tmp.name) / "ledger.json"

    def tearDown(self):
        self.tmp.cleanup()

    def provision(self, cat):
        return provisioning.provision(cat, LOC, {"products": [OFFER]}, self.ledger)

    def executor(self, cat):
        return caf_executor.CafExecutor(
            runner=lambda a, t: (0, "", ""), provisioning_ledger=str(self.ledger),
            product_reader=lambda loc, pid: cat.get_product(loc, pid))

    WF = {"requires": {"products": ["bf_main"]}}

    def test_same_name_other_price_is_not_provisioned(self):
        cat = FakeCatalog()
        cat.native("old", "Black Friday Bundle", 29700)  # last year's $297
        receipt = self.provision(cat)
        item = receipt["items"][0]
        self.assertEqual(item["state"], "created")
        self.assertEqual(cat.creates, 1)
        native = json.loads(self.ledger.read_text())[LOC]["product_native"]["bf_main"]
        self.assertEqual(native["native_product_id"], "new1")  # never the $297 product
        self.assertEqual(native["native_price_id"], "pr_new1")
        self.assertEqual(native["amount_minor"], 19700)

    def test_matching_product_is_adopted_with_native_ids_and_rerun_is_idempotent(self):
        cat = FakeCatalog()
        cat.native("p1", "Black Friday Bundle", 19700)
        self.assertEqual(self.provision(cat)["items"][0]["state"], "existed")
        self.provision(cat)
        self.assertEqual(cat.creates, 0)
        native = json.loads(self.ledger.read_text())[LOC]["product_native"]["bf_main"]
        self.assertEqual((native["native_product_id"], native["native_price_id"]), ("p1", "pr_p1"))

    def test_other_location_product_is_not_adopted(self):
        cat = FakeCatalog()
        cat.native("p1", "Black Friday Bundle", 19700, loc="OTHER")
        self.assertEqual(self.provision(cat)["items"][0]["state"], "created")

    def test_unverified_create_is_not_recorded(self):
        cat = FakeCatalog()
        cat.create_product_with_price = lambda loc, name, price: "ghost"  # read-back finds nothing
        receipt = self.provision(cat)
        self.assertEqual(receipt["items"][0]["state"], "unverified")
        self.assertFalse(receipt["complete"])
        self.assertEqual(json.loads(self.ledger.read_text())[LOC]["product_native"], {})

    def test_bare_name_product_is_flagged_and_never_native(self):
        cat = FakeCatalog()
        cat.list_products = lambda loc: ["Black Friday Bundle"]
        receipt = provisioning.provision(cat, LOC, {"products": ["Black Friday Bundle"]},
                                         self.ledger)
        self.assertTrue(receipt["items"][0]["price_unverified"])
        self.assertEqual(json.loads(self.ledger.read_text())[LOC]["product_native"], {})
        wf = {"requires": {"products": ["Black Friday Bundle"]}}
        self.assertEqual(len(self.executor(cat).dependencies_present(LOC, wf)), 1)

    def test_executor_accepts_only_what_a_live_get_confirms(self):
        cat = FakeCatalog()
        self.provision(cat)
        ex = self.executor(cat)
        self.assertEqual(ex.dependencies_present(LOC, self.WF), [])
        cat.native("new1", "Black Friday Bundle", 29700)  # price changed after the ledger
        self.assertEqual(len(ex.dependencies_present(LOC, self.WF)), 1)
        del cat.products["new1"]  # product gone: the ledger still claims it
        self.assertIn("does not match", ex.dependencies_present(LOC, self.WF)[0])

    def test_forged_ledger_is_refused_by_plan_terms(self):
        cat = FakeCatalog()
        cat.native("p9", "Black Friday Bundle", 29700)
        self.ledger.write_text(json.dumps({LOC: {"product_native": {"bf_main": {
            "native_product_id": "p9", "native_price_id": "pr_p9", "name": "Black Friday Bundle",
            "amount_minor": 29700, "currency": "USD"}}}}))
        wf = {"requires": {"products": ["bf_main"], "product_terms": {
            "bf_main": {"amount_minor": 19700, "currency": "USD"}}}}
        self.assertEqual(len(self.executor(cat).dependencies_present(LOC, wf)), 1)
        self.assertEqual(self.executor(cat).dependencies_present(LOC, self.WF), [])  # ledger-only terms

    def test_no_reader_means_unverified(self):
        cat = FakeCatalog()
        self.provision(cat)
        ex = caf_executor.CafExecutor(runner=lambda a, t: (0, "", ""),
                                      provisioning_ledger=str(self.ledger))
        self.assertIn("no live product reader", ex.dependencies_present(LOC, self.WF)[0])


if __name__ == "__main__":
    unittest.main()
