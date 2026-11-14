#!/usr/bin/env python3
"""S75-018 C05 / U-GEN315: a resumed run applies the answers it already holds.

Run: python3 core/choice_card/intake_card/test_answer_reuse_wiring_u_gen315.py
"""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
CORE = HERE.parent.parent
sys.path.insert(0, str(CORE))
from choice_card.intake_card import intake_session as session  # noqa: E402


def _typed(qid):
    return {"id": qid, "label": qid.upper(), "ask": "Type your " + qid + ".",
            "why": "Your own words are preserved.", "free_text": True,
            "options": [("Type it in", "Use your own words.")]}


class ReuseWiringTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="s75-gen315-reuse-")
        self.run = Path(self.temp.name) / "run"
        self.run.mkdir()
        self.qs = [_typed("offer"), _typed("audience"), _typed("story")]

    def tearDown(self):
        self.temp.cleanup()

    def call(self, replies=(), qs=None):
        return session.process(list(replies), qs or self.qs, run_dir=str(self.run),
                               purpose_flow=False)

    def state(self):
        return json.loads((self.run / "control" / "intake-session.json").read_text())

    def test_plain_resume_applies_every_matching_answer(self):
        self.call()
        self.call(["The Quiet Kitchen"])
        self.call(["adults 40 to 60 caring for a parent"])
        shown = self.call()
        self.assertEqual(shown["reason_code"], "INTAKE_WAITING")
        self.assertEqual(shown["reuse"]["applied"], ["offer", "audience"])
        self.assertEqual(shown["reuse"]["refused"], [])

    def test_resume_applies_a_matching_answer_and_refuses_a_changed_one(self):
        self.call()
        self.call(["The Quiet Kitchen"])
        self.call(["adults 40 to 60 caring for a parent"])
        before = self.state()
        changed = copy.deepcopy(self.qs)
        changed[1]["ask"] = "A changed audience question."
        shown = self.call(qs=changed)
        self.assertEqual(shown["reason_code"], "CARD_REVISION_CHANGED")
        self.assertEqual(shown["reuse"]["applied"], ["offer"])
        self.assertEqual([r["question_id"] for r in shown["reuse"]["refused"]],
                         ["audience"])
        after = self.state()
        self.assertEqual(after["reuse"]["applied"], ["offer"])
        self.assertTrue(after["answer_records"]["offer"]["reused_at_utc"])
        # The changed question is refused: its saved answer is never overwritten.
        self.assertEqual(after["answer_records"]["audience"],
                         before["answer_records"]["audience"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
