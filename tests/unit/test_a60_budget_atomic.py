#!/usr/bin/env python3
"""A60 money-safety regression (JEV spec 1.1, ss 3.8/3.9).

Criterion A60: "Existing standing approval authorizes matching operations
automatically with no per-task nagging. Concurrent calls reserve budget
atomically; failure, cancellation, and uncertain usage cannot free money
prematurely or overdraw it through fallback."

Four defects, one test each (all offline, fake transports only):
  (a) a failing/refusing reserve fences the send (no dispatch without a
      successful reservation);
  (b) two concurrent standing-authorized calls have exactly one winner
      through the real SqliteBudgetStore (platform conditional write,
      not check-then-act);
  (c) the atomic budget store exists and is atomic under real contention;
  (d) reconcile errors are surfaced (gate_errors/accounting_uncertain),
      and uncertain usage frees nothing.

Offline: fake transports, fake clock, temp SQLite file only; removed in
tearDown. No network, no environment reads, no real spend.

Run: python3 -m pytest tests/unit/test_a60_budget_atomic.py -q
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_DE = _REPO_ROOT / "shared-utils" / "decision_engine"

_spec = importlib.util.spec_from_file_location(
    "a60_ladder_under_test", _DE / "ladder" / "ladder.py")
ladder = importlib.util.module_from_spec(_spec)
sys.modules["a60_ladder_under_test"] = ladder
_spec.loader.exec_module(ladder)

_QS = [{"id": "q1", "type": "select"}]


def _creds(direct=True, openrouter=True):
    return {"direct": SimpleNamespace(configured=bool(direct)),
            "openrouter": SimpleNamespace(configured=bool(openrouter))}


def _allow(provider, purpose="decide"):
    return {"spend_ok": True, "transmit_ok": True, "reason": "standing"}


def _make(reserve_fn=None, policy=_allow, reconcile_fn=None, direct=None):
    sends = []

    def _resolve(c, s, ctx):
        return _creds()

    def _direct(*, body, api_key, timeout_ms, http_post=None):
        sends.append(1)
        if direct is not None:
            return direct()
        return {"outcome": "ok", "attempts": 1, "estimated_cost": 0.0,
                "actual_cost": 0.0, "payload": {"judgments": []}}

    def _router(**kw):
        return {"outcome": "transport_error", "attempts": 1,
                "estimated_cost": 0.0, "actual_cost": 0.0, "detail": "n/a"}

    kw = dict(resolve_credentials=_resolve, direct_call=_direct,
              openrouter_call=_router, policy_fn=policy)
    if reserve_fn is not None:
        kw["reserve_fn"] = reserve_fn
    if reconcile_fn is not None:
        kw["reconcile_fn"] = reconcile_fn
    return ladder.DirectFirstLadder(**kw), sends


class ReserveFailureFencesSend(unittest.TestCase):
    """(a) no send without a successful reservation."""

    def test_reserve_raising_fences_send(self):
        def raising(provider, estimate):
            raise RuntimeError("budget store down")

        lad, sends = _make(reserve_fn=raising)
        v = lad.run(company_id="acme", state={}, questions=_QS, keys={})
        self.assertEqual(sends, [])
        self.assertEqual(v["stages"][0]["skip_reason"],
                         "technical_unavailable")
        self.assertTrue(any(e["kind"] == "reserve_error"
                            for e in v.get("gate_errors", [])))

    def test_reserve_refusal_fences_send(self):
        def refuses(provider, estimate):
            return {"reservation": None, "estimated": estimate,
                    "error": "insufficient_remaining_budget"}

        lad, sends = _make(reserve_fn=refuses)
        v = lad.run(company_id="acme", state={}, questions=_QS, keys={})
        self.assertEqual(sends, [])
        self.assertEqual(v["stages"][0]["skip_reason"], "budget_exhausted")

    def test_granted_reservation_still_sends_control(self):
        def grants(provider, estimate):
            return {"reservation": {"id": "res-1"}, "estimated": estimate}

        lad, sends = _make(reserve_fn=grants)
        v = lad.run(company_id="acme", state={}, questions=_QS, keys={})
        self.assertEqual(len(sends), 1)
        self.assertEqual(v["decision_source"], "typesafe_direct")

    def test_default_noop_reserve_still_sends(self):
        # The shipped default reserve is a no-op; it must keep sending or
        # every policy-only caller breaks.
        lad, sends = _make()
        v = lad.run(company_id="acme", state={}, questions=_QS, keys={})
        self.assertEqual(len(sends), 1)
        self.assertEqual(v["decision_source"], "typesafe_direct")


class AtomicStoreConcurrency(unittest.TestCase):
    """(b)+(c) real store, real contention, exactly one winner."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="a60-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_concurrent_pair_exactly_one_winner(self):
        store = ladder.SqliteBudgetStore(self.tmp / "b.sqlite",
                                         {"acme": 1.0})
        barrier = threading.Barrier(2)
        sends = []
        lock = threading.Lock()
        results = {}

        def policy(provider, purpose="decide"):
            barrier.wait(timeout=10)
            return _allow(provider, purpose)

        def direct():
            with lock:
                sends.append(1)
            return {"outcome": "ok", "attempts": 1, "estimated_cost": 0.0,
                    "actual_cost": 0.0, "payload": {"judgments": []}}

        def worker(i):
            lad, _ = _make(reserve_fn=store.reserve_fn("acme"),
                           policy=policy,
                           reconcile_fn=store.reconcile)
            lad._direct = lambda **kw: direct()
            results[i] = lad.run(company_id="acme", state={}, questions=_QS,
                                 keys={})

        threads = [threading.Thread(target=worker, args=(i,))
                   for i in (0, 1)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)
        self.assertEqual(len(sends), 1, "exactly one winner must send")
        sources = sorted(r["decision_source"] for r in results.values())
        self.assertEqual(sources, ["no_jev", "typesafe_direct"])
        self.assertGreaterEqual(store.remaining("acme"), 0.0)

    def test_conditional_write_refuses_overdraw(self):
        store = ladder.SqliteBudgetStore(self.tmp / "b2.sqlite",
                                         {"acme": 1.0})
        first = store.reserve("acme", "typesafe_direct", 1.0)
        self.assertTrue(first.get("reservation"))
        second = store.reserve("acme", "typesafe_direct", 1.0)
        self.assertIsNone(second.get("reservation"))
        self.assertEqual(second.get("error"), "insufficient_remaining_budget")
        self.assertEqual(store.remaining("acme"), 0.0)

    def test_uncertain_usage_frees_nothing(self):
        store = ladder.SqliteBudgetStore(self.tmp / "b3.sqlite",
                                         {"acme": 1.0})
        held = store.reserve("acme", "typesafe_direct", 1.0)
        out = store.reconcile("typesafe_direct", held, None)
        self.assertTrue(out["ok"])
        self.assertFalse(out["settled"])
        self.assertEqual(store.remaining("acme"), 0.0)   # nothing freed
        self.assertEqual(store.reservation(
            held["reservation"]["id"])["state"], "uncertain")

    def test_measured_underspend_refunds_only_difference(self):
        store = ladder.SqliteBudgetStore(self.tmp / "b4.sqlite",
                                         {"acme": 1.0})
        held = store.reserve("acme", "typesafe_direct", 1.0)
        out = store.reconcile("typesafe_direct", held, 0.25)
        self.assertEqual(out["released"], 0.75)
        self.assertAlmostEqual(store.remaining("acme"), 0.75)

    def test_store_path_is_caller_supplied_absolute(self):
        with self.assertRaises(ValueError):
            ladder.SqliteBudgetStore(Path("relative.sqlite"), {"a": 1.0})


