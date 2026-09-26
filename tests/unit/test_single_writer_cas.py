#!/usr/bin/env python3
"""D23 single-writer CAS commit tests (JEV spec 1.1, ss 10.3/10.4/5.5).

Proves, against the REAL shared-utils/decision_engine/commit/commit.py
(no reimplemented logic):
  * single CAS: N threads racing one expected_revision -> exactly 1 winner,
    every loser gets ObsoleteRevisionError, mirrors match the winner only;
  * stale input hash fails cleanly (ObsoleteInputError) even at head;
  * fencing: root expiry + mode/policy revision change invalidate
    uncommitted recommendations (FencedError); committed decisions untouched;
  * late selector/backfill/producer-report/audience-rescore vs obsolete
    revision -> typed LateResultError (all four kinds named);
  * pending selection: preparing -> committed|held, terminal enforced, no
    new board columns; wait ticks never consume retry budget; no parallel
    self-heal selector while a record exists (counters asserted);
  * scope path: pre-dispatch recompute+commit+dispatch matches post-change
    scope; post-start running snapshot immutable, amendment separate head;
  * commit module has no network/SQLite imports (caller-supplied store).

Run: python3 -m pytest tests/unit/test_single_writer_cas.py -q
"""

from __future__ import annotations

import copy
import importlib.util
import threading
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_COMMIT_PY = (_REPO_ROOT / "shared-utils" / "decision_engine"
              / "commit" / "commit.py")

_spec = importlib.util.spec_from_file_location("d23_commit", _COMMIT_PY)
cas = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cas)


def _decision(tag, input_hash="h1", extra=None):
    d = {"decisionId": "d-%s" % tag, "inputHash": input_hash,
         "scope": "scope-%s" % tag}
    if extra:
        d.update(extra)
    return d


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, s):
        self.t += s


