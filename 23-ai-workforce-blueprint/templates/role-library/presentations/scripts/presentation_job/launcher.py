"""Engine dispatch bridge -- the single entry point for launching the engine.

WORK-ITEM-02: Every caller (intake poll.sh, canonical entry, CC ingest callback)
uses this shared dispatch function instead of independently constructing the
`presentation_job --new --run-dir <dir>` invocation. Centralizes dispatch logic so
there is exactly one place where the engine is launched.

Root cause prevented: The engine (presentation_job.py + 18 modules, 552 tests)
has zero production callers (CURRENT-STATE Section B breakpoint 5). The intake
cron, canonical entry, and CC all stop short. This module closes that gap.

CAPACITY GATE (unit u07)
------------------------
Dispatch now measures before it launches. capacity.probe() detects THIS client's
provider and plan; if it cannot produce a dispatchable number -- the plan is
undeclared (PARKED behind the one-time interview question), or a declared
capacity_override.json is unusable (FAILED) -- dispatch REFUSES with
AF-CAPACITY-UNMEASURED and a non-zero exit, and no engine process is spawned.
A capacity probe whose result nothing acts on is an advisory print, not a gate;
this is the acting-on.

THE NO-CONFIG CASE (UNDETERMINED) IS NOT THE SAME AS MEASURED
---------------------------------------------------------------
A box with no capacity_override.json, no 9Router combo, and no OpenClaw config
-- the state almost every client box starts in -- is UNDETERMINED, not FAILED
and not PARKED. capacity.probe() answers that with `available =
DEFAULT_CONSERVATIVE (3)` so the department is not dead out of the box, but
that 3 was never measured; it is a floor, never a proven ceiling.

Refusing every unconfigured box would make the department unusable by default,
which is its own outage -- so this gate does NOT refuse on UNDETERMINED alone.
Instead it does three things a plain "capacity measured" print cannot be
mistaken for:
  1. proceeds at the conservative floor, with a banner that says UNDETERMINED
     out loud (never the same line MEASURED prints);
  2. records the probe result into run state (state.json / a pre-state.json
     sidecar) so the anomaly outlives the launch log line;
  3. pings the operator (best-effort, never fatal to dispatch) so a fleet of
     boxes silently running at the floor is visible, not just archived.

It DOES refuse -- the same AF-CAPACITY-UNMEASURED, same non-zero exit, same
"nothing spawned" contract as PARKED/FAILED -- when a caller declares
`requested_parallel` and that request exceeds the conservative floor while
capacity is UNDETERMINED. Wanting more parallel width than the un-measured
floor, without a real measurement backing it, is exactly the blind dispatch
this gate exists to stop; wanting the floor itself (or not declaring a
request at all -- the overwhelming majority of callers today) is not.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Tuple


# ---------------------------------------------------------------------------
# Dispatch return sentinels and exit codes
# ---------------------------------------------------------------------------
#: dispatch() already returns -1 (failure), -2 (already running) and -3 (already
#: DONE). -4 joins that family: capacity could not be measured, so NOTHING was
#: spawned. Callers that only test `> 0` keep working unchanged.
DISPATCH_CAPACITY_REFUSED = -4

#: CLI exit code for a capacity refusal (== state.EXIT_GATE_BLOCKED).
EXIT_CAPACITY_UNMEASURED = 3

CAPACITY_AUTOFAIL_CODE = "AF-CAPACITY-UNMEASURED"

#: Mirrors capacity.STATUS_UNDETERMINED. `available` is non-None in this status
#: (it's capacity.DEFAULT_CONSERVATIVE) but was NEVER MEASURED -- it is a floor
#: to proceed AT, not a ceiling this account was proven to support. Checking
#: only `available is None` (as this gate used to) treats the no-config case,
#: which is what nearly every client box IS, as a clean measurement. See
#: dispatch()'s capacity gate below.
CAPACITY_STATUS_UNDETERMINED = "UNDETERMINED"


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
def resolve_scripts_dir() -> Path:
    """Walk up from this file's location to find the scripts/ directory.

    The scripts/ dir is the one containing run_signature_deck.py and build_deck.py.
    Returns the absolute Path. Exits 2 if not found.
    """
    here = Path(__file__).resolve().parent  # presentation_job/
    scripts = here.parent  # scripts/
    if (scripts / "build_deck.py").is_file() and (scripts / "run_signature_deck.py").is_file():
        return scripts
    print(f"launcher: canonical scripts not found under {scripts}", file=sys.stderr)
    print("  expected build_deck.py + run_signature_deck.py", file=sys.stderr)
    sys.exit(2)


def resolve_runs_root() -> Path:
    """Return the canonical Presentations runs/ directory."""
    scripts = resolve_scripts_dir()
    return scripts.parent / "runs"


# ---------------------------------------------------------------------------
# Engine lifecycle
# ---------------------------------------------------------------------------
def is_engine_running(run_dir: str | Path) -> bool:
    """Read the recorded engine PID (state.json, or .engine.pid sidecar before
    state.json exists). Check if that PID is still alive.

    Uses os.kill(pid, 0) -- signal 0 is an existence check, never a real signal.
    Returns True if running, False if dead or no PID recorded.
    """
    pid = _read_engine_pid(run_dir)
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def stop_engine(run_dir: str | Path) -> bool:
    """Read the recorded engine PID (state.json, or .engine.pid sidecar before
    state.json exists). Send SIGTERM to the process group.

    Wait up to 10 seconds. If still alive, SIGKILL. Returns True on
    successful stop, False on timeout.
    """
    pid = _read_engine_pid(run_dir)
    if pid is None:
        return True  # nothing to stop
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        pass
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return True
        time.sleep(0.5)
    try:
        os.killpg(pid, signal.SIGKILL)
    except OSError:
        return True
    return True


def _engine_pid_sidecar(run_dir: str | Path) -> Path:
    """Path of the engine-pid sidecar used until state.json exists.

    Canary D1 (R3): launcher.py must not create state.json itself on --new --
    the engine's cmd_new refuses to start when state.json already exists. Until
    cmd_new has written state.json, the engine PID is recorded here; once
    state.json exists the PID lives inside it (is_engine_running/stop_engine
    read the sidecar only as a fallback)."""
    return Path(run_dir) / ".engine.pid"


def _write_engine_pid(run_dir: str | Path, pid: int) -> None:
    """Record the engine PID for the watchdog to monitor.

    If state.json exists, the PID is merged into it (preserving every field
    the engine wrote). If state.json does not exist yet -- the --new window,
    before cmd_new has run -- the PID goes to the .engine.pid sidecar instead;
    state.json is NEVER created here, so the engine's 'state.json already
    exists' refusal can never trigger from the launcher."""
    run_path = Path(run_dir).expanduser().resolve()
    state_path = run_path / "state.json"
    if state_path.is_file():
        state: dict = {}
        try:
            state = json.loads(state_path.read_text(encoding="utf-8")) or {}
        except (json.JSONDecodeError, OSError):
            state = {}
        state["engine_pid"] = pid
        tmp = state_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        os.replace(tmp, state_path)
        try:
            _engine_pid_sidecar(run_path).unlink(missing_ok=True)
        except OSError:
            pass
        return
    # No state.json yet: sidecar only. Never synthesize state.json here.
    sidecar = _engine_pid_sidecar(run_path)
    try:
        tmp = sidecar.with_suffix(".pid.tmp")
        tmp.write_text(f"{pid}\n", encoding="utf-8")
        os.replace(tmp, sidecar)
    except OSError as exc:
        print(f"launcher: could not record engine pid {pid}: {exc}", file=sys.stderr)


