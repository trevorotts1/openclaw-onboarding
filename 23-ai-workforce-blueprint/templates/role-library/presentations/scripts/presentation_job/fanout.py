from __future__ import annotations

"""
presentation_job/fanout.py -- the per-phase worker pool (PARALLEL-PIPELINE-SPEC,
2026-08-27, Ticket 1).

WHAT THIS MODULE IS: a bounded-concurrency pool that lets a single dispatcher
phase author N independent units (slides, QC checks, media files) concurrently
instead of one at a time, while leaving `phases.py` (the Engine) and its
RunLock invariant completely untouched -- see the spec's S2.1: "phases.py
changes in exactly one respect: nothing." This module has ZERO importers as
of Ticket 1; dispatcher.py wires it in per-phase starting with Ticket 4
(P4-PROMPT).

HARD INVARIANTS (spec S2.6 -- mechanical, not just documented):

  1. A worker is a callable, not a command. `run_units` takes
     `worker_fn: Callable[[Unit], UnitResult]`. There is no code path here by
     which a worker becomes an argv.
  2. A worker is NEVER a `presentation_job.py` / `presentation_job` package /
     `run_signature_deck.py` / `presentation-canonical-entry.sh` re-entry.
     The Engine holds RunLock (state.py:148) for its whole run
     (`__main__.py:229`, `:582`), so any re-entry dies with EXIT_LOCK_HELD
     (state.py:162) -- the exact regression class
     `tests/test_l11_webinar_executor_no_recursion.py` exists to catch.
     `_assert_not_a_second_engine` below is the mechanical guard: any FUTURE
     subprocess-based worker (e.g. the Ticket 7 ffmpeg clip loop) must call it
     on its argv before invoking `subprocess`/`run_with_cleanup`, and it
     raises at SUBMIT time rather than surfacing as an exit-6 mystery N times
     over.
  3. No fail-fast, no cancellation (spec S2.4). By the time unit 7 of 50
     fails, units 8-50 are already in flight and already billed; cancelling
     them saves nothing and throws away completed work. Every SUBMITTED unit
     runs to its own conclusion, including after the phase deadline passes --
     the deadline only stops NEW submissions.
  4. Deterministic output order (spec S2.5). `run_units` returns results in
     the SAME order as the input `units` list, regardless of completion
     order, so an ordered-concatenation caller (P4-COPY's Wave-D harmonize
     input, the TTS phases) never has to re-sort itself.

RETRY DESIGN NOTE (a place the spec's own pseudocode under-specifies, so the
choice made here is written down rather than left implicit): `worker_fn` is
expected to perform ONE authoritative attempt and return a definitive
UnitResult (status "ok" or "failed") -- exactly what an extracted-verbatim
function like the eventual `_author_one_slide` (Ticket 4, which already
contains ITS OWN internal DISPATCH_RETRY_CAP retry loop, dispatcher.py
~1815-1855) does. `run_units`'s own `retry_cap` is therefore a SEPARATE,
outer safety net that only fires when `worker_fn` *raises* (an unexpected
transport/programming fault), never when it returns a normal "failed"
verdict -- so a worker that already owns its retry policy is never
double-retried by the pool, while a simple worker that has no retry policy of
its own (a QC grader, a media upload) still gets the shared
HEAL_CAP_TRANSIENT-based backoff for free. This is the meaning of spec S2.3's
"retries happen inside the worker": whichever side (worker_fn's own loop, or
this fallback) does the retrying, a retrying unit always occupies exactly one
pool slot and never inflates live concurrency above `workers`.

Concurrency primitive: `concurrent.futures.ThreadPoolExecutor` -- the same
import dispatcher.py already uses (dispatcher.py:58). Not multiprocessing,
not asyncio -- see spec S2.3 for why.
"""

import os
import re
import sys
import threading
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# ---------------------------------------------------------------------------
# Path bootstrap -- same pattern as dispatcher.py, so this module imports
# cleanly both as `presentation_job.fanout` and when scripts_dir is the sys.path
# root (e.g. under a GATE-1-style import smoke test).
# ---------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()
_OWN_SCRIPTS_DIR = _THIS_FILE.parent.parent  # presentation_job/ -> scripts/
if str(_OWN_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_OWN_SCRIPTS_DIR))

from presentation_job import heal as _heal  # noqa: E402

# FIX 14 (MASTER Part 8): one per-provider governor for every outbound call.
# Defensive import, same pattern as heal above: a tree that predates the
# governor module (W09 has not landed presentation_job/governor.py yet) keeps
# the old behavior byte-for-byte -- the _run_one gate degrades to a no-op.
try:
    from presentation_job import governor as _governor  # noqa: E402
except ImportError:  # pragma: no cover - pre-FIX-14 trees limit nothing new
    _governor = None  # type: ignore[assignment]

# Reused, never re-invented (spec S2.3): the one retry budget the serial path
# already uses at dispatcher.py:1815 (`for attempt in range(1, DISPATCH_RETRY_CAP + 1)`).
DEFAULT_RETRY_CAP = _heal.HEAL_CAP_TRANSIENT  # = 3


class FanoutContractError(Exception):
    """Raised at SUBMIT time when a worker argv would re-enter the pipeline.
    Never raised for a normal unit failure -- that is a UnitResult with
    status="failed", never an exception."""


