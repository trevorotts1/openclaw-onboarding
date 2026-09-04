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

# ---------------------------------------------------------------------------
# FIX 10 (MASTER Part 8): the heal ladder dispatches on FAILURE CLASS, not on
# rung number alone. Every block reason is classified, and the class decides
# which rungs run and how many times:
#   provider_error      -> alternate provider (one failover per phase, from the
#                          model router's ordered candidates) — the QC FIX 10
#                          proof: a forced 402 on one provider completes on the
#                          fallback, the heal ledger records route_change=true
#                          with BOTH providers, and no --resume is typed.
#   verifier_substance  -> regenerate with the verifier's message recorded as
#                          the phase's heal reason (the regeneration re-runs the
#                          same guarded executor; the notes ride the phase
#                          record as last_verifier_notes).
#   missing_input       -> regenerate too, but the reason names the missing
#                          input so the re-run producer unit re-derives it.
#   owner_decision      -> park and notify (Engine._block), never quarantine.
# Caps per MASTER spec: same route x2 (HEAL_CAP_REGENERATE), alternate model x1
# (HEAL_CAP_ALT_ROUTE), alternate provider x1 (HEAL_CAP_PROVIDER), then the
# unit quarantines with the written reason (Engine._fail_unit).
# ---------------------------------------------------------------------------
FAILURE_PROVIDER_ERROR = "provider_error"
FAILURE_VERIFIER_SUBSTANCE = "verifier_substance"
FAILURE_MISSING_INPUT = "missing_input"
FAILURE_OWNER_DECISION = "owner_decision"
FAILURE_TRANSIENT = "transient"

# HTTP/transport vocabulary that names a PROVIDER failure (the provider or its
# gateway refused, throttled, or ran out of credits) -- the class that earns
# the alternate-provider rung. Matched case-insensitively against the block
# reason text.
_PROVIDER_ERROR_MARKERS = (
    "http 402", "http 429", "http 5",
    "402", "429", "payment required", "insufficient",
    "can only afford", "quota", "rate limit",
    "connection", "timed out", "timeout", "bad gateway",
    "service unavailable", "provider", "deepseekcal",
)

# Vocabulary that names an OWNER decision (waiver / approval / gate decline) --
# these park and notify; they are never healed automatically.
_OWNER_DECISION_MARKERS = (
    "owner_skip_approval", "waiver", "waivers", "owner has",
    "owner-decision", "owner decision", "gate declined",
)

# Vocabulary that names a MISSING INPUT (an artifact another unit should have
# produced) -- the fix is to re-run the producing unit, which the regenerate
# rung does by re-executing the phase that (re)derives it.
_MISSING_INPUT_MARKERS = ("missing working/", "missing deliverables/",
                          "no artifact", "produced nothing",
                          "missing intake", "not found in working/")

# Substance-verifier vocabulary (the verifier's own notes name what failed).
_VERIFIER_MARKERS = ("substance check failed", "verifier", "verify")


def classify_failure(reason: Any) -> str:
    """FIX 10: classify one block/heal reason into a failure class.

    `reason` is usually the human-readable reason string the rungs record;
    anything non-str classifies as transient (the safe retry class). Order
    matters: owner decisions are checked first (a waiver reason that happens
    to contain the word 'missing' must still park, never auto-heal), then
    provider errors, then missing inputs, then verifier substance.
    """
    text = str(reason or "").lower()
    if not text:
        return FAILURE_TRANSIENT
    if any(m in text for m in _OWNER_DECISION_MARKERS):
        return FAILURE_OWNER_DECISION
    if any(m in text for m in _PROVIDER_ERROR_MARKERS):
        return FAILURE_PROVIDER_ERROR
    if any(m in text for m in _MISSING_INPUT_MARKERS):
        return FAILURE_MISSING_INPUT
    if any(m in text for m in _VERIFIER_MARKERS):
        return FAILURE_VERIFIER_SUBSTANCE
    return FAILURE_TRANSIENT


# Cap: ONE alternate-provider failover per phase per run (MASTER Fix 10 cap
# table: "alternate provider x1, then quarantine with the written reason").
HEAL_CAP_PROVIDER = 1


