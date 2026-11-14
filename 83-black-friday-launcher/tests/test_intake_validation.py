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
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import checkout, intake, launch_bridge, route  # noqa: E402

FIXTURES = SKILL_ROOT / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name / "intake.json").read_text(encoding="utf-8"))


def offer(payload: dict, offer_id: str) -> dict:
    return next(o for o in payload["offers"] if o["offer_id"] == offer_id)


_ANSWERS_DIR = tempfile.TemporaryDirectory()  # the answers file copies the cases below edit


def answers_for(name: str) -> dict:
    return json.loads((FIXTURES / name / "answers.json").read_text(encoding="utf-8"))


def use_answers(payload: dict, doc: dict) -> dict:
    """Point the intake at a copy of the client's answers (written to a tmp dir) and return the intake."""
    text = json.dumps(doc, sort_keys=True)
    path = Path(_ANSWERS_DIR.name) / f"answers-{abs(hash(text))}.json"
    path.write_text(text, encoding="utf-8")
    payload["answers_file"] = str(path)
    return payload


def entry(doc: dict, offer_id: str) -> dict:
    """The answers entry (an item of the packages list, or a slot's value) that holds this offer."""
    for key, answer in doc["answers"].items():
        value = answer.get("value")
        for item in (value if isinstance(value, list) else [value]):
            if isinstance(item, dict) and item.get("offer_id") == offer_id:
                return item
    raise KeyError(offer_id)


def reprice(payload: dict, offer_id: str, name: str = "", **price) -> dict:
    """A price (or name) the client really gave: the intake AND the client's answers carry it together."""
    which = "seven-figure-preneur" if payload["journey_mode"] == "folded_levels" else "elevation"
    doc = answers_for(which)
    if name:
        offer(payload, offer_id)["name"] = name
        entry(doc, offer_id)["display_name"] = name.strip()  # the intake strips names; the answers hold the clean one
    offer(payload, offer_id)["price"].update(price)
    entry(doc, offer_id)["price"].update({k: v for k, v in price.items() if k in ("amount_minor", "currency")})
    return use_answers(payload, doc)


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

    def test_test_only_has_no_default_and_an_absent_one_is_refused(self):
        # Issue 36: a forgotten `false` used to build a practice package with every live gate off.
        payload = load("elevation")
        del payload["test_only"]
        err = self.refuses(payload, "AF-LAUNCH-INTAKE-TEST-ONLY", "test_only")
        self.assertIn("say true (practice) or false (client)", err.detail)
        self.assertNotIn("test_only", intake.PERMITTED_DEFAULTS)  # the default is gone, not just unused
        self.assertIn("test_only", intake.EXPLICIT_FIELDS)

    def test_a_said_test_only_is_recorded_as_supplied_never_as_a_default(self):
        for said in (True, False):
            payload = load("elevation")
            payload["test_only"] = said
            normalized = intake.validate(payload)
            self.assertIs(normalized["test_only"], said)
            self.assertEqual(normalized["provenance"]["test_only"], "supplied")

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


class LaunchIdShape(IntakeCase):  # rehearsal F9: refuse at intake what the launch-plan schema refuses later
    def test_ids_the_launch_plan_schema_refuses_are_refused_at_intake(self):
        for bad in ("TEST-REHEARSAL-V2-UPPER", "Bf-2026", "-bf-2026", "bf_2026", "bf 2026", "ab"):
            payload = load("elevation")
            payload["launch_id"] = bad
            self.refuses(payload, "AF-LAUNCH-INTAKE-SHAPE", "launch_id")

    def test_a_slug_the_schema_accepts_passes(self):
        for good in ("bf-2026", "elevation-2026-11", "9lives", "abc"):
            payload = load("elevation")
            payload["launch_id"] = good
            self.assertEqual(intake.validate(payload)["launch_id"], good)


