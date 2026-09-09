"""PRES-054 — one absolute deadline for persona resolution, owned-tree reap.

Defect: ``persona.resolve_for_phase`` runs ``governed_phase_voice`` under a
90-second Future wall with ``shutdown(wait=False)``, while the seam below
(``shared-utils/persona_for_job.py``) spawns the selector subprocess with a
600-second default. A timed-out Future does NOT stop the selector subprocess,
so a retry starts while expensive timed-out work is still alive.

This module is the single fix:

* :class:`Deadline` — one absolute monotonic deadline. The persona Future
  wall, the selector subprocess timeout and the provider-call budget all
  derive their remaining time from it. Nothing gets a fresh wall.
* Owned child-process tree — every selector subprocess is spawned in its own
  process group and registered under a resolution id. On timeout/cancel the
  whole group is SIGTERM'd, then SIGKILL'd, then reaped. A retry is admitted
  only after the reap proof exists. ``Future.cancel()`` is NEVER treated as
  proof the subprocess stopped (it only cancels the Python wait).
* Shared capacity — each attempt holds one governor lease for the whole
  attempt and releases it exactly once (idempotent guard), so slots cannot
  leak on the timeout path.
* Scoped immutable cache — successful bundles persist under
  ``<run>/working/persona_selections/`` keyed by the full immutable context
  hash. Only a byte-identical context reuses a bundle.
* Visible state — timeout/cancel emit ``persona_timeout`` /
  ``persona_cancelled`` events into the run's own state.json and never touch
  unrelated jobs.
* Provider resume — :class:`RemoteTaskRegistry` maps a scope to a known
  remote task id so a retry polls the existing remote task instead of
  creating a duplicate.
* Deadline propagation — the absolute deadline is exported on the wall clock
  (``PERSONA_FOR_JOB_DEADLINE``) so the selector spawn seam
  (``shared-utils/persona_for_job.py``) CLAMPS its own 600-second default to
  the caller's remaining time: the subprocess can never outlive the
  resolution that owns it.

stdlib only. Importing this module has no side effects.
"""
from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

GRACE_S = 2.0
CACHE_DIRNAME = "persona_selections"
REMOTE_TASKS_FILENAME = "persona_remote_tasks.json"

#: PRES-054 — one absolute resolution budget, shared by the persona Future
#: wall AND (propagated below) the selector subprocess. Mirrors
#: presentation_job.persona.BLEND_TIMEOUT_S at import time without importing
#: it (no cycle). Env override: PERSONA_BUDGET_S (read per-resolution, so a
#: test or operator can retune it between resolutions).
BLEND_TIMEOUT = 90.0


def current_budget_s() -> float:
    """The budget ONE resolution gets, read live so PERSONA_BUDGET_S can be
    set after import (tests, per-box operator retuning)."""
    raw = os.environ.get("PERSONA_BUDGET_S", "").strip()
    if raw:
        try:
            val = float(raw)
        except ValueError:
            return BLEND_TIMEOUT
        if val > 0:
            return val
    return BLEND_TIMEOUT


