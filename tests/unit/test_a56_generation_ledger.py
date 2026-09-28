#!/usr/bin/env python3
"""A56 acceptance: deadline reset / no self-retry / linked amendment.

Against the REAL modules by file path (no reimplemented logic):
  * clause 1 — a restart, a failover, and a sweep each leave the SAME
    generation's persisted deadline unchanged (spec 3.5.4);
  * clause 2 — exhausted unchanged work does not self-retry: the persisted
    exhaustion survives a restart, a sweep spawns nothing, and a spent-out
    retry budget still refuses `consume_retry` after a hydrate;
  * clause 3 — a real owner confirmation (D11 ExecutionPolicyRecord from
    trusted context) opens generation N+1 linked via `amended_from`, and
    the prior generation's usage/attempts are byte-identical afterwards.

Instrument control: the probe reads through `load_generation`, and a
perturbed deadline is proven to be reported (a reader that cannot see a
change cannot prove the absence of one).

Run: python3 -m pytest tests/unit/test_a56_generation_ledger.py -q
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent.parent
_COMMIT_DIR = _REPO / "shared-utils" / "decision_engine" / "commit"
sys.path.insert(0, str(_COMMIT_DIR))

import dispatch  # noqa: E402

commit = dispatch._load_commit()
ep = dispatch._load_execution_policy()

SCOPE = {"title": "T1", "audience": "A1", "voice": "V1", "sop": "S1"}
DEADLINE = 1_700_000_100.0


def compute(base, scope):
    return ({"decisionId": "sel", "action": "select", "scope": dict(scope)},
            {"board": "sel"})


def confirmation(**over):
    base = dict(
        requested_executor="current_assistant",
        actual_executor="current_assistant",
        source_message_id="owner-msg-1",
        evidence_span="amend please",
        authenticated_requester="owner",
        requester_authenticated=True,
        authorization_source=ep.TRUSTED_SOURCE,
        company="und056",
        policy_revision=1,
    )
    base.update(over)
    return ep.ExecutionPolicyRecord(**base)


class A56Base(unittest.TestCase):
    def setUp(self):
        self.con = sqlite3.connect(":memory:")
        self.con.row_factory = sqlite3.Row
        dispatch.ensure_revision_table(self.con)

    def tearDown(self):
        self.con.close()

    def seed_generation(self, task="t", generation=0, deadline=DEADLINE,
                        retry_budget=3):
        dispatch.begin_generation(self.con, task, "prep-%d" % generation,
                                  generation, deadline,
                                  retry_budget=retry_budget)
        dispatch.redispatch(self.con, task, dict(SCOPE), compute, "first", {})


class InstrumentControl(A56Base):
    def test_probe_reports_a_perturbed_deadline(self):
        self.seed_generation()
        self.assertEqual(
            dispatch.load_generation(self.con, "t", 0)["deadline_s"], DEADLINE)
        self.con.execute(
            "UPDATE preparation_generations SET deadline_s=? WHERE"
            " task_key=? AND generation=0", (DEADLINE + 1.0, "t"))
        self.con.commit()
        self.assertEqual(
            dispatch.load_generation(self.con, "t", 0)["deadline_s"],
            DEADLINE + 1.0)


class Clause1NoReset(A56Base):
    def test_restart_hydrate_keeps_the_same_deadline(self):
        self.seed_generation()
        dispatch.update_generation(self.con, "t", 0, consumed_ms=100.0)
        self.con.commit()
        _c, store = dispatch.load_cas_store(self.con, "t")
        self.assertEqual(store["fence"]["deadline_s"], DEADLINE)
        self.assertEqual(
            dispatch.load_generation(self.con, "t", 0)["deadline_s"], DEADLINE)

    def test_failover_second_connection_keeps_the_same_deadline(self):
        tmp = Path(tempfile.mkdtemp(prefix="a56-failover-"))
        path = str(tmp / "decision_revisions.db")
        con1 = sqlite3.connect(path)
        con1.row_factory = sqlite3.Row
        try:
            dispatch.ensure_revision_table(con1)
            dispatch.begin_generation(con1, "t", "prep-0", 0, DEADLINE)
            dispatch.redispatch(con1, "t", dict(SCOPE), compute, "first", {})
            con1.commit()
            con2 = sqlite3.connect(path)  # failover: independent handle
            con2.row_factory = sqlite3.Row
            try:
                _c1, s1 = dispatch.load_cas_store(con1, "t")
                _c2, s2 = dispatch.load_cas_store(con2, "t")
                self.assertEqual(s1["fence"]["deadline_s"], DEADLINE)
                self.assertEqual(s2["fence"]["deadline_s"], DEADLINE)
                self.assertEqual(
                    dispatch.load_generation(con2, "t", 0)["deadline_s"],
                    DEADLINE)
            finally:
                con2.close()
        finally:
            con1.close()
            shutil.rmtree(tmp, ignore_errors=True)

    def test_sweep_keeps_the_deadline_and_leaves_the_generation_settled(self):
        self.seed_generation()
        sel = None
        _c, store = dispatch.load_cas_store(self.con, "t")
        sel = store["pending"]
        sel.commit()
        out = commit.selfheal_sweep(store, reason="sweep")
        self.assertFalse(out["spawned"])
        self.assertEqual(
            dispatch.load_generation(self.con, "t", 0)["deadline_s"], DEADLINE)

    def test_rebegin_of_the_same_generation_is_refused(self):
        self.seed_generation()
        with self.assertRaises(ValueError):
            dispatch.begin_generation(self.con, "t", "prep-again", 0, 999.0)
        self.assertEqual(
            dispatch.load_generation(self.con, "t", 0)["deadline_s"], DEADLINE)


class Clause2NoSelfRetry(A56Base):
    def test_exhausted_generation_stays_held_across_hydrate_and_sweep(self):
        self.seed_generation()
        dispatch.exhaust_generation(self.con, "t", 0)
        self.con.commit()
        _c, store = dispatch.load_cas_store(self.con, "t")
        self.assertEqual(store["pending"].status, "held")
        self.assertEqual(store["pending"].reason, "exhausted")
        out = commit.selfheal_sweep(store, reason="post_exhaustion")
        self.assertFalse(out["spawned"])
        self.assertEqual(
            dispatch.load_generation(self.con, "t", 0)["status"], "exhausted")

    def test_spent_retry_budget_survives_hydrate(self):
        self.seed_generation(retry_budget=1)
        _c, store = dispatch.load_cas_store(self.con, "t")
        store["pending"].commit()
        self.assertEqual(commit.consume_retry(store), 0)
        dispatch.sync_usage(store, self.con, "t", 0)
        dispatch.update_generation(self.con, "t", 0, status="committed")
        self.con.commit()
        _c2, store2 = dispatch.load_cas_store(self.con, "t")
        self.assertEqual(store2["retry"], {"remaining": 0, "consumed": 1})
        with self.assertRaises(commit.BadTransitionError) as ctx:
            commit.consume_retry(store2)
        self.assertEqual(ctx.exception.from_state, "retry_exhausted")

    def test_usage_survives_hydrate(self):
        self.seed_generation()
        _c, store = dispatch.load_cas_store(self.con, "t")
        store["pending"].commit()
        commit.consume_retry(store)
        dispatch.sync_usage(store, self.con, "t", 0)
        self.con.commit()
        _c2, store2 = dispatch.load_cas_store(self.con, "t")
        self.assertEqual(store2["retry"], {"remaining": 2, "consumed": 1})


class Clause3LinkedAmendment(A56Base):
    def _amend(self, **over):
        self.seed_generation()
        _c, store = dispatch.load_cas_store(self.con, "t")
        store["pending"].commit()
        commit.consume_retry(store)
        dispatch.sync_usage(store, self.con, "t", 0)
        dispatch.update_generation(self.con, "t", 0, consumed_ms=420.5,
                                   status="exhausted")
        self.con.commit()
        return dispatch.amend_generation(
            self.con, "t", dict(SCOPE, title="T2"), compute,
            confirmation(**over), "owner_amendment", {"by": "owner-msg-1"},
            deadline_s=DEADLINE + 900.0)

    def test_owner_confirmation_links_new_generation(self):
        out = self._amend()
        new_row = dispatch.load_generation(self.con, "t", 1)
        self.assertEqual(out["action"], "recommitted")
        self.assertEqual(new_row["generation"], 1)
        self.assertEqual(new_row["amended_from"], 0)
        self.assertEqual(new_row["confirmed_by"], "owner-msg-1:amend please")
        self.assertEqual(new_row["deadline_s"], DEADLINE + 900.0)

    def test_prior_usage_and_attempts_are_not_erased(self):
        self._amend()
        prior = dispatch.load_generation(self.con, "t", 0)
        self.assertEqual(prior["consumed_ms"], 420.5)
        self.assertEqual(prior["attempts"], 1)
        self.assertEqual(prior["retry_remaining"], 2)
        self.assertEqual(prior["retry_consumed"], 1)
        self.assertEqual(prior["status"], "exhausted")
        self.assertEqual(prior["deadline_s"], DEADLINE)

    def test_unchanged_scope_amendment_still_requires_the_confirmation(self):
        self.seed_generation()
        _c, store = dispatch.load_cas_store(self.con, "t")
        store["pending"].commit()
        self.con.commit()
        with self.assertRaises(dispatch.UnauthorizedAmendmentError):
            dispatch.amend_generation(
                self.con, "t", dict(SCOPE), compute,
                confirmation(authorization_source="user_supplied_json"),
                "no")
        self.assertEqual(
            [g["generation"] for g in
             dispatch.generation_rows(self.con, "t")], [0])

    def test_unauthenticated_confirmation_writes_nothing(self):
        self.seed_generation()
        with self.assertRaises(dispatch.UnauthorizedAmendmentError):
            dispatch.amend_generation(
                self.con, "t", dict(SCOPE, title="T2"), compute,
                confirmation(requester_authenticated=False), "no")
        self.assertEqual(
            [g["generation"] for g in
             dispatch.generation_rows(self.con, "t")], [0])
        self.assertEqual(dispatch.revision_history(self.con, "t")[0]["revision"], 1)

    def test_update_of_missing_generation_is_refused(self):
        with self.assertRaises(ValueError):
            dispatch.update_generation(self.con, "t", 7, consumed_ms=1.0)


class NoLedgerBackwardCompatibility(A56Base):
    def test_hydrate_without_a_ledger_row_keeps_a35_semantics(self):
        _commit, store = dispatch.load_cas_store(self.con, "t",
                                                 input_hash="h")
        self.assertEqual(store["decision_revision"], 0)
        self.assertIsNone(store["decision"])
        self.assertIsNone(store["fence"]["deadline_s"])
        self.assertIsNone(store["pending"])


if __name__ == "__main__":
    unittest.main()
