#!/usr/bin/env python3
"""platform_fit tests: researched specs carry their source and their clock, and
the delivered-file checker answers PASS / FLAG / UNDETERMINED / NOT_AVAILABLE.

Cases are the BUILD-PLAN Prove line for W1-method-qc-U2:

  1. every row in platform-specs.json carries the documented fields, a 30 day
     re-verify window, a status in the allowed set, a unique placement id, and
     (for the organic rows) the BlackCEO GHL publishing guide as its source;
  2. 58 s 9:16 vs the Instagram Reels ad row -> PASS;
  3. the same file vs the Facebook Stories ad row -> FLAG, split into cards;
  4. 30 fps vs the LinkedIn rows -> FLAG (the ceiling is 30, not 30 inclusive);
  5. a row 40 days past its window -> FLAG code STALE_SPEC naming its source;
  6. the UNDETERMINED Facebook Reels ad row -> FLAG "verify by hand", never PASS;
  7. GHL destinations: 75 s vertical fits Facebook Story and Facebook Reel but
     not Instagram Story or Instagram feed; 180 s fits YouTube Short and
     Instagram Reel; 120 MB at 60 s fails Instagram Story (100 MB) and passes
     Instagram Reel (1 GB); X/Twitter is NOT_AVAILABLE;
  8. the probe is one ffprobe read routed through core/load_governor, and its
     JSON is parsed into the probe dict;
  9. one real probe of trial-oct13/test-a-30s-cartoon/final_30s.mp4 when this
     machine keeps that file and ffprobe is installed.

Every date is pinned: the spec rows were read 2026-10-13, so the functional
cases judge them on 2026-10-15 and the staleness case on 2026-11-22 (40 days).

Run: python3 -m pytest -q scripts/core/platform_fit
  or python3 scripts/core/platform_fit/test_platform_fit.py
"""
from __future__ import annotations

import glob
import json
import os
import shutil
import sys
import unittest
from pathlib import Path
from unittest import mock

_HERE = Path(__file__).resolve().parent
_CORE = _HERE.parents[0]                       # .../scripts/core
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

import platform_fit.platform_fit as PF  # noqa: E402

TODAY = "2026-10-15"          # 2 days after the rows were read: inside the window
STALE_TODAY = "2026-11-22"    # 40 days after the rows were read: past 30
READ_UTC = "2026-10-13"
GHL_SOURCE = "BlackCEO GHL publishing guide 2026-10-13"

RELSAMPLE = os.path.join("trial-oct13", "test-a-30s-cartoon", "final_30s.mp4")


def probe(seconds=58.0, width=1080, height=1920, fps="30/1",
          size=20 * 1024 * 1024, container="mp4", codec="h264",
          path="/tmp/delivered.mp4"):
    """A probe dict the way probe_file() reports one."""
    return {
        "path": path, "duration_s": float(seconds), "size_bytes": int(size),
        "container": container, "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "video_codec": codec, "audio_codec": "aac",
        "width": width, "height": height, "fps": PF._frame_rate(fps),
    }


def sample_video():
    """trial-oct13/test-a-30s-cartoon/final_30s.mp4 when this machine has it."""
    env = os.environ.get("DSAF_PLATFORM_FIT_SAMPLE")
    if env and os.path.isfile(env):
        return env
    for base in [Path.cwd()] + list(Path.cwd().parents)[:4] + list(_HERE.parents)[:5]:
        p = base / RELSAMPLE
        if p.is_file():
            return str(p)
    for hit in sorted(glob.glob(os.path.join(
            os.path.expanduser("~"), "Downloads", "*", RELSAMPLE))):
        if os.path.isfile(hit):
            return hit
    return None


class SpecTable(unittest.TestCase):
    """The data file itself: fields, clock, statuses, unique ids, sources."""

    def setUp(self):
        self.rows = PF.load_specs()

    def test_every_row_carries_the_documented_fields(self):
        for row in self.rows:
            missing = [f for f in PF.ROW_FIELDS if f not in row]
            self.assertEqual(missing, [], "%s misses %s" % (row.get("placement"), missing))
            self.assertEqual(row["reverify_after_days"], 30, row["placement"])
            self.assertEqual(row["read_utc"], READ_UTC, row["placement"])
            self.assertIn(row["status"], ("VERIFIED", "SECONDARY", "UNDETERMINED"))
            self.assertIn(row["availability"], ("AVAILABLE", "NOT_AVAILABLE"))
            self.assertIn(row["kind"], ("paid_ad", "ghl"))

    def test_placement_ids_are_unique(self):
        ids = [r["placement"] for r in self.rows]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue({"instagram_reels_ad", "facebook_stories_ad",
                         "facebook_reels_ad", "linkedin_video_ad",
                         "instagram_story", "instagram_reel", "facebook_story",
                         "facebook_reel", "youtube_short", "x_twitter"} <= set(ids))

    def test_organic_rows_cite_the_ghl_guide(self):
        for row in self.rows:
            if row["kind"] == "ghl":
                self.assertEqual(row["source"], GHL_SOURCE, row["placement"])

    def test_undetermined_row_has_no_fabricated_value(self):
        row = PF.row_for("facebook_reels_ad")
        self.assertEqual(row["status"], "UNDETERMINED")
        self.assertIsNone(row["min_seconds"])
        self.assertIsNone(row["max_seconds"])


