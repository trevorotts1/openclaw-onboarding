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

PRES-019 -- the missing-lock defect, stale escalation, and progress deadlines
-----------------------------------------------------------------------------
Three findings changed what a liveness verdict is allowed to conclude:

  1. NO_LOCK was classified "inactive" and skipped. A live flock proves
     process ownership, not useful work -- and its ABSENCE proves nothing
     either: a run whose lock file was swept by a crash cleanup, or which
     was left non-terminal by a `kill -9` between checkpoints, is not
     "inactive", it is UNDETERMINED-until-reconciled. So a non-terminal
     state.json with no lock is now reconciled against the EXECUTION LEDGER
     (working/checkpoints/process_manifest.json -- the engine's own
     attestation chain, written under the engine lock, the one writer that
     cannot lie about its own progress):
       - ledger shows a phase started but never finished  -> the run is
         MISSING_LOCK_ACTIVE: the engine died owning work and lost its lock
         marker. Same restart path as a DEAD worker, same budget, same
         alarm ceiling.
       - ledger shows nothing in flight                  -> the run is
         really inactive: counted, no action. Never restarted unrequested.
  2. STALE AGE WAS A BRANCH ON A CORPSE PILE. The old guard silently
     skipped any dead run older than --max-idle-hours: a four-day-old
     client request vanished from every report into a counter nobody
     reads. PRES-019: stale age now ESCALATES -- it is loud (`stale_
     escalated`), it carries the age and the phase, and it tells the
     operator what to do -- but it is NEVER an implicit cancellation. The
     run stays non-terminal; the choice to cancel is a human's alone. The
     restart budget is still not spent on stale runs (restarting a week-old
     run unrequested is still not supervision); what changed is silence ->
     visibility.
  3. PID LIVENESS WAS THE ONLY HEALTH SIGNAL. A worker can be alive and
     useless -- wedged on a phase it will never finish, past its own
     budget. The engine checkpoints `heartbeat.budget_minutes` per phase
     (phases._checkpoint); a run whose LAST checkpoint is older than that
     budget x grace, while the process is alive or lock is held, is
     STALLED -- alarmed loudly (never restarted behind a live holder: the
     holder may be a long render doing honest work; the alarm is the
     operator's cue). A run with no heartbeat at all is UNDETERMINED and
     skipped, as before.

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

PRES-019 -- one recovery owner, not two
---------------------------------------
The poller's auto_resume (bounded 3/day classified BLOCKED retries) and this
supervisor (dead-worker restarts) are BOTH recovery actors over the same run
dirs. They must never race: auto_resume owns PARKED runs (terminal=BLOCKED --
the state a live-or-dead engine left after a classified failure), this
supervisor owns NON-TERMINAL runs whose worker died. A BLOCKED run is skipped
here (terminal filter) and a dead-worker run is not BLOCKED, so the two
ownership domains are disjoint by construction -- and where they could touch
(the restart spawn of a run that blocks again mid-flight) the run lease and
the .job.lock flock arbitrate, exactly as before. auto_resume's attempt
ledger (state["auto_resume"]) and this module's ledger (supervisor-restarts.
json) are separate books and each is bounded on its own.

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


def _spawn_python() -> str:
    """PRES-035: the interpreter supervised/spawned children run under.

    Same contract as launcher._spawn_python: this process was started by
    the pinned scheduler entry point, so sys.executable already IS the
    validated pin on the live path. An explicit
    PRESENTATION_PIPELINE_INTERPRETER wins only when it names a usable
    executable; a set-but-unusable pin is reported, never silently
    skipped, never used.
    """
    pin = (os.environ.get("PRESENTATION_PIPELINE_INTERPRETER") or "").strip()
    if pin:
        if os.path.isabs(pin) and os.path.isfile(pin) and os.access(pin, os.X_OK):
            return pin
        print(f"supervisor: PRESENTATION_PIPELINE_INTERPRETER={pin} is set "
              f"but not an executable file — spawning under this process's "
              f"interpreter ({sys.executable}); fix the pin or re-run "
              f"update-skills.sh", file=sys.stderr)
    return sys.executable or "python3"

from .state import (
    _read_json, pid_is_alive, utcnow, LOCK_FILENAME,
    EXIT_OK, EXIT_SUPERVISOR_ALARM, EXIT_SUPERVISOR_NO_RUNS,
    EXIT_SUPERVISOR_STALLED,
)
from .watchdog import _find_state_files

