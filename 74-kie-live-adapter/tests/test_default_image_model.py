"""X-97: the fleet default GPT Image model is the newest one priced PER PICTURE, never per token.

Price texts below are copied from KIE's live catalog (fetched 2026-11-10): the 2.6 sunburst and
flare variants are priced per 1M tokens, the 2.6 economy variant per picture.
"""
import importlib.util
import json
import os
import subprocess
import sys
import unittest

from test_registry_commands import Base, cat, schema, T2I, I2I, G25S, G25S_I  # noqa: F401
import kie_live_adapter as K

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.abspath(os.path.join(HERE, ".."))
CHECK = os.path.join(SKILL, "scripts", "check_default_image_model.py")

TOKEN = ("Text input 900 credits / 1M tokens ($4.50), cached text input 225 ($1.125), image input 1,440 ($7.20), "
         "cached image input 360 ($1.80), image output 5,400 ($27.00) — 10% below official pricing.")
ECON = ("GPT Image 2.6 (Economy) — just 5 credits ($0.025) per 1K image. Same GPT Image 2.6 model, served through "
        "our economy channel at a flat per-image price, 1K only.")
TIERS = "GPT Image 2.5 — now just 6 credits ($0.03) for 1 K, 10 credits ($0.05) for 2 K, and 16 credits ($0.08) for 4 K."
S26, S26_I = "gpt-image-2-6/sunburst-text-to-image", "gpt-image-2-6/sunburst-image-to-image"
E26, E26_I = "gpt-image-2-6/economy-text-to-image", "gpt-image-2-6/economy-image-to-image"
S25, S25_I = "gpt-image-2-5-sunburst-text-to-image", "gpt-image-2-5-sunburst-image-to-image"
S27, S27_I = "gpt-image-2-7/aurora-text-to-image", "gpt-image-2-7/aurora-image-to-image"

def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


LIVE_2_6 = [(S26, T2I, TOKEN), (S26_I, I2I, TOKEN), (E26, T2I, ECON), (E26_I, I2I, ECON),
            (S25, T2I, TIERS), (S25_I, I2I, TIERS)]


