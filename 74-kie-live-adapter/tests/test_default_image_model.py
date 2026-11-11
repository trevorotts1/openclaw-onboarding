"""X-97: the fleet default GPT Image model is KIE.ai GPT Image 2.6 Sunburst at medium quality (rule N43).

2.6 is billed by tokens; the default carries KIE's published per-picture reference price for the quality
(references/kie-default-price-evidence.json). Free: Skill 74's Adapter runs on a fake transport.
"""
import json
import os
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

    def test_no_catalog_means_the_pin(self):
        a, tr, c = self.adapter([["GET", "/api/v1/models", [(200, {"code": 500, "msg": "down"})]]])
        self.assertEqual((a.default_model("gpt-image"), a.default_model("gpt-image", edit=True)), (S26, S26_I))


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
        self.assertEqual(a.cmd_default_price("gpt-image", quality="auto")["error"]["code"], "no_picture_price")
        self.assertEqual(a.cmd_default_price("gpt-image", quality="ultra")["error"]["code"], "bad_quality")

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


if __name__ == "__main__":
    unittest.main()
