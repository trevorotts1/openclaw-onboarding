#!/usr/bin/env python3
"""S75-T16: the character sync protocol, fixture only.

No client workspace, credential, socket or network call is used anywhere in
this file: the transport is a local function and every wait is collected
instead of slept. Run: python3 test_sync_protocol_s75_t16.py
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

from character_library import sync_protocol as SP  # noqa: E402

NS = "fixture-client-sync"
CHAR = "chr-fixture-marcus"
OTHER = "chr-fixture-nadia"


class Transport:
    """A local stand-in for the authorized connection's call()."""

    def __init__(self, replies=None, failures=0, reply_factory=None):
        self.calls = []
        self.failures_left = failures
        self.replies = list(replies or [])
        self.reply_factory = reply_factory

    def __call__(self, action, payload):
        self.calls.append({"action": action, "payload": dict(payload)})
        if self.failures_left:
            self.failures_left -= 1
            raise TimeoutError("fixture transport went away")
        if self.reply_factory is not None:
            return self.reply_factory(action, payload, len(self.calls))
        if self.replies:
            return self.replies.pop(0)
        return {"revision": int(payload["base_revision"]) + 1,
                "catalog_revision": "sha256:fixture"}


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="s75-t16-")
        self.path = os.path.join(self.temp, "sync-state.json")
        self.slept = []

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)

    def state(self, namespace=NS):
        return SP.SyncState(self.path, namespace)

    def engine(self, transport, **kwargs):
        kwargs.setdefault("sleep", self.slept.append)
        return SP.SyncEngine(self.state(), transport, **kwargs)

    @staticmethod
    def operation(payload=None, *, action="push_identity", object_id=CHAR,
                  base_revision=1):
        return {"action": action, "object_id": object_id,
                "base_revision": base_revision,
                "payload": payload if payload is not None else {"name": "Marcus"}}


class OperationIds(Base):
    def test_same_operation_gets_one_stable_id(self):
        first = SP.operation_id("push_identity", CHAR, 2, {"name": "Marcus", "role": "lead"})
        second = SP.operation_id("push_identity", CHAR, 2, {"role": "lead", "name": "Marcus"})
        self.assertEqual(first, second)
        self.assertTrue(first.startswith("op-"))
        self.assertEqual(len(first), 3 + 32)

    def test_id_changes_with_payload_object_and_base_revision(self):
        base = SP.operation_id("push_identity", CHAR, 1, {"name": "Marcus"})
        self.assertNotEqual(base, SP.operation_id("push_identity", CHAR, 1, {"name": "Nadia"}))
        self.assertNotEqual(base, SP.operation_id("push_identity", OTHER, 1, {"name": "Marcus"}))
        self.assertNotEqual(base, SP.operation_id("push_identity", CHAR, 2, {"name": "Marcus"}))
        self.assertNotEqual(base, SP.operation_id("delete", CHAR, 1, {"name": "Marcus"}))

    def test_repeated_delivery_is_recognised_not_applied_twice(self):
        transport = Transport()
        engine = self.engine(transport)
        first = engine.apply(self.operation())
        again = engine.apply(self.operation())
        self.assertEqual(first["status"], "APPLIED")
        self.assertTrue(first["applied"])
        self.assertEqual(again["status"], "DUPLICATE")
        self.assertFalse(again["applied"])
        self.assertTrue(again["duplicate"])
        self.assertEqual(again["revision"], first["revision"])
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(transport.calls[0]["payload"]["operation_id"],
                         first["operation_id"])

    def test_delivery_is_recognised_after_a_restart(self):
        transport = Transport()
        first = self.engine(transport).apply(self.operation())
        # A fresh store reads the same journal: the id must still be known.
        second = self.engine(transport).apply(self.operation())
        self.assertEqual(second["status"], "DUPLICATE")
        self.assertEqual(second["revision"], first["revision"])
        self.assertEqual(len(transport.calls), 1)

    def test_id_reused_for_a_different_payload_is_refused(self):
        # DEFENSIVE: a public caller cannot build a second operation with an id
        # already used (the id is derived from the payload), so the guard is
        # exercised the only way it can be reached -- a journal whose recorded
        # digest no longer matches the operation that arrives with that id.
        state = self.state()
        engine = SP.SyncEngine(state, Transport(), sleep=self.slept.append)
        engine.apply(self.operation())
        op_id = SP.operation_id("push_identity", CHAR, 1, {"name": "Marcus"})
        recorded = state.operation(op_id)
        recorded["payload_digest"] = "sha256:" + "0" * 64
        state.remember_operation(op_id, recorded)
        with self.assertRaises(SP.OperationRefused):
            engine.apply(self.operation())

    def test_a_failed_operation_may_be_retried_with_the_same_id(self):
        transport = Transport(failures=SP.HARD_MAX_ATTEMPTS)
        engine = self.engine(transport, policy=SP.RetryPolicy(max_attempts=2))
        with self.assertRaises(SP.RetryExhausted):
            engine.apply(self.operation())
        recorded = self.state().operations()
        self.assertEqual([item["status"] for item in recorded.values()], ["FAILED"])
        transport.failures_left = 0
        retried = engine.apply(self.operation())
        self.assertEqual(retried["status"], "APPLIED")
        self.assertFalse(retried["duplicate"])


