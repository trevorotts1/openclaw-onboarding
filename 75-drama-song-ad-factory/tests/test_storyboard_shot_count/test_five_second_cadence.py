#!/usr/bin/env python3
"""PKG-06-U3 — DEL-15: past two minutes the cadence continues at one
picture per five seconds of runtime.

The owner order pins the two anchors (8 at 60 s, 24 at 2 min) and then
"about one more picture per five seconds". This walks the whole unclamped
range in five-second steps and requires exactly +1 per step, so a cadence
of four or six seconds (or a second slope between the anchors) fails.

Run: python3 tests/test_storyboard_shot_count/test_five_second_cadence.py
(also collected by pytest). stdlib only, no network.
"""
from __future__ import annotations

import importlib.util
import os
import sys
import unittest

HERE = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.realpath(os.path.join(HERE, "..", ".."))
CORE = os.path.join(SKILL, "scripts", "core")
if CORE not in sys.path:
    sys.path.insert(0, CORE)
CALC_PATH = os.path.join(CORE, "catalog_calculator", "catalog_calculator.py")

_spec = importlib.util.spec_from_file_location("pkg06u3_calc_cadence", CALC_PATH)
cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cc)

# First fully unclamped five-second step past the 2-minute anchor, and the
# last one whose next step still lands on or below the 120 cap.
CADENCE_FIRST = 121
CADENCE_LAST = 595


class CadencePastTwoMinutes(unittest.TestCase):
    def test_every_five_seconds_adds_exactly_one_picture(self):
        for seconds in range(CADENCE_FIRST, CADENCE_LAST + 1):
            self.assertEqual(
                cc.shot_count(seconds + 5), cc.shot_count(seconds) + 1,
                "five seconds after %d must add one picture" % seconds)

    def test_the_documented_cadence_rows(self):
        # price-menu.md / choice-card-spec 3.12 table: 3 min -> 36, 5 min -> 60.
        self.assertEqual(cc.shot_count(180), 36)
        self.assertEqual(cc.shot_count(300), 60)

    def test_sixty_six_hundred_lands_exactly_on_the_cap_row(self):
        # 600 s / 5 = 120: the doc's "10 minutes | 120 (at the cap)" row is
        # the formula and the cap agreeing, not the cap alone.
        self.assertEqual(cc.shot_count(600), 120)

    def test_five_seconds_is_the_step_not_four_or_six(self):
        self.assertEqual(cc.shot_count(125), 25)
        self.assertEqual(cc.shot_count(130), 26)
        self.assertEqual(cc.shot_count(305), 61)
        # six-second steps would give ceil(306/5)=62 vs ceil(300/5)=60: +2;
        # four-second steps would give +1 every four seconds. Neither passes
        # the walk above; these three rows pin the absolute values.


class BridgeAcrossTheAnchors(unittest.TestCase):
    def test_between_the_anchors_the_count_only_climbs(self):
        previous = cc.shot_count(60)
        for seconds in range(61, 121):
            pictures = cc.shot_count(seconds)
            self.assertGreaterEqual(pictures, previous, seconds)
            previous = pictures
        self.assertEqual(previous, 24)

    def test_the_count_crosses_the_anchor_without_a_gap_backwards(self):
        self.assertEqual(cc.shot_count(120), 24)
        self.assertEqual(cc.shot_count(121), 25)


if __name__ == "__main__":
    unittest.main(verbosity=2)
