#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_agnes_gates.py -- evidence suite for agnes_gates.py.

A24 Leg 4, build lane B (G-03, G-04, G-05, G-06, G-11). Covers
the contract section 11.5 subsets that touch the gates: model
resolution and stored-config provenance, the policy cases, the
ratio cases, and the post-Q1 citation cases. Stdlib unittest
only; no network, no sender, no spend. Run:

  python3 -m unittest test_agnes_gates -v
"""

from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parents[1]
_SUBSTRATE_DIR = _REPO_ROOT / "63-agnes-image" / "scripts"
for _p in (str(_HERE), str(_SUBSTRATE_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import agnes_gates as gates  # noqa: E402
import launch_prompt_policy  # noqa: E402
import resolve_model  # noqa: E402
import validate_payload  # noqa: E402
from agnes_gates import (  # noqa: E402
    CapInfo,
    CitationResolutionError,
    DispatchMetadata,
    MalformedCapRecord,
    PolicyEvaluationStop,
    RatioDisagreement,
)

ALL_ELEMENTS = {"subject", "environment", "style", "lighting",
                "composition", "output"}
KNOWN_ENTRY_HASH = ("ace1998862604904b5e2e224c0f85c87daf1ea0"
                    "7b74d2b60608589a4631e0532")


def long_prompt(chars: int) -> str:
    """A prompt of at least chars characters built from unique
    tokens, so the completeness padding rule (repeated 8-word
    grams) cannot fire."""
    words = []
    total = 0
    i = 0
    while total < chars:
        w = f"tok{i:05d}x"
        words.append(w)
        total += len(w) + 1
        i += 1
    return " ".join(words)


class ModelResolutionGateTests(unittest.TestCase):
    """Section 11.5 resolution and provenance cases, as they
    touch the gates (G-11 retention included)."""

    def test_none_resolves_to_default_with_default_provenance(self):
        res = resolve_model.resolve_model(None)
        self.assertEqual(res.model_id, "agnes-image-2.5-flash")
        self.assertEqual(res.provenance, "default")
        self.assertEqual(res.role, "default")

    def test_generic_alias_resolves_default_explicit_alias(self):
        res = resolve_model.resolve_model("agnes image")
        self.assertEqual(res.model_id, "agnes-image-2.5-flash")
        self.assertEqual(res.provenance, "explicit_alias")

    def test_default_alias_resolves_default_explicit_alias(self):
        res = resolve_model.resolve_model("agnes image 2.5")
        self.assertEqual(res.model_id, "agnes-image-2.5-flash")
        self.assertEqual(res.provenance, "explicit_alias")

    def test_explicit_21_pin_stays(self):
        res = resolve_model.resolve_model("agnes-image-2.1-flash")
        self.assertEqual(res.model_id, "agnes-image-2.1-flash")
        self.assertEqual(res.provenance, "explicit_pin")
        self.assertEqual(res.role, "legacy")

    def test_legacy_alias_stays_on_21(self):
        res = resolve_model.resolve_model("agnes image legacy")
        self.assertEqual(res.model_id, "agnes-image-2.1-flash")
        self.assertEqual(res.provenance, "explicit_alias")

    def test_rejected_text_video_ids_raise_before_payload(self):
        for bad in ("agnes-2.5-flash", "agnes-2.0-flash",
                    "agnes-video-2.5-flash", "agnes-video-2.0-flash"):
            with self.subTest(bad=bad):
                with self.assertRaises(resolve_model.ResolutionError):
                    resolve_model.resolve_model(bad)
                # The payload gate independently refuses them too;
                # resolution simply never lets them reach it.
                ok, exit_code, _, _ = validate_payload.validate_payload_data(
                    {"model": bad, "prompt": "x", "size": "1K"})
                self.assertFalse(ok)
                self.assertEqual(exit_code, 2)

    def test_stored_generated_default_follows_current_default(self):
        res = resolve_model.resolve_stored_config(
            "agnes-image-2.1-flash", "generated_default")
        self.assertEqual(res.model_id, "agnes-image-2.5-flash")
        self.assertEqual(res.provenance, "default")

    def test_stored_missing_provenance_ambiguous_no_overwrite(self):
        stored = {"model": "agnes-image-2.1-flash", "provenance": None}
        res = resolve_model.resolve_stored_config(
            stored["model"], stored["provenance"])
        self.assertEqual(res.model_id, "agnes-image-2.1-flash")
        self.assertEqual(res.provenance, "ambiguous")
        # The gate retains the result in metadata; the stored
        # configuration itself is never written by resolution.
        self.assertEqual(stored,
                         {"model": "agnes-image-2.1-flash",
                          "provenance": None})

    def test_stored_explicit_pin_preserved(self):
        res = resolve_model.resolve_stored_config(
            "agnes-image-2.1-flash", "explicit_pin")
        self.assertEqual(res.model_id, "agnes-image-2.1-flash")
        self.assertEqual(res.provenance, "explicit_pin")

    def test_full_resolution_retained_in_dispatch_metadata(self):
        res = resolve_model.resolve_model("agnes image 2.1")
        meta = DispatchMetadata().retain_resolution(res)
        record = meta.to_record()
        self.assertEqual(record["resolution"]["model_id"],
                         "agnes-image-2.1-flash")
        self.assertEqual(record["resolution"]["role"], "legacy")
        self.assertEqual(record["resolution"]["provenance"],
                         "explicit_alias")
        self.assertEqual(record["resolution"]["requested"],
                         "agnes image 2.1")
        # Provenance stays out of a provider payload built from
        # the same resolution: only model_id crosses that line.
        payload = {"model": res.model_id, "prompt": "p", "size": "1K"}
        self.assertNotIn("provenance", payload)
        self.assertNotIn("resolution", payload)


class CapTranslationTests(unittest.TestCase):
    """G-05: cap records translated into CapInfo, fail closed."""

    def test_both_current_models_translate_not_published(self):
        for model_id in ("agnes-image-2.5-flash", "agnes-image-2.1-flash"):
            with self.subTest(model_id=model_id):
                record = gates.load_model_record(model_id)
                cap = gates.translate_cap(record)
                self.assertEqual(cap, CapInfo(status="not_published",
                                              chars=None))

    def test_published_with_number_translates(self):
        record = {"canonical_model_id": "m", "cap_status": "PUBLISHED",
                  "vendor_hard_cap_chars": 8000,
                  "owner_observed_cap_chars": None}
        self.assertEqual(gates.translate_cap(record),
                         CapInfo(status="published", chars=8000))

    def test_owner_observed_with_number_translates(self):
        record = {"canonical_model_id": "m",
                  "cap_status": "OWNER_OBSERVED",
                  "vendor_hard_cap_chars": None,
                  "owner_observed_cap_chars": 7500}
        self.assertEqual(gates.translate_cap(record),
                         CapInfo(status="owner_observed", chars=7500))

    def test_published_without_number_fails_closed(self):
        record = {"canonical_model_id": "m", "cap_status": "PUBLISHED",
                  "vendor_hard_cap_chars": None,
                  "owner_observed_cap_chars": None}
        with self.assertRaises(MalformedCapRecord):
            gates.translate_cap(record)

    def test_owner_observed_without_number_fails_closed(self):
        record = {"canonical_model_id": "m",
                  "cap_status": "OWNER_OBSERVED",
                  "vendor_hard_cap_chars": None,
                  "owner_observed_cap_chars": None}
        with self.assertRaises(MalformedCapRecord):
            gates.translate_cap(record)

    def test_not_published_with_a_number_fails_closed(self):
        record = {"canonical_model_id": "m",
                  "cap_status": "NOT_PUBLISHED",
                  "vendor_hard_cap_chars": 8000,
                  "owner_observed_cap_chars": None}
        with self.assertRaises(MalformedCapRecord):
            gates.translate_cap(record)

    def test_unknown_status_fails_closed(self):
        record = {"canonical_model_id": "m", "cap_status": "VERIFIED",
                  "vendor_hard_cap_chars": 8000,
                  "owner_observed_cap_chars": None}
        with self.assertRaises(MalformedCapRecord):
            gates.translate_cap(record)

    def test_registry_uppercase_never_reaches_evaluator(self):
        # The exact G-05 seam: passing the registry string through
        # untranslated makes the evaluator report an unknown
        # status; the gate's translation prevents that.
        raw = launch_prompt_policy.evaluate_launch_policy(
            "a prompt", set(ALL_ELEMENTS),
            CapInfo(status="NOT_PUBLISHED", chars=None))
        self.assertFalse(raw.valid)
        record = gates.load_model_record("agnes-image-2.5-flash")
        outcome = gates.evaluate_policy_gate(
            prompt="a prompt", elements_present=set(ALL_ELEMENTS),
            named_policy=None, cap=gates.translate_cap(record))
        self.assertTrue(outcome.result.valid)


class PolicyGateTests(unittest.TestCase):
    """Section 11.5 policy cases (G-04, and G-03's evaluated
    half)."""

    def gate(self, **kwargs):
        kwargs.setdefault("cap", CapInfo(status="not_published",
                                         chars=None))
        kwargs.setdefault("named_policy", None)
        return gates.evaluate_policy_gate(**kwargs)

    def test_missing_required_element_is_invalid(self):
        elements = set(ALL_ELEMENTS) - {"output"}
        with self.assertRaises(PolicyEvaluationStop) as ctx:
            self.gate(prompt="a complete scene description",
                      elements_present=elements)
        result = ctx.exception.result
        self.assertIsNotNone(result)
        self.assertFalse(result.valid)
        self.assertIn("output", result.missing_elements)
        self.assertTrue(result.errors)  # errors preserved

    def test_elements_recorded_verbatim_never_inferred(self):
        # The prose names every element; the supplied set is
        # empty. The gate must not infer from prose (G-04).
        prose = ("subject environment style lighting composition "
                 "output all appear in this sentence")
        with self.assertRaises(PolicyEvaluationStop) as ctx:
            self.gate(prompt=prose, elements_present=set())
        self.assertEqual(sorted(ctx.exception.result.missing_elements),
                         sorted(ALL_ELEMENTS))

    def test_supplied_elements_recorded_on_outcome(self):
        outcome = self.gate(prompt="a scene",
                            elements_present=set(ALL_ELEMENTS))
        self.assertEqual(set(outcome.elements_supplied), ALL_ELEMENTS)
        self.assertEqual(outcome.receipt_policy_id,
                         "signature_launch_completeness")

    def test_long_complete_prompt_not_rejected_for_length(self):
        prompt = long_prompt(20000)
        self.assertGreater(len(prompt), 19000)
        outcome = self.gate(prompt=prompt,
                            elements_present=set(ALL_ELEMENTS))
        self.assertTrue(outcome.result.valid)
        self.assertEqual(outcome.result.char_count, len(prompt.strip()))

    def test_published_cap_exactly_at_cap_passes(self):
        outcome = self.gate(prompt="a" * 100,
                            elements_present=set(ALL_ELEMENTS),
                            cap=CapInfo(status="published", chars=100))
        self.assertTrue(outcome.result.valid)

    def test_published_cap_one_over_fails(self):
        with self.assertRaises(PolicyEvaluationStop) as ctx:
            self.gate(prompt="a" * 101,
                      elements_present=set(ALL_ELEMENTS),
                      cap=CapInfo(status="published", chars=100))
        self.assertFalse(ctx.exception.result.valid)
        self.assertTrue(any("ceiling" in e
                            for e in ctx.exception.result.errors))

    def test_owner_observed_cap_enforced_the_same_way(self):
        with self.assertRaises(PolicyEvaluationStop):
            self.gate(prompt="a" * 51,
                      elements_present=set(ALL_ELEMENTS),
                      cap=CapInfo(status="owner_observed", chars=50))

    def test_legacy_band_long_prompt_valid_with_advisory_note(self):
        prompt = long_prompt(20000)
        outcome = self.gate(prompt=prompt, elements_present=set(),
                            named_policy="legacy_house_band")
        self.assertTrue(outcome.result.valid)
        self.assertIn("ABOVE_PREFERRED_MAX", outcome.result.note)
        # The evaluated ID is what the receipt must carry
        # explicitly; the receipt builder's default is the launch
        # ID and would have masked this (G-03).
        self.assertEqual(outcome.receipt_policy_id, "legacy_house_band")

    def test_named_policy_mismatch_with_result_stops(self):
        # G-03: stop if the request's named policy and the
        # evaluator result's policy ID differ. The real evaluators
        # return their own constants, so the branch is exercised
        # with a patched evaluator returning a foreign ID.
        foreign = launch_prompt_policy.PolicyResult(
            valid=True, policy_id="legacy_house_band", char_count=1,
            missing_elements=[], errors=[], note="")
        original = launch_prompt_policy.evaluate_launch_policy
        launch_prompt_policy.evaluate_launch_policy = (
            lambda prompt, elements, cap: foreign)
        try:
            with self.assertRaises(PolicyEvaluationStop) as ctx:
                self.gate(prompt="a scene",
                          elements_present=set(ALL_ELEMENTS),
                          named_policy="signature_launch_completeness")
            self.assertIn("mismatch", str(ctx.exception))
            self.assertIs(ctx.exception.result, foreign)
        finally:
            launch_prompt_policy.evaluate_launch_policy = original

    def test_unknown_named_policy_stops(self):
        with self.assertRaises(PolicyEvaluationStop):
            self.gate(prompt="a scene",
                      elements_present=set(ALL_ELEMENTS),
                      named_policy="some_other_policy")

    def test_empty_prompt_invalid(self):
        with self.assertRaises(PolicyEvaluationStop):
            self.gate(prompt="   ", elements_present=set(ALL_ELEMENTS))


class CitationTests(unittest.TestCase):
    """G-03 citation half: the governing band entry resolved by
    id plus entry hash against the registry of record."""

    def _registry_copy(self, mutate=None):
        source = gates.default_registry_path()
        data = json.loads(source.read_text(encoding="utf-8"))
        if mutate:
            mutate(data)
        tmp = tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(data, tmp)
        tmp.close()
        self.addCleanup(Path(tmp.name).unlink, missing_ok=True)
        return Path(tmp.name)

    def test_registry_of_record_resolves_by_id_and_hash(self):
        citation = gates.resolve_governing_citation()
        self.assertEqual(citation.policy_id, "kie-rule-12-band")
        self.assertEqual(citation.entry_hash, KNOWN_ENTRY_HASH)

    def test_tampered_stored_hash_fails_closed(self):
        def mutate(data):
            data["entries"][0]["entry_hash"] = "0" * 64
        path = self._registry_copy(mutate)
        with self.assertRaises(CitationResolutionError):
            gates.resolve_governing_citation(registry_path=path)

    def test_tampered_entry_content_fails_closed(self):
        def mutate(data):
            data["entries"][0]["provenance"] = "rewritten after minting"
        path = self._registry_copy(mutate)
        with self.assertRaises(CitationResolutionError):
            gates.resolve_governing_citation(registry_path=path)

    def test_missing_entry_fails_closed(self):
        with self.assertRaises(CitationResolutionError):
            gates.resolve_governing_citation(policy_id="no_such_policy")

    def test_non_active_entry_fails_closed(self):
        def mutate(data):
            entry = data["entries"][0]
            entry["entry_status"] = "superseded"
            # Recompute so only the status, not the hash, is wrong.
            entry["entry_hash"] = gates._entry_hash(entry)
        path = self._registry_copy(mutate)
        with self.assertRaises(CitationResolutionError):
            gates.resolve_governing_citation(registry_path=path)

    def test_citation_retained_in_metadata_record(self):
        citation = gates.resolve_governing_citation()
        meta = DispatchMetadata().attach_citation(citation)
        record = meta.to_record()
        self.assertEqual(record["governing_citation"]["policy_id"],
                         "kie-rule-12-band")
        self.assertEqual(record["governing_citation"]["entry_hash"],
                         KNOWN_ENTRY_HASH)


class RatioGateTests(unittest.TestCase):
    """Section 11.5 ratio cases (G-06)."""

    def test_every_model_ratio_passes_payload_validation(self):
        for model_id in ("agnes-image-2.5-flash", "agnes-image-2.1-flash"):
            record = gates.load_model_record(model_id)
            for ratio in record["aspect_ratios"]:
                with self.subTest(model_id=model_id, ratio=ratio):
                    ok, exit_code, errors, _ = (
                        validate_payload.validate_payload_data(
                            {"model": model_id, "prompt": "a scene",
                             "size": "1K", "ratio": ratio}))
                    self.assertTrue(ok, errors)
                    self.assertEqual(exit_code, 0)

    def test_gate_accepts_each_authoritative_ratio(self):
        record = gates.load_model_record("agnes-image-2.5-flash")
        for ratio in record["aspect_ratios"]:
            with self.subTest(ratio=ratio):
                outcome = gates.check_ratio_authority(
                    model_id="agnes-image-2.5-flash", record=record,
                    requested_ratio=ratio)
                self.assertEqual(outcome.requested_ratio, ratio)

    def test_unsupported_ratio_fails_and_is_not_remapped(self):
        ok, exit_code, _, _ = validate_payload.validate_payload_data(
            {"model": "agnes-image-2.5-flash", "prompt": "a scene",
             "size": "1K", "ratio": "5:4"})
        self.assertFalse(ok)
        self.assertEqual(exit_code, 2)
        record = gates.load_model_record("agnes-image-2.5-flash")
        with self.assertRaises(RatioDisagreement) as ctx:
            gates.check_ratio_authority(
                model_id="agnes-image-2.5-flash", record=record,
                requested_ratio="5:4")
        message = str(ctx.exception)
        self.assertIn("5:4", message)
        self.assertIn("agnes-image-2.5-flash", message)
        self.assertIn("not remapped", message)

    def test_no_ratio_requested_is_not_a_disagreement(self):
        record = gates.load_model_record("agnes-image-2.5-flash")
        outcome = gates.check_ratio_authority(
            model_id="agnes-image-2.5-flash", record=record,
            requested_ratio=None)
        self.assertIsNone(outcome.requested_ratio)
        self.assertEqual(len(outcome.authority), 8)

    def test_deliberate_disagreement_fails_closed_by_name(self):
        record = copy.deepcopy(
            gates.load_model_record("agnes-image-2.5-flash"))
        record["aspect_ratios"] = [
            r for r in record["aspect_ratios"] if r != "21:9"]
        record["dimension_table"] = {
            k: v for k, v in record["dimension_table"].items()
            if k != "21:9"}
        with self.assertRaises(RatioDisagreement) as ctx:
            gates.check_ratio_authority(
                model_id="agnes-image-2.5-flash", record=record)
        message = str(ctx.exception)
        self.assertIn("21:9", message)
        self.assertIn("agnes-image-2.5-flash", message)
        self.assertIn("models.json aspect_ratios", message)
        self.assertIn("validate_payload.RATIOS", message)

    def test_dimension_table_disagreement_fails_closed(self):
        record = copy.deepcopy(
            gates.load_model_record("agnes-image-2.5-flash"))
        record["dimension_table"] = {
            k: v for k, v in record["dimension_table"].items()
            if k != "3:2"}
        with self.assertRaises(RatioDisagreement) as ctx:
            gates.check_ratio_authority(
                model_id="agnes-image-2.5-flash", record=record)
        self.assertIn("dimension_table", str(ctx.exception))

    def test_registry_snapshot_disagreement_fails_closed(self):
        record = gates.load_model_record("agnes-image-2.5-flash")
        snapshot = [r for r in record["aspect_ratios"] if r != "9:16"]
        with self.assertRaises(RatioDisagreement) as ctx:
            gates.check_ratio_authority(
                model_id="agnes-image-2.5-flash", record=record,
                registry_snapshot=snapshot)
        self.assertIn("registry snapshot", str(ctx.exception))
        self.assertIn("9:16", str(ctx.exception))

    def test_current_records_agree_with_validator(self):
        for model_id in ("agnes-image-2.5-flash", "agnes-image-2.1-flash"):
            with self.subTest(model_id=model_id):
                record = gates.load_model_record(model_id)
                outcome = gates.check_ratio_authority(
                    model_id=model_id, record=record)
                self.assertEqual(set(outcome.authority),
                                 set(validate_payload.RATIOS))


if __name__ == "__main__":
    unittest.main()
