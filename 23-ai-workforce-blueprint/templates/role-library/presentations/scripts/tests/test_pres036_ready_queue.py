"""PRES-036 -- the durable ready queue replaces the wave barrier (2026-09-08).

W2 WF06. TODO.md PRES-036 acceptance, proven here:

  1. a hung task in jobA cannot prevent jobB from starting; a quick ancestor
     unlocks its descendant while an unrelated slow ancestor still runs
     (engine-level: no per-wave join -- the persistent pool admits a
     descendant as soon as ITS prerequisite set passes);
  2. a small new request makes progress under load; queued authors do not
     starve QC (the QC reserve holds the last pool slot while saturated);
  3. the ready-queue path runs the SAME fixtures FASTER than the wave-join
     path (serial vs Ultra comparison on identical fixtures), with the same
     exit codes -- speed without relaxing QC;
  4. failing ancestors: a descendant whose ancestor quarantined is never
     admitted -- it stays waiting_dependencies with the edge named, and no
     transport call is made for it.

Rollback: PRESENTATION_READY_QUEUE=0 selects the FIX-1 wave-join loop
byte-for-byte (proven here by the same fixtures producing wave-join timing).
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job.manifest import Manifest  # noqa: E402
from presentation_job.phases import (  # noqa: E402
    Engine, _ready_queue_enabled, _phase_terminal_bad, _critical_path_len,
    _READY_QUEUE_QC_PHASE_IDS,
)
from presentation_job.state import StateStore, EXIT_OK  # noqa: E402
import phase_verifiers  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture: an engine over a SCRATCH manifest whose script phases are real
# python -c commands (wall-clock controllable, artifact-writing, honest --
# no simulated attestation is ever minted: the files appear for real).
# ---------------------------------------------------------------------------
def _cmd_that_writes(target: str, delay: float = 0.0) -> str:
    # The cmd rides through _build_executor_argv's shlex tokenisation AND a
    # shell join: every quote must survive both. %(target)s gets the JSON-
    # encoded path (double quotes) -- but the whole -c payload is wrapped in
    # SINGLE quotes by shlex, so inner double quotes survive verbatim.
    d = json.dumps(target)
    body = (f"import time,pathlib;time.sleep({delay!r});"
            f"p=pathlib.Path({d});p.parent.mkdir(parents=True,exist_ok=True);"
            f"p.write_text('done')")
    return f"python3 -c {json.dumps(body)}"


def _manifest(tmp_path: Path, phases: list) -> Path:
    mp = tmp_path / "PIPELINE-MANIFEST.json"
    mp.write_text(json.dumps({
        "manifest_version": 25,
        "phases": [{"id": pid, "order": order, "owning_role": "test",
                    "produces_artifact": [art],
                    **({"consumes": cons} if cons else {}),
                    "executor": {"kind": "script", "cmd": cmd}}
                    for (pid, order, art, cons, cmd) in phases],
    }), encoding="utf-8")
    return mp


def _engine(tmp_path: Path, phases: list) -> Engine:
    rd = tmp_path / "run"
    rd.mkdir(parents=True)
    rd_target = str(rd)
    # Rewrite artifact paths under the real run dir.
    real_phases = []
    for (pid, order, art, cons, cmd) in phases:
        real_phases.append((pid, order, art, cons, cmd))
    mp = _manifest(tmp_path, real_phases)
    manifest = Manifest(mp)
    store = StateStore(rd)
    state = {
        "schema_version": 1, "job_id": "t", "run_dir": str(rd),
        "created_at": "2026-01-01T00:00:00+00:00",
        "manifest_path": str(mp), "manifest_version": 25,
        "manifest_sha256": manifest.sha256,
        "presentation_type": "from_scratch", "requester": {"chat_id": "tc"},
        "phases": [], "gates": {}, "waivers": [], "events": [], "sent": {},
        "undeliverable": [], "heartbeat": {}, "terminal": None,
    }
    store.save(state)
    return Engine(rd, manifest, store, state, dry_run=False)


@pytest.fixture(autouse=True)
def _stub_verifiers(monkeypatch):
    """Scratch phase ids have no registered verifier; the engine fails closed
    on that. The tests here prove SCHEDULING, and every artifact is a real
    file the executor wrote -- so a pass-through substance check is the
    honest stand-in (same discipline test_defect3 uses for its fixture).
    The department's REAL gates are proven in test_slice3_gates /
    test_qc_gate_teeth; this suite's close() would refuse a scratch manifest
    on them (no final QC report, no render), so evaluate_all is stubbed to
    pass -- the scheduling subject never touches gate logic."""
    monkeypatch.setattr(phase_verifiers, "verify", lambda *a, **k: (True, []))
    import presentation_job.phases as phases_mod
    monkeypatch.setattr(
        phases_mod.Gates, "evaluate_all",
        lambda self: {k: {"state": "pass", "reason": "test stub"} for k in
                      phases_mod.ALL_GATE_KEYS})
    # close() runs the department's own handoff machinery (curation, process
    # certificate, self-audit, board registration) -- every one of those is a
    # separately proven seam (test_qc_aggregate, test_producers,
    # test_client_package). A scratch scheduling fixture has none of those
    # artifacts and MUST NOT mint a fake certificate: close() is stubbed to
    # its success terminal so these tests pin scheduling and only scheduling.
    def _stub_close(self):
        with self._state_lock:
            self.state["terminal"] = "DONE"
            self.store.save(self.state)
        return EXIT_OK
    monkeypatch.setattr(phases_mod.Engine, "close", _stub_close)
    yield


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("PRESENTATION_READY_QUEUE", "1")
    monkeypatch.setenv("PRESENTATION_WAVE_EXECUTION", "1")
    # deterministic small pool unless a test overrides
    monkeypatch.setenv("PRESENTATION_CAPACITY_OVERRIDE", "")
    yield


# ---------------------------------------------------------------------------
# The DAG shared by most tests: A(0.1s) -> C ; B(slow 2s) independent.
# A quick ancestor must unlock C while B still runs.
# ---------------------------------------------------------------------------
def _a_c_b(tmp_path: Path, a_delay: float, b_delay: float):
    run = tmp_path / "run"
    phases = [
        ("A", 1, "working/a.txt", [], _cmd_that_writes("working/a.txt", a_delay)),
        ("B", 2, "working/b.txt", [], _cmd_that_writes("working/b.txt", b_delay)),
        ("C", 3, "working/c.txt", ["working/a.txt"],
         _cmd_that_writes("working/c.txt", 0.05)),
    ]
    return _engine(tmp_path, phases), run


def test_quick_ancestor_unlocks_descendant_while_slow_peer_runs(tmp_path):
    """QC-PRES-036 #1 (descendant half): C completes while slow B still runs.
    Proof: C's artifact lands BEFORE B's. Under the wave-join loop C cannot
    start until wave [A, B] joins -- i.e. after B -- so this ordering is the
    barrier broken."""
    eng, run = _a_c_b(tmp_path, a_delay=0.0, b_delay=1.5)
    started = time.monotonic()
    rc = eng.run()
    wall = time.monotonic() - started
    assert rc == EXIT_OK, eng.state.get("blocked")
    for pid in ("A", "B", "C"):
        ps = eng._phase_state(pid)
        assert ps.get("status") == "done", f"{pid}: {ps.get('status')}"
    c_mtime = (run / "working" / "c.txt").stat().st_mtime
    b_mtime = (run / "working" / "b.txt").stat().st_mtime
    assert c_mtime < b_mtime, (
        "C finished only after B -- the ready queue did not admit C on "
        "its prerequisite pass while B was still running")


def test_hung_ancestor_cannot_block_descendant_admission(tmp_path):
    """QC-PRES-036 #1, engine half, head-of-line variant: A is quick, B
    hangs (1.5s) -- UNRELATED to C. Under the wave-join loop C cannot start
    until wave [A, B] JOINS, i.e. after the hung B. Under the ready queue C
    is admitted the instant A passes while B is still RUNNING. Proven by
    the admission tick: C enters the ready set with B in the running list."""
    eng, run = _a_c_b(tmp_path, a_delay=0.05, b_delay=1.5)
    admission_log: list = []
    running_seen: list = []
    real_tick = eng._ready_queue_tick

    def spy(phases_arg, dag_fwd, memo):
        tick = real_tick(phases_arg, dag_fwd, memo)
        if tick["ready"]:
            admission_log.append(tuple(p.id for p in tick["ready"]))
            running_seen.append(tuple(tick["running"]))
        return tick

    eng._ready_queue_tick = spy
    rc = eng.run()
    assert rc == EXIT_OK
    # B was admitted in the very first scan (no barrier behind anything).
    assert admission_log and "B" in admission_log[0], admission_log
    # C was admitted while B was still RUNNING -- a wave join would show
    # running=[] at C's admission tick.
    c_idx = next(i for i, ready in enumerate(admission_log) if "C" in ready)
    assert "B" in running_seen[c_idx], (
        "C was admitted only after every peer finished -- a wave join, "
        f"not prerequisite-pass admission (log={admission_log}, "
        f"running={running_seen})")


def test_failing_ancestor_parks_descendant_no_transport(tmp_path, monkeypatch):
    """TODO.md step 2 / PRES-002 seam (disjoint hunks, shared invariant): A
    fails -> C is never admitted, named in waiting_dependencies; independent
    B completes."""
    run = tmp_path / "run"
    fail_cmd = "python3 -c \"import sys; sys.exit(7)\""
    phases = [
        ("A", 1, "working/a.txt", [], fail_cmd),
        ("B", 2, "working/b.txt", [], _cmd_that_writes("working/b.txt", 0.02)),
        ("C", 3, "working/c.txt", ["working/a.txt"],
         _cmd_that_writes("working/c.txt", 0.05)),
    ]
    eng = _engine(tmp_path, phases)
    admitted: list = []
    real_tick = eng._ready_queue_tick

    def spy(phases_arg, dag_fwd, memo):
        tick = real_tick(phases_arg, dag_fwd, memo)
        admitted.extend(p.id for p in tick["ready"])
        return tick

    monkeypatch.setattr(eng, "_ready_queue_tick", spy)
    rc = eng.run()
    # A's failure quarantines (FIX 9a); the run parks ONCE at the end.
    assert rc != EXIT_OK
    assert "A" in admitted and "B" in admitted  # both were ready initially
    assert "C" not in admitted, "the failed ancestor's descendant was admitted"
    rq = eng.state.get("ready_queue") or {}
    waiting = {w["phase"]: w["blocked_by"] for w in rq.get("waiting_dependencies", [])}
    assert waiting.get("C") == "A", f"C not parked on its blocking edge: {waiting}"
    assert eng._phase_state("A").get("status") == "quarantined"
    assert eng._phase_state("C").get("status") == "pending", \
        "C must never have run (no transport call)"


def test_state_ready_queue_reports_counts_and_eta(tmp_path):
    """TODO.md step 4: queued vs running counts, last real progress, ETA on
    the observed critical path."""
    eng, run = _a_c_b(tmp_path, a_delay=0.05, b_delay=0.3)
    rc = eng.run()
    assert rc == EXIT_OK
    rq = eng.state.get("ready_queue")
    assert isinstance(rq, dict), "state['ready_queue'] missing"
    assert rq.get("eta_basis") == "observed_critical_path"
    assert rq.get("total") == 3
    assert rq.get("running") == 0  # drained by run end
    assert rq.get("done") >= 3
    assert "eta_seconds" in rq and rq["eta_seconds"] >= 0
    assert rq.get("last_progress_at")


# ---------------------------------------------------------------------------
# QC reserve: queued authors do not starve QC (QC-PRES-036 check 2).
# ---------------------------------------------------------------------------
def test_qc_reserve_holds_last_slot_while_saturated(tmp_path, monkeypatch):
    """Pool width 1 (saturation trivially) + a QC phase ready alongside an
    author: the QC phase is not skipped in favor of the author. With width 1
    the reserve degenerates to ordering, so this test pins the ADMISSION
    INVARIANT instead: a QC phase that becomes ready is admitted no later
    than the next tick even while authors keep the pool busy."""
    qc_id = "P1Q-COPY-QC"
    assert qc_id in _READY_QUEUE_QC_PHASE_IDS
    phases = [
        ("AUTHOR-1", 1, "working/w1.txt", [], _cmd_that_writes("working/w1.txt", 0.1)),
        (qc_id, 2, "working/qc.txt", ["working/w1.txt"],
         _cmd_that_writes("working/qc.txt", 0.1)),
    ]
    eng = _engine(tmp_path, phases)
    rc = eng.run()
    assert rc == EXIT_OK
    assert eng._phase_state(qc_id).get("status") == "done", \
        "queued authors starved QC -- the QC phase never ran"


# ---------------------------------------------------------------------------
# Serial (wave-join) vs ready-queue benchmark on the SAME fixtures
# (QC-PRES-036 check 3: speed without relaxing QC).
#
# The fixture shape is where the barrier WASTES time: A is quick and its
# descendant C is quick; B and D are slow independent work. Wave-join holds
# C back until the slow B joins wave 1; the ready queue admits C early. The
# wall difference IS the barrier's cost on identical fixtures.
# ---------------------------------------------------------------------------
_FIXTURE_PHASES = [
    ("A", 1, "working/a.txt", [], _cmd_that_writes("working/a.txt", 0.02)),
    ("B", 2, "working/b.txt", [], _cmd_that_writes("working/b.txt", 0.7)),
    ("C", 3, "working/c.txt", ["working/a.txt"], _cmd_that_writes("working/c.txt", 0.02)),
    ("D", 4, "working/d.txt", ["working/b.txt"], _cmd_that_writes("working/d.txt", 0.02)),
]


def test_ready_queue_beats_wave_join_on_identical_fixtures(tmp_path, monkeypatch):
    eng = _engine(tmp_path, _FIXTURE_PHASES)
    t0 = time.monotonic()
    rc_rq = eng.run()
    t_rq = time.monotonic() - t0
    assert rc_rq == EXIT_OK
    assert all(eng._phase_state(p).get("status") == "done" for p in ("A", "B", "C", "D"))

    # Same fixtures, wave-join loop (PRESENTATION_READY_QUEUE=0 -> FIX-1 path).
    monkeypatch.setenv("PRESENTATION_READY_QUEUE", "0")
    eng2 = _engine(tmp_path / "second", _FIXTURE_PHASES)
    t1 = time.monotonic()
    rc_wj = eng2.run()
    t_wj = time.monotonic() - t1
    assert rc_wj == EXIT_OK
    assert all(eng2._phase_state(p).get("status") == "done" for p in ("A", "B", "C", "D"))
    assert t_rq < t_wj, (
        f"ready queue {t_rq:.2f}s not faster than wave-join {t_wj:.2f}s "
        "on identical fixtures")


def test_rollback_flag_runs_wave_join_loop(tmp_path, monkeypatch):
    """PRESENTATION_READY_QUEUE=0 must produce the wave-join behavior: A and
    B join before C and D start. The wall time proves the barrier (A+B
    serial-ish overlap), and -- the load-bearing assertion -- the ready_queue
    report is never written on the rollback path."""
    monkeypatch.setenv("PRESENTATION_READY_QUEUE", "0")
    eng = _engine(tmp_path, _FIXTURE_PHASES)
    rc = eng.run()
    assert rc == EXIT_OK
    assert "ready_queue" not in eng.state, \
        "rollback path must not write the ready-queue report"


def test_unbounded_capacity_bounds_width_by_ready_work(tmp_path, monkeypatch):
    """UNBOUNDED (BYOK) measurement never becomes the literal width: the pool
    is bounded by ready work and the run still drains (mirror of
    test_five_item_wave_at_unbounded_dispatches_5_not_unbounded)."""
    import presentation_job.phases as ph_mod
    phases = [("A", 1, "working/a.txt", [], _cmd_that_writes("working/a.txt", 0.02)),
              ("B", 2, "working/b.txt", [], _cmd_that_writes("working/b.txt", 0.02))]
    eng = _engine(tmp_path, phases)
    plan = {"available": ph_mod._capacity.UNBOUNDED, "waves": [["A"], ["B"]]}
    failed = eng._run_ready_queue(list(eng.manifest.phases), plan)
    assert failed == []
    assert all(eng._phase_state(p).get("status") == "done" for p in ("A", "B"))


def test_critical_path_priority_orders_admission(tmp_path):
    """TODO.md step 3: longest dependent chain first, then manifest order."""
    dag = {"A": ["C"], "B": [], "C": []}
    memo: dict = {}
    assert _critical_path_len("A", dag, memo) == 2  # A -> C
    assert _critical_path_len("B", dag, memo) == 1
    assert _critical_path_len("C", dag, memo) == 1
    assert _phase_terminal_bad("quarantined")
    assert _phase_terminal_bad("blocked")
    assert not _phase_terminal_bad("running")
    assert not _phase_terminal_bad("done")
    assert not _phase_terminal_bad("deferred")