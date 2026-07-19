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


class Defect1CIResolvesOnHeadShaNotMergeCommit(unittest.TestCase):
    """MUTATION PROOF for DEFECT 1 (the CI check ran against the SYNTHETIC
    MERGE commit -- leg_result["raw"]["merge_sha"] -- instead of the leg's
    OWN head sha, i.e. the commit CI actually ran on). Merge commits carry
    ZERO check-runs on this repo's CI configuration (pull_request-triggered
    Actions record check-runs against the PR branch's head, never the
    merge commit GitHub creates afterward on main) -- so the pre-fix tool
    printed "CI: no-data" for EVERY unit, always, regardless of the real
    CI outcome. Empirically re-confirmed live below (network + gh auth
    required) against U11's REAL commits in openclaw-onboarding, copied
    verbatim from `gh api .../check-runs` output at the time this fix was
    written -- not synthesized."""

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

    def test_u11_onb_leg_merge_commit_precondition_still_has_zero_checkruns(self):
        """PRECONDITION: the exact merge commit the pre-fix tool queried for
        U11's ONB leg must still carry 0 check-runs -- if GitHub ever starts
        recording check-runs against merge commits on this repo, the bug
        this fix targets no longer exists and this whole test class needs
        re-deriving, not blind re-running."""
        merge_sha = "93e4c1ed596608410abf599edf37c8f8ac9069f8"
        result = usc.ci_status_for_sha("trevorotts1/openclaw-onboarding", merge_sha)
        self.assertEqual(
            result["status"], "no-data",
            f"PRECONDITION FAILED: merge commit {merge_sha} now has check-run data "
            f"({result}) -- this fix's premise (merge commits carry ZERO check-runs "
            f"on this repo's CI config) no longer holds; re-derive before trusting the "
            f"assertions below.",
        )

    def test_u11_resolve_unit_ci_uses_real_head_sha_not_merge_commit(self):
        """FAILS on pre-fix code: leg_result["ci"] would be status="no-data",
        total=0 (queried the merge commit, which has 0 runs), and would have
        NO "head_sha" key at all (pre-fix ci_status_for_sha() never added
        one). PASSES on shipped code: status="green", total>=1, and
        head_sha equals U11's REAL branch tip in each repo (not the merge
        commit) -- both hardcoded here verbatim from real `git rev-parse`
        output, not synthesized."""
        result = usc.resolve_unit("U11", self.onb_dir, self.cc_dir, self.ledger_paths, skip_ci=False)
        onb_ci = result["legs"]["onb"]["ci"]
        self.assertEqual(onb_ci["status"], "green", f"REGRESSION: U11 ONB leg CI must be green -- got {onb_ci}")
        self.assertGreaterEqual(onb_ci["total"], 1, f"REGRESSION: U11 ONB leg CI must show real check-run data -- got {onb_ci}")
        self.assertEqual(onb_ci["failure"], 0)
        self.assertEqual(
            onb_ci["head_sha"], "f3d751f5f19f6d2edd8921382a6a4975e39a3ae8",
            "REGRESSION: CI must be checked against U11's real ONB branch tip, not its merge commit.",
        )

        cc_ci = result["legs"]["cc"]["ci"]
        self.assertEqual(cc_ci["status"], "green", f"REGRESSION: U11 CC leg CI must be green -- got {cc_ci}")
        self.assertGreaterEqual(cc_ci["total"], 1, f"REGRESSION: U11 CC leg CI must show real check-run data -- got {cc_ci}")
        self.assertEqual(
            cc_ci["head_sha"], "d618f332b4748a34cf4831ab05771ed3f96c954a",
            "REGRESSION: CI must be checked against U11's real CC branch tip, not its merge commit.",
        )


class Defect2RealFossilAndNoDataCases(unittest.TestCase):
    """MUTATION PROOF for DEFECT 2 (a real 18-unit triage found every
    historic `failure > 0` on an exact head sha was noise no longer present
    on current main -- a QC gate tripping on a DIFFERENT unit's evidence
    file, a version-bump gate, an infra flake -- yet a naive "green on the
    exact sha" tool would have missed that entirely if it silently upgraded
    these to green, and a naive "red on the exact sha" tool would wrongly
    flag units that are actually fine). U24's ONB leg's real head sha
    genuinely failed `G3 -- skill content change requires skill-version.txt
    bump` historically; that exact check NAME now passes on current main --
    a real, live-verified fossil, not a synthesized fixture. U5's CC leg
    has a real head sha with 0 retained check-runs at all -- a genuine
    `no-data` case (old direct-push era), proven distinct from DEFECT 1's
    bug because this tool now records exactly WHICH sha (head, not merge)
    it checked and came up empty."""

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

    def test_u24_merge_commit_precondition_still_has_zero_checkruns(self):
        """PRECONDITION, same shape as Defect1's -- U24's merge commit must
        still carry 0 check-runs, or this test needs re-deriving."""
        merge_sha = "1de2099a51a61bcf1266291b29cb02a25bf152c1"
        result = usc.ci_status_for_sha("trevorotts1/openclaw-onboarding", merge_sha)
        self.assertEqual(result["status"], "no-data", f"PRECONDITION FAILED: {result}")

    def test_u24_onb_leg_is_red_fossil_never_upgraded_to_green_never_left_as_plain_red(self):
        """FAILS on pre-fix code: status would be "no-data" (merge commit
        has 0 runs) -- neither "red-fossil" nor any "failing_checks" key
        would exist (KeyError). PASSES on shipped code: status is the
        DISTINCT "red-fossil" value (never silently "green", never a bare
        undifferentiated "red"), the specific failing check name is named,
        and the overall unit verdict stays DONE -- a fossil must NOT gate
        NOT-DONE (that would be exactly the false-negative disease this
        fix exists to prevent, just from the opposite direction)."""
        result = usc.resolve_unit("U24", self.onb_dir, self.cc_dir, self.ledger_paths, skip_ci=False)
        ci = result["legs"]["onb"]["ci"]
        self.assertEqual(ci["status"], "red-fossil", f"REGRESSION: got {ci}")
        names = [fc["name"] for fc in ci["failing_checks"]]
        self.assertIn("G3 — skill content change requires skill-version.txt bump", names)
        fc = ci["failing_checks"][0]
        self.assertEqual(fc["head_conclusion"], "failure")
        self.assertEqual(fc["main_conclusion"], "success", f"REGRESSION: must confirm the SAME check name now passes on current main -- got {fc}")
        self.assertEqual(
            result["verdict"], "DONE",
            f"REGRESSION: a red-fossil leg must not gate the unit to NOT-DONE -- got {result['verdict']}",
        )

    def test_u5_cc_leg_is_genuine_no_data_recorded_against_the_real_head_sha(self):
        """FAILS on pre-fix code: the returned ci dict has no "head_sha" key
        at all (KeyError) -- pre-fix code never recorded which sha it
        queried, so a genuine no-data case was structurally indistinguishable
        from DEFECT 1's bug (every leg showed no-data either way). PASSES on
        shipped code: status is "no-data" AND head_sha is confirmed to be
        U5's real CC branch tip (not a merge commit, not absent)."""
        result = usc.resolve_unit("U5", self.onb_dir, self.cc_dir, self.ledger_paths, skip_ci=False)
        ci = result["legs"]["cc"]["ci"]
        self.assertEqual(ci["status"], "no-data", f"got {ci}")
        self.assertEqual(
            ci["head_sha"], "8922998209d956cc3db75155d4f39c52dd8cba90",
            "REGRESSION: no-data must still record the real head sha it queried, not be silent about it.",
        )


