#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_budget.py — the budget / paid-call gate (Skill 62, U7).

CWFE-MANIFEST.json wires this module to three gate points:

  - P4-JOURNEY  gate="scripts/prove_budget.py"  py_symbol="prove_budget.evaluate_forecast"
  - P5-BUDGET   gate="scripts/prove_budget.py"  py_symbol="prove_budget.evaluate_approval"
  - cross_cutting AF-CWFE-PAID-GATE  py_symbol="prove_budget.evaluate_paid_call_preconditions"
    trigger: "a paid provider call attempted before P1 locked brief + P4 scene
    plan + a live registry price snapshot + P5 recorded cap approval + an
    idempotency check"

``evaluate_paid_call_preconditions`` is THE gate spec Section 10.3 requires:
no paid generation may occur before ALL eight of its named preconditions
hold. It never mutates state (it is a pure evaluator, like every other
``prove_*`` script in this skill) — a caller that receives a passing
``PaidCallGateResult`` is the one that goes on to call
``scripts/state_engine.py``'s ``ProjectState.begin_task()`` to actually open
the paid task. Money is never spent, and no ledger entry is ever opened, from
inside this module.

The eight preconditions, evaluated independently (never short-circuited, so a
caller/test always sees the full diagnostic picture) and ALL required to pass:

  1. intake_locked                — spec 10.3.1 "intake passes"
  2. scene_plan_exists             — spec 10.3.2 "scene plan exists"
  3. model_registry_resolves       — spec 10.3.3 "model registry resolves"
  4. cost_estimate_exists          — spec 10.3.4 "cost estimate exists"
  5. budget_cap_exists             — spec 10.3.5 "budget cap exists"
  6. approval_recorded             — spec 10.3.6 "user/operator approval is recorded"
  7. run_manifest_persisted        — spec 10.3.7 "run manifest is persisted"
  8. idempotency_check_passes      — spec 10.3.8 "duplicate/idempotency check passes"

Precondition 4 resolves price with `strict=True` (a VERIFIED registry price is
required, never merely a present-but-unconfirmed one) — this is the strict
bar `providers/base.py`'s `ModelRegistry.price_for()` docstring explicitly
names this gate as the owner of (see base.py `_is_priced()`'s comment: "that
stricter bar belongs to the budget gate (U7, AF-CWFE-PAID-GATE)"). A model
whose registry entry is unpriced or merely unverified — for example
`kie-bytedance-seedance-1.5-pro`, whose registry note states Kie.ai has no
published price for it as of this snapshot — correctly, deliberately FAILS
this gate until a live price is confirmed and the registry is updated. This
is fail-closed behavior working as designed, not a defect.

Prices/slugs are NEVER hardcoded here — every number and slug in this module
comes from ``providers/base.py:ModelRegistry`` resolving
``providers/model-registry.json`` at call time (ADR-7, ADR-8), and every
result is stamped with that registry load's ``snapshot_id``.

stdlib only. Phase-gate CLI convention matches `prove_p0_environment.py`:
`--run-dir` only, exit 0 = PASS / 2 = FAIL / 3 = usage error. Because
P4-JOURNEY and P5-BUDGET share this one script file under the orchestrator's
uniform `python3 <gate> --run-dir <dir>` invocation (no phase-specific CLI
flag is passed — see `run_cinematic_web_funnel._run_phase_gate`), which check
runs is selected the same way `prove_p0_environment.py` reads configuration —
an environment variable, `CWFE_BUDGET_CHECK`, set to "forecast" (default) or
"approval". A later orchestrator-integration unit may replace this with a
phase-specific argument if the manifest/orchestrator contract grows one;
until then this is the documented, working seam.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))

import approve_paid_run as apr  # noqa: E402
import estimate_cost as ec  # noqa: E402
import state_engine as se  # noqa: E402
from providers import base as providers_base  # noqa: E402

AF_CODE_PAID_GATE = "AF-CWFE-PAID-GATE"
AF_CODE_P4 = "AF-CWFE-P4-JOURNEY"
AF_CODE_P5 = "AF-CWFE-P5-BUDGET"

EXIT_OK = 0
EXIT_FAIL = 2
EXIT_USAGE = 3

