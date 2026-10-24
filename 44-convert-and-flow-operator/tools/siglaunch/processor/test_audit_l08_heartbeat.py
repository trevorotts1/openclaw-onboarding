"""Audit lane L08 (UL-012): heartbeat lease renewal keeps a live owner.

Guarded completion already refuses a stale owner, so safety never depended
on the heartbeat. What was missing is liveness: a callback longer than the
lease TTL lost the lease mid-flight and parked as ``unknown`` even though
the worker was alive and still the logical owner. These tests pin the
renewal and its negative control against a real SQLite store with local
fakes only (no network, no live provider, no secrets):

  1. a tag callback that outlives the TTL completes ``done``;
  2. a fulfillment callback that outlives the TTL completes ``done``;
  3. with the heartbeat disabled, the same call parks ``unknown`` — so the
     mapping above is the heartbeat and not the timing.
"""
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "store"))

from processor import DurableProcessor, effect_resource_for_tag
from store import Store

TENANT = "T1"
TXN = "txn-heartbeat"
TAG = "siglaunch:purchased:main"
VERSION = "v1"
TTL = 0.15          # renew every 0.05s
SLOW = 0.6          # well past the TTL


class _NoHeartbeat:
    """Context manager that renews nothing — the pre-fix behaviour."""

    renewals = 0
    lost = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def make_event():
    return {
        "schema_version": "1.2",
        "tenant_id": TENANT, "location_id": "LOC1", "launch_id": "LN1",
        "provider": "ghl", "event_id": "evt-hb-1",
        "event_type": "purchase_observed",
        "native_order_ref": "ord-hb-1", "native_transaction_ref": TXN,
        "occurred_at": "2026-10-15T20:00:00Z",
        "received_at": "2026-10-15T20:00:05Z",
        "payment_status": "succeeded",
        "line_items": [{"native_line_ref": "li-m", "offer_id": "off-1",
                        "slot": "main", "currency": "USD",
                        "amount_minor": 1000,
                        "entitlement_ids": ["ent-main"]}],
        "evidence_ref": "readback/ord-hb-1",
        "test_only": True,
    }


def tag_key():
    return (TENANT, TXN, "*", "apply_verified_purchase_tag", VERSION)


def fulfillment_key():
    return (TENANT, TXN, "li-m", "initiate_fulfillment", VERSION)


def slow_applier():
    def apply(contact_ref, tag):
        time.sleep(SLOW)
    return apply


class HeartbeatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(str(Path(self.tmp.name) / "hb.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_tag_callback_past_ttl_completes_done(self):
        proc = DurableProcessor(self.store, tag_applier=slow_applier(),
                                purchase_tag=TAG, lease_ttl_seconds=TTL)
        out = proc.process(make_event(), contact_ref="contact-1")
        self.assertEqual(out["tag_state"], "done", out)
        self.assertEqual(self.store.get_action(tag_key())["state"], "done")

    def test_fulfillment_callback_past_ttl_completes_done(self):
        proc = DurableProcessor(self.store, lease_ttl_seconds=TTL)
        proc.process(make_event(), contact_ref="contact-1")
        executed = []

        def executor(payload):
            executed.append(payload)
            time.sleep(SLOW)

        out = DurableProcessor(self.store,
                               lease_ttl_seconds=TTL).fulfill(
            fulfillment_key(), executor)
        self.assertEqual(out, "done")
        self.assertEqual(len(executed), 1)
        self.assertEqual(self.store.get_action(fulfillment_key())["state"],
                         "done")

    def test_without_heartbeat_the_same_call_parks(self):
        proc = DurableProcessor(self.store, tag_applier=slow_applier(),
                                purchase_tag=TAG, lease_ttl_seconds=TTL)
        proc._heartbeat = lambda *a, **k: _NoHeartbeat()
        out = proc.process(make_event(), contact_ref="contact-1")
        self.assertEqual(out["tag_state"], "parked_unknown", out)
        self.assertEqual(self.store.get_action(tag_key())["state"],
                         "unknown")

    def test_renewal_extends_the_lease_past_its_first_expiry(self):
        proc = DurableProcessor(self.store, lease_ttl_seconds=TTL)
        resource = effect_resource_for_tag(TXN)
        holder = proc._holder()
        token, took_over = self.store.acquire_effect_lease(
            TENANT, resource, holder, ttl_seconds=TTL)
        self.assertFalse(took_over)
        with proc._heartbeat(TENANT, resource, holder, token) as beat:
            time.sleep(SLOW)
        self.assertGreater(beat.renewals, 0)
        self.assertFalse(beat.lost)
        self.assertTrue(
            self.store.check_fencing(TENANT, resource, holder, token),
            "the live owner still holds the lease after the original TTL")


if __name__ == "__main__":
    unittest.main()
