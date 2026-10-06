#!/usr/bin/env python3
"""Tests for validate_visual_direction.py (order A2 + font fallback 1.1.1).

Fixture brand file is used, never the real blackceo-brand.json — the real
one still has TREVOR_MUST_SUPPLY fonts, but its font_policy authorizes
derive-document, so a bible that is derived-and-documented (fonts_source
"derived", non-empty font_rationale, font_reviewer named) PASSES instead of
failing on the missing brand fonts. Every other MUST_SUPPLY key still
fails; a MUST_SUPPLY or banned font inside the bible still fails.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
SCRIPT = os.path.join(SKILL_ROOT, "scripts", "validate_visual_direction.py")

# Fixture brand: palette + fonts all supplied so palette/font checks can be
# tested on their own terms.
FIXTURE_BRAND = {
    "brand_id": "fixture",
    "palette": {"gold": "#C9A227", "navy": "#1A1A2E", "cream": "#F5F0E8"},
    "logo_only_colors": {"black": "#000000", "white": "#FFFFFF"},
    "color_tolerance": 3,
    "fonts": {"display": "Fixture Display", "body": "Fixture Body",
              "accent": "Fixture Accent"},
    "banned_fonts": ["Inter", "Arial", "Roboto"],
}


def write_run(dirpath, intake, bible, brand):
    os.makedirs(os.path.join(dirpath, "visual-mockup"), exist_ok=True)
    brand_path = os.path.join(dirpath, "brand.json")
    with open(brand_path, "w", encoding="utf-8") as f:
        json.dump(brand, f)
    intake = dict(intake, brand_file=brand_path)
    with open(os.path.join(dirpath, "intake.json"), "w", encoding="utf-8") as f:
        json.dump(intake, f)
    with open(os.path.join(dirpath, "visual-mockup", "page-visual-bible.json"),
              "w", encoding="utf-8") as f:
        json.dump(bible, f)


def run_validator(run_dir):
    return subprocess.run([sys.executable, SCRIPT, run_dir],
                          capture_output=True, text=True, timeout=30)


class TestValidateVisualDirection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="vvd-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    # Fixture copied from the real failed run: agent-selected VDL-001,
    # invented ivory/ink/gold tokens, banned font Inter.
    BAD_INTAKE = {"creative_direction": None}
    BAD_BIBLE = {
        "selection_mode": "agent-selected",
        "style_id": "VDL-001",
        "page_tokens": {"ivory": "#F6F1E8", "ink": "#111214", "gold": "#D4A646"},
        "fonts": {"display": "Inter", "body": "Inter"},
    }

    def test_bad_fixture_fails_with_all_three_reasons(self):
        run = os.path.join(self.tmp, "bad")
        write_run(run, self.BAD_INTAKE, self.BAD_BIBLE, FIXTURE_BRAND)
        r = run_validator(run)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        # Reason 1: no direction => must be SECRET_SAUCE_ONLY.
        self.assertIn("SECRET_SAUCE_ONLY", r.stdout)
        self.assertIn("selection_mode", r.stdout)
        # Reason 2: external style not named at intake.
        self.assertIn("does not name that exact style ID", r.stdout)
        self.assertIn("VDL-001", r.stdout)
        # Reason 3: off-palette tokens. #F6F1E8 sits within tolerance 3 of
        # brand cream #F5F0E8 (diff 1,1,0 per channel) so it correctly passes
        # the tolerance check; #111214 and #D4A646 are genuinely off-palette
        # and must be named.
        for token in ("#111214", "#D4A646"):
            self.assertIn(token, r.stdout)
        self.assertIn("off-palette", r.stdout)
        # Reason 4: banned font Inter.
        self.assertIn("Inter", r.stdout)
        self.assertIn("banned_fonts", r.stdout)

    def test_secret_sauce_brand_palette_brand_fonts_passes(self):
        run = os.path.join(self.tmp, "good")
        write_run(run,
                  {"creative_direction": None},
                  {"selection_mode": "SECRET_SAUCE_ONLY",
                   "page_tokens": {"navy": "#1A1A2E", "cream": "#F5F0E8",
                                   "gold": "#C9A227"},
                   "fonts": {"display": "Fixture Display",
                             "body": "Fixture Body"}},
                  FIXTURE_BRAND)
        r = run_validator(run)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_must_supply_fonts_derived_documented_passes(self):
        # font_policy derive-document: MUST_SUPPLY brand fonts no longer fail.
        # The bible must instead be derived-and-documented.
        brand = json.loads(json.dumps(FIXTURE_BRAND))
        brand["fonts"] = {"display": "TREVOR_MUST_SUPPLY",
                          "body": "TREVOR_MUST_SUPPLY",
                          "accent": "TREVOR_MUST_SUPPLY"}
        brand["font_policy"] = {"when_brand_fonts_missing": "derive-document",
                                "requires_rationale": True,
                                "requires_reviewer": True}
        run = os.path.join(self.tmp, "derived")
        write_run(run, {"creative_direction": None},
                  {"selection_mode": "SECRET_SAUCE_ONLY",
                   "fonts": {"display": "Fixture Derived Display",
                             "body": "Fixture Derived Body",
                             "accent": "Fixture Derived Accent"},
                   "fonts_source": "derived",
                   "font_rationale": "Display: heavy grotesque suits the Big "
                                     "Bold Claim. Body: workhorse legibility "
                                     "at 19/32px. Accent: serif italic for "
                                     "pull quotes.",
                   "font_reviewer": "independent-reviewer-agent"},
                  brand)
        r = run_validator(run)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn("TREVOR_MUST_SUPPLY", r.stdout)

    def test_must_supply_fonts_without_fonts_source_fails(self):
        brand = json.loads(json.dumps(FIXTURE_BRAND))
        brand["fonts"] = {"display": "TREVOR_MUST_SUPPLY",
                          "body": "TREVOR_MUST_SUPPLY",
                          "accent": "TREVOR_MUST_SUPPLY"}
        brand["font_policy"] = {"when_brand_fonts_missing": "derive-document",
                                "requires_rationale": True,
                                "requires_reviewer": True}
        run = os.path.join(self.tmp, "nosource")
        write_run(run, {"creative_direction": None},
                  {"selection_mode": "SECRET_SAUCE_ONLY"}, brand)
        r = run_validator(run)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('fonts_source = "derived"', r.stdout)

    def test_must_supply_fonts_without_rationale_fails(self):
        brand = json.loads(json.dumps(FIXTURE_BRAND))
        brand["fonts"] = {"display": "TREVOR_MUST_SUPPLY",
                          "body": "TREVOR_MUST_SUPPLY",
                          "accent": "TREVOR_MUST_SUPPLY"}
        brand["font_policy"] = {"when_brand_fonts_missing": "derive-document",
                                "requires_rationale": True,
                                "requires_reviewer": True}
        run = os.path.join(self.tmp, "norationale")
        write_run(run, {"creative_direction": None},
                  {"selection_mode": "SECRET_SAUCE_ONLY",
                   "fonts_source": "derived",
                   "font_reviewer": "reviewer-agent"}, brand)
        r = run_validator(run)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("font_rationale is empty", r.stdout)

    def test_must_supply_fonts_without_reviewer_fails(self):
        brand = json.loads(json.dumps(FIXTURE_BRAND))
        brand["fonts"] = {"display": "TREVOR_MUST_SUPPLY",
                          "body": "TREVOR_MUST_SUPPLY",
                          "accent": "TREVOR_MUST_SUPPLY"}
        brand["font_policy"] = {"when_brand_fonts_missing": "derive-document",
                                "requires_rationale": True,
                                "requires_reviewer": True}
        run = os.path.join(self.tmp, "noreviewer")
        write_run(run, {"creative_direction": None},
                  {"selection_mode": "SECRET_SAUCE_ONLY",
                   "fonts_source": "derived",
                   "font_rationale": "documented"}, brand)
        r = run_validator(run)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("font_reviewer", r.stdout)

    def test_derived_bible_placeholder_font_still_fails(self):
        brand = json.loads(json.dumps(FIXTURE_BRAND))
        brand["fonts"] = {"display": "TREVOR_MUST_SUPPLY",
                          "body": "TREVOR_MUST_SUPPLY",
                          "accent": "TREVOR_MUST_SUPPLY"}
        brand["font_policy"] = {"when_brand_fonts_missing": "derive-document",
                                "requires_rationale": True,
                                "requires_reviewer": True}
        run = os.path.join(self.tmp, "placeholderfont")
        write_run(run, {"creative_direction": None},
                  {"selection_mode": "SECRET_SAUCE_ONLY",
                   "fonts": {"display": "TREVOR_MUST_SUPPLY"},
                   "fonts_source": "derived",
                   "font_rationale": "documented",
                   "font_reviewer": "reviewer-agent"}, brand)
        r = run_validator(run)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("placeholder", r.stdout)

    def test_derived_bible_banned_font_still_fails(self):
        brand = json.loads(json.dumps(FIXTURE_BRAND))
        brand["fonts"] = {"display": "TREVOR_MUST_SUPPLY",
                          "body": "TREVOR_MUST_SUPPLY",
                          "accent": "TREVOR_MUST_SUPPLY"}
        brand["font_policy"] = {"when_brand_fonts_missing": "derive-document",
                                "requires_rationale": True,
                                "requires_reviewer": True}
        run = os.path.join(self.tmp, "derivedbanned")
        write_run(run, {"creative_direction": None},
                  {"selection_mode": "SECRET_SAUCE_ONLY",
                   "fonts": {"body": "Inter"},
                   "fonts_source": "derived",
                   "font_rationale": "documented",
                   "font_reviewer": "reviewer-agent"}, brand)
        r = run_validator(run)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("banned_fonts", r.stdout)

    def test_non_font_must_supply_still_fails(self):
        # The carve-out covers fonts.* ONLY. Any other MUST_SUPPLY key in the
        # brand file still FAILS.
        brand = json.loads(json.dumps(FIXTURE_BRAND))
        brand["font_policy"] = {"when_brand_fonts_missing": "derive-document",
                                "requires_rationale": True,
                                "requires_reviewer": True}
        brand["logo"] = {"files": "TREVOR_MUST_SUPPLY"}
        run = os.path.join(self.tmp, "logomissing")
        write_run(run, {"creative_direction": None},
                  {"selection_mode": "SECRET_SAUCE_ONLY",
                   "fonts_source": "derived",
                   "font_rationale": "documented",
                   "font_reviewer": "reviewer-agent"}, brand)
        r = run_validator(run)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("logo.files", r.stdout)
        self.assertIn("TREVOR_MUST_SUPPLY", r.stdout)

    def test_within_tolerance_token_passes(self):
        # cream #F5F0E8 with tolerance 3: #F4F0E8 passes (diff 1 per channel).
        run = os.path.join(self.tmp, "tol")
        write_run(run, {"creative_direction": None},
                  {"selection_mode": "SECRET_SAUCE_ONLY",
                   "page_tokens": {"creamish": "#F4F0E8"},
                   "fonts": {"body": "Fixture Body"}},
                  FIXTURE_BRAND)
        r = run_validator(run)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_external_style_named_at_intake_passes(self):
        run = os.path.join(self.tmp, "ext")
        write_run(run, {"creative_direction": "VDL-001"},
                  {"selection_mode": "agent-selected", "style_id": "VDL-001",
                   "page_tokens": {}, "fonts": {}},
                  FIXTURE_BRAND)
        r = run_validator(run)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_missing_bible_exit_2(self):
        run = os.path.join(self.tmp, "nobile")
        os.makedirs(run)
        with open(os.path.join(run, "intake.json"), "w") as f:
            json.dump({"brand_file": os.path.join(self.tmp, "brand.json")}, f)
        with open(os.path.join(self.tmp, "brand.json"), "w") as f:
            json.dump(FIXTURE_BRAND, f)
        r = run_validator(run)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
