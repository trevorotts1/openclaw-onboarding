#!/usr/bin/env python3
"""Offline gate for build_questions_payload.py.

Proves the payload the mini-app renders is generated FROM the canonical intake
JSONs (single source of truth), for both the standard and signature sets.
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

STANDARD_SPEC = {
    "questions": [
        {"id": "deck_type", "order": 0, "prompt": "Which deck?", "kind": "enum",
         "required": True, "allowed_values": ["webinar", "signature_presentation"],
         "value_labels": {"webinar": "Standard", "signature_presentation": "Signature"},
         "storeOn": "DECK_TYPE", "resolverHint": "should be dropped"},
        {"id": "grounded", "order": 3, "prompt": "Your content?", "kind": "text", "required": True},
        {"id": "wpm", "order": 1, "prompt": "Pace?", "kind": "integer", "required": False, "default": 140},
    ]
}

SIGNATURE_SPEC = {
    "questions": [{"id": f"q{i}", "order": i, "prompt": f"Q{i}?", "kind": "text", "required": True}
                  for i in range(1, 9)],
    "frame_selection_question": {
        "id": "frame_selection", "order": 9, "prompt": "Which frame?", "kind": "enum",
        "required": True, "allowed_values": ["rulebook", "vault", "quest", "original"],
    },
}


class TestPayload(unittest.TestCase):
    def test_standard_sorted_and_projected(self):
        payload = bqp.build_payload("RUN1", "standard", STANDARD_SPEC, None)
        self.assertEqual(payload["run_id"], "RUN1")
        self.assertEqual(payload["question_set"], "standard")
        ids = [q["id"] for q in payload["questions"]]
        self.assertEqual(ids, ["deck_type", "wpm", "grounded"])  # sorted by order
        # UI-irrelevant internals are stripped.
        self.assertNotIn("storeOn", payload["questions"][0])
        self.assertNotIn("resolverHint", payload["questions"][0])
        # UI-relevant fields survive.
        self.assertIn("value_labels", payload["questions"][0])
        self.assertEqual(payload["questions"][0]["allowed_values"], ["webinar", "signature_presentation"])

    def test_signature_appends_frame(self):
        payload = bqp.build_payload("RUN2", "signature", STANDARD_SPEC, SIGNATURE_SPEC)
        ids = [q["id"] for q in payload["questions"]]
        self.assertEqual(len(ids), 9)
        self.assertEqual(ids[:8], [f"q{i}" for i in range(1, 9)])
        self.assertEqual(ids[-1], "frame_selection")

    def test_signature_requires_spec(self):
        with self.assertRaises(ValueError):
            bqp.build_payload("RUN3", "signature", STANDARD_SPEC, None)

    def test_unknown_set_rejected(self):
        with self.assertRaises(ValueError):
            bqp.build_payload("RUN4", "podcast", STANDARD_SPEC, None)

    def test_every_question_has_a_prompt(self):
        payload = bqp.build_payload("RUN5", "standard", STANDARD_SPEC, None)
        for q in payload["questions"]:
            self.assertTrue(q.get("prompt"))
            self.assertIn("kind", q)
            self.assertIn("required", q)

    def test_against_real_canonical_jsons_if_present(self):
        root = bqp._project_root(HERE)
        std = bqp.default_standard_path(root)
        sig = bqp.default_signature_path(root)
        if not std.is_file():
            self.skipTest(f"canonical standard JSON not found at {std}")
        std_spec = json.loads(std.read_text(encoding="utf-8"))
        payload = bqp.build_payload("RUNREAL", "standard", std_spec, None)
        # Order-0 canonical question is the type-picker (`presentation_type`),
        # which replaced the old binary `deck_type` question in the typepicker
        # unit — it derives deck_type/creation_mode/presentation_mode/audience_mode.
        self.assertEqual(payload["questions"][0]["id"], "presentation_type")
        self.assertGreaterEqual(len(payload["questions"]), 8)
        if sig.is_file():
            sig_spec = json.loads(sig.read_text(encoding="utf-8"))
            sp = bqp.build_payload("RUNREAL", "signature", std_spec, sig_spec)
            self.assertEqual(len(sp["questions"]), 9)


if __name__ == "__main__":
    unittest.main(verbosity=2)
