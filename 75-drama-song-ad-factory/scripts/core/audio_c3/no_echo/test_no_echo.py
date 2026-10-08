#!/usr/bin/env python3
"""Mocked tests for the D22a no-echo rule on every Suno payload (AF-ECHO-U1;
Part F F13 owner order 2026-10-08).

Owner: Decision log 36 (D22a) 2026-10-07; plan 6.12 item 3; Part F F13
(02-FIX-AND-IMPROVE-MANUAL.md F13, 03-ECHO-ROOT-CAUSE.md).

Covers: the dry close-microphone vocal rule and the short negative tags
(reverb, echo, choir) ride on every Suno payload — the song payload and every
voice-pack payload; the three banned style words (spacious, cinematic, choir)
are refused by name in spoken parts; the SONG style itself is banned-word
checked (Part F F13): a song style naming strings / gospel / harmonies /
cinematic / choir (or any SONG_BANNED_STYLE_WORDS word) is refused by name;
the choice card and the docs each state the dry vocal rule; fail-closed
checks (negative controls prove a disabled rule is caught); the two real
payload builders in this repo are run and stamped; zero paid calls (mocked
socket, no transport import); no media files and no operator paths in the
owned dir.

Dual-mode -- plain python3 and pytest:

    python3 core/audio_c3/no_echo/test_no_echo.py
    python3 -m pytest core/audio_c3/no_echo/
"""
from __future__ import annotations

import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import no_echo as M  # noqa: E402  module under test

CLI = os.path.join(HERE, "no_echo.py")
OWNED_DIR = HERE
MEDIA_EXT = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".aac",
             ".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mov",
             ".webm", ".srt")
# Source substrings that would put a transport, a spend path or an operator
# path inside this owned directory. Scanned on the module and the package
# init only -- never on this test file, which mocks the transport on purpose.
FORBIDDEN_SOURCE = (
    "urllib", "requests", "http.client", "socket", "subprocess", "ftplib",
    "telnetlib", "websocket", "spend_ledger", "openai", "kie.ai", "api.kie",
    "pm2", "expanduser", "/users/", "/home/", ".openclaw",
    "/Users/", "os.environ",
)

SONG_PAYLOAD = {
    "endpoint": "/api/v1/jobs/createTask",
    "model": "ai-music-api/generate",
    "input": {"custom_mode": True, "instrumental": False, "model": "V6",
              "style": "warm soul ballad", "title": "T", "lyrics": "la la"},
}

PACK_RAW = {
    "character_id": "c-host",
    "provider": "suno",
    "pack_kind": "spoken-only",
    "prompt": "[Female voice - hero, warm], spoken only, dry close-microphone "
              "vocal",
    "dry_close_mic": True,
    "negative_tags": list(M.NEGATIVE_TAGS),
    "style_words_banned": list(M.SPOKEN_BANNED_STYLE_WORDS),
}


class ConstantsTests(unittest.TestCase):
    def test_short_negative_tags_exactly(self):
        self.assertEqual(len(M.NEGATIVE_TAGS), 3, M.NEGATIVE_TAGS)
        self.assertEqual(M.NEGATIVE_TAGS, ("reverb", "echo", "choir"))
        self.assertEqual(M.negative_tags(), list(M.NEGATIVE_TAGS))

    def test_three_banned_spoken_style_words_exactly(self):
        self.assertEqual(M.SPOKEN_BANNED_STYLE_WORDS,
                         ("spacious", "cinematic", "choir"))

    def test_song_banned_style_words_cover_the_root_cause_list(self):
        # Part F F13: the song-style ban names every word the root-cause
        # report and the acceptance brief call out, choir included.
        for word in ("strings", "gospel", "choir", "harmonies", "cinematic",
                     "spacious", "prayerful", "atmospheric", "ethereal",
                     "ambient", "airy", "wet", "shimmer", "hall", "room"):
            self.assertIn(word, M.SONG_BANNED_STYLE_WORDS, word)

    def test_dry_rule_is_the_owner_phrase(self):
        self.assertEqual(M.DRY_RULE, "dry close-microphone vocal")

    def test_brief_extended_tags_cover_the_short_tags(self):
        # The owner brief's wider set is a superset; it never replaces the
        # short stamp.
        self.assertTrue(set(M.NEGATIVE_TAGS) <= set(M.BRIEF_NEGATIVE_TAGS),
                        M.BRIEF_NEGATIVE_TAGS)

    def test_two_payload_kinds_only(self):
        self.assertEqual(M.REQUEST_KINDS, ("song", "voice-pack"))

    def test_kie_path_is_skill_74_only(self):
        self.assertEqual(M.KIE_PATH, "Skill 74")
        self.assertEqual(M.PROVIDER, "suno")
        self.assertEqual(M.RULE_ID, "D22a")

    def test_tag_list_text_is_derived_from_the_short_tags(self):
        self.assertEqual(M.TAG_LIST_TEXT, ", ".join(M.NEGATIVE_TAGS))


