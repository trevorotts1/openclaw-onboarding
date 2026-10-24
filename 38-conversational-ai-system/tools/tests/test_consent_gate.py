#!/usr/bin/env python3
"""Tests for T-18 consent: scoped refusal, global opt-out, human precedence,
partial capture, and the fresh gate at dispatch time.

Contract basis: DATA-CONTRACTS section 7 ("Capture, refusal and one SMS email
ask") and section 3 (fresh gate before every dispatch and retry).

Run from the skill root:
    python3 -m unittest discover -s tools/tests -p 'test_consent_gate.py' -v
or directly:
    python3 tools/tests/test_consent_gate.py

What is proven here:

  SCOPE       a topic/campaign/offer refusal blocks that ask only; a channel
              opt-out blocks that channel only; a global stop blocks every
              channel; an unresolved channel is not broader permission.

  STOP        a global stop survives a process restart and blocks a dispatch
              performed by a DIFFERENT process, across channels.

  HUMAN       human takeover fences the bot; a grant does NOT release it; an
              explicit release does; the fence survives a restart.

  CAPTURE     a capture interrupted by a real crashing process resumes at its
              own cursor in a new process without re-running a step; a
              rejected capture stays rejected across processes.

  FRESH GATE  a suppression recorded AFTER the action was queued still blocks
              the send through outbound_gate.dispatch(), and the provider is
              never called; a different topic still sends.

Every multi-process case uses real child interpreters (`--worker <cfg.json>`),
not threads, against one SQLite database on disk.
"""

import contextlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parents[1]
TESTS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from collection_lock import (  # noqa: E402
    CaptureIncomplete,
    CaptureRejected,
    CollectionLock,
)
from consent_gate import (  # noqa: E402
    ConsentCapture,
    ConsentError,
    ConsentStore,
    DECISION_GRANT,
    DECISION_REFUSE,
    REASON_CHANNEL,
    REASON_CHANNEL_UNRESOLVED,
    REASON_FIELD,
    REASON_GLOBAL,
    REASON_HUMAN,
    SCOPE_CAMPAIGN,
    SCOPE_CHANNEL,
    SCOPE_GLOBAL,
    SCOPE_OFFER,
    SCOPE_TOPIC,
    make_gate_evaluator,
)
from durable_store import DurableStore, STATE_SUPPRESSED  # noqa: E402
from outbound_gate import ST_BLOCKED, ST_SENT, dispatch  # noqa: E402
from tenant_identity import TenantIdentity, VerificationError  # noqa: E402

TENANT = "t1"
SEQ = "seq-1"


# ══════════════════════════════════════════════════════════════════════════
# worker process (real second interpreter)
# ══════════════════════════════════════════════════════════════════════════

def _emit(path, payload):
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")
        handle.flush()


def _wait(path, timeout=30.0):
    deadline = time.time() + timeout
    while not Path(path).exists():
        if time.time() > deadline:
            raise AssertionError("barrier timeout: " + str(path))
        time.sleep(0.002)


def _acquire_for_resume(lock, owner, lease_seconds=5.0):
    """Acquire, or hand over a dead writer's expired lease, then acquire."""
    deadline = time.time() + 20.0
    while True:
        lease = lock.acquire(TENANT, CFG_CONTACT, SEQ, owner,
                             lease_seconds=lease_seconds)
        if lease.granted:
            return lease
        if lease.reason == "reconcile_required":
            lock.reconcile(TENANT, CFG_CONTACT, SEQ, owner, lease.fence)
            continue
        if time.time() > deadline:
            raise AssertionError("could not acquire: " + lease.reason)
        time.sleep(min(lease.retry_after or 0.01, 0.05))


CFG_CONTACT = ""


