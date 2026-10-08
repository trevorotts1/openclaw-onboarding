#!/usr/bin/env python3
"""G7 tests: the 7-question delivery checklist on the Final edit QC gate.

Done-when cases from Trevor order 1140 (in HOME=$(mktemp -d), no operator
paths, stdlib only):
  1. a receipt missing ANY of the 7 measured answers FAILS the gate;
  2. a complete measured receipt PASSES;
  3. a "yes" without a measurement FAILS;
  4. a "no" produces a redo directive naming ONLY the failing part and
     never a cancel (repair_scope is exactly the failing questions, the
     shared gate verdict stays FAIL -- targeted repair -- never BLOCKED).

Also proves the checklist ships verbatim next to the code and that the
gate record wires into core/qc_gate.py (evaluate accepts it; a FAIL
record fails the final_edit stage fail-closed).

Run: python3 core/delivery_checklist/test_delivery_checklist.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_CORE = _HERE.parents[0]                       # .../scripts/core
_SKILL = _CORE.parents[1]                      # .../75-drama-song-ad-factory
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

# the checker lives in the package next to this test; import it as a
# package module so sys.path order can never shadow it with __init__.py
import delivery_checklist.delivery_checklist as dc  # noqa: E402

import qc_gate                                 # noqa: E402  (shared gate)

RUN = "g7-run"
STAGE = "final"
REVIEWER = {"identity": "delivery_checklist/1.0.0",
            "session": "g7-test-session",
            "authority": "trevor-order-1140-G7"}
MAKERS = {dc.CHECK_ID: "final_assembler/1.0.0",
          "final-edit-e2e": "final_assembler/1.0.0"}
# gate 4 "Final" required list with the G7 checker on it (the wiring the
# run's Final edit QC uses from now on)
FINAL_GATE_REQUIRED = ["final_edit", "delivery_checklist"]


def final_edit_record(run=RUN, stage=STAGE, verdict="PASS"):
    """A sibling final_edit PASS record, so the gate has both required checks."""
    return {
        "schema_version": "1.0.0", "check_id": "final-edit-e2e",
        "run_id": run, "stage": stage, "check": "final_edit",
        "verdict": verdict,
        "evidence": {"summary": "final edit %s (e2e fixture)"
                               % ("pass" if verdict == "PASS" else "FAIL")},
        "checker_version": "1.0.0",
        "reviewer": {"identity": "final_qc/1.0.0", "session": "g7-e2e",
                     "authority": "17.5 final edit QC"},
    }


def full_answered_receipt():
    """A receipt answering all 7 questions with measured evidence."""
    return {
        "SUNG": {"style": "sung", "sung_pct": 61.0, "spoken_pct": 39.0,
                 "detector": "singing-detector(vocal-stem)", "source_sung_pct":
                 "vocal-stem astats", "source_spoken_pct": "vocal-stem astats",
                 "source_detector": "detector-id g3"},
        "ON_TARGET": {"shares": {
            "sung": {"measured_pct": 61.0, "target_pct": 60.0},
            "spoken": {"measured_pct": 45.0, "target_pct": 45.0},
        }, "length_s": 61.0, "target_length_s": 60.0,
            "source_shares": "timing map", "source_length_s": "ffprobe"},
        "WORDS": {"words_present": 100, "words_total": 100,
                  "missing_words": [], "invented_words": [],
                  "source_words_present": "diff script vs srt",
                  "source_words_total": "script"},
        "FACES": {"shots": [
            {"shot": "s1", "frame": "frames/s1-012.png", "emotion_match":
             True},
            {"shot": "s2", "frame": "frames/s2-044.png", "emotion_match":
             True},
        ], "source_shots": "sampled frames"},
        "VOICE_MUSIC": {"music_unbroken": True, "music_gaps_s": 0.0,
                        "reverb_tail_s": 0.0, "lines": [
            {"delivery": "spoken", "mode": "spoken"},
            {"delivery": "sung", "mode": "sung"},
        ], "source_music_gaps_s": "silencedetect"},
        "MODELS": {"used": {"video": "MiniMax H3 768P",
                            "images": "gpt-image sunburst",
                            "song": "Suno V6",
                            "lip_sync": "Kling avatar"},
                   "source_used": "job receipts"},
        "HONEST_RECEIPT": {"measured_fields": 14, "unmeasured_fields": 0,
                           "source_measured_fields": "receipt audit",
                           "source_unmeasured_fields": "receipt audit"},
        "LIP_SYNC": {"source": "lipsync_gate(H2) envelope xcorr", "clips": [
            {"clip": "ls1", "offset_s": 0.02, "correlation": 0.71,
             "control_correlation": 0.20, "frozen_s": 0.3},
            {"clip": "ls2", "offset_s": -0.04, "correlation": 0.60,
             "control_correlation": 0.30, "frozen_s": 0.0},
        ]},
        "FIRST_SUNG": {"source": "singing-detector vocal stem",
                       "detector": "singing-detector(vocal-stem)",
                       "first_sung_pct": 14.0},
        "PICTURES_MATCH": {"source": "H5 shot-to-line map, Suno timestamps",
                           "shots": [
            {"shot": "s1", "time_s": 4.2, "line": "the house went quiet",
             "match": True, "slowdown": 1.0},
            {"shot": "s2", "time_s": 9.8, "line": "she picked up the phone",
             "match": True, "slowdown": 1.1},
        ]},
        "GOALS_BAND": {"source": "target engine receipt", "goals": [
            {"name": "sung_share", "measured": 61.0, "target": 60.0},
            {"name": "spoken_share", "measured": 49.0, "target": 45.0},
            {"name": "length_s", "measured": 63.0, "target": 60.0,
             "unit": "s"},
            {"name": "first_sung", "measured": 21.0, "target": 15.0,
             "flag": "FLAG first_sung 21 vs 15 (6 off, over 5)"},
        ]},
    }


def measured_yes(q, receipt):
    """Flip question q's answer to an explicit measured pass."""
    receipt[q] = receipt[q]                  # already measured in the fixture
    return receipt


