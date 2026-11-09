#!/usr/bin/env python3
"""U-products-06: the plan summary the client approves shows every offer, deliverables are a
list, recommendations are not owner-sourced, journey words match whole words, money uses the
currency's own exponent. Free: no network, no model.
Run: python3 -m pytest 49-signature-funnel/scripts/test_launch_intake_summary.py -q
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import launch_intake as li  # noqa: E402

USD = "USD"


def price(minor, cur=USD):
    return {"amount_minor": minor, "currency": cur}


def known(**fields):
    return {k.replace("__", "."): v for k, v in fields.items()}


def session(known_fields):
    return li.new_session(tenant_id="t1", location_id="loc1", launch_id="L1",
                          client_identity_ref="client:1", known=known_fields,
                          test_only=True)


def packages(names_prices, cur=USD):
    return [{"display_name": n, "price": price(p, cur), "deliverables": ["a", "b"]}
            for n, p in names_prices]


def assembled(known_fields):
    s = session(known_fields)
    r = li.assemble_plan(s)
    assert "plan" in r, r
    return s


class EveryOfferInTheSummary(unittest.TestCase):
    def check_all(self, s):
        text = li.render_summary(s)
        for o in s["plan"]["offers"]:
            p = o["prices"][0]
            self.assertIn(o["display_name"], text, o["offer_id"])
            self.assertIn(li._money_display(p["amount_minor"], p["currency"]), text,
                          o["offer_id"])
        return text

    def test_folded_levels_shows_all_three_levels(self):
        lv = [("Level 1", 49700), ("Level 2", 99700), ("Level 3", 249700)]
        s = assembled(known(journey_mode="folded_levels", offers__main__packages=packages(lv)))
        text = self.check_all(s)
        for name, minor in lv:
            self.assertIn(name, text)
            self.assertIn(f"${minor // 100:,}.00", text)
        self.assertNotIn("USD ", text)

    def test_multiple_options_lists_billing_and_deliverable_count(self):
        lv = [("Basic", 19700), ("Plus", 49700)]
        s = assembled(known(journey_mode="multiple_options", offers__main__packages=packages(lv)))
        text = self.check_all(s)
        self.assertIn("one payment", text)
        self.assertIn("2 deliverables", text)

    def test_single_simple_with_every_extra(self):
        s = assembled(known(
            journey_mode="single_simple",
            offers__main__description={"display_name": "Main Course", "deliverables": ["x"]},
            offers__main__price=price(49700),
            extras={"upsell_1": True, "downsell_1": True, "upsell_2": True},
            bump_enabled=True,
            offers__bump={"display_name": "Bump Pack", "price": price(1900)},
            offers__upsell_1={"display_name": "VIP Day", "price": price(99700)},
            offers__downsell_1={"display_name": "Mini Day", "price": price(29700)},
            offers__upsell_2={"display_name": "Mastermind", "price": price(199700)}))
        self.check_all(s)

    def test_jpy_is_not_divided_by_100(self):
        s = assembled(known(
            journey_mode="single_simple",
            offers__main__description={"display_name": "Course", "deliverables": ["x"]},
            offers__main__price=price(500000, "JPY")))
        text = li.render_summary(s)
        self.assertIn("¥500,000", text)
        self.assertIn("JPY 500,000", text)
        self.assertEqual(li._money_display(50000, "JPY"), "¥50,000")


class Deliverables(unittest.TestCase):
    def test_a4_answer_is_a_list_and_exclusions_stay_empty(self):
        s = session({})
        li.answer(s, "a4_deliverables", "12 video lessons, 4 live calls")
        self.assertEqual(li._get(s, "offers.main.deliverables")["value"],
                         ["12 video lessons", "4 live calls"])
        self.assertIsNone(li._get(s, "offers.main.exclusions"))
        s["answers"]["offers.main.description"] = {"value": "Course", "state": "provided"}
        s["answers"]["offers.main.price"] = {"value": price(100), "state": "provided"}
        self.assertEqual(li._offer_from_answers(s, "main", "offers.main.description",
                                                "MAIN")["exclusions"], [])
        li.answer(s, "a4b_exclusions", "no refunds after 30 days; no 1:1 coaching")
        o = li._offer_from_answers(s, "main", "offers.main.description", "MAIN")
        self.assertEqual(o["exclusions"], ["no refunds after 30 days", "no 1:1 coaching"])
        self.assertEqual(o["deliverables"], ["12 video lessons", "4 live calls"])

    def test_exclusions_none_is_an_empty_list_answer(self):
        s = session({})
        li.answer(s, "a4b_exclusions", "None")
        e = li._get(s, "offers.main.exclusions")
        self.assertEqual((e["value"], e["state"]), ([], "provided"))

    def test_same_split_as_the_shared_engine(self):
        eng = li._client_intake()
        raw = "12 video lessons, 4 live calls\n- templates; bonus call"
        got = eng._normalize({}, {"id": "x", "answer_type": "list", "choices": [],
                                  "required": "always"}, raw)[0]
        self.assertEqual(li._split_list(raw), got)

    def test_exclusions_question_is_in_the_bank_after_deliverables(self):
        ids = [q["id"] for q in li.load_question_bank()]
        self.assertEqual(ids[ids.index("a4_deliverables") + 1], "a4b_exclusions")


class Recommendation(unittest.TestCase):
    def test_recommended_packages_are_not_owner_sourced(self):
        lv = [("Basic", 19700), ("Plus", 49700)]
        s = session({"journey_mode": "multiple_options",
                     "offers.main.packages": {"value": packages(lv),
                                              "state": "recommended_unapproved"}})
        offers = li.assemble_plan(s)["plan"]["offers"]
        self.assertEqual({o["source_kind"] for o in offers}, {"test_fixture"})
        s["test_only"] = False
        self.assertEqual({o["source_kind"] for o in li._package_offers(s, [])},
                         {"recommendation"})

    def test_recommended_main_is_not_owner_sourced(self):
        s = session({"offers.main.description": {"value": "Course", "state": "recommended_unapproved"},
                     "offers.main.price": {"value": price(100), "state": "provided"}})
        s["test_only"] = False
        o = li._offer_from_answers(s, "main", "offers.main.description", "MAIN")
        self.assertEqual(o["source_kind"], "recommendation")

    def test_owner_packages_stay_owner(self):
        s = session({"offers.main.packages": packages([("A", 1), ("B", 2)])})
        s["test_only"] = False
        self.assertEqual({o["source_kind"] for o in li._package_offers(s, [])}, {"owner"})


class JourneyWords(unittest.TestCase):
    def rec(self, text):
        return li._recommend_journey(session({"offers.main.description": text}))

    def test_substrings_do_not_count(self):
        self.assertEqual(self.rec("A compassionate coaching program"), "single_simple")
        self.assertEqual(self.rec("Passion for fitness"), "single_simple")

    def test_whole_words_still_count(self):
        self.assertEqual(self.rec("Three packages to pick from"), "multiple_options")
        self.assertEqual(self.rec("VIP level"), "multiple_options")


if __name__ == "__main__":
    unittest.main(verbosity=1)
