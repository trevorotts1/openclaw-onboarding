#!/usr/bin/env python3
"""process_reaper.py — FIX-21 (D21): stray/zombie process cleanup + build health check.

WHAT THIS CLOSES
  D21 — "A `find ~ -name build_deck.py` process ran 18+ minutes as a zombie alongside
  the real build. Their presence masked whether the real render was alive (they matched
  the process filter)."
  The engine's exec sites either had NO timeout (run_signature_deck._dispatch_render /
  _dispatch_notes_sync) or a plain `subprocess.run(timeout=…)` that kills ONLY the direct
  child — orphaned grandchildren survive the timeout and keep running (the zombie path).
  And the old "process filter" was a NAME match: any process whose cmdline mentioned
  build_deck.py counted as "the build is alive", so an 18-minute `find` looked healthy.

THIS MODULE PROVIDES (deterministic, NO-AI, no network):
  1. run_with_cleanup(argv, timeout=…, grace=…)
       Spawns the exec in a NEW SESSION / PROCESS GROUP (start_new_session=True) and, on
       timeout, kills the WHOLE process group (SIGTERM then SIGKILL after grace). No
       orphan survives a timed-out exec — the direct-child-only `subprocess.run` gap.
  2. classify(proc) -> "REAL_BUILD" | "STRAY" | "WATCHDOG" | "OTHER"
       The health check that tells a real build process from a stray. A REAL build is a
       canonical engine script whose OWN run dir is alive (state.json present, not
       terminal, heartbeat within the phase grace). A STRAY is anything that merely
       *looks* build-shaped but has no live run dir: a `find`/`locate` scanning for
       build_deck.py, a defunct/zombie, or a build process whose run dir went terminal.
  3. reap_strays(scan_root, …) / CLI
       Enumerates the process table, classifies every build-shaped process, kills
       STRAYs (SIGTERM -> SIGKILL), and writes BEFORE/AFTER process-table evidence to a
       JSON file. This is the reaper the watchdog / operator runs.

FIX 34 — INTAKE IS SEALED, AND THE REAPER LEAVES IT SEALED
  After the engine's --new consumed `working/copy/intake.json`, the launcher
  (presentation_job/launcher.py, Fix 34 block) seals it 0444. A stray that
  "repairs" that mode back to 0644 would reopen the exact rewrite-mid-run hole
  Fix 34 closed, so the reaper NEVER chmods any file: it kills processes only,
  and reap_strays() records the intake's seal state in its evidence so an
  unsealed intake next to a reaped stray is visible, not silently re-writable.
  Intake data changes go through the launcher's amendment channel
  (working/copy/intake_amendments.jsonl), never a chmod.

EVIDENCE PROTOCOL
  The QC gate for FIX-21 requires "process-table listing before/after (python psutil,
  not grep)". list_processes() prefers psutil (best-quality: status, create_time, cwd,
  cmdline) and falls back to a `ps -axo …` parse so the module still works on boxes
  without psutil. reap_strays() writes a `process-reaper-evidence.json` with the full
  before/after table plus per-process classification.
"""

from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Canonical engine scripts. A process is build-SHAPED when its command line names
# one of these (or is a find/locate probing for one of them).
#
# FIX 19 (MASTER Part 8): the dispatcher and the prompt workers were invisible
# to this set — only the dispatcher *pid* was ever signalled on stop, so orphan
# `work_order_dispatcher.py --watch` processes and standalone
# `python -m presentation_job.parallel_prompt_worker` runs survived an engine
# kill and kept rewriting intake. Both argv shapes are now build-shaped and
# flow through the same run-dir-liveness oracle below: an orphan whose run dir
# is terminal/stale (or unresolvable) classifies STRAY and is reaped, children
# included (reap_strays kills the whole descendant tree).
# ---------------------------------------------------------------------------
CANONICAL_ENGINE_SCRIPTS = frozenset({
    "build_deck.py",
    "run_signature_deck.py",
    "presentation_job.py",
    "build_teleprompter.py",
    "presentation-watchdog.sh",
    "work_order_dispatcher.py",          # FIX 19: standalone dispatcher entry
    "parallel_prompt_worker.py",         # FIX 19: wrapper-name match (module form below)
})

# FIX 19: the `-m` invocation forms. `python3 -m presentation_job.dispatcher`
# and `python3 -m presentation_job.parallel_prompt_worker` never carry a *.py
# token, so the basename set above cannot see them; the module token itself is
# matched instead (argv token exactly, never a substring of the joined string —
# the D21 rule).
DISPATCHER_WORKER_MODULE_TOKENS = frozenset({
    "presentation_job.dispatcher",
    "presentation_job.parallel_prompt_worker",
})

