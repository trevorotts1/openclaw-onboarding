#!/usr/bin/env python3
"""F16 S2: one style vocabulary, one brand identity, one creative-direction precedence.

Free: no network, no model, no paid call.
Run: python3 shared-utils/client_intake/tests/test_brand_record.py
"""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
sys.path.insert(0, str(PKG))

_spec = importlib.util.spec_from_file_location("brand_record", PKG / "brand_record.py")
brand_record = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(brand_record)

# Every spelling the four modules actually used, plus invention and absence.
SPELLINGS = ("client_choice", "client-choice", "client", "accepted_recommendation",
             "recommended_accepted", "recommendation-accepted", "palette-help", "feel-words",
             "default_to_confirm", "suggested", "proposed", "unknown", "not_asked",
             "", None, "made_up_value", "  Client_Choice  ")


class IdempotenceTests(unittest.TestCase):
    def test_normalizing_twice_equals_normalizing_once(self):
        for value in SPELLINGS:
            once = brand_record.normalize_style_source(value)
            self.assertIn(once, brand_record.STYLE_SOURCES, (value, once))
            self.assertEqual(brand_record.normalize_style_source(once), once, value)

    def test_palette_status_normalizing_twice_equals_normalizing_once(self):
        for value in ("provided", "client-confirmed", "client_confirmed", "suggested",
                      "default_to_confirm", "unknown", "", None, "made_up", " Provided "):
            once = brand_record.normalize_palette_status(value)
            self.assertIn(once, brand_record.PALETTE_STATUSES, (value, once))
            self.assertEqual(brand_record.normalize_palette_status(once), once, value)

    def test_an_entry_normalizes_to_a_canonical_value(self):
        entry = {"status": "provided", "value": "B", "source": "recommendation-accepted",
                 "accepted_proposal": True}
        once = brand_record.style_source_from_entry(entry)
        self.assertEqual(once, "recommended_accepted")
        self.assertEqual(brand_record.normalize_style_source(once), once)


class VocabularyTests(unittest.TestCase):
    def test_both_live_spellings_are_the_same_recorded_decision(self):
        for value in ("accepted_recommendation", "recommended_accepted"):
            self.assertEqual(brand_record.normalize_style_source(value), "recommended_accepted")
            self.assertTrue(brand_record.is_recorded_decision(value))

    def test_a_proposal_is_never_a_recorded_decision(self):
        for value in ("default_to_confirm", "suggested", "proposed"):
            self.assertEqual(brand_record.normalize_style_source(value), "default_to_confirm")
            self.assertFalse(brand_record.is_recorded_decision(value))

    def test_absence_is_unknown_and_never_client_choice(self):
        for value in ("", None, "not_asked", "unknown", "not-asked"):
            self.assertEqual(brand_record.normalize_style_source(value), "unknown")
            self.assertFalse(brand_record.is_recorded_decision(value))

    def test_an_invented_spelling_is_not_known(self):
        self.assertFalse(brand_record.is_known_style_source("made_up_value"))
        self.assertTrue(brand_record.is_known_style_source("accepted_recommendation"))
        self.assertTrue(brand_record.is_known_style_source(None))

    def test_an_accepted_answers_entry_is_recommended_accepted(self):
        self.assertEqual(brand_record.style_source_from_entry(
            {"status": "provided", "value": "C", "accepted_proposal": True}), "recommended_accepted")
        self.assertEqual(brand_record.style_source_from_entry(
            {"status": "provided", "value": "C", "source": "recommendation-accepted"}),
            "recommended_accepted")
        self.assertEqual(brand_record.style_source_from_entry(
            {"status": "provided", "value": "C", "source": "client"}), "client_choice")
        self.assertEqual(brand_record.style_source_from_entry(
            {"status": "default_to_confirm", "value": "A"}), "default_to_confirm")
        self.assertEqual(brand_record.style_source_from_entry(None), "unknown")


