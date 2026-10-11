#!/usr/bin/env python3
"""WWFIXPIN-U1: pin defect 1 -- section MARKUP is never a lexical story word.

WWFIX-U1 fixed defect 1 (``story_coverage`` counted a split end-marker row and
other bracketed section tags as lexical story words) but shipped NO test that
detects a regression of it: the only other importer,
``music_qc/test_wwfix_u1.py``, drives the story gates on synthetic rows of the
words ``count`` / ``la`` with no brackets at all. This file pins the fix on the
REAL returned-take fixture, so a future edit that stops rejecting markup turns
this file red.

The two mechanisms under test (both public API, no private names imported):

  * ``is_lexical`` rejects any token that carries ``[`` or ``]`` -- the tail of
    a tag that Suno left bracket-bearing ('Break]', 'End]').
  * ``aligned_lexical_words`` skips every aligned row that lies INSIDE a
    bracketed tag or marker. That is the only thing that can drop the
    bracket-FREE middle fragments of a split tag ('Rap ', 'Verse 3 ', 'Chanel ('
    ...), whose own token has no bracket yet is not a spoken word.

The fixture ``song_contract/fixtures/one-check-v2-g2a-take.json`` is the real
one-check-v2-g2a take (419 aligned rows, 152.42 s) and carries both cases:

  * rows 134..144 -- a '[Rap Verse 3 Chanel (rap): ...]' tag split across rows;
    rows 135..143 have NO bracket in their own token;
  * row 363 'Instrumental ' -- another tag's middle fragment, no bracket;
  * rows 417/418 -- the '[End]' marker split across two rows ('...[' then
    'End]');
  * rows 0 and 9 -- a section tag AND a real lyric word in the SAME row
    ('Girl! ' / 'Girl, '): the exclusion must not over-fire and swallow them.

The fixture's lexical word count is a number MEASURED by the builder on this
head, not copied from any QC: 319 lexical words, 64.024 s of lexical time.
With the markup logic reverted the same fixture reads 329 lexical words and
64.163 s, so this count is exactly the pin.

stdlib only; no network, no spend. Run:

    python3 75-drama-song-ad-factory/scripts/core/story_coverage/test_story_coverage_markup.py
"""
from __future__ import annotations

import json
import os
import sys
import unittest

CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from story_coverage import (          # noqa: E402
    aligned_lexical_words,
    is_lexical,
    lexical_coverage_gate,
    lexical_seconds,
)

FIXTURE = os.path.join(CORE, "song_contract", "fixtures",
                       "one-check-v2-g2a-take.json")

#: Measured by the builder (WWFIXPIN-U1) on this head, directly from the
#: fixture via the public API -- never copied from a QC report. The reverted
#: markup logic reads 329 / 64.163, so these two numbers are the pin.
FIXTURE_LEXICAL_WORDS = 319
FIXTURE_LEXICAL_SECONDS = 64.024
FIXTURE_DURATION_S = 152.42
FIXTURE_COVERAGE = 0.42


