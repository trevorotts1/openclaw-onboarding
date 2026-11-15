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


#: S75-006: CHARACTER is the fourth screen of the card a new run asks (the OFFER
#: reply carries the web address, so OFFER LINK is never a screen of its own), and
#: the saved-character pick takes that same slot -- one "who stars" question
#: either way. Read the slot off the card so a re-ordered card cannot drift.
AT = [q["id"] for q in IC.QUESTIONS].index("character")   # 0-based slot
N = len(IC.QUESTIONS)
#: the count the chat numbers its one-at-a-time questions by: every screen that
#: is asked (the defaulted recap lines are not).
ASKED = len([q for q in IC.QUESTIONS if not q.get("defaulted")])
#: the answers that come before the saved-character pick.
BRIEF = IC.example_replies(IC.QUESTIONS)[:AT]

NEW = ("Question %d of %d - CHARACTER\n"
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
        #: U-GEN425: the counter reads the screens asked one by one (ASKED).
        self.assertEqual(IC.render_step(AT + 1, self.one),
                         NEW % (AT + 1, ASKED, "1 character") + "2. Use Maya Lee - Warm, 40s, silver braids\n" + TAIL)

    def test_text_two_saved_plural(self):
        self.assertEqual(IC.render_step(AT + 1, self.qs),
                         NEW % (AT + 1, ASKED, "2 characters") + "2. Use Dre - Sharp suit, calm voice\n"
                         "3. Use Maya Lee - Warm, 40s, silver braids\n" + TAIL)

    def test_card_uses_same_text(self):
        self.assertIn(IC.render_step(AT + 1, self.qs), IC.render_card(self.qs))

    def test_replies_map(self):
        for reply, n in (("1", 1), ("recommended", 1), ("2", 2), ("3", 3)):
            self.assertEqual(IC._parse(reply, self.qs[AT])["n"], n, reply)
        self.assertEqual(IC._parse("2", self.qs[AT])["text"], "Use Dre")
        self.assertIsNone(IC._parse("4", self.qs[AT]))

    def test_no_saved_line_not_a_question(self):
        empty = IC._with_saved_character(os.path.join(self.t, "empty"))
        self.assertEqual(len(empty), len(IC.QUESTIONS))
        first = IC.conversation([], empty)["message"]
        self.assertTrue(first.startswith(NO_SAVED + "\n\nQuestion 1 of %d - OFFER" % ASKED))
        #: U-GEN425: the card counts the screens it ASKS, exactly like the chat.
        self.assertTrue(IC.render_card(empty).startswith(NO_SAVED + "\n\nQuestion 1 of %d" % ASKED))
        self.assertNotIn("CHARACTER", first)
        self.assertNotIn(NO_SAVED, IC.conversation(["1"], empty)["message"])   # shown once
        self.assertEqual(IC._with_saved_character(""), IC.QUESTIONS)           # no folder: nothing
        self.assertNotIn(NO_SAVED, IC.render_card(self.qs))                    # saved: no such line

    def test_recap_plain_english_and_change_by_number(self):
        #: every screen the card asks after CHARACTER (S75-006): AI MODELS,
        #: LENGTH, MUSIC STYLE, VIDEO STYLE, CHECKPOINTS, BUDGET.
        rest = ["1", "1", "1", "1", "1", "$25"]
        line = AT + 1                                                   # the saved-character line number
        st = IC.conversation(BRIEF + ["3"] + rest, self.qs)
        self.assertIn("%d. Character: Maya Lee (saved)" % line, st["message"])
        st = IC.conversation(BRIEF + ["1"] + rest, self.qs)
        self.assertIn("%d. Character: new" % line, st["message"])
        st = IC.conversation(BRIEF + ["1"] + rest + [str(line), "2"], self.qs)
        self.assertIn("%d. Character: Dre (saved)" % line, st["message"])
        st = IC.conversation(BRIEF + ["1"] + rest + [str(line)], self.qs)
        #: the re-asked screen is the CHARACTER question itself. The chat counts
        #: only the screens it asks one at a time (S75-006), the card counts every
        #: line, so only that count differs -- compare the question body exactly.
        self.assertEqual(st["message"].split("\n", 1)[1],
                         IC.render_step(line, self.qs).split("\n", 1)[1])
        self.assertRegex(st["message"].splitlines()[0],
                         r"^Question %d of \d+ - CHARACTER$" % line)


if __name__ == "__main__":
    unittest.main()
