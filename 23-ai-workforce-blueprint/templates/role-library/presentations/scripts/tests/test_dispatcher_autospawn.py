"""Tests for F07 -- the Work-Order Dispatcher auto-spawn (presentation_job/__main__.py).

THE FAULT (orchestrator-verified, this is what this file proves fixed):
work_order_dispatcher.py's own module docstring says it is started by "the
Engine's own auto-spawn in presentation_job/__main__.py". Before this fix,
nothing in __main__.py ever spawned it -- grep -nE
"dispatcher|auto.spawn|autospawn|DISPATCH" against __main__.py returned ZERO
matches. phases.py's Engine._run_agent_phase() writes
working/work-orders/<phase>.json for every agent-authored phase, then polls
the filesystem for the produced artifact for up to phase.budget_minutes; it
is a stall DETECTOR, not a dispatcher (see that method's own docstring). With
nothing consuming work-orders/*.json, an agent-authored phase blocked
silently until its budget expired on every real run -- the run stalled
forever with no cron, no launchd entry, and no in-process mechanism ever
servicing it.

This file tests presentation_job.__main__._spawn_dispatcher_if_available /
_stop_auto_dispatcher directly (Part 1), then proves the real wiring through
the actual `main()` CLI entrypoint: starting an engine run (--run) for a run
dir that already carries an outstanding agent work order results in
work_order_dispatcher.py being spawned for it, BEFORE (concurrently with,
never serially after) engine.run() is called (Part 2) -- the exact ordering
that avoids the live-proven "dispatcher then engine" deadlock (the engine
would otherwise block on the very artifact the dispatcher was about to
author).

subprocess.Popen is mocked in EVERY test in this file. A real (unmocked)
work_order_dispatcher.py --watch process would call DeepSeek V4 Flash direct
to author phase content for a real work order -- a real, billed API call --
which a test suite must never trigger, so no test here ever lets a real
dispatcher process start.

Flat file inside tests/, manages its own import path -- matching every
sibling in this directory (test_engine_client_report.py, test_resume.py).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import __main__ as pj_main  # noqa: E402
from presentation_job.manifest import Manifest  # noqa: E402
from presentation_job.phases import Engine  # noqa: E402
from presentation_job.state import StateStore, STATE_SCHEMA_VERSION, utcnow  # noqa: E402


def _canonical_manifest_path() -> Path:
    """Same two-tier resolution every sibling test in this directory uses
    (test_presentation_job.py._canonical_manifest, test_engine_client_report.py)."""
    deployed = SCRIPTS.parent / "sops" / "PIPELINE-MANIFEST.json"
    if deployed.is_file():
        return deployed
    cur = SCRIPTS
    for _ in range(12):
        cand = cur / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
        if cand.is_file():
            return cand
        if cur.parent == cur:
            break
        cur = cur.parent
    raise FileNotFoundError(
        "PIPELINE-MANIFEST.json not found (looked in scripts/../sops/ and the "
        "universal-sops/presentation-slide-craft walk-up)")


def _fake_proc(pid: int = None):
    """Stand-in for subprocess.Popen()'s return value. `pid` defaults to THIS
    test process's own pid, so the double-spawn guard's os.kill(pid, 0)
    liveness check finds a genuinely live process without ever starting one."""
    proc = mock.Mock()
    proc.pid = pid if pid is not None else os.getpid()
    proc.poll.return_value = None  # still running
    proc.terminate = mock.Mock()
    proc.wait = mock.Mock(return_value=0)
    proc.kill = mock.Mock()
    return proc


# ---------------------------------------------------------------------------
# Part 1: _spawn_dispatcher_if_available / _stop_auto_dispatcher in isolation
# ---------------------------------------------------------------------------
class TestSpawnDispatcherIfAvailable:
    def test_spawns_with_expected_argv(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PRESENTATION_AUTO_DISPATCH", raising=False)
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        with mock.patch.object(pj_main.subprocess, "Popen") as popen:
            popen.return_value = _fake_proc()
            proc = pj_main._spawn_dispatcher_if_available(run_dir, SCRIPTS)
        assert proc is not None
        popen.assert_called_once()
        argv = popen.call_args.args[0]
        assert argv[0] == sys.executable
        assert argv[1] == str(SCRIPTS / "work_order_dispatcher.py")
        assert "--run-dir" in argv and str(run_dir) in argv
        assert "--watch" in argv

    def test_writes_lock_file_with_spawned_pid(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        with mock.patch.object(pj_main.subprocess, "Popen") as popen:
            popen.return_value = _fake_proc(pid=424242)
            pj_main._spawn_dispatcher_if_available(run_dir, SCRIPTS)
        lock = json.loads((run_dir / "working" / "dispatcher-autospawn.lock").read_text())
        assert lock["pid"] == 424242

    def test_does_not_double_spawn_when_lock_holder_is_alive(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        with mock.patch.object(pj_main.subprocess, "Popen") as popen:
            popen.return_value = _fake_proc(pid=os.getpid())  # this test process: genuinely alive
            first = pj_main._spawn_dispatcher_if_available(run_dir, SCRIPTS)
            second = pj_main._spawn_dispatcher_if_available(run_dir, SCRIPTS)
        assert first is not None
        assert second is None
        assert popen.call_count == 1, "a second call must not start a second dispatcher"

    def test_stale_lock_from_a_dead_pid_still_spawns(self, tmp_path):
        run_dir = tmp_path / "run"
        (run_dir / "working").mkdir(parents=True)
        dead_pid = 9_999_999  # essentially guaranteed not alive -> ProcessLookupError
        (run_dir / "working" / "dispatcher-autospawn.lock").write_text(
            json.dumps({"pid": dead_pid, "started_at": "x"}))
        with mock.patch.object(pj_main.subprocess, "Popen") as popen:
            popen.return_value = _fake_proc()
            proc = pj_main._spawn_dispatcher_if_available(run_dir, SCRIPTS)
        assert proc is not None
        popen.assert_called_once()

    def test_disabled_by_env_var(self, tmp_path, monkeypatch):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        monkeypatch.setenv("PRESENTATION_AUTO_DISPATCH", "0")
        with mock.patch.object(pj_main.subprocess, "Popen") as popen:
            proc = pj_main._spawn_dispatcher_if_available(run_dir, SCRIPTS)
        assert proc is None
        popen.assert_not_called()

    def test_disabled_by_flag(self, tmp_path, monkeypatch):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        monkeypatch.delenv("PRESENTATION_AUTO_DISPATCH", raising=False)
        with mock.patch.object(pj_main.subprocess, "Popen") as popen:
            proc = pj_main._spawn_dispatcher_if_available(run_dir, SCRIPTS, disabled=True)
        assert proc is None
        popen.assert_not_called()


class TestStopAutoDispatcher:
    def test_terminates_live_process_and_removes_its_own_lock(self, tmp_path):
        run_dir = tmp_path / "run"
        (run_dir / "working").mkdir(parents=True)
        lock_path = run_dir / "working" / "dispatcher-autospawn.lock"
        proc = _fake_proc(pid=555)
        lock_path.write_text(json.dumps({"pid": 555, "started_at": "x"}))
        pj_main._stop_auto_dispatcher(run_dir, proc)
        proc.terminate.assert_called_once()
        assert not lock_path.exists()

    def test_none_proc_leaves_an_existing_lock_alone(self, tmp_path):
        # proc=None means this call never spawned one (disabled, or one was
        # already running) -- a lock file found in that case belongs to an
        # instance this call does not own and must not be deleted.
        run_dir = tmp_path / "run"
        (run_dir / "working").mkdir(parents=True)
        lock_path = run_dir / "working" / "dispatcher-autospawn.lock"
        lock_path.write_text(json.dumps({"pid": os.getpid(), "started_at": "x"}))
        pj_main._stop_auto_dispatcher(run_dir, None)
        assert lock_path.exists(), "must not delete another instance's live lock"


# ---------------------------------------------------------------------------
# Part 2: the real wiring, through main() -- THE MANDATORY TEST.
#
# "starting an engine run for a run dir with an outstanding agent work order
# results in a dispatcher being spawned for it."
# ---------------------------------------------------------------------------
def _build_run_dir_with_outstanding_work_order(tmp_path) -> Path:
    """A run dir in exactly the state the live fault leaves behind: an
    agent-authored phase (P-SP-CLAIM) has already written its work order to
    working/work-orders/, the phase is still marked "running" (never
    serviced), and state.json is otherwise a real, schema-valid job document
    pinned to the real canonical manifest."""
    run_dir = tmp_path / "run"
    (run_dir / "working" / "work-orders").mkdir(parents=True)
    manifest_path = _canonical_manifest_path()
    manifest = Manifest(manifest_path)
    phase_id = "P-SP-CLAIM"
    phase = manifest.phase(phase_id)
    assert phase.executor_kind == "agent", (
        "fixture assumption broken: P-SP-CLAIM must stay agent-authored "
        "for this test to exercise the real fault scenario")

    order = {
        "phase": phase_id, "owning_role": phase.owning_role,
        "produces_artifact": phase.produces_artifact, "verifier": phase.verifier,
        "budget_minutes": phase.budget_minutes, "issued_at": utcnow(),
    }
    (run_dir / "working" / "work-orders" / f"{phase_id}.json").write_text(
        json.dumps(order, indent=2), encoding="utf-8")

    state = {
        "schema_version": STATE_SCHEMA_VERSION, "job_id": "pj_f07_autospawn_test",
        "run_dir": str(run_dir), "created_at": utcnow(),
        "manifest_path": str(manifest_path), "manifest_version": manifest.version,
        "manifest_sha256": manifest.sha256, "presentation_type": "signature",
        "requester": {"chat_id": "test-chat"}, "intake": {},
        "current_phase": phase_id,
        "phases": [{"id": phase_id, "status": "running", "artifacts": [], "sha256": {},
                    "attempts": 1, "heal_events": [], "attested_at": None}],
        "gates": {}, "waivers": [], "events": [], "sent": {"ack": {"count": 1}},
        "undeliverable": [], "heartbeat": {}, "terminal": None,
    }
    StateStore(run_dir).save(state)
    return run_dir


class TestEndToEndAutoSpawnWiring:
    def test_run_spawns_dispatcher_before_engine_run(self, tmp_path, monkeypatch):
        """The mandatory test: `presentation_job.py --run --run-dir <run with
        an outstanding agent work order>` spawns work_order_dispatcher.py for
        that run dir, and does so BEFORE engine.run() executes -- concurrent,
        never serial (a serial dispatcher-then-engine shape deadlocks: proven
        live, see the module-level design note in __main__.py)."""
        monkeypatch.delenv("PRESENTATION_AUTO_DISPATCH", raising=False)
        run_dir = _build_run_dir_with_outstanding_work_order(tmp_path)

        call_order = []

        def fake_engine_run(self, only=None, until=None):
            call_order.append("engine.run")
            return 0

        def fake_popen(argv, **kw):
            call_order.append("dispatcher.popen")
            return _fake_proc()

        with mock.patch.object(Engine, "run", fake_engine_run), \
             mock.patch.object(pj_main.subprocess, "Popen") as popen:
            popen.side_effect = fake_popen
            rc = pj_main.main(["--run", "--run-dir", str(run_dir)])

        assert rc == 0
        popen.assert_called_once()
        argv = popen.call_args.args[0]
        assert argv[1] == str(SCRIPTS / "work_order_dispatcher.py")
        assert "--run-dir" in argv and str(run_dir) in argv
        assert "--watch" in argv
        assert call_order == ["dispatcher.popen", "engine.run"], (
            f"the dispatcher must be spawned BEFORE engine.run() is called, "
            f"got order {call_order}")

    def test_dispatcher_stopped_when_engine_run_returns(self, tmp_path, monkeypatch):
        """The auto-spawned dispatcher must not be left running (no orphans)
        once the engine run it was spawned for is over."""
        monkeypatch.delenv("PRESENTATION_AUTO_DISPATCH", raising=False)
        run_dir = _build_run_dir_with_outstanding_work_order(tmp_path)
        fake = _fake_proc()

        with mock.patch.object(Engine, "run", lambda self, only=None, until=None: 0), \
             mock.patch.object(pj_main.subprocess, "Popen", return_value=fake):
            rc = pj_main.main(["--run", "--run-dir", str(run_dir)])

        assert rc == 0
        fake.terminate.assert_called_once()
        assert not (run_dir / "working" / "dispatcher-autospawn.lock").exists()

    def test_dispatcher_stopped_even_when_engine_run_raises(self, tmp_path, monkeypatch):
        """The `finally` around engine.run() must stop the dispatcher on an
        exception too -- an engine crash must not leave an orphaned
        dispatcher spinning declines for hours (observed live)."""
        monkeypatch.delenv("PRESENTATION_AUTO_DISPATCH", raising=False)
        run_dir = _build_run_dir_with_outstanding_work_order(tmp_path)
        fake = _fake_proc()

        def boom(self, only=None, until=None):
            raise RuntimeError("simulated engine crash")

        with mock.patch.object(Engine, "run", boom), \
             mock.patch.object(pj_main.subprocess, "Popen", return_value=fake):
            with pytest.raises(RuntimeError):
                pj_main.main(["--run", "--run-dir", str(run_dir)])

        fake.terminate.assert_called_once()
        assert not (run_dir / "working" / "dispatcher-autospawn.lock").exists()

    def test_no_auto_dispatch_flag_disables_spawn(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PRESENTATION_AUTO_DISPATCH", raising=False)
        run_dir = _build_run_dir_with_outstanding_work_order(tmp_path)
        with mock.patch.object(Engine, "run", lambda self, only=None, until=None: 0), \
             mock.patch.object(pj_main.subprocess, "Popen") as popen:
            rc = pj_main.main(["--run", "--run-dir", str(run_dir), "--no-auto-dispatch"])
        assert rc == 0
        popen.assert_not_called()

    def test_env_var_disables_spawn(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PRESENTATION_AUTO_DISPATCH", "0")
        run_dir = _build_run_dir_with_outstanding_work_order(tmp_path)
        with mock.patch.object(Engine, "run", lambda self, only=None, until=None: 0), \
             mock.patch.object(pj_main.subprocess, "Popen") as popen:
            rc = pj_main.main(["--run", "--run-dir", str(run_dir)])
        assert rc == 0
        popen.assert_not_called()
