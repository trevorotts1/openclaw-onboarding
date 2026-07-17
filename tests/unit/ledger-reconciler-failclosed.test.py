#!/usr/bin/env python3
"""
tests/unit/ledger-reconciler-failclosed.test.py
─────────────────────────────────────────────────────────────────────────────
Proves shared-utils/ledger_reconciler_core.py::detect_failclosed_mismatches()
and render_recovery_state() no longer let a "both-repo/one-leg" unit render
as silently `verified` in a repo's per-branch table when THAT repo's leg was
never actually merged into that repo's main.

THE BUG (QC-cited, U53-shaped): the shared skill6 ledger has exactly one row
per unit id. For a both-repo unit where only ONE repo's leg has landed, that
row's status cell legitimately reads "verified" (prose-documenting the leg
that IS done) -- but recovery-state.md's ONB per-branch table naively
re-printed that same global "verified" status next to the OTHER repo's
branch row, even when that specific repo's leg shows `mergedIntoMain=False`,
no `mergeSha`, no `tag`. A recovery/rebuild session reading recovery-state.md
had no way to tell, from the table alone, that "verified" belonged to the
other repo's leg -- a fail-OPEN misread. Reproduces the exact shape from the
real U53 row: ONB leg unmerged (tip `1afb5690`, no mergeSha/tag) + CC leg
merged (`481ff9a2`, tag `v6.0.36`) + one shared ledger row reading
"verified".

FAIL-FIRST: on the pre-fix module (no detect_failclosed_mismatches function,
no Integrity Alarms section in render_recovery_state's output),
TestFailClosedMismatchDetection.test_onb_leg_unmerged_but_ledger_verified_is_flagged
raises AttributeError, and TestRenderSurfacesAlarm's assertion that
"MISMATCH (fail-closed)" appears in the ONB table row FAILS (the pre-fix
render prints bare "verified" there instead).

Run:
    python3 tests/unit/ledger-reconciler-failclosed.test.py
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_SHARED_UTILS = _REPO_ROOT / "shared-utils"
assert _SHARED_UTILS.is_dir()

sys.path.insert(0, str(_SHARED_UTILS))

_spec = importlib.util.spec_from_file_location(
    "ledger_reconciler_core", _SHARED_UTILS / "ledger_reconciler_core.py"
)
assert _spec is not None
mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(mod)  # type: ignore

detect_failclosed_mismatches = mod.detect_failclosed_mismatches
render_recovery_state = mod.render_recovery_state
build_gap_fill_evidence = mod.build_gap_fill_evidence
requires_both_legs = mod.requires_both_legs
parse_leg_requirement = mod.parse_leg_requirement


# ─── Shared fixture: the exact U53 shape ─────────────────────────────────────
# A shared ledger with 4 unit rows:
#   U1  - normal, merged everywhere, verified -> never an alarm
#   U53 - the real-world case: ledger says verified (prose documents the CC
#         leg), but the ONB leg (this fixture's onb_units entry) is NOT
#         merged into ONB's main
#   U60 - same shape as U53 but with the auto-reconciled status VARIANT
#         (gap-fill only requires one side to have merge_sha+tag, so this
#         variant can produce the identical mismatch)
#   U70 - unmerged leg but ledger still says "pending" -- NOT an alarm; the
#         ledger and git truth already agree nothing is done yet
LEDGER_TEXT = (
    "| unit | description | label | status | evidence | timestamp |\n"
    "|---|---|---|---|---|---|\n"
    "| U1 | normal unit | [Sonnet] merge U1 | verified | QC PASS 9.0 | 2026-07-01T00:00:00Z |\n"
    "| U53 | [HL/U68] (both, P1) self-updater unit | [Opus] merge U53 | verified | "
    "QC PASS (QC-passed branch). NOTE: this row records the CC leg of U53 "
    "(both-repo unit); any ONB-repo leg is tracked separately. | 2026-07-15T19:15:50-04:00 |\n"
    "| U60 | auto-reconciled unit | [ledger-reconciler] auto-reconciled from git truth | "
    "verified (auto-reconciled, needs test-proof confirmation) | AUTO-RECONCILED from git "
    "truth by ledger-reconciler. | 2026-07-15T20:00:00Z |\n"
    "| U70 | not started | | pending | | |\n"
)

ONB_UNITS = {
    "skill6-v2/U1": {
        "branch": "skill6-v2/U1", "tip": "aaaaaaaa1111",
        "is_ancestor_of_main": True, "merge_sha": "bbbbbbbb2222", "tag": "v20.0.1",
    },
    "skill6-v2/U53": {
        # exact real-world tip from the U53 QC finding: ONB leg not merged
        "branch": "skill6-v2/U53", "tip": "1afb56901111",
        "is_ancestor_of_main": False, "merge_sha": None, "tag": None,
    },
    "skill6-v2/U60": {
        "branch": "skill6-v2/U60", "tip": "cccccccc3333",
        "is_ancestor_of_main": False, "merge_sha": None, "tag": None,
    },
    "skill6-v2/U70": {
        "branch": "skill6-v2/U70", "tip": "dddddddd4444",
        "is_ancestor_of_main": False, "merge_sha": None, "tag": None,
    },
}

CC_UNITS = {
    "skill6-v2/U53": {
        # exact real-world CC leg from the U53 QC finding: merged, tagged v6.0.36
        "branch": "skill6-v2/U53", "tip": "c8086c73ffff",
        "is_ancestor_of_main": True, "merge_sha": "481ff9a2eeee", "tag": "v6.0.36",
    },
}


class TestFailClosedMismatchDetection(unittest.TestCase):
    """Unit-level proof for detect_failclosed_mismatches()."""

    def test_onb_leg_unmerged_but_ledger_verified_is_flagged(self):
        alarms = detect_failclosed_mismatches("openclaw-onboarding", ONB_UNITS, LEDGER_TEXT)
        flagged_units = {a["unit"] for a in alarms}
        self.assertIn(
            "U53", flagged_units,
            "REGRESSION: the exact U53 shape (ONB leg unmerged, shared ledger row "
            "verified) must be flagged as a fail-closed mismatch.",
        )
        u53_alarm = next(a for a in alarms if a["unit"] == "U53")
        self.assertEqual(u53_alarm["repo"], "openclaw-onboarding")
        self.assertEqual(u53_alarm["branch"], "skill6-v2/U53")
        self.assertEqual(u53_alarm["ledger_status"], "verified")

    def test_auto_reconciled_status_variant_is_also_flagged(self):
        alarms = detect_failclosed_mismatches("openclaw-onboarding", ONB_UNITS, LEDGER_TEXT)
        flagged_units = {a["unit"] for a in alarms}
        self.assertIn(
            "U60", flagged_units,
            "the 'verified (auto-reconciled, needs test-proof confirmation)' status "
            "variant produces the identical both-repo/one-leg mismatch and must also "
            "be flagged, not just the bare 'verified' status.",
        )

    def test_merged_leg_produces_no_false_positive(self):
        alarms = detect_failclosed_mismatches("openclaw-onboarding", ONB_UNITS, LEDGER_TEXT)
        flagged_units = {a["unit"] for a in alarms}
        self.assertNotIn(
            "U1", flagged_units,
            "a unit whose leg IS merged into main must never be flagged, "
            "regardless of ledger status.",
        )

    def test_cc_leg_merged_for_u53_produces_no_alarm(self):
        """The CC leg of U53 (the leg the 'verified' status actually documents)
        is merged -- checking IT against the same shared ledger must NOT alarm.
        This is the mirror-image proof that the detector is leg-specific, not
        just "any unmerged branch anywhere raises an alarm for every repo"."""
        alarms = detect_failclosed_mismatches("blackceo-command-center", CC_UNITS, LEDGER_TEXT)
        self.assertEqual(
            alarms, [],
            "the CC leg of U53 is merged (mergeSha 481ff9a2, tag v6.0.36) -- "
            "no mismatch should be raised for this repo's leg.",
        )

    def test_unmerged_leg_with_pending_status_is_not_an_alarm(self):
        """U70: leg not merged AND ledger still says 'pending' -- git truth and
        the ledger already agree nothing is done. This is normal in-progress
        state, not a fail-open mismatch, and must not be flagged."""
        alarms = detect_failclosed_mismatches("openclaw-onboarding", ONB_UNITS, LEDGER_TEXT)
        flagged_units = {a["unit"] for a in alarms}
        self.assertNotIn("U70", flagged_units)


class TestRenderSurfacesAlarm(unittest.TestCase):
    """End-to-end proof against the actual rendered recovery-state.md text --
    the artifact a recovery session actually reads."""

    def _build_truth(self):
        onb_alarms = detect_failclosed_mismatches("openclaw-onboarding", ONB_UNITS, LEDGER_TEXT)
        cc_alarms = detect_failclosed_mismatches("blackceo-command-center", CC_UNITS, LEDGER_TEXT)
        return {
            "generated_at": "2026-07-16T06:00:00Z",
            "onb_main_sha": "0" * 40,
            "cc_main_sha": "1" * 40,
            "onb_units": ONB_UNITS,
            "cc_units": CC_UNITS,
            "cinematic": {"branch": "skill62/cinematic-engine", "exists": False},
            "cinematic_local_clone": {"clone_exists": False},
            "merge_queue": {"tickets_ready": [], "done": [], "lock_held": False},
            "journal_hits": [],
            "ledger_edit_allowed": True,
            "units_gap_filled": "",
            "failclosed_alarms": sorted(
                onb_alarms + cc_alarms,
                key=lambda a: (int(a["unit"][1:]), a["repo"]),
            ),
        }

    def test_integrity_alarms_section_present_with_u53(self):
        truth = self._build_truth()
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "recovery-state.md"
            render_recovery_state(truth, LEDGER_TEXT, out_path)
            rendered = out_path.read_text()

        self.assertIn("## INTEGRITY ALARMS", rendered)
        self.assertIn("mismatch(es) found this run", rendered)
        self.assertIn("U53", rendered)
        self.assertIn("openclaw-onboarding", rendered)

    def test_onb_table_row_for_u53_no_longer_shows_bare_verified(self):
        """The actual QC-cited defect: recovery-state.md's ONB per-branch
        table row for U53 must not silently print 'verified' next to
        mergedIntoMain=False. It must be visibly flagged as a mismatch."""
        truth = self._build_truth()
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "recovery-state.md"
            render_recovery_state(truth, LEDGER_TEXT, out_path)
            rendered = out_path.read_text()

        onb_u53_line = next(
            line for line in rendered.splitlines()
            if line.startswith("| U53 | `skill6-v2/U53` | `1afb5690`")
        )
        self.assertIn(
            "MISMATCH (fail-closed)", onb_u53_line,
            "REGRESSION: ONB U53 row must render a fail-closed MISMATCH marker, "
            "not a bare 'verified' status, since the ONB leg is not merged.",
        )
        self.assertNotRegex(
            onb_u53_line, r"\|\s*verified\s*\|\s*-\s*\|\s*$",
            "the row must not end with a bare unqualified 'verified' cell.",
        )

    def test_cc_table_row_for_u53_still_shows_plain_verified(self):
        """Mirror-image check: the CC leg IS merged, so its row should render
        the plain ledger status with no mismatch marker -- the fix must not
        over-flag the leg that actually earned the 'verified' status."""
        truth = self._build_truth()
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "recovery-state.md"
            render_recovery_state(truth, LEDGER_TEXT, out_path)
            rendered = out_path.read_text()

        cc_u53_line = next(
            line for line in rendered.splitlines()
            if line.startswith("| U53 | `skill6-v2/U53` | `c8086c73`")
        )
        self.assertIn("verified", cc_u53_line)
        self.assertNotIn("MISMATCH", cc_u53_line)

    def test_this_run_section_reports_alarm_count(self):
        truth = self._build_truth()
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "recovery-state.md"
            render_recovery_state(truth, LEDGER_TEXT, out_path)
            rendered = out_path.read_text()

        self.assertIn("fail-closed integrity alarms this run", rendered)
        # 2 alarms expected: U53-openclaw-onboarding, U60-openclaw-onboarding
        self.assertIn("2 (", rendered)

    def test_no_alarms_renders_clean_message(self):
        truth = self._build_truth()
        truth["failclosed_alarms"] = []
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "recovery-state.md"
            render_recovery_state(truth, LEDGER_TEXT, out_path)
            rendered = out_path.read_text()

        self.assertIn("No mismatches found this run.", rendered)


# ─── U44/U108 defect: the "either leg" gap-fill guard ────────────────────────
# THE BUG (2026-07-16, U44/U108-shaped): build_gap_fill_evidence() stamped
# `verified` the moment ANY ONE side had a confirmed merge_sha+tag, with no
# check that the unit's own row actually requires both legs. U44's row reads
# "(both, P1)" -- its ONB leg merged, but its CC leg's QC send-back (score
# 5.0) was never merged (branch existed, unmerged). U108's row also reads
# "(both, P1)" -- its ONB leg merged, but its CC leg was never even branched
# (no branch, no PR, nothing built). Both got gap-filled to "verified
# (auto-reconciled, needs test-proof confirmation)" off the ONB leg alone.
class TestBothLegsGapFillGuard(unittest.TestCase):
    """Mutation-test for build_gap_fill_evidence()'s both-legs guard."""

    ONB_MERGED = {
        "branch": "skill6-v2/UX", "tip": "1111111122223333",
        "is_ancestor_of_main": True, "merge_sha": "aaaaaaaabbbbbbbb", "tag": "v20.0.99",
    }
    CC_MERGED = {
        "branch": "skill6-v2/UX", "tip": "4444444455556666",
        "is_ancestor_of_main": True, "merge_sha": "ccccccccdddddddd", "tag": "v6.0.99",
    }
    CC_UNMERGED_BRANCH_EXISTS = {
        "branch": "skill6-v2/UX", "tip": "7777777788889999",
        "is_ancestor_of_main": False, "merge_sha": None, "tag": None,
    }

    def test_both_required_only_onb_leg_present_refuses_to_stamp_verified(self):
        """MUTATION TEST (construction): a unit whose row requires two legs
        ("both") where only ONE leg (ONB) is confirmed merged+tagged and the
        other (CC) has NO branch at all (cc_entry=None) -- the pre-fix
        function stamped `verified` off the ONB leg alone. The fixed
        function must refuse (return None): no gap-fill, no verified stamp."""
        desc = "[E5-3 (G2b)] (both, P1) Department opt-out + functionality WARNING"
        result = build_gap_fill_evidence("UX", self.ONB_MERGED, None, desc)
        self.assertIsNone(
            result,
            "REGRESSION: a both-required unit with only one confirmed leg "
            "must never be gap-filled to verified.",
        )

    def test_both_required_cc_branch_exists_but_unmerged_refuses_to_stamp_verified(self):
        """Same guard, U44 shape specifically: CC branch EXISTS but is not
        merged (QC send-back). Must still refuse."""
        desc = "[C/C-13] (both, P1) Catch-all conformance"
        result = build_gap_fill_evidence(
            "UX", self.ONB_MERGED, self.CC_UNMERGED_BRANCH_EXISTS, desc
        )
        self.assertIsNone(result)

    def test_both_required_both_legs_confirmed_still_stamps_correctly(self):
        """Second half of the mutation test: a GENUINELY complete both-repo
        unit (both legs independently confirmed merged+tagged) must still be
        gap-filled to verified -- the guard must not over-correct into never
        gap-filling both-required units at all."""
        desc = "[E5-5 (G2d)] (both, P1) Department-set board wiring"
        result = build_gap_fill_evidence("UX", self.ONB_MERGED, self.CC_MERGED, desc)
        self.assertIsNotNone(
            result,
            "a both-required unit with BOTH legs confirmed merged+tagged "
            "must still be gap-filled to verified -- over-correction would "
            "just trade one bug for another.",
        )
        label, status, evidence, ts = result
        self.assertTrue(status.startswith("verified"))
        self.assertIn("openclaw-onboarding", evidence)
        self.assertIn("blackceo-command-center", evidence)

    def test_single_repo_onb_only_unit_unaffected_by_the_guard(self):
        """Regression guard: a normal single-repo ("ONB", not "both") unit
        must still gap-fill off its one and only leg, exactly as before --
        the both-legs check must not falsely apply to units that were never
        both-repo units in the first place."""
        desc = "[A/A-U1] (ONB, P0) `persona_for_job` carries the blend"
        result = build_gap_fill_evidence("UX", self.ONB_MERGED, None, desc)
        self.assertIsNotNone(
            result,
            "a single-repo ONB-only unit must gap-fill off its one leg, "
            "unaffected by the both-legs guard.",
        )

    def test_compound_tag_is_not_treated_as_both_required(self):
        """A compound/modified tag like 'CC (+ONB probe)' is deliberately
        NOT treated as both-required (different, narrower secondary-leg
        semantics this fix does not model) -- must behave like a single-leg
        unit, not trigger the both-legs refusal."""
        desc = "[A/A-U12] (CC (+ONB probe), P2) Blend observability"
        self.assertFalse(requires_both_legs(desc))
        result = build_gap_fill_evidence("UX", None, self.CC_MERGED, desc)
        self.assertIsNotNone(result)

    def test_unparseable_description_does_not_trigger_both_required(self):
        """An unparseable/missing description must not be misread as
        both-required (that would over-block genuinely single-leg units);
        the missing-leg alarm in detect_failclosed_mismatches() is the
        fail-closed net for genuinely both-required units this can't parse."""
        self.assertIsNone(parse_leg_requirement(""))
        self.assertFalse(requires_both_legs(""))
        result = build_gap_fill_evidence("UX", self.ONB_MERGED, None, "")
        self.assertIsNotNone(result)


