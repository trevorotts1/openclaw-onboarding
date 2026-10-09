#!/usr/bin/env python3
"""FU-LENGTH-CLIPS: the 3 minute ad schedules a 60s and a 90s clip, and the
cutdown produces both from a 180s timeline (no media, no paid calls).

Run: python3 core/clip_cutdown/test_clip_cutdown_flc.py
"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)
from clip_cutdown import clips_for, plan_clips, build_argv, run_clips, ClipCutdownError  # noqa: E402
from sung_hook import sung_hook as SH  # noqa: E402
from delivery_fixture import make_video  # noqa: E402


def timeline(total=178.0, end_card=None):
    """A line every 5 s; a hook line wherever sung_hook says one belongs."""
    hooks = SH.hook_times(total)
    lines = []
    for i in range(int(total // 5)):
        s = i * 5.0
        lines.append({"line_id": "L%d" % i, "start_s": s, "end_s": s + 4.5,
                      "beat": "beat%d" % (i // 3),
                      "hook": any(s <= h < s + 5 for h in hooks)})
    tl = {"schema_version": "blackceo.timeline/v1", "lines": lines}
    if end_card:
        tl["endcard_start_s"] = end_card
    return tl


class T(unittest.TestCase):
    def test_three_minutes_schedules_both_clips(self):
        self.assertEqual(clips_for(180), (60, 90))
        self.assertEqual([p["clip_length_s"] for p in plan_clips(timeline(), 180)], [60, 90])

    def test_5_and_10_minutes_too_60_and_90_get_none(self):
        self.assertEqual(clips_for(300), (60, 90))
        self.assertEqual(clips_for(600), (60, 90))
        self.assertEqual((clips_for(60), clips_for(90)), ((), ()))
        self.assertEqual(plan_clips(timeline(88), 90), [])

    def test_clips_come_out_at_60_and_90_from_180s(self):
        tl = timeline(178, end_card=176)
        calls = []

        class R:
            returncode = 0

        def fake(argv, **k):                  # a real AAC file, so the delivery gate passes
            calls.append(argv)
            make_video(argv[-1])
            return R()
        paths = run_clips("master.mp4", plan_clips(tl, 180), tempfile.mkdtemp(), runner=fake)
        self.assertEqual([os.path.basename(p) for p in paths], ["clip-60s.mp4", "clip-90s.mp4"])
        durs = [float(a[a.index("-t") + 1]) for a in calls]
        self.assertTrue(50 <= durs[0] <= 58, durs)      # 60 s clip, ends 2 s early
        self.assertTrue(75 <= durs[1] <= 88, durs)      # 90 s clip, ends 2 s early

    def test_whole_lines_hooks_and_end_card_rules(self):
        tl = timeline(178, end_card=170)
        starts = {l["start_s"] for l in tl["lines"]}
        ends = {l["end_s"] for l in tl["lines"]}
        for p in plan_clips(tl, 180):
            self.assertIn(p["start_s"], starts)
            self.assertIn(p["end_s"], ends)
            self.assertLessEqual(p["end_s"], 170)
            self.assertLessEqual(p["duration_s"], p["clip_length_s"] - 2)
            self.assertGreaterEqual(p["hooks"], 2)
            inside = [l for l in tl["lines"] if l["hook"] and p["start_s"] <= l["start_s"] and l["end_s"] <= p["end_s"]]
            self.assertLessEqual(inside[0]["start_s"] - p["start_s"], SH.FIRST_HOOK_AT * p["duration_s"] + 1e-6)

    def test_clips_never_run_into_the_end_card(self):
        for p in plan_clips(timeline(178, end_card=60), 180):
            self.assertLessEqual(p["end_s"], 60)

    def test_no_hook_lines_fails_closed(self):
        tl = timeline()
        for l in tl["lines"]:
            l["hook"] = False
        with self.assertRaises(ClipCutdownError):
            plan_clips(tl, 180)

    def test_argv_cuts_and_fades(self):
        p = plan_clips(timeline(), 180)[0]
        a = build_argv("m.mp4", p, "o")
        self.assertEqual(a[a.index("-ss") + 1], "%.3f" % p["start_s"])
        self.assertTrue(any(x.startswith("afade=") for x in a))


if __name__ == "__main__":
    unittest.main()
