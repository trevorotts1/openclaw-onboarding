#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""generate_images.py — anchor image / scene still generator (Skill 62, U11).

Implements spec Section 9.3's two-stage anchor approval (P6-ANCHOR) and
Section 9.2/9.4's per-scene still generation (P7-STILLS):

  P6-ANCHOR:
    1. run_concept_board()        — a low-cost concept board of several
                                     distinct art directions (spec 9.3 stage 1).
    2. approve_concept_candidate() — an operator picks one candidate to seed
                                     the final anchor (spec 9.3's named
                                     approval event, audited in
                                     project-manifest.approvals[]).
    3. generate_final_anchor()    — ONE production-quality anchor image,
                                     generated as an image-to-image reference
                                     off the approved concept candidate
                                     (spec 9.3 stage 2).
    4. approve_final_anchor()     — locks anchor-approval.json
                                     (status='anchor_approved') and records
                                     the audit entry. "No full scene or video
                                     batch may begin until the final anchor
                                     is approved and its asset hash recorded"
                                     (spec 9.3) is enforced by
                                     generate_scene_stills() refusing to run
                                     until this has happened.

  P7-STILLS:
    5. generate_scene_stills()    — for every scene in journey/scene-plan.json,
                                     generates THREE reference-consistent
                                     stills: the scene's own approval-tracked
                                     'anchor_still' (image-to-image off the
                                     approved project anchor) plus a
                                     'first_frame_still' / 'last_frame_still'
                                     boundary pin pair (image-to-image off
                                     that scene's own anchor_still, framed to
                                     the scene's camera.start_state /
                                     end_state — spec 9.2). These boundary
                                     pins seed a LATER unit's video
                                     generation first-and-last-frame control
                                     for a scene's OWN clip; they are NOT the
                                     spec 12.2 connector boundary frames,
                                     which ADR-9 requires be REAL ENCODED
                                     video frames extracted after encoding,
                                     never a generated still.
    6. approve_scene_stills()     — approves the generated stills and
                                     mirrors each scene's own anchor_still
                                     hash into journey/scene-plan.json's
                                     scenes[].anchor_asset_hash /
                                     approval_status='anchor_approved' — the
                                     mechanical enforcement point
                                     scene-plan.schema.json's own docstring
                                     names (spec 9.3).

Every image generation call funnels through the ONE paid-call chokepoint in
this module, `_paid_image_call()`, which never calls a provider directly:
it first evaluates AF-CWFE-PAID-GATE (prove_budget.evaluate_paid_call_
preconditions — spec 10.3's eight preconditions), then opens/tracks the call
through scripts/state_engine.py's ProjectState (idempotency, budget hard-stop,
task status transitions), exactly like every other paid-adjacent unit in this
skill. Nothing here ever hardcodes a Kie model slug or price (ADR-7, ADR-8) —
every model is resolved through providers/base.py:ModelRegistry by capability
tier ('concept_image' for the cheap concept board, 'production_scene_image'
for the final anchor and every scene still — spec 10.2 default policy).

Restart-safety: every producer function checks whether its target asset (by a
deterministic id) is ALREADY recorded on disk before generating it again, and
saves its manifest kind incrementally after each successful asset — never
just once at the end of a multi-asset loop — so a failure partway through a
run never discards already-paid-for assets, and a resumed run never repeats a
completed paid call (the same restart-safety spec 11.2 requires everywhere
else in this skill).

BUILD+TEST AGAINST MOCKED KIE FIXTURES ONLY (spec §19.2) — this module never
makes a live network call in its own test suite; see FixtureKieTransport and
providers/kie.py's own RequestsTransport/KieTransport seam.

stdlib only (providers.kie's optional `requests` dependency is never
triggered by anything in this module's own test/self-test paths).
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))

import prove_budget as pbud  # noqa: E402
import state_engine as se  # noqa: E402
from providers import base as providers_base  # noqa: E402
from providers import kie as kie_provider  # noqa: E402

EXIT_OK = 0
EXIT_FAIL = 2
EXIT_USAGE = 3

# providers/model-registry.json capability_tiers this module resolves through
# (spec 10.2 default policy) — never a hardcoded model_id/slug (ADR-8).
_CONCEPT_TIER = "concept_image"
_PRODUCTION_TIER = "production_scene_image"

_DEFAULT_ASPECT_RATIO = "16:9"
_DEFAULT_CONCEPT_RESOLUTION = "720p"
_DEFAULT_PRODUCTION_RESOLUTION = "2K"

# Spec 9.3 "multiple distinct art directions" — three is the concept-board
# default; callers may override via run_concept_board(candidate_labels=...).
_DEFAULT_CONCEPT_LABELS = ("documentary realism", "editorial premium", "warm cinematic")

_SCENE_STILL_PURPOSES = ("anchor_still", "first_frame_still", "last_frame_still")


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _media_dir(run_dir: Path) -> Path:
    return run_dir / "media" / "stills"


class GenerateImagesError(Exception):
    """Base class for every error this module raises."""


class PaidGateBlocked(GenerateImagesError):
    """A proposed paid image call was refused by AF-CWFE-PAID-GATE
    (prove_budget.evaluate_paid_call_preconditions). Carries the full
    PaidCallGateResult so a caller can inspect exactly which of the eight
    spec-10.3 preconditions failed."""

    def __init__(self, result: "pbud.PaidCallGateResult") -> None:
        self.result = result
        failed = "; ".join(f"{c.name}: {c.detail}" for c in result.failed_checks())
        super().__init__(f"AF-CWFE-PAID-GATE blocked this call: {failed}")


