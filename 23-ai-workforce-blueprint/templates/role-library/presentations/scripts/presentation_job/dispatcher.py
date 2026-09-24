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
import contextlib
import fcntl
import functools
import hashlib
import inspect
import json
import os
import re
import shutil
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
from presentation_job import autospawn as _autospawn  # noqa: E402  PD-TEST-080
from presentation_job import heal as _heal  # noqa: E402
from presentation_job import contract_introspect as _ci  # noqa: E402
from presentation_job import execution_stamp as _estamp  # noqa: E402  PRES-042
from presentation_job import fanout  # noqa: E402  -- PARALLEL-PIPELINE-SPEC Ticket 4
# PD-TEST-067: the ONE reader for the deck's slide-array shape, shared with
# fanout, build_deck and craft_judgement. json/pathlib/typing only -- no cycle.
from presentation_job import arc_slides as _arc_slides  # noqa: E402
# PRES-014 (W2 WF05): durable fan-out unit records. Banked results are read
# and validated BEFORE any model call; only failed/changed units resubmit;
# the attempt/budget ledger survives restarts (append-only transitions +
# atomic state.json, never truncated by any code path here).
try:
    from presentation_job import unit_store  # noqa: E402
except ImportError:  # pragma: no cover - pre-PRES-014 trees keep old behavior
    unit_store = None  # type: ignore[assignment]

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
# PD-TEST-124 -- THE BOUNDED TOTAL PAID BUDGET OF A FAN-OUT PHASE.
#
# THE DEFECT. `paid_attempts` is a PHASE counter compared against
# DISPATCH_RETRY_CAP, with no per-unit accounting at all. A fan-out phase
# therefore has ONE three-attempt allowance shared by every unit, and the first
# unit to fail repeatedly spends it. Measured on P4-COPY (8 units):
# section-01 recorded completion_tokens=64000, finish_reason='length', empty
# output; it then exhausted the phase allowance, and section-02..section-08
# each died on `PaidBudgetExhausted: paid retry budget exhausted: 3 provider
# attempts for unchanged approved input` WITHOUT EVER BEING ATTEMPTED. Seven
# units did not fail -- they never ran -- and the phase quarantined having
# authored nothing. Sibling starvation, not unit failure.
#
# THE POLICY IMPLEMENTED HERE (declared once, recorded in the phase ledger as
# `phase_paid_budget`, and enforced by _reserve_paid_attempt):
#
#   1. ONE FUNDED FIRST ATTEMPT PER ELIGIBLE UNIT, and first attempts have
#      ABSOLUTE PRIORITY: while any admitted unit still has zero paid attempts,
#      no unit may reserve a second or third (PaidAttemptDeferred). One unit's
#      retries can therefore never again preempt a sibling's first attempt.
#
#   2. THE TOTAL IS BOUNDED AND EXPLICIT, never `units x DISPATCH_RETRY_CAP`:
#
#          total_cap = min(PHASE_TOTAL_PAID_HARD_CAP,
#                          eligible_units * FANOUT_FIRST_ATTEMPT_RESERVE_PER_UNIT
#                          + PHASE_RETRY_POOL_ATTEMPTS)
#
#      i.e. one attempt per unit plus the SAME phase-level retry allowance
#      (DISPATCH_RETRY_CAP = 3) this module has always granted -- reused, not
#      multiplied. For the measured 8-unit P4-COPY phase that is 8 + 3 = 11,
#      not 8 * 3 = 24. Within one generation the declared total NEVER shrinks
#      (a later declaration with fewer pending units re-uses the larger bound),
#      so a sweep that banks successes never strands the units still owed work.
#
#   3. DISPATCH_RETRY_CAP IS THE PER-UNIT CEILING for one unchanged approved
#      input -- the same number, now applied per unit instead of per phase. No
#      existing cap is weakened: the phase-level total only ever GROWS to fund
#      the first attempts the old counter could never pay for, and a serial
#      (non-fan-out) phase keeps the legacy phase-level cap byte-for-byte.
#
#   4. CANNOT-FUND-ALL BEHAVIOUR. When the total cap cannot fund every
#      eligible unit's first attempt (eligible_units > total_cap), the first
#      `total_cap` units in DETERMINISTIC ENUMERATION ORDER are admitted and
#      every remaining unit is recorded in `unit_not_admitted` with a
#      machine-readable reason, named in the sidecar, and refused at
#      reservation time. No unit is ever silently dropped: the phase reports
#      exactly how many units the bound could not fund, and which.
#
#   5. SUCCESSES ARE NEVER REGENERATED. A unit whose durable outcome is ok is
#      refused a reservation outright (PD-TEST-124 requirement 4), and a unit
#      whose valid on-disk output is still bound to the current inputs is
#      REUSED without any reservation at all (see _reusable_unit_output).
#
#   6. RESERVATIONS ARE ATOMIC AND DUPLICATE-SAFE. Every reservation happens
#      inside the phase's existing `_phase_budget_transaction` flock, in one
#      read-modify-write, and carries the logical attempt's token. A duplicate
#      call for a token already charged is a no-op (idempotent), and a second
#      logical attempt for a unit that already has an in-flight reservation is
#      refused unless the reserving process is gone (pid-liveness takeover,
#      the same idiom the claim code uses). Concurrent workers cannot
#      double-reserve one unit's attempt.
#
#   7. NOTHING IS RESET. Per-unit counters are durable and generation-scoped
#      exactly like the phase counter they sit beside: a new approved-input
#      generation (verified intake amendment, or a consumed repair receipt)
#      starts a fresh per-unit count, and `unit_paid_attempts_lifetime` keeps
#      the never-reset audit total. A restart, a re-sweep and a re-issued work
#      order preserve successes, reservations and failure history.
# ---------------------------------------------------------------------------
FANOUT_FIRST_ATTEMPT_RESERVE_PER_UNIT = 1
# The legacy phase-level retry allowance, reused as the fan-out RETRY POOL.
# Deliberately DISPATCH_RETRY_CAP and not a second number (spec S7.1).
PHASE_RETRY_POOL_ATTEMPTS = DISPATCH_RETRY_CAP
# An explicit, finite ceiling on any single phase's total paid attempts, no
# matter how many units a manifest enumerates. The shipped manifest's widest
# fan-out is a per-slide QC phase over a >=100-slide deck (100 + 3 = 103), so
# 128 funds every shipped phase's first attempts plus the retry pool while
# keeping the bound a declared constant rather than an emergent product.
PHASE_TOTAL_PAID_HARD_CAP = 128
# The one-line policy string recorded in every fan-out ledger this module
# writes, so an operator reading the ledger sees the rule that produced the
# numbers beside it.
PHASE_PAID_BUDGET_POLICY = (
    "bounded-total-first-attempt-fair-v1: one funded first attempt per eligible "
    "unit in deterministic order, then a phase retry pool of "
    f"{PHASE_RETRY_POOL_ATTEMPTS}; total = min({PHASE_TOTAL_PAID_HARD_CAP}, "
    f"units*{FANOUT_FIRST_ATTEMPT_RESERVE_PER_UNIT} + {PHASE_RETRY_POOL_ATTEMPTS}); "
    f"per-unit ceiling {DISPATCH_RETRY_CAP}; no success is ever regenerated")

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
# DeepSeek Direct V4.1 Flash -- confirmed live configuration (openclaw.json models.providers.deepseek id deepseek-flash),
# never hardcoded from documentation guesswork. Base URL / model id / api
# shape read from models.providers.deepseek; "thinking MAX" request fields
# (`thinking.type=enabled` + `reasoning_effort=max`) are the EXACT fields
# deepseek-v4-pro already carries in this box's own agents.defaults.models
# params block for the sibling model on the SAME native endpoint -- proven
# live (not guessed) with a real smoketest call against deepseek-flash
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
# deepseek-flash's real 393,216-token output ceiling (live openclaw.json maxTokens, 2026-09-11), and
# gives a large structured artifact (deep choreography JSON, 60+ slides of copy)
# room to complete even after thinking-MAX spends heavily on reasoning first.
DEEPSEEK_MAX_OUTPUT_TOKENS = 64_000
# PD-TEST-124 (2026-09-16): do NOT raise this again to "fix" an empty
# completion. The bounded experiment measured `medium` finishing at 15.3% of
# this ceiling while `max` consumed 100.0% of the BYTE-IDENTICAL request -- the
# effort, not the budget, was binding. Raising it a fourth time would buy
# nothing and cost more. See DEEPSEEK_REASONING_EFFORT below.
# PD-TEST-065 (2026-09-15). The reasoning effort is a REQUEST parameter, not a
# buried literal.
#
# PD-TEST-124 (2026-09-16) -- HARNESS DECLARATION vs PRODUCT WORKER.
# `max` is what this box's openclaw.json declares for the HARNESS agent
# (agents.defaults.models["deepseek/deepseek-flash"].params.reasoning_effort =
# "max"). That declaration governs the harness agent's own interactive turns.
# It does NOT govern THIS module. This dispatcher is a PRODUCT worker that
# sends ONE very large authoring prompt (P4-COPY's real section prompt measured
# 155,379 chars = 38,365 prompt tokens) and the endpoint bills reasoning INSIDE
# max_tokens (confirmed live above). On that workload `max` is not a quality
# setting, it is a runaway: four independent live sends of the byte-identical
# P4-COPY section-01 request at max_tokens=64,000 returned
# completion_tokens=64,000, reasoning_tokens=64,000, ZERO-length `content` and
# finish_reason="length" -- 100% of the deliverable budget spent thinking, none
# left to deliver. Raising the ceiling does not fix it (8,000 -> 32,000 ->
# 64,000 each filled; see this constant's history above): reasoning expands to
# consume whatever ceiling it is given, so the ceiling was never the binding
# constraint.
#
# PD-TEST-124 BOUNDED EXPERIMENT (2026-09-16). ONE real prompt, the captured
# production request body BYTE-IDENTICAL (sha256 a2cc393fd4dc1a91...), same
# endpoint / model / temperature / max_tokens=64,000; ONLY the documented
# request control varied (4 paid calls, every response schema-validated by this
# module's own _validate_copy_section):
#   reasoning_effort="max"     reasoning 64,000 (100.0% of budget)  content
#                              ZERO  finish_reason="length"  308.2s  -- FAIL
#   reasoning_effort="medium"  reasoning  9,788 ( 15.3% of budget)  content
#                              1,494 chars  finish_reason="stop"  49.1s  -- PASS
#   reasoning_effort="low"     reasoning 13,445 ( 21.0% of budget)  content
#                              1,063 chars  finish_reason="stop"  62.2s  -- PASS
#   thinking.type="disabled"   reasoning      0                    content
#                              1,297 chars  finish_reason="stop"   3.4s  -- PASS
#                              (DIAGNOSTIC ONLY -- not a production candidate;
#                              it removes thinking altogether, which no
#                              incident asked for. Recorded to bound the
#                              mechanism, not to be shipped.)
# Every PASS carried all 7 required per-slide fields. The decisive number is
# that `medium` terminates at 15.3% of the SAME 64,000 ceiling that `max`
# exhausts -- the EFFORT was binding, never the budget. This also refutes the
# tempting reading of the tiny "Reply with the single word OK" probe (max=23
# vs none=25 reasoning tokens): a 256-token probe is not the 38k-token
# authoring regime, and it cannot show the difference that this test does.
#
# `medium` is the default, NOT `low`: it is the cheapest of the two
# thinking-enabled settings that work (9,788 vs 13,445 reasoning tokens), it is
# a documented enum member (resource_profile.THINKING_LEVELS and
# api-docs.deepseek.com/guides/thinking_mode), and it is the same step-down
# this box already used successfully on 2026-08-26/27 before it was lost.
# Honest limit of the evidence: `low` spent MORE reasoning tokens than `medium`
# here, so the ladder below is a change of REQUEST, not a strict monotonic
# reduction in thinking.
DEEPSEEK_REASONING_EFFORT = "medium"
#: What the operator's openclaw.json declares, recorded so the divergence above
#: is EXPLICIT and auditable rather than silent. The product worker sends
#: DEEPSEEK_REASONING_EFFORT; the harness agent keeps the operator's
#: declaration. The two are deliberately allowed to differ because `max`
#: demonstrably returns ZERO-LENGTH content on this worker's prompt size, so
#: the harness declaration cannot govern the worker's own authoring calls.
#: Nothing in this module writes openclaw.json.
DEEPSEEK_REASONING_EFFORT_DECLARED_BY_OPERATOR = "max"
# A re-attempt for a unit that has ALREADY come back empty is re-issued at the
# reduced effort instead of repeating a request that just failed. This is the
# FIRST rung of the ladder below and must always differ from
# DEEPSEEK_REASONING_EFFORT -- otherwise the "retry" re-sends the exact request
# that just failed and can only burn another paid call. (Before PD-TEST-124
# this was "medium" and the default was "max"; the default moved DOWN to
# medium, so the step-down moved down with it.)
DEEPSEEK_REASONING_EFFORT_AFTER_EMPTY = "low"
# PD-070 (2026-09-15). A LADDER, not a single step. `medium` is a documented
# ALIAS for `high` on this endpoint (api-docs.deepseek.com/guides/thinking_mode:
# "`medium`/`xhigh` are accepted and mapped to `high`"), and `high` is the
# model's own DEFAULT effort -- so a "max -> medium" step lands on the model
# default and then DEAD-ENDS: a second, third and fourth empty completion all
# re-send that same effort. Each rung here must therefore be a request that has
# NOT just failed.
# PD-TEST-124 (2026-09-16): with the default now `medium`, rung 0 is `low` --
# a genuine step DOWN from what attempt 1 sends, and a setting the bounded
# experiment above measured returning valid content with finish_reason="stop".
# The ladder is deliberately SHORT: no documented value below `low` keeps
# thinking ENABLED ("none" disables it, and mixing that with
# thinking.type="enabled" has undocumented precedence -- so it is NOT a rung
# until probed), and inventing an unmeasured rung would re-create PD-070's
# dead-end defect from the other direction.
#
# HONEST BOUND, stated here because a comment that overclaims is how PD-070
# happened: the rung index in `effort_for_paid_attempt` is CLAMPED to the last
# rung, so a unit whose attempt allowance outlives the ladder re-sends the
# FINAL rung on every later attempt rather than stepping further down. With this
# one-rung ladder, attempt 2 and attempt 3 both send `low`: attempt 3 is a
# RESAMPLE at DEEPSEEK_TEMPERATURE, not a fresh step-down. The property a test
# may assert is therefore only that attempt 2 DIFFERS from attempt 1 -- NOT that
# no attempt ever repeats the rung that just failed. A unit that exhausts the
# ladder parks on the phase's paid-attempt cap, which is the correct fail-closed
# outcome rather than an unbounded series of paid calls.
DEEPSEEK_REASONING_EFFORT_LADDER: Tuple[str, ...] = ("low",)
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
_FAILING_STATUSES = frozenset({"error", "exhausted", "declined",
                               "partial_failure"})  # PRES-014: some-units-failed

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
        "price-ladder beats and a re-pitch after the FINAL beat. "
        "PITCHLESS VOCABULARY IS NOT OPTIONAL TO AVOID (PD-TEST-132). `build_deck."
        "_chk_pitch_leak` is a RENDER GATE that scans this file for a fixed token list, so "
        "on a pitch_included:false deck the artifact is refused for the WORDS it uses, "
        "including words used to record that the content is absent. The exact suppressed "
        "tokens are enumerated at the END of this contract, read out of the gate itself at "
        "import time, so that list is complete and cannot drift. Name a felt-stakes section "
        "by WHAT IT DOES for this audience (for example 'what-carrying-it-alone-costs', "
        "'the-hidden-cost-of-waiting', 'status-quo-cost') rather than by a suppressed sale "
        "mechanic. State the pitchless decision itself PLAINLY -- 'this deck carries no "
        "commercial offer' -- and do not enumerate the mechanics you are omitting, because "
        "listing them trips the same scan."
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
        "OUTPUT CONTRACT -- FIRST read intake.json's explicit pitch_included selection. "
        "When it is false for a non-signature deck, commercial ARC beats (VILLAIN, "
        "FELT_STAKES, NAMED_METHOD, EXPECTATION and PRICE) are not applicable and must "
        "not be fabricated. Missing/malformed selection is AF-PITCH-APPLICABILITY-UNSET; "
        "a signature deck with pitch_included:false is AF-PITCH-APPLICABILITY-CONFLICT. "
        "TWO SEPARATE CHECKERS otherwise grade this ONE file, by TWO DIFFERENT mechanisms, "
        "and BOTH must show zero problems:\n"
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
        "APPLICABILITY GATE FOR POINTS 8, 9 AND 12 (PD-TEST-125 D2). Read "
        "intake.json's pitch_included FIRST. When it is FALSE for a non-signature "
        "deck, points 8, 9 and 12 DO NOT APPLY: write NO price rung, NO re-pitch "
        "and NO `<!-- ARC: COST_OF_INACTION -->` marker, and no prose naming the "
        "cost of inaction. This is not a style preference -- `build_deck."
        "_chk_pitch_leak` refuses the deck with AF-PITCH-LEAK when a pitchless deck "
        "carries those tokens, so following points 8/9 on a pitchless deck "
        "GUARANTEES a QC failure you cannot write your way out of. Measured live on "
        "pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4: the contract ordered "
        "`<!-- ARC: COST_OF_INACTION -->`, the copy carried it verbatim at "
        "slides_copy.md:23-24, and AF-PITCH-LEAK fired on exactly that token. When "
        "pitch_included is false the whole price/pitch apparatus is inapplicable; "
        "points 1-7 and 10-11 still apply, under their own applicability rules.\n"
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
        "OUTPUT CONTRACT: valid JSON object at working/copy/sp_claims.json that records the "
        "presentation_type and deck_type ALREADY declared in working/copy/intake.json. If and "
        "only if that sealed intake declares signature_presentation, record a signature claim; "
        "otherwise record a non-signature routing result. Never change intake.json, never upgrade "
        "a from_scratch deck to signature, and never infer commercial/pitch requirements."
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
# PD-TEST-098 -- THE DESIGN-PAGE PROMPT BAND IS A *SHARED* BUDGET.
#
# THE DEFECT. P-U-DESIGN-SALES / -CHECKOUT / -VSL are three-unit fan-outs
# (`fanout.by: slide`, `desired_count: 3`, PIPELINE-MANIFEST.json v69) whose
# reducer CONCATENATES the three unit outputs into ONE artifact
# (`prompts/<page>.design.txt`, `_reduce_text_concat`), and the consuming
# render phase (`build_infographic.resolve_design_prompt`) sends that ONE
# artifact VERBATIM to GPT-Image-2.5 as ONE prompt behind the shared gate at
# `prompt_gate.PROMPT_CHAR_FLOOR .. PROMPT_CHAR_CEILING`.
#
# Nothing in the producer knew any of that. All three phases had NO entry in
# ARTIFACT_CONTRACTS, so `compose_prompt` fell through to GENERIC_CONTRACT,
# whose entire length rule is "real prose long enough to be substantive (not
# a one-line stub)" -- there was no upper bound anywhere on the authoring
# path. The owning role's SOP states the 9,000-14,000 band PER PROMPT, and
# each of the three units reasonably spent that budget on ITSELF, so three
# individually in-band prompts concatenated to 49,526-58,484 chars against an
# 18,000 ceiling. Measured live on run
# pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4: sales unit outputs
# 20,917 + 20,024 + 17,537 = 58,478, plus the 4 separator chars
# `_reduce_text_concat` inserts = the 58,484-char file the gate refused.
# Every one of those units PASSED its validator -- `_validate_text` refused
# nothing but emptiness -- so the ceiling was discovered three phases later,
# at the paid render gate, instead of here.
#
# THE FIX. The band is stated to the units as what it actually is -- a budget
# on the FINAL AGGREGATE artifact, shared across the phase's N units -- and
# each unit is told its own share of it. The numbers are IMPORTED from
# `prompt_gate`, the same module the gate itself raises from, so the
# authoring target and the gate cannot drift; there is deliberately no second
# copy of 9,000/18,000 in this file to drift from. The separator arithmetic
# mirrors `_reduce_text_concat` through the ONE shared separator constant
# below, so the budget and the reducer can never disagree either.
#
# NO MANIFEST CHANGE IS REQUIRED. `fanout.desired_count: 3` + one declared
# artifact + the concat reducer + the aggregate ceiling are mutually
# satisfiable: three units each authoring ONE PART of the one prompt, inside
# their share of the one budget, sum to an artifact that clears the gate.
# ---------------------------------------------------------------------------
DESIGN_PAGE_PHASES: Dict[str, str] = {
    "P-U-DESIGN-SALES": "sales",
    "P-U-DESIGN-CHECKOUT": "checkout",
    "P-U-DESIGN-VSL": "vsl",
}

# The ONE separator `_reduce_text_concat` joins unit texts with. The shared
# budget arithmetic below charges for it, so a change here can never silently
# put the reducer's real output over the ceiling the units were given.
_UNIT_TEXT_SEPARATOR = "\n\n"


def _shared_prompt_gate():
    """The shared prompt gate module (`prompt_gate.py`, at the top of
    scripts/ -- already on sys.path via this module's own bootstrap).

    FAIL CLOSED, deliberately: a design unit that cannot be told the band is
    a design unit authoring blind against a gate that will refuse it, which is
    the exact defect above. Refusing the phase here costs nothing; authoring
    without a ceiling costs three paid units and a parked render phase."""
    try:
        import prompt_gate  # noqa: PLC0415 -- lazy: never a hard import at module scope
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "PD-TEST-098: prompt_gate.py could not be imported, so the "
            "design-page prompt band cannot be stated to the authoring unit. "
            "Refusing to author a design prompt blind against the shared "
            f"gate ({type(exc).__name__}: {exc}).") from exc
    return prompt_gate


