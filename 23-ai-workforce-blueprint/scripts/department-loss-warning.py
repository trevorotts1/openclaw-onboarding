#!/usr/bin/env python3
"""
department-loss-warning.py — the ONE reader for a floor department's opt-out
"here's what you lose without X" warning (P2-05 step 1).

WHY THIS EXISTS:
The interview lets an owner DECLINE a floor department (a provenanced "no",
honored by canonical_decline.py). Before that opt-out is recorded, the interview
MUST show the owner what they give up — a one-line loss_warning authored per
floor department in department-naming-map.json. record-dept-decision.sh calls
THIS reader so the warning text has a single source of truth (the naming map)
and can never drift from a hand-copied string in the writer.

A "floor department" is one of the 29 the floor guarantees: the 23 mandatory
canonical depts (nm.mandatory) + the 6 universal-primary vertical-pack depts
(one per pack flagged universal_primary=true). ONLY those carry a loss_warning;
a keyword-matched industry extra or a custom department is NOT a floor dept and
returns no warning (rc=3) — declining a non-floor dept costs no guaranteed
functionality, so no confirmation is required for it.

Slug comparison is normalization-insensitive (delegates to canonical_decline.norm
so 'Video', 'billing_finance', 'billing-finance' all resolve identically).

USAGE
  python3 department-loss-warning.py --dept billing-finance
  python3 department-loss-warning.py --dept billing-finance --json

EXIT CODES
  0  a floor dept with a loss_warning was found (text printed to stdout)
  2  bad usage (no --dept)
  3  the dept is CONCLUSIVELY not a floor dept, or a floor dept carries no
     loss_warning — determined against a READABLE, structurally-valid naming map
     (either way: nothing to confirm — the caller may proceed without a warning)
  4  INDETERMINATE: the naming map could not be read/parsed, or it is
     structurally unusable for floor determination (no populated `mandatory`
     section). Floor status is UNKNOWN — the caller must NOT treat this as
     "non-floor / proceed". It must fail closed (refuse the decline unless the
     owner explicitly overrides), because a real floor department under an
     unreadable map would otherwise masquerade as a non-floor dept (rc=3) and
     its opt-out would be dropped silently. This mirrors department-floor.py,
     which fails CLOSED to the full 28 floor on an unreadable map (OQ-7).

Read-only. Never writes. Import-safe: `from department_loss_warning import
loss_warning_for` (after adding the scripts dir to sys.path).
"""

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
NAMING_MAP = SKILL_DIR / "department-naming-map.json"

if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from canonical_decline import norm as _norm  # noqa: E402


def load_naming_map(path=None):
    p = Path(path) if path else NAMING_MAP
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def naming_map_is_usable(nm):
    """True only when the map is structurally usable for FLOOR determination: it
    must be a dict carrying a populated `mandatory` object. A missing/empty/
    non-dict `mandatory` means we cannot know the 23 mandatory floor depts, so
    floor status is UNKNOWN and rc=3 ('conclusively non-floor') would be a lie.
    A healthy naming map always ships a populated `mandatory` section."""
    if not isinstance(nm, dict):
        return False
    mand = nm.get("mandatory")
    return isinstance(mand, dict) and len(mand) > 0


def _floor_warnings(nm):
    """Return {normalized_slug: (raw_id, loss_warning)} for every FLOOR dept that
    carries a loss_warning — the 23 mandatory + the 6 universal-primary depts."""
    out = {}
    for did, dept in (nm.get("mandatory") or {}).items():
        if not isinstance(dept, dict):
            continue
        lw = dept.get("loss_warning")
        if lw:
            out[_norm(did)] = (did, lw)
    for pack in (nm.get("vertical_packs") or {}).values():
        if not isinstance(pack, dict):
            continue
        for dept in pack.get("auto_add_departments", []) or []:
            if not isinstance(dept, dict):
                continue
            # ONLY the universal-primary dept of a pack is a floor dept.
            if not dept.get("universal_primary"):
                continue
            did = dept.get("id")
            lw = dept.get("loss_warning")
            if did and lw:
                out.setdefault(_norm(did), (did, lw))
    return out


def loss_warning_for(dept_id, nm=None, naming_map_path=None):
    """Return the loss_warning string for a floor dept, or None if the dept is
    not a floor dept / carries no warning. Normalization-insensitive."""
    nm = nm if nm is not None else load_naming_map(naming_map_path)
    entry = _floor_warnings(nm).get(_norm(dept_id))
    return entry[1] if entry else None


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Print a floor department's opt-out loss_warning (single source: "
                    "department-naming-map.json). Empty/rc=3 for non-floor depts.")
    ap.add_argument("--dept", help="canonical/universal-primary department id")
    ap.add_argument("--naming-map", help="override path to department-naming-map.json (testing)")
    ap.add_argument("--json", action="store_true", help="emit a machine-readable object")
    args = ap.parse_args(argv)

    if not args.dept:
        print("ERROR: --dept <id> is required", file=sys.stderr)
        return 2

    nm = load_naming_map(args.naming_map)
    # Fail-closed: if the map is unreadable/unparseable/structurally-unusable we
    # CANNOT determine floor status. Return rc=4 (INDETERMINATE) rather than
    # rc=3 — the caller must not mistake "can't read the floor" for "not a floor
    # dept". (See OQ-7 / department-floor.py, which fails closed to full 28.)
    if not naming_map_is_usable(nm):
        if args.json:
            print(json.dumps({
                "dept": args.dept,
                "is_floor_department": None,
                "loss_warning": None,
                "indeterminate": True,
                "reason": "department-naming-map.json unreadable/unparseable/"
                          "missing populated `mandatory` — floor status unknown",
            }, ensure_ascii=False, indent=2))
        else:
            print("INDETERMINATE: department-naming-map.json is unreadable/"
                  "unparseable or missing its `mandatory` floor section — cannot "
                  "determine floor status.", file=sys.stderr)
        return 4

    warning = loss_warning_for(args.dept, nm=nm)
    if args.json:
        print(json.dumps({
            "dept": args.dept,
            "is_floor_department": warning is not None,
            "loss_warning": warning,
        }, ensure_ascii=False, indent=2))
    elif warning is not None:
        print(warning)

    return 0 if warning is not None else 3


if __name__ == "__main__":
    sys.exit(main())
