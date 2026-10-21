#!/usr/bin/env python3
"""QC duration overshoot (order 2026-10-21): a FLAG, never a stop.

The one rule lives in master_length.judge_duration and is wired into the video
master check (master_length.check_master -> qc_gate / final_assembler) and the
song length gate (song_dispatch.judge_take). What this pins:

  * actual == target            -> PASS, no warning
  * target + 3 s                -> PASS + QC_DURATION_OVERSHOOT
  * target + 10 s               -> PASS + QC_DURATION_OVERSHOOT
  * target + 11 s               -> PASS + QC_DURATION_OVERSHOOT_SEVERE (no stop)
  * undershoot past the band    -> FAIL (exactly as today)

Nothing here is a new measured limit: the 10-second allowance is the rule the
order set, and the short-side band is spoken_share's 5/10 band, unchanged.

Run: python3 scripts/core/master_length/test_qc_duration_overshoot.py
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from master_length import (judge_duration, check_master, to_qc_record,
                           OVERSHOOT_ALLOWANCE_S)   # noqa: E402
import qc_gate                                      # noqa: E402

REV = {"identity": "qc", "session": "s1", "authority": "qc"}
TARGET = 60.0


class SongGate(unittest.TestCase):
    """The song length gate: overshoot passes, undershoot keeps today's band."""

    def test_exact_passes_clean(self):
        r = judge_duration(TARGET, TARGET)
        self.assertEqual((r["outcome"], r["verdict"]), ("ok", "PASS"))
        self.assertIsNone(r["warning"])
        self.assertEqual(r["reason_code"], "DURATION_WITHIN")

    def test_three_seconds_over_passes_with_the_named_warning(self):
        r = judge_duration(TARGET + 3, TARGET)
        self.assertEqual((r["outcome"], r["verdict"]), ("ok", "PASS"))
        self.assertEqual(r["warning"]["code"], "QC_DURATION_OVERSHOOT")
        self.assertIn("63s of 60s", r["detail"])
        self.assertIn("within the 10-second allowance", r["detail"])

    def test_ten_seconds_over_still_within_the_allowance(self):
        r = judge_duration(TARGET + OVERSHOOT_ALLOWANCE_S, TARGET)
        self.assertEqual(r["verdict"], "PASS")
        self.assertEqual(r["warning"]["code"], "QC_DURATION_OVERSHOOT")

    def test_eleven_seconds_over_flags_louder_and_never_stops(self):
        r = judge_duration(TARGET + 11, TARGET)
        self.assertEqual((r["outcome"], r["verdict"]), ("ok", "PASS"))
        self.assertEqual(r["warning"]["code"], "QC_DURATION_OVERSHOOT_SEVERE")
        self.assertIn("1s over the 10-second allowance", r["warning"]["detail"])

    def test_undershoot_still_fails_as_today(self):
        self.assertEqual(judge_duration(45, TARGET)["verdict"], "FAIL")
        self.assertEqual(judge_duration(45, TARGET)["outcome"], "rejected")
        # the existing 5/10 band on the short side is untouched
        self.assertEqual(judge_duration(57, TARGET)["verdict"], "PASS")
        self.assertEqual(judge_duration(54, TARGET)["verdict"], "FLAG")

    def test_unmeasured_fails_closed(self):
        for bad in (None, 0, -1, "60"):
            self.assertEqual(judge_duration(bad, TARGET)["verdict"], "FAIL")


class VideoMasterGate(unittest.TestCase):
    """The video master check (target L-2) and the qc_gate wiring."""

    def test_overshoot_is_a_flag_not_a_stop(self):
        r = check_master(60, 62)                    # 4 s over the 58 s maximum
        self.assertEqual((r["outcome"], r["reason_code"]),
                         ("ok", "MASTER_LENGTH_OVERSHOOT"))
        self.assertEqual(r["warning"]["code"], "QC_DURATION_OVERSHOOT")
        self.assertEqual(check_master(60, 68)["warning"]["code"],
                         "QC_DURATION_OVERSHOOT")   # +10 over the maximum
        severe = check_master(60, 69)               # +11 over the maximum
        self.assertEqual(severe["outcome"], "ok")
        self.assertEqual(severe["warning"]["code"], "QC_DURATION_OVERSHOOT_SEVERE")

    def test_short_master_is_still_free_on_the_short_side(self):
        # Unchanged from today: I4 is a maximum only.
        self.assertEqual(check_master(60, 30)["outcome"], "ok")

    def test_gate_advances_and_carries_the_warning(self):
        rec = to_qc_record(60, 62, REV, "r1", stage="final-qc")
        self.assertEqual(rec["verdict"], "PASS")
        self.assertEqual(rec["warnings"][0]["code"], "QC_DURATION_OVERSHOOT")
        g = qc_gate.evaluate("r1", "final-qc", [rec],
                             {rec["check_id"]: "maker"}, ["final_edit"],
                             master={"chosen_length_s": 60, "measured_s": 62})
        self.assertEqual(g["gate"], "PASS")
        self.assertEqual([w["code"] for w in g["warnings"]],
                         ["QC_DURATION_OVERSHOOT"])

    def test_unmeasured_master_still_blocks(self):
        rec = to_qc_record(60, 58, REV, "r1", stage="final-qc")
        g = qc_gate.evaluate("r1", "final-qc", [rec],
                             {rec["check_id"]: "maker"}, ["final_edit"])
        self.assertEqual(g["gate"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
