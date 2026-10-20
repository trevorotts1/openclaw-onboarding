#!/usr/bin/env python3
"""Free proofs for the client intake engine: no network, no paid call, no model.

Run: python3 shared-utils/client_intake/tests/test_client_intake.py
"""
import importlib
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
REPO = PKG.parents[1]
sys.path.insert(0, str(PKG))
import engine as e  # noqa: E402
import palette_help as ph  # noqa: E402

BLACKCEO = json.loads((REPO / "71-blackceo-signature-page/assets/brand/blackceo-brand.json").read_text())["palette"]
FIX = PKG / "fixtures"


def answered(doc, pairs):
    for q, v in pairs:
        r = e.record(doc, q, v)
        assert r.get("ok") or r.get("action"), (q, v, r)
    return doc


class Bank(unittest.TestCase):
    def test_every_question_is_short_plain_and_helpful(self):
        bank = e.load_bank()
        ids = [q["id"] for q in bank["questions"]]
        self.assertEqual(len(ids), len(set(ids)))
        for q in bank["questions"]:
            self.assertLessEqual(len(q["choices"]), 3, q["id"])
            self.assertTrue(q["text"].strip() and q["why"].strip() and q["help"]["explain"].strip(), q["id"])
            self.assertLess(len(q["text"]), 330, q["id"])
            self.assertEqual(q["help"]["label"], "I'm not sure, help me")
            if q["never_default"]:
                self.assertIsNone(q["default"], q["id"])
            elif q["required"] != "optional":
                self.assertIsNotNone(q["default"], q["id"])
            if q["default"]:
                self.assertEqual(q["default"]["flag"], "to confirm")

    def test_never_default_list_matches_the_rules(self):
        never = {q["id"] for q in e.load_bank()["questions"] if q["never_default"]}
        for must in ("price", "offer_name", "offer_description", "representation", "community_truth", "entitlement", "paid_render_approval", "plan_approval"):
            self.assertIn(must, never)

    def test_coverage_every_required_field_has_a_question_or_a_system_reason(self):
        bank = e.load_bank()
        covered = set(bank["system_fields"])
        for q in bank["questions"]:
            covered.add(q["id"])
            covered.update(q["targets"])
            for r in q["required_by"]:
                covered.add(r.split(":", 1)[1])
        required = {}
        sys.path.insert(0, str(REPO / "49-signature-funnel/scripts"))
        vlp = importlib.import_module("validate_launch_plan")
        required["49 launch"] = set(vlp.REQUIRED_LAUNCH_FIELDS)
        sys.path.insert(0, str(REPO / "83-black-friday-launcher"))
        try:
            intake83 = importlib.import_module("launcher_core.intake")
            required["83 intake"] = set(intake83.REQUIRED_FIELDS)
        except ImportError:
            self.skipTest("Skill 83 not present in this checkout")
        wi = (REPO / "71-blackceo-signature-page/scripts/write_intake.py").read_text()
        required["71 write_intake"] = {re.match(r'"--([a-z-]+)"', c).group(1) for c in wi.split("p.add_argument(")[1:] if "required=True" in c.split("p.add_argument(")[0].split("\n    p.")[0]}
        for who, fields in required.items():
            self.assertFalse(fields - covered, f"{who} fields with no question and no system reason: {sorted(fields - covered)}")
        # every legacy and launch question id lands on a canonical question
        legacy = set()
        for q in bank["questions"]:
            legacy.update(q["legacy_ids"])
        sf = json.loads((REPO / "49-signature-funnel/intake/sf-intake-questions.json").read_text())["questions"]
        launch = json.loads((REPO / "49-signature-funnel/intake/launch-questions.json").read_text())["questions"]
        want = {x["id"] for x in sf} | {x["id"] for x in launch}
        self.assertFalse(want - legacy, f"questions with no canonical id: {sorted(want - legacy)}")


