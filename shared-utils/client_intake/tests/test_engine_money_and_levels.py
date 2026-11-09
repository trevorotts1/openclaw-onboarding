#!/usr/bin/env python3
"""Proofs for PRD-08 (strict price parser), PRD-09 (exact journey matching), PRD-11 (cited client
messages) and PRD-34 (no free main offer in bf mode). No network, no paid call, no model.

Run: python3 -m pytest shared-utils/client_intake/tests/test_engine_money_and_levels.py -q
"""
import json
import sys
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PKG))
import engine as e  # noqa: E402

# the transcript store, in memory: id -> (role, text)
STORE = {
    "c1": ("client", "$497"), "c2": ("client", "yes"), "c3": ("client", "CAD 497"),
    "c4": ("client", "One offer"), "c5": ("client", "12 lessons; 4 calls"),
    "c6": ("client", "Premium | 12 lessons | $497\nBasic | 4 lessons | $97"),
    "c7": ("client", "Yes, it is included"), "c8": ("client", "free"),
    "a1": ("assistant", "$497"),
}


def lookup(ref):
    row = STORE.get(ref)
    return {"role": row[0], "text": row[1]} if row else None


class Base(unittest.TestCase):
    def setUp(self):
        e.TRANSCRIPT_LOOKUP = lookup
        self.addCleanup(setattr, e, "TRANSCRIPT_LOOKUP", None)


class StrictMoney(Base):
    def test_exact_prices_parse_exactly(self):
        for text, want in (("$497", ("USD", 49700)), ("497", ("USD", 49700)), ("€497.00", ("EUR", 49700)),
                           ("USD 497", ("USD", 49700)), ("$1,497.50", ("USD", 149750)), ("497 EUR", ("EUR", 49700))):
            self.assertEqual(e._money(text), {"amount_minor": want[1], "currency": want[0]}, text)

    def test_the_bad_strings_are_refused_with_a_question(self):
        for text in ("$1.5k", "CAD 497", "¥50000", "1.997", "1 497", "was $2,997 now $497", "1.497", "$5m", "1,49", "USD $497"):
            self.assertIsNone(e._money(text), text)
            m, why = e._parse_money(text)
            self.assertIsNone(m)
            self.assertTrue("?" in why or "number" in why or "decimal" in why, (text, why))
            d = e.new_doc()
            r = e.record(d, "price", text, source_message_ref="c1")
            self.assertFalse(r.get("ok"), text)
            self.assertIsNone(e.val(d, "price"), text)

    def test_which_currency_is_asked_for_an_unknown_marker(self):
        r = e.record(e.new_doc(), "price", "CAD 497", source_message_ref="c3")
        self.assertFalse(r["ok"])
        self.assertIn("currency", r["message"].lower())

    def test_a_price_is_echoed_and_recorded_only_after_a_yes(self):
        d = e.new_doc()
        r = e.record(d, "price", "$497", source_message_ref="c1")
        self.assertFalse(r["ok"])
        self.assertEqual(r["action"], "confirm_price")
        self.assertIn("I heard USD 497.00, correct?", r["message"])
        self.assertIsNone(e.val(d, "price"))
        r = e.record(d, "price", "yes", source_message_ref="c2")
        self.assertTrue(r["ok"], r)
        ent = e.get(d, "price")
        self.assertEqual((ent["value"], ent["status"]), ({"amount_minor": 49700, "currency": "USD"}, "provided"))
        self.assertEqual((ent["source_message_ref"], ent["confirmation_ref"]), ("c1", "c2"))

    def test_a_no_to_the_echo_records_nothing(self):
        d = e.new_doc()
        e.record(d, "price", "$497", source_message_ref="c1")
        r = e.record(d, "price", "no", source_message_ref="c2")
        self.assertFalse(r["ok"])
        self.assertIsNone(e.val(d, "price"))
        self.assertFalse(e.record(d, "price", "yes", source_message_ref="c2")["ok"])  # nothing left to confirm


class ExactJourney(Base):
    def shape(self, text):
        r = e.record(e.new_doc(), "funnel_shape", text, source_message_ref="c4")
        return r["entry"]["value"] if r.get("ok") else None

    def test_the_sentences_resolve_or_ask(self):
        for text, want in (("a single offer, no levels", "single_simple"), ("one offer, no levels", "single_simple"),
                           ("a few packages with different levels of support", "multiple_options"),
                           ("levels that build on each other", "folded_levels"),
                           ("One offer", "single_simple"), ("A few packages", "multiple_options"),
                           ("Levels that build on each other", "folded_levels")):
            out = e._normalize(e.new_doc(), e.question("funnel_shape"), text)
            self.assertEqual(out[0], want, text)

    def test_unclear_or_conflicting_text_is_asked_back(self):
        for text in ("levels", "not levels", "no levels", "one offer or a few packages", "maybe"):
            out = e._normalize(e.new_doc(), e.question("funnel_shape"), text)
            self.assertFalse(isinstance(out, tuple), text)
            self.assertIn("one offer, a few packages", out["message"])

    def test_no_levels_never_records_folded_levels(self):
        self.assertEqual(self.shape("One offer"), "single_simple")
        self.assertNotEqual(e._normalize(e.new_doc(), e.question("funnel_shape"), "a single offer, no levels")[0], "folded_levels")


