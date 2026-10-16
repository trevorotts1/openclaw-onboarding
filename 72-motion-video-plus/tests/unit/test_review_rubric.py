"""Tests for the MG-033 creative review rubric tooling.

The tooling (scripts/review_rubric.py) validates creative review
records under references/review-rubric-schema.json and the structural
rules of references/critique-protocol.md. These tests prove the
directive acceptance behaviors and every negative case:

- A two-round fixture where the same defect persists refuses the
  inflated second-round score by name (REVIEW_SCORE_INFLATED_
  UNRESOLVED); the capped score and the resolved defect both pass.
- Author self-approval is refused (REVIEW_SELF_APPROVAL).
- Scoring a bundle whose coverage verdict is not complete is refused
  by name (REVIEW_COVERAGE_INCOMPLETE); a coverage record bound to
  another job is refused as a security binding (REVIEW_FOREIGN_JOB).
- A visual sign-off by a vision-incapable reviewer is refused
  (REVIEW_VISION_INCAPABLE); the same reviewer may sign
  data_proof_integrity from records alone.
- A sound judgment without attached measured audio evidence is
  refused (REVIEW_AUDIO_EVIDENCE_MISSING); with an MG-031-style
  measured loudness record attached it passes.
- A claimed 10 against a CALIBRATION_PENDING reference is refused
  (REVIEW_TEN_UNCALIBRATED); a 10 against an OWNER_APPROVED reference
  with a cited approval record passes.
- A scored dimension with no evidence is refused; an unscored
  dimension without a reason fails the schema; verdict ship against
  a failing gate is refused; round six without escalation is
  refused; a defect dropped from the append-only history is refused.
- The dashboard renders the rounds, the calibration state, the
  provisional banner, per-dimension evidence, and the defect ledger
  ordered worst first.

Static fixtures live under tests/fixtures/review-rubric/ (coverage
records, a motion-proof record, a measured audio record, frames);
review records are built per test in a temporary directory.
"""

from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import review_rubric  # noqa: E402

FIXTURES = SKILL_ROOT / "tests" / "fixtures" / "review-rubric"
SCRIPT = SKILL_ROOT / "scripts" / "review_rubric.py"
VIDEO_SHA = "a" * 64

DIMENSIONS = review_rubric.DIMENSIONS


def frame_evidence(frame: str = "frames/frame45.png") -> list:
    return [{"type": "frame", "ref": frame,
             "detail": "fixture frame cited as visual evidence"}]


def base_record() -> dict:
    dims = []
    for name in DIMENSIONS:
        dims.append({
            "dimension": name,
            "status": "scored",
            "score": 7,
            "reference_comparison":
                "Matches the reference on the fixture criteria; "
                "departures are recorded as defects where they "
                "exist.",
            "audio_judgment": False,
            "evidence": frame_evidence(),
            "defects": [],
        })
    return {
        "schema_version": "1.0",
        "kind": "creative_review_record",
        "item": "MG-033",
        "job_id": "fixture-review-job",
        "round": 1,
        "artifact": {
            "video": {"path": "fixture.mp4", "sha256": VIDEO_SHA},
            "mode": "powerpoint_graphic",
            "bundle_dir": ".",
            "coverage_record": "coverage-complete.json",
        },
        "author": {"id": "fixture-author", "kind": "agent",
                   "vision_capable": True},
        "reviewer": {"id": "fixture-reviewer", "kind": "agent",
                     "vision_capable": True},
        "reference": {"reference_id": "VREF-TEST",
                      "calibration_state": "CALIBRATION_PENDING",
                      "approval_record": None},
        "provisional": True,
        "dimensions": dims,
        "remediation": [],
        "verdict": "another_round",
        "escalation_basis": None,
        "notes": None,
    }


def dim(record: dict, name: str) -> dict:
    return next(d for d in record["dimensions"]
                if d["dimension"] == name)


def categories(report: dict) -> list:
    return [f["category"] for f in report["findings"]]


class ReviewRubricCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="mg033-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        for item in FIXTURES.iterdir():
            if item.is_dir():
                shutil.copytree(item, self.tmp / item.name)
            else:
                shutil.copy2(item, self.tmp / item.name)

    def write(self, record: dict, name: str = "record.json") -> Path:
        path = self.tmp / name
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return path

    def validate(self, record: dict, name: str = "record.json",
                 history: bool = True) -> dict:
        path = self.write(record, name)
        return review_rubric.validate_record(
            path, self.tmp if history else None)


