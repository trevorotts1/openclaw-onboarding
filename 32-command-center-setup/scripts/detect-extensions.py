#!/usr/bin/env python3
"""
detect-extensions.py — Skill 32 Command Center Setup

PURPOSE
    Compares the current role-library _index.json against a saved last-sync
    manifest (last-sync.json) and emits the delta: which departments are NEW
    since the last sync run.

OUTPUT FORMAT (stdout)
    NEW: <dept-slug>       — one line per new department
    SKIP: <dept-slug>      — one line per already-synced department (verbose only)
    INFO: <message>        — informational line (verbose only)

    Exit 0 = success (even if no new depts)
    Exit 1 = error (malformed index or unreadable files)

USAGE
    python3 detect-extensions.py \\
        --index  /path/to/_index.json \\
        [--last-sync /path/to/last-sync.json] \\
        [--verbose]
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone


def load_json(path: str, label: str) -> dict:
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"INFO: {label} not found at {path} — treating as empty baseline",
              flush=True)
        return {}
    except json.JSONDecodeError as e:
        print(f"ERROR: Cannot parse {label} at {path}: {e}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect role-library extension delta")
    parser.add_argument("--index",     required=True,
                        help="Path to role-library _index.json (current truth)")
    parser.add_argument("--last-sync", default=None,
                        help="Path to last-sync.json (prior sync state)")
    parser.add_argument("--verbose",   action="store_true",
                        help="Also emit SKIP: lines for already-synced depts")
    args = parser.parse_args()

    # ── Load current index ───────────────────────────────────────────────────
    index = load_json(args.index, "_index.json")
    current_depts: set[str] = set(index.get("departments", {}).keys())
    index_version = index.get("version", "unknown")

    if not current_depts:
        print("INFO: _index.json has no departments — nothing to sync", flush=True)
        sys.exit(0)

    if args.verbose:
        print(f"INFO: _index.json version={index_version}, "
              f"departments={len(current_depts)}", flush=True)

    # ── Load prior sync state ────────────────────────────────────────────────
    synced_depts: set[str] = set()
    if args.last_sync and Path(args.last_sync).exists():
        last_sync = load_json(args.last_sync, "last-sync.json")
        synced_depts = set(last_sync.get("departments", []))
        synced_at = last_sync.get("synced_at", "unknown")
        if args.verbose:
            print(f"INFO: last-sync.json synced_at={synced_at}, "
                  f"synced_depts={len(synced_depts)}", flush=True)
    else:
        if args.verbose:
            print("INFO: No last-sync.json — treating all departments as new",
                  flush=True)

    # ── Compute delta ────────────────────────────────────────────────────────
    new_depts = sorted(current_depts - synced_depts)
    already_synced = sorted(current_depts & synced_depts)
    removed_depts = sorted(synced_depts - current_depts)  # informational only

    if args.verbose:
        for dept in removed_depts:
            print(f"INFO: dept removed from index since last sync: {dept}",
                  flush=True)
        for dept in already_synced:
            print(f"SKIP: {dept}", flush=True)

    for dept in new_depts:
        print(f"NEW: {dept}", flush=True)

    if args.verbose:
        print(f"INFO: delta summary — "
              f"new={len(new_depts)}, "
              f"synced={len(already_synced)}, "
              f"removed={len(removed_depts)}", flush=True)


if __name__ == "__main__":
    main()