def _worker(cfg_path):
    global CFG_CONTACT
    with open(cfg_path, encoding="utf-8") as handle:
        cfg = json.load(handle)
    CFG_CONTACT = cfg["contact"]
    identity = TenantIdentity(cfg["db"])
    consent = ConsentStore(identity)
    mode = cfg["mode"]
    out = cfg["out"]
    tenant, contact = cfg["tenant"], cfg["contact"]

    if mode == "stop":
        row = consent.global_stop(tenant, contact, reason="customer said stop",
                                  actor="agent")
        _emit(out, {"ok": True, "seq": row["seq"]})
        return 0

    if mode == "takeover":
        consent.human_takeover(tenant, contact, actor="jill", reason="human reply")
        _emit(out, {"ok": True, "fence": consent.human_fence(tenant, contact)})
        return 0

    if mode == "dispatch":
        store = DurableStore(cfg["store"])
        evaluator = make_gate_evaluator(consent)
        sends = []

        def sender(ctx):
            sends.append(ctx["action_id"])
            with open(cfg["send_log"], "a", encoding="utf-8") as handle:
                handle.write(ctx["action_id"] + "\n")
                handle.flush()
            return {"provider": "ghl", "provider_receipt_id": "r-" + ctx["action_id"]}

        result = dispatch(store, evaluator, sender, cfg["action_id"], cfg["worker"],
                          context=cfg.get("context") or {})
        _emit(out, {"ok": True, "status": result.status,
                    "verdict": result.verdict, "sends": sends})
        store.close()
        return 0

    if mode == "capture_crash":
        lock = CollectionLock(identity)
        capture = ConsentCapture(lock, consent)
        lease = _acquire_for_resume(lock, "crasher", lease_seconds=0.5)
        capture.begin(tenant, contact, SEQ, cfg["capture"], cfg["steps"],
                      owner_id="crasher", fence=lease.fence)
        capture.record_step(tenant, contact, SEQ, cfg["capture"], 0,
                            decision=DECISION_REFUSE,
                            scope_kind=SCOPE_CHANNEL, scope_value="sms",
                            owner_id="crasher", fence=lease.fence)
        _emit(out, {"ok": True, "cursor": 1, "fence": lease.fence})
        os._exit(9)  # crash mid-capture: no release, no complete, no reject

    if mode == "capture_resume":
        lock = CollectionLock(identity)
        capture = ConsentCapture(lock, consent)
        lease = _acquire_for_resume(lock, "resumer")
        state = capture.begin(tenant, contact, SEQ, cfg["capture"], cfg["steps"],
                              owner_id="resumer", fence=lease.fence)
        cursor = state["cursor"]
        for step in cfg["remaining"]:
            capture.record_step(tenant, contact, SEQ, cfg["capture"],
                                step["step_index"], decision=step["decision"],
                                scope_kind=step["scope_kind"],
                                scope_value=step["scope_value"],
                                owner_id="resumer", fence=lease.fence)
        if cfg.get("complete"):
            state = capture.complete(tenant, contact, SEQ, cfg["capture"],
                                     owner_id="resumer", fence=lease.fence)
        _emit(out, {"ok": True, "resumed_at": cursor, "state": state["state"],
                    "cursor": state["cursor"]})
        return 0

    if mode == "capture_reject":
        lock = CollectionLock(identity)
        capture = ConsentCapture(lock, consent)
        lease = _acquire_for_resume(lock, "decliner")
        capture.begin(tenant, contact, SEQ, cfg["capture"], cfg["steps"],
                      owner_id="decliner", fence=lease.fence)
        capture.record_step(tenant, contact, SEQ, cfg["capture"], 0,
                            decision=DECISION_REFUSE,
                            scope_kind=SCOPE_CHANNEL, scope_value="sms",
                            owner_id="decliner", fence=lease.fence)
        state = capture.reject(tenant, contact, SEQ, cfg["capture"],
                               reason="declined:final collection",
                               owner_id="decliner", fence=lease.fence)
        _emit(out, {"ok": True, "state": state["state"]})
        return 0

    if mode == "capture_after_reject":
        lock = CollectionLock(identity)
        capture = ConsentCapture(lock, consent)
        lease = _acquire_for_resume(lock, "late")
        state = capture.begin(tenant, contact, SEQ, cfg["capture"], cfg["steps"],
                              owner_id="late", fence=lease.fence)
        refused = None
        try:
            capture.record_step(tenant, contact, SEQ, cfg["capture"], 1,
                                decision=DECISION_GRANT,
                                scope_kind=SCOPE_CHANNEL, scope_value="email",
                                owner_id="late", fence=lease.fence)
        except CaptureRejected as exc:
            refused = "CaptureRejected:" + str(exc)
        _emit(out, {"ok": True, "state": state["state"],
                    "cursor": state["cursor"], "refused": refused})
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
        self.tmp = Path(tempfile.mkdtemp(prefix="t18-"))
        self.db = str(self.tmp / "consent.sqlite")
        self.store_path = str(self.tmp / "outbox.sqlite")
        self.send_log = str(self.tmp / "sends.log")
        self.identity = TenantIdentity(self.db)
        self.identity.register_tenant(TENANT, "purple billboard")
        self.contact = self.identity.bind(
            TENANT, [("sms_number", "+15550123", True)], source="test")
        self.consent = ConsentStore(self.identity)

    # ── helpers ───────────────────────────────────────────────────────────

    def _run_worker(self, cfg, expect_rc=0):
        cfg = dict(cfg)
        cfg.setdefault("db", self.db)
        cfg.setdefault("tenant", TENANT)
        cfg.setdefault("contact", self.contact)
        cfg.setdefault("store", self.store_path)
        cfg.setdefault("send_log", self.send_log)
        cfg.setdefault("out", str(self.tmp / "worker-out.jsonl"))
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

    def _sends(self):
        p = Path(self.send_log)
        if not p.exists():
            return []
        return [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln]

    def _new_queued(self, key, contact=True, scope="person_directed"):
        store = DurableStore(self.store_path)
        kwargs = {"canonical_contact_id": self.contact} if contact else {}
        row, _ = store.create_intent(
            logical_intent_key=key, idempotency_key="idem-" + key,
            tenant_id=TENANT, scope=scope, content_sha256="sha-" + key, **kwargs)
        store.queue(row["action_id"])
        store.close()
        return row["action_id"]

    def _dispatch(self, action_id, *, context=None, worker="w1",
                  expect_sent=True):
        store = DurableStore(self.store_path)
        evaluator = make_gate_evaluator(self.consent)
        sends = []

        def sender(ctx):
            sends.append(ctx["action_id"])
            with open(self.send_log, "a", encoding="utf-8") as handle:
                handle.write(ctx["action_id"] + "\n")
            return {"provider": "ghl",
                    "provider_receipt_id": "r-" + ctx["action_id"]}

        result = dispatch(store, evaluator, sender, action_id, worker,
                          context=context or {})
        row = store.get_action(action_id)
        store.close()
        self.assertEqual(bool(sends), expect_sent,
                         "sender called=%s status=%s" % (bool(sends), result.status))
        return result, row

    @contextlib.contextmanager
    def _collector(self, owner="collector", lease_seconds=30.0):
        lock = CollectionLock(self.identity)
        lease = lock.acquire(TENANT, self.contact, SEQ, owner,
                             lease_seconds=lease_seconds)
        self.assertTrue(lease.granted, "acquire failed: " + lease.reason)
        try:
            yield lock, lease
        finally:
            try:
                lock.release(TENANT, self.contact, SEQ, owner, lease.fence)
            except Exception:
                pass


