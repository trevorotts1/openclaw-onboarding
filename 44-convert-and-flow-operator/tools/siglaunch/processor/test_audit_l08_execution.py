"""Audit lane L08 (UL-002) processor proofs: paid fulfillment and
execution ownership.

Pins the four behaviours this lane repairs, against a real SQLite store
and recording fakes only at the external boundary:

  1. entitlement identity is part of the durable grant key — a line with
     several entitlements records every one of them;
  2. an already-processed bundle that is incomplete (claim recorded, right
     missing) is reviewed and reconciled without repeating an external
     effect;
  3. every side effect runs under the store's durable lease with a
     fencing token, so two workers cannot produce two effects;
  4. a lost acknowledgement parks the effect and is reconciled against
     remote state BEFORE any retry — a confirmed success is never
     re-applied.

Synthetic-local only: fake contact/tag/tenant strings, recording
appliers and executors, no network, no live provider, no secrets.
"""
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "store"))

from processor import DurableProcessor
from store import Store

TENANT = "T1"
TXN = "txn-1"
TAG = "siglaunch:purchased:main"
VERSION = "v1"


def line(ref, slot, ents, offer="off-1"):
    return {"native_line_ref": ref, "offer_id": offer, "slot": slot,
            "currency": "USD", "amount_minor": 1000,
            "entitlement_ids": list(ents)}


def make_event(line_items=None, *, txn=TXN, status="succeeded",
               kind="purchase_observed", event_id="evt-1",
               evidence="readback/ord-1", **overrides):
    event = {
        "schema_version": "1.2",
        "tenant_id": TENANT, "location_id": "LOC1", "launch_id": "LN1",
        "provider": "ghl", "event_id": event_id, "event_type": kind,
        "native_order_ref": "ord-1", "native_transaction_ref": txn,
        "occurred_at": "2026-10-15T20:00:00Z",
        "received_at": "2026-10-15T20:00:05Z",
        "payment_status": status,
        "line_items": (line_items if line_items is not None
                       else [line("li-m", "main", ["ent-main"])]),
        "evidence_ref": evidence,
        "test_only": True,
    }
    event.update(overrides)
    return event


class RecordingApplier:
    """The tag seam's fake: records every invocation (thread-safe) and
    can fail a chosen invocation AFTER recording it, which is exactly a
    lost acknowledgement (the remote write happened, the answer did not
    arrive)."""

    def __init__(self, fail_on=()):
        self.calls = []
        self.fail_on = set(fail_on)
        self._lock = threading.Lock()
        self._n = 0

    def __call__(self, contact_ref, tag):
        with self._lock:
            self._n += 1
            self.calls.append((contact_ref, tag))
            n = self._n
        if n in self.fail_on:
            raise RuntimeError("acknowledgement lost")

    def __len__(self):
        return len(self.calls)


def grant_action_key(line_ref="li-m", txn=TXN):
    return (TENANT, txn, line_ref, "grant_access", VERSION)


def right_key(ent, line_ref="li-m", txn=TXN, action="grant_access"):
    return (TENANT, txn, line_ref, action, ent)


def fulfillment_key(line_ref="li-m", txn=TXN):
    return (TENANT, txn, line_ref, "initiate_fulfillment", VERSION)


def tag_key(txn=TXN):
    return (TENANT, txn, "*", "apply_verified_purchase_tag", VERSION)


def right_rows(db_path, entitlement):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT state FROM right_claims WHERE tenant_id=?"
            " AND entitlement=?", (TENANT, entitlement)).fetchall()
    finally:
        conn.close()


