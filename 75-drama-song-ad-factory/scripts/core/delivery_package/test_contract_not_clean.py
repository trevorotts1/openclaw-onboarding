#!/usr/bin/env python3
"""DEL-13 clean-folder gate: the client folder holds deliverables only.

Proves the two halves of the review's L1/L5 fix together:
  * verify_folder lists the folder and fails DELIVERY_FOLDER_NOT_CLEAN for
    any top-level name outside the 12 contract items plus the known extras
    (delivery-receipt.json, README.md, SONG-CHOICES/, the song mp3/wav pair);
  * a lip-sync mouth strip (QC evidence, never a deliverable) lands under
    <run>/qc/mouth-strips/, so it can no longer make the delivery folder
    dirty in the first place.

stdlib only, no network, no provider call. Run:
python3 delivery_package/test_contract_not_clean.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CORE = _HERE.parents[0]                       # .../scripts/core
for _p in (_CORE, _CORE / "lip_sync" / "lip_gate"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import delivery_package.contract as C           # noqa: E402
import lip_process as LP                        # noqa: E402


class CleanFolder(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="del13-clean-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def folder(self, name="delivery"):
        return C.write_reference_package(self.tmp / name)

    def test_a_clean_twelve_item_folder_passes(self):
        report = C.verify_folder(self.folder())
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["not_clean"], [])
        self.assertEqual(report["missing"], [])

    def test_a_stray_cost_report_fails_not_clean(self):
        folder = self.folder()
        (folder / "cost-report.json").write_text("{}", encoding="utf-8")
        report = C.verify_folder(folder)
        self.assertFalse(report["ok"])
        self.assertEqual(report["not_clean"], ["cost-report.json"])
        self.assertEqual(report["missing"], [],
                         "the 12 items are all there: this is a cleanliness "
                         "failure, not a missing-item failure")
        problem = [p for p in report["problems"]
                   if p["file"] == "cost-report.json"][0]
        self.assertIn(C.DELIVERY_FOLDER_NOT_CLEAN, problem["problem"])

    def test_a_stray_directory_fails_too(self):
        folder = self.folder()
        (folder / "working").mkdir()
        (folder / "working" / "scratch.mp4").write_bytes(b"x")
        report = C.verify_folder(folder)
        self.assertFalse(report["ok"])
        self.assertEqual(report["not_clean"], ["working"])
        problem = [p for p in report["problems"] if p["file"] == "working"][0]
        self.assertIn(C.DELIVERY_FOLDER_NOT_CLEAN, problem["problem"])
        self.assertIn("directory", problem["problem"])

    def test_old_mouth_strip_folder_is_refused(self):
        # the leak this gate exists for: QC strips in the client folder
        folder = self.folder()
        strips = folder / "mouth-strips"
        strips.mkdir()
        (strips / "seg1.png").write_bytes(b"\x89PNG\r\n\x1a\nstrip")
        report = C.verify_folder(folder)
        self.assertFalse(report["ok"])
        self.assertEqual(report["not_clean"], ["mouth-strips"])

    def test_every_allowed_extra_is_accepted(self):
        folder = self.folder("with-extras")
        (folder / "delivery-receipt.json").write_text("{}", encoding="utf-8")
        (folder / "README.md").write_text("# yours\n", encoding="utf-8")
        (folder / "SONG-CHOICES").mkdir()
        (folder / "SONG-CHOICES" / "README.txt").write_text("x",
                                                            encoding="utf-8")
        (folder / "Jane Doe - Midnight Call - Song.mp3").write_bytes(b"m")
        (folder / "Jane Doe - Midnight Call - Song.wav").write_bytes(b"w")
        report = C.verify_folder(folder)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["not_clean"], [])

    def test_the_song_pair_must_carry_both_names(self):
        # '<Author> - <Title> - Song.mp3' is the pattern; a bare extra mp3 is not
        folder = self.folder("song-pattern")
        (folder / "just-a-song.mp3").write_bytes(b"m")
        report = C.verify_folder(folder)
        self.assertFalse(report["ok"])
        self.assertEqual(report["not_clean"], ["just-a-song.mp3"])


class MouthStripsGoToQc(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="del13-strip-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_strip_lands_under_qc_not_delivery(self):
        run = self.tmp / "run"
        run.mkdir()
        out = LP.strip_path(str(run), "Perm_5-v2")
        self.assertEqual(out, str(run / "qc" / "mouth-strips" /
                                  "Perm_5-v2.png"))
        self.assertNotIn("delivery", out)

    def test_a_delivery_folder_caller_is_derived_to_its_run(self):
        run = self.tmp / "run"
        (run / "delivery").mkdir(parents=True)
        out = LP.strip_path(str(run / "delivery"), "seg1")
        self.assertEqual(out, str(run / "qc" / "mouth-strips" / "seg1.png"))

    def test_the_strip_keeps_the_delivery_folder_clean(self):
        # the two fixes together: a strip written where strip_path says, then
        # the delivery folder still verifies clean.
        run = self.tmp / "run"
        (run / "delivery").mkdir(parents=True)
        folder = C.write_reference_package(run / "delivery")
        out = Path(LP.strip_path(str(run), "seg1"))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"\x89PNG\r\n\x1a\nstrip")
        report = C.verify_folder(folder)
        self.assertTrue(report["ok"], report)


if __name__ == "__main__":
    unittest.main(verbosity=2)
