"""music package: S75-T25 duration, word-fit, lip-sync and route constraints.

Pure stdlib. No provider call, no spend, no client write.
"""
from .constraints import (  # noqa: F401
    DELIVERIES,
    DURATIONS_S,
    LIPSYNC_HARD_CAP,
    LIPSYNC_TARGET_MAX,
    LIPSYNC_TARGET_MIN,
    SPOKEN_OPENER_S,
    STYLE_IDS,
    ConstraintError,
    assert_lipsync,
    assert_route,
    assert_route_preserved,
    bind_matrix,
    canonical_route,
    check_opener,
    duration_row,
    duration_seconds,
    spoken_audio_share,
    union_duration,
    visible_lip_sync,
)
from .word_fit import (  # noqa: F401
    WordFitError,
    available_vocal_seconds,
    block_seconds,
    fit,
    style_rates,
)

__all__ = [
    "DELIVERIES", "DURATIONS_S", "LIPSYNC_HARD_CAP", "LIPSYNC_TARGET_MAX",
    "LIPSYNC_TARGET_MIN", "SPOKEN_OPENER_S", "STYLE_IDS", "ConstraintError",
    "assert_lipsync", "assert_route", "assert_route_preserved", "bind_matrix",
    "canonical_route", "check_opener", "duration_row", "duration_seconds",
    "spoken_audio_share", "union_duration", "visible_lip_sync", "WordFitError",
    "available_vocal_seconds", "block_seconds", "fit", "style_rates",
]
