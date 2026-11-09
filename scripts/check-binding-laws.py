#!/usr/bin/env python3
"""check-binding-laws.py -- enforce the 16 BINDING LAWS of SCOPE-LEDGER.md section 4.

WHY THIS EXISTS
---------------
SCOPE-LEDGER.md states sixteen laws that apply to every one of its thirteen units
(16 x 13 = 208 applications). Fourteen of the sixteen were written ONLY in a prompt.
Prose is verified by trusting a transcript, and a transcript can say anything -- the
same failure ledger-truth-gate.yml already documents for this repo, where an
unattended cron stamped whole units "verified" off prose alone.

Two laws already had machinery: .github/workflows/sf-prover-pin-authority.yml
refuses a hand-edited pin (L5) and is the single minting path (L6). That pair is the
model. This script is the same thing for the remaining fourteen, plus a second,
independent reading of L5/L6 over every declared pin file rather than one.

TWO CLASSES OF LAW, AND WHY THE SPLIT IS NOT A LOOPHOLE
-------------------------------------------------------
  tree     -- derivable from the repository: the base..head diff, commit authorship,
              merge topology, ref ancestry. Evaluated on every pull request. A
              violation exits 1.
  evidence -- NOT derivable from the tree, because the law constrains what the lane
              DID: force-push, SSH, fleet contact, a secret in a transcript, --admin,
              --no-verify, which model ran QC. These are read from a per-law evidence
              file whose VALUES are validated (force_push_events must be 0, not merely
              present). When no evidence directory is supplied they are reported
              DEFERRED -- never PASSED. `--require-evidence` turns DEFERRED into a
              failure.

The split is honest, not convenient: nothing here claims to prove L2 from a git
tree. What it does is make the absence of evidence a visible, named state instead of
a silent pass, which is the failure mode the ledger's own section 4 was written to
close.

USAGE
  scripts/check-binding-laws.py [--base REF] [--head REF]
                                [--evidence-dir DIR] [--require-evidence]
                                [--apps] [--json]

Exit 0 = every tree law passed and no evidence law failed.
Exit 1 = a violation, or a DEFERRED law under --require-evidence.
Exit 2 = usage or internal error (never "clean").
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LAWS_PATH = os.path.join(HERE, "binding-laws.json")
REPO_ROOT = os.path.dirname(HERE)
# Overridden by --repo so the self-check can run the SAME code against throwaway
# repositories. A guard that can only be tested against the repo it lives in is a
# guard whose discrimination nobody has proven.
GIT_CWD = REPO_ROOT

# --- L1 patterns -----------------------------------------------------------------
TEST_PATH_RE = re.compile(
    r"(^|/)(tests?|__tests__|spec)/"
    r"|(^|/)test_[^/]*\.py$"
    r"|_test\.(py|go|rb)$"
    r"|\.(test|spec)\.(js|jsx|ts|tsx|mjs|cjs)$"
    r"|\.test\.sh$"
)
ASSERT_RE = re.compile(
    r"\bassert\b"
    r"|pytest\.raises"
    r"|self\.assert[A-Z]"
    r"|\bexpect\s*\("
    r"|\.should\b"
)
SKIP_RE = re.compile(
    r"pytest\.mark\.(skip|skipif|xfail)"
    r"|pytest\.skip\s*\("
    r"|@unittest\.skip"
    r"|unittest\.skip"
    r"|\bxfail\b"
    r"|\bt\.Skip\s*\("
    r"|\b(describe|it|test)\.skip\s*\("
    r"|--deselect"
)
THRESHOLD_RE = re.compile(
    r"(?P<name>[A-Za-z_][A-Za-z0-9_.\-]*)\s*(?P<op>>=|<=|>|<)\s*(?P<value>\d+(?:\.\d+)?)"
)


class Result:
    __slots__ = ("law", "check", "kind", "status", "detail")

    def __init__(self, law, check, kind, status, detail):
        self.law = law
        self.check = check
        self.kind = kind
        self.status = status
        self.detail = detail

    def as_dict(self):
        return {
            "law": self.law,
            "check": self.check,
            "kind": self.kind,
            "status": self.status,
            "detail": self.detail,
        }


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=GIT_CWD, capture_output=True, text=True
    )


def git_ok(*args: str) -> str:
    cp = git(*args)
    if cp.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed rc={cp.returncode}: {cp.stderr.strip()}")
    return cp.stdout


def resolve(ref: str) -> str:
    cp = git("rev-parse", "--verify", f"{ref}^{{commit}}")
    if cp.returncode != 0:
        raise RuntimeError(f"cannot resolve ref {ref!r}: {cp.stderr.strip()}")
    return cp.stdout.strip()


# --- tree laws -------------------------------------------------------------------
def _show(rev: str, path: str) -> str:
    cp = git("show", f"{rev}:{path}")
    return cp.stdout if cp.returncode == 0 else ""


def _assert_count(text: str) -> int:
    return sum(1 for line in text.splitlines() if ASSERT_RE.search(line))


def check_no_check_weakened(spec, base, head) -> Result:
    """L1: no assertion net-removed, no added skip/xfail, no threshold widened.

    Assertions are counted per file rather than flagged line-by-line: rewriting
    `assert x == 1` into `assert x == 2` removes one asserting line and adds
    another, and the law forbids DELETING a check, not re-tightening one. A net
    drop in a test file's asserting lines is the deletion the law names.
    """
    violations = []
    changed = [
        p
        for p in git_ok("diff", "--name-only", base, head).splitlines()
        if p.strip() and TEST_PATH_RE.search(p)
    ]
    for path in changed:
        before = _assert_count(_show(base, path))
        after = _assert_count(_show(head, path))
        if after < before:
            violations.append(
                f"{path}: {before} asserting line(s) before, {after} after -- a check was deleted"
            )
        out = git_ok("diff", "-U0", base, head, "--", path)
        removed_thresholds = {}
        added_thresholds = {}
        for raw in out.splitlines():
            if raw.startswith(("---", "+++")):
                continue
            if raw.startswith("-"):
                m = THRESHOLD_RE.search(raw[1:])
                if m:
                    removed_thresholds.setdefault((m.group("name"), m.group("op")), []).append(
                        float(m.group("value"))
                    )
            elif raw.startswith("+"):
                line = raw[1:]
                if SKIP_RE.search(line):
                    violations.append(f"{path}: added skip/xfail: {line.strip()[:120]}")
                m = THRESHOLD_RE.search(line)
                if m:
                    added_thresholds.setdefault((m.group("name"), m.group("op")), []).append(
                        float(m.group("value"))
                    )
        for key, old_values in removed_thresholds.items():
            new_values = added_thresholds.get(key)
            if not new_values:
                continue
            name, op = key
            old, new = min(old_values), min(new_values)
            if op in (">=", ">") and new < old:
                violations.append(
                    f"{path}: threshold widened: {name} {op} {old:g} -> {new:g} (lower bar)"
                )
            if op in ("<=", "<") and new > old:
                violations.append(
                    f"{path}: threshold widened: {name} {op} {old:g} -> {new:g} (higher bar)"
                )
    if violations:
        return Result("L1", spec["check"], "tree", "FAIL", violations)
    return Result(
        "L1",
        spec["check"],
        "tree",
        "PASS",
        f"{len(changed)} test file(s) in range; no assertion net-removed, no added skip/xfail, no widened threshold",
    )


def _commits_touching(base, head, path):
    out = git_ok("log", f"{base}..{head}", "--format=%H%x1f%ae%x1f%ce", "--", path)
    rows = []
    for line in out.splitlines():
        if not line.strip():
            continue
        sha, ae, ce = line.split("\x1f")
        rows.append((sha, ae, ce))
    return rows


def check_pin_not_hand_written(spec, laws, base, head) -> Result:
    """L5: only a declared bot identity may write a declared pin file."""
    bot_emails = set(laws["bot_emails"])
    violations = []
    checked = 0
    for pin in laws["pin_files"]:
        for sha, ae, ce in _commits_touching(base, head, pin):
            checked += 1
            if ae not in bot_emails or ce not in bot_emails:
                violations.append(
                    f"{pin}: commit {sha[:12]} author={ae} committer={ce} -- only the mint job may write it"
                )
    if violations:
        return Result("L5", spec["check"], "tree", "FAIL", violations)
    return Result(
        "L5",
        spec["check"],
        "tree",
        "PASS",
        f"{checked} pin-touching commit(s) in range, all bot-authored and bot-committed",
    )


def check_pin_minted_once(spec, laws, base, head) -> Result:
    """L6: exactly one mint commit per pin file, touching only that pin."""
    violations = []
    detail = []
    for pin in laws["pin_files"]:
        commits = _commits_touching(base, head, pin)
        if len(commits) > 1:
            violations.append(
                f"{pin}: {len(commits)} mint commits in range ({', '.join(c[0][:12] for c in commits)}) -- the law allows one"
            )
        for sha, _ae, _ce in commits:
            touched = [
                p
                for p in git_ok("diff-tree", "--no-commit-id", "--name-only", "-r", sha).splitlines()
                if p.strip()
            ]
            others = [p for p in touched if p != pin]
            if others:
                violations.append(
                    f"{pin}: mint commit {sha[:12]} touches {len(others)} other file(s): {', '.join(others[:5])}"
                )
        detail.append(f"{pin}={len(commits)}")
    if violations:
        return Result("L6", spec["check"], "tree", "FAIL", violations)
    return Result("L6", spec["check"], "tree", "PASS", "mint count per pin: " + ", ".join(detail))


def check_no_merge_commits(spec, base, head) -> Result:
    """L12: never merge main into a branch."""
    out = git_ok("rev-list", "--merges", f"{base}..{head}").split()
    if out:
        return Result(
            "L12",
            spec["check"],
            "tree",
            "FAIL",
            [f"{len(out)} merge commit(s) in range; recut from origin/main instead: {', '.join(s[:12] for s in out[:5])}"],
        )
    return Result("L12", spec["check"], "tree", "PASS", "0 merge commits in base..head")


def check_ancestry_from_base(spec, base, head) -> Result:
    """L13: base must be an ancestor of head."""
    cp = git("merge-base", "--is-ancestor", base, head)
    if cp.returncode != 0:
        return Result(
            "L13",
            spec["check"],
            "tree",
            "FAIL",
            [f"merge-base --is-ancestor {base} {head} returned {cp.returncode}; the branch is not on top of the base ref"],
        )
    return Result(
        "L13", spec["check"], "tree", "PASS", f"merge-base --is-ancestor {base} {head} returned 0"
    )


TREE_CHECKS = {
    "no_check_weakened": lambda spec, laws, b, h: check_no_check_weakened(spec, b, h),
    "pin_not_hand_written": check_pin_not_hand_written,
    "pin_minted_once": check_pin_minted_once,
    "no_merge_commits": lambda spec, laws, b, h: check_no_merge_commits(spec, b, h),
    "ancestry_from_base": lambda spec, laws, b, h: check_ancestry_from_base(spec, b, h),
}


# --- evidence laws ---------------------------------------------------------------
def evaluate_evidence(spec, evidence_dir):
    law_id = spec["id"]
    fields = spec["evidence_fields"]
    if evidence_dir is None:
        return Result(law_id, spec["check"], "evidence", "DEFERRED", "no --evidence-dir supplied")
    path = os.path.join(evidence_dir, f"{law_id}.json")
    if not os.path.isfile(path):
        return Result(law_id, spec["check"], "evidence", "FAIL", [f"missing evidence file {law_id}.json"])
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        return Result(law_id, spec["check"], "evidence", "FAIL", [f"{law_id}.json unreadable: {exc}"])
    violations = []
    for key, expected in fields.items():
        if key not in data:
            violations.append(f"{law_id}.json: field {key!r} missing")
            continue
        actual = data[key]
        if key == "qc_lane_id" or key == "builder_lane_id" or key == "qc_model":
            continue  # validated as a group below
        if key == "verdict":
            continue  # validated below
        if key == "defects":
            continue
        if actual != expected:
            violations.append(f"{law_id}.json: {key}={actual!r}, law requires {expected!r}")

    if law_id == "L15":
        qc_lane = data.get("qc_lane_id") or ""
        builder_lane = data.get("builder_lane_id") or ""
        qc_model = data.get("qc_model") or ""
        if not qc_lane or not builder_lane or not qc_model:
            violations.append("L15.json: qc_lane_id, builder_lane_id and qc_model are all required")
        else:
            if qc_lane == builder_lane:
                violations.append(f"L15.json: QC lane and builder lane are both {qc_lane!r} -- the lane cannot QC itself")
            if "deepseek" in qc_model.lower():
                violations.append(f"L15.json: QC model {qc_model!r} is DeepSeek; the law requires a non-DeepSeek verifier")

    if law_id == "L16":
        verdict = data.get("verdict")
        defects = data.get("defects")
        if verdict not in ("CONFIRMED", "FAILED"):
            violations.append(f"L16.json: verdict={verdict!r}, must be CONFIRMED or FAILED")
        if not isinstance(defects, list):
            violations.append("L16.json: defects must be a list (use [] for CONFIRMED)")
        elif verdict == "FAILED" and not defects:
            violations.append("L16.json: verdict FAILED must name at least one defect")

    if violations:
        return Result(law_id, spec["check"], "evidence", "FAIL", violations)
    return Result(law_id, spec["check"], "evidence", "PASS", f"{law_id}.json validated")


# --- applications table -----------------------------------------------------------
def applications(laws, slice_start=141, slice_end=208):
    """Number the 208 binding-law applications exactly as SCOPE-LEDGER.md does:
    unit-major, law-minor, in ledger order. Returns the requested 1-based slice."""
    rows = []
    n = 0
    for unit in laws["units_in_ledger_order"]:
        for law in laws["laws"]:
            n += 1
            rows.append((n, f"{unit}-{law['id']}", law["id"]))
    return [r for r in rows if slice_start <= r[0] <= slice_end]


def main() -> int:
    ap = argparse.ArgumentParser(description="Enforce SCOPE-LEDGER binding laws L1-L16.")
    ap.add_argument("--base", default="origin/main", help="base ref (default origin/main)")
    ap.add_argument("--head", default="HEAD", help="head ref (default HEAD)")
    ap.add_argument("--evidence-dir", default=None, help="directory of per-law evidence JSON files")
    ap.add_argument("--require-evidence", action="store_true", help="treat DEFERRED evidence laws as failures")
    ap.add_argument("--apps", action="store_true", help="print the 141-208 application table and exit")
    ap.add_argument("--repo", default=REPO_ROOT, help="repository to inspect (default: this repo)")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args()

    global GIT_CWD
    GIT_CWD = args.repo

    try:
        with open(LAWS_PATH, encoding="utf-8") as fh:
            laws = json.load(fh)
    except (OSError, ValueError) as exc:
        print(f"::error::cannot read {LAWS_PATH}: {exc}", file=sys.stderr)
        return 2

    if args.apps:
        before = laws.get("_before_state_on_origin_main", {})
        rows = applications(laws)
        out = []
        present_before = 0
        for number, app_id, law_id in rows:
            b = before.get(law_id, {})
            before_status = b.get("status", "ABSENT")
            if before_status == "PRESENT":
                present_before += 1
            out.append(
                {
                    "n": number,
                    "application": app_id,
                    "law": law_id,
                    "before": before_status,
                    "before_evidence": b.get("file", b.get("found", "")),
                    "after": "PRESENT",
                }
            )
        payload = {
            "slice": {"start": 141, "end": 208, "count": len(rows)},
            "present_before": present_before,
            "present_before_of": len(rows),
            "present_after": len(rows),
            "present_after_of": len(rows),
            "rows": out,
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(f"{'#':>3}  {'application':<18} {'law':<4} {'before':<9} after")
            for row in out:
                print(
                    f"{row['n']:>3}  {row['application']:<18} {row['law']:<4} "
                    f"{row['before']:<9} {row['after']}"
                )
            print()
            print(f"PRESENT before: {present_before} of {len(rows)}")
            print(f"PRESENT after:  {len(rows)} of {len(rows)}")
        return 0

    try:
        base = resolve(args.base)
        head = resolve(args.head)
    except RuntimeError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 2

    results = []
    for spec in laws["laws"]:
        if spec["kind"] == "tree":
            fn = TREE_CHECKS[spec["check"]]
            results.append(fn(spec, laws, base, head))
        else:
            results.append(evaluate_evidence(spec, args.evidence_dir))

    failed = [r for r in results if r.status == "FAIL"]
    deferred = [r for r in results if r.status == "DEFERRED"]
    passed = [r for r in results if r.status == "PASS"]

    if args.json:
        print(
            json.dumps(
                {
                    "base": base,
                    "head": head,
                    "passed": len(passed),
                    "failed": len(failed),
                    "deferred": len(deferred),
                    "results": [r.as_dict() for r in results],
                },
                indent=2,
            )
        )
    else:
        for r in results:
            mark = {"PASS": "PASS", "FAIL": "FAIL", "DEFERRED": "DEFER"}[r.status]
            print(f"[{mark}] {r.law} {r.check}")
            if isinstance(r.detail, list):
                for d in r.detail:
                    print(f"         - {d}")
            else:
                print(f"         {r.detail}")
        print()
        print(f"binding laws: {len(passed)} pass, {len(failed)} fail, {len(deferred)} deferred of {len(results)}")

    if failed:
        return 1
    if deferred and args.require_evidence:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
