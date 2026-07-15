#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_prove_intake.py — offline unit tests for scripts/prove_intake.py, the
P1-INTAKE phase gate (Skill 62, build unit U9).

stdlib unittest only. Run:
  python3 -m unittest discover -s tests/unit -v
  (from the 62-cinematic-web-funnel-engine/ directory)
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _TESTS_DIR.parent.parent
_SCRIPTS_DIR = _SKILL_DIR / "scripts"
for p in (str(_SCRIPTS_DIR), str(_SCRIPTS_DIR / "lib")):
    if p not in sys.path:
        sys.path.insert(0, p)

import intake_engine as ie  # noqa: E402
import prove_intake as pi  # noqa: E402

PY = sys.executable or "python3"
GATE_PATH = _SCRIPTS_DIR / "prove_intake.py"


def _lock_valid_brief(run_dir: Path, *, project_id: str = "proj-gate") -> dict:
    return ie.run_scripted_intake(run_dir, project_id=project_id, known_context=None, answer_map=ie._sample_answer_map())


class TestPassScenario(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cwfe-prove-intake-ut-pass-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        _lock_valid_brief(self.tmp)

    def test_evaluate_passes_on_a_fully_locked_valid_brief(self):
        passed, detail = pi.evaluate(self.tmp)
        self.assertTrue(passed, detail)
        self.assertIn("brief_hash", detail)

    def test_cli_exits_zero_on_pass(self):
        proc = subprocess.run([PY, str(GATE_PATH), "--run-dir", str(self.tmp)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("[PASS] P1-INTAKE", proc.stdout)


class TestFailScenarios(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cwfe-prove-intake-ut-fail-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_empty_run_dir_fails_with_missing_artifacts(self):
        passed, detail = pi.evaluate(self.tmp)
        self.assertFalse(passed)
        self.assertIn("AF-CWFE-P1-INTAKE", detail)
        self.assertIn("missing artifact", detail)

    def test_unlocked_brief_fails(self):
        _lock_valid_brief(self.tmp)
        brief_path = self.tmp / "intake" / "project-brief.json"
        data = json.loads(brief_path.read_text())
        data["locked"] = False
        brief_path.write_text(json.dumps(data))
        passed, detail = pi.evaluate(self.tmp)
        self.assertFalse(passed)
        self.assertIn("locked must be true", detail)

    def test_zero_budget_cap_fails(self):
        _lock_valid_brief(self.tmp)
        ba_path = self.tmp / "intake" / "budget-authorization.json"
        data = json.loads(ba_path.read_text())
        data["max_media_spend_usd"] = 0
        ba_path.write_text(json.dumps(data))
        passed, detail = pi.evaluate(self.tmp)
        self.assertFalse(passed)
        self.assertIn("budget cap", detail)

    def test_missing_destination_fails(self):
        _lock_valid_brief(self.tmp)
        brief_path = self.tmp / "intake" / "project-brief.json"
        data = json.loads(brief_path.read_text())
        data["groups"]["hosting"]["vercel_project"] = None
        data["groups"]["hosting"]["alternate_host"] = None
        brief_path.write_text(json.dumps(data))
        passed, detail = pi.evaluate(self.tmp)
        self.assertFalse(passed)
        self.assertIn("destination", detail)

    def test_missing_representation_requirements_fails(self):
        # An empty representation_requirements[] is rejected at the schema
        # layer (minItems: 1) before this gate's own business-logic check
        # ever runs — defense in depth, still a correct fail-closed result.
        _lock_valid_brief(self.tmp)
        brief_path = self.tmp / "intake" / "project-brief.json"
        data = json.loads(brief_path.read_text())
        data["groups"]["brand"]["representation_requirements"] = []
        brief_path.write_text(json.dumps(data))
        passed, detail = pi.evaluate(self.tmp)
        self.assertFalse(passed)
        self.assertIn("representation_requirements", detail)

    def test_missing_required_assets_fails(self):
        _lock_valid_brief(self.tmp)
        brief_path = self.tmp / "intake" / "project-brief.json"
        data = json.loads(brief_path.read_text())
        data["groups"]["project_goal"]["required_assets"] = []
        brief_path.write_text(json.dumps(data))
        passed, detail = pi.evaluate(self.tmp)
        self.assertFalse(passed)
        self.assertIn("required assets", detail)

    def test_missing_approval_policy_field_fails(self):
        # An empty final_deployment_approver is rejected at the schema layer
        # (minLength: 1) before this gate's own business-logic check ever
        # runs — defense in depth, still a correct fail-closed result.
        _lock_valid_brief(self.tmp)
        ap_path = self.tmp / "intake" / "approval-policy.json"
        data = json.loads(ap_path.read_text())
        data["final_deployment_approver"] = ""
        ap_path.write_text(json.dumps(data))
        passed, detail = pi.evaluate(self.tmp)
        self.assertFalse(passed)
        self.assertIn("final_deployment_approver", detail)

    def test_truth_source_deleted_after_lock_fails_gate(self):
        # This is the key adversarial case: a locked brief on disk is
        # tampered with directly (bypassing intake_engine entirely) — the
        # gate must catch it independently, never trusting locked=True alone.
        _lock_valid_brief(self.tmp)
        ts_path = self.tmp / "intake" / "truth-sources.json"
        data = json.loads(ts_path.read_text())
        self.assertEqual(len(data["sources"]), 2)
        data["sources"] = data["sources"][:1]  # drop one claim's truth source
        ts_path.write_text(json.dumps(data))
        passed, detail = pi.evaluate(self.tmp)
        self.assertFalse(passed)
        self.assertIn("missing truth source", detail)

    def test_duplicate_truth_source_entry_fails_gate(self):
        _lock_valid_brief(self.tmp)
        ts_path = self.tmp / "intake" / "truth-sources.json"
        data = json.loads(ts_path.read_text())
        data["sources"].append(dict(data["sources"][0]))  # duplicate claim_id
        ts_path.write_text(json.dumps(data))
        passed, detail = pi.evaluate(self.tmp)
        self.assertFalse(passed)
        self.assertIn("duplicate truth source", detail)

    def test_truth_source_ids_mismatch_fails_gate(self):
        _lock_valid_brief(self.tmp)
        brief_path = self.tmp / "intake" / "project-brief.json"
        data = json.loads(brief_path.read_text())
        data["truth_source_ids"] = ["offer.proof#0"]  # drop one, no longer matches groups.offer.proof
        brief_path.write_text(json.dumps(data))
        passed, detail = pi.evaluate(self.tmp)
        self.assertFalse(passed)
        self.assertIn("truth_source_ids", detail)

    def test_corrupt_json_fails_closed(self):
        _lock_valid_brief(self.tmp)
        brief_path = self.tmp / "intake" / "project-brief.json"
        brief_path.write_text("{not valid json")
        passed, detail = pi.evaluate(self.tmp)
        self.assertFalse(passed)
        self.assertIn("corrupt JSON", detail)

    def test_cli_exits_two_on_fail(self):
        proc = subprocess.run([PY, str(GATE_PATH), "--run-dir", str(self.tmp)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("[FAIL] P1-INTAKE", proc.stderr)


class TestCliUsageErrors(unittest.TestCase):
    def test_nonexistent_run_dir_is_usage_error(self):
        proc = subprocess.run(
            [PY, str(GATE_PATH), "--run-dir", "/nonexistent/run/dir/for/u9/tests"],
            capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 3)
        self.assertIn("USAGE ERROR", proc.stderr)

    def test_run_dir_is_a_file_not_a_directory_is_usage_error(self):
        with tempfile.NamedTemporaryFile() as f:
            proc = subprocess.run([PY, str(GATE_PATH), "--run-dir", f.name], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
