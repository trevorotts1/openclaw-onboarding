#!/usr/bin/env python3
"""Run one cross-flavor acceptance facet AND the nine S75-A32 cells, in isolation.

Isolation is deliberate: each flavor runs in its own process with only its own
`scripts/core` on sys.path, so an ONB facet can never pick up an N999 module or
the reverse. That is also the evidence that each facet releases its own
repository (S75-A32 / S75-A36, S75-A37).

The nine cells run whether or not the shared contracts are present: a cell that
runs nothing is absence of evidence, so a flavour without the contracts still
records, for every cell, what its probe observed and which unit owes the
capability it lacks.

Usage:
    python3 facet_runner.py --skill-root <root> --flavor onboarding --facet all
    python3 facet_runner.py --skill-root <root> --flavor 999 --repository owner/repo

Exit codes:
    0  every requested facet green AND every negative control red
    1  a facet or a cell failed, or a control stayed green (vacuous fixture)
    2  unavailable: contract files absent from this skill root (named in output)
No network, no writes, no model calls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import acceptance_fixtures as F  # noqa: E402
import cell_matrix as C  # noqa: E402


def _digest(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def contract_digests(skill_root):
    out = {}
    for rel in F.REQUIRED_CONTRACT_FILES:
        path = os.path.join(skill_root, rel)
        out[rel] = _digest(path) if os.path.isfile(path) else None
    return out


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill-root", required=True)
    parser.add_argument("--flavor", required=True)
    parser.add_argument("--repository", default=None,
                        help="the repository this skill root belongs to")
    parser.add_argument("--facet", default="all")
    args = parser.parse_args(argv)

    skill_root = os.path.abspath(args.skill_root)
    repository = args.repository or ("trevorotts1/openclaw-onboarding"
                                     if args.flavor == "onboarding"
                                     else "trevorotts1/999-setup")
    target = C.Target(args.flavor, repository, skill_root)

    # Always execute the cells, even when the contracts are absent: the cell
    # record is the observation, and an absence is one of the observations.
    cells = C.run_cells(target)
    cell_counts = C.counts(cells)

    absent = F.missing_contract_files(skill_root)
    if absent:
        json.dump({
            "flavor": args.flavor,
            "repository": repository,
            "skill_root": skill_root,
            "status": "UNAVAILABLE",
            "reason": "candidate skill root does not yet carry the shared contracts",
            "missing_sources_checked": absent,
            "cells": cells,
            "cell_counts": cell_counts,
        }, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 2

    ctx = F.load_package(skill_root)
    facets = list(F.RECEIPT_FACETS) if args.facet == "all" else [args.facet]
    unknown = [f for f in facets if f not in F.FACET_FUNCTIONS]
    if unknown:
        json.dump({"status": "ERROR", "unknown_facets": unknown,
                   "known": list(F.FACET_FUNCTIONS)}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1

    results = [F.run_facet(ctx, facet) for facet in facets]
    ok = all(r["ok"] and r["control"]["control_red"] for r in results)
    cells_ok = cell_counts["cells_fail"] == 0
    json.dump({
        "flavor": args.flavor,
        "repository": repository,
        "skill_root": skill_root,
        "status": "PASS" if (ok and cells_ok) else "FAIL",
        "seam": ctx.adapter.SEAM,
        "core_digest": ctx.adapter.core_digest(),
        "core_schema_version": ctx.core.SCHEMA_VERSION,
        "stage_count": len(ctx.core.STAGE_ORDER),
        "python": platform.python_version(),
        "contract_digests": contract_digests(skill_root),
        "facets": results,
        "cells": cells,
        "cell_counts": cell_counts,
        "coverage": F.coverage(),
    }, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0 if (ok and cells_ok) else 1


if __name__ == "__main__":
    sys.exit(main())
