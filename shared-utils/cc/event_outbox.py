"""
shared-utils/cc/event_outbox.py — durable event outbox and reconciliation for
the GHL delivery stream board events (W11, assignment W11AC unit 2 / W11C).

One writer for this file: assignment W11AC-U2. This module is the PRODUCER-side
durable outbox for board task-lifecycle events. It sits between the cc_board
producer (W11AC-U1 board_events.py) and the Command Center consumer
(blackceo-command-center src/task_state.ts, W11B).

Contract basis (GHL-DELIVERY-SPEC.md, "Board events (W11 contract)" and
"Command Center (W11)"): task lifecycle events (create/assign/start/block/
complete) with stable task IDs, idempotency keys, monotonic sequence/revision,
durable outbox with reconciliation, so simultaneous updates never overwrite
newer state and board retries must never repeat GHL writes or purchases.

WIRE SHAPE — closed against the real W11B consumer implementation
(lanes/W11B-U1-lane/wt/src/task_state.ts, interface BoardEventInput):

    {"idempotencyKey", "taskId", "kind", "seq", "parentTaskId",
     "title", "actor", "note", "stage", "at"}

  kind : "create" | "assign" | "start" | "block" | "complete"
  stage: "code_built" | "remote_incorporated" | "configured_object"
         | "published" | "owner_accepted"   (monotonic advance, optional)
  seq  : producer-monotonic per task; the consumer applies it only when it
         strictly increases, and treats a replayed idempotencyKey as a
         duplicate with zero change and zero effects.

Guarantees enforced here:

1. Durable. Events live in a SQLite outbox; every state change is a committed
   transaction. Nothing is ever deleted — the outbox is the audit trail.
2. Idempotent append. The idempotency key is UNIQUE. Appending the same key
   again returns the existing event with created=False and writes nothing.
   A board retry therefore NEVER creates a second effect.
3. Monotonic sequence. seq is allocated strictly increasing per task inside
   one IMMEDIATE transaction (or accepted explicit when it is strictly
   greater than the task's last seq). A stale seq is refused — older state
   must never overwrite newer state.
4. Stable identity on retry. A redelivery carries the SAME event_id,
   idempotency key and seq as the original attempt. Reconciling an uncertain
   outcome back to pending never mints a new identity.
5. At-least-once delivery, never-after-acked. due() returns pending events
   whose backoff has elapsed, per-task in seq order; acked and rejected
   events are never redelivered (board retries must never repeat GHL writes
   or purchases). Delivery order across tasks is not a claim; per-task seq
   order is.
6. Bounded backoff on failure. mark_failed schedules a bounded exponential
   retry (capped), attempts increments; mark_rejected is terminal (the
   consumer deterministically refused the event, e.g. stale_seq).
7. Reconciliation of uncertain outcomes. An in_flight event whose lease
   expired has an UNKNOWN outcome (the send may or may not have applied).
   reconcile(resolver) asks the authoritative consumer state and settles:
   applied -> acked; not_applied -> back to pending under the SAME identity;
   unknown -> left untouched and reported as unresolved. Contradictions
   (resolver says "applied" while its own sequence says the task has not
   reached this seq, or "not_applied" while it has) FAIL CLOSED: nothing is
   settled and nothing is resent, because resending might repeat a write.
8. Newer state wins. Observed consumer sequence per task is remembered and
   never allowed to move backwards; a regressed report is recorded as a
   contradiction, never applied.

Scope: this module performs no network IO and talks to no platform. The
resolver callable of reconcile() is the caller's authoritative read of the
consumer (that seam is integration work, see seam_status()). Validation here
is shape-level and fail-closed; consumer-side parent/status semantics are
W11B's job.

PROVISIONAL (W11AC-U2): the W11AC-U1 producer module
shared-utils/cc/board_events.py lands via the batch integrator. This module
consumes its real ``to_outbox_envelope`` shape (append_envelope) and emits the
W11B wire keys, and exposes seam_status() so every caller can see exactly what
integration remains outstanding.

Import pattern (namespace package — no __init__.py needed):

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared-utils"))
    from cc.event_outbox import EventOutbox

Run the assert-based self-check (stdlib only):

    python3 -I shared-utils/cc/event_outbox.py
"""

from __future__ import annotations

import sqlite3
import time
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

EVENT_KINDS: Tuple[str, ...] = ("create", "assign", "start", "block", "complete")

DELIVERY_STAGES: Tuple[str, ...] = (
    "code_built",
    "remote_incorporated",
    "configured_object",
    "published",
    "owner_accepted",
)

# Outbox event statuses. Terminal states are never redelivered.
STATUS_PENDING = "pending"
STATUS_IN_FLIGHT = "in_flight"
STATUS_ACKED = "acked"
STATUS_REJECTED = "rejected"
ALL_STATUSES: Tuple[str, ...] = (STATUS_PENDING, STATUS_IN_FLIGHT, STATUS_ACKED, STATUS_REJECTED)

DEFAULT_LEASE_S = 300.0     # an in_flight send older than this has an uncertain outcome
DEFAULT_BACKOFF_BASE_S = 1.0
DEFAULT_BACKOFF_CAP_S = 64.0  # bounded backoff — never unbounded retry storms