def _read_engine_pid(run_dir: str | Path) -> Optional[int]:
    """Read the recorded engine PID: state.json first, .engine.pid sidecar second."""
    run_path = Path(run_dir).expanduser().resolve()
    state_path = run_path / "state.json"
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            state = {}
        pid = state.get("engine_pid")
        if isinstance(pid, int) and pid > 0:
            return pid
    sidecar = _engine_pid_sidecar(run_path)
    if sidecar.is_file():
        try:
            pid = int(sidecar.read_text(encoding="utf-8").strip())
            if pid > 0:
                return pid
        except (OSError, ValueError):
            pass
    return None


# ---------------------------------------------------------------------------
# Capacity gate -- measured before anything is launched
# ---------------------------------------------------------------------------
def capacity_gate() -> Tuple[Optional[int], dict]:
    """Probe THIS client's capacity. Returns (available, probe_result).

    `available` is None when the probe could not produce a number, which is the
    dispatch path's refusal condition. An import failure of the capacity module
    is itself an unmeasured capacity -- it is never treated as "no limit"."""
    try:
        try:
            from . import capacity  # package-relative (python3 -m presentation_job)
        except ImportError:
            import capacity  # direct file run from presentation_job/
        result = capacity.probe()
        return capacity.available_or_none(result), result
    except Exception as exc:  # noqa: BLE001 -- an unreadable probe is UNMEASURED
        return None, {
            "status": "FAILED",
            "available": None,
            "notes": [f"capacity probe could not run: {exc.__class__.__name__}: {exc}"],
        }


