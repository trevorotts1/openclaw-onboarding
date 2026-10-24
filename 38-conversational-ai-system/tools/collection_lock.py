#!/usr/bin/env python3
"""Collection lock and durable capture cursor for Skill 38.

DATA-CONTRACTS 1: serialize at
(tenant_id, canonical_contact_id, collection_sequence_id). FB, IG and SMS
references share this lock; a conversation ID is a channel reference, not the
collection boundary.

The lock is a SQLite row guarded by BEGIN IMMEDIATE, so real parallel
processes contend on one writer. Guarantees:

  * exactly one collector holds the key; a second acquire is denied with
    reason "held" (defer) or blocks in acquire_or_wait;
  * every successful acquire advances a monotonic fence; a stale writer's
    fenced write is rejected, so a deferred loser cannot duplicate a send;
  * an expired lease is frozen as "reconcile_required". No successor may
    take over until reconcile() records the handover at the exact fence it
    observed; only then does the next acquire advance the fence.

CaptureStore keeps a capture's own cursor. begin() on an existing capture
returns it unchanged (resume, never restart), advance() refuses to rewind,
and a rejected capture stays rejected.

Tenant isolation is enforced by the module: acquire(), reconcile(), and every
CaptureStore entry point call TenantIdentity.verify() before touching a row,
so an unregistered tenant or another tenant's contact is rejected. Every
fenced write (record_effect, renew, release) re-validates owner, fence and
lease inside its own transaction.

Python 3 standard library only.
"""

import dataclasses
import json
import sqlite3
import time
from typing import Any, Dict, List, Optional

from tenant_identity import TenantIdentity, VerificationError

DEFAULT_LEASE_SECONDS = 60.0
DEFAULT_WAIT_SECONDS = 5.0
DEFAULT_POLL_SECONDS = 0.02

STATE_HELD = "held"
STATE_FREE = "free"
STATE_RECONCILE_REQUIRED = "reconcile_required"

CAPTURE_IN_PROGRESS = "in_progress"
CAPTURE_COMPLETE = "complete"
CAPTURE_REJECTED = "rejected"

SCHEMA = """
CREATE TABLE IF NOT EXISTS collection_locks (
    tenant_id            TEXT NOT NULL,
    canonical_contact_id TEXT NOT NULL,
    collection_sequence_id TEXT NOT NULL,
    owner_id             TEXT,
    fence                INTEGER NOT NULL DEFAULT 0,
    lease_expires_at     REAL,
    state                TEXT NOT NULL DEFAULT 'free',
    reconciled_at        REAL,
    reconciled_by        TEXT,
    updated_at           REAL NOT NULL,
    PRIMARY KEY (tenant_id, canonical_contact_id, collection_sequence_id)
);

CREATE TABLE IF NOT EXISTS collection_effects (
    tenant_id            TEXT NOT NULL,
    canonical_contact_id TEXT NOT NULL,
    collection_sequence_id TEXT NOT NULL,
    fence                INTEGER NOT NULL,
    effect_id            TEXT NOT NULL,
    recorded_at          REAL NOT NULL,
    PRIMARY KEY (tenant_id, canonical_contact_id,
                 collection_sequence_id, effect_id)
);

CREATE TABLE IF NOT EXISTS captures (
    tenant_id            TEXT NOT NULL,
    canonical_contact_id TEXT NOT NULL,
    collection_sequence_id TEXT NOT NULL,
    capture_id           TEXT NOT NULL,
    state                TEXT NOT NULL,
    cursor               INTEGER NOT NULL DEFAULT 0,
    steps_json           TEXT NOT NULL,
    data_json            TEXT NOT NULL DEFAULT '{}',
    rejection_reason     TEXT,
    updated_at           REAL NOT NULL,
    PRIMARY KEY (tenant_id, canonical_contact_id,
                 collection_sequence_id, capture_id)
);
"""


class LockError(Exception):
    """Base collection-lock error."""


class LockConflict(LockError):
    """The lock exists in a state that forbids the requested transition."""


class StaleWriter(LockError):
    """The caller's owner/fence no longer owns the lock."""


class CaptureError(Exception):
    """Base capture-state error."""


class CaptureConflict(CaptureError):
    """The capture cursor may not move backwards or restart."""


class CaptureRejected(CaptureError):
    """The capture is terminal-rejected and cannot advance."""


class CaptureComplete(CaptureError):
    """The capture is already complete and cannot advance."""


