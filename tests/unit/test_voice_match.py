#!/usr/bin/env python3
"""D18 voice-matching tests (JEV spec 1.1, ss 8.2/8.3/8.4; extends D16, feeds D17).

Proves, against the REAL personas/voice_match.py implementation:
  * ranking follows explicit audience needs/context/brand prefs/documented
    suitability (lexical overlap over structured fields + suitability text);
  * demographic tokens are INERT: candidates identical except one
    demographic word rank in the same order;
  * suitability evidence is the discriminator (required per candidate,
    surfaced in evidence_refs, D16-shape valid);
  * provenance basis (needs|context|brand|suitability) + evidence_refs feed
    D16 evidence shapes (REAL make_profile round-trip);
  * assignment-read-only (inputs unmutated) and fail-closed (empty
    candidates, malformed candidates, signal-free audience, zero overlap
    raise — never rank-everything).

Run: pytest tests/unit/test_voice_match.py -q
"""

from __future__ import annotations

import copy
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


vm = _load("d18_voice_match_under_test", _DE / "personas" / "voice_match.py")
ep = _load("d18_evidence_profiles", _DE / "personas" / "evidence_profiles.py")


def _cand(cid, **over):
    base = {
        "candidate_id": cid,
        "needs_tags": ["email nurture"],
        "context_tags": ["startup founders"],
        "brand_tags": ["direct plainspoken"],
        "suitability": "proven email voice for startup founders, plainspoken and direct",
        "suitability_evidence": [f"catalog:voice:{cid}:usable_as=audience"],
    }
    base.update(over)
    return base


class NeedsRanking(unittest.TestCase):
    def test_explicit_needs_win(self):
        cands = [
            _cand("v-quiet", needs_tags=["whisper lullaby"],
                  suitability="quiet lullaby voice for bedtime",
                  suitability_evidence=["catalog:voice:v-quiet:usable_as=audience"]),
            _cand("v-mail"),
        ]
        ranked = vm.semantic_voice_match("email nurture sequence", cands)
        self.assertEqual(ranked[0]["candidate_id"], "v-mail")
        self.assertGreater(ranked[0]["score"], ranked[1]["score"])

    def test_context_brand_and_suitability_text_all_count(self):
        cands = [
            _cand("v-plain", context_tags=["enterprise bankers"],
                  brand_tags=["formal ornate"],
                  suitability="formal ornate voice for enterprise bankers",
                  suitability_evidence=["catalog:voice:v-plain:usable_as=audience"]),
            _cand("v-mail"),
        ]
        ranked = vm.semantic_voice_match(
            {"needs": "email nurture", "context": "startup founders",
             "brand_prefs": "direct plainspoken"}, cands)
        self.assertEqual(ranked[0]["candidate_id"], "v-mail")

    def test_string_and_dict_audience_agree(self):
        cands = [_cand("v-a"), _cand("v-b", needs_tags=["sports recap"])]
        by_str = vm.semantic_voice_match("email nurture", cands)
        by_dict = vm.semantic_voice_match({"needs": "email nurture"}, cands)
        self.assertEqual([m["candidate_id"] for m in by_str],
                         [m["candidate_id"] for m in by_dict])

    def test_deterministic_tie_break_by_id(self):
        cands = [_cand("v-b"), _cand("v-a")]
        ranked = vm.semantic_voice_match("email nurture", cands)
        self.assertEqual(ranked[0]["score"], ranked[1]["score"])
        self.assertEqual([m["candidate_id"] for m in ranked], ["v-a", "v-b"])

    def test_select_voice_returns_winner(self):
        cands = [_cand("v-b", needs_tags=["sports recap"]), _cand("v-a")]
        winner = vm.select_voice("email nurture", cands)
        self.assertEqual(winner["candidate_id"], "v-a")
        self.assertIn(winner["basis"], vm.BASIS_VALUES)


class DemographicInertness(unittest.TestCase):
    def test_demographic_word_alone_never_changes_ranking(self):
        plain = [_cand("v-a"), _cand("v-b", needs_tags=["sports recap"])]
        demo = [_cand("v-a"), _cand("v-b", needs_tags=["sports recap",
                                                       "women millennial latina"])]
        before = [(m["candidate_id"], m["score"]) for m in
                  vm.semantic_voice_match("email nurture", plain)]
        after = [(m["candidate_id"], m["score"]) for m in
                 vm.semantic_voice_match("email nurture", demo)]
        self.assertEqual(before, after)

    def test_audience_demographic_words_are_inert_not_signal(self):
        cands = [_cand("v-a"), _cand("v-b", needs_tags=["sports recap"])]
        ranked = vm.semantic_voice_match("women millennial latina email nurture", cands)
        self.assertEqual(ranked[0]["candidate_id"], "v-a")
        with self.assertRaises(ValueError):
            vm.semantic_voice_match("women millennial latina", cands)

    def test_suitability_evidence_is_the_discriminator(self):
        cands = [
            _cand("v-a", suitability_evidence=["catalog:voice:v-a:case-study:q3"]),
            _cand("v-b", suitability_evidence=["catalog:voice:v-b:case-study:q3"]),
        ]
        ranked = vm.semantic_voice_match("email nurture", cands)
        self.assertIn("catalog:voice:v-a:case-study:q3", ranked[0]["evidence_refs"])
        # Same field overlap, different refs -> refs travel with the winner.
        self.assertNotIn("catalog:voice:v-b:case-study:q3", ranked[0]["evidence_refs"])