def _refuse_unmeasured_capacity(result: dict, run_path: Path) -> int:
    """Emit the autofail and refuse. No engine process has been created."""
    try:
        try:
            from . import capacity
        except ImportError:
            import capacity
        payload = capacity.autofail_payload(result)
        detail = capacity.refusal_message(result)
    except Exception:  # noqa: BLE001 -- refuse loudly even if capacity.py is gone
        payload = {"code": CAPACITY_AUTOFAIL_CODE, "detail": str(result)}
        detail = str(result)
    payload["run_dir"] = str(run_path)
    print(f"launcher: REFUSING to dispatch {run_path} -- {CAPACITY_AUTOFAIL_CODE}: "
          f"{detail}", file=sys.stderr)
    print(json.dumps(payload, indent=2), file=sys.stderr)
    return DISPATCH_CAPACITY_REFUSED


def _refuse_undetermined_parallel(result: dict, run_path: Path, requested: int,
                                  available: int) -> int:
    """Refuse a wide-parallel request when capacity was never actually measured.

    UNDETERMINED's `available` is capacity.DEFAULT_CONSERVATIVE -- a floor to
    proceed AT, never a ceiling this account was proven to support. A caller
    that declares it wants MORE than that floor, with nothing backing the
    number, is exactly the blind dispatch AF-CAPACITY-UNMEASURED exists to
    stop -- so this refuses the same way an unusable override refuses: same
    code, same non-zero sentinel, nothing spawned."""
    detail = (
        f"requested {requested} concurrent, but capacity is UNDETERMINED (no "
        f"provider/plan could be detected) -- only the conservative floor of "
        f"{available} is safe to assume. Declare capacity_override.json or answer "
        f"the capacity interview ('python3 -m presentation_job --capacity') to "
        f"unlock wider dispatch."
    )
    payload = {
        "code": CAPACITY_AUTOFAIL_CODE,
        "status": result.get("status"),
        "detection_source": result.get("detection_source"),
        "requested": requested,
        "conservative_floor": available,
        "run_dir": str(run_path),
        "detail": detail,
    }
    print(f"launcher: REFUSING to dispatch {run_path} -- {CAPACITY_AUTOFAIL_CODE}: "
          f"{detail}", file=sys.stderr)
    print(json.dumps(payload, indent=2), file=sys.stderr)
    return DISPATCH_CAPACITY_REFUSED