# Tools whose presence in a cmdline marks a "scanning for build" stray even when they
# also name a canonical script (D21's `find ~ -name build_deck.py`).
SCAN_TOOLS = frozenset({"find", "locate", "mdfind", "grep", "rg", "ag"})

# Default hard timeout for run_with_cleanup when the caller supplies none.
DEFAULT_EXEC_TIMEOUT_SECONDS = 300          # 5 minutes — a subprocess that runs longer is hung
KILL_GRACE_SECONDS = 5                       # SIGTERM -> SIGKILL grace

# Default strays: how stale a run dir's heartbeat must be (as a fraction of its phase
# interval) before its build process is declared a STRAY. Mirrors the watchdog's
# grace_multiplier so a build that is merely mid-checkpoint is never misclassified.
DEFAULT_HEARTBEAT_GRACE_MULTIPLIER = 1.5
DEFAULT_MAX_PROCESS_AGE_SECONDS = 24 * 3600  # a build process older than a day is a stray

# HARDEN G3: sanity ceiling for a state.json heartbeat.interval_minutes value (mirrors
# presentation_job/manifest.py's MAX_HEARTBEAT_INTERVAL_MINUTES -- the longest total
# per-phase budget the engine grants ANY phase, i.e. the slowest legitimate unit of work
# this engine ever performs; see that module for the full rationale). Without this bound,
# _run_dir_liveness() below only rejected interval<=0, so a poisoned
# interval_minutes=999999999 read straight off disk made every run look "alive" no matter
# how stale its last checkpoint really was. PHASE_BUDGET_MINUTES / DEFAULT_PHASE_BUDGET_MINUTES
# are imported alongside it for the per-phase follow-up (RCA §1.5, §7): the flat 240 max is
# the slowest phase in the WHOLE engine, not a bound on any one phase, so it is tightened
# below to min(MAX_HEARTBEAT_INTERVAL_MINUTES, that phase's OWN budget). Imported when
# presentation_job is reachable so the modules can never silently diverge on what "sane"
# means; the literal fallbacks keep the reaper functional even if this file is ever
# deployed without presentation_job/ beside it (normally it sits in this same scripts/
# directory: imported by phases.py, and run standalone by presentation-watchdog.sh, both
# of which put scripts/ on sys.path).
try:
    from presentation_job.manifest import (
        MAX_HEARTBEAT_INTERVAL_MINUTES, PHASE_BUDGET_MINUTES, DEFAULT_PHASE_BUDGET_MINUTES,
    )
except ImportError:  # pragma: no cover — see comment above
    MAX_HEARTBEAT_INTERVAL_MINUTES = 240
    PHASE_BUDGET_MINUTES = {}
    DEFAULT_PHASE_BUDGET_MINUTES = 20


class ProcessTableError(RuntimeError):
    """Raised when the process table cannot be enumerated at all (both psutil and ps
    are unavailable or broken). Fail-closed for the reaper: an unreadable table never
    reports "nothing to reap"."""


# ---------------------------------------------------------------------------
# Process-table enumeration (psutil preferred, `ps` fallback — never grep)
# ---------------------------------------------------------------------------
def _psutil_available() -> bool:
    try:
        import psutil  # noqa: F401
        return True
    except ImportError:
        return False


def _ps_row(pid: int) -> Optional[Dict[str, Any]]:
    """psutil path: one process entry, or None if the pid vanished mid-scan."""
    try:
        import psutil
    except ImportError:
        return None
    try:
        p = psutil.Process(pid)
        with p.oneshot():
            cmd = p.cmdline() or []
            status_raw = p.status()
            # Normalise: psutil spells it 'zombie', `ps` spells it 'Z'. Always "ZOMBIE".
            status = ("ZOMBIE" if status_raw == psutil.STATUS_ZOMBIE
                      else str(status_raw).upper())
            create = p.create_time()
            try:
                cwd = p.cwd()
            except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
                cwd = None
            return {
                "pid": pid,
                "ppid": p.ppid() or None,
                "name": p.name() or "",
                "cmdline": cmd,
                "cmdline_str": " ".join(cmd),
                "status": status,
                "create_time": create,
                "elapsed_seconds": max(0.0, time.time() - create),
                "cwd": cwd,
            }
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return None
    except Exception:  # noqa: BLE001 — a broken single process never kills the table
        return None


