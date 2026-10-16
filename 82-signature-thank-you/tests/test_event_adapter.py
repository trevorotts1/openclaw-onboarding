"""Tests for the S82-05 offline purchase-event adapter.

The adapter turns normalized purchase events (packet purchase-event
shape) into the verified snapshots the resolver already consumes. The
live half of S82-05 (installed S79/S80/S81 native product mappings +
an S06 native order read) remains a named blocker; everything here is
TEST ONLY fixture data and proves only the offline contract:

(1) main+bump arriving in ONE event stay together and resolve;
(2) a later U1 event under the same native order appends;
(3) an extra event under a DIFFERENT order never merges into the
    first order's snapshot;
(4) the adapter has no email/contact input at all, so two orders from
    "the same buyer" cannot be grouped by email;
(5) identical event redelivery dedupes; conflicting redelivery raises;
(6) a mixed-tenant (or mixed-launch) stream is rejected;
(7) require_live_evidence=True refuses test_only events, and accepts
    a live-shaped (non-test, evidenced) stream;
(8) a merged snapshot passes validate_thank_you and
    validate_entitlements with a matching fulfillment map;
(9) a line's own payment_status (fixture extension) wins over the
    event-level status — a pending extra keeps base access (A20).

Stdlib unittest only.
"""

import copy
import inspect
import json
import os
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from purchase_event_adapter import (  # noqa: E402
    AdapterError,
    build_snapshot,
    build_snapshots,
)
from thank_you_resolver import resolve_order_view  # noqa: E402
from validate_entitlements import validate_entitlements  # noqa: E402
from validate_thank_you import validate_thank_you  # noqa: E402
from test_thank_you import IDENTITY, LAUNCH, OFFERS, make_fulfillment  # noqa: E402

ORDER_1 = "TEST-ORDER-0001"
ORDER_2 = "TEST-ORDER-0002"
JOURNEYS = {ORDER_1: "TEST-JOURNEY-0001", ORDER_2: "TEST-JOURNEY-0002"}


def make_event(event_id, order_ref, offer_ids, payment_status="succeeded",
               line_statuses=None, tenant_id=None, launch_id=None,
               provider="TEST-ONLY", test_only=True,
               evidence_ref="TEST-ONLY event evidence"):
    """Build one normalized purchase event in the packet shape.

    Lines are packet-minimal (no display_name / billing extension) so
    the tests also prove the adapter's catalog fallback; a line only
    gains a payment_status extension when line_statuses names it.
    """
    line_statuses = line_statuses or {}
    line_items = []
    for offer_id in offer_ids:
        offer = OFFERS[offer_id]
        price = offer["prices"][0]
        line = {
            "native_line_ref": f"TEST-LINE-{offer_id}",
            "offer_id": offer_id,
            "slot": offer["slot"],
            "currency": price["currency"],
            "amount_minor": price["amount_minor"],
            "entitlement_ids": list(offer["entitlement_ids"]),
        }
        if offer_id in line_statuses:
            line["payment_status"] = line_statuses[offer_id]
        line_items.append(line)
    return {
        "schema_version": "1.0",
        "tenant_id": tenant_id or IDENTITY["tenant_id"],
        "location_id": IDENTITY["location_id"],
        "launch_id": launch_id or IDENTITY["launch_id"],
        "provider": provider,
        "event_id": event_id,
        "event_type": "purchase_observed",
        "native_order_ref": order_ref,
        "native_transaction_ref": "TEST-TXN-0001",
        "occurred_at": "2026-10-15T12:00:00Z",
        "received_at": "2026-10-15T12:00:01Z",
        "payment_status": payment_status,
        "line_items": line_items,
        "evidence_ref": evidence_ref,
        "test_only": test_only,
    }


def build(events, **overrides):
    kwargs = {"journey_ids": JOURNEYS, "offer_catalog": OFFERS,
              "revision": LAUNCH["revision"]}
    kwargs.update(overrides)
    return build_snapshots(events, **kwargs)