# project-manifest.json status values that mean "intake has NOT yet locked" —
# see project-manifest.schema.json's status enum, whose declared order
# mirrors CWFE-MANIFEST.json's phase spine (created -> intake -> methodology
# -> content -> journey -> ...). Any status past this set means P1-INTAKE has
# already been passed by the no-skip orchestrator.
_PRE_INTAKE_STATUSES = ("created", "intake")


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Result shapes
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class PaidCallGateResult:
    gate: str
    af_code: str
    passed: bool
    checks: List[CheckResult]
    request_hash: Optional[str]
    estimated_cost_usd: Optional[float]
    registry_snapshot_id: Optional[str]
    checked_at: str

    def to_dict(self) -> Dict[str, Any]:
        d = dataclasses.asdict(self)
        d["checks"] = [c.to_dict() for c in self.checks]
        return d

    def failed_checks(self) -> List[CheckResult]:
        return [c for c in self.checks if not c.passed]


def _receipt_path(run_dir: Path, name: str) -> Path:
    return run_dir / name


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _intake_locked(manifest: Dict[str, Any]) -> Tuple[bool, str]:
    status = manifest.get("status")
    if status in _PRE_INTAKE_STATUSES:
        return False, (
            f"project-manifest.status={status!r} has not progressed past intake "
            f"({_PRE_INTAKE_STATUSES!r}) — P1-INTAKE has not locked the project brief yet"
        )
    return True, f"project-manifest.status={status!r} has progressed past intake"


def _budget_cap_exists(manifest: Dict[str, Any]) -> Tuple[bool, str]:
    cap = manifest.get("budget", {}).get("cap_usd")
    if not isinstance(cap, (int, float)) or isinstance(cap, bool) or cap <= 0:
        return False, f"project-manifest.budget.cap_usd is not a positive number (got {cap!r})"
    return True, f"budget.cap_usd={cap}"


def _approval_recorded(run_dir: Path) -> Tuple[bool, str]:
    if apr.is_approved(run_dir):
        return True, "budget.approved=true with a matching approvals[] audit entry"
    return False, (
        "no recorded budget approval — budget.approved is not true, or no matching "
        "kind='budget' approvals[] audit entry exists (see approve_paid_run.py)"
    )


def _run_manifest_persisted(run_dir: Path) -> Tuple[bool, str]:
    pm_path = run_dir / se.ARTIFACT_RELPATHS["project-manifest"]
    cl_path = run_dir / se.ARTIFACT_RELPATHS["cost-ledger"]
    missing = [str(p) for p in (pm_path, cl_path) if not p.exists()]
    if missing:
        return False, f"required persisted artifact(s) missing on disk: {missing}"
    return True, f"{pm_path.name} and {cl_path.name} both persisted on disk"


# ---------------------------------------------------------------------------
# P4-JOURNEY — evaluate_forecast
# ---------------------------------------------------------------------------


def evaluate_forecast(run_dir: Path, *, registry_path: Optional[str] = None) -> Tuple[bool, str]:
    """P4-JOURNEY phase gate. Confirms a schema-valid scene-plan.json exists
    and that every scene in it resolves to a real, quantifiable cost forecast
    against the live model registry (spec 9.2's "estimated cost" field is
    treated as informational only — this gate RE-COMPUTES the forecast from
    the registry rather than trusting the scene-plan's own numbers, per
    ADR-8). Writes budget-forecast-gate-receipt.json into run_dir either way."""
    state = se.ProjectState(run_dir)
    receipt: Dict[str, Any] = {"gate": "P4-JOURNEY", "af_code": AF_CODE_P4, "checked_at": _now()}

    if not state.exists("scene-plan"):
        receipt.update(passed=False, detail="journey/scene-plan.json does not exist yet")
        _write_json(_receipt_path(run_dir, "budget-forecast-gate-receipt.json"), receipt)
        return False, receipt["detail"]

    try:
        scene_plan = state.load("scene-plan")
    except se.StateEngineError as exc:
        receipt.update(passed=False, detail=f"scene-plan.json failed to load/validate: {exc}")
        _write_json(_receipt_path(run_dir, "budget-forecast-gate-receipt.json"), receipt)
        return False, receipt["detail"]

    try:
        registry = providers_base.ModelRegistry(registry_path or providers_base.DEFAULT_REGISTRY_PATH)
    except providers_base.ModelRegistryError as exc:
        receipt.update(passed=False, detail=f"model registry failed to load: {exc}")
        _write_json(_receipt_path(run_dir, "budget-forecast-gate-receipt.json"), receipt)
        return False, receipt["detail"]

    forecast = ec.estimate_scene_plan(scene_plan, registry, strict=True)
    receipt["forecast"] = forecast.to_dict()

    if not forecast.complete:
        detail = (
            f"{len(forecast.unresolved_scene_ids)} scene(s) did not resolve to a priced "
            f"model: {forecast.unresolved_scene_ids}"
        )
        receipt.update(passed=False, detail=detail)
        _write_json(_receipt_path(run_dir, "budget-forecast-gate-receipt.json"), receipt)
        return False, detail

    detail = (
        f"forecast complete: {len(forecast.scenes)} scene(s), "
        f"total_estimated_usd={forecast.total_estimated_usd}, "
        f"registry_snapshot={forecast.registry_snapshot_id[:12]}"
    )
    receipt.update(passed=True, detail=detail)
    _write_json(_receipt_path(run_dir, "budget-forecast-gate-receipt.json"), receipt)
    return True, detail


