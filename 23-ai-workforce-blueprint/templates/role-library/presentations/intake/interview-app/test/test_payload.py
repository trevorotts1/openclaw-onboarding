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
        for must in ("speech_speed_preference", "want_sales_checkout", "want_vsl_page"):
            self.assertIn(must, ids)
        # Store-on / label wiring survives.
        offer = next(q for q in payload["questions"] if q["id"] == "offer_name")
        self.assertEqual(offer["storeOn"], "deck_brief.OFFER_NAME")

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
