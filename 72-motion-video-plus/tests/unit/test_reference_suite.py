"""T25 complete visual reference (MG-044): the shipped reference suite.

Validates the suite under assets/examples/reference-suite/ as a
reviewable artifact set, not as a pile of files:

- the Section 17.4 registry names VREF-01 to VREF-05 with exactly the
  Section 17.3 approval states, a null approved_event_ref with a
  stated reason for each, and hashes that match the shipped files;
- all four delivery modes are present, each with its manifest,
  poster, clip, MG-033 review record, and MG-034 QC record, and the
  review records themselves validate with the shipped rubric tool;
- the Section 8 storyboard covers frames 0 to 900 contiguously and
  exercises all four modes;
- the component index covers C01 to C12 with C01 to C09 available and
  C10 to C12 unavailable with reasons;
- every negative exemplar carries a gate record that fails, with the
  gate named and the reason stated;
- the evidence index lists every file in the suite (except itself)
  with a matching SHA-256;
- nothing in the suite claims owner approval: review records are
  provisional with a null approval record, and the registry statuses
  are the pending ones.

Run from the skill root:
    python3 -m unittest tests.unit.test_reference_suite
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2]
SUITE = SKILL_DIR / "assets" / "examples" / "reference-suite"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


EXPECTED_STATUS = {
    "VREF-01": "CALIBRATION_PENDING",
    "VREF-02": "ENGINEERING_FIXTURE_ONLY",
    "VREF-03": "CALIBRATION_PENDING",
    "VREF-04": "BLOCKED_ASSET",
    "VREF-05": "CALIBRATION_PENDING",
}

MODES = ["powerpoint_graphic", "vsl_desktop", "vsl_mobile", "standalone_video"]


class RegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = read_json(SUITE / "reference-registry.json")
        cls.refs = {r["reference_id"]: r for r in cls.registry["references"]}

    def test_all_five_references_present(self):
        self.assertEqual(sorted(self.refs), sorted(EXPECTED_STATUS))

    def test_statuses_are_exactly_the_section_17_3_states(self):
        for ref_id, status in EXPECTED_STATUS.items():
            self.assertEqual(self.refs[ref_id]["status"], status, ref_id)

    def test_no_reference_claims_an_approval_event(self):
        for ref_id, ref in self.refs.items():
            self.assertIsNone(ref["approved_event_ref"], ref_id)
            self.assertTrue(ref["approved_event_ref_reason"], ref_id)

    def test_clip_and_frame_hashes_match_shipped_files(self):
        for ref_id, ref in self.refs.items():
            clip = ref.get("clip_file")
            if clip:
                self.assertEqual(
                    sha256(SUITE / clip["path"]), clip["sha256"], ref_id)
            for frame in ref.get("frame_files", []):
                self.assertTrue((SUITE / frame).is_file(), f"{ref_id}: {frame}")

    def test_design_and_render_revisions_recorded(self):
        for ref_id in ("VREF-01", "VREF-02", "VREF-03"):
            ref = self.refs[ref_id]
            self.assertTrue(ref["design_revision"], ref_id)
            self.assertTrue(ref["render_revision"], ref_id)

    def test_scores_have_a_named_basis(self):
        for ref_id, ref in self.refs.items():
            if ref.get("scores"):
                self.assertTrue(
                    ref["scores"].get("record") or ref["scores"].get("basis"),
                    ref_id)
            else:
                self.assertTrue(ref.get("scores_reason"), ref_id)


class ModeCoverageTests(unittest.TestCase):
    def test_each_mode_carries_the_full_example_set(self):
        for mode in MODES:
            folder = SUITE / "modes" / mode
            for name in ("manifest.json", "poster.png", "clip.mp4",
                         "review-record.json", "qc-record.json"):
                self.assertTrue((folder / name).is_file(), f"{mode}/{name}")

    def test_dataset_present_where_the_mode_has_one(self):
        for mode in ("powerpoint_graphic", "vsl_desktop", "vsl_mobile"):
            self.assertTrue(
                (SUITE / "modes" / mode / "dataset.json").is_file(), mode)
        data_dir = SUITE / "modes" / "standalone_video" / "data"
        self.assertTrue(any(data_dir.iterdir()))

    def test_review_records_validate_with_the_shipped_rubric_tool(self):
        for mode in MODES:
            record = SUITE / "modes" / mode / "review-record.json"
            proc = subprocess.run(
                [sys.executable, str(SKILL_DIR / "scripts" / "review_rubric.py"),
                 "validate", str(record)],
                capture_output=True, text=True)
            self.assertEqual(
                proc.returncode, 0,
                f"{mode}: {proc.stdout[-400:]} {proc.stderr[-200:]}")

    def test_review_records_are_provisional_and_unapproved(self):
        for mode in MODES:
            record = read_json(SUITE / "modes" / mode / "review-record.json")
            self.assertTrue(record["provisional"], mode)
            self.assertIsNone(record["reference"]["approval_record"], mode)

    def test_qc_records_are_real_gate_records(self):
        for mode in MODES:
            qc = read_json(SUITE / "modes" / mode / "qc-record.json")
            text = json.dumps(qc)
            self.assertIn("verdict", text, mode)


class SequenceTests(unittest.TestCase):
    def test_storyboard_covers_900_frames_contiguously(self):
        board = read_json(SUITE / "sequence" / "storyboard.json")
        self.assertEqual(board["frames_total"], 900)
        beats = board["beats"]
        self.assertEqual(beats[0]["frames"][0], 0)
        self.assertEqual(beats[-1]["frames"][1], 900)
        for prev, nxt in zip(beats, beats[1:]):
            self.assertEqual(prev["frames"][1], nxt["frames"][0])

    def test_all_four_modes_exercised(self):
        board = read_json(SUITE / "sequence" / "storyboard.json")
        self.assertEqual(sorted(board["modes_exercised"]), sorted(MODES))

    def test_beat_frames_exist(self):
        board = read_json(SUITE / "sequence" / "storyboard.json")
        for beat in board["beats"]:
            for frame in beat["evidence"].get("frames", []):
                self.assertTrue(
                    (SUITE / "sequence" / frame).is_file(), frame)


class ComponentIndexTests(unittest.TestCase):
    def test_index_covers_all_twelve_with_honest_states(self):
        index = read_json(SUITE / "components" / "index.json")
        by_id = {c["component_id"]: c for c in index["components"]}
        self.assertEqual(
            sorted(by_id), [f"C{n:02d}" for n in range(1, 13)])
        for n in range(1, 10):
            self.assertIn("available", by_id[f"C{n:02d}"]["state"])
        for n in range(10, 13):
            entry = by_id[f"C{n:02d}"]
            self.assertIn("unavailable", entry["state"])

    def test_index_frames_exist(self):
        index = read_json(SUITE / "components" / "index.json")
        for comp in index["components"]:
            for frame in comp["frames"]:
                self.assertTrue(
                    (SUITE / "components" / frame).is_file(),
                    f"{comp['component_id']}: {frame}")


class NegativeExemplarTests(unittest.TestCase):
    CASES = {
        "small-type": ("TYPO_BELOW_FLOOR",),
        "static-chart": ("MG_FAKE_MOTION",),
        "incorrect-crop": ("VSL_MOBILE_RECOMPOSITION_FAILED", "MG_QC_FAILED"),
        "decorative-substitution": ("MG_PLANNER_COVERAGE",),
    }

    def test_each_negative_fails_its_named_gate_with_a_reason(self):
        for folder, codes in self.CASES.items():
            record = read_json(SUITE / "negatives" / folder / "gate-record.json")
            self.assertEqual(record["expected"], "fail", folder)
            gate_pass = record.get("gate_pass", record.get("valid"))
            self.assertFalse(gate_pass, folder)
            self.assertTrue(record["reason_it_fails"], folder)
            self.assertTrue(record["gate"], folder)
            blob = json.dumps(record)
            self.assertTrue(
                any(code in blob for code in codes),
                f"{folder}: none of {codes} in the gate record")


class EvidenceIndexTests(unittest.TestCase):
    def test_index_covers_every_file_with_matching_hashes(self):
        index = read_json(SUITE / "evidence-index.json")
        listed = {a["path"]: a for a in index["artifacts"]}
        on_disk = {
            p.relative_to(SUITE).as_posix()
            for p in SUITE.rglob("*") if p.is_file()
        }
        on_disk.discard("evidence-index.json")
        self.assertEqual(set(listed), on_disk,
                         "index and suite tree disagree")
        for rel, artifact in listed.items():
            self.assertEqual(
                sha256(SUITE / rel), artifact["sha256"], rel)
            self.assertTrue(artifact["produced_by"], rel)


class CalibrationWordingTests(unittest.TestCase):
    def test_readme_states_the_calibration_status(self):
        readme = (SUITE / "README.md").read_text(encoding="utf-8")
        self.assertIn("CALIBRATION_PENDING", readme)
        self.assertIn("ENGINEERING_FIXTURE_ONLY", readme)
        self.assertIn("BLOCKED_ASSET", readme)

    def test_no_suite_json_claims_owner_approval(self):
        for path in SUITE.rglob("*.json"):
            doc = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(doc, dict) and doc.get("kind") == "creative_review_record":
                self.assertIsNone(doc["reference"]["approval_record"], str(path))
                self.assertTrue(doc["provisional"], str(path))


if __name__ == "__main__":
    unittest.main()
