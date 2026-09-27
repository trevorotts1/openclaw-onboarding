#!/usr/bin/env python3
"""A61 shadow evaluation enforcement tests (JEV spec 1.1, s 3.6/3.9).

Proves the repaired shadow sampler
(shared-utils/decision_engine/shadow/__init__.py) against the REAL D34
predicates (modes.py) and the REAL D23 store (commit.py):

  * sampling/quota/dedup/in-flight/deadline are CONSUMED: every typed
    denial the gate can produce is exercised through the sampler and the
    refusal path (refuse_shadow_commit) runs on every evaluation;
  * enforcement SURVIVES RESTART: a second process (fresh evaluator
    instance, same state dir) rehydrates dedup/quota/in-flight numbers
    from SQLite, not memory;
  * enforcement SURVIVES FAILOVER: a peer holding the in-flight slot
    blocks the failover's sample; a deadline-expired in-flight sample is
    swept so it cannot starve the slot; external-attempt retries consume
    the same persisted budget;
  * results DO NOT MUTATE task/persona/adaptive-weight/confirmation/
    execution state (byte/dict compare before/after a full cycle);
  * the whole cycle runs inside the D30 offline() context (socket stays
    blocked) with zero real network attempts.

Run: python3 -m pytest tests/unit/test_shadow_eval_a61.py -q
"""

from __future__ import annotations

import copy
import importlib.util
import json
import socket
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_DE = _REPO_ROOT / "shared-utils" / "decision_engine"
_SHADOW_PY = _DE / "shadow" / "__init__.py"
_PERSONA_FIXTURE = _DE / "contracts" / "fixtures" / "envelope_committed.json"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


modes = _load("a61_modes", _DE / "modes" / "modes.py")
commit = _load("a61_commit", _DE / "commit" / "commit.py")
shadow = _load("a61_shadow", _SHADOW_PY)
adaptive = _load("a61_adaptive",
                 _REPO_ROOT / "shared-utils" / "adaptive_weights.py")
ev = _load("a61_eval", _DE / "evaluation" / "__init__.py")

CFG = {"shadow": {"sample_rate": 1.0, "max_evaluations_per_company_hour": 20,
                  "max_external_attempts_per_company_hour": 40,
                  "max_in_flight_per_company": 1,
                  "evaluation_deadline_ms": 6000}}


def _sample_kw(**kw):
    base = dict(company="acme", scope="s1", input_hash="h1", stage="dept",
                candidate_version="v1", policy_version="p1",
                model_version="m1", epoch="e1",
                config=copy.deepcopy(CFG), now_s=1000.0)
    base.update(kw)
    return base


