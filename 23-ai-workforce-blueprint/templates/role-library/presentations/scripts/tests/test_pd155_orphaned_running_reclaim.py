"""PD-TEST-155 -- a phase stranded `running` by a dead engine must be reclaimable.

THE DEFECT, measured on run pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4.

`Engine._ready_set()` treats `running` as a status it neither plans nor expires:
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