@dataclasses.dataclass(frozen=True)
class Lease:
    """Result of an acquire/renew/reconcile attempt."""

    granted: bool
    fence: int
    owner_id: Optional[str]
    reason: str
    retry_after: Optional[float] = None

    def __bool__(self) -> bool:
        return self.granted


def _key(tenant_id: str, canonical_contact_id: str, collection_sequence_id: str):
    parts = (tenant_id, canonical_contact_id, collection_sequence_id)
    for value in parts:
        if not isinstance(value, str) or not value.strip():
            raise LockError(
                "collection key requires tenant_id, canonical_contact_id and"
                " collection_sequence_id"
            )
    return tuple(part.strip() for part in parts)


def _require_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LockError("%s is required" % name)
    return value.strip()


class CollectionLock:
    """One collector per (tenant, canonical contact, collection sequence)."""

    def __init__(self, identity: TenantIdentity):
        if not isinstance(identity, TenantIdentity):
            raise TypeError("CollectionLock requires a TenantIdentity")
        self.identity = identity
        self.db_path = identity.db_path
        self.init_schema()

    # -- storage ---------------------------------------------------------

    def init_schema(self) -> None:
        conn = self.identity.connection()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = FULL")
            conn.executescript(SCHEMA)
        finally:
            conn.close()

    def _write(self):
        return self.identity.write_transaction()

    def _read(self):
        return self.identity.read_transaction()

    @staticmethod
    def _select(conn: sqlite3.Connection, key) -> Optional[sqlite3.Row]:
        return conn.execute(
            "SELECT fence, owner_id, lease_expires_at, state, reconciled_at"
            " FROM collection_locks"
            " WHERE tenant_id = ? AND canonical_contact_id = ?"
            " AND collection_sequence_id = ?",
            key,
        ).fetchone()

    # -- lock lifecycle --------------------------------------------------

    def acquire(
        self,
        tenant_id: str,
        canonical_contact_id: str,
        collection_sequence_id: str,
        owner_id: str,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
    ) -> Lease:
        """Try to become the collector. Never blocks; returns a Lease."""
        key = _key(tenant_id, canonical_contact_id, collection_sequence_id)
        owner_id = _require_id(owner_id, "owner_id")
        if lease_seconds is None or lease_seconds < 0:
            raise LockError("lease_seconds must be >= 0")
        # Module-enforced tenant isolation: unknown tenant or foreign contact
        # is rejected before a lock row is read or written.
        self.identity.verify(tenant_id, canonical_contact_id)

        now = time.time()
        with self._write() as conn:
            row = self._select(conn, key)
            if row is None:
                conn.execute(
                    "INSERT INTO collection_locks"
                    " (tenant_id, canonical_contact_id,"
                    "  collection_sequence_id, owner_id, fence,"
                    "  lease_expires_at, state, updated_at)"
                    " VALUES (?, ?, ?, ?, 1, ?, ?, ?)",
                    key + (owner_id, now + lease_seconds, STATE_HELD, now),
                )
                return Lease(True, 1, owner_id, "acquired")

            fence = int(row["fence"])
            owner = row["owner_id"]
            expires = row["lease_expires_at"]
            state = row["state"]

            if state == STATE_FREE:
                conn.execute(
                    "UPDATE collection_locks SET owner_id = ?, fence = ?,"
                    " lease_expires_at = ?, state = ?, reconciled_at = NULL,"
                    " reconciled_by = NULL, updated_at = ?"
                    " WHERE tenant_id = ? AND canonical_contact_id = ?"
                    " AND collection_sequence_id = ?",
                    (
                        owner_id,
                        fence + 1,
                        now + lease_seconds,
                        STATE_HELD,
                        now,
                    )
                    + key,
                )
                return Lease(True, fence + 1, owner_id, "acquired")

            if (
                state == STATE_HELD
                and owner == owner_id
                and expires is not None
                and expires > now
            ):
                conn.execute(
                    "UPDATE collection_locks SET lease_expires_at = ?,"
                    " updated_at = ? WHERE tenant_id = ?"
                    " AND canonical_contact_id = ?"
                    " AND collection_sequence_id = ?",
                    (now + lease_seconds, now) + key,
                )
                return Lease(True, fence, owner_id, "renewed")

            if state == STATE_HELD and expires is not None and expires > now:
                return Lease(
                    False, fence, None, "held", retry_after=expires - now
                )

            # Lease expired, or a previous reconcile_required is still open.
            # Freeze the row: the dead writer's in-flight effects must be
            # reconciled before any successor may write.
            if state != STATE_RECONCILE_REQUIRED:
                conn.execute(
                    "UPDATE collection_locks SET state = ?, owner_id = NULL,"
                    " lease_expires_at = NULL, updated_at = ?"
                    " WHERE tenant_id = ? AND canonical_contact_id = ?"
                    " AND collection_sequence_id = ?",
                    (STATE_RECONCILE_REQUIRED, now) + key,
                )
            return Lease(False, fence, None, "reconcile_required")

    def acquire_or_wait(
        self,
        tenant_id: str,
        canonical_contact_id: str,
        collection_sequence_id: str,
        owner_id: str,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
        timeout: float = DEFAULT_WAIT_SECONDS,
        poll_seconds: float = DEFAULT_POLL_SECONDS,
    ) -> Lease:
        """Block until granted, timeout, or reconciliation is required."""
        deadline = time.time() + max(0.0, timeout)
        while True:
            lease = self.acquire(
                tenant_id,
                canonical_contact_id,
                collection_sequence_id,
                owner_id,
                lease_seconds,
            )
            if lease.granted or lease.reason == "reconcile_required":
                return lease
            remaining = deadline - time.time()
            if remaining <= 0:
                return Lease(False, lease.fence, None, "deferred")
            delay = min(poll_seconds, remaining)
            if lease.retry_after is not None:
                delay = min(delay, max(lease.retry_after, 0.0))
            time.sleep(max(delay, 0.001))

    def renew(
        self,
        tenant_id: str,
        canonical_contact_id: str,
        collection_sequence_id: str,
        owner_id: str,
        fence: int,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
    ) -> Lease:
        key = _key(tenant_id, canonical_contact_id, collection_sequence_id)
        now = time.time()
        with self._write() as conn:
            self._assert_fence_locked(conn, key, owner_id, fence, now)
            conn.execute(
                "UPDATE collection_locks SET lease_expires_at = ?,"
                " updated_at = ? WHERE tenant_id = ? AND canonical_contact_id = ?"
                " AND collection_sequence_id = ?",
                (now + lease_seconds, now) + key,
            )
        return Lease(True, int(fence), owner_id, "renewed")

    def release(
        self,
        tenant_id: str,
        canonical_contact_id: str,
        collection_sequence_id: str,
        owner_id: str,
        fence: int,
    ) -> bool:
        key = _key(tenant_id, canonical_contact_id, collection_sequence_id)
        now = time.time()
        with self._write() as conn:
            row = self._select(conn, key)
            if row is None:
                return False
            self._assert_fence_locked(conn, key, owner_id, fence, now)
            conn.execute(
                "UPDATE collection_locks SET state = ?, owner_id = NULL,"
                " lease_expires_at = NULL, updated_at = ?"
                " WHERE tenant_id = ? AND canonical_contact_id = ?"
                " AND collection_sequence_id = ?",
                (STATE_FREE, now) + key,
            )
        return True

    def reconcile(
        self,
        tenant_id: str,
        canonical_contact_id: str,
        collection_sequence_id: str,
        owner_id: str,
        expected_fence: int,
    ) -> Lease:
        """Record a successor's handover of an expired lease.

        Requires the exact fence the successor observed. Only after this may
        acquire() issue fence + 1. The successor is expected to inspect the
        dead writer's receipts/effects here; the lock records that it did.
        """
        key = _key(tenant_id, canonical_contact_id, collection_sequence_id)
        owner_id = _require_id(owner_id, "owner_id")
        self.identity.verify(tenant_id, canonical_contact_id)
        now = time.time()
        with self._write() as conn:
            row = self._select(conn, key)
            if row is None:
                raise LockError("no lock record to reconcile")
            if row["state"] != STATE_RECONCILE_REQUIRED:
                raise LockConflict(
                    "lock is %r; reconciliation only applies to an expired"
                    " lease" % (row["state"],)
                )
            if int(expected_fence) != int(row["fence"]):
                raise StaleWriter(
                    "reconcile expected fence %s, lock is at %s"
                    % (expected_fence, row["fence"])
                )
            conn.execute(
                "UPDATE collection_locks SET state = ?, owner_id = NULL,"
                " lease_expires_at = NULL, reconciled_at = ?,"
                " reconciled_by = ?, updated_at = ?"
                " WHERE tenant_id = ? AND canonical_contact_id = ?"
                " AND collection_sequence_id = ?",
                (STATE_FREE, now, owner_id, now) + key,
            )
        return Lease(False, int(row["fence"]), None, "reconciled")

    # -- fenced writes ---------------------------------------------------

    def assert_fence(
        self,
        tenant_id: str,
        canonical_contact_id: str,
        collection_sequence_id: str,
        owner_id: str,
        fence: int,
    ) -> None:
        key = _key(tenant_id, canonical_contact_id, collection_sequence_id)
        with self._read() as conn:
            self._assert_fence_locked(conn, key, owner_id, fence, time.time())

    def record_effect(
        self,
        tenant_id: str,
        canonical_contact_id: str,
        collection_sequence_id: str,
        owner_id: str,
        fence: int,
        effect_id: str,
    ) -> bool:
        """Fenced, idempotent side-effect record.

        Re-validates the fence inside the write transaction, so a stale
        writer cannot add a duplicate effect. Returns False when effect_id
        was already recorded under this collection.
        """
        key = _key(tenant_id, canonical_contact_id, collection_sequence_id)
        effect_id = _require_id(effect_id, "effect_id")
        now = time.time()
        with self._write() as conn:
            self._assert_fence_locked(conn, key, owner_id, fence, now)
            try:
                conn.execute(
                    "INSERT INTO collection_effects"
                    " (tenant_id, canonical_contact_id,"
                    "  collection_sequence_id, fence, effect_id, recorded_at)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    key + (int(fence), effect_id, now),
                )
            except sqlite3.IntegrityError:
                return False
        return True

    @staticmethod
    def _assert_fence_locked(
        conn: sqlite3.Connection, key, owner_id: str, fence: int, now: float
    ) -> None:
        row = CollectionLock._select(conn, key)
        if row is None:
            raise StaleWriter("no lock record")
        if row["state"] != STATE_HELD:
            raise StaleWriter("lock is %r, not held" % (row["state"],))
        if row["owner_id"] != owner_id:
            raise StaleWriter(
                "lock is owned by %r, not %r" % (row["owner_id"], owner_id)
            )
        if int(row["fence"]) != int(fence):
            raise StaleWriter(
                "fence %s is stale; lock is at %s" % (fence, row["fence"])
            )
        if (
            row["lease_expires_at"] is None
            or row["lease_expires_at"] <= now
        ):
            raise StaleWriter("lease expired; reconcile before writing")


