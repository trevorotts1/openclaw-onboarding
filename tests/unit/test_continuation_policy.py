#!/usr/bin/env python3
"""Unit JEV-012: owner-direct/named-worker continuation policy (spec 1.1, s 5.5).

Offline regression tests: no client runtime, provider calls or config writes.
Consumes D11 shared-utils/execution_policy LIVE and reuses D23
shared-utils/decision_engine/commit by IMPORT (no logic restated, no files
modified under commit/).
"""
import importlib.util
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_REPO_ROOT / 'shared-utils'))
sys.path.insert(0, str(_REPO_ROOT / 'shared-utils/execution_policy'))
sys.path.insert(0, str(_REPO_ROOT / 'shared-utils/decision_engine'))

import execution_policy as ep
from execution_policy import ExecutionPolicyRecord
from continuation import (
    EXECUTION_ACTIVE,
    HOLD_UNAVAILABLE,
    PREFERENCE_NAMED_WORKER,
    PREFERENCE_NORMAL,
    PREFERENCE_OWNER_DIRECT,
    PRESERVE_EXECUTOR,
    REROUTE_DELEGATED,
    ExecutorAvailability,
    TaskSnapshot,
    apply_qc_failure_to_snapshot,
    build_cas_payload,
    commit_continuation,
    decide_continuation,
    to_bridge_dict,
)

_COMMIT_PY = (_REPO_ROOT / "shared-utils" / "decision_engine"
              / "commit" / "commit.py")
_spec = importlib.util.spec_from_file_location("d23_commit_live", _COMMIT_PY)
cas = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cas)


def trusted_record(**over):
    base = dict(
        mode='owner_direct',
        requested_executor='current_assistant',
        actual_executor='current_assistant',
        source_message_id='msg-1',
        evidence_span='span:42:7',
        authenticated_requester='owner',
        requester_authenticated=True,
        authorization_source='trusted_context',
        company='acme',
        policy_revision=3,
        config_revision='cfg-9',
    )
    base.update(over)
    return ExecutionPolicyRecord(**base)


def snap(**over):
    base = dict(
        task_id='t-1',
        status='backlog',
        assignment_version=7,
        input_hash='h1',
        policy_revision=3,
        config_revision='cfg-9',
        company_id='acme',
        workspace_id='ws-1',
        assigned_agent_id='agent-ceo',
        execution_state='none',
        qc_failures=1,
        qc_cap=5,
        killed=False,
        archived=False,
    )
    base.update(over)
    return TaskSnapshot(**base)


AVAIL = ExecutorAvailability(True, 'ok')
GONE = ExecutorAvailability(False, 'executor_offline')


class PreserveTests(unittest.TestCase):
    def test_owner_direct_qc_failure_keeps_executor(self):
        d = decide_continuation(
            trusted_record(), snap(), AVAIL, True, PREFERENCE_OWNER_DIRECT)
        self.assertEqual(d.action, PRESERVE_EXECUTOR)
        self.assertEqual(d.executor, 'current_assistant')
        self.assertEqual(d.reason, 'owner_direct_preserved')
        self.assertEqual(d.task_id, 't-1')

    def test_qc_failure_retry_still_preserves_until_cap(self):
        s2 = apply_qc_failure_to_snapshot(snap(qc_failures=3))
        self.assertEqual(s2.qc_failures, 4)
        self.assertEqual(s2.task_id, 't-1')  # task ID retained
        d = decide_continuation(
            trusted_record(), s2, AVAIL, True, PREFERENCE_OWNER_DIRECT)
        self.assertEqual(d.action, PRESERVE_EXECUTOR)

    def test_named_worker_preserved(self):
        rec = trusted_record(actual_executor='jordan',
                             requested_executor='jordan')
        d = decide_continuation(rec, snap(assigned_agent_id='agent-jordan'),
                                AVAIL, True, PREFERENCE_NAMED_WORKER,
                                requested_executor='jordan')
        self.assertEqual((d.action, d.executor),
                         (PRESERVE_EXECUTOR, 'jordan'))

    def test_bridge_dict_json_safe(self):
        d = decide_continuation(
            trusted_record(), snap(), AVAIL, True, PREFERENCE_OWNER_DIRECT)
        b = to_bridge_dict(d)
        import json
        self.assertEqual(json.loads(json.dumps(b))['action'],
                         PRESERVE_EXECUTOR)


class HoldTests(unittest.TestCase):
    def test_unavailable_executor_holds_never_delegates(self):
        d = decide_continuation(
            trusted_record(), snap(), GONE, True, PREFERENCE_OWNER_DIRECT)
        self.assertEqual(d.action, HOLD_UNAVAILABLE)
        self.assertIsNone(d.executor)
        self.assertEqual(d.reason, 'executor_unavailable')

    def test_killed_holds(self):
        d = decide_continuation(
            trusted_record(), snap(killed=True), AVAIL, True,
            PREFERENCE_OWNER_DIRECT)
        self.assertEqual((d.action, d.reason),
                         (HOLD_UNAVAILABLE, 'task_killed'))

    def test_archived_holds(self):
        d = decide_continuation(
            trusted_record(), snap(archived=True), AVAIL, True,
            PREFERENCE_OWNER_DIRECT)
        self.assertEqual((d.action, d.reason),
                         (HOLD_UNAVAILABLE, 'task_archived'))

    def test_active_and_unknown_execution_hold_never_steal(self):
        for state in EXECUTION_ACTIVE:
            d = decide_continuation(
                trusted_record(), snap(execution_state=state), AVAIL, True,
                PREFERENCE_OWNER_DIRECT)
            self.assertEqual(d.action, HOLD_UNAVAILABLE, state)
            self.assertEqual(d.reason, 'execution_active', state)

    def test_terminal_execution_preserves(self):
        for state in ('succeeded', 'failed'):
            d = decide_continuation(
                trusted_record(), snap(execution_state=state), AVAIL, True,
                PREFERENCE_OWNER_DIRECT)
            self.assertEqual(d.action, PRESERVE_EXECUTOR, state)

    def test_policy_drift_holds(self):
        d = decide_continuation(
            trusted_record(policy_revision=4), snap(policy_revision=3),
            AVAIL, True, PREFERENCE_OWNER_DIRECT)
        self.assertEqual((d.action, d.reason),
                         (HOLD_UNAVAILABLE, 'policy_changed'))

    def test_qc_cap_holds(self):
        d = decide_continuation(
            trusted_record(), snap(qc_failures=5, qc_cap=5), AVAIL, True,
            PREFERENCE_OWNER_DIRECT)
        self.assertEqual((d.action, d.reason),
                         (HOLD_UNAVAILABLE, 'qc_cap_exhausted'))


