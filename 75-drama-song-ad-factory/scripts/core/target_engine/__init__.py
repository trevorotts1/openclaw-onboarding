"""target_engine package: G4 steering engine (closest-of-N, Trevor's 5/10
band accept/flag/redo, adjust-then-REDO, never cancel). One constants
module: targets, ACCEPT_PTS/FLAG_PTS and GRACE_PCT come from
core/spoken_share. Stdlib only, no network, no spend."""
from .target_engine import (  # noqa: F401
    ACCEPT_PTS,
    BAND_ACCEPT,
    BAND_FLAG,
    BAND_REDO,
    CAP,
    FLOOR,
    FLAG_PTS,
    GRACE_PCT,
    MAX_ROUNDS,
    MIN_CANDIDATES_PER_ROUND,
    SPOKEN_MAX_PCT,
    SPOKEN_MIN_PCT,
    SPOKEN_TARGET_PCT,
    TARGET,
    VERDICT_ACCEPT,
    VERDICT_ADJUST,
    VERDICT_CONTINUE,
    VERDICT_FLAG,
    VERDICT_REDO,
    VERDICT_REGENERATE,
    TargetEngineError,
    adjustment_for,
    band_for_gap,
    best,
    measure_candidate,
    normalize_metrics,
    score,
    steer,
    targets,
)

__all__ = [
    "ACCEPT_PTS", "BAND_ACCEPT", "BAND_FLAG", "BAND_REDO", "CAP", "FLOOR",
    "FLAG_PTS", "GRACE_PCT", "MAX_ROUNDS", "MIN_CANDIDATES_PER_ROUND",
    "SPOKEN_MAX_PCT", "SPOKEN_MIN_PCT", "SPOKEN_TARGET_PCT", "TARGET",
    "VERDICT_ACCEPT", "VERDICT_ADJUST", "VERDICT_CONTINUE", "VERDICT_FLAG",
    "VERDICT_REDO", "VERDICT_REGENERATE", "TargetEngineError",
    "adjustment_for", "band_for_gap", "best", "measure_candidate",
    "normalize_metrics", "score", "steer", "targets",
]