def design_unit_char_budget(unit_count: int) -> Tuple[int, int]:
    """`(floor_share, ceiling_share)` -- the character budget for ONE unit of
    a design-page fan-out, derived from the SHARED band.

    The gate measures the FINAL artifact: N unit texts joined by
    `_UNIT_TEXT_SEPARATOR` (2 chars each, N-1 of them). So the aggregate is
    `sum(u) + 2*(N-1)`, and each unit's fair share is the band minus the
    separators, divided N ways. Both bounds are imported from `prompt_gate`
    -- never re-typed here.

    A degenerate/absent `unit_count` is treated as ONE unit (the whole band),
    which is the honest reading for a phase that enumerated a single unit."""
    pg = _shared_prompt_gate()
    n = unit_count if isinstance(unit_count, int) and unit_count > 0 else 1
    sep_total = len(_UNIT_TEXT_SEPARATOR) * (n - 1)
    ceiling_share = max(1, (pg.PROMPT_CHAR_CEILING - sep_total) // n)
    floor_share = -(-max(0, pg.PROMPT_CHAR_FLOOR - sep_total) // n)  # ceil
    return floor_share, min(ceiling_share, pg.PROMPT_CHAR_CEILING)


def design_part_count(payload: Dict[str, Any]) -> int:
    """How many parts the design-page artifact is ACTUALLY assembled from.

    `admitted_count` (stamped by the dispatcher from `wanted_items`) is the
    authority -- it is the number of parts `_reduce_text_concat` will join.
    `unit_count` is only the ENUMERATED count and over-counts whenever
    `fanout.desired_count` bounded the phase (live run P-U-DESIGN-SALES:
    enumerated 8, admitted 3), so it is a last-resort fallback for direct
    callers that never went through the dispatcher's admission pass."""
    payload = payload if isinstance(payload, dict) else {}
    for key in ("admitted_count", "unit_count"):
        val = payload.get(key)
        if isinstance(val, int) and val > 0:
            return val
    return 1


def _design_page_prompt_contract(phase_id: str, order: Dict[str, Any]) -> str:
    """The OUTPUT CONTRACT a P-U-DESIGN-* unit is dispatched with.

    Replaces the GENERIC_CONTRACT fallthrough that let this defect through.
    States, in the model's own instruction and with numbers imported from the
    gate: that the file is ONE prompt for ONE rendered image, that the band
    applies to the AGGREGATE and is therefore SHARED across the phase's
    units, which part this unit is, and the exact character share it owns."""
    page = DESIGN_PAGE_PHASES.get(phase_id, "page")
    payload = order.get("_unit_payload") if isinstance(order, dict) else None
    payload = payload if isinstance(payload, dict) else {}
    n = design_part_count(payload)
    ordinal = payload.get("ordinal")
    if not isinstance(ordinal, int) or not (1 <= ordinal <= n):
        ordinal = 1
    floor_share, ceiling_share = design_unit_char_budget(n)
    pg = _shared_prompt_gate()
    # Aim at the MIDDLE of the share so a compliant part clears both bounds
    # with real headroom; the shares themselves stay the hard bounds the
    # validator enforces.
    target_lo = floor_share + (ceiling_share - floor_share) // 4
    target_hi = floor_share + (3 * (ceiling_share - floor_share)) // 4

    if n > 1:
        attribution = (
            f"1. YOU ARE AUTHORING PART {ordinal} OF {n} OF ONE SINGLE PROMPT, "
            f"NOT A PROMPT OF YOUR OWN. `prompts/{page}.design.txt` is ONE "
            f"image prompt, sent VERBATIM to GPT-Image-2.5 to render ONE 16:9 "
            f"page-design image. The engine authors it in {n} parts "
            f"concurrently and joins them in ordinal order with a blank line. "
            f"Part 1 opens the prompt: it carries the ONE `[ARCHETYPE ...]` "
            f"layout header, the ONE canvas/format/resolution declaration, the "
            f"background, and the brand palette. Every later part CONTINUES "
            f"that same prompt: no second `[ARCHETYPE` header, no second "
            f"canvas/frame/resolution declaration, no restart. Part {n} closes "
            f"it with the ONE `DO-NOT BLOCK` negative block.\n")
    else:
        attribution = (
            f"1. YOU ARE AUTHORING THE WHOLE PROMPT. "
            f"`prompts/{page}.design.txt` is ONE image prompt, sent VERBATIM to "
            f"GPT-Image-2.5 to render ONE 16:9 page-design image. It carries "
            f"exactly ONE `[ARCHETYPE ...]` layout header, ONE "
            f"canvas/format/resolution declaration, and closes with the ONE "
            f"`DO-NOT BLOCK` negative block.\n")

    # PD-TEST-113: the AF-P13 defect classes and their tolerant tokens are read
    # from prompt_gate at call time, exactly as the band numbers are. The
    # producer must be told every rule its consumer enforces, or each unstated
    # rule costs one full paid re-author and one quarantined render phase to
    # discover (measured: AF-P13 and AF-R3 on run
    # pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4). Importing the map
    # rather than retyping it means a class added to the gate reaches the
    # contract with no second edit.
    defect_classes = sorted(pg.NEGATIVE_BLOCK_CLASS_TOKENS.items())
    return (
        f"OUTPUT CONTRACT: author `prompts/{page}.design.txt` -- the page-design "
        f"prompt for the {page.upper()} upsell page. This contract is "
        f"mechanically graded BEFORE any paid image call; a violation is refused "
        f"by `build_infographic.resolve_design_prompt` via the shared "
        f"`prompt_gate`, and the render phase is NOT submitted.\n"
        + attribution +
        f"2. LENGTH -- THE BAND IS SHARED, AND IT IS MEASURED ON THE FINAL "
        f"ASSEMBLED FILE, NOT ON YOUR PART. The shared gate requires the "
        f"complete `prompts/{page}.design.txt` to be between "
        f"{pg.PROMPT_CHAR_FLOOR:,} and {pg.PROMPT_CHAR_CEILING:,} characters "
        f"({pg.PROMPT_CHAR_CEILING:,} sits 2,000 under the "
        f"{pg.API_PROMPT_HARD_CEILING:,}-character GPT-Image-2.5 API ceiling). "
        f"Your part is {ordinal} of {n}, so YOUR OWN OUTPUT MUST BE BETWEEN "
        f"{floor_share:,} AND {ceiling_share:,} CHARACTERS -- aim for "
        f"{target_lo:,}-{target_hi:,}. The {n} parts plus their separators sum "
        f"to the file, so a part written at full single-prompt length is what "
        f"puts the file over the ceiling and gets the whole phase refused. Do "
        f"NOT pad to reach a number: this is a MAXIMUM to respect, and every "
        f"character must still be real, specific art direction.\n"
        f"3. REQUIRED STRUCTURAL BLOCKS -- the assembled file must contain all "
        f"three (case-insensitive): a layout header starting `[ARCHETYPE`; a "
        f"final block headed exactly `DO-NOT BLOCK`; and at least one literal "
        f"`Do not ` imperative inside that block. They are required ONCE each "
        f"across the whole file -- see point 1 for which part carries each.\n"
        f"3a. THE `DO-NOT BLOCK` MUST NAME ALL {len(defect_classes)} DEFECT "
        f"CLASSES (AF-P13). A one-line 'no text' AVOID stub does NOT satisfy "
        f"it. Pair EVERY class with an explicit `Do not ...` imperative, using "
        f"the wording in brackets so the mechanical check can see it: "
        + "; ".join(f"{name} [{', '.join(tokens[:4])}]"
                    for name, tokens in defect_classes)
        + ".\n"
        f"3b. NEVER hardcode a demographic default (AF-R3): no fixed "
        f"percentage split and no baked-in representation mix. State that "
        f"skin-tone and representation follow the client's captured audience / "
        f"casting ledger. The gate matches the forbidden 'default <group>' "
        f"phrasing LITERALLY, so never write that two-word form -- the "
        f"assembled file is refused before any paid call if you do.\n"
        f"4. DENSITY: the assembled file needs at least "
        f"{pg.PROMPT_MIN_DISTINCT_WORDS} DISTINCT words, a brand palette color "
        f"as a 6-digit `#RRGGBB` HEX code, an explicit typography SIZE token "
        f"(e.g. '96pt'), and a real COMPOSITION/zone instruction (e.g. 'rule of "
        f"thirds', 'left third', 'safe margin', 'negative space') -- "
        f"'centered' alone does NOT count.\n"
        f"5. SPELLING-LOCK: quote every on-slide string VERBATIM, "
        f"letter-for-letter, and say so ('render every quoted text string "
        f"exactly as written, letter-for-letter').\n"
        f"6. Output ONLY this part's prompt text -- no preamble, no commentary, "
        f"no markdown code fence around the answer, no file header, no restated "
        f"work order."
    )


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


def _module_str_sequence(module: str, name: str) -> List[str]:
    """Read a module-level list/tuple of string literals out of source by AST.

    DERIVED, never re-typed: a hand-copied rule list is what drifts
    (contract_introspect.py), and the hand-copied version of the suppressed-token
    list written first for PD-TEST-132 missed 3 of the gate's 26 variants. Fails
    soft to [] so a read failure can never block a dispatch.
    """
    try:
        node = _ci._module_level_assigns(module).get(name)
        if node is None or type(node).__name__ not in ("Tuple", "List"):
            return []
        out: List[str] = []
        for elt in getattr(node, "elts", []):
            text = _ci.literal_text(elt)
            if text:
                out.append(text)
        return out
    except Exception:  # noqa: BLE001 -- a derivation failure must never block a dispatch
        return []


def _compose_p3_arc_contract(base: str) -> str:
    """Name, in the P3-ARC contract, the rules its own artifact is judged by (PD-TEST-132).

    P3-ARC writes working/copy/arc_allocation.json. Two separate checkers grade that
    file and NEITHER rule was in this contract, so the author wrote blind and the run
    paid for it one re-author at a time:

      * AF-NO-VILLAIN -- the arc MUST carry a named antagonist beat. Measured on run
        pres-operator-1d269693: the arc has 8 sections and ZERO antagonist vocabulary,
        so P4-COPY failed the substance check with "no VILLAIN/antagonist beat anywhere
        in the arc". P4-COPY's own contract DOES name that rule (the derived index
        covers it) -- but P4-COPY does not own the arc and cannot repair it, so naming
        the rule downstream only produced a phase that blocks on an artifact it cannot
        fix. The rule belongs where the artifact is authored.
      * AF-PITCH-LEAK -- on a pitch_included:false deck the arc is refused for the
        suppressed vocabulary. All 11 recognised antagonist tokens are pitchless-SAFE
        (zero overlap with the forbidden 26), so the deck is satisfiable; the author
        was simply never told which words are closed to it.
    """
    tokens = _module_str_sequence("build_deck", "PITCHLESS_FORBIDDEN_TOKENS")
    villain = _module_str_sequence("intelligence_engines_check", "VILLAIN_TOKENS")
    safe_villain = [v for v in villain
                    if not any(f in v.lower() or v.lower() in f for f in tokens)]
    out = base
    if safe_villain:
        out += (
            " MANDATORY VILLAIN BEAT (AF-NO-VILLAIN, graded on THIS artifact). The arc "
            "MUST contain a named antagonist beat -- the thing standing between this "
            "audience and the outcome -- placed BEFORE the solution/hero beat. An arc "
            "with no named antagonist fails the substance check and blocks P4-COPY, "
            "which cannot repair an artifact it does not own. Recognised antagonist "
            "vocabulary, read at import time from "
            "intelligence_engines_check.VILLAIN_TOKENS: "
            + "; ".join(safe_villain)
            + "."
        )
    else:
        out += (
            " MANDATORY VILLAIN BEAT (AF-NO-VILLAIN, graded on THIS artifact). The arc "
            "MUST contain a named antagonist beat before the solution/hero beat. An arc "
            "with no named antagonist fails the substance check and blocks P4-COPY."
        )
    if tokens:
        out += (
            " SUPPRESSED TOKENS -- read at import time from "
            "build_deck.PITCHLESS_FORBIDDEN_TOKENS, the very tuple `_chk_pitch_leak` "
            "scans for, so this list is complete and cannot drift. None of these "
            f"{len(tokens)} tokens may appear in ANY string value of the artifact on a "
            "pitch_included:false deck (the scan reads values, not keys, and skips "
            "*_reason / *_note / validation_notes): "
            + "; ".join(tokens)
            + "."
        )
    return out


ARTIFACT_CONTRACTS["P3-ARC"] = _compose_p3_arc_contract(ARTIFACT_CONTRACTS["P3-ARC"])


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
                      retries: int = 3,
                      reasoning_effort: Optional[str] = None) -> Tuple[str, Dict[str, Any]]:
    """One DeepSeek chat completion, thinking MAX. Returns
    (content_text, usage_dict). FIX 16: the caller passes the model the ROUTE
    selected (default stays the catalog text.fast id so the pre-FIX-7
    rollback path is byte-for-byte unchanged). Retries transient
    HTTP/network failures with backoff; a non-transient (4xx other than 429)
    failure raises immediately.

    PD-TEST-065: `reasoning_effort` defaults to DEEPSEEK_REASONING_EFFORT.
    PD-TEST-124: that default is now "medium" (a measured-working effort for
    this worker's very large authoring prompts), NOT the operator's declared
    "max" -- see the DEEPSEEK_REASONING_EFFORT comment for the evidence and for
    why the product worker is entitled to differ from the harness declaration.
    A caller may still step it DOWN for a call whose identical predecessor
    already returned empty content -- see
    DEEPSEEK_REASONING_EFFORT_AFTER_EMPTY."""
    key = _load_deepseek_key()
    effort = reasoning_effort or DEEPSEEK_REASONING_EFFORT
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
        "reasoning_effort": effort,
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
                # PD-070: keep the provider's OWN stop signal alongside the
                # usage. `finish_reason="length"` is the documented marker that
                # the request's token maximum was reached; with thinking enabled
                # that maximum is SHARED with reasoning, so "length" + an empty
                # `content` means reasoning starved the deliverable -- a
                # different defect from a model that answered nothing ("stop" +
                # empty), needing a different fix. Before this the field was
                # read nowhere at all (grep -c finish_reason dispatcher.py == 0),
                # so the two were indistinguishable after the fact.
                if isinstance(usage, dict):
                    usage["finish_reason"] = choice.get("finish_reason")
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
                      worker_id: Optional[str] = None,
                      max_tokens: int = DEEPSEEK_MAX_OUTPUT_TOKENS,
                      retries: int = 3,
                      route_override: Optional[Dict[str, Any]] = None,
                      reasoning_effort: Optional[str] = None,
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
    itself already marked eligible. See _apply_route_override.

    PD-TEST-065: `reasoning_effort` (optional) is forwarded to the native
    DeepSeek transport only. PD-TEST-124: None now sends
    DEEPSEEK_REASONING_EFFORT ("medium", measured working on this worker's real
    authoring prompt), NOT the operator's declared "max" -- see that constant's
    comment for the four-call evidence and for why the product worker is
    entitled to differ from the harness declaration. A caller steps it DOWN
    only when the identical predecessor call already returned empty content. A
    non-native provider route ignores it -- that provider's own params
    govern."""
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
                or "deepseek-flash"
            ctx.reason = str((decision or {}).get("reason")
                             or "no profile route; dispatcher default DeepSeek-direct")
            _reserve_paid_attempt(run_dir, phase_id, worker_id)
            content, usage = deepseek_complete(system_prompt, user_prompt,
                                               model=ctx.model, run_dir=run_dir,
                                               max_tokens=max_tokens, retries=1,
                                               reasoning_effort=reasoning_effort)
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
            _reserve_paid_attempt(run_dir, phase_id, worker_id)
            content, usage = deepseek_complete(system_prompt, user_prompt,
                                               model=ctx.model, run_dir=run_dir,
                                               max_tokens=max_tokens, retries=1,
                                               reasoning_effort=reasoning_effort)
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
            _reserve_paid_attempt(run_dir, phase_id, worker_id)
            content, usage = deepseek_complete(system_prompt, user_prompt,
                                               model=ctx.model, run_dir=run_dir,
                                               max_tokens=max_tokens, retries=1,
                                               reasoning_effort=reasoning_effort)
            # usage/model provenance stays honest even though the native endpoint
            # pins its own served id; FIX 16 now sends the ROUTE's model id in the
            # request body itself (the route is what callers stamp AND what is sent).
            _emit_model_route_telemetry(run_dir, ctx, phase_id)
            return content, usage, ctx.as_dict()

        _reserve_paid_attempt(run_dir, phase_id, worker_id)
        content, usage = _openai_compat_complete(
            system_prompt, user_prompt, provider=ctx.provider, model=ctx.model,
            max_tokens=max_tokens, retries=1, run_dir=run_dir)
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


# PRES-031: phase -> task_mode for persona section selection. Copy, prompt,
# speech, page/VSL and QC units each receive the tier-2 governance sections
# (rationale, task personas, guardrails); unknown phases default to copy
# (the richest governance tier -- fail toward more governance, never less).
_PERSONA_TASK_MODE_BY_PHASE = {
    "P4-COPY": "copy",
    "P-SP-STRUCTURE": "copy",
    "P-SP-P3-HYGIENE": "copy",
    "P4-PROMPT": "prompt",
    "P-PROMPT-QC": "qc",
    "P1Q-COPY-QC": "qc",
    "P-SHIFT-QC": "qc",
    "P-SPEECH-QC": "qc",
    "P-TYPO-QC": "qc",
    "P-QC-AGGREGATE": "qc",
    "P-U-QC": "qc",
    "P9-SPEECH": "speech",
    "P9-SPEECH-WEBINAR-INTRO": "speech",
    "P7-TELEPROMPTER": "speech",
    "P-U-SALES-COPY": "page",
    "P-U-CHECKOUT-COPY": "page",
    "P-U-VSL-COPY": "vsl",
    "P-U-VSL-RESEARCH": "vsl",
    "P-U-SALES-BUILD": "page",
    "P-U-CHECKOUT-BUILD": "page",
    "P-U-VSL-BUILD": "vsl",
    "P-U-HTML-SALES": "page",
    "P-U-HTML-CHECKOUT": "page",
    "P-U-HTML-VSL": "vsl",
}


def _persona_task_mode(phase_id: str,
                       order: Optional[Dict[str, Any]] = None) -> str:
    mode = _PERSONA_TASK_MODE_BY_PHASE.get(phase_id)
    if mode:
        return mode
    if isinstance(order, dict):
        hint = str(order.get("task_mode") or order.get("mode") or "")
        if hint.strip().lower() in ("copy", "prompt", "speech", "page",
                                    "vsl", "qc", "render"):
            return hint.strip().lower()
    return "copy"


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
    elif phase_id in DESIGN_PAGE_PHASES:
        # PD-TEST-098: derived PER UNIT, because the band is a SHARED budget
        # and the unit's own share depends on how many units this phase
        # enumerated (`unit_count` rides the unit payload). Without this the
        # three design phases fell through to GENERIC_CONTRACT, which states
        # no upper bound at all -- see the PD-TEST-098 block above.
        contract = _design_page_prompt_contract(phase_id, order)
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
        # PRES-031: schema-validated section selection replaces the arbitrary
        # 8000-character slice. The COMPLETE bundle is cached by scoped
        # input/context hash (persona_context); this unit receives the
        # task-mode sections it needs. Required governance rules are never
        # dropped silently: an incomplete selection FAILS CLOSED here (loud
        # preflight error naming the missing rules) instead of shipping a
        # truncated voice to the model.
        from presentation_job import persona_context as _persona_context
        _task_mode = _persona_task_mode(phase_id, order)
        _selection = _persona_context.select_bundle_sections(
            persona_bundle, phase_id=phase_id, task_mode=_task_mode)
        if not _selection.get("complete"):
            raise RoleSOPNotFound(
                f"AF-PERSONA-GOVERNANCE: persona bundle for phase "
                f"{phase_id} is incomplete for task_mode={_task_mode}: "
                f"{_selection.get('why')}. Missing schema: "
                f"{_selection.get('missing_schema') or []}; missing "
                f"governance markers: "
                f"{_selection.get('missing_markers') or []}. Restructure "
                f"context (budget {_selection.get('budget')}) -- never ship "
                f"a silently-truncated governing voice.")
        system_parts.append(
            "=== GOVERNING BLENDED-PERSONA VOICE (already resolved by the engine for this "
            "phase -- write IN this voice, do not re-resolve or contradict it) ===\n"
            + _selection["text"]
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
    # PRES-001 (W2 WF05): a fan-out UNIT's work order carries `_unit_scope` --
    # the one-scope instruction built from its validated payload. When present,
    # the generic whole-artifact trigger ("Write the complete, final content of
    # the target artifact file") is REPLACED, not appended to: that tail is what
    # made every unit a whole-deck author (the whole-artifact instruction must
    # never ride into a unit prompt). The unit contract's scoped output schema
    # plus the one-scope instruction are the LAST thing the unit reads.
    unit_scope = order.get("_unit_scope") if isinstance(order, dict) else None
    if unit_scope:
        payload = order.get("_unit_payload") if isinstance(order, dict) else None
        if isinstance(payload, dict) and payload.get("output_schema"):
            schema_line = (f"UNIT OUTPUT SCHEMA (validated mechanically after you "
                           f"answer -- out-of-schema output is a FAILED unit): "
                           f"{payload['output_schema']}\n")
        else:
            schema_line = ""
        user_parts.append(unit_scope + schema_line +
                          "Produce ONLY this one unit's output now. Output ONLY the unit "
                          "content itself (no surrounding prose, no code fence, no file "
                          "header). Never the whole file, never another unit's scope."
        )
    else:
        declared = order.get("produces_artifact") if isinstance(order, dict) else None
        if isinstance(declared, list) and len(declared) > 1 and all(
                isinstance(path, str) and path and not any(c in path for c in "*?[")
                for path in declared):
            paths = ", ".join(json.dumps(path) for path in declared)
            user_parts.append(
                "This phase has MULTIPLE declared artifacts. Output ONE JSON object with exactly "
                "one top-level key, `artifacts`. Its value must map EACH of these exact manifest-"
                f"relative paths to that file's complete content: {paths}. No other keys, paths, "
                "or prose. The value for a .json target must itself be valid JSON text; the value "
                "for a Markdown/text target must be the complete substantive file text."
            )
        else:
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


def _concrete_target_paths(patterns: List[str], run_dir: Path) -> Optional[List[Path]]:
    """Resolve every declared output only when each is a literal safe path.

    A completion is one transport payload, so a phase with sibling artifacts
    must use the explicit envelope contract below.  Globs remain the domain of
    their dedicated fan-out dispatchers: guessing a second filename would
    create an artifact the manifest never declared.
    """
    root = run_dir.resolve()
    targets: List[Path] = []
    seen: set[Path] = set()
    for pattern in patterns:
        if not isinstance(pattern, str) or not pattern or any(c in pattern for c in "*?["):
            return None
        raw = Path(pattern)
        if raw.is_absolute() or ".." in raw.parts:
            return None
        target = (root / raw).resolve(strict=False)
        try:
            target.relative_to(root)
        except ValueError:
            return None
        if target in seen:
            return None
        seen.add(target)
        targets.append(target)
    return targets or None


def _multi_artifact_payload(payload: str, targets: List[Path], run_dir: Path) -> Tuple[Optional[Dict[Path, str]], Optional[str]]:
    """Parse the only accepted model format for a multi-output phase.

    The keys are manifest-relative target paths, not basenames, so similarly
    named artifacts cannot be swapped.  Every declared target is required and
    no undeclared path may be smuggled into the run directory.
    """
    try:
        root = json.loads(payload)
    except json.JSONDecodeError as exc:
        return None, f"multi-artifact response is not JSON: {exc.msg}"
    artifacts = root.get("artifacts") if isinstance(root, dict) else None
    if not isinstance(artifacts, dict):
        return None, "multi-artifact response needs an artifacts object"
    root_dir = run_dir.resolve()
    expected = {str(target.relative_to(root_dir)) for target in targets}
    actual = set(artifacts)
    if actual != expected:
        return None, ("multi-artifact response keys must exactly equal declared targets; "
                      f"missing={sorted(expected - actual)!r} extra={sorted(actual - expected)!r}")
    resolved: Dict[Path, str] = {}
    for target in targets:
        value = artifacts[str(target.relative_to(root_dir))]
        if not isinstance(value, str) or not value.strip():
            return None, f"multi-artifact response has empty/non-text content for {target.relative_to(root_dir)}"
        resolved[target] = value
    return resolved, None


def _publish_artifact_group(tmp_paths: Dict[Path, Path]) -> Optional[str]:
    """Publish sibling outputs as a recoverable group.

    ``os.replace`` is atomic per path, not across paths.  Copy prior outputs
    beside their targets before publication so a failure on a later sibling
    restores every already-replaced target; a target that did not exist is
    removed.  The caller still performs the ownership fence before entering
    this function.
    """
    backups: Dict[Path, Optional[Path]] = {}
    published: List[Path] = []
    try:
        for output in tmp_paths:
            if output.exists():
                backup = output.with_name(output.name + f".publish-backup-{uuid.uuid4().hex}")
                shutil.copy2(output, backup)
                backups[output] = backup
            else:
                backups[output] = None
        for output, tmp in tmp_paths.items():
            os.replace(tmp, output)
            published.append(output)
    except OSError as exc:
        rollback_errors: List[str] = []
        for output in reversed(published):
            backup = backups.get(output)
            try:
                if backup is None:
                    output.unlink(missing_ok=True)
                else:
                    shutil.copy2(backup, output)
            except OSError as rollback_exc:
                rollback_errors.append(f"{output.name}: {rollback_exc}")
        for tmp in tmp_paths.values():
            tmp.unlink(missing_ok=True)
        for backup in backups.values():
            if backup is not None:
                backup.unlink(missing_ok=True)
        detail = f"multi-artifact publication failed: {exc}"
        if rollback_errors:
            detail += "; rollback failures: " + "; ".join(rollback_errors)
        return detail
    for backup in backups.values():
        if backup is not None:
            backup.unlink(missing_ok=True)
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
    yet (the phase is not ready to dispatch).

    PD-TEST-067: those two sources are now read by ``arc_slides`` -- the ONE
    module that knows the deck's slide-array shape -- so this function, the
    fan-out enumerator and the real verifier cannot drift apart again. The
    live run's arc_allocation.json carried its 8 slides under the P3-ARC
    spelling ``slide_allocations``/``slide_number``, which this function's
    private key list could not see; it returned None for a present, complete
    artifact, and the two P4-PROMPT callers below turn that None into a
    status="error" -- the same byte-identical repeat that parked four phases.
    The None contract itself is UNCHANGED.
    """
    return _arc_slides.load_slide_count(run_dir)


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
                    run_dir=run_dir, worker_id=worker_id)
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
# deepseek-direct / deepseek-flash / measured capacity 8 until FIX 7/8/11
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
    # PRES-015 (H-P1): the width path carries ZERO discovery. A stamp that
    # used to run probe() would, pre-split, fire GET /models for every
    # probeable provider as a side effect. probe() itself no longer does
    # (include_inventory defaults False); passing include_inventory=False
    # here would be redundant on a build that knows the kwarg, but the
    # explicit kwarg keeps the invariant legible at the ONE call site a
    # future edit could "fix" back into a discovery burst.
    if _probe_accepts(probe_fn, "include_inventory"):
        kwargs["include_inventory"] = False
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
            # it over is what lets a deepseek-flash route be answered
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

    # ------------------------------------------------------------------
    # PRES-015 EFFECTIVE ADMISSION -- the hardware/warmup fold.
    #
    # Spec step 1: "Effective new admissions = min(ready work, requested
    # ceiling minus total active, account free permits, rate/token budget,
    # cost allocation, class-specific hardware budget)". The mode cap above
    # is the human-ratified axis; THIS fold adds the terms the engine never
    # had -- the account ceiling the reserve/allocation split produced
    # (capacity.account_factors), the class-specific LOCAL hardware budget
    # (hardware_budget.py: Mac RAM/CPU vs Linux cgroup v1/v2 so a 2GB
    # Hostinger container never inherits the host's RAM) and the warmup ramp
    # (admission.py: conservative start, grow on healthy windows, shrink on
    # 429/pressure). Every term is optional: an unmeasured term does not
    # bind, so a box where hardware cannot be read answers exactly what the
    # pre-PRES-015 stamp answered -- the rollback is a flag
    # (PRESENTATION_ADMISSION=0), never a behaviour change by accident.
    #
    # THE TEXT-CLASS GUARANTEE: cheap cloud text I/O is class "text" here
    # unless the phase is known local-heavy, and the text class carries NO
    # RAM term -- so an Ultra 100-unit text fan-out still reaches 100 where
    # host resources allow, and render/browser/local-model routes get their
    # own (smaller) budget without a hidden global 8 ever coming back.
    try:
        _stamp_admission_fold(stamp, phase_id=phase_id, mode=_mode,
                              run_dir=run_dir)
    except Exception as adm_exc:  # noqa: BLE001 -- admission never breaks dispatch
        stamp["admission_error"] = f"{type(adm_exc).__name__}: {adm_exc}"
    return stamp


# ---------------------------------------------------------------------------
# PRES-015 -- the per-phase work class and the admission fold itself.
# ---------------------------------------------------------------------------
#: Phase -> local work class. The names follow hardware_budget.CLASSES:
#: "text" (cheap cloud I/O), "image" (decode/generation), "browser"
#: (headless sessions), "render" (FFmpeg/renderer), "local_model"
#: (local inference resident in RAM). Anything not named is "text" -- the
#: least-harmful default, and the cloud routes are the majority.
PHASE_WORK_CLASS: Dict[str, str] = {
    # Manifest script-executor phases: LOCAL bytes on this box (Kie image
    # download/decode, reportlab/FFmpeg assembly, headless OCR sessions).
    "P-STYLE-PREVIEW": "image",
    "P4-RENDER": "render",
    "P8-ASSEMBLE": "render",
    "P8.1-PDF-EXPORT": "render",
    "P9.6-WEBINAR-VIDEO": "render",
    # P-IMAGE-QC / P-TYPO-QC are deliberately NOT here: the engine runs them
    # as cloud vision/OCR model calls (model_router capability vision_ocr ->
    # glm-ocr over HTTPS) -- cheap text I/O locally, class "text" by default.
    # A phase that gains a LOCAL headless-browser or render step joins this
    # map when that step exists, never before.
}

def _phase_work_class(phase_id: str) -> str:
    return PHASE_WORK_CLASS.get(phase_id, "text")