# ══════════════════════════════════════════════════════════════════════════
# 1. SCOPED REFUSAL
# ══════════════════════════════════════════════════════════════════════════

class TestScopedRefusal(_Base):
    def test_topic_refusal_blocks_that_topic_only(self):
        self.consent.refuse(TENANT, self.contact, scope_kind=SCOPE_TOPIC,
                            scope_value="pricing")
        blocked = self.consent.decide(TENANT, self.contact, channel="sms",
                                      topic="pricing")
        allowed = self.consent.decide(TENANT, self.contact, channel="sms",
                                      topic="onboarding")
        self.assertFalse(blocked["allowed"])
        self.assertEqual(blocked["reason"], REASON_FIELD)
        self.assertEqual(blocked["blocking"]["scope_value"], "pricing")
        self.assertTrue(allowed["allowed"], "a topic refusal must not block another ask")

    def test_channel_opt_out_blocks_that_channel_only(self):
        self.consent.refuse(TENANT, self.contact, scope_kind=SCOPE_CHANNEL,
                            scope_value="sms")
        sms = self.consent.decide(TENANT, self.contact, channel="sms")
        email = self.consent.decide(TENANT, self.contact, channel="email")
        self.assertFalse(sms["allowed"])
        self.assertEqual(sms["reason"], REASON_CHANNEL)
        self.assertTrue(email["allowed"], "channel opt-out must not block another channel")

    def test_offer_and_campaign_refusals_are_narrow(self):
        self.consent.refuse(TENANT, self.contact, scope_kind=SCOPE_OFFER,
                            scope_value="pass-only")
        self.consent.refuse(TENANT, self.contact, scope_kind=SCOPE_CAMPAIGN,
                            scope_value="spring")
        self.assertFalse(self.consent.decide(
            TENANT, self.contact, channel="sms", offer="pass-only")["allowed"])
        self.assertTrue(self.consent.decide(
            TENANT, self.contact, channel="sms", offer="full-bonus")["allowed"])
        self.assertFalse(self.consent.decide(
            TENANT, self.contact, channel="email", campaign="spring")["allowed"])
        self.assertTrue(self.consent.decide(
            TENANT, self.contact, channel="email", campaign="autumn")["allowed"])

    def test_unknown_channel_is_not_broader_permission(self):
        self.consent.refuse(TENANT, self.contact, scope_kind=SCOPE_CHANNEL,
                            scope_value="sms")
        verdict = self.consent.decide(TENANT, self.contact)
        self.assertFalse(verdict["allowed"])
        self.assertEqual(verdict["reason"], REASON_CHANNEL_UNRESOLVED)
        self.assertTrue(verdict["evidence"]["unknown_scope_is_not_permission"])

    def test_grant_lifts_only_its_own_scope(self):
        self.consent.refuse(TENANT, self.contact, scope_kind=SCOPE_CHANNEL,
                            scope_value="sms")
        self.consent.refuse(TENANT, self.contact, scope_kind=SCOPE_TOPIC,
                            scope_value="pricing")
        self.consent.grant(TENANT, self.contact, scope_kind=SCOPE_CHANNEL,
                           scope_value="sms")
        self.assertTrue(self.consent.decide(TENANT, self.contact, channel="sms")["allowed"])
        self.assertFalse(self.consent.decide(
            TENANT, self.contact, channel="sms", topic="pricing")["allowed"])

    def test_refusal_is_tenant_scoped_and_needs_a_real_contact(self):
        other = TenantIdentity(str(self.tmp / "other.sqlite"))
        other.register_tenant("t2")
        foreign = other.bind("t2", [("email", "a@example.com", True)])
        with self.assertRaises(VerificationError):
            ConsentStore(other).refuse("t2", self.contact,
                                       scope_kind=SCOPE_GLOBAL)
        with self.assertRaises(VerificationError):
            self.consent.decide(TENANT, foreign, channel="sms")

    def test_bad_scope_input_is_refused(self):
        with self.assertRaises(ConsentError):
            self.consent.refuse(TENANT, self.contact, scope_kind="everything")
        with self.assertRaises(ConsentError):
            self.consent.refuse(TENANT, self.contact, scope_kind=SCOPE_CHANNEL)
        with self.assertRaises(ConsentError):
            self.consent.refuse(TENANT, self.contact, scope_kind=SCOPE_GLOBAL,
                                scope_value="sms")


