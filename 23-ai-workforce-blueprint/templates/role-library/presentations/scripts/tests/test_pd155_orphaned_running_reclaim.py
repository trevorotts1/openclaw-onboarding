"""PD-TEST-155 -- a phase stranded `running` by a dead engine must be reclaimable.

THE DEFECT, measured on run pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4.

`Engine._ready_queue_tick()` treats `running` as a status it neither plans nor expires:
the phase is collected into the `running` bucket and `continue`d. Only the phase's
OWN wait loop (phases.py:3438-3446) can time it out, and that loop only runs while
an engine is executing the phase. So when an engine dies mid-wait -- a crash, an
OOM, a reboot, or an operator stopping a spinning engine -- the phase stays
`running` FOREVER, `_phase_terminal_bad` does not apply to it, and every
descendant simply reports `waiting_dependency` on it.

Measured live after the PD-TEST-151 repin + `--resume`:
  * three phases (P1Q-COPY-QC, P-TYPO-QC, P4-PROMPT) left `status: running` by the
    previous engine; their dispatch ledgers all named `dispatcher-64201-...`,
    a pid that no longer existed;
  * `waited_seconds` FROZEN at 602 / 600 / 450 across minutes of sampling while
    state.json `updated_at` kept advancing;
  * ZERO provider requests for 11 minutes;
  * the engine log carried ONLY identical `phase.waiting_dependency` lines;
  * all 29 pending phases were downstream of those three.
The run was therefore UNBLOCKED (terminal None, blocked null) and yet completely
INERT. No supported verb could fix it: `--invalidate-phase` refuses a phase that
is not `done`, and `--watchdog` only reports.

Two of the three had already been judged satisfied by the dispatcher
(`.dispatch-state/<phase>.json: status="skipped_satisfied"`) with their artifacts
on disk, so reclaiming them costs nothing and lets the existing wait/verify path
finish them.

WHAT THESE TESTS PIN
  * a `running` phase whose ledger names a DEAD worker is re-admitted to pending;
  * a `running` phase whose ledger names a LIVE worker is NOT touched (fail closed);
  * an unreadable / unparseable / worker-less ledger is NOT touched (fail closed);
  * the reclaim is recorded in the readmission audit trail, with the artifact the
    phase was waiting on;
  * the pre-existing FAILED / QUARANTINED / verifier-BLOCKED behaviour is
    unchanged, and an operator park is still honoured.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import dispatcher, phases  # noqa: E402

RUN_DIR_KEY = "run_dir"


def _iso_now() -> str:
    """Now, in the same shape the dispatcher writes (`utcnow()`)."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _ledger(tmp_path: Path, phase_id: str, worker: str, **extra) -> Path:
    """Write a dispatch ledger in the shape the real writer produces."""
    d = tmp_path / "working" / "work-orders" / ".dispatch-state"
    d.mkdir(parents=True, exist_ok=True)
    rec = {"phase_id": phase_id, "status": "running", "worker": worker,
           "last_seen_at": "2026-09-16T11:47:00+00:00",
           "paid_attempts": 1, "generation": 0}
    rec.update(extra)
    p = d / f"{phase_id}.json"
    p.write_text(json.dumps(rec), encoding="utf-8")
    return p


def _phase(pid, status, **kw):
    d = {"id": pid, "status": status, "attempts": 1, "heal_events": []}
    d.update(kw)
    return d


def _state(tmp_path, *phases_):
    return {RUN_DIR_KEY: str(tmp_path), "phases": list(phases_)}


def _status_of(state, pid):
    for p in state["phases"]:
        if p["id"] == pid:
            return p["status"]
    raise AssertionError(f"{pid} not in state")


# ---------------------------------------------------------------------------
# The ownership verdict itself.
# ---------------------------------------------------------------------------

def test_a_dead_worker_pid_is_orphaned(tmp_path):
    # pid 0 is never a live user process; use a certainly-dead high pid instead
    # of a fork so the test stays hermetic and fast.
    _ledger(tmp_path, "P4-PROMPT", "dispatcher-999999-deadbeef")
    state, detail = dispatcher.running_worker_owner_state(tmp_path, "P4-PROMPT")
    assert state == "orphaned", (state, detail)
    assert "999999" in detail


def test_a_live_worker_pid_is_honoured(tmp_path):
    # OUR OWN pid is definitionally alive; the helper only special-cases self as
    # "live", which is exactly the answer wanted here.
    _ledger(tmp_path, "P4-PROMPT", f"dispatcher-{os.getpid()}-cafebabe")
    state, detail = dispatcher.running_worker_owner_state(tmp_path, "P4-PROMPT")
    assert state == "live", (state, detail)