# ─── U108 defect: the missing-leg blind spot ─────────────────────────────────
class TestMissingLegBlindSpot(unittest.TestCase):
    """Mutation-test for detect_failclosed_mismatches()'s new missing-leg
    check -- the structural blind spot: units_truth is built from
    list_remote_branches(), so a leg with NO branch at all has no key in
    units_truth and the pre-fix loop (branch exists but unmerged) never
    visits it. This is exactly the real U108 shape: CC leg never branched,
    ledger row still says "verified"."""

    LEDGER_WITH_MISSING_CC_LEG = (
        "| unit | description | label | status | evidence | timestamp |\n"
        "|---|---|---|---|---|---|\n"
        "| U1 | normal unit | [Sonnet] merge U1 | verified | QC PASS 9.0 | 2026-07-01T00:00:00Z |\n"
        "| U108 | [E5-3 (G2b)] (both, P1) Department opt-out + functionality WARNING | "
        "[ledger-reconciler] auto-reconciled from git truth | "
        "verified (auto-reconciled, needs test-proof confirmation) | "
        "AUTO-RECONCILED from git truth by ledger-reconciler. | 2026-07-16T13:30:24Z |\n"
    )

    ONB_UNITS_WITH_U108 = {
        "skill6-v2/U1": {
            "branch": "skill6-v2/U1", "tip": "aaaa1111",
            "is_ancestor_of_main": True, "merge_sha": "bbbb2222", "tag": "v20.0.1",
        },
        "skill6-v2/U108": {
            "branch": "skill6-v2/U108", "tip": "eac10193",
            "is_ancestor_of_main": True, "merge_sha": "2bb9cbe4", "tag": "v20.0.61",
        },
    }
    # CC_UNITS has NO "skill6-v2/U108" key at all -- no branch ever existed.
    CC_UNITS_NO_U108_BRANCH = {}

    def test_missing_branch_for_a_both_required_unit_is_flagged(self):
        """MUTATION TEST (construction): U108's exact shape -- CC repo has
        NO branch for U108 at all, yet the ledger says verified. The pre-fix
        detector (loop over units_truth.items() only) would return zero
        alarms here since there is no key to iterate. The fixed detector
        must flag it."""
        alarms = detect_failclosed_mismatches(
            "blackceo-command-center", self.CC_UNITS_NO_U108_BRANCH,
            self.LEDGER_WITH_MISSING_CC_LEG,
        )
        flagged = {a["unit"] for a in alarms}
        self.assertIn(
            "U108", flagged,
            "REGRESSION: a both-required unit whose CC leg has NO branch at "
            "all must be flagged, not silently skipped.",
        )
        u108_alarm = next(a for a in alarms if a["unit"] == "U108")
        self.assertEqual(u108_alarm["repo"], "blackceo-command-center")
        self.assertEqual(u108_alarm["kind"], "missing-leg")
        self.assertIn("NO", u108_alarm["reason"])
        self.assertIn("never started", u108_alarm["reason"])

    def test_onb_side_of_same_ledger_has_no_missing_leg_alarm(self):
        """Mirror-image proof: U108's ONB leg DOES have a branch (merged),
        so calling the detector for openclaw-onboarding against the same
        ledger must not raise a missing-leg alarm for U108 -- the check is
        leg-specific, not "any both-required unit anywhere is suspect"."""
        alarms = detect_failclosed_mismatches(
            "openclaw-onboarding", self.ONB_UNITS_WITH_U108,
            self.LEDGER_WITH_MISSING_CC_LEG,
        )
        flagged = {a["unit"] for a in alarms}
        self.assertNotIn("U108", flagged)

    def test_single_repo_unit_with_no_branch_in_the_other_repo_is_not_a_false_positive(self):
        """Critical regression guard: ordinary single-repo ("ONB"-only)
        units NEVER have a CC branch by design -- that must NOT trip the new
        missing-leg check when scanning the CC repo. Without this guard,
        the fix would flood the alarm list with a false positive for every
        single-repo unit in the ledger."""
        ledger = (
            "| unit | description | label | status | evidence | timestamp |\n"
            "|---|---|---|---|---|---|\n"
            "| U1 | [A/A-U1] (ONB, P0) single-repo unit | [Sonnet] merge U1 | "
            "verified | QC PASS 9.0 | 2026-07-01T00:00:00Z |\n"
        )
        alarms = detect_failclosed_mismatches("blackceo-command-center", {}, ledger)
        self.assertEqual(
            alarms, [],
            "a single-repo ONB-only unit must never be flagged as a missing "
            "CC leg -- it was never supposed to have one.",
        )

    def test_suffixed_cc_branch_name_is_not_a_false_positive(self):
        """Real-world false-positive guard: a live scan of the actual repo
        found 3 CC-leg branches that exist and are MERGED but use a
        disambiguated suffix instead of the exact `skill6-v2/<uid>` name --
        `skill6-v2/U117-cc` (PR #208, merged), `skill6-v2/U116-cc-leg`
        (PR #201, merged), `skill6-v2/U59-cc-d15` (PR #193, merged). The
        first draft of the missing-leg check (exact-name-only) flagged all
        three as false "missing leg" alarms. Must not repeat that."""
        ledger = (
            "| unit | description | label | status | evidence | timestamp |\n"
            "|---|---|---|---|---|---|\n"
            "| U117 | [E6-3/G9] (both, P1) comms-artifact QC conformance | "
            "[Sonnet] merge U117 | verified | QC 9.2 (pass, gate 8.5). | "
            "2026-07-16T19:00:00Z |\n"
        )
        cc_units = {
            "skill6-v2/U117-cc": {
                "branch": "skill6-v2/U117-cc", "tip": "518792c0",
                "is_ancestor_of_main": True, "merge_sha": "f8ce5176", "tag": "v6.0.56",
            },
        }
        alarms = detect_failclosed_mismatches("blackceo-command-center", cc_units, ledger)
        self.assertEqual(
            alarms, [],
            "REGRESSION: a suffixed-but-real, merged CC-leg branch name "
            "(e.g. `skill6-v2/U117-cc`) must not be misread as a missing "
            "leg.",
        )

    def test_missing_leg_alarm_surfaces_in_rendered_recovery_state(self):
        """End-to-end: the missing-leg alarm must appear in the actual
        rendered recovery-state.md artifact (the INTEGRITY ALARMS section),
        not just in the in-memory alarm list -- a 'no branch' case must be
        a FINDING a recovery session can actually read, not a silent skip."""
        onb_alarms = detect_failclosed_mismatches(
            "openclaw-onboarding", self.ONB_UNITS_WITH_U108, self.LEDGER_WITH_MISSING_CC_LEG
        )
        cc_alarms = detect_failclosed_mismatches(
            "blackceo-command-center", self.CC_UNITS_NO_U108_BRANCH, self.LEDGER_WITH_MISSING_CC_LEG
        )
        truth = {
            "generated_at": "2026-07-16T18:00:00Z",
            "onb_main_sha": "0" * 40,
            "cc_main_sha": "1" * 40,
            "onb_units": self.ONB_UNITS_WITH_U108,
            "cc_units": self.CC_UNITS_NO_U108_BRANCH,
            "cinematic": {"branch": "skill62/cinematic-engine", "exists": False},
            "cinematic_local_clone": {"clone_exists": False},
            "merge_queue": {"tickets_ready": [], "done": [], "lock_held": False},
            "journal_hits": [],
            "ledger_edit_allowed": True,
            "units_gap_filled": "",
            "failclosed_alarms": sorted(
                onb_alarms + cc_alarms,
                key=lambda a: (int(a["unit"][1:]), a["repo"]),
            ),
        }
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "recovery-state.md"
            render_recovery_state(truth, self.LEDGER_WITH_MISSING_CC_LEG, out_path)
            rendered = out_path.read_text()
        self.assertIn("## INTEGRITY ALARMS", rendered)
        self.assertIn("U108", rendered)
        self.assertIn("blackceo-command-center", rendered)
        self.assertNotIn("No mismatches found this run.", rendered)


