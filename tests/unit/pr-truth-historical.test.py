#!/usr/bin/env python3
"""
tests/unit/pr-truth-historical.test.py
─────────────────────────────────────────────────────────────────────────────
Proves shared-utils/pr_truth_core.py (driven by ../../pr-truth.sh) against
the REAL, LIVE historical cases named in the operator brief -- the
acceptance bar, not a synthetic fixture suite. Network + `gh` auth
required (integration test).

REQUIRED CASES:
  - `pr-truth.sh 193 --repo trevorotts1/blackceo-command-center --stale-ref
    5654cba882f4c0033bca70ee69eb6de4223d6322` must return STALE-REF. The
    merge commit's branch-side parent is `6490fe8a24be1b4b4a46c9e871970c1c92441c3c`;
    the PR's real, live head (branch `skill6-v2/U59-cc-d15`) is
    `d0f3558cc8555c2eb4657d09f9cbca7c41270bb3`, one commit further --
    ancestry of the merged parent alone is a TRUE ancestor of main (looks
    perfect) and cannot catch this; only a merge-commit-vs-live-head
    comparison can. Independently re-confirmed here: the live head's
    unique commit touches `src/lib/db/migrations.ts` +
    `tests/unit/u59-da-challenges-round-trip.test.ts`, and a content diff
    (not ancestry) shows `src/lib/db/migrations.ts` is genuinely absent
    from `origin/main`'s current tip.
  - `pr-truth.sh 617 --supersedes 599` must return NO. PR #599's tree has
    34 files (all of `ledgers/evidence/U87-GK-25/*` plus
    `ledgers/ratified-decisions-2026-07-16.md`) that are COMPLETELY ABSENT
    from PR #617's tree -- not merely modified, entirely missing. A tool
    that answers YES here would have let #617 close #599 and orphan real,
    already-scored (9.4) work.

Run:
    python3 tests/unit/pr-truth-historical.test.py

Env overrides (skip auto-clone, point at existing checkouts):
    PR_TRUTH_TEST_ONB_DIR, PR_TRUTH_TEST_CC_DIR
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_SHARED_UTILS = _REPO_ROOT / "shared-utils"
assert _SHARED_UTILS.is_dir()

sys.path.insert(0, str(_SHARED_UTILS))


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, _SHARED_UTILS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod


prt = _load("pr_truth_core", "pr_truth_core.py")


def _clone_or_reuse(url, envvar, cache_name):
    override = os.environ.get(envvar)
    if override:
        assert Path(override).is_dir(), f"{envvar}={override} does not exist"
        subprocess.run(["git", "-C", override, "fetch", "-q", "origin", "main"], check=False)
        return override
    cache_root = Path(os.environ.get("PR_TRUTH_TEST_CACHE", tempfile.gettempdir())) / "openclaw-git-truth-tools-tests"
    cache_root.mkdir(parents=True, exist_ok=True)
    dest = cache_root / cache_name
    if (dest / ".git").is_dir():
        subprocess.run(["git", "-C", str(dest), "fetch", "-q", "origin", "main"], check=False)
    else:
        subprocess.run(["git", "clone", "-q", url, str(dest)], check=True)
    return str(dest)


class HistoricalCases(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.onb_dir = _clone_or_reuse(
            "https://github.com/trevorotts1/openclaw-onboarding.git",
            "PR_TRUTH_TEST_ONB_DIR", "openclaw-onboarding",
        )
        cls.cc_dir = _clone_or_reuse(
            "https://github.com/trevorotts1/blackceo-command-center.git",
            "PR_TRUTH_TEST_CC_DIR", "blackceo-command-center",
        )

    def test_pr193_stale_ref_caught(self):
        merge_sha = "5654cba882f4c0033bca70ee69eb6de4223d6322"
        result = prt.check_stale_ref(self.cc_dir, "trevorotts1/blackceo-command-center", 193, merge_sha)
        self.assertEqual(result["verdict"], "STALE-REF", f"got: {result}")
        self.assertEqual(result["merge_sha"], "5654cba882f4c0033bca70ee69eb6de4223d6322")
        self.assertEqual(result["branch_side_parent"], "6490fe8a24be1b4b4a46c9e871970c1c92441c3c")
        self.assertEqual(result["live_head"], "d0f3558cc8555c2eb4657d09f9cbca7c41270bb3")
        self.assertIn("src/lib/db/migrations.ts", result["genuinely_missing_paths"],
                      "the content-diff corroboration must independently confirm real missing content, "
                      "not just report a commit-count gap")
        # Sanity: ancestry of the STALE parent alone is a true ancestor --
        # this is exactly why ancestry cannot catch this form on its own.
        self.assertTrue(prt.is_ancestor(self.cc_dir, result["branch_side_parent"], "origin/main"))
        self.assertFalse(prt.is_ancestor(self.cc_dir, result["live_head"], "origin/main"),
                          "the real head must NOT be an ancestor of main -- if it now is, someone "
                          "landed the missing content and this fixture needs updating")

    def test_pr617_does_not_supersede_pr599(self):
        result = prt.check_supersedes(self.onb_dir, "trevorotts1/openclaw-onboarding", 617, 599)
        self.assertEqual(result["verdict"], "NO", f"got: {result}")
        self.assertGreater(len(result["missing_from_this"]), 0)
        # The specific, named evidence: the whole U87-GK-25 evidence directory
        # and the ratified-decisions ledger must be among what's missing.
        missing_set = set(result["missing_from_this"])
        self.assertIn("ledgers/evidence/U87-GK-25/README.md", missing_set)
        self.assertIn("ledgers/ratified-decisions-2026-07-16.md", missing_set)
        self.assertTrue(any(p.startswith("ledgers/evidence/U87-GK-25/") for p in missing_set))

    def test_pr599_supersedes_pr617_direction_is_not_assumed(self):
        """The reverse check: does #599 (the fuller PR) contain everything
        #617 has? Must independently re-diff -- never assumed from the
        first direction's result. (Not part of the required acceptance
        bar, but 'diffed live, both ways' is explicit in the brief.)"""
        result = prt.check_supersedes(self.onb_dir, "trevorotts1/openclaw-onboarding", 599, 617)
        self.assertIn(result["verdict"], ("YES", "PARTIAL"))
        self.assertEqual(len(result["missing_from_this"]), 0,
                          "#599 should be missing nothing #617 has, per the earlier live diff "
                          "(0 files exist in 617's tree but not 599's)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
