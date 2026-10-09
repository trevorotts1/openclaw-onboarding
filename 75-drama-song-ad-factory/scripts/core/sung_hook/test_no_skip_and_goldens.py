#!/usr/bin/env python3
"""Round-3 checker points: no gate switches itself off on a missing or
invalid input, and every golden sheet goes through the real director.

  (a) guard_request with no style_id refuses a sheet that carries sung or rap
      sections ("UNMEASURED: style_id"): the One-Check v1 sheet used to pass;
  (b) check_payload with no music_style is "UNMEASURED: music_style", never [];
  (c) a take whose true_at_beat is not a beat, or is the opening beat, FAILS
      check_returned with the same reason check_story gives;
  (d) the words-fit sung share is the style's own FLOOR (the song_contract
      rule): a mostly sung Soul sheet passes, a short one does not, and every
      golden sheet fits its delivered length;
  (e) the director's spelling check reads held vowels ("re-est", "lo-ook",
      "mi-ine") as their words, and still refuses real misspellings;
  (f) every golden sheet names the beat where its hook pays off (never the
      opening beats), carries hook_target(D, plan) hooks, and FAILS when its
      first hook is moved up to right after the build-up.

Dual-mode: python3 core/sung_hook/test_no_skip_and_goldens.py, or pytest.
stdlib only; no network, no spend.
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
import music_director as MD                  # noqa: E402
import protected_names as PN                 # noqa: E402
import suno_recipe as R                      # noqa: E402
import words_fit as W                        # noqa: E402

GOLDEN = os.path.join(os.path.dirname(os.path.dirname(CORE)), "references",
                      "prompt-templates", "fixtures", "suno-sheets")
V1_SHEET = os.path.join(CORE, "suno_recipe", "fixtures", "one-check-lyrics.txt")
V1_TAKE = os.path.join(HERE, "fixtures", "one-check-v1-take-headers.json")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _goldens():
    out = []
    for name in sorted(n for n in os.listdir(GOLDEN) if n.endswith(".json")):
        g = json.loads(_read(os.path.join(GOLDEN, name)))
        text = "\n\n".join(seg["lyrics"] for seg in g["segments"])
        hooks = [s for s in R.parse_lyrics(text) if HP.kind_of(s) == "hook"]
        out.append((name, g, text, " ".join(hooks[0]["lines"])))   # chorus = client's words
    return out


class MissingStyleIsRefused(unittest.TestCase):
    def test_a_no_style_id_with_sung_or_rap_sections(self):
        v1 = _read(V1_SHEET)
        style = R.style_text("rnb-flow", R.parse_lyrics(v1))
        with self.assertRaises(R.RecipeError) as cm:
            R.guard_request(style, v1, None, "Girl, I got you.", 148, hook_plan=None)
        self.assertIn("UNMEASURED: style_id", str(cm.exception))
        for text in ("[Hook (sung): full melody]\nGirl, I got you",
                     "[Verse]\nlines under a tag that names no delivery are sung too"):
            with self.assertRaises(R.RecipeError, msg=text) as cm:
                R.guard_request("warm soul", text, None)
            self.assertIn("UNMEASURED: style_id", str(cm.exception))
        # the director refuses the same sheet (no length: nothing runs before the guard)
        with self.assertRaises(Exception) as cm:
            MD.build_generate_request(v1, style, "T", protected=(
                "Chanel", "Girl I Got You Masterclass", "GirlIGotYouEvent.com"))
        self.assertIn("UNMEASURED: style_id", str(cm.exception))
        # free text with no sections at all is still the caller's (legacy)
        self.assertIsNone(R.guard_request("warm soul", "la la la", None))

    def test_b_payload_with_no_music_style(self):
        name, g, _, _ = _goldens()[0]
        self.assertEqual(R.check_payload(g), [], name)
        bare = {k: v for k, v in g.items() if k != "music_style"}
        self.assertIn("UNMEASURED: music_style", R.check_payload(bare))
        # a hook moved to the very first block is not waved through either
        first = dict(bare, segments=[{"kind": "base", "lyrics": "[Hook (sung): full melody]\n"
                                      "You can rest and still ri-i-ise,\nthe morning in your e-eyes\n\n"
                                      + g["segments"][0]["lyrics"]}])
        self.assertIn("UNMEASURED: music_style", R.check_payload(first))


class InvalidBeatOnATake(unittest.TestCase):
    def test_c_bogus_or_opening_beat_fails_the_take(self):
        sheet, take = _read(V1_SHEET), json.loads(_read(V1_TAKE))
        ok = HP.check_returned(sheet, take, "rnb-flow", 148, {"true_at_beat": "the_world"})
        self.assertEqual(ok["verdict"], "PASS", ok)     # the take itself is in order
        for beat, why in (("bogus", "is not a beat of the story arc"),
                          ("hook", "never the opener")):
            r = HP.check_returned(sheet, take, "rnb-flow", 148, {"true_at_beat": beat})
            self.assertEqual(r["verdict"], "FAIL", (beat, r))
            self.assertIn(why, "; ".join(r["reasons"]))
            self.assertEqual(r["reasons"],
                             HP.check_story(sheet, {"true_at_beat": beat}, 148, "rnb-flow"))


class WordsFitFloor(unittest.TestCase):
    def test_d_sung_share_is_the_styles_floor(self):
        # mostly sung Soul: over the 77.5% target is never a miss
        r = W.preflight(300, 200, 5, style="soul-ballad")
        self.assertEqual(r["outcome"], "ok", r.get("detail"))
        self.assertEqual(r["sung_target_pct"], 77.5)
        # short of the floor by more than the band is still refused
        r = W.preflight(300, 20, 80, style="soul-ballad")
        self.assertEqual(r["reason_code"], "SHARE_OFF_TARGET", r.get("detail"))
        # R&B Flow uses its own target (the share its length plan sings)
        self.assertEqual(W.style_sung_target_pct("rnb-flow", 148), 71.1)
        self.assertEqual(W.style_sung_target_pct("rnb-flow", 298), 66.0)
        self.assertEqual(W.style_sung_target_pct("soul-rise", 598), 77.5)
        self.assertEqual(W.style_sung_target_pct(None, 58), 77.5)
        for name, g, text, _ in _goldens():
            fit = W.preflight_sheet(g["delivered_s"], text, style=g["music_style"])
            self.assertEqual(fit["outcome"], "ok", (name, fit.get("detail")))
            self.assertLessEqual(fit["plan_s"], g["delivered_s"], name)


class HeldVowels(unittest.TestCase):
    def test_e_held_vowels_are_words_misspellings_are_not(self):
        for line in ("but I can't re-est,", "She handed me a bo-ook, just lo-ook,",
                     "this heart is mi-ine,", "I rise before the su-un,", "I slowed it dow-own,"):
            self.assertEqual(PN.check_lyrics_spelling(line), [], line)
        for line, bad in (("but I can't re-esst,", "esst"), ("just lo-oik,", "oik"),
                          ("I cleaned the kitchan", "kitchan")):
            errs = PN.check_lyrics_spelling(line)
            self.assertTrue(errs and bad in errs[0], (line, errs))


class GoldenSheets(unittest.TestCase):
    def test_f_story_beat_is_real_and_can_fail(self):
        early_beats = HP._LF.STORY_ARC_U16[:2]          # "hook", "the_world": start at 0 s
        for name, g, text, client in _goldens():
            D, sid, plan = g["delivered_s"], g["music_style"], g["hook_plan"]
            self.assertNotIn(plan["true_at_beat"], early_beats, name)
            n = sum(1 for s in R.parse_lyrics(text) if HP.kind_of(s) == "hook")
            self.assertEqual(n, HP.hook_target(D, plan), name)
            self.assertEqual(HP.check_story(text, plan, D, sid), [], name)
            # move the first hook up to right after the build-up: still built up,
            # but before its beat, so the story check FAILS it
            blocks = text.split("\n\n")
            kinds = [HP.kind_of(R.parse_lyrics(b)[0]) if R.parse_lyrics(b) else "other"
                     for b in blocks]
            need = HP.buildup(sid, D)
            cut = max(kinds.index(k) for k in need) + 1
            first = kinds.index("hook")
            early = blocks[:cut] + [blocks[first]] + [b for i, b in enumerate(blocks[cut:], cut)
                                                      if i != first]
            early = "\n\n".join(early)
            self.assertEqual(HP.check_buildup(early, sid, D), [], name)
            errs = HP.check_story(early, plan, D, sid)
            self.assertTrue(any("before %r" % plan["true_at_beat"] in e for e in errs), (name, errs))

    def test_every_golden_sheet_goes_through_the_director(self):
        for name, g, text, client in _goldens():
            req = MD.build_generate_request(text, g["style"], g["title"], style_id=g["music_style"],
                                            client_text=client, length_s=g["delivered_s"],
                                            true_at_beat=g["hook_plan"]["true_at_beat"])
            self.assertEqual(req["_hook_plan"]["true_at_beat"], g["hook_plan"]["true_at_beat"], name)
            self.assertNotIn("_hook_plan", req["input"], name)


if __name__ == "__main__":
    unittest.main()
