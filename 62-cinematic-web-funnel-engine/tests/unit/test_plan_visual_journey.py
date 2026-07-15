#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_plan_visual_journey.py — unit + break-it test suite for build unit
U10 (scripts/plan_visual_journey.py): the visual-journey / scene planner
(spec Section 9).

stdlib unittest only. Run with:
  python3 -m unittest discover -s tests/unit -v
     (from the 62-cinematic-web-funnel-engine/ directory)
or directly:
  python3 tests/unit/test_plan_visual_journey.py -v

Coverage map:
  - build_scene_plan() deterministic field derivation: architecture
    selection, connector placement per architecture (A/B/C), duration
    clamped to a resolved model's duration_limits, cta_relationship /
    copy_overlay_timing derived from content-manifest.cta_map, anchor_inputs
    derived from content-manifest.claims, scene_id uniqueness.
  - schema validity: every produced scene-plan.json round-trips through
    state_engine.ProjectState (which validates against U6's
    scene-plan.schema.json on every save/load).
  - plan_visual_journey() disk-driver preconditions: missing content-
    manifest, unlocked content-manifest, empty sections, project_id
    mismatch across manifests, unresolvable registry tier.
  - determinism: identical inputs (content-manifest + project-manifest +
    registry snapshot) produce byte-identical output modulo timestamps.
  - check_budget_forecast() REUSES prove_budget.evaluate_forecast (U7) —
    proven by an end-to-end fail (unpriced tier) and an end-to-end pass
    (verified-priced tier) against the SAME reused function, never a
    locally re-implemented pricing check.
  - CLI subprocess contract (--run-dir, --architecture, --generation-tier,
    --check-budget, exit codes, --self-test).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _TESTS_DIR.parent.parent
_SCRIPTS_DIR = _SKILL_DIR / "scripts"
for p in (_SKILL_DIR, _SCRIPTS_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import plan_visual_journey as pvj  # noqa: E402
import prove_budget as pb  # noqa: E402
import state_engine as se  # noqa: E402
from providers import base as providers_base  # noqa: E402

PY = sys.executable or "python3"
SCRIPT = _SCRIPTS_DIR / "plan_visual_journey.py"


class PlanVisualJourneyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="cwfe-plan-visual-journey-tests-"))
        self.registry = providers_base.ModelRegistry()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _fixture(self, **kwargs):
        return pvj.build_fixture_project_and_content_manifest(self.tmp, **kwargs)


