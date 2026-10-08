#!/usr/bin/env python3
"""Tests for the SMP thin re-export of the D22a no-echo rule (manual L1).

The rule itself is implemented once in ``core/audio_c3/no_echo/no_echo.py``.
``core/smp/no_echo/no_echo.py`` is a thin re-export so imports under
``core/smp/`` keep resolving. These tests prove: the file is thin, every
exported name is the core module's own object, the rule behaves through the
re-export, the CLI still works, and the source carries no transport, spend
path or operator path.

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

import no_echo as M  # noqa: E402  module under test (the re-export)

CLI = os.path.join(HERE, "no_echo.py")
OWNED_DIR = HERE
CORE_PATH = os.path.abspath(os.path.join(
    HERE, "..", "..", "audio_c3", "no_echo", "no_echo.py"))
MEDIA_EXT = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".aac",
             ".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mov",
             ".webm", ".srt")
FORBIDDEN_SOURCE = (
    "urllib", "requests", "http.client", "socket", "subprocess", "ftplib",
    "telnetlib", "websocket", "spend_ledger", "openai", "kie.ai", "api.kie",
    "pm2", "expanduser", "/users/", "/home/", ".openclaw",
    "/" + "Users/", "os.environ",
)
THIN_MAX_LINES = 20


def load_core():
    """The core module instance the re-export bound itself to (one execution).

    Loading the file a second time would make equal-but-distinct objects and
    break identity; the re-export caches its load under this exact name.
    """
    cached = sys.modules.get("_smp_core_no_echo")
    if cached is not None:
        return cached
    import importlib.util
    spec = importlib.util.spec_from_file_location("_core_no_echo", CORE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CORE = load_core()


class ThinnessTests(unittest.TestCase):
    def test_module_is_under_twenty_lines(self):
        with open(CLI, "r", encoding="utf-8") as handle:
            count = sum(1 for _ in handle)
        self.assertLess(count, THIN_MAX_LINES, "module is %d lines" % count)

    def test_every_exported_name_is_the_core_objects_own(self):
        # plain run binds no_echo.py (the re-export module); pytest binds the
        # package, which re-exports a subset -- names absent on M are allowed
        # unless the core package's __all__ demands them.
        demanded = set(getattr(CORE, "__all__", ()))
        for name in CORE.__dict__:
            if name.startswith("_"):
                continue
            if not hasattr(M, name):
                if name in demanded:
                    self.fail("core package exports %r; smp does not" % name)
                continue
            self.assertIs(getattr(M, name), getattr(CORE, name), name)

    def test_implementation_lives_in_audio_c3_not_here(self):
        # stamp is defined in core/audio_c3, not re-implemented in smp/
        self.assertIn("audio_c3", M.stamp.__code__.co_filename)
        self.assertIn("audio_c3", M.check.__code__.co_filename)
        self.assertIn("audio_c3", M.song_request.__code__.co_filename)


class ConstantsTests(unittest.TestCase):
    def test_short_negative_tags_exactly(self):
        self.assertEqual(len(M.NEGATIVE_TAGS), 3, M.NEGATIVE_TAGS)
        self.assertEqual(M.NEGATIVE_TAGS, ("reverb", "echo", "choir"))
        self.assertEqual(M.negative_tags(), list(M.NEGATIVE_TAGS))

    def test_three_banned_spoken_style_words_exactly(self):
        self.assertEqual(M.SPOKEN_BANNED_STYLE_WORDS,
                         ("spacious", "cinematic", "choir"))

    def test_song_banned_style_words_reexported(self):
        # Part F F13: the song-style ban travels through the re-export too.
        self.assertEqual(M.SONG_BANNED_STYLE_WORDS,
                         CORE.SONG_BANNED_STYLE_WORDS)

    def test_dry_rule_and_card_line_state_the_rule(self):
        self.assertIn("dry close-microphone vocal", M.DRY_RULE)
        self.assertIn("reverb, echo, choir", M.rule_text())
        self.assertIn("spacious", M.card_line())
        self.assertIn("cinematic", M.card_line())
        self.assertIn("choir", M.card_line())

    def test_kie_path_is_skill_74_only(self):
        self.assertEqual(M.KIE_PATH, "Skill 74")
        self.assertEqual(M.PROVIDER, "suno")

    def test_schema_is_the_core_audio_c3_one(self):
        self.assertEqual(M.SCHEMA_VERSION, "blackceo.audio-c3/no-echo/v1")
        self.assertEqual(M.RULE_ID, "D22a")


class SongRequestTests(unittest.TestCase):
    def test_request_carries_dry_rule_and_negative_tags(self):
        res = M.song_request({"prompt": "soul ballad"}, request_id="w1")
        self.assertEqual(res["outcome"], "ok", res["errors"])
        req = res["request"]
        self.assertIs(req["dry_close_mic"], True)
        self.assertIn("dry close-microphone vocal", req["prompt"])
        self.assertEqual(req["negative_tags"], list(M.NEGATIVE_TAGS))
        self.assertEqual(len(req["negative_tags"]), 3)
        self.assertEqual(req["style_words_banned"],
                         list(M.SPOKEN_BANNED_STYLE_WORDS))
        self.assertEqual(req["song_style_words_banned"],
                         list(M.SONG_BANNED_STYLE_WORDS))
        self.assertEqual(req["provider"], "suno")
        self.assertEqual(req["kie_path"], "Skill 74")
        self.assertEqual(req["request_id"], "w1")
        self.assertEqual(res["rule"], M.RULE_TEXT)

    def test_dry_rule_added_to_a_prompt_that_lacks_it(self):
        res = M.song_request({"prompt": "warm soul ballad, 60 seconds"})
        self.assertEqual(res["outcome"], "ok", res["errors"])
        self.assertIn("warm soul ballad", res["request"]["prompt"])
        self.assertIn("dry close-microphone vocal", res["request"]["prompt"])

    def test_dry_rule_not_duplicated_when_already_asked_for(self):
        res = M.song_request({"prompt": "intimate dry close-mic vocal take"})
        self.assertEqual(res["outcome"], "ok", res["errors"])
        self.assertEqual(res["request"]["prompt"].lower().count("dry"), 1,
                         res["request"]["prompt"])

    def test_request_is_deterministic(self):
        a = M.song_request({"prompt": "soul ballad"}, request_id="x")
        b = M.song_request({"prompt": "soul ballad"}, request_id="x")
        self.assertEqual(json.dumps(a, sort_keys=True),
                         json.dumps(b, sort_keys=True))


class BannedWordRefusalTests(unittest.TestCase):
    def test_each_banned_word_refused_by_name_in_spoken_style(self):
        for word in M.SPOKEN_BANNED_STYLE_WORDS:
            res = M.song_request({"prompt": "soul ballad"},
                                 spoken_style="wide %s production" % word)
            self.assertEqual(res["outcome"], "rejected",
                             "%s not refused" % word)
            self.assertEqual(res["reason_code"],
                             "banned-spoken-style-word", res)
            self.assertTrue(any(("BANNED_STYLE_WORD:%s" % word) in e
                                for e in res["errors"]), res["errors"])
            self.assertIsNone(res["request"], "a refused request was built")

    def test_refusal_is_case_insensitive(self):
        res = M.song_request({"prompt": "soul ballad"},
                             spoken_style="CINEMATIC boom")
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
        res = M.song_request({"prompt": "soul ballad"}, spoken_parts=parts)
        self.assertEqual(res["outcome"], "rejected", res)
        self.assertEqual(sorted(res["refused_words"]),
                         ["cinematic", "spacious"])

    def test_stamp_raises_named_refusal(self):
        with self.assertRaises(M.NoEchoError) as ctx:
            M.stamp({}, spoken_style="cinematic bed")
        self.assertEqual(ctx.exception.code, "BANNED_STYLE_WORD")
        self.assertIn("cinematic", str(ctx.exception))

    def test_song_style_with_a_banned_word_is_refused(self):
        # Part F F13: the song style itself is banned-word checked through
        # the re-export too; the old sung-side exemption is gone.
        res = M.song_request({"prompt": "cinematic soul ballad chorus"})
        self.assertEqual(res["outcome"], "rejected", res)
        self.assertEqual(res["reason_code"], "banned-song-style-word", res)
        self.assertIsNone(res["request"], "a refused request was built")


class CheckTests(unittest.TestCase):
    def _stamped(self, **kw):
        res = M.song_request({"prompt": "soul ballad"}, **kw)
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
                                if t != "echo"]
        out = M.check(req)
        self.assertEqual(out["outcome"], "rejected")
        self.assertIn("MISSING_NEGATIVE_TAG:echo", out["errors"])
        self.assertEqual(
            sorted(e for e in out["errors"]
                   if e.startswith("MISSING_NEGATIVE_TAG:")),
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
        # "choir" lives in negative_tags; only spoken text is scanned.
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
        res = M.song_request({"prompt": "soul ballad"},
                             spoken_style=["not", "a", "string"])
        self.assertEqual(res["outcome"], "rejected", res)
        self.assertEqual(res["reason_code"], "spoken-part-invalid")
        self.assertIsNone(res["request"])


class ZeroSpendTests(unittest.TestCase):
    def test_no_transport_even_with_socket_mocked_broken(self):
        with mock.patch("socket.socket",
                        side_effect=AssertionError("network call")):
            res = M.song_request({"prompt": "soul ballad"},
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
        res = M.song_request({"prompt": "soul ballad"})
        proc = self._run(res["request"])
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["outcome"], "ok")

    def test_cli_exit_4_when_the_rule_is_disabled(self):
        res = M.song_request({"prompt": "soul ballad"})
        disabled = res["request"]
        disabled["dry_close_mic"] = False
        disabled["prompt"] = "soul ballad"
        proc = self._run(disabled)
        self.assertEqual(proc.returncode, 4, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["outcome"], "rejected")

    def test_cli_exit_4_on_a_banned_spoken_word(self):
        res = M.song_request({"prompt": "soul ballad"})
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


class ImportTests(unittest.TestCase):
    def test_import_from_another_working_directory(self):
        code = ("import sys; sys.path.insert(0, %r); import no_echo as M;"
                "print(len(M.NEGATIVE_TAGS), M.KIE_PATH,"
                "M.SPOKEN_BANNED_STYLE_WORDS)" % HERE)
        proc = subprocess.run([sys.executable, "-c", code],
                              cwd=tempfile.gettempdir(),
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(proc.stdout.strip(),
                         "3 Skill 74 ('spacious', 'cinematic', 'choir')")

    def test_package_exports_every_name_the_core_package_hands_out(self):
        core_init = os.path.abspath(os.path.join(
            HERE, "..", "..", "audio_c3", "no_echo", "__init__.py"))
        with open(core_init, "r", encoding="utf-8") as handle:
            text = handle.read()
        exported = re.findall(r'^\s{4}([A-Z][A-Z0-9_a-z]*),?\s*$', text,
                              re.M)
        exported += re.findall(r'^\s{4}([a-z][a-z0-9_]*),?\s*$', text, re.M)
        for name in exported:
            self.assertIn(name, M.__dict__, name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
