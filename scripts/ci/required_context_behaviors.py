#!/usr/bin/env python3
"""required_context_behaviors.py — required checks, and what each one proves.

The merge gate reads eight required status contexts off a PR's status rollup
(scripts/pr-rollup-required-contexts.fallback.json is the checked-in snapshot;
scripts/pr-rollup-check.py fetches the live list). Two failure shapes are
invisible in a green rollup:

  1. A context no workflow job reports never appears at all, so the PR sits at
     "Expected - Waiting for status to be reported" and nothing merges.
  2. A context whose job is skipped on pull_request DOES appear, as SKIPPED,
     and the merge gate counts SKIPPED as PASS (scripts/pr-rollup-check.py
     TERMINAL_PASS). The check is green on every PR while proving nothing.

This module maps each required context to the workflow job that reports it and
the behavior that job actually verifies on a PR, and exits non-zero when a
context is missing, ambiguous, reported from a workflow that never runs on a
PR, skipped on PRs without a declared gap, or covered by a declared gap that no
longer matches reality.

  python3 scripts/ci/required_context_behaviors.py [--root DIR] [--json]

Exit 0 = every required context is accounted for. Exit 1 = mapping defect.
Read-only: it never edits a workflow, never contacts GitHub, never runs a gate.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FALLBACK_RELPATH = "scripts/pr-rollup-required-contexts.fallback.json"
WORKFLOW_DIR = ".github/workflows"

# What each required context is SUPPOSED to prove, plus one literal snippet
# from its job body that proves the named behavior is actually implemented
# there. A renamed job or a gutted step body breaks the mapping, not just a
# string in this table.
CHECKS = {
    "ghl-mcp-pin-gate": {
        "workflow": "ghl-mcp-supervised-guard.yml",
        "job": "ghl-mcp-pin-gate",
        "proves": (
            "pin digest binding, pin-by-SHA reachability on the mirror, lockfile "
            "coverage and fallback constants (scripts/qc-assert-ghl-mcp-pin-gate.sh "
            "--network), plus the vetting-digest mutation proofs."
        ),
        "must_contain": [
            "qc-assert-ghl-mcp-pin-gate.sh --network",
            "ghl-mcp-pin-digest.test.sh",
        ],
    },
    "GHL MCP supervision + install regression guard": {
        "workflow": "ghl-mcp-supervised-guard.yml",
        "job": "ghl-mcp-supervised-guard",
        "proves": (
            "supervised autostart and install-time invariants: a pinned 40-char "
            "commit, a CLEAN vetting verdict, resolver delivery paths, runtime "
            "conformance, and positive+negative mutation tests."
        ),
        "must_contain": [
            "qc-assert-ghl-mcp-supervised.sh",
            "ghl-mcp-supervised.test.sh",
        ],
    },
    "QC static invariants": {
        "workflow": "qc-static.yml",
        "job": "qc-static",
        "proves": (
            "repo-static invariants (Python parse, weight sums, JSON schemas, "
            "banned model strings) and the skill QC gates, several of which carry "
            "their own deliberate negative self-tests."
        ),
        "must_contain": ["qc-assert-", "tests/unit/"],
    },
    "G1 — version file change requires a matching annotated tag (push to main)": {
        "workflow": "version-consistency.yml",
        "job": "check-version-tag-guard",
        "proves": (
            "PUSH ONLY: when /version changed, an annotated tag for the new "
            "version must exist on origin within 300s; a lightweight tag is "
            "rejected."
        ),
        "must_contain": ["git cat-file -t", "Only ANNOTATED tags are accepted"],
    },
    "G1b — every release on main must keep a truthful annotated tag": {
        "workflow": "version-consistency.yml",
        "job": "check-released-versions-tagged",
        "proves": (
            "every release on origin/main's first-parent history carries an "
            "annotated tag whose commit carries that version "
            "(scripts/check-released-versions-tagged.py)."
        ),
        "must_contain": ["check-released-versions-tagged.py"],
    },
    "G2 — every v11+ annotated tag must have a CHANGELOG entry": {
        "workflow": "version-consistency.yml",
        "job": "check-tag-changelog-guard",
        "proves": (
            "every annotated vX.Y.Z tag with major >= 11 that is present in the "
            "checkout has a matching CHANGELOG.md header."
        ),
        "must_contain": ["Checked $CHECKED v11+ annotated tags"],
    },
    "G3 — skill content change requires skill-version.txt bump": {
        "workflow": "version-consistency.yml",
        "job": "check-skill-version-bump",
        "proves": (
            "a changed file inside a numbered skill directory must come with that "
            "skill's skill-version.txt in the same diff (merge-base diff on PRs)."
        ),
        "must_contain": ["Skill content changed without a skill-version.txt bump"],
    },
    "Verify all version markers agree (scripts/bump-version.sh --check)": {
        "workflow": "version-consistency.yml",
        "job": "check-version-drift",
        "proves": (
            "scripts/bump-version.sh --check over scripts/version-markers.json, "
            "plus the cc-compat.json integrity self-test and doc-currency "
            "self-tests."
        ),
        "must_contain": ["bump-version.sh --check", "cc-compat.json"],
    },
}

# Contexts whose job is deliberately skipped on pull_request. Each entry is a
# GAP, not a green check: the merge gate counts SKIPPED as PASS, so on a PR the
# context proves nothing. It is declared here with the exact skip condition so
# it cannot be mistaken for coverage, and so a change to the condition (the gap
# closing or moving) fails this map instead of passing silently.
KNOWN_PR_SKIPS = {
    "G1 — version file change requires a matching annotated tag (push to main)": {
        "workflow": "version-consistency.yml",
        "job": "check-version-tag-guard",
        "condition": "github.event_name == 'push'",
        "gap": (
            "Push-only by design: auto-tag-on-merge publishes the release tag "
            "after the merge, so a PR has no tag to check. On every PR this "
            "required context reports SKIPPED, which the merge gate counts as "
            "PASS (pr-rollup-check.py TERMINAL_PASS). The PR that introduces an "
            "untagged version therefore clears this required check without "
            "verifying anything; only the post-merge push can fail it."
        ),
    },
}


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _norm_if(value: str) -> str:
    """Normalize a job-level `if:` for comparison (drop ${{ }}, collapse space)."""
    value = value.strip()
    if value.startswith("${{") and value.endswith("}}"):
        value = value[3:-2]
    return re.sub(r"\s+", " ", value.strip())


def _on_block(lines: list[str]) -> dict[str, tuple[int, list[str]]]:
    """Return {event: (line_index, block_lines)} for the top-level `on:` block."""
    events: dict[str, tuple[int, list[str]]] = {}
    start = None
    for i, line in enumerate(lines):
        if line.rstrip() == "on:" and not line.startswith(" "):
            start = i + 1
            break
    if start is None:
        return events
    i = start
    while i < len(lines):
        line = lines[i]
        if line.strip() and not line.startswith(" "):
            break  # next top-level key (jobs:)
        m = re.match(r"^  ([A-Za-z0-9_-]+):", line)
        if m:
            event = m.group(1)
            block: list[str] = []
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if nxt.strip() and not nxt.startswith("    "):
                    break  # next event key or end of on:
                block.append(nxt)
                j += 1
            events[event] = (i, block)
            i = j
            continue
        i += 1
    return events


def _pr_runs(events: dict[str, tuple[int, list[str]]]) -> tuple[bool, str]:
    """Would this workflow report a job on a pull_request targeting main?"""
    if "pull_request" not in events:
        return False, "workflow has no pull_request trigger"
    _, block = events["pull_request"]
    for i, line in enumerate(block):
        m = re.match(r"^    branches:\s*(.*)$", line)
        if not m:
            continue
        spec = m.group(1).strip()
        if spec.startswith("["):
            patterns = [_unquote(p) for p in spec.strip("[]").split(",") if p.strip()]
        else:
            patterns = []
            for follow in block[i + 1 :]:
                mm = re.match(r"^      -\s*(.+?)\s*$", follow)
                if not mm:
                    break
                patterns.append(_unquote(mm.group(1)))
        if "main" not in patterns:
            return False, "pull_request trigger excludes main (%s)" % (patterns,)
    return True, ""


def load_jobs(workflow_dir: Path) -> dict[str, dict]:
    """Index every workflow job by its reported check name."""
    jobs: dict[str, dict] = {}
    for path in sorted(workflow_dir.glob("*.yml")):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        start = None
        for i, line in enumerate(lines):
            if line.rstrip() == "jobs:" and not line.startswith(" "):
                start = i + 1
                break
        if start is None:
            continue
        events = _on_block(lines)
        for job in _collect_jobs(lines, start, path.name):
            job["pr_runs"], job["pr_reason"] = _pr_runs(events)
            if job["name"]:
                jobs.setdefault(job["name"], []).append(job)
    return jobs


def _collect_jobs(lines: list[str], start: int, workflow: str) -> list[dict]:
    """Second pass: build job records with their full body text."""
    out: list[dict] = []
    current = None
    for i in range(start, len(lines)):
        line = lines[i]
        if line.strip() and not line.startswith(" "):
            break
        m = re.match(r"^  ([A-Za-z0-9_-]+):\s*(?:#.*)?$", line)
        if m:
            if current and current["name"]:
                out.append(current)
            current = {"id": m.group(1), "workflow": workflow, "line": i,
                       "name": None, "if": None, "body": []}
            continue
        if current is None:
            continue
        current["body"].append(line)
        m = re.match(r"^    name:\s*(.+?)\s*$", line)
        if m:
            current["name"] = _unquote(m.group(1))
        m = re.match(r"^    if:\s*(.+?)\s*$", line)
        if m:
            current["if"] = _norm_if(_unquote(m.group(1)))
    if current and current["name"]:
        out.append(current)
    return out


def build(root: Path) -> dict:
    errors: list[str] = []
    contexts = json.loads((root / FALLBACK_RELPATH).read_text(encoding="utf-8"))
    required = contexts["required_contexts"]
    jobs = load_jobs(root / WORKFLOW_DIR)

    rows: list[dict] = []
    for context in required:
        row: dict = {"context": context, "status": "OK", "errors": []}
        spec = CHECKS.get(context)
        if spec is None:
            row["errors"].append("no curated behavior statement for this context")
        matches = jobs.get(context, [])
        if not matches:
            row["errors"].append("no workflow job reports this check name")
            row["status"] = "FAIL"
            errors.extend("%s: %s" % (context, e) for e in row["errors"])
            rows.append(row)
            continue
        if len(matches) > 1:
            where = ", ".join("%s:%s" % (m["workflow"], m["id"]) for m in matches)
            row["errors"].append("reported by more than one job (%s)" % where)
        job = matches[0]
        row.update({"workflow": job["workflow"], "job": job["id"],
                    "proves": spec["proves"] if spec else ""})

        if not job["pr_runs"]:
            row["errors"].append("does not run on pull_request: %s" % job["pr_reason"])
        if job["if"] is not None:
            skip = KNOWN_PR_SKIPS.get(context)
            if skip is None:
                row["errors"].append(
                    "undeclared job-level `if: %s` - the context may report SKIPPED "
                    "(counted as PASS) without proving its named behavior" % job["if"])
            elif (skip["workflow"] != job["workflow"] or skip["job"] != job["id"]
                  or _norm_if(skip["condition"]) != job["if"]):
                row["errors"].append(
                    "declared PR-skip gap is stale: registry has %s:%s if `%s`, "
                    "actual %s:%s if `%s`" % (
                        skip["workflow"], skip["job"], skip["condition"],
                        job["workflow"], job["id"], job["if"]))
            else:
                row["status"] = "GAP"
                row["pr_skip_condition"] = job["if"]
                row["gap"] = skip["gap"]
        else:
            skip = KNOWN_PR_SKIPS.get(context)
            if skip is not None:
                row["errors"].append(
                    "declared PR-skip gap is stale: the job now runs on pull_request")
        # The named behavior must be implemented in the job body whether the job
        # runs on PRs or is a declared push-only gap. A declared gap explains WHEN
        # the check proves nothing; it never licenses an empty check.
        body = "\n".join(job["body"])
        if spec:
            missing = [s for s in spec["must_contain"] if s not in body]
            if missing:
                row["errors"].append(
                    "job body no longer contains the named behavior: %s"
                    % ", ".join(repr(s) for s in missing))
        if row["errors"]:
            row["status"] = "FAIL"
            errors.extend("%s: %s" % (context, e) for e in row["errors"])
        rows.append(row)

    declared = set(KNOWN_PR_SKIPS)
    for context in KNOWN_PR_SKIPS:
        if context not in required:
            errors.append("declared PR-skip gap %r is no longer a required context" % context)
    result = {
        "result": "PASS" if not errors else "FAIL",
        "required_count": len(required),
        "contexts": rows,
        "gaps": [r for r in rows if r.get("status") == "GAP"],
        "declared_gap_count": len(declared),
        "undeclared_errors": errors,
    }
    return result


def print_text(result: dict) -> None:
    print("REQUIRED CONTEXT BEHAVIOR MAP (%d contexts)" % result["required_count"])
    print("")
    for n, row in enumerate(result["contexts"], 1):
        print("%d. %s" % (n, row["context"]))
        if row.get("workflow"):
            print("   reports from: %s job `%s`" % (row["workflow"], row["job"]))
        print("   on a PR: %s" % (
            "RUNS" if row["status"] == "OK" else
            "SKIPPED - counted as PASS, proves nothing" if row["status"] == "GAP" else
            "BROKEN"))
        if row.get("proves"):
            print("   proves: %s" % row["proves"])
        if row.get("pr_skip_condition"):
            print("   skip condition: `if: %s`" % row["pr_skip_condition"])
        if row.get("gap"):
            print("   GAP: %s" % row["gap"])
        for err in row["errors"]:
            print("   ERROR: %s" % err)
        print("")
    print("RESULT: %s - %d/%d contexts resolve; %d declared PR-skip gap(s); %d mapping error(s)" % (
        result["result"], sum(1 for r in result["contexts"] if not r["errors"]),
        result["required_count"], len(result["gaps"]), len(result["undeclared_errors"])))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(REPO_ROOT))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    try:
        result = build(Path(args.root))
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        print("ERROR: cannot build the required-context map: %s" % exc, file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print_text(result)
    return 0 if result["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
