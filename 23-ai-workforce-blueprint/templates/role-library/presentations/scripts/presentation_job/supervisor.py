"""Worker-liveness supervisor -- detects a run whose engine PROCESS died mid-flight
and restarts it: bounded, loudly, and never in a storm.

Why this exists, and why watchdog.py did not already cover it
-------------------------------------------------------------
watchdog.py answers "is this run's HEARTBEAT stale?" -- a question about a
timestamp inside state.json. That is a genuinely different question from "is the
process that writes that timestamp still alive?", and the gap between them is
real: on 2026-08-27 the engine for a live deck exited between checkpoints, and
nothing on the box noticed. The heartbeat was recent enough to look healthy right
up until the phase budget expired, and even once it did go stale the watchdog's
only power is to mark a board card blocked -- it has never been able to start
anything. A human had to spot a dead pid.

So this module asks the process question directly, and is the only component
allowed to restart a worker.

How liveness is decided (and why not just the pid)
--------------------------------------------------
`.job.lock` carries "<pid> <timestamp>" (see state.RunLock), but the pid TEXT is
the weaker of the two signals it offers: pids are recycled, so a live unrelated
process can wear a dead worker's number. The authoritative signal is the flock
RunLock itself -- if an engine is running this run, it holds LOCK_EX on that file
and our non-blocking probe cannot take it. We use the same instrument the writer
uses, then cross-check the pid:

  lock is held                  -> ALIVE     (an engine owns this run)
  lock free + pid gone          -> DEAD      (restartable)
  lock free + pid still exists  -> UNDETERMINED, never restarted -- most likely
                                   pid reuse, but "probably safe to start a
                                   second engine over one state.json" is not a
                                   call this module gets to make (state.RunLock:
                                   "two engines over one state.json corrupts it")
  no lock file at all           -> NOT ACTIVE, no action -- a run that never
                                   started, or one that shut down cleanly, is
                                   not a death

Storm control
-------------
Every restart is charged against a per-run budget kept in a ledger at the scan
root. Restart N waits `backoff_seconds * 2**(N-1)` after the previous attempt, the
budget is capped at --max-restarts, and once it is spent this module stops trying
and raises a persistent alarm instead of looping. A spawn that FAILS is charged
too, so a broken entry script alarms rather than retrying forever. This box has
already been through a 399-retry storm; the cap is the point of this design, not
a decoration.

Read-only on run directories
----------------------------
Like the watchdog (Super Spec 8.3), this module never writes state.json or
anything else inside a run dir -- the engine owns those, and a supervisor that
scribbles on the state it is judging cannot be trusted about it. The ledger, the
event log, the alarm file, and restart stdout all live under the scan root.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from .state import (
    _read_json, pid_is_alive, utcnow, LOCK_FILENAME,
    EXIT_OK, EXIT_SUPERVISOR_ALARM, EXIT_SUPERVISOR_NO_RUNS,
)
from .watchdog import _find_state_files

DEFAULT_MAX_RESTARTS = 3
DEFAULT_BACKOFF_SECONDS = 60

LEDGER_FILENAME = "supervisor-restarts.json"
EVENTS_FILENAME = "supervisor-events.jsonl"
ALARM_FILENAME = "SUPERVISOR-ALARM.json"
RESTART_LOG_DIRNAME = "supervisor-restart-logs"

# Liveness verdicts.
ALIVE = "alive"
DEAD = "dead"
UNDETERMINED = "undetermined"
NO_LOCK = "no_lock"


def worker_liveness(run_dir: Path) -> Tuple[str, str]:
    """Is an engine process currently running `run_dir`? Returns (verdict, why).

    See the module docstring for why the flock probe outranks the pid text.
    """
    lock_path = run_dir / LOCK_FILENAME
    if not lock_path.is_file():
        return NO_LOCK, f"no {LOCK_FILENAME} -- this run is not active"

    pid: Optional[int] = None
    try:
        first = lock_path.read_text(encoding="utf-8").split()
        if first:
            pid = int(first[0])
    except (OSError, ValueError):
        pid = None

    # O_RDWR, never O_CREAT: a probe that CREATES the lock it is testing would
    # manufacture the very "active run" it then reports on.
    try:
        fd = os.open(str(lock_path), os.O_RDWR)
    except OSError as exc:
        return UNDETERMINED, f"cannot open {lock_path} to probe the lock: {exc}"
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return ALIVE, f"RunLock is held (pid {pid if pid else 'unreadable'})"
        except OSError as exc:
            return UNDETERMINED, f"flock probe failed on {lock_path}: {exc}"
        # We took it, so nobody held it. Drop it in the same breath -- holding
        # it any longer than the probe would block a legitimately starting engine.
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)

    if pid is None:
        return DEAD, f"RunLock is free and {LOCK_FILENAME} carries no readable pid"
    if pid_is_alive(pid):
        return (UNDETERMINED,
                f"RunLock is free but pid {pid} still exists -- pid reuse, or a worker "
                f"that lost its lock; refusing to start a second engine over one state.json")
    return DEAD, f"RunLock is free and pid {pid} is gone"


def _ledger_path(scan_root: Path) -> Path:
    return scan_root / LEDGER_FILENAME


def _read_ledger(scan_root: Path) -> Dict[str, Any]:
    data = _read_json(_ledger_path(scan_root))
    if not isinstance(data, dict):
        return {}
    runs = data.get("runs")
    return runs if isinstance(runs, dict) else {}


def _write_ledger(scan_root: Path, runs: Dict[str, Any]) -> None:
    """Best-effort. A ledger we cannot persist must not stop us reporting a death,
    but it DOES mean the next pass will not remember this attempt -- so say so."""
    try:
        scan_root.mkdir(parents=True, exist_ok=True)
        _ledger_path(scan_root).write_text(
            json.dumps({"updated_at": utcnow(), "runs": runs}, indent=2),
            encoding="utf-8")
    except OSError as exc:
        print(f"supervisor: WARNING -- cannot write {_ledger_path(scan_root)}: {exc} "
              f"-- restart attempts will NOT be remembered across passes, so the "
              f"--max-restarts cap cannot be enforced until this is fixed", flush=True)


def _emit(scan_root: Path, event: str, run_dir: Path, detail: str,
          extra: Optional[Dict[str, Any]] = None, notify: bool = False,
          to_disk: bool = True) -> None:
    """One death, one restart, one alarm = one printed line + one jsonl row.

    Silence is the whole bug this module exists to fix, so every state change
    goes to stdout (the launchd log) AND to a durable jsonl, and the loud ones
    additionally go out over PRESENTATION_NOTIFY_CMD when it is configured.

    `to_disk=False` (a report-only pass) keeps the stdout line and the notify
    but writes NOTHING -- not even the scan-root directory itself. A pass that
    is only reporting must not leave a byte behind on the scanned tree.
    """
    record = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": event,
        "run_dir": str(run_dir),
        "detail": detail,
    }
    if extra:
        record.update(extra)
    print(f"supervisor: {event.upper()} {run_dir}: {detail}", flush=True)
    if to_disk:
        try:
            scan_root.mkdir(parents=True, exist_ok=True)
            with open(scan_root / EVENTS_FILENAME, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            print(f"supervisor: WARNING -- cannot append to {scan_root / EVENTS_FILENAME}: {exc}",
                  flush=True)
    if notify and os.environ.get("PRESENTATION_NOTIFY_CMD"):
        from .report import dispatch
        dispatch("supervisor", event, f"Supervisor {event}: {run_dir}\n{detail}")


def _backoff_seconds(attempts: int, base: int) -> int:
    """Wait before attempt N+1, given N attempts already spent. First restart is
    immediate; each subsequent one doubles."""
    if attempts <= 0:
        return 0
    return base * (2 ** (attempts - 1))


def _raise_alarm(scan_root: Path, run_dir: Path, entry: Dict[str, Any],
                 max_restarts: int, why: str, to_disk: bool = True) -> None:
    """Stop restarting and leave something a human will trip over. Persistent by
    design: the file stays until the run recovers or someone clears it.

    `to_disk=False` (report-only pass) says it loudly on stdout but leaves no
    alarm file -- a reporting pass may not write to the scanned tree."""
    alarm = {
        "at": utcnow(),
        "run_dir": str(run_dir),
        "attempts": entry.get("attempts", 0),
        "max_restarts": max_restarts,
        "last_attempt_at": entry.get("last_attempt_at"),
        "last_error": entry.get("last_error"),
        "why": why,
    }
    if to_disk:
        try:
            scan_root.mkdir(parents=True, exist_ok=True)
            (scan_root / ALARM_FILENAME).write_text(json.dumps(alarm, indent=2), encoding="utf-8")
        except OSError as exc:
            print(f"supervisor: WARNING -- cannot write alarm file: {exc}", flush=True)
    _emit(scan_root, "alarm", run_dir,
          f"restart budget exhausted ({entry.get('attempts', 0)}/{max_restarts}) -- "
          f"NO further restarts will be attempted for this run. {why}",
          extra={"attempts": entry.get("attempts", 0), "max_restarts": max_restarts},
          notify=True, to_disk=to_disk)


def _restart(scan_root: Path, run_dir: Path, scripts_dir: Path) -> Tuple[bool, str]:
    """Spawn `presentation_job.py --resume --run-dir <run_dir>`, detached.

    start_new_session=True is load-bearing: this runs under a launchd
    StartInterval job that exits as soon as the shell script returns, and a child
    left in that process group goes with it -- the restart would be reaped
    seconds after it was announced, which reads in the log as a successful
    restart that silently never ran.
    """
    entry_script = scripts_dir / "presentation_job.py"
    if not entry_script.is_file():
        return False, f"entry script missing: {entry_script}"
    log_dir = scan_root / RESTART_LOG_DIRNAME
    argv = [sys.executable, str(entry_script), "--resume", "--run-dir", str(run_dir)]
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"{run_dir.name}.log"
        with open(log_path, "a", encoding="utf-8") as log_fh:
            log_fh.write(f"\n=== supervisor restart {utcnow()} :: {' '.join(argv)} ===\n")
            log_fh.flush()
            proc = subprocess.Popen(argv, cwd=str(scripts_dir),
                                    stdout=log_fh, stderr=subprocess.STDOUT,
                                    start_new_session=True)
    except OSError as exc:
        return False, f"spawn failed: {exc}"
    return True, f"spawned pid {proc.pid} ({' '.join(argv)}); output -> {log_path}"


def supervise(
    scan_root: Path,
    scan_depth: int = 3,
    apply: bool = False,
    max_restarts: int = DEFAULT_MAX_RESTARTS,
    backoff_seconds: int = DEFAULT_BACKOFF_SECONDS,
    scripts_dir: Optional[Path] = None,
    now: Optional[datetime] = None,
    max_idle_hours: float = 72.0,
) -> int:
    """Scan `scan_root` for active runs whose worker process has died.

    Report-only unless `apply` is True -- same staging discipline as
    reconcile-board's --apply (Rule 3.5, warn mode before fail-closed): a pass
    that can start processes on 38 boxes gets to prove itself in the log first.

    READ-ONLY CONTRACT: with `apply=False` this pass writes NOTHING to the
    scanned tree -- no ledger, no supervisor-events.jsonl, no alarm file, no
    restart logs, not even the scan-root directory itself (a nonexistent scan
    root stays nonexistent; a missing ledger reads as empty silently, because
    not writing is the point, not a failure). Reporting goes to stdout only,
    and PRESENTATION_NOTIFY_CMD notifications still fire. The durable files
    (ledger, jsonl, alarms) are written only under --apply. Note the ledger is
    also what carries the restart budget across passes, so report-only passes
    never consume or clear it.

    Returns EXIT_SUPERVISOR_NO_RUNS (14) when zero state.json files were found
    (UNDETERMINED -- a wrong --scan-root must never read as a healthy fleet; this
    is exactly how the 2026-08-27 death went unseen, the watchdog was pointed at a
    root the live deck did not live under). Returns EXIT_SUPERVISOR_ALARM (15) if
    any run exhausted its restart budget. EXIT_OK (0) otherwise.

    `max_idle_hours` (default 72, reconcile-board's --max-age-hours ceiling) is
    the stale-abandonment guard: a dead run whose state.json has not been
    written for longer than that is reported (`stale_dead_run`) but never
    restarted -- reviving a week-old run unrequested is not supervision.
    """
    if scripts_dir is None:
        scripts_dir = Path(__file__).resolve().parent.parent
    if now is None:
        now = datetime.now(timezone.utc)

    ledger = _read_ledger(scan_root)
    scanned = 0
    terminal = 0
    inactive = 0
    alive = 0
    undetermined = 0
    dead = 0
    restarted = 0
    deferred = 0
    alarmed = 0
    reported_only = 0
    stale_abandoned = 0

    for state_path in _find_state_files(scan_root, scan_depth):
        scanned += 1
        run_dir = state_path.parent
        key = str(run_dir)
        st = _read_json(state_path)
        if not st:
            undetermined += 1
            _emit(scan_root, "unreadable_state", run_dir,
                  f"{state_path} could not be parsed -- cannot tell whether this run is active",
                  to_disk=apply)
            continue
        # DONE/BLOCKED/ABANDONED are the department's terminal values -- ABANDONED
        # (FAULT #11 fix, LIVE-DECK-RUN-FAULTS.md) is the sanctioned retirement
        # marker: stand down for good, never restart, never alarm.
        if st.get("terminal") in ("DONE", "BLOCKED", "ABANDONED"):
            terminal += 1
            continue

        verdict, why = worker_liveness(run_dir)

        if verdict == NO_LOCK:
            inactive += 1
            continue

        if verdict == ALIVE:
            alive += 1
            # Recovery clears the budget -- otherwise a long-lived run accretes
            # attempts across days and alarms on its fourth unrelated blip.
            # Report-only passes only LOOK: clearing the ledger entry and
            # unlinking the alarm file are mutations of the scanned tree, so
            # they wait for an --apply pass to confirm the recovery.
            if apply:
                prior = ledger.pop(key, None)
                if prior and prior.get("attempts"):
                    _emit(scan_root, "recovered", run_dir,
                          f"worker is alive again after {prior.get('attempts')} restart(s) -- "
                          f"restart budget reset")
                    alarm_file = scan_root / ALARM_FILENAME
                    try:
                        if alarm_file.is_file():
                            existing = _read_json(alarm_file) or {}
                            if existing.get("run_dir") == key:
                                alarm_file.unlink()
                    except OSError:
                        pass
            else:
                prior = ledger.get(key)
                if prior and prior.get("attempts"):
                    _emit(scan_root, "recovered", run_dir,
                          f"worker is alive again after {prior.get('attempts')} restart(s) -- "
                          f"restart budget would reset under --apply",
                          to_disk=False)
            continue

        if verdict == UNDETERMINED:
            undetermined += 1
            _emit(scan_root, "undetermined", run_dir, why, notify=True, to_disk=apply)
            continue

        # verdict == DEAD. Stale-abandonment guard: a run whose state has not
        # been touched in --max-idle-hours (default 72, the same ceiling
        # reconcile-board's --max-age-hours uses) is a corpse, not a casualty --
        # it was left behind by some past session and nobody is waiting on it.
        # Restarting a week-old run out of the blue is exactly the kind of
        # unrequested action a supervisor must not take, so old dead runs are
        # counted and reported, never restarted. A genuinely active run that
        # just lost its worker was written to within its phase budget (minutes),
        # never days.
        dead += 1
        phase = st.get("current_phase", "?")
        job_id = st.get("job_id", "?")
        idle_hours: Optional[float] = None
        updated = st.get("updated_at")
        if isinstance(updated, str):
            try:
                idle_hours = (now - datetime.fromisoformat(updated).astimezone(timezone.utc)
                              ).total_seconds() / 3600.0
            except (ValueError, TypeError):
                idle_hours = None  # unparseable timestamp: treat as NOT stale
        if idle_hours is not None and idle_hours > max_idle_hours:
            stale_abandoned += 1
            _emit(scan_root, "stale_dead_run", run_dir,
                  f"{why}; state last touched {idle_hours:.1f}h ago (cap "
                  f"{max_idle_hours}h) -- too old to restart unrequested, "
                  f"phase {phase}, job {job_id}",
                  extra={"phase": phase, "job_id": job_id,
                         "idle_hours": round(idle_hours, 1)},
                  to_disk=apply)
            continue
        _emit(scan_root, "worker_dead", run_dir,
              f"{why}; run is NOT terminal (phase {phase}, job {job_id})",
              extra={"phase": phase, "job_id": job_id}, notify=True, to_disk=apply)

        entry = ledger.get(key) or {"attempts": 0}
        attempts = int(entry.get("attempts") or 0)

        if attempts >= max_restarts:
            if not entry.get("alarm_raised"):
                # Report-only: the ledger is the only memory of "alarm_raised",
                # so without --apply we say it on stdout but neither consume the
                # budget nor leave the alarm file -- an --apply pass re-raises.
                entry["alarm_raised"] = True
                if apply:
                    ledger[key] = entry
                _raise_alarm(scan_root, run_dir, entry, max_restarts,
                             "worker is still dead after the last restart attempt",
                             to_disk=apply)
            else:
                _emit(scan_root, "alarm_standing", run_dir,
                      f"still dead, budget still exhausted ({attempts}/{max_restarts}) -- "
                      f"not restarting; see {scan_root / ALARM_FILENAME}",
                      to_disk=apply)
            alarmed += 1
            continue

        wait = _backoff_seconds(attempts, backoff_seconds)
        last_at = entry.get("last_attempt_at")
        if wait and last_at:
            try:
                since = (now - datetime.fromisoformat(last_at).astimezone(timezone.utc)
                         ).total_seconds()
            except (ValueError, TypeError):
                since = wait  # unparseable timestamp must not pin the run shut
            if since < wait:
                deferred += 1
                _emit(scan_root, "restart_deferred", run_dir,
                      f"backoff -- {int(wait - since)}s left of a {wait}s wait after "
                      f"attempt {attempts}/{max_restarts}",
                      to_disk=apply)
                continue

        if not apply:
            reported_only += 1
            _emit(scan_root, "restart_withheld", run_dir,
                  f"would restart (attempt {attempts + 1}/{max_restarts}) but --apply "
                  f"was not given -- report-only pass",
                  to_disk=apply)
            continue

        ok, detail = _restart(scan_root, run_dir, scripts_dir)
        entry["attempts"] = attempts + 1
        entry["last_attempt_at"] = now.isoformat(timespec="seconds")
        if ok:
            entry.pop("last_error", None)
            restarted += 1
            _emit(scan_root, "restart", run_dir,
                  f"attempt {entry['attempts']}/{max_restarts} -- {detail}",
                  extra={"attempt": entry["attempts"]}, notify=True, to_disk=apply)
        else:
            entry["last_error"] = detail
            _emit(scan_root, "restart_failed", run_dir,
                  f"attempt {entry['attempts']}/{max_restarts} FAILED -- {detail}",
                  extra={"attempt": entry["attempts"]}, notify=True, to_disk=apply)
            # A failed spawn is charged to the budget on purpose: a missing or
            # unexecutable entry script would otherwise retry every 5 minutes
            # forever, which is the storm this cap exists to prevent.
            if entry["attempts"] >= max_restarts:
                entry["alarm_raised"] = True
                ledger[key] = entry
                _raise_alarm(scan_root, run_dir, entry, max_restarts,
                             f"last restart could not even be spawned: {detail}")
                alarmed += 1
        ledger[key] = entry

    if apply:
        _write_ledger(scan_root, ledger)

    if scanned == 0:
        print("supervisor: NO state.json found -- check --scan-root and --scan-depth "
              "-- UNDETERMINED, exiting EXIT_SUPERVISOR_NO_RUNS (14), NOT a clean pass",
              flush=True)
        return EXIT_SUPERVISOR_NO_RUNS

    print(f"supervisor: scanned {scanned} state file(s) under {scan_root} "
          f"(depth {scan_depth}); {terminal} terminal, {inactive} not active (no lock), "
          f"{alive} alive, {undetermined} undetermined, {dead} dead "
          f"({stale_abandoned} too old to restart, cap {max_idle_hours}h) "
          f"-- {restarted} restarted, {deferred} deferred by backoff, "
          f"{reported_only} withheld (report-only), {alarmed} alarming", flush=True)

    return EXIT_SUPERVISOR_ALARM if alarmed else EXIT_OK
