#!/usr/bin/env python3
"""W1-method-qc-U3: the delivery folder holds deliverables only (SPEC B3b).

Trevor's standing rule, client-folder review 2026-10-13: the folder a client
gets holds deliverables and nothing else. This proves the three parts the
method adds to ``contract.verify_folder``:

  * a clean 12-item folder still passes, and the contract still carries the
    12 base items plus the OPTIONAL item 13;
  * a method run names item 6's files as trailers (slot 06) and a CAMPAIGN
    run also owes the ad clips, ``13 - Ad 60s.mp4`` / ``13 - Ad 90s.mp4`` --
    both inert until the caller says the run carries them, so an ordinary run
    behaves exactly as it did before;
  * every working file (mouth strips, Agnes prompts, chained last frames, the
    kit JSON beside its PDF, a venv) is refused by name with
    DELIVERY_FOLDER_NOT_CLEAN -- in an ordinary run and in a method/campaign
    run alike, because those files live in the run's work/, qc/, control/ and
    receipts/ homes, never in the client folder.

stdlib only, no network, no provider call, no client name. Run:
python3 delivery_package/test_deliverables_only.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CORE = _HERE.parents[0]                       # .../scripts/core
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

import delivery_package.contract as C           # noqa: E402

#: working files that belong in <run>/work/agnes, <run>/qc or <run>/control
#: (SPEC B3b) -- none of them is ever a deliverable.
STRAYS = ("mouth-strips", "prompt.txt", "last_frame.png",
          "07 - Ready-to-Post Kit.json", "venv")


def _rename(folder, old, new):
    (folder / old).rename(folder / new)


def _write_ad_clips(folder, *names):
    for name in names:
        (folder / name).write_bytes(C.MEDIA_BYTES)


class TwelveBaseItems(unittest.TestCase):
    """The 12 base items are unchanged; item 13 is the optional one."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="agn-u3-base-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_the_contract_carries_twelve_base_items_plus_optional_13(self):
        self.assertEqual(len(C.PACKAGE_ITEMS), 12)
        self.assertEqual([i.number for i in C.PACKAGE_ITEMS],
                         list(range(1, 13)))
        self.assertEqual(len(C.OPTIONAL_ITEMS), 1)
        self.assertEqual(C.AD_CLIPS_ITEM.number, 13)
        self.assertEqual(C.AD_CLIPS_ITEM.key, "ad_clips")
        self.assertEqual(C.AD_CLIPS_ITEM.files,
                         ("13 - Ad 60s.mp4", "13 - Ad 90s.mp4"))
        self.assertEqual(C.AD_CLIPS_ITEM.kinds, ("media", "media"))
        for item in C.PACKAGE_ITEMS + C.OPTIONAL_ITEMS:
            self.assertRegex(item.unit, r"^DEL-\d{2}$")
            self.assertEqual(len(item.files), len(item.kinds), item.key)
            prefix = "%02d - " % item.number
            for name in item.files:
                self.assertTrue(name.startswith(prefix),
                                "%s: %s lacks %s" % (item.key, name, prefix))

    def test_a_clean_twelve_item_folder_passes(self):
        folder = C.write_reference_package(self.tmp / "delivery")
        report = C.verify_folder(folder)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["missing"], [])
        self.assertEqual(report["not_clean"], [])
        self.assertEqual(report["expected"], 12)
        self.assertEqual(len(report["present"]), 12)

    def test_a_missing_folder_misses_only_the_base_items(self):
        report = C.verify_folder(self.tmp / "absent")
        self.assertFalse(report["ok"])
        self.assertEqual(len(report["missing"]), 12)
        self.assertNotIn("ad_clips", report["missing"])


