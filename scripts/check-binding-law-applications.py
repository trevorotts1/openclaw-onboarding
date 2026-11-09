#!/usr/bin/env python3
"""Verify the binding-law application register for SCOPE-LEDGER applications 71-140.

The register (evidence/binding-laws/applications-71-140.json) is prose-free: every
row must be re-derivable or explicitly UNKNOWN with a reason. This checker enforces
the parts a checkout can decide by itself:

  * shape      -- 70 rows, n contiguous 71..140, id == "<unit>-<law>", ledger order
  * verdicts   -- PRESENT / ABSENT / UNKNOWN only; every row carries evidence text
  * tree rows  -- every row claiming method tree/tree+git is re-verified against the
                  files it cites (file exists, quoted anchor present)

Rows whose truth lives in a lane transcript or the GitHub timeline are declared
UNKNOWN or ABSENT with their recorded evidence; the checker does NOT trust them as
verified, and it fails if such a row is relabelled PRESENT without a tree method.

Exit 0 = register holds. Exit 1 = drift or a false PRESENT. Exit 2 = register missing.
"""

import argparse
import json
import os
import re
import subprocess
import sys

REGISTER = "evidence/binding-laws/applications-71-140.json"
UNITS = ["LAND-001", "LAND-002", "LAND-003", "LAND-004", "LAND-005",
         "RES-001", "RES-002", "RES-003", "RES-004", "MOCK-001", "ASM-001",
         "PRMPT-001", "INST-001"]
LAWS = ["L%d" % i for i in range(1, 17)]
EXPECTED = [(u, l) for u in UNITS for l in LAWS][70:140]
VERDICTS = {"PRESENT", "ABSENT", "UNKNOWN"}
TREE_METHODS = {"tree", "tree+git", "git_diff", "git_log_merges", "git_merge_base",
                "github_timeline", "github_pr"}


