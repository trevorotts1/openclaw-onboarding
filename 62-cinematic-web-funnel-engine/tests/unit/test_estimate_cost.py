#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_estimate_cost.py — offline unit tests for scripts/estimate_cost.py
(Skill 62, U7).

Covers:
  - quantity_for_unit() conversion rules for every price.unit the shipped
    model-registry.json actually uses, plus its fail-closed rejection of an
    unrecognized unit.
  - estimate_scene() against the REAL shipped registry: a verified model
    (kie-veo3-fast) resolves a real dollar figure; an unverified/unpriced
    model (kie-bytedance-seedance-1.5-pro) resolves=False rather than
    crashing or silently pricing at $0; a scene with
    expected_generation_count=0 short-circuits to a free, resolved forecast;
    an unknown generation_model fails closed with resolved=False.
  - estimate_scene_plan() aggregation: complete/all_verified/
    unresolved_scene_ids/unverified_scene_ids all reflect the real per-scene
    outcomes, and total_estimated_usd sums only the resolvable scenes.
  - every dollar figure traces back to the SAME registry_snapshot_id a
    directly-constructed ModelRegistry produces (never hardcoded).

stdlib unittest only.
Run: python3 -m unittest discover -s tests/unit -v
     (from the 62-cinematic-web-funnel-engine/ directory)
