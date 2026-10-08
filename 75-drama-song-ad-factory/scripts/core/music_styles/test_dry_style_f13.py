#!/usr/bin/env python3
"""F13 dry song style: no default style prompt carries a banned word, and
the no-echo check fails a run whose style does (manual Part F F13, owner
order 2026-10-08; 03-ECHO-ROOT-CAUSE.md sections 5 and 7).

The 2026-10-07 echo batch was caused by builder-invented Suno song styles
asking for "soft strings", "gospel organ pad", "choir pad", "spacious",
"cinematic" and "prayerful" with no reverb/echo tags. F13 moves the ban onto
the SONG STYLE itself:

  * every default style prompt in core/music_styles is scanned against the
    banned song-style word list and must come back clean (negative tags stay
    short: reverb, echo, choir);
  * a run whose style carries a banned word is FAILed by the checker
    (core/audio_c3/no_echo refuses it by name, never ships it);
  * the short negative tags remain present on every stamped payload.

Dual-mode -- plain python3 and pytest:

    python3 core/music_styles/test_dry_style_f13.py
    python3 -m pytest core/music_styles/test_dry_style_f13.py
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
NO_ECHO_DIR = os.path.join(CORE, "audio_c3", "no_echo")

for path in (CORE, NO_ECHO_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

import music_styles as MS  # noqa: E402  module under test


def _load_no_echo():
    """The core no_echo module, loaded once by file path (stdlib only)."""
    cached = sys.modules.get("_f13_core_no_echo")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(
        "_f13_core_no_echo",
        os.path.join(NO_ECHO_DIR, "no_echo.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["_f13_core_no_echo"] = mod
    return mod


NE = _load_no_echo()


def _hits(text):
    """Which banned song-style words this text names (whole word, no case)."""
    if not isinstance(text, str):
        return []
    return [word for word in NE.SONG_BANNED_STYLE_WORDS
            if re.search(r"\b%s\b" % re.escape(word), text, re.IGNORECASE)]


class PromptIsDryTests(unittest.TestCase):
    """No default style prompt contains a banned word (F13 done-when 1)."""

    def test_every_default_prompt_is_banned_word_free(self):
        for sid in MS.style_ids():
            prompt = MS.style_prompt(sid)
            self.assertIsInstance(prompt, str)
            self.assertTrue(prompt.strip(), "%s has an empty prompt" % sid)
            self.assertEqual(_hits(prompt), [],
                             "%s style prompt names banned words: %s"
                             % (sid, _hits(prompt)))

    def test_every_default_prompt_asks_for_the_dry_vocal(self):
        for sid in MS.style_ids():
            prompt = MS.style_prompt(sid).lower()
            self.assertIn("dry", prompt,
                          "%s style prompt does not ask for a dry vocal" % sid)
            self.assertIn("vocal", prompt, sid)

    def test_every_style_record_field_is_clean(self):
        for sid, rec in MS.STYLES.items():
            for key, value in rec.items():
                self.assertEqual(_hits(value), [],
                                 "%s.%s names banned words: %s"
                                 % (sid, key, _hits(value)))

    def test_section_hints_are_banned_word_free(self):
        for sid, hint in MS.SECTION_HINTS.items():
            self.assertEqual(_hits(hint), [],
                             "%s section hint names banned words: %s"
                             % (sid, _hits(hint)))

    def test_the_old_echo_batch_words_are_gone(self):
        # The exact phrases the 2026-10-07 root cause named, per style.
        old = {
            "soul-ballad": ("swelling analog strings",
                            "gospel-tinged backing harmonies",
                            "clean cinematic studio mix",
                            "long held final note"),
            "soul-rise": ("gospel-tinged backing choir",),
        }
        for sid, phrases in old.items():
            prompt = MS.style_prompt(sid)
            for phrase in phrases:
                self.assertNotIn(phrase, prompt,
                                 "%s still carries %r" % (sid, phrase))

    def test_soul_ballad_and_soul_rise_keep_their_keys(self):
        # The rest of the file expects the same structure: keys unchanged.
        for sid in ("soul-ballad", "soul-rise", "rnb-flow"):
            rec = MS.style(sid)
            for key in ("style_id", "label", "sound", "share_rule",
                        "notes", "suno_style_prompt"):
                self.assertIn(key, rec, "%s lost %r" % (sid, key))
            self.assertEqual(rec["style_id"], sid)
        # D15 band still enforced through the same surface.
        band = MS.d15_range(90)
        self.assertEqual(band, (MS.SPOKEN_SHARE_MIN, MS.SPOKEN_SHARE_MAX))


class CheckerFailsABannedStyleTests(unittest.TestCase):
    """The checker FAILs a run whose style carries a banned word (F13
    done-when 2): the run never ships."""

    def test_a_run_whose_style_carries_strings_is_failed(self):
        res = NE.song_request({"input": {"style": "ballad"}},
                              style_text="slow ballad, swelling analog "
                                         "strings, warm piano")
        self.assertEqual(res["outcome"], "rejected", res)
        self.assertEqual(res["reason_code"], "banned-song-style-word", res)
        self.assertIn("strings", res["refused_words"], res)
        self.assertIsNone(res["request"], "a refused run was built")

    def test_the_original_echo_batch_style_text_is_failed(self):
        # The real 13:41 S&S style text from 03-ECHO-ROOT-CAUSE.md section 3.
        res = NE.song_request({"input": {"style": "ballad"}}, style_text=(
            "Slow emotional soul ballad, about 64 BPM: warm Rhodes piano, "
            "soft strings, gentle brushed drums, deep round bass, subtle "
            "gospel organ and a tender choir pad, intimate and cinematic."))
        self.assertEqual(res["outcome"], "rejected", res)
        self.assertEqual(res["reason_code"], "banned-song-style-word", res)
        self.assertTrue(set(res["refused_words"]) >=
                        {"strings", "gospel", "choir", "cinematic"}, res)
        self.assertIsNone(res["request"])

    def test_every_banned_word_fails_a_song_style(self):
        for word in NE.SONG_BANNED_STYLE_WORDS:
            res = NE.song_request({"input": {"style": "ballad"}},
                                  style_text="ballad with %s colouring"
                                             % word)
            self.assertEqual(res["outcome"], "rejected",
                             "%s not failed: %s" % (word, res))
            self.assertEqual(res["reason_code"], "banned-song-style-word",
                             res)

    def test_check_fails_a_payload_edited_after_the_stamp(self):
        res = NE.song_request({"input": {"style": "ballad"}},
                              style_text="soul ballad")
        req = res["request"]
        req["input"]["style"] = ("soul ballad, gospel-tinged backing "
                                 "harmonies, cinematic mix")
        out = NE.check(req)
        self.assertEqual(out["outcome"], "rejected", out["errors"])
        self.assertEqual(out["reason_code"], "banned-song-style-word", out)

    def test_a_clean_dry_style_passes(self):
        for sid in MS.style_ids():
            prompt = MS.style_prompt(sid)
            res = NE.song_request({"input": {"style": prompt}},
                                  style_text=None)
            self.assertEqual(res["outcome"], "ok",
                             "%s default prompt refused: %s"
                             % (sid, res["errors"]))
            req = res["request"]
            self.assertIs(req["dry_close_mic"], True)
            self.assertEqual(NE.check(req)["outcome"], "ok", sid)


class ShortNegativeTagsRemainTests(unittest.TestCase):
    """The short negative tags remain present (F13 done-when 3)."""

    def test_the_short_tags_are_exactly_reverb_echo_choir(self):
        self.assertEqual(NE.NEGATIVE_TAGS, ("reverb", "echo", "choir"))

    def test_every_stamped_payload_carries_the_short_tags(self):
        for sid in MS.style_ids():
            res = NE.song_request(
                {"input": {"style": MS.style_prompt(sid)}})
            self.assertEqual(res["outcome"], "ok", res["errors"])
            req = res["request"]
            self.assertEqual(req["negative_tags"], ["reverb", "echo",
                                                    "choir"])
            for tag in req["negative_tags"]:
                self.assertIn(tag, req["negative_tags"])
            self.assertIs(req["dry_close_mic"], True)

    def test_brief_extended_tags_stay_a_superset(self):
        self.assertTrue(set(NE.NEGATIVE_TAGS) <= set(NE.BRIEF_NEGATIVE_TAGS))


class ZeroSpendTests(unittest.TestCase):
    def test_no_transport_no_spend(self):
        # Mocked providers only: no socket, no request import in either
        # module under test.
        import socket as _socket
        src_ne = open(os.path.join(NO_ECHO_DIR, "no_echo.py"),
                      encoding="utf-8").read()
        src_ms = open(os.path.join(HERE, "music_styles.py"),
                      encoding="utf-8").read()
        for needle in ("urllib", "http.client", "socket", "requests",
                       "subprocess"):
            self.assertNotIn(needle, src_ne, "no_echo.py: %s" % needle)
            self.assertNotIn(needle, src_ms, "music_styles.py: %s" % needle)


if __name__ == "__main__":
    unittest.main(verbosity=2)