class CardAndDocsTests(unittest.TestCase):
    """The card line and the docs line state the dry vocal rule."""

    def test_card_line_states_dry_vocals_and_the_short_tags(self):
        line = M.card_line()
        self.assertIn("dry close-mic vocal", line)
        self.assertIn(M.TAG_LIST_TEXT, line)
        self.assertIn("negative tags", line)

    def test_card_line_names_all_three_banned_words(self):
        for word in M.SPOKEN_BANNED_STYLE_WORDS:
            self.assertIn(word, M.card_line(), word)

    def test_card_line_states_the_song_style_ban(self):
        # Part F F13 is stated on the card: song styles stay dry.
        self.assertIn("song styles stay dry", M.card_line())

    def test_docs_line_states_dry_vocals_and_the_short_tags(self):
        line = M.docs_line()
        self.assertIn(M.DRY_RULE, line)
        self.assertIn(M.TAG_LIST_TEXT, line)
        self.assertIn("short negative tags", line)

    def test_docs_line_names_the_song_style_ban(self):
        line = M.docs_line()
        self.assertIn("song style", line)
        for word in ("strings", "gospel", "harmonies", "cinematic", "choir"):
            self.assertIn(word, line, word)

    def test_docs_line_names_all_three_banned_words(self):
        for word in M.SPOKEN_BANNED_STYLE_WORDS:
            self.assertIn(word, M.docs_line(), word)

    def test_docs_line_covers_both_payload_kinds(self):
        self.assertIn("song", M.docs_line())
        self.assertIn("voice-pack", M.docs_line())

    def test_rule_text_states_the_rule(self):
        self.assertIn(M.DRY_RULE, M.rule_text())
        self.assertIn(M.TAG_LIST_TEXT, M.rule_text())
        self.assertIn("spacious, cinematic or choir", M.rule_text())
        self.assertIn("song style", M.rule_text())

    def test_card_and_docs_lines_travel_on_the_envelope(self):
        out = M.song_request({}, style_text="ballad")
        self.assertEqual(out["card_line"], M.CARD_LINE)
        self.assertEqual(out["docs_line"], M.DOCS_LINE)
        self.assertEqual(out["rule"], M.RULE_TEXT)


