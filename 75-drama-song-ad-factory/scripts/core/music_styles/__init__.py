"""music_styles package: D18 music styles + D15 spoken-share targets.

The three styles offered on the approval card, each with its Suno style
prompt, its song-brief sound description, and the spoken-share target it
carries (D15 retarget: target 45% of runtime, hard band 40-55%, identical
for every length and every style, rap counted as spoken-style delivery;
first real singing targeted at 15% of runtime). The earlier 40-70% band and the
per-length targets are retired -- the numbers come from core/spoken_share.
stdlib only, no network, no paid calls.

Consumed by core/style_defaults (V2B-AUDIO-U5) through style_prompt().
Voice gender is not decided here: that is core/audio_c3 (V2B-AUDIO-U1).
"""
from .music_styles import (
    DELIVERIES,
    FIRST_SUNG_TARGET_PCT,
    SCHEMA_VERSION,
    SPOKEN_SHARE_MAX,
    SPOKEN_SHARE_MIN,
    SPOKEN_SHARE_TARGET,
    SECTION_HINTS,
    SOURCE_D15,
    SOURCE_D18,
    SPOKEN_STYLE_DELIVERIES,
    STYLES,
    TOOL_NAME,
    TOOL_VERSION,
    MusicStyleError,
    check_first_sung,
    check_share,
    d15_range,
    measure_share,
    refusal,
    section_hint,
    share_pct,
    spoken_target,
    spoken_targets,
    style,
    style_ids,
    style_prompt,
)

__all__ = [
    "DELIVERIES",
    "FIRST_SUNG_TARGET_PCT",
    "SCHEMA_VERSION",
    "SPOKEN_SHARE_MAX",
    "SPOKEN_SHARE_MIN",
    "SPOKEN_SHARE_TARGET",
    "SECTION_HINTS",
    "SOURCE_D15",
    "SOURCE_D18",
    "SPOKEN_STYLE_DELIVERIES",
    "STYLES",
    "TOOL_NAME",
    "TOOL_VERSION",
    "MusicStyleError",
    "check_first_sung",
    "check_share",
    "d15_range",
    "measure_share",
    "refusal",
    "section_hint",
    "share_pct",
    "spoken_target",
    "spoken_targets",
    "style",
    "style_ids",
    "style_prompt",
]
