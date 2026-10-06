"""storyboard_director package: QC gate before video spend + adversarial review (directive 14.1, 14.4). Stdlib only."""
from .storyboard_director import (
    CRITERIA,
    FILLER_PATTERNS,
    SCHEMA_VERSION,
    TOOL_VERSION,
    ReviewError,
    is_filler,
    adversarial_review,
    video_spend_allowed,
)

__all__ = [
    "CRITERIA", "FILLER_PATTERNS", "SCHEMA_VERSION", "TOOL_VERSION",
    "ReviewError", "is_filler", "adversarial_review", "video_spend_allowed",
]