class ReconcileErrorsSurfaced(unittest.TestCase):
    """(d) accounting failures are visible and money stays held."""

    def test_reconcile_raising_is_surfaced(self):
        def bad(provider, reservation, actual):
            raise RuntimeError("accounting write failed")

        def grants(provider, estimate):
            return {"reservation": {"id": "res-1"}, "estimated": estimate}

        lad, sends = _make(reserve_fn=grants, reconcile_fn=bad)
        v = lad.run(company_id="acme", state={}, questions=_QS, keys={})
        self.assertEqual(len(sends), 1)          # send happened, money held
        kinds = [e["kind"] for e in v.get("gate_errors", [])]
        self.assertIn("reconcile_error", kinds)
        self.assertTrue(v.get("accounting_uncertain"))

    def test_reconcile_error_dict_is_surfaced(self):
        def refusing(provider, reservation, actual):
            return {"ok": False, "error": "reservation_not_held"}

        def grants(provider, estimate):
            return {"reservation": {"id": "res-1"}, "estimated": estimate}

        lad, _ = _make(reserve_fn=grants, reconcile_fn=refusing)
        v = lad.run(company_id="acme", state={}, questions=_QS, keys={})
        self.assertTrue(any(e["detail"] == "reservation_not_held"
                            for e in v.get("gate_errors", [])))

    def test_clean_run_has_no_gate_errors(self):
        lad, _ = _make()
        v = lad.run(company_id="acme", state={}, questions=_QS, keys={})
        self.assertNotIn("gate_errors", v)


if __name__ == "__main__":
    unittest.main(verbosity=2)