class ColourRoles(unittest.TestCase):
    def test_primary_asked_when_two_colors_have_no_roles(self):
        d = e.new_doc()
        e.record(d, "brand_colors", "#0A7E8C and #E76F51")
        q = e.next_question(d)
        self.assertEqual(q["id"], "brand_primary")
        self.assertIn("MAIN color", q["text"])
        self.assertEqual(q["choices"], ["#0A7E8C", "#E76F51"])
        e.record(d, "brand_primary", "2")
        self.assertEqual(e.val(d, "brand_primary"), "#E76F51")
        self.assertEqual(e.val(d, "brand_secondary"), "#0A7E8C")  # the one color left needs no question
        self.assertEqual(e.next_question(d)["id"], "brand_background")
        e.record(d, "brand_background", "Dark")
        self.assertEqual(e.roles(d)["roles"]["text"], "#FFFFFF")  # contrast rule picks readable text

    def test_one_color_is_primary_without_asking(self):
        d = e.new_doc()
        e.record(d, "brand_colors", "navy")
        self.assertEqual(e.val(d, "brand_primary"), "#1B2A4A")
        self.assertNotEqual(e.next_question(d)["id"], "brand_primary")

    def test_roles_in_the_answer_skip_the_questions(self):
        d = e.new_doc()
        e.record(d, "brand_colors", "primary #0A7E8C, secondary #102A43, accent #E76F51, background #FFFFFF, text #1B2A33")
        ids = [q["id"] for q in e.applicable(d)]
        self.assertFalse([i for i in ids if i.startswith("brand_") and i != "brand_colors"])
        self.assertEqual(e.roles(d)["roles"]["primary"], "#0A7E8C")

    def test_four_colors_ask_primary_secondary_then_accent(self):
        d = e.new_doc()
        e.record(d, "brand_colors", "#111111 #0A7E8C #E76F51 #F4D35E")
        order = []
        for _ in range(3):
            q = e.next_question(d)
            order.append(q["id"])
            e.record(d, q["id"], q["choices"][0])
        self.assertEqual(order, ["brand_primary", "brand_secondary", "brand_accent"])

    def test_color_name_it_cannot_read_is_asked_back_plainly(self):
        r = e.record(e.new_doc(), "brand_colors", "something sparkly")
        self.assertFalse(r["ok"])
        self.assertIn("color codes", r["message"])

    def test_unreadable_text_warning_is_plain(self):
        d = e.new_doc()
        e.record(d, "brand_colors", "primary #F4D35E, background #FFFFFF, text #F4D35E")
        self.assertTrue(any("hard to read" in w for w in e.roles(d)["warnings"]))


