from __future__ import annotations

from typing import Any, Dict

HEAL_CAP_TRANSIENT = 3
HEAL_CAP_REGENERATE = 2
HEAL_CAP_ALT_ROUTE = 1
HEAL_CAP_REGATE = 1


def record_heal_event(state, phase_id, store, phase_data, rung, attempt, reason):
    """Record a heal event — extracted from Engine._heal_event."""
    from .state import utcnow
    phase_data.setdefault("heal_events", []).append(
        {"at": utcnow(), "rung": rung, "attempt": attempt, "reason": reason})
    store.save(state)

