#!/usr/bin/env python3
"""Regression lock for the GPT Image 2.6 owner prompt cap (20,000).

Owner ruling 2026-11-08: `owner_prompt_cap_chars` in 66-kie-image/models.json outranks
the vendor schema's published 32,000. The landed fix (8f8d387aa) shipped no test, so this
pins the resolution in all three skills that read it: 66, 71 and 74.

No repo service, pin or network is touched: the three modules are loaded by path.
"""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL = "gpt-image-2-6/sunburst-text-to-image"
CAP = 20000


def _load(rel, name):
    path = ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(path.parent))
    return module


class OwnerCapInData(unittest.TestCase):
    def test_both_gpt_image_2_6_rows_declare_20000(self):
        rows = json.loads((ROOT / "66-kie-image" / "models.json").read_text(encoding="utf-8"))
        entries = [e for e in rows["models"] if "gpt-image-2-6" in (e.get("family") or "")]
        self.assertGreaterEqual(len(entries), 2, "expected the t2i and i2i 2.6 rows")
        for e in entries:
            self.assertEqual(e.get("owner_prompt_cap_chars"), CAP,
                             f"{e.get('canonical_model_id')} must declare the owner cap")

    def test_vendor_figure_never_becomes_the_limit(self):
        rows = json.loads((ROOT / "66-kie-image" / "models.json").read_text(encoding="utf-8"))
        for e in rows["models"]:
            if "gpt-image-2-6" in (e.get("family") or ""):
                self.assertNotEqual(e.get("owner_prompt_cap_chars"), 32000)


class Skill66Resolves20000(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v = _load("66-kie-image/scripts/validate_prompt.py", "s66_validate_prompt")

    def test_19500_passes_not_below_floor(self):
        r = self.v.validate_body("x" * 19500, MODEL, False)
        self.assertEqual(r["max"], CAP)
        self.assertEqual(r["status"], "PASS")
        self.assertTrue(r["valid"])

    def test_20000_passes(self):
        self.assertEqual(self.v.validate_body("x" * CAP, MODEL, False)["status"], "PASS")

    def test_20001_is_above_max(self):
        r = self.v.validate_body("x" * (CAP + 1), MODEL, False)
        self.assertEqual(r["status"], "ABOVE_MAX")
        self.assertFalse(r["valid"])


class Skill71Resolves20000(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.se = _load("71-blackceo-signature-page/scripts/stage_executor.py", "s71_stage_executor")

    def test_band_is_built_on_20000(self):
        budget = self.se.prompt_budget(MODEL)
        self.assertEqual(budget["max_chars"], CAP)
        self.assertEqual(budget["floor_chars"], 19000)
        self.assertEqual(budget["hard_floor_chars"], 16000)

    def test_cap_alias(self):
        self.assertEqual(self.se.prompt_cap(MODEL), CAP)


class Skill74Resolves20000(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.kla = _load("74-kie-live-adapter/scripts/kie_live_adapter.py", "s74_live_adapter")

    def test_owner_cap_wins(self):
        cap, owner = self.kla.policy_owner_cap(MODEL)
        self.assertEqual(cap, CAP)
        self.assertEqual(owner, "66-kie-image")


if __name__ == "__main__":
    unittest.main(verbosity=2)
