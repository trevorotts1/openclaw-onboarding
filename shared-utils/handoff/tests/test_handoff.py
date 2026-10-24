#!/usr/bin/env python3
"""Proofs for the owned human handoff: R-19 / C-29.

Every clause in the acceptance is pinned, including the refusals:
  context, actual owner acceptance, due action, backup, escalation, and the
  bot paused/resumed only by an explicit release.

Run: python3 shared-utils/handoff/tests/test_handoff.py
No network, no provider, no model. The real T-12/T-18 modules on main are the
fence and identity under test, not a stub.
"""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE = HERE.parent
REPO = MODULE.parents[1]
TOOLS = REPO / "38-conversational-ai-system" / "tools"
sys.path.insert(0, str(MODULE))
sys.path.insert(0, str(TOOLS))

import handoff as h  # noqa: E402
from consent_gate import ConsentStore  # noqa: E402
from tenant_identity import VerificationError  # noqa: E402

OWNER = "owner-primary"
BACKUP = "owner-backup"


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self._tmp.name, "handoff.db")
        self.store = h.HandoffStore(self.db)
        self.store.identity.register_tenant("t1")
        self.store.identity.register_tenant("t2")
        self.contact = self.store.identity.bind(
            "t1", [("email", "person@example.com", True)])
        self.other_tenant_contact = self.store.identity.bind(
            "t2", [("email", "person@example.com", True)])
        self.t0 = time.time()

    def tearDown(self):
        self._tmp.cleanup()

    def open(self, **over):
        args = dict(
            context_ref="conversation:conv-42:message-7",
            context_summary="Person asked what the guide costs and wants a call",
            owner_id=OWNER,
            backup_owner_id=BACKUP,
            due_action="Call back with the price and the booking link",
            due_at=self.t0 + 3600.0,
            created_by="agent:concierge",
            reason="needs a human decision on pricing",
            now=self.t0,
        )
        args.update(over)
        return self.store.create("t1", self.contact, **args)

    def accepted(self, **over):
        handoff = self.open(**over)
        return self.store.accept(handoff["handoff_id"], actor=OWNER,
                                 now=self.t0 + 10.0)

    def consent(self):
        return ConsentStore(self.store.identity)


class ContextTests(Base):
    def test_create_requires_a_context_reference(self):
        for value in ("", "   ", None, 7):
            with self.subTest(value=value):
                with self.assertRaises(h.HandoffError) as caught:
                    self.open(context_ref=value)
                self.assertTrue(
                    str(caught.exception).startswith("bad_input:"),
                    caught.exception)

    def test_create_requires_a_context_summary(self):
        for value in ("", "  \t ", None):
            with self.subTest(value=value):
                with self.assertRaises(h.HandoffError) as caught:
                    self.open(context_summary=value)
                self.assertTrue(
                    str(caught.exception).startswith("bad_input:"),
                    caught.exception)

    def test_create_requires_a_due_action(self):
        for value in ("", "   ", None):
            with self.subTest(value=value):
                with self.assertRaises(h.HandoffError) as caught:
                    self.open(due_action=value)
                self.assertTrue(
                    str(caught.exception).startswith("bad_input:"),
                    caught.exception)

    def test_create_requires_a_future_due_time(self):
        for offset in (0.0, -1.0):
            with self.subTest(offset=offset):
                with self.assertRaises(h.HandoffError) as caught:
                    self.open(due_at=self.t0 + offset)
                self.assertTrue(
                    str(caught.exception).startswith("bad_input:"),
                    caught.exception)
        with self.assertRaises(h.HandoffError):
            self.open(due_at=float("inf"))

    def test_create_requires_a_distinct_backup_owner(self):
        with self.assertRaises(h.HandoffError) as caught:
            self.open(backup_owner_id=OWNER)
        self.assertTrue(str(caught.exception).startswith("bad_input:"))
        with self.assertRaises(h.HandoffError):
            self.open(backup_owner_id="  ")

    def test_context_and_due_are_returned_verbatim(self):
        due = self.t0 + 3600.0
        row = self.open(due_at=due)
        self.assertEqual(row["context"]["ref"],
                         "conversation:conv-42:message-7")
        self.assertEqual(
            row["context"]["summary"],
            "Person asked what the guide costs and wants a call")
        self.assertEqual(row["context"]["reason"],
                         "needs a human decision on pricing")
        self.assertEqual(row["owner_id"], OWNER)
        self.assertEqual(row["backup_owner_id"], BACKUP)
        self.assertEqual(row["due_action"],
                         "Call back with the price and the booking link")
        self.assertEqual(row["due_at"], due)


