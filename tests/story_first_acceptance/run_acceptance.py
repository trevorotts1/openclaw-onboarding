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
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import acceptance_fixtures as F  # noqa: E402
import provenance  # noqa: E402
import receipt as R  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
RUNNER = os.path.join(HERE, "facet_runner.py")

_HEX40 = re.compile(r"^[0-9a-f]{40}$")

# The N999 side is pinned to a NAMED REVISION, never to a live working tree.
# Round 3 mis-measured six of nine N999 cells because this resolver walked into
# a checkout that sat 55 commits behind its own origin/main and reported it as
# the candidate. A path derived from a commit sha cannot do that: it is either
# provisioned at that revision or it does not exist.
# ponytail: one pin is enough while only one N999 revision is under measurement;
# upgrade to a pins manifest when a second revision must be judged side by side.
PINS = provenance.load_pins()
REPOSITORIES = {
    "onboarding": PINS["onboarding"]["repository"],
    "999": PINS["999"]["repository"],
}
N999_PIN_REPOSITORY = PINS["999"]["repository"]
N999_PIN_REVISION = PINS["999"]["revision"]
N999_PIN_ROOT = os.path.join(HERE, "pins", "999-setup", N999_PIN_REVISION)

# The harness writes its own receipts here. Its own output is not candidate
# drift, so it is excluded from the dirt check and the exclusion is recorded.
_INSTRUMENT_OUTPUT = os.path.join("evidence", "acceptance")