def _record_capacity_status(run_path: Path, result: dict) -> None:
    """Record an UNDETERMINED probe into run state so the anomaly outlives the
    launch-line log entry. Written unconditionally to a `.capacity-status.json`
    sidecar (never depends on state.json existing yet -- the --new window,
    before cmd_new runs, is exactly when this matters) and merged into
    state.json too once it exists, mirroring _write_engine_pid's dual-write
    pattern. Best-effort: a write failure here must never affect dispatch."""
    record = {
        "status": result.get("status"),
        "available": result.get("available"),
        "provider": result.get("provider"),
        "plan": result.get("plan"),
        "detection_source": result.get("detection_source"),
        "notes": result.get("notes"),
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    try:
        run_path.mkdir(parents=True, exist_ok=True)
        sidecar = run_path / ".capacity-status.json"
        tmp = sidecar.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(record, indent=2), encoding="utf-8")
        os.replace(tmp, sidecar)
    except OSError as exc:
        print(f"launcher: could not record capacity status: {exc}", file=sys.stderr)
        return
    state_path = run_path / "state.json"
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8")) or {}
        except (json.JSONDecodeError, OSError):
            state = {}
        state["capacity_status"] = record
        tmp = state_path.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
            os.replace(tmp, state_path)
        except OSError as exc:
            print(f"launcher: could not merge capacity status into state.json: {exc}",
                  file=sys.stderr)


def _notify_operator_undetermined(result: dict, run_path: Path, available: int) -> None:
    """Best-effort ping to the operator channel. Follows watchdog.py's own
    precedent (report.dispatch("watchdog", "stall", ...): a fixed, non-numeric
    chat_id names the subsystem raising the alert, distinct from any per-job
    requester chat_id). A notify failure is swallowed -- it must never affect
    the dispatch decision."""
    try:
        try:
            from . import report
        except ImportError:
            import report
        report.dispatch(
            "capacity",
            "capacity_undetermined",
            f"Presentations: capacity UNDETERMINED for {run_path} -- dispatching at "
            f"the conservative floor of {available} only (provider/plan could not be "
            f"detected). Declare capacity_override.json or answer the capacity "
            f"interview to unlock this box's real ceiling.",
        )
    except Exception:  # noqa: BLE001 -- never let operator-notify break dispatch
        pass


def _announce_undetermined_capacity(result: dict, run_path: Path, available: int) -> None:
    """Make the UNDETERMINED case impossible to miss: a banner that cannot be
    confused with the MEASURED print, a run-state record, and an operator
    ping. This -- not silence -- is what closes the no-config hole without
    turning an unconfigured box into an outage."""
    banner = (
        f"launcher: !! CAPACITY UNDETERMINED for {run_path} -- no provider/plan "
        f"could be detected (checked: declared override, 9Router, OpenClaw). "
        f"Proceeding at the conservative floor of {available} concurrent agent(s) "
        f"ONLY -- never guessed upward. Run 'python3 -m presentation_job --capacity' "
        f"(or answer the one-time capacity interview) to declare this box's real "
        f"ceiling."
    )
    print(banner, file=sys.stderr)
    print(banner, flush=True)
    _record_capacity_status(run_path, result)
    _notify_operator_undetermined(result, run_path, available)


