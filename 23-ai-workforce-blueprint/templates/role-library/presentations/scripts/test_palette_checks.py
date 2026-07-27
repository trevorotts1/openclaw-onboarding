"""Tests for U050 palette-check repairs: _png_dominant_hue_bucket fix, staging flags,
_imaging_available dependency probe, and warn-mode recording."""

import json, os, sys, tempfile, unittest
from pathlib import Path
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_deck as bd

def _make_solid_slides(dest_dir, colour, count=20, width=2048, height=1152):
    for i in range(1, count + 1):
        Image.new("RGB", (width, height), colour).save(dest_dir / f"slide-{i:02d}.png")

def _make_margin_slides(dest_dir, margin_colour, inset_colours, count=20, width=2048, height=1152):
    inset_w, inset_h = 1808, 912
    inset_x = (width - inset_w) // 2
    inset_y = (height - inset_h) // 2
    for i in range(1, count + 1):
        im = Image.new("RGB", (width, height), margin_colour)
        fill = inset_colours[(i - 1) % len(inset_colours)]
        inset = Image.new("RGB", (inset_w, inset_h), fill)
        im.paste(inset, (inset_x, inset_y))
        im.save(dest_dir / f"slide-{i:02d}.png")

class TestPaletteChecks(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self._tmp.name)
        (self.run_dir / "renders").mkdir()
        (self.run_dir / "working" / "copy").mkdir(parents=True)
        (self.run_dir / "working" / "copy" / "intake.json").write_text(json.dumps({"brand": {}}), encoding="utf-8")
    def tearDown(self):
        self._tmp.cleanup()

    def test_01_white_deck_regression_lock_enforced(self):
        _make_solid_slides(self.run_dir / "renders", (255, 255, 255), count=20)
        saved = bd.VISUAL_VARIETY_NEUTRAL_HUE_ENFORCED
        try:
            bd.VISUAL_VARIETY_NEUTRAL_HUE_ENFORCED = True
            result = bd.check_visual_variety(self.run_dir)
        finally:
            bd.VISUAL_VARIETY_NEUTRAL_HUE_ENFORCED = saved
        self.assertIsNotNone(result)
        self.assertNotEqual(result, "")
        self.assertIn("monotone_palette", result)

    def test_02_lightgrey_deck_enforced(self):
        _make_solid_slides(self.run_dir / "renders", (240, 240, 240), count=20)
        saved = bd.VISUAL_VARIETY_NEUTRAL_HUE_ENFORCED
        try:
            bd.VISUAL_VARIETY_NEUTRAL_HUE_ENFORCED = True
            result = bd.check_visual_variety(self.run_dir)
        finally:
            bd.VISUAL_VARIETY_NEUTRAL_HUE_ENFORCED = saved
        self.assertIsNotNone(result)
        self.assertNotEqual(result, "")
        self.assertIn("monotone_palette", result)

    def test_03_black_deck_shipped_default(self):
        _make_solid_slides(self.run_dir / "renders", (0, 0, 0), count=20)
        result = bd.check_visual_variety(self.run_dir)
        self.assertIsNotNone(result)
        self.assertNotEqual(result, "")
        self.assertIn("monotone_dark_palette", result)
        self.assertNotIn("monotone_palette", result)

    def test_04_varied_solid_fill_passes_both_flags(self):
        families = [(20, 40, 180), (180, 40, 20), (20, 180, 40), (200, 200, 20)]
        for i in range(1, 21):
            c = families[(i - 1) % len(families)]
            Image.new("RGB", (2048, 1152), c).save(self.run_dir / "renders" / f"slide-{i:02d}.png")
        for flag_pos in (False, True):
            saved = bd.VISUAL_VARIETY_NEUTRAL_HUE_ENFORCED
            try:
                bd.VISUAL_VARIETY_NEUTRAL_HUE_ENFORCED = flag_pos
                result = bd.check_visual_variety(self.run_dir)
            finally:
                bd.VISUAL_VARIETY_NEUTRAL_HUE_ENFORCED = saved
            self.assertEqual(result, "")

    def test_05_png_dominant_hue_bucket_white_returns_36(self):
        png = self.run_dir / "renders" / "white.png"
        Image.new("RGB", (2048, 1152), (255, 255, 255)).save(png)
        self.assertEqual(bd._png_dominant_hue_bucket(png), 36)

    def test_06_imaging_unavailable_fails_both_checkers(self):
        Image.new("RGB", (2048, 1152), (255, 255, 255)).save(self.run_dir / "renders" / "slide-01.png")
        (self.run_dir / "working" / "copy" / "intake.json").write_text(json.dumps({"brand": {"palette": ["#0A2540"]}}), encoding="utf-8")
        orig = bd._imaging_available
        try:
            bd._imaging_available = lambda: False
            vv = bd.check_visual_variety(self.run_dir)
            bc = bd.check_brand_consistency(self.run_dir)
        finally:
            bd._imaging_available = orig
        self.assertIn("pip install Pillow", vv)
        self.assertIn("pip install Pillow", bc)

    def test_07_staged_warning_is_written(self):
        _make_solid_slides(self.run_dir / "renders", (255, 255, 255), count=20)
        result = bd.check_visual_variety(self.run_dir)
        self.assertEqual(result, "")
        wp = self.run_dir / "working" / "qc" / "staged_warnings.json"
        self.assertTrue(wp.exists())
        data = json.loads(wp.read_text(encoding="utf-8"))
        self.assertEqual(data.get("neutral_hue_dominance"), 1)

    def test_08_white_margin_varied_inset_passes_at_default(self):
        inset_colours = [(20, 40, 180), (180, 40, 20), (20, 180, 40), (200, 200, 20)]
        _make_margin_slides(self.run_dir / "renders", (255, 255, 255), inset_colours, count=20)
        self.assertEqual(bd.check_visual_variety(self.run_dir), "")

if __name__ == "__main__":
    unittest.main()