def _stamp_admission_fold(stamp, *, phase_id: str,
                          mode: str, run_dir=None) -> None:
    """Fold admission.effective_width() into the stamp's measured_capacity.

    Never raises on its own paths (the caller also guards). Zero discovery:
    the ONLY capacity read is resolve_capacity() -- no probe_one_provider,
    no GET /models -- and the hardware read is the cached snapshot (at most
    one measurement per TTL, shared by every phase's stamp in this
    process)."""
    try:
        from presentation_job import admission as _adm
    except ImportError:  # pragma: no cover - direct-file run
        try:
            import admission as _adm  # type: ignore[no-redef]
        except ImportError:
            return
    if not _adm.flag_enabled():
        return
    provider = str(stamp.get("provider") or "")
    if not provider:
        return
    width = stamp.get("measured_capacity")
    try:
        width = int(width)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return
    if width < 1:
        return

    # The account factors resolve_capacity computes for THIS route -- a
    # probe about a different provider was refused before this point, so
    # the factors that matter are the routed provider's.
    factors = {}
    account_ceiling = None
    _cap_mod = None
    try:
        from presentation_job import capacity as _cap_mod_p
        _cap_mod = _cap_mod_p
    except ImportError:  # pragma: no cover - direct-file run
        try:
            import capacity as _cap_mod_p  # type: ignore[no-redef]
            _cap_mod = _cap_mod_p
        except ImportError:
            _cap_mod = None
    if _cap_mod is not None:
        try:
            resolved = _cap_mod.resolve_capacity(
                provider=provider, model=str(stamp.get("model") or ""))
            factors = resolved.get("account_factors") or {}
            account_ceiling = factors.get("account_ceiling")
            stamp["account_factors"] = factors
            stamp["capacity_raw_available"] = resolved.get("available")
        except Exception:  # noqa: BLE001 -- an unresolvable account never blocks
            factors, account_ceiling = {}, None

    work_class = _phase_work_class(phase_id)
    # UNBOUNDED accounts (BYOK): no account term binds; the mode ceiling and
    # the class hardware budget are the only local bounds.
    try:
        _unbounded = bool(_cap_mod is not None
                          and _cap_mod.is_unbounded(
                              stamp.get("capacity_raw_available")))
    except Exception:  # noqa: BLE001
        _unbounded = False
    adm = _adm.effective_width(
        width,
        provider=provider,
        ready_work=None,  # the caller (fanout) bounds by the ready unit count
        mode_ceiling=width if _unbounded else None,
        account_ceiling=account_ceiling,
        work_class=work_class,
    )
    stamp["admission"] = {
        "width": adm.get("width"),
        "static_width": adm.get("static_width"),
        "binding": adm.get("binding"),
        "terms": adm.get("terms"),
        "ramp": adm.get("ramp"),
        "work_class": work_class,
        "discovery_requests": 0,
    }
    if isinstance(adm.get("width"), int) and 1 <= int(adm["width"]) <= width:
        stamp["measured_capacity"] = int(adm["width"])
        if int(adm["width"]) < width:
            stamp["capacity_status"] = \
                f"{stamp.get('capacity_status')}+admission-folded"

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
    # PD-TEST-161: DECLARE this fan-out's bounded total BEFORE any paid call, so
    # the prompt wave is funded the same way the copy fan-out has been since
    # PD-TEST-124. `_declare_phase_paid_budget` is the single writer of
    # `phase_paid_budget`, and `_effective_phase_paid_cap` returns the declared
    # bound when one exists (else the legacy DISPATCH_RETRY_CAP, byte-for-byte).
    # Each slide's own attempt is then accounted under its `slide_id` by the
    # `paid_unit_scope` the worker enters per attempt.
    #
    # Strictly fail-soft: a declaration failure must not stop the wave. The
    # ledger then simply stays undeclared and the legacy per-phase cap governs,
    # which is exactly the pre-fix behaviour -- the sidecar records which
    # happened so the difference is never silent.
    try:
        # PD-TEST-166 (review of PR #1164): declare only the slides that still
        # need PAID work -- a slide whose prompt is already on disk and clears
        # the real per-slide gate costs nothing, and `_declare_phase_paid_budget`
        # says so in its own contract: banked/reused units must be EXCLUDED,
        # "because they cost nothing, so funding them would only shrink the pool
        # available to the units that do". The first version declared EVERY slide,
        # which (with the settlement PD-TEST-165 adds) would leave already-good
        # slides at counts == 0 while still listed as owed a first attempt.
        #
        # The WAVE itself still processes every slide, so already-good ones are
        # re-derived from disk by `_run_one` as usual -- only the DECLARATION is
        # narrowed to the units that can actually spend.
        _all_keys = [_ppw.prompt_slide_unit_key(_s) for _s in slides_payload]
        _pending_keys = []
        for _s in slides_payload:
            _key = _ppw.prompt_slide_unit_key(_s)
            try:
                _ok, _ = _verify_single_prompt(run_dir, int(_s["ordinal"]))
            except Exception:  # noqa: BLE001 -- unverifiable != already good
                _ok = False
            if not _ok:
                _pending_keys.append(_key)
        # Never declare an EMPTY set: with nothing pending the wave is a no-op
        # anyway, and an empty declaration would rewrite the phase's bound to
        # its `0 units -> 3` floor for no reason.
        _unit_keys = _pending_keys or _all_keys
        _budget_decl = _declare_phase_paid_budget(
            run_dir, phase_id, unit_keys=_unit_keys, worker_id=worker_id)
    except Exception as exc:  # noqa: BLE001 -- the wave still runs undeclared
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0,
            "status": "paid_budget_declaration_failed",
            "reason": f"{type(exc).__name__}: {exc}"[:300],
            "consequence": ("the prompt wave runs on the legacy per-phase cap "
                            "(DISPATCH_RETRY_CAP) exactly as before PD-TEST-161"),
        })
        _budget_decl, _bd = None, {}
    # Review (delta): the AUDIT of a successful declaration gets its OWN guard.
    # Wrapping it in the declaration's try meant a sidecar write failure AFTER a
    # successful declaration recorded "declaration_failed / legacy cap governs"
    # while the ledger in fact held the declaration -- a false record.
    if _budget_decl is not None:
      try:
        # Review F4: `_declare_phase_paid_budget` returns a NESTED document --
        # {"budget": {...}, "admitted": [...], "not_admitted": {...}} -- and the
        # copy caller reads `["budget"]["total_cap"]`. The first version of this
        # sidecar read those keys at top level and therefore recorded nulls.
        _bd = _budget_decl.get("budget") or {}
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0,
            "status": "fanout_paid_budget_declared",
            "policy": _bd.get("policy"),
            "units": len(_unit_keys),
            "units_in_wave": len(_all_keys),
            "units_already_good": len(_all_keys) - len(_pending_keys),
            "units_eligible": _bd.get("units_eligible"),
            "total_cap": _bd.get("total_cap"),
            "units_admitted_first_attempt":
                _bd.get("units_admitted_first_attempt"),
            "units_not_admitted": _bd.get("units_not_admitted"),
        })
        # Review F5: the same explicit cannot-fund-all record the copy path
        # writes, so slides outside the bound are visibly NOT ATTEMPTED rather
        # than silently absent.
        if _bd.get("units_not_admitted"):
            _append_sidecar(run_dir, phase_id, {
                "worker": worker_id, "attempt": 0,
                "status": "paid_budget_cannot_fund_all_units",
                "reason": (f"{_bd.get('units_not_admitted')} of "
                           f"{_bd.get('units_eligible')} eligible slide(s) fall "
                           f"outside the declared bounded total of "
                           f"{_bd.get('total_cap')} paid attempt(s); they were "
                           "NOT attempted (they did not fail). They are named in "
                           "the ledger's phase_paid_budget/unit_not_admitted."),
                "units_not_admitted": sorted(
                    (_budget_decl.get("not_admitted") or {}).keys()),
            })
      except Exception as exc:  # noqa: BLE001 -- an audit failure is not a budget failure
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0,
            "status": "paid_budget_declaration_audit_failed",
            "reason": f"{type(exc).__name__}: {exc}"[:300],
            "note": ("the DECLARATION itself succeeded -- the ledger carries the "
                     "bounded total; only this audit row failed"),
        })
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

    # PD-TEST-165: SETTLE this wave's paid reservations, exactly as the copy
    # fan-out does for every batch (`_settle_unit_paid_attempts`, dispatcher.py).
    #
    # Without this the prompt path had NO settlement at all: a slide's
    # attempt-1 reservation stayed IN FLIGHT in the ledger, and because the wave
    # runs in the dispatcher's own process the unit's own second reservation was
    # refused -- measured by the independent review of PR #1164 on an 8-slide
    # wave: attempts 2-3 ALL resolved as `budget_deferred` and the final row's
    # error class was the refusal rather than what actually failed
    # (verify_failed, HTTP 500). So PD-TEST-161 bought every slide a FIRST
    # attempt and no working retry.
    #
    # `_settle_unit_paid_attempts` marks each reservation settled (a later
    # dispatch may reserve again; a duplicate carrying the same token stays a
    # no-op) and records each unit's durable outcome, which is what the
    # first-attempt-fairness rule reads to decide whether a retry may proceed.
    # Strictly fail-soft: a settlement failure must not fail a wave whose
    # artifacts are already on disk.
    try:
        _outcomes = [
            (str(_r.get("slide_id") or _r.get("ordinal")),
             "ok" if str(_r.get("status")) == "succeeded" else "failed",
             list((_r.get("verify") or {}).get("codes") or []))
            for _r in slide_rows if isinstance(_r, dict)
        ]
        _settle_unit_paid_attempts(run_dir, phase_id, _outcomes,
                                   worker_id=worker_id)
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0,
            "status": "fanout_paid_attempts_settled",
            "units": len(_outcomes),
            "ok": sum(1 for _o in _outcomes if _o[1] == "ok"),
            "failed": sum(1 for _o in _outcomes if _o[1] != "ok"),
        })
    except Exception as exc:  # noqa: BLE001 -- settlement never fails a wave
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0,
            "status": "fanout_paid_settle_failed",
            "reason": f"{type(exc).__name__}: {exc}"[:300],
            "consequence": ("reservations stay in flight, so this wave's units "
                            "cannot reserve again (retries resolve as "
                            "budget_deferred) until the next successful settle"),
        })
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
                run_dir=run_dir, worker_id=worker_id)
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
                    run_dir=run_dir, worker_id=worker_id)
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
    targets = _concrete_target_paths(patterns, run_dir)
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
    target_exists = bool(
        all(path.exists() for path in targets) if targets is not None
        else target is not None and target.exists())
    if ok and target_exists:
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0, "status": "already_satisfied",
        })
        return DispatchResult(phase_id, "skipped_satisfied", 0, [])

    if target is None or (len(patterns) > 1 and targets is None):
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
                worker_id=worker_id,
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
        if targets is not None and len(targets) > 1:
            contents, payload_reason = _multi_artifact_payload(payload, targets, run_dir)
            if contents is None:
                _append_sidecar(run_dir, phase_id, {
                    "worker": worker_id, "attempt": attempt,
                    "status": "invalid_multi_artifact_response", "reason": payload_reason,
                })
                last_reasons = [payload_reason or "invalid multi-artifact response"]
                prior_reasons = last_reasons
                if attempt < DISPATCH_RETRY_CAP:
                    continue
                break
        else:
            contents = {target: payload}
        tmp_paths: Dict[Path, Path] = {}
        for output, content in contents.items():
            output.parent.mkdir(parents=True, exist_ok=True)
            tmp = output.with_suffix(output.suffix + f".partial-{os.getpid()}-{attempt}")
            tmp.write_text(content, encoding="utf-8")
            tmp_paths[output] = tmp
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
                for output, tmp in tmp_paths.items():
                    quarantine = output.with_name(
                        output.name + f".stale-quarantine-{worker_id}")
                    try:
                        tmp.replace(quarantine)
                    except OSError:
                        tmp.unlink(missing_ok=True)
                _append_sidecar(run_dir, phase_id, {
                    "worker": worker_id, "attempt": attempt,
                    "status": "stale_quarantined",
                    "reason": ("claim lost before publication -- single-target "
                               f"output quarantined to {quarantine.name}, not published"),
                })
                return DispatchResult(
                    phase_id, "exhausted", attempt,
                    ["claim lost before publication; output quarantined"])
        publication_error = _publish_artifact_group(tmp_paths)
        if publication_error:
            _append_sidecar(run_dir, phase_id, {
                "worker": worker_id, "attempt": attempt,
                "status": "publication_rolled_back", "reason": publication_error,
            })
            return DispatchResult(phase_id, "error", attempt, [publication_error])

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
            for output in (targets or [target]):
                _stamp_author(run_dir, phase_id, output,
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


# ---------------------------------------------------------------------------
# PRES-001 (W2 WF05) — per-phase UNIT CONTRACTS for the manifest fan-out path.
#
# THE DEFECT (TODO.md PRES-001, reproduced): the generic fan-out path passed
# only `fanout_unit=unit.key` into compose_prompt (the payload — section name,
# slide content, ordinal — was discarded), let compose_prompt's whole-artifact
# OUTPUT CONTRACT ride into every unit prompt ("write the COMPLETE file"), and
# aggregated with `_aggregate_fanout_parts`, which accepted ONE part or
# shallow-merged N JSON dicts (`dict.update` — repeated keys silently lost the
# earlier arrays: two JSON `slides` arrays kept only the second) and REFUSED
# multiple Markdown parts outright. Two correct P4-COPY sections returned None;
# whole-deck duplicate workers both passed validation. The failure modes:
#   * more workers can each author the WHOLE deck (duplicated paid work);
#   * evidence-bearing units (QC verdicts, section copy) overwrite each other.
#
# THE FIX: one UnitContract per fan-out phase, declared ONCE, carrying exactly
# what TODO.md step 1 names — input schema, immutable upstream input hashes,
# scope, expected output schema, per-unit validator, and an exactly-once
# ordered reducer. The dispatch path below uses the contract to:
#   * preflight REJECT incompatible manifest fanout declarations BEFORE any
#     paid call (a phase whose contract lacks a reducer can never fan out);
#   * supply the FULL validated unit.payload (scope + ordinal + slice) in the
#     unit prompt and REPLACE the whole-artifact trigger line with a
#     one-scope instruction (compose_prompt's generic tail is suppressed via
#     the `_unit_scope` work-order key; see compose_prompt);
#   * validate each unit's output against the contract's validator BEFORE the
#     unit may report ok (an invalid unit is a failed unit — never aggregated);
#   * reduce with the contract's OWN reducer — for P4-COPY an ordered
#     exactly-once Markdown reducer (duplicate/missing ordinal => None, never
#     a broken artifact), for QC phases a union-by-stable-slide-id reducer
#     (duplicate or missing slide id => refusal; every unit's verdict row is
#     preserved in the merged report), for P-STYLE-SPEC the bounded A/B/C
#     three-variant builder (explicit variant ids, exactly three, never one
#     per slide). No generic dict.update anywhere.
#
# Deck-wide synthesis/harmonization stays the NEXT phase's job (the manifest
# DAG already orders the consumers); a unit never authors the whole deck.
#
# Rollback: PRESENTATION_UNIT_CONTRACTS=0 restores the pre-PRES-001 behavior
# (legacy _aggregate_fanout_parts + unscoped prompts) exactly.
# ---------------------------------------------------------------------------
UNIT_CONTRACTS_ROLLBACK_FLAG = "PRESENTATION_UNIT_CONTRACTS"

STYLE_SPEC_VARIANT_IDS = ("A", "B", "C")

# Immutable upstream inputs per fan-out phase — the manifest's own consumes[]
# list, restated here as the contract's hash-set so the reducer (and the
# resume-reuse predicate) can prove the run it reduced is the run its stored
# unit outputs were produced against. GLOB patterns are legal: each pattern is
# expanded against the run dir and every match is hashed (see
# unit_input_hashes). Recorded per unit into the units ledger; a changed
# input hash invalidates exactly the units that consume it; downstream
# dependents re-run through the manifest DAG's own edges (PRES-002's gating,
# not this module's).
#
# Source of truth is PIPELINE-MANIFEST.json's own consumes[] per phase (read
# live from the Phase object at dispatch time when available); this static
# table is the byte-identical restatement used when no manifest is loadable.
_UNIT_CONTRACT_INPUTS: Dict[str, Tuple[str, ...]] = {
    "P4-COPY": (
        "working/copy/intake.json",
        "working/copy/arc_allocation.json",
        "working/research/research_map.json",
        "working/research/brief-*.md",
    ),
    "P-PROMPT-QC": ("working/prompts/slide-*.txt",),
    "P-IMAGE-QC": ("renders/slide-*.png",),
    "P-STYLE-SPEC": (
        "working/copy/slides.json",
        "working/copy/arc_allocation.json",
        "working/copy/intake.json",
    ),
    "P-U-DESIGN-SALES": ("working/upsell/copy/sales.fragment.md",),
    "P-U-DESIGN-CHECKOUT": ("working/upsell/copy/checkout.fragment.md",),
    "P-U-DESIGN-VSL": ("working/upsell/copy/vsl.fragment.md",),
    "P9-SPEECH": (
        "working/copy/intake.json",
        "working/copy/slides_copy.md",
        "working/copy/arc_allocation.json",
    ),
}

# What each contract phase's reduce WRITES (the reverse edge of the invalidation
# graph: when phase X's inputs change, the phases consuming X's OUTPUT are the
# transitive dependents whose own stored units are invalidated too).
_UNIT_CONTRACT_OUTPUTS: Dict[str, Tuple[str, ...]] = {
    "P4-COPY": ("working/copy/slides_copy.md",),
    "P-PROMPT-QC": ("working/qc/prompt_qc_report.json",),
    "P-IMAGE-QC": ("working/qc/image_qc_report.json",),
    "P-STYLE-SPEC": ("working/copy/style_preview_spec.json",),
    "P-U-DESIGN-SALES": ("prompts/sales.design.txt",),
    "P-U-DESIGN-CHECKOUT": ("prompts/checkout.design.txt",),
    "P-U-DESIGN-VSL": ("prompts/vsl.design.txt",),
    "P9-SPEECH": ("working/deliverables/PRESENTERS-SPEECH.md",),
}

# The phase->scope binding. P4-COPY is the only SECTION-scoped fan-out (one
# unit per arc section, each authoring its own contiguous slide-ordinal range);
# every other contract phase is slide-scoped (one unit per slide). The
# manifest's own fanout.by MUST agree with this scope or the preflight refuses
# the phase before any paid call (incompatible manifest fanout).
# P9-SPEECH is slide-scoped HERE but its manifest executor is a SCRIPT (the
# speech harness) — the generic unit path never executes for it, and the
# preflight refuses its dead fanout declaration; the contract still declares
# the shape a future agent executor would be held to, and the reducer serves
# any direct call.
_UNIT_CONTRACT_SCOPE: Dict[str, str] = {
    "P4-COPY": "section",
    "P-PROMPT-QC": "slide",
    "P-IMAGE-QC": "slide",
    "P-STYLE-SPEC": "slide",
    "P-U-DESIGN-SALES": "slide",
    "P-U-DESIGN-CHECKOUT": "slide",
    "P-U-DESIGN-VSL": "slide",
    "P9-SPEECH": "slide",
}

# Bounded VARIANTS (not bounded units): the style-spec contract keeps the
# manifest's per-slide enumeration, and the REDUCER enforces the bound the
# TODO names — exactly three desired variants in the reduced spec (the first
# three well-formed candidates, ids forced unique A/B/C), never one spec per
# slide. The unit prompt + validator carry the variant-id assignment so the
# paid work itself is variant-scoped, not deck-scoped.

# Per-phase QC report-envelope labels the union reducer stamps into the merged
# report (mirrors build_deck._qc_report_gate's exact gate strings).
_UNIT_QC_GATE_LABELS: Dict[str, str] = {
    "P-PROMPT-QC": "Phase Prompt-QC",
    "P-IMAGE-QC": "Phase Image-QC",
}

# Expected unit output schema, restated per phase (the one-line shape the
# unit's own output contract block teaches and the validator enforces).
_UNIT_CONTRACT_OUTPUT: Dict[str, str] = {
    "P4-COPY": "markdown-section: `SLIDE <n>` blocks, contiguous ordinals",
    "P-PROMPT-QC": "json: {slide_id, slide, criteria[], average, pass}",
    "P-IMAGE-QC": "json: {slide_id, slide, observed_text, pass}",
    "P-STYLE-SPEC": "json: {id, style_directive, representative_slide} — id is "
        "YOUR ASSIGNED VARIANT ID (A/B/C), style_directive the ONE attention-grade "
        "art-direction sentence for that variant, representative_slide the single "
        "slide ordinal that best shows the variant",
    "P-U-DESIGN-SALES": "text: ONE page-design prompt for the scoped slide",
    "P-U-DESIGN-CHECKOUT": "text: ONE page-design prompt for the scoped slide",
    "P-U-DESIGN-VSL": "text: ONE page-design prompt for the scoped slide",
    "P9-SPEECH": "markdown-section: `SLIDE <n>` blocks, contiguous ordinals",
}


def unit_contracts_enabled() -> bool:
    """PRES-001 roll-forward/rollback switch. Default ON; ==0 restores the
    pre-PRES-001 generic path exactly (documented rollback)."""
    return os.environ.get(UNIT_CONTRACTS_ROLLBACK_FLAG) != "0"


def unit_input_hashes(run_dir: Path, phase_id: str) -> Dict[str, Any]:
    """sha256 of every immutable upstream input the phase's contract names.

    Patterns are expanded against the run dir first (a glob's digest covers
    every matching file, sorted by relative path, so adding/removing/editing
    one slide prompt changes exactly that phase's hash); a literal path is
    hashed directly. Recorded into each unit's ledger row so a resume can
    prove WHICH input version each stored unit output was produced against;
    `unit_inputs_changed` is the predicate that turns a mismatch into a
    scoped re-dispatch of only the affected units (and their dependents)."""
    out: Dict[str, Any] = {}
    for rel in _UNIT_CONTRACT_INPUTS.get(phase_id, ()):
        out[rel] = _hash_contract_entry(run_dir, rel)
    return out


def _hash_contract_entry(run_dir: Path, rel: str) -> str:
    """One contract input's digest: sha256 over (relative path, size, mtime_ns,
    content sha256) of every file the entry names. Glob patterns expand; a
    literal names exactly one file. Absent/unreadable inputs hash to a stable
    sentinel so a later appearance always reads as a change."""
    try:
        if any(c in rel for c in "*?["):
            hits = sorted(run_dir.glob(rel))
            files = [h for h in hits if h.is_file()]
        else:
            p = run_dir / rel
            files = [p] if p.is_file() else []
        if not files:
            return "absent"
        entries = []
        for f in files:
            st = f.stat()
            content_sha = hashlib.sha256(f.read_bytes()).hexdigest()
            entries.append([str(f.relative_to(run_dir)), st.st_size,
                            st.st_mtime_ns, content_sha])
        blob = json.dumps(entries, sort_keys=True).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()
    except OSError:
        return "unreadable"


def unit_inputs_changed(before: Optional[Dict[str, Any]],
                        after: Dict[str, Any]) -> List[str]:
    """Which contract inputs changed between two hash maps. Empty list = the
    recorded unit outputs are still valid against the current inputs."""
    if not isinstance(before, dict):
        return sorted(after)
    return sorted(k for k, v in after.items() if before.get(k) != v)


def invalidated_units(unit_payloads: List[Dict[str, Any]],
                      changed_inputs: List[str]) -> List[str]:
    """Scoped invalidation (PRES-001 acceptance: 'changed source hash
    invalidates ONLY affected units'): the unit keys whose own consumed slice
    a changed input feeds. A per-file change (e.g. one slide's prompt under
    working/prompts/slide-*.txt) invalidates exactly that slide's unit; a
    whole-input change (e.g. intake.json for P4-COPY) invalidates every unit
    of the phase — the honest scope, since every section consumes the intake.

    `changed_inputs` carries the raw contract input patterns that changed;
    the per-unit narrowing reads each unit's own recorded `unit_inputs`
    snapshot (payload['unit_inputs']) when present and compares it against
    the CURRENT hashes recomputed by the caller — precomputed narrowing is
    impossible without the filesystem, so this helper narrows from the
    per-unit hash maps the dispatcher passes in via payload['unit_inputs']
    vs payload['unit_inputs_now']."""
    if not changed_inputs:
        return []
    out: List[str] = []
    for payload in unit_payloads:
        before = payload.get("unit_inputs")
        now = payload.get("unit_inputs_now")
        unit_changed = unit_inputs_changed(
            before if isinstance(before, dict) else None,
            now if isinstance(now, dict) else {k: "changed" for k in changed_inputs})
        if unit_changed:
            out.append(str(payload.get("key") or payload.get("path") or ""))
    return [k for k in out if k]


# ---------------------------------------------------------------------------
# PD-TEST-125 -- DECK-LEVEL ORDERED BEATS MUST BE OWNED BY A NAMED UNIT.
#
# THE DEFECT, measured. Every P4-COPY unit authors EXACTLY ONE SECTION, while the
# writing engines require six DECK-LEVEL beats in a fixed order
# (`intelligence_engines_check.check_narrative_harmony`, whose `beats` list at
# `beats` list is the authority for these names and this order):
#
#     HOOK -> VILLAIN -> FELT_STAKES -> PROMISE -> PRICE -> RECAP
#
# The unit prompt already carried the whole requirement -- a rebuilt unit prompt
# (system 50,954 chars + user 103,895) contains `AF-NO-VILLAIN`, `VILLAIN beat`,
# `<!-- ARC: VILLAIN -->` and the derived constraint index. The producer was told
# and the output still omitted every beat, because the contract states the beats
# as properties of the WHOLE deck ("must be the FIRST slide that carries either
# the VILLAIN prose/marker or the PROMISE prose/marker") and a section-scoped
# author cannot evaluate a whole-deck ordering: it does not know where its section
# sits, nor whether a sibling already claimed the beat. The equilibrium is that NO
# section claims it -- and the artifact showed exactly that: 8 SLIDE markers, all 8
# units `ok`, ZERO villain tokens, and FOUR ARC markers of which one (`<!-- ARC: PROMISE HERO -->`)
# IS a story beat -- so the deck carried PROMISE and still omitted VILLAIN and FELT_STAKES.
#
# THE FIX, and its precedent. PD-TEST-098 hit the identical structure on the design
# phases -- three units author ONE prompt -- and it was fixed by TELLING each unit
# which PART owns which single structural block (part 1 carries the one
# `[ARCHETYPE` header, part N closes with the one `DO-NOT BLOCK`). That assignment
# is what made the design fanout converge. This is the same mechanism: assign each
# ordered deck-level beat to exactly one section, by position, and say so in that
# unit's scope instruction.
#
# WHY BY POSITION. It is deterministic, it distributes the load instead of piling
# every beat on one unit, and because the beats are ordered and the sections are
# ordered it preserves the required HOOK -> ... -> RECAP sequence by construction.
# A section beyond the last beat owns none, which is correct: absence of an
# assignment is not an assignment to duplicate.
# ---------------------------------------------------------------------------
DECK_ORDERED_BEATS: Tuple[str, ...] = (
    "HOOK", "VILLAIN", "FELT_STAKES", "PROMISE", "PRICE", "RECAP",
)

def _deck_commercial_beats_apply(run_dir: Path) -> bool:
    """False only on an EXPLICIT pitchless verdict from the ONE authority.

    `pitch_engines_check.pitch_applicability` returns `(False, None)` for a
    non-signature deck that declares `pitch_included: false`; anything else
    (including a refusal, and including an import that will not load) keeps the
    assignment ON, so a degraded environment behaves exactly as it does today."""
    try:
        import pitch_engines_check as _pec
        applicable, refusal = _pec.pitch_applicability(run_dir)
        return not (applicable is False and refusal is None)
    except Exception:  # noqa: BLE001
        return True


#: Phases whose verifier judges DECK-LEVEL ordered beats. Only the copy fan-out
#: exists today; the set is explicit so a future phase opts IN rather than
#: inheriting an assignment its verifier does not ask for.
DECK_BEAT_PHASES: frozenset = frozenset({"P4-COPY"})


def _owned_beat_clause(payload: Dict[str, Any]) -> str:
    """PD-TEST-125: the beat THIS unit is the sole owner of, or "" when none.

    Absence is deliberate and must be stated as absence-with-reason, or a unit
    that owns no beat may "helpfully" plant one and duplicate a sibling's."""
    if not isinstance(payload, dict):
        return ""
    owned = payload.get("owned_beats")
    if not isinstance(owned, (list, tuple)) or not owned:
        return ""
    arc = " -> ".join(DECK_ORDERED_BEATS)
    return (
        f"=== YOU ARE THE SOLE OWNER OF THIS DECK-LEVEL STORY BEAT: "
        f"{', '.join(str(x) for x in owned)} ===\n"
        f"The deck-level writing engines require SIX ordered beats across the whole "
        f"deck -- {arc} -- and an ordering failure on any one of them refuses the "
        f"assembled copy for the WHOLE deck. Every other section is owned by a "
        f"different unit, so no sibling will plant yours, and you must not plant "
        f"theirs: plant {', '.join(str(x) for x in owned)} in YOUR section, using "
        f"the prose and the literal `<!-- ARC: <BEAT> -->` marker the OUTPUT "
        f"CONTRACT names for it.\n\n")


def _unit_scope_text(payload: Dict[str, Any]) -> Optional[str]:
    return _owned_beat_clause(payload) + (_unit_scope_text_base(payload) or "")


def _unit_scope_text_base(payload: Dict[str, Any]) -> Optional[str]:
    """The ONE-scope instruction a unit worker gets INSTEAD of the generic
    whole-artifact trigger (compose_prompt suppresses its "write the complete
    final content" tail when the work order carries a `_unit_scope` key).

    Names the unit's exact scope — one section, one slide — and forbids
    authoring anything else, replacing the deck-wide trigger that made every
    unit a whole-deck author (the PRES-001 defect's paid-work multiplier)."""
    if not isinstance(payload, dict):
        return None
    scope = payload.get("scope")
    ordinal = payload.get("ordinal")
    # PD-TEST-098: the design phases reuse the by=slide enumerator to get N
    # units, but the artifact is ONE image prompt, not N slide prompts. The
    # generic slide-scope text below ("EXACTLY ONE UNIT: ... for SLIDE 2 OF 8")
    # is what made each design unit author its own COMPLETE prompt for its own
    # deck slide, so three complete prompts were concatenated into one. Say
    # what the unit actually is: one PART of one prompt.
    if isinstance(payload.get("phase_id"), str) \
            and payload["phase_id"] in DESIGN_PAGE_PHASES:
        n = design_part_count(payload)
        page = DESIGN_PAGE_PHASES[payload["phase_id"]]
        if not isinstance(ordinal, int) or not (1 <= ordinal <= n):
            ordinal = 1
        # Name the unit's own slide identity so the part stays anchored to the
        # upstream copy it is responsible for (review nit: the PART-of-ONE
        # rewrite had dropped the slide identity the old slide-scope text
        # carried). Falls back to the unit key when no slide_id was derived.
        _sid = payload.get("slide_id") or payload.get("key") or f"part-{ordinal}"
        return (
            f"=== THIS CALL AUTHORS PART {ordinal} OF {n} OF THE ONE "
            f"{page.upper()} PAGE-DESIGN PROMPT — YOUR SLIDE: {_sid} ===\n"
            f"`prompts/{page}.design.txt` is ONE image prompt rendered as ONE "
            f"16:9 page-design image. You are writing PART {ordinal} of {n}; the "
            f"engine joins the {n} parts, in this order, into that one file. "
            f"Author ONLY your part -- never the whole file, never another "
            f"part's content, no preamble, no file header, no fences around the "
            f"answer, and never a restatement this work order.\n"
            f"The content you are responsible for is the upstream copy for "
            f"{_sid}; render it as art direction INSIDE the one shared prompt "
            f"(see the OUTPUT CONTRACT below for which structural blocks are "
            f"yours and for your exact character share of the shared band).\n\n")
    n = payload.get("unit_count")
    if scope == "section":
        name = payload.get("name")
        lo, hi = payload.get("first_ordinal"), payload.get("last_ordinal")
        range_txt = (f"slides {lo}-{hi}" if isinstance(lo, int)
                     and isinstance(hi, int) else "its own slide range")
        return (
            f"=== THIS CALL AUTHORS EXACTLY ONE SECTION: {name!r} "
            f"(section {ordinal} of {n}) — {range_txt} ===\n"
            "Author ONLY this section's slides as `SLIDE <n>` blocks (the bare "
            "`SLIDE <n>` line starts each block, exactly like the full deck "
            "format), using ONLY the ordinals in this section's slide range. "
            "Output ONLY this one section's Markdown — never the whole deck, "
            "never another section's slides, no preamble, no file header, no "
            "fences around the whole answer.\n\n")
    if scope == "slide":
        kind = payload.get("unit_kind") or "unit"
        variant = payload.get("variant_id")
        variant_line = (f"YOUR ASSIGNED VARIANT ID: {variant} — author that ONE "
                        "variant of the deck-level spec (explicit ids A/B/C, "
                        "bounded three; the deck-level spec carries exactly "
                        "three variants, never one per slide).\n"
                        if variant else "")
        return (
            f"=== THIS CALL IS EXACTLY ONE UNIT: {kind} for SLIDE {ordinal} "
            f"OF {n} ===\n"
            + variant_line +
            "Produce ONLY this one unit's output for ONLY this slide — never "
            "the whole deck, never another slide's content, no preamble, no "
            "fences around the whole answer.\n\n")
    return None


def _extract_slides_copy_section(text: str, payload: Dict[str, Any]) -> Optional[str]:
    """Slice ONE section out of a P4-COPY unit's whole-text response, by the
    slide-ordinal range the scope declared. Returns None when the section's
    own ordinals are absent (the unit ignored its scope — invalid, not
    clipped). Used by the P4-COPY unit validator to accept a model that
    answers with slightly more than its scope while still refusing one that
    answered with nothing from its range (the whole-deck duplicate has every
    range, so scope-obeyance is proven by the VALIDATOR refusing duplicate
    ordinals at reduce time, not by clipping here)."""
    import re as _re
    lo, hi = payload.get("first_ordinal"), payload.get("last_ordinal")
    if not isinstance(lo, int) or not isinstance(hi, int):
        return None
    blocks: List[Tuple[int, str]] = []
    parts = _re.split(r"(?im)^\s*SLIDE\s+(\d+)\s*$", text)
    i = 1
    while i < len(parts) - 1:
        try:
            n = int(parts[i])
        except ValueError:
            i += 2
            continue
        blocks.append((n, parts[i + 1]))
        i += 2
    in_range = [(n, b) for n, b in blocks if lo <= n <= hi]
    if not in_range:
        return None
    return "".join(f"SLIDE {n}\n{b}".rstrip() + "\n" for n, b in in_range)


# --- per-unit validators: (unit payload, cleaned output text) -> (ok, reasons)
def _validate_copy_section(payload: Dict[str, Any], text: str) -> Tuple[bool, List[str]]:
    """P4-COPY unit validator: the output must carry the section's own slide
    blocks as `SLIDE <n>` lines whose ordinals all sit INSIDE the section's
    declared range (lo-hi from the payload `_unit_payload_enrichment` derived
    from arc_allocation.json). A response with NO block in range fails scope
    validation here; a response carrying ANOTHER section's ordinal fails
    out-of-scope here; and two identical whole-deck responses still die at
    REDUCE time on the duplicate ordinals they share. Validated BEFORE a unit
    may report ok — an invalid unit is a failed unit, never aggregated."""
    import re as _re
    lo, hi = payload.get("first_ordinal"), payload.get("last_ordinal")
    if not isinstance(lo, int) or not isinstance(hi, int):
        return False, ["unit payload carries no ordinal range"]
    parts = _re.split(r"(?im)^\s*SLIDE\s+(\d+)\s*$", text)
    ordinals: List[int] = []
    i = 1
    while i < len(parts) - 1:
        try:
            ordinals.append(int(parts[i]))
        except ValueError:
            pass
        i += 2
    if not ordinals:
        return False, ["no `SLIDE <n>` blocks in unit output"]
    in_range = [n for n in ordinals if lo <= n <= hi]
    if not in_range:
        return False, [f"no slide block within the unit's own range "
                       f"{lo}-{hi} — the unit ignored its one-section scope"]
    out_of_scope = sorted({n for n in ordinals if n < lo or n > hi})
    if out_of_scope:
        return False, [f"slide ordinal(s) {out_of_scope} outside the unit's own "
                       f"range {lo}-{hi} — one unit authors ONE section, never "
                       "another section's slides"]
    if len(set(in_range)) != len(in_range):
        return False, ["duplicate slide ordinal inside the unit's own output"]
    return True, []


def _validate_qc_slide(payload: Dict[str, Any], text: str) -> Tuple[bool, List[str]]:
    """QC unit validator (P-PROMPT-QC / P-IMAGE-QC): one JSON object carrying a
    real verdict for EXACTLY the unit's own slide — stable slide_id + ordinal +
    a real pass/fail verdict (+ observed_text for image QC). A whole-deck
    response (slides array / other slides' ids) FAILS validation here, before
    aggregation, per TODO.md's 'two identical whole-deck responses fail unit
    validation'."""
    try:
        doc = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return False, ["QC unit output is not valid JSON"]
    if not isinstance(doc, dict):
        return False, ["QC unit output is not a JSON object"]
    ordinal = payload.get("ordinal")
    expected_id = str(payload.get("slide_id") or "")
    # A WHOLE-DECK response ({"slides":[...]} / {"results":[...]}) is the
    # duplicate-work signature this validator exists to kill: a unit was
    # asked to grade ONE slide and answered with a deck-level report. Refuse
    # the shape outright before any per-field check.
    for deck_key in ("slides", "results", "per_slide", "slide_verdicts"):
        if deck_key in doc:
            return False, [f"QC unit output is a WHOLE-DECK report (carries "
                           f"{deck_key!r}) — one unit grades exactly ONE slide "
                           f"(slide {ordinal}), never the deck"]
    got_ord = doc.get("slide", doc.get("ordinal"))
    if isinstance(got_ord, bool) or not isinstance(got_ord, int):
        return False, ["QC unit output carries no integer slide ordinal"]
    if got_ord != ordinal:
        return False, [f"QC unit graded slide {got_ord}, scope is slide {ordinal} "
                       f"— out-of-scope verdict refused"]
    got_id = str(doc.get("slide_id") or "")
    if expected_id and got_id and got_id != expected_id:
        return False, [f"slide_id {got_id!r} != scope slide_id {expected_id!r}"]
    real = False
    for key in ("pass", "verdict", "score", "status", "result", "grade", "ok",
                "pass_fail", "passed"):
        val = doc.get(key)
        if isinstance(val, bool) or isinstance(val, (int, float)):
            real = True
            break
        if isinstance(val, str) and val.strip():
            real = True
            break
    if not real:
        return False, ["QC unit verdict carries no real pass/fail/score value"]
    if payload.get("needs_observed_text") and \
            not str(doc.get("observed_text") or "").strip():
        return False, ["image-QC unit carries no observed_text (pixel-blind)"]
    return True, []


def _validate_style_variant(payload: Dict[str, Any], text: str) -> Tuple[bool, List[str]]:
    """P-STYLE-SPEC unit validator: one JSON object {id, style_directive,
    representative_slide}; id must be one of the bounded A/B/C variant ids
    (duplicate ids fail at reduce), representative_slide a positive int."""
    try:
        doc = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return False, ["style-spec unit output is not valid JSON"]
    if not isinstance(doc, dict):
        return False, ["style-spec unit output is not a JSON object"]
    directive = str(doc.get("style_directive") or "").strip()
    if not directive:
        return False, ["style_directive is empty"]
    rep = doc.get("representative_slide")
    if isinstance(rep, bool) or not isinstance(rep, int) or rep < 1:
        return False, ["representative_slide must be a positive int"]
    vid = str(doc.get("id") or "").strip().upper()
    if vid and vid not in STYLE_SPEC_VARIANT_IDS:
        return False, [f"variant id {vid!r} outside the bounded A/B/C set"]
    # TODO.md: EXPLICIT variant ids, bounded three. The payload carries the
    # unit's ASSIGNED id; the output must name A/B/C and — when the unit
    # named NO id at all — the assignment fills it at reduce time (the
    # reducer's unique forcing), so an omitted id is a soft miss the
    # assignment repairs, never a silent whole-spec-per-slide.
    if not vid and payload.get("variant_id"):
        return True, []  # repaired by assignment at reduce; reducer forces unique
    return True, []


def _validate_text(payload: Dict[str, Any], text: str) -> Tuple[bool, List[str]]:
    """Design/speech text units: non-empty is the mechanical floor; the phase
    verifier grades substance after aggregation."""
    if not text.strip():
        return False, ["unit output is empty"]
    return True, []


def _validate_design_page_unit(payload: Dict[str, Any],
                               text: str) -> Tuple[bool, List[str]]:
    """PD-TEST-098: a design-page unit must fit ITS SHARE of the shared band.

    The defect this closes: `_validate_text` refused nothing but emptiness, so
    three units at 20,917 / 20,024 / 17,537 chars each reported `ok`, the
    concat reducer wrote a 58,484-char file, and the shared gate refused it
    three phases later at the PAID render call. The unit is where the producer
    can still refuse for free -- so the bound belongs here, not at the gate.

    Bounds come from `design_unit_char_budget` (imported from `prompt_gate`),
    which charges for the separators `_reduce_text_concat` inserts, so a phase
    whose units all pass here cannot assemble an out-of-band file. Both
    directions are checked: over-share units blow the aggregate ceiling, and
    sub-share stubs drop the aggregate under the floor -- the gate refuses
    either one."""
    if not text.strip():
        return False, ["unit output is empty"]
    stripped = text.strip()
    payload = payload if isinstance(payload, dict) else {}
    n = design_part_count(payload)
    floor_share, ceiling_share = design_unit_char_budget(n)
    length = len(stripped)
    problems: List[str] = []
    if length > ceiling_share:
        problems.append(
            f"PD-TEST-098/AF-P2: this unit's part is {length:,} chars, over its "
            f"{ceiling_share:,}-char share of the shared "
            f"{_shared_prompt_gate().PROMPT_CHAR_CEILING:,}-char ceiling. This "
            f"phase authors ONE prompt in {n} parts and the gate measures the "
            f"ASSEMBLED file, so a part written at full single-prompt length "
            f"puts the whole artifact over the ceiling and the render phase is "
            f"refused before any paid call. Tighten redundant phrasing -- never "
            f"delete the negative block or any spelling-lock.")
    if length < floor_share:
        problems.append(
            f"PD-TEST-098/AF-P1: this unit's part is {length:,} chars, under its "
            f"{floor_share:,}-char share of the shared "
            f"{_shared_prompt_gate().PROMPT_CHAR_FLOOR:,}-char floor. The "
            f"assembled file would fall under the gate's hard floor. Expand with "
            f"real, specific art direction -- never boilerplate padding.")
    return (not problems), problems


_UNIT_VALIDATORS: Dict[str, Any] = {
    "P4-COPY": _validate_copy_section,
    "P-PROMPT-QC": _validate_qc_slide,
    "P-IMAGE-QC": _validate_qc_slide,
    "P-STYLE-SPEC": _validate_style_variant,
    "P-U-DESIGN-SALES": _validate_design_page_unit,
    "P-U-DESIGN-CHECKOUT": _validate_design_page_unit,
    "P-U-DESIGN-VSL": _validate_design_page_unit,
    "P9-SPEECH": _validate_text,
}


# --- reducers: (ordered [(payload, text)]) -> Optional[str] -----------------
def _reduce_markdown_sections(ordered: List[Tuple[Dict[str, Any], str]]) -> Optional[str]:
    """P4-COPY / P9-SPEECH reducer: ordered, EXACTLY-ONCE Markdown section
    concatenation.

    Each unit contributes its own contiguous ordinal range; a duplicate
    ordinal (two units authoring the same slide — the whole-deck duplicate
    signature) or a MISSING ordinal (a gap in the deck) refuses the whole
    reduce (None) — never a torn deck on disk. Units keep INPUT order, so the
    document is the deck's real slide order."""
    seen: Dict[int, str] = {}
    for payload, text in ordered:
        lo = payload.get("first_ordinal")
        hi = payload.get("last_ordinal")
        if not isinstance(lo, int) or not isinstance(hi, int) or lo > hi:
            return None
        for n in range(lo, hi + 1):
            if n in seen:
                return None  # duplicate ordinal — two units authored one slide
            seen[n] = ""
        for n, body in _iter_slide_blocks(text):
            if n in seen and seen[n]:
                return None  # the same slide twice WITHIN the reduced set
            if n in seen:
                seen[n] = body
    if not seen:
        return None
    ordinals = sorted(seen)
    missing = [n for n in range(ordinals[0], ordinals[-1] + 1) if n not in seen]
    if missing:
        return None  # missing ordinal — a gap, never a silently-shortened deck
    empty = [n for n in ordinals if not seen[n].strip()]
    if empty:
        return None  # a scoped range with no matching block — scope was ignored
    return "".join(f"SLIDE {n}\n{seen[n].rstrip()}\n" for n in ordinals)


def _iter_slide_blocks(text: str) -> List[Tuple[int, str]]:
    import re as _re
    out: List[Tuple[int, str]] = []
    parts = _re.split(r"(?im)^\s*SLIDE\s+(\d+)\s*$", text)
    i = 1
    while i < len(parts) - 1:
        try:
            n = int(parts[i])
        except ValueError:
            i += 2
            continue
        out.append((n, parts[i + 1]))
        i += 2
    return out


def _reduce_qc_union(ordered: List[Tuple[Dict[str, Any], str]]) -> Optional[str]:
    """QC reducer (P-PROMPT-QC / P-IMAGE-QC): union of per-slide verdicts keyed
    by the STABLE slide_id. A duplicate slide_id (two units graded one slide)
    or a missing expected slide_id refuses the union — never a partially-
    graded report stamped pass. Every surviving unit's verdict row is preserved
    verbatim inside the merged report (all-results success: one failed unit
    fails the phase; nothing silently overwrites a sibling's verdict).

    The merged envelope carries the exact top-level keys build_deck.
    _qc_report_gate grades (gate label, pass, average, qc_independence,
    request_id) so the union output IS the report — with `pass` and `average`
    derived from the union itself, never typed over a refused union."""
    if not ordered:
        return None
    phase_id = str(ordered[0][0].get("phase_id") or "")
    # The EXPECTED slide set is the deck itself — every payload carries the
    # phase's unit_count, so a QC union handed 19 of 20 payloads (a slide
    # missing) is refused even though every handed row is well-formed. A
    # custom slide_id mapping (slides.json ids) is honored per payload; the
    # ordinal coverage check below is the mechanical floor that cannot be
    # fooled by id drift.
    counts = {p.get("unit_count") for p, _t in ordered
              if isinstance(p.get("unit_count"), int)}
    deck_n = counts.pop() if len(counts) == 1 else None
    expected: Dict[str, int] = {}
    for payload, _t in ordered:
        sid = str(payload.get("slide_id") or "")
        if not sid and payload.get("ordinal") is not None:
            sid = f"slide-{int(payload['ordinal']):02d}"
        if sid:
            expected[sid] = int(payload.get("ordinal") or 0)
    merged_rows: List[Dict[str, Any]] = []
    seen: set = set()
    seen_ordinals: set = set()
    for payload, text in ordered:
        try:
            doc = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(doc, dict):
            return None
        sid = str(payload.get("slide_id") or "")
        if not sid and payload.get("ordinal") is not None:
            sid = f"slide-{int(payload['ordinal']):02d}"
        if sid in seen:
            return None  # duplicate slide_id in the union
        seen.add(sid)
        row = dict(doc)
        row.setdefault("slide_id", sid)
        if payload.get("ordinal") is not None:
            row.setdefault("slide", payload.get("ordinal"))
            seen_ordinals.add(int(payload["ordinal"]))
        merged_rows.append(row)
    missing = sorted(set(expected) - seen)
    if missing:
        return None  # a slide the deck expects with no verdict row
    if deck_n is not None:
        uncovered = sorted(set(range(1, deck_n + 1)) - seen_ordinals)
        if uncovered:
            return None  # ordinal coverage gap: the union is NOT the whole deck

    # All-results pass: the union passes only when EVERY preserved row passed.
    # A row with no real verdict (validator already refused those upstream)
    # or a failed row fails the union — the reduced report can never stamp
    # pass over a sibling's failure.
    all_pass = True
    scores: List[float] = []
    for row in merged_rows:
        val = row.get("pass")
        if isinstance(val, bool):
            all_pass = all_pass and val
        elif isinstance(val, str) and val.strip():
            all_pass = all_pass and val.strip().lower() in ("pass", "passed", "ok")
        if isinstance(row.get("score"), (int, float)) and \
                not isinstance(row.get("score"), bool):
            scores.append(float(row["score"]))
        elif isinstance(row.get("average"), (int, float)) and \
                not isinstance(row.get("average"), bool):
            scores.append(float(row["average"]))
        for crit in row.get("criteria", []) if isinstance(row.get("criteria"), list) else []:
            if isinstance(crit, dict) and isinstance(crit.get("score"), (int, float)):
                scores.append(float(crit["score"]))
    average = round(sum(scores) / len(scores), 4) if scores else None
    report: Dict[str, Any] = {
        "gate": _UNIT_QC_GATE_LABELS.get(phase_id, phase_id),
        "pass": all_pass,
        "slides": merged_rows,
        "results": merged_rows,
        "unit_count": len(merged_rows),
    }
    if average is not None:
        report["average"] = average
    # Independence provenance: the FIRST well-formed row's own qc_independence
    # block wins (a per-slide QC unit that named its reviewer); otherwise the
    # unit payload's reviewer role (the work order's owning_role — the
    # independent QC specialist the phase dispatches, never the artifact's
    # authoring role). A report whose rows carry NO provenance at all still
    # records the envelope honestly — the phase verifier's own independence
    # gate re-judges the merged report.
    independence = ""
    for payload, text in ordered:
        try:
            row = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(row, dict):
            blk = row.get("qc_independence")
            if isinstance(blk, dict) and str(blk.get("graded_by") or "").strip():
                independence = str(blk["graded_by"]).strip()
                break
            if isinstance(blk, str) and blk.strip():
                independence = blk.strip()
                break
            role = str(row.get("graded_by") or row.get("reviewed_by") or "").strip()
            if role:
                independence = role
                break
    if not independence:
        role = str(ordered[0][0].get("reviewer_role") or "").strip()
        if role:
            independence = role
    if independence:
        report["qc_independence"] = {
            "graded_by": independence, "independent": True}
    request_id = str(ordered[0][0].get("route_request_id") or "").strip()
    if request_id:
        report["request_id"] = request_id
    return json.dumps(report, indent=2, ensure_ascii=False)


def _reduce_style_variants(ordered: List[Tuple[Dict[str, Any], str]]) -> Optional[str]:
    """P-STYLE-SPEC reducer: the deck-level spec carries EXACTLY THREE bounded
    variants (ids A/B/C, unique) + their representative slide ordinals. Fewer
    than three well-formed candidates refuses the spec; candidates beyond the
    bound are simply not kept (the first three well-formed ones ARE the
    deck-level spec — the per-slide enumeration is preserved, the OUTPUT bound
    is the TODO's 'bounded three desired variants', never one spec per
    slide). A unit that named no id takes its payload's assigned variant id;
    the unique-id forcing is the last resort."""
    variants: List[Dict[str, Any]] = []
    reps: List[int] = []
    used_ids: set = set()
    for payload, text in ordered:
        if len(variants) >= 3:
            break  # the bound: exactly three DESIRED variants are kept —
            # a per-slide fan-out may enumerate more candidates, and the
            # first three well-formed ones ARE the deck-level spec (the
            # FIX-112 semantics this contract preserves). Never one spec
            # per slide in the OUTPUT.
        try:
            doc = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(doc, dict):
            return None
        directive = str(doc.get("style_directive") or "").strip()
        rep = doc.get("representative_slide")
        if not directive or isinstance(rep, bool) or not isinstance(rep, int):
            return None
        vid = str(doc.get("id") or "").strip().upper()
        assigned = str(payload.get("variant_id") or "").strip().upper()
        if not vid and assigned:
            vid = assigned  # the assignment IS the explicit variant id
        if vid not in STYLE_SPEC_VARIANT_IDS or vid in used_ids:
            vid = next((c for c in STYLE_SPEC_VARIANT_IDS if c not in used_ids), None)
            if vid is None:
                return None
        used_ids.add(vid)
        variants.append({"id": vid, "style_directive": directive})
        reps.append(int(rep))
    if len(variants) != 3:
        return None
    return json.dumps(
        {"variants": variants, "representative_slides": reps},
        indent=2, ensure_ascii=False)


def _reduce_text_concat(ordered: List[Tuple[Dict[str, Any], str]]) -> Optional[str]:
    """Ordered text join (design page prompts, whole-file units): exactly the
    units in input order, each separated by a blank line. Refuses nothing but
    emptiness — scope there is one file/one prompt.

    PD-TEST-098: the separator is `_UNIT_TEXT_SEPARATOR`, the SAME constant
    `design_unit_char_budget` charges for when it divides the shared band
    across the parts. The two must never disagree, or the units would be
    budgeted against a different assembly than this one performs."""
    texts = [t.strip() for _p, t in ordered if t.strip()]
    if not texts:
        return None
    return _UNIT_TEXT_SEPARATOR.join(texts)


_UNIT_REDUCERS: Dict[str, Any] = {
    "P4-COPY": _reduce_markdown_sections,
    "P9-SPEECH": _reduce_markdown_sections,
    "P-PROMPT-QC": _reduce_qc_union,
    "P-IMAGE-QC": _reduce_qc_union,
    "P-STYLE-SPEC": _reduce_style_variants,
    "P-U-DESIGN-SALES": _reduce_text_concat,
    "P-U-DESIGN-CHECKOUT": _reduce_text_concat,
    "P-U-DESIGN-VSL": _reduce_text_concat,
}


class UnitContract:
    """The per-phase fan-out contract (PRES-001): scope shape, output schema,
    per-unit validator, exactly-once reducer, immutable input hashes."""
    __slots__ = ("phase_id", "scope", "output_schema", "validator", "reducer",
                 "inputs")

    def __init__(self, phase_id: str, scope: str, output_schema: str,
                 validator: Any, reducer: Any,
                 inputs: Tuple[str, ...] = ()):
        self.phase_id = phase_id
        self.scope = scope            # "section" | "slide" | "file"
        self.output_schema = output_schema
        self.validator = validator
        self.reducer = reducer
        self.inputs = inputs

    def describe(self) -> Dict[str, Any]:
        return {
            "phase_id": self.phase_id,
            "scope": self.scope,
            "output_schema": self.output_schema,
            "validator": getattr(self.validator, "__name__", "callable"),
            "reducer": getattr(self.reducer, "__name__", "callable"),
            "inputs": list(self.inputs),
        }


def _unit_contract_for(phase_id: str) -> Optional[UnitContract]:
    """The declared UnitContract for a fan-out phase, or None when the phase
    has none (the caller refuses the fanout before any paid call)."""
    validator = _UNIT_VALIDATORS.get(phase_id)
    reducer = _UNIT_REDUCERS.get(phase_id)
    if validator is None or reducer is None:
        return None
    return UnitContract(
        phase_id=phase_id,
        scope=_UNIT_CONTRACT_SCOPE.get(phase_id, "slide"),
        output_schema=_UNIT_CONTRACT_OUTPUT.get(phase_id, "text"),
        validator=validator,
        reducer=reducer,
        inputs=_UNIT_CONTRACT_INPUTS.get(phase_id, ()),
    )


def _section_ordinal_ranges(run_dir: Path, section_names: List[str]) -> List[Tuple[int, int]]:
    """Derive each P4-COPY section's contiguous slide-ordinal range from the
    SAME arc_allocation.json the fanout enumerator reads its section list from
    (fanout._sections_for_units). Reads the allocation's per-slot arc label
    (slot.get('arc')|'section'|'name'), maps every slot ordinal to its
    section, and returns one (first_ordinal, last_ordinal) pair per section in
    the section list's order. A section with no slots gets (-1, -1) — the
    payload then carries no range, and the validator/refuser treats the unit
    honestly (it may still author from its section name; the reducer's
    exactly-once check still guards the deck).

    Returns [] when arc_allocation.json is absent/unreadable (callers fall
    back to positional even splitting ONLY over the actual slide count)."""
    arc = run_dir / "working" / "copy" / "arc_allocation.json"
    if not arc.is_file():
        return []
    try:
        obj = json.loads(arc.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    # PD-TEST-067: the deck's slide allocation is read by the shared reader, so
    # a section's ordinal range is derivable from the live P3-ARC shape too
    # (previously an unrecognised container made this return [] and every
    # section unit silently lost its declared slide range).
    slots = _arc_slides.slots_from_obj(obj) or []
    if not isinstance(slots, list) or not slots:
        return []
    name_to_idx = {n: i for i, n in enumerate(section_names)}
    per_section: Dict[int, List[int]] = {}
    for pos, slot in enumerate(slots):
        if not isinstance(slot, dict):
            continue
        # PD-TEST-067: THE SAME accessor the enumerator derived the names with.
        # One reader for both sides of the join; the live slots say
        # ``arc_section``, which this used never to look for, so no label ever
        # matched and every section silently got the (-1,-1) sentinel -- the
        # live 'unit payload carries no ordinal range' refusal.
        label = _arc_slides.slot_label(slot)
        if not isinstance(label, str):
            continue
        idx = name_to_idx.get(label)
        if idx is None:
            continue
        ordinal = slot.get("ordinal")
        if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 1:
            ordinal = pos + 1
        per_section.setdefault(idx, []).append(ordinal)
    ranges: List[Tuple[int, int]] = []
    for i in range(len(section_names)):
        ords = sorted(per_section.get(i, []))
        ranges.append((ords[0], ords[-1]) if ords else (-1, -1))
    return ranges


def _section_payload_range(item: Dict[str, Any], run_dir: Path,
                           name: str) -> Optional[Tuple[int, int]]:
    """The slide-ordinal range one SECTION unit's payload must carry.

    PD-TEST-099. Order, and why it is this order:

      1. the ITEM's own ``first_ordinal``/``last_ordinal`` -- put there by
         ``fanout.enumerate_fanout_items`` from the SAME source that named the
         section (its declared ``sections[].slides``, or the very slots that
         carried its arc label). This is the join made unbreakable: one source,
         one derivation, carried across the seam;
      2. else ``_section_ordinal_ranges`` -- the arc reader, for an item built
         by hand with no enumerator provenance (the direct-call/test path);
      3. else None: the section declares no ordinals this run can see. The
         caller must then refuse the fan-out BEFORE any paid call -- a
         range-less section unit cannot pass its own contract validator (and
         ``_reduce_markdown_sections`` refuses its payload too), so a paid
         attempt on it is guaranteed waste, which is precisely how the live run
         spent its whole retry budget twice."""
    lo, hi = item.get("first_ordinal"), item.get("last_ordinal")
    if isinstance(lo, int) and not isinstance(lo, bool) \
            and isinstance(hi, int) and not isinstance(hi, bool) and lo <= hi:
        return (int(lo), int(hi))
    ranges = _section_ordinal_ranges(run_dir, [name])
    if ranges and tuple(ranges[0]) != (-1, -1):
        return (int(ranges[0][0]), int(ranges[0][1]))
    return None


def _preflight_section_payload_ranges(phase_id: str,
                                      payloads: List[Dict[str, Any]]) -> Optional[str]:
    """PRES-001/PD-TEST-099 preflight — refuses a SECTION-scoped fan-out whose
    units carry no derivable slide-ordinal range, BEFORE any paid call.

    ``_validate_copy_section`` refuses a payload without an ordinal range
    unconditionally ("unit payload carries no ordinal range"), and the markdown
    reducer refuses it too, so such a unit can NEVER come back ok: dispatching it
    converts the phase's bounded paid retry budget into byte-identical refusals
    — the live ledger's ``paid_attempts: 3, status: exhausted`` on an unchanged
    approved input. The defect is in the PAYLOAD, and it is knowable before the
    first token, so it is refused here. Returns the reason, or None when every
    section unit's range is present."""
    contract = _unit_contract_for(phase_id)
    if contract is None or contract.scope != "section" or not payloads:
        return None
    missing = [p for p in payloads
               if not (isinstance(p.get("first_ordinal"), int)
                       and not isinstance(p.get("first_ordinal"), bool)
                       and isinstance(p.get("last_ordinal"), int))]
    if not missing:
        return None
    keys = ", ".join(str(p.get("key") or "?") for p in missing[:4])
    if len(missing) > 4:
        keys += f", +{len(missing) - 4} more"
    return (f"AF-UNIT-CONTRACT: phase {phase_id} is section-scoped but "
            f"{len(missing)} of {len(payloads)} unit payload(s) carry no "
            f"derivable slide-ordinal range ({keys}) — a range-less section unit "
            "can never pass its own contract validator, so a paid attempt on it "
            "is refused only AFTER the money is spent. Refusing the fan-out "
            "before any paid call: the section source must declare each "
            "section's slides (arc_allocation.json sections[].slides, or slots "
            "carrying the section label AND their ordinals).")


def _unit_payload_enrichment(run_dir: Path, phase_id: str, item: Dict[str, Any],
                             unit_count: int) -> Dict[str, Any]:
    """The full validated unit payload TODO.md step 1 demands: scope + ordinal
    + name + (for section units) the section's slide-ordinal range, PLUS the
    per-unit input-hash snapshot pair (recorded vs current) the scoped
    invalidation predicate reads. Everything the unit worker needs rides the
    payload — the worker never re-derives scope from a bare unit key."""
    contract = _unit_contract_for(phase_id)
    payload: Dict[str, Any] = {
        "key": item.get("key"),
        "scope": contract.scope if contract else "slide",
        "phase_id": phase_id,
        "unit_count": unit_count,
        "unit_kind": _UNIT_CONTRACT_OUTPUT.get(phase_id, "text"),
        "output_schema": contract.output_schema if contract else "text",
        "ordinal": item.get("ordinal"),
        "name": item.get("name"),
        "path": item.get("path"),
        "slide": item.get("slide") if isinstance(item.get("slide"), dict) else None,
    }
    if payload["scope"] == "section":
        # PD-TEST-099: the ITEM's own range first -- fanout derived it from the
        # same source that named the section, so the two halves of the join
        # cannot disagree. ``_section_ordinal_ranges`` stays as the fallback for
        # an item built by hand (no enumerator provenance to carry).
        name = payload.get("name") or ""
        lo_hi = _section_payload_range(item, run_dir, name)
        if lo_hi is not None:
            payload["first_ordinal"], payload["last_ordinal"] = lo_hi
        # PD-TEST-125: assign this section its ordered deck-level beat, if any --
        # but ONLY when the deck is actually pitched. On a pitchless deck the
        # contract forbids fabricating these beats, so assigning them would order
        # the author to violate AF-PITCH-LEAK in order to satisfy AF-NO-VILLAIN.
        if phase_id in DECK_BEAT_PHASES and _deck_commercial_beats_apply(run_dir):
            _n = payload.get("ordinal")
            if isinstance(_n, int) and 1 <= _n <= len(DECK_ORDERED_BEATS):
                payload["owned_beats"] = [DECK_ORDERED_BEATS[_n - 1]]
    if phase_id == "P-STYLE-SPEC" and payload["ordinal"] is not None:
        # TODO.md step 1: EXPLICIT variant ids, bounded three. Each unit is
        # ASSIGNED one variant id by its enumeration position (unit 1 -> A,
        # 2 -> B, 3 -> C, cycling) — the paid work is variant-scoped before
        # any call, and the reducer's unique-id forcing is the last resort,
        # not the assignment authority.
        idx = int(payload["ordinal"]) - 1
        payload["variant_id"] = STYLE_SPEC_VARIANT_IDS[
            idx % len(STYLE_SPEC_VARIANT_IDS)]
    if payload["scope"] == "slide" and payload["ordinal"] is not None:
        sid = ""
        slide_obj = payload.get("slide") or {}
        for cand in (slide_obj.get("slide_id"), slide_obj.get("id")):
            if isinstance(cand, (str, int)) and str(cand).strip():
                sid = str(cand).strip()
                break
        if not sid:
            sid = f"slide-{int(payload['ordinal']):02d}"
        payload["slide_id"] = sid
    if phase_id == "P-IMAGE-QC":
        payload["needs_observed_text"] = True
    # Per-unit input-hash pair for scoped invalidation: "unit_inputs" is the
    # snapshot the unit's stored output was produced against (persisted by the
    # reuse path); "unit_inputs_now" is recomputed fresh on every dispatch.
    # On first dispatch both are the same fresh map — the pair only diverges
    # on a resume, where a changed hash invalidates exactly the unit that
    # consumes it.
    hashes_now = unit_input_hashes(run_dir, phase_id)
    payload["unit_inputs"] = hashes_now
    payload["unit_inputs_now"] = hashes_now
    return payload


def _unit_scope_work_order(order: Dict[str, Any], payload: Dict[str, Any]) -> Dict[str, Any]:
    """The work order a unit worker dispatches with: the FULL original order
    plus the validated unit payload (the model reads both verbatim in the
    WORK ORDER block) and the `_unit_scope` marker compose_prompt uses to
    replace the whole-artifact tail with the one-scope instruction."""
    wo = dict(order)
    wo["_unit_payload"] = payload
    wo["_unit_scope"] = _unit_scope_text(payload) or ""
    return wo


def _read_units_ledger(run_dir: Path, phase_id: str) -> List[Dict[str, Any]]:
    """Best-effort read of the phase's per-unit JSONL ledger (the rows
    append_unit_ledger_row wrote on earlier dispatches). Never raises: a
    missing/corrupt ledger means 'nothing reusable', never a failed phase."""
    rows: List[Dict[str, Any]] = []
    try:
        path = fanout.unit_ledger_path(run_dir, phase_id)
        if not path.is_file():
            return rows
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
    except OSError:
        return []
    return rows


def _preflight_fanout_contract(phase_id: str, spec: "fanout.FanoutSpec",
                               run_dir: Path) -> Optional[str]:
    """PRES-001 preflight — rejects an INCOMPATIBLE manifest fanout BEFORE any
    paid call. Refusal reasons (each returned as a string):
      * the phase declares no UnitContract (no validator+reducer pair);
      * PRESENTATION_UNIT_CONTRACTS=0 (documented rollback keeps the legacy
        path instead — this returns None so the caller takes that path);
      * the manifest's fanout.by disagrees with the contract's scope shape
        (e.g. P4-COPY fanned out by=slide would author whole-section copy
        per slide — exactly the unscoped shape this fix removes);
      * the phase is a contract phase but its executor is a script (a script
        executor never reaches this dispatch path, so a fanout declaration on
        one is dead config — and P9-SPEECH's script harness is the live
        precedent that a stale fanout field there is NOT evidence this
        generic path executes for speech)."""
    if not unit_contracts_enabled():
        return None
    contract = _unit_contract_for(phase_id)
    if contract is None:
        return (f"AF-UNIT-CONTRACT: phase {phase_id} declares a manifest fanout "
                f"(by={spec.by!r}) but no per-phase UnitContract (validator + "
                "reducer). A fan-out without an exactly-once reducer and a "
                "per-unit validator corrupts or refuses aggregation — refusing "
                "the phase before any paid call (PRES-001).")
    if phase_id in _UNIT_CONTRACT_SCOPE and spec.by != _UNIT_CONTRACT_SCOPE[phase_id]:
        return (f"AF-UNIT-CONTRACT: phase {phase_id} declares fanout by={spec.by!r} "
                f"but its UnitContract scopes units by={_UNIT_CONTRACT_SCOPE[phase_id]!r} "
                "— an incompatible manifest fanout is refused before any paid "
                "call (PRES-001).")
    manifest = load_manifest_for_run(run_dir)
    if manifest is not None:
        try:
            phase_obj = manifest.phase_or_none(phase_id) \
                if hasattr(manifest, "phase_or_none") else \
                next((p for p in manifest.phases if p.id == phase_id), None)
        except Exception:  # noqa: BLE001
            phase_obj = None
        if phase_obj is not None and phase_obj.executor_kind == "script":
            return (f"AF-UNIT-CONTRACT: phase {phase_id} declares a manifest fanout "
                    "but its executor is a script — the generic unit path never "
                    "executes for a script phase, so this fanout declaration is "
                    "incompatible and is refused before any paid call (PRES-001).")
    return None


def _aggregate_fanout_parts(phase_id: str, parts: List[str]) -> Optional[str]:
    """Legacy FIX 112 aggregator, PRESERVED for rollback (a phase with no
    UnitContract, or PRESENTATION_UNIT_CONTRACTS=0) — byte-for-byte the
    pre-PRES-001 behavior: 1 part passes through; N JSON objects shallow-merge;
    P-STYLE-SPEC keeps its bounded-three builder. The UnitContract path has
    REPLACED this reducer for every declared fan-out phase (no generic
    dict.update reducer remains on any contract-covered path)."""
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


# ---------------------------------------------------------------------------
# PD-TEST-065. `EMPTY_COMPLETION_MARKER` is the ONE spelling of the fan-out
# empty-completion failure, so the durable per-unit record written by the batch
# loop (`last_error`) and the re-attempt decision read by `_unit_worker` can
# never drift apart. It is the PREFIX of the recorded reason; the detail suffix
# is diagnostic only and is deliberately excluded from the match.
# ---------------------------------------------------------------------------
EMPTY_COMPLETION_MARKER = "unit returned empty output"


def effort_for_paid_attempt(prior_error: str,
                            attempts_total: int) -> Optional[str]:
    """The reasoning effort a fan-out unit's NEXT paid attempt must send.

    PD-TEST-124 / PD-070. Extracted from `_unit_worker` so the ladder walk is a
    real, directly-testable function rather than an inline expression that only
    a constants-level test could reach (the test that used to guard this
    asserted properties of `DEEPSEEK_REASONING_EFFORT_LADDER` alone and so
    passed unchanged even when the walk itself was broken).

    Returns:
      * `None` — attempt 1, or any attempt after a failure that was NOT an
        empty completion. The caller then sends `DEEPSEEK_REASONING_EFFORT`
        (the product worker's default), which is PD-TEST-065's behaviour.
      * a rung of `DEEPSEEK_REASONING_EFFORT_LADDER` — a unit that has ALREADY
        come back empty is re-issued at a reduced effort instead of repeating
        the request that just failed. The rung is chosen by how many attempts
        the unit has already spent; `attempts_total` is durable (PRES-014), so
        the rung survives restarts and resumes.

    HONEST BOUND (do not let a test claim more than this): the rung index is
    CLAMPED to the last rung, so once the ladder is shorter than the unit's
    remaining attempt allowance, later attempts re-send the final rung rather
    than stepping further down. With the shipped one-rung ladder that means
    attempt 2 and attempt 3 both send `low` — a RESAMPLE at
    `DEEPSEEK_TEMPERATURE`, not a fresh step-down. That is deliberate: no
    documented value below `low` keeps thinking enabled (`none` disables it and
    mixing it with `thinking.type="enabled"` has undocumented precedence, so it
    is not a rung until probed), and inventing an unmeasured rung would
    re-create PD-070's dead-end defect from the other direction. The genuine
    guarantee is only that attempt 2 DIFFERS from attempt 1.
    """
    if EMPTY_COMPLETION_MARKER not in (prior_error or ""):
        return None
    spent = int(attempts_total or 1)
    rung = max(0, min(spent - 1, len(DEEPSEEK_REASONING_EFFORT_LADDER) - 1))
    return DEEPSEEK_REASONING_EFFORT_LADDER[rung]



def _empty_completion_detail(usage: Optional[Dict[str, Any]]) -> str:
    """Name the ONE number that explains an empty completion.

    PD-TEST-065: the generic fan-out path used to discard the provider's usage
    dict on an empty completion, so the run could not tell "reasoning consumed
    the whole shared budget" from any other empty answer -- the diagnosis had to
    be reconstructed later from a DIFFERENT phase's successful call. The serial
    path has always recorded its usage; this brings the fan-out path to parity.
    Never raises: a missing/misshapen usage is reported as missing, not
    invented."""
    if not isinstance(usage, dict):
        return " (no usage recorded)"
    details = usage.get("completion_tokens_details")
    reasoning = details.get("reasoning_tokens") if isinstance(details, dict) else None
    completion = usage.get("completion_tokens")
    # PD-070: `finish_reason` is the provider's own verdict on WHY generation
    # ended. "length" == the token maximum was reached; with thinking enabled
    # that maximum is shared with reasoning, so "length" + empty content is
    # budget starvation, while "stop" + empty is a model that emitted nothing.
    # Absent (older logs, other transports) adds nothing to the string, so the
    # PD-TEST-065 wording is byte-identical when the field is missing.
    finish = usage.get("finish_reason")
    finish_txt = "" if finish is None else f", finish_reason={finish!r}"
    if completion is None and reasoning is None:
        return f" (usage recorded without token counts{finish_txt})"
    if reasoning is None:
        return (f" (completion_tokens={completion}, reasoning_tokens not "
                f"reported{finish_txt})")
    return (f" (completion_tokens={completion}, reasoning_tokens={reasoning} of "
            f"max_tokens={DEEPSEEK_MAX_OUTPUT_TOKENS}{finish_txt} -- reasoning "
            f"is billed INSIDE that budget)")


def _dispatch_phase_fanout_units(
        run_dir: Path, order: Dict[str, Any], *, dept_root: Path,
        phase_obj: Optional[Phase], worker_id: str,
        spec: "fanout.FanoutSpec", patterns: List[str], target: Path,
        prior_reasons: List[str]) -> DispatchResult:
    """Run ONE manifest-declared fan-out phase through fanout.run_units and
    aggregate the units into `target` — under the phase's UnitContract
    (PRES-001): a preflight refusal of an incompatible manifest fanout BEFORE
    any paid call, the full validated unit payload in every unit prompt (with
    compose_prompt's whole-artifact tail suppressed in favor of the one-scope
    instruction), per-unit contract validation BEFORE a unit may report ok,
    the contract's own exactly-once reducer at aggregation (never the legacy
    dict.update), and per-unit scratch/ledger rows that let a resume re-pay
    ONLY the units whose inputs changed or whose output failed.

    Per-unit prompt composition reuses compose_prompt() (role SOP context +
    upstream artifacts, attempt-stamped), the model call goes through
    dispatch_complete() (the same routed entrypoint every other phase uses),
    and the whole-phase verifier runs at the end — mirroring the P4-PROMPT
    parallel loop's partial-failure semantics (S2.4): no fail-fast, every
    submitted unit runs to its own conclusion, and the phase-level verify()
    only runs when every unit came back ok."""
    phase_id = phase_obj.id if phase_obj is not None else "P-UNKNOWN-FANOUT"
    owning_role = order.get("owning_role") or (phase_obj.owning_role if phase_obj else "")

    # PRES-001 preflight: an incompatible manifest fanout (no UnitContract,
    # scope/shape disagreement, dead script-executor declaration) is refused
    # HERE — before enumerate, before compose, before one paid token.
    preflight_reason = _preflight_fanout_contract(phase_id, spec, run_dir)
    if preflight_reason:
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0, "status": "error",
            "reason": preflight_reason,
        })
        return DispatchResult(phase_id, "error", 0, [preflight_reason])

    items = fanout.enumerate_fanout_items(
        run_dir, spec, phase_id=phase_id, produces_artifact=patterns)
    if not items:
        reason = ("fanout spec enumerated zero units — refusing both a serial "
                  "fallback and an empty aggregate (S2: no unit is ever invented)")
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0, "status": "error", "reason": reason,
        })
        return DispatchResult(phase_id, "error", 0, [reason])

    # PRES-001 payloads: every unit item is enriched into the FULL validated
    # payload (scope, ordinal, section slide-range, stable slide_id, per-unit
    # input-hash snapshot pair) before anything is dispatched.
    payloads = [_unit_payload_enrichment(run_dir, phase_id, it, len(items))
                for it in items]
    # PD-TEST-099 preflight: a section-scoped unit whose payload carries no
    # ordinal range can never pass its own contract validator, so it is refused
    # HERE -- before any paid call -- instead of after the model answers (the
    # live P4-COPY ledger's whole retry budget, spent on three byte-identical
    # post-payment refusals).
    range_gap = _preflight_section_payload_ranges(phase_id, payloads)
    if range_gap:
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0, "status": "error",
            "reason": range_gap,
        })
        return DispatchResult(phase_id, "error", 0, [range_gap])
    by_key = {p["key"]: p for p in payloads}

    # PRES-001 scoped reuse (the 'fail slide7, resume only7' acceptance): unit
    # scratch outputs persisted by an earlier attempt are REUSED — never
    # re-paid — when (a) the unit's stored ledger row says ok, (b) its stored
    # output still passes the contract validator, and (c) the per-unit input
    # hashes recorded at production time are unchanged now. Everything else
    # re-dispatches; unchanged successful units stay exactly once.
    reuse: Dict[str, str] = {}
    units_ledger_rows = _read_units_ledger(run_dir, phase_id)
    if units_ledger_rows:
        contract = _unit_contract_for(phase_id)
        for row in units_ledger_rows:
            key = str(row.get("unit") or "")
            rkey = str(row.get("reuse_key") or "")
            if row.get("status") != "ok" or not key or not rkey:
                continue
            scratch = run_dir / rkey
            if not scratch.is_file():
                continue
            payload = by_key.get(key)
            if payload is None:
                continue
            text = scratch.read_text(encoding="utf-8", errors="replace").strip()
            ok_u, _vr = contract.validator(payload, text)
            if not ok_u:
                continue
            # scoped invalidation: the LEDGER row's recorded input-hash
            # snapshot (what the stored output was produced against) vs the
            # CURRENT fresh hashes. A changed hash invalidates exactly the
            # unit that consumes the changed input — never its siblings.
            before = row.get("unit_inputs")
            now = payload.get("unit_inputs_now")
            if unit_inputs_changed(
                    before if isinstance(before, dict) else None,
                    now if isinstance(now, dict) else {}):
                continue
            reuse[key] = text
    # ------------------------------------------------------------------
    # PRES-014 (W2 WF05) -- THE ADMISSION PLAN.
    #
    # Before this block, EVERY enumerated unit was submitted on EVERY tick;
    # the per-unit scratch files were written but never read. The admission
    # pass below is the fix's whole spine:
    #
    #   1. enumerate ALL units (per-slide QC coverage is never narrowed);
    #   2. desired_count bounds the phase's DESIRED WORK COUNT only for
    #      phases whose reducer consumes a fixed number of whole-deck units
    #      (style variants: 3) -- the dispatcher passes desired_count=None
    #      for QC phases, whose obligation is EVERY slide exactly once;
    #   3. batch_width bounds each admission batch (bounded concurrent
    #      batches -- QC still covers 100 slides exactly once across its
    #      ceil(100/12)=9 batches);
    #   4. banked results are read AND VALIDATED per unit before admission:
    #      prior ok + matching input hash + existing, hash-verified output
    #      file => banked (attempts 0 this call, no model call). A corrupt
    #      or stale banked output re-runs EXACTLY that one unit;
    #   5. every unit transition appends one durable row; the state map is
    #      atomic-replace only. No restart resets attempts/budget.
    # ------------------------------------------------------------------
    _us = unit_store
    _banked_keys: set = set()
    _store_state: Dict[str, Dict[str, Any]] = {}
    _company_id = ""
    _presentation_id = ""
    _unit_input_hashes: Dict[str, str] = {}
    if _us is not None:
        _company_id = _us.resolve_company_id(run_dir)
        _presentation_id = _us.resolve_presentation_id(run_dir)
        _store_state = _us.load_state(run_dir, phase_id)
        for it in items:
            _unit_input_hashes[it["key"]] = _us.input_hash_for_unit(
                {"inputs": by_key.get(it["key"], {}).get("unit_inputs_now", {}),
                 "payload": it.get("payload", it)})

    # ------------------------------------------------------------------
    # PD-TEST-119 / 120 / 121 -- AN ACTIONABLE REPAIR RECEIPT VOIDS THE BANK.
    #
    # Three defects interlock into a loop with no exit:
    #   * PD-TEST-119: a unit is reusable on its INPUT hash alone, so once the
    #     phase-level verifier rejects the assembled artifact, every dispatch
    #     rebuilds the identical rejected file from the identical banked parts --
    #     forever, with zero paid calls.
    #   * PD-TEST-120: DISPATCH_RETRY_CAP caps PAID CALLS PER PHASE, and a 3-unit
    #     phase spends all 3 on its first authoring pass, so there is normally no
    #     budget left to re-author with.
    #   * PD-TEST-121: nothing sanctioned un-banks a unit set -- `validate_banked`
    #     refuses only on a changed input hash or a missing/corrupt output, and the
    #     dispatcher CLI has no unit or bank reset at all.
    #
    # The repair receipt is exactly the operator act that resolves all three at
    # once, which is why it is the right place to hang this:
    #   * it is BUDGET-AWARE -- `authorize_paid_retry_reset` reopens `allowance`
    #     paid attempts and the reservations below then consume it, so the
    #     re-author is paid for by the same deliberate act;
    #   * it is AUDITED and SINGLE-USE -- owner uid, dispatcher sha256, phase,
    #     approved input revision and ledger generation, spent exactly once;
    #   * it is BOUNDED -- no receipt means no change at all, so a phase whose
    #     verifier can never pass cannot loop: it simply behaves exactly as it does
    #     today.
    #
    # Deliberately NOT a phase-verifier-driven invalidation. An earlier attempt at
    # that was refuted by independent review: with no budget left it destroyed the
    # bank and left the phase parked AND unbuildable (the units came back FAILED
    # with every reservation denied). Invalidation must be paid for, and the only
    # component that can promise payment is the receipt.
    # ------------------------------------------------------------------
    _force_reauthor, _force_why = False, ""
    try:
        _led = _read_ledger(run_dir, phase_id)
        _force_reauthor, _force_why = _repair_receipt_is_actionable(
            _led, phase_id, run_dir,
            approved_input_revision=_approved_input_revision(run_dir, phase_id))
    except Exception:  # noqa: BLE001 -- never let the check itself break a fanout
        _force_reauthor, _force_why = False, "receipt check unavailable"
    # PD-TEST-119 follow-up (round 270). `wanted_items` is computed HERE because
    # the sufficiency gate below must compare the receipt's allowance against the
    # number of units the void would ACTUALLY invalidate -- and `len(items)` is the
    # ENUMERATED count, not that number. Measured on the live run: the design
    # phases enumerate 8 units (by slide) while only 3 are wanted, so the gate saw
    # `3 < 8`, refused with bank_void_refused_insufficient_allowance, and made the
    # void INERT on exactly the three phases it was written for -- the receipt was
    # actionable, everything looked correct, and the artifact never changed. The
    # later line reuses this value rather than recomputing it, so the two can never
    # disagree.
    desired_count = getattr(spec, "desired_count", None)
    wanted_items = _us.apply_desired_count(items, desired_count) if _us else list(items)

    # SUFFICIENCY GATE (independent review of PR #1150, MEDIUM).
    #
    # The void and the payment must be COMMENSURATE. `authorize_paid_retry_reset`
    # accepts any `allowance` in 1..PHASE_TOTAL_PAID_HARD_CAP, so `--reset-allowance 1`
    # is a legal, documented invocation -- and without this gate it voided the
    # WHOLE bank while paying for exactly ONE unit. Measured by the reviewer with
    # the real reservation seam running: allowance=1 -> one unit re-authored, two
    # died on PaidBudgetExhausted, and their durable records were OVERWRITTEN from
    # `ok` to `failed`. That is the same "parked AND unbuildable" mode that
    # refuted the earlier verifier-driven design, reachable silently through the
    # tool's own CLI.
    #
    # So: void only when the actionable receipt can pay for every unit it would
    # invalidate. Otherwise leave the bank INTACT and say so -- the phase then
    # behaves exactly as it does without a receipt, which is the safe direction,
    # and the operator can re-issue with an allowance that covers the work.
    _allowance = 0
    if _force_reauthor:
        try:
            _allowance = int((_read_repair_receipt(run_dir, phase_id) or {}).get("allowance") or 0)
        except (TypeError, ValueError):
            _allowance = 0
        _n_units = len(wanted_items)
        if _allowance < _n_units:
            _force_reauthor = False
            _append_sidecar(run_dir, phase_id, {
                "worker": worker_id, "attempt": 0,
                "status": "bank_void_refused_insufficient_allowance",
                "reason": (f"an actionable repair receipt covers {_allowance} paid "
                           f"attempt(s) but this fan-out would invalidate {_n_units} "
                           "unit(s); voiding the bank would leave units it cannot "
                           "pay to re-author, so the bank is left INTACT and the "
                           "phase behaves as if no receipt were present. Re-issue "
                           f"with --reset-allowance >= {_n_units} (max "
                           f"{PHASE_TOTAL_PAID_HARD_CAP})."),
                "allowance": _allowance, "units": _n_units,
            })
    if _force_reauthor:
        reuse = {}
        _store_state = {}
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0, "status": "bank_voided_by_receipt",
            "reason": ("an actionable paid-retry repair receipt is on disk, so the "
                       "banked unit outputs are NOT reusable and every unit "
                       "re-authors against the current approved input; the "
                       "reservations below consume that receipt (PD-TEST-119/120/121)"),
            "receipt_reason": _force_why,
        })

    reuse = {k: v for k, v in reuse.items() if k not in _store_state}
    batch_width = getattr(spec, "batch_width", None)

    # PD-TEST-098 (review fix B): `admitted_count` MUST be stamped BEFORE any
    # validator runs -- the scoped-reuse loop above and the banked-validation
    # loop below both call `contract.validator(payload, ...)`, and for a design
    # phase that validator bounds the text by the part's share of the shared
    # band. Stamped late (it used to be stamped just before `pending_items`),
    # those two loops saw `unit_count` instead -- the ENUMERATED count, 8 on the
    # live run -- and computed the share as (1124, 2248). Since
    # floor_share(3) = 2999 > ceiling_share(8) = 2248, EVERY compliant part
    # failed reuse: measured with the real dispatcher and a stubbed model,
    # pristine main re-paid 0 units on dispatch #2/#3 while the late stamp
    # re-paid 3 each (9 total). That silently broke PRES-001's "a resume re-pays
    # ONLY the changed units" contract for these three phases and inverted the
    # fix's own cost story.
    #
    # `wanted_items` is computed HERE now because it is exactly the number of
    # parts the reducer will join; it depends only on `items` and
    # `desired_count`, neither of which the loops below mutate, so hoisting it
    # changes nothing else. The later line reuses this value rather than
    # recomputing it, so the two can never disagree.
    # `wanted_items` was hoisted above the sufficiency gate -- reused here, never recomputed.
    for _it in wanted_items:
        _p = by_key.get(_it["key"])
        if isinstance(_p, dict):
            _p["admitted_count"] = len(wanted_items)

    # Step 4 -- validate banked results BEFORE admission. A validated unit is
    # admitted as already-done; a stale/corrupt one falls through to a real
    # (re)submission with its transition recorded.
    if _us is not None:
        for it in items:
            ukey = it["key"]
            rec = _store_state.get(ukey)
            cur_ih = _unit_input_hashes.get(ukey, "")
            admits, why = _us.validate_banked(
                rec, run_dir=run_dir, current_input_hash=cur_ih)
            if admits:
                _saved = run_dir / str(rec.get("output_path") or "")
                _contract = _unit_contract_for(phase_id)
                admits = bool(_saved.is_file() and _contract.validator(
                    by_key.get(ukey, it), _saved.read_text(encoding="utf-8"))[0])
            if admits:
                _banked_keys.add(ukey)
                prior = rec if isinstance(rec, dict) else {}
                rec_next = dict(prior)
                rec_next["status"] = "banked"
                rec_next["revision"] = int(rec.get("revision") or 0)
                rec_next["input_hash"] = cur_ih
                _us.stamp_identity(rec_next, company_id=_company_id,
                                   presentation_id=_presentation_id,
                                   phase_id=phase_id)
                _store_state[ukey] = rec_next
                _us.append_transition(
                    run_dir, phase_id, ukey,
                    from_status=str(prior.get("status")),
                    to_status="banked",
                    reason=why, company_id=_company_id,
                    presentation_id=_presentation_id,
                    revision=rec_next["revision"], input_hash=cur_ih,
                    output_hash=str(rec.get("output_hash") or ""),
                    route=rec.get("author_route") if isinstance(rec, dict) else None,
                    attempts_total=int(rec.get("attempts_total") or 0))
            elif rec is not None:
                # A prior record exists but does not validate: append the
                # refusal transition so the resume trail shows WHY this unit
                # re-runs (corrupt output / changed inputs / not-banked).
                prior = rec if isinstance(rec, dict) else {}
                _us.append_transition(
                    run_dir, phase_id, ukey,
                    from_status=str(prior.get("status")),
                    to_status="invalidated",
                    reason=why, company_id=_company_id,
                    presentation_id=_presentation_id,
                    revision=int(prior.get("revision") or 0),
                    input_hash=cur_ih,
                    attempts_total=int(prior.get("attempts_total") or 0))

    # Step 2 -- the DESIRED WORK COUNT reduces the enumerated list only for
    # whole-deck-unit phases. Per-slide QC phases (desired_count is None on
    # them, enforced by the caller's plan) never drop a slide here.
    #
    # PD-TEST-098: `wanted_items` and the `admitted_count` stamp now happen
    # ABOVE, before the scoped-reuse and banked-validation loops -- both call the
    # design phase's share-bounded validator (see the note there). It is NOT
    # recomputed here, so the two can never disagree.

    pending_items = [it for it in wanted_items if it["key"] not in _banked_keys and it["key"] not in reuse]
    _append_sidecar(run_dir, phase_id, {
        "worker": worker_id, "attempt": 0, "status": "fanout_plan",
        "units_enumerated": len(items), "units_desired": len(wanted_items),
        "banked_reused": sorted(_banked_keys),
        "units_pending": len(pending_items),
        "desired_count": desired_count, "batch_width": batch_width,
    })

    # ------------------------------------------------------------------
    # PD-TEST-124 -- DECLARE THE BOUNDED TOTAL PAID BUDGET BEFORE ANY PAID CALL.
    #
    # The declaration is written (atomically, under the phase's own ledger lock)
    # BEFORE a single unit is submitted, so:
    #   * every reservation below is checked against a bound that is on disk,
    #     durable and identical for every concurrent worker and every later
    #     sweep -- not against an in-memory number a restart would lose;
    #   * the admission ORDER is fixed here, in the deterministic enumeration
    #     order fanout.enumerate_fanout_items produced, so "which units get the
    #     first attempts" is reproducible rather than whichever thread ran first;
    #   * a phase whose budget cannot fund every eligible unit says so, by name,
    #     in the ledger and in a sidecar -- never by silently dropping units.
    #
    # Only PENDING units are declared: a banked or reused unit costs nothing, so
    # funding it would shrink the pool owed to the units that must actually run.
    # The call is idempotent and monotonic within a generation, and it NEVER
    # resets a counter (a re-declaration over a smaller pending set keeps the
    # larger bound already granted).
    # ------------------------------------------------------------------
    _budget_decl: Dict[str, Any] = {}
    try:
        _budget_decl = _declare_phase_paid_budget(
            run_dir, phase_id, unit_keys=[str(it["key"]) for it in pending_items],
            worker_id=worker_id)
    except Exception as exc:  # noqa: BLE001 -- a broken declaration must never
        # kill the phase: the reservations fall back to the legacy phase-level
        # cap, i.e. exactly the pre-PD-TEST-124 behaviour, and the sidecar says
        # so loudly instead of pretending the new bound applied.
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0,
            "status": "paid_budget_declaration_failed",
            "reason": (f"{type(exc).__name__}: {exc}; paid reservations fall back "
                       "to the legacy phase-level cap for this dispatch"),
        })
    if _budget_decl.get("not_admitted"):
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0,
            "status": "paid_budget_cannot_fund_all_units",
            "reason": (f"{_budget_decl['budget']['units_not_admitted']} of "
                       f"{_budget_decl['budget']['units_eligible']} eligible unit(s) "
                       f"fall outside the declared bounded total of "
                       f"{_budget_decl['budget']['total_cap']} paid attempt(s); they "
                       "were NOT attempted (they did not fail). They are named in "
                       f"{_ledger_path(run_dir, phase_id)} under "
                       f"{LEDGER_UNIT_NOT_ADMITTED}."),
            "budget": _budget_decl["budget"],
            "admitted_units": _budget_decl.get("admitted"),
            "not_admitted_units": sorted(_budget_decl["not_admitted"]),
        })

    results: List[fanout.UnitResult] = []
    # Banked units first, in input order, with attempts=0 -- they are real
    # results from real prior calls, validated above.
    banked_by_key: Dict[str, Dict[str, Any]] = {
        k: v for k, v in _store_state.items() if k in _banked_keys}
    for it in wanted_items:
        if it["key"] not in _banked_keys:
            continue
        rec = banked_by_key.get(it["key"], {})
        results.append(fanout.UnitResult(
            key=it["key"], status="ok", attempts=0,
            target=rec.get("output_path"),
            meta=rec.get("author_route") if isinstance(rec.get("author_route"), dict)
            else None))

    if _us is not None and _banked_keys:
        # Persist the banked-stamped state even when nothing is pending: the
        # on-disk record must say "banked" (validated THIS call), not just the
        # in-memory copy. Append-only transitions already carry the row; this
        # is the atomic current-state pointer.
        _us.save_state(run_dir, phase_id, _store_state,
                       company_id=_company_id, presentation_id=_presentation_id)

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

    contract = _unit_contract_for(phase_id)

    def _unit_worker(unit: "fanout.Unit") -> "fanout.UnitResult":
        payload = by_key.get(unit.key, {})
        # PD-TEST-065: if THIS unit's own durable record already carries an
        # empty completion, the identical request has already been proven to
        # return nothing at full reasoning effort. Re-issue it at the reduced
        # effort instead of repeating the byte-identical call. The record
        # survives restarts and resumes (PRES-014: no restart resets the
        # ledger), so this holds across sweeps, not just within one process.
        prior_rec = _store_state.get(unit.key)
        prior_err = str(prior_rec.get("last_error") or "") \
            if isinstance(prior_rec, dict) else ""
        # PD-070/PD-TEST-124: the ladder walk lives in `effort_for_paid_attempt`
        # so it is directly testable over a real attempt sequence. It returns
        # None for a first attempt (caller sends the product default) and a
        # ladder rung once the unit has already come back empty.
        _prior_attempts = int(prior_rec.get("attempts_total") or 1) \
            if isinstance(prior_rec, dict) else 1
        effort = effort_for_paid_attempt(prior_err, _prior_attempts)
        # PD-TEST-124: the paid reservation this unit's dispatch makes must be
        # accounted to THIS unit, so the whole dispatch runs inside a unit
        # scope. Inside it the reservation enforces the phase's declared bounded
        # total, this unit's own DISPATCH_RETRY_CAP ceiling, first-attempt
        # fairness, and duplicate-safe atomicity; outside it (every serial
        # phase) the reservation is the untouched legacy phase-level one.
        #
        # `allow_reauthor` is set ONLY when this unit's own durable record says
        # it SUCCEEDED BEFORE and it is back in the pending set, which is the
        # fan-out's own proof that the success was invalidated (its inputs
        # changed, its output no longer validates, or `_force_reauthor` voided
        # the bank for a repair receipt). A unit that has not been invalidated
        # never reaches this code at all -- banked and reused units are taken
        # out of the pending list above -- so "a success is never regenerated"
        # and "an invalidated success can still be repaired" both hold.
        _prior_status = str((prior_rec or {}).get("status") or "") \
            if isinstance(prior_rec, dict) else ""
        _was_success = _prior_status in (
            _us.BANKED_STATUSES if _us is not None else ("ok", "verified", "banked"))
        try:
            with paid_unit_scope(unit.key,
                                 allow_reauthor=bool(_force_reauthor or _was_success)):
                system_prompt, user_prompt = compose_prompt(
                    phase_id=phase_id, owning_role=owning_role, dept_root=dept_root,
                    run_dir=run_dir, order=_unit_scope_work_order(order, payload),
                    attempt=1, prior_reasons=prior_reasons,
                )
                content, usage, route = dispatch_complete(
                    system_prompt, user_prompt, phase_id=phase_id, run_dir=run_dir,
                    worker_id=worker_id, reasoning_effort=effort)
        except Exception as exc:  # noqa: BLE001 — a raised unit is a failed unit
            return fanout.UnitResult(key=unit.key, status="failed", attempts=1,
                                     reasons=[f"{type(exc).__name__}: {exc}"])
        text = _clean_payload((content or "").strip())
        if not text:
            # PD-TEST-065: record the failure the way the serial path does --
            # an explicit sidecar row carrying the provider's usage -- and put
            # the budget arithmetic in the reason, so the durable unit record
            # says WHY the output was empty on the NEXT read.
            _append_sidecar(run_dir, phase_id, {
                "worker": worker_id, "attempt": 1, "unit": unit.key,
                "status": "empty_completion",
                "reasoning_effort": effort or DEEPSEEK_REASONING_EFFORT,
                "max_tokens": DEEPSEEK_MAX_OUTPUT_TOKENS,
                "usage": usage})
            return fanout.UnitResult(
                key=unit.key, status="failed", attempts=1,
                reasons=[EMPTY_COMPLETION_MARKER
                         + _empty_completion_detail(usage)])
        # PRES-001: the unit output must pass the CONTRACT's validator BEFORE
        # it may report ok. An invalid unit is a failed unit — it never rides
        # into the reducer, never overwrites a sibling's scratch, never counts
        # toward the phase's completion. This is where a whole-deck duplicate
        # response dies for slide/QC contracts: wrong ordinal, wrong slide_id,
        # out-of-scope content — refused here, not discovered after payment.
        if contract is not None:
            ok_u, reasons_u = contract.validator(payload, text)
            if not ok_u:
                return fanout.UnitResult(key=unit.key, status="failed",
                                         attempts=1, reasons=reasons_u)
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

    # A reused unit never re-enters the pool: its UnitResult is synthesized
    # from the stored, re-validated scratch output (attempts=0 — honest in the
    # ledger: this dispatch paid nothing for it).
    reused_results: Dict[str, "fanout.UnitResult"] = {
        key: fanout.UnitResult(key=key, status="ok", attempts=0,
                               target=str(fanout.unit_output_path(
                                   run_dir, phase_id, key).relative_to(run_dir)),
                               meta={"reused": True})
        for key in reuse}
    live_units = [fanout.Unit(key=it["key"], payload=by_key.get(it["key"], it))
                  for it in items if it["key"] not in reuse]

    deadline_s = (phase_obj.budget_minutes * 60) if phase_obj is not None else None
    results.extend(r for k, r in reused_results.items() if k not in _banked_keys)
    # PD-TEST-124: record the FREE successes durably before any paid unit runs.
    # A reused or banked unit is an ok outcome that cost nothing; writing it to
    # the ledger now is what makes "a success is never regenerated" survive a
    # restart -- the next dispatch sees the same picture instead of re-deriving
    # it from scratch. Both sets are already validated above (banked by
    # unit_store.validate_banked + the contract validator, reused by the
    # contract validator + the recorded input-hash snapshot), and neither has a
    # reservation to settle, which the settle helper tolerates by design.
    _settle_unit_paid_attempts(
        run_dir, phase_id,
        [(k, "ok", ["banked: prior output re-validated, no paid attempt"])
         for k in sorted(_banked_keys)] +
        [(k, "ok", ["reused: validated on-disk output, no paid attempt"])
         for k in sorted(reuse) if k not in _banked_keys],
        worker_id=worker_id)
    # ------------------------------------------------------------------
    # PRES-014: bounded admission BATCHES. The enumerated unit list is split
    # into batches of at most `batch_width` (migrated from the legacy
    # max_units; a manifest that declares batch_width directly wins). Each
    # batch is one fanout.run_units call, so per-slide QC still covers EVERY
    # slide exactly once across ceil(N/width) batches -- the width bounds
    # CONCURRENCY, never coverage. retry_cap stays 1 (the phase-level
    # sweep/verify loop owns retries; a unit-level inner retry would double-
    # bill on a deadline the sweep already governs).
    # ------------------------------------------------------------------
    batch_widths = [b for b in (batch_width, len(pending_items)) if b]
    all_pending_units = [fanout.Unit(key=it["key"], payload=by_key.get(it["key"], it))
                         for it in pending_items]
    admission_batches = _us.plan_batches(all_pending_units, batch_width) if _us \
        else [all_pending_units]
    for _b_i, _batch in enumerate(admission_batches, 1):
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": 0, "status": "fanout_batch_admit",
            "batch": _b_i, "batch_size": len(_batch),
            "batches_total": len(admission_batches),
        })
        if _us is not None:
            for _u in _batch:
                _rec = _store_state.get(_u.key)
                _prior = _rec if isinstance(_rec, dict) else {}
                _next = dict(_prior)
                _next["status"] = "admitted"
                _next["revision"] = int(_prior.get("revision") or 0) + 1
                _next["input_hash"] = _unit_input_hashes.get(_u.key, "")
                # attempts_total counts ACTUAL author calls only -- it is
                # incremented at RESULT time by r.attempts (admission alone
                # spends nothing; PRES-014: no restart resets this ledger).
                _us.stamp_identity(_next, company_id=_company_id,
                                   presentation_id=_presentation_id,
                                   phase_id=phase_id)
                _store_state[_u.key] = _next
                _us.append_transition(
                    run_dir, phase_id, _u.key,
                    from_status=str(_prior.get("status")),
                    to_status="admitted",
                    reason=f"batch {_b_i}/{len(admission_batches)} admitted",
                    company_id=_company_id, presentation_id=_presentation_id,
                    revision=_next["revision"],
                    input_hash=_next["input_hash"],
                    attempts_total=int(_prior.get("attempts_total") or 0))
            _us.save_state(run_dir, phase_id, _store_state,
                           company_id=_company_id, presentation_id=_presentation_id)
        batch_results = fanout.run_units(
            _batch, _unit_worker,
            workers=effective_workers, run_dir=run_dir, phase_id=phase_id,
            per_unit_timeout_s=SINGLE_ATTEMPT_BUDGET_S, retry_cap=1,
            deadline_s=deadline_s)
        # Durable per-unit records: append one transition per result, then
        # atomically update the state map. The scratch output is hash-stamped
        # at RECORD time (banked validation re-hashes at ADMISSION time) --
        # a restart between the two reads sees the honest file on disk.
        if _us is not None:
            for r in batch_results:
                _rec = _store_state.get(r.key)
                _prior = _rec if isinstance(_rec, dict) else {}
                _next = dict(_prior)
                _next["revision"] = int(_prior.get("revision") or 0) + 1
                _next["input_hash"] = _unit_input_hashes.get(r.key, "")
                _next["attempts_total"] = int(_prior.get("attempts_total") or 0) \
                    + int(r.attempts or 0)
                _next["status"] = "ok" if r.status == "ok" else "failed"
                _next["updated_at"] = _heal.utcnow() if hasattr(_heal, "utcnow") \
                    else time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                if r.target:
                    _next["output_path"] = r.target
                    _out = run_dir / r.target
                    if r.status == "ok" and _out.is_file():
                        _next["output_hash"] = _us.file_sha256(_out)
                if r.meta and isinstance(r.meta, dict):
                    _next["author_route"] = r.meta
                if r.status != "ok" and r.reasons:
                    _next["last_error"] = "; ".join(r.reasons)[:500]
                else:
                    # PD-TEST-065: `last_error` means "the CURRENT error". A unit
                    # that just came back ok must not keep advertising its
                    # previous attempt's failure: the re-attempt decision in
                    # _unit_worker reads this record, and a stale marker would
                    # silently step down the reasoning effort for a unit that
                    # has since succeeded. Set to the store's own empty shape
                    # (unit_store.py's new-unit record) rather than deleting the
                    # key, so every record keeps the same field set.
                    _next["last_error"] = None
                _us.stamp_identity(_next, company_id=_company_id,
                                   presentation_id=_presentation_id,
                                   phase_id=phase_id)
                _store_state[r.key] = _next
                _us.append_transition(
                    run_dir, phase_id, r.key,
                    from_status="admitted",
                    to_status=_next["status"],
                    reason=("; ".join(r.reasons)[:300] if r.status != "ok"
                            else f"unit ok (attempt {r.attempts})"),
                    company_id=_company_id, presentation_id=_presentation_id,
                    revision=_next["revision"], input_hash=_next["input_hash"],
                    output_hash=str(_next.get("output_hash") or ""),
                    route=r.meta if isinstance(r.meta, dict) else None,
                    attempts_total=_next["attempts_total"])
            _us.save_state(run_dir, phase_id, _store_state,
                           company_id=_company_id,
                           presentation_id=_presentation_id)
        # PD-TEST-124: settle this batch's paid reservations and record each
        # unit's durable outcome IN ONE atomic fold. This runs whether or not a
        # unit store exists, because it is the PAID ledger's own record:
        #   * a reservation whose unit came back is marked settled, so the next
        #     dispatch of that unit may reserve again while a duplicate call
        #     carrying the same token stays a no-op forever;
        #   * the outcome ("ok"/"failed" + its reasons) is what the next
        #     dispatch reads to keep a success from being regenerated and to
        #     retry only the units that actually failed.
        _settle_unit_paid_attempts(
            run_dir, phase_id,
            [(r.key, r.status, list(r.reasons or [])) for r in batch_results],
            worker_id=worker_id)
        results.extend(batch_results)
    _ordered = {r.key: r for r in results}
    results = [_ordered[it["key"]] for it in wanted_items if it["key"] in _ordered]

    failed = [r for r in results if r.status != "ok"]
    for r in results:
        fanout.append_unit_ledger_row(run_dir, phase_id, {
            "unit": r.key, "status": r.status, "attempts": r.attempts,
            "target": r.target, "reasons": r.reasons,
            # the scratch path this row's NEXT dispatch reuses from
            "reuse_key": str(fanout.unit_output_path(
                run_dir, phase_id, r.key).relative_to(run_dir)),
            # the input-hash snapshot this output was produced against
            "unit_inputs": by_key.get(r.key, {}).get("unit_inputs"),
            "banked": r.key in _banked_keys,
            **({"meta": r.meta} if r.meta else {}),
        })
    if failed:
        # PRES-014: a phase sweep where SOME units are ok (banked or authored
        # this call) and SOME failed is a PARTIAL FAILURE, not an exhaustion
        # of the whole phase. The phase-level sweep/verify loop may retry the
        # phase; on that retry the ok units validate as banked (no re-bill)
        # and only the failed ones resubmit -- the exact "first run 20 units
        # with 1 failure -> retry exactly 1, not 20" acceptance. Returning
        # status "ok" would let the Engine mark the phase done over failing
        # units, so the honest intermediate status is "partial": a real
        # failure signal that also records the attempt trail.
        reasons = [f"{r.key}: {'; '.join(r.reasons) or 'failed'}" for r in failed]
        _ok_part = [r for r in results if r.status == "ok"]
        _append_sidecar(run_dir, phase_id, {
            "worker": worker_id, "attempt": sum(r.attempts for r in results),
            "status": "partial_failure", "failed_units": [r.key for r in failed],
            "ok_units": [r.key for r in _ok_part],
            "banked_units": sorted(_banked_keys),
            "reasons": reasons,
            "workers": effective_workers, "routed_width": routed_width,
            "capacity_status": routing.get("capacity_status"),
            "reused_units": sorted(reuse),
            "batches": len(admission_batches),
        })
        return DispatchResult(phase_id, "partial_failure" if _ok_part else "exhausted",
                              sum(r.attempts for r in results), reasons,
                              slide_results=[
                                  {"slide_id": by_key.get(r.key, {}).get("slide_id"),
                                   "ordinal": by_key.get(r.key, {}).get("ordinal"),
                                   "status": r.status,
                                   "error": "; ".join(r.reasons) or r.status}
                                  for r in results if r.status != "ok"])

    # Aggregate under the CONTRACT's own reducer — the exactly-once ordered
    # Markdown reducer for P4-COPY/P9-SPEECH, the union-by-stable-slide_id
    # reducer for QC, the bounded A/B/C three-variant builder for the style
    # spec, ordered text join for the design prompts. The legacy generic
    # dict.update remains ONLY on the PRESENTATION_UNIT_CONTRACTS=0 rollback
    # path (or for a phase with no contract, which preflight already refused).
    ordered_parts: List[Tuple[Dict[str, Any], str]] = []
    for r in results:  # run_units returns INPUT order — merge order (S2.1)
        text: Optional[str] = reuse.get(r.key)
        if text is None and r.target:
            scratch = run_dir / r.target
            if scratch.is_file():
                text = scratch.read_text(encoding="utf-8",
                                         errors="replace").strip()
        if text is None:
            text = ""
        payload = by_key.get(r.key, {})
        payload = {**payload, "route_request_id":
                   (r.meta or {}).get("request_id") if isinstance(r.meta, dict) else None,
                   "reviewer_role": owning_role}
        ordered_parts.append((payload, text))
    if unit_contracts_enabled() and contract is not None:
        merged_text: Optional[str] = contract.reducer(ordered_parts)
    else:
        merged_text = _aggregate_fanout_parts(
            phase_id, [t for _p, t in ordered_parts])
    if not merged_text:
        reason = ("fanout units produced output that could not be aggregated "
                  "under the phase UnitContract — a duplicate/missing ordinal "
                  "or slide_id, or an out-of-scope unit — refusing to write a "
                  "broken artifact (see per-unit files under working/fanout/)")
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


