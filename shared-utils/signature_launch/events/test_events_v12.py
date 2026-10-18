"""Schema v1.2 acceptance tests (CR-S44-003, consumers-accept-first).

v1.2 landed by PR #2190 in train #2235 (main 9ccd6536): the only
change from v1.1 is the OPTIONAL nullable parent_order_ref, placed
immediately after contact_ref — populated only from a real provider
read-back, never synthesized, never load-bearing.

This step is ACCEPTANCE ONLY: validate_event and the processor
accept the "1.2" stamp and honor its rules; normalize_order_event
does NOT stamp "1.2" and does not carry the field (producer
stamping is the later CR-S44-003 step, pinned here so it cannot
arrive silently). The original 17 L1 tests (test_events.py) and
the dual-version tests (test_events_dual.py) run unchanged as the
1.0/1.1 regression proof.
"""
import copy
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import events as ev_mod
from events import (PurchaseProcessor, normalize_order_event,
                    validate_event)

BINDINGS = {"prod-main": "main", "prod-bump": "bump"}
BASE = {"tenant_id": "T1", "location_id": "L1", "launch_id": "LN1",
        "provider": "ghl", "native_order_ref": "ord-1",
        "native_transaction_ref": "txn-1",
        "occurred_at": "2026-10-15T20:00:00Z",
        "received_at": "2026-10-15T20:00:01Z",
        "evidence_ref": "fixture/readback-1", "test_only": True}

# S49's C9 landing note: the merged v1.2 schema bytes on main.
LANDED_V12_SHA256 = \
    "4f9e8122b2767d098ab980be9f33e4503bb1f9e3cc4f4bda17a3990e325378c0"


def line(ref, line_ref, ents):
    return {"native_product_ref": ref, "native_line_ref": line_ref,
            "offer_id": "off-" + line_ref, "currency": "USD",
            "amount_minor": 1000, "entitlement_ids": ents}


def raw(event_id, items, status="succeeded", **kw):
    r = dict(BASE, provider_event_id=event_id, line_items=items,
             payment_status=status)
    r.update(kw)
    return r


def v12_event(parent_order_ref="ord-0", **overrides):
    ev = normalize_order_event(
        raw("e1", [line("prod-main", "li-m", ["ent-main"])]), BINDINGS)
    ev["schema_version"] = "1.2"
    if parent_order_ref is not _ABSENT:
        ev["parent_order_ref"] = parent_order_ref
    ev.update(overrides)
    return ev


class _Absent:
    pass


_ABSENT = _Absent()


class VendoredSchemaTests(unittest.TestCase):
    def test_v12_registered_from_the_vendored_copy(self):
        self.assertIn("1.2", ev_mod.SUPPORTED_SCHEMA_VERSIONS)
        self.assertTrue(ev_mod.SCHEMA_SOURCES["1.2"].endswith(
            "purchase-event.v1.2.schema.json"))

    def test_vendored_v12_bytes_are_the_landed_bytes(self):
        path = Path(ev_mod.SCHEMA_SOURCES["1.2"])
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(digest, LANDED_V12_SHA256)


class V12AcceptanceTests(unittest.TestCase):
    def test_v12_with_parent_order_ref_string_passes(self):
        ev = v12_event()
        self.assertIs(validate_event(ev), ev)

    def test_v12_with_parent_order_ref_null_passes(self):
        ev = v12_event(parent_order_ref=None)
        self.assertIs(validate_event(ev), ev)

    def test_v12_without_parent_order_ref_passes(self):
        ev = v12_event(parent_order_ref=_ABSENT)
        self.assertNotIn("parent_order_ref", ev)
        self.assertIs(validate_event(ev), ev)

    def test_v12_with_contact_ref_and_parent_order_ref_passes(self):
        ev = v12_event(contact_ref="ghl-contact-abc123")
        self.assertIs(validate_event(ev), ev)

    def test_v12_contact_ref_rules_still_enforced(self):
        ev = v12_event(contact_ref="")
        with self.assertRaises(Exception):
            validate_event(ev)

    def test_v12_unknown_extra_field_fails(self):
        ev = v12_event()
        ev["parent_order_id"] = "ord-0"  # near-miss name: not a field
        with self.assertRaises(Exception):
            validate_event(ev)


