"""U-images-01: paid image spend needs a verified paid_asset_budget approval (ENF-05), a defaulted style
is never paid for (IMG-08), an unconfirmed palette is never paid for (IMG-09).

Free: nothing here calls a provider or Command Center. The approval verifier is faked at the one seam
(image_plan._approval_verify); a free-text reference, a falsy test_only, a default style or a default
palette must each stop before allow_paid can be True.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "routes"))

sys.path.insert(0, str(Path(__file__).resolve().parent))
from price_cache_fixture import seed_price_cache  # noqa: E402
from launcher_core import image_plan  # noqa: E402
from launcher_core.image_plan import ImagePlanError, resolve  # noqa: E402

PLAN_HASH = "a" * 64
APPROVAL_ID = "appr_budget_0001"


def ok_record(**over):
    rec = {"ok": True, "approval_id": APPROVAL_ID, "kind": "paid_asset_budget", "plan_hash": PLAN_HASH,
           "client_identity": "TEST-ONLY", "scope": ["paid_asset_budget"], "expires_at": "2999-01-01T00:00:00Z",
           "authority": "command-center", "test_only": False}
    rec.update(over)
    return rec


class PaidSpendTests(unittest.TestCase):
    def setUp(self):
        seed_price_cache(self)  # never the machine's own price cache
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.brand = self.write_brand({"palette_status": "provided"})

    def write_brand(self, doc, name="brand.json"):
        path = self.tmp / name
        path.write_text(json.dumps(doc), encoding="utf-8")
        return str(path)

    def raw(self, **over):
        raw = {"brand_file": self.brand, "brand_owner": "TEST-ONLY Client", "design_style": "B",
               "design_style_source": "client_choice", "image_provider": "kie",
               "image_cap_minor": 4000, "image_currency": "USD", "paid_render_approval_ref": APPROVAL_ID}
        raw.update(over)
        return raw

    def paid(self, raw=None, verifier=None, **kw):
        verifier = verifier or mock.Mock(return_value=ok_record())
        kw.setdefault("plan_hash", PLAN_HASH)
        with mock.patch.object(image_plan, "_approval_verify", return_value=verifier):
            return resolve(self.raw() if raw is None else raw, test_only=False, **kw), verifier

    def refused(self, code, raw=None, **kw):
        with self.assertRaises(ImagePlanError) as ctx:
            self.paid(raw, **kw)
        self.assertEqual(ctx.exception.code, code)
        return ctx.exception

    # ---- ENF-05: test_only is a real bool; a free-text ref is not an approval -------------------
    def test_a_falsy_or_untyped_test_only_never_reaches_a_paid_run(self):
        for bad in (None, 0, "", [], "false", 1):
            with self.assertRaises(ImagePlanError) as ctx:
                resolve(self.raw(), test_only=bad, plan_hash=PLAN_HASH)
            self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-TEST-ONLY", repr(bad))

    def test_a_free_text_approval_ref_cannot_reach_allow_paid(self):
        def refuse(*_a, **_k):
            raise RuntimeError("no such approval in Command Center")
        err = self.refused("AF-LAUNCH-IMAGE-PLAN-APPROVAL", self.raw(paid_render_approval_ref="ok"),
                           verifier=refuse)
        self.assertIn("nothing has been spent", err.detail.lower())

    def test_with_no_approval_checker_installed_a_paid_run_fails_closed(self):
        # The seam is the approval checker itself: when it is not installed, a paid run cannot be
        # approved and stops. (A brand path is loaded the same way, so patching every is_file()
        # would test the brand record instead of the approval gate.)
        missing = ImagePlanError("AF-LAUNCH-IMAGE-PLAN-APPROVAL", "x", "the approval checker is not installed")
        with mock.patch.object(image_plan, "_approval_verify", side_effect=missing):
            with self.assertRaises(ImagePlanError) as ctx:
                resolve(self.raw(), test_only=False, plan_hash=PLAN_HASH)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-APPROVAL")

    def test_the_real_verifier_refuses_a_made_up_reference(self):
        try:
            image_plan._approval_verify()
        except ImagePlanError:
            return  # checker not in this checkout: already proven to fail closed above
        # The price is fixed here: clearing the environment makes the live-price reader fall back to the
        # machine's own cached catalog, which prices this model per million tokens (issue 60 now refuses
        # that), and this test is about the approval gate, not the price source.
        quote = {"model": "gpt-image-2-6/sunburst-text-to-image", "per_picture_minor": 8, "credits": 16.0,
                 "price_source": "test"}
        with mock.patch.dict("os.environ", {}, clear=True), mock.patch.object(image_plan, "live_price",
                                                                              return_value=quote):
            with self.assertRaises(ImagePlanError) as ctx:
                resolve(self.raw(paid_render_approval_ref="ok"), test_only=False, plan_hash=PLAN_HASH)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-APPROVAL")

    def test_a_record_that_is_not_from_command_center_or_not_a_budget_is_refused(self):
        for rec in (ok_record(authority="local-test-record"), ok_record(kind="launch_plan_build"),
                    ok_record(approval_id="someone_else_1"), ok_record(ok=1), {}):
            self.refused("AF-LAUNCH-IMAGE-PLAN-APPROVAL", verifier=mock.Mock(return_value=rec))

    def test_a_paid_run_without_the_plan_hash_is_refused(self):
        self.refused("AF-LAUNCH-IMAGE-PLAN-APPROVAL", plan_hash=None)
        self.refused("AF-LAUNCH-IMAGE-PLAN-APPROVAL", plan_hash="  ")

    def test_a_verified_budget_allows_paid_and_reports_the_derived_picture_ceiling(self):
        (inputs, to_confirm), verifier = self.paid()
        price = image_plan.live_price("kie", "USD")["per_picture_minor"]
        self.assertTrue(inputs["allow_paid"])
        self.assertEqual(inputs["executor_provider"], "kie")
        self.assertEqual(inputs["paid_approval_id"], APPROVAL_ID)
        self.assertEqual((inputs["image_cap_minor"], inputs["image_currency"], inputs["image_price_minor"]),
                         (4000, "USD", price))
        self.assertEqual(inputs["image_cap"], 4000 // price)  # the picture ceiling, derived from the money
        self.assertEqual(to_confirm, [])
        args, kwargs = verifier.call_args
        self.assertEqual(args[1:3], ("paid_asset_budget", PLAN_HASH))
        self.assertEqual(kwargs["cap"], {"cap_minor": 4000, "currency": "USD"})
        self.assertIs(kwargs["test_only"], False)

    def test_a_paid_run_is_priced_from_the_seeded_cache_never_the_machines_own(self):
        # The machine's own cache (HOME/.openclaw/cache/kie-live-adapter) prices the default model per million
        # tokens. A paid-run price must not depend on it: the seeded per-picture cache (setUp) wins.
        machine = self.tmp / "machine-home" / ".openclaw" / "cache" / "kie-live-adapter"
        machine.mkdir(parents=True)
        token_catalog = json.dumps({"fetched_at": time.time(), "models": [
            {"model": "gpt-image-2-6/sunburst-text-to-image", "pricingDesc": TOKEN_TEXT}]})
        (machine / "catalog.json").write_text(token_catalog, encoding="utf-8")
        with mock.patch.dict(os.environ, {"HOME": str(self.tmp / "machine-home")}):
            (inputs, _), _v = self.paid()
        self.assertEqual(inputs["image_price_minor"], 8)  # the seeded 4 K tier, not a refusal
        self.assertIn("catalog:cache", inputs["image_price_source"])  # read from the seeded catalog itself
        self.assertEqual((machine / "catalog.json").read_text(encoding="utf-8"), token_catalog)  # read-only

    def test_the_picture_ceiling_is_priced_live_not_from_a_table(self):
        (inputs, _), _v = self.paid()
        quote = image_plan.live_price("kie", "USD")
        self.assertEqual(inputs["image_price_minor"], quote["per_picture_minor"])
        self.assertEqual(inputs["image_price_credits"], quote["credits"])
        self.assertIn("74-kie-live-adapter", inputs["image_price_source"])
        self.assertFalse(hasattr(image_plan, "IMAGE_PRICE_MINOR"), "a static table cannot price a paid run")
        for currency in ("EUR", "GBP"):
            self.refused("AF-LAUNCH-IMAGE-PLAN-CAP", self.raw(image_currency=currency))

    def test_a_named_resolution_selects_the_live_tier(self):
        (inputs, _), _v = self.paid(self.raw(image_resolution="1K"))
        self.assertEqual(inputs["image_resolution"], "1K")
        self.assertLessEqual(inputs["image_price_minor"],
                             image_plan.live_price("kie", "USD")["per_picture_minor"])

    def test_the_spend_is_money_not_a_picture_count(self):
        self.refused("AF-LAUNCH-IMAGE-PLAN-CAP", {k: v for k, v in self.raw().items()
                                                  if k not in ("image_cap_minor", "image_currency")} | {"image_cap": 50})
        self.refused("AF-LAUNCH-IMAGE-PLAN-CAP", self.raw(image_cap_minor=None))
        self.refused("AF-LAUNCH-IMAGE-PLAN-CAP", self.raw(image_currency="XYZ"))  # no price row: never guessed
        self.refused("AF-LAUNCH-IMAGE-PLAN-CAP", self.raw(image_cap_minor=3))     # not even one picture
        ceiling = 4000 // image_plan.live_price("kie", "USD")["per_picture_minor"]
        self.refused("AF-LAUNCH-IMAGE-PLAN-CAP", self.raw(image_cap=ceiling + 1))
        (inputs, _), _v = self.paid(self.raw(image_cap=ceiling - 1))
        self.assertEqual(inputs["image_cap"], ceiling - 1)

    def test_bad_money_values_are_named(self):
        for over in ({"image_cap_minor": True}, {"image_cap_minor": 0}, {"image_cap_minor": "40"},
                     {"image_currency": "usd"}, {"image_currency": 5}):
            with self.assertRaises(ImagePlanError) as ctx:
                resolve(self.raw(**over), test_only=True)
            self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-CAP", over)

    def test_a_practice_run_needs_no_approval_and_never_spends(self):
        verifier = mock.Mock()
        with mock.patch.object(image_plan, "_approval_verify", return_value=verifier):
            inputs, _ = resolve({"brand_file": "/nope.json", "brand_owner": "X"}, test_only=True)
        self.assertEqual((inputs["executor_provider"], inputs["allow_paid"]), ("stub", False))
        self.assertIsNone(inputs["paid_approval_id"])
        verifier.assert_not_called()

    # ---- IMG-24: an Agnes plan resolves and draws placeholders only -----------------------------
    def test_an_agnes_plan_resolves_and_draws_one_stub_section(self):
        inputs, _ = image_plan.resolve({"brand_file": self.brand, "brand_owner": "TEST-ONLY Client",
                                        "design_style": "A", "image_provider": "agnes"}, test_only=True)
        self.assertEqual(inputs["executor_provider"], "stub")
        self.assertIs(inputs["allow_paid"], False)
        self.assertEqual(image_plan.image_inputs_file(inputs)["image_provider"], "stub")
        sys.path.insert(0, str(SKILL_ROOT.parent / "71-blackceo-signature-page" / "tests"))
        import board_fixture as bf  # noqa: E402  (Skill 71's own run fixture)
        executor = SKILL_ROOT.parent / "71-blackceo-signature-page" / "scripts" / "stage_executor.py"
        run_dir = self.tmp / "agnes-run"
        run_dir.mkdir()
        bf.make_run(run_dir, base_request={"model": "STUB-NO-MODEL", "sections": [
            {"section_id": "hero", "section_name": "Hero", "copy": "New copy one.",
             "slots": [{"slot_id": "IMG-001", "aspect_ratio": "16:9", "art_direction": "Window light."}]}]})
        proc = subprocess.run([sys.executable, str(executor), str(run_dir), "--provider", inputs["executor_provider"],
                               "--stages", "desktop-wireframe"], capture_output=True, text=True, env=bf.subprocess_env())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        drawn = run_dir / "desktop-wireframe" / "section-01.png"
        self.assertEqual(drawn.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
        record = json.loads((run_dir / "desktop-wireframe" / "stage-executor-record.json").read_text(encoding="utf-8"))
        self.assertEqual(record["provider"], "stub")

    # ---- IMG-08: a defaulted style is never paid for -------------------------------------------
    def test_a_paid_run_with_no_style_stops_until_the_client_picks_a_b_or_c(self):
        for raw in (self.raw(design_style=None), self.raw(design_style="not sure"),
                    self.raw(design_style="B", design_style_source="default_to_confirm")):
            verifier = mock.Mock(return_value=ok_record())
            self.refused("AF-LAUNCH-IMAGE-PLAN-STYLE", raw, verifier=verifier)
            verifier.assert_not_called()  # stopped before any approval lookup, nothing spent
        (inputs, _), _v = self.paid(self.raw(design_style="C", design_style_source="client_choice"))
        self.assertEqual((inputs["design_style"], inputs["design_style_source"]), ("C", "client_choice"))

    def test_a_defaulted_style_stays_flagged_and_is_never_called_a_client_choice_on_a_practice_run(self):
        inputs, to_confirm = resolve(self.raw(design_style="B", design_style_source="default_to_confirm"),
                                     test_only=True)
        self.assertEqual(inputs["design_style_source"], "default_to_confirm")
        self.assertIn("image_plan.design_style", {r["field"] for r in to_confirm})
        with self.assertRaises(ImagePlanError):
            resolve(self.raw(design_style_source="made_up"), test_only=True)

    # ---- IMG-09: an unconfirmed palette is never paid for --------------------------------------
    def test_a_paid_run_refuses_a_suggested_or_default_palette(self):
        for status in ("default_to_confirm", "suggested", "", None, "made_up"):
            brand = self.write_brand({"palette_status": status}, f"b-{status}.json")
            err = self.refused("AF-LAUNCH-IMAGE-PLAN-BRAND", self.raw(brand_file=brand))
            self.assertIn("nothing has been spent", err.detail.lower())
        self.refused("AF-LAUNCH-IMAGE-PLAN-BRAND", self.raw(brand_file=str(self.tmp / "missing.json")))
        self.write_brand([], "list.json")
        self.refused("AF-LAUNCH-IMAGE-PLAN-BRAND", self.raw(brand_file=str(self.tmp / "list.json")))

    def test_a_confirmed_palette_passes_and_a_practice_run_is_not_checked(self):
        for doc in ({"palette_status": "provided"}, {"palette_status": "client-confirmed"}):
            brand = self.write_brand(doc, "ok.json")
            (inputs, _), _v = self.paid(self.raw(brand_file=brand))
            self.assertTrue(inputs["allow_paid"])
        bad = self.write_brand({"palette_status": "default_to_confirm"}, "d.json")
        inputs, _ = resolve(self.raw(brand_file=bad), test_only=True)
        self.assertFalse(inputs["allow_paid"])

    def test_a_brand_file_with_no_palette_status_is_unknown_and_never_paid(self):
        # F16 item 8: a missing status is unknown, not "provided" for files made before the field.
        brand = self.write_brand({}, "legacy.json")
        err = self.refused("AF-LAUNCH-IMAGE-PLAN-BRAND", self.raw(brand_file=brand))
        self.assertIn("no palette status", err.detail)

    # ---- the shared file carries the style source and the creative direction -------------------
    def test_design_style_source_and_creative_direction_travel_in_the_shared_file(self):
        inputs, _ = resolve(self.raw(creative_direction="like the Acme homepage",
                                     design_style_source="recommended_accepted"), test_only=True)
        self.assertEqual(inputs["creative_direction"], "like the Acme homepage")
        takes_all = SimpleNamespace(dispatch=lambda: SimpleNamespace(pset=SimpleNamespace(
            IMAGE_INPUT_KEYS=image_plan.C3_KEYS + image_plan.C3_CARRIED_KEYS)))
        with mock.patch.dict(sys.modules, {"substrate": takes_all}):
            doc = image_plan.image_inputs_file(inputs)
        self.assertEqual(doc["design_style_source"], "recommended_accepted")
        self.assertEqual(doc["creative_direction"], "like the Acme homepage")
        takes_base = SimpleNamespace(dispatch=lambda: SimpleNamespace(pset=SimpleNamespace(
            IMAGE_INPUT_KEYS=image_plan.C3_KEYS)))
        with mock.patch.dict(sys.modules, {"substrate": takes_base}):  # Skill 49 refuses unknown keys
            self.assertEqual(sorted(image_plan.image_inputs_file(inputs)), sorted(image_plan.C3_KEYS))

    def test_the_price_travels_into_both_shared_files(self):
        # Issue 76: the money that justifies the count is written beside it, to Skill 49's file and Skill 78's.
        inputs, _ = resolve(self.raw(), test_only=True)
        inputs = dict(inputs, image_price_minor=8, image_cap_minor=320, image_currency="USD")
        takes_all = SimpleNamespace(dispatch=lambda: SimpleNamespace(pset=SimpleNamespace(
            IMAGE_INPUT_KEYS=image_plan.C3_KEYS + image_plan.C3_CARRIED_KEYS)))
        with mock.patch.dict(sys.modules, {"substrate": takes_all}):
            doc = image_plan.image_inputs_file(inputs)
        self.assertEqual((doc["image_price_minor"], doc["image_cap_minor"], doc["image_currency"]), (8, 320, "USD"))
        order = image_plan.order_page_inputs_file(inputs, route_graph="route-graph.json")
        self.assertEqual((order["image_price_minor"], order["image_cap_minor"], order["image_currency"]), (8, 320, "USD"))


GPT_IMAGE_TEXT = ("GPT Image 2.6 \u2014 now just 6 credits ($0.03) for 1 K, 10 credits ($0.05) for 2 K, "
                  "and 16 credits ($0.08) for 4 K.")
TOKEN_TEXT = ("Input 800 credits / 1M tokens (\u2248 $4.00), Output 4,000 credits / 1M tokens "
              "(\u2248 $20.00)")


class PriceTierAndUnitTests(unittest.TestCase):
    """Issues 59 and 60: the named tier is the price, and only a per-picture price is a picture price."""

    def setUp(self):
        seed_price_cache(self)  # never the machine's own price cache

    def quote(self, desc, unit, model="gpt-image-2-6/sunburst-text-to-image", resolution=None):
        adapter = mock.Mock()
        adapter.cmd_price.return_value = {"state": "ok", "data": {"pricing_desc": desc, "unit": unit,
                                                                  "price_source": "test"}}
        module = SimpleNamespace(KNOWN_DEFAULTS={"gpt-image": model})
        with mock.patch.object(image_plan, "_price_module", return_value=module), \
                mock.patch.object(image_plan, "_price_adapter", return_value=adapter):
            return image_plan.live_price("kie", "USD", model=model, resolution=resolution)

    # ---- issue 59 ----------------------------------------------------------------------------
    def test_each_named_tier_picks_its_own_price_from_the_real_gpt_image_text(self):
        for res, credits, usd in (("1K", 6.0, 0.03), ("2K", 10.0, 0.05), ("4K", 16.0, 0.08)):
            got = image_plan.pick_price(GPT_IMAGE_TEXT, res)
            self.assertEqual((got["credits"], got["usd"]), (credits, usd), res)

    def test_each_named_tier_prices_from_text_with_no_comma_before_the_and(self):
        # Issue 59: "... for 1 K and 10 credits ($0.05) for 2 K and 16 credits ($0.08) for 4 K" has no
        # comma at all; the `and` half of the clause splitter is what keeps each tier apart.
        text = "6 credits ($0.03) for 1 K and 10 credits ($0.05) for 2 K and 16 credits ($0.08) for 4 K"
        for res, usd in (("1K", 0.03), ("2K", 0.05), ("4K", 0.08)):
            self.assertEqual(image_plan.pick_price(text, res)["usd"], usd, res)

    def test_each_clause_boundary_keeps_its_own_tier(self):
        # One text per branch of the clause splitter: the tier word may sit after a comma that is
        # followed by words, directly after a comma with no space, inside a word that ends in "and",
        # or in a tier that names two resolutions before its price.
        for text, res, usd in (
                ("6 credits ($0.03), each at 1 K, 16 credits ($0.08), each at 4 K", "1K", 0.03),
                ("6 credits ($0.03) for 1 K,16 credits ($0.08) for 4 K", "1K", 0.03),
                ("6 credits ($0.03) for 1 K,16 credits ($0.08) for 4 K", "4K", 0.08),
                ("6 credits ($0.03) for Brand 1 K, 16 credits ($0.08) for 4 K", "1K", 0.03),
                ("6 credits ($0.03) for 1 K and the 2 K tier, 16 credits ($0.08) for 4 K", "2K", 0.03),
                ("6 credits ($0.03) for 1 K, and 16 credits ($0.08) for 4 K", "4K", 0.08),
                ("6 credits ($0.03) for 1 K and 16 credits ($0.08) for 4 K", "1K", 0.03)):
            self.assertEqual(image_plan.pick_price(text, res)["usd"], usd, (text, res))

    def test_a_tier_name_is_matched_whole_and_with_or_without_a_space(self):
        text = "10 credits ($0.05) for 12 K, 16 credits ($0.08) for 2 K"
        self.assertEqual(image_plan.pick_price(text, "2K")["usd"], 0.08)
        self.assertEqual(image_plan.pick_price("6 credits ($0.03) for 1K, 16 credits ($0.08) for 4K", "4K")["usd"], 0.08)
        self.assertEqual(image_plan.pick_price("6 credits ($0.03) for 1K, 16 credits ($0.08) for 4K", "1")["usd"], 0.03)
        self.assertEqual(image_plan.pick_price("10 credits ($0.05) for 2 Kb, 16 credits ($0.08) for 2 K", "2K")["usd"], 0.08)
        self.assertEqual(image_plan.pick_price("10 credits ($0.05) for 2 K, 16 credits ($0.08) for 4 K", " 2K ")["usd"], 0.05)

    def test_tiers_that_cannot_be_told_apart_are_refused_not_guessed(self):
        # "and" glued to the next price or a comma-and with no space leaves both prices in one clause.
        for text in ("6 credits ($0.03) for 1 K and16 credits ($0.08) for 4 K",
                     "6 credits ($0.03) for 1 K,and16 credits ($0.08) for 4 K"):
            with self.assertRaises(ImagePlanError, msg=text) as ctx:
                image_plan.pick_price(text, "1K")
            self.assertIn("ambiguous", ctx.exception.detail)

    def test_a_tier_that_differs_only_in_credits_or_only_in_dollars_is_still_ambiguous(self):
        for text in ("4 K is 16 credits ($0.08); 4 K is 16 credits ($0.09)",
                     "4 K is 16 credits ($0.08); 4 K is 20 credits ($0.08)"):
            with self.assertRaises(ImagePlanError, msg=text) as ctx:
                image_plan.pick_price(text, "4K")
            self.assertEqual((ctx.exception.code, ctx.exception.field),
                             ("AF-LAUNCH-IMAGE-PLAN-PRICE", "image_plan.image_resolution"))
            self.assertIn("ambiguous", ctx.exception.detail)

    def test_the_tier_price_reaches_image_price_minor_exactly(self):
        for res, minor in (("1K", 3), ("2K", 5), ("4K", 8)):
            self.assertEqual(self.quote(GPT_IMAGE_TEXT, "per-job", resolution=res)["per_picture_minor"], minor, res)

    def test_a_ten_dollar_cap_at_4k_buys_125_pictures_not_200(self):
        price = self.quote(GPT_IMAGE_TEXT, "per-job", resolution="4K")["per_picture_minor"]
        self.assertEqual(1000 // price, 125)

    def test_two_different_prices_for_the_named_tier_are_refused_not_the_first(self):
        text = "4 K costs 16 credits ($0.08) per image; 4 K is also 10 credits ($0.05) per image"
        with self.assertRaises(ImagePlanError) as ctx:
            image_plan.pick_price(text, "4K")
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-PRICE")
        self.assertIn("ambiguous", ctx.exception.detail)

    def test_the_same_price_repeated_for_the_tier_is_not_ambiguous(self):
        text = "4 K is 16 credits ($0.08) per image; 4 K: 16 credits ($0.08)"
        self.assertEqual(image_plan.pick_price(text, "4K")["usd"], 0.08)

    # ---- issue 60 ----------------------------------------------------------------------------
    def test_a_token_priced_model_is_refused_as_not_a_picture_price(self):
        with self.assertRaises(ImagePlanError) as ctx:
            self.quote(TOKEN_TEXT, "per-1m-tokens", model="gpt-image-chat-model")
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-PRICE")
        self.assertEqual(ctx.exception.field, "image_plan.image_model")
        self.assertIn("per-1m-tokens", ctx.exception.detail)
        self.assertIn("not per picture", ctx.exception.detail)

    def test_per_image_and_per_job_prices_are_accepted_and_no_unit_is_refused(self):
        for unit in ("per-image", "per-job"):
            self.assertEqual(self.quote(GPT_IMAGE_TEXT, unit, resolution="1K")["per_picture_minor"], 3, unit)
        for unit in (None, "", "per-second", "per-1k-chars"):
            with self.assertRaises(ImagePlanError, msg=repr(unit)):
                self.quote(GPT_IMAGE_TEXT, unit)

    def test_a_free_text_image_model_outside_the_family_is_refused_without_an_override_approval(self):
        base = {"brand_file": "b.json", "brand_owner": "X", "image_provider": "kie"}
        with self.assertRaises(ImagePlanError) as ctx:
            image_plan.validate_raw(dict(base, image_model="some-chat-model"))
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-PRICE")
        image_plan.validate_raw(dict(base, image_model="gpt-image-2-6/sunburst-text-to-image"))
        image_plan.validate_raw(dict(base, image_model="some-chat-model", image_model_override_approval_ref="APPR-1"))


    def test_the_model_family_check_is_exact_about_case_provider_and_the_override_text(self):
        base = {"brand_file": "b.json", "brand_owner": "X", "image_provider": "kie"}
        image_plan.validate_raw(dict(base, image_model="GPT-Image-2-6/Sunburst"))  # case is not a difference
        image_plan.validate_raw(dict(base, image_model="  gpt-image-2-6  "))  # nor is stray whitespace
        for model in ("gpt-chat-4", "my-gpt-image"):  # same start letters, or the family name not at the start
            with self.assertRaises(ImagePlanError, msg=model):
                image_plan.validate_raw(dict(base, image_model=model))
        for ref in ("   ", "", 5):  # an override that names nothing is not an approval reference
            with self.assertRaises(ImagePlanError, msg=repr(ref)):
                image_plan.validate_raw(dict(base, image_model="some-chat-model", image_model_override_approval_ref=ref))
        no_provider = {"brand_file": "b.json", "brand_owner": "X", "image_model": "some-chat-model"}
        with self.assertRaises(ImagePlanError) as ctx:  # no provider given means the default provider's family
            image_plan.validate_raw(no_provider)
        self.assertEqual((ctx.exception.code, ctx.exception.field),
                         ("AF-LAUNCH-IMAGE-PLAN-PRICE", "image_plan.image_model"))
        image_plan.validate_raw(dict(no_provider, image_provider="stub"))  # a provider with no family map is not checked


REAL_TOKEN_CATALOG_TEXT = (
    "Text input 900 credits / 1M tokens ($4.50), cached text input 225 ($1.125), image input 1,440 ($7.20), "
    "cached image input 360 ($1.80), image output 5,400 ($27.00) \u2014 10% below official pricing.")


class RealCatalogEntryTests(unittest.TestCase):
    """Issue 60, the e2e reproduction: Skill 74's REAL adapter reads a cached live catalog whose entry for
    the default image model is priced per million tokens. Before the unit check, 'credits ($usd)' in that
    text was read as a picture price ('72 minor USD does not pay for one picture (450 each)')."""

    MODEL = "gpt-image-2-6/sunburst-text-to-image"

    def setUp(self):
        seed_price_cache(self)  # the env var is re-pointed per quote below

    def _quote(self, entries, model, resolution=None):
        with tempfile.TemporaryDirectory() as cache:
            Path(cache, "catalog.json").write_text(json.dumps(
                {"fetched_at": time.time(),
                 "models": [{"model": m, "pricingDesc": d} for m, d in entries]}), encoding="utf-8")
            with mock.patch.dict(os.environ, {"KIE_LIVE_CACHE_DIR": cache}):
                return image_plan.live_price("kie", "USD", model=model, resolution=resolution)

    def test_the_default_model_with_a_per_token_catalog_entry_is_refused_not_priced_450(self):
        with self.assertRaises(ImagePlanError) as ctx:
            self._quote([(self.MODEL, REAL_TOKEN_CATALOG_TEXT)], self.MODEL)
        self.assertEqual(ctx.exception.code, "AF-LAUNCH-IMAGE-PLAN-PRICE")
        self.assertIn("per-1m-tokens", ctx.exception.detail)
        self.assertNotIn("450", ctx.exception.detail)

    def test_control_the_same_harness_prices_a_per_picture_catalog_entry(self):
        got = self._quote([("gpt-image-2-text-to-image", GPT_IMAGE_TEXT)], "gpt-image-2-text-to-image",
                          resolution="1K")
        self.assertEqual(got["per_picture_minor"], 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
