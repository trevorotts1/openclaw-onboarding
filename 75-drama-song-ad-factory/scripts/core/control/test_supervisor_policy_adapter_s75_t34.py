#!/usr/bin/env python3
"""S75-T34: contract tests for the changed supervisor control layer.

Every host effect is a local fake: no process is started, signalled or
inspected, no network call is made and no client data is used. Each clause of
S75-A34 has a test that constructs the violation first, then shows the control
reporting it (and, where a restore applies, the control clearing afterwards).

Run: python3 test_supervisor_policy_adapter_s75_t34.py
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

from control import supervisor_policy_adapter as SP  # noqa: E402

START = "2026-10-25T00:00:00Z-4242"


def assignment(**overrides):
    record = {
        "unit_id": "S75-T34",
        "attempt_generation": 1,
        "project": "proj-disposable",
        "state": "READY",
        "owner": "worker-a",
        "lease_generation": 7,
        "scope": ["control/supervisor_policy_adapter.py"],
        "counters": {"failures": 2, "budget_used": 3},
        "sequence": 10,
        "ready_age_ticks": 0,
    }
    record.update(overrides)
    return record


def worker(**overrides):
    record = {
        "pid": 4242,
        "start_identity": START,
        "executable": "/opt/disposable/bin/python3",
        "cwd": "/tmp/proj-disposable",
        "project": "proj-disposable",
        "owner_id": "worker-a",
        "lease_generation": 7,
    }
    record.update(overrides)
    return record


def stopped_proof(**overrides):
    proof = {
        "process_absent": True,
        "terminal_ack": True,
        "write_owner_readback": {"pid": 4242, "start_identity": START},
        "owner_counted": True,
    }
    proof.update(overrides)
    return proof


class FakeEffects:
    """Local stand-in for the host's supported supervisor operations."""

    def __init__(self, *, fence=True, fence_readback=True, ack=True,
                 observations=((False, False),), revalidate=True,
                 terminate_targets=None, verify=None, services=None):
        self.calls = []
        self._fence = fence
        self._fence_readback = fence_readback
        self._ack = ack
        self._observations = list(observations)
        self._revalidate = revalidate
        self._verify = stopped_proof() if verify is None else verify
        self._services = services or []
        self._targets = terminate_targets
        self._last = self._observations[-1] if self._observations else (False, False)

    def fence(self, offender):
        self.calls.append("fence")
        return {"fenced": self._fence, "readback_verified": self._fence_readback}

    def request_stop(self, offender, deadline_seconds):
        self.calls.append("request_stop")
        return {"ack": self._ack, "deadline_seconds": deadline_seconds}

    def observe(self, offender):
        self.calls.append("observe")
        if self._observations:
            self._last = self._observations.pop(0)
        return {"running": self._last[0], "grace_expired": self._last[1]}

    def revalidate_fingerprint(self, offender):
        self.calls.append("revalidate_fingerprint")
        return {"matches": self._revalidate}

    def terminate_scoped(self, offender):
        self.calls.append("terminate_scoped")
        targets = self._targets
        if targets is None:
            targets = [{"pid": offender["pid"],
                        "start_identity": offender["start_identity"]}]
        return {"terminated": targets, "affected_services": list(self._services)}

    def verify_stopped(self, offender):
        self.calls.append("verify_stopped")
        return dict(self._verify)


class FakeIsolation:
    def __init__(self, **result):
        self.calls = []
        self._result = result or {"access_fenced": True,
                                  "assignment_fenced": True,
                                  "readback_verified": True}

    def isolate(self, payload):
        self.calls.append("isolate")
        return dict(self._result)


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.mkdtemp(prefix="s75-t34-")

    def tearDown(self):
        shutil.rmtree(self.temp, ignore_errors=True)


