"""Deterministic L1 tests for the brand loader component (doc 16 s.1-2)."""

import importlib.util
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


loader = _load("sl_brand_loader", "brand_loader", "brand_loader.py")


def _fixture(name):
    return os.path.join(FIXTURES, name)


class LoadBrand(unittest.TestCase):
    def test_complete_brand_loads_and_resolves(self):
        brand = loader.load_brand(_fixture("brand_test_alpha.json"))
        self.assertEqual(brand["brand_id"], "TEST-ONLY-alpha")
        res = loader.load_brand_tokens(_fixture("brand_test_alpha.json"))
        self.assertTrue(res["complete"])
        self.assertEqual(res["missing"], [])
        self.assertEqual(res["colors"]["accent"], "#AA8800")

    def test_missing_required_key_is_a_load_failure(self):
        with self.assertRaises(loader.BrandLoadError) as caught:
            loader.load_brand(_fixture("brand_missing_key.json"))
        self.assertTrue(
            any("palette" in problem for problem in caught.exception.problems)
        )

    def test_malformed_file_is_a_load_failure(self):
        with self.assertRaises(loader.BrandLoadError):
            loader.load_brand(_fixture("brand_malformed.txt"))

    def test_nonexistent_file_is_a_load_failure(self):
        with self.assertRaises(loader.BrandLoadError):
            loader.load_brand(_fixture("brand_does_not_exist.json"))


class MissingValueFailureMode(unittest.TestCase):
    """Sentinel values load, are reported missing, and are never filled."""

    def test_incomplete_brand_reports_missing_without_inventing(self):
        res = loader.load_brand_tokens(_fixture("brand_incomplete.json"))
        self.assertFalse(res["complete"])
        fields = {entry["field"] for entry in res["missing"]}
        self.assertIn("palette.gold", fields)
        self.assertIn("founder_photos", fields)
        # The loader must not substitute any value for the missing gold.
        self.assertIsNone(res["colors"]["accent"])
        self.assertIsNone(res["colors"]["palette"]["gold"])
        # Present values still resolve normally.
        self.assertEqual(res["colors"]["ground_dark"], "#22304A")
        self.assertEqual(res["typography"]["body"], "Incomplete Body Face")


if __name__ == "__main__":
    unittest.main()
