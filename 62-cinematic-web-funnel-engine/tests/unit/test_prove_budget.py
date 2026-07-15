#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_prove_budget.py — unit + break-it test suite for build unit U7
(scripts/prove_budget.py + scripts/estimate_cost.py + scripts/approve_paid_run.py).

stdlib unittest only. Run with:
  python3 -m unittest discover -s tests/unit -v
     (from the 62-cinematic-web-funnel-engine/ directory)
or directly:
  python3 tests/unit/test_prove_budget.py -v

Coverage map (spec Section 10.3 "no paid generation before ..." + Section
19.1/19.4's parts this unit owns):

  - evaluate_forecast()   P4-JOURNEY  -> ForecastGateTests
  - evaluate_approval()   P5-BUDGET   -> ApprovalGateTests
  - evaluate_paid_call_preconditions()  AF-CWFE-PAID-GATE, all 8 preconditions
    independently, plus the two REQUIRED break-it cases:
      * overspend attempt is hard-stopped                -> BreakItOverspendTests
      * duplicate paid call is refused                    -> BreakItDuplicateCallTests
  - CLI subprocess contract (--run-dir, --check, exit codes, --self-test)
    -> CliTests
"""

from __future__ import annotations

import datetime
import json
import os
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

import approve_paid_run as apr  # noqa: E402
import prove_budget as pb  # noqa: E402
import state_engine as se  # noqa: E402

PY = sys.executable or "python3"
GATE_SCRIPT = _SCRIPTS_DIR / "prove_budget.py"


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _scene_plan(model_id: str = "kie-veo3-fast", duration_seconds: float = 8, count: int = 1) -> dict:
    now = _now()
    return {
        "schema_version": "1.0.0",
        "project_id": "proj-prove-budget-tests",
        "architecture": "hybrid",
        "scenes": [
            {
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
                "duration_seconds": duration_seconds,
                "crop_rules": {"desktop": "16:9", "mobile": "9:16"},
                "copy_overlay_timing": [],
                "cta_relationship": "none",
                "generation_model": model_id,
                "generation_tier": "final-motion",
                "connector_required": False,
                "expected_generation_count": count,
                "estimated_cost_usd": 0.40,
                "approval_status": "anchor_approved",
                "anchor_asset_hash": "a" * 64,
            }
        ],
        "created_at": now,
        "updated_at": now,
    }


class ProveBudgetTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="cwfe-prove-budget-tests-"))
        self.state = se.ProjectState(self.tmp)
        self.state.create_project(
            project_id="proj-prove-budget-tests",
            client_slug="acme",
            project_slug="launch",
            deliverable_type="cinematic-landing-page",
            budget_cap_usd=1.0,
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _lock_intake(self) -> None:
        self.state.transition_project_status("journey", reason="test: simulate P1-P3 passing")

    def _write_scene_plan(self, **kwargs) -> None:
        self.state.save("scene-plan", _scene_plan(**kwargs))

    def _approve(self, cap_usd: float = 5.0, approved_by: str = "test-operator") -> None:
        apr.approve(self.tmp, cap_usd=cap_usd, approved_by=approved_by, note="test approval")


# ---------------------------------------------------------------------------
# P4-JOURNEY — evaluate_forecast
# ---------------------------------------------------------------------------


class ForecastGateTests(ProveBudgetTestCase):
    def test_fails_when_scene_plan_missing(self) -> None:
        passed, detail = pb.evaluate_forecast(self.tmp)
        self.assertFalse(passed)
        self.assertIn("scene-plan.json", detail)

    def test_passes_with_a_fully_priced_scene_plan(self) -> None:
        self._write_scene_plan()
        passed, detail = pb.evaluate_forecast(self.tmp)
        self.assertTrue(passed)
        self.assertIn("total_estimated_usd=0.4", detail)

    def test_fails_when_a_scene_targets_an_unpriced_model(self) -> None:
        self._write_scene_plan(model_id="kie-bytedance-seedance-1.5-pro")
        passed, detail = pb.evaluate_forecast(self.tmp)
        self.assertFalse(passed)
        self.assertIn("scene-01", detail)

    def test_writes_a_receipt_either_way(self) -> None:
        pb.evaluate_forecast(self.tmp)  # fails (no scene plan) — must still write a receipt
        receipt_path = self.tmp / "budget-forecast-gate-receipt.json"
        self.assertTrue(receipt_path.exists())
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["af_code"], "AF-CWFE-P4-JOURNEY")
        self.assertFalse(receipt["passed"])

    def test_never_hardcodes_price_uses_live_registry_snapshot(self) -> None:
        self._write_scene_plan()
        pb.evaluate_forecast(self.tmp)
        receipt = json.loads((self.tmp / "budget-forecast-gate-receipt.json").read_text(encoding="utf-8"))
        from providers import base as providers_base

        self.assertEqual(receipt["forecast"]["registry_snapshot_id"], providers_base.ModelRegistry().snapshot_id)


# ---------------------------------------------------------------------------
# P5-BUDGET — evaluate_approval
# ---------------------------------------------------------------------------


class ApprovalGateTests(ProveBudgetTestCase):
    def test_fails_before_any_approval(self) -> None:
        passed, detail = pb.evaluate_approval(self.tmp)
        self.assertFalse(passed)

    def test_passes_once_approved(self) -> None:
        self._approve(cap_usd=5.0)
        passed, detail = pb.evaluate_approval(self.tmp)
        self.assertTrue(passed)
        self.assertIn("cap_usd=5.0", detail)

    def test_fails_when_flag_is_hand_edited_without_matching_audit_entry(self) -> None:
        manifest = self.state.load("project-manifest")
        manifest["budget"]["approved"] = True
        manifest["budget"]["approved_by"] = "nobody"
        manifest["budget"]["approved_at"] = "2020-01-01T00:00:00Z"
        manifest["budget"]["cap_usd"] = 42.0
        self.state.save("project-manifest", manifest)
        passed, detail = pb.evaluate_approval(self.tmp)
        self.assertFalse(passed)

    def test_fails_when_ledger_and_manifest_cap_disagree(self) -> None:
        self._approve(cap_usd=5.0)
        ledger = self.state.load("cost-ledger")
        ledger["budget_cap_usd"] = 999.0  # simulate drift/corruption
        self.state.save("cost-ledger", ledger)
        passed, detail = pb.evaluate_approval(self.tmp)
        self.assertFalse(passed)
        self.assertIn("does not match", detail)

    def test_writes_a_receipt_either_way(self) -> None:
        pb.evaluate_approval(self.tmp)
        self.assertTrue((self.tmp / "budget-approval-gate-receipt.json").exists())


# ---------------------------------------------------------------------------
# AF-CWFE-PAID-GATE — all 8 preconditions, individually
# ---------------------------------------------------------------------------


class PaidCallGateEightPreconditionsTests(ProveBudgetTestCase):
    def _call(self, **overrides):
        kwargs = dict(
            provider="kie",
            model_id="kie-veo3-fast",
            operation="generate_video",
            params={"scene": "scene-01"},
            duration_seconds=8,
            generation_count=1,
        )
        kwargs.update(overrides)
        return pb.evaluate_paid_call_preconditions(self.tmp, **kwargs)

    def _names(self, result) -> dict:
        return {c.name: c.passed for c in result.checks}

    def test_all_eight_named_checks_are_always_present(self) -> None:
        result = self._call()
        expected = {
            "intake_locked",
            "scene_plan_exists",
            "model_registry_resolves",
            "cost_estimate_exists",
            "budget_cap_exists",
            "approval_recorded",
            "run_manifest_persisted",
            "idempotency_check_passes",
        }
        self.assertEqual(set(self._names(result).keys()), expected)

    def test_fails_closed_on_brand_new_project(self) -> None:
        result = self._call()
        self.assertFalse(result.passed)
        names = self._names(result)
        self.assertFalse(names["intake_locked"])
        self.assertFalse(names["scene_plan_exists"])
        self.assertFalse(names["approval_recorded"])
        # NOTE: budget_cap_exists checks only "is cap_usd positive?" — a
        # brand-new project's create_project() placeholder cap (1.0) is
        # already positive, so this precondition alone can be true on a
        # brand-new project. Explicit sufficiency/approval is a SEPARATE
        # precondition (approval_recorded, asserted False above). See
        # test_budget_cap_exists_precondition_specifically.

    def test_intake_locked_precondition_specifically(self) -> None:
        self.assertFalse(self._names(self._call())["intake_locked"])
        self._lock_intake()
        self._write_scene_plan()
        self._approve()
        self.assertTrue(self._names(self._call())["intake_locked"])

    def test_scene_plan_exists_precondition_specifically(self) -> None:
        self._lock_intake()
        self._approve()
        self.assertFalse(self._names(self._call())["scene_plan_exists"])
        self._write_scene_plan()
        self.assertTrue(self._names(self._call())["scene_plan_exists"])

    def test_model_registry_resolves_precondition_rejects_unknown_model(self) -> None:
        self._lock_intake()
        self._write_scene_plan()
        self._approve()
        result = self._call(model_id="totally-not-a-real-model")
        self.assertFalse(result.passed)
        self.assertFalse(self._names(result)["model_registry_resolves"])

    def test_model_registry_resolves_precondition_rejects_deprecated_model(self) -> None:
        from providers import base as providers_base

        real_path = providers_base.DEFAULT_REGISTRY_PATH
        data = json.loads(real_path.read_text(encoding="utf-8"))
        for entry in data["models"]:
            if entry["model_id"] == "kie-veo3-fast":
                entry["status"] = "deprecated"
        temp_registry = self.tmp / "temp-registry.json"
        temp_registry.write_text(json.dumps(data), encoding="utf-8")

        self._lock_intake()
        self._write_scene_plan()
        self._approve()
        result = self._call(registry_path=str(temp_registry))
        self.assertFalse(result.passed)
        self.assertFalse(self._names(result)["model_registry_resolves"])

    def test_cost_estimate_exists_precondition_rejects_unverified_price(self) -> None:
        self._lock_intake()
        self._write_scene_plan(model_id="kie-bytedance-seedance-1.5-pro")
        self._approve()
        result = self._call(model_id="kie-bytedance-seedance-1.5-pro")
        self.assertFalse(result.passed)
        self.assertFalse(self._names(result)["cost_estimate_exists"])

    def test_budget_cap_exists_precondition_specifically(self) -> None:
        self._lock_intake()
        self._write_scene_plan()
        # No approval recorded at all yet -> both budget_cap_exists (default
        # cap_usd=1.0 from create_project IS positive, so this alone can
        # still pass) and approval_recorded should be independently checked.
        result = self._call()
        self.assertTrue(self._names(result)["budget_cap_exists"])  # create_project's default cap is positive
        self.assertFalse(self._names(result)["approval_recorded"])

    def test_approval_recorded_precondition_specifically(self) -> None:
        self._lock_intake()
        self._write_scene_plan()
        self.assertFalse(self._names(self._call())["approval_recorded"])
        self._approve()
        self.assertTrue(self._names(self._call())["approval_recorded"])

    def test_run_manifest_persisted_precondition_true_once_project_created(self) -> None:
        # create_project() in setUp already persisted both files.
        self.assertTrue(self._names(self._call())["run_manifest_persisted"])

    def test_fully_locked_project_passes_all_eight(self) -> None:
        self._lock_intake()
        self._write_scene_plan()
        self._approve()
        result = self._call()
        self.assertTrue(result.passed)
        self.assertTrue(all(result_check.passed for result_check in result.checks))
        self.assertEqual(result.estimated_cost_usd, 0.40)
        self.assertIsNotNone(result.request_hash)

    def test_paid_call_gate_log_is_append_only_evidence_trail(self) -> None:
        self._lock_intake()
        self._write_scene_plan()
        self._approve()
        self._call()
        self._call()
        log = json.loads((self.tmp / "budget-paid-call-gate-log.json").read_text(encoding="utf-8"))
        self.assertEqual(len(log), 2)


# ---------------------------------------------------------------------------
# REQUIRED break-it case 1: overspend
# ---------------------------------------------------------------------------


class BreakItOverspendTests(ProveBudgetTestCase):
    def test_begin_task_hard_stops_when_estimated_cost_exceeds_cap(self) -> None:
        self._lock_intake()
        self._write_scene_plan()
        self._approve(cap_usd=0.10)  # far below the $0.40 veo3_fast estimate

        result = pb.evaluate_paid_call_preconditions(
            self.tmp,
            provider="kie",
            model_id="kie-veo3-fast",
            operation="generate_video",
            params={"scene": "scene-01"},
            duration_seconds=8,
            generation_count=1,
        )
        # The gate's own preconditions do not themselves compare estimate
        # against cap sufficiency (see prove_budget.py's design note) — the
        # actual hard-stop lives in state_engine.begin_task().
        self.assertTrue(result.passed)
        self.assertEqual(result.estimated_cost_usd, 0.40)

        with self.assertRaises(se.BudgetExceeded):
            self.state.begin_task(
                provider="kie",
                model="kie-veo3-fast",
                operation="generate_video",
                params={"scene": "scene-01"},
                estimated_cost_usd=result.estimated_cost_usd,
                seconds=8,
            )

    def test_overspend_leaves_no_ledger_entry_behind(self) -> None:
        self._lock_intake()
        self._write_scene_plan()
        self._approve(cap_usd=0.10)
        try:
            self.state.begin_task(
                provider="kie",
                model="kie-veo3-fast",
                operation="generate_video",
                params={"scene": "scene-01"},
                estimated_cost_usd=0.40,
                seconds=8,
            )
        except se.BudgetExceeded:
            pass
        ledger = self.state.load("cost-ledger")
        self.assertEqual(ledger["entries"], [])

    def test_outstanding_queued_tasks_count_toward_the_cap_before_completion(self) -> None:
        # A cap of $0.50 accepts one $0.40 call, but a second $0.40 call must
        # be blocked by the FIRST call's outstanding (not-yet-complete)
        # estimate — proving the cap accounts for in-flight spend, not just
        # already-completed spend.
        self._lock_intake()
        self._write_scene_plan()
        self._approve(cap_usd=0.50)
        self.state.begin_task(
            provider="kie",
            model="kie-veo3-fast",
            operation="generate_video",
            params={"scene": "scene-01"},
            estimated_cost_usd=0.40,
            seconds=8,
        )
        with self.assertRaises(se.BudgetExceeded):
            self.state.begin_task(
                provider="kie",
                model="kie-veo3-fast",
                operation="generate_video",
                params={"scene": "scene-02-different"},
                estimated_cost_usd=0.40,
                seconds=8,
            )


# ---------------------------------------------------------------------------
# REQUIRED break-it case 2: duplicate paid call
# ---------------------------------------------------------------------------


class BreakItDuplicateCallTests(ProveBudgetTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._lock_intake()
        self._write_scene_plan()
        self._approve(cap_usd=5.0)

    def test_gate_refuses_a_duplicate_call_already_open(self) -> None:
        first = pb.evaluate_paid_call_preconditions(
            self.tmp,
            provider="kie",
            model_id="kie-veo3-fast",
            operation="generate_video",
            params={"scene": "scene-01"},
            duration_seconds=8,
            generation_count=1,
        )
        self.assertTrue(first.passed)
        self.state.begin_task(
            provider="kie",
            model="kie-veo3-fast",
            operation="generate_video",
            params={"scene": "scene-01"},
            estimated_cost_usd=first.estimated_cost_usd,
            seconds=8,
        )

        duplicate = pb.evaluate_paid_call_preconditions(
            self.tmp,
            provider="kie",
            model_id="kie-veo3-fast",
            operation="generate_video",
            params={"scene": "scene-01"},
            duration_seconds=8,
            generation_count=1,
        )
        self.assertFalse(duplicate.passed)
        idempotency_check = next(c for c in duplicate.checks if c.name == "idempotency_check_passes")
        self.assertFalse(idempotency_check.passed)
        self.assertEqual(duplicate.request_hash, first.request_hash)

    def test_gate_still_passes_for_a_genuinely_different_request(self) -> None:
        self.state.begin_task(
            provider="kie",
            model="kie-veo3-fast",
            operation="generate_video",
            params={"scene": "scene-01"},
            estimated_cost_usd=0.40,
            seconds=8,
        )
        different = pb.evaluate_paid_call_preconditions(
            self.tmp,
            provider="kie",
            model_id="kie-veo3-fast",
            operation="generate_video",
            params={"scene": "scene-01", "variant": "retry-2"},  # different params -> different hash
            duration_seconds=8,
            generation_count=1,
        )
        self.assertTrue(different.passed)

    def test_begin_task_itself_independently_rejects_the_duplicate(self) -> None:
        entry = self.state.begin_task(
            provider="kie",
            model="kie-veo3-fast",
            operation="generate_video",
            params={"scene": "scene-01"},
            estimated_cost_usd=0.40,
            seconds=8,
        )
        with self.assertRaises(se.IdempotencyViolation):
            self.state.begin_task(
                provider="kie",
                model="kie-veo3-fast",
                operation="generate_video",
                params={"scene": "scene-01"},
                estimated_cost_usd=0.40,
                seconds=8,
            )
        # And the gate reflects the SAME task/hash the direct call opened.
        result = pb.evaluate_paid_call_preconditions(
            self.tmp,
            provider="kie",
            model_id="kie-veo3-fast",
            operation="generate_video",
            params={"scene": "scene-01"},
            duration_seconds=8,
            generation_count=1,
        )
        self.assertEqual(result.request_hash, entry["request_hash"])
        self.assertFalse(result.passed)

    def test_completed_task_still_blocks_a_repeat_call_after_restart(self) -> None:
        entry = self.state.begin_task(
            provider="kie",
            model="kie-veo3-fast",
            operation="generate_video",
            params={"scene": "scene-01"},
            estimated_cost_usd=0.40,
            seconds=8,
        )
        self.state.transition_task(entry["task_id"], "submitted", provider_task_id="kie-x")
        self.state.transition_task(entry["task_id"], "in_progress")
        self.state.transition_task(entry["task_id"], "complete", actual_cost_usd=0.40)

        # Simulate a fresh process ("after restart") re-evaluating the same
        # request against the same run_dir.
        fresh_result = pb.evaluate_paid_call_preconditions(
            self.tmp,
            provider="kie",
            model_id="kie-veo3-fast",
            operation="generate_video",
            params={"scene": "scene-01"},
            duration_seconds=8,
            generation_count=1,
        )
        self.assertFalse(fresh_result.passed)
        idempotency_check = next(c for c in fresh_result.checks if c.name == "idempotency_check_passes")
        self.assertIn("complete", idempotency_check.detail)


# ---------------------------------------------------------------------------
# CLI subprocess contract
# ---------------------------------------------------------------------------


class CliTests(ProveBudgetTestCase):
    def test_self_test_exits_zero(self) -> None:
        proc = subprocess.run([PY, str(GATE_SCRIPT), "--self-test"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertIn("RESULT: PASS", proc.stdout)

    def test_missing_run_dir_is_usage_error(self) -> None:
        proc = subprocess.run(
            [PY, str(GATE_SCRIPT), "--run-dir", "/definitely/does/not/exist"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 3)

    def test_check_forecast_cli_matches_direct_call(self) -> None:
        self._write_scene_plan()
        proc = subprocess.run(
            [PY, str(GATE_SCRIPT), "--run-dir", str(self.tmp), "--check", "forecast"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        self.assertIn("[PASS] P4-JOURNEY", proc.stdout)

    def test_check_approval_cli_fails_closed_before_approval(self) -> None:
        proc = subprocess.run(
            [PY, str(GATE_SCRIPT), "--run-dir", str(self.tmp), "--check", "approval"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 2)
        self.assertIn("[FAIL] P5-BUDGET", proc.stderr)

    def test_env_var_selects_check_when_flag_omitted(self) -> None:
        env = dict(os.environ, CWFE_BUDGET_CHECK="approval")
        proc = subprocess.run(
            [PY, str(GATE_SCRIPT), "--run-dir", str(self.tmp)],
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(proc.returncode, 2)  # not approved yet -> P5 fails, proving env var routed correctly
        self.assertIn("P5-BUDGET", proc.stderr)

    def test_check_paid_call_preconditions_cli_requires_model_flags(self) -> None:
        proc = subprocess.run(
            [PY, str(GATE_SCRIPT), "--run-dir", str(self.tmp), "--check", "paid-call-preconditions"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 3)

    def test_check_paid_call_preconditions_cli_end_to_end(self) -> None:
        self._lock_intake()
        self._write_scene_plan()
        self._approve()
        proc = subprocess.run(
            [
                PY,
                str(GATE_SCRIPT),
                "--run-dir",
                str(self.tmp),
                "--check",
                "paid-call-preconditions",
                "--provider",
                "kie",
                "--model-id",
                "kie-veo3-fast",
                "--operation",
                "generate_video",
                "--params-json",
                json.dumps({"scene": "scene-01"}),
                "--duration-seconds",
                "8",
                "--generation-count",
                "1",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["passed"])
        self.assertEqual(payload["estimated_cost_usd"], 0.40)


if __name__ == "__main__":
    unittest.main()
