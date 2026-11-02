"""Intake validates the operational and commercial fields it forwards (U-products-01).

PRD-13 operational fields, PRD-14 coherent offer set, PRD-35 levels on mains, UPS-15 upsell and
downsell deliverables, CHK-16 checkout terms, delivery destinations and refused payment plans.
Stdlib only. Every case starts from a fixture that validates, then breaks exactly one thing.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import checkout, intake, launch_bridge, route  # noqa: E402

FIXTURES = SKILL_ROOT / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name / "intake.json").read_text(encoding="utf-8"))


def offer(payload: dict, offer_id: str) -> dict:
    return next(o for o in payload["offers"] if o["offer_id"] == offer_id)


class IntakeCase(unittest.TestCase):
    def refuses(self, payload: dict, code: str, field: str = "", detail: str = ""):
        with self.assertRaises(intake.IntakeError) as ctx:
            intake.validate(payload)
        err = ctx.exception
        self.assertTrue(err.code.startswith(code), f"{err.code} does not start with {code}")
        self.assertIn(field, err.field)
        self.assertIn(detail, err.detail)
        return err


class FixturesValidate(IntakeCase):
    def test_both_fixtures_validate_with_level_data(self):
        for name in ("elevation", "seven-figure-preneur"):
            normalized = intake.validate(load(name))
            mains = [o for o in normalized["offers"] if o["role"] == "main"]
            self.assertTrue(all(o["level"]["state"] == "supplied" for o in mains), name)
            self.assertTrue(all(o["delivery"]["owner_confirmed"] for o in normalized["offers"]), name)
            self.assertEqual(normalized["checkout_terms"]["terms_ref"], "TEST-ONLY-TERMS-REF")


class OperationalFields(IntakeCase):  # PRD-13
    def test_test_only_must_be_a_bool(self):
        for bad in (0, 1, "", "false", None, []):
            payload = load("elevation")
            payload["test_only"] = bad
            self.refuses(payload, "AF-LAUNCH-INTAKE-TEST-ONLY", "test_only")
        for good in (True, False):
            payload = load("elevation")
            payload["test_only"] = good
            self.assertIs(intake.validate(payload)["test_only"], good)

    def test_write_target_enum(self):
        for bad in ("approved_live_publication", "anywhere", "", None):
            payload = load("elevation")
            payload["allowed_write_target"] = bad
            self.refuses(payload, "AF-LAUNCH-INTAKE-WRITE-TARGET", "allowed_write_target")
        payload = load("elevation")
        payload["allowed_write_target"] = "approved_test_location"
        self.assertEqual(intake.validate(payload)["allowed_write_target"], "approved_test_location")

    def test_automation_execution_enum(self):
        payload = load("elevation")
        payload["automation_execution"] = "run_now"
        self.refuses(payload, "AF-LAUNCH-INTAKE-AUTOMATION", "automation_execution")

    def test_locale_is_a_bcp47_tag(self):
        for bad in ("english please", "", 5, None, "en_US", "e"):
            payload = load("elevation")
            payload["locale"] = bad
            self.refuses(payload, "AF-LAUNCH-INTAKE-LOCALE", "locale")
        for good in ("en", "en-US", "pt-BR", "zh-Hant-TW"):
            payload = load("elevation")
            payload["locale"] = good
            self.assertEqual(intake.validate(payload)["locale"], good)


class OfferSetCoherence(IntakeCase):  # PRD-14
    def test_mixed_currencies_refused(self):
        payload = load("elevation")
        offer(payload, "BUMP")["price"]["currency"] = "EUR"
        self.refuses(payload, "AF-LAUNCH-INTAKE-OFFER", "currency", "'EUR'")

    def test_offer_ids_unique_case_insensitively(self):
        payload = load("elevation")
        offer(payload, "U1")["offer_id"] = "main-ess"
        self.refuses(payload, "AF-LAUNCH-INTAKE-OFFER", "main-ess", "offer id")

    def test_offer_id_charset(self):
        payload = load("elevation")
        offer(payload, "BUMP")["offer_id"] = "BUMP 1!"
        self.refuses(payload, "AF-LAUNCH-INTAKE-OFFER", "offer_id", "[A-Za-z0-9_-]+")

    def test_display_names_unique(self):
        payload = load("elevation")
        offer(payload, "U1")["name"] = "  test only ESSENTIAL "
        self.refuses(payload, "AF-LAUNCH-INTAKE-OFFER", "U1", "display name")

    def test_multiple_options_identical_price_needs_different_levels(self):
        payload = load("elevation")
        pro, ess = offer(payload, "MAIN-PRO"), offer(payload, "MAIN-ESS")
        pro["price"]["amount_minor"] = ess["price"]["amount_minor"]
        intake.validate(payload)  # the levels differ, so identical prices are allowed
        pro["level"] = copy.deepcopy(ess["level"])
        self.refuses(payload, "AF-LAUNCH-INTAKE-OFFER", "offers", "same level")

    def test_folded_levels_identical_price_refused(self):
        payload = load("seven-figure-preneur")
        offer(payload, "MAIN-B")["price"]["amount_minor"] = 9700
        self.refuses(payload, "AF-LAUNCH-INTAKE-OFFER", "offers", "identical prices")

    def test_price_sanity_bounds_need_confirmation(self):
        for amount in (99, 10_000_001):
            payload = load("elevation")
            offer(payload, "BUMP")["price"]["amount_minor"] = amount
            self.refuses(payload, "AF-LAUNCH-INTAKE-OFFER", "amount_minor", "bounds_confirmed")
            offer(payload, "BUMP")["price"]["bounds_confirmed"] = True
            intake.validate(payload)


class MainLevels(IntakeCase):  # PRD-35
    def test_folded_levels_without_level_refused(self):
        payload = load("seven-figure-preneur")
        for o in payload["offers"]:
            o.pop("level", None)
        err = self.refuses(payload, "AF-LAUNCH-INTAKE-LEVEL", "offers[0].level")
        self.assertIn("level.state", err.detail)

    def test_multiple_options_without_level_refused(self):
        payload = load("elevation")
        offer(payload, "MAIN-PRO")["level"] = {"state": "unknown"}
        self.refuses(payload, "AF-LAUNCH-INTAKE-LEVEL", "offers[1].level")

    def test_main_level_needs_a_deliverable(self):
        payload = load("seven-figure-preneur")
        offer(payload, "MAIN-A")["level"]["deliverables"] = []
        self.refuses(payload, "AF-LAUNCH-INTAKE-LEVEL", "deliverables")

    def test_bump_level_may_stay_unknown(self):
        self.assertEqual(intake.validate(load("elevation"))["offers"][3]["level"], {"state": "unknown"})


class UpsellDownsellDeliverables(IntakeCase):  # UPS-15
    def test_each_enabled_extra_needs_deliverables_and_asks_by_name(self):
        for offer_id in ("U1", "D1", "U2"):
            for strip in (lambda o: o.pop("level"), lambda o: o.update(level={"state": "unknown"})):
                payload = load("elevation")
                strip(offer(payload, offer_id))
                err = self.refuses(payload, "AF-LAUNCH-INTAKE-LEVEL", "level")
                self.assertIn(f"TEST ONLY {offer_id}", err.detail)  # the question names the offer
                self.assertIn("What exactly does the buyer receive", err.detail)

    def test_single_simple_main_level_stays_optional(self):
        payload = load("elevation")
        payload["journey_mode"] = "single_simple"
        payload["offers"] = [o for o in payload["offers"] if o["offer_id"] not in ("MAIN-PRO", "MAIN-ELITE")]
        offer(payload, "MAIN-ESS").pop("level")
        self.assertEqual(intake.validate(payload)["offers"][0]["level"], {"state": "unknown"})

    def test_supplied_deliverables_reach_the_launch_record(self):
        normalized = intake.validate(load("elevation"))
        record = launch_bridge.to_launch_record(
            normalized, route.compile_route(normalized), {"image_provider": "stub", "design_style": "A"})
        by_id = {o["offer_id"]: o for o in record["offers"]}
        for offer_id in ("U1", "D1", "U2"):
            self.assertTrue(by_id[offer_id]["deliverables"], offer_id)


class CheckoutFacts(IntakeCase):  # CHK-16
    def test_missing_checkout_terms_refused(self):
        payload = load("elevation")
        del payload["checkout_terms"]
        self.refuses(payload, "AF-LAUNCH-INTAKE-MISSING", "checkout_terms")

    def test_each_terms_field_is_required_verbatim_text_included(self):
        for key in intake.TERMS_FIELDS:
            payload = load("elevation")
            payload["checkout_terms"][key] = "  "
            self.refuses(payload, "AF-LAUNCH-INTAKE-TERMS", key)
        payload = load("elevation")
        payload["checkout_terms"]["terms_text"] = "  Verbatim, spaces and all.  "
        self.assertEqual(intake.validate(payload)["checkout_terms"]["terms_text"],
                         "  Verbatim, spaces and all.  ")

    def test_delivery_destination_is_required_https_and_owner_confirmed(self):
        payload = load("elevation")
        del offer(payload, "U1")["delivery"]
        self.refuses(payload, "AF-LAUNCH-INTAKE-OFFER", "delivery", "missing")
        for bad in ("http://delivery.test-only.invalid/x", "ftp://a.b/c", "https://", "not a url",
                    "https://user:pw@delivery.test-only.invalid/x", None, 5):
            payload = load("elevation")
            offer(payload, "U1")["delivery"]["destination"] = bad
            self.refuses(payload, "AF-LAUNCH-INTAKE-DELIVERY", "destination")
        for bad in (False, None, "true", 1):
            payload = load("elevation")
            offer(payload, "U1")["delivery"]["owner_confirmed"] = bad
            self.refuses(payload, "AF-LAUNCH-INTAKE-DELIVERY", "owner_confirmed")

    def test_instalments_and_recurring_refused_by_name(self):
        said = "payment plans are not supported in this release"
        cases = (
            lambda p: offer(p, "MAIN-ESS").setdefault("checkout", {}).update(billing_type="installment"),
            lambda p: offer(p, "MAIN-ESS").setdefault("checkout", {}).update(billing_type="recurring"),
            lambda p: offer(p, "MAIN-ESS").setdefault("checkout", {}).update(
                schedule=[{"sequence": 1, "due": "now", "amount_minor": 4850}]),
            lambda p: offer(p, "MAIN-ESS").update(installments=3),
            lambda p: offer(p, "MAIN-ESS")["price"].update(recurring="monthly"),
            lambda p: p.update(payment_plan={"parts": 3}),
        )
        for mutate in cases:
            payload = load("elevation")
            mutate(payload)
            self.refuses(payload, "AF-LAUNCH-INTAKE-PAYMENT-PLAN", "", said)

    def test_one_time_checkout_block_normalizes_with_native_ids_unset(self):
        normalized = intake.validate(load("elevation"))
        bump = next(o for o in normalized["offers"] if o["role"] == "bump")
        self.assertEqual(bump["checkout"], {
            "billing_type": "one_time", "schedule": [], "native_product_id": None,
            "native_price_id": None, "headline": "TEST ONLY bump headline",
            "benefit_explanation": "TEST ONLY bump benefit"})

    def test_bump_headline_and_benefit_go_together_and_only_on_a_bump(self):
        payload = load("elevation")
        del offer(payload, "BUMP")["checkout"]["benefit_explanation"]
        self.refuses(payload, "AF-LAUNCH-INTAKE-CHECKOUT", "checkout", "go together")
        payload = load("elevation")
        offer(payload, "U1")["checkout"] = {"headline": "h", "benefit_explanation": "b"}
        self.refuses(payload, "AF-LAUNCH-INTAKE-CHECKOUT", "checkout", "bump")

    def test_intake_carries_every_fact_a_s79_request_needs(self):
        """Proves the intake carries the facts, and that Skill 79's validator accepts a request built from them plus fixed read-back constants.

        83's own S79 probe acceptance is U-checkout-commerce-07's carried row (checkout.py).

        Fields Skill 79 reads back or derives (capability evidence, fulfillment rule, component
        ids, currency exponent) are fixed test constants; the terms, consent, bump copy, entitlement
        ids and prices come from the validated intake.
        """
        payload = load("elevation")
        payload["journey_mode"] = "single_simple"
        payload["offers"] = [o for o in payload["offers"] if o["offer_id"] in ("MAIN-ESS", "BUMP")]
        normalized = intake.validate(payload)
        main = next(o for o in normalized["offers"] if o["role"] == "main")
        bump = next(o for o in normalized["offers"] if o["role"] == "bump")
        terms = normalized["checkout_terms"]

        def price(o):
            return {"price_choice_id": o["offer_id"], "currency": o["price"]["currency"],
                    "currency_exponent": 2, "amount_minor": o["price"]["amount_minor"],
                    "billing_type": o["checkout"]["billing_type"],
                    "native_product_id": o["checkout"]["native_product_id"],
                    "native_price_id": o["checkout"]["native_price_id"],
                    "approval_status": "test_only"}

        request = {
            "tenant_id": normalized["tenant_id"], "location_id": normalized["location_id"],
            "launch_id": normalized["launch_id"], "launch_revision": normalized["revision"],
            "launch_plan_approval_ref": normalized["approval"]["ref"],
            "approved_plan_hash": normalized["approval"]["hash"],
            "checkout_mode": "combined_single_offer", "main_offer_id": main["offer_id"],
            "main_price": price(main), "quantity": 1, "selection_ref": None,
            "main_entitlement_ids": [main["offer_id"].lower()],
            "previously_purchased_entitlement_ids": [],
            "bump": {"component_id": "bump", "component_version": "1", "enabled": True,
                     "offer_id": bump["offer_id"], "applicable_main_offer_ids": [main["offer_id"]],
                     "entitlement_ids": [bump["offer_id"].lower()],
                     "headline": bump["checkout"]["headline"],
                     "benefit_explanation": bump["checkout"]["benefit_explanation"],
                     "price": price(bump), "default_selected": False,
                     "quantity_policy": "fixed_1", "fulfillment_rule_ref": "TEST-ONLY-FULFILLMENT"},
            "brand_ref": normalized["brand"]["ref"], "brand_revision": normalized["brand"]["hash"],
            "terms_ref": terms["terms_ref"], "consent_ref": terms["consent_ref"],
            "native_capability_evidence_ref": "TEST-ONLY-CAPABILITY",
            "successful_payment_next_route": main["delivery"]["destination"],
            "fulfillment_mapping_ref": "TEST-ONLY-FULFILLMENT",
            "test_only": normalized["test_only"],
            "failed_pending_requirements": {
                "failed_state_copy_ref": "TEST-ONLY-FAILED", "pending_state_copy_ref": "TEST-ONLY-PENDING",
                "retry_policy": "reconcile_native_records_first"},
        }
        validator_file = checkout.validator_path()
        spec = importlib.util.spec_from_file_location("s79_validate_checkout_under_test", validator_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.validate_request(request)  # raises on rejection


if __name__ == "__main__":
    unittest.main()