# ══════════════════════════════════════════════════════════════════════════
# 2. GLOBAL OPT-OUT
# ══════════════════════════════════════════════════════════════════════════

class TestGlobalStop(_Base):
    def test_global_stop_blocks_every_channel_and_topic(self):
        self.consent.global_stop(TENANT, self.contact, actor="agent")
        for channel, topic in (("sms", None), ("email", None), ("facebook", "pricing"),
                               (None, None)):
            verdict = self.consent.decide(TENANT, self.contact,
                                          channel=channel, topic=topic)
            self.assertFalse(verdict["allowed"], "global stop must block %s" % channel)
            self.assertEqual(verdict["reason"], REASON_GLOBAL)

    def test_global_stop_survives_restart(self):
        self.consent.global_stop(TENANT, self.contact)
        del self.consent
        reopened_identity = TenantIdentity(self.db)   # new process-like handle
        reopened = ConsentStore(reopened_identity)
        self.assertFalse(reopened.decide(TENANT, self.contact, channel="email")["allowed"])
        self.assertEqual(len(reopened.active_refusals(TENANT, self.contact)), 1)

    def test_global_stop_written_by_another_process_blocks_dispatch(self):
        action_id = self._new_queued("L-across")
        worker = self._run_worker({"mode": "stop"})
        self.assertTrue(worker["ok"])
        # This process never saw the stop; a third process performs the dispatch.
        result = self._run_worker({"mode": "dispatch", "action_id": action_id,
                                   "worker": "w2",
                                   "context": {"channel": "facebook"}})
        self.assertEqual(result["status"], ST_BLOCKED)
        self.assertEqual(result["verdict"], "SUPPRESSED")
        self.assertEqual(result["sends"], [])
        self.assertEqual(self._sends(), [], "provider must never be called")

    def test_legacy_identity_suppression_is_honoured(self):
        with self.identity.write_transaction() as conn:
            conn.execute(
                "UPDATE contacts SET suppression = 'global_stop'"
                " WHERE tenant_id = ? AND canonical_contact_id = ?",
                (TENANT, self.contact))
        verdict = self.consent.decide(TENANT, self.contact, channel="sms")
        self.assertFalse(verdict["allowed"])
        self.assertEqual(verdict["reason"], "consent:global_stop_recorded_in_identity")


