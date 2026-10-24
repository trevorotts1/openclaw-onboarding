#!/usr/bin/env python3
"""Tests for shared-utils/capture/progressive_capture.py (T-16).

Each test pins one acceptance clause from build.json T-16:

  "Single logical ask states, known fields, corrected number/unknown handling;
   pass-only when email already known."

and its checks C-16 / C-F06 / C-F11 over R-14 / R-16 and DATA-CONTRACTS 6-7.
The upstream modules are the real T-11 and T-12 ones on main - no stub is
substituted for a guard being tested.

Run:
  python3 -m unittest discover -s shared-utils/capture/tests -p 'test_*.py'
"""

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

CAPTURE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CAPTURE_DIR))

import progressive_capture as pc  # noqa: E402

UP = pc.upstream()


def _tmp() -> str:
    return tempfile.mkdtemp(prefix="pb-t16-")


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = _tmp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.identity = UP.tenant_identity.TenantIdentity(
            os.path.join(self.dir, "identity.sqlite"))
        self.store = UP.durable_store.DurableStore(
            os.path.join(self.dir, "outbox.sqlite"))
        self.addCleanup(self.store.close)
        self.tenant = "tenant-a"
        self.identity.register_tenant(self.tenant)
        self.cid = self.identity.bind(
            self.tenant, [("fb_psid", "psid-1", True)], source="test")
        self.seq = "seq-1"
        self.ask = pc.SmsEmailAsk(
            self.store, tenant_id=self.tenant,
            canonical_contact_id=self.cid,
            collection_sequence_id=self.seq,
            identity=self.identity)

    def evaluator(self, verdict="ALLOW"):
        calls = []

        def evaluate(context):
            calls.append(dict(context))
            return verdict
        evaluate.calls = calls
        return evaluate

    def sender(self, receipt=None, exc=None) -> object:
        calls = []

        def send(context):
            calls.append(dict(context))
            if exc is not None:
                raise exc
            return receipt
        send.calls = calls
        return send

    def queued_ask(self):
        row, created = self.ask.create_or_resume(body="your pass + one email ask")
        self.assertTrue(created)
        self.store.queue(row["action_id"])
        return row["action_id"]


# ── C-16: capture policy, known fields, pass-only ───────────────────────────

