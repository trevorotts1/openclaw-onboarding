#!/usr/bin/env python3
"""D12 assignment-race regressions (JEV spec 1.1, ss 5.5/10.3; A16/A64 ONB half).

Two races the ONB policy/CAS seam must decide correctly:

* concurrent auto-route vs manual assignment — the awaited route result must
  not overwrite an assignment that landed while routing ran: the stale commit
  loses typed (ObsoleteRevisionError), writes no decision, no board mirror
  (the assignment-success-notice seam) and dispatches nothing;
* late provider result vs newer decision — a provider result carrying an
  obsolete revision is refused typed (LateResultError; "producer_report" is
  the provider-output kind of the D23 closed set) and never moves the newer
  decision head.

Uses ONLY the real shared-utils modules: continuation decision (D12) plus the
D23 single-writer CAS loaded by file path (never restated, registered in
sys.modules so every loader shares one exception identity).

Run: python3 -m pytest tests/unit/test_d12_assignment_races.py -q
"""
import importlib.util
import json
import sys
import threading
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
sys.path.insert(0, str(_REPO_ROOT / 'shared-utils'))
sys.path.insert(0, str(_REPO_ROOT / 'shared-utils/execution_policy'))
sys.path.insert(0, str(_REPO_ROOT / 'shared-utils/decision_engine'))

from execution_policy import ExecutionPolicyRecord
from continuation import (
    PREFERENCE_OWNER_DIRECT,
    PRESERVE_EXECUTOR,
    ExecutorAvailability,
    TaskSnapshot,
    commit_continuation,
    decide_continuation,
)

_COMMIT_PY = (_REPO_ROOT / "shared-utils" / "decision_engine"
              / "commit" / "commit.py")

def _load_cas():
    key = "jev_d23_commit:" + str(_COMMIT_PY)
    cached = sys.modules.get(key)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(key, str(_COMMIT_PY))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod

cas = _load_cas()

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

def route_decision():
    """Owner-direct QC-failure reroute decision: preserve current assistant."""
    return decide_continuation(
        trusted_record(), snap(), AVAIL, True, PREFERENCE_OWNER_DIRECT)

def manual_decision_mirrors(tag='manual-1', executor='agent-manual'):
    return ({"decisionId": tag, "inputHash": "h1",
             "action": "manual_assignment", "executor": executor},
            {"task": "t-1", "executor": executor,
             "reason": "owner_manual_assignment",
             "action": "manual_assignment"})

def select_decision(tag):
    return ({"decisionId": tag, "inputHash": "h1", "action": "select"},
            {"task": "t-1", "executor": "agent-" + tag})

class AutoRouteVsManualAssignment(unittest.TestCase):
    def test_route_result_after_manual_assignment_loses_typed(self):
        store = cas.fresh_state(input_hash="h1")
        d = route_decision()
        self.assertEqual(d.action, PRESERVE_EXECUTOR)
        # Owner manually assigns while the route result is still awaited.
        m_decision, m_mirrors = manual_decision_mirrors()
        cas.cas_commit(store, 0, m_decision, m_mirrors)
        # The awaited route result now arrives: stale, loses typed.
        with self.assertRaises(cas.ObsoleteRevisionError) as ctx:
            commit_continuation(store, 0, d, snap(), cas)
        self.assertEqual((ctx.exception.expected, ctx.exception.actual), (0, 1))
        # No write, no assignment-success notice (mirror), no dispatch.
        self.assertEqual(store["decision"], m_decision)
        self.assertEqual(store["mirrors"], m_mirrors)
        self.assertEqual(store["decision_revision"], 1)
        self.assertEqual(store["dispatched"], [])
        blob = json.dumps([store["decision"], store["mirrors"]])
        self.assertNotIn("current_assistant", blob)

    def test_concurrent_manual_and_route_exactly_one_winner(self):
        store = cas.fresh_state(input_hash="h1")
        d = route_decision()
        gate = threading.Barrier(2)
        result = {}

        def manual():
            try:
                gate.wait(timeout=10)
                m_decision, m_mirrors = manual_decision_mirrors()
                result["manual_rev"] = cas.cas_commit(
                    store, 0, m_decision, m_mirrors)
            except cas.ObsoleteRevisionError as exc:
                result["manual_lost"] = exc

        def route():
            try:
                gate.wait(timeout=10)
                result["route_rev"] = commit_continuation(
                    store, 0, d, snap(), cas)
            except cas.ObsoleteRevisionError as exc:
                result["route_lost"] = exc

        threads = [threading.Thread(target=manual),
                   threading.Thread(target=route)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        wins = [k for k in ("manual_rev", "route_rev") if k in result]
        self.assertEqual(len(wins), 1)
        self.assertEqual(store["decision_revision"], 1)
        if "manual_rev" in result:
            self.assertIn("route_lost", result)
            self.assertEqual(store["mirrors"]["executor"], "agent-manual")
            self.assertEqual(store["decision"]["decisionId"], "manual-1")
        else:
            self.assertIn("manual_lost", result)
            self.assertEqual(store["mirrors"]["executor"], "current_assistant")
            self.assertEqual(store["decision"]["action"], PRESERVE_EXECUTOR)
        # No torn write: revision never exceeds the single winner.
        self.assertEqual(store["dispatched"], [])

class LateProviderResultVsNewerDecision(unittest.TestCase):
    def _store_head_1(self):
        store = cas.fresh_state(input_hash="h1")
        cas.cas_commit(store, 0, *select_decision("route-v1"))
        return store

    def test_result_for_old_revision_after_newer_decision_loses_typed(self):
        store = self._store_head_1()
        # Newer decision lands (rev 2) while the provider result is in flight.
        cas.cas_commit(store, 1, *select_decision("route-v2"))
        head = dict(store["decision"])
        with self.assertRaises(cas.LateResultError) as ctx:
            cas.check_late_result(store, "producer_report", 1)
        self.assertEqual((ctx.exception.kind, ctx.exception.result_revision,
                          ctx.exception.head_revision),
                         ("producer_report", 1, 2))
        # Late result never moves the newer head.
        self.assertEqual(store["decision"], head)
        self.assertEqual(store["decision_revision"], 2)
        self.assertEqual(store["decision"]["decisionId"], "route-v2")

    def test_result_gate_raced_by_newer_decision(self):
        store = self._store_head_1()
        started = threading.Event()
        newer_landed = threading.Event()
        outcome = {}

        def provider_result():
            started.set()
            # Result tagged revision 1; the newer decision must land first.
            self.assertTrue(newer_landed.wait(timeout=10))
            try:
                cas.check_late_result(store, "producer_report", 1)
                outcome["accepted"] = True
            except cas.LateResultError as exc:
                outcome["late"] = exc

        t = threading.Thread(target=provider_result)
        t.start()
        self.assertTrue(started.wait(timeout=10))
        cas.cas_commit(store, 1, *select_decision("route-v2"))
        newer_landed.set()
        t.join(timeout=30)
        self.assertIn("late", outcome)
        self.assertNotIn("accepted", outcome)
        self.assertEqual(store["decision_revision"], 2)
        self.assertEqual(store["decision"]["decisionId"], "route-v2")

    def test_current_result_passes_without_moving_head(self):
        store = self._store_head_1()
        self.assertTrue(cas.check_late_result(store, "producer_report", 1))
        self.assertEqual(store["decision_revision"], 1)
        self.assertEqual(store["decision"]["decisionId"], "route-v1")

if __name__ == "__main__":
    unittest.main()