# S2.6 point 3: a mechanical guard, not a comment.
_FORBIDDEN_WORKER_TOKENS = (
    "presentation_job.py",
    "presentation_job",
    "run_signature_deck.py",
    "presentation-canonical-entry.sh",
)


def _assert_not_a_second_engine(argv: List[str]) -> None:
    """A worker is a model call or a media subprocess. It is NEVER a pipeline
    re-entry. The Engine holds RunLock (state.py:148) for its whole run, so
    any re-entry dies with EXIT_LOCK_HELD (state.py:162) -- the L11/workbook
    regression class. This raises at SUBMIT time so the failure names the
    cause instead of surfacing as an exit-6 mystery N times over."""
    joined = " ".join(str(a) for a in argv)
    for tok in _FORBIDDEN_WORKER_TOKENS:
        if tok in joined:
            raise FanoutContractError(
                f"worker argv would re-enter the pipeline ({tok!r}); workers are "
                f"model calls or media subprocesses, never second engines: {argv!r}"
            )


@dataclass(frozen=True)
class Unit:
    """One independent piece of fan-out work. `key` must be stable and
    sortable ("slide-07", "chunk-003") -- it is both the merge-ordering key
    and the progress-artifact key. `payload` carries everything the worker
    needs; per spec, no shared mutable state may live here."""
    key: str
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UnitResult:
    key: str
    status: str  # "ok" | "failed" | "skipped"
    attempts: int = 1
    reasons: List[str] = field(default_factory=list)
    target: Optional[str] = None  # path relative to run_dir, when a file was produced
    # FIX 15: optional per-unit stamps {provider, model, request_id, response_id,
    # started_at, ended_at} the worker_fn already holds in hand, forwarded into
    # the unit ledger row below so every unit row carries its own provenance.
    meta: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# PRES-013 (2026-09-08): bounded-deadline execution states.
#
# The original run_units documented `per_unit_timeout_s` as "informational"
# and submitted every unit eagerly, so the phase deadline only gated
# submission time, not when a queued item STARTED -- and a unit with no
# actual work left to do (queued behind a full pool) was still counted as
# in-flight, because the pool itself waited on every submitted future. A
# 1-worker pool with a 15 ms deadline therefore started its 2nd-4th units at
# 44/86/128 ms and finished at 173 ms: the deadline bounded nothing.
#
# The contract now has four explicit states a unit moves through, and the
# deadline is checked at every state transition that could start NEW
# transport work:
#
#   queued    -- enumerated, not yet admitted to the pool. Billed nothing,
#                called nothing: safe to defer/cancel at any time.
#   admitted  -- holding one of the `workers` pool slots; about to call
#                 worker_fn. Admission is REFUSED once the deadline has
#                 passed (the unit returns skipped, resumable).
#   submitted -- worker_fn is executing (transport in flight or a local
#                 call inside the worker).
#   provider_running -- the worker declared it had handed the unit to a
#                 remote async provider (raise ProviderTaskPending /
#                 return a UnitResult carrying provider_task_id): the unit
#                 is NOT re-run from scratch after a deadline; the durable
#                 task id is persisted and polling resumes from it.
#
# `deadline_at` is a MONOTONIC ABSOLUTE instant (time.monotonic() +
# deadline_s) checked (a) at admission, (b) before every retry attempt, and
# (c) by long-running WAIT paths -- never re-derived from a fresh
# time.monotonic() per queued item, which is what let queued items start
# arbitrarily late under the old code.
# ---------------------------------------------------------------------------
UNIT_STATES_QUEUED = "queued"
UNIT_STATES_ADMITTED = "admitted"
UNIT_STATES_SUBMITTED = "submitted"
UNIT_STATES_PROVIDER_RUNNING = "provider_running"


class ProviderTaskPending(Exception):
    """A worker raises this when it has handed the unit to a remote ASYNC
    provider (image/video/speech generation) that is still running and
    returned a durable task id.

    Preserving the id (never discarding or repeating it) is the whole point:
    a deadline that expires while a provider task runs must NOT create a
    second bill. `task_id` is persisted (best-effort) to the unit scratch
    dir so a later run -- or a restart -- polls the SAME id instead of
    resubmitting a fresh (paid) task.
    """

    def __init__(self, task_id: str, *, provider: Optional[str] = None,
                 message: str = "") -> None:
        super().__init__(message or f"provider task pending: {task_id}")
        self.task_id = str(task_id)
        self.provider = provider


# ---------------------------------------------------------------------------
# S2.2: the Option-B-shaped observability layer bolted onto the Option-A
# direct-HTTP mechanism -- a live progress artifact the dept-presentations
# agent already reads, so a phase "37/50 slides authored, 2 retrying" is
# visible instead of one silent "busy".
# ---------------------------------------------------------------------------
def _progress_path(run_dir: Path, phase_id: str) -> Path:
    return run_dir / "working" / "fanout" / f"{phase_id}-progress.json"


def _write_progress(run_dir: Path, phase_id: str, state: Dict[str, Any]) -> None:
    """Atomic os.replace, matching every other artifact write in this package
    (dispatcher.py:1866-1869) -- concurrent worker threads call this
    concurrently, so a reader must never see a half-written file."""
    path = _progress_path(run_dir, phase_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".partial-{os.getpid()}-{threading.get_ident()}")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# PRES-013: remaining-deadline helper -- the admission snapshot's stamps
