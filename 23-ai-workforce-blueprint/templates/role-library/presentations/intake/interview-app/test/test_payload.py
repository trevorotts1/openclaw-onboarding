#!/usr/bin/env python3
"""Offline gate for build_questions_payload.py — proves the curated set is
derived from the canonical JSONs and respects the 7-9 core contract (19 core
questions plus the two conditional U026 waiver follow-ups, 21 total), and
that the signature set (FIX-PLAN Item 13, step S8) is built whole from
Skill 51's sp-8-questions.json.
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
        # Hard cap 20 binds the set WITHOUT the declined-reason waiver
        # follow-ups (each rides on its toggle's "no"; pinned in the
        # dedicated test below). Other conditional questions stay counted.
        waiver_followups = [q for q in payload["questions"]
                            if q["id"].endswith("_declined_reason")]
        self.assertLessEqual(len(ids) - len(waiver_followups), 20)
        self.assertGreaterEqual(len(ids), 7) # 7-9 core minimum
        # The mandatory new + derived questions are present.
        for must in ("speech_speed_preference", "want_sales_checkout",
                     "want_vsl_page", "want_email_sequences", "run_mode",
                     "sales_checkout_declined_reason",
                     "vsl_page_declined_reason"):
            self.assertIn(must, ids)
        # Store-on / label wiring survives.
        offer = next(q for q in payload["questions"] if q["id"] == "offer_name")
        self.assertEqual(offer["storeOn"], "deck_brief.OFFER_NAME")
        # The waiver follow-ups are asked ONLY on a "no" and store to the
        # canonical nested location both builder gates read first.
        for rid, toggle, field in (
                ("sales_checkout_declined_reason", "want_sales_checkout",
                 "SALES_CHECKOUT_DECLINED_REASON"),
                ("vsl_page_declined_reason", "want_vsl_page",
                 "VSL_PAGE_DECLINED_REASON")):
            q = next(q for q in payload["questions"] if q["id"] == rid)
            self.assertEqual(q["conditional_on"], {"id": toggle, "equals": "no"})
            self.assertEqual(q["storeOn"], f"pre_presentation_capture.{field}")
            self.assertTrue(q["required"])

    def test_email_election_pair_is_pinned(self):
        """Item 33c: the Skill 50 email election rides the curated set beside
        the other upsell elections. The toggle is an opt-in (default "no");
        its declined-reason follow-up is conditional on the "no", required,
        and stored at the canonical pre_presentation_capture home -- the
        same waiver shape as the sales/VSL pairs."""
        intake_dir = self._canonical_intake_dir()
        if not (intake_dir / "deck-intake-questions.json").is_file():
            self.skipTest("canonical deck-intake-questions.json not found - cannot build curated set")
        specs = {"questions": []}
        std = json.loads((intake_dir / "deck-intake-questions.json").read_text(encoding="utf-8"))
        specs["questions"] = std.get("questions", [])
        store_target = std.get("storeTarget")
        upsell = intake_dir / "upsell-questions.json"
        if upsell.is_file():
            specs["questions"] += json.loads(upsell.read_text(encoding="utf-8")).get("questions", [])
        specs["questions"] += list(bqp.APP_ONLY_QUESTIONS.values())
        payload = bqp.build_curated_payload("RUN1", specs, bqp.DEFAULT_CURATED, store_target)
        by_id = {q["id"]: q for q in payload["questions"]}
        toggle = by_id["want_email_sequences"]
        self.assertEqual(toggle["storeOn"], "pre_presentation_capture.WANT_EMAIL_SEQUENCES")
        self.assertEqual(toggle["default"], "no")   # opt-in only; silence is not an election
        self.assertEqual(toggle["allowed_values"], ["yes", "no"])
        self.assertTrue(toggle["required"])
        reason = by_id["email_sequences_declined_reason"]
        self.assertEqual(reason["storeOn"], "pre_presentation_capture.EMAIL_SEQUENCES_DECLINED_REASON")
        self.assertEqual(reason["conditional_on"],
                         {"id": "want_email_sequences", "equals": "no"})
        self.assertTrue(reason["required"])
        # The follow-up sits immediately after its toggle in the ask order.
        ids = [q["id"] for q in payload["questions"]]
        self.assertEqual(ids.index("email_sequences_declined_reason"),
                         ids.index("want_email_sequences") + 1)

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


# A fixture in the shape of Skill 51's sp-8-questions.json: q1..q8 in spec
# order, each carrying its sp_intake storeOn key, one carrying a spec
# internal (note) the projection must drop, plus the frame-selection
# question the builder appends last.
SIGNATURE_SPEC = {
    "questions": [
        {"id": f"q{i}", "order": i, "prompt": f"Q{i}?", "kind": "text",
         "required": True, "storeOn": f"q{i}_key"}
        for i in range(1, 9)
    ],
    "frame_selection_question": {
        "id": "frame_selection", "order": 9, "prompt": "Which frame?",
        "kind": "enum", "required": True, "storeOn": "signature_frame",
        "allowed_values": ["rulebook", "vault", "quest", "original"],
        "value_labels": {"rulebook": "The Rulebook", "vault": "The Vault",
                         "quest": "The Quest", "original": "The Original"},
    },
}
SIGNATURE_SPEC["questions"][6]["note"] = "spec internal, must be dropped"


class TestSignaturePayload(unittest.TestCase):
    """FIX-PLAN Item 13, step S8: the signature payload path ported from
    the miniapp builder (previously the only signature payload builder)
    into this builder, with the miniapp builder's behavior as the
    reference. The miniapp's own test_payload.py pins the same set
    behavior against its builder."""

    def test_signature_appends_frame_and_keeps_spec_order(self):
        shuffled = {"questions": list(reversed(SIGNATURE_SPEC["questions"])),
                    "frame_selection_question": SIGNATURE_SPEC["frame_selection_question"]}
        payload = bqp.build_signature_payload("RUN2", shuffled)
        self.assertEqual(payload["run_id"], "RUN2")
        self.assertEqual(payload["question_set"], "signature")
        self.assertEqual(payload["source"], "sp-8-questions.json")
        ids = [q["id"] for q in payload["questions"]]
        self.assertEqual(len(ids), 9)
        self.assertEqual(ids[:8], [f"q{i}" for i in range(1, 9)])
        self.assertEqual(ids[-1], "frame_selection")

    def test_signature_projection_is_this_builders(self):
        """Port, not copy: the miniapp builder's projection drops storeOn;
        this builder's projection carries it, because this app routes
        answers by storeOn. The sp-8 keys are sp_intake record keys and
        ride verbatim (the storeTarget table never rewrites them), while
        spec internals outside the passthrough set are dropped."""
        payload = bqp.build_signature_payload("RUN6", SIGNATURE_SPEC)
        q1 = payload["questions"][0]
        self.assertEqual(q1["storeOn"], "q1_key")
        frame = payload["questions"][-1]
        self.assertEqual(frame["storeOn"], "signature_frame")
        self.assertEqual(frame["allowed_values"],
                         ["rulebook", "vault", "quest", "original"])
        self.assertIn("value_labels", frame)
        q7 = next(q for q in payload["questions"] if q["id"] == "q7")
        self.assertNotIn("note", q7)
        for q in payload["questions"]:
            self.assertTrue(q.get("prompt"))
            self.assertIn("kind", q)
            self.assertIn("required", q)

    def test_signature_requires_spec(self):
        with self.assertRaises(ValueError):
            bqp.build_signature_payload("RUN3", None)

    def test_signature_empty_spec_rejected(self):
        with self.assertRaises(ValueError):
            bqp.build_signature_payload("RUN4", {"questions": []})

    def test_against_real_sp8_json_if_present(self):
        root = bqp._project_root(HERE)
        sig = bqp.default_signature_path(root)
        if not sig.is_file():
            self.skipTest(f"canonical sp-8-questions.json not found at {sig}")
        spec = json.loads(sig.read_text(encoding="utf-8"))
        payload = bqp.build_signature_payload("RUNREAL", spec)
        ids = [q["id"] for q in payload["questions"]]
        self.assertEqual(ids, [f"q{i}" for i in range(1, 9)] + ["frame_selection"])
        self.assertEqual(payload["questions"][0]["storeOn"], "q1_title")
        self.assertEqual(payload["questions"][-1]["storeOn"], "signature_frame")
        self.assertEqual(payload["questions"][-1]["allowed_values"],
                         ["rulebook", "vault", "quest", "original"])
        for q in payload["questions"]:
            self.assertTrue(q.get("prompt"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