def test_a_missing_ledger_is_absent_and_an_unreadable_one_is_unknown(tmp_path):
    state, _ = dispatcher.running_worker_owner_state(tmp_path, "NOPE")
    assert state == "absent"

    p = _ledger(tmp_path, "P4-PROMPT", "dispatcher-1-aaaa")
    p.write_text("{ this is not json", encoding="utf-8")
    state, _ = dispatcher.running_worker_owner_state(tmp_path, "P4-PROMPT")
    assert state == "unknown", "a corrupt ledger must fail CLOSED, not reclaim"


def test_a_ledger_with_no_adjudicable_worker_is_unknown(tmp_path):
    _ledger(tmp_path, "P4-PROMPT", "some-old-shape-worker")
    state, detail = dispatcher.running_worker_owner_state(tmp_path, "P4-PROMPT")
    assert state == "unknown", (state, detail)


# ---------------------------------------------------------------------------
# F1 (independent review of PR #1161) -- the pair-selection regression.
#
# The ledger carries TWO owner records naming DIFFERENT attempts:
#   * `last_reservation_worker` + `last_reserved_at` -- written BEFORE the
#     transport call and erased by the next outcome fold, so they exist ONLY
#     while an attempt is genuinely IN FLIGHT;
#   * `worker` + `last_seen_at` -- written at outcome-fold time, naming the last
#     SETTLED attempt.
# The first version of the helper read only the second pair. Mid-dispatch that
# pair still names the PREVIOUS attempt, and if its pid has since been recycled
# by the CURRENT dispatcher the start-time comparison fires and a phase with a
# LIVE worker is reported "orphaned". These tests pin the fix.
# ---------------------------------------------------------------------------

def _spawn_live_worker():
    """A genuinely alive process whose pid is NOT this process -- so the
    os.getpid() short-circuit cannot mask the pid-reuse guard (review F4)."""
    import subprocess
    return subprocess.Popen(["sleep", "30"])


def _reap(proc) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:  # noqa: BLE001 -- best-effort cleanup
        pass


def test_an_in_flight_live_worker_is_honoured_even_when_the_settled_worker_is_dead(tmp_path):
    """The exact false reclaim the review constructed: a LIVE in-flight worker,
    while the ledger's settled pair still names a DEAD worker from the previous
    attempt with a timestamp that predates the live process."""
    live = _spawn_live_worker()
    try:
        _ledger(tmp_path, "P4-PROMPT", "dispatcher-999999-deadbeef",
                last_seen_at="2020-01-01T00:00:00+00:00",
                last_reservation_worker=f"dispatcher-{live.pid}-feedface",
                last_reserved_at=_iso_now())
        state, detail = dispatcher.running_worker_owner_state(tmp_path, "P4-PROMPT")
        assert state == "live", (
            "an IN-FLIGHT reservation naming a live worker must be honoured even "
            f"though the settled worker is dead: got {state!r} ({detail})")
    finally:
        _reap(live)


def test_a_live_worker_is_honoured_using_a_REAL_process(tmp_path):
    """F4: the first version's 'live' case used os.getpid(), which short-circuits
    at the self check before the pid-reuse guard -- so the guard the author cites
    as the protection was exercised by ZERO tests. This drives the full path."""
    live = _spawn_live_worker()
    try:
        assert live.pid != os.getpid(), "the test must not self-short-circuit"
        _ledger(tmp_path, "P4-PROMPT", f"dispatcher-{live.pid}-feedface",
                last_seen_at=_iso_now())  # written AFTER the process started
        state, detail = dispatcher.running_worker_owner_state(tmp_path, "P4-PROMPT")
        assert state == "live", (state, detail)
        assert str(live.pid) in detail
    finally:
        _reap(live)


def test_a_pid_recycled_after_the_record_is_reported_orphaned(tmp_path):
    """The guard's real teeth, on a real process: the recorded pid IS alive, but
    the process holding it started long AFTER the record was written."""
    live = _spawn_live_worker()
    try:
        _ledger(tmp_path, "P4-PROMPT", f"dispatcher-{live.pid}-feedface",
                last_seen_at="2020-01-01T00:00:00+00:00")
        state, detail = dispatcher.running_worker_owner_state(tmp_path, "P4-PROMPT")
        assert state == "orphaned", (state, detail)
        assert "recycled" in detail, detail
    finally:
        _reap(live)


# ---------------------------------------------------------------------------
# F4: the paths the first version left unpinned.
# ---------------------------------------------------------------------------

def test_an_ABSENT_verdict_reclaims_through_the_real_entry_point(tmp_path):
    """No ledger at all: a `running` phase cannot be backed by any dispatch, and
    the reclaim must still reach it. This is a real shape -- an engine that died
    after checkpointing status=running but before the first ledger write."""
    st = _state(tmp_path, _phase("P4-PROMPT", "running"))
    readmitted = phases.readmit_retryable_phases(st)
    assert [r["phase"] for r in readmitted] == ["P4-PROMPT"]
    assert _status_of(st, "P4-PROMPT") == "pending"