class CitedMessages(Base):
    def test_a_commercial_answer_without_a_ref_is_refused(self):
        for qid, value in (("funnel_shape", "One offer"), ("deliverables", "12 lessons; 4 calls")):
            for ref in (None, "", "nope", "a1"):  # missing, empty, unknown id, an assistant message
                d = e.new_doc()
                r = e.record(d, qid, value, source_message_ref=ref)
                self.assertFalse(r["ok"], (qid, ref))
                self.assertIn("error", r)
                self.assertIsNone(e.val(d, qid))
        d = e.new_doc()
        r = e.record(d, "price", "$497")
        self.assertEqual((r["ok"], r["error"]), (False, "source_message_ref_required"))

    def test_a_cited_message_that_does_not_say_it_is_refused(self):
        r = e.record(e.new_doc(), "funnel_shape", "A few packages", source_message_ref="c4")
        self.assertEqual(r["error"], "source_message_mismatch")
        r = e.record(e.new_doc(), "price", "$997", source_message_ref="c1")
        self.assertEqual(r["error"], "source_message_mismatch")

    def test_a_self_assigned_source_is_refused(self):
        for src in ("ai-agent", ""):
            r = e.record(e.new_doc(), "funnel_shape", "One offer", source=src, source_message_ref="c4")
            self.assertEqual(r["error"], "source_not_client", src)

    def test_status_cannot_be_forced_up_to_provided(self):
        d = e.new_doc()
        r = e.record(d, "price", {"amount_minor": 49700, "currency": "USD",
                                  "rationale": "Similar programs charge 400 to 600."},
                     status="provided", source_message_ref="c1")
        self.assertFalse(r["ok"])

    def test_cited_answers_are_recorded_with_their_ref(self):
        d = e.new_doc()
        for qid, value, ref in (("funnel_shape", "One offer", "c4"), ("deliverables", "12 lessons; 4 calls", "c5")):
            self.assertTrue(e.record(d, qid, value, source_message_ref=ref)["ok"], qid)
            self.assertEqual(e.get(d, qid)["source_message_ref"], ref)
        json.dumps(d)  # the doc stays plain JSON

    def test_a_dict_price_never_skips_the_parser(self):
        d = e.new_doc()
        r = e.record(d, "price", {"amount_minor": 49700, "currency": "USD"}, source_message_ref="c1")
        self.assertFalse(r["ok"])
        self.assertIsNone(e.val(d, "price"))
        r = e.record(d, "price", {"amount_minor": 49700, "currency": "USD", "rationale": "Similar programs charge 400 to 600."})
        self.assertEqual(e.get(d, "price")["status"], "suggested")  # a reasoned proposal needs no ref, and is never provided
        r = e.record(d, "price", {"amount_minor": 49700, "rationale": "x"})
        self.assertIn("currency", r["message"].lower())

    def test_package_dicts_are_validated(self):
        good = {"display_name": "Premium", "price": {"amount_minor": 49700, "currency": "USD"}}
        other = {"display_name": "Basic", "price": {"amount_minor": 9700, "currency": "USD"}, "price_status": "provided"}
        STORE["c9"] = ("client", "Premium 497 and Basic 97 dollars")
        self.addCleanup(STORE.pop, "c9", None)
        approved = dict(good, price_status="approved")
        r = e.record(e.new_doc(), "packages", [approved, other], source_message_ref="c9")
        self.assertFalse(r["ok"])
        self.assertIn("price_status", r["message"])
        nocur = {"display_name": "Premium", "price": {"amount_minor": 49700}}
        self.assertIn("currency", e.record(e.new_doc(), "packages", [nocur, other], source_message_ref="c9")["message"].lower())
        for bad in (-5, 0, 1.5, True):
            row = {"display_name": "Premium", "price": {"amount_minor": bad, "currency": "USD"}}
            self.assertFalse(e.record(e.new_doc(), "packages", [row, other], source_message_ref="c9")["ok"], bad)
        ok = e.record(e.new_doc(), "packages", [good, other], source_message_ref="c9")
        self.assertTrue(ok["ok"], ok)

    def test_text_packages_need_one_clear_price_per_line(self):
        d = e.new_doc()
        self.assertTrue(e.record(d, "packages", "Premium | 12 lessons | $497\nBasic | 4 lessons | $97", source_message_ref="c6")["ok"])
        two = e._normalize(e.new_doc(), e.question("packages"), "Premium | was $997 now $497\nBasic | $97")
        self.assertIsInstance(two, dict)  # one row with two numbers is refused, never half-read


class NoFreeMainInBf(Base):
    def test_free_in_bf_mode_asks_the_lead_magnet_question(self):
        for text in ("free", "It is free", "0", "$0", "0.00"):
            d = e.new_doc("bf")
            r = e.record(d, "price", text, source_message_ref="c8")
            self.assertFalse(r["ok"], text)
            self.assertNotIn("action", r)
            self.assertIn("lead magnet", r["message"], text)
            self.assertIsNone(e.val(d, "price"))

    def test_free_outside_bf_is_echoed_not_refused(self):
        d = e.new_doc("launch")
        r = e.record(d, "price", "free", source_message_ref="c8")
        self.assertEqual(r["action"], "confirm_price")

    def test_a_paid_price_in_bf_mode_still_works(self):
        d = e.new_doc("bf")
        self.assertEqual(e.record(d, "price", "$497", source_message_ref="c1")["action"], "confirm_price")
        self.assertTrue(e.record(d, "price", "yes", source_message_ref="c2")["ok"])


class Schema(unittest.TestCase):
    def test_the_answers_schema_names_the_citation_fields(self):
        props = json.loads((PKG / "answers.schema.json").read_text())["properties"]["answers"]["additionalProperties"]["properties"]
        self.assertIn("source_message_ref", props)
        self.assertIn("confirmation_ref", props)


if __name__ == "__main__":
    unittest.main()
