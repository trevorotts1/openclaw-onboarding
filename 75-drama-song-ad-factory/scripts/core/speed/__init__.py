#!/usr/bin/env python3
"""speed: the speed build's dispatch-side rules (plan 10B, 10C, 10D).

- speed.py: the pure send-and-read rules (pace, poll tiers, outlier,
  chain child, spend guard, clip length, resubmit, upload freshness,
  slow route first), reading references/speed-limits.json.
- burst.py: the one-burst run path over those rules (F-SPD-1, N-79,
  N-83, N-87, N-88, N-92, N-97).

Stdlib only, no network, no spend, no clock unless `now` is passed.
"""
from __future__ import annotations

from . import burst
from . import speed as rules

__all__ = ["burst", "rules"]

TOOL_NAME = "speed"
TOOL_VERSION = "1.0.0"
