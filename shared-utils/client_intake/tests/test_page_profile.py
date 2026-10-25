#!/usr/bin/env python3
"""Page-only intake profile, colour policy and choice filtering (findings 18, 19, 23, 46).

Run: python3 shared-utils/client_intake/tests/test_page_profile.py
"""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
REPO = PKG.parents[1]
sys.path.insert(0, str(PKG))
import engine as e  # noqa: E402

SKILL_MD = REPO / "71-blackceo-signature-page/SKILL.md"
BRAND_INTAKE = REPO / "71-blackceo-signature-page/references/brand-intake.md"

FUNNEL_ONLY = {
    "funnel_length", "bump", "upsell_1", "downsell_1", "upsell_2", "downsell_2",
    "page_set", "channels", "conversation_ai", "a2p_ready", "sender_name",
    "reply_to_email", "launch_calendar", "location", "community_truth",
    "entitlement", "plan_approval", "bf_promotion", "bf_limitations",
    "bf_buyers", "bf_followup",
}
PAGE_NEEDS = {
    "interview_mode", "business_name", "offer_name", "offer_description",
    "audience", "offer_transformation", "pains", "deliverables", "proof",
    "voice", "founder_story", "funnel_shape", "price", "billing",
    "brand_colors", "logo", "fonts", "photos_founder", "design_style",
    "image_provider", "image_cap", "paid_render_approval", "copy_profile",
}


class TestBank(unittest.TestCase):
    def setUp(self):
        self.bank = e.load_bank()
        self.by_id = {q["id"]: q for q in self.bank["questions"]}

    def test_a_page_mode_and_a_page_profile_are_declared(self):
        self.assertIn("page", self.bank["modes"])
        profile = self.bank["profiles"]["page"]
        self.assertEqual(profile["skills"], [71])
        ids = profile["questions"]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertFalse(set(ids) - set(self.by_id), "profile names unknown questions")
        self.assertFalse(FUNNEL_ONLY & set(ids), "page profile still asks funnel work")
        self.assertFalse(PAGE_NEEDS - set(ids), "page profile is missing a page question")

    def test_confirmed_answers_are_reused_never_asked_twice(self):
        profile = self.bank["profiles"]["page"]
        self.assertIn("never re-asked", profile["reuse"])
        doc = e.new_doc("page")
        e.record(doc, "business_name", "Bright Path Studio")
        e.record(doc, "audience", "New coaches")
        asked = []
        for _ in range(3):
            q = e.next_question(doc)
            if q is None:
                break
            asked.append(q["id"])
            break
        self.assertNotIn("business_name", asked)
        self.assertNotIn("audience", asked)

    def test_one_audience_group_is_enough(self):
        text = self.by_id["audience"]["text"]
        self.assertNotIn("3 to 6", text)
        self.assertIn("at least one", text)

    def test_founder_context_is_optional_and_never_a_forced_low_point(self):
        q = self.by_id["founder_story"]
        self.assertEqual(q["required"], "optional")
        self.assertNotIn("low moment", q["text"].lower())
        self.assertIn("skip", q["text"].lower())

    def test_the_payment_plan_flag_is_derived_not_reasked(self):
        self.assertEqual(self.by_id["payment_plans"]["condition"], "payment_plans answered")
        asked = [q["id"] for q in e.applicable(e.new_doc("launch"))]
        self.assertNotIn("payment_plans", asked)
        self.assertIn("payment_plans", self.bank["system_fields"])

    def test_the_access_link_follows_the_delivery_choice(self):
        q = self.by_id["access_url"]
        self.assertEqual(q["condition"], "access_delivery == yes")
        doc = e.new_doc("launch")
        e.record(doc, "access_delivery", "No, nothing to deliver")
        self.assertNotIn("access_url", [x["id"] for x in e.applicable(doc)])
        e.record(doc, "access_delivery", "Yes, send access after purchase")
        self.assertIn("access_url", [x["id"] for x in e.applicable(doc)])

    def test_a_page_never_offers_no_images(self):
        self.assertNotIn("No images needed", self.by_id["image_provider"]["choices"])
        self.assertNotIn("No pictures", self.by_id["image_cap"]["choices"])
        self.assertIn("one image per copy section", self.by_id["image_cap"]["help"]["explain"])

    def test_opt_in_length_rule_is_named_with_the_length_choice(self):
        q = self.by_id["copy_profile"]
        blob = " ".join([q["text"], q["why"], q["help"]["explain"]] + list(q["choice_explanations"].values()))
        self.assertIn("opt-in", blob.lower())
        self.assertIn("long-form", blob.lower())
        self.assertIn("long-form only", blob.lower())
        self.assertIn("Standard", q["choice_explanations"])


class TestDocuments(unittest.TestCase):
    def setUp(self):
        self.skill = SKILL_MD.read_text(encoding="utf-8")
        self.brand = BRAND_INTAKE.read_text(encoding="utf-8")

    def test_colour_default_is_permitted_and_labelled_a_proposal(self):
        # the absolute ban is gone from SKILL.md ...
        self.assertNotIn("No default or other client's palette is ever used", self.skill)
        for doc in (self.skill, self.brand):
            self.assertIn("default_to_confirm", doc)
            self.assertIn("proposal", doc.lower())
            self.assertIn("confirm", doc.lower())
        # ... and both name the one restriction that survives: it cannot ship
        self.assertIn("may not ship", self.skill)
        self.assertIn("may not ship", self.brand)

    def test_the_page_profile_and_long_form_rule_are_documented(self):
        self.assertIn("--mode page", self.skill)
        self.assertIn("profiles.page", self.skill)
        self.assertIn("Long-Form only", self.skill)


if __name__ == "__main__":
    unittest.main(verbosity=2)
