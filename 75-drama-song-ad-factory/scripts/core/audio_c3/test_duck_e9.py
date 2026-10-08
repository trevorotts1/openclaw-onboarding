#!/usr/bin/env python3
"""W-E-U9 suite: E9 ducking envelope — a small dip under speech only.

Proves EXACTLY the manual's done-when (02-FIX-AND-IMPROVE-MANUAL E9, High)
plus the owner ADDENDUM 2 wording on unit W-E-U9:

  * a spoken line's bed level lands 6-8 dB below the adjacent sung section
    for dip_db in the 6-8 range (7 shows as exactly 7 dB, per the envelope);
  * a caller passing dip_db=10 is CLAMPED to 8 — never more than 8 dB;
  * attack/release stay short (defaults 50 ms / 150 ms; an oversized one is
    refused, not shipped);
  * the measured level math the checks use is pure (db_to_lin / lin_to_db /
    duck_lin / envelope_gain_at / envelope_level_delta_db) — no real audio
    to run;
  * the envelope folds into the bed mixer's gain_points (instrumental
    carries the dip, song stays 1.0 in sung spans) and the E8 bed-mix plan
    still builds on the same branch (base carry, byte-identical U8 files).

Exit 0 = all pass; unittest style, python3 test_duck_e9.py or -m pytest.
"""
from __future__ import annotations

import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)

# Judge the SOURCE on disk, never a stale __pycache__.
_CACHE = os.path.join(HERE, "__pycache__")
if os.path.isdir(_CACHE):
    for _name in os.listdir(_CACHE):
        if _name.endswith(".pyc"):
            try:
                os.remove(os.path.join(_CACHE, _name))
            except OSError:
                pass

sys.path.insert(0, HERE)
import bed_mixer as M  # noqa: E402  module under test

DURATION = 30.0
SPOKEN = [
    {"line_id": "L1", "start": 6.0, "end": 11.0, "text": "call now"},
    {"line_id": "L2", "start": 15.0, "end": 19.5, "text": "don't wait"},
]
REGIONS = [{"start": 0.0, "end": DURATION}]     # one continuous sung region
SONG = {"duration_s": DURATION, "tempo_bpm": 120.0, "song_id": "s"}
INSTR = {"duration_s": DURATION, "song_id": "s"}

failures = []


def check(name, cond, detail=""):
    if cond:
        print("ok:", name)
    else:
        failures.append(name)
        print("FAIL:", name, "--", detail)


class LevelMathTests(unittest.TestCase):
    """The pure level math the checks measure with (no real audio)."""

    def test_db_lin_roundtrip(self):
        for db in (-8.0, -7.0, -6.0, 0.0):
            self.assertAlmostEqual(M.lin_to_db(M.db_to_lin(db)), db, places=9)

    def test_duck_lin_is_dip_down(self):
        self.assertAlmostEqual(M.duck_lin(7.0), 10 ** (-7.0 / 20.0), places=12)
        self.assertAlmostEqual(M.lin_to_db(M.duck_lin(6.0)), -6.0, places=9)

    def test_duck_lin_never_dips_more_than_8(self):
        self.assertAlmostEqual(M.duck_lin(10.0), 10 ** (-8.0 / 20.0), places=12)
        self.assertGreater(M.duck_lin(10.0), 10 ** (-8.5 / 20.0))

    def test_zero_gain_maps_to_minus_inf(self):
        self.assertEqual(M.lin_to_db(0.0), float("-inf"))


class ConstantsTests(unittest.TestCase):
    def test_short_attack_release_defaults(self):
        self.assertEqual(M.ATTACK_S, 0.050)
        self.assertEqual(M.RELEASE_S, 0.150)
        self.assertLess(M.ATTACK_S, 0.1)
        self.assertLess(M.RELEASE_S, 0.2)

    def test_band_constants(self):
        self.assertEqual(M.DEFAULT_DIP_DB, 7.0)
        self.assertEqual(M.MAX_DIP_DB, 8.0)
        self.assertEqual(M.DEFAULT_DIP_DB, M.DEFAULT_DUCK_DB)
        self.assertEqual(M.MAX_DIP_DB, M.DUCK_MAX_DB)