# ══════════════════════════════════════════════════════════════════════════
# 3. HUMAN PRECEDENCE
# ══════════════════════════════════════════════════════════════════════════

class TestHumanPrecedence(_Base):
    def test_takeover_fences_all_channels_and_survives_restart(self):
        self.consent.human_takeover(TENANT, self.contact, actor="jill",
                                    reason="human took the thread")
        for channel in ("sms", "email", "facebook"):
            verdict = self.consent.decide(TENANT, self.contact, channel=channel)
            self.assertFalse(verdict["allowed"])
            self.assertEqual(verdict["reason"], REASON_HUMAN)
        reopened = ConsentStore(TenantIdentity(self.db))
        self.assertFalse(reopened.decide(TENANT, self.contact, channel="sms")["allowed"])
        fence = reopened.human_fence(TENANT, self.contact)
        self.assertTrue(fence["active"])
        self.assertEqual(fence["actor"], "jill")
        self.assertEqual(fence["revision"], 1)

    def test_a_grant_does_not_release_the_fence(self):
        self.consent.human_takeover(TENANT, self.contact, actor="jill")
        self.consent.grant(TENANT, self.contact, scope_kind=SCOPE_GLOBAL,
                           actor="agent")
        self.consent.grant(TENANT, self.contact, scope_kind=SCOPE_CHANNEL,
                           scope_value="sms", actor="agent")
        verdict = self.consent.decide(TENANT, self.contact, channel="sms")
        self.assertFalse(verdict["allowed"], "only an explicit release may resume")
        self.assertEqual(verdict["reason"], REASON_HUMAN)

    def test_explicit_release_re_enables_and_is_audited(self):
        self.consent.human_takeover(TENANT, self.contact, actor="jill")
        released = self.consent.human_release(TENANT, self.contact,
                                              actor="jill", reason="handed back")
        self.assertFalse(released["active"])
        self.assertEqual(released["revision"], 2)
        self.assertTrue(self.consent.decide(
            TENANT, self.contact, channel="sms")["allowed"])
        events = [e["action"] for e in
                  self.consent.fence_events(TENANT, self.contact)]
        self.assertEqual(events, ["takeover", "release"])
        with self.assertRaises(ConsentError):
            self.consent.human_release(TENANT, self.contact, actor="jill")

    def test_takeover_in_another_process_blocks_dispatch_until_release(self):
        action_id = self._new_queued("L-human")
        worker = self._run_worker({"mode": "takeover"})
        self.assertTrue(worker["fence"]["active"])
        result = self._run_worker({"mode": "dispatch", "action_id": action_id,
                                   "worker": "w2", "context": {"channel": "sms"}})
        self.assertEqual(result["status"], ST_BLOCKED)
        self.assertEqual(result["verdict"], "SUPPRESSED")
        self.assertEqual(self._sends(), [])
        store = DurableStore(self.store_path)
        self.assertEqual(store.get_action(action_id)["state"], STATE_SUPPRESSED)
        store.close()

        self.consent.human_release(TENANT, self.contact, actor="jill")
        # The action the fence blocked stays suppressed (a gate verdict is
        # terminal); the release re-enables the SYSTEM, proven by a new action.
        fresh_id = self._new_queued("L-human-after")
        result = self._run_worker({"mode": "dispatch", "action_id": fresh_id,
                                   "worker": "w3", "context": {"channel": "sms"}})
        self.assertEqual(result["status"], ST_SENT)
        self.assertEqual(len(self._sends()), 1, "release re-enables exactly one send")


# ══════════════════════════════════════════════════════════════════════════
# 4. PARTIAL CAPTURE
# ══════════════════════════════════════════════════════════════════════════