class MethodRunTrailers(unittest.TestCase):
    """Item 6 on a method run: ``06 - Trailer 60s/90s.mp4``, same slot."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="agn-u3-method-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def method_folder(self, name="delivery"):
        folder = C.write_reference_package(self.tmp / name)
        _rename(folder, "06 - Clip 60s.mp4", "06 - Trailer 60s.mp4")
        _rename(folder, "06 - Clip 90s.mp4", "06 - Trailer 90s.mp4")
        return folder

    def test_a_method_run_ships_trailers_in_slot_06(self):
        report = C.verify_folder(self.method_folder(), method_run=True)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["missing"], [])
        self.assertEqual(report["not_clean"], [])
        self.assertEqual(report["expected"], 12)
        self.assertIn("clips", report["present"])

    def test_a_method_run_still_accepts_the_clip_names(self):
        folder = C.write_reference_package(self.tmp / "clips")
        report = C.verify_folder(folder, method_run=True)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["missing"], [])

    def test_a_method_run_missing_both_60s_names_is_named(self):
        folder = C.write_reference_package(self.tmp / "no60")
        _rename(folder, "06 - Clip 60s.mp4", "06 - Trailer 60s.mp4")
        _rename(folder, "06 - Clip 90s.mp4", "06 - Trailer 90s.mp4")
        (folder / "06 - Trailer 60s.mp4").unlink()
        report = C.verify_folder(folder, method_run=True)
        self.assertFalse(report["ok"])
        self.assertEqual(report["missing"], ["clips"])
        problem = [p for p in report["problems"]
                   if p["item"] == "clips"][0]
        self.assertEqual(problem["file"], "06 - Trailer 60s.mp4")
        self.assertEqual(problem["problem"], "missing")

    def test_a_trailer_name_is_inert_outside_a_method_run(self):
        # no method.json, no wiring: the trailer name is a stray and item 6
        # still owes the clip names -- byte for byte the old gate.
        folder = self.method_folder("inert")
        report = C.verify_folder(folder)
        self.assertFalse(report["ok"])
        self.assertEqual(report["missing"], ["clips"])
        self.assertEqual(sorted(report["not_clean"]),
                         ["06 - Trailer 60s.mp4", "06 - Trailer 90s.mp4"])
        for name in ("06 - Trailer 60s.mp4", "06 - Trailer 90s.mp4"):
            problem = [p for p in report["problems"]
                       if p["file"] == name][0]
            self.assertIn(C.DELIVERY_FOLDER_NOT_CLEAN, problem["problem"])

    def test_the_allow_list_grows_only_for_the_run_that_earned_it(self):
        base = C.allowed_top_level()
        self.assertNotIn("06 - Trailer 60s.mp4", base)
        self.assertNotIn("13 - Ad 60s.mp4", base)
        method = C.allowed_top_level(method_run=True)
        self.assertIn("06 - Trailer 60s.mp4", method)
        self.assertIn("06 - Trailer 90s.mp4", method)
        self.assertNotIn("13 - Ad 60s.mp4", method)
        campaign = C.allowed_top_level(method_run=True, campaign_run=True)
        self.assertIn("13 - Ad 60s.mp4", campaign)
        self.assertIn("13 - Ad 90s.mp4", campaign)


class CampaignAdClips(unittest.TestCase):
    """Item 13: the ad clips ship on a campaign method run, and only there."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="agn-u3-campaign-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def campaign_folder(self, name="delivery"):
        folder = C.write_reference_package(self.tmp / name)
        _write_ad_clips(folder, "13 - Ad 60s.mp4", "13 - Ad 90s.mp4")
        return folder

    def test_a_campaign_run_ships_both_ad_clips(self):
        folder = self.campaign_folder()
        report = C.verify_folder(folder, method_run=True, campaign_run=True)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["missing"], [])
        self.assertEqual(report["not_clean"], [])
        self.assertEqual(report["expected"], 13, "12 base + optional 13")
        self.assertEqual(len(report["present"]), 13)
        self.assertIn("ad_clips", report["present"])

    def test_a_campaign_run_owes_both_ad_clips(self):
        folder = C.write_reference_package(self.tmp / "onead")
        _write_ad_clips(folder, "13 - Ad 60s.mp4")
        report = C.verify_folder(folder, method_run=True, campaign_run=True)
        self.assertFalse(report["ok"])
        self.assertEqual(report["missing"], ["ad_clips"])
        self.assertEqual(report["expected"], 13)
        problem = [p for p in report["problems"]
                   if p["item"] == "ad_clips"][0]
        self.assertEqual(problem["file"], "13 - Ad 90s.mp4")
        self.assertEqual(problem["problem"], "missing")

    def test_an_ad_clip_outside_a_campaign_run_is_a_stray(self):
        # campaign runs only (F19): elsewhere the ad clip is not on the list
        for flags in ({}, {"method_run": True}):
            folder = self.campaign_folder("stray-%d" % len(flags))
            report = C.verify_folder(folder, **flags)
            self.assertFalse(report["ok"], flags)
            self.assertIn("13 - Ad 60s.mp4", report["not_clean"])
            self.assertIn("13 - Ad 90s.mp4", report["not_clean"])
            for name in ("13 - Ad 60s.mp4", "13 - Ad 90s.mp4"):
                problem = [p for p in report["problems"]
                           if p["file"] == name][0]
                self.assertIn(C.DELIVERY_FOLDER_NOT_CLEAN,
                              problem["problem"])
                self.assertIn(name, problem["problem"])