class HealLedger:
    """FIX 10: one JSONL heal ledger per run — working/heal/ladder.jsonl.

    One row per rung attempt: {at, phase, rung, attempt, class, reason,
    route_change, from_provider, to_provider, outcome}. The QC FIX 10 proof
    reads the route_change row naming BOTH providers. Appends are atomic-ish
    (single write, flush, close); every failure is swallowed -- the heal
    ledger is a VIEW, like the board; it can never block a build (Invariant 1).
    """

    def __init__(self, run_dir: Optional[Any] = None) -> None:
        self.run_dir = run_dir

    def _path(self, run_dir: Optional[Any] = None) -> Any:
        rd = run_dir or self.run_dir
        if rd is None:
            return None
        try:
            from pathlib import Path as _P
            return _P(str(rd)) / "working" / "heal" / "ladder.jsonl"
        except Exception:  # noqa: BLE001
            return None

    def append(self, run_dir: Optional[Any] = None, **row: Any) -> Optional[dict]:
        path = self._path(run_dir or self.run_dir)
        if path is None:
            return None
        try:
            row.setdefault("at", utcnow())
            import json as _json
            import os as _os
            path.parent.mkdir(parents=True, exist_ok=True)
            line = _json.dumps(row, default=str)
            with open(str(path), "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
            return row
        except Exception:  # noqa: BLE001 -- ledger is fail-soft, never fatal
            return None


def record_heal_event(state, phase_id, store, phase_data, rung, attempt, reason,
                      failure_class=None):
    phase_data.setdefault("heal_events", []).append(
        {"at": utcnow(), "rung": rung, "attempt": attempt, "reason": reason,
         "class": failure_class or classify_failure(reason)})
    store.save(state)


def rung2_provider_failover(engine, phase, reason, child_env=None):
    """FIX 10: the alternate-PROVIDER rung -- the class-dispatched ladder's
    provider_error arm (MASTER Fix 10: "provider_error -> alternate provider
    from the router", cap x1 per phase per run).

    Re-executes the SAME phase executor (the engine's single guarded argv
    builder -- U069 rule) after asking model_router.resolve_route for this
    phase's ordered candidates and picking the first eligible one whose
    provider differs from the one the dispatcher was last routed to (recorded
    by the dispatcher's model_route telemetry; falls back to the router's
    PRIMARY provider). The dispatcher's per-call routing still owns per-request
    failover when the router is in play; this rung is the ENGINE-level
    failover for phases whose executor process died on a provider refusal
    (the QC FIX 10 proof: a forced 402 on one provider completes on the
    fallback, the heal ledger shows route_change with both providers, and no
    --resume is typed).

    Returns EXIT_OK when the re-execution succeeded, else EXIT_EXECUTOR_FAILED.
    Never raises.
    """
    rc = EXIT_EXECUTOR_FAILED
    try:
        from_provider = _last_routed_provider(engine, phase.id)
        decision = None
        try:
            from . import model_router as _router
            decision = _router.resolve_route(phase.id)
        except Exception:  # noqa: BLE001 -- a broken router never blocks a run
            decision = None
        candidates = (decision or {}).get("candidates") or []

        to_provider = None
        to_model = None
        for cand in candidates:
            if not cand.get("eligible"):
                continue
            cand_provider = str(cand.get("provider") or "")
            if cand_provider and cand_provider != from_provider:
                to_provider = cand_provider
                to_model = str(cand.get("model") or cand.get("alias") or "")
                break
        if not to_provider:
            _ledger(engine, phase=phase.id, rung=2, attempt=1,
                    failure_class=FAILURE_PROVIDER_ERROR, reason=reason,
                    from_provider=from_provider, to_provider=None,
                    route_change=False, outcome="no_alternate_provider")
            return EXIT_EXECUTOR_FAILED

        argv = engine._build_executor_argv(phase.executor_cmd, phase.id)
        if not argv:
            return EXIT_EXECUTOR_FAILED
        ps = engine._phase_state(phase.id)
        record_heal_event(engine.state, phase.id, engine.store, ps,
                          rung=2, attempt=1,
                          reason=f"{reason} -- failover to {to_provider}",
                          failure_class=FAILURE_PROVIDER_ERROR)
        engine.report.to_requester(
            "blocked",
            f"{phase.id} hit a provider error ({reason}). Retrying on the "
            f"alternate provider {to_provider}"
            + (f" ({to_model})" if to_model else "") +
            f" -- 1 of {HEAL_CAP_PROVIDER} failover attempt(s). "
            "Nothing you need to do yet.",
            phase_id=phase.id, reason=f"rung2-failover:{reason}")
        engine._checkpoint(phase.id, pending_cmd=' '.join(argv),
                           pending_started_at=utcnow(),
                           last_provider=from_provider,
                           failover_provider=to_provider)
        budget = phase.budget_minutes * 60
        try:
            if run_with_cleanup is not None:
                r = run_with_cleanup(argv, cwd=str(engine.run_dir),
                                     timeout=budget, capture=False,
                                     env=child_env)
            else:
                r = subprocess.run(argv, shell=False, cwd=str(engine.run_dir),
                                   timeout=budget, capture_output=False,
                                   env=child_env)
            if r.returncode == 0:
                rc = EXIT_OK
        except (subprocess.TimeoutExpired, OSError):
            rc = EXIT_EXECUTOR_FAILED
        _ledger(engine, phase=phase.id, rung=2, attempt=1,
                failure_class=FAILURE_PROVIDER_ERROR, reason=reason,
                from_provider=from_provider, to_provider=to_provider,
                to_model=to_model, route_change=True,
                outcome=("ok" if rc == EXIT_OK else "still_failed"))
        return rc
    except Exception:  # noqa: BLE001 -- a heal rung can never crash the engine
        return EXIT_EXECUTOR_FAILED


def _last_routed_provider(engine, phase_id):
    """FIX 10 helper: the provider the dispatcher LAST routed this phase to,
    read from the run's stage-timings telemetry jsonl -- dispatcher.py's
    _emit_model_route_telemetry rows land in working/telemetry/
    stage-timings.jsonl with event="model_route" and selected_provider set.
    None when nothing routed yet -- then the failover picks the router's first
    eligible non-primary candidate."""
    try:
        import json as _json
        tel = engine.run_dir / "working" / "telemetry" / "stage-timings.jsonl"
        if not tel.is_file():
            return None
        last = None
        with open(str(tel), "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = _json.loads(line)
                except Exception:  # noqa: BLE001
                    continue
                if (row.get("phase_id") == phase_id
                        and row.get("event") == "model_route"):
                    last = row
        if last:
            return str(last.get("selected_provider") or "") or None
    except Exception:  # noqa: BLE001
        return None
    return None


def _ledger(engine, **row):
    """FIX 10 helper: append to the run's heal ladder ledger, fail-soft."""
    try:
        HealLedger().append(engine.run_dir, **row)
    except Exception:  # noqa: BLE001
        pass


def rung2_regenerate(engine, phase, deficiency, child_env=None):
    # U069: route through the engine's single tokenise-first builder -- do not
    # re-derive the command here. A hand-rolled `.replace()` + shell=True in
    # this rung is exactly the bypass that let U069's original fix (in
    # phases.py._run_script_phase only) ship with a live shell-injection hole
    # in the retry path.
    # FIX 25 (MASTER Part 8): a regenerate is the SAME front-door-guarded script
    # re-executed, so it must receive the same per-invocation env dict the first
    # attempt got (OC_DECK_ENTRY_NONCE + OC_DECK_ENTRY_NONCE_FILE pointing at
    # this phase's .nonce-<id> file). F54's env=None here made every attempt 2
    # die at the front door with AF-CANONICAL-RENDER-BYPASS.
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
                                     timeout=budget, capture=False,
                                     env=child_env)
            else:
                r = subprocess.run(argv, shell=False, cwd=str(engine.run_dir),
                                   timeout=budget, capture_output=False,
                                   env=child_env)
            if r.returncode == 0:
                return EXIT_OK
        except (subprocess.TimeoutExpired, OSError):
            pass
    return EXIT_EXECUTOR_FAILED


def rung3_alt_route(engine, phase, child_env=None):
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
    # FIX 25 (MASTER Part 8): the alternate route runs the same guarded front
    # door, so it too must carry the per-invocation nonce env dict.
    for attempt in range(1, HEAL_CAP_ALT_ROUTE + 1):
        record_heal_event(engine.state, phase.id, engine.store, ps,
                          rung=3, attempt=attempt, reason="alternate route")
        try:
            budget = phase.budget_minutes * 60
            if run_with_cleanup is not None:
                r = run_with_cleanup(argv, cwd=str(engine.run_dir),
                                     timeout=budget, capture=False,
                                     env=child_env)
            else:
                r = subprocess.run(argv, shell=False, cwd=str(engine.run_dir),
                                   timeout=budget, capture_output=False,
                                   env=child_env)
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