class Defect2PureClassifierFixtures(unittest.TestCase):
    """Offline, no-network coverage of classify_ci_from_data()'s full
    state space -- including red-live and red-check-removed / red-main-
    unverifiable, states that (per the operator brief) this repo's current
    green main cannot currently produce a REAL example of, so these use
    hand-built fixtures shaped exactly like ci_status_for_sha()'s real
    return value. This is brand-new code with no pre-fix equivalent at
    all, so every test in this class fails on pre-fix code with a hard
    AttributeError (classify_ci_from_data does not exist) -- a legitimate,
    unavoidable form of fail-first for a capability that is not a
    behavior change but a wholly new one."""

    @staticmethod
    def _ci(status, checks_by_name):
        failing = [n for n, info in checks_by_name.items() if info["conclusion"] in usc._FAILURE_CONCLUSIONS]
        return {"status": status, "total": len(checks_by_name), "checks_by_name": checks_by_name, "failing_names": failing}

    def test_red_live_when_same_check_name_still_fails_on_main(self):
        head = self._ci("red", {"Fixture check": {"conclusion": "failure", "status": "completed"}})
        main = self._ci("red", {"Fixture check": {"conclusion": "failure", "status": "completed"}})
        result = usc.classify_ci_from_data(head, "MAINSHA", main)
        self.assertEqual(result["status"], "red-live")
        self.assertEqual(result["failing_checks"][0]["main_conclusion"], "failure")

    def test_red_fossil_when_same_check_name_now_passes_on_main(self):
        head = self._ci("red", {"Fixture check": {"conclusion": "failure", "status": "completed"}})
        main = self._ci("green", {"Fixture check": {"conclusion": "success", "status": "completed"}})
        result = usc.classify_ci_from_data(head, "MAINSHA", main)
        self.assertEqual(result["status"], "red-fossil")
        self.assertEqual(result["failing_checks"][0]["main_conclusion"], "success")

    def test_red_main_unverifiable_when_same_check_name_is_skipped_on_main(self):
        """MUTATION PROOF for the fossil-classification hole this test was
        written to close: BEFORE this fix, classify_ci_from_data() reused
        _SUCCESS_CONCLUSIONS (which includes "skipped") on the MAIN-
        comparison side too -- so a check that merely did NOT RUN on
        current main's tip (a conditional `if:` gate, path filter, or
        event-type gate -- all real on this repo, e.g. G1's
        `if: github.event_name == 'push'`) was treated as an equivalent
        pass and silently classified "red-fossil", the non-gating bucket --
        even though nobody re-verified anything. FAILS on pre-fix code
        (asserts "red-fossil", proven live against the pre-fix function
        body via git stash -- see PR discussion); PASSES on the shipped
        fix ("red-main-unverifiable" -- the fail-loud, non-lenient state,
        never silently upgraded to the lenient fossil read)."""
        head = self._ci("red", {"Fixture check": {"conclusion": "failure", "status": "completed"}})
        main = self._ci("green", {"Fixture check": {"conclusion": "skipped", "status": "completed"}})
        result = usc.classify_ci_from_data(head, "MAINSHA", main)
        self.assertEqual(
            result["status"], "red-main-unverifiable",
            f"REGRESSION: a check that merely didn't RUN on current main (conclusion='skipped') "
            f"is not proof its cause is gone -- must fail loud as red-main-unverifiable, never "
            f"quietly pass as red-fossil. Got {result}",
        )
        self.assertEqual(result["failing_checks"][0]["main_conclusion"], "skipped")

    def test_red_main_unverifiable_when_same_check_name_is_neutral_on_main(self):
        """Same reasoning as the 'skipped' case immediately above --
        "neutral" is also not a genuine re-verification (nobody confirmed
        the check actually ran and passed), so it must be treated as
        unverifiable, not silently upgraded to fossil."""
        head = self._ci("red", {"Fixture check": {"conclusion": "failure", "status": "completed"}})
        main = self._ci("green", {"Fixture check": {"conclusion": "neutral", "status": "completed"}})
        result = usc.classify_ci_from_data(head, "MAINSHA", main)
        self.assertEqual(
            result["status"], "red-main-unverifiable",
            f"REGRESSION: 'neutral' on main is not a genuine pass either -- got {result}",
        )
        self.assertEqual(result["failing_checks"][0]["main_conclusion"], "neutral")

    def test_red_check_removed_when_check_name_absent_from_main_entirely(self):
        head = self._ci("red", {"Retired check": {"conclusion": "failure", "status": "completed"}})
        main = self._ci("green", {"Some other check": {"conclusion": "success", "status": "completed"}})
        result = usc.classify_ci_from_data(head, "MAINSHA", main)
        self.assertEqual(result["status"], "red-check-removed")
        self.assertIsNone(result["failing_checks"][0]["main_conclusion"])

    def test_red_main_unverifiable_when_main_itself_has_no_data(self):
        head = self._ci("red", {"Fixture check": {"conclusion": "failure", "status": "completed"}})
        main = {"status": "no-data", "total": 0, "checks_by_name": {}, "failing_names": []}
        result = usc.classify_ci_from_data(head, "MAINSHA", main)
        self.assertEqual(
            result["status"], "red-main-unverifiable",
            "REGRESSION: when main's own check-run data can't be fetched at all, the tool "
            "must fail loud (a distinct status), never default to the lenient 'fossil' read.",
        )

    def test_live_wins_priority_over_a_co_occurring_fossil_on_the_same_leg(self):
        """A leg with TWO failing checks, one still-live and one fossil,
        must never let the fossil hide the live one -- overall status must
        be red-live, not red-fossil."""
        head = self._ci("red", {
            "Live check": {"conclusion": "failure", "status": "completed"},
            "Fossil check": {"conclusion": "failure", "status": "completed"},
        })
        main = self._ci("red", {
            "Live check": {"conclusion": "failure", "status": "completed"},
            "Fossil check": {"conclusion": "success", "status": "completed"},
        })
        result = usc.classify_ci_from_data(head, "MAINSHA", main)
        self.assertEqual(result["status"], "red-live")


