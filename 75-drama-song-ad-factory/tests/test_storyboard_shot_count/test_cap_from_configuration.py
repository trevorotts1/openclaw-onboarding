#!/usr/bin/env python3
"""PKG-06-U3 — DEL-15: the 120-picture cap comes from configuration and
actually clamps.

The owner addenda (2026-10-09 13:40) fixed the cap at 120 and required it
to live in configuration, never hard-coded in the calculator. These tests
prove all three: the file holds 120, the calculator reads the file, and
pointing the calculator at a different file moves the clamp with it.

Run: python3 tests/test_storyboard_shot_count/test_cap_from_configuration.py
(also collected by pytest). stdlib only, no network.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.realpath(os.path.join(HERE, "..", ".."))
CORE = os.path.join(SKILL, "scripts", "core")
if CORE not in sys.path:
    sys.path.insert(0, CORE)
CALC_PATH = os.path.join(CORE, "catalog_calculator", "catalog_calculator.py")

_spec = importlib.util.spec_from_file_location("pkg06u3_calc_cap", CALC_PATH)
cc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cc)

CONFIGURED_CAP = 120


class ConfigHoldsTheCap(unittest.TestCase):
    def test_the_config_file_ships_beside_the_calculator(self):
        self.assertTrue(os.path.isfile(cc.STORYBOARD_CONFIG),
                        cc.STORYBOARD_CONFIG)
        self.assertEqual(os.path.dirname(os.path.realpath(cc.STORYBOARD_CONFIG)),
                         os.path.dirname(os.path.realpath(CALC_PATH)))

    def test_the_config_file_holds_120_as_an_integer(self):
        with open(cc.STORYBOARD_CONFIG, encoding="utf-8") as f:
            data = json.load(f)
        cap = data["storyboard_picture_cap"]
        self.assertIs(type(cap), int)   # True would be a bool, not a cap
        self.assertEqual(cap, CONFIGURED_CAP)

    def test_storyboard_cap_reads_that_value(self):
        self.assertEqual(cc.storyboard_cap(), CONFIGURED_CAP)


class CapActuallyClamps(unittest.TestCase):
    def test_over_cap_lengths_come_back_at_the_cap(self):
        # 601 s is 121 pictures on the cadence, 1200 s is 240: both clamp.
        self.assertEqual(cc.shot_count(601), CONFIGURED_CAP)
        self.assertEqual(cc.shot_count(1200), CONFIGURED_CAP)

    def test_at_cap_the_formula_and_the_cap_agree(self):
        self.assertEqual(cc.shot_count(600), CONFIGURED_CAP)

    def test_under_cap_the_cap_never_touches_the_count(self):
        self.assertEqual(cc.shot_count(60), 8)
        self.assertEqual(cc.shot_count(120), 24)
        self.assertEqual(cc.shot_count(180), 36)


class CapIsDataNotCode(unittest.TestCase):
    def test_a_different_config_file_moves_the_clamp(self):
        # Repoint STORYBOARD_CONFIG at a file holding 50: the clamp must
        # follow the file. If 120 were hard-coded, this stays 120.
        workdir = tempfile.mkdtemp(prefix="TrevelynsMini2-PKG-06-U3-cap-")
        self.addCleanup(shutil.rmtree, workdir, True)
        other = os.path.join(workdir, "storyboard-config.json")
        with open(other, "w", encoding="utf-8") as f:
            json.dump({"storyboard_picture_cap": 50}, f)
        original = cc.STORYBOARD_CONFIG
        self.addCleanup(setattr, cc, "STORYBOARD_CONFIG", original)
        cc.STORYBOARD_CONFIG = other
        self.assertEqual(cc.storyboard_cap(), 50)
        self.assertEqual(cc.shot_count(1200), 50)

    def test_restored_config_brings_the_120_cap_back(self):
        # Runs after the repoint above (alphabetical class order): the
        # default path still ends on the shipped file.
        self.assertEqual(cc.storyboard_cap(), CONFIGURED_CAP)
        self.assertEqual(cc.shot_count(1200), CONFIGURED_CAP)

    def test_missing_config_fails_closed(self):
        original = cc.STORYBOARD_CONFIG
        self.addCleanup(setattr, cc, "STORYBOARD_CONFIG", original)
        cc.STORYBOARD_CONFIG = os.path.join(tempfile.gettempdir(),
                                            "no-such-storyboard-config.json")
        with self.assertRaises(ValueError) as ctx:
            cc.shot_count(60)
        self.assertIn("STORYBOARD_CAP_UNAVAILABLE", str(ctx.exception))

    def test_malformed_caps_fail_closed(self):
        workdir = tempfile.mkdtemp(prefix="TrevelynsMini2-PKG-06-U3-cap-")
        self.addCleanup(shutil.rmtree, workdir, True)
        original = cc.STORYBOARD_CONFIG
        self.addCleanup(setattr, cc, "STORYBOARD_CONFIG", original)
        for cap in ("120", 0, -1, True, 1.5, None):
            bad = os.path.join(workdir, "bad-%s.json" % type(cap).__name__)
            with open(bad, "w", encoding="utf-8") as f:
                json.dump({"storyboard_picture_cap": cap}, f)
            cc.STORYBOARD_CONFIG = bad
            with self.assertRaises(ValueError, msg=repr(cap)):
                cc.shot_count(60)

    def test_explicit_cap_override_is_honoured_and_validated(self):
        self.assertEqual(cc.shot_count(1200, cap=10), 10)
        for bad in (0, -5, True, "120", 1.5):
            with self.assertRaises(ValueError, msg=repr(bad)):
                cc.shot_count(60, cap=bad)


if __name__ == "__main__":
    unittest.main(verbosity=2)
