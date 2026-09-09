#!/usr/bin/env python3
"""PRES-008 — the durable submission-state ledger for the intake bridge.

THE DEFECT THIS CLOSES
----------------------
Before PRES-008, `intake_bridge.cmd_poll` kept a BOOLEAN poll ledger: a bare
text file of session ids, appended the moment `cmd_ingest` returned 0. And
`cmd_ingest` returned 0 whenever the Command Center card existed — even when
the engine dispatch had been REFUSED (capacity unmeasured, notify unconfigured,
deck type unresolvable), and even when the worker's /api/dept-start answered
202 "deferred". A submission the engine never launched was therefore stamped
"processed" forever: the bridge lost the retry, and the deck stalled silently
unless some other actor (the local intake-poll, whose coverage of a box's runs
is conditional) happened to pick it up.

THE CONTRACT THIS MODULE GIVES THE BRIDGE
-----------------------------------------
Every submission carries a durable, crash-safe state document — one JSON file
per session, atomically written (temp + fsync + os.replace) under the run
dir's own working/checkpoints/, next to the checkpoints it protects:

    working/checkpoints/intake_submission_state.json

with the seven states the PRES-008 spec names:

    staged              submission claimed; run-dir record being written
    board_registered    CC kanban card exists; board task id PERSISTED
    launch_pending      waiting for an engine launch; a retry is scheduled
    launching           a dispatch attempt is in flight under a current
                        execution id (the crash window: a crash here is
                        recoverable — the next tick discovers the live worker)
    worker_acknowledged COMPLETE — a current execution id AND a live
                        worker-start acknowledgement are persisted
    failed_retryable    an attempt failed unexpectedly (transport, crash);
                        retry scheduled with bounded backoff
    blocked_actionable  a PERMANENT refusal (or exhausted retry budget);
                        remediation recorded; no further automatic retries

THE RULES THE BRIDGE DEPENDS ON
-------------------------------
1.  Completion requires BOTH a current execution id and a worker-start
    acknowledgement (mark_worker_acknowledged raises without an execution id —
    fail closed, never complete on a bare rc).
2.  Board task id and run binding persist across launch retries: the bridge
    never re-ingests a submission whose board_task_id is recorded, so the card
    is never duplicated and the binding never moves.
3.  A live existing worker's acknowledgement is an IDEMPOTENT success —
    re-acking a completed submission changes nothing.
4.  Retries are BOUNDED: exponential backoff (base * 2^(n-1), capped) between
    attempts, a hard attempt budget, and CEO/operator notification thresholds
    crossed at configured attempt counts — an operator hears about a stuck
    submission at attempt 3 and again at 7, not every five minutes forever.
5.  A permanent refusal (or exhausted budget) lands in blocked_actionable with
    a recorded REMEDIATION, and stops consuming retries — every other session
    keeps progressing.
6.  Concurrent pollers claim a submission atomically (O_CREAT|O_EXCL on the
    state file): exactly one execution per run; the loser skips the tick and
    the claim is recoverable after the claim TTL.
7.  Completed intake records and checkpoints are never overwritten by a
    retry — the bridge only writes the run-dir record in `staged`, before any
    of this state exists to say otherwise.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional

#: The state document lives INSIDE the run dir it describes — per-session
#: isolation is the run dir's, and a submission's state travels with its run.
STATE_FILENAME = "intake_submission_state.json"
LEDGER_VERSION = 1

#: History rows kept per submission (bounded — a submission retried for weeks
#: must not grow an unbounded document).
HISTORY_MAX = 50

#: How long another poller's claim blocks this one, before the claim is
#: treated as crashed and taken over.
DEFAULT_CLAIM_TTL_S = 120.0

#: Bounded backoff between launch retries: base * 2^(attempt-1), capped.
DEFAULT_BACKOFF_BASE_S = 60.0
DEFAULT_BACKOFF_CAP_S = 1800.0

#: The hard retry budget. A submission that fails this many attempts is
#: blocked_actionable with a remediation, never retried again automatically.
DEFAULT_MAX_RETRY_ATTEMPTS = 10

#: Attempt counts at which the operator (CEO/client channel via the notify
#: transport) is told — escalating attention without spam.
DEFAULT_NOTIFY_THRESHOLDS = (3, 7)

# --- the seven states -------------------------------------------------------
STAGED = "staged"
BOARD_REGISTERED = "board_registered"
LAUNCH_PENDING = "launch_pending"
LAUNCHING = "launching"
WORKER_ACKNOWLEDGED = "worker_acknowledged"
FAILED_RETRYABLE = "failed_retryable"
BLOCKED_ACTIONABLE = "blocked_actionable"

STATES = (STAGED, BOARD_REGISTERED, LAUNCH_PENDING, LAUNCHING,
          WORKER_ACKNOWLEDGED, FAILED_RETRYABLE, BLOCKED_ACTIONABLE)

#: End states. WORKER_ACKNOWLEDGED is the handoff complete; BLOCKED_ACTIONABLE
#: needs a human and gets no more automatic attempts.
TERMINAL_STATES = (WORKER_ACKNOWLEDGED, BLOCKED_ACTIONABLE)

Notifier = Callable[[str, str, str], None]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).isoformat(timespec="seconds")


def _parse_iso(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def state_path(run_dir, session_id: str) -> Path:
    """Where this submission's durable state document lives."""
    return Path(run_dir) / "working" / "checkpoints" / STATE_FILENAME


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(run_dir, session_id: str) -> Optional[Dict[str, Any]]:
    """Read the submission's state document, or None when absent OR unreadable.

    A corrupt file deliberately reads as None (the caller distinguishes
    absent from corrupt via acquire_new's O_EXCL failure and decides — a file
    that cannot be parsed must never be silently trusted as a clean state).
    """
    try:
        raw = state_path(run_dir, session_id).read_text(encoding="utf-8")
        doc = json.loads(raw)
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or doc.get("session_id") != session_id:
        return None
    return doc


