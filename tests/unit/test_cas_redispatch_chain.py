#!/usr/bin/env python3
"""JEV A35/A36: CAS re-dispatch + late-gate integration (real SQLite, stdlib).

A35: unchanged re-dispatch reuses the committed selection; a changed scope
recommits through the EXISTING D23 recommit_scope with reason + evidence, and
the revision chain records the new revision. A raced late result fails with
the typed D23 LateResultError and never overwrites the newer head.

A36: every named late path (selector, backfill, producer_report,
audience_rescore) gates through the existing check_late_result against real
persistence; the audience-update change detector fires recompute only when
the audience/voice/SOP triple moves (spec 8.12).

Run: python3 -m pytest tests/unit/test_cas_redispatch_chain.py -q
"""

import importlib.util
import json
import sqlite3
import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
_COMMIT = _REPO / "shared-utils" / "decision_engine" / "commit"
sys.path.insert(0, str(_COMMIT))

import dispatch


def _load_commit():
    key = "jev_d23_commit:" + str(_COMMIT / "commit.py")
    cached = sys.modules.get(key)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(
        key, str(_COMMIT / "commit.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


_COMMIT_MOD = _load_commit()

_SCOPE = {
    "title": "T1", "description": "D1", "audience": "A1", "voice": "V1",
    "sop": "S1", "catalog": "C1", "policy": "P1", "model": "M1",
    "owner": "O1", "persona": "per1",
}


def _compute(base, scope):
    sel = dict(scope or {})
    return ({"decisionId": "sel", "action": "select", "scope": sel},
            {"board": "sel"})


class RedispatchChainTests(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row

    def tearDown(self):
        self.con.close()

    def test_unchanged_redispatch_reuses_committed_selection(self):
        first = dispatch.redispatch(self.con, "task-1", dict(_SCOPE),
                                    _compute, "first-dispatch", {"by": "t"})
        self.assertEqual(first[0], "committed")
        self.assertEqual(first[1], 1)
        again = dispatch.redispatch(self.con, "task-1", dict(_SCOPE),
                                    _compute, "retry", {})
        self.assertEqual(again[0], "reuse")
        self.assertEqual(again[1], 1)
        self.assertEqual(again[2]["decisionId"], first[2]["decision"]["decisionId"])
        self.assertEqual(len(dispatch.revision_history(self.con, "task-1")), 1)

    def test_scope_change_recommits_with_reason_evidence_chain(self):
        dispatch.redispatch(self.con, "task-2", dict(_SCOPE),
                            _compute, "first-dispatch", {"by": "t1"})
        changed = dict(_SCOPE, title="T2")
        out = dispatch.redispatch(self.con, "task-2", changed, _compute,
                                  "scope-changed", {"by": "t2"})
        self.assertEqual(out[0], "recommitted")
        self.assertEqual(out[1], 2)
        hist = dispatch.revision_history(self.con, "task-2")
        self.assertEqual([r["revision"] for r in hist], [1, 2])
        self.assertEqual(hist[0]["reason"], "first-dispatch")
        self.assertEqual(hist[1]["reason"], "scope-changed")
        evidence = json.loads(hist[1]["evidence"])
        self.assertEqual(evidence["changed_fields"], ["title"])
        self.assertEqual(evidence["prior_revision"], 1)
        self.assertIn("T2", hist[1]["envelope"])

    def test_late_result_does_not_overwrite_newer_head(self):
        dispatch.redispatch(self.con, "task-3", dict(_SCOPE),
                            _compute, "first", {})
        dispatch.redispatch(self.con, "task-3", dict(_SCOPE, title="T2"),
                            _compute, "scope-changed", {})
        _commit, store = dispatch.load_cas_store(
            self.con, "task-3", dispatch.scope_hash(dict(_SCOPE, title="T2")))
        self.assertTrue(dispatch.guard_late_result(store, "selector", 2))
        with self.assertRaises(_COMMIT_MOD.LateResultError):
            dispatch.guard_late_result(store, "selector", 1)
        with self.assertRaises(ValueError):
            dispatch.guard_late_result(store, "bogus-kind", 2)
        hist = dispatch.revision_history(self.con, "task-3")
        self.assertEqual([r["revision"] for r in hist], [1, 2])

    def test_all_four_late_kinds_gate_against_real_persistence(self):
        dispatch.redispatch(self.con, "task-4", dict(_SCOPE),
                            _compute, "first", {})
        dispatch.redispatch(self.con, "task-4", dict(_SCOPE, voice="V2"),
                            _compute, "scope-changed", {})
        _commit, store = dispatch.load_cas_store(
            self.con, "task-4", dispatch.scope_hash(dict(_SCOPE, voice="V2")))
        for kind in ("selector", "backfill", "producer_report",
                     "audience_rescore"):
            self.assertTrue(dispatch.guard_late_result(store, kind, 2),
                            kind)
            with self.assertRaises(_COMMIT_MOD.LateResultError, msg=kind):
                dispatch.guard_late_result(store, kind, 1)

    def test_audience_update_detector_fires_only_on_triple_change(self):
        old = {"audience": "A1", "voice": "V1", "sop": "S1"}
        self.assertEqual(dispatch.audience_scope_changed(dict(old), dict(old)), [])
        self.assertEqual(
            dispatch.audience_scope_changed(old, dict(old, audience="A2")),
            ["audience"])
        self.assertEqual(
            dispatch.audience_scope_changed(old, dict(old, voice="V2", sop="S2")),
            ["voice", "sop"])
        # 8.12 full-scope diff catches non-audience dimensions too.
        full_old = dict(_SCOPE)
        self.assertEqual(dispatch.detect_scope_change(full_old, dict(full_old)), [])
        self.assertEqual(
            dispatch.detect_scope_change(full_old, dict(full_old, model="M2")),
            ["model"])


if __name__ == "__main__":
    unittest.main()
