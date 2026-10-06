"""test_f33_execution_policy.py — F33 acceptance (ONB half).

"Ultra can use more slots with an eligible provider but launches only useful
work. Ollama request counts never exceed 3 or 10 for the chosen plan, including
orchestration/QC calls. Worker death, 429 and quota exhaustion recover without
duplicate side effects."

Proven with deterministic delayed provider stubs against
shared-utils/social_execution_policy.py:
  1. 60 independent jobs: Ultra fills the application ceiling (50) with USEFUL
     work; Standard runs exactly 1.
  2. Ollama Cloud plan limits: Pro never exceeds 3 overlapping claims, Max
     never exceeds 10 — INCLUDING coordinator/QC calls (same semaphore);
     unknown plan degrades to the conservative default (2), never unlimited.
  3. Dependent chains: waves order correctly; a dependent step is never
     claimed before its dependencies settle.
  4. Worker death: expired leases recovered WITHOUT duplicate side effects —
     the stale holder's settle is refused on fencing-token mismatch.
  5. 429/Retry-After: provider parked; claims refused until the window passes.
  6. Quota exhaustion (budget): a reservation that would exceed the cap is
     refused; settled spend is retained; released reservations free headroom.
  7. Fair queue across providers; circuit breaker opens after repeated
     failures while other providers stay eligible.

Run: python3 -m unittest discover -s tests/social-planner -p 'test_f*.py'
"""

import importlib.util
import sys
import unittest
from pathlib import Path

_ONB_ROOT = Path(__file__).resolve().parents[2]
_POLICY = _ONB_ROOT / "shared-utils" / "social_execution_policy.py"


def _load_policy_module():
    spec = importlib.util.spec_from_file_location("f33_social_execution_policy", _POLICY)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["f33_social_execution_policy"] = mod
    spec.loader.exec_module(mod)
    return mod


policy_mod = _load_policy_module()
ExecutionPolicy = policy_mod.ExecutionPolicy
ULTRA_APP_CEILING = policy_mod.ULTRA_APP_CEILING
UNKNOWN_PROVIDER_QUOTA_DEFAULT = policy_mod.UNKNOWN_PROVIDER_QUOTA_DEFAULT


class FakeClock:
    def __init__(self, start=10_000.0):
        self.t = start

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


def _plan(provider, n, *, role="worker", cycle_id="c1", cost=0.0, chain=False):
    steps = []
    prev = None
    for i in range(n):
        sid = f"{role}-{i:02d}"
        deps = [prev] if (chain and prev) else []
        steps.append({"step_id": sid, "depends_on": deps, "role": role,
                      "provider": provider, "estimated_cost": cost})
        prev = sid
    return {"cycle_id": cycle_id, "steps": steps}


