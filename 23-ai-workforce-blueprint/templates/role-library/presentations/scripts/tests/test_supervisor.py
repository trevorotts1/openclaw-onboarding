"""Tests for presentation_job.supervisor -- worker-liveness supervision.

Covers the 2026-08-27 defect: an engine process died mid-run and nothing on the
box detected it, restarted it, or alarmed. Three behaviors are pinned here,
exactly as the fix ticket requires:

  1. dead worker + active run   => restart attempt (with --apply) + visible events
  2. dead worker + no active run => no action at all
  3. repeated failures          => ALARM, not a loop (bounded retries, then stop)

No real sleeps (backoff is injected via `now`), no network, no real engine
spawns except where an explicit assertion needs one (and those spawn nothing:
the child is a python that exits immediately, in a tmp dir).
"""

from __future__ import annotations

import fcntl
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

from presentation_job.supervisor import (
    supervise, worker_liveness, _backoff_seconds,
    ALIVE, DEAD, UNDETERMINED, NO_LOCK,
    DEFAULT_MAX_RESTARTS, DEFAULT_BACKOFF_SECONDS,
    LEDGER_FILENAME, EVENTS_FILENAME, ALARM_FILENAME,
)
from presentation_job.state import LOCK_FILENAME, EXIT_OK, pid_is_alive


NOW = datetime(2026, 8, 27, 21, 0, 0, tzinfo=timezone.utc)


def _run(run_dir: Path, *, phase="P4-RENDER", job="pj_sup_test", terminal=None,
         updated_at=None, dead_pid=999999999, lock=True):
    """Build a run dir the way the engine leaves one behind."""
    run_dir.mkdir(parents=True, exist_ok=True)
    st = {
        "schema_version": 1,
        "job_id": job,
        "run_dir": str(run_dir),
        "terminal": terminal,
        "current_phase": phase,
        "heartbeat": {
            "last_checkpoint_at": NOW.isoformat(timespec="seconds"),
            "current_phase": phase,
            "interval_minutes": 10,
        },
        "updated_at": updated_at or NOW.isoformat(timespec="seconds"),
    }
    (run_dir / "state.json").write_text(json.dumps(st, indent=2))
    if lock:
        (run_dir / LOCK_FILENAME).write_text(f"{dead_pid} {NOW.isoformat()}\n")
    return run_dir


def _alive_lock(run_dir: Path):
    """Hold the run's RunLock from THIS live process -- the real ALIVE shape."""
    fh = (run_dir / LOCK_FILENAME).open("a+")
    fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
    fh.write(f"{os.getpid()} {NOW.isoformat()}\n")
    fh.flush()
    return fh


def _run_sup(root: Path, **kw):
    import io
    kw.setdefault("now", NOW)
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        rc = supervise(root, **kw)
    finally:
        sys.stdout = old
    return rc, buf.getvalue()


def _events(root: Path) -> list:
    p = root / EVENTS_FILENAME
    if not p.is_file():
        return []
    return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# worker_liveness verdicts
# ---------------------------------------------------------------------------

class TestWorkerLiveness:
    def test_held_lock_is_alive_even_with_dead_looking_pid(self, tmp_path):
        rd = _run(tmp_path / "a", dead_pid=os.getpid())
        fh = _alive_lock(rd)
        try:
            verdict, why = worker_liveness(rd)
        finally:
            fh.close()
        assert verdict == ALIVE

    def test_free_lock_and_gone_pid_is_dead(self, tmp_path):
        rd = _run(tmp_path / "a")
        assert pid_is_alive(999999999) is False  # precondition, not assumed
        verdict, _ = worker_liveness(rd)
        assert verdict == DEAD

    def test_no_lock_file_is_not_active(self, tmp_path):
        rd = _run(tmp_path / "a", lock=False)
        verdict, _ = worker_liveness(rd)
        assert verdict == NO_LOCK

    def test_free_lock_but_live_pid_is_undetermined_never_restarted(self, tmp_path):
        # pid reuse / lock-lost worker: the supervisor must refuse to start a
        # second engine over one state.json.
        rd = _run(tmp_path / "a", dead_pid=os.getpid())
        verdict, why = worker_liveness(rd)
        assert verdict == UNDETERMINED

    def test_probe_does_not_create_the_lock_it_tests(self, tmp_path):
        # O_RDWR, never O_CREAT: probing a run with no lock must not
        # manufacture one (that would manufacture an active run).
        rd = _run(tmp_path / "a", lock=False)
        worker_liveness(rd)
        assert not (rd / LOCK_FILENAME).exists()


