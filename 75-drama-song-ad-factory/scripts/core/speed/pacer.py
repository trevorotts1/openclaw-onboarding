#!/usr/bin/env python3
"""speed.pacer: burst pacing and drip refusal over the speed rules.

Adapter module: `kie_dispatch.submit_burst` imports these names. Every
number comes from speed.py (references/speed-limits.json); nothing is
duplicated here.
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


def max_at_once():
    """The pace's requests-per-window: 20 (S-13)."""
    return _S.pacing()[0]


def is_staggered(ready_count, submitted_batches):
    """True when ready jobs were split over more than one send (N-79)."""
    ready = int(ready_count or 0)
    batches = int(submitted_batches or 0)
    return ready > 1 and batches > 1


def stagger_refusal(ready_count, submitted_batches):
    """STAGGERED_SEND for a drip, else None. One ready job is never a drip."""
    if is_staggered(ready_count, submitted_batches):
        return {"ok": False, "code": "STAGGERED_SEND",
                "detail": "%d ready jobs split over %d sends; the dispatcher "
                          "offers only one batch send up to the rate limit"
                          % (int(ready_count), int(submitted_batches))}
    return None


def order_slowest_first(jobs):
    """Slowest route first in the burst (N-97); stable, never drops a job."""
    return _S.slow_route_first(jobs)
