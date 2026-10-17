"""Asset preparation tests for Skill 72 (MG-011).

Covers the preparation layer in scripts/prepare_assets.py against the
committed fixtures under tests/fixtures/assets plus targeted mutations
in temporary copies:

- a fully provenanced valid set prepares to INPUTS_READY (exit 0);
- a changed image fails integrity (MG_HASH_MISMATCH, exit 9) and
  invalidates exactly the scenes that use it, while independent assets
  still verify;
- a missing required asset is a targeted blocker (MG_INPUT_MISSING,
  exit 3) naming the asset and its waiting scenes, while a missing
  optional asset is a warning only;
- an unapproved derivative fails (MG_APPROVAL_REQUIRED, exit 4);
- a reference_only asset embedded by a scene fails
  (MG_SCHEMA_INVALID, exit 2);
- a redrawn supplied logo fails the hash check on the embed_original
  path, so it is never silently accepted;
- assets.json shape errors and sidecar lies about media type or
  dimensions are contract failures (exit 2);
- a scene referencing an undeclared asset is a resolution blocker
  (exit 3).

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

import prepare_assets  # noqa: E402

FIXTURES = SKILL_ROOT / "tests" / "fixtures" / "assets"
SCRIPT = SKILL_ROOT / "scripts" / "prepare_assets.py"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, doc) -> None:
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def _asset(report: dict, asset_id: str) -> dict:
    for entry in report["assets"]:
        if entry["id"] == asset_id:
            return entry
    raise AssertionError(f"asset {asset_id} missing from report")


def _categories(report: dict) -> list[str]:
    return [f["category"] for f in report["findings"]]


class ValidSetTests(unittest.TestCase):
    def test_valid_set_is_ready(self):
        report = prepare_assets.prepare_job(FIXTURES / "valid-set")
        self.assertTrue(report["ready"])
        self.assertEqual("INPUTS_READY", report["state"])
        self.assertEqual(0, report["exit_code"])
        self.assertIsNone(report["first_error_category"])
        self.assertEqual([], report["findings"])
        self.assertEqual([], report["blockers"])
        self.assertEqual([], report["invalidated_scenes"])

    def test_valid_set_measures_real_dimensions_and_media(self):
        report = prepare_assets.prepare_job(FIXTURES / "valid-set")
        hero = _asset(report, "hero-image")
        self.assertEqual("verified", hero["status"])
        self.assertEqual({"width": 800, "height": 600}, hero["dimensions"])
        self.assertEqual("image/png", hero["media_type_detected"])
        chart = _asset(report, "data-chart")
        self.assertEqual({"width": 1024, "height": 768}, chart["dimensions"])
        self.assertEqual("image/jpeg", chart["media_type_detected"])
        mood = _asset(report, "mood-reference")
        self.assertEqual({"width": 1200, "height": 800}, mood["dimensions"])
        self.assertEqual("image/svg+xml", mood["media_type_detected"])

    def test_valid_set_usage_semantics(self):
        report = prepare_assets.prepare_job(FIXTURES / "valid-set")
        mood = _asset(report, "mood-reference")
        self.assertFalse(mood["embeddable"], "reference_only assets are never embeddable")
        self.assertFalse(mood["required"], "unreferenced reference asset is not required")
        derivative = _asset(report, "poster-derivative")
        self.assertEqual("verified_derivative", derivative["status"])
        self.assertTrue(derivative["embeddable"])
        for entry in report["assets"]:
            self.assertEqual([], entry["provenance_gaps"], f"{entry['id']} provenance is complete")

    def test_valid_set_font_requirements_are_deferred_not_invented(self):
        report = prepare_assets.prepare_job(FIXTURES / "valid-set")
        self.assertEqual(1, len(report["font_requirements"]))
        self.assertEqual(
            "deferred_to_runtime_registry", report["font_requirements"][0]["status"]
        )


class IntegrityTests(unittest.TestCase):
    def test_changed_image_fails_integrity_and_invalidates_only_its_scenes(self):
        report = prepare_assets.prepare_job(FIXTURES / "changed-image")
        self.assertFalse(report["ready"])
        self.assertEqual(9, report["exit_code"])
        self.assertEqual("MG_HASH_MISMATCH", report["first_error_category"])
        self.assertEqual(["scene-01"], report["invalidated_scenes"])
        fine = _asset(report, "fine-photo")
        self.assertEqual("verified", fine["status"], "independent assets still verify")

    def test_redrawn_logo_is_not_silently_accepted(self):
        report = prepare_assets.prepare_job(FIXTURES / "redrawn-logo")
        self.assertEqual(9, report["exit_code"])
        self.assertEqual("MG_HASH_MISMATCH", report["first_error_category"])
        logo = _asset(report, "client-logo")
        self.assertEqual("embed_original", logo["usage"])
        self.assertEqual("hash_mismatch", logo["status"])
        self.assertNotEqual(logo["sha256_recorded"], logo["sha256_actual"])
        self.assertEqual(["scene-01"], report["invalidated_scenes"])

    def test_dynamic_byte_flip_invalidates_dependent_scene(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job"
            shutil.copytree(FIXTURES / "valid-set", job)
            before = prepare_assets.prepare_job(job)
            self.assertTrue(before["ready"])
            hero_path = job / "media" / "hero.png"
            data = bytearray(hero_path.read_bytes())
            data[-1] ^= 0xFF
            hero_path.write_bytes(bytes(data))
            after = prepare_assets.prepare_job(job)
            self.assertEqual("MG_HASH_MISMATCH", after["first_error_category"])
            self.assertEqual(["scene-01"], after["invalidated_scenes"])
            self.assertNotIn("scene-02", after["invalidated_scenes"])


class BlockerTests(unittest.TestCase):
    def test_missing_required_asset_is_a_targeted_blocker(self):
        report = prepare_assets.prepare_job(FIXTURES / "missing-required")
        self.assertFalse(report["ready"])
        self.assertEqual(3, report["exit_code"])
        self.assertEqual("MG_INPUT_MISSING", report["first_error_category"])
        self.assertEqual(1, len(report["blockers"]))
        blocker = report["blockers"][0]
        self.assertEqual("hero-image", blocker["asset_id"])
        self.assertEqual(["scene-01"], blocker["waiting_scenes"])
        chart = _asset(report, "data-chart")
        self.assertEqual("verified", chart["status"], "independent work continues")

    def test_missing_optional_asset_is_a_warning_only(self):
        report = prepare_assets.prepare_job(FIXTURES / "missing-required")
        mood = _asset(report, "mood-reference")
        self.assertEqual("missing_optional", mood["status"])
        warning_paths = [w["path"] for w in report["warnings"]]
        self.assertIn("assets.json:mood-reference", warning_paths)

    def test_unapproved_derivative_fails_with_approval_category(self):
        report = prepare_assets.prepare_job(FIXTURES / "unapproved-derivative")
        self.assertFalse(report["ready"])
        self.assertEqual(4, report["exit_code"])
        self.assertEqual("MG_APPROVAL_REQUIRED", report["first_error_category"])
        derivative = _asset(report, "poster-derivative")
        self.assertEqual("unapproved_derivative", derivative["status"])
        self.assertEqual(1, len(report["blockers"]))
        self.assertEqual(["scene-01"], report["blockers"][0]["waiting_scenes"])

    def test_reference_only_asset_embedded_by_scene_fails(self):
        report = prepare_assets.prepare_job(FIXTURES / "reference-only-misused")
        self.assertFalse(report["ready"])
        self.assertEqual(2, report["exit_code"])
        self.assertEqual("MG_SCHEMA_INVALID", report["first_error_category"])
        mood = _asset(report, "mood-reference")
        self.assertEqual("reference_only_misused", mood["status"])

    def test_scene_referencing_undeclared_asset_is_a_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job"
            shutil.copytree(FIXTURES / "valid-set", job)
            scene = _load(job / "scenes" / "scene-01.json")
            scene["asset_ids"].append("ghost-asset")
            _save(job / "scenes" / "scene-01.json", scene)
            report = prepare_assets.prepare_job(job)
            self.assertEqual(3, report["exit_code"])
            self.assertIn("MG_INPUT_MISSING", _categories(report))
            ghost = [b for b in report["blockers"] if b["asset_id"] == "ghost-asset"]
            self.assertEqual(1, len(ghost))
            self.assertEqual(["scene-01"], ghost[0]["waiting_scenes"])


class ContractTests(unittest.TestCase):
    def test_unknown_asset_key_is_schema_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job"
            shutil.copytree(FIXTURES / "valid-set", job)
            doc = _load(job / "assets.json")
            doc["assets"][0]["surprise_key"] = True
            _save(job / "assets.json", doc)
            report = prepare_assets.prepare_job(job)
            self.assertEqual(2, report["exit_code"])
            self.assertEqual("MG_SCHEMA_INVALID", report["first_error_category"])

    def test_sidecar_media_type_lie_is_a_contract_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job"
            shutil.copytree(FIXTURES / "valid-set", job)
            sidecar = _load(job / "asset-provenance.json")
            sidecar["assets"]["hero-image"]["media_type"] = "image/gif"
            _save(job / "asset-provenance.json", sidecar)
            report = prepare_assets.prepare_job(job)
            self.assertEqual(2, report["exit_code"])
            self.assertIn("MG_SCHEMA_INVALID", _categories(report))

    def test_sidecar_dimension_lie_is_a_contract_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job"
            shutil.copytree(FIXTURES / "valid-set", job)
            sidecar = _load(job / "asset-provenance.json")
            sidecar["assets"]["data-chart"]["dimensions"] = {"width": 640, "height": 480}
            _save(job / "asset-provenance.json", sidecar)
            report = prepare_assets.prepare_job(job)
            self.assertEqual(2, report["exit_code"])
            self.assertIn("MG_SCHEMA_INVALID", _categories(report))

    def test_kind_mismatch_is_a_contract_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            job = Path(tmp) / "job"
            shutil.copytree(FIXTURES / "valid-set", job)
            doc = _load(job / "assets.json")
            for entry in doc["assets"]:
                if entry["id"] == "mood-reference":
                    entry["kind"] = "image"
            _save(job / "assets.json", doc)
            report = prepare_assets.prepare_job(job)
            self.assertEqual(2, report["exit_code"])
            mood = _asset(report, "mood-reference")
            self.assertEqual("media_type_mismatch", mood["status"])


class CliTests(unittest.TestCase):
    def _run_cli(self, *argv: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *argv],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cli_valid_set_exit_zero_and_report_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "evidence" / "asset-preparation.json"
            report_path.parent.mkdir(parents=True)
            proc = self._run_cli(
                "prepare", str(FIXTURES / "valid-set"), "--report", str(report_path)
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            stdout_report = json.loads(proc.stdout)
            self.assertTrue(stdout_report["ready"])
            persisted = _load(report_path)
            self.assertEqual(stdout_report, persisted, "persisted report matches stdout")

    def test_cli_exit_codes_match_section_169(self):
        cases = {
            "valid-set": 0,
            "changed-image": 9,
            "missing-required": 3,
            "unapproved-derivative": 4,
            "reference-only-misused": 2,
            "redrawn-logo": 9,
        }
        for name, expected in cases.items():
            with self.subTest(fixture=name):
                proc = self._run_cli("prepare", str(FIXTURES / name))
                self.assertEqual(expected, proc.returncode, proc.stderr)
                parsed = json.loads(proc.stdout)
                self.assertEqual(expected, parsed["exit_code"])


if __name__ == "__main__":
    unittest.main()
