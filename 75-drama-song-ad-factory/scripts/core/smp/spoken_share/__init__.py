"""spoken_share package: D15 re-export of core spoken_share for scripts/core/smp/.

One implementation lives in ``core/spoken_share/spoken_share.py`` (manual L1);
this package re-exports it so ``import spoken_share`` under ``core/smp/`` keeps
resolving to the same rule (45% target, 40-55 band, every length and style,
rap counts as spoken, first sung line within about 10 seconds). Skill 74 stays
the sole KIE path. Plan measuring and verification only — no network, no
spend. stdlib only.
"""
from .spoken_share import (  # noqa: F401
    CAP,
    DELIVERIES,
    FIRST_SUNG_WITHIN_SECONDS,
    FLOOR,
    SCHEMA_VERSION,
    SOURCE,
    SPOKEN_MAX_PCT,
    SPOKEN_MIN_PCT,
    SPOKEN_STYLE_DELIVERIES,
    SPOKEN_TARGET_PCT,
    TARGET,
    TOOL_NAME,
    TOOL_VERSION,
    SpokenShareError,
    band,
    check_first_sung,
    check_plan,
    check_share,
    is_spoken_style,
    measure_share,
    plan_refusal,
    refusal,
    seconds_for,
    share_pct,
)

__all__ = [
    "CAP",
    "DELIVERIES",
    "FIRST_SUNG_WITHIN_SECONDS",
    "FLOOR",
    "SCHEMA_VERSION",
    "SOURCE",
    "SPOKEN_MAX_PCT",
    "SPOKEN_MIN_PCT",
    "SPOKEN_STYLE_DELIVERIES",
    "SPOKEN_TARGET_PCT",
    "TARGET",
    "TOOL_NAME",
    "TOOL_VERSION",
    "SpokenShareError",
    "band",
    "check_first_sung",
    "check_plan",
    "check_share",
    "is_spoken_style",
    "measure_share",
    "plan_refusal",
    "refusal",
    "seconds_for",
    "share_pct",
]
