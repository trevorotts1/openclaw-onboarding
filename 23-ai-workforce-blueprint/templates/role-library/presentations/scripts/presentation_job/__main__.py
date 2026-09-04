from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .state import (
    StateStore, RunLock, utcnow, sha256_text, _read_json,
    die, EXIT_OK, EXIT_USAGE, EXIT_MANIFEST_MISMATCH,
    EXIT_STATE_CORRUPT, EXIT_LOCK_HELD, STATE_SCHEMA_VERSION,
    EXIT_GATE_BLOCKED,
)
from . import lease as lease_mod
from .lease import DEFAULT_TTL_S as LEASE_TTL_S, HEARTBEAT_INTERVAL_S as LEASE_HEARTBEAT_S
from .manifest import Manifest, ManifestInvalid, resolve_manifest
from .phases import Engine
from .report import dispatch
# FIX 64 (one notification transport): the scheduled undeliverable-retry pass a
# watchdog tick can run (--sweep-undeliverable-roots) resolves the SAME root
# list every other scanning pass uses, so it needs scan_roots' resolver/report
# helpers, sweep.py's run-dir finder, and the sweep exit code it returns.
from .scan_roots import format_roots_report, resolve_scan_roots, split_primary
from .watchdog import watchdog as _run_watchdog
from .supervisor import supervise as _run_supervise, DEFAULT_MAX_RESTARTS, DEFAULT_BACKOFF_SECONDS
from .board import BoardMirror
from .sweep import reconcile_sweep
from .sweep import _find_run_dirs_multi  # FIX 64: shared run-dir finder for the roots sweep
from .state import EXIT_SWEEP_HAD_FAILURES
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
    m.add_argument("--run", action="store_true",
                   help="run the phase loop. FIX 22: like --resume, a --run on a parked job "
                        "clears terminal/blocked first, so the door's --run invocation "
                        "continues a parked run instead of leaving it terminal-blocked "
                        "(the dispatcher exits on a set terminal and every agent phase "
                        "blocks after its full budget).")
    m.add_argument("--resume", action="store_true",
                   help="resume a parked job from checkpoint; prints why it parked first. "
                        "With --phase, re-runs only that phase and does NOT evaluate gates, "
                        "so it cannot clear a job parked on a gate failure.")
    m.add_argument("--status", action="store_true", help="print job status")
    m.add_argument("--repin", action="store_true",
                   help="FIX 20: re-pin a parked job to the CURRENT manifest. Recomputes the "
                        "plan, diffs phase ids, marks removed phases obsolete and new phases "
                        "pending, records the old and new manifest sha256 in state "
                        "(manifest.repin history + manifest_sha256_prev), so --resume can "
                        "continue under the bumped manifest instead of dying with exit 7. "
                        "Mutually exclusive with every other mode.")
    m.add_argument("--close", action="store_true", help="evaluate gates and close")
    m.add_argument("--watchdog", action="store_true", help="scan for stalled jobs")
    m.add_argument("--reconcile-board", action="store_true",
                   help="scan --scan-root for jobs whose board card is missing or behind; "
                        "reports only unless --apply is given")
    m.add_argument("--sweep-undeliverable", action="store_true",
                   help="retry every queued undeliverable message for --run-dir, oldest first")
    m.add_argument("--sweep-undeliverable-roots", action="store_true",
                   help="FIX 64: retry every queued undeliverable message across ALL "
                        "configured scan roots (--scan-root + PRESENTATION_SCAN_ROOTS + "
                        "config file), one run dir at a time; the --sweep-undeliverable "
                        "pass a watchdog tick can run without knowing any --run-dir")
    m.add_argument("--workingset", nargs="?", const="__all__", default=None, metavar="PHASE",
                   help="FIX-20: measure one phase's working-set token count (or all phases) and "
                        "report fit against the context-window cap. Exit 0 if every measured phase "
                        "fits one window, exit 3 (EXIT_GATE_BLOCKED) if any exceeds it.")
    m.add_argument("--capacity", action="store_true",
                   help="WORK-ITEM-12: run the 9Router capacity probe and print the report; "
                        "exit 0. Read-only measurement, never simulated.")
    m.add_argument("--plan", action="store_true",
                   help="MASTER Part 8 FIX 8: print the wave-scheduled execution plan (the "
                        "artifact DAG the engine runs: wave one is intake + research only, "
                        "P8.2-GUIDE never before P4-COPY) and exit. Read-only — never runs "
                        "a phase, never takes the run lease. Manifest resolution mirrors "
                        "--status/--run: the job's pinned manifest when state.json exists "
                        "in --run-dir, else --manifest, else resolve_manifest()'s search.")
    p.add_argument("--run-dir", type=Path, help="the job's run directory")
    p.add_argument("--intake", type=Path, help="intake JSON for --new")
    p.add_argument("--manifest", help="explicit PIPELINE-MANIFEST.json path")
    p.add_argument("--phase", help="run exactly one phase")
    p.add_argument("--until", help="run through this phase then stop")
    p.add_argument("--scan-root", type=Path, help="PRIMARY root to scan for "
                   "--watchdog / --reconcile-board; may be os.pathsep-packed "
                   "(':'-joined, as the launchd plist passes SCAN_ROOT); "
                   "additional roots come from --scan-root-extra, "
                   "PRESENTATION_SCAN_ROOTS, and the scan-roots config file "
                   "(see presentation_job/scan_roots.py)")
    # 2026-08-27 scan-roots fix: a single --scan-root was the blind spot. Extra
    # roots are CLI-repeatable, env (os.pathsep-separated), and config-file
    # driven; resolution and the unreadable-root => UNDETERMINED doctrine live
    # in scan_roots.py, shared with run_discovery.py.
    p.add_argument("--scan-root-extra", type=Path, action="append", default=None,
                   dest="scan_root_extras", metavar="PATH",
                   help="additional scan root; repeatable")
    p.add_argument("--roots-config", type=Path, default=None,
                   help="config file listing additional roots, one path per line "
                        "(default: <department>/config/scan-roots.conf, "
                        "overridable with SCAN_ROOTS_CONFIG)")
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
    # Worker-liveness supervision (supervisor.py): the watchdog answers "is the
    # HEARTBEAT stale?" -- supervisor answers "is the PROCESS that writes it
    # alive?", detects a dead worker behind an active run, and restarts it with
    # a bounded, backed-off budget (report-only without --apply, exactly like
    # reconcile-board).
    m.add_argument("--supervise", action="store_true",
                   help="scan --scan-root for active runs whose worker process "
                        "has died; report-only unless --apply is also given")
    p.add_argument("--max-restarts", type=int, default=None,
                   help="with --supervise: restart budget per run before the "
                        "supervisor stops and raises an alarm (default: "
                        "supervisor.DEFAULT_MAX_RESTARTS)")
    p.add_argument("--supervisor-backoff", type=int, default=None,
                   help="with --supervise: base seconds of exponential backoff "
                        "between restart attempts (default: "
                        "supervisor.DEFAULT_BACKOFF_SECONDS)")
    p.add_argument("--max-idle-hours", type=float, default=72.0,
                   help="with --supervise: a dead run whose state.json is older "
                        "than this is reported but never restarted (default 72, "
                        "the same ceiling reconcile-board uses)")
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


