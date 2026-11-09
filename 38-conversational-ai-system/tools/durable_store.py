#!/usr/bin/env python3
"""durable_store.py - durable inbox dedupe and idempotency-keyed outbox.

Contract basis: Purple-Billboard DATA-CONTRACTS.md section 4 ("Durable
inbox/outbox and truthful stages") and section 9 ("Engineering state and
action acknowledgement"). Python 3 standard library only.

Two stores in one SQLite file:

INBOX  - one row per provider event identity (provider, tenant_id,
         provider_event_id). Dedupe is on that identity, never on a body hash:
         two legitimately identical messages with different provider event
         ids are two events. A redelivery of the same identity is admitted
         once, ever, across process restarts. Own outgoing and reveal events
         are excluded by verified direction/actor before admission.

OUTBOX - one row per logical action. States, exactly:

         not_requested -> queued -> dispatched -> acknowledged -> completed
         plus unknown, failed, canceled, suppressed, quarantined.

         suppressed and quarantined are the persisted forms of the section 3
         gate verdicts of the same name; they are terminal non-dispatch states.

         ACK and completion are separate persisted receipts. A stop ACK is not
         completion: record_completion() refuses unless an ack receipt exists.

Leases and fences:

  claim_for_dispatch() takes a lease and bumps a monotonic fence inside one
  IMMEDIATE transaction. Exactly one worker can hold a lease. begin_attempt()
  inserts the attempt row only when the action is still queued, the fence
  matches and this worker still holds the lease - a single statement that a
  cancellation or a stolen lease makes fail. Nothing is sent unless that
  statement reports one row.

  An attempt row with outcome IS NULL is an IN-FLIGHT effect: possibly sent,
  possibly not. claim_for_dispatch() refuses to start a new attempt while one
  exists, so a crash between provider acceptance and receipt persistence can
  never be resent by a racing worker. reconciliation.py resolves it.

No network IO. Nothing is deleted; the tables are the audit trail.

Import (stdlib path pattern used by Skill 38 tools):

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from durable_store import DurableStore

Assert-based self-check:  python3 -I durable_store.py
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional, Tuple

# ── vocabulary ──────────────────────────────────────────────────────────────

INBOX_STATES: Tuple[str, ...] = ("received", "admitted", "deciding", "decided")

STATE_NOT_REQUESTED = "not_requested"
STATE_QUEUED = "queued"
STATE_DISPATCHED = "dispatched"
STATE_ACKNOWLEDGED = "acknowledged"
STATE_COMPLETED = "completed"
STATE_UNKNOWN = "unknown"
STATE_FAILED = "failed"
STATE_CANCELED = "canceled"
STATE_SUPPRESSED = "suppressed"
STATE_QUARANTINED = "quarantined"

OUTBOX_STATES: Tuple[str, ...] = (
    STATE_NOT_REQUESTED, STATE_QUEUED, STATE_DISPATCHED, STATE_ACKNOWLEDGED,
    STATE_COMPLETED, STATE_UNKNOWN, STATE_FAILED, STATE_CANCELED,
    STATE_SUPPRESSED, STATE_QUARANTINED,
)

# States from which no dispatch can ever begin again.
TERMINAL_STATES = frozenset({
    STATE_COMPLETED, STATE_FAILED, STATE_CANCELED, STATE_SUPPRESSED,
    STATE_QUARANTINED,
})

RECEIPT_KINDS: Tuple[str, ...] = ("dispatch", "ack", "completion")

# DATA-CONTRACTS section 2: strictly two outbound variants.
SCOPES: Tuple[str, ...] = ("public_placement", "person_directed")

DEFAULT_LEASE_S = 60.0

_SCHEMA = """
CREATE TABLE IF NOT EXISTS inbox_events (
    provider          TEXT NOT NULL,
    tenant_id         TEXT NOT NULL,
    provider_event_id TEXT NOT NULL,
    direction         TEXT NOT NULL,
    actor_id          TEXT,
    payload_sha256    TEXT,
    state             TEXT NOT NULL,
    received_at       REAL NOT NULL,
    admitted_at       REAL,
    decided_at        REAL,
    decision_ref      TEXT,
    PRIMARY KEY (provider, tenant_id, provider_event_id)
);