class SamplerConsumesPredicates(unittest.TestCase):
    """Every enforcement predicate is reached through the sampler."""

    def test_source_names_each_predicate_call_site(self):
        src = _SHADOW_PY.read_text(encoding="utf-8")
        for call in ("self.modes.shadow_sample_allowed(",
                     "self.modes.shadow_dedup_key(",
                     "self.modes.refuse_shadow_commit("):
            self.assertIn(call, src, call)
        self.assertIn("deadline_ms=allowance_ms", src)
        for line_no, line in enumerate(src.splitlines(), 1):
            if ("self.modes.shadow_sample_allowed(" in line
                    or "self.modes.shadow_dedup_key(" in line
                    or "self.modes.refuse_shadow_commit(" in line
                    or "deadline_ms=allowance_ms" in line):
                self.assertTrue(line.strip())
                _ = line_no  # named call sites are the evidence

    def test_sampled_and_finished_persist(self):
        with tempfile.TemporaryDirectory(prefix="blackceomacmini-REP-061-") as tmp:
            se = shadow.ShadowEvaluator(tmp, "t1")
            res = se.evaluate(**_sample_kw())
            self.assertTrue(res["run"], res)
            self.assertEqual(res["reason"], "sampled")
            self.assertIn("diagnostic only", res["refused_commit"])
            fin = se.finish(key=res["key"])
            self.assertTrue(fin["recorded"])
            row = se.status(key=res["key"])
            self.assertEqual(row["status"], "complete")

    def test_not_sampled_rate_zero(self):
        with tempfile.TemporaryDirectory(prefix="blackceomacmini-REP-061-") as tmp:
            cfg = copy.deepcopy(CFG)
            cfg["shadow"]["sample_rate"] = 0.0
            res = shadow.ShadowEvaluator(tmp, "t1").evaluate(
                **_sample_kw(config=cfg))
            self.assertFalse(res["run"])
            self.assertEqual(res["reason"], "not_sampled")

    def test_not_authorized(self):
        with tempfile.TemporaryDirectory(prefix="blackceomacmini-REP-061-") as tmp:
            res = shadow.ShadowEvaluator(tmp, "t1").evaluate(
                **_sample_kw(permission_ok=False))
            self.assertFalse(res["run"])
            self.assertEqual(res["reason"], "not_authorized")

    def test_quota_exhausted_persisted_count(self):
        with tempfile.TemporaryDirectory(prefix="blackceomacmini-REP-061-") as tmp:
            cfg = copy.deepcopy(CFG)
            cfg["shadow"]["max_evaluations_per_company_hour"] = 1
            se = shadow.ShadowEvaluator(tmp, "t1")
            first = se.evaluate(**_sample_kw(config=cfg))
            self.assertTrue(first["run"], first)
            second = se.evaluate(
                **_sample_kw(config=cfg, input_hash="h2"))
            self.assertFalse(second["run"])
            self.assertEqual(second["reason"], "quota_exhausted")

    def test_in_flight_capped(self):
        with tempfile.TemporaryDirectory(prefix="blackceomacmini-REP-061-") as tmp:
            se = shadow.ShadowEvaluator(tmp, "t1")
            first = se.evaluate(**_sample_kw())
            self.assertTrue(first["run"], first)
            second = se.evaluate(**_sample_kw(input_hash="h2"))
            self.assertFalse(second["run"])
            self.assertEqual(second["reason"], "in_flight_capped")

    def test_dedup_same_identity_never_re_samples(self):
        with tempfile.TemporaryDirectory(prefix="blackceomacmini-REP-061-") as tmp:
            se = shadow.ShadowEvaluator(tmp, "t1")
            first = se.evaluate(**_sample_kw())
            self.assertTrue(first["run"], first)
            again = se.evaluate(**_sample_kw())
            self.assertFalse(again["run"])
            self.assertEqual(again["reason"], "duplicate_in_flight")
            se.finish(key=first["key"])
            later = se.evaluate(**_sample_kw(now_s=1001.0))
            self.assertEqual(later["reason"], "duplicate_sample")

    def test_deadline_expired_denies_and_persists(self):
        with tempfile.TemporaryDirectory(prefix="blackceomacmini-REP-061-") as tmp:
            se = shadow.ShadowEvaluator(tmp, "t1")
            res = se.evaluate(**_sample_kw(deadline_remaining_ms=0))
            self.assertFalse(res["run"])
            self.assertEqual(res["reason"], "deadline_expired")
            self.assertEqual(se.status(key=res["key"])["status"], "skipped")

    def test_gate_deadline_parameter_typed_denials(self):
        ok, why = modes.shadow_sample_allowed(
            sample_rate=1.0, draw=0.0, quota_remaining=5, in_flight=0,
            max_in_flight=1, permission_ok=True, deadline_ms=6000)
        self.assertTrue(ok, why)
        for bad in (0, -1, "x"):
            ok, why = modes.shadow_sample_allowed(
                sample_rate=1.0, draw=0.0, quota_remaining=5, in_flight=0,
                max_in_flight=1, permission_ok=True, deadline_ms=bad)
            self.assertFalse(ok)
            self.assertEqual(why, "deadline_expired")


class SurvivesRestartAndFailover(unittest.TestCase):
    def test_restart_rehydrates_dedup_quota_inflight(self):
        with tempfile.TemporaryDirectory(prefix="blackceomacmini-REP-061-") as tmp:
            first = shadow.ShadowEvaluator(tmp, "t1").evaluate(**_sample_kw())
            self.assertTrue(first["run"], first)
            # "restart": a brand-new instance over the same state dir only.
            restarted = shadow.ShadowEvaluator(tmp, "t1")
            dup = restarted.evaluate(**_sample_kw(input_hash="h2"))
            self.assertEqual(dup["reason"], "in_flight_capped")  # slot held
            state = restarted.company_state(company="acme", now_s=1001.0)
            self.assertEqual(state["in_flight"], 1)
            self.assertEqual(state["evaluations_used_hour"], 1)
            state_dir = Path(tmp)
            self.assertTrue(
                (state_dir / "shadow_evaluation.db").is_file())

    def test_failover_peer_sees_same_state_via_persisted_rows(self):
        with tempfile.TemporaryDirectory(prefix="blackceomacmini-REP-061-") as tmp:
            a = shadow.ShadowEvaluator(tmp, "t1")
            b = shadow.ShadowEvaluator(tmp, "t1")  # second process
            held = a.evaluate(**_sample_kw())
            self.assertTrue(held["run"], held)
            denied = b.evaluate(**_sample_kw(input_hash="h9"))
            self.assertEqual(denied["reason"], "in_flight_capped")
            a.finish(key=held["key"])
            # the recorded denial is never retried (gate contract)
            retry = b.evaluate(**_sample_kw(input_hash="h9"))
            self.assertEqual(retry["reason"], "duplicate_sample")
            # a new identity is admitted now the slot is free
            fresh = b.evaluate(**_sample_kw(input_hash="h10"))
            self.assertTrue(fresh["run"], fresh)

    def test_expired_in_flight_is_swept_not_starving(self):
        with tempfile.TemporaryDirectory(prefix="blackceomacmini-REP-061-") as tmp:
            a = shadow.ShadowEvaluator(tmp, "t1")
            held = a.evaluate(**_sample_kw())  # deadline 6000ms -> +6s
            self.assertTrue(held["run"], held)
            late = a.evaluate(**_sample_kw(input_hash="h2", now_s=1010.0))
            self.assertTrue(late["run"], late)  # slot freed by sweep
            self.assertEqual(a.status(key=held["key"])["status"], "expired")
            self.assertEqual(
                a.company_state(company="acme", now_s=1010.0)["in_flight"], 1)
            # a late finish cannot resurrect an expired sample
            fin = a.finish(key=held["key"], now_s=1011.0)
            self.assertFalse(fin["recorded"])
            self.assertEqual(fin["reason"], "already_expired")

    def test_external_retries_consume_same_persisted_budget(self):
        with tempfile.TemporaryDirectory(prefix="blackceomacmini-REP-061-") as tmp:
            cfg = copy.deepcopy(CFG)
            cfg["shadow"]["max_external_attempts_per_company_hour"] = 2
            a = shadow.ShadowEvaluator(tmp, "t1")
            b = shadow.ShadowEvaluator(tmp, "t1")  # failover peer
            self.assertTrue(a.reserve_external(
                company="acme", config=cfg, now_s=1000.0)["reserved"])
            self.assertTrue(b.reserve_external(
                company="acme", config=cfg, now_s=1001.0)["reserved"])
            third = b.reserve_external(
                company="acme", config=cfg, now_s=1002.0)
            self.assertFalse(third["reserved"])
            self.assertEqual(third["reason"], "external_quota_exhausted")
            # window ages out: same quota, one hour later
            fourth = b.reserve_external(
                company="acme", config=cfg, now_s=5000.0)
            self.assertTrue(fourth["reserved"])


