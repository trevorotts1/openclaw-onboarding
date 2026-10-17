"""S44-06/07 durable processor proofs: same acceptance semantics as
the L1 suite, now against the production store, plus the tag seam,
fulfillment parking, and refund-unsuppresses behavior."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "store"))
sys.path.insert(0, str(Path(__file__).parent.parent / "normalizer"))
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


class ProcessorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.tmp.name) / "s44.db"))
        self.tags_applied = []
        self.proc = DurableProcessor(
            self.store,
            tag_applier=lambda c, t: self.tags_applied.append((c, t)),
            purchase_tag="siglaunch:purchased:main")

    def tearDown(self):
        self.tmp.cleanup()

    def _ingest_process(self, rb):
        status, payload = ingest(self.store, rb, CTX)
        self.assertEqual(status, "accepted")
        return self.proc.process(payload["event"],
                                 contact_ref=payload["contact_ref_context"])

    def test_full_pipeline_end_to_end(self):
        result = self._ingest_process(readback())
        self.assertEqual(result["result"], "processed")
        self.assertEqual(self.store.active_entitlements("T1"),
                         ["ent-bump", "ent-main"])
        # tag applied exactly once, verbatim Phase-A string
        self.assertEqual(self.tags_applied,
                         [("contact-1", "siglaunch:purchased:main")])
        # buyer suppressed via the authority check
        self.assertTrue(self.proc.is_suppressed("T1", "LN1", "contact-1"))
        sent = dispatch_marketing(
            self.proc,
            {"tenant_id": "T1", "launch_id": "LN1",
             "contact_ref": "contact-1"},
            lambda q: "sent")
        self.assertEqual(sent, "suppressed")

    def test_duplicate_event_no_duplicate_effects(self):
        self._ingest_process(readback())
        # redelivery: the normalizer's ingest dedups before the processor
        status, _ = ingest(self.store, readback(), CTX)
        self.assertEqual(status, "duplicate")
        self.assertEqual(len(self.tags_applied), 1)

    def test_pending_never_grants(self):
        result = self._ingest_process(readback(payment_status="pending"))
        self.assertEqual(result["result"], "no_grant:pending")
        self.assertEqual(self.store.active_entitlements("T1"), [])
        self.assertEqual(self.tags_applied, [])

    def test_refund_revokes_line_and_unsuppresses_when_all_gone(self):
        self._ingest_process(readback())
        refund = readback(provider_event_id="evt-2",
                          native_event_kind="refund",
                          payment_status="refunded")
        status, payload = ingest(self.store, refund, CTX)
        self.assertEqual(status, "accepted")
        out = self.proc.process(payload["event"],
                                contact_ref="contact-1")
        self.assertEqual(out["result"], "refund_applied")
        self.assertEqual(self.store.active_entitlements("T1"), [])
        # suppression follows ACTIVE entitlement state: fully refunded
        # buyer is no longer suppressed, with no unsuppress job involved
        self.assertFalse(self.proc.is_suppressed("T1", "LN1", "contact-1"))

    def test_partial_refund_keeps_other_line_and_suppression(self):
        self._ingest_process(readback())
        refund = readback(provider_event_id="evt-3",
                          native_event_kind="refund",
                          payment_status="partially_refunded",
                          line_items=[readback()["line_items"][1]])
        _, payload = ingest(self.store, refund, CTX)
        self.proc.process(payload["event"], contact_ref="contact-1")
        self.assertEqual(self.store.active_entitlements("T1"), ["ent-main"])
        self.assertTrue(self.proc.is_suppressed("T1", "LN1", "contact-1"))

    def test_fulfillment_parks_on_unknown_outcome(self):
        self._ingest_process(readback())
        key = ("T1", "txn-1", "li-m", "initiate_fulfillment", "v1")
        action = self.store.get_action(key)
        self.assertEqual(action["state"], "claimed")

        def boom(payload):
            raise RuntimeError("send result unknown")

        self.assertEqual(self.proc.fulfill(key, boom), "parked_unknown")
        self.assertEqual(self.store.get_action(key)["state"], "unknown")
        # a parked action is never silently retried by fulfill
        self.assertEqual(self.proc.fulfill(key, lambda p: None),
                         "parked_unknown")
        # explicit reconciliation (operator marks after native check)
        self.store.mark_action(key, "done",
                               evidence_ref="native/export-verified")
        self.assertEqual(self.proc.fulfill(key, lambda p: None),
                         "already_done")

    def test_tag_applier_failure_parks_never_claims_success(self):
        def bad_applier(contact, tag):
            raise RuntimeError("timeout after write")

        proc = DurableProcessor(self.store, tag_applier=bad_applier,
                                purchase_tag="siglaunch:purchased:main")
        status, payload = ingest(self.store, readback(), CTX)
        proc.process(payload["event"], contact_ref="contact-1")
        tkey = ("T1", "txn-1", "*", "apply_verified_purchase_tag", "v1")
        self.assertEqual(self.store.get_action(tkey)["state"], "unknown")
        self.assertEqual(len(self.store.unknown_actions("T1")), 1)


if __name__ == "__main__":
    unittest.main()
