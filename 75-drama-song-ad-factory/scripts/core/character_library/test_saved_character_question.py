#!/usr/bin/env python3
"""FU-SAVED-CHARACTER-QUESTION: the saved-character question is a full,
numbered question. Run: python3 test_saved_character_question.py"""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for p in (CORE, os.path.join(CORE, "choice_card", "intake_card")):
    if p not in sys.path:
        sys.path.insert(0, p)
from character_library import character_library as CL  # noqa: E402
from choice_card.intake_card import intake_card as IC  # noqa: E402


class SavedCharacterQuestion(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.client = os.path.join(self.t, "client")
        img = os.path.join(self.t, "a.png")
        with open(img, "wb") as f:
            f.write(b"\x89PNG-fake")
        CL.save_character(self.client, "Maya Lee", "Warm, 40s, silver braids", [img])
        CL.save_character(self.client, "Dre", "Sharp suit, calm voice", [img])
        self.qs = IC._with_saved_character(self.client)

    def test_rendered_text(self):
        text = IC.render_step(1, self.qs)
        self.assertIn("Question 1 of 7 - SAVED CHARACTER", text)
        self.assertIn("Do you want to use one of them in this ad, or make a "
                      "brand-new character?\n", text)
        self.assertIn("1. Make a new character", text)
        self.assertIn("1. Make a new character - I create a fresh character "
                      "for this ad. (RECOMMENDED)", text)
        self.assertIn("2. Use Dre - Sharp suit, calm voice", text)
        self.assertIn("3. Use Maya Lee - Warm, 40s, silver braids", text)
        self.assertTrue(self.qs[0]["ask"].endswith("?"))
        self.assertIn('Reply with a number, or say "recommended".', text)

    def test_replies_map(self):
        for reply, n in (("1", 1), ("recommended", 1), ("2", 2), ("3", 3)):
            a = IC._parse(reply, self.qs[0])
            self.assertEqual(a["n"], n, reply)
        self.assertEqual(IC._parse("2", self.qs[0])["text"], "Use Dre")
        self.assertIsNone(IC._parse("4", self.qs[0]))

    def test_absent_without_saved_characters(self):
        empty = os.path.join(self.t, "empty")
        self.assertEqual(IC._with_saved_character(empty), IC.QUESTIONS)
        self.assertNotIn("SAVED CHARACTER", IC.render_card(IC._with_saved_character(empty)))
        self.assertEqual(len(self.qs), len(IC.QUESTIONS) + 1)

    def test_recap_plain_english_and_change_by_number(self):
        st = IC.conversation(["3"] + ["recommended"] * 6, self.qs)
        self.assertIn("1. Character: Maya Lee (saved)", st["message"])
        st = IC.conversation(["1"] + ["recommended"] * 6, self.qs)
        self.assertIn("1. Character: new", st["message"])
        st = IC.conversation(["1"] + ["recommended"] * 6 + ["1", "2"], self.qs)
        self.assertIn("1. Character: Dre (saved)", st["message"])
        st = IC.conversation(["1"] + ["recommended"] * 6 + ["1"], self.qs)
        self.assertIn("Question 1 of 7 - SAVED CHARACTER", st["message"])


if __name__ == "__main__":
    unittest.main()
