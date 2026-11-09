#!/usr/bin/env python3
"""T-29 fence at the reminder send gate (PBB-664).

Pins the wire that gives `shared-utils/handoff/handoff.py` its production call
site: `ReminderStateMachine._gate_evaluator()` must suppress a send while a
human handoff is open, and must do so through `HandoffStore.gate_decision()`
-- not only through the consent fence that `create()` happens to pause.

Run from the repo root:
    python3 -I shared-utils/reminders/tests/test_handoff_fence.py
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
REPO = PKG.parents[1]
for path in (str(PKG), str(REPO / "38-conversational-ai-system" / "tools"),
             str(REPO / "shared-utils" / "handoff")):
    if path not in sys.path:
        sys.path.insert(0, path)

import reminder_state_machine as rsm  # noqa: E402
from durable_store import DurableStore  # noqa: E402
from tenant_identity import TenantIdentity  # noqa: E402

TENANT = "tenant-pb"


class TestHandoffFence(unittest.TestCase):
    """The dispatch gate must consult the handoff store on every send."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t29-fence-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.identity = TenantIdentity(str(self.tmp / "identity.sqlite"))
        self.identity.register_tenant(TENANT, "purple billboard")
        self.contact = self.identity.bind(
            TENANT, [("sms_number", "+15550177", True)], source="t29")
        self.store = DurableStore(str(self.tmp / "outbox.sqlite"))
        self.addCleanup(self.store.close)
        self.machine = rsm.ReminderStateMachine(self.identity, self.store)
        self.evaluator = self.machine._gate_evaluator()

    def _ctx(self):
        return {"action": {"tenant_id": TENANT,
                           "canonical_contact_id": self.contact,
                           "action_id": "a1", "scope": "reminder"},
                "now": 10.0}

    def _open_handoff(self):
        return self.machine.handoffs.create(
            TENANT, self.contact,
            context_ref="ctx-1", context_summary="owner asked to take over",
            owner_id="owner-1", backup_owner_id="owner-2",
            due_action="call the client back", due_at=2000000000.0,
            created_by="t29", reason="owner took over", now=1000.0,
            create_key="t29-k1")

    def test_no_handoff_allows_the_send(self):
        """The control: with no handoff row the consent gate's ALLOW stands."""
        self.assertEqual(self.machine.handoffs.open_for_contact(
            TENANT, self.contact), [])
        self.assertEqual(self.evaluator(self._ctx())["verdict"], "ALLOW")

    def test_opening_a_handoff_pauses_the_consent_fence(self):
        """The handoff's own create() pauses the consent fence."""
        self._open_handoff()
        self.assertTrue(self.machine.handoffs.fence.is_paused(TENANT, self.contact))
        out = self.evaluator(self._ctx())
        self.assertEqual(out["verdict"], "SUPPRESSED")
        self.assertEqual(out["evidence"]["reason"], "consent:human_owned")

    def test_open_handoff_suppresses_with_the_consent_fence_released(self):
        """DECISIVE: only gate_decision() can suppress once the fence is clear.

        The consent fence is released directly, so the consent evaluator
        ALLOWs and the dispatch gate is reached. The open handoff row is then
        the only thing that can refuse the send.
        """
        handoff = self._open_handoff()
        self.machine.handoffs.fence.release(
            TENANT, self.contact, actor="t29",
            reason="release the consent fence only", now=1001.0)
        self.assertFalse(self.machine.handoffs.fence.is_paused(TENANT, self.contact))
        self.assertEqual(len(self.machine.handoffs.open_for_contact(
            TENANT, self.contact)), 1)

        out = self.evaluator(self._ctx())
        self.assertEqual(out["verdict"], "SUPPRESSED",
                         "an open handoff must refuse the send")
        self.assertEqual(out["evidence"]["source"], "handoff")
        self.assertEqual(out["evidence"]["reason"], "handoff:human_owned")
        self.assertEqual(out["evidence"]["handoff_id"], handoff["handoff_id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
