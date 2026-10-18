"""Purchase-event schema v1.2 (CR-S44-003) staging tests.

Validates the staged domain schemas in ../shared-utils/signature_launch/domain/:
  - purchase-event.schema.json        (v1.2, current)
  - purchase-event.v1.1.schema.json   (preserved, byte-identical to main's v1.1)
  - purchase-event.v1.0.schema.json   (preserved, byte-identical to main's v1.0)

Fixture values are drawn only from existing test corpora:
  - identity / offers / amounts: packet reference launch-example.json
    (TEST-TENANT, TEST-LOCATION, TEST-LAUNCH, MAIN-A 9700, U1 6700,
    entitlements base-a / extra-full).
  - refs / timestamps / provider: S82 A13 synthetic corpus
    (rooms/S82/work/a13-l3-readiness/fixtures/synthetic/s06-native-order-read.json:
    SYNTH-ORDER-0001, SYNTH-TXN-0001/0002, SYNTHETIC-TEST-ONLY,
    2026-10-16T00:00:00Z / 00:00:05Z). SYNTH-ORDER-0001 is the initial
    order's ref in that corpus, so it is the parent_order_ref value used
    for the later extra-purchase (U1) event.
  - contact_ref literal TEST-CONTACT-0001 is taken verbatim from the
    existing fixture corpora (S82/S44 work trees carry it, alongside
    SYNTH-CONTACT-0001); it is an opaque string, not PII, exactly as the
    v1.1 contract requires.

Run: python3 -m unittest test_purchase_event_1_2 -v   (from this directory)
"""

import copy
import json
import pathlib
import unittest

from jsonschema import Draft202012Validator

HERE = pathlib.Path(__file__).resolve().parent
DOMAIN = HERE.parent / "shared-utils" / "signature_launch" / "domain"


def load_schema(name):
    with open(DOMAIN / name, encoding="utf-8") as f:
        return json.load(f)


SCHEMA_12 = load_schema("purchase-event.schema.json")
SCHEMA_11 = load_schema("purchase-event.v1.1.schema.json")
SCHEMA_10 = load_schema("purchase-event.v1.0.schema.json")

V12 = Draft202012Validator(SCHEMA_12)
V11 = Draft202012Validator(SCHEMA_11)
V10 = Draft202012Validator(SCHEMA_10)


def base_event():
    """One purchase_observed event in exact domain-schema shape (v1.0 core)."""
    return {
        "schema_version": "1.0",
        "tenant_id": "TEST-TENANT",
        "location_id": "TEST-LOCATION",
        "launch_id": "TEST-LAUNCH",
        "provider": "SYNTHETIC-TEST-ONLY",
        "event_id": "SYNTH-EVT-001",
        "event_type": "purchase_observed",
        "native_order_ref": "SYNTH-ORDER-0001",
        "native_transaction_ref": "SYNTH-TXN-0001",
        "occurred_at": "2026-10-16T00:00:00Z",
        "received_at": "2026-10-16T00:00:05Z",
        "payment_status": "succeeded",
        "line_items": [
            {
                "native_line_ref": "SYNTH-LINE-MAIN-A",
                "offer_id": "MAIN-A",
                "slot": "main",
                "currency": "USD",
                "amount_minor": 9700,
                "entitlement_ids": ["base-a"],
            }
        ],
        "evidence_ref": "SYNTHETIC s06 native order read export, event 1",
        "test_only": True,
    }


def extra_event():
    """A later extra-purchase (upsell_1) event: the shape parent_order_ref
    exists for. Its own order/transaction refs differ from the initial
    order's; the initial order's identity is SYNTH-ORDER-0001."""
    ev = base_event()
    ev["event_id"] = "SYNTH-EVT-003"
    ev["native_order_ref"] = "SYNTH-ORDER-0002"
    ev["native_transaction_ref"] = "SYNTH-TXN-0002"
    ev["occurred_at"] = "2026-10-16T00:01:00Z"
    ev["received_at"] = "2026-10-16T00:01:05Z"
    ev["line_items"] = [
        {
            "native_line_ref": "SYNTH-LINE-U1",
            "offer_id": "U1",
            "slot": "upsell_1",
            "currency": "USD",
            "amount_minor": 6700,
            "entitlement_ids": ["extra-full"],
        }
    ]
    ev["evidence_ref"] = "SYNTHETIC s06 native order read export, event 2"
    return ev


def stamped(ev, version):
    ev = copy.deepcopy(ev)
    ev["schema_version"] = version
    return ev