class CaptureStore:
    """Durable per-capture cursor. Partial failures resume, never restart."""

    def __init__(self, lock: CollectionLock):
        if not isinstance(lock, CollectionLock):
            raise TypeError("CaptureStore requires a CollectionLock")
        self.lock = lock
        self.identity = lock.identity
        self.db_path = lock.db_path

    @staticmethod
    def _select(conn, key, capture_id) -> Optional[sqlite3.Row]:
        return conn.execute(
            "SELECT state, cursor, steps_json, data_json, rejection_reason"
            " FROM captures WHERE tenant_id = ? AND canonical_contact_id = ?"
            " AND collection_sequence_id = ? AND capture_id = ?",
            key + (capture_id,),
        ).fetchone()

    @staticmethod
    def _as_dict(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "state": row["state"],
            "cursor": int(row["cursor"]),
            "steps": json.loads(row["steps_json"]),
            "data": json.loads(row["data_json"]),
            "rejection_reason": row["rejection_reason"],
        }

    def begin(
        self,
        tenant_id: str,
        canonical_contact_id: str,
        collection_sequence_id: str,
        capture_id: str,
        steps: List[str],
    ) -> Dict[str, Any]:
        """Create or resume. An existing capture is returned unchanged."""
        key = _key(tenant_id, canonical_contact_id, collection_sequence_id)
        capture_id = _require_id(capture_id, "capture_id")
        if not steps or not isinstance(steps, list):
            raise CaptureError("capture steps must be a non-empty list")
        self.identity.verify(tenant_id, canonical_contact_id)
        now = time.time()
        with self.lock._write() as conn:
            row = self._select(conn, key, capture_id)
            if row is not None:
                return self._as_dict(row)
            conn.execute(
                "INSERT INTO captures"
                " (tenant_id, canonical_contact_id, collection_sequence_id,"
                "  capture_id, state, cursor, steps_json, data_json,"
                "  rejection_reason, updated_at)"
                " VALUES (?, ?, ?, ?, ?, 0, ?, '{}', NULL, ?)",
                key + (capture_id, CAPTURE_IN_PROGRESS, json.dumps(steps), now),
            )
            return {
                "state": CAPTURE_IN_PROGRESS,
                "cursor": 0,
                "steps": list(steps),
                "data": {},
                "rejection_reason": None,
            }

    def advance(
        self,
        tenant_id: str,
        canonical_contact_id: str,
        collection_sequence_id: str,
        capture_id: str,
        step_index: int,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Move the cursor forward only. step_index is the count completed."""
        key = _key(tenant_id, canonical_contact_id, collection_sequence_id)
        capture_id = _require_id(capture_id, "capture_id")
        if not isinstance(step_index, int) or step_index < 0:
            raise CaptureError("step_index must be a non-negative integer")
        now = time.time()
        with self.lock._write() as conn:
            row = self._select(conn, key, capture_id)
            if row is None:
                raise CaptureError("unknown capture %r" % (capture_id,))
            if row["state"] == CAPTURE_REJECTED:
                raise CaptureRejected(
                    "capture rejected: %s" % (row["rejection_reason"],)
                )
            if row["state"] == CAPTURE_COMPLETE:
                raise CaptureComplete("capture already complete")
            steps = json.loads(row["steps_json"])
            if step_index <= int(row["cursor"]):
                raise CaptureConflict(
                    "capture cursor is %s; refusing to rewind or restart"
                    % (row["cursor"],)
                )
            if step_index > len(steps):
                raise CaptureError(
                    "step_index %s exceeds %s steps" % (step_index, len(steps))
                )
            merged = json.loads(row["data_json"])
            if data:
                merged.update(data)
            conn.execute(
                "UPDATE captures SET cursor = ?, data_json = ?, updated_at = ?"
                " WHERE tenant_id = ? AND canonical_contact_id = ?"
                " AND collection_sequence_id = ? AND capture_id = ?",
                (step_index, json.dumps(merged), now) + key + (capture_id,),
            )
            return {
                "state": CAPTURE_IN_PROGRESS,
                "cursor": step_index,
                "steps": steps,
                "data": merged,
                "rejection_reason": None,
            }

    def complete(
        self,
        tenant_id: str,
        canonical_contact_id: str,
        collection_sequence_id: str,
        capture_id: str,
    ) -> Dict[str, Any]:
        return self._set_terminal(
            tenant_id,
            canonical_contact_id,
            collection_sequence_id,
            capture_id,
            CAPTURE_COMPLETE,
            None,
        )

    def reject(
        self,
        tenant_id: str,
        canonical_contact_id: str,
        collection_sequence_id: str,
        capture_id: str,
        reason: str = "",
    ) -> Dict[str, Any]:
        return self._set_terminal(
            tenant_id,
            canonical_contact_id,
            collection_sequence_id,
            capture_id,
            CAPTURE_REJECTED,
            reason or "",
        )

    def _set_terminal(
        self, tenant_id, canonical_contact_id, collection_sequence_id,
        capture_id, state, reason,
    ) -> Dict[str, Any]:
        key = _key(tenant_id, canonical_contact_id, collection_sequence_id)
        capture_id = _require_id(capture_id, "capture_id")
        now = time.time()
        with self.lock._write() as conn:
            row = self._select(conn, key, capture_id)
            if row is None:
                raise CaptureError("unknown capture %r" % (capture_id,))
            if row["state"] == CAPTURE_REJECTED:
                return self._as_dict(row)
            if row["state"] == CAPTURE_COMPLETE:
                raise CaptureComplete("capture already complete")
            conn.execute(
                "UPDATE captures SET state = ?, rejection_reason = ?,"
                " updated_at = ? WHERE tenant_id = ? AND"
                " canonical_contact_id = ? AND collection_sequence_id = ?"
                " AND capture_id = ?",
                (state, reason, now) + key + (capture_id,),
            )
            return {
                "state": state,
                "cursor": int(row["cursor"]),
                "steps": json.loads(row["steps_json"]),
                "data": json.loads(row["data_json"]),
                "rejection_reason": reason,
            }

    def get(
        self,
        tenant_id: str,
        canonical_contact_id: str,
        collection_sequence_id: str,
        capture_id: str,
    ) -> Optional[Dict[str, Any]]:
        key = _key(tenant_id, canonical_contact_id, collection_sequence_id)
        self.identity.verify(tenant_id, canonical_contact_id)
        with self.lock._read() as conn:
            row = self._select(conn, key, _require_id(capture_id, "capture_id"))
        return self._as_dict(row) if row is not None else None