_SCHEMA = """
CREATE TABLE IF NOT EXISTS outbox_events (
    event_id        TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    task_id         TEXT NOT NULL,
    kind            TEXT NOT NULL,
    seq             INTEGER NOT NULL,
    parent_task_id  TEXT,
    title           TEXT,
    actor           TEXT,
    note            TEXT,
    stage           TEXT,
    at              TEXT,
    status          TEXT NOT NULL,
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at REAL NOT NULL DEFAULT 0,
    sent_at         REAL,
    last_error      TEXT,
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL,
    UNIQUE (task_id, seq)
);
CREATE TABLE IF NOT EXISTS outbox_tasks (
    task_id      TEXT PRIMARY KEY,
    last_seq     INTEGER NOT NULL,
    consumer_seq INTEGER
);
"""


class OutboxError(ValueError):
    """Raised on invalid input or an illegal state transition. Fail closed."""


def _require_str(value: Any, field: str, *, allow_none: bool = False) -> Optional[str]:
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or value == "":
        raise OutboxError(f"bad_input: {field} must be a non-empty string")
    return value


def _require_seq(value: Any) -> int:
    # bool is an int subclass — explicitly refused.
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise OutboxError("bad_input: seq must be an int >= 1")
    return value


def _wire(row: Dict[str, Any]) -> Dict[str, Any]:
    """Project an outbox row to the W11B BoardEventInput wire shape.

    The four required keys are always present; optional keys appear only when
    set (the W11A to_consumer_projection convention — two identical logical
    events serialize identically).
    """
    out: Dict[str, Any] = {
        "idempotencyKey": row["idempotency_key"],
        "taskId": row["task_id"],
        "kind": row["kind"],
        "seq": row["seq"],
    }
    for src, dst in (("parent_task_id", "parentTaskId"), ("title", "title"),
                     ("actor", "actor"), ("note", "note"),
                     ("stage", "stage"), ("at", "at")):
        if row[src] is not None:
            out[dst] = row[src]
    return out


