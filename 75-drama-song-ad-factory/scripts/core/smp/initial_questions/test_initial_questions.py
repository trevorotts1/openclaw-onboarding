#!/usr/bin/env python3
"""Mocked tests for the drama-song setup block (Owner D27 / D35, plan 6.15).

Offline, stdlib only, zero paid calls, zero network, zero media. One test per
acceptance rule:

  * the block is ONE added block, weekly question defaults yes only while
    Skill 74 is active (no when it is off);
  * look / music / voice / length are asked ONCE with the plan defaults
    pre-selected: Lifelike 3D / Soul Ballad / All Suno / 60 seconds, 90
    optional and nothing longer offered;
  * the weekly call to action defaults to the planner's weekly action link;
  * an explicit client answer beats the default; off-menu answers refuse by
    name instead of guessing;
  * the resolved record carries exactly the eight brief fields and persists;
  * no transport / no KIE client / Skill 74 only path / no operator paths.

Run: python3 core/smp/initial_questions/test_initial_questions.py
"""
import json
import os
import re
import socket
import sys
import tempfile
import unittest
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))

def _build_root():
    """Walk up to the tree root that owns core/smp/initial_questions/.

    Two trees carry this unit: the build root (where core/artifact_graph.py
    lives) and the openclaw-onboarding worktree (where core/ was added by the
    wave). Match on this package's own path so either root resolves.
    """
    node = HERE
    while True:
        if os.path.isdir(os.path.join(node, "core", "smp",
                                      "initial_questions")):
            return node
        parent = os.path.dirname(node)
        if parent == node:
            raise RuntimeError("tree root not found above %s" % HERE)
        node = parent

BUILD_ROOT = _build_root()
sys.path.insert(0, BUILD_ROOT)
sys.path.insert(0, os.path.join(BUILD_ROOT, "core"))   # sibling vocab imports

import core.smp.initial_questions as PKG                      # noqa: E402
import core.smp.initial_questions.initial_questions as Q      # noqa: E402

# --- mocked environment: no live sockets for the whole suite ----------------
_REAL_SOCKET = socket.socket

class _NoNetwork(_REAL_SOCKET):
    def connect(self, *a, **kw):
        raise AssertionError("network call during a mocked test")

    def connect_ex(self, *a, **kw):
        raise AssertionError("network call during a mocked test")

socket.socket = _NoNetwork                      # noqa: A001

# Plan 6.15, transcribed from the owner plan -- never read back from the
# module under test, so a gutted module cannot satisfy its own test.
PLAN_WEEKLY_Q = "Do you want a drama song video every week?"
# manual C4 step 4, transcribed -- never read back from the module.
PLAN_WEEKLY_BRIEF = (
    "What should viewers do, and what is your weekly video budget?")
PLAN_DEFAULTS = ("Lifelike 3D", "Soul Ballad", "All Suno", "60")
FIXED_NOW = datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)


class BlockShapeTests(unittest.TestCase):
    def test_one_added_block_with_plan_wording(self):
        block = Q.build_block(True, "https://example.test/go")
        self.assertEqual(block["block"], "drama-song")
        self.assertEqual(block["source"], Q.SOURCE)
        prompts = [q["prompt"] for q in block["questions"]]
        self.assertIn(PLAN_WEEKLY_Q, prompts)
        # manual C4 step 4: ONE combined ask fills the weekly brief, so the
        # factory's three-question intake cap is never reached from setup.
        self.assertIn(PLAN_WEEKLY_BRIEF, prompts)
        # weekly + look + music + voice + length + cta + weekly_brief
        self.assertEqual(len(block["questions"]), 7)
        combined = [q for q in block["questions"]
                    if q["id"] == "weekly_brief"][0]
        self.assertEqual(combined["prompt"], PLAN_WEEKLY_BRIEF)
        self.assertEqual(Q.Q_WEEKLY_BRIEF, PLAN_WEEKLY_BRIEF)
        self.assertEqual(combined["cadence"], "once")
        # one question carries the whole brief: no second budget ask here.
        self.assertEqual(
            len([q for q in block["questions"]
                 if q["id"] in ("weekly_brief", "budget", "offer", "audience")]),
            1)

    def test_weekly_default_yes_only_when_kie_active(self):
        self.assertEqual(Q.default_weekly(True), "yes")
        self.assertEqual(Q.default_weekly(False), "no")
        on = Q.build_block(True)
        off = Q.build_block(False)
        weekly_on = [q for q in on["questions"] if q["id"] == "weekly"][0]
        weekly_off = [q for q in off["questions"] if q["id"] == "weekly"][0]
        self.assertEqual(weekly_on["default"], "yes")
        self.assertEqual(weekly_off["default"], "no")
        self.assertEqual(weekly_on["cadence"], "weekly")

    def test_style_questions_asked_once_with_plan_defaults(self):
        block = Q.build_block(True)
        by_id = {q["id"]: q for q in block["questions"]}
        for qid, default in (("look", "Lifelike 3D"), ("music", "Soul Ballad"),
                             ("voice", "All Suno"), ("length", "60")):
            self.assertEqual(by_id[qid]["default"], default, qid)
            self.assertEqual(by_id[qid]["cadence"], "once", qid)
        # 90 seconds exists as the optional second choice, nothing longer.
        self.assertEqual(by_id["length"]["options"], ["60", "90"])
        self.assertEqual(by_id["length"]["optional"], ["90"])
        self.assertEqual(tuple(Q.LENGTHS), (60, 90))
        self.assertEqual(Q.DEFAULT_LENGTH, 60)

    def test_cta_question_defaults_to_planner_weekly_action_link(self):
        link = "https://book.example.test/weekly"
        block = Q.build_block(True, link)
        cta = [q for q in block["questions"] if q["id"] == "cta"][0]
        self.assertEqual(cta["default"], link)
        self.assertTrue(cta["required"])


