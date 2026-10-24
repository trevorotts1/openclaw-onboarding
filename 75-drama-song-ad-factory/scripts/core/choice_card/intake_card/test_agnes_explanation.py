"""Focused offline checks for the authorized Agnes choice explanation."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
CORE = HERE.parent.parent
sys.path.insert(0, str(CORE))
from choice_card.intake_card import agnes_explanation as explanation
from choice_card.intake_card import intake_card as card


class AgnesExplanation(unittest.TestCase):
    def test_both_choices_explain_providers_and_charges(self):
        text = "\n".join(explanation.lines(env={}))
        self.assertIn("Option 1 - Agnes:", text)
        self.assertIn("paid Agnes plan", text)
        self.assertIn("subscription API access", text)
        self.assertIn("720p", text)
        self.assertIn("10 seconds each", text)
        self.assertIn("up to 5 minutes", text)
        self.assertIn("500 video seconds and 4,000 images", text)
        self.assertIn("remaining plan quota", text)
        self.assertIn("Option 2 - KIE.ai:", text)
        self.assertIn("including premium options", text)
        self.assertIn("choose the model next", text)
        self.assertIn("estimated cost", text)
        self.assertIn("approve it before generation", text)
        self.assertIn("KIE.ai also supplies the pictures", text)
        self.assertIn("Suno song and Kling talking close-ups", text)
        self.assertIn("billed separately", text)
        self.assertIn("approved spending limit", text)
        self.assertIn("does not make the whole production free", text)
        self.assertIn("Neither option is selected for you", text)

    def test_effective_local_limits_are_displayed_without_a_balance_claim(self):
        text = "\n".join(explanation.lines(env={
            "AGNES_DAILY_VIDEO_SECONDS": "350",
            "AGNES_DAILY_IMAGES": "1200",
            "AGNES_API_KEY": "secret-value-never-to-print",
        }))
        self.assertIn("350 video seconds and 1,200 images", text)
        self.assertIn("daily planning limits", text)
        self.assertNotIn("secret-value", text)
        self.assertNotIn("500 video", text)

    def test_explanation_preserves_question_and_option_identity(self):
        q = card._agnes_q("unknown")
        before = copy.deepcopy(q)
        explanation.lines(env={})
        self.assertEqual(q, before)
        self.assertEqual([o[0] for o in q["options"]], [
            "Yes - use my Agnes plan.",
            "No - use the studio's standard models.",
        ])
        self.assertEqual(card._parse("1", q)["n"], 1)
        self.assertEqual(card._parse("2", q)["n"], 2)
        self.assertIsNone(card._parse("", q))
        self.assertIsNone(card._parse("3", q))

    def test_each_explicit_choice_keeps_existing_route(self):
        q = card._agnes_q("unknown")
        for number, expected in (("1", "yes"), ("2", "no")):
            with self.subTest(number=number), tempfile.TemporaryDirectory() as run:
                answer = card._parse(number, q)
                card._record_agnes_receipt(run, [answer], [q])
                rec = json.loads((Path(run) / "control/card-receipt.json").read_text())
                self.assertEqual(rec["agnes"]["answer"], expected)
                model = card._model_question("2 minutes", agnes_yes=expected == "yes")
                self.assertEqual("if Agnes cannot" in model["ask"], expected == "yes")
                self.assertTrue(model["options"])
        with tempfile.TemporaryDirectory() as run:
            card._record_agnes_receipt(run, [], [q])
            self.assertFalse((Path(run) / "control/card-receipt.json").exists())


if __name__ == "__main__":
    unittest.main()
