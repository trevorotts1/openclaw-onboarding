"""camera_shot_rules package — DEL-16 shot-planner rules (PKG-07-U2).

The rules run for music and for dialogue or narration alike: the same
vocabulary, the same checks, the same reason codes.

What ships here
---------------
``vocabulary``   the camera vocabulary every shot brief carries — framing
                 ladder (establishing wide through insert and detail),
                 angles (eye, low, high, bird's-eye, dutch), moves (static
                 through crane), lenses (24/35/50/85 mm) and the aperture
                 range from wide open to stopped down — plus the pacing
                 planning ranges. Optionally enriched by the skill's own
                 ``references/camera-vocabulary.json`` (PKG-07-U1); never by
                 anything outside the skill folder.
``brief``        ``build_shot_brief`` — one shot brief, full vocabulary
                 attached, prompt written without an f-stop number or a lens
                 word, text and logos held for post.
``rules``        ``run_rule_checks`` — every DEL-16 rule over a plan,
                 returning a reason string per violation.

CLI: ``python3 scripts/camera_shot_rules/cli.py check --plan plan.json``

Planning ranges are planning ranges, not measured standards.
"""
from __future__ import annotations

from .vocabulary import (  # noqa: F401
    SCHEMA_VERSION,
    TOOL_VERSION,
    PLANNING_RANGE_LABEL,
    SHOT_TYPES,
    ANGLES,
    CAMERA_MOVES,
    EDIT_TRANSITION_MOVES,
    LENSES_MM,
    APERTURES,
    COVERAGE_ROLES,
    CONTENT_MODES,
    DEFAULT_CLIP_SECONDS_PLANNING_RANGE,
    FRAMING_SECONDS_PLANNING_RANGE,
    MEDIUM_SHARE_PLANNING_RANGE,
    CLOSE_UP_SHARE_CAP,
    MAX_IDENTICAL_FRAMINGS_IN_A_ROW,
    LONG_VIDEO_SECONDS,
    full_vocabulary,
    missing_from,
    shipped_reference_path,
)
from .brief import build_shot_brief, BriefError  # noqa: F401
from .rules import run_rule_checks, plan_total_seconds  # noqa: F401

__all__ = [
    "SCHEMA_VERSION",
    "TOOL_VERSION",
    "PLANNING_RANGE_LABEL",
    "SHOT_TYPES",
    "ANGLES",
    "CAMERA_MOVES",
    "EDIT_TRANSITION_MOVES",
    "LENSES_MM",
    "APERTURES",
    "COVERAGE_ROLES",
    "CONTENT_MODES",
    "DEFAULT_CLIP_SECONDS_PLANNING_RANGE",
    "FRAMING_SECONDS_PLANNING_RANGE",
    "MEDIUM_SHARE_PLANNING_RANGE",
    "CLOSE_UP_SHARE_CAP",
    "MAX_IDENTICAL_FRAMINGS_IN_A_ROW",
    "LONG_VIDEO_SECONDS",
    "full_vocabulary",
    "missing_from",
    "shipped_reference_path",
    "build_shot_brief",
    "BriefError",
    "run_rule_checks",
    "plan_total_seconds",
]
