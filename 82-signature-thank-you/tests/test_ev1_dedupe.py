"""Gap I6 regression tests: S44's ev1 entitlement_version must be able
to reach the confirmation_shown dedupe key through the real pipeline.

Before this repair, the contract's joint dedupe rule (references/
s44-fulfillment-continuity.md section 3) could never hold on the page
side: S44 supplies its order-level entitlement version (the ev1 value
of CR-S82-002 item 5) only on the fulfillment-map producer envelope,
the contract map shape had no order-level field, the resolver never
emitted one, and the order-view schema forbade one
(additionalProperties: false). Every schema-valid, resolver-produced
view therefore fell back to the derived fingerprint, and the page-side
key could never equal an ev1-based worker-side key.

These tests pin the repaired behavior end to end
(resolver -> view -> observation) and pin backward compatibility just
as hard: with no version supplied, resolver output on the shipped
fixtures is exactly the shipped fixture view and the observation is
exactly the one built from that fixture view.

All data is TEST ONLY. Stdlib unittest only (jsonschema used when
available, mirroring tests/test_repairs.py).
"""

import copy
import hashlib
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from confirmation_observation import (  # noqa: E402
    build_confirmation_observation,
    dedupe_key_for,
)
from thank_you_resolver import ResolverError, resolve_order_view  # noqa: E402
from validate_thank_you import validate_thank_you  # noqa: E402

# A well-formed ev1 value (CR-S82-002 item 5: "ev1:" + lowercase sha256
# hex of S44's canonical book-state string), TEST ONLY content.
EV1 = "ev1:" + hashlib.sha256(b"TEST ONLY ev1 book state A").hexdigest()
EV1_OTHER = "ev1:" + hashlib.sha256(b"TEST ONLY ev1 book state B").hexdigest()


def _load(name):
    with open(os.path.join(ROOT, "fixtures", name), encoding="utf-8") as fh:
        return json.load(fh)


def _envelope(snapshot, fulfillment_map, version=EV1, **overrides):
    envelope = {
        "tenant_id": snapshot["tenant_id"],
        "launch_id": snapshot["launch_id"],
        "contact_ref": "TEST-CONTACT-0001",
        "entitlement_version": version,
        "entitlements": fulfillment_map,
    }
    envelope.update(overrides)
    return envelope


