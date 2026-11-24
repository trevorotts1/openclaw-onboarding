#!/usr/bin/env python3
"""Voice Map tests (3N; requirement N-117).

Proves, stdlib only and no paid call:
  * the map gives every word a role, a track and a confidence, and refuses an
    incomplete or unordered map (``VOICE_MAP_INCOMPLETE``);
  * the gate refuses a lead-alone entry where the backing track sings
    (``VOICE_STEM_BLEED``) and a disputed entry (``VOICE_MAP_DISPUTED``);
  * a piece on the wrong track fails ``LIPSYNC_WRONG_STEM``, a lead-alone
    piece over a backing stretch fails ``LIPSYNC_MIXED_PARTS``, and a picture
    with the wrong faces fails ``LIPSYNC_WRONG_FACES``;
  * an absent map refuses before spend (``VOICE_MAP_MISSING``);
  * the Right Voice check returns ``WRONG_VOICE_MOUTHED``, MAJOR.

Run: python3 -B scripts/core/voice_map/test_voice_map.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for _path in (CORE, HERE):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from voice_map import voice_map as VM  # noqa: E402  module under test

SONG = "a" * 64
TRACKS = {VM.TRACK_VOCALS: "music/vocals.mp3",
          VM.TRACK_BACKING: "music/backing-vocals.mp3"}
QUIET = [-80.0] * 200
LOUD = [-10.0] * 200
#: Word 0 (0-2 s) is the lead alone; word 1 (4-6 s) is the backing alone.
LEAD_MIX = [-10.0] * 40 + [-80.0] * 160
BACK_MIX = [-80.0] * 40 + [-10.0] * 160


def _words():
    return [{"word": "hello", "start_s": 0.0, "end_s": 2.0},
            {"word": "again", "start_s": 4.0, "end_s": 6.0}]


def _doc():
    return VM.build(SONG, TRACKS, _words(), LEAD_MIX, BACK_MIX)


class BuildTests(unittest.TestCase):
    def test_every_word_gets_one_entry_with_role_and_track(self):
        doc = _doc()
        self.assertEqual(2, len(doc["entries"]))
        self.assertEqual("lead", doc["entries"][0]["role"])
        self.assertEqual(VM.TRACK_VOCALS, doc["entries"][0]["track"])
        self.assertEqual("backing", doc["entries"][1]["role"])
        self.assertEqual(VM.TRACK_BACKING, doc["entries"][1]["track"])
        for entry in doc["entries"]:
            self.assertEqual(1, len(entry["words"]))
            self.assertIn(entry["confidence"], VM.CONFIDENCE)

    def test_unordered_word_refused(self):
        with self.assertRaises(VM.VoiceMapError) as caught:
            VM.build(SONG, TRACKS,
                     [{"word": "bad", "start_s": 3.0, "end_s": 2.0}],
                     LOUD, QUIET)
        self.assertEqual(VM.VOICE_MAP_INCOMPLETE, caught.exception.code)

    def test_no_words_refused(self):
        with self.assertRaises(VM.VoiceMapError) as caught:
            VM.build(SONG, TRACKS, [], LOUD, QUIET)
        self.assertEqual(VM.VOICE_MAP_INCOMPLETE, caught.exception.code)

    def test_track_role_matches_by_name_not_order(self):
        self.assertEqual(VM.TRACK_BACKING,
                         VM.track_role("x/backing_vocals.mp3"))
        self.assertEqual(VM.TRACK_VOCALS, VM.track_role("x/vocals.mp3"))
        self.assertIsNone(VM.track_role("x/drums.mp3"))

    def test_tracks_by_role_refuses_a_missing_backing(self):
        with self.assertRaises(VM.VoiceMapError) as caught:
            VM.tracks_by_role(["music/vocals.mp3"])
        self.assertEqual("VOICE_MAP_TRACK_MISSING", caught.exception.code)

    def test_write_and_load(self):
        with tempfile.TemporaryDirectory() as temp:
            VM.write(temp, _doc())
            self.assertEqual(SONG, VM.load(temp)["song_sha256"])

    def test_absent_map_refused_before_spend(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(VM.VoiceMapError) as caught:
                VM.load(temp)
            self.assertEqual(VM.VOICE_MAP_MISSING, caught.exception.code)


class GateTests(unittest.TestCase):
    def test_clean_backing_passes(self):
        ok, code, errors = VM.gate(_doc(), LOUD, QUIET)
        self.assertTrue(ok, (code, errors))

    def test_lead_where_backing_sings_fails(self):
        ok, code, _ = VM.gate(_doc(), LOUD, LOUD)
        self.assertFalse(ok)
        self.assertEqual(VM.VOICE_STEM_BLEED, code)

    def test_disputed_entry_fails(self):
        doc = _doc()
        ok, code, _ = VM.gate(doc, LOUD, QUIET, heard={"0": False})
        self.assertFalse(ok)
        self.assertEqual(VM.VOICE_MAP_DISPUTED, code)

    def test_guessed_entry_never_passes(self):
        doc = _doc()
        doc["entries"][0]["confidence"] = "guessed"
        ok, code, _ = VM.gate(doc, LOUD, QUIET)
        self.assertFalse(ok)
        self.assertEqual(VM.VOICE_MAP_DISPUTED, code)

    def test_heard_upgrades_a_guessed_entry(self):
        with tempfile.TemporaryDirectory() as temp:
            got = VM.build_and_gate(temp, SONG, TRACKS, _words(), LEAD_MIX,
                                    BACK_MIX, heard={"0": True, "1": True})
            self.assertEqual("ok", got["outcome"], got)
            self.assertTrue(all(e["confidence"] == "heard"
                                for e in got["map"]["entries"]))

    def test_results_are_recorded_to_the_record_file(self):
        # 3N.8: results go to control/voice-map-record.json.
        with tempfile.TemporaryDirectory() as temp:
            got = VM.build_and_gate(temp, SONG, TRACKS, _words(), LEAD_MIX,
                                    BACK_MIX, heard={"0": True, "1": True})
            self.assertEqual("ok", got["outcome"], got)
            with open(os.path.join(temp, VM.RECORD_PATH), encoding="utf-8") as f:
                rec = json.load(f)
            self.assertEqual("passed", rec["tests"]["V1"])
            self.assertEqual("not-passed", rec["tests"]["V2"])
            self.assertEqual("passed", rec["tests"]["V3"])
            self.assertEqual("failed", rec["tests"]["V8"])
            self.assertEqual(SONG, rec["song_sha256"])

    def test_failed_gate_writes_no_map(self):
        with tempfile.TemporaryDirectory() as temp:
            got = VM.build_and_gate(temp, SONG, TRACKS, _words(), LEAD_MIX,
                                    BACK_MIX, heard={"0": False})
            self.assertEqual("refused", got["outcome"])
            self.assertEqual(VM.VOICE_MAP_DISPUTED, got["reason_code"])
            self.assertFalse(os.path.exists(
                os.path.join(temp, VM.MAP_PATH)))

    def test_one_word_in_two_entries_fails_complete(self):
        # 3N.2 Complete: every word has EXACTLY one entry.
        doc = _doc()
        doc["entries"][1]["words"] = [dict(doc["entries"][0]["words"][0])]
        ok, code, errors = VM.gate(doc)
        self.assertFalse(ok)
        self.assertEqual(VM.VOICE_MAP_INCOMPLETE, code)
        self.assertTrue(any("appears twice" in e for e in errors), errors)


class PlanTests(unittest.TestCase):
    def test_wrong_track_fails(self):
        errs = VM.check_plan([{"piece_id": "p1", "start_s": 4.0, "end_s": 6.0,
                               "role": "backing", "track": VM.TRACK_VOCALS}],
                             _doc())
        self.assertTrue(any(VM.LIPSYNC_WRONG_STEM in e for e in errs), errs)

    def test_lead_alone_over_backing_fails(self):
        # Entry one is the lead alone, entry two the backing alone; a lead
        # piece over both covers a stretch where the backing sings.
        errs = VM.check_plan([{"piece_id": "p1", "start_s": 0.0,
                               "end_s": 6.0, "role": "lead",
                               "track": VM.TRACK_VOCALS}], _doc())
        self.assertTrue(any(VM.LIPSYNC_MIXED_PARTS in e for e in errs), errs)

    def test_wrong_faces_fail(self):
        doc = _doc()
        entry = doc["entries"][0]
        entry["who"] = ["cara", "dana"]
        errs = VM.check_plan([{"piece_id": "p1", "start_s": 0.0,
                               "end_s": 2.0, "role": "lead",
                               "track": VM.TRACK_VOCALS,
                               "faces": [{"character_id": "cara"}]}], doc)
        self.assertTrue(any(VM.LIPSYNC_WRONG_FACES in e for e in errs), errs)

    def test_require_plan_loads_the_map(self):
        with tempfile.TemporaryDirectory() as temp:
            VM.write(temp, _doc())
            VM.require_plan([{"piece_id": "p1", "start_s": 0.0,
                              "end_s": 2.0, "role": "lead",
                              "track": VM.TRACK_VOCALS}], temp)

    def test_overlap_backing_piece_on_backing_track_passes(self):
        # 3N.0 line 3: where lead and backing sing different words, the
        # screen shows the backing singers, fed the backing track.
        doc = VM.build(SONG, TRACKS, _words(), LOUD, LOUD,
                       reader=lambda p: ["back"] if "backing" in p else ["lead"])
        self.assertEqual("overlap", doc["entries"][0]["role"])
        self.assertEqual([], VM.check_plan(
            [{"piece_id": "p1", "start_s": 0.0, "end_s": 2.0,
              "role": "backing", "track": VM.TRACK_BACKING}], doc))

    def test_unison_piece_needs_all_the_vocals(self):
        doc = VM.build(SONG, TRACKS, _words(), LOUD, LOUD,
                       reader=lambda p: ["same words"])
        self.assertEqual("unison", doc["entries"][0]["role"])
        self.assertEqual(VM.TRACK_VOCALS, VM.track_for(doc, 0.0, 2.0, "unison"))
        errs = VM.check_plan([{"piece_id": "p1", "start_s": 0.0,
                               "end_s": 2.0, "role": "backing",
                               "track": VM.TRACK_BACKING}], doc)
        self.assertTrue(any(VM.LIPSYNC_WRONG_STEM in e for e in errs), errs)


class RightVoiceTests(unittest.TestCase):
    def test_clean_take_passes(self):
        got = VM.right_voice({"piece_id": "p1", "track": VM.TRACK_VOCALS},
                             {"track": VM.TRACK_VOCALS}, True)
        self.assertEqual("PASS", got["verdict"])

    def test_wrong_audio_is_major(self):
        got = VM.right_voice({"piece_id": "p1", "track": VM.TRACK_VOCALS},
                             {"track": VM.TRACK_BACKING}, True)
        self.assertEqual("FAIL", got["verdict"])
        self.assertEqual(VM.WRONG_VOICE_MOUTHED, got["code"])
        self.assertEqual("MAJOR", got["severity"])

    def test_mouthing_someone_else_is_major(self):
        got = VM.right_voice({"piece_id": "p1", "track": VM.TRACK_VOCALS},
                             {"track": VM.TRACK_VOCALS}, False)
        self.assertEqual(VM.WRONG_VOICE_MOUTHED, got["code"])
        self.assertEqual("MAJOR", got["severity"])

    def test_plan_check_against_the_map_is_major(self):
        # A lead piece over the backing stretch is a mixed part on the plan.
        got = VM.right_voice(
            {"piece_id": "p1", "start_s": 4.0, "end_s": 6.0, "role": "lead",
             "track": VM.TRACK_VOCALS}, {"track": VM.TRACK_VOCALS}, True,
            doc=_doc())
        self.assertEqual(VM.WRONG_VOICE_MOUTHED, got["code"])
        self.assertEqual("MAJOR", got["severity"])


class FallbackTests(unittest.TestCase):
    def test_no_map_means_no_lipsync(self):
        got = VM.fallback(None)
        self.assertEqual("no-lipsync", got["outcome"])
        self.assertEqual(VM.VOICE_MAP_MISSING, got["reason_code"])
        self.assertIn("split_stem_advanced", got["advanced_stem"])

    def test_singers_names_the_map_singers(self):
        doc = _doc()
        doc["entries"][0]["who"] = ["cara"]
        self.assertEqual(["cara"], VM.singers(doc, 0.0, 2.0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
