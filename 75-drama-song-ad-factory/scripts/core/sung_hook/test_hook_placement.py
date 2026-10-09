#!/usr/bin/env python3
"""FU-HOOK-PLACEMENT tests. Dual-mode:

    python3 core/sung_hook/test_hook_placement.py
    python3 -m pytest core/sung_hook/test_hook_placement.py

Replays the One-Check v1 and v2 sheets (150 s, R&B Flow): both sheets
fail with a plain reason, and the v2 take's extra hook at 13.6 s is caught
before any picture spend. The story-beat check MEASURES where each hook
sits: a hook at about a quarter of the song fails a plan whose words only
become true at the turn, whatever beats a plan claims.
"""
from __future__ import annotations

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from sung_hook import hook_placement as HP   # noqa: E402
import suno_recipe as R                      # noqa: E402

FIX = os.path.join(HERE, "fixtures")
V1_SHEET = os.path.join(CORE, "suno_recipe", "fixtures", "one-check-lyrics.txt")
D150 = 148                                   # 150 s chosen -> 148 s delivered


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _json(name):
    with open(os.path.join(FIX, name), encoding="utf-8") as f:
        return json.load(f)


def _sung(tag, *lines):
    return {"tag": tag, "delivery": "sung", "lines": list(lines)}


CHORUS = ("Girl, I got you", "right by your si-ide")   # the hook + one more real line
CLIENT = "Girl, I got you. Right by your side."


def _built_up_sheet():
    """Intro -> vocalise -> three verses -> pre-chorus -> hook (at about 60%
    of the planned song, inside the turn) -> hook 2 -> spoken outro."""
    return [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
            _sung("Vocalise", "Oo-o-oh"),
            _sung("Verse 1", "The bills came due", "The lights went dim"),
            _sung("Verse 2", "The calls went cold", "I lost the thread"),
            _sung("Verse 3", "She took my hand", "She showed me how"),
            _sung("Pre-Chorus", "I kept my faith", "I hung on tight"),
            _sung("Hook", *CHORUS),
            _sung("Hook 2", *CHORUS),
            {"tag": "Outro", "delivery": "spoken", "lines": ["Link below."]}]


def _early_sheet():
    """The same song with the first hook moved up to about a third of the way
    in: built up (verse + pre-chorus) but long before the turn."""
    s = _built_up_sheet()
    return s[:3] + [s[5], s[6], s[3], s[4]] + s[7:]   # verse 1, pre, HOOK, verse 2, verse 3


PLAN = {"true_at_beat": "the_turn"}


