"""S44-03 Phase-A provisioning proofs against a fake catalog."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "receiver"))
from provisioning import provision


class FakeCatalog:
    def __init__(self):
        self.tags = {"siglaunch:purchased:main"}
        self.fields = set()
        self.products = set()
        self.creates = []
        self.drop_creates = False  # simulate write-succeeded/verify-fail

    def list_tags(self, loc):
        return sorted(self.tags)

    def create_tag(self, loc, name):
        self.creates.append(("tag", name))
        if not self.drop_creates:
            self.tags.add(name)

    def list_fields(self, loc):
        return sorted(self.fields)

    def create_field(self, loc, name, field_type):
        self.creates.append(("field", name))
        if not self.drop_creates:
            self.fields.add(name)

    def list_products(self, loc):
        return sorted(self.products)

    def create_product(self, loc, name):
        self.creates.append(("product", name))
        if not self.drop_creates:
            self.products.add(name)


MANIFEST = {
    "tags": ["siglaunch:purchased:main", "siglaunch:purchased:bump"],
    "fields": [{"name": "siglaunch_launch_id", "type": "TEXT"}],
    "products": ["Signature Launch Main"],
}


class ProvisioningTests(unittest.TestCase):
    def test_get_first_creates_only_missing_and_writes_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            cat = FakeCatalog()
            ledger = Path(d) / "ledger.json"
            receipt = provision(cat, "LOC1", MANIFEST, ledger)
            states = {(i["kind"], i["name"]): i["state"]
                      for i in receipt["items"]}
            self.assertEqual(
                states[("tags", "siglaunch:purchased:main")], "existed")
            self.assertEqual(
                states[("tags", "siglaunch:purchased:bump")], "created")
            self.assertTrue(receipt["complete"])
            on_disk = json.loads(ledger.read_text())
            self.assertEqual(on_disk["LOC1"]["tags"],
                             ["siglaunch:purchased:main",
                              "siglaunch:purchased:bump"])
            # the receiver's dependency precheck reads this exact ledger
            from caf_executor import CafExecutor
            ex = CafExecutor(runner=lambda a, t: (0, "", ""),
                             provisioning_ledger=str(ledger))
            wf = {"requires": {"tags": ["siglaunch:purchased:bump"]}}
            self.assertEqual(ex.dependencies_present("LOC1", wf), [])

    def test_second_run_is_fully_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            cat = FakeCatalog()
            ledger = Path(d) / "ledger.json"
            provision(cat, "LOC1", MANIFEST, ledger)
            creates_after_first = len(cat.creates)
            receipt2 = provision(cat, "LOC1", MANIFEST, ledger)
            self.assertEqual(len(cat.creates), creates_after_first)
            self.assertTrue(all(i["state"] == "existed"
                                for i in receipt2["items"]))

    def test_unverified_create_never_enters_ledger(self):
        with tempfile.TemporaryDirectory() as d:
            cat = FakeCatalog()
            cat.drop_creates = True
            ledger = Path(d) / "ledger.json"
            receipt = provision(cat, "LOC1",
                                {"tags": ["siglaunch:purchased:bump"]},
                                ledger)
            self.assertEqual(receipt["items"][0]["state"], "unverified")
            self.assertFalse(receipt["complete"])
            on_disk = json.loads(ledger.read_text())
            self.assertEqual(on_disk["LOC1"]["tags"], [])


if __name__ == "__main__":
    unittest.main()