class ProvenanceFeedsD16(unittest.TestCase):
    def test_basis_values_and_refs(self):
        ranked = vm.semantic_voice_match(
            {"needs": "email nurture", "context": "startup founders",
             "brand_prefs": "direct plainspoken"},
            [_cand("v-mail")])
        match = ranked[0]
        self.assertIn(match["basis"], ("needs", "context", "brand", "suitability"))
        self.assertTrue(match["evidence_refs"])
        self.assertTrue(any(r.startswith(f"{match['basis']}:") or r.startswith("catalog:")
                            for r in match["evidence_refs"]))

    def test_suitability_basis_when_text_carries_signal(self):
        cands = [_cand("v-deep",
                       needs_tags=["unrelated topic"],
                       context_tags=["unrelated crowd"],
                       brand_tags=["unrelated tone"],
                       suitability="email nurture playbook for startup founders",
                       suitability_evidence=["catalog:voice:v-deep:usable_as=audience"])]
        match = vm.semantic_voice_match("email nurture startup founders direct", cands)[0]
        self.assertEqual(match["basis"], "suitability")

    def test_match_refs_validate_as_real_d16_profile(self):
        match = vm.semantic_voice_match("email nurture", [_cand("v-mail")])[0]
        profile = ep.make_profile(
            "voice", "explicit", evidence_refs=match["evidence_refs"],
            confidence="medium",
            detail=f"d18 {match['basis']} match for {match['candidate_id']}")
        ok, errs = ep.validate_profile(profile)
        self.assertTrue(ok, errs)

    def test_d16_resolve_audience_ordering_untouched(self):
        p = ep.resolve_audience(
            explicit="startup founders",
            prior={"label": "old", "scope_match": True, "data_unchanged": True},
            company="house-list")
        self.assertEqual(p.resolution, "explicit")
        self.assertFalse(p.confirm_required)

    def test_top_n_slices_ranked(self):
        cands = [_cand("v-a"), _cand("v-b"), _cand("v-c")]
        ranked = vm.semantic_voice_match("email nurture", cands, top_n=2)
        self.assertEqual(len(ranked), 2)
        self.assertEqual([m["candidate_id"] for m in ranked], ["v-a", "v-b"])


class AssignmentReadOnlyFailClosed(unittest.TestCase):
    def test_inputs_never_mutated(self):
        audience = {"needs": ["email nurture"], "context": ["startup founders"],
                    "brand_prefs": ["direct"]}
        cands = [_cand("v-a"), _cand("v-b")]
        frozen_a, frozen_c = copy.deepcopy(audience), copy.deepcopy(cands)
        vm.semantic_voice_match(audience, cands)
        self.assertEqual(audience, frozen_a)
        self.assertEqual(cands, frozen_c)

    def test_empty_candidates_raise_never_rank_everything(self):
        for bad in ([], None, "v-a"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                vm.semantic_voice_match("email nurture", bad)

    def test_malformed_candidates_raise(self):
        with self.assertRaises(ValueError):
            vm.semantic_voice_match("email nurture", [{"needs_tags": ["email"]}])
        with self.assertRaises(ValueError):
            vm.semantic_voice_match("email nurture", [_cand("v-x", suitability_evidence=[])])
        with self.assertRaises(ValueError):
            vm.semantic_voice_match("email nurture", [_cand("v-x", candidate_id="  ")])
        with self.assertRaises(ValueError):
            vm.semantic_voice_match("email nurture", "not-a-list")

    def test_signal_free_audience_raises(self):
        cands = [_cand("v-a")]
        for bad in ("", "   ", {}, {"needs": []}, [], None, 42):
            with self.assertRaises(ValueError, msg=repr(bad)):
                vm.semantic_voice_match(bad, cands)

    def test_zero_overlap_field_raises_never_demographic_guess(self):
        cands = [_cand("v-a", needs_tags=["quantum knitting"],
                       context_tags=["deep sea welders"],
                       brand_tags=["baroque whispers"],
                       suitability="quantum knitting for deep sea welders",
                       suitability_evidence=["catalog:voice:v-a:usable_as=audience"])]
        with self.assertRaises(ValueError):
            vm.semantic_voice_match("email nurture startup founders", cands)

    def test_bad_top_n_raises(self):
        with self.assertRaises(ValueError):
            vm.semantic_voice_match("email nurture", [_cand("v-a")], top_n=0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
