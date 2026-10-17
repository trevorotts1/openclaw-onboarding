"""A21 acceptance harness (S44/S50, weight 3) — production pipeline.

A21 rule (DESIGN-S44-07 section 2, Guard 2): buyer suppression is
RECHECKED at dispatch time against the authoritative entitlement book,
never decided at enqueue time. A contact can buy after a promo was
queued for them; the send must consult state at the moment it fires.

This harness drives the real pipeline (normalizer ingest ->
DurableProcessor on the durable store -> dispatch_marketing), following
the wiring of work/processor/test_processor.py, and proves:

(a) a queued marketing send to a non-buyer dispatches;
(b) the SAME queued send, dispatched after the contact buys, is
    suppressed — the recheck reads live state, so a send that would
    have fired before the purchase is stopped after it;
(c) after a FULL refund revoking every entitlement, suppression lifts
    and the same queued send dispatches again (no unsuppress job);
(d) after a PARTIAL refund (extra/bump line only), the base entitlement
    survives and suppression is KEPT.

Module-level proof only (L1/L2 semantics on the production store).
This is NOT native proof and is never labeled live proof.
"""
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE.parent / "processor"))
sys.path.insert(0, str(_HERE.parent / "store"))
sys.path.insert(0, str(_HERE.parent / "normalizer"))
from normalizer import LaunchContext, ingest
from processor import DurableProcessor, dispatch_marketing
from store import Store

CTX = LaunchContext("T1", "LOC1", "LN1",
                    {"prod-main": "main", "prod-bump": "bump"})


def readback(**overrides):
    rb = {
        "tenant_id": "T1", "location_id": "LOC1", "launch_id": "LN1",
        "provider": "ghl", "provider_event_id": "evt-1",
        "native_event_kind": "order_paid",
        "native_order_ref": "ord-1", "native_transaction_ref": "txn-1",
        "occurred_at": "2026-10-15T20:00:00Z",
        "received_at": "2026-10-15T20:00:05Z",
        "payment_status": "succeeded",
        "line_items": [
            {"native_line_ref": "li-m", "native_product_ref": "prod-main",
             "offer_id": "off-main", "currency": "USD",
             "amount_minor": 49700, "entitlement_ids": ["ent-main"]},
            {"native_line_ref": "li-b", "native_product_ref": "prod-bump",
             "offer_id": "off-bump", "currency": "USD",
             "amount_minor": 3700, "entitlement_ids": ["ent-bump"]},
        ],
        "evidence_ref": "readback/ord-1", "test_only": True,
        "contact_ref": "contact-1",
    }
    rb.update(overrides)
    return rb


class RecordingSender:
    """Stands in for the marketing send. Records every invocation so a
    test can prove the sender was NOT called, not merely that a return
    string looked right."""

    def __init__(self):
        self.calls = []

    def __call__(self, queued):
        self.calls.append(dict(queued))
        return "sent"


class A21AcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.tmp.name) / "s44.db"))
        self.proc = DurableProcessor(self.store)
        self.sender = RecordingSender()
        # the queued marketing send: created once, dispatched later —
        # enqueue performs no suppression decision (dispatch_marketing is
        # the only decision point in the pipeline)
        self.queued = {"tenant_id": "T1", "launch_id": "LN1",
                       "contact_ref": "contact-1",
                       "campaign": "promo-launch-LN1"}

    def tearDown(self):
        self.tmp.cleanup()

    def _buy(self, rb=None):
        status, payload = ingest(self.store, rb or readback(), CTX)
        self.assertEqual(status, "accepted")
        out = self.proc.process(payload["event"],
                                contact_ref=payload["contact_ref_context"])
        self.assertEqual(out["result"], "processed")

    def _refund(self, rb):
        status, payload = ingest(self.store, rb, CTX)
        self.assertEqual(status, "accepted")
        out = self.proc.process(payload["event"],
                                contact_ref="contact-1")
        self.assertEqual(out["result"], "refund_applied")

    def test_a_nonbuyer_queued_send_dispatches(self):
        self.assertFalse(self.proc.is_suppressed("T1", "LN1", "contact-1"))
        result = dispatch_marketing(self.proc, self.queued, self.sender)
        self.assertEqual(result, "sent")
        self.assertEqual(len(self.sender.calls), 1)
        self.assertEqual(self.sender.calls[0]["contact_ref"], "contact-1")

    def test_b_same_queued_send_suppressed_after_purchase(self):
        # canonical A21 timeline: the send is already sitting in the
        # queue when the purchase lands; at dispatch it must NOT fire
        self._buy()
        result = dispatch_marketing(self.proc, self.queued, self.sender)
        self.assertEqual(result, "suppressed")
        self.assertEqual(self.sender.calls, [])

    def test_b2_recheck_reads_live_state_at_each_dispatch(self):
        # the same queued object dispatched BEFORE the purchase fires;
        # dispatched again AFTER the purchase it is suppressed, and the
        # sender is not invoked a second time — proof the decision is
        # made from current state at dispatch, not cached at enqueue
        first = dispatch_marketing(self.proc, self.queued, self.sender)
        self.assertEqual(first, "sent")
        self.assertEqual(len(self.sender.calls), 1)
        self._buy()
        second = dispatch_marketing(self.proc, self.queued, self.sender)
        self.assertEqual(second, "suppressed")
        self.assertEqual(len(self.sender.calls), 1)

    def test_c_full_refund_lifts_suppression(self):
        self._buy()
        self.assertEqual(
            dispatch_marketing(self.proc, self.queued, self.sender),
            "suppressed")
        self._refund(readback(provider_event_id="evt-2",
                              native_event_kind="refund",
                              payment_status="refunded"))
        # every entitlement revoked: suppression follows ACTIVE state,
        # so it lifts on its own — there is no unsuppress job to run
        self.assertEqual(self.store.active_entitlements("T1"), [])
        self.assertFalse(self.proc.is_suppressed("T1", "LN1", "contact-1"))
        result = dispatch_marketing(self.proc, self.queued, self.sender)
        self.assertEqual(result, "sent")
        self.assertEqual(len(self.sender.calls), 1)

    def test_d_partial_refund_keeps_suppression(self):
        self._buy()
        self.assertEqual(
            dispatch_marketing(self.proc, self.queued, self.sender),
            "suppressed")
        # refund of the extra (bump) line only
        self._refund(readback(
            provider_event_id="evt-3", native_event_kind="refund",
            payment_status="partially_refunded",
            line_items=[readback()["line_items"][1]]))
        # base entitlement untouched, buyer still suppressed
        self.assertEqual(self.store.active_entitlements("T1"), ["ent-main"])
        self.assertTrue(self.proc.is_suppressed("T1", "LN1", "contact-1"))
        result = dispatch_marketing(self.proc, self.queued, self.sender)
        self.assertEqual(result, "suppressed")
        self.assertEqual(self.sender.calls, [])


if __name__ == "__main__":
    unittest.main()
