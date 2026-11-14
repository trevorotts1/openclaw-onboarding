#!/usr/bin/env python3
"""Recurring billing (weekly, monthly, quarterly, yearly) through Skill 49's own path: the interview
records the client's cadence, the plan the client approves says it ("$49.00/month"), the launch plan and
the record validator carry and check the interval, and an upsell's disclosure is derived from it.
Neutral test values only. Free: no network, no model.
Run: python3 -m pytest 49-signature-funnel/scripts/test_recurring_billing.py -q
"""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import launch_intake as li  # noqa: E402
import launch_plan as lp  # noqa: E402
import upsell_wrapper as uw  # noqa: E402
import validate_launch_plan as vlp  # noqa: E402

HERE = Path(__file__).resolve()
BILLING = HERE.parents[2] / "shared-utils" / "signature_launch_contract" / "billing.py"
CADENCES = (("Weekly", "week", "weekly", "/week"), ("Monthly", "month", "monthly", "/month"),
            ("Quarterly", "quarter", "quarterly", "/quarter"), ("Yearly", "year", "yearly", "/year"))


def price(minor, **extra):
    return dict({"amount_minor": minor, "currency": "USD"}, **extra)


def session(**fields):
    known = {k.replace("__", "."): v for k, v in fields.items()}
    return li.new_session(tenant_id="t1", location_id="loc1", launch_id="L1",
                          client_identity_ref="client:1", known=known, test_only=True)


def single_main(billing_word, **extra):
    s = session(journey_mode="single_simple",
                offers__main__description={"display_name": "Example Monthly Coaching", "deliverables": ["x"]},
                offers__main__price=price(4900), **extra)
    li.answer(s, "b3_billing", billing_word)
    return s


class TheInterviewRecordsTheCadence(unittest.TestCase):
    def test_each_cadence_word_sets_billing_type_and_interval(self):
        for word, interval, _, _ in CADENCES:
            s = single_main(word)
            self.assertEqual(s["answers"]["offers.main.billing_type"]["value"], "recurring", word)
            self.assertEqual(s["answers"]["offers.main.recurring_interval"]["value"], interval, word)

    def test_the_banks_three_choices_keep_their_meaning(self):
        s = single_main("All at once")
        self.assertEqual(s["answers"]["offers.main.billing_type"]["value"], "one_time")
        self.assertIsNone(s["answers"]["offers.main.recurring_interval"]["value"])
        s = single_main("In parts / trial first")
        self.assertEqual(s["answers"]["offers.main.billing_type"]["value"], "installment")

    def test_the_main_offer_carries_the_interval_into_the_launch_record(self):
        for word, interval, _, _ in CADENCES:
            r = li.assemble_plan(single_main(word))
            p = r["plan"]["offers"][0]["prices"][0]
            self.assertEqual((p["billing_type"], p["recurring_interval"]), ("recurring", interval), word)
            self.assertEqual(vlp.validate_launch(r["plan"]), [], word)

    def test_a_one_payment_main_carries_no_interval(self):
        r = li.assemble_plan(single_main("All at once"))
        self.assertNotIn("recurring_interval", r["plan"]["offers"][0]["prices"][0])


class ThePlanTheClientApprovesSaysIt(unittest.TestCase):
    def test_the_summary_shows_the_price_per_interval_for_every_cadence(self):
        for word, _, said, per in CADENCES:
            s = single_main(word)
            self.assertEqual(li.assemble_plan(s)["state"], "awaiting_plan_approval", word)
            text = li.render_summary(s)
            self.assertIn("$49.00" + per, text, word)

    def test_a_one_payment_summary_is_unchanged(self):
        s = single_main("All at once")
        li.assemble_plan(s)
        text = li.render_summary(s)
        self.assertIn("$49.00", text)
        self.assertNotIn("/month", text)

    def test_packages_and_extras_carry_their_own_cadence(self):
        pk = [{"display_name": "Basic", "price": price(4900), "billing": "monthly", "deliverables": ["a"]},
              {"display_name": "Plus", "price": price(12900), "deliverables": ["a"]}]
        s = session(journey_mode="multiple_options", offers__main__packages=pk)
        r = li.assemble_plan(s)
        self.assertEqual(r["state"], "awaiting_plan_approval", r)
        by = {o["display_name"]: o["prices"][0] for o in r["plan"]["offers"]}
        self.assertEqual((by["Basic"]["billing_type"], by["Basic"]["recurring_interval"]), ("recurring", "month"))
        self.assertEqual(by["Plus"]["billing_type"], "one_time")
        text = li.render_summary(s)
        self.assertIn("$49.00/month, billed monthly", text)
        self.assertIn("$129.00, one payment", text)

    def test_an_upsell_priced_per_quarter(self):
        s = session(journey_mode="single_simple",
                    offers__main__description={"display_name": "Example Course", "deliverables": ["x"]},
                    offers__main__price=price(12900), extras={"upsell_1": True, "downsell_1": False, "upsell_2": False},
                    offers__upsell_1={"display_name": "Example Quarterly Club", "price": price(9900),
                                      "billing": "every three months", "deliverables": ["y"]})
        li.answer(s, "b3_billing", "All at once")
        r = li.assemble_plan(s)
        self.assertEqual(r["state"], "awaiting_plan_approval", r)
        u1 = next(o for o in r["plan"]["offers"] if o["slot"] == "upsell_1")["prices"][0]
        self.assertEqual((u1["billing_type"], u1["recurring_interval"]), ("recurring", "quarter"))
        self.assertIn("$99.00/quarter", li.render_summary(s))

    def test_a_cadence_word_this_release_does_not_carry_is_a_missing_fact_not_one_payment(self):
        pk = [{"display_name": "Basic", "price": price(4900), "billing": "every other month", "deliverables": ["a"]},
              {"display_name": "Plus", "price": price(12900), "deliverables": ["a"]}]
        r = li.assemble_plan(session(journey_mode="multiple_options", offers__main__packages=pk))
        self.assertEqual(r["state"], "awaiting_missing_fact")
        self.assertTrue(any("every other month" in m and "how Basic bills" in m for m in r["missing"]), r["missing"])


