#!/usr/bin/env python3
"""Mocked tests for the SMP weekly step's D22a no-echo rule (AF-SMP-U1).

Owner: Decision log 36-37 applied to Skill 35 (2026-10-07), plan 6.15.

Covers: the dry close-microphone rule and the seven negative tags ride on
every weekly Suno request; the three banned style words (spacious, cinematic,
choir) are refused by name in spoken parts; fail-closed checks (negative
controls prove a disabled rule is caught); zero paid calls (mocked socket,
no transport import); no media files and no operator paths in the owned dir.

Dual-mode -- plain python3 and pytest:

    python3 core/smp/no_echo/test_no_echo.py
    python3 -m pytest core/smp/no_echo/
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import no_echo as M  # noqa: E402  module under test

CLI = os.path.join(HERE, "no_echo.py")
OWNED_DIR = HERE
MEDIA_EXT = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".aac",
             ".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mov",
             ".webm", ".srt")
# Source substrings that would put a transport, a spend path or an operator
# path inside this owned directory.
FORBIDDEN_SOURCE = (
    "urllib", "requests", "http.client", "socket", "subprocess", "ftplib",
    "telnetlib", "websocket", "spend_ledger", "openai", "kie.ai", "api.kie",
    "pm2", "expanduser", "/users/", "/home/", ".openclaw",
    "/Users/", "os.environ",
)


def weekly_style():
    return {"look": "Lifelike 3D", "music": "Soul Ballad",
            "voice": "All Suno", "length_seconds": 60}


class ConstantsTests(unittest.TestCase):
    def test_seven_negative_tags_exactly(self):
        self.assertEqual(len(M.NEGATIVE_TAGS), 7, M.NEGATIVE_TAGS)
        self.assertEqual(
            M.NEGATIVE_TAGS,
            ("reverb", "echo", "delay", "hall", "ethereal", "ambient",
             "choir pad"))
        self.assertEqual(M.negative_tags(), list(M.NEGATIVE_TAGS))

    def test_three_banned_spoken_style_words_exactly(self):
        self.assertEqual(M.SPOKEN_BANNED_STYLE_WORDS,
                         ("spacious", "cinematic", "choir"))

    def test_dry_rule_and_card_line_state_the_rule(self):
        self.assertIn("dry close-microphone vocal", M.DRY_RULE)
        self.assertIn("reverb, echo, delay, hall, ethereal, ambient, "
                      "choir pad", M.rule_text())
        self.assertIn("spacious", M.card_line())
        self.assertIn("cinematic", M.card_line())
        self.assertIn("choir", M.card_line())

    def test_kie_path_is_skill_74_only(self):
        self.assertEqual(M.KIE_PATH, "Skill 74")
        self.assertEqual(M.PROVIDER, "suno")


class WeeklyRequestTests(unittest.TestCase):
    def test_request_carries_dry_rule_and_negative_tags(self):
        res = M.weekly_request(weekly_style(), request_id="w1")
        self.assertEqual(res["outcome"], "ok", res["errors"])
        req = res["request"]
        self.assertIs(req["dry_close_mic"], True)
        self.assertIn("dry close-microphone vocal", req["prompt"])
        self.assertEqual(req["negative_tags"], list(M.NEGATIVE_TAGS))
        self.assertEqual(len(req["negative_tags"]), 7)
        self.assertEqual(req["style_words_banned"],
                         list(M.SPOKEN_BANNED_STYLE_WORDS))
        self.assertEqual(req["provider"], "suno")
        self.assertEqual(req["kie_path"], "Skill 74")
        self.assertEqual(req["step"], "smp-weekly-drama-song")
        self.assertEqual(req["request_id"], "w1")
        self.assertEqual(res["rule"], M.RULE_TEXT)

    def test_dry_rule_added_to_a_prompt_that_lacks_it(self):
        res = M.weekly_request(prompt="warm soul ballad, 60 seconds")
        self.assertEqual(res["outcome"], "ok", res["errors"])
        self.assertIn("warm soul ballad", res["request"]["prompt"])
        self.assertIn("dry close-microphone vocal", res["request"]["prompt"])

    def test_dry_rule_not_duplicated_when_already_asked_for(self):
        res = M.weekly_request(prompt="intimate dry close-mic vocal take")
        self.assertEqual(res["outcome"], "ok", res["errors"])
        self.assertEqual(res["request"]["prompt"].lower().count("dry"), 1,
                         res["request"]["prompt"])

    def test_stored_weekly_style_renders_into_the_prompt(self):
        res = M.weekly_request(weekly_style())
        self.assertIn("Lifelike 3D, Soul Ballad, All Suno, 60 seconds",
                      res["request"]["prompt"])

    def test_request_is_deterministic(self):
        a = M.weekly_request(weekly_style(), request_id="x")
        b = M.weekly_request(weekly_style(), request_id="x")
        self.assertEqual(json.dumps(a, sort_keys=True),
                         json.dumps(b, sort_keys=True))


class BannedWordRefusalTests(unittest.TestCase):
    def test_each_banned_word_refused_by_name_in_spoken_style(self):
        for word in M.SPOKEN_BANNED_STYLE_WORDS:
            res = M.weekly_request(weekly_style(),
                                   spoken_style="wide %s production" % word)
            self.assertEqual(res["outcome"], "rejected",
                             "%s not refused" % word)
            self.assertEqual(res["reason_code"],
                             "banned-spoken-style-word", res)
            self.assertTrue(any(("BANNED_STYLE_WORD:%s" % word) in e
                                for e in res["errors"]), res["errors"])
            self.assertIsNone(res["request"], "a refused request was built")

    def test_refusal_is_case_insensitive(self):
        res = M.weekly_request(weekly_style(), spoken_style="CINEMATIC boom")
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
        res = M.weekly_request(weekly_style(), spoken_parts=parts)
        self.assertEqual(res["outcome"], "rejected", res)
        self.assertEqual(sorted(res["refused_words"]),
                         ["cinematic", "spacious"])

    def test_stamp_raises_named_refusal(self):
        with self.assertRaises(M.NoEchoError) as ctx:
            M.stamp({}, spoken_style="cinematic bed")
        self.assertEqual(ctx.exception.code, "BANNED_STYLE_WORD")
        self.assertIn("cinematic", str(ctx.exception))

    def test_sung_prompt_is_not_subject_to_the_spoken_ban(self):
        # D22a bans the three words in SPOKEN parts only; the sung side of
        # the weekly prompt may still ask for them.
        res = M.weekly_request(prompt="cinematic soul ballad chorus")
        self.assertEqual(res["outcome"], "ok", res["errors"])
        self.assertEqual(M.check(res["request"])["outcome"], "ok")


class CheckTests(unittest.TestCase):
    def _stamped(self, **kw):
        res = M.weekly_request(weekly_style(), **kw)
        self.assertEqual(res["outcome"], "ok", res["errors"])
        return res["request"]

    def test_check_passes_on_a_stamped_request(self):
        self.assertEqual(M.check(self._stamped())["outcome"], "ok")

    def test_negcontrol_dry_rule_disabled_is_caught(self):
        req = self._stamped()
        req["dry_close_mic"] = False
        req["prompt"] = "soul ballad"
        out = M.check(req)
        self.assertEqual(out["outcome"], "rejected")
        self.assertEqual(out["reason_code"], "no-echo-rule-incomplete")
        self.assertTrue(any("MISSING_DRY_RULE" in e for e in out["errors"]),
                        out["errors"])
        self.assertTrue(any("dry_close_mic" in e for e in out["errors"]),
                        out["errors"])

    def test_negcontrol_one_negative_tag_dropped_is_caught(self):
        req = self._stamped()
        req["negative_tags"] = [t for t in req["negative_tags"]
                                if t != "hall"]
        out = M.check(req)
        self.assertEqual(out["outcome"], "rejected")
        self.assertIn("MISSING_NEGATIVE_TAG:hall", out["errors"])
        # all seven must be demanded, not just the missing one
        self.assertEqual(
            sorted(e for e in out["errors"]
                   if e.startswith("MISSING_NEGATIVE_TAG:")),
            ["MISSING_NEGATIVE_TAG:hall"])

    def test_negcontrol_all_tags_dropped_is_caught(self):
        req = self._stamped()
        req["negative_tags"] = []
        out = M.check(req)
        self.assertEqual(out["outcome"], "rejected")
        self.assertEqual(
            len([e for e in out["errors"]
                 if e.startswith("MISSING_NEGATIVE_TAG:")]), 7)

    def test_negcontrol_banned_guard_removed_is_caught(self):
        req = self._stamped()
        req["style_words_banned"] = ["spacious"]
        out = M.check(req)
        self.assertEqual(out["outcome"], "rejected")
        self.assertIn("MISSING_BANNED_STYLE_WORD_GUARD:cinematic",
                      out["errors"])
        self.assertIn("MISSING_BANNED_STYLE_WORD_GUARD:choir", out["errors"])

    def test_negcontrol_request_without_the_rule_at_all_is_caught(self):
        out = M.check({"prompt": "soul ballad"})
        self.assertEqual(out["outcome"], "rejected")
        self.assertTrue(any("MISSING_DRY_RULE" in e for e in out["errors"]),
                        out["errors"])

    def test_check_refuses_a_banned_spoken_word_even_on_a_stamped_request(self):
        req = self._stamped()
        req["spoken_style"] = "spacious hall of voices"
        out = M.check(req)
        self.assertEqual(out["outcome"], "rejected")
        self.assertEqual(out["reason_code"], "banned-spoken-style-word")
        self.assertTrue(
            any(e.startswith("BANNED_STYLE_WORD_IN_SPOKEN:spacious")
                for e in out["errors"]), out["errors"])

    def test_negative_tag_field_is_not_mistaken_for_spoken_text(self):
        # "choir pad" lives in negative_tags; only spoken text is scanned.
        req = self._stamped()
        self.assertIn("choir pad", req["negative_tags"])
        self.assertEqual(M.check(req)["outcome"], "ok")

    def test_wrong_provider_and_wrong_kie_path_refused(self):
        req = self._stamped()
        req["provider"] = "elevenlabs"
        out = M.check(req)
        self.assertEqual(out["outcome"], "rejected")
        self.assertIn("WRONG_PROVIDER:elevenlabs (only suno makes this "
                      "audio)", out["errors"])
        req = self._stamped()
        req["kie_path"] = "direct-adapter"
        out = M.check(req)
        self.assertEqual(out["outcome"], "rejected")
        self.assertIn("WRONG_KIE_PATH:direct-adapter (only Skill 74 is the "
                      "permitted KIE path)", out["errors"])

    def test_non_dict_request_fail_closed(self):
        out = M.check(["not", "a", "request"])
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
        caller = {"prompt": "soul ballad"}
        stamped = M.stamp(caller)
        self.assertEqual(caller, {"prompt": "soul ballad"})
        self.assertIn("dry close-microphone vocal", stamped["prompt"])
        self.assertIs(stamped["dry_close_mic"], True)

    def test_stamp_on_request_that_already_has_the_rule_is_idempotent(self):
        once = M.stamp({"prompt": "soul ballad"})
        twice = M.stamp(once)
        self.assertEqual(once, twice)

    def test_invalid_inputs_raise(self):
        with self.assertRaises(M.NoEchoError):
            M.stamp("not a dict")
        with self.assertRaises(M.NoEchoError):
            M.stamp({}, spoken_style=["not", "a", "string"])
        # the envelope builder refuses instead of raising: still fail closed
        res = M.weekly_request(weekly_style(), spoken_style=["not", "a",
                                                             "string"])
        self.assertEqual(res["outcome"], "rejected", res)
        self.assertEqual(res["reason_code"], "spoken-part-invalid")
        self.assertIsNone(res["request"])


class ZeroSpendTests(unittest.TestCase):
    def test_no_transport_even_with_socket_mocked_broken(self):
        with mock.patch("socket.socket",
                        side_effect=AssertionError("network call")):
            res = M.weekly_request(weekly_style(),
                                   spoken_style="plain spoken line")
        self.assertEqual(res["outcome"], "ok", res["errors"])
        self.assertEqual(M.check(res["request"])["outcome"], "ok")

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

    def test_cli_exit_0_on_a_compliant_request(self):
        res = M.weekly_request(weekly_style())
        proc = self._run(res["request"])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["outcome"], "ok")

    def test_cli_exit_4_when_the_rule_is_disabled(self):
        res = M.weekly_request(weekly_style())
        disabled = res["request"]
        disabled["dry_close_mic"] = False
        disabled["prompt"] = "soul ballad"
        proc = self._run(disabled)
        self.assertEqual(proc.returncode, 4, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["outcome"], "rejected")

    def test_cli_exit_4_on_a_banned_spoken_word(self):
        res = M.weekly_request(weekly_style())
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


class IntegrationWithSmpWeeklyStepTests(unittest.TestCase):
    """The weekly step's own style decision flows into a D22a request."""

    def test_saturday_style_decision_feeds_the_request(self):
        sys.path.insert(0, os.path.dirname(HERE))  # core/smp
        try:
            import saturday_prompt as sp  # noqa: E402
        except ImportError:
            self.skipTest("saturday_prompt sibling not present")
        finally:
            sys.path.pop(0)
        decision = sp.resolve_week("change to Cinematic Soul",
                                   weekly_style())
        self.assertEqual(decision["action"], "change")
        res = M.weekly_request(decision["style"],
                               spoken_style="spoken host intro")
        self.assertEqual(res["outcome"], "ok", res["errors"])
        out = M.check(res["request"])
        self.assertEqual(out["outcome"], "ok", out["errors"])

    def test_client_named_a_banned_word_as_the_spoken_style(self):
        sys.path.insert(0, os.path.dirname(HERE))
        try:
            import saturday_prompt as sp  # noqa: E402
        except ImportError:
            self.skipTest("saturday_prompt sibling not present")
        finally:
            sys.path.pop(0)
        decision = sp.resolve_week(None, weekly_style())
        res = M.weekly_request(decision["style"],
                               spoken_style="spacious spoken outro")
        self.assertEqual(res["outcome"], "rejected", res)
        self.assertEqual(res["refused_words"], ["spacious"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