class CapturePlanTests(Base):
    def test_mobile_missing_is_asked_first_over_the_original_dm(self):
        plan = pc.plan_capture(pc.KnownFields(), access_ready=False)
        self.assertEqual("awaiting_mobile", plan.state)
        self.assertEqual(1, len(plan.asks))
        self.assertEqual(pc.PURPOSE_CAPTURE_REMINDER, plan.asks[0].purpose)
        self.assertEqual("mobile", plan.asks[0].field)
        self.assertFalse(plan.email_ask_allowed)

    def test_email_already_known_is_pass_only_never_an_email_ask(self):
        known = pc.KnownFields(mobile="+15550001111", email="a@example.com")
        plan = pc.plan_capture(known, access_ready=True)
        self.assertFalse(plan.email_ask_allowed)
        self.assertEqual("email_known_pass_only", plan.reason)
        self.assertEqual(1, len(plan.asks))
        self.assertEqual(pc.PURPOSE_ACCESS_PASS, plan.asks[0].purpose)
        self.assertEqual("SMS", plan.asks[0].channel)
        self.assertNotIn(pc.PURPOSE_SMS_EMAIL_ASK,
                         [ask.purpose for ask in plan.asks])

    def test_email_known_and_mobile_missing_does_not_ask_email_again(self):
        plan = pc.plan_capture(pc.KnownFields(email="a@example.com"),
                              access_ready=True)
        self.assertFalse(plan.email_ask_allowed)
        self.assertEqual((), plan.asks)
        self.assertEqual("email_known_pass_only", plan.reason)

    def test_mobile_known_and_access_ready_is_exactly_one_sms_email_ask(self):
        plan = pc.plan_capture(pc.KnownFields(mobile="+15550001111"),
                              access_ready=True)
        self.assertEqual("awaiting_email", plan.state)
        self.assertTrue(plan.email_ask_allowed)
        self.assertEqual(
            [("SMS_EMAIL_ASK", "SMS", "email")],
            [(ask.purpose, ask.channel, ask.field) for ask in plan.asks])

    def test_the_ask_waits_until_access_is_actually_ready(self):
        plan = pc.plan_capture(pc.KnownFields(mobile="+15550001111"),
                              access_ready=False)
        self.assertFalse(plan.email_ask_allowed)
        self.assertEqual("preparing_access", plan.state)
        self.assertEqual((), plan.asks)

    def test_an_open_ask_is_never_reissued(self):
        for state in (pc.ASK_QUEUED, pc.ASK_DISPATCHING, pc.ASK_ACCEPTED,
                      pc.ASK_UNKNOWN):
            plan = pc.plan_capture(pc.KnownFields(mobile="+15550001111"),
                                  access_ready=True, ask_state=state)
            self.assertFalse(plan.email_ask_allowed, state)
            self.assertEqual((), plan.asks, state)
            self.assertEqual("ask_already_exists", plan.reason, state)

    def test_the_ask_budget_is_one(self):
        plan = pc.plan_capture(pc.KnownFields(mobile="+15550001111"),
                              access_ready=True, asks_used=1)
        self.assertFalse(plan.email_ask_allowed)
        self.assertEqual("ask_budget_exhausted", plan.reason)

    def test_a_failed_not_sent_ask_may_be_retried_not_replaced(self):
        plan = pc.plan_capture(pc.KnownFields(mobile="+15550001111"),
                              access_ready=True,
                              ask_state=pc.ASK_FAILED_NOT_SENT,
                              asks_used=1)
        # The retry is a dispatch of the same action (asks_used stays 1), so
        # no *new* ask is planned.
        self.assertFalse(plan.email_ask_allowed)
        self.assertEqual("ask_budget_exhausted", plan.reason)


# ── R-16: refusal scopes ────────────────────────────────────────────────────

