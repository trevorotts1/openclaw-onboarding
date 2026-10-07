#!/usr/bin/env python3
"""CI matrix: required repo CI gates green on this build's proposed merges.

Targets, all read live from GitHub through `gh api` (no token printed):

  build-proposed-merge  the four merges this build proposed and landed —
                        999-setup PR 40 + PR 41, blackceo-command-center
                        PR 487, openclaw-onboarding PR 1563 — checked at
                        their PR head SHA (the commit the gates judged),
                        with merge SHA/merge time recorded as provenance.
  main-tip              current origin/main HEAD of the same three repos,
                        so "green on the merge" is not stale by the time
                        this receipt is read.

Row verdict
  GREEN    every check run completed, none red, >=1 gate actually ran
  RED      any check conclusion in the red set
  PENDING  checks still queued/in_progress after the poll window

Overall PASS only when every row is GREEN. Exit 2 when `gh` itself is
broken or unauthenticated — a shell/API failure is never evidence about
the checks. Receipt: receipts/ci-matrix.json
"""
from __future__ import annotations

import json
import subprocess
import time

from lib import EXIT_TOOLING, ROOT, ToolingError, finish, read_json, utcnow

REPOS = [
    "trevorotts1/openclaw-onboarding",
    "trevorotts1/blackceo-command-center",
    "trevorotts1/999-setup",
]

# The merges this build proposed (HANDOFF merge state; qualification/
# merge-receipts.json carries the same four rows).
BUILD_PRS = [
    ("trevorotts1/999-setup", 40, "W3-03 skill distribution"),
    ("trevorotts1/999-setup", 41, "W3-03 registry +2"),
    ("trevorotts1/blackceo-command-center", 487, "W3-01 media-campaign-adapter"),
    ("trevorotts1/openclaw-onboarding", 1563, "W3-02/W3-05 skill 75 + batch"),
]

RED = {"failure", "timed_out", "cancelled", "action_required",
       "startup_failure", "stale"}
GREEN_OK = {"success", "skipped", "neutral"}

# origin/main checks are live: e.g. onboarding's "QC static invariants"
# runs 6-8 minutes. Poll long enough to read a green, not a snapshot of
# a healthy run still in flight.
POLL_ATTEMPTS = 26
POLL_SECONDS = 20


def gh(path: str) -> dict:
    try:
        proc = subprocess.run(
            ["gh", "api", path],
            capture_output=True, text=True, timeout=60,
            cwd=str(ROOT),
        )
    except FileNotFoundError as exc:
        raise ToolingError("gh CLI not found: %s" % exc) from exc
    except subprocess.TimeoutExpired as exc:
        raise ToolingError("gh api timed out on %s" % path) from exc
    if proc.returncode != 0:
        raise ToolingError(
            "gh api %s rc=%s stderr=%s" % (path, proc.returncode,
                                           proc.stderr.strip()[:400]))
    try:
        return json.loads(proc.stdout)
    except ValueError as exc:
        raise ToolingError("gh api %s returned non-JSON" % path) from exc


def check_runs(repo: str, sha: str) -> list:
    """All check runs for a commit, paginated (per_page caps at 100)."""
    runs, page = [], 1
    while True:
        data = gh("repos/%s/commits/%s/check-runs?per_page=100&page=%d"
                  % (repo, sha, page))
        batch = data.get("check_runs") or []
        runs.extend(batch)
        total = int(data.get("total_count") or 0)
        if len(runs) >= total or not batch or page >= 20:
            break
        page += 1
    return runs


def classify(runs: list) -> dict:
    red, pending, green = [], [], []
    for run in runs:
        name = run.get("name") or "<unnamed>"
        status = run.get("status")
        conclusion = run.get("conclusion")
        if status != "completed" or conclusion is None:
            pending.append({"name": name, "status": status})
        elif conclusion in RED:
            red.append({"name": name, "conclusion": conclusion})
        elif conclusion in GREEN_OK:
            green.append({"name": name, "conclusion": conclusion})
        else:  # unknown conclusion — do not pass it silently
            red.append({"name": name, "conclusion": conclusion})
    verdict = "GREEN"
    if red:
        verdict = "RED"
    elif pending or not runs:
        verdict = "PENDING"
    return {
        "verdict": verdict,
        "total": len(runs),
        "green": len(green),
        "red": red,
        "pending": pending,
        "checks": sorted(
            [{"name": r.get("name"),
              "status": r.get("status"),
              "conclusion": r.get("conclusion")} for r in runs],
            key=lambda c: c["name"] or ""),
    }


def build_row(kind: str, repo: str, sha: str, label: str, extra=None) -> dict:
    row = {"type": kind, "repo": repo, "sha": sha, "label": label}
    row.update(extra or {})
    row.update(classify(check_runs(repo, sha)))
    return row


