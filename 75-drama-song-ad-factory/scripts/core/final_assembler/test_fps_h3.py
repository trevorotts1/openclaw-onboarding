#!/usr/bin/env python3
"""Part H H3 tests: master 30 fps, Kling pass-through, MiniMax H3 24->30
interpolation, per-segment mpdecimate duplicate check. $0: local ffmpeg only.

Run: python3 test_fps_h3.py
"""
import json
import os
import shutil
import subprocess
import sys
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
    return {"schema_version": A.TIMELINE_SCHEMA, "fps": 30, "width": 320,
            "height": 240, "song_path": None, "segments": segs, **kw}


class TestPolicy(unittest.TestCase):
    def test_master_must_be_30(self):
        with self.assertRaises(ValueError) as c:
            self._load(24, False)
        self.assertIn("TIMELINE_FPS_NOT_30", str(c.exception))

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
        self.assertEqual(self._load(24, True)["fps"], 24)

    def test_native_rates(self):
        self.assertEqual(F.native_fps("kling-ai-avatar"), 30.0)
        self.assertEqual(F.native_fps("MiniMax-Hailuo-H3"), 24.0)
        self.assertIsNone(F.native_fps("unknown"))

    def test_kling_passthrough_h3_interpolated_never_plain_fps(self):
        tl = _tl([{"src": "k.mp4", "dur": 2, "model": "kling-avatar"},
                  {"src": "h.mp4", "dur": 2, "model": "minimax-h3"}])
        plan = A.plan_timeline(tl, ".", probe=lambda s: 2.0)
        self.assertEqual(plan["segments"][0]["source_fps"], 30.0)
        self.assertEqual(plan["segments"][1]["source_fps"], 24.0)
        argv = A.build_argv(plan, "out.mp4")
        fc = argv[argv.index("-filter_complex") + 1].split(";")
        self.assertNotIn("minterpolate", fc[0])
        self.assertNotIn("fps=", fc[0])
        self.assertIn("minterpolate=fps=30:mi_mode=mci", fc[1])
        self.assertNotIn(",fps=", ";".join(fc))


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
    def test_30fps_master_kling_keeps_frames_h3_interpolated(self):
        d = tempfile.mkdtemp()
        try:
            for name, rate in (("k.mp4", 30), ("h.mp4", 24)):
                subprocess.run(
                    ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                     "-threads", "4", "-t", "2.5", "-f", "lavfi", "-i",
                     "mandelbrot=size=320x240:rate=%d" % rate,
                     "-pix_fmt", "yuv420p", os.path.join(d, name)],
                    check=True)
            tp = os.path.join(d, "t.json")
            kl = {"src": "k.mp4", "dur": 2, "model": "kling",
                  "lip_sync": True}
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
            self.assertEqual(st["r_frame_rate"], "30/1")
            segs = rec["evidence"]["segment_dups"]
            self.assertEqual(len(segs), 4)
            self.assertTrue(all(r["pass"] for r in segs))
            self.assertLessEqual(rec["evidence"]["dup_frame_pct"], 2.0)
            # Kling: 60 source frames in, none dropped (2 s x 30 fps window).
            with open(tp) as fh:
                total = A.plan_timeline(json.load(fh), d,
                                        probe=lambda s: 2.0)["total_frames"]
            self.assertEqual(int(st["nb_read_frames"]), total)
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