class TestMissedReadyDetection(Base):
    """Row clause: changed controls detect a missed-ready violation."""

    def test_ready_past_threshold_without_dispatch_is_reported(self):
        ready = assignment(state="READY", ready_age_ticks=2)
        self.assertEqual(SP.detect_missed_ready([ready]), [{
            "class": SP.MISSED_READY,
            "unit_id": "S75-T34",
            "reason": "READY_WITHOUT_DISPATCH",
            "ready_age_ticks": 2,
            "threshold_ticks": 2,
            "attempt_generation": 1,
        }])

    def test_below_threshold_dispatch_receipt_and_running_states_are_clean(self):
        self.assertEqual(SP.detect_missed_ready([assignment(ready_age_ticks=1)]), [])
        self.assertEqual(SP.detect_missed_ready(
            [assignment(ready_age_ticks=9, dispatch_receipt={"id": "r-1"})]), [])
        self.assertEqual(SP.detect_missed_ready(
            [assignment(state="RUNNING", ready_age_ticks=9)]), [])

    def test_violation_clears_when_the_restored_record_is_dispatched(self):
        violations = SP.detect_missed_ready([assignment(ready_age_ticks=5)])
        self.assertEqual(len(violations), 1)
        restored = assignment(ready_age_ticks=5,
                              dispatch_receipt={"id": "r-1", "owner": "worker-a"})
        self.assertEqual(SP.detect_missed_ready([restored]), [])


class TestOwnedViolationDetection(Base):
    """Row clause: changed controls detect an owned violation."""

    def test_each_owned_reason_is_reported(self):
        record = assignment(shared_paths=["/tmp/proj-disposable/shared.json"])
        foreign = SP.detect_owned_violation(
            record, worker(project="other-project"))
        self.assertEqual([row["reason"] for row in foreign["violations"]],
                         ["FOREIGN_PROJECT_WRITER"])

        lease = SP.detect_owned_violation(record, worker(lease_generation=6))
        self.assertEqual([row["reason"] for row in lease["violations"]],
                         ["LEASE_GENERATION_MISMATCH"])

        owner = SP.detect_owned_violation(record, worker(owner_id="worker-b"))
        self.assertEqual([row["reason"] for row in owner["violations"]],
                         ["OWNER_MISMATCH"])

        shared = SP.detect_owned_violation(
            record, worker(),
            shared_writers={"/tmp/proj-disposable/shared.json":
                            ["worker-a", "worker-b"]})
        self.assertEqual([row["reason"] for row in shared["violations"]],
                         ["SHARED_FILE_SECOND_WRITER"])
        self.assertEqual(shared["violations"][0]["owners"], ["worker-a", "worker-b"])

    def test_clean_owner_is_not_a_violation_and_restore_clears_it(self):
        record = assignment()
        dirty = SP.detect_owned_violation(record, worker(project="other-project"))
        self.assertEqual(dirty["status"], SP.OWNED_VIOLATION)
        restored = SP.detect_owned_violation(record, worker())
        self.assertEqual(restored["status"], "OWNED_OK")
        self.assertEqual(restored["violations"], [])

    def test_partial_fingerprint_is_unknown_ownership_not_a_violation(self):
        record = assignment()
        missing_start = SP.detect_owned_violation(
            record, worker(start_identity=""))
        self.assertEqual(missing_start["status"], "OWNER_UNKNOWN")
        self.assertEqual(missing_start["reason"], "INCOMPLETE_FINGERPRINT")
        self.assertIn("start_identity", missing_start["missing_fields"])

        name_only = SP.detect_owned_violation(
            record, {"name": "python3", "cwd": "/tmp/proj-disposable"})
        self.assertEqual(name_only["status"], "OWNER_UNKNOWN")
        self.assertEqual(name_only["reason"], "INCOMPLETE_FINGERPRINT")

    def test_assessment_is_sorted_and_separates_unknown_owners(self):
        report = SP.assess(
            [assignment(unit_id="S75-T40", ready_age_ticks=3),
             assignment(unit_id="S75-T34", state="QUEUED", ready_age_ticks=4)],
            {"S75-T34": worker(project="other-project")},
            threshold_ticks=2)
        self.assertEqual([row["unit_id"] for row in report["violations"]],
                         ["S75-T34", "S75-T40", "S75-T34"])
        self.assertEqual([row["class"] for row in report["violations"]],
                         [SP.MISSED_READY, SP.MISSED_READY, SP.OWNED_VIOLATION])
        self.assertEqual([row["unit_id"] for row in report["unknown_owners"]],
                         ["S75-T40"])
        self.assertFalse(report["clean"])


