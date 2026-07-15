#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""generate_videos.py — draft + final scene/connector video generator (Skill 62, U12).

Implements spec Section 9.2/9.5's draft-then-final motion pipeline (P8-DRAFT /
P9-FINAL-MEDIA) via the U5 Kie ``bytedance/seedance-1.5-pro`` adapter
(``providers/kie.py``), with TWO-IMAGE first/last frame pinning throughout
(ADR-8's ``input_urls`` contract) and ADR-9's "real encoded boundary frames
are authoritative" rule:

  P8-DRAFT (``generate_draft_clips`` / ``approve_draft_clips``):
    One lowest-cost ``draft_motion``-tier review clip per scene, pinned to
    that scene's OWN approved P7-STILLS boundary stills
    (``asset-ledger.json``'s ``first_frame_still``/``last_frame_still`` —
    generated_images.py's own docstring names these as the seed for "a LATER
    unit's video generation first-and-last-frame control for a scene's OWN
    clip"; this is that later unit). Never a connector — drafts are
    single-scene review clips only (spec 9.2). Writes
    ``draft-media-receipt.json``.

  P9-FINAL-MEDIA, stage A (``generate_final_scene_clips``):
    One production-tier clip per APPROVED-draft scene, pinned to the SAME
    scene's own boundary stills, using the model-tier already resolved onto
    that scene by ``plan_visual_journey.py`` (``scene["generation_model"]`` —
    never re-resolved independently, so a scene's draft/final motion always
    resolves through the SAME registry decision the scene plan already
    locked in). Immediately after download, the clip is run through the REAL
    U13 pipeline (``encode_scrub_media.py`` -> ``extract_boundaries.py``) so
    its actual encoded first/last frames exist on disk (ADR-9) — never a
    generated still stands in for an encoded boundary frame. Writes entries
    into ``video-asset-ledger.json`` (kind='scene_final').

  P9-FINAL-MEDIA, stage B (``generate_connector_clips``):
    For every scene whose ``scene-plan.json`` ``connector_required`` is true
    (spec 9.1/9.5 — the connector joins the PRECEDING scene into THIS one),
    generates a connector clip pinned to the REAL ENCODED boundary frames
    U13 already extracted for BOTH adjacent scenes' own
    kind='scene_final' entries — spec 12.2's exact contract: ``first_frame =
    actual last encoded frame of the previous playable clip``, ``last_frame
    = actual first encoded frame of the next playable clip``. Both adjacent
    scenes must already have a fully encoded+boundary-extracted
    kind='scene_final' entry (never falls back to a generated still for a
    connector pin — that would violate ADR-9). The connector's own clip is
    ALSO immediately encoded+boundary-extracted (spec 12.2: "After generation
    and final encoding, extract boundaries again"). Writes entries into
    ``video-asset-ledger.json`` (kind='connector').

  Approval (``approve_final_media``):
    Approves ``scene_final``/``connector`` entries touching the target
    scenes and records the ``project-manifest.approvals[]`` audit entry
    (kind='final_media').

Every paid call funnels through the ONE chokepoint ``_paid_video_call()``,
which mirrors ``generate_images.py``'s ``_paid_image_call()`` exactly: it
first evaluates AF-CWFE-PAID-GATE
(``prove_budget.evaluate_paid_call_preconditions`` — spec 10.3's eight
preconditions), then opens/tracks the call through
``scripts/state_engine.py``'s ``ProjectState`` (idempotency, budget
hard-stop, task status transitions). Nothing here ever hardcodes a Kie model
slug or price (ADR-7, ADR-8) — every model is resolved through
``providers/base.py:ModelRegistry`` by capability tier ('draft_motion' for
P8) or by the scene plan's own already-registry-resolved
``generation_model`` (for P9, both scene-final and connector clips, per
ADR-8's "all final clips in a connected chain should normally use the same
video model").

Restart-safety: every producer function checks whether its target asset (by
a deterministic id) is ALREADY recorded on disk before generating it again,
and saves its manifest kind incrementally after each successful asset —
never just once at the end of a multi-asset loop (the same restart-safety
convention ``generate_images.py`` and every other producer in this skill
uses).

BUILD+TEST AGAINST MOCKED KIE FIXTURES ONLY (spec §19.2) — this module never
makes a live network call in its own test suite; see ``FixtureKieTransport``
below, which additionally synthesizes REAL short ffmpeg-encoded clips for its
``download()`` responses so the downstream encode/boundary-extraction stage
of this module's own pipeline is exercised against genuinely decodable
media, not opaque fixture bytes (mirrors ``extract_boundaries.py``'s own
self-test composition of ``encode_scrub_media.py`` -> ``extract_boundaries.py``
against a real synthesized source).

stdlib only (``providers.kie``'s optional ``requests`` dependency is never
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
if str(_SCRIPT_DIR / "lib") not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR / "lib"))

import encode_scrub_media as esm  # noqa: E402
import extract_boundaries as eb  # noqa: E402
import media_ffmpeg as mf  # noqa: E402
import prove_budget as pbud  # noqa: E402
import state_engine as se  # noqa: E402
from providers import base as providers_base  # noqa: E402
from providers import kie as kie_provider  # noqa: E402

EXIT_OK = 0
EXIT_FAIL = 2
EXIT_USAGE = 3

# providers/model-registry.json capability_tiers this module resolves through
# for P8-DRAFT (spec 10.2 default policy). P9-FINAL-MEDIA never re-resolves a
# tier independently — it uses scene["generation_model"], the model
# plan_visual_journey.py already locked onto that scene via the
# 'final_connected_motion'/'premium_photoreal_override' tier (ADR-8).
_DRAFT_TIER = "draft_motion"
_DEFAULT_DRAFT_RESOLUTION = "480p"
_FINAL_RESOLUTION_PREFERENCE: Tuple[str, ...] = ("1080p", "720p", "480p")
_CONNECTOR_TARGET_DURATION_SECONDS = 4.0
_REQUIRED_STILL_PURPOSES = ("first_frame_still", "last_frame_still")


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _media_dir(run_dir: Path) -> Path:
    return run_dir / "media" / "video"


class GenerateVideosError(Exception):
    """Base class for every error this module raises."""


class PaidGateBlocked(GenerateVideosError):
    """A proposed paid video call was refused by AF-CWFE-PAID-GATE
    (prove_budget.evaluate_paid_call_preconditions). Carries the full
    PaidCallGateResult so a caller can inspect exactly which of the eight
    spec-10.3 preconditions failed."""

    def __init__(self, result: "pbud.PaidCallGateResult") -> None:
        self.result = result
        failed = "; ".join(f"{c.name}: {c.detail}" for c in result.failed_checks())
        super().__init__(f"AF-CWFE-PAID-GATE blocked this call: {failed}")


# ---------------------------------------------------------------------------
# Small, pure helpers
# ---------------------------------------------------------------------------
def _aspect_ratio_from_crop_rules(scene: Dict[str, Any]) -> str:
    """scene-plan.json's crop_rules.desktop is a free-text string like
    '16:9 full-bleed' (schema only requires non-empty) — the leading token is
    the aspect ratio by this skill's own producer convention
    (plan_visual_journey.py's _CROP_RULES constant), with a safe fallback."""
    desktop = (scene.get("crop_rules") or {}).get("desktop") or ""
    token = desktop.split()[0] if desktop.split() else ""
    return token or "16:9"


def _nearest_valid_duration(target: float, model_entry: Dict[str, Any]) -> int:
    """Clamp/round `target` seconds to a duration this model's registry
    entry actually supports (mirrors plan_visual_journey.py's own
    _pick_duration logic, duplicated locally rather than importing a private
    symbol across modules — same small-helper-duplication convention this
    skill already uses for _now()/_sha256_file() in every producer)."""
    limits = model_entry.get("duration_limits") or {}
    valid = limits.get("valid_values")
    if valid:
        return int(min(valid, key=lambda v: (abs(v - target), v)))
    lo, hi = limits.get("min"), limits.get("max")
    t = float(target)
    if lo is not None and t < lo:
        t = float(lo)
    if hi is not None and t > hi:
        t = float(hi)
    return int(round(t))


def _pick_final_resolution(model_entry: Dict[str, Any]) -> str:
    available = model_entry.get("output_resolutions") or []
    for pref in _FINAL_RESOLUTION_PREFERENCE:
        if pref in available:
            return pref
    return available[0] if available else "1080p"


def _style_fragment(style_contract: Dict[str, Any]) -> str:
    parts = [
        style_contract.get("visual_world", ""),
        f"{style_contract.get('realism_level', '')} realism",
        style_contract.get("lighting_logic", ""),
        style_contract.get("lens_family", ""),
        style_contract.get("composition_system", ""),
    ]
    return "; ".join(p for p in parts if p)


def _draft_scene_prompt(style_contract: Dict[str, Any], scene: Dict[str, Any]) -> str:
    camera = scene["camera"]
    return (
        f"{_style_fragment(style_contract)}; scene: {scene['visual_motif']}; "
        f"camera motion: {camera['motion_direction']} ({camera['motion_speed']}), "
        f"from {camera['start_state']} to {camera['end_state']}; "
        "LOW-COST DRAFT REVIEW clip for continuity/motion review before final render"
    )


def _final_scene_prompt(style_contract: Dict[str, Any], scene: Dict[str, Any]) -> str:
    camera = scene["camera"]
    return (
        f"{_style_fragment(style_contract)}; scene: {scene['visual_motif']}; "
        f"narrative purpose: {scene['narrative_purpose']}; "
        f"camera motion: {camera['motion_direction']} ({camera['motion_speed']}), "
        f"from {camera['start_state']} to {camera['end_state']}; "
        "PRODUCTION FINAL scroll-scrub clip — must match this scene's approved anchor/scene stills exactly"
    )


def _connector_prompt(style_contract: Dict[str, Any], from_scene: Dict[str, Any], to_scene: Dict[str, Any]) -> str:
    return (
        f"{_style_fragment(style_contract)}; seamless cinematic connector transition from "
        f"'{from_scene['visual_motif']}' into '{to_scene['visual_motif']}'; continue the exact camera "
        "motion, lighting, and material language across the hand-off — a blurred next-scene entering "
        "frame with 3D depth through the move, never a hard cut (spec 9.5)"
    )


# ---------------------------------------------------------------------------
# THE one paid-call chokepoint. Never call provider.generate_video /
# provider.download_results anywhere else in this module.
# ---------------------------------------------------------------------------
def _paid_video_call(
    run_dir: Path,
    state: se.ProjectState,
    provider: providers_base.MediaProvider,
    *,
    model_id: str,
    prompt: str,
    aspect_ratio: str,
    resolution: str,
    duration_seconds: int,
    input_urls: Tuple[str, str],
    purpose: str,
    scene_id: Optional[str],
    from_scene_id: Optional[str],
    to_scene_id: Optional[str],
    destination: Path,
    registry_path: Optional[str],
) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "purpose": purpose,
        "scene_id": scene_id,
        "from_scene_id": from_scene_id,
        "to_scene_id": to_scene_id,
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "duration_seconds": duration_seconds,
        "input_urls": list(input_urls),
    }
    gate_result = pbud.evaluate_paid_call_preconditions(
        run_dir,
        provider=provider.name,
        model_id=model_id,
        operation="generate_video",
        params=params,
        duration_seconds=float(duration_seconds),
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
            operation="generate_video",
            params=params,
            estimated_cost_usd=gate_result.estimated_cost_usd or 0.0,
            seconds=float(duration_seconds),
            resolution=resolution,
        )
    except se.StateEngineError as exc:
        # AF-CWFE-PAID-GATE's own preconditions PASSED, yet begin_task still
        # refused — expected, not a contradiction (budget SUFFICIENCY and the
        # literal idempotency insert are begin_task's own enforcement, not
        # the gate's stateless precondition check; see generate_images.py's
        # identical docstring note on this exact point).
        raise GenerateVideosError(
            f"begin_task refused this paid call for {purpose}/{scene_id or (from_scene_id, to_scene_id)!r} "
            f"even though AF-CWFE-PAID-GATE passed: {exc}"
        ) from exc

    request = providers_base.VideoGenerationRequest(
        model_id=model_id,
        prompt=prompt,
        duration_seconds=int(duration_seconds),
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        input_urls=tuple(input_urls),
    )
    try:
        handle = provider.generate_video(request)
    except providers_base.ProviderTaskError as exc:
        state.transition_task(entry["task_id"], "failed", retry_reason=str(exc))
        raise GenerateVideosError(f"generate_video submit failed for {purpose}: {exc}") from exc

    state.transition_task(entry["task_id"], "submitted", provider_task_id=handle.task_id)
    state.transition_task(entry["task_id"], "in_progress")

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        written = provider.download_results(handle.task_id, str(destination))
    except providers_base.ProviderTaskError as exc:
        state.transition_task(entry["task_id"], "failed", retry_reason=str(exc))
        raise GenerateVideosError(f"generate_video download failed for {purpose}: {exc}") from exc

    local_path = Path(written[0])
    hash_sha256 = _sha256_file(local_path)
    state.transition_task(entry["task_id"], "complete", actual_cost_usd=gate_result.estimated_cost_usd)

    return {
        "model_id": model_id,
        "provider_task_id": handle.task_id,
        "local_path": str(local_path),
        "hash_sha256": hash_sha256,
        "prompt": prompt,
        "duration_seconds": float(duration_seconds),
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "input_urls": list(input_urls),
        "generated_at": _now(),
    }


def _encode_and_extract(run_dir: Path, raw_path: Path, *, asset_id: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Runs the REAL U13 encode -> extract pipeline against a just-downloaded
    provider clip. Desktop variant only — boundary pinning needs exactly one
    authoritative encoded reference per ADR-9; the mobile derivative is a
    site-runtime concern the same encoded source feeds, not a second pin
    source. Raises mf.MediaToolingUnavailable/mf.MediaProcessingError rather
    than ever returning a partial result — never fabricates a boundary frame
    for a clip that failed to encode/extract."""
    encode_out_dir = _media_dir(run_dir) / "final" / "encoded" / asset_id
    media_receipt = esm.encode_scrub_media(raw_path, encode_out_dir, asset_id=asset_id, variant_names=["desktop"])
    variant = media_receipt["variants"][0]
    media_receipt_path = encode_out_dir / f"{asset_id}.media-processing-receipt.json"

    boundaries_out_dir = _media_dir(run_dir) / "final" / "boundaries" / asset_id
    variant_output_path = Path(variant["output_path"])
    boundary_receipt = eb.extract_boundaries(variant_output_path, boundaries_out_dir)
    boundary_receipt_path = boundaries_out_dir / f"{variant_output_path.stem}.boundary-frames.json"
    by_pos = {f["position"]: f for f in boundary_receipt["frames"]}

    encoded_entry = {
        "media_processing_receipt_path": str(media_receipt_path),
        "variant_name": variant["variant_name"],
        "output_path": variant["output_path"],
        "width": variant["width"],
        "height": variant["height"],
        "duration_seconds": variant["duration_seconds"],
        "hash_sha256": variant["hash_sha256"],
    }
    boundary_entry = {
        "boundary_frames_receipt_path": str(boundary_receipt_path),
        "first": {
            "frame_index": by_pos["first"]["frame_index"],
            "timestamp_seconds": by_pos["first"]["timestamp_seconds"],
            "output_path": by_pos["first"]["output_path"],
            "hash_sha256": by_pos["first"]["hash_sha256"],
        },
        "last": {
            "frame_index": by_pos["last"]["frame_index"],
            "timestamp_seconds": by_pos["last"]["timestamp_seconds"],
            "output_path": by_pos["last"]["output_path"],
            "hash_sha256": by_pos["last"]["hash_sha256"],
        },
    }
    return encoded_entry, boundary_entry


# ---------------------------------------------------------------------------
# P8-DRAFT
# ---------------------------------------------------------------------------
def generate_draft_clips(
    run_dir: Path,
    *,
    scene_ids: Optional[Tuple[str, ...]] = None,
    provider: Optional[providers_base.MediaProvider] = None,
    registry_path: Optional[str] = None,
) -> Tuple[bool, str]:
    """spec 9.2 P8-DRAFT. Refuses to run until P6-ANCHOR is approved and
    P7-STILLS' boundary stills for every target scene are approved (mirrors
    generate_images.generate_scene_stills' own P6-gate check style). Idempotent
    by scene_id: a producer re-run never regenerates an already-recorded draft."""
    state = se.ProjectState(run_dir)
    provider = provider or kie_provider.KieProvider()

    if not state.exists("anchor-approval"):
        return False, "anchor-approval.json does not exist yet — P6-ANCHOR must run first"
    anchor = state.load("anchor-approval")
    if anchor["status"] != "anchor_approved" or anchor["final_anchor"] is None:
        return False, (
            f"anchor-approval.status={anchor['status']!r} — P8-DRAFT may not begin until the project "
            "anchor is approved (spec 9.3)"
        )

    if not state.exists("scene-plan"):
        return False, "journey/scene-plan.json does not exist yet — P4-JOURNEY must run first"
    scene_plan = state.load("scene-plan")

    if not state.exists("asset-ledger"):
        return False, "asset-ledger.json does not exist yet — P7-STILLS must run first"
    ledger = state.load("asset-ledger")
    assets_by_scene: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for a in ledger["assets"]:
        assets_by_scene.setdefault(a["scene_id"], {})[a["purpose"]] = a

    target_scenes = scene_plan["scenes"]
    if scene_ids is not None:
        wanted = set(scene_ids)
        target_scenes = [s for s in target_scenes if s["scene_id"] in wanted]
        if not target_scenes:
            return False, f"no scenes in scene-plan.json matched scene_ids={sorted(wanted)!r}"

    try:
        registry = providers_base.ModelRegistry(registry_path or providers_base.DEFAULT_REGISTRY_PATH)
        model_entry = registry.resolve_default(_DRAFT_TIER, require_priced=False)
    except providers_base.ModelRegistryError as exc:
        return False, f"model registry could not resolve capability_tier {_DRAFT_TIER!r}: {exc}"
    model_id = model_entry["model_id"]

    now = _now()
    if state.exists("draft-media-receipt"):
        receipt = state.load("draft-media-receipt")
    else:
        receipt = {
            "schema_version": "1.0.0",
            "project_id": scene_plan["project_id"],
            "drafts": [],
            "created_at": now,
            "updated_at": now,
        }
    existing_ids = {d["scene_id"] for d in receipt["drafts"]}

    generated = 0
    for scene in target_scenes:
        scene_id = scene["scene_id"]
        if scene_id in existing_ids:
            continue

        purposes = assets_by_scene.get(scene_id, {})
        missing = [p for p in _REQUIRED_STILL_PURPOSES if p not in purposes]
        if missing:
            receipt["updated_at"] = _now()
            state.save("draft-media-receipt", receipt)
            return False, (
                f"scene {scene_id!r}: missing asset-ledger boundary still(s) {missing} — P7-STILLS must "
                "generate and approve this scene's boundary stills before draft motion may begin"
            )
        not_approved = [p for p in _REQUIRED_STILL_PURPOSES if purposes[p]["approval_status"] != "approved"]
        if not_approved:
            receipt["updated_at"] = _now()
            state.save("draft-media-receipt", receipt)
            return False, (
                f"scene {scene_id!r}: boundary still(s) {not_approved} are not yet approval_status='approved' "
                "— P7-STILLS must be approved for this scene before draft motion may begin"
            )

        try:
            first_url = provider.upload_asset(
                providers_base.AssetUploadRequest(path=purposes["first_frame_still"]["local_path"], purpose="draft_first_frame")
            )
            last_url = provider.upload_asset(
                providers_base.AssetUploadRequest(path=purposes["last_frame_still"]["local_path"], purpose="draft_last_frame")
            )
        except providers_base.ProviderTaskError as exc:
            receipt["updated_at"] = _now()
            state.save("draft-media-receipt", receipt)
            return False, f"scene {scene_id!r}: failed to upload boundary stills as frame pins: {exc}"

        duration = _nearest_valid_duration(scene["duration_seconds"], model_entry)
        aspect_ratio = _aspect_ratio_from_crop_rules(scene)
        prompt = _draft_scene_prompt(anchor["style_contract"], scene)

        destination = _media_dir(run_dir) / "drafts" / f"{scene_id}.mp4"
        try:
            asset = _paid_video_call(
                run_dir, state, provider,
                model_id=model_id, prompt=prompt, aspect_ratio=aspect_ratio,
                resolution=_DEFAULT_DRAFT_RESOLUTION, duration_seconds=duration,
                input_urls=(first_url, last_url), purpose="draft_scene",
                scene_id=scene_id, from_scene_id=None, to_scene_id=None,
                destination=destination, registry_path=registry_path,
            )
        except (PaidGateBlocked, GenerateVideosError) as exc:
            receipt["updated_at"] = _now()
            state.save("draft-media-receipt", receipt)
            return False, str(exc)

        asset["scene_id"] = scene_id
        asset["review_status"] = "proposed"
        receipt["drafts"].append(asset)
        existing_ids.add(scene_id)
        generated += 1
        receipt["updated_at"] = _now()
        try:
            state.save("draft-media-receipt", receipt)
        except se.SchemaValidationFailed as exc:
            return False, f"draft-media-receipt.json failed schema validation on write: {exc}"

    return True, (
        f"draft motion: {len(receipt['drafts'])} scene(s) on file ({generated} newly generated this run)"
    )


def approve_draft_clips(
    run_dir: Path, *, approved_by: str, scene_ids: Optional[Tuple[str, ...]] = None
) -> Tuple[bool, str]:
    """Approves draft-media-receipt.json entries (review_status='approved')
    and records the project-manifest audit entry (kind='draft_media')."""
    state = se.ProjectState(run_dir)
    if not approved_by or not approved_by.strip():
        return False, "approved_by must be a non-empty identity label"
    if not state.exists("draft-media-receipt"):
        return False, "draft-media-receipt.json does not exist yet — generate_draft_clips must run first"
    receipt = state.load("draft-media-receipt")

    wanted = set(scene_ids) if scene_ids is not None else {d["scene_id"] for d in receipt["drafts"]}
    matched = [d for d in receipt["drafts"] if d["scene_id"] in wanted]
    if not matched:
        return False, f"draft-media-receipt.json has no draft(s) for scene_ids={sorted(wanted)!r}"

    now = _now()
    approved_count = 0
    for d in matched:
        if d["review_status"] == "approved":
            continue
        d["review_status"] = "approved"
        approved_count += 1
    receipt["updated_at"] = now
    try:
        state.save("draft-media-receipt", receipt)
    except se.SchemaValidationFailed as exc:
        return False, f"draft-media-receipt.json failed schema validation on write: {exc}"

    with state.lock():
        manifest = state.load("project-manifest")
        manifest["approvals"].append(
            {"kind": "draft_media", "approved_by": approved_by, "approved_at": now, "scene_ids": sorted(wanted)}
        )
        manifest["updated_at"] = now
        state.save("project-manifest", manifest)

    return True, f"approved {approved_count} draft(s) (requested scene_ids={sorted(wanted)!r})"


# ---------------------------------------------------------------------------
# P9-FINAL-MEDIA, stage A: scene final clips
# ---------------------------------------------------------------------------
def generate_final_scene_clips(
    run_dir: Path,
    *,
    scene_ids: Optional[Tuple[str, ...]] = None,
    provider: Optional[providers_base.MediaProvider] = None,
    registry_path: Optional[str] = None,
) -> Tuple[bool, str]:
    """spec 9.2/12.1 P9-FINAL-MEDIA stage A. Refuses to run for a scene until
    that scene's P8-DRAFT entry is review_status='approved'. Uses
    scene['generation_model'] directly (never re-resolved) — the model
    plan_visual_journey.py already locked onto this scene. Immediately
    encodes+boundary-extracts the downloaded clip (ADR-9). Idempotent by
    asset_id '{scene_id}:final'."""
    state = se.ProjectState(run_dir)
    provider = provider or kie_provider.KieProvider()

    if not state.exists("draft-media-receipt"):
        return False, "draft-media-receipt.json does not exist yet — P8-DRAFT must run first"
    drafts = state.load("draft-media-receipt")
    drafts_by_scene = {d["scene_id"]: d for d in drafts["drafts"]}

    if not state.exists("scene-plan"):
        return False, "journey/scene-plan.json does not exist yet"
    scene_plan = state.load("scene-plan")

    if not state.exists("asset-ledger"):
        return False, "asset-ledger.json does not exist yet"
    ledger = state.load("asset-ledger")
    assets_by_scene: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for a in ledger["assets"]:
        assets_by_scene.setdefault(a["scene_id"], {})[a["purpose"]] = a

    if not state.exists("anchor-approval"):
        return False, "anchor-approval.json does not exist yet"
    anchor = state.load("anchor-approval")

    target_scenes = scene_plan["scenes"]
    if scene_ids is not None:
        wanted = set(scene_ids)
        target_scenes = [s for s in target_scenes if s["scene_id"] in wanted]
        if not target_scenes:
            return False, f"no scenes in scene-plan.json matched scene_ids={sorted(wanted)!r}"

    try:
        registry = providers_base.ModelRegistry(registry_path or providers_base.DEFAULT_REGISTRY_PATH)
    except providers_base.ModelRegistryError as exc:
        return False, f"model registry failed to load: {exc}"

    now = _now()
    if state.exists("video-asset-ledger"):
        vledger = state.load("video-asset-ledger")
    else:
        vledger = {
            "schema_version": "1.0.0",
            "project_id": scene_plan["project_id"],
            "assets": [],
            "created_at": now,
            "updated_at": now,
        }
    existing_ids = {a["asset_id"] for a in vledger["assets"]}

    generated = 0
    for scene in target_scenes:
        scene_id = scene["scene_id"]
        asset_id = f"{scene_id}:final"
        if asset_id in existing_ids:
            continue

        draft = drafts_by_scene.get(scene_id)
        if draft is None or draft["review_status"] != "approved":
            vledger["updated_at"] = _now()
            state.save("video-asset-ledger", vledger)
            return False, (
                f"scene {scene_id!r}: draft-media-receipt review_status must be 'approved' before final "
                "media may begin (P8-DRAFT gate) — run generate_draft_clips + approve_draft_clips first"
            )

        purposes = assets_by_scene.get(scene_id, {})
        missing = [p for p in _REQUIRED_STILL_PURPOSES if p not in purposes]
        if missing:
            vledger["updated_at"] = _now()
            state.save("video-asset-ledger", vledger)
            return False, f"scene {scene_id!r}: missing asset-ledger boundary still(s) {missing}"

        model_id = scene["generation_model"]
        try:
            model_entry = registry.get_model(model_id)
        except providers_base.ModelRegistryError as exc:
            vledger["updated_at"] = _now()
            state.save("video-asset-ledger", vledger)
            return False, f"scene {scene_id!r}: scene-plan generation_model {model_id!r} does not resolve in the registry: {exc}"

        try:
            first_url = provider.upload_asset(
                providers_base.AssetUploadRequest(path=purposes["first_frame_still"]["local_path"], purpose="final_first_frame")
            )
            last_url = provider.upload_asset(
                providers_base.AssetUploadRequest(path=purposes["last_frame_still"]["local_path"], purpose="final_last_frame")
            )
        except providers_base.ProviderTaskError as exc:
            vledger["updated_at"] = _now()
            state.save("video-asset-ledger", vledger)
            return False, f"scene {scene_id!r}: failed to upload boundary stills as frame pins: {exc}"

        duration = _nearest_valid_duration(scene["duration_seconds"], model_entry)
        aspect_ratio = _aspect_ratio_from_crop_rules(scene)
        resolution = _pick_final_resolution(model_entry)
        prompt = _final_scene_prompt(anchor["style_contract"], scene)

        raw_destination = _media_dir(run_dir) / "final" / "raw" / f"{scene_id}.mp4"
        try:
            asset = _paid_video_call(
                run_dir, state, provider,
                model_id=model_id, prompt=prompt, aspect_ratio=aspect_ratio,
                resolution=resolution, duration_seconds=duration,
                input_urls=(first_url, last_url), purpose="final_scene",
                scene_id=scene_id, from_scene_id=None, to_scene_id=None,
                destination=raw_destination, registry_path=registry_path,
            )
        except (PaidGateBlocked, GenerateVideosError) as exc:
            vledger["updated_at"] = _now()
            state.save("video-asset-ledger", vledger)
            return False, str(exc)

        try:
            encoded_entry, boundary_entry = _encode_and_extract(run_dir, Path(asset["local_path"]), asset_id=f"{scene_id}-final")
        except (mf.MediaToolingUnavailable, mf.MediaProcessingError) as exc:
            vledger["updated_at"] = _now()
            state.save("video-asset-ledger", vledger)
            return False, f"scene {scene_id!r}: encode/boundary-extraction of the downloaded final clip failed: {exc}"

        asset["asset_id"] = asset_id
        asset["kind"] = "scene_final"
        asset["scene_id"] = scene_id
        asset["from_scene_id"] = None
        asset["to_scene_id"] = None
        asset["encoded"] = encoded_entry
        asset["boundary_frames"] = boundary_entry
        asset["approval_status"] = "proposed"
        vledger["assets"].append(asset)
        existing_ids.add(asset_id)
        generated += 1
        vledger["updated_at"] = _now()
        try:
            state.save("video-asset-ledger", vledger)
        except se.SchemaValidationFailed as exc:
            return False, f"video-asset-ledger.json failed schema validation on write: {exc}"

    total_finals = len([a for a in vledger["assets"] if a["kind"] == "scene_final"])
    return True, f"final scene clips: {total_finals} on file ({generated} newly generated this run)"


# ---------------------------------------------------------------------------
# P9-FINAL-MEDIA, stage B: connector clips
# ---------------------------------------------------------------------------
def generate_connector_clips(
    run_dir: Path,
    *,
    scene_ids: Optional[Tuple[str, ...]] = None,
    provider: Optional[providers_base.MediaProvider] = None,
    registry_path: Optional[str] = None,
) -> Tuple[bool, str]:
    """spec 9.1/9.5/12.2 P9-FINAL-MEDIA stage B. `scene_ids` (when given)
    filters on the TO-scene of each connector (matching scene-plan.json's own
    convention: connector_required is a property of the scene the connector
    joins INTO, not the scene it leaves FROM). Both adjacent scenes must
    already carry a kind='scene_final' video-asset-ledger entry with
    boundary_frames populated — never falls back to a generated still for a
    connector pin (ADR-9)."""
    state = se.ProjectState(run_dir)
    provider = provider or kie_provider.KieProvider()

    if not state.exists("scene-plan"):
        return False, "journey/scene-plan.json does not exist yet"
    scene_plan = state.load("scene-plan")
    scenes = scene_plan["scenes"]

    if not state.exists("video-asset-ledger"):
        return False, "video-asset-ledger.json does not exist yet — generate_final_scene_clips must run first"
    vledger = state.load("video-asset-ledger")
    finals_by_scene = {a["scene_id"]: a for a in vledger["assets"] if a["kind"] == "scene_final"}

    if not state.exists("anchor-approval"):
        return False, "anchor-approval.json does not exist yet"
    anchor = state.load("anchor-approval")

    connector_scenes = [(i, s) for i, s in enumerate(scenes) if s.get("connector_required")]
    if scene_ids is not None:
        wanted = set(scene_ids)
        connector_scenes = [(i, s) for i, s in connector_scenes if s["scene_id"] in wanted]
        if not connector_scenes:
            return False, f"no connector-required scenes in scene-plan.json matched scene_ids={sorted(wanted)!r}"
    if not connector_scenes:
        return True, "no connector-required scenes in this scene-plan.json — nothing to generate"

    try:
        registry = providers_base.ModelRegistry(registry_path or providers_base.DEFAULT_REGISTRY_PATH)
    except providers_base.ModelRegistryError as exc:
        return False, f"model registry failed to load: {exc}"

    existing_ids = {a["asset_id"] for a in vledger["assets"]}
    generated = 0

    for i, to_scene in connector_scenes:
        to_scene_id = to_scene["scene_id"]
        if i == 0:
            # scene-plan.schema.json / plan_visual_journey.py's own invariant:
            # the first scene never carries an incoming connector. A hand-built
            # or malformed scene-plan claiming otherwise fails closed here
            # rather than indexing scenes[-1].
            return False, f"scene {to_scene_id!r} is scene-plan index 0 but connector_required=True — invalid (the first scene never has an incoming connector)"
        from_scene = scenes[i - 1]
        from_scene_id = from_scene["scene_id"]
        asset_id = f"{from_scene_id}->{to_scene_id}:connector"
        if asset_id in existing_ids:
            continue

        from_final = finals_by_scene.get(from_scene_id)
        to_final = finals_by_scene.get(to_scene_id)
        missing = [sid for sid, final in ((from_scene_id, from_final), (to_scene_id, to_final)) if final is None]
        if missing:
            vledger["updated_at"] = _now()
            state.save("video-asset-ledger", vledger)
            return False, (
                f"connector {from_scene_id!r}->{to_scene_id!r}: kind='scene_final' entry missing for "
                f"scene(s) {missing} — generate_final_scene_clips must run for both adjacent scenes first"
            )

        model_id = to_scene["generation_model"]
        try:
            model_entry = registry.get_model(model_id)
        except providers_base.ModelRegistryError as exc:
            vledger["updated_at"] = _now()
            state.save("video-asset-ledger", vledger)
            return False, f"connector {asset_id!r}: model_id {model_id!r} does not resolve in the registry: {exc}"

        try:
            # ADR-9 + spec 12.2: input_urls[0] = actual LAST encoded frame of
            # the preceding scene's own final clip; input_urls[1] = actual
            # FIRST encoded frame of the following scene's own final clip.
            first_url = provider.upload_asset(
                providers_base.AssetUploadRequest(
                    path=from_final["boundary_frames"]["last"]["output_path"], purpose="connector_first_frame"
                )
            )
            last_url = provider.upload_asset(
                providers_base.AssetUploadRequest(
                    path=to_final["boundary_frames"]["first"]["output_path"], purpose="connector_last_frame"
                )
            )
        except providers_base.ProviderTaskError as exc:
            vledger["updated_at"] = _now()
            state.save("video-asset-ledger", vledger)
            return False, f"connector {asset_id!r}: failed to upload real encoded boundary frames as pins: {exc}"

        duration = _nearest_valid_duration(_CONNECTOR_TARGET_DURATION_SECONDS, model_entry)
        aspect_ratio = _aspect_ratio_from_crop_rules(to_scene)
        resolution = _pick_final_resolution(model_entry)
        prompt = _connector_prompt(anchor["style_contract"], from_scene, to_scene)

        raw_destination = _media_dir(run_dir) / "connectors" / "raw" / f"{from_scene_id}-to-{to_scene_id}.mp4"
        try:
            asset = _paid_video_call(
                run_dir, state, provider,
                model_id=model_id, prompt=prompt, aspect_ratio=aspect_ratio,
                resolution=resolution, duration_seconds=duration,
                input_urls=(first_url, last_url), purpose="connector",
                scene_id=None, from_scene_id=from_scene_id, to_scene_id=to_scene_id,
                destination=raw_destination, registry_path=registry_path,
            )
        except (PaidGateBlocked, GenerateVideosError) as exc:
            vledger["updated_at"] = _now()
            state.save("video-asset-ledger", vledger)
            return False, str(exc)

        try:
            encoded_entry, boundary_entry = _encode_and_extract(
                run_dir, Path(asset["local_path"]), asset_id=f"{from_scene_id}-to-{to_scene_id}-connector"
            )
        except (mf.MediaToolingUnavailable, mf.MediaProcessingError) as exc:
            vledger["updated_at"] = _now()
            state.save("video-asset-ledger", vledger)
            return False, f"connector {asset_id!r}: encode/boundary-extraction of the downloaded connector clip failed: {exc}"

        asset["asset_id"] = asset_id
        asset["kind"] = "connector"
        asset["scene_id"] = None
        asset["from_scene_id"] = from_scene_id
        asset["to_scene_id"] = to_scene_id
        asset["encoded"] = encoded_entry
        asset["boundary_frames"] = boundary_entry
        asset["approval_status"] = "proposed"
        vledger["assets"].append(asset)
        existing_ids.add(asset_id)
        generated += 1
        vledger["updated_at"] = _now()
        try:
            state.save("video-asset-ledger", vledger)
        except se.SchemaValidationFailed as exc:
            return False, f"video-asset-ledger.json failed schema validation on write: {exc}"

    total_connectors = len([a for a in vledger["assets"] if a["kind"] == "connector"])
    return True, f"connector clips: {total_connectors} on file ({generated} newly generated this run)"


def approve_final_media(
    run_dir: Path, *, approved_by: str, scene_ids: Optional[Tuple[str, ...]] = None
) -> Tuple[bool, str]:
    """Approves BOTH kind='scene_final' and kind='connector' video-asset-ledger
    entries touching the target scene_ids (a connector counts if EITHER its
    from_scene_id or to_scene_id is targeted) and records the project-manifest
    audit entry (kind='final_media')."""
    state = se.ProjectState(run_dir)
    if not approved_by or not approved_by.strip():
        return False, "approved_by must be a non-empty identity label"
    if not state.exists("video-asset-ledger"):
        return False, "video-asset-ledger.json does not exist yet"
    vledger = state.load("video-asset-ledger")

    all_scene_ids = {a["scene_id"] for a in vledger["assets"] if a["kind"] == "scene_final"}
    wanted = set(scene_ids) if scene_ids is not None else all_scene_ids
    if not wanted:
        return False, "no target scene_ids resolved (video-asset-ledger.json has no scene_final assets yet)"

    def _touches(asset: Dict[str, Any]) -> bool:
        if asset["kind"] == "scene_final":
            return asset["scene_id"] in wanted
        return asset["from_scene_id"] in wanted or asset["to_scene_id"] in wanted

    matched = [a for a in vledger["assets"] if _touches(a)]
    if not matched:
        return False, f"video-asset-ledger.json has no asset(s) touching scene_ids={sorted(wanted)!r}"

    now = _now()
    approved_count = 0
    for a in matched:
        if a["approval_status"] == "approved":
            continue
        a["approval_status"] = "approved"
        approved_count += 1
    vledger["updated_at"] = now
    try:
        state.save("video-asset-ledger", vledger)
    except se.SchemaValidationFailed as exc:
        return False, f"video-asset-ledger.json failed schema validation on write: {exc}"

    with state.lock():
        manifest = state.load("project-manifest")
        manifest["approvals"].append(
            {"kind": "final_media", "approved_by": approved_by, "approved_at": now, "scene_ids": sorted(wanted)}
        )
        manifest["updated_at"] = now
        state.save("project-manifest", manifest)

    return True, f"approved {approved_count} final-media asset(s) touching scene_ids={sorted(wanted)!r}"


# ---------------------------------------------------------------------------
# Test-support fixtures — mirrors generate_images.py's FixtureKieTransport /
# build_verified_image_registry_copy convention. Never used by any
# production code path in this module.
# ---------------------------------------------------------------------------
class FixtureKieTransport:
    """A self-contained, fully offline fake KieTransport (same duck-typed
    post_json/get_json/download surface as providers.kie.KieTransport) used
    only by self_test() below and tests/unit/test_generate_videos.py. NEVER
    touches the network (spec §19.2). Unlike a purely synthetic fixture,
    ``download()`` synthesizes a REAL short H.264 clip with ffmpeg so this
    module's own encode/boundary-extraction stage is exercised against
    genuinely decodable media, not opaque bytes -- clip length is varied
    deterministically per request URL so different scenes/connectors produce
    visibly distinct downloaded content (never a hash collision across
    distinct provider tasks)."""

    def __init__(self, scratch_dir: Path) -> None:
        self._scratch_dir = Path(scratch_dir)
        self._scratch_dir.mkdir(parents=True, exist_ok=True)
        self._clip_counter = 0
        self.uploaded_file_names: List[str] = []  # test-observability only

    def post_json(self, url, *, headers, body, timeout):  # noqa: D401
        from providers.kie import HttpResponse  # local import: test-support only

        digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()[:16]
        if url.endswith("/createTask"):
            return HttpResponse(
                status_code=200,
                json_body={"code": 200, "msg": "success", "data": {"taskId": f"fixture-video-task-{digest}"}},
            )
        # upload endpoint — record the fileName so a test can assert exactly
        # which local file this call was asked to upload (e.g. that a
        # connector really pinned the two ADJACENT scenes' own boundary
        # frame PNGs, not their generated stills).
        self.uploaded_file_names.append(body.get("fileName", ""))
        return HttpResponse(
            status_code=200,
            json_body={"data": {"downloadUrl": f"https://fixtures.example/uploaded-{digest}.png"}},
        )

    def get_json(self, url, *, headers, params, timeout):
        from providers.kie import HttpResponse  # local import: test-support only

        task_id = (params or {}).get("taskId", "unknown")
        result_url = f"https://fixtures.example/result-{task_id}.mp4"
        result_json = json.dumps({"resultUrls": [result_url]})
        return HttpResponse(
            status_code=200,
            json_body={
                "code": 200, "msg": "success",
                "data": {"taskId": task_id, "state": "success", "resultJson": result_json},
            },
        )

    def download(self, url, *, timeout):
        binaries = mf.require_binaries()  # fail-closed: this fixture is REAL media, not opaque bytes
        seed = int(hashlib.sha256(url.encode("utf-8")).hexdigest()[:4], 16)
        duration = 2 + (seed % 2)  # 2s or 3s -- deterministic per url, varies across distinct tasks
        self._clip_counter += 1
        out_path = self._scratch_dir / f"fixture-clip-{self._clip_counter}-{seed}.mp4"
        cmd = [
            binaries["ffmpeg"], "-y",
            "-f", "lavfi", "-i", f"testsrc2=size=320x240:rate=10:duration={duration}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(out_path),
        ]
        proc = mf.run_cmd(cmd, label="ffmpeg-fixture-video-download")
        if proc.returncode != 0 or not out_path.exists() or out_path.stat().st_size == 0:
            raise RuntimeError(f"FixtureKieTransport could not synthesize a fixture clip: {proc.stderr[-400:]}")
        return out_path.read_bytes()


def build_verified_media_registry_copy(dest_dir: Path, *, source_registry_path: Optional[str] = None) -> Path:
    """TEST-SUPPORT ONLY. Writes a copy of providers/model-registry.json to
    dest_dir/model-registry-verified-media.json with price.verified flipped
    true (and, for Seedance, a concrete test amount set) on every model this
    module's own pipeline touches: the two gpt-image-2 image models (needed
    to drive the real P6/P7 pipeline that must precede P8/P9 in an end-to-end
    self-test) plus kie-bytedance-seedance-1.5-pro (the draft_motion /
    final_connected_motion tier this module itself calls) -- all three are
    genuinely unverified/unpriced in the real registry as of this snapshot
    (see model-registry.json's own price.note fields), so no real
    end-to-end happy-path exercise of the paid-call chain is otherwise
    possible without a live Kie.ai pricing confirmation. NEVER touches
    providers/model-registry.json itself. Mirrors
    generate_images.py's build_verified_image_registry_copy, extended to
    cover this module's own unverified model too."""
    source_path = Path(source_registry_path or providers_base.DEFAULT_REGISTRY_PATH)
    data = json.loads(source_path.read_text(encoding="utf-8"))
    for entry in data["models"]:
        if entry["model_id"] in ("kie-gpt-image-2-text-to-image", "kie-gpt-image-2-image-to-image"):
            entry["price"]["verified"] = True
            entry["price"]["note"] = (
                "TEST FIXTURE ONLY — verified flipped true for an offline self-test; NOT a real "
                "Kie.ai pricing confirmation."
            )
        if entry["model_id"] == "kie-bytedance-seedance-1.5-pro":
            entry["price"]["verified"] = True
            entry["price"]["amount"] = 0.05
            entry["price"]["note"] = (
                "TEST FIXTURE ONLY — verified/amount set for an offline self-test; NOT a real Kie.ai "
                "pricing confirmation (the real registry entry correctly has amount=null, verified=false "
                "per 07-kie-setup/kie-setup-full.md, which states pricing is not listed)."
            )
    dest_path = dest_dir / "model-registry-verified-media.json"
    dest_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return dest_path


# ---------------------------------------------------------------------------
# Self-test — offline, temp run_dir, real ffmpeg fixture clips, no network,
# no real KIE_API_KEY value.
# ---------------------------------------------------------------------------
def self_test() -> int:
    import shutil
    import tempfile
    from unittest.mock import patch

    import approve_paid_run as apr
    import generate_images as gi
    import plan_visual_journey as pvj

    fails = 0

    def check(label: str, cond: bool) -> None:
        nonlocal fails
        if cond:
            print(f"  [PASS] {label}")
        else:
            print(f"  [FAIL] {label}")
            fails += 1

    def run_full_p6_p7_pipeline(tmp: Path, transport, verified_registry: Path) -> None:
        """Drives the REAL P6-ANCHOR/P7-STILLS pipeline (generate_images.py)
        so this module's own P8/P9 self-test exercises against a genuinely
        valid upstream state, exactly like a real run would produce."""
        style_contract = gi.build_style_contract(visual_world="a sunlit modern studio loft")
        provider = kie_provider.KieProvider(transport=transport)
        passed, detail = gi.run_concept_board(tmp, style_contract=style_contract, provider=provider, registry_path=str(verified_registry))
        check(f"[setup] run_concept_board ({detail})", passed)
        anchor = se.ProjectState(tmp).load("anchor-approval")
        first_candidate_id = anchor["concept_candidates"][0]["candidate_id"]
        passed, detail = gi.approve_concept_candidate(tmp, first_candidate_id, approved_by="selftest-operator")
        check(f"[setup] approve_concept_candidate ({detail})", passed)
        passed, detail = gi.generate_final_anchor(tmp, provider=provider, registry_path=str(verified_registry))
        check(f"[setup] generate_final_anchor ({detail})", passed)
        passed, detail = gi.approve_final_anchor(tmp, approved_by="selftest-operator")
        check(f"[setup] approve_final_anchor ({detail})", passed)
        passed, detail = gi.generate_scene_stills(tmp, provider=provider, registry_path=str(verified_registry))
        check(f"[setup] generate_scene_stills ({detail})", passed)
        passed, detail = gi.approve_scene_stills(tmp, approved_by="selftest-operator")
        check(f"[setup] approve_scene_stills ({detail})", passed)

    tmp = Path(tempfile.mkdtemp(prefix="cwfe-generate-videos-selftest-"))
    scratch = tmp / "_fixture_scratch"
    try:
        with patch.dict("os.environ", {"KIE_API_KEY": "FIXTURE-KEY"}, clear=False):
            # 6 sections -> plan_visual_journey picks 'hybrid' architecture,
            # chapter_size default 3 -> exactly one connector at scene index 3
            # (matches plan_visual_journey.py's own self-test finding), so
            # this fixture exercises BOTH scene_final AND connector paths.
            project_manifest, content_manifest = pvj.build_fixture_project_and_content_manifest(
                tmp, project_id="proj-video-selftest",
                sections=["hero", "problem", "solution", "offer", "proof", "cta"],
            )
            state = se.ProjectState(tmp)
            state.transition_project_status("journey", reason="selftest: simulate P1-P3 passing")
            passed, detail = pvj.plan_visual_journey(tmp)
            check(f"[setup] fixture scene-plan.json written ({detail})", passed)
            scene_plan = state.load("scene-plan")
            check("[setup] exactly one connector-required scene (index 3)", [s["connector_required"] for s in scene_plan["scenes"]] == [False, False, False, True, False, False])

            apr.approve(tmp, cap_usd=50.0, approved_by="selftest-operator", note="selftest cap")

            verified_registry = build_verified_media_registry_copy(tmp)
            transport = FixtureKieTransport(scratch)
            provider = kie_provider.KieProvider(transport=transport)

            run_full_p6_p7_pipeline(tmp, transport, verified_registry)

            # ---- break-it: the REAL (unverified) registry fails closed ----
            passed, detail = generate_draft_clips(tmp, provider=provider)
            check(f"generate_draft_clips fails-closed against the REAL registry's unverified Seedance pricing ({detail})", not passed)
            check(
                "no draft-media-receipt.json was left half-written by the first AF-CWFE-PAID-GATE refusal",
                not state.exists("draft-media-receipt") or state.load("draft-media-receipt")["drafts"] == [],
            )

            # ---- P8-DRAFT happy path ----
            passed, detail = generate_draft_clips(tmp, provider=provider, registry_path=str(verified_registry))
            check(f"generate_draft_clips PASSES against the verified test registry ({detail})", passed)
            drafts = state.load("draft-media-receipt")
            check("6 draft clips generated (one per scene)", len(drafts["drafts"]) == 6)
            check(
                "draft clips have distinct hashes (real per-task bytes, not a stub)",
                len({d["hash_sha256"] for d in drafts["drafts"]}) >= 2,
            )
            for d in drafts["drafts"]:
                check(f"draft {d['scene_id']!r} local file exists on disk", Path(d["local_path"]).exists())

            # idempotent re-run: no new drafts, no new paid calls.
            passed, detail = generate_draft_clips(tmp, provider=provider, registry_path=str(verified_registry))
            check(f"re-running generate_draft_clips is idempotent (0 newly generated) ({detail})", "(0 newly generated" in detail)

            # ---- break-it: P9 refuses before drafts are approved ----
            passed, detail = generate_final_scene_clips(tmp, provider=provider, registry_path=str(verified_registry))
            check(f"generate_final_scene_clips refuses before drafts are approved ({detail})", not passed)

            passed, detail = approve_draft_clips(tmp, approved_by="selftest-operator")
            check(f"approve_draft_clips passes ({detail})", passed)
            check(
                "every draft's review_status is now 'approved'",
                all(d["review_status"] == "approved" for d in state.load("draft-media-receipt")["drafts"]),
            )
            check(
                "project-manifest.approvals[] carries a matching kind='draft_media' audit entry",
                any(a["kind"] == "draft_media" for a in state.load("project-manifest")["approvals"]),
            )

            # ---- P9-FINAL-MEDIA stage A: scene finals ----
            passed, detail = generate_final_scene_clips(tmp, provider=provider, registry_path=str(verified_registry))
            check(f"generate_final_scene_clips PASSES once drafts are approved ({detail})", passed)
            vledger = state.load("video-asset-ledger")
            finals = [a for a in vledger["assets"] if a["kind"] == "scene_final"]
            check("6 scene_final clips generated", len(finals) == 6)
            for f in finals:
                check(f"scene_final {f['scene_id']!r} encoded output exists", Path(f["encoded"]["output_path"]).exists())
                check(
                    f"scene_final {f['scene_id']!r} boundary_frames first != last (real distinct encoded frames)",
                    f["boundary_frames"]["first"]["hash_sha256"] != f["boundary_frames"]["last"]["hash_sha256"],
                )

            # idempotent re-run: no new finals, no new paid calls, no re-encode.
            passed, detail = generate_final_scene_clips(tmp, provider=provider, registry_path=str(verified_registry))
            check(f"re-running generate_final_scene_clips is idempotent (0 newly generated) ({detail})", "(0 newly generated" in detail)

            # ---- break-it: connector refuses if an adjacent scene_final is missing ----
            vledger_bak = json.loads(json.dumps(vledger))
            vledger_tampered = json.loads(json.dumps(vledger))
            vledger_tampered["assets"] = [a for a in vledger_tampered["assets"] if a.get("scene_id") != "scene-03-solution"]
            state.save("video-asset-ledger", vledger_tampered)
            passed, detail = generate_connector_clips(tmp, provider=provider, registry_path=str(verified_registry))
            check(f"generate_connector_clips refuses when an adjacent scene_final is missing ({detail})", not passed)
            state.save("video-asset-ledger", vledger_bak)  # restore

            # ---- P9-FINAL-MEDIA stage B: connector ----
            passed, detail = generate_connector_clips(tmp, provider=provider, registry_path=str(verified_registry))
            check(f"generate_connector_clips PASSES once both adjacent scene_final entries exist ({detail})", passed)
            vledger = state.load("video-asset-ledger")
            connectors = [a for a in vledger["assets"] if a["kind"] == "connector"]
            check("exactly 1 connector clip generated (one connector-required scene)", len(connectors) == 1)
            connector = connectors[0]
            check("connector.from_scene_id/to_scene_id are the correct adjacent pair", (connector["from_scene_id"], connector["to_scene_id"]) == ("scene-03-solution", "scene-04-offer"))
            check("connector boundary_frames first != last", connector["boundary_frames"]["first"]["hash_sha256"] != connector["boundary_frames"]["last"]["hash_sha256"])

            from_final = next(a for a in vledger["assets"] if a["kind"] == "scene_final" and a["scene_id"] == "scene-03-solution")
            to_final = next(a for a in vledger["assets"] if a["kind"] == "scene_final" and a["scene_id"] == "scene-04-offer")
            expected_first_name = Path(from_final["boundary_frames"]["last"]["output_path"]).name
            expected_last_name = Path(to_final["boundary_frames"]["first"]["output_path"]).name
            check(
                "connector's UPLOADED frame pins were the two adjacent scenes' REAL encoded boundary frames "
                "(ADR-9), not a generated still",
                expected_first_name in transport.uploaded_file_names and expected_last_name in transport.uploaded_file_names,
            )

            # idempotent re-run: no new connectors.
            passed, detail = generate_connector_clips(tmp, provider=provider, registry_path=str(verified_registry))
            check(f"re-running generate_connector_clips is idempotent (0 newly generated) ({detail})", "(0 newly generated" in detail)

            # ---- no-op path: filtering to a non-connector scene finds nothing to do ----
            passed, detail = generate_connector_clips(tmp, provider=provider, registry_path=str(verified_registry), scene_ids=("scene-01-hero",))
            check(f"generate_connector_clips scene_ids filter to a non-connector scene reports a clean no-match ({detail})", not passed)

            # ---- approve_final_media ----
            passed, detail = approve_final_media(tmp, approved_by="selftest-operator")
            check(f"approve_final_media passes ({detail})", passed)
            vledger = state.load("video-asset-ledger")
            check("every video-asset-ledger entry is now approval_status='approved'", all(a["approval_status"] == "approved" for a in vledger["assets"]))
            check(
                "project-manifest.approvals[] carries a matching kind='final_media' audit entry",
                any(a["kind"] == "final_media" for a in state.load("project-manifest")["approvals"]),
            )

            # ---- break-it: no target scene_ids resolves cleanly on a project with no finals ----
            tmp3 = Path(tempfile.mkdtemp(prefix="cwfe-generate-videos-selftest3-"))
            try:
                pvj.build_fixture_project_and_content_manifest(tmp3, project_id="proj-video-selftest-3", sections=["hero", "cta"])
                state3 = se.ProjectState(tmp3)
                state3.transition_project_status("journey", reason="selftest")
                pvj.plan_visual_journey(tmp3)
                passed, detail = generate_draft_clips(tmp3, provider=kie_provider.KieProvider(transport=FixtureKieTransport(tmp3 / "_scratch")))
                check(f"generate_draft_clips refuses before P6-ANCHOR exists ({detail})", not passed)
                passed, detail = generate_final_scene_clips(tmp3, provider=kie_provider.KieProvider(transport=FixtureKieTransport(tmp3 / "_scratch")))
                check(f"generate_final_scene_clips refuses before draft-media-receipt.json exists ({detail})", not passed)
                passed, detail = generate_connector_clips(tmp3, provider=kie_provider.KieProvider(transport=FixtureKieTransport(tmp3 / "_scratch")))
                check(f"generate_connector_clips refuses before video-asset-ledger.json exists ({detail})", not passed)
                passed, detail = approve_final_media(tmp3, approved_by="selftest-operator")
                check(f"approve_final_media refuses before video-asset-ledger.json exists ({detail})", not passed)
            finally:
                shutil.rmtree(tmp3, ignore_errors=True)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if fails:
        print(f"RESULT: FAIL — {fails} self-test check(s) failed.", file=sys.stderr)
        return 1
    print("RESULT: PASS — draft/final video generator self-test green (real ffmpeg encode+extract).")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Draft/final scene+connector video generator for the Cinematic and Web Funnel Engine "
        "(Skill 62, U12, spec Section 9.2/9.5/12.2). Not itself a manifest-declared gate — "
        "CWFE-MANIFEST.json wires P8-DRAFT/P9-FINAL-MEDIA to scripts/prove_media.py, which reads what "
        "this module writes."
    )
    parser.add_argument("--run-dir", help="project run directory (required unless --self-test)")
    parser.add_argument(
        "--action",
        choices=[
            "draft-clips", "approve-draft", "final-scene-clips", "connector-clips", "approve-final",
        ],
    )
    parser.add_argument("--approved-by", help="required for every approve-* action")
    parser.add_argument("--scene-ids", help="comma-separated scene_id filter")
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

    if args.action == "draft-clips":
        passed, detail = generate_draft_clips(run_dir, scene_ids=scene_ids, registry_path=args.registry)
    elif args.action == "approve-draft":
        if not args.approved_by:
            print("USAGE ERROR: --action approve-draft requires --approved-by", file=sys.stderr)
            sys.exit(EXIT_USAGE)
        passed, detail = approve_draft_clips(run_dir, approved_by=args.approved_by, scene_ids=scene_ids)
    elif args.action == "final-scene-clips":
        passed, detail = generate_final_scene_clips(run_dir, scene_ids=scene_ids, registry_path=args.registry)
    elif args.action == "connector-clips":
        passed, detail = generate_connector_clips(run_dir, scene_ids=scene_ids, registry_path=args.registry)
    else:  # approve-final
        if not args.approved_by:
            print("USAGE ERROR: --action approve-final requires --approved-by", file=sys.stderr)
            sys.exit(EXIT_USAGE)
        passed, detail = approve_final_media(run_dir, approved_by=args.approved_by, scene_ids=scene_ids)

    if passed:
        print(f"[PASS] {args.action} — {detail}")
        sys.exit(EXIT_OK)
    print(f"[FAIL] {args.action} — {detail}", file=sys.stderr)
    sys.exit(EXIT_FAIL)


if __name__ == "__main__":
    main()
