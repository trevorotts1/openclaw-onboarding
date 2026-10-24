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

    if mode == "capture_unfenced":
        # Deliberately never acquires the collection lock: the capture
        # mutators must refuse before the step runs.
        store = cl.CaptureStore(lock)
        try:
            store.begin(
                tenant,
                contact,
                seq,
                cfg["capture"],
                cfg["steps"],
                owner_id=cfg["owner"],
                fence=int(cfg["fence"]),
            )
        except Exception as exc:
            _emit(
                cfg,
                {
                    "owner": cfg["owner"],
                    "begin": "refused:" + type(exc).__name__,
                    "ran": None,
                },
            )
            return 0
        # begin() handed control back, so the step would run here.
        _emit(
            cfg,
            {"owner": cfg["owner"], "begin": "ok", "ran": cfg["steps"][0]},
        )
        return 0

    if mode in ("capture_partial", "capture_resume"):
        store = cl.CaptureStore(lock)
        lease = lock.acquire(tenant, contact, seq, cfg["owner"], 60.0)
        if not lease.granted:
            _emit(cfg, {"error": "lock not granted: %s" % (lease.reason,)})
            return 4
        owner = cfg["owner"]
        fence = lease.fence

    if mode == "capture_partial":
        store.begin(
            tenant,
            contact,
            seq,
            cfg["capture"],
            cfg["steps"],
            owner_id=owner,
            fence=fence,
        )
        for index in range(1, int(cfg["advance_to"]) + 1):
            store.advance(
                tenant,
                contact,
                seq,
                cfg["capture"],
                index,
                {"step": cfg["steps"][index - 1]},
                owner_id=owner,
                fence=fence,
            )
        state = store.get(tenant, contact, seq, cfg["capture"])
        lock.release(tenant, contact, seq, owner, fence)
        _emit(cfg, {"state": state["state"], "cursor": state["cursor"]})
        return 0

    if mode == "capture_resume":
        first = store.begin(
            tenant,
            contact,
            seq,
            cfg["capture"],
            cfg["steps"],
            owner_id=owner,
            fence=fence,
        )
        executed = []
        for index in range(first["cursor"] + 1, len(cfg["steps"]) + 1):
            store.advance(
                tenant,
                contact,
                seq,
                cfg["capture"],
                index,
                {"step": cfg["steps"][index - 1]},
                owner_id=owner,
                fence=fence,
            )
            executed.append(cfg["steps"][index - 1])
        store.complete(
            tenant, contact, seq, cfg["capture"], owner_id=owner, fence=fence
        )
        state = store.get(tenant, contact, seq, cfg["capture"])
        lock.release(tenant, contact, seq, owner, fence)
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
            cfg.get("effect") or ("send:" + cfg["owner"]),
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

    def _held(self, owner="capture-owner", seq="seq-1", lease=60.0):
        lease_result = self.lock.acquire(
            "tenant-a", self.cid, seq, owner, lease
        )
        self.assertTrue(lease_result.granted, lease_result)
        return lease_result

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
        lease = self._held()
        store = cl.CaptureStore(self.lock)
        store.begin(
            "tenant-a", self.cid, "seq-1", "cap-2", self.STEPS,
            owner_id=lease.owner_id, fence=lease.fence,
        )
        store.reject(
            "tenant-a", self.cid, "seq-1", "cap-2", "client declined",
            owner_id=lease.owner_id, fence=lease.fence,
        )
        with self.assertRaises(cl.CaptureRejected):
            store.advance(
                "tenant-a", self.cid, "seq-1", "cap-2", 1,
                owner_id=lease.owner_id, fence=lease.fence,
            )
        again = store.begin(
            "tenant-a", self.cid, "seq-1", "cap-2", self.STEPS,
            owner_id=lease.owner_id, fence=lease.fence,
        )
        self.assertEqual(again["state"], "rejected")
        self.assertEqual(again["rejection_reason"], "client declined")
        self.assertEqual(again["cursor"], 0)

    def test_capture_cursor_never_rewinds(self):
        lease = self._held()
        store = cl.CaptureStore(self.lock)
        store.begin(
            "tenant-a", self.cid, "seq-1", "cap-3", self.STEPS,
            owner_id=lease.owner_id, fence=lease.fence,
        )
        store.advance(
            "tenant-a", self.cid, "seq-1", "cap-3", 2,
            owner_id=lease.owner_id, fence=lease.fence,
        )
        with self.assertRaises(cl.CaptureConflict):
            store.advance(
                "tenant-a", self.cid, "seq-1", "cap-3", 2,
                owner_id=lease.owner_id, fence=lease.fence,
            )
        with self.assertRaises(cl.CaptureConflict):
            store.advance(
                "tenant-a", self.cid, "seq-1", "cap-3", 1,
                owner_id=lease.owner_id, fence=lease.fence,
            )

    def test_capture_rejects_a_foreign_contact(self):
        cid_b = self.ident.bind("tenant-b", [("fb_psid", "fb-b", True)])
        lease = self._held()
        store = cl.CaptureStore(self.lock)
        with self.assertRaises(ti.VerificationError):
            store.begin(
                "tenant-a", cid_b, "seq-1", "cap-4", self.STEPS,
                owner_id=lease.owner_id, fence=lease.fence,
            )


