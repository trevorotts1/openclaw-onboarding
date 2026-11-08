#!/usr/bin/env python3
"""F16 S2 in Skill 83's image plan: one style vocabulary, the plan's brand hash, and the
resolved creative-direction precedence.

Free: no provider, no Command Center. The approval verifier is faked at its one seam and the
resolution is exercised directly (the C3 writer's substrate gate is exercised by the suite).
Run: python3 83-black-friday-launcher/tests/test_f16_brand_style_precedence.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import image_plan  # noqa: E402
from launcher_core.image_plan import ImagePlanError, resolve  # noqa: E402

PLAN_HASH = "a" * 64
APPROVAL = "appr_budget_f16"


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.brand = self.write_brand({"palette_status": "provided", "brand_id": "acme"})
        self.digest = hashlib.sha256(Path(self.brand).read_bytes()).hexdigest()

    def write_brand(self, doc, name="brand.json"):
        path = self.tmp / name
        path.write_text(json.dumps(doc), encoding="utf-8")
        return str(path)

    def free(self, **over):
        raw = {"brand_file": self.brand, "brand_owner": "TEST-ONLY Client", "design_style": "B",
               "design_style_source": "client_choice", "image_provider": "kie", "image_cap": 40}
        raw.update(over)
        return resolve(raw, test_only=True)

    def paid(self, **over):
        raw = {"brand_file": self.brand, "brand_owner": "TEST-ONLY Client", "design_style": "B",
               "design_style_source": "client_choice", "image_provider": "kie",
               "image_cap_minor": 4000, "image_currency": "USD", "paid_render_approval_ref": APPROVAL,
               "brand_sha256": self.digest}
        raw.update(over)
        verify = mock.Mock(return_value={"ok": True, "approval_id": APPROVAL, "kind": "paid_asset_budget",
                                         "authority": "command-center"})
        with mock.patch.object(image_plan, "_approval_verify", return_value=verify):
            return resolve(raw, test_only=False, plan_hash=PLAN_HASH)


class StyleVocabularyTests(Base):
    def test_absence_is_unknown_not_a_client_choice(self):
        inputs, _ = self.free(design_style_source=None)
        self.assertEqual(inputs["design_style_source"], "unknown")

    def test_both_spellings_of_an_accepted_recommendation_read_as_one_decision(self):
        for spelling in ("accepted_recommendation", "recommended_accepted"):
            inputs, _ = self.free(design_style_source=spelling)
            self.assertEqual(inputs["design_style_source"], "recommended_accepted", spelling)

    def test_an_accepted_recommendation_can_be_paid_for_and_an_absence_cannot(self):
        inputs, _ = self.paid(design_style_source="recommended_accepted")
        self.assertTrue(inputs["allow_paid"])
        for source in (None, "default_to_confirm", "suggested"):
            with self.assertRaises(ImagePlanError) as ctx:
                self.paid(design_style_source=source)
            self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-STYLE", source)

    def test_an_invented_source_is_refused_not_downgraded(self):
        with self.assertRaises(ImagePlanError) as ctx:
            self.free(design_style_source="made_up")
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-STYLE")


class BrandHashTests(Base):
    def test_the_plan_brand_hash_is_matched_against_the_file_in_hand(self):
        inputs, _ = self.paid()
        self.assertEqual(inputs["brand_sha256"], self.digest)
        self.assertEqual(inputs["brand_record_state"], "verified")

    def test_a_stale_or_substituted_brand_file_is_never_drawn(self):
        other = self.write_brand({"palette_status": "provided", "brand_id": "other"}, "other.json")
        with self.assertRaises(ImagePlanError) as ctx:
            self.paid(brand_file=other)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-BRAND")
        self.assertIn("not the one this plan was built from", ctx.exception.detail)

    def test_a_malformed_hash_is_named(self):
        for bad in ("ABC", "0" * 63, "Z" * 64):
            with self.assertRaises(ImagePlanError) as ctx:
                self.free(brand_sha256=bad)
            self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-BRAND")

    def test_an_unbound_plan_reports_unbound_and_never_a_verified_hash(self):
        inputs, _ = self.free()
        self.assertIsNone(inputs["brand_sha256"])
        self.assertEqual(inputs["brand_record_state"], "unbound")


class PaletteStatusTests(Base):
    def test_a_brand_file_with_no_palette_status_is_unknown_and_never_paid(self):
        legacy = self.write_brand({"brand_id": "acme"}, "legacy.json")
        digest = hashlib.sha256(Path(legacy).read_bytes()).hexdigest()
        with self.assertRaises(ImagePlanError) as ctx:
            self.paid(brand_file=legacy, brand_sha256=digest)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-BRAND")
        self.assertIn("no palette status", ctx.exception.detail)
        inputs, _ = self.free(brand_file=legacy)  # a practice run may still work
        self.assertEqual(inputs["brand_palette_status"], "unknown")


class CreativeDirectionTests(Base):
    def test_an_approved_blend_supplies_the_grade_and_no_conflict_is_flagged(self):
        for mode in ("FULL", "ADAPT", "SUPPRESS"):
            inputs, to_confirm = self.free(creative_direction_kind="external_direction",
                                           creative_direction_blend=mode.lower(),
                                           creative_direction_approval_ref="appr_style")
            self.assertEqual(inputs["creative_direction_grade_mode"], mode)
            self.assertEqual(to_confirm, [], mode)

    def test_an_unapproved_blend_keeps_the_house_grade_and_is_flagged(self):
        inputs, to_confirm = self.free(creative_direction_kind="external_direction",
                                       creative_direction_blend="suppress")
        self.assertEqual(inputs["creative_direction_grade_mode"], "FULL")
        row = next(r for r in to_confirm if r["field"] == "image_plan.creative_direction")
        self.assertIn("no approval reference", row["reason"])

    def test_no_direction_is_not_asked_and_the_house_grade_stays(self):
        inputs, _ = self.free()
        self.assertEqual(inputs["creative_direction_source"], "not_asked")
        self.assertEqual(inputs["creative_direction_grade_mode"], "FULL")


if __name__ == "__main__":
    unittest.main(verbosity=2)
