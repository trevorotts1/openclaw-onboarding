#!/usr/bin/env python3
"""S75-T20 / S75-A20: the three executable rap recipes.

Melodic Rap, Trap Rap and Pop Rap each compile distinct production
directions into the actual style field. Proves, stdlib only and with zero
paid calls:

  1. three stable recipe ids; exact client labels/descriptions;
  2. each recipe compiles DIFFERENT provider text carrying its own
     instrumentation identity (melodic piano/808/hook, trap 808/hats,
     pop bright bass/pop drums);
  3. client recognition references are display-only and never serialized
     into any provider style text;
  4. rap counts as spoken delivery under the accepted share policy;
  5. trap arrangement words are not read as rap delivery, and Trap Rap
     never enables explicitness by itself;
  6. the three original D18 strings stay byte-for-byte identical;
  7. all six durations resolve for each rap recipe.

Dual-mode -- plain python3 and pytest:

    python3 core/music_styles/test_rap_recipes_t20.py
    python3 -m pytest core/music_styles/test_rap_recipes_t20.py
"""
from __future__ import annotations

import ast
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import music_styles as MS  # noqa: E402  module under test
import suno_recipe.suno_recipe as SR  # noqa: E402

RAP_IDS = ("melodic-rap", "trap-rap", "pop-rap")

EXACT = {
    "melodic-rap": ("Melodic Rap",
                    "emotional rap that moves between rhythmic lines and a "
                    "tuneful hook."),
    "trap-rap": ("Trap Rap",
                 "punchy rap over deep bass and crisp, rolling hi-hats, "
                 "with a strong hook."),
    "pop-rap": ("Pop Rap",
                "upbeat, easy-to-follow rap with a bright, catchy pop hook."),
}

#: Frozen D18 strings -- hard rule: byte-for-byte identical.
FROZEN = {
    "soul-ballad": ("Soul Ballad",
                    "slow, heartfelt singing; builds to a big emotional "
                    "chorus."),
    "rnb-flow": ("R&B Flow",
                 "rhythmic rap verses, then a smooth sung hook you "
                 "remember."),
    "soul-rise": ("Soul Rise",
                  "starts slow and sad, then lifts into an upbeat, hopeful "
                  "groove."),
}