class NotKnowing(unittest.TestCase):
    def test_help_then_default_flagged_and_not_blocking(self):
        d = e.new_doc()
        first = e.record(d, "brand_colors", "I'm not sure, help me")
        self.assertEqual(first["action"], "help")
        self.assertEqual(len(first["palettes"]), 3)
        for p in first["palettes"]:
            self.assertTrue(p["reason"] and p["example"] and set(p["roles"]) >= {"primary", "background", "text"})
        self.assertEqual({o["id"] for o in first["options"]}, {"logo", "website", "palette"})
        second = e.record(d, "brand_colors", "not sure")
        self.assertEqual(second["action"], "default_applied")
        self.assertEqual(second["flag"], "to confirm")
        self.assertEqual(e.get(d, "brand_colors")["status"], "default_to_confirm")
        self.assertEqual(e.roles(d)["status"], "default_to_confirm")
        self.assertIn("brand_colors", [t["id"] for t in d["to_confirm"]])
        self.assertTrue(all(t["how_to_change"] for t in d["to_confirm"]))
        self.assertNotIn("brand_colors", [b["id"] for b in e.check(d)["blocking"]])

    def test_default_palette_belongs_to_no_client(self):
        taken = {v.upper() for v in BLACKCEO.values()}
        pals = [ph.safe_default()] + [ph.DEFAULTS["suggested"][i] for i in range(3)]
        for p in pals:
            r = p["roles"]
            hexes = {r["primary"], r.get("secondary"), r["text"], *r["background"], *r["accent"]}
            self.assertFalse({h.upper() for h in hexes if h} & taken, p["name"])
            self.assertEqual(ph.check_palette(r), [], p["name"])

    def test_price_unknown_stays_blocked_and_cannot_be_defaulted(self):
        d = e.new_doc()
        e.record(d, "funnel_shape", "One offer")
        for _ in range(3):
            r = e.record(d, "price", "I don't know")
            self.assertEqual(r["action"], "blocked")
        self.assertIn("price", [b["id"] for b in e.check(d)["blocking"]])
        with self.assertRaises(ValueError):
            e.apply_default(d, "price")
        with self.assertRaises(ValueError):
            e.record(d, "price", 100, status="default_to_confirm")

    def test_suggested_price_is_blocking_until_approved(self):
        d = e.new_doc()
        e.record(d, "funnel_shape", "One offer")
        e.record(d, "price", {"amount_minor": 49700, "currency": "USD", "rationale": "Similar programs charge 400 to 600."})
        self.assertEqual(e.get(d, "price")["status"], "suggested")
        self.assertIn("price", [b["id"] for b in e.check(d)["blocking"]])
        e.record(d, "price", "$497")
        self.assertNotIn("price", [b["id"] for b in e.check(d)["blocking"]])

    def test_finalize_defaults_the_rest_but_never_the_facts(self):
        d = e.new_doc()
        e.record(d, "business_name", "Maya Ortiz Studio")
        out = e.finalize(d)
        self.assertFalse(out["ready"])
        blocked = {b["id"] for b in out["blocking"]}
        self.assertTrue({"offer_name", "funnel_shape"} <= blocked)
        self.assertFalse({"brand_colors", "fonts", "logo", "design_style", "page_set", "image_cap"} & blocked)
        self.assertEqual(e.get(d, "logo")["value"], {"mode": "wordmark", "text": "Maya Ortiz Studio"})
        self.assertEqual(e.get(d, "design_style")["status"], "default_to_confirm")

    def test_style_help_recommends_from_three_words_and_waits_for_a_yes(self):
        d = e.new_doc()
        r = e.resolve_unknown(d, "design_style", mood="warm friendly playful")
        self.assertEqual(r["recommendation"], "B")
        self.assertIsNone(e.val(d, "design_style"))

    def test_logo_without_a_file_never_invents_one(self):
        d = e.new_doc()
        e.record(d, "business_name", "Bright Path")
        e.record(d, "logo", "not sure")
        e.record(d, "logo", "not sure")
        self.assertEqual(e.val(d, "logo")["mode"], "wordmark")
        e.record(d, "photos_founder", "not sure")
        e.record(d, "photos_founder", "not sure")
        self.assertEqual(e.val(d, "photos_founder"), "empty_frame")

    def test_photos_need_a_clear_permission_yes(self):
        d = e.new_doc()
        e.record(d, "photos_founder", "Yes, I will send photos")
        self.assertIn("photos_permission", [q["id"] for q in e.applicable(d)])
        e.record(d, "photos_founder", "No photos of me")
        self.assertNotIn("photos_permission", [q["id"] for q in e.applicable(d)])