class BoundedRetry(Base):
    def test_backoff_grows_and_is_capped(self):
        policy = SP.RetryPolicy(max_attempts=5, base_delay=1.0, factor=2.0,
                                max_delay=3.0)
        self.assertEqual([policy.delay_for(n) for n in (1, 2, 3, 4, 5, 6)],
                         [1.0, 2.0, 3.0, 3.0, 3.0, 3.0])

    def test_two_failures_then_success_is_bounded_and_ordered(self):
        transport = Transport(failures=2)
        result = self.engine(transport, policy=SP.RetryPolicy(
            max_attempts=4, base_delay=0.5, factor=2.0)).apply(self.operation())
        self.assertEqual(result["attempts"], 3)
        self.assertEqual(result["delays"], [0.5, 1.0])
        self.assertEqual(self.slept, [0.5, 1.0])
        self.assertEqual(len(transport.calls), 3)

    def test_retry_stops_at_the_ceiling(self):
        transport = Transport(failures=99)
        engine = self.engine(transport, policy=SP.RetryPolicy(max_attempts=3))
        with self.assertRaises(SP.RetryExhausted) as caught:
            engine.apply(self.operation())
        error = caught.exception
        self.assertEqual(error.attempts, 3)
        self.assertEqual(len(error.delays), 2)
        self.assertEqual(len(transport.calls), 3)   # bounded, not spinning
        self.assertTrue(error.operation.startswith("op-"))
        self.assertIn("TimeoutError", error.reason)

    def test_a_policy_cannot_ask_for_an_unbounded_loop(self):
        with self.assertRaises(SP.SyncError):
            SP.RetryPolicy(max_attempts=SP.HARD_MAX_ATTEMPTS + 1)
        with self.assertRaises(SP.SyncError):
            SP.RetryPolicy(max_attempts=0)
        with self.assertRaises(SP.SyncError):
            SP.RetryPolicy(max_attempts=4, factor=0.5)

    def test_zero_delay_policy_still_calls_once(self):
        transport = Transport()
        result = self.engine(transport, policy=SP.RetryPolicy(
            max_attempts=3, base_delay=0)).apply(self.operation())
        self.assertEqual((result["attempts"], result["delays"]), (1, []))
        self.assertEqual(self.slept, [])


