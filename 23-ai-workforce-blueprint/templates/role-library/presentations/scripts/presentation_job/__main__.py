from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .state import (
    StateStore, RunLock, utcnow, sha256_text,
    die, EXIT_OK, EXIT_USAGE, EXIT_MANIFEST_MISMATCH,
    EXIT_STATE_CORRUPT, STATE_SCHEMA_VERSION,
)
from .manifest import Manifest, resolve_manifest
from .phases import Engine
from .watchdog import watchdog as _run_watchdog
from .board import BoardMirror
from .sweep import reconcile_sweep

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="presentation_job.py",
        description="The process engine for the Presentation Department. "
                    "Walks the manifest, refuses to skip a step, announces where it is.")
    m = p.add_mutually_exclusive_group(required=True)
    m.add_argument("--new", action="store_true", help="create a job in --run-dir from --intake")
    m.add_argument("--run", action="store_true", help="run the phase loop")
    m.add_argument("--resume", action="store_true", help="resume a parked job from checkpoint")
    m.add_argument("--status", action="store_true", help="print job status")
    m.add_argument("--close", action="store_true", help="evaluate gates and close")
    m.add_argument("--watchdog", action="store_true", help="scan for stalled jobs")
    m.add_argument("--reconcile-board", action="store_true",
                   help="scan --scan-root for jobs whose board card is missing or behind; "
                        "reports only unless --apply is given")
    p.add_argument("--run-dir", type=Path, help="the job's run directory")
    p.add_argument("--intake", type=Path, help="intake JSON for --new")
    p.add_argument("--manifest", help="explicit PIPELINE-MANIFEST.json path")
    p.add_argument("--phase", help="run exactly one phase")
    p.add_argument("--until", help="run through this phase then stop")
    p.add_argument("--scan-root", type=Path, help="root to scan for --watchdog / --reconcile-board")
    p.add_argument("--dry-run", action="store_true", help="print what would run, execute nothing")
    p.add_argument("--json", action="store_true", help="machine-readable --status")
    p.add_argument("--apply", action="store_true",
                   help="with --reconcile-board: actually create and advance cards")
    p.add_argument("--max-age-hours", type=float, default=72.0,
                   help="with --reconcile-board: ignore run dirs created longer ago than this")
    if not any("--scan-depth" in a.option_strings for a in p._actions):
        p.add_argument("--scan-depth", type=int, default=2,
                       help="how many directory levels below --scan-root to search for state.json")
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
    legal = ("from_scratch", "content_personal", "content_general", "signature")
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
    if st.get("undeliverable"):
        print(f"UNDELIVERABLE messages: {len(st['undeliverable'])} "
              "(the requester was NOT told — see F2)")
    return EXIT_OK



def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    scripts_dir = Path(__file__).resolve().parent.parent

    if args.watchdog:
        root = (args.scan_root or args.run_dir)
        if not root:
            die(EXIT_USAGE, "--watchdog needs --scan-root")
        return _run_watchdog(root.expanduser().resolve())

    if args.reconcile_board:
        if not args.scan_root:
            die(EXIT_USAGE, "--reconcile-board needs --scan-root")
        return reconcile_sweep(
            args.scan_root.expanduser().resolve(),
            scan_depth=args.scan_depth if hasattr(args, "scan_depth") else 2,
            apply=args.apply,
            max_age_hours=args.max_age_hours,
        )

    if args.apply:
        die(EXIT_USAGE, "--apply is only meaningful with --reconcile-board")

    if not args.run_dir:
        die(EXIT_USAGE, "--run-dir is required")
    run_dir = args.run_dir.expanduser().resolve()

    if args.new:
        return cmd_new(args, scripts_dir)
    if args.status:
        return cmd_status(args)

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
        if args.close:
            return engine.close()
        if args.resume:
            state["terminal"] = None
            state.pop("blocked", None)
            store.save(state)
            engine.report.event("job.resume", "resuming from checkpoint; banked artifacts reused")
        return engine.run(only=args.phase, until=args.until)