class RefusalTests(Base):
    def test_field_refusal_of_email_preserves_requested_sms_access(self):
        facts = pc.refuse(pc.CaptureFacts(), scope="field", value="email")
        self.assertEqual(("email",), facts.field_refusals)
        plan = pc.plan_capture(pc.KnownFields(mobile="+15550001111"),
                              facts=facts, access_ready=True)
        self.assertFalse(plan.email_ask_allowed)
        self.assertEqual("field_refused:email", plan.reason)

    def test_field_refusal_of_mobile_stops_mobile_prompts_and_keeps_email(self):
        facts = pc.refuse(pc.CaptureFacts(), scope="field", value="mobile")
        plan = pc.plan_capture(pc.KnownFields(), facts=facts)
        self.assertEqual((), plan.asks)
        self.assertEqual("field_refused:mobile", plan.reason)
        # An existing email is untouched by a mobile refusal.
        plan = pc.plan_capture(
            pc.KnownFields(mobile="+15550001111", email="a@example.com"),
            facts=facts, access_ready=True)
        self.assertEqual("email_known_pass_only", plan.reason)

    def test_sequence_decline_stops_automatic_capture(self):
        facts = pc.refuse(pc.CaptureFacts(), scope="sequence")
        self.assertEqual("stopped_declined", facts.state)
        plan = pc.plan_capture(pc.KnownFields(mobile="+15550001111"),
                              facts=facts, access_ready=True)
        self.assertEqual((), plan.asks)
        self.assertEqual("sequence_terminal", plan.reason)

    def test_a_channel_optout_blocks_only_that_channel(self):
        facts = pc.refuse(pc.CaptureFacts(), scope="channel", value="sms")
        plan = pc.plan_capture(pc.KnownFields(mobile="+15550001111"),
                              facts=facts, access_ready=True)
        self.assertFalse(plan.email_ask_allowed)
        self.assertEqual("channel_optout:SMS", plan.reason)

    def test_global_stop_and_human_ownership_suppress_every_ask(self):
        stopped = pc.refuse(pc.CaptureFacts(), scope="global")
        self.assertTrue(stopped.global_stop)
        plan = pc.plan_capture(pc.KnownFields(mobile="+15550001111"),
                              facts=stopped, access_ready=True)
        self.assertEqual((), plan.asks)
        self.assertEqual("global_stop", plan.reason)

        owned = pc.CaptureFacts(human_owner_id="human-1")
        plan = pc.plan_capture(pc.KnownFields(mobile="+15550001111"),
                              facts=owned, access_ready=True)
        self.assertEqual("human_owned", plan.state)
        self.assertEqual((), plan.asks)

    def test_unknown_refusal_scope_is_not_broader_permission(self):
        with self.assertRaises(pc.CaptureRefused):
            pc.refuse(pc.CaptureFacts(), scope="whatever")
        with self.assertRaises(pc.CaptureRefused):
            pc.refuse(pc.CaptureFacts(), scope="field", value="address")

    def test_a_field_refusal_is_case_insensitive_like_channel_optouts(self):
        # "sms" and "SMS" are one channel opt-out; "Mobile" must be one field
        # refusal too, and the refusal must reach plan_capture as "mobile".
        facts = pc.refuse(pc.CaptureFacts(), scope="field", value="Mobile")
        self.assertEqual(("mobile",), facts.field_refusals)
        plan = pc.plan_capture(pc.KnownFields(), facts=facts)
        self.assertEqual((), plan.asks)
        self.assertEqual("field_refused:mobile", plan.reason)
        # Facts built directly take the same path.
        plan = pc.plan_capture(
            pc.KnownFields(mobile="+15550001111"),
            facts=pc.CaptureFacts(field_refusals=("EMAIL",)), access_ready=True)
        self.assertFalse(plan.email_ask_allowed)
        self.assertEqual("field_refused:email", plan.reason)
        # Case folding is not blanket permission: a value that names no field
        # is still refused, and a non-string refusal still fails closed.
        with self.assertRaises(pc.CaptureRefused):
            pc.refuse(pc.CaptureFacts(), scope="field", value="address")
        with self.assertRaises(pc.CaptureError):
            pc.plan_capture(
                pc.KnownFields(),
                facts=pc.CaptureFacts(field_refusals=("address",)))

    def test_delivery_consent_is_separate_and_required(self):
        plan = pc.plan_capture(pc.KnownFields(mobile="+15550001111"),
                              facts=pc.CaptureFacts(delivery_consent=False),
                              access_ready=True)
        self.assertEqual((), plan.asks)
        self.assertEqual("delivery_consent_missing", plan.reason)


# ── C-16 / C-F06: one durable ask and its receipt states ────────────────────

