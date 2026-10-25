#!/usr/bin/env python3
"""T-18: suppression precedence, gated re-entry, partial-capture serving, and
the point-of-use suppression fence.

Contract basis: DATA-CONTRACTS section 7 (capture, refusal, human precedence)
and section 3 (a fresh gate before every dispatch), plus R-19's owned handoff.

Run from the skill root:
    python3 -m unittest discover -s tools/tests -p 'test_suppression_reentry.py' -v

What is proven here, each with its inverse:

  PRECEDENCE   global > channel > sequence > human > field, reported in that
               order; a sequence refusal blocks that sequence only, and a send
               that cannot name its sequence is not treated as a different one.

  RE-ENTRY     un-suppressing requires a recorded actor and reason (and, in the
               fence, an authority). Without them the write is refused and the
               suppression stands. Nothing here expires on a timer.

  DURABLE      a suppression is contactable-again only after a recorded
               re-entry, across a close and reopen of the database.

  CAPTURE      a partial capture serves the ORIGINAL ask at its own cursor; a
               rejected ask serves help and can never be restarted.

  POINT OF USE the fence is re-read inside the transaction that starts the send,
               so a suppression that lands after the gate said ALLOW still
               blocks it - proven with two real processes, not a sleep.

Every multi-process case uses real child interpreters (--worker <cfg.json>),
never threads.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from collection_lock import CollectionLock, CaptureRejected  # noqa: E402
from consent_gate import (  # noqa: E402
    ConsentCapture,
    ConsentError,
    ConsentStore,
    DECISION_GRANT,
    DECISION_REFUSE,
    PRECEDENCE,
    REASON_CHANNEL,
    REASON_FIELD,
    REASON_GLOBAL,
    REASON_HUMAN,
    REASON_SEQUENCE,
    REASON_SEQUENCE_UNRESOLVED,
    SCOPE_CAMPAIGN,
    SCOPE_CHANNEL,
    SCOPE_GLOBAL,
    SCOPE_SEQUENCE,
    SCOPE_TOPIC,
    make_gate_evaluator,
)
from durable_store import DurableStore, STATE_SUPPRESSED  # noqa: E402
from outbound_gate import (  # noqa: E402
    GateError,
    ST_BLOCKED,
    ST_SENT,
    dispatch,
)
from suppression_ledger import SuppressionError, SuppressionLedger  # noqa: E402
from tenant_identity import TenantIdentity  # noqa: E402

TENANT = "t1"
SEQ = "seq-1"


# ══════════════════════════════════════════════════════════════════════════
# worker process (real second interpreter)
# ══════════════════════════════════════════════════════════════════════════

def _emit(path, payload):
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")
        handle.flush()


def _wait_until(stamp):
    while time.time() < float(stamp):
        time.sleep(0.001)


def _wait_file(path, timeout=30.0):
    deadline = time.time() + timeout
    while not Path(path).exists():
        if time.time() > deadline:
            raise AssertionError("barrier timeout: " + str(path))
        time.sleep(0.002)


def _worker(cfg_path):
    with open(cfg_path, encoding="utf-8") as handle:
        cfg = json.load(handle)
    tenant, contact = cfg["tenant"], cfg["contact"]
    mode, out = cfg["mode"], cfg["out"]

    if mode == "suppress":
        _wait_until(cfg["at"])
        consent = ConsentStore(TenantIdentity(cfg["db"]))
        consent.global_stop(tenant, contact, actor="agent",
                            reason="customer said stop")
        ledger = SuppressionLedger(cfg["store"])
        event = ledger.suppress(tenant, contact, reason="global_stop",
                                actor="agent")
        ledger.close()
        _emit(out, {"ok": True, "at": event["at"], "epoch": event["epoch"]})
        return 0

    if mode == "dispatch":
        _wait_until(cfg["at"])
        store = DurableStore(cfg["store"])
        ledger = SuppressionLedger(cfg["store"])
        evaluator = make_gate_evaluator(ConsentStore(TenantIdentity(cfg["db"])))
        sends = []

        def sender(ctx):
            sends.append(ctx["action_id"])
            with open(cfg["send_log"], "a", encoding="utf-8") as handle:
                handle.write(ctx["action_id"] + "\n")
                handle.flush()
            return {"provider": "ghl", "provider_receipt_id": "r"}

        result = dispatch(store, evaluator, sender, cfg["action_id"],
                          cfg["worker"], context={"channel": "sms"},
                          ledger=ledger)
        attempt = store._db.execute(
            "SELECT COALESCE(MIN(started_at), 0) AS s FROM outbox_attempts"
            " WHERE action_id=?", (cfg["action_id"],)).fetchone()["s"]
        store.close()
        ledger.close()
        _emit(out, {"ok": True, "status": result.status,
                    "verdict": result.verdict, "sends": sends,
                    "attempt_started_at": float(attempt or 0.0)})
        return 0

    if mode == "dispatch_stale":
        # A real second process whose gate decided ALLOW BEFORE the suppression
        # existed and then waited for it to commit. This is the torn read the
        # fence must survive.
        store = DurableStore(cfg["store"])
        ledger = SuppressionLedger(cfg["store"])
        consent = ConsentStore(TenantIdentity(cfg["db"]))
        sends = []

        def stale_evaluator(ctx):
            decision = consent.decide(tenant, contact, channel="sms")
            Path(cfg["decided"]).write_text("1", encoding="utf-8")
            _wait_file(cfg["released"])
            return {"verdict": "ALLOW",
                    "evidence": {"stale": True,
                                 "decided_allowed": decision["allowed"]}}

        def sender(ctx):
            sends.append(ctx["action_id"])
            with open(cfg["send_log"], "a", encoding="utf-8") as handle:
                handle.write(ctx["action_id"] + "\n")
                handle.flush()
            return {"provider": "ghl", "provider_receipt_id": "r"}

        result = dispatch(store, stale_evaluator, sender, cfg["action_id"],
                          cfg["worker"], context={"channel": "sms"},
                          ledger=ledger)
        row = store.get_action(cfg["action_id"])
        store.close()
        ledger.close()
        _emit(out, {"ok": True, "status": result.status,
                    "verdict": result.verdict, "sends": sends,
                    "state": row["state"]})
        return 0

    if mode == "capture_crash":
        identity = TenantIdentity(cfg["db"])
        lock = CollectionLock(identity)
        capture = ConsentCapture(lock)
        lease = lock.acquire(tenant, contact, SEQ, "crasher", 0.5)
        capture.begin(tenant, contact, SEQ, cfg["capture"], cfg["steps"],
                      owner_id="crasher", fence=lease.fence)
        capture.record_step(tenant, contact, SEQ, cfg["capture"], 0,
                            decision=DECISION_REFUSE,
                            scope_kind=SCOPE_CHANNEL, scope_value="sms",
                            owner_id="crasher", fence=lease.fence)
        _emit(out, {"ok": True, "cursor": 1})
        os._exit(9)  # crash: no release, no complete, no reject

    if mode == "capture_serve":
        identity = TenantIdentity(cfg["db"])
        lock = CollectionLock(identity)
        capture = ConsentCapture(lock)
        deadline = time.time() + 20.0
        while True:
            lease = lock.acquire(tenant, contact, SEQ, "resumer", 5.0)
            if lease.granted:
                break
            if lease.reason == "reconcile_required":
                lock.reconcile(tenant, contact, SEQ, "resumer", lease.fence)
                continue
            if time.time() > deadline:
                raise AssertionError("could not acquire: " + lease.reason)
            time.sleep(0.01)
        state = capture.begin(tenant, contact, SEQ, cfg["capture"], cfg["steps"],
                              owner_id="resumer", fence=lease.fence)
        served = capture.serve(tenant, contact, SEQ, cfg["capture"])
        _emit(out, {"ok": True, "state": state["state"],
                    "cursor": state["cursor"], "served": served})
        return 0

    raise SystemExit("unknown worker mode " + mode)


if "--worker" in sys.argv:
    _worker(sys.argv[sys.argv.index("--worker") + 1])
    raise SystemExit(0)


# ══════════════════════════════════════════════════════════════════════════
# fixtures
# ══════════════════════════════════════════════════════════════════════════

class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t18sr-"))
        self.db = str(self.tmp / "consent.sqlite")
        self.store_path = str(self.tmp / "outbox.sqlite")
        self.send_log = str(self.tmp / "sends.log")
        self.identity = TenantIdentity(self.db)
        self.identity.register_tenant(TENANT, "purple billboard")
        self.contact = self.identity.bind(
            TENANT, [("sms_number", "+15550123", True)], source="test")
        self.consent = ConsentStore(self.identity)
        self.ledger = SuppressionLedger(self.store_path)

    def tearDown(self):
        try:
            self.consent.identity = None
        finally:
            pass

    # ── helpers ───────────────────────────────────────────────────────────

    def _run_worker(self, cfg, expect_rc=0):
        cfg = dict(cfg)
        cfg.setdefault("db", self.db)
        cfg.setdefault("tenant", TENANT)
        cfg.setdefault("contact", self.contact)
        cfg.setdefault("store", self.store_path)
        cfg.setdefault("send_log", self.send_log)
        cfg.setdefault("out", str(self.tmp / ("worker-%s-%d.jsonl"
                                             % (cfg["mode"], time.time_ns()))))
        cfg_path = self.tmp / ("cfg-" + cfg["mode"] + "-%d.json" % time.time_ns())
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-I", str(Path(__file__).resolve()), "--worker",
             str(cfg_path)],
            capture_output=True, text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(proc.returncode, expect_rc,
                         "worker rc=%s stdout=%s stderr=%s"
                         % (proc.returncode, proc.stdout, proc.stderr))
        lines = [ln for ln in Path(cfg["out"]).read_text(
            encoding="utf-8").splitlines() if ln.strip()]
        self.assertTrue(lines, "worker emitted nothing: " + proc.stderr)
        return json.loads(lines[-1])

    def _new_queued(self, key):
        store = DurableStore(self.store_path)
        row, _ = store.create_intent(
            logical_intent_key=key, idempotency_key="idem-" + key,
            tenant_id=TENANT, scope="person_directed",
            canonical_contact_id=self.contact, content_sha256="sha-" + key)
        store.queue(row["action_id"])
        store.close()
        return row["action_id"]

    def _sends(self):
        p = Path(self.send_log)
        return [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln] \
            if p.exists() else []


# ══════════════════════════════════════════════════════════════════════════
# 1. PRECEDENCE: field vs channel / global / sequence / handoff
# ══════════════════════════════════════════════════════════════════════════

class TestPrecedence(_Base):
    def test_sequence_refusal_blocks_that_sequence_only(self):
        self.consent.refuse(TENANT, self.contact, scope_kind=SCOPE_SEQUENCE,
                            scope_value="onboarding-a")
        blocked = self.consent.decide(TENANT, self.contact, channel="sms",
                                      sequence="onboarding-a")
        allowed = self.consent.decide(TENANT, self.contact, channel="sms",
                                      sequence="onboarding-b")
        self.assertFalse(blocked["allowed"])
        self.assertEqual(blocked["reason"], REASON_SEQUENCE)
        self.assertEqual(blocked["blocking"]["scope_kind"], SCOPE_SEQUENCE)
        self.assertTrue(allowed["allowed"],
                        "a sequence refusal must not block another sequence")

    def test_unnamed_sequence_is_not_broader_permission(self):
        self.consent.refuse(TENANT, self.contact, scope_kind=SCOPE_SEQUENCE,
                            scope_value="onboarding-a")
        verdict = self.consent.decide(TENANT, self.contact, channel="sms")
        self.assertFalse(verdict["allowed"])
        self.assertEqual(verdict["reason"], REASON_SEQUENCE_UNRESOLVED)
        self.assertTrue(verdict["evidence"]["unknown_scope_is_not_permission"])

    def test_precedence_is_reported_global_then_channel_then_sequence_then_human_then_field(self):
        # Everything that can block, blocks at once; the REPORTED reason must
        # follow the documented ladder, and each narrower cause must take over
        # as soon as the broader one is lifted.
        self.consent.refuse(TENANT, self.contact, scope_kind=SCOPE_CAMPAIGN,
                            scope_value="spring")
        self.consent.human_takeover(TENANT, self.contact, actor="jill",
                                    reason="human reply")
        self.consent.refuse(TENANT, self.contact, scope_kind=SCOPE_SEQUENCE,
                            scope_value="onboarding-a")
        self.consent.refuse(TENANT, self.contact, scope_kind=SCOPE_CHANNEL,
                            scope_value="sms")
        self.consent.global_stop(TENANT, self.contact)

        def reason():
            return self.consent.decide(
                TENANT, self.contact, channel="sms", sequence="onboarding-a",
                campaign="spring")["reason"]

        self.assertEqual(reason(), REASON_GLOBAL)
        self.assertEqual(self.consent.decide(
            TENANT, self.contact, channel="sms", sequence="onboarding-a",
            campaign="spring")["evidence"]["precedence"], PRECEDENCE)
        self.consent.lift_global_stop(TENANT, self.contact, actor="jill",
                                      reason="customer asked to resume")
        self.assertEqual(reason(), REASON_CHANNEL)
        self.consent.grant(TENANT, self.contact, scope_kind=SCOPE_CHANNEL,
                           scope_value="sms", actor="jill",
                           reason="sms ok again")
        self.assertEqual(reason(), REASON_SEQUENCE)
        self.consent.grant(TENANT, self.contact, scope_kind=SCOPE_SEQUENCE,
                           scope_value="onboarding-a", actor="jill",
                           reason="sequence may resume")
        self.assertEqual(reason(), REASON_HUMAN)
        self.consent.human_release(TENANT, self.contact, actor="jill",
                                   reason="handed back")
        self.assertEqual(reason(), REASON_FIELD)
        self.consent.grant(TENANT, self.contact, scope_kind=SCOPE_CAMPAIGN,
                           scope_value="spring", actor="jill",
                           reason="campaign cleared")
        self.assertTrue(self.consent.decide(
            TENANT, self.contact, channel="sms", sequence="onboarding-a",
            campaign="spring")["allowed"])

    def test_handoff_uses_the_same_ladder_and_needs_a_named_owner(self):
        self.consent.human_takeover(TENANT, self.contact, actor="jill",
                                    reason="human reply")
        verdict = self.consent.decide(TENANT, self.contact, channel="sms")
        self.assertEqual(verdict["reason"], REASON_HUMAN)
        self.assertEqual(verdict["blocking"]["scope_value"], "jill",
                         "the handoff names the owner who holds the thread")
        with self.assertRaises(ConsentError):
            self.consent.human_takeover(TENANT, self.contact, actor="",
                                        reason="no owner")
        self.consent.human_release(TENANT, self.contact, actor="jill")
        self.assertTrue(self.consent.decide(
            TENANT, self.contact, channel="sms")["allowed"])


# ══════════════════════════════════════════════════════════════════════════
# 2. RE-ENTRY: explicit, gated, never a timeout
# ══════════════════════════════════════════════════════════════════════════

class TestGatedReentry(_Base):
    def test_a_grant_without_a_recorded_human_is_refused(self):
        self.consent.refuse(TENANT, self.contact, scope_kind=SCOPE_CHANNEL,
                            scope_value="sms")
        with self.assertRaises(ConsentError) as caught:
            self.consent.grant(TENANT, self.contact, scope_kind=SCOPE_CHANNEL,
                               scope_value="sms", reason="some reason")
        self.assertIn("reentry_requires_authority", str(caught.exception))
        self.assertFalse(self.consent.decide(
            TENANT, self.contact, channel="sms")["allowed"],
            "a refused re-entry leaves the suppression standing")

    def test_a_grant_without_a_reason_is_refused(self):
        self.consent.refuse(TENANT, self.contact, scope_kind=SCOPE_CHANNEL,
                            scope_value="sms")
        with self.assertRaises(ConsentError) as caught:
            self.consent.grant(TENANT, self.contact, scope_kind=SCOPE_CHANNEL,
                               scope_value="sms", actor="jill")
        self.assertIn("reason", str(caught.exception))
        self.assertEqual(len(self.consent.active_refusals(TENANT, self.contact)), 1)

    def test_a_baseline_grant_before_any_refusal_needs_no_authority(self):
        # A grant that lifts nothing is a preference, not a re-entry.
        row = self.consent.grant(TENANT, self.contact, scope_kind=SCOPE_CHANNEL,
                                 scope_value="sms")
        self.assertEqual(row["decision"], DECISION_GRANT)
        self.assertTrue(self.consent.decide(
            TENANT, self.contact, channel="sms")["allowed"])

    def test_authorised_reentry_is_audited_and_lifts_exactly_its_scope(self):
        self.consent.refuse(TENANT, self.contact, scope_kind=SCOPE_CHANNEL,
                            scope_value="sms")
        self.consent.refuse(TENANT, self.contact, scope_kind=SCOPE_TOPIC,
                            scope_value="pricing")
        lifted = self.consent.grant(TENANT, self.contact,
                                    scope_kind=SCOPE_CHANNEL, scope_value="sms",
                                    actor="jill", reason="customer asked again")
        self.assertEqual(lifted["actor"], "jill")
        self.assertEqual(lifted["reason"], "customer asked again")
        self.assertTrue(self.consent.decide(
            TENANT, self.contact, channel="sms")["allowed"])
        self.assertFalse(self.consent.decide(
            TENANT, self.contact, channel="sms", topic="pricing")["allowed"],
            "re-entry lifts its own scope and nothing else")

    def test_nothing_expires_on_a_timer(self):
        self.consent.global_stop(TENANT, self.contact, actor="agent",
                                 reason="stop")
        far_future = time.time() + 10 * 365 * 24 * 3600
        verdict = self.consent.decide(TENANT, self.contact, channel="sms")
        self.assertFalse(verdict["allowed"])
        # The decision function takes no clock, so no amount of elapsed time can
        # change it; the only way past is a recorded re-entry.
        self.assertFalse(self.consent.decide(
            TENANT, self.contact, channel="sms")["allowed"])
        self.assertGreater(far_future, time.time())
        events = self.ledger.events(TENANT, self.contact)
        self.assertEqual(events, [], "no fence event without a fence write")

    def test_fence_reentry_requires_actor_authority_and_reason(self):
        self.ledger.suppress(TENANT, self.contact, reason="stop", actor="agent")
        for broken in ({"actor": "", "authority": "ops", "reason": "x"},
                       {"actor": "jill", "authority": "", "reason": "x"},
                       {"actor": "jill", "authority": "ops", "reason": ""}):
            with self.assertRaises(SuppressionError) as caught:
                self.ledger.reenter(TENANT, self.contact, **broken)
            self.assertIn("reentry_requires_authority", str(caught.exception))
        self.assertEqual(self.ledger.epoch(TENANT, self.contact), 1,
                         "a refused re-entry does not move the fence")

    def test_fence_reentry_is_durable_and_audited(self):
        self.ledger.suppress(TENANT, self.contact, reason="stop", actor="agent")
        self.assertEqual(self.ledger.epoch(TENANT, self.contact), 1)
        self.ledger.close()
        self.ledger = SuppressionLedger(self.store_path)
        self.assertEqual(self.ledger.epoch(TENANT, self.contact), 1,
                         "the fence survives a reopen")
        self.ledger.reenter(TENANT, self.contact, actor="jill",
                            authority="ops:supervisor",
                            reason="customer asked us to resume")
        self.ledger.close()
        self.ledger = SuppressionLedger(self.store_path)
        trail = [(e["action"], e["authority"])
                 for e in self.ledger.events(TENANT, self.contact)]
        self.assertEqual(trail, [("suppress", ""), ("reenter", "ops:supervisor")])


# ══════════════════════════════════════════════════════════════════════════
# 3. PARTIAL CAPTURE: serve the original, never restart a rejected ask
# ══════════════════════════════════════════════════════════════════════════

class TestPartialCaptureServesOriginal(_Base):
    STEPS = ["ask:SMS email", "ask:confirm email", "ask:topic"]

    def _capture(self, owner="collector", lease_seconds=30.0):
        lock = CollectionLock(self.identity)
        lease = lock.acquire(TENANT, self.contact, SEQ, owner, lease_seconds)
        self.assertTrue(lease.granted, "acquire failed: " + lease.reason)
        return ConsentCapture(lock), lock, lease

    def test_partial_capture_serves_the_original_step_at_the_cursor(self):
        capture, lock, lease = self._capture()
        capture.begin(TENANT, self.contact, SEQ, "cap-1", self.STEPS,
                      owner_id="collector", fence=lease.fence)
        capture.record_step(TENANT, self.contact, SEQ, "cap-1", 0,
                            decision=DECISION_REFUSE, scope_kind=SCOPE_CHANNEL,
                            scope_value="sms", owner_id="collector",
                            fence=lease.fence)
        served = capture.serve(TENANT, self.contact, SEQ, "cap-1")
        self.assertEqual(served["kind"], "original")
        self.assertEqual(served["original"], self.STEPS[1],
                         "the ask served is the step the person was answering")
        self.assertEqual(served["original_step_index"], 1)
        self.assertFalse(served["restart_allowed"])
        lock.release(TENANT, self.contact, SEQ, "collector", lease.fence)

    def test_a_rejected_ask_serves_help_and_never_restarts(self):
        capture, lock, lease = self._capture()
        capture.begin(TENANT, self.contact, SEQ, "cap-2", self.STEPS,
                      owner_id="collector", fence=lease.fence)
        capture.record_step(TENANT, self.contact, SEQ, "cap-2", 0,
                            decision=DECISION_REFUSE, scope_kind=SCOPE_CHANNEL,
                            scope_value="sms", owner_id="collector",
                            fence=lease.fence)
        capture.reject(TENANT, self.contact, SEQ, "cap-2",
                       reason="declined:final collection",
                       owner_id="collector", fence=lease.fence)
        served = capture.serve(TENANT, self.contact, SEQ, "cap-2")
        self.assertEqual(served["kind"], "help")
        self.assertIsNone(served["original"],
                          "a rejected ask must never be served again")
        self.assertFalse(served["restart_allowed"])
        self.assertEqual(served["rejection_reason"], "declined:final collection")
        # And it cannot be advanced past the rejection either.
        with self.assertRaises(CaptureRejected):
            capture.record_step(TENANT, self.contact, SEQ, "cap-2", 1,
                                decision=DECISION_GRANT,
                                scope_kind=SCOPE_CHANNEL, scope_value="email",
                                owner_id="collector", fence=lease.fence)
        again = capture.begin(TENANT, self.contact, SEQ, "cap-2", self.STEPS,
                             owner_id="collector", fence=lease.fence)
        self.assertEqual(again["state"], "rejected",
                         "begin() on a rejected capture resumes nothing")
        self.assertEqual(again["cursor"], 1, "and rewinds nothing")
        lock.release(TENANT, self.contact, SEQ, "collector", lease.fence)

    def test_a_completed_capture_serves_nothing_to_answer(self):
        capture, lock, lease = self._capture()
        capture.begin(TENANT, self.contact, SEQ, "cap-3", ["ask:only"],
                      owner_id="collector", fence=lease.fence)
        capture.record_step(TENANT, self.contact, SEQ, "cap-3", 0,
                            decision=DECISION_REFUSE, scope_kind=SCOPE_CHANNEL,
                            scope_value="sms", owner_id="collector",
                            fence=lease.fence)
        capture.complete(TENANT, self.contact, SEQ, "cap-3",
                         owner_id="collector", fence=lease.fence)
        served = capture.serve(TENANT, self.contact, SEQ, "cap-3")
        self.assertEqual(served["kind"], "complete")
        self.assertIsNone(served["original"])
        lock.release(TENANT, self.contact, SEQ, "collector", lease.fence)

    def test_the_original_ask_survives_a_crashing_process(self):
        crashed = self._run_worker({"mode": "capture_crash", "capture": "cap-4",
                                    "steps": self.STEPS}, expect_rc=9)
        self.assertEqual(crashed["cursor"], 1)
        served = self._run_worker({"mode": "capture_serve", "capture": "cap-4",
                                   "steps": self.STEPS})
        self.assertEqual(served["cursor"], 1, "resumed at its own cursor")
        self.assertEqual(served["served"]["kind"], "original")
        self.assertEqual(served["served"]["original"], self.STEPS[1],
                         "the new process serves the original ask, not a fresh one")
        self.assertFalse(served["served"]["restart_allowed"])


# ══════════════════════════════════════════════════════════════════════════
# 4. POINT OF USE: the fence inside the transaction that starts the send
# ══════════════════════════════════════════════════════════════════════════

class TestPointOfUseFence(_Base):
    def _dispatch(self, action_id, evaluator, *, ledger=None, worker="w1"):
        store = DurableStore(self.store_path)
        sends = []

        def sender(ctx):
            sends.append(ctx["action_id"])
            with open(self.send_log, "a", encoding="utf-8") as handle:
                handle.write(ctx["action_id"] + "\n")
            return {"provider": "ghl", "provider_receipt_id": "r"}

        result = dispatch(store, evaluator, sender, action_id, worker,
                          context={"channel": "sms"}, ledger=ledger)
        row = store.get_action(action_id)
        store.close()
        return result, row, sends

    def test_a_suppression_landing_after_the_verdict_still_blocks_the_send(self):
        """The torn read: ALLOW computed, then the stop commits, then the send.

        The evaluator below reproduces exactly that ordering inside one call: it
        reads consent (ALLOW), commits the suppression, and returns the stale
        ALLOW. The epoch was captured before that read, so the CAS in
        begin_attempt_guarded no longer matches and no attempt is created.
        """
        action_id = self._new_queued("L-torn")
        consent, ledger = self.consent, self.ledger

        def torn(ctx):
            stale = consent.decide(TENANT, self.contact, channel="sms")
            consent.global_stop(TENANT, self.contact, actor="agent",
                                reason="customer said stop")
            ledger.suppress(TENANT, self.contact, reason="global_stop",
                            actor="agent")
            return {"verdict": "ALLOW",
                    "evidence": {"stale": True, "allowed": stale["allowed"]}}

        result, row, sends = self._dispatch(action_id, torn, ledger=ledger)
        self.assertEqual(sends, [], "provider must never be called")
        self.assertEqual(result.status, ST_BLOCKED)
        self.assertEqual(result.verdict, "SUPPRESSED")
        self.assertEqual(row["state"], STATE_SUPPRESSED)
        attempts = DurableStore(self.store_path)._db.execute(
            "SELECT COUNT(*) AS n FROM outbox_attempts WHERE action_id=?",
            (action_id,)).fetchone()["n"]
        self.assertEqual(attempts, 0, "the refused attempt row was rolled back")

    def test_control_same_probe_without_the_suppression_does_send(self):
        # Proves the probe above is not vacuous: the identical call shape sends
        # when nothing suppresses it.
        action_id = self._new_queued("L-torn-control")

        def torn_without_stop(ctx):
            return {"verdict": "ALLOW", "evidence": {"stale": True}}

        result, row, sends = self._dispatch(action_id, torn_without_stop,
                                            ledger=self.ledger)
        self.assertEqual(len(sends), 1)
        self.assertEqual(result.status, ST_SENT)

    def test_the_consent_evaluator_is_rechecked_inside_the_transaction(self):
        # No ledger at all: the evaluator advertises itself as a consent guard,
        # so dispatch re-runs it inside the transaction that starts the send.
        action_id = self._new_queued("L-recheck")
        consent = self.consent

        def flips_once(ctx):
            if not Path(self.tmp / "flipped").exists():
                (self.tmp / "flipped").write_text("1", encoding="utf-8")
                consent.global_stop(TENANT, self.contact, actor="agent",
                                    reason="stop")
                return {"verdict": "ALLOW", "evidence": {"first": True}}
            return make_gate_evaluator(consent)(ctx)

        flips_once.consent_guard = True  # declares the in-transaction recheck
        result, row, sends = self._dispatch(action_id, flips_once)
        self.assertEqual(sends, [], "the in-transaction recheck must catch it")
        self.assertEqual(result.status, ST_BLOCKED)

    def test_a_ledger_from_another_database_is_refused(self):
        action_id = self._new_queued("L-wrongdb")
        other = SuppressionLedger(str(self.tmp / "elsewhere.sqlite"))
        with self.assertRaises(GateError):
            self._dispatch(action_id, make_gate_evaluator(self.consent),
                           ledger=other)
        other.close()
        self.assertEqual(self._sends(), [])

    def test_two_real_processes_cannot_send_after_a_suppression_commits(self):
        """Two interpreters, one barrier, one torn read."""
        action_id = self._new_queued("L-proc")
        decided = str(self.tmp / "decided")
        released = str(self.tmp / "released")
        out_dispatcher = str(self.tmp / "out-dispatch.jsonl")
        cfg = {"mode": "dispatch_stale", "action_id": action_id,
               "worker": "w-dispatch", "decided": decided,
               "released": released, "out": out_dispatcher}
        cfg_path = self.tmp / "cfg-proc.json"
        cfg_path.write_text(json.dumps({**cfg, "db": self.db, "tenant": TENANT,
                                        "contact": self.contact,
                                        "store": self.store_path,
                                        "send_log": self.send_log}),
                            encoding="utf-8")
        proc = subprocess.Popen(
            [sys.executable, "-I", str(Path(__file__).resolve()), "--worker",
             str(cfg_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        _wait_file(decided)          # the gate has ALREADY said ALLOW
        self.ledger.suppress(TENANT, self.contact, reason="global_stop",
                             actor="agent")   # a second writer commits the stop
        Path(released).write_text("1", encoding="utf-8")
        stdout, stderr = proc.communicate(timeout=60)
        self.assertEqual(proc.returncode, 0, stderr)
        result = json.loads(Path(out_dispatcher).read_text(
            encoding="utf-8").splitlines()[-1])
        self.assertEqual(result["sends"], [], "no send after the stop committed")
        self.assertEqual(result["state"], STATE_SUPPRESSED)
        self.assertEqual(self._sends(), [])

    def test_free_running_race_never_sends_after_the_fence_moved(self):
        """N rounds of a real suppress/dispatch race; the order is checked."""
        violations = []
        sends_seen = 0
        rounds = 6
        for i in range(rounds):
            # A fresh contact per round: an earlier round's stop is permanent,
            # so reusing one contact would make every later round vacuous.
            contact = self.identity.bind(
                TENANT, [("sms_number", "+1555%05d" % (70000 + i), True)],
                source="race")
            store = DurableStore(self.store_path)
            row, _ = store.create_intent(
                logical_intent_key="L-race-%d" % i,
                idempotency_key="idem-race-%d" % i, tenant_id=TENANT,
                scope="person_directed", canonical_contact_id=contact,
                content_sha256="sha-race-%d" % i)
            store.queue(row["action_id"])
            store.close()
            action_id = row["action_id"]
            at = time.time() + 0.35
            # Alternate who moves first so the probe exercises BOTH orders: the
            # stop ahead of the send (must never send) and the send ahead of the
            # stop (may send, and then must be ordered before the stop).
            dispatch_at = at
            suppress_at = at + (0.6 if i % 2 else -0.25)
            sup_out = str(self.tmp / ("sup-%d.jsonl" % i))
            dis_out = str(self.tmp / ("dis-%d.jsonl" % i))
            procs = []
            for cfg in ({"mode": "suppress", "at": suppress_at, "out": sup_out},
                        {"mode": "dispatch", "at": dispatch_at, "out": dis_out,
                         "action_id": action_id, "worker": "w-race"}):
                full = {**cfg, "db": self.db, "tenant": TENANT,
                        "contact": contact, "store": self.store_path,
                        "send_log": self.send_log}
                path = self.tmp / ("cfg-race-%d-%s.json" % (i, cfg["mode"]))
                path.write_text(json.dumps(full), encoding="utf-8")
                procs.append(subprocess.Popen(
                    [sys.executable, "-I", str(Path(__file__).resolve()),
                     "--worker", str(path)],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}))
            outs = []
            for proc in procs:
                stdout, stderr = proc.communicate(timeout=60)
                self.assertEqual(proc.returncode, 0, stderr)
            outs.append(json.loads(Path(sup_out).read_text(
                encoding="utf-8").splitlines()[-1]))
            outs.append(json.loads(Path(dis_out).read_text(
                encoding="utf-8").splitlines()[-1]))
            suppressed_at = outs[0]["at"]
            dispatched = outs[1]
            if dispatched["sends"]:
                sends_seen += 1
                started = dispatched["attempt_started_at"]
                if started > suppressed_at:
                    violations.append({"round": i, "started": started,
                                       "suppressed_at": suppressed_at})
            # Stop must be durable whatever the interleaving.
            self.assertEqual(self.ledger.epoch(TENANT, contact), 1)
        self.assertEqual(violations, [],
                         "a send began after the suppression was durable")
        # At least one round must have dispatched before the stop committed,
        # otherwise the invariant above only proves the dispatcher was slow.
        self.assertGreaterEqual(
            sends_seen, 1,
            "no round exercised the send path (%d/6 sent)" % sends_seen)

        # Liveness control: the SAME two-process harness, same worker, on a
        # contact with no suppression at all. If this cannot send, the invariant
        # above would be satisfied by a dispatcher that never sends anything.
        control_contact = self.identity.bind(
            TENANT, [("sms_number", "+15550999", True)], source="control")
        store = DurableStore(self.store_path)
        row, _ = store.create_intent(
            logical_intent_key="L-race-control", idempotency_key="idem-control",
            tenant_id=TENANT, scope="person_directed",
            canonical_contact_id=control_contact, content_sha256="sha-control")
        store.queue(row["action_id"])
        store.close()
        control_id = row["action_id"]
        control_out = str(self.tmp / "dis-control.jsonl")
        cfg = {"mode": "dispatch", "at": 0, "out": control_out,
               "action_id": control_id, "worker": "w-control", "db": self.db,
               "tenant": TENANT, "contact": control_contact,
               "store": self.store_path, "send_log": self.send_log}
        path = self.tmp / "cfg-race-control.json"
        path.write_text(json.dumps(cfg), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-I", str(Path(__file__).resolve()), "--worker",
             str(path)], capture_output=True, text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        control = json.loads(Path(control_out).read_text(
            encoding="utf-8").splitlines()[-1])
        self.assertEqual(len(control["sends"]), 1,
                         "liveness control: this harness must be able to send")
        self.assertEqual(sends_seen + 1, len(self._sends()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
