#!/usr/bin/env python3
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Exit codes. Documented so callers, CI, and the watchdog can branch on them.
# ---------------------------------------------------------------------------
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_GATE_BLOCKED = 3
EXIT_EXECUTOR_FAILED = 4
EXIT_STALLED = 5
EXIT_LOCK_HELD = 6
EXIT_MANIFEST_MISMATCH = 7
EXIT_STATE_CORRUPT = 8
EXIT_WAIVER_INVALID = 9
# reconcile_sweep (sweep.py) is a report-only pass, not a gate -- but "found
# nothing" and "found problems" are still not the same as "found and checked
# N runs, all fine". Callers (presentation-watchdog.sh) must not read any of
# the three codes below as a plain pass.
EXIT_SWEEP_NO_RUNS = 10       # scanned 0 run dirs -- UNDETERMINED, not a pass
EXIT_SWEEP_HAD_FAILURES = 11  # scanned >0 but >=1 run dir raised an unexpected error
# scanned >0, none raised, but EVERY run dir was rejected by Guard A
# (not_a_run_dir) -- zero were ever classified/reconciled. This is the SAME
# epistemic state as EXIT_SWEEP_NO_RUNS ("I could not check anything"), just
# reached via rejection instead of absence -- e.g. a STATE_SCHEMA_VERSION
# bump that makes every real run dir on the box fail the version check.
# "scanned 5, not_a_run_dir: 5" must never read as a pass.
EXIT_SWEEP_ALL_REJECTED = 12
# watchdog.py's own version of the same fix, applied for the same reason: before
# this code, watchdog(scanned=0) fell all the way through to
# `EXIT_STALLED if (enforce and findings) else EXIT_OK` with findings == [], and
# returned EXIT_OK -- bitwise identical, at the exit-code level, to "scanned N
# run dirs, zero were stalled." A wrong --scan-root, a mount that didn't come up,
# or a typo'd path all read as a clean fleet. Returned whenever scanned == 0,
# REGARDLESS of --enforce (mirroring EXIT_SWEEP_NO_RUNS, which is likewise
# unconditional on sweep.py's --apply) -- "I found nothing to check" is never
# the same claim as "I checked and it's fine," in warn mode or enforce mode.
EXIT_WATCHDOG_NO_RUNS = 13   # scanned 0 state.json files -- UNDETERMINED, not a pass
# supervisor.py (worker liveness). Same doctrine as the two blocks above: the
# supervisor's three outcomes are distinguishable at the exit-code level, because
# "I found no run to supervise" and "I checked and every worker is alive" are not
# the same claim, and "I gave up restarting and raised an alarm" must never be
# swallowed by a 0. EXIT_SUPERVISOR_ALARM is the loud one: it means a worker died,
# the bounded retry budget is spent, and a human has to look.
EXIT_SUPERVISOR_NO_RUNS = 14  # scanned 0 state.json files -- UNDETERMINED, not a pass
EXIT_SUPERVISOR_ALARM = 15    # >=1 run exhausted its restart budget -- NOT a pass

STATE_FILENAME = "state.json"
LOCK_FILENAME = ".job.lock"
STATE_SCHEMA_VERSION = 1

# The shim U011 keeps at the scripts-dir root.  Printed by _block and close()
# as the runnable entry-point, so that the command the engine tells operators to
# run is actually the command that works.
ENTRY_COMMAND = "presentation_job.py"

def utcnow() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")



def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()



def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Atomic state store. Invariant 2.
# ---------------------------------------------------------------------------

def _norm(s: str) -> str:
    return " ".join(s.lower().split())



def pid_is_alive(pid: int) -> bool:
    """True if `pid` names a process this user can at least see.

    A PermissionError from os.kill(pid, 0) still means the process exists
    (owned by someone else, or a privilege boundary) -- only
    ProcessLookupError means the pid is genuinely free. Collapsing those two
    into one "dead" answer is how a liveness check reports a running worker as
    absent; `kill -0 1` on this platform returns EPERM for a very-much-alive
    launchd, which is exactly the false negative this discrimination prevents.

    Lives here, in the leaf module, because __main__ (auto-dispatch) and
    supervisor (worker liveness) both need it and a second hand-maintained copy
    is the divergence shape report.py's dispatch3() docstring warns about.
    """
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


def _read_json(p: Path) -> Optional[Dict[str, Any]]:
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# The engine.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Atomic state store. Invariant 2.
# ---------------------------------------------------------------------------
class StateStore:
    """Reads and writes state.json atomically. Never leaves a partial file behind."""

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.path = run_dir / STATE_FILENAME

    def exists(self) -> bool:
        return self.path.is_file()

    def load(self) -> Dict[str, Any]:
        try:
            with self.path.open("r", encoding="utf-8") as fh:
                state = json.load(fh)
        except FileNotFoundError:
            die(EXIT_STATE_CORRUPT, f"no {STATE_FILENAME} in {self.run_dir} — run --new first")
        except (json.JSONDecodeError, OSError) as exc:
            die(EXIT_STATE_CORRUPT, f"{self.path} is unreadable: {exc}")
        if not isinstance(state, dict) or "job_id" not in state:
            die(EXIT_STATE_CORRUPT, f"{self.path} is not a valid job state document")
        if state.get("schema_version") != STATE_SCHEMA_VERSION:
            die(EXIT_STATE_CORRUPT,
                f"state schema {state.get('schema_version')} != expected {STATE_SCHEMA_VERSION}")
        return state

    def save(self, state: Dict[str, Any]) -> None:
        """Atomic: write to a temp file in the same directory, fsync, then os.replace."""
        state["updated_at"] = utcnow()
        payload = json.dumps(state, indent=2, ensure_ascii=False, sort_keys=False)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.run_dir), prefix=".state-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self.path)          # atomic on the same filesystem
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise



class RunLock:
    """Exclusive advisory lock per run dir. Two engines over one state.json corrupts it."""

    def __init__(self, run_dir: Path) -> None:
        self.path = run_dir / LOCK_FILENAME
        self._fh = None

    def __enter__(self) -> "RunLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = self.path.open("a+")
        try:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._fh.close()
            die(EXIT_LOCK_HELD,
                f"another presentation_job owns {self.path.parent} — refusing to start a second")
        self._fh.seek(0)
        self._fh.truncate()
        self._fh.write(f"{os.getpid()} {utcnow()}\n")
        self._fh.flush()
        return self

    def __exit__(self, *exc) -> None:
        if self._fh:
            try:
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
            finally:
                self._fh.close()



def die(code: int, message: str) -> None:
    print(f"FATAL: {message}", file=sys.stderr, flush=True)
    sys.exit(code)


# ---------------------------------------------------------------------------
# Manifest. Pinned per job (invariant 4).
# ---------------------------------------------------------------------------

