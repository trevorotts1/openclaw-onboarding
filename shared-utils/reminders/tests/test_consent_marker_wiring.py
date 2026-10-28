#!/usr/bin/env python3
"""T-29 repair (PBB-1280): the consent marker must reach outbound_gate.dispatch.

The T-29 handoff fence wraps the consent evaluator in _gate_evaluator(). A plain
closure around make_gate_evaluator loses the consent_guard marker, and
outbound_gate.dispatch only runs its point-of-use re-check when that marker is
present - so a STOP recorded after the fresh verdict still let a send go out.

Three assertions, one per claim:
  1. the wrapper carries the marker;
  2. with the marker, a STOP landing after the verdict refuses the send;
  3. with the marker and no STOP, the send still happens (the fence can pass).

Run: python3 -I shared-utils/reminders/tests/test_consent_marker_wiring.py
"""
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
REPO = PKG.parents[1]
for path in (str(PKG), str(REPO / "38-conversational-ai-system" / "tools")):
    if path not in sys.path:
        sys.path.insert(0, path)

import outbound_gate as og  # noqa: E402
import reminder_state_machine as rsm  # noqa: E402
from durable_store import DurableStore  # noqa: E402
from tenant_identity import TenantIdentity  # noqa: E402

TENANT = "tenant-marker"
SEQ = "seq-marker"
POLICY = rsm.ReminderPolicy(
    version="pb/reminders/v1",
    slot_offsets_seconds=(10.0, 25.0, 150.0),
    quiet_interval_seconds=60.0,
    final_slot_seconds=600.0,
)


class ConsentMarkerWiring(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="t29-marker-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.identity = TenantIdentity(str(self.tmp / "identity.sqlite"))
        self.identity.register_tenant(TENANT, "marker")
        self.contact = self.identity.bind(
            TENANT, [("sms_number", "+15550188", True)], source="t29")
        self.store = DurableStore(str(self.tmp / "outbox.sqlite"))
        self.machine = rsm.ReminderStateMachine(self.identity, self.store)
        self.machine.open_sequence(TENANT, self.contact, SEQ,
                                   request_id="req-marker", now=1000.0)
        self.machine.adopt_policy(TENANT, self.contact, SEQ, POLICY, now=1002.0)
        self.machine.record_initial_invitation(
            TENANT, self.contact, SEQ, invitation_id="inv-marker", now=1010.0)
        self.calls = 0
        self.guarded = 0
        self.sends = []

    def tearDown(self):
        try:
            self.store.close()
        except Exception:
            pass

    def send(self, stop_after_first_verdict):
        """Run one real dispatch; optionally land a STOP mid-gate."""
        real_evaluate = og.evaluate_gate
        real_guarded = self.store.begin_attempt_guarded
        machine, contact = self.machine, self.contact

        def evaluate(evaluator, context, **kw):
            self.calls += 1
            verdict = real_evaluate(evaluator, context, **kw)
            if stop_after_first_verdict and self.calls == 1:
                machine.consent.global_stop(TENANT, contact,
                                            reason="late_stop", actor="test")
            return verdict

        def guarded(action_id, fence, worker_id, *, pre_send=None, epoch=None,
                    now=None):
            self.guarded += 1 if pre_send is not None else 0
            return real_guarded(action_id, fence, worker_id, pre_send=pre_send,
                                epoch=epoch, now=now)

        og.evaluate_gate = evaluate
        self.store.begin_attempt_guarded = guarded
        try:
            return self.machine.send_reminder(
                TENANT, contact, SEQ,
                lambda ctx: self.sends.append(ctx["action_id"]) or
                {"provider": "sms", "message_id": ctx["action_id"]},
                channel="sms", worker_id="marker-test", now=1020.0)
        finally:
            og.evaluate_gate = real_evaluate
            self.store.begin_attempt_guarded = real_guarded

    def test_wrapper_keeps_the_consent_marker(self):
        evaluator = self.machine._gate_evaluator()
        self.assertTrue(getattr(evaluator, "consent_guard", False),
                        "_gate_evaluator dropped make_gate_evaluator's marker")

    def test_marker_refuses_a_send_once_the_stop_lands(self):
        result = self.send(stop_after_first_verdict=True)
        self.assertEqual(self.guarded, 1,
                         "the attempt was not committed through the guard")
        self.assertEqual(self.calls, 2,
                         "dispatch did not re-run the evaluator at point of use")
        self.assertEqual(result.status, "suppressed")
        self.assertEqual(self.sends, [], "a message went out after the STOP")
        self.assertIn("point-of-use guard refused", result.reason)

    def test_marker_lets_a_clean_send_through(self):
        result = self.send(stop_after_first_verdict=False)
        self.assertEqual(self.guarded, 1)
        self.assertEqual(self.calls, 2)
        self.assertEqual(result.status, "sent")
        self.assertEqual(len(self.sends), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
