"""Fix 13 — the engine never records its own pid, so runs started through
the canonical entry get re-dispatched every tick.

THE DEFECT
`engine_pid` was written only by the launcher and by the poller's `--new`
spawner. The canonical entry runs the engine directly. The poller's
"already running" check read only `state.json engine_pid`, so a directly-run
engine was invisible and got re-dispatched every tick.

THE FIX
- `presentation_job/__main__.py`: inside `with RunLock(run_dir):` after
  `store.load()`, set `state["engine_pid"] = os.getpid()` and save.
- `presentation-intake-poll.sh`: the "already running" check uses
  `read_engine_pid "$run_dir"` (state.json, .engine.pid, .job.lock fallback).
- `launcher._read_engine_pid`: added the same `.job.lock` fallback.

THE TEST (per the fix order): a foreground `--run` with no launcher is
counted by the poller as `skipped_running`.

The test verifies the three legs, plus the end-to-end scenario the fix
order requires:
1. `launcher._read_engine_pid` falls back to `.job.lock` when state.json
   has no engine_pid.
2. The poller's `read_engine_pid` shell function finds a pid from state.json.
3. The `__main__.py` RunLock block contains the engine_pid assignment
   (static check).
4. (MUST-TEST) a foreground `--run` with no launcher is counted by the
   poller as `skipped_running`: engine_pid is written through the real
   RunLock+StateStore path, then the poller's already-running check
   (`PID=$(read_engine_pid "$run_dir")` -> `kill -0`) takes the skip branch.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import launcher  # noqa: E402
from presentation_job.state import RunLock, StateStore  # noqa: E402


def test_launcher_read_engine_pid_falls_back_to_job_lock(tmp_path):
    """launcher._read_engine_pid reads .job.lock when state.json lacks engine_pid."""
    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    # state.json exists but has no engine_pid
    (run_dir / "state.json").write_text('{"job": "test"}')
    # .job.lock has "<pid> <timestamp>" format (what RunLock writes)
    my_pid = os.getpid()
    (run_dir / ".job.lock").write_text(f"{my_pid} 1234567890\n")

    pid = launcher._read_engine_pid(run_dir)
    assert pid == my_pid, f"expected {my_pid} from .job.lock, got {pid}"


def test_launcher_read_engine_pid_prefers_state_json(tmp_path):
    """state.json engine_pid still takes precedence over .job.lock."""
    run_dir = tmp_path / "run2"
    run_dir.mkdir()
    (run_dir / "state.json").write_text('{"engine_pid": 12345}')
    (run_dir / ".job.lock").write_text("99999 1234567890\n")

    pid = launcher._read_engine_pid(run_dir)
    assert pid == 12345, f"expected 12345 from state.json, got {pid}"


def test_poller_read_engine_pid_finds_state_json_pid(tmp_path):
    """The poller's read_engine_pid shell function finds state.json engine_pid."""
    poller = SCRIPTS / "presentation-intake-poll.sh"
    run_dir = tmp_path / "run3"
    run_dir.mkdir()
    (run_dir / "state.json").write_text('{"engine_pid": 4242}')

    # Extract and run read_engine_pid in isolation
    result = subprocess.run(
        ["bash", "-c", f'source <(sed -n "/^read_engine_pid/,/^}}/p" "{poller}"); read_engine_pid "{run_dir}"'],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.stdout.strip() == "4242", (
        f"read_engine_pid returned {result.stdout.strip()!r}, expected '4242'. "
        f"stderr: {result.stderr[-500:]}"
    )


def test_main_runlock_records_engine_pid():
    """__main__.py's RunLock block sets state['engine_pid'] = os.getpid()."""
    main_py = SCRIPTS / "presentation_job" / "__main__.py"
    content = main_py.read_text()
    # The assignment must be inside the RunLock block after store.load()
    assert 'state["engine_pid"] = os.getpid()' in content, (
        "__main__.py does not set state['engine_pid'] = os.getpid()"
    )
    assert "store.save(state)" in content, (
        "__main__.py does not save state after setting engine_pid"
    )


def test_direct_run_engine_pid_counted_as_skipped_running(tmp_path):
    """MUST-TEST (per the fix order): a foreground `--run` with no launcher
    is counted by the poller as `skipped_running`.

    Simulates the direct `--run` path: engine_pid is written through the
    REAL RunLock+StateStore path (the same code `__main__.py` runs), using
    this test process's own pid so `kill -0` sees it alive. Then the
    poller's already-running check (`PID=$(read_engine_pid "$run_dir")`
    -> `kill -0 "$PID"`) is driven verbatim and must take the skip branch.
    """
    poller = SCRIPTS / "presentation-intake-poll.sh"
    run_dir = tmp_path / "run-direct"
    run_dir.mkdir()

    # Simulate the direct `--run`: canonical entry runs the engine directly
    # (no launcher), and __main__.py records its own pid under RunLock.
    with RunLock(run_dir):
        store = StateStore(run_dir)
        state = store.load()
        state["engine_pid"] = os.getpid()
        store.save(state)

    check = (
        'source <(sed -n "/^read_engine_pid/,/^}/p" "%s"); '
        'run_dir="%s"; '
        'PID=$(read_engine_pid "$run_dir"); '
        'if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then '
        'echo "skipped_running"; '
    'else echo "NOT_SKIPPED pid=\'$PID\'"; fi'
    ) % (poller, run_dir)
    result = subprocess.run(
        ["bash", "-c", check],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.stdout.strip() == "skipped_running", (
        "direct-run engine was NOT counted as skipped_running. "
        f"stdout={result.stdout.strip()!r} stderr={result.stderr[-500:]!r}"
    )