class TestValidRecords(ReviewRubricCase):
    def test_valid_round_one_passes(self):
        report = self.validate(base_record())
        self.assertEqual(report["status"], "SUCCEEDED", report)
        self.assertEqual(report["exit_code"], 0)
        self.assertEqual(report["findings"], [])
        self.assertFalse(report["gate"]["passes"])

    def test_ship_verdict_passes_when_gate_passes(self):
        record = base_record()
        for entry in record["dimensions"]:
            entry["score"] = 9
        record["verdict"] = "ship"
        report = self.validate(record)
        self.assertEqual(report["status"], "SUCCEEDED", report)
        self.assertTrue(report["gate"]["passes"])

    def test_ten_passes_against_owner_approved_reference(self):
        record = base_record()
        record["reference"] = {
            "reference_id": "VREF-TEST",
            "calibration_state": "OWNER_APPROVED",
            "approval_record": "owner-decision-2026-10-14.md",
        }
        record["provisional"] = False
        dim(record, "composition")["score"] = 10
        report = self.validate(record)
        self.assertEqual(report["status"], "SUCCEEDED", report)

    def test_vision_incapable_reviewer_may_sign_records_dimension(self):
        record = base_record()
        record["reviewer"]["vision_capable"] = False
        for entry in record["dimensions"]:
            if entry["dimension"] != "data_proof_integrity":
                entry["status"] = "unscored"
                entry["score"] = None
                entry["unscored_reason"] = (
                    "Reviewer cannot see frames; visual dimensions "
                    "require a vision-capable reviewer.")
                entry["reference_comparison"] = None
                entry["evidence"] = []
        entry = dim(record, "data_proof_integrity")
        entry["evidence"] = [{
            "type": "proof_record", "ref": "proof-record.json",
            "detail": "Proof record verdict pass for this job."}]
        report = self.validate(record)
        self.assertEqual(report["status"], "SUCCEEDED", report)

    def test_audio_judgment_with_measured_audio_evidence_passes(self):
        record = base_record()
        entry = dim(record, "finishing")
        entry["audio_judgment"] = True
        entry["evidence"] = frame_evidence() + [{
            "type": "audio_record", "ref": "audio-record.json",
            "detail": "Measured integrated loudness -14.0 LUFS in "
                      "the bundle metrics record."}]
        report = self.validate(record)
        self.assertEqual(report["status"], "SUCCEEDED", report)

    def test_escalation_at_round_five_passes(self):
        first = base_record()
        self.write(first, "round1.json")
        record = base_record()
        record["round"] = 5
        record["verdict"] = "escalate"
        record["escalation_basis"] = (
            "Five correction rounds recorded; gate still fails on "
            "composition and finishing. Full history attached.")
        report = self.validate(record, "round5.json")
        self.assertEqual(report["status"], "SUCCEEDED", report)


