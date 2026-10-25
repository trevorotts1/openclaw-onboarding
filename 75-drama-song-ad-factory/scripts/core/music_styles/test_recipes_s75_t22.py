#!/usr/bin/env python3
"""S75-T22 focused checks: the four orchestral / theater / gospel recipes.

Each check names its failure so a verdict says which invariant broke. Real
code under test, no provider call, no paid generation.

Dual-mode -- plain python3 and pytest:

    python3 core/music_styles/test_recipes_s75_t22.py
    python3 -m pytest core/music_styles/test_recipes_s75_t22.py
"""
from __future__ import annotations

import importlib.util
import inspect
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
NO_ECHO_DIR = os.path.join(CORE, "audio_c3", "no_echo")
INTAKE = os.path.join(CORE, "choice_card", "intake_card", "intake_card.py")

for path in (CORE, NO_ECHO_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

import music_styles as MS                     # noqa: E402  shared choke point
import recipes_s75_t22 as R                   # noqa: E402  module under test


def _load_no_echo():
    cached = sys.modules.get("_t22_core_no_echo")
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(
        "_t22_core_no_echo", os.path.join(NO_ECHO_DIR, "no_echo.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["_t22_core_no_echo"] = mod
    return mod


NE = _load_no_echo()

#: The three originals, byte-for-byte (owner hard rule, S75-T22).
ORIGINAL_SENTENCES = {
    "soul-ballad": "slow, heartfelt singing; builds to a big emotional "
                   "chorus.",
    "rnb-flow": "rhythmic rap verses, then a smooth sung hook you remember.",
    "soul-rise": "starts slow and sad, then lifts into an upbeat, hopeful "
                 "groove.",
}

#: The four descriptions from MUSIC-AND-VIDEO-UX.md section 2, exact bytes.
EXPECTED_DESCRIPTIONS = {
    "cinematic-orchestral-song": (
        "a dramatic song with sweeping strings and a powerful film-style "
        "chorus. Keep the singing and spoken words clear and easy to hear, "
        "even when the music gets big and powerful."),
    "musical-theater": (
        "character-driven singing and dialogue that build into a dramatic "
        "stage-style payoff."),
    "contemporary-gospel": (
        "faith-centered singing with piano, organ, and a powerful choir that "
        "builds from testimony to an uplifting chorus."),
    "urban-gospel": (
        "faith-centered singing with R&B and hip-hop grooves, choir responses, "
        "and a memorable gospel hook."),
}


class OriginalsUntouched(unittest.TestCase):
    def test_original_three_stay_byte_identical(self):
        with open(INTAKE, encoding="utf-8") as fh:
            source = fh.read()
        for sid, sentence in ORIGINAL_SENTENCES.items():
            self.assertIn('"%s": "%s"' % (sid, sentence), source,
                          "%s description changed in intake_card" % sid)
            self.assertIn(sid, MS.STYLES)

    def test_this_module_adds_no_style_to_the_shared_table(self):
        for sid in R.style_ids():
            self.assertNotIn(sid, MS.STYLES,
                             "%s must be merged by the catalog owner, not "
                             "injected at import" % sid)


class RecipeShape(unittest.TestCase):
    def test_four_ids_in_spec_order(self):
        self.assertEqual(R.style_ids(), (
            "cinematic-orchestral-song", "musical-theater",
            "contemporary-gospel", "urban-gospel"))

    def test_labels_and_descriptions_are_exact(self):
        labels = {
            "cinematic-orchestral-song": "Cinematic Orchestral Song",
            "musical-theater": "Musical Theater",
            "contemporary-gospel": "Contemporary Gospel",
            "urban-gospel": "Urban Gospel",
        }
        for sid, sentence in EXPECTED_DESCRIPTIONS.items():
            rec = R.recipe(sid)
            self.assertEqual(rec["label"], labels[sid], sid)
            self.assertEqual(rec["description"], sentence, sid)
            self.assertEqual(rec["recipe_revision"], R.RECIPE_REVISION, sid)
            for field in ("instrumentation", "avoided_instrumentation",
                          "tempo_range_bpm", "meter", "vocal_delivery",
                          "energy_map", "hook_guidance",
                          "delivery_constraints", "story_dynamics",
                          "negative_constraints", "provider_clauses"):
                self.assertTrue(rec["production_traits"][field],
                                "%s has an empty %s" % (sid, field))

    def test_every_style_keeps_the_shared_rules(self):
        self.assertEqual(R.SHARED_RULES["durations_s"],
                         (60, 90, 120, 180, 300, 600))
        self.assertEqual(tuple(R.SHARED_RULES["durations_s"]),
                         tuple(MS.OFFERED_LENGTHS_S))
        self.assertEqual(R.SHARED_RULES["spoken_opener_seconds"], 12)
        self.assertEqual(R.SHARED_RULES["visible_lip_sync_target"], (0.25, 0.30))
        self.assertEqual(R.SHARED_RULES["visible_lip_sync_cap"], 0.35)
        self.assertFalse(R.SHARED_RULES["invents_client_facts"])


class CompiledField(unittest.TestCase):
    def test_compile_is_clause_only_and_deterministic(self):
        for sid in R.style_ids():
            text = R.compile_style_field(sid)
            self.assertEqual(text, R.compile_style_field(sid), sid)
            self.assertEqual(
                text,
                ", ".join(R.RECIPES[sid]["production_traits"]
                          ["provider_clauses"]), sid)

    def test_compile_takes_no_client_input(self):
        params = list(inspect.signature(R.compile_style_field).parameters)
        self.assertEqual(params, ["style_id"],
                         "a client argument would let a fact reach the payload")

    def test_four_fields_are_pairwise_distinct(self):
        fields = {sid: R.compile_style_field(sid) for sid in R.style_ids()}
        ids = list(fields)
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                self.assertNotEqual(fields[a], fields[b],
                                    "%s and %s compile identically" % (a, b))

    def test_f13_dry_style_ban_is_clean(self):
        for sid in R.style_ids():
            self.assertEqual(NE.refused_song_style_words(
                R.compile_style_field(sid)), [],
                "%s names an F13-banned song-style word" % sid)

    def test_no_artist_name_or_alias_reaches_the_field(self):
        for sid in R.style_ids():
            text = R.compile_style_field(sid)
            self.assertEqual(R.client_reference_hits(text, sid), [], sid)
            R.assert_no_client_reference(text, sid)

    def test_alias_guard_actually_fires(self):
        for sid in R.style_ids():
            with self.assertRaises(MS.MusicStyleError) as ctx:
                R.assert_no_client_reference(
                    "build it like Kirk Franklin, Adele and Idina Menzel", sid)
            self.assertEqual(ctx.exception.code,
                             "CLIENT_REFERENCE_IN_PAYLOAD")

    def test_no_language_explicitness_or_route_is_chosen(self):
        for sid in R.style_ids():
            text = R.compile_style_field(sid).lower()
            for banned in ("spanish", "profanity", "explicit", "route",
                           "provider", "voice gender"):
                self.assertNotIn(banned, text, "%s selects %r" % (sid, banned))


class OrchestralStaysASong(unittest.TestCase):
    def test_orchestral_requests_a_lyrical_vocal_song(self):
        sid = "cinematic-orchestral-song"
        rec = R.recipe(sid)
        text = R.compile_style_field(sid)
        self.assertIn("lead vocal", text)
        self.assertIn("sung refrain", text)
        self.assertIn("sung", rec["deliveries"])
        self.assertNotIn("instrumental-only cut", text)
        self.assertIn("no instrumental-only cut",
                      rec["production_traits"]["negative_constraints"])

    def test_orchestral_description_keeps_the_client_sentence(self):
        self.assertIn(
            "Keep the singing and spoken words clear and easy to hear, even "
            "when the music gets big and powerful.",
            R.recipe("cinematic-orchestral-song")["description"])


class TheaterAndGospel(unittest.TestCase):
    def test_theater_dialogue_is_optional_not_automatic(self):
        rec = R.recipe("musical-theater")
        traits = rec["production_traits"]
        delivery = " ".join(traits["delivery_constraints"])
        negative = " ".join(traits["negative_constraints"])
        self.assertIn("only if already approved", delivery)
        self.assertIn("no invented ensemble", negative)
        for word in ("must sing dialogue", "automatic reprise",
                     "add dialogue"):
            self.assertNotIn(word, R.compile_style_field("musical-theater"))

    def test_gospel_styles_stay_separate(self):
        contemp = R.compile_style_field("contemporary-gospel").lower()
        urban = R.compile_style_field("urban-gospel").lower()
        for text in (contemp, urban):
            self.assertIn("faith-centered", text)
        self.assertIn("organ", contemp)
        self.assertIn("backing vocal ensemble", contemp)
        self.assertNotIn("hip-hop", contemp)
        self.assertIn("hip-hop groove", urban)
        self.assertIn("rap", urban)
        self.assertIn("rap", R.recipe("urban-gospel")["deliveries"])

    def test_gospel_invents_no_client_fact(self):
        for sid in ("contemporary-gospel", "urban-gospel"):
            text = R.compile_style_field(sid).lower()
            for fact in ("church affiliation", "conversion", "sermon",
                         "testimony of the client", "denomination"):
                self.assertNotIn(fact, text, "%s states a client fact" % sid)
            for key in ("language_locked_to_client",
                        "vocal_gender_locked_to_client",
                        "explicitness_locked_to_client"):
                self.assertTrue(R.SHARED_RULES[key], key)


class CatalogSeam(unittest.TestCase):
    """The compiled field must reach the real style_prompt choke point."""

    def setUp(self):
        self._saved = dict(MS.STYLES)

    def tearDown(self):
        MS.STYLES.clear()
        MS.STYLES.update(self._saved)

    def test_four_records_merge_and_render(self):
        MS.STYLES.update(R.as_catalog_entries())
        for sid in R.style_ids():
            rendered = MS.style_prompt(sid)
            self.assertTrue(rendered.startswith(R.compile_style_field(sid)),
                            "%s compiled clauses did not reach style_prompt"
                            % sid)
            for verb in ("SPEAKS", "SINGS") if sid != "urban-gospel" else (
                    "SPEAKS", "RAPS", "SINGS"):
                self.assertIn(verb, rendered, "%s missing %s" % (sid, verb))
            self.assertEqual(NE.refused_song_style_words(rendered), [], sid)
            self.assertEqual(R.client_reference_hits(rendered, sid), [], sid)
            target = MS.spoken_target(sid, 180)
            self.assertEqual(target["style_id"], sid)

    def test_describe_is_display_only(self):
        for sid in R.style_ids():
            menu = R.describe(sid)
            self.assertEqual(set(menu), {
                "style_id", "label", "description", "client_references",
                "recipe_revision"})
            self.assertNotIn("provider", menu)


if __name__ == "__main__":
    unittest.main(verbosity=2)