# ---------------------------------------------------------------------------
# Style contract (spec 9.4 consistency rules + spec 8.1 group 4 brand fields)
# ---------------------------------------------------------------------------
def build_style_contract(
    *,
    visual_world: str,
    realism_level: str = "photoreal",
    palette: Optional[List[str]] = None,
    material_language: str = "natural materials, tactile surfaces, consistent light temperature",
    lighting_logic: str = "single consistent key-light direction across every scene",
    lens_family: str = "35mm-85mm cinematic lens family, shallow depth of field",
    composition_system: str = "rule-of-thirds with a consistent horizon line",
    prohibited_styles: Optional[List[str]] = None,
    negative_prompt: str = "no AI-generated text, no watermark, no distorted anatomy, no extra limbs",
) -> Dict[str, Any]:
    """Builds an anchor-approval.schema.json-shaped style_contract object.
    Every field is schema-required; sane defaults are provided so a caller
    only has to name the project-specific visual_world."""
    return {
        "visual_world": visual_world,
        "realism_level": realism_level,
        "palette": list(palette or []),
        "material_language": material_language,
        "lighting_logic": lighting_logic,
        "lens_family": lens_family,
        "composition_system": composition_system,
        "prohibited_styles": list(prohibited_styles or []),
        "negative_prompt": negative_prompt,
    }


def _style_fragment(style_contract: Dict[str, Any]) -> str:
    parts = [
        style_contract["visual_world"],
        f"{style_contract['realism_level']} realism",
        style_contract["lighting_logic"],
        style_contract["lens_family"],
        style_contract["composition_system"],
        style_contract["material_language"],
    ]
    if style_contract.get("palette"):
        parts.append("palette: " + ", ".join(style_contract["palette"]))
    return "; ".join(p for p in parts if p)


def _concept_prompt(style_contract: Dict[str, Any], label: str) -> str:
    return f"{_style_fragment(style_contract)}; concept art direction: {label}"


def _final_anchor_prompt(style_contract: Dict[str, Any]) -> str:
    return (
        f"{_style_fragment(style_contract)}; production-quality hero anchor image — the definitive "
        "visual reference every downstream scene must match"
    )


def _scene_anchor_prompt(style_contract: Dict[str, Any], scene: Dict[str, Any]) -> str:
    return (
        f"{_style_fragment(style_contract)}; scene: {scene['visual_motif']}; "
        f"narrative purpose: {scene['narrative_purpose']}; consistent with the approved project anchor"
    )


def _scene_boundary_prompt(style_contract: Dict[str, Any], scene: Dict[str, Any], purpose: str) -> str:
    camera = scene["camera"]
    state_label = camera["start_state"] if purpose == "first_frame_still" else camera["end_state"]
    return (
        f"{_style_fragment(style_contract)}; scene: {scene['visual_motif']}; "
        f"camera framing at this boundary: {state_label} shot; motion direction: {camera['motion_direction']}; "
        "consistent with this scene's own approved anchor still"
    )


# ---------------------------------------------------------------------------
# THE one paid-call chokepoint. Never call provider.generate_image /
# provider.download_results anywhere else in this module.
# ---------------------------------------------------------------------------
def _paid_image_call(
    run_dir: Path,
    state: se.ProjectState,
    provider: providers_base.MediaProvider,
    *,
    model_id: str,
    prompt: str,
    aspect_ratio: str,
    resolution: str,
    reference_image_urls: Tuple[str, ...] = (),
    negative_prompt: Optional[str] = None,
    purpose: str,
    scene_id: Optional[str],
    destination: Path,
    registry_path: Optional[str],
) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "purpose": purpose,
        "scene_id": scene_id,
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "reference_image_urls": list(reference_image_urls),
    }
    gate_result = pbud.evaluate_paid_call_preconditions(
        run_dir,
        provider=provider.name,
        model_id=model_id,
        operation="generate_image",
        params=params,
        generation_count=1,
        resolution=resolution,
        registry_path=registry_path,
    )
    if not gate_result.passed:
        raise PaidGateBlocked(gate_result)

    try:
        entry = state.begin_task(
            provider=provider.name,
            model=model_id,
            operation="generate_image",
            params=params,
            estimated_cost_usd=gate_result.estimated_cost_usd or 0.0,
            image_count=1,
            resolution=resolution,
        )
    except se.StateEngineError as exc:
        # AF-CWFE-PAID-GATE's own preconditions PASSED, yet begin_task still
        # refused — this is expected, not a contradiction (see
        # prove_budget.py's own docstring: budget SUFFICIENCY and the literal
        # idempotency insert are begin_task's own enforcement, not the
        # gate's stateless precondition check).
        raise GenerateImagesError(
            f"begin_task refused this paid call for {purpose}/{scene_id!r} even though "
            f"AF-CWFE-PAID-GATE passed: {exc}"
        ) from exc

    request = providers_base.ImageGenerationRequest(
        model_id=model_id,
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        reference_image_urls=tuple(reference_image_urls),
        negative_prompt=negative_prompt,
    )
    try:
        handle = provider.generate_image(request)
    except providers_base.ProviderTaskError as exc:
        state.transition_task(entry["task_id"], "failed", retry_reason=str(exc))
        raise GenerateImagesError(f"generate_image submit failed for {purpose}/{scene_id!r}: {exc}") from exc

    state.transition_task(entry["task_id"], "submitted", provider_task_id=handle.task_id)
    state.transition_task(entry["task_id"], "in_progress")

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        written = provider.download_results(handle.task_id, str(destination))
    except providers_base.ProviderTaskError as exc:
        state.transition_task(entry["task_id"], "failed", retry_reason=str(exc))
        raise GenerateImagesError(f"generate_image download failed for {purpose}/{scene_id!r}: {exc}") from exc

    local_path = Path(written[0])
    hash_sha256 = _sha256_file(local_path)
    state.transition_task(entry["task_id"], "complete", actual_cost_usd=gate_result.estimated_cost_usd)

    return {
        "model_id": model_id,
        "provider_task_id": handle.task_id,
        "local_path": str(local_path),
        "hash_sha256": hash_sha256,
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "generated_at": _now(),
    }


