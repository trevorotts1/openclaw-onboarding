#!/usr/bin/env python3
"""F7 tests: words match the script exactly (unit W-F-U7).

Covers: exact match passes; a "gonna" rewrite where the packet says
"going to" fails; an invented line fails; whitespace/case normalization
passes. Also proves the seam: music_director.build_generate_request refuses
a rewritten or invented lyric and never builds the master payload when
packet_lines is bound. Zero paid calls; stdlib only.

Dual-mode -- plain python3 and pytest:

    python3 core/test_words_match_f7.py
    python3 -m pytest core/test_words_match_f7.py
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = HERE
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import words_match as W  # noqa: E402  module under test

CODE = "CAPTION_WORD_MISMATCH"

PACKET = [
    "I'm gonna show you   the kitchen",
    "It CHANGED my mornings forever.",
]


class ValidateWordsMatchTests(unittest.TestCase):
    """The guard's own four acceptance behaviors."""

    def test_exact_match_passes(self):
        caption = "I'm gonna show you the kitchen\nIt changed my mornings forever."
        self.assertEqual(W.validate_words_match(caption, PACKET), [])

    def test_gonna_rewrite_where_packet_says_going_to_fails(self):
        packet = ["I'm going to show you the kitchen",
                  "It changed my mornings forever."]
        errors = W.validate_words_match(
            "I'm gonna show you the kitchen\nIt changed my mornings forever.",
            packet)
        self.assertEqual(len(errors), 1, errors)
        self.assertTrue(errors[0].startswith(CODE), errors)
        self.assertIn("'gonna'", errors[0])
        self.assertIn("'going'", errors[0])
        self.assertIn("'to'", errors[0])

    def test_invented_line_fails(self):
        caption = "I'm gonna show you the kitchen\n" \
                  "It changed my mornings forever.\n" \
                  "And a bonus line nobody approved"
        errors = W.validate_words_match(caption, PACKET)
        self.assertEqual(len(errors), 1, errors)
        self.assertTrue(errors[0].startswith(CODE), errors)
        self.assertIn("invented", errors[0])

    def test_whitespace_and_case_normalization_passes(self):
        caption = "  I'M   gonna show you\tTHE KITCHEN\n" \
                  "it changed    MY MORNINGS forever  "
        self.assertEqual(W.validate_words_match(caption, PACKET), [])

    def test_missing_word_fails(self):
        caption = "I'm gonna show you the kitchen"
        errors = W.validate_words_match(caption, PACKET)
        self.assertEqual(len(errors), 1, errors)
        self.assertTrue(errors[0].startswith(CODE), errors)
        self.assertIn("'it'", errors[0])

    def test_fail_closed_bad_input_shapes(self):
        self.assertTrue(W.validate_words_match(None, PACKET))
        self.assertTrue(W.validate_words_match("x y", ["x", "y", None]))
        self.assertTrue(W.validate_words_match("x y", "not a list"))
        self.assertEqual(W.validate_words_match("", []), [])

    def test_error_code_constant(self):
        self.assertEqual(W.CODE, CODE)

    def test_punctuation_is_boundary_noise_not_content(self):
        caption = "It changed my mornings, forever!"
        self.assertEqual(W.validate_words_match(caption,
                                               ["It changed my mornings forever"]), [])


class SeamTests(unittest.TestCase):
    """music_director.build_generate_request refuses mismatched words."""

    def setUp(self):
        import music_director
        self.md = music_director
        # $0 doctrine: mock the catalog cache so no work copy or network is
        # touched. Only the suno-generate fields the builder reads.
        self._saved = self.md._cat
        self.md._cat = {"suno-generate": {
            "route_models": {"current": "ai-music-api/generate V6"},
            "model_default": "V6", "model_enum": ["V4", "V5", "V6"]}}

    def tearDown(self):
        self.md._cat = self._saved

    def test_matching_lyrics_build_payload(self):
        req = self.md.build_generate_request(
            "I'm gonna show you the kitchen\nIt changed my mornings forever.",
            "ballad", "T",
            packet_lines=["I'm gonna show you the kitchen",
                          "it changed my mornings forever"])
        self.assertEqual(req["input"]["lyrics"],
                         "I'm gonna show you the kitchen\n"
                         "It changed my mornings forever."
                         "\n\n[Outro]\n[Resolve on final chord]\n")  # I5 ending

    def test_gonna_rewrite_raises_and_builds_nothing(self):
        with self.assertRaises(ValueError) as cm:
            self.md.build_generate_request(
                "I'm gonna show you the kitchen\nIt changed my mornings forever.",
                "ballad", "T",
                packet_lines=["I'm going to show you the kitchen",
                              "It changed my mornings forever."])
        self.assertIn(CODE, str(cm.exception))

    def test_invented_line_raises_and_builds_nothing(self):
        with self.assertRaises(ValueError) as cm:
            self.md.build_generate_request(
                "I'm gonna show you the kitchen\nIt changed my mornings forever.\nextra line here",
                "ballad", "T", packet_lines=PACKET)
        self.assertIn(CODE, str(cm.exception))

    def test_packet_lines_none_keeps_old_behavior(self):
        req = self.md.build_generate_request(
            "I'm gonna show you the kitchen", "ballad", "T")
        self.assertEqual(req["input"]["lyrics"],
                         "I'm gonna show you the kitchen"
                         "\n\n[Outro]\n[Resolve on final chord]\n")  # I5 ending


if __name__ == "__main__":
    unittest.main(verbosity=2)