class EventAdapterTest(unittest.TestCase):
    def test_1_main_plus_bump_single_event(self):
        # Main and bump arriving in ONE event stay in one snapshot.
        event = make_event("TEST-EVT-A1", ORDER_1, ["MAIN-A", "BUMP"])
        snapshot = build_snapshot([event], journey_ids=JOURNEYS,
                                  offer_catalog=OFFERS,
                                  revision=LAUNCH["revision"])
        self.assertTrue(snapshot["verified"])
        self.assertTrue(snapshot["test_only"])
        self.assertEqual(snapshot["native_order_ref"], ORDER_1)
        self.assertEqual(snapshot["journey_id"], "TEST-JOURNEY-0001")
        # Provenance manifest == the per-line event IDs (O-01 shape),
        # and the two lines of one event carry distinct line event IDs.
        line_event_ids = [line["event_id"] for line in snapshot["line_items"]]
        self.assertEqual(snapshot["event_ids"], line_event_ids)
        self.assertEqual(len(set(line_event_ids)), 2)

        view = resolve_order_view(snapshot, make_fulfillment(snapshot),
                                  expected_identity=IDENTITY)
        self.assertEqual([i["offer_id"] for i in view["items"]],
                         ["MAIN-A", "BUMP"])
        self.assertEqual(view["totals"]["paid_total_minor"], 9700 + 2700)
        # Catalog fallback supplied the display names.
        self.assertEqual(view["items"][0]["display_name"], "TEST ONLY MAIN-A")

    def test_2_later_u1_event_same_order_merges(self):
        events = [
            make_event("TEST-EVT-B1", ORDER_1, ["MAIN-A", "BUMP"]),
            make_event("TEST-EVT-B2", ORDER_1, ["U1"]),
        ]
        snapshot = build(events)[ORDER_1]
        view = resolve_order_view(snapshot, make_fulfillment(snapshot),
                                  expected_identity=IDENTITY)
        self.assertEqual([i["offer_id"] for i in view["items"]],
                         ["MAIN-A", "BUMP", "U1"])
        self.assertEqual(view["totals"]["paid_total_minor"],
                         9700 + 2700 + 6700)
        access = {b["entitlement_id"] for b in view["access_blocks"]}
        self.assertEqual(access, {"base-a", "workbook", "extra-full"})

    def test_3_extra_under_different_order_not_merged(self):
        events = [
            make_event("TEST-EVT-C1", ORDER_1, ["MAIN-A"]),
            make_event("TEST-EVT-C2", ORDER_2, ["U1"]),
        ]
        snapshots = build(events)
        self.assertEqual(set(snapshots), {ORDER_1, ORDER_2})
        order_1_offers = [line["offer_id"]
                          for line in snapshots[ORDER_1]["line_items"]]
        self.assertEqual(order_1_offers, ["MAIN-A"])  # no U1 leaked in
        order_2_offers = [line["offer_id"]
                          for line in snapshots[ORDER_2]["line_items"]]
        self.assertEqual(order_2_offers, ["U1"])

    def test_4_no_email_input_two_orders_stay_separate(self):
        # The adapter surface has no email/contact parameter at all, so
        # grouping by a shared buyer email is impossible by construction.
        params = set(inspect.signature(build_snapshots).parameters)
        self.assertNotIn("email", params)
        self.assertNotIn("contact", params)
        self.assertNotIn("contact_id", params)
        # Two complete orders (as one buyer might place) stay separate.
        events = [
            make_event("TEST-EVT-D1", ORDER_1, ["MAIN-A", "BUMP"]),
            make_event("TEST-EVT-D2", ORDER_2, ["MAIN-B"]),
        ]
        snapshots = build(events)
        self.assertEqual(
            [line["offer_id"] for line in snapshots[ORDER_1]["line_items"]],
            ["MAIN-A", "BUMP"])
        self.assertEqual(
            [line["offer_id"] for line in snapshots[ORDER_2]["line_items"]],
            ["MAIN-B"])
        for snapshot in snapshots.values():
            view = resolve_order_view(snapshot, make_fulfillment(snapshot),
                                      expected_identity=IDENTITY)
            self.assertEqual(view["order_ref"], snapshot["native_order_ref"])

    def test_5_duplicate_event_deduped_conflict_raises(self):
        event = make_event("TEST-EVT-E1", ORDER_1, ["MAIN-A", "BUMP"])
        snapshot = build([event, copy.deepcopy(event)])[ORDER_1]
        self.assertEqual(len(snapshot["line_items"]), 2)  # not doubled
        view = resolve_order_view(snapshot, make_fulfillment(snapshot),
                                  expected_identity=IDENTITY)
        self.assertEqual(view["totals"]["paid_total_minor"], 9700 + 2700)

        conflicting = make_event("TEST-EVT-E1", ORDER_1, ["MAIN-A", "BUMP"])
        conflicting["line_items"][0]["amount_minor"] = 1
        with self.assertRaises(AdapterError) as ctx:
            build([event, conflicting])
        self.assertIn("conflicting_event_redelivery", str(ctx.exception))

    def test_6_mixed_tenant_stream_rejected(self):
        events = [
            make_event("TEST-EVT-F1", ORDER_1, ["MAIN-A"]),
            make_event("TEST-EVT-F2", ORDER_1, ["BUMP"],
                       tenant_id="OTHER-TENANT"),
        ]
        with self.assertRaises(AdapterError) as ctx:
            build(events)
        self.assertIn("mixed_identity_stream", str(ctx.exception))

        mixed_launch = [
            make_event("TEST-EVT-F3", ORDER_1, ["MAIN-A"]),
            make_event("TEST-EVT-F4", ORDER_1, ["BUMP"],
                       launch_id="OTHER-LAUNCH"),
        ]
        with self.assertRaises(AdapterError) as ctx:
            build(mixed_launch)
        self.assertIn("mixed_identity_stream", str(ctx.exception))

    def test_7_require_live_evidence_refuses_test_events(self):
        test_event = make_event("TEST-EVT-G1", ORDER_1, ["MAIN-A"])
        with self.assertRaises(AdapterError) as ctx:
            build([test_event], require_live_evidence=True)
        self.assertIn("test_evidence_refused", str(ctx.exception))

        # A live-shaped stream (non-test provider, test_only False,
        # evidence present) is accepted in production mode.
        live_event = make_event(
            "LIVE-EVT-0001", ORDER_1, ["MAIN-A"],
            provider="ghl-native", test_only=False,
            evidence_ref="native-order-readback:TEST-ORDER-0001",
        )
        snapshot = build([live_event], require_live_evidence=True)[ORDER_1]
        self.assertTrue(snapshot["verified"])
        self.assertFalse(snapshot["test_only"])

    def test_8_merged_snapshot_passes_both_validators(self):
        events = [
            make_event("TEST-EVT-H1", ORDER_1, ["MAIN-A", "BUMP"]),
            make_event("TEST-EVT-H2", ORDER_1, ["U1"]),
        ]
        snapshot = build(events)[ORDER_1]
        fulfillment = make_fulfillment(snapshot)
        view = resolve_order_view(snapshot, fulfillment,
                                  expected_identity=IDENTITY)
        self.assertEqual(validate_thank_you(view, snapshot, fulfillment), [])
        self.assertEqual(
            validate_entitlements(view, snapshot, fulfillment), [])

    def test_9_line_payment_status_wins_over_event_status(self):
        # Event-level status says succeeded, but the U1 line's own
        # status (fixture extension) says pending: the line wins, U1
        # shows pending, and base access survives (A20).
        event = make_event("TEST-EVT-I1", ORDER_1, ["MAIN-A", "U1"],
                           payment_status="succeeded",
                           line_statuses={"U1": "pending"})
        snapshot = build([event])[ORDER_1]
        view = resolve_order_view(snapshot, make_fulfillment(snapshot),
                                  expected_identity=IDENTITY)
        statuses = {i["offer_id"]: i["display_status"] for i in view["items"]}
        self.assertEqual(statuses, {"MAIN-A": "paid", "U1": "pending"})
        self.assertEqual(view["totals"]["paid_total_minor"], 9700)
        self.assertEqual(view["pending_items"], ["U1"])
        access = {b["entitlement_id"] for b in view["access_blocks"]}
        self.assertEqual(access, {"base-a"})


if __name__ == "__main__":
    unittest.main()
