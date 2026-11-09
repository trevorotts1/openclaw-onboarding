#!/usr/bin/env python3
"""SPF020: the page color system, the image grade, and the page-level pixel check.

Pins: the blocks carry only the client's colors; Trevor's grade wording is verbatim; grounds change
section to section; the blocks reach the mockup and image-slot prompts and nothing else; the pixel
check passes a hypersaturated page, fails a calm one, follows the client's hero hue, and its
thresholds are exactly what the derivation rule gives for the two reference pages.
"""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


sys.path.insert(0, str(ROOT / "scripts"))
hs = _load("hypersaturation", "scripts/hypersaturation.py")
exe = _load("stage_executor", "scripts/stage_executor.py")

try:
    from PIL import Image, ImageDraw
    pvc = _load("validate_page_color", "scripts/validate_page_color.py")
except ImportError:  # Pillow is a declared optional dependency of the pixel tests
    Image = None

# A made-up client. Never a real brand, never the examples' red, green or tan.
CLIENT = {"primary": "#0B5FFF", "secondary": "#0A0A12", "accent": "#FFB400",
          "background": "#FFFFFF", "text": "#0A0A12"}
EXAMPLE_COLORS = ("#BF031C", "#BB0102", "#B80000", "#1ED650", "#E4A967", "#C9A227", "#A64335")
SECTION = {"section_id": "S01", "section_name": "Hero", "copy": "You are doing every job. CTA: SAVE MY SEAT.",
           "slots": [{"slot_id": "IMG-001", "aspect_ratio": "3:4", "art_direction": "Founder at a desk."}]}
REQUEST = {"model": "gpt-image-2-5-sunburst-image-to-image", "style": "client colors",
           "stage_prompts": {"visual-mockup": "Mockup {section_number} {section_name} {width} {ratio} {copy} {slots}",
                             "desktop-wireframe": "Wireframe {section_number} {copy} {slots}"}}


class RolesTests(unittest.TestCase):
    def test_roles_from_roles_form(self):
        r = hs.roles({}, CLIENT)
        self.assertEqual((r["hero"], r["dark"], r["light"], r["accent"]),
                         ("#0B5FFF", "#0A0A12", "#FFFFFF", "#FFB400"))

    def test_one_chromatic_palette_has_no_accent_and_none_is_invented(self):
        r = hs.roles({"gold": "#C9A227", "navy": "#1A1A2E", "cream": "#F5F0E8"})
        self.assertEqual(r["hero"], "#C9A227")
        self.assertIsNone(r["accent"])
        block = hs.page_block(r, "hero")
        self.assertIn("no second chromatic color", block)
        self.assertNotIn("(gold) is small", block)

    def test_too_small_a_palette_is_refused(self):
        with self.assertRaises(ValueError):
            hs.roles({"only": "#0B5FFF"})

    def test_neutral_primary_falls_back_to_most_chromatic(self):
        r = hs.roles({}, {"primary": "#222222", "secondary": "#0B5FFF", "background": "#FFFFFF"})
        self.assertEqual(r["hero"], "#0B5FFF")


class BlockTests(unittest.TestCase):
    def setUp(self):
        self.r = hs.roles({}, CLIENT)

    def test_blocks_carry_only_client_colors(self):
        text = "\n".join(hs.page_block(self.r, g) for g in hs.GROUNDS) + hs.grade_block(self.r)
        for ex in EXAMPLE_COLORS:
            self.assertNotIn(ex, text.upper())
        for c in CLIENT.values():
            self.assertIn(c.upper(), text.upper())

    def test_grade_block_is_trevors_wording(self):
        g = hs.grade_block(self.r)
        for phrase in ("hyper-saturated cinematic color grade", "deep true blacks, crushed shadows",
                       "vivid fully saturated #0B5FFF (blue) and #FFB400 (gold)", "clean bright whites",
                       "high contrast, punchy midtones", "strong directional key + rim light",
                       "luminous natural skin", "no muted, matte, faded, pastel, washed-out, flat or "
                       "low-contrast grade, no grey haze, no warm ivory wash as the white"):
            self.assertIn(phrase, g)

    def test_each_ground_names_its_own_color(self):
        for ground in hs.GROUNDS:
            self.assertIn(f"THIS SLICE sits on the {ground.upper()} ground {self.r[ground]}",
                          hs.page_block(self.r, ground))

    def test_rotation_changes_ground_every_section_and_pins_win(self):
        seq = [hs.ground_for(i) for i in range(1, 9)]
        self.assertTrue(all(a != b for a, b in zip(seq, seq[1:])), seq)
        self.assertEqual(hs.ground_for(1, {"ground": "dark"}), "dark")
        self.assertEqual(hs.ground_for(1, {"ground": "teal"}), "hero")

    def test_item_prompt_adds_grade_once(self):
        once = hs.item_prompt("Founder at a desk.", self.r)
        self.assertTrue(once.startswith(hs.MARKER_GRADE))
        self.assertEqual(hs.item_prompt(once, self.r), once)
        self.assertEqual(hs.item_prompt("x", None), "x")

    def test_blocks_fit_the_budget_they_claim(self):
        page = hs.page_block(self.r, "hero")
        self.assertLessEqual(len(page), 2000)
        self.assertLessEqual(len(hs.grade_block(self.r)), 700)