# ---------------------------------------------------------------------------
# P6-ANCHOR, stage 1: concept board
# ---------------------------------------------------------------------------
def run_concept_board(
    run_dir: Path,
    *,
    style_contract: Dict[str, Any],
    candidate_labels: Tuple[str, ...] = _DEFAULT_CONCEPT_LABELS,
    provider: Optional[providers_base.MediaProvider] = None,
    registry_path: Optional[str] = None,
) -> Tuple[bool, str]:
    """spec 9.3 stage 1. Idempotent: a candidate_id already present in
    anchor-approval.json's concept_candidates[] is never regenerated. Refuses
    to run once the project anchor is already locked (status='anchor_approved')."""
    state = se.ProjectState(run_dir)
    provider = provider or kie_provider.KieProvider()

    if not state.exists("project-manifest"):
        return False, "project-manifest.json does not exist yet — P1-INTAKE must run first"
    try:
        project_id = state.load("project-manifest")["project_id"]
    except se.StateEngineError as exc:
        return False, f"project-manifest.json failed to load/validate: {exc}"

    now = _now()
    if state.exists("anchor-approval"):
        try:
            data = state.load("anchor-approval")
        except se.StateEngineError as exc:
            return False, f"anchor-approval.json failed to load/validate: {exc}"
        if data["status"] == "anchor_approved":
            return False, (
                "anchor-approval.json is already status='anchor_approved' — refusing to regenerate the "
                "concept board once the project anchor is locked (spec 9.3)"
            )
    else:
        data = {
            "schema_version": "1.0.0",
            "project_id": project_id,
            "status": "proposed",
            "style_contract": style_contract,
            "concept_candidates": [],
            "approved_candidate_id": None,
            "final_anchor": None,
            "approved_by": None,
            "approved_at": None,
            "created_at": now,
            "updated_at": now,
        }

    try:
        registry = providers_base.ModelRegistry(registry_path or providers_base.DEFAULT_REGISTRY_PATH)
        model_entry = registry.resolve_default(_CONCEPT_TIER, require_priced=False)
    except providers_base.ModelRegistryError as exc:
        return False, f"model registry could not resolve capability_tier {_CONCEPT_TIER!r}: {exc}"
    model_id = model_entry["model_id"]

    existing_ids = {c["candidate_id"] for c in data["concept_candidates"]}
    generated = 0
    for i, label in enumerate(candidate_labels):
        candidate_id = f"concept-{i + 1:02d}"
        if candidate_id in existing_ids:
            continue

        destination = _media_dir(run_dir) / "anchor" / f"{candidate_id}.png"
        try:
            asset = _paid_image_call(
                run_dir,
                state,
                provider,
                model_id=model_id,
                prompt=_concept_prompt(style_contract, label),
                aspect_ratio=_DEFAULT_ASPECT_RATIO,
                resolution=_DEFAULT_CONCEPT_RESOLUTION,
                negative_prompt=style_contract.get("negative_prompt"),
                purpose="concept_candidate",
                scene_id=None,
                destination=destination,
                registry_path=registry_path,
            )
        except (PaidGateBlocked, GenerateImagesError) as exc:
            # Persist whatever succeeded before this failure — never lose a
            # completed paid call to an unsaved in-memory dict (restart safety).
            data["updated_at"] = _now()
            state.save("anchor-approval", data)
            return False, str(exc)

        asset["candidate_id"] = candidate_id
        data["concept_candidates"].append(asset)
        existing_ids.add(candidate_id)
        generated += 1
        data["updated_at"] = _now()
        try:
            state.save("anchor-approval", data)
        except se.SchemaValidationFailed as exc:
            return False, f"anchor-approval.json failed schema validation on write: {exc}"

    return True, (
        f"concept board: {len(data['concept_candidates'])} candidate(s) on file "
        f"({generated} newly generated this run)"
    )


def approve_concept_candidate(run_dir: Path, candidate_id: str, *, approved_by: str) -> Tuple[bool, str]:
    """spec 9.3 stage 1 approval event. Records the audit entry in
    project-manifest.approvals[] (kind='anchor_concept') in the same locked
    transaction that mutates anchor-approval.json's approved_candidate_id."""
    state = se.ProjectState(run_dir)
    if not approved_by or not approved_by.strip():
        return False, "approved_by must be a non-empty identity label"

    with state.lock():
        if not state.exists("anchor-approval"):
            return False, "anchor-approval.json does not exist yet — run_concept_board must run first"
        data = state.load("anchor-approval")
        if data["status"] == "anchor_approved":
            return False, "anchor-approval.json is already locked (status='anchor_approved')"
        ids = {c["candidate_id"] for c in data["concept_candidates"]}
        if candidate_id not in ids:
            return False, f"candidate_id {candidate_id!r} not found among concept_candidates {sorted(ids)!r}"

        now = _now()
        data["approved_candidate_id"] = candidate_id
        data["status"] = "concept_approved"
        data["updated_at"] = now
        state.save("anchor-approval", data)

        manifest = state.load("project-manifest")
        manifest["approvals"].append(
            {"kind": "anchor_concept", "approved_by": approved_by, "approved_at": now, "candidate_id": candidate_id}
        )
        manifest["updated_at"] = now
        state.save("project-manifest", manifest)

    return True, f"concept candidate {candidate_id!r} approved by {approved_by!r}"


