"""Purchase-event packet acceptance: the reference carries the 1.0, 1.1
and 1.2 schemas side by side and all three resolve. 1.0 keeps its path
and bytes; 1.1 (CR-S44-001, optional contact_ref) and 1.2 (CR-S44-003,
optional parent_order_ref) are byte-identical copies of
shared-utils/signature_launch/domain/purchase-event.v1.1.schema.json and
purchase-event.schema.json respectively. Unknown versions fail closed.

L1 deterministic evidence only: no native GHL/payment behavior.
"""
import hashlib
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
SKILL_ROOT = HERE.parents[1]
sys.path.insert(0, str(SKILL_ROOT / "scripts"))

import jsonschema  # noqa: E402

from purchase_event import (EntitlementGrantor, HandoffError,  # noqa: E402
                            PACKET_EVENT_SCHEMA, PACKET_EVENT_SCHEMA_V11,
                            PACKET_EVENT_SCHEMA_V12,
                            load_packet_event_schema, validate_packet_event)

SHA_10 = "c346bbb539927dc109189fb6454bea0fe495eb52f668a632d01c6fc9e779fd20"
SHA_11 = "311d04820360193a892929e6cf12788372db85977caf1e1277a8f3024515806a"
SHA_12 = "4f9e8122b2767d098ab980be9f33e4503bb1f9e3cc4f4bda17a3990e325378c0"


def event(version="1.2", **overrides):
    ev = {
        "schema_version": version,
        "tenant_id": "TEST-TENANT", "location_id": "TEST-LOCATION",
        "launch_id": "TEST-LAUNCH", "provider": "SYNTHETIC-TEST-ONLY",
        "event_id": "SYNTH-EVT-001", "event_type": "purchase_observed",
        "native_order_ref": "SYNTH-ORDER-0001",
        "native_transaction_ref": "SYNTH-TXN-0002",
        "occurred_at": "2026-10-16T00:00:00Z",
        "received_at": "2026-10-16T00:00:05Z",
        "payment_status": "succeeded",
        "line_items": [{
            "native_line_ref": "SYNTH-LINE-MAIN-A", "offer_id": "MAIN-A",
            "slot": "main", "currency": "USD", "amount_minor": 9700,
            "entitlement_ids": ["base-a"],
        }],
        "evidence_ref": "SYNTHETIC packet schema test",
        "test_only": True,
    }
    ev.update(overrides)
    return ev


class PacketSchemaResolutionTests(unittest.TestCase):
    def test_1_0_path_and_bytes_unchanged(self):
        self.assertEqual(PACKET_EVENT_SCHEMA.name, "purchase-event.schema.json")
        self.assertEqual(hashlib.sha256(
            PACKET_EVENT_SCHEMA.read_bytes()).hexdigest(), SHA_10)
        schema = load_packet_event_schema("1.0")
        self.assertEqual(schema["properties"]["schema_version"]["const"], "1.0")
        self.assertNotIn("parent_order_ref", schema["properties"])

    def test_1_1_resolves_beside_1_0(self):
        self.assertEqual(PACKET_EVENT_SCHEMA_V11.name,
                         "purchase-event.v1.1.schema.json")
        self.assertEqual(PACKET_EVENT_SCHEMA_V11.parent,
                         PACKET_EVENT_SCHEMA.parent)
        self.assertEqual(hashlib.sha256(
            PACKET_EVENT_SCHEMA_V11.read_bytes()).hexdigest(), SHA_11)
        schema = load_packet_event_schema("1.1")
        self.assertEqual(schema["properties"]["schema_version"]["const"], "1.1")
        self.assertIn("contact_ref", schema["properties"])
        self.assertNotIn("parent_order_ref", schema["properties"])

    def test_1_2_resolves_beside_1_0(self):
        self.assertEqual(PACKET_EVENT_SCHEMA_V12.name,
                         "purchase-event.v1.2.schema.json")
        self.assertEqual(PACKET_EVENT_SCHEMA_V12.parent,
                         PACKET_EVENT_SCHEMA.parent)
        self.assertEqual(hashlib.sha256(
            PACKET_EVENT_SCHEMA_V12.read_bytes()).hexdigest(), SHA_12)
        schema = load_packet_event_schema("1.2")
        self.assertEqual(schema["properties"]["schema_version"]["const"], "1.2")
        self.assertIn("parent_order_ref", schema["properties"])
        self.assertNotIn("parent_order_ref", schema["required"])

    def test_unknown_versions_fail_closed(self):
        for bad in ("1.3", "2.0", "", None, 1.2):
            with self.assertRaises(HandoffError) as caught:
                load_packet_event_schema(bad)
            self.assertIn("fail closed", str(caught.exception))
            self.assertIn("['1.0', '1.1', '1.2']", str(caught.exception))

    def test_validate_accepts_all_and_rejects_bad_payloads(self):
        validate_packet_event(event("1.0"))
        # 1.1 is what the normalized 44 producer stamps when the read-back
        # supplies an opaque contact_ref; with or without it, it is valid.
        validate_packet_event(event("1.1"))
        validate_packet_event(event("1.1", contact_ref="SYNTH-CONTACT-0001"))
        validate_packet_event(event("1.2"))
        validate_packet_event(event("1.2", parent_order_ref=None))
        validate_packet_event(event("1.2", parent_order_ref="SYNTH-ORDER-0000"))
        with self.assertRaises(jsonschema.ValidationError):
            validate_packet_event(event("1.2", promo_code="FREE"))
        ev = event("1.2")
        del ev["evidence_ref"]
        with self.assertRaises(jsonschema.ValidationError):
            validate_packet_event(ev)
        with self.assertRaises(HandoffError):
            validate_packet_event(event("1.3"))


class GrantBoundaryV12Tests(unittest.TestCase):
    def test_1_2_event_grants_once_and_parent_ref_is_not_identity(self):
        grantor = EntitlementGrantor()
        self.assertEqual(grantor.apply(event("1.2")), ["base-a"])
        # same event_id: deduped, whatever parent_order_ref says
        self.assertEqual(
            grantor.apply(event("1.2", parent_order_ref="SYNTH-ORDER-0000")),
            [])
        # different event_id, same parent ref: a separate grant, not grouped
        self.assertEqual(
            grantor.apply(event("1.2", event_id="SYNTH-EVT-002",
                                parent_order_ref="SYNTH-ORDER-0000")),
            ["base-a"])
        self.assertEqual(grantor.grant_log, [
            ("TEST-TENANT", "SYNTH-EVT-001", "base-a"),
            ("TEST-TENANT", "SYNTH-EVT-002", "base-a"),
        ])

    def test_grant_policy_unchanged_for_1_2(self):
        grantor = EntitlementGrantor()
        with self.assertRaises(HandoffError):
            grantor.apply(event("1.2", payment_status="pending"))
        with self.assertRaises(HandoffError):
            grantor.apply(event("1.2", event_type="refund_observed"))
        with self.assertRaises(HandoffError):
            grantor.apply(event("1.3"))
        self.assertEqual(grantor.grant_log, [])

    def test_1_0_still_validates_exactly_as_before(self):
        grantor = EntitlementGrantor()
        self.assertEqual(grantor.apply(event("1.0")), ["base-a"])
        # 1.0 schema still forbids the 1.2-only property
        with self.assertRaises(HandoffError):
            grantor.apply(event("1.0", parent_order_ref="SYNTH-ORDER-0000"))


if __name__ == "__main__":
    unittest.main()
