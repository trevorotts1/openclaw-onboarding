"""S82-08 fulfillment-continuity tests.

Covers scripts/confirmation_observation.py: the confirmation_shown
observation is deterministic and idempotent (a page refresh rebuilds
the identical record, so it can never trigger a duplicate onboarding
send), changes when the order changes, and carries no PII fields.
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

PII_KEY_FRAGMENTS = ("email", "name", "card", "cvv", "cvc", "password",
                     "phone", "address", "secret", "token")


def _load(name):
    with open(os.path.join(ROOT, "fixtures", name), encoding="utf-8") as fh:
        return json.load(fh)


def _all_keys(obj):
    keys = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            keys.add(str(key).lower())
            keys |= _all_keys(value)
    elif isinstance(obj, list):
        for value in obj:
            keys |= _all_keys(value)
    return keys


class ConfirmationObservationTests(unittest.TestCase):
    def setUp(self):
        self.view = _load("test-only-order-view.json")

    def test_same_view_same_key_idempotent(self):
        first = build_confirmation_observation(self.view)
        refreshed = build_confirmation_observation(copy.deepcopy(self.view))
        self.assertEqual(first, refreshed)
        self.assertEqual(first["dedupe_key"], refreshed["dedupe_key"])

    def test_key_matches_documented_formula(self):
        record = build_confirmation_observation(self.view)
        expected = dedupe_key_for(
            self.view["tenant_id"], self.view["location_id"],
            self.view["launch_id"], self.view["order_ref"],
            record["entitlement_version"])
        self.assertEqual(record["dedupe_key"], expected)
        manual = hashlib.sha256(
            "|".join([self.view["tenant_id"], self.view["location_id"],
                      self.view["launch_id"], self.view["order_ref"],
                      record["entitlement_version"]]).encode("utf-8")
        ).hexdigest()
        self.assertEqual(record["dedupe_key"], manual)

    def test_different_order_different_key(self):
        other = copy.deepcopy(self.view)
        other["order_ref"] = "TEST-ORDER-0002"
        other["order_number"] = "TEST-ORDER-0002"
        first = build_confirmation_observation(self.view)
        second = build_confirmation_observation(other)
        self.assertNotEqual(first["dedupe_key"], second["dedupe_key"])

    def test_entitlement_change_changes_key(self):
        changed = copy.deepcopy(self.view)
        changed["access_blocks"][0]["fulfillment_state"] = "revoked"
        first = build_confirmation_observation(self.view)
        second = build_confirmation_observation(changed)
        self.assertNotEqual(first["entitlement_version"],
                            second["entitlement_version"])
        self.assertNotEqual(first["dedupe_key"], second["dedupe_key"])

    def test_explicit_entitlement_version_is_used(self):
        view = copy.deepcopy(self.view)
        view["entitlement_version"] = "s44-v7"
        record = build_confirmation_observation(view)
        self.assertEqual(record["entitlement_version"], "s44-v7")
        self.assertEqual(record["dedupe_key"], dedupe_key_for(
            view["tenant_id"], view["location_id"], view["launch_id"],
            view["order_ref"], "s44-v7"))

    def test_record_contains_no_pii_fields(self):
        record = build_confirmation_observation(self.view)
        for key in _all_keys(record):
            for fragment in PII_KEY_FRAGMENTS:
                self.assertNotIn(fragment, key,
                                 f"PII-shaped key {key!r} in record")
        serialized = json.dumps(record).lower()
        self.assertNotIn("@", serialized.replace("example.test", ""))

    def test_record_shape_and_no_send(self):
        record = build_confirmation_observation(self.view)
        self.assertEqual(record["record_type"], "confirmation_shown")
        self.assertEqual(record["observed_via"], "thank_you_page_render")
        self.assertIs(record["emits_send"], False)
        self.assertEqual(record["entitlement_ids"],
                         ["base-a", "extra-full", "workbook"])

    def test_cli_prints_record(self):
        import subprocess
        script = os.path.join(ROOT, "scripts", "confirmation_observation.py")
        view = os.path.join(ROOT, "fixtures", "test-only-order-view.json")
        run = subprocess.run([sys.executable, script, "--view", view],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        record = json.loads(run.stdout)
        self.assertEqual(record["record_type"], "confirmation_shown")
        self.assertEqual(record, build_confirmation_observation(self.view))


if __name__ == "__main__":
    unittest.main()
