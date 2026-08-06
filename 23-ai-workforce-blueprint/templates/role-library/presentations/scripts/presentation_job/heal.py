from __future__ import annotations

import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

from .state import utcnow, EXIT_OK, EXIT_EXECUTOR_FAILED

# FIX-21 (D21): process-group exec with cleanup — the retry rungs must not leave
# orphaned grandchildren when a regenerated/alt-route exec times out.
try:
    from process_reaper import run_with_cleanup
except ImportError:  # pragma: no cover — module ships beside presentation_job
    run_with_cleanup = None

HEAL_CAP_TRANSIENT = 3
HEAL_CAP_REGENERATE = 2
HEAL_CAP_ALT_ROUTE = 1
HEAL_CAP_REGATE = 1


def record_heal_event(state, phase_id, store, phase_data, rung, attempt, reason):
    phase_data.setdefault("heal_events", []).append(
        {"at": utcnow(), "rung": rung, "attempt": attempt, "reason": reason})
    store.save(state)


def rung2_regenerate(engine, phase, deficiency):
    # U069: route through the engine's single tokenise-first builder -- do not
    # re-derive the command here. A hand-rolled `.replace()` + shell=True in
    # this rung is exactly the bypass that let U069's original fix (in
    # phases.py._run_script_phase only) ship with a live shell-injection hole
    # in the retry path.
    ps = engine._phase_state(phase.id)
    argv = engine._build_executor_argv(phase.executor_cmd, phase.id)
    if not argv:
        return EXIT_EXECUTOR_FAILED
    for attempt in range(1, HEAL_CAP_REGENERATE + 1):
        record_heal_event(engine.state, phase.id, engine.store, ps,
                          rung=2, attempt=attempt, reason=deficiency)
        engine.report.to_requester(
            "blocked",
            f"{phase.id} artifact check failed ({deficiency}). "
            f"Regenerating -- attempt {attempt} of {HEAL_CAP_REGENERATE}.",
            phase_id=phase.id, reason=f"rung2:{deficiency}")
        if attempt < HEAL_CAP_REGENERATE:
            time.sleep(min(60, 5 * (2 ** (attempt - 1))))
        engine._checkpoint(phase.id, pending_cmd=' '.join(argv), pending_started_at=utcnow())
        try:
            budget = phase.budget_minutes * 60
            if run_with_cleanup is not None:
                r = run_with_cleanup(argv, cwd=str(engine.run_dir),
                                     timeout=budget, capture=False)
            else:
                r = subprocess.run(argv, shell=False, cwd=str(engine.run_dir),
                                   timeout=budget, capture_output=False)
            if r.returncode == 0:
                return EXIT_OK
        except (subprocess.TimeoutExpired, OSError):
            pass
    return EXIT_EXECUTOR_FAILED


def rung3_alt_route(engine, phase):
    # U069: same rule as rung2 -- tokenise via the engine builder, never a
    # local .replace() + shell=True re-derivation.
    alt_cmd = None
    for p in engine.manifest.raw.get("phases", []):
        if p.get("id") == phase.id:
            ex = p.get("executor") or {}
            alt_cmd = ex.get("alt_cmd")
            break
    if not alt_cmd:
        return EXIT_EXECUTOR_FAILED
    argv = engine._build_executor_argv(alt_cmd, phase.id)
    if not argv:
        return EXIT_EXECUTOR_FAILED
    ps = engine._phase_state(phase.id)
    for attempt in range(1, HEAL_CAP_ALT_ROUTE + 1):
        record_heal_event(engine.state, phase.id, engine.store, ps,
                          rung=3, attempt=attempt, reason="alternate route")
        try:
            budget = phase.budget_minutes * 60
            if run_with_cleanup is not None:
                r = run_with_cleanup(argv, cwd=str(engine.run_dir),
                                     timeout=budget, capture=False)
            else:
                r = subprocess.run(argv, shell=False, cwd=str(engine.run_dir),
                                   timeout=budget, capture_output=False)
            if r.returncode == 0:
                return EXIT_OK
        except (subprocess.TimeoutExpired, OSError):
            pass
        if attempt < HEAL_CAP_ALT_ROUTE:
            time.sleep(min(60, 5 * (2 ** (attempt - 1))))
    return EXIT_EXECUTOR_FAILED


def rung4_regate(engine, failed_keys):
    from .gates import Gates
    gates_obj = Gates(engine.run_dir, engine.state)
    result = {}
    for attempt in range(1, HEAL_CAP_REGATE + 1):
        ps = engine._phase_state("CLOSE")
        record_heal_event(engine.state, "CLOSE", engine.store, ps,
                          rung=4, attempt=attempt,
                          reason=f"re-evaluating gates: {', '.join(failed_keys)}")
        all_gates = gates_obj.evaluate_all()
        for k in failed_keys:
            result[k] = all_gates.get(k, {"state": "fail", "reason": "not evaluated"})
        if all(result.get(k, {}).get("state") == "pass" for k in failed_keys):
            break
        if attempt < HEAL_CAP_REGATE:
            time.sleep(min(60, 5 * (2 ** (attempt - 1))))
    return result