class EnvelopeTests(unittest.TestCase):
    def envelope(self, dip=7.0, **kw):
        return M.duck_envelope(SPOKEN, REGIONS, duration_s=DURATION,
                               dip_db=dip, **kw)

    def test_plateau_6_8_below_adjacent_sung(self):
        for dip in (6.0, 7.0, 8.0):
            env = self.envelope(dip=dip)
            for t in (8.0, 17.0):                       # plateau of each line
                delta = M.envelope_level_delta_db(env, t)
                self.assertGreaterEqual(delta, dip - 1e-9,
                                        "t=%s dip=%s" % (t, dip))
                self.assertLessEqual(delta, dip + 1e-9,
                                     "t=%s dip=%s" % (t, dip))

    def test_exact_7_at_default(self):
        env = self.envelope()
        self.assertAlmostEqual(M.envelope_level_delta_db(env, 8.0), 7.0,
                               places=9)

    def test_clamp_10_to_8(self):
        env = self.envelope(dip=10.0)
        self.assertEqual(env["dip_db"], 8.0)
        delta = M.envelope_level_delta_db(env, 8.0)
        self.assertAlmostEqual(delta, 8.0, places=9)
        self.assertLessEqual(delta, 8.0 + 1e-9)

    def test_never_more_than_8_anywhere(self):
        env = self.envelope(dip=10.0)
        worst = min(M.envelope_level_delta_db(env, t)
                    for t in [x * 0.05 for x in range(601)])
        self.assertLessEqual(worst, 8.0 + 1e-9, "worst=%r" % worst)

    def test_sung_spans_untouched(self):
        env = self.envelope()
        for t in (2.0, 4.0, 12.5, 21.0, 27.0):
            self.assertAlmostEqual(M.envelope_gain_at(env, t), 1.0, places=12)

    def test_attack_release_stay_short(self):
        env = self.envelope()
        self.assertEqual(env["attack_s"], 0.050)
        self.assertEqual(env["release_s"], 0.150)
        for ln in env["lines"]:
            knee_in, knee_out = ln["knee_in"], ln["knee_out"]
            self.assertAlmostEqual(knee_in[0], ln["start"] - 0.050, places=9)
            self.assertAlmostEqual(knee_out[1], 1.0, places=9)

    def test_oversized_attack_refused(self):
        with self.assertRaisesRegex(M.BedError, "BAD_ENVELOPE_RATE"):
            self.envelope(attack_s=0.2)

    def test_oversized_release_refused(self):
        with self.assertRaisesRegex(M.BedError, "BAD_ENVELOPE_RATE"):
            self.envelope(release_s=0.5)

    def test_sub_band_dip_refused(self):
        with self.assertRaisesRegex(M.BedError, "DIP_RANGE"):
            self.envelope(dip=5.0)

    def test_dip_inside_spans_only(self):
        env = self.envelope()
        bounds = M.line_bounds(env)
        self.assertEqual(len(bounds), 2)
        for (lo, hi), src in zip(bounds, ((6.0, 11.0), (15.0, 19.5))):
            self.assertGreaterEqual(lo, src[0] - M.ATTACK_S - 1e-9)
            self.assertLessEqual(hi, src[1] + 1e-9)

    def test_breakpoints_monotone(self):
        env = self.envelope()
        ts = [t for t, _g in env["breakpoints"]]
        for a, b in zip(ts, ts[1:]):
            self.assertLess(a, b, "%r vs %r" % (a, b))


class FoldTests(unittest.TestCase):
    def test_fold_into_gain_points_shape(self):
        env = M.duck_envelope(SPOKEN, REGIONS, duration_s=DURATION)
        pts = M.duck_envelope_to_gain_points(env, DURATION)
        self.assertTrue(pts)
        at = lambda t: M._gain_at([(a, c) for a, _b, c in pts], t)
        self.assertAlmostEqual(at(8.0), 10 ** (-7.0 / 20.0), places=9)
        self.assertAlmostEqual(at(3.0), 1.0, places=9)

    def test_e8_plan_still_builds_on_this_branch(self):
        plan = M.build_mix(SONG, INSTR, SPOKEN)
        self.assertEqual(plan["schema_version"], M.SCHEMA_VERSION)
        self.assertEqual(plan["duck_db"], 7.0)
        gp = plan["gain_points"]
        def total_at(t):
            s = M._gain_at([(p[0], p[1]) for p in gp], t)
            i = M._gain_at([(p[0], p[2]) for p in gp], t)
            return s, i
        s_mid, i_mid = total_at(8.0)
        self.assertLess(s_mid, 1e-6)
        self.assertAlmostEqual(i_mid, 10 ** (-7.0 / 20.0), places=9)
        worst = min(s + i for probe in [x * 0.05 for x in range(601)]
                    for s, i in [total_at(round(probe, 3))])
        self.assertGreaterEqual(worst, 10 ** (-8.0 / 20.0) - 1e-6,
                                "worst=%r" % worst)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromModule(
        sys.modules["__main__"])
    res = unittest.TextTestRunner(verbosity=2).run(suite)
    if failures or not res.wasSuccessful():
        sys.stderr.write("FAILED: %r / unittest failed=%r errors=%r\n"
                         % (failures, len(res.failures), len(res.errors)))
        sys.exit(1)
    print("all W-E-U9 (E9) checks passed")