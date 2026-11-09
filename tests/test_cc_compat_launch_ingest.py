#!/usr/bin/env python3
"""CON-23 compat check: the pinned Command Center tag must ship the launch ingest route.

Fleet boxes deploy cc-compat.json commandCenter.pinnedTag and never main, so a
pin older than the release that added src/app/api/launch-runs/ingest/route.ts
answers 404 to every launch/run event producer.

  * floor test (offline, always runs): pinnedTag >= v7.6.125, the first CC tag
    that contains the route (v7.6.124 and older do not).
  * tree test: `git ls-tree <pinnedTag> <route>` returns the file. Reads a local
    Command Center clone from CC_REPO_DIR when set, else the GitHub API through
    `gh`. Skips only when neither source is reachable; a definite "path absent"
    answer fails.
  * control: the floor comparison refuses the old v7.6.112 pin.

Run: python3 -m pytest tests/test_cc_compat_launch_ingest.py -q
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "shared-utils"))
from cc_compat import _version_gte, load_cc_compat  # noqa: E402

ROUTE = "src/app/api/launch-runs/ingest/route.ts"
FIRST_TAG_WITH_ROUTE = "v7.6.125"


def _pin() -> tuple[str, str]:
    cc = load_cc_compat(_REPO_ROOT)["commandCenter"]
    return cc["repo"], cc["pinnedTag"]


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


def test_pinned_tag_is_at_or_above_first_release_with_launch_ingest():
    _, pinned = _pin()
    assert _version_gte(pinned, FIRST_TAG_WITH_ROUTE), (
        f"cc-compat.json pinnedTag {pinned} predates {FIRST_TAG_WITH_ROUTE}, the first "
        f"Command Center tag containing {ROUTE}"
    )


def test_floor_comparison_refuses_the_old_pin():
    assert not _version_gte("v7.6.112", FIRST_TAG_WITH_ROUTE)
    assert not _version_gte("v7.6.124", FIRST_TAG_WITH_ROUTE)
    assert _version_gte(FIRST_TAG_WITH_ROUTE, FIRST_TAG_WITH_ROUTE)


def test_pinned_tag_tree_contains_launch_ingest_route():
    repo, pinned = _pin()
    clone = os.environ.get("CC_REPO_DIR")
    if clone:
        res = _run(["git", "-C", clone, "ls-tree", pinned, ROUTE])
        if res.returncode != 0:
            pytest.skip(f"CC_REPO_DIR cannot resolve {pinned}: {res.stderr.strip()[:120]}")
        assert ROUTE in res.stdout, f"git ls-tree {pinned} {ROUTE} returned nothing"
        return
    if not shutil.which("gh"):
        pytest.skip("no CC_REPO_DIR and no gh CLI: tree check not reachable")
    res = _run(["gh", "api", f"repos/{repo}/contents/{ROUTE}?ref={pinned}", "--jq", ".path"])
    if res.returncode == 0:
        assert res.stdout.strip() == ROUTE
        return
    if "HTTP 404" in res.stderr + res.stdout:
        pytest.fail(f"{repo}@{pinned} has no {ROUTE}")
    pytest.skip(f"GitHub API not reachable for {repo}: {res.stderr.strip()[:120]}")
