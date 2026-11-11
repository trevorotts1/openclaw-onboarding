#!/usr/bin/env python3
"""F16 S2 on Skill 49's C3 surface: one style vocabulary, the plan's brand hash, one grade mode.

Free: reads and validates a JSON file; no network, no provider, no page build.
Run: python3 49-signature-funnel/scripts/test_f16_c3_brand_binding.py
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
_spec = importlib.util.spec_from_file_location("pset", HERE / "page_set.py")
pset = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pset)


class C3Tests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.brand = self.tmp / "brand.json"
        self.brand.write_text(json.dumps({"palette_status": "provided"}), encoding="utf-8")
        self.digest = hashlib.sha256(self.brand.read_bytes()).hexdigest()

    def write(self, doc, name="image_inputs.json"):
        path = self.tmp / name
        base = {"design_style": "B", "design_style_source": "client_choice",
                "brand_file": str(self.brand), "brand_owner": "TEST-ONLY Client",
                "image_cap": 40, "image_provider": "stub", "test_only": True}
        base.update(doc)
        path.write_text(json.dumps(base), encoding="utf-8")
        return path

    def test_the_new_f16_keys_are_part_of_the_contract(self):
        for key in ("brand_sha256", "creative_direction_source", "creative_direction_grade_mode"):
            self.assertIn(key, pset.IMAGE_INPUT_KEYS)

    def test_a_matching_plan_brand_hash_passes(self):
        got = pset.load_image_inputs(self.write({"brand_sha256": self.digest}))
        self.assertEqual(got["brand_sha256"], self.digest)
        self.assertFalse(got["allow_paid"])

    def test_a_substituted_brand_file_is_refused(self):
        with self.assertRaises(pset.PageSetError) as ctx:
            pset.load_image_inputs(self.write(
                {"brand_sha256": hashlib.sha256(b"another brand file").hexdigest()}))
        self.assertIn("does not match the brand file", str(ctx.exception))

    def test_the_two_spellings_of_an_accepted_recommendation_read_as_one(self):
        for spelling in ("accepted_recommendation", "recommended_accepted"):
            got = pset.load_image_inputs(self.write({"design_style_source": spelling}))
            self.assertEqual(got["design_style_source"], "recommended_accepted", spelling)

    def test_an_invented_style_source_is_refused(self):
        with self.assertRaises(pset.PageSetError) as ctx:
            pset.load_image_inputs(self.write({"design_style_source": "made_up"}))
        self.assertIn("design_style_source", str(ctx.exception))

    def test_the_grade_mode_and_direction_source_are_checked_against_one_vocabulary(self):
        for mode in ("FULL", "ADAPT", "SUPPRESS"):
            got = pset.load_image_inputs(self.write({"creative_direction_grade_mode": mode,
                                                     "creative_direction_source": "recorded"}))
            self.assertEqual(got["creative_direction_grade_mode"], mode)
        for bad in ({"creative_direction_grade_mode": "HALF"},
                    {"creative_direction_source": "made_up"},
                    {"brand_sha256": "not-a-hash"}):
            with self.assertRaises(pset.PageSetError, msg=bad):
                pset.load_image_inputs(self.write(bad, "bad.json"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