class IdentityTests(Base):
    def test_create_requires_a_verified_contact(self):
        with self.assertRaises(VerificationError):
            self.store.create(
                "t1", "cc_missing", context_ref="c", context_summary="s",
                owner_id=OWNER, backup_owner_id=BACKUP, due_action="a",
                due_at=self.t0 + 60, now=self.t0)

    def test_a_contact_from_another_tenant_is_refused(self):
        with self.assertRaises(VerificationError):
            self.store.create(
                "t1", self.other_tenant_contact,
                context_ref="c", context_summary="s", owner_id=OWNER,
                backup_owner_id=BACKUP, due_action="a",
                due_at=self.t0 + 60, now=self.t0)

    def test_create_verifies_even_with_a_foreign_fence(self):
        class NoopFence:
            def pause(self, *a, **k):
                return {}

            def release(self, *a, **k):
                return {}

            def is_paused(self, *a, **k):
                return False

        store = h.HandoffStore(self.db, fence=NoopFence())
        with self.assertRaises(VerificationError):
            store.create(
                "t1", "cc_missing", context_ref="c", context_summary="s",
                owner_id=OWNER, backup_owner_id=BACKUP, due_action="a",
                due_at=self.t0 + 60, now=self.t0)

    def test_tenants_do_not_share_a_fence(self):
        self.open()
        t2 = self.store.gate_decision("t2", self.other_tenant_contact)
        self.assertEqual(t2["verdict"], h.GATE_ALLOW)
        self.assertFalse(t2["bot_paused"])
        self.assertEqual(
            self.store.gate_decision("t1", self.contact)["verdict"],
            h.GATE_SUPPRESSED)


class AcceptanceTests(Base):
    def test_assignment_is_not_acceptance(self):
        row = self.open()
        self.assertEqual(row["state"], h.STATE_OFFERED)
        self.assertFalse(row["accepted"])
        self.assertIsNone(row["actual_owner_id"])

    def test_opening_the_handoff_pauses_the_bot(self):
        row = self.open()
        self.assertTrue(row["bot_paused"])
        decision = self.store.gate_decision("t1", self.contact)
        self.assertEqual(decision["verdict"], h.GATE_SUPPRESSED)
        self.assertEqual(decision["reason"], h.REASON_HUMAN)
        self.assertEqual(decision["handoff_id"], row["handoff_id"])
        consent = self.consent().decide("t1", self.contact)
        self.assertFalse(consent["allowed"])
        self.assertEqual(consent["reason"], "consent:human_owned")

    def test_only_the_offered_owner_can_accept(self):
        row = self.open()
        for actor in (BACKUP, "someone-else", "system:handoff"):
            with self.subTest(actor=actor):
                with self.assertRaises(h.HandoffError) as caught:
                    self.store.accept(row["handoff_id"], actor=actor,
                                      now=self.t0 + 5)
                self.assertTrue(
                    str(caught.exception).startswith("refused:"),
                    caught.exception)
        self.assertEqual(self.store.get(row["handoff_id"])["state"],
                         h.STATE_OFFERED)

    def test_the_offered_owner_accepts_and_owns_it(self):
        row = self.accepted()
        self.assertEqual(row["state"], h.STATE_ACTIVE)
        self.assertTrue(row["accepted"])
        self.assertEqual(row["actual_owner_id"], OWNER)
        self.assertTrue(row["bot_paused"])

    def test_acceptance_after_the_due_time_is_refused(self):
        row = self.open()
        with self.assertRaises(h.HandoffError) as caught:
            self.store.accept(row["handoff_id"], actor=OWNER,
                              now=self.t0 + 3600.0)
        self.assertTrue(str(caught.exception).startswith("refused:"))
        after = self.store.get(row["handoff_id"])
        self.assertEqual(after["state"], h.STATE_OFFERED)
        self.assertEqual(after["version"], row["version"])
        self.assertTrue(after["bot_paused"])

    def test_duplicate_acceptance_is_refused(self):
        row = self.accepted()
        with self.assertRaises(h.HandoffError) as caught:
            self.store.accept(row["handoff_id"], actor=OWNER,
                              now=self.t0 + 20)
        self.assertTrue(
            str(caught.exception).startswith("illegal_transition:"))
        self.assertEqual(self.store.get(row["handoff_id"])["version"],
                         row["version"])

    def test_a_stale_expected_version_is_refused(self):
        row = self.open()
        with self.assertRaises(h.HandoffError) as caught:
            self.store.accept(row["handoff_id"], actor=OWNER,
                              now=self.t0 + 5,
                              expect_version=row["version"] + 5)
        self.assertTrue(str(caught.exception).startswith("conflict:"))
        self.assertEqual(self.store.get(row["handoff_id"])["state"],
                         h.STATE_OFFERED)


