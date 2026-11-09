"""A declared SOP is a dependency only when its read receipt matches the file.

C5: dependencies.json carries `sop` entries; dependencies._present requires a
read receipt per declared SOP and refuses a missing, stale or mis-named one.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import dependencies  # noqa: E402


def _fixture(tmp: Path):
    sop = tmp / "sops" / "SOP-TEST.md"
    sop.parent.mkdir(parents=True)
    sop.write_text("# SOP TEST\n\nread me\n", encoding="utf-8")
    skill = tmp / "skill"
    (skill / dependencies.SOP_RECEIPT_DIR).mkdir(parents=True)
    entry = {"id": "sop-test", "kind": "sop", "ref": "sops/SOP-TEST.md",
             "required": False}
    return sop, skill, entry


def _receipt(skill: Path, digest: str = "", sop_name: str = "sops/SOP-TEST.md") -> None:
    (skill / dependencies.SOP_RECEIPT_DIR / "SOP-TEST.json").write_text(
        json.dumps({"sop": sop_name, "sha256": digest}), encoding="utf-8")


class SopReadReceiptTests(unittest.TestCase):
    def _present(self, root: Path, entry: dict, skill: Path) -> dict:
        with mock.patch.object(dependencies, "resolve_skill_dir", return_value=skill):
            return dependencies._present(entry, root)

    def test_missing_receipt_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            _sop, skill, entry = _fixture(Path(tmp))
            result = self._present(Path(tmp), entry, skill)
        self.assertEqual(result["status"], "missing", result["evidence"])
        self.assertIn("no read receipt", result["evidence"])

    def test_matching_receipt_is_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            sop, skill, entry = _fixture(Path(tmp))
            _receipt(skill, hashlib.sha256(sop.read_bytes()).hexdigest())
            result = self._present(Path(tmp), entry, skill)
        self.assertEqual(result["status"], "present", result["evidence"])
        self.assertIn("receipt=", result["evidence"])

    def test_stale_receipt_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            _sop, skill, entry = _fixture(Path(tmp))
            _receipt(skill, "0" * 64)
            result = self._present(Path(tmp), entry, skill)
        self.assertEqual(result["status"], "missing", result["evidence"])
        self.assertIn("is stale", result["evidence"])

    def test_receipt_naming_another_sop_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            sop, skill, entry = _fixture(Path(tmp))
            _receipt(skill, hashlib.sha256(sop.read_bytes()).hexdigest(),
                     sop_name="sops/SOP-OTHER.md")
            result = self._present(Path(tmp), entry, skill)
        self.assertEqual(result["status"], "missing", result["evidence"])
        self.assertIn("names", result["evidence"])

    def test_every_declared_sop_in_the_real_manifest_is_present(self):
        entries = [e for e in dependencies.load_manifest()["entries"]
                   if e.get("kind") == "sop"]
        self.assertTrue(entries, "the manifest declares no sop entry")
        for entry in entries:
            result = dependencies._present(entry, dependencies._repo_root())
            self.assertEqual(result["status"], "present",
                             f'{entry["id"]}: {result["evidence"]}')


if __name__ == "__main__":
    unittest.main()
