#!/usr/bin/env python3
"""test_intake_contract_authority.py — T2-38 contract-authority contract.

intake/email-intake-questions.json describes itself as "the authoritative spec
that prove-email.py loads for the intake gate". Nothing loaded it: the required
field tuple was hardcoded in tools/prove-email.py, so editing the declared
authority changed nothing and the two could drift apart with no signal.

BOTH DIRECTIONS ARE REQUIRED:
  * editing the contract CHANGES the prover's required set   (the authority is real)
  * an unreadable/empty contract is REPORTED, never silently replaced by a
    built-in list  (a checker that cannot run must not count as a pass)
  * the set derived from the shipped contract is unchanged from the tuple it
    replaces  (anti-false-fail: no brief that passed yesterday fails today)

Hermetic: copies tools/ + intake/ into a temp dir, mutates only the copy.
stdlib only, no network, no fleet box.

Usage: python3 50-email-engine/test_intake_contract_authority.py
Exit:  0 = the contract is authoritative; 1 = it is not.
"""

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent

# The exact tuple that was hardcoded in tools/prove-email.py before T2-38. Pinned
# here so a contract edit that silently changes what every brief is graded against
# has to be a deliberate, visible change to this list too.
LEGACY_REQUIRED = ("objective", "buyer_type", "offer", "brand_voice",
                   "sequence_position", "founder_name")


def load_prover(root: Path, tag: str):
    spec = importlib.util.spec_from_file_location("pe_" + tag, root / "tools" / "prove-email.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class IntakeContractAuthority(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="intake-contract-")
        self.root = Path(self._tmp.name)
        shutil.copytree(SKILL_DIR / "tools", self.root / "tools")
        shutil.copytree(SKILL_DIR / "intake", self.root / "intake")
        self.contract = self.root / "intake" / "email-intake-questions.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_shipped_contract_yields_the_established_required_set(self):
        """Anti-false-fail: deriving the set must not change what briefs are graded against."""
        pe = load_prover(self.root, "shipped")
        self.assertIsNone(pe.REQUIRED_BRIEF_ERROR)
        self.assertEqual(tuple(pe.REQUIRED_BRIEF), LEGACY_REQUIRED)

    def test_adding_a_required_question_changes_the_required_set(self):
        """The declared authority must actually be authoritative."""
        doc = json.loads(self.contract.read_text())
        doc["questions"].append({
            "id": "campaign_window", "order": 9, "prompt": "synthetic test question",
            "kind": "text", "required": True, "storeOn": "campaign_window",
        })
        self.contract.write_text(json.dumps(doc))
        pe = load_prover(self.root, "added")
        self.assertIn("campaign_window", pe.REQUIRED_BRIEF,
                      "editing the contract did not change the prover's required set")

    def test_removing_a_required_flag_changes_the_required_set(self):
        doc = json.loads(self.contract.read_text())
        for q in doc["questions"]:
            if q.get("storeOn") == "offer":
                q["required"] = False
        self.contract.write_text(json.dumps(doc))
        pe = load_prover(self.root, "removed")
        self.assertNotIn("offer", pe.REQUIRED_BRIEF)

    def test_unreadable_contract_is_reported_not_silently_replaced(self):
        self.contract.unlink()
        pe = load_prover(self.root, "missing")
        self.assertEqual(tuple(pe.REQUIRED_BRIEF), ())
        self.assertTrue(pe.REQUIRED_BRIEF_ERROR)
        self.assertIn("unreadable", pe.REQUIRED_BRIEF_ERROR)

    def test_unparseable_contract_is_reported(self):
        self.contract.write_text("{ this is not json")
        pe = load_prover(self.root, "broken")
        self.assertTrue(pe.REQUIRED_BRIEF_ERROR)

    def test_empty_questions_array_is_reported(self):
        self.contract.write_text(json.dumps({"questions": []}))
        pe = load_prover(self.root, "empty")
        self.assertTrue(pe.REQUIRED_BRIEF_ERROR)

    def test_prove_returns_the_usage_code_when_the_contract_is_unreadable(self):
        """A prover that does not know what it is proving must not return PASS."""
        self.contract.unlink()
        pe = load_prover(self.root, "usage")
        target = SKILL_DIR / "examples" / "golden-landing-10" / "emails.json"
        rc = pe.prove(str(target), kind="sequence")
        self.assertEqual(rc, pe.EXIT_USAGE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
