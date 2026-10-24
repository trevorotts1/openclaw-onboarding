#!/usr/bin/env python3
"""Tests for collection_lock.py (T-11, DATA-CONTRACTS 1 and 4).

Real parallel processes, not threads: every concurrency case spawns child
interpreters that race on the same SQLite database after a barrier file
appears.

Run from the skill root:
  python3 -m unittest discover -s tools/tests -p 'test_*.py'
or:
  python3 tools/tests/test_collection_lock.py
"""

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

import collection_lock as cl  # noqa: E402
import tenant_identity as ti  # noqa: E402


def _emit(cfg, payload):
    with open(cfg["out"], "a") as handle:
        handle.write(json.dumps(payload) + "\n")
        handle.flush()


def _worker(cfg_path):
    with open(cfg_path) as handle:
        cfg = json.load(handle)

    ident = ti.TenantIdentity(cfg["db"])
    try:
        ident.register_tenant(cfg["tenant"])
    except Exception:
        pass
    lock = cl.CollectionLock(ident)

    start = Path(cfg["start"])
    deadline = time.time() + 30
    while not start.exists():
        if time.time() > deadline:
            _emit(cfg, {"error": "barrier timeout"})
            return 3
        time.sleep(0.001)

    tenant = cfg["tenant"]
    contact = cfg["contact"]
    seq = cfg["seq"]
    mode = cfg["mode"]

    if mode == "capture_partial":
        store = cl.CaptureStore(lock)
        store.begin(tenant, contact, seq, cfg["capture"], cfg["steps"])
        for index in range(1, int(cfg["advance_to"]) + 1):
            store.advance(
                tenant,
                contact,
                seq,
                cfg["capture"],
                index,
                {"step": cfg["steps"][index - 1]},
            )
        state = store.get(tenant, contact, seq, cfg["capture"])
        _emit(cfg, {"state": state["state"], "cursor": state["cursor"]})
        return 0

    if mode == "capture_resume":
        store = cl.CaptureStore(lock)
        first = store.begin(tenant, contact, seq, cfg["capture"], cfg["steps"])
        executed = []
        for index in range(first["cursor"] + 1, len(cfg["steps"]) + 1):
            store.advance(
                tenant,
                contact,
                seq,
                cfg["capture"],
                index,
                {"step": cfg["steps"][index - 1]},
            )
            executed.append(cfg["steps"][index - 1])
        store.complete(tenant, contact, seq, cfg["capture"])
        state = store.get(tenant, contact, seq, cfg["capture"])
        _emit(
            cfg,
            {
                "resumed_from": first["cursor"],
                "executed": executed,
                "state": state["state"],
                "cursor": state["cursor"],
            },
        )
        return 0

    if mode == "acquire":
        lease = lock.acquire(
            tenant, contact, seq, cfg["owner"], float(cfg["lease"])
        )
    elif mode == "wait":
        lease = lock.acquire_or_wait(
            tenant,
            contact,
            seq,
            cfg["owner"],
            float(cfg["lease"]),
            timeout=float(cfg["wait"]),
        )
    else:
        _emit(cfg, {"error": "unknown mode %r" % (mode,)})
        return 2

    result = {
        "owner": cfg["owner"],
        "granted": lease.granted,
        "reason": lease.reason,
        "fence": lease.fence,
    }
    if lease.granted:
        result["wrote"] = lock.record_effect(
            tenant,
            contact,
            seq,
            cfg["owner"],
            lease.fence,
            "send:" + cfg["owner"],
        )
    _emit(cfg, result)
    return 0


class LockTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self._tmp.name, "identity.sqlite3")
        self.ident = ti.TenantIdentity(self.db)
        self.ident.register_tenant("tenant-a")
        self.ident.register_tenant("tenant-b")
        self.cid = self.ident.bind("tenant-a", [("fb_psid", "fb-a", True)])
        self.lock = cl.CollectionLock(self.ident)

    def tearDown(self):
        self._tmp.cleanup()

    # -- process harness -------------------------------------------------

    def _run_jobs(self, jobs):
        token = uuid.uuid4().hex
        start = os.path.join(self._tmp.name, "start-" + token)
        out = os.path.join(self._tmp.name, "out-" + token + ".jsonl")
        cfgdir = tempfile.mkdtemp(dir=self._tmp.name)
        procs = []
        for index, job in enumerate(jobs):
            cfg = dict(job)
            cfg.update(
                {
                    "db": self.db,
                    "tenant": "tenant-a",
                    "contact": self.cid,
                    "seq": "seq-1",
                    "out": out,
                    "start": start,
                }
            )
            path = os.path.join(cfgdir, "job-%02d.json" % index)
            with open(path, "w") as handle:
                json.dump(cfg, handle)
            procs.append(
                subprocess.Popen(
                    [sys.executable, os.path.abspath(__file__), "--worker", path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            )
        Path(start).write_text("go", encoding="utf-8")
        for proc in procs:
            stdout, stderr = proc.communicate(timeout=180)
            if proc.returncode != 0:
                self.fail(
                    "worker failed rc=%s\nstdout=%s\nstderr=%s"
                    % (proc.returncode, stdout, stderr)
                )
        with open(out) as handle:
            results = [json.loads(line) for line in handle if line.strip()]
        self.assertEqual(len(results), len(jobs), results)
        return results

    def _jobs(self, mode, count, **extra):
        jobs = []
        for index in range(count):
            job = {
                "mode": mode,
                "owner": "%s-%02d" % (mode, index),
                "lease": 60.0,
                "wait": 0.15,
            }
            job.update(extra)
            jobs.append(job)
        return jobs

    def _effect_count(self):
        conn = sqlite3.connect(self.db)
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM collection_effects"
            ).fetchone()[0]
        finally:
            conn.close()


class TestConcurrency(LockTestBase):
    def test_only_one_concurrent_collector_wins(self):
        results = self._run_jobs(self._jobs("acquire", 8))
        winners = [r for r in results if r["granted"]]
        self.assertEqual(len(winners), 1, results)
        self.assertTrue(winners[0]["wrote"])
        losers = [r for r in results if not r["granted"]]
        self.assertEqual(len(losers), 7)
        self.assertEqual({r["reason"] for r in losers}, {"held"})
        self.assertEqual(self._effect_count(), 1)

    def test_losers_defer_instead_of_duplicating_a_send(self):
        results = self._run_jobs(self._jobs("wait", 6, lease=5.0, wait=0.15))
        winners = [r for r in results if r["granted"]]
        self.assertEqual(len(winners), 1, results)
        deferred = [r for r in results if not r["granted"]]
        self.assertEqual(len(deferred), 5)
        self.assertEqual({r["reason"] for r in deferred}, {"deferred"})
        self.assertEqual(self._effect_count(), 1)

    def test_expired_lease_requires_reconciliation_before_successor_writes(self):
        first = self.lock.acquire(
            "tenant-a", self.cid, "seq-1", "dead-writer", lease_seconds=0.05
        )
        self.assertTrue(first.granted)
        self.assertEqual(first.fence, 1)
        self.assertTrue(
            self.lock.record_effect(
                "tenant-a", self.cid, "seq-1", "dead-writer", first.fence,
                "send:dead-writer",
            )
        )
        time.sleep(0.15)

        successor_attempts = self._run_jobs(
            [
                {
                    "mode": "acquire",
                    "owner": "successor",
                    "lease": 60.0,
                    "wait": 0.15,
                }
            ]
        )
        attempt = successor_attempts[0]
        self.assertFalse(attempt["granted"], attempt)
        self.assertEqual(attempt["reason"], "reconcile_required")
        self.assertEqual(self._effect_count(), 1)

        reconciled = self.lock.reconcile(
            "tenant-a", self.cid, "seq-1", "successor", first.fence
        )
        self.assertEqual(reconciled.reason, "reconciled")

        second = self.lock.acquire(
            "tenant-a", self.cid, "seq-1", "successor", lease_seconds=60
        )
        self.assertTrue(second.granted)
        self.assertEqual(second.fence, first.fence + 1)

        with self.assertRaises(cl.StaleWriter):
            self.lock.record_effect(
                "tenant-a", self.cid, "seq-1", "dead-writer", first.fence,
                "send:dead-writer-again",
            )
        self.assertTrue(
            self.lock.record_effect(
                "tenant-a", self.cid, "seq-1", "successor", second.fence,
                "send:successor",
            )
        )
        self.assertEqual(self._effect_count(), 2)


class TestLockSemantics(LockTestBase):
    def test_release_hands_over_with_a_higher_fence(self):
        first = self.lock.acquire("tenant-a", self.cid, "seq-1", "owner-1", 60)
        self.assertTrue(self.lock.release("tenant-a", self.cid, "seq-1", "owner-1", first.fence))
        second = self.lock.acquire("tenant-a", self.cid, "seq-1", "owner-2", 60)
        self.assertTrue(second.granted)
        self.assertEqual(second.fence, first.fence + 1)
        third = self.lock.acquire("tenant-a", self.cid, "seq-1", "owner-3", 60)
        self.assertFalse(third.granted)

    def test_same_owner_reacquire_renews_without_bumping_the_fence(self):
        first = self.lock.acquire("tenant-a", self.cid, "seq-1", "owner-1", 60)
        again = self.lock.acquire("tenant-a", self.cid, "seq-1", "owner-1", 60)
        self.assertTrue(again.granted)
        self.assertEqual(again.fence, first.fence)
        self.assertEqual(again.reason, "renewed")

    def test_different_sequences_do_not_block_each_other(self):
        one = self.lock.acquire("tenant-a", self.cid, "seq-1", "owner-1", 60)
        two = self.lock.acquire("tenant-a", self.cid, "seq-2", "owner-2", 60)
        self.assertTrue(one.granted)
        self.assertTrue(two.granted)

    def test_tenants_do_not_share_a_lock(self):
        cid_b = self.ident.bind("tenant-b", [("fb_psid", "fb-b", True)])
        one = self.lock.acquire("tenant-a", self.cid, "seq-1", "owner-a", 60)
        two = self.lock.acquire("tenant-b", cid_b, "seq-1", "owner-b", 60)
        self.assertTrue(one.granted)
        self.assertTrue(two.granted)
        self.assertEqual(one.fence, 1)
        self.assertEqual(two.fence, 1)

    def test_lock_rejects_unknown_tenant_and_foreign_contact(self):
        cid_b = self.ident.bind("tenant-b", [("fb_psid", "fb-b", True)])
        with self.assertRaises(ti.UnknownTenant):
            self.lock.acquire("tenant-z", self.cid, "seq-1", "owner", 60)
        with self.assertRaises(ti.VerificationError):
            self.lock.acquire("tenant-a", cid_b, "seq-1", "owner", 60)

    def test_reconcile_requires_the_exact_fence(self):
        first = self.lock.acquire("tenant-a", self.cid, "seq-1", "owner-1", 0.01)
        time.sleep(0.05)
        self.lock.acquire("tenant-a", self.cid, "seq-1", "owner-2", 60)
        with self.assertRaises(cl.StaleWriter):
            self.lock.reconcile("tenant-a", self.cid, "seq-1", "owner-2", first.fence + 5)

    def test_stale_fence_cannot_write_after_handover(self):
        first = self.lock.acquire("tenant-a", self.cid, "seq-1", "owner-1", 60)
        self.lock.release("tenant-a", self.cid, "seq-1", "owner-1", first.fence)
        second = self.lock.acquire("tenant-a", self.cid, "seq-1", "owner-2", 60)
        with self.assertRaises(cl.StaleWriter):
            self.lock.record_effect(
                "tenant-a", self.cid, "seq-1", "owner-1", first.fence, "send:x"
            )
        self.assertTrue(
            self.lock.record_effect(
                "tenant-a", self.cid, "seq-1", "owner-2", second.fence, "send:x"
            )
        )
        # The same effect id under the same collection is idempotent.
        self.assertFalse(
            self.lock.record_effect(
                "tenant-a", self.cid, "seq-1", "owner-2", second.fence, "send:x"
            )
        )


class TestCaptureState(LockTestBase):
    STEPS = ["step1", "step2", "step3", "step4"]

    def test_partial_capture_resumes_in_a_new_process_never_restarts(self):
        first = self._run_jobs(
            [
                {
                    "mode": "capture_partial",
                    "owner": "capture-a",
                    "capture": "cap-1",
                    "steps": self.STEPS,
                    "advance_to": 2,
                }
            ]
        )[0]
        self.assertEqual(first["state"], "in_progress")
        self.assertEqual(first["cursor"], 2)

        resumed = self._run_jobs(
            [
                {
                    "mode": "capture_resume",
                    "owner": "capture-b",
                    "capture": "cap-1",
                    "steps": self.STEPS,
                }
            ]
        )[0]
        self.assertEqual(resumed["resumed_from"], 2)
        self.assertEqual(resumed["executed"], ["step3", "step4"])
        self.assertEqual(resumed["state"], "complete")
        self.assertEqual(resumed["cursor"], 4)

    def test_rejected_capture_stays_rejected_and_cannot_advance(self):
        store = cl.CaptureStore(self.lock)
        store.begin("tenant-a", self.cid, "seq-1", "cap-2", self.STEPS)
        store.reject("tenant-a", self.cid, "seq-1", "cap-2", "client declined")
        with self.assertRaises(cl.CaptureRejected):
            store.advance("tenant-a", self.cid, "seq-1", "cap-2", 1)
        again = store.begin("tenant-a", self.cid, "seq-1", "cap-2", self.STEPS)
        self.assertEqual(again["state"], "rejected")
        self.assertEqual(again["rejection_reason"], "client declined")
        self.assertEqual(again["cursor"], 0)

    def test_capture_cursor_never_rewinds(self):
        store = cl.CaptureStore(self.lock)
        store.begin("tenant-a", self.cid, "seq-1", "cap-3", self.STEPS)
        store.advance("tenant-a", self.cid, "seq-1", "cap-3", 2)
        with self.assertRaises(cl.CaptureConflict):
            store.advance("tenant-a", self.cid, "seq-1", "cap-3", 2)
        with self.assertRaises(cl.CaptureConflict):
            store.advance("tenant-a", self.cid, "seq-1", "cap-3", 1)

    def test_capture_rejects_a_foreign_contact(self):
        cid_b = self.ident.bind("tenant-b", [("fb_psid", "fb-b", True)])
        store = cl.CaptureStore(self.lock)
        with self.assertRaises(ti.VerificationError):
            store.begin("tenant-a", cid_b, "seq-1", "cap-4", self.STEPS)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--worker":
        sys.exit(_worker(sys.argv[2]))
    unittest.main()
