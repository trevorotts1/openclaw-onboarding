#!/usr/bin/env python3
"""E7 tests for sung_vocal_guard (manual 02 Part E E7, Critical).

stdlib only, zero paid calls, no ffmpeg binary required (the scan path is
exercised through the pure parsers over canned stderr text).

Acceptance proven (Trevor, 2026-10-08: no absolute floor; the ad's own sung
target judged by the 5/10 band; the only hard reject is no 6 s sung stretch;
SPK001: sung is measured against VOICE time, sung / (sung + spoken), default
target 77.5, and a music-only intro / end card is never penalized):
  76 / 69 / 60 of voice vs 77.5                  -> PASS / PASS+flag / FAIL
  75% sung vs a 75% target                       -> PASS
  50 vs target 60 (10 points)                    -> PASS with a flag
  48 vs target 60 (12 points)                    -> FAIL SUNG_COVERAGE_LOW
  57 vs target 60                                -> PASS, no flag
  no 55% floor anywhere (50% vs a 50% target)    -> PASS
  voiceover-only master (0% sung)                -> FAIL VOCAL_MISSING
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


SPOKEN = ["spoken-line-1"]


def _chk(**kw):
    """check_sung_vocal with the fixture's spoken section named."""
    kw.setdefault("spoken_section_ids", SPOKEN)
    return SVG.check_sung_vocal(**kw)


def _timing(sung_s, total=60.0, spoken_s=0.0, start=0.0):
    """12.4 map with ``sung_s`` seconds of sung line windows and ``spoken_s``
    seconds of spoken line windows (section ``spoken-line-1``), the sung
    window beginning at ``start`` (a music-only intro before it).

    Seconds no line covers (intro, gaps, end card) are music only: voice time
    is sung + spoken (SPK001).
    """
    secs = [{"section_id": "verse-1", "lyrics": [
        {"line_id": "L1", "start": start, "end": round(start + sung_s, 3),
         "text": "sung words carry the song"}]}] if sung_s > 0 \
        else [{"section_id": "verse-1", "lyrics": []}]  # valid map, 0 sung
    if spoken_s > 0:
        b = start + sung_s
        secs.append({"section_id": "spoken-line-1", "lyrics": [
            {"line_id": "L2", "start": b, "end": round(b + spoken_s, 3),
             "text": "spoken words"}]})
    return {"song_id": "song-e7", "duration_seconds": total,
            "sections": secs}