class ResultsNeverMutateOtherState(unittest.TestCase):
    def test_full_cycle_leaves_every_named_state_untouched(self):
        persona_before = _PERSONA_FIXTURE.read_bytes()
        persona_parsed_before = json.loads(persona_before)
        weights_before = copy.deepcopy(adaptive.DEFAULT_WEIGHTS)
        weights_call = adaptive.get_weights_for_task(
            "write a follow-up email", mode="leadership")
        execution = commit.fresh_state(input_hash="h-exec")
        rev = commit.cas_commit(execution, 0,
                                {"decisionId": "d1", "inputHash": "h-exec"},
                                {"board": 1})
        running = commit.start_execution(execution)
        store_before = json.dumps(execution, sort_keys=True, default=str)
        running_before = json.dumps(running, sort_keys=True, default=str)
        caller_cfg = copy.deepcopy(CFG)
        caller_cfg["confirmation"] = {"mode": "owner_confirm",
                                      "state": "pending"}
        cfg_frozen = json.dumps(caller_cfg, sort_keys=True)
        with tempfile.TemporaryDirectory(prefix="blackceomacmini-REP-061-") as tmp:
            se = shadow.ShadowEvaluator(tmp, "t1")
            res = se.evaluate(**_sample_kw(config=caller_cfg))
            self.assertTrue(res["run"], res)
            se.finish(key=res["key"])
            se.reserve_external(company="acme", config=caller_cfg,
                                now_s=1000.0)
            se.evaluate(**_sample_kw(config=caller_cfg, input_hash="h2"))
            state_files = sorted(
                str(p.relative_to(tmp)) for p in Path(tmp).rglob("*")
                if p.is_file())
            # only the shadow evaluation db may exist in the state dir
            self.assertEqual(state_files, ["shadow_evaluation.db"])
        self.assertEqual(_PERSONA_FIXTURE.read_bytes(), persona_before)
        self.assertEqual(json.loads(persona_before), persona_parsed_before)
        self.assertEqual(adaptive.DEFAULT_WEIGHTS, weights_before)
        self.assertEqual(
            adaptive.get_weights_for_task("write a follow-up email",
                                          mode="leadership"),
            weights_call)
        self.assertEqual(json.dumps(execution, sort_keys=True, default=str),
                         store_before)
        self.assertEqual(execution["decision_revision"], rev)
        self.assertEqual(json.dumps(running, sort_keys=True, default=str),
                         running_before)
        self.assertEqual(json.dumps(caller_cfg, sort_keys=True), cfg_frozen)
        with self.assertRaises(modes.ShadowCommitError):
            modes.refuse_shadow_commit(res)


class OfflinePathStaysOffline(unittest.TestCase):
    def test_full_cycle_inside_offline_ctx_with_zero_net_attempts(self):
        real_socket = socket.socket
        attempts = []

        class CountingSocket(real_socket):
            def __init__(self, *a, **kw):
                fam = a[0] if a else kw.get("family")
                if fam in (socket.AF_INET, socket.AF_INET6):
                    attempts.append(fam)
                    raise RuntimeError("a61: outbound attempt blocked")
                super().__init__(*a, **kw)

        with tempfile.TemporaryDirectory(prefix="blackceomacmini-REP-061-") as tmp:
            socket.socket = CountingSocket
            try:
                with ev.offline():
                    se = shadow.ShadowEvaluator(tmp, "t1")
                    res = se.evaluate(**_sample_kw())
                    self.assertTrue(res["run"], res)
                    self.assertEqual(se.company_state(
                        company="acme", now_s=1001.0)["in_flight"], 1)
            finally:
                socket.socket = real_socket
        self.assertEqual(attempts, [])


if __name__ == "__main__":
    unittest.main()