# ---------------------------------------------------------------------------
# Required behavior 1: dead worker + active run => restart + visible events
# ---------------------------------------------------------------------------

class TestDeadWorkerActiveRun:
    def test_restart_with_apply_and_events(self, tmp_path):
        root = tmp_path
        rd = _run(root / "run-a")
        # A real, instantly-exiting child: the spawn succeeds (a PID exists),
        # which is all _restart needs to report success here.
        rc, out = _run_sup(root, apply=True, scan_depth=1,
                           scripts_dir=Path(_scripts_dir),
                           backoff_seconds=0)
        assert rc == EXIT_OK
        assert "RESTART" in out and "attempt 1/" in out
        events = _events(root)
        kinds = [e["event"] for e in events]
        assert "worker_dead" in kinds, kinds
        assert "restart" in kinds, kinds
        ledger = json.loads((root / LEDGER_FILENAME).read_text())
        assert ledger["runs"][str(rd)]["attempts"] == 1

    def test_report_only_without_apply_withholds_restart_but_emits_death(self, tmp_path):
        root = tmp_path
        _run(root / "run-a")
        rc, out = _run_sup(root, apply=False, scan_depth=1)
        assert rc == EXIT_OK
        assert "WORKER_DEAD" in out
        assert "RESTART_WITHHELD" in out
        kinds = [e["event"] for e in _events(root)]
        assert "worker_dead" in kinds and "restart" not in kinds
        # the ledger records nothing that was not attempted
        ledger = json.loads((root / LEDGER_FILENAME).read_text())
        assert ledger["runs"] == {}

    def test_no_action_on_terminal_run(self, tmp_path):
        root = tmp_path
        _run(root / "done", terminal="DONE")
        _run(root / "blocked", terminal="BLOCKED")
        rc, out = _run_sup(root, apply=True, scan_depth=1)
        assert rc == EXIT_OK and "DEAD" not in out.replace("worker_dead", "")
        assert [e for e in _events(root) if e["event"] == "worker_dead"] == []

    def test_no_action_on_abandoned_run(self, tmp_path):
        # ABANDONED is the sanctioned retirement marker (FAULT #11): stand
        # down, never restart, never alarm.
        root = tmp_path
        _run(root / "gone", terminal="ABANDONED")
        rc, out = _run_sup(root, apply=True, scan_depth=1)
        assert rc == EXIT_OK
        assert "WORKER_DEAD" not in out

    def test_no_action_when_no_active_run_no_lock(self, tmp_path):
        root = tmp_path
        _run(root / "never-started", lock=False)
        rc, out = _run_sup(root, apply=True, scan_depth=1)
        assert rc == EXIT_OK
        assert "not active (no lock)" in out
        assert [e for e in _events(root) if e["event"] == "worker_dead"] == []

    def test_stale_dead_run_is_never_restarted(self, tmp_path):
        # A dead run abandoned days ago is a corpse, not a casualty.
        root = tmp_path
        _run(root / "corpse", updated_at=(NOW - timedelta(hours=100)).isoformat(timespec="seconds"))
        rc, out = _run_sup(root, apply=True, scan_depth=1, max_idle_hours=72.0)
        assert rc == EXIT_OK
        assert "STALE_DEAD_RUN" in out
        kinds = [e["event"] for e in _events(root)]
        assert "stale_dead_run" in kinds and "restart" not in kinds

    def test_fresh_dead_run_is_within_restart_window(self, tmp_path):
        root = tmp_path
        _run(root / "fresh", updated_at=(NOW - timedelta(hours=1)).isoformat(timespec="seconds"))
        rc, out = _run_sup(root, apply=False, scan_depth=1, max_idle_hours=72.0)
        # fresh => still a candidate; report-only => withheld, not skipped
        assert "RESTART_WITHHELD" in out and "STALE_DEAD_RUN" not in out


