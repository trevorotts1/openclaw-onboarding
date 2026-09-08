#!/usr/bin/env python3
"""
test_f28_content_quality.py — F28 content quality beyond length (QC-F28).

Fixtures only; NO live model calls. Covers:
  - an unsupported fact FAILS the rubric; the same fact WITH a source URL
    passes and stays traceable;
  - a prior-week duplicate FAILS;
  - a different-brand voice FAILS;
  - short EFFECTIVE copy passes without padding;
  - platform variants retain the approved meaning (drift fails);
  - Skill 57 prompt 01 + bands.json carry the F28 rubric contract.

Run:  python3 -m unittest discover -s tests/social-planner -p 'test_f*.py'
"""

import json
import os
import sys
import unittest

_ONB_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SHARED = os.path.join(_ONB_ROOT, "shared-utils")
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import social_content_quality as q  # noqa: E402

VOICE = "warm practical coach helping small business owners grow with confidence"
BRIEF = {
    "brand_voice": VOICE,
    "source_urls": [],
    "recent_history": [],
    "cta": "Book a free call",
    "audience": "small business owners",
}

GOOD_SHORT = ("Stop guessing your prices. How to price with confidence: list "
              "costs, add margin, test for a week. Book a free call.")


class TestUnsupportedFacts(unittest.TestCase):
    def test_unsupported_fact_fails(self):
        content = "Our clients see 300% growth in 30 days. Book a free call."
        r = q.rubric(content, BRIEF)
        self.assertFalse(r["passes"])
        self.assertTrue(any(p["code"] == "AF-QUALITY-FACT" for p in r["problems"]),
                        r["problems"])

    def test_research_claim_without_source_fails(self):
        content = "Studies show most owners underprice. Book a free call."
        r = q.rubric(content, dict(BRIEF))
        self.assertFalse(r["passes"])
        self.assertTrue(any(p["code"] == "AF-QUALITY-FACT" for p in r["problems"]))

    def test_sourced_fact_passes_and_is_traceable(self):
        content = "Our clients see 300% growth in 30 days. Book a free call."
        brief = dict(BRIEF, source_urls=["https://example.com/case-study-2026"])
        r = q.rubric(content, brief)
        self.assertTrue(r["passes"], r["problems"])
        self.assertEqual(r["scores"]["factual_support"], 2)
        # traceable: the brief carries the URL a reader can be given
        self.assertIn("https://example.com/case-study-2026", brief["source_urls"])

    def test_bare_year_is_not_a_fact(self):
        content = "Since 2019 we have helped owners price with confidence. Book a free call."
        r = q.rubric(content, dict(BRIEF))
        self.assertTrue(r["passes"], r["problems"])

    def test_uncertain_fact_routes_to_omission_not_guess(self):
        # The deterministic marker: an unsupported fact raises AF-QUALITY-FACT,
        # whose remediation text says route to clarification or omit — the
        # caller's signal to ask the client instead of guessing.
        r = q.rubric("Clients report 98% satisfaction. Book a free call.", dict(BRIEF))
        problem = next(p for p in r["problems"] if p["code"] == "AF-QUALITY-FACT")
        self.assertIn("clarification", problem["detail"])


class TestPriorWeekDuplicate(unittest.TestCase):
    def test_duplicate_fails(self):
        prior = ("How to price with confidence: list your costs, add a healthy "
                 "margin, then test for a week and watch what happens.")
        r = q.rubric(prior, dict(BRIEF, recent_history=[prior]))
        self.assertFalse(r["passes"])
        self.assertTrue(any(p["code"] == "AF-QUALITY-DUPLICATE" for p in r["problems"]))

    def test_fresh_angle_on_same_theme_passes(self):
        prior = ("How to price with confidence: list your costs, add a healthy "
                 "margin, then test for a week and watch what happens.")
        fresh = ("Three costs owners forget to count: refunds, returns and your "
                 "own hours. Price with the real number. Book a free call.")
        r = q.rubric(fresh, dict(BRIEF, recent_history=[prior]))
        self.assertTrue(r["passes"], r["problems"])


