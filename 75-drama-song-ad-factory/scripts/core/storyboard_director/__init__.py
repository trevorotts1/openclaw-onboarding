"""storyboard_director package: QC gate before video spend + adversarial review (directive 14.1, 14.4). Stdlib only.

Style Bible consumption gate (13.3): video prompts are refused at intake
unless bible.assert_compiled marks them as compiler output. See
style_bible_integration.
"""
from __future__ import annotations

from .storyboard_director import (
    CRITERIA,
    FILLER_PATTERNS,
    SCHEMA_VERSION,
    TOOL_VERSION,
    ReviewError,
    is_filler,
    adversarial_review,
    video_spend_allowed as _video_spend_allowed,
)

try:
    from style_bible_integration import StyleGateError, require_compiled
except ImportError as _e:  # imported as core.storyboard_director
    if "style_bible_integration" not in str(_e):
        raise
    from ..style_bible_integration import StyleGateError, require_compiled


def intake_video_prompt(shot_id, prompt):
    """Video prompt intake gate (13.3): compiler output only.

    Returns the prompt. Raises ReviewError UNCOMPILED_PROMPT on a
    hand-written prompt.
    """
    if not isinstance(shot_id, str) or not shot_id.strip():
        raise ReviewError("PROMPTS_INVALID",
                          "video prompt intake needs a shot_id")
    try:
        return require_compiled(prompt, "video prompt for %s" % shot_id)
    except StyleGateError as e:
        raise ReviewError("UNCOMPILED_PROMPT", str(e)) from e


def video_spend_allowed(shots, review, prompts=None):
    """14.1 spend gate with the 13.3 prompt intake: pass
    prompts={shot_id: prompt} to gate every video prompt through
    assert_compiled before the gate opens.

    prompts=None keeps the original behaviour exactly (no prompt intake).
    """
    if prompts is not None:
        if not isinstance(prompts, dict) or not prompts:
            raise ReviewError("PROMPTS_INVALID",
                              "video prompts must be a non-empty "
                              "shot_id->prompt map")
        for sid, prompt in prompts.items():
            intake_video_prompt(sid, prompt)
    return _video_spend_allowed(shots, review)


__all__ = [
    "CRITERIA", "FILLER_PATTERNS", "SCHEMA_VERSION", "TOOL_VERSION",
    "ReviewError", "is_filler", "adversarial_review", "video_spend_allowed",
    "intake_video_prompt",
]