# ---------------------------------------------------------------------------
# P6-ANCHOR, stage 2: final production-quality anchor
# ---------------------------------------------------------------------------
def generate_final_anchor(
    run_dir: Path,
    *,
    provider: Optional[providers_base.MediaProvider] = None,
    registry_path: Optional[str] = None,
) -> Tuple[bool, str]:
    """spec 9.3 stage 2. Idempotent: refuses to regenerate once final_anchor
    is already populated (a caller who wants a redo must go through
    run_concept_board again for a NEW candidate, never silently overwrite an
    existing production anchor)."""
    state = se.ProjectState(run_dir)
    provider = provider or kie_provider.KieProvider()

    if not state.exists("anchor-approval"):
        return False, "anchor-approval.json does not exist yet"
    data = state.load("anchor-approval")
    if data["final_anchor"] is not None:
        # Idempotent short-circuit checked FIRST: once a final anchor exists
        # (whether still status='concept_approved' or already locked to
        # 'anchor_approved' by approve_final_anchor), a re-run must always
        # report "already generated" rather than a misleading precondition
        # error about the status having since moved past 'concept_approved'.
        return True, "final_anchor already generated for this project — skipping (idempotent)"
    if data["status"] != "concept_approved":
        return False, (
            f"anchor-approval.status={data['status']!r} — a concept candidate must be approved "
            "(status='concept_approved', see approve_concept_candidate) before the final production "
            "anchor can be generated"
        )

    try:
        registry = providers_base.ModelRegistry(registry_path or providers_base.DEFAULT_REGISTRY_PATH)
        model_entry = registry.resolve_default(_PRODUCTION_TIER, require_priced=False)
    except providers_base.ModelRegistryError as exc:
        return False, f"model registry could not resolve capability_tier {_PRODUCTION_TIER!r}: {exc}"
    model_id = model_entry["model_id"]

    chosen = next(c for c in data["concept_candidates"] if c["candidate_id"] == data["approved_candidate_id"])
    try:
        reference_url = provider.upload_asset(
            providers_base.AssetUploadRequest(path=chosen["local_path"], purpose="approved_concept_reference")
        )
    except providers_base.ProviderTaskError as exc:
        return False, f"failed to upload the approved concept candidate as a reference image: {exc}"

    destination = _media_dir(run_dir) / "anchor" / "final-anchor.png"
    try:
        asset = _paid_image_call(
            run_dir,
            state,
            provider,
            model_id=model_id,
            prompt=_final_anchor_prompt(data["style_contract"]),
            aspect_ratio=_DEFAULT_ASPECT_RATIO,
            resolution=_DEFAULT_PRODUCTION_RESOLUTION,
            reference_image_urls=(reference_url,),
            negative_prompt=data["style_contract"].get("negative_prompt"),
            purpose="final_anchor",
            scene_id=None,
            destination=destination,
            registry_path=registry_path,
        )
    except (PaidGateBlocked, GenerateImagesError) as exc:
        return False, str(exc)

    data["final_anchor"] = asset
    data["updated_at"] = _now()
    try:
        state.save("anchor-approval", data)
    except se.SchemaValidationFailed as exc:
        return False, f"anchor-approval.json failed schema validation on write: {exc}"

    return True, f"final_anchor generated: hash_sha256={asset['hash_sha256'][:12]}…"


def approve_final_anchor(run_dir: Path, *, approved_by: str) -> Tuple[bool, str]:
    """Locks anchor-approval.json (status='anchor_approved') and records the
    audit entry (kind='anchor_final'). Idempotent: re-calling once already
    locked is a no-op success, never a re-approval."""
    state = se.ProjectState(run_dir)
    if not approved_by or not approved_by.strip():
        return False, "approved_by must be a non-empty identity label"

    with state.lock():
        if not state.exists("anchor-approval"):
            return False, "anchor-approval.json does not exist yet"
        data = state.load("anchor-approval")
        if data["final_anchor"] is None:
            return False, "final_anchor has not been generated yet — run generate_final_anchor first"
        if data["status"] == "anchor_approved":
            return True, "anchor-approval.json is already status='anchor_approved' (idempotent)"

        now = _now()
        data["status"] = "anchor_approved"
        data["approved_by"] = approved_by
        data["approved_at"] = now
        data["updated_at"] = now
        state.save("anchor-approval", data)

        manifest = state.load("project-manifest")
        manifest["approvals"].append(
            {
                "kind": "anchor_final",
                "approved_by": approved_by,
                "approved_at": now,
                "hash_sha256": data["final_anchor"]["hash_sha256"],
            }
        )
        manifest["updated_at"] = now
        state.save("project-manifest", manifest)

    return True, f"final anchor approved by {approved_by!r} (hash_sha256={data['final_anchor']['hash_sha256'][:12]}…)"