class G7DoneWhen(unittest.TestCase):
    # ---- done-when 1: missing ANY measured answer FAILS the gate -------
    def test_missing_answer_fails(self):
        for q in dc.QUESTIONS:
            receipt = full_answered_receipt()
            del receipt[q]
            res = dc.evaluate(receipt)
            self.assertFalse(res["pass"], "missing %s must FAIL" % q)
            self.assertIn(q, res["repair_scope"])
            codes = {c.split(":")[0] for c in
                     [res["detail"]]}
            self.assertIn(dc.REASON_CODES["ANSWER_MISSING"], res["reason_code"])

    # ---- done-when 2: complete measured receipt PASSES ------------------
    def test_complete_receipt_passes(self):
        res = dc.evaluate(full_answered_receipt())
        self.assertTrue(res["pass"], res["detail"])
        self.assertEqual(res["repair_scope"], [])
        self.assertEqual(res["reason_code"], "CHECKLIST_ALL_MEASURED_PASS")
        self.assertEqual(len(res["answers"]), 11)
        self.assertTrue(all(a["answer"] == "yes"
                            for a in res["answers"].values()))

    # ---- done-when 3: "yes" without a measurement FAILS -----------------
    def test_yes_without_measurement_fails(self):
        for q, bare in (
            ("SUNG", {"sung": "yes"}),
            ("ON_TARGET", {"on_target": "yes"}),
            ("WORDS", {"words_ok": True}),
            ("FACES", {"faces_ok": "yes"}),
            ("VOICE_MUSIC", {"music_ok": "yes"}),
            ("MODELS", {"models_ok": True}),
            ("HONEST_RECEIPT", {"honest": "yes"}),
            ("LIP_SYNC", {"lip_sync_ok": "yes"}),
            ("FIRST_SUNG", {"singing_early": True}),
            ("PICTURES_MATCH", {"pictures_ok": "yes"}),
            ("GOALS_BAND", {"all_within": "yes"}),
        ):
            receipt = full_answered_receipt()
            receipt[q] = bare
            res = dc.evaluate(receipt)
            self.assertFalse(res["pass"],
                             "%s bare 'yes' must count as 'no'" % q)
            self.assertEqual(res["repair_scope"], [q])
            self.assertEqual(res["answers"][q]["answer"], "no")

    # ---- done-when 4: "no" re-does ONLY the failing part, never cancel --
    def test_no_names_only_failing_part_never_cancels(self):
        # Q2 off-target: length 20% off (target 60, measured 72) only
        receipt = full_answered_receipt()
        receipt["ON_TARGET"]["length_s"] = 72.0
        res = dc.evaluate(receipt)
        self.assertFalse(res["pass"])
        self.assertEqual(res["repair_scope"], ["ON_TARGET"])
        self.assertNotIn("CANCEL", res["reason_code"])
        # gate stays FAIL (targeted repair), never BLOCKED; the sibling
        # final_edit record passes, so the FAIL is the checklist alone
        rec = dc.to_qc_record(res, RUN, STAGE, REVIEWER)
        gate = qc_gate.evaluate(RUN, STAGE, [rec, final_edit_record()],
                                MAKERS, FINAL_GATE_REQUIRED, master={"chosen_length_s": 60, "measured_s": 58})
        self.assertEqual(gate["gate"], "FAIL")
        self.assertEqual(gate["repair_scope"], [dc.CHECK_ID])
        self.assertNotEqual(gate["gate"], "BLOCKED")
        # and two failures name exactly those two, nothing more
        receipt["WORDS"]["invented_words"] = ["wow"]
        res2 = dc.evaluate(receipt)
        self.assertEqual(sorted(res2["repair_scope"]),
                         ["ON_TARGET", "WORDS"])

    # ---- the other five G7 laws -----------------------------------------
    def test_yes_without_measurement_in_evidence_counts_no(self):
        # the literal order law: "yes" WITHOUT a measurement == "no"
        receipt = full_answered_receipt()
        receipt["FACES"] = {"faces_ok": "yes", "emotion": "matches"}
        res = dc.evaluate(receipt)
        self.assertEqual(res["answers"]["FACES"]["answer"], "no")
        self.assertIn("NO_MEASUREMENT", res["answers"]["FACES"]["measurement"])

    def test_off_target_within_tolerance_passes(self):
        receipt = full_answered_receipt()
        receipt["ON_TARGET"]["shares"]["spoken"]["measured_pct"] = 49.5
        res = dc.evaluate(receipt)
        self.assertTrue(res["pass"], res["detail"])

    def test_unmeasured_written_unmeasured_is_honest(self):
        receipt = full_answered_receipt()
        receipt["HONEST_RECEIPT"] = {
            "reverb_tail_s": "UNMEASURED",
            "source_reverb_tail_s": "not sampled this run",
            "measured_fields": 13,
            "source_measured_fields": "receipt audit",
        }
        res = dc.evaluate(receipt)
        self.assertTrue(res["pass"], res["detail"])

    def test_honest_numbers_without_source_fail(self):
        receipt = full_answered_receipt()
        del receipt["HONEST_RECEIPT"]["source_measured_fields"]
        res = dc.evaluate(receipt)
        self.assertFalse(res["pass"])
        self.assertIn("HONEST_RECEIPT", res["repair_scope"])

    def test_wrong_model_fails(self):
        receipt = full_answered_receipt()
        receipt["MODELS"]["used"]["video"] = "Runway Gen-3"
        res = dc.evaluate(receipt)
        self.assertFalse(res["pass"])
        self.assertIn("MODELS", res["repair_scope"])

    def test_face_mismatch_names_frame_and_line(self):
        receipt = full_answered_receipt()
        receipt["FACES"]["shots"][1]["emotion_match"] = False
        res = dc.evaluate(receipt)
        self.assertFalse(res["pass"])
        self.assertIn("s2", res["detail"])
        self.assertIn("FACES", res["repair_scope"])

    def test_sung_zero_on_sung_ad_fails(self):
        receipt = full_answered_receipt()
        receipt["SUNG"]["sung_pct"] = 0.0
        receipt["SUNG"]["spoken_pct"] = 100.0
        res = dc.evaluate(receipt)
        self.assertFalse(res["pass"])
        self.assertIn("SUNG", res["repair_scope"])

    # ---- G3-WIRE: sung claims flow through core/singing_detector --------
    def test_q1_detector_must_be_the_singing_detector(self):
        """A named-but-wrong instrument (labels) is the fake-number path."""
        for bad in ("section labels", "verse/chorus time", "manual listen",
                    "vocal-stem astats"):
            receipt = full_answered_receipt()
            receipt["SUNG"]["detector"] = bad
            res = dc.evaluate(receipt)
            self.assertFalse(res["pass"], bad)
            self.assertIn("SUNG", res["repair_scope"], bad)

    def test_q1_accepts_every_singing_detector_spelling(self):
        for good in ("singing_detector", "singing-detector(vocal-stem)",
                     "singing detector v2.0.0", "SingingDetector"):
            receipt = full_answered_receipt()
            receipt["SUNG"]["detector"] = good
            res = dc.evaluate(receipt)
            self.assertTrue(res["pass"], (good, res["detail"]))

    def test_q1_share_source_must_be_measured(self):
        receipt = full_answered_receipt()
        receipt["SUNG"]["share_source"] = "planned"
        res = dc.evaluate(receipt)
        self.assertFalse(res["pass"])
        self.assertIn("SUNG", res["repair_scope"])

    def test_q9_detector_must_be_the_singing_detector(self):
        receipt = full_answered_receipt()
        receipt["FIRST_SUNG"]["detector"] = "section labels"
        res = dc.evaluate(receipt)
        self.assertFalse(res["pass"])
        self.assertIn("FIRST_SUNG", res["repair_scope"])

    def test_music_broken_fails(self):
        receipt = full_answered_receipt()
        receipt["VOICE_MUSIC"]["music_gaps_s"] = 2.5
        receipt["VOICE_MUSIC"]["music_unbroken"] = False
        res = dc.evaluate(receipt)
        self.assertFalse(res["pass"])
        self.assertIn("VOICE_MUSIC", res["repair_scope"])

    def test_bad_receipt_fails_closed(self):
        with self.assertRaises(dc.ChecklistError):
            dc.evaluate("not-a-receipt")
        with self.assertRaises(dc.ChecklistError):
            dc.evaluate(None)

    # ---- H11: Q8-Q11 --------------------------------------------------
    def test_h11_q8_shifted_clip_fails_good_passes(self):
        receipt = full_answered_receipt()
        self.assertTrue(dc.evaluate(receipt)["pass"])
        receipt["LIP_SYNC"]["clips"][1]["offset_s"] = 0.20     # shifted
        res = dc.evaluate(receipt)
        self.assertEqual(res["repair_scope"], ["LIP_SYNC"])
        self.assertIn("ls2", res["detail"])
        self.assertIn("0.200s", res["detail"])

    def test_h11_q8_control_gap_and_frozen_face_fail(self):
        for k, v in (("control_correlation", 0.50), ("frozen_s", 1.0),
                     ("correlation", 0.40)):
            receipt = full_answered_receipt()
            receipt["LIP_SYNC"]["clips"][0][k] = v
            self.assertEqual(dc.evaluate(receipt)["repair_scope"],
                             ["LIP_SYNC"], k)

    def test_h11_q9_first_sung_band(self):
        for pct, want in ((10.0, "ACCEPT"), (20.0, "ACCEPT"),
                          (23.0, "ACCEPT_WITH_FLAG")):
            r = full_answered_receipt()
            r["FIRST_SUNG"]["first_sung_pct"] = pct
            r["GOALS_BAND"]["goals"][3]["measured"] = 15.0   # keep Q11 clean
            res = dc.evaluate(r)
            self.assertTrue(res["pass"], (pct, res["detail"]))
            self.assertEqual(res["evidence"]["first_sung_band"], want)
        r = full_answered_receipt()
        r["FIRST_SUNG"]["first_sung_pct"] = 3.3     # Kiesett v3: late
        res = dc.evaluate(r)
        self.assertEqual(res["repair_scope"], ["FIRST_SUNG"])
        r["FIRST_SUNG"].pop("detector")
        self.assertFalse(dc.evaluate(r)["pass"])    # no label-only answers

    def test_h11_q10_mismatched_shot_or_slowmo_fails(self):
        r = full_answered_receipt()
        r["PICTURES_MATCH"]["shots"][1]["match"] = False
        res = dc.evaluate(r)
        self.assertEqual(res["repair_scope"], ["PICTURES_MATCH"])
        self.assertIn("s2", res["detail"])
        r = full_answered_receipt()
        r["PICTURES_MATCH"]["shots"][0]["slowdown"] = 1.26
        self.assertEqual(dc.evaluate(r)["repair_scope"], ["PICTURES_MATCH"])
        r = full_answered_receipt()
        del r["PICTURES_MATCH"]["shots"][0]["line"]
        self.assertEqual(dc.evaluate(r)["repair_scope"], ["PICTURES_MATCH"])

    def test_h11_band_edges(self):
        self.assertEqual(dc.band(5.0), "ACCEPT")
        self.assertEqual(dc.band(5.1), "ACCEPT_WITH_FLAG")
        self.assertEqual(dc.band(10.0), "ACCEPT_WITH_FLAG")
        self.assertEqual(dc.band(10.1), "REDO")

    def test_h11_q11_flag_must_be_shown_and_over_10_redone(self):
        r = full_answered_receipt()
        del r["GOALS_BAND"]["goals"][3]["flag"]       # 6 off, no flag shown
        res = dc.evaluate(r)
        self.assertEqual(res["repair_scope"], ["GOALS_BAND"])
        self.assertIn("no flag", res["detail"])
        r = full_answered_receipt()
        r["GOALS_BAND"]["goals"][0]["measured"] = 71.5   # 11.5 off: redo
        res = dc.evaluate(r)
        self.assertEqual(res["repair_scope"], ["GOALS_BAND"])
        self.assertIn("redo", res["detail"])
        self.assertEqual(res["evidence"]["goals_flagged"], 1)

    def test_h11_q2_uses_band_flag_ok_redo_fails(self):
        r = full_answered_receipt()
        r["ON_TARGET"]["shares"]["spoken"]["measured_pct"] = 52.0   # 7 off
        res = dc.evaluate(r)
        self.assertTrue(res["pass"], res["detail"])
        self.assertTrue(res["evidence"]["on_target_flags"])
        r["ON_TARGET"]["shares"]["spoken"]["measured_pct"] = 56.0   # 11 off
        self.assertEqual(dc.evaluate(r)["repair_scope"], ["ON_TARGET"])

    # ---- gate wiring ------------------------------------------------------
    def test_record_wires_into_shared_gate(self):
        res = dc.evaluate(full_answered_receipt())
        rec = dc.to_qc_record(res, RUN, STAGE, REVIEWER)
        self.assertEqual(rec["check"], "delivery_checklist")
        self.assertEqual(rec["schema_version"], "1.0.0")
        err = qc_gate.validate_record(rec)
        self.assertIsNone(err, err)
        gate = qc_gate.evaluate(RUN, STAGE, [rec, final_edit_record()],
                                MAKERS, FINAL_GATE_REQUIRED, master={"chosen_length_s": 60, "measured_s": 58})
        self.assertEqual(gate["gate"], "PASS", gate["failures"])

    def test_final_edit_gate_4_requires_the_checklist(self):
        # gate 4 "Final" wiring: when delivery_checklist is required (the
        # G7 final gate row), a run without its record cannot advance.
        # A missing checker run is structural (BLOCKED: no record repair
        # can pass it); a FAIL *inside* the record is targeted FAIL.
        gate = qc_gate.evaluate(RUN, STAGE, [final_edit_record()], MAKERS,
                                FINAL_GATE_REQUIRED)
        self.assertEqual(gate["gate"], "BLOCKED")
        codes = {f["code"] for f in gate["failures"]}
        self.assertIn("MISSING_QC", codes)

    def test_fail_record_fails_final_stage(self):
        receipt = full_answered_receipt()
        del receipt["MODELS"]
        res = dc.evaluate(receipt)
        rec = dc.to_qc_record(res, RUN, STAGE, REVIEWER)
        gate = qc_gate.evaluate(RUN, STAGE, [rec, final_edit_record()],
                                MAKERS, FINAL_GATE_REQUIRED, master={"chosen_length_s": 60, "measured_s": 58})
        self.assertEqual(gate["gate"], "FAIL")
        self.assertIn(dc.CHECK_ID, gate["repair_scope"])

    def test_maker_self_review_still_refused(self):
        res = dc.evaluate(full_answered_receipt())
        rec = dc.to_qc_record(res, RUN, STAGE, REVIEWER)
        makers = {dc.CHECK_ID: REVIEWER["identity"],
                  "final-edit-e2e": "final_qc/1.0.0"}
        gate = qc_gate.evaluate(RUN, STAGE, [rec, final_edit_record()],
                                makers, FINAL_GATE_REQUIRED)
        self.assertEqual(gate["gate"], "BLOCKED")
        codes = {f["code"] for f in gate["failures"]}
        self.assertIn("MAKER_SELF_REVIEW", codes)

    # ---- checklist ships verbatim -----------------------------------------
    def test_checklist_file_verbatim(self):
        shipped = _SKILL / "references" / "QC-CHECKLIST-BEFORE-DELIVERY.md"
        self.assertTrue(shipped.is_file(), str(shipped))
        text = shipped.read_text(encoding="utf-8")
        for marker in ("SUNG?", "ON TARGET?", "WORDS?", "FACES?",
                       "VOICE + MUSIC?", "MODELS?", "HONEST RECEIPT?",
                       "LIP-SYNC MEASURED?", "FIRST SUNG?",
                       "PICTURES MATCH THE WORDS?",
                       "JUDGED BY TREVOR'S BAND?",
                       'A "yes" without a measurement counts as "no"'):
            self.assertIn(marker, text)
        self.assertEqual(len(dc.QUESTIONS), 11)

    # ---- CLI round trip (temp home, no operator paths) ---------------------
    def test_cli_round_trip(self):
        with tempfile.TemporaryDirectory() as td:
            receipt = full_answered_receipt()
            rp = os.path.join(td, "receipt.json")
            with open(rp, "w", encoding="utf-8") as f:
                json.dump(receipt, f)
            p = subprocess.run(
                [sys.executable, str(_HERE / "delivery_checklist.py"),
                 "check", "--receipt", rp],
                capture_output=True, text=True,
                env={"HOME": td, "PATH": "/usr/bin:/bin"})
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            out = json.loads(p.stdout)
            self.assertEqual(out["outcome"], "ok")
            # failing receipt: exit 5, redo directive names only that part
            del receipt["WORDS"]
            with open(rp, "w", encoding="utf-8") as f:
                json.dump(receipt, f)
            p = subprocess.run(
                [sys.executable, str(_HERE / "delivery_checklist.py"),
                 "check", "--receipt", rp],
                capture_output=True, text=True,
                env={"HOME": td, "PATH": "/usr/bin:/bin"})
            self.assertEqual(p.returncode, 5, p.stdout + p.stderr)
            out = json.loads(p.stdout)
            self.assertEqual(out["repair_scope"], ["WORDS"])
            # gate record path
            qp = os.path.join(td, "rec.json")
            p = subprocess.run(
                [sys.executable, str(_HERE / "delivery_checklist.py"),
                 "check", "--receipt", rp, "--qc-record", qp,
                 "--run-id", RUN, "--stage", STAGE,
                 "--reviewer-identity", REVIEWER["identity"],
                 "--reviewer-session", REVIEWER["session"],
                 "--reviewer-authority", REVIEWER["authority"]],
                capture_output=True, text=True,
                env={"HOME": td, "PATH": "/usr/bin:/bin"})
            self.assertEqual(p.returncode, 5, p.stdout + p.stderr)
            rec = json.loads(Path(qp).read_text(encoding="utf-8"))
            err = qc_gate.validate_record(rec)
            self.assertIsNone(err, err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
