"""agnes_plan: the fixed 10-second Agnes segments and the prompts for them."""
from .agnes_plan import (  # noqa: F401
    AGNES_MAX_DELIVERED_S, ALLOWANCE, CHANNELS, NO_TEXT_BLOCK, SEGMENT_S,
    TOOL_NAME, TOOL_VERSION, PlanError, closeup_prompt, lipsync_cutaways,
    need, segments, video_prompt,
)

__all__ = ["AGNES_MAX_DELIVERED_S", "ALLOWANCE", "CHANNELS", "NO_TEXT_BLOCK",
           "SEGMENT_S", "TOOL_NAME", "TOOL_VERSION", "PlanError",
           "closeup_prompt", "lipsync_cutaways", "need", "segments",
           "video_prompt"]
