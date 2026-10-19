#!/usr/bin/env python3
"""SPF019: every wireframe and mockup is in the CLIENT's brand colors, or no image stage starts.

Known colors resolve with no ask; unknown colors produce the client ask and refuse; another
client's palette (or BlackCEO's) is never used for a client; the resolved palette reaches the
composed prompt. No generation, no network.
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import brand_colors as bc  # noqa: E402

TEMPLATE = json.loads((ROOT / "assets/brand/client-brand.template.json").read_text())
ACME = dict(TEMPLATE, brand_id="acme-coaching",
            palette={"gold": "#C0392B", "navy": "#1B2A41", "cream": "#FAF3E0"})
REQ = {"model": "stub", "sections": [
    {"section_id": "hero", "section_name": "Hero", "copy": "Join the class.", "slots": []}]}


def run(td, owner, brand=None, brand_file="brand/b.json"):
    d = Path(td)
    (d / "brand").mkdir()
    intake = {"brand_owner": owner}
    if brand_file:
        intake["brand_file"] = brand_file
    (d / "intake.json").write_text(json.dumps(intake))
    (d / "production-request.json").write_text(json.dumps(REQ))
    if brand is not None:
        (d / "brand" / "b.json").write_text(json.dumps(brand))
    return d


def preflight(d):
    return subprocess.run([sys.executable, str(ROOT / "scripts/stage_executor.py"), str(d), "--preflight"],
                          capture_output=True, text=True)


class BrandColorsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_known_colors_resolve_and_reach_the_prompt(self):
        d = run(self.tmp.name, "Acme Coaching", ACME)
        res = bc.resolve(d)
        self.assertTrue(res.ok)
        self.assertIn("brand_file", res.source)
        proc = preflight(d)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("#C0392B", proc.stdout)
        self.assertNotIn("#C9A227", proc.stdout)

    def test_missing_colors_ask_and_refuse(self):
        d = run(self.tmp.name, "Beta Studio", dict(TEMPLATE, brand_id="beta-studio"))
        self.assertFalse(bc.resolve(d).ok)
        self.assertIn("What are your brand colors?", bc.failure(d))
        proc = preflight(d)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("brand colors unresolved", proc.stdout)
        self.assertNotIn("PREFLIGHT_COLORS", proc.stdout)

    def test_another_clients_palette_is_never_used(self):
        d = run(self.tmp.name, "Gamma Co", ACME)
        self.assertFalse(bc.resolve(d).ok)
        self.assertIn("another client's palette is never used", bc.failure(d))

    def test_blackceo_palette_is_not_a_client_default(self):
        d = run(self.tmp.name, "Gamma Co", brand_file="assets/brand/blackceo-brand.json")
        self.assertFalse(bc.resolve(d).ok)
        d2 = Path(self.tmp.name) / "none"
        d2.mkdir()
        (d2 / "intake.json").write_text(json.dumps({"brand_owner": "Gamma Co"}))
        self.assertFalse(bc.resolve(d2).ok)
        self.assertEqual(bc.fallback_path(d2).name, bc.UNRESOLVED)

    def test_blackceo_own_run_still_resolves(self):
        d = run(self.tmp.name, "blackceo", brand_file="assets/brand/blackceo-brand.json")
        self.assertTrue(bc.resolve(d).ok)

    def test_stages_that_make_no_image_are_not_gated(self):
        d = run(self.tmp.name, "Beta Studio", dict(TEMPLATE, brand_id="beta-studio"))
        self.assertIsNone(bc.failure(d, "copy"))
        self.assertIsNotNone(bc.failure(d, "desktop-wireframe"))

    def test_record_writes_the_answer_and_a_color_name_is_refused(self):
        d = run(self.tmp.name, "Beta Studio", dict(TEMPLATE, brand_id="beta-studio"))
        with self.assertRaises(ValueError):
            bc.record(d, "teal", "#101010", ["#FFFFFF"])
        bc.record(d, "#112233", "#101010", ["#FFFFFF"], secondary="#445566", accents=["#FFAA00"])
        res = bc.resolve(d)
        self.assertTrue(res.ok)
        self.assertEqual(res.palette["gold"], "#112233")
        self.assertIn("secondary #445566", res.block())


if __name__ == "__main__":
    unittest.main(verbosity=2)
