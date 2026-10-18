"""Lane-B dual-version tests for the schema v1.1 switch (CR-S44-001).

Covers: v1.0 unchanged, v1.1 with contact_ref present / null / absent,
contact_ref type enforcement, fail-closed unknown versions, the
normalize_order_event version stamping, processor buyer registration
from a v1.1 envelope, and the domain-sibling schema loading layout.
The original 17 L1 tests live unchanged in test_events.py beside this
file and run against the same dual module as the regression proof.
"""
import copy
import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import events as dual
from events import PurchaseProcessor, normalize_order_event, validate_event

BINDINGS = {"prod-main": "main", "prod-bump": "bump", "prod-u1": "upsell_1"}
BASE = {"tenant_id": "T1", "location_id": "L1", "launch_id": "LN1",
        "provider": "ghl", "native_order_ref": "ord-1",
        "native_transaction_ref": "txn-1",
        "occurred_at": "2026-10-15T20:00:00Z",
        "received_at": "2026-10-15T20:00:01Z",
        "evidence_ref": "fixture/readback-1", "test_only": True}


def line(ref, line_ref, ents):
    return {"native_product_ref": ref, "native_line_ref": line_ref,
            "offer_id": "off-" + line_ref, "currency": "USD",
            "amount_minor": 1000, "entitlement_ids": ents}


def raw(event_id, items, status="succeeded", **kw):
    r = dict(BASE, provider_event_id=event_id, line_items=items,
             payment_status=status)
    r.update(kw)
    return r


def v10_event():
    return normalize_order_event(
        raw("e1", [line("prod-main", "li-m", ["ent-main"])]), BINDINGS)


def v11_event(contact_ref="ghl-contact-abc123"):
    ev = v10_event()
    ev["schema_version"] = "1.1"
    ev["contact_ref"] = contact_ref
    return ev


class SchemaInventoryTests(unittest.TestCase):
    def test_both_schemas_installed_and_sourced_from_lane_copies(self):
        # extended at the v1.2 acceptance step (CR-S44-003): the
        # vendored v1.2 copy registers beside the 1.0/1.1 copies
        self.assertEqual(dual.SUPPORTED_SCHEMA_VERSIONS,
                         ("1.0", "1.1", "1.2"))
        self.assertTrue(dual.SCHEMA_SOURCES["1.0"].endswith(
            "purchase-event.schema.json"))
        self.assertTrue(dual.SCHEMA_SOURCES["1.1"].endswith(
            "purchase-event.v1.1.schema.json"))
        self.assertTrue(dual.SCHEMA_SOURCES["1.2"].endswith(
            "purchase-event.v1.2.schema.json"))


class V10UnchangedTests(unittest.TestCase):
    def test_v10_event_validates(self):
        ev = v10_event()
        self.assertEqual(ev["schema_version"], "1.0")
        self.assertNotIn("contact_ref", ev)
        self.assertIs(validate_event(ev), ev)

    def test_v10_event_with_contact_ref_fails(self):
        # contact_ref is a v1.1 field; a 1.0 stamp carrying it is invalid
        ev = v10_event()
        ev["contact_ref"] = "ghl-contact-abc123"
        with self.assertRaises(Exception):
            validate_event(ev)

    def test_v10_missing_required_field_still_fails(self):
        ev = v10_event()
        del ev["evidence_ref"]
        with self.assertRaises(Exception):
            validate_event(ev)


class V11AcceptanceTests(unittest.TestCase):
    def test_v11_with_contact_ref_string_passes(self):
        ev = v11_event()
        self.assertIs(validate_event(ev), ev)

    def test_v11_with_contact_ref_null_passes(self):
        ev = v11_event(contact_ref=None)
        self.assertIs(validate_event(ev), ev)

    def test_v11_without_contact_ref_passes(self):
        # a 1.1 event missing nothing else still passes: contact_ref is
        # optional, so its absence cannot fail validation
        ev = v11_event()
        del ev["contact_ref"]
        self.assertIs(validate_event(ev), ev)

    def test_v11_missing_other_required_field_fails(self):
        ev = v11_event()
        del ev["tenant_id"]
        with self.assertRaises(Exception):
            validate_event(ev)

    def test_v11_unknown_extra_field_fails(self):
        ev = v11_event()
        ev["contact_email"] = "x@example.com"  # PII-shaped, never allowed
        with self.assertRaises(Exception):
            validate_event(ev)