# ---------------------------------------------------------------------------
# Preconditions — plan_visual_journey() disk driver
# ---------------------------------------------------------------------------
class PreconditionTests(PlanVisualJourneyTestCase):
    def test_fails_when_content_manifest_missing(self) -> None:
        passed, detail = pvj.plan_visual_journey(self.tmp)
        self.assertFalse(passed)
        self.assertIn("content-manifest.json does not exist", detail)

    def test_fails_when_content_manifest_unlocked(self) -> None:
        state = se.ProjectState(self.tmp)
        state.create_project(
            project_id="proj-unlocked",
            client_slug="acme",
            project_slug="launch",
            deliverable_type="cinematic-funnel",
            budget_cap_usd=25.0,
        )
        unlocked = {
            "schema_version": "1.0.0",
            "project_id": "proj-unlocked",
            "methodology_source": "cinematic-native",
            "source_skill": "62-cinematic-web-funnel-engine",
            "source_skill_version": "0.0.0",
            "page_profiles": [{"profile_id": "main", "sections": ["hero", "cta"]}],
            "section_order": ["hero", "cta"],
            "approved_copy_paths": [],
            "cta_map": {},
            "offer_ledger": [],
            "conversion_requirements": {"form": False, "calendar": False, "payment": False},
            "claims": [],
            "copy_qc_receipt": {},
            "content_hash": "a" * 64,
            "locked": False,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
        }
        state.save("content-manifest", unlocked)
        passed, detail = pvj.plan_visual_journey(self.tmp)
        self.assertFalse(passed)
        self.assertIn("locked", detail)

    def test_fails_when_no_sections_at_all(self) -> None:
        self._fixture(sections=[])
        passed, detail = pvj.plan_visual_journey(self.tmp)
        self.assertFalse(passed)
        self.assertIn("no page sections", detail)

    def test_fails_on_project_id_mismatch_between_manifests(self) -> None:
        project_manifest, content_manifest = self._fixture()
        with self.assertRaises(pvj.PlanVisualJourneyError):
            pvj.build_scene_plan(
                content_manifest,
                {**project_manifest, "project_id": "proj-someone-else"},
                registry=self.registry,
            )

    def test_fails_on_unknown_architecture_override(self) -> None:
        _, content_manifest = self._fixture()
        with self.assertRaises(pvj.PlanVisualJourneyError):
            pvj.build_scene_plan(content_manifest, None, registry=self.registry, architecture="not-a-real-one")

    def test_fails_on_unknown_generation_tier(self) -> None:
        _, content_manifest = self._fixture()
        with self.assertRaises(pvj.PlanVisualJourneyError):
            pvj.build_scene_plan(content_manifest, None, registry=self.registry, generation_tier="not-a-real-tier")

    def test_succeeds_with_no_project_manifest_present(self) -> None:
        # plan_visual_journey() tolerates project-manifest.json being absent —
        # architecture selection just falls back to the section-count default.
        state = se.ProjectState(self.tmp)
        decision_payload = {"decision": {"methodology_source": "cinematic-native"}, "request": {}}
        import resolve_content_engine as rce

        fields = rce.build_cinematic_native_manifest_fields("proj-no-pm", decision_payload)
        fields["page_profiles"] = [{"profile_id": "main", "sections": ["hero", "cta"]}]
        fields["section_order"] = ["hero", "cta"]
        rce.finalize_and_save_content_manifest(self.tmp, fields)
        self.assertFalse(state.exists("project-manifest"))
        passed, detail = pvj.plan_visual_journey(self.tmp)
        self.assertTrue(passed, msg=detail)