class SingleAskTests(Base):
    def test_the_same_capture_creates_exactly_one_action(self):
        first, created = self.ask.create_or_resume(body="ask body")
        second, created_again = self.ask.create_or_resume(body="ask body")
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first["action_id"], second["action_id"])
        self.assertEqual(1, self.store.counts()["actions"])

    def test_a_different_capture_gets_its_own_ask(self):
        first, _ = self.ask.create_or_resume(body="ask body")
        other = pc.SmsEmailAsk(
            self.store, tenant_id=self.tenant,
            canonical_contact_id=self.cid, collection_sequence_id="seq-2")
        second, _ = other.create_or_resume(body="ask body")
        self.assertNotEqual(first["action_id"], second["action_id"])

    def test_receipt_state_walks_queued_to_accepted_and_is_never_completed(self):
        action_id = self.queued_ask()
        self.assertEqual(pc.ASK_QUEUED, self.ask.state())
        sender = self.sender(receipt={"provider": "twilio",
                                      "provider_message_id": "SM123",
                                      "evidence_id": "ev-1"})
        outcome = self.ask.dispatch(self.evaluator(), sender, "w1")
        self.assertTrue(outcome.sent)
        self.assertEqual(pc.ASK_ACCEPTED, self.ask.state())
        self.assertEqual(pc.ASK_ACCEPTED, self.ask.state_after(outcome))
        view = self.ask.view()
        self.assertEqual(pc.ASK_ACCEPTED, view["state"])
        self.assertEqual("SM123", view["provider_message_id"])
        self.assertEqual("ev-1", view["evidence_id"])
        # Accepted is not completed: the store keeps separate receipts.
        self.assertEqual("dispatched", self.store.get_action(action_id)["state"])

    def test_no_verdict_means_unknown_not_failed(self):
        self.queued_ask()
        outcome = self.ask.dispatch(self.evaluator(), self.sender(receipt=None), "w1")
        self.assertEqual(UP.outbound_gate.ST_UNKNOWN, outcome.status)
        self.assertEqual(pc.ASK_UNKNOWN, self.ask.state())

    def test_a_raising_sender_is_unknown_not_a_reason_to_retry(self):
        self.queued_ask()
        outcome = self.ask.dispatch(
            self.evaluator(), self.sender(exc=TimeoutError("no verdict")), "w1")
        self.assertEqual(UP.outbound_gate.ST_SEND_ERROR, outcome.status)
        self.assertEqual(pc.ASK_UNKNOWN, self.ask.state())
        with self.assertRaises(pc.CaptureRefused):
            self.ask.retry_after_correction(
                corrected_mobile="+15550002222", evaluator=self.evaluator(),
                sender=self.sender(receipt={"provider": "twilio"}), worker_id="w1")

    def test_accepted_ask_is_not_repeated_because_the_person_stayed_silent(self):
        self.queued_ask()
        self.ask.dispatch(self.evaluator(),
                          self.sender(receipt={"provider": "twilio"}), "w1")
        plan = pc.plan_capture(pc.KnownFields(mobile="+15550001111"),
                              access_ready=True, ask_state=self.ask.state(),
                              asks_used=1)
        self.assertEqual((), plan.asks)
        _, created = self.ask.create_or_resume(body="ask body again")
        self.assertFalse(created)

    def test_carrier_failure_after_acceptance_is_not_nonexecution(self):
        self.queued_ask()
        self.ask.dispatch(self.evaluator(),
                          self.sender(receipt={"provider": "twilio"}), "w1")
        with self.assertRaises(pc.CaptureRefused):
            self.ask.record_known_nonexecution("carrier reported a late failure")
        self.assertEqual(pc.ASK_ACCEPTED, self.ask.state())

    def test_a_corrected_number_retries_the_same_ask(self):
        action_id = self.queued_ask()
        outcome = self.ask.dispatch(
            self.evaluator(), self.sender(exc=ConnectionError("dial failed")), "w1")
        self.assertEqual(UP.outbound_gate.ST_SEND_ERROR, outcome.status)
        # Provider evidence: nothing was sent. Known nonexecution only.
        self.ask.reconcile("not_applied", {"evidence": "carrier log ev-9"})
        self.ask.record_known_nonexecution("carrier rejected the handset number")
        self.assertEqual(pc.ASK_FAILED_NOT_SENT, self.ask.state())

        retry = self.ask.retry_after_correction(
            corrected_mobile="+15550002222", evaluator=self.evaluator(),
            sender=self.sender(receipt={"provider": "twilio"}), worker_id="w1")
        self.assertTrue(retry.sent)
        self.assertEqual(action_id, retry.action_id)
        self.assertEqual(1, self.store.counts()["actions"])
        self.assertEqual(pc.ASK_ACCEPTED, self.ask.state())

    def test_unknown_ask_is_not_replayed_until_it_reconciles(self):
        self.queued_ask()
        self.ask.dispatch(self.evaluator(), self.sender(receipt=None), "w1")
        self.assertEqual(pc.ASK_UNKNOWN, self.ask.state())
        # The reason is pinned, not just the class: without it, deleting the
        # unknown guard is hidden behind the later "retry requires known
        # nonexecution" guard, which raises the same exception type.
        with self.assertRaisesRegex(pc.CaptureRefused,
                                   "unknown ask must reconcile"):
            self.ask.retry_after_correction(
                corrected_mobile="+15550002222", evaluator=self.evaluator(),
                sender=self.sender(receipt={"provider": "twilio"}), worker_id="w1")
        # Reconciled as applied: the effect exists, so it is accepted, not resent.
        self.ask.reconcile("applied", {"evidence": "carrier ev-10"},
                           receipt={"provider": "twilio",
                                    "provider_message_id": "SM999"})
        self.assertEqual(pc.ASK_ACCEPTED, self.ask.state())
        with self.assertRaisesRegex(pc.CaptureRefused,
                                   "accepted ask is not a new or retryable send"):
            self.ask.retry_after_correction(
                corrected_mobile="+15550002222", evaluator=self.evaluator(),
                sender=self.sender(receipt={"provider": "twilio"}), worker_id="w1")
        self.assertEqual(1, self.store.counts()["actions"])

    def test_unknown_that_reconciles_not_applied_becomes_retryable(self):
        self.queued_ask()
        self.ask.dispatch(self.evaluator(), self.sender(receipt=None), "w1")
        self.ask.reconcile("not_applied", {"evidence": "carrier ev-11"})
        self.ask.record_known_nonexecution("provider confirmed nonexecution")
        self.assertEqual(pc.ASK_FAILED_NOT_SENT, self.ask.state())
        retry = self.ask.retry_after_correction(
            corrected_mobile="+15550003333", evaluator=self.evaluator(),
            sender=self.sender(receipt={"provider": "twilio"}), worker_id="w1")
        self.assertTrue(retry.sent)
        self.assertEqual(1, self.store.counts()["actions"])

    def test_email_before_dispatch_suppresses_the_ask_and_leaves_a_pass(self):
        action_id = self.queued_ask()
        result = self.ask.email_arrived_before_dispatch(access_ready=True)
        self.assertTrue(result["suppressed"])
        self.assertEqual(pc.ASK_SUPPRESSED, result["ask_state"])
        self.assertEqual(pc.ASK_SUPPRESSED, self.ask.state())
        pass_id = result["pass_only_action_id"]
        self.assertIsNotNone(pass_id)
        self.assertNotEqual(action_id, pass_id)
        self.assertEqual(pc.PURPOSE_ACCESS_PASS,
                         self.store.get_action(pass_id)["purpose"])
        # The ask itself never dispatched, and no second ask was minted.
        self.assertEqual(2, self.store.counts()["actions"])
        self.assertEqual(0, self.store.attempts(action_id).__len__())
        plan = pc.plan_capture(
            pc.KnownFields(mobile="+15550001111", email="a@example.com"),
            access_ready=True)
        self.assertFalse(plan.email_ask_allowed)

    def test_email_after_acceptance_cannot_be_retroactively_suppressed(self):
        self.queued_ask()
        self.ask.dispatch(self.evaluator(),
                          self.sender(receipt={"provider": "twilio"}), "w1")
        with self.assertRaises(pc.CaptureRefused):
            self.ask.email_arrived_before_dispatch(access_ready=True)
        self.assertEqual(pc.ASK_ACCEPTED, self.ask.state())

    def test_email_before_any_ask_creates_no_ask_at_all(self):
        result = self.ask.email_arrived_before_dispatch(access_ready=True)
        self.assertEqual(pc.ASK_NOT_CREATED, result["ask_state"])
        self.assertFalse(result["suppressed"])
        self.assertIsNone(self.store.action_by_intent(self.ask.logical_intent_key))
        self.assertEqual(pc.PURPOSE_ACCESS_PASS,
                         self.store.get_action(result["pass_only_action_id"])["purpose"])

    def test_the_view_matches_the_contract_schema_in_every_ask_state(self):
        action_id = self.queued_ask()
        self.assertEqual(pc.ASK_QUEUED, self.ask.view()["state"])
        self.ask.dispatch(self.evaluator(), self.sender(receipt=None), "w1")
        self.assertEqual(pc.ASK_UNKNOWN, self.ask.view()["state"])
        self.ask.reconcile("not_applied", {"evidence": "ev-12"})
        self.ask.record_known_nonexecution("nonexecution")
        self.assertEqual(pc.ASK_FAILED_NOT_SENT, self.ask.view()["state"])
        self.assertEqual(action_id, self.ask.view()["logical_action_id"])


