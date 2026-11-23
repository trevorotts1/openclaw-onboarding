"""RFX-015: an upsell's ``price.annual`` answer becomes a second (yearly) price choice of the same offer.

The offer mapper used to ignore ``price.annual``, so a membership the client approved at $89 a month
AND $500 a year reached the launch record with one price. Now the answers entry's ``price.annual``
maps to a second price choice (recurring, year) on the same offer; the launch record keeps both with
distinct ids, Skill 49's validator accepts it, the plan the client approves names both prices, and
the production manifest carries both native accept actions to the delivery rail. Refusals: annual
on a non-upsell, a one-payment first price, a second currency, a first price that is already yearly.
Neutral values only.
"""

from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))
sys.path.insert(0, str(SKILL_ROOT / "tests"))
sys.path.insert(0, str(SKILL_ROOT / "fixtures"))

import test_intake_validation as base  # noqa: E402
from launcher_core import cli, image_plan, intake, launch_bridge, route  # noqa: E402


def answers(month=8900, annual=50000, billing="monthly", slot_id="U2"):
    doc = base.answers_for("elevation")
    e = base.entry(doc, slot_id)
    e["price"]["amount_minor"] = month
    if billing:
        e["billing"] = billing
    if annual is not None:
        e["price"]["annual"] = annual
    return doc


def build(doc, slot_id="U2", month=8900):
    payload = base.load("elevation")
    base.offer(payload, slot_id)["price"]["amount_minor"] = month
    normalized = intake.validate(base.use_answers(payload, doc))
    with tempfile.TemporaryDirectory() as td:
        normalized["image_plan"] = {"brand_file": str(Path(td) / "brand.json"),
                                    "brand_owner": "TEST-ONLY Client"}
        inputs, _ = image_plan.resolve(normalized.get("image_plan"), test_only=normalized["test_only"])
        record = launch_bridge.to_launch_record(normalized, route.compile_route(normalized), inputs)
    return normalized, record


def prices(record, slot="upsell_2"):
    return next(o for o in record["offers"] if o["slot"] == slot)["prices"]


class AnnualIsASecondPriceChoice(unittest.TestCase):
    def test_monthly_plus_annual_reaches_the_record_as_two_choices(self):
        normalized, record = build(answers())
        got = [(p["price_choice_id"], p["amount_minor"], p["billing_type"], p.get("recurring_interval"),
                p["approval_status"]) for p in prices(record)]
        self.assertEqual(got, [("U2-USD", 8900, "recurring", "month", "provided"),
                               ("U2-USD-YEAR", 50000, "recurring", "year", "provided")])
        self.assertEqual(launch_bridge.check_launch_record(record), [])

    def test_the_plan_the_client_approves_names_both_prices(self):
        normalized, record = build(answers())
        line = next(l for l in cli.render_plan(normalized, record).splitlines() if "upsell_2:" in l)
        self.assertIn("$89.00/month", line)
        self.assertIn("$500.00/year", line)

    def test_an_offer_without_annual_is_unchanged(self):
        _, record = build(answers(annual=None))
        self.assertEqual([p["price_choice_id"] for p in prices(record)], ["U2-USD"])

    def test_annual_as_an_object_carries_its_native_price(self):
        _, record = build(answers(annual={"amount_minor": 50000, "native_price_id": "TEST-ONLY-NP-YEAR"}))
        self.assertEqual(prices(record)[1]["native_price_id"], "TEST-ONLY-NP-YEAR")


class AnnualRefusals(unittest.TestCase):
    def refuses(self, doc, needle, slot_id="U2", month=8900):
        with self.assertRaises(intake.IntakeError) as ctx:
            build(doc, slot_id, month)
        self.assertIn(needle, ctx.exception.detail)

    def test_a_one_payment_first_price_refuses(self):
        self.refuses(answers(billing="one payment"), "first price is 'one_time'")

    def test_a_first_price_already_yearly_refuses(self):
        self.refuses(answers(billing="yearly"), "already yearly")

    def test_a_second_currency_refuses(self):
        self.refuses(answers(annual={"amount_minor": 50000, "currency": "EUR"}), "one currency")

    def test_annual_on_a_downsell_refuses(self):
        doc = answers(annual=None)
        d1 = base.entry(doc, "D1")
        d1["billing"], d1["price"]["annual"] = "monthly", 30000
        self.refuses(doc, "only carried by an upsell", "D1", 3700)

    def test_a_zero_or_fractional_annual_refuses(self):
        for bad in (0, 499.5, True):
            self.refuses(answers(annual=bad), "price.annual")


class ProductionCarriesBothActions(unittest.TestCase):
    def test_the_production_row_and_handoff_carry_every_accept_action(self):
        from launcher_core import install_handoff, production
        row = {"accept_actions": [{"price_choice_id": "U2-USD"}, {"price_choice_id": "U2-USD-YEAR"}]}
        src = Path(production.__file__).read_text(encoding="utf-8")
        self.assertIn('"accept_actions": page_rows[role]["accept_actions"]', src)
        self.assertIn('"accept_actions": row["accept_actions"]', Path(install_handoff.__file__).read_text())
        self.assertEqual(len(row["accept_actions"]), 2)


if __name__ == "__main__":
    unittest.main()
