#!/usr/bin/env python3
"""U8 tests: captions caught early. Stdlib only, zero network, zero paid calls.

Every test here is a way the skill used to lose a string that ends up on
screen (the One-Check run: "could’ve" split into "could" + "ve" so a
misspelled contraction passed; "Girl, I got you-u" was burned as written;
a misspelled lyric word was first seen at delivery):

  (a) "could’ve" (U+2019) tokenises to "could've";
  (b) "Girl, I got you-u" builds the caption "Girl, I got you";
  (c) a misspelled lyric word is refused BEFORE any Suno payload is built;
  (d) a keyframe request with unchecked on-screen text is refused;
  (e) the script gate requires the spelling and grammar record;
  (f) a client typo goes back as a QUESTION and is never auto-fixed.

    python3 core/test_captions_early_u8.py
    python3 -m pytest core/test_captions_early_u8.py
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = HERE  # this test lives in scripts/core beside the modules it checks
for sub in ("", "intake_preflight"):
    p = os.path.join(CORE, sub)
    if p not in sys.path:
        sys.path.insert(0, p)

import protected_names as P  # noqa: E402  module under test
import intake as I  # noqa: E402  module under test
import qc_gate as G  # noqa: E402  module under test

#: The typographic apostrophe a client storyboard really carries.
CURLY = "’"


def curve(text):
    return text.replace("'", CURLY)


def aligned(words):
    return [{"word": w, "start": float(i), "end": float(i) + 0.5}
            for i, w in enumerate(words)]


class TokensSurviveTheTypographicApostrophe(unittest.TestCase):
    """(a) The word splitter is ASCII only; a storyboard is not."""

    def test_curly_contraction_is_one_word(self):
        self.assertEqual(P._tokens(curve("could've")), ["could've"])

    def test_curly_contraction_tokens_the_plain_way(self):
        self.assertEqual(P._tokens(curve("could've")),
                         P._tokens("could've"))

    def test_curly_yall_is_one_word(self):
        self.assertEqual(P._tokens(curve("Y'all")), ["y'all"])

    def test_wrong_contraction_is_named_by_the_spelling_check(self):
        # "could'nt" is not a word whichever apostrophe is used, so the
        # check must SEE it (today the curly form splits into "could" and
        # "nt" and the fragment passes).
        errs = P.check_spelling([curve("I could'nt stay")])
        self.assertTrue(any("could'nt" in e for e in errs), errs)


class DisplaySpellingReachesTheCaption(unittest.TestCase):
    """(b) Performance spelling is for the singer, not for the screen."""

    SHEET = "[Sung - lead, long held notes]\nGirl, I got you-u"

    def test_held_vowel_collapses(self):
        self.assertEqual(P.display_text("Girl, I got you-u").split()[-1],
                         "you")

    def test_caption_text_is_the_display_spelling(self):
        cues = P.build_captions(self.SHEET,
                                aligned(["girl", "i", "got", "you", "u"]))
        self.assertEqual([c["text"] for c in cues], ["Girl, I got you"])

    def test_a_real_hyphenated_word_is_left_alone(self):
        self.assertEqual(P.display_text("no-one knows"), "no-one knows")

    def test_wordless_vocalise_makes_no_cue(self):
        sheet = ("[Vocalise]\nOo-o-o-o-o-oh,\n"
                 "[Sung - lead]\nI got you-u")
        cues = P.build_captions(sheet, aligned(["i", "got", "you", "u"]))
        self.assertEqual([c["text"] for c in cues], ["I got you"])

    def test_captions_still_match_the_display_sheet(self):
        cues = P.build_captions(self.SHEET,
                                aligned(["girl", "i", "got", "you", "u"]))
        self.assertEqual(P.check_captions(cues, self.SHEET), [])


class LyricSpellingRefusedBeforeSuno(unittest.TestCase):
    """(c) A misspelled word is refused before any payload is built."""

    GOOD = "[Sung - lead, ballad]\nI cleaned the kitchen all day"

    def setUp(self):
        import music_director
        self.md = music_director
        self._saved = self.md._cat
        self.md._cat = {"suno-generate": {
            "route_models": {"current": "ai-music-api/generate V6"},
            "model_default": "V6", "model_enum": ["V4", "V5", "V6"]}}

    def tearDown(self):
        self.md._cat = self._saved

    def test_clean_sheet_still_builds(self):
        req = self.md.build_generate_request(self.GOOD, "ballad", "T")
        self.assertIn("kitchen", req["input"]["lyrics"])

    def test_misspelled_sheet_is_refused_and_builds_nothing(self):
        bad = self.GOOD.replace("kitchen", "kitchan")
        with self.assertRaises(ValueError) as cm:
            self.md.build_generate_request(bad, "ballad", "T")
        self.assertIn(P.CODE_LYRIC, str(cm.exception))
        self.assertIn("kitchan", str(cm.exception))

    def test_performance_spelling_is_not_a_misspelling(self):
        # The recipe NEEDS hyphen holds and wordless vocalise; they must not
        # be what the spelling gate refuses.
        sheet = ("[Vocalise]\nOo-o-o-o-o-oh,\n[Sung - lead, ballad]\n"
                 "I am not sma-a-all")
        req = self.md.build_generate_request(sheet, "ballad", "T")
        self.assertIn("sma-a-all", req["input"]["lyrics"])


class OnScreenTextGatedBeforeSpend(unittest.TestCase):
    """(d) A paid keyframe may not print a string nobody checked."""

    MODEL = "gpt-image-2-5-sunburst-text-to-image"
    TEXT = "MANDATORY ALL-STAFF MEETING - 9:00 AM"

    def setUp(self):
        self.kd = importlib.import_module("kie_dispatch.kie_dispatch")

        def _forbid(*_a, **_k):
            raise AssertionError("no dispatch test may spawn a real runner")

        self._saved = self.kd.make_runner
        self.kd.make_runner = _forbid
        self.tmp = tempfile.mkdtemp(prefix="u8-onscreen-")

    def tearDown(self):
        self.kd.make_runner = self._saved

    def _dispatch(self, request):
        return self.kd.dispatch(
            model=self.MODEL, request=request,
            save_dir=os.path.join(self.tmp, "out"),
            ledger_db=os.path.join(self.tmp, "spend.db"),
            run_id="run-u8", logical_key="keyframe-u8", attempt_id="att-1",
            estimated_cost=100, adapter_path=os.path.abspath(__file__))

    def test_unchecked_on_screen_text_is_refused(self):
        env = self._dispatch({"model": self.MODEL,
                              "input": {"prompt": "p" * 200},
                              "on_screen_text": self.TEXT})
        self.assertEqual(env.get("reason_code"),
                         "ONSCREEN_TEXT_NOT_CHECKED", env)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "spend.db")),
                         "a refused job must reserve nothing")

    def test_a_checked_string_passes_this_gate(self):
        request = {"model": self.MODEL, "input": {"prompt": "p" * 200},
                   "on_screen_text": self.TEXT,
                   "onscreen_text_checked": [self.TEXT]}
        self.assertIsNone(self.kd.onscreen_text_refusal(self.MODEL, request))

    def test_a_different_string_is_not_covered_by_an_old_receipt(self):
        request = {"model": self.MODEL, "input": {"prompt": "p" * 200},
                   "on_screen_text": "SALE ENDS AT MIDNIGHT",
                   "onscreen_text_checked": [self.TEXT]}
        self.assertIsNotNone(self.kd.onscreen_text_refusal(self.MODEL, request))

    def test_text_inside_the_shot_block_is_seen_too(self):
        request = {"model": self.MODEL, "input": {"prompt": "p" * 200},
                   "shot": {"on_screen_text": [{"text": self.TEXT}]}}
        self.assertIsNotNone(self.kd.onscreen_text_refusal(self.MODEL, request))


class ScriptGateRequiresSpellingGrammar(unittest.TestCase):
    """(e) The independent script gate carries the spelling/grammar record."""

    def _record(self, check, who):
        return {"schema_version": "1.0.0", "check_id": "qc-" + check,
                "run_id": "run-u8", "stage": "script", "check": check,
                "verdict": "PASS",
                "evidence": {"summary": "u8 fixture %s pass" % check},
                "checker_version": "1.0.0",
                "reviewer": {"identity": who, "session": "u8",
                             "authority": "u8-fixture"}}

    def test_spelling_grammar_is_a_known_check(self):
        self.assertIn("spelling_grammar", G.CHECKS)

    def test_script_stage_requires_the_record(self):
        res = G.evaluate("run-u8", "script", [], {},
                         ["storyboard"])
        named = [f for f in res["failures"]
                 if f.get("check_id") == "spelling_grammar"]
        self.assertTrue(named, res["failures"])

    def test_script_gate_passes_with_the_record(self):
        records = [self._record("storyboard", "reviewer-a"),
                   self._record("spelling_grammar", "reviewer-b")]
        makers = {"qc-storyboard": "maker-storyboard",
                  "qc-spelling_grammar": "maker-script"}
        res = G.evaluate("run-u8", "script", records, makers, ["storyboard"])
        self.assertEqual(res["gate"], "PASS", res)

    def test_other_stages_are_untouched(self):
        res = G.evaluate("run-u8", "final_edit", [], {}, ["timeline"])
        self.assertFalse([f for f in res["failures"]
                          if f.get("check_id") == "spelling_grammar"])


class ClientTypoGoesBackAsAQuestion(unittest.TestCase):
    """(f) The client's own words are asked about, never auto-fixed."""

    BRIEF = {"offer": "The book", "audience": "women 35-55",
             "action": "Buy the book", "budget_minor": 2500,
             "budget_currency": "USD", "placement": "9:16 vertical"}

    def test_a_client_typo_comes_back_as_a_question(self):
        brief = dict(self.BRIEF,
                     packet_lines=["I cleaned the kitchan all day"])
        r = I.evaluate(brief)
        self.assertEqual(r["outcome"], "waiting", r)
        self.assertEqual(r["reason_code"], "client-typo-confirmation", r)
        self.assertIn("kitchan", r["question_message"])

    def test_the_client_text_is_never_rewritten(self):
        text = "I cleaned the kitchan all day"
        brief = dict(self.BRIEF, packet_lines=[text])
        r = I.evaluate(brief)
        self.assertIn(text, brief["packet_lines"])
        self.assertNotIn("kitchen", r["question_message"])

    def test_approved_vernacular_never_asks(self):
        brief = dict(self.BRIEF,
                     packet_lines=["That don't sound soft"],
                     approved_spellings=["dont"])
        r = I.evaluate(brief)
        self.assertNotEqual(r.get("reason_code"), "client-typo-confirmation",
                            r)

    def test_clean_client_words_do_not_ask(self):
        brief = dict(self.BRIEF,
                     packet_lines=["I cleaned the kitchen all day"])
        r = I.evaluate(brief)
        self.assertNotEqual(r.get("reason_code"), "client-typo-confirmation",
                            r)


if __name__ == "__main__":
    unittest.main(verbosity=2)
