"""Assert-based self-check for integrations/CHANGED-RISK-REVIEW.md (W12-U1).

Re-proves every factual claim the review makes about merged GHL-delivery cohort 1
(W8A + W10B, PR #2491 folded by merge train #2492 at 510995e0c):

  - the review file exists and names the exact reviewed heads
  - the cohort diff vs the freeze base is pure addition (no deletions)
  - every member/cohort/train head is an ancestor of origin/main
  - the four cohort files exist at HEAD
  - both unit self-checks pass with their exact asserted output
  - the three Python files compile
  - the 10 version markers agree at HEAD

Run:  python3 -I integrations/changed_risk_review_selfcheck.py
Stdlib only; read-only; exits 0 on success, raises AssertionError on any drift.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REVIEW = REPO / "integrations" / "CHANGED-RISK-REVIEW.md"

BASE = "4b48ce34775b78afd55abfcd52fa85c8efc3c271"          # cohort freeze base
TRAIN_MERGE = "510995e0cadff7d863c8be62d272613c1af512f4"   # merge train #2492
W8A_HEAD = "89af6b7cab534fe3bbd27655b5a658db8447954f"
W10B_HEAD = "e8cfa1bf8f6755cbd438f23967b5f1673248f761"
COHORT_HEAD = "c2775d6dbe355dbc36a3d241bd70016bd747dfb2"

COHORT_FILES = (
    "integrations/BATCH-MERGE-LOG.md",
    "shared-utils/skills/__init__.py",
    "shared-utils/skills/discovery_aliases.py",
    "skills/79-checkout/order_bumps.py",
)


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True, check=False)


def run_check(relpath: str, expect: str) -> None:
    proc = subprocess.run([sys.executable, "-I", str(REPO / relpath)],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, f"{relpath} exited {proc.returncode}: {proc.stderr[-400:]}"
    assert expect in proc.stdout, f"{relpath} missing {expect!r}: {proc.stdout[-400:]}"


def main() -> int:
    passed = 0

    def ok(cond: bool, label: str) -> None:
        nonlocal passed
        assert cond, "FAIL: " + label
        passed += 1
        print("PASS", label)

    # 1 — review artifact exists and names the reviewed heads
    ok(REVIEW.is_file(), "CHANGED-RISK-REVIEW.md exists")
    text = REVIEW.read_text(encoding="utf-8")
    for sha in (TRAIN_MERGE, W8A_HEAD, W10B_HEAD, COHORT_HEAD):
        ok(sha in text, f"review names head {sha[:9]}")

    # 2 — cohort diff is pure addition over exactly the four cohort files
    numstat = git("diff", "--numstat", f"{BASE}..{TRAIN_MERGE}")
    ok(numstat.returncode == 0, "git diff --numstat runs")
    rows = [line.split("\t") for line in numstat.stdout.splitlines() if line.strip()]
    ok(sorted(r[2] for r in rows) == sorted(COHORT_FILES), "diff touches exactly the four cohort files")
    ok(all(r[1] == "0" for r in rows), "pure addition: zero deletions")
    ok(sum(int(r[0]) for r in rows) == 804, "804 insertions as reviewed")

    # 3 — merge proof: every member/cohort/train head is on origin/main
    for sha in (W8A_HEAD, W10B_HEAD, COHORT_HEAD, TRAIN_MERGE):
        ok(git("merge-base", "--is-ancestor", sha, "origin/main").returncode == 0,
           f"{sha[:9]} is ancestor of origin/main")

    # 4 — cohort files exist at HEAD
    for relpath in COHORT_FILES:
        ok((REPO / relpath).is_file(), f"exists at HEAD: {relpath}")

    # 5 — both unit self-checks pass with their exact asserted output
    run_check("skills/79-checkout/order_bumps.py", "self-check OK (23 assertions)")
    ok(True, "W8A self-check: self-check OK (23 assertions), exit 0")
    run_check("shared-utils/skills/discovery_aliases.py", "OK 75 PASS")
    ok(True, "W10B self-check: OK 75 PASS, exit 0")

    # 6 — the three Python files compile
    compile3 = subprocess.run(
        [sys.executable, "-m", "py_compile",
         str(REPO / "skills/79-checkout/order_bumps.py"),
         str(REPO / "shared-utils/skills/discovery_aliases.py"),
         str(REPO / "shared-utils/skills/__init__.py")],
        capture_output=True, text=True, check=False)
    ok(compile3.returncode == 0, "py_compile on all three Python files, exit 0")

    # 7 — version markers agree at HEAD
    markers = subprocess.run(["bash", str(REPO / "scripts" / "bump-version.sh"), "--check"],
                             capture_output=True, text=True, check=False)
    ok(markers.returncode == 0 and "All 10 version markers agree." in markers.stdout,
       "scripts/bump-version.sh --check: All 10 version markers agree")

    print(f"changed-risk-review self-check OK ({passed} assertions)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