class SongPayloadTests(unittest.TestCase):
    def _stamped(self, **kw):
        res = M.song_request(dict(SONG_PAYLOAD), style_text="warm soul "
                              "ballad", **kw)
        self.assertEqual(res["outcome"], "ok", res["errors"])
        return res["request"]

    def test_song_payload_carries_dry_rule_in_its_style(self):
        req = self._stamped()
        self.assertEqual(req["request_kind"], "song")
        self.assertIs(req["dry_close_mic"], True)
        style = req["input"]["style"]
        self.assertIn("warm soul ballad", style)
        self.assertIn(M.DRY_RULE, style)
        self.assertEqual(req["negative_tags"], list(M.NEGATIVE_TAGS))
        self.assertEqual(len(req["negative_tags"]), 3)
        self.assertEqual(req["style_words_banned"],
                         list(M.SPOKEN_BANNED_STYLE_WORDS))
        self.assertEqual(req["song_style_words_banned"],
                         list(M.SONG_BANNED_STYLE_WORDS))
        self.assertEqual(req["provider"], "suno")
        self.assertEqual(req["kie_path"], "Skill 74")
        self.assertEqual(M.check(req)["outcome"], "ok")

    def test_raw_song_payload_fails_the_check_before_the_stamp(self):
        out = M.check(dict(SONG_PAYLOAD))
        self.assertEqual(out["outcome"], "rejected")
        self.assertEqual(out["reason_code"], "no-echo-rule-incomplete")
        self.assertTrue(
            any(e.startswith("MISSING_DRY_RULE:input.style")
                for e in out["errors"]), out["errors"])
        self.assertTrue(
            any(e.startswith("MISSING_NEGATIVE_TAG:")
                for e in out["errors"]), out["errors"])

    def test_caller_payload_is_never_mutated(self):
        raw = dict(SONG_PAYLOAD)
        raw["input"] = dict(SONG_PAYLOAD["input"])
        before = json.dumps(raw, sort_keys=True)
        M.song_request(raw, style_text="ballad")
        self.assertEqual(json.dumps(raw, sort_keys=True), before)

    def test_dry_rule_added_to_a_style_that_lacks_it(self):
        res = M.song_request(style_text="epic trailer music")
        self.assertEqual(res["outcome"], "ok", res["errors"])
        self.assertIn("epic trailer music", res["request"]["prompt"])
        self.assertIn(M.DRY_RULE, res["request"]["prompt"])

    def test_dry_rule_not_duplicated_when_already_asked_for(self):
        res = M.song_request(style_text="intimate dry close-mic vocal take")
        self.assertEqual(res["outcome"], "ok", res["errors"])
        text = res["request"]["prompt"].lower()
        self.assertEqual(text.count("dry"), 1, text)

    def test_song_request_is_deterministic(self):
        a = M.song_request(dict(SONG_PAYLOAD), style_text="ballad",
                           request_id="x")
        b = M.song_request(dict(SONG_PAYLOAD), style_text="ballad",
                           request_id="x")
        self.assertEqual(json.dumps(a, sort_keys=True),
                         json.dumps(b, sort_keys=True))

    def test_request_id_rides_on_the_payload(self):
        res = M.song_request(dict(SONG_PAYLOAD), request_id="s-1")
        self.assertEqual(res["request"]["request_id"], "s-1")

    def test_a_payload_with_no_text_surface_gets_one(self):
        res = M.song_request({})
        self.assertEqual(res["outcome"], "ok", res["errors"])
        self.assertEqual(res["request"]["prompt"], M.DRY_RULE)
        self.assertEqual(M.check(res["request"])["outcome"], "ok")


class VoicePackPayloadTests(unittest.TestCase):
    def test_already_correct_pack_is_accepted_unchanged(self):
        out = M.check(dict(PACK_RAW))
        self.assertEqual(out["outcome"], "ok", out["errors"])

    def test_stamp_is_idempotent_on_a_correct_pack(self):
        res = M.voice_pack_request(dict(PACK_RAW))
        self.assertEqual(res["outcome"], "ok", res["errors"])
        self.assertEqual(res["request"]["prompt"], PACK_RAW["prompt"])
        self.assertEqual(res["request"]["request_kind"], "voice-pack")
        self.assertEqual(M.check(res["request"])["outcome"], "ok")

    def test_pack_missing_the_rule_gets_it(self):
        raw = {"character_id": "c-host", "provider": "suno",
               "prompt": "warm female voice, spoken only"}
        out = M.check(raw)
        self.assertEqual(out["outcome"], "rejected")
        res = M.voice_pack_request(raw)
        self.assertEqual(res["outcome"], "ok", res["errors"])
        req = res["request"]
        self.assertEqual(req["request_kind"], "voice-pack")
        self.assertIn(M.DRY_RULE, req["prompt"])
        self.assertEqual(req["negative_tags"], list(M.NEGATIVE_TAGS))
        self.assertEqual(M.check(req)["outcome"], "ok")

    def test_voice_pack_and_song_share_the_same_rule(self):
        song = M.song_request(dict(SONG_PAYLOAD), style_text="ballad")
        pack = M.voice_pack_request(dict(PACK_RAW))
        for req in (song["request"], pack["request"]):
            self.assertEqual(req["negative_tags"], list(M.NEGATIVE_TAGS))
            self.assertEqual(req["style_words_banned"],
                             list(M.SPOKEN_BANNED_STYLE_WORDS))
            self.assertIs(req["dry_close_mic"], True)
            self.assertEqual(M.check(req)["outcome"], "ok")


