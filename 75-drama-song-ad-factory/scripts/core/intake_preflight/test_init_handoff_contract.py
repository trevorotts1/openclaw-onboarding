"""No-generation CLI acceptance for confirmed intake's live dispatch handoff."""
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
CORE = HERE.parent
for path in (str(CORE), str(HERE)):
    if path not in sys.path:
        sys.path.insert(0, path)
import factory as factory
from batch_mode.batch import STAGES
from choice_card.intake_card import ai_models as models


class InitHandoffContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="intake-handoff-contract-")
        self.addCleanup(self.tmp.cleanup)
        self.run = Path(self.tmp.name) / "owner-test-fixture"

    def invoke(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = factory.main(list(argv))
        return code, json.loads(out.getvalue())

    def card(self, *extra):
        return self.invoke("card", "--step", "--run-dir", str(self.run),
                           "--format", "session-json", *extra)

    def confirm(self):
        code, state = self.card("--purpose-flow", "--runtime", "claude-nine")
        self.assertEqual(code, 0, state)
        self.assertEqual(state["question_id"], "purpose")
        facts = {"purpose": "A video for social media",
                 "where": "Facebook or Instagram - paid ad.",
                 "offer": "A fixture offer", "link": "https://example.com/fixture",
                 "audience": "successful women 45–60 tired of waking up alone",
                 "character": "Christine, a lawyer alone at the New Year's Eve ball drop",
                 "photos": "Generate the photos", "spend": "$25",
                 "models": "deepseek-chain builds, opus-chain checks"}
        for _ in range(40):
            qid = state["question_id"]
            if qid == "recap":
                self.assertFalse(state["done"])
                self.assertEqual(state["answered_count"], state["total_count"])
                raw = "yes"
            else:
                question = state["pending"]["definition"]
                raw = facts.get(qid, "recommended" if question.get("recommended") is not None else "1")
            code, state = self.card("--question-id", qid,
                "--question-digest", state["question_digest"], "--reply", raw,
                "--answer-source-ref", "offline-owner-fixture:" + qid)
            self.assertEqual(code, 0, state)
            if state["done"]:
                return state
        self.fail("the exact rendered intake never reached explicit confirmation")

    def test_bound_method_run_without_step_keeps_its_purpose_flow(self):
        control = self.run / "control"
        control.mkdir(parents=True)
        method = control / "method.json"
        prior = json.dumps({"purpose": "paid_ad", "owner_fact": "preserve this record"}, sort_keys=True)
        method.write_text(prior, encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out):
            code = factory.main(["card", "--run-dir", str(self.run)])
        self.assertEqual(code, 0)
        message = out.getvalue()
        self.assertIn("- PURPOSE", message.splitlines()[0])
        self.assertNotIn("Question 2 of", message)
        session_path = control / "intake-session.json"
        session = json.loads(session_path.read_text())
        self.assertTrue(session["purpose_flow"])
        self.assertEqual(session["pending"]["id"], "purpose")
        self.assertEqual(session["answer_records"], {})
        self.assertEqual(method.read_text(), prior)
        self.assertFalse((control / "state.sqlite3").exists())
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(factory.main(["card", "--run-dir", str(self.run)]), 0)
        self.assertEqual(out.getvalue(), message)
        self.assertEqual(method.read_text(), prior)
        # The explicit all-screen export is still a read-only export.
        before = session_path.read_bytes()
        _, export = self.invoke("card", "--run-dir", str(self.run), "--format", "studio-json")
        self.assertEqual(export["format"], "studio-json")
        self.assertEqual(session_path.read_bytes(), before)

    def test_confirm_initializes_real_stages_and_exposes_exact_admitted_aliases(self):
        confirmed = self.confirm()
        db = self.run / "control" / "state.sqlite3"
        self.assertTrue(db.is_file())
        with closing(sqlite3.connect(db)) as con:
            rows = con.execute("SELECT run_id,stage,state FROM stages ORDER BY rowid").fetchall()
        self.assertEqual([row[1] for row in rows], [stage_id for stage_id, _ in STAGES])
        self.assertEqual({row[2] for row in rows}, {"NOT_STARTED"})
        self.assertEqual({row[0] for row in rows}, {confirmed["run_id"]})
        bindings = json.loads((self.run / "model-bindings.json").read_text())
        self.assertEqual(bindings["bindings"]["build"]["model_id"], "deepseek-chain")
        self.assertEqual(bindings["bindings"]["check"]["model_id"], "opus-chain")
        self.assertEqual(bindings["attempts"], [])
        from choice_card.intake_card import intake_session as consumer_session
        with mock.patch.object(consumer_session, "ensure_handoff", wraps=consumer_session.ensure_handoff) as handoff:
            code, nxt = self.invoke("next", "--run-dir", str(self.run))
        self.assertTrue(handoff.called)
        self.assertEqual(code, 0, nxt)
        self.assertEqual(nxt["data"]["stage"], "research")
        self.assertTrue(nxt["data"]["command"])
        dispatch = nxt["data"]["ai_role_bindings"]
        self.assertEqual(dispatch["execution"], "admitted_not_called")
        for role, alias in (("build", "deepseek-chain"), ("check", "opus-chain"), ("repair", "opus-chain")):
            row = dispatch["roles"][role]
            self.assertEqual(row["call_id"], alias)
            self.assertTrue(row["admission"]["ok"])
        self.assertEqual(dispatch["roles"]["repair"]["binding_role"], "check")
        self.assertEqual(nxt["data"]["llm_dispatch"]["call_id"], "deepseek-chain")
        self.assertEqual(nxt["data"]["llm_dispatch"]["execution"], "admitted_not_called")
        self.assertEqual(json.loads((self.run / "model-bindings.json").read_text())["attempts"], [])
        _, resumed = self.card()
        self.assertTrue(resumed["done"])
        self.assertEqual(resumed["answers"], confirmed["answers"])
        method = json.loads((self.run / "control" / "method.json").read_text())
        self.assertEqual(method["purpose"], "paid_ad")

    def test_unavailable_admission_does_not_default_or_return_a_command(self):
        self.confirm()
        # Resolve the consumer's current module after the package test fixtures
        # may have reloaded it; patching a stale imported object proves nothing.
        from choice_card.intake_card import ai_models as active_models
        with mock.patch.object(active_models, "admit_dispatch", return_value={
                "ok": False, "error_code": "MODEL_UNAVAILABLE", "reason": "fixture route unavailable"}) as admission:
            code, nxt = self.invoke("next", "--run-dir", str(self.run))
        admission.assert_called_once()
        self.assertEqual(code, 1, nxt)
        self.assertEqual(nxt["reason_code"], "MODEL_UNAVAILABLE")
        self.assertIsNone(nxt["data"]["stage"])
        self.assertIsNone(nxt["data"]["command"])

    def test_mismatched_saved_call_identifier_is_refused(self):
        self.confirm()
        path = self.run / "model-bindings.json"
        doc = json.loads(path.read_text())
        doc["bindings"]["build"]["dispatch"]["call_id"] = "unselected-alias"
        path.write_text(json.dumps(doc))
        code, nxt = self.invoke("next", "--run-dir", str(self.run))
        self.assertEqual(code, 1)
        self.assertIsNone(nxt["data"]["command"])
        self.assertEqual(json.loads(path.read_text())["bindings"]["build"]["dispatch"]["call_id"], "unselected-alias")

    def test_provider_stage_keeps_its_own_model_and_command(self):
        self.confirm()
        provider = {"stage": "video-generation", "command": "fixture-provider --model minimax-h3/image-to-video",
                    "provider_model": "minimax-h3/image-to-video"}
        with mock.patch.object(factory, "_next_stage", return_value=factory.envelope(
                "next", "fixture", "ok", "next-stage", "fixture", data=dict(provider))):
            code, nxt = self.invoke("next", "--run-dir", str(self.run))
        self.assertEqual(code, 0)
        self.assertEqual(nxt["data"]["command"], provider["command"])
        self.assertEqual(nxt["data"]["provider_model"], provider["provider_model"])
        self.assertNotIn("llm_dispatch", nxt["data"])

    def test_no_session_no_bindings_preserves_legacy_next(self):
        self.run.mkdir()
        code, nxt = self.invoke("next", "--run-dir", str(self.run))
        self.assertEqual(code, 1)
        self.assertEqual(nxt["reason_code"], "state-file-missing")
        self.assertNotIn("ai_role_bindings", nxt["data"])
        self.assertFalse((self.run / "model-bindings.json").exists())


if __name__ == "__main__":
    unittest.main()