DEFAULT_MAX_RESTARTS = 3
DEFAULT_BACKOFF_SECONDS = 60

# FIX 18: the supervisor holds the run lease only for the moment of the restart
# (acquire -> spawn -> release). 300 s is several heartbeats of headroom over
# that window, long enough that a crashed supervisor cannot leave the run
# locked for more than the lease's own TTL expiry machinery handles.
RESTART_LEASE_TTL_SECONDS = 300

LEDGER_FILENAME = "supervisor-restarts.json"
EVENTS_FILENAME = "supervisor-events.jsonl"
ALARM_FILENAME = "SUPERVISOR-ALARM.json"
RESTART_LOG_DIRNAME = "supervisor-restart-logs"

# F2b: the supervisor is the SECOND of the three engine-spawn paths, and it
# Popens `presentation_job.py --resume` DIRECTLY -- it never goes through
# launcher.dispatch, so F2's auto-repin gate did not cover it. A run whose
# pinned manifest sha no longer matches the file on disk dies
# EXIT_MANIFEST_MISMATCH (7) about a second after the spawn, so an uncovered
# supervisor would spend its whole bounded restart budget on corpses after any
# manifest-changing roll and then raise an alarm that is not about the run at
# all. _restart therefore calls the launcher's own auto_repin_gate -- the same
# function, not a copy -- before it spawns.
#
# BUDGET CONTRACT. A repin refusal is NOT a restart attempt: nothing was
# spawned, and the cure is one operator `--repin`, not three more restarts. So
# _restart returns None (not False) for it, and supervise() `continue`s WITHOUT
# charging the attempt -- the same shape the FIX 18 lease refusal uses.
RESTART_REFUSED = None  # documentation alias for _restart's tri-state

# Liveness verdicts.
ALIVE = "alive"
DEAD = "dead"
UNDETERMINED = "undetermined"
NO_LOCK = "no_lock"

# PRES-019: the run's own record of its in-flight work, written under the
# engine lock by phases._checkpoint / _engine_attest. The one writer that
# cannot lie about its own progress.
PROCESS_MANIFEST_REL = Path("working") / "checkpoints" / "process_manifest.json"

# PRES-019: heartbeat grace multiplier for the progress-deadline check --
# how far past a phase's own budget_minutes a held/alive run may sit before
# it is STALLED. The watchdog uses 1.5 for the same purpose; same number,
# same reason (budgets carry real renders; grace is not permission to nap).
PROGRESS_GRACE_MULTIPLIER = 1.5

# Verdict flavours that carry the PRES-019 reconciliations (documentation
# aliases; supervise() branches on them explicitly).
NO_LOCK_LEDGER_INFLIGHT = "no_lock_ledger_inflight"   # missing lock, ledger says work in flight -> treat as dead
NO_LOCK_LEDGER_CLEAR = "no_lock_ledger_clear"         # missing lock, ledger clear -> really inactive