class Defect1LegHeadShaExtraction(unittest.TestCase):
    """Offline, no-network coverage of _leg_head_sha() -- the function that
    replaces the pre-fix "always use raw['merge_sha']" call site. Fixtures
    below are the REAL raw shapes captured live from resolve_leg() for
    U11 (own-branch), U79 (token-scan), and U108 (cross-reference) at the
    time this fix was written -- not synthesized. Every test in this class
    fails on pre-fix code with a hard AttributeError (_leg_head_sha does
    not exist pre-fix -- the call site inlined raw['merge_sha'] directly)."""

    def test_own_branch_returns_tip_not_merge_sha(self):
        leg_result = {
            "method": "own-branch",
            "raw": {
                "branch": "skill6-v2/U11", "tip": "f3d751f5f19f6d2edd8921382a6a4975e39a3ae8",
                "merge_sha": "93e4c1ed596608410abf599edf37c8f8ac9069f8", "tag": "v20.0.61",
            },
        }
        self.assertEqual(usc._leg_head_sha(leg_result), "f3d751f5f19f6d2edd8921382a6a4975e39a3ae8")

    def test_token_scan_returns_tip_not_merge_sha(self):
        leg_result = {
            "method": "token-scan",
            "raw": {
                "branch": "u79-gk17-cc-anthology-selfheal-banner", "tip": "d8cc1ad5249e2100b35467dafdd9fe3a13f5cdce",
                "merge_sha": "747fca41fdc78c5b6d72937bc7d74a2489dccf94", "tag": "v6.0.52",
            },
        }
        self.assertEqual(usc._leg_head_sha(leg_result), "d8cc1ad5249e2100b35467dafdd9fe3a13f5cdce")

    def test_cross_reference_returns_citation_full_sha_not_merge_sha(self):
        leg_result = {
            "method": "cross-reference",
            "raw": {
                "citation": {
                    "cited_sha": "25ba6c6c", "full_sha": "25ba6c6ceb956b9cb5d71442c6de39676a6e6b18",
                    "is_ancestor_of_main": True, "merge_sha": "b11c45b3ea2219e1bd07788f230dc1006f0fefa7",
                    "tag": "v6.0.55", "source": "U108's own row", "repo": "blackceo-command-center",
                },
                "all_citation_hits": [],
            },
        }
        self.assertEqual(usc._leg_head_sha(leg_result), "25ba6c6ceb956b9cb5d71442c6de39676a6e6b18")

    def test_no_confirmed_commit_methods_return_none_never_a_merge_sha_fallback(self):
        for method in ("own-branch-unmerged", "token-scan-ambiguous", "none-found"):
            leg_result = {"method": method, "raw": {"branch": "skill6-v2/U0", "merge_sha": "shouldneverbeused"}}
            self.assertIsNone(
                usc._leg_head_sha(leg_result),
                f"REGRESSION: method={method} has no single confirmed commit -- must return None, "
                f"never silently fall back to a merge_sha.",
            )


class Defect2OnlyRedLiveGatesVerdict(unittest.TestCase):
    """Proves the verdict-computation gating rule itself: of all the
    Defect-2 CI sub-statuses, ONLY "red-live" may flip an otherwise-DONE
    unit to NOT-DONE. Uses monkeypatching (usc.resolve_leg / usc.
    classify_leg_ci reassigned at module level -- Python resolves these
    names dynamically at call time, so resolve_unit()'s internal calls see
    the patched versions) to inject a fixed leg outcome without touching
    real git/network for the leg resolution itself. The pre-fix call site
    (`ci_status_for_sha(owner_repo, leg_result["raw"]["merge_sha"])`) does
    NOT call classify_leg_ci at all -- so on a pre-fix revert, the
    classify_leg_ci patch is simply never consulted, and the pre-fix code
    instead makes a REAL (network) `gh api` call against the fixture's
    fake merge_sha, which 422s and resolves to "no-data" -- never "red" --
    so the pre-fix path can NEVER produce NOT-DONE here. That is the
    FAIL-FIRST proof: these assertions are unreachable on pre-fix code."""

    ONB_PLACEHOLDER = "/nonexistent-onb"
    CC_PLACEHOLDER = "/nonexistent-cc"

    def _fixture_leg_result(self):
        return {
            "satisfied": True, "proved": True, "method": "own-branch",
            "evidence": "fixture leg for gating-logic test",
            "raw": {
                "branch": "skill6-v2/U999999-fixture",
                "tip": "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
                # A syntactically-valid-looking but NON-EXISTENT full-length
                # hex sha -- if pre-fix code's call site is exercised (it
                # uses this key directly), the real `gh api` call 422s fast
                # and returns "no-data", never "red".
                "merge_sha": "cafebabecafebabecafebabecafebabecafebabe",
                "tag": None,
            },
        }

    def _fixture_ledger(self, td, unit_id, tag):
        p = Path(td) / "fixture-ledger.md"
        p.write_text(f"| {unit_id} | [X] ({tag}, P1) fixture row for gating test | label | verified | evidence | ts |\n")
        return str(p)

    def test_red_live_gates_to_not_done(self):
        with tempfile.TemporaryDirectory() as td:
            ledger_path = self._fixture_ledger(td, "U999901", "ONB")
            orig_resolve_leg = usc.resolve_leg
            orig_classify = usc.classify_leg_ci
            usc.resolve_leg = lambda *a, **kw: self._fixture_leg_result()
            usc.classify_leg_ci = lambda owner_repo, repo_dir, head_sha, main_ref="origin/main": {
                "status": "red-live", "total": 1, "success": 0, "failure": 1, "pending": 0,
                "head_sha": head_sha, "main_sha": "beefbeefbeefbeefbeefbeefbeefbeefbeefbeef",
                "failing_checks": [{"name": "Fixture check", "head_conclusion": "failure",
                                     "main_conclusion": "failure", "note": "still fails on current main"}],
            }
            try:
                result = usc.resolve_unit("U999901", self.ONB_PLACEHOLDER, self.CC_PLACEHOLDER, [ledger_path], skip_ci=False)
            finally:
                usc.resolve_leg = orig_resolve_leg
                usc.classify_leg_ci = orig_classify
            self.assertEqual(
                result["verdict"], "NOT-DONE",
                f"REGRESSION: a red-live leg (confirmed still failing on current main) must gate "
                f"NOT-DONE -- got {result['verdict']}: {result}",
            )

    def test_red_fossil_does_not_gate_to_not_done(self):
        with tempfile.TemporaryDirectory() as td:
            ledger_path = self._fixture_ledger(td, "U999902", "ONB")
            orig_resolve_leg = usc.resolve_leg
            orig_classify = usc.classify_leg_ci
            usc.resolve_leg = lambda *a, **kw: self._fixture_leg_result()
            usc.classify_leg_ci = lambda owner_repo, repo_dir, head_sha, main_ref="origin/main": {
                "status": "red-fossil", "total": 1, "success": 0, "failure": 1, "pending": 0,
                "head_sha": head_sha, "main_sha": "beefbeefbeefbeefbeefbeefbeefbeefbeefbeef",
                "failing_checks": [{"name": "Fixture check", "head_conclusion": "failure",
                                     "main_conclusion": "success", "note": "now passes on current main -- fossil"}],
            }
            try:
                result = usc.resolve_unit("U999902", self.ONB_PLACEHOLDER, self.CC_PLACEHOLDER, [ledger_path], skip_ci=False)
            finally:
                usc.resolve_leg = orig_resolve_leg
                usc.classify_leg_ci = orig_classify
            self.assertEqual(
                result["verdict"], "DONE",
                f"REGRESSION: a red-fossil leg (confirmed the cause no longer exists on current "
                f"main) must NOT gate NOT-DONE -- got {result['verdict']}: {result}",
            )


