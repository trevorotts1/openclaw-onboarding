"""Run-manifest tests (CR-S49-004 Path B, Skill 82 v0.3.0).

S82's reply to CR-S49-004 committed a companion run manifest: per
fulfilled purchase resolution, alongside (never inside, never
altering) the thank-you result document, a manifest carrying the
result-side facts page-result 1.0 needs that the result document
does not — `independent_review` {status, reviewer, verdict,
record_ref}, `native_bindings_ref` {envelope_ref,
entitlement_version}, `provenance` {snapshot_ref, map_ref} — under a
top-level `manifest_version`, the run's identity triple, `test_only`
and `result_ref`. The field names are the commitment to S49; these
tests pin them field-for-field, pin the honesty rules (no review ->
status "none" with null facts; no envelope -> null bindings; never
a fabricated reference or version), and pin that building a
manifest leaves the resolver's output byte-identical in shape.

All data is TEST ONLY. Stdlib unittest only (jsonschema used when
available, mirroring tests/test_ev1_dedupe.py).
"""

import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from run_manifest import (  # noqa: E402
    DEFAULT_RESULT_REF,
    ManifestError,
    build_run_manifest,
    main as run_manifest_main,
)
from thank_you_resolver import resolve_order_view  # noqa: E402

# A well-formed ev1 value (CR-S82-002 item 5), TEST ONLY content.
EV1 = "ev1:" + hashlib.sha256(b"TEST ONLY ev1 book state A").hexdigest()

# The exact committed key sets (CR-S49-004 reply, S82 side).
TOP_LEVEL_KEYS = {
    "manifest_version", "tenant_id", "location_id", "launch_id",
    "test_only", "result_ref", "independent_review",
    "native_bindings_ref", "provenance",
}
REVIEW_KEYS = {"status", "reviewer", "verdict", "record_ref"}
BINDINGS_KEYS = {"envelope_ref", "entitlement_version"}
PROVENANCE_KEYS = {"snapshot_ref", "map_ref"}

RECORDED_REVIEW = {
    "status": "recorded",
    "reviewer": "TEST-REVIEWER",
    "verdict": "verified",
    "record_ref": "TEST-ONLY review record",
}

ENVELOPE_REF = "TEST-ONLY envelope ref"
SNAPSHOT_REF = "TEST-ONLY snapshot ref"
MAP_REF = "TEST-ONLY map ref"


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


class RunManifestTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = _load("test-only-snapshot.json")
        self.fulfillment = _load("test-only-fulfillment.json")
        self.fixture_view = _load("test-only-order-view.json")
        self.view = resolve_order_view(self.snapshot, self.fulfillment)

    # --- emission + committed field names -----------------------------

    def test_normal_run_emits_manifest(self):
        manifest = build_run_manifest(
            self.view, self.snapshot, self.fulfillment,
            envelope_ref=ENVELOPE_REF, snapshot_ref=SNAPSHOT_REF,
            map_ref=MAP_REF)
        self.assertEqual(manifest["manifest_version"], "1.0")
        self.assertEqual(manifest["tenant_id"], "TEST-TENANT")
        self.assertEqual(manifest["location_id"], "TEST-LOCATION")
        self.assertEqual(manifest["launch_id"], "TEST-LAUNCH")
        self.assertIs(manifest["test_only"], True)
        self.assertEqual(manifest["result_ref"], DEFAULT_RESULT_REF)
        self.assertEqual(manifest["provenance"],
                         {"snapshot_ref": SNAPSHOT_REF, "map_ref": MAP_REF})

    def test_field_names_match_the_commitment_field_for_field(self):
        manifest = build_run_manifest(
            self.view, self.snapshot, self.fulfillment,
            independent_review=RECORDED_REVIEW)
        self.assertEqual(set(manifest), TOP_LEVEL_KEYS)
        self.assertEqual(set(manifest["independent_review"]), REVIEW_KEYS)
        self.assertEqual(set(manifest["native_bindings_ref"]), BINDINGS_KEYS)
        self.assertEqual(set(manifest["provenance"]), PROVENANCE_KEYS)
        # The manifest is a JSON document: fully serializable, and it
        # never embeds the result document or the order view.
        json.dumps(manifest)
        self.assertNotIn("order_view", manifest)
        self.assertNotIn("validation", manifest)
        self.assertNotIn("errors", manifest)

    # --- independent_review honesty -----------------------------------

    def test_no_review_is_status_none_with_null_facts(self):
        manifest = build_run_manifest(self.view, self.snapshot,
                                      self.fulfillment)
        self.assertEqual(manifest["independent_review"],
                         {"status": "none", "reviewer": None,
                          "verdict": None, "record_ref": None})

    def test_recorded_review_is_carried_verbatim(self):
        manifest = build_run_manifest(
            self.view, self.snapshot, self.fulfillment,
            independent_review=RECORDED_REVIEW)
        self.assertEqual(manifest["independent_review"], RECORDED_REVIEW)

    def test_partial_recorded_review_fails_closed(self):
        partial = {"status": "recorded", "reviewer": "TEST-REVIEWER",
                   "verdict": "verified", "record_ref": None}
        with self.assertRaises(ManifestError):
            build_run_manifest(self.view, independent_review=partial)

    def test_contradictory_review_fails_closed(self):
        contradictory = {"status": "none", "reviewer": "TEST-REVIEWER",
                         "verdict": None, "record_ref": None}
        with self.assertRaises(ManifestError):
            build_run_manifest(self.view, independent_review=contradictory)

    def test_unknown_review_status_fails_closed(self):
        with self.assertRaises(ManifestError):
            build_run_manifest(
                self.view,
                independent_review={"status": "pending",
                                    "reviewer": None, "verdict": None,
                                    "record_ref": None})

    # --- native_bindings_ref honesty -----------------------------------

    def test_envelope_run_binds_the_consumed_ev1_version(self):
        envelope = _envelope(self.snapshot, self.fulfillment)
        view = resolve_order_view(self.snapshot, envelope)
        manifest = build_run_manifest(
            view, self.snapshot, envelope, envelope_ref=ENVELOPE_REF)
        self.assertEqual(manifest["native_bindings_ref"],
                         {"envelope_ref": ENVELOPE_REF,
                          "entitlement_version": EV1})

    def test_version_recovered_from_view_when_envelope_not_repassed(self):
        envelope = _envelope(self.snapshot, self.fulfillment)
        view = resolve_order_view(self.snapshot, envelope)
        manifest = build_run_manifest(view)
        self.assertEqual(
            manifest["native_bindings_ref"]["entitlement_version"], EV1)

    def test_missing_envelope_binds_nothing_and_fabricates_nothing(self):
        manifest = build_run_manifest(self.view, self.snapshot,
                                      self.fulfillment)
        self.assertEqual(manifest["native_bindings_ref"],
                         {"envelope_ref": None, "entitlement_version": None})
        bare = build_run_manifest(self.view)
        self.assertEqual(bare["native_bindings_ref"],
                         {"envelope_ref": None, "entitlement_version": None})
        self.assertEqual(bare["provenance"],
                         {"snapshot_ref": None, "map_ref": None})

    def test_forged_version_on_envelope_fails_closed(self):
        forged = _envelope(self.snapshot, self.fulfillment,
                           version="ev1:not-a-real-hash")
        view = resolve_order_view(self.snapshot, self.fulfillment)
        with self.assertRaises(ManifestError):
            build_run_manifest(view, self.snapshot, forged)

    def test_envelope_for_another_launch_fails_closed(self):
        alien = _envelope(self.snapshot, self.fulfillment,
                          launch_id="OTHER-LAUNCH")
        with self.assertRaises(ManifestError):
            build_run_manifest(self.view, self.snapshot, alien)

    def test_snapshot_for_another_tenant_fails_closed(self):
        alien = copy.deepcopy(self.snapshot)
        alien["tenant_id"] = "OTHER-TENANT"
        with self.assertRaises(ManifestError):
            build_run_manifest(self.view, alien, self.fulfillment)

    # --- the result document is untouched ------------------------------

    def test_resolver_output_shape_is_unchanged_by_the_addition(self):
        # Backward-compat pin, same as the shipped fixtures pin: with
        # no version supplied the resolved view is exactly the
        # shipped fixture view.
        self.assertEqual(self.view, self.fixture_view)

    def test_building_a_manifest_never_mutates_the_view(self):
        before = copy.deepcopy(self.view)
        manifest = build_run_manifest(
            self.view, self.snapshot, self.fulfillment,
            independent_review=RECORDED_REVIEW,
            envelope_ref=ENVELOPE_REF, snapshot_ref=SNAPSHOT_REF,
            map_ref=MAP_REF)
        self.assertEqual(self.view, before)
        # Mutating the manifest cannot reach back into the view.
        manifest["independent_review"]["reviewer"] = "CHANGED"
        manifest["native_bindings_ref"]["envelope_ref"] = "CHANGED"
        self.assertEqual(self.view, before)

    def test_forbidden_credential_field_is_rejected(self):
        poisoned = copy.deepcopy(self.snapshot)
        poisoned["card_number"] = "TEST-ONLY-NOT-A-REAL-CARD"
        with self.assertRaises(ManifestError):
            build_run_manifest(self.view, poisoned, self.fulfillment)

    # --- schema --------------------------------------------------------

    def test_manifest_validates_against_the_schema(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("jsonschema not available")
        with open(os.path.join(ROOT, "schemas",
                               "run-manifest.schema.json"),
                  encoding="utf-8") as fh:
            schema = json.load(fh)
        jsonschema.Draft202012Validator.check_schema(schema)
        none_case = build_run_manifest(self.view, self.snapshot,
                                       self.fulfillment)
        jsonschema.validate(none_case, schema)
        recorded_case = build_run_manifest(
            self.view, self.snapshot,
            _envelope(self.snapshot, self.fulfillment),
            independent_review=RECORDED_REVIEW,
            envelope_ref=ENVELOPE_REF, snapshot_ref=SNAPSHOT_REF,
            map_ref=MAP_REF)
        jsonschema.validate(recorded_case, schema)
        with self.assertRaises(jsonschema.ValidationError):
            extra = copy.deepcopy(recorded_case)
            extra["page_id"] = "S49-fact-not-ours"
            jsonschema.validate(extra, schema)
        with self.assertRaises(jsonschema.ValidationError):
            half = copy.deepcopy(recorded_case)
            half["independent_review"]["record_ref"] = None
            jsonschema.validate(half, schema)
        with self.assertRaises(jsonschema.ValidationError):
            ghost = copy.deepcopy(none_case)
            ghost["independent_review"]["reviewer"] = "GHOST"
            jsonschema.validate(ghost, schema)

    # --- CLI ------------------------------------------------------------

    def test_cli_emits_the_manifest_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            def _write(name, doc):
                path = os.path.join(tmp, name)
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(doc, fh)
                return path
            out_path = os.path.join(tmp, "run-manifest.json")
            rc = run_manifest_main([
                "--view", _write("view.json", self.view),
                "--snapshot", _write("snapshot.json", self.snapshot),
                "--fulfillment", _write("fulfillment.json",
                                        self.fulfillment),
                "--snapshot-ref", SNAPSHOT_REF,
                "--map-ref", MAP_REF,
                "--out", out_path,
            ])
            self.assertEqual(rc, 0)
            with open(out_path, encoding="utf-8") as fh:
                manifest = json.load(fh)
        self.assertEqual(set(manifest), TOP_LEVEL_KEYS)
        self.assertEqual(manifest["provenance"]["snapshot_ref"],
                         SNAPSHOT_REF)
        self.assertEqual(manifest["independent_review"]["status"], "none")


if __name__ == "__main__":
    unittest.main()
