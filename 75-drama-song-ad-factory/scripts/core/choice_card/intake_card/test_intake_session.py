"""No-media regression checks for persisted, exact-menu intake turns."""
import copy
import json
from types import SimpleNamespace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from choice_card.intake_card import intake_session as session
from choice_card.intake_card import intake_card as card


def _typed(qid):
    return {"id": qid, "label": qid.upper(), "ask": "Type your " + qid + ".",
            "why": "Your own words are preserved.", "free_text": True,
            "options": [("Type it in", "Use your own words.")]}


def _menu(qid, labels):
    return {"id": qid, "label": qid.upper(), "ask": "Choose your " + qid + ".",
            "why": "This is the existing menu.", "options": [(x, None) for x in labels],
            "recommended": 0}


class IntakeSessionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="s75-intake-session-")
        self.run = Path(self.temp.name) / "run"
        self.run.mkdir()
        self.qs = [_typed("offer"), _typed("audience"),
                   _menu("music", ["Soul Ballad", "R&B Flow", "Soul Rise"])]

    def tearDown(self):
        self.temp.cleanup()

    def call(self, replies=(), **kw):
        return session.process(list(replies), self.qs, run_dir=str(self.run),
                               purpose_flow=False, **kw)

    def read(self):
        return json.loads((self.run / "control" / "intake-session.json").read_text())

    def advance(self):
        self.call()
        self.call(["New Chapter Coaching"])
        return self.call(["successful founders 45–60 building new routines"])

    def test_first_reply_cannot_answer_an_unseen_question(self):
        st = self.call(["Made-up offer"])
        self.assertEqual(st["reason_code"], "QUESTION_NOT_PRESENTED")
        self.assertEqual(st["answers"], [])
        self.assertEqual(st["message"], card.render_step(1, self.qs))
        self.assertEqual(self.read()["events"], [])

    def test_interrupted_calls_preserve_exact_facts_and_provenance(self):
        st = self.advance()
        self.assertEqual(st["question_id"], "music")
        ledger = self.read()
        self.assertEqual(ledger["answer_records"]["audience"]["raw_answer"],
                         "successful founders 45–60 building new routines")
        self.assertEqual(st["answers"][1]["value"], ledger["answer_records"]["audience"]["raw_answer"])
        for qid in ("offer", "audience"):
            rec = ledger["answer_records"][qid]
            self.assertEqual(rec["question_id"], qid)
            self.assertEqual(rec["source"], "client")
            self.assertTrue(rec["at_utc"])
            self.assertIn("Question ", rec["rendered_question"])
            self.assertEqual(len(rec["question_digest"]), 64)
        self.assertEqual(self.call()["answers"], st["answers"])

    def test_same_singleton_is_new_not_cumulative_replay(self):
        self.call()
        self.call(["same exact answer"])
        st = self.call(["same exact answer"])
        self.assertEqual(st["answered_count"], 2)
        self.assertEqual(len(self.read()["events"]), 2)

    def test_unknown_option_yes_and_wrong_identity_do_not_advance(self):
        st = self.advance()
        for reply in ("yes", "cinematic soul", "5", "all recommended"):
            refused = self.call([reply])
            self.assertEqual(refused["reason_code"], "INVALID_OPTION")
            self.assertEqual(refused["answered_count"], 2)
            self.assertEqual(refused["question_digest"], st["question_digest"])
        self.assertEqual(self.call(["1"], question_id="look")["reason_code"], "QUESTION_ID_MISMATCH")
        self.assertEqual(self.call(["1"], question_digest="stale")["reason_code"], "QUESTION_DIGEST_MISMATCH")
        self.assertEqual(self.call(["1"], source="assistant")["reason_code"], "ANSWER_SOURCE_REQUIRED")
        self.assertEqual(self.call(["Soul Rise"])["answers"][-1]["text"], "Soul Rise")

    def test_menu_reorder_rejects_numeric_then_accepts_new_explicit_answer(self):
        st = self.advance()
        original = st["question_digest"]
        self.qs[-1]["options"].reverse()
        refused = self.call(["1"], question_digest=original)
        self.assertEqual(refused["reason_code"], "CARD_REVISION_CHANGED")
        self.assertEqual(refused["answered_count"], 2)
        self.assertEqual(self.call(["1"], question_digest=original)["reason_code"], "QUESTION_DIGEST_MISMATCH")
        next_turn = self.call(["Soul Ballad"], question_digest=refused["question_digest"])
        self.assertEqual(next_turn["answers"][-1]["n"], 3)
        rec = self.read()["answer_records"]["music"]
        self.assertEqual(rec["option"]["label"], "Soul Ballad")
        self.assertEqual(rec["option"]["number_shown"], 3)

    def test_cumulative_legacy_replay_is_exact_and_only_one_new_turn(self):
        self.call()
        self.call(["My offer"])
        st = self.call(["My offer", "Women 45–60"])
        self.assertEqual(st["answered_count"], 2)
        again = self.call(["My offer", "Women 45–60"])
        self.assertEqual(again["reason_code"], "INTAKE_REPLAYED")
        self.assertEqual(len(self.read()["events"]), 2)
        refused = self.call(["Other offer", "Women 45–60", "1"])
        self.assertEqual(refused["reason_code"], "INTAKE_REPLAY_MISMATCH")
        refused = self.call(["My offer", "Women 45–60", "1", "yes"])
        self.assertEqual(refused["reason_code"], "ONE_REPLY_AT_A_TIME")

    def test_full_answers_still_wait_for_exact_recap_confirmation(self):
        self.advance()
        st = self.call(["recommended"])
        self.assertFalse(st["done"])
        self.assertEqual(st["question_id"], "recap")
        with patch.object(session, "_finish", return_value=None) as finish:
            st = self.call(["yes"], question_id="recap", question_digest=st["question_digest"])
            self.assertTrue(st["done"])
            self.assertEqual(st["answered_count"], st["total_count"])
            finish.assert_called_once()
            self.assertTrue(self.read()["confirmation"]["accepted"])
            self.call()
            finish.assert_called_once()

    def test_saved_option_revision_is_ambiguous_not_reinterpreted(self):
        self.advance()
        self.call(["1"])
        self.qs[-1]["options"].reverse()
        st = self.call(["yes"])
        self.assertEqual(st["reason_code"], "CARD_REVISION_CHANGED")
        self.assertFalse(st["done"])
        self.assertEqual(self.read()["answer_records"]["music"]["parsed"]["text"], "Soul Ballad")
        st = self.call(["Soul Ballad"], question_digest=st["question_digest"])
        self.assertEqual(st["answers"][-1]["text"], "Soul Ballad")
        self.assertFalse(st["done"])

    def test_corrupt_state_fails_closed_and_is_not_overwritten(self):
        self.call()
        p = self.run / "control" / "intake-session.json"
        p.write_text("{broken state")
        st = self.call(["My offer"])
        self.assertEqual(st["reason_code"], "INTAKE_SESSION_UNREADABLE")
        self.assertEqual(p.read_text(), "{broken state")

    def test_saved_option_mismatch_fails_closed_without_repairing_history(self):
        self.advance()
        self.call(["1"])
        state = self.read()
        state["answer_records"]["music"]["parsed"]["n"] = 3
        p = self.run / "control" / "intake-session.json"
        p.write_text(json.dumps(state))
        before = p.read_text()
        refused = self.call(["yes"])
        self.assertEqual(refused["reason_code"], "INTAKE_SESSION_UNREADABLE")
        self.assertEqual(p.read_text(), before)

    def test_true_yes_no_approval_menus_accept_explicit_yes_only(self):
        for qid, label in (("storyboard", "Yes, show me first"),
                           ("script", "Yes, show me first"),
                           ("song", "Yes, send me 3 versions to choose from")):
            q = _menu(qid, [label, "No, continue without showing me"])
            self.assertEqual(session._parse("yes", q)["n"], 1)
        self.assertIsNone(session._parse("yes", self.qs[-1]))

    def test_read_only_completion_inspects_exact_confirmation(self):
        self.advance()
        st = self.call(["1"])
        status = session.completion_status(self.run)
        self.assertTrue(status["valid"])
        self.assertFalse(status["done"])
        with patch.object(session, "_finish", return_value=None):
            self.call(["yes"])
        p = self.run / "control" / "intake-session.json"
        before, mtime = p.read_bytes(), p.stat().st_mtime_ns
        status = session.completion_status(self.run)
        self.assertTrue(status["valid"])
        self.assertTrue(status["done"])
        self.assertEqual(p.read_bytes(), before)
        self.assertEqual(p.stat().st_mtime_ns, mtime)
        corrupt = self.read()
        corrupt["confirmation"]["source"] = "assistant"
        p.write_text(json.dumps(corrupt))
        status = session.completion_status(self.run)
        self.assertFalse(status["valid"])
        self.assertFalse(status["done"])

    def test_completion_rejects_false_counts_and_missing_answers(self):
        self.advance()
        state = self.read()
        state["done"] = True
        state["answered_count"] = state["total_count"]
        (self.run / "control" / "intake-session.json").write_text(json.dumps(state))
        status = session.completion_status(self.run)
        self.assertFalse(status["valid"])
        self.assertFalse(status["done"])

    def test_seed_prior_business_facts_before_unknown_purpose(self):
        qs = self.qs
        st = session.seed_answers([
            {"question_id": "audience", "raw_answer": "Founders 45–60", "source_ref": "message:explicit-client-12"},
        ], qs, run_dir=self.run, purpose_flow=False)
        self.assertEqual(st["question_id"], "offer")
        self.assertEqual(st["saved_answer_count"], 1)
        st = self.call(["New Chapter Coaching"])
        self.assertEqual(st["question_id"], "music")
        self.assertEqual(st["answers"][1]["value"], "Founders 45–60")
        self.assertEqual(self.read()["answer_records"]["audience"]["source_ref"], "message:explicit-client-12")

    def test_seed_refuses_unprovenanced_recaps_old_numbers_and_conflicts(self):
        st = session.seed_answers([{"question_id": "audience", "raw_answer": "Founders"}],
                                  self.qs, run_dir=self.run, purpose_flow=False)
        self.assertEqual(st["reason_code"], "SEED_PROVENANCE_REQUIRED")
        self.advance()
        st = session.seed_answers([{"question_id": "music", "raw_answer": "1",
                                   "source_ref": "message:old-menu", "question_digest": self.call()["question_digest"]}],
                                  self.qs, run_dir=self.run, purpose_flow=False)
        self.assertEqual(st["reason_code"], "SEED_MENU_IDENTITY_REQUIRED")
        st = session.seed_answers([{"question_id": "offer", "raw_answer": "Different offer",
                                   "source_ref": "message:other-answer"}],
                                  self.qs, run_dir=self.run, purpose_flow=False)
        self.assertEqual(st["reason_code"], "SEED_CONFLICTS_WITH_SAVED_ANSWER")

    def test_seed_menu_needs_exact_current_identity_and_keeps_provenance(self):
        st = self.advance()
        st = session.seed_answers([{"question_id": "music", "raw_answer": "Soul Ballad",
                                   "source_ref": "message:explicit-music", "question_digest": st["question_digest"]}],
                                  self.qs, run_dir=self.run, purpose_flow=False)
        self.assertEqual(st["question_id"], "recap")
        self.assertFalse(st["done"])
        self.assertEqual(self.read()["answer_records"]["music"]["option"]["label"], "Soul Ballad")

    def test_legacy_numeric_answers_are_preserved_and_flagged_never_imported(self):
        legacy = self.run / "card-answers.json"
        data = {"schema_version": 2, "answers": [{"id": "music", "n": 3, "text": "assistant recap"}]}
        legacy.write_text(json.dumps(data))
        st = self.call()
        self.assertEqual(st["answers"], [])
        self.assertEqual(st["legacy_answers"]["status"], "unverified_preserved")
        self.assertEqual(json.loads(legacy.read_text()), data)

    def test_lock_has_native_windows_stdlib_branch(self):
        calls = []
        fake = SimpleNamespace(LK_LOCK=1, LK_UNLCK=2,
                               locking=lambda fd, kind, count: calls.append((kind, count)))
        with patch.object(session, "fcntl", None), patch.object(session, "msvcrt", fake, create=True):
            with session.session_lock(str(self.run / "windows.lock")):
                self.assertEqual(calls, [(1, 1)])
        self.assertEqual(calls, [(1, 1), (2, 1)])

    def test_seed_rejects_conflicting_duplicate_question_rows(self):
        rows = [{"question_id": "audience", "raw_answer": "Founders 45–60", "source_ref": "message:first"},
                {"question_id": "audience", "raw_answer": "Founders 30–40", "source_ref": "message:second"}]
        st = session.seed_answers(rows, self.qs, run_dir=self.run, purpose_flow=False)
        self.assertEqual(st["reason_code"], "SEED_DUPLICATE_OR_UNKNOWN_QUESTION")
        self.assertEqual(self.read()["answer_records"], {})

    def test_exact_original_questions_are_not_mutated(self):
        original = copy.deepcopy(self.qs)
        self.advance()
        self.call(["recommended"])
        self.assertEqual(self.qs, original)


if __name__ == "__main__":
    unittest.main()