def _phase_started_not_finished(run_dir: Path, state: Dict[str, Any]) -> Optional[str]:
    """PRES-019: did the engine start a phase it never finished?

    Reads the run's own execution ledger (process_manifest.json
    phase_attestations -- written under the engine lock at every phase
    completion) and the run's phase records in state.json, and returns the
    phase id of work that is provably IN FLIGHT (started, no completion
    row) -- or None when the ledger shows nothing in flight.

    Reconciliation rule, and why these two sources: state.json's phase
    records say what the engine WANTED to track; the attestations say what
    the engine actually FINISHED (a `kill -9` between checkpoint and attest
    leaves a phase record that never attested). A phase record in status
    running/blocked/failed with no later attestation for the same phase id,
    or a phase whose record postdates its last attestation, is in flight.
    Unreadable manifest or empty state: None -- UNDETERMINED reads as
    inactive, never as a death (a negative needs proof; absence of a ledger
    is not evidence of in-flight work).
    """
    manifest = _read_json(run_dir / PROCESS_MANIFEST_REL)
    if not isinstance(manifest, dict):
        return None
    attestations = manifest.get("phase_attestations")
    if not isinstance(attestations, list):
        return None
    # The newest attestation timestamp per phase id -- the ledger's own
    # "finished at" for that phase. Unparseable stamps are skipped, never
    # treated as proof either way.
    finished: Dict[str, str] = {}
    for row in attestations:
        if not isinstance(row, dict):
            continue
        pid = row.get("phase_id")
        at = row.get("attested_at")
        if not isinstance(pid, str) or not isinstance(at, str):
            continue
        if pid not in finished or at > finished[pid]:
            finished[pid] = at

    for ps in state.get("phases") or []:
        if not isinstance(ps, dict):
            continue
        pid = ps.get("id")
        if not isinstance(pid, str) or not pid:
            continue
        if ps.get("status") == "done":
            continue  # completed -- never in flight
        # A started-but-unfinished phase: running/blocked/failed/pending
        # after work began. `attempts > 0` or a checkpoint timestamp says
        # the engine actually began it (a never-touched pending phase in a
        # fresh run dir is a run that never started, not a death).
        touched = bool(ps.get("attempts")) or bool(ps.get("started_at")) \
            or bool(ps.get("updated_at")) or bool(ps.get("blocked_reason"))
        if not touched:
            continue
        att_at = finished.get(pid)
        ps_at = str(ps.get("updated_at") or ps.get("started_at") or "")
        # No attestation ever for this phase -> started, never finished.
        if att_at is None:
            return pid
        # Attested, but the phase record moved afterwards (a retry/bank
        # invalidation the attest chain has not caught up with yet) -> in
        # flight again. Unparseable record stamps cannot order the two, so
        # they never claim in-flight (same negative-needs-proof rule).
        if ps_at:
            try:
                if (datetime.fromisoformat(ps_at).astimezone(timezone.utc)
                        > datetime.fromisoformat(att_at).astimezone(timezone.utc)):
                    return pid
            except (ValueError, TypeError):
                continue
    return None


def _progress_deadline(run_dir: Path, state: Dict[str, Any],
                       now: datetime) -> Optional[Dict[str, Any]]:
    """PRES-019: is a HELD/ALIVE run past its own progress deadline?

    The engine checkpoints heartbeat.budget_minutes per phase (phases.
    _checkpoint). A run whose last checkpoint is older than budget x
    PROGRESS_GRACE_MULTIPLIER is STALLED: the process may be alive, a live
    flock proves ownership, not useful work. Returns a detail dict for the
    alarm, or None when the run is within its deadline, has no heartbeat
    to judge (UNDETERMINED -> caller skips), or carries an unparseable
    timestamp (also skipped -- a guessed deadline is worse than none).
    """
    hb = state.get("heartbeat")
    if not isinstance(hb, dict):
        return None
    last = hb.get("last_checkpoint_at")
    if not isinstance(last, str) or not last.strip():
        return None
    try:
        age_min = (now - datetime.fromisoformat(last).astimezone(timezone.utc)
                   ).total_seconds() / 60.0
    except (ValueError, TypeError):
        return None
    budget = hb.get("budget_minutes")
    if not isinstance(budget, (int, float)) or isinstance(budget, bool) \
            or budget <= 0:
        # No usable budget on the heartbeat: fall back to the phase-budget
        # table the watchdog trusts, keyed by the CURRENT phase id. A phase
        # the table does not know gets the engine-wide default. This mirrors
        # watchdog.py's own resolution so both passes agree on "stalled".
        pid = hb.get("current_phase") or state.get("current_phase") or ""
        try:
            from .manifest import (PHASE_BUDGET_MINUTES,
                                   DEFAULT_PHASE_BUDGET_MINUTES)
            budget = PHASE_BUDGET_MINUTES.get(pid, DEFAULT_PHASE_BUDGET_MINUTES)
        except ImportError:
            budget = 20.0
    threshold_min = float(budget) * PROGRESS_GRACE_MULTIPLIER
    if age_min <= threshold_min:
        return None
    return {
        "age_minutes": round(age_min, 1),
        "budget_minutes": float(budget),
        "threshold_minutes": round(threshold_min, 1),
        "phase": hb.get("current_phase") or state.get("current_phase") or "?",
        "last_checkpoint_at": last,
    }


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