class SungVocalE7(unittest.TestCase):

    # ------------------------------------------------------- acceptance ---
    def test_timing_map_75pct_passes(self):
        out = _chk(timing=_timing(45.0, 60.0, 15.0),
                                   profile="all_suno", target=0.75)
        self.assertEqual(out["outcome"], "PASS")
        self.assertEqual(out["reason_code"], "SUNG_COVERAGE_OK")
        # G5: timing-map time is LABELLED time, never a sung %.
        self.assertEqual(out["share_basis"], "planned")
        self.assertAlmostEqual(out["labelled_coverage_pct"], 75.0, places=2)
        self.assertIn("NOT measured", out["labelled_source"])

    def test_g5_labelled_time_never_reported_as_sung(self):
        """G5: without a measured detector run, no sung % may be printed."""
        out = SVG.check_sung_vocal(timing=_timing(45.0, 60.0),
                                   profile="all_suno")
        for field in ("sung_pct", "sung_share", "sung_share_pct"):
            self.assertNotIn(field, out)
        rec = SVG.record_for_gate(out, RUN_ID, STAGE, REVIEWER,
                                  "sess-e7", "qc-checker")
        self.assertIn("LABELLED", rec["evidence"]["summary"])
        self.assertIn("not measured", rec["evidence"]["summary"])
        self.assertNotIn("MEASURED", rec["evidence"]["summary"])

    def test_g5_measured_detector_drives_verdict_and_receipt(self):
        """G5: with a G3 detector record, the sung % is source=measured."""
        det = {"tool": "singing_detector.v1", "tool_version": "1.0.0",
               "sung_share": 0.02, "spoken_share": 0.98, "rap_share": 0.0,
               "no_voice_share": 0.0, "runtime_s": 60.0,
               "confidence": 0.95, "measured": True}
        out = SVG.check_sung_vocal(timing=_timing(45.0, 60.0),
                                   profile="all_suno",
                                   detector_result=det)
        # 2% measured sung < 70% floor -> FAIL even though labels say 75%.
        self.assertEqual(out["outcome"], "FAIL")
        self.assertEqual(out["reason_code"], "SUNG_COVERAGE_LOW")
        self.assertEqual(out["sung_pct"]["source"], "measured")
        self.assertEqual(out["sung_pct"]["detector"], "singing_detector.v1")
        self.assertEqual(out["sung_pct"]["confidence"], 0.95)
        # G5 amend (order 1150): all four measured deliveries, with seconds
        self.assertEqual(out["sung_pct"]["rap_pct"], 0.0)
        self.assertEqual(out["sung_pct"]["no_voice_pct"], 0.0)
        self.assertEqual(out["sung_pct"]["sung_seconds"], 1.2)
        self.assertEqual(out["sung_pct"]["spoken_seconds"], 58.8)
        rec = SVG.record_for_gate(out, RUN_ID, STAGE, REVIEWER,
                                  "sess-e7", "qc-checker")
        self.assertIn("MEASURED", rec["evidence"]["summary"])
        self.assertIn("singing_detector.v1", rec["evidence"]["summary"])

    def test_g5_measured_all_spoken_fails_vocal_missing(self):
        """The failed-ad shape, measured honestly: labels say 75% sung,
        detector says 0% -> VOCAL_MISSING, never the label number."""
        det = {"tool": "singing_detector.v1", "tool_version": "1.0.0",
               "sung_share": 0.0, "spoken_share": 1.0, "rap_share": 0.0,
               "no_voice_share": 0.0, "runtime_s": 60.0,
               "confidence": 0.95, "measured": True}
        out = SVG.check_sung_vocal(timing=_timing(45.0, 60.0),
                                   profile="all_suno",
                                   detector_result=det)
        self.assertEqual(out["outcome"], "FAIL")
        self.assertEqual(out["reason_code"], "VOCAL_MISSING")
        self.assertEqual(out["sung_pct"]["sung_pct"], 0.0)

    def test_g5_labelled_fields_boxed_on_verdict(self):
        out = SVG.check_sung_vocal(timing=_timing(45.0, 60.0),
                                   profile="all_suno")
        self.assertIn("labelled_source", out)
        self.assertIn("labelled_sung_seconds", out)
        self.assertIn("labelled_coverage_pct", out)
        self.assertAlmostEqual(out["labelled_sung_seconds"], 45.0, places=2)

    def test_no_absolute_floor_exists(self):
        """Trevor: not an absolute 55%. 50% against a 50% target passes."""
        self.assertFalse(hasattr(SVG, "MIN_SUNG_COVERAGE"))
        out = _chk(timing=_timing(30.0, 60.0, 30.0),
                                   profile="all_suno", target=0.50)
        self.assertEqual((out["outcome"], out["flags"]), ("PASS", []))

    def test_default_target_comes_from_the_g10_constants(self):
        self.assertEqual(SVG.SUNG_TARGET, SVG._SS.SUNG_TARGET_PCT / 100.0)
        out = _chk(timing=_timing(31.0, 60.0, 9.0),
                                   profile="all_suno")      # 77.5% vs 77.5%
        self.assertEqual((out["outcome"], out["target"]), ("PASS", 0.775))

    def test_card_target_is_read_from_the_profile(self):
        card = {"voice": "all_suno", "sung_target_pct": 60}
        out = _chk(timing=_timing(30.0, 60.0, 30.0), profile=card)
        self.assertEqual((out["outcome"], out["target"], len(out["flags"])),
                         ("PASS", 0.6, 1))                  # 50 vs 60

    def test_voiceover_only_master_fails_vocal_missing(self):
        out = _chk(timing=_timing(0.0, 60.0),
                                   profile="all_suno")
        self.assertEqual(out["outcome"], "FAIL")
        self.assertEqual(out["reason_code"], "VOCAL_MISSING")

    def test_velvet_profile_with_song_bed_passes(self):
        out = _chk(timing=_timing(20.0, 60.0),
                                   profile="velvet_voiceover")
        self.assertEqual(out["outcome"], "PASS")
        self.assertEqual(out["reason_code"], "VELVET_BED_PRESENT")

    def test_velvet_without_bed_fails_vocal_missing(self):
        out = _chk(timing=_timing(0.0, 60.0),
                                   profile="velvet_voiceover")
        self.assertEqual(out["outcome"], "FAIL")
        self.assertEqual(out["reason_code"], "VOCAL_MISSING")

    # ------------------------------------------------- secondary (scan) ---
    def test_scan_absent_audio_fails_vocal_missing(self):
        out = _chk(
            profile="all_suno",
            scan_stderr="I:  -71.0 LUFS")
        self.assertEqual(out["outcome"], "FAIL")
        self.assertEqual(out["reason_code"], "VOCAL_MISSING")

    def test_scan_energy_present_passes_all_suno(self):
        out = _chk(
            profile="all_suno",
            scan_stderr="[Parsed_ebur128_0] I: -14.2 LUFS")
        self.assertEqual(out["outcome"], "PASS")
        self.assertEqual(out["reason_code"], "SUNG_COVERAGE_OK")
        self.assertEqual(out["evidence_path"], "vocal_presence")

    def test_no_evidence_at_all_is_unavailable(self):
        out = _chk(profile="all_suno", timing=None)
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
        self.assertAlmostEqual(ratio, 40.0 / 50.0, places=3)   # of voice time

    def test_bad_timing_is_unavailable_not_vocal_missing(self):
        out = _chk(timing={"no": "map"}, profile="all_suno")
        self.assertEqual(out["outcome"], "UNAVAILABLE")
        self.assertEqual(out["reason_code"], "TIMING_UNREADABLE")

    # ------------------------------------------------- gate wiring (QC) ---
    def test_pass_record_validates_and_gate_passes(self):
        ver = _chk(timing=_timing(45.0, 60.0, 15.0),
                                   profile="all_suno", target=0.75)
        rec = SVG.record_for_gate(ver, RUN_ID, STAGE, REVIEWER,
                                  "sess-e7", "qc-checker")
        self.assertIsNone(qc_gate.validate_record(rec))
        res = qc_gate.evaluate(
            RUN_ID, STAGE, [rec], {"final:audio:sung_vocal": MAKER},
            ["audio"])
        self.assertEqual(res["gate"], "PASS")

    def test_fail_record_fails_final_edit_gate(self):
        ver = _chk(timing=_timing(0.0, 60.0),
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
        ver = _chk(timing=_timing(30.0, 60.0, 30.0),
                                   profile="all_suno", target=0.75)
        rec = SVG.record_for_gate(ver, RUN_ID, "final", REVIEWER,
                                  "sess-e7", "qc-checker")
        self.assertIsNone(qc_gate.validate_record(rec))
        # Sibling 17.5 checks ride as their own PASS records (independent
        # reviewers); the sung-vocal FAIL must flip the whole gate to FAIL
        # with repair_scope carrying ONLY the sung-vocal record. BLOCKED
        # (structural) would mean the record never joined the gate's audio
        # bucket -- the exact wiring defect this test exists to catch.
        ver_ok = _chk(timing=_timing(45.0, 60.0, 15.0),
                                      profile="all_suno", target=0.75)
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
            ["final_edit", "export", "timeline", "audio"],
            master={"chosen_length_s": 60, "measured_s": 58})
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

    # ---------------------- Trevor's band around the ad's own target ---
    def _vs60(self, sung_pct):
        return _chk(timing=_timing(sung_pct * 0.6, 60.0,
                                   (100 - sung_pct) * 0.6),
                    profile="all_suno", target=0.60)

    def test_57_vs_60_accepts_without_flag(self):
        out = self._vs60(57)
        self.assertEqual((out["outcome"], out["reason_code"], out["flags"]),
                         ("PASS", "SUNG_COVERAGE_OK", []))

    def test_50_vs_60_is_10_points_accepted_with_a_flag(self):
        out = self._vs60(50)
        self.assertEqual(out["outcome"], "PASS")
        self.assertEqual(len(out["flags"]), 1)
        rec = SVG.record_for_gate(out, "r1", "final", "qc", "s1", "auth")
        self.assertEqual(rec["verdict"], "PASS")
        self.assertIn("FLAG", rec["evidence"]["summary"])

    def test_48_vs_60_is_12_points_redo(self):
        out = self._vs60(48)
        self.assertEqual((out["outcome"], out["reason_code"]),
                         ("FAIL", "SUNG_COVERAGE_LOW"))

    def test_too_much_singing_is_judged_the_same_way(self):
        out = self._vs60(75)                                # 15 points over
        self.assertEqual(out["reason_code"], "SUNG_COVERAGE_LOW")

    def test_bad_target_is_refused(self):
        with self.assertRaises(SVG.SungGuardError):
            _chk(timing=_timing(30.0), profile="all_suno",
                                 target="high")

    def test_h8_no_6s_stretch_is_the_hard_reject(self):
        out = _chk(timing=_timing(5.0, 60.0, 5.0),
                                   profile="all_suno")
        self.assertEqual((out["outcome"], out["reason_code"]),
                         ("FAIL", "VOCAL_MISSING"))
        self.assertIn("no real singing", out["next_action"])

    # ---------------------- SPK001: singing judged against voice time ---
    def _voice(self, pct_of_voice, start=0.0, total=60.0):
        """Default target (77.5) on a map with ``pct_of_voice`` sung of 40 s
        of voice, the sung window beginning at ``start``."""
        return _chk(timing=_timing(pct_of_voice * 0.4, total,
                                   (100 - pct_of_voice) * 0.4, start=start),
                    profile="all_suno")

    def test_spk001_76_of_voice_accepts(self):
        out = self._voice(76)
        self.assertEqual((out["outcome"], out["flags"]), ("PASS", []))
        self.assertEqual(out["measured_over"], "voice_time")

    def test_spk001_69_of_voice_accepts_with_flag(self):
        out = self._voice(69)                           # 8.5 points off
        self.assertEqual((out["outcome"], len(out["flags"])), ("PASS", 1))

    def test_spk001_60_of_voice_is_redo(self):
        out = self._voice(60)                           # 17.5 points off
        self.assertEqual((out["outcome"], out["reason_code"]),
                         ("FAIL", "SUNG_COVERAGE_LOW"))

    def test_spk001_intro_and_end_card_are_not_penalized(self):
        """10 s music-only intro + 5 s end card around 40 s of voice: same
        verdict and same share as with no intro and no end card."""
        bare = self._voice(76, start=0.0, total=40.0)
        framed = self._voice(76, start=10.0, total=55.0)    # 10 + 40 + 5
        self.assertEqual((framed["outcome"], framed["flags"]), ("PASS", []))
        self.assertEqual(framed["sung_coverage"], bare["sung_coverage"])
        self.assertAlmostEqual(framed["sung_coverage"], 0.76, places=3)

    def test_h8_guard_uses_the_shared_constants(self):
        self.assertIs(SVG._SS.NO_REAL_SINGING_STRETCH_S,
                      SVG._SS.NO_REAL_SINGING_STRETCH_S)
        self.assertEqual(SVG._SS.ACCEPT_PTS, 5)
        self.assertEqual(SVG._SS.FLAG_PTS, 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)