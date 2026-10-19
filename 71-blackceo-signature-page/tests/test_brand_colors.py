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
import stage_gate  # noqa: E402
import validate_install  # noqa: E402
import validate_wireframe  # noqa: E402

TEMPLATE = json.loads((ROOT / "assets/brand/client-brand.template.json").read_text())
BLACKCEO = ROOT / "assets/brand/blackceo-brand.json"
GAMMA = dict(TEMPLATE, brand_id="gamma-co",
             palette={"gold": "#0A7E8C", "navy": "#102A43", "cream": "#FFF8E7"})
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
    return subprocess.run([sys.executable, str(ROOT / "scripts/stage_executor.py"), str(d), "--preflight", "--stages", "visual-mockup"],
                          capture_output=True, text=True)  # the board gate guards final-mockups, not the palette check


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

    # --- D1: the owner check is equality, never containment ---
    def test_owner_must_equal_brand_id_not_contain_it(self):
        # P1: "Acme" is a prefix of another client's "acme-coaching"
        self.assertFalse(bc.resolve(run(self.tmp.name, "Acme", ACME)).ok)

    def test_short_brand_id_does_not_match_a_longer_owner(self):
        # P2: brand_id "co" is inside "Gamma Co"
        d = Path(self.tmp.name) / "p2"
        d.mkdir()
        self.assertFalse(bc.resolve(run(d, "Gamma Co", dict(GAMMA, brand_id="co"))).ok)

    def test_blackceo_fallback_needs_exact_owner(self):
        # P6/P7: an owner that merely contains "blackceo" gets neither the file nor resolve
        d = Path(self.tmp.name) / "p6"
        d.mkdir()
        run(d, "BlackCEO client Jane Doe", brand_file="assets/brand/blackceo-brand.json")
        self.assertFalse(bc.resolve(d).ok)
        self.assertEqual(bc.fallback_path(d).name, bc.UNRESOLVED)
        own = Path(self.tmp.name) / "own"
        own.mkdir()
        self.assertEqual(bc.fallback_path(run(own, "BlackCEO")).name, BLACKCEO.name)

    def test_record_stamps_the_owner_so_its_own_file_resolves(self):
        d = run(self.tmp.name, "Beta Studio", dict(TEMPLATE, brand_id="somebody-else"), )
        bc.record(d, "#112233", "#101010", ["#FFFFFF"])
        self.assertTrue(bc.resolve(d).ok)

    def test_must_supply_names_unresolved_colors_not_an_unreadable_file(self):
        d = run(self.tmp.name, "Gamma Co", ACME)  # another client's file
        msg = stage_gate.run_builtin("gate:must_supply", [], d)
        self.assertIn("brand colors unresolved", msg)

    # --- D2/D3: prompts, gate and every QC check read the one resolved palette ---
    def _one_palette(self, d, want):
        res = bc.resolve(d)
        self.assertTrue(res.ok)
        self.assertEqual(res.path.resolve(), want.resolve())
        self.assertEqual(stage_gate.brand_path_for(d).resolve(), want.resolve())
        self.assertEqual(stage_gate.brand_path_for_checked(d).resolve(), want.resolve())
        self.assertEqual(validate_wireframe.resolve_brand_path(d, None).resolve(), want.resolve())
        self.assertEqual(validate_install.brand_path_for(d).resolve(), want.resolve())
        cmd, lines = stage_gate.resolve_brand_placeholder("x {brand}", d, "visual-mockup", None)
        self.assertEqual(lines, [])
        self.assertEqual(Path(cmd.split(" ", 1)[1].strip("'")).resolve(), want.resolve())

    def test_foreign_pin_is_skipped_by_every_resolver(self):
        # P3: pin is BlackCEO's file, intake points at Gamma's valid file
        d = run(self.tmp.name, "Gamma Co", GAMMA)
        (d / "private").mkdir()
        (d / "private" / "brand.json").write_text(BLACKCEO.read_text())
        self._one_palette(d, d / "brand" / "b.json")

    def test_pin_wins_over_a_foreign_intake_file_everywhere(self):
        # P4b: pin is Gamma's valid palette, intake.brand_file is BlackCEO's absolute path
        d = run(self.tmp.name, "Gamma Co", brand_file=str(BLACKCEO))
        (d / "private").mkdir()
        (d / "private" / "brand.json").write_text(json.dumps(GAMMA))
        self._one_palette(d, d / "private" / "brand.json")


if __name__ == "__main__":
    unittest.main(verbosity=2)