CREATE TABLE IF NOT EXISTS outbox_actions (
    action_id          TEXT PRIMARY KEY,
    logical_intent_key TEXT NOT NULL UNIQUE,
    idempotency_key    TEXT NOT NULL UNIQUE,
    tenant_id          TEXT NOT NULL,
    scope              TEXT NOT NULL,
    purpose            TEXT,
    canonical_contact_id TEXT,
    content_sha256     TEXT NOT NULL,
    binding_revision   TEXT,
    state              TEXT NOT NULL,
    tries              INTEGER NOT NULL DEFAULT 0,
    fence              INTEGER NOT NULL DEFAULT 0,
    lease_owner        TEXT,
    lease_expires_at   REAL,
    not_before         REAL,
    blocked_reason     TEXT,
    cancel_reason      TEXT,
    unknown_reason     TEXT,
    created_at         REAL NOT NULL,
    updated_at         REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS outbox_attempts (
    action_id  TEXT NOT NULL,
    attempt_no INTEGER NOT NULL,
    fence      INTEGER NOT NULL,
    worker_id  TEXT NOT NULL,
    started_at REAL NOT NULL,
    ended_at   REAL,
    outcome    TEXT,
    PRIMARY KEY (action_id, attempt_no)
);

CREATE TABLE IF NOT EXISTS outbox_receipts (
    action_id           TEXT NOT NULL,
    kind                TEXT NOT NULL,
    provider            TEXT,
    provider_receipt_id TEXT,
    payload_json        TEXT NOT NULL,
    received_at         REAL NOT NULL,
    PRIMARY KEY (action_id, kind)
);

CREATE TABLE IF NOT EXISTS gate_checks (
    action_id        TEXT NOT NULL,
    attempt_no       INTEGER NOT NULL,
    verdict          TEXT NOT NULL,
    checked_at       REAL NOT NULL,
    binding_revision TEXT,
    policy_revision  TEXT,
    fence            INTEGER,
    evidence_json    TEXT NOT NULL,
    PRIMARY KEY (action_id, attempt_no)
);

CREATE TABLE IF NOT EXISTS keyword_mappings (
    tenant_id               TEXT NOT NULL,
    keyword_norm            TEXT NOT NULL,
    promised_item_version   TEXT NOT NULL,
    first_cycle_id          TEXT NOT NULL,
    first_seen_ts           REAL NOT NULL,
    retired_at              REAL,
    PRIMARY KEY (tenant_id, keyword_norm)
);

CREATE TABLE IF NOT EXISTS reconciliation_runs (
    action_id       TEXT NOT NULL,
    run_no          INTEGER NOT NULL,
    outcome         TEXT NOT NULL,
    observed_at     REAL NOT NULL,
    evidence_json   TEXT NOT NULL,
    PRIMARY KEY (action_id, run_no)
);
"""


class DurableStoreError(ValueError):
    """Raised on bad input or an illegal state transition. Always fail closed."""


class _PreSendBlocked(Exception):
    """Internal: the point-of-use guard refused. Rolls the attempt back."""


# ── small validators ────────────────────────────────────────────────────────

def _str(value: Any, field: str, *, allow_none: bool = False) -> Optional[str]:
    if value is None and allow_none:
        return None
    if not isinstance(value, str) or not value.strip():
        raise DurableStoreError(f"bad_input: {field} must be a non-empty string")
    return value


def _ts(value: Optional[float]) -> float:
    return time.time() if value is None else float(value)


class _Tx:
    """IMMEDIATE transaction. Serialises writers so claims and cancels race honestly."""

    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db
        self.cur: Optional[sqlite3.Cursor] = None

    def __enter__(self) -> sqlite3.Cursor:
        self.cur = self.db.cursor()
        self.cur.execute("BEGIN IMMEDIATE")
        return self.cur

    def __exit__(self, exc_type, exc, tb) -> bool:
        assert self.cur is not None
        if exc_type is None:
            self.db.commit()
        else:
            self.db.rollback()
        self.cur.close()
        return False


class DurableStore:
    """Durable inbox dedupe + idempotency-keyed outbox over one SQLite file."""

    def __init__(self, path: str) -> None:
        self.path = str(path)
        self._db = sqlite3.connect(self.path, timeout=30.0,
                                   isolation_level=None)  # explicit BEGIN only
        self._db.row_factory = sqlite3.Row
        # busy_timeout first: switching to WAL takes a database-wide lock, and
        # two processes opening the same new file must wait rather than fail.
        # SQLite does not always invoke the busy handler for the journal_mode
        # change itself, so that one statement is retried explicitly.
        self._db.execute("PRAGMA busy_timeout=30000")
        self._retry(lambda: self._db.execute("PRAGMA journal_mode=WAL").fetchone(),
                    what="journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")   # a committed effect survives a kill
        self._retry(lambda: self._db.executescript(_SCHEMA), what="schema")

    def _retry(self, fn, *, what: str, deadline_s: float = 30.0):
        """Retry a statement that can lose an opening race between processes."""
        deadline = time.time() + deadline_s
        while True:
            try:
                return fn()
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc) and "busy" not in str(exc):
                    raise
                if time.time() > deadline:
                    raise DurableStoreError(f"db_busy: {what} after {deadline_s}s") from exc
                time.sleep(0.01)

    def close(self) -> None:
        self._db.close()

    # ── INBOX ───────────────────────────────────────────────────────────────

    def admit_event(self, *, provider: str, tenant_id: str, provider_event_id: str,
                    direction: str = "inbound", actor_id: Optional[str] = None,
                    payload_sha256: Optional[str] = None,
                    own_actor_ids: Iterable[str] = (), now: Optional[float] = None) -> Dict[str, Any]:
        """Persist tenant/provider event dedupe before any ACK.

        Returns {"admitted": bool, "reason": str, "row": dict}. admitted=True
        means this call created the row and the caller may serialise a decision.
        admitted=False means the provider event identity was already known (or
        the event is one of our own), so the effect already happened once.
        """
        _str(provider, "provider")
        _str(tenant_id, "tenant_id")
        _str(provider_event_id, "provider_event_id")
        _str(direction, "direction")
        _str(actor_id, "actor_id", allow_none=True)
        _str(payload_sha256, "payload_sha256", allow_none=True)
        ts = _ts(now)

        own = {str(a) for a in own_actor_ids}
        excluded: Optional[str] = None
        if direction != "inbound":
            excluded = f"excluded:direction={direction}"
        elif actor_id is not None and actor_id in own:
            excluded = "excluded:own_actor"

        with _Tx(self._db) as cur:
            existing = cur.execute(
                "SELECT * FROM inbox_events WHERE provider=? AND tenant_id=?"
                " AND provider_event_id=?",
                (provider, tenant_id, provider_event_id),
            ).fetchone()
            if existing is not None:
                # Identity dedupe: the SAME provider event never has a second effect.
                return {"admitted": False, "reason": "duplicate",
                        "row": dict(existing)}
            if excluded is not None:
                cur.execute(
                    "INSERT INTO inbox_events (provider, tenant_id, provider_event_id,"
                    " direction, actor_id, payload_sha256, state, received_at,"
                    " admitted_at, decided_at, decision_ref)"
                    " VALUES (?,?,?,?,?,?,?,?,NULL,?,?)",
                    (provider, tenant_id, provider_event_id, direction, actor_id,
                     payload_sha256, "decided", ts, ts, excluded),
                )
                return {"admitted": False, "reason": excluded,
                        "row": self._inbox_row(cur, provider, tenant_id, provider_event_id)}
            cur.execute(
                "INSERT INTO inbox_events (provider, tenant_id, provider_event_id,"
                " direction, actor_id, payload_sha256, state, received_at,"
                " admitted_at, decided_at, decision_ref)"
                " VALUES (?,?,?,?,?,?,?,?,?,NULL,NULL)",
                (provider, tenant_id, provider_event_id, direction, actor_id,
                 payload_sha256, "admitted", ts, ts),
            )
            return {"admitted": True, "reason": "admitted",
                    "row": self._inbox_row(cur, provider, tenant_id, provider_event_id)}

    def _inbox_row(self, cur: sqlite3.Cursor, provider: str, tenant_id: str,
                   provider_event_id: str) -> Dict[str, Any]:
        row = cur.execute(
            "SELECT * FROM inbox_events WHERE provider=? AND tenant_id=?"
            " AND provider_event_id=?",
            (provider, tenant_id, provider_event_id),
        ).fetchone()
        if row is None:
            raise DurableStoreError("unknown inbox event")
        return dict(row)

    def claim_decision(self, *, provider: str, tenant_id: str,
                       provider_event_id: str, now: Optional[float] = None) -> bool:
        """Atomically move admitted -> deciding. Exactly one caller wins."""
        ts = _ts(now)
        with _Tx(self._db) as cur:
            cur.execute(
                "UPDATE inbox_events SET state='deciding' WHERE provider=?"
                " AND tenant_id=? AND provider_event_id=? AND state='admitted'",
                (provider, tenant_id, provider_event_id),
            )
            return cur.rowcount == 1

    def record_decision(self, *, provider: str, tenant_id: str,
                        provider_event_id: str, decision_ref: str,
                        now: Optional[float] = None) -> bool:
        _str(decision_ref, "decision_ref")
        ts = _ts(now)
        with _Tx(self._db) as cur:
            cur.execute(
                "UPDATE inbox_events SET state='decided', decided_at=?, decision_ref=?"
                " WHERE provider=? AND tenant_id=? AND provider_event_id=?"
                " AND state='deciding'",
                (ts, decision_ref, provider, tenant_id, provider_event_id),
            )
            return cur.rowcount == 1

    def inbox_row(self, *, provider: str, tenant_id: str,
                  provider_event_id: str) -> Dict[str, Any]:
        with _Tx(self._db) as cur:
            return self._inbox_row(cur, provider, tenant_id, provider_event_id)

    # ── OUTBOX: intent ──────────────────────────────────────────────────────

    def create_intent(self, *, logical_intent_key: str, idempotency_key: str,
                      tenant_id: str, scope: str, content_sha256: str,
                      purpose: Optional[str] = None,
                      canonical_contact_id: Optional[str] = None,
                      binding_revision: Optional[str] = None,
                      action_id: Optional[str] = None,
                      now: Optional[float] = None) -> Tuple[Dict[str, Any], bool]:
        """Create the durable action in not_requested. Returns (row, created).

        Repeating the same logical_intent_key or idempotency_key returns the
        existing row with created=False and writes nothing: a reprocessed
        request never mints a second action.
        """
        _str(logical_intent_key, "logical_intent_key")
        _str(idempotency_key, "idempotency_key")
        _str(tenant_id, "tenant_id")
        _str(content_sha256, "content_sha256")
        _str(purpose, "purpose", allow_none=True)
        _str(binding_revision, "binding_revision", allow_none=True)
        _str(canonical_contact_id, "canonical_contact_id", allow_none=True)
        if scope not in SCOPES:
            raise DurableStoreError(f"bad_input: scope {scope!r} not in {SCOPES}")
        # DATA-CONTRACTS section 2 variant rules, enforced by name.
        if scope == "public_placement" and canonical_contact_id is not None:
            raise DurableStoreError(
                "bad_input: public_placement takes no canonical_contact_id")
        if scope == "person_directed" and canonical_contact_id is None:
            raise DurableStoreError(
                "bad_input: person_directed requires canonical_contact_id")

        ts = _ts(now)
        with _Tx(self._db) as cur:
            for column, value in (("logical_intent_key", logical_intent_key),
                                  ("idempotency_key", idempotency_key)):
                row = cur.execute(
                    f"SELECT * FROM outbox_actions WHERE {column}=?", (value,)
                ).fetchone()
                if row is not None:
                    if row["logical_intent_key"] != logical_intent_key:
                        raise DurableStoreError(
                            "conflict: idempotency_key already used by another"
                            " logical intent")
                    return dict(row), False
            aid = action_id or ("act_" + uuid.uuid4().hex)
            _str(aid, "action_id")
            cur.execute(
                "INSERT INTO outbox_actions (action_id, logical_intent_key,"
                " idempotency_key, tenant_id, scope, purpose, canonical_contact_id,"
                " content_sha256, binding_revision, state, tries, fence, lease_owner,"
                " lease_expires_at, not_before, blocked_reason, cancel_reason,"
                " unknown_reason, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,0,0,NULL,NULL,NULL,NULL,NULL,NULL,?,?)",
                (aid, logical_intent_key, idempotency_key, tenant_id, scope, purpose,
                 canonical_contact_id, content_sha256, binding_revision,
                 STATE_NOT_REQUESTED, ts, ts),
            )
            return self._action(cur, aid), True

    def get_action(self, action_id: str) -> Dict[str, Any]:
        _str(action_id, "action_id")
        with _Tx(self._db) as cur:
            return self._action(cur, action_id)

    def action_by_intent(self, logical_intent_key: str) -> Optional[Dict[str, Any]]:
        _str(logical_intent_key, "logical_intent_key")
        with _Tx(self._db) as cur:
            row = cur.execute(
                "SELECT * FROM outbox_actions WHERE logical_intent_key=?",
                (logical_intent_key,),
            ).fetchone()
            return dict(row) if row is not None else None

    def _action(self, cur: sqlite3.Cursor, action_id: str) -> Dict[str, Any]:
        row = cur.execute(
            "SELECT * FROM outbox_actions WHERE action_id=?", (action_id,)
        ).fetchone()
        if row is None:
            raise DurableStoreError(f"unknown action_id {action_id!r}")
        return dict(row)

    # ── OUTBOX: queue ───────────────────────────────────────────────────────

    def queue(self, action_id: str, now: Optional[float] = None) -> Dict[str, Any]:
        """not_requested -> queued. Idempotent on an already-queued action."""
        ts = _ts(now)
        with _Tx(self._db) as cur:
            row = self._action(cur, action_id)
            if row["state"] == STATE_QUEUED:
                return row
            if row["state"] != STATE_NOT_REQUESTED:
                raise DurableStoreError(
                    f"illegal_transition: queue from {row['state']!r}")
            cur.execute(
                "UPDATE outbox_actions SET state='queued', updated_at=?"
                " WHERE action_id=? AND state='not_requested'",
                (ts, action_id),
            )
            return self._action(cur, action_id)

    # ── OUTBOX: dispatch lease and fence ────────────────────────────────────

    def claim_for_dispatch(self, action_id: str, worker_id: str, *,
                           now: Optional[float] = None,
                           lease_seconds: float = DEFAULT_LEASE_S) -> Optional[Dict[str, Any]]:
        """Take the dispatch lease. Returns a claim dict, or None if refused.

        Refused when: not queued (canceled/dispatched/terminal), not_before in
        the future, a live lease exists, or an unresolved attempt exists
        (a possibly-sent effect awaiting reconciliation).
        """
        _str(worker_id, "worker_id")
        ts = _ts(now)
        lease = float(lease_seconds)
        if lease <= 0:
            raise DurableStoreError("bad_input: lease_seconds must be > 0")
        with _Tx(self._db) as cur:
            cur.execute(
                "UPDATE outbox_actions SET lease_owner=?, lease_expires_at=?,"
                " tries=tries+1, fence=fence+1, updated_at=?"
                " WHERE action_id=? AND state='queued'"
                "   AND (not_before IS NULL OR not_before <= ?)"
                "   AND (lease_owner IS NULL OR lease_expires_at IS NULL"
                "        OR lease_expires_at <= ?)"
                "   AND NOT EXISTS (SELECT 1 FROM outbox_attempts a"
                "        WHERE a.action_id=? AND a.outcome IS NULL)",
                (worker_id, ts + lease, ts, action_id, ts, ts, action_id),
            )
            if cur.rowcount != 1:
                return None
            row = self._action(cur, action_id)
            return {"action": row, "fence": int(row["fence"]),
                    "tries": int(row["tries"]), "worker_id": worker_id,
                    "lease_expires_at": ts + lease}

    def release_lease(self, action_id: str, fence: int,
                      now: Optional[float] = None) -> bool:
        ts = _ts(now)
        with _Tx(self._db) as cur:
            cur.execute(
                "UPDATE outbox_actions SET lease_owner=NULL, lease_expires_at=NULL,"
                " updated_at=? WHERE action_id=? AND fence=? AND state='queued'",
                (ts, action_id, int(fence)),
            )
            return cur.rowcount == 1

    def begin_attempt(self, action_id: str, fence: int, worker_id: str, *,
                      now: Optional[float] = None) -> bool:
        """Commit the start of a real send, atomically against cancel and theft.

        One INSERT ... SELECT. Returns True only when this worker, at this
        fence, on a still-queued action with no other unresolved attempt,
        created the attempt row. False means NOTHING may be sent.
        """
        _str(worker_id, "worker_id")
        ts = _ts(now)
        with _Tx(self._db) as cur:
            cur.execute(
                "INSERT INTO outbox_attempts (action_id, attempt_no, fence,"
                " worker_id, started_at, ended_at, outcome)"
                " SELECT a.action_id, a.tries, a.fence, ?, ?, NULL, NULL"
                " FROM outbox_actions a"
                " WHERE a.action_id=? AND a.state='queued' AND a.fence=?"
                "   AND a.lease_owner=?"
                "   AND NOT EXISTS (SELECT 1 FROM outbox_attempts x"
                "        WHERE x.action_id=a.action_id AND x.outcome IS NULL)",
                (worker_id, ts, action_id, int(fence), worker_id),
            )
            return cur.rowcount == 1

    def begin_attempt_guarded(self, action_id: str, fence: int, worker_id: str,
                              *, pre_send: Optional[Any] = None,
                              epoch: Optional[Tuple[str, str, int]] = None,
                              now: Optional[float] = None) -> Tuple[bool, Optional[str]]:
        """begin_attempt with the guard evaluated inside the SAME transaction.

        The point-of-use check is not "just before the send" in wall-clock terms:
        it is inside the IMMEDIATE transaction that creates the attempt row, so
        no other writer can commit between the check and the commit that lets a
        send happen.

        pre_send() -> True/False, or (ok, reason). False rolls the attempt back.
        epoch=(tenant_id, canonical_contact_id, expected) adds a compare-and-swap
        on suppression_epochs to the INSERT itself: the attempt row is created
        only while the fence still reads `expected`. That closes the window even
        when the gate already decided ALLOW before the suppression landed.

        Returns (started, reason). started=False with a reason means the state
        changed under the gate: NOTHING may be sent. started=False with None is
        the ordinary not-queued/canceled/leased refusal.
        """
        _str(worker_id, "worker_id")
        ts = _ts(now)
        if epoch is not None:
            if (not isinstance(epoch, tuple) or len(epoch) != 3
                    or not all(isinstance(part, str) for part in epoch[:2])
                    or not isinstance(epoch[2], int)):
                raise DurableStoreError(
                    "bad_input: epoch must be (tenant_id, contact, int)")
        try:
            with _Tx(self._db) as cur:
                has_fence = cur.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table'"
                    " AND name='suppression_epochs'").fetchone() is not None
                sql = (
                    "INSERT INTO outbox_attempts (action_id, attempt_no, fence,"
                    " worker_id, started_at, ended_at, outcome)"
                    " SELECT a.action_id, a.tries, a.fence, ?, ?, NULL, NULL"
                    " FROM outbox_actions a"
                    " WHERE a.action_id=? AND a.state='queued' AND a.fence=?"
                    "   AND a.lease_owner=?"
                    "   AND NOT EXISTS (SELECT 1 FROM outbox_attempts x"
                    "        WHERE x.action_id=a.action_id AND x.outcome IS NULL)")
                params: Tuple[Any, ...] = (worker_id, ts, action_id, int(fence),
                                           worker_id)
                if epoch is not None:
                    if has_fence:
                        sql += (" AND (SELECT COALESCE(MAX(epoch), 0)"
                                " FROM suppression_epochs WHERE tenant_id=?"
                                " AND canonical_contact_id=?)=?")
                        params += (epoch[0], epoch[1], int(epoch[2]))
                    else:
                        # No fence table means no suppression was ever durable
                        # in this database: only the never-suppressed epoch
                        # (0) may proceed. Anything else fails closed.
                        sql += " AND ?=0"
                        params += (int(epoch[2]),)
                cur.execute(sql, params)
                if cur.rowcount != 1:
                    if epoch is not None and has_fence:
                        moved = cur.execute(
                            "SELECT COALESCE(MAX(epoch), 0) AS e"
                            " FROM suppression_epochs WHERE tenant_id=?"
                            " AND canonical_contact_id=?",
                            (epoch[0], epoch[1])).fetchone()["e"]
                        if int(moved) != int(epoch[2]):
                            # A suppression committed after the fence token was
                            # read: say so, so the caller blocks rather than
                            # reporting an ordinary lease race.
                            return (False, "suppression_epoch_moved:%s->%s"
                                    % (epoch[2], moved))
                    return (False, None)
                if pre_send is None:
                    return (True, None)
                decision = pre_send()
                if isinstance(decision, tuple):
                    ok = bool(decision[0])
                    reason = str(decision[1]) if len(decision) > 1 else "pre_send"
                else:
                    ok = bool(decision)
                    reason = "pre_send"
                if not ok:
                    # Roll back: the attempt row must not survive a refusal.
                    raise _PreSendBlocked(reason)
                return (True, None)
        except _PreSendBlocked as blocked:
            return (False, str(blocked))

    # ── OUTBOX: outcomes ────────────────────────────────────────────────────

    def record_dispatch(self, action_id: str, fence: int, receipt: Dict[str, Any], *,
                        now: Optional[float] = None) -> Dict[str, Any]:
        """Persist provider admission for the attempt begun at this fence.

        queued -> dispatched. Provider admission is NOT completion; ack is a
        separate receipt and completion is separate again.
        """
        _validate_receipt(receipt)
        ts = _ts(now)
        with _Tx(self._db) as cur:
            row = self._action(cur, action_id)
            if row["state"] != STATE_QUEUED:
                raise DurableStoreError(
                    f"illegal_transition: record_dispatch from {row['state']!r}")
            cur.execute(
                "UPDATE outbox_actions SET state='dispatched', lease_owner=NULL,"
                " lease_expires_at=NULL, updated_at=?"
                " WHERE action_id=? AND state='queued' AND fence=?"
                "   AND EXISTS (SELECT 1 FROM outbox_attempts a WHERE"
                "        a.action_id=? AND a.attempt_no=outbox_actions.tries"
                "        AND a.outcome IS NULL)",
                (ts, action_id, int(fence), action_id),
            )
            if cur.rowcount != 1:
                raise DurableStoreError(
                    "stale_fence: attempt not open for this fence")
            self._attempt_close(cur, action_id, "dispatched", ts)
            self._receipt(cur, action_id, "dispatch", receipt, ts)
            return self._action(cur, action_id)

    def mark_attempt_unknown(self, action_id: str, fence: int, reason: str, *,
                             now: Optional[float] = None) -> Dict[str, Any]:
        """No verdict came back (timeout / exception). queued -> unknown.

        The attempt stays recorded; it is the evidence that a send MAY have
        happened. state=unknown blocks every future claim until reconciliation.
        """
        _str(reason, "reason")
        ts = _ts(now)
        with _Tx(self._db) as cur:
            row = self._action(cur, action_id)
            if row["state"] not in (STATE_QUEUED, STATE_DISPATCHED):
                raise DurableStoreError(
                    f"illegal_transition: mark unknown from {row['state']!r}")
            cur.execute(
                "UPDATE outbox_actions SET state='unknown', lease_owner=NULL,"
                " lease_expires_at=NULL, unknown_reason=?, updated_at=?"
                " WHERE action_id=? AND state IN ('queued','dispatched')"
                "   AND fence=?",
                (reason, ts, action_id, int(fence)),
            )
            if cur.rowcount != 1:
                raise DurableStoreError("stale_fence: cannot mark unknown")
            self._attempt_close(cur, action_id, "unknown", ts)
            return self._action(cur, action_id)

    def mark_gate_unknown(self, action_id: str, reason: str, *,
                          now: Optional[float] = None) -> Dict[str, Any]:
        """Gate returned RECONCILE_UNKNOWN: park the action for reconciliation."""
        _str(reason, "reason")
        ts = _ts(now)
        with _Tx(self._db) as cur:
            row = self._action(cur, action_id)
            if row["state"] != STATE_QUEUED:
                raise DurableStoreError(
                    f"illegal_transition: gate unknown from {row['state']!r}")
            cur.execute(
                "UPDATE outbox_actions SET state='unknown', lease_owner=NULL,"
                " lease_expires_at=NULL, unknown_reason=?, updated_at=?"
                " WHERE action_id=? AND state='queued'",
                (reason, ts, action_id),
            )
            return self._action(cur, action_id)

    def record_ack(self, action_id: str, receipt: Dict[str, Any], *,
                   now: Optional[float] = None) -> Dict[str, Any]:
        """dispatched -> acknowledged. A stop ACK is not completion."""
        _validate_receipt(receipt)
        ts = _ts(now)
        with _Tx(self._db) as cur:
            row = self._action(cur, action_id)
            if row["state"] == STATE_ACKNOWLEDGED:
                return row
            if row["state"] != STATE_DISPATCHED:
                raise DurableStoreError(
                    f"illegal_transition: ack from {row['state']!r}")
            cur.execute(
                "UPDATE outbox_actions SET state='acknowledged', updated_at=?"
                " WHERE action_id=? AND state='dispatched'", (ts, action_id),
            )
            self._receipt(cur, action_id, "ack", receipt, ts)
            return self._action(cur, action_id)

    def record_completion(self, action_id: str, receipt: Dict[str, Any], *,
                          now: Optional[float] = None) -> Dict[str, Any]:
        """acknowledged -> completed. Refused without a persisted ack receipt."""
        _validate_receipt(receipt)
        ts = _ts(now)
        with _Tx(self._db) as cur:
            row = self._action(cur, action_id)
            if row["state"] == STATE_COMPLETED:
                return row
            if row["state"] != STATE_ACKNOWLEDGED:
                raise DurableStoreError(
                    f"illegal_transition: completion from {row['state']!r}"
                    " (an ACK is not completion)")
            ack = cur.execute(
                "SELECT 1 FROM outbox_receipts WHERE action_id=? AND kind='ack'",
                (action_id,),
            ).fetchone()
            if ack is None:
                raise DurableStoreError(
                    "illegal_transition: completion without a persisted ack receipt")
            cur.execute(
                "UPDATE outbox_actions SET state='completed', updated_at=?"
                " WHERE action_id=? AND state='acknowledged'", (ts, action_id),
            )
            self._receipt(cur, action_id, "completion", receipt, ts)
            return self._action(cur, action_id)

    def mark_failed(self, action_id: str, reason: str, *,
                    now: Optional[float] = None) -> Dict[str, Any]:
        """Known nonexecution only. Never call this on an unknown outcome."""
        _str(reason, "reason")
        ts = _ts(now)
        with _Tx(self._db) as cur:
            row = self._action(cur, action_id)
            if row["state"] not in (STATE_QUEUED, STATE_DISPATCHED):
                raise DurableStoreError(
                    f"illegal_transition: failed from {row['state']!r}")
            cur.execute(
                "UPDATE outbox_actions SET state='failed', lease_owner=NULL,"
                " lease_expires_at=NULL, blocked_reason=?, updated_at=?"
                " WHERE action_id=? AND state IN ('queued','dispatched')",
                (reason, ts, action_id),
            )
            self._attempt_close(cur, action_id, "failed_nonexecution", ts)
            return self._action(cur, action_id)

    def cancel(self, action_id: str, reason: str, *,
               now: Optional[float] = None) -> Dict[str, Any]:
        """Cancel a not-yet-dispatched action. Refuses once a send may have begun."""
        _str(reason, "reason")
        ts = _ts(now)
        with _Tx(self._db) as cur:
            row = self._action(cur, action_id)
            if row["state"] == STATE_CANCELED:
                return row
            if row["state"] not in (STATE_NOT_REQUESTED, STATE_QUEUED):
                raise DurableStoreError(
                    f"illegal_transition: cancel from {row['state']!r}")
            cur.execute(
                "UPDATE outbox_actions SET state='canceled', lease_owner=NULL,"
                " lease_expires_at=NULL, cancel_reason=?, updated_at=?"
                " WHERE action_id=? AND state IN ('not_requested','queued')"
                "   AND NOT EXISTS (SELECT 1 FROM outbox_attempts a"
                "        WHERE a.action_id=? AND a.outcome IS NULL)",
                (reason, ts, action_id, action_id),
            )
            if cur.rowcount != 1:
                raise DurableStoreError(
                    "in_flight: a dispatch attempt already began; cancellation"
                    " cannot un-send it")
            return self._action(cur, action_id)

    def apply_gate_block(self, action_id: str, state: str, reason: str, *,
                         now: Optional[float] = None) -> Dict[str, Any]:
        """Persist a terminal gate block (suppressed / quarantined)."""
        if state not in (STATE_SUPPRESSED, STATE_QUARANTINED):
            raise DurableStoreError(f"bad_input: not a gate block state {state!r}")
        _str(reason, "reason")
        ts = _ts(now)
        with _Tx(self._db) as cur:
            cur.execute(
                "UPDATE outbox_actions SET state=?, lease_owner=NULL,"
                " lease_expires_at=NULL, blocked_reason=?, updated_at=?"
                " WHERE action_id=? AND state IN ('not_requested','queued')",
                (state, reason, ts, action_id),
            )
            if cur.rowcount != 1:
                raise DurableStoreError("illegal_transition: cannot gate-block now")
            return self._action(cur, action_id)

    def set_not_before(self, action_id: str, until: float, *,
                       now: Optional[float] = None) -> Dict[str, Any]:
        """Persist WAIT_UNTIL: stays queued, but no claim before `until`."""
        ts = _ts(now)
        with _Tx(self._db) as cur:
            cur.execute(
                "UPDATE outbox_actions SET not_before=?, blocked_reason='wait_until',"
                " lease_owner=NULL, lease_expires_at=NULL, updated_at=?"
                " WHERE action_id=? AND state='queued'",
                (float(until), ts, action_id),
            )
            if cur.rowcount != 1:
                raise DurableStoreError("illegal_transition: cannot set not_before now")
            return self._action(cur, action_id)

    def mark_dead_inflight_unknown(self, reason: str = "crash_during_send", *,
                                   now: Optional[float] = None) -> List[str]:
        """Startup sweep: a lease died with an attempt still open -> unknown.

        Only touches state='queued' rows whose lease is gone and whose attempt
        has no outcome. The attempt is NOT closed: it is the evidence that a
        send may have happened, so the action stays unclaimable until
        reconciliation resolves it. Never sends anything. Returns the ids.
        """
        _str(reason, "reason")
        ts = _ts(now)
        with _Tx(self._db) as cur:
            rows = cur.execute(
                "SELECT a.action_id FROM outbox_actions a"
                " WHERE a.state='queued'"
                "   AND (a.lease_expires_at IS NULL OR a.lease_expires_at <= ?)"
                "   AND EXISTS (SELECT 1 FROM outbox_attempts x"
                "        WHERE x.action_id=a.action_id AND x.outcome IS NULL)",
                (ts,),
            ).fetchall()
            ids = [r["action_id"] for r in rows]
            for aid in ids:
                cur.execute(
                    "UPDATE outbox_actions SET state='unknown', lease_owner=NULL,"
                    " lease_expires_at=NULL, unknown_reason=?, updated_at=?"
                    " WHERE action_id=? AND state='queued'",
                    (reason, ts, aid),
                )
            return ids

    def queued_with_open_attempt(self, *, now: Optional[float] = None) -> List[str]:
        """Actions whose worker may have died mid-send (read-only)."""
        ts = _ts(now)
        with _Tx(self._db) as cur:
            return [r["action_id"] for r in cur.execute(
                "SELECT a.action_id FROM outbox_actions a"
                " WHERE a.state='queued'"
                "   AND (a.lease_expires_at IS NULL OR a.lease_expires_at <= ?)"
                "   AND EXISTS (SELECT 1 FROM outbox_attempts x"
                "        WHERE x.action_id=a.action_id AND x.outcome IS NULL)",
                (ts,)).fetchall()]

    def _attempt_close(self, cur: sqlite3.Cursor, action_id: str,
                       outcome: str, ts: float) -> None:
        cur.execute(
            "UPDATE outbox_attempts SET ended_at=?, outcome=?"
            " WHERE action_id=? AND outcome IS NULL", (ts, outcome, action_id),
        )

    def _receipt(self, cur: sqlite3.Cursor, action_id: str, kind: str,
                 receipt: Dict[str, Any], ts: float) -> None:
        if kind not in RECEIPT_KINDS:
            raise DurableStoreError(f"bad_input: receipt kind {kind!r}")
        cur.execute(
            "INSERT OR REPLACE INTO outbox_receipts (action_id, kind, provider,"
            " provider_receipt_id, payload_json, received_at)"
            " VALUES (?,?,?,?,?,?)",
            (action_id, kind, receipt.get("provider"),
             receipt.get("provider_receipt_id"),
             json.dumps(receipt, sort_keys=True, separators=(",", ":")), ts),
        )

    def receipts(self, action_id: str) -> Dict[str, Dict[str, Any]]:
        _str(action_id, "action_id")
        with _Tx(self._db) as cur:
            rows = cur.execute(
                "SELECT * FROM outbox_receipts WHERE action_id=?", (action_id,)
            ).fetchall()
            return {r["kind"]: {**dict(r), "payload": json.loads(r["payload_json"])}
                    for r in rows}

    def attempts(self, action_id: str) -> List[Dict[str, Any]]:
        _str(action_id, "action_id")
        with _Tx(self._db) as cur:
            return [dict(r) for r in cur.execute(
                "SELECT * FROM outbox_attempts WHERE action_id=?"
                " ORDER BY attempt_no", (action_id,)).fetchall()]

    def unresolved_attempt(self, action_id: str) -> Optional[Dict[str, Any]]:
        with _Tx(self._db) as cur:
            row = cur.execute(
                "SELECT * FROM outbox_attempts WHERE action_id=?"
                " AND outcome IS NULL ORDER BY attempt_no DESC LIMIT 1",
                (action_id,),
            ).fetchone()
            return dict(row) if row is not None else None

    # ── GATE EVIDENCE (one row per attempt, never reusable) ─────────────────

    def record_gate_check(self, action_id: str, attempt_no: int,
                          verdict: Dict[str, Any], *, now: Optional[float] = None) -> None:
        ts = _ts(now)
        with _Tx(self._db) as cur:
            try:
                cur.execute(
                    "INSERT INTO gate_checks (action_id, attempt_no, verdict,"
                    " checked_at, binding_revision, policy_revision, fence,"
                    " evidence_json) VALUES (?,?,?,?,?,?,?,?)",
                    (action_id, int(attempt_no), verdict["verdict"],
                     float(verdict.get("checked_at", ts)),
                     verdict.get("binding_revision"),
                     verdict.get("policy_revision"),
                     verdict.get("fence"),
                     json.dumps(verdict.get("evidence") or {},
                                sort_keys=True, separators=(",", ":"))),
                )
            except sqlite3.IntegrityError as exc:
                raise DurableStoreError(
                    f"gate_reuse: attempt {attempt_no} already has a verdict"
                    " (a gate is never reused across attempts)") from exc

    def gate_checks(self, action_id: str) -> List[Dict[str, Any]]:
        _str(action_id, "action_id")
        with _Tx(self._db) as cur:
            return [dict(r) for r in cur.execute(
                "SELECT * FROM gate_checks WHERE action_id=? ORDER BY attempt_no",
                (action_id,)).fetchall()]

    # ── RECONCILIATION EVIDENCE ─────────────────────────────────────────────

    def reconcile_applied(self, action_id: str, receipt: Dict[str, Any], *,
                          now: Optional[float] = None) -> Dict[str, Any]:
        """Provider evidence says the effect EXISTS. Never sends anything.

        queued-with-dangling-attempt or unknown -> acknowledged, with the
        dispatch receipt persisted from provider evidence and a separate ack
        receipt. dispatched -> acknowledged (only the ack was missing).
        Completion stays separate and is NOT claimed here.
        """
        _validate_receipt(receipt)
        ts = _ts(now)
        with _Tx(self._db) as cur:
            row = self._action(cur, action_id)
            state = row["state"]
            if state == STATE_DISPATCHED:
                cur.execute(
                    "UPDATE outbox_actions SET state='acknowledged',"
                    " unknown_reason=NULL, updated_at=?"
                    " WHERE action_id=? AND state='dispatched'", (ts, action_id))
                if cur.rowcount != 1:
                    raise DurableStoreError("illegal_transition: ack after reconcile")
                self._receipt(cur, action_id, "ack", receipt, ts)
                return self._action(cur, action_id)
            if state not in (STATE_QUEUED, STATE_UNKNOWN):
                raise DurableStoreError(
                    f"illegal_transition: reconcile applied from {state!r}")
            cur.execute(
                "UPDATE outbox_actions SET state='acknowledged',"
                " lease_owner=NULL, lease_expires_at=NULL, unknown_reason=NULL,"
                " updated_at=? WHERE action_id=? AND state IN ('queued','unknown')",
                (ts, action_id))
            if cur.rowcount != 1:
                raise DurableStoreError("illegal_transition: reconcile applied lost race")
            self._attempt_close(cur, action_id, "applied_after_reconcile", ts)
            self._receipt(cur, action_id, "dispatch", receipt, ts)
            self._receipt(cur, action_id, "ack", receipt, ts)
            return self._action(cur, action_id)

    def reconcile_not_applied(self, action_id: str, *,
                              now: Optional[float] = None) -> Dict[str, Any]:
        """Provider evidence says the effect does NOT exist.

        Back to queued under the SAME action identity. The next dispatch runs a
        fresh gate; no identity is minted and nothing is sent from here.
        """
        ts = _ts(now)
        with _Tx(self._db) as cur:
            row = self._action(cur, action_id)
            if row["state"] not in (STATE_QUEUED, STATE_UNKNOWN):
                raise DurableStoreError(
                    f"illegal_transition: reconcile not_applied from {row['state']!r}")
            cur.execute(
                "UPDATE outbox_actions SET state='queued', lease_owner=NULL,"
                " lease_expires_at=NULL, unknown_reason=NULL, not_before=NULL,"
                " blocked_reason='reconciled_not_applied', updated_at=?"
                " WHERE action_id=? AND state IN ('queued','unknown')", (ts, action_id))
            if cur.rowcount != 1:
                raise DurableStoreError("illegal_transition: reconcile requeue lost race")
            self._attempt_close(cur, action_id, "not_applied_after_reconcile", ts)
            return self._action(cur, action_id)

    def mark_reconcile_unknown(self, action_id: str, reason: str, *,
                               now: Optional[float] = None) -> Dict[str, Any]:
        """Unresolved. State stays unknown and any attempt stays OPEN, so no
        worker can claim the action and resend."""
        _str(reason, "reason")
        ts = _ts(now)
        with _Tx(self._db) as cur:
            cur.execute(
                "UPDATE outbox_actions SET state='unknown', lease_owner=NULL,"
                " lease_expires_at=NULL, unknown_reason=?, updated_at=?"
                " WHERE action_id=? AND state IN ('queued','dispatched','unknown')",
                (reason, ts, action_id))
            if cur.rowcount != 1:
                raise DurableStoreError("illegal_transition: cannot park as unknown")
            return self._action(cur, action_id)

    def record_reconciliation(self, action_id: str, outcome: str,
                              evidence: Dict[str, Any], *,
                              now: Optional[float] = None) -> int:
        _str(outcome, "outcome")
        ts = _ts(now)
        with _Tx(self._db) as cur:
            nxt = cur.execute(
                "SELECT COALESCE(MAX(run_no),0)+1 AS n FROM reconciliation_runs"
                " WHERE action_id=?", (action_id,)).fetchone()["n"]
            cur.execute(
                "INSERT INTO reconciliation_runs (action_id, run_no, outcome,"
                " observed_at, evidence_json) VALUES (?,?,?,?,?)",
                (action_id, int(nxt), outcome, ts,
                 json.dumps(evidence, sort_keys=True, separators=(",", ":"))),
            )
            return int(nxt)

    def reconciliation_runs(self, action_id: str) -> List[Dict[str, Any]]:
        _str(action_id, "action_id")
        with _Tx(self._db) as cur:
            return [dict(r) for r in cur.execute(
                "SELECT * FROM reconciliation_runs WHERE action_id=?"
                " ORDER BY run_no", (action_id,)).fetchall()]

    # ── observation helpers ─────────────────────────────────────────────────

    # -- H8: the permanent per-tenant keyword registry ---------------------
    def register_keyword(self, *, tenant_id: str, keyword_norm: str,
                         promised_item_version: str, first_cycle_id: str,
                         now: Optional[float] = None) -> bool:
        """First use records the mapping; a repeat against another item is refused.

        The row is a tombstone: ``retired_at`` is set when a keyword leaves service,
        and it is never deleted, so an old keyword can never be recycled onto a
        different promised item. Returns True when the mapping holds (fresh or the
        same item), False when it names a different item.
        """
        ts = _ts(now)

        def fn() -> bool:
            cur = self._db.execute(
                "SELECT promised_item_version, retired_at FROM keyword_mappings"
                " WHERE tenant_id = ? AND keyword_norm = ?", (tenant_id, keyword_norm))
            row = cur.fetchone()
            if row is None:
                self._db.execute(
                    "INSERT INTO keyword_mappings (tenant_id, keyword_norm,"
                    " promised_item_version, first_cycle_id, first_seen_ts, retired_at)"
                    " VALUES (?, ?, ?, ?, ?, NULL)",
                    (tenant_id, keyword_norm, promised_item_version, first_cycle_id, ts))
                self._db.commit()
                return True
            version, retired_at = row[0], row[1]
            if retired_at is None and version != promised_item_version:
                return False
            return True

        return self._retry(fn, what="register_keyword")

    def keyword_item(self, tenant_id: str, keyword_norm: str) -> Optional[Dict[str, Any]]:
        cur = self._db.execute(
            "SELECT tenant_id, keyword_norm, promised_item_version, first_cycle_id,"
            " first_seen_ts, retired_at FROM keyword_mappings"
            " WHERE tenant_id = ? AND keyword_norm = ?", (tenant_id, keyword_norm))
        row = cur.fetchone()
        if row is None:
            return None
        return {"tenant_id": row[0], "keyword_norm": row[1],
                "promised_item_version": row[2], "first_cycle_id": row[3],
                "first_seen_ts": row[4], "retired_at": row[5]}

    def keyword_rows(self, tenant_id: str) -> List[Dict[str, Any]]:
        cur = self._db.execute(
            "SELECT keyword_norm, promised_item_version, first_cycle_id, retired_at"
            " FROM keyword_mappings WHERE tenant_id = ? ORDER BY keyword_norm", (tenant_id,))
        return [{"keyword_norm": r[0], "promised_item_version": r[1],
                 "first_cycle_id": r[2], "retired_at": r[3]} for r in cur.fetchall()]

    def counts(self) -> Dict[str, int]:
        with _Tx(self._db) as cur:
            return {
                "inbox": cur.execute("SELECT COUNT(*) c FROM inbox_events").fetchone()["c"],
                "actions": cur.execute("SELECT COUNT(*) c FROM outbox_actions").fetchone()["c"],
                "attempts": cur.execute("SELECT COUNT(*) c FROM outbox_attempts").fetchone()["c"],
                "receipts": cur.execute("SELECT COUNT(*) c FROM outbox_receipts").fetchone()["c"],
                "gate_checks": cur.execute("SELECT COUNT(*) c FROM gate_checks").fetchone()["c"],
            }


def _validate_receipt(receipt: Dict[str, Any]) -> None:
    if not isinstance(receipt, dict) or not receipt:
        raise DurableStoreError("bad_input: receipt must be a non-empty dict")
    _str(receipt.get("provider"), "receipt.provider")


# ── assert-based self-check (stdlib only) ───────────────────────────────────

def _selfcheck() -> int:
    import tempfile
    from pathlib import Path

    d = Path(tempfile.mkdtemp(prefix="durstore-selfcheck-"))
    db = d / "store.sqlite"
    passed = 0

    def ok(cond: bool, label: str) -> None:
        nonlocal passed
        if not cond:
            raise AssertionError("FAIL: " + label)
        passed += 1

    s = DurableStore(str(db))
    a = s.admit_event(provider="ghl", tenant_id="t1", provider_event_id="e1",
                      payload_sha256="aa", now=100.0)
    b = s.admit_event(provider="ghl", tenant_id="t1", provider_event_id="e1",
                      payload_sha256="aa", now=101.0)
    c = s.admit_event(provider="ghl", tenant_id="t1", provider_event_id="e2",
                      payload_sha256="aa", now=102.0)
    ok(a["admitted"] is True, "first delivery admitted")
    ok(b["admitted"] is False and b["reason"] == "duplicate",
       "redelivery deduped on provider event identity")
    ok(c["admitted"] is True, "identical body, different event id is a new event")
    own = s.admit_event(provider="ghl", tenant_id="t1", provider_event_id="e3",
                        direction="outgoing", now=103.0)
    ok(own["admitted"] is False and own["reason"].startswith("excluded:"),
       "own outgoing excluded by direction")
    s.close()

    s = DurableStore(str(db))  # restart: durable state survives
    ok(s.admit_event(provider="ghl", tenant_id="t1", provider_event_id="e1")["admitted"]
       is False, "dedupe survives restart")
    ok(s.claim_decision(provider="ghl", tenant_id="t1", provider_event_id="e1") is True,
       "single decision claim")
    ok(s.claim_decision(provider="ghl", tenant_id="t1", provider_event_id="e1") is False,
       "second decision claim refused")

    row, created = s.create_intent(logical_intent_key="L1", idempotency_key="K1",
                                   tenant_id="t1", scope="person_directed",
                                   canonical_contact_id="c1", content_sha256="h",
                                   now=200.0)
    aid = row["action_id"]
    ok(created is True and row["state"] == STATE_NOT_REQUESTED, "intent created")
    row2, created2 = s.create_intent(logical_intent_key="L1", idempotency_key="K1",
                                     tenant_id="t1", scope="person_directed",
                                     canonical_contact_id="c1", content_sha256="h")
    ok(created2 is False and row2["action_id"] == aid, "same key never mints a second action")

    ok(s.queue(aid, now=201.0)["state"] == STATE_QUEUED, "queued")
    cl = s.claim_for_dispatch(aid, "w1", now=202.0, lease_seconds=30)
    ok(cl is not None and cl["fence"] == 1, "first claim wins with fence 1")
    ok(s.claim_for_dispatch(aid, "w2", now=202.5) is None, "live lease blocks second claim")
    ok(s.begin_attempt(aid, cl["fence"], "w1", now=202.6) is True, "attempt begins")
    ok(s.begin_attempt(aid, cl["fence"], "w1", now=202.7) is False,
       "second concurrent attempt refused")
    ok(s.record_dispatch(aid, cl["fence"], {"provider": "ghl",
                                            "provider_receipt_id": "r1"}, now=203.0)
       ["state"] == STATE_DISPATCHED, "dispatch receipt persisted")
    try:
        s.record_completion(aid, {"provider": "ghl", "provider_receipt_id": "r1"})
        ok(False, "completion without ack must raise")
    except DurableStoreError as exc:
        ok("ACK" in str(exc), "completion without ack refused")
    ok(s.record_ack(aid, {"provider": "ghl", "provider_receipt_id": "r1"})
       ["state"] == STATE_ACKNOWLEDGED, "ack receipt is separate")
    ok(s.record_completion(aid, {"provider": "ghl", "provider_receipt_id": "r1"})
       ["state"] == STATE_COMPLETED, "completion after ack")
    ok(set(s.receipts(aid)) == {"dispatch", "ack", "completion"},
       "three distinct receipts persisted")
    ok(s.claim_for_dispatch(aid, "w9", now=300.0) is None,
       "completed action never dispatches again")

    # cancellation before dispatch
    row, _ = s.create_intent(logical_intent_key="L2", idempotency_key="K2",
                             tenant_id="t1", scope="public_placement",
                             content_sha256="h2")
    aid2 = row["action_id"]
    s.queue(aid2)
    s.cancel(aid2, "stop", now=400.0)
    ok(s.claim_for_dispatch(aid2, "w1", now=401.0) is None,
       "canceled action cannot be claimed")

    s.close()
    print(f"OK {passed} PASS")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selfcheck())
