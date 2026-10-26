#!/usr/bin/env python3
"""Tests for T-12 durable processing, the common send gate and reconciliation.

Run from the skill root:
    python3 -m unittest discover -s tools/tests -p 'test_durable_processing.py' -v
or directly:
    python3 tools/tests/test_durable_processing.py

What is proven here, in the order DATA-CONTRACTS section 4 requires it:

  INBOX       the same provider event, delivered twice, has exactly one
              effect - across a restart and across two real processes.
              Identical bodies with different event ids are two events.

  OUTBOX      not_requested -> queued -> dispatched -> acknowledged -> completed
              with ACK and completion as separate persisted receipts; unknown,
              failed and canceled; legal transitions enforced.

  GATE        evaluated fresh on every dispatch AND retry; a gate that allowed
              at queue time but denies at dispatch time blocks; a verdict is
              never reused across attempts.

  CRASH       a real SIGKILL after the provider accepted and before the local
              receipt was written: the record becomes unknown, reconciliation
              resolves it, and the provider send log stays at exactly one line.

  CANCEL      a canceled action cannot be dispatched by a racing worker, proven
              with two real worker processes.

Two workers and the crash run in separate OS processes (`_proc_worker.py`);
the provider is a real append+fsync file on disk.
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
for p in (str(TOOLS_DIR),):
    if p not in sys.path:
        sys.path.insert(0, p)

from durable_store import (  # noqa: E402
    DurableStore,
    DurableStoreError,
    STATE_ACKNOWLEDGED,
    STATE_CANCELED,
    STATE_COMPLETED,
    STATE_DISPATCHED,
    STATE_NOT_REQUESTED,
    STATE_QUEUED,
    STATE_SUPPRESSED,
    STATE_UNKNOWN,
)
from outbound_gate import (  # noqa: E402
    GateError,
    ST_BLOCKED,
    ST_REFUSED_RACE,
    ST_SENT,
    dispatch,
    evaluate_gate,
)
from reconciliation import (  # noqa: E402
    R_APPLIED,
    R_IN_FLIGHT,
    R_NOT_APPLIED,
    R_NOT_NEEDED,
    R_UNKNOWN,
    needs_reconciliation,
    resolve_unknown,
    sweep_inflight,
)

WORKER = str(TESTS_DIR / "_proc_worker.py")


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t12-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.db = str(self.tmp / "store.sqlite")
        self.send_log = str(self.tmp / "provider-sends.log")
        self.effect_log = str(self.tmp / "effects.log")
        self.go = str(self.tmp / "go")

    # ── process helpers ────────────────────────────────────────────────────

    def _spawn(self, *args):
        return subprocess.Popen(
            [sys.executable, "-I", WORKER, *args, "--go-file", self.go],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env=dict(os.environ),
        )

    def _wait_for(self, path, timeout=30.0):
        deadline = time.time() + timeout
        while not Path(path).exists():
            if time.time() > deadline:
                raise AssertionError(f"timed out waiting for {path}")
            time.sleep(0.005)

    def _release(self):
        Path(self.go).write_text("go", encoding="utf-8")

    def _read_json(self, proc, timeout=60.0):
        out, err = proc.communicate(timeout=timeout)
        if proc.returncode != 0:
            raise AssertionError(
                f"worker failed rc={proc.returncode}\nstdout={out}\nstderr={err}")
        lines = [ln for ln in out.splitlines() if ln.strip()]
        self.assertTrue(lines, f"worker produced no JSON; stderr={err}")
        return json.loads(lines[-1])

    def _lines(self, path):
        p = Path(path)
        if not p.exists():
            return []
        return [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln]

    def _new_action(self, store, key="L", scope="person_directed"):
        kwargs = {}
        if scope == "person_directed":
            kwargs["canonical_contact_id"] = "contact-1"
        row, _ = store.create_intent(
            logical_intent_key=key, idempotency_key="idem-" + key,
            tenant_id="t1", scope=scope, content_sha256="content-hash", **kwargs)
        store.queue(row["action_id"])
        return row["action_id"]


# ══════════════════════════════════════════════════════════════════════════
# 1. INBOX DEDUPE
# ══════════════════════════════════════════════════════════════════════════

class TestInboxDedupe(_Base):
    def test_same_event_twice_one_effect_across_restart(self):
        store = DurableStore(self.db)
        first = store.admit_event(provider="ghl", tenant_id="t1",
                                  provider_event_id="evt-1", payload_sha256="h")
        self.assertTrue(first["admitted"])
        self.assertTrue(store.claim_decision(provider="ghl", tenant_id="t1",
                                             provider_event_id="evt-1"))
        store.record_decision(provider="ghl", tenant_id="t1",
                              provider_event_id="evt-1", decision_ref="effect-1")
        Path(self.effect_log).write_text("effect-1\n", encoding="utf-8")
        store.close()

        store = DurableStore(self.db)          # restart
        again = store.admit_event(provider="ghl", tenant_id="t1",
                                  provider_event_id="evt-1", payload_sha256="h")
        self.assertFalse(again["admitted"])
        self.assertEqual(again["reason"], "duplicate")
        self.assertFalse(store.claim_decision(provider="ghl", tenant_id="t1",
                                              provider_event_id="evt-1"))
        row = store.inbox_row(provider="ghl", tenant_id="t1",
                              provider_event_id="evt-1")
        store.close()
        self.assertEqual(row["state"], "decided")
        self.assertEqual(len(self._lines(self.effect_log)), 1,
                         "exactly one effect across the restart")

    def test_two_processes_deliver_same_event_one_effect(self):
        procs = [
            self._spawn("admit", "--db", self.db, "--event-id", "evt-race",
                        "--effect-log", self.effect_log, "--worker", f"w{i}")
            for i in range(2)
        ]
        self._release()
        results = [self._read_json(p) for p in procs]
        self.assertEqual(len(self._lines(self.effect_log)), 1,
                         "one provider event must have exactly one effect")
        self.assertEqual(sum(r["effects"] for r in results), 1)
        self.assertEqual(sorted(r["admitted"] for r in results), [False, True])

    def test_identical_body_different_event_ids_are_two_events(self):
        store = DurableStore(self.db)
        a = store.admit_event(provider="ghl", tenant_id="t1",
                              provider_event_id="evt-a", payload_sha256="same")
        b = store.admit_event(provider="ghl", tenant_id="t1",
                              provider_event_id="evt-b", payload_sha256="same")
        store.close()
        self.assertTrue(a["admitted"] and b["admitted"],
                        "a body hash alone must not collapse two messages")

    def test_own_outgoing_is_excluded_by_direction_and_actor(self):
        store = DurableStore(self.db)
        by_direction = store.admit_event(provider="ghl", tenant_id="t1",
                                         provider_event_id="evt-out",
                                         direction="outgoing")
        by_actor = store.admit_event(provider="ghl", tenant_id="t1",
                                     provider_event_id="evt-own",
                                     actor_id="acct-us",
                                     own_actor_ids=["acct-us"])
        store.close()
        self.assertFalse(by_direction["admitted"])
        self.assertTrue(by_direction["reason"].startswith("excluded:"))
        self.assertFalse(by_actor["admitted"])
        self.assertEqual(by_actor["reason"], "excluded:own_actor")


# ══════════════════════════════════════════════════════════════════════════
# 2. OUTBOX STATES AND SEPARATE RECEIPTS
# ══════════════════════════════════════════════════════════════════════════

class TestOutboxStates(_Base):
    def test_full_lifecycle_with_separate_ack_and_completion(self):
        store = DurableStore(self.db)
        aid = self._new_action(store, "life")
        self.assertEqual(store.get_action(aid)["state"], STATE_QUEUED)

        sent = []
        out = dispatch(store, lambda c: "ALLOW",
                       lambda c: sent.append(c["action_id"]) or {
                           "provider": "ghl", "provider_receipt_id": "p1"},
                       aid, "w1")
        self.assertEqual(out.status, ST_SENT)
        self.assertEqual(store.get_action(aid)["state"], STATE_DISPATCHED,
                         "provider admission is dispatched, not completed")

        with self.assertRaises(DurableStoreError) as ctx:
            store.record_completion(aid, {"provider": "ghl",
                                          "provider_receipt_id": "p1"})
        self.assertIn("ACK", str(ctx.exception),
                      "completion before ACK must be refused")

        store.record_ack(aid, {"provider": "ghl", "provider_receipt_id": "p1"})
        self.assertEqual(store.get_action(aid)["state"], STATE_ACKNOWLEDGED)
        self.assertNotEqual(store.get_action(aid)["state"], STATE_COMPLETED,
                            "a stop ACK is not completion")

        store.record_completion(aid, {"provider": "ghl",
                                      "provider_receipt_id": "p1"})
        self.assertEqual(store.get_action(aid)["state"], STATE_COMPLETED)
        self.assertEqual(set(store.receipts(aid)), {"dispatch", "ack", "completion"})
        self.assertEqual(len(sent), 1)
        store.close()

    def test_failed_and_unknown_are_distinct(self):
        store = DurableStore(self.db)
        failed = self._new_action(store, "fail")
        store.mark_failed(failed, "provider_known_nonexecution")
        self.assertEqual(store.get_action(failed)["state"], "failed")

        unknown = self._new_action(store, "unk")
        out = dispatch(store, lambda c: "ALLOW", lambda c: None, unknown, "w1")
        self.assertEqual(store.get_action(unknown)["state"], STATE_UNKNOWN)
        self.assertEqual(out.status, "unknown")
        self.assertIn("unknown", out.note)
        store.close()

    def test_canceled_is_terminal_and_never_claimable(self):
        store = DurableStore(self.db)
        aid = self._new_action(store, "cancel")
        store.cancel(aid, "client_stop")
        self.assertEqual(store.get_action(aid)["state"], STATE_CANCELED)
        self.assertIsNone(store.claim_for_dispatch(aid, "w1"))
        with self.assertRaises(DurableStoreError):
            store.queue(aid)
        store.close()

    def test_idempotent_intent_never_mints_a_second_action(self):
        store = DurableStore(self.db)
        first, created1 = store.create_intent(
            logical_intent_key="K", idempotency_key="I", tenant_id="t1",
            scope="person_directed", canonical_contact_id="c",
            content_sha256="h")
        second, created2 = store.create_intent(
            logical_intent_key="K", idempotency_key="I", tenant_id="t1",
            scope="person_directed", canonical_contact_id="c",
            content_sha256="h")
        self.assertTrue(created1)
        self.assertFalse(created2)
        self.assertEqual(first["action_id"], second["action_id"])
        self.assertEqual(store.counts()["actions"], 1)
        store.close()

    def test_outbound_variants_are_enforced_by_name(self):
        store = DurableStore(self.db)
        with self.assertRaises(DurableStoreError):
            store.create_intent(logical_intent_key="P", idempotency_key="P",
                               tenant_id="t1", scope="public_placement",
                               canonical_contact_id="c", content_sha256="h")
        with self.assertRaises(DurableStoreError):
            store.create_intent(logical_intent_key="D", idempotency_key="D",
                               tenant_id="t1", scope="person_directed",
                               content_sha256="h")
        row, _ = store.create_intent(logical_intent_key="OK", idempotency_key="OK",
                                     tenant_id="t1", scope="public_placement",
                                     content_sha256="h")
        self.assertEqual(row["state"], STATE_NOT_REQUESTED)
        store.close()


# ══════════════════════════════════════════════════════════════════════════
# 3. FRESH GATE ON EVERY DISPATCH AND RETRY
# ══════════════════════════════════════════════════════════════════════════

class TestFreshGate(_Base):
    def test_gate_valid_at_queue_time_invalid_at_dispatch_blocks(self):
        store = DurableStore(self.db)
        aid = self._new_action(store, "stale")
        # Queue-time evaluation: the world says ALLOW.
        self.assertEqual(evaluate_gate(lambda c: "ALLOW", {"action_id": aid}).verdict,
                         "ALLOW")
        sent = []
        # Dispatch time: the world changed.
        out = dispatch(store, lambda c: {"verdict": "SUPPRESSED",
                                         "evidence": {"reason": "global_stop"}},
                       lambda c: sent.append(c) or {"provider": "ghl"},
                       aid, "w1")
        self.assertEqual(out.status, ST_BLOCKED)
        self.assertEqual(sent, [], "a stale queue-time ALLOW must not authorise a send")
        self.assertEqual(store.get_action(aid)["state"], STATE_SUPPRESSED)
        store.close()

    def test_gate_runs_again_on_retry_and_new_verdict_is_used(self):
        store = DurableStore(self.db)
        aid = self._new_action(store, "retry")
        calls = []

        def evaluator(ctx):
            calls.append(ctx["attempt_no"])
            if len(calls) == 1:
                return {"verdict": "WAIT_UNTIL", "wait_until": time.time() + 0.05}
            return "ALLOW"

        sent = []
        first = dispatch(store, evaluator,
                         lambda c: sent.append(c) or {"provider": "ghl",
                                                      "provider_receipt_id": "p"},
                         aid, "w1")
        self.assertEqual(first.status, ST_BLOCKED)
        self.assertEqual(sent, [])
        time.sleep(0.1)   # let the WAIT_UNTIL horizon pass
        second = dispatch(store, evaluator,
                          lambda c: sent.append(c) or {"provider": "ghl",
                                                       "provider_receipt_id": "p"},
                          aid, "w2")
        self.assertEqual(second.status, ST_SENT)
        self.assertEqual(len(sent), 1)
        self.assertEqual(len(calls), 2, "the gate must run on every attempt")
        self.assertNotEqual(calls[0], calls[1], "each attempt has its own number")
        rows = store.gate_checks(aid)
        self.assertEqual([r["attempt_no"] for r in rows], calls)
        self.assertEqual([r["verdict"] for r in rows], ["WAIT_UNTIL", "ALLOW"])
        store.close()

    def test_a_verdict_can_never_be_reused_for_another_attempt(self):
        store = DurableStore(self.db)
        aid = self._new_action(store, "reuse")
        verdict = evaluate_gate(lambda c: "ALLOW", {}).as_record()
        store.record_gate_check(aid, 1, verdict)
        with self.assertRaises(DurableStoreError) as ctx:
            store.record_gate_check(aid, 1, verdict)
        self.assertIn("gate_reuse", str(ctx.exception))
        store.close()

    def test_unrecognised_verdict_fails_closed(self):
        with self.assertRaises(GateError):
            evaluate_gate(lambda c: {"verdict": "MAYBE"}, {})
        with self.assertRaises(GateError):
            evaluate_gate(lambda c: None, {})
        with self.assertRaises(GateError):
            evaluate_gate(lambda c: {"verdict": "WAIT_UNTIL"}, {})  # no until
        store = DurableStore(self.db)
        aid = self._new_action(store, "garbage")
        sent = []
        with self.assertRaises(GateError):
            dispatch(store, lambda c: {"verdict": "PROBABLY"},
                     lambda c: sent.append(c), aid, "w1")
        self.assertEqual(sent, [], "an unknown verdict never sends")
        store.close()

    def test_wait_until_defers_then_releases(self):
        store = DurableStore(self.db)
        aid = self._new_action(store, "wait")
        future = time.time() + 3600
        out = dispatch(store, lambda c: {"verdict": "WAIT_UNTIL",
                                         "wait_until": future},
                       lambda c: {"provider": "ghl"}, aid, "w1")
        self.assertEqual(out.status, ST_BLOCKED)
        self.assertEqual(store.get_action(aid)["state"], STATE_QUEUED)
        self.assertIsNone(store.claim_for_dispatch(aid, "w2"),
                          "no claim before not_before")
        out2 = dispatch(store, lambda c: "ALLOW",
                        lambda c: {"provider": "ghl", "provider_receipt_id": "p"},
                        aid, "w3", now=future + 1)
        self.assertEqual(out2.status, ST_SENT)
        store.close()

    def test_quarantined_and_reconcile_unknown_are_persisted_distinctly(self):
        store = DurableStore(self.db)
        q = self._new_action(store, "quar")
        dispatch(store, lambda c: {"verdict": "QUARANTINED",
                                   "evidence": {"reason": "binding_changed"}},
                 lambda c: {"provider": "ghl"}, q, "w1")
        self.assertEqual(store.get_action(q)["state"], "quarantined")

        u = self._new_action(store, "recon")
        sent = []
        out = dispatch(store, lambda c: {"verdict": "RECONCILE_UNKNOWN",
                                         "evidence": {"reason": "prior_unknown"}},
                       lambda c: sent.append(c) or {"provider": "ghl"}, u, "w1")
        self.assertEqual(out.status, ST_BLOCKED)
        self.assertEqual(sent, [], "RECONCILE_UNKNOWN must never send")
        self.assertEqual(store.get_action(u)["state"], STATE_UNKNOWN)
        store.close()


# ══════════════════════════════════════════════════════════════════════════
# 4. UNKNOWN SEND + REAL CRASH RECOVERY (no double send)
# ══════════════════════════════════════════════════════════════════════════

class TestCrashRecovery(_Base):
    def test_real_sigkill_after_send_then_reconcile_never_resends(self):
        store = DurableStore(self.db)
        aid = self._new_action(store, "crash")
        store.close()

        proc = self._spawn("dispatch", "--db", self.db, "--action-id", aid,
                           "--worker", "w-crash", "--send-log", self.send_log,
                           "--crash", "after_send", "--lease-seconds", "0.5")
        self._release()
        proc.communicate(timeout=60)
        self.assertEqual(proc.returncode, -signal.SIGKILL,
                         "the worker must really die by SIGKILL")
        self.assertEqual(len(self._lines(self.send_log)), 1,
                         "provider accepted exactly one send before the crash")

        store = DurableStore(self.db)
        action = store.get_action(aid)
        self.assertEqual(action["state"], STATE_QUEUED,
                         "the local receipt was lost, as in the crash window")
        self.assertIsNotNone(store.unresolved_attempt(aid),
                             "an open attempt is the evidence of a possible send")
        # A racing worker must not be able to start a second send.
        self.assertIsNone(store.claim_for_dispatch(aid, "w-race"),
                          "a possibly-sent action is never claimable")
        store.close()

        time.sleep(0.7)  # real lease expiry, not a simulated clock
        store = DurableStore(self.db)
        self.assertTrue(needs_reconciliation(store, aid),
                        "expired lease plus an open attempt demands reconciliation")
        self.assertIsNone(store.claim_for_dispatch(aid, "w-race2"),
                          "still unclaimable after the lease expired")
        out = resolve_unknown(
            store, aid,
            lambda ctx: {"outcome": "applied",
                         "receipt": {"provider": "ghl",
                                     "provider_receipt_id": "prov-crash"},
                         "evidence": {"source": "provider_history"}})
        self.assertEqual(out.status, R_APPLIED)
        self.assertEqual(out.state_after, STATE_ACKNOWLEDGED,
                         "resolved to acknowledged; completion not claimed")
        self.assertEqual(len(self._lines(self.send_log)), 1,
                         "reconciliation must not send")
        self.assertEqual(set(store.receipts(aid)), {"dispatch", "ack"})
        final = dispatch(store, lambda c: "ALLOW",
                         lambda c: self.fail("must never send again"),
                         aid, "w-late")
        self.assertEqual(final.status, "not_claimed")
        self.assertEqual(len(self._lines(self.send_log)), 1,
                         "TOTAL provider sends stays exactly one")
        store.close()

    def test_restart_sweep_makes_crash_explicitly_unknown_without_resend(self):
        store = DurableStore(self.db)
        aid = self._new_action(store, "sweep")
        store.close()

        proc = self._spawn("dispatch", "--db", self.db, "--action-id", aid,
                           "--worker", "w-crash", "--send-log", self.send_log,
                           "--crash", "after_send", "--lease-seconds", "0.3")
        self._release()
        proc.communicate(timeout=60)
        self.assertEqual(proc.returncode, -signal.SIGKILL)
        self.assertEqual(len(self._lines(self.send_log)), 1)

        time.sleep(0.6)  # real lease expiry
        store = DurableStore(self.db)
        self.assertEqual(store.get_action(aid)["state"], STATE_QUEUED,
                         "the dead process left no verdict behind")
        self.assertEqual(sweep_inflight(store), [aid],
                         "restart promotes the dead-mid-send action")
        self.assertEqual(store.get_action(aid)["state"], STATE_UNKNOWN,
                         "a dispatch with no verdict becomes explicitly unknown")
        self.assertIsNotNone(store.unresolved_attempt(aid),
                             "the possibly-sent attempt stays open")
        self.assertIsNone(store.claim_for_dispatch(aid, "w-race"),
                          "swept action is never claimable")
        self.assertEqual(sweep_inflight(store), [], "the sweep is idempotent")
        out = resolve_unknown(
            store, aid,
            lambda c: {"outcome": "applied",
                       "receipt": {"provider": "ghl",
                                   "provider_receipt_id": "prov-sweep"}})
        self.assertEqual(out.state_after, STATE_ACKNOWLEDGED)
        self.assertEqual(len(self._lines(self.send_log)), 1,
                         "sweep plus reconcile send nothing")
        store.close()

    def test_crash_before_send_resolves_not_applied_then_retries_same_action(self):
        store = DurableStore(self.db)
        aid = self._new_action(store, "crash2")
        store.close()

        proc = self._spawn("dispatch", "--db", self.db, "--action-id", aid,
                           "--worker", "w-crash", "--send-log", self.send_log,
                           "--crash", "before_send", "--lease-seconds", "0.5")
        self._release()
        proc.communicate(timeout=60)
        self.assertEqual(proc.returncode, -signal.SIGKILL)
        self.assertEqual(self._lines(self.send_log), [],
                         "nothing reached the provider")

        time.sleep(0.7)
        store = DurableStore(self.db)
        out = resolve_unknown(store, aid, lambda ctx: "not_applied")
        self.assertEqual(out.status, R_NOT_APPLIED)
        self.assertEqual(out.state_after, STATE_QUEUED)
        self.assertEqual(store.get_action(aid)["action_id"], aid,
                         "the SAME action identity is retried")
        def retry_sender(ctx):
            with open(self.send_log, "a", encoding="utf-8") as fh:
                fh.write(ctx["action_id"] + "\n")
            return {"provider": "ghl", "provider_receipt_id": "p-retry"}

        retry = dispatch(store, lambda c: "ALLOW", retry_sender, aid, "w-retry")
        self.assertEqual(retry.status, ST_SENT)
        self.assertEqual(len(self._lines(self.send_log)), 1,
                         "the retry is the only real send")
        self.assertEqual(len(store.attempts(aid)), 2,
                         "two attempts recorded for one logical action")
        store.close()

    def test_in_flight_lease_is_left_alone(self):
        store = DurableStore(self.db)
        aid = self._new_action(store, "live")
        claim = store.claim_for_dispatch(aid, "w1", lease_seconds=60)
        self.assertIsNotNone(claim)
        self.assertTrue(store.begin_attempt(aid, claim["fence"], "w1"))
        self.assertFalse(needs_reconciliation(store, aid),
                         "a live lease means a worker is mid-send")
        self.assertEqual(sweep_inflight(store), [],
                         "a startup sweep never touches a live lease")
        out = resolve_unknown(store, aid, lambda c: "applied")
        self.assertEqual(out.status, R_IN_FLIGHT)
        self.assertEqual(store.get_action(aid)["state"], STATE_QUEUED)
        store.close()

    def test_unresolved_unknown_is_never_claimed_even_after_lease_expiry(self):
        store = DurableStore(self.db)
        aid = self._new_action(store, "never")
        dispatch(store, lambda c: "ALLOW", lambda c: None, aid, "w1",
                 lease_seconds=0.2)
        time.sleep(0.4)
        self.assertEqual(store.get_action(aid)["state"], STATE_UNKNOWN)
        self.assertIsNone(store.claim_for_dispatch(aid, "w2"),
                          "unknown stays unclaimable")
        out = resolve_unknown(store, aid, lambda c: "unknown")
        self.assertEqual(out.status, R_UNKNOWN)
        self.assertIsNone(store.claim_for_dispatch(aid, "w3"),
                          "still unclaimable after an unresolved reconcile")
        store.close()

    def test_reconcile_after_ack_before_completion(self):
        store = DurableStore(self.db)
        aid = self._new_action(store, "ackonly")
        dispatch(store, lambda c: "ALLOW",
                 lambda c: {"provider": "ghl", "provider_receipt_id": "p"}, aid, "w1")
        store.record_ack(aid, {"provider": "ghl", "provider_receipt_id": "p"})
        self.assertEqual(store.get_action(aid)["state"], STATE_ACKNOWLEDGED)
        self.assertFalse(needs_reconciliation(store, aid),
                         "an ACKed action is not an unknown send")
        out = resolve_unknown(store, aid, lambda c: "applied")
        self.assertEqual(out.status, R_NOT_NEEDED)
        self.assertEqual(store.get_action(aid)["state"], STATE_ACKNOWLEDGED)
        store.close()

    def test_sender_exception_is_unknown_not_resent(self):
        store = DurableStore(self.db)
        aid = self._new_action(store, "boom")
        out = dispatch(store, lambda c: "ALLOW",
                       lambda c: (_ for _ in ()).throw(TimeoutError("no answer")),
                       aid, "w1")
        self.assertEqual(out.status, "send_error")
        self.assertEqual(store.get_action(aid)["state"], STATE_UNKNOWN)
        self.assertIsNone(store.claim_for_dispatch(aid, "w2"))
        store.close()


# ══════════════════════════════════════════════════════════════════════════
# 5. CANCELLATION AGAINST RACING WORKERS (real processes)
# ══════════════════════════════════════════════════════════════════════════

class TestCancellationRace(_Base):
    def test_two_workers_on_one_action_send_exactly_once(self):
        store = DurableStore(self.db)
        aid = self._new_action(store, "race")
        store.close()

        procs = [
            self._spawn("dispatch", "--db", self.db, "--action-id", aid,
                        "--worker", f"w{i}", "--send-log", self.send_log)
            for i in range(2)
        ]
        self._release()
        results = [self._read_json(p) for p in procs]
        self.assertEqual(len(self._lines(self.send_log)), 1,
                         "two racing workers must produce exactly one send")
        self.assertEqual(sorted(r["status"] for r in results),
                         ["not_claimed", "sent"])

    def test_canceled_action_cannot_be_dispatched_by_racing_workers(self):
        store = DurableStore(self.db)
        aid = self._new_action(store, "cancel-race")
        store.cancel(aid, "client_stop")
        store.close()

        procs = [
            self._spawn("dispatch", "--db", self.db, "--action-id", aid,
                        "--worker", f"w{i}", "--send-log", self.send_log)
            for i in range(2)
        ]
        self._release()
        results = [self._read_json(p) for p in procs]
        self.assertEqual(self._lines(self.send_log), [],
                         "a canceled action must never reach the provider")
        self.assertEqual({r["status"] for r in results}, {"not_claimed"})

    def test_cancel_after_claim_and_during_gate_blocks_the_send(self):
        store = DurableStore(self.db)
        aid = self._new_action(store, "cancel-mid")
        store.close()

        marker = str(self.tmp / "in-gate")
        proc = self._spawn("dispatch", "--db", self.db, "--action-id", aid,
                           "--worker", "w-slow", "--send-log", self.send_log,
                           "--gate", "slow_allow", "--gate-marker", marker,
                           "--gate-delay", "0.8")
        self._release()
        self._wait_for(marker)          # the worker has claimed and is in the gate

        store = DurableStore(self.db)
        store.cancel(aid, "stop_arrived_mid_gate")
        self.assertEqual(store.get_action(aid)["state"], STATE_CANCELED)
        store.close()

        result = self._read_json(proc)
        self.assertEqual(result["status"], ST_REFUSED_RACE,
                         "the fenced begin_attempt must lose to the cancellation")
        self.assertEqual(self._lines(self.send_log), [],
                         "nothing was sent after the cancel")
        store = DurableStore(self.db)
        self.assertEqual(store.get_action(aid)["state"], STATE_CANCELED)
        store.close()

    def test_cancel_is_refused_once_a_send_may_have_begun(self):
        store = DurableStore(self.db)
        aid = self._new_action(store, "cancel-late")
        claim = store.claim_for_dispatch(aid, "w1", lease_seconds=30)
        self.assertTrue(store.begin_attempt(aid, claim["fence"], "w1"))
        with self.assertRaises(DurableStoreError) as ctx:
            store.cancel(aid, "too_late")
        self.assertIn("in_flight", str(ctx.exception))
        store.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
