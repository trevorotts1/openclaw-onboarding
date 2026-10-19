"""S44-04 production normalizer proofs (DESIGN-S44-04-v1.md)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "store"))
sys.path.insert(0, str(Path(__file__).parent.parent / "processor"))
from normalizer import LaunchContext, ingest, normalize
from processor import validate_event as validate_processed_event
from store import Store

_HERE = Path(__file__).parent
V11 = json.loads((_HERE / "purchase-event.v1.1.schema.json").read_text())
V12 = json.loads((_HERE / "purchase-event.v1.2.schema.json").read_text())

CTX = LaunchContext("T1", "LOC1", "LN1",
                    {"prod-main": "main", "prod-bump": "bump",
                     "prod-u1": "upsell_1", "prod-d1": "downsell_1"})


def readback(**overrides):
    rb = {
        "tenant_id": "T1", "location_id": "LOC1", "launch_id": "LN1",
        "provider": "ghl", "provider_event_id": "evt-1",
        "native_event_kind": "order_paid",
        "native_order_ref": "ord-1", "native_transaction_ref": "txn-1",
        "occurred_at": "2026-10-15T20:00:00Z",
        "received_at": "2026-10-15T20:00:05Z",
        "payment_status": "succeeded",
        "submission_type": "Upsell",  # the lying label: never read
        "line_items": [
            {"native_line_ref": "li-m", "native_product_ref": "prod-main",
             "offer_id": "off-main", "currency": "USD",
             "amount_minor": 49700, "entitlement_ids": ["ent-main"]},
            {"native_line_ref": "li-b", "native_product_ref": "prod-bump",
             "offer_id": "off-bump", "currency": "USD",
             "amount_minor": 3700, "entitlement_ids": ["ent-bump"]},
        ],
        "evidence_ref": "readback/ord-1",
        "test_only": True,
    }
    rb.update(overrides)
    return rb


class NormalizerTests(unittest.TestCase):
    def test_main_plus_bump_line_complete_slots_by_binding(self):
        out = normalize(readback(), CTX)
        ev = out["event"]
        self.assertEqual([l["slot"] for l in ev["line_items"]],
                         ["main", "bump"])
        self.assertEqual(ev["schema_version"], "1.0")
        self.assertNotIn("contact_ref", ev)

    def test_lying_label_never_used_for_slot(self):
        rb = readback(line_items=[
            {"native_line_ref": "li-u", "native_product_ref": "prod-d1",
             "offer_id": "off-d1", "currency": "USD", "amount_minor": 9700,
             "entitlement_ids": ["ent-d1"]}])
        ev = normalize(rb, CTX)["event"]
        self.assertEqual(ev["line_items"][0]["slot"], "downsell_1")

    def test_missing_event_identity_quarantines(self):
        out = normalize(readback(provider_event_id=""), CTX)
        self.assertEqual(out["quarantine"]["reason_code"],
                         "no_verified_event_identity")

    def test_unmapped_product_quarantines_whole_event(self):
        rb = readback()
        rb["line_items"][1]["native_product_ref"] = "prod-UNKNOWN"
        out = normalize(rb, CTX)
        self.assertEqual(out["quarantine"]["reason_code"],
                         "unmapped_native_product")

    def test_tenant_mismatch_quarantines(self):
        out = normalize(readback(location_id="LOC-OTHER"), CTX)
        self.assertEqual(out["quarantine"]["reason_code"],
                         "tenant_mismatch")

    def test_cancellation_quarantines_until_addendum(self):
        out = normalize(readback(native_event_kind="cancellation"), CTX)
        self.assertEqual(out["quarantine"]["reason_code"],
                         "unmapped_event_kind")

    def test_submission_without_transaction_status_is_unknown(self):
        rb = readback()
        del rb["payment_status"]
        ev = normalize(rb, CTX)["event"]
        self.assertEqual(ev["payment_status"], "unknown")

    def test_out_of_enum_status_quarantines_never_coerces(self):
        out = normalize(readback(payment_status="probably_paid"), CTX)
        self.assertEqual(out["quarantine"]["reason_code"], "schema_invalid")

    def test_absent_transaction_ref_stays_null(self):
        rb = readback()
        del rb["native_transaction_ref"]
        ev = normalize(rb, CTX)["event"]
        self.assertIsNone(ev["native_transaction_ref"])

    def test_pii_field_never_enters_envelope(self):
        rb = readback(contact_email="buyer@example.com")
        ev = normalize(rb, CTX)["event"]
        self.assertNotIn("contact_email", ev)
        self.assertNotIn("buyer@example.com", str(ev))

    def test_contact_ref_context_only_without_v11_schema(self):
        rb = readback(contact_ref="native-contact-123")
        out = normalize(rb, CTX)
        self.assertEqual(out["event"]["schema_version"], "1.0")
        self.assertNotIn("contact_ref", out["event"])
        self.assertEqual(out["contact_ref_context"], "native-contact-123")

    def test_parent_order_ref_stamps_1_2_and_carries_contact_ref(self):
        rb = readback(contact_ref="native-contact-123",
                      parent_order_ref="ORDER-INITIAL-1")
        ev = normalize(rb, CTX, schema_v11=V11, schema_v12=V12)["event"]
        self.assertEqual(ev["schema_version"], "1.2")
        self.assertEqual(ev["parent_order_ref"], "ORDER-INITIAL-1")
        self.assertEqual(ev["contact_ref"], "native-contact-123")
        self.assertEqual(ev["event_id"], "evt-1")
        validate_processed_event(ev)  # the production processor accepts it

    def test_parent_order_ref_alone_stamps_1_2(self):
        # contact_ref is optional in 1.2; parent_order_ref alone still
        # justifies the stamp, and only the stamp
        rb = readback(parent_order_ref="ORDER-INITIAL-1")
        ev = normalize(rb, CTX, schema_v12=V12)["event"]
        self.assertEqual(ev["schema_version"], "1.2")
        self.assertEqual(ev["parent_order_ref"], "ORDER-INITIAL-1")
        self.assertNotIn("contact_ref", ev)
        validate_processed_event(ev)

    def test_absent_parent_order_ref_keeps_old_stream_stamps(self):
        out = normalize(readback(), CTX, schema_v11=V11, schema_v12=V12)
        self.assertEqual(out["event"]["schema_version"], "1.0")
        self.assertNotIn("parent_order_ref", out["event"])
        out = normalize(readback(contact_ref="c-1"), CTX,
                        schema_v11=V11, schema_v12=V12)
        self.assertEqual(out["event"]["schema_version"], "1.1")
        self.assertNotIn("parent_order_ref", out["event"])
        self.assertEqual(out["event"]["contact_ref"], "c-1")

    def test_parent_order_ref_never_synthesized(self):
        # empty string is absent; an unconfigured v1.2 drops the field
        # rather than upgrading the stamp
        out = normalize(readback(parent_order_ref=""), CTX,
                        schema_v11=V11, schema_v12=V12)
        self.assertEqual(out["event"]["schema_version"], "1.0")
        self.assertNotIn("parent_order_ref", out["event"])
        out = normalize(readback(contact_ref="c-1",
                                 parent_order_ref="ORDER-INITIAL-1"), CTX,
                        schema_v11=V11)
        self.assertEqual(out["event"]["schema_version"], "1.1")
        self.assertNotIn("parent_order_ref", out["event"])

    def test_ingest_stamps_1_2_and_dedupe_identity_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(str(Path(d) / "s44.db"))
            rb = readback(contact_ref="c-1",
                          parent_order_ref="ORDER-INITIAL-1")
            self.assertEqual(ingest(store, rb, CTX)[0], "accepted")
            self.assertEqual(ingest(store, rb, CTX)[0], "duplicate")
            stored = store.get_event("T1", "ghl", "evt-1")
            self.assertEqual(stored["schema_version"], "1.2")
            self.assertEqual(stored["parent_order_ref"], "ORDER-INITIAL-1")

    def test_ingest_accept_duplicate_quarantine(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(str(Path(d) / "s44.db"))
            self.assertEqual(ingest(store, readback(), CTX)[0], "accepted")
            self.assertEqual(ingest(store, readback(), CTX)[0], "duplicate")
            status, payload = ingest(
                store, readback(provider_event_id="evt-2",
                                native_event_kind="cancellation"), CTX)
            self.assertEqual(status, "quarantined")
            open_q = store.open_quarantine("T1")
            self.assertEqual(len(open_q), 1)
            self.assertEqual(open_q[0]["reason_code"],
                             "unmapped_event_kind")
            store.resolve_quarantine(payload["quarantine_id"])
            self.assertEqual(store.open_quarantine("T1"), [])


if __name__ == "__main__":
    unittest.main()
