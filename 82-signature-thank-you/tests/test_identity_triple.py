"""Skill 82 tests — DOC-08: the full identity triple is enforced.

Branch-matrix row DOC-08 (doc 18 section 7): identity validation
covers tenant AND location AND launch before any render. The resolver
enforces the whole triple (its identity loop over IDENTITY_KEYS), but
before this file the shipped tests named only the tenant case
(tests/test_thank_you.py :: NegativeTest.test_wrong_tenant_rejected,
which asserts the `wrong_tenant` tag and is referenced, not
duplicated, here).

The resolver refuses each mismatch distinctly: the error names the
mismatched key, and the tag differs by key — `wrong_tenant` for the
tenant, `wrong_scope` for location and launch. These tests pin the
location and launch refusals, their distinctness from the tenant
tag, the per-key independence of the check, and the control case
where the full triple matches.

All data is TEST ONLY. Stdlib unittest only.
"""

import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SKILL_DIR = TESTS_DIR.parent
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from test_thank_you import IDENTITY, make_fulfillment, make_snapshot  # noqa: E402
from thank_you_resolver import ResolverError, resolve_order_view  # noqa: E402
from validate_thank_you import validate_thank_you  # noqa: E402


def snapshot_with(**overrides):
    snapshot = make_snapshot(["MAIN-A"])
    snapshot.update(overrides)
    return snapshot


class LocationMismatchTest(unittest.TestCase):
    def test_wrong_location_rejected_as_wrong_scope(self):
        snapshot = snapshot_with(location_id="TEST-OTHER-LOCATION")
        with self.assertRaises(ResolverError) as ctx:
            resolve_order_view(snapshot, make_fulfillment(snapshot),
                               expected_identity=IDENTITY)
        message = str(ctx.exception)
        self.assertIn("identity_mismatch", message)
        self.assertIn("location_id", message)
        self.assertIn("wrong_scope", message)
        # Distinct from the tenant refusal (wrong_tenant, covered by
        # test_thank_you.py's test_wrong_tenant_rejected).
        self.assertNotIn("wrong_tenant", message)

    def test_location_checked_even_when_tenant_and_launch_match(self):
        # Per-key independence: two of three keys matching does not
        # excuse the third. IDENTITY is the full expected triple, and
        # only the snapshot's location differs from it.
        snapshot = snapshot_with(location_id="TEST-OTHER-LOCATION")
        self.assertEqual(snapshot["tenant_id"], IDENTITY["tenant_id"])
        self.assertEqual(snapshot["launch_id"], IDENTITY["launch_id"])
        with self.assertRaises(ResolverError):
            resolve_order_view(snapshot, make_fulfillment(snapshot),
                               expected_identity=IDENTITY)


class LaunchMismatchTest(unittest.TestCase):
    def test_wrong_launch_rejected_as_wrong_scope(self):
        snapshot = snapshot_with(launch_id="TEST-OTHER-LAUNCH")
        with self.assertRaises(ResolverError) as ctx:
            resolve_order_view(snapshot, make_fulfillment(snapshot),
                               expected_identity=IDENTITY)
        message = str(ctx.exception)
        self.assertIn("identity_mismatch", message)
        self.assertIn("launch_id", message)
        self.assertIn("wrong_scope", message)
        self.assertNotIn("wrong_tenant", message)

    def test_launch_checked_even_when_tenant_and_location_match(self):
        snapshot = snapshot_with(launch_id="TEST-OTHER-LAUNCH")
        self.assertEqual(snapshot["tenant_id"], IDENTITY["tenant_id"])
        self.assertEqual(snapshot["location_id"], IDENTITY["location_id"])
        with self.assertRaises(ResolverError):
            resolve_order_view(snapshot, make_fulfillment(snapshot),
                               expected_identity=IDENTITY)


class IdentityTripleControlTest(unittest.TestCase):
    def test_full_triple_match_resolves_and_validates(self):
        snapshot = make_snapshot(["MAIN-A"])
        fulfillment = make_fulfillment(snapshot)
        view = resolve_order_view(snapshot, fulfillment,
                                  expected_identity=IDENTITY)
        self.assertEqual(view["tenant_id"], IDENTITY["tenant_id"])
        self.assertEqual(view["location_id"], IDENTITY["location_id"])
        self.assertEqual(view["launch_id"], IDENTITY["launch_id"])
        self.assertEqual(validate_thank_you(view, snapshot, fulfillment), [])

    def test_no_expected_identity_means_no_identity_refusal(self):
        # The triple check is driven by the expected identity the page
        # instance is authorized for; with none supplied the resolver
        # builds from the verified snapshot alone (the snapshot's own
        # required identity fields are still enforced upstream).
        snapshot = snapshot_with(location_id="TEST-OTHER-LOCATION",
                                 launch_id="TEST-OTHER-LAUNCH")
        view = resolve_order_view(snapshot, make_fulfillment(snapshot))
        self.assertEqual(view["location_id"], "TEST-OTHER-LOCATION")
        self.assertEqual(view["launch_id"], "TEST-OTHER-LAUNCH")


if __name__ == "__main__":
    unittest.main()