# ---------------------------------------------------------------------------
# Dispatch -- the single entry point all callers use
# ---------------------------------------------------------------------------
def dispatch(
    run_dir: str,
    client: Optional[str] = None,
    deck_type: Optional[str] = None,
    resume: bool = False,
    phase: Optional[str] = None,
    until: Optional[str] = None,
    background: bool = True,
    requested_parallel: Optional[int] = None,
) -> int:
    """Launch the presentation engine.

    Args:
        run_dir: The job's run directory (must exist with state.json for resume).
        client: Client identifier for --new (written into state.json).
        deck_type: Deck type for --new (signature_presentation, standard, etc).
        resume: If True, use --resume instead of --new.
        phase: Run exactly one phase (passed through to engine --phase).
        until: Run through this phase then stop (passed through to --until).
        background: If True, spawn as detached subprocess (default).
                    If False, run synchronously (for testing).
        requested_parallel: How much parallel width this run wants, if the
                    caller knows and cares to declare it. None (the default,
                    and every caller today) means "no declared request" --
                    dispatch proceeds at whatever capacity.probe() measures,
                    including the conservative floor when it is UNDETERMINED.
                    When given AND capacity is UNDETERMINED, a request above
                    the conservative floor is refused (see the gate below);
                    it is never checked against a real MEASURED ceiling --
                    execution_plan.py already waves a wide request down to
                    a measured ceiling instead of refusing it.

    Returns:
        PID on success (int > 0), -1 on failure, -4 when the capacity gate
        refused (AF-CAPACITY-UNMEASURED, nothing spawned).
        The function returns immediately when background=True.
    """
    scripts = resolve_scripts_dir()
    engine_entry = scripts / "presentation_job.py"
    if not engine_entry.is_file():
        print(f"launcher: engine entry not found at {engine_entry}", file=sys.stderr)
        return -1

    run_path = Path(run_dir).expanduser().resolve()

    # THE GATE. Measure before launching -- before argv is built, before any
    # process exists. A run that cannot be sized is a run that does not start.
    #
    # available is None            -> PARKED or FAILED: no number at all. Refuse.
    # status == UNDETERMINED       -> a number, but never MEASURED -- it is
    #                                  capacity.DEFAULT_CONSERVATIVE, a floor to
    #                                  proceed AT. Refuse ONLY if the caller
    #                                  declared it wants more than that floor;
    #                                  otherwise proceed, but loudly, on record,
    #                                  and with the operator told.
    # anything else (MEASURED)     -> a real, detected ceiling. Proceed as before.
    available, capacity_result = capacity_gate()
    if available is None:
        return _refuse_unmeasured_capacity(capacity_result, run_path)

    if capacity_result.get("status") == CAPACITY_STATUS_UNDETERMINED:
        if requested_parallel is not None and requested_parallel > available:
            return _refuse_undetermined_parallel(capacity_result, run_path,
                                                 requested_parallel, available)
        _announce_undetermined_capacity(capacity_result, run_path, available)
    else:
        print(f"launcher: capacity measured -- {available} concurrent agents available "
              f"(provider {capacity_result.get('provider')}, plan "
              f"{capacity_result.get('plan')}, source "
              f"{capacity_result.get('detection_source')})", flush=True)

    argv = [
        sys.executable or "python3",
        str(engine_entry),
    ]
    if resume:
        argv.append("--resume")
    else:
        argv.append("--new")
    argv.extend(["--run-dir", str(run_path)])

    if client and not resume:
        # --client and --deck-type are intake-time flags; they are embedded
        # in state.json during --new (cmd_new reads intake from --intake),
        # so they are not passed as separate CLI flags to the engine.
        # Instead, we pass them via the intake JSON mechanism: the intake
        # bridge populates working/copy/intake.json (launcher contract --
        # see dispatch_new's docstring). Pass that file to --new.
        intake_arg: Optional[str] = None
        for cand in (
            run_path / "working" / "copy" / "intake.json",
            run_path / "working" / "checkpoints" / ".engine-intake.json",
        ):
            if cand.is_file():
                intake_arg = str(cand)
                break
        if intake_arg:
            argv.extend(["--intake", intake_arg])
        else:
            print(f"launcher: WARNING no intake JSON at {run_path}/working/copy/intake.json "
                  "-- engine --new will refuse (presentation_type required)", file=sys.stderr)
    if resume:
        intake_check = run_path / "working" / "checkpoints" / ".engine-intake.json"
        if intake_check.is_file():
            argv.extend(["--intake", str(intake_check)])

    if phase:
        argv.extend(["--phase", phase])
    if until:
        argv.extend(["--until", until])

    if background:
        # Spawn detached: new process group, stdout/stderr to run-dir logs.
        log_dir = run_path / "working" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = log_dir / "engine-stdout.log"
        stderr_path = log_dir / "engine-stderr.log"

        try:
            proc = subprocess.Popen(
                argv,
                shell=False,
                cwd=str(scripts),
                stdout=stdout_path.open("a", encoding="utf-8"),
                stderr=stderr_path.open("a", encoding="utf-8"),
                start_new_session=True,  # new process group for orphan-free timeout
                close_fds=True,
            )
        except OSError as exc:
            print(f"launcher: could not start engine: {exc}", file=sys.stderr)
            return -1

        # Canary D1 (R3): record the engine PID ONLY after the spawn succeeded.
        # _write_engine_pid never creates state.json -- if cmd_new has not run
        # yet (the --new window) the PID lands in the .engine.pid sidecar, so
        # the engine's 'state.json already exists' refusal can never trigger
        # from the launcher. Same path for --new and --resume.
        _write_engine_pid(run_path, proc.pid)
        # Then, once cmd_new HAS written state.json (the --new path), merge the
        # PID into it so the watchdog sees a self-contained record. Poll briefly
        # (cmd_new is fast) and fall back to the sidecar without error.
        if not resume:
            deadline = time.time() + 5.0
            state_path = run_path / "state.json"
            while time.time() < deadline and not state_path.is_file():
                time.sleep(0.1)
            if state_path.is_file():
                try:
                    state = json.loads(state_path.read_text(encoding="utf-8")) or {}
                except (json.JSONDecodeError, OSError):
                    state = {}
                state["engine_pid"] = proc.pid
                tmp = state_path.with_suffix(".json.tmp")
                tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
                os.replace(tmp, state_path)
        print(f"Engine launched: PID {proc.pid}  run-dir={run_path}  "
              f"cmd={' '.join(argv)}", flush=True)
        print(f"  logs: {stdout_path}, {stderr_path}", flush=True)
        return proc.pid
    else:
        # Synchronous -- run in foreground (for testing / debugging).
        try:
            proc = subprocess.run(argv, shell=False, cwd=str(scripts), check=False)
        except OSError as exc:
            print(f"launcher: could not start engine: {exc}", file=sys.stderr)
            return -1
        # The child has already exited; recording a PID for a finished process
        # is meaningless, so nothing is written here. The engine's cmd_new
        # wrote state.json itself (if it succeeded).
        return proc.returncode


