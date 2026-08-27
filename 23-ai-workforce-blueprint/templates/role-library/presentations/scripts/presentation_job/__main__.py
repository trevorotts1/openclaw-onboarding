from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .state import (
    StateStore, RunLock, utcnow, sha256_text, _read_json,
    die, EXIT_OK, EXIT_USAGE, EXIT_MANIFEST_MISMATCH,
    EXIT_STATE_CORRUPT, EXIT_LOCK_HELD, STATE_SCHEMA_VERSION,
    EXIT_GATE_BLOCKED,
)
from .manifest import Manifest, resolve_manifest
from .phases import Engine
from .report import dispatch
from .watchdog import watchdog as _run_watchdog
from .board import BoardMirror
from .sweep import reconcile_sweep, default_scan_roots
from . import diagnose
from . import persona
from .vocab import CANONICAL_PRESENTATION_TYPES


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="presentation_job.py",
        description="The process engine for the Presentation Department. "
                    "Walks the manifest, refuses to skip a step, announces where it is.")
    m = p.add_mutually_exclusive_group(required=True)
    m.add_argument("--new", action="store_true", help="create a job in --run-dir from --intake")
    m.add_argument("--run", action="store_true", help="run the phase loop")
    m.add_argument("--resume", action="store_true",
                   help="resume a parked job from checkpoint; prints why it parked first. "
                        "With --phase, re-runs only that phase and does NOT evaluate gates, "
                        "so it cannot clear a job parked on a gate failure.")
    m.add_argument("--status", action="store_true", help="print job status")
    m.add_argument("--close", action="store_true", help="evaluate gates and close")
    m.add_argument("--watchdog", action="store_true", help="scan for stalled jobs")
    m.add_argument("--reconcile-board", action="store_true",
                   help="scan --scan-root for jobs whose board card is missing or behind; "
                        "reports only unless --apply is given")
    m.add_argument("--sweep-undeliverable", action="store_true",
                   help="retry every queued undeliverable message for --run-dir, oldest first")
    m.add_argument("--workingset", nargs="?", const="__all__", default=None, metavar="PHASE",
                   help="FIX-20: measure one phase's working-set token count (or all phases) and "
                        "report fit against the context-window cap. Exit 0 if every measured phase "
                        "fits one window, exit 3 (EXIT_GATE_BLOCKED) if any exceeds it.")
    m.add_argument("--capacity", action="store_true",
                   help="WORK-ITEM-12: run the 9Router capacity probe and print the report; "
                        "exit 0. Read-only measurement, never simulated.")
    p.add_argument("--run-dir", type=Path, help="the job's run directory")
    p.add_argument("--intake", type=Path, help="intake JSON for --new")
    p.add_argument("--manifest", help="explicit PIPELINE-MANIFEST.json path")
    p.add_argument("--phase", help="run exactly one phase")
    p.add_argument("--until", help="run through this phase then stop")
    p.add_argument("--scan-root", type=Path, action="append", default=None,
                   help="root to scan for --watchdog / --reconcile-board "
                        "(repeatable, or comma/os.pathsep-separated in one value; "
                        "also extendable via PRESENTATION_SCAN_ROOTS) -- "
                        "run-root-agnostic: runs may live under several roots")
    p.add_argument("--dry-run", action="store_true", help="print what would run, execute nothing")
    p.add_argument("--diagnose-only", action="store_true",
                   help="with --resume: print why the job parked and exit without resuming")
    p.add_argument("--json", action="store_true", help="machine-readable --status")
    p.add_argument("--apply", action="store_true",
                   help="with --reconcile-board: actually create and advance cards")
    p.add_argument("--max-age-hours", type=float, default=72.0,
                   help="with --reconcile-board: ignore run dirs created longer ago than this")
    # U016 adds --scan-depth with default 3 (was 2), plus --grace and --enforce for the watchdog.
    if not any("--scan-depth" in a.option_strings for a in p._actions):
        p.add_argument("--scan-depth", type=int, default=3,
                       help="how many directory levels below --scan-root to search for state.json")
    p.add_argument("--grace", type=float, default=1.5,
                   help="multiply the expected checkpoint interval by this before alarming")
    p.add_argument("--enforce", action="store_true",
                   help="exit 5 on a stall (default: report and exit 0)")
    # F07: the auto-spawn closes the fault where an agent-authored phase
    # (phases.py:_run_agent_phase) writes working/work-orders/<phase>.json and
    # then blocks polling for the artifact with NOTHING servicing that file --
    # see _spawn_dispatcher_if_available's docstring below. This flag (and its
    # env-var twin PRESENTATION_AUTO_DISPATCH=0) is the operator escape hatch:
    # run work_order_dispatcher.py yourself and this stops an auto-spawned
    # instance from racing it.
    p.add_argument("--no-auto-dispatch", action="store_true",
                   help="with --run/--resume: do not auto-spawn "
                        "work_order_dispatcher.py for this run (same as "
                        "PRESENTATION_AUTO_DISPATCH=0) -- use when you are "
                        "running the dispatcher yourself")
    return p