# ---------------------------------------------------------------------------
# P5-BUDGET — evaluate_approval
# ---------------------------------------------------------------------------


def evaluate_approval(run_dir: Path) -> Tuple[bool, str]:
    """P5-BUDGET phase gate. Confirms a positive budget cap AND a matching
    recorded/audited approval exist, AND that project-manifest.json and
    cost-ledger.json agree on the exact same cap value (spec 11.2 "atomic
    writes only" / "schema validation on every read/write" extended here to
    a cross-file consistency check money-handling code must never skip).
    Writes budget-approval-gate-receipt.json into run_dir either way."""
    state = se.ProjectState(run_dir)
    receipt: Dict[str, Any] = {"gate": "P5-BUDGET", "af_code": AF_CODE_P5, "checked_at": _now()}

    if not state.exists("project-manifest") or not state.exists("cost-ledger"):
        receipt.update(passed=False, detail="project-manifest.json and/or cost-ledger.json do not exist yet")
        _write_json(_receipt_path(run_dir, "budget-approval-gate-receipt.json"), receipt)
        return False, receipt["detail"]

    try:
        manifest = state.load("project-manifest")
        ledger = state.load("cost-ledger")
    except se.StateEngineError as exc:
        receipt.update(passed=False, detail=f"failed to load/validate manifest or ledger: {exc}")
        _write_json(_receipt_path(run_dir, "budget-approval-gate-receipt.json"), receipt)
        return False, receipt["detail"]

    cap_ok, cap_detail = _budget_cap_exists(manifest)
    approved_ok, approved_detail = _approval_recorded(run_dir)

    mismatch = None
    if cap_ok:
        cap = manifest["budget"]["cap_usd"]
        if ledger.get("budget_cap_usd") != cap:
            mismatch = (
                f"project-manifest.budget.cap_usd={cap} does not match "
                f"cost-ledger.budget_cap_usd={ledger.get('budget_cap_usd')}"
            )

    reasons = []
    if not cap_ok:
        reasons.append(cap_detail)
    if not approved_ok:
        reasons.append(approved_detail)
    if mismatch:
        reasons.append(mismatch)

    receipt["cap_check"] = cap_detail
    receipt["approval_check"] = approved_detail
    receipt["cross_file_consistency"] = mismatch or "project-manifest and cost-ledger caps agree"

    if reasons:
        detail = "; ".join(reasons)
        receipt.update(passed=False, detail=detail)
        _write_json(_receipt_path(run_dir, "budget-approval-gate-receipt.json"), receipt)
        return False, detail

    detail = f"budget approved: cap_usd={manifest['budget']['cap_usd']}, approved_by={manifest['budget']['approved_by']!r}"
    receipt.update(passed=True, detail=detail)
    _write_json(_receipt_path(run_dir, "budget-approval-gate-receipt.json"), receipt)
    return True, detail


# ---------------------------------------------------------------------------
# Cross-cutting AF-CWFE-PAID-GATE — evaluate_paid_call_preconditions
# ---------------------------------------------------------------------------


