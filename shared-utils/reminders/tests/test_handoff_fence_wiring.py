#!/usr/bin/env python3
"""Reachability pin: the T-29 human handoff must gate the reminder send itself.

C-29 requires the bot to be PAUSED while a human handoff is open and to resume
ONLY through an explicit release by the accepted owner. `handoff.HandoffStore`
implements that lifecycle and, on create(), also sets the T-18 consent fence.
The consent fence alone is therefore enough while it is set -- which is why the
fence LOOKS enforced on a tree without the wiring. It is not the same claim.

This file pins the WIRING: the send path must read the handoff rows, not only
the consent fence flag. The distinguishing case is
test_open_handoff_suppresses_when_only_the_handoff_rows_remain -- a handoff
still open after the consent fence flag was cleared out of band (a grant, a
release by another path). There the handoff rows are the only remaining
evidence.

RED without the wiring
    send_reminder dispatches with make_gate_evaluator(self.consent) only, so
    that test sends: the provider IS called while a handoff is open.
GREEN with the wiring
    the send is SUPPRESSED at the gate and the provider is never called.

Run from the repo root:
    python3 -m unittest discover -s shared-utils/reminders/tests \
        -t shared-utils/reminders/tests -p 'test_handoff_fence_wiring.py' -v
"""
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
REPO = PKG.parents[1]
for path in (str(PKG), str(REPO / "38-conversational-ai-system" / "tools"),
             str(REPO / "shared-utils" / "handoff")):
    if path not in sys.path:
        sys.path.insert(0, path)

from test_reminder_state_machine import SEQ, TENANT, _Base  # noqa: E402

from handoff import HandoffStore  # noqa: E402

OWNER = "owner-primary"
BACKUP = "owner-backup"


class HandoffFenceGatesTheSend(_Base):
    """The send path must read the handoff rows, not only the consent fence."""

    def open_handoff(self, now=1010.0):
        # Opened through the lifecycle store directly, so this runs unchanged
        # against a tree where the wiring is absent.
        self.handoffs = HandoffStore(self.identity.db_path)
        return self.handoffs.create(
            TENANT, self.contact,
            context_ref="conversation:conv-1:message-2",
            context_summary="Person wants a human decision on the price",
            owner_id=OWNER,
            backup_owner_id=BACKUP,
            due_action="Call back with the price and the booking link",
            due_at=now + 3600.0,
            created_by="agent:concierge",
            reason="pricing decision needs a human",
            now=now)

    def clear_consent_fence(self, now=1013.0):
        """Release the T-18 consent fence and leave the handoff row open."""
        self.machine.consent.human_release(
            TENANT, self.contact, actor=OWNER,
            reason="cleared out of band by another path", now=now)

    def send(self, now=1020.0):
        return self.machine.send_reminder(
            TENANT, self.contact, SEQ, self.sender(), channel="sms", now=now)

    # ── the pin ───────────────────────────────────────────────────────────

    def test_open_handoff_suppresses_when_only_the_handoff_rows_remain(self):
        """RED without the wiring: the case the bare consent fence misses."""
        self.ready()
        self.open_handoff()
        self.clear_consent_fence()
        result = self.send()
        self.assertFalse(
            result.sent,
            "a send must not go out while a handoff is open, even after the "
            "consent fence flag was cleared; status=%s" % result.status)
        self.assertEqual(result.status, "suppressed")
        self.assertEqual(self.sends, [], "the provider must never be called")
        self.assertEqual(self.snap()["reminders_used"], 0)

    # ── supporting controls ───────────────────────────────────────────────

    def test_open_handoff_suppresses_with_the_consent_fence_set(self):
        self.ready()
        self.open_handoff()
        result = self.send()
        self.assertFalse(result.sent)
        self.assertEqual(self.sends, [])

    def test_acceptance_alone_does_not_release_the_bot(self):
        self.ready()
        handoff = self.open_handoff()
        self.handoffs.accept(handoff["handoff_id"], actor=OWNER, now=1011.0)
        result = self.send()
        self.assertFalse(result.sent, "acceptance is not release")
        self.assertEqual(self.sends, [])

    def test_release_by_the_accepted_owner_resumes_the_send(self):
        self.ready()
        handoff = self.open_handoff()
        hid = handoff["handoff_id"]
        self.handoffs.accept(hid, actor=OWNER, now=1011.0)
        self.handoffs.release(hid, actor=OWNER,
                              reason="owner handled the person", now=1012.0)
        result = self.send()
        self.assertTrue(result.sent, "an explicit release must resume the send")
        self.assertEqual(len(self.sends), 1)

    def test_no_handoff_still_sends(self):
        """Polarity control: the fence suppresses the handoff case only."""
        self.ready()
        result = self.send()
        self.assertTrue(result.sent)
        self.assertEqual(len(self.sends), 1)

    def test_composed_evaluator_keeps_the_point_of_use_recheck(self):
        """outbound_gate only re-runs the gate when consent_guard is set.

        A wrapper that drops the flag silently disables the re-check that
        closes the window between the first verdict and the INSERT.
        """
        self.assertTrue(
            getattr(self.machine._gate_evaluator(), "consent_guard", False),
            "the composed evaluator must keep consent_guard so dispatch "
            "re-runs it at the point of use")


if __name__ == "__main__":
    unittest.main(verbosity=2)
