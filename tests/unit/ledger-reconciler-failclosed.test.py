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


if __name__ == "__main__":
    unittest.main()
