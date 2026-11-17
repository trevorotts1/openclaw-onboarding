#!/usr/bin/env python3
"""U-U03 cases for the narrator rule: a SUNG stem is the lip-sync input when
the line's own delivery is sung and the speaker is on screen; the selection is
built with lipsync_clips.choose_window (there is no lip_sync.select_lines).
$0, stdlib only. Run: python3 test_narrator_rule_u03.py
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.abspath(os.path.join(HERE, "..", ".."))
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from lip_sync.narrator_rule import (  # noqa: E402
    build_screened_plan, check_stems, screen_line,
)
from lip_sync.narrator_rule.narrator_rule import (  # noqa: E402
    RC_MUSIC_STEM, RC_SUNG_STEM,
)


def stem(kind="sung", speaker="lead", delivery=None, isolated=True):
    s = {"speaker_id": speaker, "kind": kind, "isolated": isolated}
    if delivery is not None:
        s["delivery"] = delivery
    return s


def words(n=25, step=0.4):
    return [{"word": "la", "start": round(i * step, 3),
             "end": round(i * step + 0.3, 3)} for i in range(n)]


class SungStemTests(unittest.TestCase):
    def test_sung_stem_allowed_for_a_sung_on_screen_line(self):
        ok, code, errors = check_stems([stem(delivery="sung")], "lead")
        self.assertTrue(ok, (code, errors))
        self.assertEqual("STEM_OK", code)

    def test_the_lines_delivery_may_be_named_by_the_caller(self):
        ok, _, _ = check_stems([stem()], "lead", "sung")
        self.assertTrue(ok)

    def test_sung_stem_refused_without_a_sung_delivery(self):
        ok, code, _ = check_stems([stem()], "lead")
        self.assertFalse(ok)
        self.assertEqual(RC_SUNG_STEM, code)
        ok, code, _ = check_stems([stem(delivery="spoken")], "lead")
        self.assertFalse(ok)
        self.assertEqual(RC_SUNG_STEM, code)

    def test_sung_stem_refused_for_an_off_screen_or_narrator_voice(self):
        for speaker in ("narrator", "off-screen", ""):
            ok, _, _ = check_stems([stem(speaker=speaker, delivery="sung")], speaker)
            self.assertFalse(ok, speaker)

    def test_music_bed_is_still_never_a_lip_sync_input(self):
        ok, code, _ = check_stems([stem(kind="music_bed", delivery="sung")], "lead")
        self.assertFalse(ok)
        self.assertEqual(RC_MUSIC_STEM, code)

    def test_screening_a_sung_scene_checks_its_sung_stem(self):
        env = screen_line({"line_id": "L1", "speaker": "lead", "onscreen": "lead",
                           "delivery": "sung", "stems": [stem(delivery="sung")]})
        self.assertEqual("ok", env["outcome"], env)
        self.assertTrue(env["lipsync"] and env["stems_verified"])


class ChooseWindowSelectionTests(unittest.TestCase):
    def test_the_plan_selects_the_flagged_line_with_a_real_window(self):
        plan = build_screened_plan({"L1": words()}, ["L1"],
                                   {"L1": {"speaker": "lead", "onscreen": "lead"}})
        self.assertEqual("ok", plan["outcome"], plan)
        self.assertEqual(["L1"], plan["lipsync_line_ids"])
        window = plan["selection"]["selected"][0]["window"]
        self.assertGreaterEqual(window["dur"], 4.0)
        self.assertLessEqual(window["dur"], 6.0)
        self.assertEqual("L1", plan["lipsync_selection"]["selected"][0]["line_id"])

    def test_an_unflagged_line_is_never_selected(self):
        plan = build_screened_plan({"L1": words(), "L2": words()}, ["L2"],
                                   {"L1": {"speaker": "lead", "onscreen": "lead"},
                                    "L2": {"speaker": "lead", "onscreen": "lead"}})
        self.assertEqual(["L2"], plan["lipsync_line_ids"])
        self.assertEqual(["L2"], [r["line_id"] for r in plan["selection"]["selected"]])

    def test_unreadable_timing_fails_closed(self):
        plan = build_screened_plan(None, [], {})
        self.assertEqual("error", plan["outcome"])
        self.assertEqual("TIMING_INVALID", plan["reason_code"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