# (unit.payload["fanout_deadline"]) carry the connect/read values workers
# SHOULD use for their own transports; this helper serves the pool's own
# retry/backoff re-checks only.
# ---------------------------------------------------------------------------
def remaining_deadline_s(deadline_at: Optional[float]) -> Optional[float]:
    """Remaining seconds until a monotonic absolute deadline (never an extra
    clock read for callers that already hold `deadline_at`): max(0, ...),
    and None when no deadline is set."""
    if deadline_at is None:
        return None
    return max(0.0, deadline_at - time.monotonic())


def _provider_task_store_path(run_dir: Path, phase_id: str) -> Path:
    """Durable record of in-flight async provider task ids, one JSON object
    {unit_key: {task_id, provider, recorded_at}} per phase. A deadline that
    expires mid-task persists the id HERE (atomic replace) so the resume path
    polls the same id -- the no-second-bill contract."""
    return run_dir / "working" / "fanout" / f"{phase_id}-provider-tasks.json"


def _persist_provider_task(run_dir: Path, phase_id: str, unit_key: str,
                           task_id: str, provider: Optional[str]) -> None:
    """Best-effort durable save of one provider task id (never breaks a
    unit; an unwritable run dir must not turn a billed task into a second
    bill by losing its id)."""
    try:
        path = _provider_task_store_path(run_dir, phase_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            store = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(store, dict):
                store = {}
        except (OSError, ValueError, json.JSONDecodeError):
            store = {}
        store[unit_key] = {"task_id": str(task_id), "provider": provider,
                           "recorded_at": time.strftime(
                               "%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        tmp = path.with_suffix(path.suffix + f".partial-{os.getpid()}-{threading.get_ident()}")
        tmp.write_text(json.dumps(store, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, path)
    except Exception:  # noqa: BLE001 -- persistence is best-effort, always
        pass


def load_provider_tasks(run_dir: Path, phase_id: str) -> Dict[str, Dict[str, Any]]:
    """Read back the durable {unit_key: {task_id, provider, recorded_at}}
    store for a phase. Resume paths call this FIRST and poll existing ids
    before ever creating a new provider task."""
    try:
        store = json.loads(
            _provider_task_store_path(run_dir, phase_id).read_text(encoding="utf-8"))
        return store if isinstance(store, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def run_units(
    units: List[Unit],
    worker_fn: Callable[[Unit], UnitResult],
    *,
    workers: int,
    run_dir: Path,
    phase_id: str,
    per_unit_timeout_s: Optional[float] = None,
    retry_cap: int = DEFAULT_RETRY_CAP,
    deadline_s: Optional[float] = None,
    progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    prefetch: int = 0,
) -> List[UnitResult]:
    """Run `units` through `worker_fn` with at most `workers` concurrent
    callables, and return one UnitResult per unit IN INPUT ORDER (never
    completion order -- see module docstring point 4).

    PRES-013 REWRITE (2026-09-08) -- the deadline now bounds actual
    execution, not just submission. Admission is BOUNDED: at most
    `workers + prefetch` units are ever handed to the pool at once; a unit
    is admitted only when a pool slot is genuinely free AND the monotonic
    absolute deadline (`deadline_at = time.monotonic() + deadline_s`) has
    not passed. Queued units past the deadline are returned `skipped`
    WITHOUT ever calling worker_fn -- zero extra transport, resumable on a
    later pass exactly like the already-good short-circuit at
    dispatcher.py:4015. The single-clock scripted shape of the existing
    deadline tests is preserved: admission time reads are ONE
    time.monotonic() call per unit, in input order, on the admitting
    thread.

    `per_unit_timeout_s`: BOUNDED, not informational. It is handed to the
    worker through unit.payload["fanout_deadline"]["per_unit_timeout_s"]
    (plus the remaining-deadline transport stamps), and it is ENFORCED for
    one worker class:

      * a worker that declared a LOCAL SUBPROCESS (unit.payload carries
        {"subprocess_argv": [...]}) gets that argv run under
        process_reaper.run_with_cleanup -- NEW PROCESS GROUP, and on
        timeout the WHOLE GROUP is TERM->KILLed, so a hanging child leaves
        no orphan (the FIX-21 mechanism, reused -- never re-implemented);
      * any other worker_fn runs to its own conclusion -- a hung plain-
        thread attempt is NOT pretend-killed (a future.result(timeout=...)
        that abandons a future leaks the thread and keeps burning provider
        budget silently). A worker_fn that raises after exhausting
        retry_cap returns status "failed" with a durable
        "deadline_exceeded:async_pending" marker so the phase surface
        shows a resumable failure and the unit ledger records it.

    `deadline_s`: phase-level wall-clock ceiling on the POOL's own
    lifetime, computed by the caller from `phase.budget_minutes`
    (manifest.py:180). Checked at ADMISSION and BEFORE EVERY RETRY.
    Queued tasks have not been billed and may be safely deferred/cancelled
    at the deadline. A unit that raises ProviderTaskPending (its remote
    async provider task is still running) is NEVER re-run from scratch:
    the durable task id is persisted to
    working/fanout/<phase_id>-provider-tasks.json and the unit returns
    status "pending_provider" carrying the id, so a later run polls the
    SAME task -- no second bill.

    `prefetch`: extra units admitted AHEAD of a free slot (bounded queue
    depth = workers + prefetch, default 0 = no over-admission). Prefetched
    units hold no transport open -- admitted-but-not-started units run
    under the admission snapshot (no extra clock read). Retry attempts
    re-check the deadline before starting new transport work.

    `retry_cap`: see the module docstring's "RETRY DESIGN NOTE" -- this is
    an outer safety net for a `worker_fn` that raises, not a second retry
    layer on top of a `worker_fn` that already retries internally and
    returns a definitive verdict.
    """
    if not units:
        return []

    workers = max(1, min(int(workers), len(units)))
    deadline_at = (time.monotonic() + deadline_s) if deadline_s else None
    lock = threading.Lock()
    progress: Dict[str, Any] = {
        "phase_id": phase_id,
        "total": len(units),
        "workers": workers,
        "prefetch": max(0, int(prefetch)),
        "units": {u.key: "pending" for u in units},
    }
    # The per-attempt timeout, as the worker_fn itself should observe it.
    unit_timeout_s = per_unit_timeout_s if (per_unit_timeout_s and
                                            per_unit_timeout_s > 0) else None

    def _counts() -> Dict[str, int]:
        vals = list(progress["units"].values())
        return {
            "queued": sum(1 for v in vals if v == UNIT_STATES_QUEUED),
            "admitted": sum(1 for v in vals if v == UNIT_STATES_ADMITTED),
            "submitted": sum(1 for v in vals if v == "dispatched"),
            "provider_running": sum(1 for v in vals
                                    if v == UNIT_STATES_PROVIDER_RUNNING),
            "retrying": sum(1 for v in vals if v == "retrying"),
            "verified": sum(1 for v in vals if v == "verified"),
            "failed": sum(1 for v in vals if v == "failed"),
            "skipped": sum(1 for v in vals if v == "skipped"),
            "pending": sum(1 for v in vals if v == "pending"),
        }

    def _emit(unit_key: str, state: str) -> None:
        with lock:
            progress["units"][unit_key] = state
            snapshot = dict(progress, units=dict(progress["units"]), counts=_counts())
            # The file write is INSIDE the lock: snapshots are taken in
            # emission order, so the file must land in the same order --
            # a write released from the lock could otherwise complete after
            # a LATER snapshot's write and leave a stale (non-terminal)
            # file as the last reader-visible state.
            _write_progress(run_dir, phase_id, snapshot)
        if progress_cb:
            progress_cb(snapshot)

    def _stamp_deadline(unit: Unit, remaining_s: Optional[float]) -> Dict[str, Any]:
        """Deadline stamps for the worker's own transports: the absolute
        monotonic deadline it may read, the per-attempt cap, and remaining-
        deadline connect/read timeouts. Payload-only (never a Unit field
        change): frozen dataclass shapes stay stable for every caller.

        NO clock read of its own: `remaining_s` is the value the admission
        check already read, passed in -- one admission = one monotonic read,
        total. The scripted single-clock contract and a race-free verdict."""
        stamps: Dict[str, Any] = {
            "deadline_remaining_s": remaining_s,
            "connect_timeout_s": remaining_s,
            "read_timeout_s": remaining_s,
        }
        if unit_timeout_s is not None:
            stamps["per_unit_timeout_s"] = float(unit_timeout_s)
        return stamps

    def _run_subprocess_unit(unit: Unit) -> UnitResult:
        """Local-subprocess unit: argv under process-group supervision.

        The FIX-21/105 mechanism (process_reaper.run_with_cleanup) runs the
        child in a NEW SESSION so a timeout TERM->KILLs the whole group --
        a hanging child cannot orphan. `_assert_not_a_second_engine` runs at
        submit time (module invariant 2) before any spawn."""
        argv = list(unit.payload["subprocess_argv"])
        _assert_not_a_second_engine(argv)
        from process_reaper import run_with_cleanup as _rwc  # type: ignore
        env = dict(unit.payload.get("subprocess_env") or {})
        return _rwc(argv, cwd=str(unit.payload.get("subprocess_cwd") or "."),
                    timeout=(unit_timeout_s if unit_timeout_s is not None
                             else remaining_deadline_s(deadline_at)),
                    env=env or None)

    def _run_one(unit: Unit, deadline_snapshot: Optional[Dict[str, Any]]) -> UnitResult:
        # PRES-013: the deadline verdict for this unit was computed ON THE
        # ADMITTING THREAD at the moment of its actual admission (bounded
        # queue drain + submit) and passed in as `deadline_snapshot`
        # {"admitted": bool, ...stamps}. The worker thread performs NO clock
        # read of its own here: a scripted-clock test feeds ONE shared
        # monotonic iterator, and a worker/admit scheduling race over extra
        # reads would make "did the unit start before the deadline"
        # scheduling-dependent rather than admission-determined. The admit
        # thread's snapshot IS the decision.
        if not deadline_snapshot or not deadline_snapshot.get("admitted"):
            _emit(unit.key, "skipped")
            return UnitResult(
                key=unit.key, status="skipped", attempts=0,
                reasons=["phase deadline reached before unit start"])
        _emit(unit.key, UNIT_STATES_ADMITTED)
        _emit(unit.key, "dispatched")
        attempts = 0
        last_exc: Optional[BaseException] = None
        cap = max(1, retry_cap)
        # FIX 14: the unit's provider, when the caller stamps one into
        # unit.payload ({"provider": "kie", ...} for image/TTS units, etc.).
        # Unstamped units gate on "deepseek-direct" only if the payload also
        # carries {"govern": true}; plain local units (QC graders, file
        # assembly) consume no provider budget and stay ungated. The gate is
        # best-effort: a tree without presentation_job/governor.py no-ops.
        _gov_provider = unit.payload.get("provider") or "deepseek-direct"
        _gov_enabled = bool(unit.payload.get("provider")) or \
            bool(unit.payload.get("govern"))
        _gov = _governor if _gov_enabled else None
        is_subprocess = bool(unit.payload.get("subprocess_argv"))
        while attempts < cap:
            attempts += 1
            # PRES-013: no NEW transport work after the phase deadline. The
            # re-check consumes the SAME admission snapshot contract (one
            # clock read per attempt on the WORKING thread, after the first
            # attempt which used the admit snapshot) -- a retry is a new
            # admission of real work, so it re-reads the monotonic clock
            # exactly once, on this thread, before its backoff.
            if attempts > 1 and deadline_at is not None \
                    and remaining_deadline_s(deadline_at) <= 0:
                _emit(unit.key, "skipped")
                return UnitResult(
                    key=unit.key, status="skipped", attempts=attempts - 1,
                    reasons=["phase deadline reached before retry"])
            # PRES-013: the worker's payload receives the deadline stamps so
            # its transports bound themselves by the remaining time. A copy,
            # never a mutation -- Unit payloads are caller-owned.
            payload_stamps = dict(deadline_snapshot.get("stamps") or {})
            if unit_timeout_s is not None:
                payload_stamps["per_unit_timeout_s"] = float(unit_timeout_s)
            if payload_stamps:
                unit.payload.setdefault("fanout_deadline", payload_stamps)
            _lease = None
            if _gov is not None:
                try:
                    # FIX 14 named call site: fanout acquires one governor
                    # lease per attempt so a 40-unit wave can never exceed the
                    # provider's max_inflight or rps/burst window.
                    _lease = _gov.acquire(_gov_provider)
                except Exception:  # noqa: BLE001 -- gating never kills a unit
                    _lease = None
            try:
                if is_subprocess:
                    result = _run_subprocess_unit(unit)
                else:
                    result = worker_fn(unit)
                if _gov is not None:
                    try:
                        _gov.report_ok(_gov_provider)
                    except Exception:  # noqa: BLE001
                        pass
                _emit(unit.key, "verified" if result.status == "ok" else "failed")
                return result
            except ProviderTaskPending as ptp:
                # PRES-013: the remote async provider task is RUNNING and
                # holds a durable id. NEVER re-run from scratch, NEVER
                # resubmit -- persist the id so a later run polls the SAME
                # task. Zero additional transport on this pass.
                _persist_provider_task(run_dir, phase_id, unit.key,
                                       ptp.task_id, ptp.provider)
                _emit(unit.key, UNIT_STATES_PROVIDER_RUNNING)
                return UnitResult(
                    key=unit.key, status="pending_provider", attempts=attempts,
                    reasons=[f"provider task pending: {ptp.task_id}"],
                    meta={"provider_task_id": ptp.task_id,
                          "provider": ptp.provider,
                          "state": UNIT_STATES_PROVIDER_RUNNING})
            except Exception as exc:  # noqa: BLE001 -- transient-fault safety net (S2.3)
                last_exc = exc
                text = f"{type(exc).__name__}: {exc}"
                if _gov is not None and ("429" in text or
                                         "rate limit" in text.lower()):
                    try:
                        _gov.report_429(_gov_provider)
                    except Exception:  # noqa: BLE001
                        pass
                if attempts >= cap:
                    break
                _emit(unit.key, "retrying")
                # PRES-013: the retry backoff is bounded by the deadline
                # too -- sleeping past it would only guarantee the next
                # admission check fails. A zero/negative remaining budget
                # skips the sleep entirely (the re-check above handles it).
                if deadline_at is not None:
                    remaining = remaining_deadline_s(deadline_at)
                    if remaining <= 0:
                        _emit(unit.key, "skipped")
                        return UnitResult(
                            key=unit.key, status="skipped",
                            attempts=attempts,
                            reasons=["phase deadline reached during backoff"])
                    # Sleep bounded by the remaining budget, minus one clock
                    # read is NOT taken again -- remaining was read above.
                    time.sleep(min(min(30, 5 * attempts), remaining))
                else:
                    time.sleep(min(30, 5 * attempts))
            finally:
                if _gov is not None and _lease is not None:
                    try:
                        _gov.release(_lease)
                    except Exception:  # noqa: BLE001
                        pass
        # PRES-013: the worker raised on every attempt with no result and
        # no provider task id. The DURABLE async-pending marker keeps the
        # phase surface showing a resumable failure (append_unit_ledger_row
        # is called by the dispatcher on every result) -- the thread itself
        # already returned by raising; nothing here is pretend-killed.
        _emit(unit.key, "failed")
        return UnitResult(
            key=unit.key, status="failed", attempts=attempts,
            reasons=[f"worker raised: {last_exc}",
                     "deadline_exceeded:async_pending -- attempt did not "
                     "return within per_unit_timeout_s; unit is resumable, "
                     "no transport was left billed in flight"])

    results: Dict[str, UnitResult] = {}
    # PRES-013 bounded admission: a ThreadPoolExecutor queue is UNBOUNDED --
    # submit-all-then-join is exactly the eager-submission defect. Admission
    # advances only when a slot is actually free (or prefetch depth remains),
    # and the deadline is re-checked per admission on THIS thread (the
    # admitting thread) -- its read is the unit's verdict, passed to the
    # worker as a snapshot so worker/admit scheduling races can never flip
    # the decision.
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures: Dict[Any, Unit] = {}
        in_flight = 0
        queue_depth = workers + max(0, int(prefetch))
        for unit in units:
            # Admission check 1: bounded queue. While the pool is full
            # (beyond the prefetch allowance) DRAIN one finished future
            # FIRST -- a queued unit never waits behind an unbounded backlog,
            # which is what made "queued" and "already started"
            # indistinguishable before. The drain also fixes the ordering:
            # a unit is only admitted when a slot is genuinely free.
            while in_flight >= queue_depth:
                done = next(as_completed(list(futures)))
                finished_unit = futures.pop(done)
                in_flight -= 1
                results[finished_unit.key] = done.result()
            # Admission check 2: the phase deadline, checked AT THE MOMENT
            # real work could start (slot free). ONE time.monotonic() read
            # per unit, in input order, on this thread -- the read is shared
            # by the admit verdict AND the transport stamps handed to the
            # worker (the single scripted-clock contract the existing
            # deadline tests assert; no second read anywhere per admission).
            now = time.monotonic() if deadline_at is not None else None
            if deadline_at is not None and now >= deadline_at:
                results[unit.key] = UnitResult(
                    key=unit.key, status="skipped", attempts=0,
                    reasons=["phase deadline reached before admission"])
                _emit(unit.key, "skipped")
                continue
            stamps = _stamp_deadline(
                unit, (max(0.0, deadline_at - now)
                       if deadline_at is not None else None))
            _emit(unit.key, UNIT_STATES_QUEUED)
            futures[pool.submit(_run_one, unit,
                                {"admitted": True, "stamps": stamps})] = unit
            in_flight += 1
        # S2.4: no fail-fast, no cancellation -- every ADMITTED unit runs to
        # its own conclusion even after the deadline has passed; the
        # deadline's job is to stop NEW work, and queued-not-admitted units
        # are already skipped above with zero transport.
        for fut in as_completed(futures):
            unit = futures[fut]
            results[unit.key] = fut.result()

    return [results[u.key] for u in units]


def phase_worker_env_var(phase_id: str) -> str:
    """The shell-legal env-var name that overrides ONE phase's fan-out width.

    F6 (2026-09-06): this used to be an inline `re.sub` in dispatcher.py's
    P4-PROMPT pool path and nothing at all on the manifest fan-out path. A raw
    f-string `PRESENTATION_PHASE_WORKERS_{phase_id}` is NOT settable from a
    shell for any real phase id -- every fan-out phase in the shipped manifest
    has a hyphen in it ("P-PROMPT-QC", "P-U-DESIGN-SALES") and one has a dot
    ("P8.3-INFOGRAPHIC"), and `PRESENTATION_PHASE_WORKERS_P-PROMPT-QC=8` is not
    a valid assignment in sh/bash/zsh. Every non-alphanumeric run collapses to
    a single underscore so the override an operator can actually type is the
    one this reads:

        P-PROMPT-QC     -> PRESENTATION_PHASE_WORKERS_P_PROMPT_QC
        P8.3-INFOGRAPHIC-> PRESENTATION_PHASE_WORKERS_P8_3_INFOGRAPHIC
    """
    return "PRESENTATION_PHASE_WORKERS_" + \
        re.sub(r"[^A-Za-z0-9]+", "_", str(phase_id)).strip("_")


def resolve_effective_workers(
    phase_workers: int,
    unit_count: int,
    *,
    env_var: Optional[str] = None,
    capacity_available: Any = None,
) -> int:
    """Spec S3.3's resolution order:

        effective = min(
            declared_width,         # see below -- NOT always phase.workers
            env override if set,    # phase_worker_env_var(phase_id)
            unit_count,             # never more workers than units
            capacity_ceiling,       # capacity.probe(); UNBOUNDED drops out
        )

    The first term is whatever width the CALLER's own authority resolved:

      * `_dispatch_prompt_phase_fanout` (P4-PROMPT pool path) passes the
        manifest's `phase.workers` (12 on that phase).
      * `_dispatch_phase_fanout_units` (every manifest-declared `fanout`
        phase) passes the routing stamp's `measured_capacity` -- the same
        probe/mode-ceiling number P4-PROMPT's wave runs at. It must NOT pass
        `phase.workers` there: `Phase.workers` defaults to 1 (manifest.py:233)
        and 8 of the 9 fan-out phases declare none, so `phase.workers` as the
        first term is a hard cap of ONE and the whole phase runs serially
        (F6 / review 3.8).

    `capacity_available` is expected to be `capacity.probe()['available']` --
    a positive int or the UNBOUNDED sentinel. Reuses capacity.is_unbounded()'s
    own contract (`min(n, UNBOUNDED) == n`, capacity.py:253-259) rather than
    re-deriving it, so a NO_CAP_PROVIDERS account (deepseek-direct,
    openrouter) simply drops this term instead of being special-cased here.
    """
    effective = max(1, int(phase_workers))
    effective = min(effective, max(1, int(unit_count)))
    if env_var:
        raw = os.environ.get(env_var)
        if raw:
            try:
                env_val = int(raw)
                if env_val > 0:
                    effective = min(effective, env_val)
            except ValueError:
                pass
    if capacity_available is not None:
        try:
            from presentation_job import capacity as _capacity
            if _capacity.is_unbounded(capacity_available):
                pass  # UNBOUNDED drops out of the min() per its comparison contract
            elif isinstance(capacity_available, int) and capacity_available > 0:
                effective = min(effective, capacity_available)
        except Exception:  # noqa: BLE001 -- capacity probing is best-effort
            pass
    return max(1, effective)


# ---------------------------------------------------------------------------
# FIX 15b (MASTER Part 8 / W07a-B2): manifest-declared fanout by
# slide/section/file -- one unit per item.
#
# The manifest declares, on a per-phase entry:
#     "fanout": {"by": "slide"|"section"|"file", "max_units": N}
# and the dispatcher runs ONE unit per enumerated item (Prompts: one unit per
# slide. Prompt QC: one judge unit per slide. Image QC: one vision unit per
# slide. Copy: one unit per section. Design PNGs: one unit per page. Speech:
# one unit per slide). This module owns three things for that contract:
#
#   1. parse_fanout_field    -- manifest field -> FanoutSpec, refusing a
#                               malformed declaration at parse time (the same
#                               defect class _parse_workers_field refuses in
#                               manifest.py: silent coercion of a scheduling
#                               number).
#   2. enumerate_fanout_items -- run-dir truth -> the deterministic, ordered
#                               list of units for a spec. NO unit is invented:
#                               slides come from slides.json/arc_allocation
#                               (the same sources _prompt_slide_count trusts),
#                               sections from arc_allocation.json /
#                               slides_copy.md headings, files from the
#                               spec's own list or the phase's
#                               produces_artifact patterns.
#   3. append_unit_ledger_row -- one JSONL ledger row per unit into
#                               working/work-orders/_units/<phase>.units.jsonl
#                               ("each unit has its own ledger row", Part 7).
# ---------------------------------------------------------------------------
FANOUT_BY_VALUES = ("slide", "section", "file")


class FanoutSpecError(ValueError):
    """Raised when a manifest's `fanout` field is malformed. The dispatcher
    converts this into a phase error -- the run never proceeds with a guessed
    unit shape."""


@dataclass(frozen=True)
class FanoutSpec:
    by: str                      # "slide" | "section" | "file"
    max_units: Optional[int] = None   # submission-batch cap; None = all units at once

    def batches(self, units: List["Unit"]) -> List[List["Unit"]]:
        """Split `units` into submission batches of at most `max_units`.
        max_units=None (or <= 0, refused at parse) => one batch."""
        if not self.max_units or self.max_units >= len(units):
            return [units]
        return [units[i:i + self.max_units]
                for i in range(0, len(units), self.max_units)]


def parse_fanout_field(raw: Any) -> Optional[FanoutSpec]:
    """Manifest `fanout` field -> FanoutSpec, or None when absent.

    Absent/None => None (the phase is NOT fan-out enabled; the caller keeps
    its existing path untouched). Anything PRESENT but malformed raises
    FanoutSpecError -- a typo'd "by": "Slide" or a string "max_units": "12"
    must never silently degrade to serial dispatch (same refusal rule as
    manifest.py's _parse_workers_field).
    """
    if raw is None:
        return None
    if isinstance(raw, str) and not raw.strip():
        return None
    if not isinstance(raw, dict):
        raise FanoutSpecError(
            f"fanout must be an object {{by, max_units}}, got {raw!r}")
    by = raw.get("by")
    if not isinstance(by, str) or by.strip().lower() not in FANOUT_BY_VALUES:
        raise FanoutSpecError(
            f"fanout.by must be one of {FANOUT_BY_VALUES}, got {by!r}")
    max_units = raw.get("max_units")
    if max_units is not None:
        if isinstance(max_units, bool) or not isinstance(max_units, int) \
                or max_units < 1:
            raise FanoutSpecError(
                f"fanout.max_units must be a positive int, got {max_units!r}")
    return FanoutSpec(by=by.strip().lower(), max_units=max_units)


def unit_output_dir(run_dir: Path, phase_id: str) -> Path:
    """Per-unit scratch outputs for one phase: working/fanout/<phase_id>/."""
    return run_dir / "working" / "fanout" / phase_id


def unit_output_path(run_dir: Path, phase_id: str, unit_key: str) -> Path:
    """Where one unit's authored text lands before the dispatcher aggregates
    it into the phase's real artifact. Deterministic per unit key so a re-run
    (resume) of the same unit overwrites exactly its own scratch file."""
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", unit_key)
    return unit_output_dir(run_dir, phase_id) / f"{safe}.out"


def unit_ledger_path(run_dir: Path, phase_id: str) -> Path:
    return run_dir / "working" / "work-orders" / "_units" / f"{phase_id}.units.jsonl"


def append_unit_ledger_row(run_dir: Path, phase_id: str, row: Dict[str, Any]) -> None:
    """One JSONL row per unit into working/work-orders/_units/<phase>.units.jsonl.

    Append-only, best-effort (an OSError must never fail a unit that already
    did its real work). Rows carry at least: unit, status, attempts; callers
    add the provider/model/request-id stamps they already hold in hand."""
    try:
        path = unit_ledger_path(run_dir, phase_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        record = dict(row)
        record.setdefault("ts", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        record.setdefault("phase_id", phase_id)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        pass


def _slides_for_units(run_dir: Path) -> List[Dict[str, Any]]:
    """The slide list for by=slide units, from the SAME sources
    dispatcher._prompt_slide_count trusts (working/copy/slides.json, then
    arc_allocation.json). Ordered by ordinal; entries carry at least
    {"ordinal": int}. Returns [] when neither source is present/readable --
    the caller reports that honestly rather than inventing slides."""
    for rel in ("working/copy/slides.json", "slides.json", "working/slides.json"):
        p = run_dir / rel
        if not p.is_file():
            continue
        try:
            obj = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        raw = obj if isinstance(obj, list) else (
            obj.get("slides") if isinstance(obj, dict) else None)
        if isinstance(raw, list) and raw:
            out = []
            for s in raw:
                if isinstance(s, dict):
                    o = s.get("ordinal") if isinstance(s.get("ordinal"), int) else None
                    if o is None and isinstance(s.get("slide"), int):
                        o = s["slide"]
                    if o is None:
                        o = len(out) + 1  # positional fallback keeps order honest
                    out.append({"ordinal": int(o), **{k: v for k, v in s.items()
                                                      if k not in ("ordinal", "slide")}})
            if out:
                return sorted(out, key=lambda s: s["ordinal"])
    arc = run_dir / "working" / "copy" / "arc_allocation.json"
    if arc.is_file():
        try:
            obj = json.loads(arc.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            obj = None
        slots = None
        if isinstance(obj, dict):
            slots = obj.get("slots") or obj.get("allocation") or obj.get("slides")
        elif isinstance(obj, list):
            slots = obj
        if isinstance(slots, list) and slots:
            return [{"ordinal": i + 1, **(s if isinstance(s, dict) else {"slot": s})}
                    for i, s in enumerate(slots)]
    return []


def _sections_for_units(run_dir: Path) -> List[Dict[str, Any]]:
    """The section list for by=section units (P4-COPY: one unit per section).

    Priority: arc_allocation.json's own "sections" array (its declared shape),
    then the arc grouping of its slots, then the top-level headings of the
    existing slides_copy.md, then ONE whole-file unit. Ordered; entries carry
    {"name": str, "ordinal": int}."""
    arc = run_dir / "working" / "copy" / "arc_allocation.json"
    if arc.is_file():
        try:
            obj = json.loads(arc.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            obj = None
        if isinstance(obj, dict):
            secs = obj.get("sections")
            if isinstance(secs, list) and secs:
                return [{"ordinal": i + 1,
                         "name": str((s.get("name") if isinstance(s, dict) else s)
                                     or f"section-{i + 1:02d}")}
                        for i, s in enumerate(secs)]
            slots = obj.get("slots") or obj.get("allocation") or obj.get("slides")
            if isinstance(slots, list) and slots:
                names: List[str] = []
                for s in slots:
                    if not isinstance(s, dict):
                        continue
                    arc_name = s.get("arc") or s.get("section") or s.get("name")
                    if isinstance(arc_name, str) and arc_name.strip() \
                            and arc_name not in names:
                        names.append(arc_name)
                if names:
                    return [{"ordinal": i + 1, "name": n}
                            for i, n in enumerate(names)]
    copy_md = run_dir / "working" / "copy" / "slides_copy.md"
    if copy_md.is_file():
        try:
            names = []
            for line in copy_md.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("## ") and not line.startswith("### "):
                    n = line[3:].strip()
                    if n and n not in names:
                        names.append(n)
            if names:
                return [{"ordinal": i + 1, "name": n} for i, n in enumerate(names)]
        except OSError:
            pass
    return [{"ordinal": 1, "name": "whole"}]


def enumerate_fanout_items(run_dir: Path, spec: FanoutSpec, *, phase_id: str,
                           produces_artifact: Optional[List[str]] = None,
                           ) -> List[Dict[str, Any]]:
    """Deterministic, ordered unit items for one FanoutSpec against a run dir.

    Returns a list of item dicts, each carrying its stable `key` (the merge
    order for text aggregation) plus whatever the unit worker needs:
      by=slide    -> {"key": "slide-NN", "ordinal": N}
      by=section  -> {"key": "section-NN", "ordinal": N, "name": ...}
      by=file     -> {"key": "file-NN", "path": <rel path>}
    """
    if spec.by == "slide":
        slides = _slides_for_units(run_dir)
        return [{"key": f"slide-{s['ordinal']:02d}", "ordinal": s["ordinal"],
                 "slide": s} for s in slides]
    if spec.by == "section":
        secs = _sections_for_units(run_dir)
        return [{"key": f"section-{s['ordinal']:02d}", "ordinal": s["ordinal"],
                 "name": s["name"]} for s in secs]
    # by=file: the spec's own file list wins; else enumerate the phase's
    # produces_artifact patterns (a '*' pattern globs the run dir).
    rels: List[str] = []
    if isinstance(getattr(spec, "files", None), list):
        rels = [str(r) for r in spec.files if str(r).strip()]  # type: ignore[attr-defined]
    elif produces_artifact:
        for pattern in produces_artifact:
            if "*" in pattern or "?" in pattern:
                base = run_dir / pattern
                for hit in sorted(base.parent.glob(base.name)):
                    if hit.is_file():
                        rels.append(str(hit.relative_to(run_dir)))
            else:
                rels.append(pattern)
    seen: set = set()
    items: List[Dict[str, Any]] = []
    for rel in rels:
        if rel in seen:
            continue
        seen.add(rel)
        items.append({"key": f"file-{len(items) + 1:02d}", "path": rel})
    return items
