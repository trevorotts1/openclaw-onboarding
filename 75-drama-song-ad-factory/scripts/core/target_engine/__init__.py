"""target_engine package: G4 steering engine (closest-of-N, grace accept,
reinforce-then-continue). One constants module: targets and GRACE_PCT come
from core/spoken_share. Stdlib only, no network, no spend."""
from .target_engine import (  # noqa: F401
    CAP,
    FLOOR,
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
    VERDICT_REGENERATE,
    TargetEngineError,
    adjustment_for,
    best,
    measure_candidate,
    normalize_metrics,
    score,
    steer,
    targets,
)

__all__ = [
    "CAP", "FLOOR", "GRACE_PCT", "MAX_ROUNDS", "MIN_CANDIDATES_PER_ROUND",
    "SPOKEN_MAX_PCT", "SPOKEN_MIN_PCT", "SPOKEN_TARGET_PCT", "TARGET",
    "VERDICT_ACCEPT", "VERDICT_ADJUST", "VERDICT_CONTINUE",
    "VERDICT_REGENERATE", "TargetEngineError", "adjustment_for", "best",
    "measure_candidate", "normalize_metrics", "score", "steer", "targets",
]
