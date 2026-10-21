#!/usr/bin/env python3
"""Synthetic-local regression proofs for the launch-text pre-send gate.

No network, no provider, no live send: every case is a fixture or an
in-memory contact state.

    python3 test_sms_eligibility.py          # direct
    python3 -m unittest test_sms_eligibility # via unittest
"""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from sms_eligibility import (  # noqa: E402
    EXPECTED_CONDITIONS,
    MARKETING_CAP,
    category,
    count_segments,
    evaluate_send,
    verify_saved_conditions,
)


def fixture(name: str) -> dict:
    return json.loads((HERE / "fixtures" / name).read_text(encoding="utf-8"))


def evaluate_fixture(name: str) -> tuple[dict, dict]:
    case = fixture(name)
    return case, evaluate_send(copy.deepcopy(case["send"]))


class ClassificationTests(unittest.TestCase):
    def test_marketing_and_operational_are_separate(self):
        for kind in ("doors_open", "last_call", "abandoned_checkout"):
            self.assertEqual(category(kind), "marketing")
        for kind in ("opt_in_confirmation", "keyword_opt_in",
                     "event_reminder", "access_link"):
            self.assertEqual(category(kind), "operational")

    def test_unknown_kind_is_refused_not_guessed(self):
        with self.assertRaises(ValueError):
            category("newsletter")


class FixtureRegressionTests(unittest.TestCase):
    def assertExpectation(self, case, result):
        expect = case["expect"]
        self.assertEqual(result["action"], expect["action"], result["reason"])
        self.assertEqual(result["category"], expect["category"])
        if "reason" in expect:
            self.assertEqual(result["reason"], expect["reason"])
        if "send_at" in expect:
            self.assertEqual(result["send_at"], expect["send_at"])
        if "encoding" in expect:
            self.assertEqual(result["encoding"], expect["encoding"])

    def test_held_to_next_window(self):
        case, result = evaluate_fixture("send_marketing_held.json")
        self.assertExpectation(case, result)
        self.assertEqual(result["send_at"], "2026-10-23T08:00:00")
        self.assertGreaterEqual(result["segments"], 1)
        self.assertAlmostEqual(
            result["cost_usd"], round(result["segments"] * 0.01, 6))

    def test_deadline_conflict_moves_earlier_never_later(self):
        case, result = evaluate_fixture("send_deadline_moved_earlier.json")
        self.assertExpectation(case, result)
        self.assertLess(result["send_at"], case["send"]["deadline"])

    def test_suppression_wins_after_build(self):
        case, result = evaluate_fixture("send_suppressed.json")
        self.assertExpectation(case, result)
        check = next(c for c in result["checks"] if c["rule"] == "not_suppressed")
        self.assertFalse(check["ok"])

    def test_aggregate_contact_cap_blocks_the_sixth_marketing_send(self):
        case, result = evaluate_fixture("send_cap_reached.json")
        self.assertExpectation(case, result)
        check = next(c for c in result["checks"]
                     if c["rule"] == "aggregate_contact_cap")
        self.assertFalse(check["ok"])
        self.assertIn(str(MARKETING_CAP), check["detail"])

    def test_operational_after_deadline_is_not_blocked(self):
        case, result = evaluate_fixture("send_operational_after_deadline.json")
        self.assertExpectation(case, result)
        check = next(c for c in result["checks"]
                     if c["rule"] == "aggregate_contact_cap")
        self.assertTrue(check["ok"])
        self.assertIn("operational", check["detail"])

    def test_ucs2_over_segment_ceiling_is_refused(self):
        case, result = evaluate_fixture("send_content_ucs2_over_cap.json")
        self.assertExpectation(case, result)
        self.assertGreater(result["segments"], 1)

    def test_http_and_shortener_links_are_refused(self):
        case, result = evaluate_fixture("send_link_refused.json")
        self.assertExpectation(case, result)
        self.assertIn("content", result["reason"])

    def test_event_reminder_outside_window_skips_rather_than_lies(self):
        case, result = evaluate_fixture("send_event_reminder_conflict.json")
        self.assertExpectation(case, result)


class SendTimeTests(unittest.TestCase):
    def base(self):
        return fixture("send_marketing_held.json")["send"]

    def test_08_00_is_allowed_and_21_00_is_not(self):
        send = self.base()
        send["anchor"] = "2026-10-22T06:00:00"
        send["send_at"] = "2026-10-22T08:00:00"
        send["now"] = "2026-10-22T08:00:00"
        self.assertEqual(evaluate_send(send)["action"], "send")
        send["send_at"] = "2026-10-22T21:00:00"
        send["now"] = "2026-10-22T12:00:00"
        held = evaluate_send(send)
        self.assertEqual(held["action"], "hold")
        self.assertEqual(held["send_at"], "2026-10-23T08:00:00")

    def test_past_due_never_sends_late(self):
        send = self.base()
        send["send_at"] = "2026-10-22T10:00:00"
        send["now"] = "2026-10-22T10:05:00"
        result = evaluate_send(send)
        self.assertEqual(result["action"], "skip")
        self.assertEqual(result["reason"], "past_due")

    def test_marketing_deadline_passed_skips(self):
        send = self.base()
        send["send_at"] = "2026-10-22T09:00:00"
        send["now"] = "2026-10-22T09:00:00"
        send["deadline"] = "2026-10-22T08:30:00"
        result = evaluate_send(send)
        self.assertEqual(result["action"], "skip")
        self.assertEqual(result["reason"], "failed: launch_deadline")


    def test_hold_candidate_before_anchor_skips(self):
        send = self.base()
        send["send_at"] = "2026-10-22T07:00:00"
        send["now"] = "2026-10-22T06:00:00"
        send["anchor"] = "2026-10-22T09:00:00"
        result = evaluate_send(send)
        self.assertEqual(result["action"], "skip")
        self.assertEqual(result["reason"], "before_anchor")

    def test_unknown_timezone_blocks_never_crashes(self):
        send = self.base()
        send["send_at"] = "2026-10-22T10:00:00+00:00"
        send["now"] = "2026-10-22T10:00:00+00:00"
        send["timezone"] = "Bogus/Zone"
        result = evaluate_send(send)
        self.assertEqual(result["action"], "skip")
        self.assertIn("quiet_hours", result["reason"])


