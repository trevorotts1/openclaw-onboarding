#!/usr/bin/env python3
"""PKG-06-U3 — DEL-15 anchors: sixty seconds is eight pictures, two
minutes is twenty-four.

The two numbers are pinned by the owner order (2026-10-09 13:35 item 3;
13:40 addenda). They are asserted against the shipped calculator, never
typed into a table of their own, so a reword on either side fails here.

Run: python3 tests/test_storyboard_shot_count/test_count_anchors.py
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

# The calculator ships as a script; load it BY PATH under a private name so
# it can never shadow (or be shadowed by) the namespace package off CORE.
_spec = importlib.util.spec_from_file_location("pkg06u3_calc_anchors", CALC_PATH)
cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cc)


class SixtySecondsIsEight(unittest.TestCase):
    def test_sixty_seconds_is_eight_pictures(self):
        self.assertEqual(cc.shot_count(60), 8)

    def test_half_a_minute_scales_from_the_eight_at_sixty(self):
        self.assertEqual(cc.shot_count(30), 4)

    def test_one_second_past_sixty_takes_a_ninth_picture(self):
        self.assertEqual(cc.shot_count(61), 9)


class TwoMinutesIsTwentyFour(unittest.TestCase):
    def test_two_minutes_is_twenty_four_pictures(self):
        self.assertEqual(cc.shot_count(120), 24)
        self.assertEqual(cc.shot_count(2 * 60), 24)

    def test_one_second_past_two_minutes_adds_one_picture(self):
        self.assertEqual(cc.shot_count(121), 25)

    def test_the_anchor_sits_below_the_configured_cap(self):
        self.assertLess(cc.shot_count(120), cc.storyboard_cap())


class CountNeverGoesBackwards(unittest.TestCase):
    def test_the_count_is_monotone_over_every_offered_length(self):
        # Every offered length plus every second in between: a longer ad
        # never draws fewer storyboard pictures than a shorter one.
        previous = 0
        for seconds in range(1, 601):
            pictures = cc.shot_count(seconds)
            self.assertGreaterEqual(pictures, previous, seconds)
            previous = pictures

    def test_bad_lengths_fail_closed(self):
        for bad in (0, -1, True, "60", None):
            with self.assertRaises(ValueError, msg=repr(bad)):
                cc.shot_count(bad)


if __name__ == "__main__":
    unittest.main(verbosity=2)