# ---------------------------------------------------------------------------
# Required behavior 3: repeated failures => alarm, not loop
# ---------------------------------------------------------------------------

class TestAlarmNotLoop:
    def _dead_run(self, root: Path):
        return _run(root / "run-doomed")

    def _scripts_missing(self, tmp_path):
        # an empty scripts dir => _restart's spawn fails deterministically,
        # which charges the budget exactly like a real crash-loop would.
        return tmp_path / "no-scripts-here"

    def test_budget_exhaustion_raises_alarm_and_stops(self, tmp_path):
        root = tmp_path
        _run(root / "run-doomed")
        scripts = self._scripts_missing(tmp_path)
        # Pass 1: attempt 1 fails (charged). Pass 2: attempt 2. Pass 3: attempt
        # 3 hits the cap => alarm. Pass 4: standing alarm, no further attempts.
        seen = []
        for i in range(4):
            rc, out = _run_sup(root, apply=True, scan_depth=1, max_restarts=3,
                               backoff_seconds=0, scripts_dir=scripts)
            seen.append((rc, out))
        rc3, out3 = seen[2]
        rc4, out4 = seen[3]
        assert rc3 == 15 and "ALARM" in out3
        assert rc4 == 15 and "ALARM_STANDING" in out4
        # exactly max_restarts spawn attempts were ever made
        ledger = json.loads((root / LEDGER_FILENAME).read_text())
        assert ledger["runs"][str(root / "run-doomed")]["attempts"] == 3
        assert (root / ALARM_FILENAME).is_file()
        # and the pass AFTER the alarm attempts nothing new
        events_after = [e for e in _events(root) if e["event"] == "restart_failed"]
        assert len(events_after) == 3

    def test_alarm_is_persistent_until_cleared(self, tmp_path):
        root = tmp_path
        _run(root / "run-doomed")
        scripts = self._scripts_missing(tmp_path)
        for _ in range(3):
            _run_sup(root, apply=True, scan_depth=1, max_restarts=3,
                     backoff_seconds=0, scripts_dir=scripts)
        assert (root / ALARM_FILENAME).is_file()
        # alarm file still there on a later report-only pass
        _run_sup(root, apply=False, scan_depth=1, scripts_dir=scripts)
        assert (root / ALARM_FILENAME).is_file()

    def test_recovery_resets_budget_and_clears_alarm(self, tmp_path):
        root = tmp_path
        rd = _run(root / "run-back")
        scripts = self._scripts_missing(tmp_path)
        for _ in range(3):
            _run_sup(root, apply=True, scan_depth=1, max_restarts=3,
                     backoff_seconds=0, scripts_dir=scripts)
        assert (root / ALARM_FILENAME).is_file()
        # worker comes back: a real held lock
        fh = _alive_lock(rd)
        try:
            rc, out = _run_sup(root, apply=False, scan_depth=1, scripts_dir=scripts)
        finally:
            fh.close()
        assert "RECOVERED" in out
        assert not (root / ALARM_FILENAME).exists()
        ledger = json.loads((root / LEDGER_FILENAME).read_text())
        assert str(rd) not in ledger["runs"]

    def test_backoff_defers_second_restart(self, tmp_path):
        root = tmp_path
        _run(root / "run-backoff")
        scripts = self._scripts_missing(tmp_path)
        # attempt 1 at NOW (fails, charged)
        _run_sup(root, apply=True, scan_depth=1, max_restarts=5,
                 backoff_seconds=60, scripts_dir=scripts)
        # 10s later: backoff says wait 60s => deferred, NOT another attempt
        rc, out = _run_sup(root, apply=True, scan_depth=1, max_restarts=5,
                           backoff_seconds=60, scripts_dir=scripts,
                           now=NOW + timedelta(seconds=10))
        assert "RESTART_DEFERRED" in out
        ledger = json.loads((root / LEDGER_FILENAME).read_text())
        assert ledger["runs"][str(root / "run-backoff")]["attempts"] == 1

    def test_backoff_table_is_exponential(self):
        assert _backoff_seconds(0, 60) == 0
        assert _backoff_seconds(1, 60) == 60
        assert _backoff_seconds(2, 60) == 120
        assert _backoff_seconds(3, 60) == 240

    def test_zero_restarts_budget_alarms_immediately_without_spawning(self, tmp_path):
        # --max-restarts 0 means "never restart, alarm on the first death" --
        # the operator's kill switch for a box that must not spawn engines.
        root = tmp_path
        _run(root / "run-zero")
        rc, out = _run_sup(root, apply=True, scan_depth=1, max_restarts=0,
                           backoff_seconds=60, scripts_dir=Path(_scripts_dir))
        assert rc == 15
        assert "ALARM" in out
        assert [e for e in _events(root) if e["event"] == "restart"] == []