def evaluate_paid_call_preconditions(
    run_dir: Path,
    *,
    provider: str,
    model_id: str,
    operation: str,
    params: Dict[str, Any],
    duration_seconds: Optional[float] = None,
    generation_count: Optional[int] = None,
    resolution: Optional[str] = None,
    registry_path: Optional[str] = None,
    write_log: bool = True,
) -> PaidCallGateResult:
    """THE paid-call gate. Evaluates all eight spec-10.3 preconditions for one
    specific proposed paid call (`provider` + `model_id` + `operation` +
    `params`) and returns a `PaidCallGateResult` a caller must check
    `.passed` on before ever invoking `ProjectState.begin_task()`. Every
    check runs independently — a failure in an early check never prevents
    later checks from also being evaluated and reported, so the caller
    always sees the complete picture (never just the first failure).

    Never mutates project-manifest.json, cost-ledger.json, or the model
    registry. Never opens a cost-ledger task itself. `write_log=True`
    (default) appends this evaluation to an append-only
    budget-paid-call-gate-log.json evidence trail in run_dir (distinct from
    the fixed-name phase-gate receipts, since this check runs once per
    proposed paid call rather than once per phase).
    """
    checks: List[CheckResult] = []
    state = se.ProjectState(run_dir)

    # 1. intake_locked
    if state.exists("project-manifest"):
        try:
            manifest = state.load("project-manifest")
            ok, detail = _intake_locked(manifest)
        except se.StateEngineError as exc:
            manifest = None
            ok, detail = False, f"project-manifest.json failed to load/validate: {exc}"
    else:
        manifest = None
        ok, detail = False, "project-manifest.json does not exist yet"
    checks.append(CheckResult("intake_locked", ok, detail))

    # 2. scene_plan_exists
    if state.exists("scene-plan"):
        try:
            state.load("scene-plan")
            checks.append(CheckResult("scene_plan_exists", True, "journey/scene-plan.json exists and validates"))
        except se.StateEngineError as exc:
            checks.append(CheckResult("scene_plan_exists", False, f"scene-plan.json failed to validate: {exc}"))
    else:
        checks.append(CheckResult("scene_plan_exists", False, "journey/scene-plan.json does not exist yet"))

    # 3. model_registry_resolves
    registry: Optional[providers_base.ModelRegistry] = None
    model_entry: Optional[Dict[str, Any]] = None
    try:
        registry = providers_base.ModelRegistry(registry_path or providers_base.DEFAULT_REGISTRY_PATH)
        model_entry = registry.get_model(model_id)
        if model_entry["status"] == "deprecated":
            checks.append(
                CheckResult(
                    "model_registry_resolves",
                    False,
                    f"model_id {model_id!r} resolves but is status='deprecated' — a deprecated "
                    "model may never back a new paid call through this gate",
                )
            )
        else:
            checks.append(
                CheckResult(
                    "model_registry_resolves",
                    True,
                    f"model_id {model_id!r} resolves to slug {model_entry['provider_model_slug']!r} "
                    f"(registry snapshot {registry.snapshot_id[:12]})",
                )
            )
    except providers_base.ModelRegistryError as exc:
        checks.append(CheckResult("model_registry_resolves", False, f"registry resolution failed: {exc}"))

    # 4. cost_estimate_exists (strict = verified price required)
    estimated_cost_usd: Optional[float] = None
    if registry is not None and model_entry is not None and model_entry["status"] != "deprecated":
        try:
            quantity = ec.quantity_for_unit(
                model_entry.get("price", {}).get("unit"),
                duration_seconds=duration_seconds,
                count=generation_count,
            )
            cost = registry.estimate(model_id, quantity, resolution=resolution, strict=True)
            if cost.estimated_total is None:
                checks.append(
                    CheckResult(
                        "cost_estimate_exists",
                        False,
                        f"no verified price could be resolved for {model_id!r}: {cost.note}",
                    )
                )
            else:
                estimated_cost_usd = cost.estimated_total
                checks.append(
                    CheckResult(
                        "cost_estimate_exists",
                        True,
                        f"estimated_cost_usd={cost.estimated_total} "
                        f"(unit_price={cost.unit_price} x quantity={quantity}, verified=True)",
                    )
                )
        except ec.UnsupportedPriceUnitError as exc:
            checks.append(CheckResult("cost_estimate_exists", False, str(exc)))
    else:
        checks.append(
            CheckResult(
                "cost_estimate_exists",
                False,
                "skipped — model registry resolution already failed (see model_registry_resolves)",
            )
        )

    # 5. budget_cap_exists
    if manifest is not None:
        ok, detail = _budget_cap_exists(manifest)
        checks.append(CheckResult("budget_cap_exists", ok, detail))
    else:
        checks.append(CheckResult("budget_cap_exists", False, "skipped — no project-manifest.json"))

    # 6. approval_recorded
    ok, detail = _approval_recorded(run_dir)
    checks.append(CheckResult("approval_recorded", ok, detail))

    # 7. run_manifest_persisted
    ok, detail = _run_manifest_persisted(run_dir)
    checks.append(CheckResult("run_manifest_persisted", ok, detail))

    # 8. idempotency_check_passes
    request_hash: Optional[str] = None
    if state.exists("cost-ledger"):
        request_hash = se.ProjectState.compute_request_hash(
            provider=provider, model=model_id, operation=operation, params=params
        )
        try:
            existing = state.find_active_or_complete_entry(request_hash)
        except se.StateEngineError as exc:
            checks.append(
                CheckResult("idempotency_check_passes", False, f"cost-ledger.json failed to load: {exc}")
            )
            existing = "unreadable"
        if existing == "unreadable":
            pass
        elif existing is None:
            checks.append(
                CheckResult(
                    "idempotency_check_passes",
                    True,
                    f"no active/complete cost-ledger entry for request_hash={request_hash}",
                )
            )
        else:
            checks.append(
                CheckResult(
                    "idempotency_check_passes",
                    False,
                    f"request_hash={request_hash} already has a {existing['status']!r} task "
                    f"{existing['task_id']} — refusing a duplicate paid call (AF-CWFE-RESTART-DUPLICATE)",
                )
            )
    else:
        checks.append(CheckResult("idempotency_check_passes", False, "cost-ledger.json does not exist yet"))

    passed = all(c.passed for c in checks)
    result = PaidCallGateResult(
        gate="AF-CWFE-PAID-GATE",
        af_code=AF_CODE_PAID_GATE,
        passed=passed,
        checks=checks,
        request_hash=request_hash,
        estimated_cost_usd=estimated_cost_usd if passed else None,
        registry_snapshot_id=registry.snapshot_id if registry is not None else None,
        checked_at=_now(),
    )

    if write_log:
        log_path = _receipt_path(run_dir, "budget-paid-call-gate-log.json")
        log: List[Dict[str, Any]] = []
        if log_path.exists():
            try:
                log = json.loads(log_path.read_text(encoding="utf-8"))
                if not isinstance(log, list):
                    log = []
            except json.JSONDecodeError:
                log = []
        entry = result.to_dict()
        entry["provider"] = provider
        entry["model_id"] = model_id
        entry["operation"] = operation
        log.append(entry)
        _write_json(log_path, log)  # type: ignore[arg-type]

    return result