def cmd_new(args, scripts_dir: Path) -> int:
    run_dir = args.run_dir.expanduser().resolve()
    store = StateStore(run_dir)
    if store.exists():
        die(EXIT_USAGE, f"{store.path} already exists — refusing to overwrite a live job")
    intake = _read_json(args.intake) if args.intake else None
    if args.intake and intake is None:
        die(EXIT_USAGE, f"cannot read intake JSON at {args.intake}")
    intake = intake or {}

    ptype = intake.get("presentation_type")
    # Single-sourced with the entry script, the poll, and the launcher --
    # see vocab.py. This tuple must never be hand-copied again; two
    # independently maintained "legal" sets is the exact shape of the
    # deck-type-routing-bypass bug (a value present in both a caller's own
    # set and the engine's real set skips the caller's alias remap).
    legal = CANONICAL_PRESENTATION_TYPES
    if ptype not in legal:
        die(EXIT_USAGE,
            f"intake.presentation_type is {ptype!r}; must be one of {legal}.\n"
            "  This is the ONE question that derives both creation_mode and deck_type "
            "(deck-intake-driver.py:380-401). An unset value is AF-MODE-UNSET at preflight.")
    if ptype == "signature" and intake.get("signature_source") not in \
            ("from_scratch", "existing_content"):
        die(EXIT_USAGE,
            "presentation_type='signature' requires signature_source ∈ "
            "{from_scratch, existing_content} — it is the only thing that resolves creation_mode "
            "for a signature deck.")

    manifest_path = resolve_manifest(args.manifest, run_dir, scripts_dir)
    manifest = Manifest(manifest_path)
    manifest.verify_source()

    state = {
        "schema_version": STATE_SCHEMA_VERSION,
        "job_id": "pj_" + sha256_text(f"{run_dir}{utcnow()}")[:26],
        "run_dir": str(run_dir),
        "created_at": utcnow(),
        "manifest_path": str(manifest_path),
        "manifest_version": manifest.version,
        "manifest_sha256": manifest.sha256,
        "presentation_type": ptype,
        "requester": intake.get("requester") or {},
        "intake": intake,
        "current_phase": None,
        "phases": [],
        "gates": {},
        "waivers": [],
        "events": [],
        "sent": {},
        "undeliverable": [],
        "heartbeat": {},
        "terminal": None,
    }
    if not (state["requester"] or {}).get("chat_id"):
        die(EXIT_USAGE,
            "no requester.chat_id in intake. A presentations job with no requester cannot report "
            "progress or completion to anyone, and must not start (fix F1).")
    store.save(state)
    print(f"created {state['job_id']} in {run_dir}")
    print(f"  manifest v{manifest.version} ({len(manifest.phases)} phases) "
          f"pinned at {manifest.sha256[:12]}")
    return EXIT_OK


