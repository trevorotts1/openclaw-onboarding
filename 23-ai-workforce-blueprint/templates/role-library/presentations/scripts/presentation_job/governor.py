"""governor.py -- one per-provider rate governor for every outbound call. [FIX 14]

Contract (published for W01/W07/W09 concurrent build):

    from presentation_job import governor

    lease = governor.acquire("kie", n=1, timeout_s=30.0)   # blocks until admitted
    try:
        ...outbound call...
        governor.report_ok("kie")                          # healthy-sample telemetry
    finally:
        governor.release(lease)                            # frees the in-flight slot
    # on HTTP 429 (pass the response's Retry-After when the provider sent one):
    governor.report_429("kie", retry_after_s=float(hdr))
    # -> multiplicative decrease of the start-rate, penalty for the Retry-After
    #    (default 60 s), recovered only GRADUALLY after a full healthy
    #    observation window with a minimum number of clean samples [PRES-016].
    #    Penalty state persists to a shared circuit document so other
    #    dispatcher processes honor the same cooldown.

Per provider config lives in ``presentation_job/providers.yaml``::

    kie:
      rps: 2.0                 # sustained request-START rate (token refill)
      burst: 20                # start-rate window: max STARTS in a rolling 10 s
      max_inflight: 100        # concurrent in-flight ceiling -- a SEPARATE axis,
                               # never lifts burst [PRES-016]
      daily_cap: 2000          # acquisitions per UTC day (0 = unlimited)
      poll_counts_toward_rps: false   # poll GETs may bypass the rate bucket
    defaults:                  # fallback for unknown providers
      rps: 1.0
      burst: 10
      max_inflight: 50
      daily_cap: 0
      poll_counts_toward_rps: true

The governor reads the resource profile for the plan tier when present
(``ollama-cloud`` plan tiers: $20/month -> 3, $100/month -> 8 -- 8 and not the
raw seat maximum of 10 by operator ruling, see PLAN_TIER_RPS below -- read from
``resource_profile.json``, the same store capacity.py gates dispatch on),
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

[PRES-016] ADAPTIVE RECOVERY -- the three axes are separate facts:
  * concurrent-request axis  -> ``max_inflight`` (and capacity.CAP_TABLE)
  * request-START axis       -> ``rps`` + ``burst`` (the rolling-10s window)
  * spend axis               -> ``daily_cap``
A concurrency ceiling NEVER lifts the start-rate window: provider_config no
longer raises ``burst`` to ``max_inflight`` or the tier rate, so "100
concurrent" can no longer fabricate "100 starts per 10 s".  On a 429 the
start-rate falls MULTIPLICATIVELY (halving, floor 1/32) for the Retry-After
the provider asked for (default 60 s); ``report_ok`` records a healthy sample
but moves the scale by at most ONE ADDITIVE STEP per full healthy observation
window (HEALTHY_WINDOW_S) that carries at least HEALTHY_MIN_SAMPLES clean
responses -- so an old in-flight success arriving right after a 429 cannot
erase the penalty, and mixed 200/429 traffic cannot bounce back to full
speed.  The penalty lives in the shared circuit document
(``governor_circuit.json`` next to the resource profile store) with a
monotonic revision, written under an exclusive file lock; a writer whose
cached base revision is stale is rejected VISIBLY (a ``circuit-stale-revision``
row in the acquisition log) and re-merges from the live document, so every
dispatcher process on the host sees -- and honors -- the same cooldown while
unrelated providers continue unaffected.

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
    "circuit_snapshot",
    "window_counts",
    "max_inflight_seen",
    "provider_config",
    "reload_config",
    "set_log_path",
    "log_path",
    "PLAN_TIER_RPS",
    "HEALTHY_WINDOW_S",
    "HEALTHY_MIN_SAMPLES",
    "SCALE_STEP",
    "SCALE_FLOOR",
    "RETRY_AFTER_CAP_S",
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

# --------------------------------------------------------------------------
# [PRES-016] adaptive-recovery constants
# --------------------------------------------------------------------------

#: A 429 penalty decays only by TIME while nothing healthy is observed; a
#: success may speed recovery by at most ONE additive step per full healthy
#: observation window of this many seconds (measured from the 429 that opened
#: the penalty).
HEALTHY_WINDOW_S: float = 30.0

#: Clean responses required inside one healthy observation window before the
#: additive step is granted.  A single (possibly stale in-flight) success can
#: never satisfy this.
HEALTHY_MIN_SAMPLES: int = 10

#: One additive recovery step.  From the first 429 (scale 0.5) a FULL healthy
#: recovery to 1.0 therefore takes 4 windows -- never one lucky response.
SCALE_STEP: float = 0.125

#: Multiplicative-decrease floor (repeated 429s re-halve, never below this).
SCALE_FLOOR: float = 1.0 / 32.0

#: Default penalty when the provider sent no Retry-After header [W09-B2].
DEFAULT_PENALTY_S: float = 60.0

#: A Retry-After is honored but capped -- a hostile or broken header must not
#: wedge an account's start-rate for a day.
RETRY_AFTER_CAP_S: float = 3600.0

#: Shared circuit document (persisted penalty state), read at most this often
#: by the acquire path so cross-process penalties propagate without turning
#: every admission into an IO round-trip.
_CIRCUIT_SYNC_INTERVAL_S: float = 2.0

#: Bounded CAS retries when persisting the shared circuit document.
_CIRCUIT_PERSIST_RETRIES: int = 5

_config_lock = threading.Lock()
_config_cache: Dict[str, dict] = {}
_config_mtime: float = -1.0

#: [F17] Providers already announced this process as "no providers.yaml row".
#: Its own lock: `_config_lock` is held inside `_load_config`, and `_lock`
#: (the state lock) is held across the whole admission decision in acquire().
_defaults_announced: set = set()
_defaults_announce_lock = threading.Lock()

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
# Part 7 ceilings: $20/month -> 3 concurrent, $100/month -> 8 (the 10-slot
# plan minus the operator's deliberate 2-slot reserve; see PLAN_TIER_RPS,
# which is the number actually applied).  Everything
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
#: governor reads the resource profile for plan tier".
#:
#: These are the SAME numbers as capacity.CAP_TABLE's ollama-cloud rows, and
#: they must stay that way -- capacity.CAP_TABLE is the single source of
#: truth, this map only mirrors it for the two tier spellings the profile
#: can carry.  [U5] The $100 tier is **8, not the raw account maximum of
#: 10**: operator ruling 2026-09-04, restated 2026-09-07 -- "i said 8 so
#: that 2 are left over for other work".  The presentation job takes 8 of
#: the seat's 10 slots on BOTH axes (width and rate), leaving the client 2
#: for whatever else runs on the same Ollama account.  Raising this back to
#: 10 silently spends the operator's reserve.
PLAN_TIER_RPS: Dict[str, float] = {
    "$20/month": 3.0,
    "$100/month": 8.0,
    "20": 3.0,
    "100": 8.0,
    # a profile that records the resolved ceiling itself as the tier
    "3": 3.0,
    "8": 8.0,
    "10": 8.0,   # the 10-slot plan, minus the operator's 2-slot reserve
}


def _plan_tier_rps(provider: str) -> Optional[float]:
    """Return an rps override from the resource profile plan tier, or None.

    Reads the profile ONCE per call, tolerates any store error (the governor
    must never fail a call because the profile is absent or broken), and
    maps the plan tier onto the Part 7 rate via PLAN_TIER_RPS.  A provider
    whose entry carries an explicit concurrency ceiling uses that number as
    rps ceiling too when it IS a tier rate (3 or the reserved 8)."""
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
        # Explicit ceiling recorded by the profile, projected onto a RATE.
        # [U5] This is deliberately narrow: a concurrency ceiling is not an
        # rps, and the two only coincide for the ollama-cloud tiers, where
        # the operator ruling sets both.  So admit a recorded ceiling here
        # only when it IS one of the tier rates -- which now includes the
        # reserved 8 that the old `in (3.0, 10.0)` whitelist discarded (see
        # PLAN_TIER_RPS).  Anything else (DeepSeek's 2500, a measured 47)
        # falls through to providers.yaml rather than becoming an rps.
        ceiling = entry.get("concurrency_ceiling")
        if isinstance(ceiling, (int, float)) and not isinstance(ceiling, bool):
            if float(ceiling) in set(PLAN_TIER_RPS.values()):
                return float(ceiling)
    except Exception:
        return None
    return None


def _plan_tier_inflight(provider: str) -> Optional[int]:
    """Return the plan tier's concurrency ceiling from the resource profile,
    or None.  [FIX 14] the profile -- not a hand constant -- decides the
    ollama-cloud in-flight ceiling, matching capacity.CAP_TABLE.

    [U5] Any positive recorded ceiling is honored, not just the two the
    cap table happened to hold when FIX 14 was written.  A profile that
    records the operator's reserved 8 gets 8; a profile that records a
    measured 47 gets 47.  Previously both fell through to the tier map."""
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
        if isinstance(ceiling, (int, float)) and not isinstance(ceiling, bool):
            if 0 < float(ceiling) < float("inf"):
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
    _announce_defaults_once(provider)
    return {}


def _announce_defaults_once(provider: str) -> None:
    """[F17] Say, ONCE per process, that this provider has no yaml row.

    A provider with no row is governed at `defaults` -- rps 1.0, burst 10,
    max_inflight 50. That is a real throttle on every outbound call, and
    before F17 it happened in complete silence: adopting a model on a new
    provider serialised the whole pipeline at roughly one call per second
    with nothing in any log saying why, and the operator's only clue was the
    wall-clock. The rate itself is NOT invented upward here -- guessing a
    stranger's limit trades a stall for a 429 storm -- so the fix is to make
    the throttle audible and name the row that removes it.

    Announced on the governor's own proof surface (the acquisition log, the
    same file the FIX 14/23 window proof reads) AND on stderr, because the
    log is only read after the fact. Once per provider per process:
    `provider_config` runs on every single acquire."""
    key = str(provider or "")
    with _defaults_announce_lock:
        if key in _defaults_announced:
            return
        _defaults_announced.add(key)
    try:
        rps = (_load_config().get("defaults") or {}).get("rps", _DEFAULTS["rps"])
    except Exception:  # noqa: BLE001 -- an unreadable yaml still gets announced
        rps = _DEFAULTS["rps"]
    msg = (f"provider {key} has no providers.yaml row -- governing at "
           f"defaults rps {rps}; add a row to presentation_job/providers.yaml "
           f"to govern it at its real limits")
    _append_log(key, "config-defaults", 0, 0, ok=True, note=msg)
    try:
        print(f"WARNING: governor: {msg}", file=sys.stderr, flush=True)
    except Exception:  # noqa: BLE001 -- announcing never breaks the call path
        pass


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
    $20/month account gets rps 3, $100/month gets rps 8 -- the Part 7
    ceilings minus the operator's 2-slot reserve [U5], via PLAN_TIER_RPS.  The
    profile's concurrency ceiling also sets max_inflight, so the
    concurrent-agent ceiling and the governor's in-flight cap never disagree.
    A profile that is absent, flag-disabled, unreadable or silent about the
    provider changes nothing (the YAML values stand).

    [PRES-016] THE AXES ARE SEPARATE.  Earlier this function ALSO lifted
    ``burst`` -- first to the tier rate, then to the concurrency ceiling
    ("a width the governor will not admit is not a width", U5) -- which
    conflated the CONCURRENT-REQUEST axis (max_inflight) with the
    REQUEST-START axis (rps + the burst rolling-10s window): a profile that
    recorded 100 concurrent slots silently granted permission to START 100
    requests in one 10-second window.  Concurrency is how many requests may
    be in flight at once; the start-rate is how quickly new ones may begin.
    They are different limits and only the provider's real published or
    measured START rate may widen ``burst`` -- so neither lift remains.  The
    OpenRouter row keeps its operator-declared burst 100 (an explicit
    start-rate declaration, 2026-09-07); every other provider keeps its own
    yaml burst.  ``max_inflight`` and the plan-tier ``rps`` mapping (the
    ollama 3/8-with-2-reserve ruling) are unchanged."""
    cfg = dict(_DEFAULTS)
    cfg.update(_load_config().get("defaults") or {})
    body = _config_for(provider)
    if isinstance(body, dict):
        cfg.update(body)
    tier_rps = _plan_tier_rps(provider)
    if tier_rps is not None:
        cfg["rps"] = tier_rps
    tier_inflight = _plan_tier_inflight(provider)
    if tier_inflight is not None:
        cfg["max_inflight"] = tier_inflight
    return cfg