class WiringTests(unittest.TestCase):
    def test_mockup_prompt_gets_both_blocks_and_counts_them(self):
        req = dict(REQUEST, _hypersat=hs.roles({}, CLIENT))
        prompt, sizes = exe.stage_prompt("visual-mockup", SECTION, 1, 1440, req, "3:4", with_sizes=True)
        self.assertIn(hs.MARKER_PAGE, prompt)
        self.assertIn(hs.MARKER_GRADE, prompt)
        self.assertGreater(sizes["hypersaturation_chars"], 1500)
        self.assertGreaterEqual(sizes["contract_chars"], sizes["hypersaturation_chars"])
        self.assertTrue(prompt.startswith("VERBATIM COPY"))

    def test_wireframe_stage_gets_no_blocks(self):
        req = dict(REQUEST, _hypersat=hs.roles({}, CLIENT))
        wire = exe.stage_prompt("desktop-wireframe", SECTION, 1, 1440, req, "3:4")
        self.assertNotIn(hs.MARKER_PAGE, wire)
        self.assertNotIn(hs.MARKER_GRADE, wire)

    def test_mockup_stage_without_a_palette_refuses_never_sends_bare(self):
        for stage in hs.MOCKUP_STAGES:
            with self.assertRaises(exe.ExecutorError) as cm:
                exe.stage_prompt(stage, SECTION, 1, 1440, dict(REQUEST, _hypersat=None), "3:4")
            self.assertIn("no resolved client palette", str(cm.exception))

    def test_prose_naming_another_palette_refuses(self):
        req = dict(REQUEST, _hypersat=hs.roles({}, CLIENT))
        req["stage_prompts"] = dict(req["stage_prompts"],
                                    **{"visual-mockup": "Ground ivory #FAF9F5, CTA rust #a64335, ink #0a0a12. {copy}"})
        with self.assertRaises(exe.ExecutorError) as cm:
            exe.stage_prompt("visual-mockup", SECTION, 1, 1440, req, "3:4")
        self.assertIn("#A64335", str(cm.exception))
        self.assertIn("#FAF9F5", str(cm.exception))
        self.assertNotIn("#0A0A12", str(cm.exception))  # the client's own hex is fine

    def test_foreign_hexes_reads_three_digit_and_ignores_client_colors(self):
        r = hs.roles({}, CLIENT)
        self.assertEqual(hs.foreign_hexes("a #fff b #0b5fff c #F00", r), ["#FF0000"])
        self.assertEqual(hs.foreign_hexes("#0B5FFF #0a0a12 #FFB400 #FFFFFF", r), [])
        self.assertEqual(hs.foreign_hexes("#abc", r), ["#AABBCC"])

    def test_item_without_a_palette_refuses(self):
        with tempfile.TemporaryDirectory() as d:
            run = Path(d)
            (run / "image-inventory-prompts").mkdir()
            (run / "image-inventory-prompts" / "IMG-001.txt").write_text("Founder at a desk.")
            with self.assertRaises(exe.ExecutorError):
                exe.run_item(run, "image-generation-qc", "IMG-001", {}, exe.StubProvider(), False)

    def test_run_without_a_palette_resolves_to_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(hs.roles_for_run(d))

    def test_run_with_a_brand_file_resolves_roles(self):
        with tempfile.TemporaryDirectory() as d:
            run = Path(d)
            (run / "brand.json").write_text(json.dumps(
                {"brand_id": "test-client", "palette": {"a": "#0B5FFF", "b": "#0A0A12", "c": "#FFFFFF"},
                 "palette_roles": CLIENT}))
            (run / "intake.json").write_text(json.dumps(
                {"brand_owner": "test-client", "brand_file": "brand.json"}))
            r = hs.roles_for_run(run)
            self.assertIsNotNone(r)
            self.assertEqual(r["hero"], "#0B5FFF")

    def test_run_resolves_the_same_brand_file_as_the_stage_gate(self):
        # owner order: intake names the owner and the skill's bundled file (SPF019: the run's palette is
        # always named, never assumed from the owner alone); a pinned private/brand.json wins; another
        # client's owner never gets the bundled palette.
        with tempfile.TemporaryDirectory() as d:
            run = Path(d)
            (run / "intake.json").write_text(json.dumps(
                {"brand_owner": "blackceo", "brand_file": "assets/brand/blackceo-brand.json"}))
            r = hs.roles_for_run(run)
            self.assertIsNotNone(r)
            self.assertEqual((r["hero"], r["dark"], r["light"]), ("#C9A227", "#1A1A2E", "#F5F0E8"))
            (run / "private").mkdir()
            (run / "private" / "brand.json").write_text(json.dumps(
                {"brand_id": "blackceo", "palette": {"a": "#0B5FFF", "b": "#0A0A12", "c": "#FFFFFF"}}))
            self.assertEqual(hs.roles_for_run(run)["hero"], "#0B5FFF")
            (run / "intake.json").write_text(json.dumps({"brand_owner": "someone-else"}))
            self.assertIsNone(hs.roles_for_run(run))