def dispatch_new(
    run_dir: str,
    client: str,
    deck_type: str,
    background: bool = True,
    requested_parallel: Optional[int] = None,
) -> int:
    """Convenience wrapper: launch a new engine job.

    This is the call point for the intake bridge (poll.sh completion path)
    and the canonical entry after GATE 0/0b/1/1b/2/3 pass.

    The engine's --new path reads intake_json from the run directory's
    working/copy/intake.json (populated by the intake interview).

    requested_parallel: see dispatch()'s docstring -- None (default) means no
    declared request; the capacity gate still runs either way.

    Returns PID on success, -1 on failure.
    """
    # Verify the run dir is ready for --new
    run_path = Path(run_dir).expanduser().resolve()
    state_path = run_path / "state.json"
    if state_path.is_file():
        # state.json already exists -- check if engine is already running or completed
        if is_engine_running(run_path):
            print(f"launcher: engine already running for {run_path}", flush=True)
            return -2  # distinct code for "already running"
        # If terminal, refuse to re-launch (must --resume instead)
        try:
            st = json.loads(state_path.read_text(encoding="utf-8"))
            if st.get("terminal") in ("DONE",):
                print(f"launcher: job {run_path} is already DONE -- refusing to re-launch", flush=True)
                return -3
        except (json.JSONDecodeError, OSError):
            pass

    return dispatch(run_dir, client=client, deck_type=deck_type, resume=False,
                    background=background, requested_parallel=requested_parallel)