def reload_config() -> None:
    """Force a re-read of providers.yaml (tests / hot config)."""
    global _config_mtime
    with _config_lock:
        _config_mtime = -1.0
    # [F17] a hot config reload may have ADDED the missing row, so the
    # once-per-process announcement is re-armed with it: the next fallback to
    # `defaults` is a fact about the NEW file and has to be said again.
    with _defaults_announce_lock:
        _defaults_announced.clear()
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
    rate_scale: float = 1.0          # multiplicative start-rate decrease (429)
    rate_scale_until: float = 0.0    # wall-clock epoch the penalty expires
    last_429_ts: float = 0.0         # epoch of the most recent 429 [PRES-016]
    penalty_started: float = 0.0     # epoch the CURRENT penalty opened [PRES-016]
    retry_after_s: float = 0.0       # honored Retry-After, if any [PRES-016]
    ok_samples: list = field(default_factory=list)  # healthy-sample epochs
    day: str = ""
    day_count: int = 0
    day_count_imported: bool = False  # a restart merged the shared count in
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


# --------------------------------------------------------------------------
# [PRES-016] shared circuit document -- penalty state that survives the
# process.  Every dispatcher process on the host (each auto-spawned run owns
# its own process) reads and writes ONE document next to the resource-profile
# store, so a 429 penalty earned by one job cools the SAME account bucket in
# every other job, while unrelated providers are untouched.  Shape:
#
#   {"revision": <monotonic int>, "updated_at": <epoch>,
#    "providers": {"<provider>": {"rate_scale": float, "penalty_until": epoch,
#                                 "penalty_started": epoch, "last_429_ts": epoch,
#                                 "retry_after_s": float, "updated_at": epoch}}}
#
# Writers take an exclusive flock on a sibling .lock file, re-read the live
# document, merge per provider, bump the revision and atomically replace the
# file.  A writer whose cached base revision is behind the live revision is a
# STALE REVISION: its write is rejected VISIBLY (a "circuit-stale-revision"
# row in the acquisition log) and only re-applied when its own event is
# strictly newer than the stored one -- a newer in-flight write from another
# process always wins.  Best-effort end to end: any error degrades to
# in-process-only state and is logged, never raised.
# --------------------------------------------------------------------------

