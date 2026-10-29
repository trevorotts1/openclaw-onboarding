#!/usr/bin/env python3
"""T-29: an open human handoff suppresses a reminder and a reserved final.

The reminder machine must run TWO gates, not one: the T-18 consent fence and
the T-29 handoff lifecycle. Both must ALLOW.

Every case below is built so it CANNOT pass on the consent fence alone: the
handoff is opened (which pauses the consent fence) and the fence is then
released explicitly while the handoff row stays open. A machine that wires only
the consent evaluator sends here; the wired machine suppresses with
reason "handoff:human_owned".

Run from the repo root:
    python3 -m unittest discover -s shared-utils/reminders/tests \
        -t shared-utils/reminders/tests -p 'test_*.py' -v
or directly:
    python3 shared-utils/reminders/tests/test_reminder_handoff_fence.py

Free: no network, no model, no paid call.
"""

import shutil
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

import reminder_state_machine as rsm  # noqa: E402
from durable_store import DurableStore  # noqa: E402
from tenant_identity import TenantIdentity  # noqa: E402

TENANT = "tenant-pb"
SEQ = "seq-main"
POLICY = rsm.ReminderPolicy(
    version="pb/reminders/v1",
    slot_offsets_seconds=(10.0, 25.0, 150.0),
    quiet_interval_seconds=60.0,
    final_slot_seconds=600.0,
)


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t29-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.db = str(self.tmp / "identity.sqlite")
        self.outbox = str(self.tmp / "outbox.sqlite")
        self.identity = TenantIdentity(self.db)
        self.identity.register_tenant(TENANT, "purple billboard")
        self.contact = self.identity.bind(
            TENANT, [("sms_number", "+15550177", True)], source="t29")
        self.store = DurableStore(self.outbox)
        self.machine = rsm.ReminderStateMachine(self.identity, self.store)
        self.sends = []

    def tearDown(self):
        try:
            self.store.close()
        except Exception:
            pass

    def ready(self, now=1010.0):
        self.machine.open_sequence(TENANT, self.contact, SEQ,
                                   request_id="req-1", now=now - 10)
        self.machine.adopt_policy(TENANT, self.contact, SEQ, POLICY,
                                  now=now - 8)
        self.machine.record_initial_invitation(
            TENANT, self.contact, SEQ, invitation_id="inv-1", now=now)

    def sender(self):
        def send(ctx):
            self.sends.append(ctx["action_id"])
            return {"provider": "sms", "message_id": ctx["action_id"]}
        return send

    def open_handoff_then_release_fence(self, now=1015.0):
        """An open handoff with NO active consent fence.

        This is the state the consent gate cannot see: the handoff row is
        offered/active, the T-18 fence is released. Only the handoff gate can
        suppress a send from here.
        """
        self.machine.handoffs.create(
            TENANT, self.contact,
            context_ref="ctx-1", context_summary="client asked for a person",
            owner_id="human:trevor", backup_owner_id="human:jill",
            due_action="reply", due_at=now + 3600.0,
            created_by="system:handoff", now=now)
        self.machine.consent.human_release(
            TENANT, self.contact, actor="human:trevor",
            reason="handoff open", now=now + 1)
        self.assertFalse(self.machine.consent.human_fence(
            TENANT, self.contact)["active"],
            "precondition: the consent fence must be released for this test"
            " to discriminate the handoff gate")


class HandoffSuppressesReminder(_Base):
    def test_open_handoff_suppresses_a_due_reminder(self):
        self.ready()
        self.open_handoff_then_release_fence()
        result = self.machine.send_reminder(
            TENANT, self.contact, SEQ, self.sender(), channel="sms", now=1025.0)
        self.assertFalse(result.sent, "an open handoff must suppress the send")
        self.assertEqual(result.status, "suppressed")
        self.assertEqual(self.sends, [], "no provider call may happen")
        slots = self.machine.snapshot(TENANT, self.contact, SEQ)["slots"]
        self.assertEqual(slots[0]["status"], rsm.SLOT_SUPPRESSED)

    def test_released_handoff_allows_the_reminder(self):
        """Inverse leg: the same sequence with no handoff still sends."""
        self.ready()
        result = self.machine.send_reminder(
            TENANT, self.contact, SEQ, self.sender(), channel="sms", now=1025.0)
        self.assertTrue(result.sent, "no handoff: nothing may be suppressed")
        self.assertEqual(len(self.sends), 1)

    def test_gate_evaluator_names_the_handoff_as_the_source(self):
        """The suppression must be attributable to the handoff, not consent."""
        self.ready()
        self.open_handoff_then_release_fence()
        evaluator = self.machine._gate_evaluator()
        self.assertTrue(getattr(evaluator, "consent_guard", False),
                        "the wrapper must keep the point-of-use recheck marker")
        verdict = evaluator({
            "action": {"tenant_id": TENANT,
                       "canonical_contact_id": self.contact},
            "now": 1020.0})
        self.assertEqual(verdict["verdict"], "SUPPRESSED")
        self.assertEqual(verdict["evidence"]["source"], "handoff")
        self.assertEqual(verdict["evidence"]["reason"], "handoff:human_owned")

    def test_handoff_opened_after_the_first_verdict_still_blocks(self):
        """Point of use, not queue time: the fence is re-read at the send."""
        self.ready()

        def open_late(action_id):
            self.machine.handoffs.create(
                TENANT, self.contact,
                context_ref="ctx-late", context_summary="human took over",
                owner_id="human:trevor", backup_owner_id="human:jill",
                due_action="reply", due_at=1030.0 + 3600.0,
                created_by="system:handoff", now=1030.0)
            self.machine.consent.human_release(
                TENANT, self.contact, actor="human:trevor",
                reason="handoff open", now=1030.5)

        result = self.machine.send_reminder(
            TENANT, self.contact, SEQ, self.sender(), channel="sms",
            now=1025.0, before_dispatch=open_late)
        self.assertFalse(result.sent,
                         "a handoff opened mid-dispatch must still block")
        self.assertEqual(self.sends, [])


class HandoffSuppressesFinal(_Base):
    def reserve(self, now=1100.0):
        return self.machine.reserve_final(
            TENANT, self.contact, SEQ, channel="sms",
            content_sha256="a" * 64, now=now)

    def test_open_handoff_suppresses_the_reserved_final(self):
        self.ready()
        final = self.reserve()
        self.open_handoff_then_release_fence(now=1101.0)
        outcome = self.machine.dispatch_final(
            TENANT, self.contact, SEQ, final.action_id, self.sender(),
            channel="sms", now=1602.0)
        self.assertFalse(outcome.sent, "an open handoff must block the final")
        self.assertEqual(self.sends, [], "the final must not reach the provider")

    def test_no_handoff_lets_the_final_dispatch(self):
        self.ready()
        final = self.reserve()
        outcome = self.machine.dispatch_final(
            TENANT, self.contact, SEQ, final.action_id, self.sender(),
            channel="sms", now=1602.0)
        self.assertFalse(outcome.status == "blocked",
                         "no handoff: nothing may block the final")
        self.assertEqual(len(self.sends), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