class TestRefusals(ReviewRubricCase):
    def test_self_approval_refused(self):
        record = base_record()
        record["reviewer"]["id"] = record["author"]["id"]
        report = self.validate(record)
        self.assertIn("REVIEW_SELF_APPROVAL", categories(report))
        self.assertEqual(report["exit_code"], 4)

    def test_incomplete_coverage_refused_by_name(self):
        record = base_record()
        record["artifact"]["coverage_record"] = \
            "coverage-incomplete.json"
        report = self.validate(record)
        self.assertIn("REVIEW_COVERAGE_INCOMPLETE",
                      categories(report))
        self.assertEqual(report["exit_code"], 6)

    def test_foreign_coverage_refused_as_security_binding(self):
        record = base_record()
        record["artifact"]["coverage_record"] = \
            "coverage-foreign.json"
        report = self.validate(record)
        self.assertIn("REVIEW_FOREIGN_JOB", categories(report))
        self.assertEqual(report["exit_code"], 9)

    def test_vision_incapable_visual_signoff_refused(self):
        record = base_record()
        record["reviewer"]["vision_capable"] = False
        report = self.validate(record)
        self.assertIn("REVIEW_VISION_INCAPABLE", categories(report))
        self.assertEqual(report["exit_code"], 4)

    def test_audio_judgment_without_audio_evidence_refused(self):
        record = base_record()
        dim(record, "finishing")["audio_judgment"] = True
        report = self.validate(record)
        self.assertIn("REVIEW_AUDIO_EVIDENCE_MISSING",
                      categories(report))
        self.assertEqual(report["exit_code"], 3)

    def test_audio_claim_without_measurement_refused(self):
        record = base_record()
        entry = dim(record, "finishing")
        entry["audio_judgment"] = True
        entry["evidence"] = frame_evidence() + [{
            "type": "audio_record", "ref": "proof-record.json",
            "detail": "A record is attached but carries no measured "
                      "audio data."}]
        report = self.validate(record)
        self.assertIn("REVIEW_AUDIO_EVIDENCE_MISSING",
                      categories(report))

    def test_ten_against_pending_calibration_refused(self):
        record = base_record()
        dim(record, "composition")["score"] = 10
        report = self.validate(record)
        self.assertIn("REVIEW_TEN_UNCALIBRATED", categories(report))
        self.assertEqual(report["exit_code"], 4)

    def test_ten_against_fixture_only_reference_refused(self):
        record = base_record()
        record["reference"]["calibration_state"] = \
            "ENGINEERING_FIXTURE_ONLY"
        dim(record, "motion_clarity")["score"] = 10
        report = self.validate(record)
        self.assertIn("REVIEW_TEN_UNCALIBRATED", categories(report))

    def test_owner_approved_without_approval_record_refused(self):
        record = base_record()
        record["reference"]["calibration_state"] = "OWNER_APPROVED"
        record["reference"]["approval_record"] = None
        record["provisional"] = False
        report = self.validate(record)
        self.assertIn("REVIEW_CALIBRATION_UNPROVEN",
                      categories(report))

    def test_provisional_flag_mismatch_refused(self):
        record = base_record()
        record["provisional"] = False
        report = self.validate(record)
        self.assertIn("REVIEW_PROVISIONAL_MISMATCH",
                      categories(report))

    def test_scored_dimension_without_evidence_refused(self):
        record = base_record()
        dim(record, "composition")["evidence"] = []
        report = self.validate(record)
        self.assertIn("REVIEW_EVIDENCE_MISSING", categories(report))
        self.assertEqual(report["exit_code"], 3)

    def test_missing_evidence_file_refused(self):
        record = base_record()
        dim(record, "composition")["evidence"] = [{
            "type": "frame", "ref": "frames/does-not-exist.png",
            "detail": "Cites a frame that is not in the bundle."}]
        report = self.validate(record)
        self.assertIn("REVIEW_INPUT_MISSING", categories(report))

    def test_unscored_dimension_without_reason_fails_schema(self):
        record = base_record()
        entry = dim(record, "composition")
        entry["status"] = "unscored"
        entry["score"] = None
        entry["reference_comparison"] = None
        entry["unscored_reason"] = None
        report = self.validate(record)
        self.assertIn("REVIEW_SCHEMA_INVALID", categories(report))
        self.assertEqual(report["exit_code"], 2)

    def test_ship_verdict_against_failing_gate_refused(self):
        record = base_record()
        record["verdict"] = "ship"
        report = self.validate(record)
        self.assertIn("REVIEW_VERDICT_INCONSISTENT",
                      categories(report))
        self.assertEqual(report["exit_code"], 6)

    def test_round_six_without_escalation_refused(self):
        self.write(base_record(), "round1.json")
        record = base_record()
        record["round"] = 6
        report = self.validate(record, "round6.json")
        self.assertIn("REVIEW_ROUND_LIMIT", categories(report))

    def test_later_round_without_history_refused(self):
        record = base_record()
        record["round"] = 2
        report = self.validate(record, "round2.json", history=False)
        self.assertIn("REVIEW_HISTORY_MISSING", categories(report))

    def test_remediation_not_worst_first_refused(self):
        record = base_record()
        entry = dim(record, "composition")
        entry["defects"] = [
            {"defect_id": "MIN-1", "severity": "minor",
             "description": "Small spacing drift.",
             "cause": "Grid rounding.", "first_seen_round": 1,
             "resolved": False},
            {"defect_id": "CRT-1", "severity": "critical",
             "description": "Value labels clipped at destination "
                            "size.",
             "cause": "Fixed text column wider than the portrait "
                      "plot area.", "first_seen_round": 1,
             "resolved": False},
        ]
        record["remediation"] = ["MIN-1", "CRT-1"]
        report = self.validate(record)
        self.assertIn("REVIEW_REMEDIATION_ORDER", categories(report))

    def two_minors_round_one(self) -> dict:
        record = base_record()
        entry = dim(record, "composition")
        entry["defects"] = [{
            "defect_id": "MIN-A", "severity": "minor",
            "description": "Value column drifts two pixels at the "
                           "hold state.",
            "cause": "Grid rounding at the hold state.",
            "first_seen_round": 1, "resolved": False}]
        record["remediation"] = ["MIN-A"]
        return record

    def two_minors_round_two(self, remediation: list) -> dict:
        record = base_record()
        record["round"] = 2
        entry = dim(record, "composition")
        entry["defects"] = [
            {"defect_id": "MIN-A", "severity": "minor",
             "description": "Value column drifts two pixels at "
                            "the hold state.",
             "cause": "Grid rounding at the hold state.",
             "first_seen_round": 1, "resolved": False},
            {"defect_id": "MIN-B", "severity": "minor",
             "description": "Caption baseline sits one pixel low "
                            "in the portrait variant.",
             "cause": "Portrait baseline grid not snapped.",
             "first_seen_round": 2, "resolved": False},
        ]
        record["remediation"] = remediation
        return record

    def test_remediation_same_severity_later_first_seen_refused(self):
        # The verifier's hand-built case: two minor defects, the
        # one first seen in round 2 listed before the one first
        # seen in round 1. Severity ranks tie, so the documented
        # first-seen tiebreak decides, and this order violates it.
        self.write(self.two_minors_round_one(), "round1.json")
        report = self.validate(
            self.two_minors_round_two(["MIN-B", "MIN-A"]),
            "round2.json")
        self.assertIn("REVIEW_REMEDIATION_ORDER", categories(report))
        self.assertEqual(report["exit_code"], 6)

    def test_remediation_same_severity_earliest_first_seen_passes(self):
        self.write(self.two_minors_round_one(), "round1.json")
        report = self.validate(
            self.two_minors_round_two(["MIN-A", "MIN-B"]),
            "round2.json")
        self.assertEqual(report["status"], "SUCCEEDED", report)


