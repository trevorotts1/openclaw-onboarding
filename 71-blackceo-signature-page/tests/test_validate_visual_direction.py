#!/usr/bin/env python3
"""Tests for validate_visual_direction.py (order A2).

Fixture brand file is used, never the real blackceo-brand.json — the real
one still has TREVOR_MUST_SUPPLY fonts, which would make every run fail for
the wrong reason.
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

    def test_must_supply_brand_fails_naming_keys(self):
        brand = json.loads(json.dumps(FIXTURE_BRAND))
        brand["fonts"] = {"display": "TREVOR_MUST_SUPPLY",
                          "body": "TREVOR_MUST_SUPPLY",
                          "accent": "TREVOR_MUST_SUPPLY"}
        run = os.path.join(self.tmp, "missing")
        write_run(run, {"creative_direction": None},
                  {"selection_mode": "SECRET_SAUCE_ONLY"}, brand)
        r = run_validator(run)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertEqual(r.stdout.count("TREVOR_MUST_SUPPLY"), 3)
        self.assertIn("fonts.display", r.stdout)

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