class ContactRefTypeTests(unittest.TestCase):
    def test_contact_ref_must_be_string_or_null(self):
        for bad in (123, 12.5, True, ["ghl-contact"], {"id": "x"}):
            ev = v11_event(contact_ref=bad)
            with self.assertRaises(Exception, msg=f"contact_ref={bad!r}"):
                validate_event(ev)

    def test_contact_ref_empty_string_fails(self):
        # the landed v1.1 schema carries minLength 1 on contact_ref
        ev = v11_event(contact_ref="")
        with self.assertRaises(Exception):
            validate_event(ev)


class FailClosedVersionTests(unittest.TestCase):
    def test_unknown_versions_fail_closed(self):
        # "1.2" left this list at the v1.2 acceptance step: it is an
        # installed version now (test_events_v12.py pins its rules)
        for bad in ("1.3", "2.0", "0.9", "", "v1.1", "1.10"):
            ev = v11_event()
            ev["schema_version"] = bad
            with self.assertRaises(Exception, msg=f"version={bad!r}"):
                validate_event(ev)

    def test_missing_version_fails_closed(self):
        ev = v11_event()
        del ev["schema_version"]
        with self.assertRaises(Exception):
            validate_event(ev)

    def test_non_string_version_fails_closed(self):
        for bad in (1.1, 1, None, ["1.1"]):
            ev = v11_event()
            ev["schema_version"] = bad
            with self.assertRaises(Exception, msg=f"version={bad!r}"):
                validate_event(ev)

    def test_non_object_event_fails_closed(self):
        for bad in (None, [], "event", 42):
            with self.assertRaises(Exception, msg=f"event={bad!r}"):
                validate_event(bad)


class NormalizeStampingTests(unittest.TestCase):
    def test_readback_without_contact_ref_stamps_10(self):
        ev = normalize_order_event(
            raw("e1", [line("prod-main", "li-m", ["ent-main"])]), BINDINGS)
        self.assertEqual(ev["schema_version"], "1.0")

    def test_readback_with_contact_ref_stamps_11_and_carries_it(self):
        ev = normalize_order_event(
            raw("e1", [line("prod-main", "li-m", ["ent-main"])],
                contact_ref="ghl-contact-abc123"), BINDINGS)
        self.assertEqual(ev["schema_version"], "1.1")
        self.assertEqual(ev["contact_ref"], "ghl-contact-abc123")

    def test_readback_with_null_contact_ref_stamps_11(self):
        ev = normalize_order_event(
            raw("e1", [line("prod-main", "li-m", ["ent-main"])],
                contact_ref=None), BINDINGS)
        self.assertEqual(ev["schema_version"], "1.1")
        self.assertIsNone(ev["contact_ref"])

    def test_readback_with_bad_contact_ref_type_fails(self):
        with self.assertRaises(Exception):
            normalize_order_event(
                raw("e1", [line("prod-main", "li-m", ["ent-main"])],
                    contact_ref=123), BINDINGS)


class ProcessorDualVersionTests(unittest.TestCase):
    def test_v11_event_processes_and_grants(self):
        p = PurchaseProcessor()
        out = p.process(v11_event())
        self.assertEqual(out["result"], "processed")
        self.assertEqual(p.book.active("T1"), ["ent-main"])

    def test_v11_envelope_contact_ref_registers_buyer(self):
        # no out-of-band contact_ref argument: the envelope's own
        # auditable binding registers the buyer for the A21 recheck
        p = PurchaseProcessor()
        p.process(v11_event())
        self.assertTrue(p.is_suppressed("T1", "LN1", "ghl-contact-abc123"))

    def test_v11_null_contact_ref_registers_nobody(self):
        p = PurchaseProcessor()
        out = p.process(v11_event(contact_ref=None))
        self.assertEqual(out["result"], "processed")
        self.assertEqual(p.buyers, set())

    def test_explicit_context_contact_ref_still_wins(self):
        p = PurchaseProcessor()
        p.process(v10_event(), contact_ref="ctx-contact-9")
        self.assertTrue(p.is_suppressed("T1", "LN1", "ctx-contact-9"))

    def test_v11_duplicate_and_refund_semantics_hold(self):
        p = PurchaseProcessor()
        ev = v11_event()
        p.process(ev)
        again = p.process(copy.deepcopy(ev))
        self.assertEqual(again["result"], "duplicate_event")
        rf = v11_event()
        rf.update(event_id="e7", event_type="refund_observed",
                  payment_status="refunded")
        out = p.process(rf)
        self.assertEqual(out["result"], "refund_applied")
        self.assertEqual(p.book.active("T1"), [])

    def test_v11_pending_never_grants(self):
        p = PurchaseProcessor()
        ev = v11_event()
        ev["payment_status"] = "pending"
        out = p.process(ev)
        self.assertEqual(out["result"], "no_grant:pending")
        self.assertEqual(p.book.active("T1"), [])