class TestPartialCapture(_Base):
    STEPS = ["sms", "email", "pricing"]

    def test_interrupted_capture_resumes_in_a_new_process(self):
        crashed = self._run_worker({"mode": "capture_crash", "capture": "cap-1",
                                    "steps": self.STEPS}, expect_rc=9)
        self.assertEqual(crashed["cursor"], 1)

        resumed = self._run_worker({
            "mode": "capture_resume", "capture": "cap-1", "steps": self.STEPS,
            "remaining": [
                {"step_index": 1, "decision": DECISION_GRANT,
                 "scope_kind": SCOPE_CHANNEL, "scope_value": "email"},
                {"step_index": 2, "decision": DECISION_REFUSE,
                 "scope_kind": SCOPE_TOPIC, "scope_value": "pricing"},
            ],
            "complete": True,
        })
        self.assertEqual(resumed["resumed_at"], 1,
                         "resume must start at the durable cursor, not step 0")
        self.assertEqual(resumed["state"], "complete")
        self.assertEqual(resumed["cursor"], 3)

        steps = [r["step_index"] for r in self.consent.decisions(
            TENANT, self.contact) if r["capture_id"] == "cap-1"]
        self.assertEqual(sorted(steps), [0, 1, 2],
                         "each step has exactly one decision: step 0 was not rerun")
        self.assertTrue(self.consent.decide(
            TENANT, self.contact, channel="email")["allowed"])
        self.assertFalse(self.consent.decide(
            TENANT, self.contact, channel="sms")["allowed"])
        self.assertFalse(self.consent.decide(
            TENANT, self.contact, channel="email", topic="pricing")["allowed"])

    def test_capture_restart_in_process_keeps_its_cursor(self):
        with self._collector("a") as (lock, lease):
            capture = ConsentCapture(lock, self.consent)
            capture.begin(TENANT, self.contact, SEQ, "cap-2", self.STEPS,
                          owner_id="a", fence=lease.fence)
            capture.record_step(TENANT, self.contact, SEQ, "cap-2", 0,
                                decision=DECISION_REFUSE,
                                scope_kind=SCOPE_CHANNEL, scope_value="sms",
                                owner_id="a", fence=lease.fence)
        # A different lock instance and a fresh ConsentStore: a restart.
        restarted = ConsentStore(TenantIdentity(self.db))
        with self._collector("b") as (lock2, lease2):
            capture = ConsentCapture(lock2, restarted)
            state = capture.begin(TENANT, self.contact, SEQ, "cap-2", self.STEPS,
                                  owner_id="b", fence=lease2.fence)
            self.assertEqual(state["cursor"], 1, "never restarted from scratch")
            replay = capture.record_step(TENANT, self.contact, SEQ, "cap-2", 0,
                                         decision=DECISION_REFUSE,
                                         scope_kind=SCOPE_CHANNEL,
                                         scope_value="sms",
                                         owner_id="b", fence=lease2.fence)
            self.assertEqual(replay["cursor"], 1, "a replay must not advance twice")
            capture.record_step(TENANT, self.contact, SEQ, "cap-2", 1,
                                decision=DECISION_GRANT,
                                scope_kind=SCOPE_CHANNEL, scope_value="email",
                                owner_id="b", fence=lease2.fence)
            with self.assertRaises(CaptureIncomplete):
                capture.complete(TENANT, self.contact, SEQ, "cap-2",
                                 owner_id="b", fence=lease2.fence)
        with self._collector("c") as (lock3, lease3):
            capture = ConsentCapture(lock3, restarted)
            state = capture.begin(TENANT, self.contact, SEQ, "cap-2", self.STEPS,
                                  owner_id="c", fence=lease3.fence)
            self.assertEqual(state["state"], "in_progress")
            self.assertEqual(state["cursor"], 2, "premature complete stays resumable")
            capture.record_step(TENANT, self.contact, SEQ, "cap-2", 2,
                                decision=DECISION_REFUSE,
                                scope_kind=SCOPE_TOPIC, scope_value="pricing",
                                owner_id="c", fence=lease3.fence)
            done = capture.complete(TENANT, self.contact, SEQ, "cap-2",
                                    owner_id="c", fence=lease3.fence)
        self.assertEqual(done["state"], "complete")

    def test_rejected_capture_stays_rejected_across_processes(self):
        first = self._run_worker({"mode": "capture_reject", "capture": "cap-3",
                                  "steps": self.STEPS})
        self.assertEqual(first["state"], "rejected")
        late = self._run_worker({"mode": "capture_after_reject",
                                 "capture": "cap-3", "steps": self.STEPS})
        self.assertEqual(late["state"], "rejected",
                         "a rejected capture can never reopen")
        self.assertEqual(late["cursor"], 1, "its cursor is preserved, not reset")
        self.assertIsNotNone(late["refused"])
        self.assertTrue(late["refused"].startswith("CaptureRejected"))
        self.assertEqual(len(self.consent.decisions(TENANT, self.contact)), 1,
                         "a refused step writes no decision")