class Check(unittest.TestCase):
    """check(file_probe, placement, today) on the BUILD-PLAN cases."""

    def test_58s_916_passes_the_instagram_reels_ad_row(self):
        r = PF.check(probe(), "instagram_reels_ad", TODAY)
        self.assertEqual(r["verdict"], PF.PASS, r["reason"])
        self.assertEqual(r["code"], None)
        names = {c["name"]: c["verdict"] for c in r["checks"]}
        self.assertEqual(names.get("length"), PF.PASS)
        self.assertEqual(names.get("aspect"), PF.PASS)

    def test_58s_flags_the_facebook_stories_ad_split_rule(self):
        r = PF.check(probe(), "facebook_stories_ad", TODAY)
        self.assertEqual(r["verdict"], PF.FLAG, r["reason"])
        self.assertIn("split", r["reason"])
        names = {c["name"]: c for c in r["checks"]}
        self.assertEqual(names["full_playback"]["verdict"], PF.FLAG)
        self.assertEqual(names["length"]["verdict"], PF.PASS,
                         "58 s is inside the 1-180 s length, the flag is the card split")

    def test_30fps_flags_linkedin(self):
        for placement in ("linkedin_video_ad", "linkedin_video"):
            r = PF.check(probe(fps="30/1"), placement, TODAY)
            self.assertEqual(r["verdict"], PF.FLAG, "%s: %s" % (placement, r["reason"]))
            self.assertIn("30 fps", r["reason"])
            self.assertIn("fps", [c["name"] for c in r["checks"]
                                  if c["verdict"] == PF.FLAG])
        self.assertEqual(PF.check(probe(fps="24/1"), "linkedin_video_ad", TODAY)["verdict"],
                         PF.PASS)

    def test_a_40_day_old_row_is_stale_spec_naming_its_source(self):
        r = PF.check(probe(), "instagram_reels_ad", STALE_TODAY)
        self.assertEqual(r["verdict"], PF.FLAG)
        self.assertEqual(r["code"], PF.STALE_SPEC)
        self.assertTrue(r["stale"])
        self.assertEqual(r["days_since_read"], 40)
        self.assertIn("https://www.facebook.com/business/ads-guide/update/video/instagram-reels",
                      r["reason"])

    def test_undetermined_row_never_passes(self):
        r = PF.check(probe(), "facebook_reels_ad", TODAY)
        self.assertNotEqual(r["verdict"], PF.PASS)
        self.assertEqual(r["verdict"], PF.FLAG)
        self.assertEqual(r["code"], PF.UNDETERMINED_SPEC)
        self.assertIn("verify by hand", r["reason"])

    def test_unknown_placement_is_undetermined_not_a_pass(self):
        r = PF.check(probe(), "no_such_platform", TODAY)
        self.assertEqual(r["verdict"], PF.UNDETERMINED)
        self.assertEqual(r["code"], PF.UNKNOWN_PLACEMENT)

    def test_x_twitter_and_the_stories_rows_are_not_available(self):
        for placement in ("x_twitter", "linkedin_stories", "youtube_stories",
                          "pinterest_stories"):
            r = PF.check(probe(), placement, TODAY)
            self.assertEqual(r["verdict"], PF.NOT_AVAILABLE, placement)
        self.assertNotIn("x_twitter", PF.fits(probe()))

    def test_size_is_part_of_the_answer(self):
        big = probe(seconds=60.0, size=120 * 1024 * 1024)
        r = PF.check(big, "instagram_story", TODAY)
        self.assertEqual(r["verdict"], PF.FLAG)
        self.assertIn("100 MB", r["reason"])
        names = {c["name"]: c for c in r["checks"]}
        self.assertEqual(names["length"]["verdict"], PF.PASS)
        self.assertEqual(names["file_size"]["verdict"], PF.FLAG)

    def test_unmeasurable_probe_is_undetermined_never_a_pass(self):
        r = PF.check({"path": "x.mp4"}, "instagram_reels_ad", TODAY)
        self.assertEqual(r["verdict"], PF.UNDETERMINED)