class EscalationTests(Base):
    def test_escalation_before_the_due_time_is_refused(self):
        row = self.accepted()
        with self.assertRaises(h.HandoffError) as caught:
            self.store.escalate(row["handoff_id"], now=self.t0 + 20)
        self.assertTrue(str(caught.exception).startswith("refused:"))
        self.assertIsNone(self.store.get(row["handoff_id"])["escalated_at"])

    def test_escalation_requires_an_accepted_handoff(self):
        row = self.open()
        with self.assertRaises(h.HandoffError) as caught:
            self.store.escalate(row["handoff_id"], now=self.t0 + 7200)
        self.assertTrue(
            str(caught.exception).startswith("illegal_transition:"))

    def test_overdue_escalation_offers_the_backup_and_stays_paused(self):
        row = self.accepted()
        late = self.t0 + 7200.0
        row = self.store.escalate(row["handoff_id"], now=late)
        self.assertIsNotNone(row["escalated_at"])
        self.assertEqual(row["actual_owner_id"], OWNER)
        self.assertTrue(row["bot_paused"])
        self.assertEqual(row["state"], h.STATE_ACTIVE)
        decision = self.store.gate_decision("t1", self.contact)
        self.assertEqual(decision["verdict"], h.GATE_SUPPRESSED)
        actions = [e["action"] for e in self.store.events(row["handoff_id"])]
        self.assertEqual(actions, [h.ACTION_CREATED, h.ACTION_ACCEPTED,
                                   h.ACTION_ESCALATED])

    def test_escalation_is_recorded_once(self):
        row = self.accepted()
        self.store.escalate(row["handoff_id"], now=self.t0 + 7200)
        with self.assertRaises(h.HandoffError) as caught:
            self.store.escalate(row["handoff_id"], now=self.t0 + 7300)
        self.assertTrue(
            str(caught.exception).startswith("illegal_transition:"))

    def test_backup_acceptance_requires_the_escalation(self):
        row = self.accepted()
        with self.assertRaises(h.HandoffError) as caught:
            self.store.backup_accept(row["handoff_id"], actor=BACKUP,
                                     now=self.t0 + 7200)
        self.assertTrue(str(caught.exception).startswith("refused:"))
        self.assertEqual(self.store.get(row["handoff_id"])["actual_owner_id"],
                         OWNER)

    def test_only_the_named_backup_can_accept_after_escalation(self):
        row = self.accepted()
        self.store.escalate(row["handoff_id"], now=self.t0 + 7200)
        with self.assertRaises(h.HandoffError) as caught:
            self.store.backup_accept(row["handoff_id"], actor="someone-else",
                                     now=self.t0 + 7210)
        self.assertTrue(str(caught.exception).startswith("refused:"))

    def test_backup_acceptance_changes_the_owner_and_keeps_the_fence(self):
        row = self.accepted()
        self.store.escalate(row["handoff_id"], now=self.t0 + 7200)
        row = self.store.backup_accept(row["handoff_id"], actor=BACKUP,
                                       now=self.t0 + 7210)
        self.assertEqual(row["actual_owner_id"], BACKUP)
        self.assertTrue(row["backup_accepted"])
        self.assertTrue(row["bot_paused"])
        actions = [e["action"] for e in self.store.events(row["handoff_id"])]
        self.assertEqual(actions[-1], h.ACTION_BACKUP_ACCEPTED)
        self.assertTrue(self.consent().human_fence(
            "t1", self.contact)["active"])

    def test_the_backup_cannot_accept_twice(self):
        row = self.accepted()
        self.store.escalate(row["handoff_id"], now=self.t0 + 7200)
        self.store.backup_accept(row["handoff_id"], actor=BACKUP,
                                 now=self.t0 + 7210)
        with self.assertRaises(h.HandoffError) as caught:
            self.store.backup_accept(row["handoff_id"], actor=BACKUP,
                                     now=self.t0 + 7220)
        self.assertTrue(
            str(caught.exception).startswith("illegal_transition:"))