def _acquire_restart_lease(run_dir: Path) -> Tuple[Optional[object], Optional[str]]:
    """FIX 18: the supervisor is one of the lease's named callers ("callers: the
    door, `supervisor._restart`, ..."), so a restart may not spawn a second
    engine over a run another holder still owns. Acquire the run's lease HERE,
    before the spawn; the freshly resumed engine's own `__main__` acquire
    (which refuses to run without a lease it holds) then races nothing, because
    this holder has already won and hands the run over by releasing after the
    spawn returns.

    Guarded import on purpose: lease.py ships with the engine half of FIX 18
    (W10a B1). If it is absent this module still supervises -- a restart then
    proceeds WITHOUT a lease and says so in the return detail, exactly the
    degrade-loudly discipline _write_ledger uses when it cannot persist. Returns
    (lease, None) on success or (None, why) on refusal; (lease=None, why=None)
    means "no lease module -- restart unleased" and is NOT a refusal.
    """
    try:
        from . import lease as lease_mod
    except ImportError as exc:
        return None, f"(unleased: lease module unavailable: {exc})"
    holder = {
        "pid": os.getpid(),
        "host": os.uname().nodename,
        "session": "supervisor",
        "purpose": "supervisor.restart",
    }
    try:
        acquired = lease_mod.acquire(run_dir, holder,
                                     ttl_s=RESTART_LEASE_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001 -- lease trouble must not kill the supervise pass
        return None, f"(unleased: lease acquire raised {type(exc).__name__}: {exc})"
    if acquired is None:
        current = None
        try:
            current = lease_mod.read(run_dir)
        except Exception:  # noqa: BLE001 -- a read failure must not hide the refusal
            pass
        holder_desc = json.dumps(current, sort_keys=True) if current else \
            f"an unreadable lease at {run_dir / 'working' / '.lease.json'}"
        return None, f"restart refused: lease held by {holder_desc}"
    return acquired, None


def _release_restart_lease(lease) -> str:
    """Give the run's lease back and say what happened, in one place.

    Split out of _restart only so the F2b refusal path below can release the
    lease it took without duplicating the release. Behaviour is unchanged: a
    failed release must never abort or refuse anything -- it is a note, not a
    verdict.
    """
    if lease is None:
        return ""
    try:
        from . import lease as lease_mod
        lease_mod.release(lease)
        return "; lease acquired, verified unowned, released for the engine"
    except Exception as exc:  # noqa: BLE001 -- a failed release must not abort the spawn
        return f"; lease release failed ({type(exc).__name__}: {exc})"


def _repin_gate(run_dir: Path, entry_script: Path,
                scripts_dir: Path) -> Optional[str]:
    """F2b. Re-pin this run to the manifest on disk before the restart spawns.

    Returns None to continue the restart (nothing to repin, the answer is
    UNDETERMINED, or the repin succeeded), or a REASON STRING when the restart
    is refused because a PROVEN mismatch could not be cured.

    This is launcher.auto_repin_gate -- the identical function the poller's
    dispatch path calls, deliberately exposed as a public standalone by F2 so
    the other two spawn paths could share it. It is never reimplemented here:
    one phase diff, one place where a pin moves.

    FAIL-OPEN ON UNDETERMINED, exactly like the gate itself and like
    _acquire_restart_lease's guarded import. If launcher cannot be imported, or
    the gate raises where it is documented not to, this pass says so and lets
    the restart proceed on the existing pin -- the pre-F2b behaviour, including
    the engine's own exit 7. A supervisor that crashed on its own repin helper
    would be strictly worse than one that never had it.
    PRESENTATION_AUTO_REPIN=0 disables it inside the gate itself.
    """
    try:
        from .launcher import auto_repin_gate, REPIN_AUTOFAIL_CODE
    except (Exception, SystemExit) as exc:  # noqa: BLE001 -- see below
        print(f"supervisor: auto-repin unavailable ({type(exc).__name__}: "
              f"{exc}) -- restarting on the existing pin",
              file=sys.stderr, flush=True)
        return None
    try:
        verdict = auto_repin_gate(run_dir, entry_script, scripts_dir)
    # SystemExit is in the net on purpose: `die()` is how every manifest helper
    # reports trouble, and one escaping here would take down the whole launchd
    # supervise pass -- strictly worse than not having this gate at all.
    except (Exception, SystemExit) as exc:  # noqa: BLE001
        print(f"supervisor: auto-repin raised {type(exc).__name__}: {exc} -- "
              f"restarting on the existing pin", file=sys.stderr, flush=True)
        return None
    if verdict is None:
        return None
    return (f"restart refused: {REPIN_AUTOFAIL_CODE} -- the manifest moved "
            f"under this run and `presentation_job.py --repin --run-dir "
            f"{run_dir}` could not cure it. NOTHING was spawned and NO restart "
            f"attempt was charged: a resume on a stale pin dies "
            f"EXIT_MANIFEST_MISMATCH in about a second, so restarting here "
            f"would burn the budget on corpses. See "
            f"{run_dir / 'working' / 'logs' / 'repin.log'}.")


def _restart(scan_root: Path, run_dir: Path,
             scripts_dir: Path) -> Tuple[Optional[bool], str]:
    """Spawn `presentation_job.py --resume --run-dir <run_dir>`, detached.

    Returns (True, detail) on a spawn, (False, detail) on a spawn FAILURE that
    the caller charges to the restart budget, or (None, detail) -- RESTART_REFUSED
    -- for the F2b repin refusal, which is not an attempt and is not charged.

    FIX 18: acquires the run lease FIRST (see _acquire_restart_lease) and
    releases it after the spawn returns. If another holder owns the lease, no
    engine is spawned -- the restart is refused without charging the budget, so
    a single dead-worker flap cannot burn the whole restart budget against a
    healthy holder.

    F2b: with the lease held, `_repin_gate` re-pins a run whose manifest moved
    under it, using the launcher's own auto_repin_gate. A repin that FAILS
    refuses the restart (RESTART_REFUSED) rather than spawning an engine that
    dies EXIT_MANIFEST_MISMATCH in about a second and is then counted, logged
    and budgeted as a restart.

    start_new_session=True is load-bearing: this runs under a launchd
    StartInterval job that exits as soon as the shell script returns, and a child
    left in that process group goes with it -- the restart would be reaped
    seconds after it was announced, which reads in the log as a successful
    restart that silently never ran.
    """
    entry_script = scripts_dir / "presentation_job.py"
    if not entry_script.is_file():
        return False, f"entry script missing: {entry_script}"
    lease, refuse_why = _acquire_restart_lease(run_dir)
    if refuse_why and lease is None and refuse_why.startswith("restart refused"):
        # Held by someone else. Not a spawn failure, not a budget event: the run
        # has an owner, which is the lease doing its job. A later pass retries
        # if the holder's lease expires or the holder dies.
        return False, refuse_why

    # F2b AUTO-REPIN GATE -- UNDER the lease we just proved is ours, and before
    # the release below, so the repin's state write cannot race a second owner
    # and the release -> spawn window stays exactly as wide as it was. On a
    # proven, uncurable mismatch this refuses the restart and returns None, and
    # supervise() does not charge the attempt.
    repin_refusal = _repin_gate(run_dir, entry_script, scripts_dir)
    if repin_refusal is not None:
        return RESTART_REFUSED, repin_refusal + _release_restart_lease(lease)

    # Release BEFORE spawning, deliberately: the resumed engine's own __main__
    # acquire is the hand-off, and a lease still held by THIS pid at the moment
    # the child starts would refuse the child (same-host live pid, unexpired
    # lease => takeover denied) -- then this process exits under launchd, its
    # pid dies, and the child's takeover would have to wait out the whole TTL.
    # Releasing first makes the hand-over immediate and race-free in the
    # direction that matters: the acquire above already proved no other holder.
    handed_off = _release_restart_lease(lease)
    log_dir = scan_root / RESTART_LOG_DIRNAME
    argv = [_spawn_python(), str(entry_script), "--resume", "--run-dir", str(run_dir)]
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
    return True, (f"spawned pid {proc.pid} ({' '.join(argv)}); output -> {log_path}"
                  f"{refuse_why or ''}{handed_off}")


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
    refused = 0
    alarmed = 0
    reported_only = 0
    stale_abandoned = 0
    # PRES-019 counters: held-but-stalled alarms and missing-lock
    # reconciliations. visible in the summary line like every other count.
    stalled_count = 0
    reconciled = 0
    # PRES-019 exit-code input: a stalled alarm is a NOT-a-pass verdict even
    # with zero restarts attempted (EXIT_SUPERVISOR_STALLED, state.py).
    rc_stalled = False

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
        # PRES-019 ownership contract: BLOCKED is the POLLER's recovery
        # domain (auto_resume's classified 3/day retries), this supervisor
        # owns non-terminal dead/stalled workers. One recovery owner per
        # state, never two competing ones -- so a parked run is skipped here
        # with its park left exactly as auto_resume found it.
        if st.get("terminal") in ("DONE", "BLOCKED", "ABANDONED"):
            terminal += 1
            continue

        verdict, why = worker_liveness(run_dir)

        if verdict == NO_LOCK:
            # PRES-019: a missing lock is NOT proof of inactivity. Reconcile
            # against the run's own execution ledger: work started but never
            # finished means the engine died owning work and lost its lock
            # marker -- the same casualty a DEAD verdict reports, through a
            # different wound. Nothing in flight means really inactive.
            inflight_phase = _phase_started_not_finished(run_dir, st)
            if inflight_phase:
                verdict = NO_LOCK_LEDGER_INFLIGHT
                reconciled += 1
                _emit(scan_root, "missing_lock_reconciled", run_dir,
                      f"no {LOCK_FILENAME}, but the execution ledger shows "
                      f"phase {inflight_phase} started and never finished "
                      f"-- treating as a dead worker (same restart path and "
                      f"budget), phase {st.get('current_phase', '?')}, job "
                      f"{st.get('job_id', '?')}",
                      extra={"inflight_phase": inflight_phase},
                      notify=True, to_disk=apply)
                dead += 1
                # fall through to the shared dead-run handling below
            else:
                verdict = NO_LOCK_LEDGER_CLEAR
                inactive += 1
                continue
        if verdict in (DEAD, NO_LOCK_LEDGER_INFLIGHT):
            pass  # shared dead-run handling starts at the `dead += 1` block below
        elif verdict == ALIVE:
            alive += 1
            # PRES-019: a live flock proves process ownership, not useful
            # work. A held-but-stalled worker -- process alive, run past its
            # own progress deadline (phase budget x grace) -- gets an ALARM,
            # not a restart: restarting behind a live holder would fight the
            # very process the lock says owns the run, and a long render can
            # legitimately sit quiet inside one budget. The alarm is the
            # operator's cue; the holder is never killed here.
            stalled = _progress_deadline(run_dir, st, now)
            if stalled is not None:
                stalled_count += 1
                entry_script = scripts_dir / "presentation_job.py"
                _emit(scan_root, "stalled", run_dir,
                      f"lock held but no progress: last checkpoint "
                      f"{stalled['age_minutes']}min ago exceeds the phase "
                      f"budget x{PROGRESS_GRACE_MULTIPLIER} deadline "
                      f"({stalled['threshold_minutes']}min, phase "
                      f"{stalled['phase']}). NOT restarted behind a live "
                      f"holder -- inspect the worker; resume deliberately "
                      f"with `python3 {entry_script} --resume --run-dir "
                      f"{run_dir}` once you know it is safe.",
                      extra=stalled, notify=True, to_disk=apply)
                rc_stalled = True
                continue
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

        # verdict == DEAD, or NO_LOCK reconciled to in-flight work by the
        # execution ledger (PRES-019): the same handling, one path.
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
            # PRES-019: stale age now ESCALATES instead of silently skipping.
            # The old branch just counted the corpse and moved on -- a four-day
            # unfinished client request disappeared from every report. Now it
            # is a LOUD, notified escalation naming the age, the phase and the
            # exact resume command -- but it is NEVER an implicit cancellation
            # and NEVER an unrequested restart: the run stays non-terminal
            # (the engine owns state.json; cancelling it is a human's call),
            # and no budget is spent. Escalation is visibility, not action.
            stale_abandoned += 1
            entry_script = scripts_dir / "presentation_job.py"
            _emit(scan_root, "stale_escalated", run_dir,
                  f"{why}; state last touched {idle_hours:.1f}h ago (cap "
                  f"{max_idle_hours}h) -- ESCALATION, not cancellation: this "
                  f"unfinished run needs an operator decision. Phase {phase}, "
                  f"job {job_id}. Resume deliberately with "
                  f"`python3 {entry_script} --resume --run-dir {run_dir}` "
                  f"(or cancel it explicitly; nothing here will do either "
                  f"for you).",
                  extra={"phase": phase, "job_id": job_id,
                         "idle_hours": round(idle_hours, 1),
                         "max_idle_hours": max_idle_hours,
                         "escalation": True, "cancelled": False},
                  notify=True, to_disk=apply)
            continue
        _emit(scan_root, "worker_dead", run_dir,
              f"{why}; run is NOT terminal (phase {phase}, job {job_id})",
              extra={"phase": phase, "job_id": job_id}, notify=True, to_disk=apply)

        # FIX 18: the lease verdict outranks the flock verdict here. If the run
        # carries a live, unexpired lease, SOMEBODY owns it right now -- even
        # though the .job.lock flock is free -- and spawning a second engine
        # over it is exactly the concurrent-resume fault the lease exists to
        # close. Checked BEFORE the budget/backoff machinery (and before
        # report-only withholding, so a report-only pass still names the
        # holder) so a healthy holder never burns restart budget: this is not
        # a death, it is an owner.
        try:
            from . import lease as lease_mod
        except ImportError:
            lease_mod = None
        if lease_mod is not None:
            lease_doc = lease_mod.read(run_dir)
            if lease_doc is not None and not lease_mod._expired(lease_doc) \
                    and lease_mod._holder_is_live(lease_doc) \
                    and lease_doc.get("pid") != os.getpid():
                refused += 1
                _emit(scan_root, "restart_refused_by_lease", run_dir,
                      f"worker looks dead by flock but a live lease stands: "
                      f"{lease_mod.describe_holder(run_dir)} -- NOT restarting, "
                      f"no budget charged",
                      to_disk=apply)
                continue

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

        # F20 REPAIR: report-only must WITHHOLD the restart, not merely skip the
        # bookkeeping. `_restart` sat here unguarded, so `apply=False` still
        # spawned an engine (`--resume`) and still wrote
        # supervisor-restart-logs/<run>.log -- and the child then wrote
        # working/.lease.json into the scanned tree. That broke both promises in
        # this function's own docstring ("Report-only unless `apply` is True",
        # "with `apply=False` this pass writes NOTHING to the scanned tree") and
        # made the printed summary a lie: `reported_only` was initialised, never
        # incremented, and every dry run reported "0 withheld (report-only)"
        # while restarting. On a scheduler that runs without --apply this is a
        # fleet-wide unrequested-spawn path, so the guard fails closed.
        if not apply:
            reported_only += 1
            _emit(scan_root, "restart_withheld", run_dir,
                  f"report-only pass -- would restart (attempt {attempts + 1}/"
                  f"{max_restarts}); re-run with --apply to act",
                  to_disk=apply)
            continue

        ok, detail = _restart(scan_root, run_dir, scripts_dir)
        if ok is RESTART_REFUSED:
            # F2b: the manifest moved under this run and the repin could not
            # cure it. NOTHING was spawned, so this is not an attempt and the
            # budget is untouched -- same accounting as the FIX 18 lease
            # refusal above. Charging it would spend all three restarts on a
            # fault no restart can fix and then alarm about the wrong thing;
            # the cure is one operator `--repin`, and the next pass retries.
            refused += 1
            _emit(scan_root, "restart_refused_by_repin", run_dir,
                  f"{detail} (budget untouched at {attempts}/{max_restarts})",
                  extra={"attempts": attempts}, notify=True, to_disk=apply)
            continue
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
          f"(depth {scan_depth}); {terminal} terminal, {inactive} not active "
          f"(no lock; {reconciled} reconciled in-flight by ledger), "
          f"{alive} alive ({stalled_count} stalled past their progress "
          f"deadline), {undetermined} undetermined, {dead} dead "
          f"({stale_abandoned} escalated as stale, cap {max_idle_hours}h -- "
          f"escalation, never cancellation) "
          f"-- {restarted} restarted, {deferred} deferred by backoff, "
          f"{refused} refused by a live lease or an uncurable manifest pin, "
          f"{reported_only} withheld (report-only), {alarmed} alarming", flush=True)

    if alarmed:
        return EXIT_SUPERVISOR_ALARM
    if rc_stalled:
        # PRES-019: a held-but-stalled worker alarmed this pass -- a NOT-a-pass
        # verdict, distinct from the budget-exhausted alarm so the watchdog's
        # log line can name WHICH alarm fired. Never swallowed by a 0: the
        # same UNDETERMINED-is-not-healthy doctrine as exits 10-15.
        return EXIT_SUPERVISOR_STALLED
    return EXIT_OK
