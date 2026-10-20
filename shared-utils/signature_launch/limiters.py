#!/usr/bin/env python3
"""Signature Launch limiters: the four budgets a launch swarm must respect.

Owner: launch automation swarm (WF-SWARM / WF-LAUNCHERS). Stdlib only, no
network, no secrets, deterministic (every clock is injectable).

  KieLimiter         20 createTask starts per 10 s per KIE account. Retries
                     take tokens too. State is persisted and file-locked so
                     every runner on the box shares one budget.
  SpendCap           hard money ceiling in integer minor units. A reservation
                     is taken BEFORE dispatch; the dispatch is refused, not
                     overspent, when it would cross the cap. Unknown prices
                     block. A corrupt state file fails closed.
  GhlBuildThrottle   GHL build writes: <=100 requests/minute, >=6 s between
                     saves, >=15 s between publishes, and a global cooldown
                     after HTTP 429 (Retry-After honoured). Shared across
                     processes through the same state-file lock.
  ModelConcurrency   the model ceiling: the harness maxConcurrent minus one,
                     clamped by the provider's documented concurrency, and a
                     cross-process slot gate so workers never exceed it.

External constants and where they come from:
  - KIE 20 starts / 10 s per account: https://docs.kie.ai/ Section 8
    (verified 2026-06-14; restated in 67-kie-video/references/api-patterns.md:157
    and 71-blackceo-signature-page/references/swarm-plan.md "The limiter rule").
  - GHL ~100 requests/minute: 05-ghl-setup/INSTRUCTIONS.md:173.
  - GHL save 6 s / publish 15 s / 429 cooldown 30 s: mirrors
    06-ghl-install-pages/tools/v2_dispatcher.py RateGovernor, which mirrors
    gates.json::rate_limit_governor.
  - Ollama Cloud Pro 3 / Max 10 concurrent: shared-utils/social_execution_policy.py
    OLLAMA_CLOUD_PLAN_LIMITS (F33 S9). Unknown provider quota degrades to 2,
    never to infinity (same file: UNKNOWN_PROVIDER_QUOTA_DEFAULT).
  - OpenClaw maxConcurrent keys: agents.defaults.subagents.maxConcurrent and
    agents.defaults.maxConcurrent, plus .capacity-profile.json
    maxConcurrentAgents (same reader as 75-drama-song-ad-factory/scripts/core/
    lane_size.py: read_maxconcurrent).

Fail-closed doctrine: a state file that exists but cannot be parsed raises
LimiterStateError. It is never silently reset to empty, because an empty
budget means "spend freely" and an empty grant list means "burst freely".

Usage:
    kie = KieLimiter("/data/locks/kie-account.json")
    kie.acquire()                       # blocks until a start slot exists

    cap = SpendCap("/data/locks/spend.json", ceiling_minor=50_000)
    cap.reserve("image-01", 250)        # refuses over the ceiling
    cap.commit("image-01", 238)

    ghl = GhlBuildThrottle("/data/locks/ghl.json")
    ghl.before("save")
    ghl.note_429(retry_after_header)

    limit = model_concurrency(openclaw_config="/root/.openclaw/config",
                              provider="ollama-cloud", ollama_plan=20)["agents"]
    gate = ModelConcurrencyGate("/data/locks/model-slots.json", limit=limit)
    gate.acquire("worker-3")
"""
from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

__all__ = [
    "LimiterStateError",
    "LimitExceeded",
    "SpendCapExceeded",
    "UnknownPrice",
    "KieLimiter",
    "SpendCap",
    "GhlBuildThrottle",
    "ModelConcurrencyGate",
    "model_concurrency",
    "OLLAMA_CLOUD_PLAN_LIMITS",
    "UNKNOWN_PROVIDER_QUOTA_DEFAULT",
]

#: Documented Ollama Cloud concurrency. Mirrors shared-utils/social_execution_policy.py.
OLLAMA_CLOUD_PLAN_LIMITS = {20: 3, 100: 10}

#: Unknown provider quota is 2, never infinity (social_execution_policy.py).
UNKNOWN_PROVIDER_QUOTA_DEFAULT = 2

#: Providers with no provider-level concurrency ceiling in this repo's doctrine.
NO_CAP_PROVIDERS = frozenset({"openrouter", "deepseek-direct", "anthropic"})

MAXCONCURRENT_DOTTED_KEYS = (
    "agents.defaults.subagents.maxConcurrent",
    "agents.defaults.maxConcurrent",
)