class LastSeenRevisions(Base):
    def test_status_tracks_the_last_seen_revision(self):
        state = self.state()
        self.assertEqual(state.status(CHAR, 4), "UNSEEN")
        state.stamp(CHAR, 4)
        self.assertEqual(state.status(CHAR, 4), "IN_SYNC")
        self.assertEqual(state.status(CHAR, 7), "STALE")
        self.assertEqual(state.status(CHAR, 2), "AHEAD")

    def test_last_seen_revision_survives_a_restart(self):
        self.state().stamp(CHAR, 5, catalog_revision="sha256:abc")
        reloaded = self.state()
        self.assertEqual(reloaded.last_seen(CHAR), 5)
        self.assertEqual(reloaded.revisions()[CHAR]["catalog_revision"], "sha256:abc")

    def test_a_successful_push_records_the_new_revision(self):
        result = self.engine(Transport()).apply(self.operation(base_revision=3))
        self.assertEqual(result["revision"], 4)
        self.assertEqual(self.state().last_seen(CHAR), 4)
        self.assertEqual(self.state().status(CHAR, 4), "IN_SYNC")

    def test_one_object_does_not_answer_for_another(self):
        state = self.state()
        state.stamp(CHAR, 9)
        self.assertIsNone(state.last_seen(OTHER))
        self.assertEqual(state.status(OTHER, 9), "UNSEEN")


class ExplicitConflicts(Base):
    def test_unseen_and_unchanged_remote_revisions(self):
        engine = self.engine(Transport())
        adopted = engine.receive(CHAR, remote_revision=2)
        self.assertEqual(adopted["status"], "ADOPTED")
        self.assertEqual(self.state().last_seen(CHAR), 2)
        self.assertEqual(engine.receive(CHAR, remote_revision=2)["status"], "IN_SYNC")

    def test_fast_forward_only_when_it_descends_from_what_we_saw(self):
        self.state().stamp(CHAR, 2)
        engine = self.engine(Transport())
        forward = engine.receive(CHAR, remote_revision=3, remote_parent_revision=2)
        self.assertEqual(forward["status"], "FAST_FORWARD")
        self.assertEqual(self.state().last_seen(CHAR), 3)

    def test_a_rewritten_base_is_a_conflict_not_a_fast_forward(self):
        self.state().stamp(CHAR, 2)
        engine = self.engine(Transport())
        with self.assertRaises(SP.SyncConflict) as caught:
            engine.receive(CHAR, remote_revision=7, remote_parent_revision=5)
        self.assertEqual(caught.exception.record["reason_code"], "REMOTE_REWRITTEN_BASE")

    def test_a_newer_revision_without_a_declared_parent_is_a_conflict(self):
        # Descent that was not declared is not proved, so it is surfaced.
        self.state().stamp(CHAR, 2)
        with self.assertRaises(SP.SyncConflict) as caught:
            self.engine(Transport()).receive(CHAR, remote_revision=3)
        self.assertEqual(caught.exception.record["reason_code"],
                         "REMOTE_PARENT_UNKNOWN")
        self.assertEqual(self.state().last_seen(CHAR), 2)

    def test_a_transport_reply_without_a_revision_is_recorded_as_failed(self):
        engine = self.engine(Transport(reply_factory=lambda a, p, n: {}))
        with self.assertRaises(SP.SyncError):
            engine.apply(self.operation())
        recorded = list(self.state().operations().values())[0]
        self.assertEqual(recorded["status"], "FAILED")
        # Not stuck IN_FLIGHT: a retry with the same id is attempted again.
        retried = self.engine(Transport()).apply(self.operation())
        self.assertEqual(retried["status"], "APPLIED")

    def test_unpushed_local_edit_refuses_and_records_the_conflict(self):
        self.state().stamp(CHAR, 5)
        engine = self.engine(Transport())
        with self.assertRaises(SP.SyncConflict) as caught:
            engine.receive(CHAR, remote_revision=6, local_dirty=True,
                           detected_at="2026-10-25T00:00:00Z")
        record = caught.exception.record
        self.assertEqual(record["local_revision"], 5)
        self.assertEqual(record["remote_revision"], 6)
        self.assertEqual(record["reason_code"], "LOCAL_EDIT_UNPUSHED")
        self.assertEqual(record["resolution"], "REFUSED_PENDING_CLIENT_CHOICE")
        self.assertIn("No silent last-writer-wins", record["rule"])
        stored = self.state().conflicts()
        self.assertEqual([item["conflict_id"] for item in stored],
                         [record["conflict_id"]])
        # Nothing was overwritten: the local revision is untouched.
        self.assertEqual(self.state().last_seen(CHAR), 5)

    def test_a_remote_rollback_is_a_conflict(self):
        self.state().stamp(CHAR, 8)
        with self.assertRaises(SP.SyncConflict) as caught:
            self.engine(Transport()).receive(CHAR, remote_revision=3, local_dirty=False)
        self.assertEqual(caught.exception.record["reason_code"], "REMOTE_ROLLED_BACK")
        self.assertEqual(self.state().last_seen(CHAR), 8)

    def test_a_winner_only_applies_when_the_caller_named_it_first(self):
        self.state().stamp(CHAR, 5)
        engine = self.engine(Transport(), on_conflict="remote_wins")
        result = engine.receive(CHAR, remote_revision=9, local_dirty=True)
        self.assertEqual(result["status"], "CONFLICT_RESOLVED_REMOTE")
        self.assertEqual(result["conflict"]["resolution"], "RESOLVED_REMOTE")
        self.assertEqual(self.state().last_seen(CHAR), 9)
        self.assertEqual(len(self.state().conflicts()), 1)

    def test_later_resolution_is_explicit(self):
        self.state().stamp(CHAR, 5)
        with self.assertRaises(SP.SyncConflict) as caught:
            self.engine(Transport()).receive(CHAR, remote_revision=6,
                                             local_dirty=True)
        conflict_id = caught.exception.record["conflict_id"]
        kept = self.state().resolve_conflict(conflict_id, "keep_local")
        self.assertEqual(kept["resolution"], "RESOLVED_LOCAL")
        self.assertEqual(self.state().last_seen(CHAR), 5)
        taken = self.state().resolve_conflict(conflict_id, "take_remote")
        self.assertEqual(taken["resolution"], "RESOLVED_REMOTE")
        self.assertEqual(self.state().last_seen(CHAR), 6)
        with self.assertRaises(SP.SyncError):
            self.state().resolve_conflict("cf-unknown", "keep_local")

    def test_an_unknown_conflict_policy_is_refused(self):
        with self.assertRaises(SP.SyncError):
            SP.SyncEngine(self.state(), Transport(), on_conflict="last_writer_wins")