def cmd_status(args) -> int:
    store = StateStore(args.run_dir.expanduser().resolve())
    st = store.load()
    if args.json:
        print(json.dumps(st, indent=2))
        return EXIT_OK
    print(f"job      : {st['job_id']}")
    print(f"run dir  : {st['run_dir']}")
    print(f"manifest : v{st.get('manifest_version')} @ {str(st.get('manifest_sha256'))[:12]}")
    print(f"terminal : {st.get('terminal') or 'in progress'}")
    done = [p for p in st.get("phases", []) if p.get("status") == "done"]
    print(f"phases   : {len(done)} done")
    for p in st.get("phases", []):
        mark = {"done": "x", "running": ">", "blocked": "!", "pending": " "}.get(
            p.get("status", "pending"), "?")
        print(f"   [{mark}] {p['id']:<24} {p.get('status')}"
              + (f"  — {p.get('blocked_reason')}" if p.get("blocked_reason") else ""))
    for k, g in (st.get("gates") or {}).items():
        print(f"gate {k:<14} {g.get('state')}"
              + (f"  — {g.get('reason')}" if g.get("reason") else ""))
    # notify_target — the SPEC-mandated status line for WORK-ITEM-08/15 verification
    notify_cmd = os.environ.get("PRESENTATION_NOTIFY_CMD", "")
    if notify_cmd:
        print(f"notify_target = \"owner\"")
        print(f"notify_cmd    = {notify_cmd}")
        req = st.get("requester") or {}
        if req.get("chat_id"):
            print(f"requester_chat_id = {req['chat_id']}")
        sent = st.get("sent") or {}
        for k in ("ack", "done"):
            if k in sent:
                rec = sent[k]
                print(f"sent.{k:4}: {rec.get('count',0)} messages, "
                      f"last at {rec.get('last_at','?')}")
        progress_count = (sent.get("progress") or {}).get("count", 0)
        blocked_count = (sent.get("blocked") or {}).get("count", 0)
        print(f"sent.progress: {progress_count} messages")
        print(f"sent.blocked:  {blocked_count} messages")
    else:
        print("notify_target = \"none\" (PRESENTATION_NOTIFY_CMD unset — notifications disabled)")
    undelivered = st.get("undeliverable")
    if undelivered:
        print(f"UNDELIVERABLE messages: {len(undelivered)} "
              "(the requester was NOT told — see F2)")
    return EXIT_OK


# RCA #7: dispatch()/dispatch3() collapse "definitely permanent" and "maybe
# transient" into the same False/UNDETERMINED result -- dispatch3()'s own
# docstring says a failure "could mean a transient network blip just as
# easily as a permanent rejection." There is no structural signal in this
# codebase that tells the two apart on a single attempt (Reporter.to_requester
# treats FAIL and UNDETERMINED identically too). Consecutive failed sweeps is
# therefore the only available proxy: it survives any single blip (each sweep
# run is a separate, time-spaced retry opportunity) while still bounding the
# damage a permanently-bad chat id can do. 5 gives a stale/deleted chat id
# five independent chances to prove itself transient before it is quarantined.
MAX_DELIVERY_ATTEMPTS = 5


