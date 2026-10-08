#!/usr/bin/env python3
"""I1 tests: captions are spell-checked; the client's website is asked and kept.

Trigger: "wakeuphappysis.com" came out misspelled in the captions. Zero paid
calls; stdlib only.

    python3 core/test_caption_spelling_i1.py
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
for sub in ("", "intake_preflight", "delivery_variants"):
    p = os.path.join(HERE, sub)
    if p not in sys.path:
        sys.path.insert(0, p)

import protected_names as P  # noqa: E402
import intake as I  # noqa: E402
import checks as C  # noqa: E402

SITE = "wakeuphappysis.com"
SHEET = ["[Chorus]", "Wake up, happy sis", "Go to wakeuphappysis.com", "She is running home"]
BRIEF = {"website": SITE, "characters": ["Laya"]}
PROT = P.protected_list(BRIEF)


class Spelling(unittest.TestCase):
    def test_website_is_protected_word(self):
        self.assertIn(SITE, PROT)

    def test_clean_captions_pass(self):
        self.assertEqual(P.check_spelling(SHEET, PROT), [])

    def test_misspelled_website_in_captions_fails_with_word_shown(self):
        bad = [l.replace(SITE, "wakeuphapysis.com") for l in SHEET]
        errs = P.check_spelling(bad, PROT)
        self.assertEqual(len(errs), 1)
        self.assertIn("wakeuphapysis", errs[0])
        status, detail = C.check_captions(bad, SHEET, protected=PROT)
        self.assertEqual(status, C.FAIL)
        self.assertIn("wakeuphapysis", detail)

    def test_misspelled_ordinary_word_fails_even_if_sheet_agrees(self):
        sheet = ["She is hapy at home"]
        self.assertIn("hapy", P.check_spelling(sheet, PROT)[0])

    def test_protected_name_and_sung_filler_pass(self):
        self.assertEqual(P.check_spelling(["Laya sings ooh, don't stop, yeah 2024"], PROT), [])

    def test_website_verbatim_everywhere(self):
        ok = P.check_website(SITE, lyrics=SHEET, captions=SHEET, end_card=["Visit " + SITE])
        self.assertEqual(ok, [])
        bad = P.check_website(SITE, lyrics=SHEET, end_card="wakeuphappysi.com")
        self.assertEqual(len(bad), 1)
        self.assertIn("end_card", bad[0])


class IntakeAsksWebsite(unittest.TestCase):
    def test_asks_when_ad_sends_people_to_a_website(self):
        brief = {"offer": "Coaching", "audience": "moms", "action": "Visit her website",
                 "budget_minor": 2500, "budget_currency": "USD", "placement": "9:16 vertical"}
        r = I.evaluate(brief)
        self.assertEqual([q["id"] for q in r["questions"]], ["website"])
        self.assertIn("exact website address", r["question_message"])

    def test_no_question_once_answered_and_stored(self):
        brief = {"offer": "Coaching", "audience": "moms", "action": "Visit her website",
                 "budget_minor": 2500, "budget_currency": "USD", "placement": "9:16 vertical", "website": SITE}
        r = I.evaluate(brief)
        self.assertEqual(r["questions"], [])
        self.assertEqual(r["summary"]["website"], SITE)

    def test_no_website_question_for_non_web_ad(self):
        brief = {"offer": "Coaching", "audience": "moms", "action": "Call us now",
                 "budget_minor": 2500, "budget_currency": "USD", "placement": "9:16 vertical"}
        self.assertNotIn("website", [q["id"] for q in I.evaluate(brief)["questions"]])


if __name__ == "__main__":
    unittest.main()