# ─── Counterfactual: would the fix have caught the REAL U44 and U108? ────────
# Reconstructs the exact real-world git-truth shapes (real SHAs, real tags,
# real ledger row text, as independently verified against
# trevorotts1/openclaw-onboarding and trevorotts1/blackceo-command-center on
# 2026-07-16) and proves the FIXED reconciler refuses to stamp either one.
class TestU44U108RealWorldCounterfactual(unittest.TestCase):
    # Real U44 shape, verified via `git merge-base --is-ancestor` + `git
    # cherry origin/main origin/skill6-v2/U44` against a fresh clone of
    # trevorotts1/blackceo-command-center: 3 commits, all "+" (none
    # equivalent on main) -- the branch exists (PR #204, still OPEN) but
    # was never merged; QC sent it back at score 5.0.
    U44_DESCRIPTION = (
        '[C/C-13] (both, P1) Catch-all conformance: `general-task` seeded '
        'fleet-wide, display "General Stuff" (D8), INGEST-06 proof, stale '
        "producer-doc fix"
    )
    U44_ONB_ENTRY = {
        "branch": "skill6-v2/U44", "tip": "c6aca95f",
        "is_ancestor_of_main": True, "merge_sha": "0ecbcebe", "tag": "v20.0.60",
    }
    U44_CC_ENTRY_BRANCH_EXISTS_UNMERGED = {
        "branch": "skill6-v2/U44", "tip": "eb30a3b1fc34b6142f8f766cc65993bed4586063",
        "is_ancestor_of_main": False, "merge_sha": None, "tag": None,
    }

    # Real U108 shape: ONB leg merged (commit 2bb9cbe4, tag v20.0.61,
    # confirmed ancestor of origin/main). CC leg: `git branch -r` against a
    # fresh clone of blackceo-command-center returns ZERO branches matching
    # "U108" -- no branch, no PR, nothing built.
    U108_DESCRIPTION = (
        "[E5-3 (G2b)] (both, P1) **Department opt-out + functionality "
        "WARNING**: a client can opt a department OUT, shown a clear "
        "warning of the functionality lost, recorded and honored by "
        "provisioning"
    )
    U108_ONB_ENTRY = {
        "branch": "skill6-v2/U108", "tip": "eac10193",
        "is_ancestor_of_main": True, "merge_sha": "2bb9cbe4", "tag": "v20.0.61",
    }

    def test_u44_would_not_have_been_gap_filled_to_verified(self):
        """If U44's row had still been 'pending' at gap-fill time with this
        exact git truth (ONB merged, CC branch exists but unmerged, QC 5.0
        send-back), the FIXED build_gap_fill_evidence() refuses -- proving
        the fix would have caught it before the false 'verified' stamp was
        ever written."""
        result = build_gap_fill_evidence(
            "U44", self.U44_ONB_ENTRY, self.U44_CC_ENTRY_BRANCH_EXISTS_UNMERGED,
            self.U44_DESCRIPTION,
        )
        self.assertIsNone(
            result,
            "COUNTERFACTUAL FAILED: the fix would NOT have caught U44 -- "
            "it must refuse to gap-fill a both-required unit whose CC leg "
            "exists but is unmerged.",
        )

    def test_u44_cc_leg_unmerged_branch_is_flagged_as_an_unmerged_mismatch(self):
        """Independent of gap-fill: if U44's row is (hypothetically, as it
        stands tonight) still marked verified in the shared ledger, the
        EXISTING (pre-this-fix) unmerged-branch alarm already catches this
        shape (branch exists, not ancestor of main) -- confirming this half
        of the U44 defect was already covered by U53-class detection, and
        the row going uncorrected was a process gap (nobody acted on the
        alarm), not a detection gap. Proven here for completeness."""
        ledger_text = (
            "| unit | description | label | status | evidence | timestamp |\n"
            "|---|---|---|---|---|---|\n"
            f"| U44 | {self.U44_DESCRIPTION} | [ledger-reconciler] auto-reconciled | "
            "verified (auto-reconciled, needs test-proof confirmation) | "
            "AUTO-RECONCILED from git truth. | 2026-07-16T12:10:22Z |\n"
        )
        units_truth = {"skill6-v2/U44": self.U44_CC_ENTRY_BRANCH_EXISTS_UNMERGED}
        alarms = detect_failclosed_mismatches(
            "blackceo-command-center", units_truth, ledger_text
        )
        flagged = {a["unit"] for a in alarms}
        self.assertIn("U44", flagged)

    def test_u108_would_not_have_been_gap_filled_to_verified(self):
        """If U108's row had still been 'pending' at gap-fill time with this
        exact git truth (ONB merged, CC has no branch at all), the FIXED
        build_gap_fill_evidence() refuses -- cc_entry is None (no branch
        found), both_required is True, so onb-only evidence is rejected."""
        result = build_gap_fill_evidence(
            "U108", self.U108_ONB_ENTRY, None, self.U108_DESCRIPTION
        )
        self.assertIsNone(
            result,
            "COUNTERFACTUAL FAILED: the fix would NOT have caught U108 -- "
            "it must refuse to gap-fill a both-required unit whose CC leg "
            "has no branch at all.",
        )

    def test_u108_missing_cc_branch_is_flagged_by_the_new_missing_leg_check(self):
        """The real defect: U108's CC leg has NO branch, so it is ABSENT
        from cc_units entirely (not merely unmerged) -- the pre-fix
        detect_failclosed_mismatches() (loop over units_truth.items() only)
        has NO key to iterate and returns zero alarms for U108, no matter
        what the ledger says. This is the exact counterfactual the task
        asks for: does the FIXED detector refuse to stay silent?"""
        ledger_text = (
            "| unit | description | label | status | evidence | timestamp |\n"
            "|---|---|---|---|---|---|\n"
            f"| U108 | {self.U108_DESCRIPTION} | [ledger-reconciler] auto-reconciled | "
            "verified (auto-reconciled, needs test-proof confirmation) | "
            "AUTO-RECONCILED from git truth. | 2026-07-16T13:30:24Z |\n"
        )
        cc_units_truth = {}  # exactly what a real `git branch -r` scan returns: no U108 key
        alarms = detect_failclosed_mismatches(
            "blackceo-command-center", cc_units_truth, ledger_text
        )
        flagged = {a["unit"] for a in alarms}
        self.assertIn(
            "U108", flagged,
            "COUNTERFACTUAL FAILED: the fix would NOT have caught U108's "
            "missing CC leg -- the structural blind spot remains open.",
        )
        u108_alarm = next(a for a in alarms if a["unit"] == "U108")
        self.assertEqual(u108_alarm["kind"], "missing-leg")


