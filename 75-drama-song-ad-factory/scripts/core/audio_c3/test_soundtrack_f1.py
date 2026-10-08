#!/usr/bin/env python3
"""F1 one-track soundtrack tests (unit W-F-U1, manual Part F F1, Critical).

Proves, with mocked Suno responses only (no network, zero paid calls):
  * generate_soundtrack_request carries spoken-tagged sections ([Spoken] +
    voice tag) INSIDE the song's own lyrics, one generation, no bed;
  * record_soundtrack stamps exactly one generation id (+ whole-track
    retakes only);
  * a second generation id without a whole-track retake marker FAILS the
    receipt (verify_soundtrack) and a split retake is refused at record time;
  * the payload passes the repo's own D22a no-echo check;
  * negative controls: a disabled rule is caught.

Dual-mode -- plain python3 and pytest:

    python3 core/audio_c3/test_soundtrack_f1.py
    python3 -m pytest core/audio_c3/
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
SKILL = os.path.dirname(os.path.dirname(CORE))
for p in (HERE, CORE):
    if p not in sys.path:
        sys.path.insert(0, p)

import soundtrack as S  # noqa: E402  module under test
import no_echo as NE  # noqa: E402


def _pkg():
    return {
        "title": "Soft Life",
        "style_text": "warm soul ballad, dry close-microphone vocal",
        "lines": [
            {"line_id": "L1", "speaker_id": "c-hero",
             "text": "I been up all night counting every bill I owe",
             "delivery": "spoken"},
            {"line_id": "L2", "speaker_id": "c-hero2",
             "text": "Soft life calling and I finally let it go",
             "delivery": "sung"},
        ],
        "profiles": [
            {"character_id": "c-hero", "gender": "female",
             "age": "30s", "tone": "hushed", "role": "hero",
             "pitch_center": 200.0},
            {"character_id": "c-hero2", "gender": "female",
             "age": "30s", "tone": "hushed2", "role": "best-friend",
             "pitch_center": 230.0},
        ],
    }


class RequestShapeTests(unittest.TestCase):
    """generate_soundtrack_request: spoken tagged inside the one song."""

    def setUp(self):
        self.req = S.generate_soundtrack_request(_pkg())

    def test_spoken_sections_live_inside_the_song_lyrics(self):
        lyrics = self.req["input"]["lyrics"]
        self.assertIn(S.SPOKEN_TAG, lyrics)
        self.assertIn("[Female voice - hero, hushed]", lyrics)
        self.assertIn("I been up all night counting every bill I owe", lyrics)
        spoken, sung = lyrics.split(S.SPOKEN_TAG, 1)[1], lyrics
        for ln in self.req["soundtrack"]["spoken_line_ids"]:
            self.assertIn(ln, ("L1", "L2"))
        self.assertIn("Soft life calling and I finally let it go", lyrics)
        # sung section keeps its own tag, no [Spoken] marker on it
        tail = lyrics.split("Soft life calling", 1)[0][-60:]
        self.assertNotIn(S.SPOKEN_TAG, tail)

    def test_one_generation_shape_and_d22a_stamp(self):
        self.assertEqual(self.req["input"]["instrumental"], False)
        self.assertEqual(self.req["soundtrack"]["mode"], "one-generation")
        self.assertEqual(self.req["soundtrack"]["spoken_source"],
                         "in-song-lyrics")
        self.assertTrue(self.req["soundtrack"]["no_separate_spoken_takes"])
        self.assertTrue(self.req["soundtrack"]["no_added_bed"])
        self.assertEqual(NE.check(self.req)["outcome"], "ok")

    def test_current_envelope_fields(self):
        self.assertEqual(self.req["endpoint"],
                         "/api/v1/jobs/createTask")
        self.assertEqual(self.req["model"], "ai-music-api/generate")
        for field in ("style", "title", "lyrics"):
            self.assertIn(field, self.req["input"])

    def test_invalid_packages_refused(self):
        for bad in (None, {}, {**_pkg(), "lines": []},
                    {**_pkg(), "style_text": ""}):
            with self.assertRaises(ValueError):
                S.generate_soundtrack_request(bad)
        bad = _pkg()
        bad["profiles"] = [{"character_id": "c-x"}]
        with self.assertRaises(ValueError):
            S.generate_soundtrack_request(bad)

    def test_caller_package_not_mutated(self):
        pkg = _pkg()
        before = {k: (list(v) if isinstance(v, list) else v)
                  for k, v in pkg.items()}
        S.generate_soundtrack_request(pkg)
        self.assertEqual(sorted(pkg), sorted(before))


class ReceiptTests(unittest.TestCase):
    """record_soundtrack stamps ONE generation id; second id without a
    whole-track marker fails."""

    def test_stamps_one_generation_id(self):
        r = S.record_soundtrack({}, "gen-1111")
        self.assertEqual(r["soundtrack"]["primary_generation_id"], "gen-1111")
        self.assertEqual(r["soundtrack"]["generation_count"], 1)
        self.assertEqual(S.verify_soundtrack(r), [])

    def test_whole_track_retake_is_legal(self):
        r = S.record_soundtrack({}, "gen-1111",
                                [{"generation_id": "gen-2222",
                                  "kind": "whole-track",
                                  "reason": "words wrong"}])
        self.assertEqual(r["soundtrack"]["generation_count"], 2)
        self.assertEqual(S.verify_soundtrack(r), [])

    def test_second_generation_id_without_marker_fails_receipt(self):
        r = S.record_soundtrack({}, "gen-1111")
        r["audio_jobs"] = [{"generation_id": "gen-2222"}]  # split take
        errs = S.verify_soundtrack(r)
        self.assertTrue(any("SOUNDTRACK_MULTI_GENERATION" in e for e in errs),
                        errs)
        self.assertTrue(any("RETAKE" in e or "MULTI" in e for e in errs))

    def test_split_retake_refused_at_record_time(self):
        with self.assertRaises(ValueError):
            S.record_soundtrack({}, "gen-1111",
                                [{"generation_id": "gen-2222",
                                  "kind": "cut-line"}])
        with self.assertRaises(ValueError):
            S.record_soundtrack({}, "gen-1111", [{"generation_id": "g3"}])

    def test_bad_receipt_inputs_refused(self):
        with self.assertRaises(ValueError):
            S.record_soundtrack({}, "")
        with self.assertRaises(ValueError):
            S.record_soundtrack({}, None)
        with self.assertRaises(ValueError):
            S.record_soundtrack("nope", "gen-1111")

    def test_verify_negative_controls(self):
        self.assertTrue(any("SOUNDTRACK_NOT_RECORDED" in e
                            for e in S.verify_soundtrack({})))
        self.assertTrue(any("RECEIPT_INVALID" in e
                            for e in S.verify_soundtrack("x")))
        r = S.record_soundtrack({}, "gen-1111")
        r["soundtrack"]["mode"] = "piecemeal"
        self.assertTrue(any("ONE_GENERATION" in e
                            for e in S.verify_soundtrack(r)))
        r2 = S.record_soundtrack({}, "gen-1111", [
            {"generation_id": "g2", "kind": "whole-track"}])
        r2["soundtrack"]["generation_count"] = 9
        self.assertTrue(any("COUNT_MISMATCH" in e
                            for e in S.verify_soundtrack(r2)))

    def test_full_round_trip(self):
        receipt = {"audio_jobs": []}
        req = S.generate_soundtrack_request(_pkg())
        receipt["audio_jobs"].append({"generation_id": "gen-real-1",
                                      "kind": "primary"})
        S.record_soundtrack(receipt, "gen-real-1")
        self.assertEqual(S.verify_soundtrack(receipt), [])
        self.assertEqual(req["input"]["instrumental"], False)


def main():  # plain-python3 path, pytest path both fine
    suite = unittest.defaultTestLoader.loadTestsFromModule(
        sys.modules[__name__])
    res = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if res.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())