def _parse_etime(etime: str) -> float:
    """Parse `ps` etime into seconds. etime is space-free: SS | MM:SS | HH:MM:SS |
    D-HH:MM:SS. Returns None on any malformed value (row dropped, never a crash)."""
    etime = etime.strip()
    if "-" in etime:
        days, rest = etime.split("-", 1)
        try:
            days = int(days)
        except ValueError:
            return None
    else:
        days, rest = 0, etime
    parts = rest.split(":")
    try:
        if len(parts) == 1:
            secs = int(parts[0])
        elif len(parts) == 2:
            secs = int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            secs = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        else:
            return None
    except ValueError:
        return None
    return days * 86400 + secs


def _ps_fallback() -> List[Dict[str, Any]]:
    """`ps -axo pid=,ppid=,stat=,etime=,command=` parse when psutil is absent. Uses
    etime (space-free) so the fixed-column split never mangles a command with spaces.
    Includes the Z (zombie) state verbatim. Runs with a hard 30s timeout so an
    overloaded box cannot hang the health check (D21 root cause: an unbounded process
    query). `command` may contain spaces — captured as the trailing column verbatim."""
    argv = ["ps", "-axo", "pid=,ppid=,stat=,etime=,command="]
    try:
        r = subprocess.run(argv, shell=False, capture_output=True, text=True,
                           timeout=30)
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise ProcessTableError(f"ps failed: {exc}") from exc
    if r.returncode != 0:
        raise ProcessTableError(f"ps exited {r.returncode}: {r.stderr.strip()}")
    rows = []
    for line in r.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split(None, 4)   # pid ppid stat etime command
        if len(parts) < 5:
            continue
        pid, ppid, stat, etime, cmdline = parts
        try:
            elapsed = _parse_etime(etime)
            rows.append({
                "pid": int(pid),
                "ppid": int(ppid) if ppid.isdigit() else None,
                "name": cmdline.split("/")[-1].split(" ")[0] if cmdline else "",
                "cmdline": shlex.split(cmdline) if cmdline else [],
                "cmdline_str": cmdline,
                "status": "ZOMBIE" if "Z" in stat else stat.upper(),
                "create_time": (time.time() - elapsed) if elapsed is not None else None,
                "elapsed_seconds": elapsed,
                "cwd": None,
            })
        except (ValueError, TypeError):
            continue
    return rows


def list_processes() -> List[Dict[str, Any]]:
    """Enumerate the whole process table. psutil path when available; `ps` fallback.
    Raises ProcessTableError only when neither can produce a table (fail-closed)."""
    if _psutil_available():
        import psutil
        out = []
        for p in psutil.process_iter():
            row = _ps_row(p.pid)
            if row is not None:
                out.append(row)
        return out
    try:
        return _ps_fallback()
    except ProcessTableError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ProcessTableError(f"process table unavailable: {exc}") from exc


# ---------------------------------------------------------------------------
# Run-dir resolution + run-dir liveness (the health-check oracle)
# ---------------------------------------------------------------------------
def _extract_run_dir(proc: Dict[str, Any]) -> Optional[Path]:
    """The run dir a build process belongs to. Engine invocations ALWAYS pass
    `--run-dir <path>`; resolve that from the cmdline first. FIX 19: prompt-wave
    workers are invoked with `--input <run_dir>/working/checkpoints/*-wave-input.json`
    instead of --run-dir, so the wave-input path is resolved back to its run dir
    (only when the resolved candidate really looks like a run dir — anchored, never
    guessed). Fall back to cwd only if the cwd itself IS a run dir (contains
    state.json)."""
    cl = proc.get("cmdline") or []
    for i, tok in enumerate(cl):
        if tok == "--run-dir" and i + 1 < len(cl):
            cand = cl[i + 1]
            p = Path(cand).expanduser()
            _next = cl[i + 2] if i + 2 < len(cl) else ""
            if (p.exists() and (p / "state.json").is_file()) or (p / "working").is_dir()                     or i + 2 >= len(cl) or _next.startswith("-"):
                return p.resolve() if p.exists() else p
            # R-F02-B3: the `ps` fallback shlex-splits the command column, so a run dir
            # with SPACES arrives as several argv tokens ("/Users/.../SEPT", "1ST",
            # "PRESENTATION", ...). The next token alone does not exist. Consolidate:
            # join successive tokens until the joined candidate is a REAL path (anchored,
            # never guessed) or a token starts with '-'.
            joined = cand
            j = i + 2
            while j < len(cl) and not cl[j].startswith("-"):
                joined = joined + " " + cl[j]
                pj = Path(joined).expanduser()
                if pj.exists():
                    return pj.resolve()
                j += 1
            # Never reaped a path we cannot anchor: return the FULL joined candidate
            # even when it does not exist, so the liveness check (not the parse) is
            # the thing that decides a run is dead — a parse artifact must never
            # masquerade as an absent run dir.
            return Path(joined).expanduser()
        if tok.startswith("--run-dir="):
            p = Path(tok.split("=", 1)[1]).expanduser()
            return p.resolve() if p.exists() else p
    # FIX 19: `--input <run_dir>/working/checkpoints/<x>-wave-input.json` — the
    # dispatcher/worker spawn shape. Resolved only when the candidate directory
    # carries a state.json or a working/ subdir, so a coincidental --input path
    # elsewhere in the tree is never promoted to a run dir.
    for i, tok in enumerate(cl):
        raw = None
        if tok == "--input" and i + 1 < len(cl):
            raw = cl[i + 1]
        elif tok.startswith("--input="):
            raw = tok.split("=", 1)[1]
        if not raw:
            continue
        p = Path(raw).expanduser()
        if "working" not in p.parts:
            continue
        try:
            widx = p.parts.index("working")
        except ValueError:  # pragma: no cover — guarded above
            continue
        if widx < 2:
            continue  # "/working/..." with no run dir above it
        cand = Path(*p.parts[:widx])
        cand = cand.expanduser()
        if (cand / "state.json").is_file() or (cand / "working").is_dir():
            return cand.resolve()
    cwd = proc.get("cwd")
    if cwd:
        p = Path(cwd)
        if (p / "state.json").is_file():
            return p.resolve()
    return None


