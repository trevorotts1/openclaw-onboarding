#!/usr/bin/env python3
"""D16 evidence-profile tests (JEV spec 1.1, ss 8.1/8.2/8.3 + 10.2).

Proves, against the REAL evidence_profiles implementation:
  * five responsibilities stay separate (never a merged pool);
  * audience priority explicit > prior-confirmed > company-proposal > clarify,
    prior valid only same-scope + unchanged data;
  * confidence is not consent (high-confidence guess still confirms);
  * 8.2 keyword triggers (write/script/post/video) never force a voice;
  * required 8.2 examples route correctly (sales email, python script,
    podcast path, chat explanation, mixed chmod);
  * task-persona rows match D02 contracts/schema.py rules (seq/governance,
    up-to-10 cap) via the real D02 validator;
  * answer intents never fill task-persona slots;
  * voice never chosen from demographic stereotypes alone.

Run: pytest tests/unit/test_evidence_profiles.py
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_SHARED = _REPO_ROOT / "shared-utils"
_DE = _SHARED / "decision_engine"
sys.path.insert(0, str(_SHARED))

_spec = importlib.util.spec_from_file_location(
    "decision_engine_personas_evidence", _DE / "personas" / "evidence_profiles.py")
ep = importlib.util.module_from_spec(_spec)
sys.modules["decision_engine_personas_evidence"] = ep
_spec.loader.exec_module(ep)

_dspec = importlib.util.spec_from_file_location(
    "decision_engine_contracts_schema", _DE / "contracts" / "schema.py")
de = importlib.util.module_from_spec(_dspec)
sys.modules["decision_engine_contracts_schema"] = de
_dspec.loader.exec_module(de)

_FIX = _DE / "contracts" / "fixtures"


def _bundle_with_rows(rows):
    bundle = json.loads((_FIX / "envelope_committed.json").read_text(encoding="utf-8"))["personaBundle"]
    bundle = copy.deepcopy(bundle)
    bundle["task_personas"] = rows
    return bundle


def _full_set(**over):
    kw = {
        "audience": ("explicit", ["explicit:owners"]),
        "voice": ("explicit", ["voice:catalog:1.4"]),
        "topic": ("explicit", ["topic:catalog:1.4"]),
        "task_part": ("explicit", ["sop:slots"]),
        "outcome": ("explicit", ["goal:operator_confirmed"]),
    }
    kw.update(over)
    return [
        ep.make_profile(r, res, evidence_refs=refs, confidence="high",
                        scope_id="scope-main")
        for r, (res, refs) in kw.items()
    ]


class ResponsibilitySeparation(unittest.TestCase):
    def test_five_responsibilities(self):
        self.assertEqual(
            tuple(ep.RESPONSIBILITIES),
            ("audience", "voice", "topic", "task_part", "outcome"))

    def test_evidence_set_needs_all_five(self):
        ok, mapping, errs = ep.build_evidence_set(_full_set())
        self.assertTrue(ok, errs)
        self.assertEqual(set(mapping), set(ep.RESPONSIBILITIES))

    def test_shared_object_rejected_as_merged_pool(self):
        one = ep.make_profile("audience", "explicit", evidence_refs=["explicit:x"])
        ok, _, errs = ep.build_evidence_set([one] * 5)
        self.assertFalse(ok)
        self.assertTrue(any("merged pool" in e for e in errs), errs)

    def test_duplicate_responsibility_rejected(self):
        profiles = _full_set()
        profiles[1] = ep.make_profile("audience", "explicit", evidence_refs=["explicit:y"])
        ok, _, errs = ep.build_evidence_set(profiles)
        self.assertFalse(ok)

    def test_wrong_count_rejected(self):
        ok, _, errs = ep.build_evidence_set(_full_set()[:3])
        self.assertFalse(ok)
        self.assertTrue(any("exactly 5" in e for e in errs), errs)

    def test_make_profile_rejects_bad_enums(self):
        with self.assertRaises(ValueError):
            ep.make_profile("blended", "explicit", evidence_refs=["x"])
        with self.assertRaises(ValueError):
            ep.make_profile("voice", "guessed", evidence_refs=["x"])
        with self.assertRaises(ValueError):
            ep.make_profile("voice", "explicit", evidence_refs=["x"], confidence="sure")

    def test_validator_never_raises_on_garbage(self):
        for bad in (None, "x", 42, [], object()):
            ok, errs = ep.validate_profile(bad)
            self.assertFalse(ok)
            self.assertTrue(errs)


class AudienceResolution(unittest.TestCase):
    def test_explicit_wins(self):
        p = ep.resolve_audience(explicit="new-business-owners",
                                prior={"label": "old", "scope_match": True, "data_unchanged": True},
                                company="house-list", scope_id="scope-main")
        self.assertEqual(p.resolution, "explicit")
        self.assertFalse(p.confirm_required)
        ok, _ = ep.validate_profile(p)
        self.assertTrue(ok)

    def test_prior_only_same_scope_unchanged(self):
        good = ep.resolve_audience(
            prior={"label": "owners", "scope_match": True, "data_unchanged": True})
        self.assertEqual(good.resolution, "prior_confirmed")
        self.assertFalse(good.confirm_required)
        stale = ep.resolve_audience(
            prior={"label": "owners", "scope_match": True, "data_unchanged": False},
            company="house-list")
        self.assertEqual(stale.resolution, "company_proposal")
        self.assertTrue(stale.confirm_required)
        moved = ep.resolve_audience(
            prior={"label": "owners", "scope_match": False, "data_unchanged": True},
            company="house-list")
        self.assertEqual(moved.resolution, "company_proposal")

    def test_company_is_proposal_needing_confirmation(self):
        p = ep.resolve_audience(company="house-list")
        self.assertEqual(p.resolution, "company_proposal")
        self.assertTrue(p.confirm_required)

    def test_missing_means_single_clarification(self):
        p = ep.resolve_audience()
        self.assertEqual(p.resolution, "needs_clarification")
        self.assertTrue(p.confirm_required)
        ok, _ = ep.validate_profile(p)
        self.assertTrue(ok)

    def test_confidence_is_not_consent(self):
        p = ep.resolve_audience(company="house-list", confidence="high")
        self.assertEqual(p.confidence, "high")
        self.assertTrue(p.confirm_required)
        q = ep.resolve_audience(confidence="high")
        self.assertEqual(q.resolution, "needs_clarification")
        self.assertTrue(q.confirm_required)


class BlendApplicability(unittest.TestCase):
    def test_sales_email_blends(self):
        r = ep.assess_blend_applicability(
            "Write a sales email to new owners", artifact_intent="sales")
        self.assertEqual(r["mode"], "blend")
        self.assertTrue(r["audience_facing"] and r["task_persona_needed"])

    def test_python_script_is_not_copy(self):
        r = ep.assess_blend_applicability(
            "Write a Python script that parses CSV", artifact_intent="code")
        self.assertEqual(r["mode"], "task_only")
        self.assertFalse(r["audience_facing"])

    def test_podcast_path_is_operational(self):
        r = ep.assess_blend_applicability(
            "Repair the podcast file path", artifact_intent="operational")
        self.assertTrue(r["mechanical_only"])
        self.assertFalse(r["audience_facing"])

    def test_chat_explanation_is_answer(self):
        r = ep.assess_blend_applicability(
            "Explain a marketing concept in chat", task_type="answer_only")
        self.assertTrue(r["answer_only"])
        self.assertFalse(r["task_persona_needed"])

    def test_mixed_chmod_keeps_blend(self):
        r = ep.assess_blend_applicability(
            "Write the launch post and chmod the asset dir", artifact_intent="content")
        self.assertEqual(r["mode"], "mixed")
        self.assertTrue(r["audience_facing"] and r["task_persona_needed"])

    def test_bare_keywords_never_force_voice(self):
        for msg in ("write", "script", "post", "video", "write that up"):
            r = ep.assess_blend_applicability(msg)
            self.assertFalse(r["audience_facing"], msg)
            self.assertFalse(r["task_persona_needed"], msg)


class TaskPersonaRows(unittest.TestCase):
    def _parts(self, n, governance=False):
        parts = []
        for i in range(n):
            row = {"part": f"part-{i + 1}", "why": "slot",
                   "task_category": "marketing-email"}
            if governance:
                row["no_persona_required"] = True
            else:
                row["persona_id"] = f"persona-{i + 1}"
            parts.append(row)
        return parts

    def test_rows_validate_against_real_d02(self):
        ok, rows, errs = ep.build_task_persona_rows(self._parts(2))
        self.assertTrue(ok, errs)
        ok_b, errs_b = de.validate_persona_bundle(_bundle_with_rows(rows), company_id="fixture-co")
        self.assertTrue(ok_b, errs_b)

    def test_governance_rows_validate_against_real_d02(self):
        ok, rows, errs = ep.build_task_persona_rows(self._parts(2, governance=True))
        self.assertTrue(ok, errs)
        self.assertTrue(all(r["persona_id"] is None for r in rows))
        ok_b, errs_b = de.validate_persona_bundle(_bundle_with_rows(rows), company_id="fixture-co")
        self.assertTrue(ok_b, errs_b)

    def test_seq_unique_auto_assigned(self):
        ok, rows, _ = ep.build_task_persona_rows(self._parts(3))
        self.assertTrue(ok)
        self.assertEqual([r["seq"] for r in rows], [1, 2, 3])

    def test_cap_enforced_at_ten(self):
        ok, rows, _ = ep.build_task_persona_rows(self._parts(10))
        self.assertTrue(ok)
        self.assertEqual(len(rows), 10)
        ok_b, _ = de.validate_persona_bundle(_bundle_with_rows(rows), company_id="fixture-co")
        self.assertTrue(ok_b)
        ok11, _, errs = ep.build_task_persona_rows(self._parts(11))
        self.assertFalse(ok11)
        self.assertTrue(any("10" in e for e in errs), errs)

    def test_answer_never_fills_slots(self):
        ok, _, errs = ep.build_task_persona_rows(
            self._parts(1), intent="answer_only")
        self.assertFalse(ok)
        self.assertTrue(any("answer" in e for e in errs), errs)
        ok2, rows2, _ = ep.build_task_persona_rows([], intent="answer_only")
        self.assertTrue(ok2)
        self.assertEqual(rows2, [])

    def test_governance_with_persona_id_rejected(self):
        parts = [{"part": "p", "persona_id": "x", "no_persona_required": True}]
        ok, _, errs = ep.build_task_persona_rows(parts)
        self.assertFalse(ok)
        self.assertTrue(errs)

    def test_builder_never_raises(self):
        ok, rows, errs = ep.build_task_persona_rows("not-a-list")
        self.assertFalse(ok)
        self.assertEqual(rows, [])
        self.assertTrue(errs)


class VoiceBasis(unittest.TestCase):
    def test_demographic_alone_insufficient(self):
        self.assertFalse(ep.voice_basis_ok(demographic_tags=["women-25-34"]))
        self.assertFalse(ep.voice_basis_ok(
            demographic_tags=["women-25-34"], suitability_evidence=[""]))
        self.assertTrue(ep.voice_basis_ok(
            demographic_tags=["women-25-34"],
            suitability_evidence=["catalog:voice usable_as=audience"]))
        self.assertTrue(ep.voice_basis_ok(suitability_evidence=["brand-preference"]))
        self.assertFalse(ep.voice_basis_ok(demographic_tags="x"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