class WorkingFilesAreNeverDeliverables(unittest.TestCase):
    """SPEC B3b: the working file has a home in the run, not in the folder."""

    #: every flag set below, with the folder shape that run owes (so the
    #: failure under test is the stray, never a missing deliverable).
    RUNS = (({}, False, False), ({"method_run": True}, True, False),
            ({"method_run": True, "campaign_run": True}, True, True))

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="agn-u3-stray-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def folder(self, name, method, campaign):
        """A complete run folder for these flags: 12 items (+ ad clips)."""
        folder = C.write_reference_package(self.tmp / name)
        if method:
            _rename(folder, "06 - Clip 60s.mp4", "06 - Trailer 60s.mp4")
            _rename(folder, "06 - Clip 90s.mp4", "06 - Trailer 90s.mp4")
        if campaign:
            _write_ad_clips(folder, "13 - Ad 60s.mp4", "13 - Ad 90s.mp4")
        return folder

    def test_every_working_file_is_refused_by_name(self):
        for i, stray in enumerate(STRAYS):
            for flags, method, campaign in self.RUNS:
                name = "s-%d-%d" % (i, len(flags))
                folder = self.folder(name, method, campaign)
                target = folder / stray
                if stray in ("mouth-strips", "venv"):
                    target.mkdir()
                    (target / "seg1.png").write_bytes(b"x")
                else:
                    target.write_text("working file\n", encoding="utf-8")
                report = C.verify_folder(folder, **flags)
                self.assertFalse(report["ok"], (stray, flags))
                self.assertIn(stray, report["not_clean"], (stray, flags))
                problem = [p for p in report["problems"]
                           if p["file"] == stray][0]
                self.assertIn(C.DELIVERY_FOLDER_NOT_CLEAN,
                              problem["problem"], stray)
                self.assertIn(stray, problem["problem"], stray)
                # every deliverable the run owes is there: this is a
                # cleanliness failure, never a missing-item failure.
                self.assertEqual(report["missing"], [], (stray, flags))

    def test_a_deliverable_alone_never_reads_as_a_stray(self):
        folder = C.write_reference_package(self.tmp / "only-deliverables")
        _rename(folder, "06 - Clip 60s.mp4", "06 - Trailer 60s.mp4")
        _rename(folder, "06 - Clip 90s.mp4", "06 - Trailer 90s.mp4")
        _write_ad_clips(folder, "13 - Ad 60s.mp4", "13 - Ad 90s.mp4")
        report = C.verify_folder(folder, method_run=True, campaign_run=True)
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["not_clean"], [])
        self.assertEqual(report["missing"], [])
        self.assertEqual(report["expected"], 13)


if __name__ == "__main__":
    unittest.main(verbosity=2)
