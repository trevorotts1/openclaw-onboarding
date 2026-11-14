"""Recurring billing (weekly, monthly, quarterly, yearly) as the client SEES it, and through to the checkout.

A client who says an offer is "monthly" / "quarterly" / "$X a month" gets: a plan that says so before they
approve it, a delivery sheet that never says "one payment" for it, a launch record every consumer accepts
(Skill 71's schema, Skill 49's validator) and a Skill 79 request that carries the interval. Neutral values only.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
REPO = SKILL_ROOT.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "tests"))

import test_intake_validation as base  # noqa: E402
sys.path.insert(0, str(SKILL_ROOT / "fixtures"))
from launcher_core import checkout_instances, cli, delivery, image_plan, intake, launch_bridge, route  # noqa: E402
from test_checkout_instances import COMMERCIAL  # noqa: E402

CADENCES = (("weekly", "week", "/week"), ("monthly", "month", "/month"),
            ("quarterly", "quarter", "/quarter"), ("yearly", "year", "/year"),
            ("every three months", "quarter", "/quarter"))


def build(u1_word=None, d1_word=None):
    payload, doc = base.load("elevation"), base.answers_for("elevation")
    if u1_word:
        base.entry(doc, "U1")["billing"] = u1_word
    if d1_word:
        base.entry(doc, "D1")["billing"] = d1_word
    normalized = intake.validate(base.use_answers(payload, doc))
    with tempfile.TemporaryDirectory() as td:
        normalized["image_plan"] = {"brand_file": str(Path(td) / "brand.json"), "brand_owner": "TEST-ONLY Client"}
        inputs, _ = image_plan.resolve(normalized.get("image_plan"), test_only=normalized["test_only"])
        record = launch_bridge.to_launch_record(normalized, route.compile_route(normalized), inputs)
    return normalized, record


def price_of(record, slot):
    return next(o for o in record["offers"] if o["slot"] == slot)["prices"][0]


class ThePlanTheClientApprovesSaysHowOftenTheyAreCharged(unittest.TestCase):
    def test_every_cadence_is_in_the_plan_text_beside_the_price(self):
        for word, interval, per in CADENCES:
            normalized, record = build(u1_word=word)
            self.assertEqual(price_of(record, "upsell_1")["recurring_interval"], interval, word)
            text = cli.render_plan(normalized, record)
            self.assertIn(f"$67.00{per}", text, word)
            self.assertIn("recurring payments (", text, word)

    def test_a_one_payment_offer_next_to_a_recurring_one_still_says_one_payment(self):
        normalized, record = build(u1_word="monthly")
        text = cli.render_plan(normalized, record)
        self.assertIn("upsell_2: TEST ONLY U2, $47.00, one payment", text)
        self.assertIn("downsell_1", text)

    def test_the_plan_hash_changes_when_the_cadence_changes(self):
        _, monthly = build(u1_word="monthly")
        _, quarterly = build(u1_word="quarterly")
        self.assertNotEqual(cli._plan_hash(monthly), cli._plan_hash(quarterly))


class TheDeliverySheetNeverSaysOnePaymentForARecurringOffer(unittest.TestCase):
    def sheets(self, normalized, record):
        planned = delivery.plan(normalized, None)
        return {e["role"]: delivery._render(e, record) for e in planned["offers"]}

    def test_recurring_sheets_state_the_interval_and_one_payment_sheets_are_unchanged(self):
        normalized, record = build(u1_word="monthly", d1_word="yearly")
        sheets = self.sheets(normalized, record)
        self.assertIn("67.00 USD per month, until cancelled.", sheets["upsell_1"])
        self.assertNotIn("one payment", sheets["upsell_1"])
        self.assertIn("37.00 USD per year, until cancelled.", sheets["downsell_1"])
        self.assertIn("47.00 USD, one payment.", sheets["upsell_2"])
        plain_normalized, plain_record = build()
        self.assertIn("67.00 USD, one payment.", self.sheets(plain_normalized, plain_record)["upsell_1"])

    def test_the_planned_one_payment_entries_gain_no_new_fields(self):
        normalized, _ = build()
        for entry in delivery.plan(normalized, None)["offers"]:
            self.assertFalse({"billing_type", "recurring_interval"} & set(entry["price"]), entry["offer_id"])


class TheRecordReachesEveryConsumer(unittest.TestCase):
    def test_71_launch_context_and_49_validator_accept_each_cadence(self):
        spec = importlib.util.spec_from_file_location(
            "recurring_view_launch_context", REPO / "71-blackceo-signature-page" / "scripts" / "launch_context.py")
        lc = importlib.util.module_from_spec(spec)
        sys.modules["recurring_view_launch_context"] = lc
        spec.loader.exec_module(lc)
        schema = json.loads((REPO / "71-blackceo-signature-page" / "references" / "launch.schema.json").read_text())
        vlp = launch_bridge.substrate.dispatch().vlp
        for word, interval, _ in CADENCES:
            _, record = build(u1_word=word)
            self.assertEqual(lc.validate(record, schema, label="launch"), [], word)
            self.assertEqual(vlp.validate_launch(record), [], word)

    def test_the_main_offers_checkout_request_carries_the_interval_beside_the_recurring_type(self):
        for word, interval, _ in CADENCES:
            payload, doc = base.load("elevation"), base.answers_for("elevation")
            base.entry(doc, "MAIN-ESS")["billing"] = word
            normalized = intake.validate(base.use_answers(payload, doc))
            graph = route.compile_route(normalized)
            with tempfile.TemporaryDirectory() as td:
                normalized["image_plan"] = {"brand_file": str(Path(td) / "brand.json"), "brand_owner": "TEST-ONLY Client"}
                inputs, _ = image_plan.resolve(normalized.get("image_plan"), test_only=normalized["test_only"])
                record = launch_bridge.to_launch_record(normalized, graph, inputs)
            built = checkout_instances.build(normalized, graph, record, COMMERCIAL)
            essential = next(i for i in built["instances"] if i["main_offer_id"] == "MAIN-ESS")
            self.assertEqual(essential["validation"]["result"], "accepted", word)
            self.assertEqual((essential["request"]["main_price"]["billing_type"],
                              essential["request"]["main_price"]["recurring_interval"]), ("recurring", interval), word)
            other = next(i for i in built["instances"] if i["main_offer_id"] != "MAIN-ESS")
            self.assertEqual(other["request"]["main_price"]["billing_type"], "one_time")
            self.assertNotIn("recurring_interval", other["request"]["main_price"])

    def test_installments_are_still_refused_with_the_shared_sentence(self):
        payload, doc = base.load("elevation"), base.answers_for("elevation")
        base.entry(doc, "U1")["billing"] = "installments"
        with self.assertRaises(intake.IntakeError) as ctx:
            intake.validate(base.use_answers(payload, doc))
        self.assertIn("payment plans are not supported in this release", ctx.exception.detail)