class EventOutbox:
    """Durable, idempotent, sequence-monotonic board-event outbox over SQLite."""

    def __init__(self, path: str, *,
                 backoff_base_s: float = DEFAULT_BACKOFF_BASE_S,
                 backoff_cap_s: float = DEFAULT_BACKOFF_CAP_S,
                 lease_s: float = DEFAULT_LEASE_S) -> None:
        self.path = str(path)
        self.backoff_base_s = float(backoff_base_s)
        self.backoff_cap_s = float(backoff_cap_s)
        self.lease_s = float(lease_s)
        self._db = sqlite3.connect(self.path)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        with self._tx() as cur:
            cur.executescript(_SCHEMA)

    # ── plumbing ────────────────────────────────────────────────────────────

    def close(self) -> None:
        self._db.close()

    def _tx(self):
        return _Tx(self._db)

    def _row(self, cur: sqlite3.Cursor, event_id: str) -> Dict[str, Any]:
        row = cur.execute("SELECT * FROM outbox_events WHERE event_id = ?", (event_id,)).fetchone()
        if row is None:
            raise OutboxError(f"unknown event_id {event_id!r}")
        return dict(row)

    def _row_by_key(self, cur: sqlite3.Cursor, idempotency_key: str) -> Optional[Dict[str, Any]]:
        row = cur.execute(
            "SELECT * FROM outbox_events WHERE idempotency_key = ?", (idempotency_key,)
        ).fetchone()
        return dict(row) if row is not None else None

    def _row_by_ref(self, cur: sqlite3.Cursor, ref: str) -> Dict[str, Any]:
        """Resolve an event by its internal event_id or its stable idempotency key."""
        _require_str(ref, "event ref")
        row = cur.execute(
            "SELECT * FROM outbox_events WHERE event_id = ? OR idempotency_key = ?", (ref, ref)
        ).fetchone()
        if row is None:
            raise OutboxError(f"unknown event ref {ref!r}")
        return dict(row)

    # ── append (idempotent, sequence-monotonic) ─────────────────────────────

    def append(self, *, idempotency_key: str, task_id: str, kind: str,
               seq: Optional[int] = None,
               parent_task_id: Optional[str] = None,
               title: Optional[str] = None, actor: Optional[str] = None,
               note: Optional[str] = None, stage: Optional[str] = None,
               at: Optional[str] = None,
               now: Optional[float] = None) -> Tuple[Dict[str, Any], bool]:
        """Append one board event. Returns (wire_event, created).

        created=False means the idempotency key was already present: the
        existing event is returned unchanged and NOTHING is written — a board
        retry never creates a second effect. An explicit seq must be strictly
        greater than the task's last seq; a stale seq is refused.
        """
        _require_str(idempotency_key, "idempotency_key")
        _require_str(task_id, "task_id")
        if kind not in EVENT_KINDS:
            raise OutboxError(f"bad_input: kind {kind!r} not in {EVENT_KINDS}")
        if parent_task_id is not None:
            _require_str(parent_task_id, "parent_task_id")
            if parent_task_id == task_id:
                raise OutboxError("bad_input: self_parent (parent_task_id == task_id)")
        for name, value in (("title", title), ("actor", actor), ("note", note), ("at", at)):
            _require_str(value, name, allow_none=True)
        if stage is not None and stage not in DELIVERY_STAGES:
            raise OutboxError(f"bad_input: stage {stage!r} not in {DELIVERY_STAGES}")
        if seq is not None:
            _require_seq(seq)

        ts = time.time() if now is None else float(now)
        with self._tx() as cur:
            existing = self._row_by_key(cur, idempotency_key)
            if existing is not None:
                # Idempotent: same key -> same event, zero new writes.
                return _wire(existing), False

            last = cur.execute(
                "SELECT last_seq FROM outbox_tasks WHERE task_id = ?", (task_id,)
            ).fetchone()
            last_seq = int(last["last_seq"]) if last is not None else 0
            if seq is None:
                seq = last_seq + 1
            elif seq <= last_seq:
                # Monotonicity: older state must never overwrite newer state.
                raise OutboxError(
                    f"stale_seq: seq {seq} not greater than task {task_id!r} last seq {last_seq}"
                )

            event_id = "evt_" + uuid.uuid4().hex
            cur.execute(
                "INSERT INTO outbox_events (event_id, idempotency_key, task_id, kind, seq,"
                " parent_task_id, title, actor, note, stage, at, status, attempts,"
                " next_attempt_at, sent_at, last_error, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0,?,NULL,NULL,?,?)",
                (event_id, idempotency_key, task_id, kind, seq, parent_task_id,
                 title, actor, note, stage, at, STATUS_PENDING, ts, ts, ts),
            )
            if last is None:
                cur.execute(
                    "INSERT INTO outbox_tasks (task_id, last_seq) VALUES (?, ?)", (task_id, seq)
                )
            else:
                cur.execute(
                    "UPDATE outbox_tasks SET last_seq = ? WHERE task_id = ?", (seq, task_id)
                )
            row = self._row(cur, event_id)
            return _wire(row), True

    def append_envelope(self, envelope: Dict[str, Any],
                        now: Optional[float] = None) -> Tuple[Dict[str, Any], bool]:
        """Append from the W11A producer envelope — closed against the real
        shared-utils/cc/board_events.py ``to_outbox_envelope`` shape:

            {"schema", "idempotency_key", "task_id", "kind", "seq",
             "payload": {producer wire dict with optional display fields}}

        Identity comes from the envelope's identity keys (the contract owns
        identity, the outbox owns delivery/retry state); optional display
        fields (parent_task_id, title, actor, note, stage, at) are taken from
        ``payload`` when present. Extra keys (schema, payload) are carried by
        the producer and ignored here, never invented or coerced.
        """
        if not isinstance(envelope, dict):
            raise OutboxError("bad_input: envelope must be a dict")
        payload = envelope.get("payload")
        if payload is not None and not isinstance(payload, dict):
            raise OutboxError("bad_input: envelope payload must be a dict")

        def field(name: str) -> Any:
            if name in envelope:
                return envelope[name]
            return payload.get(name) if payload else None

        return self.append(
            idempotency_key=field("idempotency_key"),
            task_id=field("task_id"),
            kind=field("kind"),
            seq=field("seq"),
            parent_task_id=field("parent_task_id"),
            title=field("title"),
            actor=field("actor"),
            note=field("note"),
            stage=field("stage"),
            at=field("at"),
            now=now,
        )

    # ── delivery lifecycle ──────────────────────────────────────────────────

    def due(self, now: Optional[float] = None) -> List[Dict[str, Any]]:
        """Pending events whose backoff has elapsed, per-task in seq order.

        acked and rejected events are never returned — a board retry must
        never repeat GHL writes or purchases.
        """
        ts = time.time() if now is None else float(now)
        cur = self._db.execute(
            "SELECT * FROM outbox_events WHERE status = ? AND next_attempt_at <= ?"
            " ORDER BY next_attempt_at, task_id, seq",
            (STATUS_PENDING, ts),
        )
        return [_wire(dict(r)) for r in cur.fetchall()]

    def event(self, idempotency_key: str) -> Dict[str, Any]:
        """Wire view of one event by idempotency key (audit read)."""
        _require_str(idempotency_key, "idempotency_key")
        cur = self._db.execute(
            "SELECT * FROM outbox_events WHERE idempotency_key = ?", (idempotency_key,)
        )
        row = cur.fetchone()
        if row is None:
            raise OutboxError(f"unknown idempotency_key {idempotency_key!r}")
        return _wire(dict(row))

    def status_of(self, idempotency_key: str) -> str:
        _require_str(idempotency_key, "idempotency_key")
        cur = self._db.execute(
            "SELECT status FROM outbox_events WHERE idempotency_key = ?", (idempotency_key,)
        )
        row = cur.fetchone()
        if row is None:
            raise OutboxError(f"unknown idempotency_key {idempotency_key!r}")
        return row["status"]

    def mark_sent(self, ref: str, now: Optional[float] = None) -> None:
        """pending -> in_flight. The outcome is now uncertain until acked or reconciled.

        ref: the event's internal event_id or its stable idempotency key.
        """
        ts = time.time() if now is None else float(now)
        with self._tx() as cur:
            row = self._row_by_ref(cur, ref)
            if row["status"] != STATUS_PENDING:
                raise OutboxError(f"illegal transition: mark_sent from {row['status']!r}")
            cur.execute(
                "UPDATE outbox_events SET status = ?, sent_at = ?, updated_at = ?"
                " WHERE event_id = ?",
                (STATUS_IN_FLIGHT, ts, ts, row["event_id"]),
            )

    def mark_acked(self, ref: str, now: Optional[float] = None) -> None:
        """in_flight -> acked (terminal). Never redelivered."""
        ts = time.time() if now is None else float(now)
        with self._tx() as cur:
            row = self._row_by_ref(cur, ref)
            if row["status"] != STATUS_IN_FLIGHT:
                raise OutboxError(f"illegal transition: mark_acked from {row['status']!r}")
            cur.execute(
                "UPDATE outbox_events SET status = ?, updated_at = ? WHERE event_id = ?",
                (STATUS_ACKED, ts, row["event_id"]),
            )

    def mark_failed(self, ref: str, error: str, now: Optional[float] = None) -> None:
        """in_flight -> pending with bounded backoff. SAME identity on retry."""
        _require_str(error, "error")
        ts = time.time() if now is None else float(now)
        with self._tx() as cur:
            row = self._row_by_ref(cur, ref)
            if row["status"] != STATUS_IN_FLIGHT:
                raise OutboxError(f"illegal transition: mark_failed from {row['status']!r}")
            attempts = int(row["attempts"]) + 1
            delay = min(self.backoff_base_s * (2 ** (attempts - 1)), self.backoff_cap_s)
            cur.execute(
                "UPDATE outbox_events SET status = ?, attempts = ?, next_attempt_at = ?,"
                " last_error = ?, updated_at = ? WHERE event_id = ?",
                (STATUS_PENDING, attempts, ts + delay, error, ts, row["event_id"]),
            )

    def mark_rejected(self, ref: str, reason: str, now: Optional[float] = None) -> None:
        """in_flight -> rejected (terminal). The consumer deterministically refused
        the event; resending would only repeat the refusal."""
        _require_str(reason, "reason")
        ts = time.time() if now is None else float(now)
        with self._tx() as cur:
            row = self._row_by_ref(cur, ref)
            if row["status"] != STATUS_IN_FLIGHT:
                raise OutboxError(f"illegal transition: mark_rejected from {row['status']!r}")
            cur.execute(
                "UPDATE outbox_events SET status = ?, last_error = ?, updated_at = ?"
                " WHERE event_id = ?",
                (STATUS_REJECTED, reason, ts, row["event_id"]),
            )

    # ── reconciliation ──────────────────────────────────────────────────────

    def reconcile(self, resolver: Callable[[Dict[str, Any]], Any],
                  now: Optional[float] = None,
                  lease_s: Optional[float] = None) -> Dict[str, Any]:
        """Settle in_flight events whose outcome is uncertain.

        resolver(wire_event) is the caller's AUTHORITATIVE read of the consumer
        state for that event. It returns either one of the strings
        "applied" / "not_applied" / "unknown", or a dict
        {"state": <one of those>, "last_seq": <int or None>} where last_seq is
        the consumer's highest applied seq for that task.

        Settlement (fail closed on every contradiction):
          applied                          -> acked
          not_applied                      -> back to pending, SAME event_id,
                                              idempotency key and seq (no new
                                              identity, no double effect)
          unknown                          -> untouched, counted unresolved
          applied + last_seq < event seq   -> contradiction: consumer claims the
                                              event applied but its sequence has
                                              not reached it. NOTHING settles and
                                              NOTHING is resent.
          not_applied + last_seq >= seq    -> contradiction: sequence says the
                                              event was consumed. Resending might
                                              repeat a write, so nothing is resent.

        Observed consumer sequence never moves backwards (newer state wins); a
        regressed report is recorded, never applied.
        """
        ts = time.time() if now is None else float(now)
        lease = self.lease_s if lease_s is None else float(lease_s)
        report: Dict[str, Any] = {
            "checked": 0, "acked": 0, "requeued": 0, "unresolved": 0,
            "contradictions": [], "regressions": [],
        }
        cur = self._db.execute(
            "SELECT * FROM outbox_events WHERE status = ? AND sent_at IS NOT NULL"
            " AND sent_at <= ? ORDER BY task_id, seq",
            (STATUS_IN_FLIGHT, ts - lease),
        )
        stale = [dict(r) for r in cur.fetchall()]
        for row in stale:
            report["checked"] += 1
            wire = _wire(row)
            try:
                res = resolver(wire)
            except Exception as exc:  # resolver broken -> unknown, never guessed
                report["unresolved"] += 1
                report["contradictions"].append({
                    "event_id": row["event_id"], "kind": "resolver_error",
                    "detail": f"{type(exc).__name__}: {exc}",
                })
                continue

            if isinstance(res, str):
                state, last_seq = res, None
            elif isinstance(res, dict):
                state, last_seq = res.get("state"), res.get("last_seq")
            else:
                report["unresolved"] += 1
                report["contradictions"].append({
                    "event_id": row["event_id"], "kind": "bad_resolver_return",
                    "detail": f"unusable resolver return {res!r}",
                })
                continue
            if state not in ("applied", "not_applied", "unknown"):
                report["unresolved"] += 1
                report["contradictions"].append({
                    "event_id": row["event_id"], "kind": "bad_resolver_return",
                    "detail": f"state {state!r} not applied/not_applied/unknown",
                })
                continue

            with self._tx() as cur2:
                # Newer consumer state wins: observed seq never regresses.
                trow = cur2.execute(
                    "SELECT consumer_seq FROM outbox_tasks WHERE task_id = ?",
                    (row["task_id"],),
                ).fetchone()
                if isinstance(last_seq, bool) or not isinstance(last_seq, int):
                    last_seq = None
                observed = trow["consumer_seq"] if trow is not None else None
                if last_seq is not None and observed is not None and last_seq < observed:
                    report["regressions"].append({
                        "task_id": row["task_id"], "reported_seq": last_seq,
                        "kept_seq": observed,
                    })
                    last_seq = observed  # never adopt the older value

                if state == "applied" and (last_seq is None or last_seq >= row["seq"]):
                    cur2.execute(
                        "UPDATE outbox_events SET status = ?, updated_at = ? WHERE event_id = ?",
                        (STATUS_ACKED, ts, row["event_id"]),
                    )
                    report["acked"] += 1
                elif state == "not_applied" and (last_seq is None or last_seq < row["seq"]):
                    # Requeue under the SAME identity: event_id, key and seq unchanged.
                    cur2.execute(
                        "UPDATE outbox_events SET status = ?, next_attempt_at = ?,"
                        " updated_at = ? WHERE event_id = ?",
                        (STATUS_PENDING, ts, ts, row["event_id"]),
                    )
                    report["requeued"] += 1
                elif state == "unknown":
                    report["unresolved"] += 1
                else:
                    report["contradictions"].append({
                        "event_id": row["event_id"], "kind": f"{state}_seq_conflict",
                        "detail": (f"resolver {state!r} but consumer last_seq={last_seq}"
                                   f" vs event seq={row['seq']}; nothing settled, nothing resent"),
                    })
                    report["unresolved"] += 1

                if last_seq is not None:
                    if observed is None:
                        cur2.execute(
                            "UPDATE outbox_tasks SET consumer_seq = ? WHERE task_id = ?",
                            (last_seq, row["task_id"]),
                        )
                    elif last_seq > observed:
                        cur2.execute(
                            "UPDATE outbox_tasks SET consumer_seq = ? WHERE task_id = ?",
                            (last_seq, row["task_id"]),
                        )
        return report

    # ── views ───────────────────────────────────────────────────────────────

    def counts(self) -> Dict[str, int]:
        """Per-status counts against the explicit denominator (total)."""
        out = {s: 0 for s in ALL_STATUSES}
        for r in self._db.execute(
            "SELECT status, COUNT(*) AS n FROM outbox_events GROUP BY status"
        ).fetchall():
            out[r["status"]] = int(r["n"])
        out["total"] = sum(out[s] for s in ALL_STATUSES)
        return out

    def events_for(self, task_id: str) -> List[Dict[str, Any]]:
        """All events for one task in seq order (audit trail — nothing is deleted)."""
        _require_str(task_id, "task_id")
        cur = self._db.execute(
            "SELECT * FROM outbox_events WHERE task_id = ? ORDER BY seq", (task_id,)
        )
        return [_wire(dict(r)) for r in cur.fetchall()]

    def last_seq(self, task_id: str) -> int:
        _require_str(task_id, "task_id")
        row = self._db.execute(
            "SELECT last_seq FROM outbox_tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        return int(row["last_seq"]) if row is not None else 0


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


def seam_status() -> Dict[str, Any]:
    """Explicit integration-seam status — never pretended as landed."""
    outstanding = [
        "W11AC-U1 board_events.py producer calls append_envelope()/append()/due()/"
        "mark_* — envelope seam closed against its real to_outbox_envelope shape; "
        "the two units land via the batch integrator, runtime wiring is integration work",
        "reconcile() resolver: authoritative consumer read (CC API or task_state "
        "projection) is wired by the integration owner, not this module",
        "W4B evidence.py state_counts -> stage mapping is the board consumer's",
    ]
    try:  # pragma: no cover - import probe only
        from cc import board_events  # noqa: F401
        producer_importable = True
    except Exception:
        producer_importable = False
    return {"outstanding": outstanding, "board_events_importable": producer_importable}


# ── self-check ───────────────────────────────────────────────────────────────

def _selfcheck() -> int:
    import os
    import tempfile

    passed = 0

    def ok(cond: bool, label: str) -> None:
        nonlocal passed
        assert cond, "FAIL: " + label
        passed += 1
        print("PASS " + label)

    tmp = os.path.join(tempfile.gettempdir(), "lane-W11C-U1-outbox-selfcheck.sqlite")
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(tmp + suffix)
        except FileNotFoundError:
            pass

    # 1 — append allocates strictly increasing per-task seq
    ob = EventOutbox(tmp)
    e1, created = ob.append(idempotency_key="k1", task_id="T1", kind="create",
                            title="Build page A", now=1000.0)
    e2, _ = ob.append(idempotency_key="k2", task_id="T1", kind="start", now=1001.0)
    e3, _ = ob.append(idempotency_key="k3", task_id="T1", kind="complete", now=1002.0)
    ok(created and (e1["seq"], e2["seq"], e3["seq"]) == (1, 2, 3),
       "append allocates strictly increasing per-task seq (got 1,2,3)")

    # 2 — wire shape matches W11B BoardEventInput: required 4 always present,
    #     optionals only when set (W11A to_consumer_projection convention)
    ok(set(e1.keys()) == {"idempotencyKey", "taskId", "kind", "seq", "title"},
       f"wire keys: required 4 + set optionals only (got {sorted(e1.keys())})")
    ok(e1["idempotencyKey"] == "k1" and e1["taskId"] == "T1" and e1["kind"] == "create",
       "wire values carry stable task id, idempotency key, kind")

    # 2b — W11A to_outbox_envelope seam: real envelope shape appends cleanly
    ob2 = EventOutbox(tmp + ".env")
    envelope = {  # literal replica of W11A board_events.to_outbox_envelope output
        "schema": "ghl-board-event/1",
        "idempotency_key": "env-key-1",
        "task_id": "T-ENV",
        "kind": "assign",
        "seq": 1,
        "payload": {
            "schema": "ghl-board-event/1", "kind": "assign", "task_id": "T-ENV",
            "idempotency_key": "env-key-1", "seq": 1,
            "producer_id": "cc_board", "correlation_id": "ingest-9",
            "parent_task_id": "T-PARENT", "title": "Wire the board",
            "actor": "w11a", "note": "from envelope", "stage": "code_built",
            "at": "2026-10-23T00:00:00Z",
        },
    }
    ev_env, env_created = ob2.append_envelope(envelope, now=500.0)
    ok(env_created is True and ev_env["seq"] == 1 and ev_env["taskId"] == "T-ENV",
       "append_envelope accepts the real W11A envelope shape")
    ok(set(ev_env.keys()) == {"idempotencyKey", "taskId", "kind", "seq", "parentTaskId",
                              "title", "actor", "note", "stage", "at"},
       "envelope optionals promoted from payload; full 10-key wire when all set")
    ok(ev_env["parentTaskId"] == "T-PARENT" and ev_env["stage"] == "code_built",
       "payload display fields promoted unchanged (never coerced)")
    _, env_dup = ob2.append_envelope(envelope, now=501.0)
    ok(env_dup is False and ob2.counts()["total"] == 1,
       "envelope re-append is idempotent (dedupe on idempotency_key)")
    ob2.close()

    # 3 — idempotent append: same key = same event, zero new writes
    e1b, created2 = ob.append(idempotency_key="k1", task_id="T1", kind="create", now=1003.0)
    ok(created2 is False and e1b["seq"] == 1,
       "duplicate idempotency key returns existing event, created=False")
    ok(ob.counts()["total"] == 3, "duplicate append wrote nothing (total still 3)")

    # 4 — monotonic seq: stale explicit seq refused (older never overwrites newer)
    try:
        ob.append(idempotency_key="k4", task_id="T1", kind="block", seq=2, now=1004.0)
        ok(False, "stale explicit seq must raise")
    except OutboxError as exc:
        ok("stale_seq" in str(exc), f"stale explicit seq refused ({exc})")

    # 5 — explicit seq strictly greater is accepted (producer-owned numbering)
    e4, _ = ob.append(idempotency_key="k5", task_id="T1", kind="block", seq=7, now=1005.0)
    ok(e4["seq"] == 7 and ob.last_seq("T1") == 7,
       "explicit greater seq accepted and becomes task last seq")

    # 6 — interleaved tasks keep independent monotonic sequences
    ea, _ = ob.append(idempotency_key="ka", task_id="T2", kind="create", now=1006.0)
    eb, _ = ob.append(idempotency_key="kb", task_id="T2", kind="assign", now=1007.0)
    ok((ea["seq"], eb["seq"]) == (1, 2), "per-task seq independent across tasks")

    # 7 — bad input fails closed
    for bad, label in (
        (lambda: ob.append(idempotency_key="", task_id="T3", kind="create"), "empty idempotency key"),
        (lambda: ob.append(idempotency_key="z1", task_id="", kind="create"), "empty task id"),
        (lambda: ob.append(idempotency_key="z2", task_id="T3", kind="publish"), "unknown kind"),
        (lambda: ob.append(idempotency_key="z3", task_id="T3", kind="create", seq=True), "bool seq"),
        (lambda: ob.append(idempotency_key="z4", task_id="T3", kind="create", seq=0), "zero seq"),
        (lambda: ob.append(idempotency_key="z5", task_id="T3", kind="create", stage="done"), "unknown stage"),
        (lambda: ob.append(idempotency_key="z6", task_id="T3", kind="create", parent_task_id="T3"), "self_parent"),
    ):
        try:
            bad()
            ok(False, label + " must raise")
        except OutboxError:
            ok(True, f"{label} rejected")

    # 8 — due(): pending events, per-task seq order; acked/rejected never returned
    due1 = ob.due(now=1010.0)
    keys = [w["idempotencyKey"] for w in due1]
    ok(keys == ["k1", "k2", "k3", "k5", "ka", "kb"],
       f"due returns pending in per-task seq order (got {keys})")

    # 9 — delivery lifecycle: sent events leave due(); acked never returns
    ob.mark_sent("k1", now=1011.0)
    ok(ob.status_of("k1") == "in_flight", "mark_sent moves pending -> in_flight")
    ok(all(w["idempotencyKey"] != "k1" for w in ob.due(now=1012.0)),
       "in_flight event not in due()")
    ob.mark_acked("k1", now=1013.0)
    ok(ob.status_of("k1") == "acked", "mark_acked moves in_flight -> acked")
    ok(all(w["idempotencyKey"] != "k1" for w in ob.due(now=1020.0)),
       "acked event never redelivered (no repeated GHL writes)")

    # 10 — mark_failed: bounded backoff, attempts counted, SAME identity on retry
    ob.mark_sent("k2", now=1014.0)
    ob.mark_failed("k2", "network timeout", now=1015.0)
    ok(ob.status_of("k2") == "pending", "mark_failed requeues in_flight -> pending")
    ok(ob.due(now=1015.0) == [] or all(w["idempotencyKey"] != "k2" for w in ob.due(now=1015.0)),
       "backoff hides the failed event until its next attempt time")
    k2_retry = ob.event("k2")
    ok(k2_retry["seq"] == 2 and k2_retry["idempotencyKey"] == "k2",
       "retry carries the SAME idempotency key and seq (no new identity)")
    k2_due = [w for w in ob.due(now=1100.0) if w["idempotencyKey"] == "k2"]
    ok(len(k2_due) == 1, "failed event returns to due() after bounded backoff")
    ob.mark_sent("k2", now=1101.0)
    ob.mark_acked("k2", now=1102.0)

    # 11 — mark_rejected: terminal, never redelivered
    ob.mark_sent("k3", now=1016.0)
    ob.mark_rejected("k3", "stale_seq", now=1017.0)
    ok(ob.status_of("k3") == "rejected" and
       all(w["idempotencyKey"] != "k3" for w in ob.due(now=1200.0)),
       "mark_rejected is terminal; event never redelivered")

    # 12 — illegal transitions fail closed
    for fn, label in (
        (lambda: ob.mark_sent("k1", now=1300.0), "mark_sent on acked"),
        (lambda: ob.mark_acked("zzz-nope", now=1300.0), "mark_acked on unknown ref"),
        (lambda: ob.mark_failed("k5", "err", now=1300.0), "mark_failed on pending"),
    ):
        try:
            fn()
            ok(False, label + " must raise")
        except OutboxError:
            ok(True, f"{label} refused")

    # 13 — durability: reopen the DB, all state survives
    ob.close()
    ob = EventOutbox(tmp)
    ok(ob.status_of("k1") == "acked" and ob.last_seq("T1") == 7,
       "durable: acked status and task seq survive reopen")

    # 14 — reconcile: uncertain in_flight + resolver 'applied' -> acked
    ob.append(idempotency_key="r1", task_id="T9", kind="create", now=2000.0)
    ob.mark_sent("r1", now=2001.0)
    rep = ob.reconcile(lambda w: "applied", now=2001.0 + ob.lease_s + 1)
    ok(rep["acked"] == 1 and ob.status_of("r1") == "acked",
       "reconcile settles uncertain outcome 'applied' -> acked")

    # 15 — reconcile: 'not_applied' -> back to pending under the SAME identity
    ob.append(idempotency_key="r2", task_id="T9", kind="start", now=2010.0)
    ob.mark_sent("r2", now=2011.0)
    rep = ob.reconcile(lambda w: "not_applied", now=2011.0 + ob.lease_s + 1)
    ok(rep["requeued"] == 1 and ob.status_of("r2") == "pending",
       "reconcile requeues 'not_applied' -> pending")
    ok(ob.event("r2")["seq"] == 2 and ob.event("r2")["idempotencyKey"] == "r2",
       "requeued event keeps SAME idempotency key and seq (never a new effect)")

    # 16 — reconcile: 'unknown' -> untouched and counted, never guessed
    ob.mark_sent("r2", now=2020.0)
    rep = ob.reconcile(lambda w: "unknown", now=2020.0 + ob.lease_s + 1)
    ok(rep["unresolved"] == 1 and ob.status_of("r2") == "in_flight",
       "reconcile leaves 'unknown' outcomes unresolved and untouched")

    # 17 — reconcile ignores in_flight sends whose lease has not expired
    ob.append(idempotency_key="r3", task_id="T9", kind="block", now=2030.0)
    ob.mark_sent("r3", now=2031.0)
    rep = ob.reconcile(lambda w: "applied", now=2031.0 + 1.0)
    ok(rep["checked"] == 0 and ob.status_of("r3") == "in_flight",
       "fresh in_flight send (lease live) is not reconciled")

    # 18 — contradiction: resolver 'applied' but last_seq behind the event -> fail closed
    rep = ob.reconcile(lambda w: {"state": "applied", "last_seq": 1},
                       now=2031.0 + ob.lease_s + 1)
    ok(any(c["kind"] == "applied_seq_conflict" for c in rep["contradictions"]) and
       ob.status_of("r3") == "in_flight",
       "'applied' with last_seq < seq is a contradiction: nothing settles")

    # 19 — contradiction: resolver 'not_applied' but last_seq >= seq -> never resent
    rep = ob.reconcile(lambda w: {"state": "not_applied", "last_seq": 3},
                       now=2031.0 + ob.lease_s + 2)
    ok(any(c["kind"] == "not_applied_seq_conflict" for c in rep["contradictions"]) and
       ob.status_of("r3") == "in_flight",
       "'not_applied' with last_seq >= seq: nothing resent (would repeat writes)")

    # 20 — newer consumer state wins: reported seq never regresses
    rep = ob.reconcile(lambda w: {"state": "applied", "last_seq": 3},
                       now=2031.0 + ob.lease_s + 3)
    ok(rep["acked"] == 2 and ob.status_of("r3") == "acked" and ob.status_of("r2") == "acked",
       "consistent 'applied' with last_seq >= seq settles both uncertain events -> acked")
    ob.append(idempotency_key="r4", task_id="T9", kind="complete", now=2040.0)
    ob.mark_sent("r4", now=2041.0)
    rep = ob.reconcile(lambda w: {"state": "applied", "last_seq": 1},
                       now=2041.0 + ob.lease_s + 1)
    ok(len(rep["regressions"]) == 1 and rep["regressions"][0]["kept_seq"] == 3 and
       ob.status_of("r4") == "in_flight",
       "regressed consumer seq recorded, newer kept, nothing settled on stale claim")

    # 21 — bad resolver returns fail closed: unresolved + contradiction, no state change
    bad_cases = (("maybe", "bare junk string"),
                 (42, "non-string return"),
                 ({"state": "???"}, "unknown state value"))
    for i, (bad_ret, label) in enumerate(bad_cases):
        key = f"b{i}"
        ob.append(idempotency_key=key, task_id="TB", kind="create", now=2100.0 + i)
        ob.mark_sent(key, now=2100.0 + i)
        rep = ob.reconcile(lambda w, r=bad_ret: r,
                           now=2100.0 + i + ob.lease_s + 1)
        ok(rep["unresolved"] >= 1 and
           any(c["kind"] == "bad_resolver_return" for c in rep["contradictions"]),
           f"{label} fail closed: unresolved + contradiction recorded")
        ok(ob.status_of(key) == "in_flight", f"{label} changed nothing")

    # 22 — bool last_seq is treated as absent: plain 'applied' still settles
    ob.append(idempotency_key="b3", task_id="TB", kind="create", now=2130.0)
    ob.mark_sent("b3", now=2131.0)
    rep = ob.reconcile(lambda w: {"state": "applied", "last_seq": True},
                       now=2131.0 + ob.lease_s + 1)
    ok(rep["acked"] >= 1 and ob.status_of("b3") == "acked",
       "bool last_seq ignored as absent; applied settles without a seq claim")

    # 23 — resolver raising is 'unknown', never guessed
    def _boom(w):
        raise RuntimeError("consumer API down")
    ob.append(idempotency_key="b4", task_id="TB", kind="create", now=2140.0)
    ob.mark_sent("b4", now=2141.0)
    rep = ob.reconcile(_boom, now=2141.0 + ob.lease_s + 1)
    ok(any(c["kind"] == "resolver_error" for c in rep["contradictions"]) and
       ob.status_of("b4") == "in_flight",
       "resolver exception -> unresolved + recorded, never guessed")

    # 24 — counts are per-status against the explicit denominator
    c = ob.counts()
    ok(c["total"] == sum(c[s] for s in ALL_STATUSES) and c["total"] == 15,
       f"counts sum to explicit total 15 (got {c})")

    # 25 — audit trail: every event for a task in seq order, nothing deleted
    t9 = ob.events_for("T9")
    ok([w["seq"] for w in t9] == [1, 2, 3, 4],
       "events_for returns full per-task audit trail in seq order")

    # 26 — seam status is explicit, never pretended as landed
    seam = seam_status()
    ok(isinstance(seam.get("outstanding"), list) and len(seam["outstanding"]) >= 1 and
       "board_events_importable" in seam,
       "seam_status lists outstanding integration and producer import state")

    # 27 — negative control: the instrument discriminates (nothing new is written)
    _, dup_created = ob.append(idempotency_key="k1", task_id="T1", kind="create",
                               seq=1, now=3000.0)
    ok(dup_created is False and ob.counts()["total"] == 15,
       "negative control: duplicate key with stale seq still writes nothing")

    print(f"OK {passed} PASS")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selfcheck())
