#!/usr/bin/env python3
"""D07 direct-first ladder tests (JEV spec 1.1, ss 3.1/3.5/3.6/3.8).

Proves, against the REAL ladder (shared-utils/decision_engine/ladder/
ladder.py) orchestrating the REAL D04/D05/D06 modules:
  * 3.1 direct-first: direct present + OpenRouter present -> direct called
    once, OpenRouter zero; direct absent -> OpenRouter used; none -> no-JEV
    fallback with truthful stage provenance;
  * 3.5/3.6 one root deadline: every stage receives remaining budget only;
    exhausted budget short-circuits with skip_reason=root_deadline_expired;
    injected slow calls never extend the root (no reset/extend API);
  * accounting: per-stage attempts + cost accumulation; a provider-level
    retry inside one stage consumes the SAME totals (no nested multiply);
  * circuits: 3 failures open the provider; open skips without calling;
    exactly one half-open probe after cooldown;
  * 3.8 permissions: caller policy checked before EVERY remote call;
    reserve -> recheck -> send -> reconcile ordering asserted via log;
    recheck denial blocks send; not_authorized / data_not_permitted /
    budget_exhausted kept separate from technical errors.

Offline: fake D04/D05/D06 callables + fake clock only. No network, no
disk, no environment reads. Fake key material never appears in verdicts.

Run: python3 -m pytest tests/unit/test_direct_first_ladder.py -q
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_DE = _REPO_ROOT / "shared-utils" / "decision_engine"

sys.path.insert(0, str(_REPO_ROOT / "shared-utils"))

_spec = importlib.util.spec_from_file_location(
    "decision_engine_ladder_ladder", _DE / "ladder" / "ladder.py")
ladder = importlib.util.module_from_spec(_spec)
sys.modules["decision_engine_ladder_ladder"] = ladder
_spec.loader.exec_module(ladder)

_TS, _ORO, _CR = ladder._load_providers()

_FAKE_SECRET_A = "ladderFakeDirectKey9Qm4Zx7Vb2Nw8"
_FAKE_SECRET_B = "ladderFakeRouterKey3Kp8Rn5Tu2Wx6"


class FakeClock:
    def __init__(self, start=1000.0):
        self.t = float(start)

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += float(seconds)


def _ok(payload=None, attempts=1, estimated=0.0, actual=0.0):
    out = {"outcome": "ok", "attempts": attempts,
           "estimated_cost": estimated, "actual_cost": actual}
    if payload is not None:
        out["payload"] = payload
    return out


def _fail(outcome="transport_error", attempts=1):
    return {"outcome": outcome, "attempts": attempts,
            "estimated_cost": 0.0, "actual_cost": 0.0}


def _creds(direct=True, openrouter=True):
    return {"direct": SimpleNamespace(configured=bool(direct)),
            "openrouter": SimpleNamespace(configured=bool(openrouter))}


def _allow(provider, purpose="decide"):
    return {"spend_ok": True, "transmit_ok": True, "reason": "standing-policy"}


def _qs():
    return [{"id": "q1", "type": "select"}]


def _select_specs():
    return {"q1": {"type": "select", "candidates": ["a", "b"],
                   "prob_keys": ["a", "b"]}}


def _good_select_payload():
    return {"model": _TS.TYPESAFE_MODEL, "judgments": [{
        "question_id": "q1", "type": "select", "answer": "a",
        "probabilities": {"a": 0.7, "b": 0.3}}]}


def make_ladder(clock=None, resolve=None, direct=None, router=None,
                policy=None, circuit=None, **kw):
    clk = clock or FakeClock()
    calls = {"direct": [], "openrouter": []}

    def _direct(*, body, api_key, timeout_ms, http_post=None):
        calls["direct"].append({"timeout_ms": timeout_ms,
                               "has_key": bool(api_key)})
        if direct is not None:
            return direct(body=body, api_key=api_key, timeout_ms=timeout_ms)
        return _ok(_good_select_payload())

    def _router(*, state, questions, expected, candidates=(), api_key=None,
                key_env=None, timeout_s=2.5, transport=None):
        calls["openrouter"].append({"timeout_s": timeout_s})
        if router is not None:
            return router(state=state, questions=questions,
                          expected=expected, timeout_s=timeout_s)
        return _ok({"model": _ORO.REQUESTED_MODEL, "judgments": []})

    lad = ladder.DirectFirstLadder(
        resolve_credentials=resolve or (lambda *a: _creds()),
        direct_call=_direct, openrouter_call=_router,
        policy_fn=policy or _allow, clock=clk,
        circuit=circuit, **kw)
    return lad, clk, calls


class RealModulesWired(unittest.TestCase):
    def test_ladder_orchestrates_real_d04_d05_d06(self):
        self.assertEqual(_TS.TYPESAFE_ENDPOINT,
                         "https://api.typesafe.ai/v1/systemone")
        self.assertEqual(_TS.TYPESAFE_MODEL, "jev-1.13.0")
        self.assertEqual(_ORO.ENDPOINT,
                         "https://openrouter.ai/api/alpha/decisions")
        self.assertEqual(_ORO.REQUESTED_MODEL, "typesafe/jev-1.13")
        self.assertTrue(hasattr(_CR, "resolve_company_credentials"))
        src = (_DE / "ladder" / "ladder.py").read_text(encoding="utf-8")
        self.assertNotIn("urllib", src)  # no reimplemented transport
        self.assertNotIn("os.environ", src)

    def test_no_network_or_environ_at_import(self):
        before = dict(os.environ)
        fresh = importlib.util.spec_from_file_location(
            "ladder_reimport_check", _DE / "ladder" / "ladder.py")
        mod = importlib.util.module_from_spec(fresh)
        fresh.loader.exec_module(mod)
        self.assertEqual(dict(os.environ), before)


class DirectFirstOrdering(unittest.TestCase):
    def test_direct_wins_openrouter_zero_calls(self):
        lad, _, calls = make_ladder()
        verdict = lad.run(company_id="acme", state={"s": 1},
                          questions=_qs(), keys={})
        self.assertEqual(verdict["decision_source"], "typesafe_direct")
        self.assertTrue(verdict["ok"])
        self.assertEqual(len(calls["direct"]), 1)
        self.assertEqual(calls["openrouter"], [])
        self.assertEqual(verdict["stages"][0]["provider"],
                         "typesafe_direct")
        self.assertEqual(verdict["stages"][0]["outcome"], "ok")

    def test_direct_absent_openrouter_used(self):
        lad, _, calls = make_ladder(
            resolve=lambda *a: _creds(direct=False, openrouter=True))
        verdict = lad.run(company_id="acme", state={"s": 1},
                          questions=_qs(), keys={})
        self.assertEqual(verdict["decision_source"], "openrouter")
        self.assertEqual(calls["direct"], [])
        self.assertEqual(len(calls["openrouter"]), 1)
        self.assertEqual(verdict["stages"][0]["skip_reason"], "no_credential")
        self.assertEqual(verdict["stages"][1]["outcome"], "ok")

    def test_both_absent_no_jev_fallback_provenance(self):
        lad, _, calls = make_ladder(
            resolve=lambda *a: _creds(direct=False, openrouter=False))
        verdict = lad.run(company_id="acme", state={"s": 1},
                          questions=_qs(), keys={})
        self.assertEqual(verdict["decision_source"], "no_jev")
        self.assertTrue(verdict["ok"])
        self.assertEqual(calls["direct"], [])
        self.assertEqual(calls["openrouter"], [])
        skips = [s["skip_reason"] for s in verdict["stages"][:2]]
        self.assertEqual(skips, ["no_credential", "no_credential"])
        self.assertEqual(verdict["stages"][2]["stage"], "no_jev")
        self.assertIn("fallback", verdict)

    def test_direct_invalid_response_falls_through_to_openrouter(self):
        bad = {"model": _TS.TYPESAFE_MODEL, "judgments": [{
            "question_id": "q1", "type": "select", "answer": "intruder",
            "probabilities": {"a": 0.5, "b": 0.5}}]}
        lad, _, calls = make_ladder(
            direct=lambda **k: _ok(bad))
        verdict = lad.run(company_id="acme", state={"s": 1},
                          questions=_qs(), keys={},
                          direct_specs=_select_specs())
        self.assertEqual(verdict["decision_source"], "openrouter")
        self.assertEqual(len(calls["direct"]), 1)
        self.assertEqual(len(calls["openrouter"]), 1)
        self.assertEqual(verdict["stages"][0]["outcome"],
                         "invalid_response")

    def test_key_material_never_in_verdict(self):
        lad, _, _ = make_ladder()
        verdict = lad.run(
            company_id="acme", state={"s": 1}, questions=_qs(),
            keys={"TYPESAFE_API_KEY": _FAKE_SECRET_A,
                  "OPENROUTER_API_KEY": _FAKE_SECRET_B})
        blob = json.dumps(verdict)
        self.assertNotIn(_FAKE_SECRET_A, blob)
        self.assertNotIn(_FAKE_SECRET_B, blob)


class RootDeadlineSuite(unittest.TestCase):
    def test_remaining_and_send_budget_take_minimum(self):
        clk = FakeClock()
        root = ladder.RootDeadline(300000, clock=clk,
                                   settlement_reserve_ms=2000)
        self.assertAlmostEqual(root.remaining_ms(), 300000.0, places=6)
        # min(remaining - reserve, op limit, stage left)
        self.assertEqual(root.send_budget_ms(2500, 6000), 2500)
        self.assertEqual(root.send_budget_ms(500000, 6000), 6000)
        clk.advance(290)
        self.assertAlmostEqual(root.send_budget_ms(500000, 60000),
                               8000.0, places=6)

    def test_no_extend_or_reset_api(self):
        for name in ("extend", "reset", "refresh", "renew", "add_budget",
                     "extend_budget", "new_budget"):
            self.assertFalse(hasattr(ladder.RootDeadline, name), name)

    def test_exhausted_budget_short_circuits_to_fallback(self):
        clk = FakeClock()
        root = ladder.RootDeadline(1000, clock=clk)
        clk.advance(60)  # budget long gone before entry
        lad, _, calls = make_ladder()
        verdict = lad.run(company_id="acme", state={"s": 1},
                          questions=_qs(), keys={}, root_deadline=root)
        self.assertEqual(verdict["decision_source"], "no_jev")
        self.assertEqual(calls["direct"], [])
        self.assertEqual(calls["openrouter"], [])
        reasons = [s["skip_reason"] for s in verdict["stages"]]
        self.assertIn("root_deadline_expired", reasons)
        self.assertEqual(verdict["stages"][-1]["skip_reason"],
                         "root_deadline_expired")

    def test_slow_calls_never_extend_root(self):
        clk = FakeClock()
        expiry_holder = {}

        def _slow_direct(**k):
            clk.advance(5)  # one slow 5s call against a 1s root
            return _fail("timeout")

        lad, _, calls = make_ladder(clock=clk, direct=_slow_direct,
                                    root_budget_ms=1000)
        verdict = lad.run(company_id="acme", state={"s": 1},
                          questions=_qs(), keys={})
        expiry_holder["expiry"] = verdict["root"]["expiry_ms"]
        # Slow direct consumed the whole root; OpenRouter never sent.
        self.assertEqual(len(calls["direct"]), 1)
        self.assertEqual(calls["openrouter"], [])
        self.assertEqual(verdict["stages"][1]["skip_reason"],
                         "root_deadline_expired")
        self.assertTrue(verdict["root"]["expired"])
        # Root never extended: remaining only shrank, expiry is start+budget.
        self.assertAlmostEqual(expiry_holder["expiry"],
                               (1000.0 + 1.0) * 1000.0, places=6)

    def test_stage_receives_remaining_not_fresh_budget(self):
        lad, clk, calls = make_ladder(root_budget_ms=300000)
        clk.advance(290)  # 10s left of the one root budget
        verdict = lad.run(company_id="acme", state={"s": 1},
                          questions=_qs(), keys={})
        timeout_ms = calls["direct"][0]["timeout_ms"]
        self.assertLessEqual(timeout_ms, 10000.0 - 2000.0)  # minus reserve
        self.assertEqual(verdict["stages"][0]["remaining_ms_at_entry"],
                         verdict["stages"][0]["remaining_ms_at_entry"])


class AttemptAccountingSuite(unittest.TestCase):
    def test_record_accumulates_per_stage_and_costs(self):
        acc = ladder.AttemptAccounting()
        acc.record("typesafe_direct", 1, estimated=2.0, actual=1.5)
        acc.record("typesafe_direct", 2, estimated=1.0, actual=1.0)
        acc.record("openrouter", 1, estimated=0.5, actual=0.25)
        summary = acc.summary()
        self.assertEqual(summary["attempts"],
                         {"typesafe_direct": 3, "openrouter": 1})
        self.assertEqual(summary["total_attempts"], 4)
        self.assertAlmostEqual(summary["estimated_cost"], 3.5)
        self.assertAlmostEqual(summary["actual_cost"], 2.75)

    def test_nested_retry_consumes_same_budget_total_bounded(self):
        # Provider-level retry inside ONE stage reports attempts=3; the
        # shared cap (2) then blocks OpenRouter: no fresh budget per stage.
        lad, _, calls = make_ladder(
            direct=lambda **k: _fail("overload", attempts=3),
            max_total_attempts=2)
        verdict = lad.run(company_id="acme", state={"s": 1},
                          questions=_qs(), keys={})
        self.assertEqual(verdict["accounting"]["total_attempts"], 3)
        self.assertEqual(
            verdict["accounting"]["attempts"]["typesafe_direct"], 3)
        self.assertEqual(calls["openrouter"], [])
        self.assertEqual(verdict["stages"][1]["skip_reason"],
                         "budget_exhausted")
        self.assertEqual(verdict["decision_source"], "no_jev")


class CircuitBreakerSuite(unittest.TestCase):
    def test_opens_after_threshold_and_skips_without_call(self):
        clk = FakeClock()
        brk = ladder.CircuitBreaker(failure_threshold=3, cooldown_ms=60000,
                                    clock=clk)
        for _ in range(3):
            self.assertTrue(brk.allow("typesafe_direct"))
            brk.record_failure("typesafe_direct")
        self.assertEqual(brk.state_of("typesafe_direct"), "open")
        self.assertFalse(brk.allow("typesafe_direct"))

    def test_half_open_probe_allowed_exactly_once(self):
        clk = FakeClock()
        brk = ladder.CircuitBreaker(failure_threshold=1, cooldown_ms=60000,
                                    clock=clk)
        brk.record_failure("openrouter")
        self.assertFalse(brk.allow("openrouter"))
        clk.advance(61)
        self.assertEqual(brk.state_of("openrouter"), "half_open")
        self.assertTrue(brk.allow("openrouter"))  # the one probe
        self.assertFalse(brk.allow("openrouter"))  # probe in flight
        brk.record_success("openrouter")
        self.assertEqual(brk.state_of("openrouter"), "closed")
        self.assertTrue(brk.allow("openrouter"))

    def test_ladder_skips_open_circuit_without_calling(self):
        clk = FakeClock()
        brk = ladder.CircuitBreaker(failure_threshold=3,
                                    cooldown_ms=3600000, clock=clk)
        direct_calls = []

        def _down(**k):
            direct_calls.append(1)
            return _fail("overload")

        lad, _, _ = make_ladder(
            clock=clk, direct=_down, circuit=brk,
            resolve=lambda *a: _creds(direct=True, openrouter=False))
        for _ in range(3):
            verdict = lad.run(company_id="acme", state={"s": 1},
                              questions=_qs(), keys={})
            self.assertEqual(verdict["decision_source"], "no_jev")
        self.assertEqual(len(direct_calls), 3)
        verdict = lad.run(company_id="acme", state={"s": 1},
                          questions=_qs(), keys={})
        self.assertEqual(len(direct_calls), 3)  # zero further calls
        self.assertEqual(verdict["stages"][0]["skip_reason"],
                         "circuit_open")


class PermissionsGateSuite(unittest.TestCase):
    def test_deny_spend_skips_not_authorized_without_send(self):
        log = []
        lad, _, calls = make_ladder(
            policy=lambda p, q="decide": {"spend_ok": False,
                                          "transmit_ok": True,
                                          "reason": "standing-denial"})
        verdict = lad.run(company_id="acme", state={"s": 1},
                          questions=_qs(), keys={}, order_log=log)
        # Both remote stages denied; only the fallback runs.
        self.assertEqual(verdict["decision_source"], "no_jev")
        self.assertEqual(calls["direct"], [])
        self.assertEqual(calls["openrouter"], [])
        self.assertEqual(verdict["stages"][0]["skip_reason"],
                         "not_authorized")
        self.assertEqual(verdict["stages"][1]["skip_reason"],
                         "not_authorized")
        self.assertIn("policy_check:typesafe_direct", log)
        self.assertNotIn("send:typesafe_direct", log)

    def test_deny_transmit_skips_data_not_permitted(self):
        lad, _, calls = make_ladder(
            policy=lambda p, q="decide": {"spend_ok": True,
                                          "transmit_ok": False,
                                          "reason": "data-policy"})
        verdict = lad.run(company_id="acme", state={"s": 1},
                          questions=_qs(), keys={})
        self.assertEqual(verdict["stages"][0]["skip_reason"],
                         "data_not_permitted")
        self.assertEqual(calls["direct"], [])

    def test_budget_reason_maps_to_budget_exhausted(self):
        lad, _, calls = make_ladder(
            policy=lambda p, q="decide": {"spend_ok": False,
                                          "transmit_ok": True,
                                          "reason": "budget"})
        verdict = lad.run(company_id="acme", state={"s": 1},
                          questions=_qs(), keys={})
        self.assertEqual(verdict["stages"][0]["skip_reason"],
                         "budget_exhausted")
        self.assertEqual(calls["direct"], [])

    def test_reservation_before_send_ordering(self):
        log = []

        def _net(*, body, api_key, timeout_ms, http_post=None):
            log.append("network:typesafe_direct")  # the injected 'network'
            return _ok(_good_select_payload())

        lad, _, _ = make_ladder(direct=_net)
        verdict = lad.run(company_id="acme", state={"s": 1},
                          questions=_qs(), keys={}, order_log=log)
        self.assertEqual(verdict["decision_source"], "typesafe_direct")
        self.assertEqual(
            log,
            ["policy_check:typesafe_direct",
             "reserve:typesafe_direct",
             "policy_recheck:typesafe_direct",
             "send:typesafe_direct",
             "network:typesafe_direct",
             "reconcile:typesafe_direct"])
        # Policy recheck happens after reservation, never inside the call.
        self.assertLess(log.index("policy_recheck:typesafe_direct"),
                        log.index("send:typesafe_direct"))
        self.assertLess(log.index("network:typesafe_direct"),
                        log.index("reconcile:typesafe_direct"))

    def test_recheck_denial_blocks_send_but_reconciles(self):
        log = []
        reconciled = []
        seen = {"n": 0}

        def _flaky_policy(provider, purpose="decide"):
            seen["n"] += 1
            if seen["n"] == 1:
                return {"spend_ok": True, "transmit_ok": True,
                        "reason": "standing-policy"}
            return {"spend_ok": True, "transmit_ok": False,
                    "reason": "revoked-mid-flight"}

        lad, _, calls = make_ladder(
            policy=_flaky_policy,
            resolve=lambda *a: _creds(direct=True, openrouter=False),
            reconcile_fn=lambda p, r, a: reconciled.append((p, a)))
        verdict = lad.run(company_id="acme", state={"s": 1},
                          questions=_qs(), keys={}, order_log=log)
        self.assertEqual(calls["direct"], [])
        self.assertEqual(verdict["stages"][0]["skip_reason"],
                         "data_not_permitted")
        self.assertEqual(reconciled, [("typesafe_direct", 0.0)])
        self.assertNotIn("send:typesafe_direct", log)

    def test_checked_before_every_remote_call(self):
        seen = []
        lad, _, calls = make_ladder(
            direct=lambda **k: _fail("overload"),
            router=lambda **k: _ok(
                {"model": _ORO.REQUESTED_MODEL, "judgments": []}),
            policy=lambda p, q="decide": (
                seen.append(p),
                {"spend_ok": True, "transmit_ok": True,
                 "reason": "standing-policy"})[1])
        verdict = lad.run(company_id="acme", state={"s": 1},
                          questions=_qs(), keys={})
        self.assertEqual(verdict["decision_source"], "openrouter")
        self.assertIn("typesafe_direct", seen)
        self.assertIn("openrouter", seen)


class OfflineHygiene(unittest.TestCase):
    def test_no_environ_mutation_no_socket_use(self):
        import socket
        before = dict(os.environ)
        lad, _, _ = make_ladder()
        verdict = lad.run(company_id="acme", state={"s": 1},
                          questions=_qs(), keys={})
        self.assertEqual(dict(os.environ), before)
        self.assertTrue(verdict["ok"])
        self.assertFalse(hasattr(socket, "_ladder_test_marker"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