# ─── U79 defect: the compound-tag / non-namespaced-branch blind spot ────────
# THE BUG (QC send-back on PR #614, 2026-07-16): U79's real row reads
# "(CC (+ONB), P1)" -- a compound/modified tag, not the literal "both".
# TWO independent structural reasons the pre-this-commit guards never
# examine it: (1) requires_both_legs()/parse_leg_requirement() cannot parse
# this shape at all (the inner "(+ONB)" parens break LEG_TAG_RE's "no
# comma/paren before the first comma" assumption -- confirmed empirically,
# not assumed, in TestCompoundLegTagParsing below), so the missing-leg loop
# never visits rows with this tag shape regardless of branch naming; (2)
# even if it did, U79's real CC-leg branch is
# `u79-gk17-cc-anthology-selfheal-banner` -- entirely outside the
# `skill6-v2/` namespace `list_remote_branches()` collects from, so it
# would never appear in units_truth in the first place. U79 was only ever
# confirmed correct by a one-time hand audit against fresh git truth, not
# by any code path that ran automatically. Real, LIVE examples from this
# repo's own ledger use this exact tag shape: U12 ("CC (+ONB probe)"), U15
# ("ONB (+CC endpoint)"), U79 ("CC (+ONB)") -- descriptions below are the
# verbatim text from ledgers/skill6-blended-persona-kanban-v2-2026-07-13.md
# as of this commit.
class TestCompoundLegTagParsing(unittest.TestCase):
    """Unit-level proof for parse_compound_leg_primary()."""

    U12_DESCRIPTION = (
        "[A/A-U12] (CC (+ONB probe), P2) Blend observability: match-score "
        "distribution advisory in deep-health + `persona_grounding_degraded` "
        "event/chip"
    )
    U15_DESCRIPTION = (
        "[B/B-U1] (ONB (+CC endpoint), P0) Bundle-acquisition ladder in "
        "`v2_dispatcher` (threaded → CC fetch → local `--blend` → "
        "absent; receipt always)"
    )
    U79_DESCRIPTION = (
        "[GK-17] (CC (+ONB), P1) The REAL A7 repair: root-cause the silent "
        "mirror drop, then a converging self-healing reconcile (banner = "
        "last resort)"
    )

    def test_legtagre_cannot_parse_any_of_the_three_real_compound_rows(self):
        """Confirms the PREMISE of this whole fix, empirically: the
        pre-existing LEG_TAG_RE/parse_leg_requirement() genuinely cannot
        parse ANY of the 3 real compound-tag rows in the live ledger, not
        just U79. If this ever stops being true (e.g. LEG_TAG_RE is
        independently improved to parse compound tags), this test -- not
        just U79's -- must be revisited."""
        for desc in (self.U12_DESCRIPTION, self.U15_DESCRIPTION, self.U79_DESCRIPTION):
            self.assertIsNone(parse_leg_requirement(desc))
            self.assertFalse(requires_both_legs(desc))

    def test_u79_real_shape_parses_to_cc_primary(self):
        self.assertEqual(mod.parse_compound_leg_primary(self.U79_DESCRIPTION), "CC")

    def test_u15_real_shape_parses_to_onb_primary(self):
        self.assertEqual(mod.parse_compound_leg_primary(self.U15_DESCRIPTION), "ONB")

    def test_u12_real_shape_parses_to_cc_primary(self):
        self.assertEqual(mod.parse_compound_leg_primary(self.U12_DESCRIPTION), "CC")

    def test_literal_both_tag_is_not_a_compound_tag(self):
        desc = "[C/C-13] (both, P1) Catch-all conformance"
        self.assertIsNone(mod.parse_compound_leg_primary(desc))

    def test_plain_single_repo_tag_is_not_a_compound_tag(self):
        desc = "[JM/U65] (CC, P2) My AI CEO Phase B"
        self.assertIsNone(mod.parse_compound_leg_primary(desc))

    def test_empty_description_is_not_a_compound_tag(self):
        self.assertIsNone(mod.parse_compound_leg_primary(""))
        self.assertIsNone(mod.parse_compound_leg_primary(None))