class TestCheckpointPreservation(Base):
    """Row clause: preserve the checkpoint before anything is stopped."""

    def test_checkpoint_round_trips_counters_and_marks_volatile_paths(self):
        receipt = SP.preserve_checkpoint(
            assignment(),
            self.temp,
            volatile_paths=["/tmp/proj-disposable/still-writing.log"])
        self.assertTrue(receipt["readable"])
        self.assertEqual(receipt["counters"], {"failures": 2, "budget_used": 3})
        self.assertEqual(receipt["volatile_paths"][0]["status"], "NOT_READ")
        self.assertNotIn("content", receipt["volatile_paths"][0])
        self.assertTrue(SP.verify_checkpoint(receipt))
        with open(receipt["path"], "rb") as handle:
            payload = json.loads(handle.read().decode("utf-8"))
        self.assertEqual(payload["schema"], SP.CHECKPOINT_SCHEMA)
        self.assertEqual(payload["scope"], ["control/supervisor_policy_adapter.py"])

    def test_tampered_checkpoint_fails_verification(self):
        receipt = SP.preserve_checkpoint(assignment(), self.temp)
        with open(receipt["path"], "w", encoding="utf-8") as handle:
            handle.write('{"schema": "tampered"}\n')
        self.assertFalse(SP.verify_checkpoint(receipt))
        self.assertFalse(SP.verify_checkpoint({"path": receipt["path"],
                                               "digest": "sha256:0000"}))

    def test_checkpoint_requires_unit_and_generation(self):
        with self.assertRaises(SP.ControlRefused):
            SP.preserve_checkpoint(assignment(attempt_generation=0), self.temp)


class TestStopBeforeReplacement(Base):
    """Row clause: stop the verified offender before any replacement."""

    def test_verified_stop_precedes_one_replacement(self):
        effects = FakeEffects()
        result = SP.stop_verified_offender(worker(), effects)
        self.assertEqual(result["status"], SP.STOPPED_VERIFIED)
        self.assertEqual(effects.calls,
                         ["fence", "request_stop", "observe", "verify_stopped"])
        self.assertFalse(result["terminated"])

        checkpoint = SP.preserve_checkpoint(assignment(), self.temp)
        successor = assignment(attempt_generation=2, state="QUEUED",
                               exclusive_lease=True)
        plan = SP.plan_replacement(assignment(), successor,
                                   stop_result=result, checkpoint=checkpoint)
        self.assertEqual(plan["status"], "REPLACED")
        self.assertEqual(plan["successor"]["attempt_generation"], 2)
        self.assertTrue(plan["successor"]["scope_preserved"])
        self.assertEqual(plan["successor"]["predecessor_status"],
                         SP.STOPPED_VERIFIED)

    def test_running_offender_within_grace_blocks_replacement(self):
        effects = FakeEffects(observations=((True, False),))
        result = SP.stop_verified_offender(worker(), effects)
        self.assertEqual(result["status"], SP.STOP_UNVERIFIED)
        self.assertEqual(result["reason"], "STILL_RUNNING")
        self.assertNotIn("terminate_scoped", effects.calls)
        checkpoint = SP.preserve_checkpoint(assignment(), self.temp)
        with self.assertRaises(SP.ReplacementRefused):
            SP.plan_replacement(assignment(),
                                assignment(attempt_generation=2,
                                           exclusive_lease=True, state="QUEUED"),
                                stop_result=result, checkpoint=checkpoint)

    def test_ignored_deadline_revalidates_then_scoped_termination_verifies(self):
        effects = FakeEffects(observations=((True, True), (False, False)))
        result = SP.stop_verified_offender(worker(), effects)
        self.assertEqual(result["status"], SP.STOPPED_VERIFIED)
        self.assertTrue(result["terminated"])
        self.assertEqual(effects.calls,
                         ["fence", "request_stop", "observe",
                          "revalidate_fingerprint", "terminate_scoped",
                          "observe", "verify_stopped"])

    def test_termination_scope_escape_is_refused(self):
        effects = FakeEffects(
            observations=((True, True), (False, False)),
            terminate_targets=[{"pid": 9999, "start_identity": START}])
        with self.assertRaises(SP.StopRefused) as caught:
            SP.stop_verified_offender(worker(), effects)
        self.assertEqual(str(caught.exception), "SCOPE_ESCAPE")

    def test_shared_service_termination_is_refused(self):
        effects = FakeEffects(observations=((True, True), (False, False)),
                              services=["pm2:gateway"])
        with self.assertRaises(SP.StopRefused) as caught:
            SP.stop_verified_offender(worker(), effects)
        self.assertEqual(str(caught.exception), "PROTECTED_SERVICE_TOUCHED")

    def test_fence_without_readback_stops_the_sequence(self):
        effects = FakeEffects(fence_readback=False)
        with self.assertRaises(SP.StopRefused) as caught:
            SP.stop_verified_offender(worker(), effects)
        self.assertEqual(str(caught.exception), "FENCE_UNVERIFIED")
        self.assertEqual(effects.calls, ["fence"])

    def test_incomplete_offender_fingerprint_is_refused(self):
        with self.assertRaises(SP.StopRefused) as caught:
            SP.stop_verified_offender(worker(start_identity=""), FakeEffects())
        self.assertIn("INCOMPLETE_OFFENDER_FINGERPRINT", str(caught.exception))

    def test_stop_proof_without_owner_count_or_terminal_ack_is_unverified(self):
        for proof in (stopped_proof(owner_counted=False),
                      stopped_proof(terminal_ack=False),
                      stopped_proof(write_owner_readback=None)):
            result = SP.stop_verified_offender(worker(), FakeEffects(verify=proof))
            self.assertEqual(result["status"], SP.STOP_UNVERIFIED)
            self.assertEqual(result["reason"], "STOP_PROOF_INCOMPLETE")

    def test_replacement_requires_fresh_generation_exclusive_lease_and_scope(self):
        result = SP.stop_verified_offender(worker(), FakeEffects())
        checkpoint = SP.preserve_checkpoint(assignment(), self.temp)
        for successor, error in (
            (assignment(attempt_generation=1, state="QUEUED",
                        exclusive_lease=True), "SUCCESSOR_GENERATION_NOT_FRESH"),
            (assignment(attempt_generation=2, state="QUEUED"), "SUCCESSOR_LEASE_NOT_EXCLUSIVE"),
            (assignment(attempt_generation=2, state="QUEUED",
                        exclusive_lease=True, scope=["another.py"]), "SCOPE_CHANGED"),
        ):
            with self.assertRaises(SP.ReplacementRefused) as caught:
                SP.plan_replacement(assignment(), successor,
                                    stop_result=result, checkpoint=checkpoint)
            self.assertEqual(str(caught.exception), error)