class LiveLegOwedMachineReadable(unittest.TestCase):
    """MUTATION PROOF for the machine-readable "(live leg OWED)" state. BEFORE
    this change, the only place a compound unit's owed non-repo leg appeared
    was PROSE inside tag_note ("flagged OWED separately") -- nothing in the
    JSON result distinguished "fully DONE" from "repo-legs DONE, live leg
    OWED", so a caller (the ledger-truth gate) could not branch on it
    programmatically. Every assertion below reads keys that DO NOT EXIST on
    pre-change code (live_leg_owed / owed_non_repo_components /
    completion_state, and the resolve_owed_non_repo_components function
    itself) -- so on a revert these tests fail with AttributeError/KeyError,
    never silently pass.

    All offline: verbatim real tag strings (same discipline as
    CompoundLegTagFix), fixture ledgers in tempdirs, and a monkeypatched
    usc.resolve_leg (same pattern as Defect2OnlyRedLiveGatesVerdict) so no
    real git dir or network is touched."""

    # Real description-column texts copied VERBATIM from
    # ledgers/skill6-blended-persona-kanban-v2-2026-07-13.md (same source as
    # CompoundLegTagFix.REAL_LIVE_TAG_UNITS / REAL_UNPARSEABLE_COMPOUND_UNITS).
    REAL_COMPOUND_DESCS = {
        "U29": ("[B/B-U15] (ONB + live, P2) ENV-MATRIX live proof: the ASSUMED VPS mount row + "
                "first-hour ground truth on one Mac + one VPS + stale-env preflight", ["live"]),
        "U63": ("[GK-01] (ONB + n8n, P0) **P0 live**: fix the podcast publish path that failed on "
                "`image_url = null` + fail-closed entry guard + retry the episode", ["n8n"]),
        "U71": ("[GK-09] (ONB + GHL, P1) Clear the WAF/edge 403 on `verify-imported`; run the "
                "never-yet-run snapshot chain end-to-end once", ["ghl"]),
        "U74": ("[GK-12] (n8n + ONB, P1) Canonicalize the podcast pipeline per D19 (kill the "
                "double-publish risk)", ["n8n"]),
    }

    ONB_PLACEHOLDER = "/nonexistent-onb"
    CC_PLACEHOLDER = "/nonexistent-cc"

    def _satisfied_leg(self, *a, **kw):
        return {
            "satisfied": True, "proved": True, "method": "own-branch",
            "evidence": "fixture leg for live-leg-owed test",
            "raw": {"branch": "skill6-v2/U999-fixture", "tip": "deadbeef" * 5,
                    "merge_sha": "cafebabe" * 5, "tag": None},
        }

    def _unsatisfied_leg(self, *a, **kw):
        return {
            "satisfied": False, "proved": True, "method": "own-branch-unmerged",
            "evidence": "fixture unmerged leg for live-leg-owed test",
            "raw": {"branch": "skill6-v2/U999-fixture"},
        }

    def _resolve_with_leg(self, unit_id, tag, leg_fn):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "fixture-ledger.md"
            p.write_text(f"| {unit_id} | [X] ({tag}, P1) fixture row | label | verified | evidence | ts |\n")
            orig = usc.resolve_leg
            usc.resolve_leg = leg_fn
            try:
                return usc.resolve_unit(unit_id, self.ONB_PLACEHOLDER, self.CC_PLACEHOLDER, [str(p)], skip_ci=True)
            finally:
                usc.resolve_leg = orig

    def test_resolver_flags_real_compound_tags_owed_components(self):
        """The pure resolver, against the REAL ledger tag strings: every
        non-repo component of a repo-carrying '+'-joined tag is listed,
        regardless of '+'-join order. FAILS on revert with AttributeError
        (function does not exist)."""
        for uid, (desc, expected) in self.REAL_COMPOUND_DESCS.items():
            self.assertEqual(
                usc.resolve_owed_non_repo_components(desc), expected,
                f"{uid}: owed components wrong -- got {usc.resolve_owed_non_repo_components(desc)}",
            )

    def test_resolver_returns_empty_for_non_compound_or_non_repo_shapes(self):
        """Guard against over-flagging: bare repo tags, parenthesized
        compound (the '(+ONB)' secondary is a repo hint, NOT a live leg),
        zero-leg all-non-repo '+'-tags, and garbled fail-closed tags must
        ALL return [] -- only a repo-carrying flat compound owes a live
        leg."""
        cases = [
            "[X] (ONB, P1) bare single repo tag",
            "[X] (both, P1) both-repos tag",
            "[E2-3a (G2)] (CC (+ONB), P1) parenthesized compound -- secondary is a repo hint",
            "[X] (GHL + n8n, P1) zero-leg, no repo component at all",
            "[X] (0NB + live, P1) garbled repo token -- fail-closed unknown, nothing owed",
            "[X] (live, P1) bare non-repo tag",
        ]
        for desc in cases:
            self.assertEqual(
                usc.resolve_owed_non_repo_components(desc), [],
                f"must not flag owed components for: {desc!r}",
            )

    def test_done_compound_unit_is_visibly_live_leg_owed_not_fully_done(self):
        """THE state this change exists to expose: repo leg DONE, live leg
        owed. verdict stays DONE (repo legs ARE done), but the machine-
        readable fields must distinguish it from fully-done. FAILS on
        revert with KeyError ('live_leg_owed')."""
        result = self._resolve_with_leg("U999101", "ONB + live", self._satisfied_leg)
        self.assertEqual(result["verdict"], "DONE")
        self.assertTrue(result["live_leg_owed"],
                        f"REGRESSION: repo-done compound unit with an owed live leg must set live_leg_owed -- got {result}")
        self.assertEqual(result["owed_non_repo_components"], ["live"])
        self.assertEqual(result["completion_state"], "repo-legs-done-live-leg-owed",
                         f"REGRESSION: must NOT read 'fully-done' -- got {result['completion_state']}")

    def test_done_single_leg_unit_is_fully_done(self):
        """The contrast case: a plain (ONB, P1) unit with its leg satisfied
        is fully-done -- live_leg_owed False, no owed components."""
        result = self._resolve_with_leg("U999102", "ONB", self._satisfied_leg)
        self.assertEqual(result["verdict"], "DONE")
        self.assertFalse(result["live_leg_owed"])
        self.assertEqual(result["owed_non_repo_components"], [])
        self.assertEqual(result["completion_state"], "fully-done")

    def test_not_done_compound_lists_owed_components_but_flag_stays_false(self):
        """live_leg_owed means 'repo legs DONE but live leg OWED' -- a unit
        whose repo leg is NOT-DONE is not in that state at all. The owed
        components stay VISIBLE (a caller can still see the unit owes a
        live leg) but the flag and completion_state must not claim the
        repo-done/live-owed shape."""
        result = self._resolve_with_leg("U999103", "ONB + live", self._unsatisfied_leg)
        self.assertEqual(result["verdict"], "NOT-DONE")
        self.assertFalse(result["live_leg_owed"])
        self.assertEqual(result["owed_non_repo_components"], ["live"])
        self.assertIsNone(result["completion_state"])

    def test_garbled_tag_stays_fail_closed_and_owes_nothing(self):
        """Fail-closed behavior unchanged: an unparseable '+'-joined tag is
        UNKNOWN (never DONE off the ledger's 'verified' cell) and carries
        empty owed fields -- the new keys must not weaken the existing
        loud-failure path."""
        result = self._resolve_with_leg("U999104", "0NB + live", self._satisfied_leg)
        self.assertEqual(result["verdict"], "UNKNOWN")
        self.assertFalse(result["live_leg_owed"])
        self.assertEqual(result["owed_non_repo_components"], [])
        self.assertIsNone(result["completion_state"])


