#!/usr/bin/env python3
"""Focused trace for the required-check -> behavior map (PBB-069 / T-42).

Runs scripts/ci/required_context_behaviors.py against the real tree and against
deliberately broken copies of it. The broken copies are the point: a mapping
check nobody has ever seen fail is indistinguishable from one that cannot fail.

  python3 tests/unit/required-context-behaviors.test.py

Exit 0 only when the real tree maps cleanly AND every broken copy is rejected.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts/ci/required_context_behaviors.py"
FALLBACK = Path("scripts/pr-rollup-required-contexts.fallback.json")
WORKFLOWS = Path(".github/workflows")


def run_map(root: Path) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, "-I", str(MODULE), "--root", str(root), "--json"],
        capture_output=True, text=True)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise AssertionError("module did not emit JSON (rc=%d)\nstdout=%s\nstderr=%s"
                             % (proc.returncode, proc.stdout, proc.stderr))
    return proc.returncode, payload


def broken_workflows(mutate) -> Path:
    """Copy only what the map reads, apply mutate(workflow_dir), return the root."""
    tmp = Path(tempfile.mkdtemp(prefix="required-contexts-"))
    (tmp / FALLBACK.parent).mkdir(parents=True)
    shutil.copy2(ROOT / FALLBACK, tmp / FALLBACK)
    shutil.copytree(ROOT / WORKFLOWS, tmp / WORKFLOWS)
    mutate(tmp / WORKFLOWS)
    return tmp


def rewrite(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, "fixture drift: %r not found in %s" % (old, path)
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def expect_rejected(label: str, root: Path, needle: str) -> None:
    rc, payload = run_map(root)
    assert rc == 1, "%s: expected exit 1 on the broken tree, got %d" % (label, rc)
    assert payload["result"] == "FAIL", "%s: expected FAIL, got %s" % (label, payload["result"])
    joined = "\n".join(payload["undeclared_errors"])
    assert needle in joined, "%s: expected %r in errors, got:\n%s" % (label, needle, joined)
    print("ok   %-38s rejected: %s" % (label, needle))


def main() -> int:
    # 1. The real tree must map cleanly, with G1 declared as the one PR-skip gap.
    rc, payload = run_map(ROOT)
    assert rc == 0, "real tree failed the map:\n%s" % "\n".join(payload["undeclared_errors"])
    assert payload["required_count"] == 8, payload["required_count"]
    assert len(payload["contexts"]) == 8
    assert len(payload["gaps"]) == 1, [g["context"] for g in payload["gaps"]]
    gap = payload["gaps"][0]
    assert gap["context"].startswith("G1 — version file change"), gap["context"]
    assert gap["pr_skip_condition"] == "github.event_name == 'push'", gap["pr_skip_condition"]
    for row in payload["contexts"]:
        assert row.get("workflow") and row.get("job"), row
        assert row.get("proves"), row
    print("ok   real tree: 8/8 contexts resolve; 1 declared PR-skip gap (G1)")

    cases = []

    # 2. Renamed job -> the required context no longer reports at all.
    def rename(wd: Path) -> None:
        rewrite(wd / "qc-static.yml", "    name: QC static invariants",
                "    name: QC static invariants (renamed)")
    cases.append(("renamed required job", rename, "no workflow job reports"))

    # 3. A PR skip appearing without a declared gap -> silent green, caught.
    def add_skip(wd: Path) -> None:
        rewrite(wd / "ghl-mcp-supervised-guard.yml", "  ghl-mcp-pin-gate:\n",
                "  ghl-mcp-pin-gate:\n    if: github.event_name == 'push'\n")
    cases.append(("undeclared PR skip on pin gate", add_skip, "undeclared job-level"))

    # 4. G1's skip removed -> the declared gap is stale, not silently kept.
    def close_gap(wd: Path) -> None:
        rewrite(wd / "version-consistency.yml", "    if: github.event_name == 'push'\n", "")
    cases.append(("G1 gap closed without registry update", close_gap,
                  "declared PR-skip gap is stale"))

    # 5. A workflow that stops triggering on pull_request -> context never reports.
    def drop_pr_trigger(wd: Path) -> None:
        rewrite(wd / "qc-static.yml", "  pull_request:\n", "  workflow_dispatch:\n")
    cases.append(("required workflow off pull_request", drop_pr_trigger,
                  "does not run on pull_request"))

    # 6. The named behavior gutted from the job body -> mapping keeps name, loses proof.
    def gut_body(wd: Path) -> None:
        path = wd / "version-consistency.yml"
        text = path.read_text(encoding="utf-8")
        assert "Only ANNOTATED tags are accepted" in text
        path.write_text(text.replace("Only ANNOTATED tags are accepted", "tag accepted"),
                        encoding="utf-8")
    cases.append(("named-behavior assertion removed", gut_body, "no longer contains the named behavior"))

    for label, mutate, needle in cases:
        root = broken_workflows(mutate)
        try:
            expect_rejected(label, root, needle)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    print("PASS: %d broken inputs rejected, real tree maps cleanly" % len(cases))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print("FAIL: %s" % exc, file=sys.stderr)
        sys.exit(1)
