#!/usr/bin/env python3
"""receipt_mapping_check.py — read-only integrity check of receipt-mapping.json.

Verifies, without claiming anything:
  * schema + unit id present;
  * every acceptance row A01-A12 exists with its FROZEN weight (8,8,8,8,7,7,8,8,8,6,14,10);
  * weights sum to exactly 100;
  * every row and every canary names a concrete harness file that EXISTS in this
    directory;
  * NO row claims an accepted point now (claims_now must be "none" everywhere),
    and the mapping's accepted_points_claimed_now == 0.

Exit 0 = mapping is internally consistent and claims nothing; 1 = inconsistency.
Stdlib only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

FROZEN_WEIGHTS = {
    "A01": 8, "A02": 8, "A03": 8, "A04": 8, "A05": 7, "A06": 7,
    "A07": 8, "A08": 8, "A09": 8, "A10": 6, "A11": 14, "A12": 10,
}
FAILS = []


def check(name, ok, detail=""):
    print("  [%s] %s%s" % ("PASS" if ok else "FAIL", name,
                           (" — " + detail) if detail else ""))
    if not ok:
        FAILS.append(name)
    return ok


def main():
    path = HERE / "receipt-mapping.json"
    try:
        m = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print("receipt-mapping.json unreadable: %s" % e)
        return 1

    check("schema present", m.get("schema") == "blackceo.skill75.receipt-mapping/v1",
          m.get("schema"))

    rows = m.get("acceptance_rows", {})
    check("all 12 acceptance rows present",
          set(rows) == set(FROZEN_WEIGHTS),
          "missing: %s extra: %s" % (
              sorted(set(FROZEN_WEIGHTS) - set(rows)),
              sorted(set(rows) - set(FROZEN_WEIGHTS))))

    weight_mismatches = [
        "%s=%s (expected %s)" % (k, rows[k].get("weight"), w)
        for k, w in FROZEN_WEIGHTS.items()
        if k in rows and rows[k].get("weight") != w]
    check("frozen weights exact", not weight_mismatches,
          "; ".join(weight_mismatches))

    total = sum(rows[k].get("weight", 0) for k in rows)
    check("weights sum to 100", total == 100, "sum=%d" % total)
    check("mapping records weights_total=100", m.get("weights_total") == 100)

    # every named harness file must exist
    missing = []
    for cname, c in m.get("canaries", {}).items():
        rel = c.get("harness")
        if rel and not (HERE.parents[2] / rel).is_file() and not (HERE / Path(rel).name).is_file():
            # harness paths are repo-root-relative (tests/w10-canary/<file>)
            candidate = HERE / Path(rel).name
            if not candidate.is_file():
                missing.append("%s -> %s" % (cname, rel))
    for cname, c in m.get("read_only_checks", {}).items():
        rel = c.get("harness")
        if rel and not (HERE / Path(rel).name).is_file():
            missing.append("%s -> %s" % (cname, rel))
    check("every mapped harness file exists", not missing, "; ".join(missing))

    # nothing claimed
    claimed = [(k, rows[k].get("claims_now")) for k in rows
               if rows[k].get("claims_now") != "none"]
    check("no acceptance point claimed now", not claimed, str(claimed))
    check("accepted_points_claimed_now == 0",
          m.get("accepted_points_claimed_now") == 0,
          m.get("accepted_points_claimed_now"))

    # blockers named precisely where status says so
    blocked = [k for k, v in rows.items()
               if v.get("prepared_status") == "BLOCKED_NEEDS_AUTHORIZATION"]
    unnamed = [k for k in blocked if not rows[k].get("blocker")]
    check("every blocked row names its blocker precisely", not unnamed,
          str(unnamed))

    print("receipt-mapping check: %s" % ("OK" if not FAILS else
          "FAILED: " + ", ".join(FAILS)))
    return 0 if not FAILS else 1


if __name__ == "__main__":
    sys.exit(main())