class AllModeAggregate(unittest.TestCase):
    """MUTATION PROOF for the --all aggregate count mode. BEFORE this change
    the tool accepted exactly one unit id; list_ledger_unit_ids /
    summarize_results / format_summary_line / aggregate_exit_code /
    resolve_all_units did not exist. Every test below fails on a revert with
    AttributeError -- never a hollow pass. All offline: fixture ledgers in
    tempdirs + a monkeypatched usc.resolve_leg."""

    ONB_PLACEHOLDER = "/nonexistent-onb"
    CC_PLACEHOLDER = "/nonexistent-cc"

    def _leg_satisfied(self, *a, **kw):
        return {"satisfied": True, "proved": True, "method": "own-branch",
                "evidence": "fixture satisfied leg", "raw": {"branch": "b", "tip": "d" * 40, "merge_sha": None, "tag": None}}

    def _leg_unsatisfied(self, *a, **kw):
        return {"satisfied": False, "proved": True, "method": "own-branch-unmerged",
                "evidence": "fixture unmerged leg", "raw": {"branch": "b"}}

    def test_list_ledger_unit_ids_numeric_sort_rows_only(self):
        """Unit ids come from real row starts (`| U<n> |`), numeric-sorted
        (U2 before U10) -- a prose mention of U99 mid-row must NOT become a
        checked unit."""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "fixture-ledger.md"
            p.write_text(
                "Some prose mentioning U99 and U1000 outside any row.\n"
                "| U10 | [X] (live, P1) ten | label | pending | ev | ts |\n"
                "| U2 | [X] (live, P1) two -- row text cites U99 in passing | label | pending | ev | ts |\n"
                "not a row: | U77 | should not count (does not start the line)\n"
                "| U1 | [X] (live, P1) one | label | pending | ev | ts |\n"
            )
            self.assertEqual(usc.list_ledger_unit_ids([str(p)]), ["U1", "U2", "U10"])

    def test_result_tier_buckets_fail_closed(self):
        """Tier mapping: DONE splits on live_leg_owed; NOT-DONE and UNKNOWN
        pass through; an UNEXPECTED verdict value must bucket as UNKNOWN,
        never ride along as a pass."""
        self.assertEqual(usc.result_tier({"verdict": "DONE", "live_leg_owed": False}), "DONE")
        self.assertEqual(usc.result_tier({"verdict": "DONE", "live_leg_owed": True}), "DONE-LIVE-OWED")
        self.assertEqual(usc.result_tier({"verdict": "NOT-DONE"}), "NOT-DONE")
        self.assertEqual(usc.result_tier({"verdict": "UNKNOWN"}), "UNKNOWN")
        self.assertEqual(usc.result_tier({"verdict": "SOME-FUTURE-VALUE"}), "UNKNOWN",
                         "an unrecognized verdict must bucket fail-closed as UNKNOWN")

    def test_summary_line_and_exit_code_pure(self):
        """The ONE summary line's exact format (fixed tier order, zero
        counts printed), plus the aggregate exit-code vocabulary: NOT-DONE
        dominates (1), else UNKNOWN (3), else 0."""
        results = [
            {"verdict": "DONE", "live_leg_owed": False},
            {"verdict": "DONE", "live_leg_owed": True},
            {"verdict": "NOT-DONE"},
            {"verdict": "UNKNOWN"},
        ]
        counts = usc.summarize_results(results)
        self.assertEqual(counts, {"DONE": 1, "DONE-LIVE-OWED": 1, "NOT-DONE": 1, "UNKNOWN": 1, "TOTAL": 4})
        self.assertEqual(
            usc.format_summary_line(counts),
            "UNITS CHECKED: 4 -- DONE: 1, DONE-LIVE-OWED: 1, NOT-DONE: 1, UNKNOWN: 1",
        )
        self.assertEqual(usc.aggregate_exit_code(counts), 1, "any NOT-DONE must dominate the exit code")
        self.assertEqual(
            usc.aggregate_exit_code(usc.summarize_results([{"verdict": "DONE", "live_leg_owed": False},
                                                            {"verdict": "UNKNOWN"}])),
            3, "UNKNOWN with no NOT-DONE exits 3",
        )
        self.assertEqual(
            usc.aggregate_exit_code(usc.summarize_results([{"verdict": "DONE", "live_leg_owed": False},
                                                            {"verdict": "DONE", "live_leg_owed": True}])),
            0, "all-DONE (incl. live-owed) exits 0",
        )

    def test_resolve_all_units_end_to_end_counts_and_summary(self):
        """End-to-end over a fixture ledger: one fully-DONE unit, one
        DONE-with-live-leg-owed, one NOT-DONE, one UNKNOWN (garbled tag --
        the existing fail-closed path must survive aggregation). Asserts
        the per-unit loop reused resolve_unit (full result dicts preserved),
        the exact tier counts, and the one-line summary. FAILS on revert
        with AttributeError (resolve_all_units does not exist)."""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "fixture-ledger.md"
            p.write_text(
                "| U1 | [X] (ONB, P1) plain repo unit | label | verified | ev | ts |\n"
                "| U2 | [X] (ONB + live, P1) compound live-owed unit | label | verified | ev | ts |\n"
                "| U3 | [X] (0NB + live, P1) garbled token unit | label | verified | ev | ts |\n"
                "| U4 | [X] (ONB, P1) repo unit with unmerged leg | label | pending | ev | ts |\n"
            )
            def fake_resolve_leg(repo_dir, repo_label, unit_id, ledger_paths, row_text, **_kw):
                if unit_id == "U4":
                    return self._leg_unsatisfied()
                return self._leg_satisfied()
            orig = usc.resolve_leg
            usc.resolve_leg = fake_resolve_leg
            try:
                agg = usc.resolve_all_units(["U1", "U2", "U3", "U4"], self.ONB_PLACEHOLDER,
                                             self.CC_PLACEHOLDER, [str(p)], skip_ci=True)
            finally:
                usc.resolve_leg = orig

            self.assertEqual([u["unit"] for u in agg["units"]], ["U1", "U2", "U3", "U4"],
                             "per-unit order must follow the input list")
            self.assertEqual([u["verdict"] for u in agg["units"]], ["DONE", "DONE", "UNKNOWN", "NOT-DONE"])
            self.assertTrue(agg["units"][1]["live_leg_owed"],
                            "the compound unit must surface live_leg_owed in the aggregate per-unit detail")
            self.assertEqual(agg["counts"],
                             {"DONE": 1, "DONE-LIVE-OWED": 1, "NOT-DONE": 1, "UNKNOWN": 1, "TOTAL": 4})
            self.assertEqual(
                agg["summary_line"],
                "UNITS CHECKED: 4 -- DONE: 1, DONE-LIVE-OWED: 1, NOT-DONE: 1, UNKNOWN: 1",
            )
            self.assertEqual(usc.aggregate_exit_code(agg["counts"]), 1)