# ---------------------------------------------------------------------------
# FIX 20 — Manifest bump must not brick in-flight runs.
#   `presentation_job.py --repin --run-dir <run>`: recompute the plan against
#   the CURRENT manifest, diff phase ids, mark removed phases obsolete and new
#   phases pending, and record old and new shas. `--resume` then continues.
#   SOURCE: [R1 §E] [R4 §G] — Master Part 8 Fix 20. W05-B4, delivered as a
#   patch for W10a's --repin wiring.
# ---------------------------------------------------------------------------
def cmd_repin(args, scripts_dir: Path) -> int:
    """Re-pin a parked job to the current manifest (FIX 20).

    Exit 7 (EXIT_MANIFEST_MISMATCH) from verify_pin() is the ONLY thing this
    cures: the manifest changed under a running job and every pinned run is
    stranded. Repin is explicit operator action, never a silent fallback.
    """
    run_dir = args.run_dir.expanduser().resolve()
    store = StateStore(run_dir)
    if not store.exists():
        die(EXIT_USAGE, f"no job state in {run_dir} — nothing to repin (run --new first)")
    state = store.load()
    old_sha = str(state.get("manifest_sha256") or "")
    old_ver = state.get("manifest_version")

    manifest_path = Path(state.get("manifest_path") or
                         resolve_manifest(args.manifest, run_dir, scripts_dir))
    # --manifest explicitly overrides the pinned path; otherwise repin in place.
    if args.manifest:
        manifest_path = Path(args.manifest).expanduser().resolve()
        if not manifest_path.is_file():
            die(EXIT_USAGE, f"--manifest {manifest_path} does not exist")
    if not manifest_path.is_file():
        die(EXIT_MANIFEST_MISMATCH, f"pinned manifest {manifest_path} is gone; "
                                    "pass --manifest to repin against a copy")

    new_manifest = Manifest(manifest_path)
    new_sha = new_manifest.sha256
    if old_sha and old_sha == new_sha:
        print(f"repin: manifest unchanged (sha {new_sha[:12]}); nothing to do")
        return EXIT_OK

    # Phase-id diff: OLD side from the state's own phase rows (the run's real
    # progress, not the old manifest, which may no longer be readable), NEW
    # side from the manifest just loaded.
    old_ids = {ps.get("id") for ps in state.get("phases", []) if ps.get("id")}
    new_ids = {p.id for p in new_manifest.phases}
    removed = sorted(old_ids - new_ids)
    added = sorted(new_ids - old_ids)

    changed = 0
    for ps in state.get("phases", []):
        if ps.get("id") in removed and ps.get("status") != "obsolete":
            ps["status"] = "obsolete"
            ps["obsolete_reason"] = "removed from manifest at repin (FIX 20)"
            changed += 1
    for pid in added:
        state.setdefault("phases", []).append(
            {"id": pid, "status": "pending", "artifacts": [], "sha256": {},
             "attempts": 0, "heal_events": [], "attested_at": None,
             "repin_added": True})
        changed += 1

    # Record BOTH shas: manifest_sha256_prev keeps the old pin discoverable,
    # manifest.repin history rows name old and new together, and the live pin
    # moves forward so verify_pin() lets --resume through.
    state["manifest_sha256_prev"] = old_sha
    state["manifest_version_prev"] = old_ver
    state["manifest_sha256"] = new_sha
    state["manifest_version"] = new_manifest.version
    state["manifest_path"] = str(manifest_path)
    hist = state.setdefault("manifest_repin_history", [])
    hist.append({
        "at": utcnow(),
        "old_sha256": old_sha,
        "new_sha256": new_sha,
        "old_manifest_version": old_ver,
        "new_manifest_version": new_manifest.version,
        "phases_removed": removed,
        "phases_added": added,
    })
    # An obsolete phase can never satisfy close()'s attestation walk, so the
    # terminal/blocked state from the old plan must reset — --resume already
    # clears "blocked"; mark the plan-version bump so the operator sees why.
    state["repin_applied"] = True
    store.save(state)

    print(f"repin: manifest v{old_ver} @ {old_sha[:12] if old_sha else '?'} "
          f"-> v{new_manifest.version} @ {new_sha[:12]}")
    print(f"  removed phases marked obsolete: {len(removed)}"
          + (f" {removed}" if removed else ""))
    print(f"  new phases added pending:       {len(added)}"
          + (f" {added}" if added else ""))
    print("  resume with: presentation_job.py --resume --run-dir "
          f"{run_dir}")
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