@unittest.skipIf(Image is None, "Pillow not importable")
class PixelCheckTests(unittest.TestCase):
    @staticmethod
    def _page(bands, w=300):
        """bands: list of (rgb, height). A flat-band page; text-free, which is all the metrics read."""
        img = Image.new("RGB", (w, sum(h for _, h in bands)))
        d, y = ImageDraw.Draw(img), 0
        for rgb, h in bands:
            d.rectangle([0, y, w, y + h], fill=rgb)
            y += h
        return img

    def _check(self, img, hero):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "page.png"
            img.save(p)
            m = pvc.measure(p, hero)
        return pvc.verdict(pvc.evaluate(m, pvc.load_thresholds())), m

    def test_hypersaturated_page_passes_for_any_hero_hue(self):
        for hero_rgb, hero_hex in (((11, 95, 255), "#0B5FFF"), ((200, 20, 30), "#C8141E")):
            page = self._page([(hero_rgb, 300), ((255, 255, 255), 250), ((8, 8, 12), 250), ((255, 255, 255), 200)])
            verdict, m = self._check(page, hero_hex)
            self.assertEqual(verdict, "PASS", m)

    def test_calm_ivory_page_fails(self):
        page = self._page([((250, 249, 245), 400), ((22, 47, 35), 150), ((240, 222, 219), 300), ((250, 249, 245), 150)])
        verdict, m = self._check(page, "#A64335")
        self.assertEqual(verdict, "FAIL", m)

    def test_wrong_hero_fails_only_the_hero_metric(self):
        page = self._page([((11, 95, 255), 300), ((255, 255, 255), 250), ((8, 8, 12), 250), ((255, 255, 255), 200)])
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "page.png"
            page.save(p)
            rows = pvc.evaluate(pvc.measure(p, "#00A650"), pvc.load_thresholds())
        failed = [r["metric"] for r in rows if r["status"] == "FAIL"]
        self.assertEqual(failed, ["hero_hue_saturated_share"])

    def test_hero_metric_skipped_without_hero(self):
        page = self._page([((11, 95, 255), 300), ((255, 255, 255), 300)])
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "page.png"
            page.save(p)
            rows = pvc.evaluate(pvc.measure(p), pvc.load_thresholds())
        self.assertEqual([r["status"] for r in rows if r["metric"].startswith("hero")], ["SKIPPED"])

    def test_missing_thresholds_is_undetermined_not_a_pass(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "page.png"
            self._page([((11, 95, 255), 100)]).save(p)
            self.assertEqual(pvc.main(["check", str(p), "--thresholds", str(Path(d) / "nope.json")]), 3)

    def test_thresholds_file_is_exactly_the_derivation_of_the_two_references(self):
        data = pvc.load_thresholds()
        va, vb = (data["references"][k]["measures"] for k in ("va", "vb"))
        derived = pvc.derive(va, vb)
        self.assertEqual({k: v["bound"] for k, v in derived.items()},
                         {k: v["bound"] for k, v in data["thresholds"].items()})
        for name, rule in data["thresholds"].items():
            weaker = min(va[name], vb[name]) if rule["kind"] == "floor" else max(va[name], vb[name])
            self.assertTrue(rule["bound"] <= weaker if rule["kind"] == "floor" else rule["bound"] >= weaker,
                            f"{name}: the bound must sit on the permissive side of both references")


if __name__ == "__main__":
    if Image is None:
        print("SKIPMOD test_hypersaturation.py: Pillow not importable (pixel tests need it)")
    unittest.main(verbosity=2)
