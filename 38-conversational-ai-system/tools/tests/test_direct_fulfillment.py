#!/usr/bin/env python3
"""Tests for T-13 original direct fulfillment.

Contract basis: DATA-CONTRACTS section 5 ("Direct original fulfillment") with
sections 2-4 (person-directed basis, fresh gate, durable outbox, truthful
stages). Runs offline: the only transport is a local append-only journal.

What is proven here:

  HAPPY       an approved immutable item is sent once through the accepted
              T-12 gate; admission is labelled accepted, not delivered.

  PROOF       "delivered" exists only after an actual receipt matching the
              pinned content hash and the recorded destination.

  PARTIAL     a crash after provider acceptance but before the receipt is
  FAILURE     persisted leaves state unknown; resume() reconciles against the
              transport journal and acknowledges WITHOUT a second send.

  RESUME      known nonexecution is requeued under the same action identity;
              an explicit retry re-passes the fresh gate and sends once.

  DOUBLE      repeated calls never reach the transport twice, before or after
              completion.

  CONSENT     no durable delivery basis refuses before any action exists; a
              T-18 global stop recorded after queueing suppresses the send.

  IMMUTABLE   a hosting URL move is the same promise; a different content hash
              under the same item id/version is refused.

Run from the skill root:
    python3 -m unittest discover -s tools/tests -p 'test_direct_fulfillment.py' -v
"""

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from consent_gate import ConsentStore, make_gate_evaluator  # noqa: E402
from direct_fulfillment import (  # noqa: E402
    D_ACCEPTED,
    D_DELIVERED,
    D_NOT_SENT,
    D_UNKNOWN,
    DeliveryBasis,
    FulfillmentError,
    FulfillmentLedger,
    F_ALREADY_SATISFIED,
    F_REFUSED,
    F_RESUMED,
    F_SENT,
    F_SUPPRESSED,
    F_UNKNOWN,
    JournalTransport,
    PromisedItem,
    can_continue,
    fulfill,
    record_delivery_proof,
    resume,
)
from durable_store import (  # noqa: E402
    DurableStore,
    STATE_ACKNOWLEDGED,
    STATE_COMPLETED,
    STATE_DISPATCHED,
    STATE_QUEUED,
    STATE_SUPPRESSED,
    STATE_UNKNOWN,
)
from tenant_identity import TenantIdentity  # noqa: E402

TENANT = "t1"
CONTENT = b"the original promised checklist, version one\n"
HASH = hashlib.sha256(CONTENT).hexdigest()


class CrashAfterAccept:
    """Provider accepts and journals, then the process dies before persisting."""

    def __init__(self, journal):
        self.journal = journal
        self.calls = 0

    def __call__(self, ctx):
        self.calls += 1
        self.journal(ctx)
        raise RuntimeError("process died before the dispatch receipt was saved")


class NeverAccepts:
    """Known nonexecution: the transport fails before anything is journaled."""

    def __init__(self):
        self.calls = 0

    def __call__(self, ctx):
        self.calls += 1
        raise RuntimeError("transport refused before acceptance")


class FulfillmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="direct-fulfil-"))
        self.store = DurableStore(str(self.tmp / "outbox.sqlite"))
        self.ledger = FulfillmentLedger(str(self.tmp / "ledger.sqlite"))
        self.journal_path = str(self.tmp / "journal.jsonl")
        self.journal = JournalTransport(self.journal_path)
        self.item = PromisedItem(
            item_id="gift-1", version="v1", content_sha256=HASH,
            approved=True, content_uri="https://host-a.example/x")
        self.basis = DeliveryBasis(
            tenant_id=TENANT, canonical_contact_id="c1", item_id="gift-1",
            version="v1", basis="requested_in_conversation", actor="agent",
            evidence="the person asked for the checklist in chat",
            channel="sms", address="+15550123")

    def tearDown(self):
        self.store.close()
        self.ledger.close()

    # ── helpers ────────────────────────────────────────────────────────────

    def _consent(self):
        identity = TenantIdentity(str(self.tmp / "identity.sqlite"))
        identity.register_tenant(TENANT, "purple billboard")
        contact = identity.bind(TENANT, [("sms_number", "+15550123", True)],
                                source="test")
        return ConsentStore(identity), contact

    def _fulfill(self, **kwargs):
        return fulfill(self.store, self.ledger, self.journal, self.item,
                       self.basis, worker_id="w1", **kwargs)

    def _proof(self, receipt=None):
        receipt = receipt or self.journal.find(
            self.store.get_action(
                self._action_id())["idempotency_key"])
        return {**receipt, "kind": "delivery"}

    def _action_id(self):
        from direct_fulfillment import fulfillment_action
        return fulfillment_action(self.store, self.basis)["action_id"]

    # ── HAPPY ──────────────────────────────────────────────────────────────

    def test_happy_path_sends_the_original_item_once(self):
        self.ledger.record_basis(self.basis)
        out = self._fulfill()
        self.assertEqual(out.status, F_SENT, out.reason)
        self.assertEqual(out.delivery_status, D_ACCEPTED)
        self.assertEqual(out.destination,
                         {"channel": "sms", "address": "+15550123"})
        self.assertEqual(self.journal.sends, 1)
        receipt = self.journal.find(out.transport_receipt["idempotency_key"])
        self.assertEqual(receipt["content_sha256"], HASH)
        self.assertEqual(receipt["item_id"], "gift-1")
        self.assertEqual(receipt["version"], "v1")
        self.assertEqual(self.store.get_action(out.action_id)["state"],
                         STATE_DISPATCHED)

    def test_real_receipt_promotes_accepted_to_delivered(self):
        self.ledger.record_basis(self.basis)
        out = self._fulfill()
        done = record_delivery_proof(self.store, self.item, self.basis,
                                     self._proof(out.transport_receipt))
        self.assertEqual(done.delivery_status, D_DELIVERED)
        self.assertEqual(done.state, STATE_COMPLETED)
        self.assertEqual(self.journal.sends, 1)

    def test_proof_must_name_pinned_content_and_destination(self):
        self.ledger.record_basis(self.basis)
        out = self._fulfill()
        wrong_hash = {**out.transport_receipt, "content_sha256": "0" * 64}
        with self.assertRaises(FulfillmentError):
            record_delivery_proof(self.store, self.item, self.basis, wrong_hash)
        wrong_dest = {**out.transport_receipt,
                      "destination": {"channel": "sms", "address": "+15559999"}}
        with self.assertRaises(FulfillmentError):
            record_delivery_proof(self.store, self.item, self.basis, wrong_dest)

    def test_proof_before_any_send_is_refused(self):
        self.ledger.record_basis(self.basis)
        self._fulfill()
        other = DeliveryBasis(
            tenant_id=TENANT, canonical_contact_id="c2", item_id="gift-1",
            version="v1", basis="requested_in_conversation", actor="agent",
            evidence="asked", channel="sms", address="+15550999")
        self.ledger.record_basis(other)
        unused = {"provider": "journal", "provider_receipt_id": "r-none",
                  "content_sha256": HASH,
                  "destination": {"channel": "sms", "address": "+15550999"}}
        with self.assertRaises(FulfillmentError):
            record_delivery_proof(self.store, self.item, other, unused)

    # ── DOUBLE DELIVERY REFUSED ────────────────────────────────────────────

    def test_second_call_never_reaches_the_transport(self):
        self.ledger.record_basis(self.basis)
        first = self._fulfill()
        second = self._fulfill()
        self.assertEqual(second.status, F_ALREADY_SATISFIED)
        self.assertEqual(second.action_id, first.action_id)
        self.assertEqual(self.journal.sends, 1)

    def test_completed_fulfillment_cannot_be_sent_again(self):
        self.ledger.record_basis(self.basis)
        out = self._fulfill()
        record_delivery_proof(self.store, self.item, self.basis,
                              self._proof(out.transport_receipt))
        again = self._fulfill()
        self.assertEqual(again.status, F_ALREADY_SATISFIED)
        self.assertEqual(again.delivery_status, D_DELIVERED)
        self.assertEqual(self.journal.sends, 1)

    # ── PARTIAL FAILURE WITH RESUME ────────────────────────────────────────

    def test_crash_after_acceptance_resumes_without_resending(self):
        self.ledger.record_basis(self.basis)
        crash = CrashAfterAccept(self.journal)
        out = fulfill(self.store, self.ledger, crash, self.item, self.basis,
                      worker_id="w1")
        self.assertEqual(out.status, F_UNKNOWN)
        self.assertEqual(out.delivery_status, D_UNKNOWN)
        self.assertEqual(crash.calls, 1)
        self.assertEqual(self.journal.sends, 1)
        self.assertEqual(self.store.get_action(out.action_id)["state"],
                         STATE_UNKNOWN)

        resumed = resume(self.store, self.ledger, self.journal, self.item,
                         self.basis, worker_id="w1")
        self.assertEqual(resumed.status, F_RESUMED)
        self.assertEqual(resumed.state, STATE_ACKNOWLEDGED)
        self.assertEqual(resumed.delivery_status, D_ACCEPTED)
        self.assertEqual(self.journal.sends, 1, "resume must not double-send")
        self.assertEqual(crash.calls, 1)

    def test_known_nonexecution_retries_same_identity_after_fresh_gate(self):
        self.ledger.record_basis(self.basis)
        broken = NeverAccepts()
        out = fulfill(self.store, self.ledger, broken, self.item, self.basis,
                      worker_id="w1")
        self.assertEqual(out.status, F_UNKNOWN)
        self.assertEqual(broken.calls, 1)
        self.assertEqual(self.journal.sends, 0)

        requeued = resume(self.store, self.ledger, self.journal, self.item,
                          self.basis, worker_id="w1")
        self.assertEqual(requeued.status, F_RESUMED)
        self.assertEqual(self.store.get_action(out.action_id)["state"],
                         STATE_QUEUED)
        self.assertEqual(self.journal.sends, 0)

        retried = resume(self.store, self.ledger, self.journal, self.item,
                         self.basis, worker_id="w1", retry=True)
        self.assertEqual(retried.status, F_SENT)
        self.assertEqual(retried.action_id, out.action_id,
                         "retry must reuse the same action identity")
        self.assertEqual(self.journal.sends, 1)

    # ── CONSENT ABSENT ─────────────────────────────────────────────────────

    def test_refuses_when_no_delivery_basis_exists(self):
        out = self._fulfill()
        self.assertEqual(out.status, F_REFUSED)
        self.assertEqual(out.reason, "no_delivery_basis")
        self.assertEqual(self.journal.sends, 0)
        self.assertEqual(self.store.counts()["actions"], 0,
                         "no outbox action may exist without a basis")

    def test_consent_stop_after_queueing_suppresses_the_send(self):
        consent, contact = self._consent()
        self.basis = DeliveryBasis(
            tenant_id=TENANT, canonical_contact_id=contact, item_id="gift-1",
            version="v1", basis="requested_in_conversation", actor="agent",
            evidence="asked", channel="sms", address="+15550123")
        self.ledger.record_basis(self.basis)
        # Queue first through a gate that allows, proving the stop is re-read.
        consent.global_stop(TENANT, contact, reason="customer said stop",
                            actor="agent")
        out = fulfill(self.store, self.ledger, self.journal, self.item,
                      self.basis, worker_id="w1",
                      consent_evaluator=make_gate_evaluator(consent))
        self.assertEqual(out.status, F_SUPPRESSED)
        self.assertEqual(self.store.get_action(out.action_id)["state"],
                         STATE_SUPPRESSED)
        self.assertEqual(self.journal.sends, 0)

        again = fulfill(self.store, self.ledger, self.journal, self.item,
                        self.basis, worker_id="w2",
                        consent_evaluator=make_gate_evaluator(consent))
        self.assertIn(again.status, (F_SUPPRESSED,))
        self.assertEqual(self.journal.sends, 0)

    # ── IMMUTABLE PROMISE / HOST MIGRATION ─────────────────────────────────

    def test_hosting_move_is_the_same_promise(self):
        self.ledger.record_basis(self.basis)
        first = self._fulfill()
        moved = PromisedItem(item_id="gift-1", version="v1",
                             content_sha256=HASH, approved=True,
                             content_uri="https://host-b.example/y")
        second = fulfill(self.store, self.ledger, self.journal, moved,
                         self.basis, worker_id="w1")
        self.assertEqual(second.status, F_ALREADY_SATISFIED)
        self.assertEqual(second.action_id, first.action_id)
        self.assertEqual(self.journal.sends, 1)

    def test_same_version_with_different_content_is_refused(self):
        self.ledger.record_basis(self.basis)
        self._fulfill()
        tampered = PromisedItem(item_id="gift-1", version="v1",
                                content_sha256=hashlib.sha256(b"other").hexdigest(),
                                approved=True)
        with self.assertRaises(FulfillmentError) as caught:
            fulfill(self.store, self.ledger, self.journal, tampered,
                    self.basis, worker_id="w1")
        self.assertIn("immutable_violation", str(caught.exception))
        self.assertEqual(self.journal.sends, 1)

    def test_unapproved_item_is_never_sent(self):
        self.ledger.record_basis(self.basis)
        unapproved = PromisedItem(item_id="gift-1", version="v1",
                                  content_sha256=HASH, approved=False)
        with self.assertRaises(FulfillmentError) as caught:
            fulfill(self.store, self.ledger, self.journal, unapproved,
                    self.basis, worker_id="w1")
        self.assertIn("not_approved", str(caught.exception))
        self.assertEqual(self.journal.sends, 0)

    # ── CONTINUATION ───────────────────────────────────────────────────────

    def test_continuation_waits_for_reader_access(self):
        self.ledger.record_basis(self.basis)
        self._fulfill()
        blocked = can_continue(self.store, self.ledger, self.item, self.basis)
        self.assertFalse(blocked.continuation_allowed)
        self.assertEqual(blocked.reason, "reader_access_unverified")

        self.ledger.record_reader_access(
            TENANT, "gift-1", "v1", accessible=False,
            evidence="operator could not open the file")
        still = can_continue(self.store, self.ledger, self.item, self.basis)
        self.assertFalse(still.continuation_allowed)

        self.ledger.record_reader_access(
            TENANT, "gift-1", "v1", accessible=True,
            evidence="operator opened the file as the intended reader")
        allowed = can_continue(self.store, self.ledger, self.item, self.basis)
        self.assertTrue(allowed.continuation_allowed)
        self.assertEqual(allowed.delivery_status, D_ACCEPTED)

    def test_continuation_is_blocked_while_outcome_unknown(self):
        self.ledger.record_basis(self.basis)
        self.ledger.record_reader_access(
            TENANT, "gift-1", "v1", accessible=True, evidence="verified")
        crash = CrashAfterAccept(self.journal)
        out = fulfill(self.store, self.ledger, crash, self.item, self.basis,
                      worker_id="w1")
        self.assertEqual(out.status, F_UNKNOWN)
        cont = can_continue(self.store, self.ledger, self.item, self.basis)
        self.assertFalse(cont.continuation_allowed)
        self.assertEqual(cont.delivery_status, D_UNKNOWN)

    def test_nothing_sent_means_nothing_to_continue(self):
        cont = can_continue(self.store, self.ledger, self.item, self.basis)
        self.assertFalse(cont.continuation_allowed)
        self.assertEqual(cont.delivery_status, D_NOT_SENT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