def cmd_sweep_undeliverable(args) -> int:
    """Retry every queued undeliverable message, oldest first. Takes the run lock.

    A message that still fails after MAX_DELIVERY_ATTEMPTS tries is moved to
    state["dead_letter"] instead of being re-queued forever (RCA #7) -- it is
    quarantined, not silently dropped: the record stays in state.json with the
    reason and timestamp, and a DEAD-LETTERED line is printed so an operator
    scanning sweep output (or state["dead_letter"] via --status/--json) can
    find it. A message that succeeds on any attempt before the cap is
    delivered normally regardless of its attempt count.
    """
    run_dir = args.run_dir.expanduser().resolve()
    with RunLock(run_dir):
        store = StateStore(run_dir)
        state = store.load()
        undeliverable = state.get("undeliverable", [])
        if not undeliverable:
            print("0 queued, 0 delivered, 0 still undeliverable, 0 dead-lettered")
            return EXIT_OK
        delivered = 0
        dead_lettered = 0
        remaining = []
        dead_letter = state.setdefault("dead_letter", [])
        for msg in undeliverable:
            chat_id = msg.get("chat_id", "")
            kind = msg.get("kind", "")
            message = msg.get("message", "")
            attempts = msg.get("attempts", 0) + 1
            # U069: route through the single shared report.dispatch() --
            # do not re-derive a subprocess.run(cmd, shell=True, ...) call
            # here. A hand-rolled third copy of this logic (independent of
            # report.py's dispatch() and Reporter._dispatch()) is exactly
            # the drift U069's closure exists to prevent.
            ok = bool(chat_id and kind) and dispatch(chat_id, kind, message)
            if ok:
                delivered += 1
                sent = state.setdefault("sent", {})
                prior = sent.get(kind)
                if not isinstance(prior, dict):
                    sent[kind] = {"count": 0, "first_at": prior, "last_at": prior}
                rec = sent[kind]
                rec["count"] = rec.get("count", 0) + 1
                rec["first_at"] = rec["first_at"] or utcnow()
                rec["last_at"] = utcnow()
            elif attempts >= MAX_DELIVERY_ATTEMPTS:
                msg["attempts"] = attempts
                msg["last_attempt_at"] = utcnow()
                msg["dead_lettered_at"] = utcnow()
                msg["dead_letter_reason"] = (
                    f"undeliverable after {attempts} attempts "
                    f"(cap {MAX_DELIVERY_ATTEMPTS}); chat_id={chat_id!r} kind={kind!r}"
                )
                dead_letter.append(msg)
                dead_lettered += 1
                print(f"DEAD-LETTERED: {kind!r} to chat_id={chat_id!r} after "
                      f"{attempts} attempts (cap {MAX_DELIVERY_ATTEMPTS}) -- "
                      "quarantined in state['dead_letter'], will not be retried again")
            else:
                msg["attempts"] = attempts
                msg["last_attempt_at"] = utcnow()
                remaining.append(msg)
        total = len(undeliverable)
        still = len(remaining)
        state["undeliverable"] = remaining
        store.save(state)
        print(f"{total} queued, {delivered} delivered, {still} still undeliverable, "
              f"{dead_lettered} dead-lettered")
        return EXIT_OK if still == 0 and dead_lettered == 0 else 1


def cmd_capacity(args) -> int:
    """WORK-ITEM-12: run the 9Router capacity probe and print the report.

    Read-only measurement of the harness settings and the local process table.
    Never simulated. Prints the probe report to stdout; the machine-greppable
    JSON block ships inside it (probe_mode / dispatchable / available)."""
    from . import capacity
    result = capacity.probe()
    print(capacity.format_report(result), flush=True)
    return EXIT_OK


