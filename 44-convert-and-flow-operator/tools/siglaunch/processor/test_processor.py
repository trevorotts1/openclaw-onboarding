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
import hashlib

import jsonschema

from normalizer import LaunchContext, ingest
from processor import (DurableProcessor, SCHEMA_PATH, SCHEMA_SOURCES,
                       SUPPORTED_SCHEMA_VERSIONS, dispatch_marketing,
                       validate_event)
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


def event_12(**overrides):
    """A valid schema 1.2 envelope. Values are drawn from the existing
    readback() corpus; parent_order_ref is OPTIONAL, so it is absent
    unless a test supplies it."""
    ev = {
        "schema_version": "1.2",
        "tenant_id": "T1", "location_id": "LOC1", "launch_id": "LN1",
        "provider": "ghl", "event_id": "evt-12-1",
        "event_type": "purchase_observed",
        "native_order_ref": "ord-1", "native_transaction_ref": "txn-1",
        "occurred_at": "2026-10-15T20:00:00Z",
        "received_at": "2026-10-15T20:00:05Z",
        "payment_status": "succeeded",
        "line_items": [
            {"native_line_ref": "li-m", "offer_id": "off-main",
             "slot": "main", "currency": "USD", "amount_minor": 49700,
             "entitlement_ids": ["ent-main"]},
            {"native_line_ref": "li-b", "offer_id": "off-bump",
             "slot": "bump", "currency": "USD", "amount_minor": 3700,
             "entitlement_ids": ["ent-bump"]},
        ],
        "evidence_ref": "readback/ord-1", "test_only": True,
    }
    ev.update(overrides)
    return ev


class SchemaV12AcceptanceTests(unittest.TestCase):
    """CR-S44-003 consumer-side acceptance: the processor accepts the
    stamped 1.2 envelope. Nothing here stamps 1.2."""

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

    def test_registry_holds_1_0_1_1_1_2_and_older_copies_unchanged(self):
        self.assertEqual(SUPPORTED_SCHEMA_VERSIONS, ("1.0", "1.1", "1.2"))
        # back-compat surface still names the v1.0 file
        self.assertEqual(SCHEMA_PATH.name, "purchase-event.schema.json")
        digests = {v: hashlib.sha256(Path(p).read_bytes()).hexdigest()
                   for v, p in SCHEMA_SOURCES.items()}
        self.assertEqual(
            digests["1.0"],
            "c346bbb539927dc109189fb6454bea0fe495eb52f668a632d01c6fc9e779fd20")
        self.assertEqual(
            digests["1.1"],
            "311d04820360193a892929e6cf12788372db85977caf1e1277a8f3024515806a")
        self.assertEqual(
            digests["1.2"],
            "4f9e8122b2767d098ab980be9f33e4503bb1f9e3cc4f4bda17a3990e325378c0")

    def test_valid_1_2_event_processes_and_grants(self):
        result = self.proc.process(event_12(), contact_ref="contact-1")
        self.assertEqual(result["result"], "processed")
        self.assertEqual(self.store.active_entitlements("T1"),
                         ["ent-bump", "ent-main"])
        self.assertEqual(self.tags_applied,
                         [("contact-1", "siglaunch:purchased:main")])
        self.assertTrue(self.proc.is_suppressed("T1", "LN1", "contact-1"))

    def test_parent_order_ref_absent_null_and_string_all_valid(self):
        self.assertEqual(validate_event(event_12()), event_12())
        self.assertEqual(validate_event(event_12(parent_order_ref=None)),
                         event_12(parent_order_ref=None))
        self.assertEqual(validate_event(event_12(parent_order_ref="ord-0")),
                         event_12(parent_order_ref="ord-0"))
        # and all three process, each on its own store so this proves
        # acceptance, not dedupe
        for i, extra in enumerate(({}, {"parent_order_ref": None},
                                   {"parent_order_ref": "ord-0"})):
            store = Store(str(Path(self.tmp.name) / f"p{i}.db"))
            proc = DurableProcessor(store)
            out = proc.process(event_12(event_id=f"evt-12-{i}",
                                        **extra))
            self.assertEqual(out["result"], "processed")
            self.assertEqual(store.active_entitlements("T1"),
                             ["ent-bump", "ent-main"])

    def test_parent_order_ref_is_never_identity_or_dedupe(self):
        # same transaction, different parent refs: still one grant
        # (identity stays tenant + transaction + line), and the second
        # event adds no action
        first = self.proc.process(event_12(), contact_ref="contact-1")
        self.assertGreater(first["actions_created"], 0)
        second = self.proc.process(event_12(parent_order_ref="ord-0",
                                            event_id="evt-12-2"),
                                   contact_ref="contact-1")
        self.assertEqual(second["actions_created"], 0)
        self.assertEqual(len(self.tags_applied), 1)
        # same parent ref, different transaction: neither grouped nor
        # suppressed by the shared parent
        third = self.proc.process(event_12(parent_order_ref="ord-0",
                                           event_id="evt-12-3",
                                           native_transaction_ref="txn-2"),
                                  contact_ref="contact-1")
        self.assertGreater(third["actions_created"], 0)

    def test_1_2_missing_required_field_still_fails(self):
        ev = event_12()
        del ev["evidence_ref"]
        with self.assertRaises(jsonschema.ValidationError):
            validate_event(ev)
        with self.assertRaises(jsonschema.ValidationError):
            self.proc.process(ev)

    def test_unknown_version_1_3_still_fails_closed(self):
        with self.assertRaises(jsonschema.ValidationError) as caught:
            self.proc.process(event_12(schema_version="1.3"))
        self.assertEqual(
            str(caught.exception),
            "unsupported schema_version '1.3': fail closed "
            "(installed schemas: ['1.0', '1.1', '1.2'])")

    def test_1_2_unknown_extra_property_still_fails(self):
        with self.assertRaises(jsonschema.ValidationError):
            validate_event(event_12(promo_code="FREE"))
        with self.assertRaises(jsonschema.ValidationError):
            self.proc.process(event_12(promo_code="FREE"))

    def test_1_2_refund_still_revokes_and_unsuppresses(self):
        self.proc.process(event_12(), contact_ref="contact-1")
        refund = event_12(event_id="evt-12-r", event_type="refund_observed",
                          payment_status="refunded",
                          native_transaction_ref="txn-1-refund")
        self.assertEqual(self.proc.process(refund)["result"],
                         "refund_applied")
        self.assertEqual(self.store.active_entitlements("T1"), [])
        self.assertFalse(self.proc.is_suppressed("T1", "LN1", "contact-1"))


if __name__ == "__main__":
    unittest.main()