def _worker_key(snapshot, version):
    """The key the S44 event worker checks (contract section 3 formula,
    computed here independently of the page-side code)."""
    material = "|".join([snapshot["tenant_id"], snapshot["location_id"],
                         snapshot["launch_id"],
                         snapshot["native_order_ref"], version])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class Ev1DedupeTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = _load("test-only-snapshot.json")
        self.fulfillment = _load("test-only-fulfillment.json")
        self.fixture_view = _load("test-only-order-view.json")

    # --- backward compatibility: no version supplied -------------------

    def test_absent_version_view_is_fixture_identical(self):
        view = resolve_order_view(self.snapshot, self.fulfillment)
        self.assertNotIn("entitlement_version", view)
        self.assertEqual(view, self.fixture_view)

    def test_absent_version_observation_unchanged(self):
        view = resolve_order_view(self.snapshot, self.fulfillment)
        record = build_confirmation_observation(view)
        self.assertEqual(record,
                         build_confirmation_observation(self.fixture_view))
        self.assertTrue(
            record["entitlement_version"].startswith("derived-sha256:"))
        self.assertEqual(record["dedupe_key"], dedupe_key_for(
            view["tenant_id"], view["location_id"], view["launch_id"],
            view["order_ref"], record["entitlement_version"]))

    def test_bare_map_is_never_mistaken_for_an_envelope(self):
        # A bare map keyed by entitlement_id (values are entry objects)
        # must resolve exactly as before, even if an entitlement were
        # literally named like an envelope field.
        odd_map = copy.deepcopy(self.fulfillment)
        odd_map["entitlements"] = {
            "state": "granted", "delivery_url": None,
            "next_action": "access",
        }
        view = resolve_order_view(self.snapshot, odd_map)
        self.assertNotIn("entitlement_version", view)
        self.assertEqual(
            [b["entitlement_id"] for b in view["access_blocks"]],
            ["base-a", "workbook", "extra-full"])

    # --- the ev1 value reaches the dedupe key ---------------------------

    def test_envelope_version_reaches_view_and_key(self):
        envelope = _envelope(self.snapshot, self.fulfillment)
        view = resolve_order_view(self.snapshot, envelope)
        self.assertEqual(view["entitlement_version"], EV1)
        without_version = {k: v for k, v in view.items()
                           if k != "entitlement_version"}
        self.assertEqual(without_version, self.fixture_view)
        record = build_confirmation_observation(view)
        self.assertEqual(record["entitlement_version"], EV1)
        self.assertEqual(record["dedupe_key"],
                         _worker_key(self.snapshot, EV1))

    def test_explicit_version_input_reaches_view_and_key(self):
        view = resolve_order_view(self.snapshot, self.fulfillment,
                                  entitlement_version=EV1)
        self.assertEqual(view["entitlement_version"], EV1)
        record = build_confirmation_observation(view)
        self.assertEqual(record["entitlement_version"], EV1)
        self.assertEqual(record["dedupe_key"],
                         _worker_key(self.snapshot, EV1))

    def test_explicit_input_overrides_envelope_version(self):
        envelope = _envelope(self.snapshot, self.fulfillment,
                             version=EV1_OTHER)
        view = resolve_order_view(self.snapshot, envelope,
                                  entitlement_version=EV1)
        self.assertEqual(view["entitlement_version"], EV1)
        record = build_confirmation_observation(view)
        self.assertEqual(record["dedupe_key"],
                         _worker_key(self.snapshot, EV1))

    def test_ev1_key_is_idempotent_and_state_sensitive(self):
        envelope = _envelope(self.snapshot, self.fulfillment)
        first = build_confirmation_observation(
            resolve_order_view(self.snapshot, copy.deepcopy(envelope)))
        refreshed = build_confirmation_observation(
            resolve_order_view(self.snapshot, copy.deepcopy(envelope)))
        self.assertEqual(first, refreshed)
        changed = build_confirmation_observation(resolve_order_view(
            self.snapshot,
            _envelope(self.snapshot, self.fulfillment, version=EV1_OTHER)))
        self.assertNotEqual(first["dedupe_key"], changed["dedupe_key"])

    def test_ev1_view_still_passes_structured_validation(self):
        view = resolve_order_view(
            self.snapshot, _envelope(self.snapshot, self.fulfillment))
        self.assertEqual(
            validate_thank_you(view, self.snapshot, self.fulfillment), [])

    # --- mismatched / forged shapes fail closed --------------------------

    BAD_VERSIONS = (
        "s44-v7",                          # legacy free-form label
        "ev1:xyz",                         # not hex
        "ev1:" + "A" * 64,                 # uppercase hex
        "ev1:" + "0" * 63,                 # too short
        "ev1:" + "0" * 65,                 # too long
        "ev1:" + "g" * 64,                 # non-hex letters
        "derived-sha256:" + "0" * 64,      # the fallback is not an input
        "",                                # empty
        " ev1:" + "0" * 64,                # padded
    )

    def test_malformed_explicit_version_rejected(self):
        for bad in self.BAD_VERSIONS:
            with self.subTest(version=bad):
                with self.assertRaises(ResolverError):
                    resolve_order_view(self.snapshot, self.fulfillment,
                                       entitlement_version=bad)

    def test_non_string_explicit_version_rejected(self):
        with self.assertRaises(ResolverError):
            resolve_order_view(self.snapshot, self.fulfillment,
                               entitlement_version=7)

    def test_malformed_envelope_version_rejected(self):
        for bad in self.BAD_VERSIONS:
            with self.subTest(version=bad):
                envelope = _envelope(self.snapshot, self.fulfillment,
                                     version=bad)
                with self.assertRaises(ResolverError):
                    resolve_order_view(self.snapshot, envelope)

    def test_envelope_for_another_tenant_or_launch_rejected(self):
        for field, value in (("tenant_id", "OTHER-TENANT"),
                             ("launch_id", "OTHER-LAUNCH")):
            with self.subTest(field=field):
                envelope = _envelope(self.snapshot, self.fulfillment,
                                     **{field: value})
                with self.assertRaises(ResolverError):
                    resolve_order_view(self.snapshot, envelope)

    # --- schema agreement -------------------------------------------------

    def test_schema_allows_ev1_and_rejects_forged_shapes(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not available")
        with open(os.path.join(ROOT, "schemas", "order-view.schema.json"),
                  encoding="utf-8") as fh:
            schema = json.load(fh)
        jsonschema.Draft202012Validator.check_schema(schema)
        ev1_view = resolve_order_view(
            self.snapshot, _envelope(self.snapshot, self.fulfillment))
        jsonschema.validate(ev1_view, schema)
        jsonschema.validate(self.fixture_view, schema)
        for bad in self.BAD_VERSIONS:
            with self.subTest(version=bad):
                forged = copy.deepcopy(self.fixture_view)
                forged["entitlement_version"] = bad
                with self.assertRaises(jsonschema.ValidationError):
                    jsonschema.validate(forged, schema)


if __name__ == "__main__":
    unittest.main()
