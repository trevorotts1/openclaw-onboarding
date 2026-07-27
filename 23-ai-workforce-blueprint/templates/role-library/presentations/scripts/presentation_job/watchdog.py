from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .state import _read_json, EXIT_OK, EXIT_STALLED
from .manifest import PHASE_BUDGET_MINUTES, DEFAULT_PHASE_BUDGET_MINUTES

# ---------------------------------------------------------------------------
# Watchdog. Stall detection is SEPARATE from error detection.
# ---------------------------------------------------------------------------
def watchdog(scan_root: Path, grace_multiplier: float = 1.5) -> int:
    stalled = []
    for state_path in scan_root.glob("*/state.json"):
        st = _read_json(state_path)
        if not st or st.get("terminal") in ("DONE", "BLOCKED"):
            continue
        hb = st.get("heartbeat") or {}
        last = hb.get("last_checkpoint_at")
        pid = hb.get("current_phase") or st.get("current_phase") or "?"
        if not last:
            continue
        try:
            age_min = (datetime.now(timezone.utc) -
                       datetime.fromisoformat(last).astimezone(timezone.utc)).total_seconds() / 60
        except ValueError:
            continue
        budget = PHASE_BUDGET_MINUTES.get(pid, DEFAULT_PHASE_BUDGET_MINUTES)
        if age_min > budget * grace_multiplier:
            stalled.append((state_path.parent, pid, round(age_min, 1), budget))
    for run_dir, pid, age, budget in stalled:
        print(f"STALLED {run_dir}: phase {pid} last checkpointed {age} min ago "
              f"(budget {budget} min)", flush=True)
    return EXIT_STALLED if stalled else EXIT_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

