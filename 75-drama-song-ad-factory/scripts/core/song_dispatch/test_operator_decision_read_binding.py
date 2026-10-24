#!/usr/bin/env python3
"""A recorded operator decision binds current evidence on every downstream read.

Actual renderer-confirmed intake, governed predecessors, script approval and
music completion are reused from the existing operator-decision fixture.
No media, transport or provider calls are needed.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
CORE = HERE.parent
sys.path[:0] = [str(CORE), str(HERE), str(CORE / "intake_preflight")]
import test_operator_decision_v2973 as fixture
import production_process

SD = fixture.SD


class OperatorDecisionReadBinding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="operator-read-binding-")
        cls.run_dir = fixture.new_run(cls.tmp.name)
        fixture.F.music_stage(cls.run_dir, fixture.OWNER, "start")
        result = fixture.F.music_stage(
            cls.run_dir, fixture.OWNER, "complete", qc=fixture._qc(),
            operator_decision=fixture._decision(cls.run_dir, operator="fixture-operator"))
        if result["outcome"] != "ok":
            raise AssertionError(result)
        cls.decision_path = Path(SD.operator_decision_path(cls.run_dir))
        cls.evidence_path = Path(cls.run_dir) / "music" / "acceptance" / "v1.json"
        cls.decision_bytes = cls.decision_path.read_bytes()
        cls.evidence_bytes = cls.evidence_path.read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.decision_path.write_bytes(self.decision_bytes)
        self.evidence_path.write_bytes(self.evidence_bytes)

    def tearDown(self):
        self.decision_path.write_bytes(self.decision_bytes)
        self.evidence_path.write_bytes(self.evidence_bytes)

    def assert_refused(self, expected):
        before_decision = self.decision_path.read_bytes()
        before_evidence = (self.evidence_path.read_bytes()
                           if self.evidence_path.exists() else None)
        decision, reasons = SD.decision_applies(self.run_dir)
        self.assertIsNone(decision)
        self.assertTrue(any(expected in reason for reason in reasons), reasons)
        admission = production_process.admit_production(self.run_dir, "continuity-bible")
        self.assertFalse(admission["ok"], admission)
        self.assertEqual("ACCEPTANCE_NOT_PROVEN", admission["reason_code"])
        self.assertEqual(before_decision, self.decision_path.read_bytes())
        self.assertEqual(before_evidence, self.evidence_path.read_bytes()
                         if self.evidence_path.exists() else None)

    def test_current_accepted_decision_advances_without_rewriting_evidence(self):
        decision, reasons = SD.decision_applies(self.run_dir)
        self.assertIsNotNone(decision)
        self.assertEqual([], reasons)
        result = production_process.admit_production(self.run_dir, "continuity-bible")
        self.assertTrue(result["ok"], result)
        self.assertEqual(self.decision_bytes, self.decision_path.read_bytes())
        self.assertEqual(self.evidence_bytes, self.evidence_path.read_bytes())
        self.assertEqual("UNMEASURED", json.loads(self.evidence_bytes)["results"]["D5"]["verdict"])

    def test_mismatched_persisted_digest_is_refused(self):
        decision = json.loads(self.decision_bytes)
        decision["measured_evidence_digest"] = "0" * 64
        self.decision_path.write_text(json.dumps(decision), encoding="utf-8")
        self.assert_refused("OPERATOR_DECISION_EVIDENCE_MISMATCH")

    def test_changed_current_evidence_invalidates_accepted_decision(self):
        evidence = json.loads(self.evidence_bytes)
        evidence["results"]["D5"]["binding"]["creative_revision"] = "fixture-next-revision"
        self.evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
        self.assert_refused("OPERATOR_DECISION_EVIDENCE_MISMATCH")
        self.assertEqual("UNMEASURED", json.loads(self.evidence_path.read_bytes())["results"]["D5"]["verdict"])

    def test_missing_and_corrupt_current_evidence_are_refused(self):
        self.evidence_path.unlink()
        self.assert_refused("OPERATOR_DECISION_EVIDENCE_MISSING")
        for raw in (b"{not json", b'{"results": []}'):
            with self.subTest(raw=raw):
                self.evidence_path.write_bytes(raw)
                self.assert_refused("OPERATOR_DECISION_EVIDENCE_UNREADABLE")

    def test_explicit_current_variant_scope_uses_same_writer_and_reader_binding(self):
        decision = fixture._decision(self.run_dir, variants=["v1"], operator="fixture-operator")
        SD.record_operator_decision(self.run_dir, decision)
        written = self.decision_path.read_bytes()
        current, reasons = SD.decision_applies(self.run_dir)
        self.assertIsNotNone(current)
        self.assertEqual([], reasons)
        self.assertTrue(production_process.admit_production(self.run_dir, "continuity-bible")["ok"])
        self.assertEqual(written, self.decision_path.read_bytes())
        self.assertEqual(self.evidence_bytes, self.evidence_path.read_bytes())

    def test_writer_uses_same_current_evidence_check_without_overwriting_decision(self):
        bad = fixture._decision(self.run_dir, measured_evidence_digest="0" * 64)
        with self.assertRaisesRegex(SD.DispatchError, "OPERATOR_DECISION_EVIDENCE_MISMATCH"):
            SD.record_operator_decision(self.run_dir, bad)
        self.assertEqual(self.decision_bytes, self.decision_path.read_bytes())
        self.evidence_path.unlink()
        with self.assertRaisesRegex(SD.DispatchError, "OPERATOR_DECISION_EVIDENCE_MISSING"):
            SD.record_operator_decision(self.run_dir, fixture._decision(self.run_dir))
        self.assertEqual(self.decision_bytes, self.decision_path.read_bytes())


if __name__ == "__main__":
    unittest.main()