def _read_json_safe(p: Path) -> Optional[Dict[str, Any]]:
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _run_dir_liveness(run_dir: Path, grace_multiplier: float) -> Tuple[str, str]:
    """Classify a run dir's liveness. Returns (verdict, detail) with verdict in
    {"alive", "no_state", "terminal", "stale", "corrupt"}.

    `alive`    — state.json present + parseable + non-terminal + heartbeat fresh.
    `no_state` — state.json missing entirely (the process points at a dead/never-valid dir).
    `terminal` — state.json says terminal in (DONE, BLOCKED); its build process is leftover.
    `corrupt`  — state.json unreadable; fail-closed (never trust a dead dir as alive).
    `stale`    — heartbeat older than interval x grace_multiplier: the job stalled, so
                 its build process is dead weight (the D14 hang, now reapable).
    """
    st_path = run_dir / "state.json"
    if not st_path.is_file():
        return "no_state", f"no state.json at {run_dir}"
    st = _read_json_safe(st_path)
    if not st:
        return "corrupt", f"state.json unreadable at {run_dir}"
    terminal = st.get("terminal")
    if terminal in ("DONE", "BLOCKED"):
        return "terminal", f"run dir terminal={terminal}"
    hb = st.get("heartbeat") or {}
    last = hb.get("last_checkpoint_at")
    if not last:
        # No heartbeat yet — a job that just started. Treat as alive (never reap a
        # build that hasn't had a chance to checkpoint).
        return "alive", "no heartbeat yet (job starting)"
    try:
        age_min = (datetime.now(timezone.utc) - datetime.fromisoformat(str(last))
                   .astimezone(timezone.utc)).total_seconds() / 60.0
    except (ValueError, TypeError):
        return "alive", "unparseable heartbeat timestamp (defer to watchdog)"
    interval = hb.get("interval_minutes")
    pid = hb.get("current_phase") or st.get("current_phase") or "?"
    # HARDEN G3 + per-phase follow-up: reject not just <=0 but anything past THIS phase's
    # own ceiling -- min(MAX_HEARTBEAT_INTERVAL_MINUTES, that phase's PHASE_BUDGET_MINUTES
    # entry), not the flat engine-wide 240 max (mirrors watchdog.py's identical bound). A
    # state.json written before the manifest.py fix (or by any other writer) could still
    # carry a poisoned interval_minutes, and this reaper reads state.json independently of
    # the watchdog, so it needs its own bound rather than trusting the value on disk.
    phase_ceiling = min(MAX_HEARTBEAT_INTERVAL_MINUTES,
                         PHASE_BUDGET_MINUTES.get(pid, DEFAULT_PHASE_BUDGET_MINUTES))
    if (not isinstance(interval, (int, float)) or isinstance(interval, bool)
            or interval <= 0 or interval > phase_ceiling):
        # No manifest interval recorded, or an insane value — fall back to this phase's
        # own budget-table entry (or the engine default) rather than trust it.
        interval = PHASE_BUDGET_MINUTES.get(pid, DEFAULT_PHASE_BUDGET_MINUTES)
    threshold = interval * grace_multiplier
    if age_min > threshold:
        return "stale", (f"heartbeat {age_min:.1f} min old > threshold {threshold:.1f} "
                         f"min (interval {interval} x grace {grace_multiplier})")
    return "alive", f"heartbeat {age_min:.1f} min old (within {threshold:.1f} min threshold)"