class TestCompoundTagUnconfirmedFinding(unittest.TestCase):
    """Mutation-test for detect_failclosed_mismatches()'s THIRD,
    informational-only loop -- proves it catches the U79 shape (compound
    tag + branch entirely outside units_truth) without reopening the false
    positives the branch-name tolerance was already tuned against."""

    U79_DESCRIPTION = TestCompoundLegTagParsing.U79_DESCRIPTION
    U15_DESCRIPTION = TestCompoundLegTagParsing.U15_DESCRIPTION
    U12_DESCRIPTION = TestCompoundLegTagParsing.U12_DESCRIPTION

    def _ledger(self, uid, description, status):
        return (
            "| unit | description | label | status | evidence | timestamp |\n"
            "|---|---|---|---|---|---|\n"
            f"| {uid} | {description} | [x] | {status} | evidence | 2026-07-16T00:00:00Z |\n"
        )

    def test_u79_shape_no_cc_branch_at_all_raises_informational_finding(self):
        """THE FIX: U79's real shape -- compound tag, primary=CC, and CC's
        units_truth has NO `skill6-v2/U79` key at all (exactly the live,
        real-world fact: U79's actual CC branch,
        `u79-gk17-cc-anthology-selfheal-banner`, is outside the
        `skill6-v2/` namespace this module ever collects from). Pre-fix:
        zero alarms for U79, ever, from any repo, regardless of branch
        state -- this loop is what closes that."""
        ledger = self._ledger(
            "U79", self.U79_DESCRIPTION,
            "verified (auto-reconciled, needs test-proof confirmation)",
        )
        alarms = detect_failclosed_mismatches("blackceo-command-center", {}, ledger)
        flagged = {a["unit"] for a in alarms}
        self.assertIn(
            "U79", flagged,
            "REGRESSION: the U79 compound-tag shape (no branch anywhere in "
            "units_truth, primary leg=CC) must produce a finding, not silence.",
        )
        u79_finding = next(a for a in alarms if a["unit"] == "U79")
        self.assertEqual(u79_finding["kind"], "compound-tag-unconfirmed")
        self.assertEqual(u79_finding["repo"], "blackceo-command-center")
        self.assertIn("NOT", u79_finding["reason"])
        self.assertIn("does NOT mean the leg is missing", u79_finding["reason"])

    def test_u79_shape_wrong_repo_call_raises_no_finding(self):
        """Mirror-image: U79's primary leg is CC, not ONB -- calling the
        detector for openclaw-onboarding against the identical ledger row
        must NOT raise a finding (the row's primary leg is the other
        repo's problem, not ONB's)."""
        ledger = self._ledger(
            "U79", self.U79_DESCRIPTION,
            "verified (auto-reconciled, needs test-proof confirmation)",
        )
        alarms = detect_failclosed_mismatches("openclaw-onboarding", {}, ledger)
        flagged = {a["unit"] for a in alarms}
        self.assertNotIn("U79", flagged)

    def test_u15_shape_no_onb_branch_raises_informational_finding(self):
        """Real second instance of the same shape, opposite primary repo:
        U15's real ONB leg shipped inside a multi-unit branch
        (`skill6-v2/chainA`), not its own `skill6-v2/U15` -- units_truth
        genuinely has no key for it. Primary=ONB, so the ONB-side call
        must raise the finding."""
        ledger = self._ledger("U15", self.U15_DESCRIPTION, "verified")
        alarms = detect_failclosed_mismatches("openclaw-onboarding", {}, ledger)
        flagged = {a["unit"] for a in alarms}
        self.assertIn("U15", flagged)
        u15_finding = next(a for a in alarms if a["unit"] == "U15")
        self.assertEqual(u15_finding["kind"], "compound-tag-unconfirmed")

    def test_u12_shape_branch_exists_produces_no_false_positive(self):
        """Critical false-positive guard: U12's real CC leg DOES have a
        branch under the exact canonical name (`skill6-v2/U12`, confirmed
        live against blackceo-command-center) -- the safe check must find
        it and NOT raise a finding, even though the row's tag is the same
        compound shape as U79's. Proves this loop does not just fire on
        every compound-tag row unconditionally."""
        ledger = self._ledger(
            "U12", self.U12_DESCRIPTION,
            "verified (auto-reconciled, needs test-proof confirmation)",
        )
        cc_units = {
            "skill6-v2/U12": {
                "branch": "skill6-v2/U12", "tip": "aaaaaaaa",
                "is_ancestor_of_main": True, "merge_sha": "bbbbbbbb", "tag": "v6.0.1",
            },
        }
        alarms = detect_failclosed_mismatches("blackceo-command-center", cc_units, ledger)
        self.assertEqual(
            alarms, [],
            "REGRESSION: a compound-tag row whose primary-leg branch genuinely "
            "exists under the exact canonical name must not be flagged.",
        )

    def test_compound_tag_pending_status_is_not_a_finding(self):
        """Consistency guard, same shape as every other check in this
        module: a compound-tag row that is honestly still 'pending' (git
        truth and ledger already agree) must not be flagged."""
        ledger = self._ledger("U79", self.U79_DESCRIPTION, "pending")
        alarms = detect_failclosed_mismatches("blackceo-command-center", {}, ledger)
        self.assertEqual(alarms, [])

    def test_literal_both_tagged_row_is_unaffected_by_this_loop(self):
        """Non-interaction guard: this new loop must never fire for a
        literal "(both, ...)" row (that shape is already fully covered by
        the missing-leg loop with a HARD, not informational, severity) --
        parse_compound_leg_primary() must return None for it, so this loop
        skips it entirely, exactly like TestMissingLegBlindSpot already
        proves for that row's own (hard) coverage."""
        ledger = self._ledger(
            "U108",
            "[E5-3 (G2b)] (both, P1) Department opt-out + functionality WARNING",
            "verified (auto-reconciled, needs test-proof confirmation)",
        )
        alarms = detect_failclosed_mismatches("blackceo-command-center", {}, ledger)
        kinds = {a["kind"] for a in alarms}
        self.assertNotIn(
            "compound-tag-unconfirmed", kinds,
            "a literal both-tagged row must be caught (if at all) by the "
            "hard missing-leg loop, never by the informational compound-tag loop.",
        )
        # (it SHOULD still be caught by the existing hard missing-leg loop --
        # confirmed already by TestMissingLegBlindSpot; re-asserted here for
        # this test's own clarity)
        self.assertIn("missing-leg", kinds)

    def test_finding_severity_is_distinct_from_hard_alarm_kinds(self):
        """The finding's own "kind" field must never collide with either
        hard-alarm kind string ("unmerged"/"missing-leg") -- callers (e.g.
        render_recovery_state()) rely on this string to route severity."""
        ledger = self._ledger(
            "U79", self.U79_DESCRIPTION,
            "verified (auto-reconciled, needs test-proof confirmation)",
        )
        alarms = detect_failclosed_mismatches("blackceo-command-center", {}, ledger)
        u79_finding = next(a for a in alarms if a["unit"] == "U79")
        self.assertNotIn(u79_finding["kind"], ("unmerged", "missing-leg"))


