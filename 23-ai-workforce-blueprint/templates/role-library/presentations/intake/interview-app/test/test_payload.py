#!/usr/bin/env python3
"""Offline gate for build_questions_payload.py — proves the curated set is
derived from the canonical JSONs and respects the 7-9 core / cap 20 contract.
Run: python3 test/test_payload.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "payload"))

import build_questions_payload as bqp  # noqa: E402


class TestPayload(unittest.TestCase):
    def _canonical_intake_dir(self):
        root = bqp._project_root(HERE)
        return (root / "23-ai-workforce-blueprint" / "templates" / "role-library"
                / "presentations" / "intake")

    def test_curated_set_contract(self):
        intake_dir = self._canonical_intake_dir()
        if not (intake_dir / "deck-intake-questions.json").is_file():
            self.skipTest("canonical deck-intake-questions.json not found — cannot build curated set")
        specs = {"questions": []}
        std = json.loads((intake_dir / "deck-intake-questions.json").read_text(encoding="utf-8"))
        specs["questions"] = std.get("questions", [])
        store_target = std.get("storeTarget")
        upsell = intake_dir / "upsell-questions.json"
        if upsell.is_file():
            specs["questions"] += json.loads(upsell.read_text(encoding="utf-8")).get("questions", [])
        specs["questions"] += list(bqp.APP_ONLY_QUESTIONS.values())
        payload = bqp.build_curated_payload("RUN1", specs, bqp.DEFAULT_CURATED, store_target)
        ids = [q["id"] for q in payload["questions"]]
        self.assertLessEqual(len(ids), 20)   # hard cap
        self.assertGreaterEqual(len(ids), 7) # 7-9 core minimum
        # The mandatory new + derived questions are present.
        for must in ("speech_speed_preference", "want_sales_checkout",
                     "want_vsl_page", "run_mode"):
            self.assertIn(must, ids)
        # Store-on / label wiring survives.
        offer = next(q for q in payload["questions"] if q["id"] == "offer_name")
        self.assertEqual(offer["storeOn"], "deck_brief.OFFER_NAME")

    def test_run_mode_is_projected_from_the_bank_never_hardcoded(self):
        """FIX 11. run_mode is a SUBFIELD of the bank's merged resource_plan
        turn, not a question row -- it rides that turn so the agent-driven
        interview never spends a 24th turn on it. The hosted app has no such
        ceiling but must not invent a second vocabulary, so its standalone
        question is PROJECTED from that subfield: the enum, the refused
        interview-depth words and the refusal message come from the bank, and
        only the client-facing sentence is the app's own.

        This is also the drift guard for RUN_MODE_FALLBACK_VOCABULARY, the
        mirror used when the bank is unreachable (a standalone app checkout)."""
        intake_dir = self._canonical_intake_dir()
        bank_file = intake_dir / "deck-intake-questions.json"
        if not bank_file.is_file():
            self.skipTest("canonical deck-intake-questions.json not found")
        bank = json.loads(bank_file.read_text(encoding="utf-8"))
        rp = [q for q in bank["questions"] if q["id"] == "resource_plan"][0]
        ann = rp["subfields"]["run_mode"]
        # No question row carries the id -- it really is only a subfield.
        self.assertEqual([q for q in bank["questions"] if q["id"] == "run_mode"], [])

        projected = bqp._project_run_mode_question(bank["questions"])
        self.assertEqual(projected["allowed_values"],
                         [str(v).lower() for v in ann["enum"]])
        self.assertEqual(projected["refuse_values"], list(ann["refuse_values"]))
        self.assertEqual(projected["refuse_message"], ann["refuse_message"])
        self.assertEqual(projected["default"], "")   # undeclared is undeclared
        # ... and the offline mirror says exactly the same thing.
        fb = bqp.RUN_MODE_FALLBACK_VOCABULARY
        self.assertEqual(fb["allowed_values"], projected["allowed_values"])
        self.assertEqual(fb["refuse_values"], projected["refuse_values"])
        self.assertEqual(fb["refuse_message"], projected["refuse_message"])
        # A run mode is an execution axis, never deck content.
        self.assertNotIn("deck_brief", projected["storeOn"])

    def test_run_mode_resolves_for_a_caller_that_built_its_own_pool(self):
        """The projection lives in build_curated_payload, not load_specs,
        because a curated id that resolves on one pool-assembly path and raises
        ValueError on the other is a trap -- this test IS the other path."""
        intake_dir = self._canonical_intake_dir()
        bank_file = intake_dir / "deck-intake-questions.json"
        if not bank_file.is_file():
            self.skipTest("canonical deck-intake-questions.json not found")
        specs = {"questions": json.loads(
            bank_file.read_text(encoding="utf-8"))["questions"]}
        payload = bqp.build_curated_payload("R", specs, ["offer_name", "run_mode"])
        ids = [q["id"] for q in payload["questions"]]
        self.assertEqual(ids, ["offer_name", "run_mode"])

    def test_missing_id_rejected(self):
        specs = {"questions": [{"id": "a", "prompt": "A"}]}
        with self.assertRaises(ValueError):
            bqp.build_curated_payload("R", specs, ["a", "ghost"])

    def test_every_question_has_prompt_and_kind(self):
        specs = {"questions": [{"id": f"q{i}", "order": i, "prompt": f"Q{i}", "kind": "text"} for i in range(3)]}
        payload = bqp.build_curated_payload("R", specs, ["q0", "q1", "q2"])
        for q in payload["questions"]:
            self.assertTrue(q.get("prompt"))
            self.assertIn("kind", q)


if __name__ == "__main__":
    unittest.main(verbosity=2)