class Sheets(unittest.TestCase):
    def test_v1_fails_story_sense(self):
        # no hook_plan: the story check is UNMEASURED, a FAIL, never a skip
        r = HP.check_sheet(_read(V1_SHEET), "rnb-flow", D150)
        self.assertEqual(r["reasons"], ["UNMEASURED: hook_plan"])
        # the honest plan: "Girl, I got you" only becomes true at the turn (the
        # masterclass); v1 sang it at 16% of the song, in the world-building
        r = HP.check_sheet(_read(V1_SHEET), "rnb-flow", D150, PLAN)
        self.assertEqual(r["verdict"], "FAIL")
        self.assertTrue(any("first hook sits at 16% of the song (beat 'villain_arrives'), "
                            "before 'the_turn'" in x for x in r["reasons"]), r)
        self.assertTrue(any("6 hook blocks, the 148 s plan fits at most 3" in x
                            for x in r["reasons"]), r)

    def test_v2_fails_buildup(self):
        r = HP.check_sheet(_read(os.path.join(FIX, "one-check-v2-lyrics.txt")), "rnb-flow", D150)
        self.assertEqual(r["verdict"], "FAIL")
        self.assertIn("the first hook is section #3 ('Hook') and comes before a verse", r["reasons"][0])

    def test_built_up_sheet_at_its_beat_passes(self):
        r = HP.check_sheet(_built_up_sheet(), "soul-ballad", D150, PLAN)
        self.assertEqual((r["verdict"], r["reasons"]), ("PASS", []))
        self.assertEqual(r["buildup"], ["verse", "pre"])
        self.assertEqual(r["hook_beats"], ["the_turn", "the_rise"])   # measured

    def test_pre_chorus_required_where_the_style_has_one(self):
        no_pre = [s for s in _built_up_sheet() if s["tag"] != "Pre-Chorus"]
        self.assertTrue(HP.check_buildup(no_pre, "soul-ballad", D150))     # ballad has [Pre-Chorus]
        self.assertEqual(HP.check_buildup(no_pre, "rnb-flow", D150), [])   # R&B Flow: verse -> hook
        self.assertEqual(HP.check_buildup(no_pre, "soul-ballad", 58), [])  # 60 s plan has no pre-chorus

    def test_story_beat_is_measured_not_declared(self):
        # the checker's counter-example shape: built up, but the first hook at
        # about a third of the song while its words become true at the turn
        early = _early_sheet()
        self.assertEqual(HP.check_buildup(early, "soul-ballad", D150), [])
        r = HP.check_story(early, PLAN, D150, "soul-ballad")
        self.assertTrue(any("before 'the_turn' (from 57%)" in x for x in r), r)
        # a plan that CLAIMS the turn for every hook changes nothing: the
        # beats are measured from the sheet, never read from the plan
        claimed = {"true_at_beat": "the_turn", "beats": ["the_turn", "the_rise"]}
        self.assertEqual(HP.check_story(early, claimed, D150, "soul-ballad"), r)
        self.assertEqual(HP.plan_for(early, D150, "the_turn", "soul-ballad")["beats"][0],
                         "pain_deepens")
        opener = {"true_at_beat": "hook"}
        self.assertTrue(any("never the opener" in x
                            for x in HP.check_story(_built_up_sheet(), opener, D150, "soul-ballad")))

    def test_count_fits_after_the_beat(self):
        # hook_count(148) = 6; true only at the turn leaves the runtime for 3
        self.assertEqual((HP.hook_target(D150), HP.hook_target(D150, PLAN)), (6, 3))
        self.assertEqual(HP.hook_target(178, {"true_at_beat": "the_world"}), 8)
        many = _built_up_sheet()[:-1] + [_sung("Hook %d" % i, *CHORUS) for i in range(3, 5)]
        r = HP.check_story(many, PLAN, D150, "soul-ballad")
        self.assertTrue(any("4 hook blocks, the 148 s plan fits at most 3" in x for x in r), r)

    def test_plan_for_measures_every_hook(self):
        p = HP.plan_for(_built_up_sheet(), D150, "the_turn", "soul-ballad")
        self.assertEqual(p, {"true_at_beat": "the_turn", "beats": ["the_turn", "the_rise"]})
        self.assertEqual(HP.check_story(_built_up_sheet(), p, D150, "soul-ballad"), [])

    def test_missing_inputs_fail_unmeasured(self):
        self.assertEqual(HP.check_buildup(_built_up_sheet(), None, D150), ["UNMEASURED: style_id"])
        self.assertEqual(HP.check_buildup(_built_up_sheet(), "soul-ballad", None), ["UNMEASURED: length_s"])
        self.assertEqual(HP.check_story(_built_up_sheet(), None, D150, "soul-ballad"),
                         ["UNMEASURED: hook_plan"])
        self.assertEqual(HP.check_story(_built_up_sheet(), {"beats": ["the_turn"]}, D150, "soul-ballad"),
                         ["UNMEASURED: true_at_beat"])
        r = HP.check_returned(None, [], "soul-ballad", D150, PLAN)
        self.assertEqual((r["verdict"], r["reasons"]), ("FAIL", ["UNMEASURED: sheet_text"]))
        r = HP.check_returned(_built_up_sheet(), [], "soul-ballad", D150)
        self.assertEqual((r["verdict"], r["reasons"]), ("FAIL", ["UNMEASURED: hook_plan"]))

    def test_recipe_refuses_hook_before_buildup_and_bad_plans(self):
        early = _built_up_sheet()
        early.insert(2, early.pop(6))                     # hook straight after the vocalise
        with self.assertRaises(R.RecipeError) as cm:
            R.prepare("soul-ballad", early, CLIENT, 58, hook_plan=PLAN)
        self.assertIn("payoff", str(cm.exception))
        with self.assertRaises(R.RecipeError) as cm:
            R.prepare("soul-ballad", _built_up_sheet(), CLIENT, None, hook_plan=PLAN)
        self.assertIn("UNMEASURED: length_s", str(cm.exception))
        with self.assertRaises(R.RecipeError) as cm:
            R.prepare("soul-ballad", _built_up_sheet(), CLIENT, 58)
        self.assertIn("UNMEASURED: hook_plan", str(cm.exception))
        with self.assertRaises(R.RecipeError) as cm:
            R.prepare("soul-ballad", _early_sheet(), CLIENT, 58, hook_plan=PLAN)
        self.assertIn("before 'the_turn'", str(cm.exception))
        self.assertFalse(R.prepare("soul-ballad", _built_up_sheet(), CLIENT, 58, hook_plan=PLAN)["exempt"])


