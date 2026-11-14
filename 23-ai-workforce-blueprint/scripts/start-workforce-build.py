#!/usr/bin/env python3
"""start-workforce-build.py -- finish the interview, start the build.

A Telegram send does not start an agent turn (see the dispatch-result note near
the end of resume-workforce-build.sh): an outbound message never becomes an
inbound turn, so a self-ping can never start a build. This program is the thing
that actually starts one, or records that an agent turn is needed:

  * standard-first box, prebuild done, owner review not settled -> write the
    build's config (answers_to_config.py) and launch the apply-diff build
    DETACHED. It can run for more than an hour, so it is never awaited;
  * any other lane -> write `.workforce-build-wanted.json` so the Command
    Center's build-kick job can start an agent turn (a script cannot).

Usage
  start-workforce-build.py --state FILE [--dry-run]

Exit codes (interface contract, 01-BUILD-SPEC.md section 2.5)
  0  one JSON action line on standard output (see below)
  3  refused: the interview is not complete, its QC verdict is not
     build-eligible, the state file cannot be read, or the config could not be
     written. Nothing is started and nothing is written.

The one JSON line is one of
  {"action":"none"}                     buildCompletedAt is already set
  {"action":"already-running"}          a start (or a live build) is in flight
  {"action":"apply-started","pid":N}    the apply-diff build is running detached
  {"action":"agent-turn-wanted"}        the wanted file asks for an agent turn

Files (interface contract, section 2.1), all in the state file's folder:
  .workforce-build-start.json  {startedAt, pid, command, logPath}, then
                               {exitedAt, exitCode} appended when the build exits
  .workforce-build-start.log   the detached build's output
  .workforce-build-wanted.json {wantedAt, reason, buildId}

The in-flight marker is the one resume-workforce-build.sh stamps
(.workforce-build-resume.inflight, 20-minute life, WORKFORCE_RESUME_INFLIGHT_TTL_MINUTES
overrides it): a fresh marker means a start/turn is already in flight. Because a
real build outlives that marker, a start record younger than 90 minutes whose
process is still alive also counts as "already running" -- that is what stops a
*/15 cron fire from stacking a second build over the first.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

INFLIGHT_NAME = ".workforce-build-resume.inflight"
START_RECORD_NAME = ".workforce-build-start.json"
START_LOG_NAME = ".workforce-build-start.log"
WANTED_NAME = ".workforce-build-wanted.json"
DEFAULT_INFLIGHT_TTL_MINUTES = 20
START_RECORD_MAX_MINUTES = 90
# How much of the build log after the launch point is scanned for the
# procedure-step stop. The build writes far more than this on a real box; the
# stop line is printed at the end of the run, so the tail is what matters.
LOG_SCAN_BYTES = 4 * 1024 * 1024
# The two lines build-workforce.py / populate-sops-from-manifest.py print when
# the procedure step stops for an owner-input-required model (finding WF-021
# link 7: populate-sops-from-manifest.py returns 3 there).
PROCEDURE_STOP_SIGNATURES = (
    "SOP populate rc=3",
    "Selector returned Tier 5 (owner-input-required)",
)


# ---- small helpers ---------------------------------------------------------------------------
def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit(obj: dict) -> None:
    """The one JSON line. Nothing else is written to standard output."""
    print(json.dumps(obj, separators=(",", ":")), flush=True)


def write_json_atomic(path: Path, data: dict, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def inflight_ttl_minutes() -> int:
    raw = os.environ.get("WORKFORCE_RESUME_INFLIGHT_TTL_MINUTES", "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = DEFAULT_INFLIGHT_TTL_MINUTES
    return max(value, 5)


def process_alive(pid) -> bool:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
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


def _iso_to_epoch(value) -> float | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.timestamp()


# ---- the decisions ---------------------------------------------------------------------------
def marker_is_fresh(workspace: Path) -> bool:
    marker = workspace / INFLIGHT_NAME
    try:
        age = time.time() - marker.stat().st_mtime
    except OSError:
        return False
    # A marker stamped in the future (clock skew) still means "in flight".
    return age < inflight_ttl_minutes() * 60


def build_is_running(workspace: Path) -> bool:
    """A start record younger than 90 minutes whose process is still alive."""
    record = read_json(workspace / START_RECORD_NAME)
    if not isinstance(record, dict):
        return False
    if record.get("exitedAt"):
        return False
    started = _iso_to_epoch(record.get("startedAt"))
    if started is None:
        return False
    age = time.time() - started
    if age >= START_RECORD_MAX_MINUTES * 60:
        return False
    return process_alive(record.get("pid"))


def procedure_stop_in_log(log_path: Path, offset: int) -> bool:
    try:
        size = log_path.stat().st_size
    except OSError:
        return False
    if size <= offset:
        return False
    start = max(offset, size - LOG_SCAN_BYTES)
    try:
        with open(log_path, "rb") as fh:
            fh.seek(start)
            tail = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return False
    return any(signature in tail for signature in PROCEDURE_STOP_SIGNATURES)


def wanted_payload(state: dict, reason) -> dict:
    return {
        "wantedAt": now_iso(),
        "reason": reason,
        "buildId": state.get("buildId"),
    }


def wanted_reason(state: dict, rc: int, log_path: Path, offset: int):
    """Why an agent turn is wanted: the exit code, or 3 from the procedure step."""
    if rc != 0:
        return str(rc)
    if procedure_stop_in_log(log_path, offset):
        return "3"
    return None


# ---- the two lanes ---------------------------------------------------------------------------
def start_apply_build(state_path: Path, workspace: Path, state: dict) -> int:
    """Write the config, then launch the apply-diff build detached."""
    config_path = workspace / "company-discovery" / "workforce-config.generated.json"
    log_path = workspace / START_LOG_NAME
    record_path = workspace / START_RECORD_NAME
    build_script = HERE / "build-workforce.py"
    config_script = HERE / "answers_to_config.py"

    with open(log_path, "ab") as log_handle:
        log_handle.write(
            f"[start-workforce-build] {now_iso()} writing the build config: "
            f"{config_script.name} --state {state_path.name}\n".encode("utf-8")
        )
        log_handle.flush()
        config_rc = subprocess.call(
            [sys.executable, "-B", str(config_script),
             "--state", str(state_path),
             "--state-dir", str(workspace / "company-discovery"),
             "--out", str(config_path)],
            stdout=log_handle, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, cwd=str(HERE),
        )

    if config_rc != 0:
        message = (
            f"answers_to_config.py exited {config_rc} - the build config was not written, "
            f"so the build was not started (see {log_path.name})"
        )
        print(f"start-workforce-build: {message}", file=sys.stderr)
        emit({"action": "refused", "reason": message})
        return 3

    build_cmd = [sys.executable, "-B", str(build_script),
                 "--non-interactive", "--config-file", str(config_path),
                 "--apply-standard-edits"]
    supervise_cmd = [sys.executable, "-B", os.path.abspath(__file__), "--_supervise",
                     str(state_path), str(record_path), str(workspace), "--"] + build_cmd

    with open(log_path, "ab") as log_handle:
        proc = subprocess.Popen(
            supervise_cmd,
            stdout=log_handle, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            start_new_session=True, cwd=str(HERE),
        )

    write_json_atomic(record_path, {
        "startedAt": now_iso(),
        "pid": proc.pid,
        "command": " ".join(build_cmd),
        "logPath": str(log_path),
    })
    (workspace / INFLIGHT_NAME).write_text(now_iso() + "\n", encoding="utf-8")
    emit({"action": "apply-started", "pid": proc.pid})
    return 0


def want_agent_turn(state_path: Path, workspace: Path, state: dict, reason: str) -> int:
    write_json_atomic(workspace / WANTED_NAME, wanted_payload(state, reason))
    (workspace / INFLIGHT_NAME).write_text(now_iso() + "\n", encoding="utf-8")
    emit({"action": "agent-turn-wanted"})
    return 0


# ---- the detached supervisor ------------------------------------------------------------------
def supervise(argv: list) -> int:
    """Run the build, then append {exitedAt, exitCode} and record a needed turn.

    Started as its own session by the parent, so the build outlives the caller.
    """
    try:
        sep = argv.index("--")
    except ValueError:
        print("start-workforce-build: --_supervise needs '--' before the build command", file=sys.stderr)
        return 1
    state_path = Path(argv[0])
    record_path = Path(argv[1])
    workspace = Path(argv[2])
    build_cmd = argv[sep + 1:]
    if not build_cmd:
        print("start-workforce-build: --_supervise got no build command", file=sys.stderr)
        return 1

    # The parent writes the start record right after spawning us; do not run the
    # build until it exists, so {exitedAt, exitCode} can never land first.
    for _ in range(200):
        if record_path.exists():
            break
        time.sleep(0.05)

    log_path = workspace / START_LOG_NAME
    try:
        offset = log_path.stat().st_size
    except OSError:
        offset = 0

    with open(log_path, "ab") as log_handle:
        log_handle.write(
            f"[start-workforce-build] {now_iso()} starting: {' '.join(build_cmd)}\n".encode("utf-8")
        )
        log_handle.flush()
        rc = subprocess.call(build_cmd, stdout=log_handle, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, cwd=str(HERE))

    record = read_json(record_path)
    if not isinstance(record, dict):
        record = {}
    record["exitedAt"] = now_iso()
    record["exitCode"] = rc
    write_json_atomic(record_path, record)

    state = read_json(state_path)
    if not isinstance(state, dict):
        state = {}
    reason = wanted_reason(state, rc, log_path, offset)
    if reason is not None:
        write_json_atomic(workspace / WANTED_NAME, wanted_payload(state, reason))
        print(f"start-workforce-build: build exited {rc}; an agent turn is wanted (reason={reason})",
              file=sys.stderr)
    return 0


# ---- the public command ----------------------------------------------------------------------
def main(argv: list | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--_supervise"]:
        return supervise(argv[1:])

    ap = argparse.ArgumentParser(description="Start the workforce build after the interview")
    ap.add_argument("--state", required=True, help="the build state file (.workforce-build-state.json)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report the action this run would take; write and start nothing")
    args = ap.parse_args(argv)

    state_path = Path(args.state).expanduser()
    if not state_path.is_absolute():
        state_path = Path(os.path.abspath(state_path))
    workspace = state_path.parent

    state = read_json(state_path)
    if not isinstance(state, dict):
        message = f"the build state is missing or unreadable: {state_path}"
        print(f"start-workforce-build: {message}", file=sys.stderr)
        emit({"action": "refused", "reason": message})
        return 3

    if state.get("interviewComplete") is not True:
        message = "interviewComplete is not true - the interview is not finished"
        print(f"start-workforce-build: {message}", file=sys.stderr)
        emit({"action": "refused", "reason": message})
        return 3

    qc = state.get("interviewQc")
    qc_status = qc.get("status") if isinstance(qc, dict) else None
    if qc_status not in ("pass", "needs-review"):
        message = (f"interviewQc.status={qc_status or 'unset'} is not build-eligible "
                   f"(eligible: pass|needs-review)")
        print(f"start-workforce-build: {message}", file=sys.stderr)
        emit({"action": "refused", "reason": message})
        return 3

    completed_at = state.get("buildCompletedAt")
    if isinstance(completed_at, str) and completed_at.strip():
        emit({"action": "none"})
        return 0

    if marker_is_fresh(workspace) or build_is_running(workspace):
        emit({"action": "already-running"})
        return 0

    prebuild = state.get("standardPrebuild")
    prebuild_status = prebuild.get("status") if isinstance(prebuild, dict) else None
    apply_lane = (
        state.get("buildType") == "standard-first"
        and prebuild_status == "done"
        and state.get("confirmationsComplete") is not True
    )

    if apply_lane:
        if args.dry_run:
            emit({"action": "apply-started", "dryRun": True})
            return 0
        return start_apply_build(state_path, workspace, state)

    if args.dry_run:
        emit({"action": "agent-turn-wanted", "dryRun": True})
        return 0
    return want_agent_turn(state_path, workspace, state,
                           "interview complete, departments not planned")


if __name__ == "__main__":
    raise SystemExit(main())
