#!/usr/bin/env python3
"""D19 collapse-policy tests (JEV spec 1.1, ss 8.8/8.9/8.10; topic-fit 8.6).

Proves, against the REAL personas/collapse_policy.py implementation:
  * collapse needs INDEPENDENT voice-fit AND topic-fit at/above caller-set
    thresholds (topic-strong-but-voice-unchecked never collapses);
  * cheap storage / tag overlap / previous winner never collapse;
  * strong fits + audience kept collapse with scores logged; expertise loss
    keeps separate; reason codes enumerable + logged (8.8);
  * per-part guidance defaults to shared coherent voice, differs only with
    recorded justification; audience change invalidates affected + dependent
    parents only, siblings survive (8.10);
  * decomposition guard accepts exactly one of blend|planner|sop_slot and
    rejects double-runs; slot/hint check detects a missing hint (8.9);
  * D16/D17/D03 types and levels imported, never redefined.

Run: pytest tests/unit/test_collapse_policy.py -q
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_SHARED = _REPO_ROOT / "shared-utils"
_DE = _SHARED / "decision_engine"
sys.path.insert(0, str(_SHARED))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cp = _load("d19_collapse_policy_under_test", _DE / "personas" / "collapse_policy.py")
ep = _load("d19_evidence_check", _DE / "personas" / "evidence_profiles.py")
pol = _load("d19_policies_check", _DE / "policies" / "__init__.py")


def _fit(kind, **over):
    base = {
        "level": 3, "levels": 5,
        "evidence_refs": [f"ev:{kind}:1"],
        "checked": True,
    }
    base.update(over)
    return base


def _good_request(**over):
    kw = {
        "voice": _fit("voice"),
        "topic": _fit("topic"),
        "thresholds": {"voice_min": 0.5, "topic_min": 0.5},
        "audience_kept": True,
        "expertise_loss": False,
        "basis": "voice_topic_fit",
    }
    kw.update(over)
    return kw


class RealModules(unittest.TestCase):
    def test_types_and_levels_imported_not_redefined(self):
        self.assertEqual(cp.CONFIDENCE_LEVELS, ep.CONFIDENCE_LEVELS)
        self.assertEqual(cp.RESPONSIBILITIES, ep.RESPONSIBILITIES)
        self.assertEqual(cp.normalize_score(3, 5), pol.normalize_score(3, 5))
        self.assertTrue(callable(cp.aggregate_fit))

    def test_level_score_uses_d03_normalize(self):
        req = _good_request(
            voice=_fit("voice", level=3, levels=5),
            topic=_fit("topic", level=2, levels=4),
        )
        out = cp.decide_collapse(**req)
        self.assertAlmostEqual(out["voice_score"], pol.normalize_score(3, 5))
        self.assertAlmostEqual(out["topic_score"], pol.normalize_score(2, 4))


class CollapseDecisions(unittest.TestCase):
    def test_strong_fits_audience_kept_collapse_scores_logged(self):
        out = cp.decide_collapse(**_good_request())
        self.assertEqual(out["decision"], "collapse")
        self.assertEqual(out["reason_code"], "voice-and-topic-fit")
        self.assertGreaterEqual(out["voice_score"], 0.5)
        self.assertGreaterEqual(out["topic_score"], 0.5)
        log = out["log"]
        self.assertEqual(log["decision"], "collapse")
        self.assertEqual(log["reason_code"], "voice-and-topic-fit")
        self.assertIn("voice_score", log)
        self.assertIn("topic_score", log)
        self.assertIn("thresholds", log)

    def test_topic_strong_voice_unchecked_never_collapses(self):
        out = cp.decide_collapse(**_good_request(
            voice=_fit("voice", level=4, levels=5, checked=False),
            topic=_fit("topic", level=4, levels=5, checked=True),
        ))
        self.assertEqual(out["decision"], "keep_separate")
        self.assertEqual(out["reason_code"], "voice-unchecked")

    def test_topic_unchecked_never_collapses(self):
        out = cp.decide_collapse(**_good_request(
            topic=_fit("topic", checked=False),
        ))
        self.assertEqual(out["decision"], "keep_separate")
        self.assertEqual(out["reason_code"], "topic-unchecked")

    def test_tag_overlap_only_never_collapses(self):
        out = cp.decide_collapse(**_good_request(basis="tag_overlap"))
        self.assertEqual(out["decision"], "keep_separate")
        self.assertEqual(out["reason_code"], "tag-overlap-only")

    def test_cheap_storage_only_never_collapses(self):
        out = cp.decide_collapse(**_good_request(basis="cheap_storage"))
        self.assertEqual(out["decision"], "keep_separate")
        self.assertEqual(out["reason_code"], "cheap-storage-only")

    def test_previous_winner_only_never_collapses(self):
        out = cp.decide_collapse(**_good_request(basis="previous_winner"))
        self.assertEqual(out["decision"], "keep_separate")
        self.assertEqual(out["reason_code"], "previous-winner-only")

    def test_expertise_loss_keeps_separate(self):
        out = cp.decide_collapse(**_good_request(expertise_loss=True))
        self.assertEqual(out["decision"], "keep_separate")
        self.assertEqual(out["reason_code"], "expertise-loss")

    def test_audience_changed_keeps_separate(self):
        out = cp.decide_collapse(**_good_request(audience_kept=False))
        self.assertEqual(out["decision"], "keep_separate")
        self.assertEqual(out["reason_code"], "audience-changed")

    def test_below_threshold_keeps_separate(self):
        out = cp.decide_collapse(**_good_request(
            thresholds={"voice_min": 0.95, "topic_min": 0.95},
        ))
        self.assertEqual(out["decision"], "keep_separate")
        self.assertEqual(out["reason_code"], "below-threshold")

    def test_thresholds_are_caller_set(self):
        req = _good_request()
        del req["thresholds"]
        with self.assertRaises(ValueError):
            cp.decide_collapse(**req)
        with self.assertRaises(ValueError):
            cp.decide_collapse(**_good_request(thresholds={"voice_min": 0.5}))

    def test_reason_codes_enumerable_and_logged(self):
        cases = [
            _good_request(),
            _good_request(voice=_fit("voice", checked=False)),
            _good_request(basis="tag_overlap"),
            _good_request(basis="cheap_storage"),
            _good_request(basis="previous_winner"),
            _good_request(expertise_loss=True),
            _good_request(audience_kept=False),
            _good_request(thresholds={"voice_min": 0.99, "topic_min": 0.99}),
        ]
        for req in cases:
            out = cp.decide_collapse(**req)
            self.assertIn(out["reason_code"], cp.COLLAPSE_REASONS)
            self.assertEqual(out["log"]["reason_code"], out["reason_code"])
            self.assertIn(out["decision"], cp.DECISIONS)

    def test_deterministic(self):
        req = _good_request()
        first = cp.decide_collapse(**req)
        second = cp.decide_collapse(**_good_request())
        self.assertEqual(first, second)

    def test_score_inputs_accepted(self):
        out = cp.decide_collapse(**_good_request(
            voice={"score": 0.8, "evidence_refs": ["ev:voice:1"], "checked": True},
            topic={"score": 0.7, "evidence_refs": ["ev:topic:1"], "checked": True},
        ))
        self.assertEqual(out["decision"], "collapse")

    def test_bad_fit_raises_never_silent(self):
        with self.assertRaises(ValueError):
            cp.decide_collapse(**_good_request(voice={"level": 1}))
        with self.assertRaises(ValueError):
            cp.decide_collapse(**_good_request(
                voice=_fit("voice", evidence_refs=[])))


class PerPartGuidance(unittest.TestCase):
    def _parts(self):
        return [
            {"part_id": "part-a", "topic": "onboarding email",
             "decision_id": "dec-A", "parents": ["parent-P"]},
            {"part_id": "part-b", "topic": "welcome post",
             "decision_id": "dec-B", "parents": []},
        ]

    def test_default_shared_coherent_voice(self):
        out = cp.per_part_guidance(
            self._parts(),
            {"voice": "plainspoken-guide"},
            "founders", "acme-direct",
        )
        self.assertEqual(out["invalidated"], [])
        for row in out["per_part"]:
            self.assertIsNone(row["voice_override"])
            self.assertEqual(row["justification"], "shared-coherent-voice")
        self.assertEqual(out["per_part"][0]["audience"], "founders")
        self.assertEqual(out["per_part"][0]["brand"], "acme-direct")
        self.assertEqual(out["per_part"][0]["topic_guidance"], "onboarding email")

    def test_new_audience_on_part_overrides_with_reason(self):
        parts = self._parts()
        parts[0] = dict(parts[0], audience="enterprise-bankers")
        out = cp.per_part_guidance(
            parts, {"voice": "plainspoken-guide"}, "founders", "acme-direct",
        )
        row = out["per_part"][0]
        self.assertIsNotNone(row["voice_override"])
        self.assertIn("audience-change", row["justification"])
        self.assertIn("enterprise-bankers", row["justification"])
        self.assertEqual(row["voice_override"]["audience"], "enterprise-bankers")
        # unchanged sibling keeps shared voice
        self.assertIsNone(out["per_part"][1]["voice_override"])

    def test_audience_change_invalidates_only_affected_and_parents(self):
        parts = self._parts()
        parts[0] = dict(parts[0], audience="enterprise-bankers")
        out = cp.per_part_guidance(
            parts, {"voice": "plainspoken-guide"}, "founders", "acme-direct",
        )
        self.assertEqual(sorted(out["invalidated"]), ["dec-A", "parent-P"])
        self.assertNotIn("dec-B", out["invalidated"])

    def test_sibling_decisions_survive(self):
        parts = self._parts()
        parts[1] = dict(parts[1], audience="enterprise-bankers")
        out = cp.per_part_guidance(
            parts, {"voice": "plainspoken-guide"}, "founders", "acme-direct",
        )
        self.assertIn("dec-B", out["invalidated"])
        self.assertNotIn("dec-A", out["invalidated"])

    def test_bad_parts_raise(self):
        with self.assertRaises(ValueError):
            cp.per_part_guidance(
                [], {"voice": "v"}, "founders", "acme-direct")
        dup = [dict(self._parts()[0]), dict(self._parts()[0])]
        with self.assertRaises(ValueError):
            cp.per_part_guidance(
                dup, {"voice": "v"}, "founders", "acme-direct")


class DecompositionGuard(unittest.TestCase):
    def test_accepts_each_single_path(self):
        for path in ("blend", "planner", "sop_slot"):
            out = cp.assert_single_decomposition(path)
            self.assertTrue(out["ok"])
            self.assertEqual(out["path"], path)

    def test_rejects_blend_plus_standalone_double_run(self):
        with self.assertRaises(ValueError):
            cp.assert_single_decomposition("blend+standalone")
        with self.assertRaises(ValueError):
            cp.assert_single_decomposition(["blend", "planner"])
        with self.assertRaises(ValueError):
            cp.assert_single_decomposition({"blend": True, "planner": True})

    def test_unknown_path_rejected(self):
        with self.assertRaises(ValueError):
            cp.assert_single_decomposition("double")

    def test_slot_hint_check_detects_missing_hint(self):
        out = cp.check_slot_hint_propagation(
            ["slot-a", "slot-b"], ["slot-a"])
        self.assertFalse(out["ok"])
        self.assertEqual(out["missing"], ["slot-b"])
        self.assertEqual(out["undeclared"], [])

    def test_slot_hint_clean(self):
        out = cp.check_slot_hint_propagation(["slot-a"], ["slot-a"])
        self.assertTrue(out["ok"])
        self.assertEqual(out["missing"], [])
        self.assertEqual(out["errors"], [])

    def test_slot_hint_never_raises(self):
        out = cp.check_slot_hint_propagation("nope", "nope")
        self.assertFalse(out["ok"])
        self.assertTrue(out["errors"])


if __name__ == "__main__":
    unittest.main()
