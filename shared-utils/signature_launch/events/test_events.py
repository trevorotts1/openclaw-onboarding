"""S44 L1 fault-injection tests — doc 14 section 11 / doc 18 A17/A19/A20/A21.

L1 only: deterministic in-memory fixtures. These prove envelope semantics,
never live GHL behavior.
"""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from events import (ActionLedger, PurchaseProcessor, dispatch_marketing,
                    normalize_order_event, validate_event)

BINDINGS = {"prod-main": "main", "prod-bump": "bump", "prod-u1": "upsell_1",
            "prod-d1": "downsell_1", "prod-u2": "upsell_2"}
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


class EventTests(unittest.TestCase):
    def setUp(self):
        self.p = PurchaseProcessor()

    def test_a17_main_plus_bump_one_event_keeps_bump(self):
        ev = normalize_order_event(raw("e1", [line("prod-main", "li-m", ["ent-main"]),
                                              line("prod-bump", "li-b", ["ent-bump"])]), BINDINGS)
        out = self.p.process(ev, contact_ref="c1")
        self.assertEqual(out["result"], "processed")
        self.assertEqual(self.p.book.active("T1"), ["ent-bump", "ent-main"])

    def test_a19_duplicate_event_no_duplicate_effects(self):
        ev = normalize_order_event(raw("e1", [line("prod-main", "li-m", ["ent-main"])]), BINDINGS)
        self.p.process(ev)
        again = self.p.process(copy.deepcopy(ev))
        self.assertEqual(again["result"], "duplicate_event")
        grants = [e for e in self.p.ledger.entries()
                  if e["payload"].get("entitlement") == "ent-main"]
        self.assertEqual(len(grants), 1)

    def test_a19_later_extra_same_order_not_deduped_by_order(self):
        e1 = normalize_order_event(raw("e1", [line("prod-main", "li-m", ["ent-main"])]), BINDINGS)
        self.p.process(e1)
        e2 = normalize_order_event(raw("e2", [line("prod-u1", "li-u1", ["ent-u1"])],
                                       native_transaction_ref="txn-2"), BINDINGS)
        out = self.p.process(e2)
        self.assertEqual(out["result"], "processed")
        self.assertEqual(self.p.book.active("T1"), ["ent-main", "ent-u1"])

    def test_a19_out_of_order_u1_before_main(self):
        e2 = normalize_order_event(raw("e2", [line("prod-u1", "li-u1", ["ent-u1"])],
                                       native_transaction_ref="txn-2"), BINDINGS)
        self.p.process(e2)
        e1 = normalize_order_event(raw("e1", [line("prod-main", "li-m", ["ent-main"])]), BINDINGS)
        self.p.process(e1)
        self.assertEqual(self.p.book.active("T1"), ["ent-main", "ent-u1"])

    def test_upsell_label_resolved_by_binding_not_label(self):
        # native says 'Upsell' for all three; bindings decide the slot
        for prod, slot in [("prod-u1", "upsell_1"), ("prod-d1", "downsell_1"),
                           ("prod-u2", "upsell_2")]:
            ev = normalize_order_event(raw("ex", [line(prod, "li-x", ["e"])],
                                           submission_type="Upsell"), BINDINGS)
            self.assertEqual(ev["line_items"][0]["slot"], slot)

    def test_unmapped_product_quarantined(self):
        with self.assertRaises(ValueError):
            normalize_order_event(raw("e9", [line("prod-???", "li-z", ["e"])]), BINDINGS)

    def test_missing_event_identity_quarantined(self):
        with self.assertRaises(ValueError):
            normalize_order_event(raw("", [line("prod-main", "li-m", ["e"])]), BINDINGS)

    def test_pending_and_failed_never_grant(self):
        for status in ("pending", "failed", "requires_customer_action", "unknown"):
            p = PurchaseProcessor()
            ev = normalize_order_event(raw("e1", [line("prod-main", "li-m", ["ent-main"])],
                                           status=status), BINDINGS)
            out = p.process(ev)
            self.assertTrue(out["result"].startswith("no_grant"))
            self.assertEqual(p.book.active("T1"), [])

    def test_a20_fulfillment_without_thankyou_visit(self):
        ev = normalize_order_event(raw("e1", [line("prod-main", "li-m", ["ent-main"])]), BINDINGS)
        self.p.process(ev)  # no page-visit input exists in the API at all
        kinds = [e["key"][3] for e in self.p.ledger.entries()]
        self.assertIn("initiate_fulfillment", kinds)

    def test_refund_revokes_only_affected_line(self):
        e1 = normalize_order_event(raw("e1", [line("prod-main", "li-m", ["ent-main"]),
                                              line("prod-bump", "li-b", ["ent-bump"])]), BINDINGS)
        self.p.process(e1)
        rf = normalize_order_event(raw("e7", [line("prod-bump", "li-b", ["ent-bump"])],
                                       status="refunded", event_type="refund_observed",
                                       native_transaction_ref="txn-1"), BINDINGS)
        self.p.process(rf)
        self.assertEqual(self.p.book.active("T1"), ["ent-main"])

    def test_a21_suppression_rechecked_at_dispatch(self):
        sent = []
        queued = {"tenant_id": "T1", "launch_id": "LN1", "contact_ref": "c1"}
        # queued BEFORE purchase; purchase lands while it sits in the queue
        ev = normalize_order_event(raw("e1", [line("prod-main", "li-m", ["ent-main"])]), BINDINGS)
        self.p.process(ev, contact_ref="c1")
        result = dispatch_marketing(self.p, queued,
                                    lambda q: sent.append(q) or "sent")
        self.assertEqual(result, "suppressed")
        self.assertEqual(sent, [])
        # a non-buyer on the same launch still receives
        other = {"tenant_id": "T1", "launch_id": "LN1", "contact_ref": "c2"}
        self.assertEqual(dispatch_marketing(self.p, other,
                                              lambda q: "sent"), "sent")

    def test_a18_handler_has_no_waits_and_repeat_buyer_works(self):
        # second launch, same contact, rapid succession: nothing blocks
        e1 = normalize_order_event(raw("e1", [line("prod-main", "li-m", ["ent-main"])]), BINDINGS)
        self.p.process(e1, contact_ref="c1")
        e3 = normalize_order_event(raw("e3", [line("prod-main", "li-m2", ["ent-main2"])],
                                       launch_id="LN2", native_order_ref="ord-2",
                                       native_transaction_ref="txn-9"), BINDINGS)
        out = self.p.process(e3, contact_ref="c1")
        self.assertEqual(out["result"], "processed")

    def test_wrong_tenant_isolated(self):
        e1 = normalize_order_event(raw("e1", [line("prod-main", "li-m", ["ent-main"])]), BINDINGS)
        self.p.process(e1)
        other = copy.deepcopy(e1)
        other["tenant_id"] = "T2"
        out = self.p.process(other)  # same provider event id, other tenant
        self.assertEqual(out["result"], "processed")

    def test_schema_rejects_unknown_fields(self):
        ev = normalize_order_event(raw("e1", [line("prod-main", "li-m", ["ent-main"])]), BINDINGS)
        bad = dict(ev, contact_email="x@example.com")
        with self.assertRaises(Exception):
            validate_event(bad)

    def test_subscription_renewal_grants_per_new_transaction(self):
        # doc 14 s11 recurring renewals: a renewal is a subscription_updated
        # event under the same succeeded-only rule; no special shortcut.
        e1 = normalize_order_event(raw("e1", [line("prod-main", "li-m", ["ent-main"])]), BINDINGS)
        self.p.process(e1, contact_ref="c1")
        ren = normalize_order_event(raw("e2", [line("prod-main", "li-m2", ["ent-main"])],
                                        event_type="subscription_updated",
                                        native_transaction_ref="txn-2"), BINDINGS)
        out = self.p.process(ren, contact_ref="c1")
        self.assertEqual(out["result"], "processed")
        self.assertEqual(self.p.book.active("T1"), ["ent-main"])
        # redelivery of the same renewal event is a no-op
        again = self.p.process(copy.deepcopy(ren), contact_ref="c1")
        self.assertEqual(again["result"], "duplicate_event")
        grants = [e for e in self.p.ledger.entries()
                  if e["payload"].get("entitlement") == "ent-main"]
        self.assertEqual(len(grants), 2)  # one per transaction, never more

    def test_failed_renewal_never_grants(self):
        e1 = normalize_order_event(raw("e1", [line("prod-main", "li-m", ["ent-main"])]), BINDINGS)
        self.p.process(e1, contact_ref="c1")
        ren = normalize_order_event(raw("e2", [line("prod-main", "li-m2", ["ent-main"])],
                                        status="failed",
                                        event_type="subscription_updated",
                                        native_transaction_ref="txn-2"), BINDINGS)
        out = self.p.process(ren, contact_ref="c1")
        self.assertEqual(out["result"], "no_grant:failed")
        # a failed renewal grants nothing new; whether it later revokes is an
        # access-change policy for the adapter addendum, not assumed here.

    def test_atomic_claim_single_winner(self):
        ledger = ActionLedger()
        key = ("T1", "txn-1", "li-m", "grant_access", "v1")
        self.assertIsNone(ledger.claim(key, {"entitlement": "ent-main"}))
        self.assertIsNotNone(ledger.claim(key, {"entitlement": "ent-main"}))


if __name__ == "__main__":
    unittest.main()
