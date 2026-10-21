"""Audit lane L08 (UL-012) takeover and guarded-completion proofs.

Pins the four behaviours the uncommitted processor/store changes add,
against a real SQLite store with synthetic-local fakes only at the
external boundary (recording appliers/executors, fake tenant/tag
strings, no network, no live provider, no secrets):

  1. takeover parks without executing — taking over an expired
     unreleased effect lease never runs the callback; the action parks
     for reconciliation;
  2. lease-lost-mid-callback parks exactly once — a callback that
     outlives its lease records unknown via the settle path and never
     retries blindly;
  3. lost-ack reconcile is single-effect — a possibly-landed effect
     confirmed present by the reconciler is marked done without a
     second execution;
  4. entitlement bundling preserved — a multi-entitlement line still
     grants every right with exactly one tag effect under the stable
     idempotency key.
"""
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "store"))

from processor import (DurableProcessor, effect_resource_for_action,
                       effect_resource_for_tag)
from store import Store

TENANT = "T1"
TXN = "txn-takeover"
TAG = "siglaunch:purchased:main"
VERSION = "v1"


def line(ref, slot, ents):
    return {"native_line_ref": ref, "offer_id": "off-1", "slot": slot,
            "currency": "USD", "amount_minor": 1000,
            "entitlement_ids": list(ents)}


def make_event(line_items=None, *, txn=TXN, event_id="evt-tk-1"):
    return {
        "schema_version": "1.2",
        "tenant_id": TENANT, "location_id": "LOC1", "launch_id": "LN1",
        "provider": "ghl", "event_id": event_id, "event_type":
        "purchase_observed",
        "native_order_ref": "ord-tk-1", "native_transaction_ref": txn,
        "occurred_at": "2026-10-15T20:00:00Z",
        "received_at": "2026-10-15T20:00:05Z",
        "payment_status": "succeeded",
        "line_items": (line_items if line_items is not None
                       else [line("li-m", "main", ["ent-main"])]),
        "evidence_ref": "readback/ord-tk-1",
        "test_only": True,
    }


class RecordingApplier:
    def __init__(self):
        self.calls = []

    def __call__(self, contact_ref, tag):
        self.calls.append((contact_ref, tag))


def tag_key(txn=TXN):
    return (TENANT, txn, "*", "apply_verified_purchase_tag", VERSION)


def fulfillment_key(line_ref="li-m", txn=TXN):
    return (TENANT, txn, line_ref, "initiate_fulfillment", VERSION)


def expire_unreleased_lease(store, tenant, resource):
    """A dead owner's row: acquired, never released, lapsed."""
    store.acquire_lease(tenant, resource, "dead-owner", ttl_seconds=0.02)
    time.sleep(0.1)


class TakeoverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.tmp.name) / "tk.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_takeover_parks_tag_without_executing(self):
        expire_unreleased_lease(
            self.store, TENANT, effect_resource_for_tag(TXN))
        applier = RecordingApplier()
        proc = DurableProcessor(self.store, tag_applier=applier,
                                purchase_tag=TAG)
        out = proc.process(make_event(), contact_ref="contact-1")
        self.assertEqual(out["tag_state"], "parked_takeover")
        self.assertEqual(applier.calls, [])
        self.assertEqual(self.store.get_action(tag_key())["state"],
                         "unknown")

    def test_takeover_parks_fulfillment_without_executing(self):
        proc = DurableProcessor(self.store)
        proc.process(make_event(), contact_ref="contact-1")
        key = fulfillment_key()
        expire_unreleased_lease(
            self.store, TENANT,
            effect_resource_for_action("initiate_fulfillment", TXN,
                                       "li-m"))
        executed = []
        out = DurableProcessor(self.store).fulfill(
            key, lambda p: executed.append(p))
        self.assertEqual(out, "parked_takeover")
        self.assertEqual(executed, [])
        self.assertEqual(self.store.get_action(key)["state"], "unknown")


class LostOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.tmp.name) / "lo.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def _short_lease_processor(self, **kwargs):
        return DurableProcessor(self.store, lease_ttl_seconds=0.05,
                                **kwargs)

    def test_lease_lost_mid_callback_parks_exactly_once(self):
        self._short_lease_processor().process(make_event(),
                                              contact_ref="contact-1")
        key = fulfillment_key()
        executed = []

        def slow_executor(payload):
            time.sleep(0.3)  # outlive the 0.05s lease, then succeed
            executed.append(payload)

        proc = self._short_lease_processor()
        self.assertEqual(proc.fulfill(key, slow_executor),
                         "parked_unknown")
        self.assertEqual(len(executed), 1)
        self.assertEqual(self.store.get_action(key)["state"], "unknown")
        # no blind retry: without a reconciler the park stands and the
        # executor never runs again
        self.assertEqual(proc.fulfill(key, slow_executor),
                         "parked_unknown")
        self.assertEqual(len(executed), 1)

    def test_lost_ack_reconcile_is_single_effect(self):
        self._short_lease_processor().process(make_event(),
                                              contact_ref="contact-1")
        key = fulfillment_key()
        executed = []

        def slow_executor(payload):
            time.sleep(0.3)  # effect may have landed; ack window lost
            executed.append(payload)

        proc = self._short_lease_processor()
        self.assertEqual(proc.fulfill(key, slow_executor),
                         "parked_unknown")
        # reconciler confirms the remote effect landed: done without a
        # second execution
        self.assertEqual(
            proc.fulfill(key, lambda p: executed.append(p),
                         reconcile=lambda p: True),
            "reconciled_done")
        self.assertEqual(len(executed), 1)
        self.assertEqual(self.store.get_action(key)["state"], "done")


class BundlingPreservedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.tmp.name) / "bd.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_multi_entitlement_line_grants_all_with_one_effect(self):
        # the stable idempotency key is constant across retries,
        # workers, and restarts
        self.assertEqual(effect_resource_for_tag(TXN),
                         f"effect:apply_verified_purchase_tag:{TXN}")
        self.assertEqual(
            effect_resource_for_action("initiate_fulfillment", TXN,
                                       "li-m"),
            "effect:initiate_fulfillment:txn-takeover:li-m")
        applier = RecordingApplier()
        proc = DurableProcessor(self.store, tag_applier=applier,
                                purchase_tag=TAG)
        out = proc.process(
            make_event([line("li-m", "main", ["ent-a", "ent-b"])]),
            contact_ref="contact-1")
        self.assertEqual(out["result"], "processed")
        self.assertEqual(self.store.active_entitlements(TENANT),
                         ["ent-a", "ent-b"])
        self.assertEqual(len(applier.calls), 1)
        self.assertEqual(self.store.get_action(tag_key())["state"],
                         "done")
        # replay creates no new effect
        replay = proc.process(
            make_event([line("li-m", "main", ["ent-a", "ent-b"])],
                       event_id="evt-tk-2"),
            contact_ref="contact-1")
        self.assertEqual(replay["actions_created"], 0)
        self.assertEqual(len(applier.calls), 1)


if __name__ == "__main__":
    unittest.main()