class TestCaptureFencing(LockTestBase):
    """D4: capture mutation must require a valid lock fence."""

    STEPS = ["step1", "step2", "step3", "step4"]

    def test_capture_mutation_refuses_before_any_step_without_the_lock(self):
        store = cl.CaptureStore(self.lock)
        for method, args in (
            ("begin", ("cap-f", self.STEPS)),
            ("advance", ("cap-f", 1)),
            ("complete", ("cap-f",)),
            ("reject", ("cap-f",)),
        ):
            with self.assertRaises(cl.StaleWriter):
                getattr(store, method)(
                    "tenant-a", self.cid, "seq-1", *args,
                    owner_id="nobody", fence=0,
                )
        self.assertIsNone(store.get("tenant-a", self.cid, "seq-1", "cap-f"))

    def test_stale_fence_is_refused_after_a_handover(self):
        first = self.lock.acquire("tenant-a", self.cid, "seq-1", "owner-1", 60)
        store = cl.CaptureStore(self.lock)
        store.begin(
            "tenant-a", self.cid, "seq-1", "cap-h", self.STEPS,
            owner_id=first.owner_id, fence=first.fence,
        )
        self.lock.release(
            "tenant-a", self.cid, "seq-1", "owner-1", first.fence
        )
        second = self.lock.acquire("tenant-a", self.cid, "seq-1", "owner-2", 60)
        with self.assertRaises(cl.StaleWriter):
            store.advance(
                "tenant-a", self.cid, "seq-1", "cap-h", 1,
                owner_id=first.owner_id, fence=first.fence,
            )
        store.advance(
            "tenant-a", self.cid, "seq-1", "cap-h", 1,
            owner_id=second.owner_id, fence=second.fence,
        )
        self.assertEqual(
            store.get("tenant-a", self.cid, "seq-1", "cap-h")["cursor"], 1
        )

    def test_two_unfenced_workers_never_run_a_step(self):
        results = self._run_jobs(
            [
                {
                    "mode": "capture_unfenced",
                    "owner": "worker-%02d" % index,
                    "capture": "cap-race",
                    "steps": ["collect-answers"],
                    "fence": 0,
                }
                for index in range(2)
            ]
        )
        ran = [r for r in results if r.get("ran")]
        self.assertEqual(ran, [], results)
        self.assertEqual(
            {r["begin"] for r in results},
            {"refused:StaleWriter"},
            results,
        )
        self.assertIsNone(
            cl.CaptureStore(self.lock).get(
                "tenant-a", self.cid, "seq-1", "cap-race"
            )
        )


