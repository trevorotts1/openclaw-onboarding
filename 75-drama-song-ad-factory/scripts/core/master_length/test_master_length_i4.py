#!/usr/bin/env python3
"""I4 tests: master ends 2 s early for every length. Run: python3 test_master_length_i4.py"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from master_length import master_max_s, plan, check_master, to_qc_record, MasterLengthError  # noqa: E402
import qc_gate  # noqa: E402

REV = {"identity": "qc", "session": "s1", "authority": "qc"}


class T(unittest.TestCase):
    def test_each_length(self):
        for L, want in ((15, 13), (30, 28), (60, 58), (90, 88), (120, 118), (180, 178)):
            p = plan(L)
            self.assertEqual(master_max_s(L), want)
            self.assertEqual({p["song_target_s"], p["shot_plan_end_s"], p["end_card_end_s"]}, {want})
            self.assertEqual(check_master(L, want)["outcome"], "ok")      # at the line passes
            self.assertEqual(check_master(L, want - 1.5)["outcome"], "ok")  # shorter passes
            bad = check_master(L, want + 0.04)                              # one frame over fails
            self.assertEqual((bad["outcome"], bad["reason_code"]), ("rejected", "MASTER_TOO_LONG"))
            self.assertEqual(check_master(L, L)["outcome"], "rejected")     # the full length now fails

    def test_one_minute_two_fails(self):
        self.assertEqual(check_master(60, 62)["reason_code"], "MASTER_TOO_LONG")

    def test_bad_input(self):
        for bad in (None, "60", True, 2, 0, -5, float("nan")):
            with self.assertRaises(MasterLengthError):
                master_max_s(bad)
        self.assertEqual(check_master(60, None)["reason_code"], "MASTER_LENGTH_UNMEASURED")

    def test_intake_summary_carries_master_max(self):
        import intake_preflight.intake as I
        for L, want in ((60, 58), (90, 88)):
            summary, _ = I.summarize({"target_length_s": L})
            self.assertEqual(summary["master_max_s"], want)
        self.assertIsNone(I.summarize({"target_length_s": None})[0]["master_max_s"])

    def test_qc_record_is_gate_valid(self):
        ok, no = to_qc_record(60, 58, REV, "r1"), to_qc_record(60, 61, REV, "r1")
        self.assertIsNone(qc_gate.validate_record(ok))
        self.assertIsNone(qc_gate.validate_record(no))
        self.assertEqual((ok["verdict"], no["verdict"]), ("PASS", "FAIL"))


if __name__ == "__main__":
    unittest.main()
