#!/usr/bin/env python3
"""D08 no-JEV fallback tests (JEV spec 1.1, ss 3.6/4.5/9.8).

Proves, against the REAL fallback/__init__.py implementation (no
reimplemented logic):
  * the spec 9.8 capability-combination catalog routes all four
    combinations to their expected paths;
  * caller-supplied byte-identical ranking: identical inputs give
    identical normalized decisions across differing labels;
  * legacy/off produce equivalent normalized decisions (spec 3.6: same
    improved no-JEV engine, labels differ only);
  * select is assignment-only and read-only: caller data untouched,
    snapshot has no revision fields, zero JEV/probe/shadow counters in
    every mode including legacy/off;
  * every skip reason is honest (jev_unavailable / not_authorized /
    data_not_permitted / budget_exhausted) and surfaces on the result;
  * fallback_model is caller-supplied optional: noted when present,
    pure rule ranking when absent, and never a key requirement;
  * malformed inputs fail: bad input raises, validators return
    (ok=False, errors) and never raise.

Run: python3 -m pytest tests/unit/test_nojev_fallback.py -q (from repo root)
"""

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_FB = _REPO_ROOT / "shared-utils" / "decision_engine" / "fallback"

_spec = importlib.util.spec_from_file_location(
    "decision_engine_nojev_fallback", _FB / "__init__.py"
)
fb = importlib.util.module_from_spec(_spec)
sys.modules["decision_engine_nojev_fallback"] = fb
_spec.loader.exec_module(fb)

CATALOG = [
    {"id": "persona-alpha", "text": "email nurture voice", "topics": ["email"]},
    {"id": "persona-beta", "text": "campaign strategy", "topics": ["campaign"]},
    {"id": "persona-gamma", "text": "sales followup", "topics": ["sales"]},
]


class CapabilityCombinations(unittest.TestCase):
    def test_all_four_combinations_route(self):
        cases = [
            (True, True, fb.PATH_JEV_HYBRID),
            (True, False, fb.PATH_JEV_LEXICAL),
            (False, True, fb.PATH_NOJEV_SEMANTIC),
            (False, False, fb.PATH_NOJEV_CATALOG_RULE),
        ]
        for jev, emb, want in cases:
            self.assertEqual(fb.route_capability(jev, emb), want, f"jev={jev} emb={emb}")

    def test_non_bool_inputs_raise_never_guess(self):
        for bad in (None, 1, "yes", [True]):
            with self.assertRaises(ValueError, msg=f"jev={bad!r}"):
                fb.route_capability(bad, True)
            with self.assertRaises(ValueError, msg=f"emb={bad!r}"):
                fb.route_capability(True, bad)

    def test_path_through_select_matches_catalog(self):
        got = fb.select(
            CATALOG,
            "email nurture",
            jev_available=False,
            embeddings_available=False,
            skip_reason="jev_unavailable",
        )
        self.assertEqual(got["capabilityPath"], fb.PATH_NOJEV_CATALOG_RULE)
        got = fb.select(
            CATALOG,
            "email nurture",
            jev_available=False,
            embeddings_available=True,
            skip_reason="budget_exhausted",
        )
        self.assertEqual(got["capabilityPath"], fb.PATH_NOJEV_SEMANTIC)


class ModesSameEngine(unittest.TestCase):
    def test_legacy_off_byte_identical_normalized(self):
        kw = dict(
            catalog=CATALOG,
            query="email nurture campaign",
            jev_available=False,
            embeddings_available=False,
            skip_reason="jev_unavailable",
        )
        legacy = fb.select(
            CATALOG,
            "email nurture campaign",
            {"configuredMode": "legacy"},
            jev_available=False,
            embeddings_available=False,
            skip_reason="jev_unavailable",
        )
        off = fb.select(
            CATALOG,
            "email nurture campaign",
            {"configuredMode": "off"},
            jev_available=False,
            embeddings_available=False,
            skip_reason="jev_unavailable",
        )
        n_leg = fb.normalized_decision(legacy)
        n_off = fb.normalized_decision(off)
        self.assertEqual(
            fb.canonical_result_json(n_leg), fb.canonical_result_json(n_off)
        )
        self.assertEqual(legacy["configuredMode"], "legacy")
        self.assertEqual(off["configuredMode"], "off")
        self.assertNotEqual(
            fb.canonical_result_json(legacy), fb.canonical_result_json(off)
        )

    def test_byte_identical_ranking_same_inputs(self):
        a = fb.select(CATALOG, "sales followup", skip_reason="not_authorized")
        b = fb.select(CATALOG, "sales followup", skip_reason="not_authorized")
        self.assertEqual(
            fb.canonical_result_json(fb.normalized_decision(a)),
            fb.canonical_result_json(fb.normalized_decision(b)),
        )

    def test_zero_traffic_counters_all_modes(self):
        for mode in ("auto", "shadow", "legacy", "off"):
            got = fb.select(
                CATALOG,
                "email nurture",
                {"configuredMode": mode},
                jev_available=False,
                embeddings_available=False,
                skip_reason="jev_unavailable",
            )
            self.assertEqual(got["jevCalls"], 0, mode)
            self.assertEqual(got["probeCalls"], 0, mode)
            self.assertEqual(got["shadowRemoteCalls"], 0, mode)

    def test_effective_path_is_non_jev_for_fallback(self):
        got = fb.select(CATALOG, "email nurture", skip_reason="data_not_permitted")
        self.assertEqual(got["effectivePath"], "non_jev")