class TestPrematureComplete(LockTestBase):
    """D5: complete() must refuse while steps remain."""

    STEPS = ["s1", "s2", "s3", "s4"]

    def _partial(self, capture="cap-p"):
        lease = self.lock.acquire("tenant-a", self.cid, "seq-1", "owner-1", 60)
        store = cl.CaptureStore(self.lock)
        store.begin(
            "tenant-a", self.cid, "seq-1", capture, self.STEPS,
            owner_id=lease.owner_id, fence=lease.fence,
        )
        store.advance(
            "tenant-a", self.cid, "seq-1", capture, 2, {"half": True},
            owner_id=lease.owner_id, fence=lease.fence,
        )
        return lease, store

    def test_complete_refuses_while_steps_remain(self):
        lease, store = self._partial()
        with self.assertRaises(cl.CaptureIncomplete) as raised:
            store.complete(
                "tenant-a", self.cid, "seq-1", "cap-p",
                owner_id=lease.owner_id, fence=lease.fence,
            )
        self.assertIn("2 of 4", str(raised.exception))
        state = store.get("tenant-a", self.cid, "seq-1", "cap-p")
        self.assertEqual(state["state"], "in_progress")
        self.assertEqual(state["cursor"], 2)

    def test_premature_complete_leaves_the_capture_resumable(self):
        lease, store = self._partial("cap-q")
        with self.assertRaises(cl.CaptureIncomplete):
            store.complete(
                "tenant-a", self.cid, "seq-1", "cap-q",
                owner_id=lease.owner_id, fence=lease.fence,
            )
        store.advance(
            "tenant-a", self.cid, "seq-1", "cap-q", 3,
            owner_id=lease.owner_id, fence=lease.fence,
        )
        store.advance(
            "tenant-a", self.cid, "seq-1", "cap-q", 4,
            owner_id=lease.owner_id, fence=lease.fence,
        )
        done = store.complete(
            "tenant-a", self.cid, "seq-1", "cap-q",
            owner_id=lease.owner_id, fence=lease.fence,
        )
        self.assertEqual(done["state"], "complete")
        self.assertEqual(done["cursor"], 4)

    def test_reject_is_still_allowed_with_steps_remaining(self):
        lease, store = self._partial("cap-r")
        gone = store.reject(
            "tenant-a", self.cid, "seq-1", "cap-r", "client declined",
            owner_id=lease.owner_id, fence=lease.fence,
        )
        self.assertEqual(gone["state"], "rejected")
        self.assertEqual(gone["cursor"], 2)


class TestOwnerIdentity(LockTestBase):
    """D3: mutual exclusion must not rest on a caller-supplied string."""

    def test_two_processes_sharing_one_owner_string_are_mutually_exclusive(self):
        results = self._run_jobs(
            [
                {
                    "mode": "acquire",
                    "owner": "job-shared",
                    "effect": "send:job-%02d" % index,
                    "lease": 60.0,
                    "wait": 0.15,
                }
                for index in range(4)
            ]
        )
        self.assertEqual({r["owner"] for r in results}, {"job-shared"})
        winners = [r for r in results if r["granted"]]
        self.assertEqual(len(winners), 1, results)
        self.assertEqual(self._effect_count(), 1, results)
        conn = sqlite3.connect(self.db)
        try:
            effects = [
                row[0]
                for row in conn.execute(
                    "SELECT effect_id FROM collection_effects"
                    " ORDER BY effect_id"
                )
            ]
        finally:
            conn.close()
        self.assertEqual(len(effects), 1, effects)
        self.assertTrue(effects[0].startswith("send:job-"), effects)

    def test_owner_id_is_normalized_the_same_way_in_every_method(self):
        lease = self.lock.acquire("tenant-a", self.cid, "seq-1", "  owner-1  ", 60)
        self.assertTrue(lease.granted)
        self.assertTrue(
            self.lock.record_effect(
                "tenant-a", self.cid, "seq-1", "owner-1", lease.fence, "send:x"
            )
        )
        self.assertTrue(
            self.lock.renew(
                "tenant-a", self.cid, "seq-1", "  owner-1  ", lease.fence, 60
            ).granted
        )
        self.lock.assert_fence(
            "tenant-a", self.cid, "seq-1", " owner-1 ", lease.fence
        )
        self.assertTrue(
            self.lock.release(
                "tenant-a", self.cid, "seq-1", "owner-1", lease.fence
            )
        )

    def test_a_foreign_owner_label_cannot_write_with_this_owners_fence(self):
        lease = self.lock.acquire("tenant-a", self.cid, "seq-1", "owner-1", 60)
        with self.assertRaises(cl.StaleWriter):
            self.lock.record_effect(
                "tenant-a", self.cid, "seq-1", "owner-2", lease.fence, "send:x"
            )


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--worker":
        sys.exit(_worker(sys.argv[2]))
    unittest.main()