# ---------------------------------------------------------------------------
# P7-STILLS
# ---------------------------------------------------------------------------
def generate_scene_stills(
    run_dir: Path,
    *,
    scene_ids: Optional[Tuple[str, ...]] = None,
    provider: Optional[providers_base.MediaProvider] = None,
    registry_path: Optional[str] = None,
) -> Tuple[bool, str]:
    """spec 9.2/9.4. Refuses to run until the project anchor is approved
    (spec 9.3: 'No full scene or video batch may begin until the final
    anchor is approved and its asset hash recorded'). For every target
    scene, generates (idempotently, by deterministic asset_id) an
    anchor_still referencing the project anchor, then a first_frame_still /
    last_frame_still pair referencing that SCENE's own anchor_still — never
    the project anchor directly — so the boundary pins stay visually locked
    to this scene's specific composition."""
    state = se.ProjectState(run_dir)
    provider = provider or kie_provider.KieProvider()

    if not state.exists("anchor-approval"):
        return False, "anchor-approval.json does not exist yet — P6-ANCHOR must run first"
    anchor = state.load("anchor-approval")
    if anchor["status"] != "anchor_approved" or anchor["final_anchor"] is None:
        return False, (
            f"anchor-approval.status={anchor['status']!r} — P7-STILLS may not begin until the project "
            "anchor is approved and its hash recorded (spec 9.3)"
        )

    if not state.exists("scene-plan"):
        return False, "journey/scene-plan.json does not exist yet — P4-JOURNEY must run first"
    scene_plan = state.load("scene-plan")

    try:
        registry = providers_base.ModelRegistry(registry_path or providers_base.DEFAULT_REGISTRY_PATH)
        model_entry = registry.resolve_default(_PRODUCTION_TIER, require_priced=False)
    except providers_base.ModelRegistryError as exc:
        return False, f"model registry could not resolve capability_tier {_PRODUCTION_TIER!r}: {exc}"
    model_id = model_entry["model_id"]

    target_scenes = scene_plan["scenes"]
    if scene_ids is not None:
        wanted = set(scene_ids)
        target_scenes = [s for s in target_scenes if s["scene_id"] in wanted]
        if not target_scenes:
            return False, f"no scenes in scene-plan.json matched scene_ids={sorted(wanted)!r}"

    now = _now()
    if state.exists("asset-ledger"):
        ledger = state.load("asset-ledger")
    else:
        ledger = {
            "schema_version": "1.0.0",
            "project_id": scene_plan["project_id"],
            "assets": [],
            "created_at": now,
            "updated_at": now,
        }
    existing_ids = {a["asset_id"] for a in ledger["assets"]}

    anchor_reference_url: Optional[str] = None
    style_contract = anchor["style_contract"]
    generated = 0

    for scene in target_scenes:
        scene_id = scene["scene_id"]
        scene_reference_url: Optional[str] = None
        for purpose in _SCENE_STILL_PURPOSES:
            asset_id = f"{scene_id}:{purpose}"
            if asset_id in existing_ids:
                continue  # idempotent restart-safety: never regenerate an already-recorded asset

            if purpose == "anchor_still":
                if anchor_reference_url is None:
                    try:
                        anchor_reference_url = provider.upload_asset(
                            providers_base.AssetUploadRequest(
                                path=anchor["final_anchor"]["local_path"], purpose="project_anchor_reference"
                            )
                        )
                    except providers_base.ProviderTaskError as exc:
                        ledger["updated_at"] = _now()
                        state.save("asset-ledger", ledger)
                        return False, f"failed to upload the approved project anchor as a reference image: {exc}"
                prompt = _scene_anchor_prompt(style_contract, scene)
                reference_urls: Tuple[str, ...] = (anchor_reference_url,)
            else:
                if scene_reference_url is None:
                    scene_anchor_asset = next(
                        (a for a in ledger["assets"] if a["asset_id"] == f"{scene_id}:anchor_still"), None
                    )
                    if scene_anchor_asset is None:
                        ledger["updated_at"] = _now()
                        state.save("asset-ledger", ledger)
                        return False, (
                            f"scene {scene_id!r}: anchor_still must exist in the ledger before its "
                            "first_frame_still/last_frame_still can be generated"
                        )
                    try:
                        scene_reference_url = provider.upload_asset(
                            providers_base.AssetUploadRequest(
                                path=scene_anchor_asset["local_path"], purpose="scene_anchor_reference"
                            )
                        )
                    except providers_base.ProviderTaskError as exc:
                        ledger["updated_at"] = _now()
                        state.save("asset-ledger", ledger)
                        return False, f"scene {scene_id!r}: failed to upload its anchor_still as a reference image: {exc}"
                prompt = _scene_boundary_prompt(style_contract, scene, purpose)
                reference_urls = (scene_reference_url,)

            destination = _media_dir(run_dir) / "scenes" / scene_id / f"{purpose}.png"
            try:
                asset = _paid_image_call(
                    run_dir,
                    state,
                    provider,
                    model_id=model_id,
                    prompt=prompt,
                    aspect_ratio=_DEFAULT_ASPECT_RATIO,
                    resolution=_DEFAULT_PRODUCTION_RESOLUTION,
                    reference_image_urls=reference_urls,
                    negative_prompt=style_contract.get("negative_prompt"),
                    purpose=purpose,
                    scene_id=scene_id,
                    destination=destination,
                    registry_path=registry_path,
                )
            except (PaidGateBlocked, GenerateImagesError) as exc:
                ledger["updated_at"] = _now()
                state.save("asset-ledger", ledger)
                return False, str(exc)

            asset["asset_id"] = asset_id
            asset["scene_id"] = scene_id
            asset["purpose"] = purpose
            asset["approval_status"] = "proposed"
            ledger["assets"].append(asset)
            existing_ids.add(asset_id)
            generated += 1
            ledger["updated_at"] = _now()
            try:
                state.save("asset-ledger", ledger)
            except se.SchemaValidationFailed as exc:
                return False, f"asset-ledger.json failed schema validation on write: {exc}"

    return True, (
        f"scene stills: {len(ledger['assets'])} asset(s) on file across {len(target_scenes)} scene(s) "
        f"({generated} newly generated this run)"
    )