class TestMissingLegAlarmTextStrengthened(unittest.TestCase):
    """Proof for the third QC ask: the missing-leg alarm's rendered text
    must explicitly remind a reader to check OTHER cross-referenced units'
    CHANGELOGs/branches before resolving it -- the U108 blind spot already
    produced one WRONG resolution this same session on the first pass
    (marked 'verified (ONB half)' on branch-name absence alone, before a
    deeper cross-reference check reversed it)."""

    def test_missing_leg_reason_names_the_cross_reference_reminder(self):
        ledger = (
            "| unit | description | label | status | evidence | timestamp |\n"
            "|---|---|---|---|---|---|\n"
            "| U108 | [E5-3 (G2b)] (both, P1) Department opt-out | [x] | "
            "verified (auto-reconciled, needs test-proof confirmation) | e | t |\n"
        )
        alarms = detect_failclosed_mismatches("blackceo-command-center", {}, ledger)
        u108_alarm = next(a for a in alarms if a["unit"] == "U108")
        self.assertEqual(u108_alarm["kind"], "missing-leg")
        self.assertIn("cross-referenced", u108_alarm["reason"])
        self.assertIn("CHANGELOG", u108_alarm["reason"])

    def test_compound_tag_finding_also_names_the_cross_reference_reminder(self):
        ledger = (
            "| unit | description | label | status | evidence | timestamp |\n"
            "|---|---|---|---|---|---|\n"
            "| U79 | [GK-17] (CC (+ONB), P1) The REAL A7 repair | [x] | "
            "verified (auto-reconciled, needs test-proof confirmation) | e | t |\n"
        )
        alarms = detect_failclosed_mismatches("blackceo-command-center", {}, ledger)
        u79_finding = next(a for a in alarms if a["unit"] == "U79")
        self.assertIn("CHANGELOG", u79_finding["reason"])


