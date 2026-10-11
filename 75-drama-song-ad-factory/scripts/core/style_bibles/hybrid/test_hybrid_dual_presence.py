#!/usr/bin/env python3
"""Plan 3.17 dual-presence tests (APPROVED 2026-10-11): validator, shot list,
assembly, and the 4 fps frame gate with BOTH negative controls.

Stdlib only, offline, $0: no clip is ever read and no provider is ever called.
Frame statistics are the measured half-frame cues the gate consumes, so the
whole gate is provable on synthetic frames before it is pointed at any real
video.

  validator   - a compliant storyboard passes; each named rule is REFUSED by
                name, one mutation per rule (never a bare boolean);
  shot list   - the single DUAL-01 entry carries BASE_REAL + OVERLAY_SKETCH,
                and refuses to emit when the validator refuses;
  assembly    - 100% opacity alpha overlay, dissolve in <= 8 frames, hard cut
                out on 1 frame, cross-blend refused;
  gate        - the KNOWN-GOOD control first: a synthetic frame carrying one
                line-art half and one photoreal half PASSES the gate, and a
                synthetic single-style frame FAILS it. Then the positive
                control, and BOTH negative controls (the same shot with the
                twin removed, and the single-style "some time later" phone
                shot at 112.0-114.3 s) must each return ZERO passing frames.

Run: python3 scripts/core/style_bibles/hybrid/test_hybrid_dual_presence.py
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.normpath(os.path.join(HERE, "..", ".."))
for _p in (CORE, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import hybrid_bible as HB  # noqa: E402

# ---- synthetic half-frame cues (the gate's own inputs) ---------------------
SKETCH_HALF = {"saturation": 0.02, "edge_density": 0.35}   # line art
REAL_HALF = {"saturation": 0.40, "edge_density": 0.08}     # photoreal colour
DURATION_S = 4.5                                            # 4.5 * 4 = 18


def frame(left, right, t=0.0):
    return {"t": t, "left": left, "right": right}


def good_frames(n, start=0.0, step=0.25):
    return [frame(SKETCH_HALF, REAL_HALF, start + i * step) for i in range(n)]


def twin_removed_frames(n):
    """Control 1: the SAME shot with the twin removed -- both halves line art."""
    return [frame(SKETCH_HALF, SKETCH_HALF, i * 0.25) for i in range(n)]


def phone_frames(n):
    """Control 2: the single-style 'some time later' phone shot -- all photoreal."""
    lo, hi = HB.DUAL_PRESENCE_PHONE_CONTROL_SECONDS
    assert (lo, hi) == (112.0, 114.3), (lo, hi)
    return [frame(REAL_HALF, REAL_HALF, lo + i * 0.25) for i in range(n)]


def entry(**over):
    e = {
        "shot_id": "S030",
        "start_pct": 58.0,
        "duration_s": DURATION_S,
        "composition": HB.DUAL_PRESENCE_COMPOSITION,
        "sketch_character": "INNER CHANEL",
        "eyeline": HB.DUAL_PRESENCE_EYELINE,
        "ad_card": True,
        "lead_side": "LEFT",
        "twin_side": "RIGHT",
        "real_width_pct": 60.0,
        "twin_width_pct": 40.0,
        "head_height_delta_pct": 6.0,
        "figures": 2,
    }
    e.update(over)
    return e


def storyboard(**over):
    return {HB.DUAL_PRESENCE_FIELD: entry(**over)}


class Validator(unittest.TestCase):
    def test_compliant_storyboard_passes(self):
        self.assertEqual(HB.dual_presence_errors(storyboard()), [])
        self.assertEqual(HB.assert_dual_presence(storyboard()), storyboard())

    def test_each_rule_is_refused_by_name(self):
        cases = [
            ("DUAL_PRESENCE_FIELD_MISSING", {}),
            ("DUAL_PRESENCE_FIELD_INCOMPLETE",
             {HB.DUAL_PRESENCE_FIELD: {k: v for k, v in entry().items()
                                       if k != "shot_id"}}),
            ("DUAL_PRESENCE_MISSING", {HB.DUAL_PRESENCE_FIELD: []}),
            ("DUAL_PRESENCE_COUNT",
             {HB.DUAL_PRESENCE_FIELD: [entry(), entry(shot_id="S031")]}),
            ("DUAL_PRESENCE_START_PCT", storyboard(start_pct=30.0)),
            ("DUAL_PRESENCE_START_PCT", storyboard(start_pct=90.0)),
            ("DUAL_PRESENCE_DURATION", storyboard(duration_s=2.0)),
            ("DUAL_PRESENCE_DURATION", storyboard(duration_s=7.5)),
            ("DUAL_PRESENCE_COMPOSITION", storyboard(composition="SPLIT_SCREEN")),
            ("DUAL_PRESENCE_TWIN_SIDE", storyboard(twin_side="LEFT")),
            ("DUAL_PRESENCE_TWIN_SIDE", storyboard(twin_side=None)),
            ("DUAL_PRESENCE_REAL_WIDTH", storyboard(real_width_pct=50.0)),
            ("DUAL_PRESENCE_TWIN_WIDTH", storyboard(twin_width_pct=50.0)),
            ("DUAL_PRESENCE_HEAD_HEIGHT", storyboard(head_height_delta_pct=22.0)),
            ("DUAL_PRESENCE_FIGURES", storyboard(figures=3)),
            ("DUAL_PRESENCE_FIGURES", storyboard(figures=1)),
            ("DUAL_PRESENCE_EYELINE", storyboard(eyeline="REAL-TO-SKETCH")),
            ("DUAL_PRESENCE_EYELINE", storyboard(mirrored=True)),
            ("DUAL_PRESENCE_AD_CARD", storyboard(ad_card=False)),
        ]
        for rule, sb in cases:
            with self.subTest(rule=rule, sb=sb):
                self.assertEqual(HB.dual_presence_errors(sb), [rule])
                with self.assertRaises(HB.HybridError) as ctx:
                    HB.assert_dual_presence(sb)
                self.assertEqual(ctx.exception.code, rule)

    def test_spend_before_a_complete_field_is_refused(self):
        errs = HB.dual_presence_errors({}, spend_started=True)
        self.assertEqual(errs[0], "DUAL_PRESENCE_SPEND_BEFORE_FIELD")
        with self.assertRaises(HB.HybridError) as ctx:
            HB.assert_dual_presence({}, spend_started=True)
        self.assertEqual(ctx.exception.code,
                         "DUAL_PRESENCE_SPEND_BEFORE_FIELD")
        # spend after a complete field is fine
        self.assertEqual(
            HB.dual_presence_errors(storyboard(), spend_started=True), [])

    def test_every_rule_name_is_reachable(self):
        named = {"DUAL_PRESENCE_FIELD_MISSING", "DUAL_PRESENCE_FIELD_INCOMPLETE",
                 "DUAL_PRESENCE_MISSING", "DUAL_PRESENCE_COUNT",
                 "DUAL_PRESENCE_START_PCT", "DUAL_PRESENCE_DURATION",
                 "DUAL_PRESENCE_COMPOSITION", "DUAL_PRESENCE_TWIN_SIDE",
                 "DUAL_PRESENCE_REAL_WIDTH", "DUAL_PRESENCE_TWIN_WIDTH",
                 "DUAL_PRESENCE_HEAD_HEIGHT", "DUAL_PRESENCE_FIGURES",
                 "DUAL_PRESENCE_EYELINE", "DUAL_PRESENCE_AD_CARD",
                 "DUAL_PRESENCE_SPEND_BEFORE_FIELD"}
        self.assertEqual(set(HB.DUAL_PRESENCE_RULES), named)


class ShotList(unittest.TestCase):
    def test_single_entry_carries_both_assets(self):
        sl = HB.dual_presence_shot_list(storyboard())
        self.assertEqual(len(sl), 1)
        self.assertEqual(sl[0]["shot_id"], "DUAL-01")
        self.assertEqual(sl[0]["composition"], "TWO_SHOT_SIDE_BY_SIDE")
        assets = {a["asset"]: a["kind"] for a in sl[0]["assets"]}
        self.assertEqual(assets, {"BASE_REAL": "clip",
                                  "OVERLAY_SKETCH": "alpha_png"})

    def test_refuses_to_emit_when_validator_refuses(self):
        with self.assertRaises(HB.HybridError) as ctx:
            HB.dual_presence_shot_list(storyboard(start_pct=90.0))
        self.assertEqual(ctx.exception.code, "DUAL_PRESENCE_START_PCT")
        with self.assertRaises(HB.HybridError) as ctx:
            HB.dual_presence_shot_list({}, spend_started=True)
        self.assertEqual(ctx.exception.code,
                         "DUAL_PRESENCE_SPEND_BEFORE_FIELD")


class Assembly(unittest.TestCase):
    def test_approved_assembly(self):
        plan = HB.dual_presence_assembly(entry())
        self.assertEqual(plan["overlay_opacity_pct"], 100)
        self.assertEqual(plan["dissolve_in_max_frames"], 8)
        self.assertEqual(plan["cut_out_frames"], 1)
        self.assertEqual(HB.assembly_errors(plan), [])
        self.assertIn("cross-blend REFUSED", plan["plan"])

    def test_cross_blend_is_refused(self):
        with self.assertRaises(HB.HybridError) as ctx:
            HB.dual_presence_assembly(entry(), cross_blend=True)
        self.assertEqual(ctx.exception.code,
                         "DUAL_PRESENCE_ASSEMBLY_CROSS_BLEND")
        self.assertEqual(HB.assembly_errors(
            {"cross_blend": True, "overlay_opacity_pct": 100}),
            ["DUAL_PRESENCE_ASSEMBLY_CROSS_BLEND"])

    def test_opacity_dissolve_and_cut_out_are_enforced(self):
        self.assertEqual(HB.assembly_errors(
            {"overlay_opacity_pct": 70}), ["DUAL_PRESENCE_ASSEMBLY_OPACITY"])
        self.assertEqual(HB.assembly_errors(
            {"overlay_opacity_pct": 100, "dissolve_in_frames": 9}),
            ["DUAL_PRESENCE_ASSEMBLY_DISSOLVE_IN"])
        self.assertEqual(HB.assembly_errors(
            {"overlay_opacity_pct": 100, "cut_out_frames": 3}),
            ["DUAL_PRESENCE_ASSEMBLY_CUT_OUT"])


class GateKnownGood(unittest.TestCase):
    """The gate's OWN known-good control: prove it discriminates BEFORE it is
    pointed at any real video. A gate that returns zero passing frames on
    everything must not read as a pass."""

    def test_synthetic_frame_pair_passes_and_single_style_frame_fails(self):
        self.assertTrue(HB.frame_passes(frame(SKETCH_HALF, REAL_HALF)))
        self.assertTrue(HB.frame_passes(frame(REAL_HALF, SKETCH_HALF)))
        self.assertFalse(HB.frame_passes(frame(SKETCH_HALF, SKETCH_HALF)))
        self.assertFalse(HB.frame_passes(frame(REAL_HALF, REAL_HALF)))
        self.assertFalse(HB.frame_passes({}))
        self.assertEqual(HB.classify_half(SKETCH_HALF), HB.HALF_SKETCH)
        self.assertEqual(HB.classify_half(REAL_HALF), HB.HALF_REAL)
        self.assertEqual(HB.classify_half(None), HB.HALF_UNKNOWN)


class Gate(unittest.TestCase):
    def test_required_frames_is_duration_times_fps_with_a_floor(self):
        self.assertEqual(HB.required_passing_frames(DURATION_S), 18)
        self.assertEqual(HB.required_passing_frames(3.0), 12)
        self.assertEqual(HB.required_passing_frames(1.0), 12)   # floor
        self.assertIsNone(HB.required_passing_frames(0))

    def test_positive_control_passes(self):
        res = HB.qc_dual_presence_window(good_frames(18), DURATION_S)
        self.assertEqual(res["required"], 18)
        self.assertEqual(res["consecutive"], 18)
        self.assertTrue(res["passing"])

    def test_one_short_run_does_not_pass(self):
        res = HB.qc_dual_presence_window(good_frames(17), DURATION_S)
        self.assertEqual(res["consecutive"], 17)
        self.assertFalse(res["passing"])

    def test_both_negative_controls_return_zero_passing_frames(self):
        res = HB.qc_dual_presence(good_frames(18), DURATION_S,
                                  twin_removed_frames=twin_removed_frames(18),
                                  phone_frames=phone_frames(12))
        self.assertTrue(res["positive"]["passing"])
        self.assertEqual(res["negative_twin_removed"]["any_passing"], 0)
        self.assertTrue(res["negative_twin_removed"]["control_passing"])
        self.assertEqual(res["negative_phone"]["any_passing"], 0)
        self.assertTrue(res["negative_phone"]["control_passing"])
        self.assertTrue(res["passing"])

    def test_positive_that_is_really_the_twin_removed_clip_fails(self):
        res = HB.qc_dual_presence(twin_removed_frames(18), DURATION_S,
                                  twin_removed_frames=twin_removed_frames(18),
                                  phone_frames=phone_frames(12))
        self.assertFalse(res["positive"]["passing"])
        self.assertFalse(res["passing"])

    def test_a_negative_control_with_one_passing_frame_fails_the_gate(self):
        leak = [frame(SKETCH_HALF, SKETCH_HALF)] * 17
        leak.append(frame(SKETCH_HALF, REAL_HALF))
        res = HB.qc_dual_presence(good_frames(18), DURATION_S,
                                  twin_removed_frames=leak,
                                  phone_frames=phone_frames(12))
        self.assertEqual(res["negative_twin_removed"]["any_passing"], 1)
        self.assertFalse(res["negative_twin_removed"]["control_passing"])
        self.assertFalse(res["passing"])

    def test_a_missing_control_is_not_a_pass(self):
        res = HB.qc_dual_presence(good_frames(18), DURATION_S,
                                  phone_frames=phone_frames(12))
        self.assertIsNone(res["negative_twin_removed"])
        self.assertFalse(res["passing"])
        res = HB.qc_dual_presence(good_frames(18), DURATION_S,
                                  twin_removed_frames=twin_removed_frames(18))
        self.assertIsNone(res["negative_phone"])
        self.assertFalse(res["passing"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
