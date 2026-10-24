"""Offline acceptance of the supported durable factory card entrypoint."""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
CORE = HERE.parent
sys.path.insert(0, str(CORE))
sys.path.insert(0, str(HERE))
import factory as factory
import card_session_cli as cli
from choice_card.intake_card import intake_card as card
from choice_card.intake_card.intro import INTRO


class CardSessionCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="card-session-cli-")
        self.addCleanup(self.tmp.cleanup)
        self.run = Path(self.tmp.name) / "run"

    def turn(self, *args, run=True):
        argv = ["card", "--step", "--format", "session-json"]
        if run:
            argv += ["--run-dir", str(self.run)]
        out = io.StringIO()
        with redirect_stdout(out):
            code = factory.main(argv + list(args))
        return code, json.loads(out.getvalue())

    def reply(self, state, raw, *extra):
        return self.turn("--question-id", state["question_id"],
                         "--question-digest", state["question_digest"],
                         "--reply", raw, *extra)

    def test_no_state_path_fails_closed(self):
        code, result = self.turn(run=False)
        self.assertEqual(code, 1)
        self.assertEqual(result["reason_code"], "INTAKE_RUN_REQUIRED")
        self.assertFalse(result["done"])

    def test_missing_session_implementation_never_uses_stateless_replay(self):
        with mock.patch.object(cli.importlib, "import_module", side_effect=ImportError("not installed")):
            code, result = self.turn()
        self.assertEqual(code, 1)
        self.assertEqual(result["reason_code"], "INTAKE_SESSION_UNAVAILABLE")
        self.assertFalse(self.run.exists())

    def test_interrupt_resume_keeps_raw_business_fact(self):
        code, first = self.turn("--no-purpose-flow")
        self.assertEqual(code, 0)
        self.assertEqual(first["question_id"], "offer")
        raw = "New Me New Year New Love"
        code, second = self.reply(first, raw, "--no-purpose-flow")
        self.assertEqual(code, 0)
        self.assertEqual(second["question_id"], "link")
        self.assertEqual(second["answered_count"], 1)
        self.assertEqual(second["answers"][0]["text"], raw)
        # Fresh interpreter, no answer history supplied: it reads its own run.
        proc = subprocess.run([sys.executable, str(HERE / "factory.py"),
            "card", "--step", "--run-dir", str(self.run), "--format", "session-json"],
            capture_output=True, text=True, env=os.environ.copy())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        resumed = json.loads(proc.stdout)
        self.assertEqual(resumed["question_digest"], second["question_digest"])
        self.assertEqual(resumed["answers"], second["answers"])
        self.assertFalse(resumed["done"])

    def test_bulk_unreceipted_order_fails_closed_with_named_reason(self):
        code, refused = self.turn("--no-purpose-flow", "--reply", "First owner fact",
                                  "--reply", "Second owner fact")
        self.assertEqual(code, 2)
        self.assertEqual(refused["reason_code"], "QUESTION_NOT_PRESENTED")
        self.assertEqual(refused["answered_count"], 0)
        self.assertFalse(refused["done"])
        self.assertEqual(refused["question_id"], "offer")

    def test_verified_prior_facts_seed_without_changing_raw_meaning(self):
        seed = Path(self.tmp.name) / "prior-answers.json"
        rows = [{"question_id": "offer", "raw_answer": "New Me New Year New Love",
                 "source_ref": "owner-transcript:offer"},
                {"question_id": "audience", "raw_answer": "successful women 45–60 tired of waking up alone",
                 "source_ref": "owner-transcript:audience"}]
        seed.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        code, result = self.turn("--no-purpose-flow", "--seed-answers-file", str(seed))
        self.assertEqual(code, 0)
        self.assertFalse(result["done"])
        state = json.loads((self.run / "control" / "intake-session.json").read_text())
        for row in rows:
            saved = state["answer_records"][row["question_id"]]
            self.assertEqual(saved["raw_answer"], row["raw_answer"])
            self.assertEqual(saved["source_ref"], row["source_ref"])
        self.assertEqual(result["question_id"], "link")

    def test_prior_menu_number_cannot_be_seeded_as_an_owner_choice(self):
        seed = Path(self.tmp.name) / "unsafe-seed.json"
        seed.write_text(json.dumps([{"question_id": "model", "raw_answer": "1",
                                    "source_ref": "old-invented-menu"}]))
        code, result = self.turn("--no-purpose-flow", "--seed-answers-file", str(seed))
        self.assertEqual(code, 2)
        self.assertEqual(result["reason_code"], "SEED_MENU_IDENTITY_REQUIRED")
        self.assertFalse(result["done"])
        self.assertEqual(result["answered_count"], 0)

    def test_wrong_question_identity_cannot_consume_answer(self):
        _, first = self.turn("--no-purpose-flow")
        code, rejected = self.turn("--question-id", "audience", "--reply", "1")
        self.assertNotEqual(code, 0)
        self.assertEqual(rejected["answered_count"], 0)
        self.assertFalse(rejected["done"])
        _, resumed = self.turn()
        self.assertEqual(resumed["question_digest"], first["question_digest"])

    def test_unreadable_run_state_is_not_overwritten(self):
        self.run.mkdir()
        state = self.run / "run-state.json"
        state.write_text("{broken", encoding="utf-8")
        code, rejected = self.turn("--run-state-file", str(state))
        self.assertEqual(code, 1)
        self.assertEqual(rejected["reason_code"], "INTAKE_SESSION_FAILED")
        self.assertEqual(state.read_text(), "{broken")
        self.assertFalse((self.run / "control" / "intake-session.json").exists())

    def test_intro_is_exact_and_does_not_hide_a_pending_question(self):
        self.run.mkdir()
        state = self.run / "control" / "run-state.json"
        state.parent.mkdir()
        state.write_text(json.dumps({"keep": {"owner": "value"}}))
        code, intro = self.turn("--run-state-file", str(state), "--purpose-flow")
        self.assertEqual(code, 0)
        self.assertEqual(intro["message"], INTRO)
        self.assertIsNone(intro["question_id"])
        self.assertFalse((self.run / "control" / "intake-session.json").exists())
        self.assertEqual(json.loads(state.read_text())["keep"], {"owner": "value"})
        _, first = self.turn("--run-state-file", str(state))
        self.assertEqual(first["question_id"], "purpose")
        self.assertEqual(first["answered_count"], 0)
        self.assertNotIn(INTRO, first["message"])
        # The original new-run purpose flow survives the intro_shown marker.
        expected = card.render_step(1, card._shaped(card.QUESTIONS, []))
        self.assertEqual(first["message"], expected)

    def test_static_card_and_studio_exports_are_unchanged(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(factory.main(["card"]), 0)
        self.assertEqual(out.getvalue(), card.render_card() + "\n")
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(factory.main(["card", "--format", "studio-json"]), 0)
        self.assertEqual(json.loads(out.getvalue()), card.studio_json(conditional=True))
        self.assertFalse(self.run.exists())

    def test_next_waits_on_pending_durable_intake_without_handing_out_a_stage(self):
        _, first = self.turn("--no-purpose-flow")
        before = (self.run / "control" / "intake-session.json").read_bytes()
        out = io.StringIO()
        with redirect_stdout(out):
            code = factory.main(["next", "--run-dir", str(self.run)])
        result = json.loads(out.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(result["reason_code"], "INTAKE_NOT_CONFIRMED")
        self.assertIsNone(result["data"]["stage"])
        self.assertIsNone(result["data"]["command"])
        self.assertEqual(result["data"]["intake"]["question_id"], first["question_id"])
        self.assertEqual((self.run / "control" / "intake-session.json").read_bytes(), before)

    def test_next_preserves_grandfathered_run_behavior_without_a_session(self):
        self.run.mkdir()
        out = io.StringIO()
        with redirect_stdout(out):
            code = factory.main(["next", "--run-dir", str(self.run)])
        result = json.loads(out.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(result["reason_code"], "state-file-missing")
        self.assertFalse((self.run / "control" / "intake-session.json").exists())

    def test_next_rejects_malformed_session_without_overwriting_it(self):
        path = self.run / "control" / "intake-session.json"
        path.parent.mkdir(parents=True)
        path.write_text("{bad", encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out):
            code = factory.main(["next", "--run-dir", str(self.run)])
        result = json.loads(out.getvalue())
        self.assertEqual(code, 1)
        self.assertEqual(result["reason_code"], "INTAKE_SESSION_UNREADABLE")
        self.assertIsNone(result["data"]["command"])
        self.assertEqual(path.read_text(), "{bad")

    def test_send_payload_carries_identity_without_sending(self):
        argv = ["card", "--step", "--no-purpose-flow", "--run-dir", str(self.run),
                "--format", "telegram-json", "--target", "offline-fixture"]
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(factory.main(argv), 0)
        payload = json.loads(out.getvalue())
        self.assertFalse(payload["done"])
        self.assertEqual(payload["session"]["question_id"], "offer")
        self.assertEqual(payload["send"]["text"], card.render_step(1))
        self.assertTrue(payload["session"]["question_digest"])


if __name__ == "__main__":
    unittest.main()
