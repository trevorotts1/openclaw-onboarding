#!/usr/bin/env python3
"""run_discovery.py -- find run directories that are not registered as jobs (MASTER-SPEC FILE 8).

A run directory is any directory under a scan root that carries one of the
IDENTITY MARKERS in presentation_job.scan_roots.RUN_DIR_MARKERS -- state.json (an
engine job), working/checkpoints/process_manifest.json (a pre-engine legacy run),
or .job.lock (a job that started but died before its first state write). A
directory is 'registered' when its state.json has a job_id and run_dir (the
engine wrote it) -- legacy dirs have neither, so they are exactly what this tool
discovers and retroactively ingests.

TWO BLIND SPOTS CLOSED 2026-08-27 (see presentation_job/scan_roots.py):

  1. ONE ROOT. --runs-root took a single path, and presentation-watchdog.sh only
     ever passed the department tree, so a client deck built anywhere else was
     invisible. --runs-root is now repeatable and is unioned with
     PRESENTATION_SCAN_ROOTS and a config file.

  2. ONE LEVEL DEEP. find_unregistered_runs used root.iterdir(), so even pointed
     at the correct root it would have missed the incident run, which sat three
     levels down at <root>/<client>/<deck>/<date>/. Discovery is now a bounded
     walk to --scan-depth (default 3), matching the watchdog's own default.

Neither identity nor depth is inferred from a directory's NAME. The incident run
was named "2026-08-27" -- a date, not a "pres-*" slug -- so any convention-based
filter would have missed it a third time.

FAIL-SOFT and NON-BLOCKING: every failure is reported and counted, the exit code
is ALWAYS 0, and the tool is read-only unless --ingest is given. A root that
cannot be read is reported UNDETERMINED and never as "no runs here" -- absence
from a scan that could not run is not evidence about any deck.

  * find_unregistered_runs(runs_root, scan_depth) -- unregistered dirs in one root.
  * discover(roots, scan_depth) -- multi-root scan returning a DiscoveryReport.
  * retroactively_ingest(run_dir) -- write a minimal state.json (job_id,
    run_dir, schema_version 1, timestamps) so the run becomes a registered job.

Usage:
  python3 run_discovery.py --runs-root <runs-root>
  python3 run_discovery.py --runs-root <a> --runs-root <b> --scan-depth 4
  python3 run_discovery.py --runs-root <runs-root> --ingest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from presentation_job.scan_roots import (  # noqa: E402
    ScanRoot, default_config_path, format_roots_report, is_run_dir,
    matched_markers, ok_roots, resolve_scan_roots, undetermined_roots,
)

SCHEMA_VERSION = 1
DEFAULT_SCAN_DEPTH = 3


def utcnow() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------
def _is_run_dir(path: Path) -> bool:
    """A run dir proves itself by content, never by name. See scan_roots."""
    return is_run_dir(path)


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


def _walk_candidates(root: Path, scan_depth: int):
    """Yield every directory from 1..scan_depth levels below root.

    Bounded and iterative -- NOT rglob, which can stall for minutes on a large
    tree (same reasoning as watchdog._find_state_files). A run dir is not
    descended into: a deck's own working/ subtree never holds another run."""
    frontier = [root]
    for _ in range(scan_depth):
        next_frontier: List[Path] = []
        for parent in frontier:
            try:
                entries = sorted(p for p in parent.iterdir() if p.is_dir())
            except OSError:
                continue
            for entry in entries:
                yield entry
                if not _is_run_dir(entry):
                    next_frontier.append(entry)
        frontier = next_frontier


def find_unregistered_runs(runs_root: str | Path,
                           scan_depth: int = DEFAULT_SCAN_DEPTH) -> List[Path]:
    """Scan runs_root to scan_depth for run dirs that are not registered.

    Fail-soft: unreadable entries are skipped, never fatal. Kept as a
    single-root helper so existing callers and tests keep working; multi-root
    callers should use discover()."""
    root = Path(runs_root).expanduser().resolve()
    unregistered: List[Path] = []
    if not root.is_dir():
        return unregistered
    seen: Set[Path] = set()
    for entry in _walk_candidates(root, scan_depth):
        try:
            resolved = entry.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            if _is_run_dir(entry) and not _is_registered(entry):
                unregistered.append(entry)
        except OSError:
            continue
    return sorted(unregistered)