# ---------------------------------------------------------------------------
# Self-test — offline, temp run_dir, no network. Exercises the happy path
# plus the two explicitly required break-it cases: an overspend attempt and
# a duplicate paid call.
# ---------------------------------------------------------------------------


def _self_test_scene_plan(project_id: str) -> Dict[str, Any]:
    now = _now()
    return {
        "schema_version": "1.0.0",
        "project_id": project_id,
        "architecture": "hybrid",
        "scenes": [
            {
                "scene_id": "scene-01",
                "page_section": "hero",
                "narrative_purpose": "establish the world",
                "conversion_purpose": "hook attention",
                "visual_motif": "dawn light over the product",
                "anchor_inputs": ["anchor-01"],
                "camera": {
                    "start_state": "wide",
                    "end_state": "medium",
                    "motion_direction": "push-in",
                    "motion_speed": "slow",
                },
                "duration_seconds": 8,
                "crop_rules": {"desktop": "16:9 full-bleed", "mobile": "9:16 crop-safe"},
                "copy_overlay_timing": [],
                "cta_relationship": "none",
                "generation_model": "kie-veo3-fast",
                "generation_tier": "final-motion",
                "connector_required": False,
                "expected_generation_count": 1,
                "estimated_cost_usd": 0.40,
                "approval_status": "anchor_approved",
                "anchor_asset_hash": "a" * 64,
            }
        ],
        "created_at": now,
        "updated_at": now,
    }