class ResolveTests(unittest.TestCase):
    LINK = "https://book.example.test/weekly"

    def test_no_answers_take_every_plan_default(self):
        style = Q.resolve_style({}, kie_active=True,
                                weekly_action_link=self.LINK, now=FIXED_NOW)
        self.assertEqual(style, {
            "enabled": True,
            "look": "Lifelike 3D",
            "music": "Soul Ballad",
            "voice": "All Suno",
            "length": 60,
            "cta_text": self.LINK,
            "cta_link": self.LINK,
            # manual C4 step 4: blank, never an invented offer / budget.
            "offer": "",
            "audience": "",
            "action": "",
            "budget_minor": 0,
            "budget_currency": "",
            "updated_at": "2026-10-07T12:00:00Z",
        })

    def test_enabled_defaults_to_kie_state_and_explicit_answers_win(self):
        off = Q.resolve_style({}, kie_active=False,
                              weekly_action_link=self.LINK, now=FIXED_NOW)
        self.assertFalse(off["enabled"])
        # Client says yes while KIE is off: their answer wins; the weekly
        # step re-checks the mode at run time and skips with a reason.
        said_yes = Q.resolve_style({"weekly": "yes"}, kie_active=False,
                                   weekly_action_link=self.LINK, now=FIXED_NOW)
        self.assertTrue(said_yes["enabled"])
        said_no = Q.resolve_style({"weekly": "no"}, kie_active=True,
                                  weekly_action_link=self.LINK, now=FIXED_NOW)
        self.assertFalse(said_no["enabled"])
        for spelling in ("Yes", "y", "true", " Y "):
            self.assertTrue(Q.resolve_weekly(spelling, False), spelling)
        for spelling in ("No", "n", "false"):
            self.assertFalse(Q.resolve_weekly(spelling, True), spelling)

    def test_look_music_voice_accept_id_or_label(self):
        style = Q.resolve_style(
            {"look": "canvas-to-life", "music": "R&B Flow",
             "voice": "velvet_voiceover", "length": "90 seconds"},
            kie_active=True, weekly_action_link=self.LINK, now=FIXED_NOW)
        self.assertEqual(style["look"], "Canvas to Life")
        self.assertEqual(style["music"], "R&B Flow")
        self.assertEqual(style["voice"], "Velvet Voiceover")
        self.assertEqual(style["length"], 90)

    def test_sketch_to_life_never_takes_velvet_voiceover(self):
        # D25 (decision log 38): the pair is refused at intake by name, with
        # the client-facing reason and a re-ask that pre-selects All Suno.
        for look, voice in (("sketch-to-life", "velvet_voiceover"),
                            ("Sketch to Life", "Velvet Voiceover")):
            with self.assertRaises(Q.InitialQuestionsError) as ctx:
                Q.resolve_style({"look": look, "voice": voice},
                                kie_active=True, weekly_action_link=self.LINK,
                                now=FIXED_NOW)
            self.assertEqual(ctx.exception.code,
                             "stl-voice-velvet-not-offered", (look, voice))
            self.assertIn("All Suno", str(ctx.exception))
            reask = getattr(ctx.exception, "reask", None)
            self.assertIsNotNone(reask, (look, voice))
            self.assertEqual(reask["outcome"], "refused")
            self.assertEqual(reask["preselected"]["voice"], "all_suno")
            self.assertEqual(reask["preselected"]["look"], "sketch-to-life")
        # All Suno still fine on Sketch to Life, and Velvet still fine on
        # the other four looks.
        stl = Q.resolve_style({"look": "sketch-to-life", "voice": "all_suno"},
                              kie_active=True, weekly_action_link=self.LINK,
                              now=FIXED_NOW)
        self.assertEqual(stl["voice"], "All Suno")
        other = Q.resolve_style({"look": "canvas-to-3d",
                                 "voice": "velvet_voiceover"},
                                kie_active=True,
                                weekly_action_link=self.LINK, now=FIXED_NOW)
        self.assertEqual(other["voice"], "Velvet Voiceover")

    def test_off_menu_answers_refuse_by_name(self):
        cases = (("look", "photoreal", "LOOK_UNKNOWN"),
                 ("music", "jazz", "MUSIC_UNKNOWN"),
                 ("voice", "robot", "VOICE_UNKNOWN"))
        for field, value, code in cases:
            with self.assertRaises(Q.InitialQuestionsError) as ctx:
                Q.resolve_style({field: value}, kie_active=True,
                                weekly_action_link=self.LINK, now=FIXED_NOW)
            self.assertEqual(ctx.exception.code, code, field)
        with self.assertRaises(Q.InitialQuestionsError) as ctx:
            Q.resolve_style({"length": 30}, kie_active=True,
                            weekly_action_link=self.LINK, now=FIXED_NOW)
        self.assertEqual(ctx.exception.code, "LENGTH_NOT_OFFERED")
        with self.assertRaises(Q.InitialQuestionsError) as ctx:
            Q.resolve_style({"weekly": "maybe"}, kie_active=True,
                            weekly_action_link=self.LINK, now=FIXED_NOW)
        self.assertEqual(ctx.exception.code, "WEEKLY_ANSWER_INVALID")

    def test_cta_defaults_to_weekly_action_link_and_refuses_when_absent(self):
        style = Q.resolve_style({"cta_text": "Book your call"},
                                kie_active=True, weekly_action_link=self.LINK,
                                now=FIXED_NOW)
        self.assertEqual(style["cta_text"], "Book your call")
        self.assertEqual(style["cta_link"], self.LINK)
        with self.assertRaises(Q.InitialQuestionsError) as ctx:
            Q.resolve_style({}, kie_active=True, weekly_action_link="",
                            now=FIXED_NOW)
        self.assertEqual(ctx.exception.code, "CTA_LINK_MISSING")

    def test_record_carries_exactly_the_brief_fields(self):
        style = Q.resolve_style({}, kie_active=True,
                                weekly_action_link=self.LINK, now=FIXED_NOW)
        self.assertEqual(tuple(style), Q.STYLE_FIELDS)
        # plan 6.15's eight + the five weekly essentials (manual C4 step 4)
        self.assertEqual(len(Q.STYLE_FIELDS), 13)
        for field in Q.BRIEF_ESSENTIALS:
            self.assertIn(field, Q.STYLE_FIELDS)


