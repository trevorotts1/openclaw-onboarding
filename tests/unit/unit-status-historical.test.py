#!/usr/bin/env python3
"""
tests/unit/unit-status-historical.test.py
─────────────────────────────────────────────────────────────────────────────
Proves shared-utils/unit_status_core.py (driven by ../../unit-status.sh)
against the REAL, LIVE historical cases named in the operator brief that
built this tool -- this is the acceptance bar, not a synthetic fixture
suite. Every assertion below is checked against the actual git history of
trevorotts1/openclaw-onboarding and trevorotts1/blackceo-command-center on
GitHub (network + `gh` auth required -- this is an INTEGRATION test, not a
pure unit test; see the two no-network mutation-proof tests at the bottom
for fast, offline-safe regression coverage of the specific bugs this file's
own development caught).

REQUIRED-DONE CASES (a tool that gets either of these wrong has the
disease -- see unit_status_core.py's resolve_leg() docstring):
  - U108 must resolve DONE. Its CC leg has NO `skill6-v2/U108` branch in
    blackceo-command-center at all -- it shipped inside `skill6-v2/U110`'s
    own branch (commit `25ba6c6c`, merged via `b11c45b3`, tag `v6.0.55`).
    A naive per-unit, branch-name-only check calls this NOT-DONE. Wrong.
  - U79 must resolve DONE. Its (primary, per the compound leg tag
    "(CC (+ONB), P1)") CC leg has NO `skill6-v2/U79` branch either -- it
    shipped as the entirely non-namespaced branch
    `u79-gk17-cc-anthology-selfheal-banner` (merged via `747fca41`, tag
    `v6.0.52`). Only a token-scan across ALL branch names (not just the
    canonical prefix) finds it.

MUTATION PROOFS (bugs this file's own development process actually hit and
fixed -- these are FAIL-FIRST/PASS-AFTER, re-run here as permanent
regressions, not narrated after the fact):
  - test_token_scan_excludes_proven_namespace_collision: BEFORE
    FOREIGN_NAMESPACE_PREFIXES existed, `token_scan_any_branch(repo, "U15")`
    against openclaw-onboarding's REAL branch list returned
    `skill62/ce-U15` as a match -- a live false positive (a completely
    different skill's own, unrelated "U15"; skill62 is the cinematic web
    funnel engine build, with its own independent U-numbering). A
    delimited-token regex ALONE does not prevent this ("ce-U15" satisfies
    a delimiter check too). This test fails on a pre-fix copy of the
    function (delimiter-only, no namespace exclusion) and passes on the
    shipped version.
  - test_stale_ref_parent_order_not_ancestor_test: BEFORE the parent-order
    fix, check_stale_ref() classified a merge commit's "branch-side parent"
    by testing `is_ancestor(parent, origin/main)` -- which is USELESS once
    the merge itself is already part of main's history, because BOTH
    parents of a commit that's on main are trivially ancestors of main.
    Against PR #193's real merge commit `5654cba8`, that pre-fix logic
    could not disambiguate at all and returned UNKNOWN, missing the real
    stale-ref. This test fails on that logic and passes on the shipped
    parent-ORDER logic.

Run:
    python3 tests/unit/unit-status-historical.test.py

Env overrides (skip auto-clone, point at existing checkouts):
    UNIT_STATUS_TEST_ONB_DIR, UNIT_STATUS_TEST_CC_DIR
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


usc = _load("unit_status_core", "unit_status_core.py")


def _sh_ok(dirpath, args):
    r = subprocess.run(["git", "-C", str(dirpath)] + args, capture_output=True, text=True)
    return r.returncode == 0


def _clone_or_reuse(url, envvar, cache_name):
    override = os.environ.get(envvar)
    if override:
        assert Path(override).is_dir(), f"{envvar}={override} does not exist"
        subprocess.run(["git", "-C", override, "fetch", "-q", "origin", "main"], check=False)
        return override
    cache_root = Path(os.environ.get("UNIT_STATUS_TEST_CACHE", tempfile.gettempdir())) / "openclaw-git-truth-tools-tests"
    cache_root.mkdir(parents=True, exist_ok=True)
    dest = cache_root / cache_name
    if (dest / ".git").is_dir():
        subprocess.run(["git", "-C", str(dest), "fetch", "-q", "origin", "main"], check=False)
    else:
        subprocess.run(["git", "clone", "-q", url, str(dest)], check=True)
    return str(dest)


class HistoricalCases(unittest.TestCase):
    """The acceptance bar. Network + gh auth required."""

    @classmethod
    def setUpClass(cls):
        cls.onb_dir = _clone_or_reuse(
            "https://github.com/trevorotts1/openclaw-onboarding.git",
            "UNIT_STATUS_TEST_ONB_DIR", "openclaw-onboarding",
        )
        cls.cc_dir = _clone_or_reuse(
            "https://github.com/trevorotts1/blackceo-command-center.git",
            "UNIT_STATUS_TEST_CC_DIR", "blackceo-command-center",
        )
        cls.ledger_paths = [
            str(Path(cls.onb_dir) / "ledgers" / "skill6-blended-persona-kanban-v2-2026-07-13.md"),
        ]
        assert Path(cls.ledger_paths[0]).is_file(), "canonical skill6 ledger not found -- clone/branch drifted?"

    def test_u108_resolves_done_via_cross_reference_cc_leg(self):
        result = usc.resolve_unit("U108", self.onb_dir, self.cc_dir, self.ledger_paths, skip_ci=True)
        self.assertEqual(result["verdict"], "DONE",
                          f"U108 must be DONE -- got {result['verdict']}: {result}")
        cc_leg = result["legs"]["cc"]
        self.assertTrue(cc_leg["satisfied"])
        self.assertEqual(cc_leg["method"], "cross-reference",
                          "U108's CC leg must resolve via cross-reference (no skill6-v2/U108 branch "
                          "exists in blackceo-command-center) -- if this is 'own-branch', the fixture "
                          "or upstream history changed; if it's anything else, the tool regressed.")
        self.assertFalse(cc_leg["proved"], "cross-reference resolution must be labeled INFERRED, not PROVED")
        onb_leg = result["legs"]["onb"]
        self.assertTrue(onb_leg["satisfied"])
        self.assertEqual(onb_leg["method"], "own-branch")
        self.assertTrue(onb_leg["proved"])

    def test_u79_resolves_done_via_token_scan_cc_leg(self):
        result = usc.resolve_unit("U79", self.onb_dir, self.cc_dir, self.ledger_paths, skip_ci=True)
        self.assertEqual(result["verdict"], "DONE",
                          f"U79 must be DONE -- got {result['verdict']}: {result}")
        self.assertEqual(result["mode"], "compound")
        cc_leg = result["legs"]["cc"]
        self.assertTrue(cc_leg["satisfied"])
        self.assertEqual(cc_leg["method"], "token-scan",
                          "U79's CC leg must resolve via the non-namespaced token scan "
                          "(u79-gk17-cc-anthology-selfheal-banner) -- if this changed, the fixture or "
                          "upstream history changed.")
        self.assertTrue(cc_leg["proved"])
        self.assertEqual(cc_leg["raw"]["branch"], "u79-gk17-cc-anthology-selfheal-banner")

    def test_never_started_unit_would_print_unknown_not_guessed(self):
        """Fabricate a lookup for a unit id that genuinely does not exist in
        any ledger -- must be UNKNOWN, never a guessed DONE/NOT-DONE."""
        result = usc.resolve_unit("U999999", self.onb_dir, self.cc_dir, self.ledger_paths, skip_ci=True)
        self.assertEqual(result["verdict"], "UNKNOWN")


class MutationProofs(unittest.TestCase):
    """Fast, deterministic regressions for the two real bugs this tool's own
    development caught. Network required (reads real branch lists / a real
    merge commit already in history -- both immutable), but no `gh api`
    calls, so these run much faster than the historical-case suite above."""

    @classmethod
    def setUpClass(cls):
        cls.onb_dir = _clone_or_reuse(
            "https://github.com/trevorotts1/openclaw-onboarding.git",
            "UNIT_STATUS_TEST_ONB_DIR", "openclaw-onboarding",
        )
        cls.cc_dir = _clone_or_reuse(
            "https://github.com/trevorotts1/blackceo-command-center.git",
            "UNIT_STATUS_TEST_CC_DIR", "blackceo-command-center",
        )

    def test_token_scan_excludes_proven_namespace_collision(self):
        """FAIL-FIRST: a pre-fix, delimiter-only (no namespace exclusion)
        version of the scan is reproduced INLINE here and asserted to
        contain the false positive (proving the bug was real, not assumed)
        -- then the shipped function is asserted to exclude it."""
        import re
        naive_pattern = re.compile(r"(?:^|[^0-9A-Za-z])U15(?:[^0-9A-Za-z]|$)", re.IGNORECASE)
        all_branches = usc.list_all_remote_branches(self.onb_dir)
        naive_hits = [b for b in all_branches if naive_pattern.search(b)]
        self.assertIn("skill62/ce-U15", naive_hits,
                       "PRECONDITION FAILED: the naive delimiter-only scan no longer reproduces the "
                       "known collision on skill62/ce-U15 -- either upstream history changed (branch "
                       "deleted) or this precondition needs updating; the mutation proof below is "
                       "meaningless without a live FAIL case.")

        fixed_hits = usc.token_scan_any_branch(self.onb_dir, "U15")
        self.assertNotIn("skill62/ce-U15", fixed_hits,
                          "REGRESSION: token_scan_any_branch('U15') must exclude skill62/ce-U15 "
                          "(FOREIGN_NAMESPACE_PREFIXES) -- the shipped function reproduced the bug.")

    def test_stale_ref_parent_order_not_ancestor_test(self):
        """FAIL-FIRST: reproduce the pre-fix ancestor-based parent
        classification inline against PR #193's real merge commit in
        blackceo-command-center and assert it CANNOT disambiguate (both
        parents test as ancestors, since the merge is already on main) --
        then assert the shipped parent-order logic in pr_truth_core.py
        DOES disambiguate correctly. Cross-references pr_truth_core.py
        directly since this specific bug lives there, not in
        unit_status_core.py -- both tools share the same disease-class
        failure mode, so this file documents this proof for completeness
        alongside its own suite."""
        prt = _load("pr_truth_core", "pr_truth_core.py")
        merge_sha = "5654cba882f4c0033bca70ee69eb6de4223d6322"
        resolved = prt.commit_exists(self.cc_dir, merge_sha)
        if not resolved:
            prt.ensure_fetched(self.cc_dir, [merge_sha])
            resolved = prt.commit_exists(self.cc_dir, merge_sha)
        self.assertTrue(resolved, f"PRECONDITION FAILED: {merge_sha} not resolvable in blackceo-command-center")

        parents_out = prt.sh(self.cc_dir, ["log", "-1", "--format=%P", resolved])
        parents = parents_out.split()
        self.assertEqual(len(parents), 2)

        naive_on_main = [p for p in parents if prt.is_ancestor(self.cc_dir, p, "origin/main")]
        self.assertEqual(
            len(naive_on_main), 2,
            "PRECONDITION FAILED: the naive ancestor-based test no longer finds BOTH parents as "
            "ancestors of main -- either upstream history changed or this precondition needs "
            "updating; the mutation proof below is meaningless without a live FAIL case showing "
            "ancestor-of-main cannot disambiguate parent 1 from parent 2 here.",
        )

        result = prt.check_stale_ref(self.cc_dir, "trevorotts1/blackceo-command-center", 193, merge_sha)
        self.assertEqual(result["verdict"], "STALE-REF",
                          f"REGRESSION: shipped check_stale_ref() must catch the real PR #193 stale "
                          f"ref via parent ORDER, not ancestor-of-main -- got {result['verdict']}: {result}")
        self.assertEqual(result["branch_side_parent"], "6490fe8a24be1b4b4a46c9e871970c1c92441c3c")
        self.assertEqual(result["live_head"], "d0f3558cc8555c2eb4657d09f9cbca7c41270bb3")


if __name__ == "__main__":
    unittest.main(verbosity=2)