class ReleaseTests(Base):
    def test_release_before_acceptance_is_refused(self):
        row = self.open()
        with self.assertRaises(h.HandoffError) as caught:
            self.store.release(row["handoff_id"], actor=OWNER, reason="done")
        self.assertTrue(str(caught.exception).startswith("refused:"))
        after = self.store.get(row["handoff_id"])
        self.assertEqual(after["state"], h.STATE_OFFERED)
        self.assertTrue(after["bot_paused"])

    def test_only_the_actual_owner_can_release(self):
        row = self.accepted()
        for actor in (BACKUP, "someone-else"):
            with self.subTest(actor=actor):
                with self.assertRaises(h.HandoffError) as caught:
                    self.store.release(row["handoff_id"], actor=actor,
                                       reason="done")
                self.assertTrue(
                    str(caught.exception).startswith("refused:"),
                    caught.exception)
        self.assertTrue(self.store.get(row["handoff_id"])["bot_paused"])

    def test_the_primary_owner_cannot_release_after_the_backup_accepted(self):
        row = self.accepted()
        self.store.escalate(row["handoff_id"], now=self.t0 + 7200)
        self.store.backup_accept(row["handoff_id"], actor=BACKUP,
                                 now=self.t0 + 7210)
        with self.assertRaises(h.HandoffError) as caught:
            self.store.release(row["handoff_id"], actor=OWNER,
                               reason="let me close it")
        self.assertTrue(str(caught.exception).startswith("refused:"))
        self.assertTrue(self.store.get(row["handoff_id"])["bot_paused"])

    def test_release_requires_a_reason(self):
        row = self.accepted()
        for reason in ("", "   "):
            with self.subTest(reason=reason):
                with self.assertRaises(h.HandoffError) as caught:
                    self.store.release(row["handoff_id"], actor=OWNER,
                                       reason=reason)
                self.assertTrue(
                    str(caught.exception).startswith("bad_input:"),
                    caught.exception)
        self.assertTrue(self.store.get(row["handoff_id"])["bot_paused"])

    def test_explicit_release_resumes_the_bot(self):
        row = self.accepted()
        row = self.store.release(
            row["handoff_id"], actor=OWNER,
            reason="person served; the bot may answer again",
            release_key="release-1", now=self.t0 + 60)
        self.assertEqual(row["state"], h.STATE_RELEASED)
        self.assertFalse(row["bot_paused"])
        self.assertEqual(row["released_at"], self.t0 + 60)
        decision = self.store.gate_decision("t1", self.contact)
        self.assertEqual(decision["verdict"], h.GATE_ALLOW)
        self.assertFalse(decision["bot_paused"])
        self.assertTrue(self.consent().decide("t1", self.contact)["allowed"])
        self.assertFalse(self.consent().human_fence("t1", self.contact)["active"])

    def test_the_backup_releases_after_it_accepted(self):
        row = self.accepted()
        self.store.escalate(row["handoff_id"], now=self.t0 + 7200)
        self.store.backup_accept(row["handoff_id"], actor=BACKUP,
                                 now=self.t0 + 7210)
        row = self.store.release(row["handoff_id"], actor=BACKUP,
                                 reason="backup handled it", now=self.t0 + 7220)
        self.assertEqual(row["state"], h.STATE_RELEASED)
        self.assertFalse(row["bot_paused"])

    def test_timeout_never_releases_the_bot(self):
        row = self.accepted()
        row = self.store.get(row["handoff_id"])
        self.assertTrue(row["overdue"] is False)
        later = self.store.escalate(row["handoff_id"], now=self.t0 + 7200)
        self.assertTrue(later["bot_paused"])
        self.assertEqual(later["state"], h.STATE_ACTIVE)
        self.assertEqual(self.store.get(row["handoff_id"])["state"],
                         h.STATE_ACTIVE)

    def test_double_release_is_refused(self):
        row = self.accepted()
        self.store.release(row["handoff_id"], actor=OWNER, reason="done",
                           now=self.t0 + 60)
        with self.assertRaises(h.HandoffError) as caught:
            self.store.release(row["handoff_id"], actor=OWNER, reason="again",
                               release_key="release-2", now=self.t0 + 70)
        self.assertTrue(
            str(caught.exception).startswith("illegal_transition:"))

    def test_the_same_release_key_retries_idempotently(self):
        row = self.accepted()
        first = self.store.release(row["handoff_id"], actor=OWNER,
                                   reason="done", release_key="release-1",
                                   now=self.t0 + 60)
        again = self.store.release(row["handoff_id"], actor=OWNER,
                                   reason="done", release_key="release-1",
                                   now=self.t0 + 90)
        self.assertEqual(again["state"], h.STATE_RELEASED)
        self.assertEqual(again["version"], first["version"])
        self.assertEqual(again["released_at"], first["released_at"])
        self.assertEqual(len(self.store.events(row["handoff_id"])),
                         len([a for a in [h.ACTION_CREATED, h.ACTION_ACCEPTED,
                                          h.ACTION_RELEASED]]))

    def test_a_same_key_retry_still_requires_the_actual_owner(self):
        row = self.accepted()
        self.store.release(row["handoff_id"], actor=OWNER, reason="done",
                           release_key="release-1", now=self.t0 + 60)
        # Simulate a crash after the released state committed but before the
        # fence was released: the bot is still paused.
        self.consent().human_takeover(
            "t1", self.contact, actor="crash-recovery",
            reason="simulated_incomplete_release", now=self.t0 + 70)
        with self.assertRaises(h.HandoffError) as caught:
            self.store.release(row["handoff_id"], actor=BACKUP, reason="done",
                               release_key="release-1", now=self.t0 + 80)
        self.assertTrue(str(caught.exception).startswith("refused:"))
        self.assertTrue(self.store.get(row["handoff_id"])["bot_paused"])
        again = self.store.release(row["handoff_id"], actor=OWNER,
                                   reason="done", release_key="release-1",
                                   now=self.t0 + 90)
        self.assertFalse(again["bot_paused"])
        self.assertEqual(again["released_at"], self.t0 + 60)

    def test_release_events_prove_the_transition(self):
        row = self.accepted()
        self.store.release(row["handoff_id"], actor=OWNER, reason="done",
                           now=self.t0 + 60)
        events = self.store.events(row["handoff_id"])
        self.assertEqual([e["action"] for e in events],
                         [h.ACTION_CREATED, h.ACTION_ACCEPTED,
                          h.ACTION_RELEASED])
        self.assertEqual(events[-1]["actor"], OWNER)
        self.assertEqual(events[-1]["reason"], "done")