def test_the_reclaim_does_not_reset_attempts_or_touch_the_ledger(tmp_path):
    """The reclaim re-opens the phase for PLANNING. It must not grant an attempt
    and must not rewrite the paid ledger."""
    led = _ledger(tmp_path, "P4-PROMPT", "dispatcher-999999-deadbeef",
                  blocked=True, blocked_reason="paid retry budget exhausted",
                  paid_attempts=2, generation=0)
    before = led.read_bytes()
    st = _state(tmp_path, _phase("P4-PROMPT", "running", attempts=3))

    phases.readmit_retryable_phases(st)

    assert _status_of(st, "P4-PROMPT") == "pending"
    assert st["phases"][0]["attempts"] == 3, "the reclaim must not reset attempts"
    assert led.read_bytes() == before, "the reclaim must not touch the paid ledger"


# ---------------------------------------------------------------------------
# The reclaim, through the real readmission entry point.
# ---------------------------------------------------------------------------

def test_orphaned_running_phase_is_reclaimed_to_pending(tmp_path):
    _ledger(tmp_path, "P4-PROMPT", "dispatcher-999999-deadbeef")
    st = _state(tmp_path, _phase("P4-PROMPT", "running", attempts=1,
                                 waiting_for=["working/prompts/slide-*.txt"],
                                 waited_seconds=450))

    readmitted = phases.readmit_retryable_phases(st)

    assert [r["phase"] for r in readmitted] == ["P4-PROMPT"]
    assert _status_of(st, "P4-PROMPT") == "pending"
    rec = st["phases"][0]["readmissions"][-1]
    assert rec["prior_status"] == "running"
    assert "reclaimed_orphaned_running" in rec, rec
    # the artifact it was stuck on is preserved on the audit record
    assert rec["reclaimed_waiting_for"] == ["working/prompts/slide-*.txt"]
    assert rec["reclaimed_waited_seconds"] == 450


def test_a_phase_whose_worker_is_ALIVE_is_never_reclaimed(tmp_path):
    """The fail-closed direction: this is what stops the fix from stealing a
    phase out from under a worker that is still writing its artifact."""
    _ledger(tmp_path, "P4-PROMPT", f"dispatcher-{os.getpid()}-cafebabe")
    st = _state(tmp_path, _phase("P4-PROMPT", "running"))

    readmitted = phases.readmit_retryable_phases(st)

    assert readmitted == []
    assert _status_of(st, "P4-PROMPT") == "running"


def test_an_unknown_owner_is_never_reclaimed(tmp_path):
    _ledger(tmp_path, "P4-PROMPT", "not-a-worker-token")
    st = _state(tmp_path, _phase("P4-PROMPT", "running"))

    assert phases.readmit_retryable_phases(st) == []
    assert _status_of(st, "P4-PROMPT") == "running"


def test_a_done_phase_is_never_reclaimed(tmp_path):
    _ledger(tmp_path, "P4-COPY", "dispatcher-999999-deadbeef")
    st = _state(tmp_path, _phase("P4-COPY", "done"))

    assert phases.readmit_retryable_phases(st) == []
    assert _status_of(st, "P4-COPY") == "done"


# ---------------------------------------------------------------------------
# Non-regression: the statuses PD-TEST-135 / FIX 22 already handled.
# ---------------------------------------------------------------------------

def test_failed_and_quarantined_still_readmit_and_operator_park_is_honoured(tmp_path):
    st = _state(tmp_path,
                _phase("P-FAILED", "failed", failed_reason="boom"),
                _phase("P-QUAR", "quarantined", quarantined_reason="boom"),
                _phase("P-OPERATOR-PARK", "blocked",
                       blocked_reason="waiting on the owner to choose a style"))
    readmitted = {r["phase"] for r in phases.readmit_retryable_phases(st)}

    assert readmitted == {"P-FAILED", "P-QUAR"}, readmitted
    assert _status_of(st, "P-OPERATOR-PARK") == "blocked"


def test_the_reclaim_and_the_old_readmission_coexist_in_one_pass(tmp_path):
    _ledger(tmp_path, "P4-PROMPT", "dispatcher-999999-deadbeef")
    st = _state(tmp_path,
                _phase("P4-PROMPT", "running"),
                _phase("P-FAILED", "failed", failed_reason="boom"))

    readmitted = {r["phase"] for r in phases.readmit_retryable_phases(st)}

    assert readmitted == {"P4-PROMPT", "P-FAILED"}
    assert _status_of(st, "P4-PROMPT") == "pending"
    assert _status_of(st, "P-FAILED") == "pending"