class Proportional(unittest.TestCase):
    def test_60_and_300_judged_by_their_own_plan(self):
        w60, w300 = HP.min_first_hook_s("soul-ballad", 58), HP.min_first_hook_s("soul-ballad", 298)
        self.assertLess(w60, w300)
        self.assertLess(w60 / 58, 0.5)                    # still leaves room for the 60 s hooks
        self.assertGreater(w60, 5)                        # but never at the opening
        s = _built_up_sheet()
        sheet = [s[0], s[1], s[2], s[6], s[3], s[7], s[8]]   # intro, vocalise, verse, hook, verse, hook, outro
        world = {"true_at_beat": "the_world"}
        words = [{"word": "[Intro (spoken)]\nOne ", "startS": 0.5},
                 {"word": "[Verse 1 (sung)]\nThe ", "startS": 3.0},
                 {"word": "[Hook (sung)]\nGirl, ", "startS": w60 + 1},
                 {"word": "[Verse 2 (sung)]\nShe ", "startS": w60 + 8},
                 {"word": "[Hook 2 (sung)]\nGirl, ", "startS": w60 + 16},
                 {"word": "[Outro (spoken)]\nLink ", "startS": 50}]
        words.insert(1, {"word": "[Vocalise (sung)]\nOo ", "startS": 2.0})
        self.assertEqual(HP.check_returned(sheet, words, "soul-ballad", 58, world)["verdict"], "PASS")
        late = HP.check_returned(sheet, words, "rnb-flow", 298, world)
        self.assertEqual(late["verdict"], "FAIL")
        self.assertIn("inside the", late["reasons"][-1])


GOLDEN = os.path.join(os.path.dirname(os.path.dirname(CORE)), "references",
                      "prompt-templates", "fixtures", "suno-sheets")


class GoldenSheets(unittest.TestCase):
    """Every golden sheet through the real gates with its own hook_plan,
    its delivered length and its style (song_contract and guard_request on
    the same sheets: song_contract/test_song_contract.py)."""

    def test_every_golden_sheet_passes_prepare_and_build_request(self):
        names = sorted(n for n in os.listdir(GOLDEN) if n.endswith(".json"))
        self.assertEqual(len(names), 6)
        for name in names:
            g = json.loads(_read(os.path.join(GOLDEN, name)))
            D, sid = g["delivered_s"], g["music_style"]
            sheet = []
            for seg in g["segments"]:
                sheet += R.parse_lyrics(seg["lyrics"])
            hooks = [s for s in sheet if HP.kind_of(s) == "hook"]
            chorus = " ".join(hooks[0]["lines"])           # the client's own words
            plan = g["hook_plan"]
            self.assertEqual(len(HP.plan_for(sheet, D, plan["true_at_beat"], sid)["beats"]),
                             HP.hook_target(D, plan), name)
            self.assertEqual(HP.check_sheet(sheet, sid, D, plan)["reasons"], [], name)
            out = R.prepare(sid, sheet, chorus, None, delivered_s=D, hook_plan=plan)
            self.assertFalse(out["exempt"], name)
            if len(g["segments"]) == 1:                  # one Suno request per segment
                req = R.build_request(sid, sheet, chorus, g["title"], None,
                                      delivered_s=D, hook_plan=plan)
                self.assertEqual(req["lyrics"], out["lyrics"], name)
            # the chorus is never the hook alone (shared hook/chorus rule)
            for h in hooks:
                self.assertGreaterEqual(len(set(h["lines"])), 2, (name, h))
            # a hook moved ahead of the build-up is refused at the same gate
            early = list(sheet)
            first = early.index(hooks[0])
            early.insert(2, early.pop(first))
            with self.assertRaises(R.RecipeError, msg=name):
                R.prepare(sid, early, chorus, None, delivered_s=D, hook_plan=plan)


