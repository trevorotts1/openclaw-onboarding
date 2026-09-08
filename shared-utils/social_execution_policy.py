#!/usr/bin/env python3
"""social_execution_policy.py — Standard/Ultra execution policy with
dependency-aware swarm management (F33, social-planner-september-eighth/WF05).

This is the ONB half of the contract; CC's src/lib/jobs/social-orchestrator.ts
implements the SAME contract in TypeScript for Command-Central execution. Both
halves read the policy the same way so a plan approved on one side schedules
identically on the other.

WHAT THIS OWNS
  * Modes: STANDARD and ULTRA (client-approved; never silently upgraded).
  * Per-provider semaphores read from the APPROVED PLAN — Ollama Cloud
    documents 3 concurrent requests on Pro and 10 on Max [F33 S9]; an unknown
    provider quota degrades to a CONSERVATIVE DEFAULT of 2, never to infinity.
  * APPLICATION Ultra ceiling: 50 simultaneous worker EXECUTIONS (product
    policy — NOT the implementation-swarm agent limit).
  * Dependency-wave scheduling over a DAG of steps
    ({"step_id","depends_on":[],"role","provider","estimated_cost"}): only
    ready independent work launches; approval/dependent renders/publication
    stay ordered.
  * Atomic leases per the W0 dispatch.json contract: operation_key unique,
    integer fencing_token, lease_expires_at, heartbeat, retry_at. A stale
    worker cannot commit after reassignment (fencing token mismatch refuses).
  * Fair queue across provider accounts: round-robin per provider, so one
    account cannot starve another.
  * Budget reservation per cycle with settle: a step's estimated_cost is
    reserved at claim and SETTLED (deducted) or RELEASED on completion; a
    reservation that would exceed the cycle cap is refused, not overspent.
  * 429/Retry-After honoring: a 429 parks the provider (or step) until the
    Retry-After instant, refusing claims instead of hammering.
  * Circuit breaker: a provider that fails too fast trips OPEN and stops
    issuing leases while eligible branches use approved alternatives.

STDLIB ONLY. Deterministic: no wall-clock dependence a test cannot inject
(now_fn injectable). No network. No secrets.

PYTHON 3.9+: no dataclass slots kwarg, no match statements.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections import deque
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

# ── Product policy constants ────────────────────────────────────────────────
STANDARD_MODE = "standard"
ULTRA_MODE = "ultra"

#: APPLICATION ceiling on simultaneous worker EXECUTIONS in Ultra mode
#: (product policy — NOT the implementation-swarm limit).
ULTRA_APP_CEILING = 50

#: Conservative default concurrent-claim ceiling for a provider whose quota is
#: unknown. Never infinity; unknown quota means BE MORE CAREFUL, not less.
UNKNOWN_PROVIDER_QUOTA_DEFAULT = 2

#: Documented Ollama Cloud concurrency (F33 S9): Pro=3, Max=10.
OLLAMA_CLOUD_PLAN_LIMITS = {"pro": 3, "max": 10}

#: Circuit breaker: OPEN after this many consecutive failures on a provider.
CIRCUIT_FAILURE_THRESHOLD = 3

#: 429 handling: honor Retry-After seconds (bounded), else this default.
RATE_LIMIT_DEFAULT_RETRY_SECONDS = 30.0
RATE_LIMIT_MAX_RETRY_SECONDS = 3600.0

# ── Step schema ─────────────────────────────────────────────────────────────

def validate_step(step: Any) -> Dict[str, Any]:
    """Validate one DAG step; raises ValueError on a malformed step.

    Schema: {"step_id": str, "depends_on": [str], "role": str,
             "provider": str, "model": str?, "estimated_cost": float?}
    """
    if not isinstance(step, dict) or not step.get("step_id"):
        raise ValueError("step must be an object with a step_id")
    deps = step.get("depends_on") or []
    if not isinstance(deps, list) or any(not isinstance(d, str) for d in deps):
        raise ValueError("depends_on must be a list of step ids")
    return {
        "step_id": str(step["step_id"]),
        "depends_on": [str(d) for d in deps],
        "role": str(step.get("role") or "worker"),
        "provider": str(step.get("provider") or ""),
        "model": step.get("model"),
        "estimated_cost": float(step.get("estimated_cost") or 0.0),
    }


def validate_plan(steps: Iterable[Any]) -> List[Dict[str, Any]]:
    """Validate a whole plan; raises ValueError on malformed steps or cycles."""
    validated = [validate_step(s) for s in steps]
    ids = {s["step_id"] for s in validated}
    for s in validated:
        for dep in s["depends_on"]:
            if dep not in ids:
                raise ValueError(f"step {s['step_id']} depends on unknown step {dep}")
    # Cycle check (Kahn) — a cycle is un-schedulable, fail loudly.
    indegree = {s["step_id"]: 0 for s in validated}
    dependents: Dict[str, List[str]] = {s["step_id"]: [] for s in validated}
    for s in validated:
        for dep in s["depends_on"]:
            indegree[s["step_id"]] += 1
            dependents[dep].append(s["step_id"])
    queue = deque(sorted(sid for sid, deg in indegree.items() if deg == 0))
    seen = 0
    while queue:
        sid = queue.popleft()
        seen += 1
        for nxt in dependents[sid]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    if seen != len(validated):
        raise ValueError("plan contains a dependency cycle")
    return validated


# ── Provider plan resolution ────────────────────────────────────────────────

def provider_limit(provider: str, plan: Optional[Dict[str, Any]] = None) -> int:
    """Concurrent-request ceiling for a provider, read from the APPROVED PLAN
    when it carries one; else the documented Ollama Cloud plan limits; else
    the conservative default. Never returns a value below 1."""
    key = (provider or "").strip().lower()
    if not key:
        return UNKNOWN_PROVIDER_QUOTA_DEFAULT
    plan_providers = (plan or {}).get("providers") or {}
    if isinstance(plan_providers, dict):
        entry = plan_providers.get(key)
        if isinstance(entry, dict) and entry.get("concurrency"):
            try:
                return max(1, int(entry["concurrency"]))
            except (TypeError, ValueError):
                pass
    if key.startswith("ollama"):
        plan_name = str((plan or {}).get("ollama_plan") or os.environ.get("OLLAMA_PLAN") or "").strip().lower()
        if plan_name in OLLAMA_CLOUD_PLAN_LIMITS:
            return OLLAMA_CLOUD_PLAN_LIMITS[plan_name]
        # Ollama without a known plan: conservative, not unlimited.
        return UNKNOWN_PROVIDER_QUOTA_DEFAULT
    return UNKNOWN_PROVIDER_QUOTA_DEFAULT


def application_ceiling(mode: str) -> int:
    """Simultaneous worker executions allowed for the mode."""
    if (mode or "").strip().lower() == ULTRA_MODE:
        return ULTRA_APP_CEILING
    return 1


# ── The scheduler ───────────────────────────────────────────────────────────

class ExecutionPolicy:
    """Deterministic wave scheduler + lease authority for one cycle's DAG.

    All timing flows through ``now_fn`` (default: time.time) so tests inject a
    fake clock. Thread-safe via a lock — the CC/worker halves may call from
    multiple threads.
    """

    def __init__(
        self,
        mode: str = STANDARD_MODE,
        plan: Optional[Dict[str, Any]] = None,
        now_fn: Optional[Callable[[], float]] = None,
        budget_cap: float = 0.0,
        clock_scale: float = 1.0,
    ) -> None:
        self.mode = (mode or STANDARD_MODE).strip().lower()
        self.plan = plan or {}
        self.now_fn = now_fn or (lambda: _time())
        self.budget_cap = float(budget_cap or (self.plan or {}).get("cycle_budget_cap") or 0.0)
        self.clock_scale = float(clock_scale or 1.0)
        self._lock = threading.Lock()
        self._steps: Dict[str, Dict[str, Any]] = {}
        self._state: Dict[str, str] = {}          # step_id -> pending|ready|running|done|failed|blocked
        self._leases: Dict[str, Dict[str, Any]] = {}  # step_id -> lease
        self._provider_active: Dict[str, int] = {}
        self._provider_rr: Dict[str, int] = {}    # fair-queue round-robin cursor
        self._provider_penalty_until: Dict[str, float] = {}  # 429 Retry-After
        self._circuit_failures: Dict[str, int] = {}
        self._circuit_open_until: Dict[str, float] = {}
        self._budget_reserved = 0.0
        self._fencing = 0
        for raw in self.plan.get("steps") or []:
            step = validate_step(raw)
            self._steps[step["step_id"]] = step
            self._state[step["step_id"]] = "pending"

    # -- time helpers -------------------------------------------------------
    def _now(self) -> float:
        return self.now_fn()

    def _scaled(self, seconds: float) -> float:
        """Backoff windows scaled for tests (clock_scale < 1 shrinks waits)."""
        return max(0.0, seconds) * self.clock_scale

    # -- public reads -------------------------------------------------------
    @property
    def steps(self) -> List[Dict[str, Any]]:
        return [self._steps[sid] for sid in sorted(self._steps)]

    def status(self) -> Dict[str, Any]:
        """busy/waiting/queued counts + per-provider active usage."""
        with self._lock:
            states = list(self._state.values())
            return {
                "mode": self.mode,
                "busy": states.count("running"),
                "waiting": states.count("ready"),
                "queued": states.count("pending") + states.count("blocked"),
                "done": states.count("done"),
                "failed": states.count("failed"),
                "providers": dict(self._provider_active),
                "budget_reserved": round(self._budget_reserved, 6),
                "budget_cap": self.budget_cap,
            }

    # -- scheduling core ----------------------------------------------------
    def _deps_satisfied(self, step: Dict[str, Any]) -> bool:
        return all(self._state.get(dep) == "done" for dep in step["depends_on"])

    def _provider_available(self, provider: str) -> bool:
        now = self._now()
        if self._provider_active.get(provider, 0) >= provider_limit(provider, self.plan):
            return False
        if now < self._provider_penalty_until.get(provider, 0.0):
            return False
        if now < self._circuit_open_until.get(provider, 0.0):
            return False
        return True

    def _next_ready(self) -> Optional[str]:
        """Fair-queue pick: pending steps whose deps are done, ordered by
        provider round-robin so one provider's backlog cannot starve another's."""
        now = self._now()
        candidates = []
        for sid, step in self._steps.items():
            if self._state.get(sid) not in ("pending", "blocked", "ready"):
                continue
            lease = self._leases.get(sid)
            if lease and lease["lease_expires_at"] > now and not lease.get("expired"):
                continue  # live lease — not claimable
            if not self._deps_satisfied(step):
                continue
            if self.budget_cap > 0 and self._budget_reserved + step["estimated_cost"] > self._budget_cap:
                continue  # budget reservation would exceed the cap — stay queued
            if not self._provider_available(step["provider"]):
                continue
            candidates.append(sid)
        if not candidates:
            return None
        # Round-robin across providers: prefer the provider with the LEAST
        # recent issue (fair queue), tie-break on step order for determinism.
        def fair_key(sid: str) -> Tuple[int, int, str]:
            provider = self._steps[sid]["provider"]
            cursor = self._provider_rr.get(provider, 0)
            self._provider_rr[provider] = cursor  # read-only here
            return (cursor, sorted(candidates).index(sid), sid)
        return min(candidates, key=lambda sid: (self._provider_rr.get(self._steps[sid]["provider"], 0), sorted(candidates).index(sid), sid))

    # -- leases (dispatch.json contract) ------------------------------------
    def claim(self, worker_id: str, *, step_id: Optional[str] = None,
              operation_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Atomically claim one ready step. Returns the lease (with a fresh
        fencing token) or None when nothing is claimable — limits reached,
        dependency waves not yet satisfied, provider saturated/penalized, or
        budget exhausted. Ceiling enforcement order: application ceiling,
        provider semaphore, budget reservation."""
        with self._lock:
            now = self._now()
            # Application ceiling (Ultra 50 / Standard 1) — useful work only.
            running = sum(1 for st in self._state.values() if st == "running")
            if running >= application_ceiling(self.mode):
                return None
            sid = step_id or self._next_ready()
            if not sid or sid not in self._steps:
                return None
            step = self._steps[sid]
            if not self._deps_satisfied(step) or not self._provider_available(step["provider"]):
                return None
            if self.budget_cap > 0 and self._budget_reserved + step["estimated_cost"] > self.budget_cap:
                return None
            self._fencing += 1
            lease = {
                "operation_key": operation_key or self.operation_key(sid),
                "worker_id": worker_id,
                "step_id": sid,
                "attempt": int(self._leases.get(sid, {}).get("attempt", 0)) + 1,
                "fencing_token": self._fencing,
                "lease_expires_at": now + self._scaled(120.0),
                "heartbeat_at": now,
                "retry_at": None,
            }
            self._leases[sid] = lease
            self._state[sid] = "running"
            self._provider_active[step["provider"]] = self._provider_active.get(step["provider"], 0) + 1
            self._provider_rr[step["provider"]] = self._provider_rr.get(step["provider"], 0) + 1
            self._budget_reserved += step["estimated_cost"]
            return dict(lease)

    def heartbeat(self, step_id: str, worker_id: str, fencing_token: int) -> bool:
        """Extend a live lease. False when the lease was lost (reassigned)."""
        with self._lock:
            lease = self._leases.get(step_id)
            if not lease or lease["worker_id"] != worker_id \
                    or lease["fencing_token"] != fencing_token:
                return False
            lease["heartbeat_at"] = self._now()
            lease["lease_expires_at"] = self._now() + self._scaled(120.0)
            return True

    def _release(self, sid: str, state: str) -> None:
        lease = self._leases.pop(sid, None)
        step = self._steps.get(sid)
        if lease and step:
            self._provider_active[step["provider"]] = max(
                0, self._provider_active.get(step["provider"], 1) - 1)
            self._budget_reserved = max(0.0, self._budget_reserved - step["estimated_cost"])
        self._state[sid] = state

    def settle(self, step_id: str, worker_id: str, fencing_token: int, *,
               output_summary: str = "") -> bool:
        """Commit a completed step (deduct its cost — reserve → settle)."""
        with self._lock:
            lease = self._leases.get(step_id)
            if not lease or lease["worker_id"] != worker_id \
                    or lease["fencing_token"] != fencing_token:
                return False  # stale worker cannot commit after reassignment
            self._release(step_id, "done")
            return True

    def fail(self, step_id: str, worker_id: str, fencing_token: int, *,
             reason: str = "", rate_limited: bool = False,
             retry_after_seconds: Optional[float] = None,
             permanent: bool = False) -> bool:
        """Record a failed attempt. Handles 429/Retry-After and circuit
        breaking; requeues with backoff unless permanent or the attempt cap
        was reached."""
        with self._lock:
            lease = self._leases.get(step_id)
            if not lease or lease["worker_id"] != worker_id \
                    or lease["fencing_token"] != fencing_token:
                return False
            step = self._steps[step_id]
            provider = step["provider"]
            attempt = lease["attempt"]
            self._release(step_id, "pending")  # provisional; state set below
            now = self._now()
            if rate_limited:
                wait = retry_after_seconds if retry_after_seconds is not None \
                    else RATE_LIMIT_DEFAULT_RETRY_SECONDS
                wait = min(wait, RATE_LIMIT_MAX_RETRY_SECONDS)
                self._provider_penalty_until[provider] = now + self._scaled(wait)
            else:
                self._circuit_failures[provider] = self._circuit_failures.get(provider, 0) + 1
                if self._circuit_failures.get(provider, 0) >= CIRCUIT_FAILURE_THRESHOLD:
                    self._circuit_open_until[provider] = now + self._scaled(300.0)
            max_attempts = int(self.plan.get("max_attempts_per_step") or 3)
            if permanent or attempt >= max_attempts:
                self._state[step_id] = "failed"
            else:
                self._state[step_id] = "blocked"  # waiting on retry window
                self._blocked_retry_at = getattr(self, "_blocked_retry_at", {})
                self._blocked_retry_at[step_id] = now + self._scaled(30.0 * attempt)
            return True

    def retry_blocked(self) -> int:
        """Promote blocked steps whose retry window elapsed back to ready."""
        with self._lock:
            now = self._now()
            promoted = 0
            for sid, retry_at in getattr(self, "_blocked_retry_at", {}).items():
                if self._state.get(sid) == "blocked" and now >= retry_at:
                    self._state[sid] = "pending"
                    promoted += 1
            return promoted

    def recover_expired(self) -> int:
        """Reclaim leases whose holder died (worker death recovery). The
        expired lease is released and the step re-enters the ready pool —
        WITHOUT duplicate side effects, because the fencing token increments
        and the previous holder's commit is refused on token mismatch."""
        with self._lock:
            now = self._now()
            recovered = 0
            for sid, lease in list(self._leases.items()):
                if lease["lease_expires_at"] <= now:
                    self._release(sid, "pending")
                    recovered += 1
            return recovered

    def complete_dependency(self, step_id: str) -> bool:
        """Mark an externally-executed step done (adapter seam for the wave
        runner). Used by Skills 35/57 entry adapters to feed real outcomes."""
        with self._lock:
            if step_id not in self._steps:
                return False
            if self._state.get(step_id) == "running":
                self._release(step_id, "done")
            else:
                self._state[step_id] = "done"
            return True

    # -- helpers ------------------------------------------------------------
    def operation_key(self, step_id: str) -> str:
        """Unique operation identity for one step execution attempt
        (dispatch.json: operation_key unique)."""
        lease = self._leases.get(step_id) or {}
        raw = f"{self.plan.get('cycle_id', 'cycle')}:{step_id}:{lease.get('attempt', 0)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:24]

    def waves(self) -> List[List[str]]:
        """Deterministic dependency waves (topological tiers) — independent
        copy/media may run together; approval/dependent renders/publication
        stay ordered. Read-only; never mutates state."""
        with self._lock:
            remaining = {sid: set(step["depends_on"]) for sid, step in self._steps.items()}
            waves: List[List[str]] = []
            placed: set = set()
            while remaining:
                tier = sorted(sid for sid, deps in remaining.items() if deps <= placed)
                if not tier:
                    break  # cycle (validate_plan already rejects; defensive)
                waves.append(tier)
                placed.update(tier)
                for sid in tier:
                    remaining.pop(sid)
            return waves

    def ready_steps(self) -> List[str]:
        """Every launchable step right now (deps done, leaseable, provider
        not saturated) — the Ultra worker pool reads this to fill its
        application ceiling with USEFUL work only."""
        with self._lock:
            out = []
            for sid in sorted(self._steps):
                step = self._steps[sid]
                if self._state.get(sid) not in ("pending", "blocked", "ready"):
                    continue
                if self._deps_satisfied(step) and self._provider_available(step["provider"]):
                    out.append(sid)
            return out


