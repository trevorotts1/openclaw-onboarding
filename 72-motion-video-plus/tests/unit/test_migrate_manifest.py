"""Tests for the non-destructive V1 to V2 manifest migrator (MG-007).

Run from the skill root:
    python3 -m unittest discover -s tests/unit
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

SKILL_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = SKILL_ROOT / "assets" / "example-manifest.json"
MIGRATOR = SKILL_ROOT / "scripts" / "migrate_manifest.py"
SCHEMA = SKILL_ROOT / "references" / "contracts-v2.schema.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_errors(doc) -> list:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    wrapper = {
        "$schema": schema["$schema"],
        "$ref": "#/$defs/manifest",
        "$defs": schema["$defs"],
    }
    return list(Draft202012Validator(wrapper).iter_errors(doc))


class MigrateManifestTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.out_dir = Path(self._tmp.name) / "out"

    def run_migrator(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                str(MIGRATOR),
                str(EXAMPLE),
                "--out-dir",
                str(self.out_dir),
                *extra,
            ],
            capture_output=True,
            text=True,
        )

    def test_example_migrates_without_data_loss(self):
        before = _sha256(EXAMPLE)
        result = self.run_migrator("--mode", "standalone_video", "--company-id", "test-company")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(before, _sha256(EXAMPLE), "the V1 input file must never be modified")

        manifest_path = self.out_dir / "manifest.json"
        self.assertTrue(manifest_path.is_file())
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual([], _manifest_errors(manifest), "migrated manifest must pass the full manifest definition")
        self.assertEqual("standalone_video", manifest["mode"])
        self.assertEqual("test-company", manifest["company_id"])
        self.assertEqual(6, len(manifest["scenes"]))
        self.assertEqual(900, manifest["duration_frames"])

        receipt = json.loads((self.out_dir / "migration-receipt.json").read_text(encoding="utf-8"))
        self.assertEqual("migrated", receipt["status"])
        self.assertEqual(before, receipt["source_sha256"])

        v1 = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        accounted = set(receipt["mapped_fields"]) | {
            entry["field"] for entry in receipt["preserved_unmapped"]
        }
        self.assertEqual(set(v1), accounted & set(v1))
        self.assertTrue(
            set(v1) <= accounted,
            f"every V1 top-level key must be accounted for; missing: {set(v1) - accounted}",
        )
        self.assertTrue(receipt["inferred_fields"], "inferred values must be marked explicitly")
        self.assertTrue(
            any("duration_frames" in entry for entry in receipt["inferred_fields"]),
            "the duration_frames derivation must be listed as inferred",
        )

        legacy_files = sorted((self.out_dir / "scenes").glob("*.legacy.json"))
        self.assertEqual(6, len(legacy_files))
        v1_scenes = {scene["id"]: scene for scene in v1["scenes"]}
        for legacy_path in legacy_files:
            legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
            self.assertEqual("1.0", legacy["legacy_schema_version"])
            original = v1_scenes[legacy["id"]]
            for key, value in original.items():
                self.assertEqual(value, legacy[key], f"V1 scene field {key} must be preserved verbatim")

    def test_missing_company_id_is_needs_input(self):
        result = self.run_migrator("--mode", "standalone_video")
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertFalse((self.out_dir / "manifest.json").exists(), "needs_input must not write a manifest")
        receipt = json.loads((self.out_dir / "migration-receipt.json").read_text(encoding="utf-8"))
        self.assertEqual("needs_input", receipt["status"])
        self.assertTrue(receipt["missing_inputs"])

    def test_vsl_mode_is_needs_input_because_parent_is_never_invented(self):
        result = self.run_migrator("--mode", "vsl_desktop", "--company-id", "test-company")
        self.assertEqual(2, result.returncode, result.stdout + result.stderr)
        self.assertFalse((self.out_dir / "manifest.json").exists())
        receipt = json.loads((self.out_dir / "migration-receipt.json").read_text(encoding="utf-8"))
        self.assertEqual("needs_input", receipt["status"])
        self.assertTrue(any("parent" in entry for entry in receipt["missing_inputs"]))


if __name__ == "__main__":
    unittest.main()
