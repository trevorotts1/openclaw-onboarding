"""governor.py -- one per-provider rate governor for every outbound call. [FIX 14]

Contract (published for W01/W07/W09 concurrent build):

    from presentation_job import governor

    lease = governor.acquire("kie", n=1, timeout_s=30.0)   # blocks until admitted
    try:
        ...outbound call...
        governor.report_ok("kie")                          # success telemetry
    finally:
        governor.release(lease)                            # frees the in-flight slot
    # on HTTP 429:
    governor.report_429("kie")                             # halves rate for 60 s

Per provider config lives in ``presentation_job/providers.yaml``::

    kie:
      rps: 2.0                 # sustained submits per second
      burst: 20                # token-bucket capacity (rolling 10 s window cap)
      max_inflight: 100        # concurrent acquisitions ceiling
      daily_cap: 2000          # acquisitions per UTC day (0 = unlimited)
      poll_counts_toward_rps: false   # poll GETs may bypass the rate bucket
    defaults:                  # fallback for unknown providers
      rps: 1.0
      burst: 10
      max_inflight: 50
      daily_cap: 0
      poll_counts_toward_rps: true

The governor reads the resource profile for the plan tier when present
(``ollama-cloud`` plan tiers: $20/month -> 3, $100/month -> 10, read from
``resource_profile.json`` -- the same store capacity.py gates dispatch on),
else uses the YAML defaults.  Every acquisition is appended to a
rolling-window log (``working/governor_log.jsonl`` next to the run dir, or
``/tmp/presentation_governor.log`` when there is no run dir) -- the proof
surface for FIX 14/23: no rolling 10-second window with more than 20
acquisitions and ``max_inflight <= 100``.

[W09-B2] report_429 halving is enforced twice so it is real in both senses:
the refill rate halves (rate_scale) AND the hard 10 s window ceiling scales
down with it (burst * rate_scale) -- the halved kie window admits at most 10
per 10 s for the next 60 s.  The token backlog decays to the scaled burst on
report_429 so a stored surplus cannot pay for a pre-penalty burst.  The plan
tier comes from the resource profile via PLAN_TIER_RPS; the profile also
provides max_inflight when it records a concurrency_ceiling.

Thread-safe: one module-level lock guards all state.  100% stdlib, yaml parsed
by a tiny built-in loader so the module never imports PyYAML.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

__all__ = [
    "Lease",
    "GovernorTimeout",
    "acquire",
    "release",
    "report_429",
    "report_ok",
    "snapshot",
    "window_counts",
    "max_inflight_seen",
    "provider_config",
    "reload_config",
    "set_log_path",
    "log_path",
    "PLAN_TIER_RPS",
]

# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------

CONFIG_PATH = Path(__file__).resolve().parent / "providers.yaml"

# Plan-tier overrides read from the resource profile when present.
# [FIX 14] "the governor reads the resource profile for plan tier (ollama 3/10)"
# The per-tier rates now live in PLAN_TIER_RPS below (near the profile
# reader) keyed by the profile's own plan_tier strings; the old per-provider
# PLAN_TIERS map was removed -- see W09-B2.

_DEFAULTS = {
    "rps": 1.0,
    "burst": 10,
    "max_inflight": 50,
    "daily_cap": 0,
    "poll_counts_toward_rps": True,
}

_config_lock = threading.Lock()
_config_cache: Dict[str, dict] = {}
_config_mtime: float = -1.0

# --------------------------------------------------------------------------
# tiny YAML subset loader (no PyYAML dependency)
# --------------------------------------------------------------------------


def _parse_scalar(tok: str):
    tok = tok.strip()
    if tok.startswith("[") and tok.endswith("]"):
        inner = tok[1:-1].strip()
        return [_parse_scalar(x) for x in inner.split(",")] if inner else []
    if len(tok) >= 2 and tok[0] == tok[-1] and tok[0] in "'\"":
        return tok[1:-1]
    low = tok.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in ("null", "~", ""):
        return None
    try:
        return int(tok)
    except ValueError:
        pass
    try:
        return float(tok)
    except ValueError:
        pass
    return tok


def _load_yaml_subset(text: str) -> dict:
    """Parse the block-mapping subset used by providers.yaml (2-space indents)."""
    root: dict = {}
    stack: list = [(-1, root)]  # (indent, container)
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        body = line.strip()
        if ":" not in body:
            continue
        key, _, rest = body.partition(":")
        key = key.strip()
        rest = rest.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            stack.append((-1, root))
        parent = stack[-1][1]
        if rest == "":
            child: dict = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(rest)
    return root


# --------------------------------------------------------------------------
# resource profile (plan tier) -- best effort, never fatal
# --------------------------------------------------------------------------
# [FIX 14 / W09-B2] The plan tier comes from THE resource profile store
# (presentation_job.resource_profile), the same ask-once record capacity.py
# gates dispatch on -- schema: providers.<provider>.plan_tier in
# {"$20/month", "$100/month", null}.  The ollama-cloud tiers map onto the
# Part 7 ceilings: $20/month -> 3 concurrent, $100/month -> 10.  Everything
# is best-effort: an absent flag, store, provider or plan leaves the YAML
# config untouched.  This module never writes the profile and never prints
# any value from it (providers and plan tiers only -- no credentials).

def _resource_profile_path() -> Optional[Path]:
    """Resolve the profile store the same way resource_profile.py does:
    explicit $PRESENTATION_RESOURCE_PROFILE_DIR, then
    $PRESENTATION_CAPACITY_CONFIG_DIR (the shared config dir), then the
    secrets-adjacent default ~/.openclaw/state/presentation/ (oc_paths when
    importable, for the /data/.openclaw docker root)."""
    # The documented rollback flag (resource_profile.FLAG_ENV) selects the
    # no-profile path for the whole capability; the governor honours it here
    # too so a flag-disabled box falls back to the YAML defaults [W09-B2].
    if os.environ.get("PRESENTATION_RESOURCE_PROFILE") == "0":
        return None
    try:
        from . import resource_profile as _rp  # package-relative (python3 -m)
    except ImportError:  # pragma: no cover - direct file run
        try:
            from presentation_job import resource_profile as _rp
        except ImportError:
            _rp = None
    if _rp is not None:
        try:
            if not _rp.flag_enabled():
                return None
            return _rp.profile_path()
        except Exception:
            pass  # fall through to the manual candidates below
    for env in ("PRESENTATION_RESOURCE_PROFILE_DIR",
                "PRESENTATION_CAPACITY_CONFIG_DIR"):
        p = os.environ.get(env)
        if p:
            cand = Path(p).expanduser() / "resource_profile.json"
            if cand.is_file():
                return cand
            return None  # an operator redirect is authoritative: do not probe on
    home = Path(os.path.expanduser("~"))
    for cand in (
        home / ".openclaw" / "state" / "presentation" / "resource_profile.json",
        Path("/data/.openclaw/state/presentation/resource_profile.json"),
    ):
        if cand.is_file():
            return cand
    return None


def _profile_provider_entry(data: dict, provider: str) -> Optional[dict]:
    """Find the provider's entry in a loaded profile document, tolerating
    both raw and normalized provider ids via capacity.normalize_provider."""
    providers = data.get("providers") if isinstance(data, dict) else None
    if not isinstance(providers, dict):
        return None
    entry = providers.get(provider)
    if isinstance(entry, dict):
        return entry
    norm = None
    try:
        from . import capacity as _cap
    except ImportError:  # pragma: no cover
        try:
            from presentation_job import capacity as _cap
        except ImportError:
            _cap = None
    if _cap is not None:
        norm = _cap.normalize_provider(provider)
    if norm:
        entry = providers.get(norm)
        if isinstance(entry, dict):
            return entry
    return None


#: (plan_tier value from the profile) -> rps override.  [FIX 14] "the
#: governor reads the resource profile for plan tier (ollama 3/10)" -- the
#: same numbers as capacity.CAP_TABLE rows for ollama-cloud.
PLAN_TIER_RPS: Dict[str, float] = {
    "$20/month": 3.0,
    "$100/month": 10.0,
    "20": 3.0,
    "100": 10.0,
    "3": 3.0,
    "10": 10.0,
}


def _plan_tier_rps(provider: str) -> Optional[float]:
    """Return an rps override from the resource profile plan tier, or None.

    Reads the profile ONCE per call, tolerates any store error (the governor
    must never fail a call because the profile is absent or broken), and
    maps the plan tier onto the Part 7 rate via PLAN_TIER_RPS.  A provider
    whose entry carries an explicit concurrency ceiling uses that number as
    rps ceiling too when it looks like a tier rate (3 or 10)."""
    try:
        path = _resource_profile_path()
        if path is None:
            return None
        import json as _json
        data = _json.loads(path.read_text(encoding="utf-8"))
        entry = _profile_provider_entry(data, provider)
        if not entry:
            return None
        tier = entry.get("plan_tier") or entry.get("plan")
        if isinstance(tier, str):
            hit = PLAN_TIER_RPS.get(tier.strip())
            if hit is not None:
                return hit
            digits = "".join(ch for ch in tier if ch.isdigit())
            if digits in PLAN_TIER_RPS:
                return PLAN_TIER_RPS[digits]
        # explicit ceiling recorded by the profile (cap-table projection)
        ceiling = entry.get("concurrency_ceiling")
        if isinstance(ceiling, (int, float)) and float(ceiling) in (3.0, 10.0):
            return float(ceiling)
    except Exception:
        return None
    return None


def _plan_tier_inflight(provider: str) -> Optional[int]:
    """Return the plan tier's concurrency ceiling (3 or 10) from the resource
    profile, or None.  [FIX 14] the profile -- not a hand constant -- decides
    the ollama-cloud in-flight ceiling, matching capacity.CAP_TABLE."""
    try:
        path = _resource_profile_path()
        if path is None:
            return None
        import json as _json
        data = _json.loads(path.read_text(encoding="utf-8"))
        entry = _profile_provider_entry(data, provider)
        if not entry:
            return None
        ceiling = entry.get("concurrency_ceiling")
        if isinstance(ceiling, (int, float)) and float(ceiling) in (3.0, 10.0):
            return int(ceiling)
        tier = entry.get("plan_tier") or entry.get("plan")
        if isinstance(tier, str):
            hit = PLAN_TIER_RPS.get(tier.strip())
            if hit is not None:
                return int(hit)
            digits = "".join(ch for ch in tier if ch.isdigit())
            if digits in PLAN_TIER_RPS:
                return int(PLAN_TIER_RPS[digits])
    except Exception:
        return None
    return None


# --------------------------------------------------------------------------
# config access
# --------------------------------------------------------------------------


#: Canonical provider ids (capacity.py's) and the yaml aliases that carry
#: their config, so `governor.acquire("ollama-cloud")` finds the `ollama`
#: row and `deepseek-direct` finds `deepseek` [W09-B2].
PROVIDER_ALIASES: Dict[str, str] = {
    "ollama-cloud": "ollama",
    "ollamacloud": "ollama",
    "deepseek-direct": "deepseek",
    "deepseek": "deepseek",
    "openrouter": "openrouter",
    "kie": "kie",
}


def _config_for(provider: str) -> dict:
    """YAML body for *provider*, following PROVIDER_ALIASES when the exact
    id is absent (and trying capacity.normalize_provider as a last resort)."""
    table = _load_config()
    body = table.get(provider)
    if isinstance(body, dict):
        return body
    alias = PROVIDER_ALIASES.get(provider)
    if alias:
        body = table.get(alias)
        if isinstance(body, dict):
            return body
    try:
        from . import capacity as _cap
    except ImportError:  # pragma: no cover
        try:
            from presentation_job import capacity as _cap
        except ImportError:
            _cap = None
    if _cap is not None:
        norm = _cap.normalize_provider(provider)
        if norm:
            alias = PROVIDER_ALIASES.get(norm, norm)
            body = table.get(alias)
            if isinstance(body, dict):
                return body
            body = table.get(norm)
            if isinstance(body, dict):
                return body
    return {}


def _load_config() -> Dict[str, dict]:
    global _config_mtime, _config_cache
    with _config_lock:
        try:
            mtime = CONFIG_PATH.stat().st_mtime if CONFIG_PATH.is_file() else -1.0
        except OSError:
            mtime = -1.0
        if mtime != _config_mtime or not _config_cache:
            cfg: Dict[str, dict] = {}
            if CONFIG_PATH.is_file():
                try:
                    parsed = _load_yaml_subset(
                        CONFIG_PATH.read_text(encoding="utf-8")
                    )
                    for name, body in parsed.items():
                        if isinstance(body, dict):
                            cfg[name] = dict(body)
                except Exception:
                    cfg = {}
            _config_cache = cfg
            _config_mtime = mtime
        return _config_cache


def provider_config(provider: str) -> dict:
    """Effective config for *provider* (YAML merged with profile plan tier).

    [FIX 14 / W09-B2] The plan-tier read comes from THE resource profile
    (resource_profile.py's store, providers.<id>.plan_tier): an ollama-cloud
    $20/month account gets rps 3, $100/month gets rps 10 -- the Part 7
    ceilings, via PLAN_TIER_RPS.  The tier also sets max_inflight to the
    same number when the profile records a concurrency_ceiling, so the
    concurrent-agent ceiling and the governor's in-flight cap never disagree.
    A profile that is absent, flag-disabled, unreadable or silent about the
    provider changes nothing (the YAML values stand)."""
    cfg = dict(_DEFAULTS)
    cfg.update(_load_config().get("defaults") or {})
    body = _config_for(provider)
    if isinstance(body, dict):
        cfg.update(body)
    tier_rps = _plan_tier_rps(provider)
    if tier_rps is not None:
        cfg["rps"] = tier_rps
        # keep burst >= the tier rate so a full window is still possible
        cfg["burst"] = max(int(cfg.get("burst") or 0), int(tier_rps))
    tier_inflight = _plan_tier_inflight(provider)
    if tier_inflight is not None:
        cfg["max_inflight"] = tier_inflight
    return cfg


def reload_config() -> None:
    """Force a re-read of providers.yaml (tests / hot config)."""
    global _config_mtime
    with _config_lock:
        _config_mtime = -1.0
    _load_config()


# --------------------------------------------------------------------------
# state
# --------------------------------------------------------------------------


@dataclass
class _ProviderState:
    tokens: float = 0.0
    last_refill: float = 0.0
    inflight: int = 0
    max_inflight_seen: int = 0
    rate_scale: float = 1.0          # report_429 halves this for 60 s
    rate_scale_until: float = 0.0    # wall-clock epoch
    day: str = ""
    day_count: int = 0
    events: list = field(default_factory=list)  # (ts, kind, n) acquisitions


#: [W09-B4] Slack added to the 10 s window the admission check counts over.
#: Two admissions exactly 10.000 s apart sit in the same CLOSED 10-second
#: window, so counting over [now - 10, now] can let a 21st admission through
#: a window a closed-window log scan would flag.  The check therefore counts
#: over [now - 10 - WINDOW_MARGIN, now] so every closed 10 s window is a
#: strict subset of a counted window and "no rolling 10-second window with
#: more than 20 acquisitions" holds under every window convention.
WINDOW_MARGIN: float = 0.25


def _prune_events(st: _ProviderState, now: float, window_s: float = 10.0) -> None:
    """Drop window events older than *window_s* (bounded memory).

    [W09-B4] Events are kept over a widened window (WINDOW_MARGIN slack) so
    the closed-window log scan used for the FIX 14/23 proof sees the same
    picture the admission check used."""
    cutoff = now - window_s
    if st.events:
        i = 0
        n = len(st.events)
        while i < n and st.events[i][0] < cutoff:
            i += 1
        if i:
            del st.events[:i]
    if len(st.events) > 4000:  # bounded memory
        del st.events[:len(st.events) - 2000]


def _window_acquires(st: _ProviderState, now: float,
                     window_s: float = 10.0) -> int:
    """Sum of *n* over admitted acquisitions inside the trailing *window_s*.

    [W09-B4] Widened by WINDOW_MARGIN so it strictly contains every closed
    10-second window (any two admissions exactly WINDOW_S apart cannot both
    sit inside a counted window).  Caller holds the governor lock."""
    cutoff = now - (window_s + WINDOW_MARGIN)
    return sum(
        e[2] for e in st.events
        if e[1] == "acquire" and e[0] > cutoff
    )


@dataclass
class Lease:
    """Handle returned by :func:`acquire`; pass to :func:`release`."""

    provider: str
    n: int
    poll: bool
    acquired_at: float
    seq: int
    released: bool = False
    _state: Optional[_ProviderState] = None  # type: ignore[assignment]


_lock = threading.RLock()  # reentrant: acquire() logs while holding the lock
_state: Dict[str, _ProviderState] = {}
_seq = 0

_log_path_override: Optional[str] = None


def set_log_path(path: str) -> None:
    """Redirect the acquisition log (used by the selftest / engine)."""
    global _log_path_override
    with _lock:
        _log_path_override = path


def log_path() -> str:
    """Where the rolling-window acquisition log lives."""
    with _lock:
        if _log_path_override:
            return _log_path_override
    run_dir = os.environ.get("PRESENTATION_RUN_DIR")
    if run_dir:
        return str(Path(run_dir) / "working" / "governor_log.jsonl")
    return "/tmp/presentation_governor.log"


def _state_for(provider: str) -> _ProviderState:
    st = _state.get(provider)
    if st is None:
        st = _ProviderState()
        _state[provider] = st
    return st


def _utc_day() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


# --------------------------------------------------------------------------
# logging (the proof surface)
# --------------------------------------------------------------------------


def _append_log(provider: str, kind: str, n: int, inflight: int,
                ok: bool = True) -> None:
    rec = {
        "ts": time.time(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z",
        "provider": provider,
        "event": kind,
        "n": n,
        "inflight": inflight,
        "ok": ok,
    }
    try:
        path = Path(log_path())
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception:
        pass  # logging must never break the call path


# --------------------------------------------------------------------------
# window accounting
# --------------------------------------------------------------------------


def window_counts(provider: str, window_s: float = 10.0,
                  now: Optional[float] = None) -> int:
    """Acquisition events for *provider* inside the trailing window."""
    now = now if now is not None else time.time()
    with _lock:
        st = _state_for(provider)
        cutoff = now - window_s
        st.events = [e for e in st.events if e[0] >= cutoff]
        return sum(e[2] for e in st.events if e[1] == "acquire")


def max_inflight_seen(provider: Optional[str] = None) -> int:
    """Peak concurrent in-flight acquisitions (whole governor or per provider)."""
    with _lock:
        if provider is None:
            return max(
                (st.max_inflight_seen for st in _state.values()), default=0
            )
        return _state_for(provider).max_inflight_seen


def snapshot() -> dict:
    """Diagnostics: per-provider tokens, inflight, scale, day count."""
    now = time.time()
    with _lock:
        out = {}
        for name, st in _state.items():
            out[name] = {
                "tokens": round(st.tokens, 3),
                "inflight": st.inflight,
                "max_inflight_seen": st.max_inflight_seen,
                "rate_scale": st.rate_scale,
                "rate_scale_remaining_s": max(
                    0.0, st.rate_scale_until - now
                ),
                "day": st.day,
                "day_count": st.day_count,
                "window_10s": sum(
                    e[2] for e in st.events
                    if e[1] == "acquire" and e[0] >= now - 10.0
                ),
            }
        return out


# --------------------------------------------------------------------------
# core: acquire / release
# --------------------------------------------------------------------------


def acquire(
    provider: str,
    n: int = 1,
    timeout_s: Optional[float] = None,
    poll: bool = False,
) -> Lease:
    """Block until *n* rate tokens, an in-flight slot and daily capacity exist.

    Returns a :class:`Lease` -- every lease MUST be passed to
    :func:`release` (``try/finally``).  ``poll=True`` marks a poll GET, which
    bypasses the rate bucket when ``poll_counts_toward_rps`` is false but
    still respects ``max_inflight`` and ``daily_cap``.
    Raises :class:`GovernorTimeout` when *timeout_s* elapses first.
    """
    if n < 1:
        n = 1
    cfg = provider_config(provider)
    deadline = None if timeout_s is None else time.monotonic() + timeout_s
    global _seq
    while True:
        with _lock:
            st = _state_for(provider)
            now = time.time()
            # daily cap reset
            today = _utc_day()
            if st.day != today:
                st.day = today
                st.day_count = 0
            daily_ok = cfg["daily_cap"] <= 0 or st.day_count + n <= cfg["daily_cap"]
            if not daily_ok:
                raise GovernorTimeout(
                    f"governor: daily_cap {cfg['daily_cap']} reached for {provider}"
                )
            # rate scale expiry (report_429 halving lasts 60 s)
            if now >= st.rate_scale_until:
                st.rate_scale = 1.0
            rps = max(0.01, float(cfg["rps"]) * st.rate_scale)
            if st.last_refill <= 0.0:
                st.last_refill = now
            capacity = float(cfg["burst"])
            st.tokens = min(capacity, st.tokens + (now - st.last_refill) * rps)
            st.last_refill = now
            poll_ok = poll and not cfg["poll_counts_toward_rps"]
            rate_ok = poll_ok or st.tokens >= n
            # HARD 10 s window ceiling: no rolling 10-second window may hold
            # more than `burst` admissions (the FIX 14/23 proof bound), even
            # when refill would allow a 21st token inside the same window.
            # The ceiling follows the scaled rate: during a report_429
            # penalty the effective ceiling is burst * rate_scale, so a
            # halved provider admits at most half per window for the next
            # 60 s ("the next 60 seconds admit at most 10 per window").
            if not poll_ok:
                window_cap = max(1.0, round(capacity * st.rate_scale))
                window_n = _window_acquires(st, now, 10.0)
                rate_ok = rate_ok and (window_n + n) <= window_cap
            inflight_ok = st.inflight + n <= int(cfg["max_inflight"])
            if rate_ok and inflight_ok:
                if not poll_ok:
                    st.tokens -= n
                st.inflight += n
                st.day_count += n
                st.max_inflight_seen = max(st.max_inflight_seen, st.inflight)
                # poll admissions bypassing the rate bucket are logged as
                # their own event kind so they never consume the 10 s window
                # budget that poll_counts_toward_rps=False promises to spare.
                st.events.append((now, "acquire_poll" if poll_ok else "acquire", n))
                if len(st.events) > 4000:  # bounded memory
                    st.events = st.events[-2000:]
                _seq += 1
                lease = Lease(
                    provider=provider,
                    n=n,
                    poll=bool(poll),
                    acquired_at=now,
                    seq=_seq,
                    _state=st,
                )
                _append_log(provider, "acquire_poll" if poll_ok else "acquire", n, st.inflight)
                return lease
        # not admitted -- sleep a tick proportional to the deficit
        if deadline is not None and time.monotonic() >= deadline:
            raise GovernorTimeout(
                f"governor: acquire({provider!r}, n={n}) timed out "
                f"after {timeout_s}s"
            )
        with _lock:
            st = _state_for(provider)
            deficit = max(0.0, n - st.tokens)
        wait = max(0.01, min(0.25, deficit / max(0.01, float(cfg["rps"]))))
        time.sleep(wait)


class GovernorTimeout(TimeoutError):
    """Raised by :func:`acquire` when the timeout elapses or the daily cap
    is exhausted."""


def release(lease: Optional[Lease]) -> None:
    """Free the in-flight slot held by *lease*.  Idempotent."""
    if lease is None or lease.released:
        return
    with _lock:
        lease.released = True
        st = lease._state or _state_for(lease.provider)
        st.inflight = max(0, st.inflight - lease.n)
        st.events.append((time.time(), "release", lease.n))
        inflight = st.inflight
    _append_log(lease.provider, "release", lease.n, inflight)


# --------------------------------------------------------------------------
# telemetry: 429 / ok
# --------------------------------------------------------------------------


def report_429(provider: str) -> float:
    """Provider answered 429: halve the refill rate for the next 60 s.

    [FIX 14 / W09-B2] "a forced 429 halves the next minute's rate."  The
    halving applies to the REFILL RATE from this instant: the accumulated
    token balance decays to the halved burst so a stored backlog cannot pay
    for a burst of submissions at the old pace inside the penalty minute.
    Repeated 429s inside the window re-halve (floor 1/32 of base).  Returns
    the applied scale so callers/tests can assert it.
    """
    with _lock:
        st = _state_for(provider)
        now = time.time()
        if now < st.rate_scale_until:
            st.rate_scale = max(1.0 / 32.0, st.rate_scale / 2.0)
        else:
            st.rate_scale = 0.5
        st.rate_scale_until = now + 60.0
        # Token backlog decays under the penalty: a 429 must not leave the
        # bucket able to admit a full burst at the pre-429 pace.
        try:
            burst = float(provider_config(provider).get("burst") or 10)
        except Exception:
            burst = 10.0
        st.tokens = min(st.tokens, max(1.0, burst * st.rate_scale))
        st.last_refill = now
        scale = st.rate_scale
        st.events.append((now, "report_429", 0))
        inflight = st.inflight
    _append_log(provider, "report_429", 0, inflight)
    return scale


def report_ok(provider: str) -> None:
    """Call succeeded; recover the rate scale faster than the 60 s expiry.

    [FIX 14 / W09-B2] The scaled rate and the scaled window ceiling recover
    together so recovery is observable in the same place the penalty is."""
    with _lock:
        st = _state_for(provider)
        now = time.time()
        if st.rate_scale < 1.0:
            st.rate_scale = min(1.0, st.rate_scale * 2.0)
            if st.rate_scale >= 1.0:
                st.rate_scale_until = 0.0
        st.events.append((now, "report_ok", 0))


# --------------------------------------------------------------------------
# --selftest (W09-B4): the FIX 14 proof, runnable end to end.
#
#   python3 -m presentation_job.governor --selftest --provider kie --submits 100
#
# Phase 1 ("burst"): admits *submits* acquisitions as hard as it can
# (parallel workers, all released at the end) and PASSes iff the rolling
# window log never shows more than `burst` acquisitions in any closed
# 10-second window and max_inflight <= max_inflight from config.
# Phase 2 ("penalty"): forces a report_429 and PASSes iff the following
# 60 seconds admit at most `burst / 2` per window (the halved ceiling).
# The window log lives at the path `--log` (default /tmp) so the proof
# surface is inspectable after the run.  Exit 0 = PASS, 2 = FAIL, 3 = usage.
# --------------------------------------------------------------------------


def _selftest_window_max(path: str, window_s: float = 10.0,
                         since: Optional[float] = None,
                         until: Optional[float] = None,
                         provider: Optional[str] = None) -> int:
    """Max acquisitions in any closed window_s window, scanned from the log.

    ``since``/``until`` bound the scan (e.g. the 429 moment and its 60 s
    penalty expiry) so a penalty phase never counts pre-penalty burst admits
    inside its windows nor post-expiry full-rate admits; ``provider`` narrows
    the events.  Closed-window convention: pairs up to exactly ``window_s``
    apart share a window, the strictest reading of "no rolling 10-second
    window with more than N acquisitions"."""
    ts = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if rec.get("event") != "acquire":
                    continue
                if provider and rec.get("provider") != provider:
                    continue
                t = float(rec["ts"])
                if since is not None and t <= since:
                    continue
                if until is not None and t > until:
                    continue
                ts.append(t)
    except OSError:
        return 0
    ts.sort()
    best = 0
    for i in range(len(ts)):
        j = i
        while j < len(ts) and ts[j] - ts[i] <= window_s:
            j += 1
        if j - i > best:
            best = j - i
    return best


def _selftest_last_429_ts(path: str, provider: str) -> Optional[float]:
    """Timestamp of the last report_429 row for *provider* in the log, or None."""
    last = None
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                if (rec.get("event") == "report_429"
                        and rec.get("provider") == provider):
                    last = float(rec["ts"])
    except OSError:
        pass
    return last


def _selftest_phase1(provider: str, submits: int, timeout_s: float,
                     log_path_: str) -> dict:
    """Admit *submits* acquisitions in parallel; report window/inflight proof.

    [B4] The window scan is seeded by a START row written BEFORE the first
    worker is spawned and bounded by since=start_ts, so rows from anything
    else writing to the same log path (a concurrent live run on the shared
    /tmp path) can never inflate the count: the scan counts only acquisitions
    this phase emitted after its own start timestamp."""
    import threading
    leases: list = []
    errors: list = []
    start_ts = time.time()
    _append_log(f"selftest-start", "phase1_start", 0, 0)
    # One barrier party per thread: a party-count mismatch strands threads on
    # gate.wait() (BrokenBarrierError after its 10 s timeout, which then
    # shows up as spurious errors and halves the admission count).
    gate = threading.Barrier(submits)
    start = time.time()

    def worker() -> None:
        try:
            gate.wait(timeout=timeout_s)
            leases.append(acquire(provider, n=1, timeout_s=timeout_s))
        except Exception as exc:  # GovernorTimeout included
            errors.append(str(exc))

    threads = [threading.Thread(target=worker) for _ in range(submits)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    acquired = len(leases)
    peak = max_inflight_seen(provider)
    for l in leases:
        release(l)
    window_max = _selftest_window_max(log_path_, since=start_ts,
                                      provider=provider)
    cfg = provider_config(provider)
    ok = (
        acquired == submits
        and not errors
        and window_max <= int(cfg["burst"])
        and peak <= int(cfg["max_inflight"])
    )
    return {
        "phase": "burst",
        "ok": ok,
        "submits": submits,
        "acquired": acquired,
        "errors": errors[:3],
        "window_10s_max": window_max,
        "burst": int(cfg["burst"]),
        "max_inflight_seen": peak,
        "max_inflight": int(cfg["max_inflight"]),
        "elapsed_s": round(time.time() - start, 2),
    }


def _selftest_phase2(provider: str, timeout_s: float, log_path_: str) -> dict:
    """Force report_429, then prove the next 60 s admit at most burst/2 per
    10 s window.  Uses the live governor process state (same module), so the
    penalty is the same one a real caller would see.  The window scan starts
    at the 429 row and ends at the penalty expiry (429 ts + 60 s) so neither
    pre-penalty burst admits nor post-expiry full-rate admits pollute the
    penalty windows; the gate is the per-window ceiling (burst * scale),
    which is exactly what QC FIX 14 asserts ("at most 10 per window")."""
    cfg = provider_config(provider)
    start = time.time()
    scale = report_429(provider)
    since = _selftest_last_429_ts(log_path_, provider)
    until = (since + 60.0) if since is not None else None
    admits = 0
    leases = []
    # Drain until the penalty decays (64 s covers the 60 s window) so the
    # admits counted are the ones the penalty actually admits.
    while time.time() - start < 64.0:
        try:
            leases.append(acquire(provider, n=1, timeout_s=10.0))
            admits += 1
        except GovernorTimeout:
            break
    for l in leases:
        release(l)
    window_max = _selftest_window_max(log_path_, provider=provider,
                                      since=since, until=until)
    cap = max(1.0, round(float(cfg["burst"]) * scale))
    ok = window_max <= cap
    return {
        "phase": "penalty",
        "ok": ok,
        "scale": scale,
        "penalty_window_s": 60.0,
        "admitted_60s": admits,
        "admit_cap_per_window": int(cap),
        "window_10s_max_post_429": window_max,
        "elapsed_s": round(time.time() - start, 2),
    }


def _selftest_default_log() -> str:
    """Default selftest log: pid-unique under /tmp so two selftests (or a
    selftest and a live run) can never interleave rows in one file.

    [B4 / wave-1 critic] The shared ``/tmp/presentation_governor.log`` mixed
    rows from concurrent processes and a window scan over it showed 57
    acquisitions in one 10 s window while the governor itself admitted 20 --
    the proof instrument was polluted, not the limiter. A pid-unique path
    makes every selftest scan self-consistent by construction."""
    return f"/tmp/presentation_governor.{os.getpid()}.log"


def _main(argv: list) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        prog="python3 -m presentation_job.governor",
        description="Per-provider rate governor selftest (FIX 14 proof).",
    )
    ap.add_argument("--selftest", action="store_true",
                    help="run the FIX 14 selftest (burst + penalty phases)")
    ap.add_argument("--provider", default="kie",
                    help="provider to exercise (default kie)")
    ap.add_argument("--submits", type=int, default=100,
                    help="acquisitions for the burst phase (default 100)")
    ap.add_argument("--timeout", type=float, default=120.0,
                    help="per-acquire timeout in seconds")
    ap.add_argument("--log", default=None,
                    help="window log path (default: pid-unique /tmp path so "
                         "concurrent runs never share rows)")
    args = ap.parse_args(argv)
    if not args.selftest:
        ap.print_help()
        return 3
    if args.submits < 1:
        print(json.dumps({"ok": False, "error": "submits must be >= 1"}))
        return 3
    log = args.log or _selftest_default_log()
    set_log_path(log)
    if os.path.exists(log):
        try:
            os.remove(log)
        except OSError:
            pass
    report = {"selftest": True, "provider": args.provider}
    p1 = _selftest_phase1(args.provider, args.submits, args.timeout, log)
    report["phase1"] = p1
    p2 = None
    if p1["ok"]:
        p2 = _selftest_phase2(args.provider, args.timeout, log)
        report["phase2"] = p2
    else:
        report["phase2"] = {"phase": "penalty", "ok": False,
                            "skipped": "phase1 failed", "window_10s_max": 0,
                            "admitted_60s": 0, "scale": 0.0,
                            "elapsed_s": 0.0}
    report["ok"] = p1["ok"] and (p2 is not None and p2["ok"])
    print(json.dumps(report, indent=1))
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