class RefusalIsNotAChangeTests(Base):
    def test_failed_operations_change_nothing(self):
        row = self.open()
        before = self.store.get(row["handoff_id"])
        for call in (
            lambda: self.store.accept(row["handoff_id"], actor=BACKUP,
                                      now=self.t0 + 5),
            lambda: self.store.escalate(row["handoff_id"], now=self.t0 + 7200),
            lambda: self.store.release(row["handoff_id"], actor=OWNER,
                                       reason="x"),
            lambda: self.store.backup_accept(row["handoff_id"], actor=BACKUP,
                                             now=self.t0 + 7200),
        ):
            with self.assertRaises(h.HandoffError):
                call()
        after = self.store.get(row["handoff_id"])
        self.assertEqual(after["state"], before["state"])
        self.assertEqual(after["version"], before["version"])
        self.assertIsNone(after["actual_owner_id"])
        self.assertTrue(after["bot_paused"])
        self.assertEqual([e["action"] for e in self.store.events(
            row["handoff_id"])], [h.ACTION_CREATED])

    def test_a_failing_fence_prevents_the_handoff(self):
        class BrokenFence:
            def pause(self, *a, **k):
                raise RuntimeError("fence down")
            def release(self, *a, **k):
                raise RuntimeError("fence down")
            def is_paused(self, *a, **k):
                return False

        store = h.HandoffStore(self.db, fence=BrokenFence())
        with self.assertRaises(RuntimeError):
            store.create(
                "t1", self.contact, context_ref="c", context_summary="s",
                owner_id=OWNER, backup_owner_id=BACKUP, due_action="a",
                due_at=self.t0 + 60, now=self.t0)
        with store._read() as conn:
            rows = conn.execute("SELECT COUNT(*) AS n FROM handoffs").fetchone()
        self.assertEqual(rows["n"], 0)


class EscalationDataTests(Base):
    def test_create_is_idempotent_with_a_create_key(self):
        first = self.open(create_key="create-1")
        second = self.store.create(
            "t1", self.contact, context_ref="different", context_summary="x",
            owner_id=OWNER, backup_owner_id=BACKUP, due_action="a",
            due_at=self.t0 + 60, now=self.t0, create_key="create-1")
        self.assertEqual(second["handoff_id"], first["handoff_id"])
        self.assertEqual(len(self.store.open_for_contact("t1", self.contact)), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