def branch_protection(repo: str) -> dict:
    """Required status checks on main, if the repo configures any."""
    try:
        data = gh("repos/%s/branches/main/protection" % repo)
    except ToolingError as exc:
        if "HTTP 404" in str(exc) or "Branch not protected" in str(exc):
            return {"protected": False, "required_checks": []}
        raise
    required = data.get("required_status_checks") or {}
    return {
        "protected": True,
        "strict": required.get("strict"),
        "required_checks": required.get("contexts") or [],
    }


def main() -> int:
    rows = []

    # 1. The proposed merges, at the head each gate suite judged.
    for repo, number, label in BUILD_PRS:
        pr = gh("repos/%s/pulls/%d" % (repo, number))
        head = pr.get("head", {}).get("sha")
        if not head:
            raise ToolingError("PR %s #%d has no head sha" % (repo, number))
        rows.append(build_row(
            "build-proposed-merge", repo, head, "PR #%d %s" % (number, label),
            {"pr": number,
             "pr_state": pr.get("state"),
             "merged_at": pr.get("merged_at"),
             "merge_sha": pr.get("merge_commit_sha"),
             "merge_landed": bool(pr.get("merged_at"))}))

    # 2. Current origin/main of each repo (tips resolved once, then polled
    #    by fixed SHA so a train pushing mid-scan cannot move the target).
    tips = {}
    for repo in REPOS:
        tip = gh("repos/%s/commits/main" % repo)
        sha = tip.get("sha")
        if not sha:
            raise ToolingError("no origin/main sha for %s" % repo)
        tips[repo] = sha
        rows.append(build_row(
            "main-tip", repo, sha, "origin/main",
            {"subject": (tip.get("commit", {}).get("message") or "")
                        .split("\n")[0][:120]}))

    # 3. Poll anything still running, bounded window.
    for attempt in range(POLL_ATTEMPTS):
        pending_rows = [r for r in rows if r["verdict"] == "PENDING"]
        if not pending_rows:
            break
        if attempt == POLL_ATTEMPTS - 1:
            break
        time.sleep(POLL_SECONDS)
        for row in pending_rows:
            row.update(classify(check_runs(row["repo"], row["sha"])))

    protections = {repo: branch_protection(repo) for repo in REPOS}

    red_rows = [r for r in rows if r["verdict"] == "RED"]
    pending_rows = [r for r in rows if r["verdict"] == "PENDING"]
    empty_rows = [r for r in rows if r["total"] == 0]
    verdict = "PASS" if not (red_rows or pending_rows or empty_rows) else "FAIL"

    summary = [
        ["proposed merges green",
         "PASS" if not red_rows and not any(
             r["verdict"] != "GREEN" for r in rows
             if r["type"] == "build-proposed-merge") else "FAIL",
         "%d/%d build PR heads GREEN" % (
             sum(1 for r in rows if r["type"] == "build-proposed-merge"
                 and r["verdict"] == "GREEN"),
             len(BUILD_PRS))],
        ["origin/main tips green",
         "PASS" if not any(r["verdict"] != "GREEN" for r in rows
                           if r["type"] == "main-tip") else "FAIL",
         "; ".join("%s=%s(%d checks)" % (r["repo"].split("/")[1],
                                         r["verdict"], r["total"])
                   for r in rows if r["type"] == "main-tip")],
        ["no red conclusions", "PASS" if not red_rows else "FAIL",
         "; ".join("%s %s" % (r["repo"], r["red"]) for r in red_rows)
         or "0 red across %d rows" % len(rows)],
        ["no pending after poll", "PASS" if not pending_rows else "FAIL",
         ", ".join(r["label"] for r in pending_rows) or
         "%d attempts x %ds" % (POLL_ATTEMPTS, POLL_SECONDS)],
        ["every row ran gates", "PASS" if not empty_rows else "FAIL",
         "%d rows, min checks %d" % (
             len(rows), min((r["total"] for r in rows), default=0))],
    ]

    receipt = {
        "receipt_name": "ci-matrix.json",
        "schema": "blackceo.ci-provenance/ci-matrix/v1",
        "unit_id": "W4-05-U1",
        "fetched_at": utcnow(),
        "instrument": "gh api (GitHub REST check-runs + pulls + protection)",
        "red_conclusions": sorted(RED),
        "green_conclusions": sorted(GREEN_OK),
        "branch_protection": protections,
        "rows": rows,
        "counts": {"rows": len(rows),
                   "green": sum(1 for r in rows if r["verdict"] == "GREEN"),
                   "red": len(red_rows),
                   "pending": len(pending_rows),
                   "empty": len(empty_rows)},
    }
    return finish(verdict, summary, receipt)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ToolingError as exc:
        print("TOOLING FAILURE (exit 2, not a check result): %s" % exc)
        raise SystemExit(EXIT_TOOLING)
