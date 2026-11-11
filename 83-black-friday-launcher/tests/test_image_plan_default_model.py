"""X-97: a paid run that names no image model is priced at Skill 74's default: GPT Image 2.6 Sunburst, medium quality.

2.6 is billed by tokens; the default is priced per picture from KIE's published reference table (an estimate;
actual billed by tokens): medium 1K 7.82, 2K 15.90, 4K 26.43 credits. A model or quality the caller names is
never replaced. Free: Skill 74's Adapter runs on a fake transport (the one network seam), so nothing calls KIE.
Price texts are copied from KIE's live catalog (2026-11-10).
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
import types
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
S26, S26_I = "gpt-image-2-6/sunburst-text-to-image", "gpt-image-2-6/sunburst-image-to-image"
S25, S25_I = "gpt-image-2-5-sunburst-text-to-image", "gpt-image-2-5-sunburst-image-to-image"
TIERS = "GPT Image 2.5 — now just 6 credits ($0.03) for 1 K, 10 credits ($0.05) for 2 K, and 16 credits ($0.08) for 4 K."
N27, N27_I = "gpt-image-2-7/sunburst-text-to-image", "gpt-image-2-7/sunburst-image-to-image"
A27, A27_I = "gpt-image-2-7/aurora-text-to-image", "gpt-image-2-7/aurora-image-to-image"
T2I, I2I = ["Text to Image"], ["Image to Image"]


def row(model, task, price):
    return {"model": model, "title": model, "provider": "OpenAI", "taskType": task, "pricingDesc": price}


CATALOG = [row(S26, T2I, TOKEN), row(S26_I, I2I, TOKEN)]  # today's live shape: 2.6 sunburst is token-priced
TIERED = CATALOG + [row(S25, T2I, TIERS), row(S25_I, I2I, TIERS)]  # 2.5 sunburst is per picture, but older


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
        if url.endswith("/api/v1/chat/credit"):
            return 200, json.dumps({"code": 200, "data": 100000}).encode()
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

    # 7.82 / 15.90 / 26.43 credits at $0.005 each = 3.91 / 7.95 / 13.215 cents, rounded up to whole cents
    MEDIUM = (("1K", 7.82, 4), ("2K", 15.9, 8), ("4K", 26.43, 14))

    def test_no_model_and_no_quality_prices_sunburst_2_6_at_medium_per_picture(self):
        self.use_catalog(TIERED)
        for tier, credits, minor in self.MEDIUM:
            q = image_plan.live_price("kie", "USD", resolution=tier)
            self.assertEqual((q["model"], q["quality"], q["credits"], q["per_picture_minor"]), (S26, "medium", credits, minor), tier)
            self.assertTrue(q["reference_price"])
            self.assertEqual(q["price_note"], "estimate; actual billed by tokens")

    def test_a_paid_run_naming_no_model_is_budgeted_at_the_medium_price_for_each_size(self):
        self.use_catalog(TIERED)
        for tier, credits, minor in self.MEDIUM:
            inputs, _ = self.paid(image_resolution=tier)
            self.assertTrue(inputs["allow_paid"])
            self.assertEqual((inputs["image_model"], inputs["image_quality"], inputs["image_price_minor"], inputs["image_cap"]),
                             (S26, "medium", minor, 4000 // minor), tier)

    def test_a_quality_the_caller_names_is_priced_and_recorded_never_replaced(self):
        self.use_catalog(TIERED)
        for quality, credits in (("low", 4.44), ("high", 9.48), ("xhigh", 16.86), ("max", 37.93)):
            q = image_plan.live_price("kie", "USD", resolution="1K", quality=quality)
            self.assertEqual((q["model"], q["quality"], q["credits"]), (S26, quality, credits))
            inputs, _ = self.paid(image_resolution="1K", image_quality=quality)
            self.assertEqual(inputs["image_quality"], quality)

    def test_auto_and_unknown_qualities_have_no_picture_price_and_are_refused(self):
        self.use_catalog(TIERED)
        for quality in ("auto", "ultra"):
            with self.assertRaises(ImagePlanError) as ctx:
                image_plan.live_price("kie", "USD", resolution="1K", quality=quality)
            self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-PRICE")
            self.assertIn("nothing has been spent", ctx.exception.detail.lower())

    def test_a_blank_quality_is_refused_at_intake(self):
        self.use_catalog(TIERED)
        with self.assertRaises(ImagePlanError) as ctx:
            self.paid(image_quality="  ")
        self.assertEqual((ctx.exception.code, ctx.exception.field), ("AF-LAUNCH-IMAGE-PLAN-PRICE", "image_plan.image_quality"))

    def test_a_token_priced_default_without_a_reference_row_is_refused(self):
        self.use_catalog(CATALOG)
        empty = self.tmp / "no-rows.json"
        empty.write_text(json.dumps({"tables": []}), encoding="utf-8")
        with mock.patch.object(self.module, "PRICE_EVIDENCE", str(empty)):
            with self.assertRaises(ImagePlanError) as ctx:
                image_plan.live_price("kie", "USD", resolution="1K")
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-PRICE")
        self.assertIn("nothing has been spent", ctx.exception.detail.lower())

    def test_a_newer_sunburst_with_a_picture_price_becomes_the_default(self):
        self.use_catalog(TIERED + [row(N27, T2I, "7 credits ($0.035) per image"), row(N27_I, I2I, "7 credits ($0.035) per image")])
        q = image_plan.live_price("kie", "USD")
        self.assertEqual((q["model"], q["per_picture_minor"]), (N27, 4))

    def test_a_newer_non_sunburst_model_is_not_the_default(self):
        self.use_catalog(TIERED + [row(A27, T2I, "7 credits ($0.035) per image"), row(A27_I, I2I, "7 credits ($0.035) per image")])
        self.assertEqual(image_plan.live_price("kie", "USD")["model"], S26)

    def test_a_model_the_caller_names_is_priced_as_named_not_replaced(self):
        self.use_catalog(TIERED)
        q = image_plan.live_price("kie", "USD", model=S25, resolution="2K", quality="max")
        self.assertEqual((q["model"], q["credits"], q["quality"], q["reference_price"]), (S25, 10.0, None, False))

    def test_with_wp04_a_named_token_priced_model_is_still_refused(self):
        self.use_catalog(TIERED)
        with self.assertRaises(ImagePlanError) as ctx:
            image_plan.live_price("kie", "USD", model=S26, resolution="1K")
        self.assertIn("not per picture", ctx.exception.detail)

    def test_the_default_is_preflighted_at_its_picture_price_not_the_token_text(self):
        self.use_catalog(TIERED)
        inputs, _ = self.paid(image_resolution="4K")
        pf = inputs["image_preflight"]
        self.assertEqual(pf["state"], "ok")
        self.assertEqual(pf["required"], self.module.preflight_amount(26.43 * inputs["image_cap"]))


    def test_a_named_quality_is_preflighted_at_its_own_price_not_medium(self):
        self.use_catalog(TIERED)
        seen = {}
        for quality, top in (("medium", 26.43), ("high", 32.02), ("max", 128.08)):
            inputs, _ = self.paid(image_resolution="1K", image_quality=quality)
            pf = inputs["image_preflight"]
            self.assertEqual(pf["state"], "ok")
            self.assertEqual(pf["required"], self.module.preflight_amount(round(top * inputs["image_cap"], 4)), quality)
            seen[quality] = pf["required"] / inputs["image_cap"]
        self.assertLess(seen["medium"], seen["high"])
        self.assertLess(seen["high"], seen["max"])

    def test_a_model_the_caller_names_is_preflighted_at_its_own_picture_price_not_the_defaults_reference_price(self):
        self.use_catalog(TIERED)
        q = image_plan.live_price("kie", "USD", model=S25, resolution="2K", quality="max")
        self.assertFalse(q["reference_price"])
        pf = image_plan.preflight(q, 4)
        self.assertEqual(pf["state"], "ok")
        self.assertEqual(pf["required"], self.module.preflight_amount(16.0))  # S25's own per-picture price, its dearest tier (16 credits, 4 K), x1.3
        self.assertNotEqual(pf["required"], self.module.preflight_amount(round(128.08 * 4, 4)))  # not the default's "max" reference price
        inputs, _ = self.paid(image_model=S25, image_resolution="2K")  # and the same through a paid run that names the model
        self.assertEqual(inputs["image_preflight"]["state"], "ok")
        self.assertEqual(inputs["image_preflight"]["required"], self.module.preflight_amount(16.0))

    def test_a_practice_run_records_the_quality_it_was_given(self):
        self.use_catalog(TIERED)
        raw = {"brand_file": self.brand, "brand_owner": "TEST-ONLY Client", "design_style": "B",
               "design_style_source": "client_choice", "image_provider": "kie", "image_quality": "high"}
        inputs, _ = resolve(raw, test_only=True, plan_hash=PLAN_HASH)
        self.assertEqual(inputs["image_quality"], "high")

    def test_an_older_adapter_without_a_default_price_prices_the_known_default_as_named(self):
        self.use_catalog([row(S26, T2I, "6 credits ($0.03) per image"), row(S26_I, I2I, "6 credits ($0.03) per image")])
        real = image_plan._price_adapter()
        old = type("OldAdapter", (), {"cmd_price": lambda self, model, units=1: real.cmd_price(model, units=units)})()
        with mock.patch.object(image_plan, "_price_adapter", return_value=old):
            q = image_plan.live_price("kie", "USD", resolution="1K")
        self.assertEqual((q["model"], q["quality"], q["reference_price"], q["credits"]), (S26, None, False, 6.0))

    def test_a_provider_with_no_image_family_cannot_be_priced(self):
        self.use_catalog(TIERED)
        with self.assertRaises(ImagePlanError) as ctx:
            image_plan.live_price("elsewhere", "USD", resolution="1K")
        self.assertEqual((ctx.exception.code, ctx.exception.field), ("AF-LAUNCH-IMAGE-PLAN-PRICE", "image_plan.image_model"))

    def test_the_default_is_priced_even_when_the_module_lists_no_known_default(self):
        self.use_catalog(TIERED)
        with mock.patch.object(image_plan, "_price_module", return_value=types.SimpleNamespace(KNOWN_DEFAULTS={})):
            q = image_plan.live_price("kie", "USD", resolution="1K")
        self.assertEqual((q["model"], q["credits"], q["reference_price"]), (S26, 7.82, True))

    def test_a_catalog_picture_price_for_the_default_is_not_marked_a_reference_price(self):
        self.use_catalog([row(S26, T2I, "6 credits ($0.03) per image"), row(S26_I, I2I, "6 credits ($0.03) per image")])
        q = image_plan.live_price("kie", "USD", resolution="1K", quality="high")
        self.assertEqual((q["model"], q["quality"], q["reference_price"], q["credits"]), (S26, "high", False, 6.0))
        inputs, _ = self.paid(image_resolution="1K", image_quality="high")
        self.assertEqual(inputs["image_preflight"]["required"], self.module.preflight_amount(6.0 * inputs["image_cap"]))


if __name__ == "__main__":
    unittest.main()
