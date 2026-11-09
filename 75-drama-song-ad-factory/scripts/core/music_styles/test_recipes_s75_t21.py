#!/usr/bin/env python3
"""S75-T21 focused tests: Pop Rock, Reggaeton and Country Rap.

Two jobs, in this order:

1. S75-T21's own three records compile -- through the SAME composer the live
   styles use -- into a provider-ready style field carrying the one clean
   ending, the FU-HOOK-PLACEMENT order clause, the G1 delivery map, the band
   wording and the 1000-character cap.
2. The eight recipes coexist at this head: S75-T19's five (their JSON carriers
   present, their ids resolving to non-empty compiled content through their
   own accepted compiler) and S75-T21's three, disjoint, with no accepted
   carrier deleted.

Controls, so a clean run is not a stuck-accept:
  * known-good -- every one of the five + three compiles to non-empty output;
  * composer identity -- ``mock.patch`` proves both this module's
    ``compile_style`` and the live ``style_text`` enter the ONE
    ``compose_style_block`` (a second copy would not be called);
  * instrument -- a deliberately broken record (missing key, missing trait,
    wrong revision, empty word fit, an undeclared delivery verb) is REFUSED,
    while the untouched record passes the same validator;
  * leak detector -- the reference guard is shown to fire on a planted name.

Dual-mode -- plain python3 and pytest:

    python3 core/music_styles/test_recipes_s75_t21.py
    python3 -m pytest core/music_styles/test_recipes_s75_t21.py
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from music_styles import catalog as C          # noqa: E402  S75-T18 menu
from music_styles import music_styles as MS    # noqa: E402  the shared contract
from music_styles import recipes as T19        # noqa: E402  S75-T19's five
from music_styles import recipes_s75_t21 as R  # noqa: E402  module under test
from suno_recipe import duration_registry as DR                        # noqa: E402
import suno_recipe.suno_recipe as SR           # noqa: E402  the ONE composer
from words_fit import words_fit as WF          # noqa: E402  the word-fit gate

T21_IDS = ("pop-rock", "reggaeton", "country-rap")
T19_IDS = ("acoustic-pop", "folk-storytelling", "country-pop",
           "alternative-rnb", "afro-soul")
EIGHT = T19_IDS + T21_IDS

DESCRIPTIONS = {
    "pop-rock": "driving guitars and drums with a big, singable chorus.",
    "reggaeton": "a rolling dembow groove, rhythmic vocals, and a danceable "
                 "chorus.",
    "country-rap": (
        "Country storytelling meets rock power and hip-hop rhythm. Gritty, "
        "soulful singing and rhythmic rap verses build into a big, emotional "
        "chorus. Think acoustic guitars, heavy drums, deep bass and "
        "electric-guitar lift, with stories about struggle, regret, "
        "resilience and redemption."),
}

REFERENCE_NAMES = {
    "pop-rock": {"Maroon 5", "Paramore"},
    "reggaeton": {"Daddy Yankee", "Bad Bunny"},
    "country-rap": {"Jelly Roll"},
}

#: Files whose deletion would remove an ACCEPTED unit's carrier. This branch
#: adds to them; a red here means a merge dropped one of them.
ACCEPTED_CARRIERS = (
    "catalog.py",
    "recipes.py",
    "recipes_s75_t22.py",
    "music_styles.py",
    "test_catalog_s75t18.py",
    "test_rap_recipes_t20.py",
    "test_recipes_s75_t19.py",
    "test_recipes_s75_t22.py",
    os.path.join("recipes", "acoustic-pop.json"),
    os.path.join("recipes", "folk-storytelling.json"),
    os.path.join("recipes", "country-pop.json"),
    os.path.join("recipes", "alternative-rnb.json"),
    os.path.join("recipes", "afro-soul.json"),
)

RAP_SHEET = [{"tag": "Rap Verse", "delivery": "rap", "lines": ["a line"]}]
SUNG_SHEET = [{"tag": "Chorus", "delivery": "sung", "lines": ["a held line"]}]
ALL_SHEET = [{"tag": "Intro", "delivery": "spoken", "lines": ["a plain line"]},
             {"tag": "Verse", "delivery": "rap", "lines": ["a rhythmic line"]},
             {"tag": "Chorus", "delivery": "sung", "lines": ["a held line"]}]


def compiled(style_id, **kw):
    kw.setdefault("vocal_gender", "female")
    return R.compile_style(style_id, **kw)


class RegistryScopeTests(unittest.TestCase):
    def test_recipe_ids_are_exactly_the_three_owned_styles(self):
        self.assertEqual(R.recipe_ids(), T21_IDS)

    def test_disjoint_from_t19_and_from_the_frozen_originals(self):
        self.assertEqual(set(R.recipe_ids()) & set(T19.recipe_ids()), set())
        self.assertEqual(set(R.recipe_ids()) & set(MS.style_ids()), set())
        self.assertEqual(set(MS.style_ids()),
                         {"soul-ballad", "rnb-flow", "soul-rise"})

    def test_unknown_style_refuses_instead_of_aliasing(self):
        for other in ("soul-ballad", "acoustic-pop", "trap-rap"):
            with self.assertRaises(R.RecipeError) as caught:
                R.compile_style(other)
            self.assertEqual(caught.exception.code, "UNKNOWN_STYLE", other)

    def test_one_schema_version_and_one_revision_across_the_registry(self):
        self.assertEqual(R.SCHEMA_VERSION,
                         "blackceo.music-styles/s75-t21-recipes/v1")
        for sid in R.recipe_ids():
            record = R.load_recipe(sid)
            self.assertEqual(record["schema_version"], R.SCHEMA_VERSION, sid)
            self.assertEqual(record["recipe_revision"], R.RECIPE_REVISION, sid)
            self.assertEqual(set(record), set(R.load_recipe("pop-rock")), sid)

    def test_the_records_agree_with_the_s18_menu_record(self):
        # S75-T18 owns the catalog; this owner must not drift from it.
        for sid in R.recipe_ids():
            mine, menu = R.load_recipe(sid), C.CATALOG[sid]
            self.assertEqual(mine["label"], menu["label"], sid)
            self.assertEqual(mine["description"], menu["description"], sid)
            self.assertEqual(tuple(mine["deliveries"]),
                             tuple(menu["deliveries"]), sid)
            self.assertEqual(tuple(mine["client_references"]["artists"]),
                             tuple(menu["client_references"]), sid)


class DescriptionTests(unittest.TestCase):
    """The owner-supplied descriptions are byte-exact, never merely similar.

    ``DESCRIPTIONS`` is the approved copy (MUSIC-AND-VIDEO-UX 4.18 for Country
    Rap); this pins the records to it so a silent reword fails here.
    """

    def test_each_description_is_the_approved_string(self):
        for sid in T21_IDS:
            self.assertEqual(R.load_recipe(sid)["description"],
                             DESCRIPTIONS[sid], sid)


class ComposeTests(unittest.TestCase):
    def test_every_recipe_compiles_provider_ready_within_the_cap(self):
        for sid in R.recipe_ids():
            text = compiled(sid)
            self.assertTrue(text.strip(), sid)
            self.assertLessEqual(len(text), SR.SUNO_STYLE_FIELD_MAX, sid)
            self.assertEqual(SR.check_style_text(text), [], sid)
            self.assertTrue(text.startswith(
                R.load_recipe(sid)["style_parts"][0].rstrip(".,")), sid)

    def test_every_recipe_carries_the_one_clean_ending(self):
        for sid in R.recipe_ids():
            self.assertIn(SR._EQ.STYLE_ENDING, compiled(sid), sid)

    def test_every_recipe_carries_the_hook_order_clause(self):
        for sid in R.recipe_ids():
            text = compiled(sid)
            self.assertIn(SR._HP.PROMPT_CLAUSE, text, sid)
            self.assertIn("never opens with the hook", text, sid)

    def test_every_recipe_carries_the_band_wording(self):
        for sid in R.recipe_ids():
            self.assertIn("the full band keeps playing continuously under them",
                          compiled(sid), sid)

    def test_delivery_map_is_exactly_the_declared_set(self):
        for sid in R.recipe_ids():
            declared = set(R.load_recipe(sid)["deliveries"])
            upper = compiled(sid).upper()
            for delivery, verb in MS.DELIVERY_MAP_VERBS.items():
                self.assertEqual(verb in upper, delivery in declared,
                                 (sid, delivery))

    def test_gender_comes_from_the_brief(self):
        for sid in R.recipe_ids():
            self.assertIn("male lead", compiled(sid, vocal_gender="m"), sid)
            self.assertNotIn("{gender}", compiled(sid, vocal_gender="m"), sid)

    def test_the_approved_pace_clause_fits_under_the_cap(self):
        plan = {"drop": SR.PACE_DROP_CLAUSE, "return": SR.PACE_RETURN_CLAUSE}
        for sid in R.recipe_ids():
            text = compiled(sid, pace_plan=plan)
            self.assertLessEqual(len(text), SR.SUNO_STYLE_FIELD_MAX,
                                 (sid, len(text)))
            self.assertIn(SR.PACE_DROP_CLAUSE, text, sid)
            self.assertIn(SR.PACE_RETURN_CLAUSE, text, sid)

    def test_the_three_are_distinct_from_each_other_and_from_every_other_style(self):
        texts = [compiled(sid) for sid in R.recipe_ids()]
        self.assertEqual(len(set(texts)), 3)
        others = [MS.style_prompt(sid) for sid in MS.style_ids()]
        others += [T19.compile_style_prompt(sid) for sid in T19.recipe_ids()]
        for text in texts:
            self.assertNotIn(text, others)
        self.assertEqual(len(set(others + texts)), len(others) + 3)


class ComposerIdentityTests(unittest.TestCase):
    """The composer is ONE implementation, proved by interception.

    A second copy of the ending/hook/map/cap logic inside the recipe loader
    would not enter ``compose_style_block``; these two tests would then fail.
    """

    def test_compile_style_enters_the_live_composer(self):
        real = SR.compose_style_block
        with mock.patch.object(SR, "compose_style_block",
                               wraps=real) as spy:
            text = R.compile_style("pop-rock")
        self.assertEqual(spy.call_count, 1)
        block = spy.call_args[0][0]
        self.assertEqual(block["style_id"], "pop-rock")
        self.assertEqual(len(text), len(real(block)))

    def test_the_live_style_text_enters_the_same_composer(self):
        real = SR.compose_style_block
        with mock.patch.object(SR, "compose_style_block",
                               wraps=real) as spy:
            SR.style_text("soul-ballad")
        self.assertEqual(spy.call_count, 1)
        self.assertEqual(spy.call_args[0][0]["style_id"], "soul-ballad")


class DeliveryMapRefusalTests(unittest.TestCase):
    def test_a_rap_sheet_on_a_spoken_sung_recipe_refuses(self):
        for sid in ("pop-rock", "reggaeton"):
            with self.assertRaises(MS.MusicStyleError) as caught:
                R.compile_style(sid, sheet=RAP_SHEET)
            self.assertEqual(caught.exception.code, "NO_DELIVERY_MAP", sid)
            self.assertIs(R.style_error_type(), MS.MusicStyleError)

    def test_a_declared_delivery_compiles(self):
        self.assertTrue(R.compile_style("pop-rock", sheet=SUNG_SHEET))
        text = R.compile_style("country-rap", sheet=ALL_SHEET)
        for verb in ("SPEAKS", "RAPS", "SINGS"):
            self.assertIn(verb, text)


class PopRockTests(unittest.TestCase):
    def test_guitar_and_live_kit_dynamics_compile(self):
        text = compiled("pop-rock")
        for needle in ("electric guitars", "kick and snare", "wide guitars",
                       "electric bass", "dry upfront vocal",
                       "no electronic dance drop"):
            self.assertIn(needle, text, needle)
        traits = R.production_traits("pop-rock")
        self.assertEqual(traits["tempo_bpm"], (100, 142))
        self.assertEqual(traits["meter"], "4/4")

    def test_pop_rock_never_claims_rap_delivery(self):
        record = R.load_recipe("pop-rock")
        self.assertNotIn("rap", record["deliveries"])
        self.assertFalse(record["rap_allowed"])


class ReggaetonTests(unittest.TestCase):
    def test_dembow_identity_compiles(self):
        text = compiled("reggaeton")
        for needle in ("dembow", "sub bass", "syncopated percussion",
                       "tuneful repeatable hook", "danceable chorus",
                       "no four-on-the-floor pulse"):
            self.assertIn(needle, text, needle)
        self.assertEqual(R.production_traits("reggaeton")["tempo_bpm"],
                         (88, 105))

    def test_spanish_and_explicitness_are_never_auto_selected(self):
        text = compiled("reggaeton")
        low = text.lower()
        self.assertNotIn("spanish", low)
        self.assertNotIn("explicit", low)
        self.assertNotIn("spanish", R.negative_tags("reggaeton").lower())
        rules = " ".join(
            R.production_traits("reggaeton")["delivery_constraints"]).lower()
        self.assertIn("never automatically translates english into spanish",
                      rules)
        self.assertIn("never turns explicitness on", rules)


class CountryRapTests(unittest.TestCase):
    def test_country_texture_hip_hop_rhythm_and_guitar_lift_compile(self):
        text = compiled("country-rap")
        for needle in ("acoustic guitar", "country guitar figure",
                       "hip-hop kick and snare", "deep bass",
                       "electric-guitar lift", "strongly sung chorus",
                       "conversational rap", "close dry upfront vocal"):
            self.assertIn(needle, text, needle)
        self.assertEqual(R.production_traits("country-rap")["tempo_bpm"],
                         (74, 100))

    def test_rap_and_sung_directions_are_both_declared(self):
        text = compiled("country-rap")
        self.assertIn("RAPS the lines tagged Rap", text)
        self.assertIn("SINGS the lines tagged Sung", text)
        self.assertTrue(R.load_recipe("country-rap")["rap_allowed"])

    def test_a_reference_artist_never_becomes_a_client_fact(self):
        rules = " ".join(
            R.production_traits("country-rap")["delivery_constraints"]).lower()
        self.assertIn("never infer addiction, incarceration, violence or "
                      "religion", rules)


class ReferenceGuardTests(unittest.TestCase):
    def test_only_client_display_metadata_names_an_artist(self):
        for sid in R.recipe_ids():
            refs = R.client_references(sid)
            self.assertTrue(refs["display_only"], sid)
            self.assertEqual(set(refs["artists"]), REFERENCE_NAMES[sid], sid)

    def test_no_artist_name_reaches_an_outgoing_field(self):
        for sid in R.recipe_ids():
            self.assertEqual(R.client_reference_leaks(compiled(sid)), [], sid)
            self.assertEqual(R.client_reference_leaks(
                R.negative_tags(sid)), [], sid)
            self.assertEqual(R.client_reference_leaks(
                R.menu_record(sid)["suno_style_prompt"]), [], sid)

    def test_the_leak_check_actually_detects(self):
        self.assertEqual(R.client_reference_leaks(
            "in the style of Jelly Roll"), ["Jelly Roll"])


class MenuRecordTests(unittest.TestCase):
    def test_menu_record_is_catalog_shaped(self):
        for sid in R.recipe_ids():
            row = R.menu_record(sid)
            self.assertEqual(row["style_id"], sid)
            self.assertEqual(row["sound"], R.load_recipe(sid)["description"])
            self.assertEqual(row["suno_style_prompt"],
                             R.load_recipe(sid)["style_parts"][0])
            self.assertEqual(set(row["deliveries"]),
                             set(R.load_recipe(sid)["deliveries"]))

    def test_the_catalog_already_owns_the_three_ids_so_nothing_is_registered(self):
        # Proof this owner did not register: the catalog's own register_style
        # refuses every one of them as a duplicate, and its validator passes.
        for sid in R.recipe_ids():
            with self.assertRaises(C.CatalogError) as caught:
                C.register_style(R.menu_record(sid))
            self.assertEqual(caught.exception.code, "DUPLICATE_STYLE", sid)
        self.assertEqual(C.validate_catalog(), C.MAX_STYLES)
        self.assertEqual(C.MAX_STYLES, 18)


class WordFitTests(unittest.TestCase):
    def test_word_fit_is_read_and_clean_for_every_recipe(self):
        for sid in R.recipe_ids():
            self.assertGreaterEqual(len(R.word_fit(sid).split()),
                                    R.WORD_FIT_MIN_WORDS, sid)
            self.assertEqual(R.word_fit_findings(R.load_recipe(sid)), [], sid)

    def test_each_recipe_keeps_its_own_word_fit(self):
        self.assertEqual(len({R.word_fit(sid) for sid in R.recipe_ids()}), 3)

    def test_the_verifier_rejects_guidance_from_another_style(self):
        record = R.load_recipe("pop-rock")
        record["production_traits"]["word_fit"] = (
            "fit stressed syllables to the dembow groove with clean endings; "
            "never stretch critical business words across inaudible effects.")
        self.assertTrue(R.word_fit_findings(record))

    def test_the_verifier_rejects_sacrificing_protected_words(self):
        record = R.load_recipe("reggaeton")
        record["production_traits"]["word_fit"] = (
            "cut the CTA when the line runs long; fit syllables to the groove.")
        self.assertTrue(any("cut" in f
                            for f in R.word_fit_findings(record)))


class WordFitLyricFixtureTests(unittest.TestCase):
    """Word fit priced on REAL lyric words through core/words_fit.

    Each fixture is a tagged Suno sheet of actual lyric lines, run through the
    gate that decides whether words fit the length (``parse_sheet_words`` +
    ``preflight_sheet``). None of the three recipes is in ``STYLE_RATES``, so
    every one prices fail-closed at the calm-ballad rates -- sung 1.0 w/s,
    spoken 1.85 w/s, rap 2.0 w/s -- with 8 s of intro/outro. The expected
    numbers are hand-computed from the words on the page, so a gate that
    stopped counting words, stopped pricing rap, or stopped refusing a sheet
    that cannot fit fails here instead of passing quietly.
    """

    POP_ROCK_SHEET = (
        "[Spoken - lead, plain natural speech over the music]\n"
        "We kept counting every quiet hour in this house.\n"
        "[Sung - lead, long held notes]\n"
        "So take the long way home with me tonight.\n"
        "We are still here and the light is on our side.\n")

    COUNTRY_RAP_SHEET = (
        "[Spoken - lead, plain natural speech over the music]\n"
        "Mama kept the porch light on all night.\n"
        "[Rap - lead, confident metered flow]\n"
        "One check, one shot, we rise from dirt.\n"
        "[Sung - lead, long held notes]\n"
        "So we carry every promise over the county line.\n"
        "And the morning finds us standing where we fell.\n"
        "Still we rise with the light upon our side.\n")

    OVER_LONG_SHEET = (
        "[Sung - lead, long held notes]\n"
        "We drive all night to meet the morning on the road.\n"
        "Every window down and every voice is singing now.\n"
        "Hold the line and keep the rhythm moving through the dark.\n"
        "Take my hand and let the beat carry us home.\n"
        "We are louder than the fear that kept us quiet.\n"
        "Rise up now and let the whole room hear it.\n"
        "Nothing left to lose and everything to claim tonight.\n"
        "Sing it back to me until the daylight finds us.\n"
        "[Rap - lead, confident metered flow]\n"
        "We move fast and we never drop the beat.\n"
        "Hands up high when the bass is in the floor.\n"
        "Say the word and I meet you at the door.\n")

    def test_the_fixtures_are_real_counted_lyric_words(self):
        self.assertEqual(WF.parse_sheet_words(self.POP_ROCK_SHEET), (20, 9, 0))
        self.assertEqual(WF.parse_sheet_words(self.COUNTRY_RAP_SHEET),
                         (27, 8, 8))
        self.assertEqual(WF.parse_sheet_words(self.OVER_LONG_SHEET),
                         (80, 0, 29))

    def test_recipes_price_word_fit_fail_closed(self):
        for sid in R.recipe_ids():
            self.assertEqual(WF.rates_for(sid), WF.DEFAULT_RATES, sid)

    def test_word_fit_passes_the_card_on_the_hand_computed_plan(self):
        # The carded length decides the sung target (it is length-derived, not
        # one flat 77.5%): country-rap holds a 76.4% sung share, which is 5.4
        # points short of the 90 s target and inside the band at 180 s. The
        # words themselves price the same at every length.
        for sid, sheet, length_s, plan_s, dur_s in (
                ("pop-rock", self.POP_ROCK_SHEET, 90, 32.865, 37.795),
                ("country-rap", self.COUNTRY_RAP_SHEET, 180, 43.324, 49.823)):
            verdict = WF.preflight_sheet(length_s, sheet, style=sid)
            self.assertEqual(verdict["outcome"], "ok", sid)
            self.assertEqual(verdict["reason_code"], "WORDS_FIT_OK", sid)
            self.assertEqual(verdict["length_s"], float(length_s), sid)
            self.assertEqual(verdict["plan_s"], plan_s, sid)
            self.assertEqual(verdict["suno_duration_s"], dur_s, sid)
            self.assertLessEqual(verdict["gap_pts"], WF.BAND_PTS, sid)
            self.assertGreaterEqual(verdict["sung_share_pct"],
                                    verdict["sung_target_pct"] - WF.BAND_PTS,
                                    sid)
            sung, spoken, rap = WF.parse_sheet_words(sheet)
            self.assertEqual((verdict["sung_words"], verdict["spoken_words"],
                              verdict["rap_words"]),
                             (float(sung), float(spoken), float(rap)), sid)

    def test_word_fit_refuses_a_sheet_whose_words_cannot_fit_the_card(self):
        # 80 sung + 29 rap words need 80 + 14.5 + 8 = 102.5 s: no 90 s card.
        verdict = WF.preflight_sheet(90, self.OVER_LONG_SHEET, style="reggaeton")
        self.assertEqual(verdict["outcome"], "waiting")
        self.assertEqual(verdict["reason_code"], "WORDS_DO_NOT_FIT")
        self.assertEqual(verdict["plan_s"], 102.5)
        options = verdict["options"]
        self.assertEqual(set(options),
                         {"longer_ad", "lower_sung_target", "fewer_words"})
        self.assertEqual(options["longer_ad"]["length_s"], 120)
        self.assertLess(options["fewer_words"]["max_total_words"], 109.0)
        self.assertGreater(options["fewer_words"]["cut_words"], 0.0)


class InstrumentControlTests(unittest.TestCase):
    """The known-good record PASSES and the broken ones are REFUSED, so a
    clean run cannot be a validator that accepts everything."""

    def test_a_valid_record_passes_the_same_validator(self):
        for sid in R.recipe_ids():
            record = R.load_recipe(sid)
            self.assertIs(R.validate_record(record), record, sid)

    def test_a_missing_required_key_is_refused(self):
        record = R.load_recipe("pop-rock")
        del record["style_parts"]
        with self.assertRaises(R.RecipeError) as caught:
            R.validate_record(record)
        self.assertEqual(caught.exception.code, "RECIPE_MISSING_FIELD")

    def test_a_missing_production_trait_is_refused(self):
        record = R.load_recipe("reggaeton")
        del record["production_traits"]["hook_guidance"]
        with self.assertRaises(R.RecipeError) as caught:
            R.validate_record(record)
        self.assertEqual(caught.exception.code, "RECIPE_MISSING_FIELD")

    def test_a_wrong_revision_is_refused(self):
        record = R.load_recipe("country-rap")
        record["recipe_revision"] = "s75-t20/1"
        with self.assertRaises(R.RecipeError) as caught:
            R.validate_record(record)
        self.assertEqual(caught.exception.code, "RECIPE_BAD_REVISION")

    def test_an_empty_word_fit_is_refused(self):
        record = R.load_recipe("pop-rock")
        record["production_traits"]["word_fit"] = ""
        with self.assertRaises(R.RecipeError) as caught:
            R.validate_record(record)
        self.assertEqual(caught.exception.code, "RECIPE_BAD_WORD_FIT")

    def test_an_undeclared_delivery_verb_is_refused(self):
        record = R.load_recipe("pop-rock")
        record["style_parts"] = record["style_parts"][:2] + (
            "The lead RAPS the lines tagged Rap.",) + record["style_parts"][3:]
        with self.assertRaises(R.RecipeError) as caught:
            R.validate_record(record)
        self.assertEqual(caught.exception.code, "RECIPE_UNDECLARED_DELIVERY")

    def test_a_missing_gender_slot_is_refused(self):
        record = R.load_recipe("reggaeton")
        record["style_parts"] = (record["style_parts"][0],
                                 "the lead sings the hook",
                                 record["style_parts"][2],
                                 record["style_parts"][3])
        with self.assertRaises(R.RecipeError) as caught:
            R.validate_record(record)
        self.assertEqual(caught.exception.code, "RECIPE_BAD_STYLE_PARTS")


class InheritedRuleTests(unittest.TestCase):
    def test_the_six_durations_are_the_one_registry(self):
        self.assertEqual(DR.CANONICAL_DURATION_S, (60, 90, 120, 180, 300, 600))
        for sid in R.recipe_ids():
            self.assertEqual(R.production_traits(sid)["duration_policy"],
                             "suno_recipe.duration_registry.CANONICAL_DURATION_S")

    def test_opening_and_lip_sync_rules_are_preserved(self):
        self.assertEqual(R.OPENING_SPOKEN_SECONDS, 12)
        self.assertEqual(R.VISIBLE_LIP_SYNC_TARGET_PCT, (25, 30))
        self.assertEqual(R.VISIBLE_LIP_SYNC_CAP_PCT, 35)
        for sid in R.recipe_ids():
            traits = R.production_traits(sid)
            self.assertEqual(traits["opening_spoken_seconds"], 12, sid)
            self.assertEqual(traits["visible_lip_sync"]["target_pct"],
                             [25, 30], sid)
            self.assertEqual(traits["visible_lip_sync"]["hard_cap_pct"], 35,
                             sid)


class EightRecipeCoexistenceTests(unittest.TestCase):
    """S75-T19's five and S75-T21's three live together at this head."""

    def test_the_eight_ids_are_unique_and_disjoint(self):
        self.assertEqual(set(R.recipe_ids()), set(T21_IDS))
        self.assertEqual(set(T19.recipe_ids()), set(T19_IDS))
        self.assertEqual(len(set(EIGHT)), 8)
        self.assertEqual(set(T19.recipe_ids()) | set(R.recipe_ids()),
                         set(EIGHT))

    def test_the_five_t19_json_carriers_are_present_and_parse(self):
        for name in T19_IDS:
            path = os.path.join(HERE, "recipes", "%s.json" % name)
            self.assertTrue(os.path.isfile(path), path)
            with open(path, encoding="utf-8") as handle:
                self.assertEqual(json.load(handle)["style_id"], name, name)

    def test_every_one_of_t19_five_resolves_to_non_empty_compiled_content(self):
        for sid in T19_IDS:
            record = T19.load_recipe(sid)
            self.assertEqual(record["style_id"], sid)
            text = T19.compile_style_prompt(sid)
            self.assertTrue(text.strip(), sid)
            self.assertGreater(len(text), 400, sid)
            upper = text.upper()
            for delivery in record["deliveries"]:
                self.assertIn(MS.DELIVERY_MAP_VERBS[delivery], upper,
                              (sid, delivery))

    def test_every_one_of_t21_three_compiles_under_the_one_composer(self):
        for sid in T21_IDS:
            self.assertTrue(compiled(sid).strip(), sid)

    def test_the_eight_are_pairwise_distinct(self):
        texts = [T19.compile_style_prompt(sid) for sid in T19_IDS]
        texts += [compiled(sid) for sid in T21_IDS]
        self.assertEqual(len(set(texts)), 8)

    def test_no_accepted_carrier_was_deleted(self):
        for name in ACCEPTED_CARRIERS:
            self.assertTrue(os.path.isfile(os.path.join(HERE, name)), name)

    def test_the_sibling_suites_are_still_here(self):
        for name in ("test_recipes_s75_t19.py", "test_catalog_s75t18.py",
                     "test_rap_recipes_t20.py", "test_recipes_s75_t22.py"):
            self.assertTrue(os.path.isfile(os.path.join(HERE, name)), name)


class ZeroSpendTests(unittest.TestCase):
    def test_no_transport_in_the_owned_source(self):
        with open(os.path.join(HERE, "recipes_s75_t21.py"),
                  encoding="utf-8") as handle:
            source = handle.read()
        for needle in ("urllib", "http.client", "requests", "socket",
                       "subprocess"):
            self.assertNotIn(needle, source, needle)


if __name__ == "__main__":
    unittest.main(verbosity=2)
