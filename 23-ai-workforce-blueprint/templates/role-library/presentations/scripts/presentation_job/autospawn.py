"""presentation_job/autospawn.py -- the Work-Order Dispatcher auto-spawn helpers.

F11 (Fable review section 15): these five helpers lived in
``presentation_job/__main__.py`` and were reachable ONLY from ``main()``. The
Engine needed them too -- ``phases.Engine._run_agent_phase`` must be able to
notice that the dispatcher servicing this run has died (its own
``--max-lifetime-minutes`` ceiling, an OOM kill, a crash) and start a new one
MID-RUN, because a measured run lasts 22 h and a dispatcher lives 6 h. The
Engine cannot import ``__main__`` for them: ``__main__`` imports
``phases.Engine`` at module scope (a circular import), and under
``python3 -m presentation_job`` the entry module is registered as ``__main__``
rather than ``presentation_job.__main__``, so ``from . import __main__`` would
execute a SECOND copy of it with its own module state.

So the helpers move here, unchanged, and ``__main__`` re-exports them under
their original private names -- ``__main__._spawn_dispatcher_if_available`` and
``__main__._stop_auto_dispatcher`` keep working byte-for-byte for every existing
caller and for tests/test_dispatcher_autospawn.py.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from .state import utcnow


# ---------------------------------------------------------------------------
# F07 -- Work-Order Dispatcher auto-spawn.
#
# THE FAULT THIS CLOSES: work_order_dispatcher.py's own module docstring
# claims it is started "by an operator, a cron, or the Engine's own auto-spawn
# in presentation_job/__main__.py" -- but nothing in this file ever spawned
# it (grep -nE "dispatcher|auto.spawn|autospawn|DISPATCH" against this file
# returned zero matches before this fix). phases.py's Engine._run_agent_phase
# writes working/work-orders/<phase>.json for every agent-authored phase, then
# polls the filesystem for the produced artifact for up to phase.budget_minutes
# -- it is a stall DETECTOR, not a dispatcher (see that method's own
# docstring). With nothing consuming work-orders/*.json, every agent-authored
# phase blocked silently until its budget expired, on every real run -- this
# is why an external driver had to be hand-built to keep decks moving.
#
# DESIGN: spawn work_order_dispatcher.py --watch as a plain child process of
# THIS process (the presentation_job.py CLI invocation), started BEFORE
# engine.run()/engine.close() and left running CONCURRENTLY while engine.run()
# executes synchronously in the same process. This is deliberate, not
# incidental -- a serial "run the dispatcher, then run the engine" shape
# DEADLOCKS: the engine blocks on _run_agent_phase's poll loop waiting for the
# very artifact the dispatcher was about to author, and the dispatcher (in a
# serial shape) never gets to run until the engine returns. Proven live.
#
# Why this survives the dispatcher's own getppid guard (dispatcher.py
# watch_run_dir): that guard exits the moment os.getppid() no longer matches
# the pid captured at dispatcher startup, i.e. the moment its spawning parent
# is gone (POSIX reparents an orphan to init/launchd, changing its ppid). A
# bare `nohup ... &` from an interactive shell reparents almost immediately
# once the shell moves on, which is exactly what killed a manually-nohup'd
# instance in testing. Spawning from subprocess.Popen() INSIDE this run's own
# process keeps this process as the dispatcher's real parent for as long as
# this process is alive, which is precisely the lifetime of one engine run
# (this function is called synchronously right before engine.run(), and the
# dispatcher is explicitly stopped in a `finally` the moment engine.run()
# returns or raises -- see _stop_auto_dispatcher below). No fork/exec ever
# replaces this process mid-run, so the ppid the dispatcher captured at
# startup never changes until this process's own natural exit.
#
# Termination / no orphans: _stop_auto_dispatcher (called from a `finally` in
# main()) SIGTERMs (then SIGKILLs on a 10s timeout) the dispatcher the instant
# engine.run() returns or raises, for ANY reason -- so a run that reaches a
# terminal state, a --phase single-phase run (which returns without ever
# setting state["terminal"] -- see watch_run_dir's own orphan-guard comment),
# and an engine exception all stop the dispatcher immediately. The
# dispatcher's own terminal-state check + getppid guard + 6h --max-lifetime-
# minutes ceiling (dispatcher.py) are a SECOND, slower backstop for the case
# this process is itself killed (SIGKILL) before its `finally` can run --
# never the primary mechanism. This closes the orphaned-dispatcher-spinning-
# declines-for-hours failure mode observed live.
#
# No double-spawn: a small lock file (working/dispatcher-autospawn.lock,
# {pid, started_at}) records the pid of any dispatcher this mechanism spawned
# for this run dir. Before spawning, an existing lock's pid is checked for
# liveness (os.kill(pid, 0)) -- a live holder means a dispatcher already
# watches this run dir (a prior auto-spawn that outlived its engine, or an
# operator's own manual `--watch`), so this call is a no-op. This is a
# best-effort convenience check, not a new locking primitive over
# state.json/.job.lock -- work_order_dispatcher.py's own atomic O_CREAT|O_EXCL
# per-phase claim (dispatcher.py) is still the real safety net if two
# dispatchers ever do run concurrently against the same run dir.
#
# Overridable: --no-auto-dispatch or PRESENTATION_AUTO_DISPATCH=0 disables
# spawning entirely, so an operator can run work_order_dispatcher.py by hand
# without an auto-spawned instance racing it.
# ---------------------------------------------------------------------------

def _pid_is_alive(pid: int) -> bool:
    """True if `pid` names a process this user can at least see.

    A PermissionError from os.kill(pid, 0) still means the process exists
    (owned by someone else, or a privilege boundary) -- only
    ProcessLookupError means the pid is genuinely free."""
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _auto_dispatch_lock_path(run_dir: Path) -> Path:
    return run_dir / "working" / "dispatcher-autospawn.lock"


def _auto_dispatch_disabled(disabled_flag: bool) -> bool:
    if disabled_flag:
        return True
    return os.environ.get("PRESENTATION_AUTO_DISPATCH", "1").strip().lower() in (
        "0", "false", "no", "off")


def _spawn_dispatcher_if_available(run_dir: Path, scripts_dir: Path,
                                    disabled: bool = False) -> Optional[subprocess.Popen]:
    """Auto-spawn work_order_dispatcher.py --watch, scoped to `run_dir`, as a
    child of THIS process. See the module-level design note above this
    function for the full rationale (concurrency, getppid survival,
    termination, no-double-spawn). Call this BEFORE engine.run()/
    engine.close(), never after -- see the deadlock warning above.

    Returns the Popen handle on a real spawn, or None when auto-dispatch is
    disabled (flag/env) or a dispatcher is already alive for this run dir.
    The caller owns the returned handle and MUST pass it to
    _stop_auto_dispatcher when the run this call was made for is done,
    regardless of how it finished (success, block, or exception)."""
    if _auto_dispatch_disabled(disabled):
        return None

    lock_path = _auto_dispatch_lock_path(run_dir)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    existing_pid = None
    if lock_path.is_file():
        try:
            recorded = json.loads(lock_path.read_text(encoding="utf-8"))
            existing_pid = int(recorded.get("pid") or 0)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            existing_pid = None
    if existing_pid and _pid_is_alive(existing_pid):
        print(f"[auto-dispatch] work_order_dispatcher.py already running for "
              f"{run_dir} (pid {existing_pid}) -- not spawning a second one", flush=True)
        return None

    dispatcher_entry = scripts_dir / "work_order_dispatcher.py"
    argv = [sys.executable, str(dispatcher_entry), "--run-dir", str(run_dir), "--watch"]
    try:
        proc = subprocess.Popen(argv, cwd=str(scripts_dir),
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        print(f"[auto-dispatch] could not spawn {dispatcher_entry}: {exc}",
              file=sys.stderr, flush=True)
        return None

    try:
        lock_path.write_text(
            json.dumps({"pid": proc.pid, "started_at": utcnow(), "run_dir": str(run_dir)}),
            encoding="utf-8")
    except OSError:
        pass
    print(f"[auto-dispatch] spawned work_order_dispatcher.py --watch (pid {proc.pid}) "
          f"for {run_dir}", flush=True)
    return proc


def _stop_auto_dispatcher(run_dir: Path, proc: Optional[subprocess.Popen]) -> None:
    """Stop a dispatcher THIS process spawned via _spawn_dispatcher_if_available,
    and release the lock -- called from a `finally` around engine.run() so it
    runs on every exit path (done, blocked, or exception). `proc=None` means
    this call never spawned one (disabled, or one was already running) --
    in that case there is nothing to stop and, critically, nothing to delete:
    a lock file that exists in that case belongs to a still-running instance
    this call does not own, and must be left alone."""
    if proc is None:
        return
    if proc.poll() is None:
        try:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        except Exception:  # noqa: BLE001 -- stopping the dispatcher must never crash the engine exit
            pass
    lock_path = _auto_dispatch_lock_path(run_dir)
    try:
        if lock_path.is_file():
            try:
                recorded = json.loads(lock_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                recorded = {}
            if recorded.get("pid") == proc.pid:
                lock_path.unlink()
    except OSError:
        pass
