"""C01: the factory's own production-order gate, tested directly (the governed
production_process layer refuses first on a real run, so the end-to-end tests
cannot show this gate alone holds). Offline; local temp dirs only."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

CORE = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(CORE), str(CORE / "intake_preflight")]
from intake_preflight import factory


class OrderGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run = Path(self.tmp.name)
        self.arts = factory.STAGE_REGISTRY["research"]["required_artifacts"]
        self.assertTrue(self.arts)

    def test_complete_predecessor_with_missing_artifacts_is_refused_by_name(self):
        ok, code, detail, missing = factory.production_order_gate(
            self.run, "creative-strategy", got={"research": "COMPLETE"})
        self.assertFalse(ok)
        self.assertEqual(code, "PRODUCTION_ORDER_VIOLATION")
        self.assertEqual(sorted(missing), sorted(self.arts))
        self.assertIn("research", detail)

    def test_predecessor_with_artifacts_passes(self):
        for rel in self.arts:
            (self.run / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.run / rel).write_text("{}")
        ok, code, _, missing = factory.production_order_gate(
            self.run, "creative-strategy", got={"research": "COMPLETE"})
        self.assertTrue(ok, (code, missing))

    def test_unknown_stage_is_refused_not_assumed(self):
        ok, code, _, _ = factory.production_order_gate(self.run, "not-a-stage")
        self.assertFalse(ok)
        self.assertEqual(code, "PRODUCTION_ORDER_UNKNOWN_STAGE")

    def test_admit_stage_applies_the_gate_after_governed_admission(self):
        with mock.patch.object(factory, "_production_admission",
                               return_value={"ok": True, "run_id": "r"}):
            refused = factory._admit_stage(self.run, "creative-strategy", run_id="r",
                                           got={"research": "COMPLETE"})
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["reason_code"], "PRODUCTION_ORDER_VIOLATION")
        self.assertEqual(sorted(refused["missing_artifacts"]), sorted(self.arts))
        self.assertTrue(refused["governed_admission"]["ok"])

    def test_admit_stage_keeps_a_governed_refusal_unchanged(self):
        gov = {"ok": False, "reason_code": "PRODUCTION_PREDECESSOR_INCOMPLETE"}
        with mock.patch.object(factory, "_production_admission", return_value=gov):
            self.assertEqual(factory._admit_stage(self.run, "creative-strategy"), gov)


if __name__ == "__main__":
    unittest.main()