class L08Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "l08.db")
        self.store = Store(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def processor(self, applier=None, **kwargs):
        return DurableProcessor(
            self.store,
            tag_applier=applier if applier is not None else RecordingApplier(),
            purchase_tag=TAG, **kwargs)


class GrantKeyTests(L08Base):
    def test_every_entitlement_on_a_line_is_granted_once(self):
        applier = RecordingApplier()
        proc = self.processor(applier)
        out = proc.process(make_event(
            [line("li-m", "main", ["ent-a", "ent-b"])]),
            contact_ref="contact-1")
        self.assertEqual(out["result"], "processed")
        self.assertEqual(self.store.active_entitlements(TENANT),
                         ["ent-a", "ent-b"])
        # one durable claim per entitlement, both done
        for ent in ("ent-a", "ent-b"):
            self.assertEqual(self.store.get_right(right_key(ent))["state"],
                             "done")
        # line-level surface unchanged: one done grant row per line
        self.assertEqual(
            self.store.get_action(grant_action_key())["state"], "done")
        # external effects are not multiplied by the second entitlement
        self.assertEqual(len(applier), 1)
        self.assertEqual(
            self.store.get_action(fulfillment_key())["state"], "claimed")

    def test_replay_of_a_complete_bundle_creates_no_new_effect(self):
        applier = RecordingApplier()
        proc = self.processor(applier)
        event = make_event([line("li-m", "main", ["ent-a", "ent-b"])])
        first = proc.process(event, contact_ref="contact-1")
        second = proc.process(event, contact_ref="contact-1")
        self.assertGreater(first["actions_created"], 0)
        self.assertEqual(second["actions_created"], 0)
        self.assertEqual(len(applier), 1)

    def test_pending_and_failed_never_grant(self):
        proc = self.processor()
        for status in ("pending", "failed", "requires_customer_action",
                       "unknown"):
            out = proc.process(make_event(
                [line("li-m", "main", ["ent-main"])], status=status,
                event_id=f"evt-{status}"))
            self.assertEqual(out["result"], f"no_grant:{status}")
            self.assertIsNone(self.store.get_right(right_key("ent-main")))
            self.assertEqual(self.store.active_entitlements(TENANT), [])


class IncompleteBundleTests(L08Base):
    def test_line_action_done_but_right_missing_is_reconciled(self):
        # a prior run marked the line grant action done, then crashed
        # before recording the right. Replay must reconcile the expected
        # right without repeating the tag or the fulfillment.
        applier = RecordingApplier()
        proc = self.processor(applier)
        key = grant_action_key()
        self.assertIsNone(self.store.claim_action(key, {}))
        self.store.mark_action(key, "done", evidence_ref="readback/old")
        # the crash window itself: right claimed, grant never written
        self.assertIsNone(self.store.claim_right(right_key("ent-main")))
        out = proc.process(make_event(), contact_ref="contact-1")
        self.assertEqual(out["rights_reconciled"], 1)
        self.assertEqual(self.store.active_entitlements(TENANT),
                         ["ent-main"])
        self.assertEqual(self.store.get_right(right_key("ent-main"))["state"],
                         "done")
        self.assertEqual(len(applier), 1)
        self.assertEqual(
            self.store.get_action(fulfillment_key())["state"], "claimed")

    def test_claimed_right_without_book_row_is_recorded(self):
        # the crash window: right claimed, grant never written
        proc = self.processor()
        self.assertIsNone(self.store.claim_right(right_key("ent-main")))
        out = proc.process(make_event(), contact_ref="contact-1")
        self.assertEqual(out["rights_reconciled"], 1)
        self.assertEqual(self.store.active_entitlements(TENANT),
                         ["ent-main"])
        self.assertEqual(self.store.get_right(right_key("ent-main"))["state"],
                         "done")
        # the claim still admits exactly one external effect
        self.assertEqual(
            len(right_rows(self.db, "ent-main")), 1)

    def test_parked_right_stays_visible_and_is_not_repeated(self):
        proc = self.processor()
        self.assertIsNone(self.store.claim_right(right_key("ent-main")))
        self.store.mark_right(right_key("ent-main"), "unknown",
                              evidence_ref="readback/ambiguous")
        out = proc.process(make_event(), contact_ref="contact-1")
        self.assertEqual(out["pending_rights"], 1)
        self.assertEqual(self.store.active_entitlements(TENANT), [])
        self.assertEqual(self.store.get_right(right_key("ent-main"))["state"],
                         "unknown")
        # the line-level action is not marked done over a parked right
        self.assertEqual(
            self.store.get_action(grant_action_key())["state"], "claimed")


class ExecutionOwnershipTests(L08Base):
    def test_concurrent_workers_produce_one_grant_and_one_effect(self):
        applier = RecordingApplier()
        proc = self.processor(applier)
        event = make_event([line("li-m", "main", ["ent-a", "ent-b"])])
        n = 8
        barrier = threading.Barrier(n)
        outcomes = []
        lock = threading.Lock()

        def worker():
            barrier.wait()
            out = proc.process(event, contact_ref="contact-1")
            with lock:
                outcomes.append(out["tag_state"])

        threads = [threading.Thread(target=worker) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(applier), 1, "exactly one tag application")
        self.assertEqual(
            self.store.get_action(tag_key())["state"], "done")
        self.assertEqual(self.store.active_entitlements(TENANT),
                         ["ent-a", "ent-b"])
        for ent in ("ent-a", "ent-b"):
            self.assertEqual(len(right_rows(self.db, ent)), 1)
        self.assertEqual(
            self.store.get_action(fulfillment_key())["state"], "claimed")

    def test_tag_effect_waits_for_a_live_lease_owner(self):
        applier = RecordingApplier()
        proc = self.processor(applier)
        resource = f"effect:apply_verified_purchase_tag:{TXN}"
        token = self.store.acquire_lease(TENANT, resource, "other-box",
                                         ttl_seconds=60)
        self.assertEqual(token, 1)
        out = proc.process(make_event(), contact_ref="contact-1")
        self.assertEqual(out["tag_state"], "held_elsewhere")
        self.assertEqual(len(applier), 0)
        self.assertEqual(self.store.get_action(tag_key())["state"],
                         "claimed")
        # the owner goes away: the next pass resumes the effect once
        self.store.release_lease(TENANT, resource, "other-box", token)
        out = proc.process(make_event(), contact_ref="contact-1")
        self.assertEqual(out["tag_state"], "done")
        self.assertEqual(len(applier), 1)
        self.assertEqual(self.store.get_action(tag_key())["state"], "done")

    def test_fulfillment_two_workers_execute_once(self):
        self.processor().process(make_event(), contact_ref="contact-1")
        key = fulfillment_key()
        executed = []
        lock = threading.Lock()

        def executor(payload):
            with lock:
                executed.append(payload)
            time.sleep(0.05)

        results = []
        barrier = threading.Barrier(2)

        def worker():
            barrier.wait()
            results.append(self.processor().fulfill(key, executor))

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len(executed), 1)
        self.assertIn("done", results)
        self.assertEqual(self.store.get_action(key)["state"], "done")

    def test_fulfillment_waits_for_a_live_lease_owner(self):
        self.processor().process(make_event(), contact_ref="contact-1")
        key = fulfillment_key()
        resource = f"effect:initiate_fulfillment:{TXN}:li-m"
        token = self.store.acquire_lease(TENANT, resource, "other-box")
        executed = []
        self.assertEqual(self.processor().fulfill(
            key, lambda p: executed.append(p)), "held_elsewhere")
        self.assertEqual(executed, [])
        self.store.release_lease(TENANT, resource, "other-box", token)
        self.assertEqual(self.processor().fulfill(
            key, lambda p: executed.append(p)), "done")
        self.assertEqual(executed, [{"slot": "main"}])


