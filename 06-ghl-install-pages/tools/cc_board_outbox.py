#!/usr/bin/env python3
"""cc_board_outbox.py — WF20 durable producer outbox for Command Center board delivery.

WHY THIS EXISTS
---------------
Skill 6/44/35/83 execution must never depend on the board being up. The producer
writes ONE durable event BEFORE it attempts delivery. A timeout, 5xx, or an old
Command Center version leaves the event queued with bounded backoff and the
business work continues. Retrying re-sends the EVENT (same idempotency key, same
redacted bytes) and never re-runs the business operation, so a board retry can
never repeat a GHL mutation.

CONTRACT (frozen as checkpoint WF20-CP01)
------------------------------------------
Event schema: ``cc-board-delivery-event/1``. The producer/consumer request
contract fixture lives at
``06-ghl-install-pages/tests/fixtures/cc_board_delivery_contract.v1.json`` and is
consumed by the Command Center receipt backend (WF18) and the Projects mapping
(WF33) through the owner-mediated integration lanes.

REDACTION
---------
The request is redacted BEFORE the durable write: secret-named keys are masked,
then ``ghl_evidence`` secret SHAPES are scrubbed. ``request_hash`` is computed
over the canonical intent BEFORE redaction, so content matching survives
redaction (Document 1 s5.5).

STDLIB ONLY. No network. Never raises on a board problem; callers treat a
queued event as "board not reached", never as success.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import ghl_evidence  # noqa: E402  (share the one evidence scrubber)

EVENT_SCHEMA = "cc-board-delivery-event/1"
CONTRACT_SCHEMA = "cc-board-delivery-contract/1"
BOARD_ENDPOINT = "/api/tasks/ingest"

# Engine-produced cards carry this source; the legacy producer sources stay
# valid so old callers keep working. A new source is a contract change.
ENGINE_SOURCE = "ghl-hybrid"
ALLOWED_SOURCES = (
    "ghl-hybrid",
    "funnel",
    "survey",
    "web-development",
    "marketing",
    "copy",
)

DOMAINS = ("board", "projects_sync")
_DOMAIN_ACTION_PREFIX = {"board": "board.", "projects_sync": "projects."}

STATUS_PENDING = "pending"
STATUS_IN_FLIGHT = "in_flight"
STATUS_ACKED = "acked"
STATUS_DEAD_LETTER = "dead_letter"
ALL_STATUSES = (STATUS_PENDING, STATUS_IN_FLIGHT, STATUS_ACKED, STATUS_DEAD_LETTER)

DEFAULT_BACKOFF_BASE_S = 1.0
DEFAULT_BACKOFF_CAP_S = 64.0
DEFAULT_LEASE_S = 300.0

_SECRET_KEY_RE = None
_TEXT_ASSIGN_RE = None


class OutboxError(ValueError):
    """Invalid input or an illegal transition. Fail closed; never a silent pass."""


def _secret_key_re():
    global _SECRET_KEY_RE
    if _SECRET_KEY_RE is None:
        import re
        _SECRET_KEY_RE = re.compile(
            r"(?i)(token|secret|password|passwd|api[_-]?key|authorization|cookie|private[_-]?key)"
        )
    return _SECRET_KEY_RE


def _rfc3339(ts: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def _require_str(value: Any, name: str, *, allow_none: bool = False) -> Optional[str]:
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not value.strip():
        raise OutboxError(f"bad_input: {name} must be a non-empty string")
    return value


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def request_hash(request: dict) -> str:
    """Hash the canonical intent BEFORE redaction."""
    return "sha256:" + hashlib.sha256(_canonical(request).encode("utf-8")).hexdigest()


def _redact_keys(obj: Any) -> Tuple[Any, int]:
    if isinstance(obj, dict):
        out: Dict[str, Any] = {}
        count = 0
        for key, value in obj.items():
            if isinstance(key, str) and _secret_key_re().search(key):
                out[key] = ghl_evidence.REDACTED
                count += 1
                continue
            scrubbed, n = _redact_keys(value)
            out[key] = scrubbed
            count += n
        return out, count
    if isinstance(obj, list):
        out_list = []
        count = 0
        for value in obj:
            scrubbed, n = _redact_keys(value)
            out_list.append(scrubbed)
            count += n
        return out_list, count
    return obj, 0


def _text_assign_re():
    global _TEXT_ASSIGN_RE
    if _TEXT_ASSIGN_RE is None:
        import re
        # Secret-NAMED assignments inside free text ("api_token=...",
        # "client_secret: ..."). The generic scrubber misses names like
        # "api_token" because the underscore is a word character, so the
        # "token" alternative has no word boundary there.
        _TEXT_ASSIGN_RE = re.compile(
            r"(?i)\b([A-Za-z0-9_-]*(?:token|secret|password|passwd|api[_-]?key"
            r"|authorization|cookie)[A-Za-z0-9_-]*)(\s*[:=]\s*)"
            r"(\"[^\"]{4,}\"|'[^']{4,}'|[^\s,;\"'}\]]{4,})"
        )
    return _TEXT_ASSIGN_RE


def _redact_text_values(obj: Any) -> Tuple[Any, int]:
    if isinstance(obj, str):
        out, n = _text_assign_re().subn(
            lambda m: f"{m.group(1)}{m.group(2)}{ghl_evidence.REDACTED}", obj)
        return out, n
    if isinstance(obj, dict):
        out, count = {}, 0
        for key, value in obj.items():
            scrubbed, n = _redact_text_values(value)
            out[key] = scrubbed
            count += n
        return out, count
    if isinstance(obj, list):
        out_list, count = [], 0
        for value in obj:
            scrubbed, n = _redact_text_values(value)
            out_list.append(scrubbed)
            count += n
        return out_list, count
    return obj, 0


def redact_request(request: dict, *, secret_values=None) -> Tuple[dict, int]:
    """Return (redacted_request, redaction_count). Never mutates the input."""
    key_redacted, key_count = _redact_keys(request)
    text_redacted, text_count = _redact_text_values(key_redacted)
    shape_redacted, shape_count = ghl_evidence.scrub_obj(text_redacted, secret_values)
    return shape_redacted, key_count + text_count + shape_count


def validate_event(event: dict) -> None:
    """Shape-level, fail-closed validation of one event (producer side)."""
    if not isinstance(event, dict):
        raise OutboxError("bad_input: event must be a dict")
    for name in ("idempotency_key", "logical_action", "family", "run_id",
                 "operation_key", "source", "request_hash", "created_at"):
        _require_str(event.get(name), name)
    if event.get("schema") != EVENT_SCHEMA:
        raise OutboxError(f"bad_input: schema must be {EVENT_SCHEMA!r}")
    domain = event.get("domain")
    if domain not in DOMAINS:
        raise OutboxError(f"bad_input: domain {domain!r} not in {DOMAINS}")
    prefix = _DOMAIN_ACTION_PREFIX[domain]
    if not event["logical_action"].startswith(prefix):
        raise OutboxError(
            f"bad_input: {domain} logical_action must start {prefix!r}"
        )
    if event["source"] not in ALLOWED_SOURCES:
        raise OutboxError(
            f"bad_input: source {event['source']!r} not in {ALLOWED_SOURCES}"
        )
    if event.get("parent_task_id") is not None:
        _require_str(event.get("parent_task_id"), "parent_task_id")
    if not isinstance(event.get("request"), dict) or not event["request"]:
        raise OutboxError("bad_input: request must be a non-empty dict")
    if not str(event.get("request_hash", "")).startswith("sha256:"):
        raise OutboxError("bad_input: request_hash must be sha256:<hex>")


def build_event(
    *,
    idempotency_key: str,
    request: dict,
    run_id: str,
    operation_key: str,
    family: str,
    source: str = ENGINE_SOURCE,
    domain: str = "board",
    logical_action: str = "board.task.ingest",
    parent_task_id: Optional[str] = None,
    evidence_root: Optional[str] = None,
    secret_values=None,
    now: Optional[float] = None,
) -> dict:
    """Build (not store) one contract event; the request is redacted here."""
    ts = time.time() if now is None else float(now)
    redacted, redactions = redact_request(request, secret_values=secret_values)
    event = {
        "schema": EVENT_SCHEMA,
        "event_id": "bde_" + uuid.uuid4().hex,
        "idempotency_key": idempotency_key,
        "domain": domain,
        "logical_action": logical_action,
        "family": family,
        "run_id": run_id,
        "operation_key": operation_key,
        "source": source,
        "parent_task_id": parent_task_id,
        "request": redacted,
        "request_hash": request_hash(request),
        "redactions": redactions,
        "evidence_root": evidence_root,
        "status": STATUS_PENDING,
        "attempts": 0,
        "next_attempt_at": ts,
        "last_error": None,
        "ack_task_id": None,
        "created_at": _rfc3339(ts),
        "updated_at": _rfc3339(ts),
    }
    event["idempotency_key"] = _require_str(idempotency_key, "idempotency_key")
    event["run_id"] = _require_str(run_id, "run_id")
    event["operation_key"] = _require_str(operation_key, "operation_key")
    event["family"] = _require_str(family, "family")
    validate_event(event)
    return event


_SCHEMA = """
CREATE TABLE IF NOT EXISTS board_delivery_events (
    event_id        TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    domain          TEXT NOT NULL,
    logical_action  TEXT NOT NULL,
    family          TEXT NOT NULL,
    run_id          TEXT NOT NULL,
    operation_key   TEXT NOT NULL,
    source          TEXT NOT NULL,
    parent_task_id  TEXT,
    request_json    TEXT NOT NULL,
    request_hash    TEXT NOT NULL,
    evidence_root   TEXT,
    status          TEXT NOT NULL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at REAL NOT NULL DEFAULT 0,
    last_error      TEXT,
    ack_task_id     TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS board_parents (
    run_id         TEXT PRIMARY KEY,
    parent_task_id TEXT NOT NULL,
    created_at     TEXT NOT NULL
);
"""


class BoardOutbox:
    """Durable, idempotent, bounded-backoff producer outbox over SQLite."""

    def __init__(self, path: str, *, backoff_base_s: float = DEFAULT_BACKOFF_BASE_S,
                 backoff_cap_s: float = DEFAULT_BACKOFF_CAP_S,
                 lease_s: float = DEFAULT_LEASE_S) -> None:
        _require_str(path, "path")
        self.path = str(path)
        parent = os.path.dirname(os.path.abspath(self.path))
        ghl_evidence.ensure_private_dir(parent)
        self.backoff_base_s = float(backoff_base_s)
        self.backoff_cap_s = float(backoff_cap_s)
        self.lease_s = float(lease_s)
        self._db = sqlite3.connect(self.path)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        with self._tx() as cur:
            cur.executescript(_SCHEMA)

    # ── plumbing ──────────────────────────────────────────────────────────
    def close(self) -> None:
        self._db.close()

    def _tx(self):
        return _Tx(self._db)

    def _row(self, cur, key: str) -> Dict[str, Any]:
        row = cur.execute(
            "SELECT * FROM board_delivery_events WHERE idempotency_key = ?", (key,)
        ).fetchone()
        if row is None:
            raise OutboxError(f"unknown idempotency_key {key!r}")
        return dict(row)

    @staticmethod
    def _project(row: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(row)
        out["request"] = json.loads(out.pop("request_json"))
        return out

    # ── append (durable before delivery, idempotent key) ──────────────────
    def enqueue(self, event: dict, *, now: Optional[float] = None) -> Tuple[dict, bool]:
        """Store ONE event before delivery. Same idempotency key = same event,
        created=False, nothing written (a retry never mints a new effect)."""
        validate_event(event)
        ts = time.time() if now is None else float(now)
        with self._tx() as cur:
            existing = cur.execute(
                "SELECT * FROM board_delivery_events WHERE idempotency_key = ?",
                (event["idempotency_key"],),
            ).fetchone()
            if existing is not None:
                return self._project(dict(existing)), False
            cur.execute(
                "INSERT INTO board_delivery_events (event_id, idempotency_key, domain,"
                " logical_action, family, run_id, operation_key, source, parent_task_id,"
                " request_json, request_hash, evidence_root, status, attempts,"
                " next_attempt_at, last_error, ack_task_id, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,0,?,NULL,NULL,?,?)",
                (event["event_id"], event["idempotency_key"], event["domain"],
                 event["logical_action"], event["family"], event["run_id"],
                 event["operation_key"], event["source"], event.get("parent_task_id"),
                 json.dumps(event["request"], sort_keys=True, separators=(",", ":")),
                 event["request_hash"], event.get("evidence_root"), STATUS_PENDING,
                 ts, event["created_at"], _rfc3339(ts)),
            )
            return self._project(self._row(cur, event["idempotency_key"])), True

    # ── reads ─────────────────────────────────────────────────────────────
    def event(self, idempotency_key: str) -> dict:
        return self._project(self._row(self._db.cursor(), idempotency_key))

    def receipt(self, idempotency_key: str) -> dict:
        row = self._row(self._db.cursor(), idempotency_key)
        return {
            "idempotency_key": row["idempotency_key"],
            "event_id": row["event_id"],
            "status": row["status"],
            "attempts": int(row["attempts"]),
            "ack_task_id": row["ack_task_id"],
            "last_error": row["last_error"],
            "updated_at": row["updated_at"],
        }

    def status_of(self, idempotency_key: str) -> str:
        return self._row(self._db.cursor(), idempotency_key)["status"]

    def due(self, now: Optional[float] = None) -> List[dict]:
        """Requeue lease-expired in-flight events (unknown outcome, SAME identity)
        then return pending events whose backoff has elapsed."""
        ts = time.time() if now is None else float(now)
        with self._tx() as cur:
            cur.execute(
                "UPDATE board_delivery_events SET status = ?, last_error = ?,"
                " updated_at = ? WHERE status = ? AND next_attempt_at <= ?",
                (STATUS_PENDING,
                 "lease_expired_unknown_outcome: requeued under the same idempotency key",
                 _rfc3339(ts), STATUS_IN_FLIGHT, ts - self.lease_s),
            )
        rows = self._db.execute(
            "SELECT * FROM board_delivery_events WHERE status = ? AND next_attempt_at <= ?"
            " ORDER BY next_attempt_at, created_at",
            (STATUS_PENDING, ts),
        ).fetchall()
        return [self._project(dict(r)) for r in rows]

    def counts(self) -> Dict[str, int]:
        out = {s: 0 for s in ALL_STATUSES}
        for row in self._db.execute(
            "SELECT status, COUNT(*) AS n FROM board_delivery_events GROUP BY status"
        ).fetchall():
            out[row["status"]] = int(row["n"])
        out["total"] = sum(out[s] for s in ALL_STATUSES)
        return out

    def events(self) -> List[dict]:
        rows = self._db.execute(
            "SELECT * FROM board_delivery_events ORDER BY created_at"
        ).fetchall()
        return [self._project(dict(r)) for r in rows]

    # ── delivery lifecycle ────────────────────────────────────────────────
    def claim(self, idempotency_key: str, *, now: Optional[float] = None) -> dict:
        """pending -> in_flight. The outcome is uncertain until ack/fail."""
        ts = time.time() if now is None else float(now)
        with self._tx() as cur:
            row = self._row(cur, idempotency_key)
            if row["status"] != STATUS_PENDING:
                raise OutboxError(f"illegal claim from {row['status']!r}")
            cur.execute(
                "UPDATE board_delivery_events SET status = ?, updated_at = ?"
                " WHERE idempotency_key = ?",
                (STATUS_IN_FLIGHT, _rfc3339(ts), idempotency_key),
            )
            return self._project(self._row(cur, idempotency_key))

    def ack(self, idempotency_key: str, task_id: str, *,
            now: Optional[float] = None) -> dict:
        """Acknowledge delivery; repeated acknowledgment is harmless. A different
        task id for the same event is a contradiction, never silently accepted."""
        _require_str(task_id, "task_id")
        ts = time.time() if now is None else float(now)
        with self._tx() as cur:
            row = self._row(cur, idempotency_key)
            if row["status"] == STATUS_ACKED:
                if row["ack_task_id"] == task_id:
                    return self.receipt(idempotency_key)  # repeat: harmless
                raise OutboxError(
                    f"contradiction: event {idempotency_key!r} already acked as "
                    f"{row['ack_task_id']!r}, not {task_id!r}"
                )
            if row["status"] == STATUS_DEAD_LETTER:
                raise OutboxError("illegal ack from dead_letter")
            cur.execute(
                "UPDATE board_delivery_events SET status = ?, ack_task_id = ?,"
                " last_error = NULL, updated_at = ? WHERE idempotency_key = ?",
                (STATUS_ACKED, task_id, _rfc3339(ts), idempotency_key),
            )
            return self.receipt(idempotency_key)

    def fail(self, idempotency_key: str, error: str, *, retryable: bool = True,
             now: Optional[float] = None) -> dict:
        """in_flight -> pending with bounded exponential backoff (SAME identity),
        or -> dead_letter when the consumer deterministically refused the event."""
        _require_str(error, "error")
        ts = time.time() if now is None else float(now)
        with self._tx() as cur:
            row = self._row(cur, idempotency_key)
            if row["status"] != STATUS_IN_FLIGHT:
                raise OutboxError(f"illegal fail from {row['status']!r}")
            attempts = int(row["attempts"]) + 1
            if retryable:
                delay = min(self.backoff_base_s * (2 ** (attempts - 1)),
                            self.backoff_cap_s)
                cur.execute(
                    "UPDATE board_delivery_events SET status = ?, attempts = ?,"
                    " next_attempt_at = ?, last_error = ?, updated_at = ?"
                    " WHERE idempotency_key = ?",
                    (STATUS_PENDING, attempts, ts + delay, error, _rfc3339(ts),
                     idempotency_key),
                )
            else:
                cur.execute(
                    "UPDATE board_delivery_events SET status = ?, attempts = ?,"
                    " last_error = ?, updated_at = ? WHERE idempotency_key = ?",
                    (STATUS_DEAD_LETTER, attempts, error, _rfc3339(ts),
                     idempotency_key),
                )
            return self.receipt(idempotency_key)

    # ── parent reuse (existing parent is never re-created) ────────────────
    def record_parent(self, run_id: str, parent_task_id: str, *,
                      now: Optional[float] = None) -> str:
        _require_str(run_id, "run_id")
        _require_str(parent_task_id, "parent_task_id")
        ts = time.time() if now is None else float(now)
        with self._tx() as cur:
            row = cur.execute(
                "SELECT parent_task_id FROM board_parents WHERE run_id = ?", (run_id,)
            ).fetchone()
            if row is not None:
                if row["parent_task_id"] != parent_task_id:
                    raise OutboxError(
                        f"contradiction: run {run_id!r} already maps to parent "
                        f"{row['parent_task_id']!r}"
                    )
                return row["parent_task_id"]
            cur.execute(
                "INSERT INTO board_parents (run_id, parent_task_id, created_at)"
                " VALUES (?,?,?)",
                (run_id, parent_task_id, _rfc3339(ts)),
            )
            return parent_task_id

    def parent_for(self, run_id: str) -> Optional[str]:
        _require_str(run_id, "run_id")
        row = self._db.execute(
            "SELECT parent_task_id FROM board_parents WHERE run_id = ?", (run_id,)
        ).fetchone()
        return row["parent_task_id"] if row is not None else None


class _Tx:
    """BEGIN IMMEDIATE transaction; serializes concurrent appenders on one DB."""

    def __init__(self, db: sqlite3.Connection) -> None:
        self._db = db

    def __enter__(self) -> sqlite3.Cursor:
        self._cur = self._db.cursor()
        self._cur.execute("BEGIN IMMEDIATE")
        return self._cur

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self._db.commit()
        else:
            self._db.rollback()
        self._cur.close()


def _selfcheck() -> int:
    """Assert-based self-check. No network; tmp dir only."""
    import tempfile

    passed = 0

    def ok(cond: bool, label: str) -> None:
        nonlocal passed
        assert cond, "FAIL: " + label
        passed += 1
        print("PASS " + label)

    with tempfile.TemporaryDirectory() as tmp:
        ob = BoardOutbox(os.path.join(tmp, "outbox.sqlite3"))
        request = {
            "title": "Synthetic course build",
            "description": "synthetic description",
            "source": "ghl-hybrid",
            "idempotency_key": "run-1:course:outline",
            "api_token": "synthetic-secret-value-123456",
        }
        original_hash = request_hash(request)
        ev = build_event(
            idempotency_key="run-1:course:outline", request=request, run_id="run-1",
            operation_key="course:outline", family="course", now=1000.0,
        )
        stored, created = ob.enqueue(ev, now=1000.0)
        ok(created and stored["status"] == "pending", "event is durable before delivery")
        ok(stored["request"]["api_token"] == ghl_evidence.REDACTED,
           "secret-named request key redacted before the durable write")
        ok(stored["request_hash"] == original_hash,
           "request_hash is computed over the intent before redaction")
        again, created2 = ob.enqueue(ev, now=1001.0)
        ok(created2 is False and again["event_id"] == stored["event_id"],
           "same idempotency key returns the same event, nothing written")
        ok(ob.counts()["total"] == 1, "duplicate enqueue wrote nothing")

        ob.claim(ev["idempotency_key"], now=1002.0)
        receipt = ob.fail(ev["idempotency_key"], "TimeoutError: board timeout", now=1003.0)
        ok(receipt["status"] == "pending" and receipt["attempts"] == 1,
           "board timeout queues the event with bounded backoff")
        ok(ob.due(now=1003.0) == [], "backoff hides the event until its next attempt")
        ok(len(ob.due(now=1100.0)) == 1, "event returns to due() after backoff")
        ob.claim(ev["idempotency_key"], now=1101.0)
        receipt = ob.ack(ev["idempotency_key"], "task-synthetic-1", now=1102.0)
        ok(receipt["status"] == "acked" and receipt["ack_task_id"] == "task-synthetic-1",
           "acknowledgment records the local receipt")
        ok(ob.ack(ev["idempotency_key"], "task-synthetic-1", now=1103.0)["status"] == "acked",
           "repeated acknowledgment is harmless")
        ok(ob.due(now=5000.0) == [], "acked events are never redelivered")

        bad = dict(ev)
        bad["idempotency_key"] = "run-1:bad"
        bad["source"] = "not-a-source"
        try:
            ob.enqueue(bad)
            ok(False, "unknown source must be refused")
        except OutboxError:
            ok(True, "unknown source refused by the allowlist")

        ob.record_parent("run-1", "parent-synthetic-1", now=2000.0)
        ok(ob.parent_for("run-1") == "parent-synthetic-1",
           "existing parent mapping is reused, never re-created")

        projects = build_event(
            idempotency_key="run-1:projects:1", request={"title": "Synthetic task"},
            run_id="run-1", operation_key="cc-task-1", family="projects_sync",
            domain="projects_sync", logical_action="projects.task.upsert", now=3000.0,
        )
        pstored, pcreated = ob.enqueue(projects, now=3000.0)
        ok(pcreated and pstored["logical_action"] == "projects.task.upsert",
           "Projects sync keeps its own mapped logical action")
        ob.close()

        ob = BoardOutbox(os.path.join(tmp, "outbox.sqlite3"))
        ok(ob.status_of(ev["idempotency_key"]) == "acked",
           "durable: acks survive reopen")
        ob.close()

    print(f"OK {passed} PASS")
    return 0


if __name__ == "__main__":
    sys.exit(_selfcheck())