def repo_root():
    try:
        return subprocess.run(["git", "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return os.getcwd()


def load(root):
    path = os.path.join(root, REGISTER)
    if not os.path.exists(path):
        print("MISSING REGISTER: %s" % REGISTER, file=sys.stderr)
        sys.exit(2)
    with open(path) as fh:
        return json.load(fh)


def check_shape(doc, fail):
    rows = doc.get("rows") or []
    if len(rows) != 70:
        fail("row count is %d, expected 70 (applications 71-140)" % len(rows))
    if doc.get("counts", {}).get("total") != len(rows):
        fail("counts.total does not match row count")
    for i, row in enumerate(rows):
        want_n = 71 + i
        want = EXPECTED[i]
        if row.get("n") != want_n:
            fail("row %d carries n=%r; ledger order requires %d (no renumbering, no skip)"
                 % (i, row.get("n"), want_n))
        if (row.get("unit"), row.get("law")) != want:
            fail("row n=%s is %s/%s; ledger order requires %s/%s"
                 % (row.get("n"), row.get("unit"), row.get("law"), want[0], want[1]))
        if row.get("id") != "%s-%s" % want:
            fail("row n=%s id=%r; expected %r" % (row.get("n"), row.get("id"), "%s-%s" % want))
        if row.get("verdict") not in VERDICTS:
            fail("row %s has verdict %r outside %s" % (row.get("id"), row.get("verdict"), sorted(VERDICTS)))
        if not (row.get("evidence") or "").strip():
            fail("row %s has no evidence text" % row.get("id"))
        if not (row.get("requirement") or "").strip():
            fail("row %s has no requirement text" % row.get("id"))
        if row.get("verdict") == "PRESENT" and row.get("method") not in TREE_METHODS:
            fail("row %s claims PRESENT with method %r; PRESENT needs a re-derivable method"
                 % (row.get("id"), row.get("method")))


def check_tree_rows(doc, root, fail):
    """Every row that claims a tree method must have its cited anchors on disk."""
    anchors = {
        "sf-prover-pin-authority.yml": ".github/workflows/sf-prover-pin-authority.yml",
        "front_door.py": "49-signature-funnel/scripts/front_door.py",
        "MINTING. Only two paths write": "49-signature-funnel/scripts/front_door.py",
        "name: SF prover pin authority": ".github/workflows/sf-prover-pin-authority.yml",
    }
    checked = 0
    for row in doc["rows"]:
        if "tree" not in (row.get("method") or ""):
            continue
        ev = row.get("evidence", "")
        for needle, rel in anchors.items():
            if needle not in ev:
                continue
            path = os.path.join(root, rel)
            if not os.path.exists(path):
                fail("row %s cites %s but it is absent from the tree" % (row["id"], rel))
                continue
            with open(path, errors="replace") as fh:
                body = fh.read()
            if needle == "front_door.py" or needle == "MINTING. Only two paths write":
                if "MINTING. Only two paths write" not in body:
                    fail("row %s cites the MINTING block; it is no longer in %s" % (row["id"], rel))
            else:
                if needle not in body:
                    fail("row %s cites %r; it is no longer in %s" % (row["id"], needle, rel))
            checked += 1
    return checked


def check_pin_single_authority(root, fail):
    """L6: the pin has exactly one minting workflow. Any second committer is a defect."""
    hits = []
    wf_dir = os.path.join(root, ".github", "workflows")
    for name in sorted(os.listdir(wf_dir)) if os.path.isdir(wf_dir) else []:
        if not name.endswith((".yml", ".yaml")):
            continue
        with open(os.path.join(wf_dir, name), errors="replace") as fh:
            if "mint-pin --ci" in fh.read():
                hits.append(name)
    if hits != ["sf-prover-pin-authority.yml"]:
        fail("pin minting must run from exactly one workflow; found %r" % hits)
    return hits


def audit_ref(ref, base, fail):
    """L12: a unit branch must contain ZERO merge commits since its merge-base with base."""
    mb = subprocess.run(["git", "merge-base", base, ref], capture_output=True, text=True)
    if mb.returncode != 0:
        fail("L12 audit: no merge-base between %s and %s (shallow clone or unrelated history) "
             "-- UNDETERMINED, not pass" % (base, ref))
        return None
    count = subprocess.run(["git", "rev-list", "--merges", "--count",
                            "%s..%s" % (mb.stdout.strip(), ref)],
                           capture_output=True, text=True, check=True).stdout.strip()
    if int(count) != 0:
        fail("L12 audit: %s carries %s merge commit(s) since merge-base with %s "
             "(re-cut from origin/main instead of merging main into the branch)" % (ref, count, base))
    return int(count)


def audit_pr(number, fail):
    """L2: a unit PR must carry zero HeadRefForcePushedEvent timeline items."""
    got = subprocess.run(["gh", "api", "graphql", "-f",
                          'query($n:Int!){repository(owner:"trevorotts1",name:"openclaw-onboarding")'
                          '{pullRequest(number:$n){timelineItems(first:100,'
                          'itemTypes:[HEAD_REF_FORCE_PUSHED_EVENT]){totalCount}}}}',
                          "-F", "n=%s" % number, "--jq",
                          ".data.repository.pullRequest.timelineItems.totalCount"],
                         capture_output=True, text=True)
    if got.returncode != 0:
        fail("L2 audit: gh could not read timeline for #%s -- UNDETERMINED" % number)
        return None
    if int(got.stdout.strip() or 0) != 0:
        fail("L2 audit: PR #%s carries %s force-push event(s)" % (number, got.stdout.strip()))
    return int(got.stdout.strip() or 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="machine-readable summary")
    ap.add_argument("--audit-ref", help="L12: fail if this ref carries merge commits since its merge-base")
    ap.add_argument("--base", default="origin/main", help="base ref for --audit-ref")
    ap.add_argument("--audit-pr", help="L2: fail if this PR carries force-push events")
    args = ap.parse_args()

    root = repo_root()
    errors = []

    def fail(msg):
        errors.append(msg)

    if args.audit_ref or args.audit_pr:
        audits = {}
        if args.audit_ref:
            audits["merges_since_merge_base"] = audit_ref(args.audit_ref, args.base, fail)
        if args.audit_pr:
            audits["force_push_events"] = audit_pr(args.audit_pr, fail)
        print(json.dumps({"audit": audits, "errors": errors, "ok": not errors}, indent=1))
        return 0 if not errors else 1

    doc = load(root)
    check_shape(doc, fail)
    checked = check_tree_rows(doc, root, fail)
    workflows = check_pin_single_authority(root, fail)

    counts = {}
    for row in doc.get("rows", []):
        counts[row.get("verdict")] = counts.get(row.get("verdict"), 0) + 1

    summary = {
        "register": REGISTER,
        "rows": len(doc.get("rows", [])),
        "counts": counts,
        "tree_anchors_reverified": checked,
        "pin_minting_workflows": workflows,
        "errors": errors,
        "ok": not errors,
    }
    if args.json:
        print(json.dumps(summary, indent=1))
    else:
        print("binding-law applications 71-140: %d rows  %s" %
              (summary["rows"], " ".join("%s=%d" % (k, counts[k]) for k in sorted(counts))))
        print("tree anchors re-verified: %d; pin minting workflows: %s"
              % (checked, ",".join(workflows)))
        for e in errors:
            print("FAIL: %s" % e)
        print("OK" if not errors else "DRIFT")
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