# ---------------------------------------------------------------------------
# Classification — the health check that distinguishes real builds from strays
# ---------------------------------------------------------------------------
def _is_build_shaped(proc: Dict[str, Any]) -> bool:
    """A process is build-SHAPED only when a real argv TOKEN is a canonical engine
    script, or the process's EXECUTABLE is a scan tool probing for one. The D21 stray
    was `find ~ -name build_deck.py`: the executable is `find` and a token names the
    script. NEVER a substring match on the joined command string — a shell wrapper
    whose inline history merely mentions build_deck.py is a shell, not a build, and
    must not be reaped (a name-substring filter is exactly the D21 blind spot that
    made strays look healthy).

    FIX 19: the dispatcher and prompt workers are build-shaped in BOTH their argv
    forms — a `work_order_dispatcher.py` / `parallel_prompt_worker.py` script
    token, and the `-m presentation_job.dispatcher` /
    `-m presentation_job.parallel_prompt_worker` module token. Matched as whole
    argv tokens only, never substrings."""
    cl = proc.get("cmdline") or []
    basenames = {t.split("/")[-1] for t in cl if t}
    if basenames & CANONICAL_ENGINE_SCRIPTS:
        return True
    if {t for t in cl if t} & DISPATCHER_WORKER_MODULE_TOKENS:
        return True
    exe = (cl[0].split("/")[-1] if cl else "")
    if exe in SCAN_TOOLS:
        # A scan tool process: it is only build-shaped when one of its argv tokens
        # NAMES a canonical script (e.g. `find ~ -name build_deck.py`). A bare
        # `find . -type f` with no build-script reference is an unrelated scan.
        return bool(basenames & CANONICAL_ENGINE_SCRIPTS)
    return False


def classify(proc: Dict[str, Any], grace_multiplier: float = DEFAULT_HEARTBEAT_GRACE_MULTIPLIER,
             max_age_seconds: float = DEFAULT_MAX_PROCESS_AGE_SECONDS) -> Tuple[str, str]:
    """Classify one process. Returns (verdict, detail).

    verdict in {"REAL_BUILD", "STRAY", "WATCHDOG", "OTHER"}:
      REAL_BUILD — a canonical engine process whose own run dir is ALIVE.
      STRAY      — build-SHAPED but NOT a live build: no run dir, or a run dir that is
                   terminal / missing / corrupt / stale, or a zombie, or older than a day.
      WATCHDOG   — the `--watchdog` monitor itself; never a stray.
      OTHER      — not build-shaped; ignored by the reaper.
    """
    if proc is None:
        return "OTHER", "process vanished between table snapshots"
    cl = proc.get("cmdline") or []
    basenames = {t.split("/")[-1] for t in cl if t}

    # The watchdog monitor is a legitimate long-running process, never a stray.
    if "--watchdog" in cl or "presentation-watchdog.sh" in basenames:
        return "WATCHDOG", "monitor process (--watchdog) — never reaped"

    # Zombies are ALWAYS strays (a defunct process is dead; it only consumes a PID).
    if proc.get("status") == "ZOMBIE":
        return "STRAY", f"zombie/defunct process (status={proc.get('status')})"

    if not _is_build_shaped(proc):
        return "OTHER", "not build-shaped"

    # A build-shaped process older than a day is a stray (the 18-min `find` was ~0;
    # a genuinely hung leftover should not persist past a day).
    elapsed = proc.get("elapsed_seconds")
    if elapsed is not None and elapsed > max_age_seconds:
        return "STRAY", f"build-shaped process running {elapsed/3600:.1f}h (> {max_age_seconds/3600:.1f}h)"

    run_dir = _extract_run_dir(proc)
    if run_dir is None:
        # D21: `find ~ -name build_deck.py` has no run dir — it is NOT a build.
        return "STRAY", "build-shaped but no resolvable --run-dir / run-dir cwd"

    verdict, detail = _run_dir_liveness(run_dir, grace_multiplier)
    if verdict == "alive":
        return "REAL_BUILD", f"run dir {run_dir} alive ({detail})"
    return "STRAY", f"run dir {run_dir} {detail}"