class LostAcknowledgementTests(L08Base):
    def test_lost_ack_is_parked_then_reconciled_without_repeat(self):
        applier = RecordingApplier(fail_on={1})
        proc = self.processor(applier)
        out = proc.process(make_event(), contact_ref="contact-1")
        self.assertEqual(out["tag_state"], "parked_unknown")
        self.assertEqual(len(applier), 1)
        self.assertEqual(self.store.get_action(tag_key())["state"],
                         "unknown")
        # reconciliation against remote state confirms the write landed
        reconciler = lambda contact, tag: True
        first = self.processor(applier, tag_reconciler=reconciler)
        out = first.process(make_event(), contact_ref="contact-1")
        self.assertEqual(out["tag_state"], "reconciled_done")
        self.assertEqual(self.store.get_action(tag_key())["state"], "done")
        self.assertEqual(len(applier), 1, "never re-applied")
        # a further replay is still a no-op
        self.processor(applier, tag_reconciler=reconciler).process(
            make_event(), contact_ref="contact-1")
        self.assertEqual(len(applier), 1)

    def test_lost_ack_confirmed_absent_retries_exactly_once(self):
        applier = RecordingApplier(fail_on={1})
        proc = self.processor(applier)
        proc.process(make_event(), contact_ref="contact-1")
        self.assertEqual(self.store.get_action(tag_key())["state"],
                         "unknown")
        reconciler = lambda contact, tag: False
        out = self.processor(applier, tag_reconciler=reconciler).process(
            make_event(), contact_ref="contact-1")
        self.assertEqual(out["tag_state"], "done")
        self.assertEqual(len(applier), 2)
        self.assertEqual(self.store.get_action(tag_key())["state"], "done")
        # done is terminal: no third application
        self.processor(applier, tag_reconciler=reconciler).process(
            make_event(), contact_ref="contact-1")
        self.assertEqual(len(applier), 2)

    def test_unknown_stays_parked_without_a_reconciler(self):
        applier = RecordingApplier(fail_on={1})
        proc = self.processor(applier)
        proc.process(make_event(), contact_ref="contact-1")
        out = proc.process(make_event(), contact_ref="contact-1")
        self.assertEqual(out["tag_state"], "unknown")
        self.assertEqual(len(applier), 1)
        self.assertEqual(self.store.get_action(tag_key())["state"],
                         "unknown")
        self.assertEqual(len(self.store.unknown_actions(TENANT)), 1)

    def test_fulfillment_unknown_reconciles_before_retry(self):
        self.processor().process(make_event(), contact_ref="contact-1")
        key = fulfillment_key()
        executed = []

        def boom(payload):
            executed.append(payload)
            raise RuntimeError("acknowledgement lost")

        proc = self.processor()
        self.assertEqual(proc.fulfill(key, boom), "parked_unknown")
        self.assertEqual(len(executed), 1)
        self.assertEqual(self.store.get_action(key)["state"], "unknown")
        # remote confirms the effect landed: mark done, never execute again
        self.assertEqual(proc.fulfill(key, boom, reconcile=lambda p: True),
                         "reconciled_done")
        self.assertEqual(len(executed), 1)
        self.assertEqual(self.store.get_action(key)["state"], "done")

    def test_fulfillment_unknown_confirmed_absent_retries_once(self):
        self.processor().process(make_event(), contact_ref="contact-1")
        key = fulfillment_key()
        executed = []
        proc = self.processor()

        def boom(payload):
            executed.append(payload)
            raise RuntimeError("acknowledgement lost")

        self.assertEqual(proc.fulfill(key, boom), "parked_unknown")
        self.assertEqual(proc.fulfill(
            key, lambda p: executed.append(p),
            reconcile=lambda p: False), "done")
        self.assertEqual(len(executed), 2)
        self.assertEqual(self.store.get_action(key)["state"], "done")


