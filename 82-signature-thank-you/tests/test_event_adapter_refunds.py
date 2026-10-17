"""Regression tests for finding F-1: refund folding in the adapter.

Before the fix, feeding a purchase event and the later refund_observed
event for the same line to build_snapshots raised
``AdapterError: duplicate_conflict`` — the adapter flattened every
event's lines through the resolver's deduplicate_line_items, which
treats any content change on a native line as a conflicting
redelivery, so a post-refund snapshot could never be assembled from
the event stream (see rooms/S82/work/l4-consumption/EVIDENCE.md F-1;
the L4 harness had to assemble the post-refund snapshot by hand).

These tests pin the fold contract:

(1) purchase -> refund folds: the line takes the refunded status and
    the refund event becomes the line's provenance; the resolved view
    labels it Refunded, excludes it from the paid total, keeps base
    access, and never claims "all set" (resolver repair D-04 shape);
(2) an identical redelivery of the refund event still dedupes;
(3) a refund before its purchase, or for a line never purchased in
    the order, fails closed (refund_unknown_line);
(4) a refund whose line disagrees with the purchase on an immutable
    field fails closed (refund_mismatch) — conflicting content still
    raises, exactly as conflicting redeliveries always have;
(5) a refund over a line that never captured money, and a second
    refund over a fully refunded line, fail closed
    (refund_not_applicable);
(6) partial refunds fold as a status (partially_refunded), and a
    partial refund can later complete to a full refund. The packet
    event shape carries no refunded-amount field, so there is no
    amount-level partial refund to fold; the line keeps its purchase
    amount and the resolver excludes it from the paid total.

TEST ONLY fixture data. Stdlib unittest only.
"""

import copy
import sys
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from purchase_event_adapter import (  # noqa: E402
    AdapterError,
    build_snapshots,
)
from thank_you_resolver import resolve_order_view  # noqa: E402
from validate_entitlements import validate_entitlements  # noqa: E402
from validate_thank_you import validate_thank_you  # noqa: E402
from test_thank_you import IDENTITY, LAUNCH, OFFERS, make_fulfillment  # noqa: E402

ORDER_1 = "TEST-ORDER-0001"
ORDER_2 = "TEST-ORDER-0002"
JOURNEYS = {ORDER_1: "TEST-JOURNEY-0001", ORDER_2: "TEST-JOURNEY-0002"}


def make_event(event_id, order_ref, offer_ids, event_type="purchase_observed",
               payment_status="succeeded", line_statuses=None):
    """One normalized purchase event in the packet shape (TEST ONLY)."""
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
        "tenant_id": IDENTITY["tenant_id"],
        "location_id": IDENTITY["location_id"],
        "launch_id": IDENTITY["launch_id"],
        "provider": "TEST-ONLY",
        "event_id": event_id,
        "event_type": event_type,
        "native_order_ref": order_ref,
        "native_transaction_ref": "TEST-TXN-0001",
        "occurred_at": "2026-10-15T12:00:00Z",
        "received_at": "2026-10-15T12:00:01Z",
        "payment_status": payment_status,
        "line_items": line_items,
        "evidence_ref": "TEST-ONLY event evidence",
        "test_only": True,
    }


def refund_event(event_id, order_ref, offer_ids, payment_status="refunded"):
    return make_event(event_id, order_ref, offer_ids,
                      event_type="refund_observed",
                      payment_status=payment_status)


def build(events):
    return build_snapshots(events, journey_ids=JOURNEYS,
                           offer_catalog=OFFERS,
                           revision=LAUNCH["revision"])


def line_of(snapshot, offer_id):
    return next(line for line in snapshot["line_items"]
                if line["offer_id"] == offer_id)