# ---------------------------------------------------------------------------
# The reaper — kill strays, write before/after evidence
# ---------------------------------------------------------------------------
def _kill_pid(pid: int, sig: int) -> bool:
    try:
        os.kill(pid, sig)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _kill_group_and_tree(pid: int, sig: int) -> int:
    """FIX 19 (MASTER Part 8): signal a stray, its whole PROCESS GROUP, and its
    whole descendant tree — "children included", enforced in code rather than
    only claimed in a comment.

    1. os.killpg(pid, sig): every FIX 19 spawn (launcher engine, auto-spawned
       dispatcher) is start_new_session=True, so the stray IS its own group
       leader and the killpg reaches the watcher AND its in-flight wave
       workers in one syscall. Best-effort: a non-leader stray's killpg fails
       (ProcessLookupError/PermissionError) and is swallowed.
    2. _kill_tree(pid, sig): the ppid walk. Catches children a group kill
       misses — a child that called setpgid itself, or was reparented outside
       the stray's group between the table snapshot and the signal.

    Sending both is idempotent for already-signalled processes (a second
    SIGTERM to a dying process is a no-op; the KILL escalation below is what
    finishes survivors). Returns the total number of signals sent."""
    sent = 0
    try:
        os.killpg(pid, sig)
        sent += 1
    except (ProcessLookupError, PermissionError, OSError):
        pass
    sent += _kill_tree(pid, sig)
    return sent


def _kill_tree(pid: int, sig: int) -> int:
    """Send sig to the process AND its descendants (walked from the current table so a
    reparented child is still found). Returns the number of signals sent. Uses only
    os.kill on live pids — never a shell `pkill` string."""
    from collections import deque
    children: Dict[int, List[int]] = {}
    try:
        for row in list_processes():
            children.setdefault(row.get("ppid") or 0, []).append(row["pid"])
    except ProcessTableError:
        children = {}
    q = deque([pid])
    sent = 0
    while q:
        cur = q.popleft()
        if _kill_pid(cur, sig):
            sent += 1
        for kid in children.get(cur, []):
            q.append(kid)
    return sent


def _self_and_ancestors() -> set:
    """Set of pids we must NEVER reap: our own pid, our shell, and every ancestor.
    A build-shaped STRAY that is actually our own process tree (e.g. a reaper invoked
    from a shell whose wrapper mentions build_deck.py) is skipped — killing our own
    parents would terminate the reaper itself. Walks the table; never guesses."""
    guarded = set()
    pid = os.getpid()
    seen = set()
    table = _safe_table()
    while pid and pid not in seen and pid > 1:
        seen.add(pid)
        guarded.add(pid)
        row = next((r for r in table if r and r.get("pid") == pid), None)
        if not row:
            break
        pid = row.get("ppid") or 0
    guarded.add(1)
    return guarded


def _safe_table() -> List[Dict[str, Any]]:
    try:
        return list_processes()
    except ProcessTableError:
        return []


def _intake_seal_evidence(scan_root: Path) -> Dict[str, Any]:
    """FIX 34 evidence: the seal state of the run dir's working/copy/intake.json
    when scan_root IS (or contains) that run dir. Read-only — mode is reported,
    never changed. `sealed` mirrors launcher.INTAKE_SEAL_MODE (0444 == the
    -r--r--r-- the QC proof stats for). Absent intake -> {"present": False}."""
    intake = Path(scan_root) / "working" / "copy" / "intake.json"
    if not intake.is_file():
        return {"present": False}
    import stat as _stat
    mode_bits = intake.stat().st_mode & 0o777
    return {
        "present": True,
        "path": str(intake),
        "mode": oct(mode_bits),
        "mode_string": _stat.filemode(intake.stat().st_mode),
        "sealed": mode_bits == 0o444,
    }