# ══════════════════════════════════════════════════════════════════════════
# 5. FRESH GATE AT DISPATCH TIME
# ══════════════════════════════════════════════════════════════════════════

class TestFreshGateAtDispatch(_Base):
    def test_suppression_recorded_after_queueing_blocks_the_send(self):
        action_id = self._new_queued("L-fresh")
        self.consent.global_stop(TENANT, self.contact, reason="stop after queue")
        result, row = self._dispatch(action_id, context={"channel": "sms"},
                                     expect_sent=False)
        self.assertEqual(result.status, ST_BLOCKED)
        self.assertEqual(result.verdict, "SUPPRESSED")
        self.assertEqual(row["state"], STATE_SUPPRESSED)
        self.assertEqual(self._sends(), [])

    def test_narrow_refusal_after_queueing_blocks_only_its_ask(self):
        blocked_id = self._new_queued("L-narrow-a")
        allowed_id = self._new_queued("L-narrow-b")
        self.consent.refuse(TENANT, self.contact, scope_kind=SCOPE_TOPIC,
                            scope_value="pricing")
        blocked, row = self._dispatch(
            blocked_id, context={"channel": "sms", "topic": "pricing"},
            expect_sent=False)
        self.assertEqual(blocked.status, ST_BLOCKED)
        self.assertIn("field_refusal", blocked.note)

        allowed, row2 = self._dispatch(
            allowed_id, context={"channel": "sms", "topic": "onboarding"},
            expect_sent=True)
        self.assertEqual(allowed.status, ST_SENT)
        self.assertEqual(len(self._sends()), 1)

    def test_human_fence_after_queueing_blocks_the_send(self):
        action_id = self._new_queued("L-fence")
        self.consent.human_takeover(TENANT, self.contact, actor="jill")
        result, row = self._dispatch(action_id, context={"channel": "email"},
                                     expect_sent=False)
        self.assertEqual(result.status, ST_BLOCKED)
        self.assertEqual(row["state"], STATE_SUPPRESSED)

    def test_public_placement_has_no_person_and_is_not_suppressed(self):
        action_id = self._new_queued("L-public", contact=False,
                                     scope="public_placement")
        self.consent.global_stop(TENANT, self.contact)
        result, _ = self._dispatch(action_id, context={"channel": "facebook"},
                                   expect_sent=True)
        self.assertEqual(result.status, ST_SENT)

    def test_suppressed_action_stays_suppressed_after_a_later_grant(self):
        action_id = self._new_queued("L-recheck")
        self.consent.global_stop(TENANT, self.contact)
        blocked, row = self._dispatch(action_id, context={"channel": "sms"},
                                      expect_sent=False)
        self.assertEqual(blocked.status, ST_BLOCKED)
        self.assertEqual(row["state"], STATE_SUPPRESSED)
        self.consent.lift_global_stop(TENANT, self.contact)
        again, row2 = self._dispatch(action_id, context={"channel": "sms"},
                                     expect_sent=False)
        self.assertNotEqual(again.status, ST_SENT)
        self.assertEqual(row2["state"], STATE_SUPPRESSED,
                         "a suppressed action is terminal; a grant cannot resurrect it")
        self.assertEqual(self._sends(), [], "the gate verdict is never reused")


# ══════════════════════════════════════════════════════════════════════════
# 6. MODULE SELF-CHECK
# ══════════════════════════════════════════════════════════════════════════

class TestModuleSelfCheck(unittest.TestCase):
    def test_consent_gate_selfcheck(self):
        proc = subprocess.run(
            [sys.executable, "-I", str(TOOLS_DIR / "consent_gate.py")],
            capture_output=True, text=True, env=dict(os.environ))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("PASS", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
