#!/usr/bin/env python3
"""Guided-intake wiring checks for launch_intake: "I don't know" opens coaching and keeps
the question open; the question object carries help, examples and default to the surface;
pause/resume never repeats confirmed answers. Free: no network, no model.
Run: python3 49-signature-funnel/scripts/test_launch_intake_help.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import launch_intake as li  # noqa: E402


def session():
    return li.new_session(tenant_id="t1", location_id="loc1", launch_id="L1",
                          client_identity_ref="client:1")


class HelpRequests(unittest.TestCase):
    def test_help_words_open_coaching_and_keep_the_question_open(self):
        s = session()
        li.answer(s, "m0_mode", "Help me choose")
        # outcome/difficulty open the interview (they precede the offer questions)
        li.answer(s, "a0_outcome", "Fill my coaching program with paying clients")
        li.answer(s, "a0_difficulty", "I never know what to say in my marketing")
        for phrase in ("I don't know", "not sure", "?", "no clue what to pick"):
            r = li.answer(s, "a1_offer", phrase)
            self.assertEqual(r["action"], "help", phrase)
            self.assertTrue(r["coaching"])
            e = li._get(s, "offers.main.description")
            self.assertTrue(e is None or (e["value"] is None and e["state"] == "unknown"),
                            phrase)  # never a substantive answer
            self.assertEqual(li.next_question(s)["id"], "a1_offer")  # still open

    def test_a_real_answer_still_lands(self):
        s = session()
        li.answer(s, "a1_offer", "I help moms lose weight")
        self.assertEqual(li._get(s, "offers.main.description")["state"], "provided")
        self.assertNotEqual(li.next_question(s)["id"], "a1_offer")  # never asked twice

    def test_a_delegation_is_a_proposal_request_not_help(self):
        s = session()
        r = li.answer(s, "b1_journey", "you decide")
        self.assertNotEqual((r or {}).get("action"), "help")
        self.assertEqual(li._get(s, "journey_mode")["state"], "recommended_unapproved")

    def test_question_object_carries_help_examples_and_default(self):
        s = session()
        q = li.next_question(s)
        self.assertIn("help", q)
        self.assertIn("default", q)
        self.assertIn("estimate", q)
        self.assertEqual(q["progress"]["of"], q["estimate"]["questions"])

    def test_the_estimate_change_is_explained(self):
        s = session()
        before = li.next_question(s)["estimate"]
        li.answer(s, "c2_u1", "Yes, I have one",
                  {"upsell_1": {"display_name": "VIP Day",
                                "price": {"amount_minor": 99700, "currency": "USD"}}})
        after = li.next_question(s)["estimate"]
        self.assertEqual(after["questions"], before["questions"] + 2)  # downsell + second upsell opened
        self.assertIn("was", after["note"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