class PersistenceTests(unittest.TestCase):
    LINK = "https://book.example.test/weekly"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "drama-song-style.json")

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_then_load_round_trip(self):
        style = Q.resolve_style({"length": 90}, kie_active=True,
                                weekly_action_link=self.LINK, now=FIXED_NOW)
        Q.save_style(style, self.path)
        self.assertEqual(Q.load_style(self.path), style)
        with open(self.path, encoding="utf-8") as handle:
            on_disk = json.load(handle)
        self.assertEqual(tuple(on_disk), Q.STYLE_FIELDS)

    def test_missing_or_corrupt_or_partial_file_is_none(self):
        self.assertIsNone(Q.load_style(os.path.join(self.tmp.name, "absent.json")))
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("{not json")
        self.assertIsNone(Q.load_style(self.path))
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump({"enabled": True}, handle)
        self.assertIsNone(Q.load_style(self.path))

    def test_saving_an_incomplete_record_refuses(self):
        with self.assertRaises(Q.InitialQuestionsError) as ctx:
            Q.save_style({"enabled": True}, self.path)
        self.assertEqual(ctx.exception.code, "STYLE_INCOMPLETE")


class VocabDriftTests(unittest.TestCase):
    """The planner menu must stay the factory's menu, not a private copy.

    The owner-decision literals always run. The sibling-vocabulary comparison
    only exists in the build tree -- the onboarding worktree ships this unit
    alone -- so it reports a skip there instead of an error, and the literal
    check still holds both trees.
    """
    PLAN_LOOKS = ["Lifelike 3D", "2D Hand-Painted", "Sketch to Life",
                  "Canvas to Life", "Canvas to 3D"]          # D29 / plan 4.1
    PLAN_MUSICS = ["Soul Ballad", "R&B Flow", "Soul Rise"]    # D18 / D30
    PLAN_VOICES = ["All Suno", "Velvet Voiceover"]            # D27 / D31

    def test_menus_match_owner_decision_literals(self):
        self.assertEqual([lbl for _, lbl in Q.LOOKS], self.PLAN_LOOKS)
        self.assertEqual([lbl for _, lbl in Q.MUSICS], self.PLAN_MUSICS)
        self.assertEqual([lbl for _, lbl in Q.VOICES], self.PLAN_VOICES)
        # default first in every menu (pre-selected on the card)
        self.assertEqual(Q.LOOKS[0][1], "Lifelike 3D")
        self.assertEqual(Q.MUSICS[0][1], "Soul Ballad")
        self.assertEqual(Q.VOICES[0][1], "All Suno")

    def test_menus_match_sibling_vocabularies(self):
        try:
            from choice_card.looks import LOOK_LABELS, LOOK_ORDER
            from music_styles import music_styles as MS
            from voice_velvet_echo.velvet_voiceover import voice_options
        except ImportError as exc:
            self.skipTest("sibling vocab not in this tree (%s)" % exc)
        self.assertEqual([lbl for _, lbl in Q.LOOKS],
                         [LOOK_LABELS[lid] for lid in LOOK_ORDER])
        self.assertEqual([lbl for _, lbl in Q.MUSICS],
                         [MS.style(sid)["label"] for sid in MS.style_ids()])
        self.assertEqual([v["id"] for v in voice_options()],
                         [vid for vid, _ in Q.VOICES])


