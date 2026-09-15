"""PD-TEST-080 -- a dispatcher park marker must not outlive the dispatcher.

THE DEFECT. `__main__._reset_parked_state` (the shared --run/--resume unpark
helper, PD-TEST-060 / FIX 22) calls `phases.readmit_retryable_phases` so a
FAILED/QUARANTINED phase becomes PENDING again and can be retried -- the fix
that ended "every resume re-parked the run identically". Its own
`_dispatch_blocked_marker(...).exists()` guard defeated that intent for exactly
the runs that need it: the marker it skips on is written by the DISPATCHER, and
a dispatcher routinely outlives its own usefulness and exits. The engine clears
the marker when IT quarantines a unit (phases.py:3546), but the dispatcher
re-arms on that same state change (its own comment at phases.py:3537-3539),
sweeps again, fails identically, RE-PARKS and re-writes the marker AFTER the
clear -- then hits state.terminal and exits ("run terminal is set -- exiting"),
leaving the marker with no owner. None of the three marker-clearing sites can
fire for a phase parked by a CODE bug (new approved-input generation only, a
work-order reissue that needs a runnable phase, or the quarantine clear that
has already been undone), so the loop is closed: deploy the code repair,
--resume, the phase is skipped, it stays quarantined, its descendants stay
withheld by `_phase_terminal_bad`, and the run re-parks identically.

MEASURED, on run pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4 (terminal
BLOCKED, queued=0, done=10/57, no engine or dispatcher process alive):

    phase                  marker owner (worker:)        pid     state
    P-SP-INTAKE            dispatcher-55801-b0309fc4      55801   DEAD
    P-STYLE-SPEC           dispatcher-71266-23241037     71266   DEAD
    P-U-DESIGN-CHECKOUT    dispatcher-71266-23241037     71266   DEAD
    P-U-DESIGN-SALES       dispatcher-71266-23241037     71266   DEAD
    P-U-DESIGN-VSL         dispatcher-71266-23241037     71266   DEAD
    P0A-INTAKE             dispatcher-87833-e0a62d7b      87833   DEAD

THE CONTROL THAT ISOLATES THE CAUSE (run against a deep copy of that run's
state, markers temporarily set aside and restored):
    readmit_retryable_phases -> ['P4-COPY']                       (4 skipped)
    with the four markers hidden -> ['P4-COPY', 'P-U-DESIGN-SALES',
        'P-U-DESIGN-CHECKOUT', 'P-U-DESIGN-VSL', 'P-STYLE-SPEC']
The orphaned markers were the SOLE gate. P4-COPY is the marker-ABSENT half of
the same defect's neighbourhood: the engine's quarantine clear landed and the
dispatcher never got another sweep in, so it re-admits today -- which is why
the repair must leave that case alone.

TWO DIRECTIONS, as the repair requires:
  * a marker whose owner is ALIVE still binds -- protection intact;
  * a marker whose owner is GONE is adjudicated orphaned, the phase is
    re-admitted to PENDING (so `_phase_terminal_bad` stops withholding its
    descendants), and the ownerless marker is retired so the Engine's own F9
    park reaction cannot fire for a park nobody holds.
Plus the two things that must NOT move: the durable paid-attempt ledger (the
real budget ceiling) and the marker text/format `_park_blocked` writes.

PID REUSE. Liveness alone is not ownership: POSIX recycles pids, so a dead
dispatcher's pid can be held by an unrelated process. The marker's own
`blocked_at` is the discriminator its writer cannot fake -- the owner wrote
that line while it existed, so a live process at that pid which STARTED LATER
cannot be its author. `test_recycled_pid_is_orphaned_not_live` proves that with
a REAL live unrelated process. Every doubt (no worker line, no timestamp, no
`ps`, unparseable output) resolves to LIVE -- fail-closed, so a live owner is
never ignored.

No test here touches the network, a provider, the live run directory, the
installed mirrors, or tests/test_intake_driver_run_mode_unification.py's live
operator state. Everything is the real code against a scratch run dir.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import autospawn as autospawn_mod  # noqa: E402
from presentation_job import dispatcher as dispatcher_mod  # noqa: E402
from presentation_job.manifest import Manifest  # noqa: E402
from presentation_job.phases import (  # noqa: E402
    Engine, _dispatch_blocked_marker, _phase_terminal_bad,
    readmit_retryable_phases,
)
from presentation_job.state import StateStore, EXIT_OK, utcnow  # noqa: E402
from presentation_job.__main__ import _reset_parked_state  # noqa: E402
import phase_verifiers  # noqa: E402


# ---------------------------------------------------------------------------
# The real producer, never a retyped marker -- if dispatcher.py renames a field
# or changes the owner line, these tests must fail rather than silently pin a
# shape the dispatcher does not write (same discipline as
# test_f9f10f11_engine_heal_respawn._park_phase_like_the_dispatcher).
# ---------------------------------------------------------------------------
def _park_like_the_dispatcher(run_dir: Path, phase_id: str, *, worker_id: str,
                              blocked_at: str) -> Path:
    (run_dir / "working" / "work-orders").mkdir(parents=True, exist_ok=True)
    dispatcher_mod._park_blocked(
        run_dir, phase_id,
        {"blocked_reason": "retry ceiling reached", "blocked_at": blocked_at,
         "status": "error", "consecutive": 8, "observations": 8},
        worker_id=worker_id)
    return dispatcher_mod._blocked_marker_path(run_dir, phase_id)


def _a_dead_pid() -> int:
    """A pid that is genuinely not running. Proven, not assumed: os.kill(pid, 0)
    must raise ProcessLookupError before this returns it."""
    for candidate in range(4_000_000, 4_000_050):
        try:
            os.kill(candidate, 0)
        except ProcessLookupError:
            return candidate
        except OSError:
            continue
    pytest.fail("could not find a dead pid to test with -- the check itself is broken")


@pytest.fixture
def unrelated_live_process():
    """A REAL live process that is not this test and not a dispatcher: the
    'unrelated process took the recycled pid' case. Its start is strictly after
    the marker a recycled-pid test writes, which is exactly what makes it a
    reuser rather than an owner."""
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        # Wait until the child is really in the table (and start-time-bearing).
        deadline = time.time() + 10
        while time.time() < deadline:
            if autospawn_mod._process_start_epoch(proc.pid) is not None:
                break
            time.sleep(0.05)
        yield proc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:  # pragma: no cover - defensive
            proc.kill()
            proc.wait(timeout=5)


def _run_dir(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    (run / "working" / "work-orders").mkdir(parents=True, exist_ok=True)
    return run


def _state_for_reset(run_dir: Path, phases: list) -> dict:
    return {
        "run_dir": str(run_dir), "terminal": "BLOCKED",
        "blocked": {"phase": phases[0]["id"], "reason": "1 unit(s) failed",
                    "at": "x"},
        "phases": phases,
    }


def _quarantined(pid: str, attempts: int = 1) -> dict:
    return {"id": pid, "status": "quarantined", "attempts": attempts,
            "heal_events": [], "quarantined_reason": "artifact never appeared"}


# ===========================================================================
# Adjudication: who owns this marker RIGHT NOW?
# ===========================================================================
class TestMarkerOwnershipVerdicts:
    def test_absent(self, tmp_path):
        run = _run_dir(tmp_path)
        assert dispatcher_mod.park_marker_owner_state(run, "A")[0] == "absent"

    def test_owner_line_that_names_a_live_process_is_live(self, tmp_path,
                                                          unrelated_live_process):
        run = _run_dir(tmp_path)
        _park_like_the_dispatcher(
            run, "A", worker_id=f"dispatcher-{unrelated_live_process.pid}-{uuid.uuid4().hex[:8]}",
            blocked_at=utcnow())
        state, detail = dispatcher_mod.park_marker_owner_state(run, "A")
        assert state == "live", detail

    def test_owner_pid_that_is_gone_is_orphaned(self, tmp_path):
        run = _run_dir(tmp_path)
        dead = _a_dead_pid()
        _park_like_the_dispatcher(run, "A",
                                  worker_id=f"dispatcher-{dead}-{uuid.uuid4().hex[:8]}",
                                  blocked_at=utcnow())
        state, detail = dispatcher_mod.park_marker_owner_state(run, "A")
        assert state == "orphaned", detail
        assert "names no process" in detail

    def test_recycled_pid_is_orphaned_not_live(self, tmp_path,
                                               unrelated_live_process):
        """The pid-reuse case, with a real reuser: the live process holding the
        marker's pid started AFTER the marker was written, so it cannot be the
        author -- even though `_pid_is_alive` says True (which is all the old
        guard ever asked)."""
        run = _run_dir(tmp_path)
        pid = unrelated_live_process.pid
        assert autospawn_mod._pid_is_alive(pid), "the reuser must really be alive"
        started = autospawn_mod._process_start_epoch(pid)
        assert started is not None
        # The park predates the process now holding that pid.
        from datetime import datetime, timedelta, timezone
        blocked_at = datetime.fromtimestamp(started, timezone.utc) - timedelta(hours=3)
        _park_like_the_dispatcher(
            run, "A", worker_id=f"dispatcher-{pid}-{uuid.uuid4().hex[:8]}",
            blocked_at=blocked_at.isoformat(timespec="seconds"))
        state, detail = dispatcher_mod.park_marker_owner_state(run, "A")
        assert state == "orphaned", detail
        assert "recycled" in detail

    def test_marker_without_an_owner_line_is_honoured(self, tmp_path):
        """A bare/hand-written marker names no pid, so ownership is not
        established. Fail closed: honoured exactly as it was before this fix
        (this is the shape tests/test_pd060_failed_phase_readmission.py writes).
        """
        run = _run_dir(tmp_path)
        _dispatch_blocked_marker(run, "A").write_text(
            "DISPATCH BLOCKED -- retry ceiling", encoding="utf-8")
        state, detail = dispatcher_mod.park_marker_owner_state(run, "A")
        assert state == "unknown", detail

    def test_liveness_probe_failure_is_honoured_as_live(self, tmp_path,
                                                        monkeypatch):
        """No `ps` on the box (or a broken one) must not turn a live owner's
        park into an orphan."""
        run = _run_dir(tmp_path)
        _park_like_the_dispatcher(
            run, "A",
            worker_id=f"dispatcher-{os.getpid() + 1}-{uuid.uuid4().hex[:8]}",
            blocked_at=utcnow())

        def _no_ps(*_a, **_k):
            raise OSError("ps missing")

        monkeypatch.setattr(autospawn_mod.subprocess, "run", _no_ps)
        monkeypatch.setattr(autospawn_mod, "_pid_is_alive", lambda pid: True)
        state, detail = dispatcher_mod.park_marker_owner_state(run, "A")
        assert state == "live", detail
        assert "honoured" in detail

    def test_unparseable_blocked_at_is_honoured_as_live(
            self, tmp_path, unrelated_live_process):
        """A live owner plus a marker whose timestamp cannot be read: the
        recycling test cannot be run, so the park is honoured rather than
        guessed away."""
        run = _run_dir(tmp_path)
        _park_like_the_dispatcher(
            run, "A",
            worker_id=f"dispatcher-{unrelated_live_process.pid}-{uuid.uuid4().hex[:8]}",
            blocked_at="None")
        state, detail = dispatcher_mod.park_marker_owner_state(run, "A")
        assert state == "live", detail
        assert "honoured" in detail

    def test_own_pid_is_never_orphaned(self, tmp_path):
        run = _run_dir(tmp_path)
        _park_like_the_dispatcher(
            run, "A", worker_id=f"dispatcher-{os.getpid()}-{uuid.uuid4().hex[:8]}",
            blocked_at=utcnow())
        assert dispatcher_mod.park_marker_owner_state(run, "A")[0] == "live"

    def test_etime_parser_accepts_every_shape_ps_prints(self):
        parse = autospawn_mod._parse_ps_elapsed
        assert parse("00:00") == 0.0
        assert parse("  07:31") == 451.0
        assert parse("1:02:03") == 3723.0
        assert parse("2-03:04:05") == 183845.0
        assert parse("") is None and parse("bogus") is None


# ===========================================================================
# (a)/(b)/(d) The readmission seam: alive -> skipped, dead -> re-admitted,
# absent -> re-admitted. Plus the control that isolates the cause.
# ===========================================================================
class TestReadmissionSeam:
    def test_marker_present_owner_alive_is_still_skipped(self, tmp_path,
                                                         unrelated_live_process):
        """(a) Protection intact: a park whose dispatcher is STILL RUNNING must
        not be re-admitted, must not be retired, and must not buy an attempt."""
        run = _run_dir(tmp_path)
        marker = _park_like_the_dispatcher(
            run, "A", worker_id=f"dispatcher-{unrelated_live_process.pid}-{uuid.uuid4().hex[:8]}",
            blocked_at=utcnow())
        state = _state_for_reset(run, [_quarantined("A", attempts=3)])
        _reset_parked_state(state)
        a = state["phases"][0]
        assert a["status"] == "quarantined", "a live dispatcher's park still binds"
        assert not a.get("readmissions")
        assert state["last_resume_readmissions"] == []
        assert marker.is_file(), "a live owner's marker must not be touched"

    def test_marker_present_owner_dead_is_readmitted_and_not_withheld(
            self, tmp_path):
        """(b) The live-run case: owner pid gone -> PENDING, and the phase is no
        longer withheld (so `_phase_terminal_bad` stops gating descendants)."""
        run = _run_dir(tmp_path)
        dead = _a_dead_pid()
        marker = _park_like_the_dispatcher(
            run, "A", worker_id=f"dispatcher-{dead}-{uuid.uuid4().hex[:8]}",
            blocked_at=utcnow())
        state = _state_for_reset(run, [_quarantined("A", attempts=3)])
        _reset_parked_state(state)
        a = state["phases"][0]
        assert a["status"] == "pending", a
        assert a["attempts"] == 3, "the failed attempt counter is preserved"
        assert a["quarantined_reason"] == "artifact never appeared"
        assert _phase_terminal_bad(a["status"]) is False, (
            "a re-admitted phase must not withhold its descendants")
        record = state["last_resume_readmissions"][0]
        assert record["phase"] == "A" and record["prior_status"] == "quarantined"
        assert "names no process" in record["orphaned_park_marker"]
        assert record["orphaned_park_marker_retired"] is True
        assert not marker.exists(), (
            "an ownerless park marker must be retired, or the Engine's own F9 "
            "reaction would fire for a park nobody holds")

    def test_absent_marker_is_readmitted_as_before(self, tmp_path):
        """(d) The P4-COPY case: no marker at all -- unchanged behaviour."""
        run = _run_dir(tmp_path)
        state = _state_for_reset(run, [_quarantined("A")])
        _reset_parked_state(state)
        a = state["phases"][0]
        assert a["status"] == "pending"
        assert "orphaned_park_marker" not in state["last_resume_readmissions"][0]

    def test_orphaned_markers_are_the_only_gate_control(self, tmp_path):
        """The measured control, both directions.

        Five quarantined phases, four of them carrying dispatcher park markers
        exactly as the live run does. With the owners DEAD all five re-admit;
        with the owners ALIVE only the marker-free one does. That second half is
        what proves this repair narrows the gate without removing it."""
        live_ids = ["P4-COPY", "P-U-DESIGN-SALES", "P-U-DESIGN-CHECKOUT",
                    "P-U-DESIGN-VSL", "P-STYLE-SPEC"]
        parked = live_ids[1:]

        # -- dead owners: every phase re-admits (the control's second call) ----
        run = _run_dir(tmp_path)
        dead = _a_dead_pid()
        for pid in parked:
            _park_like_the_dispatcher(
                run, pid, worker_id=f"dispatcher-{dead}-{uuid.uuid4().hex[:8]}",
                blocked_at=utcnow())
        state = _state_for_reset(run, [_quarantined(p) for p in live_ids])
        readmitted = readmit_retryable_phases(state)
        assert [r["phase"] for r in readmitted] == live_ids, (
            "with the owners dead, the markers must not gate anything")
        assert all(r["orphaned_park_marker_retired"] for r in readmitted[1:])
        assert "orphaned_park_marker" not in readmitted[0]

        # -- live owners: the same four stay parked, the marker-free one goes --
        run2 = _run_dir(tmp_path / "alive")
        for pid in parked:
            _park_like_the_dispatcher(
                run2, pid,
                worker_id=f"dispatcher-{os.getpid() + 1}-{uuid.uuid4().hex[:8]}",
                blocked_at=utcnow())
        import unittest.mock as _mock
        with _mock.patch.object(autospawn_mod, "_pid_is_alive", lambda pid: True):
            state2 = _state_for_reset(run2, [_quarantined(p) for p in live_ids])
            readmitted2 = readmit_retryable_phases(state2)
        assert [r["phase"] for r in readmitted2] == ["P4-COPY"], (
            "a live owner's park must still withhold its phase")
        assert all(p["status"] == "quarantined"
                   for p in state2["phases"] if p["id"] in parked)
        assert all(_dispatch_blocked_marker(run2, p).is_file() for p in parked)

    def test_readmission_does_not_touch_the_durable_paid_budget(self, tmp_path):
        """The ceiling that must NOT move: re-admitting a phase parked by a dead
        dispatcher leaves the ledger byte-identical and `should_dispatch`
        refusing, because the budget is the LEDGER -- never the marker."""
        run = _run_dir(tmp_path)
        dead = _a_dead_pid()
        _park_like_the_dispatcher(
            run, "A", worker_id=f"dispatcher-{dead}-{uuid.uuid4().hex[:8]}",
            blocked_at=utcnow())
        ledger = dispatcher_mod._ledger_path(run, "A")
        dispatcher_mod._write_ledger(run, "A", {
            "phase_id": "A", "approved_input_revision": "initial",
            "paid_attempts": dispatcher_mod.DISPATCH_RETRY_CAP,
            "blocked": True, "blocked_reason": "paid retry budget exhausted",
            "next_eligible_at_epoch": time.time() + 10_000,
        })
        before = ledger.read_bytes()

        state = _state_for_reset(run, [_quarantined("A", attempts=3)])
        _reset_parked_state(state)

        assert state["phases"][0]["status"] == "pending"
        assert ledger.read_bytes() == before, (
            "re-admission must never rewrite the durable paid-attempt ledger")
        may, why = dispatcher_mod.should_dispatch(run, "A")
        assert may is False and "paid retry budget exhausted" in why, why

    def test_terminal_bad_pins_are_unchanged(self):
        """`_phase_terminal_bad` itself is untouched by this repair -- pinned so
        the withholding rule cannot drift while the gate above it narrows."""
        for status in ("pending", "running", "done", "deferred", None):
            assert _phase_terminal_bad(status) is False, status
        for status in ("quarantined", "failed", "blocked", "obsolete"):
            assert _phase_terminal_bad(status) is True, status


# ===========================================================================
# (c) Engine level: a resume after a code repair does not re-park identically.
# ===========================================================================
def _cmd_that_writes(target: str, delay: float = 0.0) -> str:
    d = json.dumps(target)
    body = (f"import time,pathlib;time.sleep({delay!r});"
            f"p=pathlib.Path({d});p.parent.mkdir(parents=True,exist_ok=True);"
            f"p.write_text('done')")
    return f"python3 -c {json.dumps(body)}"


def _cmd_that_writes_only_after_sentinel(target: str, sentinel: str) -> str:
    """Fails (rc 7) on the first run; the sentinel makes it succeed later --
    the sentinel is the deployed code repair."""
    d = json.dumps(target)
    s = json.dumps(sentinel)
    body = (f"import pathlib,sys;"
            f"p=pathlib.Path({d});s=pathlib.Path({s});"
            f"p.parent.mkdir(parents=True,exist_ok=True);"
            f"(p.write_text('done') if s.exists() else sys.exit(7))")
    return f"python3 -c {json.dumps(body)}"


def _engine(tmp_path: Path, phases: list) -> Engine:
    rd = tmp_path / "run"
    rd.mkdir(parents=True, exist_ok=True)
    mp = tmp_path / "PIPELINE-MANIFEST.json"
    mp.write_text(json.dumps({
        "manifest_version": 25,
        "phases": [{"id": pid, "order": order, "owning_role": "test",
                    "produces_artifact": [art],
                    **({"consumes": cons} if cons else {}),
                    "executor": {"kind": "script", "cmd": cmd}}
                   for (pid, order, art, cons, cmd) in phases],
    }), encoding="utf-8")
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
    monkeypatch.setattr(phase_verifiers, "verify", lambda *a, **k: (True, []))
    import presentation_job.phases as phases_mod
    monkeypatch.setattr(
        phases_mod.Gates, "evaluate_all",
        lambda self: {k: {"state": "pass", "reason": "test stub"} for k in
                      phases_mod.ALL_GATE_KEYS})

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
    monkeypatch.setenv("PRESENTATION_CAPACITY_OVERRIDE", "")
    yield


def _park_with_failed_arc(tmp_path: Path):
    """A -> C chain where A fails on the first run and would pass on a retry."""
    sentinel = tmp_path / "go"
    phases = [
        ("A", 1, "working/a.txt", [],
         _cmd_that_writes_only_after_sentinel("working/a.txt", str(sentinel))),
        ("C", 2, "working/c.txt", ["working/a.txt"],
         _cmd_that_writes("working/c.txt", 0.02)),
    ]
    return _engine(tmp_path, phases), tmp_path / "run", sentinel


class TestEngineResumeAfterACodeRepair:
    def test_orphaned_park_marker_does_not_re_park_the_run(self, tmp_path):
        """(c) The PD-TEST-060 property, in the presence of the marker that was
        defeating it: A quarantines and a dispatcher that then DIES parks it; the
        code repair lands (the sentinel); the resume must advance the run."""
        eng, run, sentinel = _park_with_failed_arc(tmp_path)
        assert eng.run() != EXIT_OK
        a = eng._phase_state("A")
        assert a["status"] == "quarantined" and a["attempts"] == 1, a
        assert eng.state.get("terminal") == "BLOCKED"
        assert not (run / "working" / "c.txt").exists(), "C ran behind a failed A"

        dead = _a_dead_pid()
        marker = _park_like_the_dispatcher(
            run, "A", worker_id=f"dispatcher-{dead}-{uuid.uuid4().hex[:8]}",
            blocked_at=utcnow())
        assert dispatcher_mod.park_marker_owner_state(run, "A")[0] == "orphaned"

        sentinel.write_text("go", encoding="utf-8")   # the deployed code repair
        prior = _reset_parked_state(eng.state)
        assert prior is not None and prior["phase"] == "A"
        assert [r["phase"] for r in eng.state["last_resume_readmissions"]] == ["A"]
        assert not marker.exists(), "the ownerless marker must be retired"
        eng.store.save(eng.state)

        assert eng.run() == EXIT_OK, eng.state.get("blocked")
        a = eng._phase_state("A")
        assert a["status"] == "done", a
        assert a["attempts"] == 2, "the retry is a real second attempt"
        assert eng._phase_state("C")["status"] == "done"
        assert (run / "working" / "c.txt").exists()
        assert eng.state["terminal"] == "DONE"

    def test_resume_still_withholds_when_the_park_owner_is_alive(
            self, tmp_path, unrelated_live_process):
        """The same resume, with the owner ALIVE: nothing moves. Asserted on
        scheduling invariants (attempts, statuses, the artifact), not on the
        engine's return code -- the autouse fixture stubs close() to succeed."""
        eng, run, sentinel = _park_with_failed_arc(tmp_path)
        assert eng.run() != EXIT_OK
        assert eng._phase_state("A")["status"] == "quarantined"

        marker = _park_like_the_dispatcher(
            run, "A",
            worker_id=f"dispatcher-{unrelated_live_process.pid}-{uuid.uuid4().hex[:8]}",
            blocked_at=utcnow())

        sentinel.write_text("go", encoding="utf-8")
        _reset_parked_state(eng.state)
        assert eng.state.get("last_resume_readmissions") == [], (
            "the live dispatcher's durable park must survive the unpark")
        eng.store.save(eng.state)
        eng.run()

        a = eng._phase_state("A")
        assert a["status"] == "quarantined", a
        assert a["attempts"] == 1, "no attempt may be bought by a resume"
        assert not a.get("readmissions"), a
        assert eng._phase_state("C")["status"] == "pending"
        assert not (run / "working" / "c.txt").exists()
        assert marker.is_file()