class Fits(unittest.TestCase):
    """fits(file_probe): the GHL destinations a file provably fits."""

    def test_75s_vertical_fits_facebook_story_and_reel_only_of_the_two_stories(self):
        got = set(PF.fits(probe(seconds=75.0, size=80 * 1024 * 1024)))
        self.assertIn("facebook_story", got)
        self.assertIn("facebook_reel", got)
        self.assertNotIn("instagram_story", got)
        self.assertNotIn("instagram_feed", got)

    def test_three_minutes_fits_youtube_short_and_instagram_reel(self):
        got = set(PF.fits(probe(seconds=180.0, size=100 * 1024 * 1024)))
        self.assertIn("youtube_short", got)
        self.assertIn("instagram_reel", got)

    def test_120mb_fails_instagram_story_and_passes_instagram_reel(self):
        got = set(PF.fits(probe(seconds=60.0, size=120 * 1024 * 1024)))
        self.assertNotIn("instagram_story", got)
        self.assertIn("instagram_reel", got)

    def test_only_ghl_rows_are_destinations(self):
        got = PF.fits(probe())
        self.assertTrue(got)
        self.assertTrue(all(PF.row_for(p)["kind"] == "ghl" for p in got))


#: one ffprobe JSON answer, as the trial delivery reports it.
FFPROBE_JSON = json.dumps({
    "format": {"duration": "30.375034", "size": "13956855",
               "format_name": "mov,mp4,m4a,3gp,3g2,mj2"},
    "streams": [{"codec_type": "video", "codec_name": "h264", "width": 720,
                 "height": 1280, "avg_frame_rate": "24/1"},
                {"codec_type": "audio", "codec_name": "aac"}],
})


class _FakeProc:
    """A subprocess result stand-in: no ffprobe needed for the parse path."""
    returncode = 0
    stderr = ""
    stdout = FFPROBE_JSON


class Probe(unittest.TestCase):
    """probe_file(): one ffprobe read, routed through core/load_governor."""

    def test_json_becomes_a_probe_dict(self):
        got = PF.probe_file("/tmp/ad.mp4", runner=lambda argv: _FakeProc())
        self.assertEqual(got["duration_s"], 30.375034)
        self.assertEqual(got["size_bytes"], 13956855)
        self.assertEqual(got["container"], "mp4")
        self.assertEqual(got["video_codec"], "h264")
        self.assertEqual((got["width"], got["height"]), (720, 1280))
        self.assertEqual(got["fps"], 24.0)

    def test_the_command_is_ffprobe_through_the_governor(self):
        seen = {}

        def run(argv, job, **kw):
            seen["argv"], seen["job"] = list(argv), job
            return _FakeProc()

        with mock.patch.object(PF._LG, "run_heavy", run):
            PF.probe_file("/tmp/ad.mp4")
        self.assertEqual(seen["argv"][0], "ffprobe")
        self.assertEqual(seen["argv"][-1], "/tmp/ad.mp4")
        self.assertEqual(seen["job"], "platform-fit-probe")

    def test_a_failed_ffprobe_is_loud(self):
        class Bad:
            returncode = 1
            stderr = "No such file or directory"
            stdout = ""

        with self.assertRaises(ValueError):
            PF.probe_file("/tmp/nope.mp4", runner=lambda argv: Bad())


class RealFile(unittest.TestCase):
    """One real probe of the trial delivery, read-only, when this machine has it."""

    SAMPLE = sample_video()

    @unittest.skipUnless(SAMPLE and shutil.which("ffprobe"),
                         "sample video or ffprobe not present on this machine")
    def test_trial_a_delivery_is_probed_and_fits_the_reel_rows(self):
        try:
            got = PF.probe_file(self.SAMPLE)
        except Exception as exc:                       # noqa: BLE001
            if type(exc).__name__ in ("LoadGovernorError", "HeavyJobTimeout"):
                self.skipTest("load governor refused the probe: %s" % exc)
            raise
        self.assertEqual(got["container"], "mp4")
        self.assertGreater(got["duration_s"], 25.0)
        self.assertLess(got["duration_s"], 40.0)
        self.assertGreater(got["size_bytes"], 0)
        self.assertEqual(PF._ratio(got["width"], got["height"]), "9:16")
        r = PF.check(got, "instagram_reels_ad", TODAY)
        self.assertEqual(r["verdict"], PF.PASS, r["reason"])
        got_fits = PF.fits(got)
        self.assertIn("instagram_reel", got_fits)
        self.assertIn("youtube_short", got_fits)
        self.assertNotIn("x_twitter", got_fits)


if __name__ == "__main__":
    unittest.main(verbosity=2)