class RealSongBuilderTests(unittest.TestCase):
    """Run the repo's own song payload builder and stamp what it produces."""

    def setUp(self):
        if CORE not in sys.path:
            sys.path.insert(0, CORE)
        try:
            self.md = importlib.import_module("music_director")
        except Exception as exc:                        # pragma: no cover
            self.skipTest("music_director unavailable: %s" % exc)
        # The builder reads the W1-06 work-copy catalog. The repackaged
        # skill layout needs the ancestor-walk workcopy_paths (batch train
        # w6, 36f2e2491); until that lands, skip cleanly instead of
        # erroring on a missing models.json.
        try:
            models_path = self.md.workcopy_paths()["models"]
        except Exception as exc:                        # pragma: no cover
            self.skipTest("work-copy catalog unresolvable: %s" % exc)
        if not models_path.is_file():                   # pragma: no cover
            self.skipTest("W1-06 work-copy catalog missing: %s"
                          % models_path)

    def test_real_song_builder_output_carries_the_rule_after_the_stamp(self):
        raw = self.md.build_generate_request("la la la", "warm soul ballad",
                                             "T")
        self.assertIn("input", raw)
        before = M.check(raw)
        self.assertEqual(before["outcome"], "rejected",
                         "the builder already carries D22a -- update the "
                         "negative control, not this assertion")
        res = M.song_request(raw, style_text=None, spoken_style="host intro")
        self.assertEqual(res["outcome"], "ok", res["errors"])
        req = res["request"]
        self.assertIn(M.DRY_RULE, req["input"]["style"])
        self.assertEqual(req["negative_tags"], list(M.NEGATIVE_TAGS))
        self.assertEqual(req["request_kind"], "song")
        self.assertEqual(M.check(req)["outcome"], "ok", M.check(req))

    def test_real_song_builder_output_refuses_a_banned_spoken_style(self):
        raw = self.md.build_generate_request("la la la", "ballad", "T")
        for word in M.SPOKEN_BANNED_STYLE_WORDS:
            res = M.song_request(raw, spoken_style="%s host intro" % word)
            self.assertEqual(res["outcome"], "rejected",
                             "%s not refused" % word)
            self.assertEqual(res["reason_code"],
                             "banned-spoken-style-word", res)
            self.assertTrue(any(("BANNED_STYLE_WORD:%s" % word) in e
                                for e in res["errors"]), res["errors"])
            self.assertIsNone(res["request"], "a refused payload was built")

    def test_real_song_builder_output_is_not_mutated(self):
        raw = self.md.build_generate_request("la la la", "ballad", "T")
        before = json.dumps(raw, sort_keys=True)
        M.song_request(raw)
        self.assertEqual(json.dumps(raw, sort_keys=True), before)


class RealVoicePackBuilderTests(unittest.TestCase):
    """Run the repo's own voice-pack payload builder and stamp the output."""

    def setUp(self):
        if CORE not in sys.path:
            sys.path.insert(0, CORE)
        try:
            self.V = importlib.import_module(
                "audio_c3.voice_packs.voice_packs")
        except Exception as exc:                        # pragma: no cover
            self.skipTest("audio_c3.voice_packs unavailable: %s" % exc)
        self.registry = self.V.new_registry()
        ident = {"character_id": "c-host", "voice_id": "v-host",
                 "gender": "female", "age": "adult", "tone": "warm",
                 "role": "hero", "pitch_center": 195.0}
        self.assertEqual(self.V.register(self.registry, ident)["outcome"],
                         "ok")

    def _raw_pack(self):
        env = self.V.build_pack_request(self.registry, "c-host")
        self.assertEqual(env["outcome"], "ok", env["errors"])
        return env["request"]

    def test_real_voice_pack_builder_output_already_carries_the_rule(self):
        out = M.check(self._raw_pack())
        self.assertEqual(out["outcome"], "ok", out["errors"])

    def test_real_voice_pack_builder_output_survives_the_stamp(self):
        res = M.voice_pack_request(self._raw_pack(),
                                   spoken_style="warm spoken intro")
        self.assertEqual(res["outcome"], "ok", res["errors"])
        self.assertEqual(res["request"]["request_kind"], "voice-pack")
        self.assertEqual(res["request"]["negative_tags"],
                         list(M.NEGATIVE_TAGS))
        self.assertEqual(M.check(res["request"])["outcome"], "ok")

    def test_real_voice_pack_refuses_a_banned_spoken_style(self):
        for word in M.SPOKEN_BANNED_STYLE_WORDS:
            res = M.voice_pack_request(self._raw_pack(),
                                       spoken_style="wide %s bed" % word)
            self.assertEqual(res["outcome"], "rejected",
                             "%s not refused" % word)
            self.assertEqual(res["refused_words"], [word], res)
            self.assertTrue(any(("BANNED_STYLE_WORD:%s" % word) in e
                                for e in res["errors"]), res["errors"])
            self.assertIsNone(res["request"])