def approve_scene_stills(
    run_dir: Path,
    *,
    approved_by: str,
    scene_ids: Optional[Tuple[str, ...]] = None,
) -> Tuple[bool, str]:
    """Approves generated scene stills (approval_status='approved' in
    asset-ledger.json) and mirrors each fully-approved scene's anchor_still
    hash into journey/scene-plan.json's scenes[].anchor_asset_hash /
    approval_status='anchor_approved' — the mechanical enforcement point
    scene-plan.schema.json's docstring names for spec 9.3."""
    state = se.ProjectState(run_dir)
    if not approved_by or not approved_by.strip():
        return False, "approved_by must be a non-empty identity label"
    if not state.exists("asset-ledger"):
        return False, "asset-ledger.json does not exist yet — generate_scene_stills must run first"
    if not state.exists("scene-plan"):
        return False, "journey/scene-plan.json does not exist yet"

    ledger = state.load("asset-ledger")
    scene_plan = state.load("scene-plan")

    all_scene_ids = {s["scene_id"] for s in scene_plan["scenes"]}
    wanted_scene_ids = set(scene_ids) if scene_ids is not None else all_scene_ids
    if not any(a["scene_id"] in wanted_scene_ids for a in ledger["assets"]):
        return False, f"asset-ledger.json has no assets for scene_ids={sorted(wanted_scene_ids)!r}"

    now = _now()
    approved_count = 0
    for asset in ledger["assets"]:
        if asset["scene_id"] not in wanted_scene_ids:
            continue
        if asset["approval_status"] == "approved":
            continue
        asset["approval_status"] = "approved"
        approved_count += 1
    ledger["updated_at"] = now

    scenes_by_id = {s["scene_id"]: s for s in scene_plan["scenes"]}
    approved_scene_count = 0
    for scene_id in wanted_scene_ids:
        anchor_still = next(
            (a for a in ledger["assets"] if a["scene_id"] == scene_id and a["purpose"] == "anchor_still"), None
        )
        if anchor_still is None or anchor_still["approval_status"] != "approved":
            continue  # this scene's ledger is incomplete; leave scene-plan untouched, not a hard failure
        scene = scenes_by_id.get(scene_id)
        if scene is None:
            continue
        scene["approval_status"] = "anchor_approved"
        scene["anchor_asset_hash"] = anchor_still["hash_sha256"]
        approved_scene_count += 1
    scene_plan["updated_at"] = now

    try:
        state.save("asset-ledger", ledger)
        state.save("scene-plan", scene_plan)
    except se.SchemaValidationFailed as exc:
        return False, f"schema validation failed while saving approval state: {exc}"

    with state.lock():
        manifest = state.load("project-manifest")
        manifest["approvals"].append(
            {
                "kind": "scene_stills",
                "approved_by": approved_by,
                "approved_at": now,
                "scene_ids": sorted(wanted_scene_ids),
            }
        )
        manifest["updated_at"] = now
        state.save("project-manifest", manifest)

    return True, (
        f"approved {approved_count} asset(s) across {approved_scene_count} scene(s) "
        f"(requested scene_ids={sorted(wanted_scene_ids)!r})"
    )


# ---------------------------------------------------------------------------
# Test-support fixtures (mirrors plan_visual_journey.py's
# build_fixture_project_and_content_manifest convention: shared by this
# module's own self_test() AND tests/unit/test_generate_images.py, so
# neither drifts from what a "valid, fully-mocked P6-P7 pipeline" looks
# like). Never used by any production code path in this module.
# ---------------------------------------------------------------------------
class FixtureKieTransport:
    """A self-contained, fully offline fake KieTransport (implements the
    same duck-typed post_json/get_json/download surface as
    providers.kie.KieTransport) that answers ANY createTask/recordInfo/
    upload call deterministically from the REQUEST CONTENT itself, rather
    than a manually ordered FIFO queue — so a caller driving the full
    multi-step P6-P7 pipeline never has to hand-choreograph Kie's exact call
    order. NEVER touches the network (spec §19.2 'Kie adapter against mocked
    API fixtures'); used only by self_test() below and
    tests/unit/test_generate_images.py."""

    def post_json(self, url, *, headers, body, timeout):  # noqa: D401
        from providers.kie import HttpResponse  # local import: test-support only

        digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        if url.endswith("/createTask"):
            return HttpResponse(
                status_code=200,
                json_body={"code": 200, "msg": "success", "data": {"taskId": f"fixture-task-{digest}"}},
            )
        return HttpResponse(
            status_code=200,
            json_body={"data": {"downloadUrl": f"https://fixtures.example/uploaded-{digest}.png"}},
        )

    def get_json(self, url, *, headers, params, timeout):
        from providers.kie import HttpResponse  # local import: test-support only

        task_id = (params or {}).get("taskId", "unknown")
        result_url = f"https://fixtures.example/result-{task_id}.png"
        result_json = json.dumps({"resultUrls": [result_url]})
        return HttpResponse(
            status_code=200,
            json_body={
                "code": 200,
                "msg": "success",
                "data": {"taskId": task_id, "state": "success", "resultJson": result_json},
            },
        )

    def download(self, url, *, timeout):
        return f"FIXTURE-IMAGE-BYTES::{url}".encode("utf-8")


def build_verified_image_registry_copy(dest_dir: Path, *, source_registry_path: Optional[str] = None) -> Path:
    """TEST-SUPPORT ONLY. Writes a copy of providers/model-registry.json to
    dest_dir/model-registry-verified-images.json with price.verified flipped
    true on the two candidate models for 'concept_image'/
    'production_scene_image' (kie-gpt-image-2-text-to-image /
    kie-gpt-image-2-image-to-image) — both are genuinely unverified in the
    real registry as of this snapshot (see model-registry.json's own
    price.note), so no real end-to-end happy-path exercise of the paid-call
    chain is otherwise possible without a live Kie.ai pricing confirmation.
    NEVER touches providers/model-registry.json itself, and nothing else in
    this module calls it — used only by self_test() below and
    tests/unit/test_generate_images.py, exactly like spec §19.2's mandate to
    test 'against mocked API fixtures' extends naturally to a mocked PRICING
    fixture for an as-yet-unpriced model. Returns the path written."""
    source_path = Path(source_registry_path or providers_base.DEFAULT_REGISTRY_PATH)
    data = json.loads(source_path.read_text(encoding="utf-8"))
    for entry in data["models"]:
        if entry["model_id"] in ("kie-gpt-image-2-text-to-image", "kie-gpt-image-2-image-to-image"):
            entry["price"]["verified"] = True
            entry["price"]["note"] = (
                "TEST FIXTURE ONLY — verified flipped true for an offline self-test; NOT a real "
                "Kie.ai pricing confirmation."
            )
    dest_path = dest_dir / "model-registry-verified-images.json"
    dest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return dest_path