class TheLaunchPlanAndRecordValidatorCarryTheInterval(unittest.TestCase):
    def record(self, interval="month", **price_extra):
        r = copy.deepcopy(li.assemble_plan(single_main("Monthly"))["plan"])
        p = r["offers"][0]["prices"][0]
        if interval is None:
            p.pop("recurring_interval", None)
        else:
            p["recurring_interval"] = interval
        p.update(price_extra)
        return r

    def test_the_validator_vocabulary_is_the_shared_one(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("billing_for_test", BILLING)
        shared = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(shared)
        self.assertEqual(vlp.BILLING_TYPES, shared.BILLING_TYPES)
        self.assertEqual(vlp.RECURRING_INTERVALS, shared.RECURRING_INTERVALS)

    def test_every_carried_interval_validates(self):
        for _, interval, _, _ in CADENCES:
            self.assertEqual(vlp.validate_launch(self.record(interval)), [], interval)

    def test_an_interval_outside_the_four_is_refused(self):
        fails = vlp.validate_launch(self.record("fortnight"))
        self.assertTrue(any("fortnight" in f and "recurring_interval" in f for f in fails), fails)

    def test_recurrence_terms_on_a_one_payment_price_are_refused(self):
        fails = vlp.validate_launch(self.record("month", billing_type="one_time"))
        self.assertTrue(any("recurrence terms" in f for f in fails), fails)

    def test_a_recurring_price_with_no_interval_and_no_schedule_is_refused(self):
        fails = vlp.validate_launch(self.record(None))
        self.assertTrue(any("neither a recurring_interval nor a schedule" in f for f in fails), fails)

    def test_the_launch_plan_package_names_the_interval_and_accepts_it_as_the_terms(self):
        launch = self.record("quarter")
        pkg = lp._package_record(launch["offers"][0], 0)
        self.assertEqual((pkg["billing_type"], pkg["recurring_interval"]), ("recurring", "quarter"))
        missing = []
        lp._offer_block(launch, {}, missing)
        self.assertFalse([m for m in missing if "terms" in m or "interval" in m], missing)

    def test_the_launch_plan_still_asks_for_terms_when_a_recurring_price_has_no_interval(self):
        missing = []
        lp._offer_block(self.record(None), {}, missing)
        self.assertTrue(any("exact recurring terms" in m for m in missing), missing)

    def test_installment_and_trial_stay_refused_with_the_shared_sentence(self):
        for kind in ("installment", "trial"):
            missing = []
            lp._offer_block(self.record(None, billing_type=kind, schedule=[{"amount_minor": 1000, "due": "now"}]), {}, missing)
            self.assertTrue(any("payment plans are not supported in this release" in m for m in missing), (kind, missing))


class AnUpsellsDisclosureComesFromTheRecordsInterval(unittest.TestCase):
    def offer(self, interval, billing="recurring"):
        p = {"price_choice_id": "U1-USD", "currency": "USD", "amount_minor": 4900, "billing_type": billing,
             "native_price_id": None, "schedule": [], "approval_status": "approved"}
        if interval:
            p["recurring_interval"] = interval
        return {"offer_id": "U1", "slot": "upsell_1", "prices": [p]}

    def test_each_interval_states_what_recurs_and_how_often(self):
        want = {"week": "then USD 49.00 per week until cancelled", "month": "then USD 49.00 per month until cancelled",
                "quarter": "then USD 49.00 every 3 months until cancelled", "year": "then USD 49.00 per year until cancelled"}
        for interval, phrase in want.items():
            problems = []
            block = uw._disclosure_block(self.offer(interval), {}, problems)
            self.assertEqual(problems, [], interval)
            self.assertIn(phrase, block["disclosure_text"], interval)
            self.assertNotIn("per every", block["disclosure_text"])
            self.assertIn("USD 49.00 today", block["disclosure_text"])

    def test_a_quarter_is_three_months_in_the_terms(self):
        block = uw._disclosure_block(self.offer("quarter"), {}, [])
        self.assertEqual((block["recurring_terms"]["interval"], block["recurring_terms"]["interval_count"]), ("month", 3))

    def test_a_sidecar_that_contradicts_the_record_fails_closed(self):
        problems = []
        sidecar = {"disclosure": {"recurring_terms": {"interval": "year", "interval_count": 1, "cycles": None}}}
        self.assertIsNone(uw._disclosure_block(self.offer("month"), sidecar, problems))
        self.assertTrue(any("contradiction fails closed" in p for p in problems), problems)

    def test_a_sidecar_that_agrees_is_used(self):
        problems = []
        sidecar = {"disclosure": {"recurring_terms": {"interval": "month", "interval_count": 3, "cycles": None}}}
        self.assertIsNotNone(uw._disclosure_block(self.offer("quarter"), sidecar, problems))
        self.assertEqual(problems, [])

    def test_a_recurring_price_with_no_interval_and_no_sidecar_still_names_the_missing_terms(self):
        problems = []
        self.assertIsNone(uw._disclosure_block(self.offer(None), {}, problems))
        self.assertTrue(any("disclosure.recurring_terms" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
