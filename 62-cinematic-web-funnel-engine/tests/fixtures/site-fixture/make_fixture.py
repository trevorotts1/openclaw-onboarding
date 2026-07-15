#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_fixture.py — the DETERMINISTIC fixture site spec Section 19.3 requires
("Use Playwright to test a deterministic fixture site") for build unit U15.

Materializes a complete, schema-valid P1-P10 output set (content-manifest.json
+ journey/scene-plan.json + per-scene browser media) into a caller-supplied
run_dir, using the SAME content-manifest/scene-plan schemas and the SAME
compute_content_hash()/verify_locked_manifest() functions U6/U8 already ship
— this is not a shortcut input format, it is exactly what a real P3+P4 run
would leave behind, so scripts/build_site.py exercises its real run_dir-
reading code path against it (spec 19.2 "Next.js project generation" +
19.3's "deterministic fixture site" are the same fixture here, not two
different ones).

Media is generated with `ffmpeg`'s `lavfi color` source keyed by a fixed
per-scene hex color and fixed duration/resolution/fps — no randomness, so
re-running this against an empty target directory always produces
byte-identical output (the only outside dependency is the installed ffmpeg
binary's own determinism, which is not this module's concern to control).

CLI:
    python3 make_fixture.py --run-dir /path/to/run_dir [--media-dir DIR]

Library:
    write_fixture_run_dir(run_dir: Path, media_dir: Optional[Path] = None) -> dict
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_FIXTURE_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _FIXTURE_DIR.parent.parent.parent
_SCRIPTS_DIR = _SKILL_DIR / "scripts"

if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
import resolve_content_engine as rce  # noqa: E402

SCHEMA_VERSION = "1.0.0"
PROJECT_ID = "u15-fixture-site"
SOURCE_SKILL = "62-cinematic-web-funnel-engine"
SOURCE_SKILL_VERSION = (_SKILL_DIR / "skill-version.txt").read_text(encoding="utf-8").strip()

# scene_id -> (ffmpeg lavfi color, duration_seconds). Deterministic, no RNG.
SCENES: List[Dict[str, Any]] = [
    {
        "scene_id": "hero-open",
        "page_section": "hero",
        "color": "0x1d4ed8",
        "duration_seconds": 2.0,
        "narrative_purpose": "Open on the transformation promise.",
        "conversion_purpose": "Earn attention before any ask.",
        "visual_motif": "Slow push-in on a rising horizon.",
        "camera": {
            "start_state": "wide",
            "end_state": "medium",
            "motion_direction": "push-in",
            "motion_speed": "slow",
        },
        "cta_relationship": "none",
        "generation_model": "fixture/lavfi-color",
        "generation_tier": "final-motion",
    },
    {
        "scene_id": "feature-dive",
        "page_section": "proof",
        "color": "0x059669",
        "duration_seconds": 2.0,
        "narrative_purpose": "Descend into proof and mechanism.",
        "conversion_purpose": "Build credibility before the offer.",
        "visual_motif": "Lateral dolly across a proof wall.",
        "camera": {
            "start_state": "medium",
            "end_state": "medium",
            "motion_direction": "lateral-dolly",
            "motion_speed": "medium",
        },
        "cta_relationship": "secondary",
        "generation_model": "fixture/lavfi-color",
        "generation_tier": "final-motion",
    },
    {
        "scene_id": "cta-close",
        "page_section": "cta",
        "color": "0xdc2626",
        "duration_seconds": 2.0,
        "narrative_purpose": "Resolve the journey at the offer.",
        "conversion_purpose": "Convert.",
        "visual_motif": "Settle to a static close frame.",
        "camera": {
            "start_state": "medium",
            "end_state": "close",
            "motion_direction": "settle",
            "motion_speed": "slow",
        },
        "cta_relationship": "primary",
        "generation_model": "fixture/lavfi-color",
        "generation_tier": "final-motion",
    },
]

RESOLUTION = "640x360"
FPS = 24


def _run_ffmpeg(args: List[str]) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
        check=True,
        stdin=subprocess.DEVNULL,
    )


def generate_scene_media(media_dir: Path) -> None:
    """Deterministically synthesizes one silent .mp4 + one .jpg poster per
    fixture scene using ffmpeg's lavfi `color` source — real, decodable
    media (spec 19.2 'actual FFmpeg fixture processing'), not a stub file."""
    media_dir.mkdir(parents=True, exist_ok=True)
    for scene in SCENES:
        video_path = media_dir / f"{scene['scene_id']}.mp4"
        poster_path = media_dir / f"{scene['scene_id']}.jpg"
        lavfi = f"color=c={scene['color']}:s={RESOLUTION}:d={scene['duration_seconds']}:r={FPS}"
        _run_ffmpeg(
            [
                "-f", "lavfi",
                "-i", lavfi,
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                "-an",
                str(video_path),
            ]
        )
        _run_ffmpeg(
            [
                "-f", "lavfi",
                "-i", f"color=c={scene['color']}:s={RESOLUTION}:d=1",
                "-frames:v", "1",
                str(poster_path),
            ]
        )


