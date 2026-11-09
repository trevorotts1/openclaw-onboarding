#!/usr/bin/env python3
"""Acceptance proof for the single-responder policy (WF28 / B11, B12).

Every acceptance id has its own class:
  B11       no double send; human takeover, opt-out and quiet hours work
  B12       explicit channel mapping; no unsupported destination invented
  IG-AI-04  native AI and the local brain never answer the same input
  IG-AI-05  handoff / opt-out / quiet hours / returning-contact rules hold
  IG-AI-08  customer content cannot change administrative policy

Run: python3 tools/tests/test_responder_policy.py
     bash scripts/qc-responder-policy.sh
"""
from __future__ import annotations

import copy
import datetime
import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

import responder_policy as policy  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "responder-policy"
DAY = datetime.datetime(2026, 1, 1, 17, 0, tzinfo=datetime.timezone.utc).timestamp()
NIGHT = datetime.datetime(2026, 1, 1, 3, 0, tzinfo=datetime.timezone.utc).timestamp()


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def event(**overrides):
    doc = {"kind": "inbound", "contact_id": "cc_synthetic",
           "thread_id": "conv_synthetic", "message_id": "msg_1"}
    doc.update(overrides)
    return doc


class RecordValidationTests(unittest.TestCase):
    def test_every_fixture_validates(self):
        for name in ("local-only.json", "native-off.json", "native-suggestive.json",
                     "native-auto-pilot.json", "human-takeover.json"):
            with self.subTest(fixture=name):
                self.assertEqual(policy.validate_record(load(name)), [])

    def test_unsupported_destination_is_refused_by_name(self):
        doc = load("local-only.json")
        doc["channels"]["linkedin"] = dict(doc["channels"]["sms"],
                                           native_channel="SMS")
        errors = policy.validate_record(doc)
        self.assertTrue(any(e.startswith(policy.REFUSE_UNSUPPORTED_CHANNEL)
                            for e in errors), errors)

    def test_channel_map_mismatch_is_refused(self):
        doc = load("local-only.json")
        doc["channels"]["sms"]["native_channel"] = "FB"
        errors = policy.validate_record(doc)
        self.assertTrue(any(e.startswith(policy.REFUSE_CHANNEL_MAP_MISMATCH)
                            for e in errors), errors)

    def test_two_internal_names_for_one_native_channel_are_refused(self):
        doc = load("local-only.json")
        doc["channels"]["text"] = copy.deepcopy(doc["channels"]["sms"])
        errors = policy.validate_record(doc)
        self.assertTrue(any(e.startswith(policy.REFUSE_TWO_RESPONDERS)
                            for e in errors), errors)

    def test_local_primary_with_sending_native_ai_is_refused(self):
        doc = load("local-only.json")
        doc["channels"]["sms"]["native_mode"] = "auto-pilot"
        errors = policy.validate_record(doc)
        self.assertTrue(any(e.startswith(policy.REFUSE_RESPONDER_CONFLICT)
                            for e in errors), errors)

    def test_native_primary_with_mode_off_is_refused(self):
        doc = load("native-suggestive.json")
        doc["channels"]["fb"]["native_mode"] = "off"
        errors = policy.validate_record(doc)
        self.assertTrue(any(e.startswith(policy.REFUSE_NO_RESPONDER)
                            for e in errors), errors)

    def test_disabling_a_hard_limit_is_refused(self):
        for limit in ("opt_out", "quiet_hours", "client_test_mode"):
            with self.subTest(limit=limit):
                doc = load("local-only.json")
                doc["channels"]["sms"]["limits"][limit] = False
                errors = policy.validate_record(doc)
                self.assertTrue(any(e.startswith(policy.REFUSE_POLICY_WEAKENED)
                                    for e in errors), errors)

    def test_workflow_sends_without_dedupe_are_refused(self):
        doc = load("native-suggestive.json")
        doc["channels"]["fb"]["workflow_sends"]["deduplicates_with_primary"] = False
        errors = policy.validate_record(doc)
        self.assertTrue(any(e.startswith(policy.REFUSE_WORKFLOW_SEND_CONFLICT)
                            for e in errors), errors)

    def test_unknown_properties_are_refused_at_every_level(self):
        doc = load("local-only.json")
        doc["admin_override"] = True
        doc["channels"]["sms"]["grant_admin"] = True
        errors = policy.validate_record(doc)
        self.assertTrue(any("admin_override" in e for e in errors), errors)
        self.assertTrue(any("grant_admin" in e for e in errors), errors)

    def test_primary_switch_without_approval_is_refused(self):
        doc = load("native-auto-pilot.json")
        doc["production_primary"]["approved_switch_ref"] = None
        errors = policy.validate_record(doc)
        self.assertTrue(any(e.startswith(policy.REFUSE_PRIMARY_SWITCH_UNAPPROVED)
                            for e in errors), errors)

    def test_primary_switch_without_snapshot_is_refused(self):
        doc = load("native-auto-pilot.json")
        doc["production_primary"]["snapshot_ref"] = ""
        errors = policy.validate_record(doc)
        self.assertTrue(any("snapshot_ref" in e for e in errors), errors)


