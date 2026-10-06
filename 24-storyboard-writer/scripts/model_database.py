#!/usr/bin/env python3
"""model_database.py - AI video model specifications

Data source: scripts/model-database.json, a DATED, NON-AUTHORITATIVE SNAPSHOT
(last verified 2024-01-15). It is used for storyboard clip-length math only.
Model policy is owned by Skill 67 (67-kie-video); the live KIE catalog and
live prices come from `kie_live_adapter.py price --model <id>` (Skill 74).
The cost_per_video / tier numbers read below are FALLBACK CONSTANTS for the
local estimate only, not a price authority.

This module loads the JSON database and exposes a small API:
- get_model(model_id)
- list_models()
- calculate_cost(model_id, total_duration_seconds)

The JSON database stores some providers as one model with multiple supported
clip durations. For ease of use from the CLI, this module expands those into
IDs like "sora-10s", "sora-15s", and "sora-25s".
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent / "model-database.json"


def _load_db() -> Dict[str, Any]:
    with DB_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _duration_key(seconds: int) -> str:
    return f"{seconds}s"


def _add_model(
    models: Dict[str, Dict[str, Any]],
    *,
    model_id: str,
    name: str,
    provider: str,
    duration_s: int,
    cost_per_video: Any,
    source_base_id: str,
) -> None:
    models[model_id] = {
        "id": model_id,
        "name": name,
        "provider": provider,
        "durations": [duration_s],
        "cost_per_video": cost_per_video,
        # create_storyboard.py expects these fields for display
        "resolution": "Varies",
        "audio": "Varies",
        "source_base_id": source_base_id,
    }


def _build_models(db: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    models: Dict[str, Dict[str, Any]] = {}

    for entry in db.get("models", []):
        base_id = entry.get("id")
        name = entry.get("name")
        provider = entry.get("provider")
        durations: List[int] = entry.get("durations") or []
        pricing: Dict[str, Any] = entry.get("pricing") or {}

        # Skip entries with no clip durations (example: upscalers).
        if not durations:
            continue

        pricing_type = pricing.get("type")

        if pricing_type == "per_video":
            cost = pricing.get("cost_per_video_usd")
            for d in durations:
                _add_model(
                    models,
                    model_id=f"{base_id}-{_duration_key(d)}",
                    name=name,
                    provider=provider,
                    duration_s=d,
                    cost_per_video=cost,
                    source_base_id=base_id,
                )

        elif pricing_type == "per_video_tiered":
            tiers: Dict[str, Any] = pricing.get("tiers") or {}
            for d in durations:
                cost = tiers.get(_duration_key(d))
                _add_model(
                    models,
                    model_id=f"{base_id}-{_duration_key(d)}",
                    name=name,
                    provider=provider,
                    duration_s=d,
                    cost_per_video=cost,
                    source_base_id=base_id,
                )

        else:
            for d in durations:
                _add_model(
                    models,
                    model_id=f"{base_id}-{_duration_key(d)}",
                    name=name,
                    provider=provider,
                    duration_s=d,
                    cost_per_video="Variable",
                    source_base_id=base_id,
                )

    # Friendly aliases used by the CLI/docs.
    def alias(new_id: str, existing_id: str) -> None:
        if existing_id in models:
            models[new_id] = {**models[existing_id], "id": new_id}

    alias("veo-3-1", "veo-8s")
    alias("kling-3", "kling-10s")
    alias("seed-dance", "seed-dance-10s")
    alias("wan-2-6", "wan-10s")

    return models


_DB = _load_db()
MODELS = _build_models(_DB)


def get_model(model_id: str) -> Optional[Dict[str, Any]]:
    return MODELS.get(model_id)


def list_models() -> List[str]:
    return sorted(MODELS.keys())


def calculate_cost(model_id: str, total_duration_seconds: int) -> Optional[Dict[str, Any]]:
    model = MODELS.get(model_id)
    if not model:
        return None

    clip_duration = model["durations"][0]
    num_clips = math.ceil(total_duration_seconds / clip_duration)

    cost_per_clip = model.get("cost_per_video", "Variable")
    if isinstance(cost_per_clip, (int, float)):
        total_cost: Any = round(num_clips * float(cost_per_clip), 2)
    else:
        total_cost = "Variable"

    return {
        "num_clips": num_clips,
        "clip_duration": clip_duration,
        "cost_per_clip": cost_per_clip,
        "total_cost": total_cost,
    }