def reap_strays(scan_root: Path,
                grace_multiplier: float = DEFAULT_HEARTBEAT_GRACE_MULTIPLIER,
                kill_grace: int = KILL_GRACE_SECONDS,
                dry_run: bool = False,
                evidence_path: Optional[Path] = None,
                notify: Optional[Any] = None) -> Dict[str, Any]:
    """Enumerate the process table, classify every process, and kill STRAYs.

    Writes BEFORE/AFTER process-table evidence (psutil-quality) to evidence_path
    (default <scan_root>/process-reaper-evidence.json). `dry_run=True` classifies and
    reports but never kills. Returns a summary dict (also appended to the evidence
    file) with before/after tables, classifications, and kill results.

    Never touches client credentials, never messages a client. The `notify` callable,
    if supplied, receives one line per action for the operator's own log.
    """
    if evidence_path is None:
        evidence_path = scan_root / "process-reaper-evidence.json"

    before = list_processes()
    classifications = []
    strays = []
    for row in before:
        verdict, detail = classify(row, grace_multiplier)
        if row is not None:
            row["class"] = verdict
            row["class_detail"] = detail
        classifications.append(row)
        if verdict == "STRAY" and row is not None:
            strays.append(row)

    record = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scan_root": str(scan_root),
        "grace_multiplier": grace_multiplier,
        "dry_run": dry_run,
        "intake_seal": _intake_seal_evidence(scan_root),
        "before_table": before,
        "strays": [{"pid": r["pid"], "cmdline_str": r.get("cmdline_str", ""),
                    "class_detail": r.get("class_detail", "")} for r in strays],
        "kills": [],
        "skipped_guarded": [],
        "after_table": [],
    }

    guarded = _self_and_ancestors() if not dry_run else set()
    for row in strays:
        if row is None:
            continue
        pid = row["pid"]
        if pid in guarded:
            record["skipped_guarded"].append(
                {"pid": pid, "reason": "self/ancestor of the reaper — not reaped",
                 "cmdline_str": row.get("cmdline_str", "")})
            print(f"SKIP guarded pid={pid} (ancestor of the reaper) — not reaped", flush=True)
            continue
        line = f"REAP stray pid={pid} ({row.get('cmdline_str', '')[:120]})"
        if dry_run:
            line = "[dry-run] " + line
        print(line, flush=True)
        if notify:
            notify(line)
        if not dry_run:
            # FIX 19: the reap is a GROUP-AND-TREE kill, not a bare pid signal —
            # "children included" is the whole point of this fix. A stray
            # dispatcher/signature engine carries its wave workers; killing the
            # pid alone is the pre-FIX 19 bug in miniature. _kill_group_and_tree
            # killpg's the stray's own process group (every FIX 19 spawn is
            # start_new_session=True) and walks the descendant tree, so the
            # SIGTERM reaches workers a pid-only signal never saw.
            _kill_group_and_tree(pid, signal.SIGTERM)
            time.sleep(min(kill_grace, KILL_GRACE_SECONDS))
            # Confirm dead; escalate to SIGKILL if it survived (incl. a zombie reparent).
            still = _pid_alive(pid)
            if still:
                _kill_group_and_tree(pid, signal.SIGKILL)
                record["kills"].append({"pid": pid, "signal": "SIGTERM->SIGKILL",
                                        "final": "SIGKILL"})
            else:
                record["kills"].append({"pid": pid, "signal": "SIGTERM", "final": "SIGTERM"})

    after = list_processes()
    for row in after:
        if row is None:
            continue
        verdict, detail = classify(row, grace_multiplier)
        row["class"] = verdict
        row["class_detail"] = detail
    record["after_table"] = after

    counts: Dict[str, int] = {}
    for row in before:
        if row is not None:
            counts[row.get("class")] = counts.get(row.get("class"), 0) + 1
    record["counts_before"] = counts
    counts_after: Dict[str, int] = {}
    for row in after:
        if row is not None:
            counts_after[row.get("class")] = counts_after.get(row.get("class"), 0) + 1
    record["counts_after"] = counts_after

    try:
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(json.dumps(record, indent=2, default=str),
                                 encoding="utf-8")
    except OSError as exc:
        print(f"reap_strays: could not write evidence {evidence_path}: {exc}",
              file=sys.stderr, flush=True)

    print(f"reap_strays: {len(strays)} stray(s) "
          f"{'would be killed' if dry_run else 'killed'}; REAL_BUILD={counts.get('REAL_BUILD', 0)} "
          f"left running; evidence -> {evidence_path}", flush=True)
    return record


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