class BannedWordRefusalTests(unittest.TestCase):
    def test_each_banned_word_refused_by_name_in_spoken_style(self):
        for word in M.SPOKEN_BANNED_STYLE_WORDS:
            res = M.song_request(dict(SONG_PAYLOAD),
                                 spoken_style="wide %s production" % word)
            self.assertEqual(res["outcome"], "rejected",
                             "%s not refused" % word)
            self.assertEqual(res["reason_code"],
                             "banned-spoken-style-word", res)
            self.assertTrue(any(("BANNED_STYLE_WORD:%s" % word) in e
                                for e in res["errors"]), res["errors"])
            self.assertIsNone(res["request"], "a refused payload was built")

    def test_refusal_is_case_insensitive(self):
        res = M.song_request(dict(SONG_PAYLOAD), spoken_style="CINEMATIC boom")
        self.assertEqual(res["outcome"], "rejected", res)
        self.assertIn("cinematic", res["refused_words"])

    def test_refusal_is_whole_word_not_substring(self):
        self.assertEqual(M.refused_style_words("spaciousness here"), [])
        self.assertEqual(M.refused_style_words("choir"), ["choir"])
        # "choir pad" is a negative tag, and it names the banned word choir.
        self.assertEqual(M.refused_style_words("choir pad"), ["choir"])

    def test_spoken_parts_list_is_checked(self):
        parts = [{"line_id": "s1", "delivery": "spoken",
                  "style": "airy and spacious"}, "cinematic narration"]
        res = M.song_request(dict(SONG_PAYLOAD), spoken_parts=parts)
        self.assertEqual(res["outcome"], "rejected", res)
        self.assertEqual(sorted(res["refused_words"]),
                         ["cinematic", "spacious"])

    def test_stamp_raises_named_refusal(self):
        with self.assertRaises(M.NoEchoError) as ctx:
            M.stamp({}, spoken_style="cinematic bed")
        self.assertEqual(ctx.exception.code, "BANNED_STYLE_WORD")
        self.assertIn("cinematic", str(ctx.exception))

    def test_song_style_with_a_banned_word_is_refused(self):
        # Part F F13: the song style itself is banned-word checked. The old
        # sung-side exemption is gone -- a song style naming strings, gospel,
        # harmonies, cinematic or choir is refused, never shipped.
        for word in M.SONG_BANNED_STYLE_WORDS:
            res = M.song_request(dict(SONG_PAYLOAD),
                                 style_text="warm ballad with %s sheen"
                                            % word)
            self.assertEqual(res["outcome"], "rejected",
                             "%s not refused in a song style" % word)
            self.assertEqual(res["reason_code"], "banned-song-style-word",
                             res)
            self.assertTrue(any(("BANNED_SONG_STYLE_WORD:%s" % word) in e
                                for e in res["errors"]), res["errors"])
            self.assertIsNone(res["request"], "a refused payload was built")

    def test_song_style_refusal_is_case_insensitive(self):
        res = M.song_request(dict(SONG_PAYLOAD), style_text="SWELLING STRINGS")
        self.assertEqual(res["outcome"], "rejected", res)
        self.assertIn("strings", res["refused_words"])

    def test_song_style_refusal_is_whole_word(self):
        # "string pads" would miss; whole-word matching keeps "strings" out
        # of a style without banning unrelated words that contain it.
        self.assertEqual(M.refused_song_style_words("stronger staccato"), [])
        self.assertEqual(M.refused_song_style_words("strings"), ["strings"])

    def test_song_style_scan_hits_every_surface(self):
        for payload in ({"input": {"style": "choir-tinged ballad"}},
                        {"prompt": "gospel-flavoured anthem"},
                        {"style_text": "cinematic ballad"}):
            res = M.song_request(payload)
            self.assertEqual(res["outcome"], "rejected", (payload, res))
            self.assertEqual(res["reason_code"], "banned-song-style-word",
                             res)

    def test_lyrics_surface_is_not_song_style_scanned(self):
        # The ban is a style rule, not a lyric rule: a lyric line naming a
        # banned word is not refused by the song-style scan.
        payload = {"input": {"style": "soul ballad",
                             "lyrics": "the choir in my head sings"}}
        res = M.song_request(payload)
        self.assertEqual(res["outcome"], "ok", res["errors"])
        self.assertEqual(M.check(res["request"])["outcome"], "ok")

    def test_check_catches_a_banned_word_edited_into_the_style(self):
        res = M.song_request(dict(SONG_PAYLOAD), style_text="soul ballad")
        req = res["request"]
        req["input"]["style"] = "warm ballad, swelling analog strings"
        out = M.check(req)
        self.assertEqual(out["outcome"], "rejected")
        self.assertEqual(out["reason_code"], "banned-song-style-word", out)
        self.assertTrue(any(e.startswith("BANNED_SONG_STYLE_WORD_IN_STYLE:")
                            for e in out["errors"]), out["errors"])

    def test_check_negcontrol_song_guard_removed_is_caught(self):
        res = M.song_request(dict(SONG_PAYLOAD), style_text="soul ballad")
        req = res["request"]
        req["song_style_words_banned"] = ["strings"]
        out = M.check(req)
        self.assertEqual(out["outcome"], "rejected")
        self.assertIn("MISSING_SONG_BANNED_STYLE_WORD_GUARD:choir",
                      out["errors"])

    def test_voice_pack_prompt_is_not_song_style_scanned(self):
        # A voice pack is spoken text; its prompt carries the D22a dry rule
        # and the spoken ban, not the song-style ban.
        res = M.voice_pack_request({"prompt": "warm voice, spoken only"})
        self.assertEqual(res["outcome"], "ok", res["errors"])
        self.assertNotIn("song_style_words_banned", res["request"])