class PerPictureDefault(Base):
    def routes(self, rows):
        return [["GET", "/schema", [schema(20000)]],
                ["GET", "/api/v1/models", [cat(*rows)]]]

    def latest(self, rows, resolution=None, **env):
        a, tr, c = self.adapter(self.routes(rows), env=env)
        return a, a.cmd_latest_family("gpt-image", resolution=resolution)

    def test_pinned_fallback_is_gpt_image_2_6_economy(self):
        self.assertEqual(K.KNOWN_DEFAULTS["gpt-image"], E26)

    def test_token_priced_2_6_is_skipped_for_the_per_picture_2_6(self):
        a, r = self.latest(LIVE_2_6)
        d = r["data"]
        self.assertEqual((d["default"], d["version"], d["routes"]["Image to Image"]), (E26, [2, 6], E26_I))
        self.assertNotIn(S26, json.dumps(d["candidates"]))

    def test_a_newer_per_picture_generation_becomes_the_default(self):
        rows = LIVE_2_6 + [(S27, T2I, "7 credits ($0.035) per image"), (S27_I, I2I, "7 credits ($0.035) per image")]
        self.assertEqual(self.latest(rows)[1]["data"]["default"], S27)

    def test_a_newer_token_priced_generation_is_never_the_default(self):
        rows = LIVE_2_6 + [(S27, T2I, TOKEN), (S27_I, I2I, TOKEN)]
        self.assertEqual(self.latest(rows)[1]["data"]["default"], E26)

    def test_registry_fallback_also_drops_token_priced_models(self):
        def row(i, tt, raw):
            return {"id": i, "taskType": tt, "schema": {"readable": True}, "pricing": {"raw": raw}}
        reg = self.write_registry([row(S26, T2I, TOKEN), row(S26_I, I2I, TOKEN), row(S25, T2I, TIERS), row(S25_I, I2I, TIERS)])
        a, tr, c = self.adapter([["GET", "/api/v1/models", [(200, {"code": 500, "msg": "down"})]]], env={"KIE_LIVE_REGISTRY": reg})
        r = a.cmd_latest_family("gpt-image")
        self.assertEqual((r["data"]["default"], r["data"]["source"]), (S25, "registry"))

    def test_only_token_priced_models_means_no_resolved_default(self):
        a, r = self.latest([(S26, T2I, TOKEN), (S26_I, I2I, TOKEN)])
        self.assertEqual(r["error"]["code"], "latest_unavailable")

    def test_default_model_resolves_then_falls_back_to_the_pin(self):
        a, _ = self.latest(LIVE_2_6 + [(S27, T2I, "7 credits"), (S27_I, I2I, "7 credits")])
        self.assertEqual(a.default_model("gpt-image"), S27)
        a, tr, c = self.adapter([["GET", "/api/v1/models", [(200, {"code": 500, "msg": "down"})]]],
                                env={"KIE_LIVE_CACHE_DIR": os.path.join(self.tmp, "c4")})
        self.assertEqual(a.default_model("gpt-image"), E26)  # no catalog, no registry: the pin
        a, _ = self.latest([(S26, T2I, TOKEN), (S26_I, I2I, TOKEN)], KIE_LIVE_CACHE_DIR=os.path.join(self.tmp, "c5"))
        self.assertEqual(a.default_model("gpt-image"), E26)  # token-only catalog: the pin, never a token model

    # ---- ruling X-97-1: a named tier the default does not publish moves to the newest per-picture model that does
    def test_a_named_tier_resolves_to_the_newest_per_picture_model_that_publishes_it(self):
        a, r = self.latest(LIVE_2_6, resolution="1K")
        self.assertEqual(a.default_model("gpt-image", "1K"), E26)
        self.assertEqual(a.default_model("gpt-image", "2K"), S25)
        self.assertEqual(a.default_model("gpt-image", "4K"), S25)
        self.assertEqual(a.default_model("gpt-image"), E26)  # no tier named: the plain default

    def test_a_tier_no_per_picture_model_publishes_has_no_default(self):
        a, r = self.latest(LIVE_2_6)
        self.assertIsNone(a.default_model("gpt-image", "8K"))
        a, r = self.latest([(S26, T2I, TOKEN), (S26_I, I2I, TOKEN), (E26, T2I, ECON), (E26_I, I2I, ECON)],
                           KIE_LIVE_CACHE_DIR=os.path.join(self.tmp, "c6"))
        self.assertIsNone(a.default_model("gpt-image", "2K"))  # only token-priced models publish 2K here: refused, not pinned

    def test_when_no_schema_is_readable_the_pin_answers_only_for_a_tier_it_publishes(self):
        rows = [(E26, T2I, TIERS), (E26_I, I2I, TIERS)]  # pin shows per-picture tiers 1K, 2K, 4K in the catalog
        a, tr, c = self.adapter([["GET", "/api/v1/models", [cat(*rows)]]])  # no schema routes: nothing readable
        self.assertEqual(a.default_model("gpt-image", "2K"), E26)
        self.assertIsNone(a.default_model("gpt-image", "8K"))
        a, tr, c = self.adapter([["GET", "/api/v1/models", [cat((E26, T2I, ECON), (E26_I, I2I, ECON))]]],
                                env={"KIE_LIVE_CACHE_DIR": os.path.join(self.tmp, "c7")})
        self.assertIsNone(a.default_model("gpt-image", "2K"))  # the pin is 1K only: no pin, no 1K price for a 2K ask

    def test_a_tier_answer_never_moves_the_family_default_state(self):
        a, r = self.latest(LIVE_2_6)
        a.default_model("gpt-image", "4K")
        self.assertEqual(a.cmd_latest_family("gpt-image", refresh=True)["data"]["default"], E26)
        self.assertFalse(any("DEFAULT CHANGED" in w for w in a.cmd_latest_family("gpt-image", refresh=True)["warnings"]))

    def test_publishes_tier_reads_the_tier_tokens_of_the_price_text(self):
        self.assertTrue(K.publishes_tier(ECON, "1K"))
        self.assertFalse(K.publishes_tier(ECON, "2K"))
        self.assertTrue(K.publishes_tier(TIERS, "4K"))
        self.assertFalse(K.publishes_tier(TIERS, "8K"))
        self.assertFalse(K.publishes_tier("12 credits per image", "2K"))  # no tier named in the text: not published

    def test_the_economy_and_token_texts_parse_to_the_units_the_check_relies_on(self):
        self.assertIn(K.parse_pricing(ECON)["unit"], K.PICTURE_PRICE_UNITS)
        self.assertIn(K.parse_pricing(TIERS)["unit"], K.PICTURE_PRICE_UNITS)
        self.assertEqual(K.parse_pricing(TOKEN)["unit"], "per-1m-tokens")
        self.assertFalse(K.is_picture_priced(TOKEN))


class DefaultCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("check_default_image_model", CHECK)
        cls.C = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.C)

    def rows(self, **prices):
        return {i: {"model": i, "pricingDesc": p} for i, p in prices.items()}

    def test_the_shipped_default_passes_against_the_shipped_evidence(self):
        r = subprocess.run([sys.executable, "-I", CHECK], capture_output=True, text=True)
        self.assertEqual((r.returncode, r.stdout.strip()[:2]), (0, "OK"), r.stdout + r.stderr)

    def test_a_token_priced_default_is_refused(self):
        bad = self.C.check({"gpt-image": S26}, self.rows(**{S26: TOKEN}))
        self.assertEqual(len(bad), 1)
        self.assertIn("per-1m-tokens", bad[0])

    def test_a_default_with_no_price_evidence_is_refused(self):
        bad = self.C.check({"gpt-image": E26}, {})
        self.assertEqual(len(bad), 1)
        self.assertIn("no price evidence", bad[0])

    def test_per_picture_defaults_pass(self):
        self.assertEqual(self.C.check({"gpt-image": E26}, self.rows(**{E26: ECON})), [])
        self.assertEqual(self.C.check({"gpt-image": S25}, self.rows(**{S25: TIERS})), [])

    def test_a_default_outside_the_image_family_is_refused(self):
        bad = self.C.check({"gpt-image": "gpt-5-5"}, self.rows(**{"gpt-5-5": ECON}))
        self.assertEqual(len(bad), 1)

    def test_main_fails_when_the_pinned_default_is_token_priced(self):
        import tempfile
        src = read(os.path.join(SKILL, "scripts", "kie_live_adapter.py"))
        self.assertIn('PINNED_DEFAULT = "%s"' % E26, src)
        with tempfile.TemporaryDirectory() as d:
            sk = os.path.join(d, "74-kie-live-adapter")
            os.makedirs(os.path.join(sk, "scripts"))
            os.makedirs(os.path.join(sk, "references"))
            for rel in ("scripts/kie_live_adapter.py", "scripts/check_default_image_model.py",
                        "references/kie-default-price-evidence.json"):
                body = read(os.path.join(SKILL, rel))
                if rel.endswith("adapter.py"):
                    body = body.replace('PINNED_DEFAULT = "%s"' % E26, 'PINNED_DEFAULT = "%s"' % S26)
                with open(os.path.join(sk, rel), "w", encoding="utf-8") as f:
                    f.write(body)
            r = subprocess.run([sys.executable, "-I", os.path.join(sk, "scripts", "check_default_image_model.py")],
                               capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("per-1m-tokens", r.stdout)


if __name__ == "__main__":
    unittest.main()