class TestSchemaMetaValidity(unittest.TestCase):
    def test_all_three_schemas_are_valid_2020_12(self):
        for schema in (SCHEMA_12, SCHEMA_11, SCHEMA_10):
            Draft202012Validator.check_schema(schema)

    def test_version_consts(self):
        self.assertEqual(SCHEMA_12["properties"]["schema_version"]["const"], "1.2")
        self.assertEqual(SCHEMA_11["properties"]["schema_version"]["const"], "1.1")
        self.assertEqual(SCHEMA_10["properties"]["schema_version"]["const"], "1.0")

    def test_parent_order_ref_shape_matches_ruling(self):
        prop = SCHEMA_12["properties"]["parent_order_ref"]
        self.assertEqual(prop["type"], ["string", "null"])
        self.assertEqual(prop["minLength"], 1)
        self.assertNotIn("parent_order_ref", SCHEMA_12["required"])

    def test_earlier_schemas_do_not_define_parent_order_ref(self):
        self.assertNotIn("parent_order_ref", SCHEMA_11["properties"])
        self.assertNotIn("parent_order_ref", SCHEMA_10["properties"])
        self.assertNotIn("contact_ref", SCHEMA_10["properties"])
        self.assertIn("contact_ref", SCHEMA_11["properties"])


class TestV12Acceptance(unittest.TestCase):
    def test_v12_without_parent_order_ref_valid(self):
        self.assertTrue(V12.is_valid(stamped(base_event(), "1.2")))

    def test_v12_with_parent_order_ref_valid(self):
        ev = stamped(extra_event(), "1.2")
        ev["parent_order_ref"] = "SYNTH-ORDER-0001"
        self.assertTrue(V12.is_valid(ev))

    def test_v12_with_null_parent_order_ref_valid(self):
        ev = stamped(extra_event(), "1.2")
        ev["parent_order_ref"] = None
        self.assertTrue(V12.is_valid(ev))

    def test_v12_with_contact_ref_and_parent_order_ref_valid(self):
        ev = stamped(extra_event(), "1.2")
        ev["contact_ref"] = "TEST-CONTACT-0001"
        ev["parent_order_ref"] = "SYNTH-ORDER-0001"
        self.assertTrue(V12.is_valid(ev))

    def test_v12_empty_string_parent_order_ref_rejected(self):
        ev = stamped(extra_event(), "1.2")
        ev["parent_order_ref"] = ""
        self.assertFalse(V12.is_valid(ev))

    def test_v12_non_string_parent_order_ref_rejected(self):
        ev = stamped(extra_event(), "1.2")
        ev["parent_order_ref"] = 12345
        self.assertFalse(V12.is_valid(ev))

    def test_v12_unknown_version_stamp_rejected(self):
        self.assertFalse(V12.is_valid(stamped(base_event(), "1.3")))
        self.assertFalse(V12.is_valid(stamped(base_event(), "9.9")))


class TestVersionDiscipline(unittest.TestCase):
    """The field on the wrong stamp fails, as contact_ref does on 1.0."""

    def test_parent_order_ref_on_1_1_stamp_rejected(self):
        ev = stamped(extra_event(), "1.1")
        ev["parent_order_ref"] = "SYNTH-ORDER-0001"
        self.assertFalse(V11.is_valid(ev))

    def test_parent_order_ref_on_1_0_stamp_rejected(self):
        ev = stamped(extra_event(), "1.0")
        ev["parent_order_ref"] = "SYNTH-ORDER-0001"
        self.assertFalse(V10.is_valid(ev))

    def test_contact_ref_on_1_0_stamp_rejected(self):
        ev = stamped(base_event(), "1.0")
        ev["contact_ref"] = "TEST-CONTACT-0001"
        self.assertFalse(V10.is_valid(ev))

    def test_1_2_event_rejected_by_1_1_and_1_0_validators(self):
        ev = stamped(extra_event(), "1.2")
        ev["parent_order_ref"] = "SYNTH-ORDER-0001"
        self.assertFalse(V11.is_valid(ev))
        self.assertFalse(V10.is_valid(ev))

    def test_1_1_event_rejected_by_1_2_validator(self):
        ev = stamped(base_event(), "1.1")
        ev["contact_ref"] = "TEST-CONTACT-0001"
        self.assertFalse(V12.is_valid(ev))

    def test_1_0_event_rejected_by_1_2_validator(self):
        self.assertFalse(V12.is_valid(stamped(base_event(), "1.0")))


class TestPreservedVersionsStillValidate(unittest.TestCase):
    """Existing-corpus-shaped documents validate under their own stamps."""

    def test_v10_document_valid_under_v10(self):
        self.assertTrue(V10.is_valid(stamped(base_event(), "1.0")))

    def test_v10_extra_event_valid_under_v10(self):
        self.assertTrue(V10.is_valid(stamped(extra_event(), "1.0")))

    def test_v11_document_with_contact_ref_valid_under_v11(self):
        ev = stamped(base_event(), "1.1")
        ev["contact_ref"] = "TEST-CONTACT-0001"
        self.assertTrue(V11.is_valid(ev))

    def test_v11_document_without_contact_ref_valid_under_v11(self):
        self.assertTrue(V11.is_valid(stamped(base_event(), "1.1")))

    def test_v11_document_with_null_contact_ref_valid_under_v11(self):
        ev = stamped(base_event(), "1.1")
        ev["contact_ref"] = None
        self.assertTrue(V11.is_valid(ev))


if __name__ == "__main__":
    unittest.main()