class OfferSetCoherence(IntakeCase):  # PRD-14
    def test_mixed_currencies_refused(self):
        payload = load("elevation")
        reprice(payload, "BUMP", currency="EUR")
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
        reprice(payload, "U1", name="  test only ESSENTIAL ")
        self.refuses(payload, "AF-LAUNCH-INTAKE-OFFER", "U1", "display name")

    def test_multiple_options_identical_price_needs_different_levels(self):
        payload = load("elevation")
        pro, ess = offer(payload, "MAIN-PRO"), offer(payload, "MAIN-ESS")
        reprice(payload, "MAIN-PRO", amount_minor=ess["price"]["amount_minor"])
        intake.validate(payload)  # the levels differ, so identical prices are allowed
        pro["level"] = copy.deepcopy(ess["level"])
        self.refuses(payload, "AF-LAUNCH-INTAKE-OFFER", "offers", "same level")

    def test_folded_levels_identical_price_refused(self):
        payload = load("seven-figure-preneur")
        reprice(payload, "MAIN-B", amount_minor=9700)
        self.refuses(payload, "AF-LAUNCH-INTAKE-OFFER", "offers", "identical prices")

    def test_price_sanity_bounds_need_confirmation(self):
        for amount in (99, 10_000_001):
            payload = reprice(load("elevation"), "BUMP", amount_minor=amount)
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


class PriceProvenance(IntakeCase):  # PRD-03: the client's answers file is the only price authority
    def test_both_fixtures_resolve_every_price_to_a_provided_owner_answer(self):
        for name in ("elevation", "seven-figure-preneur"):
            normalized = intake.validate(load(name))
            for o in normalized["offers"]:
                canon = o["canonical"]
                self.assertEqual(canon["prices"][0]["approval_status"], "provided", (name, o["offer_id"]))
                self.assertEqual(canon["source_kind"], "owner", (name, o["offer_id"]))
                self.assertEqual(o["price"]["source_ref"], canon["source_ref"])

    def test_an_offer_whose_price_has_no_source_ref_is_refused(self):
        payload = load("elevation")
        del offer(payload, "BUMP")["price"]["source_ref"]
        self.refuses(payload, "AF-LAUNCH-INTAKE-PROVENANCE", "offers[3].price.source_ref")

    def test_a_ref_that_is_not_an_answers_entry_is_refused(self):
        for ref in ("answers-file:made_up_price", "launcher-intake:L1:r1"):
            payload = load("elevation")
            offer(payload, "BUMP")["price"]["source_ref"] = ref
            self.refuses(payload, "AF-LAUNCH-INTAKE-PROVENANCE", "offers[3].price.source_ref")

    def test_a_real_ref_with_a_different_amount_is_refused(self):
        payload = load("elevation")
        offer(payload, "BUMP")["price"]["amount_minor"] = 1
        payload["offers"][3]["price"]["bounds_confirmed"] = True  # past the sanity bounds, so only provenance can refuse
        self.refuses(payload, "AF-LAUNCH-INTAKE-PROVENANCE", "offers[3].price.source_ref")

    def test_an_intake_with_no_answers_file_is_refused(self):
        payload = load("elevation")
        del payload["answers_file"]
        self.refuses(payload, "AF-LAUNCH-INTAKE-MISSING", "answers_file")

    def test_an_answers_file_that_cannot_be_read_or_is_the_wrong_schema_is_refused(self):
        payload = load("elevation")
        payload["answers_file"] = str(Path(_ANSWERS_DIR.name) / "absent.json")
        self.refuses(payload, "AF-LAUNCH-INTAKE-PROVENANCE", "answers_file")
        doc = answers_for("elevation")
        doc["schema"] = "something-else/v9"
        self.refuses(use_answers(load("elevation"), doc), "AF-LAUNCH-INTAKE-PROVENANCE", "answers_file")

    def test_a_suggested_price_carries_its_recommendation_status_into_the_canonical_offer(self):
        doc = answers_for("elevation")
        doc["answers"]["packages"]["status"] = "suggested"
        normalized = intake.validate(use_answers(load("elevation"), doc))
        for o in normalized["offers"]:
            want = ("recommended_unapproved", "recommendation") if o["role"] == "main" else ("provided", "owner")
            self.assertEqual((o["canonical"]["prices"][0]["approval_status"], o["canonical"]["source_kind"]),
                             want, o["offer_id"])