try:
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    _fcntl = None  # type: ignore[assignment]

_CIRCUIT_FILENAME = "governor_circuit.json"
_circuit_lock = threading.Lock()
_circuit_cache: Dict[str, dict] = {}
_circuit_loaded_at: float = 0.0


def _circuit_dir(create: bool) -> Optional[Path]:
    """Where the shared circuit document lives: the resource-profile store's
    directory when it resolves, else the capacity-config env dirs, else the
    documented state defaults.  ``create`` only ever makes the ENV-REDIRECTED
    directory (a test/explicit operator path); the default on-disk homes are
    only created when a write actually needs them."""
    path = _resource_profile_path()
    if path is not None:
        return path.parent
    for env in ("PRESENTATION_CAPACITY_CONFIG_DIR",
                "PRESENTATION_RESOURCE_PROFILE_DIR"):
        val = os.environ.get(env)
        if val:
            d = Path(val).expanduser()
            if create:
                try:
                    d.mkdir(parents=True, exist_ok=True)
                except OSError:
                    return None
            return d
    home = Path(os.path.expanduser("~"))
    for d in (home / ".openclaw" / "state" / "presentation",
              Path("/data/.openclaw/state/presentation")):
        if create:
            try:
                d.mkdir(parents=True, exist_ok=True)
                return d
            except OSError:
                continue
        elif d.is_dir():
            return d
    return None