class ChannelMapTests(unittest.TestCase):
    def test_every_native_enumeration_is_reachable(self):
        mapped = set(policy.CHANNEL_MAP.values())
        self.assertEqual(mapped, set(policy.NATIVE_CHANNELS))

    def test_webchat_and_live_chat_are_distinct(self):
        self.assertEqual(policy.native_channel_for("webchat"), "WebChat")
        self.assertEqual(policy.native_channel_for("live_chat"), "Live_Chat")
        self.assertNotEqual(policy.native_channel_for("webchat"),
                            policy.native_channel_for("live_chat"))

    def test_unsupported_and_ambiguous_names_are_refused(self):
        for name in ("linkedin", "facebook_comments", "all_in_one", "gmb"):
            with self.subTest(channel=name):
                with self.assertRaises(policy.PolicyError) as caught:
                    policy.native_channel_for(name)
                self.assertIn(policy.REFUSE_UNSUPPORTED_CHANNEL, str(caught.exception))
        with self.assertRaises(policy.PolicyError) as caught:
            policy.native_channel_for("chat")
        self.assertIn(policy.REFUSE_UNKNOWN_CHANNEL, str(caught.exception))


class SingleResponderTests(unittest.TestCase):
    """B11 and IG-AI-04: one responder, no duplicate sends."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lease = policy.ResponderLease(str(Path(self.tmp.name) / "lease.sqlite"))
        self.record = load("local-only.json")

    def tearDown(self):
        self.lease.close()
        self.tmp.cleanup()

    def decide(self, record=None, channel="sms", ev=None, now=DAY, **kwargs):
        return policy.resolve(record or self.record, channel, ev or event(),
                              now=now, lease=self.lease, tenant_id="t1",
                              thread_ref="conversation-1", **kwargs)

    def test_local_brain_owns_an_off_channel(self):
        verdict = self.decide()
        self.assertEqual(verdict["code"], policy.ALLOW_LOCAL)
        self.assertEqual(verdict["responder"]["kind"], "openclaw_inbound")
        self.assertEqual(verdict["responder"]["native_mode"], "off")

    def test_two_messages_close_together_send_once(self):
        first = self.decide(ev=event(message_id="msg_1"))
        second = self.decide(ev=event(message_id="msg_2"))
        self.assertEqual(first["code"], policy.ALLOW_LOCAL)
        self.assertEqual(second["code"], policy.SUPPRESS_DUPLICATE_EVENT)
        self.assertIsNone(second["responder"])

    def test_redelivered_provider_event_sends_once(self):
        first = self.decide(ev=event(message_id="msg_1"))
        again = self.decide(ev=event(message_id="msg_1"))
        self.assertEqual(first["code"], policy.ALLOW_LOCAL)
        self.assertEqual(again["code"], policy.SUPPRESS_DUPLICATE_EVENT)

    def test_native_suggestive_never_sends_alone(self):
        verdict = self.decide(record=load("native-suggestive.json"), channel="fb")
        self.assertEqual(verdict["code"], policy.ALLOW_NATIVE_SUGGESTIVE)
        self.assertEqual(verdict["responder"]["native_channel"], "FB")

    def test_native_auto_pilot_is_the_only_sender(self):
        verdict = self.decide(record=load("native-auto-pilot.json"),
                              channel="whatsapp")
        self.assertEqual(verdict["code"], policy.ALLOW_NATIVE_AUTOPILOT)
        self.assertEqual(verdict["responder"]["kind"], "native_ghl")

    def test_native_off_channel_stays_local(self):
        verdict = self.decide(record=load("native-off.json"))
        self.assertEqual(verdict["code"], policy.ALLOW_LOCAL)

    def test_second_channel_on_the_same_record_is_independently_mapped(self):
        verdict = self.decide(record=load("native-auto-pilot.json"),
                              channel="webchat")
        self.assertEqual(verdict["code"], policy.ALLOW_LOCAL)
        self.assertEqual(verdict["responder"]["native_channel"], "WebChat")


class HandoffAndLimitsTests(unittest.TestCase):
    """B11 / IG-AI-05: takeover, opt-out, quiet hours, returning contact."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lease = policy.ResponderLease(str(Path(self.tmp.name) / "lease.sqlite"))
        self.record = load("human-takeover.json")

    def tearDown(self):
        self.lease.close()
        self.tmp.cleanup()

    def decide(self, ev=None, now=DAY, **kwargs):
        return policy.resolve(self.record, "ig", ev or event(), now=now,
                              lease=self.lease, tenant_id="t1",
                              thread_ref="conversation-9", **kwargs)

    def test_human_takeover_suppresses_both_responders(self):
        self.lease.takeover(tenant_id="t1", thread_ref="conversation-9",
                            actor="operator", reason="customer asked for a person")
        verdict = self.decide()
        self.assertEqual(verdict["code"], policy.SUPPRESS_HUMAN_TAKEOVER)

    def test_takeover_has_no_expiry(self):
        self.lease.takeover(tenant_id="t1", thread_ref="conversation-9",
                            actor="operator", reason="human owns it")
        future = DAY + 30 * 24 * 3600
        verdict = self.decide(now=future)
        self.assertEqual(verdict["code"], policy.SUPPRESS_HUMAN_TAKEOVER)

    def test_release_lets_a_returning_contact_back_in(self):
        first = self.decide(ev=event(message_id="m1"))
        self.assertEqual(first["code"], policy.ALLOW_NATIVE_AUTOPILOT)
        released = self.lease.release(tenant_id="t1", thread_ref="conversation-9",
                                      holder="responder")
        self.assertEqual(released["status"], "released")
        returning = self.decide(ev=event(kind="returning_contact", message_id="m2"))
        self.assertEqual(returning["code"], policy.ALLOW_NATIVE_AUTOPILOT)

    def test_foreign_holder_cannot_release_a_takeover(self):
        self.lease.takeover(tenant_id="t1", thread_ref="conversation-9",
                            actor="operator", reason="human owns it")
        outcome = self.lease.release(tenant_id="t1", thread_ref="conversation-9",
                                     holder="responder")
        self.assertEqual(outcome["status"], "refused_foreign_holder")

    def test_opt_out_suppresses_every_responder(self):
        for ev, kwargs in (
            (event(kind="opt_out"), {}),
            (event(), {"suppression_state": "global_stop"}),
            (event(), {"suppression_state": "channel_opt_out"}),
        ):
            with self.subTest(event=ev, kwargs=kwargs):
                verdict = self.decide(ev=ev, **kwargs)
                self.assertEqual(verdict["code"], policy.SUPPRESS_OPT_OUT)

    def test_quiet_hours_queue_instead_of_send(self):
        verdict = self.decide(now=NIGHT)
        self.assertEqual(verdict["code"], policy.WAIT_QUIET_HOURS)
        self.assertIsNone(verdict["responder"])

    def test_daytime_is_outside_the_window(self):
        verdict = self.decide(now=DAY)
        self.assertEqual(verdict["code"], policy.ALLOW_NATIVE_AUTOPILOT)


