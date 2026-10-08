#!/usr/bin/env python3
"""H7 tests: captions use the approved words + protected names enforced.

Kiesett's Stop Stale ad: the sheet said "the house went still" where the
packet says "Stale"; Suno sang it and the caption copied it. Each test here
is one way that must now fail (or pass). Zero paid calls; stdlib only.

    python3 core/test_protected_names_h7.py
    python3 -m pytest core/test_protected_names_h7.py
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import protected_names as P  # noqa: E402  module under test

NAMES = ["Stale", "Stop Stale"]
PACKET = ["The house went Stale", "Stop Stale, take back the wheel"]
GOOD = "[Verse]\nThe house went Stale\nI cleaned it all day\n[Chorus]\nStop Stale, take back the wheel"
BAD = GOOD.replace("went Stale", "went still")
SUNG = [("the", 0.0, 0.2), ("house", 0.2, 0.5), ("went", 0.5, 0.8), ("stale", 0.8, 1.3),
        ("i", 1.3, 1.4), ("cleaned", 1.4, 1.8), ("it", 1.8, 1.9), ("all", 1.9, 2.1),
        ("day", 2.1, 2.5), ("stop", 3.0, 3.3), ("stale", 3.3, 3.8), ("take", 3.8, 4.0),
        ("back", 4.0, 4.2), ("the", 4.2, 4.3), ("wheel", 4.3, 4.8)]


def aligned(words):
    return [{"word": w, "start": s, "end": e} for w, s, e in words]


class SheetBuildGate(unittest.TestCase):
    def test_clean_sheet_with_added_lines_and_tags_passes(self):
        self.assertEqual(P.check_sheet(GOOD, PACKET, NAMES), [])

    def test_stale_to_still_fails_naming_the_packet_line(self):
        errs = P.check_sheet(BAD, PACKET, NAMES)
        self.assertTrue(any(e.startswith(P.CODE_PACKET) and "went Stale" in e
                            for e in errs), errs)
        self.assertTrue(any(e.startswith(P.CODE_SHEET) and "Stale" in e
                            for e in errs), errs)

    def test_rewritten_packet_line_fails(self):
        errs = P.check_sheet(GOOD.replace("take back", "get back"), PACKET, NAMES)
        self.assertTrue(any(e.startswith(P.CODE_PACKET) for e in errs), errs)

    def test_protected_list_from_brief(self):
        brief = {"characters": [{"name": "Stale"}, "Stale"], "brands": ["Stop Stale"],
                 "product_name": "Shine Kit"}
        self.assertEqual(P.protected_list(brief), ["Stale", "Stop Stale", "Shine Kit"])

    def test_lyric_writer_rejects_changed_name(self):
        import lyric_writer.lyric_writer as LW
        brief = {"characters": ["Stale"], "packet_lines": ["I watched the house go Stale"]}
        ok = [{"line_id": "v1", "text": "I watched the house go Stale"}]
        bad = [{"line_id": "v1", "text": "I watched the house go still"}]
        self.assertEqual(LW.validate_lyrics(ok, brief)["outcome"], "ok")
        r = LW.validate_lyrics(bad, brief)
        self.assertEqual(r["outcome"], "rejected")
        self.assertIn("packet-line-rewritten", [e["error"] for e in r["errors"]])

    def test_suno_request_not_built_with_changed_name(self):
        import music_director as MD
        MD.build_generate_request(GOOD, "style", "t", packet_lines=PACKET, protected=NAMES)
        with self.assertRaises(ValueError) as cm:
            MD.build_generate_request(BAD, "style", "t", packet_lines=PACKET,
                                      protected=NAMES)
        self.assertIn(P.CODE_PACKET, str(cm.exception))


class SungTakeWordsCheck(unittest.TestCase):
    def test_sung_correctly_passes(self):
        self.assertEqual(P.check_sung_names(GOOD, aligned(SUNG), NAMES), [])

    def test_sung_still_for_stale_fails(self):
        heard = [("still" if w == "stale" and s < 2 else w, s, e) for w, s, e in SUNG]
        errs = P.check_sung_names(GOOD, aligned(heard), NAMES)
        self.assertEqual(len(errs), 1, errs)
        self.assertIn("'still'", errs[0])

    def test_dropped_name_fails(self):
        heard = [x for x in SUNG if not (x[0] == "stop")]
        errs = P.check_sung_names(GOOD, aligned(heard), NAMES)
        self.assertTrue(any("Stop Stale" in e for e in errs), errs)

    def test_music_qc_fails_take_with_wrong_name(self):
        import music_qc
        approved = [{"line_id": "a", "text": "The house went Stale"}]
        seen = [{"line_id": "a", "text": "The house went still"}]
        r = music_qc.check_song_qc(approved, seen, {}, protected=NAMES)
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIn("protected_name", [f["check"] for f in r["findings"]])


class Captions(unittest.TestCase):
    def test_caption_text_is_the_sheet_even_when_the_recognizer_heard_still(self):
        heard = [("still" if w == "stale" and s < 2 else w, s, e) for w, s, e in SUNG]
        cues = P.build_captions(GOOD, aligned(heard))
        self.assertEqual([c["text"] for c in cues],
                         ["The house went Stale", "I cleaned it all day",
                          "Stop Stale, take back the wheel"])
        self.assertEqual((cues[0]["start"], cues[0]["end"]), (0.0, 1.3))
        self.assertEqual(cues[2]["start"], 3.0)
        self.assertEqual(P.check_captions(cues, GOOD, NAMES), [])

    def test_untimed_line_still_gets_the_sheet_text(self):
        cues = P.build_captions(GOOD, aligned(SUNG[:4]))
        self.assertEqual(cues[1]["text"], "I cleaned it all day")

    def test_caption_with_still_for_stale_fails_qc(self):
        errs = P.check_captions([{"text": "The house went still"}], "The house went Stale",
                                NAMES)
        self.assertEqual(len(errs), 1)
        self.assertIn("protected name Stale", errs[0])

    def test_delivery_check_fails_still_for_stale(self):
        from delivery_variants import checks
        v, why = checks.check_captions(["the house went still"], ["The house went Stale"],
                                       protected=NAMES)
        self.assertEqual(v, checks.FAIL, why)
        v, _ = checks.check_captions(["the house went stale"], ["The house went Stale"],
                                     protected=NAMES)
        self.assertEqual(v, checks.PASS)

    def test_speech_to_text_source_fails(self):
        errs = P.check_captions(["The house went Stale"], "The house went Stale", NAMES,
                                text_source="speech-to-text")
        self.assertTrue(errs[0].startswith(P.CODE_SOURCE), errs)


if __name__ == "__main__":
    unittest.main()