class ConsentAndA2PTests(unittest.TestCase):
    def test_consent_is_read_immediately_before_send(self):
        send = fixture("send_marketing_held.json")["send"]
        send["send_at"] = "2026-10-22T10:00:00"
        send["now"] = "2026-10-22T10:00:00"
        send["contact"]["consent"] = "pending"
        result = evaluate_send(send)
        self.assertEqual(result["action"], "skip")
        self.assertIn("consent", result["reason"])

    def test_opt_in_confirmation_may_run_on_pending_consent(self):
        send = {
            "kind": "opt_in_confirmation",
            "template": "{{first_name}}, you're in. {{business_name}} will text you "
                        "about {{offer_name}}. Msg frequency varies. Reply HELP for "
                        "help or STOP to opt out.",
            "variables": {"first_name": "Ada", "business_name": "Example Co",
                          "offer_name": "Signature Launch"},
            "send_at": "2026-10-22T10:00:00",
            "now": "2026-10-22T10:00:00",
            "a2p_ready": True,
            "contact": {"consent": "pending", "sms_subscribed": False,
                        "tags": ["text-optin-pending"], "suppression": [],
                        "marketing_sends": 0, "operational_sends": 0},
        }
        result = evaluate_send(send)
        self.assertEqual(result["action"], "send", result["reason"])

    def test_a2p_not_ready_blocks_every_set(self):
        send = fixture("send_marketing_held.json")["send"]
        send["a2p_ready"] = False
        result = evaluate_send(send)
        self.assertEqual(result["action"], "skip")
        self.assertIn("a2p_ready", result["reason"])


class ContentTests(unittest.TestCase):
    def test_gsm7_segment_math(self):
        self.assertEqual(count_segments("a" * 160), ("gsm7", 1))
        self.assertEqual(count_segments("a" * 161), ("gsm7", 2))
        self.assertEqual(count_segments("{" + "a" * 159), ("gsm7", 2))
        self.assertEqual(count_segments("€" * 80), ("gsm7", 1))
        self.assertEqual(count_segments("€" * 81), ("gsm7", 2))

    def test_ucs2_segment_math(self):
        self.assertEqual(count_segments("a" * 70), ("gsm7", 1))
        self.assertEqual(count_segments("Ж" * 70), ("ucs2", 1))
        self.assertEqual(count_segments("Ж" * 71), ("ucs2", 2))

    def test_unknown_placeholder_is_refused(self):
        send = fixture("send_marketing_held.json")["send"]
        send["template"] = "{{first_name}}, {{mystery_token}} Reply STOP"
        result = evaluate_send(send)
        self.assertEqual(result["action"], "skip")
        check = next(c for c in result["checks"] if c["rule"] == "content")
        self.assertIn("unknown placeholder", check["detail"])

    def test_copy_is_validated_after_merge(self):
        send = fixture("send_marketing_held.json")["send"]
        send["variables"]["first_name"] = "Zoë"  # UCS-2 but still 1 segment
        result = evaluate_send(send)
        self.assertEqual(result["action"], "hold")
        self.assertEqual(result["encoding"], "ucs2")


class NativeConditionTests(unittest.TestCase):
    def test_saved_native_conditions_pass(self):
        snapshot = fixture("native_export_ok.json")
        for cat in ("marketing", "operational"):
            result = verify_saved_conditions(snapshot, cat)
            self.assertTrue(result["ok"], result["missing"])

    def test_prose_alone_never_satisfies_a_rule(self):
        snapshot = fixture("native_export_prose_only.json")
        result = verify_saved_conditions(snapshot, "marketing")
        self.assertFalse(result["ok"])
        self.assertEqual(sorted(result["missing"]),
                         sorted(rule for rule, _ in EXPECTED_CONDITIONS["marketing"]))
        self.assertTrue(result["prose_only"])
        self.assertIn("suppression", result["prose_only"])

    def test_one_missing_native_condition_fails_the_export(self):
        snapshot = fixture("native_export_ok.json")
        snapshot["steps"] = [
            step for step in snapshot["steps"]
            if step.get("name") != "Aggregate contact cap?"
        ]
        result = verify_saved_conditions(snapshot, "marketing")
        self.assertFalse(result["ok"])
        self.assertEqual(result["missing"], ["aggregate_contact_cap"])

    def test_disabled_condition_does_not_count(self):
        snapshot = fixture("native_export_ok.json")
        snapshot["steps"][0]["disabled"] = True
        result = verify_saved_conditions(snapshot, "marketing")
        self.assertIn("suppression", result["missing"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
