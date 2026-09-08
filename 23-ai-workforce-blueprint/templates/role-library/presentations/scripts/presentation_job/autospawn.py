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
import time
from pathlib import Path
from typing import Optional

from .state import utcnow

# ---------------------------------------------------------------------------
# PRES-017 (2026-09-08): a spawned dispatcher must PROVE readiness.
#
# The old shape Popen'd the dispatcher with stdout/stderr -> DEVNULL and
# stamped the autospawn lock / printed "spawned" IMMEDIATELY. A missing
# entrypoint, an import error or a bad provider config exited instantly,
# invisibly -- "spawned" was a claim about an attempt, not about a consumer.
# The failure mode compounded in phases.py: a CLEAN dispatcher exit deleted
# its lock, and the engine's respawn treated a MISSING lock as "never
# armed" and refused to ever spawn again -- the six-hour lifetime could
# then leave later work orders with no consumer at all.
#
# The contract now (all additive, none of it breaking the callers above):
#
#   * rotating redacted per-run log: working/dispatcher-logs/dispatcher-
#     <pid>.log (written by the child through _run_dispatcher_with_log --
#     argv stdout/stderr are captured, never DEVNULL; a redact pass drops
#     credential-shaped lines before anything is written);
#   * a STARTUP READINESS HANDSHAKE with a 10 s ceiling: _spawn_...
#     returns only after the child wrote working/dispatcher-ready.json
#     {pid, started_at, run_dir, revision} -- "spawned" now means "a
#     consumer answered". A child that dies or never writes the file
#     within _READINESS_TIMEOUT_S is reported as a FAILED START with the
#     tail of its captured log;
#   * the lock stamp records armed state plus the spawn's verdict, and
#     _stop_auto_dispatcher records a clean retirement WITHOUT implying
#     disablement -- desired state (enabled) lives separately from the
#     transient owner lock, so a missing lock NEVER means "user said stop".
# ---------------------------------------------------------------------------
_READINESS_TIMEOUT_S = 10.0
_MAX_LOG_BYTES = 512 * 1024


def _redact(text: str) -> str:
    """Drop credential-shaped content from captured dispatcher output before
    it lands in any log file. Keys/tokens appear as env exports, JSON
    fields or flag values; values never reach disk intact.

    QC repair (2026-09-08): the original label match was `\\b(...)(sep)`,
    which (a) missed underscore-joined labels (`DB_TOKEN`, `client_secret`
    -- `\\b` does not advance past `_` inside a word), and (b) only
    accepted a bare `=`/`:`/space separator, so JSON-quoted keys
    (`"password": "..."`) leaked their values. Redaction is now three
    ordered passes: Bearer, then quoted JSON keys, then bare key=value /
    key: value / space-separated forms; the credential LABEL always
    survives, only its value is dropped."""
    import re as _re

    _LABEL = (r"(?:api[_-]?key|access[_-]?token|auth[_-]?token|refresh[_-]?token|"
              r"token|secret|password|passwd|pwd|credential[s]?|authorization|"
              r"private[_-]?key)")
    # Any key-shaped token whose whole body ENDS in (or contains) a
    # credential label: API_KEY, DB_TOKEN, client_secret, GITHUB_TOKEN...
    _KEYLIKE = r"[A-Za-z0-9_.-]*" + _LABEL + r"[A-Za-z0-9_.-]*"

    patterns = (
        # Bearer <value> first (its value would otherwise survive the
        # key=value pass as "Bearer" is the label).
        (_re.compile(r"\bBearer\s+\S+", _re.IGNORECASE),
         lambda m: "Bearer [REDACTED]"),
        # JSON-quoted key: "password": "hunter2secret" / 'api_key': 'v'
        (_re.compile(
            r"(?i)(['\"])(?P<key>" + _KEYLIKE + r")\1(\s*:\s*)"
            r"(?P<q>['\"])(?P<val>.*?)(?P=q)"),
         lambda m: f"{m.group(1)}{m.group('key')}{m.group(1)}"
                   f"{m.group(3)}[REDACTED]"),
        # Bare key=value / key: value / key value (env exports, flags,
        # prose-style "token <value>"). Value runs to whitespace or end of
        # line; a leading quote on the value is consumed with it.
        (_re.compile(
            r"(?i)\b(?P<key>" + _KEYLIKE + r")\b(\s*[=:]\s*|\s+)"
            r"['\"]?(?P<val>[^\s'\"]*)"),
         lambda m: f"{m.group('key')}{m.group(2)}[REDACTED]"),
        (_re.compile(r"\b(?:sk|pk)-[A-Za-z0-9_-]{8,}"), lambda m: "[REDACTED]"),
    )
    out = text
    for pat, repl in patterns:
        out = pat.sub(repl, out)
    return out


