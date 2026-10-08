#!/usr/bin/env python3
"""E7 tests for sung_vocal_guard (manual 02 Part E E7, Critical).

stdlib only, zero paid calls, no ffmpeg binary required (the scan path is
exercised through the pure parsers over canned stderr text).

Acceptance proven (floor amended to 55 % per Addendum 3 / Decision 39):
  timing map with 75% sung coverage              -> PASS
  timing map with 55% sung coverage (the floor)  -> PASS
  voiceover-only master (0% sung)                -> FAIL VOCAL_MISSING
  50% sung coverage                              -> FAIL SUNG_COVERAGE_LOW
  Velvet profile with a song bed present         -> PASS
plus the gate wiring: the record rides qc_gate.validate_record/evaluate.

Run: python3 core/final_assembler/test_sung_vocal_e7.py
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import sung_vocal_guard as SVG                      # noqa: E402
import qc_gate                                      # noqa: E402

RUN_ID = "e7-run"
STAGE = "final_edit"
MAKER = "final_assembler-maker"
REVIEWER = "independent-qc-checker"


def _timing(sung_s, total=60.0):
    """12.4 map with exactly ``sung_s`` seconds of sung line windows.

    Timing-map lines ARE sung lines (planner 12.4 lyric windows); a gap in
    the map means no line covers it -- E8 lays spoken lines over the bed
    OUTSIDE the sung windows, so a sung/blank split is the honest fixture.
    """
    secs = [{"section_id": "verse-1", "lyrics": [
        {"line_id": "L1", "start": 0.0, "end": round(sung_s, 3),
         "text": "sung words carry the song"}]}] if sung_s > 0 \
        else [{"section_id": "verse-1", "lyrics": []}]  # valid map, 0 sung
    return {"song_id": "song-e7", "duration_seconds": total,
            "sections": secs}


class SungVocalE7(unittest.TestCase):

    # ------------------------------------------------------- acceptance ---
    def test_timing_map_75pct_passes(self):
        out = SVG.check_sung_vocal(timing=_timing(45.0, 60.0),
                                   profile="all_suno")
        self.assertEqual(out["outcome"], "PASS")
        self.assertEqual(out["reason_code"], "SUNG_COVERAGE_OK")
        self.assertAlmostEqual(out["sung_coverage"], 0.75, places=3)

    def test_timing_map_55pct_floor_passes(self):
        """E7 amended (Decision 39): floor 55% -- a 55% master now passes."""
        self.assertEqual(SVG.MIN_SUNG_COVERAGE, 0.55)
        out = SVG.check_sung_vocal(timing=_timing(33.0, 60.0),
                                   profile="all_suno")
        self.assertEqual(out["outcome"], "PASS")
        self.assertEqual(out["reason_code"], "SUNG_COVERAGE_OK")
        self.assertAlmostEqual(out["sung_coverage"], 0.55, places=3)

    def test_voiceover_only_master_fails_vocal_missing(self):
        out = SVG.check_sung_vocal(timing=_timing(0.0, 60.0),
                                   profile="all_suno")
        self.assertEqual(out["outcome"], "FAIL")
        self.assertEqual(out["reason_code"], "VOCAL_MISSING")

    def test_50pct_fails_sung_coverage_low(self):
        """E7 amended (Decision 39): 50% stays below the 55% floor."""
        out = SVG.check_sung_vocal(timing=_timing(30.0, 60.0),
                                   profile="all_suno")
        self.assertEqual(out["outcome"], "FAIL")
        self.assertEqual(out["reason_code"], "SUNG_COVERAGE_LOW")

    def test_velvet_profile_with_song_bed_passes(self):
        out = SVG.check_sung_vocal(timing=_timing(20.0, 60.0),
                                   profile="velvet_voiceover")
        self.assertEqual(out["outcome"], "PASS")
        self.assertEqual(out["reason_code"], "VELVET_BED_PRESENT")

    def test_velvet_without_bed_fails_vocal_missing(self):
        out = SVG.check_sung_vocal(timing=_timing(0.0, 60.0),
                                   profile="velvet_voiceover")
        self.assertEqual(out["outcome"], "FAIL")
        self.assertEqual(out["reason_code"], "VOCAL_MISSING")

    # ------------------------------------------------- secondary (scan) ---
    def test_scan_absent_audio_fails_vocal_missing(self):
        out = SVG.check_sung_vocal(
            profile="all_suno",
            scan_stderr="I:  -71.0 LUFS")
        self.assertEqual(out["outcome"], "FAIL")
        self.assertEqual(out["reason_code"], "VOCAL_MISSING")

    def test_scan_energy_present_passes_all_suno(self):
        out = SVG.check_sung_vocal(
            profile="all_suno",
            scan_stderr="[Parsed_ebur128_0] I: -14.2 LUFS")
        self.assertEqual(out["outcome"], "PASS")
        self.assertEqual(out["reason_code"], "SUNG_COVERAGE_OK")
        self.assertEqual(out["evidence_path"], "vocal_presence")

    def test_no_evidence_at_all_is_unavailable(self):
        out = SVG.check_sung_vocal(profile="all_suno", timing=None)
        self.assertEqual(out["outcome"], "UNAVAILABLE")
        self.assertEqual(out["reason_code"], "NO_EVIDENCE")

    # ------------------------------------------------------- pure parse ---
    def test_parse_ebur128_last_i_wins(self):
        txt = ("[Parsed_ebur128_0] t: 1.0 TARGET:-23 LUFS "
               "M: -18.5 S: -19.1 I: -17.9 LUFS\n"
               "[Parsed_ebur128_0] Summary: Integrated loudness:\n"
               "I:         -13.6 LUFS")
        self.assertEqual(SVG.parse_ebur128(txt), -13.6)
        self.assertIsNone(SVG.parse_ebur128("no numbers here"))

    def test_parse_astats_rms_values(self):
        txt = ("Rms level dB:       -12.3\n"
               "Rms level dB:       -35.7")
        self.assertEqual(SVG.parse_astats(txt), [-12.3, -35.7])
        self.assertEqual(SVG.parse_astats(""), [])

    def test_vocal_presence_threshold(self):
        self.assertTrue(SVG.vocal_presence(
            "Rms level dB: -14.0\nRms level dB: -18.2", floor_lufs=-70))
        self.assertFalse(SVG.vocal_presence(
            "Rms level dB: -80.0", floor_lufs=-70))

    # ------------------------------------------------- mode resolution ----
    def test_mode_from_intake_style_record(self):
        mode, deflt = SVG.resolve_voice_mode(
            {"voice": "all_suno", "length": "60"})
        self.assertEqual((mode, deflt), ("all_suno", False))

    def test_mode_from_card_slug(self):
        mode, _ = SVG.resolve_voice_mode({"voice": "velvet-voiceover"})
        self.assertEqual(mode, "velvet_voiceover")

    def test_mode_nested_style(self):
        mode, _ = SVG.resolve_voice_mode({"style": {"voice": "Velvet Echo"}})
        self.assertEqual(mode, "velvet_voiceover")

    def test_mode_absent_defaults_all_suno(self):
        mode, deflt = SVG.resolve_voice_mode({})
        self.assertEqual((mode, deflt), ("all_suno", True))
        mode, deflt = SVG.resolve_voice_mode(None)
        self.assertEqual((mode, deflt), ("all_suno", True))

    def test_mode_unknown_refused(self):
        with self.assertRaisesRegex(SVG.SungGuardError, "VOICE_MODE_UNKNOWN"):
            SVG.resolve_voice_mode({"voice": "robot"})
        with self.assertRaisesRegex(SVG.SungGuardError, "VOICE_MODE_UNKNOWN"):
            SVG.resolve_voice_mode({"voice": "whispered-speech"})

    # ------------------------------------------------- spoken exclusion ---
    def test_spoken_sections_excluded_from_sung_sum(self):
        timing = {"song_id": "s", "duration_seconds": 60.0,
                  "sections": [
                      {"section_id": "verse-1", "lyrics": [
                          {"line_id": "L1", "start": 0.0, "end": 40.0,
                           "text": "sung"}]},
                      {"section_id": "spoken-line-1", "lyrics": [
                          {"line_id": "L2", "start": 40.0, "end": 50.0,
                           "text": "spoken"}]}]}
        ratio, _ = SVG.sung_coverage_from_timing(
            timing, spoken_section_ids=["spoken-line-1"])
        self.assertAlmostEqual(ratio, 40.0 / 60.0, places=3)

    def test_bad_timing_is_unavailable_not_vocal_missing(self):
        out = SVG.check_sung_vocal(timing={"no": "map"}, profile="all_suno")
        self.assertEqual(out["outcome"], "UNAVAILABLE")
        self.assertEqual(out["reason_code"], "TIMING_UNREADABLE")

    # ------------------------------------------------- gate wiring (QC) ---
    def test_pass_record_validates_and_gate_passes(self):
        ver = SVG.check_sung_vocal(timing=_timing(45.0, 60.0),
                                   profile="all_suno")
        rec = SVG.record_for_gate(ver, RUN_ID, STAGE, REVIEWER,
                                  "sess-e7", "qc-checker")
        self.assertIsNone(qc_gate.validate_record(rec))
        res = qc_gate.evaluate(
            RUN_ID, STAGE, [rec], {"final:audio:sung_vocal": MAKER},
            ["audio"])
        self.assertEqual(res["gate"], "PASS")

    def test_fail_record_fails_final_edit_gate(self):
        ver = SVG.check_sung_vocal(timing=_timing(0.0, 60.0),
                                   profile="all_suno")
        rec = SVG.record_for_gate(ver, RUN_ID, STAGE, REVIEWER,
                                  "sess-e7", "qc-checker")
        self.assertIsNone(qc_gate.validate_record(rec))
        self.assertEqual(rec["verdict"], "FAIL")
        res = qc_gate.evaluate(
            RUN_ID, STAGE, [rec], {"final:audio:sung_vocal": MAKER},
            ["audio"])
        self.assertEqual(res["gate"], "FAIL")
        self.assertTrue(
            any("VOCAL_MISSING" in f["detail"] for f in res["failures"]))

    def test_fail_record_fails_when_audio_required_for_final_edit(self):
        """Wiring: audio rides the 17.5 Final edit required set."""
        ver = SVG.check_sung_vocal(timing=_timing(30.0, 60.0),
                                   profile="all_suno")
        rec = SVG.record_for_gate(ver, RUN_ID, "final", REVIEWER,
                                  "sess-e7", "qc-checker")
        self.assertIsNone(qc_gate.validate_record(rec))
        # Sibling 17.5 checks ride as their own PASS records (independent
        # reviewers); the sung-vocal FAIL must flip the whole gate to FAIL
        # with repair_scope carrying ONLY the sung-vocal record. BLOCKED
        # (structural) would mean the record never joined the gate's audio
        # bucket -- the exact wiring defect this test exists to catch.
        ver_ok = SVG.check_sung_vocal(timing=_timing(45.0, 60.0),
                                      profile="all_suno")
        ok = SVG.record_for_gate(ver_ok, RUN_ID, "final", REVIEWER,
                                 "sess-e7", "qc-checker")

        def sibling(check_id, check):
            r = dict(ok)
            r["check_id"], r["check"] = check_id, check
            r["evidence"] = {"summary": "pass fixture (%s)" % check}
            return r

        records = [rec,
                   sibling("x:export", "export"),
                   sibling("x:timeline", "timeline"),
                   sibling("x:final_edit", "final_edit")]
        res = qc_gate.evaluate(
            RUN_ID, "final", records,
            {"final:audio:sung_vocal": MAKER, "x:export": MAKER,
             "x:timeline": MAKER, "x:final_edit": MAKER},
            ["final_edit", "export", "timeline", "audio"])
        self.assertEqual(res["gate"], "FAIL")
        self.assertEqual(res["repair_scope"], ["final:audio:sung_vocal"])

    def test_maker_cannot_self_review_the_guard_record(self):
        rec = {"schema_version": "1.0.0", "check_id": "final:audio:sung_vocal",
               "run_id": RUN_ID, "stage": STAGE, "check": "audio",
               "verdict": "PASS",
               "evidence": {"summary": "made and judged by the same agent"},
               "checker_version": SVG.TOOL_VERSION,
               "reviewer": {"identity": MAKER, "session": "sess-e7",
                            "authority": "qc-checker"}}
        res = qc_gate.evaluate(
            RUN_ID, STAGE, [rec], {"final:audio:sung_vocal": MAKER},
            ["audio"])
        self.assertEqual(res["gate"], "BLOCKED")
        self.assertTrue(
            any(f["code"] == "MAKER_SELF_REVIEW" for f in res["failures"]))

    def test_covered_ratio_capped_at_one(self):
        ratio, _ = SVG.sung_coverage_from_timing(_timing(90.0, 60.0))
        self.assertLessEqual(ratio, 1.0)

    # -------------------------------------- H8: ONE rule, Trevor's band ---
    def test_h8_within_5_points_accepts_without_flag(self):
        out = SVG.check_sung_vocal(timing=_timing(39.0, 60.0),   # 65% vs 70
                                   profile="all_suno")
        self.assertEqual((out["outcome"], out["flags"]), ("PASS", []))

    def test_h8_5_to_10_points_accepts_with_flag(self):
        out = SVG.check_sung_vocal(timing=_timing(36.0, 60.0),   # 60% vs 70
                                   profile="all_suno")
        self.assertEqual(out["outcome"], "PASS")
        self.assertEqual(len(out["flags"]), 1)
        rec = SVG.record_for_gate(out, "r1", "final", "qc", "s1", "auth")
        self.assertIn("FLAG", rec["evidence"]["summary"])

    def test_h8_past_10_points_is_redo(self):
        out = SVG.check_sung_vocal(timing=_timing(30.0, 60.0),   # 50% vs 70
                                   profile="all_suno")
        self.assertEqual((out["outcome"], out["reason_code"]),
                         ("FAIL", "SUNG_COVERAGE_LOW"))

    def test_h8_no_6s_stretch_is_the_hard_reject(self):
        out = SVG.check_sung_vocal(timing=_timing(5.0, 60.0),
                                   profile="all_suno")
        self.assertEqual((out["outcome"], out["reason_code"]),
                         ("FAIL", "VOCAL_MISSING"))
        self.assertIn("no real singing", out["next_action"])

    def test_h8_guard_uses_the_shared_constants(self):
        self.assertIs(SVG._SS.NO_REAL_SINGING_STRETCH_S,
                      SVG._SS.NO_REAL_SINGING_STRETCH_S)
        self.assertEqual(SVG._SS.ACCEPT_PTS, 5)
        self.assertEqual(SVG._SS.FLAG_PTS, 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)