def _time() -> float:
    import time
    return time.time()


def load_policy(path: str) -> Dict[str, Any]:
    """Load an approved policy JSON (mode + plan) from disk. Raises ValueError
    on malformed plans; the caller decides mode approval, this never upgrades."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    mode = str(data.get("mode") or STANDARD_MODE)
    plan = data.get("plan") or {}
    validate_plan(plan.get("steps") or [])
    return {"mode": mode, "plan": plan}


if __name__ == "__main__":  # pragma: no cover — tiny self-check
    demo = {
        "mode": "ultra",
        "cycle_budget_cap": 10.0,
        "providers": {"ollama-cloud": {"concurrency": 3}},
        "steps": [
            {"step_id": "copy-a", "depends_on": [], "role": "writer",
             "provider": "ollama-cloud", "estimated_cost": 0.5},
            {"step_id": "copy-b", "depends_on": [], "role": "writer",
             "provider": "openrouter", "estimated_cost": 0.5},
            {"step_id": "qc", "depends_on": ["copy-a", "copy-b"], "role": "qc",
             "provider": "ollama-cloud", "estimated_cost": 0.25},
        ],
    }
    policy = ExecutionPolicy(mode=demo["mode"], plan=demo)
    print(json.dumps(policy.waves()))
    print(json.dumps(policy.status()))