# ---------------------------------------------------------------------------
# Self-test — offline, temp run_dir, no network, no real KIE_API_KEY value.
# ---------------------------------------------------------------------------
def self_test() -> int:
    import shutil
    import tempfile
    from unittest.mock import patch

    import plan_visual_journey as pvj

    fails = 0

    def check(label: str, cond: bool) -> None:
        nonlocal fails
        if cond:
            print(f"  [PASS] {label}")
        else:
            print(f"  [FAIL] {label}")
            fails += 1

    tmp = Path(tempfile.mkdtemp(prefix="cwfe-generate-images-selftest-"))
    try:
        with patch.dict("os.environ", {"KIE_API_KEY": "FIXTURE-KEY"}, clear=False):
            project_manifest, content_manifest = pvj.build_fixture_project_and_content_manifest(
                tmp, project_id="proj-media-selftest", sections=["hero", "problem", "cta"]
            )
            state = se.ProjectState(tmp)
            state.transition_project_status("journey", reason="selftest: simulate P1-P3 passing")
            passed, detail = pvj.plan_visual_journey(tmp)
            check(f"fixture scene-plan.json written ({detail})", passed)

            import approve_paid_run as apr

            apr.approve(tmp, cap_usd=50.0, approved_by="selftest-operator", note="selftest cap")

            # ---- break-it: the REAL (unverified) registry correctly fails-closed ----
            style_contract = build_style_contract(visual_world="a sunlit modern studio loft")
            provider = kie_provider.KieProvider(transport=FixtureKieTransport())
            passed, detail = run_concept_board(tmp, style_contract=style_contract, provider=provider)
            check(
                f"run_concept_board fails-closed against the REAL registry's unverified gpt-image-2 "
                f"pricing ({detail})",
                not passed,
            )
            check("no anchor-approval.json was left half-written by the AF-CWFE-PAID-GATE refusal "
                  "(the very first candidate is blocked before any state mutation)",
                  not state.exists("anchor-approval") or state.load("anchor-approval")["concept_candidates"] == [])

            # ---- happy path against a TEST-ONLY verified-price registry copy ----
            verified_registry = build_verified_image_registry_copy(tmp)

            passed, detail = run_concept_board(
                tmp, style_contract=style_contract, provider=provider, registry_path=str(verified_registry)
            )
            check(f"run_concept_board PASSES against the verified test registry ({detail})", passed)
            anchor = state.load("anchor-approval")
            check("concept board produced 3 distinct candidates", len(anchor["concept_candidates"]) == 3)
            check(
                "concept candidates have distinct hashes (real per-call bytes, not a stub)",
                len({c["hash_sha256"] for c in anchor["concept_candidates"]}) == 3,
            )

            # idempotent re-run: no new candidates, no new paid calls.
            passed, detail = run_concept_board(
                tmp, style_contract=style_contract, provider=provider, registry_path=str(verified_registry)
            )
            check(f"re-running run_concept_board is idempotent (0 newly generated) ({detail})", "(0 newly generated" in detail)

            first_candidate_id = anchor["concept_candidates"][0]["candidate_id"]
            passed, detail = approve_concept_candidate(tmp, first_candidate_id, approved_by="selftest-operator")
            check(f"approve_concept_candidate passes ({detail})", passed)
            check(
                "anchor-approval.status is now 'concept_approved'",
                state.load("anchor-approval")["status"] == "concept_approved",
            )

            passed, detail = generate_final_anchor(tmp, provider=provider, registry_path=str(verified_registry))
            check(f"generate_final_anchor passes ({detail})", passed)
            check("final_anchor is populated", state.load("anchor-approval")["final_anchor"] is not None)

            passed, detail = approve_final_anchor(tmp, approved_by="selftest-operator")
            check(f"approve_final_anchor passes ({detail})", passed)
            check(
                "anchor-approval.status is now 'anchor_approved'",
                state.load("anchor-approval")["status"] == "anchor_approved",
            )
            check(
                "project-manifest.approvals[] carries a matching kind='anchor_final' audit entry",
                any(a["kind"] == "anchor_final" for a in state.load("project-manifest")["approvals"]),
            )

            # ---- break-it: scene stills refuse to start before the anchor is approved ----
            # (simulate by checking a FRESH unapproved project instead of mutating this one)

            passed, detail = generate_scene_stills(tmp, provider=provider, registry_path=str(verified_registry))
            check(f"generate_scene_stills passes once the anchor is approved ({detail})", passed)
            ledger = state.load("asset-ledger")
            check(
                "every scene has exactly 3 purposes (anchor_still, first_frame_still, last_frame_still)",
                all(
                    {a["purpose"] for a in ledger["assets"] if a["scene_id"] == s["scene_id"]}
                    == set(_SCENE_STILL_PURPOSES)
                    for s in state.load("scene-plan")["scenes"]
                ),
            )
            check(
                "3 scenes x 3 purposes = 9 assets total",
                len(ledger["assets"]) == 9,
            )

            # idempotent re-run: no new assets.
            passed, detail = generate_scene_stills(tmp, provider=provider, registry_path=str(verified_registry))
            check(f"re-running generate_scene_stills is idempotent (0 newly generated) ({detail})", "(0 newly generated" in detail)

            passed, detail = approve_scene_stills(tmp, approved_by="selftest-operator")
            check(f"approve_scene_stills passes ({detail})", passed)
            scene_plan_after = state.load("scene-plan")
            check(
                "every scene's approval_status mirrored to 'anchor_approved' in scene-plan.json",
                all(s["approval_status"] == "anchor_approved" for s in scene_plan_after["scenes"]),
            )
            check(
                "every scene's anchor_asset_hash mirrors its anchor_still hash exactly",
                all(
                    s["anchor_asset_hash"]
                    == next(a for a in ledger["assets"] if a["scene_id"] == s["scene_id"] and a["purpose"] == "anchor_still")[
                        "hash_sha256"
                    ]
                    for s in scene_plan_after["scenes"]
                ),
            )

            # ---- break-it: run_concept_board refuses once locked ----
            passed, detail = run_concept_board(tmp, style_contract=style_contract, provider=provider)
            check(f"run_concept_board refuses to run once anchor_approved ({detail})", not passed)

            # ---- break-it: generate_final_anchor is idempotent once populated ----
            passed, detail = generate_final_anchor(tmp, provider=provider, registry_path=str(verified_registry))
            check(f"generate_final_anchor is idempotent once final_anchor exists ({detail})", passed and "already generated" in detail)

        # ---- break-it: generate_scene_stills refuses before the anchor is approved (fresh project) ----
        tmp2 = Path(tempfile.mkdtemp(prefix="cwfe-generate-images-selftest2-"))
        try:
            with patch.dict("os.environ", {"KIE_API_KEY": "FIXTURE-KEY"}, clear=False):
                pvj.build_fixture_project_and_content_manifest(tmp2, project_id="proj-media-selftest-2")
                state2 = se.ProjectState(tmp2)
                state2.transition_project_status("journey", reason="selftest")
                pvj.plan_visual_journey(tmp2)
                passed, detail = generate_scene_stills(tmp2, provider=kie_provider.KieProvider(transport=FixtureKieTransport()))
                check(f"generate_scene_stills refuses before the anchor exists ({detail})", not passed)
                passed, detail = approve_final_anchor(tmp2, approved_by="selftest-operator")
                check(f"approve_final_anchor refuses before anchor-approval.json exists ({detail})", not passed)
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print(f"RESULT: FAIL — {fails} self-test check(s) failed.", file=sys.stderr)
        return 1
    print("RESULT: PASS — anchor/scene-stills generator self-test green.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Anchor image / scene still generator for the Cinematic and Web Funnel Engine "
        "(Skill 62, U11, spec Section 9.3/9.2). Not itself a manifest-declared gate — CWFE-MANIFEST.json "
        "wires P6-ANCHOR/P7-STILLS to scripts/prove_media.py, which reads what this module writes."
    )
    parser.add_argument("--run-dir", help="project run directory (required unless --self-test)")
    parser.add_argument(
        "--action",
        choices=["concept-board", "approve-concept", "final-anchor", "approve-anchor", "scene-stills", "approve-stills"],
    )
    parser.add_argument("--candidate-id", help="required for --action approve-concept")
    parser.add_argument("--approved-by", help="required for every approve-* action")
    parser.add_argument("--scene-ids", help="comma-separated scene_id filter for scene-stills/approve-stills")
    parser.add_argument(
        "--visual-world",
        default="a sunlit modern studio loft",
        help="style_contract.visual_world for --action concept-board when --style-contract-json is not given",
    )
    parser.add_argument("--style-contract-json", help="path to a JSON file containing a full style_contract object")
    parser.add_argument("--registry", default=None, help="override path to model-registry.json")
    parser.add_argument("--self-test", action="store_true", help="run the built-in offline self-test and exit")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(self_test())

    if not args.run_dir or not args.action:
        print("USAGE ERROR: --run-dir and --action are required (unless --self-test)", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    run_dir = Path(args.run_dir)
    if not run_dir.is_dir():
        print(f"USAGE ERROR: --run-dir does not exist: {run_dir}", file=sys.stderr)
        sys.exit(EXIT_USAGE)

    scene_ids = tuple(s.strip() for s in args.scene_ids.split(",") if s.strip()) if args.scene_ids else None

    if args.action == "concept-board":
        if args.style_contract_json:
            style_contract = json.loads(Path(args.style_contract_json).read_text(encoding="utf-8"))
        else:
            style_contract = build_style_contract(visual_world=args.visual_world)
        passed, detail = run_concept_board(run_dir, style_contract=style_contract, registry_path=args.registry)
    elif args.action == "approve-concept":
        if not args.candidate_id or not args.approved_by:
            print("USAGE ERROR: --action approve-concept requires --candidate-id and --approved-by", file=sys.stderr)
            sys.exit(EXIT_USAGE)
        passed, detail = approve_concept_candidate(run_dir, args.candidate_id, approved_by=args.approved_by)
    elif args.action == "final-anchor":
        passed, detail = generate_final_anchor(run_dir, registry_path=args.registry)
    elif args.action == "approve-anchor":
        if not args.approved_by:
            print("USAGE ERROR: --action approve-anchor requires --approved-by", file=sys.stderr)
            sys.exit(EXIT_USAGE)
        passed, detail = approve_final_anchor(run_dir, approved_by=args.approved_by)
    elif args.action == "scene-stills":
        passed, detail = generate_scene_stills(run_dir, scene_ids=scene_ids, registry_path=args.registry)
    else:  # approve-stills
        if not args.approved_by:
            print("USAGE ERROR: --action approve-stills requires --approved-by", file=sys.stderr)
            sys.exit(EXIT_USAGE)
        passed, detail = approve_scene_stills(run_dir, approved_by=args.approved_by, scene_ids=scene_ids)

    if passed:
        print(f"[PASS] {args.action} — {detail}")
        sys.exit(EXIT_OK)
    print(f"[FAIL] {args.action} — {detail}", file=sys.stderr)
    sys.exit(EXIT_FAIL)


if __name__ == "__main__":
    main()
