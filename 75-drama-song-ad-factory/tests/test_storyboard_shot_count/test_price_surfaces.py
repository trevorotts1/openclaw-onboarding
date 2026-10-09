#!/usr/bin/env python3
"""PKG-06-U3 — DEL-15: every price surface agrees with the calculator.

Three surfaces state the storyboard picture count (choice-card-spec 3.12):
references/price-menu.md (the rates and the count table), the choice card
itself (rendered by card_render), and references/CLIENT-GUIDE.md (the
client-facing wording). Each is parsed here and every number is checked
against the live calculator — shot_count() and storyboard_cap() — so a
document that drifts from the code fails this test instead of shipping.

The client guide carries no dollar amounts at all; the per-picture rate
lives only in price-menu.md, and no rate is printed next to the count on
the card (choice-card-spec 3.12, section 4).

Run: python3 tests/test_storyboard_shot_count/test_price_surfaces.py
(also collected by pytest). stdlib only, no network.
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
import unittest

HERE = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.realpath(os.path.join(HERE, "..", ".."))
CORE = os.path.join(SKILL, "scripts", "core")
PKG = os.path.join(CORE, "catalog_calculator")
if CORE not in sys.path:
    sys.path.insert(0, CORE)
# card_render's script-import fallback resolves `extensions` off this dir.
if PKG not in sys.path:
    sys.path.insert(0, PKG)
CALC_PATH = os.path.join(PKG, "catalog_calculator.py")

_spec = importlib.util.spec_from_file_location("pkg06u3_calc_surfaces", CALC_PATH)
cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cc)

_spec2 = importlib.util.spec_from_file_location("pkg06u3_card_render",
                                                os.path.join(PKG, "card_render.py"))
cr = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(cr)


def read(path):
    with open(os.path.join(SKILL, "references", path), encoding="utf-8") as f:
        return f.read()


#: Label as the documents write it -> seconds of runtime.
DOC_ROWS = (
    ("60 seconds", 60),
    ("2 minutes", 120),
    ("3 minutes", 180),
    ("5 minutes", 300),
    ("10 minutes", 600),
)


class PriceMenuAgreesWithCalculator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read("price-menu.md")

    def test_every_table_row_matches_the_calculator(self):
        for label, seconds in DOC_ROWS:
            expected = cc.shot_count(seconds)
            counts = re.findall(r"^\|\s*%s\s*\|\s*(\d+)" % re.escape(label),
                                self.text, re.M)
            self.assertTrue(counts, "price-menu.md has no row for %r" % label)
            for seen in counts:
                self.assertEqual(int(seen), expected,
                                 (label, seen, expected))

    def test_money_columns_are_the_count_times_two_cents(self):
        for label, seconds in DOC_ROWS:
            expected = cc.shot_count(seconds)
            one = round(expected * 0.02, 2)
            both = round(expected * 0.04, 2)   # both shapes double it
            match = re.search(
                r"^\|\s*%s\s*\|\s*(\d+)[^|\n]*\|\s*\$([0-9.]+)\s*\|"
                r"\s*\$([0-9.]+)\s*\|" % re.escape(label),
                self.text, re.M)
            self.assertTrue(match, "no priced row for %r" % label)
            self.assertEqual(int(match.group(1)), expected, label)
            self.assertAlmostEqual(float(match.group(2)), one, places=2,
                                   msg=label)
            self.assertAlmostEqual(float(match.group(3)), both, places=2,
                                   msg=label)

    def test_the_rate_itself_stated_once(self):
        self.assertIn("$0.02 each", self.text)
        self.assertIn("two cents", self.text)

    def test_the_stated_cap_is_the_configured_cap(self):
        cap = cc.storyboard_cap()
        match = re.search(r"capped at \*\*(\d+) pictures\*\*", self.text)
        self.assertTrue(match, "price-menu.md must state the cap in bold")
        self.assertEqual(int(match.group(1)), cap)
        # and the 10-minute row is labelled as sitting at that cap
        self.assertIn("| 10 minutes | %d (at the cap) |" % cap, self.text)

    def test_the_menu_cites_the_calculator_rule(self):
        self.assertIn("core/catalog_calculator.shot_count", self.text)

    def test_the_menu_keeps_the_two_counts_apart(self):
        # prose wraps across lines; compare on flattened whitespace
        flat = " ".join(self.text.split())
        self.assertIn("separate from - and larger than - the video shot count",
                      flat)
        self.assertIn("the two are never conflated", flat)


class ChoiceCardSpecAgreesWithCalculator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        text = read("choice-card-spec.md")
        start = text.find("### 3.12")
        end = text.find("## 4.", start)
        if start < 0 or end <= start:
            raise AssertionError("choice-card-spec.md section 3.12 is missing")
        cls.section = text[start:end]
        cls.full = text

    def test_normative_table_matches_the_calculator(self):
        for label, seconds in DOC_ROWS:
            expected = cc.shot_count(seconds)
            match = re.search(r"^\|\s*%s\s*\|\s*(\d+)" % re.escape(label),
                              self.section, re.M)
            self.assertTrue(match, "section 3.12 has no row for %r" % label)
            self.assertEqual(int(match.group(1)), expected, label)

    def test_the_spec_pins_the_anchors_the_owner_pinned(self):
        self.assertIn("| 60 seconds | 8 |", self.section)
        self.assertIn("| 2 minutes | 24 |", self.section)
        self.assertEqual(cc.shot_count(60), 8)
        self.assertEqual(cc.shot_count(120), 24)

    def test_the_spec_requires_exact_agreement_with_the_calculator(self):
        self.assertIn("core/catalog_calculator.shot_count", self.section)
        self.assertIn("exactly", self.section)

    def test_the_spec_cap_is_the_configured_cap(self):
        match = re.search(r"cap is (\d+) pictures per ad", self.section)
        self.assertTrue(match, "section 3.12 must state the cap")
        self.assertEqual(int(match.group(1)), cc.storyboard_cap())

    def test_the_spec_forbids_conflating_the_counts(self):
        flat = " ".join(self.section.split())
        self.assertIn("never conflated or added together", flat)
        self.assertIn("separate count", flat)

    def test_the_spec_prints_no_rate_next_to_the_count(self):
        self.assertIn("No rate is printed next to the count", self.section)
        self.assertNotIn("$", self.section)

    def test_section_3_1_cross_references_the_rule(self):
        # The length row in 3.1 must point a reader at the 3.12 rule.
        head = self.full[:self.full.find("### 3.12")]
        self.assertIn("section 3.12", head)


class ClientGuideAgreesWithCalculator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = read("CLIENT-GUIDE.md")

    def test_step_7_counts_match_the_calculator(self):
        cap = cc.storyboard_cap()
        sixty = re.search(r"(\d+) for a 60-second ad", self.text)
        two = re.search(r"(\d+) for a 2-minute ad", self.text)
        ceiling = re.search(r"capped at (\d+) pictures", self.text)
        self.assertTrue(sixty, "STEP 7 must state the 60-second count")
        self.assertTrue(two, "STEP 7 must state the 2-minute count")
        self.assertTrue(ceiling, "STEP 7 must state the cap")
        self.assertEqual(int(sixty.group(1)), cc.shot_count(60))
        self.assertEqual(int(two.group(1)), cc.shot_count(120))
        self.assertEqual(int(ceiling.group(1)), cap)

    def test_step_15_counts_match_the_calculator(self):
        cap = cc.storyboard_cap()
        sixty = re.search(r"a 60-second ad gets (\d+) storyboard pictures",
                          self.text)
        two = re.search(r"a 2-minute ad gets (\d+)", self.text)
        ceiling = re.search(r"maximum of (\d+) pictures", self.text)
        self.assertTrue(sixty, "STEP 15 must state the 60-second count")
        self.assertTrue(two, "STEP 15 must state the 2-minute count")
        self.assertTrue(ceiling, "STEP 15 must state the maximum")
        self.assertEqual(int(sixty.group(1)), cc.shot_count(60))
        self.assertEqual(int(two.group(1)), cc.shot_count(120))
        self.assertEqual(int(ceiling.group(1)), cap)

    def test_the_cadence_wording_is_five_seconds(self):
        self.assertIn("every five seconds of runtime", self.text)

    def test_no_dollar_amounts_reach_the_client(self):
        # The client guide states counts and caps; prices are the card's.
        self.assertNotIn("$", self.text)


class CardLineAgreesWithCalculator(unittest.TestCase):
    def test_unpriced_card_line_shows_the_calculators_count(self):
        lines = []
        cr._append_storyboard_line(lines, None, {"length": "60 seconds"})
        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertIn("%d storyboard pictures" % cc.shot_count(60), line)
        self.assertIn("cap %d from configuration" % cc.storyboard_cap(), line)
        self.assertIn("separate from the video shot count", line)
        self.assertNotIn("$", line)
        self.assertNotIn("0.02", line)

    def test_priced_envelope_line_uses_the_cards_own_numbers(self):
        lines = []
        envelope = {"card": {"storyboard_pictures": 36,
                             "storyboard_picture_cap": cc.storyboard_cap(),
                             "shots_per_shape": 12}}
        cr._append_storyboard_line(lines, envelope, {"length": "3 minutes"})
        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertIn("36 storyboard pictures", line)
        self.assertIn("cap %d from configuration" % cc.storyboard_cap(), line)
        self.assertIn("separate from the 12 video shots above", line)
        self.assertNotIn("$", line)

    def test_every_offered_length_renders_the_calculators_count(self):
        labels = {"60 seconds": 60, "90 seconds": 90, "2 minutes": 120,
                  "3 minutes": 180, "5 minutes": 300,
                  "10-minute long version": 600}
        for label, seconds in labels.items():
            lines = []
            cr._append_storyboard_line(lines, None, {"length": label})
            self.assertEqual(len(lines), 1, label)
            self.assertIn("%d storyboard pictures" % cc.shot_count(seconds),
                          lines[0], label)


if __name__ == "__main__":
    unittest.main(verbosity=2)