class UnsupportedSecondDownsell(IntakeCase):  # PRD-30
    def test_a_downsell_2_offer_is_refused_by_name_never_dropped(self):
        payload = load("elevation")
        payload["offers"].append({
            "offer_id": "down-2", "name": "Down Two", "role": "downsell_2",
            "price": {"amount_minor": 2700, "currency": "USD"},
            "level": {"state": "supplied", "name": "Down Two", "deliverables": ["Down Two access"]},
            "delivery": {"destination": "https://delivery.test-only.invalid/elevation/down-2", "owner_confirmed": True}})
        err = self.refuses(payload, "AF-LAUNCH-INTAKE-OFFER", f"offers[{len(payload['offers']) - 1}].role")
        self.assertIn("a second downsell is not supported in this release", str(err))


class PromotionFacts(IntakeCase):  # PRD-15, DECISIONS-NEEDED[37]: a fact record only
    PROMOTION = {"kind": "A discount", "limitations": "only 50 seats at this price", "buyers": None, "followup": None,
                 "seat_limit": 50, "seat_limit_state": "limited",
                 "source_refs": ["answers-file:bf_promotion", "answers-file:bf_limitations"]}

    def test_a_supplied_promotion_reaches_the_normalized_intake(self):
        payload = load("elevation")
        payload["promotion"] = dict(self.PROMOTION)
        promo = intake.validate(payload)["promotion"]
        self.assertEqual((promo["seat_limit"], promo["kind"]), (50, "A discount"))
        self.assertNotIn("promotion", intake.validate(load("elevation")))  # never defaulted

    def test_an_undeclared_promotion_key_is_refused(self):
        payload = load("elevation")
        payload["promotion"] = dict(self.PROMOTION, compare_at_claim="was $997")
        self.refuses(payload, "AF-LAUNCH-INTAKE-PROMOTION", "promotion")

    def test_a_bad_promotion_value_is_refused(self):
        for bad in ({"kind": "A free car"}, {"seat_limit": 0}, {"seat_limit": 50, "seat_limit_state": "no_limit"},
                    {"seat_limit": None, "seat_limit_state": "limited"}, {"source_refs": []},
                    {"source_refs": ["launcher-intake:x"]}, {"limitations": 5}):
            payload = load("elevation")
            payload["promotion"] = dict(self.PROMOTION, **bad)
            self.refuses(payload, "AF-LAUNCH-INTAKE-PROMOTION", "promotion")