# ── C-16: the gate is fresh on every send and every retry ───────────────────

class FreshGateTests(Base):
    def test_every_dispatch_records_its_own_fresh_verdict(self):
        self.queued_ask()
        calls = []

        def sequential(context):
            calls.append(dict(context))
            if len(calls) == 1:
                return {"verdict": "WAIT_UNTIL", "wait_until": 0.0,
                        "checked_at": context["now"]}
            return "ALLOW"

        outcome = self.ask.dispatch(sequential,
                                    self.sender(receipt={"provider": "twilio"}),
                                    "w1")
        self.assertEqual(UP.outbound_gate.ST_BLOCKED, outcome.status)
        self.assertEqual(pc.ASK_QUEUED, self.ask.state())
        outcome = self.ask.dispatch(sequential,
                                    self.sender(receipt={"provider": "twilio"}),
                                    "w2")
        self.assertTrue(outcome.sent)
        checks = self.store.gate_checks(self.ask.require_action()["action_id"])
        self.assertEqual(2, len(checks))
        self.assertEqual([1, 2], sorted(int(c["attempt_no"]) for c in checks))
        self.assertEqual(2, len(calls))

    def test_a_blocking_verdict_means_the_sender_is_never_called(self):
        self.queued_ask()
        sender = self.sender(receipt={"provider": "twilio"})
        outcome = self.ask.dispatch(self.evaluator("SUPPRESSED"), sender, "w1")
        self.assertEqual(UP.outbound_gate.ST_BLOCKED, outcome.status)
        self.assertEqual(0, len(sender.calls))
        self.assertEqual(pc.ASK_SUPPRESSED, self.ask.state())

    def test_a_retry_still_passes_a_new_gate(self):
        self.queued_ask()
        self.ask.dispatch(self.evaluator(), self.sender(receipt=None), "w1")
        self.ask.reconcile("not_applied", {"evidence": "ev-13"})
        self.ask.record_known_nonexecution("provider confirmed nonexecution")
        sender = self.sender(receipt={"provider": "twilio"})
        outcome = self.ask.retry_after_correction(
            corrected_mobile="+15550004444", evaluator=self.evaluator("QUARANTINED"),
            sender=sender, worker_id="w1")
        self.assertEqual(UP.outbound_gate.ST_BLOCKED, outcome.status)
        self.assertEqual("QUARANTINED", outcome.verdict)
        self.assertEqual(0, len(sender.calls))
        self.assertEqual(pc.ASK_SUPPRESSED, self.ask.state())


