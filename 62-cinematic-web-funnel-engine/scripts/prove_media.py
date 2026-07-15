#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_media.py — P6-ANCHOR / P7-STILLS phase gates (Skill 62, U11).

CWFE-MANIFEST.json wires this module to:

    P6-ANCHOR  gate="scripts/prove_media.py"  py_symbol="prove_media.evaluate_anchor"  af_code="AF-CWFE-P6-ANCHOR"
    P7-STILLS  gate="scripts/prove_media.py"  py_symbol="prove_media.evaluate_stills"  af_code="AF-CWFE-P7-STILLS"

Both phases share this ONE gate script file under the orchestrator's uniform
`python3 <gate> --run-dir <dir>` invocation (run_cinematic_web_funnel.py's
_run_phase_gate passes no phase-specific argument) — exactly the same
constraint prove_budget.py already solved for its P4/P5 split. Which check
runs is selected by the `CWFE_MEDIA_CHECK` environment variable ("anchor"
default, or "stills"), the SAME documented seam prove_budget.py established
(`CWFE_BUDGET_CHECK`) for the identical uniform-invocation problem.

Neither evaluate_* function ever mutates state, calls a provider, or spends
money — pure read-and-verify gates over what scripts/generate_images.py (the
P6/P7 producer) already wrote to disk, matching every other prove_*.py gate
in this skill (a phase never passes on an agent's claim).

TASK/ASSET PROVENANCE (never trust a recorded hash blindly): both gates
re-read every referenced local_path from disk and RECOMPUTE its sha256,
comparing it against the recorded hash_sha256 — a tampered, corrupted, or
missing file on disk fails the gate even when the JSON record itself looks
perfectly schema-valid, mirroring state_engine.py's own atomic-write/verify
discipline and spec 17.4's "asset hashes" gate requirement.

evaluate_stills() also cross-checks the mechanical enforcement point
scene-plan.schema.json's own docstring names for spec 9.3: every scene's
journey/scene-plan.json approval_status/anchor_asset_hash must actually
match what asset-ledger.json's approved anchor_still records — a still that
exists and is 'approved' in the ledger but was never mirrored back into
scene-plan.json (or was mirrored with a stale/wrong hash) fails the gate.

stdlib only. Phase-gate CLI convention matches prove_p0_environment.py /
prove_budget.py: `--run-dir` only, exit 0 = PASS / 2 = FAIL / 3 = usage error.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import state_engine as se  # noqa: E402

AF_CODE_P6 = "AF-CWFE-P6-ANCHOR"
AF_CODE_P7 = "AF-CWFE-P7-STILLS"

EXIT_OK = 0
EXIT_FAIL = 2
EXIT_USAGE = 3

_REQUIRED_SCENE_STILL_PURPOSES = ("anchor_still", "first_frame_still", "last_frame_still")


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_asset_on_disk(entry: Dict[str, Any], *, run_dir: Path, label: str) -> List[str]:
    """Returns a list of violation strings (empty == provenance verified).
    Never trusts entry['hash_sha256'] at face value — always re-reads the
    file at entry['local_path'] and recomputes it."""
    violations: List[str] = []
    raw_path = entry.get("local_path", "")
    local_path = Path(raw_path)
    if not local_path.is_absolute():
        local_path = run_dir / local_path
    actual_hash = _sha256_file(local_path)
    if actual_hash is None:
        violations.append(f"{label}: local_path does not exist on disk: {raw_path!r}")
        return violations
    recorded_hash = entry.get("hash_sha256")
    if actual_hash != recorded_hash:
        violations.append(
            f"{label}: on-disk file hash {actual_hash} does not match recorded hash_sha256 "
            f"{recorded_hash!r} (file tampered, corrupted, or regenerated without updating the ledger)"
        )
    return violations


def _fail(run_dir: Path, receipt: Dict[str, Any], receipt_name: str, detail: str) -> Tuple[bool, str]:
    receipt.update(passed=False, detail=detail)
    _write_json(run_dir / receipt_name, receipt)
    return False, detail


# ---------------------------------------------------------------------------
# P6-ANCHOR
# ---------------------------------------------------------------------------
def evaluate_anchor(run_dir: Path) -> Tuple[bool, str]:
    """CWFE-MANIFEST.json py_symbol 'prove_media.evaluate_anchor'. Writes
    anchor-gate-receipt.json into run_dir either way."""
    state = se.ProjectState(run_dir)
    receipt: Dict[str, Any] = {"gate": "P6-ANCHOR", "af_code": AF_CODE_P6, "checked_at": _now()}
    receipt_name = "anchor-gate-receipt.json"

    if not state.exists("anchor-approval"):
        return _fail(
            run_dir, receipt, receipt_name,
            "anchor-approval.json does not exist yet — P6-ANCHOR's producer "
            "(scripts/generate_images.py) has not run",
        )
    try:
        anchor = state.load("anchor-approval")
    except se.StateEngineError as exc:
        return _fail(run_dir, receipt, receipt_name, f"anchor-approval.json failed to load/validate: {exc}")

    violations: List[str] = []

    if not anchor["concept_candidates"]:
        violations.append(
            "concept_candidates is empty — spec 9.3's two-stage approval requires a concept board "
            "before any final anchor may exist"
        )
    if anchor["status"] != "anchor_approved":
        violations.append(f"status={anchor['status']!r}, expected 'anchor_approved'")
    if not anchor.get("approved_by"):
        violations.append("approved_by is empty — the final anchor approval must be a named, audited event")
    if not anchor.get("approved_at"):
        violations.append("approved_at is empty")

    if anchor.get("final_anchor") is None:
        violations.append("final_anchor is null — required non-null once status='anchor_approved' (spec 9.3)")
    else:
        candidate_ids = {c["candidate_id"] for c in anchor["concept_candidates"]}
        if anchor.get("approved_candidate_id") not in candidate_ids:
            violations.append(
                f"approved_candidate_id={anchor.get('approved_candidate_id')!r} does not reference any "
                "concept_candidates entry"
            )
        violations.extend(_verify_asset_on_disk(anchor["final_anchor"], run_dir=run_dir, label="final_anchor"))

    for i, candidate in enumerate(anchor["concept_candidates"]):
        violations.extend(
            _verify_asset_on_disk(
                candidate, run_dir=run_dir, label=f"concept_candidates[{i}] ({candidate.get('candidate_id')!r})"
            )
        )

    if not state.exists("project-manifest"):
        violations.append("project-manifest.json does not exist — cannot verify the anchor approval's audit trail")
    else:
        try:
            manifest = state.load("project-manifest")
        except se.StateEngineError as exc:
            manifest = None
            violations.append(f"project-manifest.json failed to load/validate: {exc}")
        if manifest is not None and anchor.get("final_anchor") is not None:
            matching = [
                a
                for a in manifest.get("approvals", [])
                if a.get("kind") == "anchor_final"
                and a.get("approved_by") == anchor.get("approved_by")
                and a.get("approved_at") == anchor.get("approved_at")
                and a.get("hash_sha256") == anchor["final_anchor"].get("hash_sha256")
            ]
            if not matching:
                violations.append(
                    "no matching kind='anchor_final' project-manifest.approvals[] audit entry found for "
                    "this approval (spec 25 rule 8: never mark done from an agent's claim alone)"
                )

    if violations:
        return _fail(run_dir, receipt, receipt_name, "; ".join(violations))

    detail = (
        f"anchor approved: {len(anchor['concept_candidates'])} concept candidate(s), final_anchor "
        f"hash_sha256={anchor['final_anchor']['hash_sha256'][:12]}…, approved_by={anchor['approved_by']!r}"
    )
    receipt.update(passed=True, detail=detail)
    _write_json(run_dir / receipt_name, receipt)
    return True, detail


# ---------------------------------------------------------------------------
# P7-STILLS
# ---------------------------------------------------------------------------
def evaluate_stills(run_dir: Path) -> Tuple[bool, str]:
    """CWFE-MANIFEST.json py_symbol 'prove_media.evaluate_stills'. Requires
    P6-ANCHOR to already pass (re-evaluated fresh, never trusted from a prior
    run's receipt). Writes stills-gate-receipt.json into run_dir either way."""
    state = se.ProjectState(run_dir)
    receipt: Dict[str, Any] = {"gate": "P7-STILLS", "af_code": AF_CODE_P7, "checked_at": _now()}
    receipt_name = "stills-gate-receipt.json"

    anchor_ok, anchor_detail = evaluate_anchor(run_dir)
    if not anchor_ok:
        return _fail(
            run_dir, receipt, receipt_name,
            f"P6-ANCHOR has not passed yet (P7-STILLS requires it first): {anchor_detail}",
        )

    if not state.exists("scene-plan"):
        return _fail(run_dir, receipt, receipt_name, "journey/scene-plan.json does not exist yet")
    try:
        scene_plan = state.load("scene-plan")
    except se.StateEngineError as exc:
        return _fail(run_dir, receipt, receipt_name, f"scene-plan.json failed to load/validate: {exc}")

    if not state.exists("asset-ledger"):
        return _fail(
            run_dir, receipt, receipt_name,
            "asset-ledger.json does not exist yet — P7-STILLS's producer (scripts/generate_images.py) "
            "has not run",
        )
    try:
        ledger = state.load("asset-ledger")
    except se.StateEngineError as exc:
        return _fail(run_dir, receipt, receipt_name, f"asset-ledger.json failed to load/validate: {exc}")

    violations: List[str] = []
    assets_by_scene: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for asset in ledger["assets"]:
        assets_by_scene.setdefault(asset["scene_id"], {})[asset["purpose"]] = asset

    for scene in scene_plan["scenes"]:
        scene_id = scene["scene_id"]
        purposes = assets_by_scene.get(scene_id, {})
        missing = [p for p in _REQUIRED_SCENE_STILL_PURPOSES if p not in purposes]
        if missing:
            violations.append(f"scene {scene_id!r}: missing asset-ledger purpose(s) {missing}")
            continue

        for purpose, asset in purposes.items():
            if asset["approval_status"] != "approved":
                violations.append(
                    f"scene {scene_id!r}/{purpose}: approval_status={asset['approval_status']!r}, "
                    "expected 'approved'"
                )
            violations.extend(
                _verify_asset_on_disk(asset, run_dir=run_dir, label=f"scene {scene_id!r}/{purpose}")
            )

        if scene.get("approval_status") != "anchor_approved":
            violations.append(
                f"scene {scene_id!r}: scene-plan.json approval_status={scene.get('approval_status')!r}, "
                "expected 'anchor_approved' (spec 9.3 mirror requirement)"
            )
        anchor_still = purposes.get("anchor_still")
        if anchor_still is not None and scene.get("anchor_asset_hash") != anchor_still.get("hash_sha256"):
            violations.append(
                f"scene {scene_id!r}: scene-plan.json anchor_asset_hash={scene.get('anchor_asset_hash')!r} "
                f"does not match asset-ledger anchor_still hash_sha256={anchor_still.get('hash_sha256')!r}"
            )

    if violations:
        return _fail(run_dir, receipt, receipt_name, "; ".join(violations))

    detail = f"{len(scene_plan['scenes'])} scene(s) fully stilled and approved ({len(ledger['assets'])} asset(s) total)"
    receipt.update(passed=True, detail=detail)
    _write_json(run_dir / receipt_name, receipt)
    return True, detail


# ---------------------------------------------------------------------------
# Self-test — offline, temp run_dir, no network. Builds minimal HAND-CRAFTED
# fixture artifacts directly via state.save() (mirrors prove_budget.py's own
# _self_test_scene_plan() precedent — a gate's self-test proves the gate's
# EVALUATION logic, not the producer's generation pipeline, which
# generate_images.py's own self_test already covers end-to-end).
# ---------------------------------------------------------------------------
def _write_fixture_file(path: Path, content: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _fixture_asset(
    *, local_path: Path, content: bytes, model_id: str = "kie-gpt-image-2-image-to-image",
    provider_task_id: str = "fixture-task-0001", prompt: str = "fixture prompt",
) -> Dict[str, Any]:
    hash_sha256 = _write_fixture_file(local_path, content)
    return {
        "model_id": model_id,
        "provider_task_id": provider_task_id,
        "local_path": str(local_path),
        "hash_sha256": hash_sha256,
        "prompt": prompt,
        "aspect_ratio": "16:9",
        "resolution": "2K",
        "generated_at": _now(),
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

    tmp = Path(tempfile.mkdtemp(prefix="cwfe-prove-media-selftest-"))
    try:
        state = se.ProjectState(tmp)
        state.create_project(
            project_id="proj-prove-media-selftest",
            client_slug="acme",
            project_slug="launch",
            deliverable_type="cinematic-landing-page",
            budget_cap_usd=10.0,
        )

        # ---- break-it: no anchor-approval.json yet ----------------------------
        passed, detail = evaluate_anchor(tmp)
        check(f"evaluate_anchor fails cleanly with no anchor-approval.json yet ({detail})", not passed)
        passed, detail = evaluate_stills(tmp)
        check(f"evaluate_stills fails cleanly with no anchor-approval.json yet ({detail})", not passed)

        now = _now()

        # ---- break-it: proposed status, empty concept board -------------------
        anchor_bad = {
            "schema_version": "1.0.0", "project_id": "proj-prove-media-selftest", "status": "proposed",
            "style_contract": {
                "visual_world": "x", "realism_level": "photoreal", "palette": [], "material_language": "x",
                "lighting_logic": "x", "lens_family": "x", "composition_system": "x",
                "prohibited_styles": [], "negative_prompt": "",
            },
            "concept_candidates": [], "approved_candidate_id": None, "final_anchor": None,
            "approved_by": None, "approved_at": None, "created_at": now, "updated_at": now,
        }
        state.save("anchor-approval", anchor_bad)
        passed, detail = evaluate_anchor(tmp)
        check(
            f"evaluate_anchor fails on empty concept_candidates + status != anchor_approved ({detail})",
            not passed,
        )
        check("anchor-gate-receipt.json was written on failure too", (tmp / "anchor-gate-receipt.json").exists())

        # ---- happy path: hand-crafted, fully-valid, disk-backed fixture -------
        media_dir = tmp / "media" / "stills" / "anchor"
        candidate = _fixture_asset(
            local_path=media_dir / "concept-01.png", content=b"FIXTURE-CONCEPT-01",
            model_id="kie-gpt-image-2-text-to-image", provider_task_id="fixture-concept-task-01",
        )
        candidate["candidate_id"] = "concept-01"
        final_anchor = _fixture_asset(
            local_path=media_dir / "final-anchor.png", content=b"FIXTURE-FINAL-ANCHOR",
            provider_task_id="fixture-final-anchor-task",
        )
        anchor_good = dict(anchor_bad)
        anchor_good.update(
            status="anchor_approved",
            concept_candidates=[candidate],
            approved_candidate_id="concept-01",
            final_anchor=final_anchor,
            approved_by="selftest-operator",
            approved_at=now,
            updated_at=now,
        )
        state.save("anchor-approval", anchor_good)

        passed, detail = evaluate_anchor(tmp)
        check(f"evaluate_anchor fails without a matching project-manifest approvals[] entry ({detail})", not passed)

        manifest = state.load("project-manifest")
        manifest["approvals"].append(
            {"kind": "anchor_final", "approved_by": "selftest-operator", "approved_at": now, "hash_sha256": final_anchor["hash_sha256"]}
        )
        state.save("project-manifest", manifest)

        passed, detail = evaluate_anchor(tmp)
        check(f"evaluate_anchor PASSES against a fully valid, disk-backed, audited fixture ({detail})", passed)

        # ---- break-it: tampered file content (hash mismatch) ------------------
        (media_dir / "final-anchor.png").write_bytes(b"TAMPERED-BYTES")
        passed, detail = evaluate_anchor(tmp)
        check(f"evaluate_anchor detects a tampered final_anchor file (hash mismatch) ({detail})", not passed)
        (media_dir / "final-anchor.png").write_bytes(b"FIXTURE-FINAL-ANCHOR")  # restore
        passed, _ = evaluate_anchor(tmp)
        check("evaluate_anchor passes again once the file is restored", passed)

        # ---- break-it: missing file on disk ------------------------------------
        (media_dir / "concept-01.png").unlink()
        passed, detail = evaluate_anchor(tmp)
        check(f"evaluate_anchor detects a missing concept candidate file ({detail})", not passed)
        _write_fixture_file(media_dir / "concept-01.png", b"FIXTURE-CONCEPT-01")  # restore
        passed, _ = evaluate_anchor(tmp)
        check("evaluate_anchor passes again once the file is restored", passed)

        # ---- P7-STILLS: build a minimal scene-plan + asset-ledger fixture -----
        scene = {
            "scene_id": "scene-01-hero", "page_section": "hero", "narrative_purpose": "x",
            "conversion_purpose": "x", "visual_motif": "x", "anchor_inputs": [],
            "camera": {"start_state": "wide", "end_state": "medium", "motion_direction": "push-in", "motion_speed": "slow"},
            "duration_seconds": 8, "crop_rules": {"desktop": "16:9 full-bleed", "mobile": "9:16 crop-safe"},
            "copy_overlay_timing": [], "cta_relationship": "none", "generation_model": "kie-bytedance-seedance-1.5-pro",
            "generation_tier": "final-motion", "connector_required": False, "expected_generation_count": 1,
            "estimated_cost_usd": 0.4, "approval_status": "proposed", "anchor_asset_hash": None,
        }
        scene_plan = {
            "schema_version": "1.0.0", "project_id": "proj-prove-media-selftest",
            "architecture": "continuous-forward-journey", "scenes": [scene], "created_at": now, "updated_at": now,
        }
        state.save("scene-plan", scene_plan)

        passed, detail = evaluate_stills(tmp)
        check(f"evaluate_stills fails with no asset-ledger.json yet ({detail})", not passed)

        scenes_dir = tmp / "media" / "stills" / "scenes" / "scene-01-hero"
        anchor_still = _fixture_asset(local_path=scenes_dir / "anchor_still.png", content=b"SCENE-ANCHOR")
        anchor_still.update(asset_id="scene-01-hero:anchor_still", scene_id="scene-01-hero", purpose="anchor_still", approval_status="proposed")
        first_frame = _fixture_asset(local_path=scenes_dir / "first_frame_still.png", content=b"SCENE-FIRST")
        first_frame.update(asset_id="scene-01-hero:first_frame_still", scene_id="scene-01-hero", purpose="first_frame_still", approval_status="proposed")
        last_frame = _fixture_asset(local_path=scenes_dir / "last_frame_still.png", content=b"SCENE-LAST")
        last_frame.update(asset_id="scene-01-hero:last_frame_still", scene_id="scene-01-hero", purpose="last_frame_still", approval_status="proposed")
        ledger = {
            "schema_version": "1.0.0", "project_id": "proj-prove-media-selftest",
            "assets": [anchor_still, first_frame, last_frame], "created_at": now, "updated_at": now,
        }
        state.save("asset-ledger", ledger)

        passed, detail = evaluate_stills(tmp)
        check(f"evaluate_stills fails while assets are still approval_status='proposed' ({detail})", not passed)

        for a in ledger["assets"]:
            a["approval_status"] = "approved"
        state.save("asset-ledger", ledger)

        passed, detail = evaluate_stills(tmp)
        check(
            f"evaluate_stills fails when scene-plan.json's own approval_status/anchor_asset_hash were "
            f"never mirrored ({detail})",
            not passed,
        )

        scene_plan["scenes"][0]["approval_status"] = "anchor_approved"
        scene_plan["scenes"][0]["anchor_asset_hash"] = anchor_still["hash_sha256"]
        state.save("scene-plan", scene_plan)

        passed, detail = evaluate_stills(tmp)
        check(f"evaluate_stills PASSES once every scene is fully stilled, approved, and mirrored ({detail})", passed)
        check("stills-gate-receipt.json was written", (tmp / "stills-gate-receipt.json").exists())

        # ---- break-it: a scene missing one purpose -----------------------------
        ledger["assets"] = [a for a in ledger["assets"] if a["purpose"] != "last_frame_still"]
        state.save("asset-ledger", ledger)
        passed, detail = evaluate_stills(tmp)
        check(f"evaluate_stills fails when a scene is missing a required purpose ({detail})", not passed)

        # ---- break-it: scene-plan anchor_asset_hash drifts from the ledger ----
        ledger["assets"].append(last_frame)  # restore
        state.save("asset-ledger", ledger)
        scene_plan["scenes"][0]["anchor_asset_hash"] = "f" * 64
        state.save("scene-plan", scene_plan)
        passed, detail = evaluate_stills(tmp)
        check(f"evaluate_stills detects a scene-plan anchor_asset_hash drift from the ledger ({detail})", not passed)

        # ---- CLI wiring: CWFE_MEDIA_CHECK dispatch -----------------------------
        import subprocess

        scene_plan["scenes"][0]["anchor_asset_hash"] = anchor_still["hash_sha256"]  # restore
        state.save("scene-plan", scene_plan)

        env_anchor = dict(os.environ)
        env_anchor["CWFE_MEDIA_CHECK"] = "anchor"
        result = subprocess.run(
            [sys.executable, str(_SCRIPT_DIR / "prove_media.py"), "--run-dir", str(tmp)],
            capture_output=True, text=True, env=env_anchor,
        )
        check(f"CLI CWFE_MEDIA_CHECK=anchor exits 0 (stderr={result.stderr!r})", result.returncode == 0)

        env_stills = dict(os.environ)
        env_stills["CWFE_MEDIA_CHECK"] = "stills"
        result = subprocess.run(
            [sys.executable, str(_SCRIPT_DIR / "prove_media.py"), "--run-dir", str(tmp)],
            capture_output=True, text=True, env=env_stills,
        )
        check(f"CLI CWFE_MEDIA_CHECK=stills exits 0 (stderr={result.stderr!r})", result.returncode == 0)

        result = subprocess.run(
            [sys.executable, str(_SCRIPT_DIR / "prove_media.py"), "--run-dir", str(tmp), "--check", "stills"],
            capture_output=True, text=True,
        )
        check(f"CLI --check stills explicit flag also exits 0 (stderr={result.stderr!r})", result.returncode == 0)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print(f"RESULT: FAIL — {fails} self-test check(s) failed.", file=sys.stderr)
        return 1
    print("RESULT: PASS — P6-ANCHOR / P7-STILLS gate self-test green.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="P6-ANCHOR / P7-STILLS phase gate for the Cinematic and Web Funnel Engine. "
        "Invoked by run_cinematic_web_funnel.py as `prove_media.py --run-dir <dir>`."
    )
    parser.add_argument("--run-dir", help="project run directory (required unless --self-test)")
    parser.add_argument(
        "--check",
        choices=["anchor", "stills"],
        default=None,
        help="which check to run against --run-dir. Defaults to $CWFE_MEDIA_CHECK (itself defaulting to "
        "'anchor') when omitted — matches the orchestrator's uniform `--run-dir`-only phase-gate invocation.",
    )
    parser.add_argument("--self-test", action="store_true", help="run the built-in offline self-test and exit")
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

    check = args.check or os.environ.get("CWFE_MEDIA_CHECK", "anchor")
    if check == "anchor":
        passed, detail = evaluate_anchor(run_dir)
        label = "P6-ANCHOR"
    else:
        passed, detail = evaluate_stills(run_dir)
        label = "P7-STILLS"

    if passed:
        print(f"[PASS] {label} — {detail}")
        sys.exit(EXIT_OK)
    print(f"[FAIL] {label} — {detail}", file=sys.stderr)
    sys.exit(EXIT_FAIL)


if __name__ == "__main__":
    main()