# ---------------------------------------------------------------------------
# Deterministic field derivation
# ---------------------------------------------------------------------------
class BuildScenePlanTests(PlanVisualJourneyTestCase):
    def test_scene_count_matches_section_order(self) -> None:
        _, content_manifest = self._fixture(sections=["hero", "offer", "cta"])
        plan = pvj.build_scene_plan(content_manifest, None, registry=self.registry)
        self.assertEqual(len(plan["scenes"]), 3)
        self.assertEqual([s["page_section"] for s in plan["scenes"]], ["hero", "offer", "cta"])

    def test_scene_ids_are_unique_even_with_repeated_section_names(self) -> None:
        _, content_manifest = self._fixture(sections=["hero", "cta", "cta"])
        plan = pvj.build_scene_plan(content_manifest, None, registry=self.registry)
        ids = [s["scene_id"] for s in plan["scenes"]]
        self.assertEqual(len(set(ids)), 3)

    def test_falls_back_to_page_profiles_when_section_order_empty(self) -> None:
        _, content_manifest = self._fixture(sections=["hero", "offer"])
        content_manifest["section_order"] = []
        plan = pvj.build_scene_plan(content_manifest, None, registry=self.registry)
        self.assertEqual([s["page_section"] for s in plan["scenes"]], ["hero", "offer"])

    def test_unknown_section_name_gets_a_deterministic_non_fabricated_fallback(self) -> None:
        _, content_manifest = self._fixture(sections=["a-totally-custom-section"])
        plan = pvj.build_scene_plan(content_manifest, None, registry=self.registry)
        scene = plan["scenes"][0]
        self.assertIn("a-totally-custom-section", scene["narrative_purpose"])
        self.assertTrue(scene["visual_motif"])

    # -- architecture selection -----------------------------------------------
    def test_scroll_story_page_always_gets_continuous_forward_journey(self) -> None:
        project_manifest, content_manifest = self._fixture(
            deliverable_type="scroll-story-page", sections=["hero", "problem", "solution", "offer", "proof", "cta"]
        )
        plan = pvj.build_scene_plan(content_manifest, project_manifest, registry=self.registry)
        self.assertEqual(plan["architecture"], "continuous-forward-journey")

    def test_short_journeys_default_to_continuous_forward_journey(self) -> None:
        _, content_manifest = self._fixture(sections=["hero", "cta"])
        plan = pvj.build_scene_plan(content_manifest, None, registry=self.registry)
        self.assertEqual(plan["architecture"], "continuous-forward-journey")

    def test_longer_funnels_default_to_hybrid(self) -> None:
        _, content_manifest = self._fixture(sections=["hero", "problem", "solution", "offer", "proof", "cta"])
        plan = pvj.build_scene_plan(content_manifest, None, registry=self.registry)
        self.assertEqual(plan["architecture"], "hybrid")

    def test_explicit_architecture_override_wins(self) -> None:
        _, content_manifest = self._fixture(sections=["hero", "cta"])
        plan = pvj.build_scene_plan(
            content_manifest, None, registry=self.registry, architecture="scene-dives-plus-connectors"
        )
        self.assertEqual(plan["architecture"], "scene-dives-plus-connectors")

    # -- connector placement per architecture ---------------------------------
    def test_continuous_forward_journey_never_requires_connectors(self) -> None:
        _, content_manifest = self._fixture(sections=["hero", "problem", "solution", "offer"])
        plan = pvj.build_scene_plan(
            content_manifest, None, registry=self.registry, architecture="continuous-forward-journey"
        )
        self.assertTrue(all(not s["connector_required"] for s in plan["scenes"]))

    def test_scene_dives_requires_a_connector_at_every_scene_after_the_first(self) -> None:
        _, content_manifest = self._fixture(sections=["hero", "problem", "solution", "offer"])
        plan = pvj.build_scene_plan(
            content_manifest, None, registry=self.registry, architecture="scene-dives-plus-connectors"
        )
        flags = [s["connector_required"] for s in plan["scenes"]]
        self.assertEqual(flags, [False, True, True, True])

    def test_hybrid_requires_a_connector_only_at_chapter_boundaries(self) -> None:
        _, content_manifest = self._fixture(
            sections=["s0", "s1", "s2", "s3", "s4", "s5", "s6"]
        )
        plan = pvj.build_scene_plan(
            content_manifest, None, registry=self.registry, architecture="hybrid", chapter_size=3
        )
        flags = [s["connector_required"] for s in plan["scenes"]]
        # index 0 -> False (first scene); index 3, 6 are chapter boundaries -> True; rest False.
        self.assertEqual(flags, [False, False, False, True, False, False, True])

    def test_connector_required_scenes_expect_two_generations_not_required_scenes_expect_one(self) -> None:
        _, content_manifest = self._fixture(sections=["hero", "problem", "solution", "offer"])
        plan = pvj.build_scene_plan(
            content_manifest, None, registry=self.registry, architecture="scene-dives-plus-connectors"
        )
        self.assertEqual(plan["scenes"][0]["expected_generation_count"], 1)
        self.assertTrue(all(s["expected_generation_count"] == 2 for s in plan["scenes"][1:]))

    # -- cta_map / claims derivation -------------------------------------------
    def test_cta_relationship_and_overlay_timing_derive_from_cta_map(self) -> None:
        _, content_manifest = self._fixture(
            sections=["hero", "offer", "cta"],
            cta_map={"cta": {"label": "Book Now", "type": "calendar"}},
        )
        plan = pvj.build_scene_plan(content_manifest, None, registry=self.registry)
        by_section = {s["page_section"]: s for s in plan["scenes"]}
        self.assertEqual(by_section["cta"]["cta_relationship"], "primary-cta")
        self.assertEqual(len(by_section["cta"]["copy_overlay_timing"]), 1)
        self.assertEqual(by_section["hero"]["copy_overlay_timing"], [])

    def test_anchor_inputs_derive_from_claims_truth_sources(self) -> None:
        _, content_manifest = self._fixture(
            sections=["hero", "cta"],
            claims=[
                {"claim": "A", "truth_source": "source-a"},
                {"claim": "B", "truth_source": "source-b"},
                {"claim": "C", "truth_source": "source-a"},  # duplicate -> deduped
            ],
        )
        plan = pvj.build_scene_plan(content_manifest, None, registry=self.registry)
        self.assertEqual(plan["scenes"][0]["anchor_inputs"], ["source-a", "source-b"])

    def test_no_claims_means_empty_anchor_inputs(self) -> None:
        _, content_manifest = self._fixture(sections=["hero", "cta"], claims=[])
        plan = pvj.build_scene_plan(content_manifest, None, registry=self.registry)
        self.assertEqual(plan["scenes"][0]["anchor_inputs"], [])

    # -- duration clamped to the resolved model's duration_limits --------------
    def test_duration_clamped_to_veo3_valid_values(self) -> None:
        _, content_manifest = self._fixture(sections=["hero"])
        plan = pvj.build_scene_plan(content_manifest, None, registry=self.registry, generation_tier="premium-override")
        # kie-veo3-fast's duration_limits.valid_values is [4, 6, 8]; the
        # planner's target (8) is already a member, so it must resolve exactly.
        self.assertEqual(plan["scenes"][0]["duration_seconds"], 8)

    # -- generation model / tier resolution never hardcodes a slug -------------
    def test_generation_model_resolves_through_the_registry_not_hardcoded(self) -> None:
        _, content_manifest = self._fixture(sections=["hero"])
        plan = pvj.build_scene_plan(content_manifest, None, registry=self.registry, generation_tier="premium-override")
        self.assertEqual(plan["scenes"][0]["generation_model"], self.registry.resolve_default(
            "premium_photoreal_override", require_priced=False
        )["model_id"])

    def test_every_scene_starts_proposed_with_no_anchor_hash(self) -> None:
        _, content_manifest = self._fixture(sections=["hero", "cta"])
        plan = pvj.build_scene_plan(content_manifest, None, registry=self.registry)
        for scene in plan["scenes"]:
            self.assertEqual(scene["approval_status"], "proposed")
            self.assertIsNone(scene["anchor_asset_hash"])


