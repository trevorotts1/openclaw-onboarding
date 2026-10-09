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


NEW = ("Question 2 of %d - CHARACTER\n"
       "Do you want to create a new character for this ad, or use one you've used before?\n"
       "You have %s saved with us.\n"
       "1. Create a new character (recommended)\n")
TAIL = "Reply with a number, or 'recommended'."
NO_SAVED = ("You don't have any saved characters yet, so I'll create a new one "
            "for this ad and save it for next time.")


class SavedCharacterQuestion(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        self.client = os.path.join(self.t, "client")
        self.img = os.path.join(self.t, "a.png")
        with open(self.img, "wb") as f:
            f.write(b"\x89PNG-fake")
        CL.save_character(self.client, "Maya Lee", "Warm, 40s, silver braids", [self.img])
        self.one = IC._with_saved_character(self.client)
        CL.save_character(self.client, "Dre", "Sharp suit, calm voice", [self.img])
        self.qs = IC._with_saved_character(self.client)

    def test_text_one_saved_singular(self):
        self.assertEqual(IC.render_step(2, self.one),
                         NEW % (10, "1 character") + "2. Use Maya Lee - Warm, 40s, silver braids\n" + TAIL)

    def test_text_two_saved_plural(self):
        self.assertEqual(IC.render_step(2, self.qs),
                         NEW % (10, "2 characters") + "2. Use Dre - Sharp suit, calm voice\n"
                         "3. Use Maya Lee - Warm, 40s, silver braids\n" + TAIL)

    def test_card_uses_same_text(self):
        self.assertIn(IC.render_step(2, self.qs), IC.render_card(self.qs))

    def test_replies_map(self):
        for reply, n in (("1", 1), ("recommended", 1), ("2", 2), ("3", 3)):
            self.assertEqual(IC._parse(reply, self.qs[1])["n"], n, reply)
        self.assertEqual(IC._parse("2", self.qs[1])["text"], "Use Dre")
        self.assertIsNone(IC._parse("4", self.qs[1]))

    def test_no_saved_line_not_a_question(self):
        empty = IC._with_saved_character(os.path.join(self.t, "empty"))
        self.assertEqual(len(empty), len(IC.QUESTIONS))
        first = IC.conversation([], empty)["message"]
        self.assertTrue(first.startswith(NO_SAVED + "\n\nQuestion 1 of 9 - AI MODELS"))
        self.assertTrue(IC.render_card(empty).startswith(NO_SAVED + "\n\nQuestion 1 of 9"))
        self.assertNotIn("CHARACTER", first)
        self.assertNotIn(NO_SAVED, IC.conversation(["1"], empty)["message"])   # shown once
        self.assertEqual(IC._with_saved_character(""), IC.QUESTIONS)           # no folder: nothing
        self.assertNotIn(NO_SAVED, IC.render_card(self.qs))                    # saved: no such line

    def test_recap_plain_english_and_change_by_number(self):
        rest = ["recommended"] * 4 + ["$25"] + ["recommended"] * 3      # length..model, budget, three approvals
        st = IC.conversation(["1", "3"] + rest, self.qs)
        self.assertIn("2. Character: Maya Lee (saved)", st["message"])
        st = IC.conversation(["1", "1"] + rest, self.qs)
        self.assertIn("2. Character: new", st["message"])
        st = IC.conversation(["1", "1"] + rest + ["2", "2"], self.qs)
        self.assertIn("2. Character: Dre (saved)", st["message"])
        st = IC.conversation(["1", "1"] + rest + ["2"], self.qs)
        self.assertEqual(st["message"], IC.render_step(2, self.qs))


if __name__ == "__main__":
    unittest.main()
