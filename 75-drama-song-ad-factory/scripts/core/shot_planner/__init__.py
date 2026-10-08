"""shot_planner package: per-shot records bound to lyric timing (directive 14.2-14.3). Stdlib only.

Style Bible consumption gate (13.3): every shot prompt and every
image-generation prompt is refused unless bible.assert_compiled marks it
as compiler output. See style_bible_integration.
"""
from __future__ import annotations

from .shot_planner import (
    SHOT_FIELDS,
    CONTRACT_KEYS,
    PRODUCT_VISIBILITY,
    STATUSES,
    TREATMENTS,
    SCHEMA_VERSION,
    TOOL_VERSION,
    MIN_SHOT_S,
    BEAT_CUT_MIN_SHOT_S,
    PlanError,
    validate_shot,
    validate_contract,
    load_timing_map,
    plan_shot_floor,
    validate_timeline_min_shot,
    bind_plan as _bind_plan,
)

try:
    from style_bible_integration import (
        StyleGateError,
        intake_image_prompt,
        require_compiled,
    )
except ImportError as _e:  # imported as core.shot_planner
    if "style_bible_integration" not in str(_e):
        raise
    from ..style_bible_integration import (
        StyleGateError,
        intake_image_prompt,
        require_compiled,
    )


def intake_shot_prompts(prompts):
    """Shot prompt intake gate (13.3): compiler output only.

    prompts: {shot_id: prompt}. Returns the same map. Raises PlanError
    UNCOMPILED_PROMPT on the first hand-written prompt; PROMPTS_INVALID
    on a bad map shape.
    """
    if not isinstance(prompts, dict) or not prompts:
        raise PlanError("PROMPTS_INVALID",
                        "shot prompts must be a non-empty shot_id->prompt map")
    for sid, prompt in prompts.items():
        if not isinstance(sid, str) or not sid.strip():
            raise PlanError("PROMPTS_INVALID",
                            "prompt key must be a non-empty shot_id")
        try:
            require_compiled(prompt, "shot %s prompt" % sid)
        except StyleGateError as e:
            raise PlanError("UNCOMPILED_PROMPT", str(e)) from e
    return prompts


def bind_plan(shots, timing, contracts=None, prompts=None):
    """bind_plan with the 13.3 prompt intake: pass prompts={shot_id: prompt}
    to gate every shot prompt through assert_compiled before binding.

    prompts=None keeps the original behaviour exactly (no prompt intake).
    """
    if prompts is not None:
        intake_shot_prompts(prompts)
    return _bind_plan(shots, timing, contracts)


__all__ = [
    "SHOT_FIELDS", "CONTRACT_KEYS", "PRODUCT_VISIBILITY", "STATUSES",
    "TREATMENTS", "SCHEMA_VERSION", "TOOL_VERSION", "MIN_SHOT_S",
    "BEAT_CUT_MIN_SHOT_S", "PlanError",
    "validate_shot", "validate_contract", "load_timing_map", "bind_plan",
    "plan_shot_floor", "validate_timeline_min_shot",
    "intake_image_prompt", "intake_shot_prompts", "require_compiled",
]
