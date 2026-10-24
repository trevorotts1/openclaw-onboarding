#!/usr/bin/env python3
"""Run-bound card calls honor the saved flow without requiring --step.

Only temporary synthetic runs are written. No real owner project is opened,
no provider is called, and generated send payloads are never transmitted.
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
from choice_card.intake_card import intake_card as IC
from choice_card.intake_card.intro import INTRO


def invoke(*args):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        rc = IC.main(list(args))
    return rc, output.getvalue().rstrip("\n")


class RunBoundCardContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="skill75-run-bound-card-")
        self.addCleanup(self.tmp.cleanup)
        self.run = Path(self.tmp.name) / "run"
        self.run.mkdir()

    def method_run(self):
        control = self.run / "control"
        control.mkdir()
        method = control / "method.json"
        method.write_text(json.dumps({"purpose": "paid_ad", "chosen_length_s": 120}))
        return method

    def test_default_run_bound_call_honors_existing_purpose_flow(self):
        method = self.method_run()
        before = method.read_bytes()
        rc, text = invoke("--run-dir", str(self.run))
        expected = IC.render_step(1, IC._shaped(IC.QUESTIONS, []))
        self.assertEqual(rc, 0)
        self.assertEqual(text, expected)
        self.assertTrue(text.splitlines()[0].endswith("- PURPOSE"))
        self.assertNotIn("Question 1 of 14 - OFFER", text)
        self.assertEqual(text.count("Question "), 1)
        self.assertEqual(method.read_bytes(), before)

    def test_new_default_run_resumes_exact_saved_pending_question(self):
        rc, first = invoke("--run-dir", str(self.run))
        self.assertEqual(rc, 0)
        self.assertTrue(first.splitlines()[0].endswith("- PURPOSE"))
        rc, second = invoke("--run-dir", str(self.run), "--reply", "1")
        self.assertEqual(rc, 0)
        self.assertTrue(second.startswith("Question 2 of "))
        self.assertTrue(second.splitlines()[0].endswith("- OFFER"))
        rc, raw = invoke("--run-dir", str(self.run), "--format", "session-json")
        state = json.loads(raw)
        self.assertEqual(rc, 0)
        self.assertEqual(state["answered_count"], 1)
        self.assertEqual(state["question_id"], "offer")
        self.assertEqual(state["message"], second)
        digest = state["question_digest"]
        for _ in range(2):
            rc, resumed = invoke("--run-dir", str(self.run))
            self.assertEqual(rc, 0)
            self.assertEqual(resumed, second)
        rc, raw = invoke("--run-dir", str(self.run), "--format", "session-json")
        resumed = json.loads(raw)
        self.assertEqual(resumed["question_digest"], digest)
        self.assertEqual(resumed["answered_count"], 1)
        self.assertFalse(resumed["done"])

    def test_run_state_file_without_step_keeps_intro_and_one_question(self):
        state_file = self.run / "run-state.json"
        rc, first = invoke("--run-state-file", str(state_file))
        self.assertEqual(rc, 0)
        self.assertEqual(first, INTRO)
        rc, second = invoke("--run-state-file", str(state_file))
        self.assertEqual(rc, 0)
        self.assertEqual(second, IC.conversation([])["message"])
        self.assertEqual(second.count("Question "), 1)

    def test_run_bound_send_payload_is_one_durable_question(self):
        self.method_run()
        rc, raw = invoke("--run-dir", str(self.run), "--format", "telegram-json", "--target", "fixture-target")
        payload = json.loads(raw)
        self.assertEqual(rc, 0)
        self.assertIsInstance(payload, dict)
        self.assertFalse(payload["done"])
        self.assertEqual(payload["session"]["question_id"], "purpose")
        self.assertEqual(payload["send"]["text"].count("Question "), 1)
        self.assertTrue(payload["send"]["text"].splitlines()[0].endswith("- PURPOSE"))

    def test_unbound_full_card_preview_and_step_preview_are_unchanged(self):
        rc, text = invoke()
        self.assertEqual(rc, 0)
        self.assertEqual(text, IC.render_card())
        rc, step = invoke("--step")
        self.assertEqual(rc, 0)
        self.assertEqual(step, IC.conversation([])["message"])

    def test_studio_export_remains_static_and_never_creates_intake_state(self):
        self.method_run()
        rc, unbound = invoke("--format", "studio-json")
        self.assertEqual(rc, 0)
        rc, bound = invoke("--run-dir", str(self.run), "--format", "studio-json")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(bound), json.loads(unbound))
        self.assertFalse((self.run / "control" / "intake-session.json").exists())


if __name__ == "__main__":
    unittest.main()