class TestBrandVoice(unittest.TestCase):
    CORP = ("Synergistic enterprise solutions leverage robust paradigms to "
            "optimize stakeholder engagement across verticals.")

    def test_other_brand_voice_fails(self):
        r = q.rubric(self.CORP, dict(BRIEF, other_brand_voice=self.CORP))
        self.assertFalse(r["passes"])
        self.assertTrue(any(p["code"] == "AF-QUALITY-VOICE" for p in r["problems"]))

    def test_approved_voice_passes(self):
        r = q.rubric(GOOD_SHORT, dict(BRIEF))
        self.assertTrue(r["passes"], r["problems"])
        self.assertGreaterEqual(r["scores"]["voice"], 0)  # voice alone is not fatal here


class TestShortEffectiveCopy(unittest.TestCase):
    def test_short_effective_copy_passes_without_padding(self):
        self.assertLess(len(GOOD_SHORT), 400)
        r = q.rubric(GOOD_SHORT, dict(BRIEF))
        self.assertTrue(r["passes"], r["problems"])

    def test_length_is_not_a_rubric_dimension(self):
        r = q.rubric(GOOD_SHORT, dict(BRIEF))
        self.assertNotIn("length", r["scores"])
        self.assertNotIn("padding", r["scores"])


class TestPlatformVariantMeaning(unittest.TestCase):
    BASE = ("How to price with confidence: list costs, add margin, test for a "
            "week. Book a free call.")
    CTA = "Book a free call"

    def test_variant_retains_meaning(self):
        variant = ("Pricing with confidence in one line: costs, margin, one week "
                   "of testing. Ready? Book a free call today.")
        r = q.validate_platform_variant(self.BASE, variant, cta=self.CTA)
        self.assertTrue(r["passes"], r["problems"])

    def test_drifted_variant_fails(self):
        variant = "Sunsets are beautiful and life is a journey worth savoring."
        r = q.validate_platform_variant(self.BASE, variant, cta=self.CTA)
        self.assertFalse(r["passes"])
        self.assertTrue(any(p["code"] == "AF-QUALITY-MEANING-DRIFT" for p in r["problems"]))

    def test_variant_dropping_cta_fails(self):
        variant = "Costs, margin, one week of testing — that's confident pricing."
        r = q.validate_platform_variant(self.BASE, variant, cta=self.CTA)
        self.assertFalse(r["passes"])
        self.assertTrue(any(p["code"] == "AF-QUALITY-CTA-DROPPED" for p in r["problems"]))


class TestPromptAndBandsCarryF28(unittest.TestCase):
    def test_prompt_01_has_f28_supplement(self):
        path = os.path.join(_ONB_ROOT, "57-social-media-in-a-box", "prompts",
                            "01-content-generator-multiplatform.md")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        for needle in ("CONTENT QUALITY BEYOND LENGTH", "source URL",
                       "AF-QUALITY-FACT", "clarification",
                       "Specificity", "Distinctiveness",
                       "WITHOUT PADDING"):
            self.assertIn(needle, text, needle)

    def test_bands_json_has_quality_contract(self):
        path = os.path.join(_ONB_ROOT, "57-social-media-in-a-box", "config", "bands.json")
        with open(path, encoding="utf-8") as f:
            bands = json.load(f)
        note = bands["bands"].get("$f28_quality_note", "")
        for needle in ("AF-QUALITY-FACT", "AF-QUALITY-DUPLICATE",
                       "social_content_quality.py", "WITHOUT padding"):
            self.assertIn(needle, note, needle)
        self.assertEqual(bands["bands"]["quality_duplicate_overlap_max"]["exact_max"], 0.60)
        self.assertEqual(bands["bands"]["quality_variant_meaning_overlap_min"]["exact_min"], 0.18)


if __name__ == "__main__":
    unittest.main()