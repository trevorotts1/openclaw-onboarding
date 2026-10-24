"""No-media regression checks for persisted, exact-menu intake turns."""
import copy
from contextlib import closing
import json
from types import SimpleNamespace
from pathlib import Path
import shutil
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

    def model_turns(self, n=2):
        qs = [next(q for q in card.QUESTIONS if q["id"] == "model")]
        session.process([], qs, run_dir=self.run, purpose_flow=False)
        st = session.process([str(n)], qs, run_dir=self.run, purpose_flow=False)
        self.assertFalse(st["done"])
        return qs, st

    def test_confirmed_nondefault_model_persists_and_dispatch_reads_that_choice(self):
        from choice_card.video_models import video_models as models
        from kie_dispatch import model_lock
        qs, st = self.model_turns(2)
        st = session.process(["yes"], qs, run_dir=self.run, purpose_flow=False,
                             question_id=st["question_id"], question_digest=st["question_digest"])
        self.assertTrue(st["done"], st)
        expected = models.model_for(2)
        db = self.run / "control" / "state.sqlite3"
        self.assertEqual(model_lock.read_locked_model(db, self.run.name),
                         expected.get("lock", expected["kie_model"]))
        request = models.request_for_run(db, st["run_id"], "A silent scene.", 5,
                                         first_frame_url="https://example.com/frame.png")
        self.assertEqual(request["model"], expected["kie_model"])
        self.assertEqual(st["model_lock"]["provider_identity"]["kie_model"], expected["kie_model"])
        self.assertTrue(session.completion_status(self.run)["done"])
        import sqlite3
        with closing(sqlite3.connect(db)) as con:
            from batch_mode.batch import STAGES
            self.assertEqual(con.execute("SELECT stage, state FROM stages ORDER BY rowid").fetchall(),
                             [(stage, "NOT_STARTED") for stage, _ in STAGES])

    def test_completion_inspector_does_not_recreate_missing_model_store(self):
        qs, st = self.model_turns(2)
        st = session.process(["yes"], qs, run_dir=self.run, purpose_flow=False)
        self.assertTrue(st["done"])
        db = self.run / "control" / "state.sqlite3"
        db.unlink()
        status = session.completion_status(self.run)
        self.assertFalse(status["valid"])
        self.assertFalse(db.exists())

    def test_actual_existing_run_id_is_reused_and_conflicting_lock_refused(self):
        import state_store
        from choice_card.video_models import video_models as models
        from kie_dispatch import model_lock
        db = self.run / "control" / "state.sqlite3"
        db.parent.mkdir(parents=True)
        with state_store.Store(db) as store:
            store.init_run("existing-real-run", ["research"])
        expected = models.model_for(1)
        old = expected.get("lock", expected["kie_model"])
        model_lock.lock_run_model(db, "existing-real-run", old)
        qs, st = self.model_turns(2)
        st = session.process(["yes"], qs, run_dir=self.run, purpose_flow=False)
        self.assertFalse(st["done"])
        self.assertEqual(st["reason_code"], "VIDEO_MODEL_LOCK_CONFLICT")
        self.assertEqual(model_lock.read_locked_model(db, "existing-real-run"), old)
        import sqlite3
        with closing(sqlite3.connect(db)) as con:
            self.assertEqual(con.execute("SELECT state FROM stages WHERE run_id='existing-real-run'").fetchone()[0], "NOT_STARTED")

    def test_multiple_existing_run_ids_are_rejected_without_a_lock(self):
        import state_store
        from kie_dispatch import model_lock
        db = self.run / "control" / "state.sqlite3"
        db.parent.mkdir(parents=True)
        with state_store.Store(db) as store:
            store.init_run("first", ["research"])
            store.init_run("second", ["research"])
        qs, st = self.model_turns(1)
        st = session.process(["yes"], qs, run_dir=self.run, purpose_flow=False)
        self.assertFalse(st["done"])
        self.assertEqual(st["reason_code"], "VIDEO_MODEL_RUN_ID_AMBIGUOUS")
        self.assertIsNone(model_lock.read_locked_model(db, "first"))

    def test_provider_route_change_cannot_reuse_saved_name_and_price(self):
        from choice_card.video_models import video_models as models
        qs, st = self.model_turns(2)
        row = models.model_for(2)
        altered = dict(row, kie_model="veo-3-1")
        with patch.object(models, "model_for", return_value=altered):
            st = session.process(["yes"], qs, run_dir=self.run, purpose_flow=False)
        self.assertFalse(st["done"])
        self.assertEqual(st["reason_code"], "INTAKE_SESSION_UNREADABLE")
        self.assertFalse((self.run / "control" / "state.sqlite3").exists())

    def test_revision_cannot_reinterpret_bare_old_numeric_reply(self):
        self.advance()
        self.qs[-1]["options"].reverse()
        self.call(["1"])
        st = self.call(["1"])
        self.assertEqual(st["reason_code"], "QUESTION_IDENTITY_REQUIRED")
        self.assertEqual(st["answered_count"], 2)

    def test_revision_identity_requirement_survives_invalid_reply(self):
        self.advance()
        self.qs[-1]["options"].reverse()
        self.call(["1"])
        self.call(["unoffered option"])
        st = self.call(["1"])
        self.assertEqual(st["reason_code"], "QUESTION_IDENTITY_REQUIRED")
        self.assertEqual(st["answered_count"], 2)

    def test_first_question_preface_is_exactly_the_existing_renderer_flow(self):
        self.qs[0]["preface"] = card.NO_SAVED_LINE
        expected = card.conversation([], self.qs, purpose_flow=False)["message"]
        self.assertEqual(self.call()["message"], expected)

    def test_malformed_existing_stage_store_refuses_without_mutation(self):
        import sqlite3
        db = self.run / "control" / "state.sqlite3"
        db.parent.mkdir(parents=True)
        with closing(sqlite3.connect(db)) as con:
            con.execute("CREATE TABLE stages(run_id TEXT, stage TEXT, state TEXT)")
            con.execute("INSERT INTO stages VALUES('actual-existing', 'research', 'NOT_STARTED')")
            con.commit()
        before = db.read_bytes()
        qs, st = self.model_turns(2)
        st = session.process(["yes"], qs, run_dir=self.run, purpose_flow=False)
        self.assertFalse(st["done"])
        self.assertEqual(st["reason_code"], "VIDEO_MODEL_STATE_UNAVAILABLE")
        self.assertEqual(db.read_bytes(), before)
        with closing(sqlite3.connect(db)) as con:
            self.assertEqual(con.execute("SELECT run_id, stage, state FROM stages").fetchall(),
                             [("actual-existing", "research", "NOT_STARTED")])
            self.assertEqual(con.execute("SELECT count(*) FROM sqlite_master WHERE name='video_model_lock'").fetchone()[0], 0)
        self.assertFalse(self.read()["done"])

    def pair_and_model_turns(self, runtime=None):
        qs = [next(q for q in card.QUESTIONS if q["id"] == qid) for qid in ("models", "model")]
        session.process([], qs, run_dir=self.run, purpose_flow=False, runtime=runtime)
        st = session.process(["opus-chain builds, haiku-chain checks"], qs,
                             run_dir=self.run, purpose_flow=False, source_ref="message:synthetic-explicit-pair")
        self.assertEqual(st["question_id"], "model", st)
        st = session.process(["2"], qs, run_dir=self.run, purpose_flow=False)
        self.assertEqual(st["question_id"], "recap", st)
        return qs

    def test_confirmed_pair_binds_exact_aliases_and_initialises_pending_stages(self):
        from choice_card.intake_card import ai_models
        from batch_mode.batch import STAGES
        qs = self.pair_and_model_turns(runtime="claude-nine")
        st = session.process(["yes"], qs, run_dir=self.run, purpose_flow=False)
        self.assertTrue(st["done"], st)
        bound = ai_models.load_bindings(self.run)
        self.assertEqual(bound["bindings"]["build"]["model_id"], "opus-chain")
        self.assertEqual(bound["bindings"]["check"]["model_id"], "haiku-chain")
        self.assertEqual(bound["bindings"]["build"]["dispatch"]["call_id"], "opus-chain")
        self.assertEqual(bound["bindings"]["check"]["dispatch"]["call_id"], "haiku-chain")
        self.assertEqual(bound["attempts"], [])
        import sqlite3
        db = self.run / "control" / "state.sqlite3"
        with closing(sqlite3.connect(db)) as con:
            self.assertEqual(con.execute("SELECT stage, state FROM stages ORDER BY rowid").fetchall(),
                             [(stage, "NOT_STARTED") for stage, _ in STAGES])
        self.assertTrue(session.completion_status(self.run)["done"])
        # A confirmed resume never rebinds, reinitialises or invokes a provider.
        binding_path = self.run / "model-bindings.json"
        before_binding, before_db = binding_path.read_bytes(), db.read_bytes()
        with patch.object(ai_models, "bind_roles", side_effect=AssertionError("must not rebind")):
            self.assertTrue(session.process([], qs, run_dir=self.run, purpose_flow=False)["done"])
            self.assertEqual(session.process(["yes"], qs, run_dir=self.run, purpose_flow=False)["reason_code"], "INTAKE_ALREADY_CONFIRMED")
        self.assertEqual(binding_path.read_bytes(), before_binding)
        self.assertEqual(db.read_bytes(), before_db)

    def test_identical_existing_pair_preserves_runtime_attempts_and_approval_bytes(self):
        from choice_card.intake_card import ai_models
        from batch_mode.batch import STAGES
        import state_store
        import sqlite3
        ai_models.bind_roles(self.run, "opus-chain", "haiku-chain", runtime="claude-nine")
        binding_path = self.run / "model-bindings.json"
        binding = json.loads(binding_path.read_text())
        binding["attempts"] = [{"attempt_id": "prior-synthetic-fixture", "fixture": True}]
        binding_path.write_text(json.dumps(binding))
        before = binding_path.read_bytes()
        approval = self.run / "prior-artifact-approval.json"
        approval.write_bytes(b"existing synthetic approval remains untouched")
        db = self.run / "control" / "state.sqlite3"
        db.parent.mkdir(parents=True)
        with state_store.Store(db) as store:
            store.init_run("existing-actual-id", ["research"])
            store.con.execute("UPDATE stages SET state='COMPLETE' WHERE run_id='existing-actual-id'")
            store.con.commit()
        qs = self.pair_and_model_turns()
        with patch.object(ai_models, "bind_roles", side_effect=AssertionError("existing pair must be reused")):
            st = session.process(["yes"], qs, run_dir=self.run, purpose_flow=False)
        self.assertTrue(st["done"], st)
        self.assertEqual(st["run_id"], "existing-actual-id")
        self.assertEqual(binding_path.read_bytes(), before)
        self.assertEqual(approval.read_bytes(), b"existing synthetic approval remains untouched")
        with closing(sqlite3.connect(db)) as con:
            rows = dict(con.execute("SELECT stage, state FROM stages WHERE run_id='existing-actual-id'"))
        self.assertEqual(rows.pop("research"), "COMPLETE")
        self.assertEqual(rows, {stage: "NOT_STARTED" for stage, _ in STAGES if stage != "research"})

    def test_conflicting_existing_pair_is_refused_before_stage_initialisation(self):
        from choice_card.intake_card import ai_models
        ai_models.bind_roles(self.run, "haiku-chain", "opus-chain", runtime="claude-nine")
        path = self.run / "model-bindings.json"
        before = path.read_bytes()
        qs = self.pair_and_model_turns(runtime="claude-nine")
        st = session.process(["yes"], qs, run_dir=self.run, purpose_flow=False)
        self.assertFalse(st["done"])
        self.assertEqual(st["reason_code"], "AI_MODEL_BINDING_CONFLICT")
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.run / "control" / "state.sqlite3").exists())

    def test_explicit_runtime_conflict_never_rewrites_existing_pair(self):
        from choice_card.intake_card import ai_models
        ai_models.bind_roles(self.run, "opus-chain", "haiku-chain", runtime="claude-nine")
        path = self.run / "model-bindings.json"
        before = path.read_bytes()
        qs = self.pair_and_model_turns(runtime="openclaw")
        st = session.process(["yes"], qs, run_dir=self.run, purpose_flow=False)
        self.assertFalse(st["done"])
        self.assertEqual(st["reason_code"], "AI_MODEL_BINDING_CONFLICT")
        self.assertEqual(path.read_bytes(), before)

    def test_prior_confirmed_handoff_upgrade_is_provenanced_idempotent_and_preserves_assets(self):
        from choice_card.intake_card import ai_models
        from batch_mode.batch import STAGES
        import sqlite3
        qs = [next(q for q in card.QUESTIONS if q["id"] == qid) for qid in
              ("offer", "audience", "models", "model", "storyboard", "song", "script")]
        state = session.process([], qs, run_dir=self.run, purpose_flow=False, target="original-fixture-target")
        replies = ["New Chapter Coaching", "Founders 45–60", "opus-chain builds, haiku-chain checks", "2", "yes", "yes", "yes", "yes"]
        for raw in replies:
            state = session.process([raw], qs, run_dir=self.run, purpose_flow=False,
                                    target="original-fixture-target", source_ref="message:original-synthetic-source")
        self.assertTrue(state["done"], state)
        # Recreate the prior release's provenanced, confirmed protocol state:
        # it had its exact model lock and approval preferences, but no AI or
        # canonical-stage bootstrap. Actual prior-source reproduction is also
        # recorded in private QC evidence; this fixture needs no Git checkout.
        state_path = self.run / "control" / "intake-session.json"
        old = json.loads(state_path.read_text())
        old.pop("ai_model_binding")
        old.pop("requested_runtime", None)
        state_path.write_text(json.dumps(old))
        (self.run / "model-bindings.json").unlink()
        db = self.run / "control" / "state.sqlite3"
        with closing(sqlite3.connect(db)) as con:
            con.execute("DELETE FROM stages")
            con.execute("DELETE FROM events WHERE kind='init'")
            con.commit()
        prior_copy = self.run.parent / "prior-release-copy"
        shutil.copytree(self.run, prior_copy)

        def snapshot(folder):
            return {str(p.relative_to(folder)): (p.read_bytes(), p.stat().st_mtime_ns)
                    for p in folder.rglob("*") if p.is_file()}

        self.assertTrue(session.completion_status(self.run, require_handoff=False)["done"])
        self.assertFalse(session.completion_status(self.run)["valid"])
        before = snapshot(self.run)
        with patch.object(session, "_finish", side_effect=AssertionError("approval/preference writers forbidden")):
            result = session.ensure_handoff(self.run, runtime="claude-nine")
        self.assertTrue(result["handoff_ready"], result)
        self.assertTrue(result["changed"])
        after = snapshot(self.run)
        for rel, original in before.items():
            if rel not in ("control/intake-session.json", "control/state.sqlite3"):
                self.assertEqual(after[rel], original, rel)
        upgraded = json.loads(state_path.read_text())
        for key in ("answer_records", "confirmation", "events", "pending", "run_id"):
            self.assertEqual(upgraded[key], old[key], key)
        with closing(sqlite3.connect(db)) as con:
            self.assertEqual(con.execute("SELECT stage, state FROM stages ORDER BY rowid").fetchall(),
                             [(stage, "NOT_STARTED") for stage, _ in STAGES])
        binding = ai_models.load_bindings(self.run)
        self.assertEqual(binding["bindings"]["build"]["model_id"], "opus-chain")
        self.assertEqual(binding["bindings"]["check"]["model_id"], "haiku-chain")
        self.assertEqual(binding["attempts"], [])
        ready_snapshot = snapshot(self.run)
        with patch.object(session, "_persist_ai_roles", side_effect=AssertionError("must not rebind")), patch.object(session, "_persist_model_lock", side_effect=AssertionError("must not rewrite DB")):
            again = session.ensure_handoff(self.run)
        self.assertTrue(again["handoff_ready"])
        self.assertFalse(again["changed"])
        self.assertEqual(snapshot(self.run), ready_snapshot)

        for condition in ("invalid_confirmation", "missing_db", "corrupt_db", "conflicting_roles"):
            with self.subTest(condition=condition):
                case = self.run.parent / condition
                shutil.copytree(prior_copy, case)
                case_state = case / "control" / "intake-session.json"
                case_db = case / "control" / "state.sqlite3"
                if condition == "invalid_confirmation":
                    untrusted = json.loads(case_state.read_text())
                    untrusted["confirmation"]["source"] = "assistant"
                    case_state.write_text(json.dumps(untrusted))
                elif condition == "missing_db":
                    case_db.unlink()
                elif condition == "corrupt_db":
                    case_db.write_bytes(b"malformed database fixture")
                else:
                    ai_models.bind_roles(case, "haiku-chain", "opus-chain", runtime="claude-nine")
                blocked_before = snapshot(case)
                result = session.ensure_handoff(case)
                self.assertFalse(result["handoff_ready"], result)
                self.assertFalse(result["changed"])
                self.assertEqual(snapshot(case), blocked_before)

    def test_exact_original_questions_are_not_mutated(self):
        original = copy.deepcopy(self.qs)
        self.advance()
        self.call(["recommended"])
        self.assertEqual(self.qs, original)


if __name__ == "__main__":
    unittest.main()
