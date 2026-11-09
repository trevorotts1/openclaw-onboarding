"""Typed cleanup eligibility and immediate disposal (PBB-131 / T-46).

Consumer-facing surface:

    from cleanup import evaluate, dispatch, ELIGIBLE, DEFERRED, BLOCKED, UNKNOWN
"""
from .disposal import (  # noqa: F401
    BLOCKED,
    DEFERRED,
    DISPOSITIONS,
    ELIGIBLE,
    UNKNOWN,
    CleanupAuthorityUnavailable,
    Refused,
    dispatch,
    evaluate,
    prove_absence,
    worktree_remove_command,
)

__all__ = [
    'BLOCKED',
    'DEFERRED',
    'DISPOSITIONS',
    'ELIGIBLE',
    'UNKNOWN',
    'CleanupAuthorityUnavailable',
    'Refused',
    'dispatch',
    'evaluate',
    'prove_absence',
    'worktree_remove_command',
]
