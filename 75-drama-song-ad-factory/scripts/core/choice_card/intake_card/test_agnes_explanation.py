"""Focused offline checks for the authorized Agnes choice explanation.

S75-074 step 7: the explanation is two plain sentences, one per option. It names
no vendor, prints no balance and reads no credential or quota setting.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
CORE = HERE.parent.parent
sys.path.insert(0, str(CORE))
from choice_card.intake_card import agnes_explanation as explanation
from choice_card.intake_card import intake_card as card

#: The exact two paragraphs the page shows, in order.
EXPECTED = (
    "Option 1 uses the plan you already pay Agnes for to make the pictures and "
    "clips. The song and the talking close-ups are still charged to your studio "
    "balance, and that cost is in your estimate.",
    "Option 2 uses the studio's own models for everything. You pick the quality "
    "next and see the cost before anything is made.",
)


class AgnesExplanation(unittest.TestCase):
    def test_both_choices_explain_plainly_and_in_order(self):
        self.assertEqual(explanation.lines(env={}), list(EXPECTED))
        text = "\n".join(explanation.lines())
        self.assertIn("Option 1 uses the plan you already pay Agnes for", text)
        self.assertIn("still charged to your studio balance", text)
        self.assertIn("Option 2 uses the studio's own models for everything", text)
        self.assertIn("see the cost before anything is made", text)

    def test_no_vendor_name_or_provider_jargon_reaches_the_client(self):
        text = "\n".join(explanation.lines(env={}))
        for word in ("KIE", "Suno", "Kling", "OpenRouter", "Ollama", "sqlite"):
            self.assertNotIn(word, text, word)

    def test_no_balance_claim_and_no_setting_or_credential_is_read(self):
        # the old text printed daily quota figures; the page forbids them
        text = "\n".join(explanation.lines(env={
            "AGNES_DAILY_VIDEO_SECONDS": "350",
            "AGNES_DAILY_IMAGES": "1200",
            "AGNES_API_KEY": "secret-value-never-to-print",
        }))
        self.assertEqual(text, "\n".join(EXPECTED))
        self.assertNotIn("secret-value", text)
        self.assertNotIn("daily planning limits", text)

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