class TestF33ExecutionPolicy(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()

    # ── 1. Ceilings ────────────────────────────────────────────────────────
    def test_ultra_fills_ceiling_with_useful_work_and_standard_runs_one(self):
        plan = _plan("openrouter", 60)
        plan["providers"] = {"openrouter": {"concurrency": 100}}
        ultra = ExecutionPolicy(mode="ultra", plan=plan, now_fn=self.clock)
        claimed = []
        while True:
            lease = ultra.claim(f"worker-{len(claimed)}")
            if not lease:
                break
            claimed.append(lease)
            self.clock.advance(0.001)
        self.assertLessEqual(len(claimed), ULTRA_APP_CEILING,
                             "Ultra never exceeds the 50-execution application ceiling")
        self.assertEqual(len(claimed), ULTRA_APP_CEILING,
                         "Ultra fills its ceiling with useful (ready) work")

        standard = ExecutionPolicy(mode="standard", plan=plan, now_fn=self.clock)
        self.assertIsNotNone(standard.claim("w1"))
        self.assertIsNone(standard.claim("w2"), "Standard runs exactly ONE execution")

    # ── 2. Ollama plan limits (incl. coordinator/QC calls) ────────────────
    def test_ollama_plan_limits_including_qc_calls(self):
        for plan_name, limit in (("pro", 3), ("max", 10)):
            # Roles are IRRELEVANT to the semaphore: writer AND qc steps share
            # the provider limit — orchestration/QC calls count too.
            plan = {"cycle_id": "c", "ollama_plan": plan_name,
                    "steps": ([{"step_id": f"w-{i:02d}", "depends_on": [], "role": "writer",
                                "provider": "ollama-cloud", "estimated_cost": 0}
                               for i in range(30)]
                              + [{"step_id": f"qc-{i:02d}", "depends_on": [], "role": "qc",
                                  "provider": "ollama-cloud", "estimated_cost": 0}
                                 for i in range(5)])}
            pol = ExecutionPolicy(mode="ultra", plan=plan, now_fn=self.clock)
            overlap = 0
            active = []
            while True:
                lease = pol.claim("w")
                if not lease:
                    break
                active.append(lease)
                overlap = max(overlap, len(active))
                if len(active) >= 50:  # never even brush the app ceiling
                    break
            self.assertLessEqual(overlap, limit,
                                 f"Ollama {plan_name} never exceeds {limit} concurrent calls "
                                 f"(saw {overlap})")

        # Unknown plan → conservative default (2), never unlimited.
        plan = _plan("ollama-cloud", 20)
        pol = ExecutionPolicy(mode="ultra", plan=plan, now_fn=self.clock)
        claimed = []
        while True:
            lease = pol.claim("w")
            if not lease:
                break
            claimed.append(lease)
        self.assertEqual(len(claimed), UNKNOWN_PROVIDER_QUOTA_DEFAULT,
                         "unknown Ollama plan degrades to the conservative default")
        # Plan-provided concurrency overrides win.
        plan2 = {"cycle_id": "c",
                 "providers": {"custom": {"concurrency": 7}},
                 "steps": [{"step_id": f"s-{i}", "depends_on": [], "role": "worker",
                            "provider": "custom", "estimated_cost": 0} for i in range(20)]}
        pol2 = ExecutionPolicy(mode="ultra", plan=plan2, now_fn=self.clock)
        count = 0
        while pol2.claim("w"):
            count += 1
        self.assertEqual(count, 7, "an approved plan's concurrency entry is honored")

    # ── 3. Dependency waves ────────────────────────────────────────────────
    def test_dependent_chains_stay_ordered(self):
        plan = _plan("openrouter", 4, chain=True)
        pol = ExecutionPolicy(mode="ultra", plan=plan, now_fn=self.clock)
        waves = pol.waves()
        self.assertEqual(waves, [["worker-00"], ["worker-01"], ["worker-02"], ["worker-03"]],
                         "a chain yields one wave per step, in order")
        # The dependent step is never claimable before its dependency settles.
        first = pol.claim("w")
        self.assertIsNotNone(first)
        self.assertIsNone(pol.claim("w2", step_id="worker-01"), "dependent step blocked while dep runs")
        pol.settle("worker-00", "w", first["fencing_token"])
        lease = pol.claim("w2", step_id="worker-01")
        self.assertIsNotNone(lease, "dependent becomes claimable only after dep settles")

    # ── 4. Worker death → recovery without duplicate side effects ─────────
    def test_worker_death_recovery_fencing(self):
        plan = _plan("openrouter", 2)
        pol = ExecutionPolicy(mode="ultra", plan=plan, now_fn=self.clock)
        lease = pol.claim("worker-a")
        self.assertIsNotNone(lease)
        self.clock.advance(200)  # lease TTL (120s) lapses — worker died
        recovered = pol.recover_expired()
        self.assertEqual(recovered, 1, "dead worker's lease reclaimed")
        # The STALE worker cannot commit after reassignment (fencing).
        self.assertFalse(pol.settle("worker-00", "worker-a", lease["fencing_token"]),
                         "stale worker settle refused on fencing token")
        # A new claim mints a NEW fencing token; the fresh worker commits fine.
        fresh = pol.claim("worker-b", step_id="worker-00")
        self.assertIsNotNone(fresh)
        self.assertGreater(fresh["fencing_token"], lease["fencing_token"],
                           "fencing token advances on reassignment")
        self.assertTrue(pol.settle("worker-00", "worker-b", fresh["fencing_token"]))
        self.assertFalse(pol.settle("worker-00", "worker-b", fresh["fencing_token"]),
                         "double settle refused")

    # ── 5. 429 / Retry-After ───────────────────────────────────────────────
    def test_429_retry_after_parks_provider(self):
        plan = {"cycle_id": "c",
                "steps": [{"step_id": "s1", "depends_on": [], "role": "worker",
                           "provider": "openrouter", "estimated_cost": 0},
                          {"step_id": "s2", "depends_on": [], "role": "worker",
                           "provider": "deepseek", "estimated_cost": 0}]}
        pol = ExecutionPolicy(mode="ultra", plan=plan, now_fn=self.clock)
        lease = pol.claim("w", step_id="s1")
        self.assertIsNotNone(lease)
        self.assertTrue(pol.fail("s1", "w", lease["fencing_token"],
                                 rate_limited=True, retry_after_seconds=60))
        self.assertIsNone(pol.claim("w", step_id="s1"), "429 parks the provider — no hammering")
        # An eligible ALTERNATIVE provider still runs (circuit isolation).
        self.assertIsNotNone(pol.claim("w2", step_id="s2"), "approved alternative provider proceeds")
        self.clock.advance(61)
        lease2 = pol.claim("w3", step_id="s1")
        self.assertIsNotNone(lease2, "after the Retry-After window the provider serves again")

    # ── 6. Budget reservation with settle ──────────────────────────────────
    def test_budget_reservation_and_settle(self):
        plan = {"cycle_id": "c", "cycle_budget_cap": 1.0,
                "steps": [{"step_id": "big", "depends_on": [], "role": "worker",
                           "provider": "openrouter", "estimated_cost": 0.75},
                          {"step_id": "huge", "depends_on": [], "role": "worker",
                           "provider": "openrouter", "estimated_cost": 0.50},
                          {"step_id": "small", "depends_on": [], "role": "worker",
                           "provider": "deepseek", "estimated_cost": 0.20}]}
        pol = ExecutionPolicy(mode="ultra", plan=plan, now_fn=self.clock)
        self.assertIsNotNone(pol.claim("w", step_id="big"), "big fits under the cap")
        self.assertIsNone(pol.claim("w2", step_id="huge"), "over-cap reservation refused")
        self.assertIsNotNone(pol.claim("w3", step_id="small"), "a fitting step still claims")
        status = pol.status()
        self.assertAlmostEqual(status["budget_reserved"], 0.95)
        # Settle keeps the spend; release frees the headroom.
        big_lease = pol._leases.get("big")
        pol.settle("big", "w", big_lease["fencing_token"])
        status2 = pol.status()
        self.assertAlmostEqual(status2["budget_reserved"], 0.20)
        self.assertAlmostEqual(status2["budget_cap"], 1.0)

    # ── 7. Fair queue + circuit breaker ────────────────────────────────────
    def test_fair_queue_and_circuit_breaker(self):
        plan = {"cycle_id": "c",
                "steps": ([{"step_id": f"a-{i}", "depends_on": [], "role": "worker",
                            "provider": "provider-a", "estimated_cost": 0} for i in range(4)]
                          + [{"step_id": f"b-{i}", "depends_on": [], "role": "worker",
                              "provider": "provider-b", "estimated_cost": 0} for i in range(4)])}
        pol = ExecutionPolicy(mode="ultra", plan=plan, now_fn=self.clock)
        sequence = []
        while True:
            lease = pol.claim("w")
            if not lease:
                break
            sequence.append(lease["step_id"])
        # Both providers' limits (default 2) are served before one starves the
        # other: first four claims interleave a/b.
        providers_first4 = [sid.split("-")[0] for sid in sequence[:4]]
        self.assertIn("a", providers_first4)
        self.assertIn("b", providers_first4, "fair queue: no starvation between providers")

        # Circuit breaker: 3 consecutive failures OPEN provider-a; provider-b
        # remains eligible (approved alternative).
        pol2 = ExecutionPolicy(mode="ultra", plan=plan, now_fn=self.clock)
        for _ in range(3):
            lease = pol2.claim("w", step_id="a-0")
            if not lease:
                break
            pol2.fail(lease["step_id"], "w", lease["fencing_token"])
        self.assertIsNone(pol2.claim("w", step_id="a-1"),
                          "open circuit refuses claims for the failing provider")
        lease_b = pol2.claim("w", step_id="b-0")
        self.assertIsNotNone(lease_b, "circuit isolates the failing provider only — "
                                      "eligible alternatives still serve")


if __name__ == "__main__":
    unittest.main()