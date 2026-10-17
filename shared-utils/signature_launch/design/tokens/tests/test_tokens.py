"""Deterministic L1 tests for the design tokens component (doc 16 s.1-2)."""

import importlib.util
import json
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
DESIGN = os.path.abspath(os.path.join(HERE, "..", ".."))
FIXTURES = os.path.join(DESIGN, "tests", "fixtures")


def _load(name, *relpath):
    spec = importlib.util.spec_from_file_location(name, os.path.join(DESIGN, *relpath))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tokens = _load("sl_tokens", "tokens", "tokens.py")


def _brand(name):
    with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as handle:
        return json.load(handle)


class ResolveFromFixtureBrand(unittest.TestCase):
    def test_tokens_resolve_from_fixture_brand(self):
        res = tokens.resolve_tokens(_brand("brand_test_alpha.json"))
        self.assertEqual(res["brand_id"], "TEST-ONLY-alpha")
        self.assertEqual(res["colors"]["accent"], "#AA8800")
        self.assertEqual(res["colors"]["ground_dark"], "#101828")
        self.assertEqual(res["colors"]["ground_light"], "#FAF6ED")
        self.assertEqual(res["colors"]["logo_black"], "#000000")
        self.assertEqual(res["typography"]["display"], "Test Serif Display")
        self.assertEqual(res["typography"]["body"], "Test Sans Body")
        self.assertEqual(res["assets"]["logo_files"], "test-only/alpha-logo.png")
        self.assertTrue(res["complete"])
        self.assertEqual(res["missing"], [])

    def test_second_brand_resolves_its_own_values(self):
        res = tokens.resolve_tokens(_brand("brand_test_beta.json"))
        self.assertEqual(res["colors"]["accent"], "#0E7C66")
        self.assertEqual(res["colors"]["ground_dark"], "#2B2118")
        self.assertEqual(res["typography"]["display"], "Beta Display Face")
        self.assertTrue(res["complete"])

    def test_css_contains_resolved_variables(self):
        res = tokens.resolve_tokens(_brand("brand_test_alpha.json"))
        css = tokens.tokens_to_css(res)
        self.assertIn("--sl-color-accent: #AA8800;", css)
        self.assertIn('--sl-font-display: "Test Serif Display";', css)
        self.assertIn("--sl-space-md: 1rem;", css)


class MissingValues(unittest.TestCase):
    def test_sentinels_resolve_to_none_and_are_named(self):
        res = tokens.resolve_tokens(_brand("brand_incomplete.json"))
        self.assertIsNone(res["colors"]["accent"])
        self.assertIsNone(res["colors"]["ground_light"])
        self.assertEqual(res["colors"]["ground_dark"], "#22304A")
        self.assertIsNone(res["typography"]["display"])
        self.assertIsNone(res["assets"]["founder_photos"])
        self.assertFalse(res["complete"])
        fields = {entry["field"] for entry in res["missing"]}
        self.assertEqual(
            fields,
            {
                "palette.gold",
                "palette.cream",
                "fonts.display",
                "fonts.accent",
                "logo.files",
                "founder_photos",
            },
        )

    def test_css_omits_unresolved_variables(self):
        res = tokens.resolve_tokens(_brand("brand_incomplete.json"))
        css = tokens.tokens_to_css(res)
        self.assertNotIn("--sl-color-accent", css)
        self.assertNotIn("--sl-font-display", css)
        self.assertIn("--sl-color-ground-dark: #22304A;", css)

    def test_spacing_is_labeled_library_default(self):
        res = tokens.resolve_tokens(_brand("brand_test_alpha.json"))
        self.assertEqual(res["spacing"]["source"], "library_default")
        self.assertEqual(res["radii"]["source"], "library_default")


if __name__ == "__main__":
    unittest.main()
