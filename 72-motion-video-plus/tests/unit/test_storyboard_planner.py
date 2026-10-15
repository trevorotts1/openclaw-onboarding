"""Planner-gate tests for the MG-009 visual-storytelling validator.

The fixtures under tests/fixtures/storyboards pair each storyboard.json with
its planner record (planner.json) and the minimal job context the planner
layer resolves against (assets.json, data/, scenes/). Passing fixtures cover
genuine image-led, chart, and mechanism storytelling. Negative fixtures each
isolate one planner failure category. Mutation tests edit a passing fixture
in a temp copy and prove the validator catches the change.

Run from the skill root:
    python3 -m unittest discover -s tests/unit
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import validate_storyboard as planner  # noqa: E402

FIXTURES = SKILL_ROOT / "tests" / "fixtures" / "storyboards"

PASS_FIXTURES = ("pass-image-led", "pass-chart", "pass-mechanism")

NEGATIVE_FIXTURES = {
    "fail-text-only": {planner.COVERAGE},
    "fail-typography-evasion": {planner.COVERAGE},
    "fail-unrelated-assertion": {planner.ASSERTION_SUBJECT_MISMATCH},
    "fail-missing-proof-state": {planner.SCHEMA_INVALID},
    "fail-literal-evidence-missing": {planner.EVIDENCE_UNRESOLVED},
}


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, doc) -> None:
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def _categories(findings) -> set:
    return {f["category"] for f in findings}


class PassingFixtureTests(unittest.TestCase):
    def test_passing_fixtures_have_zero_findings(self):
        for name in PASS_FIXTURES:
            with self.subTest(fixture=name):
                findings = planner.validate_storyboard(FIXTURES / name)
                self.assertEqual([], findings, f"{name} must pass the planner gate")

    def test_coverage_numbers_for_chart_fixture(self):
        storyboard = _load(FIXTURES / "pass-chart" / "storyboard.json")
        report = planner.coverage_report(storyboard)
        self.assertEqual(3, report["explanatory_beats"])
        self.assertEqual(2, report["non_text_beats"])
        self.assertEqual(1, report["typography_beats"])
        self.assertEqual(2, report["required_non_text"])
        self.assertTrue(report["passes"])

    def test_required_non_text_rounds_up(self):
        # Section 1.1: two-thirds of explanatory beats, rounding up.
        self.assertEqual(1, planner.required_non_text(1))
        self.assertEqual(2, planner.required_non_text(2))
        self.assertEqual(2, planner.required_non_text(3))
        self.assertEqual(3, planner.required_non_text(4))
        self.assertEqual(4, planner.required_non_text(5))


class NegativeFixtureTests(unittest.TestCase):
    def test_negative_fixtures_fail_with_the_isolated_category(self):
        for name, expected in NEGATIVE_FIXTURES.items():
            with self.subTest(fixture=name):
                findings = planner.validate_storyboard(FIXTURES / name)
                self.assertTrue(findings, f"{name} must fail the planner gate")
                self.assertEqual(
                    expected,
                    _categories(findings),
                    f"{name} must fail with exactly {sorted(expected)}",
                )

    def test_missing_proof_state_is_a_schema_failure_first(self):
        findings = planner.validate_storyboard(FIXTURES / "fail-missing-proof-state")
        self.assertEqual(planner.SCHEMA_INVALID, planner.first_error_category(findings))

    def test_text_only_plan_fails_coverage_despite_exceptions(self):
        # Every beat in fail-text-only carries a typography_only_exception.
        # The exception is a rationale, not an exemption from the count.
        findings = planner.validate_storyboard(FIXTURES / "fail-text-only")
        coverage = [f for f in findings if f["category"] == planner.COVERAGE]
        self.assertEqual(1, len(coverage))
        self.assertIn("0 of 3", coverage[0]["message"])


class MutationTests(unittest.TestCase):
    """Edit a passing fixture in a temp copy; the gate must catch it."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def copy_fixture(self, name: str) -> Path:
        target = self.tmp / name
        shutil.copytree(FIXTURES / name, target)
        return target

    def test_rebinding_assertion_to_unrelated_subject_fails(self):
        job = self.copy_fixture("pass-mechanism")
        scene_path = job / "scenes" / "flow-01.json"
        scene = _load(scene_path)
        for assertion in scene["semantic_motion_assertions"]:
            if assertion["id"] == "item-traverses-stages":
                assertion["subject_ids"] = ["stage-backdrop"]
        _save(scene_path, scene)
        findings = planner.validate_storyboard(job)
        self.assertIn(planner.ASSERTION_SUBJECT_MISMATCH, _categories(findings))

    def test_removing_typography_exception_rationale_fails(self):
        job = self.copy_fixture("pass-chart")
        storyboard_path = job / "storyboard.json"
        storyboard = _load(storyboard_path)
        for beat in storyboard["beats"]:
            if beat["id"] == "beat-headline":
                beat["typography_only_exception"] = None
        _save(storyboard_path, storyboard)
        findings = planner.validate_storyboard(job)
        self.assertIn(planner.EXCEPTION_MISSING, _categories(findings))

    def test_deleting_a_planner_record_fails(self):
        job = self.copy_fixture("pass-image-led")
        planner_path = job / "planner.json"
        doc = _load(planner_path)
        doc["beats"] = [b for b in doc["beats"] if b["beat_id"] != "beat-reveal"]
        _save(planner_path, doc)
        findings = planner.validate_storyboard(job)
        self.assertIn(planner.FIELD_MISSING, _categories(findings))

    def test_unbinding_all_assertions_fails(self):
        job = self.copy_fixture("pass-chart")
        planner_path = job / "planner.json"
        doc = _load(planner_path)
        for entry in doc["beats"]:
            if entry["beat_id"] == "beat-bars":
                entry["assertion_ids"] = []
        _save(planner_path, doc)
        findings = planner.validate_storyboard(job)
        self.assertIn(planner.ASSERTION_MISSING, _categories(findings))

    def test_renaming_a_dataset_id_breaks_literal_evidence(self):
        job = self.copy_fixture("pass-chart")
        data_path = job / "data" / "bars.json"
        dataset = _load(data_path)
        dataset["id"] = "bars-renamed"
        _save(data_path, dataset)
        findings = planner.validate_storyboard(job)
        self.assertIn(planner.EVIDENCE_UNRESOLVED, _categories(findings))


class CliTests(unittest.TestCase):
    def run_cli(self, target: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                str(SKILL_ROOT / "scripts" / "validate_storyboard.py"),
                "validate",
                str(target),
            ],
            capture_output=True,
            text=True,
        )

    def test_cli_passes_a_good_plan_with_exit_0(self):
        proc = self.run_cli(FIXTURES / "pass-mechanism")
        self.assertEqual(0, proc.returncode, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertTrue(result["valid"])
        self.assertIsNone(result["first_error_category"])
        self.assertTrue(result["coverage"]["passes"])

    def test_cli_fails_a_text_only_plan_with_exit_2(self):
        proc = self.run_cli(FIXTURES / "fail-text-only")
        self.assertEqual(2, proc.returncode, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertFalse(result["valid"])
        self.assertEqual(planner.COVERAGE, result["first_error_category"])


if __name__ == "__main__":
    unittest.main()
