#!/usr/bin/env python3
"""Mocked tests for the Saturday theme prompt line (Owner D27 / plan 6.15).

No network, no Skill 74/75 client, no media, no operator paths: every test
runs against temp state files and pure functions. Run:

    python3 -m unittest discover -s core/smp/saturday_prompt -v
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import saturday_prompt as sp  # noqa: E402


class BuildPromptTests(unittest.TestCase):
    def test_line_uses_owner_wording(self):
        prompt = sp.build_saturday_prompt({"look": "Lifelike 3D", "music": "Soul Ballad",
                                           "voice": "All Suno", "length": 60})
        self.assertIn("Drama song of the week: keep ", prompt)
        self.assertIn(" or change it?", prompt)
        self.assertIn("Lifelike 3D, Soul Ballad, All Suno, 60 seconds", prompt)
        self.assertTrue(prompt.startswith(sp.PROMPT_PREFIX))

    def test_default_style_when_nothing_stored(self):
        prompt = sp.build_saturday_prompt(None)
        self.assertIn("Lifelike 3D, Soul Ballad, All Suno, 60 seconds", prompt)

    def test_theme_line_kept(self):
        prompt = sp.build_saturday_prompt(None, theme="  Halloween week  ")
        self.assertIn("Halloween week", prompt)
        self.assertIn("Drama song of the week: keep", prompt)


class ParseReplyTests(unittest.TestCase):
    CURRENT = {"look": "Lifelike 3D", "music": "Soul Ballad",
               "voice": "All Suno", "length": 60}

    def test_no_answer_means_keep(self):
        for reply in (None, "", "   ", "\n\t"):
            decision = sp.parse_reply(reply, self.CURRENT)
            self.assertEqual(decision["action"], "keep", reply)
            self.assertFalse(decision["answered"])
            self.assertEqual(decision["style"], self.CURRENT)
            self.assertEqual(decision["reason"], "no_answer_keeps_style")

    def test_explicit_keep(self):
        for reply in ("keep", "Keep it.", "same", "unchanged", "no change"):
            decision = sp.parse_reply(reply, self.CURRENT)
            self.assertEqual(decision["action"], "keep", reply)
            self.assertEqual(decision["style"], self.CURRENT)

    def test_change_to_named_style(self):
        reply = "change to Sketch to Life, R&B Flow, Velvet Voiceover, 90 seconds"
        decision = sp.parse_reply(reply, self.CURRENT)
        self.assertEqual(decision["action"], "change")
        self.assertEqual(decision["style"]["style_text"],
                         "Sketch to Life, R&B Flow, Velvet Voiceover, 90 seconds")
        self.assertEqual(decision["reason"], "style_changed_from_reply")

    def test_bare_change_keeps_current(self):
        decision = sp.parse_reply("change", self.CURRENT)
        self.assertEqual(decision["action"], "keep")
        self.assertEqual(decision["style"], self.CURRENT)

    def test_plain_style_reply_is_taken_as_the_new_style(self):
        decision = sp.parse_reply("Sketch to Life", self.CURRENT)
        self.assertEqual(decision["action"], "change")
        self.assertEqual(decision["style"]["style_text"], "Sketch to Life")

    def test_a_named_look_reaches_the_structured_field(self):
        # H6: Sunday's run reads `look`, so the named look has to land there.
        decision = sp.parse_reply("change to Canvas to Life", self.CURRENT)
        self.assertEqual(decision["action"], "change")
        self.assertEqual(decision["style"]["look"], "Canvas to Life")
        self.assertEqual(decision["style"]["style_text"], "Canvas to Life")

    def test_an_off_menu_phrase_is_kept_as_text_only(self):
        decision = sp.parse_reply("change to Cinematic Soul", self.CURRENT)
        self.assertEqual(decision["action"], "change")
        self.assertEqual(decision["style"]["style_text"], "Cinematic Soul")
        self.assertEqual(decision["style"]["look"], self.CURRENT["look"])
        self.assertEqual(decision["style"]["length"], self.CURRENT["length"])

    def test_a_spoken_length_the_planner_does_not_offer_is_not_applied(self):
        decision = sp.parse_reply("change to 120 seconds", self.CURRENT)
        self.assertEqual(decision["action"], "change")
        self.assertEqual(decision["style"]["length"], self.CURRENT["length"])


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = os.path.join(self.tmp.name, "drama-song-style.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_style_persists_across_weeks_and_no_answer_keeps_it(self):
        first = sp.resolve_week("change to Sketch to Life, R&B Flow", sp.load_style(self.state))
        sp.save_style(first["style"], self.state)

        # Next Saturday: fresh process reads the stored style into the prompt.
        stored = sp.load_style(self.state)
        prompt = sp.build_saturday_prompt(stored)
        self.assertIn("Sketch to Life, R&B Flow", prompt)

        # Owner says nothing -> style unchanged for the following week too.
        second = sp.resolve_week(None, stored)
        sp.save_style(second["style"], self.state)
        self.assertEqual(sp.load_style(self.state), first["style"])
        self.assertIn("Sketch to Life, R&B Flow", sp.build_saturday_prompt(sp.load_style(self.state)))

    def test_missing_state_file_falls_back_to_defaults(self):
        missing = os.path.join(self.tmp.name, "absent", "style.json")
        self.assertEqual(sp.load_style(missing), sp.DEFAULT_STYLE)

    def test_corrupt_state_file_falls_back_to_defaults(self):
        with open(self.state, "w", encoding="utf-8") as handle:
            handle.write("{not json")
        self.assertEqual(sp.load_style(self.state), sp.DEFAULT_STYLE)

    def test_saved_state_is_valid_json_with_schema_version(self):
        sp.save_style(sp.DEFAULT_STYLE, self.state)
        with open(self.state, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual(data["schema_version"], sp.SCHEMA_VERSION)
        self.assertEqual(data["look"], "Lifelike 3D")

    def test_state_path_is_imported_from_the_setup_block(self):
        sys.path.insert(0, os.path.dirname(HERE))          # core/smp
        try:
            import initial_questions as Q                  # noqa: E402
        finally:
            sys.path.pop(0)
        # `is`, not `==`: a copied literal is the drift H6 exists to end.
        self.assertIs(sp.DEFAULT_STATE_PATH, Q.DEFAULT_STYLE_PATH)

    def test_record_is_flat_so_the_weekly_step_can_read_it(self):
        # H6: the weekly step and the setup block read the top level, not a
        # wrapped `style` object, so Saturday has to write the same shape.
        sp.save_style(sp.DEFAULT_STYLE, self.state)
        with open(self.state, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertNotIn("style", data)
        self.assertEqual(data["look"], "Lifelike 3D")
        self.assertEqual(data["length"], 60)

    def test_a_saturday_change_keeps_the_setup_blocks_fields(self):
        sys.path.insert(0, os.path.dirname(HERE))          # core/smp
        try:
            import initial_questions as Q                  # noqa: E402
        finally:
            sys.path.pop(0)
        Q.save_style(Q.resolve_style(
            {"look": "Lifelike 3D", "cta_link": "https://example.test/cta"},
            kie_active=True), self.state)

        decision = sp.resolve_week("change to Canvas to Life",
                                   sp.load_style(self.state))
        sp.save_style(decision["style"], self.state)

        # The setup block still reads a complete record, with Saturday's
        # change applied and its own fields untouched.
        record = Q.load_style(self.state)
        self.assertIsNotNone(record)
        self.assertEqual(record["look"], "Canvas to Life")
        self.assertEqual(record["cta_link"], "https://example.test/cta")
        self.assertTrue(record["enabled"])


class CliTests(unittest.TestCase):
    def test_cli_prints_prompt_then_applies_reply(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = os.path.join(tmp, "style.json")
            module = os.path.join(HERE, "saturday_prompt.py")

            shown = subprocess.run(
                [sys.executable, module, "--state", state],
                capture_output=True, text=True, check=True)
            self.assertIn("Drama song of the week: keep", shown.stdout)
            self.assertIn("Lifelike 3D", shown.stdout)

            applied = subprocess.run(
                [sys.executable, module, "--state", state, "--apply",
                 "--reply", "change to Sketch to Life"],
                capture_output=True, text=True, check=True)
            decision = json.loads(applied.stdout)
            self.assertEqual(decision["action"], "change")

            shown2 = subprocess.run(
                [sys.executable, module, "--state", state],
                capture_output=True, text=True, check=True)
            self.assertIn("Sketch to Life", shown2.stdout)


class HygieneTests(unittest.TestCase):
    def test_module_makes_no_calls_to_kie_or_network(self):
        module_path = os.path.join(os.path.dirname(__file__), "saturday_prompt.py")
        with open(module_path, "r", encoding="utf-8") as handle:
            source = handle.read()
        for banned in ("requests", "urllib.request", "http.client", "socket",
                       "subprocess", "kie_dispatch", "spend_ledger"):
            self.assertNotIn(banned, source, banned)
        # Skill 74 stays the only KIE path: this module never names one itself.
        self.assertNotIn("74-kie", source)

    def test_no_operator_paths_or_media_files(self):
        module_path = os.path.join(os.path.dirname(__file__), "saturday_prompt.py")
        with open(module_path, "r", encoding="utf-8") as handle:
            source = handle.read()
        self.assertIsNone(re.search(r"/[Uu]sers/", source))
        for media in (".mp4", ".mov", ".png", ".jpg", ".mp3", ".wav"):
            self.assertNotIn(media, source)


if __name__ == "__main__":
    unittest.main()