# ---------------------------------------------------------------------------
# Scan-root epistemics (the B5/13 doctrine, carried into the supervisor)
# ---------------------------------------------------------------------------

class TestScanRootEpistemics:
    def test_zero_runs_is_exit_14_undetermined_not_pass(self, tmp_path):
        rc, out = _run_sup(tmp_path, scan_depth=1)
        assert rc == 14
        assert "NO state.json" in out

    def test_unreadable_state_is_reported_not_counted_healthy(self, tmp_path):
        root = tmp_path
        rd = root / "corrupt"
        rd.mkdir()
        (rd / "state.json").write_text("{not json at all")
        rc, out = _run_sup(root, scan_depth=1)
        assert rc == EXIT_OK
        assert "UNREADABLE_STATE" in out

    def test_exit_code_family_is_distinguishable(self, tmp_path):
        # 0 = checked and fine, 14 = checked nothing, 15 = gave up loudly.
        assert EXIT_OK == 0
        root = tmp_path
        rc_empty, _ = _run_sup(root, scan_depth=1)
        assert rc_empty == 14
        _run(root / "doomed")
        missing = tmp_path / "no-scripts-here"
        for _ in range(3):
            rc_alarm, _ = _run_sup(root, apply=True, scan_depth=1, max_restarts=3,
                                   backoff_seconds=0, scripts_dir=missing)
        assert rc_alarm == 15


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

class TestCliWiring:
    def test_cli_flags_parse(self):
        from presentation_job.__main__ import build_parser
        p = build_parser()
        a = p.parse_args(["--supervise", "--scan-root", "/tmp/x", "--apply",
                          "--max-restarts", "5", "--supervisor-backoff", "30",
                          "--max-idle-hours", "48"])
        assert a.supervise and a.apply
        assert a.max_restarts == 5 and a.supervisor_backoff == 30
        assert a.max_idle_hours == 48.0

    def test_cli_supervise_defaults_match_module_defaults(self):
        from presentation_job.__main__ import build_parser
        a = build_parser().parse_args(["--supervise", "--scan-root", "/tmp/x"])
        assert a.max_restarts is None and a.supervisor_backoff is None
        assert a.max_idle_hours == 72.0

    def test_cli_supervise_requires_scan_root(self, capsys):
        from presentation_job.__main__ import main
        try:
            main(["--supervise"])
        except SystemExit as exc:
            assert exc.code == 2  # argparse EXIT_USAGE
        else:
            raise AssertionError("--supervise without --scan-root must die")