@dataclass
class DiscoveryReport:
    """What was searched, what was found, and what could not be determined."""

    roots: List[ScanRoot] = field(default_factory=list)
    unregistered: List[Path] = field(default_factory=list)
    markers: Dict[str, List[str]] = field(default_factory=dict)

    @property
    def searched(self) -> List[ScanRoot]:
        return ok_roots(self.roots)

    @property
    def unsearchable(self) -> List[ScanRoot]:
        return undetermined_roots(self.roots)

    @property
    def complete(self) -> bool:
        """False whenever any configured root could not be read.

        A caller must never turn `unregistered == []` into "there are no
        unregistered runs" while this is False -- that is the exact inference
        that let a live client deck go unwatched for three hours."""
        return not self.unsearchable

    @property
    def verdict(self) -> str:
        if not self.complete:
            return "UNDETERMINED"
        return "found" if self.unregistered else "none"


def discover(roots: List[ScanRoot],
             scan_depth: int = DEFAULT_SCAN_DEPTH) -> DiscoveryReport:
    """Scan every readable root, de-duplicating runs reachable from two roots."""
    report = DiscoveryReport(roots=roots)
    seen: Set[Path] = set()
    for root in ok_roots(roots):
        for run_dir in find_unregistered_runs(root.path, scan_depth):
            resolved = run_dir.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            report.unregistered.append(resolved)
            report.markers[str(resolved)] = matched_markers(resolved)
    report.unregistered.sort()
    return report


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
    p.add_argument("--runs-root", type=Path, action="append", default=None,
                   dest="runs_roots", metavar="PATH",
                   help="root directory holding run directories; repeatable. "
                        "Unioned with PRESENTATION_SCAN_ROOTS and --roots-config.")
    p.add_argument("--roots-config", type=Path, default=None,
                   help="config file listing additional roots, one path per line "
                        "(default: <department>/config/scan-roots.conf, "
                        "overridable with SCAN_ROOTS_CONFIG)")
    p.add_argument("--scan-depth", type=int, default=DEFAULT_SCAN_DEPTH,
                   help=f"how many directory levels below each root to search "
                        f"(default {DEFAULT_SCAN_DEPTH})")
    p.add_argument("--ingest", action="store_true",
                   help="retroactively register discovered runs (default: report only)")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.scan_depth < 1:
        print("run_discovery: --scan-depth must be >= 1", file=sys.stderr)
        return 0  # fail-soft: exit 0 always

    cli_roots = list(args.runs_roots or [])
    primary = cli_roots[0] if cli_roots else None
    config_path = args.roots_config or default_config_path(_SCRIPTS_DIR)
    roots = resolve_scan_roots(
        primary=primary, extra=cli_roots[1:], config_path=config_path,
    )

    print(format_roots_report(roots, "run_discovery"), flush=True)
    if not ok_roots(roots):
        # No readable root at all. This is UNDETERMINED, not "no unregistered
        # runs" -- the distinction the 2026-08-27 incident turned on.
        print("run_discovery: UNDETERMINED -- no readable scan root; "
              "nothing could be checked. This is NOT evidence that every run is "
              "registered.", file=sys.stderr, flush=True)
        return 0

    try:
        report = discover(roots, args.scan_depth)
    except Exception as exc:  # noqa: BLE001 -- fail-soft
        print(f"run_discovery: scan failed: {exc}", file=sys.stderr)
        return 0

    print(f"run_discovery: searched {len(report.searched)} root(s) at depth "
          f"{args.scan_depth}", flush=True)
    print(f"run_discovery: {len(report.unregistered)} unregistered run dir(s) "
          f"[verdict: {report.verdict}]", flush=True)
    ingested = 0
    failed = 0
    for run_dir in report.unregistered:
        marks = ",".join(report.markers.get(str(run_dir), [])) or "?"
        print(f"  unregistered: {run_dir} (markers: {marks})", flush=True)
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
    if not report.complete:
        print(f"run_discovery: WARNING -- {len(report.unsearchable)} configured root(s) "
              f"could not be read; this scan is INCOMPLETE. A run not listed above is "
              f"UNDETERMINED, not absent.", flush=True)
    return 0  # fail-soft: exit 0 always


if __name__ == "__main__":
    sys.exit(main())
