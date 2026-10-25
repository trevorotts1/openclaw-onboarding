#!/usr/bin/env python3
"""Execute the cross-flavor acceptance fixtures and write exact-head receipts.

One parameterized fixture set, one process per flavor:

    onboarding (ONB)  executes now against this repository's skill root
    999 (N999)        executes when its candidate skill root carries the shared
                      contracts; until then it records UNAVAILABLE with every
                      source path it checked named. It never records a pass.

Every facet is executed with a negative control, and a control that stays green
fails the run. That is the anti-vacuity gate the project has been missing.

Usage:
    python3 run_acceptance.py                       # both flavors, receipts to evidence/acceptance
    python3 run_acceptance.py --flavors onboarding
    python3 run_acceptance.py --checker "opus-chain reviewer <name>" --acceptance
    python3 run_acceptance.py --n999-skill-root /path/to/999/skill

Exit codes: 0 harness completed (UNAVAILABLE is reported, not hidden);
            1 a flavor executed and FAILED; 2 harness could not run.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import acceptance_fixtures as F  # noqa: E402
import receipt as R  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
RUNNER = os.path.join(HERE, "facet_runner.py")


def _git(repo, *args):
    proc = subprocess.run(["git", "-C", repo] + list(args),
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _first_existing(paths):
    for path in paths:
        if path and os.path.isdir(path):
            return path
    return None


def resolve_flavors(repo_root, args, order):
    """Map each contract flavor to a candidate skill root; keep every path checked."""
    skill_rel = os.path.join(".claude", "skills", "drama-song-ad-factory")
    n999_candidates = [
        args.n999_skill_root,
        os.environ.get("S75_999_SKILL_ROOT"),
        os.path.join(os.path.dirname(repo_root), "999-setup", skill_rel),
        os.path.join(os.path.expanduser("~"), "999-setup", skill_rel),
    ]
    out = {}
    for flavor in order:
        if flavor == "onboarding":
            onb_candidates = [args.onb_skill_root, os.path.join(repo_root, "75-drama-song-ad-factory")]
            out[flavor] = {
                "skill_root": _first_existing(onb_candidates),
                "sources_checked": [p for p in onb_candidates if p],
            }
        else:
            out[flavor] = {
                "skill_root": _first_existing(n999_candidates),
                "sources_checked": [p for p in n999_candidates if p],
            }
    return out


def run_flavor(flavor, flavor_info):
    if not flavor_info["skill_root"]:
        return {
            "status": "UNAVAILABLE",
            "reason": "no candidate skill root exists for this flavor",
            "missing_sources_checked": flavor_info["sources_checked"],
            "facets": [],
        }
    proc = subprocess.run(
        [sys.executable, RUNNER, "--skill-root", flavor_info["skill_root"],
         "--flavor", flavor, "--facet", "all"],
        capture_output=True, text=True)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {"status": "ERROR", "reason": "facet_runner produced no JSON",
                   "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-2000:]}
    payload["runner_exit_code"] = proc.returncode
    if proc.returncode not in (0, 1, 2):
        payload["status"] = "ERROR"
        payload["reason"] = payload.get("reason") or proc.stderr[-2000:]
    return payload


def _repo_state(path):
    """(head, branch, clean) for the git repository containing `path`."""
    if not path:
        return None, None, None
    probe = path if os.path.isdir(path) else os.path.dirname(path)
    while probe and not os.path.isdir(probe):
        probe = os.path.dirname(probe)
    _, head, _ = _git(probe, "rev-parse", "HEAD")
    _, branch, _ = _git(probe, "rev-parse", "--abbrev-ref", "HEAD")
    _, dirty, _ = _git(probe, "status", "--porcelain", "--untracked-files=no")
    if not head:
        return None, None, None
    return head, branch, not bool(dirty)


def build_receipt(flavor, repo_root, args, payload, contracts, flavor_info):
    _, head, _ = _git(repo_root, "rev-parse", "HEAD")
    _, branch, _ = _git(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    _, base_commit, _ = _git(repo_root, "rev-parse", args.base_ref)
    # A file that records its own commit cannot be committed inside that
    # commit. Record the head the facets actually ran at and say so; the unit
    # receipt carries the pushed head alongside it.
    expected = args.candidate
    if expected and expected != head:
        raise SystemExit("--candidate %s does not match this checkout's HEAD %s"
                         % (expected, head))
    status = payload.get("status")
    if flavor == "onboarding":
        candidate_head, candidate_branch, candidate_clean = head, branch, _repo_state(repo_root)[2]
    else:
        candidate_head, candidate_branch, candidate_clean = _repo_state(
            flavor_info.get("skill_root") or next(iter(flavor_info["sources_checked"]), None))
    checkout_head = candidate_head
    if status == "UNAVAILABLE":
        candidate_head = None  # no executed candidate skill root; null, never the harness head
    head_verified = candidate_head is not None

    facets = payload.get("facets") or []
    executed = []
    for facet in facets:
        executed.append({
            "facet": facet["facet"],
            "ok": facet["ok"],
            "checks": len(facet["checks"]),
            "negative_control": facet["control"],
            "reason": facet["reason"],
        })
    facets_green = sum(1 for f in facets if f["ok"])
    facets_red = len(facets) - facets_green
    controls_red = sum(1 for f in facets if f["control"]["control_red"])
    controls_green = len(facets) - controls_red

    # The nine S75-A32 cells. They are recorded even when the flavour has no
    # candidate: an executing cell with an honest NOT_APPLICABLE is evidence,
    # an empty list is not.
    cells = payload.get("cells") or []
    cell_counts = {"cells_total": len(cells),
                   "cells_pass": sum(1 for c in cells
                                     if c.get("status") == "OBSERVED_PASS"),
                   "cells_fail": sum(1 for c in cells
                                     if c.get("status") == "OBSERVED_FAIL"),
                   "cells_not_applicable": sum(1 for c in cells
                                               if c.get("status") == "NOT_APPLICABLE")}
    cell_not_executed = []
    for cell in cells:
        control = cell.get("negative_control") or {}
        if cell.get("status") == "NOT_APPLICABLE":
            na = cell.get("not_applicable") or {}
            cell_not_executed.append({
                "facet": "cell:%s" % cell["behavior"],
                "reason": "capability not present in this repository: %s; owed by %s"
                          % (na.get("missing_capability"), na.get("owed_by")),
                "class": "NOT_MODELLED_BY_CONTRACTS",
            })
            continue
        executed.append({
            "facet": "cell:%s" % cell["behavior"],
            "ok": cell.get("status") == "OBSERVED_PASS",
            "checks": max(1, len(cell.get("checks") or [])),
            "negative_control": {
                "unmet_condition": control.get("unmet_condition"),
                "facet_ok_on_unmet": control.get("observed"),
                "control_red": control.get("control_red"),
            },
            "reason": "; ".join((cell.get("observations") or [])[:2])[:400],
        })

    status = payload.get("status")
    if status == "PASS" and (facets_red or controls_green
                             or cell_counts["cells_fail"]):
        status = "FAIL"
    not_executed = []
    if status == "UNAVAILABLE":
        missing = payload.get("missing_sources_checked") or []
        for facet in F.RECEIPT_FACETS:
            not_executed.append({
                "facet": facet,
                "reason": "candidate skill root lacks the shared contracts; sources checked: "
                          + ", ".join(missing),
                "class": "CANDIDATE_NOT_LANDED",
            })
    for row in cell_not_executed:
        row["class"] = ("CANDIDATE_NOT_LANDED" if status == "UNAVAILABLE"
                        else "NOT_MODELLED_BY_CONTRACTS")
        not_executed.append(row)
    not_executed = R.with_coverage_gaps(not_executed, F.NOT_COVERED)

    return R.build(
        flavor=flavor,
        repository=contracts.get("repository", "unknown"),
        candidate={
            "repository": contracts.get("repository"),
            "commit": candidate_head,
            "branch": candidate_branch,
            "checkout_commit": checkout_head,
            "head_verified_at_execution": head_verified,
            "worktree_clean_excluding_receipts": candidate_clean,
            "filing_note": ("this commit is the head the facets executed at; the "
                            "commit that files this receipt is its child and "
                            "changes only this receipt"),
        },
        harness={"repository": "trevorotts1/openclaw-onboarding",
                 "commit": head, "branch": branch},
        base={"repository": "trevorotts1/openclaw-onboarding",
              "ref": args.base_ref, "commit": base_commit},
        contracts={
            "skill_root": payload.get("skill_root") or (contracts.get("skill_root")),
            "core_module": "scripts/core/story_first_contracts.py",
            "adapter_module": "scripts/core/package_flavor_adapter.py",
            "seam": payload.get("seam"),
            "core_digest": payload.get("core_digest"),
            "core_schema_version": payload.get("core_schema_version"),
            "stage_count": payload.get("stage_count"),
            "file_digests": payload.get("contract_digests") or {},
        },
        dependencies={"python": payload.get("python"), "network": "none",
                      "model_calls": "none", "spend": "none"},
        executed=executed,
        not_executed=not_executed,
        literal_binding={
            "seam": payload.get("seam") or "package_flavor_adapter.resolve",
            "contract_module": "scripts/core/story_first_contracts.py",
            "contract_files": list(F.REQUIRED_CONTRACT_FILES),
        },
        checks=dict(facets_green=facets_green, facets_red=facets_red,
                    controls_red=controls_red, controls_green=controls_green,
                    **cell_counts),
        execution_verdict=status if status in ("PASS", "FAIL", "UNAVAILABLE") else "FAIL",
        unaffected_proof={
            "method": "one subprocess and one receipt per flavor; each flavor loads only its own "
                      "scripts/core, so neither flavor's absence can block or contaminate the other",
            "this_flavor_executed": [f["facet"] for f in facets],
            "cross_flavor_blocking": False,
            "note": "S75-A36 and S75-A37 require each release to proceed without the other flavor's fixtures",
        },
        coverage=F.coverage(),
        author=args.author,
        checker=args.checker,
        cells=cells,
    )


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=REPO_ROOT)
    parser.add_argument("--flavors", default="onboarding,999")
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--candidate", default=None,
                        help="expected candidate commit; receipt marks head_verified false when it differs")
    parser.add_argument("--onb-skill-root", default=None)
    parser.add_argument("--n999-skill-root", default=None)
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--author", default="S75-T32 builder (deepseek-chain)")
    parser.add_argument("--checker", default=None,
                        help="identity of the executing independent checker; omit to leave acceptance PENDING")
    args = parser.parse_args(argv)

    repo_root = os.path.abspath(args.repo_root)
    order = [f.strip() for f in args.flavors.split(",") if f.strip()]
    unknown = [f for f in order if f not in ("onboarding", "999")]
    if unknown:
        print("unknown flavor(s): %s" % unknown, file=sys.stderr)
        return 2

    # Flavor names are the adapter's own contract, not a second list.
    onb_root = _first_existing([args.onb_skill_root,
                                os.path.join(repo_root, "75-drama-song-ad-factory")])
    if not onb_root:
        print("onboarding skill root not found", file=sys.stderr)
        return 2
    ctx = F.load_package(onb_root)
    contract_flavors = list(ctx.adapter.FLAVORS)
    missing_order = [f for f in order if f not in contract_flavors]
    if missing_order:
        print("flavor(s) not declared by package_flavor_adapter.FLAVORS: %s" % missing_order,
              file=sys.stderr)
        return 2

    out_dir = args.out_dir or os.path.join(repo_root, "evidence", "acceptance")
    flavors = resolve_flavors(repo_root, args, order)
    repositories = {
        "onboarding": "trevorotts1/openclaw-onboarding",
        "999": "trevorotts1/999-setup",
    }

    failures = 0
    written = []
    for flavor in order:
        payload = run_flavor(flavor, flavors[flavor])
        receipt = build_receipt(flavor, repo_root, args, payload, {
            "repository": repositories[flavor],
            "skill_root": flavors[flavor]["skill_root"],
        }, flavors[flavor])
        path = R.write(os.path.join(out_dir, "%s.json" % flavor), receipt)
        written.append(path)
        verdict = receipt["execution"]["verdict"]
        print("%-10s %-11s facets %d green / %d red, controls %d red / %d green; "
              "cells %d executed (%d pass / %d fail / %d not-applicable) -> %s"
              % (flavor, verdict,
                 receipt["checks"]["facets_green"], receipt["checks"]["facets_red"],
                 receipt["checks"]["controls_red"], receipt["checks"]["controls_green"],
                 receipt["checks"]["cells_total"],
                 receipt["checks"]["cells_pass"], receipt["checks"]["cells_fail"],
                 receipt["checks"]["cells_not_applicable"], path))
        if verdict == "FAIL":
            failures += 1
        if verdict == "UNAVAILABLE":
            print("           UNAVAILABLE is reported, never converted to a pass: %s"
                  % (payload.get("missing_sources_checked") or payload.get("reason")))

    print("\nreceipts: %s" % ", ".join(written))
    print("acceptance verdicts require a named independent checker; author alone leaves PENDING_INDEPENDENT_CHECK")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