class S58LedgerCountingGapFix(unittest.TestCase):
    """MUTATION PROOF for the S58 counting-gap defect (2026-07-19): every one
    of skill58-podbean-proxy-2026-07-16.md's 21 unit rows had NO leg-
    requirement tag in its desc column at all -- resolve_required_legs()
    correctly fell into mode="unknown" for every single row (fail-closed,
    exactly as designed), but that meant `unit-status.sh --all --ledger
    ledgers/skill58-podbean-proxy-2026-07-16.md` printed UNKNOWN for ALL 21
    units, always, with zero ability to adjudicate ANY of them -- a
    tooling-coverage gap, not incomplete underlying work (verbatim repro:
    "UNITS CHECKED: 21 -- DONE: 0, DONE-LIVE-OWED: 0, NOT-DONE: 0,
    UNKNOWN: 21", exit 3).

    Fixed by (a) adding real leg tags to the ledger rows (repo-leg units
    get their real repo tag, citing the exact SHA already present in that
    row's own evidence text; live-n8n-only units get the zero-leg 'live'
    tag the resolver already recognized) and (b) a second, independently
    discovered resolver bug this surfaced while verifying (a): resolve_unit()
    hardcoded the Skill-6-only `skill6-v2/` own-branch prefix for EVERY
    ledger, so S58's U12/U14/U21 (which reuse the same U<n> numbering)
    silently resolved against Skill 6's OWN, unrelated `skill6-v2/U12` /
    `skill6-v2/U14` / `skill6-v2/U21` branches instead of the real S58
    evidence -- U21 (ledger status cell literally 'pending', zero repo work)
    came back a false git-DONE this way before the
    NO_OWN_BRANCH_PREFIX_LEDGERS fix, confirmed live during this fix's own
    development and reproduced as a precondition below.

    Network + gh auth NOT required beyond the initial clone/fetch (skip_ci
    is used throughout, so no `gh api` check-run calls are made) -- reads
    real branch lists / real merge commits already in
    trevorotts1/openclaw-onboarding's history (both immutable)."""

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
        cls.s58_ledger = [str(Path(cls.onb_dir) / "ledgers" / "skill58-podbean-proxy-2026-07-16.md")]

    def test_pretag_desc_text_reproduces_the_original_all_unknown_bug(self):
        """PRECONDITION / proves the bug was real, not assumed: the EXACT
        pre-fix desc text (verbatim, no leg tag at all) for a repo-leg unit
        (U14) and a live-only unit (U1), fed straight into
        resolve_required_legs(), must still classify mode='unknown' --
        confirming the counting-gap was a real, structural tag-absence
        (every row), not a narrow parsing edge case."""
        pretag_u1 = "Prove n8n API WRITE capability (POST/GET/DELETE scratch workflow) or record manual-UI fallback"
        pretag_u14 = "`publish-proxy` transport in `podbean_publish.sh` (proxy → broker → local)"
        for desc in (pretag_u1, pretag_u14):
            legs, mode, note = usc.resolve_required_legs(desc)
            self.assertEqual(mode, "unknown", f"PRECONDITION FAILED for {desc!r}: got mode={mode!r} ({note})")
            self.assertEqual(legs, set())

    def test_s58_aggregate_matches_independently_verified_ground_truth(self):
        """FAILS on the pre-fix ledger (all 21 rows mode='unknown', counts
        {DONE:0, DONE-LIVE-OWED:0, NOT-DONE:0, UNKNOWN:21}). PASSES on the
        shipped ledger + resolver fix: matches the independently-verified
        ground truth exactly -- 16 ledger-'verified' rows split 15 plain-
        DONE + 1 DONE-LIVE-OWED (U12: repo leg proven, n8n leg still owed),
        5 ledger-'pending' rows all correctly UNKNOWN (never a false DONE,
        never a false NOT-DONE), 0 NOT-DONE (no fabricated claim in this
        ledger)."""
        unit_ids = usc.list_ledger_unit_ids(self.s58_ledger)
        self.assertEqual(unit_ids, [f"U{n}" for n in range(1, 22)])
        agg = usc.resolve_all_units(unit_ids, self.onb_dir, self.cc_dir, self.s58_ledger, skip_ci=True)
        self.assertEqual(
            agg["counts"],
            {"DONE": 15, "DONE-LIVE-OWED": 1, "NOT-DONE": 0, "UNKNOWN": 5, "TOTAL": 21},
            f"REGRESSION: S58 aggregate must match independently-verified ground truth -- got {agg['counts']}",
        )
        by_unit = {u["unit"]: u for u in agg["units"]}
        self.assertEqual(by_unit["U12"]["verdict"], "DONE")
        self.assertTrue(by_unit["U12"]["live_leg_owed"],
                         "U12 is HYBRID (repo leg + n8n leg) -- must be visibly live-leg-owed, not plain DONE.")
        self.assertEqual(by_unit["U12"]["owed_non_repo_components"], ["n8n"])
        for uid in ("U7", "U18", "U19", "U20", "U21"):
            self.assertEqual(by_unit[uid]["verdict"], "UNKNOWN",
                              f"{uid} is genuinely pending/NOT STARTED per the ledger's own status cell "
                              f"-- must never resolve DONE.")

    def test_u12_and_u14_resolve_via_real_cited_sha_not_skill6_collision_branch(self):
        """MUTATION PROOF for the second, resolver-level bug this fix
        surfaced: BEFORE NO_OWN_BRANCH_PREFIX_LEDGERS, S58's U12/U14 legs
        resolved method='own-branch' against Skill 6's OWN, unrelated
        `skill6-v2/U12` / `skill6-v2/U14` branches (both real, both merged,
        both a completely different unit) -- coincidentally still verdict
        DONE for these two, but for the WRONG reason (wrong evidence
        entirely, not the real S58 PR merge commits already cited in the
        row's own text). FAILS on pre-fix code (method=='own-branch' against
        the WRONG branch); PASSES on shipped code (method=='cross-reference'
        against the REAL cited SHA)."""
        collision_branches = usc.list_all_remote_branches(self.onb_dir)
        self.assertIn("skill6-v2/U12", collision_branches,
                       "PRECONDITION FAILED: skill6-v2/U12 no longer exists -- collision no longer reproducible.")
        self.assertIn("skill6-v2/U14", collision_branches,
                       "PRECONDITION FAILED: skill6-v2/U14 no longer exists -- collision no longer reproducible.")

        u12 = usc.resolve_unit("U12", self.onb_dir, self.cc_dir, self.s58_ledger, skip_ci=True)
        onb_leg = u12["legs"]["onb"]
        self.assertEqual(onb_leg["method"], "cross-reference",
                          f"REGRESSION: U12's ONB leg must resolve via cross-reference to the REAL cited "
                          f"PR #606 SHA, not an own-branch collision with skill6-v2/U12 -- got {onb_leg}")
        # Two real SHAs are cited in U12's own row text for PR #606 (the
        # branch tip `a5048fe0` and the merge commit `28bca8dd` it landed
        # via) -- resolve_leg_via_citations() picks whichever confirmed-
        # ancestor candidate it encounters FIRST in extraction order, which
        # is legitimately either one (both are real, both independently
        # verified ancestors of origin/main). Either is honest evidence;
        # what must NEVER happen is a skill6-v2/U12 branch/sha appearing
        # here at all.
        self.assertIn(onb_leg["raw"]["citation"]["cited_sha"], {"a5048fe0", "28bca8dd"},
                       f"got {onb_leg['raw']['citation']}")
        self.assertEqual(onb_leg["raw"]["citation"]["merge_sha"][:8], "28bca8dd")

        u14 = usc.resolve_unit("U14", self.onb_dir, self.cc_dir, self.s58_ledger, skip_ci=True)
        onb_leg14 = u14["legs"]["onb"]
        self.assertEqual(onb_leg14["method"], "cross-reference",
                          f"REGRESSION: U14's ONB leg must resolve via cross-reference to the REAL cited "
                          f"PR #609 SHA, not an own-branch collision with skill6-v2/U14 -- got {onb_leg14}")
        self.assertIn(onb_leg14["raw"]["citation"]["cited_sha"], {"7b207bcf", "5020e2f0"},
                       f"got {onb_leg14['raw']['citation']}")
        self.assertEqual(onb_leg14["raw"]["citation"]["merge_sha"][:8], "5020e2f0")

    def test_u21_pending_unit_does_not_false_positive_via_skill6_collision(self):
        """THE concrete false-DONE this bug produced live during development:
        U21 (ledger status cell literally 'pending', 'NOT STARTED. Gates
        every verified row above.') has NO own-named branch under any real
        S58 convention and NO citation SHA in its own row text -- yet,
        before NO_OWN_BRANCH_PREFIX_LEDGERS, it resolved DONE anyway by
        matching Skill 6's real, unrelated `skill6-v2/U21` branch via
        own-branch (confirmed live during this fix's own development,
        reproduced as a precondition below). FAILS on pre-fix code
        (verdict=='DONE', method=='own-branch' against skill6-v2/U21);
        PASSES on shipped code (verdict=='UNKNOWN', method=='none-found',
        never a fabricated DONE for a unit with zero real evidence)."""
        collision_branches = usc.list_all_remote_branches(self.onb_dir)
        self.assertIn("skill6-v2/U21", collision_branches,
                       "PRECONDITION FAILED: skill6-v2/U21 no longer exists -- collision no longer reproducible.")

        result = usc.resolve_unit("U21", self.onb_dir, self.cc_dir, self.s58_ledger, skip_ci=True)
        self.assertEqual(result["ledger_status_cell"], "pending")
        self.assertEqual(
            result["verdict"], "UNKNOWN",
            f"REGRESSION: U21 is genuinely pending/NOT STARTED -- must never resolve DONE via the "
            f"skill6-v2/U21 namespace collision. Got {result['verdict']}: {result}",
        )
        onb_leg = result["legs"]["onb"]
        self.assertNotEqual(onb_leg["method"], "own-branch",
                             f"REGRESSION: must not resolve via own-branch (that IS the collision) -- got {onb_leg}")
        self.assertIsNone(onb_leg["satisfied"])

    def test_own_branch_prefix_is_a_blocklist_not_an_allowlist(self):
        """Direct unit coverage of NO_OWN_BRANCH_PREFIX_LEDGERS /
        DEFAULT_OWN_BRANCH_PREFIX: deliberately a BLOCKLIST, not an
        allowlist -- ONLY Skill 58's ledger (the one file with a proven,
        empirical skill6-v2/ collision) is excluded from the default
        own-named-branch prefix. Every other ledger basename -- the real
        Skill-6 kanban ledger (unchanged behavior -- U108/U79 in
        HistoricalCases above still pass unmodified), a brand-new one nobody
        has written yet, or a TEST FIXTURE that deliberately emulates the
        skill6-v2/ convention under a different filename (see
        tests/unit/ledger-truth-gate.test.py's
        FalseClaimStillRejectedElsewhere -- this is the regression an
        allowlist-shaped fix would have silently broken and this test pins
        against reintroducing) -- keeps the default 'skill6-v2/' prefix.
        Offline, no network needed for this part."""
        self.assertIn("skill58-podbean-proxy-2026-07-16.md", usc.NO_OWN_BRANCH_PREFIX_LEDGERS)
        self.assertNotIn("skill6-blended-persona-kanban-v2-2026-07-13.md", usc.NO_OWN_BRANCH_PREFIX_LEDGERS)
        self.assertNotIn("some-future-ledger-nobody-has-written-yet.md", usc.NO_OWN_BRANCH_PREFIX_LEDGERS)
        self.assertNotIn("fixture-kanban-style.md", usc.NO_OWN_BRANCH_PREFIX_LEDGERS,
                          "REGRESSION: this is the exact fixture basename "
                          "ledger-truth-gate.test.py's FalseClaimStillRejectedElsewhere uses to "
                          "exercise the default skill6-v2/ own-branch convention -- it must never "
                          "be silently excluded.")
        self.assertEqual(usc.DEFAULT_OWN_BRANCH_PREFIX, "skill6-v2/")
        self.assertIsNone(usc.find_own_named_branch("/nonexistent-repo-dir-never-touched", "U1", prefix=None))
        self.assertIsNone(usc.find_own_named_branch("/nonexistent-repo-dir-never-touched", "U1", prefix=""))

    def test_token_scan_also_excludes_skill6_v2_namespace(self):
        """MUTATION PROOF, same shape as the pre-existing
        test_token_scan_excludes_proven_namespace_collision (skill62/ce-U15)
        but for the newly-discovered skill6-v2/ direction: a pre-fix,
        delimiter-only-plus-skill62-only-exclusion scan (i.e. the ORIGINAL
        FOREIGN_NAMESPACE_PREFIXES tuple, reproduced inline) still matches
        `skill6-v2/U21` for token 'U21' -- proving the collision was real
        and not fixed by the pre-existing skill62 exclusion alone. The
        shipped token_scan_any_branch() (FOREIGN_NAMESPACE_PREFIXES now
        includes 'skill6-v2/') must exclude it."""
        import re
        naive_pattern = re.compile(r"(?:^|[^0-9A-Za-z])U21(?:[^0-9A-Za-z]|$)", re.IGNORECASE)
        all_branches = usc.list_all_remote_branches(self.onb_dir)
        pre_fix_foreign_prefixes = ("skill62/",)  # the ORIGINAL tuple, before this fix
        naive_hits = [
            b for b in all_branches
            if naive_pattern.search(b) and not any(b.startswith(p) for p in pre_fix_foreign_prefixes)
        ]
        self.assertIn("skill6-v2/U21", naive_hits,
                       "PRECONDITION FAILED: the pre-fix exclusion list no longer reproduces the "
                       "skill6-v2/U21 collision -- either upstream history changed or this precondition "
                       "needs updating; the mutation proof below is meaningless without a live FAIL case.")

        fixed_hits = usc.token_scan_any_branch(self.onb_dir, "U21")
        self.assertNotIn("skill6-v2/U21", fixed_hits,
                          "REGRESSION: token_scan_any_branch('U21') must exclude skill6-v2/U21 "
                          "(FOREIGN_NAMESPACE_PREFIXES) -- the shipped function reproduced the collision.")


