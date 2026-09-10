from __future__ import annotations

"""
presentation_job/dispatcher.py -- the Work-Order Dispatcher.

THE ONE-SENTENCE PROBLEM THIS FIXES: Engine._run_agent_phase() (phases.py) writes
a work order to working/work-orders/<phase>.json for every agent-authored phase
and then polls the filesystem every 15s for the artifact to appear -- but until
this module existed, NOTHING ever consumed that work order, so every
agent-authored phase timed out and blocked. This module is the consumer.

See CONTROL/DISPATCHER-SPEC.md (analysis + design) for the full evidence trail.
This file implements that spec's Strategy A (text/JSON authoring via DeepSeek V4
Flash direct) plus an honest, non-fabricating decline for phases that need a
deterministic script or a real conversation transcript instead of a text
completion (Strategy B/C phases -- see DECLINE_PHASES below).

HARD INVARIANTS -- every one of these is load-bearing, not stylistic:

  1. NEVER marks a phase "done". NEVER writes state.json. NEVER takes RunLock
     (state.RunLock is exclusive per run dir; a second process attempting it
     while the Engine is alive dies immediately with EXIT_LOCK_HELD -- and even
     if it didn't, a read-modify-write outside the lock would race the Engine's
     own periodic checkpoint and silently clobber it). phase_verifiers.verify()
     -- the SAME function Engine.run_phase() calls -- is the only judge. This
     module only PREDICTS that judgment before the Engine's poll loop notices
     the file; the Engine still re-runs the identical check and is the only
     thing that ever writes status="done".
  2. NEVER fabricates a passing artifact. Every artifact written here is real
     model output that this module's OWN pre-check (the same verify() call)
     confirms passes before it is left in place. A phase this module cannot
     honestly author (DECLINE_PHASES below) is left alone -- never faked.
  3. Claim-safe and idempotent. An atomic O_CREAT|O_EXCL claim file stops two
     workers (same run, cross-run scan, or a re-launched process) from
     double-spending a DeepSeek call on the same phase. A sweep that finds a
     work order already satisfied skips it without spending anything.
  4. Every attempt is logged to a sidecar file the Engine never reads or writes
     (working/work-orders/<phase>.dispatcher-log.jsonl) -- so a human (or a
     future Engine change) can see the REAL reason a phase failed minutes to
     hours before the Engine's own generic budget-timeout message would
     otherwise surface it.

Runnable two ways (both exercise the exact same code):
    python3 -m presentation_job.dispatcher --run-dir <run_dir> --once
    python3 work_order_dispatcher.py --run-dir <run_dir> --watch      (standalone)
"""

import argparse
import hashlib
import inspect
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Path bootstrap. This module must import cleanly whether launched as
# `python3 -m presentation_job.dispatcher` (package import) or as the
# standalone work_order_dispatcher.py wrapper (which path-inserts scripts_dir
# before importing this module) -- and it must be able to `import
# phase_verifiers` / `import build_deck`, both of which live at the TOP of
# scripts_dir, not inside the presentation_job package. Explicit, defensive
# sys.path insertion mirrors the pattern persona.py and phase_verifiers.py
# already use in this codebase for the same reason.
# ---------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()
_OWN_SCRIPTS_DIR = _THIS_FILE.parent.parent  # presentation_job/ -> scripts/
if str(_OWN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_OWN_SCRIPTS_DIR))

from presentation_job.manifest import Manifest, Phase, resolve_manifest  # noqa: E402
from presentation_job import model_catalog as _model_catalog  # noqa: E402  FIX 13
from presentation_job.state import StateStore, utcnow  # noqa: E402
from presentation_job import heal as _heal  # noqa: E402
from presentation_job import contract_introspect as _ci  # noqa: E402
from presentation_job import execution_stamp as _estamp  # noqa: E402  PRES-042
from presentation_job import fanout  # noqa: E402  -- PARALLEL-PIPELINE-SPEC Ticket 4

# Defensive import of build_deck (top-level scripts_dir module) -- mirrors
# phase_verifiers.py's own `try: import build_deck as _bd` pattern exactly (same
# module, same optionality). Used ONLY by the P4-PROMPT per-slide dispatch below to
# re-use the REAL check_prompt_qc_deterministic gate for per-slide verification
# (never a separately-reimplemented, potentially-drifting copy of its rules).
try:
    import build_deck as _bd
except ImportError:
    _bd = None  # type: ignore[assignment]

# FIX 2: the parallel P4-PROMPT prompt authoring worker (same package). Same
# defensive pattern. Consulted by the P4-PROMPT branch of dispatch_one under the
# PRESENTATION_PROMPT_PARALLEL feature flag (default ON; =0 selects the
# untouched serial loop below as the documented rollback path).
try:
    from presentation_job import parallel_prompt_worker as _ppw
except ImportError:  # pragma: no cover - degraded envs fall back to serial
    _ppw = None  # type: ignore[assignment]

try:
    from presentation_job import model_router as _model_router
except ImportError:  # pragma: no cover - pre-FIX-7 trees route nothing new
    _model_router = None  # type: ignore[assignment]

# FIX 19: the real web-search/fetch capability for P-0.5-RESEARCH (Brave-primary,
# bounded fetch, retrieval ledger). Same defensive pattern as the imports above:
# a tree that predates the module routes nothing new.
try:
    from presentation_job import research_web as _research_web
except ImportError:  # pragma: no cover - pre-FIX-19 trees keep the old behavior
    _research_web = None  # type: ignore[assignment]

# FIX 14 (MASTER Part 8): one per-provider governor for every outbound call.
# Same defensive pattern as the imports above: a tree that predates the
# governor module (or one where W09 has not yet landed governor.py) keeps the
# old behavior byte-for-byte -- every _govern_acquire call degrades to a
# no-op lease when the module is absent, so nothing here can hard-crash a run.
try:
    from presentation_job import governor as _governor
except ImportError:  # pragma: no cover - pre-FIX-14 trees limit nothing new
    _governor = None  # type: ignore[assignment]

# FIX 104 (Master Part 8): the ONE WaveContract shared by dispatcher and
# parallel_prompt_worker (stamp -> wave_input -> validate_input). Same
# defensive pattern: a tree without wave_contract.py keeps the inline
# dict-building path, and _wave_contract is None.
try:
    from presentation_job import wave_contract as _wave_contract
except ImportError:  # pragma: no cover - pre-FIX-104 trees keep inline dict
    _wave_contract = None  # type: ignore[assignment]

DISPATCH_RETRY_CAP = _heal.HEAL_CAP_TRANSIENT  # = 3. Reused, not re-invented (spec S7.1):
                                                # one operator-visible retry budget for the
                                                # whole pipeline, not a second number.

# ---------------------------------------------------------------------------
# FIX 14 -- per-provider governor gates. Every outbound call site acquires a
# lease from presentation_job.governor before its HTTP attempt and releases it
# after; a 429 feeds report_429, a clean response feeds report_ok. The gates
# live HERE (module-level helpers) so dispatcher, parallel_prompt_worker and
# fanout all gate through the same code path instead of re-deriving the
# acquire/release/refcount dance per module.
#
# [PRES-003] THE GATE IS FAIL-CLOSED, NOT BEST-EFFORT.  The old helper caught
# every acquire exception and returned None, and every transport treated None
# as "proceed unthrottled" -- a broken governor, an exhausted daily cap or a
# missing module all silently turned into UNLIMITED outbound spend.  Admission
# is now REQUIRED for paid/network work and TYPED:
#
#     _govern_admit(provider) -> _GovernAdmission(admitted, lease, blocked,
#                                                 retry_after_s, reason)
#
#   * admitted  -- a live lease (or a reentrant/local-bypass pass) exists.
#   * retry     -- not admitted now (timeout, governor error): retry_after_s
#                  says when to re-attempt.  Transport is NOT invoked.
#   * blocked   -- permanent (governor module missing): a preflight error with
#                  visible remediation.  Transport is NOT invoked.
#
# WHY THE ATTEMPT-SCOPED LEASE REGISTRY: the transports issue one HTTP request
# per retry attempt inside their own `for attempt in range(1, retries + 1)`
# loop, and a 429 must be reported to the governor (rate halved 60 s) before
# the loop's backoff sleep re-attempts. A single outer acquire cannot do that,
# so each ATTEMPT takes its own lease. A re-entrant caller (worker -> provider
# call -> dispatch_complete -> transport) must not then double-hold a lease for
# one logical call, because max_inflight would under-count real capacity:
# _GOVERN_DEPTH counts, per thread, how many nested _govern_acquire calls are
# already holding for the same provider; only depth 0 actually touches the
# governor (a "logical acquire"), deeper nesting reuses the same lease.
#
# [PRES-003] REENTRANT SINGLE-LEASE FIX: a depth-0 acquire that FAILED used to
# be un-counted and the transport's nested frame would then try a SECOND real
# acquire -- and if THAT one succeeded, the logical request proceeded with a
# lease the outer admission had already given up on (the fail-open hole).  A
# failed admission now leaves depth 0 and NO active lease, and the refusal
# propagates as a typed outcome before any transport frame can run: one
# logical HTTP request holds exactly one lease, or makes no HTTP request.
#
# [PRES-003] LOCAL BYPASS ALLOWLIST: only explicitly classified local
# CPU/file/image-inspection units bypass the provider gate -- by token, never
# by absence.  Anything else (including an unnameable provider) is gated.
# ---------------------------------------------------------------------------
_GOVERN_DEPTH_LOCK = threading.Lock()
_GOVERN_DEPTH: Dict[str, int] = {}   # f"{thread_ident}:{provider}" -> nested depth
_GOVERN_ACTIVE: Dict[str, Any] = {}  # same key -> live lease to release once

#: [PRES-003] Local-bypass tokens.  A unit whose provider identity is one of
#: these is explicitly classified LOCAL (CPU or file work -- QC graders, file
#: assembly, local image inspection): it consumes no provider budget and is
#: admitted with lease=None.  These tokens must never be sent as a network
#: provider id; the transports only ever name real providers.
_GOVERN_LOCAL_BYPASS = frozenset({
    "local", "local-cpu", "local-file", "local-image-inspection",
})

#: [PRES-003] Bounded wait for one admission.  A refusal is a TYPED outcome
#: the caller retries with its own backoff -- never an unbounded block inside
#: the gate and never a silent pass-through.
_GOVERN_ACQUIRE_TIMEOUT_S = 120.0


class _GovernAdmission:
    """Typed admission outcome for one provider on one thread.

    admitted     -- the call may proceed; `lease` is live (None only for a
                    local-bypass or reentrant pass, which release as None).
    blocked      -- PERMANENT refusal (missing/broken governor): a preflight
                    error with remediation in `reason`; retrying cannot fix it.
    retry_after_s -- seconds to wait before re-attempting (retry class only).
    reason       -- human-readable, operator-visible, never empty on refusal.
    """

    __slots__ = ("admitted", "lease", "blocked", "retry_after_s", "reason")

    def __init__(self, *, admitted: bool, lease: Any = None,
                 blocked: bool = False, retry_after_s: Optional[float] = None,
                 reason: str = "") -> None:
        self.admitted = bool(admitted)
        self.lease = lease
        self.blocked = bool(blocked)
        self.retry_after_s = retry_after_s
        self.reason = str(reason or "")

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return (f"_GovernAdmission(admitted={self.admitted}, "
                f"blocked={self.blocked}, retry_after_s={self.retry_after_s}, "
                f"reason={self.reason!r})")


def _govern_refusal_text(provider: str, admission: "_GovernAdmission") -> str:
    """The one-line, sidecar-greppable refusal reason.  "No outbound call was
    attempted" is part of the contract: the reader must be able to tell from
    the log alone that zero transport calls were made."""
    canon = _govern_provider(provider)
    if admission.blocked:
        return (f"GOVERNOR-BLOCKED: provider {canon} admission permanently "
                f"refused ({admission.reason}) -- no outbound call was "
                f"attempted. Fix the governor before re-dispatching: "
                f"restore/repair presentation_job/governor.py so acquire() "
                f"works, then reissue the work order.")
    wait = admission.retry_after_s
    wait_s = f"{wait:.0f}s" if isinstance(wait, (int, float)) else "unknown"
    return (f"GOVERNOR-RETRY: provider {canon} admission not granted "
            f"({admission.reason}) -- no outbound call was attempted; "
            f"retry after {wait_s}.")


# U4 (2026-09-07) -- PROVIDER IDENTITY IS FOLDED ONCE, HERE, FOR EVERY GATE.
#
# THE DEFECT. Provider identity has two live spellings in this tree, MEASURED
# on this box today:
#     model_router.resolve_alias("deepseek-v4-pro")["provider"] -> 'deepseek'
#     capacity.probe()["provider"]                              -> 'deepseek-direct'
# and providers.yaml keys the SHORT form ('deepseek', 'ollama') while
# capacity.CAP_TABLE keys the LONG one ('deepseek-direct', 'ollama-cloud').
# `governor.provider_config` already folds (PROVIDER_ALIASES), so BOTH
# spellings read the same rps/burst/max_inflight row -- but `governor._state`
# and `_GOVERN_DEPTH` are keyed by the RAW string, so the two spellings open
# TWO INDEPENDENT token buckets over ONE account. Measured before this fix:
#     governor._state_for('deepseek') is _state_for('deepseek-direct') -> False
#     provider_config(both) -> max_inflight 400   ==> 800 effective in flight
# and the re-entrancy depth counter could not dedupe the worker's outer lease
# against the transport's inner one, so one logical call took two real
# acquires. This is the DEFECT-5 class (spelling compared instead of identity)
# on the governor's own bucket.
#
# THE FOLD. Same authority DEFECT 5 used: capacity.normalize_provider, the ONE
# cap table. Unlike the stamp we can never return None here -- a gate must
# still gate -- so an id the cap table cannot resolve keeps its canonical
# TOKEN (lowercase, underscores/spaces -> dashes). That is deliberate and it
# is not a fabrication: 'anthropic' has no CAP_TABLE row but DOES have a real
# providers.yaml row, and folding it to some nearest-looking provider would be
# exactly the silent substitution this program is removing. A token with no
# yaml row is governed at `defaults` and `governor._announce_defaults_once`
# already says so, once, on stderr and in the acquisition log -- so the quiet
# case is already loud and this helper must not double-announce it.
def _govern_provider(provider: Any) -> str:
    """The canonical governor key for `provider`: one bucket per ACCOUNT, never
    one per spelling. Never returns None or "" -- a gate that cannot name its
    provider still has to gate."""
    raw = str(provider or "").strip()
    token = raw.lower().replace("_", "-").replace(" ", "-")
    if not token:
        # No identity at all. Callers must not reach here (the worker refuses
        # loudly instead), but a gate is never allowed to crash a run.
        return "unknown-provider"
    try:
        from presentation_job import capacity as _cap_mod
        canon = _cap_mod.normalize_provider(token)
    except Exception:  # noqa: BLE001 -- a fold failure never changes gating
        canon = None
    return str(canon) if canon else token


def _govern_key(provider: str) -> str:
    return f"{threading.get_ident()}:{_govern_provider(provider)}"

def _govern_admit(provider: str) -> "_GovernAdmission":
    """[PRES-003] Required, typed admission for `provider` on this thread.

    Admitted -> live lease (reentrant frames reuse the outer lease; explicitly
    local tokens bypass with lease=None).  Refused -> a typed retry/blocked
    outcome and NO governor state is left behind, so the caller must not (and
    cannot) invoke the transport.  Never raises."""
    canon = _govern_provider(provider)
    if canon in _GOVERN_LOCAL_BYPASS:
        # Explicitly classified local unit: no provider budget, no lease.
        return _GovernAdmission(admitted=True, lease=None,
                                reason="local-bypass: local CPU/file unit "
                                       "admitted outside the provider gate")
    key = f"{threading.get_ident()}:{canon}"
    with _GOVERN_DEPTH_LOCK:
        depth = _GOVERN_DEPTH.get(key, 0)
        if depth > 0:
            # Nested call: the outer frame already holds the lease for this
            # logical call on this thread.
            return _GovernAdmission(admitted=True,
                                    lease=_GOVERN_ACTIVE.get(key),
                                    reason="reentrant: outer admission's lease")
        # Hold the frame count while the real acquire runs, so a concurrent
        # nested admission cannot sneak past; a failed admit pops it again.
        _GOVERN_DEPTH[key] = 1
    if _governor is None:
        with _GOVERN_DEPTH_LOCK:
            _GOVERN_DEPTH.pop(key, None)
        return _GovernAdmission(
            admitted=False, blocked=True,
            reason=("presentation_job/governor.py is missing or failed to "
                    "import -- the per-provider admission governor is REQUIRED "
                    "for outbound work"))
    try:
        lease = _governor.acquire(canon, timeout_s=_GOVERN_ACQUIRE_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 -- typed outcome, never a pass
        with _GOVERN_DEPTH_LOCK:
            _GOVERN_DEPTH.pop(key, None)
        timeout = type(exc).__name__ == "GovernorTimeout" or \
            isinstance(exc, TimeoutError)
        if timeout:
            return _GovernAdmission(
                admitted=False, retry_after_s=30.0,
                reason=f"governor acquire timed out after "
                       f"{_GOVERN_ACQUIRE_TIMEOUT_S}s ({exc})")
        return _GovernAdmission(
            admitted=False, retry_after_s=0.0,
            reason=f"governor acquire failed: {type(exc).__name__}: {exc}")
    with _GOVERN_DEPTH_LOCK:
        _GOVERN_ACTIVE[key] = lease
    return _GovernAdmission(admitted=True, lease=lease, reason="admitted")

def _govern_acquire(provider: str):
    """Back-compat wrapper around :func:`_govern_admit`: returns the live
    lease, or None when the admission was refused.  Callers that treat None as
    "no outer lease of my own" (parallel_prompt_worker) stay correct because
    the ENFORCING gate is the transport's own admission inside
    dispatch_complete -- a refused call never reaches the wire.  Callers that
    need the typed outcome call _govern_admit directly."""
    admission = _govern_admit(provider)
    return admission.lease if admission.admitted else None

def _govern_release(provider: str, lease: Any) -> None:
    """Release the lease taken by _govern_acquire for `provider` on this
    thread (only when this frame is the outermost one). Best-effort."""
    if _governor is None:
        return
    key = _govern_key(provider)  # U4: same fold as _govern_acquire
    with _GOVERN_DEPTH_LOCK:
        depth = _GOVERN_DEPTH.get(key, 0)
        _GOVERN_DEPTH[key] = max(0, depth - 1)
        active = _GOVERN_ACTIVE.get(key)
        if depth <= 1:
            _GOVERN_ACTIVE.pop(key, None)
    if depth <= 1 and active is not None:
        try:
            _governor.release(active)
        except Exception:  # noqa: BLE001
            pass

def _govern_429(provider: str, retry_after_s: Optional[float] = None) -> None:
    """Feed a 429 back to the governor. Best-effort. [PRES-016] carries the
    response's Retry-After (seconds) when the provider sent one, so the
    penalty matches what the provider actually asked for."""
    if _governor is None:
        return
    try:
        # U4: the penalty must land on the bucket the calls were admitted
        # from, so it folds exactly like _govern_acquire.
        _governor.report_429(_govern_provider(provider),
                             retry_after_s=retry_after_s)
    except Exception:  # noqa: BLE001
        pass

def _govern_ok(provider: str) -> None:
    """Feed a clean response back to the governor (one healthy sample).
    Best-effort. [PRES-016] recovery is additive per healthy window, decided
    inside governor.report_ok."""
    if _governor is None:
        return
    try:
        _governor.report_ok(_govern_provider(provider))  # U4: same fold
    except Exception:  # noqa: BLE001
        pass


def _govern_retry_after(exc: BaseException) -> Optional[float]:
    """[PRES-016] The provider's Retry-After header, in seconds, when the
    exception is an HTTPError carrying one.  Only the integer-seconds form is
    parsed; the HTTP-date form yields None (the 60 s default stands) -- an
    honest "unknown" beats a wrong clock parse."""
    try:
        headers = getattr(exc, "headers", None)
        if headers is None:
            return None
        raw = headers.get("Retry-After")
        if raw is None:
            return None
        text = str(raw).strip()
        if not text or any(ch.isalpha() for ch in text.replace("GMT", "")):
            return None
        return float(text)
    except Exception:  # noqa: BLE001 -- a malformed header is just None
        return None

# ---------------------------------------------------------------------------
# DeepSeek V4 Flash direct -- confirmed live configuration (openclaw.json),
# never hardcoded from documentation guesswork. Base URL / model id / api
# shape read from models.providers.deepseek; "thinking MAX" request fields
# (`thinking.type=enabled` + `reasoning_effort=max`) are the EXACT fields
# deepseek-v4-pro already carries in this box's own agents.defaults.models
# params block for the sibling model on the SAME native endpoint -- proven
# live (not guessed) with a real smoketest call against deepseek-v4-flash
# before this module was wired in: HTTP 200, a populated `reasoning_content`
# field, and usage.completion_tokens_details.reasoning_tokens > 0, proving
# thinking is genuinely engaged and not silently dropped.
# ---------------------------------------------------------------------------
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
# FIX 13: no literal model id in this code path. The "fast" authoring class
# resolves from the central versioned catalog (text.fast alias); operator
# bump changes what the NEXT call sends without editing this file. The
# base URL stays pinned here — it is endpoint config, not a model id.
DEEPSEEK_MODEL = _model_catalog.model_id("text.fast")
DEEPSEEK_CHAT_URL = f"{DEEPSEEK_BASE_URL}/chat/completions"
# CONFIRMED LIVE (not guessed): DeepSeek's native endpoint bills reasoning tokens
# AND the final content tokens out of the SAME max_tokens budget --
# usage.completion_tokens_details.reasoning_tokens is a SUBSET of completion_tokens,
# not additional to it (proven by a real call during dispatcher development: a
# max_tokens=8000 request with reasoning_effort=max returned completion_tokens=7999,
# reasoning_tokens=7999, and a ZERO-LENGTH `content` field -- "thinking MAX" had
# consumed the entire budget on reasoning, leaving nothing for the deliverable
# itself, and the empty file that produced then raced the Engine's own 15s poll
# into a real BLOCKED park before this module's own retry loop could recover).
# ROOT CAUSE (live run pj_34a56a26caca04532ec6e9cba6, 2026-08-18): 32,000 was NOT
# generous enough in practice -- P3-ARC's real dispatch hit completion_tokens=31997
# (reasoning_tokens=25333, leaving ~6.6k for content) and its structured JSON
# artifact was cut off mid-object (truncated, invalid JSON), correctly blocking
# the Engine on a substance-check failure. Same bug class the 8000->32000 raise
# already fixed once (see the comment above this constant's history), recurring
# at a higher artifact size. Raised again to 64,000 -- still well inside
# deepseek-v4-flash's real 393,216-token output ceiling (confirmed live), and
# gives a large structured artifact (deep choreography JSON, 60+ slides of copy)
# room to complete even after thinking-MAX spends heavily on reasoning first.
DEEPSEEK_MAX_OUTPUT_TOKENS = 64_000
DEEPSEEK_TEMPERATURE = 0.3
DEEPSEEK_TIMEOUT_S = 600       # thinking MAX at a large max_tokens can genuinely run minutes

SECRETS_ENV_PATH = Path.home() / ".openclaw" / "secrets" / "secrets.env"

SWEEP_INTERVAL_S = 10          # faster than the Engine's own 15s poll (phases.py:472)
CLAIM_STALE_MULTIPLIER = 2.0   # a claim older than 2x a single attempt's wall budget
                                # is presumed abandoned (crashed worker), not slow.
SINGLE_ATTEMPT_BUDGET_S = DEEPSEEK_TIMEOUT_S + 60  # ceiling on one round-trip + write + verify

DEFAULT_MAX_WORKERS = 8        # sane default when capacity.py is unavailable; the real
                                # ceiling (declared 100 for deepseek-direct) is resolved
                                # from capacity.py at runtime -- see resolve_max_workers().
# U1 (2026-09-07): DEFAULT_MAX_WORKERS IS NOT A CAPACITY ANSWER.
# It was born 2026-08-18 ("Add the Work-Order Dispatcher", f16eb55cb) as the
# worker-pool default when capacity.py is unavailable. It has NO lineage to the
# operator's Ollama reserve (capacity.CAP_TABLE[(ollama-cloud, $100/month)] = 8,
# ruling 2026-09-04: consume 8 of a real ceiling of 10, leave the client 2) --
# the digits merely coincide, and that coincidence is dangerous: a log line
# reading "8 workers" on an OpenRouter run LOOKS like the reserve being honoured
# when it is actually capacity resolution having failed. From U1 onward this
# constant may answer only three questions: (a) the router-absent rollback stamp
# (byte-for-byte pre-FIX-7), (b) an explicit caller request, and (c) the case
# where capacity.py itself cannot be imported. It may NEVER stand in for an
# UNBOUNDED reading (that resolves to the MODE CEILING) and it may never stand
# in for a capacity that could not be established (that REFUSES LOUDLY and
# carries capacity.DEFAULT_CONSERVATIVE, the floor capacity.py itself owns).

#: The autofail code a width refusal cites. Same string as capacity.AUTOFAIL_CODE
#: and launcher.CAPACITY_AUTOFAIL_CODE; duplicated as a literal so the refusal
#: path never depends on importing the module that just failed.
CAPACITY_REFUSAL_CODE = "AF-CAPACITY-UNMEASURED"

# --- Repeat suppression / backoff (see the dispatch-ledger section below) ----
# Delay before re-dispatching a phase that just produced the SAME outcome
# again: BASE * MULTIPLIER**(repeat-1), clamped at CAP. At the live-observed
# SWEEP_INTERVAL_S=10 that turns 360 identical records/hour into ~11/hour once
# the cap is reached, WITHOUT slowing the first observation of anything new
# (repeat 0 => zero delay, always).
DISPATCH_BACKOFF_BASE_S = 30.0
DISPATCH_BACKOFF_MULTIPLIER = 2.0
DISPATCH_BACKOFF_CAP_S = 900.0
# Consecutive IDENTICAL failing outcomes (error/exhausted) for one (phase, run)
# before the phase is parked BLOCKED with a visible on-disk reason instead of
# being re-dispatched forever. 8 identical failures at the backoff schedule
# above is ~32 minutes of real retrying -- past any transient.
DISPATCH_REPEAT_CEILING = 8


# ---------------------------------------------------------------------------
# Phases this module explicitly DECLINES to author via a text completion --
# named and reasoned, never silently skipped, never faked. Two different
# reasons land a phase here (spec S3.1 Strategies B/C):
#
#   render     -- the phase's own verifier proves REAL KIE.ai image bytes must
#                 exist (P-STYLE-PREVIEW). A text model cannot emit
#                 a PNG. Route: build_deck.py's real render path via the
#                 manifest script executor (P4-RENDER now has one; FIX 4).
#   assembly   -- P8-ASSEMBLE/P9.5-NOTES-SYNC are mechanical PPTX-container
#                 operations (zip a already-rendered PNGs, or reopen a PPTX to
#                 inject notes), not authored prose -- confirmed by reading
#                 their verifiers (check_deck_harmony / notes_sync structural
#                 checks), not assumed from the manifest's blanket "agent"
#                 default (manifest.py:279 -- no phase declares an executor at
#                 all, so EVERY phase defaults to "agent" whether or not that
#                 is true).
#   driver_only -- P-SP-INTAKE-TRACE's own verifier (build_deck._chk_sp_intake_
#                 trace) requires a SIGNED envelope (format
#                 "sp-intake-transcript-v1" + driver_signature + qid_sequence)
#                 written mechanically, turn-by-turn, by deck-intake-driver.py.
#                 Its own docstring: "Presence of a transcript file is not
#                 proof it came from a real conversation." A DeepSeek-authored
#                 JSON blob, however well-formed, is definitionally NOT a
#                 driver-signed envelope and WILL fail this gate by design --
#                 attempting it would be spending real API calls to manufacture
#                 a guaranteed, correctly-fail-closed rejection.
# ---------------------------------------------------------------------------
DECLINE_PHASES: Dict[str, str] = {
    "P-STYLE-PREVIEW": "render: build_deck._chk_style_preview (a later precondition check) "
                        "proves the manifest must reference 9 real KIE renders (3 style x 3 "
                        "slides) plus an owner-approved pick. A manifest DeepSeek invents "
                        "without real renders behind it is exactly the fabricated-artifact "
                        "failure mode this module refuses to produce.",
    "P8-ASSEMBLE": "assembly: verifier (build_deck.check_deck_harmony) requires a real "
                   "PK\\x03\\x04 PPTX container assembled from already-rendered slide PNGs "
                   "-- a mechanical zip/assembly operation, not authored prose.",
    "P9.5-NOTES-SYNC": "assembly: reopens the assembled PPTX and re-injects speaker notes "
                       "-- a mechanical python-pptx operation, not authored prose.",
    "P-SP-INTAKE-TRACE": "driver_only: build_deck._chk_sp_intake_trace requires a "
                         "driver-signed envelope (format 'sp-intake-transcript-v1' + "
                         "driver_signature + qid_sequence) written turn-by-turn by "
                         "deck-intake-driver.py. A DeepSeek-authored transcript is not, "
                         "and by design cannot be, driver-signed -- it would fail this "
                         "gate correctly every time. If this run's real interview already "
                         "produced a driver-signed transcript, this phase's artifact is "
                         "already satisfied and this module never reaches this branch for "
                         "it (see the idempotent skip in sweep_run_dir).",
    # FIX 34 (MASTER Part 8): P0A-INTAKE joins the decline family. The launcher
    # seals working/copy/intake.json 0444 once --new consumes it
    # (launcher.seal_intake), so a worker "re-emitting" it would either raise
    # PermissionError mid-run (recorded in working/logs/intake_protection.jsonl)
    # or, pre-seal, overwrite the run's constitutional record with model-invented
    # intake data. Neither is acceptable: the real intake already exists from the
    # completed interview, its content reaches every phase as upstream context,
    # and changes flow exclusively through launcher.apply_intake_amendment
    # (Fix 32-verified owner approval). Declining costs nothing and can never
    # fabricate; it mirrors P-SP-INTAKE-TRACE's driver_only verdict -- a
    # non-driver-authored intake artifact is definitionally out of this module's
    # charter. (Its ARTIFACT_CONTRACTS entry above was rewritten to "produce
    # NOTHING" so even a flag-rolled-back path never teaches re-emit.)
    "P0A-INTAKE": "sealed_record: working/copy/intake.json is the run's sealed "
                  "constitutional record, written by the completed interview and "
                  "chmod 0444 by the launcher at --new (launcher.seal_intake; every "
                  "write attempt lands in working/logs/intake_protection.jsonl). "
                  "A model-authored re-emission would overwrite client interview "
                  "data with invented content pre-seal, or fail at the OS level "
                  "post-seal. The record already exists; every phase reads it as "
                  "upstream context; sanctioned changes go ONLY through "
                  "launcher.apply_intake_amendment (Fix 32-verified owner approval). "
                  "Nothing for a worker to author here, ever.",
    # Confirmed empirically during acceptance testing (not merely read from source):
    # 3 real DeepSeek dispatch attempts against the live gate all failed identically
    # on AF-SP-8Q-MISSING even with a schema-correct-looking payload, which led to
    # reading prove_sp_intake.py's _evaluate_turn_pacing()/_sign_turn_ledger() in
    # full. For a "runtime record" (any payload carrying an `answers` dict, which is
    # the ONLY shape _missing_questions() will actually credit -- top-level q1..q8
    # keys, the shape this module's own first contract attempt tried, are read as
    # the unrelated STATIC "questions[].id/prompt" spec shape and never match),
    # _evaluate_turn_pacing() then activates and hard-requires a
    # `turn_ledger_provenance` block whose `signature` is an HMAC-SHA256 over the
    # exact turn sequence, keyed by a constant this file publishes verbatim
    # (TURN_LEDGER_KEY) so any consumer can VERIFY it -- but the only legitimate
    # PRODUCER of that signature is deck-intake-driver.py, at the moment of a real,
    # paced, one-question-per-turn conversation. Computing a matching signature over
    # DeepSeek-invented turns would be manufacturing false provenance -- the exact
    # thing this gate's own module docstring calls "UNFAKEABLE" by design. This is
    # the P-SP-INTAKE-TRACE defect's twin, one phase earlier in the pipeline.
    "P-SP-INTAKE": "driver_only: build_deck._chk_sp_intake -> Skill 51's "
                   "prove_sp_intake.evaluate() requires an `answers` dict PLUS a "
                   "`turn_ledger_provenance.signature` that is a real HMAC-SHA256 over "
                   "the actual turn-by-turn conversation, produced only by "
                   "deck-intake-driver.py's real turn gate. A DeepSeek-authored record, "
                   "however well-formed, cannot legitimately carry that signature -- "
                   "computing one over invented turns would be forging conversation "
                   "provenance, not authoring content. If this run's real interview "
                   "already produced a compliant, driver-signed sp_intake.json, this "
                   "phase's artifact is already satisfied and this module never reaches "
                   "this branch for it.",
}

# ---------------------------------------------------------------------------
# Two manifest produces_artifact values are stale relative to their own
# verifier (spec S3, confirmed by direct read of phase_verifiers.py): the
# dispatcher must target what the VERIFIER actually checks, not the
# manifest's declared string, or it will pass existence and still fail
# substance.
# ---------------------------------------------------------------------------
ARTIFACT_TARGET_OVERRIDE: Dict[str, List[str]] = {
    "P-CONVERTER": [
        "working/copy/source_brief.json",
        "working/copy/source_brief.md",
        "working/converter/source_brief.md",
        "working/copy/source_brief.txt",
    ],
    "P-SP-CLAIM": ["working/copy/sp_claims.json"],
}

# Outcomes that mean "this dispatch failed and would fail again the same way".
# Only these can drive a phase to the BLOCKED retry ceiling; a benign repeat
# (already-satisfied / already-done) backs off but is never parked as a fault.
# "declined" is deliberately IN this set: a DECLINE_PHASES entry is a permanent
# verdict about what this module will never author (live-proven: 494 identical
# declines for P-SP-INTAKE in one run -- re-logging that forever is not a
# decision, it is a stuck record). Parking it writes a VISIBLE marker file and
# still auto-un-parks the moment the work order is reissued or state changes.
_FAILING_STATUSES = frozenset({"error", "exhausted", "declined"})

# ---------------------------------------------------------------------------
# Per-phase artifact contracts -- the EXACT, mechanical requirements each
# phase's real verifier enforces, read directly out of phase_verifiers.py /
# build_deck.py (never guessed, never copied from the manifest's looser
# prose). Handed to DeepSeek verbatim as "the output contract" (spec S5.3
# item 5) so the model can converge on a passing artifact instead of
# guessing at what a primary gate demands. This is not gaming the verifier
# -- it is the same information a human SOP would give the role; the
# verifier itself is still the one and only judge of the real output.
# ---------------------------------------------------------------------------
ARTIFACT_CONTRACTS: Dict[str, str] = {
    "P-0.5-RESEARCH": (
        "OUTPUT CONTRACT (mechanically enforced by build_deck._chk_research_brief / "
        "_chk_research_cited -- read this carefully, it is graded literally):\n"
        "1. File path: working/research/brief-<short-topic-slug>.md\n"
        "2. Near the top of the file, include the literal text `research_complete:true` "
        "(this exact token, colon, no space required).\n"
        "3. Structure the body as TWELVE headed sections, each starting on its own line "
        "with EXACTLY this format (case-insensitive but keep this casing): "
        "`## Category A: Niche Deck Structures` ... through `## Category L: Compliance "
        "Flags`. Use these twelve labels in order: A Niche Deck Structures, B Pricing & "
        "Value Benchmarking, C Supporting Statistics / Studies / White Papers, D External "
        "Corroboration, E Grounded Image Context, F Design + Hook + Pacing Best-Practices "
        "Research, G Credible Attributable Quotes, H Fact-Validation Ledger, I Objection "
        "Research, J Social-Proof Patterns, K Persuasion-Framework Validation, L Compliance "
        "Flags.\n"
        "4. Categories G, H, I, K, and L are HARD-GATED: each MUST have real, substantive "
        "body text (not a placeholder, not a one-line stub, not '[Output of SOP ...]') "
        "between its heading and the next '## ' heading. Write at least 3-5 sentences or "
        "list items of REAL content in each of G, H, I, K, L specifically.\n"
        "5. Cite at least 8 distinct http(s):// URLs across the whole document, covering "
        "AT LEAST 6 DISTINCT REGISTERED DOMAINS (not the same domain repeated). FIX 19: "
        "you have REAL web retrieval for this phase -- every URL you cite MUST come from "
        "the RETRIEVED SOURCES section supplied in the prompt (the engine actually "
        "fetched each page and recorded it in the retrieval ledger). Cite those exact "
        "canonical URLs, each with the supporting quote/stat you found there. NEVER "
        "invent a URL, NEVER cite a well-known organization's domain hoping one exists, "
        "and NEVER use localhost, example.com, bare IP addresses, or any "
        ".local/.internal/.test/.invalid domain -- a citation that is not in the "
        "retrieval ledger fails the gate outright.\n"
        "6. Categories G, H, and I specifically must EACH contain at least one of those "
        "cited URLs inline (not just listed once elsewhere in the document).\n"
        "7. Write categories B, D, E, F, J too (the SOP requires all twelve for a complete "
        "brief) even though the mechanical gate above only hard-fails on G/H/I/K/L."
    ),
    "P0B-PRIORITY": (
        "OUTPUT CONTRACT: valid JSON object at working/copy/priority_shift_spec.json. "
        "Per the attention-content-strategist SOP (Seven-P model, Eight-Move build "
        "sequence): include at minimum a `true_goal` string, a `priority_stack` array "
        "(ordered, each item a short label), and the eight build-move beats named in "
        "order. Write REAL, deck-specific content derived from the upstream intake/arc "
        "context supplied below -- never placeholder text."
    ),
    "P3-ARC": (
        "OUTPUT CONTRACT: valid JSON object at working/copy/arc_allocation.json. Per the "
        "offer-price-strategist SOP: a per-slide arc-section allocation (which narrative "
        "arc section each slide belongs to), a clear PEAK/APEX beat, and a clear ending "
        "beat (never a flat ending). If intake.json records pitch_included:false, do NOT "
        "include any offer/price/ladder content; otherwise include the value-stack/anchor/"
        "price-ladder beats and a re-pitch after the FINAL beat."
    ),
    "P-3.5-RESEARCH-MAP": (
        "OUTPUT CONTRACT: valid JSON object at working/research/research_map.json mapping "
        "specific researched facts/quotes/stats (from the research brief supplied below) "
        "to specific slide numbers/sections. Include at least 8 distinct mapped items when "
        "the research brief supports it."
    ),
    # FIX 34 (MASTER Part 8): the intake contract NEVER re-emits. The launcher
    # seals working/copy/intake.json 0444 the moment --new consumes it
    # (launcher.seal_intake, reason "dispatch-new-*"), so any attempt to write
    # it mid-run raises PermissionError at the OS level and the attempt lands in
    # working/logs/intake_protection.jsonl. Sanctioned intake changes go through
    # launcher.apply_intake_amendment() only (Fix 32-verified owner approval,
    # staged via intake.json.staging, one row in intake_amendments.jsonl, then
    # re-sealed). A P0A worker therefore READS the sealed intake as upstream
    # context and never writes the file -- and P0A-INTAKE is declined below in
    # dispatch_one (DECLINE_PHASES), the same driver_only verdict family as
    # P-SP-INTAKE-TRACE, so no model call is ever spent authoring a file the
    # engine will refuse to overwrite.
    "P0A-INTAKE": (
        "OUTPUT CONTRACT: NONE -- you do not write a file in this phase. "
        "working/copy/intake.json is the run's SEALED constitutional record: it was "
        "written once by the completed interview and sealed read-only (0444) when "
        "the job was created. It is provided as upstream context below for you to "
        "READ and reason over. You must NEVER re-emit, rewrite, or 'enrich' it: the "
        "file is immutable on disk, any write attempt fails, and the only sanctioned "
        "way intake data changes is the operator amendment channel "
        "(launcher.apply_intake_amendment with a verified owner approval). If the "
        "work order asks you to produce intake.json anyway, produce NOTHING -- "
        "answer with an empty output and let the dispatcher record the decline."
    ),
    # ROOT CAUSE #1 (live run pj_34a56a26caca04532ec6e9cba6, 2026-08-18): P4-COPY had no
    # entry here (fell back to GENERIC_CONTRACT) and, even with the exact verifier
    # failure reasons fed back on retry, repeatedly missed the SAME mechanical writing-
    # engine tags across 5 real attempts -- a generic "write good copy" instruction
    # never told the model these are literal, positionally-checked TAG lines, not just
    # a vibe. A first fix extracted the beat VOCABULARY verbatim from the real checkers
    # but described it as PROSE PHRASES to write ("villain, antagonist, the enemy, ...").
    # ROOT CAUSE #2 (live run pres-wave-e-zhc-1787175621, 2026-08-19): that fix was
    # itself WRONG about the mechanism. intelligence_engines_check.check_copy really
    # does scan prose substrings (VILLAIN_TOKENS / HERO_TOKENS / FELT_FRAME_TOKENS / a
    # `LADDER: <value>` field line) -- but pitch_engines_check.py's four beat checks
    # (chk_villain, chk_felt_stakes, chk_branded_method, chk_time_to_result) do NOT read
    # prose at all: pitch_engines_check._arc_tags_in_order() recognises ONLY the literal
    # marker syntax `<!-- ARC: TAG -->` or `[ARC:TAG]` via
    # `re.finditer(r'(?:<!--\s*ARC:\s*([^>]+?)\s*-->|\[ARC:\s*([^\]]+?)\s*\])', ...)`.
    # A deck with the exact prose phrases this contract previously taught, and ZERO ARC
    # markers, reproducibly fails AF-NO-VILLAIN / AF-NO-FELT-STAKES / AF-NO-BRANDED-
    # METHOD / AF-NO-TIME-TO-RESULT even though intelligence_engines_check passes clean
    # -- verified by running both real checkers against that live run's slides_copy.md
    # by hand (pitch_engines_check: 4 fails; intelligence_engines_check: 0). BOTH
    # checkers read this SAME file, by TWO DIFFERENT mechanisms -- so every beat below
    # now carries BOTH halves: the prose/field text intelligence_engines_check scans,
    # AND its own literal `<!-- ARC: TAG -->` marker for pitch_engines_check. Do not
    # "fix" this again by teaching only one half.
    "P4-COPY": (
        "OUTPUT CONTRACT -- TWO SEPARATE CHECKERS both grade this ONE file, by TWO "
        "DIFFERENT mechanisms, and BOTH must show zero problems:\n"
        "  (a) intelligence_engines_check.check_copy scans PROSE SUBSTRINGS and a "
        "`LADDER: <value>` metadata field line.\n"
        "  (b) pitch_engines_check.check_copy scans ONLY literal marker syntax: "
        "`<!-- ARC: TAGNAME -->` (preferred) or `[ARC:TAGNAME]` -- it does NOT read "
        "prose. A sentence containing the word 'villain' with no `<!-- ARC: VILLAIN "
        "-->` marker on that block is INVISIBLE to pitch_engines_check and WILL fail "
        "AF-NO-VILLAIN even though it reads as correct writing.\n"
        "Every beat below therefore needs BOTH halves, on the SAME slide block: the "
        "descriptive prose/field AND its own literal ARC marker. Multiple tags may "
        "share one marker, space- or comma-separated: `<!-- ARC: PROMISE HERO -->`. "
        "This is LITERAL and POSITIONALLY-CHECKED, not a vibe.\n"
        "1. File path: working/copy/slides_copy.md. Format: each slide is its own block "
        "starting with a line containing ONLY `SLIDE <n>` (e.g. `SLIDE 1` on its own "
        "line, exactly that many spaces, no markdown '##', no colon), in slide order, "
        "1 through the deck's real slide count. ARC markers sit on their own line "
        "anywhere inside the block they belong to.\n"
        "2. MASTER ARC ORDER (governs every beat below -- pitch_engines_check's "
        "per-beat ordering checks AND intelligence_engines_check's AF-NARRATIVE-HARMONY "
        "both fail if any pair here lands out of order): HOOK (recurs throughout) -> "
        "VILLAIN -> FELT_STAKES -> PROMISE -> PRICE beats (ANCHOR/DROP1/DROP2/DROP3/"
        "FINAL, in that rung order) -> RECAP. Each beat's FIRST occurrence must land in "
        "this relative slide order; only beats that are actually present are checked.\n"
        "3. HOOK: the canonical hook line from intake.json (see upstream context) must "
        "recur VERBATIM on 3-4 dedicated slide blocks (never fewer than 3, never more "
        "than 4), and never twice within one block. On EACH of those 3-4 hook-carrying "
        "blocks ALSO add the field line `HOOK_REFRAIN: yes` (own line, exact token) -- "
        "P4-PROMPT's own contract reads this field to know which slides may legally "
        "bake the hook into the rendered image; without it, P4-PROMPT is told to bake "
        "the hook nowhere at all.\n"
        "4. VILLAIN beat: on ONE slide block, write prose naming the antagonist using "
        "one of: villain, antagonist, the enemy, the real enemy, the thing stopping, "
        "what's holding you back, the obstacle, the lie, the trap, the broken system, "
        "the old way is the villain -- AND add the literal marker "
        "`<!-- ARC: VILLAIN -->` on that same block. This must be the FIRST slide "
        "(lowest slide number) that carries either the VILLAIN prose/marker or the "
        "PROMISE prose/marker (point 6) -- villain always precedes promise/hero.\n"
        "5. FELT_STAKES beat: on ONE slide block, BEFORE any price/ladder beat (point "
        "7), write prose pairing a concrete number (a real figure, never filler) with "
        "one of: mornings left, days left, years left, running out, before it's too "
        "late, every day you wait, you will lose, cost you, while you wait, never get "
        "-- AND put the literal marker `<!-- ARC: FELT_STAKES -->` as the FIRST line of "
        "that block's body, so the number and the loss-frame phrase both land within "
        "the ~600 characters immediately AFTER the marker (pitch_engines_check scans a "
        "fixed window starting at the marker's position, not the whole block -- placing "
        "the marker late in the block can push your own qualifying text outside the "
        "window even though it is in the same block).\n"
        "6. PROMISE beat (the hero/solution turn): on ONE slide block, write prose "
        "using one of: hero, the solution, the breakthrough, the way out, the answer, "
        "the promise, the new way, you become, the transformation, the path forward -- "
        "AND add the literal marker `<!-- ARC: PROMISE HERO -->` on that same block "
        "(both tokens in one marker -- HERO lets pitch_engines_check's villain-ordering "
        "check see this beat explicitly rather than relying on it being skipped). This "
        "slide must be LATER than the VILLAIN slide and EARLIER than every price/ladder "
        "slide (point 7).\n"
        "7. PRICE / ladder beats (only if intake.json's pitch_included is not false): "
        "for every rung of the price ladder that actually appears (ANCHOR, then "
        "BUILDUP if used, then DROP1, DROP2, DROP3 as real pricing drops occur, then "
        "FINAL), put BOTH the existing field line `LADDER: ANCHOR` / `LADDER: BUILDUP` "
        "/ `LADDER: DROP1` / `LADDER: DROP2` / `LADDER: DROP3` / `LADDER: FINAL` (exact "
        "token, own line -- read by intelligence_engines_check) AND a literal ARC "
        "marker carrying that SAME token on that SAME block, e.g. "
        "`<!-- ARC: ANCHOR -->` on the ANCHOR block, `<!-- ARC: DROP1 -->` on the DROP1 "
        "block, `<!-- ARC: FINAL -->` on the FINAL block (BUILDUP needs no ARC marker; "
        "pitch_engines_check never reads that token). If this deck is NOT using the "
        "priced-ladder structure, a bare `$` price figure anywhere satisfies "
        "intelligence_engines_check's price-beat detector on its own, but "
        "pitch_engines_check's promise-before-price check specifically keys off these "
        "ARC markers -- add at least one, typically `<!-- ARC: FINAL -->` on the single "
        "price-reveal slide, even for a flat-price deck, so that check can see the beat "
        "at all. Every price/ladder slide must be LATER than the PROMISE slide.\n"
        "8. Cadence loop between price rungs (AF-CADENCE -- NOTE: this specific check "
        "currently DEFERS pipeline-wide because no phase yet writes "
        "working/copy/price_ladder.json; write it correctly anyway so the deck already "
        "complies the day that phase is wired, but do not lose sleep chasing it today). "
        "Between EACH adjacent PAIR of DROP/FINAL-type markers you tagged in point 7 "
        "(DROP1<->DROP2, DROP2<->DROP3, DROP3<->FINAL -- the check does NOT treat "
        "ANCHOR as a rung boundary), place, somewhere in that span and in this relative "
        "order, a `<!-- ARC: VALUE_ADD -->` beat (restate what they get), a re-used "
        "`<!-- ARC: PROMISE -->` beat (reaffirm the transformation), a "
        "`<!-- ARC: REPITCH_MINI -->` beat (a short re-pitch line), and a "
        "`<!-- ARC: COST_OF_INACTION -->` beat (what not acting now costs them) -- in "
        "that order.\n"
        "9. COST_OF_INACTION also needs at least one standalone beat outside the "
        "cadence loop (AF-NO-COST-OF-INACTION also currently defers for the same "
        "price_ladder.json reason as point 8 -- write it anyway): add "
        "`<!-- ARC: COST_OF_INACTION -->` somewhere in the deck (the point-8 occurrence "
        "satisfies this too) stating, in prose, the real cost of not acting.\n"
        "10. NAMED_METHOD beat -- READ intake.json's named_methodology field FIRST "
        "(see upstream context). If it has a real, already-declared value: quote it "
        "verbatim in the prose on the slide that introduces it AND add "
        "`<!-- ARC: NAMED_METHOD -->` on that same block. If intake.json's "
        "named_methodology is empty or absent: do NOT add the marker and do NOT invent "
        "a method name to fill it -- pitch_engines_check treats a tagged method beat "
        "with no intake/owner backing (AF-METHOD-FABRICATED) as a WORSE fail than "
        "having no method beat at all (AF-NO-BRANDED-METHOD); silent fabrication is "
        "explicitly banned by that checker's own doctrine and neither path this "
        "contract controls can make that specific check pass without a real value in "
        "intake.json. Instead add the line `<!-- QC-NOTE: AF-NO-BRANDED-METHOD -- "
        "intake.json has no named_methodology; needs a real branded-method name with "
        "owner approval upstream of this copy phase -->` so the QC specialist sees the "
        "real, upstream cause instead of a vague copy fail.\n"
        "11. EXPECTATION beat -- READ intake.json's time_to_result field FIRST (see "
        "upstream context). If it has a real value: put `<!-- ARC: EXPECTATION -->` on "
        "the slide that sets the expectation, followed within that block by prose "
        "stating that SAME duration with a day/week/month/session/hour/minute unit "
        "word within ~600 characters of the marker (e.g. '8 weeks to your first real "
        "result'). Never invent a different timeframe than intake.json states. If "
        "intake.json's time_to_result is empty or absent: pitch_engines_check checks "
        "`intake.time_to_result` directly and this specific sub-check is MECHANICALLY "
        "UNSATISFIABLE from copy content alone no matter what is written here -- still "
        "add an honest `<!-- ARC: EXPECTATION -->` beat with a real duration if one is "
        "independently stated elsewhere in intake.json (e.g. a stated program length), "
        "but also add `<!-- QC-NOTE: AF-NO-TIME-TO-RESULT -- intake.json has no "
        "time_to_result field; the fix belongs upstream of this copy phase -->` so the "
        "gap is visible rather than silently eaten.\n"
        "12. RECAP beat: AFTER the LAST price/ladder beat (a later slide number), "
        "include a block containing one of: recap, to recap, re-pitch, repitch, "
        "here's everything, everything you get, everything you're getting, in summary, "
        "let's recap, quick recap, value stack, stack recap -- restating the value "
        "stack and the price. No ARC marker needed here; pitch_engines_check has no "
        "RECAP check (only intelligence_engines_check's AF-NO-RECAP reads this, from "
        "prose alone).\n"
        "13. AF-C8 DENSITY CEILING (root cause: live run "
        "pres-wave-e-v3-1787240658, 2026-08-20 -- P1Q-COPY-QC auto-failed with "
        "'AF-C8 density ceiling exceeded on slide 20 (34 words vs 30 max; "
        "offer-stack component list)' and 'AF-C8 density ceiling exceeded on "
        "slide 25 (37 words vs 30 max; re-pitch recap list)' because this "
        "contract never told the copywriter the ceiling the QC Specialist "
        "actually grades against -- confirmed by hand-counting both real "
        "offending slides: HEADLINE(7) + SUBHEAD(4) + 5 SUPPORTING lines(23) "
        "= 34 on slide 20; HEADLINE(4) + SUBHEAD(5) + 6 SUPPORTING lines(28) "
        "= 37 on slide 25 -- exact matches). Per qc-specialist-presentations."
        "md's AF-C8 doctrine (graded by the QC Specialist role reading "
        "slides_copy.md, NOT by any Python gate -- there is no mechanical "
        "AF-C8 check in this codebase, so this contract is the ONLY place "
        "the writer can learn the rule before it costs a retry), EVERY slide "
        "has a hard ceiling of 30 TOTAL words, summed across ALL on-slide "
        "text fields. In THIS contract's own field format (point 1), the "
        "fields that COUNT toward that 30-word total are exactly: HEADLINE, "
        "SUBHEAD, and every line under SUPPORTING. The fields that do NOT "
        "count: SECTION, PURPOSE, ARCHETYPE, LADDER, EMPHASIS, PROOF USED, "
        "PEOPLE, HOOK_REFRAIN, TEXT_ANCHOR, and HOOK VARIANT are internal "
        "production metadata never rendered on the slide; PRESENTER NOTE is "
        "spoken narration the audience hears but never sees and is also "
        "excluded. AF-C8 is MECHANICAL and INDEPENDENT of every per-field "
        "wording rule above -- a slide can satisfy points 1-12 perfectly and "
        "STILL auto-fail AF-C8 purely on the summed total, exactly as both "
        "real offenders did (each field individually read fine; the SUM did "
        "not). Practical rule for value-stack / offer-stack / re-pitch / "
        "recap slides (point 12) whose full component list will not fit "
        "under 30 on-slide words: do NOT enumerate every line item in "
        "SUPPORTING. Put the itemized breakdown in the PRESENTER NOTE "
        "(exactly where both QC-failed live slides had ALREADY duplicated "
        "it) and leave the on-slide SUPPORTING field carrying only the "
        "running tally and the price -- the slide shows the number, the "
        "presenter's voice carries the list.\n"
        "14. CODE MAP for points 3-12 (the mechanical index appended at the end of "
        "this contract lists every code by name; these are the ones points 3-12 "
        "already teach, named here so a verifier reason string maps straight back "
        "to the point that fixes it): point 3's 3-4 dedicated hook beats are "
        "AF-NO-HOOK-REFRAIN (fewer than 3) and AF-HOOK-1 (more than 4, the deck "
        "veto), and repeating the hook twice inside ONE block is AF-HOOK-OVERSTAMP; "
        "point 5 is AF-NO-FELT-STAKES; point 4 is AF-NO-VILLAIN; points 6+7's "
        "promise-before-every-price-beat ordering is AF-PRICE-BEFORE-PROMISE; point "
        "12 is AF-NO-RECAP; the whole point-2 arc is AF-NARRATIVE-HARMONY.\n"
        "15. GUARANTEE (AF-GUARANTEE-GENERIC): if the deck carries a guarantee at "
        "all, it must NOT reduce to a bare refund template. 'Money-back', "
        "'30-day', 'refund', 'satisfaction guaranteed' and 'no-questions-asked', "
        "standing alone, are mechanically detected as generic and auto-fail. Write "
        "the guarantee as a felt, client-specific frame -- what SPECIFICALLY they "
        "keep, get back, or never risk in THIS offer's own terms, sourced from the "
        "upstream intake -- with the refund mechanics as a clause inside it, never "
        "as the whole statement.\n"
        "16. PER-FIELD CHARACTER BANDS (AF-COPY-BAND) and COMPARISON TABLES "
        "(AF-OBI-6) -- both are declared gate codes for THIS phase. Every line you "
        "write here is carried into the render copy and measured in CHARACTERS, not "
        "words: HEADLINE 12-60 chars, SUBHEAD 20-110 chars when present, KICKER <=40 "
        "chars when present, at most 3 bullets of 8-30 chars each, and 40-180 chars "
        "for the slide total (12-180 for a hook or section-banner slide). Note the "
        "FLOOR as well as the ceiling: a 6-character headline fails just as hard as "
        "a 70-character one. This is a SEPARATE measure from AF-C8's 30-word total "
        "(point 13) and both are enforced -- a slide must satisfy the character "
        "bands AND the word ceiling. Any comparison / before-after / us-vs-them "
        "table is capped at 2 ROWS (AF-OBI-6); a third row auto-fails.\n"
        "17. RESEARCH MUST BE WOVEN, VERBATIM AND WIDELY (AF-RESEARCH-WEAVE, "
        "AF-RESEARCH-REACHES-RENDER). research_map.json (supplied in the upstream "
        "context) assigns real research items to specific slides. Reproduce each "
        "mapped item's ANCHOR TOKEN verbatim in that slide's on-slide copy -- not "
        "paraphrased, not moved to the PRESENTER NOTE, and never funnelled into one "
        "'proof' slide: the weave gate requires research on at least 60% of "
        "non-exempt content slides, and the render gate re-checks that the SAME "
        "anchor survived into the rendered copy. A statistic that exists only in "
        "your narration fails both gates."
    ),
    "P-SP-CLAIM": (
        "OUTPUT CONTRACT: valid JSON object at working/copy/sp_claims.json recording that "
        "this deck's presentation_type/deck_type has been explicitly claimed as a signature "
        "presentation (deck_type: 'signature_presentation'), matching intake.json."
    ),
    # NOTE: P-SP-STRUCTURE has no static entry here (mirrors the P-SP-INTAKE
    # no-entry comment below) -- unlike every other phase, its contract is NOT
    # run-invariant: points 2/3/6 (the per-phase slide floors, the client-exact
    # override fields, and the total slide count) depend on THIS run's own
    # client-exact slide count, which changes deck to deck. A first fix here
    # (2026-08-18) hardcoded one live run's own numbers (25 slides, scaled
    # floors 3/3/9/10) directly into this shared table -- a defect a later
    # audit unit found and fixed (2026-08-20): every OTHER run, including the
    # common case of NO client-exact override at all (which must get the
    # sacred >=100-slide floor, unscaled), was being handed that same
    # "write exactly 25, floors 3/3/9/10" instruction verbatim, regardless of
    # its own real slide count. compose_prompt() now special-cases phase_id ==
    # "P-SP-STRUCTURE" and calls _sp_structure_contract(run_dir) instead of
    # this dict, which derives the text fresh per run -- see that function and
    # _sp_read_client_exact_count / _sp_scaled_floor immediately below
    # GENERIC_CONTRACT for the full derivation and its sourcing.
    # PROACTIVE (found while investigating fault #9, live run
    # pj_34a56a26caca04532ec6e9cba6, 2026-08-18, iteration 3): phase_verifiers.verify()
    # for these three QC-report phases does NOT itself read the report file (it
    # re-checks the upstream artifact instead, e.g. P1Q-COPY-QC re-runs the same
    # slides_copy.md engine checks P4-COPY already passed) -- so a generic/sloppy
    # report would still let the STATE.JSON phase transition to done. But
    # build_deck._chk_copy_qc / _qc_report_gate (the SAME report-shape gate, reused
    # for prompt/typography/speech) is a SEPARATE, much stricter check the full
    # canonical-entry preflight runs before assembly -- it requires an EXACT gate
    # string, a real per-criterion average >= 8.5 that is not inflated over its own
    # cited criteria, zero triggered autofails, pass:true, and PROVEN independent-
    # reviewer provenance (self/builder-graded reports are refused by name). Writing
    # this correctly NOW avoids a much-later, harder-to-diagnose block deep in the
    # render/assembly path. Extracted verbatim from build_deck.py's _qc_report_gate /
    # _qc_independence_reason / _qc_report_substance_problems.
    "P1Q-COPY-QC": (
        "OUTPUT CONTRACT (mechanically enforced LATER by build_deck._chk_copy_qc at "
        "the canonical-entry preflight -- write it right the first time). File path: "
        "working/qc/copy_qc_report.json (a single JSON object). Required top-level "
        "fields, EXACTLY:\n"
        "1. `gate`: the exact string `Phase 1Q` (case-sensitive, no variation).\n"
        "2. `criteria`: an array of objects, each `{\"name\": <criterion>, \"score\": "
        "<number 1-10>}`, covering the real writing-engine criteria you actually "
        "checked against slides_copy.md (hook cadence, audience-first care, one-big-"
        "idea-per-slide, density, felt-stakes, villain-before-hero, promise-before-"
        "price, etc.) -- at least 6 criteria, each scored HONESTLY from the real "
        "content (see upstream slides_copy.md).\n"
        "3. `average`: the arithmetic mean of every `criteria[].score`, rounded to 1 "
        "decimal -- must be >= 8.5 AND must NOT exceed that real mean by more than "
        "1.0 (a headline score inflated over your own cited criteria is rejected).\n"
        "4. `triggered_autofails`: `[]` (empty array) -- if slides_copy.md genuinely "
        "still has an open AF-* issue, name it here instead of inflating scores to "
        "hide it.\n"
        "5. `pass`: boolean `true` (only if average >= 8.5 and triggered_autofails is "
        "empty -- these must be mutually consistent, never pass:true over a failing "
        "score).\n"
        "6. `qc_independence`: an object `{\"graded_by\": \"qc-specialist-"
        "presentations\", \"independent\": true, \"self_graded\": false}` -- `graded_by` "
        "must be the QC role, NEVER `slide-copywriter`/`build_deck.py`/`self`/"
        "`builder` (those identities are the artifact's own author and are refused "
        "as self-graded).\n"
        "7. Never include the substrings 'word_count_band', 'words_in_band', "
        "'typography_overlay_readiness', or any word-count/overlay rubric language -- "
        "those are eliminated legacy generator signatures and cause automatic "
        "rejection regardless of your scores."
    ),
    "P-PROMPT-QC": (
        "OUTPUT CONTRACT (mechanically enforced LATER by build_deck's "
        "_qc_report_gate at the canonical-entry preflight -- write it right the "
        "first time). File path: working/qc/prompt_qc_report.json (a single JSON "
        "object). Same shape and rules as the P1Q-COPY-QC contract (criteria array, "
        "honest average, triggered_autofails, pass:true, qc_independence with "
        "graded_by='qc-specialist-prompt-presentations', no foreign rubric "
        "language) with ONE difference: `gate` must be the exact string "
        "`Phase Prompt-QC`. Grade the real per-slide prompts in working/prompts/ "
        "against length (9,000-18,000 chars), the negative-class block, spelling-"
        "lock, and verbatim-copy-baked criteria -- never rubber-stamp a thin prompt."
    ),
    "P-TYPO-QC": (
        "OUTPUT CONTRACT (mechanically enforced LATER by build_deck's "
        "_qc_report_gate at the canonical-entry preflight -- write it right the "
        "first time). File path: working/qc/typography_qc_report.json (a single "
        "JSON object). Same shape and rules as the P1Q-COPY-QC contract (criteria "
        "array, honest average, triggered_autofails, pass:true, qc_independence "
        "with graded_by='qc-specialist-typography-presentations', no foreign rubric "
        "language) with ONE difference: `gate` must be the exact string "
        "`Phase Typography-QC`."
    ),
    # PROACTIVE (found before P4-PROMPT was ever reached this run, live run
    # pj_34a56a26caca04532ec6e9cba6, 2026-08-18, iteration 3): extracted verbatim
    # from build_deck.py's check_prompt_qc_deterministic + rich_prompt_quality_
    # problems + intelligence_engines_check.check_prompts (the REAL per-slide
    # prompt gate this module's own _verify_single_prompt calls). One dispatch of
    # this contract authors ONE slide at a time (see _dispatch_prompt_phase) --
    # the per-slide scoping line is prepended by that function, not here.
    "P4-PROMPT": (
        "OUTPUT CONTRACT (mechanically enforced by build_deck.check_prompt_qc_"
        "deterministic -- LITERAL, MECHANICALLY-CHECKED requirements, every one of "
        "these is graded by a token/regex scan of your output, not a vibe):\n"
        "1. LENGTH: 9,000-18,000 characters (stripped of leading/trailing "
        "whitespace). Under 9,000 is a fatal fail; do NOT pad with filler to hit "
        "the floor -- every added sentence must be real, specific art direction.\n"
        "2. REQUIRED STRUCTURAL BLOCKS, all three present verbatim (case-"
        "insensitive): a layout header starting `[ARCHETYPE` (e.g. `[ARCHETYPE: "
        "A2 recognition]`); a final block headed exactly `DO-NOT BLOCK` (a list of "
        "things the render must NOT do); and at least one literal `Do not ` "
        "imperative sentence inside that block.\n"
        "3. THE DO-NOT BLOCK must name ALL EIGHT of these defect classes "
        "(paraphrase freely, but each class needs its OWN sentence using language "
        "recognizably matching it): (a) garbled/misspelled text -- e.g. 'render "
        "every quoted text string exactly as written, letter-for-letter, never "
        "garbled or misspelled'; (b) logo mutation -- 'never redraw, recolor, or "
        "restyle the logo/monogram/tagline lockup'; (c) placeholder/bracket tokens "
        "-- 'no bracketed placeholder tokens, no [TBD], nothing marked pending or "
        "owner to confirm'; (d) image narration/presenter/meta -- 'no presenter "
        "line, no spoken-script text, no stage direction, no self-talk, no "
        "description of the picture baked into the image, never the word "
        "\"webinar\"'; (e) anatomical artifacts -- 'no fused fingers, no malformed "
        "or asymmetric hands, no distorted facial features, no mismatched eyes, no "
        "extra limbs, no over-smoothed skin, natural body proportions'; (f) "
        "background competing with text -- 'background must never compete with "
        "the text zone, no busy or cluttered high-detail background behind any "
        "text, preserve negative space and legibility'; (g) demographic/skin-tone "
        "fidelity -- 'render the stated skin tone faithfully, never lighten, "
        "ashen, or desaturate; no mono-cast representation'; (h) carried-forward "
        "universal baseline -- 'no watermark, no emoji, no clipart, no default "
        "system font (Calibri/Arial/Times New Roman), no UI artifacts, no pure-"
        "black fills, no em dash character anywhere'.\n"
        "4. SPELLING-LOCK: include a literal phrase such as 'render every quoted "
        "text string exactly as written, letter-for-letter' or 'spelling-lock: "
        "this exact string reads exactly as written' pinning the on-slide text.\n"
        "5. VERBATIM COPY BAKED: quote the slide's ACTUAL headline (and subhead/"
        "supporting line if it has one) from slides_copy.md VERBATIM, word for "
        "word, inside the prompt body (in quotes, as the text to render) -- never "
        "paraphrase the copy; the exact string must appear character-for-character "
        "(whitespace-normalized) or the image will not carry the approved words.\n"
        "6. DENSITY (four concrete specificity signals, all required): a brand "
        "palette color as a 6-digit HEX code in `#RRGGBB` form; an explicit "
        "typography SIZE token (e.g. '96pt', '42px'); a COMPOSITION/zone "
        "instruction (e.g. 'rule of thirds', 'left third', 'safe margin', "
        "'quadrant', 'negative space', 'focal point' -- 'centered' alone does NOT "
        "count); and at least 220 DISTINCT words across the whole prompt (a long "
        "prompt that repeats one paragraph to pad length fails this -- write real, "
        "varied, non-repeating specificity throughout).\n"
        "7. IF this slide's PEOPLE field (in slides_copy.md / sp_structure.json) "
        "is yes/carries a human subject, ALSO include: (a) FACIAL -- one explicit "
        "expression term, not bare 'smiling' (use e.g. 'half-smile', 'soft "
        "confident smile', 'brow tension', 'shoulders down', 'settled', "
        "'resolved', 'that's me' recognition beat, 'direct to camera'); (b) "
        "LIGHTING -- a key/fill/rim light direction (e.g. 'key light from camera "
        "left, soft fill, rim light separating hair from background') AND a "
        "separate hair/rim separation-light token appropriate to the subject's "
        "skin tone; (c) HAIR -- one specific, age-appropriate hairstyle "
        "descriptor (e.g. 'natural coils', 'locs', 'tapered fade', 'silk press', "
        "'low bun', 'waves') -- never a generic 'hair' with no style named.\n"
        "8. IF this slide's prompt states any real-world SETTING/scene (a room, "
        "office, kitchen, studio, exterior), it ALSO needs a believability "
        "justification clause (e.g. 'a normal home office, not a luxury "
        "penthouse, because this is what fits an owner running the business "
        "solo' / 'their actual station, believable for the scene').\n"
        "9. HOOK LINE: intake.json's canonical hook string (see upstream "
        "context) may appear BAKED VERBATIM into this slide's prompt AT MOST "
        "ONCE, and ONLY if this is one of the 3-4 dedicated hook-carrying slides "
        "named in slides_copy.md's `# HOOK-CARRYING SLIDES:` comment or this "
        "slide's own `HOOK_REFRAIN: yes` field -- if this slide is not one of "
        "those, do NOT bake the hook line into the image at all. NEVER place the "
        "hook inside anything described as a footer / bottom band / bottom strip "
        "-- it is a dedicated typographic beat, never a footer stamp.\n"
        "10. Output ONLY the prompt body for the ONE slide named in the scoping "
        "instruction above -- no markdown fences, no slide-number header line, no "
        "commentary before or after."
    ),
    # NOTE: P-SP-INTAKE has no contract entry -- confirmed during acceptance testing
    # to be driver_only (see DECLINE_PHASES above); this module honestly declines it
    # rather than guessing at a schema it cannot legitimately satisfy.
}


# ---------------------------------------------------------------------------
# CONTRACT COMPLETENESS (the class fix, not the instance).
#
# THE DEFECT: every rule in the hand-written contract above had to be noticed
# by a human and typed in. The rules that judge the artifact live somewhere
# else entirely (phase_verifiers -> intelligence_engines_check /
# pitch_engines_check, build_deck's _chk_* preflights, PIPELINE-MANIFEST's
# gate_codes and 181-entry autofails registry). Nothing tied the two together,
# so the author wrote BLIND against part of its own rule set and every missing
# rule cost one full, PAID re-author to discover. Measured live on run
# pres-wave-e-v3-1787240658 (2026-08-20): four serial P4-COPY blocks
# (AF-NO-FELT-STAKES, AF-NO-RECAP, AF-NO-VILLAIN, AF-NARRATIVE-HARMONY) plus
# AF-C8 at P1Q-COPY-QC -- each discovered only after the previous one was
# fixed. Serial discovery across 181 codes cannot converge.
#
# THE FIX: derive the constraint set from the code that judges, at import
# time, and append it. presentation_job/contract_introspect.py does the
# derivation (and documents its scope rule); this block only wires the result
# into the one string P4-COPY is dispatched with. The hand-written points
# above are NOT replaced -- they teach the literal ARC-marker syntax and field
# names that no failure message contains. The generated index is the FLOOR
# (nothing reachable is ever unstated again); the prose is the ceiling.
#
# tests/test_contract_completeness.py fails RED when a rule exists on the
# judging path but is absent from the contract -- including a rule added
# later, which is the whole point.
# ---------------------------------------------------------------------------
CONSTRAINT_INDEX_MARKER = "=== MECHANICAL CONSTRAINT INDEX (auto-derived) ==="

#: True when the P4-COPY contract carries a real, derived constraint index.
#: False means the derivation failed and the model got the loud fallback
#: notice instead of the rule list -- a state the drift test refuses to allow.
P4_COPY_CONTRACT_DERIVED: bool = False

#: Populated with the IntrospectionError text when derivation fails.
P4_COPY_CONTRACT_DERIVATION_ERROR: Optional[str] = None


def _compose_p4_copy_contract(base: str) -> str:
    """Append the AF-C8 carve-out (read from doctrine) + the derived index.

    Never raises. A derivation failure must not take the engine down mid-run,
    but it must ALSO never degrade quietly into "there are no other rules":
    the fallback text tells the model, in the prompt, that its rule list could
    not be enumerated, and P4_COPY_CONTRACT_DERIVED goes False so the test
    suite catches it on the next run."""
    global P4_COPY_CONTRACT_DERIVED, P4_COPY_CONTRACT_DERIVATION_ERROR
    try:
        prose, carve_out = _ci.af_c8_doctrine()
        index = _ci.render_constraint_index()
    except Exception as exc:  # noqa: BLE001 -- fail LOUD-in-prompt, not silent
        P4_COPY_CONTRACT_DERIVED = False
        P4_COPY_CONTRACT_DERIVATION_ERROR = repr(exc)
        return (
            base
            + "\n\n"
            + CONSTRAINT_INDEX_MARKER
            + "\n!! UNAVAILABLE -- presentation_job.contract_introspect could not read "
            "the judging path for this artifact ("
            + repr(exc)
            + "). The complete list of autofail codes you are graded by CANNOT be "
            "shown in this prompt. Do not read that as 'there are no other rules': "
            "treat every rule in the department's MASTER-QC-AUTOFAIL-RULESET as live "
            "and write to the strictest reading of the points above."
        )
    P4_COPY_CONTRACT_DERIVED = True
    P4_COPY_CONTRACT_DERIVATION_ERROR = None
    return (
        base
        + "\n18. AF-C8 ARCHETYPE CARVE-OUT -- value-stack / offer-stack slides. "
        "Quoted verbatim from the department's MASTER-QC-AUTOFAIL-RULESET (read "
        "from disk at engine start, so this contract can never state a ceiling the "
        "ruling no longer holds). This does NOT relax point 13 for ordinary "
        "slides:\n"
        + prose
        + "\n"
        + carve_out
        + "\n\n"
        + CONSTRAINT_INDEX_MARKER
        + "\n"
        + index
    )


ARTIFACT_CONTRACTS["P4-COPY"] = _compose_p4_copy_contract(ARTIFACT_CONTRACTS["P4-COPY"])


GENERIC_CONTRACT = (
    "OUTPUT CONTRACT: write the exact artifact file(s) named in the work order below at "
    "the exact path(s) given. If the target is JSON, it MUST be syntactically valid JSON "
    "with real, substantive, deck-specific content (never a placeholder, never a stub, "
    "never '[TODO]'). If the target is Markdown/text, it must be real prose long enough "
    "to be substantive (not a one-line stub)."
)


# ---------------------------------------------------------------------------
# P-SP-STRUCTURE's contract, derived PER RUN (fix for the defect described in
# the "NOTE: P-SP-STRUCTURE has no static entry" comment above, inside
# ARTIFACT_CONTRACTS). Only points 2/3/6 of the contract text are run-
# dependent (the per-phase slide floors, the client-exact override fields,
# and the total slide count) -- every other point (1, 4, 5, 7, 8, 9, 10) is
# genuinely identical for every signature deck and is reproduced VERBATIM
# from the original hand-written text below.
#
# The SACRED per-phase floors and the SACRED default slide-count floor are
# read verbatim from 51-signature-presentation/structure/sp_structure.json's
# own `phases[].min_slides` / `slide_floor.default_minimum` -- per that
# ledger's own description ("Derived verbatim from MASTERDOC Prime
# Directives; never floored or reinterpreted"), these four numbers and the
# phase order are genuine constants across EVERY signature deck, unlike the
# scaled/derived numbers that were wrongly frozen to one run below. Mirroring
# them here (rather than reading the ledger file at runtime) matches
# prove_sp_structure.py's own pattern of shipping this same sacred JSON as
# its default-structure fallback; a future change to that ledger's four
# min_slides values would need a matching update here, exactly as it would
# need one in the ledger-reading prover itself.
_SP_SACRED_PHASE_ORDER: Tuple[str, ...] = ("avatar", "story", "teaching", "pitch")
_SP_SACRED_PHASE_FLOORS: Dict[str, int] = {
    "avatar": 11, "story": 13, "teaching": 36, "pitch": 40,
}
_SP_SACRED_DEFAULT_MIN = 100


def _sp_scaled_floor(min_slides: int, exact: int, default_min: int = _SP_SACRED_DEFAULT_MIN) -> int:
    """EXACT clone of prove_sp_structure.verify()'s CHECK D scaling arithmetic
    (51-signature-presentation/scripts/prove_sp_structure.py):
        _sp_scale = exact / default_min                     # only when exact > 0
        floor = max(1, int(round(min_slides * _sp_scale)))
    Kept byte-identical -- same float division, same round()/int() calls, same
    operand order -- so this module's STATED floor and the prover's COMPUTED
    floor can never disagree for the same (min_slides, exact) input.
    """
    scale = exact / default_min
    return max(1, int(round(min_slides * scale)))


def _sp_read_client_exact_count(run_dir: Path) -> Tuple[Optional[int], str]:
    """Read the client's declared exact slide count for THIS run -- never a
    hardcoded number baked into a shared contract (that was the defect this
    replaces). Returns (count_or_None, source_description).

    Priority 1: working/copy/sp_intake.json's OWN `client_overrode_slide_floor`
    / `client_exact_slide_count` fields. These are not a guess at a key name --
    they are the EXACT two field names
    51-signature-presentation/structure/sp_structure.json's own
    `slide_floor.client_exact_override` block declares (`flag`/`count_field`),
    sourced from `working/copy/sp_intake.json` per that same ledger entry's own
    `source` key, and written there by the Signature Presentation Architect
    during intake per signature-presentation-architect.md SOP 9.1 step 7 ("Log
    a client-exact slide count now... write `client_overrode_slide_floor: true`
    + `client_exact_slide_count: <N>` into `sp_intake.json`"). This IS how the
    rest of the pipeline sources the override -- already normalized to a clean
    bool + positive int, zero free-text parsing required, and it is produced
    by P-SP-INTAKE, the phase that always runs immediately before
    P-SP-STRUCTURE (see phases.py's _SP_ONLY_PHASE_IDS ordering), so it is
    reliably present by the time this contract is composed.

    Priority 2 (fallback -- sp_intake.json missing, unreadable, or simply
    didn't log an override): the raw client answer at working/copy/intake.json
    `deck_brief.SLIDE_COUNT` -- the REAL key, confirmed against
    intake/deck-intake-questions.json's slide_count question
    (`"storeOn": "SLIDE_COUNT"`, section `deck-intake` -> mapped to the
    `deck_brief` object) and intake/interview-app/bridge/intake_writer.py's
    `ID_TO_FIELD["slide_count"] = "SLIDE_COUNT"` mapping. This is FREE TEXT
    ("Exactly 25 slides, no more, no less", "40", "no preference, let the
    duration math decide", or the key absent entirely when unasked/unanswered)
    -- the first standalone positive integer found in it is treated as the
    client's exact count; no digits found means the client did not state one.
    Top-level `intake.json["SLIDE_COUNT"]` / `intake.json["slide_count"]` are
    also checked as defensive aliases in case an older/alternate intake shape
    ever wrote it un-nested.

    Returns (None, "...") when no client-exact count is available anywhere --
    the common case, where the sacred >=100 floor governs, unscaled.
    """
    sp_intake_path = run_dir / "working" / "copy" / "sp_intake.json"
    if sp_intake_path.is_file():
        try:
            sp_intake = json.loads(sp_intake_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            sp_intake = None
        if isinstance(sp_intake, dict) and sp_intake.get("client_overrode_slide_floor") is True:
            exact = sp_intake.get("client_exact_slide_count")
            if isinstance(exact, bool):
                exact = None  # bool is an int subclass -- reject True/False as a count
            if isinstance(exact, int) and exact > 0:
                return exact, (
                    "working/copy/sp_intake.json's own client_overrode_slide_floor=true / "
                    f"client_exact_slide_count={exact} (logged by the Signature Presentation "
                    "Architect during intake, SOP 9.1 step 7)"
                )

    intake_path = run_dir / "working" / "copy" / "intake.json"
    if intake_path.is_file():
        try:
            intake = json.loads(intake_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            intake = None
        if isinstance(intake, dict):
            deck_brief = intake.get("deck_brief")
            raw = None
            if isinstance(deck_brief, dict) and deck_brief.get("SLIDE_COUNT") not in (None, ""):
                raw = deck_brief.get("SLIDE_COUNT")
            elif intake.get("SLIDE_COUNT") not in (None, ""):
                raw = intake.get("SLIDE_COUNT")
            elif intake.get("slide_count") not in (None, ""):
                raw = intake.get("slide_count")
            if isinstance(raw, bool):
                raw = None
            if isinstance(raw, int) and raw > 0:
                return raw, f"working/copy/intake.json deck_brief.SLIDE_COUNT (raw integer {raw})"
            if isinstance(raw, str):
                m = re.search(r"\d+", raw)
                if m and int(m.group(0)) > 0:
                    n = int(m.group(0))
                    return n, (
                        f"working/copy/intake.json deck_brief.SLIDE_COUNT (free-text client "
                        f"answer {raw!r}, first number extracted: {n})"
                    )

    return None, (
        "no client-exact count found in working/copy/sp_intake.json's "
        "client_overrode_slide_floor/client_exact_slide_count fields nor in "
        "working/copy/intake.json's deck_brief.SLIDE_COUNT"
    )


def _sp_structure_contract(run_dir: Path) -> str:
    """Build the P-SP-STRUCTURE OUTPUT CONTRACT text FRESH for this run (see
    the "NOTE: P-SP-STRUCTURE has no static entry" comment in ARTIFACT_
    CONTRACTS above). Points 1/4/5/7/8/9/10 are run-invariant schema rules,
    unchanged from the original hand-written contract; only points 2/3/6 are
    computed here from _sp_read_client_exact_count() / _sp_scaled_floor()."""
    exact, source = _sp_read_client_exact_count(run_dir)
    order = _SP_SACRED_PHASE_ORDER

    if exact is not None:
        floors = {p: _sp_scaled_floor(_SP_SACRED_PHASE_FLOORS[p], exact) for p in order}
        floor_sum = sum(floors.values())
        floor_list = " / ".join(str(floors[p]) for p in order)
        floor_clause = ", ".join(f"`{p}` >= {floors[p]} slides" for p in order)
        scale_disp = f"{exact / _SP_SACRED_DEFAULT_MIN:g}"
        sacred_list = "/".join(str(_SP_SACRED_PHASE_FLOORS[p]) for p in order)

        if floor_sum == exact:
            point2 = (
                f"2. Phase order and floors for THIS {exact}-slide deck (scaled from the "
                f"sacred defaults {sacred_list} by this run's client-exact override, "
                f"{exact}/{_SP_SACRED_DEFAULT_MIN} = {scale_disp}x, rounded): {floor_clause}. "
                f"These four floors already SUM to exactly {exact} -- with a {exact}-slide "
                f"deck there is no slack, so the counts must be EXACTLY {floor_list} in that "
                "phase order (adjust boundaries to fit where the REAL content in "
                f"slides_copy.md naturally divides, but keep the four counts exactly "
                f"{floor_list}).\n"
            )
        elif floor_sum < exact:
            slack = exact - floor_sum
            point2 = (
                f"2. Phase order and floors for THIS {exact}-slide deck (scaled from the "
                f"sacred defaults {sacred_list} by this run's client-exact override, "
                f"{exact}/{_SP_SACRED_DEFAULT_MIN} = {scale_disp}x, rounded): {floor_clause}. "
                f"These four floors SUM to {floor_sum}, leaving {slack} slide(s) of slack "
                f"under the {exact}-slide total -- each number above is a MINIMUM, not an "
                "exact count; distribute the slack among phases however the REAL content in "
                f"slides_copy.md naturally divides, but the total `slides` array length must "
                f"still be EXACTLY {exact} (point 6) and no phase may fall under its own "
                "floor.\n"
            )
        else:  # floor_sum > exact -- the client-exact count is smaller than the sacred
            # per-phase floors can satisfy even after the max(1, ...) clamp. Genuinely
            # infeasible math (an upstream intake/QC problem, not something this contract
            # can resolve) -- state the true floors and the true total honestly rather
            # than silently hiding the conflict or fabricating numbers that "work".
            point2 = (
                f"2. Phase order and floors for THIS {exact}-slide deck (scaled from the "
                f"sacred defaults {sacred_list} by this run's client-exact override, "
                f"{exact}/{_SP_SACRED_DEFAULT_MIN} = {scale_disp}x, rounded, each floor "
                f"clamped to a minimum of 1 slide): {floor_clause}. NOTE: these floors SUM "
                f"to {floor_sum}, which is MORE than the client-exact total of {exact} -- "
                "this combination cannot be fully satisfied (some phase will necessarily "
                "land under its own floor). Get as close to every floor as truly possible, "
                f"keep the total EXACTLY {exact} (point 6) and the phase order/contiguity "
                "correct, and add a short top-level `structure_conflict_note` string "
                "describing the conflict (this field is not read by the verifier but "
                "flags the real upstream problem for the QC specialist -- never silently "
                "paper over it).\n"
            )

        point3 = (
            "3. Top-level keys `client_overrode_slide_floor: true` and "
            f"`client_exact_slide_count: {exact}` (exactly these two fields, these exact "
            f"values) -- this is the real, already-declared client-exact override (sourced "
            f"from {source}); it is what legitimately waives the sacred "
            f">={_SP_SACRED_DEFAULT_MIN}-slide default floor for this deck. Do not omit "
            "these two fields or the deck will hard-fail AF-SP-SLIDE-FLOOR.\n"
        )
        point6 = (
            f"6. This deck has `client_exact_slide_count: {exact}` (point 3) so the total "
            f"`slides` array length must be EXACTLY {exact} -- not more, not fewer.\n"
        )
        slide_count_clause = f"this run: exactly {exact} -- see point 6"
    else:
        sacred_list = "/".join(str(_SP_SACRED_PHASE_FLOORS[p]) for p in order)
        floor_clause = ", ".join(
            f"`{p}` >= {_SP_SACRED_PHASE_FLOORS[p]} slides" for p in order
        )
        point2 = (
            f"2. Phase order and floors (the SACRED, un-scaled defaults, {sacred_list} -- "
            f"no client-exact override is logged for this run, see point 3): {floor_clause}, "
            "contiguous in that order starting at slide 1.\n"
        )
        point3 = (
            "3. Do NOT set `client_overrode_slide_floor: true` and do NOT add a "
            f"`client_exact_slide_count` field -- {source}. Fabricating an override or an "
            "exact count nobody declared is exactly the failure this contract exists to "
            f"prevent; the sacred >={_SP_SACRED_DEFAULT_MIN}-slide floor (point 6) governs "
            "unscaled for this deck.\n"
        )
        point6 = (
            f"6. No client-exact override applies to this run (point 3), so the sacred "
            f"default floor governs: total `slides` array length must be >= "
            f"{_SP_SACRED_DEFAULT_MIN} -- there is no ceiling; expand phases proportionally "
            "past their floors to reach it.\n"
        )
        slide_count_clause = f"this run: >= {_SP_SACRED_DEFAULT_MIN} -- see point 6"

    return (
        "OUTPUT CONTRACT (mechanically enforced by build_deck._chk_sp_structure -> "
        "prove_sp_structure.verify() -- LITERAL, POSITIONALLY-CHECKED requirements, not "
        "stylistic suggestions). File path: working/copy/sp_structure.json (a single JSON "
        "object). This deck's slides_copy.md ALREADY exists (see upstream context) -- your "
        "job here is to CLASSIFY and RE-LEDGER those same already-approved slides into "
        "this exact required shape, not to invent new content:\n"
        "1. Top-level key `slides`: a JSON array, one entry per slide, in slide order. "
        "Each entry is an object with these fields:\n"
        "   - `slide`: integer, 1-based, unique, contiguous from 1 to the deck's real "
        f"slide count ({slide_count_clause}).\n"
        "   - `phase`: one of exactly these four lowercase strings: `avatar`, `story`, "
        "`teaching`, `pitch`. Every slide up to a phase boundary gets that phase; phases "
        "must be CONTIGUOUS blocks in this EXACT order starting at slide 1 (all `avatar` "
        "slides first, then all `story`, then all `teaching`, then all `pitch` -- never "
        "interleaved).\n"
        "   - `label_slide`: boolean. Exactly one slide in EACH of the four phases must "
        "have `label_slide: true` (the slide that names that phase's purpose); all others "
        "in that phase are `false`.\n"
        "   - `suggested_image`: a non-empty string (copy the slide's own visual/PEOPLE "
        "description from slides_copy.md, or write a short scene seed) -- never empty or "
        "whitespace-only.\n"
        "   - `tags`: a JSON array (may be `[]`, but the KEY must always be present -- a "
        "missing `tags` key on ANY slide is itself a hard fail). Use this array to carry "
        "the markers in points 4/5/7 below.\n"
        + point2 + point3 +
        "4. `avatar`, `story`, and `pitch` phases (NOT `teaching`) must each have at "
        "least one slide whose `tags` array includes a tag that normalizes to `NEEIT` "
        "(e.g. write the tag as `N.E.E.I.T.` or `NEEIT`) AND at least one slide (same or "
        "different) whose `tags` includes a tag that normalizes to `QUADRANT`, "
        "`4QUADRANT`, or `FOURQUADRANT` (e.g. write `4-Quadrant`).\n"
        "5. Across the WHOLE deck (any slides, any phases), the tags collectively must "
        "include at least one tag each normalizing to `MOVEMENT`, `MESSAGE`, and "
        "`METHODOLOGY` (e.g. write `Movement`, `Message`, `Methodology` as separate tags "
        "on any 1-3 slides).\n"
        + point6 +
        "7. `teaching` phase (3-7 distinct steps required): EITHER add a top-level "
        "`teaching_steps` field (an integer 3-7, or an array of 3-7 step labels), OR tag "
        "each teaching-phase step slide with a tag that normalizes to `STEP1`, `STEP2`, "
        "... `STEP7` (e.g. write `Step 1`, `TEACHING STEP 2`) -- 3 to 7 DISTINCT step "
        "numbers total, no fewer than 3, no more than 7.\n"
        "8. 1 to 2 slides total (never 0, never more than 2) must carry a tag that "
        "normalizes to `CASESTUDY` (e.g. write `CASE_STUDY`) -- omit entirely if this "
        "deck's real content has no case-study beat, but then explicitly add the tag "
        "`CASE_STUDY` to the strongest proof/wall-of-wins slide so the floor of 1 is met.\n"
        "9. Top-level key `hook_package`: an object with `central_hook` (a non-empty "
        "string -- use the canonical hook line VERBATIM from intake.json/slides_copy.md, "
        "see upstream context) and `section_hooks` (an array of EXACTLY 4 non-empty "
        "strings, one per phase, each DISTINCT from `central_hook` and from each other -- "
        "use the real hook-variant lines already written in slides_copy.md's HOOK VARIANT "
        "fields where available, never re-use the central hook verbatim as a section "
        "hook).\n"
        "10. You may keep any additional descriptive top-level fields your own analysis "
        "produces (title, narrative_summary, sections, etc.) -- they are not read by the "
        "verifier and do no harm -- but `slides`, `client_overrode_slide_floor`, "
        "`client_exact_slide_count`, and `hook_package` in the EXACT shapes above are the "
        "ones that are mechanically graded and MUST be correct."
    )


# ---------------------------------------------------------------------------
# DeepSeek API key resolution -- NEVER printed, loaded the way production
# loads it (binding doctrine): prefer an already-exported environment
# variable (the normal case when this process was launched by a shell that
# already did `set -a; . secrets.env; set +a`, or spawned by the Engine which
# inherits that same environment); fall back to reading secrets.env directly
# so this module is self-sufficient when launched standalone by an operator
# who has not sourced it.
# ---------------------------------------------------------------------------
def _load_deepseek_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key
    if SECRETS_ENV_PATH.is_file():
        try:
            for line in SECRETS_ENV_PATH.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("DEEPSEEK_API_KEY="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val:
                        os.environ["DEEPSEEK_API_KEY"] = val
                        return val
        except OSError:
            pass
    raise RuntimeError(
        "DEEPSEEK_API_KEY not set and not found in "
        f"{SECRETS_ENV_PATH} -- cannot dispatch any work order without it."
    )


# ---------------------------------------------------------------------------
# The DeepSeek call. Thinking MAX via the exact field names this box's own
# openclaw.json already uses for deepseek-v4-pro's params block on the SAME
# native endpoint (proven, not guessed -- see module docstring).
# ---------------------------------------------------------------------------
class DeepSeekCallError(RuntimeError):
    pass


def deepseek_complete(system_prompt: str, user_prompt: str, *,
                      model: Optional[str] = None,
                      run_dir: Optional[Path] = None,
                      max_tokens: int = DEEPSEEK_MAX_OUTPUT_TOKENS,
                      retries: int = 3) -> Tuple[str, Dict[str, Any]]:
    """One DeepSeek chat completion, thinking MAX. Returns
    (content_text, usage_dict). FIX 16: the caller passes the model the ROUTE
    selected (default stays the catalog text.fast id so the pre-FIX-7
    rollback path is byte-for-byte unchanged). Retries transient
    HTTP/network failures with backoff; a non-transient (4xx other than 429)
    failure raises immediately."""
    key = _load_deepseek_key()
    body = {
        # FIX 16: send the model the router chose, not a module constant.
        "model": model or DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": DEEPSEEK_TEMPERATURE,
        "thinking": {"type": "enabled"},
        "reasoning_effort": "max",
    }
    data = json.dumps(body).encode("utf-8")
    # FIX 16 dispatcher debug log: the exact request body that leaves this
    # box, one JSON line per attempt (proof a Pro route shows
    # "model": "deepseek-v4-pro" in the body). Prompt text is redacted so the
    # log stays small and carries no artifact content; never the key.
    if run_dir is not None:
        try:
            dbg = run_dir / "working" / "debug" / "dispatcher-requests.jsonl"
            dbg.parent.mkdir(parents=True, exist_ok=True)
            with dbg.open("a", encoding="utf-8") as dfh:
                dfh.write(json.dumps({
                    "event": "request_body",
                    "transport": "deepseek-direct",
                    "model": body.get("model"),
                    "url": DEEPSEEK_CHAT_URL,
                    "max_tokens": max_tokens,
                    "system_chars": len(system_prompt),
                    "user_chars": len(user_prompt),
                    # the request body exactly as serialized for the wire --
                    # the FIX 16 proof greps this for the routed model id
                    "body": body,
                    "attempt": 1,
                    "at": utcnow(),
                }, ensure_ascii=False) + "\n")
        except Exception as exc:  # noqa: BLE001 -- debug log never breaks a call
            print(f"WARN dispatcher debug log: {exc}", flush=True)
    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        # FIX 14: one governor lease per HTTP attempt on the deepseek-direct
        # provider. The 429 branch feeds report_429 before the backoff sleep
        # so the governor halves the next 60 s of rate; a clean response feeds
        # report_ok. Lease is released before the loop's backoff sleep so a
        # sleeping retry never occupies an in-flight slot.
        # [PRES-003] ADMISSION IS REQUIRED: a refused admission (daily cap,
        # timeout, broken governor, missing module) raises HERE, before the
        # request is built -- the transport is never invoked without one.
        _admission = _govern_admit("deepseek-direct")
        if not _admission.admitted:
            raise DeepSeekCallError(
                _govern_refusal_text("deepseek-direct", _admission))
        _lease = _admission.lease
        try:
            req = urllib.request.Request(
                DEEPSEEK_CHAT_URL, data=data, method="POST",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=DEEPSEEK_TIMEOUT_S) as resp:
                    raw = resp.read().decode("utf-8")
                obj = json.loads(raw)
                choice = (obj.get("choices") or [{}])[0]
                content = ((choice.get("message") or {}).get("content")) or ""
                usage = obj.get("usage") or {}
                _govern_ok("deepseek-direct")
                return content, usage
            except urllib.error.HTTPError as exc:
                payload = ""
                try:
                    payload = exc.read().decode("utf-8", errors="replace")[:2000]
                except Exception:  # noqa: BLE001
                    pass
                if exc.code == 429 or exc.code >= 500:
                    if exc.code == 429:
                        # [PRES-016] honor the provider's own Retry-After.
                        _govern_429("deepseek-direct",
                                    retry_after_s=_govern_retry_after(exc))
                    last_exc = DeepSeekCallError(f"HTTP {exc.code}: {payload}")
                else:
                    raise DeepSeekCallError(f"HTTP {exc.code} (non-transient): {payload}") from exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
                last_exc = DeepSeekCallError(f"{type(exc).__name__}: {exc}")
        finally:
            _govern_release("deepseek-direct", _lease)
        if attempt < retries:
            time.sleep(min(30, 3 * (2 ** (attempt - 1))))
    raise last_exc or DeepSeekCallError("deepseek_complete: exhausted retries")

# ---------------------------------------------------------------------------
# FIX 7 -- profile-driven model routing. The transports stay HERE (this module
# owns credentials and HTTP, as before); the DECISION lives in model_router
# (pure, credential-free selection over the client resource profile). Every
# completion the dispatcher issues goes through dispatch_complete, which
# resolves the route, picks the transport, and emits the FIX 5 routing
# telemetry row {phase_id, requested_alias, selected_provider, selected_model,
# reason} best-effort (telemetry NEVER breaks a run).
#
# PRESENTATION_MODEL_ROUTER=0 (rollback): the router reports "disabled" and
# dispatch_complete takes the untouched pre-FIX-7 path -- deepseek_complete
# with the module's own constants --
# every call site byte-for-byte equivalent to before this fix.
# ---------------------------------------------------------------------------
class RoutingUnavailable(RuntimeError):
    """No client-owned, consented route for the phase's required capability
    (model_router resolved route=None). Fail-closed: park the phase, never
    fabricate a route to a provider the client does not own."""


class _RouteContext:
    """Per-call mutable record of what dispatch_complete resolved, so callers
    can stamp sidecars/telemetry with the ACTUAL model used instead of the
    pre-FIX-7 constant."""

    __slots__ = ("provider", "model", "reason", "requested_alias", "router")

    def __init__(self) -> None:
        self.provider: Optional[str] = None
        self.model: Optional[str] = None
        self.reason: str = ""
        self.requested_alias: Optional[str] = None
        self.router: str = "model_router"

    def as_dict(self) -> Dict[str, Any]:
        return {"provider": self.provider, "model": self.model,
                "reason": self.reason, "requested_alias": self.requested_alias,
                "router": self.router}


def _emit_model_route_telemetry(run_dir: Optional[Path], ctx: _RouteContext,
                                phase_id: str) -> None:
    """FIX 5 row for one routing decision. Best-effort: never raises."""
    if run_dir is None:
        return
    try:
        row = {
            "run_id": run_dir.name,
            "phase_id": phase_id,
            "wave": 1,
            "model_used": ctx.model,
            "event": "model_route",
            # the FIX 7 payload, top-level exactly as the fix spec shapes it
            "requested_alias": ctx.requested_alias,
            "selected_provider": ctx.provider,
            "selected_model": ctx.model,
            "reason": ctx.reason,
            "router": ctx.router,
            "started_at": utcnow(),
            "ended_at": utcnow(),
            "duration_s": None,
            "status": "routed" if ctx.model else "unrouted",
        }
        _emit_slide_author_telemetry(run_dir, [row])
    except Exception as exc:  # noqa: BLE001 -- telemetry NEVER breaks a run
        print(f"WARN telemetry: model_route row failed: {exc}", flush=True)


#: Fallback key-name table, used ONLY when model_router is not importable.
#: It must stay a MIRROR of model_router._PROVIDER_KEY_NAMES, never a second
#: opinion: the router decides eligibility from that table, and a transport
#: that reads a different name is a route that passes the gate and dies on the
#: wire.
_FALLBACK_PROVIDER_KEY_NAMES: Dict[str, Tuple[str, ...]] = {
    "deepseek-direct": ("DEEPSEEK_API_KEY",),
    "openrouter": ("OPENROUTER_API_KEY",),
    "ollama-cloud": ("OLLAMA_CLOUD_API_KEY", "OLLAMA_API_KEY"),
    "agnes": ("AGNES_AI_API_KEY", "AGNES_API_KEY"),
    "kie": ("KIE_API_KEY",),
}


def _provider_key_names(provider: str) -> Tuple[str, ...]:
    """Every env key name this provider's credential may be spelled under.

    THE SEAM THIS CLOSES: model_router._eligible accepts an ollama-cloud route
    when EITHER OLLAMA_CLOUD_API_KEY or OLLAMA_API_KEY resolves
    (model_router._PROVIDER_KEY_NAMES), while this transport used to read only
    OLLAMA_CLOUD_API_KEY -- so a box carrying OLLAMA_API_KEY produced routes
    that passed the eligibility gate and then failed on the wire, phase after
    phase. Eligibility and transport now read the SAME table; the router owns
    it, and the mirror above is only for a deploy where the router is absent.
    """
    token = str(provider or "").strip().lower().replace("_", "-").replace(" ", "-")
    table = None
    if _model_router is not None:
        candidate = getattr(_model_router, "_PROVIDER_KEY_NAMES", None)
        if isinstance(candidate, dict) and candidate:
            table = candidate
    if table is None:
        table = _FALLBACK_PROVIDER_KEY_NAMES
    for key, names in table.items():
        if str(key).strip().lower().replace("_", "-") == token and names:
            return tuple(str(n) for n in names)
    return (f"{token.upper().replace('-', '_')}_API_KEY",)


def _openai_compat_complete(system_prompt: str, user_prompt: str, *,
                            provider: str, model: str,
                            max_tokens: int = DEEPSEEK_MAX_OUTPUT_TOKENS,
                            retries: int = 3,
                            run_dir: Optional[Path] = None) -> Tuple[str, Dict[str, Any]]:
    """OpenAI-compatible chat-completions transport for NON-DeepSeek client-owned
    providers (openrouter, ollama-cloud text classes, ...). Mirrors
    deepseek_complete's retry/timeout semantics. Credentials resolve per
    provider from the environment the Engine already exported; a key value is
    never printed, never logged, never included in any telemetry row."""
    key_names = _provider_key_names(provider)
    key = ""
    key_name = key_names[0]
    for candidate_name in key_names:
        value = (os.environ.get(candidate_name) or "").strip()
        if value:
            key_name, key = candidate_name, value
            break
    if not key:
        # Do NOT route a provider we cannot authenticate to: fall back to a
        # clear, non-spammy error surfaced through the normal DeepSeekCallError
        # retry path the call sites already handle. Every accepted spelling is
        # named, because a route that PASSED eligibility on OLLAMA_API_KEY and
        # then died here on "OLLAMA_CLOUD_API_KEY not set" is the exact drift
        # _provider_key_names() exists to close.
        raise DeepSeekCallError(
            f"none of {list(key_names)} is set in environment -- cannot "
            f"dispatch to provider {provider} (model {model})")
    base_urls = {
        "openrouter": "https://openrouter.ai/api/v1",
        "ollama-cloud": "https://ollama.com/v1",
        "agnes": "https://api.agnes.ai/v1",
    }
    base = base_urls.get(provider) or os.environ.get(
        f"PRESENTATION_{provider.upper().replace('-', '_')}_BASE_URL", "")
    if not base:
        raise DeepSeekCallError(
            f"no base URL known for provider {provider} -- set "
            f"PRESENTATION_{provider.upper().replace('-', '_')}_BASE_URL")
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
    "temperature": DEEPSEEK_TEMPERATURE,
    }
    data = json.dumps(body).encode("utf-8")
    last_exc: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        # FIX 14: one governor lease per HTTP attempt on the routed provider
        # (openrouter / ollama-cloud / agnes / ...). Same contract as
        # deepseek_complete: report_429 before backoff on 429, report_ok on a
        # clean response, lease released before the backoff sleep.
        # [PRES-003] admission is required: refusal raises before the request.
        _admission = _govern_admit(provider)
        if not _admission.admitted:
            raise DeepSeekCallError(_govern_refusal_text(provider, _admission))
        _lease = _admission.lease
        try:
            req = urllib.request.Request(
                f"{base.rstrip('/')}/chat/completions", data=data, method="POST",
                headers={"Authorization": f"Bearer {key}",
                         "Content-Type": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=DEEPSEEK_TIMEOUT_S) as resp:
                    raw = resp.read().decode("utf-8")
                obj = json.loads(raw)
                choice = (obj.get("choices") or [{}])[0]
                content = ((choice.get("message") or {}).get("content")) or ""
                usage = obj.get("usage") or {}
                _govern_ok(provider)
                return content, usage
            except urllib.error.HTTPError as exc:
                payload = ""
                try:
                    payload = exc.read().decode("utf-8", errors="replace")[:2000]
                except Exception:  # noqa: BLE001
                    pass
                if exc.code == 429 or exc.code >= 500:
                    if exc.code == 429:
                        # [PRES-016] honor the provider's own Retry-After.
                        _govern_429(provider,
                                    retry_after_s=_govern_retry_after(exc))
                    last_exc = DeepSeekCallError(f"HTTP {exc.code}: {payload}")
                elif exc.code == 402 and "can only afford" in payload:
                    # F31 (SMOKE-1, 2026-09-01): OpenRouter 402 names the exact
                    # token budget the remaining credits can afford. Retry THIS
                    # call at that budget instead of treating it as fatal -- the
                    # deliverable (an OCR readback) is small and does not need the
                    # 64k default. One demotion per call site, floor 512.
                    import re as _re
                    _m = _re.search(r"can only afford (\d+)", payload)
                    if _m:
                        afford = max(512, int(_m.group(1)) - 128)
                        demoted = dict(body)
                        demoted["max_tokens"] = afford
                        data2 = json.dumps(demoted).encode("utf-8")
                        req2 = urllib.request.Request(
                            f"{base.rstrip('/')}/chat/completions", data=data2,
                            method="POST",
                            headers={"Authorization": f"Bearer {key}",
                                     "Content-Type": "application/json"})
                        try:
                            with urllib.request.urlopen(req2, timeout=DEEPSEEK_TIMEOUT_S) as resp2:
                                obj2 = json.loads(resp2.read().decode("utf-8"))
                            choice2 = (obj2.get("choices") or [{}])[0]
                            content2 = ((choice2.get("message") or {}).get("content")) or ""
                            usage2 = obj2.get("usage") or {}
                            _govern_ok(provider)
                            return content2, usage2
                        except Exception as exc2:  # noqa: BLE001
                            raise DeepSeekCallError(
                                f"HTTP 402 demoted retry ({afford} tokens) also failed: "
                                f"{type(exc2).__name__}: {exc2}") from exc2
                    raise DeepSeekCallError(
                        f"HTTP 402 (non-transient): {payload}") from exc
                else:
                    raise DeepSeekCallError(
                        f"HTTP {exc.code} (non-transient): {payload}") from exc
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError,
                    OSError) as exc:
                last_exc = DeepSeekCallError(f"{type(exc).__name__}: {exc}")
        finally:
            _govern_release(provider, _lease)
        if attempt < retries:
            time.sleep(min(30, 3 * (2 ** (attempt - 1))))
    raise last_exc or DeepSeekCallError(
        f"{provider}/chat/completions: exhausted retries")


def _active_mode() -> Tuple[str, str]:
    """The run's FIX 11 mode inside the ENGINE process, plus where it came from.

    THIS IS THE READ THAT WAS MISSING. The launcher exports PRESENTATION_MODE
    into the engine's environment (launcher.dispatch -> mode_env) and, until
    now, not one line of the engine consumed it: a typed `--mode Ultra` reached
    a sidecar and an env var and then stopped, so every dispatch resolved its
    route at the default no matter what the operator declared. Ultra was
    unreachable by construction.

    Resolution order is model_router's single authority (active_mode):
    explicit > PRESENTATION_MODE > "standard".

    A garbage env value never crashes a running deck AND is never silently
    coerced: it falls back to standard and SAYS SO in the returned source,
    which the routing stamp then carries into the wave input and the run's
    record. Silence is the thing this codebase refuses, not the fallback."""
    if _model_router is None:
        return "standard", "router-absent-default"
    env_name = getattr(_model_router, "MODE_ENV", "PRESENTATION_MODE")
    raw = os.environ.get(env_name)
    declared = bool(str(raw or "").strip().strip("'\""))
    try:
        return _model_router.active_mode(), (env_name if declared else "default")
    except ValueError:
        return (getattr(_model_router, "DEFAULT_MODE", "standard"),
                f"invalid {env_name}={raw!r} -- fell back to standard")


def _apply_route_override(decision: Optional[Dict[str, Any]],
                          route_override: Optional[Dict[str, Any]],
                          ) -> Optional[Dict[str, Any]]:
    """F10: fold a heal rung's `route_override` into a routing decision.

    The override wins ONLY when model_router's own candidate list for this
    phase contains that provider with eligible=True. That is deliberate and it
    is the entire safety property of this function: `candidates` is where
    client-owned-provider consent, catalog health, capability and mode budget
    have ALREADY been applied, so honouring only an eligible candidate means a
    heal rung can re-point a phase but can never widen what the client owns.

    An override that names nothing, names a provider with no eligible
    candidate, or arrives with no decision at all returns `decision` unchanged
    -- fail-closed onto the router's own pick, never onto a fabricated route.
    The chosen candidate's own model is used when the override does not name
    one (or names one the candidate does not offer), so the model can never
    drift away from the provider that was actually vetted.
    """
    if not route_override or not isinstance(route_override, dict):
        return decision
    if not isinstance(decision, dict):
        return decision
    want_provider = str(route_override.get("provider") or "")
    if not want_provider:
        return decision
    for cand in (decision.get("candidates") or []):
        if not isinstance(cand, dict) or not cand.get("eligible"):
            continue
        if str(cand.get("provider") or "") != want_provider:
            continue
        model = str(route_override.get("model") or "") or str(cand.get("model") or "")
        if not model:
            continue
        out = dict(decision)
        out["route"] = {"provider": want_provider, "model": model}
        out["reason"] = (f"heal route_override -> {want_provider}/{model} "
                         f"(eligible candidate; prior: {decision.get('reason')})")
        return out
    return decision


def dispatch_complete(system_prompt: str, user_prompt: str, *,
                      phase_id: str,
                      run_dir: Optional[Path] = None,
                      max_tokens: int = DEEPSEEK_MAX_OUTPUT_TOKENS,
                      retries: int = 3,
                      route_override: Optional[Dict[str, Any]] = None,
                      ) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    """THE routed completion entrypoint: every dispatcher LLM call site goes
    through here. Returns (content, usage, route_dict) where route_dict carries
    {provider, model, reason, requested_alias, router} for sidecar/telemetry
    stamping.

    Selection (model_router.resolve_route): required capability -> client-owned
    consented providers -> catalog health -> mode budget -> fallback list.
    route=None (no eligible client-owned route) raises RoutingUnavailable --
    park/fail-closed, never a fabricated model. PRESENTATION_MODEL_ROUTER=0
    (rollback) selects the pre-FIX-7 DeepSeek-direct path exactly.

    F10: `route_override` ({provider, model}, from a heal rung's reissued work
    order) re-points the selection -- but only onto a candidate the router
    itself already marked eligible. See _apply_route_override."""
    ctx = _RouteContext()
    decision: Optional[Dict[str, Any]] = None
    if _model_router is not None:
        try:
            # FIX 11 wire: the RUN'S mode, not the signature default. Passed
            # explicitly (rather than left to resolve_route's own env read) so
            # a hand-set garbage PRESENTATION_MODE degrades to standard with a
            # recorded reason here instead of raising into the routing path.
            decision = _model_router.resolve_route(phase_id,
                                                   mode=_active_mode()[0])
        except Exception as exc:  # noqa: BLE001 -- a broken router never
                                  # hard-crashes a run: fall back to DeepSeek
            decision = {"router": f"error: {exc}", "route": None, "reason": str(exc)}

    # F10 (2026-09-06): the Engine's provider-failover heal rung pins an
    # alternate provider on the reissued work order (order["route_override"]).
    # Honour it AHEAD of the router's own pick -- but ONLY when the router
    # itself lists that provider among this phase's ELIGIBLE candidates. That
    # gate is the whole safety property: a heal rung must never be a back door
    # around client-owned-provider consent, catalog health or the mode budget.
    # An override naming an ineligible (or unknown) provider is dropped and the
    # router's decision stands untouched.
    decision = _apply_route_override(decision, route_override)

    # FIX 14: the routed entrypoint itself holds one logical governor lease
    # for the phase's provider across the whole dispatch (all retry attempts
    # of the chosen transport run inside it). The transports take their own
    # per-attempt leases, but the re-entrancy depth counter in _govern_admit
    # means exactly ONE real acquire per logical call per provider per thread:
    # this outer frame is it, the inner transport frames re-use this lease.
    # Every return path AND every exception releases through _govern_release
    # via the single finally below.
    # [PRES-003] THE ENFORCING GATE: a refused admission (missing/broken
    # governor, exhausted budget, acquire timeout) raises BEFORE any transport
    # work -- zero outbound calls, with a typed, greppable GOVERNOR-BLOCKED /
    # GOVERNOR-RETRY reason the caller's sidecar records verbatim.
    route = (decision or {}).get("route") or None
    router_id = str((decision or {}).get("router") or "")
    profile_state = str((decision or {}).get("profile_state") or "")
    _route_unknown_yet = (route is None or router_id == "disabled")
    _dispatch_provider = "deepseek-direct" if _route_unknown_yet \
        else str(route.get("provider") or "deepseek-direct")
    _dispatch_admission = _govern_admit(_dispatch_provider)
    if not _dispatch_admission.admitted:
        raise DeepSeekCallError(
            _govern_refusal_text(_dispatch_provider, _dispatch_admission))
    _dispatch_lease = _dispatch_admission.lease
    try:
        if route is None and router_id != "disabled":
            if profile_state == "has_providers":
                # The client OWNS providers yet none satisfies this phase's
                # required capability (e.g. a vision/OCR phase with no OCR owner,
                # or only unconsented/unwired candidates): fail-closed PARK. A
                # fabrication here would spend a provider the client does not own
                # on a model that cannot hold the artifact.
                ctx.router = router_id or "model_router"
                ctx.reason = str((decision or {}).get("reason") or "no eligible route")
                ctx.requested_alias = (decision or {}).get("requested_alias")
                _emit_model_route_telemetry(run_dir, ctx, phase_id)
                raise RoutingUnavailable(
                    f"phase {phase_id}: no eligible client-owned route -- "
                    f"{(decision or {}).get('reason')}")
            # profile_state in ("absent", "", "mechanical", ...) -- no client-owned
            # provider evidence exists yet: keep the dispatcher's pre-FIX-7
            # default (DeepSeek-direct) rather than stranding runs on a profile
            # that simply has not been captured yet.
            ctx.router = router_id or "model_router"
            ctx.provider = "deepseek-direct"
            ctx.model = DEEPSEEK_MODEL
            ctx.requested_alias = (decision or {}).get("requested_alias") \
                or "deepseek-v4-flash"
            ctx.reason = str((decision or {}).get("reason")
                             or "no profile route; dispatcher default DeepSeek-direct")
            content, usage = deepseek_complete(system_prompt, user_prompt,
                                               model=ctx.model, run_dir=run_dir,
                                               max_tokens=max_tokens, retries=retries)
            _emit_model_route_telemetry(run_dir, ctx, phase_id)
            return content, usage, ctx.as_dict()
        if router_id == "disabled":
            # PRESENTATION_MODEL_ROUTER=0 rollback: the untouched pre-FIX-7 path,
            # no model_route telemetry row (it predates the routing event).
            ctx.router = "disabled"
            ctx.provider = "deepseek-direct"
            ctx.model = DEEPSEEK_MODEL
            ctx.requested_alias = None
            ctx.reason = str((decision or {}).get("reason") or "router disabled")
            content, usage = deepseek_complete(system_prompt, user_prompt,
                                               model=ctx.model, run_dir=run_dir,
                                               max_tokens=max_tokens, retries=retries)
            return content, usage, ctx.as_dict()

        ctx.provider = str(route.get("provider") or "")
        ctx.model = str(route.get("model") or "")
        ctx.requested_alias = (decision or {}).get("requested_alias")
        ctx.reason = str((decision or {}).get("reason") or "")
        ctx.router = router_id or "model_router"

        # FIX 17a provider fold at the ONE transport seam: the catalog may
        # spell the native DeepSeek provider "deepseek" while every transport,
        # the profile store and the key canon speak "deepseek-direct" (the
        # router's own _norm_provider fold). Without this fold a routed
        # "deepseek" phase fell through to _openai_compat_complete, which has
        # no base URL and no transport for the native endpoint -- every call
        # died with "no base URL known for provider deepseek" no matter how
        # healthy the route. Normalizing here (never in the catalog) keeps the
        # catalog's spelling authoritative for eligibility while the dispatch
        # branch picks the transport the provider id actually owns.
        try:
            ctx.provider = _model_router._norm_provider(ctx.provider)
        except Exception:  # noqa: BLE001 -- a fold failure must not change routing
            pass

        if ctx.provider == "deepseek-direct":
            content, usage = deepseek_complete(system_prompt, user_prompt,
                                               model=ctx.model, run_dir=run_dir,
                                               max_tokens=max_tokens, retries=retries)
            # usage/model provenance stays honest even though the native endpoint
            # pins its own served id; FIX 16 now sends the ROUTE's model id in the
            # request body itself (the route is what callers stamp AND what is sent).
            _emit_model_route_telemetry(run_dir, ctx, phase_id)
            return content, usage, ctx.as_dict()

        content, usage = _openai_compat_complete(
            system_prompt, user_prompt, provider=ctx.provider, model=ctx.model,
            max_tokens=max_tokens, retries=retries, run_dir=run_dir)
        _emit_model_route_telemetry(run_dir, ctx, phase_id)
        return content, usage, ctx.as_dict()
    finally:
        _govern_release(_dispatch_provider, _dispatch_lease)


# ---------------------------------------------------------------------------
# Role-SOP resolution (spec S4.1). Portable across BOTH tree layouts this
# codebase actually ships:
#   - deployed/materialized department tree: <dept>/<role-slug>/how-to.md
#     (falls back to a numbered <dept>/NN-<role-slug>/how-to.md dir, e.g. the
#     confirmed qc-specialist-signature-presentations gap, spec S4.2)
#   - git-repo template tree: <dept>/<role-slug>.md (flat file, no how-to.md
#     wrapper directory)
# Only how-to.md / SOUL.md are read (spec S4, confirmed finding: the numbered
# NN-core-sop.md files are auto-generated DMAIC padding -- 63 repetitions of
# one boilerplate sentence, present under every role, zero role-specific
# signal). A flat <role>.md file already IS "the SOP", equivalent in role to
# how-to.md; SOUL.md may not exist in the flat-file layout and is optional.
# ---------------------------------------------------------------------------
class RoleSOPNotFound(RuntimeError):
    pass


def resolve_role_prompt_path(dept_root: Path, role_slug: str) -> Path:
    candidates = [dept_root / role_slug / "how-to.md"]
    numbered = sorted(dept_root.glob(f"[0-9]*-{role_slug}/how-to.md"))
    candidates.extend(numbered)
    candidates.append(dept_root / f"{role_slug}.md")
    for c in candidates:
        if c.is_file():
            return c
    raise RoleSOPNotFound(
        f"no how-to.md or flat {role_slug}.md found under {dept_root} "
        f"(tried: {', '.join(str(c) for c in candidates)})"
    )


def load_role_context(dept_root: Path, role_slug: str, *, max_chars: int = 60_000) -> str:
    sop_path = resolve_role_prompt_path(dept_root, role_slug)
    text = sop_path.read_text(encoding="utf-8", errors="replace")
    soul_path = dept_root / role_slug / "SOUL.md"
    soul_text = ""
    if soul_path.is_file():
        try:
            soul_text = soul_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
    combined = text
    if soul_text:
        combined += "\n\n---\n\n## SOUL.md (voice/mission)\n\n" + soul_text
    if len(combined) > max_chars:
        combined = combined[:max_chars] + "\n\n[...truncated for length...]"
    return combined


# ---------------------------------------------------------------------------
# Blended-persona voice (spec S5.3 item 3). READ-ONLY -- state.json's
# phases[].persona_bundle, already resolved by Engine._run_phase BEFORE this
# module ever sees the work order (phases.py:226). Never re-resolved here:
# that would risk disagreeing with what the Engine already committed. A bare
# json.loads read never races the Engine's own atomic write-temp-then-
# os.replace save for a state.json this small.
# ---------------------------------------------------------------------------
def read_persona_bundle(run_dir: Path, phase_id: str) -> Optional[Dict[str, Any]]:
    state_path = run_dir / "state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for ps in state.get("phases", []):
        if ps.get("id") == phase_id:
            bundle = ps.get("persona_bundle")
            return bundle if isinstance(bundle, dict) else None
    return None


# ---------------------------------------------------------------------------
# Upstream artifact context (spec S5.3 item 4). A fixed, generous candidate
# list of the files role SOPs actually name as required reading -- read
# whichever already exist, capped so a huge upstream file set never blows
# the (very large, 1M-token) DeepSeek context window into an expensive call.
# ---------------------------------------------------------------------------
_UPSTREAM_CANDIDATES = [
    "working/copy/intake.json",
    "working/copy/sp_intake.json",
    "working/copy/sp_claims.json",
    "working/copy/sp_structure.json",
    "working/interview/intake_transcript.json",
    "working/interview/intake_ledger.json",
    "working/copy/priority_shift_spec.json",
    "working/copy/arc_allocation.json",
    "working/copy/mission_prd.json",
    "working/copy/slides_copy.md",
]

# ---------------------------------------------------------------------------
# P4-COPY-SPECIFIC upstream budget/candidate override (root-cause fix,
# 2026-08-19, live run pres-wave-e-zhc-1787175621): the generic path above
# (all ~10 candidates, up to 150_000 chars, plus every research brief) was
# measured live at ~127K chars of upstream context alone for this run --
# combined with the ~50K-char role-SOP + persona + contract overhead, the
# TOTAL prompt handed to DeepSeek for P4-COPY was 185,008 chars, with the
# literal, positionally-checked OUTPUT CONTRACT (the <!-- ARC: TAG --> marker
# spec) sitting early in that prompt and then buried under the bulk of it.
# DeepSeek returned well-formed 25-slide copy, attempt after attempt, with
# ZERO ARC markers -- and on one attempt, an outright empty completion
# (thinking MAX exhausting the whole 64,000-token output budget). Read
# ARTIFACT_CONTRACTS["P4-COPY"] closely: every beat it grades is sourced from
# EXACTLY four things -- intake.json (canonical hook, named_methodology,
# time_to_result, pitch_included), arc_allocation.json (which arc-section
# each slide belongs to -- the beat ORDER contract point 2 hard-requires),
# priority_shift_spec.json (the strategic priority stack/build sequence that
# governs pacing), and sp_intake.json (signature-presentation framing). The
# research brief and research_map.json (grounded facts/quotes/stats, and
# which slide each maps to) round that out -- handled via the same
# research-directory glob below, now widened to also read research_map.json
# (previously never read by ANY phase -- a plain omission, not a design
# choice: only brief-*.md was ever globbed). NOT needed: the raw turn-by-turn
# interview transcript/ledger (already fully distilled into intake.json for
# every field this contract reads), sp_claims.json/sp_structure.json/
# mission_prd.json (later-phase artifacts, normally still absent this early
# anyway), and -- deliberately excluded -- P4-COPY's OWN prior-attempt
# slides_copy.md (the exact file this call is about to overwrite; including
# a previous WRONG attempt as "upstream context" is a self-anchoring risk,
# not a genuine input -- the prior_reasons block already tells the model
# precisely what the real verifier rejected, which is the actionable part of
# a bad prior attempt, not the prose itself).
#
# 100_000 chars is not an arbitrary round number: measured against this run's
# real files, intake.json (7,603B) + arc_allocation.json (18,266B) +
# priority_shift_spec.json (10,031B) + sp_intake.json (3,711B) +
# research_map.json (23,765B) + the research brief (30,138B) sum to 93,514
# chars -- everything P4-COPY's contract actually cites, in full, with zero
# truncation, and ~6.5K of headroom to spare. That is a real, load-bearing
# cut from the previous ~127K/150K (roughly a third smaller), applied ONLY to
# P4-COPY -- every other phase keeps the original candidate list and the
# original 150_000-char budget, unchanged, exactly as before this fix.
# ---------------------------------------------------------------------------
_P4_COPY_UPSTREAM_CANDIDATES = [
    "working/copy/intake.json",
    "working/copy/arc_allocation.json",
    "working/copy/priority_shift_spec.json",
    "working/copy/sp_intake.json",
]
_P4_COPY_UPSTREAM_MAX_CHARS = 100_000


def gather_upstream_context(run_dir: Path, *, max_chars: int = 150_000,
                            phase_id: Optional[str] = None) -> str:
    candidates = _UPSTREAM_CANDIDATES
    effective_max_chars = max_chars
    if phase_id == "P4-COPY":
        candidates = _P4_COPY_UPSTREAM_CANDIDATES
        effective_max_chars = min(max_chars, _P4_COPY_UPSTREAM_MAX_CHARS)
    parts: List[str] = []
    total = 0
    for rel in candidates:
        p = run_dir / rel
        if not p.is_file():
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if total + len(txt) > effective_max_chars:
            txt = txt[: max(0, effective_max_chars - total)]
        parts.append(f"### {rel}\n```\n{txt}\n```")
        total += len(txt)
        if total >= effective_max_chars:
            break
    # Research materials -- research_map.json (facts/quotes mapped to specific
    # slide numbers -- the highest-signal single research artifact for a copy
    # phase) FIRST, then every brief-*.md in name order. research_map.json was
    # never read by any phase before this fix (see the P4-COPY override
    # comment above); widening this shared loop benefits every phase that
    # already reads the research directory, not just P4-COPY.
    research_dir = run_dir / "working" / "research"
    research_files: List[Path] = []
    if research_dir.is_dir():
        rm_path = research_dir / "research_map.json"
        if rm_path.is_file():
            research_files.append(rm_path)
        research_files.extend(sorted(research_dir.glob("brief-*.md")))
    for rel in research_files:
        if total >= effective_max_chars:
            break
        try:
            txt = rel.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        relname = str(rel.relative_to(run_dir))
        if total + len(txt) > effective_max_chars:
            txt = txt[: max(0, effective_max_chars - total)]
        parts.append(f"### {relname}\n```\n{txt}\n```")
        total += len(txt)
    # ROOT-CAUSE FIX (live run pj_34a56a26caca04532ec6e9cba6, 2026-08-18,
    # iteration 3): P-PROMPT-QC is an INDEPENDENT reviewer of the 25 per-slide
    # prompt files (working/prompts/slide-*.txt), but the fixed _UPSTREAM_
    # CANDIDATES list above never named them (it is a list of single files, and
    # a 25-file, one-per-slide glob does not fit that shape) -- confirmed live:
    # the reviewer's own report honestly recorded "slide-01.txt through
    # slide-25.txt were not delivered to the QC specialist in this run context"
    # and correctly failed (average=1.0) rather than hallucinate scores over
    # content it never saw. That was an HONEST failure of a REAL gap, not a
    # rubber stamp -- the fix is to actually deliver the files, not to loosen
    # the report requirements. 25 slides x up to 18,000 chars is at most
    # 450,000 chars (~115K tokens) -- comfortably inside DeepSeek's very large
    # context window (see the module comment above _UPSTREAM_CANDIDATES), so
    # this phase alone gets a raised budget rather than quietly truncating
    # mid-file, which would just move the same "can't verify what I can't see"
    # failure onto whichever slide got cut off.
    if phase_id == "P-PROMPT-QC":
        prompts_dir = run_dir / "working" / "prompts"
        if prompts_dir.is_dir():
            budget = max(max_chars, 500_000)
            for rel in sorted(prompts_dir.glob("slide-*.txt")):
                if total >= budget:
                    break
                try:
                    txt = rel.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                relname = str(rel.relative_to(run_dir))
                if total + len(txt) > budget:
                    txt = txt[: max(0, budget - total)]
                parts.append(f"### {relname}\n```\n{txt}\n```")
                total += len(txt)
    return "\n\n".join(parts) if parts else "(no upstream artifacts exist yet for this run)"


# ---------------------------------------------------------------------------
# Prompt composition (spec S5.3, in order): how-to.md/SOUL.md, persona bundle
# (if governed), upstream context, the work order itself, prior-attempt
# verifier feedback, and -- LAST, immediately before generation -- a verbatim
# restatement of the OUTPUT CONTRACT.
#
# RECENCY FIX (root cause, live run pres-wave-e-zhc-1787175621, 2026-08-19):
# the literal, positionally-checked OUTPUT CONTRACT used to be placed right
# after the work order, then get buried under up to ~127K chars of upstream
# context that followed it (measured live: total prompt 185,008 chars, with
# "ARC:" appearing 19 times in the contract text itself but ZERO times in
# DeepSeek's completions, attempt after attempt -- one attempt returned an
# outright empty completion). Wiring was fine and the instruction reached the
# model; it just wasn't the LAST thing the model read before generating.
# Recency dominates instruction-following far more than mere presence, so the
# contract is now restated, VERBATIM, as the final substantial block in the
# user prompt -- immediately before the one-line "write it now" trigger --
# with an EARLIER, lighter-weight contract mention removed (see below) so
# this fix does not also grow the very prompt size problem it exists to fix.
# ---------------------------------------------------------------------------
def compose_prompt(*, phase_id: str, owning_role: str, dept_root: Path, run_dir: Path,
                    order: Dict[str, Any], attempt: int,
                    prior_reasons: Optional[List[str]]) -> Tuple[str, str]:
    role_context = load_role_context(dept_root, owning_role)
    persona_bundle = read_persona_bundle(run_dir, phase_id)
    upstream = gather_upstream_context(run_dir, phase_id=phase_id)
    # P-SP-STRUCTURE's contract is derived PER RUN, not looked up statically --
    # see _sp_structure_contract's docstring and the "NOTE: P-SP-STRUCTURE has
    # no static entry" comment in ARTIFACT_CONTRACTS for why.
    if phase_id == "P-SP-STRUCTURE":
        contract = _sp_structure_contract(run_dir)
    else:
        contract = ARTIFACT_CONTRACTS.get(phase_id, GENERIC_CONTRACT)

    system_parts = [
        f"You are the {owning_role} for the Presentations department, executing pipeline "
        f"phase {phase_id} as a real, autonomous worker -- your output is graded by a "
        f"mechanical verifier, not by a human skimming it. Follow your SOP below exactly. "
        f"Output ONLY the requested artifact content -- no chat, no preamble, no markdown "
        f"code fences wrapping the whole answer (fences INSIDE content, e.g. inside a "
        f".md file's own code blocks, are fine), no explanation of what you did.",
        "=== YOUR ROLE SOP (how-to.md) ===",
        role_context,
    ]
    if persona_bundle:
        system_parts.append(
            "=== GOVERNING BLENDED-PERSONA VOICE (already resolved by the engine for this "
            "phase -- write IN this voice, do not re-resolve or contradict it) ===\n"
            + json.dumps(persona_bundle, indent=2)[:8000]
        )
    system_prompt = "\n\n".join(system_parts)

    # NOTE: the OUTPUT CONTRACT is deliberately NOT included here anymore --
    # only ONE copy of it exists in the prompt now, placed at the very end
    # (below), where recency makes it far more likely to survive generation.
    user_parts = [
        f"=== WORK ORDER ===\n{json.dumps(order, indent=2)}",
        f"=== UPSTREAM ARTIFACTS ALREADY PRODUCED FOR THIS RUN ===\n{upstream}",
    ]
    # ROOT CAUSE (live run pj_34a56a26caca04532ec6e9cba6, 2026-08-18): this was gated
    # on `attempt > 1`, which only covers a retry WITHIN one dispatch_one() call. In
    # practice the Engine's own poll (phases.py) almost always sees a freshly-written-
    # but-verifier-failing artifact and BLOCKS the whole job before this loop reaches
    # attempt 2 (the documented race -- see this module's own history notes on the
    # empty-payload guard). The NEXT --resume spawns a brand-new dispatcher process,
    # dispatch_one() runs again, and its own idempotent pre-check (`ok, reasons =
    # _verify(...)`) already recovers the SAME real verifier reasons into
    # `prior_reasons` -- but at attempt=1 of the NEW call, so they were silently
    # dropped here every time, and the model started over blind on every single
    # --resume instead of ever seeing what it needs to fix. `prior_reasons` already
    # means "a real prior failure exists for this artifact" regardless of which
    # dispatch_one() call is speaking -- the attempt-number gate added nothing prior
    # attempts didn't already prove.
    # F10 (2026-09-06): the Engine's heal ladder reissues an agent phase's work
    # order with `heal_reason` -- the verbatim reason the last attempt failed
    # (a substance-verifier note, a "produced nothing" timeout, or the text of
    # this dispatcher's own retry-ceiling park marker). It is a prior finding
    # exactly like the ones recovered from the sidecar, and it belongs in the
    # SAME block: without it the model is handed a fresh-looking order and
    # starts over blind on the very retry that exists to fix a named defect.
    heal_reason = order.get("heal_reason") if isinstance(order, dict) else None
    if heal_reason:
        prior_reasons = list(prior_reasons or []) + [str(heal_reason)]
    if prior_reasons:
        user_parts.append(
            "=== YOUR PREVIOUS ATTEMPT FAILED THE REAL VERIFIER. Fix EXACTLY these named "
            "reasons, verbatim from the verifier -- do not guess, do not change unrelated "
            "content ===\n" + "\n".join(f"- {r}" for r in prior_reasons)
        )
    # THE LAST substantial thing the model reads before generating -- an
    # unmissable, verbatim restatement of the exact same contract text (see
    # module comment above compose_prompt for why this replaces the earlier,
    # buried placement rather than merely duplicating it).
    user_parts.append(
        "=== OUTPUT CONTRACT -- OBEY EXACTLY, THIS OVERRIDES ANYTHING ABOVE ===\n"
        + contract +
        "\n=== END OUTPUT CONTRACT -- everything above is the ONE, FINAL, LITERAL spec "
        "for the file you are about to write. Re-read it now before writing. ==="
    )
    user_parts.append(
        "Write the complete, final content of the target artifact file now. If the target "
        "is JSON, output ONLY the JSON object/array itself (no surrounding prose, no code "
        "fence). If the target is Markdown/text, output the complete file content directly."
    )
    user_prompt = "\n\n".join(user_parts)
    return system_prompt, user_prompt


# ---------------------------------------------------------------------------
# Extract a clean artifact payload from a raw DeepSeek completion. Strips a
# single outer ```...``` fence if the model wrapped its answer in one despite
# being told not to (cheap, common failure mode -- stripping it is not
# "fabricating content", it is un-wrapping the SAME content).
# ---------------------------------------------------------------------------
_FENCE_RE = re.compile(r"^```[a-zA-Z0-9_-]*\n(.*)\n```\s*$", re.DOTALL)


def _clean_payload(text: str) -> str:
    text = text.strip()
    m = _FENCE_RE.match(text)
    if m:
        text = m.group(1).strip()
    return text


# ---------------------------------------------------------------------------
# Target artifact path resolution -- prefers the REAL Phase object's
# resolve_artifact_patterns() (handles {deck_slug}/{run_dir} tokens
# correctly, matching exactly what the Engine's own _artifacts_present
# checks), falls back to the work order's raw produces_artifact list when no
# Manifest/Phase is available, then applies the two known manifest/verifier
# path overrides (spec S3 table notes).
# ---------------------------------------------------------------------------
def resolve_target_paths(phase_id: str, order: Dict[str, Any],
                          phase_obj: Optional[Phase], run_dir: Path) -> List[str]:
    if phase_id in ARTIFACT_TARGET_OVERRIDE:
        return ARTIFACT_TARGET_OVERRIDE[phase_id]
    if phase_obj is not None:
        resolved = phase_obj.resolve_artifact_patterns(run_dir)
        if resolved:
            return resolved
    raw = order.get("produces_artifact")
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        return [raw]
    return []


def _first_concrete_path(patterns: List[str], run_dir: Path) -> Optional[Path]:
    """Pick ONE concrete write target from produces_artifact pattern(s). A
    glob pattern (contains */?/[) cannot be written to directly -- synthesize
    a concrete filename inside its directory using the phase id, mirroring
    how a real author would name a new file matching that glob (e.g.
    'working/research/brief-*.md' -> 'working/research/brief-<phase>.md')."""
    for pat in patterns:
        if any(c in pat for c in "*?[") :
            # Only handle the common single-`*`-as-filename-stem case; anything
            # stranger is a real ambiguity this module should refuse to guess at.
            if pat.count("*") == 1:
                stem = pat.replace("*", "generated")
                return run_dir / stem
            continue
        return run_dir / pat
    return None


# ---------------------------------------------------------------------------
# The dispatch loop for ONE phase (spec S5.7): call, write atomically, run
# the SAME verifier the Engine will run, and either return on a real pass or
# retry with the exact prior failure reasons folded in. Never marks anything
# done; never touches state.json.
# ---------------------------------------------------------------------------
class DispatchResult:
    def __init__(self, phase_id: str, status: str, attempts: int,
                 reasons: Optional[List[str]] = None, target: Optional[str] = None,
                 slide_results: Optional[List[Dict[str, Any]]] = None):
        self.phase_id = phase_id
        self.status = status  # "ok" | "exhausted" | "declined" | "skipped_satisfied" | "error"
        self.attempts = attempts
        self.reasons = reasons or []
        self.target = target
        # Per-slide result list consumable by FIX 2: [{slide_id, ordinal, status, error}, ...]
        self.slide_results = slide_results or []

    def __repr__(self) -> str:
        return f"DispatchResult({self.phase_id}, {self.status}, attempts={self.attempts})"


def _sidecar_log_path(run_dir: Path, phase_id: str) -> Path:
    return run_dir / "working" / "work-orders" / f"{phase_id}.dispatcher-log.jsonl"


def _append_sidecar(run_dir: Path, phase_id: str, record: Dict[str, Any]) -> None:
    path = _sidecar_log_path(run_dir, phase_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = dict(record)
    record["at"] = utcnow()
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _stamp_author(run_dir: Path, phase_id: str, target: Path, *,
                  model: Optional[str], provider: Optional[str]) -> None:
    """PRES-042 — mint the AUTHOR execution stamp for one produced artifact
    revision. Called by the dispatcher (the TRUSTED writer) at the exact
    moment the artifact lands; never by the model. Best-effort: a stamp
    failure must never block a dispatch (the gate reads its absence as
    UNPROVEN, which is the fail-closed posture, not a crash)."""
    try:
        if _estamp.stamps_enabled():
            _estamp.author_stamp(run_dir, phase_id, target, model=model, provider=provider)
    except Exception as exc:  # noqa: BLE001 — stamping must never block dispatch
        try:
            _append_sidecar(run_dir, phase_id, {
                "worker": "stamp", "attempt": 0, "status": "stamp_failed",
                "reason": f"author stamp for {target.name} failed: {exc!r}",
            })
        except Exception:
            pass


# Phases whose produced artifact IS a QC review record (the manifest's
# *-QC / P-U-QC ids and their owning roles). Kept as an explicit tuple, not a
# regex, so a reviewer can read the exact set that gets reviewer-stamped.
_QC_PHASE_ID_TOKENS = ("QC",)
_QC_ROLE_TOKENS = ("qc-specialist", "qc_specialist")


def _is_qc_phase(owning_role: str, phase_id: str) -> bool:
    role = (owning_role or "").lower()
    pid = (phase_id or "").upper()
    if any(tok in role for tok in _QC_ROLE_TOKENS):
        return True
    return pid.endswith(tuple(f"-{tok}" for tok in _QC_PHASE_ID_TOKENS)) or pid in (
        "P-U-QC", "P-SHIFT-QC", "P-QC-AGGREGATE",
    )


def _stamp_qc_reviewer(run_dir: Path, phase_id: str, report_artifact: Path, *,
                       model: Optional[str], provider: Optional[str]) -> None:
    """PRES-042 — mint the REVIEWER execution stamp for a QC phase's produced
    report, binding the review to the artifacts the phase CONSUMED (the
    manifest's consumes list / the report's own grading targets) at their
    CURRENT sha. The reviewed-artifact binding is what makes 'mutate a
    reviewed file after pass => its QC is stale' mechanical.

    QC-SONNET-R4 (PRES-042 repair): the SAME reviewer execution ALSO stamps
    the produced REPORT itself. Without this, the aggregate's report-level
    gate (author+reviewer stamps covering the report's CURRENT bytes) could
    never pass on a production-dispatched run — every domain would block, and
    the stamp surface would be undeployable with its default-ON flag. One
    reviewer id binds both levels: 'this QC execution reviewed these inputs
    (at these shas) and attests these report bytes under this rubric'.
    Honest limits (documented, not hidden): the report-level pair proves
    dispatch integrity + sha currency, NOT cross-execution independence on its
    own — the author/review execution ids are dispatch-minted, so the
    exec-inequality leg passes trivially in production. The teeth against a
    same-worker forgery are the consumed-upstream coverage the aggregate ALSO
    verifies (reviewer stamp from THIS phase on each consumed input at its
    current sha, with the producer's author stamp and model classes on record)
    plus the legacy graded_by text provenance that still runs alongside."""
    consumed: List[Path] = []
    try:
        from presentation_job.manifest import Manifest
        # QC-OPUS seam repair: resolve via the run's pinned manifest / dept
        # sops / walk-up — the SAME resolution the aggregate's consumed-
        # coverage check uses, so stamps minted here always match what the
        # aggregate verifies (the old hand-rolled candidates missed in BOTH
        # layouts and silently downgraded to report-stamp-only).
        cand = _qc_manifest_for_run(run_dir)
        if cand is not None:
            man = Manifest(cand)
            ph = man.phase_or_none(phase_id)
            import glob as _glob
            for pat in (ph.consumes if ph else []) or []:
                for hit in _glob.glob(str(run_dir / pat)):
                    hp = Path(hit)
                    if hp.is_file():
                        consumed.append(hp)
    except Exception:
        consumed = []
    reviewer_execution_id = f"qc-{phase_id}-{os.getpid()}-{utcnow()}"
    rubric_version = _qc_rubric_version()
    for artifact in consumed:
        _estamp.qc_stamp(
            run_dir, phase_id, artifact,
            reviewer_execution_id=reviewer_execution_id,
            model=model, provider=provider,
            rubric_version=rubric_version,
        )
    # The report attestation itself (QC-SONNET-R4): best-effort like the rest —
    # a failure here must never block the dispatch that just succeeded.
    try:
        if report_artifact.is_file():
            _estamp.qc_stamp(
                run_dir, phase_id, report_artifact,
                reviewer_execution_id=reviewer_execution_id,
                model=model, provider=provider,
                rubric_version=rubric_version,
            )
    except Exception as exc:  # noqa: BLE001 — best-effort, never blocks
        try:
            _append_sidecar(run_dir, phase_id, {
                "worker": "stamp", "attempt": 0, "status": "qc_stamp_failed",
                "reason": f"report reviewer stamp failed: {exc!r}",
            })
        except Exception:
            pass


def _qc_manifest_for_run(run_dir: Optional[Path] = None) -> Optional[Path]:
    """PRES-042 (QC-OPUS seam repair): resolve the PIPELINE-MANIFEST.json the
    SAME way the rest of the engine and the aggregate do, so the reviewer
    stamps the dispatcher mints and the consumed-coverage the aggregate
    verifies always agree. Resolution order (never guesses past this list):
      1. the run's own pinned state.json manifest_path (authoritative per-run
         — the exact file the engine was launched with);
      2. <scripts_dir's parent>/sops/PIPELINE-MANIFEST.json (deployed
         department layout: manifest lives at <dept_root>/sops/, NOT
         scripts/sops/);
      3. manifest_source.find_repo_root() walk-up to the repo cluster copy
         (the canonical resolver qc_aggregate/_resolve_domain_paths uses).
    Returns None only when nothing resolves — the callers then degrade to the
    documented best-effort behavior (report-level stamp only / renderer-pin
    rubric), which the aggregate's own manifest-unresolvable branch mirrors."""
    if run_dir is not None:
        try:
            state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
            mp = state.get("manifest_path")
            if mp and Path(mp).is_file():
                return Path(mp).resolve()
        except (OSError, json.JSONDecodeError):
            pass
    scripts_dir = Path(__file__).resolve().parent  # .../scripts/presentation_job
    cand = (scripts_dir.parent.parent / "sops" / "PIPELINE-MANIFEST.json").resolve()
    if cand.is_file():
        return cand
    try:
        from manifest_source import find_repo_root
        root = find_repo_root(scripts_dir)
        if root is not None:
            cand = (root / "universal-sops" / "presentation-slide-craft"
                    / "PIPELINE-MANIFEST.json")
            if cand.is_file():
                return cand
    except Exception:  # noqa: BLE001 — resolver unavailability is not a stamp crash
        pass
    return None


def _qc_rubric_version() -> str:
    """The rubric version a QC phase graded against: the manifest revision
    when resolvable, else the scripts dir's CANONICAL-RENDERER-PIN hash
    (deterministic, reproducible)."""
    try:
        from presentation_job.manifest import Manifest
        cand = _qc_manifest_for_run()
        if cand is not None:
            man = Manifest(cand)
            version = getattr(man, "version", None)
            if version:
                return f"manifest-{version}"
    except Exception:
        pass
    pin = Path(__file__).resolve().parent.parent / "CANONICAL-RENDERER-PIN.sha256"
    try:
        if pin.is_file():
            return f"renderer-pin-{pin.read_text(encoding='utf-8').strip()[:16]}"
    except OSError:
        pass
    return "unknown"


def _verify(phase_id: str, run_dir: Path) -> Tuple[bool, List[str]]:
    import phase_verifiers  # top-level module in scripts_dir; see path bootstrap above
    return phase_verifiers.verify(phase_id, run_dir)


def _phase_already_done(run_dir: Path, phase_id: str) -> bool:
    """True when state.json already records this phase as status=='done' --
    a READ-ONLY check (bare json.loads, never StateStore/RunLock -- S5.5).

    Covers a case verify()-alone misses: Engine.run()'s converter-routing
    (phases.py._route_around_converter_phase) marks a phase done WITHOUT ever
    producing/expecting an artifact (verifier_ok stays None, artifacts stays
    empty) when that phase does not apply to this deck's creation_mode. Its
    work-order file can still be sitting in working/work-orders/ from an
    EARLIER attempt (written before the routing decision existed, or before
    this deck's creation_mode was known) -- nothing in the Engine ever
    deletes a stale work order. Without this check the dispatcher would spend
    a real DeepSeek call authoring an artifact for a phase the Engine has
    already, correctly, decided never to look at again. This is a pure
    efficiency guard, not a correctness one: dispatch_one's own verify()
    pre-check already makes an unnecessary dispatch harmless (never fabricates,
    never marks anything done) -- this just avoids paying for it."""
    try:
        state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    for ps in state.get("phases", []):
        if ps.get("id") == phase_id:
            return ps.get("status") == "done"
    return False


# ---------------------------------------------------------------------------
# P4-PROMPT special case (spec gap found live, run pj_34a56a26caca04532ec6e9cba6,
# 2026-08-18, iteration 3 -- found PROACTIVELY, before the phase ever blocked, by
# reading resolve_target_paths/_first_concrete_path against the REAL verifier
# (build_deck.check_prompt_qc_deterministic / resolve_prompt_path) rather than
# waiting for the doomed dispatch to burn 3 real attempts first).
#
# ROOT CAUSE: every phase dispatch_one() has ever handled until now produces ONE
# file (produces_artifact is a single path, or a single-`*` glob _first_concrete_
# path can synthesize one concrete name for). P4-PROMPT's produces_artifact,
# `working/prompts/slide-*.txt`, is fundamentally different: the REAL verifier
# (resolve_prompt_path, called once per ordinal 1..N inside
# check_prompt_qc_deterministic) requires N SEPARATE files -- slide-01.txt,
# slide-02.txt, ... slide-25.txt for this run's 25-slide deck -- each independently
# graded. The generic single-target loop would synthesize ONE wrongly-named file
# ("working/prompts/slide-generated.txt"), which check_prompt_qc_deterministic
# would never even look at (every real ordinal still reports "no prompt file"), so
# all 3 retry attempts were guaranteed to exhaust and BLOCK the phase regardless of
# content quality -- confirmed by reading the two functions side by side, not by
# waiting for it to fail live.
#
# FIX: a dedicated per-slide dispatch loop. Determine N the SAME way the real
# verifier does (_prompt_slide_count mirrors build_deck._count_output_slides'
# priority order exactly), then for each ordinal whose OWN file is missing or
# fails ITS OWN per-slide gate (_verify_single_prompt, which calls the REAL
# check_prompt_qc_deterministic and reads out just that ordinal's deficiency list
# -- never a reimplemented/looser copy of the rules), dispatch ONE DeepSeek call
# scoped to that single slide, with its own DISPATCH_RETRY_CAP retry budget and its
# own prior_reasons feedback loop -- exactly the same proven pattern every other
# phase already uses, just run N times instead of once.
# ---------------------------------------------------------------------------
def _prompt_slide_count(run_dir: Path) -> Optional[int]:
    """How many slide prompt files P4-PROMPT must produce. Mirrors
    build_deck._count_output_slides' priority order EXACTLY (minus the
    slides_path override, which no dispatch caller ever has) so this module and
    the real verifier can never disagree on N: working/copy/slides.json (a list,
    or {"slides":[...]}) first, then working/copy/arc_allocation.json's
    slides/slots/allocation array. Returns None when neither is present/readable
    yet (the phase is not ready to dispatch)."""
    def _len_from(obj) -> Optional[int]:
        if isinstance(obj, list):
            return len(obj)
        if isinstance(obj, dict) and "__parse_error__" not in obj:
            slides = obj.get("slides")
            if isinstance(slides, list):
                return len(slides)
        return None

    for rel in ("working/copy/slides.json", "slides.json", "working/slides.json"):
        p = run_dir / rel
        if not p.is_file():
            continue
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        n = _len_from(obj)
        if n is not None:
            return n

    arc = run_dir / "working" / "copy" / "arc_allocation.json"
    if arc.is_file():
        try:
            obj = json.loads(arc.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            obj = None
        if isinstance(obj, dict):
            slots = obj.get("slots") or obj.get("allocation") or obj.get("slides")
            if isinstance(slots, list):
                return len(slots)
        elif isinstance(obj, list):
            return len(obj)
    return None


def _verify_single_prompt(run_dir: Path, ordinal: int) -> Tuple[bool, List[str]]:
    """Check ONE slide's prompt file against the REAL rich-prompt gate
    (build_deck.check_prompt_qc_deterministic), reading out just that ordinal's
    own deficiency list so a per-slide dispatch loop can verify incrementally --
    correctly ignoring the (expected, irrelevant at this point) "missing" verdicts
    for every OTHER ordinal that has not been authored yet. Falls back to a bare
    length-floor/ceiling check if build_deck is unavailable (defensive; matches
    the degraded-mode pattern phase_verifiers.py already uses elsewhere)."""
    if _bd is None or not hasattr(_bd, "check_prompt_qc_deterministic"):
        p = run_dir / "working" / "prompts" / f"slide-{ordinal:02d}.txt"
        if not p.is_file():
            return False, ["no prompt file"]
        length = len(p.read_text(encoding="utf-8", errors="replace").strip())
        if length < 9000:
            return False, [f"AF-P1: {length} chars < 9,000 floor"]
        if length > 18000:
            return False, [f"AF-P2: {length} chars > 18,000 ceiling"]
        return True, ["NOTE: build_deck.check_prompt_qc_deterministic unavailable "
                       "-- degraded to a length-only check"]
    try:
        verdict = _bd.check_prompt_qc_deterministic(run_dir)
    except Exception as exc:  # noqa: BLE001 -- fail-closed, never crash the loop
        return False, [f"check_prompt_qc_deterministic raised {exc!r}"]
    slide_info = None
    if isinstance(verdict, dict):
        slide_info = (verdict.get("slides") or {}).get(ordinal)
    if slide_info is None:
        return False, [f"no verdict entry for slide {ordinal} (n_slides="
                       f"{verdict.get('n_slides') if isinstance(verdict, dict) else '?'})"]
    defs = slide_info.get("deficiencies") or []
    fatal = [d for d in defs if isinstance(d, dict)
            and d.get("severity") in ("fatal", "reauthor")]
    if fatal:
        # _pdef's schema (build_deck.py) is {code, severity, measured, required,
        # intelligence, fix} -- there is no "detail" key (a prior version of this
        # line read d.get("detail", "") and silently produced an empty reason
        # string on every real deficiency; caught before this ever dispatched a
        # live call by testing against the real run dir).
        return False, [f"{d.get('code', '?')} ({d.get('intelligence', '?')}): measured="
                       f"{d.get('measured', '?')!r} required={d.get('required', '?')!r} -- "
                       f"{d.get('fix', '')}" for d in fatal]
    return True, []


def _dispatch_prompt_phase(run_dir: Path, order: Dict[str, Any], *, dept_root: Path,
                           phase_obj: Optional[Phase], worker_id: str,
                           ordinals: Optional[List[int]] = None) -> DispatchResult:
    """PARALLEL-PIPELINE-SPEC Ticket 4 (2026-08-27): branches on
    `phase.workers` BEFORE any fan-out machinery is even reached. Absent or
    `1` => the LITERAL existing serial path (_dispatch_prompt_phase_serial,
    below, completely untouched) -- not "a pool of size one". This is the
    property that makes the whole feature safe to ship at `workers: 1`
    fleet-wide (spec S3.1): a phase that has never been fan-out-enabled
    cannot regress, because it never even imports the branch that changed."""
    phase_workers = phase_obj.workers if phase_obj else 1
    if phase_workers <= 1:
        return _dispatch_prompt_phase_serial(
            run_dir, order, dept_root=dept_root, phase_obj=phase_obj,
            worker_id=worker_id, ordinals=ordinals)
    return _dispatch_prompt_phase_fanout(
        run_dir, order, dept_root=dept_root, phase_obj=phase_obj,
        worker_id=worker_id, ordinals=ordinals, phase_workers=phase_workers)


def _dispatch_prompt_phase_serial(run_dir: Path, order: Dict[str, Any], *, dept_root: Path,
                           phase_obj: Optional[Phase], worker_id: str,
                           ordinals: Optional[List[int]] = None) -> DispatchResult:
    """P4-PROMPT's dedicated multi-file dispatch loop -- see the module comment
    above for the root cause this replaces. Never marks anything done, never
    touches state.json (same invariant as dispatch_one).

    `ordinals`: OPTIONAL manual-throughput escape hatch (iteration 2, live run
    pj_34a56a26caca04532ec6e9cba6). Each of the 25 slides is an independent
    unit -- its own file, its own verifier call, no shared mutable state
    except the append-only sidecar log -- so multiple OS processes can author
    DIFFERENT ordinals concurrently with zero risk of corrupting each other's
    output (os.replace() is atomic; a slide already verified+on-disk is
    skipped instantly by any worker that reaches it). The 25-slide phase
    previously ran ~3-9 real-DeepSeek-minutes PER SLIDE, fully serial inside
    ONE dispatch_one() call (~2-3 hours wall clock for one phase) -- a real
    throughput blocker, not a correctness one. Passing an explicit ordinal
    subset lets an operator partition the remaining slides across several
    concurrently-launched processes (see parallel_prompt_worker.py) instead
    of widening DISPATCH_RETRY_CAP or touching the verifier. Default (None)
    is UNCHANGED behavior: the full 1..n range, single process -- this is
    what dispatch_one() / the --watch loop always pass, so normal operation
    is byte-for-byte identical to before this parameter existed."""
    phase_id = "P4-PROMPT"
    n = _prompt_slide_count(run_dir)
    if n is None:
        reason = ("cannot determine slide count yet -- neither working/copy/"
                  "slides.json nor working/copy/arc_allocation.json (with a "
                  "slots/allocation/slides array) is present/readable")
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0, "status": "error", "reason": reason})
        return DispatchResult(phase_id, "error", 0, [reason])

    is_full_sweep = ordinals is None
    work_ordinals = list(range(1, n + 1)) if is_full_sweep else list(ordinals)

    owning_role = order.get("owning_role") or (phase_obj.owning_role if phase_obj else "")
    prompts_dir = run_dir / "working" / "prompts"
    total_attempts = 0
    final_reasons: List[str] = []
    slide_results: List[Dict[str, Any]] = []

    for ordinal in work_ordinals:
        target = prompts_dir / f"slide-{ordinal:02d}.txt"
        ok, reasons = _verify_single_prompt(run_dir, ordinal)
        if ok and target.is_file():
            # this slide already clears its own gate -- skip, no spend
            slide_results.append({
                "slide_id": f"slide-{ordinal:02d}", "ordinal": ordinal,
                "status": "succeeded", "error": None,
                "skipped_already_ok": True})
            continue

        slide_order = dict(order)
        slide_order["produces_artifact"] = [f"working/prompts/slide-{ordinal:02d}.txt"]
        slide_order["_prompt_slide_ordinal"] = ordinal
        slide_order["_prompt_slide_total"] = n

        prior_reasons: Optional[List[str]] = reasons if reasons else None
        last_reasons: List[str] = reasons
        slide_ok = False

        for attempt in range(1, DISPATCH_RETRY_CAP + 1):
            total_attempts += 1
            try:
                system_prompt, user_prompt = compose_prompt(
                    phase_id=phase_id, owning_role=owning_role, dept_root=dept_root,
                    run_dir=run_dir, order=slide_order, attempt=attempt,
                    prior_reasons=prior_reasons,
                )
            except RoleSOPNotFound as exc:
                _append_sidecar(run_dir, phase_id, {
                    "worker": worker_id, "attempt": attempt, "slide": ordinal,
                    "status": "error", "reason": f"RoleSOPNotFound: {exc}"})
                # FIX 3: used to abort the WHOLE phase here. A missing SOP is
                # raised before any provider call (zero spend) and fails every
                # slide identically, but the phase result must still name every
                # unresolved slide, so record it through the shared per-slide
                # failure path below and move on to the next ordinal.
                last_reasons = [f"RoleSOPNotFound: {exc}"]
                break

            # Per-slide scoping instruction, prepended so ONE role SOP + ONE
            # contract serves every slide -- this text names exactly which slide
            # THIS call authors and forbids it from wandering onto neighbors.
            user_prompt = (
                f"=== THIS CALL AUTHORS EXACTLY ONE FILE: SLIDE {ordinal} OF {n} ===\n"
                f"Find slide {ordinal}'s block in slides_copy.md above (the line "
                f"reading exactly `SLIDE {ordinal}`) and author ONLY its rich "
                f"image-generation prompt. Output ONLY that one slide's complete "
                f"9,000-18,000-char prompt body -- no slide-number header, no "
                f"preamble, no other slide's content.\n\n" + user_prompt
            )

            # FIX 7: routed completion -- the profile decides the transport
            # (DeepSeek-direct stays the default + one option among many).
            route_dict: Dict[str, Any] = {}
            try:
                content, usage, route_dict = dispatch_complete(
                    system_prompt, user_prompt, phase_id=phase_id,
                    run_dir=run_dir)
            except RoutingUnavailable as exc:
                # no client-owned model can serve this phase: park the slide
                # honestly (fail-closed), never fabricate a route.
                last_reasons = [f"RoutingUnavailable: {exc}"]
                _append_sidecar(run_dir, phase_id, {
                    "worker": worker_id, "attempt": attempt, "slide": ordinal,
                    "status": "routing_unavailable", "reason": str(exc)})
                break
            except DeepSeekCallError as exc:
                last_reasons = [f"Model call failed: {exc}"]
                _append_sidecar(run_dir, phase_id, {
                    "worker": worker_id, "attempt": attempt, "slide": ordinal,
                    "status": "call_failed", "reason": str(exc)})
                if attempt < DISPATCH_RETRY_CAP:
                    time.sleep(min(30, 5 * attempt))
                    continue
                break

            payload = _clean_payload(content)
            if not payload.strip():
                _append_sidecar(run_dir, phase_id, {
                    "worker": worker_id, "attempt": attempt, "slide": ordinal,
                    "status": "empty_completion", "usage": usage})
                last_reasons = ["DeepSeek returned an empty completion"]
                if attempt < DISPATCH_RETRY_CAP:
                    continue
                break

            target.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = target.with_suffix(
                target.suffix + f".partial-{os.getpid()}-{attempt}")
            tmp_path.write_text(payload, encoding="utf-8")
            os.replace(tmp_path, target)

            v_ok, v_reasons = _verify_single_prompt(run_dir, ordinal)
            _append_sidecar(run_dir, phase_id, {
                "worker": worker_id, "attempt": attempt, "slide": ordinal,
                "status": "verified" if v_ok else "failed", "verifier_ok": v_ok,
                "verifier_reasons": v_reasons,
                "model": route_dict.get("model") or DEEPSEEK_MODEL,
                "provider": route_dict.get("provider") or "deepseek-direct",
                "target": str(target.relative_to(run_dir)), "usage": usage})
            if v_ok:
                # PRES-042: stamp the AUTHOR execution on the verified artifact.
                _stamp_author(run_dir, phase_id, target,
                              model=route_dict.get("model") or DEEPSEEK_MODEL,
                              provider=route_dict.get("provider") or "deepseek-direct")
                slide_ok = True
                break
            last_reasons = v_reasons
            prior_reasons = v_reasons

        if slide_ok:
            slide_results.append({
                "slide_id": f"slide-{ordinal:02d}", "ordinal": ordinal,
                "status": "succeeded", "error": None})
            continue

        # FIX 3: this slide exhausted its own retry budget -- record the failure
        # and KEEP GOING through the remaining slides. The old behavior
        # returned here on the first exhausted slide, silently discarding every
        # later slide's chance to author. The phase now fails only AFTER every
        # slide got its own full retry behavior, and the failure report names
        # exactly which slides failed (never a bare "phase aborted"). The
        # resume property is unchanged: every already-good slide is still
        # skipped instantly by the ok-and-exists check above, and nothing
        # already written is lost or re-spent.
        exhausted_reasons = [f"slide {ordinal}: {r}" for r in last_reasons]
        final_reasons.extend(exhausted_reasons)
        slide_results.append({
            "slide_id": f"slide-{ordinal:02d}", "ordinal": ordinal,
            "status": "failed", "error": "; ".join(exhausted_reasons)})
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": DISPATCH_RETRY_CAP, "slide": ordinal,
            "status": "exhausted", "final_reasons": last_reasons})

    # FIX 3: every ordinal THIS CALL owns has now been through its own full
    # retry budget -- a failed slide no longer cuts the loop short. If any
    # slide is still unresolved, the phase fails HERE, after every slide got
    # its chance, and the report names exactly which slides failed (plus the
    # per-slide result list consumed by FIX 2). Successful slides authored in
    # this pass are kept on disk and never re-spent by the next sweep call.
    if final_reasons:
        failed_slides = [s["slide_id"] for s in slide_results
                         if s["status"] == "failed"]
        succeeded_slides = [s["slide_id"] for s in slide_results
                            if s["status"] == "succeeded"]
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": total_attempts,
            "status": "phase_exhausted",
            "failed_slides": failed_slides,
            "succeeded_slides": succeeded_slides,
            "note": "all owned slides attempted; phase fails for the named "
                    "slides only",
        })
        return DispatchResult(phase_id, "exhausted", total_attempts,
                              final_reasons, "working/prompts/",
                              slide_results=slide_results)

    # Every ordinal THIS CALL owns cleared its own gate. The real whole-phase
    # verify() also folds in the deck-level writing-engine backstop and
    # directory-level duplicate/name checks the per-slide loop above never
    # sees -- but it requires ALL n slides to exist, so a partial-range call
    # (a manual-throughput worker handed a subset via `ordinals`) must NOT
    # run it: with other ordinals possibly still unwritten by sibling
    # workers, _verify() would correctly report "failed" every time and this
    # call would misreport its own subset as a phase-level failure. Only the
    # full-range call (ordinals=None -- the normal dispatch_one()/--watch
    # path) is authoritative for the whole phase.
    if not is_full_sweep:
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": total_attempts,
            "status": "subset_ok", "ordinals": work_ordinals,
            "note": "partial-range worker finished its subset; whole-phase "
                    "verify() deferred to a full-sweep call",
        })
        return DispatchResult(phase_id, "ok", total_attempts, [],
                              "working/prompts/ (subset)",
                              slide_results=slide_results)

    ok, reasons = _verify(phase_id, run_dir)
    _append_sidecar(run_dir, phase_id, {
        "worker": worker_id, "attempt": total_attempts,
        "status": "verified" if ok else "failed", "verifier_ok": ok,
        "verifier_reasons": reasons,
    })
    if ok:
        return DispatchResult(phase_id, "ok", total_attempts, [], "working/prompts/",
                              slide_results=slide_results)
    return DispatchResult(phase_id, "exhausted", total_attempts, reasons,
                          slide_results=slide_results)


# ---------------------------------------------------------------------------
# FIX 2: parallel P4-PROMPT dispatch. The dispatcher branch REMAINS the owner of
# the phase: it selects the slides, stamps the routing (Phase A stub:
# deepseek-direct / deepseek-v4-flash / measured capacity 8 until FIX 7/8/11
# provide real profiles), builds prompt-wave-input.json, invokes the worker ONCE,
# ingests the result file, emits FIX 5-style per-slide telemetry rows, and
# advances only when every required ordinal succeeded with an on-disk SHA match
# and a passing verify verdict. PRESENTATION_PROMPT_PARALLEL=0 selects the
# untouched serial loop above (byte-for-byte rollback path; the serial loop
# stays until the operator-box proof window ends).
# ---------------------------------------------------------------------------
def _prompt_parallel_enabled() -> bool:
    """Default ON. The only value that disables is exactly "0" (also strip
    quotes/whitespace so `PRESENTATION_PROMPT_PARALLEL=""` counts as unset,
    not OFF -- an EMPTY value must never silently select the rollback path)."""
    raw = os.environ.get("PRESENTATION_PROMPT_PARALLEL")
    if raw is None:
        return True
    return raw.strip().strip("'\"") != "0"


# ---------------------------------------------------------------------------
# U1 (2026-09-07) -- the two helpers the width authority below is built on.
#
# THE BUG U1 REMOVES: capacity.probe() correctly answers UNBOUNDED for a
# NO_CAP_PROVIDERS account (capacity.NO_CAP_PROVIDERS = {"openrouter"},
# capacity.py:259 -- the operator's 2026-08-18 ruling "do not limit someone who
# brought their own capacity"), and `_routing_stamp` then REPLACED that reading
# with DEFAULT_MAX_WORKERS. Because the mode ceiling is applied afterwards as a
# min() (model_router.capped_width), ultra could never lift it back: MEASURED on
# the operator box 2026-09-07, an OpenRouter route stamped measured_capacity 8
# under BOTH ultra and standard. Since F6 (1602a5d39) that same number is also
# the width of all nine manifest fan-out phases, so the 8 governed the whole
# fan-out surface. Operator requirement, verbatim: "if I am using OpenRouter I
# should not be capped at 8. I should be able to use at least 100 agents in
# parallel if I'm using OpenRouter."
# ---------------------------------------------------------------------------
def _unbounded_width(mode: str,
                     decision: Optional[Dict[str, Any]] = None) -> Optional[int]:
    """The width an UNBOUNDED capacity reading resolves to: THE MODE CEILING.

    UNBOUNDED is a READING ("this account has no structural ceiling"), never an
    absence, so the only thing allowed to bound it is the mode's own
    human-ratified ceiling -- ultra 100 (model_router.ULTRA_OPERATOR_CEILING),
    standard whatever STANDARD_MODE_CEILING resolves to for this client -- and
    the unit count, which parallel_prompt_worker._workers_for and
    fanout.resolve_effective_workers apply downstream. Never DEFAULT_MAX_WORKERS.

    `decision` is resolve_route()'s own block: when it carries `mode_ceiling`
    that value is PROFILE-AWARE (it was computed against this client's declared
    concurrency_ceiling) and is preferred. Falling back to
    model_router.mode_ceiling(mode) with no profile yields the operator ceiling
    for every mode -- which is mode_operator_ceiling()'s documented behaviour on
    an unmeasured client (the axis is inert), not a widening invented here.

    Returns None when model_router is absent -- the caller then keeps the
    pre-FIX-7 rollback number, byte for byte."""
    if _model_router is None:
        return None
    block = (decision or {}).get("mode_ceiling")
    if not isinstance(block, dict):
        try:
            block = _model_router.mode_ceiling(mode)
        except Exception:  # noqa: BLE001 -- a ceiling that cannot be computed
            block = None                       # falls through to the constant
    ceiling = (block or {}).get("ceiling")
    try:
        ceiling = int(ceiling)
    except (TypeError, ValueError):
        ceiling = 0
    if ceiling >= 1:
        return ceiling
    try:
        return int(_model_router.ULTRA_OPERATOR_CEILING)
    except Exception:  # noqa: BLE001 -- router present but shape unexpected
        return None


def _conservative_floor() -> Optional[int]:
    """capacity.DEFAULT_CONSERVATIVE -- "the floor every unknown collapses to.
    NEVER guess upward" (capacity.py:204-205). The number a REFUSED width
    carries, because it is the one the capacity module itself owns for an
    unknown; DEFAULT_MAX_WORKERS is a worker-pool default and answers a
    different question entirely. None when capacity.py cannot be imported."""
    try:
        from presentation_job import capacity as _cap
        floor = int(_cap.DEFAULT_CONSERVATIVE)
        return floor if floor >= 1 else None
    except Exception:  # noqa: BLE001 -- capacity.py gone is the one case where
        return None                        # DEFAULT_MAX_WORKERS is still honest


def _probe_accepts(fn: Any, name: str) -> bool:
    """Does this `capacity.probe`/`detect` accept the keyword `name`?

    F4 FORWARD GUARD (2026-09-07). The agreed signature is
    `capacity.probe(config_dir=None, *, provider=None, model=None)`, but this
    module must not explode on a build of capacity.py that predates it (nor on
    a test double that takes no arguments at all -- e.g.
    tests/test_capacity_detection.py's `def boom()`). Asking the callee what
    it accepts is the only honest way to tell "this build has no per-provider
    probe" apart from "the probe raised a TypeError of its own", which a
    try/except TypeError would silently conflate and mislabel as a capacity
    failure. A `**kwargs` double accepts everything, which is exactly what the
    existing `lambda *a, **k` probe stubs are."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):  # unintrospectable callable
        return False
    param = params.get(name)
    if param is not None and param.kind in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY):
        return True
    return any(p.kind is inspect.Parameter.VAR_KEYWORD
               for p in params.values())


def _probe_routed_capacity(cap_mod: Any, *, provider: str,
                           model: str) -> Tuple[Any, Dict[str, str]]:
    """F4 (2026-09-07): PROBE THE PROVIDER THIS STAMP WILL ACTUALLY DISPATCH TO.

    THE DEFECT this replaces: `_routing_stamp` called `capacity.probe()` with
    no arguments, and `probe()` answers about exactly ONE provider -- the one
    detection resolved (or, before F1/F2, whichever single provider
    capacity_override.json happened to name). On a two-provider client that
    global answer is right for at most one route, and the identity guard below
    then correctly refused the OTHER route down to capacity.DEFAULT_CONSERVATIVE
    (3). MEASURED by Fable on this box 2026-09-07: an ollama-cloud plan answer
    made `probe()` answer `ollama-cloud/8` while P4-PROMPT routed to
    deepseek-direct -- providers_match False -> refusal -> width 3, with a real
    2,500 measurement sitting one keyword argument away. There is no single
    global answer that satisfies a two-provider client; the question itself was
    wrong.

    So the question now names the route: `probe(provider=<routed>,
    model=<route model>)`. The identity guard STAYS -- it becomes a tautology
    on a capacity build that honours the kwarg, which is the point: the only
    way it can fire afterwards is a provider id this build cannot canonicalise,
    and that is still the right loud failure, never a quiet width.

    Returns (probe_result, kwargs_actually_passed). An empty kwargs dict means
    this capacity build has no per-provider probe and the caller got today's
    global answer -- recorded on the stamp as `probe_scope`, never hidden."""
    kwargs: Dict[str, str] = {}
    probe_fn = getattr(cap_mod, "probe")
    if provider and _probe_accepts(probe_fn, "provider"):
        kwargs["provider"] = provider
    if model and kwargs.get("provider") and _probe_accepts(probe_fn, "model"):
        # `model` is only ever a REFINEMENT of `provider` (it resolves the plan
        # tier for that provider -- capacity._plan_from_model_slug). Sending it
        # without a provider would ask a question nobody asked.
        kwargs["model"] = model
    return probe_fn(**kwargs), kwargs


def _refuse_unmeasured_width(stamp: Dict[str, Any], *,
                             run_dir: Optional[Path], phase_id: str,
                             missing: str, detail: str,
                             provider: Optional[str] = None) -> None:
    """REFUSE LOUDLY, naming the missing value -- never a silent 8.

    Operator ruling (2026-09-07): "system need to ask if unclear ... never
    silently substitute a fabricated number." This is the truly-unknown branch:
    the probe could not establish a capacity FOR THE PROVIDER THIS STAMP WILL
    DISPATCH TO (PARKED/UNDETERMINED, a probe about a genuinely different
    provider, an identity neither side could resolve, or a probe that raised).

    WHERE THE REFUSAL SURFACES -- three places, all of them durable:
      1. stderr, as `REFUSING ... AF-CAPACITY-UNMEASURED: <detail> MISSING:
         <value>` -- the engine's stderr is the run log the poller captures;
      2. the phase's own sidecar (`working/work-orders/<phase>.jsonl`), status
         `capacity_width_refused`, so the refusal outlives the log line and is
         readable per phase after the fact;
      3. the stamp itself, `capacity_refusal`, which travels into the wave
         input (WaveContract.RoutingStamp extras) and into the fan-out sidecar
         rows written by _dispatch_phase_fanout_units.
    A run whose capacity was never measurable AT ALL is refused EARLIER and
    harder -- launcher._refuse_unmeasured_capacity / _refuse_undetermined_parallel
    emit the same AF-CAPACITY-UNMEASURED and exit DISPATCH_CAPACITY_REFUSED with
    no engine spawned. This function covers what that gate cannot see: a
    PER-ROUTE attribution failure discovered after dispatch has begun.

    It does NOT raise. `_routing_stamp`'s contract -- stated in its own
    docstring and relied on by every caller -- is that a stamp failure never
    breaks P4-PROMPT, and F41's wave contract rejects a non-positive-int
    measured_capacity outright ("routing.measured_capacity must be a positive
    integer"), so a None here would kill the wave with an unrelated error
    message instead of the reason. LOUD means announced and recorded, and the
    width that proceeds is the conservative floor, labelled as a refusal."""
    floor = _conservative_floor()
    basis = "capacity.DEFAULT_CONSERVATIVE"
    if floor is None:                       # capacity.py itself is unreachable
        floor, basis = DEFAULT_MAX_WORKERS, "dispatcher.DEFAULT_MAX_WORKERS"
    stamp["measured_capacity"] = int(floor)
    stamp["capacity_refusal"] = {
        "code": CAPACITY_REFUSAL_CODE,
        "phase_id": phase_id,
        "missing": missing,
        "detail": detail,
        "width_applied": int(floor),
        "width_basis": basis,
    }
    # F4 (2026-09-07): the old instruction was "Declare capacity_override.json
    # for this provider". THAT ADVICE IS THE OTHER HALF OF THE DEFECT. Before
    # F1/F2 the override file is a SINGLE-PROVIDER, whole-client answer that
    # pre-empts detection (capacity.detect step (a)), so an operator following
    # it to widen route A silently pinned every OTHER route to A's plan --
    # MEASURED on this box 2026-09-07: writing an ollama-cloud $100/month
    # record to widen the QC phases made capacity.probe() answer
    # `ollama-cloud/8` for the DeepSeek-primary wave that had measured 2,500.
    # Name the provider whose plan is missing, and point at the two doors that
    # are per-provider: the capacity interview, and --declare-provider.
    who = str(provider or "").strip() or "the routed provider"
    msg = (f"{phase_id} routing stamp: REFUSING to fabricate a fan-out width -- "
           f"{CAPACITY_REFUSAL_CODE}: {detail} MISSING: {missing}. Proceeding at "
           f"the conservative floor {floor} ({basis}), NOT at "
           f"{DEFAULT_MAX_WORKERS} -- a fabricated 8 here is indistinguishable "
           f"from the operator's deliberate Ollama reserve. To widen it, answer "
           f"the capacity interview FOR {who} (python3 -m presentation_job "
           f"--capacity), or declare that one provider explicitly: "
           f"--declare-capacity N --declare-provider {who}. Do NOT hand-write a "
           f"whole-client capacity_override.json to fix this route: one "
           f"provider's declaration must never answer for another.")
    print(f"WARNING: {msg}", file=sys.stderr, flush=True)
    try:
        _append_sidecar(run_dir, phase_id, {
            "status": "capacity_width_refused",
            "code": CAPACITY_REFUSAL_CODE,
            "missing": missing,
            "reason": msg,
            "width_applied": int(floor),
        })
    except Exception:  # noqa: BLE001 -- sidecar is best-effort, never a break
        pass


def _routing_stamp(run_dir: Optional[Path] = None,
                   phase_id: str = "P4-PROMPT") -> Dict[str, Any]:
    """FIX 7 profile-driven routing stamp for a phase that decides a WIDTH.

    F6 (2026-09-06): renamed from `_prompt_routing_stamp` -- this stamp is not
    P4-PROMPT-specific. It is the ONE authority that turns (client resource
    profile -> route -> capacity probe -> mode ceiling) into a worker-slot
    count, and `_dispatch_phase_fanout_units` now reads the SAME number for
    every manifest-declared fan-out phase instead of the manifest's
    `phase.workers` (absent => 1). `phase_id` selects the route (its
    capability lookup) and names the sidecar rows; it defaults to "P4-PROMPT"
    so the pre-F6 call shape -- and the `_prompt_routing_stamp` alias kept
    below for existing callers/tests -- behaves byte-identically.

    Original contract, unchanged: the P4-PROMPT wave input.
    Resolves the route through model_router.resolve_route (the client resource
    profile decides), falling back to the pre-FIX-7 DeepSeek-direct stamp when
    the router is absent/flagged off/profile not yet captured. The wave input
    shape is unchanged; only the VALUES become profile-truth. (The Phase A
    measured_capacity=8 stamp was a hardcoded fabrication -- FIX 6 removes that
    fiction; this stamp carries routing truth only.)"""
    # FIX 11 wire: the REAL mode of this run (was hardcoded "standard" here
    # and in the resolve_route call below, so the P4-PROMPT fan-out -- the one
    # place the engine actually decides a width -- could never be told that an
    # Ultra or Economy run was in progress).
    _mode, _mode_source = _active_mode()
    stamp: Dict[str, Any] = {
        "provider": "deepseek-direct",
        "model": DEEPSEEK_MODEL,
        "router": "disabled",
        "mode": _mode,
        "mode_source": _mode_source,
        "measured_capacity": DEFAULT_MAX_WORKERS,
    }
    # F41 (SMOKE-1, 2026-09-01): FIX 7 popped measured_capacity whenever the
    # router resolved a profile route -- but the parallel_prompt_worker usage
    # contract (routing.measured_capacity must be a positive int,
    # parallel_prompt_worker.py validate_input) rejects the whole wave input,
    # so EVERY router-resolved wave self-rejected with
    # "routing.measured_capacity must be a positive integer (got None)" before
    # any provider call. The stamp must always carry a worker-slot count.
    # Derive it from the capacity probe -- never fabricate a provider claim.
    # U1 (2026-09-07) rewrote all three arms; the pre-U1 text is kept inline so
    # the change is legible:
    #   * UNBOUNDED (NO_CAP_PROVIDERS BYOK hit -- capacity.NO_CAP_PROVIDERS is
    #     {"openrouter"}; operator ruling fix/capacity-uncap-byok: never limit
    #     someone who brought their own capacity) -> THE MODE CEILING
    #     (_unbounded_width: ultra 100, standard its own share), bounded
    #     downstream by the slide/unit count.
    #     WAS: "-> DEFAULT_MAX_WORKERS (8) worker slots; the worker itself
    #     clamps to its own DEFAULT_MAX_WORKERS=8 ceiling." Both halves were
    #     wrong by 2026-09-07: the 8 discarded a correct reading, and
    #     parallel_prompt_worker._workers_for stopped re-clamping a measured
    #     width to 8 with the 2026-09-04 ruling. F17 (382388378) named this
    #     mapping in its own commit message and shipped around it; F6
    #     (1602a5d39) then made it the width of all nine fan-out phases.
    #   * MEASURED positive int for THIS route -> that real cap-table ceiling.
    #   * probe PARKED/UNDETERMINED/FAILED for the routed provider, a probe
    #     about a genuinely DIFFERENT provider, an unresolvable identity, or a
    #     probe that raised -> REFUSE LOUDLY (_refuse_unmeasured_width): stderr
    #     + sidecar + a `capacity_refusal` block, proceeding at
    #     capacity.DEFAULT_CONSERVATIVE, never at a silent 8.
    #     WAS: "-> DEFAULT_MAX_WORKERS, honestly labelled capacity_status so
    #     the audit trail never reads as a measurement." The label was honest;
    #     the NUMBER was still a fabrication, and 8 is the one number that
    #     cannot be told apart from the operator's deliberate Ollama reserve.
    # The capacity PARK about a DIFFERENT provider (e.g. 9router combo routing
    # an unrelated model to ollama-cloud) does not gate this route: the
    # launcher's AF-CAPACITY-UNMEASURED refuse already ran before dispatch --
    # but it cannot see a PER-ROUTE attribution failure, which is why the third
    # arm now refuses here too.
    stamp["capacity_status"] = "fallback-default"
    stamp["capacity_source"] = "dispatcher-default"
    if _model_router is None:
        return stamp
    decision: Optional[Dict[str, Any]] = None
    try:
        decision = _model_router.resolve_route(phase_id, mode=_mode)
        route = (decision or {}).get("route")
        profile_state = (decision or {}).get("profile_state")
        routed_provider = ""
        routed_model = ""
        if profile_state == "has_providers" and route:
            stamp.update({
                "provider": str(route.get("provider")),
                "model": str(route.get("model")),
                "router": str(decision.get("router") or "model_router"),
                "route_reason": decision.get("reason"),
                "requested_alias": decision.get("requested_alias"),
            })
            routed_provider = str(route.get("provider") or "")
            # F4: the route's MODEL, not just its provider. capacity resolves a
            # plan tier from the model slug (_plan_from_model_slug), so handing
            # it over is what lets a deepseek-v4-flash route be answered
            # `v4-flash / 2500` instead of PARKing on "provider known, plan
            # unknown".
            routed_model = str(route.get("model") or "")
        elif profile_state == "absent":
            # U1 SECOND CASE (2026-09-07) -- A CLIENT WITH NO PROFILE DROPPED TO
            # 8 EVEN WHEN THE PROBE HAD MEASURED 2,500.
            #
            # `profile_state == "absent"` means resolve_route found no
            # client-owned providers (or no resource_profile store at all), so
            # it returns route=None and the dispatcher serves the phase from its
            # OWN default -- stamp["provider"], "deepseek-direct", set at the top
            # of this function. Until U1 the probe block below was gated on
            # has_providers, so that whole branch was skipped and the stamp kept
            # measured_capacity = DEFAULT_MAX_WORKERS.
            # MEASURED on the operator box 2026-09-07, scratch-redirected state:
            # an empty profile with capacity_override.json
            # {"provider":"deepseek-direct","plan":"v4-flash"} probed
            # MEASURED/deepseek-direct/2500 and the stamp still said 8 under
            # ultra AND standard. That is a REAL MEASUREMENT being discarded --
            # strictly worse than the UNBOUNDED case, because a number existed.
            #
            # There is nothing to attribute badly here: the provider the probe
            # measured and the provider this stamp will dispatch to are compared
            # by the same normalize_provider() identity test as any routed
            # provider, so a probe about somebody else still refuses. What
            # changes is only that "the client declared no providers" stops
            # meaning "throw away what we measured about the provider we are
            # about to use".
            routed_provider = str(stamp.get("provider") or "")
            routed_model = str(stamp.get("model") or "")
            stamp["route_reason"] = (decision or {}).get("reason")
        # Any other profile_state -- "mechanical" (no LLM route exists) or a
        # router-disabled decision carrying no profile_state at all
        # (PRESENTATION_MODEL_ROUTER=0, the byte-for-byte pre-FIX-7 rollback) --
        # is left exactly as it was: routed_provider stays "" and the base stamp
        # returns untouched. U1 widens nothing on a rollback path.
        if routed_provider:
            try:
                from presentation_job import capacity as _cap_mod
                # F4 (2026-09-07) -- THE STAMP ASKS ABOUT ITS OWN ROUTE.
                # `probe()` with no arguments answers about ONE provider (the
                # detected primary, or whichever single provider a legacy
                # capacity_override.json names). That answer is right for at
                # most one route on a two-provider client, and the identity
                # guard below then refuses every other route down to
                # DEFAULT_CONSERVATIVE=3 -- correctly, given the question it
                # was asked. The question was the bug. See
                # _probe_routed_capacity for the measurement and the
                # forward-guard on capacity builds that predate the kwarg.
                probe_res, probe_kwargs = _probe_routed_capacity(
                    _cap_mod, provider=routed_provider, model=routed_model)
                stamp["probe_scope"] = ("routed-provider"
                                        if probe_kwargs.get("provider")
                                        else "global-no-arg")
                if probe_kwargs:
                    stamp["probe_requested"] = dict(probe_kwargs)
                # The agreed contract adds `provider_requested` to the result,
                # so the stamp can record what capacity BELIEVES it was asked
                # -- attribution evidence that survives into the sidecar.
                _asked = probe_res.get("provider_requested")
                if _asked is not None:
                    stamp["probe_provider_requested"] = _asked
                available = probe_res.get("available")
                probe_provider = str(probe_res.get("provider") or "")
                # DEFECT-5 REPAIR (2026-09-05): compare provider IDENTITY, not
                # SPELLING. `probe_res["provider"]` is always canonical -- the
                # probe runs every id through capacity.normalize_provider().
                # `route["provider"]` is NOT: model_router.resolve_alias()
                # normalises served_ids keys but hands the catalog's own
                # provider string straight through, and model_catalog.json
                # spells DeepSeek "deepseek". Measured live on the shipped
                # table, this box, 2026-09-05:
                #     resolve_alias("deepseek-v4-pro")["provider"] -> 'deepseek'
                #     capacity.probe()["provider"]                 -> 'deepseek-direct'
                # so the raw `probe_provider == routed_provider` this replaces
                # was FALSE on every DeepSeek route -- the department default
                # for authoring/prompt_authoring/reasoning -- and a real
                # measured ceiling (2500 Flash / 500 Pro) was silently thrown
                # away for DEFAULT_MAX_WORKERS on every router-resolved run.
                # Both sides are folded through the ONE cap-table authority.
                probe_canon = _cap_mod.normalize_provider(probe_provider)
                routed_canon = _cap_mod.normalize_provider(routed_provider)
                stamp["probe_provider"] = probe_provider
                stamp["routed_provider"] = routed_provider
                stamp["probe_provider_canonical"] = probe_canon
                stamp["routed_provider_canonical"] = routed_canon
                # normalize_provider returns None for anything the cap table
                # does not cover. An UNRESOLVABLE id on either side is not a
                # "different provider" -- it is a provider identity this build
                # cannot establish, and it must never look like a quiet
                # measurement decision. Say so on stderr AND in the sidecar,
                # then fall back labelled. (Never `raise`: this function's
                # contract is that a stamp failure never breaks P4-PROMPT --
                # see the `except` below -- so LOUD here means announced and
                # recorded, not a dead wave.)
                provider_unresolved = (probe_canon is None or routed_canon is None)
                if provider_unresolved:
                    _msg = (f"{phase_id} routing stamp: provider identity is "
                            f"UNRESOLVABLE against the capacity cap table -- "
                            f"routed={routed_provider!r}->{routed_canon!r}, "
                            f"probed={probe_provider!r}->{probe_canon!r}. The "
                            f"measured ceiling cannot be attributed to this "
                            f"route; the width is REFUSED (U1) and labelled "
                            f"capacity_status=provider-unresolved -- see the "
                            f"{CAPACITY_REFUSAL_CODE} line that follows for the "
                            f"width actually applied.")
                    print(f"WARNING: {_msg}", file=sys.stderr, flush=True)
                    try:
                        _append_sidecar(run_dir, phase_id, {
                            "status": "routing_provider_unresolved",
                            "reason": _msg,
                            "routed_provider": routed_provider,
                            "probe_provider": probe_provider,
                        })
                    except Exception:  # noqa: BLE001 -- sidecar is best-effort
                        pass
                providers_match = bool(
                    probe_canon is not None and probe_canon == routed_canon)
                unbounded_width = (_unbounded_width(_mode, decision)
                                   if _cap_mod.is_unbounded(available) else None)
                if unbounded_width is not None and providers_match:
                    # U1 THE HEADLINE FIX. An UNBOUNDED reading about THIS
                    # route resolves to the MODE CEILING -- ultra 100 for a
                    # client whose own ceiling does not say less -- and is then
                    # bounded by the slide/unit count downstream. The min()
                    # below re-applies the same ceiling and is a no-op, which is
                    # the point: nothing can lower this except a real ceiling.
                    stamp["measured_capacity"] = int(unbounded_width)
                    stamp["capacity_status"] = "unbounded-byok"
                    stamp["capacity_source"] = str(
                        probe_res.get("detection_source") or "capacity-probe")
                elif (isinstance(available, int) and available > 0
                        and providers_match):
                    stamp["measured_capacity"] = available
                    stamp["capacity_status"] = "measured"
                    stamp["capacity_source"] = str(
                        probe_res.get("detection_source") or "capacity-probe")
                else:
                    # PARKED/UNDETERMINED for the routed provider, a probe
                    # about a genuinely DIFFERENT provider, or an identity
                    # neither side could resolve -- labelled, and never as if
                    # the three were the same thing.
                    #
                    # U1: an UNBOUNDED reading lands here too when it cannot be
                    # ATTRIBUTED to this route (providers_match False). That is
                    # deliberate and it is a tightening: before U1 an unbounded
                    # probe about somebody else's provider was labelled
                    # "unbounded-byok" for this route, which was already a
                    # mis-attribution and would now hand out the mode ceiling on
                    # the strength of it.
                    stamp["capacity_status"] = (
                        "provider-unresolved" if provider_unresolved
                        else "probe-not-measured")
                    stamp["capacity_source"] = (
                        f"{probe_res.get('status')}"
                        f"/{probe_provider or 'none'}"
                        f"->{probe_canon or 'unresolved'}"
                        f" vs {routed_canon or 'unresolved'}")
                    _refuse_unmeasured_width(
                        stamp, run_dir=run_dir, phase_id=phase_id,
                        provider=(routed_canon or routed_provider),
                        missing=(f"a capacity reading attributable to "
                                 f"{routed_provider or 'the routed provider'}"),
                        detail=(f"capacity.probe() answered "
                                f"status={probe_res.get('status')!r} "
                                f"available={available!r} about "
                                f"{probe_provider or 'no provider'!r} "
                                f"(canonical {probe_canon!r}); this phase routes "
                                f"to {routed_provider!r} (canonical "
                                f"{routed_canon!r})."))
            except Exception as cap_exc:  # noqa: BLE001 -- probe is best-effort
                stamp["capacity_status"] = "probe-error"
                stamp["capacity_source"] = type(cap_exc).__name__
                _refuse_unmeasured_width(
                    stamp, run_dir=run_dir, phase_id=phase_id,
                    provider=routed_provider,
                    missing=(f"any capacity reading at all for "
                             f"{routed_provider or 'the routed provider'}"),
                    detail=(f"the capacity probe raised "
                            f"{type(cap_exc).__name__}: {cap_exc}."))
    except Exception as exc:  # noqa: BLE001 -- stamp failure never breaks P4
        try:
            _append_sidecar(run_dir, phase_id, {
                "status": "routing_stamp_error", "reason": f"{type(exc).__name__}: {exc}"})
        except Exception:  # noqa: BLE001
            pass

    # FIX 11 CEILING -- applied HERE, to the width the wave will actually run
    # at, because routing.measured_capacity IS the P4-PROMPT worker-slot count
    # (parallel_prompt_worker._workers_for honours it verbatim, deliberately
    # NOT re-clamping a measured 2,500 to 8). A CAP, never a floor and never a
    # target: min(what was measured, the mode's ceiling), so a client measured
    # at 3 still runs 3 under Ultra and a client measured at 2,500 runs 100 --
    # the human-ratified operator ceiling, never provider advertising. The
    # decision computed the ceiling already; nothing is re-measured here.
    try:
        cap = _model_router.capped_width(stamp.get("measured_capacity"),
                                         _mode, decision=decision)
        if cap.get("width"):
            stamp["mode_cap"] = cap
            if cap.get("capped"):
                stamp["capacity_status"] = \
                    f"{stamp.get('capacity_status')}+mode-capped"
            stamp["measured_capacity"] = int(cap["width"])
    except Exception as cap_exc:  # noqa: BLE001 -- a ceiling that cannot be
        # computed never widens the wave: the measured width stands, labelled.
        stamp["mode_cap_error"] = f"{type(cap_exc).__name__}: {cap_exc}"
    return stamp


# F6 back-compat: `_prompt_routing_stamp` was the pre-rename name and is what
# tests/test_defect5_routing_stamp_provider_identity.py,
# tests/test_fix11_mode_axis.py and wave_contract.py's docstring name. Keeping
# the alias means the rename is a rename, not a break.
_prompt_routing_stamp = _routing_stamp


def _emit_slide_author_telemetry(run_dir: Path, rows: List[Dict[str, Any]]) -> None:
    """FIX 5-style one-row-per-slide telemetry into
    working/telemetry/stage-timings.jsonl (same row schema Engine._emit_stage_timing
    writes: run_id, phase_id, wave, model_used, event, started_at, ended_at,
    duration_s, status [, error_class]). No Engine instance exists inside the
    dispatcher process, so the dispatcher writes the rows itself, best-effort:
    telemetry NEVER breaks a run."""
    try:
        tdir = run_dir / "working" / "telemetry"
        tdir.mkdir(parents=True, exist_ok=True)
        with (tdir / "stage-timings.jsonl").open("a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
    except OSError as exc:
        print(f"WARN telemetry: could not write slide_author rows: {exc}",
              flush=True)


def _dispatch_prompt_phase_parallel(run_dir: Path, order: Dict[str, Any], *,
                                    dept_root: Path, phase_obj: Optional[Phase],
                                    worker_id: str) -> DispatchResult:
    """FIX 2 parallel path for P4-PROMPT. Returns the same DispatchResult the
    serial loop returns; identical statuses so callers cannot tell them apart
    (that is the point: the flag switches IMPLEMENTATION, not CONTRACT)."""
    phase_id = "P4-PROMPT"
    if _ppw is None:
        reason = ("parallel prompt worker module unavailable -- falling back to "
                  "the serial P4-PROMPT loop")
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0, "status": "error", "reason": reason})
        return _dispatch_prompt_phase(run_dir, order, dept_root=dept_root,
                                      phase_obj=phase_obj, worker_id=worker_id)

    n = _prompt_slide_count(run_dir)
    if n is None:
        reason = ("cannot determine slide count yet -- neither working/copy/"
                  "slides.json nor working/copy/arc_allocation.json (with a "
                  "slots/allocation/slides array) is present/readable")
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0, "status": "error", "reason": reason})
        return DispatchResult(phase_id, "error", 0, [reason])

    owning_role = order.get("owning_role") or (phase_obj.owning_role if phase_obj else "")

    # --- normalize slides from the SAME source the serial loop + verifier use
    slides_payload: List[Dict[str, Any]] = []
    try:
        for rel in ("working/copy/slides.json", "slides.json", "working/slides.json"):
            p = run_dir / rel
            if not p.is_file():
                continue
            obj = json.loads(p.read_text(encoding="utf-8"))
            raw_slides = obj if isinstance(obj, list) else (
                obj.get("slides") if isinstance(obj, dict) else None)
            if isinstance(raw_slides, list) and raw_slides:
                for s in raw_slides:
                    if not isinstance(s, dict):
                        continue
                    ordinal = s.get("slide")
                    if not isinstance(ordinal, int):
                        continue
                    slides_payload.append({
                        "slide_id": f"slide-{ordinal:02d}",
                        "ordinal": ordinal,
                        "copy": [str(c) for c in (s.get("copy") or [])
                                 if isinstance(c, str)],
                        "archetype": str(s.get("archetype") or ""),
                        "research_anchors": [str(a) for a in
                                             (s.get("research_anchors") or [])],
                        "design_tokens": s.get("design_tokens") or {},
                        "negative_requirements": [str(ngr) for ngr in
                                                  (s.get("negative_requirements")
                                                   or [])],
                    })
                break
    except (OSError, json.JSONDecodeError):
        slides_payload = []
    if not slides_payload:
        reason = ("P4-PROMPT parallel dispatch could not normalize any slide "
                  "payloads from slides.json/arc_allocation.json")
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0, "status": "error", "reason": reason})
        return DispatchResult(phase_id, "error", 0, [reason])
    slides_payload = [s for s in slides_payload if 1 <= s["ordinal"] <= n]
    if not slides_payload:
        reason = "P4-PROMPT parallel dispatch: no in-range ordinals after normalization"
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0, "status": "error", "reason": reason})
        return DispatchResult(phase_id, "error", 0, [reason])

    # --- build prompt-wave-input.json (schema_version 1) stamped routing
    # FIX 104: built through the ONE WaveContract (stamp -> wave_input ->
    # validate), no longer a hand-built dict that could drift from the
    # worker's validate_input. The contract validates BEFORE the file is
    # written or the worker is invoked -- a bad contract fails here, named.
    routing = _routing_stamp(run_dir=run_dir, phase_id=phase_id)
    if _wave_contract is not None:
        contract = _wave_contract.WaveContract(
            run_id=run_dir.name,
            run_dir=str(run_dir),
            # F42 (SMOKE-1, 2026-09-01): the manifest's owning_role MUST ride
            # the wave input. Without it the worker falls back to its
            # hardcoded default ("Presentation Manager (Deck Author)") whose
            # role-SOP lookup cannot resolve against the flat role-library
            # layout -- RoleSOPNotFound on slide-01 every wave.
            owning_role=owning_role,
            routing=_wave_contract.RoutingStamp(
                provider=str(routing.get("provider", "deepseek-direct")),
                model=str(routing.get("model", DEEPSEEK_MODEL)),
                router=str(routing.get("router", "disabled")),
                mode=str(routing.get("mode", "standard")),
                measured_capacity=int(routing.get("measured_capacity")
                                      or DEFAULT_MAX_WORKERS),
                extra={k: v for k, v in routing.items()
                       if k not in ("provider", "model", "router", "mode",
                                    "measured_capacity")},
            ),
            slides=slides_payload,
            prompt_constraints=_wave_contract.PromptConstraints(
                min_chars=9000, max_chars=18000,
                required_blocks=("[ARCHETYPE", "DO-NOT BLOCK", "Do not ")),
        )
        try:
            wave_input = contract.validate()
        except _wave_contract.WaveContractError as exc:
            reason = f"WaveContract rejected the P4-PROMPT wave input: {exc}"
            _append_sidecar(run_dir, phase_id, {
                "worker": worker_id, "attempt": 0, "status": "error",
                "reason": reason})
            return DispatchResult(phase_id, "error", 0, [reason])
        input_path = contract.write(run_dir)
    else:
        # Pre-FIX-104 rollback: the inline dict build, byte-identical shape.
        wave_input = {
            "schema_version": 1,
            "run_id": run_dir.name,
            "run_dir": str(run_dir),
            "phase_id": phase_id,
            "owning_role": owning_role,
            "routing": routing,
            "prompt_constraints": {
                "min_chars": 9000,
                "max_chars": 18000,
                "required_blocks": ["[ARCHETYPE", "DO-NOT BLOCK", "Do not "],
            },
            "slides": slides_payload,
        }
        input_path = run_dir / "working" / "checkpoints" / "prompt-wave-input.json"
        input_path.parent.mkdir(parents=True, exist_ok=True)
        input_path.write_text(
            json.dumps(wave_input, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")

    # --- invoke the worker ONCE. An unhandled WorkerUsageError (exit-2 class:
    # bad input/paths/schema) is a dispatcher bug, so it surfaces as a phase
    # error -- never silently falls back to the serial loop and re-spends.
    started_iso = utcnow()
    started_t = time.monotonic()
    _append_sidecar(run_dir, phase_id, {
        "worker": worker_id, "attempt": 1, "status": "parallel_wave_started",
        "input": str(input_path), "slides": len(slides_payload),
        "routing": routing,
    })
    try:
        exit_code, result_doc = _ppw.run_worker(wave_input)
    except _ppw.WorkerUsageError as exc:
        # FIX 15 (QC.md FIX 15 proof): a forced WorkerUsageError must not fail
        # the phase -- the serial loop is the documented fallback. Log the
        # rejection, then complete the phase through
        # _dispatch_prompt_phase_serial (which owns no wave input, so it
        # cannot re-trigger the usage error).
        reason = f"parallel prompt worker rejected the wave input: {exc}"
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0, "status": "serial_fallback",
            "reason": reason,
            "note": "WorkerUsageError -> _dispatch_prompt_phase_serial (FIX 15)"})
        return _dispatch_prompt_phase_serial(
            run_dir, order, dept_root=dept_root, phase_obj=phase_obj,
            worker_id=worker_id)
    except Exception as exc:  # noqa: BLE001 -- phase must fail loudly, named
        reason = f"parallel prompt worker crashed: {type(exc).__name__}: {exc}"
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0, "status": "error", "reason": reason})
        return _dispatch_prompt_phase(run_dir, order, dept_root=dept_root,
                                      phase_obj=phase_obj, worker_id=worker_id)
    duration_total = round(time.monotonic() - started_t, 3)

    # --- ingest the result file + emit FIX 5-style per-slide telemetry rows
    result_path = run_dir / "working" / "checkpoints" / "prompt-worker-results.json"
    try:
        doc = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        doc = result_doc  # in-memory copy is authoritative if the file vanished
    slide_rows = doc.get("slides") or []
    telemetry_rows = []
    for row in slide_rows:
        telemetry_rows.append({
            "run_id": run_dir.name,
            "phase_id": phase_id,
            "wave": doc.get("wave_count", 1),
            "model_used": row.get("model_used") or routing["model"],
            "event": "slide_author",
            "started_at": row.get("started_at") or started_iso,
            "ended_at": row.get("ended_at") or utcnow(),
            "duration_s": row.get("duration_s"),
            "status": row.get("status"),
            "error_class": row.get("error_class"),
        })
    _emit_slide_author_telemetry(run_dir, telemetry_rows)
    _append_sidecar(run_dir, phase_id, {
        "worker": worker_id, "attempt": 1,
        "status": "parallel_wave_finished", "worker_exit_code": exit_code,
        "succeeded": doc.get("succeeded_count"), "failed": doc.get("failed_count"),
        "wave_count": doc.get("wave_count"), "duration_s": duration_total,
        "seam": doc.get("provider_seam"),
    })

    # --- advance only when EVERY required ordinal succeeded with an on-disk
    # SHA match AND a passing verify verdict.
    succeeded: Dict[int, Dict[str, Any]] = {}
    failed_reasons: List[str] = []
    for row in slide_rows:
        try:
            ordinal = int(row["ordinal"])
        except (TypeError, ValueError):
            continue
        if row.get("status") == "succeeded":
            succeeded[ordinal] = row
        else:
            failed_reasons.append(
                f"slide {ordinal}: {row.get('error_class') or 'failed'} -- "
                f"{row.get('error_message') or 'no error detail'}")
    sha_mismatches: List[str] = []
    verify_failures: List[str] = []
    for ordinal, row in sorted(succeeded.items()):
        # FIX 15: canonical name is slide-NN.txt (worker now writes it too);
        # legacy slide-NN-prompt.txt stays as a read-back candidate so older
        # banked waves still pass the SHA gate.
        target = run_dir / "working" / "prompts" / f"slide-{ordinal:02d}.txt"
        candidates = [target,
                      run_dir / "working" / "prompts" / f"slide-{ordinal:02d}-prompt.txt"]
        disk = next((c for c in candidates if c.is_file()), None)
        if disk is None:
            sha_mismatches.append(f"slide {ordinal}: no prompt file on disk")
            continue
        actual = _ppw._sha256_file(disk)
        if row.get("prompt_sha256") and actual != row["prompt_sha256"]:
            sha_mismatches.append(f"slide {ordinal}: sha256 mismatch on {disk.name}")
            continue
        v_ok, v_reasons = _verify_single_prompt(run_dir, ordinal)
        if not v_ok:
            verify_failures.append(f"slide {ordinal}: {'; '.join(v_reasons)[:200]}")

    if not failed_reasons and not sha_mismatches and not verify_failures \
            and all(o in succeeded for o in range(1, n + 1)):
        ok, reasons = _verify(phase_id, run_dir)
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 1,
            "status": "verified" if ok else "failed", "verifier_ok": ok,
            "verifier_reasons": reasons,
            "parallel": True,
        })
        if ok:
            return DispatchResult(phase_id, "ok", len(slide_rows), [],
                                  "working/prompts/",
                                  slide_results=[
                                      {"slide_id": f"slide-{o:02d}",
                                       "ordinal": o, "status": "succeeded",
                                       "error": None,
                                       "prompt_sha256": succeeded[o].get("prompt_sha256")}
                                      for o in sorted(succeeded)])
        return DispatchResult(phase_id, "exhausted", len(slide_rows), reasons,
                              "working/prompts/",
                              slide_results=[
                                  {"slide_id": f"slide-{o:02d}", "ordinal": o,
                                   "status": "succeeded", "error": None}
                                  for o in sorted(succeeded)])

    # partial / failed: name every unmet ordinal, phase fails AFTER all slides
    final_reasons = list(failed_reasons) + [f"sha: {m}" for m in sha_mismatches] + \
        [f"verify: {v}" for v in verify_failures]
    for o in range(1, n + 1):
        if o not in succeeded:
            if not any(r.startswith(f"slide {o}:") for r in final_reasons):
                final_reasons.append(f"slide {o}: not succeeded in result document")
    failed_slides = [f"slide-{o:02d}" for o in range(1, n + 1) if o not in succeeded]
    succeeded_slides = [f"slide-{o:02d}" for o in sorted(succeeded)]
    _append_sidecar(run_dir, phase_id, {
        "worker": worker_id, "attempt": 1, "status": "phase_exhausted",
        "failed_slides": failed_slides, "succeeded_slides": succeeded_slides,
        "parallel": True,
        "note": "parallel wave finished with unresolved slides; phase fails "
                "only after every slide's outcome is recorded",
    })
    return DispatchResult(phase_id, "exhausted", len(slide_rows), final_reasons,
                          "working/prompts/",
                          slide_results=[
                              {"slide_id": f"slide-{o:02d}", "ordinal": o,
                               "status": "succeeded" if o in succeeded else "failed",
                               "error": None if o in succeeded else "parallel wave failed"}
                              for o in range(1, n + 1)])


# ---------------------------------------------------------------------------
# FIX 19 -- P-0.5-RESEARCH gets real web access.
#
# ROOT CAUSE (Codex-confirmed; fix-spec FIX 19): the research phase was a no-web
# DeepSeek call TOLD to emit research_complete:true + 8 URLs. Nothing was ever
# retrieved -- the brief invented plausible-looking hbr.org/mckinsey.com sources
# that never resolve, and the engine's gates counted URL strings.
#
# The contract now:
#   1. BRAVE-primary search gating BRAVE_SEARCH_API_KEY. Key absence / auth
#      failure / exhausted quota PARKS the phase with a configuration error.
#      Never falls back to a no-web model claiming research.
#   2. Retrieval is bounded: 12 unique fetched URLs per deck max, ONE network
#      fetch per canonical URL (repeated citations reuse the cached response),
#      public http(s) only, redirects <= 2, body <= 2 MB, timeout 15 s. The
#      13th unique URL is refused WITHOUT a fetch.
#   3. Every fetched source lands in working/research/retrieval_ledger.jsonl
#      (query, canonical URL, retrieval time, HTTP status, content hash,
#      extraction length, citation anchors -- never the key, never full text).
#      FIX 20 consumes this ledger.
#   4. The synthesis prompt embeds ONLY actually-retrieved source material
#      beside the usual SOP/contract, and the artifact contract now requires
#      sources drawn from the retrieval ledger -- a brief URL not present in
#      the ledger cannot be produced from fabrication.
#   5. PRESENTATION_RESEARCH_WEB_FETCH=0 (operator kill-switch) parks the
#      phase -- it never restores the old no-web path.
#
# The synthesis model transport resolves through dispatch_complete (FIX 7), so
# the profile still owns WHICH long-context model writes the brief.
# ---------------------------------------------------------------------------
def _intake_topic(run_dir: Path) -> str:
    """The deck topic from the intake artifact. Reads only; never invents."""
    for rel in ("working/copy/intake.json",
                "working/interview/intake_transcript.json"):
        p = run_dir / rel
        if not p.is_file():
            continue
        try:
            obj = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            continue
        for key in ("topic", "deck_topic", "presentation_topic", "subject"):
            val = obj.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return ""


def _research_source_context(result: Dict[str, Any], limit: int = 1600) -> str:
    """One ledger-cited source block for the synthesis prompt: canonical URL,
    title, and the page's own extracted text (truncated) -- the material the
    brief may cite."""
    row = result.get("row") or {}
    url = str(row.get("canonical_url") or result.get("url") or "")
    title = str(result.get("title") or "")
    body = str(row.get("extracted") or "")[:limit]
    return (f"### SOURCE {url}\nTITLE: {title}\n"
            f"EXTRACTED PAGE TEXT:\n{body}\n")


def _dispatch_research_phase(run_dir: Path, order: Dict[str, Any], *,
                             dept_root: Path, phase_obj: Optional[Phase],
                             worker_id: str) -> DispatchResult:
    """P-0.5-RESEARCH: Brave-primary retrieval + routed long-context synthesis.

    Returns statuses shared with the generic loop: ok / exhausted / error.
    RoutingUnavailable and ResearchWebError both PARK the phase (statuses
    error/exhausted with the real, operator-actionable reason) -- the phase
    never silently degrades to a no-web dispatch that would fabricate sources.
    """
    phase_id = "P-0.5-RESEARCH"
    owning_role = order.get("owning_role") or (phase_obj.owning_role if phase_obj else "")

    if _research_web is None:
        reason = ("presentation_job.research_web unavailable -- P-0.5-RESEARCH "
                  "parks: research requires real retrieved sources, and the "
                  "no-web fallback this module replaced may never return.")
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0, "status": "parked",
            "reason": reason})
        return DispatchResult(phase_id, "error", 0, [reason])

    topic = _intake_topic(run_dir)

    # ---- retrieval (Brave-primary, bounded, ledgered) ---------------------
    retrieval_started = time.time()
    retrieval: Optional[Dict[str, Any]] = None
    try:
        retrieval = _research_web.run_research_retrieval(run_dir, topic=topic)
    except _research_web.ResearchWebError as exc:
        reason = f"ResearchWebError: {exc}"
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0, "status": "parked",
            "reason": reason, "topic": topic})
        return DispatchResult(phase_id, "error", 0, [reason])
    except Exception as exc:  # noqa: BLE001 -- retrieval faults park, never crash
        reason = f"retrieval failed: {type(exc).__name__}: {exc}"
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0, "status": "parked",
            "reason": reason})
        return DispatchResult(phase_id, "error", 0, [reason])
    fetcher = retrieval["fetcher"]

    # Usable sources: fetched OK (HTTP 200) with substance to quote.
    usable: List[Dict[str, Any]] = []
    for src in retrieval["sources"]:
        canon = _research_web.canonical_url(src["url"])
        row = fetcher.cache.get(canon) or {}
        if row.get("status") == 200 and len(row.get("extracted") or "") >= \
                _research_web.MIN_EXTRACT_CHARS:
            usable.append({**src, "row": row})

    if not usable:
        reason = ("no usable retrieved sources (every candidate was refused, "
                  "non-200, or under the extraction floor) -- P-0.5-RESEARCH "
                  "parks: a brief with zero actually-retrieved sources is the "
                  "fabrication this fix removes")
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0, "status": "parked",
            "reason": reason, "refusals": fetcher.refusals[:6]})
        return DispatchResult(phase_id, "error", 0, [reason])

    sources_ctx = "\n\n".join(_research_source_context(s) for s in usable)
    ok_urls = "\n".join(
        f"- {s['row']['canonical_url']} -- {_research_web.registered_domain(s['row']['canonical_url'])}"
        for s in usable)

    # ---- routed synthesis --------------------------------------------------
    patterns = resolve_target_paths("P-0.5-RESEARCH", order, phase_obj, run_dir)
    target = _first_concrete_path(patterns, run_dir)
    if target is None:
        reason = ("cannot resolve a concrete write target from "
                  f"produces_artifact={patterns!r}")
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0, "status": "error",
            "reason": reason})
        return DispatchResult(phase_id, "error", 0, [reason])

    ok, reasons = _verify("P-0.5-RESEARCH", run_dir)
    prior_reasons: Optional[List[str]] = reasons if reasons else None
    last_reasons: List[str] = reasons

    for attempt in range(1, DISPATCH_RETRY_CAP + 1):
        try:
            system_prompt, user_prompt = compose_prompt(
                phase_id="P-0.5-RESEARCH", owning_role=owning_role,
                dept_root=dept_root, run_dir=run_dir, order=order,
                attempt=attempt, prior_reasons=prior_reasons)
        except RoleSOPNotFound as exc:
            _append_sidecar(run_dir, phase_id, {
                "worker": worker_id, "attempt": attempt, "status": "error",
                "reason": f"RoleSOPNotFound: {exc}"})
            return DispatchResult(phase_id, "error", attempt, [str(exc)])

        # The retrieval bundle rides the user prompt; the source block sits
        # BEFORE the verbatim contract restatement (compose_prompt always
        # terminates the prompt with the contract, so recency ordering holds).
        user_prompt = (
            "=== RETRIEVED SOURCES (the ONLY citable material for this brief -- "
            "cite these exact canonical URLs; every citation must come from this "
            "Retrieval Ledger, which the engine recorded by ACTUALLY fetching "
            "each page; inventing any URL outside this list is fabrication and "
            "fails the gate) ===\n"
            + sources_ctx +
            "\n=== USABLE SOURCE URLS (canonical, with registered domains) ===\n"
            + ok_urls + "\n\n" + user_prompt
        )

        route_dict: Dict[str, Any] = {}
        try:
            content, usage, route_dict = dispatch_complete(
                system_prompt, user_prompt, phase_id="P-0.5-RESEARCH",
                run_dir=run_dir)
        except RoutingUnavailable as exc:
            reason = f"RoutingUnavailable: {exc}"
            _append_sidecar(run_dir, phase_id, {
                "worker": worker_id, "attempt": attempt,
                "status": "routing_unavailable", "reason": reason})
            return DispatchResult(phase_id, "error", attempt, [reason])
        except DeepSeekCallError as exc:
            last_reasons = [f"Model call failed: {exc}"]
            _append_sidecar(run_dir, phase_id, {
                "worker": worker_id, "attempt": attempt,
                "status": "call_failed", "reason": str(exc)})
            if attempt < DISPATCH_RETRY_CAP:
                time.sleep(min(30, 5 * attempt))
                continue
            break

        payload = _clean_payload(content)
        if not payload.strip():
            _append_sidecar(run_dir, phase_id, {
                "worker": worker_id, "attempt": attempt,
                "status": "empty_completion", "usage": usage})
            last_reasons = ["completion returned empty"]
            if attempt < DISPATCH_RETRY_CAP:
                continue
            break
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target.with_suffix(target.suffix + f".partial-{os.getpid()}-{attempt}")
        tmp_path.write_text(payload, encoding="utf-8")
        os.replace(tmp_path, target)

        verifier_ok, verifier_reasons = _verify("P-0.5-RESEARCH", run_dir)
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": attempt,
            "status": "verified" if verifier_ok else "failed",
            "verifier_ok": verifier_ok, "verifier_reasons": verifier_reasons,
            "model": route_dict.get("model") or DEEPSEEK_MODEL,
            "provider": route_dict.get("provider") or "deepseek-direct",
            "target": str(target.relative_to(run_dir)), "usage": usage,
            "retrieved_sources": len(usable),
            "network_fetches": retrieval.get("network_fetches", 0),
        })
        if verifier_ok:
            # PRES-042: stamp the AUTHOR execution on the verified artifact.
            _stamp_author(run_dir, phase_id, target,
                          model=route_dict.get("model") or DEEPSEEK_MODEL,
                          provider=route_dict.get("provider") or "deepseek-direct")
            return DispatchResult(phase_id, "ok", attempt, [],
                                  str(target.relative_to(run_dir)))
        last_reasons = verifier_reasons
        prior_reasons = verifier_reasons

    _append_sidecar(run_dir, phase_id, {
        "worker": worker_id, "attempt": DISPATCH_RETRY_CAP, "status": "exhausted",
        "final_reasons": last_reasons})
    return DispatchResult(phase_id, "exhausted", DISPATCH_RETRY_CAP,
                          last_reasons, str(target.relative_to(run_dir)))


def _make_slide_worker(*, run_dir: Path, order: Dict[str, Any], dept_root: Path,
                       worker_id: str, n: int, owning_role: str,
                       phase_id: str) -> "callable":
    """PARALLEL-PIPELINE-SPEC Ticket 4: a fanout.py worker_fn for exactly one
    slide ordinal. The body below is the SAME per-slide logic
    _dispatch_prompt_phase_serial's own loop iteration runs (same compose_prompt
    call, same DeepSeek call, same DISPATCH_RETRY_CAP internal retry loop, same
    atomic os.replace write, same _verify_single_prompt gate, same sidecar
    records) -- extracted so it can be handed to fanout.run_units, with ONE
    deliberate behavioral change from the serial version: on exhaustion this
    returns a UnitResult instead of returning a DispatchResult and stopping
    every other ordinal. Fan-out never fail-fasts (spec S2.4): by the time an
    earlier slide's exhaustion would be noticed, later slides are already in
    flight and already billed, so cancelling them saves nothing and throws
    away completed work."""
    prompts_dir = run_dir / "working" / "prompts"

    def _worker(unit: fanout.Unit) -> fanout.UnitResult:
        ordinal = unit.payload["ordinal"]
        target = prompts_dir / f"slide-{ordinal:02d}.txt"

        slide_order = dict(order)
        slide_order["produces_artifact"] = [f"working/prompts/slide-{ordinal:02d}.txt"]
        slide_order["_prompt_slide_ordinal"] = ordinal
        slide_order["_prompt_slide_total"] = n

        ok0, reasons0 = _verify_single_prompt(run_dir, ordinal)
        prior_reasons: Optional[List[str]] = reasons0 if reasons0 else None
        last_reasons: List[str] = reasons0
        attempts_used = 0

        for attempt in range(1, DISPATCH_RETRY_CAP + 1):
            attempts_used = attempt
            try:
                system_prompt, user_prompt = compose_prompt(
                    phase_id=phase_id, owning_role=owning_role, dept_root=dept_root,
                    run_dir=run_dir, order=slide_order, attempt=attempt,
                    prior_reasons=prior_reasons,
                )
            except RoleSOPNotFound as exc:
                _append_sidecar(run_dir, phase_id, {
                    "worker": worker_id, "attempt": attempt, "slide": ordinal,
                    "status": "error", "reason": f"RoleSOPNotFound: {exc}"})
                return fanout.UnitResult(key=unit.key, status="failed", attempts=attempts_used,
                                         reasons=[f"RoleSOPNotFound: {exc}"])

            user_prompt = (
                f"=== THIS CALL AUTHORS EXACTLY ONE FILE: SLIDE {ordinal} OF {n} ===\n"
                f"Find slide {ordinal}'s block in slides_copy.md above (the line "
                f"reading exactly `SLIDE {ordinal}`) and author ONLY its rich "
                f"image-generation prompt. Output ONLY that one slide's complete "
                f"9,000-18,000-char prompt body -- no slide-number header, no "
                f"preamble, no other slide's content.\n\n" + user_prompt
            )

            try:
                # FIX 16: the fanout worker is a dispatcher call site like any
                # other -- it goes through dispatch_complete (the routed
                # entrypoint), never the raw transport, so the model actually
                # sent is the one the client's profile routed.
                content, usage, route_dict = dispatch_complete(
                    system_prompt, user_prompt, phase_id=phase_id,
                    run_dir=run_dir)
            except RoutingUnavailable as exc:
                # fail-closed: no client-owned route for this phase, park the
                # slide honestly rather than fabricating a model.
                last_reasons = [f"RoutingUnavailable: {exc}"]
                _append_sidecar(run_dir, phase_id, {
                    "worker": worker_id, "attempt": attempt, "slide": ordinal,
                    "status": "routing_unavailable", "reason": str(exc)})
                break
            except DeepSeekCallError as exc:
                last_reasons = [f"Model call failed: {exc}"]
                _append_sidecar(run_dir, phase_id, {
                    "worker": worker_id, "attempt": attempt, "slide": ordinal,
                    "status": "call_failed", "reason": str(exc)})
                if attempt < DISPATCH_RETRY_CAP:
                    time.sleep(min(30, 5 * attempt))
                    continue
                break

            payload = _clean_payload(content)
            if not payload.strip():
                _append_sidecar(run_dir, phase_id, {
                    "worker": worker_id, "attempt": attempt, "slide": ordinal,
                    "status": "empty_completion", "usage": usage})
                last_reasons = ["DeepSeek returned an empty completion"]
                if attempt < DISPATCH_RETRY_CAP:
                    continue
                break

            target.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = target.with_suffix(
                target.suffix + f".partial-{os.getpid()}-{attempt}")
            tmp_path.write_text(payload, encoding="utf-8")
            os.replace(tmp_path, target)

            v_ok, v_reasons = _verify_single_prompt(run_dir, ordinal)
            _append_sidecar(run_dir, phase_id, {
                "worker": worker_id, "attempt": attempt, "slide": ordinal,
                "status": "verified" if v_ok else "failed", "verifier_ok": v_ok,
                "verifier_reasons": v_reasons,
                # FIX 16: stamp the model actually SENT (the routed one), not
                # the module constant.
                "model": route_dict.get("model") or DEEPSEEK_MODEL,
                "provider": route_dict.get("provider") or "deepseek-direct",
                "target": str(target.relative_to(run_dir)), "usage": usage})
            if v_ok:
                # PRES-042: stamp the AUTHOR execution on the verified artifact.
                _stamp_author(run_dir, phase_id, target,
                              model=route_dict.get("model") or DEEPSEEK_MODEL,
                              provider=route_dict.get("provider") or "deepseek-direct")
                return fanout.UnitResult(key=unit.key, status="ok", attempts=attempts_used,
                                         target=str(target.relative_to(run_dir)))
            last_reasons = v_reasons
            prior_reasons = v_reasons

        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": DISPATCH_RETRY_CAP, "slide": ordinal,
            "status": "exhausted", "final_reasons": last_reasons})
        return fanout.UnitResult(key=unit.key, status="failed", attempts=attempts_used,
                                 reasons=[f"slide {ordinal}: {r}" for r in last_reasons])

    return _worker


def _dispatch_prompt_phase_fanout(run_dir: Path, order: Dict[str, Any], *, dept_root: Path,
                                  phase_obj: Optional[Phase], worker_id: str,
                                  ordinals: Optional[List[int]],
                                  phase_workers: int) -> DispatchResult:
    """The fan-out path for P4-PROMPT (Ticket 4). Only reachable when the
    manifest declares `workers > 1` for this phase -- see _dispatch_prompt_phase.

    Partial-failure semantics per spec S2.4: no fail-fast, no cancellation --
    every submitted slide runs to its own conclusion even after others fail.
    The phase-level `_verify()` (the SAME authoritative check the serial path
    and the Engine's own poll loop both use) only runs when every dispatched
    slide came back "ok" -- mirroring the serial path's own behavior of never
    running the whole-phase verify on a call it already knows is incomplete."""
    phase_id = "P4-PROMPT"
    n = _prompt_slide_count(run_dir)
    if n is None:
        reason = ("cannot determine slide count yet -- neither working/copy/"
                  "slides.json nor working/copy/arc_allocation.json (with a "
                  "slots/allocation/slides array) is present/readable")
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0, "status": "error", "reason": reason})
        return DispatchResult(phase_id, "error", 0, [reason])

    is_full_sweep = ordinals is None
    work_ordinals = list(range(1, n + 1)) if is_full_sweep else list(ordinals)
    owning_role = order.get("owning_role") or (phase_obj.owning_role if phase_obj else "")

    # Skip already-good slides BEFORE submitting -- identical short-circuit to
    # the serial loop's own `if ok and target.is_file(): continue`, computed
    # up front so the pool only ever spends on real remaining work (this is
    # also what makes fan-out compose with --resume for free: a re-run after
    # a partial failure only re-submits the ordinals that actually failed).
    prompts_dir = run_dir / "working" / "prompts"
    pending_ordinals: List[int] = []
    results: List[fanout.UnitResult] = []
    for ordinal in work_ordinals:
        target = prompts_dir / f"slide-{ordinal:02d}.txt"
        ok0, _reasons0 = _verify_single_prompt(run_dir, ordinal)
        if ok0 and target.is_file():
            results.append(fanout.UnitResult(
                key=f"slide-{ordinal:02d}", status="ok", attempts=0,
                target=str(target.relative_to(run_dir))))
        else:
            pending_ordinals.append(ordinal)

    effective_workers = phase_workers
    if pending_ordinals:
        units = [fanout.Unit(key=f"slide-{ordinal:02d}", payload={"ordinal": ordinal})
                 for ordinal in pending_ordinals]
        worker_fn = _make_slide_worker(
            run_dir=run_dir, order=order, dept_root=dept_root, worker_id=worker_id,
            n=n, owning_role=owning_role, phase_id=phase_id)

        # F6: the sanitised name lives in ONE place now (fanout.py) so the
        # manifest fan-out path below reads the same override an operator can
        # actually export from a shell.
        env_key = fanout.phase_worker_env_var(phase_id)
        effective_workers = fanout.resolve_effective_workers(
            phase_workers, len(units), env_var=env_key)

        deadline_s: Optional[float] = None
        if phase_obj is not None:
            try:
                deadline_s = float(phase_obj.budget_minutes * 60)
            except Exception:  # noqa: BLE001 -- budget_minutes is best-effort here
                deadline_s = None

        pending_results = fanout.run_units(
            units, worker_fn, workers=effective_workers, run_dir=run_dir,
            phase_id=phase_id, per_unit_timeout_s=SINGLE_ATTEMPT_BUDGET_S,
            retry_cap=1,  # the worker above already owns its own internal retry loop
            deadline_s=deadline_s,
        )
        results.extend(pending_results)

    # Re-sort into ordinal order -- `results` may have skipped-good slides
    # (appended first, above) interleaved with pool results out of ordinal
    # order; downstream sidecar/aggregate reporting reads more cleanly sorted.
    results.sort(key=lambda r: r.key)

    total_attempts = sum(r.attempts for r in results)
    failed = [r for r in results if r.status != "ok"]

    if failed:
        final_reasons: List[str] = []
        for r in failed:
            final_reasons.extend(r.reasons)
        status = "error" if any("RoleSOPNotFound" in r for r in final_reasons) else "exhausted"
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": total_attempts, "status": status,
            "failed_slides": [r.key for r in failed], "reasons": final_reasons,
            "workers": effective_workers,
        })
        return DispatchResult(phase_id, status, total_attempts, final_reasons)

    if not is_full_sweep:
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": total_attempts,
            "status": "subset_ok", "ordinals": work_ordinals, "workers": effective_workers,
            "note": "partial-range fan-out worker finished its subset; whole-phase "
                    "verify() deferred to a full-sweep call",
        })
        return DispatchResult(phase_id, "ok", total_attempts, [],
                              "working/prompts/ (subset)")

    ok, reasons = _verify(phase_id, run_dir)
    _append_sidecar(run_dir, phase_id, {
        "worker": worker_id, "attempt": total_attempts,
        "status": "verified" if ok else "failed", "verifier_ok": ok,
        "verifier_reasons": reasons, "workers": effective_workers,
    })
    if ok:
        return DispatchResult(phase_id, "ok", total_attempts, [], "working/prompts/")
    return DispatchResult(phase_id, "exhausted", total_attempts, reasons)


def dispatch_one(run_dir: Path, phase_id: str, order: Dict[str, Any], *,
                  dept_root: Path, phase_obj: Optional[Phase],
                  worker_id: str) -> DispatchResult:
    owning_role = order.get("owning_role") or (phase_obj.owning_role if phase_obj else "")

    if phase_id in DECLINE_PHASES:
        reason = DECLINE_PHASES[phase_id]
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0, "status": "declined", "reason": reason,
        })
        return DispatchResult(phase_id, "declined", 0, [reason])

    if _phase_already_done(run_dir, phase_id):
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0, "status": "already_done_in_state",
        })
        return DispatchResult(phase_id, "skipped_satisfied", 0, [])

    # P4-PROMPT is a genuine multi-file phase (one prompt file PER SLIDE) -- the
    # generic single-target logic below cannot express that shape at all (see the
    # module comment above _dispatch_prompt_phase for the full root cause). Route
    # it to its own dedicated per-slide loop before the single-target machinery
    # ever runs.
    if phase_id == "P4-PROMPT":
        # FIX 2: PRESENTATION_PROMPT_PARALLEL (default ON) routes to the parallel
        # worker. The flag value "0" selects the untouched serial loop below --
        # the documented rollback path, byte-for-byte identical to pre-FIX-2.
        if _prompt_parallel_enabled():
            return _dispatch_prompt_phase_parallel(
                run_dir, order, dept_root=dept_root, phase_obj=phase_obj,
                worker_id=worker_id)
        return _dispatch_prompt_phase(run_dir, order, dept_root=dept_root,
                                      phase_obj=phase_obj, worker_id=worker_id)

    # FIX 19: P-0.5-RESEARCH owns its own retrieval + synthesis pipeline (Brave
    # primary, bounded fetch, retrieval ledger). The generic loop below speaks
    # only "model, write one file" -- exactly the no-web fabrication this fix
    # removes -- so the phase branches here before that machinery ever runs.
    if phase_id == "P-0.5-RESEARCH":
        return _dispatch_research_phase(
            run_dir, order, dept_root=dept_root, phase_obj=phase_obj,
            worker_id=worker_id)

    # Idempotent pre-check: a prior sweep (or the interview process, or an
    # earlier real run) may have already produced a passing artifact.
    ok, reasons = _verify(phase_id, run_dir)
    patterns = resolve_target_paths(phase_id, order, phase_obj, run_dir)
    target = _first_concrete_path(patterns, run_dir)
    # ROOT CAUSE (live run pj_34a56a26caca04532ec6e9cba6, 2026-08-18, iteration 3):
    # verify()==True does NOT mean THIS phase's own produces_artifact file exists --
    # for a QC/audit phase whose phase_verifiers mapping re-runs an UPSTREAM check
    # (P1Q-COPY-QC maps to the exact same _verify_copy() P4-COPY already passed,
    # which only ever reads working/copy/slides_copy.md and never looks at
    # working/qc/copy_qc_report.json at all), verify() can be True forever while the
    # phase's own artifact is never written. Before this fix, `ok` alone was treated
    # as "already satisfied" and dispatch_one returned WITHOUT writing anything. But
    # the Engine's separate poll loop (phases.py._run_agent_phase) gates PURELY on
    # _artifacts_present(phase) -- literal file existence at produces_artifact -- and
    # never calls the substance verifier in that loop. Confirmed live: P1Q-COPY-QC's
    # watcher logged "already_satisfied" every ~10s for 2+ minutes while
    # working/qc/copy_qc_report.json never existed -- a permanent deadlock that would
    # have run out the full budget_minutes and hard-blocked a phase that was, by its
    # own substance check, already fine. FIX: "already satisfied" now requires BOTH
    # verify()==True AND the resolved target artifact already existing on disk --
    # exactly what the Engine itself checks. When verify() passes but the target file
    # is still missing, fall through to a REAL dispatch so the phase's own artifact
    # actually gets written (cheap: the model already has the passing upstream
    # content in its context). Zero behavior change for every phase seen so far
    # (P4-COPY, P-SP-STRUCTURE, the intake phases, ...) where produces_artifact IS
    # the exact file the verifier reads -- once written it stays on disk, so
    # target_exists is True from the next check onward, same as before.
    target_exists = bool(target is not None and target.exists())
    if ok and target_exists:
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0, "status": "already_satisfied",
        })
        return DispatchResult(phase_id, "skipped_satisfied", 0, [])

    if target is None:
        reason = f"cannot resolve a concrete write target from produces_artifact={patterns!r}"
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0, "status": "error", "reason": reason,
        })
        return DispatchResult(phase_id, "error", 0, [reason])

    # FIX 15b: the manifest's `fanout` field turns this whole phase into N
    # independent units -- one per slide/section/file -- run through
    # fanout.run_units with per-unit ledger rows, instead of one serial call
    # authoring one file. Phases without the field keep the single-target
    # loop below untouched.
    fanout_spec = _phase_fanout_spec(phase_id, run_dir)
    if fanout_spec is not None:
        return _dispatch_phase_fanout_units(
            run_dir, order, dept_root=dept_root, phase_obj=phase_obj,
            worker_id=worker_id, spec=fanout_spec, patterns=patterns,
            target=target, prior_reasons=reasons if reasons else None)

    last_reasons: List[str] = reasons
    # FIX 69 (proof run 2026-09-02): `prior_reasons` is only rebound AFTER a
    # failed verifier pass (below), so attempt 1 of every dispatch crashed with
    # UnboundLocalError("cannot access local variable 'prior_reasons'") — the
    # same live failure the wave-1 proof hit on P-SP-P3-HYGIENE. Seed it from
    # the sweep's own upstream reasons; empty reasons means None (compose_prompt
    # treats a falsy prior_reasons as "no prior findings"), exactly the shape
    # the fanout branch above already passes.
    prior_reasons: Optional[List[str]] = reasons if reasons else None

    for attempt in range(1, DISPATCH_RETRY_CAP + 1):
        try:
            system_prompt, user_prompt = compose_prompt(
                phase_id=phase_id, owning_role=owning_role, dept_root=dept_root,
                run_dir=run_dir, order=order, attempt=attempt, prior_reasons=prior_reasons,
            )
        except RoleSOPNotFound as exc:
            _append_sidecar(run_dir, phase_id, {
                "worker": worker_id, "attempt": attempt, "status": "error",
                "reason": f"RoleSOPNotFound: {exc}",
            })
            return DispatchResult(phase_id, "error", attempt, [str(exc)])

        # FIX 7: routed completion (profile-selected transport; DeepSeek
        # remains the default when the profile has no eligible owner yet).
        route_dict2: Dict[str, Any] = {}
        try:
            content, usage, route_dict2 = dispatch_complete(
                system_prompt, user_prompt, phase_id=phase_id, run_dir=run_dir,
                # F10: a heal rung's provider pin, if this order carries one.
                # Ignored unless the router already lists it as eligible --
                # see _apply_route_override.
                route_override=(order.get("route_override")
                                if isinstance(order, dict) else None))
        except RoutingUnavailable as exc:
            reason = f"RoutingUnavailable: {exc}"
            _append_sidecar(run_dir, phase_id, {
                "worker": worker_id, "attempt": attempt, "status": "routing_unavailable",
                "reason": reason,
            })
            return DispatchResult(phase_id, "error", attempt, [reason])
        except DeepSeekCallError as exc:
            last_reasons = [f"Model call failed: {exc}"]
            _append_sidecar(run_dir, phase_id, {
                "worker": worker_id, "attempt": attempt, "status": "call_failed",
                "reason": str(exc),
            })
            if attempt < DISPATCH_RETRY_CAP:
                time.sleep(min(30, 5 * attempt))
                continue
            break

        payload = _clean_payload(content)
        if not payload.strip():
            # Never write an empty/whitespace-only file: it would still satisfy the
            # Engine's own glob-only _artifacts_present existence check (phases.py)
            # and could race its 15s poll into a real BLOCKED park on empty content
            # before this loop's next attempt ever runs. Treat exactly like a failed
            # call and retry -- this is what happened once during development
            # (reasoning_effort=max consumed the entire max_tokens budget, leaving a
            # zero-length content field) before DEEPSEEK_MAX_OUTPUT_TOKENS was raised;
            # this guard makes the failure mode safe even if it recurs.
            _append_sidecar(run_dir, phase_id, {
                "worker": worker_id, "attempt": attempt, "status": "empty_completion",
                "usage": usage,
            })
            last_reasons = ["DeepSeek returned an empty completion (thinking budget "
                            "likely consumed the whole max_tokens; not written to disk)"]
            if attempt < DISPATCH_RETRY_CAP:
                continue
            break
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target.with_suffix(target.suffix + f".partial-{os.getpid()}-{attempt}")
        tmp_path.write_text(payload, encoding="utf-8")
        # PRES-018 fencing at publication (same contract as the fanout
        # aggregate above): a single-target artifact is published only while
        # the claim file still names THIS worker. A worker whose claim was
        # stolen mid-call must not overwrite the new owner's output -- the
        # stale write is quarantined and the attempt reports lost, never a
        # pretended win. No claim file at all = no fencing context (operator
        # --once dispatches and tests): publication proceeds.
        _pub_claim_file = _claim_path(run_dir, phase_id)
        if _pub_claim_file.exists():
            _pub_rec = _read_claim_record(_pub_claim_file) or {}
            if _pub_rec.get("worker") != worker_id or \
                    _pub_rec.get("owner_token") != _current_claim_token(run_dir, phase_id, worker_id):
                quarantine = target.with_name(
                    target.name + f".stale-quarantine-{worker_id}")
                try:
                    tmp_path.replace(quarantine)
                except OSError:
                    tmp_path.unlink(missing_ok=True)
                _append_sidecar(run_dir, phase_id, {
                    "worker": worker_id, "attempt": attempt,
                    "status": "stale_quarantined",
                    "reason": ("claim lost before publication -- single-target "
                               f"output quarantined to {quarantine.name}, not published"),
                })
                return DispatchResult(
                    phase_id, "exhausted", attempt,
                    ["claim lost before publication; output quarantined"])
        os.replace(tmp_path, target)  # atomic on POSIX, same filesystem -- no torn read

        verifier_ok, verifier_reasons = _verify(phase_id, run_dir)
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": attempt, "status": "verified" if verifier_ok else "failed",
            "verifier_ok": verifier_ok, "verifier_reasons": verifier_reasons,
            "model": route_dict2.get("model") or DEEPSEEK_MODEL,
            "provider": route_dict2.get("provider") or "deepseek-direct",
            "target": str(target.relative_to(run_dir)),
            "usage": usage,
        })
        if verifier_ok:
            # PRES-042: stamp the AUTHOR execution on the verified artifact.
            # For a QC phase the produced artifact IS the review record: the
            # same stamp doubles as the REVIEWER execution stamp (separate
            # execution identity, actual model/provider, the reviewed
            # artifact's sha via the QC report's own consumes, rubric
            # version) — identity from the dispatch record, never the
            # report's graded_by prose.
            _stamp_author(run_dir, phase_id, target,
                          model=route_dict2.get("model") or DEEPSEEK_MODEL,
                          provider=route_dict2.get("provider") or "deepseek-direct")
            if _estamp.stamps_enabled() and _is_qc_phase(owning_role, phase_id):
                try:
                    _stamp_qc_reviewer(run_dir, phase_id, target,
                                       model=route_dict2.get("model") or DEEPSEEK_MODEL,
                                       provider=route_dict2.get("provider") or "deepseek-direct")
                except Exception as exc:  # noqa: BLE001 — best-effort, never blocks
                    try:
                        _append_sidecar(run_dir, phase_id, {
                            "worker": "stamp", "attempt": 0, "status": "qc_stamp_failed",
                            "reason": f"reviewer stamp failed: {exc!r}",
                        })
                    except Exception:
                        pass
            return DispatchResult(phase_id, "ok", attempt, [], str(target.relative_to(run_dir)))

        last_reasons = verifier_reasons
        prior_reasons = verifier_reasons

    _append_sidecar(run_dir, phase_id, {
        "worker": worker_id, "attempt": DISPATCH_RETRY_CAP, "status": "exhausted",
        "final_reasons": last_reasons,
    })
    return DispatchResult(phase_id, "exhausted", DISPATCH_RETRY_CAP, last_reasons,
                          str(target.relative_to(run_dir)))




# ---------------------------------------------------------------------------
# FIX 112 — the missing FIX-15b generic fan-out dispatch glue.
#
# dispatch_one() below has branched on `_phase_fanout_spec()` /
# `_dispatch_phase_fanout_units()` since FIX 15b, but the two callables were
# never defined in any shipped module: the moment a manifest phase declares a
# `fanout` field (this fix does exactly that for P-STYLE-SPEC — "a fanout unit
# in the copy stage authors the style-preview spec from the design direction"),
# the generic dispatch path died with `NameError: name '_phase_fanout_spec' is
# not defined` AFTER the target had already been resolved — a latent crash,
# proven live against a synthetic manifest before this fix (the serial path
# never hit it only because no shipped manifest phase declared `fanout`).
#
# The contract here mirrors fanout.py's own three seams (PARALLEL-PIPELINE-SPEC
# S2): parse the manifest's {"by", "max_units"} field via fanout.parse_fanout_field
# (malformed -> FanoutSpecError -> phase error, never a silent serial fallback),
# enumerate the deterministic unit list via fanout.enumerate_fanout_items, run
# the pool through fanout.run_units (per-unit ledger rows, partial failure
# without cancellation), then aggregate every authored unit into the phase's
# single produces_artifact target and re-run the SAME whole-phase verifier the
# engine will run. A unit that returns nothing aggregates to nothing: if no
# unit produced text the phase reports exhausted — never a fabricated file.
# ---------------------------------------------------------------------------
def _phase_fanout_spec(phase_id: str, run_dir: Path) -> Optional["fanout.FanoutSpec"]:
    """Read THIS run's resolved manifest and return the phase's FanoutSpec,
    or None when the phase declares no fanout field (the serial path below
    stays byte-for-byte untouched). The manifest is re-resolved through the
    same load_manifest_for_run() every sweep already uses — never a second,
    drifting manifest source."""
    manifest = load_manifest_for_run(run_dir)
    if manifest is None:
        return None
    try:
        phase_obj = manifest.phase_or_none(phase_id) if hasattr(manifest, "phase_or_none") \
            else next((p for p in manifest.phases if p.id == phase_id), None)
    except Exception:  # noqa: BLE001 — an unresolvable phase has no fanout spec
        return None
    if phase_obj is None:
        return None
    raw = getattr(phase_obj, "fanout", None)
    if raw is None:
        return None
    try:
        return fanout.parse_fanout_field(raw)
    except fanout.FanoutSpecError as exc:
        _append_sidecar(run_dir, phase_id, {
            "worker": "dispatcher", "attempt": 0, "status": "error",
            "reason": f"fanout field malformed: {exc}",
        })
        return None


def _aggregate_fanout_parts(phase_id: str, parts: List[str]) -> Optional[str]:
    """FIX 112: per-phase aggregation of fanout unit outputs into the ONE text
    document the phase's produces_artifact names. Returns None when the parts
    cannot be honestly aggregated (the caller then refuses the write — never a
    broken artifact on disk).

    Default (no per-phase override): 1 part passes through as-is; N JSON-object
    parts shallow-merge into one object; anything else is refused.

    P-STYLE-SPEC override: each unit authored {"id","style_directive",
    "representative_slide"}; the deck-level spec build_deck.run_style_preview_samples
    enforces is {"variants":[exactly 3],"representative_slides":[exactly 3]}.
    The aggregator keeps the first THREE well-formed variant candidates (ids
    forced unique A/B/C in unit order), maps each candidate's own
    representative_slide ordinal, and refuses unless exactly 3 made it."""
    if phase_id != "P-STYLE-SPEC":
        if len(parts) == 1:
            return parts[0]
        if not parts:
            return None
        try:
            docs = [json.loads(p) for p in parts]
        except (json.JSONDecodeError, TypeError):
            return None
        if not all(isinstance(d, dict) for d in docs):
            return None
        merged: Dict[str, Any] = {}
        for d in docs:
            merged.update(d)
        return json.dumps(merged, indent=2, ensure_ascii=False)

    variants: List[Dict[str, Any]] = []
    reps: List[int] = []
    used_ids: set = set()
    fallback_ids = ("A", "B", "C")
    for p in parts:
        if len(variants) >= 3:
            break
        try:
            doc = json.loads(p)
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(doc, dict):
            continue
        directive = str(doc.get("style_directive") or "").strip()
        rep = doc.get("representative_slide")
        if not directive or isinstance(rep, bool) or not isinstance(rep, int):
            continue
        vid = str(doc.get("id") or "").strip().upper()
        if vid not in ("A", "B", "C") or vid in used_ids:
            vid = next((c for c in fallback_ids if c not in used_ids), None)
            if vid is None:
                continue
        used_ids.add(vid)
        variants.append({"id": vid, "style_directive": directive})
        reps.append(int(rep))
    if len(variants) != 3:
        return None
    return json.dumps(
        {"variants": variants, "representative_slides": reps},
        indent=2, ensure_ascii=False)


def _dispatch_phase_fanout_units(
        run_dir: Path, order: Dict[str, Any], *, dept_root: Path,
        phase_obj: Optional[Phase], worker_id: str,
        spec: "fanout.FanoutSpec", patterns: List[str], target: Path,
        prior_reasons: List[str]) -> DispatchResult:
    """Run ONE manifest-declared fan-out phase through fanout.run_units and
    aggregate the units into `target`. Per-unit prompt composition reuses
    compose_prompt() (role SOP context + upstream artifacts, attempt-stamped),
    the model call goes through dispatch_complete() (the same routed
    entrypoint every other phase uses), and the whole-phase verifier runs at
    the end — mirroring the P4-PROMPT parallel loop's partial-failure
    semantics (S2.4): no fail-fast, every submitted unit runs to its own
    conclusion, and the phase-level verify() only runs when every unit came
    back ok."""
    phase_id = phase_obj.id if phase_obj is not None else "P-UNKNOWN-FANOUT"
    owning_role = order.get("owning_role") or (phase_obj.owning_role if phase_obj else "")
    items = fanout.enumerate_fanout_items(
        run_dir, spec, phase_id=phase_id, produces_artifact=patterns)
    if not items:
        reason = ("fanout spec enumerated zero units — refusing both a serial "
                  "fallback and an empty aggregate (S2: no unit is ever invented)")
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0, "status": "error", "reason": reason,
        })
        return DispatchResult(phase_id, "error", 0, [reason])

    # F6 (review 3.8, 2026-09-06) -- THE WIDTH.
    #
    # This used to pass `phase_obj.workers` as the first term of
    # resolve_effective_workers' min(). `Phase.workers` defaults to 1 when the
    # manifest omits it (manifest.py:233) and EIGHT of the nine fan-out phases
    # in the shipped manifest omit it (P4-COPY, P-U-DESIGN-SALES/CHECKOUT/VSL,
    # P-PROMPT-QC, P-STYLE-SPEC, P-IMAGE-QC, P9-SPEECH -- only P4-PROMPT, which
    # never reaches this function, declares workers:12). A cap of 1 is a
    # SERIAL phase: 20-25 language-model calls one after another, twice per
    # deck, in every QC phase. `capacity_available` was never passed either,
    # so the measured ceiling had no say at all.
    #
    # The manifest's `fanout` field IS the opt-in flag -- this function is only
    # reached when _phase_fanout_spec() returned one -- so `workers` is not a
    # cap here. The width now comes from the SAME authority P4-PROMPT's wave
    # uses: _routing_stamp -> (client resource profile -> route -> capacity
    # probe -> mode ceiling) -> measured_capacity, then min'd against the unit
    # count and the per-phase env override. A stamp that cannot resolve a route
    # falls back labelled -- never to 1.
    # U1 (2026-09-07) corrects what that fallback IS: it was DEFAULT_MAX_WORKERS
    # (8), which is exactly the collapse U1 removes. The stamp now hands this
    # function the MODE CEILING for an UNBOUNDED account, the measurement when
    # one is attributable, and capacity.DEFAULT_CONSERVATIVE plus a LOUD
    # AF-CAPACITY-UNMEASURED refusal when neither exists. The
    # `or DEFAULT_MAX_WORKERS` below is now only reachable if a stamp lies about
    # its own shape (a non-int, or a value <1), which _routing_stamp cannot
    # produce -- it is a shape guard, not a capacity answer.
    from presentation_job.fanout import resolve_effective_workers
    routing = _routing_stamp(run_dir=run_dir, phase_id=phase_id)
    try:
        routed_width = int(routing.get("measured_capacity") or DEFAULT_MAX_WORKERS)
    except (TypeError, ValueError):  # a stamp that lied about its own shape
        routed_width = DEFAULT_MAX_WORKERS
    if routed_width < 1:
        routed_width = DEFAULT_MAX_WORKERS
    effective_workers = resolve_effective_workers(
        routed_width, unit_count=len(items),
        env_var=fanout.phase_worker_env_var(phase_id))

    def _unit_worker(unit: "fanout.Unit") -> "fanout.UnitResult":
        try:
            system_prompt, user_prompt = compose_prompt(
                phase_id=phase_id, owning_role=owning_role, dept_root=dept_root,
                run_dir=run_dir, order={**order, "fanout_unit": unit.key},
                attempt=1, prior_reasons=prior_reasons,
            )
            content, usage, route = dispatch_complete(
                system_prompt, user_prompt, phase_id=phase_id, run_dir=run_dir)
        except Exception as exc:  # noqa: BLE001 — a raised unit is a failed unit
            return fanout.UnitResult(key=unit.key, status="failed", attempts=1,
                                     reasons=[f"{type(exc).__name__}: {exc}"])
        text = (content or "").strip()
        if not text:
            return fanout.UnitResult(key=unit.key, status="failed", attempts=1,
                                     reasons=["unit returned empty output"])
        scratch = fanout.unit_output_path(run_dir, phase_id, unit.key)
        scratch.parent.mkdir(parents=True, exist_ok=True)
        tmp = scratch.with_name(scratch.name + ".partial")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(scratch)
        return fanout.UnitResult(
            key=unit.key, status="ok", attempts=1,
            target=str(scratch.relative_to(run_dir)),
            meta={"provider": route.get("provider"), "model": route.get("model"),
                  "request_id": usage.get("request_id") if isinstance(usage, dict) else None},
        )

    deadline_s = (phase_obj.budget_minutes * 60) if phase_obj is not None else None
    results = fanout.run_units(
        [fanout.Unit(key=it["key"], payload=it) for it in items], _unit_worker,
        workers=effective_workers, run_dir=run_dir, phase_id=phase_id,
        per_unit_timeout_s=SINGLE_ATTEMPT_BUDGET_S, retry_cap=1,
        deadline_s=deadline_s)

    failed = [r for r in results if r.status != "ok"]
    for r in results:
        fanout.append_unit_ledger_row(run_dir, phase_id, {
            "unit": r.key, "status": r.status, "attempts": r.attempts,
            "target": r.target, "reasons": r.reasons,
            **({"meta": r.meta} if r.meta else {}),
        })
    if failed:
        reasons = [f"{r.key}: {'; '.join(r.reasons) or 'failed'}" for r in failed]
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": sum(r.attempts for r in results),
            "status": "exhausted", "failed_units": [r.key for r in failed],
            "reasons": reasons,
            "workers": effective_workers, "routed_width": routed_width,
            "capacity_status": routing.get("capacity_status"),
        })
        return DispatchResult(phase_id, "exhausted",
                              sum(r.attempts for r in results), reasons)

    # Aggregate: every ok unit's text is concatenated in unit-key order — the
    # spec authoring contract (P-STYLE-SPEC) is one JSON document, so the
    # units' outputs must be joined as JSON parts, not raw concatenation. The
    # unit contract itself teaches JSON-object output; aggregation validates
    # the JOIN and fails loudly rather than writing an unparsable file.
    parts = []
    for r in results:  # run_units returns INPUT order — merge order (S2.1)
        if r.target:
            scratch = run_dir / r.target
            if scratch.is_file():
                parts.append(scratch.read_text(encoding="utf-8", errors="replace").strip())
    merged_text: Optional[str] = _aggregate_fanout_parts(phase_id, parts)
    if not merged_text:
        reason = ("fanout units produced output that could not be aggregated "
                  "into a single artifact document — refusing to write a broken "
                  "artifact (see per-unit files under working/fanout/)")
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 1, "status": "exhausted",
            "reason": reason,
        })
        return DispatchResult(phase_id, "exhausted", 1, [reason])

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".partial")
    tmp.write_text(merged_text + "\n", encoding="utf-8")
    # PRES-018 fencing at publication: the aggregated artifact is published
    # only while THIS worker's claim still owns the phase. A worker whose
    # claim was stolen (dead holder reclaimed) must not overwrite the NEW
    # owner's output with its own stale result -- the stale aggregate is
    # quarantined (kept, renamed, never published) and the dispatch result
    # says so instead of pretending a win. NO claim file at all means no
    # fencing context (direct dispatch_one callers -- an operator --once,
    # tests): publication proceeds.
    _claim_file = _claim_path(run_dir, phase_id)
    if _claim_file.exists():
        claim_rec = _read_claim_record(_claim_file) or {}
        if claim_rec.get("worker") != worker_id \
                or claim_rec.get("owner_token") != _current_claim_token(run_dir, phase_id, worker_id):
            quarantine = target.with_name(
                target.name + f".stale-quarantine-{worker_id}")
            try:
                tmp.replace(quarantine)
            except OSError:
                tmp.unlink(missing_ok=True)
            _append_sidecar(run_dir, phase_id, {
                "worker": worker_id, "attempt": len(results),
                "status": "stale_quarantined",
                "reason": ("claim lost before publication -- aggregated output "
                           f"quarantined to {quarantine.name}, not published"),
            })
            return DispatchResult(
                phase_id, "exhausted", len(results),
                ["claim lost before publication; output quarantined"])
    tmp.replace(target)

    ok, reasons = _verify(phase_id, run_dir)
    _append_sidecar(run_dir, phase_id, {
        "worker": worker_id, "attempt": len(results),
        "status": "verified" if ok else "failed", "verifier_ok": ok,
        "verifier_reasons": reasons, "units": len(results),
        "workers": effective_workers, "routed_width": routed_width,
        "capacity_status": routing.get("capacity_status"),
    })
    if ok:
        return DispatchResult(phase_id, "ok", len(results), [],
                              str(target.relative_to(run_dir)))
    return DispatchResult(phase_id, "exhausted", len(results), reasons)


# ---------------------------------------------------------------------------
# Claiming (spec S5.6) -- atomic O_CREAT|O_EXCL, no new locking primitive,
# never touches state.json/.job.lock (which is the Engine's own RunLock file
# -- a completely different mechanism this module must never touch).
#
# FIX 105 (Master Part 8): a claim file now carries the claimant's PID and
# boot-relative start time, and a claim whose recorded PID is DEAD is IGNORED
# (never a stall) -- the next dispatcher re-claims the same atomic way without
# any hand removal. Before this fix a dispatcher killed mid-wave (engine kill,
# FIX 19 process-group teardown) left `.claim` files behind whose only cure was
# the age-based heuristic below -- a fresh resume then waited out the FULL
# SINGLE_ATTEMPT_BUDGET_S * CLAIM_STALE_MULTIPLIER window (over 20 minutes)
# per claimed phase before it could proceed. Liveness replaces waiting:
#
#   pid dead                        -> claim is stale NOW, re-claim immediately
#   pid alive                       -> a live dispatcher holds it; age heuristic
#                                      still applies as the only fallback for a
#                                      claim from a process this user cannot
#                                      signal-probe (PermissionError edge).
#   pid missing/unreadable (legacy) -> fall back to the age heuristic exactly.
#
# PRES-018 (2026-09-08): claim OWNERSHIP, not just claim liveness. FIX 105
# fixed the crash case but left two holes the reproduction caught live:
#
#   1. AGE STEAL: a claim owned by a LIVE process became stealable solely
#      because file age exceeded SINGLE_ATTEMPT_BUDGET_S *
#      CLAIM_STALE_MULTIPLIER. A legitimately long model round-trip
#      (thinking MAX at large max_tokens) got reaped mid-flight and a
#      second dispatcher re-ran PAID work concurrently.
#   2. UNCONDITIONAL RELEASE: release_claim() unlinked whichever claim file
#      was there NOW -- an old owner's slow finally could delete a NEW
#      owner's claim; overlapping dispatchers deleted each other's claims.
#
# The claim is now an OWNED LEASE with: owner_token (random -- the only
# release/steal credential), revision + fencing (monotonic per phase, the
# fencing token publication checks before writing artifacts), pid + boot
# identity (pid REUSE never matches the recorded holder), and expiry_at
# (recorded for operators/tooling; the staleness oracle below never
# consults it -- a foreign pid this user cannot signal is treated as
# LIVE, never stolen here).
#
#   live identity-matched holder   -> NEVER stale, not by age, not by expiry
#   dead / pid-reused holder       -> stale NOW (FIX 105 liveness kept)
#   legacy record (no owner token) -> FIX 105 age behaviour exactly
#   release                        -> owner token (or own-pid legacy) match
#                                     required, else the file is NOT ours
# ---------------------------------------------------------------------------
def _claim_path(run_dir: Path, phase_id: str) -> Path:
    return run_dir / "working" / "work-orders" / f"{phase_id}.claim"


def _boot_uptime_s() -> float:
    """Boot-relative uptime seconds (CLOCK_BOOTTIME on Linux; sysctl
    kern.boottime fallback on macOS). Binds a recorded pid to the process
    START that created the claim: a reused pid never matches the recorded
    holder, because its boot-relative start reference differs."""
    try:
        return float(time.clock_gettime(time.CLOCK_BOOTTIME))  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass
    try:
        out = subprocess.run(["sysctl", "-n", "kern.boottime"],
                             capture_output=True, text=True, timeout=5)
        m = re.search(r"sec\s*=\s*(\d+)", out.stdout or "")
        if out.returncode == 0 and m:
            return max(0.0, time.time() - int(m.group(1)))
    except Exception:  # noqa: BLE001 -- identity stamp is best-effort
        pass
    return 0.0


def _claim_owner_identity() -> Dict[str, Any]:
    """THIS process's claim-owner identity: pid + boot-relative start
    reference. Written at claim creation; verified before any steal or
    legacy self-release."""
    return {"pid": os.getpid(), "boot_uptime": _boot_uptime_s()}


def _owner_matches_identity(rec: Dict[str, Any]) -> bool:
    """True iff `rec`'s recorded owner identity is still THE SAME PROCESS:
    alive, same pid, and -- when the record carries it -- a boot-relative
    start reference the current clock has not reset (a reused pid restarts
    near uptime 0; a recorded uptime far above the present one for the same
    pid means the recorded process is gone and a NEW one recycled the
    number)."""
    pid = rec.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return False
    if not _pid_is_alive(pid):
        return False
    rec_boot = rec.get("boot_uptime")
    if isinstance(rec_boot, (int, float)) and rec_boot > 0:
        now_boot = _boot_uptime_s()
        # Tolerance 1s covers read granularity between write and check.
        if now_boot > 0 and now_boot + 1.0 < float(rec_boot):
            return False
    return True


def _read_claim_record(path: Path) -> Optional[Dict[str, Any]]:
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
        return rec if isinstance(rec, dict) else None
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def _next_claim_revision(path: Path) -> int:
    """Claim revision: one more than the file's current fencing value (1
    when absent/legacy). Monotonic across steal cycles of one phase -- the
    fencing token artifact publication checks before accepting output."""
    rec = _read_claim_record(path)
    if not rec:
        return 1
    try:
        return int(rec.get("fencing") or 0) + 1
    except (TypeError, ValueError):
        return 1


def _claim_is_stale(path: Path, age: float) -> Tuple[bool, str]:
    """Claim-staleness oracle. Returns (stale, why).

    PRES-018 precedence, in order:

      1. an OWNERSHIP record (owner_token present) whose process is ALIVE
         and identity-matched is NEVER stale -- not by age, not by expiry.
         A hung live owner requires explicit supervised termination
         (PRES-019's reconciliation), never a silent age steal.
      2. an ownership record whose holder is DEAD or pid-REUSED is stale
         RIGHT NOW (FIX 105's liveness win, now identity-safe).
      3. a legacy record (no owner token) keeps FIX 105 exactly: dead pid
         => stale; else the age heuristic (the caller applies it).

    NOTE: expiry_at is a RECORD, not a reap rule -- this oracle never
    consults it. A FOREIGN pid this user cannot signal (the
    PermissionError edge: _pid_is_alive True) is treated as LIVE and
    never stolen here.
    """
    rec = _read_claim_record(path)
    if rec is None:
        return False, ""       # unreadable shape: age heuristic decides
    owner = rec.get("owner_token")
    if not owner:
        # Legacy FIX 105 record: pid liveness, age fallback.
        pid = rec.get("pid")
        if not isinstance(pid, int) or pid <= 0:
            return False, ""   # legacy claim without a pid: age heuristic
        if pid == os.getpid():
            # Our own (thread-pool sibling's) claim: never stale by
            # liveness; an O_EXCL loss here can only be a race against
            # ourselves -- the age rule decides.
            return False, ""
        if _pid_is_alive(pid):
            return False, ""
        return True, (f"legacy claim pid {pid} is dead (claimed_at "
                      f"{rec.get('claimed_at')!r})")

    # PRES-018 ownership record:
    if _owner_matches_identity(rec):
        return False, ""       # confirmed live holder: NEVER reaped here
    return True, (f"claim owner {str(owner)[:8]}.. pid {rec.get('pid')} is "
                  f"dead or its pid was recycled (claimed_at "
                  f"{rec.get('claimed_at')!r})")


def _unlink_claim_if_token(path: Path, owner_token: str) -> bool:
    """CAS-delete: unlink the claim ONLY if the record on disk still holds
    exactly `owner_token`. The atomic steal primitive: two reapers that both
    judged the same dead claim stale unlink-race safely -- exactly one sees
    its token still present; the loser's unlink is a no-op against the
    winner's freshly created record.

    A record WITHOUT an owner_token is a LEGACY claim (FIX 105 shape): it is
    CAS-matched against the empty token, so a stale legacy claim is still
    stealable -- its liveness is already settled by the oracle above."""
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if not isinstance(rec, dict):
        return False
    rec_token = rec.get("owner_token") or ""
    if rec_token != owner_token:
        return False          # a new owner got there first: NOT ours to delete
    try:
        path.unlink()
        return True
    except OSError:
        return False


def _steal_lock_path(run_dir: Path, phase_id: str) -> Path:
    """The steal window's flock anchor. flock on this file serializes the
    read-stale -> CAS-unlink -> O_EXCL-create sequence so two simultaneous
    reapers produce exactly ONE winner: the unlink->create gap that O_EXCL
    alone cannot close is closed by the advisory lock, held only for the
    microseconds of the steal, never while work runs."""
    return _claim_path(run_dir, phase_id).with_suffix(".claim.steal-lock")


def try_claim(run_dir: Path, phase_id: str, worker_id: str) -> bool:
    """Atomically claim `phase_id` for THIS worker (PRES-018 owned lease).

    Returns True iff THIS call now owns the claim. The file records the
    owner token (the release credential), worker id, pid + boot identity,
    monotonic revision/fencing, claimed_at and expiry_at. A steal happens
    ONLY through the staleness oracle above -- never by age alone -- and
    the whole stale-claim replacement runs inside a per-phase flock window,
    so two simultaneous reapers racing one dead claim produce exactly one
    winner (the O_EXCL create alone cannot close the unlink->create gap)."""
    path = _claim_path(run_dir, phase_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    owner_token = uuid.uuid4().hex
    # The fencing revision is read from the PREDECESSOR record (inside the
    # steal window when stealing) so it advances monotonically through
    # steal cycles of one phase.
    revision = _next_claim_revision(path)
    fd = None

    # Fresh-claim fast path: O_EXCL create when NO claim file exists yet.
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        # PRES-018: steal ONLY through the staleness oracle, serialized.
        lock_path = _steal_lock_path(run_dir, phase_id)
        try:
            lock_fd = os.open(str(lock_path),
                              os.O_CREAT | os.O_RDWR, 0o644)
        except OSError:
            return False
        try:
            try:
                import fcntl
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
            except (ImportError, OSError):
                pass  # degraded platform: fall through to best-effort CAS
            try:
                # Re-check staleness INSIDE the window: the file may have
                # changed (or vanished) while we waited for the lock.
                if not path.exists():
                    fd = os.open(str(path), os.O_CREAT | os.O_EXCL
                                 | os.O_WRONLY, 0o644)
                else:
                    stale, _why = _claim_is_stale(path, 0.0)
                    if not stale:
                        return False
                    # CAS: the token judged stale must still be on disk at
                    # unlink time, or a racer already re-claimed. The
                    # predecessor's fencing value is read from the SAME
                    # record, BEFORE the unlink -- after unlink the file is
                    # gone and the revision would reset to 1 instead of
                    # advancing monotonically (PRES-018 fencing contract).
                    victim = _read_claim_record(path) or {}
                    victim_token = str(victim.get("owner_token") or "")
                    try:
                        revision = int(victim.get("fencing") or 0) + 1
                    except (TypeError, ValueError):
                        revision = 1
                    if not _unlink_claim_if_token(path, victim_token):
                        return False
                    try:
                        fd = os.open(str(path), os.O_CREAT | os.O_EXCL
                                     | os.O_WRONLY, 0o644)
                    except FileExistsError:
                        return False
            finally:
                try:
                    import fcntl
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                except (ImportError, OSError):
                    pass
        finally:
            os.close(lock_fd)
    try:
        identity = _claim_owner_identity()
        # FIX 105 start reference (liveness tooling keeps reading it) plus
        # the PRES-018 ownership record.
        try:
            started_at = time.clock_gettime(time.CLOCK_BOOTTIME)  # type: ignore[attr-defined]
        except (AttributeError, OSError):
            started_at = time.time()
        os.write(fd, json.dumps({
            "owner_token": owner_token,
            "worker": worker_id,
            "revision": revision,
            "fencing": revision,
            "pid": identity["pid"],
            "boot_uptime": identity["boot_uptime"],
            "started_at": started_at,
            "claimed_at": utcnow(),
            "expiry_at": time.time() + (SINGLE_ATTEMPT_BUDGET_S *
                                        CLAIM_STALE_MULTIPLIER),
        }).encode())
    finally:
        os.close(fd)
    return True


def release_claim(run_dir: Path, phase_id: str,
                  owner_token: Optional[str] = None) -> None:
    """Release THIS worker's claim -- ONLY while it still owns it.

    PRES-018: the unlink happens only when the file on disk still records
    an owner token matching `owner_token` (the token THIS worker's
    try_claim generated). A mismatch -- a NEW owner has claimed since --
    leaves the file alone: an old owner can never delete a new owner's
    claim, and PID reuse proves nothing. Back-compat: the two-argument form
    releases only a claim whose recorded holder is still THIS process
    (pid + boot identity), matching FIX 105's self-release contract."""
    path = _claim_path(run_dir, phase_id)
    rec = _read_claim_record(path)
    if rec is None:
        return
    if owner_token is not None:
        if rec.get("owner_token") != owner_token:
            return            # a new owner holds it now: NOT ours to delete
    else:
        if rec.get("pid") != os.getpid():
            return
        if not _owner_matches_identity(rec):
            return
    try:
        path.unlink()
    except OSError:
        pass


def _current_claim_token(run_dir: Path, phase_id: str,
                         worker_id: str) -> Optional[str]:
    """The owner token in the claim file IF the file still names `worker_id`
    as its holder, else None (the caller's fencing check then fails). This
    is the publication-side half of the fencing contract: the token a
    worker captured at claim time must still be the file's token at
    publish time."""
    rec = _read_claim_record(_claim_path(run_dir, phase_id))
    if not rec:
        return None
    if rec.get("worker") != worker_id:
        return None
    token = rec.get("owner_token")
    return str(token) if token else None


# ---------------------------------------------------------------------------
# Manifest resolution for a run -- read-only. Used to build real Phase
# objects (for resolve_artifact_patterns and owning_role fallback) but the
# work order's own JSON is authoritative when a Manifest cannot be loaded
# (this module must keep working even in a degraded environment; it simply
# falls back to the raw work-order fields, per resolve_target_paths above).
# ---------------------------------------------------------------------------
def load_manifest_for_run(run_dir: Path) -> Optional[Manifest]:
    state_path = run_dir / "state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    mp = state.get("manifest_path")
    if not mp or not Path(mp).is_file():
        return None
    try:
        return Manifest(Path(mp))
    except SystemExit:
        return None


def resolve_scripts_dir_for_run(run_dir: Path) -> Path:
    """The scripts_dir that OWNS this run -- derived from state.json's own
    pinned manifest_path (authoritative, per-run) so this module works
    correctly against ANY run regardless of where dispatcher.py itself is
    installed. Falls back to this module's own location only when state.json
    is unavailable (e.g. a sweep tick that races job creation)."""
    state_path = run_dir / "state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
        mp = state.get("manifest_path")
        if mp:
            # manifest lives at <dept_root>/sops/PIPELINE-MANIFEST.json
            scripts_dir = Path(mp).resolve().parent.parent / "scripts"
            if scripts_dir.is_dir():
                return scripts_dir
    except (OSError, json.JSONDecodeError):
        pass
    return _OWN_SCRIPTS_DIR


def resolve_dept_root(scripts_dir: Path) -> Path:
    return scripts_dir.parent


# FIX 6 (presentation rev2): the auto-stamp that unconditionally wrote
# capacity_override.json = {provider: deepseek-direct, max_concurrent: 100}
# before every dispatch was DELETED. That fabricated declaration resolved
# capacity.probe() to MEASURED=100 and masked the real detected tier (and the
# PARK/interview path) on every box. The override file is now written ONLY by
# the detection/interview flow (resource_profile.record_plan_answer ->
# capacity.declare_capacity) or an explicit operator action
# (--declare-capacity --declare-provider); with no override present,
# resolve_max_workers() reports the DETECTED tier (e.g. ollama-cloud /
# $20/month -> 3), never a fabricated 100.


class CapacityDeclarationRefused(RuntimeError):
    """--declare-capacity could not establish WHICH provider it declares.

    Raised INSTEAD of writing a record that would PARK the run. main() turns
    it into exit 2 with the message intact."""


def ensure_capacity_override(dept_root: Path, *, max_concurrent: int = 100,
                             provider: Optional[str] = None,
                             model: Optional[str] = None,
                             plan: Optional[str] = None) -> Optional[Path]:
    """Declare a capacity ceiling for ONE NAMED PROVIDER. Never a hard-coded one.

    THE DEFECT (F4, MEASURED by Fable on this box 2026-09-07, scratch config
    dir, live profile md5 unchanged): this function hard-coded
    `{"provider": "deepseek-direct", "max_concurrent": N}`. deepseek-direct
    JOINED THE STRUCTURAL CAP TABLE on 2026-09-04 (capacity.CAP_TABLE carries
    ('deepseek-direct','v4-flash')=2500 and ('deepseek-direct','v4-pro')=500,
    and capacity.NO_CAP_PROVIDERS shrank to {'openrouter'}). A cap-table
    provider declared WITHOUT a plan hits capacity._resolve_override case 2 --
    "the provider's real ceiling is a physical fact the operator cannot opt out
    of by typing a bigger number" -- and PARKS. So `--declare-capacity 100`,
    the flag whose entire job is to WIDEN a run, measured:

        capacity.probe() -> status=PARKED provider=deepseek-direct
                            plan=None available=None
                            autofail=AF-CAPACITY-UNMEASURED
        dispatcher.resolve_max_workers(...) -> 3

    Three changes:
      1. THE PROVIDER IS AN ARGUMENT. Explicit `provider` wins; otherwise the
         canonical provider capacity.detect() actually found on this box. The
         literal "deepseek-direct" is gone -- a declaration about a provider
         this box does not use is not a widening, it is a lie about a route.
      2. A PLAN IS RESOLVED FOR THAT PROVIDER before writing, so the record
         lands on _resolve_override case 1 (cap table authoritative; a declared
         number may only LOWER it) instead of case 2 (PARK): explicit `plan` >
         the route/model slug > the profile's locked tier > this box's own
         detection when it is about the SAME provider.
      3. IT REFUSES rather than writing a PARK-inducing record -- no provider
         establishable, or a cap-table provider whose plan nobody knows. A
         refusal the operator can act on beats a file that silently drops the
         whole run to capacity.DEFAULT_CONSERVATIVE.

    NO_CAP providers (openrouter) need no plan: _resolve_override case 0
    honours a declared self-throttle verbatim, so they are never refused here.

    Idempotent, as before: an existing capacity_override.json is NEVER
    overwritten -- it may be the client's own declaration, and this function is
    not the owner of somebody else's answer. Returns the path (written or
    pre-existing), or None when capacity.py cannot be imported."""
    try:
        sys.path.insert(0, str(dept_root / "scripts"))
        from presentation_job import capacity as _capacity
    except ImportError:
        return None
    path = _capacity.override_path()
    if path.is_file():
        return path

    detected: Optional[Dict[str, Any]] = None

    def _detect_once() -> Dict[str, Any]:
        nonlocal detected
        if detected is None:
            try:
                detected = _capacity.detect() or {}
            except Exception:  # noqa: BLE001 -- detection is evidence, not a gate
                detected = {}
        return detected

    canon = _capacity.normalize_provider(provider) if provider else None
    if provider and not canon:
        raise CapacityDeclarationRefused(
            f"--declare-capacity refused: provider {provider!r} does not "
            f"resolve to any provider this build knows (cap table "
            f"{sorted(_capacity.CAP_TABLE_PROVIDERS)}, no-cap "
            f"{sorted(_capacity.NO_CAP_PROVIDERS)}). A declaration about an "
            f"unidentified provider is a self-report, not a measurement: "
            f"capacity bounds it to DEFAULT_CONSERVATIVE="
            f"{_capacity.DEFAULT_CONSERVATIVE}, so the run would end up "
            f"NARROWER than with no file at all. Name a provider this build "
            f"knows, or answer the capacity interview "
            f"(python3 -m presentation_job --capacity).")
    if not canon:
        canon = _capacity.normalize_provider(
            str(_detect_once().get("provider") or "")) or None
    if not canon:
        raise CapacityDeclarationRefused(
            "--declare-capacity refused: no provider could be established for "
            "this box (none passed via --declare-provider, and capacity."
            "detect() resolved none from 9Router or OpenClaw). Writing a "
            "declaration anyway would have to GUESS a provider -- and a guess "
            "that lands on a structural cap-table provider with no plan PARKS "
            "the run at AF-CAPACITY-UNMEASURED (width "
            f"{_capacity.DEFAULT_CONSERVATIVE}), which is the opposite of what "
            "this flag is for. Pass --declare-provider <provider>, or answer "
            "the capacity interview (python3 -m presentation_job --capacity).")

    norm_plan = None
    if plan:
        norm_plan = _capacity.normalize_plan(plan, canon)
        if not norm_plan:
            raise CapacityDeclarationRefused(
                f"--declare-capacity refused: plan {plan!r} is not a known "
                f"tier for {canon}. Known tiers: "
                f"{list(_capacity.PLANS_BY_PROVIDER.get(canon, ()))}.")
    if not norm_plan and model:
        norm_plan = _capacity._plan_from_model_slug(canon, str(model))
    if not norm_plan:
        # the resource profile is the per-provider store of plan answers
        try:
            from presentation_job import resource_profile as _rp
            entry = _rp.get_provider(_rp.load_profile(), canon) or {}
            if entry.get("locked") or entry.get("plan_known"):
                norm_plan = _capacity.normalize_plan(entry.get("plan_tier"), canon)
        except Exception:  # noqa: BLE001 -- the profile is evidence, not a gate
            pass
    if not norm_plan:
        det = _detect_once()
        if _capacity.normalize_provider(str(det.get("provider") or "")) == canon:
            norm_plan = _capacity.normalize_plan(det.get("plan"), canon)

    if not norm_plan and canon in _capacity.CAP_TABLE_PROVIDERS:
        raise CapacityDeclarationRefused(
            f"--declare-capacity refused: {canon} is on the structural cap "
            f"table {sorted(_capacity.CAP_TABLE_PROVIDERS)} and no plan tier "
            f"could be established for it (none passed via --declare-plan, no "
            f"route model to read one from, nothing locked in the resource "
            f"profile, and this box's own detection did not answer about "
            f"{canon}). A cap-table provider declared without a plan PARKS the "
            f"run -- capacity._resolve_override case 2, MEASURED "
            f"status=PARKED available=None, resolve_max_workers -> "
            f"{_capacity.DEFAULT_CONSERVATIVE} -- so this refuses instead of "
            f"writing that record. Pass --declare-plan from "
            f"{list(_capacity.PLANS_BY_PROVIDER.get(canon, ()))}, or answer "
            f"the capacity interview for {canon} "
            f"(python3 -m presentation_job --capacity).")

    declare = getattr(_capacity, "declare_capacity", None)
    if callable(declare):
        # F1's per-provider writer (schema 2): merges ONE sub-record and
        # preserves every other provider's declaration.
        return declare(canon, plan=norm_plan, max_concurrent=int(max_concurrent))

    # Pre-F1 capacity build: the same file, in the v1 shape
    # capacity.read_override already understands -- but about the provider that
    # was ESTABLISHED, and carrying the plan that keeps it out of the PARK
    # branch. F1 reads a v1 record as a declaration about ITS OWN provider
    # only, so this record never answers for anybody else.
    record: Dict[str, Any] = {"provider": canon,
                              "max_concurrent": int(max_concurrent)}
    if norm_plan:
        record["plan"] = norm_plan
    record["source"] = "operator-declared"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return path


def resolve_max_workers(dept_root: Path, requested: Optional[int],
                         *, unit_count: Optional[int] = None) -> int:
    """Ticket 2 (PARALLEL-PIPELINE-SPEC S0.6): `capacity.probe()['available']` is
    either a positive int (a measured CAP_TABLE ceiling) or the UNBOUNDED
    sentinel (a NO_CAP_PROVIDERS hit, e.g. deepseek-direct/openrouter --
    capacity.py's `_Unbounded.__int__` raises TypeError ON PURPOSE so nothing
    can silently treat it as a count). The old `isinstance(available, int)`
    check is therefore False for EVERY unbounded account, and fell through to
    DEFAULT_MAX_WORKERS = 8 -- silently collapsing "no structural ceiling" to
    "8" any time ensure_capacity_override() had not already pre-written an
    int override first (dispatcher.py:2275's watch_run_dir path masked this in
    practice; the --once path with a pre-existing provider-only override did
    not). Branch on is_unbounded() BEFORE the isinstance(int) test: an
    unbounded account resolves to `unit_count` (dispatch as wide as the ready
    work allows, per cap_wave_width's own contract, execution_plan.py:155-176)
    when the caller knows it.

    U1 (2026-09-07): when the caller does NOT know a unit count this returned
    DEFAULT_MAX_WORKERS -- the same "UNBOUNDED means 8" collapse `_routing_stamp`
    had, in the accessor the dispatcher's own work-order pool uses (four call
    sites below, none of which passes a unit_count). It now returns THE MODE
    CEILING, exactly as the stamp does. `_unbounded_width` is given no decision
    here, so it answers model_router.mode_ceiling(mode) with no profile: the
    operator ceiling for every mode. That is mode_operator_ceiling()'s own
    documented behaviour on a client whose ceiling was never measured (the mode
    axis is inert there), not a widening invented in this function -- the
    profile-aware ceiling is applied where the profile is actually loaded, in
    _routing_stamp via resolve_route's `mode_ceiling` block. The router being
    absent still yields DEFAULT_MAX_WORKERS: the pre-FIX-7 rollback number.

    The final fallback (probe raised, or answered nothing usable) is the same
    truly-unknown case `_refuse_unmeasured_width` covers in the stamp, so it
    likewise resolves to capacity.DEFAULT_CONSERVATIVE -- "the floor every
    unknown collapses to. NEVER guess upward" -- and only degrades to
    DEFAULT_MAX_WORKERS when capacity.py itself cannot be imported, which is the
    one situation that constant was actually written for.

    F4 (2026-09-07) -- THE NO-ARG PROBE HERE IS DELIBERATE. DO NOT "FIX" IT.
    F4 made `_routing_stamp` ask `capacity.probe(provider=<the routed
    provider>, model=<the route model>)`, because that stamp decides ONE
    ROUTE's fan-out width and a single global answer is right for at most one
    route on a two-provider client. THIS function decides something different:
    the size of the dispatcher's WORK-ORDER POOL, which serves every route in
    the run at once. There is no single provider to name here -- the pool is
    not per-provider -- and naming one would cap the whole pool at one
    provider's ceiling, which is Defect 1 rebuilt in a second place.

    What bounds any ONE provider inside that pool is the governor's per-provider
    `max_inflight` (governor.py provider_config -> the profile's
    concurrency_ceiling / plan tier), applied per lease at call time. Pool size
    and per-provider ceiling are two different numbers and both are enforced;
    collapsing them into one is the mistake, not the fix.
    """
    if requested is not None:
        return max(1, requested)
    try:
        sys.path.insert(0, str(dept_root / "scripts"))
        from presentation_job import capacity as _capacity
        result = _capacity.probe()
        available = result.get("available")
        if _capacity.is_unbounded(available):
            if isinstance(unit_count, int) and unit_count > 0:
                return unit_count
            mode, _source = _active_mode()
            ceiling = _unbounded_width(mode)
            if ceiling is not None:
                return int(ceiling)
            return DEFAULT_MAX_WORKERS
        if isinstance(available, int) and available > 0:
            return available
    except Exception:  # noqa: BLE001 -- capacity probing is best-effort; never block dispatch
        pass
    floor = _conservative_floor()
    return int(floor) if floor is not None else DEFAULT_MAX_WORKERS


# ---------------------------------------------------------------------------
# The dispatch ledger (FIX 2026-08-27) -- the CROSS-TICK memory this module
# never had. Diagnosed from a live run's own sidecar logs, not from theory:
# /Users/.../trust-ledger/2026-08-27/working/work-orders/.
#
# THE DEFECT, in two symptoms with one cause:
#
#   (a) 494 byte-identical `"status": "declined"` records (382KB) for
#       P-SP-INTAKE in a single run.
#   (b) 497 records for P-0.5-RESEARCH, every one of them
#       `"status": "already_done_in_state"`, ~every 10s for the run's life.
#
# CAUSE: sweep_run_dir() re-enumerates working/work-orders/*.json every
# SWEEP_INTERVAL_S and re-dispatches EVERY order file it finds. Nothing ever
# removes or marks a work order once its phase reaches a terminal outcome, so
# a phase that is `done` in state.json -- or one this module permanently
# DECLINES (DECLINE_PHASES is a module-level constant; membership cannot
# change while the process lives) -- is re-claimed, re-dispatched, re-declined
# and re-logged on every tick until the run ends.
#
# WHY NO BACKOFF EVER ENGAGED: DISPATCH_RETRY_CAP bounds retries *inside* one
# dispatch_one() call. Each sweep tick calls dispatch_one() FRESH, with zero
# knowledge of any prior tick, so there was no cross-tick attempt count to
# back off on and no ceiling on re-entry. (The `"attempt": 0` on every one of
# those records is NOT a counter that failed to increment -- it is a hardcoded
# literal meaning "no model call was made on this tick". The real per-call
# counter increments correctly; the same live log's first line is
# `"attempt": 1, "status": "verified"`. What was missing was persistence
# ACROSS calls, which is what this ledger adds.)
#
# ANTI-STARVATION (the property that matters most here): suppression is keyed
# on an outcome SIGNATURE, never on the phase alone. A different status, a
# different reason, or any movement in the two things that can change this
# phase's outcome -- its work-order file (the Engine rewrites it only when it
# genuinely wants the phase run again; phases.py FAULT-09b explicitly refuses
# to rewrite a live one) and the phase's own status in state.json -- resets
# the counter to zero and re-dispatches on the very next tick with NO delay.
# Deduplication here removes redundant repeats of an outcome already recorded.
# It can never delay the first observation of a new one.
#
# Ledger files live in a DOT-SUBDIRECTORY of work-orders/ on purpose:
# sweep_run_dir globs "*.json" in that directory and treats every match as a
# phase id, so a sibling <phase>.dispatch-state.json would be dispatched as a
# phantom phase named "<phase>.dispatch-state". The existing .claim and
# .dispatcher-log.jsonl conventions dodge that glob the same way.
# ---------------------------------------------------------------------------
_LEDGER_DIRNAME = ".dispatch-state"


def _ledger_path(run_dir: Path, phase_id: str) -> Path:
    return run_dir / "working" / "work-orders" / _LEDGER_DIRNAME / f"{phase_id}.json"


def _blocked_marker_path(run_dir: Path, phase_id: str) -> Path:
    """Deliberately NOT *.json and NOT hidden: this file is the loud, visible
    'a human needs to look at this' signal, and it must survive an `ls` while
    staying out of sweep_run_dir's own *.json phase glob."""
    return run_dir / "working" / "work-orders" / f"{phase_id}.dispatch-blocked.txt"


def _read_ledger(run_dir: Path, phase_id: str) -> Dict[str, Any]:
    try:
        obj = json.loads(_ledger_path(run_dir, phase_id).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return obj if isinstance(obj, dict) else {}


def _write_ledger(run_dir: Path, phase_id: str, record: Dict[str, Any]) -> None:
    path = _ledger_path(run_dir, phase_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".json.partial-{os.getpid()}")
    tmp.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)  # atomic: a concurrent reader never sees a torn ledger


def _outcome_signature(status: str, reasons: Optional[List[str]] = None) -> str:
    """What makes two outcomes 'the same outcome'. Status plus reasons, never
    the timestamp or the worker id -- those are exactly the two fields that
    made 494 identical declines look superficially unique."""
    body = "|".join(str(r) for r in (reasons or []))
    return f"{status}::{hashlib.sha256(body.encode('utf-8')).hexdigest()[:16]}"


def _dispatch_revision(run_dir: Path, phase_id: str,
                       order_file: Optional[Path] = None) -> str:
    """A cheap witness of everything that could change this phase's outcome.

    Two stats, no parsing beyond one small state.json read:
      * the work-order file's mtime+size -- the Engine writes it only when it
        actually wants this phase dispatched again (phases.py:800 refuses to
        clobber a live one), so a change here is a genuine new request;
      * this phase's OWN status string in state.json -- deliberately not the
        whole file's mtime, which churns whenever ANY other phase advances and
        would break every backoff window in the run for no reason.
    """
    of = order_file or (run_dir / "working" / "work-orders" / f"{phase_id}.json")
    try:
        st = of.stat()
        wo = f"{st.st_mtime_ns}:{st.st_size}"
    except OSError:
        wo = "absent"
    status = "unknown"
    try:
        state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
        for ps in state.get("phases", []):
            if ps.get("id") == phase_id:
                status = str(ps.get("status"))
                break
    except (OSError, json.JSONDecodeError):
        pass
    return f"wo={wo}|state={status}"


def _backoff_delay_s(repeat: int) -> float:
    """repeat is the number of times this outcome has recurred AFTER its first
    observation. repeat<=0 (a new or changed outcome) is always zero delay."""
    if repeat <= 0:
        return 0.0
    return min(DISPATCH_BACKOFF_CAP_S,
               DISPATCH_BACKOFF_BASE_S * (DISPATCH_BACKOFF_MULTIPLIER ** (repeat - 1)))


def should_dispatch(run_dir: Path, phase_id: str, *,
                    order_file: Optional[Path] = None,
                    now: Optional[float] = None) -> Tuple[bool, str]:
    """The gate sweep_run_dir consults BEFORE claiming a phase. Returns
    (True, "") to dispatch, or (False, why) to skip this tick.

    Skipping happens on exactly one condition -- an unexpired backoff window
    whose world has NOT moved. Anything else dispatches."""
    led = _read_ledger(run_dir, phase_id)
    if not led:
        return True, ""
    eligible_at = led.get("next_eligible_at_epoch")
    if not isinstance(eligible_at, (int, float)):
        return True, ""
    now = time.time() if now is None else now
    if now >= eligible_at:
        return True, ""
    if _dispatch_revision(run_dir, phase_id, order_file) != led.get("revision"):
        # ANTI-STARVATION: the work order was reissued or this phase's own
        # state changed. Whatever we backed off from is no longer the same
        # situation -- dispatch immediately, no matter how deep the backoff.
        return True, ""
    return False, (f"backoff: {led.get('consecutive', 0)} consecutive "
                   f"'{led.get('status')}' outcomes, next eligible in "
                   f"{eligible_at - now:.0f}s")


def record_outcome(run_dir: Path, phase_id: str, status: str,
                   reasons: Optional[List[str]] = None, *, worker_id: str,
                   order_file: Optional[Path] = None,
                   now: Optional[float] = None) -> Dict[str, Any]:
    """Fold one dispatch outcome into the ledger and decide whether it earns a
    sidecar record. Returns the new ledger entry.

    A sidecar line is written when the outcome is NEW (different signature, or
    a changed world) -- never for a byte-identical repeat of something already
    on the log. `observation` is the cross-tick counter the old records lacked
    entirely: it persists in the ledger and increments on every tick, so the
    one emitted record still reports honestly how many times this was seen."""
    now = time.time() if now is None else now
    led = _read_ledger(run_dir, phase_id)
    sig = _outcome_signature(status, reasons)
    rev = _dispatch_revision(run_dir, phase_id, order_file)

    same = bool(led) and led.get("signature") == sig and led.get("revision") == rev
    consecutive = (int(led.get("consecutive") or 0) + 1) if same else 1
    observations = int(led.get("observations") or 0) + 1
    # repeat 0 == first sighting of this outcome => next tick is eligible with
    # no delay at all. Backoff only ever grows on a genuine identical repeat.
    delay = _backoff_delay_s(consecutive - 1)

    entry: Dict[str, Any] = {
        "phase_id": phase_id,
        "status": status,
        "signature": sig,
        "revision": rev,
        "consecutive": consecutive,
        "observations": observations,
        "reasons": list(reasons or []),
        "first_seen_at": led.get("first_seen_at") if same else utcnow(),
        "last_seen_at": utcnow(),
        "backoff_s": delay,
        "next_eligible_at_epoch": now + delay,
        "blocked": False,
        "blocked_reason": None,
        "worker": worker_id,
    }

    if status in _FAILING_STATUSES and consecutive >= DISPATCH_REPEAT_CEILING:
        entry["blocked"] = True
        entry["blocked_reason"] = (
            f"{consecutive} consecutive identical '{status}' dispatch outcomes for "
            f"{phase_id} (retry ceiling DISPATCH_REPEAT_CEILING={DISPATCH_REPEAT_CEILING}). "
            f"Last reasons: {reasons or []}")
        entry["blocked_at"] = utcnow()
        # Parked, never dropped: re-dispatch resumes the moment the Engine
        # reissues the work order or this phase's state changes (should_dispatch's
        # revision check), so a real fix upstream un-parks it automatically.
        entry["next_eligible_at_epoch"] = now + DISPATCH_BACKOFF_CAP_S

    _write_ledger(run_dir, phase_id, entry)

    if not same:
        record: Dict[str, Any] = {
            "worker": worker_id, "attempt": 0, "status": status,
            "observation": observations, "consecutive": consecutive,
        }
        if reasons:
            record["reason"] = reasons[0] if len(reasons) == 1 else list(reasons)
        _append_sidecar(run_dir, phase_id, record)

    if entry["blocked"] and not led.get("blocked"):
        _park_blocked(run_dir, phase_id, entry, worker_id=worker_id)

    return entry


def _park_blocked(run_dir: Path, phase_id: str, entry: Dict[str, Any], *,
                  worker_id: str) -> None:
    """Fail LOUD. Three independent, non-silenceable signals: a plain-text
    marker file a human will see in an `ls` of work-orders/, a distinct
    sidecar status no other outcome uses, and stderr."""
    reason = entry.get("blocked_reason") or "retry ceiling reached"
    marker = _blocked_marker_path(run_dir, phase_id)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        "DISPATCH BLOCKED -- NEEDS ATTENTION\n"
        f"phase:       {phase_id}\n"
        f"blocked_at:  {entry.get('blocked_at')}\n"
        f"worker:      {worker_id}\n"
        f"status:      {entry.get('status')}\n"
        f"consecutive: {entry.get('consecutive')} identical outcomes\n"
        f"reason:      {reason}\n"
        "\nThis phase stopped being re-dispatched after the retry ceiling. It was NOT\n"
        "marked done and NOT silently dropped. Dispatch resumes automatically if the\n"
        "Engine reissues the work order or this phase's state.json status changes.\n"
        f"Ledger: working/work-orders/{_LEDGER_DIRNAME}/{phase_id}.json\n",
        encoding="utf-8")
    _append_sidecar(run_dir, phase_id, {
        "worker": worker_id, "attempt": 0, "status": "blocked_retry_ceiling",
        "reason": reason, "consecutive": entry.get("consecutive"),
        "observation": entry.get("observations"),
    })
    print(f"[dispatcher {worker_id}] BLOCKED {phase_id}: {reason} "
          f"(marker: {marker})", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# One sweep over one run dir's work-orders directory.
# ---------------------------------------------------------------------------
def sweep_run_dir(run_dir: Path, *, worker_id: str, max_workers: int) -> List[DispatchResult]:
    wo_dir = run_dir / "working" / "work-orders"
    if not wo_dir.is_dir():
        return []
    order_files = sorted(wo_dir.glob("*.json"))
    if not order_files:
        return []

    manifest = load_manifest_for_run(run_dir)
    scripts_dir = resolve_scripts_dir_for_run(run_dir)
    dept_root = resolve_dept_root(scripts_dir)

    claimed_here: List[str] = []
    # PRES-018: phase_id -> the owner token THIS sweep captured at claim
    # time. release uses it (owner-matched delete); dispatch_one's
    # publication fence re-reads the file and compares against the holder.
    owner_tokens: Dict[str, Optional[str]] = {}
    jobs: List[Tuple[str, Dict[str, Any], Optional[Phase]]] = []
    for of in order_files:
        phase_id = of.stem
        try:
            order = json.loads(of.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        # TERMINAL SHORT-CIRCUIT (FIX 2026-08-27). Both predicates below are
        # settled facts, not work: DECLINE_PHASES is a module constant, and a
        # phase `done` in state.json is monotonic. dispatch_one() already
        # returned early on both -- but only AFTER the sweep had paid for a
        # claim-file create, a manifest lookup, a thread-pool submit and a
        # claim-file unlink, every tick, forever. Deciding it here costs one
        # dict lookup and one small json read, and skips the round-trip
        # entirely. The predicates are still re-evaluated EVERY tick, so a
        # phase that genuinely stops being done is picked straight back up;
        # only the redundant repeat record is suppressed (record_outcome).
        if phase_id in DECLINE_PHASES:
            record_outcome(run_dir, phase_id, "declined", [DECLINE_PHASES[phase_id]],
                           worker_id=worker_id, order_file=of)
            continue
        if _phase_already_done(run_dir, phase_id):
            record_outcome(run_dir, phase_id, "already_done_in_state",
                           worker_id=worker_id, order_file=of)
            continue

        may, why = should_dispatch(run_dir, phase_id, order_file=of)
        if not may:
            continue

        if not try_claim(run_dir, phase_id, worker_id):
            continue
        claimed_here.append(phase_id)
        # PRES-018: capture THIS claim's owner token right after the
        # successful O_EXCL create -- it is both the release credential
        # (release only deletes while the file still records it) and the
        # fencing token checked at artifact publication.
        claim_rec = _read_claim_record(_claim_path(run_dir, phase_id)) or {}
        owner_tokens[phase_id] = str(claim_rec.get("owner_token") or "") or None
        phase_obj = None
        if manifest is not None:
            try:
                phase_obj = manifest.phase_or_none(phase_id) if hasattr(manifest, "phase_or_none") \
                    else next((p for p in manifest.phases if p.id == phase_id), None)
            except Exception:  # noqa: BLE001
                phase_obj = None
        jobs.append((phase_id, order, phase_obj))

    if not jobs:
        return []

    results: List[DispatchResult] = []
    workers = max(1, min(max_workers, len(jobs)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {
            pool.submit(dispatch_one, run_dir, phase_id, order,
                       dept_root=dept_root, phase_obj=phase_obj, worker_id=worker_id): phase_id
            for phase_id, order, phase_obj in jobs
        }
        for fut in as_completed(futs):
            phase_id = futs[fut]
            try:
                res = fut.result()
            except Exception as exc:  # noqa: BLE001 -- one phase's crash must not kill the sweep
                _append_sidecar(run_dir, phase_id, {
                    "worker": worker_id, "attempt": 0, "status": "error",
                    "reason": f"dispatch_one raised {exc!r}",
                })
                # A crashing dispatch_one IS a failing outcome: fold it into the
                # ledger too, or a phase whose dispatch_one always raises would
                # loop forever outside every backoff/ceiling mechanism.
                record_outcome(run_dir, phase_id, "error", [f"dispatch_one raised {exc!r}"],
                               worker_id=worker_id)
                results.append(DispatchResult(phase_id, "error", 0, [repr(exc)]))
            else:
                results.append(res)
                # FIX 2026-09-04 -- THE RETURNED-OUTCOME LEDGER GAP.
                #
                # Until this line, record_outcome() had exactly THREE call
                # sites, and all three sat OUTSIDE dispatch_one's normal
                # return path: the DECLINE_PHASES short-circuit and the
                # already-done short-circuit (both above, before the phase is
                # ever claimed), and the `except` branch just above (only when
                # dispatch_one RAISES). Every value dispatch_one actually
                # RETURNS -- "ok", "error", "exhausted", "declined",
                # "skipped_satisfied" -- was appended to `results` and thrown
                # away as far as the ledger was concerned. No signature, no
                # `consecutive`, no backoff window, no ceiling. should_dispatch
                # therefore returned True on every tick forever.
                #
                # Live proof (run pres-wave-e-v3-1787240658, the SAME 542 sweep
                # ticks 2026-09-02T11:31:25 -> 14:06:13):
                #   P-SP-INTAKE  (DECLINE_PHASES -> record_outcome)
                #       -> ledger written, parked at consecutive=8 with a
                #          .dispatch-blocked.txt marker.
                #   P4-PROMPT    (dispatch_one RETURNED "error" every tick)
                #       -> 542 error rows, NO ledger file at all, never parked.
                # Same run, same ticks, same failure class: 542 vs 8. The split
                # lands exactly on "did the outcome flow through record_outcome"
                # -- a routing fault, not a per-call-site bug. Reproduced at the
                # seam for the fanout zero-units refusal in
                # tests/test_fanout_zero_units_ceiling.py.
                #
                # Folding the returned outcome in here fixes EVERY such path at
                # once, because sweep_run_dir is dispatch_one's only production
                # caller -- so all ~60 _append_sidecar sites inside its call
                # tree (the fanout zero-units refusal included) now reach the
                # ceiling. The refusals themselves are untouched: a phase that
                # must refuse still refuses, it just stops refusing FOREVER.
                # Non-failing statuses are recorded too (they earn backoff on an
                # identical repeat) but can never park -- only _FAILING_STATUSES
                # reach the DISPATCH_REPEAT_CEILING branch in record_outcome.
                #
                # order_file is left to record_outcome's default, which resolves
                # to run_dir/working/work-orders/<phase_id>.json -- byte-identical
                # to the `of` this sweep globbed (phase_id IS of.stem).
                record_outcome(run_dir, phase_id, res.status, list(res.reasons),
                               worker_id=worker_id)
            finally:
                # PRES-018: owner-matched release -- the token captured at
                # claim time must still be the file's token, or the file
                # belongs to a NEW owner and is left untouched. Never the
                # old unconditional unlink.
                release_claim(run_dir, phase_id, owner_tokens.get(phase_id))
    return results


def _run_terminal(run_dir: Path) -> Optional[str]:
    try:
        state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
        return state.get("terminal")
    except (OSError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# FIX 9 -- the dispatcher's own exit condition. Per MASTER Part 8 Fix 9 the
# watch loops no longer rely solely on "terminal is set" (a single-phase
# --resume never sets terminal, and a quarantined unit parks WITHOUT setting
# terminal). The exit condition becomes exactly: NO OPEN WORK ORDERS and the
# ENGINE PID DEAD. Until both hold, the dispatcher keeps sweeping: a phase
# whose work order is still open must be picked up whether the engine is alive
# or newly resumed.
#
# RECONCILIATION (2026-09-05, from the live run archived in the P-SP-INTAKE
# collision evidence). This comment used to also claim "Fix 9 drops
# terminal=BLOCKED entirely". That claim is FALSE and had drifted from the
# code on BOTH sides:
#   * terminal="BLOCKED" is still WRITTEN, in 8 places in phases.py
#     (:2446 _block, :2673 the end-of-run park, and the six close()/gate
#     paths at :3120 :3192 :3210 :3233 :3267 :3285);
#   * it is still READ as a real terminal by five other modules --
#     supervisor.py:406, watchdog.py:131, sweep.py:120, cc_board.py:188 and
#     process_reaper.py:351 -- plus roughly fifteen tests that assert it by
#     name. Nothing was ever retired.
# So _run_terminal() honouring it is CORRECT and stays exactly as it is; the
# comment was the thing that drifted, and the dispatcher's behaviour is not
# changed by this reconciliation.
#
# What Fix 9 actually did was move the RUN-LEVEL park to a single end-of-run
# site (phases.py:2672, guarded by `terminal is None`) so one failing unit
# quarantines instead of parking the whole run mid-plan. The half nobody
# enforced was the Engine's own side of that contract: _block() still stamps a
# run-level terminal MID-PLAN, which silently kills dispatch for the whole run
# (both watch loops below exit on the next tick) while the Engine keeps walking
# the plan and queueing work orders nothing can service. That was FIX 22's bug
# (__main__.py:866-876) recurring mid-run rather than at entry. It is fixed on
# the Engine side, where the queueing happens, in _run_agent_phase's
# `run_parked` guard (phases.py) -- NOT by loosening this terminal check, which
# is the safety that stops a dispatcher working a run that is over.
#
# Engine-liveness oracle (read-only; this module NEVER takes RunLock -- hard
# invariant 1): the Engine writes its pid into run_dir/.job.lock on every
# RunLock acquisition (state.py RunLock.__enter__: "{pid} {ts}\n") and holds
# the flock for the whole run. This module only READS that file and probes the
# pid -- it never flocks the file, so it can never race a starting engine out
# of its own lock. A crashed engine leaves the file with a dead pid -> dead.
# Known residual: OS pid reuse could make a dead engine's pid look alive; the
# getppid guard, the terminal check and --max-lifetime-minutes remain as
# backstops, exactly as before.
# ---------------------------------------------------------------------------
DISPATCH_EXIT_GRACE_S = 120.0   # engine may not have written .job.lock yet when
                                # the auto-spawn races engine.run(); grace before
                                # "engine dead" may be believed from its absence.

def _pid_is_alive(pid: int) -> bool:
    """Mirror of __main__._pid_is_alive: True if `pid` names a process this
    user can at least see. PermissionError still means it exists."""
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True

def _engine_pid_alive(run_dir: Path) -> bool:
    """True iff the Engine process for this run dir is alive (its pid is
    recorded in .job.lock and still resolves). A missing or unreadable lock
    file means the engine is NOT running."""
    try:
        text = (run_dir / ".job.lock").read_text(encoding="utf-8")
    except OSError:
        return False
    m = re.match(r"\s*(\d+)", text)
    if not m:
        return False
    pid = int(m.group(1))
    if pid == os.getpid():   # a stale record of a probe we never make -- never self
        return False
    return _pid_is_alive(pid)

def _open_work_orders(run_dir: Path) -> List[str]:
    """Phase ids whose work order is still OPEN: an order file exists for a
    phase this module would actually work on. Settled orders are exactly the
    sweep's own terminal short-circuits: DECLINE_PHASES membership (never
    dispatchable) and `done` in state.json (monotonic). A phase under backoff
    or parked at the retry ceiling is still OPEN -- its order is live and a
    reissue or state change re-arms it, so its presence keeps the watcher
    alive."""
    wo_dir = run_dir / "working" / "work-orders"
    if not wo_dir.is_dir():
        return []
    open_ids: List[str] = []
    for of in sorted(wo_dir.glob("*.json")):
        phase_id = of.stem
        if phase_id in DECLINE_PHASES:
            continue
        if _phase_already_done(run_dir, phase_id):
            continue
        open_ids.append(phase_id)
    return open_ids

def _autospawn_lock_path(run_dir: Path) -> Path:
    """Same file __main__._auto_dispatch_lock_path uses (that module is not
    importable here without side effects; the path is duplicated, and its
    record shape {pid, started_at, run_dir} is honoured, not invented)."""
    return run_dir / "working" / "dispatcher-autospawn.lock"

def _clear_stale_autospawn_lock(run_dir: Path) -> bool:
    """Orphan-lock handling: a lock recording a DEAD pid (or an unreadable
    one) is a leftover from a killed dispatcher -- clear it so the next
    engine's auto-spawn is never confused by a stale record. A live pid (and
    not ours) is a real watcher: leave it alone."""
    path = _autospawn_lock_path(run_dir)
    if not path.is_file():
        return False
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
        pid = int(rec.get("pid") or 0)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pid = 0
    if pid == os.getpid():
        return False
    if pid == 0 or not _pid_is_alive(pid):
        try:
            path.unlink()
            return True
        except OSError:
            return False
    return False

def _release_own_autospawn_lock(run_dir: Path) -> None:
    """On this watcher's own exit, clear the autospawn lock IF it records our
    pid -- so an auto-spawned dispatcher never leaves an orphan lock behind
    (a lock naming a live-but-gone dispatcher pid is the orphan-lock defect
    of MASTER Fix 9's evidence). A lock naming some OTHER live pid belongs to
    a watcher this process does not own and is left untouched."""
    path = _autospawn_lock_path(run_dir)
    try:
        if path.is_file():
            rec = json.loads(path.read_text(encoding="utf-8"))
            if int(rec.get("pid") or 0) == os.getpid():
                path.unlink()
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass


def _dispatcher_revision() -> str:
    """PRES-017: this module's installed revision stamp -- the source file's
    size+mtime identity. Cheap, dependency-free, and enough to prove the
    consumer that answered readiness is the tree the operator deployed
    (a full git sha is not available inside an installed template)."""
    try:
        st = os.stat(__file__)
        return f"dispatcher-{st.st_size}-{int(st.st_mtime)}"
    except OSError:
        return "dispatcher-unknown"


def watch_run_dir(run_dir: Path, *, interval: float = SWEEP_INTERVAL_S,
                  max_lifetime_s: float = 6 * 3600, max_workers: Optional[int] = None,
                  worker_id: Optional[str] = None) -> None:
    worker_id = worker_id or f"dispatcher-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    scripts_dir = resolve_scripts_dir_for_run(run_dir)
    dept_root = resolve_dept_root(scripts_dir)
    # FIX 6: no auto-stamp here -- with no override file, resolve_max_workers()
    # below returns the real DETECTED tier from capacity.probe().
    workers = resolve_max_workers(dept_root, max_workers)
    # Orphan guard: a single-phase invocation (`presentation_job.py --resume --phase X`,
    # the operator/manual-targeting path -- see __main__.py's _spawn_dispatcher_if_
    # available docstring) calls engine.run(only=X), which returns EXIT_OK WITHOUT
    # ever calling close(), so state.json's "terminal" is NEVER set for that
    # invocation. Without this guard this watch loop would then run for the full
    # max_lifetime_s (default 6h) after its spawning presentation_job.py process has
    # already exited -- a real, harmless-but-wasteful orphan (found during
    # acceptance testing: two dispatcher processes were still alive, one from a
    # completed --phase run, after its parent had long since exited). POSIX
    # reparents an orphaned child to init/launchd, changing its ppid -- comparing
    # against the ppid captured at startup is a standard, dependency-free way to
    # detect "my spawning process is gone" without needing the Engine to signal
    # anything (which would mean touching phases.py/state.json, forbidden here).
    spawning_ppid = os.getppid()
    started = time.time()
    # PRES-017: STARTUP READINESS HANDSHAKE -- the watch loop's FIRST act,
    # before the first sweep, is to prove to its spawner (and any operator)
    # that this process resolved its imports, its run binding and its
    # worker capacity and is actually about to consume orders. The spawner
    # (_spawn_dispatcher_if_available) waits for THIS file within 10 s;
    # without it, "spawned" never happened and the failure is surfaced.
    # Heartbeats (below) keep the same file current: last claim, last work
    # progress, outstanding orders, active units -- "alive" is a claim about
    # consumption, not about a pid.
    def _write_heartbeat(open_orders: Optional[List[str]] = None,
                         last_claim: Optional[str] = None,
                         last_progress: Optional[str] = None,
                         active_units: int = 0) -> None:
        try:
            ready_path = run_dir / "working" / "dispatcher-ready.json"
            ready_path.parent.mkdir(parents=True, exist_ok=True)
            obj = {
                "pid": os.getpid(),
                "worker_id": worker_id,
                "run_dir": str(run_dir),
                "started_at": utcnow(),
                "ready_at": utcnow(),
                "heartbeat_at": utcnow(),
                # Installed revision: this module's own source stamp -- a
                # consumer that cannot say which revision it runs is not
                # verifiably the revision the operator thinks it deployed.
                "revision": _dispatcher_revision(),
                "max_lifetime_s": max_lifetime_s,
                "last_claim_phase": last_claim,
                "last_work_progress": last_progress,
                "outstanding_orders": len(open_orders or []),
                "active_units": int(active_units),
            }
            tmp = ready_path.with_suffix(
                ready_path.suffix + f".partial-{os.getpid()}")
            tmp.write_text(json.dumps(obj, indent=2, sort_keys=True),
                           encoding="utf-8")
            tmp.replace(ready_path)
        except Exception:  # noqa: BLE001 -- the handshake is best-effort
            pass

    _write_heartbeat(open_orders=[])

    # FIX 9: the exit condition is "no open work orders AND engine pid dead",
    # never either half alone. _idle_ticks counts consecutive ticks with zero
    # open orders while the engine is believed dead; the grace window covers
    # the auto-spawn race (the dispatcher may start a beat BEFORE engine.run()
    # takes RunLock and writes its pid into .job.lock) so we never declare the
    # engine dead during startup, and never exit while an order is still open.
    idle_ticks = 0
    first_tick = True
    last_claim_phase: Optional[str] = None
    last_progress_note: Optional[str] = None
    try:
        while True:
            if _run_terminal(run_dir) is not None:
                print(f"[dispatcher {worker_id}] run terminal is set -- exiting", flush=True)
                return
            if os.getppid() != spawning_ppid:
                # The spawning engine process is gone. If ANY work order is
                # still open, stay alive and keep sweeping (the swarm-runner
                # contract: work orders outlive one engine invocation and the
                # next resume may need no re-spawn). Exit only when nothing
                # is open -- the old unconditional orphan exit is kept solely
                # for the already-empty case, where spinning was pure waste.
                if not _open_work_orders(run_dir):
                    print(f"[dispatcher {worker_id}] spawning process ({spawning_ppid}) is gone "
                          f"(reparented to {os.getppid()}) and no open work orders -- exiting",
                          flush=True)
                    return
            if time.time() - started > max_lifetime_s:
                print(f"[dispatcher {worker_id}] max lifetime exceeded -- exiting", flush=True)
                return
            _clear_stale_autospawn_lock(run_dir)
            open_orders = _open_work_orders(run_dir)
            engine_alive = _engine_pid_alive(run_dir)
            if first_tick:
                # Startup: the engine may not hold RunLock yet. Assume alive
                # on the very first pass so a fresh auto-spawn never exits
                # out from under a just-starting engine.
                idle_ticks = 0
                first_tick = False
            elif not open_orders and not engine_alive:
                idle_ticks += 1
            else:
                idle_ticks = 0
            if idle_ticks and time.time() - started > DISPATCH_EXIT_GRACE_S:
                print(f"[dispatcher {worker_id}] no open work orders and engine pid dead "
                      f"({idle_ticks} idle ticks) -- exiting", flush=True)
                return
            try:
                results = sweep_run_dir(run_dir, worker_id=worker_id, max_workers=workers)
            except Exception as exc:  # noqa: BLE001 -- a sweep failure must never kill the watch loop
                print(f"[dispatcher {worker_id}] sweep error: {exc!r}", flush=True)
                results = []
            for r in results:
                print(f"[dispatcher {worker_id}] {r.phase_id}: {r.status} "
                      f"(attempts={r.attempts})" + (f" target={r.target}" if r.target else "")
                      + (f" reasons={r.reasons}" if r.status in ("exhausted", "error", "declined")
                         else ""), flush=True)
            # PRES-017: heartbeat refresh every tick -- last claim, last work
            # progress, outstanding orders, active units. An ALIVE process
            # that never claims/progresses is distinguishable from a healthy
            # one by comparing heartbeat fields, not by pid presence.
            _write_heartbeat(
                open_orders=open_orders,
                last_claim=(results[0].phase_id if results else last_claim_phase),
                last_progress=(f"{results[0].phase_id}:{results[0].status}"
                               if results else last_progress_note),
                active_units=len(results))
            last_claim_phase = results[0].phase_id if results else last_claim_phase
            last_progress_note = (f"{results[0].phase_id}:{results[0].status}"
                                  if results else last_progress_note)
            time.sleep(interval)
    finally:
        _release_own_autospawn_lock(run_dir)


def watch_scan_root(scan_root: Path, *, interval: float = SWEEP_INTERVAL_S,
                    max_lifetime_s: float = 24 * 3600,
                    max_workers: Optional[int] = None) -> None:
    worker_id = f"dispatcher-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    started = time.time()
    print(f"[dispatcher {worker_id}] watching all runs under {scan_root}", flush=True)
    while time.time() - started <= max_lifetime_s:
        run_dirs = [p.parent for p in scan_root.glob("*/state.json")]
        for run_dir in run_dirs:
            if _run_terminal(run_dir) is not None:
                continue
            # FIX 9: a run with open work orders and a dead engine pid is
            # exactly what this scan-root watcher EXISTS for -- it sweeps
            # stranded runs an --run-dir watcher can no longer see. Only a
            # run with nothing open and no engine skips its sweep.
            if not _open_work_orders(run_dir) and not _engine_pid_alive(run_dir):
                continue
            scripts_dir = resolve_scripts_dir_for_run(run_dir)
            dept_root = resolve_dept_root(scripts_dir)
            workers = resolve_max_workers(dept_root, max_workers)
            try:
                results = sweep_run_dir(run_dir, worker_id=worker_id, max_workers=workers)
            except Exception as exc:  # noqa: BLE001
                print(f"[dispatcher {worker_id}] {run_dir}: sweep error: {exc!r}", flush=True)
                continue
            for r in results:
                print(f"[dispatcher {worker_id}] {run_dir.name}/{r.phase_id}: {r.status} "
                      f"(attempts={r.attempts})", flush=True)
        time.sleep(interval)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
# F11: mode-specific --watch lifetime ceilings. --run-dir is ONE run's companion
# process and must outlive the run (measured: 22 h); --scan-root is a periodic
# sweeper across many runs and keeps the old 6 h ceiling.
RUN_DIR_MAX_LIFETIME_MINUTES = 1440.0
SCAN_ROOT_MAX_LIFETIME_MINUTES = 360.0


def resolve_max_lifetime_minutes(explicit: Optional[float], *, run_dir_mode: bool) -> float:
    """The ceiling actually used by main(). An explicitly passed flag always
    wins; otherwise the mode's own default applies."""
    if explicit is not None:
        return float(explicit)
    return RUN_DIR_MAX_LIFETIME_MINUTES if run_dir_mode else SCAN_ROOT_MAX_LIFETIME_MINUTES


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="work_order_dispatcher.py",
        description="Consumes working/work-orders/<phase>.json, authors the phase's real "
                    "artifact via DeepSeek V4 Flash direct (or honestly declines), and "
                    "verifies with the SAME phase_verifiers.verify() the Engine uses. "
                    "Never marks a phase done; never touches state.json.")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--run-dir", type=Path, help="dispatch work orders for ONE run")
    g.add_argument("--scan-root", type=Path,
                   help="dispatch work orders for EVERY run dir under this root")
    m = p.add_mutually_exclusive_group()
    m.add_argument("--once", action="store_true", help="one sweep, then exit")
    m.add_argument("--watch", action="store_true",
                   help="sweep repeatedly until the run's terminal is set (--run-dir) or "
                        "--max-lifetime-minutes elapses (--scan-root). Default mode.")
    p.add_argument("--interval", type=float, default=SWEEP_INTERVAL_S,
                   help=f"seconds between sweeps (default {SWEEP_INTERVAL_S})")
    p.add_argument("--max-workers", type=int, default=None,
                   help="cap concurrent DeepSeek dispatches this process runs; default "
                        "resolves from capacity.py's probe() -- the DETECTED tier "
                        "(no capacity_override.json is fabricated; --declare-capacity "
                        "writes one explicitly)")
    # F11 (2026-09-06): the --run-dir default was 360 (6 h) while MEASURED runs
    # last 22 hours, so the dispatcher servicing a long deck died roughly two
    # thirds of the way through it and every agent phase queued afterwards
    # burned its FULL budget producing nothing. 1440 (24 h) covers the measured
    # envelope; --scan-root keeps 360 because that mode is a periodic sweeper,
    # not the single companion process of one run. Explicitly passing the flag
    # still wins in both modes -- see RUN_DIR_MAX_LIFETIME_MINUTES /
    # SCAN_ROOT_MAX_LIFETIME_MINUTES and main()'s resolution below.
    p.add_argument("--max-lifetime-minutes", type=float, default=None,
                   help="safety ceiling on how long --watch runs before exiting on its own "
                        f"(default {RUN_DIR_MAX_LIFETIME_MINUTES:.0f} = 24h for --run-dir, "
                        f"{SCAN_ROOT_MAX_LIFETIME_MINUTES:.0f} = 6h for --scan-root)")
    p.add_argument("--declare-capacity", type=int, default=None,
                   help="idempotently declare max_concurrent=N FOR ONE PROVIDER in "
                        "capacity_override.json if the file does not already exist "
                        "(never overwrites an existing declaration). The provider comes "
                        "from --declare-provider, else from capacity.detect(); if none "
                        "can be established this REFUSES with exit 2 rather than writing "
                        "a record that PARKs the run")
    p.add_argument("--declare-provider", default=None,
                   help="the provider --declare-capacity is about (e.g. ollama-cloud, "
                        "deepseek-direct, openrouter). F4: this used to be hard-coded to "
                        "deepseek-direct, which PARKS every run since deepseek-direct "
                        "joined the structural cap table on 2026-09-04")
    p.add_argument("--declare-plan", default=None,
                   help="the plan tier of --declare-provider (e.g. v4-flash, $100/month) "
                        "when this box's detection and resource profile do not already "
                        "know it. A structural cap-table provider declared with no plan "
                        "PARKS the run, so --declare-capacity refuses instead")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    watch = args.watch or not args.once  # --watch is the default mode

    if args.run_dir:
        run_dir = args.run_dir.expanduser().resolve()
        scripts_dir = resolve_scripts_dir_for_run(run_dir)
        dept_root = resolve_dept_root(scripts_dir)
        # FIX 6: the override file is written only when an operator explicitly
        # passes --declare-capacity (or by the detection/interview flow); the
        # unconditional auto-stamp is gone so capacity.probe() reports the
        # DETECTED tier instead of a fabricated deepseek-direct/100.
        if args.declare_capacity is not None:
            try:
                ensure_capacity_override(dept_root,
                                         max_concurrent=args.declare_capacity,
                                         provider=args.declare_provider,
                                         plan=args.declare_plan)
            except CapacityDeclarationRefused as exc:
                # Exit 2, nothing written. A capacity declaration nobody can
                # attribute to a provider is not a narrower answer -- it is a
                # WRONG one, and it would PARK the run it was meant to widen.
                print(f"ERROR: {exc}", file=sys.stderr, flush=True)
                return 2
        workers = resolve_max_workers(dept_root, args.max_workers)
        if not watch:
            worker_id = f"dispatcher-{os.getpid()}-{uuid.uuid4().hex[:8]}"
            results = sweep_run_dir(run_dir, worker_id=worker_id, max_workers=workers)
            for r in results:
                print(f"[dispatcher] {r.phase_id}: {r.status} (attempts={r.attempts})"
                      + (f" reasons={r.reasons}" if r.reasons else ""), flush=True)
            return 0
        watch_run_dir(run_dir, interval=args.interval,
                     max_lifetime_s=resolve_max_lifetime_minutes(
                         args.max_lifetime_minutes, run_dir_mode=True) * 60,
                     max_workers=workers)
        return 0

    scan_root = args.scan_root.expanduser().resolve()
    if not watch:
        worker_id = f"dispatcher-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        run_dirs = [p.parent for p in scan_root.glob("*/state.json")]
        for run_dir in run_dirs:
            scripts_dir = resolve_scripts_dir_for_run(run_dir)
            dept_root = resolve_dept_root(scripts_dir)
            workers = resolve_max_workers(dept_root, args.max_workers)
            results = sweep_run_dir(run_dir, worker_id=worker_id, max_workers=workers)
            for r in results:
                print(f"[dispatcher] {run_dir.name}/{r.phase_id}: {r.status} "
                      f"(attempts={r.attempts})", flush=True)
        return 0
    watch_scan_root(scan_root, interval=args.interval,
                    max_lifetime_s=resolve_max_lifetime_minutes(
                        args.max_lifetime_minutes, run_dir_mode=False) * 60,
                    max_workers=args.max_workers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