class RefundFoldTest(unittest.TestCase):
    def test_1_purchase_then_refund_folds_and_resolves(self):
        events = [
            make_event("TEST-EVT-RF1", ORDER_1, ["MAIN-A", "U1"]),
            refund_event("TEST-EVT-RF1:refund:T1", ORDER_1, ["U1"]),
        ]
        snapshot = build(events)[ORDER_1]
        self.assertEqual(len(snapshot["line_items"]), 2)

        main = line_of(snapshot, "MAIN-A")
        self.assertEqual(main["payment_status"], "succeeded")
        self.assertEqual(main["event_id"], "TEST-EVT-RF1::TEST-LINE-MAIN-A")

        extra = line_of(snapshot, "U1")
        self.assertEqual(extra["payment_status"], "refunded")
        # The refund event is the provenance of the line's current state.
        self.assertEqual(extra["event_id"],
                         "TEST-EVT-RF1:refund:T1::TEST-LINE-U1")
        # O-01: the manifest is exactly the per-line event IDs.
        self.assertEqual(snapshot["event_ids"],
                         [line["event_id"] for line in snapshot["line_items"]])
        self.assertTrue(snapshot["verified"])

        fulfillment = make_fulfillment(snapshot)
        view = resolve_order_view(snapshot, fulfillment,
                                  expected_identity=IDENTITY)
        statuses = {i["offer_id"]: i["display_status"] for i in view["items"]}
        self.assertEqual(statuses, {"MAIN-A": "paid", "U1": "refunded"})
        self.assertEqual(view["totals"]["paid_total_minor"], 9700)
        self.assertEqual(view["confirmation"]["status"], "refund_applied")
        self.assertFalse(view["confirmation"]["all_set"])
        access = {b["entitlement_id"] for b in view["access_blocks"]}
        self.assertEqual(access, {"base-a"})  # base access survives (A20)
        self.assertEqual(validate_thank_you(view, snapshot, fulfillment), [])
        self.assertEqual(validate_entitlements(view, snapshot, fulfillment), [])

    def test_2_duplicate_refund_delivery_deduped(self):
        purchase = make_event("TEST-EVT-RF2", ORDER_1, ["MAIN-A", "U1"])
        refund = refund_event("TEST-EVT-RF2:refund:T1", ORDER_1, ["U1"])
        single = build([purchase, refund])
        doubled = build([purchase, refund, copy.deepcopy(refund)])
        self.assertEqual(single, doubled)
        self.assertEqual(
            line_of(doubled[ORDER_1], "U1")["payment_status"], "refunded")

    def test_3_refund_before_purchase_fails_closed(self):
        refund = refund_event("TEST-EVT-RF3:refund:T1", ORDER_1, ["U1"])
        with self.assertRaises(AdapterError) as ctx:
            build([refund])
        self.assertIn("refund_unknown_line", str(ctx.exception))

        purchase = make_event("TEST-EVT-RF3", ORDER_1, ["MAIN-A", "U1"])
        with self.assertRaises(AdapterError) as ctx:
            build([refund, purchase])  # refund precedes its purchase
        self.assertIn("refund_unknown_line", str(ctx.exception))

    def test_4_refund_for_unknown_line_fails_closed(self):
        events = [
            make_event("TEST-EVT-RF4", ORDER_1, ["MAIN-A"]),
            refund_event("TEST-EVT-RF4:refund:T1", ORDER_1, ["U1"]),
        ]
        with self.assertRaises(AdapterError) as ctx:
            build(events)
        self.assertIn("refund_unknown_line", str(ctx.exception))

    def test_5_refund_in_other_order_fails_closed(self):
        # The line was purchased under ORDER_1; a refund event filed
        # under ORDER_2 has no such purchase line in its own order.
        events = [
            make_event("TEST-EVT-RF5", ORDER_1, ["MAIN-A"]),
            refund_event("TEST-EVT-RF5:refund:T1", ORDER_2, ["MAIN-A"]),
        ]
        with self.assertRaises(AdapterError) as ctx:
            build(events)
        self.assertIn("refund_unknown_line", str(ctx.exception))

    def test_6_refund_conflicting_line_content_fails_closed(self):
        purchase = make_event("TEST-EVT-RF6", ORDER_1, ["MAIN-A", "U1"])
        refund = refund_event("TEST-EVT-RF6:refund:T1", ORDER_1, ["U1"])
        refund["line_items"][0]["amount_minor"] = 1  # not the purchase's 6700
        with self.assertRaises(AdapterError) as ctx:
            build([purchase, refund])
        self.assertIn("refund_mismatch", str(ctx.exception))

    def test_7_refund_over_unpaid_line_fails_closed(self):
        purchase = make_event("TEST-EVT-RF7", ORDER_1, ["MAIN-A", "U1"],
                              line_statuses={"U1": "pending"})
        refund = refund_event("TEST-EVT-RF7:refund:T1", ORDER_1, ["U1"])
        with self.assertRaises(AdapterError) as ctx:
            build([purchase, refund])
        self.assertIn("refund_not_applicable", str(ctx.exception))

    def test_8_partial_refund_folds_as_status(self):
        events = [
            make_event("TEST-EVT-RF8", ORDER_1, ["MAIN-A", "U1"]),
            refund_event("TEST-EVT-RF8:refund:T1", ORDER_1, ["U1"],
                         payment_status="partially_refunded"),
        ]
        snapshot = build(events)[ORDER_1]
        extra = line_of(snapshot, "U1")
        self.assertEqual(extra["payment_status"], "partially_refunded")
        # No refunded-amount field exists in the event shape: the line
        # keeps its purchase amount; the resolver still excludes the
        # partially refunded money from the paid total.
        self.assertEqual(extra["amount_minor"], 6700)
        view = resolve_order_view(snapshot, make_fulfillment(snapshot),
                                  expected_identity=IDENTITY)
        self.assertEqual(view["totals"]["paid_total_minor"], 9700)
        self.assertEqual(view["confirmation"]["status"], "partially_refunded")
        self.assertFalse(view["confirmation"]["all_set"])

    def test_9_partial_then_full_refund_folds(self):
        events = [
            make_event("TEST-EVT-RF9", ORDER_1, ["MAIN-A", "U1"]),
            refund_event("TEST-EVT-RF9:refund:T1", ORDER_1, ["U1"],
                         payment_status="partially_refunded"),
            refund_event("TEST-EVT-RF9:refund:T2", ORDER_1, ["U1"]),
        ]
        snapshot = build(events)[ORDER_1]
        extra = line_of(snapshot, "U1")
        self.assertEqual(extra["payment_status"], "refunded")
        self.assertEqual(extra["event_id"],
                         "TEST-EVT-RF9:refund:T2::TEST-LINE-U1")

    def test_10_second_refund_after_full_refund_fails_closed(self):
        events = [
            make_event("TEST-EVT-RF10", ORDER_1, ["MAIN-A", "U1"]),
            refund_event("TEST-EVT-RF10:refund:T1", ORDER_1, ["U1"]),
            refund_event("TEST-EVT-RF10:refund:T2", ORDER_1, ["U1"]),
        ]
        with self.assertRaises(AdapterError) as ctx:
            build(events)
        self.assertIn("refund_not_applicable", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
