#!/usr/bin/env python3
"""
rescue_cc_board.py — Rescue Rangers Command Center board caller (FAIL-SOFT).

Topic-4 FIX 4-C: put rescue TICKETS on the Command Center Kanban (kills R3 "no
ticket visibility on the Kanban" and R6 "no aging/SLA sweep"). A direct port of
the proven presentations/scripts/cc_board.py, re-shaped for a rescue ticket
(department_slug:"rescue-rangers"). The operator receiver/poller call this on:
  * ticket-open  -> POST /api/tasks/ingest (card lands in backlog)
  * answer-out   -> PATCH status=review  (moves to the review column)
  * RESOLVED     -> PATCH status=done    (moves to done)
  * blocked      -> PATCH status=blocked
The board columns then give the open-ticket + aging view for free.

NON-NEGOTIABLE DESIGN RULES (mirrored verbatim from cc_board.py)
  * FAIL-SOFT. A board outage, a missing token, an unreachable URL, an HTTP
    error, a timeout, or any other failure is CAUGHT, LOGGED to stderr, and the
    rescue flow CONTINUES. Boarding a ticket is a VIEW, never a gate — a stuck
    board must never block answering a distress call. Every public function
    returns a value (task_id / bool / list) and NEVER raises.

  * AUTH PARITY with the CC /api/tasks/ingest endpoint (byte-for-byte):
      - Authorization: Bearer <CC_API_TOKEN>            (middleware layer)
      - x-webhook-signature: HMAC-SHA256(WEBHOOK_SECRET, rawBody) hex (per-route)
    Both no-op server-side when the corresponding secret is unset (dev mode);
    we sign the EXACT bytes we send, so a configured secret matches.

  * STDLIB ONLY (urllib). Zero third-party deps.

  * CREDENTIALS FROM ENV, never hardcoded; absent base URL => fail-soft no-op.
      COMMAND_CENTER_URL / MISSION_CONTROL_URL   base URL (either accepted).
      CC_API_TOKEN / MC_API_TOKEN                bearer (optional).
      WEBHOOK_SECRET / CC_WEBHOOK_SECRET         HMAC secret (optional).
      CC_BOARD_TIMEOUT                           per-request timeout s (default 8).

REQUEST CONTRACT (matched to the live /api/tasks/ingest endpoint):
  CREATE  POST {base}/api/tasks/ingest
    {title, description, priority, source:"rescue-rangers", source_ref:ticket_id,
     department_slug:"rescue-rangers", persona:"Director of Rescue Rangers",
     external_session_id:ticket_id, idempotency_key:ticket_id}
  PATCH   PATCH {base}/api/tasks/{task_id}     {status, note?}
    status vocabulary is the authoritative CC TaskStatus enum: backlog | inbox |
    planning | in_progress | assigned | review | testing | blocked |
    pending_dispatch | done.
  ACTIVITY POST {base}/api/tasks/{task_id}/activities   {activity_type, message}

The ticket_id IS the idempotency key: a re-delivered escalation dedupes to the
SAME card server-side, so the two transports (receiver push + poller pull) never
create duplicate cards for one ticket.

LEDGER LINK: when a rescue_ledger.Ledger is passed, a successful ingest stamps
cc_task_id back onto the ticket row (stamp_cc_task) so the Ticket Clerk can join
the board card to the durable record, and aging_sweep() reads aging tickets
straight from that ledger.

MOVEMENT RECEIPT: every advance attempt + its HTTP status/body is appended to
<state_dir>/cc-board/<ticket_id>.json so a failed advance is VISIBLE on disk
(mirrors cc_board's working/checkpoints/cc-board.json). Recording is fail-soft.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import hmac
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# RR-024 receipt hardening (COMPATIBILITY-ONLY drill bridge).
# ---------------------------------------------------------------------------
# Base defects fixed here (SPEC RR-024, source _record_movement):
#   traversal ticket_id escaped cc-board/; one shared "<ticket>.json.tmp" temp
#   per ticket collided across writers; read-modify-write lost concurrent
#   events; "successful_advances" counted kind="activity" notes as state
#   advances; raw response bodies persisted unredacted; write failure only
#   logged. The canonical receipt record is the append-only operation/event
#   store (FLEET ledger rr_ticket_events keyed by tenant+operation; executor
#   rr_fix_receipt/rr_fix_events); this file keeps the drill export only.
RECEIPT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
RECEIPT_ID_MAX = 128
RECEIPT_DETAIL_MAX = 300
# A record is a STATE TRANSITION only when kind is one of these AND it names
# the observed resulting state; kind "activity" is an event with zero
# transition delta (activity is never a state transition).
RECEIPT_TRANSITION_KINDS = frozenset({"transition", "ingest", "status"})
_CREDENTIAL_SHAPE_RES = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"),
    re.compile(r"[A-Za-z0-9_-]{40,}"),
)


def validate_receipt_id(ticket_id) -> bool:
    """Bounded opaque ID check. False for traversal/absolute/oversized input."""
    if not isinstance(ticket_id, str):
        return False
    if not ticket_id or len(ticket_id) > RECEIPT_ID_MAX:
        return False
    return RECEIPT_ID_RE.match(ticket_id) is not None


def _receipt_identity(ticket_id: str) -> str:
    """Stable filename stem: the valid ID itself, else sha256(ticket_id)."""
    if validate_receipt_id(ticket_id):
        return ticket_id
    return "id_" + hashlib.sha256(ticket_id.encode("utf-8")).hexdigest()


def _scrub_detail(detail) -> str:
    text = re.sub(r"\s+", " ", str(detail or "")).strip()
    for rx in _CREDENTIAL_SHAPE_RES:
        text = rx.sub("[redacted-credential-shape]", text)
    return text[:RECEIPT_DETAIL_MAX]

_DEFAULT_TIMEOUT = 8
_DEPARTMENT_SLUG = "rescue-rangers"
_PERSONA = "Director of Rescue Rangers"

# Authoritative Command Center TaskStatus enum (same 10 values cc_board.py pins).
CC_TASK_STATUSES = frozenset({
    "backlog", "inbox", "planning", "in_progress", "assigned",
    "review", "testing", "blocked", "pending_dispatch", "done",
})

# Ledger status -> CC column mapping (FIX 4-C lifecycle->column contract).
LEDGER_TO_CC_STATUS = {
    "open": "backlog",
    "in_progress": "in_progress",
    "incomplete": "backlog",
    "answered": "review",
    "resolved": "done",
    "closed": "done",
    "blocked": "blocked",
}


# ---------------------------------------------------------------------------
# Config — read from the environment; absent base URL => board disabled no-op.
# ---------------------------------------------------------------------------
def board_config(env: Optional[dict] = None) -> Optional[dict]:
    """Resolve board config from the environment. Returns None (board disabled,
    a clean no-op) when neither COMMAND_CENTER_URL nor MISSION_CONTROL_URL is
    set. Never raises."""
    env = env if env is not None else os.environ
    base = (env.get("COMMAND_CENTER_URL") or env.get("MISSION_CONTROL_URL") or "").strip().rstrip("/")
    if not base:
        return None
    try:
        timeout = int(env.get("CC_BOARD_TIMEOUT", "") or _DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        timeout = _DEFAULT_TIMEOUT
    return {
        "base_url": base,
        "token": (env.get("CC_API_TOKEN") or env.get("MC_API_TOKEN") or "").strip(),
        "secret": (env.get("WEBHOOK_SECRET") or env.get("CC_WEBHOOK_SECRET") or "").strip(),
        "timeout": timeout,
    }


def _log(msg: str) -> None:
    print(f"[rescue_cc_board] {msg}", file=sys.stderr, flush=True)


def _sign(secret: str, raw_body: bytes) -> Optional[str]:
    """x-webhook-signature = HMAC-SHA256(WEBHOOK_SECRET, rawBody) hex — byte-for-
    byte parity with the CC route handler. None when no secret."""
    if not secret:
        return None
    return hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def _request(method: str, url: str, payload: dict, cfg: dict):
    """One signed JSON request. Returns (status_code, parsed_json_or_None).
    Raises only urllib/OS errors, which the public callers catch (fail-soft)."""
    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if cfg["token"]:
        headers["Authorization"] = f"Bearer {cfg['token']}"
    sig = _sign(cfg["secret"], raw_body)
    if sig is not None:
        headers["x-webhook-signature"] = sig
    req = urllib.request.Request(url, data=raw_body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=cfg["timeout"]) as resp:
            body = resp.read().decode("utf-8", "replace")
            status = resp.getcode()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace") if exc.fp else ""
        status = exc.code
    try:
        parsed = json.loads(body) if body else None
    except json.JSONDecodeError:
        parsed = None
    return status, parsed


# ---------------------------------------------------------------------------
# Pure payload builders (unit-testable without a live server).
# ---------------------------------------------------------------------------
def build_ingest_payload(ticket_id: str, client: str, problem: str,
                         priority: str = "high", box: str = "") -> dict:
    """The exact /api/tasks/ingest body for a rescue ticket. ticket_id is the
    idempotency key (dedupes a re-delivered escalation to one card). Pure/no I/O."""
    title = f"[{client or 'unknown'}] {(problem or 'rescue ticket').strip()[:80]}"
    box_line = f" (box: {box})" if box else ""
    payload = {
        "title": title,
        "description": (problem or "").strip() + box_line,
        "priority": priority,
        "source": "rescue-rangers",
        "source_ref": ticket_id,
        "department_slug": _DEPARTMENT_SLUG,
        "persona": _PERSONA,
        "external_session_id": ticket_id,
        "idempotency_key": ticket_id,
    }
    return payload


def cc_status_for(ledger_status: str) -> Optional[str]:
    """Translate a rescue_ledger status to a CC TaskStatus column value, or None
    when there is no mapping. The result is always inside CC_TASK_STATUSES."""
    v = LEDGER_TO_CC_STATUS.get(ledger_status)
    return v if v in CC_TASK_STATUSES else None


# ---------------------------------------------------------------------------
# Movement receipt — <state_dir>/cc-board/<ticket_id>.json.
# ---------------------------------------------------------------------------
def _receipts_dir(state_dir) -> Optional[Path]:
    if state_dir is None:
        return None
    d = Path(state_dir) / "cc-board"
    return d


def _now() -> str:
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%S%z") or time.strftime("%Y-%m-%dT%H:%M:%S")
    except Exception:  # noqa: BLE001
        return ""


def _receipt_path(state_dir, ticket_id: str) -> Optional[Path]:
    """Resolve the receipt file with containment enforced. Valid bounded
    opaque IDs map to <id>.json; anything else (traversal, absolute,
    oversized, bad characters) maps to the sha256 identity hash. The
    resolved path is always contained under cc-board/; None refuses
    empty/oversized input outright."""
    d = _receipts_dir(state_dir)
    if d is None:
        return None
    if not isinstance(ticket_id, str) or not ticket_id or len(ticket_id) > 1024:
        return None
    root = Path(os.path.realpath(d) if d.exists() else os.path.abspath(d))
    candidate = (root / (_receipt_identity(ticket_id) + ".json"))
    resolved = Path(os.path.realpath(candidate) if candidate.exists()
                    else os.path.abspath(candidate))
    if resolved != root and root not in resolved.parents:
        return None
    return resolved


def _persist_outstanding(state_dir, ticket_id: str, entry: dict,
                         write_error: str) -> None:
    """A disk failure becomes an outstanding OWNED intent (owner + due),
    never a bare log line. Retention is bounded only after reconciliation
    (see reconcile_outstanding)."""
    d = _receipts_dir(state_dir)
    if d is None:
        return
    try:
        out_dir = d / "outstanding"
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(out_dir, 0o700)
        except OSError:
            pass
        now = time.time()
        op_id = str(entry.get("operation_id") or "")
        intent = {
            "schema_version": 1,
            "intent_id": "out_" + hashlib.sha256(
                f"{_receipt_identity(ticket_id)}|{op_id}|{entry.get('kind')}".encode()
            ).hexdigest()[:32],
            "ticket_id": ticket_id,
            "identity": _receipt_identity(ticket_id),
            "operation_id": entry.get("operation_id"),
            "kind": entry.get("kind"),
            "observed": entry.get("observed"),
            "detail": _scrub_detail(entry.get("detail")),
            "owner": "rescue-rangers",
            "next_action_at": time.strftime(
                "%Y-%m-%dT%H:%M:%S%z", time.localtime(now + 3600)),
            "write_error": _scrub_detail(write_error),
            "reconciled": False,
            "ts": _now(),
        }
        fd, tmp_name = tempfile.mkstemp(prefix=".out-", suffix=".tmp",
                                        dir=str(out_dir))
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(intent, fh, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.chmod(tmp_name, 0o600)
            os.replace(tmp_name, str(out_dir / (intent["intent_id"] + ".json")))
            try:
                dfd = os.open(str(out_dir), os.O_RDONLY)
                try:
                    os.fsync(dfd)
                finally:
                    os.close(dfd)
            except OSError:
                pass
        finally:
            try:
                if os.path.exists(tmp_name):
                    os.unlink(tmp_name)
            except OSError:
                pass
    except OSError as exc:
        _log(f"outstanding intent persist failed ({exc}).")


def _stable_op_id(ticket_id: str, record: dict) -> str:
    """Idempotency key for one movement attempt. An explicit
    ``operation_id`` wins (retries replay it); otherwise derive a stable
    key from the attempt itself so a retried call dedupes instead of
    doubling the event log."""
    explicit = record.get("operation_id")
    if explicit:
        return str(explicit)
    core = json.dumps(
        {k: record.get(k) for k in (
            "kind", "endpoint", "target", "http_status", "task_id",
            "observed", "detail", "ok")},
        sort_keys=True, default=str)
    return "op_" + hashlib.sha256(
        f"{ticket_id}|{core}".encode("utf-8")).hexdigest()[:32]

def _acquire_lock(lock_path: Path, timeout_s: float = 15.0) -> Optional[int]:
    """Create the lock file with O_EXCL. Returns the fd or None on timeout."""
    deadline = time.time() + timeout_s
    while True:
        try:
            return os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except OSError as exc:
            if exc.errno not in (errno.EEXIST, errno.EACCES):
                raise
            if time.time() > deadline:
                return None
            time.sleep(0.025)

def _record_movement(state_dir, ticket_id: str, entry: dict) -> None:
    """Append one advance-attempt receipt for a ticket. Never raises; no-op when
    state_dir is None. RR-024: containment enforced, unique temp + fsync,
    process-safe (dedicated lock file + O_EXCL) serialization, op-ID dedupe,
    redacted detail, observed-state transition split, owned intent on disk
    error."""
    p = _receipt_path(state_dir, ticket_id)
    if p is None:
        _log("movement receipt refused — invalid ticket identity.")
        return
    if not isinstance(entry, dict):
        entry = {"detail": entry}
    record = {"ts": _now()}
    record.update(entry)
    # Operation-ID dedupe: a retry replays the recorded receipt (no 2nd event).
    # Transition split: only transition kinds carrying the OBSERVED resulting
    # state advance the counter; activity never does.
    record["operation_id"] = _stable_op_id(ticket_id, record)
    op_id = record["operation_id"]
    detail = _scrub_detail(record.get("detail"))
    try:
        d = p.parent
        d.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(d, 0o700)
        except OSError:
            pass
        lock_path = d / (p.stem + ".lock")
        lock_fd = _acquire_lock(lock_path)
        if lock_fd is None:
            raise OSError(errno.ETIMEDOUT, "receipt lock timeout")
        try:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX)
            except OSError:
                pass  # O_EXCL creation is the mutual exclusion; flock is belt-and-braces
            data: dict = {}
            if p.exists():
                try:
                    loaded = json.loads(p.read_text())
                    if isinstance(loaded, dict):
                        data = loaded
                except (json.JSONDecodeError, OSError):
                    data = {}
            movements = data.get("movements")
            if not isinstance(movements, list):
                movements = []
            deduped = any(isinstance(m, dict) and m.get("operation_id") == op_id
                          for m in movements)
            if not deduped:  # idempotent replay: recorded receipt, zero delta
                stored = dict(record)
                stored["detail"] = detail
                movements.append(stored)
            data["movements"] = movements
            data["transitions"] = sum(
                1 for m in movements
                if isinstance(m, dict) and m.get("kind") in RECEIPT_TRANSITION_KINDS
                and isinstance(m.get("observed"), dict) and m["observed"].get("to"))
            # Legacy key kept for readers: now equals the transition count
            # (activity no longer inflates it).
            data["successful_advances"] = data["transitions"]
            wfd, tmp_name = tempfile.mkstemp(prefix="." + p.stem + ".",
                                             suffix=".tmp", dir=str(d))
            try:
                with os.fdopen(wfd, "w") as out_fh:
                    json.dump(data, out_fh, indent=2)
                    out_fh.flush()
                    os.fsync(out_fh.fileno())
                os.chmod(tmp_name, 0o600)
                os.replace(tmp_name, p)
                try:
                    dfd = os.open(str(d), os.O_RDONLY)
                    try:
                        os.fsync(dfd)
                    finally:
                        os.close(dfd)
                except OSError:
                    pass
            finally:
                try:
                    if os.path.exists(tmp_name):
                        os.unlink(tmp_name)
                except OSError:
                    pass
        finally:
            try:
                os.close(lock_fd)
            except OSError:
                pass
            try:
                os.unlink(lock_path)
            except OSError:
                pass
    except OSError as exc:
        _persist_outstanding(state_dir, ticket_id, record,
                             f"{type(exc).__name__}: {exc}")


def _count_transitions(movements) -> int:
    """Transitions only: transition kinds carrying OBSERVED resulting state.
    Activity (kind activity, or transition kinds without observed.to) never
    counts — activity is not a state transition."""
    total = 0
    for m in movements or []:
        if not isinstance(m, dict):
            continue
        if m.get("kind") not in RECEIPT_TRANSITION_KINDS:
            continue
        observed = m.get("observed")
        if isinstance(observed, dict) and observed.get("to"):
            total += 1
    return total


def count_transitions(state_dir, ticket_id: str) -> int:
    """RR-024 transition count (observed-state advances only)."""
    p = _receipt_path(state_dir, ticket_id)
    if p is None or not p.exists():
        return 0
    try:
        data = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return 0
    if not isinstance(data, dict):
        return 0
    got = data.get("transitions")
    if isinstance(got, int):
        return got
    movements = data.get("movements")
    if isinstance(movements, list):
        return _count_transitions(movements)
    return 0


def count_successful_advances(state_dir, ticket_id: str) -> int:
    """Legacy alias: now equals the transition count (activity excluded)."""
    return count_transitions(state_dir, ticket_id)


def list_outstanding(state_dir) -> list:
    """Outstanding owned intents from disk failures (unreconciled evidence)."""
    d = _receipts_dir(state_dir)
    if d is None:
        return []
    out_dir = d / "outstanding"
    intents = []
    try:
        files = sorted(out_dir.glob("*.json"))
    except OSError:
        return []
    for f in files:
        try:
            intents.append(json.loads(f.read_text()))
        except (json.JSONDecodeError, OSError):
            continue
    return intents


def reconcile_outstanding(state_dir, intent_id: str) -> bool:
    """Mark one outstanding intent reconciled after replay into the canonical
    store. Retention purges reconciled intents only (see
    purge_reconciled_outstanding)."""
    d = _receipts_dir(state_dir)
    if d is None:
        return False
    if not validate_receipt_id(intent_id):
        return False
    p = d / "outstanding" / (intent_id + ".json")
    try:
        data = json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(data, dict):
        return False
    data["reconciled"] = True
    data["reconciled_at"] = _now()
    try:
        p.write_text(json.dumps(data, indent=2))
        return True
    except OSError as exc:
        _log(f"outstanding reconcile failed ({exc}).")
        return False


def purge_reconciled_outstanding(state_dir, older_than_seconds: int = 604800) -> dict:
    """Bound retention: remove ONLY reconciled intents older than the bound.
    Unreconciled evidence is never purged (returned in refused)."""
    d = _receipts_dir(state_dir)
    if d is None:
        return {"ok": True, "purged": [], "refused": []}
    import datetime as _dt
    cutoff = time.time() - max(0, int(older_than_seconds))
    purged, refused = [], []
    for intent in list_outstanding(state_dir):
        iid = intent.get("intent_id", "")
        ts = intent.get("ts", "")
        try:
            age = _dt.datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S").timestamp()
        except (ValueError, TypeError):
            age = time.time()
        if intent.get("reconciled") is True and age < cutoff:
            try:
                (d / "outstanding" / (iid + ".json")).unlink()
                purged.append(iid)
            except OSError:
                refused.append(iid)
        else:
            refused.append(iid)
    return {"ok": True, "purged": purged, "refused": refused}


# ---------------------------------------------------------------------------
# CREATE — POST /api/tasks/ingest (idempotent on ticket_id server-side).
# ---------------------------------------------------------------------------
def ingest_ticket(ticket_id: str, client: str, problem: str, *,
                  priority: str = "high", box: str = "", state_dir=None,
                  ledger=None, env: Optional[dict] = None) -> Optional[str]:
    """Land a rescue ticket on the CC board as ONE card. Returns the task_id on
    success else None. FAIL-SOFT — a None return never blocks the rescue flow.
    When `ledger` is a rescue_ledger.Ledger, the returned task_id is stamped back
    onto the ticket row (stamp_cc_task)."""
    if not ticket_id:
        return None
    cfg = board_config(env)
    if cfg is None:
        _log("COMMAND_CENTER_URL/MISSION_CONTROL_URL unset — CC board disabled "
             "(no-op); ticket handled ungrouped.")
        _record_movement(state_dir, ticket_id, {
            "kind": "ingest", "endpoint": "POST /api/tasks/ingest",
            "http_status": None, "ok": False, "detail": "board disabled"})
        return None

    payload = build_ingest_payload(ticket_id, client, problem, priority, box)
    url = f"{cfg['base_url']}/api/tasks/ingest"
    try:
        status, body = _request("POST", url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"ingest POST failed ({type(exc).__name__}: {exc}); ticket handled ungrouped.")
        _record_movement(state_dir, ticket_id, {
            "kind": "ingest", "endpoint": "POST /api/tasks/ingest",
            "http_status": None, "ok": False, "detail": f"{type(exc).__name__}: {exc}"})
        return None

    if status in (200, 201) and isinstance(body, dict) and body.get("task_id"):
        task_id = str(body["task_id"])
        deduped = body.get("deduped", False)
        _log(f"card {'deduped (reused)' if deduped else 'created'}: "
             f"task_id={task_id} ticket_id={ticket_id}")
        _record_movement(state_dir, ticket_id, {
            "kind": "ingest", "endpoint": "POST /api/tasks/ingest",
            "http_status": status, "ok": True, "task_id": task_id, "deduped": deduped,
            "observed": {"from": None, "to": "backlog"},
            "operation_id": f"ingest|{ticket_id}|{task_id}"})
        if ledger is not None:
            try:
                ledger.stamp_cc_task(ticket_id, task_id)
            except Exception as exc:  # noqa: BLE001 — board link is best-effort
                _log(f"stamp_cc_task failed ({exc}) — non-fatal.")
        return task_id

    _log(f"ingest POST non-OK (HTTP {status}): {body}; ticket handled ungrouped.")
    _record_movement(state_dir, ticket_id, {
        "kind": "ingest", "endpoint": "POST /api/tasks/ingest",
        "http_status": status, "ok": False, "detail": _scrub_detail(body)})
    return None


# ---------------------------------------------------------------------------
# PATCH — advance the card as the ticket moves through its lifecycle.
# ---------------------------------------------------------------------------
def patch_status(task_id: str, status: str, *, ticket_id: str = "", note: str = "",
                 state_dir=None, env: Optional[dict] = None) -> bool:
    """PATCH the CC card to a CC TaskStatus. Rejects a status outside the
    authoritative enum offline (before any network call). FAIL-SOFT: returns
    False, never raises."""
    endpoint = "PATCH /api/tasks/{id}"
    if status not in CC_TASK_STATUSES:
        _log(f"patch_status refused — '{status}' not in the CC TaskStatus enum.")
        _record_movement(state_dir, ticket_id or task_id, {
            "kind": "status", "target": status, "endpoint": endpoint,
            "http_status": None, "ok": False, "detail": "status not in enum"})
        return False
    cfg = board_config(env)
    if cfg is None:
        _record_movement(state_dir, ticket_id or task_id, {
            "kind": "status", "target": status, "endpoint": endpoint,
            "http_status": None, "ok": False, "detail": "board disabled"})
        return False
    if not task_id:
        _log("patch_status skipped — task_id missing.")
        _record_movement(state_dir, ticket_id or "unknown", {
            "kind": "status", "target": status, "endpoint": endpoint,
            "http_status": None, "ok": False, "detail": "task_id missing"})
        return False

    payload: dict = {"status": status}
    if note:
        payload["note"] = note
    url = f"{cfg['base_url']}/api/tasks/{task_id}"
    try:
        st, body = _request("PATCH", url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _log(f"patch_status ->{status} failed ({type(exc).__name__}: {exc}).")
        _record_movement(state_dir, ticket_id or task_id, {
            "kind": "status", "target": status, "endpoint": endpoint,
            "http_status": None, "ok": False, "detail": f"{type(exc).__name__}: {exc}"})
        return False

    ok = st == 200
    _record_movement(state_dir, ticket_id or task_id, {
        "kind": "status", "target": status, "endpoint": endpoint,
        "http_status": st, "ok": ok, "detail": "OK" if ok else _scrub_detail(body),
        **({"observed": {"from": None, "to": status},
            "operation_id": f"status|{ticket_id or task_id}|{status}|{st}"} if ok else {})})
    if ok:
        _log(f"patch_status ->{status} OK (task_id={task_id}).")
    else:
        _log(f"patch_status ->{status} non-OK (HTTP {st}): {body}.")
    return ok


def mark_answered(task_id: str, *, ticket_id: str = "", note: str = "",
                  state_dir=None, env: Optional[dict] = None) -> bool:
    """Answer produced -> move the card to the review column."""
    return patch_status(task_id, "review", ticket_id=ticket_id,
                        note=note or "rescue answer posted", state_dir=state_dir, env=env)


def mark_resolved(task_id: str, *, ticket_id: str = "", note: str = "",
                  state_dir=None, env: Optional[dict] = None) -> bool:
    """RESOLVED confirmed -> close the card to done."""
    return patch_status(task_id, "done", ticket_id=ticket_id,
                        note=note or "rescue ticket resolved", state_dir=state_dir, env=env)


def post_activity(task_id: str, message: str, *, ticket_id: str = "",
                  activity_type: str = "updated", state_dir=None,
                  env: Optional[dict] = None) -> bool:
    """Mid-lifecycle progress note (e.g. tier assigned, fix DRY-RUN passed).
    FAIL-SOFT: returns False, never raises."""
    endpoint = "POST /api/tasks/{id}/activities"
    cfg = board_config(env)
    if cfg is None:
        _record_movement(state_dir, ticket_id or task_id, {
            "kind": "activity", "target": activity_type, "endpoint": endpoint,
            "http_status": None, "ok": False, "detail": "board disabled"})
        return False
    if not task_id:
        _record_movement(state_dir, ticket_id or "unknown", {
            "kind": "activity", "target": activity_type, "endpoint": endpoint,
            "http_status": None, "ok": False, "detail": "task_id missing"})
        return False
    payload = {"activity_type": activity_type, "message": message or "(rescue update)"}
    url = f"{cfg['base_url']}/api/tasks/{task_id}/activities"
    try:
        st, body = _request("POST", url, payload, cfg)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        _record_movement(state_dir, ticket_id or task_id, {
            "kind": "activity", "target": activity_type, "endpoint": endpoint,
            "http_status": None, "ok": False, "detail": f"{type(exc).__name__}: {exc}"})
        return False
    ok = st in (200, 201)
    _record_movement(state_dir, ticket_id or task_id, {
        "kind": "activity", "target": activity_type, "endpoint": endpoint,
        "http_status": st, "ok": ok, "detail": "OK" if ok else _scrub_detail(body)})
    return ok


# ---------------------------------------------------------------------------
# AGING SWEEP — the durable view the CC/cron uses to page on aging tickets.
# ---------------------------------------------------------------------------
def aging_sweep(ledger, older_than_minutes: int,
                statuses=("open", "in_progress", "answered", "blocked")):
    """Return the tickets in `statuses` older than the cutoff, read straight from
    the durable ledger (kills R6). Pure read — never raises, never pages. The
    operator aging cron decides whether to page the Fixer topic (deduped). Returns
    [] on any error / empty ledger."""
    try:
        return ledger.aging(older_than_minutes, statuses=statuses)
    except Exception as exc:  # noqa: BLE001 — a view must never raise
        _log(f"aging_sweep read failed ({exc}) — returning empty.")
        return []


# ---------------------------------------------------------------------------
# self-test (deterministic, no network — exercises the OFFLINE fail-soft paths
# and the pure payload/status builders; a live POST is out of scope here).
# ---------------------------------------------------------------------------
def self_test():
    import tempfile
    print("[rescue_cc_board] self-test: payload build, enum guard, fail-soft no-op, "
          "receipts, aging sweep")

    # pure payload builder
    p = build_ingest_payload("tkt-9", "acme", "gateway down at 3am", box="acme-mac")
    assert p["department_slug"] == "rescue-rangers"
    assert p["persona"] == "Director of Rescue Rangers"
    assert p["idempotency_key"] == "tkt-9" and p["source_ref"] == "tkt-9"
    assert p["title"].startswith("[acme]") and "gateway down" in p["title"]
    print("  payload case: PASS (rescue-rangers dept, ticket_id is idempotency key)")

    # ledger-status -> CC-column mapping stays inside the enum
    assert cc_status_for("answered") == "review"
    assert cc_status_for("resolved") == "done"
    assert cc_status_for("open") == "backlog"
    assert cc_status_for("bogus") is None
    for v in LEDGER_TO_CC_STATUS.values():
        assert v in CC_TASK_STATUSES
    print("  status-map case: PASS (every mapped status is a real CC column)")

    # signature parity: signing is deterministic + matches a hand HMAC
    raw = json.dumps({"a": 1}, separators=(",", ":")).encode()
    assert _sign("", raw) is None
    assert _sign("s3cr3t", raw) == hmac.new(b"s3cr3t", raw, hashlib.sha256).hexdigest()
    print("  signature case: PASS (HMAC parity; empty secret => no signature)")

    # board disabled => every call is a clean fail-soft no-op (no network)
    empty_env: dict = {}
    with tempfile.TemporaryDirectory() as td:
        sd = Path(td) / "rescue"
        assert ingest_ticket("tkt-9", "acme", "x", state_dir=sd, env=empty_env) is None
        assert mark_answered("cc-1", ticket_id="tkt-9", state_dir=sd, env=empty_env) is False
        assert mark_resolved("cc-1", ticket_id="tkt-9", state_dir=sd, env=empty_env) is False
        assert post_activity("cc-1", "note", ticket_id="tkt-9", state_dir=sd, env=empty_env) is False
        # a movement receipt was still written (visible on disk), all ok:false
        receipt = Path(td) / "rescue" / "cc-board" / "tkt-9.json"
        assert receipt.is_file()
        assert count_successful_advances(sd, "tkt-9") == 0
        print("  fail-soft case: PASS (disabled board no-ops + records receipts)")

        # enum guard: a bogus status is refused offline, before any network call
        assert patch_status("cc-1", "delivered", ticket_id="tkt-9",
                           state_dir=sd, env={"COMMAND_CENTER_URL": "http://x"}) is False
        print("  enum-guard case: PASS ('delivered' rejected — not a CC status)")

        # aging sweep reads the retired writer under the explicit offline-drill
        # opt-out (RR-006: isolated tempdir fixture only, never ticket state).
        # RR-030 guard retained: missing ledger FAILS (no blanket-SKIP hole).
        _ledger_py = Path(__file__).with_name("rescue_ledger.py")
        if not _ledger_py.is_file():
            print(f"  aging-sweep case: FAIL (rescue_ledger.py not found next to "
                  f"rescue_cc_board.py at {_ledger_py} — the ledger is required, "
                  f"not optional)")
            print("[rescue_cc_board] self-test: FAIL")
            return 1
        import os as _os
        _prev_drill = _os.environ.get("RR_LEDGER_DRILL")
        _os.environ["RR_LEDGER_DRILL"] = "1"
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(
                "rescue_ledger", str(_ledger_py))
            rl = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(rl)
            from datetime import datetime as _dt, timedelta as _td, timezone as _tz
            led = rl.Ledger(sd)
            old = (_dt.now(_tz.utc) - _td(hours=5)).replace(microsecond=0).isoformat()
            led.open_ticket("tkt-old", client="beta", problem="stuck", ts_open=old)
            led.open_ticket("tkt-new", client="beta", problem="fresh")
            # RR-030: exercise the SWEEP directly — assert fails loudly, no SKIP.
            aged = {t["ticket_id"] for t in aging_sweep(led, 120)}
            assert "tkt-old" in aged and "tkt-new" not in aged, (
                f"aging_sweep returned {sorted(aged)}; expected tkt-old aged in, "
                f"tkt-new excluded — the sweep is broken")
            led.close()
            print("  aging-sweep case: PASS (durable ledger drives the SLA view)")
        finally:
            if _prev_drill is None:
                _os.environ.pop("RR_LEDGER_DRILL", None)
            else:
                _os.environ["RR_LEDGER_DRILL"] = _prev_drill

    print("[rescue_cc_board] self-test: PASS")
    return 0


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Rescue Rangers CC board caller (fail-soft).")
    ap.add_argument("--self-test", action="store_true", help="run the offline self-test")
    args = ap.parse_args()
    if args.self_test:
        sys.exit(self_test())
    ap.print_help()
    sys.exit(0)