# ── C-16: the send boundary only ever touches THIS ask ──────────────────────

class OwnActionBoundaryTests(Base):
    """A foreign action_id must never be sent AS the one logical SMS email ask.

    The identity of an ask is (tenant_id, canonical_contact_id,
    logical_intent_key, purpose). Any row that does not match all four is not
    this ask: another person's action, this person's ACCESS_PASS, or another
    sequence's ask. Each case below is refused before the sender is called,
    and the same call on this ask still sends - so the guard cannot be
    satisfied by blanket refusal.
    """

    def foreign_action(self, *, key: str, contact_id: str,
                       purpose: str) -> str:
        row, _ = self.store.create_intent(
            logical_intent_key=key, idempotency_key=key,
            tenant_id=self.tenant, scope="person_directed",
            purpose=purpose, canonical_contact_id=contact_id,
            content_sha256="deadbeef")
        self.store.queue(row["action_id"])
        return row["action_id"]

    def foreign_rows(self):
        other = self.identity.bind(
            self.tenant, [("fb_psid", "psid-2", True)], source="test")
        return {
            "another contact's ACCESS_PASS": self.foreign_action(
                key="access-pass:%s:%s:seq-1" % (self.tenant, other),
                contact_id=other, purpose=pc.PURPOSE_ACCESS_PASS),
            "this contact's ACCESS_PASS": self.foreign_action(
                key=self.ask.pass_intent_key,
                contact_id=self.cid, purpose=pc.PURPOSE_ACCESS_PASS),
            "another sequence's ask": self.foreign_action(
                key="sms-email-ask:%s:%s:seq-2" % (self.tenant, self.cid),
                contact_id=self.cid, purpose=pc.PURPOSE_SMS_EMAIL_ASK),
        }

    def test_a_foreign_action_is_never_sent_as_this_ask(self):
        mine = self.queued_ask()
        for label, foreign in self.foreign_rows().items():
            with self.subTest(label):
                sender = self.sender(receipt={"provider": "twilio",
                                              "provider_message_id": "SMX"})
                with self.assertRaisesRegex(
                        pc.CaptureRefused, "is not this SMS email ask"):
                    self.ask.dispatch(self.evaluator(), sender, "w1",
                                      action_id=foreign)
                self.assertEqual([], sender.calls, label)
                self.assertEqual("queued", self.store.get_action(foreign)["state"],
                                 label)
                self.assertEqual({}, self.store.receipts(foreign), label)
        # Inverse: the same dispatch on this ask still sends.
        sender = self.sender(receipt={"provider": "twilio",
                                      "provider_message_id": "SM1"})
        outcome = self.ask.dispatch(self.evaluator(), sender, "w1",
                                    action_id=mine)
        self.assertTrue(outcome.sent)
        self.assertEqual(1, len(sender.calls))
        self.assertEqual(pc.ASK_ACCEPTED, self.ask.state())

    def test_state_and_view_refuse_a_foreign_action(self):
        mine = self.queued_ask()
        for label, foreign in self.foreign_rows().items():
            with self.subTest(label):
                with self.assertRaisesRegex(
                        pc.CaptureRefused, "is not this SMS email ask"):
                    self.ask.state(foreign)
                with self.assertRaisesRegex(
                        pc.CaptureRefused, "is not this SMS email ask"):
                    self.ask.view(foreign)
        # Inverse: this ask's own id still reports its state and view.
        self.assertEqual(pc.ASK_QUEUED, self.ask.state(mine))
        self.assertEqual(mine, self.ask.view(mine)["logical_action_id"])

    def test_retry_after_correction_stays_on_this_ask(self):
        self.queued_ask()
        self.ask.dispatch(self.evaluator(),
                          self.sender(exc=ConnectionError("dial failed")), "w1")
        self.ask.reconcile("not_applied", {"evidence": "carrier log ev-9"})
        self.ask.record_known_nonexecution("carrier rejected the handset number")
        outcome = self.ask.retry_after_correction(
            corrected_mobile="+15550002222", evaluator=self.evaluator(),
            sender=self.sender(receipt={"provider": "twilio"}), worker_id="w1")
        self.assertTrue(outcome.sent)
        self.assertEqual(self.ask.require_action()["action_id"], outcome.action_id)
        self.assertEqual(1, self.store.counts()["actions"])