class MarkupIsNotStory(unittest.TestCase):
    """Defect 1, pinned on the real one-check-v2-g2a returned take."""

    @classmethod
    def setUpClass(cls):
        with open(FIXTURE, "r", encoding="utf-8") as fh:
            cls.take = json.load(fh)
        cls.rows = cls.take["aligned_words"]
        cls.delivered_s = float(cls.take["duration_s"])
        cls.lex = aligned_lexical_words(cls.rows)
        cls.lex_set = set(cls.lex)

    def _tok(self, i):
        """The lexical token of row ``i`` -- Suno's inline header dropped."""
        return str(self.rows[i]["word"]).split("\n")[-1]

    def _tuple(self, i):
        w = self.rows[i]
        return (float(w["startS"]), float(w["endS"]), self._tok(i))

    # ---- the fixture itself and the measured pin ---------------------------

    def test_fixture_is_the_real_take_and_pins_the_measured_lexical_count(self):
        self.assertTrue(os.path.exists(FIXTURE), FIXTURE)
        self.assertEqual(len(self.rows), 419)
        self.assertEqual(self.delivered_s, FIXTURE_DURATION_S)
        # THE PIN: measured on this head; reverted markup logic reads 329.
        self.assertEqual(len(self.lex), FIXTURE_LEXICAL_WORDS,
                         "lexical word count moved off the measured 319")
        self.assertEqual(lexical_seconds(self.rows), FIXTURE_LEXICAL_SECONDS,
                         "lexical seconds moved off the measured 64.024")

    # ---- split end-marker header fragments are excluded --------------------

    def test_split_tag_fragment_rows_are_excluded(self):
        # rows 135..143: the tail of a '[Rap Verse 3 Chanel (rap): ...]' tag
        # that Suno split off after row 134 'you\\n\\n['. Their OWN token has no
        # bracket, so only the inside-a-tag row scan can drop them.
        fragments = {
            135: "Rap ", 136: "Verse 3 ", 137: "Chanel (", 138: "rap): ",
            139: "Female ", 140: "voice - ", 141: "chanel, ", 142: "warm ",
            143: "confident ",
        }
        for i, want in fragments.items():
            self.assertEqual(self._tok(i), want,
                             "fixture row %d is not the expected tag fragment" % i)
            self.assertNotIn(self._tuple(i), self.lex_set,
                             "split tag fragment %r (row %d) counted as lexical"
                             % (want, i))
        # and the bracket-bearing halves of the split never read as story words
        self.assertEqual(self._tok(134), "[")
        self.assertFalse(is_lexical(self._tok(134)))
        self.assertFalse(is_lexical("alto]"))

    def test_instrumental_tag_fragment_row_is_excluded(self):
        # row 363 'Instrumental ' -- a middle tag fragment with no bracket of
        # its own, opening on row 362 'you\\n\\n[' and closing on 'Break]'.
        self.assertEqual(self._tok(363), "Instrumental ")
        self.assertNotIn(self._tuple(363), self.lex_set,
                         "'Instrumental ' row counted as a lexical story word")
        self.assertNotIn("Instrumental ",
                         [t for _s, _e, t in self.lex])

    # ---- tag-only / marker-only rows are never lexical ---------------------

    def test_tag_only_and_marker_only_tokens_are_never_lexical(self):
        for bad in ("[", "]", "[Instrumental ", "Break]", "End]",
                    "[Hook (sung): female r&b singer, bright upbeat]",
                    "[Rap Verse 3 Chanel (rap): Female voice - chanel]"):
            self.assertFalse(is_lexical(bad),
                             "%r read as a lexical story word" % bad)

    # ---- the split [End] marker is never counted ---------------------------

    def test_split_end_marker_is_never_counted(self):
        # rows 417 'com\\n\\n[' and 418 'End]\\n\\n\\n': the '[End]' marker split
        # across two rows. Neither half is a lexical story word, and no lexical
        # word lands anywhere inside the marker's own span.
        self.assertEqual(self._tok(417), "[")
        self.assertFalse(is_lexical(self._tok(417)))
        self.assertFalse(is_lexical("End]"))
        lo = float(self.rows[417]["startS"])
        hi = float(self.rows[418]["endS"])
        inside = [(s, e, t) for (s, e, t) in self.lex if lo <= s <= hi]
        self.assertEqual(inside, [],
                         "a word inside the split [End] marker was counted: %r"
                         % inside)

    # ---- real lyrics on markup-carrying rows are KEPT ----------------------

    def test_real_lyrics_on_markup_carrying_rows_are_kept(self):
        # rows 0 and 9 carry a section tag AND a real lyric word in one row. The
        # markup exclusion must not over-fire and swallow the lyric.
        for i, want in ((0, "Girl! "), (9, "Girl, ")):
            raw = self.rows[i]["word"]
            self.assertIn("[", raw, "row %d no longer carries a tag" % i)
            self.assertEqual(self._tok(i), want)
            self.assertTrue(is_lexical(want))
            self.assertIn(self._tuple(i), self.lex_set,
                          "real lyric %r on markup row %d was dropped" % (want, i))

    # ---- the coverage gate drives the same real rows -----------------------

    def test_lexical_coverage_gate_reads_the_real_fixture(self):
        gate = lexical_coverage_gate(self.rows, self.delivered_s)
        self.assertEqual(gate["lexical_s"], FIXTURE_LEXICAL_SECONDS)
        self.assertEqual(gate["coverage"], FIXTURE_COVERAGE)
        self.assertFalse(gate["vocalise_counted"])
        # 0.42 < the 0.70 floor, so this partial take FAILS the coverage gate.
        self.assertEqual(gate["verdict"], "FAIL")


if __name__ == "__main__":
    unittest.main(verbosity=2)
