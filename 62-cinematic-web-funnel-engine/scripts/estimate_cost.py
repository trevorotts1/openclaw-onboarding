#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""estimate_cost.py — budget estimate computation (Skill 62, U7).

Implements the "cost estimate exists" leg of spec Section 10.3's paid-call
rule and the "estimated cost" per-scene field of Section 9.2's scene-plan
artifact. Turns a project's ``journey/scene-plan.json`` (produced by a later
unit's scene planner) into a full project cost FORECAST by RE-RESOLVING every
scene's declared ``generation_model`` through ``providers/base.py:ModelRegistry``
at the moment the forecast runs — a scene's own pre-recorded
``estimated_cost_usd`` is never trusted as authoritative here, because it may
have been written against an earlier registry snapshot (ADR-8: "resolve exact
current model slugs and prices from the live registry at build/run time").

Every dollar figure this module produces traces back to a
``registry_snapshot_id`` (a sha256 of the exact ``model-registry.json`` bytes
that priced it), so a downstream cost ledger or budget gate can prove exactly
which registry state produced a number — never a hardcoded slug or price
(ADR-7, ADR-8).

Nothing here calls a network API, touches a secret, or mutates project state.
Pure, side-effect-free computation over already-loaded JSON. stdlib only.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))

from providers import base as providers_base  # noqa: E402


class EstimateCostError(Exception):
    """Base class for every error this module raises."""


class UnsupportedPriceUnitError(EstimateCostError):
    """A resolved model's price.unit is not one this estimator knows how to
    convert a scene's duration/count fields into a quantity for. Fails
    closed rather than silently guessing a quantity."""


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Result shapes
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class SceneForecast:
    scene_id: str
    generation_model: str
    provider_model_slug: Optional[str]
    quantity: float
    unit: Optional[str]
    unit_price: Optional[float]
    estimated_cost_usd: Optional[float]
    verified: bool
    resolved: bool
    note: str

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class BudgetForecast:
    project_id: str
    registry_snapshot_id: str
    scenes: List[SceneForecast]
    total_estimated_usd: float
    complete: bool
    all_verified: bool
    unresolved_scene_ids: List[str]
    unverified_scene_ids: List[str]
    generated_at: str

    def to_dict(self) -> Dict[str, Any]:
        d = dataclasses.asdict(self)
        d["scenes"] = [s.to_dict() for s in self.scenes]
        return d


# ---------------------------------------------------------------------------
# Quantity conversion — the ONLY place a price unit is mapped to a scene's
# duration/count fields. A model whose price.unit this function does not
# recognize fails closed (UnsupportedPriceUnitError) rather than silently
# defaulting to a quantity of 1.
# ---------------------------------------------------------------------------


def quantity_for_unit(
    unit: Optional[str],
    *,
    duration_seconds: Optional[float] = None,
    count: Optional[int] = None,
) -> float:
    """Resolve how many priced units a request represents, given a model's
    price.unit and the caller-supplied duration/count. `count` defaults to 1
    when the unit does not need a duration (a single image/clip request);
    for `usd_per_second`, `count` multiplies the duration (e.g. an
    expected_generation_count of several clips at the same duration)."""
    n = 1 if count is None else max(int(count), 0)
    if unit == "usd_per_second":
        if duration_seconds is None:
            raise UnsupportedPriceUnitError(
                "price.unit is 'usd_per_second' but no duration_seconds was supplied"
            )
        return max(float(duration_seconds), 0.0) * n
    if unit in ("usd_per_image", "usd_per_clip"):
        return float(n)
    raise UnsupportedPriceUnitError(
        f"no quantity conversion known for price.unit {unit!r} — "
        "extend quantity_for_unit() explicitly rather than guessing"
    )


# ---------------------------------------------------------------------------
# Scene-plan -> forecast
# ---------------------------------------------------------------------------


