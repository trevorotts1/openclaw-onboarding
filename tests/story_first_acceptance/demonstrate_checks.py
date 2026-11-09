#!/usr/bin/env python3
"""Show every narrowed S75-A32 cell PASSING and FAILING, for each flavor facet.

This is the demonstration, not the test suite. For each of the seven narrowed
behaviours in each requested flavor it prints the observation that passes and
the observation that fails. A cell with no red side is a line in a list; this
script refuses to call it a check.

The FAIL side is where the cell keeps it: every executed cell carries a
negative control -- the same code path driven with its condition deliberately
unmet -- and ``control_red`` is the observation that the control actually went
red. Cells that could not execute (a flavor whose package anchor is not
provisioned) are reported UNAVAILABLE and never counted as demonstrated.

Usage:
    python3 demonstrate_checks.py [--json] [--flavors onboarding[,999]]
                                  [--repo-root PATH]

Exit: 0 every requested cell executed and demonstrated both sides;
      1 a cell exists with no demonstrated failure side, or a flavor ran
        nothing it could demonstrate.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cell_matrix as C  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
FLAVORS = ("onboarding", "999")


def _rows(repo_root, flavors):
    out = []
    for flavor in flavors:
        target = C.facet_target(flavor, repo_root)
        cells = C.run_cells(target)
        for cell in cells:
            passed = sum(1 for c in cell["checks"] if c["result"])
            control = cell["negative_control"] or {}
            row = {
                "flavor": flavor,
                "behavior": cell["behavior"],
                "pass_status": cell["status"],
                "checks_passed": passed,
                "checks_total": len(cell["checks"]),
                "root_source": target.root_source,
                "fail_status": "negative control",
                "pass_evidence": (
                    "%d/%d checks pass on the production code at %s"
                    % (passed, len(cell["checks"]), target.root_source)),
                "fail_evidence": (
                    "unmet condition: %s -> observed=%s, control_red=%s"
                    % (control.get("unmet_condition"), control.get("observed"),
                       control.get("control_red"))),
                "failable": (
                    cell["executed"] is True
                    and cell["status"] == C.OBSERVED_PASS
                    and cell["known_good_control"]["pass"] is True
                    and bool(cell["checks"])
                    and all(c["result"] for c in cell["checks"])
                    and control.get("control_red") is True),
            }
            if not cell["executed"] or not cell["checks"]:
                row["fail_status"] = "UNAVAILABLE"
            out.append(row)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--flavors", default=",".join(FLAVORS))
    parser.add_argument("--repo-root", default=REPO_ROOT)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    flavors = tuple(f.strip() for f in args.flavors.split(",") if f.strip())
    unknown = [f for f in flavors if f not in FLAVORS]
    if unknown:
        parser.error("unknown flavor(s) %r; choose from %r" % (unknown, FLAVORS))

    rows = _rows(args.repo_root, flavors)
    demonstrated = [r for r in rows if r["failable"]]
    all_demonstrated = (
        bool(rows) and len(demonstrated) == len(rows)
        and set(flavors) <= {r["flavor"] for r in rows})

    if args.json:
        json.dump({"rows": rows, "all_demonstrated": all_demonstrated},
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
              % (len(rows), len(demonstrated)))
    return 0 if all_demonstrated else 1


if __name__ == "__main__":
    sys.exit(main())