def _git(repo, *args):
    proc = subprocess.run(["git", "-C", repo] + list(args),
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _first_existing(paths):
    for path in paths:
        if path and os.path.isdir(path):
            return path
    return None


def _pinned_revision_of(path):
    """The 40-hex revision an extracted tree is named by, or None."""
    probe = path
    while probe and probe != os.path.dirname(probe):
        if _HEX40.match(os.path.basename(probe)):
            return os.path.basename(probe)
        probe = os.path.dirname(probe)
    return None


def revision_gate(root, expected_repository=None, pin=None):
    """Provenance of a resolved skill root. Refuses an unmeasurable one.

    A live working tree is mutable and can look like an ordinary directory while
    sitting 55 commits behind its own origin/main - the exact mechanism that
    mis-reported eight S75-A32 cells in round 3. So a root is measurable only if
    it is a pinned archive named by its revision, or a clean worktree whose HEAD
    is a revision that exists on origin. Anything else is REFUSED, and every
    reason is recorded here so the refusal cannot be silent.

    MEASURABLE IS NOT ATTRIBUTABLE. Round 4 minted a 999 release claim from a
    planted directory because the only identity test was os.path.isdir. The gate
    therefore also requires provenance.resolve to read a remote, a revision and
    a digest that match the declared repository before the root is usable.
    """
    gate = {"root": root, "status": "UNRESOLVED", "mode": None,
            "revision": None, "revision_source": None,
            "clean_excluding_instrument_output": None, "at_origin_main": None,
            "is_origin_revision": None, "violations": []}
    proof = provenance.resolve(root, expected_repository, pin)
    gate["provenance"] = proof
    if not proof["identity_proven"]:
        gate["violations"].extend(proof["refusals"])

    def _finish():
        if gate["violations"]:
            gate["status"] = "REFUSED"
        return gate

    if not root:
        gate["violations"].append("no candidate skill root resolved")
        return _finish()

    probe = root if os.path.isdir(root) else os.path.dirname(root)
    while probe and not os.path.isdir(probe):
        probe = os.path.dirname(probe)
    rc, top, _ = _git(probe, "rev-parse", "--show-toplevel")
    if rc != 0 or not top:
        gate["mode"] = "extracted_tree"
        revision = _pinned_revision_of(root)
        if revision:
            gate["revision"] = revision
            gate["revision_source"] = "directory name of the extracted tree"
            gate["status"] = "PINNED_REVISION"
        else:
            gate["violations"].append(
                "not inside a git worktree and no ancestor directory names a 40-hex "
                "revision; an extracted tree must be named by the revision it was cut from")
        return _finish()

    gate["mode"] = "git_worktree"
    _, head, _ = _git(probe, "rev-parse", "HEAD")
    gate["revision"] = head or None
    gate["revision_source"] = "git rev-parse HEAD in %s" % top
    _, status_out, _ = _git(top, "status", "--porcelain", "--untracked-files=no")
    dirty = [line for line in status_out.splitlines()
             if line.strip() and not line[3:].strip().startswith(_INSTRUMENT_OUTPUT + os.sep)]
    gate["clean_excluding_instrument_output"] = not dirty
    if dirty:
        gate["violations"].append(
            "worktree is dirty (%d tracked change(s), excluding %s): %s"
            % (len(dirty), _INSTRUMENT_OUTPUT,
               ", ".join(line.strip() for line in dirty[:5])))
    _, origin_main, _ = _git(top, "rev-parse", "--verify", "--quiet", "origin/main")
    gate["at_origin_main"] = bool(origin_main) and origin_main == head
    rc_c, contains, _ = _git(top, "branch", "-r", "--contains", head)
    gate["is_origin_revision"] = bool(gate["at_origin_main"]) or (rc_c == 0 and bool(contains))
    if not gate["is_origin_revision"]:
        gate["violations"].append(
            "HEAD %s is not origin/main and is not a revision that exists on origin"
            % (head or "<none>"))
    if not gate["violations"]:
        gate["status"] = "AT_ORIGIN_MAIN" if gate["at_origin_main"] else "ORIGIN_REVISION"
    return _finish()

def default_n999_candidates(args):
    """Every N999 root that may be used, in order. No live working tree is one."""
    skill_rel = os.path.join(".claude", "skills", "drama-song-ad-factory")
    return [
        args.n999_skill_root,
        os.environ.get("S75_999_SKILL_ROOT"),
        os.path.join(N999_PIN_ROOT, skill_rel),
    ]


def resolve_flavors(repo_root, args, order):
    """Map each contract flavor to a candidate skill root; gate and record provenance."""
    n999_candidates = default_n999_candidates(args)
    out = {}
    for flavor in order:
        if flavor == "onboarding":
            onb_candidates = [args.onb_skill_root, os.path.join(repo_root, "75-drama-song-ad-factory")]
        else:
            onb_candidates = n999_candidates
        root = _first_existing(onb_candidates)
        out[flavor] = {
            "skill_root": root,
            "sources_checked": [p for p in onb_candidates if p],
            "revision_gate": revision_gate(root, REPOSITORIES.get(flavor),
                                           PINS.get(flavor)),
        }
    return out


def run_flavor(flavor, flavor_info):
    gate = flavor_info.get("revision_gate") or {}
    if gate.get("status") == "REFUSED":
        # Refuse to measure, and say so where it cannot be missed.
        return {
            "status": "UNAVAILABLE",
            "reason": ("REFUSED - resolved skill root is not a measurable revision: "
                       + "; ".join(gate.get("violations") or ["unstated"])),
            "missing_sources_checked": flavor_info["sources_checked"],
            "revision_gate": gate,
            "facets": [],
        }
    if not flavor_info["skill_root"]:
        return {
            "status": "UNAVAILABLE",
            "reason": "no candidate skill root exists for this flavor",
            "missing_sources_checked": flavor_info["sources_checked"],
            "revision_gate": gate,
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
    # The repository label is not minted from the flavour name. It is the
    # repository the gate PROVED, or the declared one with its refusal carried
    # alongside; a release claim never outranks the evidence again.
    proof = (flavor_info.get("revision_gate") or {}).get("provenance") or {}
    if proof.get("identity_proven"):
        repository = proof["proven_repository"]
    else:
        repository = contracts.get("repository", "unknown")
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
    gate = flavor_info.get("revision_gate") or {}
    if flavor == "onboarding":
        candidate_head, candidate_branch, candidate_clean = head, branch, _repo_state(repo_root)[2]
    else:
        candidate_head, candidate_branch, candidate_clean = _repo_state(
            flavor_info.get("skill_root") or next(iter(flavor_info["sources_checked"]), None))
    if not candidate_head:
        # A pinned extraction carries no git metadata; its revision IS the pin.
        candidate_head = gate.get("revision")
        candidate_branch = (candidate_branch or
                            "pinned archive of %s" % (gate.get("revision_source") or "a named revision"))
        candidate_clean = gate.get("clean_excluding_instrument_output")
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
                "reason": ((payload.get("reason") or "candidate skill root lacks the shared contracts")
                           + "; sources checked: " + ", ".join(missing)),
                "class": "CANDIDATE_NOT_LANDED",
            })
    for row in cell_not_executed:
        row["class"] = ("CANDIDATE_NOT_LANDED" if status == "UNAVAILABLE"
                        else "NOT_MODELLED_BY_CONTRACTS")
        not_executed.append(row)
    not_executed = R.with_coverage_gaps(not_executed, F.NOT_COVERED)

    return R.build(
        flavor=flavor,
        repository=repository,
        candidate={
            "repository": repository,
            "repository_identity": proof,
            "commit": candidate_head,
            "branch": candidate_branch,
            "checkout_commit": checkout_head,
            "head_verified_at_execution": head_verified,
            "worktree_clean_excluding_receipts": candidate_clean,
            "revision_gate": flavor_info.get("revision_gate") or {},
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
        # A refused or unprovisioned flavor never ran, so it has no cells; that is
        # the shape validate() already allows, not a free pass - a flavor that DID
        # run still has to supply all nine.
        cells=cells or None,
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

    failures = 0
    written = []
    for flavor in order:
        gate = flavors[flavor].get("revision_gate") or {}
        print("%-10s REVISION GATE %-13s revision=%s %s"
              % (flavor, gate.get("status", "?"), gate.get("revision") or "-",
                 ("violations: " + "; ".join(gate["violations"])) if gate.get("violations") else ""))
        payload = run_flavor(flavor, flavors[flavor])
        receipt = build_receipt(flavor, repo_root, args, payload, {
            "repository": REPOSITORIES[flavor],
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