# ── C-F11: the later email binds to the same verified member ───────────────

class EmailIdentityTests(Base):
    def test_a_later_email_binds_to_the_same_member(self):
        resolved = pc.bind_email(
            self.identity, tenant_id=self.tenant,
            canonical_contact_id=self.cid, email="Later@Example.com")
        self.assertEqual(self.cid, resolved)
        self.assertEqual(
            self.cid,
            self.identity.resolve(self.tenant, "email", "later@example.com"))
        contact = self.identity.contact(self.tenant, self.cid)
        self.assertIsNotNone(contact)

    def test_an_email_belonging_to_someone_else_is_refused_not_merged(self):
        other = self.identity.bind(
            self.tenant, [("fb_psid", "psid-2", True)], source="test")
        self.assertNotEqual(self.cid, other)
        pc.bind_email(self.identity, tenant_id=self.tenant,
                      canonical_contact_id=other, email="b@example.com")
        with self.assertRaises(pc.CaptureConflict):
            pc.bind_email(self.identity, tenant_id=self.tenant,
                          canonical_contact_id=self.cid, email="b@example.com")

    def test_the_same_email_in_another_tenant_is_another_member(self):
        self.identity.register_tenant("tenant-b")
        cid_b = self.identity.bind(
            "tenant-b", [("fb_psid", "psid-1", True)], source="test")
        pc.bind_email(self.identity, tenant_id=self.tenant,
                      canonical_contact_id=self.cid, email="a@example.com")
        self.assertIsNone(
            self.identity.resolve("tenant-b", "email", "a@example.com"))
        bound = pc.bind_email(self.identity, tenant_id="tenant-b",
                              canonical_contact_id=cid_b, email="a@example.com")
        self.assertEqual(cid_b, bound)
        self.assertNotEqual(self.cid, bound)

    def test_binding_refuses_an_unregistered_tenant(self):
        with self.assertRaises(UP.tenant_identity.UnknownTenant):
            pc.bind_email(self.identity, tenant_id="tenant-z",
                          canonical_contact_id=self.cid, email="z@example.com")