def dispatch_resume(run_dir: str, background: bool = True,
                    requested_parallel: Optional[int] = None) -> int:
    """Convenience wrapper: resume a parked engine job.

    Returns PID on success, -1 on failure.
    """
    run_path = Path(run_dir).expanduser().resolve()
    if not (run_path / "state.json").is_file():
        print(f"launcher: no state.json at {run_path} -- cannot resume", file=sys.stderr)
        return -1
    if is_engine_running(run_path):
        print(f"launcher: engine already running for {run_path}", flush=True)
        return -2
    return dispatch(run_dir, resume=True, background=background,
                    requested_parallel=requested_parallel)


# ---------------------------------------------------------------------------
# CLI entry point -- for shell-script callers (poll.sh, canonical entry)
# ---------------------------------------------------------------------------
def main(argv: Optional[list] = None) -> int:
    import argparse
    p = argparse.ArgumentParser(
        prog="launcher.py",
        description="Engine dispatch bridge -- launch the presentation engine",
    )
    p.add_argument("--run-dir", type=Path, required=True,
                   help="the job's run directory")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--new", action="store_true",
                   help="launch a new engine job")
    g.add_argument("--resume", action="store_true",
                   help="resume a parked engine job")
    p.add_argument("--client", help="client identifier")
    p.add_argument("--deck-type", help="deck type (signature_presentation, standard, etc)")
    p.add_argument("--foreground", action="store_true",
                   help="run synchronously (for testing)")
    p.add_argument("--phase", help="run exactly one phase")
    p.add_argument("--until", help="run through this phase then stop")
    p.add_argument("--check", action="store_true",
                   help="check if engine is running; exit 0 if yes, 1 if no")
    p.add_argument("--stop", action="store_true",
                   help="stop the engine for this run-dir")
    p.add_argument("--requested-parallel", type=int, default=None,
                   help="declare the parallel width this run wants. Only checked "
                        "when capacity is UNDETERMINED: a request above the "
                        "conservative floor (3) is refused (AF-CAPACITY-UNMEASURED). "
                        "Omit (the default) to run at whatever capacity.probe() "
                        "measures, floor included.")

    args = p.parse_args(argv)
    run_path = args.run_dir.expanduser().resolve()

    if args.check:
        running = is_engine_running(run_path)
        print(f"engine {'IS' if running else 'is NOT'} running for {run_path}")
        return 0 if running else 1

    if args.stop:
        ok = stop_engine(run_path)
        print(f"engine {'stopped' if ok else 'stop timed out'} for {run_path}")
        return 0 if ok else 1

    if args.foreground:
        # Sync mode: dispatch returns the engine's own exit code (0 == ok), or a
        # negative sentinel when the launcher itself refused before spawning.
        rc = dispatch_resume(str(run_path), background=False,
                             requested_parallel=args.requested_parallel) if args.resume else \
            dispatch_new(str(run_path),
                         client=args.client or "operator",
                         deck_type=args.deck_type or "standard",
                         background=False,
                         requested_parallel=args.requested_parallel)
        if rc == DISPATCH_CAPACITY_REFUSED:
            return EXIT_CAPACITY_UNMEASURED
        return 0 if rc == 0 else 1
    pid = dispatch_resume(str(run_path), background=True,
                          requested_parallel=args.requested_parallel) if args.resume else \
        dispatch_new(str(run_path),
                     client=args.client or "operator",
                     deck_type=args.deck_type or "standard",
                     background=True,
                     requested_parallel=args.requested_parallel)
    if pid == DISPATCH_CAPACITY_REFUSED:
        return EXIT_CAPACITY_UNMEASURED
    return 0 if pid > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
