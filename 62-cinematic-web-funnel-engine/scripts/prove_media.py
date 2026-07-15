#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_media.py — P6-ANCHOR / P7-STILLS / P8-DRAFT / P9-FINAL-MEDIA phase
gates (Skill 62, U11 + U12).

CWFE-MANIFEST.json wires this module to:

    P6-ANCHOR      gate="scripts/prove_media.py"  py_symbol="prove_media.evaluate_anchor"  af_code="AF-CWFE-P6-ANCHOR"
    P7-STILLS      gate="scripts/prove_media.py"  py_symbol="prove_media.evaluate_stills"  af_code="AF-CWFE-P7-STILLS"
    P8-DRAFT       gate="scripts/prove_media.py"  py_symbol="prove_media.evaluate_draft"   af_code="AF-CWFE-P8-DRAFT"
    P9-FINAL-MEDIA gate="scripts/prove_media.py"  py_symbol="prove_media.evaluate_final"   af_code="AF-CWFE-P9-FINAL-MEDIA"

(P8/P9 wiring added in U12 — additive to the U11 P6/P7 gates above; neither
evaluate_anchor() nor evaluate_stills() changed shape or behavior.)

All four phases share this ONE gate script file under the orchestrator's
uniform `python3 <gate> --run-dir <dir>` invocation (run_cinematic_web_funnel.py's
_run_phase_gate passes no phase-specific argument) — exactly the same
constraint prove_budget.py already solved for its P4/P5 split. Which check
runs is selected by the `CWFE_MEDIA_CHECK` environment variable ("anchor"
default, "stills", "draft", or "final"), the SAME documented seam
prove_budget.py established (`CWFE_BUDGET_CHECK`) for the identical
uniform-invocation problem.

Each gate CHAINS to the phase before it (evaluate_stills requires
evaluate_anchor to pass first; evaluate_draft requires evaluate_stills;
evaluate_final requires evaluate_draft) — re-evaluated fresh every call,
never trusted from a prior run's receipt, matching CWFE-MANIFEST.json's
no-skip phase-spine contract.

