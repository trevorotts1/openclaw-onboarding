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


class CompoundLegTagFix(unittest.TestCase):
    """MUTATION PROOF -- the defect an audit found reading resolve_required_legs()
    directly (not the tool's output, per this repo's own "paper feeds paper"
    lesson): ANY leg tag whose text merely CONTAINED the substring "live" --
    including a flat, un-parenthesized compound tag like "ONB + live" /
    "CC + live" -- fell into the zero-leg return. Zero-leg means NO repo git
    check runs at all; resolve_unit()'s zero-leg branch then trusts the
    ledger's OWN "verified" status-cell stamp. That is exactly the disease
    this file's module docstring says is structurally unreachable everywhere
    else in this file -- status asserted from a ledger claim instead of
    diffed from content.

    A related, second-order gap: a '+'-joined tag NOT containing the
    substring "live" (e.g. "ONB + n8n", "n8n + ONB", "ONB + GHL") fell
    through every branch to "unknown" -- fail-loud, so never a false DONE,
    but it also never checked the real, present ONB/CC repo leg via git,
    losing real evidence the tool could have produced.

    Every tag string below is copied VERBATIM from the real row in
    ledgers/skill6-blended-persona-kanban-v2-2026-07-13.md for the named
    unit (not synthesized) -- this proves the fix against the exact data the
    audit found broken. Offline / no network / no repo clone required --
    resolve_required_legs() is a pure function of the description string.
    """

    # unit_id -> (raw description column text, expected required repo legs)
    REAL_LIVE_TAG_UNITS = {
        "U29": (
            "[B/B-U15] (ONB + live, P2) ENV-MATRIX live proof: the ASSUMED VPS mount row + "
            "first-hour ground truth on one Mac + one VPS + stale-env preflight",
            {"onb"},
        ),
        "U86": (
            "[GK-24] (ONB + live, P1) Reproduce + fix the on-box presentation Python breakage "
            "by root-cause class (stale content / deps preflight / `--workspace` flag)",
            {"onb"},
        ),
        "U106": (
            "[E5-1 (G1)] (ONB + live, P2) **Communities / courses / channels build + "
            "live-prove** (Skill-6 companion to U30): live-create a community",
            {"onb"},
        ),
        "U112": (
            "[E5-7 (G5)] (ONB + live, P2) **Skill 6 bulk-send GHL workflow**: add many "
            "contacts via tag / arrays into a GHL workflow (surfaced in a live SMS firefight) "
            "— build + prove",
            {"onb"},
        ),
        "U41": (
            "[C/C-10] (CC + live, P1) Create-task proven end-to-end ON-BOX: shipped Playwright "
            "suite + workspace-scoped create + SSE assertion",
            {"cc"},
        ),
        "U43": (
            "[C/C-12] (CC + live, P1) Home-dashboard missing-cards: induced-failure proof on "
            "the operator box + fleet version/build audit field",
            {"cc"},
        ),
    }

    REAL_UNPARSEABLE_COMPOUND_UNITS = {
        "U63": (
            "[GK-01] (ONB + n8n, P0) **P0 live**: fix the podcast publish path that failed on "
            "`image_url = null` + fail-closed entry guard + retry the episode",
            {"onb"},
        ),
        "U71": (
            "[GK-09] (ONB + GHL, P1) Clear the WAF/edge 403 on `verify-imported`; run the "
            "never-yet-run snapshot chain end-to-end once",
            {"onb"},
        ),
        "U74": (
            "[GK-12] (n8n + ONB, P1) Canonicalize the podcast pipeline per D19 (kill the "
            "double-publish risk)",
            {"onb"},
        ),
    }

    def test_naive_substring_check_reproduces_the_bug(self):
        """PRECONDITION / proves the bug was real, not assumed: reproduce the
        exact pre-fix substring check inline and confirm it really did
        classify these real 'ONB + live' / 'CC + live' rows as zero-leg."""
        def naive_classify(tag_l):
            if "live" in tag_l or "read-only" in tag_l or tag_l in ("n/a", "na", "doc", "none"):
                return "zero-leg"
            return "not-zero-leg"

        for uid, (desc, _expected_legs) in self.REAL_LIVE_TAG_UNITS.items():
            tag = usc.parse_leg_requirement(desc)
            self.assertEqual(
                naive_classify(tag.strip().lower()), "zero-leg",
                f"PRECONDITION FAILED for {uid}: the naive pre-fix substring check no longer "
                f"reproduces zero-leg on tag {tag!r} -- update this precondition.",
            )

    def test_real_live_compound_tags_resolve_their_repo_leg_not_zero_leg(self):
        """FAILS on pre-fix code (mode would be 'zero-leg', legs would be
        empty -- no git check, verdict falls through to trusting the
        ledger's status cell). PASSES on shipped code: mode 'compound',
        legs = the real repo leg(s)."""
        for uid, (desc, expected_legs) in self.REAL_LIVE_TAG_UNITS.items():
            legs, mode, note = usc.resolve_required_legs(desc)
            self.assertEqual(mode, "compound", f"{uid}: expected mode 'compound', got {mode!r} ({note})")
            self.assertEqual(legs, expected_legs, f"{uid}: expected legs {expected_legs}, got {legs} ({note})")
            self.assertNotEqual(mode, "zero-leg", f"REGRESSION for {uid}: fell back to zero-leg -- repo git check skipped again.")

    def test_real_unparseable_compound_tags_now_resolve_their_repo_leg(self):
        """FAILS on pre-fix code (mode would be 'unknown', legs empty -- the
        real ONB leg present in the tag was never checked). PASSES on shipped
        code: mode 'compound', legs = {'onb'} for all three, regardless of
        whether ONB is the first or second '+'-joined token."""
        for uid, (desc, expected_legs) in self.REAL_UNPARSEABLE_COMPOUND_UNITS.items():
            legs, mode, note = usc.resolve_required_legs(desc)
            self.assertEqual(mode, "compound", f"{uid}: expected mode 'compound', got {mode!r} ({note})")
            self.assertEqual(legs, expected_legs, f"{uid}: expected legs {expected_legs}, got {legs} ({note})")

    def test_pure_live_tag_with_no_repo_component_stays_zero_leg(self):
        """Guard against over-correction: a tag that is GENUINELY non-repo
        (no onb/cc component at all) must still resolve zero-leg, not get
        dragged into 'unknown' or invent a repo leg that isn't there. Covers
        both a bare single-word tag and a '+'-joined tag where every part is
        a recognized non-repo token."""
        legs, mode, note = usc.resolve_required_legs(
            "[X] (live, P1) bare non-repo, no repo component at all"
        )
        self.assertEqual(mode, "zero-leg", f"got {mode!r}: {note}")
        self.assertEqual(legs, set())

        legs, mode, note = usc.resolve_required_legs(
            "[X] (GHL + n8n, P1) bare compound, both parts non-repo"
        )
        self.assertEqual(mode, "zero-leg", f"got {mode!r}: {note}")
        self.assertEqual(legs, set())

    def test_unparseable_compound_never_silently_degrades_to_ledger_trust(self):
        """The tool's whole reason to exist: an unparseable tag must fail
        LOUD (an explicit 'unknown' verdict the caller cannot mistake for
        DONE), never silently fall back to trusting the ledger's own status
        cell. A '+'-joined tag with a garbled/mistyped repo token ('0NB'
        instead of 'ONB') must NOT be guessed as zero-leg (which would
        silently trust the ledger) and must NOT be guessed as a repo leg
        either (which would assert a fact never git-checked) -- it must come
        back 'unknown'."""
        legs, mode, note = usc.resolve_required_legs("[X] (0NB + live, P1) garbled repo token")
        self.assertEqual(mode, "unknown", f"must fail loud, got {mode!r}: {note}")
        self.assertEqual(legs, set())

    def test_unparseable_compound_end_to_end_via_resolve_unit_is_unknown_not_done(self):
        """End-to-end (still offline -- skip_ci and a throwaway fixture
        ledger, no real git dirs touched): a unit whose row carries a
        garbled '+'-joined tag must resolve_unit() to UNKNOWN, and MUST NOT
        read as DONE even though the ledger's own status cell says
        'verified' -- the exact silent-ledger-trust shape this fix exists
        to prevent."""
        with tempfile.TemporaryDirectory() as td:
            ledger_path = Path(td) / "fixture-ledger.md"
            ledger_path.write_text(
                "| U999001 | [X] (0NB + live, P1) garbled repo token | label | verified | evidence | ts |\n"
            )
            result = usc.resolve_unit(
                "U999001", "/nonexistent-onb", "/nonexistent-cc", [str(ledger_path)], skip_ci=True
            )
            self.assertEqual(
                result["verdict"], "UNKNOWN",
                f"REGRESSION: an unparseable '+'-joined tag must never resolve DONE off the "
                f"ledger's own 'verified' status cell -- got {result['verdict']}: {result}",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
