#!/usr/bin/env python3
"""Exact-head receipt format for cross-flavor acceptance (S75-T32).

The ledger's gap is named independent checking, so the receipt cannot be a
green line: it must carry the candidate head, the base it was cut from, what
ran, what did NOT run, and WHO checked it. A self-issued PASS is refused by
`validate` — the builder can record an execution result, never an acceptance.

Top-level shape (see receipt.schema.json):

    receipt_version, unit_id, flavor, repository,
    candidate{commit,branch,head_verified,worktree_clean},
    base{ref,commit}, contracts{...}, dependencies{...},
    executed[], not_executed[],
    literal_binding{...}, checks{...},
    execution{verdict,...}, coverage{...},
    author, acceptance{verdict,checker,checker_distinct_from_author}

Stdlib only.
"""
from __future__ import annotations

import json
import os
import re

RECEIPT_VERSION = "s75.cross_flavor.receipt.v1"
EXECUTION_VERDICTS = ("PASS", "FAIL", "UNAVAILABLE")
ACCEPTANCE_VERDICTS = ("PASS", "FAIL", "PENDING_INDEPENDENT_CHECK", "UNAVAILABLE")
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_REQUIRED = (
    "receipt_version", "unit_id", "flavor", "repository", "candidate", "base",
    "harness", "contracts", "dependencies", "executed", "not_executed",
    "literal_binding", "checks", "execution", "unaffected_proof", "coverage",
    "author", "acceptance",
)


class ReceiptError(Exception):
    pass


def build(*, flavor, repository, candidate, harness, base, contracts,
          dependencies, executed, not_executed, literal_binding, checks,
          execution_verdict, unaffected_proof, coverage, author, checker=None,
          generated_at=None):
    """Assemble and validate one receipt. Refuses a self-issued PASS."""
    receipt = {
        "receipt_version": RECEIPT_VERSION,
        "unit_id": "S75-T32",
        "flavor": flavor,
        "repository": repository,
        "generated_at": generated_at or _now(),
        "candidate": candidate,
        "base": base,
        "harness": harness,
        "contracts": contracts,
        "dependencies": dependencies,
        "executed": executed,
        "not_executed": not_executed,
        "literal_binding": literal_binding,
        "checks": checks,
        "execution": {"verdict": execution_verdict},
        "unaffected_proof": unaffected_proof,
        "coverage": coverage,
        "author": author,
        "acceptance": {
            "verdict": _acceptance_verdict(execution_verdict, checker, author),
            "checker": checker,
            "checker_distinct_from_author": (
                None if checker is None else checker.strip() != author.strip()),
        },
    }
    validate(receipt)
    return receipt


def _now():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _acceptance_verdict(execution_verdict, checker, author):
    if execution_verdict != "PASS":
        return execution_verdict
    if checker is None or checker.strip() == "" or checker.strip() == author.strip():
        return "PENDING_INDEPENDENT_CHECK"
    return "PASS"


def validate(receipt):
    """Return None when valid; raise ReceiptError listing every defect."""
    defects = []
    for key in _REQUIRED:
        if key not in receipt:
            defects.append("missing %s" % key)
    if defects:
        raise ReceiptError("; ".join(defects))

    candidate = receipt["candidate"] or {}
    base = receipt["base"] or {}
    harness = receipt["harness"] or {}
    execution = (receipt.get("execution") or {}).get("verdict")
    if execution not in EXECUTION_VERDICTS:
        defects.append("execution.verdict must be one of %s" % (EXECUTION_VERDICTS,))
    if not _HEX40.match(str(harness.get("commit", ""))):
        defects.append("harness.commit must be a full 40-hex commit naming the fixtures that ran")
    if not _HEX40.match(str(base.get("commit", ""))):
        defects.append("base.commit must be a full 40-hex commit")
    if execution == "UNAVAILABLE":
        # No candidate skill root existed; the candidate commit is explicitly null.
        if candidate.get("commit") is not None:
            defects.append("UNAVAILABLE must record candidate.commit as null, not the harness head")
        if candidate.get("head_verified_at_execution") is not False:
            defects.append("UNAVAILABLE must record head_verified_at_execution as false")
    else:
        if not _HEX40.match(str(candidate.get("commit", ""))):
            defects.append("candidate.commit must be a full 40-hex commit")
        if candidate.get("head_verified_at_execution") is not True:
            defects.append("candidate.head_verified_at_execution must be true; a receipt about another head does not count")

    checks = receipt["checks"] or {}
    if execution == "PASS":
        if not receipt["executed"]:
            defects.append("execution PASS requires at least one executed facet")
        if checks.get("facets_red", 0) != 0:
            defects.append("execution PASS with facets_red=%r" % checks.get("facets_red"))
        if checks.get("controls_green", 0) != 0:
            defects.append("execution PASS with negative controls that stayed green")
    if execution == "UNAVAILABLE" and not receipt["not_executed"]:
        defects.append("UNAVAILABLE requires not_executed to name what did not run and why")

    acceptance = receipt.get("acceptance") or {}
    verdict = acceptance.get("verdict")
    if verdict not in ACCEPTANCE_VERDICTS:
        defects.append("acceptance.verdict must be one of %s" % (ACCEPTANCE_VERDICTS,))
    if verdict == "PASS":
        checker = (acceptance.get("checker") or "").strip()
        if not checker:
            defects.append("acceptance PASS requires the executing checker's identity")
        if acceptance.get("checker_distinct_from_author") is not True:
            defects.append("acceptance PASS requires a checker distinct from the author")
        if checker and checker == (receipt.get("author") or "").strip():
            defects.append("author cannot be its own acceptance checker")
    unaffected = receipt.get("unaffected_proof") or {}
    if not unaffected.get("method"):
        defects.append("unaffected_proof.method must say how flavors stay independent")
    if unaffected.get("cross_flavor_blocking") is not False:
        defects.append("unaffected_proof.cross_flavor_blocking must be false: one flavor's absence "
                       "cannot hold the other's facets")
    if any(not item.get("reason") for item in receipt["not_executed"]):
        defects.append("every not_executed entry needs a reason")
    if defects:
        raise ReceiptError("; ".join(defects))
    return None


def with_coverage_gaps(not_executed, gaps):
    """Append one not_executed row per criterion the contracts do not state."""
    out = list(not_executed)
    for criterion, reason in sorted(gaps.items()):
        out.append({"facet": criterion, "reason": "not stated by the shared contracts: " + reason,
                    "class": "NOT_MODELLED_BY_CONTRACTS"})
    return out


def write(path, receipt):
    """Validate then write one receipt. Refuses on any defect."""
    validate(receipt)
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path