def cmd_sweep_undeliverable_roots(args) -> int:
    """FIX 64 (MASTER Part 8) -- --sweep-undeliverable without knowing a run dir.

    cmd_sweep_undeliverable is per-run: it takes --run-dir and its lock, which
    is exactly right for an engine resuming its own job and exactly wrong for
    a watchdog tick, which knows only --scan-root. Before this command, the
    undeliverable retry loop report.py queues into state["undeliverable"]
    (FAULT-14) had NO scheduled driver: a message queued while the transport
    was down stayed queued until a human ran the sweep by hand against a
    run dir they had to know. This is the scheduled driver: it resolves the
    same root list every other scanning pass uses (SCAN_ROOT + extras +
    PRESENTATION_SCAN_ROOTS + the config file, via resolve_scan_roots), finds
    every run dir holding a non-empty undeliverable queue, and runs the SAME
    per-run cmd_sweep_undeliverable logic against each -- the run lock, the
    dead-letter cap, the sent stamping, all of it shared by delegation, not
    re-derived (U069's one-implementation rule applies to behavior too).

    Epistemics and fail-softness:
      - A run dir whose lock is held by a live engine is SKIPPED, never
        contended: die(EXIT_LOCK_HELD) from cmd_sweep_undeliverable is caught
        (it is SystemExit) and counted as skipped -- a busy job will be swept
        on a later tick, and an undeliverable queue is eventually-consistent
        state, not an emergency.
      - A run dir that raises anything else is reported and the sweep moves
        on (same fail-soft shape as reconcile_sweep) -- one bad run dir never
        ends the pass.
      - Every run dir's per-run verdict line is printed (grep-able, same
        format as the per-run sweep), plus a ROOTS summary line at the end:
        "sweep-undeliverable-roots: N run dirs, D swept, S skipped
        (locked), F failed -- Q queued messages remaining".
      - Exit 0 when nothing failed; EXIT_SWEEP_HAD_FAILURES (11) when >=1 run
        dir failed unexpectedly (same shape as reconcile_sweep). A sweep that
        found zero runs and zero queued messages is exit 0 -- between jobs is
        a normal, expected state (the EXIT_SWEEP_NO_RUNS UNDETERMINED doctrine
        is for a pass that classifies run dirs; a retry pass with nothing to
        retry simply succeeded at retrying nothing).
    """
    root = args.scan_root if args.scan_root else None
    primary_roots = split_primary(root) if root is not None else [Path(".")]
    if root is not None and not primary_roots:
        die(EXIT_USAGE, "--sweep-undeliverable-roots needs --scan-root")
    roots = resolve_scan_roots(
        primary=primary_roots[0] if primary_roots else None,
        extra=tuple(primary_roots[1:]) + tuple(getattr(args, "scan_root_extras", None) or ()),
        config_path=getattr(args, "roots_config", None),
    )
    print(format_roots_report(roots, "sweep-undeliverable-roots"), flush=True)

    run_dirs = _find_run_dirs_multi(roots, getattr(args, "scan_depth", 3) or 3)
    total_runs = len(run_dirs)
    swept = skipped = failed = 0
    queued_remaining = 0
    saw_queue = 0
    for run_dir in run_dirs:
        try:
            # Cheap pre-check under no lock: state.json may not even exist
            # (a partially materialised dir) or may be unreadable. Reading it
            # here keeps the common no-op case lock-free.
            st = _read_json(run_dir / "state.json")
            if not isinstance(st, dict):
                continue
            if not st.get("undeliverable"):
                continue
        except OSError:
            # UNREADABLE state is UNDETERMINED, not "nothing queued" -- but
            # the per-run sweep below would report the same fact loudly, so
            # fall through and let it speak.
            st = {"undeliverable": [{"at": utcnow(), "kind": "unknown",
                                     "message": "unreadable state.json",
                                     "chat_id": "", "attempts": 0,
                                     "outcome": "PRECHECK_UNREADABLE"}]}
        saw_queue += 1
        before = len(st.get("undeliverable") or [])
        try:
            # Delegate to the SAME per-run sweep -- same lock, same cap, same
            # output format. args.run_dir is what cmd_sweep_undeliverable
            # reads; build a shallow copy rather than mutate the parser's
            # namespace a caller might be holding.
            per_run_args = _ShallowArgsCopy(args, run_dir=run_dir)
            rc = cmd_sweep_undeliverable(per_run_args)
        except SystemExit as exc:
            # RunLock dies with EXIT_LOCK_HELD on contention -- a live engine
            # owns this run right now. Skip, count, move on: never compete
            # for a lock a worker is actively holding, never abort the pass.
            try:
                code = int(getattr(exc, "code", 0) or 0)
            except (TypeError, ValueError):
                code = 0
            if code == EXIT_LOCK_HELD:
                skipped += 1
                print(f"sweep-undeliverable-roots: skipped (lock held) {run_dir}",
                      flush=True)
                continue
            failed += 1
            print(f"sweep-undeliverable-roots: FAILED (exit {exc.code}) {run_dir}",
                  flush=True)
            continue
        except OSError as exc:
            failed += 1
            print(f"sweep-undeliverable-roots: FAILED ({exc}) {run_dir}", flush=True)
            continue
        swept += 1
        try:
            after_st = _read_json(run_dir / "state.json")
            after_q = len((after_st or {}).get("undeliverable") or []) \
                if isinstance(after_st, dict) else 0
        except OSError:
            after_q = 0
        queued_remaining += after_q
        if rc != EXIT_OK or before:
            print(f"sweep-undeliverable-roots: run {run_dir} rc={rc} "
                  f"queued {before} -> {after_q}", flush=True)
    print(f"sweep-undeliverable-roots: {total_runs} run dirs, {swept} swept, "
          f"{skipped} skipped (locked), {failed} failed -- "
          f"{queued_remaining} queued messages remaining across {saw_queue} "
          f"run dirs seen", flush=True)
    return EXIT_OK if failed == 0 else EXIT_SWEEP_HAD_FAILURES


class _ShallowArgsCopy:
    """argparse.Namespace stand-in for per-run delegation: copies every
    attribute from the parsed namespace except the ones being overridden, so
    cmd_sweep_undeliverable's args.run_dir is the run dir THIS root-walk is
    currently sweeping while every other flag keeps its parsed value."""

    def __init__(self, source: Any, **overrides: Any) -> None:
        self.__dict__.update({k: v for k, v in source.__dict__.items()})
        self.__dict__.update(overrides)


def cmd_capacity(args) -> int:
    """WORK-ITEM-12: run the 9Router capacity probe and print the report.

    Read-only measurement of the harness settings and the local process table.
    Never simulated. Prints the probe report to stdout; the machine-greppable
    JSON block ships inside it (probe_mode / dispatchable / available)."""
    from . import capacity
    result = capacity.probe()
    print(capacity.format_report(result), flush=True)
    return EXIT_OK