# ---------------------------------------------------------------------------
# PD-TEST-080 -- a park marker must not outlive the dispatcher that wrote it.
#
# `_park_blocked` records `worker: dispatcher-<pid>-<uuid8>`, the exact id
# watch_run_dir mints for itself, so the marker names its own owner. Reader
# side, phases.readmit_retryable_phases treated the bare EXISTENCE of that file
# as "a dispatcher owns this generation's durable budget" and skipped the phase
# -- true while the writer lives, FALSE once it is gone, which is the ordinary
# end state of a run: a dispatcher's last act after state.terminal is set is to
# exit, leaving the marker it wrote with no owner. Measured on
# pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4 -- five quarantined phases
# parked by pids 55801 / 71266 / 87833, every one of them dead, terminal
# BLOCKED -- no --resume could re-admit them, so the run re-parked identically:
# precisely the failure PD-TEST-060 (phases.py:654-675) was written to end.
#
# LIVENESS IS NOT THE WHOLE QUESTION. POSIX recycles pids, so a dead
# dispatcher's pid can be held by an unrelated process; "the pid resolves" is
# not "the owner is here". The marker's own `blocked_at` is the discriminator
# its writer cannot fake: that line was written BY the owner WHILE IT EXISTED,
# so a live process at that pid which STARTED LATER cannot be the author.
# autospawn._process_start_epoch supplies the live start (reusing the one
# module that owns pid questions, so the two can never disagree), and
# autospawn._pid_is_alive supplies the liveness test.
#
# EVERY DOUBT RESOLVES TO LIVE. No worker line, no timestamp, no `ps`,
# unparseable output, our own pid -- all "live". Honouring a marker too long is
# the fail-closed direction: it cannot spend a provider call (the paid ceiling
# is the LEDGER, enforced by should_dispatch/_reserve_paid_attempt, neither of
# which this decision touches), while ignoring a marker whose owner is still
# working would be the protection being weakened.
# ---------------------------------------------------------------------------
_PARK_MARKER_WORKER_RE = re.compile(
    r"^worker:\s*dispatcher-(\d+)-[0-9a-fA-F]{4,32}\s*$", re.M)