class TestRenderSeveritySeparation(unittest.TestCase):
    """End-to-end proof that render_recovery_state() renders hard
    fail-closed alarms and informational compound-tag findings in SEPARATE
    sections, never conflating the two severities in the artifact a
    recovery session actually reads."""

    def _build_truth_with_mixed_severities(self):
        ledger = (
            "| unit | description | label | status | evidence | timestamp |\n"
            "|---|---|---|---|---|---|\n"
            "| U108 | [E5-3 (G2b)] (both, P1) Department opt-out | [x] | "
            "verified (auto-reconciled, needs test-proof confirmation) | e | t |\n"
            "| U79 | [GK-17] (CC (+ONB), P1) The REAL A7 repair | [x] | "
            "verified (auto-reconciled, needs test-proof confirmation) | e | t |\n"
        )
        cc_alarms = detect_failclosed_mismatches("blackceo-command-center", {}, ledger)
        truth = {
            "generated_at": "2026-07-17T00:00:00Z",
            "onb_main_sha": "0" * 40,
            "cc_main_sha": "1" * 40,
            "onb_units": {},
            "cc_units": {},
            "cinematic": {"branch": "skill62/cinematic-engine", "exists": False},
            "cinematic_local_clone": {"clone_exists": False},
            "merge_queue": {"tickets_ready": [], "done": [], "lock_held": False},
            "journal_hits": [],
            "ledger_edit_allowed": True,
            "units_gap_filled": "",
            "failclosed_alarms": cc_alarms,
        }
        return truth, ledger

    def test_hard_and_informational_sections_both_present_and_distinct(self):
        truth, ledger = self._build_truth_with_mixed_severities()
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "recovery-state.md"
            render_recovery_state(truth, ledger, out_path)
            rendered = out_path.read_text()

        self.assertIn("## INTEGRITY ALARMS", rendered)
        self.assertIn("## INTEGRITY FINDINGS", rendered)
        alarms_idx = rendered.index("## INTEGRITY ALARMS")
        findings_idx = rendered.index("## INTEGRITY FINDINGS")
        this_run_idx = rendered.index("## This run")
        self.assertLess(alarms_idx, findings_idx)
        self.assertLess(findings_idx, this_run_idx)

        alarms_section = rendered[alarms_idx:findings_idx]
        findings_section = rendered[findings_idx:this_run_idx]
        # U108 (hard, missing-leg) belongs in the ALARMS section only.
        self.assertIn("U108", alarms_section)
        self.assertNotIn("U79", alarms_section)
        # U79 (informational, compound-tag-unconfirmed) belongs in the
        # FINDINGS section only.
        self.assertIn("U79", findings_section)
        self.assertNotIn("| U79 |", alarms_section)

    def test_this_run_reports_both_counts_separately(self):
        truth, ledger = self._build_truth_with_mixed_severities()
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "recovery-state.md"
            render_recovery_state(truth, ledger, out_path)
            rendered = out_path.read_text()

        this_run = rendered[rendered.index("## This run"):]
        self.assertIn("fail-closed integrity alarms this run", this_run)
        self.assertIn("informational leg-unconfirmed findings this run", this_run)
        # exactly 1 hard (U108) + 1 informational (U79)
        self.assertIn("1 (U108-blackceo-command-center)", this_run)
        self.assertIn("1 (U79-blackceo-command-center)", this_run)


if __name__ == "__main__":
    unittest.main()