def cmd_workingset(args, scripts_dir: Path) -> int:
    """FIX-20 gate: measure phase working sets against the context-window cap.

    With no phase argument, measures every manifest phase. Prints one JSON
    report per phase. Exit 0 when every measured phase fits one context
    window; exit EXIT_GATE_BLOCKED (3) when any phase's estimated token count
    exceeds the cap. Reading a run dir; never mutates state."""
    from .workingset import measure_all, measure_workingset, list_checkpoints
    run_dir = args.run_dir.expanduser().resolve()
    manifest = None
    store = StateStore(run_dir)
    state = {}
    if store.exists():
        state = store.load()
        mp = state.get("manifest_path")
        if mp and Path(mp).is_file():
            manifest = Manifest(Path(mp))

    results = []
    if args.workingset == "__all__":
        results = measure_all(run_dir, manifest)
    else:
        results = [measure_workingset(run_dir, args.workingset, manifest)]

    checkpoints = list_checkpoints(run_dir)
    overview = {
        "mode": "all" if args.workingset == "__all__" else args.workingset,
        "run_dir": str(run_dir),
        "phases_measured": len(results),
        "context_window_cap": results[0]["context_window_cap"] if results else None,
        "phases_fit": sum(1 for r in results if r["fits"]),
        "phases_over": sum(1 for r in results if not r["fits"]),
        "disk_checkpoints": checkpoints,
        "measurements": results,
    }
    print(json.dumps(overview, indent=2))
    for r in results:
        if not r["fits"]:
            print(f"AF-WORKINGSET-OVER: phase {r['phase_id']} estimated "
                  f"{r['estimated_tokens']} tokens, cap {r['context_window_cap']} "
                  f"({r['tokens_pct_of_cap'] * 100:.1f}% of window)", file=sys.stderr)
    return EXIT_OK if all(r["fits"] for r in results) else EXIT_GATE_BLOCKED


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


