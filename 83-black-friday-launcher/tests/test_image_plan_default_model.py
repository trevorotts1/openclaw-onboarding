"""X-97: a paid run that names no image model is priced at Skill 74's default, and that default is PER PICTURE.

Free: Skill 74's Adapter runs on a fake transport (the one network seam), so nothing here calls KIE.
Price texts are copied from KIE's live catalog (2026-11-10): 2.6 sunburst is per 1M tokens (it priced at
"450 each" before this item), 2.6 economy is per picture.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "routes"))

from launcher_core import image_plan  # noqa: E402
from launcher_core.image_plan import ImagePlanError, resolve  # noqa: E402

PLAN_HASH = "a" * 64
APPROVAL_ID = "appr_budget_0001"
TOKEN = ("Text input 900 credits / 1M tokens ($4.50), cached text input 225 ($1.125), image input 1,440 ($7.20), "
         "cached image input 360 ($1.80), image output 5,400 ($27.00) — 10% below official pricing.")
ECON = ("GPT Image 2.6 (Economy) — just 5 credits ($0.025) per 1K image. Same GPT Image 2.6 model, served through "
        "our economy channel at a flat per-image price, 1K only.")
S26, S26_I = "gpt-image-2-6/sunburst-text-to-image", "gpt-image-2-6/sunburst-image-to-image"
E26, E26_I = "gpt-image-2-6/economy-text-to-image", "gpt-image-2-6/economy-image-to-image"
S25, S25_I = "gpt-image-2-5-sunburst-text-to-image", "gpt-image-2-5-sunburst-image-to-image"
TIERS = "GPT Image 2.5 — now just 6 credits ($0.03) for 1 K, 10 credits ($0.05) for 2 K, and 16 credits ($0.08) for 4 K."
N27, N27_I = "gpt-image-2-7/aurora-text-to-image", "gpt-image-2-7/aurora-image-to-image"
T2I, I2I = ["Text to Image"], ["Image to Image"]


def row(model, task, price):
    return {"model": model, "title": model, "provider": "OpenAI", "taskType": task, "pricingDesc": price}


CATALOG = [row(S26, T2I, TOKEN), row(S26_I, I2I, TOKEN), row(E26, T2I, ECON), row(E26_I, I2I, ECON)]
TIERED = CATALOG + [row(S25, T2I, TIERS), row(S25_I, I2I, TIERS)]  # today's live shape: 2.5 publishes 1K, 2K, 4K


class FakeKie:
    """Skill 74's transport seam: the catalog, and a readable schema for every model."""

    def __init__(self, module, rows):
        doc = {"paths": {module.JOB_PATH: {"post": {"requestBody": {"content": {"application/json": {"schema": {
            "type": "object", "required": ["model", "input"], "properties": {"model": {"type": "string"}, "input": {
                "type": "object", "required": ["prompt"], "properties": {"prompt": {"type": "string"}}}}}}}}}}}}
        self.schema = {"code": 200, "data": {"model": "x", "openapi": doc}}
        self.catalog = {"code": 200, "data": {"total": len(rows), "models": rows}}

    def request(self, method, url, headers=None, body=None, timeout=60, guard=None):
        if "/schema" in url:
            return 200, json.dumps(self.schema).encode()
        if url.endswith("/api/v1/models"):
            return 200, json.dumps(self.catalog).encode()
        return 404, b'{"code":404,"msg":"no route"}'


class DefaultModelPriceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        brand = self.tmp / "brand.json"
        brand.write_text(json.dumps({"palette_status": "provided"}), encoding="utf-8")
        self.brand = str(brand)
        self.module = image_plan._price_module()

    def use_catalog(self, rows):
        net = FakeKie(self.module, rows)
        env = {"KIE_API_KEY": "fake-key-for-tests", "KIE_LIVE_ADAPTER_MODE": "shadow", "HOME": str(self.tmp),
               "KIE_LIVE_CACHE_DIR": str(self.tmp / "cache"), "KIE_LIVE_REGISTRY": str(self.tmp / "none.json")}
        adapter = self.module.Adapter(env=env, transport=net, now=time.time, sleep=lambda s: None)
        patcher = mock.patch.object(image_plan, "_price_adapter", return_value=adapter)
        patcher.start()
        self.addCleanup(patcher.stop)

    def paid(self, **over):
        raw = {"brand_file": self.brand, "brand_owner": "TEST-ONLY Client", "design_style": "B",
               "design_style_source": "client_choice", "image_provider": "kie", "image_cap_minor": 4000,
               "image_currency": "USD", "paid_render_approval_ref": APPROVAL_ID}
        raw.update(over)
        record = {"ok": True, "approval_id": APPROVAL_ID, "kind": "paid_asset_budget", "plan_hash": PLAN_HASH,
                  "client_identity": "TEST-ONLY", "scope": ["paid_asset_budget"], "expires_at": "2999-01-01T00:00:00Z",
                  "authority": "command-center", "test_only": False}
        verifier = mock.Mock(return_value=record)
        with mock.patch.object(image_plan, "_approval_verify", return_value=verifier):
            return resolve(raw, test_only=False, plan_hash=PLAN_HASH)

    def test_no_model_named_prices_the_per_picture_default_not_the_token_one(self):
        self.use_catalog(CATALOG)
        quote = image_plan.live_price("kie", "USD")
        self.assertEqual((quote["model"], quote["credits"], quote["per_picture_minor"]), (E26, 5.0, 3))
        self.assertNotIn("1M tokens", quote["pricing_desc"])

    def test_a_paid_run_naming_no_model_gets_a_per_picture_price_and_a_sane_ceiling(self):
        self.use_catalog(CATALOG)
        inputs, _to_confirm = self.paid()
        self.assertTrue(inputs["allow_paid"])
        self.assertEqual(inputs["image_price_minor"], 3)
        self.assertEqual(inputs["image_cap"], 4000 // 3)  # not 4000 // 450, the token-priced "450 each"

    def test_a_newer_per_picture_model_in_the_catalog_becomes_the_default(self):
        self.use_catalog(CATALOG + [row(N27, T2I, "7 credits ($0.035) per image"), row(N27_I, I2I, "7 credits ($0.035) per image")])
        quote = image_plan.live_price("kie", "USD")
        self.assertEqual((quote["model"], quote["per_picture_minor"]), (N27, 4))

    def test_a_newer_token_priced_model_is_not_the_default(self):
        self.use_catalog(CATALOG + [row(N27, T2I, TOKEN), row(N27_I, I2I, TOKEN)])
        self.assertEqual(image_plan.live_price("kie", "USD")["model"], E26)

    def test_a_model_the_caller_names_is_priced_as_named(self):
        self.use_catalog(CATALOG + [row(N27, T2I, "7 credits ($0.035) per image"), row(N27_I, I2I, "7 credits ($0.035) per image")])
        self.assertEqual(image_plan.live_price("kie", "USD", model=E26)["model"], E26)

    def test_with_only_token_priced_models_nothing_is_priced_at_a_token_price(self):
        self.use_catalog([row(S26, T2I, TOKEN), row(S26_I, I2I, TOKEN)])
        with self.assertRaises(ImagePlanError) as ctx:
            image_plan.live_price("kie", "USD")
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-PRICE")
        self.assertIn("nothing has been spent", ctx.exception.detail.lower())

    # ---- ruling X-97-1: per picture stays absolute; 2K and 4K move to the newest per-picture model that publishes them
    def test_1k_resolves_the_2_6_economy_at_its_own_price(self):
        self.use_catalog(TIERED)
        q = image_plan.live_price("kie", "USD", resolution="1K")
        self.assertEqual((q["model"], q["credits"], q["per_picture_minor"]), (E26, 5.0, 3))
        self.assertEqual(q["selection"]["resolved_model"], E26)

    def test_2k_resolves_the_2_5_sunburst_at_the_2k_price_never_the_1k_price(self):
        self.use_catalog(TIERED)
        q = image_plan.live_price("kie", "USD", resolution="2K")
        self.assertEqual((q["model"], q["credits"], q["per_picture_minor"]), (S25, 10.0, 5))
        sel = q["selection"]
        self.assertEqual((sel["requested_model"], sel["resolved_model"], sel["resolution"]), (None, S25, "2K"))
        self.assertEqual((sel["tier_price_credits"], sel["tier_price_minor"]), (10.0, 5))
        self.assertIn(E26, sel["reason"])
        self.assertIn("2K", sel["reason"])

    def test_4k_resolves_the_2_5_sunburst(self):
        self.use_catalog(TIERED)
        q = image_plan.live_price("kie", "USD", resolution="4K")
        self.assertEqual(q["model"], S25)
        self.assertEqual(q["selection"]["resolved_model"], S25)

    def test_a_tier_nobody_prices_per_picture_is_refused(self):
        self.use_catalog(TIERED)
        with self.assertRaises(ImagePlanError) as ctx:
            image_plan.live_price("kie", "USD", resolution="8K")
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-PRICE")
        self.assertIn("nothing has been spent", ctx.exception.detail.lower())

    def test_a_tier_only_token_priced_models_publish_is_refused(self):
        tok_tiers = "Image output 5,400 credits / 1M tokens ($27.00); 1K 2K 4K sizes."
        self.use_catalog(CATALOG + [row(S25, T2I, tok_tiers), row(S25_I, I2I, tok_tiers)])
        with self.assertRaises(ImagePlanError) as ctx:
            image_plan.live_price("kie", "USD", resolution="2K")
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-PRICE")

    def test_a_paid_run_at_2k_holds_the_cap_against_the_2k_price_and_records_the_choice(self):
        self.use_catalog(TIERED)
        inputs, _ = self.paid(image_resolution="2K")
        self.assertEqual((inputs["image_model"], inputs["image_price_minor"], inputs["image_cap"]), (S25, 5, 4000 // 5))
        self.assertEqual(inputs["image_model_selection"]["resolved_model"], S25)
        self.assertEqual(inputs["image_model_selection"]["requested_model"], None)

    def test_a_paid_run_with_no_tier_still_prices_the_per_picture_default(self):
        self.use_catalog(TIERED)
        inputs, _ = self.paid()
        self.assertEqual((inputs["image_model"], inputs["image_price_minor"]), (E26, 3))


if __name__ == "__main__":
    unittest.main()
