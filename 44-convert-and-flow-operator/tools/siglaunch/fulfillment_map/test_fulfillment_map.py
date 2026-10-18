"""Fulfillment-map producer proofs (CR-S82-002 reply commitment).

States are produced by the REAL pipeline (normalizer ingest ->
DurableProcessor on the durable store), never by hand-crafted rows,
except the two branches the pipeline cannot reach within buyer
scope — payment-pending and not_granted — whose read-model-level
justification is named in evidence-fulfillment-map.md: the processor
registers a buyer line only on the succeeded path (which also
grants), so a non-granting first purchase creates no buyer scope to
attach those states to.

Module-level (L1/L2) proof only; NOT native proof.
"""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "store"))
sys.path.insert(0, str(Path(__file__).parent.parent / "normalizer"))
sys.path.insert(0, str(Path(__file__).parent.parent / "processor"))
from fulfillment_map import (NEXT_ACTIONS, VocabularyError,
                             _check_vocabulary, build_fulfillment_map)
from normalizer import LaunchContext, ingest
from processor import DurableProcessor
from store import Store

CTX = LaunchContext("T1", "LOC1", "LN1",
                    {"prod-main": "main", "prod-bump": "bump"})
SIX = {"access", "download", "manage_purchase", "support",
       "schedule_included_service", "noncommercial_next_step"}


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


def table_counts(db_path):
    conn = sqlite3.connect(db_path)
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
            " AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {t: conn.execute(
            f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
    finally:
        conn.close()


class FulfillmentMapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "s44.db")
        self.store = Store(self.db)
        self.proc = DurableProcessor(self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def _buy(self, rb=None):
        status, payload = ingest(self.store, rb or readback(), CTX)
        self.assertEqual(status, "accepted")
        return self.proc.process(
            payload["event"],
            contact_ref=payload["contact_ref_context"])

    def _map(self):
        return build_fulfillment_map(self.store, "T1", "LN1", "contact-1")

    def _fulfill_line(self, line_ref, executor=lambda payload: None):
        key = ("T1", "txn-1", line_ref, "initiate_fulfillment", "v1")
        return self.proc.fulfill(key, executor)

    # ── the four states through the real pipeline ───────────────────
    def test_granted_after_fulfillment_done(self):
        self._buy()
        self.assertEqual(self._fulfill_line("li-m"), "done")
        self.assertEqual(self._fulfill_line("li-b"), "done")
        m = self._map()
        self.assertEqual(m["entitlements"], {
            "ent-main": {"state": "granted", "delivery_url": None,
                         "next_action": "access"},
            "ent-bump": {"state": "granted", "delivery_url": None,
                         "next_action": "access"},
        })
        self.assertEqual(
            m["entitlement_version"],
            self.store.entitlement_version("T1", "LN1", "contact-1"))
        self.assertTrue(m["entitlement_version"].startswith("ev1:"))

    def test_pending_while_fulfillment_claimed(self):
        self._buy()  # granted in the book; fulfillment not yet executed
        m = self._map()
        for ent in ("ent-main", "ent-bump"):
            self.assertEqual(m["entitlements"][ent]["state"], "pending")
            self.assertEqual(m["entitlements"][ent]["next_action"],
                             "noncommercial_next_step")

    def test_pending_support_when_fulfillment_parked_unknown(self):
        self._buy()

        def boom(payload):
            raise RuntimeError("dispatch result unknown")

        self.assertEqual(self._fulfill_line("li-m", boom),
                         "parked_unknown")
        m = self._map()
        self.assertEqual(m["entitlements"]["ent-main"]["state"],
                         "pending")
        self.assertEqual(m["entitlements"]["ent-main"]["next_action"],
                         "support")
        # the untouched line is still plainly in flight
        self.assertEqual(m["entitlements"]["ent-bump"]["next_action"],
                         "noncommercial_next_step")

    def test_revoked_after_full_refund(self):
        self._buy()
        self._fulfill_line("li-m")
        self._fulfill_line("li-b")
        refund = readback(provider_event_id="evt-2",
                          native_event_kind="refund",
                          payment_status="refunded")
        status, payload = ingest(self.store, refund, CTX)
        self.assertEqual(status, "accepted")
        self.proc.process(payload["event"], contact_ref="contact-1")
        m = self._map()
        for ent in ("ent-main", "ent-bump"):
            self.assertEqual(m["entitlements"][ent]["state"], "revoked")
            self.assertEqual(m["entitlements"][ent]["next_action"],
                             "manage_purchase")

    def test_partial_refund_revokes_only_the_extra(self):
        self._buy()
        self._fulfill_line("li-m")
        self._fulfill_line("li-b")
        refund = readback(provider_event_id="evt-3",
                          native_event_kind="refund",
                          payment_status="partially_refunded",
                          line_items=[readback()["line_items"][1]])
        _, payload = ingest(self.store, refund, CTX)
        self.proc.process(payload["event"], contact_ref="contact-1")
        m = self._map()
        self.assertEqual(m["entitlements"]["ent-main"]["state"],
                         "granted")
        self.assertEqual(m["entitlements"]["ent-bump"]["state"],
                         "revoked")

    # ── states the pipeline cannot reach in buyer scope ─────────────
    # Justification (also in the evidence note): DurableProcessor
    # registers buyer lines only on the succeeded path, so a pending
    # or failed purchase never creates buyer scope. These construct
    # the read model's inputs directly in the store (a registered
    # line plus a recorded non-granting event) to pin branch 3.
    def _register_line_with_event(self, payment_status, event_id):
        self.store.add_buyer("T1", "LN1", "contact-1", "li-m")
        _, payload = ingest(self.store, readback(
            provider_event_id=event_id,
            payment_status=payment_status), CTX)
        self.proc.process(payload["event"], contact_ref="contact-1")

    def test_not_granted_from_failed_payment(self):
        self._register_line_with_event("failed", "evt-f1")
        m = self._map()
        # only li-m is in this buyer's registered scope
        self.assertEqual(m["entitlements"]["ent-main"]["state"],
                         "not_granted")
        self.assertEqual(m["entitlements"]["ent-main"]["next_action"],
                         "manage_purchase")
        self.assertNotIn("ent-bump", m["entitlements"])

    def test_pending_from_unsettled_payment(self):
        self._register_line_with_event("pending", "evt-p1")
        m = self._map()
        self.assertEqual(m["entitlements"]["ent-main"]["state"],
                         "pending")
        self.assertEqual(m["entitlements"]["ent-main"]["next_action"],
                         "manage_purchase")

    def test_not_granted_support_from_unknown_payment(self):
        self._register_line_with_event("unknown", "evt-u1")
        m = self._map()
        self.assertEqual(m["entitlements"]["ent-main"]["state"],
                         "not_granted")
        self.assertEqual(m["entitlements"]["ent-main"]["next_action"],
                         "support")

    # ── entitlement_version behaviour through the pipeline ──────────
    def test_version_stable_across_duplicate_delivery(self):
        self._buy()
        v1 = self._map()["entitlement_version"]
        status, _ = ingest(self.store, readback(), CTX)
        self.assertEqual(status, "duplicate")
        self.assertEqual(self._map()["entitlement_version"], v1)

    def test_version_changes_on_revoke_and_returns_on_regrant(self):
        self._buy()
        v_granted = self._map()["entitlement_version"]
        refund = readback(provider_event_id="evt-2",
                          native_event_kind="refund",
                          payment_status="refunded")
        _, payload = ingest(self.store, refund, CTX)
        self.proc.process(payload["event"], contact_ref="contact-1")
        v_revoked = self._map()["entitlement_version"]
        self.assertNotEqual(v_granted, v_revoked)
        # re-purchase the same lines: rows flip back to the granted
        # set, so the version returns to the granted value
        self._buy(readback(provider_event_id="evt-3",
                           native_transaction_ref="txn-2"))
        self.assertEqual(self._map()["entitlement_version"], v_granted)

    # ── producer discipline ─────────────────────────────────────────
    def test_map_emission_never_writes(self):
        self._buy()
        self._fulfill_line("li-m")
        before = table_counts(self.db)
        self._map()
        self._map()
        self.assertEqual(table_counts(self.db), before)

    def test_vocabulary_is_exactly_the_contract_six(self):
        self.assertEqual(set(NEXT_ACTIONS), SIX)

    def test_vocabulary_check_fails_closed(self):
        self.assertEqual(_check_vocabulary("access"), "access")
        with self.assertRaises(VocabularyError):
            _check_vocabulary("buy_now")  # a new-charge action: never
        with self.assertRaises(VocabularyError):
            _check_vocabulary("")

    def test_emitted_actions_stay_in_vocabulary_across_states(self):
        self._buy()
        seen = set()
        seen |= {e["next_action"]
                 for e in self._map()["entitlements"].values()}
        self._fulfill_line("li-m")
        self._fulfill_line("li-b")
        seen |= {e["next_action"]
                 for e in self._map()["entitlements"].values()}
        refund = readback(provider_event_id="evt-2",
                          native_event_kind="refund",
                          payment_status="refunded")
        _, payload = ingest(self.store, refund, CTX)
        self.proc.process(payload["event"], contact_ref="contact-1")
        seen |= {e["next_action"]
                 for e in self._map()["entitlements"].values()}
        self.assertTrue(seen <= SIX)
        self.assertEqual(seen, {"access", "noncommercial_next_step",
                                "manage_purchase"})

    def test_unknown_buyer_gets_empty_map_and_zero_row_version(self):
        m = build_fulfillment_map(self.store, "T1", "LN1", "nobody")
        self.assertEqual(m["entitlements"], {})
        self.assertEqual(
            m["entitlement_version"],
            self.store.entitlement_version("T1", "LN1", "nobody"))

    def test_buyer_isolation(self):
        self._buy()
        other = build_fulfillment_map(self.store, "T1", "LN1",
                                      "contact-2")
        self.assertEqual(other["entitlements"], {})
        self.assertNotEqual(other["entitlement_version"],
                            self._map()["entitlement_version"])


class DeliveryBindingTests(unittest.TestCase):
    """CR-S82-003: the launch record's delivery_bindings (launch
    schema 1.2, keyed by entitlement_id) supply a GRANTED
    entitlement's delivery kind and URL. Every other output is
    byte-identical to the pre-binding producer."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "s44.db")
        self.store = Store(self.db)
        self.proc = DurableProcessor(self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def _buy(self, rb=None):
        status, payload = ingest(self.store, rb or readback(), CTX)
        self.assertEqual(status, "accepted")
        return self.proc.process(
            payload["event"],
            contact_ref=payload["contact_ref_context"])

    def _fulfill_line(self, line_ref):
        key = ("T1", "txn-1", line_ref, "initiate_fulfillment", "v1")
        return self.proc.fulfill(key, lambda payload: None)

    def _granted_map(self, record=None):
        self._buy()
        self._fulfill_line("li-m")
        self._fulfill_line("li-b")
        return self._map(record)

    def _map(self, record=None):
        # read-only: safe to call repeatedly on one built state
        return build_fulfillment_map(self.store, "T1", "LN1",
                                     "contact-1", launch_record=record)

    def _record(self, bindings):
        return {"schema_version": "1.2", "tenant_id": "T1",
                "launch_id": "LN1", "delivery_bindings": bindings}

    def test_bound_granted_emits_bound_kind_and_url(self):
        record = self._record({
            "ent-main": {"delivery_kind": "download",
                         "delivery_url": "https://example.test/main"},
            # an orphan binding (no such entitlement in the map) is
            # never consulted producer-side; R-DB-1 is the launch
            # validator's layer
            "ent-orphan": {"delivery_kind": "download",
                           "delivery_url": "https://example.test/x"},
        })
        m = self._granted_map(record)
        self.assertEqual(m["entitlements"]["ent-main"], {
            "state": "granted",
            "delivery_url": "https://example.test/main",
            "next_action": "download"})
        # ent-bump is unbound in the same map: pre-binding behavior
        self.assertEqual(m["entitlements"]["ent-bump"], {
            "state": "granted", "delivery_url": None,
            "next_action": "access"})
        self.assertNotIn("ent-orphan", m["entitlements"])
        # ev1 is not a binding input: the version is the store's own
        self.assertEqual(
            m["entitlement_version"],
            self.store.entitlement_version("T1", "LN1", "contact-1"))

    def test_unbound_granted_byte_identical(self):
        plain = self._granted_map()
        no_key = self._map({"schema_version": "1.2", "tenant_id": "T1",
                            "launch_id": "LN1"})
        empty = self._map(self._record({}))
        self.assertEqual(plain, no_key)
        self.assertEqual(plain, empty)

    def test_bound_kind_with_null_url(self):
        record = self._record({
            "ent-main": {"delivery_kind": "schedule_included_service",
                         "delivery_url": None}})
        m = self._granted_map(record)
        self.assertEqual(m["entitlements"]["ent-main"], {
            "state": "granted", "delivery_url": None,
            "next_action": "schedule_included_service"})

    def test_bound_but_not_granted_keeps_url_null(self):
        record = self._record({
            "ent-bump": {"delivery_kind": "download",
                         "delivery_url": "https://example.test/bump"}})
        # pending: the bump's fulfillment has not executed
        self._buy()
        self._fulfill_line("li-m")
        m = build_fulfillment_map(self.store, "T1", "LN1",
                                  "contact-1", launch_record=record)
        self.assertEqual(m["entitlements"]["ent-bump"], {
            "state": "pending", "delivery_url": None,
            "next_action": "noncommercial_next_step"})
        # revoked: fulfill, then refund the bump line only
        self._fulfill_line("li-b")
        refund = readback(provider_event_id="evt-3",
                          native_event_kind="refund",
                          payment_status="partially_refunded",
                          line_items=[readback()["line_items"][1]])
        _, payload = ingest(self.store, refund, CTX)
        self.proc.process(payload["event"], contact_ref="contact-1")
        m = build_fulfillment_map(self.store, "T1", "LN1",
                                  "contact-1", launch_record=record)
        self.assertEqual(m["entitlements"]["ent-bump"], {
            "state": "revoked", "delivery_url": None,
            "next_action": "manage_purchase"})

    def test_malformed_binding_fails_closed(self):
        bad_bindings = [
            {"delivery_kind": "buy_now",  # outside the six entirely
             "delivery_url": "https://example.test/x"},
            {"delivery_kind": "support",  # in the six, not a kind
             "delivery_url": "https://example.test/x"},
            {"delivery_kind": "download",  # non-https URL
             "delivery_url": "http://example.test/x"},
            {"delivery_kind": "download",  # non-string URL
             "delivery_url": 42},
            {"delivery_kind": "download"},  # missing delivery_url
            {"delivery_kind": "download",  # unknown extra key
             "delivery_url": "https://example.test/x", "extra": 1},
            "download",  # binding is not an object
        ]
        self._buy()
        self._fulfill_line("li-m")
        self._fulfill_line("li-b")
        for bad in bad_bindings:
            with self.subTest(bad=bad):
                record = self._record({"ent-main": bad})
                with self.assertRaises(VocabularyError):
                    self._map(record)


if __name__ == "__main__":
    unittest.main()