class ContentCannotChangePolicyTests(unittest.TestCase):
    """IG-AI-08: customer/source content never becomes administrative policy."""

    def test_event_payload_cannot_promote_native_ai(self):
        record = load("local-only.json")
        hostile = event(mode="auto-pilot", primary_responder="native_ghl",
                        allowed_actions=["grant_admin"], admin=True)
        verdict = policy.resolve(record, "sms", hostile, now=DAY)
        self.assertEqual(verdict["code"], policy.ALLOW_LOCAL)
        self.assertEqual(verdict["responder"]["allowed_actions"],
                         record["channels"]["sms"]["allowed_actions"])

    def test_event_payload_cannot_widen_allowed_actions(self):
        record = load("native-auto-pilot.json")
        hostile = event(allowed_actions=["refund_payment", "grant_admin"])
        verdict = policy.resolve(record, "whatsapp", hostile, now=DAY)
        self.assertEqual(verdict["responder"]["allowed_actions"],
                         record["channels"]["whatsapp"]["allowed_actions"])

    def test_record_cannot_grant_limits_off(self):
        record = load("local-only.json")
        record["channels"]["sms"]["limits"]["opt_out"] = False
        verdict = policy.resolve(record, "sms", event(), now=DAY)
        self.assertEqual(verdict["code"], policy.REFUSE_POLICY_WEAKENED)


class LeaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "lease.sqlite")

    def tearDown(self):
        self.tmp.cleanup()

    def test_lease_persists_and_audits(self):
        first = policy.ResponderLease(self.path)
        first.claim(tenant_id="t", thread_ref="th", event_id="m1", holder="r")
        first.close()
        reopened = policy.ResponderLease(self.path)
        self.assertIsNotNone(reopened.active("t", "th"))
        events = reopened.events("t", "th")
        self.assertEqual(events[0]["action"], "claim")
        self.assertEqual(events[0]["event_id"], "m1")
        reopened.close()

    def test_expired_lease_becomes_claimable(self):
        lease = policy.ResponderLease(self.path)
        lease.claim(tenant_id="t", thread_ref="th", event_id="m1",
                    holder="r", now=1000.0, ttl_s=10)
        self.assertIsNone(lease.active("t", "th", now=1020.0))
        claim = lease.claim(tenant_id="t", thread_ref="th", event_id="m2",
                            holder="r", now=1020.0)
        self.assertEqual(claim["status"], "acquired")
        lease.close()

    def test_unknown_channel_returns_a_refusal_not_an_exception(self):
        verdict = policy.resolve(load("local-only.json"), "linkedin", event())
        self.assertEqual(verdict["status"], "refused")
        self.assertEqual(verdict["code"], policy.REFUSE_UNSUPPORTED_CHANNEL)

    def test_channel_without_a_record_is_not_silently_allowed(self):
        verdict = policy.resolve(load("local-only.json"), "whatsapp", event())
        self.assertEqual(verdict["status"], "refused")
        self.assertEqual(verdict["code"], policy.REFUSE_NO_RESPONDER)


if __name__ == "__main__":
    unittest.main(verbosity=2)