class RefundTests(L08Base):
    def _buy_two_lines(self, applier=None):
        proc = self.processor(applier)
        proc.process(make_event([
            line("li-m", "main", ["ent-main"], offer="off-main"),
            line("li-b", "bump", ["ent-bump"], offer="off-bump"),
        ]), contact_ref="contact-1")
        return proc

    def test_partial_refund_removes_only_its_line_and_replay_cannot_resurrect(self):
        applier = RecordingApplier()
        proc = self._buy_two_lines(applier)
        refund = make_event(
            [line("li-b", "bump", ["ent-bump"], offer="off-bump")],
            txn="txn-refund", status="partially_refunded",
            kind="refund_observed", event_id="evt-refund")
        out = proc.process(refund)
        self.assertEqual(out["result"], "refund_applied")
        self.assertEqual(out["rights_revoked"], 1)
        self.assertEqual(self.store.active_entitlements(TENANT),
                         ["ent-main"])
        self.assertEqual(
            self.store.entitlement_state(TENANT, "li-b", "ent-bump"),
            "revoked")
        self.assertEqual(
            self.store.get_right(right_key("ent-bump", line_ref="li-b",
                                           txn="txn-refund",
                                           action="revoke_access"))["state"],
            "done")
        # replaying the purchase event must not resurrect the revoked right
        replay = proc.process(make_event([
            line("li-m", "main", ["ent-main"], offer="off-main"),
            line("li-b", "bump", ["ent-bump"], offer="off-bump"),
        ], event_id="evt-replay"), contact_ref="contact-1")
        self.assertEqual(replay["result"], "processed")
        self.assertEqual(self.store.active_entitlements(TENANT),
                         ["ent-main"])
        self.assertEqual(len(applier), 1, "replay repeats no effect")

    def test_full_refund_revokes_every_line_and_lifts_suppression(self):
        proc = self._buy_two_lines()
        self.assertTrue(proc.is_suppressed(TENANT, "LN1", "contact-1"))
        refund = make_event([
            line("li-m", "main", ["ent-main"], offer="off-main"),
            line("li-b", "bump", ["ent-bump"], offer="off-bump"),
        ], txn="txn-refund2", status="refunded",
            kind="refund_observed", event_id="evt-refund2")
        proc.process(refund)
        self.assertEqual(self.store.active_entitlements(TENANT), [])
        self.assertFalse(proc.is_suppressed(TENANT, "LN1", "contact-1"))


if __name__ == "__main__":
    unittest.main()
