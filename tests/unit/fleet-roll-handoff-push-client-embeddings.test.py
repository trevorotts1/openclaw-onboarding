#!/usr/bin/env python3
"""
tests/unit/fleet-roll-handoff-push-client-embeddings.test.py
─────────────────────────────────────────────────────────────────────────────
U96 (X/U-X6) — proves the ROUTED hand-off row for push-client-embeddings
lands in docs/FLEET-ROLL-RUNBOOK.md (the receiving run), names its owning
run and its mechanism file, carries the 2026-07-14 embedding-model EOL
deadline context, and cites D21 — plus that the citation is not stale: the
mechanism file and the migration-check script it names must actually exist,
and the cited header lines must actually carry the contract they're quoted
for.

FAIL-FIRST: this section is NEW. On the pre-fix tree
docs/FLEET-ROLL-RUNBOOK.md contains zero occurrences of "push-client-embeddings"
— every assertion in TestHandoffRowPresent below fails against that tree.

Per the D21 binary-acceptance test (spec X.6 / U-X6): "the assembled v2 E.2
contains exactly one such row ... the row names the receiving run and the
mechanism file ... a whole-document search shows the item ROUTED, not
unowned and not absent." This test operationalizes that against the repo
artifact that models "the receiving run" (docs/FLEET-ROLL-RUNBOOK.md).

Run:
    python3 tests/unit/fleet-roll-handoff-push-client-embeddings.test.py -v
"""
from __future__ import annotations

import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent

_RUNBOOK = _REPO_ROOT / "docs" / "FLEET-ROLL-RUNBOOK.md"
_MECHANISM_FILE = _REPO_ROOT / "shared-utils" / "sop-embed-once" / "build-and-publish.sh"
_MIGRATION_CHECK = _REPO_ROOT / "scripts" / "pre-july14-embedding-migration-check.sh"

_ITEM_TOKEN = "push-client-embeddings"
_EOL_DATE = "2026-07-14"
_EOL_MODEL = "gemini-embedding-001"
_DECISION_ID = "D21"


class TestHandoffRowPresent(unittest.TestCase):
    """The row exists exactly once and names what D21/U96 require it to name."""

    @classmethod
    def setUpClass(cls) -> None:
        assert _RUNBOOK.is_file(), f"docs/FLEET-ROLL-RUNBOOK.md not found at {_RUNBOOK}"
        cls.text = _RUNBOOK.read_text(encoding="utf-8")

    def test_item_appears_exactly_once(self) -> None:
        # "exactly one such row" (X.6 binary acceptance) — not duplicated,
        # not silently multiplied by a later careless edit.
        self.assertEqual(
            self.text.count(_ITEM_TOKEN),
            1,
            f"expected exactly one '{_ITEM_TOKEN}' occurrence in the runbook, "
            f"found {self.text.count(_ITEM_TOKEN)}",
        )

    def test_hand_off_section_header_present(self) -> None:
        self.assertIn("## Routed hand-off items", self.text)

    def test_names_the_receiving_run(self) -> None:
        # The receiving run is this very document (the fleet-roll run). The
        # row must say so explicitly, not leave ownership implicit.
        self.assertIn("What this run owns", self.text)
        self.assertIn("DISTRIBUTION", self.text)

    def test_names_the_mechanism_file_with_line_citation(self) -> None:
        self.assertIn(
            "shared-utils/sop-embed-once/build-and-publish.sh:1-17", self.text
        )

    def test_carries_the_eol_deadline_context(self) -> None:
        self.assertIn(_EOL_MODEL, self.text)
        self.assertIn(_EOL_DATE, self.text)
        self.assertIn("scripts/pre-july14-embedding-migration-check.sh", self.text)

    def test_cites_the_routing_decision(self) -> None:
        self.assertIn(_DECISION_ID, self.text)
        self.assertIn("ROUTED", self.text)

    def test_not_unowned_and_not_absent(self) -> None:
        # Guard against a row that names the item but never resolves it
        # (e.g. leaving it as an open question) — the whole-document search
        # must show a settled ROUTED disposition, not a TBD.
        self.assertNotIn("TBD", self.text.split(_ITEM_TOKEN)[0][-200:])
        self.assertIn("ROUTED not dropped", self.text)


class TestCitationsAreNotStale(unittest.TestCase):
    """The doc cites real files with real content — catch drift, not just prose."""

    def test_mechanism_file_exists(self) -> None:
        self.assertTrue(
            _MECHANISM_FILE.is_file(),
            f"cited mechanism file missing: {_MECHANISM_FILE}",
        )

    def test_mechanism_file_header_carries_the_claimed_contract(self) -> None:
        header_lines = _MECHANISM_FILE.read_text(encoding="utf-8").splitlines()[:17]
        header = "\n".join(header_lines)
        # The row's parenthetical paraphrases the header's own contract
        # statement (embed ONCE with the operator's key; clients pull
        # read-only). If a future edit drops that language, this test must
        # fail — the citation would have gone stale.
        self.assertIn("ONCE", header)
        self.assertIn("OPERATOR", header.upper())
        self.assertIn("read-only", header)
        self.assertIn("CLIENT's own key", header)

    def test_migration_check_script_exists(self) -> None:
        self.assertTrue(
            _MIGRATION_CHECK.is_file(),
            f"cited migration-check script missing: {_MIGRATION_CHECK}",
        )

    def test_migration_check_script_names_the_same_dying_model_and_date(self) -> None:
        text = _MIGRATION_CHECK.read_text(encoding="utf-8")
        self.assertIn(_EOL_MODEL, text)
        self.assertIn(_EOL_DATE, text)


if __name__ == "__main__":
    unittest.main()
