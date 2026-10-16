"""Regression tests for observation O-01 (event provenance cross-check).

O-01 (first independent review, review-s82-01-03.md): the resolver
copied provenance event_ids from the snapshot's top-level ``event_ids``
manifest without ever cross-checking that list against the line items'
own event_id values, and the validator trusted the same manifest. A
snapshot whose manifest disagreed with its lines produced a view whose
provenance over- or under-claimed events.

Real data shape (verified against tests/test_thank_you.make_snapshot
and fixtures/test-only-snapshot.json): every line item carries its own
distinct event_id (TEST-EVT-NNN, one per line) and the top-level
``event_ids`` manifest is exactly the list of those line event_ids, in
line order. The fix therefore requires, after duplicate-delivery
deduplication:

- the manifest set == the deduplicated line event_id set;
- no two distinct lines sharing one event_id;
- the view's copied provenance event_ids == the verified line set.

Preserved behavior: an identical redelivery of the same event (same
native_line_ref, identical content) collapses in deduplication BEFORE
the cross-check, so it still dedupes; a conflicting redelivery still
raises duplicate_conflict (covered by tests/test_thank_you.py).

All data is TEST ONLY. Stdlib unittest only.
"""

import copy
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from thank_you_resolver import ResolverError, resolve_order_view  # noqa: E402
from validate_thank_you import validate_thank_you  # noqa: E402
from test_thank_you import IDENTITY, make_fulfillment, make_snapshot  # noqa: E402


def _honest_view(snapshot):
    return resolve_order_view(snapshot, make_fulfillment(snapshot),
                              expected_identity=IDENTITY)


class EventProvenanceTest(unittest.TestCase):
    def test_honest_snapshot_still_resolves(self):
        # Baseline: the unmodified builder shape passes the cross-check
        # in both the resolver and the validator, and the view's
        # provenance mirrors exactly the line event_ids.
        snapshot = make_snapshot(["MAIN-A", "BUMP", "U1"])
        view = _honest_view(snapshot)
        self.assertEqual(view["provenance"]["event_ids"],
                         snapshot["event_ids"])
        self.assertEqual(view["provenance"]["event_ids"],
                         [line["event_id"] for line in snapshot["line_items"]])
        self.assertEqual(
            validate_thank_you(view, snapshot, make_fulfillment(snapshot)), [])

    def test_manifest_with_extra_id_rejected(self):
        # Manifest claims an event no line carries (over-claim).
        snapshot = make_snapshot(["MAIN-A", "BUMP"])
        view = _honest_view(copy.deepcopy(snapshot))
        snapshot["event_ids"].append("TEST-EVT-999")
        with self.assertRaises(ResolverError) as ctx:
            resolve_order_view(snapshot, make_fulfillment(snapshot),
                               expected_identity=IDENTITY)
        self.assertIn("event_id_mismatch", str(ctx.exception))
        errors = validate_thank_you(view, snapshot)
        self.assertTrue(any("event_id_mismatch" in e for e in errors), errors)

    def test_manifest_missing_a_line_id_rejected(self):
        # Manifest omits a line's event (under-claim).
        snapshot = make_snapshot(["MAIN-A", "BUMP"])
        view = _honest_view(copy.deepcopy(snapshot))
        dropped = snapshot["event_ids"].pop()  # BUMP's event_id
        self.assertEqual(dropped, snapshot["line_items"][1]["event_id"])
        with self.assertRaises(ResolverError) as ctx:
            resolve_order_view(snapshot, make_fulfillment(snapshot),
                               expected_identity=IDENTITY)
        self.assertIn("event_id_mismatch", str(ctx.exception))
        errors = validate_thank_you(view, snapshot)
        self.assertTrue(any("event_id_mismatch" in e for e in errors), errors)

    def test_two_lines_sharing_one_event_id_rejected(self):
        # Two DISTINCT lines (different native_line_ref) carrying the
        # same event_id. The manifest is edited to carry the same
        # (duplicated) id, so the only anomaly is the sharing itself.
        snapshot = make_snapshot(["MAIN-A", "BUMP"])
        view = _honest_view(copy.deepcopy(snapshot))
        shared = snapshot["line_items"][0]["event_id"]
        snapshot["line_items"][1]["event_id"] = shared
        snapshot["event_ids"] = [shared, shared]
        with self.assertRaises(ResolverError) as ctx:
            resolve_order_view(snapshot, make_fulfillment(snapshot),
                               expected_identity=IDENTITY)
        self.assertIn("event_id_mismatch", str(ctx.exception))
        self.assertIn("share", str(ctx.exception))
        errors = validate_thank_you(view, snapshot)
        self.assertTrue(any("event_id_mismatch" in e for e in errors), errors)

    def test_view_provenance_event_ids_tampered_rejected(self):
        # Snapshot stays honest; the VIEW's copied provenance list
        # over-claims an event the verified lines never carried.
        snapshot = make_snapshot(["MAIN-A"])
        view = _honest_view(snapshot)
        tampered = copy.deepcopy(view)
        tampered["provenance"]["event_ids"].append("TEST-EVT-999")
        errors = validate_thank_you(tampered, snapshot)
        self.assertTrue(any("event_id_mismatch" in e for e in errors), errors)

    def test_identical_duplicate_still_dedupes(self):
        # Same event redelivered identically (same native_line_ref,
        # identical content): dedup happens before the cross-check, so
        # this resolves cleanly and the purchase is counted once.
        snapshot = make_snapshot(["MAIN-A", "BUMP"])
        snapshot["line_items"].append(copy.deepcopy(snapshot["line_items"][1]))
        view = resolve_order_view(snapshot, make_fulfillment(snapshot),
                                  expected_identity=IDENTITY)
        self.assertEqual([i["offer_id"] for i in view["items"]],
                         ["MAIN-A", "BUMP"])
        self.assertEqual(view["totals"]["paid_total_minor"], 9700 + 2700)
        self.assertEqual(view["provenance"]["event_ids"],
                         snapshot["event_ids"])
        self.assertEqual(
            validate_thank_you(view, snapshot, make_fulfillment(snapshot)), [])


if __name__ == "__main__":
    unittest.main()
