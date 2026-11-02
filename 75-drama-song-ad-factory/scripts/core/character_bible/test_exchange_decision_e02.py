#!/usr/bin/env python3
"""E02: same cast size, opposite verdicts -- consequential passes, decorative
praise fails on the unchanged decision, and the names / word-count proxies are
planted failures. Run: python3 test_exchange_decision_e02.py (or pytest)."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for _p in (CORE, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from character_bible import character_bible as CB  # noqa: E402
from character_bible import exchange_decision as ED  # noqa: E402


def _char(name, role, voice_dir):
    return {"name": name, "role": role, "want": "w " + name, "wound": "x " + name,
            "relationships": "r " + name, "consequential_action": "a " + name,
            "voice": "v " + name, "person": True, "speaks": True,
            "voice_direction": voice_dir}


CAST = {"schema": CB.CAST_SCHEMA, "mode": "ensemble", "characters": [
    _char("Mara Vale", "protagonist",
          dict(register="alto", timbre="warm", articulation="clipped",
               delivery="restrained", emotional_progression="guarded to resolved",
               version_treatment="dry lead")),
    _char("Dane Rook", "villain",
          dict(register="baritone", timbre="bright", articulation="open",
               delivery="theatrical", emotional_progression="charming to cold",
               version_treatment="double-tracked")),
]}


def sheet(a, b):
    return "[Dane Rook (male): smooth]\n%s\n[Mara Vale (female): steady]\n%s\n" % (a, b)


REPLY = "Then you get nothing. I will burn the stock before I hand you the keys."
CONSEQ = sheet("Sign the deed tonight or the bank takes the shop at dawn.", REPLY)
THANKS = "Thank you. It is kind of you to say so; I do try to keep it tidy."
DECOR = sheet("Your window display tonight was lovely, truly a credit to the street.",
              THANKS)
NAMES = sheet("Dane Rook. Mara Vale. Dane Rook.", "Mara Vale. Dane Rook. Mara Vale.")
WORDS = sheet(" ".join(["words"] * 12) + ".", " ".join(["words"] * 12) + ".")

CHANGED = {"decider": "Mara Vale", "before": "sell the shop to Dane",
           "after": "burn the stock rather than sell", "evidence_line": REPLY}
UNCHANGED = {"decider": "Mara Vale", "before": "keep the shop",
             "after": "Keep the shop", "evidence_line": THANKS}


class ExchangeDecision(unittest.TestCase):
    def test_structural_gate_cannot_tell_them_apart(self):
        # the defect E02 closes: every scene below passes the existing gate
        for s in (CONSEQ, DECOR, NAMES, WORDS):
            self.assertEqual(CB.check_cast(CAST, sheet_text=s)["verdict"], "PASS")

    def test_pair_has_opposite_verdicts(self):
        self.assertEqual(len(CB.speaker_turns(CONSEQ)), len(CB.speaker_turns(DECOR)))
        good = ED.check_exchange(CAST, CONSEQ, CHANGED)
        bad = ED.check_exchange(CAST, DECOR, UNCHANGED)
        self.assertEqual((good["verdict"], bad["verdict"]), ("PASS", "FAIL"))
        self.assertEqual(bad["reason_code"], ED.CODE_UNCHANGED)
        self.assertIn("unchanged", bad["detail"])
        self.assertIn("keep the shop", bad["detail"])

    def test_decorative_cannot_borrow_the_consequential_record(self):
        r = ED.check_exchange(CAST, DECOR, CHANGED)  # claimed change, line not spoken
        self.assertEqual(r["reason_code"], ED.CODE_EVIDENCE)

    def test_proxy_cases_fail(self):
        for s in (NAMES, WORDS):
            self.assertEqual(ED.check_exchange(CAST, s, None)["reason_code"],
                             ED.CODE_NO_DECISION)
            self.assertEqual(ED.check_exchange(CAST, s, CHANGED)["verdict"], "FAIL")

    def test_decider_must_answer_an_opponent(self):
        ex = dict(CHANGED, decider="Dane Rook", evidence_line=REPLY)
        self.assertEqual(ED.check_exchange(CAST, CONSEQ, ex)["verdict"], "FAIL")
        ex = dict(CHANGED, decider="Nobody")
        self.assertEqual(ED.check_exchange(CAST, CONSEQ, ex)["reason_code"],
                         ED.CODE_DECIDER)


if __name__ == "__main__":
    unittest.main()