class OfflineSnapshots(Base):
    def approval(self, scope=NS):
        return {"approver": "fixture-approver", "approval_id": "ap-1",
                "scope": scope}

    def test_snapshot_needs_a_real_approval_bound_to_this_client(self):
        state = self.state()
        with self.assertRaises(SP.SyncError):
            SP.build_offline_snapshot(state, objects={CHAR: 2}, approval=None)
        with self.assertRaises(SP.SnapshotRefused):
            SP.build_offline_snapshot(state, objects={CHAR: 2},
                                      approval=self.approval("someone-else"))
        with self.assertRaises(SP.SnapshotRefused):
            SP.build_offline_snapshot(state, objects={}, approval=self.approval())

    def test_snapshot_carries_revision_and_sync_status(self):
        state = self.state()
        state.stamp(CHAR, 2)
        first = SP.build_offline_snapshot(
            state, objects={CHAR: 2}, approval=self.approval(),
            remote_revisions={CHAR: 2}, captured_at="2026-10-25T00:00:00Z")
        second = SP.build_offline_snapshot(
            state, objects={CHAR: 2}, approval=self.approval())
        self.assertEqual((first["revision"], second["revision"]), (1, 2))
        self.assertTrue(first["offline"])
        self.assertEqual(first["sync_status"], "IN_SYNC")
        self.assertEqual(second["sync_status"], "UNVERIFIED_OFFLINE")
        self.assertEqual(first["captured_at"], "2026-10-25T00:00:00Z")
        self.assertEqual(first["approval"]["approver"], "fixture-approver")
        self.assertTrue(first["catalog_revision"].startswith("sha256:"))
        self.assertEqual(first["objects"], [{"object_id": CHAR, "revision": 2}])

    def test_out_of_sync_snapshot_says_so(self):
        state = self.state()
        stale = SP.build_offline_snapshot(
            state, objects={CHAR: 2}, approval=self.approval(),
            remote_revisions={CHAR: 5})
        self.assertEqual(stale["sync_status"], "OUT_OF_SYNC")
        missing = SP.build_offline_snapshot(
            state, objects={CHAR: 2, OTHER: 1}, approval=self.approval(),
            remote_revisions={CHAR: 2})
        self.assertEqual(missing["sync_status"], "OUT_OF_SYNC")

    def test_approved_snapshot_is_usable_and_reports_its_status(self):
        state = self.state()
        snapshot = SP.build_offline_snapshot(
            state, objects={CHAR: 2}, approval=self.approval(),
            remote_revisions={CHAR: 2})
        used = SP.use_offline_snapshot(snapshot)
        self.assertTrue(used["usable"])
        self.assertEqual(used["revision"], snapshot["revision"])
        self.assertEqual(used["sync_status"], "IN_SYNC")
        self.assertEqual(used["approved_by"], "fixture-approver")

    def test_unapproved_tampered_or_stale_snapshots_are_refused(self):
        state = self.state()
        snapshot = SP.build_offline_snapshot(
            state, objects={CHAR: 2}, approval=self.approval(),
            remote_revisions={CHAR: 2})

        edited = dict(snapshot)
        edited["objects"] = [{"object_id": CHAR, "revision": 99}]
        with self.assertRaises(SP.SnapshotRefused):
            SP.use_offline_snapshot(edited)

        # Re-digest after stripping the approver, so the APPROVAL check is the
        # one that refuses this, not the tamper check above it.
        unapproved = dict(snapshot)
        unapproved["approval"] = {"approver": "", "approval_id": "ap-1",
                                  "scope": NS}
        unapproved["digest"] = SP.payload_digest(
            {k: v for k, v in unapproved.items() if k != "digest"})
        with self.assertRaises(SP.SyncError):
            SP.use_offline_snapshot(unapproved)

        stale = SP.build_offline_snapshot(
            state, objects={CHAR: 2}, approval=self.approval(),
            remote_revisions={CHAR: 5})
        with self.assertRaises(SP.SnapshotRefused):
            SP.use_offline_snapshot(stale)
        allowed = SP.use_offline_snapshot(stale, allow_out_of_sync=True)
        self.assertEqual(allowed["sync_status"], "OUT_OF_SYNC")

        online = dict(snapshot)
        online["offline"] = False
        with self.assertRaises(SP.SnapshotRefused):
            SP.use_offline_snapshot(online)

    def test_snapshot_round_trips_through_a_file(self):
        state = self.state()
        snapshot = SP.build_offline_snapshot(
            state, objects={CHAR: 2, OTHER: 4}, approval=self.approval())
        path = os.path.join(self.temp, "snapshots", "cast-r1.json")
        SP.write_snapshot(path, snapshot)
        reloaded = SP.load_snapshot(path)
        self.assertEqual(reloaded, snapshot)
        self.assertEqual(SP.use_offline_snapshot(reloaded)["objects"],
                         [{"object_id": CHAR, "revision": 2},
                          {"object_id": OTHER, "revision": 4}])
        self.assertIsNone(SP.load_snapshot(os.path.join(self.temp, "nope.json")))

    def test_state_refuses_another_clients_file(self):
        self.state().stamp(CHAR, 1)
        with self.assertRaises(SP.SyncError):
            SP.SyncState(self.path, "a-different-client")


class NoNetworkOrSecrets(unittest.TestCase):
    def test_protocol_module_makes_no_network_call_and_names_no_credential(self):
        with open(os.path.join(HERE, "sync_protocol.py"), encoding="utf-8") as handle:
            source = handle.read()
        for forbidden in ("import socket", "import urllib", "import http",
                          "import requests", "import ssl", "Authorization",
                          "Bearer"):
            self.assertNotIn(forbidden, source)
        self.assertIn("callable(call)", source)   # transport is injected only


if __name__ == "__main__":
    unittest.main(verbosity=2)
