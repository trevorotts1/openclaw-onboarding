"""S75-035: a blocked "yes" says why in words; an unmatched reply asks again.

The client never sees a reason code. Each refusal keeps the saved answers and
puts one plain sentence before the recap; a reply that matches no offered option
repeats the question behind a plain "I didn't catch that" line.
"""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from choice_card.intake_card import intake_session as session


def _typed(qid):
    return {"id": qid, "label": qid.upper(), "ask": "Type your " + qid + ".",
            "why": "Your own words are preserved.", "free_text": True,
            "options": [("Type it in", "Use your own words.")]}


def _menu(qid, labels):
    return {"id": qid, "label": qid.upper(), "ask": "Choose your " + qid + ".",
            "why": "This is the existing menu.", "options": [(x, None) for x in labels],
            "recommended": 0}


class RefusalTextTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="s75-035-")
        self.run = Path(self.temp.name) / "run"
        self.run.mkdir()
        self.qs = [_typed("offer"), _typed("audience"),
                   _menu("music", ["Soul Ballad", "R&B Flow", "Soul Rise"])]

    def tearDown(self):
        self.temp.cleanup()

    def call(self, replies=(), **kw):
        return session.process(list(replies), self.qs, run_dir=str(self.run),
                               purpose_flow=False, **kw)

    def confirmable(self):
        self.call()
        self.call(["New Chapter Coaching"])
        self.call(["successful founders 45-60 building new routines"])
        st = self.call(["recommended"])
        self.assertEqual(st["question_id"], "recap")
        self.assertFalse(st["done"])
        return st

    def blocked(self, digest, code, *, ai_role=False):
        """A "yes" whose completion check returns ``code``."""
        target, other = ("_persist_ai_roles", "_persist_model_lock") if ai_role else \
                        ("_persist_model_lock", "_persist_ai_roles")
        with patch.object(session, target, return_value=code), \
                patch.object(session, other, return_value=None):
            return self.call(["yes"], question_id="recap", question_digest=digest)

    def test_named_refusals_start_with_their_sentence_and_not_the_code(self):
        st = self.confirmable()
        codes = ("testimonial-permission-pending", "AI_MODEL_BINDING_REFUSED",
                 "VIDEO_MODEL_STATE_UNAVAILABLE", "VIDEO_MODEL_LOCK_CONFLICT")
        for code in codes:
            with self.subTest(code=code):
                out = self.blocked(st["question_digest"], code,
                                   ai_role=(code != "VIDEO_MODEL_STATE_UNAVAILABLE"
                                            and code != "VIDEO_MODEL_LOCK_CONFLICT"))
                self.assertEqual(out["reason_code"], code)
                self.assertEqual(out["outcome"], "waiting")
                self.assertFalse(out["done"])
                self.assertTrue(out["message"].startswith(session.REFUSAL_TEXT[code]),
                                out["message"])
                self.assertIn("Here is what you picked:", out["message"])
                self.assertNotIn(code.upper(), out["message"].upper())
                self.assertEqual(
                    out["message"],
                    session.REFUSAL_TEXT[code] + "\n\n" + out["pending"]["message"])

    def test_unknown_code_gets_plain_words_and_goes_only_to_stderr(self):
        st = self.confirmable()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            out = self.blocked(st["question_digest"], "SOMETHING_UNMAPPED")
        self.assertEqual(out["reason_code"], "SOMETHING_UNMAPPED")
        self.assertTrue(out["message"].startswith(session.REFUSAL_OTHER_TEXT))
        self.assertNotIn("SOMETHING_UNMAPPED", out["message"])
        self.assertIn("SOMETHING_UNMAPPED", err.getvalue())

    def test_unmatched_answer_repeats_the_question_behind_a_plain_prefix(self):
        self.call()
        self.call(["New Chapter Coaching"])
        self.call(["successful founders 45-60 building new routines"])
        asked = self.call()
        self.assertEqual(asked["question_id"], "music")
        out = self.call(["cinematic soul"])
        self.assertEqual(out["reason_code"], "INVALID_OPTION")
        self.assertTrue(out["message"].startswith(session.INVALID_REPLY_PREFIX),
                        out["message"])
        self.assertEqual(out["message"],
                         session.INVALID_REPLY_PREFIX + "\n\n" + out["pending"]["message"])
        self.assertEqual(out["pending"]["message"], asked["message"])
        self.assertEqual(out["answered_count"], 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
