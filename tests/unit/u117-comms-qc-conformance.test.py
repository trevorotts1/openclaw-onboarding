#!/usr/bin/env python3
"""Unit tests for shared-utils/page_qc.py's U117 (E6-3/G9) comms-artifact QC
+ per-part-governance / audience-prompt conformance invariant.

Locks down the BINARY acceptance items this repo's (ONB) leg owns:
  (a) a comms fixture whose part is written under the WRONG part's blend
      hard-misses the per-part-governance check; a correctly-governed part
      passes
  (b) a comms fixture with the topic un-factored hard-misses the topic-
      considered check
  (c) a comms fixture with no recorded audience decision hard-misses the
      audience-confirmed check; one recording audience_source=standard or
      =specific passes
  (f) a no-judge-key box SKIPs the semantic (blend-used) check honestly (no
      fabricated score) while the three deterministic checks (audience
      recorded, topic slot populated, part->blend match) still run key-free

(d) is the CC-side review->done refusal wiring (blackceo-command-center
U26 QC-contract) — OUT OF SCOPE for this repo leg, same per-repo/offline
split A-U5/U115/U116 already established; NOT built or faked here.
(e) the CI mutation-proof guard lives in
tests/unit/u117-comms-qc-guard.test.sh (mirrors page-qc-gate-guard.test.sh's
established seed-a-regression / restore pattern), not in this file.

Run:
    python3 tests/unit/u117-comms-qc-conformance.test.py
    or: pytest tests/unit/u117-comms-qc-conformance.test.py
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_SHARED_UTILS = _REPO_ROOT / "shared-utils"
assert _SHARED_UTILS.is_dir(), f"shared-utils not found at {_SHARED_UTILS}"
sys.path.insert(0, str(_SHARED_UTILS))

_fab_spec = importlib.util.spec_from_file_location("fab_qc", _SHARED_UTILS / "fab_qc.py")
fab_qc = importlib.util.module_from_spec(_fab_spec)
sys.modules["fab_qc"] = fab_qc
_fab_spec.loader.exec_module(fab_qc)

_pqc_spec = importlib.util.spec_from_file_location("page_qc", _SHARED_UTILS / "page_qc.py")
page_qc = importlib.util.module_from_spec(_pqc_spec)
sys.modules["page_qc"] = page_qc
_pqc_spec.loader.exec_module(page_qc)

ON = {"COMMS_QC_CONFORMANCE": "1"}


def _part_map():
    """A U115 routing/part-persona-map.json fixture: two legitimately
    different parts (sales page vs nurture email), each governed by its
    own blend, each carrying a reason (the A.6 different-blends-allowed
    invariant U115's own validate_part_blend_diversity checks)."""
    return [
        {"part_id": "sales-page", "part_role": "sales", "voice_persona_id": "hormozi-100m-offers",
         "topic_persona_id": "hormozi-100m-offers", "audience_label": "founders",
         "audience_source": "standard", "stage": "1", "reason": "topic-match: offer-led"},
        {"part_id": "nurture-email-1", "part_role": "nurture", "voice_persona_id": "wiebe-copy-hackers",
         "topic_persona_id": "wiebe-copy-hackers", "audience_label": "founders",
         "audience_source": "standard", "stage": "2", "reason": "topic-match: conversion-copy"},
    ]


def _good_judge(_dim, _payload):
    return {"score": 9.0, "reasoning": "voice attributes trace through clearly"}


def _bad_judge(_dim, _payload):
    return {"score": 2.0, "reasoning": "reads generic, no persona voice present"}


def _comms_fixture(**overrides) -> dict:
    base = {
        "part_id": "sales-page",
        "part_persona_map": _part_map(),
        "used_voice_persona_id": "hormozi-100m-offers",
        "topic": "Q3 founder offer relaunch",
        "audience_source": "standard",
        "blend_directive": {"voice_style": {"tone": "urgent", "rhythm": "punchy"}},
        "copy": "Stop leaving money on the table with a weak offer — here is exactly how to fix it.",
    }
    base.update(overrides)
    return base


class TestCommsQcFlagGate(unittest.TestCase):
    def test_flag_off_is_a_true_noop_byte_identical(self):
        r = page_qc.grade_comms_conformance(_comms_fixture(), judge_fn=_good_judge, env={})
        self.assertFalse(r["applicable"])
        self.assertIsNone(r["passed"])
        self.assertEqual(r["checks"], {})
        self.assertTrue(page_qc.validate_comms_schema(r))

    def test_comms_qc_enabled_reads_only_injected_env(self):
        self.assertFalse(page_qc.comms_qc_enabled(env={}))
        self.assertFalse(page_qc.comms_qc_enabled(env={"COMMS_QC_CONFORMANCE": "0"}))
        self.assertTrue(page_qc.comms_qc_enabled(env={"COMMS_QC_CONFORMANCE": "1"}))


class TestPerPartGovernance(unittest.TestCase):
    """BINARY acceptance (a)."""

    def test_correctly_governed_part_passes(self):
        c1 = page_qc.check_part_governance(_comms_fixture())
        self.assertFalse(c1.hard_miss, c1.observed)
        self.assertEqual(c1.score, 10.0)

    def test_wrong_parts_blend_is_hard_miss(self):
        # written under nurture-email-1's persona while declaring part_id=sales-page
        inp = _comms_fixture(used_voice_persona_id="wiebe-copy-hackers")
        c1 = page_qc.check_part_governance(inp)
        self.assertTrue(c1.hard_miss)
        self.assertIn("wrong part's blend", c1.observed)

    def test_full_grade_hard_misses_on_wrong_part_blend(self):
        inp = _comms_fixture(used_voice_persona_id="wiebe-copy-hackers")
        r = page_qc.grade_comms_conformance(inp, judge_fn=_good_judge, env=ON)
        self.assertFalse(r["passed"])
        self.assertIn("C1 Per-part persona governance", r["hard_misses"])
        self.assertTrue(r["checks"]["part_governance"]["hard_miss"])

    def test_full_grade_passes_on_correctly_governed_part(self):
        r = page_qc.grade_comms_conformance(_comms_fixture(), judge_fn=_good_judge, env=ON)
        self.assertTrue(r["passed"], r)
        self.assertNotIn("C1 Per-part persona governance", r["hard_misses"])

    def test_no_per_part_context_is_na_never_blocks(self):
        # a non-multi-part comms artifact (no part_id/part_persona_map) has
        # nothing to violate — N/A, never a hard miss.
        inp = _comms_fixture(part_id="", part_persona_map=[])
        c1 = page_qc.check_part_governance(inp)
        self.assertFalse(c1.hard_miss)
        self.assertEqual(c1.score, 10.0)
        self.assertIn("N/A", c1.observed)

    def test_unknown_part_id_not_in_map_is_hard_miss(self):
        inp = _comms_fixture(part_id="social-post-3")   # not in _part_map()
        c1 = page_qc.check_part_governance(inp)
        self.assertTrue(c1.hard_miss)
        self.assertIn("no entry", c1.observed)


class TestTopicConsidered(unittest.TestCase):
    """BINARY acceptance (b)."""

    def test_topic_populated_passes(self):
        c2 = page_qc.check_topic_considered(_comms_fixture())
        self.assertFalse(c2.hard_miss)
        self.assertEqual(c2.score, 10.0)

    def test_topic_unfactored_is_hard_miss(self):
        inp = _comms_fixture(topic="")
        c2 = page_qc.check_topic_considered(inp)
        self.assertTrue(c2.hard_miss)
        self.assertIn("topic not factored", c2.observed)

    def test_full_grade_hard_misses_on_unfactored_topic(self):
        inp = _comms_fixture(topic="")
        r = page_qc.grade_comms_conformance(inp, judge_fn=_good_judge, env=ON)
        self.assertFalse(r["passed"])
        self.assertIn("C2 Topic considered", r["hard_misses"])

    def test_topic_falls_back_to_bundle_topic_field(self):
        inp = _comms_fixture(topic="")
        inp["bundle"] = {"topic": "Q3 founder offer relaunch", "persona_id": "hormozi-100m-offers"}
        c2 = page_qc.check_topic_considered(inp)
        self.assertFalse(c2.hard_miss)


class TestAudienceConfirmed(unittest.TestCase):
    """BINARY acceptance (c)."""

    def test_standard_audience_source_passes(self):
        c3 = page_qc.check_audience_confirmed(_comms_fixture(audience_source="standard"))
        self.assertFalse(c3.hard_miss)
        self.assertEqual(c3.score, 10.0)

    def test_specific_audience_source_passes(self):
        c3 = page_qc.check_audience_confirmed(_comms_fixture(audience_source="specific"))
        self.assertFalse(c3.hard_miss)
        self.assertEqual(c3.score, 10.0)

    def test_no_audience_decision_recorded_is_hard_miss(self):
        inp = _comms_fixture(audience_source="")
        c3 = page_qc.check_audience_confirmed(inp)
        self.assertTrue(c3.hard_miss)
        self.assertIn("did not fire", c3.observed)

    def test_garbage_audience_source_value_is_hard_miss(self):
        inp = _comms_fixture(audience_source="whatever")
        c3 = page_qc.check_audience_confirmed(inp)
        self.assertTrue(c3.hard_miss)

    def test_full_grade_hard_misses_on_unrecorded_audience(self):
        inp = _comms_fixture(audience_source="")
        r = page_qc.grade_comms_conformance(inp, judge_fn=_good_judge, env=ON)
        self.assertFalse(r["passed"])
        self.assertIn("C3 Audience confirmed", r["hard_misses"])

    def test_full_grade_passes_with_specific_override_recorded(self):
        inp = _comms_fixture(audience_source="specific")
        r = page_qc.grade_comms_conformance(inp, judge_fn=_good_judge, env=ON)
        self.assertTrue(r["passed"], r)


class TestBlendUsedSemanticAndSkip(unittest.TestCase):
    """BINARY acceptance (f): deterministic checks run key-free; the
    semantic blend-used check SKIPs honestly with no judge, never
    fabricating a score, and never blocking the deterministic three."""

    def test_no_judge_key_skips_blend_used_but_deterministic_checks_still_run(self):
        r = page_qc.grade_comms_conformance(_comms_fixture(), judge_fn=None, env=dict(ON))
        self.assertTrue(r["applicable"])
        bu = r["checks"]["blend_used"]
        self.assertFalse(bu["available"])
        self.assertIsNone(bu["score"])
        self.assertIsNone(bu["passed"])
        # the three deterministic checks ran (non-empty dicts, not skipped)
        self.assertFalse(r["checks"]["part_governance"]["hard_miss"])
        self.assertFalse(r["checks"]["topic_considered"]["hard_miss"])
        self.assertFalse(r["checks"]["audience_confirmed"]["hard_miss"])
        # a SKIP never blocks -> overall passes on the deterministic three alone
        self.assertTrue(r["passed"], r)
        self.assertTrue(page_qc.validate_comms_schema(r))

    def test_no_judge_key_still_hard_misses_a_real_deterministic_failure(self):
        # SKIP-never-blocks must not be confused with SKIP-never-fails: a genuine
        # deterministic hard miss (unrecorded audience) still fails the gate even
        # with no judge key present.
        inp = _comms_fixture(audience_source="")
        r = page_qc.grade_comms_conformance(inp, judge_fn=None, env=dict(ON))
        self.assertFalse(r["passed"])
        self.assertIn("C3 Audience confirmed", r["hard_misses"])

    def test_judge_present_high_score_passes_blend_used(self):
        r = page_qc.grade_comms_conformance(_comms_fixture(), judge_fn=_good_judge, env=ON)
        bu = r["checks"]["blend_used"]
        self.assertTrue(bu["available"])
        self.assertGreaterEqual(bu["score"], 8.0)
        self.assertTrue(bu["passed"])
        self.assertTrue(r["passed"], r)

    def test_judge_present_low_score_hard_misses_blend_used(self):
        r = page_qc.grade_comms_conformance(_comms_fixture(), judge_fn=_bad_judge, env=ON)
        bu = r["checks"]["blend_used"]
        self.assertTrue(bu["available"])
        self.assertTrue(bu["hard_miss"])
        self.assertFalse(r["passed"])
        self.assertIn("C4 Blend actually used", r["hard_misses"])

    def test_judge_failure_with_key_present_is_failclosed_hard_miss(self):
        def always_broken(_dim, _payload):
            return {"error": "500 upstream"}
        r = page_qc.grade_comms_conformance(_comms_fixture(), judge_fn=always_broken, env=ON)
        bu = r["checks"]["blend_used"]
        self.assertTrue(bu["available"])
        self.assertTrue(bu["hard_miss"])
        self.assertFalse(r["passed"])

    def test_blend_used_reuses_fab_qc_voice_persona_grounded_as_evidence(self):
        # score_blend_used must call the SAME predicate U19's D4 uses (real
        # mechanism reuse, not a second independent name-match rule).
        captured = {}

        def capturing_judge(_dim, payload):
            captured["name_grounded"] = payload.get("name_grounded_deterministic_signal")
            return {"score": 9.0, "reasoning": "ok"}

        grounded_copy = ("Written in the hormozi voice: stop leaving money on the table with a "
                         "weak offer — here is exactly how to fix it.")
        inp = _comms_fixture(copy=grounded_copy)
        page_qc.grade_comms_conformance(inp, judge_fn=capturing_judge, env=ON)
        expected = fab_qc.voice_persona_grounded(grounded_copy, "hormozi-100m-offers")
        self.assertTrue(expected)  # sanity: the fixture text really does name-ground
        self.assertEqual(captured["name_grounded"], expected)

        # and the negative case: copy carrying no persona-name signal at all.
        captured.clear()
        ungrounded_copy = "A generic message with no persona name anywhere in it."
        inp2 = _comms_fixture(copy=ungrounded_copy)
        page_qc.grade_comms_conformance(inp2, judge_fn=capturing_judge, env=ON)
        self.assertFalse(captured["name_grounded"])


class TestAllFourPassIsRequiredForOverallPass(unittest.TestCase):
    def test_healthy_fully_governed_comms_artifact_passes_all_four(self):
        r = page_qc.grade_comms_conformance(_comms_fixture(), judge_fn=_good_judge, env=ON)
        self.assertTrue(r["passed"], r)
        self.assertEqual(r["hard_misses"], [])
        self.assertTrue(page_qc.validate_comms_schema(r))

    def test_single_failing_check_among_four_fails_overall(self):
        # only audience is broken; the other three are healthy -> overall FAILS.
        inp = _comms_fixture(audience_source="")
        r = page_qc.grade_comms_conformance(inp, judge_fn=_good_judge, env=ON)
        self.assertFalse(r["passed"])
        self.assertEqual(r["hard_misses"], ["C3 Audience confirmed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
