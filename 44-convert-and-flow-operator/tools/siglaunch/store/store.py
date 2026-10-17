"""S44-05 durable tenant-scoped store (production design implementation).

Implements DESIGN-S44-02-03-05-v1.md section 3: a single SQLite database
(WAL mode) carrying the inbox, the action ledger, the request store, and
cross-box leases with fencing tokens.

Semantics are identical to the L1 reference model (work/events/events.py):
  - inbox key:  (tenant_id, provider, verified event_id)
  - action key: (tenant_id, transaction_ref or order_ref, native_line_ref,
                 action_type, entitlement/campaign version)
  - uniqueness is enforced by PRIMARY KEY constraints, never check-then-act
  - claims are atomic: exactly one winner per action key, across threads
    AND processes
  - unknown external outcomes park the action (state=unknown) and block
    replay until reconciled against native state

No secrets are stored in this database. Tenant scoping is part of every key.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

_SCHEMA = """
CREATE TABLE IF NOT EXISTS inbox_events (
    tenant_id  TEXT NOT NULL,
    provider   TEXT NOT NULL,
    event_id   TEXT NOT NULL,
    event_json TEXT NOT NULL,
    received_at REAL NOT NULL,
    PRIMARY KEY (tenant_id, provider, event_id)
);
CREATE TABLE IF NOT EXISTS actions (
    tenant_id      TEXT NOT NULL,
    txn_ref        TEXT NOT NULL,
    line_ref       TEXT NOT NULL,
    action_type    TEXT NOT NULL,
    version        TEXT NOT NULL,
    state          TEXT NOT NULL DEFAULT 'claimed',
    payload_json   TEXT NOT NULL DEFAULT '{}',
    evidence_ref   TEXT,
    updated_at     REAL NOT NULL,
    PRIMARY KEY (tenant_id, txn_ref, line_ref, action_type, version)
);
CREATE TABLE IF NOT EXISTS requests (
    request_id      TEXT NOT NULL PRIMARY KEY,
    request_version INTEGER NOT NULL,
    tenant_id       TEXT NOT NULL,
    state           TEXT NOT NULL,
    receipt_json    TEXT,
    updated_at      REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS leases (
    tenant_id     TEXT NOT NULL,
    resource      TEXT NOT NULL,
    holder        TEXT NOT NULL,
    fencing_token INTEGER NOT NULL,
    expires_at    REAL NOT NULL,
    PRIMARY KEY (tenant_id, resource)
);
CREATE TABLE IF NOT EXISTS lease_counters (
    tenant_id  TEXT NOT NULL,
    resource   TEXT NOT NULL,
    last_token INTEGER NOT NULL,
    PRIMARY KEY (tenant_id, resource)
);
CREATE TABLE IF NOT EXISTS entitlements (
    tenant_id   TEXT NOT NULL,
    line_ref    TEXT NOT NULL,
    entitlement TEXT NOT NULL,
    state       TEXT NOT NULL DEFAULT 'active',
    PRIMARY KEY (tenant_id, line_ref, entitlement)
);
CREATE TABLE IF NOT EXISTS buyers (
    tenant_id   TEXT NOT NULL,
    launch_id   TEXT NOT NULL,
    contact_ref TEXT NOT NULL,
    PRIMARY KEY (tenant_id, launch_id, contact_ref)
);
CREATE TABLE IF NOT EXISTS buyer_lines (
    tenant_id   TEXT NOT NULL,
    launch_id   TEXT NOT NULL,
    contact_ref TEXT NOT NULL,
    line_ref    TEXT NOT NULL,
    PRIMARY KEY (tenant_id, launch_id, contact_ref, line_ref)
);
CREATE TABLE IF NOT EXISTS quarantine (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id     TEXT NOT NULL,
    location_id   TEXT,
    launch_id     TEXT,
    reason_code   TEXT NOT NULL,
    detail        TEXT,
    evidence_ref  TEXT,
    readback_json TEXT NOT NULL,
    received_at   TEXT NOT NULL,
    resolved      INTEGER NOT NULL DEFAULT 0
);
"""


class Store:
    """One Store per database path. Safe for concurrent threads and
    processes: every mutating operation runs inside a BEGIN IMMEDIATE
    transaction, and claims rely on PRIMARY KEY conflicts."""

    def __init__(self, path: str | Path):
        self.path = str(path)
        self._local = threading.local()
        conn = self._conn()
        conn.executescript(_SCHEMA)
        conn.commit()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=30.0,
                                   isolation_level=None)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")
            self._local.conn = conn
        return conn

    # ── Inbox ────────────────────────────────────────────────────────────
    def record_event_if_unseen(self, tenant_id: str, provider: str,
                               event_id: str, event: dict) -> bool:
        """True if this is the first sight of the event; False if it is a
        duplicate delivery (the stored original is authoritative)."""
        conn = self._conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "INSERT OR IGNORE INTO inbox_events"
                " (tenant_id, provider, event_id, event_json, received_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (tenant_id, provider, event_id,
                 json.dumps(event, sort_keys=True), time.time()))
            conn.execute("COMMIT")
            return cur.rowcount == 1
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def get_event(self, tenant_id: str, provider: str,
                  event_id: str) -> Optional[dict]:
        row = self._conn().execute(
            "SELECT event_json FROM inbox_events"
            " WHERE tenant_id=? AND provider=? AND event_id=?",
            (tenant_id, provider, event_id)).fetchone()
        return json.loads(row[0]) if row else None

    # ── quarantine (visible review items, S44-04 section 7) ─────────────
    def add_quarantine(self, tenant_id: str, location_id, launch_id,
                       reason_code: str, detail: str, evidence_ref,
                       readback: dict, received_at: str) -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO quarantine (tenant_id, location_id, launch_id,"
            " reason_code, detail, evidence_ref, readback_json, received_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (tenant_id, location_id, launch_id, reason_code, detail,
             evidence_ref, json.dumps(readback), received_at))
        return cur.lastrowid

    def open_quarantine(self, tenant_id: str) -> list[dict]:
        cols = ("id", "tenant_id", "location_id", "launch_id",
                "reason_code", "detail", "evidence_ref", "readback_json",
                "received_at", "resolved")
        rows = self._conn().execute(
            "SELECT id, tenant_id, location_id, launch_id, reason_code,"
            " detail, evidence_ref, readback_json, received_at, resolved"
            " FROM quarantine WHERE tenant_id=? AND resolved=0"
            " ORDER BY id", (tenant_id,)).fetchall()
        return [dict(zip(cols, r)) for r in rows]

    def resolve_quarantine(self, quarantine_id: int) -> None:
        self._conn().execute(
            "UPDATE quarantine SET resolved=1 WHERE id=?", (quarantine_id,))

    # ── Entitlement book (authority for suppression, S44-07) ────────────
    def grant_entitlement(self, tenant_id: str, line_ref: str,
                          entitlement: str) -> bool:
        """Activate a per-line grant. True iff this call newly activated
        it. Refunds change state; history is never deleted."""
        conn = self._conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "INSERT INTO entitlements (tenant_id, line_ref,"
                " entitlement, state) VALUES (?, ?, ?, 'active')"
                " ON CONFLICT(tenant_id, line_ref, entitlement)"
                " DO UPDATE SET state='active'"
                " WHERE entitlements.state != 'active'",
                (tenant_id, line_ref, entitlement))
            conn.execute("COMMIT")
            return cur.rowcount == 1
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def revoke_entitlement(self, tenant_id: str, line_ref: str,
                           entitlement: str) -> None:
        conn = self._conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "UPDATE entitlements SET state='revoked'"
                " WHERE tenant_id=? AND line_ref=? AND entitlement=?",
                (tenant_id, line_ref, entitlement))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def active_entitlements(self, tenant_id: str) -> list[str]:
        """Entitlement-level set: an entitlement is active while at
        least one of its line grants is active (renewal semantics)."""
        rows = self._conn().execute(
            "SELECT DISTINCT entitlement FROM entitlements"
            " WHERE tenant_id=? AND state='active'",
            (tenant_id,)).fetchall()
        return sorted(r[0] for r in rows)

    def line_has_active_entitlement(self, tenant_id: str,
                                    line_ref: str) -> bool:
        row = self._conn().execute(
            "SELECT 1 FROM entitlements WHERE tenant_id=? AND line_ref=?"
            " AND state='active' LIMIT 1",
            (tenant_id, line_ref)).fetchone()
        return row is not None

    # ── Buyer registry (suppression fast path + line linkage) ───────────
    def add_buyer(self, tenant_id: str, launch_id: str, contact_ref: str,
                  line_ref: str) -> None:
        conn = self._conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "INSERT OR IGNORE INTO buyers VALUES (?, ?, ?)",
                (tenant_id, launch_id, contact_ref))
            conn.execute(
                "INSERT OR IGNORE INTO buyer_lines VALUES (?, ?, ?, ?)",
                (tenant_id, launch_id, contact_ref, line_ref))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def buyer_lines(self, tenant_id: str, launch_id: str,
                    contact_ref: str) -> list[str]:
        rows = self._conn().execute(
            "SELECT line_ref FROM buyer_lines WHERE tenant_id=?"
            " AND launch_id=? AND contact_ref=?",
            (tenant_id, launch_id, contact_ref)).fetchall()
        return [r[0] for r in rows]

    def is_suppressed(self, tenant_id: str, launch_id: str,
                      contact_ref: str) -> bool:
        """A21 authority check: suppressed while ANY of the buyer's
        lines still carries an active entitlement. A full refund
        unsuppresses naturally; no unsuppress job exists."""
        lines = self.buyer_lines(tenant_id, launch_id, contact_ref)
        return any(self.line_has_active_entitlement(tenant_id, line)
                   for line in lines)

    # ── Fulfillment read model (S82 map + ev1 entitlement_version) ─────
    def buyer_entitlement_rows(self, tenant_id: str, launch_id: str,
                               contact_ref: str) -> list[tuple]:
        """Every entitlement-book row (line_ref, entitlement, state) for
        the buyer's registered lines, revoked rows included (history is
        never deleted), sorted by (line_ref, entitlement) comparing
        UTF-8 byte sequences — the ev1 canonical order."""
        lines = self.buyer_lines(tenant_id, launch_id, contact_ref)
        if not lines:
            return []
        marks = ",".join("?" for _ in lines)
        rows = self._conn().execute(
            "SELECT line_ref, entitlement, state FROM entitlements"
            f" WHERE tenant_id=? AND line_ref IN ({marks})",
            (tenant_id, *lines)).fetchall()
        return sorted(
            ((r[0], r[1], r[2]) for r in rows),
            key=lambda r: (r[0].encode("utf-8"),
                           r[1].encode("utf-8")))

    def entitlement_version(self, tenant_id: str, launch_id: str,
                            contact_ref: str) -> str:
        """ev1 entitlement_version (CR-S82-002 item 5, committed spec in
        work/acceptance/evidence-a21-and-item5.md section 2):
        "ev1:" + lowercase hex SHA-256 of the canonical string
        tenant_id US launch_id US contact_ref RS, followed by the
        buyer's entitlement rows in canonical order, each encoded
        line_ref US entitlement US state and separated by RS
        (US = U+001F, RS = U+001E). With zero rows the string ends at
        the first RS. Pure function of the book's contents for this
        buyer: changes exactly when a row is granted, revoked, or
        re-granted; read-only."""
        us, rs = "\u001f", "\u001e"
        header = us.join((tenant_id, launch_id, contact_ref))
        rows = [us.join((line_ref, entitlement, state))
                for line_ref, entitlement, state in
                self.buyer_entitlement_rows(tenant_id, launch_id,
                                            contact_ref)]
        # header RS row1 RS row2 ...; with zero rows the string still
        # ends at the first RS (spec step 3)
        canonical = header + rs + rs.join(rows) if rows else header + rs
        return "ev1:" + hashlib.sha256(
            canonical.encode("utf-8")).hexdigest()

    def line_action_states(self, tenant_id: str, line_ref: str,
                           action_type: str) -> list[str]:
        """States of every ledger action of one type recorded against a
        line (across transactions and versions). Read-only; used by
        the fulfillment-map read model."""
        rows = self._conn().execute(
            "SELECT state FROM actions WHERE tenant_id=? AND line_ref=?"
            " AND action_type=? ORDER BY updated_at",
            (tenant_id, line_ref, action_type)).fetchall()
        return [r[0] for r in rows]

    def stored_events(self, tenant_id: str) -> list[dict]:
        """Every normalized envelope recorded in the inbox for a tenant,
        parsed. Read-only; the fulfillment-map read model consults
        event history for lines whose payment never granted."""
        rows = self._conn().execute(
            "SELECT event_json FROM inbox_events WHERE tenant_id=?"
            " ORDER BY received_at", (tenant_id,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    # ── Action ledger ────────────────────────────────────────────────────
    def claim_action(self, key: tuple, payload: dict) -> Optional[dict]:
        """Atomically claim an action key. Returns None to the single
        winner; returns the existing record to everyone else. A parked
        (unknown) action also returns its record: it blocks replay."""
        tenant_id, txn_ref, line_ref, action_type, version = key
        conn = self._conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "INSERT OR IGNORE INTO actions"
                " (tenant_id, txn_ref, line_ref, action_type, version,"
                "  state, payload_json, updated_at)"
                " VALUES (?, ?, ?, ?, ?, 'claimed', ?, ?)",
                (tenant_id, txn_ref, line_ref, action_type, version,
                 json.dumps(payload, sort_keys=True), time.time()))
            if cur.rowcount == 1:
                conn.execute("COMMIT")
                return None
            row = conn.execute(
                "SELECT state, payload_json, evidence_ref FROM actions"
                " WHERE tenant_id=? AND txn_ref=? AND line_ref=?"
                " AND action_type=? AND version=?",
                key).fetchone()
            conn.execute("COMMIT")
            return {"state": row[0], "payload": json.loads(row[1]),
                    "evidence_ref": row[2]}
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def mark_action(self, key: tuple, state: str,
                    evidence_ref: Optional[str] = None) -> None:
        """Transition a claimed action to done or unknown. Unknown is the
        write-succeeded/verification-incomplete parking state; it is never
        silently cleared, only reconciled by an explicit mark to done."""
        assert state in ("done", "unknown"), state
        conn = self._conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "UPDATE actions SET state=?, evidence_ref=?, updated_at=?"
                " WHERE tenant_id=? AND txn_ref=? AND line_ref=?"
                " AND action_type=? AND version=?",
                (state, evidence_ref, time.time(), *key))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def get_action(self, key: tuple) -> Optional[dict]:
        row = self._conn().execute(
            "SELECT state, payload_json, evidence_ref FROM actions"
            " WHERE tenant_id=? AND txn_ref=? AND line_ref=?"
            " AND action_type=? AND version=?", key).fetchone()
        if row is None:
            return None
        return {"state": row[0], "payload": json.loads(row[1]),
                "evidence_ref": row[2]}

    def unknown_actions(self, tenant_id: str) -> list[dict]:
        """The visible review list: parked actions awaiting reconciliation."""
        rows = self._conn().execute(
            "SELECT txn_ref, line_ref, action_type, version, payload_json,"
            " evidence_ref FROM actions"
            " WHERE tenant_id=? AND state='unknown'", (tenant_id,)).fetchall()
        return [{"key": (tenant_id, r[0], r[1], r[2], r[3]),
                 "payload": json.loads(r[4]), "evidence_ref": r[5]}
                for r in rows]

    # ── Request store (receiver redispatch) ──────────────────────────────
    def get_request(self, request_id: str) -> Optional[dict]:
        row = self._conn().execute(
            "SELECT request_version, tenant_id, state, receipt_json"
            " FROM requests WHERE request_id=?", (request_id,)).fetchone()
        if row is None:
            return None
        return {"request_version": row[0], "tenant_id": row[1],
                "state": row[2],
                "receipt": json.loads(row[3]) if row[3] else None}

    def put_request(self, request_id: str, request_version: int,
                    tenant_id: str, state: str,
                    receipt: Optional[dict]) -> bool:
        """Insert-or-replace guarded by monotonic request_version: a
        superseded version write is refused (returns False)."""
        conn = self._conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT request_version FROM requests WHERE request_id=?",
                (request_id,)).fetchone()
            if row and row[0] >= request_version:
                conn.execute("COMMIT")
                return False
            conn.execute(
                "INSERT OR REPLACE INTO requests"
                " (request_id, request_version, tenant_id, state,"
                "  receipt_json, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                (request_id, request_version, tenant_id, state,
                 json.dumps(receipt, sort_keys=True) if receipt else None,
                 time.time()))
            conn.execute("COMMIT")
            return True
        except Exception:
            conn.execute("ROLLBACK")
            raise

    # ── Leases (cross-box writer fencing, doc 14 section 9) ─────────────
    def acquire_lease(self, tenant_id: str, resource: str, holder: str,
                      ttl_seconds: float = 60.0) -> Optional[int]:
        """Acquire or renew a lease. Returns the fencing token (monotonic
        per resource) or None if a live lease is held by someone else.
        Renewal by the same holder keeps the token."""
        now = time.time()
        conn = self._conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                "SELECT holder, fencing_token, expires_at FROM leases"
                " WHERE tenant_id=? AND resource=?",
                (tenant_id, resource)).fetchone()
            if row is not None and row[0] == holder and row[2] > now:
                # live lease, same holder: renewal keeps the token
                conn.execute(
                    "UPDATE leases SET expires_at=? WHERE tenant_id=?"
                    " AND resource=?",
                    (now + ttl_seconds, tenant_id, resource))
                conn.execute("COMMIT")
                return row[1]
            if row is not None and row[2] > now:
                conn.execute("COMMIT")
                return None  # live lease held by someone else
            # New acquisition (no row, expired row, or a released lease whose
            # row is gone): the fencing token comes from the never-deleted
            # counter, so it is monotonic across the resource's whole
            # lifetime — a token value is never reused, even after release.
            cur = conn.execute(
                "INSERT INTO lease_counters (tenant_id, resource, last_token)"
                " VALUES (?, ?, 1)"
                " ON CONFLICT(tenant_id, resource)"
                " DO UPDATE SET last_token = last_token + 1 RETURNING last_token",
                (tenant_id, resource))
            token = cur.fetchone()[0]
            conn.execute(
                "INSERT OR REPLACE INTO leases VALUES (?, ?, ?, ?, ?)",
                (tenant_id, resource, holder, token, now + ttl_seconds))
            conn.execute("COMMIT")
            return token
        except Exception:
            conn.execute("ROLLBACK")
            raise

    def check_fencing(self, tenant_id: str, resource: str, holder: str,
                      fencing_token: int) -> bool:
        """A write proceeds only while its fencing token is still the
        current one for the holder. A stale holder (lease lost or taken
        over) is refused even if it still believes it holds the lease."""
        row = self._conn().execute(
            "SELECT holder, fencing_token, expires_at FROM leases"
            " WHERE tenant_id=? AND resource=?",
            (tenant_id, resource)).fetchone()
        return bool(row and row[0] == holder and row[1] == fencing_token
                    and row[2] > time.time())

    def release_lease(self, tenant_id: str, resource: str, holder: str,
                      fencing_token: int) -> None:
        conn = self._conn()
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "DELETE FROM leases WHERE tenant_id=? AND resource=?"
                " AND holder=? AND fencing_token=?",
                (tenant_id, resource, holder, fencing_token))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