def _circuit_path(create: bool = False) -> Optional[Path]:
    d = _circuit_dir(create)
    if d is None:
        return None
    return d / _CIRCUIT_FILENAME


def _circuit_revision_hint(provider: str) -> int:
    """The revision the caller's knowledge of *provider* is based on: the
    document revision when this process last read/merged that provider's
    entry.  0 when nothing was ever read (never stale)."""
    with _circuit_lock:
        entry = (_circuit_cache.get("providers") or {}).get(provider)
        if isinstance(entry, dict) and entry.get("_base_revision") is not None:
            return int(entry["_base_revision"])
        return int(_circuit_cache.get("revision") or 0)


def _load_circuit() -> dict:
    """The live shared document, or an empty one.  Callers that already hold
    the file lock pass it in; reads are always fresh (never the cache) so a
    merge decision is made against the real current state."""
    path = _circuit_path(create=False)
    if path is None or not path.is_file():
        return {"revision": 0, "providers": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"revision": 0, "providers": {}}
    if not isinstance(data, dict) or not isinstance(data.get("providers"), dict):
        return {"revision": 0, "providers": {}}
    return data


def _persist_circuit(updates: Dict[str, dict]) -> Dict[str, dict]:
    """Merge *updates* (provider -> entry fields, optional "base_revision")
    into the shared document under the file lock.  A provider entry whose
    base_revision is behind the live revision AND whose event is not newer
    than the stored one is REJECTED VISIBLY (logged) and left out; everything
    else merges.  Returns the final document, or {} when nothing could be
    written.  Never raises."""
    path = _circuit_path(create=True)
    if path is None:
        return {}
    lock_path = path.with_suffix(".lock")
    holder = None
    try:
        holder = open(lock_path, "a", encoding="utf-8")  # noqa: SIM115 - held for the critical section
        if _fcntl is not None:
            _fcntl.flock(holder.fileno(), _fcntl.LOCK_EX)
    except OSError:
        if holder is not None:
            try:
                holder.close()
            except OSError:
                pass
        holder = None  # unlocked best-effort: the retry loop still bounds us
    try:
        for _attempt in range(_CIRCUIT_PERSIST_RETRIES):
            current = _load_circuit()
            providers = dict(current.get("providers") or {})
            revision = int(current.get("revision") or 0)
            for pid, upd in dict(updates).items():
                base = int(upd.get("base_revision") or 0)
                stored = providers.get(pid) if isinstance(providers.get(pid), dict) else None
                if (base and revision > base and stored is not None
                        and float(stored.get("updated_at") or 0)
                        >= float(upd.get("updated_at") or 0)):
                    _append_log(pid, "circuit-stale-revision", 0, 0, ok=False,
                                note=(f"stale circuit write rejected: base "
                                      f"revision {base} behind live {revision} "
                                      f"and the stored event is newer -- kept "
                                      f"the live entry"))
                    continue
                entry = {k: v for k, v in upd.items() if k != "base_revision"}
                entry["_base_revision"] = revision + 1
                providers[pid] = entry
            doc = {"revision": revision + 1, "providers": providers,
                   "updated_at": time.time()}
            try:
                tmp = path.with_suffix(f".json.tmp-{os.getpid()}")
                tmp.write_text(json.dumps(doc), encoding="utf-8")
                os.replace(tmp, path)
            except OSError:
                time.sleep(0.02 * (_attempt + 1))
                continue
            with _circuit_lock:
                global _circuit_cache, _circuit_loaded_at
                _circuit_cache = doc
                _circuit_loaded_at = time.time()
            return doc
        _append_log("circuit", "circuit-persist-failed", 0, 0, ok=False,
                    note=f"shared circuit document not written after "
                         f"{_CIRCUIT_PERSIST_RETRIES} attempts: {lock_path}")
        return {}
    finally:
        if holder is not None:
            try:
                if _fcntl is not None:
                    _fcntl.flock(holder.fileno(), _fcntl.LOCK_UN)
                holder.close()
            except OSError:
                pass