class ParentOrderRefTypeTests(unittest.TestCase):
    def test_parent_order_ref_must_be_string_or_null(self):
        for bad in (123, 12.5, True, ["ord-0"], {"id": "ord-0"}):
            ev = v12_event(parent_order_ref=bad)
            with self.assertRaises(Exception,
                                   msg=f"parent_order_ref={bad!r}"):
                validate_event(ev)

    def test_parent_order_ref_empty_string_fails(self):
        # the landed v1.2 schema carries minLength 1 on the field
        ev = v12_event(parent_order_ref="")
        with self.assertRaises(Exception):
            validate_event(ev)


class FieldIsVersionScopedTests(unittest.TestCase):
    def test_v11_event_carrying_parent_order_ref_fails(self):
        ev = v12_event()
        ev["schema_version"] = "1.1"
        with self.assertRaises(Exception):
            validate_event(ev)

    def test_v10_event_carrying_parent_order_ref_fails(self):
        ev = v12_event()
        ev["schema_version"] = "1.0"
        with self.assertRaises(Exception):
            validate_event(ev)


class ProcessorV12Tests(unittest.TestCase):
    def test_v12_event_processes_and_grants(self):
        p = PurchaseProcessor()
        out = p.process(v12_event())
        self.assertEqual(out["result"], "processed")
        self.assertEqual(p.book.active("T1"), ["ent-main"])

    def test_parent_order_ref_is_never_load_bearing_for_dedupe(self):
        # same verified event identity, different parent_order_ref:
        # still the same event. Dedupe keys on event identity alone.
        p = PurchaseProcessor()
        p.process(v12_event(parent_order_ref="ord-0"))
        again = p.process(v12_event(parent_order_ref="ord-OTHER"))
        self.assertEqual(again["result"], "duplicate_event")
        self.assertEqual(p.book.active("T1"), ["ent-main"])

    def test_v12_duplicate_and_refund_semantics_hold(self):
        p = PurchaseProcessor()
        ev = v12_event()
        p.process(ev)
        again = p.process(copy.deepcopy(ev))
        self.assertEqual(again["result"], "duplicate_event")
        rf = v12_event()
        rf.update(event_id="e7", event_type="refund_observed",
                  payment_status="refunded")
        out = p.process(rf)
        self.assertEqual(out["result"], "refund_applied")
        self.assertEqual(p.book.active("T1"), [])

    def test_v12_envelope_contact_ref_registers_buyer(self):
        p = PurchaseProcessor()
        p.process(v12_event(contact_ref="ghl-contact-abc123"))
        self.assertTrue(p.is_suppressed("T1", "LN1",
                                        "ghl-contact-abc123"))

    def test_v12_pending_never_grants(self):
        p = PurchaseProcessor()
        ev = v12_event()
        ev["payment_status"] = "pending"
        out = p.process(ev)
        self.assertEqual(out["result"], "no_grant:pending")
        self.assertEqual(p.book.active("T1"), [])


class StampingDisciplineTests(unittest.TestCase):
    """Acceptance only: the producer side must not stamp 1.2 yet."""

    def test_readback_with_parent_order_ref_stamps_10_uncarried(self):
        ev = normalize_order_event(
            raw("e1", [line("prod-main", "li-m", ["ent-main"])],
                parent_order_ref="ord-0"), BINDINGS)
        self.assertEqual(ev["schema_version"], "1.0")
        self.assertNotIn("parent_order_ref", ev)

    def test_readback_with_both_refs_stamps_11_parent_uncarried(self):
        ev = normalize_order_event(
            raw("e1", [line("prod-main", "li-m", ["ent-main"])],
                contact_ref="ghl-contact-abc123",
                parent_order_ref="ord-0"), BINDINGS)
        self.assertEqual(ev["schema_version"], "1.1")
        self.assertEqual(ev["contact_ref"], "ghl-contact-abc123")
        self.assertNotIn("parent_order_ref", ev)


if __name__ == "__main__":
    unittest.main()
