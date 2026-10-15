"""Shared-corpus tests for the V2 contract validation layer (MG-007).

Valid corpus: the four extracted mode fixtures under tests/fixtures/modes
must produce zero findings. Invalid corpus: targeted mutations of the
fixtures must produce the same stable first error category the TypeScript
layer returns (directive Section 16.6 rule 12, Section 16.9 categories).

Run from the skill root:
    python3 -m unittest discover -s tests/unit
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import motion_contracts  # noqa: E402

FIXTURE_MODES = SKILL_ROOT / "tests" / "fixtures" / "modes"
ALL_MODES = ("powerpoint_graphic", "vsl_desktop", "vsl_mobile", "standalone_video")


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, doc) -> None:
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


class ValidCorpusTests(unittest.TestCase):
    def test_all_four_mode_fixtures_are_valid(self):
        for mode in ALL_MODES:
            with self.subTest(mode=mode):
                findings = motion_contracts.validate_job(FIXTURE_MODES / mode)
                self.assertEqual([], findings, f"{mode} must produce zero findings")


class InvalidCorpusTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def copy_mode(self, mode: str) -> Path:
        target = self.tmp / mode
        shutil.copytree(FIXTURE_MODES / mode, target)
        return target

    def first_category(self, job_dir: Path):
        findings = motion_contracts.validate_job(job_dir)
        self.assertTrue(findings, "mutation must produce at least one finding")
        return motion_contracts.first_error_category(findings)

    def test_unknown_manifest_key_is_schema_invalid(self):
        job = self.copy_mode("powerpoint_graphic")
        manifest = _load(job / "manifest.json")
        manifest["surprise_key"] = True
        _save(job / "manifest.json", manifest)
        self.assertEqual("MG_SCHEMA_INVALID", self.first_category(job))

    def test_broken_ratio_canvas_is_mode_mismatch(self):
        job = self.copy_mode("powerpoint_graphic")
        manifest = _load(job / "manifest.json")
        manifest["canvas"]["width"] = 1919
        manifest["canvas"]["height"] = 1080
        _save(job / "manifest.json", manifest)
        self.assertEqual("MG_MODE_MISMATCH", self.first_category(job))

    def test_zero_width_is_schema_invalid(self):
        job = self.copy_mode("powerpoint_graphic")
        manifest = _load(job / "manifest.json")
        manifest["canvas"]["width"] = 0
        _save(job / "manifest.json", manifest)
        self.assertEqual("MG_SCHEMA_INVALID", self.first_category(job))

    def test_duplicate_scene_id_is_schema_invalid(self):
        job = self.copy_mode("powerpoint_graphic")
        manifest = _load(job / "manifest.json")
        manifest["scenes"].append(dict(manifest["scenes"][0]))
        _save(job / "manifest.json", manifest)
        self.assertEqual("MG_SCHEMA_INVALID", self.first_category(job))

    def test_timeline_total_mismatch_is_timeline_invalid(self):
        job = self.copy_mode("powerpoint_graphic")
        timeline = _load(job / "timeline.json")
        timeline["total_frames"] = 181
        _save(job / "timeline.json", timeline)
        self.assertEqual("MG_TIMELINE_INVALID", self.first_category(job))

    def test_empty_motion_interval_is_timeline_invalid(self):
        job = self.copy_mode("powerpoint_graphic")
        scene = _load(job / "scenes" / "bar-01.json")
        scene["motion"]["end_frame_exclusive"] = scene["motion"]["start_frame"]
        _save(job / "scenes" / "bar-01.json", scene)
        self.assertEqual("MG_TIMELINE_INVALID", self.first_category(job))

    def test_unknown_component_is_unknown_component(self):
        job = self.copy_mode("powerpoint_graphic")
        scene = _load(job / "scenes" / "bar-01.json")
        scene["component_id"] = "C99"
        _save(job / "scenes" / "bar-01.json", scene)
        self.assertEqual("MG_UNKNOWN_COMPONENT", self.first_category(job))

    def test_reversed_dataset_domain_is_schema_invalid(self):
        job = self.copy_mode("powerpoint_graphic")
        dataset = _load(job / "data" / "bars.json")
        dataset["domain"] = [30, 0]
        _save(job / "data" / "bars.json", dataset)
        self.assertEqual("MG_SCHEMA_INVALID", self.first_category(job))

    def test_mobile_canvas_swapped_to_landscape_is_mode_mismatch(self):
        job = self.copy_mode("vsl_mobile")
        manifest = _load(job / "manifest.json")
        manifest["canvas"]["width"] = 1920
        manifest["canvas"]["height"] = 1080
        _save(job / "manifest.json", manifest)
        self.assertEqual("MG_MODE_MISMATCH", self.first_category(job))

    def test_vsl_audio_mode_none_is_mode_mismatch(self):
        # Parity case 11 (integration, 2026-10-13): the canonical schema
        # pins VSL audio.mode to "inherited"; the TypeScript layer reports
        # MG_MODE_MISMATCH for this mutation, so the Python layer must too
        # (Section 16.6 rule 12).
        job = self.copy_mode("vsl_desktop")
        manifest = _load(job / "manifest.json")
        manifest["audio"]["mode"] = "none"
        manifest["audio"]["parent_audio_ref"] = None
        _save(job / "manifest.json", manifest)
        self.assertEqual("MG_MODE_MISMATCH", self.first_category(job))

    def test_desktop_vsl_without_parent_is_mode_mismatch(self):
        job = self.copy_mode("vsl_desktop")
        manifest = _load(job / "manifest.json")
        manifest["parent"] = None
        _save(job / "manifest.json", manifest)
        (job / "parent-handoff.json").unlink()
        self.assertEqual("MG_MODE_MISMATCH", self.first_category(job))


if __name__ == "__main__":
    unittest.main()