def _sync_circuit_locked(st: _ProviderState, provider: str, now: float) -> None:
    """Import another process's persisted penalty into *this* process's live
    state.  Caller holds ``_lock``.  Throttled to one file read per
    _CIRCUIT_SYNC_INTERVAL_S; a stored entry wins only when its 429 is
    strictly newer than anything this process saw (stale-revision rule)."""
    global _circuit_loaded_at
    if now - _circuit_loaded_at < _CIRCUIT_SYNC_INTERVAL_S:
        return
    _circuit_loaded_at = now
    doc = _load_circuit()
    with _circuit_lock:
        _circuit_cache.update(doc if isinstance(doc, dict) else {})
    entry = (doc.get("providers") or {}).get(provider)
    if not isinstance(entry, dict):
        return
    # [PRES-003] RESTART RETAINS THE DAILY BUDGET: the shared document carries
    # the UTC day and its acquisition count.  A process that has counted
    # nothing today (a restart, a respawned dispatcher) imports the stored
    # count so a denial cannot be reset by starting a new process; a process
    # whose OWN count for the same day is already higher keeps its larger
    # number (monotonic, never regresses).  A stored count for a PREVIOUS day
    # is a stale row -- today's count starts at zero as before.
    stored_day = str(entry.get("day") or "")
    stored_count = entry.get("day_count")
    if stored_day == _utc_day() and isinstance(stored_count, (int, float)) \
            and not isinstance(stored_count, bool):
        stored_count = int(stored_count)
        if stored_count > st.day_count and not st.day_count_imported:
            st.day = stored_day
            st.day_count = stored_count
            st.day_count_imported = True
        elif st.day_count > 0 and not st.day_count_imported:
            # this process already counted today; merge upward only
            st.day_count_imported = True
            if stored_count > st.day_count:
                st.day_count = stored_count
    entry_ts = float(entry.get("last_429_ts") or 0)
    if entry_ts > st.last_429_ts:
        st.last_429_ts = entry_ts
        st.rate_scale = min(1.0, max(SCALE_FLOOR,
                                     float(entry.get("rate_scale") or 1.0)))
        st.rate_scale_until = float(entry.get("penalty_until") or 0)
        st.penalty_started = float(entry.get("penalty_started") or 0)
        st.retry_after_s = float(entry.get("retry_after_s") or 0)