class LimiterStateError(RuntimeError):
    """State exists but cannot be trusted. Fail closed; never spend around it."""


class LimitExceeded(RuntimeError):
    """A budget refused the request."""


class SpendCapExceeded(LimitExceeded):
    """The reservation would cross the hard money ceiling."""


class UnknownPrice(LimitExceeded):
    """No price is known, so no dispatch is authorized."""


class _SystemClock:
    def now(self):
        return time.time()

    def sleep(self, seconds):
        time.sleep(seconds)


def _clock(clock):
    return clock if clock is not None else _SystemClock()


def _read_state(path, empty):
    """Read one JSON object state file. Missing -> empty(). Unreadable -> raise."""
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return empty()
    except OSError as exc:
        raise LimiterStateError(f"cannot read limiter state {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise LimiterStateError(f"corrupt limiter state {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise LimiterStateError(f"corrupt limiter state {path}: not an object")
    return data


def _write_state(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")


class _FileLock:
    """Cross-process exclusive lock. Breaks only locks older than ``stale_s``."""

    def __init__(self, path, clock, timeout_s=120.0, stale_s=120.0):
        self.path = Path(str(path) + ".lock")
        self.clock = clock
        self.timeout_s = timeout_s
        self.stale_s = stale_s

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        deadline = self.clock.now() + self.timeout_s
        while True:
            try:
                fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return self
            except FileExistsError:
                try:
                    age = time.time() - self.path.stat().st_mtime
                    if age > self.stale_s:
                        self.path.unlink()
                        continue
                except FileNotFoundError:
                    continue
                if self.clock.now() > deadline:
                    raise TimeoutError(f"limiter lock held >{self.timeout_s}s: {self.path}")
                self.clock.sleep(0.05)

    def __exit__(self, *_exc):
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass
        return False


class KieLimiter:
    """20 createTask starts per 10 seconds per KIE account, shared and persisted."""

    LIMIT = 20
    WINDOW = 10.0

    def __init__(self, state_path, clock=None, limit=None, window=None):
        self.path = Path(state_path)
        self.clock = _clock(clock)
        self.limit = int(limit if limit is not None else self.LIMIT)
        self.window = float(window if window is not None else self.WINDOW)
        if self.limit < 1 or self.window <= 0:
            raise ValueError("limit must be >= 1 and window > 0")

    def _grants(self):
        data = _read_state(self.path, lambda: {"grants": []})
        grants = data.get("grants", [])
        if not isinstance(grants, list):
            raise LimiterStateError(f"corrupt limiter state {self.path}: grants not a list")
        try:
            return [float(g) for g in grants]
        except (TypeError, ValueError) as exc:
            raise LimiterStateError(f"corrupt limiter state {self.path}: bad grant") from exc

    def _prune(self, grants, now):
        return [g for g in grants if now - g < self.window]

    def try_acquire(self):
        """Take one start slot now. False means the window is full."""
        lock = _FileLock(self.path, self.clock)
        with lock:
            now = self.clock.now()
            grants = self._prune(self._grants(), now)
            if len(grants) >= self.limit:
                return False
            grants.append(now)
            _write_state(self.path, {"grants": grants})
            return True

    def acquire(self, timeout_s=None):
        """Block until a slot is granted; return seconds waited.

        Raises TimeoutError when ``timeout_s`` is given and expires.
        """
        start = self.clock.now()
        while True:
            if self.try_acquire():
                return self.clock.now() - start
            remaining = None if timeout_s is None else timeout_s - (self.clock.now() - start)
            if remaining is not None and remaining <= 0:
                raise TimeoutError(f"kie limiter: no slot within {timeout_s}s")
            with _FileLock(self.path, self.clock):
                grants = self._prune(self._grants(), self.clock.now())
                wait = (grants[0] + self.window - self.clock.now()) if grants else self.window
            if remaining is not None:
                wait = min(wait, remaining)
            self.clock.sleep(max(0.01, wait))


class SpendCap:
    """Hard money ceiling in integer minor units, reserved before dispatch."""

    def __init__(self, state_path, ceiling_minor, currency="USD", clock=None):
        if isinstance(ceiling_minor, bool) or not isinstance(ceiling_minor, int):
            raise ValueError("ceiling_minor must be an integer (minor units)")
        if ceiling_minor < 0:
            raise ValueError("ceiling_minor must be >= 0")
        self.path = Path(state_path)
        self.ceiling_minor = ceiling_minor
        self.currency = str(currency)
        self.clock = _clock(clock)
        if self.path.exists():  # fail fast on a foreign or corrupt ledger
            with _FileLock(self.path, self.clock):
                self._load()

    def _load(self):
        state = _read_state(self.path, lambda: {
            "ceiling_minor": self.ceiling_minor,
            "currency": self.currency,
            "spent_minor": 0,
            "entries": {},
        })
        if state.get("ceiling_minor") != self.ceiling_minor:
            raise LimiterStateError(
                f"spend cap mismatch at {self.path}: state ceiling "
                f"{state.get('ceiling_minor')!r} != {self.ceiling_minor!r}")
        if state.get("currency") != self.currency:
            raise LimiterStateError(
                f"spend cap mismatch at {self.path}: state currency "
                f"{state.get('currency')!r} != {self.currency!r}")
        spent = state.get("spent_minor")
        entries = state.get("entries")
        if isinstance(spent, bool) or not isinstance(spent, int) or spent < 0:
            raise LimiterStateError(f"corrupt limiter state {self.path}: spent_minor")
        if not isinstance(entries, dict):
            raise LimiterStateError(f"corrupt limiter state {self.path}: entries")
        reserved = 0
        for key, entry in entries.items():
            amount = entry.get("amount_minor") if isinstance(entry, dict) else None
            if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
                raise LimiterStateError(
                    f"corrupt limiter state {self.path}: entry {key!r}")
            reserved += amount
        return state, spent, reserved

    def _save(self, state):
        _write_state(self.path, state)

    def reserve(self, key, amount_minor):
        """Reserve ``amount_minor`` for ``key`` or refuse. Returns the reservation."""
        if not isinstance(key, str) or not key:
            raise ValueError("key must be a non-empty string")
        if amount_minor is None:
            raise UnknownPrice(f"no known price for {key!r}: dispatch is blocked")
        if isinstance(amount_minor, bool) or not isinstance(amount_minor, int):
            raise ValueError("amount_minor must be an integer (minor units)")
        if amount_minor < 0:
            raise ValueError("amount_minor must be >= 0")
        with _FileLock(self.path, self.clock):
            state, spent, reserved = self._load()
            entries = state["entries"]
            if key in entries:
                raise LimiterStateError(f"{key!r} is already reserved; no double reserve")
            if spent + reserved + amount_minor > self.ceiling_minor:
                raise SpendCapExceeded(
                    f"reserving {amount_minor} for {key!r} would cross the cap "
                    f"(spent {spent} + reserved {reserved} + {amount_minor} > "
                    f"{self.ceiling_minor} {self.currency})")
            entries[key] = {"amount_minor": amount_minor, "state": "reserved"}
            self._save(state)
            return amount_minor

    def commit(self, key, actual_minor=None):
        """Settle a reservation. A higher actual cost must still fit the cap."""
        with _FileLock(self.path, self.clock):
            state, spent, reserved = self._load()
            entry = state["entries"].get(key)
            if entry is None:
                raise LimiterStateError(f"{key!r} has no reservation to commit")
            amount = entry["amount_minor"]
            actual = amount if actual_minor is None else actual_minor
            if isinstance(actual, bool) or not isinstance(actual, int) or actual < 0:
                raise ValueError("actual_minor must be an integer (minor units)")
            others = reserved - amount
            if spent + others + actual > self.ceiling_minor:
                raise SpendCapExceeded(
                    f"settling {key!r} at {actual} would cross the cap "
                    f"(spent {spent} + other reservations {others} + {actual} > "
                    f"{self.ceiling_minor} {self.currency})")
            del state["entries"][key]
            state["spent_minor"] = spent + actual
            self._save(state)
            return actual

    def release(self, key):
        """Drop a reservation without spending. Idempotent."""
        with _FileLock(self.path, self.clock):
            state, _spent, _reserved = self._load()
            if state["entries"].pop(key, None) is not None:
                self._save(state)

    def remaining_minor(self):
        with _FileLock(self.path, self.clock):
            _state, spent, reserved = self._load()
            return max(0, self.ceiling_minor - spent - reserved)

    def snapshot(self):
        with _FileLock(self.path, self.clock):
            state, spent, reserved = self._load()
            return {
                "ceiling_minor": self.ceiling_minor,
                "currency": self.currency,
                "spent_minor": spent,
                "reserved_minor": reserved,
                "remaining_minor": max(0, self.ceiling_minor - spent - reserved),
                "entries": dict(state["entries"]),
            }


class GhlBuildThrottle:
    """GHL build pace: 100 req/min, save >=6 s, publish >=15 s, 429 cooldown."""

    REQUESTS_PER_MINUTE = 100
    WINDOW = 60.0
    MIN_SAVE_INTERVAL_S = 6.0
    MIN_PUBLISH_INTERVAL_S = 15.0
    DEFAULT_429_COOLDOWN_S = 30.0

    def __init__(self, state_path, clock=None, save_interval_s=None,
                 publish_interval_s=None, cooldown_s=None,
                 requests_per_minute=None, stale_s=120.0):
        self.path = Path(state_path)
        self.clock = _clock(clock)
        self.save_interval_s = float(
            self.MIN_SAVE_INTERVAL_S if save_interval_s is None else save_interval_s)
        self.publish_interval_s = float(
            self.MIN_PUBLISH_INTERVAL_S if publish_interval_s is None else publish_interval_s)
        self.default_429_cooldown_s = float(
            self.DEFAULT_429_COOLDOWN_S if cooldown_s is None else cooldown_s)
        self.requests_per_minute = int(
            self.REQUESTS_PER_MINUTE if requests_per_minute is None else requests_per_minute)
        self.stale_s = float(stale_s)

    def _empty(self):
        return {"last": {}, "requests": [], "cooldown_until": 0.0}

    def _load(self):
        state = _read_state(self.path, self._empty)
        last = state.get("last", {})
        requests = state.get("requests", [])
        cooldown = state.get("cooldown_until", 0.0)
        if not isinstance(last, dict) or not isinstance(requests, list):
            raise LimiterStateError(f"corrupt limiter state {self.path}")
        try:
            last = {str(k): float(v) for k, v in last.items()}
            requests = [float(r) for r in requests]
            cooldown = float(cooldown)
        except (TypeError, ValueError) as exc:
            raise LimiterStateError(f"corrupt limiter state {self.path}") from exc
        return {"last": last, "requests": requests, "cooldown_until": cooldown}

    def _interval(self, action):
        if action == "save":
            return self.save_interval_s
        if action == "publish":
            return self.publish_interval_s
        if action not in (None, "request"):
            raise ValueError(f"unknown GHL action {action!r}")
        return 0.0

    def available_in(self, action=None):
        """Seconds before ``action`` is allowed. Does not sleep or record."""
        interval = self._interval(action)
        now = self.clock.now()
        state = self._load()
        waits = [state["cooldown_until"] - now]
        if action in ("save", "publish") and action in state["last"]:
            waits.append(state["last"][action] + interval - now)
        window = [r for r in state["requests"] if now - r < self.WINDOW]
        if len(window) >= self.requests_per_minute:
            waits.append(window[0] + self.WINDOW - now)
        return max(0.0, max(waits))

    def before(self, action=None):
        """Block until ``action`` is allowed; return seconds waited."""
        interval = self._interval(action)
        wait = self.available_in(action)
        if wait > 0:
            self.clock.sleep(wait)
        with _FileLock(self.path, self.clock):
            now = self.clock.now()
            state = self._load()
            state["requests"] = [r for r in state["requests"] if now - r < self.WINDOW]
            state["requests"].append(now)
            if action in ("save", "publish"):
                state["last"][action] = now
            _write_state(self.path, state)
        return wait

    def note_429(self, retry_after=None):
        """Apply a global cooldown. Accepts the raw Retry-After header value."""
        cooldown = self.default_429_cooldown_s
        if retry_after is not None:
            try:
                cooldown = max(cooldown, float(retry_after))
            except (TypeError, ValueError):
                pass
        with _FileLock(self.path, self.clock):
            state = self._load()
            until = self.clock.now() + cooldown
            state["cooldown_until"] = max(state["cooldown_until"], until)
            _write_state(self.path, state)
        return cooldown


def _dig(obj, dotted):
    cur = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _profile_cap(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = data.get("maxConcurrentAgents") if isinstance(data, dict) else None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    return value


def _read_maxconcurrent(openclaw_config=None, profile_dir=None):
    """maxConcurrent keys from the OpenClaw config and capacity profiles."""
    keys = {}
    if openclaw_config:
        try:
            cfg = json.loads(Path(openclaw_config).read_text(encoding="utf-8"))
            for dotted in MAXCONCURRENT_DOTTED_KEYS:
                value = _dig(cfg, dotted)
                if isinstance(value, bool):
                    continue
                if isinstance(value, (int, float)) and value > 0:
                    keys[dotted] = value
        except (OSError, ValueError):
            keys["config-read-error"] = str(openclaw_config)
        profile = Path(openclaw_config).resolve().parent / ".capacity-profile.json"
        got = _profile_cap(profile)
        if got is not None:
            keys["profile"] = got
    if profile_dir:
        got = _profile_cap(Path(profile_dir) / ".capacity-profile.json")
        if got is not None:
            keys["profile"] = got
    return keys


def model_concurrency(openclaw_config=None, profile_dir=None, provider=None,
                      ollama_plan=None):
    """Resolve the model concurrency ceiling and the evidence behind it.

    Runtime ceiling = floor(min(maxConcurrent keys)) - 1 (one slot is always
    left for the operator). Provider ceiling follows doctrine: Ollama Cloud
    plan map, no ceiling for providers this repo treats as uncapped, and the
    conservative 2 for any other named provider. ``agents`` is None only when
    no ceiling is knowable at all -- never silently "unlimited".
    """
    keys = _read_maxconcurrent(openclaw_config, profile_dir)
    caps = [v for v in keys.values() if isinstance(v, (int, float)) and not isinstance(v, bool)]
    runtime_cap = max(0, math.floor(min(caps)) - 1) if caps else None

    provider_cap = None
    name = str(provider).strip().lower() if provider else ""
    if name:
        if name in NO_CAP_PROVIDERS:
            provider_cap = None
        elif name == "ollama-cloud":
            plan = int(ollama_plan) if ollama_plan else 20
            provider_cap = OLLAMA_CLOUD_PLAN_LIMITS.get(
                plan, OLLAMA_CLOUD_PLAN_LIMITS[20])
        else:
            provider_cap = UNKNOWN_PROVIDER_QUOTA_DEFAULT

    known = [c for c in (runtime_cap, provider_cap) if c is not None]
    agents = max(1, min(known)) if known else None
    return {
        "agents": agents,
        "runtime_cap": runtime_cap,
        "provider_cap": provider_cap,
        "maxconcurrent_keys": keys or None,
        "provider": name or None,
        "ollama_plan": int(ollama_plan) if ollama_plan else None,
    }


class ModelConcurrencyGate:
    """Cross-process slot gate for model workers, with lease expiry."""

    def __init__(self, state_path, limit, lease_ttl_s=900.0, clock=None):
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        self.path = Path(state_path)
        self.limit = limit
        self.lease_ttl_s = float(lease_ttl_s)
        self.clock = _clock(clock)

    def _load(self):
        state = _read_state(self.path, lambda: {"leases": {}})
        leases = state.get("leases")
        if not isinstance(leases, dict):
            raise LimiterStateError(f"corrupt limiter state {self.path}: leases")
        now = self.clock.now()
        live = {}
        for owner, expires in leases.items():
            try:
                expires = float(expires)
            except (TypeError, ValueError) as exc:
                raise LimiterStateError(
                    f"corrupt limiter state {self.path}: lease {owner!r}") from exc
            if expires > now and isinstance(owner, str) and owner:
                live[owner] = expires
        return live

    def active(self):
        with _FileLock(self.path, self.clock):
            return sorted(self._load())

    def try_acquire(self, owner):
        """Take or refresh a slot for ``owner``. False means the gate is full."""
        if not isinstance(owner, str) or not owner:
            raise ValueError("owner must be a non-empty string")
        with _FileLock(self.path, self.clock):
            live = self._load()
            if owner not in live and len(live) >= self.limit:
                return False
            live[owner] = self.clock.now() + self.lease_ttl_s
            _write_state(self.path, {"leases": live})
            return True

    def acquire(self, owner, timeout_s=None):
        """Block until ``owner`` holds a slot; return seconds waited."""
        start = self.clock.now()
        while not self.try_acquire(owner):
            if timeout_s is not None and self.clock.now() - start >= timeout_s:
                raise TimeoutError(f"model concurrency gate full for {owner!r}")
            self.clock.sleep(1.0)
        return self.clock.now() - start

    def release(self, owner):
        """Drop ``owner``'s slot. Idempotent."""
        with _FileLock(self.path, self.clock):
            live = self._load()
            if live.pop(owner, None) is not None:
                _write_state(self.path, {"leases": live})