class SingleWriterCas(unittest.TestCase):
    def test_race_exactly_one_winner(self):
        store = cas.fresh_state(input_hash="h1")
        gate = threading.Barrier(8)
        wins, losses, won_tag = [], [], []

        def racer(i):
            try:
                gate.wait(timeout=10)
                rev = cas.cas_commit(
                    store, 0, _decision(i), {"board": "m-%d" % i})
                wins.append(rev)
                won_tag.append(i)
            except cas.ObsoleteRevisionError:
                losses.append(i)

        threads = [threading.Thread(target=racer, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        self.assertEqual(len(wins), 1)
        self.assertEqual(len(losses), 7)
        self.assertEqual(store["decision_revision"], 1)
        # No torn mirrors: stored mirrors belong to the winner only.
        self.assertEqual(store["mirrors"], {"board": "m-%d" % won_tag[0]})
        self.assertEqual(store["decision"]["decisionId"],
                         "d-%d" % won_tag[0])

    def test_stale_input_hash_fails_at_head(self):
        store = cas.fresh_state(input_hash="h-current")
        with self.assertRaises(cas.ObsoleteInputError) as ctx:
            cas.cas_commit(store, 0, _decision("stale", input_hash="h-old"),
                           {"board": "m"})
        self.assertEqual(ctx.exception.current_hash, "h-current")
        self.assertEqual(store["decision_revision"], 0)
        self.assertIsNone(store["decision"])
        self.assertEqual(store["mirrors"], {})

    def test_bad_shapes_rejected(self):
        store = cas.fresh_state(input_hash="h1")
        with self.assertRaises(ValueError):
            cas.cas_commit(store, 0, [("not", "a", "dict")], {})
        with self.assertRaises(ValueError):
            cas.cas_commit(store, 0, _decision("x"), [("not", "dict")])


class Fencing(unittest.TestCase):
    def test_root_expiry_fences_uncommitted(self):
        clk = FakeClock()
        store = cas.fresh_state(input_hash="h1", mode_revision=1,
                                policy_revision=2, root_budget_s=10, clock=clk)
        token = cas.issue_fence_token(store)
        self.assertTrue(cas.check_fence(store, token))
        clk.advance(11)
        with self.assertRaises(cas.FencedError) as ctx:
            cas.check_fence(store, token)
        self.assertEqual(ctx.exception.reason, "root_expired")

    def test_mode_flip_fences_inflight_committed_untouched(self):
        store = cas.fresh_state(input_hash="h1", mode_revision=1,
                                policy_revision=2)
        rev = cas.cas_commit(store, 0, _decision("base"), {"board": "m0"})
        committed = copy.deepcopy(store["decision"])
        sel = cas.start_pending(store, "prep-1")
        token = cas.issue_fence_token(store)
        with store["_lock"]:
            store["fence"]["mode_revision"] = 2
        with self.assertRaises(cas.FencedError) as ctx:
            cas.check_fence(store, token)
        self.assertEqual(ctx.exception.reason, "mode_changed")
        # In-flight selection still live; committed decision untouched.
        self.assertEqual(sel.status, "preparing")
        self.assertEqual(store["decision"], committed)
        self.assertEqual(store["decision_revision"], rev)
        self.assertEqual(sel.commit(), "committed")

    def test_policy_flip_fences(self):
        store = cas.fresh_state(input_hash="h1", mode_revision=1,
                                policy_revision=2)
        token = cas.issue_fence_token(store)
        with store["_lock"]:
            store["fence"]["policy_revision"] = 3
        with self.assertRaises(cas.FencedError) as ctx:
            cas.check_fence(store, token)
        self.assertEqual(ctx.exception.reason, "policy_changed")

    def test_no_deadline_never_expires(self):
        store = cas.fresh_state(input_hash="h1")
        token = cas.issue_fence_token(store)
        self.assertTrue(cas.check_fence(store, token))


class LateResults(unittest.TestCase):
    def _head_at_1(self):
        store = cas.fresh_state(input_hash="h1")
        cas.cas_commit(store, 0, _decision("v1"), {"board": "m1"})
        return store

    def test_late_selector_obsolete(self):
        with self.assertRaises(cas.LateResultError) as ctx:
            cas.check_late_result(self._head_at_1(), "selector", 0)
        self.assertEqual((ctx.exception.kind,
                          ctx.exception.result_revision,
                          ctx.exception.head_revision),
                         ("selector", 0, 1))

    def test_late_backfill_obsolete(self):
        with self.assertRaises(cas.LateResultError) as ctx:
            cas.check_late_result(self._head_at_1(), "backfill", 0)
        self.assertEqual(ctx.exception.kind, "backfill")

    def test_late_producer_report_obsolete(self):
        with self.assertRaises(cas.LateResultError) as ctx:
            cas.check_late_result(self._head_at_1(), "producer_report", 0)
        self.assertEqual(ctx.exception.kind, "producer_report")

    def test_late_audience_rescore_obsolete(self):
        with self.assertRaises(cas.LateResultError) as ctx:
            cas.check_late_result(self._head_at_1(), "audience_rescore", 0)
        self.assertEqual(ctx.exception.kind, "audience_rescore")

    def test_current_revision_passes(self):
        self.assertTrue(
            cas.check_late_result(self._head_at_1(), "selector", 1))

    def test_unknown_kind_is_caller_defect(self):
        with self.assertRaises(ValueError):
            cas.check_late_result(self._head_at_1(), "stale_cron", 1)


class PendingSelection(unittest.TestCase):
    def test_commit_path_terminal(self):
        store = cas.fresh_state(input_hash="h1")
        sel = cas.start_pending(store, "prep-1", generation=3)
        self.assertEqual(sel.status, "preparing")
        self.assertFalse(sel.terminal)
        self.assertEqual(sel.commit(), "committed")
        self.assertTrue(sel.terminal)
        with self.assertRaises(cas.BadTransitionError):
            sel.commit()
        with self.assertRaises(cas.BadTransitionError):
            sel.hold()

    def test_hold_path_terminal(self):
        store = cas.fresh_state(input_hash="h1")
        sel = cas.start_pending(store, "prep-2")
        self.assertEqual(sel.hold("no_quorum"), "held")
        self.assertTrue(sel.terminal)
        with self.assertRaises(cas.BadTransitionError):
            sel.commit()

    def test_second_live_selection_refused(self):
        store = cas.fresh_state(input_hash="h1")
        cas.start_pending(store, "prep-1")
        with self.assertRaises(cas.BadTransitionError):
            cas.start_pending(store, "prep-2")

    def test_no_new_board_columns(self):
        self.assertEqual(cas.PendingSelection.STATUSES,
                         ("preparing", "committed", "held"))
        src = _COMMIT_PY.read_text(encoding="utf-8").lower()
        for banned in ("alter table", "add column", "board_column"):
            self.assertNotIn(banned, src)

    def test_wait_ticks_never_consume_retry(self):
        store = cas.fresh_state(input_hash="h1", retry_budget=3)
        cas.start_pending(store, "prep-1")
        for _ in range(5):
            cas.on_wait_tick(store)
        self.assertEqual(store["wait_ticks"], 5)
        self.assertEqual(store["retry"], {"remaining": 3, "consumed": 0})
        with self.assertRaises(cas.BadTransitionError):
            cas.consume_retry(store)
        self.assertEqual(store["retry"], {"remaining": 3, "consumed": 0})

    def test_retry_spends_after_terminal(self):
        store = cas.fresh_state(input_hash="h1", retry_budget=2)
        sel = cas.start_pending(store, "prep-1")
        sel.commit()
        self.assertEqual(cas.consume_retry(store), 1)
        self.assertEqual(store["retry"], {"remaining": 1, "consumed": 1})

    def test_no_parallel_selfheal_while_record_exists(self):
        store = cas.fresh_state(input_hash="h1")
        cas.start_pending(store, "prep-1")
        for _ in range(5):
            cas.on_wait_tick(store)
            out = cas.selfheal_sweep(store, reason="old_wait_expired")
            self.assertFalse(out["spawned"])
        self.assertEqual(store["selfheal_spawns"], 0)

    def test_no_selfheal_after_terminal(self):
        store = cas.fresh_state(input_hash="h1")
        sel = cas.start_pending(store, "prep-1")
        sel.hold("exhausted")
        out = cas.selfheal_sweep(store, reason="sweep")
        self.assertFalse(out["spawned"])
        self.assertEqual(store["selfheal_spawns"], 0)

    def test_sweep_spawns_only_with_no_record(self):
        store = cas.fresh_state(input_hash="h1")
        out = cas.selfheal_sweep(store, reason="orphan")
        self.assertTrue(out["spawned"])
        self.assertEqual(store["selfheal_spawns"], 1)


class ScopePath(unittest.TestCase):
    def test_predispatch_recompute_dispatches_matching_snapshot(self):
        store = cas.fresh_state(input_hash="h1")
        cas.cas_commit(store, 0, _decision("v1"), {"board": "m1"})

        def recompute(base, new_scope):
            self.assertEqual(base["decisionId"], "d-v1")
            d = dict(base, scope=new_scope, decisionId="d-v2")
            return d, {"board": "m2"}

        new_rev, snapshot = cas.recommit_scope(
            store, 1, "scope-changed", recompute)
        self.assertEqual(new_rev, 2)
        self.assertEqual(snapshot["scope"], "scope-changed")
        self.assertEqual(snapshot["decisionId"], "d-v2")
        self.assertEqual(store["dispatched"][-1], snapshot)
        self.assertEqual(store["decision"]["scope"], "scope-changed")

    def test_poststart_snapshot_immutable_amendment_separate_head(self):
        store = cas.fresh_state(input_hash="h1")
        cas.cas_commit(store, 0, _decision("v1"), {"board": "m1"})
        running = cas.start_execution(store)
        self.assertEqual(store["running_revision"], 1)
        frozen = copy.deepcopy(running)
        # Later owner amendment commits as a new head revision...
        with store["_lock"]:
            store["input_hash"] = "h2"
        new_rev = cas.cas_commit(
            store, 1, _decision("v2-amend", input_hash="h2"), {"board": "m2"})
        self.assertEqual(new_rev, 2)
        # ...but the running worker snapshot never moves.
        self.assertEqual(store["running_snapshot"], frozen)
        self.assertEqual(store["running_revision"], 1)
        self.assertEqual(store["decision"]["decisionId"], "d-v2-amend")

    def test_recompute_refused_after_start(self):
        store = cas.fresh_state(input_hash="h1")
        cas.cas_commit(store, 0, _decision("v1"), {"board": "m1"})
        cas.start_execution(store)
        with self.assertRaises(cas.BadTransitionError):
            cas.recommit_scope(store, 1, "scope-x",
                               lambda base, scope: (base, {}))

    def test_start_without_decision_refused(self):
        store = cas.fresh_state(input_hash="h1")
        with self.assertRaises(cas.BadTransitionError):
            cas.start_execution(store)


class NoNetworkImports(unittest.TestCase):
    def test_commit_module_stdlib_only(self):
        src = _COMMIT_PY.read_text(encoding="utf-8")
        for banned in ("socket", "urllib", "requests", "http.client",
                       "http.server", "sqlite3", "psycopg", "pymysql",
                       "os.environ", "os.getenv"):
            self.assertNotIn(banned, src,
                             "commit.py must not reference %r" % banned)


if __name__ == "__main__":
    unittest.main()
