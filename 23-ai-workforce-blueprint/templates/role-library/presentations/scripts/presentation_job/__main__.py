from __future__ import annotations

import argparse
import json
import os
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
from .report import flush_undeliverable
from .watchdog import watchdog as _run_watchdog
from .board import BoardMirror
from .sweep import reconcile_sweep
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
    p.add_argument("--scan-root", type=Path, help="root to scan for --watchdog / --reconcile-board")
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
        "parked": [],
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
    run_dir = args.run_dir.expanduser().resolve()
    store = StateStore(run_dir)
    st = store.load()
    # Opportunistic, non-blocking retry drain -- see report.flush_undeliverable's
    # docstring. --status is an ordinary, pre-existing, read-oriented command;
    # piggybacking the drain on it (instead of requiring a dedicated flag or a
    # cron entry invented for this fix) is what lets a job that has already
    # gone terminal heal the next time ANYONE checks on it, with no human
    # action beyond normal operation. fatal=False: if a live engine already
    # holds the run lock, this is skipped rather than killing --status, which
    # must keep working as a pure read regardless of what else is running.
    if st.get("undeliverable"):
        lock = RunLock(run_dir, fatal=False)
        with lock:
            if lock.acquired:
                st = store.load()  # re-read under the lock: don't clobber a concurrent writer
                flush_undeliverable(st, store)
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
              "(the requester was NOT told — see F2; retried automatically on backoff)")
    parked = st.get("parked")
    if parked:
        print(f"PARKED (poisoned) messages: {len(parked)} "
              "(retries stopped — content preserved, never told to the requester)")
    return EXIT_OK


def cmd_sweep_undeliverable(args) -> int:
    """Force an immediate check of the queue. Takes the run lock.

    NOT load-bearing for recovery -- see report.flush_undeliverable's
    docstring. This exists purely as an operator convenience (an explicit
    "check right now" instead of waiting for the next automatic trigger);
    normal recovery never depends on a human or a cron ever calling this.
    It shares flush_undeliverable() with every automatic caller, so it obeys
    the identical next_attempt_at backoff gate (a cron calling this every
    minute still cannot hot-loop the transport) and never touches
    state["parked"] (a cron calling this cannot resurrect a poisoned
    message) -- this is what closes the second failed attempt at this fix
    ("putting the flag in a cron line recreated unbounded retry")."""
    run_dir = args.run_dir.expanduser().resolve()
    with RunLock(run_dir):
        store = StateStore(run_dir)
        state = store.load()
        total = len(state.get("undeliverable") or [])
        if total == 0:
            print("0 queued, 0 delivered, 0 still undeliverable")
            return EXIT_OK
        stats = flush_undeliverable(state, store)
        suffix = f", {stats['parked']} newly parked (poisoned)" if stats["parked"] else ""
        print(f"{total} queued, {stats['delivered']} delivered, "
              f"{stats['still_queued']} still undeliverable{suffix}")
        return EXIT_OK if stats["still_queued"] == 0 else 1


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


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    scripts_dir = Path(__file__).resolve().parent.parent

    if args.diagnose_only and not args.resume:
        die(EXIT_USAGE, "--diagnose-only only makes sense with --resume "
                        "(it modifies --resume, it is not its own mode)")

    if args.watchdog:
        root = (args.scan_root or args.run_dir)
        if not root:
            die(EXIT_USAGE, "--watchdog needs --scan-root")
        if getattr(args, 'grace', 1.5) <= 0:
            die(EXIT_USAGE, "--grace must be > 0")
        sd = getattr(args, 'scan_depth', 3)
        if sd < 1:
            die(EXIT_USAGE, "--scan-depth must be >= 1")
        return _run_watchdog(
            root.expanduser().resolve(),
            grace_multiplier=getattr(args, 'grace', 1.5),
            scan_depth=sd,
            enforce=getattr(args, 'enforce', False),
        )

    if args.reconcile_board:
        if not args.scan_root:
            die(EXIT_USAGE, "--reconcile-board needs --scan-root")
        sd = args.scan_depth if hasattr(args, 'scan_depth') else 3
        return reconcile_sweep(
            args.scan_root.expanduser().resolve(),
            scan_depth=sd,
            apply=args.apply,
            max_age_hours=args.max_age_hours,
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
        return engine.run(only=args.phase, until=args.until)