class TestUnknownOwnerIsolation(Base):
    """Row clause: isolate an unknown owner nondestructively."""

    def test_unknown_owner_is_isolated_and_not_killed(self):
        effects = FakeIsolation()
        result = SP.isolate_unknown_owner(assignment(owner="", owner_verified=False),
                                          effects)
        self.assertEqual(result["status"], SP.ISOLATED_UNKNOWN_OWNER)
        self.assertFalse(result["killed"])
        self.assertTrue(result["owner_counted"])
        self.assertIn("OWNER_UNKNOWN", result["uncertainty"])
        self.assertEqual(effects.calls, ["isolate"])

    def test_isolation_that_kills_is_refused(self):
        effects = FakeIsolation(access_fenced=True, assignment_fenced=True,
                                readback_verified=True, killed=True)
        with self.assertRaises(SP.ControlRefused) as caught:
            SP.isolate_unknown_owner(assignment(owner="", owner_verified=False),
                                     effects)
        self.assertEqual(str(caught.exception), "ISOLATION_WAS_DESTRUCTIVE")

    def test_unverified_isolation_is_refused(self):
        effects = FakeIsolation(access_fenced=True, assignment_fenced=False,
                                readback_verified=True)
        with self.assertRaises(SP.ControlRefused) as caught:
            SP.isolate_unknown_owner(assignment(owner="", owner_verified=False),
                                     effects)
        self.assertEqual(str(caught.exception), "ISOLATION_UNVERIFIED")

    def test_known_owner_is_not_isolated_as_unknown(self):
        with self.assertRaises(SP.ControlRefused) as caught:
            SP.isolate_unknown_owner(assignment(owner_verified=True), FakeIsolation())
        self.assertEqual(str(caught.exception), "OWNER_IS_KNOWN")