class CheckTests(unittest.TestCase):
    def _stamped(self, **kw):
        res = M.song_request(dict(SONG_PAYLOAD), style_text="ballad", **kw)
        self.assertEqual(res["outcome"], "ok", res["errors"])
        return res["request"]

    def test_check_passes_on_a_stamped_payload(self):
        self.assertEqual(M.check(self._stamped())["outcome"], "ok")

    def test_negcontrol_dry_rule_disabled_is_caught(self):
        req = self._stamped()
        req["dry_close_mic"] = False
        out = M.check(req)
        self.assertEqual(out["outcome"], "rejected")
        self.assertEqual(out["reason_code"], "no-echo-rule-incomplete")
        self.assertTrue(any("MISSING_DRY_RULE:dry_close_mic" in e
                            for e in out["errors"]), out["errors"])

    def test_negcontrol_dry_phrase_stripped_from_the_style_is_caught(self):
        req = self._stamped()
        req["input"]["style"] = "warm soul ballad"
        out = M.check(req)
        self.assertEqual(out["outcome"], "rejected")
        self.assertIn("MISSING_DRY_RULE:input.style does not ask for "
                      "'dry close-microphone vocal'", out["errors"])

    def test_negcontrol_one_negative_tag_dropped_is_caught(self):
        req = self._stamped()
        req["negative_tags"] = [t for t in req["negative_tags"]
                                if t != "echo"]
        out = M.check(req)
        self.assertEqual(out["outcome"], "rejected")
        self.assertIn("MISSING_NEGATIVE_TAG:echo", out["errors"])
        self.assertEqual(
            [e for e in out["errors"] if e.startswith("MISSING_NEGATIVE_TAG:")],
            ["MISSING_NEGATIVE_TAG:echo"])

    def test_negcontrol_all_tags_dropped_is_caught(self):
        req = self._stamped()
        req["negative_tags"] = []
        out = M.check(req)
        self.assertEqual(out["outcome"], "rejected")
        self.assertEqual(
            len([e for e in out["errors"]
                 if e.startswith("MISSING_NEGATIVE_TAG:")]), 3)

    def test_negcontrol_banned_guard_removed_is_caught(self):
        req = self._stamped()
        req["style_words_banned"] = ["spacious"]
        out = M.check(req)
        self.assertEqual(out["outcome"], "rejected")
        self.assertIn("MISSING_BANNED_STYLE_WORD_GUARD:cinematic",
                      out["errors"])
        self.assertIn("MISSING_BANNED_STYLE_WORD_GUARD:choir", out["errors"])

    def test_negcontrol_partial_extended_tag_list_is_caught(self):
        req = self._stamped()
        req["negative_tags_extended"] = ["reverb", "echo"]
        out = M.check(req)
        self.assertEqual(out["outcome"], "rejected")
        self.assertIn("INCOMPLETE_EXTENDED_NEGATIVE_TAGS:hall",
                      out["errors"])

    def test_negcontrol_payload_without_the_rule_at_all_is_caught(self):
        out = M.check({"input": {"style": "ballad"}})
        self.assertEqual(out["outcome"], "rejected")
        self.assertTrue(any("MISSING_DRY_RULE" in e for e in out["errors"]),
                        out["errors"])

    def test_negcontrol_payload_with_no_text_surface_is_caught(self):
        out = M.check({"dry_close_mic": True})
        self.assertEqual(out["outcome"], "rejected")
        self.assertIn("MISSING_STYLE_TEXT:no style or prompt surface to carry "
                      "'dry close-microphone vocal'", out["errors"])

    def test_check_refuses_a_banned_spoken_word_even_on_a_stamped_payload(self):
        req = self._stamped()
        req["spoken_style"] = "spacious hall of voices"
        out = M.check(req)
        self.assertEqual(out["outcome"], "rejected")
        self.assertEqual(out["reason_code"], "banned-spoken-style-word")
        self.assertTrue(
            any(e.startswith("BANNED_STYLE_WORD_IN_SPOKEN:spacious")
                for e in out["errors"]), out["errors"])

    def test_negative_tag_field_is_not_mistaken_for_spoken_text(self):
        # "choir" lives in negative_tags; only spoken text is scanned, so a
        # compliant payload carrying the tag as a tag still passes.
        req = self._stamped()
        self.assertIn("choir", req["negative_tags"])
        self.assertEqual(M.check(req)["outcome"], "ok")

    def test_wrong_provider_and_wrong_kie_path_refused(self):
        req = self._stamped()
        req["provider"] = "elevenlabs"
        out = M.check(req)
        self.assertEqual(out["outcome"], "rejected")
        self.assertIn("WRONG_PROVIDER:elevenlabs (only suno builds this "
                      "payload)", out["errors"])
        req = self._stamped()
        req["kie_path"] = "direct-adapter"
        out = M.check(req)
        self.assertEqual(out["outcome"], "rejected")
        self.assertIn("WRONG_KIE_PATH:direct-adapter (only Skill 74 is the "
                      "permitted KIE path)", out["errors"])

    def test_wrong_request_kind_refused(self):
        req = self._stamped()
        req["request_kind"] = "video"
        out = M.check(req)
        self.assertEqual(out["outcome"], "rejected")
        self.assertIn("WRONG_REQUEST_KIND:'video'", out["errors"][0])

    def test_non_dict_payload_fail_closed(self):
        out = M.check(["not", "a", "payload"])
        self.assertEqual(out["outcome"], "rejected")
        self.assertEqual(out["reason_code"], "request-invalid")

    def test_check_is_deterministic(self):
        req = self._stamped()
        a = M.check(req)
        b = M.check(req)
        self.assertEqual(json.dumps(a, sort_keys=True),
                         json.dumps(b, sort_keys=True))


