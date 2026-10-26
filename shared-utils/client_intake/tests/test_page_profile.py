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
        # the offer-shape question is the one funnel word the profile deliberately keeps
        self.assertIn("funnel_shape", ids)
        self.assertIn("long-form only", profile["description"].lower())
        self.assertIn("no-images", profile["description"].lower())

    def test_page_mode_offers_only_the_profile(self):
        offered = {q["id"] for q in e.applicable(e.new_doc("page"))}
        self.assertFalse(offered - set(self.bank["profiles"]["page"]["questions"]),
                         f"page mode offers work outside the ask list: {sorted(offered - set(self.bank['profiles']['page']['questions']))}")
        for qid in ("business_outcome", "difficulty", "launch_calendar", "channels",
                    "conversation_ai", "access_delivery", "sender_name", "reply_to_email", "a2p_ready"):
            self.assertNotIn(qid, offered, f"page mode still offers launch work: {qid}")

    def test_every_unconditional_profile_question_is_offered_in_page_mode(self):
        offered = {q["id"] for q in e.applicable(e.new_doc("page"))}
        for qid in self.bank["profiles"]["page"]["questions"]:
            if self.by_id[qid]["condition"] == "always":
                self.assertIn(qid, offered, f"profile question {qid} is not offered in page mode")

    def test_a_page_run_is_never_offered_the_funnel_or_seasonal_work(self):
        offered = {q["id"] for q in e.applicable(e.new_doc("page"))}
        gated = {"funnel_length", "bump", "upsell_1", "downsell_1", "upsell_2", "downsell_2",
                 "page_set", "location", "community_truth", "entitlement",
                 "bf_promotion", "bf_limitations", "bf_buyers", "bf_followup"}
        self.assertFalse(gated & offered, f"page mode still offers funnel work: {sorted(gated & offered)}")

    def test_confirmed_answers_are_reused_never_asked_twice(self):
        profile = self.bank["profiles"]["page"]
        self.assertIn("never re-asked", profile["reuse"])
        doc = e.new_doc("page")
        e.record(doc, "business_name", "Bright Path Studio")
        e.record(doc, "audience", "New coaches")
        asked = []
        for _ in range(30):
            q = e.next_question(doc)
            if q is None or q["id"] in asked:
                break
            asked.append(q["id"])
            e.record(doc, q["id"], "x")
        self.assertGreater(len(asked), 5, f"the walk stalled at {asked}")
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
        self.assertIn("blank", q["text"].lower(), "the opt-out the text promises must be the one the engine honours")
        doc = e.new_doc("page")
        r = e.record(doc, "founder_story", "")
        self.assertTrue(r["ok"], r)
        self.assertIsNone(e.val(doc, "founder_story"), "a blank answer stays blank, never the word 'skip' in the letter")
        self.assertEqual(e.get(doc, "founder_story")["note"], "left blank on purpose")
        self.assertNotIn("founder_story", [b["id"] for b in e.check(doc)["blocking"]])

    def test_the_payment_plan_flag_is_derived_not_reasked(self):
        self.assertEqual(self.by_id["payment_plans"]["condition"], "payment_plans answered")
        self.assertIn("payment_plans", self.bank["system_fields"])
        self.assertIn("billing", self.bank["system_fields"]["payment_plans"])
        doc = e.new_doc("launch")
        e.record(doc, "billing", "Monthly")
        asked = []
        for _ in range(40):
            q = e.next_question(doc)
            if q is None or q["id"] in asked:
                break
            asked.append(q["id"])
            e.record(doc, q["id"], "x")
        self.assertNotIn("payment_plans", asked, "billing answered must derive the flag, never reopen the question")
        la = e.launch_answers(doc)
        self.assertEqual(la["launch.payment_plans"]["value"], True)
        self.assertEqual(la["launch.payment_plans"]["state"], "provided")
        self.assertEqual(la["launch.payment_plans"]["provenance"]["answer_source"], "derived-billing")
        self.assertEqual(la["launch.payment_plans"]["provenance"]["question_id"], "payment_plans")
        self.assertEqual(e.topics(doc)["payment_plans"]["state"], "answered")
        paid = e.new_doc("launch")
        e.record(paid, "billing", "All at once")
        self.assertIs(e.launch_answers(paid)["launch.payment_plans"]["value"], False)
        # a defaulted billing answer may not produce a confirmed flag
        sugg = e.new_doc("launch")
        e._set(sugg, "billing", "installment", "default_to_confirm", "safe-default", None)
        e.derive_payment_plans(sugg)
        la = e.launch_answers(sugg)
        self.assertEqual(la["launch.payment_plans"]["value"], True)
        self.assertEqual(la["launch.payment_plans"]["state"], "recommended_unapproved")

    def test_the_access_link_follows_the_delivery_choice(self):
        q = self.by_id["access_url"]
        self.assertEqual(q["condition"], "access_delivery == yes")
        doc = e.new_doc("launch")
        self.assertNotIn("access_url", [x["id"] for x in e.applicable(doc)],
                         "no access link question before the delivery answer exists")
        e.record(doc, "access_delivery", "No, nothing to deliver")
        self.assertNotIn("access_url", [x["id"] for x in e.applicable(doc)])
        e.record(doc, "access_delivery", "Yes, send access after purchase")
        self.assertIn("access_url", [x["id"] for x in e.applicable(doc)])

    def test_a_page_never_offers_no_images(self):
        self.assertNotIn("No images needed", self.by_id["image_provider"]["choices"])
        self.assertNotIn("No pictures", self.by_id["image_cap"]["choices"])
        self.assertIn("one image per copy section", self.by_id["image_cap"]["help"]["explain"])

    def test_the_engine_refuses_a_no_images_answer_too(self):
        doc = e.new_doc("page")
        for answer in ("No pictures", "none", "0"):
            r = e.record(doc, "image_cap", answer)
            self.assertFalse(r["ok"], f"image_cap accepted {answer!r}: {r}")
        for answer in ("No images needed", "none"):
            r = e.record(doc, "image_provider", answer)
            self.assertFalse(r["ok"], f"image_provider accepted {answer!r}: {r}")
        self.assertTrue(e.record(doc, "image_cap", "36")["ok"])
        self.assertTrue(e.record(doc, "image_provider", "My connected service")["ok"])

    def test_an_opt_in_page_refuses_standard_length(self):
        opt = e.new_doc("page", page_kind="opt_in")
        r = e.record(opt, "copy_profile", "Standard")
        self.assertFalse(r["ok"], r)
        r = e.record(opt, "copy_profile", "Long-form")
        self.assertTrue(r["ok"], r)
        self.assertEqual(e.val(opt, "copy_profile"), "long_form")
        defaulted = e.new_doc("page", page_kind="opt_in")
        e.apply_default(defaulted, "copy_profile")
        self.assertEqual(e.val(defaulted, "copy_profile"), "long_form",
                         "the default may not weaken the long-form rule")
        sales = e.new_doc("page", page_kind="sales")
        self.assertTrue(e.record(sales, "copy_profile", "Standard")["ok"])
        # a standard answer saved before the page kind was known blocks rather than ships
        saved = e.new_doc("page")
        e.record(saved, "copy_profile", "Standard")
        saved["meta"]["page_kind"] = "opt_in"
        self.assertIn("copy_profile", [b["id"] for b in e.check(saved)["blocking"]])

    def test_a_suggested_palette_is_never_reported_as_confirmed(self):
        doc = e.new_doc("page")
        e._set(doc, "brand_colors", ["#111111"], "suggested", "palette-help:option-1", None)
        e._set(doc, "brand_primary", "#111111", "suggested", "palette-help:option-1", None)
        r = e.roles(doc)
        self.assertEqual(r["status"], "suggested")
        self.assertFalse(r["confirmed"])
        defaulted = e.new_doc("page")
        e.apply_default(defaulted, "brand_colors")
        r = e.roles(defaulted)
        self.assertEqual(r["status"], "default_to_confirm")
        self.assertFalse(r["confirmed"])
        e._set(defaulted, "brand_colors", ["#111111"], "provided", "client", None)
        for role, value in (("primary", "#111111"), ("secondary", "#222222"), ("accent", ["#333333"]),
                            ("background", ["#FFFFFF"]), ("text", "#000000")):
            e._set(defaulted, f"brand_{role}", value, "provided", "client", None)
        r = e.roles(defaulted)
        self.assertEqual(r["status"], "provided")
        self.assertTrue(r["confirmed"])

    def test_opt_in_length_rule_is_named_with_the_length_choice(self):
        q = self.by_id["copy_profile"]
        blob = " ".join([q["text"], q["why"], q["help"]["explain"]] + list(q["choice_explanations"].values()))
        self.assertIn("opt-in", blob.lower())
        self.assertIn("long-form", blob.lower())
        self.assertIn("long-form only", blob.lower())
        self.assertIn("Standard", q["choice_explanations"])


    def test_a_defaulted_billing_answer_still_derives_the_flag(self):
        doc = e.new_doc("launch")
        e.apply_default(doc, "billing")  # records the bank's own answer text, not the stored key
        self.assertEqual(e.val(doc, "billing"), "All at once")
        e.derive_payment_plans(doc)
        la = e.launch_answers(doc)
        self.assertIs(la["launch.payment_plans"]["value"], False)
        self.assertEqual(la["launch.payment_plans"]["state"], "recommended_unapproved")
        self.assertEqual(la["launch.payment_plans"]["provenance"]["answer_source"], "derived-billing")

    def test_a_malformed_billing_value_never_crashes_the_derivation(self):
        doc = e.new_doc("launch")
        doc["answers"]["billing"] = {"value": ["Monthly"], "status": "provided", "source": "client"}
        e.derive_payment_plans(doc)  # must not raise
        self.assertNotIn("launch.payment_plans", e.launch_answers(doc))

    def test_a_client_provided_palette_is_never_labelled_a_proposal(self):
        doc = e.new_doc("page")
        e.record(doc, "brand_colors", "navy")
        e.record(doc, "brand_background", "light")
        r = e.roles(doc)
        self.assertEqual(r["status"], "provided")
        self.assertTrue(r["confirmed"])
        self.assertEqual(e.get(doc, "brand_text")["source"], "contrast rule")  # documented derivation
        self.assertNotIn("brand_text", [t["id"] for t in doc["to_confirm"]])

    def test_the_recorded_page_kind_governs_the_length_rule(self):
        doc = e.new_doc("launch")
        doc["meta"]["page_kind"] = "opt_in"  # the CLI stamps this even on a non-page mode
        self.assertFalse(e.record(doc, "copy_profile", "Standard")["ok"])
        self.assertTrue(e.record(doc, "copy_profile", "Long-form")["ok"])


class TestDocuments(unittest.TestCase):
    def setUp(self):
        self.skill = SKILL_MD.read_text(encoding="utf-8")
        self.brand = BRAND_INTAKE.read_text(encoding="utf-8")
        self.bank = e.load_bank()
        self.by_id = {q["id"]: q for q in self.bank["questions"]}

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
        self.assertIn("palette_status", self.brand)
        self.assertIn("`confirmed`", self.brand, "the doc must name the intake's own confirmed flag")

    def test_the_page_profile_and_long_form_rule_are_documented(self):
        self.assertIn("--mode page", self.skill)
        self.assertIn("--page-kind sales|opt_in", self.skill)
        self.assertIn("profiles.page", self.skill)
        self.assertIn("Long-Form only", self.skill)
        self.assertIn("ask list", self.skill, "the profile must be named as the ask list")
        profile = self.bank["profiles"]["page"]["questions"]
        self.assertIn("funnel_shape", profile, "the offer-shape question is part of the page interview")
        self.assertIn("proof", profile)
        self.assertFalse(self.by_id["proof"]["never_default"], "proof is not a never_default question")


if __name__ == "__main__":
    unittest.main(verbosity=2)
