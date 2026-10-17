"""Acceptance harness for S44 units A17 and A19.

Drives the REAL production pipeline — normalizer.ingest into the durable
store, then DurableProcessor.process — exactly as wired in
work/processor/test_processor.py. The only fake is at the native
boundary: the verified-purchase tag applier is a recording callable
(the engine-side seam of DESIGN-S44-06 section 1). No native system is
touched; this is L1/L2 module-level proof, NOT native (L4) proof.

A17 (owner S44, weight 3): "Original plus bump event does not drop
    the bump."
    One order event whose lines are [main, bump] must grant BOTH lines:
    per-line entitlement state, the buyer record, and the fulfillment
    action set must all carry the bump line, not just the main line.

A19 (owner S44, weight 3): "Duplicate/out-of-order events handled
    without duplicate effects."
    - Duplicate: the same verified event delivered twice is recognized
      as a duplicate at ingest (dedup is by verified provider event
      identity, never by contact alone) and produces ZERO additional
      effects. Re-processing an already-accepted event is likewise
      effect-free, because every effect is a claimed ledger action.
    - Out-of-order: for one order / one verified transaction, the bump
      line's event arrives FIRST, the main line's event SECOND, and the
      original combined event LAST (three distinct provider event
      identities). All three are accepted — dedup never drops by order
      alone — and the final state is exactly the union of lines, each
      granted once, one fulfillment action per line, one tag call.
"""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE.parent / "processor"))
sys.path.insert(0, str(_HERE.parent / "store"))
sys.path.insert(0, str(_HERE.parent / "normalizer"))
from normalizer import LaunchContext, ingest
from processor import DurableProcessor
from store import Store

CTX = LaunchContext("T1", "LOC1", "LN1",
                    {"prod-main": "main", "prod-bump": "bump"})

MAIN_LINE = {"native_line_ref": "li-m", "native_product_ref": "prod-main",
             "offer_id": "off-main", "currency": "USD",
             "amount_minor": 49700, "entitlement_ids": ["ent-main"]}
BUMP_LINE = {"native_line_ref": "li-b", "native_product_ref": "prod-bump",
             "offer_id": "off-bump", "currency": "USD",
             "amount_minor": 3700, "entitlement_ids": ["ent-bump"]}

GRANT_M = ("T1", "txn-1", "li-m", "grant_access", "v1")
GRANT_B = ("T1", "txn-1", "li-b", "grant_access", "v1")
FULFILL_M = ("T1", "txn-1", "li-m", "initiate_fulfillment", "v1")
FULFILL_B = ("T1", "txn-1", "li-b", "initiate_fulfillment", "v1")
TAG = ("T1", "txn-1", "*", "apply_verified_purchase_tag", "v1")
ALL_KEYS = (GRANT_M, GRANT_B, FULFILL_M, FULFILL_B, TAG)


def readback(event_id="evt-1", lines=(MAIN_LINE, BUMP_LINE), **overrides):
    """Native order read-back, same shape as test_processor.readback.
    All events below share order ord-1 / transaction txn-1; only the
    verified provider event identity and the line subset vary."""
    rb = {
        "tenant_id": "T1", "location_id": "LOC1", "launch_id": "LN1",
        "provider": "ghl", "provider_event_id": event_id,
        "native_event_kind": "order_paid",
        "native_order_ref": "ord-1", "native_transaction_ref": "txn-1",
        "occurred_at": "2026-10-15T20:00:00Z",
        "received_at": "2026-10-15T20:00:05Z",
        "payment_status": "succeeded",
        "line_items": [dict(line) for line in lines],
        "evidence_ref": "readback/ord-1", "test_only": True,
        "contact_ref": "contact-1",
    }
    rb.update(overrides)
    return rb


class AcceptanceBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmp.name) / "s44.db")
        self.store = Store(self.db_path)
        self.tags_applied = []
        self.proc = DurableProcessor(
            self.store,
            tag_applier=lambda c, t: self.tags_applied.append((c, t)),
            purchase_tag="siglaunch:purchased:main")

    def tearDown(self):
        self.tmp.cleanup()

    def _ingest_process(self, rb):
        status, payload = ingest(self.store, rb, CTX)
        self.assertEqual(status, "accepted")
        result = self.proc.process(
            payload["event"],
            contact_ref=payload["contact_ref_context"])
        return payload, result

    def _table_counts(self):
        """Row counts straight from the durable store file: the
        catch-all check that no unexpected effect row exists anywhere."""
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        try:
            return {t: conn.execute(
                f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in ("inbox_events", "actions", "entitlements",
                          "buyers", "buyer_lines")}
        finally:
            conn.close()

    def _action_states(self):
        return {key: (self.store.get_action(key) or {}).get("state")
                for key in ALL_KEYS}

    def _snapshot(self):
        return {
            "counts": self._table_counts(),
            "active_entitlements": self.store.active_entitlements("T1"),
            "buyer_lines": sorted(
                self.store.buyer_lines("T1", "LN1", "contact-1")),
            "action_states": self._action_states(),
            "tag_calls": list(self.tags_applied),
        }


class A17OriginalPlusBump(AcceptanceBase):
    def test_original_plus_bump_event_does_not_drop_the_bump(self):
        _, result = self._ingest_process(readback())
        self.assertEqual(result["result"], "processed")

        # Per-line entitlement state: BOTH lines granted. The bump
        # assertions are the regression this unit exists to catch —
        # a pipeline that keeps only the first/main line fails here.
        self.assertTrue(
            self.store.line_has_active_entitlement("T1", "li-m"),
            "main line li-m must carry an active entitlement")
        self.assertTrue(
            self.store.line_has_active_entitlement("T1", "li-b"),
            "A17 REGRESSION: bump line li-b lost its entitlement")
        self.assertEqual(self.store.active_entitlements("T1"),
                         ["ent-bump", "ent-main"])
        self.assertIn("ent-bump", self.store.active_entitlements("T1"),
                      "A17 REGRESSION: bump entitlement ent-bump missing")

        # The buyer record carries BOTH lines, bump included.
        self.assertEqual(
            sorted(self.store.buyer_lines("T1", "LN1", "contact-1")),
            ["li-b", "li-m"],
            "buyer record must link both the main and the bump line")

        # The fulfillment action set includes BOTH lines, and each
        # claimed fulfillment actually executes with its own slot.
        for key in (FULFILL_M, FULFILL_B):
            action = self.store.get_action(key)
            self.assertIsNotNone(
                action, f"fulfillment action missing for {key[2]}")
            self.assertEqual(action["state"], "claimed")
        executed = []
        self.assertEqual(
            self.proc.fulfill(FULFILL_M, executed.append), "done")
        self.assertEqual(
            self.proc.fulfill(FULFILL_B, executed.append), "done")
        self.assertEqual(executed, [{"slot": "main"}, {"slot": "bump"}],
                         "fulfillment must run once per line, bump too")

        # Grant actions exist per line and completed; tag applied once.
        self.assertEqual(self.store.get_action(GRANT_M)["state"], "done")
        self.assertEqual(self.store.get_action(GRANT_B)["state"], "done")
        self.assertEqual(self.tags_applied,
                         [("contact-1", "siglaunch:purchased:main")])


class A19Duplicates(AcceptanceBase):
    def test_duplicate_redelivery_produces_zero_additional_effects(self):
        self._ingest_process(readback())
        before = self._snapshot()
        # Baseline sanity: 2 grants + 2 fulfillments + 1 tag action,
        # 2 entitlement rows, 1 buyer with 2 lines, 1 inbox record.
        self.assertEqual(before["counts"], {
            "inbox_events": 1, "actions": 5, "entitlements": 2,
            "buyers": 1, "buyer_lines": 2})
        self.assertEqual(len(before["tag_calls"]), 1)

        # Second delivery of the SAME verified event (same provider
        # event identity): recognized as a duplicate at ingest, before
        # the processor can ever see it.
        status, _ = ingest(self.store, readback(), CTX)
        self.assertEqual(status, "duplicate")

        after = self._snapshot()
        self.assertEqual(after, before,
                         "duplicate delivery changed durable state")
        self.assertEqual(len(self.tags_applied), 1,
                         "duplicate delivery re-applied the purchase tag")

    def test_reprocessing_an_accepted_event_is_effect_free(self):
        payload, _ = self._ingest_process(readback())
        before = self._snapshot()

        # A worker retry re-invokes process() on the same accepted
        # event: every effect is a claimed ledger action, so nothing
        # is created twice and the tag applier is not called again.
        again = self.proc.process(
            payload["event"],
            contact_ref=payload["contact_ref_context"])
        self.assertEqual(again["result"], "processed")
        self.assertEqual(again["actions_created"], 0)
        self.assertEqual(self._snapshot(), before)
        self.assertEqual(len(self.tags_applied), 1)


class A19OutOfOrder(AcceptanceBase):
    def test_out_of_order_delivery_unions_lines_without_duplicates(self):
        # 1) The bump (extra) line's event arrives FIRST.
        self._ingest_process(
            readback(event_id="evt-bump-first", lines=(BUMP_LINE,)))
        self.assertEqual(self.store.active_entitlements("T1"),
                         ["ent-bump"])
        self.assertEqual(
            sorted(self.store.buyer_lines("T1", "LN1", "contact-1")),
            ["li-b"])

        # 2) The main line's event arrives SECOND.
        self._ingest_process(
            readback(event_id="evt-main-second", lines=(MAIN_LINE,)))
        self.assertEqual(self.store.active_entitlements("T1"),
                         ["ent-bump", "ent-main"])

        # 3) The ORIGINAL combined event arrives LAST. It is a distinct
        # verified event identity, so ingest accepts it (dedup is by
        # event identity, never by order alone) — and every one of its
        # effects is already claimed, so it changes nothing.
        self._ingest_process(readback(event_id="evt-original-combined"))
        snap = self._snapshot()
        self.assertEqual(snap["active_entitlements"],
                         ["ent-bump", "ent-main"],
                         "final state must be exactly the union of lines")
        self.assertEqual(snap["buyer_lines"], ["li-b", "li-m"])
        # Each line granted exactly once and fulfilled exactly once:
        # 2 grant actions + 2 fulfillment actions + 1 tag action total,
        # despite three accepted events covering the lines.
        self.assertEqual(snap["counts"], {
            "inbox_events": 3, "actions": 5, "entitlements": 2,
            "buyers": 1, "buyer_lines": 2})
        self.assertEqual(snap["action_states"][GRANT_M], "done")
        self.assertEqual(snap["action_states"][GRANT_B], "done")
        self.assertEqual(snap["action_states"][FULFILL_M], "claimed")
        self.assertEqual(snap["action_states"][FULFILL_B], "claimed")
        self.assertEqual(len(self.tags_applied), 1,
                         "tag must be applied exactly once across all "
                         "three out-of-order deliveries")


if __name__ == "__main__":
    unittest.main()