class StampTests(unittest.TestCase):
    def test_stamp_never_mutates_the_caller_dict(self):
        caller = {"input": {"style": "ballad"}}
        stamped = M.stamp(caller, kind="song")
        self.assertEqual(caller, {"input": {"style": "ballad"}})
        self.assertIn(M.DRY_RULE, stamped["input"]["style"])
        self.assertIs(stamped["dry_close_mic"], True)

    def test_stamp_is_idempotent(self):
        once = M.stamp(dict(SONG_PAYLOAD), kind="song")
        twice = M.stamp(once, kind="song")
        self.assertEqual(once, twice)

    def test_stamp_refuses_a_second_producer(self):
        with self.assertRaises(M.NoEchoError) as ctx:
            M.stamp({"provider": "elevenlabs"}, style_text="ballad")
        self.assertEqual(ctx.exception.code, "WRONG_PROVIDER")

    def test_stamp_refuses_a_non_skill_74_kie_path(self):
        with self.assertRaises(M.NoEchoError) as ctx:
            M.stamp({"kie_path": "direct-adapter"}, style_text="ballad")
        self.assertEqual(ctx.exception.code, "WRONG_KIE_PATH")

    def test_stamp_refuses_an_unknown_payload_kind(self):
        with self.assertRaises(M.NoEchoError) as ctx:
            M.stamp({}, kind="podcast")
        self.assertEqual(ctx.exception.code, "BAD_REQUEST_KIND")

    def test_envelope_reports_a_refusal_instead_of_raising(self):
        res = M.song_request({"provider": "elevenlabs"}, style_text="ballad")
        self.assertEqual(res["outcome"], "rejected", res)
        self.assertEqual(res["reason_code"], "wrong_provider", res)
        self.assertIsNone(res["request"])
        self.assertTrue(any("only suno builds this payload" in e
                            for e in res["errors"]), res["errors"])

    def test_invalid_inputs_raise(self):
        with self.assertRaises(M.NoEchoError):
            M.stamp("not a dict")
        with self.assertRaises(M.NoEchoError):
            M.stamp({}, spoken_style=["not", "a", "string"])
        with self.assertRaises(M.NoEchoError):
            M.stamp({}, style_text=["not", "a", "string"])
        res = M.song_request(dict(SONG_PAYLOAD), spoken_style=["not", "a",
                                                               "string"])
        self.assertEqual(res["outcome"], "rejected", res)
        self.assertEqual(res["reason_code"], "spoken-part-invalid")
        self.assertIsNone(res["request"])