class HygieneTests(unittest.TestCase):
    def _source(self, name):
        with open(os.path.join(HERE, name), encoding="utf-8") as handle:
            return handle.read()

    def test_module_makes_no_calls_to_kie_or_network(self):
        source = self._source("initial_questions.py")
        for banned in ("requests", "urllib", "http.client", "socket",
                       "subprocess", "os.system", "kie_dispatch",
                       "spend_ledger", "kie_live_adapter", "createTask",
                       "kie.ai"):
            self.assertNotIn(banned, source, banned)
        # Skill 74 stays the only KIE path: this module never names it as a
        # callable and never reaches a provider itself.
        self.assertNotIn("74-kie", source)

    def test_no_operator_paths_or_media_files(self):
        for name in ("initial_questions.py", "__init__.py"):
            source = self._source(name)
            self.assertIsNone(re.search(r"/Users/", source), name)
            for media in (".mp4", ".mov", ".png", ".jpg", ".mp3", ".wav"):
                self.assertNotIn(media, source, "%s %s" % (name, media))

    def test_package_is_pure_python_and_parses(self):
        import ast
        for name in ("initial_questions.py", "__init__.py"):
            ast.parse(self._source(name))

    def test_default_style_path_lands_in_the_skill35_workspace(self):
        # brief: ~/.openclaw/workspace/social-media-planner/drama-song-style.json
        self.assertEqual(
            Q.STYLE_PATH_TEMPLATE,
            "~/.openclaw/workspace/social-media-planner/drama-song-style.json")
        self.assertTrue(Q.DEFAULT_STYLE_PATH.endswith(
            os.path.join(".openclaw", "workspace", "social-media-planner",
                         "drama-song-style.json")))
        # no host path is written into the source itself
        self.assertIsNone(re.search(r"/Users/", Q.STYLE_PATH_TEMPLATE))

    def test_control_the_network_stub_really_refuses(self):
        with self.assertRaises(AssertionError):
            _NoNetwork().connect(("127.0.0.1", 9))

    def test_exports(self):
        for name in ("build_block", "resolve_style", "save_style",
                     "load_style", "InitialQuestionsError", "STYLE_FIELDS"):
            self.assertIn(name, PKG.__all__)
            self.assertTrue(hasattr(PKG, name), name)