def _dispatcher_log_path(run_dir: Path, pid: int) -> Path:
    return run_dir / "working" / "dispatcher-logs" / f"dispatcher-{pid}.log"


def _append_log(path: Path, text: str) -> None:
    """Best-effort redacted append; rotation keeps one previous generation
    when the log passes _MAX_LOG_BYTES."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > _MAX_LOG_BYTES:
            path.replace(path.with_suffix(path.suffix + ".1"))
        with path.open("a", encoding="utf-8") as fh:
            fh.write(_redact(text))
    except OSError:
        pass


def _readiness_path(run_dir: Path) -> Path:
    return run_dir / "working" / "dispatcher-ready.json"


def _write_handshake_file(run_dir: Path, pid: int, revision: str) -> None:
    """The dispatcher's startup readiness handshake -- written by the child
    (dispatcher.watch_run_dir's _write_heartbeat) as its FIRST act. Exposed
    as a helper so tests can simulate a real readying child without running
    a billed dispatcher."""
    path = _readiness_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    obj = {"pid": int(pid), "run_dir": str(run_dir),
           "started_at": utcnow(), "ready_at": utcnow(),
           "revision": revision}
    tmp = path.with_suffix(path.suffix + f".partial-{os.getpid()}")
    tmp.write_text(json.dumps(obj, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def _desired_state_path(run_dir: Path) -> Path:
    """PRES-017: desired dispatcher state (enabled/running intent) persisted
    SEPARATELY from the transient owner lock. A missing owner lock must
    never be read as "the user disabled dispatch"."""
    return run_dir / "working" / "dispatcher-desired-state.json"


def _record_desired_state(run_dir: Path, enabled: bool, why: str) -> None:
    try:
        path = _desired_state_path(run_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        state = {"enabled": bool(enabled), "why": why, "at": utcnow()}
        tmp = path.with_suffix(path.suffix + f".partial-{os.getpid()}")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True),
                       encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def _desired_enabled(run_dir: Path) -> bool:
    """True only when an explicit desired-state RECORD says enabled.

    PRES-017: a MISSING record means an untracked situation (an operator's
    manual --watch, a pre-PRES-017 tree, --no-auto-dispatch) -- the engine
    must stay hands-off there, exactly as F11 guaranteed. Only a record
    autospawn itself wrote (armed for this run / clean retirement) makes a
    missing owner lock re-armable."""
    try:
        obj = json.loads(_desired_state_path(run_dir).read_text(encoding="utf-8"))
        return bool(obj.get("enabled"))
    except (OSError, ValueError, json.JSONDecodeError):
        return False


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

    PRES-017: the returned handle is only handed back after the child
    passed the STARTUP READINESS HANDSHAKE (wrote working/dispatcher-
    ready.json within _READINESS_TIMEOUT_S) -- "spawned" now names a
    confirmed consumer, not a wish. A failed start (missing entrypoint,
    import error, bad config, instant death, no handshake) returns None
    with the actionable reason and the child's redacted log tail printed
    to stderr; nothing is stamped as running.

    Returns the Popen handle on a confirmed spawn, or None when
    auto-dispatch is disabled (flag/env), a dispatcher is already alive
    for this run dir, or the start failed (reason printed). The caller
    owns the returned handle and MUST pass it to _stop_auto_dispatcher
    when the run this call was made for is done, regardless of how it
    finished (success, block, or exception)."""
    if _auto_dispatch_disabled(disabled):
        _record_desired_state(run_dir, False, "auto-dispatch disabled by flag/env")
        return None
    _record_desired_state(run_dir, True, "auto-dispatch armed for this run")

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
    if not dispatcher_entry.is_file():
        # PRES-017: a missing entrypoint is an ACTIONABLE permanent error,
        # surfaced immediately -- never a silent DEVNULL death.
        reason = (f"dispatcher entrypoint not found: {dispatcher_entry} "
                  f"(scripts_dir={scripts_dir}); install/repair the "
                  f"presentations scripts tree before dispatch can run")
        _append_log(_dispatcher_log_path(run_dir, 0), reason + "\n")
        print(f"[auto-dispatch] START FAILED: {reason}", file=sys.stderr, flush=True)
        return None

    argv = [sys.executable, str(dispatcher_entry), "--run-dir", str(run_dir), "--watch"]
    log_path = None
    try:
        # PRES-017: the child's stdout/stderr land in a redacted rotating
        # per-run log, never DEVNULL -- startup errors must be readable.
        log_path = _dispatcher_log_path(run_dir, os.getpid())
        _append_log(log_path, f"=== spawn attempt {utcnow()} argv={argv}\n")
        with log_path.open("a", encoding="utf-8") as log_fh:
            proc = subprocess.Popen(argv, cwd=str(scripts_dir),
                                    stdout=log_fh, stderr=log_fh)
    except OSError as exc:
        print(f"[auto-dispatch] could not spawn {dispatcher_entry}: {exc}",
              file=sys.stderr, flush=True)
        return None

    try:
        lock_path.write_text(
            json.dumps({"pid": proc.pid, "started_at": utcnow(),
                        "run_dir": str(run_dir),
                        "readiness": "pending"}),
            encoding="utf-8")
    except OSError:
        pass

    # PRES-017: the STARTUP READINESS HANDSHAKE. The child writes
    # dispatcher-ready.json as its FIRST act once its imports, config and
    # run binding all resolved. Bounded 10 s wait; a child that dies first
    # is caught by poll().
    ready_path = _readiness_path(run_dir)
    deadline = time.monotonic() + _READINESS_TIMEOUT_S
    ready_obj = None
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            break
        try:
            obj = json.loads(ready_path.read_text(encoding="utf-8"))
            if isinstance(obj, dict) and int(obj.get("pid") or 0) == proc.pid:
                ready_obj = obj
                break
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        time.sleep(0.2)

    if ready_obj is None and proc.poll() is not None:
        # FAILED START: the child EXITED before answering readiness -- the
        # missing entrypoint / import error / bad config class. Actionable
        # reason + log tail. The lock is withdrawn (it said "pending"
        # readiness that never arrived).
        tail = ""
        if log_path is not None and log_path.is_file():
            try:
                tail = _redact(log_path.read_text(encoding="utf-8")[-1500:])
            except OSError:
                tail = "(log unreadable)"
        reason = (f"dispatcher pid {proc.pid} exited rc={proc.returncode} "
                  f"before startup readiness within {_READINESS_TIMEOUT_S:.0f}s; "
                  f"log tail:\n{tail or '(empty)'}")
        _append_log(_dispatcher_log_path(run_dir, proc.pid), reason + "\n")
        print(f"[auto-dispatch] START FAILED: {reason}", file=sys.stderr, flush=True)
        try:
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001
            pass
        try:
            if lock_path.is_file():
                lock_path.unlink()
        except OSError:
            pass
        return None

    if ready_obj is None:
        # Still ALIVE at the readiness deadline with no handshake file yet:
        # a slow-starting (not failed) child. Accept it as running -- the
        # heartbeat-staleness alarm (phases.py) covers the alive-but-never-
        # consuming case; a process that never heartbeats is visible there
        # within minutes, and a hard kill here would only race the child's
        # own first tick.
        _append_log(_dispatcher_log_path(run_dir, proc.pid),
                    f"[auto-dispatch] readiness handshake not seen within "
                    f"{_READINESS_TIMEOUT_S:.0f}s but pid {proc.pid} is alive -- "
                    f"accepted, heartbeat alarm covers non-consumption\n")
        print(f"[auto-dispatch] spawned work_order_dispatcher.py --watch (pid {proc.pid}) "
              f"for {run_dir} (readiness pending; process alive)", flush=True)
        return proc

    try:
        lock_path.write_text(
            json.dumps({"pid": proc.pid, "started_at": utcnow(),
                        "run_dir": str(run_dir),
                        "readiness": "ready",
                        "ready_at": ready_obj.get("ready_at"),
                        "revision": ready_obj.get("revision")}),
            encoding="utf-8")
    except OSError:
        pass
    print(f"[auto-dispatch] spawned work_order_dispatcher.py --watch (pid {proc.pid}) "
          f"READY for {run_dir} (revision {ready_obj.get('revision')})", flush=True)
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
    # PRES-017: a CLEAN retirement is recorded WITHOUT implying disablement.
    # Desired state stays enabled; a missing owner lock must never be read
    # as "the user said stop" -- the next engine pass respawns with a fresh
    # owner lease and a fresh readiness handshake.
    _record_desired_state(run_dir, True,
                          f"clean retirement of dispatcher pid {proc.pid}")