class RapRecipesTest(unittest.TestCase):

    def test_01_three_stable_ids(self):
        self.assertEqual(MS.recipe_ids(), RAP_IDS)
        for sid in RAP_IDS:
            rec = MS.recipe(sid)
            self.assertEqual(rec["style_id"], sid)
            self.assertEqual(rec["recipe_revision"], MS.RAP_RECIPE_REVISION)
            self.assertTrue(rec["production_traits"]["genre"])

    def test_02_exact_labels_and_descriptions(self):
        for sid, (label, description) in EXACT.items():
            rec = MS.recipe(sid)
            self.assertEqual(rec["label"], label)
            self.assertEqual(rec["description"], description)

    def test_03_compiled_prompts_are_distinct(self):
        prompts = {sid: MS.style_prompt(sid) for sid in RAP_IDS}
        self.assertEqual(len(set(prompts.values())), 3, prompts)
        self.assertIn("melodic rap", prompts["melodic-rap"])
        self.assertIn("pitched melodic hook", prompts["melodic-rap"])
        self.assertIn("808", prompts["trap-rap"])
        self.assertIn("hi-hats", prompts["trap-rap"])
        self.assertIn("pop rap", prompts["pop-rap"])
        self.assertIn("bright bass", prompts["pop-rap"])
        # trap is not pop rap's bright bed, and vice versa
        self.assertNotIn("bright bass", prompts["trap-rap"])
        self.assertNotIn("rolling hi-hats", prompts["pop-rap"])

    def test_04_client_references_never_serialized(self):
        for sid in RAP_IDS:
            refs = MS.recipe(sid)["client_references"]
            self.assertTrue(refs, "%s must keep display references" % sid)
            for field in (MS.style_prompt(sid),
                          MS.style(sid)["suno_style_prompt"],
                          MS.style_prompt(sid, sheet_text="[Rap]\nline\n"
                                                         "[Sung]\nhook")):
                for name in refs:
                    self.assertNotIn(name, field,
                                     "%s leaked into a provider field" % name)

    def test_05_delivery_map_speaks_raps_sings(self):
        for sid in RAP_IDS:
            prompt = MS.style_prompt(sid)
            self.assertIn("SPEAKS", prompt)
            self.assertIn("RAPS", prompt)
            self.assertIn("SINGS", prompt)
            sheet = "[Spoken] open\n[Rap] verse\n[Sung] hook"
            self.assertIn("RAPS", MS.style_prompt(sid, sheet_text=sheet))

    def test_06_rap_counts_as_spoken_share(self):
        segs = [
            {"delivery": "spoken", "seconds": 12.0, "source": "measured"},
            {"delivery": "rap", "seconds": 60.0, "source": "measured"},
            {"delivery": "sung", "seconds": 48.0, "source": "measured"},
        ]
        m = MS.measure_share(segs)
        self.assertAlmostEqual(m["rap_seconds"], 60.0)
        self.assertAlmostEqual(m["spoken_style_seconds"], 72.0)
        self.assertAlmostEqual(m["share"], 0.6, places=6)
        self.assertTrue(m["rap_counts_as_spoken"])
        verdict = MS.check_share("trap-rap", 120, m["share"], segments=segs)
        self.assertEqual(verdict["verdict"], "FAIL")  # 60% is over the cap
        self.assertTrue(verdict["rap_counts_as_spoken"])

    def test_07_rap_share_pass_inside_band(self):
        segs = [
            {"delivery": "spoken", "seconds": 12.0, "source": "measured"},
            {"delivery": "rap", "seconds": 15.0, "source": "measured"},
            {"delivery": "sung", "seconds": 93.0, "source": "measured"},
        ]
        m = MS.measure_share(segs)
        verdict = MS.check_share("melodic-rap", 120, m["share"], segments=segs)
        self.assertEqual(verdict["verdict"], "PASS", verdict["reasons"])

    def test_08_trap_word_is_not_rap_delivery(self):
        self.assertIsNone(SR.parse_tag("Trap Beat"))
        self.assertEqual(SR.parse_tag("Trap Rap"), "rap")
        self.assertEqual(SR.parse_tag("808 Trap"), None)

    def test_09_trap_never_enables_explicitness(self):
        for sid in RAP_IDS:
            self.assertFalse(MS.enables_explicit_lyrics(sid))
            self.assertIs(MS.recipe(sid)["explicit_lyrics"], False)
        self.assertIn("trap-rap", MS.EXPLICIT_NEVER_INFERRED)
        prompt = MS.style_prompt("trap-rap").lower()
        self.assertNotIn("explicit", prompt)
        self.assertNotIn("profan", prompt)
        self.assertIn("no profanity",
                      MS.recipe("trap-rap")["production_traits"]["negatives"])

    def test_10_original_three_unchanged(self):
        for sid, (label, _description) in FROZEN.items():
            self.assertEqual(MS.STYLES[sid]["label"], label)
            self.assertEqual(MS.style_ids()[tuple(FROZEN).index(sid)], sid)
            self.assertTrue(MS.style_prompt(sid).startswith(
                MS.STYLES[sid]["suno_style_prompt"].rstrip(".,")))
        # the spoken-share band is one band, every style, every length
        for sid in RAP_IDS + tuple(MS.style_ids()):
            for secs in MS.OFFERED_LENGTHS_S:
                t = MS.spoken_target(sid, secs)
                self.assertEqual((t["floor"], t["cap"]),
                                 (MS.SPOKEN_SHARE_MIN, MS.SPOKEN_SHARE_MAX))

    def test_11_six_durations(self):
        self.assertEqual(tuple(MS.OFFERED_LENGTHS_S),
                         (60, 90, 120, 180, 300, 600))
        for sid in RAP_IDS:
            for secs in MS.OFFERED_LENGTHS_S:
                self.assertEqual(MS.spoken_target(sid, secs)["length_seconds"],
                                 secs)

    def test_12_label_lookup_and_unknown(self):
        self.assertEqual(MS.style("Melodic Rap")["style_id"], "melodic-rap")
        self.assertEqual(MS.style("trap rap")["style_id"], "trap-rap")
        with self.assertRaises(MS.MusicStyleError):
            MS.style("bossa-nova")

    def test_13_stdlib_only(self):
        with open(os.path.join(HERE, "music_styles.py"),
                  encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        banned = ("requests", "urllib", "httpx", "socket", "subprocess",
                  "http.client")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                self.assertFalse(any(b in name for b in banned),
                                 "%s imports %s" % ("music_styles.py", name))


if __name__ == "__main__":
    unittest.main(verbosity=2)
