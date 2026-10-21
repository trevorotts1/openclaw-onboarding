"""Audit lane L08 (UL-002) store proofs: per-entitlement right claims.

The durable grant key carries the entitlement identity:
(tenant_id, txn_ref, line_ref, action_type, entitlement). Two
entitlements on one line are two claims, so a replay/restart/partial
recovery can reconcile the event's expected rights against the book
without repeating an external effect.

Synthetic-local only: a real SQLite file under a temporary directory,
fake tenant/transaction/entitlement strings, no network, no secrets.
"""
import multiprocessing as mp
import sqlite3
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from store import Store

T = "T1"
TXN = "txn-1"
LINE = "li-m"
RIGHT_A = (T, TXN, LINE, "grant_access", "ent-a")
RIGHT_B = (T, TXN, LINE, "grant_access", "ent-b")
ACTION_KEY = (T, TXN, LINE, "grant_access", "v1")


def _right_claim_worker(db_path, key, result_queue):
    store = Store(db_path)
    result_queue.put(store.claim_right(key))


class RightClaimTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / "l08.db")
        self.store = Store(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_entitlement_identity_is_part_of_the_grant_key(self):
        # the same line, same action, two entitlements: two claims
        self.assertIsNone(self.store.claim_right(RIGHT_A))
        self.assertIsNone(self.store.claim_right(RIGHT_B))
        self.assertEqual(self.store.get_right(RIGHT_A)["state"], "claimed")
        self.assertEqual(self.store.get_right(RIGHT_B)["state"], "claimed")
        # a repeat of the first key is the existing record, not a winner
        again = self.store.claim_right(RIGHT_A)
        self.assertIsNotNone(again)
        self.assertEqual(again["state"], "claimed")
        # and the line-only action key is a separate namespace
        self.assertIsNone(self.store.claim_action(ACTION_KEY, {}))

    def test_right_claims_survive_restart(self):
        self.assertIsNone(self.store.claim_right(RIGHT_A))
        self.store.mark_right(RIGHT_A, "done", evidence_ref="readback/x")
        reopened = Store(self.db)
        record = reopened.claim_right(RIGHT_A)
        self.assertEqual(record["state"], "done")
        self.assertEqual(record["evidence_ref"], "readback/x")

    def test_right_claim_thread_single_winner(self):
        results = []
        barrier = threading.Barrier(16)

        def worker():
            barrier.wait()
            results.append(self.store.claim_right(RIGHT_A))

        threads = [threading.Thread(target=worker) for _ in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(len([r for r in results if r is None]), 1)

    def test_right_claim_process_single_winner(self):
        ctx = mp.get_context("fork")
        queue = ctx.Queue()
        procs = [ctx.Process(target=_right_claim_worker,
                             args=(self.db, RIGHT_A, queue))
                 for _ in range(6)]
        for p in procs:
            p.start()
        results = [queue.get() for _ in procs]
        for p in procs:
            p.join()
        self.assertEqual(len([r for r in results if r is None]), 1,
                         "exactly one process may win the right claim")

    def test_unknown_right_parks_and_blocks_replay(self):
        self.assertIsNone(self.store.claim_right(RIGHT_A))
        self.store.mark_right(RIGHT_A, "unknown",
                              evidence_ref="readback/ambiguous")
        record = self.store.claim_right(RIGHT_A)
        self.assertEqual(record["state"], "unknown")
        self.assertEqual(record["evidence_ref"], "readback/ambiguous")

    def test_right_states_are_tenant_scoped(self):
        other = ("T2",) + RIGHT_A[1:]
        self.assertIsNone(self.store.claim_right(RIGHT_A))
        self.assertIsNone(self.store.claim_right(other))
        self.store.mark_right(RIGHT_A, "done")
        self.assertEqual(self.store.get_right(other)["state"], "claimed")

    def test_reopen_action_only_reopens_a_parked_action(self):
        self.assertIsNone(self.store.claim_action(ACTION_KEY, {}))
        # claimed (never executed yet) is not a park: no reopen
        self.assertFalse(self.store.reopen_action(ACTION_KEY))
        self.store.mark_action(ACTION_KEY, "unknown")
        self.assertTrue(self.store.reopen_action(ACTION_KEY))
        self.assertEqual(self.store.get_action(ACTION_KEY)["state"],
                         "claimed")
        self.store.mark_action(ACTION_KEY, "done")
        self.assertFalse(self.store.reopen_action(ACTION_KEY))
        self.assertEqual(self.store.get_action(ACTION_KEY)["state"], "done")

    def test_entitlement_state_reports_recorded_rights(self):
        self.assertIsNone(self.store.entitlement_state(T, LINE, "ent-a"))
        self.store.grant_entitlement(T, LINE, "ent-a")
        self.assertEqual(self.store.entitlement_state(T, LINE, "ent-a"),
                         "active")
        self.store.revoke_entitlement(T, LINE, "ent-a")
        self.assertEqual(self.store.entitlement_state(T, LINE, "ent-a"),
                         "revoked")

    def test_right_claims_table_is_added_to_an_existing_database(self):
        # an older database (created before this table existed) gains it
        # on open: the schema is additive, no replacement store
        legacy = str(Path(self.tmp.name) / "legacy.db")
        conn = sqlite3.connect(legacy)
        conn.execute("CREATE TABLE actions (tenant_id TEXT)")
        conn.commit()
        conn.close()
        store = Store(legacy)
        self.assertIsNone(store.claim_right(RIGHT_A))
        conn = sqlite3.connect(legacy)
        try:
            names = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()
        self.assertIn("right_claims", names)


if __name__ == "__main__":
    unittest.main()