class FabricatedVerifiedClaimRejected(unittest.TestCase):
    """MUTATION PROOF -- the ABSOLUTE RULE this fix was built under: a ledger
    row that claims status='verified' and cites a SHA in its evidence prose,
    but the cited SHA does not actually exist / is not a real commit in the
    repo at all, must NEVER resolve DONE. This is the tool's whole reason to
    exist (see unit_status_core.py's own module docstring: 'Nothing in this
    file trusts a ledger row's own status cell, ever') -- proven here
    against a REAL onb_dir (network required to clone/fetch, but the
    resolution itself is a local git-verify, no `gh api` calls needed --
    skip_ci=True throughout)."""

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

    def test_fabricated_verified_row_citing_nonexistent_sha_is_rejected(self):
        """A row shaped EXACTLY like a real S58 repo-leg row -- '(ONB, P1)'
        tag, status='verified', evidence prose citing a merge commit in
        backticks -- but the cited SHA does not exist in the real repo at
        all. Must resolve UNKNOWN (fail-closed: 'no verifiable
        cross-reference citation... resolved to a merged commit'), NEVER
        DONE -- proving the tool independently re-derives from git and does
        not trust the ledger's own 'verified' stamp plus a fabricated
        citation. This is the exact shape the task's own ABSOLUTE RULE
        warns against: 'do not falsely upgrade any status.'"""
        with tempfile.TemporaryDirectory() as td:
            ledger_path = Path(td) / "fixture-fabricated-ledger.md"
            ledger_path.write_text(
                "| U999201 | (ONB, P1) fabricated claim, no real merge | [Fake x1] fabricated | "
                "verified | FABRICATED-EVIDENCE: merge commit `deadbeef01deadbeef01` merged into "
                "`origin/main`, totally fake, never happened. | 2026-01-01T00:00:00Z |\n"
            )
            result = usc.resolve_unit(
                "U999201", self.onb_dir, self.cc_dir, [str(ledger_path)], skip_ci=True
            )
            self.assertNotEqual(
                result["verdict"], "DONE",
                f"REGRESSION: a fabricated 'verified' claim citing a nonexistent SHA must NEVER "
                f"resolve DONE -- got {result}",
            )
            self.assertEqual(result["verdict"], "UNKNOWN")
            onb_leg = result["legs"]["onb"]
            self.assertIsNone(onb_leg["satisfied"])
            self.assertEqual(onb_leg["method"], "none-found")

    def test_verify_candidate_sha_rejects_nonexistent_sha(self):
        """Direct unit coverage of the primitive the test above relies on:
        verify_candidate_sha() must return None for a syntactically-hex-
        looking but nonexistent sha -- it does not even resolve to a real
        commit in the repo, so no ancestry claim is ever made about it
        (never silently treated as 'not an ancestor' either, which would
        still be an assertion -- None means 'this citation doesn't even
        resolve, discard it')."""
        fabricated = usc.verify_candidate_sha(self.onb_dir, "deadbeef01deadbeef01")
        self.assertIsNone(fabricated, f"got {fabricated}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
