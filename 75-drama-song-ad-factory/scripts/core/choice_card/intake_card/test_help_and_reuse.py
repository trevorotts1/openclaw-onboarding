#!/usr/bin/env python3
"""S75-T23 focused checks: one question, plain help, reason, answer reuse.

Run: python3 core/choice_card/intake_card/test_help_and_reuse.py
"""
import copy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
CORE = HERE.parent.parent
sys.path.insert(0, str(CORE))
from choice_card.intake_card import answer_reuse as reuse  # noqa: E402
from choice_card.intake_card import intake_card as card  # noqa: E402
from choice_card.intake_card import intake_session as session  # noqa: E402
from choice_card.intake_card import style_help  # noqa: E402

FIXTURE = HERE.parents[3] / "tests" / "fixtures" / "intake_resume.json"

#: The eighteen approved ids from the specification, used ONLY as a catalog the
#: help code is handed in this test. It is not a second production catalog.
EIGHTEEN = [
    "soul-ballad", "rnb-flow", "soul-rise", "acoustic-pop", "folk-storytelling",
    "country-pop", "melodic-rap", "trap-rap", "pop-rap", "pop-rock", "reggaeton",
    "cinematic-orchestral-song", "musical-theater", "contemporary-gospel",
    "urban-gospel", "alternative-rnb", "afro-soul", "country-rap",
]
FAKE_CATALOG = {
    sid: {"label": sid.replace("-", " ").title(),
          "client_description": "a distinct fictional direction for %s." % sid,
          "client_references": ["Reference Artist"] if sid == "country-rap" else [],
          "suno_style_prompt": "SECRET PROVIDER TEXT for %s" % sid}
    for sid in EIGHTEEN
}


def _typed(qid):
    return {"id": qid, "label": qid.upper(), "ask": "Type your " + qid + ".",
            "why": "Your own words are preserved.", "free_text": True,
            "options": [("Type it in", "Use your own words.")]}


def _menu(qid, labels):
    return {"id": qid, "label": qid.upper(), "ask": "Choose your " + qid + ".",
            "why": "This is the existing menu.", "options": [(x, None) for x in labels],
            "recommended": 0}


class StyleHelpTest(unittest.TestCase):
    def test_every_offered_style_has_one_plain_line(self):
        rows = style_help.help_rows()
        self.assertTrue(rows)
        self.assertEqual(len(rows), len(style_help.style_ids()))
        lines = [row["help_line"] for row in rows]
        self.assertEqual(len(set(lines)), len(lines))          # each says something
        for row in rows:
            self.assertTrue(row["label"] and row["description"], row)
            self.assertNotIn("SECRET", row["help_line"])
            for provider_word in ("bpm", "suno", "prompt"):
                self.assertNotIn(provider_word, row["help_line"].casefold())

    def test_eighteen_style_catalog_is_fully_explained(self):
        rows = style_help.help_rows(FAKE_CATALOG)
        self.assertEqual([r["style_id"] for r in rows], EIGHTEEN)
        for row in rows:
            self.assertIn(row["label"], row["help_line"])
            self.assertNotIn("SECRET PROVIDER", row["help_line"])
        text = style_help.help_text(catalog=FAKE_CATALOG)
        for row in rows:
            self.assertIn(row["help_line"], text)
        self.assertIn("not a selection", text)

    def test_help_echoes_a_choice_instead_of_replacing_it(self):
        chosen = style_help.style_ids()[0]
        text = style_help.help_text(selected=chosen)
        self.assertIn("You chose", text)
        self.assertIn(style_help.describe(chosen)["label"], text)

    def test_recommendation_has_a_reason_and_is_only_a_suggestion(self):
        got = style_help.recommend(story="an intimate memory of one kitchen",
                                   catalog=FAKE_CATALOG)
        self.assertEqual(got["style_id"], "folk-storytelling")
        self.assertTrue(got["is_suggestion"])
        self.assertTrue(got["reason"])
        self.assertIn("suggestion only", got["note"])
        # The real three-style catalog has no folk option, so nothing is invented.
        self.assertEqual(style_help.recommend(story="an intimate memory"), None)
        self.assertEqual(style_help.recommend(story=""), None)
        self.assertEqual(style_help.recommend(story="something unmatched"), None)
        risen = style_help.recommend(story="the story lifts at the turn")
        self.assertEqual(risen["style_id"], "soul-rise")

    def test_selected_style_is_restated_never_overwritten(self):
        got = style_help.recommend(story="an intimate memory", selected="soul-ballad")
        self.assertEqual(got["style_id"], "soul-ballad")
        self.assertFalse(got["is_suggestion"])
        self.assertIn("already chose", got["reason"])

    def test_progress_uses_real_counts_only(self):
        self.assertEqual(style_help.progress(2, 5, "MUSIC STYLE"),
                         "2 of 5 answered. Next: MUSIC STYLE.")
        self.assertEqual(style_help.progress(None, 5), "")


class SessionGuidanceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="s75-help-reuse-")
        self.run = Path(self.temp.name) / "run"
        self.run.mkdir()
        self.qs = [_typed("offer"), _typed("audience"),
                   _menu("music", ["Soul Ballad", "R&B Flow", "Soul Rise"])]

    def tearDown(self):
        self.temp.cleanup()

    def call(self, replies=(), **kw):
        return session.process(list(replies), self.qs, run_dir=str(self.run),
                               purpose_flow=False, **kw)

    def state(self):
        return json.loads((self.run / "control" / "intake-session.json").read_text())

    def advance(self):
        self.call()
        self.call(["The Quiet Kitchen"])
        return self.call(["adults 40 to 60 caring for a parent"])

    def test_help_is_guidance_and_does_not_answer(self):
        st = self.advance()
        shown = self.call(["help me choose"])
        self.assertEqual(shown["reason_code"], "CARD_HELP_SHOWN")
        self.assertIn("Music styles, one line each:", shown["message"])
        for row in style_help.help_rows():
            self.assertIn(row["help_line"], shown["message"])
        self.assertEqual(shown["answered_count"], st["answered_count"])
        self.assertEqual(shown["question_digest"], st["question_digest"])
        state = self.state()
        self.assertNotIn("music", state["answer_records"])
        self.assertEqual(state["events"][-1]["guidance"], "style_help")
        self.assertFalse(state["events"][-1]["accepted"])

    def test_reuse_offer_lists_answers_and_changes_nothing(self):
        self.advance()
        shown = self.call(["reuse my answers"])
        self.assertEqual(shown["reason_code"], "REUSE_OFFER_SHOWN")
        self.assertIn("Offer: The Quiet Kitchen", shown["message"])
        self.assertIn("none is asked again", shown["message"])
        self.assertIn("not an approval", shown["message"])
        self.assertEqual(shown["answered_count"], 2)
        self.assertEqual(sorted(self.state()["answer_records"]),
                         ["audience", "offer"])

    def test_typed_help_stays_an_answer(self):
        qs = [_typed("offer"), _menu("music", ["Soul Ballad"])]
        session.process([], qs, run_dir=str(self.run), purpose_flow=False)
        saved = session.process(["help"], qs, run_dir=str(self.run),
                                purpose_flow=False)
        self.assertEqual(saved["reason_code"], "INTAKE_ANSWER_SAVED")
        self.assertEqual(saved["answers"][0]["value"], "help")

    def test_resume_does_not_re_ask_answered_choices(self):
        fx = json.loads(FIXTURE.read_text())
        self.call()                                    # present the first question
        for reply in fx["replies_before_resume"]:
            self.call([reply])
        before = self.state()
        resumed = self.call()
        self.assertEqual(resumed["reason_code"], "INTAKE_WAITING")
        self.assertEqual(resumed["question_id"], fx["next_question_id"])
        self.assertEqual(resumed["answered_count"], len(fx["answered_before_resume"]))
        self.assertEqual(resumed["answers"], [r["parsed"] for r in
                         (before["answer_records"][q] for q in fx["answered_before_resume"])])
        self.assertEqual(set(self.state()["answer_records"]),
                         set(fx["answered_before_resume"]))
        for reply in fx["replies_after_resume"]:
            shown = self.call([reply])
        self.assertEqual(shown["reason_code"], "CARD_HELP_SHOWN")
        self.assertEqual(shown["answered_count"], 2)
        answered = self.call(["2"])
        self.assertEqual(answered["answers"][-1]["text"], "R&B Flow")

    def test_changed_definition_is_stale_and_never_overwrites(self):
        self.advance()
        state = self.state()
        changed = copy.deepcopy(self.qs)
        changed[0]["ask"] = "A changed offer question."
        rows = {r["question_id"]: r for r in reuse.reusable_rows(state, changed)}
        self.assertFalse(rows["offer"]["matches"])
        self.assertTrue(rows["audience"]["matches"])
        verdict = reuse.apply_reuse(state, ["offer", "audience"], changed)
        self.assertEqual(verdict["applied"], ["audience"])
        self.assertEqual(verdict["refused"][0]["question_id"], "offer")
        self.assertFalse(verdict["wrote"])
        self.assertEqual(state, self.state())          # pure: nothing written


if __name__ == "__main__":
    unittest.main(verbosity=2)