def _copy_fragment_path(name: str) -> str:
    path = _FIXTURE_DIR / "copy" / name
    if not path.is_file():
        raise FileNotFoundError(f"fixture copy fragment missing: {path}")
    return str(path)


def build_content_manifest() -> Dict[str, Any]:
    fields: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "project_id": PROJECT_ID,
        "methodology_source": "cinematic-native",
        "source_skill": SOURCE_SKILL,
        "source_skill_version": SOURCE_SKILL_VERSION,
        "page_profiles": [{"profile_id": "main", "sections": ["hero", "proof", "cta"]}],
        "section_order": ["hero", "proof", "cta"],
        "approved_copy_paths": [
            _copy_fragment_path("hero.fragment.html"),
            _copy_fragment_path("proof.fragment.html"),
            _copy_fragment_path("cta.fragment.html"),
        ],
        "cta_map": {
            "primary": {"label": "Book Your Strategy Call", "href": "#book"},
            "form-submit": {"label": "Request My Slot", "href": "#book"},
        },
        "offer_ledger": [
            {"offer_id": "strategy-call", "kind": "booked-call", "price_usd": 0}
        ],
        "conversion_requirements": {"form": True, "calendar": False, "payment": False},
        "claims": [
            {
                "claim": "A scroll-driven page can carry a full narrative arc.",
                "truth_source": "u15-fixture-truth-source",
            }
        ],
        "copy_qc_receipt": {"fixture": True, "reviewer": "U15 build unit fixture"},
    }
    now = "2026-07-15T00:00:00Z"
    fields["created_at"] = now
    fields["updated_at"] = now
    fields["content_hash"] = rce.compute_content_hash(fields)
    fields["locked"] = True
    ok, reason = rce.verify_locked_manifest(fields)
    if not ok:
        raise AssertionError(f"fixture content-manifest failed self-verification: {reason}")
    return fields


def build_scene_plan() -> Dict[str, Any]:
    now = "2026-07-15T00:00:00Z"
    scenes = []
    for scene in SCENES:
        scenes.append(
            {
                "scene_id": scene["scene_id"],
                "page_section": scene["page_section"],
                "narrative_purpose": scene["narrative_purpose"],
                "conversion_purpose": scene["conversion_purpose"],
                "visual_motif": scene["visual_motif"],
                "anchor_inputs": ["fixture-anchor"],
                "camera": scene["camera"],
                "duration_seconds": scene["duration_seconds"],
                "crop_rules": {"desktop": "16:9 center-crop", "mobile": "9:16 center-crop"},
                "copy_overlay_timing": [],
                "cta_relationship": scene["cta_relationship"],
                "generation_model": scene["generation_model"],
                "generation_tier": scene["generation_tier"],
                "connector_required": False,
                "expected_generation_count": 1,
                "estimated_cost_usd": 0,
                "approval_status": "anchor_approved",
                "anchor_asset_hash": "0" * 64,
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "project_id": PROJECT_ID,
        "architecture": "continuous-forward-journey",
        "scenes": scenes,
        "created_at": now,
        "updated_at": now,
    }


def write_fixture_run_dir(run_dir: Path, media_dir: Optional[Path] = None) -> Dict[str, Path]:
    """Writes content-manifest.json, journey/scene-plan.json, and generated
    scene media into run_dir (creating it if needed). Returns the paths
    written so callers (build_site.py's --fixture mode, tests) don't have to
    re-derive the layout convention."""
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "journey").mkdir(parents=True, exist_ok=True)

    content_manifest_path = run_dir / "content-manifest.json"
    scene_plan_path = run_dir / "journey" / "scene-plan.json"

    content_manifest_path.write_text(
        json.dumps(build_content_manifest(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    scene_plan_path.write_text(
        json.dumps(build_scene_plan(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    resolved_media_dir = media_dir if media_dir is not None else (run_dir / "media")
    generate_scene_media(resolved_media_dir)

    return {
        "content_manifest": content_manifest_path,
        "scene_plan": scene_plan_path,
        "media_dir": resolved_media_dir,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--media-dir", type=Path, default=None)
    args = parser.parse_args()
    paths = write_fixture_run_dir(args.run_dir, args.media_dir)
    print(json.dumps({k: str(v) for k, v in paths.items()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
