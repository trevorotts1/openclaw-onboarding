#!/usr/bin/env python3
"""
tests/unit/u97-x7-routed-handoff-row.test.py
─────────────────────────────────────────────────────────────────────────────
U97 (X/U-X7) — ROUTED (narrowed per updated D22): interview-GATE mechanism +
its false-block regression guard stay in the Skill 23/32 lane; the
department-provisioning WORK is now IN-spec as U107-U110 (see E5).

U97 is a pure-document unit: its ONLY deliverable is the assembled v2 E.2
hand-off row for U97 in the master ledger
(ledgers/skill6-blended-persona-kanban-v2-2026-07-13.md). Per the unit's own
BINARY acceptance, that row must, in ONE row, name all four of:

  1. the receiving lane            ("Skill 23/32")
  2. the ratified decision id      ("OQ-1")
  3. the false-block regression-guard requirement
  4. the cross-reference to the IN-spec provisioning units U107-U110

THE BUG this test catches: the ledger's pre-fix U97 row named the lane, the
regression-guard requirement, and the U107-U110 cross-reference, but never
named the ratified decision id (OQ-1) that makes the interview-GATE mechanism
a settled, non-re-litigable hand-off rather than an open question. A future
edit could just as easily drop OQ-1 (or the lane, or the cross-reference)
again -- this is the regression guard for that document.

FAIL-FIRST: test_check_function_catches_the_real_pre_fix_defect asserts the
frozen pre-fix row text (copied verbatim from the ledger before this unit's
fix) is REJECTED by _row_meets_binary_acceptance with 'OQ-1' named as the
specific missing requirement -- proving the check has real teeth, not a
tautology. test_current_row_meets_binary_acceptance then proves the live,
on-disk row (post-fix) passes every element of the same check.

Run:
    python3 tests/unit/u97-x7-routed-handoff-row.test.py
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_LEDGER_PATH = (
    _REPO_ROOT / "ledgers" / "skill6-blended-persona-kanban-v2-2026-07-13.md"
)
assert _LEDGER_PATH.is_file(), f"ledger not found at {_LEDGER_PATH}"

_U97_ROW_RE = re.compile(r"^\| *U97 *\|.*$", re.MULTILINE)

# U107-U110 written as an en-dash range, exactly as the master spec's own E.2
# checklist row and X.4/D22 prose write it (never spelled out unit-by-unit).
_U107_U110_RANGE_RE = re.compile(r"U107\s*[–—-]\s*U110")


def _find_u97_rows(ledger_text: str) -> list[str]:
    """Every ledger table row whose id column is exactly 'U97'."""
    return _U97_ROW_RE.findall(ledger_text)


def _row_meets_binary_acceptance(row: str) -> list[str]:
    """Returns the list of U97's BINARY-acceptance elements MISSING from
    `row` (empty list == the row meets acceptance in full)."""
    missing = []
    if "Skill 23/32" not in row:
        missing.append("receiving-lane name (Skill 23/32)")
    if "OQ-1" not in row:
        missing.append("ratified decision id (OQ-1)")
    if "false-block" not in row or "regression guard" not in row:
        missing.append("false-block regression-guard requirement")
    if not _U107_U110_RANGE_RE.search(row):
        missing.append("cross-reference to IN-spec provisioning units U107-U110")
    return missing


# Frozen verbatim copy of the ledger's U97 row BEFORE this unit's fix (the
# exact text this test suite was written against pre-fix) -- never edit this
# constant when the ledger changes; it exists to prove the check function
# actually distinguishes pass from fail.
_PRE_FIX_BASELINE_ROW = (
    "| U97 | [X/U-X7] (doc, P1) ROUTED (narrowed per updated D22): the "
    "interview→CC-provisioning GATE mechanism + its false-block "
    "regression guard stay in the Skill 23/32 lane; the "
    "department-provisioning WORK is now IN-spec as U107–U110 |  | "
    "pending |  |  |"
)


class TestU97HandoffRowExistsExactlyOnce(unittest.TestCase):
    def test_exactly_one_u97_row_in_the_ledger(self) -> None:
        text = _LEDGER_PATH.read_text(encoding="utf-8")
        rows = _find_u97_rows(text)
        self.assertEqual(
            len(rows),
            1,
            f"expected exactly one U97 ledger row, found {len(rows)}: {rows}",
        )


class TestCheckFunctionHasTeeth(unittest.TestCase):
    """Fail-first proof: the check function must actually reject the real
    pre-fix defect, not just accept whatever it's handed."""

    def test_check_function_catches_the_real_pre_fix_defect(self) -> None:
        missing = _row_meets_binary_acceptance(_PRE_FIX_BASELINE_ROW)
        self.assertIn(
            "ratified decision id (OQ-1)",
            missing,
            "pre-fix baseline row unexpectedly passed the OQ-1 check -- "
            "the check function has no teeth",
        )
        # The pre-fix row DID already carry the other three elements; the
        # check must not false-positive on those.
        self.assertNotIn("receiving-lane name (Skill 23/32)", missing)
        self.assertNotIn("false-block regression-guard requirement", missing)
        self.assertNotIn(
            "cross-reference to IN-spec provisioning units U107-U110", missing
        )

    def test_check_function_accepts_a_fully_compliant_row(self) -> None:
        compliant = (
            "| U97 | [X/U-X7] (doc, P1) ROUTED (narrowed per updated D22): "
            "interview-GATE mechanism (`PREREQS.json` `interviewComplete`, "
            "ratified **OQ-1** 2026-07-03; lock-before-reachable) + its "
            "false-block regression guard stay in the Skill 23/32 lane; the "
            "department-provisioning WORK is now IN-spec as U107–U110 "
            "(see E5) |  | pending |  |  |"
        )
        self.assertEqual(_row_meets_binary_acceptance(compliant), [])


class TestCurrentLedgerRowMeetsBinaryAcceptance(unittest.TestCase):
    def test_current_row_meets_binary_acceptance(self) -> None:
        text = _LEDGER_PATH.read_text(encoding="utf-8")
        rows = _find_u97_rows(text)
        self.assertEqual(len(rows), 1, "expected exactly one U97 row")
        missing = _row_meets_binary_acceptance(rows[0])
        self.assertEqual(
            missing,
            [],
            f"U97 ledger row fails BINARY acceptance, missing: {missing}\n"
            f"row: {rows[0]!r}",
        )

    def test_current_row_still_carries_crosswalk_and_repo_phase_tag(self) -> None:
        text = _LEDGER_PATH.read_text(encoding="utf-8")
        row = _find_u97_rows(text)[0]
        self.assertIn("[X/U-X7]", row)
        self.assertIn("(doc, P1)", row)

    def test_current_row_is_not_the_stale_pre_fix_text(self) -> None:
        text = _LEDGER_PATH.read_text(encoding="utf-8")
        row = _find_u97_rows(text)[0]
        self.assertNotEqual(row, _PRE_FIX_BASELINE_ROW)


if __name__ == "__main__":
    unittest.main()