class TestTrend(ReviewRubricCase):
    def round_one_with_defect(self) -> dict:
        record = base_record()
        entry = dim(record, "composition")
        entry["score"] = 6
        entry["defects"] = [{
            "defect_id": "CMP-1", "severity": "major",
            "description": "Value labels sit in a fixed right "
                           "column, far from the bar ends they "
                           "describe.",
            "cause": "Single fixed value column shared by every "
                     "row state.",
            "first_seen_round": 1, "resolved": False}]
        record["remediation"] = ["CMP-1"]
        return record

    def round_two(self, score: int, resolved: bool) -> dict:
        record = base_record()
        record["round"] = 2
        entry = dim(record, "composition")
        entry["score"] = score
        defect = {
            "defect_id": "CMP-1", "severity": "major",
            "description": "Value labels sit in a fixed right "
                           "column, far from the bar ends they "
                           "describe.",
            "cause": "Single fixed value column shared by every "
                     "row state.",
            "first_seen_round": 1, "resolved": resolved}
        if resolved:
            defect["resolution_evidence"] = (
                "Round 2 bundle frame 45 shows values at the bar "
                "ends.")
        entry["defects"] = [defect]
        record["remediation"] = [] if resolved else ["CMP-1"]
        return record

    def test_inflated_score_with_persistent_defect_refused(self):
        self.write(self.round_one_with_defect(), "round1.json")
        report = self.validate(self.round_two(8, False), "round2.json")
        self.assertIn("REVIEW_SCORE_INFLATED_UNRESOLVED",
                      categories(report))
        self.assertEqual(report["exit_code"], 6)
        message = next(f["message"] for f in report["findings"]
                       if f["category"] ==
                       "REVIEW_SCORE_INFLATED_UNRESOLVED")
        self.assertIn("CMP-1", message)
        self.assertIn("6", message)
        self.assertIn("8", message)

    def test_capped_score_with_persistent_defect_passes(self):
        self.write(self.round_one_with_defect(), "round1.json")
        report = self.validate(self.round_two(6, False), "round2.json")
        self.assertEqual(report["status"], "SUCCEEDED", report)

    def test_lower_score_with_persistent_defect_passes(self):
        self.write(self.round_one_with_defect(), "round1.json")
        report = self.validate(self.round_two(5, False), "round2.json")
        self.assertEqual(report["status"], "SUCCEEDED", report)

    def test_resolved_defect_frees_the_score(self):
        self.write(self.round_one_with_defect(), "round1.json")
        report = self.validate(self.round_two(8, True), "round2.json")
        self.assertEqual(report["status"], "SUCCEEDED", report)

    def test_dropped_defect_refused(self):
        self.write(self.round_one_with_defect(), "round1.json")
        record = base_record()
        record["round"] = 2
        report = self.validate(record, "round2.json")
        self.assertIn("REVIEW_DEFECT_DROPPED", categories(report))

    def unscored_round_with_defect(self, rnd: int) -> dict:
        record = base_record()
        record["round"] = rnd
        entry = dim(record, "composition")
        entry["status"] = "unscored"
        entry["score"] = None
        entry["reference_comparison"] = None
        entry["unscored_reason"] = (
            "No destination-size frames were available to this "
            "round; composition is recorded unscored rather than "
            "estimated.")
        entry["evidence"] = []
        entry["defects"] = [{
            "defect_id": "CMP-1", "severity": "major",
            "description": "Value labels sit in a fixed right "
                           "column, far from the bar ends they "
                           "describe.",
            "cause": "Single fixed value column shared by every "
                     "row state.",
            "first_seen_round": 1, "resolved": False}]
        record["remediation"] = ["CMP-1"]
        return record

    def scored_round_with_defect(self, rnd: int, score: int,
                                 owner_approved: bool = False) -> dict:
        record = base_record()
        record["round"] = rnd
        if owner_approved:
            record["reference"] = {
                "reference_id": "VREF-TEST",
                "calibration_state": "OWNER_APPROVED",
                "approval_record": "owner-decision-2026-10-14.md",
            }
            record["provisional"] = False
        entry = dim(record, "composition")
        entry["score"] = score
        entry["defects"] = [{
            "defect_id": "CMP-1", "severity": "major",
            "description": "Value labels sit in a fixed right "
                           "column, far from the bar ends they "
                           "describe.",
            "cause": "Single fixed value column shared by every "
                     "row state.",
            "first_seen_round": 1, "resolved": False}]
        record["remediation"] = ["CMP-1"]
        return record

    def test_first_scored_round_carrying_defect_sets_baseline(self):
        # Round 1 carried CMP-1 but left composition unscored, so
        # it set no baseline. Round 2 is the first scored round
        # carrying the defect: its score of 9 is the baseline
        # being set, not an inflation, and the record passes.
        self.write(self.unscored_round_with_defect(1), "round1.json")
        report = self.validate(
            self.scored_round_with_defect(2, 9), "round2.json")
        self.assertEqual(report["status"], "SUCCEEDED", report)

    def test_round_above_first_scored_baseline_refused(self):
        # Same history, one round later: round 3 scores above the
        # round 2 baseline while CMP-1 is still unresolved, and
        # the tightened cap refuses it. The reference is
        # OWNER_APPROVED so the 10 itself is legal and the only
        # refusal is the inflation.
        self.write(self.unscored_round_with_defect(1), "round1.json")
        self.write(self.scored_round_with_defect(
            2, 9, owner_approved=True), "round2.json")
        report = self.validate(self.scored_round_with_defect(
            3, 10, owner_approved=True), "round3.json")
        self.assertIn("REVIEW_SCORE_INFLATED_UNRESOLVED",
                      categories(report))
        self.assertEqual(report["exit_code"], 6)

    def test_unscored_middle_round_keeps_scored_baseline(self):
        # Round 1 scored composition 6 with CMP-1; round 2 carried
        # the defect unscored; round 3 scoring 8 is still measured
        # against the earliest scored round, round 1.
        self.write(self.round_one_with_defect(), "round1.json")
        self.write(self.unscored_round_with_defect(2), "round2.json")
        report = self.validate(
            self.scored_round_with_defect(3, 8), "round3.json")
        self.assertIn("REVIEW_SCORE_INFLATED_UNRESOLVED",
                      categories(report))


