#!/usr/bin/env python3
"""Provenance register coverage check (MG-047).

Fails when any dependency in the two shipped npm locks has no record in
references/provenance-register.json, so the license and provenance
register cannot silently rot as dependencies change.

Locks covered:
  - shared-utils/motion-render-runtime/package-lock.json (the provisioned
    render runtime: Remotion, Hyperframes, GSAP, React, and their trees)
  - 72-motion-video-plus/runtime/package-lock.json (the skill runtime)

A record counts as coverage when the register carries an npm_dependency
record with the same name and version. A record whose status is
"unresolved" still counts as coverage: the register's job is that every
dependency is looked at and its position recorded honestly, including
when the honest position is that no license statement was found.

Usage:
    python3 scripts/check_provenance.py [--register PATH]

Exit codes: 0 covered, 1 missing records, 2 inputs unreadable.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
REPO_ROOT = SKILL_ROOT.parent
DEFAULT_REGISTER = SKILL_ROOT / "references" / "provenance-register.json"
LOCK_PATHS = [
    REPO_ROOT / "shared-utils" / "motion-render-runtime" / "package-lock.json",
    SKILL_ROOT / "runtime" / "package-lock.json",
]


def lock_packages(lock_path: Path) -> set[tuple[str, str]]:
    """Unique (name, version) pairs a package-lock.json ships."""
    doc = json.loads(lock_path.read_text(encoding="utf-8"))
    out: set[tuple[str, str]] = set()
    for path, meta in doc.get("packages", {}).items():
        if path == "":
            continue
        name = meta.get("name") or path.split("node_modules/")[-1]
        version = meta.get("version")
        if name and version:
            out.add((name, version))
    return out


def register_packages(register: dict) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for rec in register.get("records", []):
        if rec.get("kind") == "npm_dependency":
            out.add((rec.get("name"), rec.get("version")))
    return out


def missing_records(register: dict, lock_paths: list[Path]) -> list[str]:
    """Sorted 'name@version' strings shipped by the locks but unrecorded."""
    shipped: set[tuple[str, str]] = set()
    for lp in lock_paths:
        shipped |= lock_packages(lp)
    recorded = register_packages(register)
    return sorted(f"{n}@{v}" for (n, v) in shipped - recorded)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", type=Path, default=DEFAULT_REGISTER)
    args = parser.parse_args(argv)

    try:
        register = json.loads(args.register.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: cannot read register {args.register}: {exc}")
        return 2
    for lp in LOCK_PATHS:
        if not lp.is_file():
            print(f"ERROR: lock not found: {lp}")
            return 2

    missing = missing_records(register, LOCK_PATHS)
    shipped: set[tuple[str, str]] = set()
    for lp in LOCK_PATHS:
        shipped |= lock_packages(lp)
    if missing:
        print(f"FAIL: {len(missing)} shipped dependencies have no provenance record:")
        for item in missing:
            print(f"  MISSING {item}")
        return 1
    print(f"PASS: all {len(shipped)} unique name@version dependencies in the "
          f"shipped locks have provenance records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
