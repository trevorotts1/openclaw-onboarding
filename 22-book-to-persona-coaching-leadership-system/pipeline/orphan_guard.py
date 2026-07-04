#!/usr/bin/env python3
"""
orphan_guard.py — orphan-process prevention for the book-to-persona pipeline.

ROOT CAUSE this fixes: the pipeline is frequently launched as a DETACHED child
(an agent copies orchestrator.py to orchestrator_<slug>.py and runs it in the
background). If the launching agent/workflow is stopped mid-run, the stop reaps
the agent but NOT the detached child — it reparents to launchd/init and keeps
making :cloud calls until it finishes, billing the client. This module is the
SHARED self-defense every orchestrator copy links in, so an interrupted build
can never leave a Python child churning provider calls.

It is BOTH:
  • an importable library (orchestrator.py wires it in main()), and
  • a CLI reaper/sweeper — targeted at a specific run's process GROUP, never a
    blind pkill that could hit an unrelated run.

Env contract (set by run-orchestrator.sh, honoured by every orchestrator copy):
  OPENCLAW_RUN_ID                stable id for this run       (default run-<pid>)
  OPENCLAW_PARENT_PID            launching coordinator pid    (0 = none)
  OPENCLAW_RUN_LOCKFILE          liveness lock; removing it aborts the run
  OPENCLAW_RUN_DIR               where per-run pidfiles live
  OPENCLAW_ORCH_DETACH=1         become a session/group leader (detached launch)
  OPENCLAW_MAX_RUNTIME_SEC       hard wall-clock ceiling      (default 6h)
  OPENCLAW_WATCHDOG_INTERVAL_SEC liveness poll interval       (default 30s)
"""
import glob
import os
import signal
import sys
import threading
import time


def _env_int(name: str, default: int) -> int:
    try:
        return int((os.environ.get(name, "") or "").strip() or default)
    except ValueError:
        return default


RUN_ID = (os.environ.get("OPENCLAW_RUN_ID", "") or "").strip() or f"run-{os.getpid()}"
PARENT_PID = _env_int("OPENCLAW_PARENT_PID", 0)
LIVENESS_LOCK = (os.environ.get("OPENCLAW_RUN_LOCKFILE", "") or "").strip()
MAX_RUNTIME = _env_int("OPENCLAW_MAX_RUNTIME_SEC", 6 * 3600)
INTERVAL = max(1, _env_int("OPENCLAW_WATCHDOG_INTERVAL_SEC", 30))
DETACH = (os.environ.get("OPENCLAW_ORCH_DETACH", "") or "").strip() == "1"

_TERMINATING = False


def _safe(s) -> str:
    return "".join(c if (c.isalnum() or c in "-_.") else "_" for c in str(s))


def pid_alive(pid: int) -> bool:
    """True if pid exists. A PermissionError means it exists but isn't ours."""
    if not pid or int(pid) <= 0:
        return False
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def become_group_leader() -> None:
    """Make this process a session/group leader so signalling its group reaps
    the WHOLE child tree (Phase-5 indexer subprocess, etc.). No-op if already a
    leader, unsupported, or not a detached launch (guarded by the caller)."""
    if not hasattr(os, "setsid"):
        return
    try:
        os.setsid()
    except OSError:
        pass  # already a session/group leader — fine


def run_dir_path(default_dir: str = None) -> str:
    d = (os.environ.get("OPENCLAW_RUN_DIR", "") or "").strip()
    if d:
        return d
    if default_dir:
        return default_dir
    return os.path.join(os.path.expanduser("~"), ".openclaw", "pipeline-runs")


def _pidfile(run_dir: str, run_id: str = None) -> str:
    return os.path.join(run_dir, f"{_safe(run_id or RUN_ID)}.pid")


def write_pidfile(run_dir: str) -> None:
    try:
        os.makedirs(run_dir, exist_ok=True)
        try:
            pgid = os.getpgid(0)
        except OSError:
            pgid = os.getpid()
        with open(_pidfile(run_dir), "w") as f:
            f.write(
                f"pid={os.getpid()}\npgid={pgid}\nrun_id={RUN_ID}\n"
                f"parent={PARENT_PID}\nstarted={int(time.time())}\n"
            )
    except OSError:
        pass


def cleanup_pidfile(run_dir: str, run_id: str = None) -> None:
    try:
        os.unlink(_pidfile(run_dir, run_id))
    except OSError:
        pass


def self_terminate(reason: str, log_fn=None, run_dir: str = None) -> None:
    """Kill this run's process tree and exit hard. Reaps the whole process
    GROUP only when we actually OWN it (detached leader) — so an interactive
    foreground run can never accidentally signal its shell's group."""
    global _TERMINATING
    if _TERMINATING:
        return
    _TERMINATING = True
    say = log_fn or (lambda m: print(m, file=sys.stderr))
    say(f"[orphan-guard] SELF-TERMINATE ({RUN_ID}): {reason}. Stopping this run.")
    if run_dir:
        cleanup_pidfile(run_dir)
    try:
        if os.getpgrp() == os.getpid():  # we are the group leader — reap the tree
            os.killpg(os.getpgrp(), signal.SIGTERM)
            time.sleep(0.2)
            os.killpg(os.getpgrp(), signal.SIGKILL)
    except OSError:
        pass
    os._exit(3)


def install_signal_handlers(log_fn=None, run_dir: str = None) -> None:
    def _handler(signum, _frame):
        self_terminate(f"received signal {signum}", log_fn, run_dir)
    for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        try:
            signal.signal(s, _handler)
        except (ValueError, OSError):
            pass