def circuit_snapshot() -> dict:
    """[PRES-016] The persisted/shared penalty view: cooldown, next retry and
    the affected account per provider -- the surface another job (or the
    operator) reads to see WHY a provider is cooled down while others run."""
    now = time.time()
    doc = _load_circuit()
    out: Dict[str, dict] = {}
    for pid, entry in (doc.get("providers") or {}).items():
        if not isinstance(entry, dict):
            continue
        until = float(entry.get("penalty_until") or 0)
        out[pid] = {
            "rate_scale": float(entry.get("rate_scale") or 1.0),
            "penalty_remaining_s": max(0.0, until - now),
            "next_retry_at_epoch": until,
            "retry_after_s": float(entry.get("retry_after_s") or 0.0),
            "last_429_ts": float(entry.get("last_429_ts") or 0.0),
            "updated_at": float(entry.get("updated_at") or 0.0),
        }
    return out


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
                ok: bool = True, note: Optional[str] = None) -> None:
    rec = {
        "ts": time.time(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z",
        "provider": provider,
        "event": kind,
        "n": n,
        "inflight": inflight,
        "ok": ok,
    }
    if note:
        # [F17] a human-readable line for events that carry a reason, not a
        # count (config-defaults). Absent on every acquire/release record, so
        # the window-count readers are byte-for-byte unaffected.
        rec["note"] = note
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
    """Diagnostics: per-provider tokens, inflight, scale, penalty state, day
    count.  [PRES-016] exposes the cooldown, the next retry epoch and the
    honored Retry-After so the WHY of a cooled provider is always readable."""
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
                "penalty_remaining_s": max(0.0, st.rate_scale_until - now),
                "penalty_started": st.penalty_started,
                "last_429_ts": st.last_429_ts,
                "retry_after_s": st.retry_after_s,
                "next_retry_at_epoch": st.rate_scale_until,
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
            # [PRES-016] import another process's persisted penalty first, so
            # a cooldown earned in a sibling dispatcher cools THIS bucket too
            # (throttled; a stale entry never beats a newer local 429).
            _sync_circuit_locked(st, provider, now)
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
                # [PRES-003] the daily budget is consumed HERE, so the shared
                # document must carry the count HERE: a restart (new process,
                # zero local count) imports the stored total and a denial
                # cannot be reset by starting a fresh process.  Best-effort:
                # a persist failure degrades to in-process-only accounting
                # (the same degradation the penalty persistence already has).
                _persist_circuit({provider: {
                    "day": st.day,
                    "day_count": st.day_count,
                    "updated_at": now,
                    "base_revision": _circuit_revision_hint(provider),
                }})
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


def report_429(provider: str, retry_after_s: Optional[float] = None) -> float:
    """Provider answered 429: MULTIPLICATIVELY decrease the start-rate and
    hold the penalty for the provider's own Retry-After (default 60 s).

    [FIX 14 / W09-B2] "a forced 429 halves the next minute's rate."  The
    halving applies to the REFILL RATE from this instant: the accumulated
    token balance decays to the scaled burst so a stored surplus cannot pay
    for a burst of submissions at the old pace inside the penalty window.
    Repeated 429s re-halve (floor 1/32 of base).

    [PRES-016] The penalty duration is the provider's own Retry-After when it
    sent one (capped at RETRY_AFTER_CAP_S so a broken header cannot wedge the
    account for a day, floor 1 s), else the 60 s default.  An OLD IN-FLIGHT
    SUCCESS arriving right after this call can no longer erase the penalty:
    report_ok only ADDS recovery after a full healthy observation window with
    the minimum sample count.  The penalty is persisted to the shared circuit
    document so every other dispatcher process on the host honors the same
    cooldown (unrelated providers are never touched).  Returns the applied
    scale so callers/tests can assert it.
    """
    with _lock:
        st = _state_for(provider)
        now = time.time()
        penalty_s = DEFAULT_PENALTY_S
        if retry_after_s is not None:
            try:
                penalty_s = min(RETRY_AFTER_CAP_S, max(1.0, float(retry_after_s)))
            except (TypeError, ValueError):
                penalty_s = DEFAULT_PENALTY_S
        # Multiplicative decrease: a fresh 429 sets 0.5; another 429 inside
        # the still-open penalty window (or inside a Retry-After longer than
        # the default) halves again -- exactly the W09-B2 re-halving, with the
        # "inside the window" test measured from the last 429 rather than the
        # scale expiry so a long Retry-After cannot look like recovery.
        window = max(DEFAULT_PENALTY_S, st.retry_after_s)
        if st.last_429_ts and (now - st.last_429_ts) <= window:
            st.rate_scale = max(SCALE_FLOOR, st.rate_scale / 2.0)
        else:
            st.rate_scale = max(SCALE_FLOOR, min(st.rate_scale, 0.5))
        st.rate_scale_until = now + penalty_s
        st.last_429_ts = now
        st.penalty_started = now
        st.retry_after_s = penalty_s
        st.ok_samples.clear()
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
        circuit_entry = {
            "rate_scale": scale,
            "penalty_until": st.rate_scale_until,
            "penalty_started": st.penalty_started,
            "last_429_ts": st.last_429_ts,
            "retry_after_s": st.retry_after_s,
            # [PRES-003] the daily budget travels with the penalty so a
            # restart cannot reset the cap by starting a fresh process.
            "day": st.day,
            "day_count": st.day_count,
            "updated_at": now,
            "base_revision": _circuit_revision_hint(provider),
        }
    _append_log(provider, "report_429", 0, inflight)
    try:
        _persist_circuit({provider: circuit_entry})
    except Exception:  # noqa: BLE001 -- persistence must never break telemetry
        pass
    return scale


def report_ok(provider: str) -> None:
    """Call succeeded: record ONE healthy sample; recovery is graduated.

    [PRES-016] A success no longer doubles the scale.  A success that arrives
    right after a 429 is usually an ALREADY-IN-FLIGHT request that started
    before the penalty opened -- counting it as recovery would let one stale
    response erase the penalty, which is exactly the defect.  So every clean
    response only APPENDS a sample; the scale moves by at most ONE ADDITIVE
    STEP (SCALE_STEP) and only when a full healthy observation window
    (HEALTHY_WINDOW_S, measured from the 429 that opened the penalty) carries
    at least HEALTHY_MIN_SAMPLES clean responses.  Each granted step starts a
    NEW window, so recovery to full rate is gradual even under sustained
    healthy traffic.  When no 429 ever set a scale below 1.0 this is a no-op
    telemetry row, as before."""
    with _lock:
        st = _state_for(provider)
        now = time.time()
        changed = False
        if st.rate_scale >= 1.0:
            st.events.append((now, "report_ok", 0))
            return
        if not st.last_429_ts:
            # Below full rate with no known 429 (an imported/legacy state):
            # nothing explains the throttle, restore it.
            st.rate_scale = 1.0
            st.rate_scale_until = 0.0
            st.events.append((now, "report_ok", 0))
            changed = True
        else:
            st.ok_samples.append(now)
            elapsed = now - st.penalty_started
            if elapsed >= HEALTHY_WINDOW_S and \
                    len(st.ok_samples) >= HEALTHY_MIN_SAMPLES:
                st.rate_scale = min(1.0, st.rate_scale + SCALE_STEP)
                st.penalty_started = now  # the next window needs fresh evidence
                st.ok_samples.clear()
                if st.rate_scale >= 1.0:
                    st.rate_scale_until = 0.0
                changed = True
            st.events.append((now, "report_ok", 0))
        scale = st.rate_scale
        inflight = st.inflight
        circuit_entry = {
            "rate_scale": scale,
            "penalty_until": st.rate_scale_until,
            "penalty_started": st.penalty_started,
            "last_429_ts": st.last_429_ts,
            "retry_after_s": st.retry_after_s,
            # [PRES-003] keep the daily-budget row current on every persisted
            # write so the newest process's count is what a restart imports.
            "day": st.day,
            "day_count": st.day_count,
            "updated_at": now,
            "base_revision": _circuit_revision_hint(provider),
        }
    if not changed:
        return
    _append_log(provider, "report_ok", 0, inflight)
    try:
        _persist_circuit({provider: circuit_entry})
    except Exception:  # noqa: BLE001 -- persistence must never break telemetry
        pass


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