class TestRestartReconciliation(Base):
    """Row clause: reconcile restart and start the successor read-only."""

    def _seed(self):
        SP.preserve_checkpoint(
            assignment(attempt_generation=1, sequence=10,
                       counters={"failures": 2, "budget_used": 3}),
            self.temp)
        SP.preserve_checkpoint(
            assignment(attempt_generation=2, sequence=12,
                       counters={"failures": 2, "budget_used": 3}),
            self.temp)

    def test_restart_loads_both_checkpoints_and_replays_newer_events_only(self):
        self._seed()
        report = SP.reconcile_restart(
            self.temp,
            events=[
                {"sequence": 9, "kind": "DECISION", "id": "old-decision"},
                {"sequence": 13, "kind": "HOLD", "id": "hold-1", "status": "PAUSED"},
                {"sequence": 14, "kind": "TOMBSTONE", "id": "S75-T31"},
                {"sequence": 15, "kind": "RELEASE", "id": "hold-1"},
                {"sequence": 16, "kind": "MYSTERY", "id": "unknown-1"},
            ])
        self.assertEqual(report["current"]["attempt_generation"], 2)
        self.assertEqual(report["previous"]["attempt_generation"], 1)
        self.assertEqual([row["id"] for row in report["events_applied"]],
                         ["hold-1", "S75-T31", "hold-1"])
        self.assertEqual([row["id"] for row in report["events_skipped"]], ["old-decision"])
        self.assertEqual(report["holds"], {})
        self.assertEqual(report["tombstones"], ["S75-T31"])
        self.assertEqual(report["unresolved"][0]["kind"], "MYSTERY")
        self.assertEqual(report["counters"], {"failures": 2, "budget_used": 3})
        self.assertFalse(report["counters_reset"])
        self.assertTrue(report["successor_plan"]["read_only"])
        self.assertFalse(report["successor_plan"]["generation_transfer_allowed"])
        self.assertEqual(report["job_gap"], "NO_SUPERVISION_JOB_REGISTERED")

    def test_duplicate_supervision_job_is_refused(self):
        self._seed()
        with self.assertRaises(SP.RestartRefused) as caught:
            SP.reconcile_restart(self.temp, jobs=[{"id": "job-a"}, {"id": "job-b"}])
        self.assertEqual(str(caught.exception), "DUPLICATE_SUPERVISION_JOB")

    def test_missing_checkpoint_is_refused(self):
        with self.assertRaises(SP.RestartRefused) as caught:
            SP.reconcile_restart(self.temp)
        self.assertEqual(str(caught.exception), "NO_READABLE_CHECKPOINT")

    def test_workers_are_retained_or_flagged_never_killed(self):
        self._seed()
        report = SP.reconcile_restart(
            self.temp,
            jobs=[{"id": "job-a"}],
            workers=[worker(), worker(lease_generation=3),
                     {"name": "python3", "cwd": "/tmp/proj-disposable"}])
        actions = [row["action"] for row in report["workers"]]
        self.assertEqual(actions, ["RETAINED", "NEEDS_RECONCILIATION",
                                   "ISOLATE_NONDESTRUCTIVELY"])
        self.assertEqual(report["unknown_workers"], 1)

    def test_transfer_needs_verified_stop_and_exactly_one_generation(self):
        predecessor = {"unit_id": "S75-T34", "control_generation": 4}
        successor = {"read_only": True, "control_generation": None}
        with self.assertRaises(SP.RestartRefused):
            SP.transfer_control(predecessor, 5, predecessor_status="RUNNING",
                                successor=successor)
        with self.assertRaises(SP.RestartRefused) as caught:
            SP.transfer_control(predecessor, 6,
                                predecessor_status=SP.STOPPED_VERIFIED,
                                successor=successor)
        self.assertEqual(str(caught.exception), "GENERATION_NOT_NEXT")
        with self.assertRaises(SP.RestartRefused) as caught:
            SP.transfer_control(predecessor, 5,
                                predecessor_status=SP.STOPPED_VERIFIED,
                                successor={"control_generation": 5})
        self.assertEqual(str(caught.exception), "GENERATION_ALREADY_TRANSFERRED")
        transferred = SP.transfer_control(
            predecessor, 5, predecessor_status=SP.STOPPED_VERIFIED,
            successor=successor)
        self.assertEqual(transferred["status"], "TRANSFERRED")
        self.assertEqual(transferred["to_generation"], 5)
        self.assertFalse(transferred["successor"]["read_only"])