class ZeroSpendTests(unittest.TestCase):
    def test_no_transport_even_with_socket_mocked_broken(self):
        with mock.patch("socket.socket",
                        side_effect=AssertionError("network call")):
            res = M.song_request(dict(SONG_PAYLOAD), style_text="ballad",
                                 spoken_style="plain spoken line")
            pack = M.voice_pack_request(dict(PACK_RAW))
        self.assertEqual(res["outcome"], "ok", res["errors"])
        self.assertEqual(M.check(res["request"])["outcome"], "ok")
        self.assertEqual(M.check(pack["request"])["outcome"], "ok")

    def test_mocked_negative_control_socket_is_actually_armed(self):
        # prove the mock above would have fired had anything opened a socket
        with mock.patch("socket.socket",
                        side_effect=AssertionError("network call")):
            with self.assertRaises(AssertionError):
                import socket  # noqa: F401
                socket.socket()

    def test_module_source_carries_no_transport_no_spend_no_operator_path(self):
        with open(CLI, "r", encoding="utf-8") as handle:
            source = handle.read()
        for needle in FORBIDDEN_SOURCE:
            self.assertNotIn(needle, source, "source contains %r" % needle)
        self.assertNotIn("import " + "socket", source)
        # the only KIE path is named, never dialled
        self.assertIn("Skill 74", source)
        # proven to hold for the needle the prose would most easily trip
        self.assertNotIn("requ" + "ests", source)

    def test_package_source_carries_no_transport(self):
        with open(os.path.join(OWNED_DIR, "__init__.py"),
                  "r", encoding="utf-8") as handle:
            source = handle.read()
        for needle in FORBIDDEN_SOURCE:
            self.assertNotIn(needle, source, "init contains %r" % needle)

    def test_owned_dir_holds_no_media_files(self):
        for name in sorted(os.listdir(OWNED_DIR)):
            self.assertFalse(name.lower().endswith(MEDIA_EXT),
                             "media file in owned dir: %s" % name)

    def test_no_state_path_written_by_the_module(self):
        with open(CLI, "r", encoding="utf-8") as handle:
            source = handle.read()
        self.assertIsNone(re.search(r"open\(\s*['\"]w", source),
                          "module opens a file for writing")

    def test_owned_dir_holds_only_this_units_files(self):
        names = sorted(n for n in os.listdir(OWNED_DIR)
                       if not n.startswith("__pycache__")
                       and n != "__pycache__")
        self.assertEqual(names, ["__init__.py", "no_echo.py",
                                 "test_no_echo.py"], names)


class CliTests(unittest.TestCase):
    def _run(self, payload):
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as handle:
            json.dump(payload, handle)
            path = handle.name
        try:
            proc = subprocess.run([sys.executable, CLI, "--file", path],
                                  capture_output=True, text=True, timeout=60)
        finally:
            os.unlink(path)
        return proc

    def test_cli_exit_0_on_a_compliant_payload(self):
        res = M.song_request(dict(SONG_PAYLOAD), style_text="ballad")
        proc = self._run(res["request"])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["outcome"], "ok")

    def test_cli_exit_4_when_the_rule_is_disabled(self):
        res = M.song_request(dict(SONG_PAYLOAD), style_text="ballad")
        disabled = res["request"]
        disabled["dry_close_mic"] = False
        disabled["input"]["style"] = "ballad"
        proc = self._run(disabled)
        self.assertEqual(proc.returncode, 4, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["outcome"], "rejected")

    def test_cli_exit_4_on_a_banned_spoken_word(self):
        res = M.song_request(dict(SONG_PAYLOAD), style_text="ballad")
        bad = res["request"]
        bad["spoken_style"] = "cinematic and wide"
        proc = self._run(bad)
        self.assertEqual(proc.returncode, 4, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["reason_code"],
                         "banned-spoken-style-word")

    def test_cli_exit_1_on_unreadable_input(self):
        with tempfile.NamedTemporaryFile("w", suffix=".json",
                                         delete=False) as handle:
            handle.write("{not json")
            path = handle.name
        try:
            proc = subprocess.run([sys.executable, CLI, "--file", path],
                                  capture_output=True, text=True, timeout=60)
        finally:
            os.unlink(path)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
