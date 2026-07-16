#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_intake_engine.py — offline unit tests for scripts/intake_engine.py
(Skill 62, build unit U9).

stdlib unittest only. Run:
  python3 -m unittest discover -s tests/unit -v
  (from the 62-cinematic-web-funnel-engine/ directory)
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _TESTS_DIR.parent.parent
_SCRIPTS_DIR = _SKILL_DIR / "scripts"
for p in (str(_SCRIPTS_DIR), str(_SCRIPTS_DIR / "lib")):
    if p not in sys.path:
        sys.path.insert(0, p)

import intake_engine as ie  # noqa: E402


def sample_answers() -> dict:
    return ie._sample_answer_map()


class TestQuestionBank(unittest.TestCase):
    def test_bank_loads_and_validates(self):
        bank = ie.load_question_bank(force_reload=True)
        self.assertEqual(len(bank["groups"]), 12)

    def test_bank_groups_are_in_the_spec_8_1_order(self):
        bank = ie.load_question_bank()
        slugs = [g["slug"] for g in sorted(bank["groups"], key=lambda g: g["order"])]
        self.assertEqual(
            slugs,
            [
                "project_goal", "audience", "offer", "brand", "content_source",
                "cinematic_direction", "conversion_infrastructure", "hosting",
                "mobile_strategy", "accessibility", "budget", "approval_workflow",
            ],
        )

    def test_every_question_id_is_group_dot_field(self):
        bank = ie.load_question_bank()
        for group in bank["groups"]:
            for q in group["questions"]:
                self.assertTrue(q["id"].startswith(group["slug"] + "."))


