#!/usr/bin/env python3
"""U9 captions-final tests: the excerpt overlay burn site (D16 + U11 seam).

Stdlib only, zero network, zero paid calls, no ffmpeg binary required.

Contract proved here:

  ENTRY:  final_assembler.captions_burn.overlay_excerpt exists and is the
          module U11's call site imports (book_shot.EXCERPT_OVERLAY_HOOK =
          "final_assembler.captions_burn.overlay_excerpt" -- the hook string
          resolves to this module's entry point).
  SHAPE:  overlay_excerpt(lines, provenance=...) accepts U11's exact call
          and always returns a receipt dict that never raises on input the
          seam can produce (list of strings + optional provenance).
  DATA:   the client excerpt comes back byte-identical -- this module never
          rewrites, re-spells, re-cases or "displays-normalises" the words.
  HONEST: the receipt never claims a pixel was burned this call; it plans
          the burn (style + argv + optional SRT) and says burned=False,
          planned=True. Frames are burned by the render pass, not here.
  FAILS-CLOSED: empty / non-list / non-string input returns a refusal
          receipt (ok False, reason code), never a silent pass.
  D16:    white rounded box, black text, lower-middle third; on by default;
          9:16 sits above the bottom 20% of the frame; 16:9 uses the lower
          third (plan 6.5).
  SRT:    with measured cues the module writes a valid SRT (index, comma
          decimal timestamps, exact text); without cues it reports
          timing="unavailable" and invents no clock.
  NO-SPEND: the module imports no subprocess/urllib/socket/http client --
          it cannot reach ffmpeg or a network on its own.

Run: python3 core/final_assembler/test_captions_burn_u9.py
"""
from __future__ import annotations

import importlib
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

HOOK = "final_assembler.captions_burn.overlay_excerpt"
EXCERPT = ["The kitchen was never empty on a Sunday.",
           "She kept the recipe cards in a tin.",
           "Every table remembers who sat there."]


class EntryReachable(unittest.TestCase):
    """The U11 seam resolves: import the hook path and call it U11's way."""

    def test_hook_string_resolves_to_module_and_entry(self):
        mod = importlib.import_module("final_assembler.captions_burn")
        path, attr = HOOK.rsplit(".", 1)
        self.assertEqual(path, mod.__name__)
        self.assertTrue(callable(getattr(mod, attr, None)),
                        "overlay_excerpt missing/not callable")

    def test_u11_call_shape_never_raises(self):
        mod = importlib.import_module("final_assembler.captions_burn")
        r = mod.overlay_excerpt(EXCERPT, provenance="provided")
        self.assertIsInstance(r, dict)
        self.assertEqual(r.get("hook"), HOOK)


class ReceiptHonesty(unittest.TestCase):
    """The receipt is data, never a claim of work that did not happen."""

    def setUp(self):
        self.cb = importlib.import_module("final_assembler.captions_burn")

    def test_lines_come_back_byte_identical(self):
        r = self.cb.overlay_excerpt(EXCERPT, provenance="provided")
        self.assertTrue(r.get("ok"), r)
        self.assertEqual(r.get("lines"), EXCERPT)

    def test_never_claims_a_burn_it_did_not_perform(self):
        r = self.cb.overlay_excerpt(EXCERPT, provenance="provided")
        self.assertIs(r.get("burned"), False, r)
        self.assertIs(r.get("planned"), True, r)

    def test_provenance_is_echoed_never_invented(self):
        given = self.cb.overlay_excerpt(EXCERPT, provenance="provided")
        silent = self.cb.overlay_excerpt(EXCERPT)
        self.assertEqual(given.get("provenance"), "provided")
        self.assertNotIn("provided", repr(silent.get("provenance")))

    def test_no_prompt_key_in_the_receipt(self):
        r = self.cb.overlay_excerpt(EXCERPT, provenance="provided")
        self.assertNotIn("prompt", {k.lower() for k in r})


