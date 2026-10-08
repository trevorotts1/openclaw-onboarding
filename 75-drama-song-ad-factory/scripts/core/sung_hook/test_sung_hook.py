#!/usr/bin/env python3
"""I8 sung hook tests. Dual-mode:

    python3 core/sung_hook/test_sung_hook.py
    python3 -m pytest core/sung_hook/test_sung_hook.py
"""
from __future__ import annotations

import os
import sys
import unittest

CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import sung_hook as H              # noqa: E402
import suno_recipe as R            # noqa: E402

CLIENT = "We keep the lights on for every family. Come home to Dolce, come home tonight."
HOOK = ["Come home to Dolce", "come home tonight"]
VERSES = [{"tag": "Verse %d" % i, "delivery": "spoken", "lines": ["We keep the lights on"]}
          for i in range(1, 5)]
STYLE = "all_suno"


def seg(d, a, b):
    return {"delivery": d, "start": a, "end": b, "source": "measured"}


def words_at(*starts):
    out = []
    for t in starts:
        for k, w in enumerate("come home to dolce come home tonight".split()):
            out.append({"word": w, "startS": t + k * 0.5, "endS": t + k * 0.5 + 0.4})
    return out


class Formula(unittest.TestCase):
    def test_table(self):
        for length, want in [(28, 2), (58, 3), (88, 4), (118, 5), (178, 8), (298, 12), (598, 12)]:
            self.assertEqual(H.hook_count(length), want, length)

    def test_bad_length(self):
        for bad in (0, -5, None, "x"):
            with self.assertRaises(ValueError):
                H.hook_count(bad)

    def test_times(self):
        t = H.hook_times(118)
        self.assertEqual(len(t), 5)
        self.assertAlmostEqual(t[0], 0.15 * 118, 1)
        self.assertAlmostEqual(t[-1], 0.90 * 118, 1)
        self.assertEqual(t, sorted(t))


class HookText(unittest.TestCase):
    def test_own_words_and_length(self):
        self.assertEqual(H.check_hook_text(HOOK, CLIENT), [])
        self.assertTrue(H.check_hook_text("come home", CLIENT))                 # too short
        self.assertTrue(H.check_hook_text("come home to Dolce, forever more", CLIENT))  # invented
        self.assertTrue(H.check_hook_text("come home to dolce tonight", CLIENT, ["Dolce"]))


class Sheet(unittest.TestCase):
    def test_hook_count_and_positions(self):
        for length in (28, 58, 88, 118, 178, 298, 598):
            sheet = H.build_lyric_sheet(VERSES, HOOK, length)
            self.assertEqual(H.check_sheet_count(sheet, HOOK, length), [], length)
            hooks = [i for i, s in enumerate(sheet) if s["tag"] == "Hook"]
            self.assertEqual(len(hooks), H.hook_count(length))
            self.assertLessEqual(hooks[0], 1)
            self.assertEqual(hooks[-1], len(sheet) - 1)

    def test_wrong_count_rejected(self):
        sheet = H.build_lyric_sheet(VERSES, HOOK, 58)
        self.assertTrue(H.check_sheet_count(sheet, HOOK, 118))

    def test_recipe_enforces_count_for_every_suno_style(self):
        for sid in R.suno_style_ids():
            sheet = H.build_lyric_sheet(VERSES, HOOK, 118)
            self.assertEqual(R.prepare(sid, sheet, CLIENT, 118)["exempt"], False)
            with self.assertRaises(R.RecipeError):
                R.prepare(sid, H.build_lyric_sheet(VERSES, HOOK, 58), CLIENT, 118)

    def test_voiceover_exempt(self):
        self.assertEqual(R.hook_target("velvet_voiceover", 118), 0)
        self.assertEqual(R.hook_target(STYLE, 118), 5)
        self.assertEqual(R.prepare("velvet_voiceover", [], CLIENT, 118), {"exempt": True})


class Measured(unittest.TestCase):
    SUNG = [seg("sung", 0, 40)]

    def test_all_sung_passes(self):
        r = H.measure("come home to dolce", words_at(5, 15, 25), self.SUNG, 3)
        self.assertEqual((r["verdict"], r["measured"], r["action"]), ("PASS", 3, "accept"))
        self.assertEqual(r["times_s"], [5, 15, 25])

    def test_one_short_flags(self):
        r = H.measure("come home to dolce", words_at(5, 15), self.SUNG, 3)
        self.assertEqual((r["verdict"], r["action"]), ("FLAG", "accept-with-flag"))

    def test_two_short_regenerates(self):
        r = H.measure("come home to dolce", words_at(5), self.SUNG, 3)
        self.assertEqual((r["verdict"], r["action"]), ("FAIL", "regenerate"))

    def test_spoken_occurrence_not_counted(self):
        segs = [seg("spoken", 0, 20), seg("sung", 20, 60)]
        r = H.measure("come home to dolce", words_at(5, 15, 25), segs, 3)
        self.assertEqual(r["measured"], 1)

    def test_labels_are_not_measurement(self):
        segs = [dict(seg("sung", 0, 40), source="label")]
        self.assertEqual(H.measure("come home to dolce", words_at(5, 15), segs, 2)["verdict"], "FAIL")

    def test_score_take_carries_receipt(self):
        take = {"segments": [seg("spoken", 0, 4), seg("sung", 4, 40)]}
        out = R.score_take(take, "come home to dolce", words_at(5), 58)
        self.assertEqual(out["hook"]["target"], 3)
        self.assertEqual(out["hook"]["measured"], 1)
        self.assertEqual(out["verdict"], "FAIL")


if __name__ == "__main__":
    unittest.main()