def _scan_roots_from_args(args: Any) -> List[Path]:
    """Resolve the effective scan-root list (run-root-agnostic, 2026-08-27).

    --scan-root may be passed multiple times, and each value may itself pack
    several roots separated by the OS pathsep (':' on macOS/Linux). When no
    --scan-root is given at all, PRESENTATION_SCAN_ROOTS + the department-tree
    default (default_scan_roots) applies. Order preserved, duplicates dropped."""
    roots: List[Path] = []
    sep = os.pathsep
    for arg in (getattr(args, "scan_root", None) or []):
        for piece in str(arg).split(sep):
            piece = piece.strip()
            if piece:
                roots.append(Path(piece).expanduser())
    seen: set = set()
    ordered: List[Path] = []
    for r in roots:
        try:
            key = r.expanduser().resolve()
        except OSError:
            key = r
        if key in seen:
            continue
        seen.add(key)
        ordered.append(r)
    return ordered


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    scripts_dir = Path(__file__).resolve().parent.parent

    if args.diagnose_only and not args.resume:
        die(EXIT_USAGE, "--diagnose-only only makes sense with --resume "
                        "(it modifies --resume, it is not its own mode)")

    if args.watchdog:
        cli_roots = _scan_roots_from_args(args)
        roots = cli_roots or (
            [args.run_dir] if args.run_dir else default_scan_roots()
        )
        if not roots:
            die(EXIT_USAGE, "--watchdog needs --scan-root")
        if getattr(args, 'grace', 1.5) <= 0:
            die(EXIT_USAGE, "--grace must be > 0")
        sd = getattr(args, 'scan_depth', 3)
        if sd < 1:
            die(EXIT_USAGE, "--scan-depth must be >= 1")
        return _run_watchdog(
            [r.expanduser().resolve() for r in roots],
            grace_multiplier=getattr(args, 'grace', 1.5),
            scan_depth=sd,
            enforce=getattr(args, 'enforce', False),
        )

    if args.reconcile_board:
        cli_roots = _scan_roots_from_args(args)
        if not cli_roots:
            die(EXIT_USAGE, "--reconcile-board needs --scan-root")
        sd = args.scan_depth if hasattr(args, 'scan_depth') else 3
        first, extra = cli_roots[0], cli_roots[1:]
        return reconcile_sweep(
            first.expanduser().resolve(),
            scan_depth=sd,
            apply=args.apply,
            max_age_hours=args.max_age_hours,
            extra_scan_roots=[r.expanduser().resolve() for r in extra],
        )

    if args.apply and not args.reconcile_board:
        die(EXIT_USAGE, "--apply is only meaningful with --reconcile-board")

    # --capacity needs no run-dir: it is a read-only probe of the harness.
    if args.capacity:
        return cmd_capacity(args)

    if not args.run_dir:
        die(EXIT_USAGE, "--run-dir is required")
    run_dir = args.run_dir.expanduser().resolve()

    if args.new:
        return cmd_new(args, scripts_dir)
    if args.capacity:
        return cmd_capacity(args)
    if args.workingset is not None:
        return cmd_workingset(args, scripts_dir)
    if args.status:
        return cmd_status(args)
    if args.sweep_undeliverable:
        return cmd_sweep_undeliverable(args)

    with RunLock(run_dir):
        store = StateStore(run_dir)
        state = store.load()
        manifest_path = Path(state.get("manifest_path") or
                             resolve_manifest(args.manifest, run_dir, scripts_dir))
        if not manifest_path.is_file():
            die(EXIT_MANIFEST_MISMATCH, f"pinned manifest {manifest_path} is gone")
        manifest = Manifest(manifest_path)
        manifest.verify_pin(state.get("manifest_sha256", ""))

        engine = Engine(run_dir, manifest, store, state, dry_run=args.dry_run)

        # U024 — blended-persona governance banner, printed once at engine start
        # so every run states on the record which persona governs its output.
        # Wrapped: the banner is informational, and a persona-config problem must
        # never stop a client's job from starting.
        try:
            print(persona.governance_banner(), flush=True)
        except Exception as exc:
            print(f"[persona] governance banner unavailable: {exc}", file=sys.stderr, flush=True)

        if args.close:
            return engine.close()
        if args.resume:
            # Print the diagnosis BEFORE anything is cleared. state.pop("blocked", None)
            # used to run first, so the phase and reason the engine parked on were gone by
            # the time the operator saw output (B7's con; U017).
            lines = diagnose.describe_park(state, run_dir)
            if lines:
                print("\n".join(lines), file=sys.stderr, flush=True)
            else:
                print(f"This job is not parked (terminal={state.get('terminal')!r}). "
                      "Resuming will re-enter at the first unfinished phase.",
                      file=sys.stderr, flush=True)
            if args.diagnose_only:
                return EXIT_OK
            # Preserve the diagnosis BEFORE clearing it. Popping `blocked` without keeping
            # a copy destroys the only record of why this job parked (B7's con).
            prior = state.pop("blocked", None)
            if prior:
                state.setdefault("resume_history", []).append(
                    {"at": utcnow(), "cleared_blocked": prior})
            state["terminal"] = None
            bad_count = 0
            total_banked = 0
            for ps in state.get("phases", []):
                if ps.get("status") == "done":
                    total_banked += len(ps.get("artifacts") or [])
                if ps.get("banked_invalid"):
                    bad_count += len(ps["banked_invalid"])
            state["resume_revalidation"] = {"checked": total_banked, "failed": bad_count}
            if bad_count:
                print(f"resume: {bad_count} banked artifact(s) failed re-validation "
                      f"-- those phases will re-run", flush=True)
            else:
                print("resume: all banked artifacts re-validated", flush=True)
            store.save(state)
            engine.report.event(
                "job.resume",
                "resuming from checkpoint; banked artifacts reused" +
                (f"; cleared block at {prior.get('phase')}: {prior.get('reason')}" if prior else ""))

        # F07 -- auto-spawn the Work-Order Dispatcher for this run, CONCURRENTLY
        # with the engine (spawned before engine.run(), never after -- see the
        # design note above _spawn_dispatcher_if_available). --dry-run never
        # executes agent phases for real (no work orders are serviced, none are
        # even worth spawning a dispatcher over), so it is excluded here.
        dispatcher_proc = None
        if not args.dry_run:
            dispatcher_proc = _spawn_dispatcher_if_available(
                run_dir, scripts_dir, disabled=args.no_auto_dispatch)
        try:
            return engine.run(only=args.phase, until=args.until)
        finally:
            _stop_auto_dispatcher(run_dir, dispatcher_proc)