"""

from __future__ import annotations

import datetime
import sys
import unittest
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _TESTS_DIR.parent.parent
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))
if str(_SKILL_DIR / "scripts") not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR / "scripts"))

import estimate_cost as ec  # noqa: E402
from providers import base as providers_base  # noqa: E402


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _scene(**overrides) -> dict:
    scene = {
        "scene_id": "scene-01",
        "page_section": "hero",
        "narrative_purpose": "establish the world",
        "conversion_purpose": "hook attention",
        "visual_motif": "dawn light",
        "anchor_inputs": [],
        "camera": {
            "start_state": "wide",
            "end_state": "medium",
            "motion_direction": "push-in",
            "motion_speed": "slow",
        },
        "duration_seconds": 8,
        "crop_rules": {"desktop": "16:9", "mobile": "9:16"},
        "copy_overlay_timing": [],
        "cta_relationship": "none",
        "generation_model": "kie-veo3-fast",
        "generation_tier": "final-motion",
        "connector_required": False,
        "expected_generation_count": 1,
        "estimated_cost_usd": 0.40,
        "approval_status": "anchor_approved",
    }
    scene.update(overrides)
    return scene


def _scene_plan(scenes) -> dict:
    now = _now()
    return {
        "schema_version": "1.0.0",
        "project_id": "proj-estimate-cost-tests",
        "architecture": "hybrid",
        "scenes": scenes,
        "created_at": now,
        "updated_at": now,
    }


class QuantityForUnitTests(unittest.TestCase):
    def test_usd_per_second_multiplies_duration_by_count(self) -> None:
        self.assertEqual(ec.quantity_for_unit("usd_per_second", duration_seconds=8, count=3), 24.0)

    def test_usd_per_second_requires_duration(self) -> None:
        with self.assertRaises(ec.UnsupportedPriceUnitError):
            ec.quantity_for_unit("usd_per_second", duration_seconds=None, count=1)

    def test_usd_per_image_ignores_duration_uses_count(self) -> None:
        self.assertEqual(ec.quantity_for_unit("usd_per_image", duration_seconds=None, count=4), 4.0)

    def test_usd_per_clip_defaults_count_to_one(self) -> None:
        self.assertEqual(ec.quantity_for_unit("usd_per_clip", duration_seconds=8, count=None), 1.0)

    def test_unknown_unit_fails_closed(self) -> None:
        with self.assertRaises(ec.UnsupportedPriceUnitError):
            ec.quantity_for_unit("usd_per_gigawatt", duration_seconds=1, count=1)

    def test_negative_count_never_produces_negative_quantity(self) -> None:
        # max(int(count), 0) — a caller-supplied garbage negative count must
        # never invert into a negative (refundable-looking) quantity.
        self.assertEqual(ec.quantity_for_unit("usd_per_image", count=-5), 0.0)


class EstimateSceneRealRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = providers_base.ModelRegistry()

    def test_verified_model_resolves_a_real_dollar_figure(self) -> None:
        forecast = ec.estimate_scene(_scene(generation_model="kie-veo3-fast"), self.registry)
        self.assertTrue(forecast.resolved)
        self.assertTrue(forecast.verified)
        self.assertEqual(forecast.estimated_cost_usd, 0.40)
        self.assertEqual(forecast.provider_model_slug, "veo3_fast")

    def test_unverified_unpriced_model_fails_closed_not_free(self) -> None:
        forecast = ec.estimate_scene(
            _scene(generation_model="kie-bytedance-seedance-1.5-pro"), self.registry
        )
        self.assertFalse(forecast.resolved)
        self.assertIsNone(forecast.estimated_cost_usd)
        self.assertFalse(forecast.verified)

    def test_zero_expected_generation_count_is_free_and_resolved(self) -> None:
        forecast = ec.estimate_scene(_scene(expected_generation_count=0), self.registry)
        self.assertTrue(forecast.resolved)
        self.assertEqual(forecast.estimated_cost_usd, 0.0)
        self.assertTrue(forecast.verified)

    def test_unknown_model_id_fails_closed_without_raising(self) -> None:
        forecast = ec.estimate_scene(_scene(generation_model="does-not-exist"), self.registry)
        self.assertFalse(forecast.resolved)
        self.assertIsNone(forecast.estimated_cost_usd)
        self.assertIn("registry lookup failed", forecast.note)

    def test_multiple_clips_multiplies_cost_linearly(self) -> None:
        forecast = ec.estimate_scene(
            _scene(generation_model="kie-veo3-fast", expected_generation_count=3), self.registry
        )
        self.assertEqual(forecast.quantity, 3.0)
        self.assertEqual(forecast.estimated_cost_usd, 1.20)


class EstimateScenePlanAggregationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = providers_base.ModelRegistry()

    def test_all_resolved_scene_plan_is_complete_and_verified(self) -> None:
        plan = _scene_plan(
            [
                _scene(scene_id="s1", generation_model="kie-veo3-fast"),
                _scene(scene_id="s2", generation_model="kie-veo3-fast", expected_generation_count=2),
            ]
        )
        forecast = ec.estimate_scene_plan(plan, self.registry)
        self.assertTrue(forecast.complete)
        self.assertTrue(forecast.all_verified)
        self.assertEqual(forecast.unresolved_scene_ids, [])
        self.assertAlmostEqual(forecast.total_estimated_usd, 0.40 + 0.80)
        self.assertEqual(forecast.registry_snapshot_id, self.registry.snapshot_id)

    def test_one_unresolved_scene_marks_the_whole_forecast_incomplete(self) -> None:
        plan = _scene_plan(
            [
                _scene(scene_id="s1", generation_model="kie-veo3-fast"),
                _scene(scene_id="s2", generation_model="kie-bytedance-seedance-1.5-pro"),
            ]
        )
        forecast = ec.estimate_scene_plan(plan, self.registry)
        self.assertFalse(forecast.complete)
        self.assertEqual(forecast.unresolved_scene_ids, ["s2"])
        # total still reflects the resolvable scene(s) for visibility.
        self.assertAlmostEqual(forecast.total_estimated_usd, 0.40)

    def test_unverified_but_resolved_scene_marks_all_verified_false(self) -> None:
        plan = _scene_plan(
            [_scene(scene_id="s1", generation_model="kie-gpt-image-2-text-to-image", duration_seconds=None)]
        )
        forecast = ec.estimate_scene_plan(plan, self.registry, resolutions={"s1": "2K"}, strict=False)
        self.assertTrue(forecast.complete)
        self.assertFalse(forecast.all_verified)
        self.assertEqual(forecast.unverified_scene_ids, ["s1"])
        self.assertAlmostEqual(forecast.total_estimated_usd, 0.05)

    def test_empty_scenes_array_is_trivially_complete_with_zero_total(self) -> None:
        # scene-plan.schema.json requires minItems:1 in production, but this
        # module must not crash on a defensively-empty list either.
        plan = _scene_plan([])
        forecast = ec.estimate_scene_plan(plan, self.registry)
        self.assertTrue(forecast.complete)
        self.assertTrue(forecast.all_verified)
        self.assertEqual(forecast.total_estimated_usd, 0.0)


if __name__ == "__main__":
    unittest.main()
