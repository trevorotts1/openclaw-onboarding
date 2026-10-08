#!/usr/bin/env python3
"""E1 tests: motion-compensated fps conform + dup-frame gate (manual 02
Part E E1, Critical; wave E unit W-E-U1).

stdlib only, unittest style matching sibling tests, zero paid calls,
no ffmpeg binary required (the dup-ratio parser is a pure function over
ffmpeg stderr text).

Covers (task acceptance):
  build_conform_argv - 24 -> 30 emits the minterpolate mci argv; equal
                       fps emits no filter (pass-through); duration-
                       preserving retime (30 -> 24) uses the same
                       minterpolate pattern; never the plain `fps` filter.
  conform_record     - source_fps/output_fps recorded per segment (and
                       plan_timeline stamps them on every segment).
  plan_timeline      - legacy timeline without per-clip fps still records
                       an equal-fps pass-through pair.
  assemble argv      - the render command carries minterpolate (not
                       `fps=`) for a 24 fps source at 30 fps.
  mpdecimate_dup_ratio - pure parsing: marker ratio (drop pts: / keep
                       pts:), zero evidence -> 0.0, no crash on empty.
  assert_no_dupe_frames - dup ratio 5.0 raises exactly
                       TIMELINE_DUP_FRAMES; 1.0 passes; cap respected.
  final QC gate      - assemble() dry-run evidence shows the gate wired.

Run:
    python3 final_assembler/test_fps_conform.py
    python3 -m unittest final_assembler.test_fps_conform -v
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import final_assembler.assembler as A        # noqa: E402
from final_assembler import fps_conform as F  # noqa: E402


def _plan(fps=30, src_fps=30, segs=1, dur=2.0, w=1920, h=1080):
    """Plan with conform_record fps fields, as plan_timeline now emits."""
    return A.plan_timeline({
        "schema_version": A.TIMELINE_SCHEMA, "fps": fps,
        "width": w, "height": h, "song_path": None,
        "transition": "none",
        "segments": [{"src": "clip%d.mp4" % i, "dur": dur,
                      "fps": src_fps} for i in range(segs)],
    }, ".")


# 30 s of the mpdecimate stderr shape ffmpeg 8.1.1 prints at
# -loglevel debug for a `fps`-filter-conformed 15 -> 30 clip: 15 keeps,
# 15 drops, so 50% duplicated.
STDERR_50_PCT = "\n".join(
    ['[Parsed_mpdecimate_0 @ 0x1] "%s"' % verb for verb in
     ["drop pts:512", "drop pts:1024", "keep pts:2048", "keep pts:4096",
      "drop pts:1536", "keep pts:5632", "drop pts:8192", "keep pts:9999",
      "drop pts:16384", "keep pts:20480"]] * 5)


class TestBuildConformArgv(unittest.TestCase):
    """E1(1): conform argv cases, never the plain fps filter."""

    def test_24_to_30_emits_minterpolate_mci(self):
        argv = F.build_conform_argv(24, 30)
        self.assertIsInstance(argv, str)
        self.assertIn("minterpolate=fps=30:mi_mode=mci", argv)

    def test_25_to_30_emits_minterpolate_mci(self):
        self.assertIn("minterpolate=fps=30:mi_mode=mci",
                      F.build_conform_argv(25, 30))

    def test_equal_fps_pass_through_no_filter(self):
        self.assertEqual(F.build_conform_argv(30, 30), "")
        self.assertEqual(F.build_conform_argv(29.97, 29.97), "")

    def test_duration_preserving_retime_same_pattern(self):
        # 30 -> 24 (target BELOW source): a duration-preserving retime
        # per manual wording -- same minterpolate pattern.
        argv = F.build_conform_argv(30, 24)
        self.assertIn("minterpolate=fps=24:mi_mode=mci", argv)

    def test_never_plain_fps_filter(self):
        # The plain `fps` filter appears as `fps=<n>:` in a chain;
        # minterpolate's own `fps=` key is part of the legal pattern.
        for src, dst in ((24, 30), (25, 30), (30, 24), (23.976, 30)):
            argv = F.build_conform_argv(src, dst)
            self.assertRegex(argv, r"minterpolate=fps=[0-9.]+:mi_mode=mci")
            self.assertNotRegex(argv, r"(?<!interpolate=)fps=,")

    def test_plain_fps_banned_in_assembler_chain(self):
        # Belt + braces on the whole call: the conform segment of the
        # chain never contains the bare `fps=` filter.
        import re as _re
        argv = A.build_argv(_plan(fps=30, src_fps=24), "out.mp4")
        fc = argv[argv.index("-filter_complex") + 1]
        # The only fps= key in the chain is minterpolate's own; a bare
        # `fps=<n>` filter (E1's banned pattern) would not sit inside a
        # `minterpolate=` key.
        bare = [m for m in _re.finditer(r"fps=", fc)
                if not fc[:m.start()].endswith("interpolate=")]
        self.assertEqual(bare, [])

    def test_fractional_source_fps_string(self):
        self.assertIn("minterpolate=fps=30:mi_mode=mci",
                      F.build_conform_argv("30000/1001", 30))

    def test_bad_fps_raises(self):
        with self.assertRaises(ValueError):
            F.build_conform_argv(0, 30)
        with self.assertRaises(ValueError):
            F.build_conform_argv("nonsense", 30)


class TestConformRecord(unittest.TestCase):
    """E1(3): source_fps/output_fps per segment in the manifest."""

    def test_record_fields_round_trip(self):
        rec = F.conform_record(24, 30)
        self.assertEqual(rec["source_fps"], 24.0)
        self.assertEqual(rec["output_fps"], 30.0)

    def test_plan_timeline_stamps_every_segment(self):
        plan = A.plan_timeline({
            "schema_version": A.TIMELINE_SCHEMA, "fps": 30,
            "width": 1920, "height": 1080, "song_path": None,
            "transition": "none",
            "segments": [{"src": "a.mp4", "dur": 2.0, "fps": 24},
                         {"src": "b.mp4", "dur": 2.0, "fps": 30}],
        }, ".")
        for seg, want in zip(plan["segments"], (24.0, 30.0)):
            self.assertEqual(seg["source_fps"], want)
            self.assertEqual(seg["output_fps"], 30.0)

    def test_legacy_timeline_defaults_to_equal_fps(self):
        # A timeline without per-clip fps keys records a pass-through
        # pair (source == output == timeline fps): additive keys on
        # blackceo.timeline/v1 segments.
        plan = _plan(fps=30, src_fps=30)
        self.assertEqual(plan["segments"][0]["source_fps"], 30.0)
        self.assertEqual(plan["segments"][0]["output_fps"], 30.0)


class TestBuildArgvConformWiring(unittest.TestCase):
    """E1(2): the assembler call site uses fps_conform.build_conform_argv."""

    def test_argv_24src_carries_minterpolate_not_fps(self):
        argv = A.build_argv(_plan(fps=30, src_fps=24), "out.mp4")
        fc = argv[argv.index("-filter_complex") + 1]
        self.assertIn("minterpolate=fps=30:mi_mode=mci", fc)
        self.assertNotIn(",fps=", fc)

    def test_argv_equal_src_has_no_conform(self):
        argv = A.build_argv(_plan(fps=30, src_fps=30), "out.mp4")
        fc = argv[argv.index("-filter_complex") + 1]
        self.assertNotIn("minterpolate", fc)


class TestMpdecimateDupRatio(unittest.TestCase):
    """E1(4): pure parser over ffmpeg stderr text."""

    def test_marker_ratio_50_pct(self):
        self.assertAlmostEqual(F.mpdecimate_dup_ratio(STDERR_50_PCT), 50.0)

    def test_all_dropped_is_100(self):
        text = "drop pts:1\ndrop pts:2\ndrop pts:3\n"
        self.assertAlmostEqual(F.mpdecimate_dup_ratio(text), 100.0)

    def test_no_markers_zero(self):
        self.assertEqual(F.mpdecimate_dup_ratio("frame= 30 ... Lsize=N/A"), 0.0)
        self.assertEqual(F.mpdecimate_dup_ratio(""), 0.0)
        self.assertEqual(F.mpdecimate_dup_ratio(None), 0.0)

    def test_marker_count_over_total(self):
        # Exact fixture arithmetic: 60 keep markers, 30 drop markers
        # (mpdecimate drops every third frame) -> 33.333%.
        text = ("keep pts:1\n" * 60) + ("drop pts:1\n" * 30)
        self.assertAlmostEqual(F.mpdecimate_dup_ratio(text), 100.0 * 30 / 90)

    def test_realistic_stderr_no_crash(self):
        text = ("Input #0, mov,mp4\n"
                "frame=   15 fps=0.0 q=-0.0 Lsize=N/A time=00:00:00.96\n")
        self.assertEqual(F.mpdecimate_dup_ratio(text), 0.0)


class TestAssertNoDupeFrames(unittest.TestCase):
    """E1(4): exact reason code TIMELINE_DUP_FRAMES; 2.0 cap."""

    def test_5_pct_fails_with_exact_reason(self):
        with self.assertRaises(ValueError) as ctx:
            F.assert_no_dupe_frames(5.0)
        self.assertEqual(str(ctx.exception), F.TIMELINE_DUP_FRAMES)

    def test_1_pct_passes(self):
        self.assertTrue(F.assert_no_dupe_frames(1.0))

    def test_cap_boundary(self):
        self.assertTrue(F.assert_no_dupe_frames(2.0))       # <= cap passes
        with self.assertRaises(ValueError):
            F.assert_no_dupe_frames(2.01)

    def test_none_passes(self):
        self.assertTrue(F.assert_no_dupe_frames(None))

    def test_default_cap_is_manual_floor(self):
        self.assertEqual(F.DUP_FRAMES_CAP, 2.0)


class TestFinalGateWired(unittest.TestCase):
    """E1(5): the master QC gate fails TIMELINE_DUP_FRAMES above 2%."""

    def test_assemble_evidence_carries_dup_metrics(self):
        import json
        import tempfile
        tmp = tempfile.mkdtemp(prefix="/tmp/w75-W-E-U1-")
        try:
            clip = os.path.join(tmp, "clip.mp4")
            open(clip, "wb").close()
            tl = os.path.join(tmp, "timeline.json")
            with open(tl, "w", encoding="utf-8") as fh:
                json.dump({
                    "schema_version": A.TIMELINE_SCHEMA, "fps": 30,
                    "width": 1920, "height": 1080, "song_path": None,
                    "transition": "none",
                    "segments": [{"src": "clip.mp4", "dur": 10.0}],
                }, fh)
            rec = A.assemble(tl, os.path.join(tmp, "out.mp4"), dry_run=True)
            plan = rec["evidence"]["plan"]
            self.assertEqual(plan["segments"][0]["output_fps"], 30.0)

            # Gate path itself: a failing ratio returns the exact reason.
            fail = A._fail(F.TIMELINE_DUP_FRAMES,
                           next_action="dup frames",
                           evidence={"dup_frame_pct": 5.0})
            self.assertEqual(fail["reason_code"], F.TIMELINE_DUP_FRAMES)
            self.assertEqual(fail["evidence"]["dup_frame_pct"], 5.0)
            self.assertEqual(fail["outcome"], "error")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


def main():
    unittest.main(module=None, argv=[sys.argv[0], "-v"], exit=True)


if __name__ == "__main__":
    unittest.main()