class RerouteTests(unittest.TestCase):
    def test_normal_delegation_reroutes(self):
        d = decide_continuation(
            trusted_record(), snap(), AVAIL, True, PREFERENCE_NORMAL)
        self.assertEqual((d.action, d.reason),
                         (REROUTE_DELEGATED, 'normal_delegation'))

    def test_untrusted_context_reroutes(self):
        d = decide_continuation(
            trusted_record(), snap(), AVAIL, False, PREFERENCE_OWNER_DIRECT)
        self.assertEqual(d.action, REROUTE_DELEGATED)

    def test_user_json_record_never_authorizes(self):
        rec = trusted_record(authorization_source='user_supplied_json')
        self.assertEqual(ep.validate_record(rec)[0], False)
        d = decide_continuation(rec, snap(), AVAIL, True,
                                PREFERENCE_OWNER_DIRECT)
        self.assertEqual(d.action, REROUTE_DELEGATED)

    def test_magic_marker_record_never_authorizes(self):
        rec = trusted_record(authorization_source='magic_marker')
        d = decide_continuation(rec, snap(), AVAIL, True,
                                PREFERENCE_OWNER_DIRECT)
        self.assertEqual(d.action, REROUTE_DELEGATED)

    def test_bare_owner_direct_boolean_never_authorizes(self):
        # No validated D11 record (None) + a bare preference string must not
        # preserve: untrusted text is intent evidence, never authorization.
        d = decide_continuation(None, snap(), AVAIL, True,
                                PREFERENCE_OWNER_DIRECT)
        self.assertEqual(d.action, REROUTE_DELEGATED)

    def test_named_worker_mismatch_reroutes(self):
        rec = trusted_record(actual_executor='jordan',
                             requested_executor='jordan')
        d = decide_continuation(rec, snap(), AVAIL, True,
                                PREFERENCE_NAMED_WORKER,
                                requested_executor='casey')
        self.assertEqual((d.action, d.reason),
                         (REROUTE_DELEGATED, 'executor_mismatch'))

    def test_reroute_has_no_cas_payload(self):
        d = decide_continuation(
            trusted_record(), snap(), AVAIL, True, PREFERENCE_NORMAL)
        with self.assertRaises(ValueError):
            build_cas_payload(d, snap())


class CasCommitTests(unittest.TestCase):
    def test_preserve_commits_via_imported_d23(self):
        store = cas.fresh_state(input_hash='h1')
        d = decide_continuation(
            trusted_record(), snap(), AVAIL, True, PREFERENCE_OWNER_DIRECT)
        rev = commit_continuation(store, 0, d, snap(), cas)
        self.assertEqual(rev, 1)
        self.assertEqual(store['decision']['action'], PRESERVE_EXECUTOR)
        self.assertEqual(store['mirrors']['executor'], 'current_assistant')

    def test_stale_revision_loses_writes_nothing(self):
        store = cas.fresh_state(input_hash='h1')
        d = decide_continuation(
            trusted_record(), snap(), AVAIL, True, PREFERENCE_OWNER_DIRECT)
        commit_continuation(store, 0, d, snap(), cas)
        with self.assertRaises(cas.ObsoleteRevisionError):
            commit_continuation(store, 0, d, snap(), cas)
        self.assertEqual(store['decision_revision'], 1)

    def test_stale_input_hash_fails_cleanly(self):
        store = cas.fresh_state(input_hash='h-current')
        d = decide_continuation(
            trusted_record(), snap(), AVAIL, True, PREFERENCE_OWNER_DIRECT)
        with self.assertRaises(cas.ObsoleteInputError):
            commit_continuation(store, 0, d, snap(), cas,
                                input_hash='h-old')
        self.assertEqual(store['decision_revision'], 0)

    def test_fence_token_expiry_blocks_commit(self):
        import time
        t = [1000.0]
        store = cas.fresh_state(input_hash='h1', mode_revision=1,
                                policy_revision=2, root_budget_s=10,
                                clock=lambda: t[0])
        token = cas.issue_fence_token(store)
        t[0] += 11
        d = decide_continuation(
            trusted_record(), snap(), AVAIL, True, PREFERENCE_OWNER_DIRECT)
        with self.assertRaises(cas.FencedError):
            commit_continuation(store, 0, d, snap(), cas,
                                fence_token=token)
        self.assertEqual(store['decision_revision'], 0)


class D11LiveTests(unittest.TestCase):
    def test_consumes_d11_fields_live(self):
        names = [f.name for f in
                 __import__('dataclasses').fields(ExecutionPolicyRecord)]
        self.assertIn('policy_revision', names)
        self.assertIn('authorization_source', names)
        self.assertEqual(ep.validate_record(trusted_record()), (True, 'ok'))


if __name__ == '__main__':
    unittest.main()