class ClientChoices(IntakeCase):  # CON-04: what the CLIENT chose to leave out of the launch
    def test_a_recorded_waiver_validates_and_is_carried(self):
        payload = load("elevation")
        payload["client_choices"] = ["email_only"]
        self.assertEqual(intake.validate(payload)["client_choices"], ["email_only"])
        self.assertEqual(intake.validate(load("elevation"))["client_choices"], [])

    def test_an_unknown_or_malformed_choice_is_refused(self):
        for bad in (["skip_everything"], "email_only", ["email_only", "email_only"], [5]):
            payload = load("elevation")
            payload["client_choices"] = bad
            self.refuses(payload, "AF-LAUNCH-INTAKE-CHOICES", "client_choices")


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

    def test_instalments_are_refused_by_name_and_stated_recurring_is_accepted(self):
        said = "payment plans are not supported in this release"
        # The vocabulary the checkout can carry is one_time plus recurring (from the shared
        # billing module); instalments stay refused everywhere, including as separate keys.
        refused = (
            lambda p: offer(p, "MAIN-ESS").setdefault("checkout", {}).update(billing_type="installment"),
            lambda p: offer(p, "MAIN-ESS").setdefault("checkout", {}).update(
                schedule=[{"sequence": 1, "due": "now", "amount_minor": 4850}]),
            lambda p: offer(p, "MAIN-ESS").update(installments=3),
            lambda p: offer(p, "MAIN-ESS")["price"].update(recurring="monthly"),
            lambda p: p.update(payment_plan={"parts": 3}),
        )
        for mutate in refused:
            payload = load("elevation")
            mutate(payload)
            self.refuses(payload, "AF-LAUNCH-INTAKE-PAYMENT-PLAN", "", said)
        # a billing word the release carries as recurring, stated as a checkout billing_type,
        # is vocabulary-checked: the shared sentence names the plan-time refusal for trial.
        for bad in ("trial", "payment_plan", "unknown billing", 5, True):
            payload = load("elevation")
            offer(payload, "MAIN-ESS").setdefault("checkout", {})["billing_type"] = bad
            if bad == "trial":  # in the shared vocabulary but plan-time refused, by the shared sentence
                self.refuses(payload, "AF-LAUNCH-INTAKE-PAYMENT-PLAN", "billing_type", said)
            else:
                self.refuses(payload, "AF-LAUNCH-INTAKE-PAYMENT-PLAN", "billing_type")

    def test_stated_recurring_checkout_rides_verbatim_and_agrees_with_the_answers(self):
        payload = load("elevation")
        doc = answers_for("elevation")
        for oid in ("U1", "D1"):
            offer(payload, oid).setdefault("checkout", {})["billing_type"] = "recurring"
            entry(doc, oid)["price"]["billing_type"] = "recurring"
            entry(doc, oid)["billing"] = "monthly" if oid == "U1" else "quarterly"
        normalized = intake.validate(use_answers(payload, doc))
        for oid, cadence in (("U1", "month"), ("D1", "quarter")):
            got = next(o for o in normalized["offers"] if o["offer_id"] == oid)
            self.assertEqual(got["checkout"]["billing_type"], "recurring")
            canon = got["canonical"]["prices"][0]
            self.assertEqual((canon["billing_type"], canon["recurring_interval"]), ("recurring", cadence))

    def test_the_answers_cadence_word_is_the_billing_fact_when_nothing_is_stated(self):
        """The shape: the intake states no billing, the client's per-offer answer does."""
        for oid, word, interval in (("U1", "monthly", "month"), ("D1", "quarterly", "quarter")):
            payload = load("elevation")
            doc = answers_for("elevation")
            entry(doc, oid)["billing"] = word
            normalized = intake.validate(use_answers(payload, doc))
            canon = next(o for o in normalized["offers"] if o["offer_id"] == oid)["canonical"]["prices"][0]
            self.assertEqual((canon["billing_type"], canon["recurring_interval"]), ("recurring", interval),
                             (oid, word))

    def test_recurring_without_any_cadence_is_refused_at_plan_time_not_at_checkout(self):
        payload = load("elevation")
        doc = answers_for("elevation")
        entry(doc, "U1")["price"]["billing_type"] = "recurring"
        err = self.refuses(use_answers(payload, doc), "AF-LAUNCH-INTAKE-PAYMENT-PLAN", "price", "no recurring_interval")
        self.assertIn("material disclosure", err.detail)

    def test_a_cadence_word_the_release_does_not_carry_is_refused_not_flattened(self):
        payload = load("elevation")
        doc = answers_for("elevation")
        entry(doc, "U1")["billing"] = "every other month"
        err = self.refuses(use_answers(payload, doc), "AF-LAUNCH-INTAKE-PROVENANCE", "price",
                           "every other month")
        self.assertIn("not one this release carries", err.detail)

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


class SharedBillingVocabularyMissing(IntakeCase):  # issue 70: no vocabulary installed means nothing is judged against it
    def test_a_launcher_without_the_shared_billing_file_refuses_by_name(self):
        with tempfile.TemporaryDirectory() as empty, mock.patch.object(intake, "REPO_ROOT", Path(empty)), \
                mock.patch.dict(sys.modules):
            sys.modules.pop("signature_launch_billing", None)
            with self.assertRaises(intake.IntakeError) as ctx:
                intake.billing_module()
        self.assertTrue(ctx.exception.code.startswith("AF-LAUNCH-INTAKE-PAYMENT-PLAN"))
        self.assertIn("not installed", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