# ---------------------------------------------------------------------------
# run_with_cleanup — timeout + whole-process-group cleanup for long-running exec
# ---------------------------------------------------------------------------
def run_with_cleanup(argv: List[str], *,
                     cwd: Optional[str] = None,
                     timeout: Optional[float] = None,
                     env: Optional[Dict[str, str]] = None,
                     input_text: Optional[str] = None,
                     capture: bool = True,
                     on_spawn=None) -> subprocess.CompletedProcess:
    """Run argv in a NEW SESSION / PROCESS GROUP (start_new_session=True). If the exec
    exceeds `timeout`, kill the ENTIRE process group (SIGTERM, then SIGKILL after the
    grace) and raise subprocess.TimeoutExpired — no orphan survives.

    This is the FIX-21 replacement for bare `subprocess.run(..., timeout=…)`, which
    kills only the direct child and leaves grandchildren (and their process group)
    running — the D21 orphan/zombie path. The caller keeps the identical contract
    (returncode / stdout / stderr / TimeoutExpired), so this is a drop-in swap.

    FIX 105: optional `on_spawn` hook — a single-argument callable invoked with
    the Popen handle the moment the child exists (before communicate blocks).
    The engine (phases.py) uses it to REGISTER every in-flight exec so its
    shutdown path can killpg the exec's own session; every existing caller is
    unaffected (on_spawn defaults to None).
    """
    t = timeout if timeout is not None else DEFAULT_EXEC_TIMEOUT_SECONDS
    kwargs: Dict[str, Any] = {
        "cwd": cwd,
        "start_new_session": True,      # the whole group dies together on timeout
        "shell": False,
    }
    if env is not None:
        kwargs["env"] = env
    if input_text is not None:
        kwargs["input"] = input_text
    if capture:
        kwargs.update({"stdout": subprocess.PIPE, "stderr": subprocess.PIPE,
                       "text": True})
    proc = subprocess.Popen(argv, **kwargs)
    if on_spawn is not None:
        try:
            on_spawn(proc)
        except Exception:  # noqa: BLE001 — a broken hook must never break the exec
            pass
    try:
        out, err = proc.communicate(timeout=t)
        return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)
    except subprocess.TimeoutExpired:
        # Kill the whole process group the child created (child is group leader, pid == pgid).
        sigterm_sent = _kill_process_group(proc.pid, signal.SIGTERM)
        try:
            out, err = proc.communicate(timeout=KILL_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            _kill_process_group(proc.pid, signal.SIGKILL)
            try:
                out, err = proc.communicate(timeout=KILL_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                # Extremely unlikely: a process that ignores SIGKILL. Leave it to the reaper.
                raise subprocess.TimeoutExpired(argv, t) from None
        raise subprocess.TimeoutExpired(
            argv, t, output=out,
            stderr=(err if err else "") +
            f"\n[process_reaper] exec timed out after {t}s; killed process group "
            f"(leader pid={proc.pid}, {sigterm_sent} signal(s) sent)")


def _kill_process_group(pgid: int, sig: int) -> int:
    """os.killpg to the child's process group. Returns 1 on success, 0 if the group is
    already gone. Never falls back to a shell `kill` string."""
    try:
        os.killpg(pgid, sig)
        return 1
    except (ProcessLookupError, PermissionError):
        # The group is gone, or belongs to another user — either way, nothing to kill.
        try:
            os.kill(pgid, sig)
            return 1
        except (ProcessLookupError, PermissionError):
            return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _main(argv: Optional[List[str]] = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        prog="process_reaper.py",
        description="FIX-21: process-table health check + stray/zombie reaper for the "
                    "Presentation Department. Distinguishes REAL build processes from "
                    "strays and kills the strays (SIGTERM -> SIGKILL), writing before/after "
                    "process-table evidence.")
    ap.add_argument("--scan-root", type=Path, default=Path.cwd(),
                    help="directory for the evidence file + run-dir liveness scans")
    ap.add_argument("--grace", type=float, default=DEFAULT_HEARTBEAT_GRACE_MULTIPLIER,
                    help="heartbeat grace multiplier (default %(default)s)")
    ap.add_argument("--dry-run", action="store_true",
                    help="classify + report only; do not kill")
    ap.add_argument("--evidence", type=Path, default=None,
                    help="evidence JSON path (default <scan-root>/process-reaper-evidence.json)")
    ap.add_argument("--list", action="store_true",
                    help="print the process table with classifications, do not reap")
    args = ap.parse_args(argv)

    if args.list:
        rows = list_processes()
        for row in sorted(rows, key=lambda r: r.get("pid", 0)):
            verdict, detail = classify(row, args.grace)
            print(f"{row.get('pid', 0):>6} {row.get('status','?'):<8} "
                  f"{verdict:<11} {(row.get('cmdline_str') or '')[:110]}")
        return 0

    record = reap_strays(args.scan_root, grace_multiplier=args.grace,
                         dry_run=args.dry_run, evidence_path=args.evidence)
    if record.get("counts_before", {}).get("STRAY", 0) and not args.dry_run:
        return 1  # reaper ran and killed strays
    return 0


if __name__ == "__main__":
    sys.exit(_main())