class TestDashboard(ReviewRubricCase):
    def test_dashboard_renders_history_and_calibration(self):
        first = base_record()
        entry = dim(first, "composition")
        entry["score"] = 6
        entry["defects"] = [{
            "defect_id": "CMP-1", "severity": "major",
            "description": "Value column far from bar ends.",
            "cause": "Fixed value column.",
            "first_seen_round": 1, "resolved": False}]
        first["remediation"] = ["CMP-1"]
        text = review_rubric.render_dashboard([first])
        self.assertIn("fixture-review-job", text)
        self.assertIn("CALIBRATION_PENDING", text)
        self.assertIn("PROVISIONAL SCORES", text)
        self.assertIn("Rounds recorded: 1 of 5", text)
        self.assertIn("CMP-1", text)
        self.assertIn("frames/frame45.png", text)
        self.assertIn("never the owner's artistic approval", text)

    def test_dashboard_cli_writes_receipt(self):
        path = self.write(base_record(), "round1.json")
        out = self.tmp / "dashboard.md"
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "dashboard", str(path),
             "--out", str(out)],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("Quality dashboard", out.read_text())


class TestCli(ReviewRubricCase):
    def test_cli_validate_exit_codes(self):
        ok = self.write(base_record(), "ok.json")
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "validate", str(ok),
             "--history-dir", str(self.tmp)],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        record = base_record()
        record["reviewer"]["id"] = record["author"]["id"]
        bad = self.write(record, "bad.json")
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "validate", str(bad),
             "--history-dir", str(self.tmp)],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 4, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["category"], "REVIEW_SELF_APPROVAL")


if __name__ == "__main__":
    unittest.main()