# ---------------------------------------------------------------------------
# Schema validity (round-trips through state_engine's U6 validator)
# ---------------------------------------------------------------------------
class SchemaValidityTests(PlanVisualJourneyTestCase):
    def test_written_scene_plan_round_trips_through_state_engine(self) -> None:
        self._fixture()
        passed, detail = pvj.plan_visual_journey(self.tmp)
        self.assertTrue(passed, msg=detail)
        # load() re-validates against structure/scene-plan.schema.json — a
        # SchemaValidationFailed here would fail this test.
        loaded = se.ProjectState(self.tmp).load("scene-plan")
        self.assertEqual(loaded["schema_version"], "1.0.0")

    def test_receipt_is_written_and_shaped(self) -> None:
        self._fixture()
        pvj.plan_visual_journey(self.tmp)
        receipt = json.loads((self.tmp / "scene-planner-receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["producer"], "scripts/plan_visual_journey.py")
        self.assertEqual(receipt["scene_count"], 6)
        self.assertIn("registry_snapshot_id", receipt)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------
class DeterminismTests(PlanVisualJourneyTestCase):
    def test_identical_inputs_produce_identical_output_modulo_timestamps(self) -> None:
        _, content_manifest = self._fixture()
        plan_a = pvj.build_scene_plan(content_manifest, None, registry=self.registry)
        plan_b = pvj.build_scene_plan(content_manifest, None, registry=self.registry)
        strip = lambda p: {k: v for k, v in p.items() if k not in ("created_at", "updated_at")}  # noqa: E731
        self.assertEqual(json.dumps(strip(plan_a), sort_keys=True), json.dumps(strip(plan_b), sort_keys=True))


# ---------------------------------------------------------------------------
# check_budget_forecast() reuses prove_budget.evaluate_forecast — proven,
# not asserted, by exercising the SAME reused function to both a real FAIL
# and a real PASS.
# ---------------------------------------------------------------------------
class BudgetForecastReuseTests(PlanVisualJourneyTestCase):
    def test_reused_forecast_fails_closed_on_unpriced_default_tier(self) -> None:
        self._fixture()
        pvj.plan_visual_journey(self.tmp)  # default generation_tier='final-motion' -> unpriced Seedance
        ok, detail = pvj.check_budget_forecast(self.tmp)
        self.assertFalse(ok)
        # Confirm this call is genuinely prove_budget's own evaluate_forecast,
        # not a re-implementation, by checking the SAME receipt file it writes.
        receipt = json.loads((self.tmp / "budget-forecast-gate-receipt.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["af_code"], "AF-CWFE-P4-JOURNEY")
        self.assertFalse(receipt["passed"])

    def test_reused_forecast_passes_once_verified_priced_tier_is_chosen(self) -> None:
        self._fixture()
        pvj.plan_visual_journey(self.tmp, generation_tier="premium-override")
        ok, detail = pvj.check_budget_forecast(self.tmp)
        self.assertTrue(ok, msg=detail)
        # Independently confirm via a direct prove_budget call against the
        # exact same run_dir/scene-plan.json — pvj's wrapper must agree.
        direct_ok, direct_detail = pb.evaluate_forecast(self.tmp)
        self.assertEqual(ok, direct_ok)
        self.assertEqual(detail, direct_detail)


# ---------------------------------------------------------------------------
# CLI subprocess contract
# ---------------------------------------------------------------------------
class CliTests(PlanVisualJourneyTestCase):
    def test_self_test_exits_zero(self) -> None:
        proc = subprocess.run([PY, str(SCRIPT), "--self-test"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertIn("RESULT: PASS", proc.stdout)

    def test_missing_run_dir_is_usage_error(self) -> None:
        proc = subprocess.run(
            [PY, str(SCRIPT), "--run-dir", "/definitely/does/not/exist"], capture_output=True, text=True
        )
        self.assertEqual(proc.returncode, 3)

    def test_no_run_dir_and_no_self_test_is_usage_error(self) -> None:
        proc = subprocess.run([PY, str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 3)

    def test_cli_builds_scene_plan_and_exits_zero(self) -> None:
        self._fixture()
        proc = subprocess.run([PY, str(SCRIPT), "--run-dir", str(self.tmp)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertIn("[PASS] scene planner", proc.stdout)
        self.assertTrue((self.tmp / "journey" / "scene-plan.json").exists())

    def test_cli_fails_closed_without_content_manifest(self) -> None:
        proc = subprocess.run([PY, str(SCRIPT), "--run-dir", str(self.tmp)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("[FAIL] scene planner", proc.stderr)

    def test_cli_check_budget_fails_when_unpriced_tier(self) -> None:
        self._fixture()
        proc = subprocess.run(
            [PY, str(SCRIPT), "--run-dir", str(self.tmp), "--check-budget"], capture_output=True, text=True
        )
        self.assertEqual(proc.returncode, 2, msg=proc.stdout + proc.stderr)
        self.assertIn("P4-JOURNEY forecast", proc.stderr)

    def test_cli_check_budget_passes_with_premium_override(self) -> None:
        self._fixture()
        proc = subprocess.run(
            [PY, str(SCRIPT), "--run-dir", str(self.tmp), "--generation-tier", "premium-override", "--check-budget"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertIn("[PASS] P4-JOURNEY forecast", proc.stdout)

    def test_cli_architecture_override_is_honored(self) -> None:
        self._fixture(sections=["hero", "cta"])
        proc = subprocess.run(
            [PY, str(SCRIPT), "--run-dir", str(self.tmp), "--architecture", "hybrid"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        plan = json.loads((self.tmp / "journey" / "scene-plan.json").read_text(encoding="utf-8"))
        self.assertEqual(plan["architecture"], "hybrid")

    def test_cli_bad_chapter_size_is_usage_error(self) -> None:
        self._fixture()
        proc = subprocess.run(
            [PY, str(SCRIPT), "--run-dir", str(self.tmp), "--chapter-size", "0"], capture_output=True, text=True
        )
        self.assertEqual(proc.returncode, 3)


if __name__ == "__main__":
    unittest.main()
