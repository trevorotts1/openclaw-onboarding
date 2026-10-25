#!/usr/bin/env python3
"""Show every S75-A32 check PASSING and FAILING, for both flavor facets.

This is the demonstration, not the test suite. For each of the nine behaviours
in each of the two flavors it prints the observation that passes and the
observation that fails, and exits non-zero if any check has only one of them.
A check with no red side is a line in a list; this script refuses to call it a
check.

The FAIL side is taken from where the cell keeps it:
  * the seven contract/style/byte cells carry a negative control -- the same
    code path driven with its condition deliberately unmet;
  * the two dependency cells carry both sides of their declared protocol, a
    conforming provider (pass) and a broken one (fail), because their production
    modules are still unmerged and are owned by S75-T17 and S75-T28.

Usage:
    python3 demonstrate_checks.py [--json]

Exit: 0 every one of the eighteen cells demonstrated both sides;
      1 a check exists with no demonstrated failure.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cell_matrix as C  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
FLAVORS = ("onboarding", "999")
DEPENDENCY = ("Notion migration", "paid compatibility")

def _rows():
    out = []
    for flavor in FLAVORS:
        target = C.facet_target(flavor, REPO_ROOT)
        reference = C.run_cells(target)
        broken = C.run_cells(target, broken=True)
        broken_by = {c["behavior"]: c for c in broken}
        for cell in reference:
            behavior = cell["behavior"]
            passed = sum(1 for c in cell["checks"] if c["result"])
            row = {
                "flavor": flavor,
                "behavior": behavior,
                "pass_status": cell["status"],
                "checks_passed": passed,
                "checks_total": len(cell["checks"]),
            }
            if behavior in DEPENDENCY:
                exercise = cell["exercise"]
                row["fail_status"] = broken_by[behavior]["status"]
                row["pass_evidence"] = (
                    "conforming provider: %d/%d protocol checks pass "
                    "(root_source=%s, production carrier absent, owed by %s)"
                    % (sum(1 for c in exercise["checks"] if c["result"]),
                       len(exercise["checks"]), target.root_source,
                       cell["not_applicable"]["owed_by"]))
                row["fail_evidence"] = (
                    "broken provider: %d/%d protocol checks fail -> %s"
                    % (sum(1 for c in broken_by[behavior]["checks"] if not c["result"]),
                       len(broken_by[behavior]["checks"]),
                       broken_by[behavior]["status"]))
                row["failable"] = (
                    exercise["reference_ok"] is True
                    and exercise["broken_ok"] is False
                    and broken_by[behavior]["status"] == "OBSERVED_FAIL")
            else:
                control = cell["negative_control"]
                row["fail_status"] = "%s (negative control)" % cell["status"]
                row["pass_evidence"] = (
                    "%d/%d checks pass on the production code at %s"
                    % (passed, len(cell["checks"]), target.root_source))
                row["fail_evidence"] = (
                    "unmet condition: %s -> facet_ok_on_unmet=%s, control_red=%s"
                    % (control.get("unmet_condition"), control.get("observed"),
                       control.get("control_red")))
                row["failable"] = control.get("control_red") is True
            out.append(row)
    return out

def main(argv=None):
    as_json = "--json" in (argv if argv is not None else sys.argv[1:])
    rows = _rows()
    if as_json:
        json.dump({"rows": rows,
                   "all_demonstrated": all(r["failable"] for r in rows)},
                  sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print("%-11s %-28s %-16s %-6s %s" % (
            "flavor", "check", "pass", "fail?", "fail side"))
        for row in rows:
            print("%-11s %-28s %-16s %-6s %s" % (
                row["flavor"], row["behavior"], row["pass_status"],
                "yes" if row["failable"] else "NO", row["fail_evidence"]))
        print()
        print("%d cells, %d with a demonstrated failure side"
              % (len(rows), sum(1 for r in rows if r["failable"])))
    return 0 if all(r["failable"] for r in rows) else 1

if __name__ == "__main__":
    sys.exit(main())