def self_test() -> int:
    import shutil
    import tempfile

    fails = 0

    def check(label: str, cond: bool) -> None:
        nonlocal fails
        if cond:
            print(f"  [PASS] {label}")
        else:
            print(f"  [FAIL] {label}")
            fails += 1

    tmp = Path(tempfile.mkdtemp(prefix="cwfe-prove-budget-selftest-"))
    try:
        state = se.ProjectState(tmp)

        # A brand-new project (status='created') must fail every precondition
        # that depends on progress having happened yet.
        state.create_project(
            project_id="proj-budget-selftest",
            client_slug="acme",
            project_slug="launch",
            deliverable_type="cinematic-landing-page",
            budget_cap_usd=1.0,  # placeholder, will be overwritten by approve()
        )
        result = evaluate_paid_call_preconditions(
            tmp,
            provider="kie",
            model_id="kie-veo3-fast",
            operation="generate_video",
            params={"scene": "scene-01"},
            duration_seconds=8,
            generation_count=1,
        )
        check("brand-new project fails the paid-call gate (nothing locked/approved yet)", not result.passed)
        check(
            "brand-new project fails intake_locked specifically",
            any(c.name == "intake_locked" and not c.passed for c in result.checks),
        )
        check(
            "brand-new project fails scene_plan_exists specifically",
            any(c.name == "scene_plan_exists" and not c.passed for c in result.checks),
        )
        check(
            "brand-new project fails approval_recorded specifically",
            any(c.name == "approval_recorded" and not c.passed for c in result.checks),
        )

        # Progress the project: lock intake (advance status), write a scene
        # plan, approve a budget cap that comfortably covers the forecast.
        state.transition_project_status("journey", reason="selftest: simulate P1-P3 passing")
        state.save("scene-plan", _self_test_scene_plan("proj-budget-selftest"))

        forecast_ok, forecast_detail = evaluate_forecast(tmp)
        check(f"evaluate_forecast passes once scene-plan.json exists ({forecast_detail})", forecast_ok)

        approval_ok, _ = evaluate_approval(tmp)
        check("evaluate_approval fails before any approval is recorded", not approval_ok)

        apr.approve(tmp, cap_usd=5.00, approved_by="selftest-operator", note="selftest cap")
        approval_ok, approval_detail = evaluate_approval(tmp)
        check(f"evaluate_approval passes once a cap is approved ({approval_detail})", approval_ok)

        result = evaluate_paid_call_preconditions(
            tmp,
            provider="kie",
            model_id="kie-veo3-fast",
            operation="generate_video",
            params={"scene": "scene-01"},
            duration_seconds=8,
            generation_count=1,
        )
        check(
            "fully-locked project PASSES all 8 paid-call preconditions",
            result.passed and len(result.checks) == 8,
        )
        check("passing result carries a verified estimated_cost_usd", result.estimated_cost_usd == 0.40)
        check("passing result carries a request_hash for idempotency", bool(result.request_hash))

        # An unpriced/unverified model (Seedance — see model-registry.json's
        # own disclaimer) must fail the gate at cost_estimate_exists even
        # though every other precondition is satisfied.
        seedance_result = evaluate_paid_call_preconditions(
            tmp,
            provider="kie",
            model_id="kie-bytedance-seedance-1.5-pro",
            operation="generate_video",
            params={"scene": "scene-01-seedance"},
            duration_seconds=8,
            generation_count=1,
        )
        check(
            "an unpriced/unverified registry model fails cost_estimate_exists, not silently priced at $0",
            not seedance_result.passed
            and any(c.name == "cost_estimate_exists" and not c.passed for c in seedance_result.checks),
        )

        # ---- REQUIRED BREAK-IT CASE 1: overspend ----------------------------
        # Approve a cap too small for the call, then prove the SAME state
        # engine begin_task() a real caller would use next actually hard-stops.
        apr.approve(tmp, cap_usd=0.10, approved_by="selftest-operator", note="deliberately too small")
        overspend_result = evaluate_paid_call_preconditions(
            tmp,
            provider="kie",
            model_id="kie-veo3-fast",
            operation="generate_video",
            params={"scene": "scene-01"},
            duration_seconds=8,
            generation_count=1,
        )
        # The gate's own preconditions (cap exists>0, approval recorded) can
        # still all individually pass with a too-small cap — the ACTUAL
        # overspend hard-stop lives in state_engine.begin_task()'s cap
        # comparison against cumulative+outstanding spend, which this gate's
        # caller must invoke next. Prove that hard-stop fires end-to-end.
        # The gate's own 8 preconditions do not themselves compare the
        # estimate against the cap's sufficiency (that requires cumulative +
        # outstanding spend awareness, which is state-mutating and belongs
        # to begin_task's hard-stop, not a stateless precondition check) —
        # confirm that design point explicitly before proving begin_task is
        # the actual enforcement point below.
        check(
            "the gate's preconditions pass even when the (positive) cap is too small — "
            "sufficiency is begin_task's job, not the gate's",
            overspend_result.passed,
        )
        try:
            state.begin_task(
                provider="kie",
                model="kie-veo3-fast",
                operation="generate_video",
                params={"scene": "scene-01"},
                estimated_cost_usd=0.40,
                seconds=8,
            )
            check("begin_task hard-stops an overspend attempt after the gate's cap was set too low", False)
        except se.BudgetExceeded as exc:
            check(f"begin_task hard-stops an overspend attempt after the gate's cap was set too low ({exc})", True)

        # ---- REQUIRED BREAK-IT CASE 2: duplicate paid call -------------------
        apr.approve(tmp, cap_usd=5.00, approved_by="selftest-operator", note="raise cap back up")
        clean_result = evaluate_paid_call_preconditions(
            tmp,
            provider="kie",
            model_id="kie-veo3-fast",
            operation="generate_video",
            params={"scene": "scene-01"},
            duration_seconds=8,
            generation_count=1,
        )
        check("gate passes cleanly once the cap is corrected", clean_result.passed)
        entry = state.begin_task(
            provider="kie",
            model="kie-veo3-fast",
            operation="generate_video",
            params={"scene": "scene-01"},
            estimated_cost_usd=clean_result.estimated_cost_usd,
            seconds=8,
        )
        check("begin_task opens the first paid call for this exact request", entry["status"] == "queued")
        state.transition_task(entry["task_id"], "submitted", provider_task_id="kie-task-selftest-1")
        state.transition_task(entry["task_id"], "in_progress")
        state.transition_task(entry["task_id"], "complete", actual_cost_usd=0.42)

        duplicate_result = evaluate_paid_call_preconditions(
            tmp,
            provider="kie",
            model_id="kie-veo3-fast",
            operation="generate_video",
            params={"scene": "scene-01"},
            duration_seconds=8,
            generation_count=1,
        )
        check(
            "gate refuses a duplicate paid call for a task already open (idempotency_check_passes fails)",
            not duplicate_result.passed
            and any(c.name == "idempotency_check_passes" and not c.passed for c in duplicate_result.checks),
        )
        check(
            "duplicate_result's request_hash matches the original task's request_hash",
            duplicate_result.request_hash == entry["request_hash"],
        )

        # And begin_task() itself independently rejects the literal duplicate.
        try:
            state.begin_task(
                provider="kie",
                model="kie-veo3-fast",
                operation="generate_video",
                params={"scene": "scene-01"},
                estimated_cost_usd=clean_result.estimated_cost_usd,
                seconds=8,
            )
            check("begin_task independently rejects the literal duplicate paid call", False)
        except se.IdempotencyViolation:
            check("begin_task independently rejects the literal duplicate paid call", True)

        # Receipts were actually written to disk (evidence, not just claims).
        check(
            "budget-forecast-gate-receipt.json was written",
            (tmp / "budget-forecast-gate-receipt.json").exists(),
        )
        check(
            "budget-approval-gate-receipt.json was written",
            (tmp / "budget-approval-gate-receipt.json").exists(),
        )
        check(
            "budget-paid-call-gate-log.json accumulated every evaluation",
            len(json.loads((tmp / "budget-paid-call-gate-log.json").read_text(encoding="utf-8"))) >= 5,
        )

        # approve_paid_run.py's own guards.
        try:
            apr.approve(tmp, cap_usd=-1.0, approved_by="selftest-operator")
            check("approve() rejects a non-positive cap", False)
        except apr.InvalidCapError:
            check("approve() rejects a non-positive cap", True)

        try:
            apr.approve(tmp, cap_usd=0.001, approved_by="selftest-operator")
            check("approve() rejects a cap below already-recorded cumulative spend", False)
        except apr.InvalidCapError:
            check("approve() rejects a cap below already-recorded cumulative spend", True)

        try:
            apr.approve(tmp, cap_usd=5.0, approved_by="pit-abc123secrettoken")
            check("approve() rejects an approved_by value shaped like a leaked secret", False)
        except apr.InvalidApproverError:
            check("approve() rejects an approved_by value shaped like a leaked secret", True)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print(f"RESULT: FAIL — {fails} self-test check(s) failed.", file=sys.stderr)
        return 1
    print("RESULT: PASS — budget/paid-call gate self-test green.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Budget / paid-call gate for the Cinematic and Web Funnel Engine "
        "(P4-JOURNEY / P5-BUDGET phase gates + the cross-cutting AF-CWFE-PAID-GATE)."
    )
    parser.add_argument("--run-dir", help="project run directory (required for the phase-gate modes)")
    parser.add_argument("--self-test", action="store_true", help="run the built-in offline self-test and exit")
    parser.add_argument(
        "--check",
        choices=["forecast", "approval", "paid-call-preconditions"],
        default=None,
        help="which check to run against --run-dir. Defaults to $CWFE_BUDGET_CHECK "
        "(itself defaulting to 'forecast') when omitted — matches the orchestrator's "
        "uniform `--run-dir`-only phase-gate invocation.",
    )
    parser.add_argument("--provider", default=None, help="required for --check paid-call-preconditions")
    parser.add_argument("--model-id", default=None, help="required for --check paid-call-preconditions")
    parser.add_argument("--operation", default=None, help="required for --check paid-call-preconditions")
    parser.add_argument("--params-json", default="{}", help="JSON object of request params")
    parser.add_argument("--duration-seconds", type=float, default=None)
    parser.add_argument("--generation-count", type=int, default=None)
    parser.add_argument("--resolution", default=None)
    parser.add_argument("--registry", default=None, help="override path to model-registry.json")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(self_test())

    if not args.run_dir:
        print("USAGE ERROR: --run-dir is required (unless --self-test)", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print(f"USAGE ERROR: --run-dir does not exist: {run_dir}", file=sys.stderr)
        sys.exit(EXIT_USAGE)

    check = args.check or os.environ.get("CWFE_BUDGET_CHECK", "forecast")

    if check == "forecast":
        passed, detail = evaluate_forecast(run_dir, registry_path=args.registry)
        label = "P4-JOURNEY"
    elif check == "approval":
        passed, detail = evaluate_approval(run_dir)
        label = "P5-BUDGET"
    else:
        if not (args.provider and args.model_id and args.operation):
            print(
                "USAGE ERROR: --check paid-call-preconditions requires --provider, --model-id, --operation",
                file=sys.stderr,
            )
            sys.exit(EXIT_USAGE)
        try:
            params = json.loads(args.params_json)
        except json.JSONDecodeError as exc:
            print(f"USAGE ERROR: --params-json is not valid JSON: {exc}", file=sys.stderr)
            sys.exit(EXIT_USAGE)
        result = evaluate_paid_call_preconditions(
            run_dir,
            provider=args.provider,
            model_id=args.model_id,
            operation=args.operation,
            params=params,
            duration_seconds=args.duration_seconds,
            generation_count=args.generation_count,
            resolution=args.resolution,
            registry_path=args.registry,
        )
        print(json.dumps(result.to_dict(), indent=2))
        sys.exit(EXIT_OK if result.passed else EXIT_FAIL)

    if passed:
        print(f"[PASS] {label} — {detail}")
        sys.exit(EXIT_OK)
    print(f"[FAIL] {label} — {detail}", file=sys.stderr)
    sys.exit(EXIT_FAIL)


if __name__ == "__main__":
    main()