class MusicDirector(unittest.TestCase):
    def test_director_emits_and_carries_the_hook_plan(self):
        import music_director as MD
        sheet = _built_up_sheet()
        # a spoken close long enough for words_fit's 77.5% sung-share preflight
        sheet[4]["lines"] = ["She showed me how"]
        sheet[-1]["lines"] = ["Girl, I got you. The One-Check class shows you how. Tap the link below today."]
        low = {"true_at_beat": "lowest_point"}
        out = R.prepare("soul-ballad", sheet, CLIENT, 78, hook_plan=low)
        kw = dict(style_id="soul-ballad", client_text=CLIENT, length_s=78)
        req = MD.build_generate_request(out["lyrics"], out["style"], "T",
                                        true_at_beat="lowest_point", **kw)
        self.assertEqual(req["_hook_plan"],
                         {"true_at_beat": "lowest_point", "beats": ["lowest_point", "the_turn"]})
        self.assertNotIn("_hook_plan", req["input"])     # never a KIE field
        # (the class is compared by name: under one pytest process
        # music_director may hold a second import of suno_recipe)
        for plan, why in ((PLAN, "before 'the_turn'"), (None, "UNMEASURED: hook_plan")):
            with self.assertRaises(Exception) as cm:
                MD.build_generate_request(out["lyrics"], out["style"], "T", hook_plan=plan, **kw)
            self.assertEqual(type(cm.exception).__name__, "RecipeError")
            self.assertIn(why, str(cm.exception))


class Returned(unittest.TestCase):
    def test_v2_take_extra_hooks_caught(self):
        sheet = _read(os.path.join(FIX, "one-check-v2-lyrics.txt"))
        r = HP.check_returned(sheet, _json("one-check-v2-g2a-headers.json"), "rnb-flow", D150, PLAN)
        self.assertEqual(r["verdict"], "FAIL")
        self.assertEqual((r["hook_blocks_sheet"], r["hook_blocks_returned"]), (6, 9))
        self.assertIn("added at 13.6 s, 46.3 s, 94.8 s", r["reasons"][0])
        self.assertTrue(any("first hook sung at 8.9 s" in x for x in r["reasons"]), r)

    def test_v1_take_kept_the_sheet_order_but_sang_before_the_turn(self):
        take = _json("one-check-v1-take-headers.json")
        r = HP.check_returned(_read(V1_SHEET), take, "rnb-flow", D150, {"true_at_beat": "the_world"})
        self.assertEqual((r["hook_blocks_sheet"], r["hook_blocks_returned"]), (6, 6))
        self.assertEqual(r["verdict"], "PASS", r)        # Suno kept the sheet's order
        r = HP.check_returned(_read(V1_SHEET), take, "rnb-flow", D150, PLAN)
        self.assertEqual(r["verdict"], "FAIL")           # measured: sung before the turn
        self.assertIn("first hook sung at 23.8 s", r["reasons"][-1])
        self.assertIn("before 'the_turn' starts at 84.6 s", r["reasons"][-1])

    def test_no_headers_is_unmeasured_not_pass(self):
        r = HP.check_returned(_built_up_sheet(), [{"word": "Girl ", "startS": 1}], "soul-ballad", 58, PLAN)
        self.assertEqual(r["verdict"], "FAIL")

    def test_prompt_states_the_order(self):
        for sid in R.suno_style_ids():
            self.assertIn("never opens with the hook", R.style_text(sid, None, "female"))


if __name__ == "__main__":
    unittest.main()
