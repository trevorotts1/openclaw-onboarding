#!/usr/bin/env python3
"""speed.chain: the chain-child trigger over the speed rules (F-SPD-3).

A chain child submits within 60 seconds of its parent landing. On H3 a
chain is not a wait (the next shot's storyboard picture already exists),
so this is the seamless-move case plus the audit that no child dripped.
"""
from __future__ import annotations

import os as _os
import sys as _sys

_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)

try:  # packaged: speed.speed
    from . import speed as _S
except ImportError:  # run as a script
    import speed as _S  # type: ignore


def chain_child_within_s():
    limits = _S.load_limits()
    return float((limits.get("chain_child") or {})
                 .get("max_seconds_after_parent") or 60)


def child_due(parent_landed_at):
    """Deadline by which a chain child must be submitted."""
    return float(parent_landed_at or 0.0) + chain_child_within_s()


def chain_child_late(parent_landed_at, submitted_at):
    """True when a child missed its 60-second window (CHAIN_CHILD_LATE)."""
    if parent_landed_at is None or submitted_at is None:
        return False
    ok, _code = _S.chain_child_late(parent_landed_at, submitted_at)
    return not ok


def child_late_refusal(logical_key, parent_landed_at, submitted_at):
    """None or the CHAIN_CHILD_LATE refusal for a late child."""
    if not chain_child_late(parent_landed_at, submitted_at):
        return None
    return {"ok": False, "code": "CHAIN_CHILD_LATE",
            "detail": "chain child %s submitted %.0f s after its parent "
                      "landed; the window is %.0f s"
                      % (logical_key,
                         float(submitted_at) - float(parent_landed_at),
                         chain_child_within_s())}
