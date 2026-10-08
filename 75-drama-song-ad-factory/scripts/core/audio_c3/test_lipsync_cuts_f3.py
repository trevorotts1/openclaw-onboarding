#!/usr/bin/env python3
"""F3 lipsync_cuts tests (unit W-F-U3, manual Part F F3, High).

Proves, mocked only (no network, zero paid calls):
  * cuts land on the timing map's line timestamps;
  * every cut cites the main track generation id as source;
  * a stem used outside lip-sync input fails STEM_IN_FINAL_MIX;
  * a lip-sync clip citing another source fails LIPSYNC_SOURCE_MISMATCH;
  * the stub analyzer reports 1 distinct voice and carries the
    multi-voice-UNRELIABLE / Trevor-decides note (probe 2026-10-08);
  * the real analyzer path refuses without a named track.

Run: python3 core/audio_c3/test_lipsync_cuts_f3.py
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import lipsync_cuts as LC  # noqa: E402  module under test


def _receipt(gid="gen-abc-1"):
    return {"soundtrack": {"primary_generation_id": gid, "mode": "one-generation"},
            "generation_id": gid}


def _map():
    return [
        {"line_id": "L1", "start_s": 1.0, "end_s": 3.5},
        {"line_id": "L2", "start_s": 4.0, "end_s": 7.25},
    ]


class CutPlanTests(unittest.TestCase):
    """cut_lipsync_lines: one source, timestamps from the map."""

    def test_cuts_land_on_line_timestamps(self):
        plan = LC.cut_lipsync_lines(_receipt(), _map())
        self.assertEqual(plan["cuts"]["L1"]["start_s"], 1.0)
        self.assertEqual(plan["cuts"]["L1"]["end_s"], 3.5)
        self.assertEqual(plan["cuts"]["L2"]["start_s"], 4.0)
        self.assertEqual(plan["cuts"]["L2"]["end_s"], 7.25)
        self.assertEqual(plan["stem_mix_role"], LC.STEM_MIX_ROLE)
        self.assertEqual(plan["main_generation_id"], "gen-abc-1")

    def test_every_cut_cites_main_track_id(self):
        plan = LC.cut_lipsync_lines(_receipt("gen-zzz"), _map())
        for row in plan["cuts"].values():
            self.assertEqual(row["source"], "gen-zzz")

    def test_sections_dict_map_accepted(self):
        plan = LC.cut_lipsync_lines(
            _receipt(), {"sections": [{"lyrics": _map()}]})
        self.assertEqual(set(plan["cuts"]), {"L1", "L2"})

    def test_bad_receipt_or_map_refused(self):
        for bad_receipt in (None, {}, {"soundtrack": {}}, "x"):
            with self.assertRaises(ValueError):
                LC.cut_lipsync_lines(bad_receipt, _map())
        with self.assertRaises(ValueError):
            LC.cut_lipsync_lines(_receipt(), [{"line_id": "L1", "start_s": 2.0,
                                               "end_s": 1.0}])
        with self.assertRaises(ValueError):
            LC.cut_lipsync_lines(_receipt(), [])
        with self.assertRaises(ValueError):
            LC.cut_lipsync_lines(_receipt(), [{"text": "no id"}])


class StemAndSourceTests(unittest.TestCase):
    """STEM_IN_FINAL_MIX + LIPSYNC_SOURCE_MISMATCH."""

    def test_stem_in_final_mix_fails(self):
        errs = LC.refuse_stem_in_final_mix([
            {"slot": "final_mix", "kind": "vocal-stem", "role": "music-bed"},
        ])
        self.assertEqual(len(errs), 1)
        self.assertIn(LC.STEM_IN_FINAL_MIX, errs[0])

    def test_lipsync_input_only_stem_passes(self):
        self.assertEqual(LC.refuse_stem_in_final_mix([
            {"slot": "lipsync_in", "kind": "vocal-stem",
             "stem_mix_role": LC.STEM_MIX_ROLE},
        ]), [])
        self.assertEqual(LC.refuse_stem_in_final_mix(None), [])

    def test_clip_wrong_source_fails(self):
        errs = LC.verify_lipsync_clip_source(
            {"source": "other-gen"}, "gen-abc-1")
        self.assertEqual(len(errs), 1)
        self.assertIn(LC.LIPSYNC_SOURCE_MISMATCH, errs[0])

    def test_clip_right_source_passes(self):
        self.assertEqual(
            LC.verify_lipsync_clip_source({"source": "gen-abc-1"},
                                          "gen-abc-1"), [])


class VoiceAnalyzerTests(unittest.TestCase):
    """measure_distinct_voices: stub path + owner-gated real path."""

    def test_stub_reports_one_voice_and_unreliable_note(self):
        got = LC.measure_distinct_voices()
        self.assertEqual(got["distinct_voice_count"], 1)
        self.assertIs(got["male_voice_present"], False)
        self.assertEqual(got["method"], "stub")
        self.assertIn("UNRELIABLE", got["note"])
        self.assertIn("Trevor decides the fallback", got["note"])

    def test_injected_analyzer_requires_named_track(self):
        with self.assertRaises(ValueError):
            LC.measure_distinct_voices(track_path=None,
                                       analyzer=lambda p: {"distinct_voice_count": 2,
                                                           "male_voice_present": True,
                                                           "method": "real"})

    def test_injected_analyzer_runs_on_named_track(self):
        got = LC.measure_distinct_voices(
            track_path="/tmp/fake-suno.wav",
            analyzer=lambda p: {"distinct_voice_count": 2,
                                "male_voice_present": True,
                                "method": "pitch-cluster"})
        self.assertEqual(got["distinct_voice_count"], 2)
        self.assertIs(got["male_voice_present"], True)
        self.assertEqual(got["method"], "pitch-cluster")
        self.assertIn("Trevor decides the fallback", got["note"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
