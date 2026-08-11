#!/usr/bin/env python3
"""run_discovery.py -- find run directories that are not registered as jobs (MASTER-SPEC FILE 8).

A run directory is any directory under --runs-root that contains either
state.json (an engine job) or working/checkpoints/process_manifest.json (a
pre-engine legacy run). A directory is 'registered' when its state.json has a
job_id and run_dir (the engine wrote it) -- legacy dirs have neither, so they
are exactly what this tool discovers and retroactively ingests.

  * find_unregistered_runs(runs_root) -- returns the unregistered run dirs.
  * retroactively_ingest(run_dir) -- write a minimal state.json (job_id,
    run_dir, schema_version 1, timestamps) so the run becomes a registered job.
  * main() -- --runs-root <path>; FAIL-SOFT: every failure is reported and
    counted, but the exit code is ALWAYS 0. Read-only unless --ingest is given.

Usage:
  python3 run_discovery.py --runs-root <runs-root>
  python3 run_discovery.py --runs-root <runs-root> --ingest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

SCHEMA_VERSION = 1


def utcnow() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------
def _is_run_dir(path: Path) -> bool:
    """A run dir carries state.json or a legacy process_manifest.json."""
    if (path / "state.json").is_file():
        return True
    if (path / "working" / "checkpoints" / "process_manifest.json").is_file():
        return True
    return False


def _is_registered(path: Path) -> bool:
    """Registered = state.json exists and declares a job_id + run_dir."""
    state_path = path / "state.json"
    if not state_path.is_file():
        return False
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(state, dict):
        return False
    return bool(state.get("job_id")) and bool(state.get("run_dir"))


def find_unregistered_runs(runs_root: str | Path) -> List[Path]:
    """Scan runs_root (one level deep) for run dirs that are not registered.

    Fail-soft: unreadable entries are skipped, never fatal."""
    root = Path(runs_root).expanduser().resolve()
    unregistered: List[Path] = []
    if not root.is_dir():
        return unregistered
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return unregistered
    for entry in entries:
        if not entry.is_dir():
            continue
        try:
            if _is_run_dir(entry) and not _is_registered(entry):
                unregistered.append(entry)
        except OSError:
            continue
    return unregistered


# ---------------------------------------------------------------------------
# Retroactive ingestion
# ---------------------------------------------------------------------------
def retroactively_ingest(run_dir: str | Path) -> Tuple[bool, str]:
    """Register a legacy run dir by writing a minimal state.json.

    Refuses to touch an existing state.json (never overwrites). Returns
    (ok, message)."""
    path = Path(run_dir).expanduser().resolve()
    state_path = path / "state.json"
    if state_path.exists():
        return False, f"state.json already exists at {state_path} -- refusing to overwrite"
    state: Dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "job_id": "pj_legacy_" + _sha256_text(str(path))[:26],
        "run_dir": str(path),
        "created_at": utcnow(),
        "discovered_by": "run_discovery.py (retroactive ingest)",
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
    tmp = state_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    import os
    os.replace(tmp, state_path)
    return True, f"registered {path} (job_id={state['job_id']})"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_discovery.py",
        description="Find run directories that are not registered as jobs (MASTER-SPEC FILE 8). "
                    "Fail-soft: exit 0 always.",
    )
    p.add_argument("--runs-root", type=Path, required=True,
                   help="root directory holding run directories")
    p.add_argument("--ingest", action="store_true",
                   help="retroactively register discovered runs (default: report only)")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.runs_root).expanduser().resolve()
    if not root.is_dir():
        print(f"run_discovery: runs-root not a directory: {root}", file=sys.stderr)
        return 0  # fail-soft: exit 0 always

    try:
        unregistered = find_unregistered_runs(root)
    except Exception as exc:  # noqa: BLE001 -- fail-soft
        print(f"run_discovery: scan failed: {exc}", file=sys.stderr)
        return 0

    print(f"run_discovery: scanned {root}", flush=True)
    print(f"run_discovery: {len(unregistered)} unregistered run dir(s)", flush=True)
    ingested = 0
    failed = 0
    for run_dir in unregistered:
        print(f"  unregistered: {run_dir}", flush=True)
        if args.ingest:
            try:
                ok, msg = retroactively_ingest(run_dir)
            except Exception as exc:  # noqa: BLE001 -- fail-soft
                ok, msg = False, f"ingest failed: {exc}"
            if ok:
                ingested += 1
            else:
                failed += 1
            print(f"    {'[OK]' if ok else '[FAIL]'} {msg}", flush=True)
    if args.ingest:
        print(f"run_discovery: ingested {ingested}, failed {failed}", flush=True)
    return 0  # fail-soft: exit 0 always


if __name__ == "__main__":
    sys.exit(main())