def acquire_new(run_dir, session_id: str, *, initial: str = STAGED,
                holder: Optional[Dict[str, Any]] = None,
                run_dir_str: str = "",
                extra: Optional[Dict[str, Any]] = None,
                now: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """Atomically CLAIM a brand-new submission (O_CREAT|O_EXCL).

    Returns the fresh state document, or None when the file already exists
    (another poller claimed it first, or a corrupt file sits there — the
    caller then load()s and decides) or the write failed. The claim record
    makes dual-poller races deterministic: exactly one poller owns a run's
    dispatch at a time, and the claim is recoverable (see reclaim /
    claim_is_fresh) after the claim TTL.
    """
    now = now or _now()
    doc: Dict[str, Any] = {
        "version": LEDGER_VERSION,
        "session_id": session_id,
        "state": initial if initial in STATES else STAGED,
        "run_dir": run_dir_str or str(run_dir),
        "created_at": _iso(now),
        "updated_at": _iso(now),
        "revision": 1,
        "claim": {
            "claimed_by": (holder or {}).get("claimed_by", ""),
            "claimed_at": _iso(now),
        },
        "history": [{"at": _iso(now), "from": "", "to": doc_state(initial),
                     "why": "submission claimed"}],
    }
    if extra:
        doc.update(extra)
    path = state_path(run_dir, session_id)
    payload = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
        except BaseException:
            try:
                os.unlink(path)
            except OSError:
                pass
            raise
    except FileExistsError:
        return None
    except OSError:
        return None
    return doc


def doc_state(initial: str) -> str:
    return initial if initial in STATES else STAGED


def reclaim(run_dir, session_id: str, doc: Dict[str, Any],
            holder: Optional[Dict[str, Any]] = None,
            now: Optional[datetime] = None) -> Dict[str, Any]:
    """Take over an expired (crashed) claim: refresh the claim record."""
    now = now or _now()
    doc["claim"] = {
        "claimed_by": (holder or {}).get("claimed_by", ""),
        "claimed_at": _iso(now),
        "took_over": True,
    }
    return save(run_dir, session_id, doc, now=now)


def release_claim(run_dir, session_id: str, doc: Dict[str, Any]) -> Dict[str, Any]:
    """Clear THIS tick's driver claim and persist.

    The claim serializes CONCURRENT drivers of one submission only — it is
    never ownership BETWEEN ticks: once this driver has finished its drive
    (any verdict), the claim is released so the next tick re-drives the
    submission immediately (bounded backoff still applies via
    next_retry_at). A driver that CRASHES mid-drive never reaches this —
    its stale claim is taken over after the claim TTL (reclaim), which is
    exactly the recoverable-ownership contract."""
    if not isinstance(doc, dict) or not doc:
        return doc
    doc.pop("claim", None)
    return save(run_dir, session_id, doc)


def claim_is_fresh(doc: Dict[str, Any], mine: str,
                   ttl_s: float = DEFAULT_CLAIM_TTL_S,
                   now: Optional[datetime] = None) -> bool:
    """True when ANOTHER holder's claim is still live (this caller must skip).

    A claim by THIS caller is never "fresh" (it is ours to re-drive); an
    unparseable or missing claim is never fresh (nothing provably holds it);
    a claim older than ttl_s is a crashed poller's — steal it.
    """
    claim = doc.get("claim") if isinstance(doc, dict) else None
    if not isinstance(claim, dict):
        return False
    if claim.get("claimed_by") == mine:
        return False
    claimed_at = _parse_iso(claim.get("claimed_at"))
    if claimed_at is None:
        return False
    now = now or _now()
    return (now - claimed_at).total_seconds() < max(0.0, ttl_s)


def save(run_dir, session_id: str, doc: Dict[str, Any],
         now: Optional[datetime] = None) -> Dict[str, Any]:
    """Persist the state document atomically (tmp + fsync + os.replace).

    Bumps revision and updated_at. Returns the saved document. A write
    failure raises OSError — the bridge treats an unsaved transition as an
    attempt that did not happen, never as a completion.
    """
    now = now or _now()
    doc["updated_at"] = _iso(now)
    doc["revision"] = int(doc.get("revision") or 0) + 1
    history = doc.get("history")
    if isinstance(history, list) and len(history) > HISTORY_MAX:
        doc["history"] = history[-HISTORY_MAX:]
    path = state_path(run_dir, session_id)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".substate-",
                               suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return doc


def transition(run_dir, session_id: str, doc: Dict[str, Any], new_state: str,
               why: str = "", **fields: Any) -> Dict[str, Any]:
    """Move the submission to `new_state`, recording one history row.

    Refuses (raises RuntimeError) any transition OUT of worker_acknowledged —
    a completed handoff is final; idempotent re-acks go through
    mark_worker_acknowledged, never through a transition.
    """
    if new_state not in STATES:
        raise ValueError(f"unknown submission state {new_state!r}")
    if not isinstance(doc, dict) or not doc:
        raise ValueError("transition needs a loaded state document")
    old = doc.get("state")
    if new_state == WORKER_ACKNOWLEDGED:
        # PRES-008: a completion without a PERSISTED current execution id is
        # the exact defect this module exists to close — fail closed.
        ack = doc.get("worker_ack") if isinstance(doc.get("worker_ack"), dict) else {}
        if not str(ack.get("execution_id") or "").strip():
            raise ValueError(
                "cannot mark worker_acknowledged without a persisted current "
                "execution id (use mark_worker_acknowledged)")
    if old == WORKER_ACKNOWLEDGED and new_state != WORKER_ACKNOWLEDGED:
        raise RuntimeError(
            "refusing to move a worker_acknowledged submission out of "
            "completion (PRES-008: the handoff is final once acked)")
    doc["state"] = new_state
    for key, value in fields.items():
        if value is None:
            doc.pop(key, None)
        else:
            doc[key] = value
    history = doc.setdefault("history", [])
    if isinstance(history, list):
        history.append({"at": _iso(_now()), "from": old, "to": new_state,
                        "why": str(why or "")[:300]})
    return save(run_dir, session_id, doc)


# --- liveness / execution identity ------------------------------------------

def _read_run_state(run_dir) -> Dict[str, Any]:
    """state.json's engine_pid/job_id, else the .engine.pid sidecar — the same
    two surfaces launcher._read_engine_pid reads, reimplemented locally so the
    bridge never needs the scripts package to answer "is a worker alive"."""
    out: Dict[str, Any] = {"pid": None, "job_id": ""}
    run_dir = Path(run_dir)
    state_path_ = run_dir / "state.json"
    if state_path_.is_file():
        try:
            st = json.loads(state_path_.read_text(encoding="utf-8"))
            if isinstance(st, dict):
                pid = st.get("engine_pid")
                out["pid"] = pid if isinstance(pid, int) and pid > 0 else None
                out["job_id"] = str(st.get("job_id") or "")
                if out["pid"] is not None:
                    return out
        except (OSError, ValueError):
            pass
    sidecar = run_dir / ".engine.pid"
    if sidecar.is_file():
        try:
            pid = int(sidecar.read_text(encoding="utf-8").strip())
            if pid > 0:
                out["pid"] = pid
        except (OSError, ValueError):
            pass
    return out


def pid_is_alive(pid: Any) -> bool:
    """os.kill(pid, 0) existence check — signal 0 is never delivered."""
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def engine_alive(run_dir) -> bool:
    """A live worker exists for this run dir (pid recorded and alive)."""
    return pid_is_alive(_read_run_state(run_dir).get("pid"))


def execution_id_of(run_dir) -> str:
    """The run's CURRENT execution identity: the engine's own job_id when a
    state.json names one, else 'engine-pid:<pid>' from the sidecar, else ''.
    A completion ack must carry a non-empty value from THIS function (or the
    lease-minted id of the dispatch that started the worker) — an empty
    execution id can never complete a submission."""
    info = _read_run_state(run_dir)
    if info.get("job_id"):
        return str(info["job_id"])
    pid = info.get("pid")
    if isinstance(pid, int) and pid > 0:
        return f"engine-pid:{pid}"
    return ""


def mint_execution_id(lease: Any) -> str:
    """A stable id for THIS dispatch attempt, derived from the lease the
    bridge held while dispatching (its acquired_at + pid + host). Two
    attempts never mint the same id; the id persisted with an ack is either
    this or the live engine's own job_id — always the CURRENT execution."""
    lease_doc = getattr(lease, "doc", None)
    if not isinstance(lease_doc, dict):
        lease_doc = lease if isinstance(lease, dict) else {}
    raw = "|".join(str(lease_doc.get(k) or "") for k in
                   ("acquired_at", "pid", "host"))
    return "exec-" + _sha256_hex(raw.encode("utf-8"))[:16]


# --- state predicates --------------------------------------------------------

def is_complete(doc: Optional[Dict[str, Any]]) -> bool:
    """Handoff complete == worker_acknowledged, nothing else. A held launch
    lease alone is NOT completion; a launching state is the crash window, not
    a completion."""
    return bool(doc) and doc.get("state") == WORKER_ACKNOWLEDGED


def is_blocked(doc: Optional[Dict[str, Any]]) -> bool:
    return bool(doc) and doc.get("state") == BLOCKED_ACTIONABLE


def due_for_retry(doc: Optional[Dict[str, Any]], now: Optional[datetime] = None) -> bool:
    """May this submission be driven again right now? Complete/blocked docs
    are never due; a scheduled next_retry_at in the future is not due yet
    (bounded backoff); anything else is due."""
    if not doc or is_complete(doc) or is_blocked(doc):
        return False
    next_at = _parse_iso(doc.get("next_retry_at"))
    if next_at is None:
        return True
    return (now or _now()) >= next_at


# --- mutations the bridge drives --------------------------------------------

def mark_launching(run_dir, session_id: str, doc: Dict[str, Any],
                   execution_id: str, why: str = "dispatch in flight") -> Dict[str, Any]:
    """Record the crash window: an execution id now exists for this attempt."""
    if not str(execution_id or "").strip():
        raise ValueError("launching requires a current execution id")
    return transition(run_dir, session_id, doc, LAUNCHING,
                      execution_id=str(execution_id), why=why)


def mark_worker_acknowledged(run_dir, session_id: str, doc: Dict[str, Any],
                             execution_id: str, engine_pid: Any = None,
                             note: str = "") -> Dict[str, Any]:
    """Complete the handoff — ONLY with a current execution id persisted.

    Idempotent: an already-completed submission returns unchanged (a live
    existing worker's acknowledgement is an idempotent success). Raises
    ValueError without an execution id — a bare rc must never complete a
    submission (the exact defect this module exists to close).
    """
    execution_id = str(execution_id or "").strip()
    if not execution_id:
        raise ValueError(
            "worker acknowledgement requires a current execution id — "
            "refusing to complete (PRES-008)")
    if doc.get("state") == WORKER_ACKNOWLEDGED:
        return doc
    ack: Dict[str, Any] = {"execution_id": execution_id, "at": _iso(_now())}
    if isinstance(engine_pid, int) and engine_pid > 0:
        ack["engine_pid"] = engine_pid
    if note:
        ack["note"] = str(note)[:300]
    doc["worker_ack"] = ack
    return transition(run_dir, session_id, doc, WORKER_ACKNOWLEDGED,
                      why=note or "live worker start acknowledged")


def mark_retry_pending(run_dir, session_id: str, doc: Dict[str, Any],
                       reason: str, *, failure_class: str = "unclassified",
                       backoff_base_s: float = DEFAULT_BACKOFF_BASE_S,
                       backoff_cap_s: float = DEFAULT_BACKOFF_CAP_S,
                       max_attempts: int = DEFAULT_MAX_RETRY_ATTEMPTS,
                       notify_thresholds=DEFAULT_NOTIFY_THRESHOLDS,
                       notifier: Optional[Notifier] = None,
                       now: Optional[datetime] = None) -> Dict[str, Any]:
    """Schedule the bounded retry after a refusal/deferral/failure.

    The submission lands in launch_pending (waiting for a launch) or
    failed_retryable (an attempt itself failed), with attempt count, the
    reason, and the next eligible retry time recorded. Crossing a notify
    threshold fires ONE operator notification per threshold. Exhausting the
    attempt budget blocks the submission (blocked_actionable, remediation
    recorded) instead of retrying forever.
    """
    now = now or _now()
    if doc.get("state") == WORKER_ACKNOWLEDGED:
        return doc
    if doc.get("state") == BLOCKED_ACTIONABLE:
        return doc
    attempt = int(doc.get("retry_attempt") or 0) + 1
    doc["retry_attempt"] = attempt
    doc["retry_last_reason"] = str(reason)[:400]
    doc["retry_last_class"] = str(failure_class)
    doc["retry_last_at"] = _iso(now)
    target = LAUNCH_PENDING if failure_class in ("dispatch_refused", "worker_deferred", "engine_died") \
        else FAILED_RETRYABLE
    if attempt > max_attempts:
        return mark_blocked(
            run_dir, session_id, doc,
            reason=f"retry budget exhausted ({max_attempts} attempts); "
                   f"last failure: {reason}",
            remediation=(
                "inspect the run's working/logs/engine-*.log and the reason "
                "recorded on this submission; fix the environment or the "
                "intake; then delete this submission state file ("
                f"{state_path(run_dir, session_id)}) or raise "
                "PRES008_MAX_RETRY_ATTEMPTS and re-run the bridge to re-arm "
                "the retry budget"),
            notify=True, notifier=notifier, now=now)
    delay = min(max(0.0, backoff_base_s) * (2 ** (attempt - 1)),
                max(0.0, backoff_cap_s))
    doc["next_retry_at"] = _iso(now + timedelta(seconds=delay))
    thresholds = tuple(t for t in (notify_thresholds or ())
                       if isinstance(t, int) and t > 0)
    if attempt in thresholds and notifier is not None:
        _fire_notifier(notifier, "launch_retry_threshold", doc.get("session_id") or session_id,
                       f"intake submission '{session_id}' has failed {attempt} "
                       f"launch attempt(s) ({failure_class}); next retry at "
                       f"{doc['next_retry_at']}; reason: {str(reason)[:200]}")
    return transition(run_dir, session_id, doc, target,
                      why=f"attempt {attempt} failed ({failure_class}): {str(reason)[:200]}",
                      retry_attempt=attempt, next_retry_at=doc["next_retry_at"])


def mark_blocked(run_dir, session_id: str, doc: Dict[str, Any], *,
                 reason: str, remediation: str,
                 notify: bool = False, notifier: Optional[Notifier] = None,
                 now: Optional[datetime] = None) -> Dict[str, Any]:
    """Permanent refusal / exhausted budget: stop retrying, record the
    remediation, tell the operator once. Other sessions keep progressing."""
    now = now or _now()
    if doc.get("state") == WORKER_ACKNOWLEDGED:
        return doc
    doc["blocked"] = {
        "reason": str(reason)[:600],
        "remediation": str(remediation)[:600],
        "at": _iso(now),
    }
    if notify and notifier is not None:
        _fire_notifier(notifier, "submission_blocked", session_id,
                       f"intake submission '{session_id}' is BLOCKED — no more "
                       f"automatic retries. Reason: {str(reason)[:200]} "
                       f"Remediation: {str(remediation)[:200]}")
    return transition(run_dir, session_id, doc, BLOCKED_ACTIONABLE,
                      why=f"blocked: {str(reason)[:200]}")


def quarantine_corrupt(run_dir, session_id: str, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Replace an unreadable state document with an explicit blocked_actionable
    one carrying the corrupt file's fingerprint — never silently reset."""
    now = now or _now()
    path = state_path(run_dir, session_id)
    fingerprint = ""
    try:
        raw = path.read_bytes()
        fingerprint = _sha256_hex(raw)[:16]
    except OSError:
        pass
    doc: Dict[str, Any] = {
        "version": LEDGER_VERSION,
        "session_id": session_id,
        "state": STAGED,
        "run_dir": str(run_dir),
        "created_at": _iso(now),
        "updated_at": _iso(now),
        "revision": 1,
        "history": [],
    }
    doc = save(run_dir, session_id, doc, now=now)
    return mark_blocked(
        run_dir, session_id, doc,
        reason=f"submission state file was unreadable/corrupt "
               f"(sha256-prefix {fingerprint or 'UNDETERMINED'})",
        remediation=(f"inspect {path} in the previous backups or logs; delete "
                     "it to re-drive the submission from staged"),
        now=now)


def _fire_notifier(notifier: Notifier, kind: str, submission_id: str,
                   message: str) -> None:
    """A notification failure must never fail the submission."""
    try:
        notifier(kind, submission_id, message)
    except Exception:  # noqa: BLE001 — notify is best-effort by contract
        pass


def describe(doc: Optional[Dict[str, Any]]) -> str:
    """One-line human summary for logs."""
    if not doc:
        return "no submission state"
    bits = [f"state={doc.get('state')}",
            f"task={doc.get('board_task_id') or '-'}",
            f"exec={doc.get('execution_id') or doc.get('worker_ack', {}).get('execution_id', '-') if isinstance(doc.get('worker_ack'), dict) else '-'}",
            f"attempt={doc.get('retry_attempt') or 0}"]
    if doc.get("next_retry_at"):
        bits.append(f"next={doc['next_retry_at']}")
    return " ".join(bits)


def list_submissions(run_dir) -> list:
    """Session ids with a state document under this run dir (observability)."""
    root = Path(run_dir) / "working" / "checkpoints"
    try:
        return sorted(p.name for p in root.glob(STATE_FILENAME))
    except OSError:
        return []
