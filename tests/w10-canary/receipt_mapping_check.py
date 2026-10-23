#!/usr/bin/env python3
"""receipt_mapping_check.py — read-only integrity check of receipt-mapping.json.

Verifies, without claiming anything:
  * schema + unit id present;
  * every acceptance row A01-A12 exists with its FROZEN weight (8,8,8,8,7,7,8,8,8,6,14,10);
  * weights sum to exactly 100;
  * every declared canary and read-only-check harness file EXISTS in this repo;
  * every acceptance row names something VERIFIABLE — a declared canary whose harness
    exists, a mapped_harness that exists at its pinned revision, or a mapped_command
    whose binary exists and whose verbs exist in its CLI at that pin — or carries an
    explicit run_by_hand marker. Silence is a failure, not a pass;
  * NO row claims an accepted point now (claims_now must be "none" everywhere),
    and the mapping's accepted_points_claimed_now == 0.

Exit 0 = mapping is internally consistent and claims nothing; 1 = inconsistency.
Stdlib only.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]

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


def repo_file(rel):
    """Resolve a repo-root-relative path; absolute paths pass through."""
    p = Path(rel).expanduser()
    return p if p.is_absolute() else REPO / p


def external_root(m, name):
    entry = (m.get("external_repos") or {}).get(name)
    if not entry:
        return None, "repo %r is not declared in external_repos" % name
    root = Path(str(entry.get("root", ""))).expanduser()
    if not root.is_dir():
        return None, "root %s is not a directory" % root
    return root, ""


def git_file_at(root, pin, rel):
    """(ok, detail) — does <rel> exist in git object <pin> of <root>?"""
    try:
        r = subprocess.run(
            ["git", "-C", str(root), "cat-file", "-e", "%s:%s" % (pin, rel)],
            capture_output=True, text=True)
    except OSError as e:
        return False, "git unavailable: %s" % e
    if r.returncode == 0:
        return True, "ok"
    return False, (r.stderr.strip() or "rc=%d" % r.returncode)


def git_blob_at(root, pin, rel):
    try:
        r = subprocess.run(
            ["git", "-C", str(root), "show", "%s:%s" % (pin, rel)],
            capture_output=True, text=True)
    except OSError:
        return ""
    return r.stdout if r.returncode == 0 else ""


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

    # every declared canary / read-only-check harness file must exist in this repo
    canaries = m.get("canaries", {})
    missing = []
    for cname, c in canaries.items():
        rel = c.get("harness")
        if not rel or not repo_file(rel).is_file():
            missing.append("%s -> %s" % (cname, rel))
    for cname, c in m.get("read_only_checks", {}).items():
        rel = c.get("harness")
        if not rel or not repo_file(rel).is_file():
            missing.append("%s -> %s" % (cname, rel))
    check("every declared harness file exists", not missing, "; ".join(missing))

    # --- acceptance rows: silence is a failure, and a named harness must really exist ---
    unbacked = []
    for rid in sorted(rows):
        row = rows[rid]
        if row.get("canaries") or row.get("mapped_harness") or row.get("mapped_command"):
            continue
        marker = row.get("run_by_hand")
        if not (isinstance(marker, str) and marker.strip()):
            unbacked.append(rid)
    check("every acceptance row names a harness/command or an explicit run_by_hand marker",
          not unbacked, "rows with no evidence path and no marker: %s" % unbacked)

    row_missing = []
    for rid in sorted(rows):
        row = rows[rid]

        for cname in row.get("canaries") or []:
            c = canaries.get(cname)
            if c is None:
                row_missing.append("%s -> canary %r is not declared" % (rid, cname))
            elif not c.get("harness") or not repo_file(c["harness"]).is_file():
                row_missing.append("%s -> canary %r harness %s is missing"
                                   % (rid, cname, c.get("harness")))

        mh = row.get("mapped_harness")
        if mh:
            root, why = external_root(m, mh.get("repo"))
            rel = mh.get("relpath") or ""
            pin = mh.get("pin") or ""
            if root is None:
                row_missing.append("%s -> mapped_harness: %s" % (rid, why))
            elif not rel or not (root / rel).is_file():
                row_missing.append("%s -> %s" % (rid, (root / rel) if rel else "no relpath"))
            elif not pin:
                row_missing.append("%s -> %s has no pinned revision" % (rid, rel))
            else:
                ok, detail = git_file_at(root, pin, rel)
                if not ok:
                    row_missing.append("%s -> %s absent at pin %s (%s)"
                                       % (rid, rel, pin[:12], detail))

        mc = row.get("mapped_command")
        if mc:
            root, why = external_root(m, mc.get("repo"))
            rel = mc.get("relpath") or ""
            pin = mc.get("pin") or ""
            cli = mc.get("cli_file") or ""
            if root is None:
                row_missing.append("%s -> mapped_command: %s" % (rid, why))
                continue
            if not rel or not (root / rel).is_file():
                row_missing.append("%s -> command binary %s is missing"
                                   % (rid, (root / rel) if rel else "no relpath"))
            if not pin:
                row_missing.append("%s -> command %r has no pinned revision"
                                   % (rid, mc.get("command")))
                continue
            text = git_blob_at(root, pin, cli)
            for verb in [v for v in (mc.get("verb"), mc.get("subverb")) if v]:
                if not re.search(r'add_parser\(\s*["\']%s["\']' % re.escape(verb), text):
                    row_missing.append("%s -> verb %r not found in %s at pin %s"
                                       % (rid, verb, cli, pin[:12]))

    check("every acceptance-row mapped harness/command exists at its pin",
          not row_missing, "; ".join(row_missing))

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