class FailClosed(unittest.TestCase):
    """Bad input is a refusal receipt, never a crash or a silent pass."""

    def setUp(self):
        self.cb = importlib.import_module("final_assembler.captions_burn")

    def test_empty_lines_refused(self):
        for bad in ([], (), "", None, {}):
            r = self.cb.overlay_excerpt(bad)
            self.assertIsInstance(r, dict, bad)
            self.assertIs(r.get("ok"), False, bad)
            self.assertTrue(r.get("reason_code"), bad)

    def test_non_string_line_refused(self):
        r = self.cb.overlay_excerpt([["nested"], 7])
        self.assertIs(r.get("ok"), False, r)
        self.assertTrue(r.get("reason_code"), r)

    def test_refusal_never_burns(self):
        r = self.cb.overlay_excerpt([])
        self.assertIs(r.get("burned"), False, r)


class D16Style(unittest.TestCase):
    """Plan 6.5 / decision D16: the look and the safe area, on by default."""

    def setUp(self):
        self.cb = importlib.import_module("final_assembler.captions_burn")

    def test_default_look(self):
        st = self.cb.caption_style(1080, 1920)
        self.assertEqual(st.get("box"), "rounded")
        self.assertEqual(st.get("box_colour").lower(), "#ffffff")
        self.assertEqual(st.get("font_colour").lower(), "#000000")
        self.assertEqual(st.get("enabled"), True)

    def test_9_16_clears_the_bottom_20_percent(self):
        st = self.cb.caption_style(1080, 1920, orientation="9:16")
        self.assertGreaterEqual(st.get("bottom_margin_px"), 1920 * 0.20)

    def test_16_9_sits_in_the_lower_third(self):
        st = self.cb.caption_style(1920, 1080, orientation="16:9")
        self.assertLess(st.get("bottom_margin_px"), 1080 / 3.0)
        self.assertGreaterEqual(st.get("bottom_margin_px"), 1080 * 0.05)

    def test_orientation_inferred_from_geometry(self):
        self.assertEqual(self.cb.caption_style(1080, 1920).get("orientation"),
                         "9:16")
        self.assertEqual(self.cb.caption_style(1920, 1080).get("orientation"),
                         "16:9")


class SrtBuilder(unittest.TestCase):
    """D16 also delivers an SRT; no cue means no invented clock."""

    def setUp(self):
        self.cb = importlib.import_module("final_assembler.captions_burn")

    def _cues(self):
        return [{"text": EXCERPT[0], "start": 0.0, "end": 2.5},
                {"text": EXCERPT[1], "start": 2.5, "end": 5.25}]

    def test_valid_srt_from_measured_cues(self):
        srt = self.cb.build_srt(self._cues())
        blocks = [b for b in srt.strip().split("\n\n") if b]
        self.assertEqual(len(blocks), 2, srt)
        first = blocks[0].splitlines()
        self.assertEqual(first[0], "1")
        self.assertEqual(first[1], "00:00:00,000 --> 00:00:02,500")
        self.assertEqual(first[2], EXCERPT[0])

    def test_cue_text_is_untouched(self):
        srt = self.cb.build_srt(self._cues())
        self.assertIn(EXCERPT[0], srt)
        self.assertIn(EXCERPT[1], srt)

    def test_no_cues_reports_unavailable_timing(self):
        r = self.cb.overlay_excerpt(EXCERPT, provenance="provided")
        self.assertEqual(r.get("timing"), "unavailable", r)
        self.assertIsNone(r.get("srt"), r)

    def test_cues_bind_srt_without_inventing(self):
        r = self.cb.overlay_excerpt(EXCERPT, provenance="provided",
                                    cues=self._cues())
        self.assertEqual(r.get("timing"), "measured", r)
        self.assertIn("-->", r.get("srt") or "")


class NoSpendSurface(unittest.TestCase):
    """The module cannot reach ffmpeg or a network on its own."""

    def test_no_execution_imports(self):
        src = open(os.path.join(HERE, "captions_burn.py"),
                   encoding="utf-8").read()
        for banned in ("import subprocess", "import urllib", "import socket",
                       "import http", "from subprocess", "from urllib"):
            self.assertNotIn(banned, src, banned)


if __name__ == "__main__":
    unittest.main()