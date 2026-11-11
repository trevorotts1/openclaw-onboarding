"""X-97: the fleet default GPT Image model is KIE.ai GPT Image 2.6 Sunburst at medium quality (rule N43).

2.6 is billed by tokens; the default carries KIE's published per-picture reference price for the quality
(references/kie-default-price-evidence.json). Free: Skill 74's Adapter runs on a fake transport.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

from test_registry_commands import Base, cat, schema, T2I, I2I
import kie_live_adapter as K

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.abspath(os.path.join(HERE, ".."))
CHECK = os.path.join(SKILL, "scripts", "check_default_image_model.py")

TOKEN = ("Text input 900 credits / 1M tokens ($4.50), cached text input 225 ($1.125), image input 1,440 ($7.20), "
         "cached image input 360 ($1.80), image output 5,400 ($27.00) — 10% below official pricing.")
TIERS = "GPT Image 2.5 — now just 6 credits ($0.03) for 1 K, 10 credits ($0.05) for 2 K, and 16 credits ($0.08) for 4 K."
S26, S26_I = "gpt-image-2-6/sunburst-text-to-image", "gpt-image-2-6/sunburst-image-to-image"
F26, F26_I = "gpt-image-2-6/flare-text-to-image", "gpt-image-2-6/flare-image-to-image"
S25, S25_I = "gpt-image-2-5-sunburst-text-to-image", "gpt-image-2-5-sunburst-image-to-image"
S27, S27_I = "gpt-image-2-7/sunburst-text-to-image", "gpt-image-2-7/sunburst-image-to-image"
A27, A27_I = "gpt-image-2-7/aurora-text-to-image", "gpt-image-2-7/aurora-image-to-image"
LIVE_2_6 = [(S26, T2I, TOKEN), (S26_I, I2I, TOKEN), (F26, T2I, TOKEN), (F26_I, I2I, TOKEN),
            (S25, T2I, TIERS), (S25_I, I2I, TIERS)]


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class Default(Base):
    def make(self, rows, **env):
        return self.adapter([["GET", "/schema", [schema(20000)]], ["GET", "/api/v1/models", [cat(*rows)]]], env=env)[0]

    def test_pin_is_the_2_6_sunburst_slash_form_never_flare(self):
        self.assertEqual((K.PINNED_DEFAULTS["Text to Image"], K.PINNED_DEFAULTS["Image to Image"]), (S26, S26_I))
        self.assertEqual(K.KNOWN_DEFAULTS["gpt-image"], S26)
        self.assertNotIn("flare", json.dumps(K.PINNED_DEFAULTS))

    def test_default_is_sunburst_not_the_newer_per_picture_2_5_nor_flare(self):
        a = self.make(LIVE_2_6)
        self.assertEqual((a.default_model("gpt-image"), a.default_model("gpt-image", edit=True)), (S26, S26_I))

    def test_a_newer_sunburst_with_a_picture_price_becomes_the_default(self):
        a = self.make(LIVE_2_6 + [(S27, T2I, "7 credits ($0.035) per image"), (S27_I, I2I, "7 credits ($0.035) per image")])
        self.assertEqual((a.default_model("gpt-image"), a.default_model("gpt-image", edit=True)), (S27, S27_I))

    def test_a_newer_token_priced_sunburst_without_a_reference_row_is_skipped(self):
        a = self.make(LIVE_2_6 + [(S27, T2I, TOKEN), (S27_I, I2I, TOKEN)])
        self.assertEqual(a.default_model("gpt-image"), S26)

    def test_a_newer_token_priced_sunburst_with_a_reference_row_is_the_default(self):
        ev = dict(K.load_price_evidence())
        ev["tables"] = ev["tables"] + [{"models": [S27, S27_I], "credits_per_picture": ev["tables"][0]["credits_per_picture"]}]
        p = os.path.join(self.tmp, "ev.json")
        with open(p, "w") as f:
            json.dump(ev, f)
        a = self.make(LIVE_2_6 + [(S27, T2I, TOKEN), (S27_I, I2I, TOKEN)])
        with mock.patch.object(K, "PRICE_EVIDENCE", p):
            self.assertEqual(a.default_model("gpt-image"), S27)

    def test_a_newer_non_sunburst_variant_is_never_the_default(self):
        a = self.make(LIVE_2_6 + [(A27, T2I, "7 credits ($0.035) per image"), (A27_I, I2I, "7 credits ($0.035) per image")])
        self.assertEqual(a.default_model("gpt-image"), S26)

    def test_a_newer_per_picture_sunburst_whose_image_to_image_schema_is_unreadable_is_skipped(self):
        # both routes must be readable: a newer generation with an unreadable edit schema leaves the 2.6 pin on both routes
        a, tr, c = self.adapter([["GET", "/models/%s/schema" % S27_I, [(200, {"code": 200, "data": {"model": "x", "openapi": None}})]],
                                 ["GET", "/schema", [schema(20000)]],
                                 ["GET", "/api/v1/models", [cat(*(LIVE_2_6 + [(S27, T2I, "7 credits ($0.035) per image"),
                                                                              (S27_I, I2I, "7 credits ($0.035) per image")]))]]])
        self.assertEqual((a.default_model("gpt-image"), a.default_model("gpt-image", edit=True)), (S26, S26_I))

    def test_no_catalog_means_the_pin(self):
        a, tr, c = self.adapter([["GET", "/api/v1/models", [(200, {"code": 500, "msg": "down"})]]])
        self.assertEqual((a.default_model("gpt-image"), a.default_model("gpt-image", edit=True)), (S26, S26_I))

    def assert_edit_route(self, a, text_id, edit_id):
        self.assertEqual((a.default_model("gpt-image"), a.default_model("gpt-image", edit=True)), (text_id, edit_id))
        self.assertIn("image-to-image", edit_id)
        self.assertNotIn("text-to-image", a.default_model("gpt-image", edit=True))
        self.assertNotIn("image-to-image", a.default_model("gpt-image", edit=False))

    # one adapter per test: the catalog is cached in the test's folder
    def test_a_source_image_gets_the_newest_sunburst_image_to_image_route_never_the_text_one(self):
        self.assert_edit_route(self.make(LIVE_2_6), S26, S26_I)

    def test_a_newer_generation_hands_a_source_image_its_own_edit_route(self):
        newer = LIVE_2_6 + [(S27, T2I, "7 credits ($0.035) per image"), (S27_I, I2I, "7 credits ($0.035) per image")]
        self.assert_edit_route(self.make(newer), S27, S27_I)

    def test_a_newer_generation_without_a_picture_price_leaves_a_source_image_the_pinned_edit_route(self):
        self.assert_edit_route(self.make(LIVE_2_6 + [(S27, T2I, TOKEN), (S27_I, I2I, TOKEN)]), S26, S26_I)

    def test_with_no_catalog_a_source_image_gets_the_pinned_image_to_image_route(self):
        a, tr, c = self.adapter([["GET", "/api/v1/models", [(200, {"code": 500, "msg": "down"})]]])
        self.assert_edit_route(a, S26, S26_I)

    def test_the_edit_route_is_looked_up_by_its_own_key_not_the_text_to_image_key(self):
        # the catalog spells the text route in lower case: only the edit route's own key may find the newer id
        rows = LIVE_2_6 + [(S27, ["text to image"], "7 credits ($0.035) per image"), (S27_I, I2I, "7 credits ($0.035) per image")]
        self.assertEqual(self.make(rows).default_model("gpt-image", edit=True), S27_I)


class DefaultPrice(Base):
    def make(self, rows=LIVE_2_6):
        return self.adapter([["GET", "/schema", [schema(20000)]], ["GET", "/api/v1/models", [cat(*rows)]]])[0]

    def test_no_quality_named_prices_medium_per_picture_for_every_size(self):
        a = self.make()
        r = a.cmd_default_price("gpt-image")
        d = r["data"]
        self.assertEqual((d["model"], d["quality"], d["unit"], d["price_note"]), (S26, "medium", "per-image", "estimate; actual billed by tokens"))
        for tier, credits in (("1", 7.82), ("2", 15.9), ("4", 26.43)):
            self.assertIn("%s credits ($%s) for %s K" % (credits, round(credits * 0.005, 6), tier), d["pricing_desc"])
        self.assertNotRegex(d["pricing_desc"], r"(?i)token")
        self.assertEqual((d["credits_min"], d["credits_max"]), (7.82, 26.43))

    def test_a_named_quality_is_never_replaced(self):
        a = self.make()
        for q, top in (("low", 14.95), ("high", 32.02), ("xhigh", 56.93), ("max", 128.08)):
            d = a.cmd_default_price("gpt-image", quality=q)["data"]
            self.assertEqual((d["quality"], d["credits_max"]), (q, top))

    def test_auto_and_unknown_qualities_have_no_picture_price(self):
        a = self.make()
        r = a.cmd_default_price("gpt-image", quality="auto")
        self.assertEqual(r["error"]["code"], "no_picture_price")
        self.assertEqual(r["error"]["msg"], "no per-picture price for %s at quality auto" % S26)  # the refusal names model and quality
        r = a.cmd_default_price("gpt-image", quality="ultra")
        self.assertEqual(r["error"]["code"], "bad_quality")
        self.assertEqual(r["error"]["msg"], "quality 'ultra' is not one of low, medium, high, xhigh, max, auto")

    def test_a_token_priced_model_without_a_reference_row_is_refused(self):
        p = os.path.join(self.tmp, "none.json")
        with open(p, "w") as f:
            json.dump({"tables": []}, f)
        a = self.make([(S26, T2I, TOKEN), (S26_I, I2I, TOKEN)])  # token-priced only: the pin, with no row
        with mock.patch.object(K, "PRICE_EVIDENCE", p):
            r = a.cmd_default_price("gpt-image")
        self.assertEqual((r["state"], r["error"]["code"]), ("fail", "no_picture_price"))

    def test_a_catalog_picture_price_is_passed_through_untouched(self):
        a = self.make([(S26, T2I, "6 credits ($0.03) per image"), (S26_I, I2I, "6 credits ($0.03) per image")])
        d = a.cmd_default_price("gpt-image", quality="high")["data"]
        self.assertEqual((d["model"], d["unit"], d["pricing_desc"]), (S26, "per-image", "6 credits ($0.03) per image"))

    def test_a_catalog_picture_price_is_scaled_by_the_requested_units(self):
        a = self.make([(S26, T2I, "6 credits ($0.03) per image"), (S26_I, I2I, "6 credits ($0.03) per image")])
        d = a.cmd_default_price("gpt-image", units=3)["data"]
        self.assertEqual((d["units"], d["credits_estimate"]), (3, 18))

    def test_edit_prices_the_image_to_image_route_and_units_scale(self):
        d = self.make().cmd_default_price("gpt-image", edit=True, units=3)["data"]
        self.assertEqual((d["model"], d["credits_estimate"]), (S26_I, round(26.43 * 3, 4)))

    def test_preflight_uses_the_picture_price_not_the_token_text(self):
        a = self.make()
        price = a.cmd_default_price("gpt-image")
        a.call = lambda *x, **y: {"data": 1000}
        r = a.cmd_preflight(S26, 1, price=price)
        self.assertEqual(r["data"]["required"], K.preflight_amount(26.43))

    def test_evidence_file_carries_the_published_table_and_quotes_the_page(self):
        ev = K.load_price_evidence()
        t = ev["tables"][0]["credits_per_picture"]
        self.assertEqual(t["medium"], {"1K": 7.82, "2K": 15.9, "4K": 26.43})
        self.assertEqual(t["low"], {"1K": 4.44, "2K": 9.0, "4K": 14.95})
        self.assertEqual(t["high"], {"1K": 9.48, "2K": 19.27, "4K": 32.02})
        self.assertEqual(t["xhigh"], {"1K": 16.86, "2K": 34.25, "4K": 56.93})
        self.assertEqual(t["max"], {"1K": 37.93, "2K": 77.07, "4K": 128.08})
        self.assertEqual((ev["adders"]["credits_per_prompt"], ev["adders"]["credits_per_reference_image"]), (0.1, 2.2))
        self.assertEqual(ev["label"], "estimate; actual billed by tokens")
        self.assertIn("Credits per Image", ev["page_text_quoted"]["title"])
        self.assertIn("billed by tokens", ev["page_text_quoted"]["subtitle"])
        self.assertEqual(ev["request_field"]["enum"], list(K.QUALITY_ENUM))
        self.assertEqual(K.QUALITY_ENUM, ("low", "medium", "high", "xhigh", "max", "auto"))


class DefaultCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import importlib.util
        spec = importlib.util.spec_from_file_location("check_default_image_model", CHECK)
        cls.C = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.C)

    def mod(self, **over):
        d = {k: getattr(K, k) for k in dir(K) if not k.startswith("__")}
        d.update(over)
        return types.SimpleNamespace(**d)

    def defects(self, ev=None, **over):
        return self.C.check(self.mod(**over), ev if ev is not None else K.load_price_evidence())

    def test_the_shipped_default_passes(self):
        r = subprocess.run([sys.executable, "-I", CHECK], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout.strip()[:2]), (0, "OK"), r.stdout + r.stderr)
        self.assertEqual(self.defects(), [])

    def test_a_flare_default_is_refused(self):
        self.assertTrue(self.defects(PINNED_DEFAULTS={"Text to Image": F26, "Image to Image": F26_I}, KNOWN_DEFAULTS={"gpt-image": F26}))

    def test_a_hyphenated_sunburst_default_is_refused(self):
        h = "gpt-image-2-6-sunburst-text-to-image"
        bad = self.defects(PINNED_DEFAULTS={"Text to Image": h, "Image to Image": S26_I}, KNOWN_DEFAULTS={"gpt-image": h})
        self.assertTrue(any("not a gpt-image Sunburst" in b for b in bad))

    def test_an_economy_default_is_refused(self):
        e = "gpt-image-2-6/economy-text-to-image"
        bad = self.defects(PINNED_DEFAULTS={"Text to Image": e, "Image to Image": S26_I}, KNOWN_DEFAULTS={"gpt-image": e})
        self.assertTrue(any("not a gpt-image Sunburst" in b for b in bad))

    def test_a_default_that_is_not_the_text_route_pin_is_refused(self):
        self.assertTrue(any("KNOWN_DEFAULTS" in b for b in self.defects(KNOWN_DEFAULTS={"gpt-image": S26_I})))

    def test_a_default_quality_other_than_medium_is_refused(self):
        self.assertTrue(any("not medium" in b for b in self.defects(DEFAULT_QUALITY="high")))

    def test_a_default_quality_outside_the_enum_is_refused(self):
        self.assertTrue(any("not in the KIE quality enum" in b for b in self.defects(DEFAULT_QUALITY="medium", QUALITY_ENUM=("low", "high"))))

    def test_a_quality_enum_that_drifted_from_the_evidence_is_refused(self):
        ev = json.loads(json.dumps(K.load_price_evidence()))
        ev["request_field"]["enum"] = ["low", "medium"]
        self.assertTrue(any("quality enum differs" in b for b in self.defects(ev)))

    def test_a_missing_size_tier_at_the_default_quality_is_refused(self):
        for tier in ("1K", "2K", "4K"):
            ev = json.loads(json.dumps(K.load_price_evidence()))
            del ev["tables"][0]["credits_per_picture"]["medium"][tier]
            bad = self.defects(ev)
            self.assertTrue(any(tier in b and "no per-picture reference price" in b for b in bad), (tier, bad))

    def test_a_zero_or_non_number_price_is_refused(self):
        for v in (0, "7.82", True, None):
            ev = json.loads(json.dumps(K.load_price_evidence()))
            ev["tables"][0]["credits_per_picture"]["medium"]["2K"] = v
            self.assertTrue(self.defects(ev), v)

    def test_an_integer_price_cell_is_a_valid_price(self):
        ev = json.loads(json.dumps(K.load_price_evidence()))
        ev["tables"][0]["credits_per_picture"]["medium"]["2K"] = 16
        self.assertEqual(self.defects(ev), [])

    def test_a_default_with_no_row_at_all_is_refused(self):
        self.assertTrue(any("no per-picture reference price" in b for b in self.defects({"tables": [], "request_field": {"enum": list(K.QUALITY_ENUM)}})))

    def test_a_row_for_only_one_of_the_two_routes_is_refused(self):
        ev = json.loads(json.dumps(K.load_price_evidence()))
        ev["tables"][0]["models"] = [S26]
        self.assertTrue(any(S26_I in b for b in self.defects(ev)))

    def test_main_fails_when_the_shipped_pin_becomes_flare(self):
        src = read(os.path.join(SKILL, "scripts", "kie_live_adapter.py"))
        self.assertIn('"Text to Image": "%s"' % S26, src)
        with tempfile.TemporaryDirectory() as d:
            sk = os.path.join(d, "74-kie-live-adapter")
            os.makedirs(os.path.join(sk, "scripts"))
            os.makedirs(os.path.join(sk, "references"))
            for rel in ("scripts/kie_live_adapter.py", "scripts/check_default_image_model.py",
                        "references/kie-default-price-evidence.json"):
                body = read(os.path.join(SKILL, rel))
                if rel.endswith("adapter.py"):
                    body = body.replace('"Text to Image": "%s"' % S26, '"Text to Image": "%s"' % F26)
                with open(os.path.join(sk, rel), "w", encoding="utf-8") as f:
                    f.write(body)
            r = subprocess.run([sys.executable, "-I", os.path.join(sk, "scripts", "check_default_image_model.py")],
                               capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("not a gpt-image Sunburst", r.stdout)


PER_JOB = "12 credits ($0.06) per job"
QC = os.path.join(SKILL, "qc-74-kie-live-adapter.sh")
WORKFLOW = os.path.abspath(os.path.join(SKILL, "..", ".github", "workflows", "version-consistency.yml"))
CHECK_REL = os.path.join("scripts", "check_default_image_model.py")
SKILL_FILES = ("scripts/kie_live_adapter.py", "scripts/check_default_image_model.py", "references/kie-default-price-evidence.json")


def copy_skill(dest, edit=None, drop=()):
    """The check script, the adapter and the evidence file copied under dest; edit maps a rel path to a text edit."""
    for rel in SKILL_FILES:
        if rel in drop:
            continue
        body = read(os.path.join(SKILL, rel))
        if edit and rel in edit:
            body = edit[rel](body)
        os.makedirs(os.path.dirname(os.path.join(dest, rel)), exist_ok=True)
        with open(os.path.join(dest, rel), "w", encoding="utf-8") as f:
            f.write(body)
    return dest


class PriceEvidenceGrid(unittest.TestCase):
    def test_every_cell_is_the_pages_own_token_arithmetic(self):
        ev = K.load_price_evidence()
        t = ev["tables"][0]
        self.assertEqual(ev["image_output_credits_per_million_tokens"], 5400)
        self.assertEqual(sorted(t["credits_per_picture"]), sorted(K.QUALITY_ENUM[:-1]))
        for q, tiers in t["credits_per_picture"].items():
            self.assertEqual(sorted(tiers), ["1K", "2K", "4K"], q)
            for tier, credits in tiers.items():
                tokens = t["tokens_per_picture"][q][tier]
                self.assertEqual(round(tokens * ev["image_output_credits_per_million_tokens"] / 1000000 + 1e-12, 2), credits, (q, tier))

    def test_the_evidence_cites_the_owner_paste_and_the_page_text(self):
        ev = K.load_price_evidence()
        self.assertIn("pasted by the owner 2026-11-10", ev["source"])
        self.assertIn("KIE-GPT-IMAGE-2-6-PRICE-PASTE-2026-11-10", ev["source"])
        self.assertIn("token counts per cell", ev["source"])
        self.assertEqual((ev["request_field"]["default"], ev["aspect_ratio"]), ("medium", "1:1"))
        self.assertIn("Add \u2248 0.1 credits for the prompt and \u2248 2.2 credits per reference image", ev["page_text_quoted"]["foot"])
        self.assertIn("1 credit = $0.005", ev["page_text_quoted"]["foot"])


class LoadPriceEvidence(Base):
    def write(self, text):
        p = os.path.join(self.tmp, "ev.json")
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def test_a_missing_file_gives_nothing_and_strict_names_it(self):
        gone = os.path.join(self.tmp, "gone.json")
        self.assertEqual(K.load_price_evidence(gone), {})
        with self.assertRaises(ValueError) as c:
            K.load_price_evidence(gone, strict=True)
        self.assertIn("gone.json is unusable", str(c.exception))

    def test_a_folder_instead_of_a_file_is_unreadable(self):
        self.assertEqual(K.load_price_evidence(self.tmp), {})
        with self.assertRaises(ValueError):
            K.load_price_evidence(self.tmp, strict=True)

    def test_json_that_is_not_an_object_gives_nothing_and_strict_says_so(self):
        for text in ("[]", '"x"', "7", "null"):
            p = self.write(text)
            self.assertEqual(K.load_price_evidence(p), {}, text)
            with self.assertRaises(ValueError) as c:
                K.load_price_evidence(p, strict=True)
            self.assertIn("not a JSON object", str(c.exception))

    def test_broken_json_gives_nothing_and_strict_says_so(self):
        p = self.write("{not json")
        self.assertEqual(K.load_price_evidence(p), {})
        with self.assertRaises(ValueError) as c:
            K.load_price_evidence(p, strict=True)
        self.assertIn("ev.json is unusable", str(c.exception))

    def test_the_shipped_file_loads_strictly(self):
        self.assertEqual(K.load_price_evidence(strict=True), K.load_price_evidence())

    def test_with_missing_or_broken_evidence_a_newer_per_picture_sunburst_is_still_the_default(self):
        a = self.make_newer()
        for text in (None, "{not json"):
            p = self.write(text) if text else os.path.join(self.tmp, "gone.json")
            with mock.patch.object(K, "PRICE_EVIDENCE", p):
                self.assertEqual((a.default_model("gpt-image"), a.default_model("gpt-image", edit=True)), (S27, S27_I), text)

    def make_newer(self):
        rows = LIVE_2_6 + [(S27, T2I, "7 credits ($0.035) per image"), (S27_I, I2I, "7 credits ($0.035) per image")]
        return self.adapter([["GET", "/schema", [schema(20000)]], ["GET", "/api/v1/models", [cat(*rows)]]])[0]

    def test_with_no_evidence_a_token_priced_default_is_refused_not_guessed(self):
        a = self.adapter([["GET", "/schema", [schema(20000)]], ["GET", "/api/v1/models", [cat((S26, T2I, TOKEN), (S26_I, I2I, TOKEN))]]])[0]
        for text in (None, "[]"):
            p = os.path.join(self.tmp, "ev.json") if text else os.path.join(self.tmp, "gone.json")
            if text:
                self.write(text)
            with mock.patch.object(K, "PRICE_EVIDENCE", p):
                r = a.cmd_default_price("gpt-image")
            self.assertEqual((r["state"], r["error"]["code"]), ("fail", "no_picture_price"), text)


class PictureUnits(Base):
    def make(self, rows):
        return self.adapter([["GET", "/schema", [schema(20000)]], ["GET", "/api/v1/models", [cat(*rows)]]])[0]

    def test_a_per_job_catalog_price_is_a_picture_price(self):
        self.assertEqual(K.PICTURE_PRICE_UNITS, ("per-image", "per-job"))
        self.assertEqual(K.parse_pricing(PER_JOB)["unit"], "per-job")
        self.assertTrue(K.is_picture_priced(PER_JOB))
        self.assertTrue(K.is_picture_priced("6 credits ($0.03) per image"))
        self.assertFalse(K.is_picture_priced(TOKEN))

    def test_a_newer_sunburst_priced_per_job_becomes_the_default_and_passes_through(self):
        a = self.make(LIVE_2_6 + [(S27, T2I, PER_JOB), (S27_I, I2I, PER_JOB)])
        self.assertEqual(a.default_model("gpt-image"), S27)
        d = a.cmd_default_price("gpt-image")["data"]
        self.assertEqual((d["model"], d["unit"], d["pricing_desc"], d["quality"]), (S27, "per-job", PER_JOB, "medium"))

    def test_a_different_family_is_never_the_gpt_image_default(self):
        other, other_i = "seedream-9/sunburst-text-to-image", "seedream-9/sunburst-image-to-image"
        a = self.make(LIVE_2_6 + [(other, T2I, "7 credits ($0.035) per image"), (other_i, I2I, "7 credits ($0.035) per image")])
        self.assertEqual(a.default_model("gpt-image"), S26)


class DefaultPriceAnswer(Base):
    def make(self, rows=LIVE_2_6):
        return self.adapter([["GET", "/schema", [schema(20000)]], ["GET", "/api/v1/models", [cat(*rows)]]])[0]

    def evidence(self, mutate):
        ev = json.loads(json.dumps(K.load_price_evidence()))
        mutate(ev)
        p = os.path.join(self.tmp, "ev.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(ev, f)
        return p

    def test_the_reference_answer_names_the_model_and_carries_the_estimate_label(self):
        r = self.make().cmd_default_price("gpt-image")
        self.assertEqual((r["state"], r["model_id"], r["schema_source"]), ("success", S26, "reference-evidence"))
        self.assertEqual(r["warnings"], ["estimate; actual billed by tokens"])
        self.assertEqual(self.make().cmd_default_price("gpt-image", edit=True)["model_id"], S26_I)

    def test_the_reference_answer_carries_the_adders_and_the_source(self):
        d = self.make().cmd_default_price("gpt-image")["data"]
        self.assertEqual(d["adders"]["credits_per_prompt"], 0.1)
        self.assertEqual(d["adders"]["credits_per_reference_image"], 2.2)
        self.assertEqual((d["price_source"], d["units"]), ("reference-evidence", 1))

    def test_the_reference_answer_echoes_the_requested_units_and_totals_that_many_pictures(self):
        one = self.make().cmd_default_price("gpt-image")["data"]["credits_estimate"]
        self.assertEqual(one, 26.43)
        for units in (2, 3, 5):
            d = self.make().cmd_default_price("gpt-image", units=units)["data"]
            self.assertEqual((d["units"], d["credits_estimate"]), (units, round(one * units, 4)))
            self.assertEqual(d["preflight_required"], K.preflight_amount(round(one * units, 4)))
        self.assertEqual(self.make().cmd_default_price("gpt-image", units=3)["data"]["credits_estimate"], 79.29)
        self.assertEqual(self.make().cmd_default_price("gpt-image", edit=True, units=3)["data"]["units"], 3)

    def test_the_reference_answer_is_preflighted_with_the_conservative_multiplier(self):
        d = self.make().cmd_default_price("gpt-image", quality="max", units=2)["data"]
        self.assertEqual(d["preflight_multiplier"], 1.3)
        self.assertEqual(d["credits_estimate"], 256.16)
        self.assertEqual(d["preflight_required"], K.preflight_amount(256.16))
        self.assertEqual(d["preflight_required"], 333.01)

    def test_tiers_are_listed_smallest_first_whatever_the_file_order(self):
        def shuffle(ev):
            m = ev["tables"][0]["credits_per_picture"]["medium"]
            ev["tables"][0]["credits_per_picture"]["medium"] = {"4K": m["4K"], "1K": m["1K"], "2K": m["2K"]}
        with mock.patch.object(K, "PRICE_EVIDENCE", self.evidence(shuffle)):
            d = self.make().cmd_default_price("gpt-image")["data"]
        desc = d["pricing_desc"]
        self.assertLess(desc.index("for 1 K"), desc.index("for 2 K"))
        self.assertLess(desc.index("for 2 K"), desc.index("for 4 K"))
        self.assertEqual((d["credits_min"], d["credits_max"], d["credits_estimate"]), (7.82, 26.43, 26.43))
        self.assertEqual(d["preflight_required"], K.preflight_amount(26.43))

    def test_a_file_without_a_dollar_rate_uses_half_a_cent_per_credit(self):
        with mock.patch.object(K, "PRICE_EVIDENCE", self.evidence(lambda ev: ev.pop("usd_per_credit"))):
            desc = self.make().cmd_default_price("gpt-image")["data"]["pricing_desc"]
        self.assertIn("7.82 credits ($0.0391) for 1 K", desc)

    def test_a_file_without_a_label_still_answers(self):
        with mock.patch.object(K, "PRICE_EVIDENCE", self.evidence(lambda ev: ev.pop("label"))):
            r = self.make().cmd_default_price("gpt-image")
        self.assertEqual((r["state"], r["warnings"]), ("success", [""]))

    def test_a_blank_quality_is_not_a_named_quality_so_medium_applies(self):
        a = self.make()
        for blank in ("", " ", "  \t"):
            d = a.cmd_default_price("gpt-image", quality=blank)["data"]
            self.assertEqual((d["quality"], d["credits_max"]), ("medium", 26.43), repr(blank))
        self.assertEqual(a.cmd_default_price("gpt-image", quality=0)["error"]["code"], "bad_quality")

    def test_when_the_catalog_cannot_price_the_default_the_reference_row_answers(self):
        a, tr, c = self.adapter([["GET", "/api/v1/models", [(200, {"code": 500, "msg": "down"})]]])
        r = a.cmd_default_price("gpt-image")
        self.assertEqual((r["state"], r["data"]["price_source"], r["data"]["credits_max"]), ("success", "reference-evidence", 26.43))


class DefaultCheckCannotRun(unittest.TestCase):
    def run_check(self, **kw):
        with tempfile.TemporaryDirectory() as d:
            copy_skill(d, **kw)
            return subprocess.run([sys.executable, "-I", os.path.join(d, CHECK_REL)], capture_output=True, text=True)

    def assert_could_not_run(self, r):
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("check_default_image_model: could not run: ", r.stdout)
        self.assertRegex(r.stdout, r"could not run: \w+: \S")  # the failure is named by its kind and message
        self.assertNotIn("OK", r.stdout)

    def test_missing_evidence_exits_2(self):
        self.assert_could_not_run(self.run_check(drop=("references/kie-default-price-evidence.json",)))

    def test_evidence_that_is_not_an_object_exits_2(self):
        self.assert_could_not_run(self.run_check(edit={"references/kie-default-price-evidence.json": lambda b: "[]"}))

    def test_evidence_that_is_not_json_exits_2(self):
        self.assert_could_not_run(self.run_check(edit={"references/kie-default-price-evidence.json": lambda b: "{oops"}))

    def test_an_adapter_that_fails_to_import_exits_2(self):
        self.assert_could_not_run(self.run_check(edit={"scripts/kie_live_adapter.py": lambda b: "import module_that_is_not_there\n" + b}))

    def test_an_adapter_with_a_syntax_error_exits_2(self):
        self.assert_could_not_run(self.run_check(edit={"scripts/kie_live_adapter.py": lambda b: "def (:\n" + b}))

    def test_unreadable_evidence_exits_2(self):
        # open() refuses the evidence file with a PermissionError. Patched in the child rather than chmod 0, so the
        # answer is the same for every user (root reads any file) and nothing here needs a skip.
        deny = ("import builtins, runpy, sys\n"
                "real = builtins.open\n"
                "def deny(f, *a, **k):\n"
                "    if str(f).endswith('kie-default-price-evidence.json'):\n"
                "        raise PermissionError(13, 'Permission denied')\n"
                "    return real(f, *a, **k)\n"
                "builtins.open = deny\n"
                "runpy.run_path(sys.argv[1], run_name='__main__')\n")
        with tempfile.TemporaryDirectory() as d:
            copy_skill(d)
            r = subprocess.run([sys.executable, "-I", "-c", deny, os.path.join(d, CHECK_REL)], capture_output=True, text=True)
        self.assert_could_not_run(r)
        self.assertIn("Permission denied", r.stdout)

    def test_a_defect_exits_1_and_never_prints_ok(self):
        r = self.run_check(edit={"scripts/kie_live_adapter.py": lambda b: b.replace('DEFAULT_QUALITY = "medium"', 'DEFAULT_QUALITY = "high"', 1)})
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("DEFECT: default quality is 'high', not medium", r.stdout)
        self.assertNotIn("OK", r.stdout)


class DefaultCheckIsWired(unittest.TestCase):
    """The qc script and the CI step must fail on any non-zero exit from the check script."""

    def qc_line(self, d):
        with open(QC, encoding="utf-8") as f:
            lines = f.read().splitlines()
        defs = [l for l in lines if l.startswith(("PASS=0", "ok()", "bad()", "chk()"))]
        mine = [l for l in lines if l.startswith("chk ") and "check_default_image_model.py" in l]
        self.assertEqual((len(defs), len(mine)), (4, 1), (defs, mine))
        script = "D=%s\n%s\n%s\necho \"PASS=$PASS FAIL=$FAIL\"\n" % (shlex.quote(d), "\n".join(defs), mine[0])
        return subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True).stdout

    def test_the_qc_line_passes_a_healthy_check(self):
        with tempfile.TemporaryDirectory() as d:
            copy_skill(d)
            out = self.qc_line(d)
        self.assertIn("  PASS - default image model is priced per picture (X-97)", out)
        self.assertIn("PASS=1 FAIL=0", out)

    def test_the_qc_line_fails_on_exit_1_a_defect(self):
        with tempfile.TemporaryDirectory() as d:
            copy_skill(d, edit={"scripts/kie_live_adapter.py": lambda b: b.replace('DEFAULT_QUALITY = "medium"', 'DEFAULT_QUALITY = "high"', 1)})
            out = self.qc_line(d)
        self.assertIn("  FAIL - default image model is priced per picture (X-97)", out)
        self.assertIn("PASS=0 FAIL=1", out)

    def test_the_qc_line_fails_on_exit_2_could_not_run(self):
        with tempfile.TemporaryDirectory() as d:
            copy_skill(d, drop=("references/kie-default-price-evidence.json",))
            out = self.qc_line(d)
        self.assertIn("  FAIL - default image model is priced per picture (X-97)", out)
        self.assertIn("PASS=0 FAIL=1", out)

    def present_loop(self):
        """The qc script's `for f in <files>; do chk "present: $f" ...; done` block: (files, whole block)."""
        text = read(QC)
        m = re.search(r"^for f in (.*?); do\n(.*?)\ndone$", text, re.S | re.M)
        self.assertIsNotNone(m)
        self.assertIn('chk "present: $f"', m.group(2))
        return m.group(1).replace("\\\n", " ").split(), m.group(0)

    def test_the_qc_present_list_names_the_check_script_and_the_evidence_file(self):
        files, _ = self.present_loop()
        for rel in ("scripts/check_default_image_model.py", "references/kie-default-price-evidence.json", "tests/test_default_image_model.py"):
            self.assertIn(rel, files)

    def test_the_qc_present_loop_fails_when_the_check_script_or_the_evidence_is_missing(self):
        files, block = self.present_loop()
        defs = [l for l in read(QC).splitlines() if l.startswith(("PASS=0", "ok()", "bad()", "chk()"))]

        def run(drop):
            with tempfile.TemporaryDirectory() as d:
                for rel in files:
                    if rel != drop:
                        os.makedirs(os.path.dirname(os.path.join(d, rel)), exist_ok=True)
                        open(os.path.join(d, rel), "w").close()
                script = "D=%s\n%s\n%s\necho \"PASS=$PASS FAIL=$FAIL\"\n" % (shlex.quote(d), "\n".join(defs), block)
                return subprocess.run(["/bin/bash", "-c", script], capture_output=True, text=True).stdout

        self.assertIn("FAIL=0", run(None))
        for rel in ("scripts/check_default_image_model.py", "references/kie-default-price-evidence.json"):
            out = run(rel)
            self.assertIn("  FAIL - present: %s" % rel, out)
            self.assertIn("FAIL=1", out)

    def test_the_ci_step_runs_the_check_and_lets_any_non_zero_exit_fail_the_job(self):
        if not os.path.exists(WORKFLOW):
            # An installed skill has no repository around it, so there is no CI step to read there; what that step
            # would run must still ship with the skill.
            self.assertTrue(os.path.isfile(CHECK), CHECK)
            return
        lines = read(WORKFLOW).splitlines()
        runs = [i for i, l in enumerate(lines) if "check_default_image_model.py" in l and l.strip().startswith("run:")]
        self.assertEqual(len(runs), 1, runs)
        self.assertEqual(lines[runs[0]].strip(), "run: python3 -I 74-kie-live-adapter/scripts/check_default_image_model.py")
        start = max(i for i in range(runs[0]) if lines[i].lstrip().startswith("- name:"))
        stop = min([i for i in range(runs[0] + 1, len(lines)) if lines[i].lstrip().startswith("- name:") or (lines[i] and not lines[i].startswith(" "))] or [len(lines)])
        step = "\n".join(lines[start:stop])
        for weak in ("continue-on-error", "|| true", "|| :", "set +e", "if:"):
            self.assertNotIn(weak, step)
        self.assertIn("shell: bash", step)
        job = [l for l in lines[:start] if l.startswith("  ") and not l.startswith("   ") and l.rstrip().endswith(":")][-1]
        self.assertNotIn("continue-on-error", "\n".join(lines[lines.index(job):start]))


if __name__ == "__main__":
    unittest.main()
