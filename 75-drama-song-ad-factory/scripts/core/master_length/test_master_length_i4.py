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
            # ORDER 2026-10-21: an overshoot within the 10 s allowance is a FLAG,
            # never a stop. The warning is named and carries the plain detail.
            flag = check_master(L, want + 0.04)
            self.assertEqual(flag["outcome"], "ok")
            self.assertEqual(flag["reason_code"], "MASTER_LENGTH_OVERSHOOT")
            self.assertEqual(flag["warning"]["code"], "QC_DURATION_OVERSHOOT")
            self.assertIn("%gs of %gs" % (want + 0.04, L), flag["detail"])
            self.assertEqual(check_master(L, L)["outcome"], "ok")        # the full length flags

    def test_one_minute_two_is_a_flag_not_a_stop(self):
        r = check_master(60, 62)
        self.assertEqual((r["outcome"], r["reason_code"]), ("ok", "MASTER_LENGTH_OVERSHOOT"))
        self.assertEqual(r["warning"]["code"], "QC_DURATION_OVERSHOOT")
        self.assertIn("62s of 60s", r["detail"])
        self.assertIn("within the 10-second allowance", r["detail"])
        # past the allowance it still does not stop: the warning is louder and
        # names the exact seconds over.
        hard = check_master(60, 71)
        self.assertEqual(hard["outcome"], "ok")
        self.assertEqual(hard["warning"]["code"], "QC_DURATION_OVERSHOOT_SEVERE")
        self.assertIn("3s over the 10-second allowance", hard["detail"])

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
        ok, over = to_qc_record(60, 58, REV, "r1"), to_qc_record(60, 61, REV, "r1")
        bad = to_qc_record(60, None, REV, "r1")
        self.assertIsNone(qc_gate.validate_record(ok))
        self.assertIsNone(qc_gate.validate_record(over))
        self.assertIsNone(qc_gate.validate_record(bad))
        self.assertEqual((ok["verdict"], over["verdict"], bad["verdict"]),
                         ("PASS", "PASS", "FAIL"))
        self.assertEqual(over["warnings"][0]["code"], "QC_DURATION_OVERSHOOT")


class Wired(unittest.TestCase):
    """Repair: the rule is enforced by the gate, assembler and planner."""

    def _gate(self, chosen, measured):
        rec = to_qc_record(chosen, measured, REV, "r1", stage="final-qc")
        return qc_gate.evaluate("r1", "final-qc", [rec], {rec["check_id"]: "maker"},
                                ["final_edit"],
                                master={"chosen_length_s": chosen, "measured_s": measured})

    def test_gate_flags_62s_on_60s_video_without_stopping(self):
        g = self._gate(60, 62)
        self.assertEqual(g["gate"], "PASS")
        codes = [w["code"] for w in g.get("warnings") or []]
        self.assertEqual(codes, ["QC_DURATION_OVERSHOOT"])
        self.assertEqual(self._gate(60, 58)["gate"], "PASS")
        # past the allowance it still advances; the warning is louder
        self.assertEqual(self._gate(60, 71)["gate"], "PASS")
        self.assertEqual([w["code"] for w in self._gate(60, 71)["warnings"]],
                         ["QC_DURATION_OVERSHOOT_SEVERE"])

    def test_gate_each_length_and_missing_master(self):
        for L in (30, 60, 90, 120):
            self.assertEqual(self._gate(L, L - 2)["gate"], "PASS")
            self.assertEqual(self._gate(L, L)["gate"], "PASS")   # 2 s over: flag, no stop
        rec = to_qc_record(60, 58, REV, "r1", stage="final-qc")
        g = qc_gate.evaluate("r1", "final-qc", [rec], {rec["check_id"]: "maker"}, ["final_edit"])
        self.assertEqual(g["gate"], "BLOCKED")  # no master supplied never passes

    def test_assembler_keeps_a_flagging_timeline_moving(self):
        import json, tempfile
        import final_assembler.assembler as A
        d = tempfile.mkdtemp()
        open(os.path.join(d, "c.mp4"), "wb").close()
        for dur, want in ((62.0, "other"), (58.0, "other"), (75.0, "other")):
            tl = os.path.join(d, "t.json")
            with open(tl, "w") as fh:
                json.dump({"schema_version": A.TIMELINE_SCHEMA, "fps": 30, "song_path": None,
                           "transition": "none", "chosen_length_s": 60,
                           "segments": [{"src": "c.mp4", "dur": dur}]}, fh)
            r = A.assemble(tl, os.path.join(d, "o.mp4"), dry_run=True)
            # an overshoot never stops the assembly (other gates may still speak)
            self.assertEqual(r["reason_code"] == "MASTER_TOO_LONG", want != "other", r)

    def test_planner_ends_at_l_minus_2(self):
        import shot_planner.shot_planner as SP
        from shot_planner.test_shot_beats_e2 import _shot
        timing = lambda dur: {"duration_seconds": dur, "sections": [{"section_id": "v", "lyrics": [
            {"line_id": "L1", "start": 1.0, "end": 3.0, "text": "x"}]}]}
        ok = SP.bind_plan([_shot(1.0, 57.0)], timing(58), chosen_length_s=60)
        self.assertEqual(ok["outcome"], "ok")
        for shots, dur, code in (([_shot(1.0, 59.0)], 58, "SHOT_PAST_MASTER_END"),
                                 ([_shot(1.0, 57.0)], 61, "SONG_PAST_MASTER_END")):
            with self.assertRaises(SP.PlanError) as c:
                SP.bind_plan(shots, timing(dur), chosen_length_s=60)
            self.assertEqual(c.exception.code, code)


if __name__ == "__main__":
    unittest.main()