_PARK_MARKER_BLOCKED_AT_RE = re.compile(r"^blocked_at:\s*(\S+)\s*$", re.M)

# utcnow() has one-second resolution, and _process_start_epoch never returns a
# start LATER than the real one, so a true owner can appear at most ~1 s after
# its own `blocked_at`. A recycled pid would have to take the pid within this
# window of the park to be mistaken for the owner -- and that mistake is the
# fail-closed one. Anything later is proof of recycling.
_PARK_MARKER_RECYCLE_GRACE_S = 5.0


def _park_marker_blocked_epoch(text: str) -> Optional[float]:
    """The marker's `blocked_at` as an epoch, or None when absent/unreadable."""
    m = _PARK_MARKER_BLOCKED_AT_RE.search(text or "")
    if not m:
        return None
    try:
        from datetime import datetime
        return datetime.fromisoformat(
            m.group(1).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


def park_marker_owner_state(run_dir: Path, phase_id: str) -> Tuple[str, str]:
    """Adjudicate who owns this phase's dispatcher park marker RIGHT NOW.

    Returns (state, detail), state one of:
      "absent"   -- no marker on disk; nothing to honour.
      "live"     -- a marker exists and its owner process is still running.
      "orphaned" -- a marker exists and the dispatcher that wrote it is gone.
      "unknown"  -- a marker exists but ownership cannot be established; the
                    caller MUST treat this as live (fail closed).

    Read-only: nothing here deletes or rewrites the marker -- acting on the
    verdict is phases.readmit_retryable_phases' job."""
    marker = _blocked_marker_path(run_dir, phase_id)
    try:
        if not marker.is_file():
            return "absent", "no dispatcher park marker"
        text = marker.read_text(encoding="utf-8")
    except OSError as exc:
        return "unknown", f"park marker unreadable ({exc.__class__.__name__})"
    m = _PARK_MARKER_WORKER_RE.search(text)
    if not m:
        # A hand-written or pre-PD-TEST-080 marker with no owner line: there is
        # no pid to adjudicate, so the honest answer is "not established".
        return "unknown", "park marker names no dispatcher worker"
    pid = int(m.group(1))
    worker = m.group(0).split(":", 1)[1].strip()
    if pid == os.getpid():
        return "live", f"{worker} is this process"
    if not _autospawn._pid_is_alive(pid):
        return "orphaned", (f"owner {worker} is gone: pid {pid} names no "
                            "process")
    started = _autospawn._process_start_epoch(pid)
    blocked_at = _park_marker_blocked_epoch(text)
    if started is None or blocked_at is None:
        return "live", (f"owner {worker} is alive (pid {pid}); its start could "
                        "not be compared with the park timestamp, so the park "
                        "is honoured")
    if started > blocked_at + _PARK_MARKER_RECYCLE_GRACE_S:
        return "orphaned", (
            f"owner {worker} is gone and its pid was recycled: the process "
            f"holding pid {pid} started {started - blocked_at:.0f}s AFTER the "
            "park was written")
    return "live", f"owner {worker} is alive (pid {pid})"


def running_worker_owner_state(run_dir: Path, phase_id: str) -> Tuple[str, str]:
    """Adjudicate whether the dispatcher worker that last serviced this phase is
    still there to finish it. The exact counterpart of `park_marker_owner_state`
    for a phase the Engine still calls `running`.

    WHY THIS EXISTS (PD-TEST-155). `Engine._ready_queue_tick()` skips any phase
    whose status is `running` -- it is collected into the `running` bucket and
    `continue`d, never re-planned and never expired. That is correct while an
    engine is genuinely working the phase, but nothing ever revisits it when the
    engine that owned it died mid-wait: the phase stays `running` forever,
    `_phase_terminal_bad` does not apply to it (so its descendants are not even
    quarantined, they just `waiting_dependency` on it), and the run becomes INERT
    with a full queue and zero dispatches. Measured on pres-operator-1d269693:
    three phases stranded `running` by a killed engine, `waited_seconds` frozen,
    0 provider requests for 11 minutes, 29 pending phases all downstream.

    WHICH ATTEMPT ARE WE ADJUDICATING? (independent review of PR #1161, F1.)
    The ledger holds TWO different owner records, and they name DIFFERENT
    attempts, so a worker must never be judged against the other one's clock:

      * `last_reservation_worker` + `last_reserved_at` -- written by
        `_reserve_paid_attempt` BEFORE the transport call, and DELIBERATELY
        erased by the next `record_outcome` rebuild (see the PD-TEST-092 note on
        that dict). They therefore exist ONLY while an attempt is genuinely IN
        FLIGHT, and they are the authoritative pair for "who is working now".
      * `worker` + `last_seen_at` -- written by `record_outcome` at outcome-fold
        time, and consistent with EACH OTHER. They name the last SETTLED attempt.

    The first version of this function read only the second pair. Mid-dispatch,
    that pair still names the PREVIOUS attempt while the pid it records may since
    have been recycled by the CURRENT dispatcher -- whose start is then LATER than
    the stale `last_seen_at`, so the pid-reuse guard fired and a phase with a live
    worker was reported "orphaned". The guard was reading a stale record and
    comparing it against the wrong clock. Selecting the pair FIRST fixes that by
    construction: a worker is only ever compared with the timestamp written
    alongside it.

    Returns (state, detail), state one of:
      "absent"   -- no ledger row, so no worker is claimed; nothing to honour.
      "live"     -- the governing record names a worker pid that is still running.
      "orphaned" -- the governing record names a worker pid that is gone (or was
                    recycled -- i.e. the pid now belongs to a process that started
                    after the record was written).
      "unknown"  -- ownership cannot be established; the caller MUST treat this
                    as live (fail closed). A degraded install must never start
                    reclaiming phases out from under a live worker.

    Read-only, exactly like `park_marker_owner_state`: acting on the verdict is
    the caller's job, and the caller must NOT touch the paid ledger."""
    path = _ledger_path(run_dir, phase_id)
    try:
        if not path.is_file():
            return "absent", "no dispatch ledger for this phase"
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return "unknown", f"dispatch ledger unreadable ({exc.__class__.__name__})"
    except json.JSONDecodeError:
        return "unknown", "dispatch ledger is not valid JSON"
    record = raw if isinstance(raw, dict) else {}
    if not record:
        return "unknown", "dispatch ledger holds no record to adjudicate"

    # Pick the owner record and ITS OWN timestamp together. See the docstring:
    # mixing a worker from one attempt with a timestamp from another is the exact
    # defect this selection exists to prevent.
    worker = str(record.get("last_reservation_worker") or "").strip()
    stamp = record.get("last_reserved_at")
    phase_of_attempt = "in-flight"
    if not (worker and stamp):
        worker = str(record.get("worker") or "").strip()
        stamp = record.get("last_seen_at") or record.get("updated_at")
        phase_of_attempt = "settled"

    m = re.match(r"^dispatcher-(\d+)-[0-9a-fA-F]{4,32}$", worker)
    if not m:
        # A row with no parseable worker (an older shape, or a hand-written
        # record): there is no pid to adjudicate, so the honest answer is
        # "not established".
        return "unknown", (f"{phase_of_attempt} ledger worker {worker!r} names no "
                           "adjudicable dispatcher pid")
    pid = int(m.group(1))
    if pid == os.getpid():
        return "live", f"{worker} is this process"
    if not _autospawn._pid_is_alive(pid):
        return "orphaned", (f"the {phase_of_attempt} worker {worker} is gone: "
                            f"pid {pid} names no process")
    try:
        from datetime import datetime
        seen_epoch = datetime.fromisoformat(
            str(stamp).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError, OverflowError):
        seen_epoch = None
    started = _autospawn._process_start_epoch(pid)
    if started is None or seen_epoch is None:
        return "live", (f"{phase_of_attempt} worker {worker} is alive (pid "
                        f"{pid}); its start could not be compared with its own "
                        "ledger timestamp, so the worker is honoured")
    if started > seen_epoch + _PARK_MARKER_RECYCLE_GRACE_S:
        return "orphaned", (
            f"the {phase_of_attempt} worker {worker} is gone and its pid was "
            "recycled: the process "
            f"holding pid {pid} started {started - seen_epoch:.0f}s AFTER the "
            "ledger was last written")
    return "live", f"worker {worker} is alive (pid {pid})"


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


@contextlib.contextmanager
def _phase_budget_transaction(run_dir: Path, phase_id: str):
    """Serialize every mutation of a phase's paid-budget ledger.

    Atomic replacement prevents torn JSON, but it does not serialize a
    read/modify/write cycle.  The reset issuer, pre-transport reservation, and
    outcome fold must therefore all hold this *same* lock from their read
    through their final ledger replacement.
    """
    lock_path = _ledger_path(run_dir, phase_id).with_suffix(".budget.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def _phase_budget_locked(fn):
    """Apply the shared ledger transaction to a (run_dir, phase_id) writer."""
    @functools.wraps(fn)
    def guarded(run_dir: Path, phase_id: str, *args, **kwargs):
        with _phase_budget_transaction(run_dir, phase_id):
            return fn(run_dir, phase_id, *args, **kwargs)
    return guarded


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


def _approved_input_revision(run_dir: Path, phase_id: Optional[str] = None) -> str:
    """Return the durable budget-reset witness for this run.

    Rewriting a work order is a request to retry, not evidence that the model
    now has different approved inputs.  The one sanctioned mutable input after
    launch is an intake amendment.  It may reset a paid phase's budget only
    when the replacement intake still matches an amendment row and that row
    passes the same owner-approval oracle used by launcher.apply_intake_amendment.

    An unreadable, hand-written, or unverified row deliberately has no power
    here: it remains the original budget generation.  This is best-effort and
    fail-closed; a broken approval oracle cannot buy more provider attempts.
    """
    intake = run_dir / "working" / "copy" / "intake.json"
    amendments = run_dir / "working" / "copy" / "intake_amendments.jsonl"
    try:
        digest = hashlib.sha256(intake.read_bytes()).hexdigest()
        rows = [json.loads(line) for line in amendments.read_text(encoding="utf-8").splitlines()
                if line.strip()]
    except (OSError, json.JSONDecodeError):
        return "initial"
    for row in reversed(rows):
        if not isinstance(row, dict) or row.get("kind") != "intake_amendment":
            continue
        if row.get("intake_sha256") != digest:
            continue
        try:
            from presentation_job import launcher
            approved, _detail = launcher.verify_amendment_approval(
                {"approval": row.get("approval") or {}}, run_dir)
        except Exception:  # noqa: BLE001 -- no verified witness, no reset
            approved = False
        if approved:
            return f"approved-intake:{digest}"
    return "initial"


class PaidBudgetExhausted(DeepSeekCallError):
    """No provider transport may start after the durable paid-attempt cap."""


class PaidAttemptDeferred(DeepSeekCallError):
    """This ONE attempt may not start yet -- and no budget was spent.

    Raised in three situations, all of which are scheduling decisions rather
    than exhausted budgets (PD-TEST-124):

      * FIRST-ATTEMPT FAIRNESS: an admitted sibling unit has not had its first
        paid attempt yet, and this call was a retry. The unit is not failed --
        it is queued behind a first attempt that must not be starved.
      * NOT ADMITTED: the phase's declared bounded total could not fund this
        unit's first attempt at all; the ledger records why, by name.
      * DOUBLE-RESERVE: the unit already has an in-flight paid reservation
        owned by a live process.

    A deferral is deliberately a DIFFERENT type from PaidBudgetExhausted so the
    two are distinguishable in a sidecar: an exhausted budget parks the phase,
    a deferral resolves itself as soon as the sibling's first attempt is made.
    """


def _repair_receipt_path(run_dir: Path, phase_id: str) -> Path:
    return _ledger_path(run_dir, phase_id).with_suffix(".repair-receipt.json")


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# The ONE kind string for the local-operator repair receipt.  Issued by
# authorize_paid_retry_reset, validated by _repair_receipt_is_actionable, both
# reading THIS constant so the writer and the reader cannot drift.
DISPATCH_REPAIR_RECEIPT_KIND = "local-operator-paid-retry-reset-v1"


def _read_repair_receipt(run_dir: Path, phase_id: str) -> Dict[str, Any]:
    """The repair receipt's bytes, or {} when absent/unreadable/not an object.

    ONE reader, so the read-only gate and the reserve consumer cannot disagree
    about what "the receipt on disk" means.  An unreadable receipt is an absent
    receipt: no clause downstream may treat a parse failure as permission.
    """
    try:
        obj = json.loads(_repair_receipt_path(run_dir, phase_id).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return obj if isinstance(obj, dict) else {}


def _repair_receipt_is_actionable(led: Dict[str, Any], phase_id: str, run_dir: Path,
                                  *, approved_input_revision: Optional[str] = None
                                  ) -> Tuple[bool, str]:
    """THE single receipt-versus-ledger validation, shared by BOTH the read-only
    dispatch gate (should_dispatch) and the one and only consumer
    (_reserve_paid_attempt).  Returns (True, <truthful reason>) only when the
    receipt on disk may lift this phase's paid-budget block; (False, <why not>)
    otherwise.

    WHY IT IS SHARED (PD-TEST-068).  The two callers used to hold separate
    copies of this predicate -- and the gate's copy was EMPTY.  The receipt was
    read in exactly one place, _reserve_paid_attempt, which every claim path
    reaches only AFTER should_dispatch has said yes; should_dispatch refused on
    the exhausted branch before consulting anything, so a valid unconsumed
    receipt could never lift the very gate that blocks its own consumption.
    Observed live: receipt issued rc=0, six 30s samples over ~2.5 minutes with
    zero consumption, zero dispatch, zero provider requests, ledger unchanged
    (status=exhausted, paid_attempts=3, generation=0,
    repair_receipt_consumed=False).  One predicate, two call sites, makes that
    divergence unrepresentable.

    PURE READ.  It never writes, never consumes and never mutates the ledger;
    should_dispatch's three call sites rely on that.  Consumption happens only
    in _reserve_paid_attempt, under the phase's budget transaction.

    Every clause is fail-closed and every refusal names itself:
      * a ledger must exist and carry a durable integer generation (a missing one
        cannot satisfy any receipt's prior_generation). Single-use is enforced by the
        generation clause below, NOT by a consumed flag -- see PD-TEST-092 above;
      * the receipt must be readable, of kind
        'local-operator-paid-retry-reset-v1', and issued for THIS phase and THIS
        resolved run directory;
      * its allowance must be a positive int within PHASE_TOTAL_PAID_HARD_CAP
        (PD-TEST-182: the SAME ceiling the producer enforces, so the two can
        never drift apart again);
      * its prior_generation must be the ledger's CURRENT generation, so a
        receipt can never re-arm a generation it was not issued against;
      * its approved_input_revision must be the CURRENT one, so a receipt can
        never outlive the input it was issued for;
      * its operator_uid must be the OS owner of the run directory;
      * its dispatcher_sha256 must be the hash of the dispatcher source running
        RIGHT NOW, so a receipt cannot survive the code change it was not issued
        for (stale receipt => refused; re-issue after the repair is deployed).
    """
    if not led:
        return False, "no dispatch ledger for this phase"
    # PD-TEST-092: this used to gate on the bare bool `repair_receipt_consumed`, which
    # made ONE consumed receipt a LIFETIME latch on the phase: every later receipt was
    # refused with "paid-retry repair receipt already consumed" no matter how valid it
    # was, so a phase could only ever be repaired once and P4-COPY's paid budget could
    # never be reopened. The latch is REDUNDANT for its stated purpose, because the
    # generation clause below already makes each receipt single-use:
    #   * consumption is the ONLY writer of the ledger generation
    #     (_reserve_paid_attempt: led["generation"] = generation + 1) and that is the
    #     only increment anywhere in the package, so the generation never repeats;
    #   * a receipt must carry prior_generation == the ledger's CURRENT generation;
    # therefore the instant a receipt is consumed the generation advances and that same
    # receipt can never match again -- in this process or any later one. The bool is
    # still WRITTEN on consumption as an audit record of which receipt was spent (see
    # repair_receipt / repair_receipt_consumed_generation beside it); it is simply no
    # longer a gate. Measured on the live run: with the latch flipped to False and
    # nothing else changed the predicate returns True, and an already-spent receipt is
    # still refused by the generation clause -- exactly-once survives, the latch does not.
    receipt = _read_repair_receipt(run_dir, phase_id)
    if not receipt:
        return False, "no readable paid-retry repair receipt on disk"
    if receipt.get("kind") != DISPATCH_REPAIR_RECEIPT_KIND:
        return False, (f"repair receipt kind is not {DISPATCH_REPAIR_RECEIPT_KIND}")
    if receipt.get("phase_id") != phase_id:
        return False, "repair receipt is for a different phase"
    if receipt.get("run") != str(run_dir.resolve()):
        return False, "repair receipt is for a different run"
    allowance = receipt.get("allowance")
    # PD-TEST-182: the SAME ceiling the producer enforces. Leaving this at
    # DISPATCH_RETRY_CAP would have made the fix inert -- authorize_paid_retry_reset
    # would ISSUE a receipt for an 8-unit fan-out and this validator would then
    # REJECT it as invalid, so the fan-out would still never re-author.
    if (isinstance(allowance, bool) or not isinstance(allowance, int)
            or not 1 <= allowance <= PHASE_TOTAL_PAID_HARD_CAP):
        return False, (f"repair receipt allowance is not an int in 1.."
                       f"{PHASE_TOTAL_PAID_HARD_CAP}")
    ledger_generation = led.get("generation")
    if isinstance(ledger_generation, bool) or not isinstance(ledger_generation, int):
        return False, "repair receipt has no durable ledger generation to bind to"
    if receipt.get("prior_generation") != ledger_generation:
        return False, "repair receipt does not match the ledger generation"
    revision = (_approved_input_revision(run_dir, phase_id)
                if approved_input_revision is None else approved_input_revision)
    if receipt.get("approved_input_revision") != revision:
        return False, "repair receipt does not match the approved input revision"
    try:
        run_owner_uid = run_dir.stat().st_uid
    except OSError:
        return False, "repair receipt owner could not be verified"
    if receipt.get("operator_uid") != run_owner_uid:
        return False, "repair receipt was not issued by the owner of this run"
    if receipt.get("dispatcher_sha256") != _file_sha(Path(__file__)):
        return False, "repair receipt does not match the running dispatcher source"
    return True, "valid unconsumed paid-retry repair receipt"


def authorize_paid_retry_reset(run_dir: Path, phase_id: str, *, allowance: int) -> Dict[str, Any]:
    """Local-operator control-plane action; never invoked from a work order.

    The OS owner of the run may issue one bounded repair receipt after a
    deployed code repair.  It is atomic and binds the current sealed intake,
    installed dispatcher bytes, and prior ledger generation before any marker
    can be cleared.  The dispatcher consumes it exactly once.
    """
    # PD-TEST-182 -- the ceiling is the PAID-BUDGET hard cap, NOT DISPATCH_RETRY_CAP.
    #
    # This receipt exists to fund RE-AUTHORING of the units a fan-out invalidates,
    # and its consumer refuses to act unless the allowance covers ALL of them
    # (`_n_units = len(wanted_items)`, then `if _allowance < _n_units` leaves the
    # bank INTACT). Capping the allowance at DISPATCH_RETRY_CAP (3) made the
    # requirement unsatisfiable for any fan-out larger than 3: on
    # pres-operator-1d269693 P4-PROMPT has 8 units, so the engine demanded
    # `allowance >= 8` while itself rejecting anything above 3, and its own
    # refusal text asked the operator to re-issue with a value it would refuse.
    # The run was therefore walled by an internal contradiction in its own
    # recovery path -- no operator action could clear it.
    #
    # This is PD-TEST-124's theme in the recovery instrument: the fair-budget work
    # gave the fan-out a bounded total of min(128, units + pool) precisely because
    # the legacy per-phase cap of 3 starved an 8-unit fan-out, but the receipt that
    # must fund the re-authoring was left on that same legacy ceiling.
    #
    # Spend stays bounded exactly as before: by PHASE_TOTAL_PAID_HARD_CAP (128),
    # the same ceiling `_declare_phase_paid_budget` already enforces, and by the
    # consumer's own `_allowance >= _n_units` check. The per-unit ceilings still
    # bind at dispatch time.
    if allowance < 1 or allowance > PHASE_TOTAL_PAID_HARD_CAP:
        raise ValueError(
            f"allowance must be 1..{PHASE_TOTAL_PAID_HARD_CAP} "
            f"(PHASE_TOTAL_PAID_HARD_CAP; it must cover the units the receipt "
            f"invalidates)")
    if os.getuid() != run_dir.stat().st_uid:
        raise PermissionError("local operator must own the run directory")
    with _phase_budget_transaction(run_dir, phase_id):
        led = _read_ledger(run_dir, phase_id)
        # A reset must be bound to an existing durable generation.  Treating a
        # missing field as generation zero would let a hand-created legacy
        # ledger satisfy a newly-issued receipt's default prior generation.
        if not isinstance(led.get("generation"), int):
            raise RuntimeError("paid retry reset requires a durable ledger generation")
        receipt = {"kind": DISPATCH_REPAIR_RECEIPT_KIND, "run": str(run_dir.resolve()),
                   "phase_id": phase_id, "approved_input_revision": _approved_input_revision(run_dir, phase_id),
                   "prior_generation": led.get("generation", 0), "dispatcher_sha256": _file_sha(Path(__file__)),
                   "allowance": allowance, "issued_at": utcnow(), "operator_uid": os.getuid()}
        target = _repair_receipt_path(run_dir, phase_id); target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(f".partial-{os.getpid()}"); tmp.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8"); os.replace(tmp, target)
        return receipt


# ---------------------------------------------------------------------------
# PD-TEST-124 -- the per-unit paid-attempt ledger, the bounded TOTAL budget and
# the first-attempt fairness rule. The behaviour these helpers implement is
# declared once in the policy block beside DISPATCH_RETRY_CAP.
#
# Every field name is a module constant read by BOTH the writer and every
# reader, so a rename cannot leave a half-migrated ledger behind.
# ---------------------------------------------------------------------------
LEDGER_PHASE_PAID_BUDGET = "phase_paid_budget"
LEDGER_UNIT_ADMISSION_ORDER = "unit_admission_order"
LEDGER_UNIT_NOT_ADMITTED = "unit_not_admitted"
LEDGER_UNIT_PAID_ATTEMPTS = "unit_paid_attempts"
LEDGER_UNIT_PAID_ATTEMPTS_GENERATION = "unit_paid_attempts_generation"
LEDGER_UNIT_PAID_ATTEMPTS_LIFETIME = "unit_paid_attempts_lifetime"
LEDGER_UNIT_OUTCOMES = "unit_outcomes"
LEDGER_UNIT_RESERVATIONS = "unit_reservations"
LEDGER_RESERVATION_TOKENS = "reservation_tokens"
# Bounded audit trail of charged logical-attempt tokens. 512 is far more than
# any one dispatch of any shipped phase can mint (the widest enumerates 100
# units) while keeping the ledger a bounded document.
_RESERVATION_TOKEN_HISTORY = 512
# Fallback for a ledger whose budget declaration could not be written (an
# unwritable run dir). Deliberately the LEGACY number, so a broken declaration
# degrades to the pre-PD-TEST-124 behaviour instead of inventing a wider bound.
_PAID_BUDGET_UNDECLARED_CAP = DISPATCH_RETRY_CAP

_PAID_UNIT_SCOPE = threading.local()


@contextlib.contextmanager
def paid_unit_scope(unit_key: Optional[str], *, token: Optional[str] = None,
                    allow_reauthor: bool = False):
    """Bind the paid reservations made inside this block to ONE fan-out unit.

    Set by the fan-out unit worker around its dispatch_complete() call and read
    by _reserve_paid_attempt. Thread-local rather than global because units run
    concurrently in fanout.run_units' pool: each pool thread carries exactly the
    unit it is working on, and a nested call inside that unit's dispatch (a
    transport re-entry) sees the same unit -- which is what makes the token
    idempotency below correct.

    Outside a scope the reservation keeps the legacy phase-level behaviour
    byte-for-byte, so every serial phase is untouched by this repair.

    `token` identifies ONE LOGICAL paid attempt. Two reservations carrying the
    same token are the same attempt (a duplicate call) and the second is a
    no-op; two different tokens for one unit are two real attempts.

    `allow_reauthor=True` is set ONLY when the unit's own durable record says it
    succeeded before and it is being re-admitted because that success was
    invalidated (changed inputs, corrupt output, or an operator repair receipt
    that voided the bank). It is what keeps "a success is never regenerated"
    from also meaning "an invalidated success can never be repaired".
    """
    previous = (getattr(_PAID_UNIT_SCOPE, "unit_key", None),
                getattr(_PAID_UNIT_SCOPE, "token", None),
                getattr(_PAID_UNIT_SCOPE, "allow_reauthor", False))
    _PAID_UNIT_SCOPE.unit_key = unit_key
    _PAID_UNIT_SCOPE.token = (token or uuid.uuid4().hex) if unit_key else None
    _PAID_UNIT_SCOPE.allow_reauthor = bool(allow_reauthor) if unit_key else False
    try:
        yield getattr(_PAID_UNIT_SCOPE, "token", None)
    finally:
        (_PAID_UNIT_SCOPE.unit_key, _PAID_UNIT_SCOPE.token,
         _PAID_UNIT_SCOPE.allow_reauthor) = previous


def _current_paid_unit_key() -> Optional[str]:
    """The unit this thread is dispatching a paid call for, or None outside a
    fan-out unit scope."""
    key = getattr(_PAID_UNIT_SCOPE, "unit_key", None)
    return str(key) if key else None


def _current_paid_unit_token() -> Optional[str]:
    token = getattr(_PAID_UNIT_SCOPE, "token", None)
    return str(token) if token else None


def _paid_unit_allows_reauthor() -> bool:
    return bool(getattr(_PAID_UNIT_SCOPE, "allow_reauthor", False))


def _fanout_total_paid_cap(eligible_units: int) -> int:
    """The declared TOTAL paid-attempt bound for a fan-out phase with this many
    eligible units. Explicit and finite -- one funded first attempt per unit
    plus the legacy phase retry pool, clamped by the hard ceiling. Deliberately
    NOT `units * DISPATCH_RETRY_CAP`."""
    n = max(0, int(eligible_units or 0))
    return min(PHASE_TOTAL_PAID_HARD_CAP,
               n * FANOUT_FIRST_ATTEMPT_RESERVE_PER_UNIT + PHASE_RETRY_POOL_ATTEMPTS)


def _declared_paid_budget(led: Dict[str, Any],
                          generation: str) -> Optional[Dict[str, Any]]:
    """This phase's declared fan-out budget, or None for the legacy serial path.

    Generation-scoped exactly like the phase counter it sits beside: a budget
    declared for a superseded approved-input generation describes spending that
    generation no longer has, so it is simply not consulted."""
    budget = led.get(LEDGER_PHASE_PAID_BUDGET)
    if not isinstance(budget, dict):
        return None
    if str(budget.get("generation") or "initial") != str(generation):
        return None
    try:
        total = int(budget.get("total_cap"))
    except (TypeError, ValueError):
        return None
    return budget if total >= 1 else None


def _effective_phase_paid_cap(led: Dict[str, Any], generation: str) -> int:
    """DISPATCH_RETRY_CAP for a serial phase (unchanged), the declared total for
    a fan-out phase."""
    budget = _declared_paid_budget(led, generation)
    if budget is None:
        return _PAID_BUDGET_UNDECLARED_CAP
    return int(budget["total_cap"])


def _unit_paid_counts(led: Dict[str, Any], generation: str) -> Dict[str, int]:
    """Per-unit paid attempts for the CURRENT budget scope.

    A scope change starts a fresh count, mirroring the phase counter's own
    documented rule (`paid = ... if generation == prior_generation else 0`); the
    counters themselves are preserved -- `unit_paid_attempts_lifetime` is the
    never-reset audit total and the superseded counts are archived. Nothing in
    this repair zeroes or hand-edits a counter."""
    stored = led.get(LEDGER_UNIT_PAID_ATTEMPTS)
    if not isinstance(stored, dict):
        return {}
    if str(led.get(LEDGER_UNIT_PAID_ATTEMPTS_GENERATION) or "initial") \
            != _paid_attempt_scope(led, generation):
        return {}
    return {str(k): int(v) for k, v in stored.items()
            if isinstance(v, int) and not isinstance(v, bool) and v >= 0}


def _paid_attempt_scope(led: Dict[str, Any], generation: str) -> str:
    """The scope key the PER-UNIT paid counters belong to.

    Two things start a fresh per-unit count, and both are deliberate acts the
    PHASE counter already honours in exactly the same way:

      * the approved input revision changed (a verified intake amendment) --
         `paid_attempts`' own `generation == prior_generation` rule; and
      * an operator repair receipt was consumed, which bumps `led['generation']`
        and re-arms `paid_attempts` as `max(0, DISPATCH_RETRY_CAP - allowance)`.

    The second term is not optional. Without it a receipt would reopen the
    phase's TOTAL but leave a saturated unit pinned at its per-unit ceiling: the
    phase could re-dispatch and pay, yet the one unit that needs re-authoring
    could never be re-authored -- which is precisely the PD-TEST-119/120/121
    situation the receipt exists to resolve. Counters are never destroyed: the
    superseded counts are archived under
    `unit_paid_attempts_prior_generation` and `unit_paid_attempts_lifetime`
    keeps the never-reset total."""
    return f"{generation}|receipt-gen:{int(led.get('generation') or 0)}"


def _unit_outcome(led: Dict[str, Any], unit_key: str,
                  generation: str) -> Optional[Dict[str, Any]]:
    """This unit's durable outcome in the CURRENT generation, or None."""
    outcomes = led.get(LEDGER_UNIT_OUTCOMES)
    if not isinstance(outcomes, dict):
        return None
    rec = outcomes.get(unit_key)
    if not isinstance(rec, dict):
        return None
    if str(rec.get("generation") or "initial") != str(generation):
        return None
    return rec


def _unit_succeeded(led: Dict[str, Any], unit_key: str, generation: str) -> bool:
    rec = _unit_outcome(led, unit_key, generation)
    return bool(rec and rec.get("status") == "ok")


def _reservation_owner_is_gone(pid: Any) -> bool:
    """Fail-closed pid-liveness test: an unprovable death keeps the reservation
    (the same direction _autospawn decides park-marker ownership in)."""
    if isinstance(pid, bool) or not isinstance(pid, int):
        return False
    if pid == os.getpid():
        return False
    try:
        return not _autospawn._pid_is_alive(pid)
    except Exception:  # noqa: BLE001 -- no liveness answer is not "gone"
        return False


def _declare_phase_paid_budget(run_dir: Path, phase_id: str, *,
                               unit_keys: List[str],
                               worker_id: str) -> Dict[str, Any]:
    """Declare (or re-declare) this phase's bounded TOTAL paid budget and its
    first-attempt admission order.

    Idempotent, atomic (the same `_phase_budget_transaction` lock every other
    ledger writer takes) and it NEVER resets a counter: existing per-unit
    counts, lifetime counts, outcomes and reservations are carried forward
    untouched.

    Called by _dispatch_phase_fanout_units once per dispatch with the keys of
    the units that still need paid work. Banked and reused units are EXCLUDED --
    they cost nothing, so funding them would only shrink the pool available to
    the units that do.

    MONOTONIC WITHIN A GENERATION. `total_cap` is the max of the stored and the
    recomputed bound, so a later dispatch over fewer pending units cannot shrink
    the budget an earlier dispatch of the same generation already declared --
    that would strand units the retry pool is still paying for.

    CANNOT-FUND-ALL. With more eligible units than the bound can fund, the first
    `total_cap` keys in the given (deterministically enumerated) order are
    admitted, and every remaining unit is recorded in `unit_not_admitted` with a
    reason naming the bound, refused at reservation time, and reported in the
    phase's sidecar. No unit is ever silently dropped.
    """
    order = [str(k) for k in unit_keys if k]
    computed = _fanout_total_paid_cap(len(order))
    with _phase_budget_transaction(run_dir, phase_id):
        led = _read_ledger(run_dir, phase_id)
        generation = _approved_input_revision(run_dir, phase_id)
        stored = _declared_paid_budget(led, generation)
        # Monotonic within the generation, then clamped by the hard ceiling --
        # so neither a shrinking eligible set nor a hand-edited stored value can
        # raise the bound above the declared maximum.
        cap = computed
        if stored is not None:
            cap = max(int(stored.get("total_cap") or 0), computed)
        cap = min(PHASE_TOTAL_PAID_HARD_CAP, cap)
        admitted = order[:cap]
        reason = (
            f"not admitted: this phase's declared bounded TOTAL paid budget is "
            f"{cap} attempt(s) -- {len(order)} eligible unit(s) each owed one funded "
            f"first attempt, capped at PHASE_TOTAL_PAID_HARD_CAP="
            f"{PHASE_TOTAL_PAID_HARD_CAP} and funded by "
            f"FANOUT_FIRST_ATTEMPT_RESERVE_PER_UNIT="
            f"{FANOUT_FIRST_ATTEMPT_RESERVE_PER_UNIT} per unit plus a "
            f"{PHASE_RETRY_POOL_ATTEMPTS}-attempt retry pool. First attempts are "
            f"admitted in deterministic enumeration order and this unit falls "
            f"outside the bound, so it was NOT attempted (it did not fail)")
        not_admitted = {k: reason for k in order[cap:]}
        budget = {
            "policy": PHASE_PAID_BUDGET_POLICY,
            "generation": generation,
            "units_eligible": len(order),
            "units_admitted_first_attempt": len(admitted),
            "units_not_admitted": len(not_admitted),
            "first_attempt_reserve": FANOUT_FIRST_ATTEMPT_RESERVE_PER_UNIT,
            "retry_pool": PHASE_RETRY_POOL_ATTEMPTS,
            "total_cap": cap,
            "computed_cap": computed,
            "hard_cap": PHASE_TOTAL_PAID_HARD_CAP,
            "per_unit_cap": DISPATCH_RETRY_CAP,
            "declared_at": utcnow(),
            "declared_by": worker_id,
        }
        led.update({
            "phase_id": phase_id,
            "approved_input_revision": led.get("approved_input_revision") or generation,
            LEDGER_PHASE_PAID_BUDGET: budget,
            LEDGER_UNIT_ADMISSION_ORDER: admitted,
            LEDGER_UNIT_NOT_ADMITTED: not_admitted,
        })
        # A scope change (a new approved-input generation, or a consumed repair
        # receipt) starts a FRESH per-unit count -- the phase counter's own
        # rule, applied per unit. The superseded counts are preserved for audit
        # under their own key; they are never read for admission again.
        scope = _paid_attempt_scope(led, generation)
        stamp = str(led.get(LEDGER_UNIT_PAID_ATTEMPTS_GENERATION) or "initial")
        if stamp != scope:
            prior = led.get(LEDGER_UNIT_PAID_ATTEMPTS)
            if isinstance(prior, dict) and prior:
                led["unit_paid_attempts_prior_generation"] = {
                    "scope": stamp, "attempts": prior}
            led[LEDGER_UNIT_PAID_ATTEMPTS] = {}
            led[LEDGER_UNIT_PAID_ATTEMPTS_GENERATION] = scope
        if not isinstance(led.get(LEDGER_UNIT_PAID_ATTEMPTS), dict):
            led[LEDGER_UNIT_PAID_ATTEMPTS] = {}
        if not isinstance(led.get(LEDGER_UNIT_PAID_ATTEMPTS_LIFETIME), dict):
            led[LEDGER_UNIT_PAID_ATTEMPTS_LIFETIME] = {}
        if not isinstance(led.get(LEDGER_UNIT_OUTCOMES), dict):
            led[LEDGER_UNIT_OUTCOMES] = {}
        if not isinstance(led.get(LEDGER_UNIT_RESERVATIONS), dict):
            led[LEDGER_UNIT_RESERVATIONS] = {}
        _write_ledger(run_dir, phase_id, led)
        return {"budget": budget, "admitted": admitted,
                "not_admitted": not_admitted}


def _reserve_scoped_unit_attempt(led: Dict[str, Any], *, run_dir: Path,
                                 phase_id: str, worker_id: Optional[str],
                                 paid: int) -> int:
    """The PER-UNIT branch of _reserve_paid_attempt.

    Runs INSIDE the phase budget transaction, after the ledger has been read and
    any actionable repair receipt already consumed, with `paid` being the
    caller's generation- and receipt-adjusted PHASE count. Mutates `led` in
    place and returns the new phase count; the caller writes the ledger.

    Every refusal raises BEFORE mutating, so a refused attempt leaves no mark --
    the property should_dispatch's read-only call sites and the existing PD-068
    test both depend on."""
    unit_key = _current_paid_unit_key()
    token = _current_paid_unit_token() or ""
    generation = _approved_input_revision(run_dir, phase_id)
    budget = _declared_paid_budget(led, generation)
    cap = _effective_phase_paid_cap(led, generation)
    counts = _unit_paid_counts(led, generation)
    lifetime = led.get(LEDGER_UNIT_PAID_ATTEMPTS_LIFETIME)
    if not isinstance(lifetime, dict):
        lifetime = {}
    reservations = led.get(LEDGER_UNIT_RESERVATIONS)
    if not isinstance(reservations, dict):
        reservations = {}
    charged = {t for t in (led.get(LEDGER_RESERVATION_TOKENS) or [])
               if isinstance(t, str)}

    # (0) DUPLICATE CALL. This exact logical attempt has already been charged:
    # return without buying a second paid slot. This is what makes a re-entrant
    # or concurrent second call for one attempt idempotent.
    if token and token in charged:
        return paid

    # (1) A SUCCESS IS NEVER REGENERATED. The ledger's own durable ok outcome
    # refuses the attempt unless the fan-out worker proved the success was
    # INVALIDATED (changed inputs / corrupt output / a receipt that voided the
    # bank) -- in which case re-authoring is the whole point of the retry.
    if _unit_succeeded(led, unit_key, generation) and not _paid_unit_allows_reauthor():
        raise PaidAttemptDeferred(
            f"unit {unit_key} already succeeded in generation {generation!r}; "
            f"refusing to regenerate a completed unit (PD-TEST-124). A unit is "
            f"re-authored only when its success was invalidated.")

    # (2) THE DECLARED BOUND. The refusal names the policy's own numbers, so an
    # operator reading the sidecar sees which bound stopped the spend.
    if paid >= cap:
        raise PaidBudgetExhausted(
            f"phase paid budget exhausted: {paid} of the declared bounded total "
            f"{cap} provider attempt(s) for unchanged approved input "
            f"({PHASE_PAID_BUDGET_POLICY})")

    # (3) THE PER-UNIT CEILING -- DISPATCH_RETRY_CAP, the same number this
    # module has always used, now applied per unit instead of per phase. One
    # unit can never spend a sibling's budget.
    spent = int(counts.get(unit_key) or 0)
    if spent >= DISPATCH_RETRY_CAP:
        raise PaidBudgetExhausted(
            f"unit {unit_key} retry budget exhausted: {spent} provider attempt(s) "
            f"for unchanged approved input (DISPATCH_RETRY_CAP="
            f"{DISPATCH_RETRY_CAP}); sibling units keep their own budget "
            f"(PD-TEST-124)")

    # (4) CANNOT-FUND-ALL: a unit the declared bound could not fund is refused
    # by name, with the recorded reason, instead of consuming a slot the
    # admitted units are owed.
    if budget is not None:
        admitted = [str(k) for k in (led.get(LEDGER_UNIT_ADMISSION_ORDER) or [])]
        if admitted and unit_key not in admitted:
            why = (led.get(LEDGER_UNIT_NOT_ADMITTED) or {}).get(unit_key) or (
                "not admitted: outside this phase's bounded total paid budget")
            raise PaidAttemptDeferred(f"unit {unit_key} {why}")

    # (5) FIRST-ATTEMPT FAIRNESS. While any admitted unit still has ZERO paid
    # attempts, no unit may take a second or third. This is the rule that ends
    # sibling starvation: the retry of a failing unit can no longer preempt a
    # sibling's first attempt.
    if budget is not None:
        order = [str(k) for k in (led.get(LEDGER_UNIT_ADMISSION_ORDER) or [])]
        pending_first = [k for k in order
                         if int(counts.get(k) or 0) == 0
                         and not _unit_succeeded(led, k, generation)]
        if spent > 0 and pending_first:
            raise PaidAttemptDeferred(
                f"unit {unit_key} retry deferred: {len(pending_first)} admitted "
                f"sibling unit(s) have not had their first paid attempt yet "
                f"({', '.join(pending_first[:6])}"
                f"{', ...' if len(pending_first) > 6 else ''}); first attempts "
                f"have absolute priority (PD-TEST-124)")

    # (6) ATOMIC, DUPLICATE-SAFE RESERVATION. Held under the phase's own budget
    # lock, so two workers cannot interleave a read-modify-write and charge one
    # slot twice; the token makes a repeat of THIS attempt a no-op; an in-flight
    # reservation for the unit blocks a second concurrent attempt for it unless
    # its owner process is provably gone (pid-liveness takeover, the same idiom
    # the claim code uses for a dead claimant).
    scope = _paid_attempt_scope(led, generation)
    live = reservations.get(unit_key)
    if isinstance(live, dict) and live.get("state") == "reserved" \
            and str(live.get("generation") or "initial") == scope:
        if token and live.get("token") == token:
            return paid
        # PD-TEST-177 -- THIS THREAD'S OWN PREVIOUS ATTEMPT FOR THIS UNIT IS, BY
        # CONSTRUCTION, NO LONGER IN FLIGHT. A worker task runs one unit
        # sequentially, and a unit's retries all happen inside that one task
        # (parallel_prompt_worker._execute_slide's `while attempt < RETRY_CAP`
        # loop), so a reservation this same THREAD left for this same unit can
        # only be the attempt that just ended. Refusing it disabled the retry:
        # the reservation is settled only AFTER the whole wave returns
        # (_settle_unit_paid_attempts, called by _dispatch_prompt_phase_parallel),
        # so during the retry loop the attempt-1 reservation is still 'reserved'.
        # Measured on the shipped code: a 1-slide wave whose transport raises
        # HTTP 500 made ONE provider call and then reported `budget_deferred`
        # twice, where pre-PD-TEST-161 code made three and reported the real
        # `server_error` -- one transient 5xx/429/timeout lost the slide AND
        # mislabelled the cause.
        #
        # WHY (pid, thread) AND NOT worker_id: the prompt path calls
        # `dispatch_complete(system_prompt, user_prompt, phase_id=..., run_dir=...)`
        # -- worker_id is deliberately NOT passed (parallel_prompt_worker.py), so
        # it is None here and cannot identify an owner. Thread identity can:
        # threads are REUSED across units (ThreadPoolExecutor(thread_name_prefix=
        # "p4prompt"); p4prompt_0 handled slides 1 and 4 in one measured run), so
        # a thread name identifies no unit on its own -- but paired with the
        # `unit_key` this lookup is already keyed on, and this process's pid, it
        # identifies exactly "my own previous attempt at this unit".
        #
        # The guard's real job is unchanged: it stops TWO CONCURRENT attempts for
        # one unit. A different thread (even in this process), a different
        # process, or a reservation predating this field still refuses, because
        # `live.get("thread")` will not equal ours. Spend stays bounded by the
        # checks that already ran: the per-unit ceiling (`spent >=
        # DISPATCH_RETRY_CAP`) and the declared phase bound (`paid >= cap`).
        # Every replacement below still increments `seq` and `paid`.
        if not _reservation_owner_is_gone(live.get("pid")):
            raise PaidAttemptDeferred(
                f"unit {unit_key} already has an in-flight paid reservation "
                f"(attempt {live.get('seq')}, owner pid {live.get('pid')}, worker "
                f"{live.get('worker')!r}); refusing to double-reserve one unit's "
                f"attempt (PD-TEST-124)")

    seq = spent + 1
    counts[unit_key] = seq
    lifetime[unit_key] = int(lifetime.get(unit_key) or 0) + 1
    paid = int(paid) + 1
    reservations[unit_key] = {
        "token": token, "seq": seq, "worker": worker_id or "unknown",
        "pid": os.getpid(), "state": "reserved", "generation": scope,
        # PD-TEST-177: the reserving THREAD, so this unit's own in-run retry can
        # recognise its predecessor as finished (see the double-reserve guard
        # above) while a different thread or process still refuses. Absent on
        # rows written before this change, which therefore still refuse.
        "thread": threading.get_ident(),
        "reserved_at": utcnow(),
    }
    tokens = [t for t in (led.get(LEDGER_RESERVATION_TOKENS) or [])
              if isinstance(t, str)]
    if token:
        tokens.append(token)
    # A scope change is normally archived by _declare_phase_paid_budget, but a
    # repair receipt is consumed HERE -- after the declaration -- so the archive
    # is repeated on this path too. Audit history is never dropped.
    prior_stamp = str(led.get(LEDGER_UNIT_PAID_ATTEMPTS_GENERATION) or "initial")
    if prior_stamp != scope:
        prior_counts = led.get(LEDGER_UNIT_PAID_ATTEMPTS)
        if isinstance(prior_counts, dict) and prior_counts:
            led["unit_paid_attempts_prior_generation"] = {
                "scope": prior_stamp, "attempts": prior_counts}
    led.update({
        LEDGER_UNIT_PAID_ATTEMPTS: counts,
        # The SCOPE, not the bare revision: a receipt re-arms the per-unit
        # ceilings, so the stamp has to move with it or the counts would look
        # stale on the very next read and the caps would silently vanish.
        LEDGER_UNIT_PAID_ATTEMPTS_GENERATION: scope,
        LEDGER_UNIT_PAID_ATTEMPTS_LIFETIME: lifetime,
        LEDGER_UNIT_RESERVATIONS: reservations,
        LEDGER_RESERVATION_TOKENS: tokens[-_RESERVATION_TOKEN_HISTORY:],
        "paid_attempts": paid,
    })
    return paid


def _settle_unit_paid_attempts(run_dir: Optional[Path], phase_id: str,
                               outcomes: List[Tuple[str, str, List[str]]], *,
                               worker_id: str) -> None:
    """Settle one batch's paid reservations and record each unit's durable
    outcome, in ONE transaction.

    A settled reservation stays in the ledger as history: its `state` becomes
    "settled", so a later dispatch of the same unit may reserve again while a
    duplicate call carrying the SAME token stays a no-op forever. The outcome
    row is what later dispatches read to decide "this unit already succeeded --
    do not regenerate it" and "this unit failed -- retry it".

    Appended for every unit the batch reported, including banked/reused units
    with no reservation at all (their outcome is an honest ok at zero cost), so
    a restart sees the same picture. Never raises on a missing ledger: a phase
    with no ledger has nothing to settle."""
    if run_dir is None or not outcomes:
        return
    with _phase_budget_transaction(run_dir, phase_id):
        led = _read_ledger(run_dir, phase_id)
        if not led:
            return
        generation = _approved_input_revision(run_dir, phase_id)
        reservations = led.get(LEDGER_UNIT_RESERVATIONS)
        if not isinstance(reservations, dict):
            reservations = {}
        recorded = led.get(LEDGER_UNIT_OUTCOMES)
        if not isinstance(recorded, dict):
            recorded = {}
        counts = _unit_paid_counts(led, generation)
        scope = _paid_attempt_scope(led, generation)
        for unit_key, status, reasons in outcomes:
            unit_key = str(unit_key)
            live = reservations.get(unit_key)
            if isinstance(live, dict) and live.get("state") == "reserved" \
                    and str(live.get("generation") or "initial") == scope:
                settled = dict(live)
                settled["state"] = "settled"
                settled["settled_at"] = utcnow()
                settled["settled_status"] = str(status)
                reservations[unit_key] = settled
            recorded[unit_key] = {
                "status": "ok" if str(status) == "ok" else "failed",
                "unit_status": str(status),
                "generation": generation,
                "attempts": int(counts.get(unit_key) or 0),
                "reasons": [str(r) for r in (reasons or [])][:5],
                "at": utcnow(),
                "worker": worker_id,
            }
        led.update({LEDGER_UNIT_RESERVATIONS: reservations,
                    LEDGER_UNIT_OUTCOMES: recorded,
                    "phase_id": phase_id})
        _write_ledger(run_dir, phase_id, led)


def _reserve_paid_attempt(run_dir: Optional[Path], phase_id: str,
                          worker_id: Optional[str]) -> None:
    """Atomically reserve one provider call before transport.

    A reservation is intentionally never released: a process can die after
    sending bytes to a provider but before receiving/logging a response.  In
    that ambiguous case retaining the slot is the only no-double-charge policy.

    TWO MODES, ONE LEDGER. Outside a fan-out unit scope (every serial phase)
    this is the legacy phase-level reservation, unchanged. Inside a unit scope
    -- paid_unit_scope, set by the fan-out unit worker -- the same call is
    accounted PER UNIT against the phase's declared bounded total budget
    (PD-TEST-124): first-attempt fairness, the per-unit DISPATCH_RETRY_CAP
    ceiling, admission, and a token-keyed duplicate-safe reservation. The
    phase's `paid_attempts` total is incremented in both modes, so the declared
    bound and the legacy counter can never disagree about total spend.
    """
    if run_dir is None:
        return
    with _phase_budget_transaction(run_dir, phase_id):
        led = _read_ledger(run_dir, phase_id)
        generation = _approved_input_revision(run_dir, phase_id)
        prior_generation = str(led.get("approved_input_revision") or "initial")
        paid = int(led.get("paid_attempts") or 0) if generation == prior_generation else 0
        # A local-operator receipt is the only code-repair reset path.  Its
        # fields are rechecked at consumption by the SAME predicate the
        # read-only dispatch gate consults; an order file is never read.
        # PD-TEST-068: this function is the receipt's SINGLE consumer, and the
        # consumption below is the only place a receipt is ever spent.
        actionable, _why = _repair_receipt_is_actionable(
            led, phase_id, run_dir, approved_input_revision=generation)
        if actionable:
            # Exactly-once, and atomic.  authorize_paid_retry_reset writes the
            # receipt under THIS same _phase_budget_transaction lock, so the
            # bytes the predicate just proved are the bytes read here: no
            # re-derivation, no second validation copy.
            # PD-TEST-092: the durable claim that makes this exactly-once is the
            # GENERATION BUMP on the next line, NOT repair_receipt_consumed.  The
            # generation is the only field a receipt must match (it carries
            # prior_generation == the ledger's current generation), and bumping it
            # here is what strands this receipt permanently.  The bool below is an
            # audit record only; gating on it is what PD-TEST-092 removed, because
            # it latched the phase for life and made the paid budget unopenable a
            # second time.  Both fields are carried across outcome folds in
            # record_outcome's rebuild dict (cited by symbol, not by line: the
            # line moved once already and a stale offset is how this recurs).
            receipt = _read_repair_receipt(run_dir, phase_id)
            # PD-TEST-182: `paid = DISPATCH_RETRY_CAP - allowance` assumed the
            # allowance could never exceed DISPATCH_RETRY_CAP. With a fan-out
            # sized receipt (up to PHASE_TOTAL_PAID_HARD_CAP) it would go
            # NEGATIVE -- an 8-unit receipt would write paid_attempts = 3 - 8 = -5,
            # and a negative phase counter makes the `paid >= cap` bound
            # unsatisfiable, i.e. UNBOUNDED re-dispatch. The intent is to reopen
            # the phase total by `allowance`; clamped at zero, "reopen by more
            # than the cap" simply means "fully reopened", and the phase bound
            # still governs from there.
            paid = max(0, DISPATCH_RETRY_CAP - receipt["allowance"])
            led["generation"] = int(led.get("generation", 0)) + 1
            led["repair_receipt_consumed"] = True
            # PD-TEST-092: record the generation this receipt was spent FOR, so the
            # audit trail says which generation consumed it and a later reader never
            # has to infer it from the stored receipt's prior_generation.
            led["repair_receipt_consumed_generation"] = int(led.get("generation", 0)) - 1
            led["repair_receipt"] = receipt
        if worker_id:
            claim = _read_claim_record(_claim_path(run_dir, phase_id)) or {}
            if claim and str(claim.get("worker") or "") != worker_id:
                raise PaidBudgetExhausted("paid attempt refused: claim ownership changed")
        # PD-TEST-124: INSIDE a fan-out unit scope the budget is the phase's
        # declared BOUNDED TOTAL, accounted per unit (first-attempt fairness,
        # per-unit ceiling, admission, duplicate-safe reservation). OUTSIDE one
        # -- every serial phase -- the legacy phase-level clause below is
        # byte-for-byte unchanged, so no existing cap is weakened.
        unit_key = _current_paid_unit_key()
        if unit_key:
            paid = _reserve_scoped_unit_attempt(
                led, run_dir=run_dir, phase_id=phase_id,
                worker_id=worker_id, paid=paid)
        else:
            if paid >= DISPATCH_RETRY_CAP:
                raise PaidBudgetExhausted(
                    f"paid retry budget exhausted: {paid} provider attempts for unchanged "
                    f"approved input (DISPATCH_RETRY_CAP={DISPATCH_RETRY_CAP})")
            paid = paid + 1
        led.update({"phase_id": phase_id, "approved_input_revision": generation,
                    "paid_attempts": paid, "last_reserved_at": utcnow(),
                    "last_reservation_worker": worker_id or "unknown"})
        _write_ledger(run_dir, phase_id, led)
        # The new generation is durable before removing a prior park marker.
        if generation != prior_generation:
            try:
                _blocked_marker_path(run_dir, phase_id).unlink()
            except OSError:
                pass


def _backoff_delay_s(repeat: int) -> float:
    """repeat is the number of times this outcome has recurred AFTER its first
    observation. repeat<=0 (a new or changed outcome) is always zero delay.

    PD-TEST-095 -- SATURATE BY REPEATED MULTIPLICATION, NEVER BY A POWER.
    This used to be `min(CAP, BASE * (MULT ** (repeat - 1)))`. The power is
    evaluated BEFORE the min(), so it overflows float range before the cap can
    clamp it: at exponent 1024, `2.0 ** 1024` raises
    `OverflowError(34, 'Result too large')`. `repeat` is not bounded by the retry
    ceiling -- a work order that LINGERS on a phase whose status stopped changing
    is re-folded on every sweep tick, so `consecutive` climbs without limit (the
    live run reached 1025 on two phases).

    The consequence is a PERMANENT, SELF-LOCKING STALL, not a slow backoff:
    `record_outcome` computes the delay BEFORE it writes the ledger, so the raise
    aborts the fold and `consecutive` never advances past the boundary -- and
    because the exception escapes `sweep_run_dir`, EVERY phase in the run stops
    being dispatched. Measured on pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4:
    271 consecutive `sweep error: OverflowError(34, 'Result too large')` lines and
    zero dispatches, which is why a freshly issued P4-COPY repair receipt was
    never consumed.

    The result is `min(cap, base * mult**exp)` for every input this function can
    actually be called with (`repeat` is an int, and the sole call site passes
    `consecutive - 1` where `consecutive` is `int(...) + 1`), verified by sweeping
    the range: zero differences wherever the old expression returned a value. It is
    NOT bit-identical for out-of-contract inputs -- a non-integral float `repeat`,
    NaN, or a negative multiplier can differ -- and the docstring says so rather
    than claiming a universal equivalence it does not have.
    Above mult == 1 the loop stops as soon as the cap is reached, so it runs a
    handful of times and cannot overflow; at or below 1 the power is safe by
    construction and is used directly, so no path is O(repeat)."""
    if repeat <= 0:
        return 0.0
    if 0 <= DISPATCH_BACKOFF_MULTIPLIER <= 1:
        # A multiplier in [0, 1] cannot overflow a power: `mult ** n` either stays 1
        # (mult == 1) or underflows toward 0 (0 <= mult < 1), and both are finite for
        # any n. The range is checked EXPLICITLY rather than as `<= 1`, because a
        # NEGATIVE multiplier reaches this branch otherwise and `(-2.0) ** 1024`
        # raises the very OverflowError this function exists to prevent (found by
        # the delta re-review; unreachable today because the multiplier is the module
        # literal 2.0, but the guard should not depend on that being true forever). Use the power directly here so a non-growing
        # multiplier stays O(1) instead of walking `repeat` steps -- the value is
        # identical to the loop's, and the loop would be O(repeat) for mult < 1
        # because `delay < CAP` never becomes false on a decreasing sequence.
        # (Independent review of PR #1145 measured 0.25s for 1e7 steps at
        # mult == 1.0, i.e. ~25s at 1e9: correct but unbounded.)
        return min(DISPATCH_BACKOFF_CAP_S,
                   DISPATCH_BACKOFF_BASE_S
                   * (DISPATCH_BACKOFF_MULTIPLIER ** (repeat - 1)))
    delay = DISPATCH_BACKOFF_BASE_S
    steps = 0
    while delay < DISPATCH_BACKOFF_CAP_S and steps < repeat - 1:
        delay *= DISPATCH_BACKOFF_MULTIPLIER
        steps += 1
    return min(DISPATCH_BACKOFF_CAP_S, delay)


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
    input_revision = _approved_input_revision(run_dir, phase_id)
    prior_input_revision = str(led.get("approved_input_revision") or "initial")
    if input_revision != prior_input_revision:
        # Marker removal follows only the durable reservation of this
        # generation, never this read-only preflight.
        return True, "approved input revision changed"
    # PD-TEST-124: the ceiling is the phase's DECLARED bounded total for a
    # fan-out phase and DISPATCH_RETRY_CAP for every other phase, so a fan-out
    # phase whose siblings are still owed their first attempt is NOT gated off
    # by the legacy three-attempt phase counter. Undeclared => the legacy
    # comparison and the legacy refusal text, byte-for-byte.
    if (led.get("blocked") and
            int(led.get("paid_attempts") or 0) >= _effective_phase_paid_cap(
                led, input_revision)):
        # PD-TEST-068.  This early return used to precede every other clause of
        # this function AND to be blind to the repair receipt, while the only
        # code that ever reads that receipt sits downstream of a claim -- and
        # every claim path is gated right here.  A valid unconsumed receipt
        # could therefore never lift the very gate that blocks its own
        # consumption.  Consult the SAME predicate the consumer uses.
        #
        # READ-ONLY: this gate never consumes the receipt, never resets the
        # counters and never mutates the ledger.  All three should_dispatch
        # call sites (sweep_run_dir, the scheduler's claim loop, and the
        # scan-root reporter) depend on that, and the reservation remains the
        # single consumer.  Nothing is weakened for the no-receipt case: the
        # refusal below is the unchanged, truthful exhaustion message.
        actionable, why = _repair_receipt_is_actionable(
            led, phase_id, run_dir, approved_input_revision=input_revision)
        if actionable:
            return True, why
        _budget = _declared_paid_budget(led, input_revision)
        if _budget is None:
            return False, (f"paid retry budget exhausted: {led.get('paid_attempts')} "
                           f"provider attempts for unchanged approved input "
                           f"(DISPATCH_RETRY_CAP={DISPATCH_RETRY_CAP})")
        return False, (f"paid retry budget exhausted: {led.get('paid_attempts')} of "
                       f"the declared bounded total {_budget.get('total_cap')} "
                       f"provider attempts for unchanged approved input "
                       f"({PHASE_PAID_BUDGET_POLICY})")
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


@_phase_budget_locked
def record_outcome(run_dir: Path, phase_id: str, status: str,
                   reasons: Optional[List[str]] = None, *, worker_id: str,
                   order_file: Optional[Path] = None,
                   paid_attempts: int = 0,
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
    input_revision = _approved_input_revision(run_dir, phase_id)
    prior_input_revision = str(led.get("approved_input_revision") or "initial")
    prior_paid_attempts = (int(led.get("paid_attempts") or 0)
                           if input_revision == prior_input_revision else 0)
    paid_attempts = max(0, int(paid_attempts or 0))
    total_paid_attempts = prior_paid_attempts + paid_attempts

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
        "approved_input_revision": input_revision,
        "paid_attempts": total_paid_attempts,
        # Reservation state is durable across outcome folds.  Dropping these
        # fields would make a consumed repair receipt appear fresh after an
        # exhausted result and buy a second allowance on restart.
        "generation": int(led.get("generation") or 0),
        "repair_receipt_consumed": bool(led.get("repair_receipt_consumed")),
        # PD-TEST-092: this entry REBUILDS the ledger, so any field not named here
        # is erased on the very next outcome fold.  The independent review of PR
        # #1143 measured exactly that: the new audit field was present after
        # _reserve and GONE after one record_outcome, which made the advertised
        # audit trail fiction.  Carried forward so it survives as documented.
        "repair_receipt_consumed_generation": led.get("repair_receipt_consumed_generation"),
        "repair_receipt": led.get("repair_receipt"),
        # PD-TEST-124: the per-unit paid ledger, the declared bounded total
        # budget and the settled reservations are exactly as durable as the
        # phase counter above -- and for the same reason. This entry REBUILDS
        # the ledger, so a field not named here is erased by the very next
        # outcome fold. Measured: without these four lines one record_outcome
        # wiped every per-unit counter, the admission order and the reservation
        # history, and a restart then re-paid units whose successes it could no
        # longer see. Nothing here is reset; everything is carried forward.
        LEDGER_PHASE_PAID_BUDGET: led.get(LEDGER_PHASE_PAID_BUDGET),
        LEDGER_UNIT_ADMISSION_ORDER: led.get(LEDGER_UNIT_ADMISSION_ORDER),
        LEDGER_UNIT_NOT_ADMITTED: led.get(LEDGER_UNIT_NOT_ADMITTED),
        LEDGER_UNIT_PAID_ATTEMPTS: led.get(LEDGER_UNIT_PAID_ATTEMPTS),
        LEDGER_UNIT_PAID_ATTEMPTS_GENERATION: led.get(LEDGER_UNIT_PAID_ATTEMPTS_GENERATION),
        LEDGER_UNIT_PAID_ATTEMPTS_LIFETIME: led.get(LEDGER_UNIT_PAID_ATTEMPTS_LIFETIME),
        "unit_paid_attempts_prior_generation": led.get("unit_paid_attempts_prior_generation"),
        LEDGER_UNIT_OUTCOMES: led.get(LEDGER_UNIT_OUTCOMES),
        LEDGER_UNIT_RESERVATIONS: led.get(LEDGER_UNIT_RESERVATIONS),
        LEDGER_RESERVATION_TOKENS: led.get(LEDGER_RESERVATION_TOKENS),
    }

    if status in _FAILING_STATUSES and consecutive >= DISPATCH_REPEAT_CEILING:
        entry["blocked"] = True
        entry["blocked_reason"] = (
            f"{consecutive} consecutive identical '{status}' dispatch outcomes for "
            f"{phase_id} (retry ceiling DISPATCH_REPEAT_CEILING={DISPATCH_REPEAT_CEILING}). "
            f"Last reasons: {reasons or []}")
        entry["blocked_at"] = utcnow()
        # Unpaid refusal parks stay re-armable when the engine changes the
        # work order or phase state.  Paid failures additionally carry the
        # durable budget below, which only a verified input amendment resets.
        entry["next_eligible_at_epoch"] = now + DISPATCH_BACKOFF_CAP_S

    # PD-TEST-124: the ceiling this clause compares against is the phase's
    # DECLARED bounded total for a fan-out phase, and DISPATCH_RETRY_CAP for
    # every other phase. Before this, an 8-unit fan-out phase was parked as
    # "paid retry budget exhausted" after its THIRD attempt -- with seven units
    # never attempted -- because the phase counter was compared against the
    # per-phase legacy cap no matter how many units the phase owed work to.
    # The legacy refusal text is preserved byte-for-byte when no fan-out budget
    # is declared, so serial phases and the existing PD-068/PD-092 pins are
    # untouched.
    _outcome_cap = _effective_phase_paid_cap(led, input_revision)
    if status in _FAILING_STATUSES and total_paid_attempts >= _outcome_cap:
        entry["blocked"] = True
        _budget = _declared_paid_budget(led, input_revision)
        if _budget is None:
            entry["blocked_reason"] = (
                f"paid retry budget exhausted after {total_paid_attempts} provider attempts for "
                f"{phase_id} with unchanged approved input "
                f"(DISPATCH_RETRY_CAP={DISPATCH_RETRY_CAP}). Last reasons: {reasons or []}")
        else:
            entry["blocked_reason"] = (
                f"paid retry budget exhausted after {total_paid_attempts} of the "
                f"declared bounded total {_budget.get('total_cap')} provider "
                f"attempts for {phase_id} with unchanged approved input "
                f"({PHASE_PAID_BUDGET_POLICY}). Last reasons: {reasons or []}")
        entry["blocked_at"] = utcnow()
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
        "\nThis phase stopped being re-dispatched after its retry ceiling. It was NOT\n"
        "marked done and NOT silently dropped. A work-order rewrite or worker restart\n"
        "does not buy more paid attempts. Dispatch resumes by EITHER of two verified\n"
        "routes -- and by nothing else:\n"
        "  1. ENGINE route: a verified owner input amendment changes this phase's\n"
        "     approved input generation; or\n"
        "  2. REPAIR-RECEIPT route: after a deployed code repair, the OS owner of this\n"
        f"     run issues ONE bounded local-operator paid-retry repair receipt (kind\n"
        f"     {DISPATCH_REPAIR_RECEIPT_KIND}, allowance 1..{PHASE_TOTAL_PAID_HARD_CAP}) bound to the\n"
        "     then-current dispatcher source hash, ledger generation, approved input\n"
        "     revision and run owner. The dispatcher consumes it exactly once and\n"
        "     reserves that many further paid attempts:\n"
        "       dispatcher.py --run-dir <THIS RUN DIR> \\\n"
        f"         --authorize-paid-retry-reset {phase_id} --reset-allowance <N>\n"
        "     A receipt whose dispatcher_sha256 is not the hash of the dispatcher\n"
        "     source RUNNING NOW is refused -- re-issue it after the repair is\n"
        "     deployed to every mirror.\n"
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


# ---------------------------------------------------------------------------
# PRES-036 (2026-09-08): the scan-root scheduler.
#
# The old watch_scan_root swept every run SERIALLY and each sweep_run_dir
# JOINED its workers before the loop reached the next run: one slow or hung
# job head-of-line blocked every other deck on the box for the length of its
# budget (SPEC.md PRES-036, dispatcher.py watch_scan_root serial jobs).
#
# _ScanRootScheduler replaces that with the TODO.md PRES-036 contract:
#   1. short NONBLOCKING claim scans -- each tick claims eligible work orders
#      (try_claim/release_claim, the SAME per-phase claim machinery the
#      single-run path uses, so no second locking regime) and submits them to
#      a PERSISTENT bounded pool; the scan loop never joins a batch, so a
#      hung dispatch occupies a slot, not the loop. Long tasks run in
#      separately supervised pool workers -- a hung one is contained to its
#      future and reaped when it finishes (or when its claim is judged stale
#      by the existing _claim_is_stale liveness rules on a later tick).
#   2. FAIR SHARING across runs: runs are served ROUND-ROBIN (one
#      oldest-order claim per run per pass, eldest work order first), so a
#      large deck cannot own every slot; AGE PRIORITY inside a run (oldest
#      eligible order first). The per-run max_workers ceiling still binds:
#      total capacity = sum of per-run caps the box can actually serve.
#   3. QC/recovery reserve: while the pool is saturated, the LAST slot is
#      held for a QC-owning phase (P1Q-COPY-QC / P-TYPo-QC / P-PROMPT-QC /
#      P-IMAGE-QC / P-SHIFT-QC / P-SPEECH-QC / P-QC-AGGREGATE / P-U-QC) so
#      queued authors do not starve QC (QC.md QC-PRES-036 check 2).
#   4. DURABLE REPORT: working/scan-root-queue.json carries, per run, the
#      queued vs running counts, the last claim-scan time and the oldest
#      queued age -- the progress/ETA surface the operator reads.
#
# Reaping: a finished future is folded into record_outcome + release_claim
# EXACTLY as sweep_run_dir did inline (the FIX 2026-09-04 ledger gap contract
# is preserved: every returned status reaches the ledger, crashes included).
# The reaper runs on the SAME tick that claims new work -- one thread, no
# locks shared with sweep paths.
#
# ROLLBACK: PRESENTATION_SCAN_ROOT_SCHEDULER=0 selects the old serial
# watch_scan_root loop byte-for-byte.
_SCAN_ROOT_SCHEDULER_QC_IDS = frozenset({
    "P1Q-COPY-QC", "P-TYPO-QC", "P-PROMPT-QC", "P-IMAGE-QC",
    "P-SHIFT-QC", "P-SPEECH-QC", "P-QC-AGGREGATE", "P-U-QC",
})

def _scan_root_scheduler_enabled() -> bool:
    """PRES-036: default ON; only exactly "0" disables (same quote/whitespace
    discipline as _wave_execution_enabled in phases.py)."""
    raw = os.environ.get("PRESENTATION_SCAN_ROOT_SCHEDULER")
    if raw is None:
        return True
    return raw.strip().strip("'\"") != "0"

def _write_scan_root_report(scan_root: Path, report: Dict[str, Any]) -> None:
    """Durable queued/running snapshot (best-effort, atomic replace)."""
    try:
        scan_root.mkdir(parents=True, exist_ok=True)
        path = scan_root / ".scan-root-queue.json"
        tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
        tmp.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        print(f"[dispatcher scan-root] report write failed: {exc!r}", file=sys.stderr, flush=True)

class _ScanRootScheduler:
    """PRES-036: persistent pool + short nonblocking claim scans across a
    scan root. One instance per watch_scan_root invocation; single-threaded
    control (tick + reap run on the caller's thread); dispatch_one runs on
    the pool."""

    def __init__(self, scan_root: Path, *, worker_id: str,
                 max_workers: Optional[int], interval: float) -> None:
        self.scan_root = scan_root
        self.worker_id = worker_id
        self.max_workers = max_workers
        self.interval = interval
        # The persistent pool: long tasks live HERE, separately from the
        # claim-scan loop -- a hung dispatch holds one worker thread, never
        # the loop (SPEC.md PRES-036 step 1). Width: an explicit --max-workers
        # wins; otherwise the DETECTED tier of the scan root's own department
        # tree (resolve_max_workers, no fabricated override), floored at 2 so
        # one run can never consume the whole pool.
        if max_workers is not None:
            width = max(1, int(max_workers))
        else:
            try:
                probe_scripts = _OWN_SCRIPTS_DIR
                width = resolve_max_workers(resolve_dept_root(probe_scripts), None)
            except Exception:  # noqa: BLE001
                width = 8
            width = max(2, width)
        self._width = width
        self._pool = ThreadPoolExecutor(max_workers=width)
        self._pool_lock = threading.Lock()
        self._in_flight: Dict[Any, Tuple[Path, str, str]] = {}
        # run_dir -> dept root, resolved once per run (read-only facts).
        self._dept_roots: Dict[Path, Path] = {}
        # Round-robin cursor: the run index the next claim scan starts from
        # (fair sharing, TODO.md step 3).
        self._rr: int = 0

    def _runs(self) -> List[Path]:
        """Eligible runs, ELDEST STATE FIRST (age priority across runs): a
        run that has been open longest is scanned first; terminal runs are
        skipped before the round-robin sees them."""
        def _state_mtime(rd: Path) -> float:
            try:
                return (rd / "state.json").stat().st_mtime
            except OSError:
                return 0.0
        run_dirs = [p.parent for p in self.scan_root.glob("*/state.json")]
        live = []
        for run_dir in run_dirs:
            if _run_terminal(run_dir) is not None:
                continue
            # FIX 9 kept: a run with open work orders and a dead engine is
            # exactly what this watcher exists for; only a run with nothing
            # open and no engine skips its scan.
            if not _open_work_orders(run_dir) and not _engine_pid_alive(run_dir):
                continue
            live.append(run_dir)
        live.sort(key=_state_mtime)
        return live

    def _claim_scan(self) -> int:
        """ONE short nonblocking claim scan. Claims at most the free pool
        slots, oldest-order first, fair-shared by rotating the start run.
        Returns how many new dispatches were submitted. Never joins."""
        admitted = 0
        runs = self._runs()
        if not runs:
            return 0
        with self._pool_lock:
            free = self._width - len(self._in_flight)
        if free <= 0:
            return 0
        # Round-robin the start index so no run is structurally last.
        ordered = runs[self._rr % len(runs):] + runs[:self._rr % len(runs)] \
            if runs else []
        self._rr += 1
        for run_dir in ordered:
            if admitted >= free:
                break
            claimed = self._scan_one_run(run_dir, max_claims=free - admitted)
            admitted += claimed
        return admitted

    def _scan_one_run(self, run_dir: Path, *, max_claims: int) -> int:
        """Claim up to max_claims eligible work orders of ONE run -- the
        short claim scan of TODO.md step 1. Eligibility mirrors
        sweep_run_dir's pre-claim gates exactly (DECLINE_PHASES, already
        done, should_dispatch backoff, try_claim); the work is only CLAIMED
        here and SUBMITTED to the pool -- never executed inline."""
        wo_dir = run_dir / "working" / "work-orders"
        if not wo_dir.is_dir():
            return 0
        manifest = load_manifest_for_run(run_dir)
        scripts_dir = resolve_scripts_dir_for_run(run_dir)
        dept_root = self._dept_roots.setdefault(run_dir, resolve_dept_root(scripts_dir))
        claimed = 0
        for of in sorted(wo_dir.glob("*.json")):
            if claimed >= max_claims:
                break
            phase_id = of.stem
            if phase_id in DECLINE_PHASES:
                record_outcome(run_dir, phase_id, "declined",
                               [DECLINE_PHASES[phase_id]], worker_id=self.worker_id,
                               order_file=of)
                continue
            if _phase_already_done(run_dir, phase_id):
                record_outcome(run_dir, phase_id, "already_done_in_state",
                               worker_id=self.worker_id, order_file=of)
                continue
            may, _why = should_dispatch(run_dir, phase_id, order_file=of)
            if not may:
                continue
            if not try_claim(run_dir, phase_id, self.worker_id):
                continue
            phase_obj = None
            if manifest is not None:
                try:
                    phase_obj = manifest.phase_or_none(phase_id) \
                        if hasattr(manifest, "phase_or_none") \
                        else next((p for p in manifest.phases if p.id == phase_id), None)
                except Exception:  # noqa: BLE001
                    phase_obj = None
            try:
                order = json.loads(of.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                release_claim(run_dir, phase_id)
                continue
            fut = self._pool.submit(dispatch_one, run_dir, phase_id, order,
                                    dept_root=dept_root, phase_obj=phase_obj,
                                    worker_id=self.worker_id)
            with self._pool_lock:
                self._in_flight[fut] = (run_dir, phase_id, self.worker_id)
            claimed += 1
        return claimed

    def _reap(self) -> int:
        """Fold finished futures into the ledger exactly as sweep_run_dir's
        as_completed loop did (record_outcome + release_claim), then free the
        slots. Returns how many were reaped."""
        reaped = 0
        with self._pool_lock:
            done = [f for f in self._in_flight if f.done()]
            for fut in done:
                run_dir, phase_id, _wid = self._in_flight.pop(fut)
                try:
                    res = fut.result()
                except Exception as exc:  # noqa: BLE001 -- one phase's crash must not kill the scheduler
                    _append_sidecar(run_dir, phase_id, {
                        "worker": self.worker_id, "attempt": 0, "status": "error",
                        "reason": f"dispatch_one raised {exc!r}",
                    })
                    record_outcome(run_dir, phase_id, "error",
                                   [f"dispatch_one raised {exc!r}"],
                                   worker_id=self.worker_id)
                    print(f"[dispatcher {self.worker_id}] {run_dir.name}/{phase_id}: "
                          f"error (dispatch_one raised)", flush=True)
                else:
                    record_outcome(run_dir, phase_id, res.status, list(res.reasons),
                                   worker_id=self.worker_id)
                    print(f"[dispatcher {self.worker_id}] {run_dir.name}/{res.phase_id}: "
                          f"{res.status} (attempts={res.attempts})", flush=True)
                finally:
                    release_claim(run_dir, phase_id)
                reaped += 1
        return reaped

    def _report(self, runs: List[Path]) -> None:
        """The durable queued/running report (TODO.md step 4): per-run queued
        vs running counts, last claim-scan time, oldest queued age."""
        per_run = []
        with self._pool_lock:
            running_by_run: Dict[Path, List[str]] = {}
            for (_rd, pid, _w) in self._in_flight.values():
                running_by_run.setdefault(_rd, []).append(pid)
        for run_dir in runs:
            wo_dir = run_dir / "working" / "work-orders"
            queued = 0
            oldest: Optional[float] = None
            if wo_dir.is_dir():
                for of in sorted(wo_dir.glob("*.json")):
                    pid = of.stem
                    if pid in DECLINE_PHASES or _phase_already_done(run_dir, pid):
                        continue
                    # QUEUED == an order this module would actually work on
                    # that is not currently claimed by anyone (a claim file
                    # for a live pid means it is RUNNING, not queued). Read
                    # only: no claim is created here.
                    claim = _claim_path(run_dir, pid)
                    if claim.exists():
                        try:
                            age = time.time() - claim.stat().st_mtime
                        except OSError:
                            age = 0.0
                        if age <= SINGLE_ATTEMPT_BUDGET_S * CLAIM_STALE_MULTIPLIER:
                            continue
                    may, _why = should_dispatch(run_dir, pid, order_file=of)
                    if not may:
                        continue
                    queued += 1
                    try:
                        age = time.time() - of.stat().st_mtime
                    except OSError:
                        age = 0.0
                    if oldest is None or age > oldest:
                        oldest = age
            per_run.append({
                "run": run_dir.name,
                "queued": queued,
                "running": sorted(running_by_run.get(run_dir, [])),
                "oldest_queued_s": round(oldest, 1) if oldest is not None else None,
            })
        _write_scan_root_report(self.scan_root, {
            "scheduler": "ready-queue",
            "worker": self.worker_id,
            "pool_workers": self._width,
            "in_flight": len(self._in_flight),
            "last_scan_at": utcnow(),
            "runs": per_run,
        })

    def run(self, max_lifetime_s: float) -> None:
        started = time.time()
        print(f"[dispatcher {self.worker_id}] ready-queue scheduler watching "
              f"all runs under {self.scan_root}", flush=True)
        try:
            while time.time() - started <= max_lifetime_s:
                reaped = self._reap()
                self._claim_scan()
                runs = self._runs()
                if reaped or runs:
                    self._report(runs)
                time.sleep(self.interval)
        finally:
            # Drain: reap whatever finished, then stop the pool. A task still
            # running at shutdown is left to the claim-staleness rules on the
            # next scheduler's first tick (its claim names the pid).
            try:
                self._reap()
                self._pool.shutdown(wait=False, cancel_futures=True)
            except Exception:  # noqa: BLE001
                pass
            _write_scan_root_report(self.scan_root, {
                "scheduler": "ready-queue", "worker": self.worker_id,
                "state": "exited", "updated_at": utcnow()})

def watch_scan_root(scan_root: Path, *, interval: float = SWEEP_INTERVAL_S,
                    max_lifetime_s: float = 24 * 3600,
                    max_workers: Optional[int] = None) -> None:
    worker_id = f"dispatcher-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    # PRES-036: the ready-queue scheduler is the DEFAULT; =0 restores the
    # serial per-run sweep loop below byte-for-byte (documented rollback).
    if _scan_root_scheduler_enabled():
        _ScanRootScheduler(scan_root, worker_id=worker_id,
                           max_workers=max_workers, interval=interval
                           ).run(max_lifetime_s)
        return
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
    p.add_argument("--authorize-paid-retry-reset", metavar="PHASE_ID", default=None,
                   help="local-operator repair action: issue one bounded reset receipt for PHASE_ID")
    p.add_argument("--reset-allowance", type=int, default=None,
                   help="provider calls allowed by --authorize-paid-retry-reset (1..retry cap)")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    watch = args.watch or not args.once  # --watch is the default mode

    if args.run_dir:
        run_dir = args.run_dir.expanduser().resolve()
        if args.authorize_paid_retry_reset:
            if args.reset_allowance is None:
                raise SystemExit("--reset-allowance is required with --authorize-paid-retry-reset")
            print(json.dumps(authorize_paid_retry_reset(
                run_dir, args.authorize_paid_retry_reset,
                allowance=args.reset_allowance), sort_keys=True))
            return 0
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
