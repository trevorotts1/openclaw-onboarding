"""Tests for the MG-010 style-frame design gate.

The gate (scripts/check_style_frames.py) proves, for one job directory,
that style frames exist for the representative scenes before animation
artifacts in the record sequence, that a design approval names the
exact current frame hashes, and that any design or frame change after
approval stales the approval and blocks promotion.

Pass fixtures live under tests/fixtures/style-frames/. Every negative
case mutates a temporary copy; the committed fixtures are never edited.
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

import check_style_frames  # noqa: E402

PASS_CHART = SKILL_ROOT / "tests" / "fixtures" / "style-frames" / "pass-chart"
PASS_IMAGE = SKILL_ROOT / "tests" / "fixtures" / "style-frames" / "pass-image-led"


def copy_job(source: Path) -> Path:
    target = Path(tempfile.mkdtemp(prefix="mg010-job-")) / source.name
    shutil.copytree(source, target)
    return target


def categories(report: dict) -> list[str]:
    return [finding["category"] for finding in report["findings"]]


class StyleFrameGatePassTests(unittest.TestCase):
    def test_chart_fixture_passes(self) -> None:
        report = check_style_frames.check_job(PASS_CHART)
        self.assertEqual(report["exit_code"], 0, report["findings"])
        self.assertEqual(report["verdict"], "pass")
        self.assertTrue(report["diagnostic"])
        self.assertEqual(report["authority_basis"], "fixture_test_issuer")
        self.assertEqual(report["scenes"][0]["approval"], "current")
        for frame in report["scenes"][0]["frames"].values():
            self.assertTrue(frame["sha256_ok"])

    def test_image_led_fixture_passes(self) -> None:
        report = check_style_frames.check_job(PASS_IMAGE)
        self.assertEqual(report["exit_code"], 0, report["findings"])
        self.assertEqual(report["verdict"], "pass")
        self.assertTrue(report["diagnostic"])
        self.assertEqual(report["scenes"][0]["scene_id"], "hero-01")

    def test_cli_pass_fixture_exits_zero_with_json_report(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SKILL_ROOT / "scripts" / "check_style_frames.py"), "check", str(PASS_CHART)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["verdict"], "pass")
        self.assertEqual(report["job_id"], "fixture-style-chart")


class StyleFrameGateBlockTests(unittest.TestCase):
    def test_missing_frame_file_blocks_as_input_missing(self) -> None:
        job = copy_job(PASS_CHART)
        (job / "style-frames" / "bar-01-final.png").unlink()
        report = check_style_frames.check_job(job)
        self.assertEqual(report["exit_code"], 3)
        self.assertIn("MG_INPUT_MISSING", categories(report))
        self.assertTrue(
            any("bar-01-final.png" in finding["path"] for finding in report["findings"]),
            report["findings"],
        )

    def test_missing_approvals_block_as_approval_required(self) -> None:
        job = copy_job(PASS_CHART)
        (job / "approvals.json").unlink()
        report = check_style_frames.check_job(job)
        self.assertEqual(report["exit_code"], 4)
        self.assertEqual(report["first_error_category"], "MG_APPROVAL_REQUIRED")

    def test_frame_edited_after_approval_is_stale(self) -> None:
        # Mutation proof: the unmutated copy passes first.
        job = copy_job(PASS_CHART)
        clean = check_style_frames.check_job(job)
        self.assertEqual(clean["exit_code"], 0, clean["findings"])
        frame_path = job / "style-frames" / "bar-01-key_proof.png"
        with frame_path.open("ab") as handle:
            handle.write(b"\x00")
        report = check_style_frames.check_job(job)
        self.assertEqual(report["exit_code"], 4)
        self.assertIn("MG_APPROVAL_STALE", categories(report))
        self.assertTrue(
            any("bar-01-key_proof.png" in finding["path"] for finding in report["findings"]),
            report["findings"],
        )

    def test_design_change_after_approval_is_stale(self) -> None:
        job = copy_job(PASS_CHART)
        design_path = job / "design.json"
        design = json.loads(design_path.read_text(encoding="utf-8"))
        design["colors"]["accent"] = "#C04A27"
        design_path.write_text(json.dumps(design, indent=2) + "\n", encoding="utf-8")
        report = check_style_frames.check_job(job)
        self.assertEqual(report["exit_code"], 4)
        self.assertIn("MG_APPROVAL_STALE", categories(report))

    def test_animation_before_style_frames_blocks(self) -> None:
        job = copy_job(PASS_CHART)
        record_path = job / "style-frames.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["animation_artifacts"][0]["sequence"] = 2
        record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        report = check_style_frames.check_job(job)
        self.assertEqual(report["exit_code"], 2)
        self.assertIn("MG_SCHEMA_INVALID", categories(report))
        self.assertTrue(
            any("does not come after" in finding["message"] for finding in report["findings"]),
            report["findings"],
        )

    def test_production_context_rejects_fixture_test_issuer(self) -> None:
        job = copy_job(PASS_CHART)
        manifest_path = job / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["execution_context"] = "production"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        report = check_style_frames.check_job(job)
        self.assertEqual(report["exit_code"], 4)
        self.assertIn("MG_APPROVAL_AUTHORITY_UNAVAILABLE", categories(report))
        self.assertFalse(report["diagnostic"])


if __name__ == "__main__":
    unittest.main()