class PaletteHelp(unittest.TestCase):
    def test_logo_extraction_from_a_generated_png(self):
        from PIL import Image, ImageDraw
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "logo.png"
            im = Image.new("RGBA", (200, 100), (0, 0, 0, 0))
            dr = ImageDraw.Draw(im)
            dr.rectangle([0, 0, 120, 100], fill=(10, 126, 140, 255))
            dr.rectangle([120, 0, 200, 100], fill=(231, 111, 81, 255))
            im.save(p)
            got = ph.extract_from_logo(p)
        self.assertEqual(got["source"], "logo")
        near = lambda h, rgb: all(abs(int(h[i:i + 2], 16) - c) < 16 for i, c in zip((1, 3, 5), rgb))  # noqa: E731
        self.assertTrue(any(near(h, (10, 126, 140)) for h in got["colors"]), got)
        self.assertTrue(any(near(h, (231, 111, 81)) for h in got["colors"]), got)
        self.assertFalse(any(h == "#FFFFFF" for h in got["colors"]))

    def test_logo_help_path_through_the_engine(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "l.png"
            Image.new("RGB", (40, 40), (10, 126, 140)).save(p)
            d = e.new_doc()
            r = e.resolve_unknown(d, "brand_colors", logo=str(p))
        self.assertEqual(r["action"], "confirm_colors")
        self.assertIsNone(e.val(d, "brand_colors"), "extracted colors are not recorded until the client says yes")

    def test_website_extraction_with_injected_fetch_and_no_network(self):
        pages = {"https://example.test/": '<meta name="theme-color" content="#0A7E8C"><link rel="stylesheet" href="/s.css"><div style="color:#E76F51">',
                 "https://example.test/s.css": ":root{--primary:#0A7E8C} a{color:#E76F51} .x{color:#E76F51;background:#fff;border:1px solid #cccccc}"}
        got = ph.extract_from_website("https://example.test/", fetch=lambda u: pages[u])
        self.assertEqual(got["colors"][0], "#0A7E8C")
        self.assertIn("#E76F51", got["colors"])
        self.assertNotIn("#FFFFFF", got["colors"][:2])

    def test_private_addresses_are_refused_before_any_connection(self):
        for url in ("http://127.0.0.1/", "http://localhost:8080/x", "file:///etc/passwd", "http://169.254.169.254/"):
            with self.assertRaises(ValueError):
                ph.http_fetch(url)

    def test_palettes_from_a_seed_keep_the_seed_as_primary_and_are_readable(self):
        pals = ph.suggest_palettes("#0A7E8C")
        self.assertEqual(len(pals), 3)
        for p in pals:
            self.assertEqual(p["roles"]["primary"], "#0A7E8C")
            self.assertTrue(p["reason"] and p["example"])
            self.assertFalse([w for w in p["warnings"] if "hard to read" in w])

    def test_mood_orders_the_curated_palettes(self):
        self.assertEqual(ph.suggest_palettes(None, "warm friendly")[0]["name"], "Warm and welcoming")
        self.assertEqual(len(ph.suggest_palettes()), 3)

    def test_chosen_palette_is_the_clients_own_choice(self):
        d = e.new_doc()
        r = e.resolve_unknown(d, "brand_colors", palette="2")
        self.assertEqual(r["action"], "palette_chosen")
        self.assertEqual(e.get(d, "brand_colors")["status"], "provided")
        self.assertEqual(e.get(d, "brand_colors")["source"], "palette-help:option-2")
        self.assertEqual(d["to_confirm"], [])


class AnswersFile(unittest.TestCase):
    def test_fixtures_validate_and_are_ready(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not installed")
        schema = json.loads((PKG / "answers.schema.json").read_text())
        for name in ("answers.elevation.json", "answers.7fig.json"):
            doc = json.loads((FIX / name).read_text())
            jsonschema.validate(doc, schema)
            self.assertTrue(e.check(doc)["ready"], name)
            self.assertIsNone(e.next_question(doc), name)

    def test_7fig_fixture_reports_every_default_to_confirm(self):
        doc = json.loads((FIX / "answers.7fig.json").read_text())
        ids = {t["id"] for t in doc["to_confirm"]}
        self.assertTrue({"brand_colors", "fonts", "logo"} <= ids)
        self.assertEqual(e.view(doc)["funnel_shape"], "folded_levels")
        self.assertEqual(json.loads((FIX / "answers.elevation.json").read_text())["answers"]["funnel_shape"]["value"], "multiple_options")

    def test_resume_from_a_partial_file_in_any_harness(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "answers.json"
            d = e.new_doc("launch", harness="openclaw")
            e.record(d, "business_name", "Bright Path")
            e.save(d, f)
            again = e.load(f)
            self.assertEqual(again["harness"], "openclaw")
            self.assertEqual(e.val(again, "business_name"), "Bright Path")
            self.assertEqual(e.next_question(again)["id"], "interview_mode" if e.get(again, "interview_mode") is None else "offer_name")

    def test_cli_round_trip_is_the_same_file_a_chat_harness_would_write(self):
        with tempfile.TemporaryDirectory() as td:
            f = str(Path(td) / "a.json")
            self.assertEqual(e.main([f, "record", "business_name", "Bright Path"]), 0)
            self.assertEqual(e.main([f, "check"]), 0)
            self.assertEqual(e.val(e.load(f), "business_name"), "Bright Path")

    def test_batch_groups_independent_questions_only(self):
        d = e.new_doc()
        batch = e.next_batch(d)
        self.assertTrue(1 <= len(batch) <= 4)
        self.assertEqual({q["group"] for q in batch}, {batch[0]["group"]})

    def test_launch_known_never_passes_a_default_as_approved(self):
        doc = json.loads((FIX / "answers.7fig.json").read_text())
        known = e.to_launch_known(doc)
        self.assertEqual(known["journey_mode"]["value"], "folded_levels")
        self.assertEqual([x["price"]["amount_minor"] for x in known["offers.main.packages"]["value"]], [99700, 199700, 299700])
        self.assertEqual(known["offers.main.price"]["state"], "not_applicable")  # levels carry their own prices
        self.assertEqual(known["proof"]["state"], "not_applicable")
        self.assertEqual(known["copy_profile"]["state"], "provided")
        self.assertEqual(known["image_provider"]["state"], "recommended_unapproved")


class LegacyMapping(unittest.TestCase):
    def test_legacy_answers_cover_what_the_sf_prover_requires(self):
        sys.path.insert(0, str(REPO / "49-signature-funnel/scripts"))
        psi = importlib.import_module("prove_sf_intake")
        d = e.new_doc("legacy")
        answered(d, [
            ("business_name", "Bright Path"), ("offer_name", "The Path"), ("offer_description", "A program for coaches."),
            ("audience", "New coaches"), ("offer_transformation", "Get clients."), ("pains", "a; b; c"), ("deliverables", "12 lessons; 4 calls"),
            ("founder_story", "I was broke."), ("voice", "warm, bold"), ("representation", "100% women, diverse"), ("price", "$497"),
            ("funnel_shape", "One offer"), ("billing", "All at once"), ("funnel_length", "7-step"), ("bump", "No add-on"),
            ("upsell_1", "VIP day $997"), ("downsell_1", "VIP day in 3 payments"), ("upsell_2", "Done for you $4997"), ("downsell_2", "One seat $1997"),
            ("brand_colors", "primary #0A7E8C, background #FFFFFF"), ("photos_founder", "No photos of me"),
            ("community_truth", "https://example.test/community, Bonus: planner PDF, yes I will send the text"),
            ("page_set", "all"), ("logo", "Use my business name as text"), ("fonts", "Pick good ones for me"), ("design_style", "A"),
            ("image_provider", "My connected service"), ("image_cap", "12"), ("paid_render_approval", "No paid pieces"),
            ("copy_profile", "Standard"), ("interview_mode", "I know what I want"), ("proof", "none yet"), ("style_card_id", "")])
        d["meta"]["phase"] = "approval"
        e.record(d, "plan_approval", "Approve this plan")
        self.assertIsNone(e.next_question(d))
        self.assertTrue(e.check(d)["ready"])
        brief = e.to_sf_brief_answers(d)
        missing = [k for k in psi._required_for(7) if k not in brief]
        self.assertEqual(missing, [], brief.keys())
        self.assertIn("primary #0A7E8C", brief["q7_brand_colors"])
        self.assertEqual(brief["q16_truth_gate"]["founder_text_confirmed"], True)


if __name__ == "__main__":
    unittest.main(verbosity=1)
