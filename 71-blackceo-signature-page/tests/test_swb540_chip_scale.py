#!/usr/bin/env python3
"""SWB-540 (1.3.55): the W1 numbered-chip measure scales with the slice width.

The thank-you MOBILE slices (390 px wide) drew the spec's own chip (a filled red
"SECTION N" block beside a grey name tab) and W1 rejected it: at 390 px a legible
chip is 26 to 40 px tall, 7 to 10 percent of the width, and the limit was 8 percent
after a fixed 7 px dilation calibrated for the 720 px working width of a desktop slice.
The height share now rises with narrowness (0.08 at 720 px and wider, 0.12 at 390 px and
narrower) and the dilation shrinks in proportion. These tests prove the correct chip
passes at 390 px, that a label tab, a black chip, a missing chip, a hollow chip and a
too-tall block still fail there, and that desktop behaviour is unchanged.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

try:
    from PIL import Image, ImageDraw
except Exception:
    print("SKIPMOD Pillow is not installed; W1 pixel tests cannot run")
    sys.exit(0)

import validate_wireframe as V  # noqa: E402

RED = (237, 28, 36)
PALETTE = [RED, (0, 0, 0), (255, 255, 255)]
GREY = (230, 230, 230)


def make(width, height, boxes, knock=True):
    """A white slice with filled boxes: (x, y, w, h, colour). A box with a colour near
    RED gets white 'text' knocked out of it, as a real chip does."""
    img = Image.new("RGB", (width, height), (255, 255, 255))
    d = ImageDraw.Draw(img)
    for x, y, w, h, colour in boxes:
        d.rectangle([x, y, x + w - 1, y + h - 1], fill=colour)
        if knock and colour == RED:
            # letter-like white strokes, 2 px wide at 390 and 4 px wide at 1440
            s = max(2, round(width / 195))
            tx, ty = x + w // 8, y + h // 4
            for i in range(6):
                d.rectangle([tx + i * (s * 4), ty, tx + i * (s * 4) + s - 1, y + h - h // 4], fill=(255, 255, 255))
    return img


def chips_of(img, slice_zone=True):
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "slice.png"
        img.save(p)
        measured = V.measure_style(p, PALETTE, slice_zone=slice_zone)
        lines = V.style_failures("slice", measured, "test-brand")
    return measured["chips"], lines


class MobileChipScale(unittest.TestCase):
    def test_correct_small_red_chip_with_grey_name_tab_passes_at_390(self):
        # the shape the spec asks for and the model drew: red SECTION N chip + grey name tab
        img = make(390, 693, [(12, 52, 96, 38, RED), (108, 52, 200, 38, GREY)])
        chips, lines = chips_of(img)
        self.assertEqual(len(chips), 1, chips)
        self.assertEqual(lines["W1"], [])

    def test_the_measured_thank_you_chip_height_passes(self):
        # 40 px of 390 is 10.3 percent: over the old 8 percent, inside the narrow limit
        img = make(390, 693, [(12, 50, 104, 40, RED)])
        chips, lines = chips_of(img)
        self.assertEqual(lines["W1"], [])
        self.assertTrue(chips)

    def test_label_tab_white_words_across_red_fails(self):
        # "SECTION 2 / ORDER SUMMARY" as one wide red tab
        img = make(390, 693, [(12, 52, 290, 38, RED)])
        chips, lines = chips_of(img)
        self.assertEqual(chips, [])
        self.assertEqual(len(lines["W1"]), 1)
        self.assertIn("W1", lines["W1"][0])

    def test_black_chip_fails(self):
        img = make(390, 693, [(12, 52, 96, 38, (0, 0, 0))])
        chips, lines = chips_of(img)
        self.assertEqual(chips, [])
        self.assertTrue(lines["W1"] or lines["W8"])

    def test_missing_chip_fails(self):
        img = make(390, 693, [(12, 300, 366, 50, RED)])  # a CTA band lower down, no chip
        chips, lines = chips_of(img)
        self.assertEqual(chips, [])
        self.assertEqual(len(lines["W1"]), 1)

    def test_blank_slice_fails(self):
        chips, lines = chips_of(make(390, 693, []))
        self.assertEqual(chips, [])
        self.assertTrue(lines["W1"])

    def test_too_tall_block_still_fails_at_390(self):
        # 60 px of 390 is 15 percent: no chip, above the narrow limit
        chips, _ = chips_of(make(390, 693, [(12, 40, 100, 60, RED)]))
        self.assertEqual(chips, [])

    def test_hollow_outline_still_fails_at_390(self):
        img = Image.new("RGB", (390, 693), (255, 255, 255))
        d = ImageDraw.Draw(img)
        d.rectangle([12, 50, 112, 88], outline=RED, width=3)
        chips, lines = chips_of(img)
        self.assertEqual(chips, [])
        self.assertTrue(lines["W1"])

    def test_chip_outside_the_top_left_zone_still_fails_at_390(self):
        chips, _ = chips_of(make(390, 693, [(12, 400, 96, 38, RED)]))
        self.assertEqual(chips, [])
        chips, _ = chips_of(make(390, 693, [(250, 40, 96, 38, RED)]))
        self.assertEqual(chips, [])

    def test_extreme_aspect_still_fails_at_390(self):
        chips, _ = chips_of(make(390, 693, [(12, 52, 200, 20, RED)]))  # aspect 10
        self.assertEqual(chips, [])


class DesktopUnchanged(unittest.TestCase):
    def test_constants_and_curve_at_and_above_the_working_width(self):
        self.assertEqual(V.CHIP_HEIGHT_FRAC, (0.012, 0.08))
        self.assertEqual(V.chip_height_frac_max(720), 0.08)
        self.assertEqual(V.chip_height_frac_max(1440), 0.08)
        self.assertEqual(V.chip_dilation(720), 7)
        self.assertEqual(V.chip_dilation(1440), 7)

    def test_narrow_curve_is_monotone_odd_and_bounded(self):
        last = 0.0
        for w in (720, 700, 600, 500, 390, 300):
            frac = V.chip_height_frac_max(w)
            self.assertGreaterEqual(frac, last)
            self.assertLessEqual(frac, V.CHIP_HEIGHT_MAX_NARROW)
            last = frac
            size = V.chip_dilation(w)
            self.assertEqual(size % 2, 1)
            self.assertTrue(3 <= size <= 7)
        self.assertEqual(V.chip_height_frac_max(390), V.CHIP_HEIGHT_MAX_NARROW)

    def test_desktop_1440_slice_chip_rule_is_the_old_rule(self):
        # measured at 720: a 200x70 chip is 100x35 (4.9 percent): passes
        chips, lines = chips_of(make(1440, 1200, [(50, 90, 200, 70, RED)]))
        self.assertEqual(lines["W1"], [])
        # a 200x130 block is 100x65 (9 percent at 720): fails exactly as before
        chips, lines = chips_of(make(1440, 1200, [(50, 90, 200, 130, RED)]))
        self.assertEqual(chips, [])
        self.assertTrue(lines["W1"])

    def test_a_height_a_phone_slice_accepts_is_still_rejected_on_a_desktop_slice(self):
        # 10 percent of the width tall: accepted at 390, rejected at 1440 (measured at 720)
        chips_phone, _ = chips_of(make(390, 693, [(12, 50, 104, 39, RED)]))
        chips_desk, _ = chips_of(make(1440, 1200, [(30, 50, 380, 144, RED)]))
        self.assertTrue(chips_phone)
        self.assertEqual(chips_desk, [])


if __name__ == "__main__":
    unittest.main()
