#!/usr/bin/env python3
"""PD-929: pin the client-facing email-election help string to ONE wording.

The defect this closes: PD-911 fixed the sentence in the CONTRACT (the app's
pages/questions.json, its index.html embed, deployed-r2 and schema mirror) but
the hosted session route does not read any of those for that value. The route
is load_specs() -> build_curated_payload() -> _project_question(), and the help
text it serves comes from the QUESTION BANK:

  intake/deck-intake-questions.json   (canonical standard rows)
  intake/upsell-questions.json        (canonical upsell rows)

Both banks still carried the old sentence "Default NO -- the email sequences
are an opt-in delivery option", so a hosted client was told one thing and the
contract said another, silently.

This test fails if the contract and EITHER bank disagree, or if the projected
hosted payload drifts from the contract for that question.

Run: python3 test/test_email_help_contract_agreement.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
APP = HERE.parent
sys.path.insert(0, str(APP / "payload"))

import build_questions_payload as bqp  # noqa: E402

QUESTION_ID = "want_email_sequences"


class TestEmailHelpAgreement(unittest.TestCase):
    """The contract wording and the bank wording are the same sentence, and
    the hosted projection serves exactly that sentence."""

    def setUp(self):
        self.intake_dir = (bqp._project_root(HERE) / "23-ai-workforce-blueprint"
                           / "templates" / "role-library" / "presentations"
                           / "intake")
        for name in ("deck-intake-questions.json", "upsell-questions.json"):
            if not (self.intake_dir / name).is_file():
                self.skipTest(f"canonical {name} not found — cannot compare")

    def _contract_help(self) -> str:
        """The CONTRACT's client-facing help for the email election.

        Read from pages/questions.json, the shipped snapshot the app renders
        when its session carries no server-supplied questions. This is the
        value PD-911 fixed.
        """
        contract = json.loads((APP / "pages" / "questions.json")
                              .read_text(encoding="utf-8"))
        row = next(q for q in contract["questions"]
                   if q.get("id") == QUESTION_ID)
        return row["help"]

    def _bank_help(self, filename: str) -> str:
        data = json.loads((self.intake_dir / filename).read_text(encoding="utf-8"))
        row = next(q for q in data["questions"] if q.get("id") == QUESTION_ID)
        return row["help"]

    def _projected_help(self) -> str:
        """Exactly what the hosted session serves: the route the bridge runs."""
        specs, _empty, store_target = bqp.load_specs(bqp._project_root(HERE))
        payload = bqp.build_curated_payload("PD929", specs, bqp.DEFAULT_CURATED,
                                            store_target)
        row = next(q for q in payload["questions"] if q["id"] == QUESTION_ID)
        return row["help"]

    def test_contract_and_both_banks_agree(self):
        contract = self._contract_help()
        upsell = self._bank_help("upsell-questions.json")
        deck = self._bank_help("deck-intake-questions.json")
        self.assertEqual(
            upsell, contract,
            "upsell-questions.json help has drifted from the contract wording")
        self.assertEqual(
            deck, contract,
            "deck-intake-questions.json help has drifted from the contract wording")

    def test_old_opt_in_sentence_is_gone_everywhere(self):
        """The exact sentence PD-911 retired must not survive in any source
        the hosted route can reach."""
        old = "opt-in delivery option"
        for label, value in (
                ("contract", self._contract_help()),
                ("upsell-questions.json", self._bank_help("upsell-questions.json")),
                ("deck-intake-questions.json", self._bank_help("deck-intake-questions.json")),
                ("projected hosted payload", self._projected_help())):
            self.assertNotIn(old, value,
                             f"the retired sentence is still served by: {label}")

    def test_projected_hosted_help_equals_contract(self):
        """The end of the route: what the client is actually shown."""
        self.assertEqual(self._projected_help(), self._contract_help(),
                         "the hosted session serves different help than the contract")


if __name__ == "__main__":
    unittest.main(verbosity=2)