class PersonaTimeout(TimeoutError):
    """Persona resolution exceeded its absolute deadline.

    Carries the owned-tree reap ``proof`` dict so a caller (or test) can
    verify no owned child survived, without trusting the exception alone.
    """

    def __init__(self, message: str, proof: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.proof = proof or {}


class PersonaCancelled(RuntimeError):
    """Caller cancelled persona resolution.

    Subclasses RuntimeError (not TimeoutError) so the engine's existing
    ``except (RuntimeError, TimeoutError)`` handling stays safe, while
    ``isinstance`` checks can still tell cancel apart from timeout. The
    owned tree was terminated and reaped before this was raised; the
    ``proof`` attribute says so.
    """

    def __init__(self, message: str, proof: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.proof = proof or {}


# ---------------------------------------------------------------------------
# Absolute deadline
# ---------------------------------------------------------------------------
class Deadline:
    """One absolute deadline shared by future, subprocess, provider.

    ``remaining``/``exhausted`` run on the monotonic clock (immune to wall
    adjustments); ``wall_deadline`` is the same instant on the wall clock and
    is what gets exported to the selector subprocess (a child process cannot
    see our monotonic origin)."""

    def __init__(self, budget_s: float):
        self.budget_s = float(budget_s)
        self.started_at = time.monotonic()
        self.deadline = self.started_at + float(budget_s)
        self.wall_deadline = time.time() + float(budget_s)

    def remaining(self) -> float:
        """Seconds left; never negative."""
        return max(0.0, self.deadline - time.monotonic())

    def exhausted(self) -> bool:
        return time.monotonic() >= self.deadline


# ---------------------------------------------------------------------------
# Resolution identity (thread-local AND process env — the env copy is what
# the selector spawn path (persona_for_job) and worker threads read, since a
# ThreadPoolExecutor worker does not share the caller's thread-local).
# The env keys are process-wide: persona resolution assumes one active
# resolution per process at a time (the presentation engine runs phases
# sequentially in one process; concurrent resolutions must pass explicit
# ids/budgets instead of relying on these keys).
# ---------------------------------------------------------------------------
_PERSONA_DEADLINE_ENV = "PERSONA_FOR_JOB_DEADLINE"
_PERSONA_RESOLUTION_ENV = "PERSONA_RESOLUTION_ID"

_resolution_local = threading.local()


def set_current_resolution(resolution_id: str) -> None:
    _resolution_local.rid = resolution_id
    os.environ[_PERSONA_RESOLUTION_ENV] = resolution_id


def clear_current_resolution() -> None:
    _resolution_local.rid = None
    os.environ.pop(_PERSONA_RESOLUTION_ENV, None)


def current_resolution_id() -> Optional[str]:
    rid = getattr(_resolution_local, "rid", None)
    if rid:
        return str(rid)
    env = os.environ.get(_PERSONA_RESOLUTION_ENV, "").strip()
    return env or None


def export_wall_deadline(budget_s: float) -> float:
    """Export the absolute deadline to the process env so the selector spawn
    path (shared-utils/persona_for_job.py) can clamp its own ceiling to it.

    Returns the wall-clock deadline (epoch seconds). Called once when the
    FIRST attempt of a resolution starts;PersonaExecutor clears it when the
    whole resolution ends so an unrelated later spawn keeps its own default
    budget."""
    wall = time.time() + float(budget_s)
    os.environ[_PERSONA_DEADLINE_ENV] = repr(float(wall))
    return wall


def clear_wall_deadline() -> None:
    os.environ.pop(_PERSONA_DEADLINE_ENV, None)


def current_wall_deadline() -> Optional[float]:
    """The process's active absolute persona deadline, or None."""
    raw = os.environ.get(_PERSONA_DEADLINE_ENV, "").strip()
    if not raw:
        return None
    try:
        val = float(raw)
    except ValueError:
        return None
    return val if val > 0 else None


def new_resolution_id(job_id: str, phase_id: str, attempt: int) -> str:
    return f"{job_id}:{phase_id}:a{attempt}:{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Owned selector-process registry + whole-group terminate/reap
# ---------------------------------------------------------------------------
_REG_LOCK = threading.Lock()
_ACTIVE: Dict[str, set] = {}  # resolution_id -> set of Popen
_ATTEMPT_LOG: List[Dict[str, Any]] = []  # in-process sequential proof


def _log_attempt(event: Dict[str, Any]) -> None:
    with _REG_LOCK:
        _ATTEMPT_LOG.append(dict(event))


def attempt_log() -> List[Dict[str, Any]]:
    with _REG_LOCK:
        return [dict(e) for e in _ATTEMPT_LOG]


def clear_attempt_log() -> None:
    with _REG_LOCK:
        _ATTEMPT_LOG.clear()


def register_proc(resolution_id: Optional[str], proc: "subprocess.Popen") -> None:
    if not resolution_id:
        return
    with _REG_LOCK:
        _ACTIVE.setdefault(resolution_id, set()).add(proc)


def unregister_proc(resolution_id: Optional[str], proc: "subprocess.Popen") -> None:
    if not resolution_id:
        return
    with _REG_LOCK:
        procs = _ACTIVE.get(resolution_id)
        if procs is not None:
            procs.discard(proc)
            if not procs:
                _ACTIVE.pop(resolution_id, None)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _group_alive(proc: "subprocess.Popen") -> bool:
    """True if the owned process group still has any live member."""
    try:
        pgid = os.getpgid(proc.pid)
    except (ProcessLookupError, PermissionError, OSError):
        return False
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def live_owned_pids(resolution_id: str) -> List[int]:
    """Pids of owned procs (or their groups) still alive. Proof helper."""
    out: List[int] = []
    with _REG_LOCK:
        procs = list(_ACTIVE.get(resolution_id, set()))
    for proc in procs:
        try:
            exited = proc.poll() is not None
        except Exception:
            exited = False
        if not exited or _group_alive(proc):
            try:
                out.append(proc.pid)
            except Exception:
                pass
    return out


def terminate_owned_tree(resolution_id: str,
                         grace_s: float = GRACE_S) -> Dict[str, Any]:
    """SIGTERM the owned group, SIGKILL survivors, reap everything.

    Sequential and blocking: returns only after every owned proc is reaped
    (or proven gone). The returned proof names signalled/killed/reaped pids
    and any ``live_after`` remainder — a retry must not start unless
    ``live_after`` is empty and ``reap_complete`` is True.
    """
    with _REG_LOCK:
        procs = list(_ACTIVE.get(resolution_id, set()))
    proof: Dict[str, Any] = {
        "resolution_id": resolution_id,
        "signalled": [],
        "killed": [],
        "reaped": [],
        "live_after": [],
        "reap_complete": True,
    }
    for proc in procs:
        pid = getattr(proc, "pid", None)
        try:
            pgid = os.getpgid(proc.pid)
        except (ProcessLookupError, PermissionError, OSError):
            pgid = None
        if pgid is not None:
            try:
                os.killpg(pgid, signal.SIGTERM)
                if pid is not None:
                    proof["signalled"].append(pid)
            except (ProcessLookupError, PermissionError, OSError):
                pass
    deadline = time.monotonic() + max(0.0, grace_s)
    for proc in procs:
        pid = getattr(proc, "pid", None)
        while time.monotonic() < deadline:
            try:
                if proc.poll() is not None and not _group_alive(proc):
                    break
            except Exception:
                break
            time.sleep(0.05)
        try:
            still = proc.poll() is None or _group_alive(proc)
        except Exception:
            still = False
        if still:
            try:
                pgid = os.getpgid(proc.pid)
            except (ProcessLookupError, PermissionError, OSError):
                pgid = None
            if pgid is not None:
                try:
                    os.killpg(pgid, signal.SIGKILL)
                    if pid is not None:
                        proof["killed"].append(pid)
                except (ProcessLookupError, PermissionError, OSError):
                    pass
        try:
            proc.wait(timeout=5)
        except Exception:
            pass
        try:
            if proc.poll() is not None:
                if pid is not None:
                    proof["reaped"].append(pid)
            else:
                proof["reap_complete"] = False
                if pid is not None:
                    proof["live_after"].append(pid)
        except Exception:
            proof["reap_complete"] = False
        unregister_proc(resolution_id, proc)
    # Final sweep: anything still registered under this id is live remainder.
    remainder = live_owned_pids(resolution_id)
    if remainder:
        proof["live_after"].extend(p for p in remainder if p not in proof["live_after"])
        proof["reap_complete"] = False
    _log_attempt({"at": time.time(), "resolution_id": resolution_id,
                  "event": "tree_terminated", "proof": proof})
    return proof


# ---------------------------------------------------------------------------
# Scoped immutable selection cache (identical context only)
# ---------------------------------------------------------------------------
def scope_hash(context: Dict[str, Any]) -> str:
    raw = json.dumps(context, sort_keys=True, separators=(",", ":"),
                     default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cache_path(run_dir: Path, phase_id: str, ctx_hash: str) -> Path:
    safe_phase = "".join(c if (c.isalnum() or c in "-_") else "_" for c in phase_id)
    return (Path(run_dir) / "working" / CACHE_DIRNAME
            / f"{safe_phase}_{ctx_hash[:16]}.json")


def cache_load(run_dir: Path, phase_id: str,
               ctx_hash: str) -> Optional[Dict[str, Any]]:
    """Return the cached bundle only if its stored hash is byte-identical."""
    path = cache_path(run_dir, phase_id, ctx_hash)
    try:
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("context_hash") != ctx_hash:
        return None
    bundle = data.get("bundle")
    return bundle if isinstance(bundle, dict) else None


def cache_save(run_dir: Path, phase_id: str, ctx_hash: str,
               bundle: Dict[str, Any], meta: Optional[Dict[str, Any]] = None) -> Path:
    path = cache_path(run_dir, phase_id, ctx_hash)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"context_hash": ctx_hash, "phase_id": phase_id,
               "bundle": bundle, "meta": meta or {}}
    tmp = path.with_suffix(path.suffix + f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    os.replace(tmp, path)
    return path


# ---------------------------------------------------------------------------
# Provider remote-task registry (resume by known id, never duplicate create)
# ---------------------------------------------------------------------------
class RemoteTaskRegistry:
    """Maps a scope key to a known provider remote task id.

    ``get_or_create`` polls the recorded id when one is known and only calls
    ``create_fn`` when no id exists for the scope. Backed by one JSON file
    under the run dir so a retry/restart resumes instead of re-creating.
    """

    def __init__(self, run_dir: Path):
        self.path = Path(run_dir) / "working" / REMOTE_TASKS_FILENAME
        self._lock = threading.Lock()

    def _read_all(self) -> Dict[str, Any]:
        try:
            if self.path.is_file():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except (OSError, json.JSONDecodeError):
            pass
        return {}

    def known_id(self, scope: str) -> Optional[str]:
        with self._lock:
            entry = self._read_all().get(scope)
        if isinstance(entry, dict) and entry.get("remote_id"):
            return str(entry["remote_id"])
        return None

    def record(self, scope: str, remote_id: str,
               extra: Optional[Dict[str, Any]] = None) -> None:
        with self._lock:
            data = self._read_all()
            data[scope] = {"remote_id": remote_id,
                           "recorded_at": time.time(),
                           **(extra or {})}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + f".tmp-{os.getpid()}")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)

    def get_or_create(self, scope: str, known_remote_id: Optional[str],
                      create_fn: Callable[[], str],
                      poll_fn: Callable[[str], Any]) -> Any:
        """Poll the known id; create exactly once only when nothing is known."""
        recorded = self.known_id(scope)
        target = known_remote_id or recorded
        if target:
            if not recorded:
                self.record(scope, target, {"source": "caller-known"})
            return poll_fn(target)
        fresh = create_fn()
        self.record(scope, fresh, {"source": "created"})
        return poll_fn(fresh)


# ---------------------------------------------------------------------------
# Shared-capacity lease with release-once semantics
# ---------------------------------------------------------------------------
#: Optional client-account lease adapters, set by a client-account governor
#: integration via :func:`set_lease_provider`. Kept as a module-level pair so
#: a test (or a client integration) can inject an account-scoped capacity
#: authority without subclassing; the engine's own governor stays the default.
_PROVIDER_ADAPTER: List[Any] = [None, None]  # (acquire_fn, release_fn)


def set_lease_provider(acquire_fn: Optional[Callable[..., Any]],
                       release_fn: Optional[Callable[..., Any]]) -> None:
    """Register (or, with (None, None), clear) external lease adapters."""
    _PROVIDER_ADAPTER[0] = acquire_fn
    _PROVIDER_ADAPTER[1] = release_fn


class LeaseGuard:
    """One governor lease held for a whole attempt; release is idempotent.

    ``acquire`` prefers the caller-supplied ``acquire_fn``/``release_fn``
    adapters (a client account governor registered via
    :func:`set_lease_provider`), then the engine's own rate governor
    (presentation_job.governor, the shared per-provider capacity authority —
    persona selection is accounted under the ``persona`` provider so a
    selector run can never exceed the same shared ceilings as a paid call),
    and degrades to a counted no-op lease when neither is reachable so
    persona resolution still terminates/reaps correctly off-platform. The
    no-op is still counted: ``acquired`` stays False only when NOTHING
    accounted the lease.
    """

    def __init__(self, provider: str = "persona"):
        self.provider = provider
        self._lease: Any = None
        self._released = False
        self._lock = threading.Lock()
        self.acquired = False
        self._acquire_fn = _PROVIDER_ADAPTER[0]
        self._release_fn = _PROVIDER_ADAPTER[1]

    def acquire(self, timeout_s: Optional[float] = None) -> "LeaseGuard":
        if self._acquire_fn is not None:
            self._lease = self._acquire_fn(self.provider, timeout_s=timeout_s)
            self.acquired = True
            return self
        try:
            from . import governor as _gov
        except Exception:
            return self  # off-platform: no governor module, counted no-op
        # The governor is the shared capacity authority: an admission
        # timeout (or cap exhaustion) is a REAL refusal — propagate it, never
        # silently proceed unaccounted (that would defeat the shared cap).
        try:
            self._prime_provider(_gov)
        except Exception:
            pass
        self._lease = _gov.acquire(self.provider, n=1, timeout_s=timeout_s)
        self.acquired = True
        self._release_fn = _gov.release
        return self

    @staticmethod
    def _prime_provider(_gov: Any) -> None:
        """Pre-fill the persona provider's token bucket so an admission with
        free capacity NEVER enters the governor's block-poll loop.

        The poll loop sleeps ``time.sleep`` per deficit tick; a persona
        resolution runs inside engine code whose tests (and, rarely, hosts)
        instrument ``time.sleep`` globally — an admission that is free must
        not spend 85 poll-sleeps (and ~85 fake-clock ticks) getting a token
        it can have immediately. Priming once per provider mirrors the
        token-bucket-at-start semantics (burst full) without touching the
        governor module other units own."""
        with _gov._lock:
            st = _gov._state_for("persona")
            if st.last_refill <= 0.0:  # never acquired before: cold state
                cfg = _gov.provider_config("persona")
                st.tokens = float(cfg["burst"])
                st.last_refill = time.time()

    def release(self) -> None:
        with self._lock:
            if self._released:
                return
            self._released = True
        if self._lease is not None and self._release_fn is not None:
            try:
                self._release_fn(self._lease)
            except Exception:
                pass
            self._lease = None

    def __enter__(self) -> "LeaseGuard":
        return self.acquire()

    def __exit__(self, *exc: Any) -> None:
        self.release()


# ---------------------------------------------------------------------------
# Visible per-run state (own run_dir only; silent no-op without state.json)
# ---------------------------------------------------------------------------
def _state_store_exists(run_dir: Path) -> bool:
    try:
        from .state import STATE_FILENAME
    except Exception:
        return False
    return (Path(run_dir) / STATE_FILENAME).is_file()


def record_event(run_dir: Path, kind: str, message: str, **extra: Any) -> None:
    """Append one event to the run's own state.json. Never raises."""
    try:
        if not _state_store_exists(Path(run_dir)):
            return
        from .report import Reporter
        from .state import StateStore
        store = StateStore(Path(run_dir))
        state = store.load()
        Reporter(state, store).event(kind, message, **extra)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# PersonaExecutor — the PRES-054 resolution attempt runner
# ---------------------------------------------------------------------------
#: Total resolution attempts (initial + ONE bounded retry — the Fix-28 shape,
#: preserved as a bound). A retry is admitted only after the previous
#: attempt's owned tree is reaped, so retries never overlap.
MAX_RESOLVE_ATTEMPTS = 2

#: The per-resolution wall. ONE absolute deadline spans every attempt AND the
#: selector subprocess below (persona_for_job reads PERSONA_FOR_JOB_DEADLINE
#: and clamps its own spawn ceiling to it) — no per-retry fresh wall.
#: Kept as an alias for backwards-compatible references; the live value comes
#: from current_budget_s() so PERSONA_BUDGET_S can change between resolutions.
RESOLVE_BUDGET_S = BLEND_TIMEOUT


def resolve_persona(
    run_fn: Callable[..., Any],
    run_args: tuple,
    run_kwargs: Dict[str, Any],
    budget_s: float,
    attempts: int = MAX_RESOLVE_ATTEMPTS,
    on_state: Optional[Callable[[str, str], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    job_id: str = "job",
    phase_id: str = "phase",
) -> Any:
    """Run ``run_fn`` under ONE absolute deadline with owned-tree reaping.

    Contract (PRES-054 step 1):
      * ONE absolute deadline started once here bounds every attempt and the
        selector subprocess below (via PERSONA_FOR_JOB_DEADLINE).
      * Each attempt holds ONE governor lease for its whole attempt and
        releases it exactly once (LeaseGuard).
      * A timed-out attempt's owned child process tree is SIGTERM'd,
        SIGKILL'd and reaped BEFORE the next attempt starts — Future.cancel()
        is never treated as proof the subprocess stopped.
      * Bounded retries; cancellation is checked at the attempt boundary and
        raises PersonaCancelled with the reap proof attached.
      * Visible state: ``on_state(kind, message)`` (wired to
        record_event/run's own state.json) fires ``persona_timeout`` /
        ``persona_cancelled``; unrelated jobs are never touched.

    Raises PersonaTimeout / PersonaCancelled with ``proof`` (the terminate/
    reap receipt). Success returns ``run_fn``'s value.
    """
    deadline = Deadline(budget_s)
    export_wall_deadline(budget_s)
    try:
        return _resolve_persona_attempts(
            run_fn, run_args, run_kwargs, deadline, budget_s, attempts,
            on_state, cancel_event, job_id, phase_id)
    finally:
        # the exported wall deadline is THIS resolution's; clear it on every
        # exit (success, timeout, cancel, error) so a later unrelated spawn
        # keeps its own default budget
        clear_wall_deadline()


def _resolve_persona_attempts(
    run_fn: Callable[..., Any],
    run_args: tuple,
    run_kwargs: Dict[str, Any],
    deadline: "Deadline",
    budget_s: float,
    attempts: int,
    on_state: Optional[Callable[[str, str], None]],
    cancel_event: Optional[threading.Event],
    job_id: str,
    phase_id: str,
) -> Any:
    attempt = 0
    while attempt < max(1, int(attempts)):
        attempt += 1
        if cancel_event is not None and cancel_event.is_set():
            proof = terminate_owned_tree(
                f"{job_id}:{phase_id}", GRACE_S)  # belt: nothing yet spawned
            if on_state:
                on_state("persona_cancelled",
                         f"persona resolution for {phase_id} was cancelled "
                         "before attempt %d; owned child tree terminated and "
                         "reaped" % attempt)
            raise PersonaCancelled(
                f"persona resolution for {phase_id} cancelled before attempt "
                f"{attempt}", proof)

        if deadline.exhausted():
            proof: Dict[str, Any] = {"resolution_id": f"{job_id}:{phase_id}",
                                     "live_after": [], "reap_complete": True}
            if on_state:
                on_state("persona_timeout",
                         f"persona resolution for {phase_id} exceeded the "
                         f"absolute deadline ({budget_s}s) before attempt "
                         f"{attempt}")
            raise PersonaTimeout(
                f"persona resolution deadline ({budget_s}s) exhausted before "
                f"attempt {attempt} of {attempts} for phase {phase_id}", proof)

        rid = new_resolution_id(job_id, phase_id, attempt)
        set_current_resolution(rid)
        # Attempt 1 owns the full budget; a later attempt gets only the true
        # remainder of the ONE absolute deadline (attempt-level timeout values
        # still sum to the same wall — no fresh budget per retry).
        remaining = (budget_s if attempt == 1
                     else max(0.001, deadline.remaining()))
        ex = ThreadPoolExecutor(max_workers=1)
        fut = None
        lease = LeaseGuard(provider="persona").acquire(
            timeout_s=remaining if remaining > 0 else None)
        try:
            fut = ex.submit(run_fn, *run_args, **run_kwargs)
            bundle = fut.result(timeout=remaining)
            lease.release()
            return bundle
        except FuturesTimeout:
            # Cancel the PYTHON wait, then PROVE the subprocess stopped:
            # terminate/reap the owned tree BEFORE any replacement starts.
            if fut is not None:
                fut.cancel()
            proof = terminate_owned_tree(rid, GRACE_S)
            lease.release()
            if attempt >= max(1, int(attempts)):
                if on_state:
                    on_state("persona_timeout",
                             f"persona resolution for {phase_id} exceeded the "
                             f"absolute deadline ({budget_s}s) after "
                             f"{attempt} attempt(s); owned child tree "
                             "terminated and reaped before this state was "
                             "recorded")
                raise PersonaTimeout(
                    f"persona resolution timed out after {budget_s}s "
                    f"(absolute deadline, {attempt} of {attempts} attempts) "
                    f"for phase {phase_id}; owned child tree reaped "
                    f"(reap_complete={proof.get('reap_complete')})", proof)
            # bounded retry — falls through to the next loop iteration
        except BaseException:
            # non-timeout failure (or cancel racing in): release once; the
            # owned tree is still reaped so nothing survives the attempt.
            if fut is not None:
                fut.cancel()
            terminate_owned_tree(rid, GRACE_S)
            try:
                lease.release()
            except Exception:
                pass
            raise
        finally:
            ex.shutdown(wait=False)
            clear_current_resolution()
    # unreachable (loop always returns or raises), kept for shape honesty
    raise PersonaTimeout(
        f"persona resolution for {phase_id} exhausted {attempts} attempts",
        {"resolution_id": f"{job_id}:{phase_id}", "live_after": [],
         "reap_complete": True})


class PersonaExecutor:
    """Thin object wrapper over :func:`resolve_persona` with the run context
    bound. presentation_job.persona.resolve_for_phase constructs one per
    resolution and calls :meth:`run` — the only seam it needs."""

    def __init__(self, job_id: str = "job", phase_id: str = "phase",
                 run_dir: Optional[Path] = None,
                 attempts: int = MAX_RESOLVE_ATTEMPTS,
                 budget_s: Optional[float] = None,
                 on_state: Optional[Callable[[str, str], None]] = None,
                 cancel_event: Optional[threading.Event] = None):
        self.job_id = job_id
        self.phase_id = phase_id
        self.run_dir = Path(run_dir) if run_dir is not None else None
        self.attempts = attempts
        self.budget_s = (current_budget_s()
                         if budget_s is None else float(budget_s))
        self._on_state = on_state
        self.cancel_event = cancel_event

    def _state_emitter(self) -> Optional[Callable[[str, str], None]]:
        if self._on_state is not None:
            return self._on_state
        run_dir = self.run_dir

        def _emit(kind: str, message: str) -> None:
            if run_dir is not None:
                record_event(run_dir, kind, message, phase_id=self.phase_id)
        return _emit

    def run(self, run_fn: Callable[..., Any], *args: Any,
            **kwargs: Any) -> Any:
        return resolve_persona(
            run_fn, args, kwargs,
            budget_s=self.budget_s,
            attempts=self.attempts,
            on_state=self._state_emitter(),
            cancel_event=self.cancel_event,
            job_id=self.job_id,
            phase_id=self.phase_id)