No evaluate_* function ever mutates state, calls a provider, or spends
money — pure read-and-verify gates over what scripts/generate_images.py (the
P6/P7 producer) or scripts/generate_videos.py (the P8/P9 producer) already
wrote to disk, matching every other prove_*.py gate in this skill (a phase
never passes on an agent's claim).

TASK/ASSET PROVENANCE (never trust a recorded hash blindly): every gate
re-reads every referenced local_path/output_path from disk and RECOMPUTES
its sha256, comparing it against the recorded hash_sha256 — a tampered,
corrupted, or missing file on disk fails the gate even when the JSON record
itself looks perfectly schema-valid, mirroring state_engine.py's own
atomic-write/verify discipline and spec 17.4's "asset hashes" gate
requirement. evaluate_final() extends this to a scene-final/connector clip's
FULL chain: the raw provider-downloaded file, the encode_scrub_media.py
encoded variant, and BOTH of extract_boundaries.py's own extracted boundary
frame PNGs — plus a same-hash sanity check that a clip's first and last
boundary frames are genuinely distinct (ADR-9).

evaluate_stills() also cross-checks the mechanical enforcement point
scene-plan.schema.json's own docstring names for spec 9.3: every scene's
journey/scene-plan.json approval_status/anchor_asset_hash must actually
match what asset-ledger.json's approved anchor_still records — a still that
exists and is 'approved' in the ledger but was never mirrored back into
scene-plan.json (or was mirrored with a stale/wrong hash) fails the gate.
evaluate_final() runs an analogous structural cross-check for connectors:
a connector's recorded from_scene_id must equal the scene-plan-computed
adjacent predecessor of its to_scene_id (spec 9.1/9.5's "the connector joins
the PRECEDING scene into THIS scene" adjacency), catching a mis-wired
connector even when every individual file/hash check passes.

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
AF_CODE_P8 = "AF-CWFE-P8-DRAFT"
AF_CODE_P9 = "AF-CWFE-P9-FINAL-MEDIA"

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
# P8-DRAFT
# ---------------------------------------------------------------------------
def evaluate_draft(run_dir: Path) -> Tuple[bool, str]:
    """CWFE-MANIFEST.json py_symbol 'prove_media.evaluate_draft'. Requires
    P7-STILLS to already pass (re-evaluated fresh, never trusted from a prior
    run's receipt). Writes draft-gate-receipt.json into run_dir either way."""
    state = se.ProjectState(run_dir)
    receipt: Dict[str, Any] = {"gate": "P8-DRAFT", "af_code": AF_CODE_P8, "checked_at": _now()}
    receipt_name = "draft-gate-receipt.json"

    stills_ok, stills_detail = evaluate_stills(run_dir)
    if not stills_ok:
        return _fail(
            run_dir, receipt, receipt_name,
            f"P7-STILLS has not passed yet (P8-DRAFT requires it first): {stills_detail}",
        )

    if not state.exists("scene-plan"):
        return _fail(run_dir, receipt, receipt_name, "journey/scene-plan.json does not exist yet")
    try:
        scene_plan = state.load("scene-plan")
    except se.StateEngineError as exc:
        return _fail(run_dir, receipt, receipt_name, f"scene-plan.json failed to load/validate: {exc}")

    if not state.exists("draft-media-receipt"):
        return _fail(
            run_dir, receipt, receipt_name,
            "draft-media-receipt.json does not exist yet — P8-DRAFT's producer "
            "(scripts/generate_videos.py) has not run",
        )
    try:
        drafts = state.load("draft-media-receipt")
    except se.StateEngineError as exc:
        return _fail(run_dir, receipt, receipt_name, f"draft-media-receipt.json failed to load/validate: {exc}")

    violations: List[str] = []
    drafts_by_scene = {d["scene_id"]: d for d in drafts["drafts"]}
    for scene in scene_plan["scenes"]:
        scene_id = scene["scene_id"]
        draft = drafts_by_scene.get(scene_id)
        if draft is None:
            violations.append(f"scene {scene_id!r}: missing draft-media-receipt entry")
            continue
        if draft["review_status"] != "approved":
            violations.append(
                f"scene {scene_id!r} draft: review_status={draft['review_status']!r}, expected 'approved'"
            )
        violations.extend(_verify_asset_on_disk(draft, run_dir=run_dir, label=f"scene {scene_id!r} draft clip"))

    if violations:
        return _fail(run_dir, receipt, receipt_name, "; ".join(violations))

    detail = f"{len(scene_plan['scenes'])} scene(s) fully drafted and approved ({len(drafts['drafts'])} draft(s) on file)"
    receipt.update(passed=True, detail=detail)
    _write_json(run_dir / receipt_name, receipt)
    return True, detail


# ---------------------------------------------------------------------------
# P9-FINAL-MEDIA
# ---------------------------------------------------------------------------
def _verify_media_chain_on_disk(asset: Dict[str, Any], *, run_dir: Path, label: str) -> List[str]:
    """Provenance check for one video-asset-ledger.json entry's FULL chain:
    the raw provider-downloaded clip (via _verify_asset_on_disk, the same
    helper P6/P7 already use), its encode_scrub_media.py encoded variant, and
    BOTH of extract_boundaries.py's own extracted boundary frame PNGs — plus
    a same-hash sanity check that first != last (ADR-9: a clip whose
    extracted boundary frames hash identically is either a genuinely
    single-frame degenerate clip or an extraction fault; either way, it
    cannot back a real seam/connector hand-off, so P9 fails it closed)."""
    violations = list(_verify_asset_on_disk(asset, run_dir=run_dir, label=f"{label} (raw provider download)"))

    encoded = asset.get("encoded") or {}
    encoded_hash = _sha256_file(_resolve(run_dir, encoded.get("output_path", "")))
    if encoded_hash is None:
        violations.append(f"{label}: encoded.output_path does not exist on disk: {encoded.get('output_path')!r}")
    elif encoded_hash != encoded.get("hash_sha256"):
        violations.append(
            f"{label}: encoded output file hash mismatch (tampered, corrupted, or regenerated without "
            "updating the ledger)"
        )

    boundary = asset.get("boundary_frames") or {}
    frame_hashes: Dict[str, Optional[str]] = {}
    for pos in ("first", "last"):
        frame = boundary.get(pos) or {}
        actual = _sha256_file(_resolve(run_dir, frame.get("output_path", "")))
        frame_hashes[pos] = actual
        if actual is None:
            violations.append(f"{label}: boundary_frames.{pos}.output_path does not exist on disk: {frame.get('output_path')!r}")
        elif actual != frame.get("hash_sha256"):
            violations.append(f"{label}: boundary_frames.{pos} file hash mismatch (tampered or corrupted)")

    if frame_hashes.get("first") is not None and frame_hashes.get("first") == frame_hashes.get("last"):
        violations.append(
            f"{label}: boundary_frames.first and .last hash identically — either a genuine single-frame "
            "degenerate clip or a boundary-extraction fault; cannot back a real seam/connector hand-off (ADR-9)"
        )
    return violations


def _resolve(run_dir: Path, raw_path: str) -> Path:
    p = Path(raw_path)
    return p if p.is_absolute() else run_dir / p


def evaluate_final(run_dir: Path) -> Tuple[bool, str]:
    """CWFE-MANIFEST.json py_symbol 'prove_media.evaluate_final'. Requires
    P8-DRAFT to already pass (re-evaluated fresh). Verifies, for every scene:
    a video-asset-ledger.json kind='scene_final' entry exists, is approved,
    and its full raw/encoded/boundary-frame chain is real and on disk; and,
    for every scene whose scene-plan.json connector_required is true, a
    matching kind='connector' entry exists, is approved, its own chain is
    real and on disk, AND its recorded from_scene_id equals the scene-plan
    adjacency's actual predecessor (spec 9.1/9.5). Writes
    final-media-gate-receipt.json into run_dir either way."""
    state = se.ProjectState(run_dir)
    receipt: Dict[str, Any] = {"gate": "P9-FINAL-MEDIA", "af_code": AF_CODE_P9, "checked_at": _now()}
    receipt_name = "final-media-gate-receipt.json"

    draft_ok, draft_detail = evaluate_draft(run_dir)
    if not draft_ok:
        return _fail(
            run_dir, receipt, receipt_name,
            f"P8-DRAFT has not passed yet (P9-FINAL-MEDIA requires it first): {draft_detail}",
        )

    if not state.exists("scene-plan"):
        return _fail(run_dir, receipt, receipt_name, "journey/scene-plan.json does not exist yet")
    try:
        scene_plan = state.load("scene-plan")
    except se.StateEngineError as exc:
        return _fail(run_dir, receipt, receipt_name, f"scene-plan.json failed to load/validate: {exc}")

    if not state.exists("video-asset-ledger"):
        return _fail(
            run_dir, receipt, receipt_name,
            "video-asset-ledger.json does not exist yet — P9-FINAL-MEDIA's producer "
            "(scripts/generate_videos.py) has not run",
        )
    try:
        vledger = state.load("video-asset-ledger")
    except se.StateEngineError as exc:
        return _fail(run_dir, receipt, receipt_name, f"video-asset-ledger.json failed to load/validate: {exc}")

    violations: List[str] = []
    scenes = scene_plan["scenes"]
    finals_by_scene = {a["scene_id"]: a for a in vledger["assets"] if a["kind"] == "scene_final"}
    connectors_by_to = {a["to_scene_id"]: a for a in vledger["assets"] if a["kind"] == "connector"}

    for i, scene in enumerate(scenes):
        scene_id = scene["scene_id"]
        final = finals_by_scene.get(scene_id)
        if final is None:
            violations.append(f"scene {scene_id!r}: missing video-asset-ledger kind='scene_final' entry")
        else:
            if final["approval_status"] != "approved":
                violations.append(
                    f"scene {scene_id!r} final clip: approval_status={final['approval_status']!r}, expected 'approved'"
                )
            violations.extend(_verify_media_chain_on_disk(final, run_dir=run_dir, label=f"scene {scene_id!r} final clip"))

        if scene.get("connector_required"):
            connector = connectors_by_to.get(scene_id)
            if connector is None:
                violations.append(
                    f"scene {scene_id!r}: connector_required=True but no video-asset-ledger kind='connector' "
                    "entry targets it"
                )
                continue
            expected_from = scenes[i - 1]["scene_id"] if i > 0 else None
            if connector.get("from_scene_id") != expected_from:
                violations.append(
                    f"scene {scene_id!r} connector: from_scene_id={connector.get('from_scene_id')!r}, "
                    f"expected {expected_from!r} (scene-plan adjacency, spec 9.1/9.5)"
                )
            if connector["approval_status"] != "approved":
                violations.append(
                    f"scene {scene_id!r} connector: approval_status={connector['approval_status']!r}, "
                    "expected 'approved'"
                )
            violations.extend(
                _verify_media_chain_on_disk(connector, run_dir=run_dir, label=f"scene {scene_id!r} connector clip")
            )

    if violations:
        return _fail(run_dir, receipt, receipt_name, "; ".join(violations))

    detail = (
        f"{len(finals_by_scene)} scene final clip(s) and {len(connectors_by_to)} connector clip(s) fully "
        "encoded, boundary-extracted, and approved"
    )
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

        scene_plan["scenes"][0]["anchor_asset_hash"] = anchor_still["hash_sha256"]  # restore
        state.save("scene-plan", scene_plan)
        passed, _ = evaluate_stills(tmp)
        check("evaluate_stills passes again once scene-plan.anchor_asset_hash is restored (P8/P9 fixtures below need P7 green)", passed)

        # =====================================================================
        # P8-DRAFT / P9-FINAL-MEDIA (U12 additions to this gate script)
        # =====================================================================
        import encode_scrub_media as esm_selftest
        import extract_boundaries as eb_selftest
        import media_ffmpeg as mf_selftest

        def _make_real_video_fixture(label: str) -> Dict[str, Any]:
            """Synthesizes a REAL short H.264 clip with ffmpeg, then runs it
            through the REAL encode_scrub_media.py -> extract_boundaries.py
            pipeline (mirrors extract_boundaries.py's own self-test
            composition), so evaluate_final()'s hash/provenance checks below
            are exercised against genuinely decodable, genuinely distinct
            encoded media -- never opaque/placeholder bytes."""
            binaries = mf_selftest.require_binaries()
            raw_dir = tmp / "media" / "video" / "final" / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            raw_path = raw_dir / f"{label}.mp4"
            cmd = [
                binaries["ffmpeg"], "-y",
                "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=10:duration=2",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                str(raw_path),
            ]
            proc = mf_selftest.run_cmd(cmd, label="ffmpeg-prove-media-fixture")
            if proc.returncode != 0 or not raw_path.exists():
                raise RuntimeError(f"self-test could not synthesize a fixture clip: {proc.stderr[-400:]}")

            asset_id = f"{label}-final"
            encode_out_dir = tmp / "media" / "video" / "final" / "encoded" / asset_id
            media_receipt = esm_selftest.encode_scrub_media(raw_path, encode_out_dir, asset_id=asset_id, variant_names=["desktop"])
            variant = media_receipt["variants"][0]
            boundaries_out_dir = tmp / "media" / "video" / "final" / "boundaries" / asset_id
            variant_path = Path(variant["output_path"])
            boundary_receipt = eb_selftest.extract_boundaries(variant_path, boundaries_out_dir)
            by_pos = {f["position"]: f for f in boundary_receipt["frames"]}

            asset = _fixture_asset(
                local_path=raw_path, content=raw_path.read_bytes(),
                model_id="kie-bytedance-seedance-1.5-pro", provider_task_id=f"fixture-{label}-task",
            )
            asset.update(
                asset_id=f"{label}:final", kind="scene_final", scene_id=label,
                from_scene_id=None, to_scene_id=None, duration_seconds=2.0,
                input_urls=["https://fixtures.example/first.png", "https://fixtures.example/last.png"],
                encoded={
                    "media_processing_receipt_path": str(encode_out_dir / f"{asset_id}.media-processing-receipt.json"),
                    "variant_name": variant["variant_name"], "output_path": variant["output_path"],
                    "width": variant["width"], "height": variant["height"],
                    "duration_seconds": variant["duration_seconds"], "hash_sha256": variant["hash_sha256"],
                },
                boundary_frames={
                    "boundary_frames_receipt_path": str(boundaries_out_dir / f"{variant_path.stem}.boundary-frames.json"),
                    "first": {
                        "frame_index": by_pos["first"]["frame_index"], "timestamp_seconds": by_pos["first"]["timestamp_seconds"],
                        "output_path": by_pos["first"]["output_path"], "hash_sha256": by_pos["first"]["hash_sha256"],
                    },
                    "last": {
                        "frame_index": by_pos["last"]["frame_index"], "timestamp_seconds": by_pos["last"]["timestamp_seconds"],
                        "output_path": by_pos["last"]["output_path"], "hash_sha256": by_pos["last"]["hash_sha256"],
                    },
                },
                approval_status="proposed",
            )
            return asset

        # ---- break-it: no draft-media-receipt.json yet -------------------------
        passed, detail = evaluate_draft(tmp)
        check(f"evaluate_draft fails cleanly with no draft-media-receipt.json yet ({detail})", not passed)
        passed, detail = evaluate_final(tmp)
        check(f"evaluate_final fails cleanly with no draft-media-receipt.json yet either (chains through P8) ({detail})", not passed)

        drafts_dir = tmp / "media" / "video" / "drafts"
        draft_asset = _fixture_asset(
            local_path=drafts_dir / "scene-01-hero.mp4", content=b"FIXTURE-DRAFT-CLIP",
            model_id="kie-bytedance-seedance-1.5-pro", provider_task_id="fixture-draft-task-01",
        )
        draft_asset.update(
            scene_id="scene-01-hero", duration_seconds=8.0,
            input_urls=["https://fixtures.example/first.png", "https://fixtures.example/last.png"],
            review_status="proposed",
        )
        draft_receipt = {
            "schema_version": "1.0.0", "project_id": "proj-prove-media-selftest",
            "drafts": [draft_asset], "created_at": now, "updated_at": now,
        }
        state.save("draft-media-receipt", draft_receipt)

        passed, detail = evaluate_draft(tmp)
        check(f"evaluate_draft fails while the draft is still review_status='proposed' ({detail})", not passed)

        draft_asset["review_status"] = "approved"
        state.save("draft-media-receipt", draft_receipt)
        passed, detail = evaluate_draft(tmp)
        check(f"evaluate_draft PASSES once the draft is approved and on disk ({detail})", passed)
        check("draft-gate-receipt.json was written", (tmp / "draft-gate-receipt.json").exists())

        # ---- break-it: draft file tampered (hash mismatch) ---------------------
        (drafts_dir / "scene-01-hero.mp4").write_bytes(b"TAMPERED")
        passed, detail = evaluate_draft(tmp)
        check(f"evaluate_draft detects a tampered draft clip file ({detail})", not passed)
        _write_fixture_file(drafts_dir / "scene-01-hero.mp4", b"FIXTURE-DRAFT-CLIP")
        passed, _ = evaluate_draft(tmp)
        check("evaluate_draft passes again once the draft file is restored", passed)

        # ---- P9-FINAL-MEDIA: real encoded clip + real extracted boundaries -----
        final_asset = _make_real_video_fixture("scene-01-hero")
        vledger = {
            "schema_version": "1.0.0", "project_id": "proj-prove-media-selftest",
            "assets": [final_asset], "created_at": now, "updated_at": now,
        }
        state.save("video-asset-ledger", vledger)

        passed, detail = evaluate_final(tmp)
        check(f"evaluate_final fails while the final clip is still approval_status='proposed' ({detail})", not passed)

        final_asset["approval_status"] = "approved"
        state.save("video-asset-ledger", vledger)
        passed, detail = evaluate_final(tmp)
        check(f"evaluate_final PASSES once the final clip is approved with a real, on-disk raw/encoded/boundary chain ({detail})", passed)
        check("final-media-gate-receipt.json was written", (tmp / "final-media-gate-receipt.json").exists())

        # ---- break-it: encoded output file tampered ----------------------------
        encoded_path = Path(final_asset["encoded"]["output_path"])
        original_encoded_bytes = encoded_path.read_bytes()
        encoded_path.write_bytes(b"TAMPERED-ENCODED-OUTPUT")
        passed, detail = evaluate_final(tmp)
        check(f"evaluate_final detects a tampered encoded output file ({detail})", not passed)
        encoded_path.write_bytes(original_encoded_bytes)
        passed, _ = evaluate_final(tmp)
        check("evaluate_final passes again once the encoded file is restored", passed)

        # ---- break-it: boundary_frames.first/.last collide (ADR-9 sanity) ------
        boundary_first_path = Path(final_asset["boundary_frames"]["first"]["output_path"])
        boundary_last_path = Path(final_asset["boundary_frames"]["last"]["output_path"])
        original_last_bytes = boundary_last_path.read_bytes()
        original_last_hash = final_asset["boundary_frames"]["last"]["hash_sha256"]
        boundary_last_path.write_bytes(boundary_first_path.read_bytes())
        final_asset["boundary_frames"]["last"]["hash_sha256"] = final_asset["boundary_frames"]["first"]["hash_sha256"]
        state.save("video-asset-ledger", vledger)
        passed, detail = evaluate_final(tmp)
        check(f"evaluate_final detects boundary_frames.first==last hash collision ({detail})", not passed)
        boundary_last_path.write_bytes(original_last_bytes)
        final_asset["boundary_frames"]["last"]["hash_sha256"] = original_last_hash
        state.save("video-asset-ledger", vledger)
        passed, _ = evaluate_final(tmp)
        check("evaluate_final passes again once the boundary frame collision is restored", passed)

        # ---- break-it: connector_required=True but no connector entry ----------
        scene_plan["scenes"][0]["connector_required"] = True
        state.save("scene-plan", scene_plan)
        passed, detail = evaluate_final(tmp)
        check(f"evaluate_final fails when connector_required=True but no connector entry exists ({detail})", not passed)

        # ---- break-it: connector entry with a WRONG from_scene_id (mis-wired) --
        bogus_connector = _make_real_video_fixture("scene-01-hero-connector")
        bogus_connector.update(
            kind="connector", scene_id=None, from_scene_id="scene-99-bogus",
            to_scene_id="scene-01-hero", approval_status="approved",
        )
        vledger["assets"].append(bogus_connector)
        state.save("video-asset-ledger", vledger)
        passed, detail = evaluate_final(tmp)
        check(f"evaluate_final detects a mis-wired connector (wrong from_scene_id adjacency, spec 9.1/9.5) ({detail})", not passed)

        vledger["assets"] = [a for a in vledger["assets"] if a["asset_id"] != bogus_connector["asset_id"]]
        state.save("video-asset-ledger", vledger)
        scene_plan["scenes"][0]["connector_required"] = False
        state.save("scene-plan", scene_plan)
        passed, detail = evaluate_final(tmp)
        check(f"evaluate_final PASSES again once connector_required is restored to False ({detail})", passed)

        # ---- CLI wiring: CWFE_MEDIA_CHECK dispatch -----------------------------
        import subprocess

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

        env_draft = dict(os.environ)
        env_draft["CWFE_MEDIA_CHECK"] = "draft"
        result = subprocess.run(
            [sys.executable, str(_SCRIPT_DIR / "prove_media.py"), "--run-dir", str(tmp)],
            capture_output=True, text=True, env=env_draft,
        )
        check(f"CLI CWFE_MEDIA_CHECK=draft exits 0 (stderr={result.stderr!r})", result.returncode == 0)

        result = subprocess.run(
            [sys.executable, str(_SCRIPT_DIR / "prove_media.py"), "--run-dir", str(tmp), "--check", "final"],
            capture_output=True, text=True,
        )
        check(f"CLI --check final explicit flag exits 0 (stderr={result.stderr!r})", result.returncode == 0)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print(f"RESULT: FAIL — {fails} self-test check(s) failed.", file=sys.stderr)
        return 1
    print("RESULT: PASS — P6-ANCHOR / P7-STILLS / P8-DRAFT / P9-FINAL-MEDIA gate self-test green.")
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
        choices=["anchor", "stills", "draft", "final"],
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
    elif check == "stills":
        passed, detail = evaluate_stills(run_dir)
        label = "P7-STILLS"
    elif check == "draft":
        passed, detail = evaluate_draft(run_dir)
        label = "P8-DRAFT"
    else:
        passed, detail = evaluate_final(run_dir)
        label = "P9-FINAL-MEDIA"

    if passed:
        print(f"[PASS] {label} — {detail}")
        sys.exit(EXIT_OK)
    print(f"[FAIL] {label} — {detail}", file=sys.stderr)
    sys.exit(EXIT_FAIL)


if __name__ == "__main__":
    main()