def start_watchdog_thread(log_fn=None, run_dir: str = None) -> threading.Thread:
    """Daemon thread that self-terminates the moment the parent is gone, the
    liveness lock is removed, or the max runtime is exceeded. A THREAD (not an
    asyncio task) so it fires even while the event loop is blocked in a long
    provider await."""
    started = time.time()

    def _loop():
        while True:
            time.sleep(INTERVAL)
            if PARENT_PID and not pid_alive(PARENT_PID):
                self_terminate(f"parent pid {PARENT_PID} gone (orphaned)", log_fn, run_dir)
                return
            if LIVENESS_LOCK and not os.path.exists(LIVENESS_LOCK):
                self_terminate(f"liveness lock removed (run aborted)", log_fn, run_dir)
                return
            if MAX_RUNTIME and (time.time() - started) > MAX_RUNTIME:
                self_terminate(f"max runtime {MAX_RUNTIME}s exceeded", log_fn, run_dir)
                return

    t = threading.Thread(target=_loop, name="orphan-guard-watchdog", daemon=True)
    t.start()
    return t


def arm(log_fn=None, run_dir: str = None) -> None:
    """One-call setup for orchestrator.py main(): become a group leader (only
    when launched detached), write the run pidfile, install signal handlers and
    the liveness watchdog. Best-effort — never raises into the caller."""
    try:
        if DETACH:
            become_group_leader()
        write_pidfile(run_dir)
        import atexit
        atexit.register(lambda: cleanup_pidfile(run_dir))
        install_signal_handlers(log_fn=log_fn, run_dir=run_dir)
        start_watchdog_thread(log_fn=log_fn, run_dir=run_dir)
        say = log_fn or (lambda m: print(m))
        try:
            pgid = os.getpgrp()
        except OSError:
            pgid = os.getpid()
        say(f"  [orphan-guard] run_id={RUN_ID} pid={os.getpid()} pgid={pgid} "
            f"parent={PARENT_PID or 'none'} — liveness watchdog armed "
            f"(interval={INTERVAL}s, max_runtime={MAX_RUNTIME}s)")
    except Exception as e:  # pragma: no cover - defensive
        (log_fn or (lambda m: print(m)))(f"  [orphan-guard] WARN: could not arm: {e}")


# ── single-run-per-slug lock (fix 4) ─────────────────────────────────────────
def acquire_slug_lock(run_dir: str, slug: str):
    """Return an open, flock-held filehandle, or None if another LIVE run holds
    the lock for this slug (duplicate/overlapping orchestrator refused)."""
    try:
        import fcntl
    except ImportError:
        return open(os.devnull, "w")  # non-POSIX: no locking, don't block
    try:
        os.makedirs(run_dir, exist_ok=True)
        fh = open(os.path.join(run_dir, f"slug-{_safe(slug)}.lock"), "w")
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        fh.write(f"{os.getpid()} {RUN_ID}\n")
        fh.flush()
        return fh
    except (OSError, BlockingIOError):
        return None


def release_slug_lock(fh) -> None:
    try:
        if fh:
            fh.close()
    except OSError:
        pass


# ── CLI reaper / sweeper — TARGETED, never a blind pkill ─────────────────────
def _read_pidfile(path: str):
    d = {}
    try:
        with open(path) as f:
            for line in f:
                if "=" in line:
                    k, v = line.strip().split("=", 1)
                    d[k] = v
    except OSError:
        return None
    return d


def reap_run(run_dir: str, run_id: str, log_fn=None) -> int:
    """Kill EXACTLY the process group recorded for run_id. Never a pkill."""
    say = log_fn or (lambda m: print(m))
    info = _read_pidfile(_pidfile(run_dir, run_id))
    if not info:
        say(f"[reaper] no pidfile for run {run_id}")
        return 1
    try:
        pgid = int(info.get("pgid", "0") or 0)
    except ValueError:
        pgid = 0
    if pgid <= 1:
        say(f"[reaper] run {run_id} has no valid pgid — refusing to signal")
        return 1
    try:
        os.killpg(pgid, signal.SIGTERM)
        time.sleep(0.3)
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError as e:
        say(f"[reaper] killpg({pgid}) failed: {e}")
        return 1
    cleanup_pidfile(run_dir, run_id)
    say(f"[reaper] reaped run {run_id} (pgid {pgid})")
    return 0


def sweep_orphans(run_dir: str, log_fn=None) -> int:
    """Reap every recorded run whose PARENT pid is dead (i.e. orphaned)."""
    say = log_fn or (lambda m: print(m))
    n = 0
    for pf in sorted(glob.glob(os.path.join(run_dir, "*.pid"))):
        info = _read_pidfile(pf)
        if not info:
            continue
        try:
            parent = int(info.get("parent", "0") or 0)
        except ValueError:
            parent = 0
        rid = info.get("run_id") or os.path.basename(pf)[:-4]
        if parent and not pid_alive(parent):
            say(f"[reaper] run {rid}: parent {parent} dead — reaping")
            reap_run(run_dir, rid, log_fn)
            n += 1
    say(f"[reaper] swept {n} orphaned run(s)")
    return 0


def _main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="orphan-guard reaper/sweeper (targeted)")
    ap.add_argument("--run-dir", required=True, help="per-run pidfile directory")
    ap.add_argument("--reap", metavar="RUN_ID", help="reap exactly this run's process group")
    ap.add_argument("--sweep", action="store_true",
                    help="reap every run whose parent pid is dead")
    a = ap.parse_args()
    if a.reap:
        return reap_run(a.run_dir, a.reap)
    if a.sweep:
        return sweep_orphans(a.run_dir)
    ap.error("one of --reap RUN_ID or --sweep is required")
    return 2


if __name__ == "__main__":
    sys.exit(_main())