class BrandIdentityTests(unittest.TestCase):
    def test_the_digest_is_the_producers_own_hash_not_a_second_identity(self):
        import engine  # the same package: brand_provenance owns the plan's hash
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "brand.json"
            path.write_text(json.dumps({"brand_id": "acme", "palette_status": "provided"}), encoding="utf-8")
            produced = engine.brand_provenance({"answers": {}, "meta": {}}, brand_file=path)["brand_file_sha256"]
            self.assertEqual(brand_record.brand_digest(path), produced)

    def test_the_record_states_verified_mismatch_unbound_and_unreadable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "brand.json"
            path.write_text(json.dumps({"palette_status": "provided"}), encoding="utf-8")
            digest = brand_record.brand_digest(path)
            self.assertTrue(brand_record.matches(
                brand_record.brand_record(path, plan_brand_sha256=digest)))
            mismatch = brand_record.brand_record(path, plan_brand_sha256="0" * 64)
            self.assertEqual(mismatch["state"], "mismatch")
            self.assertFalse(brand_record.matches(mismatch))
            unbound = brand_record.brand_record(path)
            self.assertEqual(unbound["state"], "unbound")
            self.assertFalse(brand_record.matches(unbound))
            self.assertEqual(brand_record.brand_record(Path(tmp) / "nope.json")["state"], "unreadable")

    def test_a_missing_or_unrecognized_palette_status_is_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            for doc, want in (({}, "unknown"), ({"palette_status": "made_up"}, "unknown"),
                              ({"palette_status": "client-confirmed"}, "provided"),
                              ({"palette_status": "provided"}, "provided")):
                path = Path(tmp) / "b.json"
                path.write_text(json.dumps(doc), encoding="utf-8")
                rec = brand_record.brand_record(path)
                self.assertEqual(rec["palette_status"], want, doc)
                self.assertEqual(rec["palette_confirmed"], want == "provided")


class CreativeDirectionPrecedenceTests(unittest.TestCase):
    def test_an_approved_external_blend_supplies_the_grade(self):
        for mode in ("FULL", "ADAPT", "SUPPRESS"):
            policy = brand_record.creative_direction_policy(
                kind="external_direction", blend=mode.lower(), approval_ref="appr_1")
            self.assertEqual((policy["grade_mode"], policy["grade_owner"]), (mode, brand_record.EXTERNAL_STYLE))
            self.assertEqual(policy["conflicts"], [])
            self.assertEqual(policy["direction_kind"], "external_direction")

    def test_an_unapproved_blend_cannot_suppress_the_house_grade(self):
        policy = brand_record.creative_direction_policy(kind="external_direction", blend="SUPPRESS")
        self.assertEqual((policy["grade_mode"], policy["grade_owner"]), ("FULL", brand_record.HOUSE_POLICY))
        self.assertTrue(policy["conflicts"])

    def test_a_blend_with_no_external_direction_cannot_suppress_the_house_grade(self):
        policy = brand_record.creative_direction_policy(kind="house_look", blend="SUPPRESS",
                                                        approval_ref="appr_1")
        self.assertEqual((policy["grade_mode"], policy["grade_owner"]), ("FULL", brand_record.HOUSE_POLICY))
        self.assertTrue(policy["conflicts"])

    def test_an_external_style_without_a_blend_keeps_the_house_grade_and_owns_the_style(self):
        policy = brand_record.creative_direction_policy(kind="external_direction")
        self.assertEqual((policy["grade_mode"], policy["style_owner"]), ("FULL", "client_direction"))

    def test_no_direction_is_not_asked_never_a_choice_and_the_house_look_applies(self):
        for kind in (None, "", "not_asked"):
            policy = brand_record.creative_direction_policy(kind=kind)
            self.assertEqual((policy["style_state"], policy["style_owner"]), ("not_asked", brand_record.HOUSE_POLICY))
            self.assertEqual(policy["grade_mode"], "FULL")

    def test_an_unrecognized_kind_is_unknown_and_claims_nothing(self):
        policy = brand_record.creative_direction_policy(kind="made_up")
        self.assertEqual((policy["style_owner"], policy["style_state"]), ("unknown", "unknown"))

    def test_precedence_is_total_and_names_a_winner_on_every_axis(self):
        kinds = (None, "house_look", "external_direction", "own_reference", "described", "made_up")
        blends = (None, "full", "adapt", "suppress", "made_up")
        approvals = (None, "appr_1")
        for kind in kinds:
            for blend in blends:
                for approval in approvals:
                    policy = brand_record.creative_direction_policy(
                        kind=kind, blend=blend, approval_ref=approval)
                    self.assertIn(policy["grade_mode"], brand_record.GRADE_MODES)
                    self.assertIn(policy["grade_owner"], (brand_record.EXTERNAL_STYLE, brand_record.HOUSE_POLICY))
                    grade_rows = [r for r in policy["precedence"] if r["axis"] == "grade"]
                    self.assertEqual(sum(1 for r in grade_rows if r["wins"]), 1,
                                     (kind, blend, approval, policy["precedence"]))
                    self.assertIn(policy["style_state"], ("house_look", "recorded", "not_asked", "unknown"))

    def test_the_policy_is_idempotent_through_its_own_output(self):
        policy = brand_record.creative_direction_policy(kind="external_direction", blend="adapt",
                                                        approval_ref="appr_1")
        again = brand_record.creative_direction_policy(kind=policy["direction_kind"],
                                                       blend=policy["grade_mode"],
                                                       approval_ref=policy["approval_ref"])
        self.assertEqual((again["grade_mode"], again["grade_owner"]),
                         (policy["grade_mode"], policy["grade_owner"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