class TestOneQuestionAtATime(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cwfe-intake-ut-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_next_question_returns_a_single_dict_not_a_list(self):
        s = ie.IntakeSession(self.tmp, project_id="p1", known_context=None)
        q = s.next_question()
        self.assertIsInstance(q, dict)
        self.assertEqual(q["id"], "project_goal.deliverable_type")

    def test_answering_out_of_order_is_rejected(self):
        s = ie.IntakeSession(self.tmp, project_id="p1", known_context=None)
        with self.assertRaises(ie.UnknownQuestionError):
            s.answer("audience.identity", "x")

    def test_first_question_group_order_matches_bank(self):
        s = ie.IntakeSession(self.tmp, project_id="p1", known_context=None)
        seen_groups = []
        # Walk the first several base questions and confirm groups arrive in
        # ascending order (never out of sequence, never two groups interleaved).
        for _ in range(4):
            q = s.next_question()
            if q["group"] not in seen_groups:
                seen_groups.append(q["group"])
            s.answer(q["id"], sample_answers()[q["id"]])
        self.assertEqual(seen_groups, ["project_goal"])

    def test_invalid_enum_answer_rejected_without_mutating_state(self):
        s = ie.IntakeSession(self.tmp, project_id="p1", known_context=None)
        q = s.next_question()
        with self.assertRaises(ie.InvalidAnswerError):
            s.answer(q["id"], "totally-not-a-real-deliverable-type")
        # state must be unchanged — the same question is still next
        self.assertEqual(s.next_question()["id"], q["id"])

    def test_required_string_rejects_empty_string(self):
        s = ie.IntakeSession(self.tmp, project_id="p1", known_context=None)
        s.answer("project_goal.deliverable_type", "cinematic-website")
        with self.assertRaises(ie.InvalidAnswerError):
            s.answer("project_goal.success_action", "   ")


class TestKnownContextReuse(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cwfe-intake-ut-kc-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_known_value_is_offered_as_a_confirm_not_auto_filled(self):
        s = ie.IntakeSession(self.tmp, project_id="p1", known_context={"project_goal": {"deliverable_type": "cinematic-funnel"}})
        q = s.next_question()
        self.assertEqual(q["kind"], "confirm")
        self.assertEqual(q["known_value"], "cinematic-funnel")
        self.assertNotIn("project_goal.deliverable_type", s._answers)

    def test_confirming_true_reuses_value_with_correct_source(self):
        s = ie.IntakeSession(self.tmp, project_id="p1", known_context={"project_goal": {"deliverable_type": "cinematic-funnel"}})
        q = s.next_question()
        s.answer(q["id"], True)
        self.assertEqual(s._answers["project_goal.deliverable_type"]["value"], "cinematic-funnel")
        self.assertEqual(s._answers["project_goal.deliverable_type"]["source"], "known_context_confirmed")

    def test_declining_falls_through_to_a_normal_ask(self):
        s = ie.IntakeSession(self.tmp, project_id="p1", known_context={"project_goal": {"deliverable_type": "cinematic-funnel"}})
        q = s.next_question()
        s.answer(q["id"], False)
        q2 = s.next_question()
        self.assertEqual(q2["kind"], "answer")
        self.assertEqual(q2["id"], "project_goal.deliverable_type")
        s.answer(q2["id"], "cinematic-website")
        self.assertEqual(s._answers["project_goal.deliverable_type"]["source"], "asked")

    def test_missing_known_context_key_is_asked_normally(self):
        s = ie.IntakeSession(self.tmp, project_id="p1", known_context={"unrelated": "stuff"})
        q = s.next_question()
        self.assertEqual(q["kind"], "answer")

    def test_confirmation_is_persisted_to_known_context_json(self):
        s = ie.IntakeSession(self.tmp, project_id="p1", known_context={"project_goal": {"deliverable_type": "cinematic-funnel"}})
        q = s.next_question()
        s.answer(q["id"], True)
        kc_path = self.tmp / "intake" / "known-context.json"
        self.assertTrue(kc_path.exists())
        data = json.loads(kc_path.read_text())
        self.assertEqual(len(data["confirmations"]), 1)
        self.assertTrue(data["confirmations"][0]["confirmed"])


class TestTruthSourceCapture(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cwfe-intake-ut-ts-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.s = ie.IntakeSession(self.tmp, project_id="p1", known_context=None)
        answers = sample_answers()
        while True:
            q = self.s.next_question()
            if q["id"] == "offer.proof":
                break
            self.s.answer(q["id"], answers.get(q["id"]))

    def test_answering_claims_spawns_one_follow_up_per_claim(self):
        self.s.answer("offer.proof", ["claim A", "claim B", "claim C"])
        ids = []
        for _ in range(3):
            q = self.s.next_question()
            self.assertEqual(q["kind"], "truth_source")
            ids.append(q["claim_id"])
            self.s.answer(q["id"], {"source_type": "url", "reference": "https://example.test", "provided_by": "client"})
        self.assertEqual(ids, ["offer.proof#0", "offer.proof#1", "offer.proof#2"])

    def test_claim_ids_are_deterministic_not_caller_supplied(self):
        self.s.answer("offer.proof", [{"claim_text": "claim A", "claim_id": "whatever-i-want"}])
        q = self.s.next_question()
        self.assertEqual(q["claim_id"], "offer.proof#0")

    def test_invalid_truth_source_type_rejected(self):
        self.s.answer("offer.proof", ["claim A"])
        q = self.s.next_question()
        with self.assertRaises(ie.InvalidAnswerError):
            self.s.answer(q["id"], {"source_type": "not-a-real-type", "reference": "x", "provided_by": "y"})

    def test_lock_refused_while_truth_source_outstanding(self):
        self.s.answer("offer.proof", ["claim A"])
        # deliberately do NOT answer the truth-source follow-up
        with self.assertRaises(ie.IncompleteIntakeError) as ctx:
            self.s.lock_brief(locked_by="tester")
        self.assertTrue(any("truthsource::" in m for m in ctx.exception.missing))


class TestBriefLockDeterminism(unittest.TestCase):
    def setUp(self):
        self.tmp_a = Path(tempfile.mkdtemp(prefix="cwfe-intake-ut-det-a-"))
        self.tmp_b = Path(tempfile.mkdtemp(prefix="cwfe-intake-ut-det-b-"))
        self.addCleanup(shutil.rmtree, self.tmp_a, ignore_errors=True)
        self.addCleanup(shutil.rmtree, self.tmp_b, ignore_errors=True)

    def test_same_answers_same_project_id_same_hash(self):
        answers = sample_answers()
        b1 = ie.run_scripted_intake(self.tmp_a, project_id="proj-x", known_context=None, answer_map=answers)
        b2 = ie.run_scripted_intake(self.tmp_b, project_id="proj-x", known_context=None, answer_map=answers)
        self.assertEqual(b1["brief_hash"], b2["brief_hash"])
        self.assertEqual(
            json.dumps(b1["groups"], sort_keys=True),
            json.dumps(b2["groups"], sort_keys=True),
        )
        # locked_by/timestamps are metadata, not inputs to brief_hash — they
        # are allowed to coincide (same-second runs) or differ; only the
        # hash and groups payload are asserted above.

    def test_different_project_id_same_answers_same_hash(self):
        # brief_hash is computed over groups + truth_source_ids ONLY, so it
        # is stable even when project_id differs — the id is metadata, not
        # part of what "the same answers" means.
        answers = sample_answers()
        b1 = ie.run_scripted_intake(self.tmp_a, project_id="proj-x", known_context=None, answer_map=answers)
        b2 = ie.run_scripted_intake(self.tmp_b, project_id="proj-y", known_context=None, answer_map=answers)
        self.assertEqual(b1["brief_hash"], b2["brief_hash"])

    def test_different_answers_different_hash(self):
        answers = sample_answers()
        changed = dict(answers)
        changed["offer.price"] = "$4,997"
        b1 = ie.run_scripted_intake(self.tmp_a, project_id="proj-x", known_context=None, answer_map=answers)
        b2 = ie.run_scripted_intake(self.tmp_b, project_id="proj-x", known_context=None, answer_map=changed)
        self.assertNotEqual(b1["brief_hash"], b2["brief_hash"])

    def test_claim_text_change_changes_hash_even_with_same_truth_sources(self):
        answers = sample_answers()
        changed = dict(answers)
        changed["offer.proof"] = ["a DIFFERENT claim text", "featured in Fit Business Weekly"]
        b1 = ie.run_scripted_intake(self.tmp_a, project_id="proj-x", known_context=None, answer_map=answers)
        b2 = ie.run_scripted_intake(self.tmp_b, project_id="proj-x", known_context=None, answer_map=changed)
        self.assertNotEqual(b1["brief_hash"], b2["brief_hash"])

    def test_lock_is_refused_a_second_time(self):
        answers = sample_answers()
        ie.run_scripted_intake(self.tmp_a, project_id="proj-x", known_context=None, answer_map=answers)
        with self.assertRaises(ie.IntakeLockedError):
            ie.run_scripted_intake(self.tmp_a, project_id="proj-x", known_context=None, answer_map=answers)

    def test_locked_brief_written_files_are_schema_valid_on_disk(self):
        answers = sample_answers()
        ie.run_scripted_intake(self.tmp_a, project_id="proj-x", known_context=None, answer_map=answers)
        for kind in ("project-brief", "truth-sources", "approval-policy", "budget-authorization", "raw-answers", "known-context"):
            path = self.tmp_a / ie.RUNTIME_ARTIFACT_RELPATHS[kind]
            self.assertTrue(path.exists(), f"{kind} artifact missing on disk")
            data = json.loads(path.read_text())
            ie._validate_runtime(kind, data)  # raises on failure


class TestResume(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cwfe-intake-ut-resume-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_partial_session_resumes_at_the_same_question(self):
        s1 = ie.IntakeSession(self.tmp, project_id="p1", known_context=None)
        answers = sample_answers()
        for _ in range(3):
            q = s1.next_question()
            s1.answer(q["id"], answers[q["id"]])
        next_expected = s1.next_question()["id"]

        s2 = ie.IntakeSession(self.tmp, project_id="p1", known_context=None)
        self.assertEqual(s2.next_question()["id"], next_expected)

    def test_resume_after_lock_reports_locked_and_no_questions(self):
        answers = sample_answers()
        ie.run_scripted_intake(self.tmp, project_id="p1", known_context=None, answer_map=answers)
        s2 = ie.IntakeSession(self.tmp, project_id="p1", known_context=None)
        self.assertTrue(s2._locked)
        self.assertIsNone(s2.next_question())
        with self.assertRaises(ie.IntakeLockedError):
            s2.answer("project_goal.deliverable_type", "cinematic-website")

    def test_resume_mid_truth_sourcing_rebuilds_the_pending_queue(self):
        s1 = ie.IntakeSession(self.tmp, project_id="p1", known_context=None)
        answers = sample_answers()
        while True:
            q = s1.next_question()
            if q["id"] == "offer.proof":
                break
            s1.answer(q["id"], answers.get(q["id"]))
        s1.answer("offer.proof", ["claim one", "claim two"])
        # only source the FIRST claim, then simulate a crash (drop s1)
        first = s1.next_question()
        s1.answer(first["id"], {"source_type": "url", "reference": "https://example.test/1", "provided_by": "client"})
        del s1

        s2 = ie.IntakeSession(self.tmp, project_id="p1", known_context=None)
        nq = s2.next_question()
        self.assertEqual(nq["kind"], "truth_source")
        self.assertEqual(nq["claim_id"], "offer.proof#1")


class TestSelfTest(unittest.TestCase):
    def test_module_self_test_passes(self):
        self.assertEqual(ie.self_test(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
