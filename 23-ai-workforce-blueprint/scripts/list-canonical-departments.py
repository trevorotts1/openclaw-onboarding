#!/usr/bin/env python3
"""
list-canonical-departments.py — single-source-of-truth department floor printer.

Reads department-naming-map.json and prints:
  1. The 19 mandatory departments (every client gets these unless explicitly declined).
  2. The 7 universal-primary vertical-pack departments (one per pack, marked
     universal_primary=true — added for every client regardless of industry).
  3. The computed floor = mandatory count + universal-primary count = 26.

This script IS the canonical count. All docs and CI reference it instead of
hardcoding 16, 17, 23, 24, or any other stale number.

USAGE
  python3 list-canonical-departments.py           # human-readable to stdout
  python3 list-canonical-departments.py --json    # machine-readable JSON

EXIT CODES
  0  success
  1  naming map not found or could not be parsed
"""

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
NAMING_MAP = SKILL_DIR / "department-naming-map.json"


def load_naming_map():
    if not NAMING_MAP.exists():
        print(f"ERROR: naming map not found at {NAMING_MAP}", file=sys.stderr)
        sys.exit(1)
    try:
        return json.loads(NAMING_MAP.read_text())
    except json.JSONDecodeError as e:
        print(f"ERROR: could not parse naming map: {e}", file=sys.stderr)
        sys.exit(1)


def get_mandatory(nm):
    """Return list of mandatory department dicts with id + display_name."""
    result = []
    for dept_id, dept in (nm.get("mandatory") or {}).items():
        result.append({
            "id": dept_id,
            "display_name": dept.get("display_name", dept_id),
            "one_liner": dept.get("one_liner", ""),
        })
    return result


def get_universal_primaries(nm):
    """
    Return list of universal-primary vertical-pack depts — one per pack.
    The universal primary is the dept marked universal_primary=true in each
    pack's auto_add_departments (first dept is the fallback if none are marked).
    """
    result = []
    seen = set()
    for pack_id, pack in (nm.get("vertical_packs") or {}).items():
        if not isinstance(pack, dict):
            continue
        depts = pack.get("auto_add_departments") or []
        if not depts:
            continue
        primary = None
        for dept in depts:
            if isinstance(dept, dict) and dept.get("universal_primary"):
                primary = dept
                break
        if primary is None and depts:
            primary = depts[0] if isinstance(depts[0], dict) else None
        if primary:
            did = primary.get("id")
            if did and did not in seen:
                seen.add(did)
                result.append({
                    "id": did,
                    "display_name": primary.get("name", did),
                    "one_liner": primary.get("one_liner", ""),
                    "pack": pack_id,
                })
    return result


def main(argv):
    as_json = "--json" in argv
    nm = load_naming_map()

    mandatory = get_mandatory(nm)
    universal_primaries = get_universal_primaries(nm)
    floor = len(mandatory) + len(universal_primaries)

    if as_json:
        output = {
            "source": str(NAMING_MAP),
            "naming_map_version": nm.get("version", "unknown"),
            "mandatory_count": len(mandatory),
            "mandatory": mandatory,
            "universal_primary_count": len(universal_primaries),
            "universal_primary_vertical": universal_primaries,
            "floor": floor,
            "floor_label": f"{len(mandatory)} mandatory + {len(universal_primaries)} universal-primary vertical = {floor}",
        }
        print(json.dumps(output, indent=2))
    else:
        print("=" * 64)
        print("Canonical Department Floor")
        print(f"Source: {NAMING_MAP.relative_to(SKILL_DIR.parent) if NAMING_MAP.is_relative_to(SKILL_DIR.parent) else NAMING_MAP}")
        print(f"Naming map version: {nm.get('version', 'unknown')}")
        print("=" * 64)
        print(f"\n--- MANDATORY ({len(mandatory)}) ---")
        print("  These are built for EVERY client unless explicitly declined.\n")
        for i, dept in enumerate(mandatory, 1):
            print(f"  {i:2d}. {dept['display_name']:<30}  ({dept['id']})")

        print(f"\n--- UNIVERSAL PRIMARY VERTICAL PACK ({len(universal_primaries)}) ---")
        print("  One per vertical pack, added to every client regardless of industry.\n")
        for i, dept in enumerate(universal_primaries, 1):
            print(f"  {i:2d}. {dept['display_name']:<30}  ({dept['id']})  [pack: {dept['pack']}]")

        print(f"\n{'=' * 64}")
        print(f"  CANONICAL FLOOR = {len(mandatory)} mandatory + {len(universal_primaries)} universal-primary vertical = {floor}")
        print(f"  (Run department-floor.py --json to verify a live client install)")
        print("=" * 64)
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
