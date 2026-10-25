#!/usr/bin/env python3
"""S75-T19 focused tests: the five story-first production recipes.

  * the five ids are owned, disjoint from the three original styles, and
    keep their exact client descriptions byte-for-byte;
  * each recipe compiles a distinct full production prompt carrying its own
    instrumentation, vocal behaviour, rhythm, tunable tempo, story energy,
    hook shape and spoken/sung split;
  * every prompt is dry-word clean and free of display-only reference names;
  * all six offered durations are accepted and produce distinct guidance;
  * the word-fit budget follows the section 3 formula;
  * unknown styles (e.g. another unit's `reggaeton`) and unknown durations
    are refused rather than guessed.

Dual-mode -- plain python3 and pytest:

    python3 core/music_styles/test_recipes_s75_t19.py
    python3 -m pytest core/music_styles/test_recipes_s75_t19.py
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

if CORE not in sys.path:
    sys.path.insert(0, CORE)

import music_styles as MS          # noqa: E402  the shared contract
from music_styles import recipes as R   # noqa: E402  module under test

SIX = (60, 90, 120, 180, 300, 600)

#: Exact client descriptions, MUSIC-AND-VIDEO-UX.md section 2.
EXPECTED_DESCRIPTIONS = {
    "acoustic-pop": "warm acoustic guitar, clear storytelling, and a catchy "
                    "sung chorus.",
    "folk-storytelling": "intimate, detail-rich storytelling over simple "
                         "acoustic instruments.",
    "country-pop": "plainspoken country storytelling with a polished, "
                   "memorable pop chorus.",
    "alternative-rnb": "intimate, spacious R&B with inventive textures, "
                       "flexible grooves, and an expressive vocal.",
    "afro-soul": "soulful vocals over warm, organic instruments and "
                 "interlocking African-influenced rhythms.",
}

#: One phrase that must reach the payload for each recipe's identity.
MARKERS = {
    "acoustic-pop": "fingerpicked steel-string acoustic guitar",
    "folk-storytelling": "spare picked acoustic guitar",
    "country-pop": "pedal steel",
    "alternative-rnb": "negative space",
    "afro-soul": "interlocking hand percussion",
}


def _load_no_echo():
    cached = sys.modules.get("_t19_core_no_echo")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(
        "_t19_core_no_echo", os.path.join(NO_ECHO_DIR, "no_echo.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["_t19_core_no_echo"] = mod
    return mod


NE = _load_no_echo()
PROMPTS = {sid: R.compile_style_prompt(sid) for sid in R.recipe_ids()}


class OwnedScopeTests(unittest.TestCase):
    def test_five_ids_and_exact_descriptions(self):
        self.assertEqual(R.recipe_ids(), (
            "acoustic-pop", "folk-storytelling", "country-pop",
            "alternative-rnb", "afro-soul"))
        for sid, want in EXPECTED_DESCRIPTIONS.items():
            self.assertEqual(R.catalog_entry(sid)["description"], want, sid)

    def test_scope_is_disjoint_from_the_original_three(self):
        self.assertEqual(set(R.recipe_ids()) & set(MS.style_ids()), set())
        self.assertEqual(set(MS.style_ids()),
                         {"soul-ballad", "rnb-flow", "soul-rise"})

    def test_original_three_prompts_stay_byte_for_byte(self):
        # The three originals as shipped on main: a drift is a regression.
        frozen = {
            "soul-ballad": (
                "soul ballad, slow emotional 62-68 bpm, warm felt piano, "
                "brushed kit entering at the chorus, deep rounded bass, "
                "soulful lead vocal with melismatic runs, close dry upfront "
                "vocal, minor key, restrained verse opening into a "
                "full-voiced chorus, no distortion."),
            "rnb-flow": (
                "contemporary r&b with hip-hop flow, 84-94 bpm, crisp "
                "programmed drums with tight hats, deep sub bass, Rhodes "
                "chord stabs, bright synth plucks, rhythmic rap verses "
                "delivered with clear diction over the beat, smooth sung r&b "
                "hook, call-and-response ad-libs, confident swagger, dry "
                "upfront vocal, radio-ready mix, no vocals in the intro pad"),
            "soul-rise": (
                "soul with a two-part arc, brooding 62-68 bpm opening lifting "
                "to an upbeat 100-112 bpm groove at the turn, warm piano and "
                "round bass foundation, percussion thickening as it lifts, "
                "triumphant horn stabs and claps from the turnaround, hopeful "
                "minor-to-major resolution, soulful lead vocal rising in "
                "register, close dry upfront vocal, single continuous take"),
        }
        labels = {"soul-ballad": "Soul Ballad", "rnb-flow": "R&B Flow",
                  "soul-rise": "Soul Rise"}
        for sid, base in frozen.items():
            rec = MS.style(sid)
            self.assertEqual(rec["label"], labels[sid])
            self.assertEqual(rec["suno_style_prompt"], base, sid)
            self.assertTrue(MS.style_prompt(sid).startswith(base.rstrip(".")),
                            "%s prompt drifted" % sid)

    def test_unknown_style_is_refused_not_guessed(self):
        for other in ("reggaeton", "trap-rap", "contemporary-gospel"):
            with self.assertRaises(R.RecipeError) as ctx:
                R.compile_style_prompt(other)
            self.assertEqual(ctx.exception.code, "UNKNOWN_RECIPE")


class CompileTests(unittest.TestCase):
    def test_each_recipe_compiles_its_own_traits(self):
        for sid, marker in MARKERS.items():
            text = PROMPTS[sid]
            self.assertTrue(text.strip(), sid)
            self.assertIn(marker, text, "%s lost its instrumentation" % sid)
            self.assertIn("bpm", text, sid)
            self.assertIn("The lead SPEAKS the lines tagged Spoken", text, sid)
            self.assertIn("SINGS the lines tagged Sung", text, sid)

    def test_prompts_are_pairwise_distinct(self):
        self.assertEqual(len(set(PROMPTS.values())), 5)

    def test_compiled_prompts_are_banned_word_free(self):
        for sid, text in PROMPTS.items():
            hits = [w for w in NE.SONG_BANNED_STYLE_WORDS
                    if re.search(r"\b%s\b" % w, text, re.IGNORECASE)]
            self.assertEqual(hits, [], "%s prompt names %s" % (sid, hits))

    def test_delivery_map_follows_the_sheet(self):
        sheet = "[Spoken] the cost\n[Sung Verse] the chorus"
        text = R.compile_style_prompt("country-pop", sheet_text=sheet)
        self.assertIn("The lead SPEAKS", text)
        self.assertIn("SINGS", text)
        self.assertNotIn("RAPS", text)
        rap_sheet = "[Spoken] the cost\n[Rap Verse] the argument\n[Sung] the hook"
        rap_text = R.compile_style_prompt("alternative-rnb",
                                          sheet_text=rap_sheet)
        self.assertIn("RAPS the lines tagged Rap", rap_text)

    def test_reference_names_never_reach_the_payload(self):
        for sid, text in PROMPTS.items():
            self.assertEqual(R.find_client_references(text), [], sid)
        self.assertIn("Tems", R.reference_aliases())
        with self.assertRaises(R.RecipeError) as ctx:
            R.assert_no_client_references(
                "warm pop, in the spirit of Ed Sheeran and Jason Mraz")
        self.assertEqual(ctx.exception.code, "ARTIST_REFERENCE_IN_PROMPT")

    def test_display_metadata_is_separate_from_traits(self):
        entry = R.catalog_entry("afro-soul")
        self.assertEqual(entry["label"], "Afro-Soul")
        self.assertIn("Tems", entry["client_references"]["artists"])
        self.assertNotIn("client_references", R.production_traits("afro-soul"))

    def test_alternative_rnb_is_not_automatically_sad(self):
        self.assertIn("never automatically slow, sad or whispered",
                      PROMPTS["alternative-rnb"])
        self.assertIn("mood chosen from the approved story",
                      PROMPTS["alternative-rnb"])

    def test_afro_soul_is_not_automatically_dance_pop(self):
        self.assertIn(
            "neither automatically slow and sad nor automatically club "
            "dance-pop", PROMPTS["afro-soul"])
        self.assertIn("interlocking African-influenced hand-percussion "
                      "rhythms", PROMPTS["afro-soul"])


class DurationAndStoryTests(unittest.TestCase):
    def test_all_six_durations_compile_distinct_guidance(self):
        for sid in R.recipe_ids():
            seen = set()
            for secs in SIX:
                text = R.compile_style_prompt(sid, duration=secs)
                self.assertIn("at %g seconds:" % secs, text, (sid, secs))
                guidance = R.duration_guidance(sid, secs)
                self.assertTrue(guidance.strip(), (sid, secs))
                seen.add(guidance)
            self.assertEqual(len(seen), 6, "%s repeats duration guidance" % sid)

    def test_unknown_duration_is_refused(self):
        for bad in (150, "75s"):
            with self.assertRaises(R.RecipeError) as ctx:
                R.compile_style_prompt("acoustic-pop", duration=bad)
            self.assertEqual(ctx.exception.code, "UNKNOWN_DURATION", bad)
        with self.assertRaises(R.RecipeError) as ctx:
            R.compile_style_prompt("acoustic-pop", duration=True)
        self.assertEqual(ctx.exception.code, "BAD_DURATION")

    def test_energy_map_follows_the_causal_turn(self):
        stages = ("consequence", "obstacle", "choice", "change", "hook", "cta")
        for sid in R.recipe_ids():
            traits = R.production_traits(sid)
            self.assertEqual(tuple(traits["energy_map"]), stages, sid)
            texts = [R.energy_for_stage(sid, s) for s in stages]
            self.assertEqual(len(set(texts)), 6, sid)
            turn = (traits["energy_map"]["change"]
                    + " " + traits["energy_map"]["hook"]).lower()
            self.assertIn("after", turn,
                          "%s hook/change does not follow the turn" % sid)
            self.assertTrue(traits["story_energy"].strip(), sid)

    def test_word_fit_budget_formula(self):
        for sid in R.recipe_ids():
            short = R.word_fit(sid, 60)
            long = R.word_fit(sid, 600)
            self.assertEqual(short["instrumental_only_seconds"], 3.0)
            self.assertEqual(short["breath_allowance_seconds"], 3.6)
            self.assertEqual(short["available_vocal_seconds"], 53.4)
            self.assertEqual(long["available_vocal_seconds"], 561.0)
            self.assertLess(short["available_vocal_seconds"],
                            long["available_vocal_seconds"])
            self.assertIn("measure", short["basis"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