class WeeklyEssentialsTests(unittest.TestCase):
    """Manual C4 step 4: the setup answer fills the weekly brief."""

    LINK = "https://book.example.test/weekly"

    def test_combined_sentence_fills_the_weekly_budget(self):
        style = Q.resolve_style(
            {"weekly_brief": "Book the call, and my weekly video budget is $25"},
            kie_active=True, weekly_action_link=self.LINK, now=FIXED_NOW)
        self.assertEqual(style["budget_minor"], 2500)
        self.assertEqual(style["budget_currency"], "USD")

    def test_budget_shapes_a_client_actually_types(self):
        self.assertEqual(Q.resolve_budget("$25"), (2500, "USD"))
        self.assertEqual(Q.resolve_budget("25 USD"), (2500, "USD"))
        self.assertEqual(Q.resolve_budget("25.50"), (2550, ""))
        self.assertEqual(Q.resolve_budget("500 credits"), (50000, "CREDITS"))
        self.assertEqual(Q.resolve_budget("\u00a330"), (3000, "GBP"))
        self.assertEqual(Q.resolve_budget(None), (0, ""))
        self.assertEqual(Q.resolve_budget("   "), (0, ""))

    def test_budget_refuses_anything_it_cannot_read(self):
        for bad in ("soon", "$", "25 bitcoins", -5):
            with self.assertRaises(Q.InitialQuestionsError) as ctx:
                Q.resolve_budget(bad)
            self.assertIn(ctx.exception.code,
                          ("BUDGET_UNREADABLE", "BUDGET_CURRENCY_UNKNOWN"),
                          "%r -> %s" % (bad, ctx.exception.code))

    def test_essentials_land_in_the_record_blank_when_not_answered(self):
        style = Q.resolve_style({}, kie_active=True,
                                weekly_action_link=self.LINK, now=FIXED_NOW)
        for field in Q.BRIEF_ESSENTIALS:
            self.assertIn(field, style)
        self.assertEqual(style["offer"], "")
        self.assertEqual(style["audience"], "")
        self.assertEqual(style["action"], "")
        self.assertEqual(style["budget_minor"], 0)
        self.assertEqual(style["budget_currency"], "")

    def test_explicit_essentials_win_and_are_never_invented(self):
        style = Q.resolve_style(
            {"offer": "The weekly planner", "audience": "Solo founders",
             "action": "Book a call", "budget_minor": 999,
             "budget_currency": "USD"},
            kie_active=True, weekly_action_link=self.LINK, now=FIXED_NOW)
        self.assertEqual(style["offer"], "The weekly planner")
        self.assertEqual(style["audience"], "Solo founders")
        self.assertEqual(style["action"], "Book a call")
        self.assertEqual(style["budget_minor"], 999)
        self.assertEqual(style["budget_currency"], "USD")

    def test_combined_sentence_never_invents_offer_or_action(self):
        style = Q.resolve_style(
            {"weekly_brief": "Whatever you like, budget $10"},
            kie_active=True, weekly_action_link=self.LINK, now=FIXED_NOW)
        self.assertEqual(style["budget_minor"], 1000)
        self.assertEqual(style["offer"], "")
        self.assertEqual(style["audience"], "")
        self.assertEqual(style["action"], "")

    def test_a_pre_essentials_record_loads_with_them_blank(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "drama-song-style.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"enabled": True, "look": "Lifelike 3D",
                           "music": "Soul Ballad", "voice": "All Suno",
                           "length": 60, "cta_text": "Book",
                           "cta_link": self.LINK,
                           "updated_at": "2026-10-07T12:00:00Z"}, handle)
            loaded = Q.load_style(path)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["budget_minor"], 0)
            self.assertEqual(loaded["offer"], "")
            self.assertEqual(tuple(loaded), Q.STYLE_FIELDS)

    def test_a_saved_record_round_trips_every_essential(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "drama-song-style.json")
            style = Q.resolve_style(
                {"offer": "Guide", "audience": "Owners",
                 "action": "Download", "budget_minor": 1500,
                 "budget_currency": "USD"},
                kie_active=True, weekly_action_link=self.LINK, now=FIXED_NOW)
            Q.save_style(style, path)
            self.assertEqual(Q.load_style(path), style)


if __name__ == "__main__":
    unittest.main()