class TestActivationNeverFromDocumentsOrHeartbeat(Base):
    """Row clause: documents/heartbeat alone never establish ACTIVE."""

    def _readback(self):
        return {
            "controller_identity": {"id": "existing-supervisor"},
            "controller_revision": "rev-2026-10-25",
            "policy": {
                "control_interval_seconds": 60,
                "ready_unassigned_threshold_ticks": 2,
                "stop_grace_seconds": 60,
                "readback_verified": True,
            },
            "startup_readback": {"started_at": "2026-10-25T00:00:00Z",
                                 "readback_verified": True},
            "owner_generation_readback": {"generation": 4,
                                          "readback_verified": True},
            "state_path_proof": {"path": "/tmp/proj-disposable/state",
                                 "portable_verified": True},
            "supported_operations": list(SP.REQUIRED_OPERATIONS),
            "failure_injection_receipt": {"independent": True, "detected": True,
                                          "outcome": "DETECTED_AND_CORRECTED"},
        }

    def test_documents_and_heartbeat_alone_are_not_active(self):
        result = SP.activation_status({
            "document": "LOOP-CONTROL.md",
            "heartbeat_utc": "2026-10-25T00:00:00Z",
        })
        self.assertEqual(result["status"], SP.NOT_ACTIVE)
        self.assertEqual(result["evidence"], "DOCUMENT_HEARTBEAT_ONLY")
        self.assertEqual(result["missing"], sorted(SP.REQUIRED_ACTIVATION_FACETS))
        self.assertEqual(result["disqualified_evidence"],
                         ["document", "heartbeat_utc"])

    def test_full_installed_controller_readback_is_active(self):
        result = SP.activation_status(self._readback())
        self.assertEqual(result["status"], SP.ACTIVE)
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["capability_gaps"], [])

    def test_missing_operation_is_a_named_capability_gap(self):
        readback = self._readback()
        readback["supported_operations"] = ["observe", "dispatch", "lease",
                                            "fence", "stop", "verify", "report"]
        result = SP.activation_status(readback)
        self.assertEqual(result["status"], SP.NOT_ACTIVE)
        self.assertEqual(result["capability_gaps"], ["terminate"])
        self.assertIn("supported_operations", result["missing"])

    def test_missing_independent_failure_injection_stays_not_active(self):
        readback = self._readback()
        del readback["failure_injection_receipt"]
        result = SP.activation_status(readback)
        self.assertEqual(result["status"], SP.NOT_ACTIVE)
        self.assertEqual(result["missing"], ["failure_injection_receipt"])

    def test_document_alongside_readback_is_ignored_not_credited(self):
        readback = self._readback()
        readback["document"] = "LOOP-CONTROL.md"
        result = SP.activation_status(readback)
        self.assertEqual(result["status"], SP.ACTIVE)
        self.assertEqual(result["disqualified_evidence"], ["document"])


class TestEvidenceAndHygiene(Base):
    def test_evidence_write_read_round_trip(self):
        path = os.path.join(self.temp, "evidence", "control-activation.json")
        written = SP.write_evidence(path, {"status": SP.NOT_ACTIVE})
        self.assertTrue(written["digest"].startswith("sha256:"))
        self.assertEqual(SP.read_evidence(path), {"status": SP.NOT_ACTIVE})
        self.assertIsNone(SP.read_evidence(os.path.join(self.temp, "absent.json")))

    def test_module_makes_no_network_call_and_names_no_credential(self):
        with open(os.path.join(HERE, "supervisor_policy_adapter.py"),
                  encoding="utf-8") as handle:
            source = handle.read()
        for forbidden in ("import socket", "import urllib", "import http",
                          "import requests", "import ssl", "Authorization",
                          "Bearer", "os.kill", "killall", "subprocess"):
            self.assertNotIn(forbidden, source)
        self.assertIn("effects.fence", source)
        self.assertIn("effects.terminate_scoped", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
