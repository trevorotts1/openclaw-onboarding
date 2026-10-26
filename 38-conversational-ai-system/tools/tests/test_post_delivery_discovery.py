#!/usr/bin/env python3
"""Tests for T-27 post-delivery discovery, answers and recommendation.

Contract basis: Purple-Billboard SPEC.md "Fulfillment, access and useful help"
(R-17, C-27) and ACCEPTANCE-MATRIX R-20 (truthful attribution), plus
DATA-CONTRACTS sections 5 and 7.

Run from the skill root:
    python3 -m unittest discover -s tools/tests -p 'test_post_delivery_discovery.py' -v
or directly:
    python3 tools/tests/test_post_delivery_discovery.py

What is proven here:

  REAL          a resource/community/offer/calendar item is recommendable only
                when its destination is usable; pseudo-schemes, reserved
                special-use hosts, fragments, dotless hosts, placeholders,
                missing local paths and unavailable items are all refused, each
                against a known-good control that still passes.

  ADAPTIVE      the pending question set is a function of the catalogue and of
                what is already known - a learned field removes its question, a
                refused field is suppressed, and the set is never a fixed
                three. One known need is enough to recommend, so there is no
                gate to finish.

  ANSWERED      an answer is returned with the source that supplied it, and an
                unmatched topic returns `unknown` with no invented text.

  UNGATED       phone-only, email-only and marketing-declined callers get
                byte-identical recommendations and answers; the module exposes
                no capture endpoint; help is recorded independently of capture.

  TRUTHFUL      `delivered` requires a receipt while provider acceptance stays
                `accepted`; an outcome needs evidence unless it is `unknown`;
                keyword and multi-touch attribution survive with
                `exact_post_causality` false.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from post_delivery_discovery import (  # noqa: E402
    DELIVERY_ACCEPTED,
    DELIVERY_DELIVERED,
    KIND_CALENDAR,
    KIND_COMMUNITY,
    KIND_OFFER,
    KIND_RESOURCE,
    NEED_FIELDS,
    OUTCOME_ATTENDED,
    OUTCOME_BOOKED,
    OUTCOME_UNKNOWN,
    Catalog,
    Discovery,
    DiscoveryError,
    KnowledgeBase,
)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.local_path = os.path.join(self.tmp.name, "worksheet.pdf")
        with open(self.local_path, "w") as fh:
            fh.write("worksheet")

    def catalog(self):
        c = Catalog()
        c.add("res-1", KIND_RESOURCE, "Starter guide",
              "https://example-client.com/guide.pdf", ["goal"])
        c.add("com-1", KIND_COMMUNITY, "Owner circle",
              "https://community.example-client.com/", ["interests"])
        c.add("off-1", KIND_OFFER, "Deep-dive call",
              "https://example-client.com/call", ["budget", "goal"])
        c.add("cal-1", KIND_CALENDAR, "Book a slot",
              "https://cal.example-client.com/book", ["timezone"])
        c.add("res-2", KIND_RESOURCE, "Local worksheet", self.local_path,
              ["preferred_format"])
        return c

    def knowledge(self):
        kb = KnowledgeBase()
        kb.add("what is included", "The guide plus the worksheet.",
               "https://example-client.com/faq")
        kb.add("how long is the call", "Thirty minutes.",
               "Client onboarding notes 2026-10-20")
        return kb


class RealDestinationTests(Base):
    """REAL: nothing is recommended that does not exist."""

    def test_real_destinations_are_accepted(self):
        c = self.catalog()
        self.assertEqual(c.get("res-1").destination,
                         "https://example-client.com/guide.pdf")
        self.assertEqual(c.get("res-2").destination, self.local_path)

    def test_placeholders_and_fake_hosts_are_refused(self):
        bad = [
            ("", "blank"),
            ("   ", "whitespace"),
            ("#", "fragment"),
            ("todo", "todo token"),
            ("tbd", "tbd token"),
            ("n/a", "n/a token"),
            ("totally://made.up", "pseudo scheme"),
            ("https://invented.invalid/nope", "reserved .invalid host"),
            ("https://example.com/x", "reserved example.com"),
            ("http://localhost/x", "localhost"),
            ("https://nodot/x", "dotless host"),
            ("https:///x", "no host"),
            ("/tmp/definitely-not-a-real-file-461.pdf", "missing local path"),
            ("guide.pdf", "bare relative name"),
        ]
        for pointer, label in bad:
            with self.subTest(pointer=pointer, label=label):
                with self.assertRaises(DiscoveryError):
                    Catalog().add("x", KIND_RESOURCE, "Bad", pointer, ["goal"])

    def test_kind_outside_the_four_contract_kinds_is_refused(self):
        with self.assertRaises(DiscoveryError):
            Catalog().add("x", "bonus", "Bad",
                          "https://example-client.com/x", ["goal"])

    def test_unavailable_item_is_never_recommended(self):
        c = self.catalog()
        c.add("off-2", KIND_OFFER, "Retired bonus",
              "https://example-client.com/old", ["budget"], available=False)
        d = Discovery(c, self.knowledge())
        d.learn("budget", "small")
        ids = [r["item_id"] for r in d.recommend(10)["recommendations"]]
        self.assertIn("off-1", ids)
        self.assertNotIn("off-2", ids)
        self.assertTrue(c.get("off-2").available is False)


class AdaptiveDiscoveryTests(Base):
    """ADAPTIVE: no fixed three-question gate."""

    def test_known_field_removes_its_own_question(self):
        d = Discovery(self.catalog(), self.knowledge())
        first = d.next_question()
        self.assertIsNotNone(first)
        before = {q["field"] for q in d.questions()}
        self.assertIn(first["field"], before)
        d.learn(first["field"], "answer")
        after = {q["field"] for q in d.questions()}
        self.assertNotIn(first["field"], after)
        self.assertEqual(before - after, {first["field"]})

    def test_refused_field_is_suppressed_and_does_not_block(self):
        d = Discovery(self.catalog(), self.knowledge())
        d.learn("goal", "get started")
        self.assertIn("budget", {q["field"] for q in d.questions()})
        d.refuse("budget")
        self.assertNotIn("budget", {q["field"] for q in d.questions()})
        self.assertEqual(d.recommend(3)["status"], "ok")

    def test_question_set_is_not_a_fixed_three_and_shrinks_to_zero(self):
        d = Discovery(self.catalog(), self.knowledge())
        sizes = []
        sizes.append(len(d.questions()))
        self.assertGreaterEqual(sizes[0], 4,
                                "a five-tag catalogue must open more than three "
                                "questions, otherwise the 'three' is hard-coded")
        while True:
            question = d.next_question()
            if question is None:
                break
            d.learn(question["field"], "known")
            sizes.append(len(d.questions()))
        self.assertEqual(sizes[-1], 0)
        self.assertEqual(sizes, sorted(sizes, reverse=True))
        self.assertNotEqual(set(sizes), {3})

    def test_only_material_fields_are_asked(self):
        # A catalogue with a single resource tag means only that field is worth
        # asking about: no empty questionnaire is produced.
        c = Catalog()
        c.add("res-1", KIND_RESOURCE, "Only guide",
              "https://example-client.com/guide.pdf", ["goal"])
        d = Discovery(c, self.knowledge())
        self.assertEqual([q["field"] for q in d.questions()], ["goal"])
        self.assertEqual(set(NEED_FIELDS) - {"goal"},
                         set(NEED_FIELDS) - set(q["field"] for q in d.questions()))

    def test_one_known_need_is_enough_to_recommend(self):
        d = Discovery(self.catalog(), self.knowledge())
        self.assertEqual(d.recommend(3)["status"], "no_match",
                         "no known need means no invented relevance")
        d.learn("goal", "get started")
        result = d.recommend(3)
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["recommendations"])
        for rec in result["recommendations"]:
            self.assertEqual(rec["basis"]["known_needs"], ["goal"])
            self.assertIn("goal", rec["basis"]["matched_tags"])

    def test_recommendation_order_is_deterministic(self):
        d1 = Discovery(self.catalog(), self.knowledge())
        d2 = Discovery(self.catalog(), self.knowledge())
        d1.learn("goal", "a")
        d2.learn("goal", "a")
        self.assertEqual(d1.recommend(5), d2.recommend(5))

    def test_more_matched_tags_rank_first(self):
        c = Catalog()
        c.add("a-one", KIND_OFFER, "One tag",
              "https://example-client.com/a", ["goal"])
        c.add("b-two", KIND_OFFER, "Two tags",
              "https://example-client.com/b", ["goal", "budget"])
        d = Discovery(c, self.knowledge())
        d.learn("goal", "x")
        d.learn("budget", "y")
        ids = [r["item_id"] for r in d.recommend(2)["recommendations"]]
        self.assertEqual(ids, ["b-two", "a-one"])

    def test_unknown_fields_are_refused(self):
        d = Discovery(self.catalog(), self.knowledge())
        with self.assertRaises(DiscoveryError):
            d.learn("favourite_colour", "blue")
        with self.assertRaises(DiscoveryError):
            d.refuse("favourite_colour")
        with self.assertRaises(DiscoveryError):
            d.learn("goal", "   ")
        with self.assertRaises(DiscoveryError):
            d.recommend(0)


class AnswerTests(Base):
    """ANSWERED: sourced answers, unknown otherwise."""

    def test_answer_carries_its_source(self):
        d = Discovery(self.catalog(), self.knowledge())
        answered = d.answer("What Is Included")
        self.assertEqual(answered["status"], "answered")
        self.assertEqual(answered["source"], "https://example-client.com/faq")
        self.assertEqual(answered["answer"], "The guide plus the worksheet.")

    def test_named_source_is_accepted(self):
        d = Discovery(self.catalog(), self.knowledge())
        answered = d.answer("how long is the call")
        self.assertEqual(answered["source"], "Client onboarding notes 2026-10-20")

    def test_unmatched_topic_is_unknown_and_invents_nothing(self):
        d = Discovery(self.catalog(), self.knowledge())
        unknown = d.answer("what colour is the moon")
        self.assertEqual(unknown["status"], "unknown")
        self.assertIsNone(unknown["answer"])
        self.assertIsNone(unknown["source"])

    def test_blank_knowledge_answer_is_refused(self):
        with self.assertRaises(DiscoveryError):
            KnowledgeBase().add("topic", "", "https://example-client.com/x")


class UngatedTests(Base):
    """UNGATED: capture never changes help, and there is no capture endpoint."""

    def three_callers(self):
        shapes = (
            {"email": None, "sms": "phone-only"},
            {"email": "person@example-client.com"},
            {"email": "person@example-client.com", "marketing": "declined"},
        )
        out = []
        for shape in shapes:
            d = Discovery(self.catalog(), self.knowledge(), capture_state=shape)
            d.learn("goal", "get started")
            out.append(d)
        return out

    def test_recommendations_are_identical_across_capture_shapes(self):
        phone_only, email_only, declined = self.three_callers()
        self.assertEqual(phone_only.recommend(3), email_only.recommend(3))
        self.assertEqual(phone_only.recommend(3), declined.recommend(3))
        self.assertTrue(phone_only.recommend(3)["recommendations"])

    def test_answers_are_identical_across_capture_shapes(self):
        phone_only, email_only, declined = self.three_callers()
        self.assertEqual(phone_only.answer("what is included"),
                         email_only.answer("what is included"))
        self.assertEqual(phone_only.answer("what is included"),
                         declined.answer("what is included"))

    def test_module_exposes_no_capture_endpoint(self):
        import post_delivery_discovery as mod
        self.assertFalse(hasattr(mod, "capture"))
        self.assertFalse(hasattr(Discovery, "capture"))
        public = [n for n in dir(mod) if not n.startswith("_")]
        self.assertEqual([n for n in public if "capture" in n.lower()], [],
                         "a generic capture endpoint is exactly what C-27 bans")

    def test_capture_state_never_completes_discovery(self):
        d = Discovery(self.catalog(), self.knowledge(),
                      capture_state={"email": "person@example-client.com",
                                     "state": "complete"})
        # Capture claiming complete does not close the question set.
        self.assertTrue(d.questions())
        self.assertFalse(d.help_given())

    def test_help_is_recorded_independently_of_capture(self):
        d = Discovery(self.catalog(), self.knowledge(),
                      capture_state={"email": None})
        self.assertFalse(d.help_given())
        d.record_delivery("res-1", DELIVERY_ACCEPTED)
        self.assertTrue(d.help_given())


class TruthfulTests(Base):
    """TRUTHFUL: receipts, evidence and preserved attribution."""

    def test_acceptance_is_not_delivery(self):
        d = Discovery(self.catalog(), self.knowledge())
        record = d.record_delivery("res-1", DELIVERY_ACCEPTED)
        self.assertEqual(record["status"], "accepted")
        self.assertIsNone(record["receipt"])

    def test_delivered_requires_a_receipt(self):
        d = Discovery(self.catalog(), self.knowledge())
        with self.assertRaises(DiscoveryError):
            d.record_delivery("res-1", DELIVERY_DELIVERED)
        with self.assertRaises(DiscoveryError):
            d.record_delivery("res-1", DELIVERY_DELIVERED, receipt="   ")
        self.assertEqual(
            d.record_delivery("res-1", DELIVERY_DELIVERED,
                              receipt="msg-42")["status"], "delivered")

    def test_uncatalogued_delivery_is_refused(self):
        d = Discovery(self.catalog(), self.knowledge())
        with self.assertRaises(DiscoveryError):
            d.record_delivery("ghost-1", DELIVERY_ACCEPTED)

    def test_outcome_needs_evidence_unless_unknown(self):
        d = Discovery(self.catalog(), self.knowledge())
        with self.assertRaises(DiscoveryError):
            d.record_outcome("res-1", OUTCOME_BOOKED)
        with self.assertRaises(DiscoveryError):
            d.record_outcome("res-1", OUTCOME_ATTENDED, evidence="   ")
        self.assertEqual(d.record_outcome("res-1", OUTCOME_UNKNOWN)["outcome"],
                         OUTCOME_UNKNOWN)
        self.assertEqual(
            d.record_outcome("res-1", OUTCOME_ATTENDED,
                             evidence="cal receipt 2026-10-25")["outcome"],
            OUTCOME_ATTENDED)

    def test_unknown_outcome_string_is_refused(self):
        d = Discovery(self.catalog(), self.knowledge())
        with self.assertRaises(DiscoveryError):
            d.record_outcome("res-1", "probably_bought", evidence="vibes")

    def test_attribution_preserves_keyword_and_refuses_causality(self):
        d = Discovery(self.catalog(), self.knowledge())
        d.note_touch("comment")
        d.note_touch("dm", keyword="purple-billboard")
        attr = d.attribution()
        self.assertEqual(attr["keyword"], "purple-billboard")
        self.assertEqual(attr["touches"], ["comment", "dm"])
        self.assertFalse(attr["exact_post_causality"])
        self.assertTrue(attr["unknown_preserved"])

    def test_snapshot_reports_state_without_claiming_more(self):
        d = Discovery(self.catalog(), self.knowledge(),
                      capture_state={"email": None})
        d.learn("goal", "get started")
        d.record_delivery("res-1", DELIVERY_ACCEPTED)
        snap = d.snapshot()
        self.assertEqual(snap["known"], {"goal": "get started"})
        self.assertEqual(snap["capture_state"], {"email": None})
        self.assertEqual(len(snap["deliveries"]), 1)


class SelfCheckTest(unittest.TestCase):
    def test_module_self_check_passes(self):
        import subprocess
        result = subprocess.run(
            [sys.executable, "-I", str(TOOLS_DIR / "post_delivery_discovery.py")],
            capture_output=True, text=True, cwd=str(TOOLS_DIR))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