# ── T-11 collection lock: a stale writer cannot create or advance the ask ──

class CollectionFenceTests(Base):
    def setUp(self):
        super().setUp()
        self.lock = UP.collection_lock.CollectionLock(self.identity)
        self.ask = pc.SmsEmailAsk(
            self.store, tenant_id=self.tenant,
            canonical_contact_id=self.cid,
            collection_sequence_id=self.seq,
            identity=self.identity, lock=self.lock)

    def test_a_locked_capture_requires_a_live_fence(self):
        with self.assertRaises(pc.CaptureError):
            self.ask.create_or_resume(body="ask body")

    def test_a_live_fence_creates_the_ask(self):
        lease = self.lock.acquire(self.tenant, self.cid, self.seq, "worker-1")
        self.assertTrue(lease.granted)
        row, created = self.ask.create_or_resume(
            body="ask body", owner_id=lease.owner_id, fence=lease.fence)
        self.assertTrue(created)
        self.assertEqual(pc.ASK_NOT_CREATED, self.ask.state(row["action_id"]))

    def test_a_stale_fence_is_refused(self):
        first = self.lock.acquire(self.tenant, self.cid, self.seq, "worker-1")
        self.lock.release(self.tenant, self.cid, self.seq,
                          first.owner_id, first.fence)
        second = self.lock.acquire(self.tenant, self.cid, self.seq, "worker-2")
        self.assertGreater(second.fence, first.fence)
        with self.assertRaises(UP.collection_lock.StaleWriter):
            self.ask.create_or_resume(body="ask body",
                                      owner_id=first.owner_id,
                                      fence=first.fence)


if __name__ == "__main__":
    unittest.main(verbosity=2)