class SkipReasons(unittest.TestCase):
    def test_all_four_skip_reasons_surface_honestly(self):
        for reason in fb.SKIP_REASONS:
            got = fb.select(CATALOG, "email nurture", skip_reason=reason)
            self.assertEqual(got["skipReason"], reason, reason)
            self.assertEqual(got["effectivePath"], "non_jev", reason)

    def test_bad_skip_reason_raises(self):
        with self.assertRaises(ValueError):
            fb.select(CATALOG, "email nurture", skip_reason="maybe_later")
        with self.assertRaises(ValueError):
            fb.select(CATALOG, "email nurture", skip_reason=None)
        with self.assertRaises(ValueError):
            fb.select(
                CATALOG,
                "email nurture",
                jev_available=True,
                embeddings_available=True,
                skip_reason="jev_unavailable",
            )


class ReadOnlyAssignment(unittest.TestCase):
    def test_caller_data_untouched(self):
        catalog = copy.deepcopy(CATALOG)
        config = {"configuredMode": "legacy", "policy_version": "decision-policy-v1"}
        before_cat, before_cfg = copy.deepcopy(catalog), copy.deepcopy(config)
        fb.select(catalog, "email nurture", config, skip_reason="jev_unavailable")
        self.assertEqual(catalog, before_cat)
        self.assertEqual(config, before_cfg)

    def test_winner_is_top_lexical_overlap(self):
        got = fb.select(CATALOG, "sales followup help", skip_reason="jev_unavailable")
        self.assertEqual(got["selectedId"], "persona-gamma")
        self.assertGreater(got["ranking"][0]["score"], 0.0)
        scores = [r["score"] for r in got["ranking"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(
            [r["id"] for r in got["ranking"]],
            ["persona-gamma", "persona-alpha", "persona-beta"],
        )

    def test_stable_catalog_order_on_ties(self):
        tied = [
            {"id": "b-one", "text": "zzz", "topics": []},
            {"id": "a-two", "text": "zzz", "topics": []},
        ]
        got = fb.select(tied, "qqq no overlap here", skip_reason="budget_exhausted")
        self.assertEqual([r["id"] for r in got["ranking"]], ["b-one", "a-two"])

    def test_empty_catalog_truthful_no_selection(self):
        got = fb.select([], "anything at all", skip_reason="jev_unavailable")
        self.assertIsNone(got["selectedId"])
        self.assertEqual(got["ranking"], [])
        self.assertIn("empty_catalog_truthful_fallback", got["reasonCodes"])

    def test_result_carries_policy_and_config_revisions(self):
        got = fb.select(
            CATALOG,
            "email nurture",
            {"policy_version": "decision-policy-v1", "configRevision": "cfgrev-9"},
            skip_reason="jev_unavailable",
        )
        self.assertEqual(got["policyVersion"], "decision-policy-v1")
        self.assertEqual(got["configRevision"], "cfgrev-9")


class FallbackModelOptional(unittest.TestCase):
    def test_absent_model_is_pure_rules(self):
        got = fb.select(CATALOG, "email nurture", skip_reason="jev_unavailable")
        self.assertIsNone(got["fallbackModelUsed"])
        self.assertNotIn("caller_fallback_model_noted", got["reasonCodes"])

    def test_present_model_only_annotated_never_invoked(self):
        got = fb.select(
            CATALOG,
            "email nurture",
            {"fallback_model": "client-approved-helper"},
            skip_reason="jev_unavailable",
        )
        self.assertEqual(got["fallbackModelUsed"], "client-approved-helper")
        self.assertIn("caller_fallback_model_noted", got["reasonCodes"])
        plain = fb.select(CATALOG, "email nurture", skip_reason="jev_unavailable")
        self.assertEqual(
            [r["id"] for r in got["ranking"]],
            [r["id"] for r in plain["ranking"]],
        )
        self.assertEqual(got["jevCalls"], 0)
        self.assertEqual(got["probeCalls"], 0)

    def test_no_key_required_empty_config_valid(self):
        ok, errs = fb.validate_config({})
        self.assertTrue(ok, errs)


class FailClosed(unittest.TestCase):
    def test_select_raises_on_bad_input(self):
        with self.assertRaises(ValueError):
            fb.select("not-a-list", "q", skip_reason="jev_unavailable")
        with self.assertRaises(ValueError):
            fb.select([{"id": "x", "text": "t"}], "", skip_reason="jev_unavailable")
        with self.assertRaises(ValueError):
            fb.select(CATALOG, "q", {"configuredMode": "turbo"},
                      skip_reason="jev_unavailable")
        with self.assertRaises(ValueError):
            fb.select([{"id": "dup"}, {"id": "dup"}], "q",
                      skip_reason="jev_unavailable")

    def test_validators_never_raise(self):
        for bad in (None, "x", 42, [], {"configuredMode": "nope"},
                    {"fallback_model": ""}, {"skip_reason": "zzz"}):
            ok, errs = fb.validate_config(bad)
            self.assertFalse(ok, f"accepted bad config: {bad!r}"[:100])
            self.assertTrue(errs)
        for bad in (None, "x", {}, [{"no": "id"}], [{"id": "a"}, {"id": "a"}]):
            ok, errs = fb.validate_catalog(bad)
            self.assertFalse(ok, f"accepted bad catalog: {bad!r}"[:100])
            self.assertTrue(errs)

    def test_canonical_json_deterministic(self):
        a = fb.select(CATALOG, "email nurture", skip_reason="jev_unavailable")
        shuffled = dict(reversed(list(a.items())))
        self.assertEqual(fb.canonical_result_json(a),
                         fb.canonical_result_json(shuffled))
        self.assertEqual(
            json.loads(fb.canonical_result_json(a))["selectedId"], "persona-alpha"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
