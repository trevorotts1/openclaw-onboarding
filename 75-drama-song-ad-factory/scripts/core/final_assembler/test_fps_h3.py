#!/usr/bin/env python3
"""N-23 tests: master 24 fps (H3/OmniHuman native), no interpolation
anywhere, per-segment mpdecimate duplicate check. $0: local ffmpeg only.

Run: python3 test_fps_h3.py
"""
import json
import os
import shutil
import subprocess
import sys
from unittest.mock import patch
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import final_assembler.assembler as A          # noqa: E402
import final_assembler.fps_conform as F        # noqa: E402

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def _tl(segs, **kw):
    return {"schema_version": A.TIMELINE_SCHEMA, "fps": 24, "width": 320,
            "height": 240, "song_path": None, "segments": segs, **kw}


class TestPolicy(unittest.TestCase):
    def test_master_must_be_native(self):
        # N-23: 24 is the new master rate; 30 stays accepted so a timeline
        # that assembles today keeps assembling. Any other rate refuses.
        with self.assertRaises(ValueError) as c:
            self._load(60, False)
        self.assertIn("TIMELINE_FPS_NOT_NATIVE", str(c.exception))

    def test_legacy_30_still_assembles(self):
        self.assertEqual(self._load(30, False)["fps"], 30)
        self.assertEqual(self._load(24, False)["fps"], 24)

    def _load(self, fps, card):
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "t.json")
            extra = {"fps_set_by_choice_card": True} if card else {}
            with open(p, "w") as fh:
                json.dump(_tl([{"src": "a.mp4", "dur": 2}], fps=fps, **extra),
                          fh)
            return A.load_timeline(p)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_choice_card_may_set_other_rate(self):
        self.assertEqual(self._load(60, True)["fps"], 60)

    def test_native_rates(self):
        self.assertEqual(F.native_fps("kling-ai-avatar"), 30.0)
        self.assertEqual(F.native_fps("MiniMax-Hailuo-H3"), 24.0)
        self.assertIsNone(F.native_fps("unknown"))

    def test_no_interpolation_on_any_take(self):
        # N-23: the H3 clip is native 24 and passes through untouched; the
        # Kling clip drops 30 -> 24 by plain frame drop. Nothing interpolates.
        tl = _tl([{"src": "k.mp4", "dur": 2, "model": "kling-avatar"},
                  {"src": "h.mp4", "dur": 2, "model": "minimax-h3"}])
        plan = A.plan_timeline(tl, ".", probe=lambda s: 2.0)
        self.assertEqual(plan["segments"][0]["source_fps"], 30.0)
        self.assertEqual(plan["segments"][1]["source_fps"], 24.0)
        argv = A.build_argv(plan, "out.mp4")
        fc = argv[argv.index("-filter_complex") + 1]
        self.assertNotIn("minterpolate", fc)
        self.assertIn("fps=24", fc)      # Kling drops to the master rate
        # The H3 chain (second segment) is a pure pass-through.
        segs = fc.split(";")
        self.assertNotIn("fps=", segs[1])


class TestSegmentDupCheck(unittest.TestCase):
    def _plan(self, hold=False):
        segs = [{"src": "a.mp4", "frames": 60, "offset_frames": 0, "hold": False},
                {"src": "b.mp4", "frames": 60, "offset_frames": 60, "hold": hold}]
        return {"fps": 30.0, "segments": segs}

    def _run(self, argv):   # first window clean, second window 50% dupes
        keep, drop = ("keep pts:1\n", "drop pts:1\n")
        return keep * 60 if "0.000000" in argv else keep * 30 + drop * 30

    def test_bad_segment_fails_clean_passes(self):
        rows, bad = F.segment_dup_report("m.mp4", self._plan(), run=self._run)
        self.assertEqual([r["index"] for r in bad], [1])
        self.assertEqual(rows[0]["dup_pct"], 0.0)

    def test_marked_hold_is_exempt(self):
        rows, bad = F.segment_dup_report("m.mp4", self._plan(True), run=self._run)
        self.assertEqual(bad, [])
        self.assertTrue(rows[1]["hold"])


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not installed")
class TestRealRender(unittest.TestCase):
    # Isolate FPS rendering from separately tested lip-sync evidence joins.
    @patch("lipsync_evidence.check_plan", return_value={"pass": True, "evidence": {}})
    @patch.object(A, "lipsync_gate", return_value=None)
    def test_24fps_master_kling_drops_h3_passes_through(self, _coverage, _export):
        d = tempfile.mkdtemp()
        try:
            for name, rate in (("k.mp4", 30), ("h.mp4", 24)):
                subprocess.run(
                    ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                     "-threads", "4", "-t", "2.5", "-f", "lavfi", "-i",
                     "mandelbrot=size=320x240:rate=%d" % rate,
                     "-pix_fmt", "yuv420p", os.path.join(d, name)],
                    check=True)
            # N-113 needs an eye record on every lip-sync take, and
            # F-LETTER-RENDER needs a real reader (never a stub) at the
            # render. A clean registered reader rows every take, no text.
            import final_assembler.frame_text as FT
            FT.register_extractor("fps-h3-clean",
                                  lambda paths: [None] * len(paths))
            _orig = A._onscreen_extractor
            A._onscreen_extractor = lambda _ff: "fps-h3-clean"
            tp = os.path.join(d, "t.json")
            kl = {"src": "k.mp4", "dur": 2, "model": "kling",
                  "lip_sync": True,
                  "eye_check": {"sheet": "sheet.jpg", "who": "operator",
                                "verdict": "clean"}}
            with open(tp, "w") as fh:
                json.dump(_tl([kl, dict(kl), dict(kl),
                               {"src": "h.mp4", "dur": 2,
                                "model": "minimax-h3"}]), fh)
            out = os.path.join(d, "out.mp4")
            rec = A.assemble(tp, out)
            self.assertEqual(rec["outcome"], "ok", rec)
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-count_frames", "-show_entries",
                 "stream=r_frame_rate,nb_read_frames", "-of", "json", out],
                capture_output=True, text=True, check=True)
            st = json.loads(probe.stdout)["streams"][0]
            # N-23: the master is 24 fps; nothing interpolates.
            self.assertEqual(st["r_frame_rate"], "24/1")
            segs = rec["evidence"]["segment_dups"]
            self.assertEqual(len(segs), 4)
            # N-15: the Kling takes drop 30 -> 24 by plain frame drop, so the
            # per-segment rows are ADVICE on a passing master, not a refusal.
            self.assertLessEqual(rec["evidence"]["dup_frame_pct"], 2.0)
            with open(tp) as fh:
                total = A.plan_timeline(json.load(fh), d,
                                        probe=lambda s: 2.0)["total_frames"]
            self.assertEqual(int(st["nb_read_frames"]), total)
        finally:
            A._onscreen_extractor = _orig
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