def cmd_plan(args, scripts_dir: Path) -> int:
    """MASTER Part 8 FIX 8: print the wave-scheduled execution plan, exit 0.

    Read-only: resolves the manifest exactly the way --run does (the job's
    PINNED manifest when --run-dir holds a state.json naming it, else
    --manifest, else resolve_manifest()'s search — never a walk-up guess),
    validates it through Manifest.load (a consumed artifact with no producer
    that is not an intake file raises ManifestInvalid naming it), then builds
    the SAME plan the engine runs — build_execution_plan over the artifact
    DAG (edge u→v iff produces(u) ∩ consumes(v) ≠ ∅; manifest `order` only
    breaks ties intra-wave) with the REAL capacity.probe() result. The width
    is measured, never a constant: a probe that cannot produce a number
    refuses with AF-CAPACITY-UNMEASURED and EXIT_GATE_BLOCKED exactly like
    execution_plan.main().

    A fresh run dir (the QC FIX 8 proof shape — `--plan --run-dir <dir>` on a
    from-scratch deck with no state yet) resolves via --manifest /
    resolve_manifest and prints the from-scratch plan: wave 1 = intake +
    research only (P-0.5-RESEARCH, P0A-INTAKE, P-SP-CLAIM), P8.2-GUIDE in a
    strictly later wave than P4-COPY. Never writes state, never takes the
    run lease, never creates the run dir.

    Routing parity (MASTER Part 8 FIX 8 proof: "wave one = intake and research
    only"): on a dir with no state/intake yet — the from-scratch proof shape —
    the plan applies the SAME converter routing the engine applies
    (phases.py:1796-1804): converter_path phases (P-CONVERTER, "Content-first
    path only") are routed around, because the intake driver's default
    creation_mode for a not-yet-interviewed deck is from_scratch
    (deck-intake-driver.py:110,134) and P-CONVERTER does no work on such a
    deck. A dir whose state/intake positively declares a content-first
    creation_mode keeps P-CONVERTER, mirroring the engine's fail-open rule.
    """
    from . import capacity
    from .execution_plan import (CapacityUnmeasured, autofail_payload,
                                 build_execution_plan, refusal_message)

    run_dir = args.run_dir.expanduser().resolve() if args.run_dir else None
    manifest_path: Optional[Path] = None
    creation_mode: Optional[str] = None
    if run_dir is not None:
        store = StateStore(run_dir)
        if store.exists():
            pinned = store.load().get("manifest_path")
            if pinned:
                mp = Path(pinned)
                if not mp.is_file():
                    die(EXIT_MANIFEST_MISMATCH, f"pinned manifest {mp} is gone")
                manifest_path = mp
        # Same best-effort read the engine's _deck_creation_mode does
        # (phases.py:486-505): None on absence/parse failure -- a routing
        # decision that depends on this never skips a phase on missing
        # information, only on a positively-read confirmed mode.
        try:
            obj = json.loads(
                (run_dir / "working" / "copy" / "intake.json").read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                val = obj.get("creation_mode")
                if isinstance(val, str) and val:
                    creation_mode = val
        except Exception:  # noqa: BLE001
            creation_mode = None
    if manifest_path is None and args.manifest:
        mp = Path(args.manifest).expanduser().resolve()
        if not mp.is_file():
            die(EXIT_USAGE, f"--manifest {mp} does not exist")
        manifest_path = mp
    if manifest_path is None:
        if run_dir is None:
            die(EXIT_USAGE, "--plan needs --run-dir (or --manifest)")
        manifest_path = resolve_manifest(args.manifest, run_dir, scripts_dir)

    try:
        manifest = Manifest.load(manifest_path)   # ManifestInvalid names the dangling input
    except ManifestInvalid as exc:
        die(EXIT_MANIFEST_MISMATCH, f"--plan refuses this manifest: {exc}")
    probe = capacity.probe()
    try:
        plan = build_execution_plan(manifest_path, probe)
    except CapacityUnmeasured:
        print(f"CAPACITY AUTOFAIL: {refusal_message(probe)}", file=sys.stderr)
        print(json.dumps(autofail_payload(probe), indent=2), file=sys.stderr)
        return EXIT_GATE_BLOCKED

    # Converter routing (see docstring): a from-scratch deck routes
    # converter_path phases out of the plan. A fresh dir (no intake.json) IS
    # the from-scratch proof shape; an unknown mode would only arise for a
    # state-pinned run whose intake was deleted, and failing open (keeping the
    # phase) there matches the engine.
    if not (creation_mode and creation_mode in ("content_personal", "content_general")):
        plan["waves"] = [[pid for pid in wave
                          if not manifest.phase_or_none(pid).converter_path]
                         for wave in plan["waves"]]
        plan["waves"] = [wave for wave in plan["waves"] if wave]
    print(f"EXECUTION PLAN -- presentation_job (MASTER Part 8 FIX 8)")
    print(f"Manifest: {manifest_path} (v{manifest.version}, "
          f"{len(manifest.phases)} phases)")
    print(f"Capacity probe: {plan['capacity_probe_mode']} -- status "
          f"{plan.get('capacity_status')}, provider {plan.get('capacity_provider')}, "
          f"dispatchable {plan['dispatchable']}, available {plan['available']}")
    print(f"Execution plan: {len(plan['waves'])} waves")
    for i, wave in enumerate(plan["waves"], 1):
        print(f"  wave {i:>2}: " + ", ".join(wave))
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


# ---------------------------------------------------------------------------
# FIX 19 (MASTER Part 8) — reap orphans, children included.
#
# The QC probe: start a stubbed deck-12 run, wait for P4-PROMPT workers, kill
# the engine with SIGTERM, then require within 30 s that NO dispatcher,
# worker, or render child remains — and that a NEW engine on the same run dir
# spawns its own dispatcher (the old lock file did not block it).
#
# Three engine-side gaps closed here:
#
# 1. THE ENGINE IS ITS OWN SESSION LEADER. The engine process is spawned by
#    the launcher with start_new_session=True (launcher.py dispatch()), so
#    SIGTERM to the engine's process group reaches the engine, its
#    auto-spawned dispatcher, and every render child in one os.killpg. But a
#    SIGKILL (or a crash) leaves nothing to catch the stragglers — so the
#    engine also installs its own SIGTERM handler that raises a shutdown
#    event the finally-block honours before normal teardown, and the
#    scheduled process_reaper (presentation-watchdog.sh) backstops anything
#    that survives.
#
# 2. THE AUTO-SPAWNED DISPATCHER IS ITS OWN GROUP LEADER.
#    _spawn_dispatcher_if_available spawns with start_new_session=True so
#    _stop_auto_dispatcher can os.killpg the dispatcher AND its in-flight
#    wave workers, not just the watcher — the pre-FIX 19 proc.terminate()
#    killed only the watcher and orphaned the workers mid-wave, exactly the
#    survivors that kept rewriting intake.
#
# 3. THE AUTOSPAWN LOCK CANNOT BLOCK A NEW ENGINE. The lock previously
#    recorded {pid, started_at} and a live holder meant "not spawning" —
#    but a dispatcher from a PREVIOUS run id (different job on the same
#    reused run dir) is precisely the orphan this fix exists to reap. Now
#    the lock record carries run_id (the state.json job_id) and run_dir; a
#    live holder whose run_id differs from THIS run's job_id is killed
#    (whole process group, TERM then KILL) and its lock replaced, so a new
#    engine always spawns its own fresh dispatcher.
# ---------------------------------------------------------------------------

#: FIX 19: SIGTERM handler — flip the engine-shutdown flag. Installed in
#: main() for --run/--resume so a launcher stop_engine() SIGTERM (or an
#: operator's kill -TERM) is OBSERVED: the handler itself does nothing else
#: (no cleanup from a signal handler — the finally blocks own that), it only
#: raises the flag so the exit path can log it. SIGKILL remains unrecoverable
#: by design; that is what the scheduled reaper and stop_engine's killpg
#: escalation are for.
_ENGINE_SHUTDOWN_REQUESTED = False


def _install_engine_sigterm_handler() -> None:
    """FIX 19: record that this engine was asked to stop. Idempotent;
    main-thread only (signal.signal raises ValueError elsewhere).

    FIX 105: the handler ALSO raises the phases module's shutdown event (the
    sliced exec waits poll it) and killpgs every REGISTERED in-flight exec's
    own process group — the render batch spawned start_new_session=True sits
    OUTSIDE the engine's group, so the launcher's group-TERM never reaches it;
    without this the exec outlived the engine and kept writing stale renders.
    Signal-handler discipline holds: only these two asyncio-safe calls plus
    the flag write happen here; the sliced waiter does the kill join, and the
    handler's own group-KILL is a belt-and-braces reaper for execs whose
    waiter already exited."""
    global _ENGINE_SHUTDOWN_REQUESTED
    if threading.current_thread() is not threading.main_thread():
        return

    def _handler(signum, _frame):  # noqa: ANN001 -- signal handler signature
        global _ENGINE_SHUTDOWN_REQUESTED
        _ENGINE_SHUTDOWN_REQUESTED = True
        try:
            from . import phases as _ph
            _ph._ENGINE_SHUTDOWN_EVENT.set()
            _ph._kill_registered_execs(signal.SIGTERM)
            print(f"[engine {os.getpid()}] signal {signum} received -- shutdown "
                  f"requested; in-flight execs reaped; unwinding via the "
                  f"normal finally path", flush=True)
        except Exception:  # noqa: BLE001 -- the handler must never raise
            print(f"[engine {os.getpid()}] signal {signum} received -- shutdown "
                  f"requested; unwinding via the normal finally path", flush=True)

    try:
        signal.signal(signal.SIGTERM, _handler)
        signal.signal(signal.SIGINT, _handler)
    except (ValueError, OSError):
        pass


def _kill_process_group_best_effort(pid: int, sig: int) -> bool:
    """FIX 19: os.killpg(pid, sig) with a direct-pid fallback, then swallow
    every failure. The pid passed IS the group leader (every FIX 19 spawn is
    start_new_session=True); the fallback covers a recorded pid from an older
    spawn that was never a leader. Never raises — best-effort by contract."""
    try:
        os.killpg(pid, sig)
        return True
    except OSError:
        pass
    try:
        os.kill(pid, sig)
        return True
    except OSError:
        return False


def _auto_dispatch_lock_path(run_dir: Path) -> Path:
    return run_dir / "working" / "dispatcher-autospawn.lock"


def _read_autospawn_lock(lock_path: Path) -> Dict[str, Any]:
    """FIX 19: read the autospawn lock record defensively. Returns {} on any
    absence/parse failure — the caller treats an empty record as no holder."""
    try:
        rec = json.loads(lock_path.read_text(encoding="utf-8"))
        return rec if isinstance(rec, dict) else {}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def _auto_dispatch_disabled(disabled_flag: bool) -> bool:
    if disabled_flag:
        return True
    return os.environ.get("PRESENTATION_AUTO_DISPATCH", "1").strip().lower() in (
        "0", "false", "no", "off")

#: FIX 105: the module files a running dispatcher EXECUTES. Any of these whose
#: mtime postdates the running dispatcher's start time makes that dispatcher
#: stale — it is executing pre-patch code and must be replaced, never reused.
_DISPATCHER_MODULE_FILES = ("presentation_job/dispatcher.py",
                            "work_order_dispatcher.py")

def _dispatcher_modules_stale(lock_record: Dict[str, Any]) -> Tuple[bool, str]:
    """FIX 105 launcher staleness check. True (with a naming detail) when the
    live dispatcher described by `lock_record` started BEFORE the newest mtime
    of its own module files — i.e. a patch landed while it was running and it
    will keep the old code loaded forever (the silent re-introduction of a
    fixed bug). The lock record carries the spawner-written wall-clock
    `started_at`; a missing/unparseable one means we cannot judge — report
    NOT stale (fail-open to the pre-FIX 105 reuse behavior, never kill a
    dispatcher on a guess)."""
    started_at = lock_record.get("started_at")
    if not isinstance(started_at, (int, float)) or started_at <= 0:
        # ISO string form (older records): parse defensively; unparseable -> not stale.
        if isinstance(started_at, str) and started_at:
            try:
                from datetime import datetime
                started_at = datetime.fromisoformat(started_at).timestamp()
            except (ValueError, TypeError, OSError):
                return False, ""
        else:
            return False, ""
    try:
        scripts_dir = Path(__file__).resolve().parent.parent
        for name in _DISPATCHER_MODULE_FILES:
            f = scripts_dir / name
            if f.is_file() and f.stat().st_mtime > started_at + 1.0:
                return True, (f"{name} mtime {f.stat().st_mtime:.0f} > "
                              f"dispatcher started_at {float(started_at):.0f}")
    except OSError:
        return False, ""   # cannot judge the disk: never kill on a guess
    return False, ""


def _spawn_dispatcher_if_available(run_dir: Path, scripts_dir: Path,
                                    disabled: bool = False,
                                    run_id: Optional[str] = None) -> Optional[subprocess.Popen]:
    """Auto-spawn work_order_dispatcher.py --watch, scoped to `run_dir`, as a
    child of THIS process. See the module-level design note above this
    function for the full rationale (concurrency, getppid survival,
    termination, no-double-spawn). Call this BEFORE engine.run()/
    engine.close(), never after -- see the deadlock warning above.

    FIX 19: the dispatcher is spawned start_new_session=True — its own
    process-group leader — so _stop_auto_dispatcher's os.killpg reaches the
    watcher AND every in-flight wave worker it fathered, never just the
    watcher (the pre-FIX 19 terminate() that orphaned workers mid-wave).

    FIX 19: `run_id` is the current run's state.json job_id. The lock record
    now carries run_id; a lock holding a LIVE pid whose recorded run_id
    differs from `run_id` names a dispatcher from a DIFFERENT (earlier) run —
    an orphan — and is killed (whole process group: SIGTERM, 5 s grace,
    SIGKILL) before this run spawns its own fresh watcher. Only a live holder
    of the SAME run_id blocks the spawn ("already running for this run"),
    exactly the operator-manual-watcher convenience the original check
    protected, and never a stale cross-run orphan.

    Returns the Popen handle on a real spawn, or None when auto-dispatch is
    disabled (flag/env) or a same-run dispatcher is already alive for this
    run dir. The caller owns the returned handle and MUST pass it to
    _stop_auto_dispatcher when the run this call was made for is done,
    regardless of how it finished (success, block, or exception)."""
    if _auto_dispatch_disabled(disabled):
        return None

    lock_path = _auto_dispatch_lock_path(run_dir)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    recorded = _read_autospawn_lock(lock_path)
    existing_pid = 0
    try:
        existing_pid = int(recorded.get("pid") or 0)
    except (ValueError, TypeError):
        existing_pid = 0
    existing_run_id = str(recorded.get("run_id") or "")
    if existing_pid and _pid_is_alive(existing_pid):
        if run_id and existing_run_id and existing_run_id != run_id:
            # FIX 19: live pid, DIFFERENT run id — a dispatcher left over from
            # a previous job on this run dir. Kill its whole group (it is a
            # group leader: every FIX 19 spawn is start_new_session=True) so
            # its in-flight wave workers die with it, replace the lock, and
            # spawn fresh below. This is the "old lock file did not block the
            # new engine" half of the QC proof.
            print(f"[auto-dispatch] autospawn lock holds live pid {existing_pid} "
                  f"from run_id {existing_run_id!r} (this run: {run_id!r}) -- "
                  f"killing that orphan group and spawning fresh", flush=True)
            _kill_process_group_best_effort(existing_pid, signal.SIGTERM)
            time.sleep(5)
            if _pid_is_alive(existing_pid):
                _kill_process_group_best_effort(existing_pid, signal.SIGKILL)
                time.sleep(1)
        else:
            # FIX 105: same-run_id live holder — reuse it ONLY when its loaded
            # code is not stale. The lock record's started_at (wall clock,
            # written by the spawner at spawn time) is the dispatcher's birth;
            # if any module file it executes was modified AFTER that birth, the
            # running process predates the patch and must be replaced.
            stale, stale_detail = _dispatcher_modules_stale(recorded)
            if stale:
                print(f"[auto-dispatch] live dispatcher pid {existing_pid} for "
                      f"{run_dir} is running STALE modules ({stale_detail}) -- "
                      f"stopping it (whole process group) and spawning a fresh "
                      f"one on the patched code", flush=True)
                _kill_process_group_best_effort(existing_pid, signal.SIGTERM)
                time.sleep(5)
                if _pid_is_alive(existing_pid):
                    _kill_process_group_best_effort(existing_pid, signal.SIGKILL)
                    time.sleep(1)
            else:
                print(f"[auto-dispatch] work_order_dispatcher.py already running for "
                      f"{run_dir} (pid {existing_pid}) -- not spawning a second one",
                      flush=True)
                return None
    elif existing_pid:
        # Dead holder: clear the stale record so the fresh write below is the
        # only record for this run (dispatcher.py's _clear_stale_autospawn_
        # lock does the same from the watcher side).
        try:
            lock_path.unlink()
        except OSError:
            pass

    dispatcher_entry = scripts_dir / "work_order_dispatcher.py"
    argv = [sys.executable, str(dispatcher_entry), "--run-dir", str(run_dir), "--watch"]
    try:
        proc = subprocess.Popen(argv, cwd=str(scripts_dir),
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)  # FIX 19: own process group
    except OSError as exc:
        print(f"[auto-dispatch] could not spawn {dispatcher_entry}: {exc}",
              file=sys.stderr, flush=True)
        return None

    try:
        lock_path.write_text(
            json.dumps({"pid": proc.pid, "started_at": utcnow(),
                        "run_dir": str(run_dir), "run_id": run_id or ""}),
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
    this call does not own, and must be left alone.

    FIX 19: the watcher was spawned start_new_session=True, so stopping it
    means signalling its whole PROCESS GROUP (SIGTERM to proc.pid's group,
    then SIGKILL after the grace) — not just the watcher pid. The old
    terminate()/kill() pair killed the watcher and ORPHANED every wave
    worker mid-flight: the exact survivors that kept rewriting intake after
    an engine kill (the QC FIX 19 failure)."""
    if proc is None:
        return
    if proc.poll() is None:
        # FIX 19: group-TERM first (children included), then confirm, then
        # group-KILL as escalation. proc.pid IS the group leader.
        _kill_process_group_best_effort(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _kill_process_group_best_effort(proc.pid, signal.SIGKILL)
            try:
                proc.wait(timeout=5)
            except (subprocess.TimeoutExpired, Exception):  # noqa: BLE001 -- teardown never crashes the exit
                pass
    lock_path = _auto_dispatch_lock_path(run_dir)
    try:
        if lock_path.is_file():
            recorded = _read_autospawn_lock(lock_path)
            if recorded.get("pid") == proc.pid:
                lock_path.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------------------
# FIX 22 — `--run` on a parked job resets like `--resume`.
#   The door always invokes `--run` (deck-intake-driver / presentation_job.py
#   door path). Only the --resume branch cleared state["terminal"] and popped
#   state["blocked"], so a door --run against a PARKED job left terminal=BLOCKED
#   in state.json: the dispatcher's watch loop saw the set terminal and exited
#   immediately, and every agent phase then blocked after its full budget with
#   nothing servicing its work order ([F-R4 §A], [F-R1 §H.12]).
#   The reset is one shared helper so --run and --resume can never drift.
#   SOURCE: Master Part 8 FIX 22. SIZE XS. WORKFLOW W10a-B2.
# ---------------------------------------------------------------------------
def _reset_parked_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Clear a parked job's terminal/blocked marker and re-validate banked
    artifacts. Shared by --run and --resume (FIX 22) so the two entry modes
    reset identically. Preserves the cleared block in resume_history, exactly
    as the --resume branch did (U017: the diagnosis is preserved before it is
    cleared). Returns the prior "blocked" record (or None)."""
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
    return prior


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
        # The primary root may be os.pathsep-packed (":" on POSIX) -- the live
        # launchd plist passes SCAN_ROOT that way. split_primary turns it into
        # individual roots; the first chunk stays the findings/audit owner and
        # the rest ride in as extra roots, so watchdog()'s own resolution sees
        # the same root list the hotfix produced by looping over chunks here.
        primary_roots = split_primary(root)
        if not primary_roots:
            die(EXIT_USAGE, "--watchdog needs --scan-root")
        return _run_watchdog(
            primary_roots[0],
            grace_multiplier=getattr(args, 'grace', 1.5),
            scan_depth=sd,
            enforce=getattr(args, 'enforce', False),
            extra_roots=tuple(primary_roots[1:]) + tuple(args.scan_root_extras or ()),
            roots_config=args.roots_config,
        )

    if args.reconcile_board:
        if not args.scan_root:
            die(EXIT_USAGE, "--reconcile-board needs --scan-root")
        sd = args.scan_depth if hasattr(args, 'scan_depth') else 3
        # Same os.pathsep-packed primary as the --watchdog branch (see above).
        primary_roots = split_primary(args.scan_root)
        if not primary_roots:
            die(EXIT_USAGE, "--reconcile-board needs --scan-root")
        return reconcile_sweep(
            primary_roots[0],
            scan_depth=sd,
            apply=args.apply,
            max_age_hours=args.max_age_hours,
            extra_roots=tuple(primary_roots[1:]) + tuple(args.scan_root_extras or ()),
            roots_config=args.roots_config,
        )

    # FIX 64 (one notification transport): --sweep-undeliverable-roots is the
    # SCHEDULED driver for the undeliverable queue -- the pass a watchdog tick
    # runs without knowing any --run-dir. Without this branch the flag parsed
    # but was never reachable from main(): execution fell through to the
    # "--run-dir is required" usage refusal, so nothing could ever schedule
    # the retry loop report.py queues into state["undeliverable"]. Run it
    # BEFORE that --run-dir requirement, alongside the other scan-root modes.
    if args.sweep_undeliverable_roots:
        if not args.scan_root:
            die(EXIT_USAGE, "--sweep-undeliverable-roots needs --scan-root")
        return cmd_sweep_undeliverable_roots(args)

    if args.supervise:
        root = (args.scan_root or args.run_dir)
        if not root:
            die(EXIT_USAGE, "--supervise needs --scan-root")
        if args.max_restarts is not None and args.max_restarts < 0:
            die(EXIT_USAGE, "--max-restarts must be >= 0")
        if args.supervisor_backoff is not None and args.supervisor_backoff < 0:
            die(EXIT_USAGE, "--supervisor-backoff must be >= 0")
        sd = args.scan_depth if hasattr(args, 'scan_depth') else 3
        if sd < 1:
            die(EXIT_USAGE, "--scan-depth must be >= 1")
        return _run_supervise(
            root.expanduser().resolve(),
            scan_depth=sd,
            apply=args.apply,
            max_restarts=(DEFAULT_MAX_RESTARTS if args.max_restarts is None
                          else args.max_restarts),
            backoff_seconds=(DEFAULT_BACKOFF_SECONDS if args.supervisor_backoff is None
                             else args.supervisor_backoff),
            max_idle_hours=args.max_idle_hours,
        )

    if args.apply and not args.reconcile_board:
        die(EXIT_USAGE, "--apply is only meaningful with --reconcile-board")

    # --capacity needs no run-dir: it is a read-only probe of the harness.
    if args.capacity:
        return cmd_capacity(args)

    # MASTER Part 8 FIX 8: --plan is read-only inspection of the execution
    # plan (same manifest resolution --run uses, never a phase run, never
    # the lease). Sits BEFORE the "--run-dir is required" refusal: the QC
    # proof shape is `--plan --run-dir <fresh dir>` where no state exists
    # yet, so the run dir is optional-but-expected, never mandated.
    if args.plan:
        return cmd_plan(args, scripts_dir)

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
    # FIX 20: repin BEFORE the RunLock block — that block verify_pin()s against
    # state's pinned sha and would die(7) on exactly the mismatch repin exists
    # to cure. cmd_repin does its own state load/save under its own reads.
    if args.repin:
        return cmd_repin(args, scripts_dir)

    # -----------------------------------------------------------------------
    # FIX 18 — the engine refuses to run without a lease it holds.
    #   Every launch path funnels through here for --run/--resume/--close and
    #   single-phase runs, so the lease is taken ONCE, before the RunLock, by
    #   the process that will drive the engine. A second engine started one
    #   second apart exits EXIT_LOCK_HELD naming the first's pid and host from
    #   working/.lease.json (lease_mod.describe_holder) -- the exact refusal
    #   the FIX 18 proof greps for -- and never spawns a dispatcher.
    #   The heartbeat thread renews every LEASE_HEARTBEAT_S (60 s); it is
    #   stopped (and the lease released) in the same finally that stops the
    #   auto-dispatcher, so every exit path -- done, blocked, exception,
    #   SIGKILL (expiry does the work there) -- ends ownership inside ttl_s.
    #   SOURCE: Master Part 8 FIX 18. WORKFLOW W10a-B1.
    # -----------------------------------------------------------------------
    lease_held = None
    lease_hb = None
    if args.new or args.status or args.capacity or args.workingset is not None \
            or args.sweep_undeliverable or args.diagnose_only:
        pass  # read-only / creation / diagnosis modes do not need the run lease
    else:
        lease_held = lease_mod.acquire(
            run_dir, {"who": os.environ.get("PRESENTATION_LEASE_WHO", "engine")},
            ttl_s=LEASE_TTL_S)
        if lease_held is None:
            holder = lease_mod.describe_holder(run_dir)
            die(EXIT_LOCK_HELD,
                f"another engine owns this run -- refusing to start a second.\n"
                f"  holder: {holder}\n"
                f"  run   : {run_dir}\n"
                f"The holder's lease expires (ttl {LEASE_TTL_S}s, heartbeats every "
                f"{LEASE_HEARTBEAT_S}s); retry after it lapses, or after the holder exits.")

    try:
      with RunLock(run_dir):
        store = StateStore(run_dir)
        state = store.load()
        # FIX 19 (MASTER Part 8): this engine is (via the launcher's
        # start_new_session=True spawn) its own process-group leader, so a
        # stop_engine() SIGTERM reaches the whole tree. The handler only
        # RAISES a flag -- a signal handler never performs cleanup -- but the
        # flag is observable proof in the log that the signal was received
        # and the normal finally path (lease release, dispatcher stop) owns
        # the unwind. Without it a SIGTERM mid-wave looked like a silent
        # death with no teardown at all.
        _install_engine_sigterm_handler()
        manifest_path = Path(state.get("manifest_path") or
                             resolve_manifest(args.manifest, run_dir, scripts_dir))
        if not manifest_path.is_file():
            die(EXIT_MANIFEST_MISMATCH, f"pinned manifest {manifest_path} is gone")
        manifest = Manifest(manifest_path)
        # FIX 20: a sha mismatch here used to be a bare die(7) stranding the
        # run with no way forward. It must die ALL the same — the pin is real
        # and the engine must not silently run a different manifest — but the
        # message now names the repin command that cures it, so the operator
        # has the next step instead of a dead end.
        pinned = str(state.get("manifest_sha256") or "")
        if pinned and pinned != manifest.sha256:
            die(EXIT_MANIFEST_MISMATCH,
                "manifest changed under a running job.\n"
                f"  pinned : {pinned}\n"
                f"  on disk: {manifest.sha256}\n"
                f"  file   : {manifest.path}\n"
                "A job started under one manifest must finish under it.\n"
                "To continue this job under the CURRENT manifest, re-pin it first:\n"
                f"  presentation_job.py --repin --run-dir {run_dir}\n"
                + (f"  (or pass --manifest <path> to repin against a specific copy)\n"
                   if not args.manifest else "")
                + "then --resume. Old and new shas are both recorded in state "
                  "(manifest_sha256_prev + manifest.repin history).")

        engine = Engine(run_dir, manifest, store, state, dry_run=args.dry_run)

        # FIX 18 -- start the 60 s heartbeat now that the lease is held and the
        # engine is real. A lost lease (holder died and another engine took
        # over) is logged and stops renewal; the engine does not self-kill
        # mid-phase, the RunLock still protects state.json.
        if lease_held is not None:
            def _on_lease_lost(_lease, _run_dir=run_dir):
                print(f"[lease] lease for {run_dir} lost (expired and taken over) "
                      f"-- heartbeat stopped; this engine keeps running under the "
                      f"RunLock but is no longer the registered owner",
                      file=sys.stderr, flush=True)
            lease_hb = lease_mod.start_heartbeat(
                lease_held, interval_s=LEASE_HEARTBEAT_S, on_loss=_on_lease_lost)
            print(f"[lease] acquired ({lease_held.doc.get('pid')} on "
                  f"{lease_held.doc.get('host')}); ttl {LEASE_TTL_S}s, "
                  f"heartbeat every {LEASE_HEARTBEAT_S}s", flush=True)

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
            # FIX 22: the terminal/blocked reset is the SHARED helper now, so
            # --resume and --run reset a parked job identically and can never
            # drift (see _reset_parked_state above).
            prior = _reset_parked_state(state)
            store.save(state)
            engine.report.event(
                "job.resume",
                "resuming from checkpoint; banked artifacts reused" +
                (f"; cleared block at {prior.get('phase')}: {prior.get('reason')}" if prior else ""))
        elif args.run:
            # FIX 22 — --run on a parked job resets like --resume. The door
            # always invokes --run; before this branch a parked run kept
            # terminal=BLOCKED in state.json, so the dispatcher's watch loop
            # saw the set terminal and exited immediately ("run terminal is
            # set -- exiting", dispatcher.py) and every agent phase then
            # blocked after its full budget with nothing servicing its work
            # order ([F-R4 §A], [F-R1 §H.12]). Same reset, different entry
            # verb; announce it so an operator scanning output sees why the
            # parked marker vanished.
            if state.get("terminal") or state.get("blocked"):
                prior = _reset_parked_state(state)
                store.save(state)
                engine.report.event(
                    "job.run_reset",
                    "--run on a parked job: cleared terminal/blocked like --resume" +
                    (f"; cleared block at {prior.get('phase')}: {prior.get('reason')}"
                     if prior else ""),
                    phase_id=(prior or {}).get("phase"))

        # F07 -- auto-spawn the Work-Order Dispatcher for this run, CONCURRENTLY
        # with the engine (spawned before engine.run(), never after -- see the
        # design note above _spawn_dispatcher_if_available). --dry-run never
        # executes agent phases for real (no work orders are serviced, none are
        # even worth spawning a dispatcher over), so it is excluded here.
        # FIX 19: the run's job_id rides along as run_id so the autospawn-lock
        # preemption can tell a SAME-run watcher (leave it) from a PREVIOUS
        # run's orphan (kill its group and spawn fresh).
        dispatcher_proc = None
        if not args.dry_run:
            dispatcher_proc = _spawn_dispatcher_if_available(
                run_dir, scripts_dir, disabled=args.no_auto_dispatch,
                run_id=str(state.get("job_id") or ""))
        try:
            return engine.run(only=args.phase, until=args.until)
        finally:
            _stop_auto_dispatcher(run_dir, dispatcher_proc)
    # FIX 18 -- every exit path of the RunLock block (done, blocked,
    # exception, die()) stops the heartbeat and releases the lease, so the
    # next engine (or the supervisor's restart) can acquire without waiting
    # out ttl_s.
    finally:
        if lease_hb is not None:
            lease_hb.stop()
            lease_hb.join(timeout=5)
        if lease_held is not None:
            lease_mod.release(lease_held)
