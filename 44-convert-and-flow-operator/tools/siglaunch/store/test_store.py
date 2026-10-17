"""S44-05 durable store proofs: concurrency, idempotency, fencing.

These prove the production store's semantics (DESIGN-S44-02-03-05-v1.md
section 3) against a real SQLite file, including MULTI-PROCESS claims —
the property the in-memory L1 model could not prove.
"""
import multiprocessing as mp
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from store import Store

KEY = ("T1", "txn-1", "li-m", "grant_access", "v1")


def _claim_worker(db_path, key, result_queue):
    store = Store(db_path)
    result_queue.put(store.claim_action(key, {"entitlement": "ent-main"}))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "s44.db")
        self.store = Store(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_duplicate_event_returns_original(self):
        ev = {"event_id": "e1", "payment_status": "succeeded"}
        self.assertTrue(self.store.record_event_if_unseen("T1", "ghl", "e1", ev))
        self.assertFalse(self.store.record_event_if_unseen("T1", "ghl", "e1", ev))
        # same event id under another tenant is a different record (§ identity)
        self.assertTrue(self.store.record_event_if_unseen("T2", "ghl", "e1", ev))
        self.assertEqual(self.store.get_event("T1", "ghl", "e1"), ev)

    def test_thread_claim_single_winner(self):
        results = []
        barrier = threading.Barrier(16)

        def worker():
            barrier.wait()
            results.append(self.store.claim_action(KEY, {"entitlement": "e"}))

        threads = [threading.Thread(target=worker) for _ in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        winners = [r for r in results if r is None]
        self.assertEqual(len(winners), 1)
        self.assertEqual(self.store.get_action(KEY)["state"], "claimed")

    def test_process_claim_single_winner(self):
        ctx = mp.get_context("fork")
        queue = ctx.Queue()
        procs = [ctx.Process(target=_claim_worker,
                             args=(self.db, KEY, queue)) for _ in range(8)]
        for p in procs:
            p.start()
        results = [queue.get() for _ in procs]
        for p in procs:
            p.join()
        winners = [r for r in results if r is None]
        self.assertEqual(len(winners), 1,
                         "exactly one process may win the claim")

    def test_unknown_parks_and_blocks_replay(self):
        self.assertIsNone(self.store.claim_action(KEY, {"entitlement": "e"}))
        self.store.mark_action(KEY, "unknown", evidence_ref="readback/timeout")
        again = self.store.claim_action(KEY, {"entitlement": "e"})
        self.assertIsNotNone(again)
        self.assertEqual(again["state"], "unknown")
        parked = self.store.unknown_actions("T1")
        self.assertEqual(len(parked), 1)
        self.assertEqual(parked[0]["evidence_ref"], "readback/timeout")
        # reconciliation is explicit: only a mark to done clears the park
        self.store.mark_action(KEY, "done", evidence_ref="export/verified")
        self.assertEqual(self.store.unknown_actions("T1"), [])
        self.assertEqual(self.store.get_action(KEY)["state"], "done")

    def test_request_version_monotonic(self):
        self.assertTrue(self.store.put_request("r1", 1, "T1", "received", None))
        self.assertTrue(self.store.put_request(
            "r1", 2, "T1", "complete", {"status_claimed": "verified"}))
        # a superseded version write is refused, receipt untouched
        self.assertFalse(self.store.put_request(
            "r1", 1, "T1", "received", None))
        got = self.store.get_request("r1")
        self.assertEqual(got["request_version"], 2)
        self.assertEqual(got["receipt"], {"status_claimed": "verified"})

    def test_lease_fencing(self):
        t1 = self.store.acquire_lease("T1", "location:L1", "box-a")
        self.assertEqual(t1, 1)
        # a second holder cannot take a live lease
        self.assertIsNone(self.store.acquire_lease("T1", "location:L1", "box-b"))
        # same-holder renewal keeps the token and stays valid
        self.assertEqual(self.store.acquire_lease("T1", "location:L1", "box-a"), 1)
        self.assertTrue(self.store.check_fencing("T1", "location:L1", "box-a", 1))
        # release does NOT reset the token sequence: the next acquisition
        # gets a higher token (monotonic across the resource's lifetime),
        # and the released holder's old token is fenced out
        self.store.release_lease("T1", "location:L1", "box-a", 1)
        t3 = self.store.acquire_lease("T1", "location:L1", "box-b")
        self.assertEqual(t3, 2)
        self.assertFalse(self.store.check_fencing("T1", "location:L1", "box-a", 1))
        self.assertTrue(self.store.check_fencing("T1", "location:L1", "box-b", 2))
        # expiry path: a short-lived lease lapses, takeover bumps the token
        t4 = self.store.acquire_lease("T1", "location:L2", "box-a",
                                      ttl_seconds=0.01)
        self.assertEqual(t4, 1)
        time.sleep(0.03)
        t5 = self.store.acquire_lease("T1", "location:L2", "box-b")
        self.assertEqual(t5, 2)
        self.assertFalse(self.store.check_fencing("T1", "location:L2",
                                                  "box-a", t4))

    def test_tenant_isolation_actions(self):
        other = ("T2",) + KEY[1:]
        self.assertIsNone(self.store.claim_action(KEY, {"entitlement": "e"}))
        self.assertIsNone(self.store.claim_action(other, {"entitlement": "e"}))


if __name__ == "__main__":
    unittest.main()