class DomainSiblingLayoutTests(unittest.TestCase):
    def test_module_loads_both_versions_from_domain_sibling(self):
        # Simulate the repo packaged layout: events/ beside domain/,
        # no vendored schema beside the module, no packet tree. The
        # loader must take the current version from the un-suffixed
        # domain file and each preserved version from its versioned
        # name. Extended at the v1.2 acceptance step: domain/ on main
        # now carries v1.2 un-suffixed, v1.1 and v1.0 versioned.
        lane = Path(__file__).parent
        # work-layout adaptation (Lane B REPORT section 4A.3): the
        # domain source is the vendored domain-src/ copy beside this
        # file, holding the domain files under their domain names
        domain_src = lane / "domain-src"
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "events").mkdir()
            (root / "domain").mkdir()
            shutil.copy(lane / "events.py", root / "events" / "events.py")
            shutil.copy(domain_src / "purchase-event.schema.json",
                        root / "domain" / "purchase-event.schema.json")
            shutil.copy(domain_src / "purchase-event.v1.1.schema.json",
                        root / "domain" / "purchase-event.v1.1.schema.json")
            shutil.copy(domain_src / "purchase-event.v1.0.schema.json",
                        root / "domain" / "purchase-event.v1.0.schema.json")
            spec = importlib.util.spec_from_file_location(
                "events_domain_layout", root / "events" / "events.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self.assertEqual(mod.SUPPORTED_SCHEMA_VERSIONS,
                             ("1.0", "1.1", "1.2"))
            self.assertTrue(mod.SCHEMA_SOURCES["1.2"].endswith(
                "domain/purchase-event.schema.json"))
            self.assertTrue(mod.SCHEMA_SOURCES["1.1"].endswith(
                "domain/purchase-event.v1.1.schema.json"))
            self.assertTrue(mod.SCHEMA_SOURCES["1.0"].endswith(
                "domain/purchase-event.v1.0.schema.json"))
            ev = {"schema_version": "1.1", "tenant_id": "T1",
                  "location_id": "L1", "launch_id": "LN1",
                  "provider": "ghl", "event_id": "e1",
                  "event_type": "purchase_observed",
                  "native_order_ref": "ord-1",
                  "native_transaction_ref": "txn-1",
                  "contact_ref": "ghl-contact-abc123",
                  "occurred_at": "2026-10-15T20:00:00Z",
                  "received_at": "2026-10-15T20:00:01Z",
                  "payment_status": "succeeded",
                  "line_items": [{"native_line_ref": "li-m",
                                  "offer_id": "off-li-m", "slot": "main",
                                  "currency": "USD", "amount_minor": 1000,
                                  "entitlement_ids": ["ent-main"]}],
                  "evidence_ref": "fixture/readback-1", "test_only": True}
            self.assertIs(mod.validate_event(ev), ev)
            ev12 = dict(ev, schema_version="1.2", event_id="e2",
                        parent_order_ref="ord-0")
            self.assertIs(mod.validate_event(ev12), ev12)


class ShallowPathImportTests(unittest.TestCase):
    def test_module_imports_from_a_shallow_path(self):
        # Regression (2026-10-16, found by the S44 watchdog's L1
        # re-run): the packet-fallback candidate used parents[4]
        # unguarded at import time, so a copy of the module at a
        # shallow path (temp dir directly under /tmp, as a default
        # TMPDIR produces) crashed import with IndexError. The module
        # must import cleanly at any depth and load both schemas from
        # the copies vendored beside it.
        here = Path(__file__).parent
        with tempfile.TemporaryDirectory(dir="/tmp") as td:
            root = Path(td)
            shutil.copy(here / "events.py", root / "events.py")
            shutil.copy(here / "purchase-event.schema.json",
                        root / "purchase-event.schema.json")
            shutil.copy(here / "purchase-event.v1.1.schema.json",
                        root / "purchase-event.v1.1.schema.json")
            spec = importlib.util.spec_from_file_location(
                "events_shallow", root / "events.py")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self.assertEqual(mod.SUPPORTED_SCHEMA_VERSIONS, ("1.0", "1.1"))
            ev = v11_event()
            self.assertIs(mod.validate_event(ev), ev)


if __name__ == "__main__":
    unittest.main()
