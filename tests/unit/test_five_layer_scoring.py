#!/usr/bin/env python3
"""D17 five-layer scoring tests (JEV spec 1.1, ss 8.5/8.6, gated by 8.2 + D16).

Proves, against the REAL evaluators/five_layer.py implementation (no
reimplemented logic):
  * per-layer inputs use caller-supplied actual task-part rubrics (descriptive
    N-levels normalized level / (N - 1) via the REAL D03 policies module —
    never 0-10 floats, never silent 0/0.6);
  * default weights are READ from shared-utils/adaptive_weights.py
    (DEFAULT_WEIGHTS with no task text; category-aware adaptive policy with
    one — e.g. email-outreach leans task_fit 0.40); caller overrides win;
  * weights renormalize over legitimately N/A layers only (no-department
    work forces dept_kpis N/A; a fabricated applicable dept score raises);
  * blend-not-applicable paths (D16 mechanical/answer) skip voice/audience
    layers only with D16 mode + reason_code provenance (D16 decided FIRST;
    a caller-supplied applicability is never re-decided);
  * per-layer judgments {question_id, chosen_level, evidence_refs} satisfy
    the REAL D02 validate_envelope contract (round-trip test);
  * uncertainty: per-layer confidence + distribution spread stored apart
    from the aggregate; aggregate confidence is the weakest applicable
    layer (never above it);
  * batch scores N candidates independently and ranks aggregate desc with
    deterministic candidate-id-asc tie-breaks;
  * malformed results fail closed as (ok=False, errors), never raise.

Run: pytest tests/unit/test_five_layer_scoring.py -q
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


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


fl = _load("d17_five_layer_under_test", _DE / "evaluators" / "five_layer.py")
de = _load("d17_contracts_schema", _DE / "contracts" / "schema.py")
pol = _load("d17_policies_loader", _DE / "policies" / "__init__.py")
ep = _load("d17_evidence_profiles", _DE / "personas" / "evidence_profiles.py")
aw = _load("d17_adaptive_weights_direct", _SHARED / "adaptive_weights.py")

_FIX = _DE / "contracts" / "fixtures"


def _layers(**over):
    base = {
        "mission": {"level": 3, "levels": 5, "evidence_refs": ["ev:mission:1.4"],
                    "confidence": "high"},
        "owner_values": {"level": 2, "levels": 4, "evidence_refs": ["ev:values:2.1"],
                         "confidence": "medium"},
        "company_kpis": {"level": 1, "levels": 3, "evidence_refs": ["ev:kpi:3.2"],
                         "confidence": "medium"},
        "dept_kpis": {"level": 2, "levels": 3, "evidence_refs": ["ev:dept:4.1"],
                      "confidence": "low"},
        "task_fit": {"level": 4, "levels": 5, "evidence_refs": ["ev:task:actual"],
                     "confidence": "high"},
    }
    for k, v in over.items():
        base[k] = v
    return base


class FiveLayerWeights(unittest.TestCase):
    def test_default_weights_read_adaptive_module(self):
        self.assertEqual(fl.default_weights(), aw.DEFAULT_WEIGHTS)
        # Documented defaults preserved: 20/25/20/20/15 sums to 1.0.
        self.assertEqual(
            fl.default_weights(),
            {"mission": 0.20, "owner_values": 0.25, "company_kpis": 0.20,
             "dept_kpis": 0.20, "task_fit": 0.15})

    def test_default_weights_adaptive_policy_for_task(self):
        got = fl.default_weights("write a follow-up email")
        self.assertEqual(got, aw.get_weights_for_task("write a follow-up email"))
        # Category-aware policy leans task_fit for execution work.
        self.assertGreaterEqual(got["task_fit"], 0.35)

    def test_caller_weight_override_wins(self):
        w = {"mission": 0.4, "owner_values": 0.25, "company_kpis": 0.2,
             "dept_kpis": 0.05, "task_fit": 0.1}
        r = fl.score_candidate("c1", _layers(), weights=w, department_id="sales")
        self.assertEqual(r["weights_source"], "caller-override")
        self.assertAlmostEqual(sum(v for k, v in r["weights"].items()
                                   if k != "dept_kpis") + r["weights"]["dept_kpis"], 1.0)

    def test_bad_weights_rejected_loudly(self):
        with self.assertRaises(ValueError):
            fl.score_candidate("c1", _layers(), department_id="sales",
                               weights={"mission": 1.0})
        with self.assertRaises(ValueError):
            fl.score_candidate("c1", _layers(), department_id="sales",
                               weights={k: 0.0 for k in fl.LAYERS})


class FiveLayerActualTaskPart(unittest.TestCase):
    def test_task_fit_is_actual_levels_not_0_10(self):
        r = fl.score_candidate("c1", _layers(), department_id="sales")
        self.assertEqual(r["distribution"]["task_fit"], 4 / 4)  # level/(N-1)
        self.assertEqual(r["distribution"]["mission"], 3 / 4)
        self.assertEqual(r["distribution"]["owner_values"], 2 / 3)

    def test_real_d03_normalize_used(self):
        self.assertEqual(pol.normalize_score(4, 5), 1.0)
        self.assertAlmostEqual(pol.normalize_score(2, 4), 2 / 3)

    def test_10_level_without_descriptions_rejected(self):
        bad = _layers(task_fit={"level": 7, "levels": 10,
                                "evidence_refs": ["ev:x"], "confidence": "high"})
        with self.assertRaises(ValueError):
            fl.score_candidate("c1", bad, department_id="sales")

    def test_silent_defaults_rejected(self):
        bad = _layers(mission={"evidence_refs": ["ev:x"], "confidence": "high"})
        with self.assertRaises(ValueError):
            fl.score_candidate("c1", bad, department_id="sales")
        with self.assertRaises(ValueError):
            fl.score_candidate("c1", "not-a-dict", department_id="sales")

    def test_missing_mission_marked_unknown_not_neutral(self):
        layers = _layers(mission={"not_applicable": True,
                                  "reason": "no mission statement on file — unknown, not neutral"})
        r = fl.score_candidate("c1", layers, department_id="sales")
        self.assertIn("mission", r["na_layers"])
        self.assertNotIn("mission", r["distribution"])


class FiveLayerRenormalize(unittest.TestCase):
    def test_no_department_forces_dept_na(self):
        layers = _layers(dept_kpis={"not_applicable": True,
                                    "reason": "spec 8.5: no department selected"})
        r = fl.score_candidate("c1", layers, department_id=None)
        self.assertIn("dept_kpis", r["na_layers"])
        self.assertEqual(r["weights"]["dept_kpis"], 0.0)
        self.assertAlmostEqual(sum(r["weights"].values()), 1.0)

    def test_fabricated_dept_score_without_department_raises(self):
        with self.assertRaises(ValueError):
            fl.score_candidate("c1", _layers(), department_id=None)

    def test_renormalize_matches_configured_weights(self):
        layers = _layers(dept_kpis={"not_applicable": True, "reason": "no dept"})
        w = {"mission": 0.2, "owner_values": 0.25, "company_kpis": 0.2,
             "dept_kpis": 0.2, "task_fit": 0.15}
        r = fl.score_candidate("c1", layers, weights=w, department_id=None)
        total = 0.2 + 0.25 + 0.2 + 0.15
        self.assertAlmostEqual(r["weights"]["mission"], 0.2 / total)
        self.assertAlmostEqual(r["weights"]["task_fit"], 0.15 / total)
        exp = (0.75 * 0.2 + (2 / 3) * 0.25 + 0.5 * 0.2 + 1.0 * 0.15) / total
        self.assertAlmostEqual(r["aggregate"], exp)

    def test_all_na_raises(self):
        layers = {k: {"not_applicable": True, "reason": f"no {k} evidence"}
                  for k in fl.LAYERS}
        with self.assertRaises(ValueError):
            fl.score_candidate("c1", layers, department_id=None)


class FiveLayerBlendGate(unittest.TestCase):
    def test_d16_decided_first_for_mechanical(self):
        layers = _layers(
            dept_kpis={"not_applicable": True, "reason": "ops task, no dept"})
        r = fl.score_candidate("c1", layers, department_id=None,
                               message="Repair the podcast file path")
        self.assertEqual(r["provenance"]["applicability_mode"], "mechanical")
        self.assertEqual(r["provenance"]["applicability_decided_by"], "d16")
        self.assertFalse(r["provenance"]["blend_applicable"])

    def test_answer_path_provenance(self):
        layers = _layers(
            dept_kpis={"not_applicable": True, "reason": "chat answer, no dept"})
        r = fl.score_candidate("c1", layers, department_id=None,
                               message="Explain the options. Do not build anything yet.")
        self.assertEqual(r["provenance"]["applicability_mode"], "answer")
        self.assertFalse(r["provenance"]["blend_applicable"])

    def test_caller_applicability_never_redecided(self):
        supplied = {"mode": "blend", "audience_facing": True,
                    "task_persona_needed": True, "answer_only": False,
                    "mechanical_only": False, "reason_code": "caller-says-blend",
                    "note": "caller decided"}
        layers = _layers(
            dept_kpis={"not_applicable": True, "reason": "caller context"})
        r = fl.score_candidate("c1", layers, department_id=None,
                               applicability=supplied,
                               message="Repair the podcast file path")
        self.assertEqual(r["provenance"]["applicability_mode"], "blend")
        self.assertEqual(r["provenance"]["applicability_decided_by"], "caller")
        self.assertTrue(r["provenance"]["blend_applicable"])

    def test_blend_modes_carry_audience_layers(self):
        r = fl.score_candidate("c1", _layers(), department_id="sales",
                               message="Write the sales email")
        self.assertEqual(r["provenance"]["applicability_mode"], "blend")
        self.assertTrue(r["provenance"]["blend_applicable"])
        self.assertEqual(len(r["judgments"]), 5)


class FiveLayerJudgments(unittest.TestCase):
    def test_judgment_shape_per_layer(self):
        r = fl.score_candidate("c1", _layers(), department_id="sales")
        by_q = {j["question_id"]: j for j in r["judgments"]}
        self.assertEqual(len(r["judgments"]), 5)
        for j in r["judgments"]:
            self.assertIsInstance(j["question_id"], str)
            self.assertTrue(j["question_id"].strip())
            self.assertIn("chosen_level", j)
            self.assertIn("evidence_refs", j)

    def test_judgments_round_trip_through_d02_envelope(self):
        r = fl.score_candidate("c1", _layers(), department_id="sales")
        env = json.loads((_FIX / "envelope_committed.json").read_text(encoding="utf-8"))
        env = copy.deepcopy(env)
        env["judgments"] = [
            {"question_id": j["question_id"], "answer": "level-%s" % j["chosen_level"],
             "confidence": 0.7}
            for j in r["judgments"] if j["status"] == "scored"
        ]
        ok, errs = de.validate_envelope(env)
        self.assertTrue(ok, errs)


class FiveLayerUncertainty(unittest.TestCase):
    def test_aggregate_confidence_never_exceeds_weakest(self):
        r = fl.score_candidate("c1", _layers(), department_id="sales")
        order = {"none": 0, "low": 1, "medium": 2, "high": 3}
        weakest = min(order[v] for v in r["per_layer_confidence"].values())
        self.assertEqual(r["confidence_ordinal"], weakest)
        self.assertEqual(order[r["confidence"]], weakest)
        # dept is low here; aggregate must be low even with high task_fit.
        self.assertEqual(r["confidence"], "low")

    def test_spread_stored_separate_from_aggregate(self):
        r = fl.score_candidate("c1", _layers(), department_id="sales")
        vals = list(r["distribution"].values())
        self.assertAlmostEqual(r["spread"], max(vals) - min(vals))
        self.assertNotEqual(r["spread"], r["aggregate"])

    def test_single_level_spread_zero(self):
        same = {k: {"level": 1, "levels": 2, "evidence_refs": ["ev:%s" % k],
                    "confidence": "medium"} for k in fl.LAYERS}
        r = fl.score_candidate("c1", same, department_id="sales")
        self.assertEqual(r["spread"], 0.0)
        self.assertEqual(r["confidence"], "medium")


class FiveLayerBatch(unittest.TestCase):
    def _cand(self, cid, level, levels=5):
        layers = {k: {"level": 2, "levels": 4, "evidence_refs": ["ev:%s:%s" % (cid, k)],
                      "confidence": "medium"} for k in fl.LAYERS}
        layers["task_fit"] = {"level": level, "levels": levels,
                              "evidence_refs": ["ev:%s:task" % cid],
                              "confidence": "medium"}
        return {"candidate_id": cid, "layers": layers}

    def test_ranked_aggregate_desc(self):
        out = fl.score_batch([self._cand("zeta", 0), self._cand("alpha", 3)],
                             department_id="sales")
        self.assertEqual([r["candidate_id"] for r in out], ["alpha", "zeta"])
        self.assertGreater(out[0]["aggregate"], out[1]["aggregate"])

    def test_ties_broken_by_candidate_id(self):
        out = fl.score_batch([self._cand("zeta", 2, 4), self._cand("alpha", 2, 4)],
                             department_id="sales")
        self.assertEqual([r["candidate_id"] for r in out], ["alpha", "zeta"])
        self.assertEqual(out[0]["aggregate"], out[1]["aggregate"])

    def test_candidates_independent(self):
        one = fl.score_candidate("solo", self._cand("solo", 3)["layers"],
                                 department_id="sales")
        out = fl.score_batch([self._cand("solo", 3), self._cand("other", 0)],
                             department_id="sales")
        solo = next(r for r in out if r["candidate_id"] == "solo")
        self.assertEqual(solo["aggregate"], one["aggregate"])

    def test_bad_batch_rejected(self):
        with self.assertRaises(ValueError):
            fl.score_batch([], department_id="sales")
        with self.assertRaises(ValueError):
            fl.score_batch([self._cand("dup", 1), self._cand("dup", 2)],
                           department_id="sales")


class FiveLayerResultContract(unittest.TestCase):
    def test_valid_result_passes(self):
        r = fl.score_candidate("c1", _layers(), department_id="sales")
        ok, errs = fl.validate_result(r)
        self.assertTrue(ok, errs)

    def test_malformed_result_fails_closed(self):
        ok, _ = fl.validate_result({"nope": True})
        self.assertFalse(ok)
        ok, _ = fl.validate_result(None)
        self.assertFalse(ok)
        # Validator never raises on garbage.
        ok, errs = fl.validate_result({"candidate_id": "", "aggregate": float("nan"),
                                       "distribution": {}, "confidence": "maybe",
                                       "judgments": [], "weights": {},
                                       "provenance": {}})
        self.assertFalse(ok)
        self.assertTrue(errs)


class FiveLayerScorerFacade(unittest.TestCase):
    def test_class_scores_and_batches_like_functions(self):
        s = fl.FiveLayerScorer()
        layers = _layers()
        r1 = s.score("c1", layers, department_id="sales")
        r2 = fl.score_candidate("c1", layers, department_id="sales")
        self.assertEqual(r1["aggregate"], r2["aggregate"])
        out = s.batch([{"candidate_id": "c1", "layers": layers}],
                      department_id="sales")
        self.assertEqual(out[0]["candidate_id"], "c1")
        ok, errs = fl.FiveLayerScorer.validate(out[0])
        self.assertTrue(ok, errs)


if __name__ == "__main__":
    unittest.main()