def estimate_scene(
    scene: Dict[str, Any],
    registry: providers_base.ModelRegistry,
    *,
    resolution: Optional[str] = None,
    strict: bool = True,
) -> SceneForecast:
    """Forecast ONE scene-plan.json scene entry. Never raises for a
    resolvable-but-unpriced/unverified/unknown model — instead returns a
    SceneForecast with resolved=False/verified=False and a human-readable
    note, so a multi-scene forecast can report every scene's status instead
    of aborting on the first bad one (spec 17 "hard cases" — a malformed or
    not-yet-priced single scene must not crash the whole forecast)."""
    scene_id = scene["scene_id"]
    model_id = scene["generation_model"]
    count = int(scene.get("expected_generation_count") or 0)

    if count == 0:
        return SceneForecast(
            scene_id=scene_id,
            generation_model=model_id,
            provider_model_slug=None,
            quantity=0.0,
            unit=None,
            unit_price=None,
            estimated_cost_usd=0.0,
            verified=True,
            resolved=True,
            note="expected_generation_count is 0 — no spend forecast for this scene",
        )

    try:
        entry = registry.get_model(model_id)
    except providers_base.ModelRegistryError as exc:
        return SceneForecast(
            scene_id=scene_id,
            generation_model=model_id,
            provider_model_slug=None,
            quantity=0.0,
            unit=None,
            unit_price=None,
            estimated_cost_usd=None,
            verified=False,
            resolved=False,
            note=f"model registry lookup failed: {exc}",
        )

    unit = entry.get("price", {}).get("unit")
    try:
        quantity = quantity_for_unit(
            unit, duration_seconds=scene.get("duration_seconds"), count=count
        )
    except UnsupportedPriceUnitError as exc:
        return SceneForecast(
            scene_id=scene_id,
            generation_model=model_id,
            provider_model_slug=entry.get("provider_model_slug"),
            quantity=0.0,
            unit=unit,
            unit_price=None,
            estimated_cost_usd=None,
            verified=False,
            resolved=False,
            note=str(exc),
        )

    cost_estimate = registry.estimate(model_id, quantity, resolution=resolution, strict=strict)
    resolved = cost_estimate.estimated_total is not None
    note = cost_estimate.note or ("resolved" if resolved else "no price could be resolved")
    return SceneForecast(
        scene_id=scene_id,
        generation_model=model_id,
        provider_model_slug=cost_estimate.provider_model_slug,
        quantity=quantity,
        unit=cost_estimate.unit,
        unit_price=cost_estimate.unit_price,
        estimated_cost_usd=cost_estimate.estimated_total,
        verified=cost_estimate.verified,
        resolved=resolved,
        note=note,
    )


def estimate_scene_plan(
    scene_plan: Dict[str, Any],
    registry: providers_base.ModelRegistry,
    *,
    resolutions: Optional[Dict[str, str]] = None,
    strict: bool = True,
) -> BudgetForecast:
    """Forecast every scene in a scene-plan.json document. `resolutions` is an
    optional {scene_id: resolution} override map for models that price
    per-resolution (e.g. gpt-image-2's amount_by_resolution) — a scene with no
    entry there is estimated with resolution=None, which ModelRegistry.estimate
    only resolves automatically when exactly one resolution tier exists."""
    resolutions = resolutions or {}
    scenes: List[SceneForecast] = []
    for scene in scene_plan["scenes"]:
        forecast = estimate_scene(
            scene, registry, resolution=resolutions.get(scene["scene_id"]), strict=strict
        )
        scenes.append(forecast)

    unresolved_scene_ids = [s.scene_id for s in scenes if not s.resolved]
    unverified_scene_ids = [s.scene_id for s in scenes if s.resolved and not s.verified]
    total = round(sum(s.estimated_cost_usd for s in scenes if s.estimated_cost_usd is not None), 6)

    return BudgetForecast(
        project_id=scene_plan["project_id"],
        registry_snapshot_id=registry.snapshot_id,
        scenes=scenes,
        total_estimated_usd=total,
        complete=(len(unresolved_scene_ids) == 0),
        all_verified=(len(unresolved_scene_ids) == 0 and len(unverified_scene_ids) == 0),
        unresolved_scene_ids=unresolved_scene_ids,
        unverified_scene_ids=unverified_scene_ids,
        generated_at=_now(),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compute a registry-priced budget forecast from a scene-plan.json file."
    )
    parser.add_argument("scene_plan_path", help="path to a scene-plan.json file")
    parser.add_argument("--registry", default=None, help="override path to model-registry.json")
    parser.add_argument(
        "--allow-unverified",
        action="store_true",
        help="also price models whose registry entry has an amount but price.verified=false "
        "(informational only — the paid-call gate always requires strict/verified pricing)",
    )
    args = parser.parse_args()

    scene_plan = json.loads(Path(args.scene_plan_path).read_text(encoding="utf-8"))
    registry = providers_base.ModelRegistry(args.registry or providers_base.DEFAULT_REGISTRY_PATH)
    forecast = estimate_scene_plan(scene_plan, registry, strict=not args.allow_unverified)
    print(json.dumps(forecast.to_dict(), indent=2))
    sys.exit(0 if forecast.complete else 1)


if __name__ == "__main__":
    main()
