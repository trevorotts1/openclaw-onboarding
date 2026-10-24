#!/usr/bin/env python3
"""T-17: shared reminder slots and the reserved final-action window.

Acceptance (build.json T-17): "Initial invite separate, three total, no reset,
pause/window/STOP race, reserved final action and actual terminal stop."
Criteria C-17 / C-F02 / C-F05 / C-F06 / C-F19.

Run from the repo root:
    python3 -m unittest discover -s shared-utils/reminders/tests -v
or directly:
    python3 shared-utils/reminders/tests/test_reminder_state_machine.py

Every case is free: no network, no model, no paid call, no live send. The
crash case uses a real child interpreter, not a thread.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
REPO = PKG.parents[1]
UPSTREAM = REPO / "38-conversational-ai-system" / "tools"
for path in (str(PKG), str(UPSTREAM)):
    if path not in sys.path:
        sys.path.insert(0, path)

import consent_gate as cg  # noqa: E402
import outbound_gate as og  # noqa: E402
import reminder_state_machine as rsm  # noqa: E402
from durable_store import DurableStore  # noqa: E402
from tenant_identity import TenantIdentity  # noqa: E402

TENANT = "tenant-pb"
POLICY = rsm.ReminderPolicy(
    version="pb/reminders/v1",
    slot_offsets_seconds=(10.0, 25.0, 150.0),
    quiet_interval_seconds=60.0,
    final_slot_seconds=600.0,
)
SEQ = "seq-main"


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t17-"))
        self.db = str(self.tmp / "identity.sqlite")
        self.outbox = str(self.tmp / "outbox.sqlite")
        self.identity = TenantIdentity(self.db)
        self.identity.register_tenant(TENANT, "purple billboard")
        self.contact = self.identity.bind(
            TENANT, [("sms_number", "+15550177", True)], source="t17")
        self.store = DurableStore(self.outbox)
        self.machine = rsm.ReminderStateMachine(self.identity, self.store)
        self.sends = []

    def tearDown(self):
        try:
            self.store.close()
        except Exception:
            pass

    # ── helpers ───────────────────────────────────────────────────────────

    def fresh(self, contact_label="+15550178"):
        """A second verified contact on the same tenant."""
        return self.identity.bind(
            TENANT, [("sms_number", contact_label, True)], source="t17")

    def sender(self):
        def send(ctx):
            self.sends.append(ctx["action_id"])
            return {"provider": "sms", "message_id": ctx["action_id"]}
        return send

    def exploding_sender(self):
        def send(ctx):
            raise RuntimeError("provider connection lost mid-send")
        return send

    def ready(self, seq=SEQ, contact=None, now=1010.0):
        contact = contact or self.contact
        self.machine.open_sequence(TENANT, contact, seq, request_id="req-1",
                                   now=now - 10)
        self.machine.adopt_policy(TENANT, contact, seq, POLICY, now=now - 8)
        self.machine.record_initial_invitation(
            TENANT, contact, seq, invitation_id="inv-1", now=now)
        return contact

    def snap(self, seq=SEQ, contact=None):
        return self.machine.snapshot(TENANT, contact or self.contact, seq)

    def run_worker(self, cfg, expect_rc=0):
        cfg = dict(cfg)
        cfg.setdefault("db", self.db)
        cfg.setdefault("store", self.outbox)
        cfg.setdefault("tenant", TENANT)
        cfg.setdefault("contact", self.contact)
        cfg.setdefault("out", str(self.tmp / "worker-out.jsonl"))
        cfg.setdefault("seq", SEQ)
        cfg_path = self.tmp / ("cfg-%s.json" % cfg["mode"])
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-I", str(Path(__file__).resolve()),
             "--worker", str(cfg_path)],
            capture_output=True, text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(proc.returncode, expect_rc,
                         "worker rc=%s stdout=%s stderr=%s"
                         % (proc.returncode, proc.stdout, proc.stderr))
        lines = [ln for ln in Path(cfg["out"]).read_text(
            encoding="utf-8").splitlines() if ln.strip()]
        self.assertTrue(lines, "worker emitted nothing: " + proc.stderr)
        return json.loads(lines[-1])


class T01InitialInvitationSeparate(_Base):
    """Acceptance clause 1: the initial invite is separate from the three."""

    def test_invitation_is_not_a_reminder_slot(self):
        self.ready()
        snap = self.snap()
        self.assertEqual(snap["initial_invitation_id"], "inv-1")
        self.assertEqual(snap["reminders_used"], 0)
        self.assertEqual(snap["reminders_total"], 3)
        self.assertEqual([s["status"] for s in snap["slots"]],
                         ["pending", "pending", "pending"])
        self.assertNotIn("inv-1", [s["action_id"] for s in snap["slots"]])

    def test_activation_without_adopted_policy_is_refused(self):
        self.machine.open_sequence(TENANT, self.contact, SEQ, now=1000.0)
        with self.assertRaises(rsm.PolicyNotAdopted):
            self.machine.record_initial_invitation(
                TENANT, self.contact, SEQ, invitation_id="inv-x", now=1001.0)
        self.assertEqual(self.snap()["t0"], None)

    def test_repeated_invitation_keeps_t0_and_budget(self):
        self.ready()
        before = self.snap()
        self.machine.record_initial_invitation(
            TENANT, self.contact, SEQ, invitation_id="inv-2", now=1400.0)
        after = self.snap()
        self.assertEqual(after["t0"], before["t0"])
        self.assertEqual(after["initial_invitation_id"], "inv-1")
        self.assertEqual(after["reminders_total"], 3)
        self.assertEqual(after["reminders_used"], 0)
        events = [e["event"] for e in self.machine.events(TENANT, self.contact, SEQ)]
        self.assertIn("initial_invitation_repeated", events)

    def test_policy_refuses_a_fourth_slot(self):
        with self.assertRaises(rsm.InvalidPolicy):
            rsm.ReminderPolicy(version="bad",
                               slot_offsets_seconds=(1, 2, 3, 4))
class T02ThreeTotalShared(_Base):
    """Acceptance clause 2 + C-F02: three total, shared across FB/IG/SMS."""

    def test_three_shared_reminders_across_channels(self):
        self.ready()
        send = self.sender()
        r0 = self.machine.send_reminder(TENANT, self.contact, SEQ, send,
                                        channel="facebook", now=1020.0)
        r1 = self.machine.send_reminder(TENANT, self.contact, SEQ, send,
                                        channel="instagram", now=1081.0)
        r2 = self.machine.send_reminder(TENANT, self.contact, SEQ, send,
                                        channel="sms", now=1161.0)
        self.assertTrue(r0.sent and r1.sent and r2.sent)
        self.assertEqual(len(self.sends), 3)
        snap = self.snap()
        self.assertEqual(snap["reminders_used"], 3)
        self.assertEqual([s["channel"] for s in snap["slots"]],
                         ["facebook", "instagram", "sms"])

    def test_never_a_fourth_reminder(self):
        self.ready()
        send = self.sender()
        for at, channel in ((1020.0, "facebook"), (1081.0, "instagram"),
                            (1161.0, "sms")):
            self.assertTrue(
                self.machine.send_reminder(TENANT, self.contact, SEQ, send,
                                           channel=channel, now=at).sent)
        before = len(self.sends)
        # The budget is shared, so a different channel gets nothing either.
        for channel in ("facebook", "instagram", "sms"):
            out = self.machine.send_reminder(
                TENANT, self.contact, SEQ, send, channel=channel, now=5000.0)
            self.assertFalse(out.sent)
            self.assertEqual(out.reason, "no_slot_due")
        self.assertEqual(len(self.sends), before)
        self.assertEqual(self.snap()["reminders_total"], 3)

    def test_due_slot_returns_none_after_budget_exhausted(self):
        self.ready()
        send = self.sender()
        for at, channel in ((1020.0, "facebook"), (1081.0, "instagram"),
                            (1161.0, "sms")):
            self.machine.send_reminder(TENANT, self.contact, SEQ, send,
                                       channel=channel, now=at)
        decision = self.machine.due_slot(TENANT, self.contact, SEQ, now=9999.0)
        self.assertEqual(decision.kind, rsm.DECISION_NONE)


class T03NoReset(_Base):
    """Acceptance clause 3 + R-11: returning/overlapping requests never reset."""

    def test_overlapping_request_shares_the_sequence(self):
        self.ready()
        send = self.sender()
        self.machine.send_reminder(TENANT, self.contact, SEQ, send,
                                   channel="facebook", now=1020.0)
        before = self.snap()
        again = self.machine.open_sequence(TENANT, self.contact, "seq-new",
                                           request_id="req-2", now=1200.0)
        self.assertEqual(again["collection_sequence_id"], SEQ)
        after = self.snap()
        self.assertEqual(after["t0"], before["t0"])
        self.assertEqual(after["reminders_used"], 1)
        self.assertEqual(after["reminders_total"], 3)

    def test_restart_keeps_t0_budget_and_slots(self):
        self.ready()
        send = self.sender()
        self.machine.send_reminder(TENANT, self.contact, SEQ, send,
                                   channel="facebook", now=1020.0)
        before = self.snap()
        # A new process-like set of handles over the same files.
        identity = TenantIdentity(self.db)
        store = DurableStore(self.outbox)
        restarted = rsm.ReminderStateMachine(identity, store)
        after = restarted.snapshot(TENANT, self.contact, SEQ)
        self.assertEqual(after["t0"], before["t0"])
        self.assertEqual(after["reminders_used"], before["reminders_used"])
        self.assertEqual(after["version"], before["version"])
        # It continues at slot 2, it does not start over.
        out = restarted.send_reminder(TENANT, self.contact, SEQ, send,
                                      channel="instagram", now=1081.0)
        self.assertTrue(out.sent)
        self.assertEqual(out.slot_index, 1)
        store.close()

    def test_a_recorded_stop_is_not_restarted(self):
        self.ready()
        self.machine.consent.global_stop(TENANT, self.contact, actor="person")
        self.machine.open_sequence(TENANT, self.contact, "seq-again",
                                   request_id="req-3")
        before = len(self.sends)
        out = self.machine.send_reminder(TENANT, self.contact, SEQ,
                                         self.sender(), channel="sms",
                                         now=1020.0)
        self.assertFalse(out.sent)
        self.assertEqual(out.status, "suppressed")
        self.assertEqual(len(self.sends), before)
        self.assertEqual(self.snap()["state"], rsm.STATE_STOPPED_COMPLETE)

    def test_reply_changes_eligibility_not_t0_or_budget(self):
        self.ready()
        send = self.sender()
        self.machine.send_reminder(TENANT, self.contact, SEQ, send,
                                   channel="facebook", now=1020.0)
        before = self.snap()
        self.machine.record_reply(TENANT, self.contact, SEQ, reply_id="rep-1",
                                  now=1030.0)
        after = self.snap()
        self.assertEqual(after["t0"], before["t0"])
        self.assertEqual(after["reminders_used"], before["reminders_used"])
        self.assertFalse(after["reply_eligible"])
        self.assertEqual(
            self.machine.due_slot(TENANT, self.contact, SEQ, now=2000.0).kind,
            rsm.DECISION_NONE)
        # Eligibility can return; t0 and the used count still do not move.
        self.machine.mark_eligible(TENANT, self.contact, SEQ, now=2010.0)
        again = self.snap()
        self.assertEqual(again["t0"], before["t0"])
        self.assertEqual(again["reminders_used"], before["reminders_used"])

    def test_no_catch_up_burst_after_a_pause(self):
        self.ready()
        self.machine.pause(TENANT, self.contact, SEQ, now=1015.0)
        decision = self.machine.due_slot(TENANT, self.contact, SEQ, now=1200.0)
        self.assertEqual(decision.kind, rsm.DECISION_NONE)
        self.machine.resume(TENANT, self.contact, SEQ, now=1201.0)
        decision = self.machine.due_slot(TENANT, self.contact, SEQ, now=1201.0)
        self.assertTrue(decision.due)
        self.assertEqual(decision.slot_index, 0)
        snap = self.snap()
        statuses = [s["status"] for s in snap["slots"]]
        # The later overdue slots are recorded skipped, not queued in a burst.
        self.assertEqual(statuses, ["pending", "skipped", "skipped"])
        self.assertTrue(all(s["reason"] == rsm.REASON_NO_CATCH_UP
                            for s in snap["slots"][1:]))
        # Skipping consumes the fixed slot; no replacement slot appears.
        self.assertEqual(snap["reminders_total"], 3)


class T04PauseWindowStopRace(_Base):
    """Acceptance clause 4: pause / quiet window / STOP race."""

    def test_pause_blocks_before_and_after_due(self):
        self.ready()
        self.machine.pause(TENANT, self.contact, SEQ, now=1015.0)
        out = self.machine.send_reminder(TENANT, self.contact, SEQ,
                                         self.sender(), channel="sms",
                                         now=1020.0)
        self.assertFalse(out.sent)
        self.assertEqual(out.reason, rsm.STATE_PAUSED)
        self.assertEqual(self.sends, [])
        self.machine.resume(TENANT, self.contact, SEQ, now=1021.0)
        out = self.machine.send_reminder(TENANT, self.contact, SEQ,
                                         self.sender(), channel="sms",
                                         now=1021.0)
        self.assertTrue(out.sent)

    def test_quiet_window_defers_without_skipping(self):
        self.ready()
        send = self.sender()
        self.assertTrue(self.machine.send_reminder(
            TENANT, self.contact, SEQ, send, channel="facebook",
            now=1020.0).sent)
        decision = self.machine.due_slot(TENANT, self.contact, SEQ, now=1040.0)
        self.assertEqual(decision.kind, rsm.DECISION_WAIT)
        self.assertEqual(decision.wait_until, 1080.0)
        out = self.machine.send_reminder(TENANT, self.contact, SEQ, send,
                                         channel="instagram", now=1040.0)
        self.assertFalse(out.sent)
        self.assertEqual(out.status, "wait")
        self.assertEqual(len(self.sends), 1)
        snap = self.snap()
        self.assertEqual(snap["slots"][1]["status"], "pending")
        # At the end of the window the same slot is due.
        self.assertTrue(self.machine.send_reminder(
            TENANT, self.contact, SEQ, send, channel="instagram",
            now=1081.0).sent)

    def test_stop_recorded_between_queue_and_dispatch_wins(self):
        """The fresh gate, not queue-time consent, decides the race."""
        self.ready()
        consent_other = cg.ConsentStore(TenantIdentity(self.db))

        def stop_after_queue(_action_id):
            consent_other.global_stop(TENANT, self.contact,
                                      actor="person", reason="STOP")

        out = self.machine.send_reminder(
            TENANT, self.contact, SEQ, self.sender(), channel="sms",
            now=1020.0, before_dispatch=stop_after_queue)
        self.assertFalse(out.sent)
        self.assertEqual(out.status, "suppressed")
        self.assertEqual(self.sends, [])
        self.assertEqual(self.snap()["state"], rsm.STATE_STOPPED_COMPLETE)
        self.assertEqual(self.snap()["slots"][0]["status"], "suppressed")

    def test_human_takeover_wins_the_same_race(self):
        self.ready()
        consent_other = cg.ConsentStore(TenantIdentity(self.db))

        def fence(_action_id):
            consent_other.human_takeover(TENANT, self.contact,
                                         actor="trevor", reason="taking over")

        out = self.machine.send_reminder(
            TENANT, self.contact, SEQ, self.sender(), channel="sms",
            now=1020.0, before_dispatch=fence)
        self.assertFalse(out.sent)
        self.assertEqual(self.sends, [])

    def test_narrow_refusal_does_not_become_broader_permission(self):
        other = self.fresh()
        self.ready(seq="seq-topic", contact=other)
        self.machine.consent.refuse(TENANT, other, scope_kind=cg.SCOPE_TOPIC,
                                    scope_value="email_ask", actor="person")
        # The refused topic is blocked...
        blocked = self.machine.send_reminder(
            TENANT, other, "seq-topic", self.sender(), channel="sms",
            topic="email_ask", now=1020.0)
        self.assertFalse(blocked.sent)
        self.assertEqual(blocked.status, "suppressed")
        # ...and because it is a refusal, the sequence stops; it does not
        # silently continue on another topic.
        self.assertEqual(self.snap("seq-topic", other)["state"],
                         rsm.STATE_STOPPED_COMPLETE)
class T05ReservedFinalAction(_Base):
    """Acceptance clause 5 + C-F05 / C-F19: one reserved final action."""

    def test_reserve_enters_closing_final_and_cancels_siblings(self):
        self.ready()
        self.assertTrue(self.machine.send_reminder(
            TENANT, self.contact, SEQ, self.sender(), channel="facebook",
            now=1020.0).sent)
        before = self.snap()
        final = self.machine.reserve_final(
            TENANT, self.contact, SEQ, channel="sms",
            content_sha256="sha-final", now=1300.0)
        snap = self.snap()
        self.assertTrue(final.created)
        self.assertEqual(snap["state"], rsm.STATE_CLOSING_FINAL)
        self.assertEqual(snap["final_action_id"], final.action_id)
        self.assertEqual(snap["version"], before["version"] + 1)  # one state bump
        self.assertEqual(snap["slots"][0]["status"], "sent")
        for slot in snap["slots"][1:]:
            self.assertEqual(slot["status"], "canceled")
            self.assertEqual(slot["reason"], rsm.REASON_FINAL_RESERVED)
        events = [e["event"] for e in
                  self.machine.events(TENANT, self.contact, SEQ)]
        self.assertIn("final_siblings_canceled", events)

    def test_only_the_reserved_action_may_pass(self):
        self.ready()
        final = self.machine.reserve_final(
            TENANT, self.contact, SEQ, channel="sms",
            content_sha256="sha-final", now=1300.0)
        for other in ("act_invented", "fin_other"):
            with self.assertRaises(rsm.FinalNotReserved):
                self.machine.dispatch_final(
                    TENANT, self.contact, SEQ, other, self.sender(),
                    channel="sms", now=1301.0)
        self.assertEqual(self.sends, [])
        self.assertEqual(self.store.get_action(final.action_id)["state"],
                         "queued")

    def test_never_reserves_a_second_final(self):
        self.ready()
        first = self.machine.reserve_final(
            TENANT, self.contact, SEQ, channel="sms",
            content_sha256="sha-final", now=1300.0)
        second = self.machine.reserve_final(
            TENANT, self.contact, SEQ, channel="sms",
            content_sha256="sha-final", now=1301.0)
        self.assertEqual(second.action_id, first.action_id)
        self.assertFalse(second.created)
        self.assertEqual(second.reserved_at, first.reserved_at)
        action = self.store.action_by_intent("final:%s" % SEQ)
        self.assertEqual(action["action_id"], first.action_id)
        self.assertEqual(action["tries"], 0)

    def test_stop_refuses_the_reservation_itself(self):
        self.ready()
        self.machine.consent.global_stop(TENANT, self.contact, actor="person")
        with self.assertRaises(rsm.FinalRefused) as caught:
            self.machine.reserve_final(TENANT, self.contact, SEQ,
                                       channel="sms",
                                       content_sha256="sha-final", now=1300.0)
        self.assertEqual(caught.exception.reason, cg.REASON_GLOBAL)
        snap = self.snap()
        self.assertEqual(snap["state"], rsm.STATE_STOPPED_COMPLETE)
        self.assertIsNone(snap["final_action_id"])
        self.assertIsNone(snap["final_reservation"])
        self.assertIsNone(self.store.action_by_intent("final:%s" % SEQ))

    def test_reminders_cannot_send_while_closing_final(self):
        self.ready()
        self.machine.reserve_final(TENANT, self.contact, SEQ, channel="sms",
                                   content_sha256="sha-final", now=1300.0)
        decision = self.machine.due_slot(TENANT, self.contact, SEQ, now=9999.0)
        self.assertEqual(decision.kind, rsm.DECISION_NONE)
        self.assertEqual(decision.reason, "closing_final")
        out = self.machine.send_reminder(TENANT, self.contact, SEQ,
                                         self.sender(), channel="sms",
                                         now=9999.0)
        self.assertFalse(out.sent)
        self.assertEqual(self.sends, [])

    def test_stop_between_reservation_and_dispatch_cancels_the_final(self):
        self.ready()
        final = self.machine.reserve_final(
            TENANT, self.contact, SEQ, channel="sms",
            content_sha256="sha-final", now=1300.0)
        consent_other = cg.ConsentStore(TenantIdentity(self.db))

        def stop_now(_action_id):
            consent_other.global_stop(TENANT, self.contact, actor="person")

        out = self.machine.dispatch_final(
            TENANT, self.contact, SEQ, final.action_id, self.sender(),
            channel="sms", now=1301.0, before_dispatch=stop_now)
        self.assertFalse(out.sent)
        self.assertEqual(out.status, "canceled")
        self.assertEqual(out.state, rsm.STATE_STOPPED_COMPLETE)
        self.assertEqual(self.sends, [])
        self.assertEqual(self.store.get_action(final.action_id)["state"],
                         "suppressed")
        self.assertEqual(self.snap()["state"], rsm.STATE_STOPPED_COMPLETE)

    def test_crash_trace_unknown_then_reconcile_never_reserves_another(self):
        self.ready()
        result = self.run_worker({"mode": "crash-final"})
        self.assertEqual(result["status"], "unknown")
        self.assertTrue(result["created"])
        aid = result["action_id"]

        snap = self.snap()
        self.assertEqual(snap["state"], rsm.STATE_CLOSING_FINAL)
        self.assertEqual(snap["final_action_id"], aid)
        self.assertEqual(self.store.get_action(aid)["state"], "unknown")

        # A restart reloads the reservation; it never mints a second final.
        identity = TenantIdentity(self.db)
        store = DurableStore(self.outbox)
        restarted = rsm.ReminderStateMachine(identity, store)
        again = restarted.reserve_final(TENANT, self.contact, SEQ,
                                        channel="sms",
                                        content_sha256="sha-final", now=1400.0)
        self.assertEqual(again.action_id, aid)
        self.assertFalse(again.created)

        out = restarted.reconcile_final(
            TENANT, self.contact, SEQ, applied=True,
            receipt={"provider": "sms", "message_id": "AAA"}, now=1401.0)
        self.assertEqual(out.status, "sent")
        after = restarted.snapshot(TENANT, self.contact, SEQ)
        self.assertEqual(after["state"], rsm.STATE_STOPPED_FINAL)
        self.assertEqual(after["slots"][1]["status"], "canceled")
        self.assertEqual(after["slots"][2]["status"], "canceled")
        store.close()

    def test_permanent_nonexecution_closes_without_claiming_sent(self):
        self.ready()
        final = self.machine.reserve_final(
            TENANT, self.contact, SEQ, channel="sms",
            content_sha256="sha-final", now=1300.0)
        out = self.machine.reconcile_final(
            TENANT, self.contact, SEQ, applied=False, now=1400.0)
        self.assertEqual(out.state, rsm.STATE_STOPPED_INELIGIBLE)
        self.assertFalse(out.sent)
        action = self.store.get_action(final.action_id)
        self.assertEqual(action["state"], "canceled")
        self.assertEqual(self.store.receipts(final.action_id), {})
        self.assertNotEqual(self.snap()["state"], rsm.STATE_STOPPED_FINAL)

    def test_expired_final_slot_closes_without_claiming_sent(self):
        self.ready()
        final = self.machine.reserve_final(
            TENANT, self.contact, SEQ, channel="sms",
            content_sha256="sha-final", now=1300.0)
        early = self.machine.expire_final(TENANT, self.contact, SEQ, now=1400.0)
        self.assertEqual(early.reason, "slot_not_expired")
        out = self.machine.expire_final(TENANT, self.contact, SEQ, now=2000.0)
        self.assertEqual(out.state, rsm.STATE_STOPPED_INELIGIBLE)
        self.assertFalse(out.sent)
        self.assertEqual(self.store.get_action(final.action_id)["state"],
                         "canceled")
        self.assertEqual(self.store.receipts(final.action_id), {})

    def test_unknown_stays_reserved_and_cannot_create_another(self):
        self.ready()
        final = self.machine.reserve_final(
            TENANT, self.contact, SEQ, channel="sms",
            content_sha256="sha-final", now=1300.0)
        out = self.machine.dispatch_final(
            TENANT, self.contact, SEQ, final.action_id,
            self.exploding_sender(), channel="sms", now=1301.0)
        self.assertEqual(out.status, "unknown")
        snap = self.snap()
        self.assertEqual(snap["state"], rsm.STATE_CLOSING_FINAL)
        again = self.machine.reserve_final(
            TENANT, self.contact, SEQ, channel="sms",
            content_sha256="sha-final", now=1302.0)
        self.assertEqual(again.action_id, final.action_id)
        self.assertFalse(again.created)
        held = self.machine.reconcile_final(TENANT, self.contact, SEQ,
                                            applied=None, now=1303.0)
        self.assertEqual(held.state, rsm.STATE_CLOSING_FINAL)


class T06ActualTerminalStop(_Base):
    """Acceptance clause 6: the sequence actually ends."""

    def _stop_by_acceptance(self):
        self.ready()
        final = self.machine.reserve_final(
            TENANT, self.contact, SEQ, channel="sms",
            content_sha256="sha-final", now=1300.0)
        out = self.machine.dispatch_final(
            TENANT, self.contact, SEQ, final.action_id, self.sender(),
            channel="sms", now=1301.0)
        self.assertTrue(out.sent)
        return final

    def test_terminal_state_refuses_every_further_effect(self):
        final = self._stop_by_acceptance()
        snap = self.snap()
        self.assertTrue(snap["terminal"])
        self.assertEqual(snap["state"], rsm.STATE_STOPPED_FINAL)
        decision = self.machine.due_slot(TENANT, self.contact, SEQ, now=9999.0)
        self.assertEqual(decision.reason, "sequence_terminal")
        out = self.machine.send_reminder(TENANT, self.contact, SEQ,
                                         self.sender(), channel="sms",
                                         now=9999.0)
        self.assertFalse(out.sent)
        self.assertEqual(len(self.sends), 1)
        with self.assertRaises(rsm.SequenceTerminal):
            self.machine.reserve_final(TENANT, self.contact, SEQ,
                                       channel="sms",
                                       content_sha256="sha-2", now=9999.0)
        with self.assertRaises(rsm.SequenceTerminal):
            self.machine.record_initial_invitation(
                TENANT, self.contact, SEQ, invitation_id="inv-late",
                now=9999.0)
        # A late request never restarts the stopped sequence: the same id
        # returns the terminal row, and a new episode is a separate sequence
        # that leaves the stopped one's counters untouched.
        same = self.machine.open_sequence(TENANT, self.contact, SEQ,
                                          request_id="req-late", now=9999.0)
        self.assertEqual(same["collection_sequence_id"], SEQ)
        self.assertEqual(same["state"], rsm.STATE_STOPPED_FINAL)
        self.assertEqual(same["reminders_used"], snap["reminders_used"])
        late = self.machine.open_sequence(TENANT, self.contact, "seq-late",
                                          request_id="req-late", now=9999.0)
        self.assertEqual(late["collection_sequence_id"], "seq-late")
        stopped = self.snap()
        self.assertEqual(stopped["state"], rsm.STATE_STOPPED_FINAL)
        self.assertEqual(stopped["reminders_used"], snap["reminders_used"])
        self.assertEqual(stopped["version"], snap["version"])

    def test_second_dispatch_of_the_same_final_is_not_a_second_send(self):
        final = self._stop_by_acceptance()
        before = len(self.sends)
        with self.assertRaises(rsm.SequenceTerminal):
            self.machine.dispatch_final(
                TENANT, self.contact, SEQ, final.action_id, self.sender(),
                channel="sms", now=1400.0)
        self.assertEqual(len(self.sends), before)


class T07UpstreamReuse(unittest.TestCase):
    """T-17 must reuse the accepted guards, never a second copy."""

    def test_dispatch_and_gate_are_the_upstream_objects(self):
        self.assertIs(rsm.dispatch, og.dispatch)
        self.assertIs(rsm.make_gate_evaluator, cg.make_gate_evaluator)
        self.assertIs(rsm.ConsentStore, cg.ConsentStore)
        self.assertIs(rsm.DurableStore, DurableStore)
        # No second STOP vocabulary: the reason comes from consent_gate.
        self.assertFalse(hasattr(rsm, "SCOPE_GLOBAL"))
        self.assertTrue(hasattr(cg, "SCOPE_GLOBAL"))
        self.assertFalse(hasattr(rsm, "RECONCILE_OUTCOMES"))


def _worker(cfg_path):
    cfg = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
    sys.path.insert(0, str(PKG))
    sys.path.insert(0, str(UPSTREAM))
    import reminder_state_machine as worker_rsm
    from durable_store import DurableStore as WorkerStore
    from tenant_identity import TenantIdentity as WorkerIdentity

    machine = worker_rsm.ReminderStateMachine(
        WorkerIdentity(cfg["db"]), WorkerStore(cfg["store"]))
    final = machine.reserve_final(
        cfg["tenant"], cfg["contact"], cfg["seq"], channel="sms",
        content_sha256="sha-final", now=1300.0)

    def explode(ctx):
        raise RuntimeError("process died inside the provider call")

    out = machine.dispatch_final(
        cfg["tenant"], cfg["contact"], cfg["seq"], final.action_id, explode,
        channel="sms", now=1301.0)
    Path(cfg["out"]).write_text(json.dumps({
        "status": out.status,
        "action_id": out.action_id,
        "state": out.state,
        "created": final.created,
    }) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        sys.exit(_worker(sys.argv[2]))
    unittest.main(verbosity=2)


