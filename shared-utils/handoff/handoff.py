#!/usr/bin/env python3
"""handoff.py - owned human handoff: context, acceptance, due, backup, fence.

Contract basis: Purple-Billboard SPEC.md "Booking, handoff and outcomes" and
DATA-CONTRACTS section 7 precedence (human ownership fences the bot).
Python 3 standard library only.

What this module exists to guarantee (R-19 / C-29):

  CONTEXT      A handoff cannot be opened from nothing: it carries a context
               reference, a summary of what the person needs, the offered
               owner, a backup owner and a concrete due action plus due time.

  ACCEPTANCE   Assignment is not acceptance. The offered owner must accept,
               and only the offered owner can. A handoff that was never
               accepted has no actual owner, so nobody can release it.

  DUE/BACKUP   Once the due time passes the handoff is overdue. Escalation
               offers it to the backup, whether or not the offered owner ever
               accepted, and the backup must then accept it. Escalation
               changes the actual owner only through that explicit acceptance.

  FENCE        Opening a handoff pauses the bot for that contact, and the bot
               stays paused through acceptance, escalation, backup acceptance
               and any timeout. It resumes ONLY through an explicit release
               by the actual accepted owner. Nothing here releases on a timer,
               on a grant, on cancellation or on a merely recorded refusal.

REUSE (upstream modules accepted on main):

  * 38-conversational-ai-system/tools/tenant_identity.py (T-12/T-18) supplies
    tenant-scoped contact verification; every operation verifies through it.
  * 38-conversational-ai-system/tools/consent_gate.py (T-18) supplies the
    human-ownership fence itself. This module never keeps a second fence: it
    calls ConsentStore.human_takeover / human_release / human_fence.
  * T-27 (post-gift discovery) had no accepted module on main at build time,
    so nothing was reused from it; the handoff context is plain data.

Storage is an additive pair of tables in the same SQLite file as the identity
and consent tables, so one database stays one tenant boundary.

Import:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from handoff import HandoffStore

Assert-based self-check:  python3 -I handoff.py
"""

from __future__ import annotations

import contextlib
import json
import math
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

STATE_OFFERED = "offered"
STATE_ACTIVE = "active"
STATE_RELEASED = "released"
STATES = (STATE_OFFERED, STATE_ACTIVE, STATE_RELEASED)

ACTION_CREATED = "created"
ACTION_ACCEPTED = "accepted"
ACTION_ESCALATED = "escalated"
ACTION_BACKUP_ACCEPTED = "backup_accepted"
ACTION_RELEASED = "released"
ACTIONS = (ACTION_CREATED, ACTION_ACCEPTED, ACTION_ESCALATED,
           ACTION_BACKUP_ACCEPTED, ACTION_RELEASED)

GATE_SUPPRESSED = "SUPPRESSED"
GATE_ALLOW = "ALLOW"
REASON_HUMAN = "handoff:human_owned"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS handoffs (
    handoff_id           TEXT PRIMARY KEY,
    tenant_id            TEXT NOT NULL,
    canonical_contact_id TEXT NOT NULL,
    context_ref          TEXT NOT NULL,
    context_summary      TEXT NOT NULL,
    reason               TEXT NOT NULL DEFAULT '',
    owner_id             TEXT NOT NULL,
    backup_owner_id      TEXT NOT NULL,
    due_action           TEXT NOT NULL,
    due_at               REAL NOT NULL,
    state                TEXT NOT NULL,
    actual_owner_id      TEXT,
    created_by           TEXT NOT NULL DEFAULT '',
    accepted_at          REAL,
    backup_accepted_at   REAL,
    escalated_at         REAL,
    released_at          REAL,
    release_reason       TEXT NOT NULL DEFAULT '',
    version              INTEGER NOT NULL DEFAULT 0,
    created_at           REAL NOT NULL,
    updated_at           REAL NOT NULL,
    create_key           TEXT UNIQUE,
    release_key          TEXT UNIQUE
);

CREATE INDEX IF NOT EXISTS handoffs_by_contact
    ON handoffs (tenant_id, canonical_contact_id, state);

CREATE TABLE IF NOT EXISTS handoff_events (
    handoff_id TEXT NOT NULL,
    seq        INTEGER NOT NULL,
    action     TEXT NOT NULL,
    actor      TEXT NOT NULL DEFAULT '',
    reason     TEXT NOT NULL DEFAULT '',
    at         REAL NOT NULL,
    details    TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (handoff_id, seq)
);
"""

class HandoffError(ValueError):
    """Bad input, a refused operation or an illegal transition. Fail closed."""

# ── input helpers ──────────────────────────────────────────────────────────

def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HandoffError(f"bad_input: {name} must be a non-empty string")
    return value.strip()

def _seconds(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HandoffError(f"bad_input: {name} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise HandoffError(f"bad_input: {name} must be finite")
    return number

def _now(value: Optional[float]) -> float:
    return time.time() if value is None else _seconds(value, "now")

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]

# ── the fence (T-18 reuse, never a second copy) ────────────────────────────

class _ConsentFence:
    """Adapter over T-18's ConsentStore; the only fence this module consults."""

    def __init__(self, identity, consent) -> None:
        self.identity = identity
        self.consent = consent

    def pause(self, tenant_id: str, canonical_contact_id: str, *,
              actor: str, reason: str, now: float) -> Dict[str, Any]:
        return self.consent.human_takeover(
            tenant_id, canonical_contact_id, actor=actor, reason=reason, now=now)

    def release(self, tenant_id: str, canonical_contact_id: str, *,
                actor: str, reason: str, now: float) -> Dict[str, Any]:
        return self.consent.human_release(
            tenant_id, canonical_contact_id, actor=actor, reason=reason, now=now)

    def is_paused(self, tenant_id: str, canonical_contact_id: str) -> bool:
        return bool(self.consent.human_fence(
            tenant_id, canonical_contact_id)["active"])

def _load_tools(tools_dir: Optional[str]):
    """Import T-12/T-18 modules from the skill tools directory, or fail."""
    directory = Path(tools_dir) if tools_dir else (
        _repo_root() / "38-conversational-ai-system" / "tools")
    if not directory.is_dir():
        raise HandoffError(
            f"fence_unavailable: upstream tools directory not found at {directory}")
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))
    try:
        from tenant_identity import TenantIdentity  # noqa: E402
        from consent_gate import ConsentStore  # noqa: E402
    except Exception as exc:  # pragma: no cover - import shape is repo-owned
        raise HandoffError(f"fence_unavailable: {exc}") from exc
    return TenantIdentity, ConsentStore

class HandoffStore:
    """Owned handoff lifecycle over the tenant identity/consent SQLite file."""

    def __init__(self, db_path: str, *, tools_dir: Optional[str] = None,
                 fence: Optional[Any] = None) -> None:
        if not isinstance(db_path, str) or not db_path.strip():
            raise HandoffError("bad_input: db_path must be a non-empty string")
        self.db_path = db_path
        self._tools_dir = tools_dir
        self._identity = None
        self._fence = fence
        self.init_schema()

    # -- storage ----------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def init_schema(self) -> None:
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = FULL")
            conn.executescript(_SCHEMA)
        finally:
            conn.close()

    @contextlib.contextmanager
    def _write(self):
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()

    @contextlib.contextmanager
    def _read(self):
        conn = self._connect()
        try:
            yield conn
        finally:
            conn.close()

    # -- dependencies -----------------------------------------------------

    @property
    def identity(self):
        if self._identity is None:
            TenantIdentity, ConsentStore = _load_tools(self._tools_dir)
            self._identity = TenantIdentity(self.db_path)
            if self._fence is None:
                consent = ConsentStore(self._identity)
                self._fence = _ConsentFence(self._identity, consent)
        return self._identity

    @property
    def fence(self):
        if self._fence is None:
            self.identity  # builds the consent fence on the same database
        return self._fence

    def _verify(self, tenant_id: str, canonical_contact_id: str) -> None:
        tenant_id = _text(tenant_id, "tenant_id")
        canonical_contact_id = _text(canonical_contact_id,
                                     "canonical_contact_id")
        self.identity.verify(tenant_id, canonical_contact_id)

    # -- lifecycle --------------------------------------------------------

    def create(
        self,
        tenant_id: str,
        canonical_contact_id: str,
        *,
        context_ref: str,
        context_summary: str,
        owner_id: str,
        backup_owner_id: str,
        due_action: str,
        due_at: float,
        created_by: str = "system:handoff",
        reason: str = "",
        now: Optional[float] = None,
        create_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Open an offered handoff and pause the bot for that contact."""
        tenant_id = _text(tenant_id, "tenant_id")
        canonical_contact_id = _text(canonical_contact_id,
                                     "canonical_contact_id")
        context_ref = _text(context_ref, "context_ref")
        context_summary = _text(context_summary, "context_summary")
        owner_id = _text(owner_id, "owner_id")
        backup_owner_id = _text(backup_owner_id, "backup_owner_id")
        due_action = _text(due_action, "due_action")
        created_by = _text(created_by, "created_by")
        due_at = _seconds(due_at, "due_at")
        if owner_id == backup_owner_id:
            raise HandoffError("bad_input: backup_owner_id must differ from owner_id")
        ts = _now(now)
        if due_at <= ts:
            raise HandoffError("bad_input: due_at must be after the handoff opens")
        if create_key is not None:
            create_key = _text(create_key, "create_key")
        self._verify(tenant_id, canonical_contact_id)

        if create_key is not None:
            with self._read() as conn:
                earlier = conn.execute(
                    "SELECT handoff_id FROM handoffs WHERE create_key = ?",
                    (create_key,)).fetchone()
            if earlier is not None:
                return self.get(earlier["handoff_id"])

        handoff_id = "ho_" + uuid.uuid4().hex
        # Fence first: a crash between the two leaves the bot over-paused, never
        # running a conversation a human already owns.
        self.fence.pause(tenant_id, canonical_contact_id, actor=owner_id,
                         reason=f"handoff:{handoff_id}", now=ts)
        try:
            with self._write() as conn:
                conn.execute(
                    "INSERT INTO handoffs (handoff_id, tenant_id,"
                    " canonical_contact_id, context_ref, context_summary,"
                    " reason, owner_id, backup_owner_id, due_action, due_at,"
                    " state, actual_owner_id, created_by, version, created_at,"
                    " updated_at, create_key)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (handoff_id, tenant_id, canonical_contact_id, context_ref,
                     context_summary, reason or "", owner_id, backup_owner_id,
                     due_action, due_at, STATE_OFFERED, None, created_by, 1,
                     ts, ts, create_key),
                )
                self._event(conn, handoff_id, ACTION_CREATED, owner_id,
                            "offered_to_owner", ts,
                            {"owner_id": owner_id,
                             "backup_owner_id": backup_owner_id,
                             "due_at": due_at})
        except BaseException:
            # The offer is already fenced; release OUR failed offer rather than
            # leave an orphan fence. A concurrent open handoff for the same
            # contact keeps the fence: releasing it would unpause a live one.
            if not self._other_open(tenant_id, canonical_contact_id):
                try:
                    self.fence.release(
                        tenant_id, canonical_contact_id, actor=owner_id,
                        reason=f"handoff_create_failed:{handoff_id}", now=ts)
                except Exception:
                    pass  # over-paused is the safe direction
            raise
        return self.get(handoff_id)

    def accept(self, handoff_id: str, *, actor: str,
               now: Optional[float] = None,
               expect_version: Optional[int] = None) -> Dict[str, Any]:
        """The offered owner accepts the duty. Assignment alone never counts."""
        handoff_id = _text(handoff_id, "handoff_id")
        actor = _text(actor, "actor")
        ts = _now(now)
        with self._write() as conn:
            row = self._locked(conn, handoff_id)
            self._expect_version(row, expect_version)
            if row["state"] != STATE_OFFERED:
                raise HandoffError(
                    f"illegal_transition: accept requires state {STATE_OFFERED},"
                    f" found {row['state']}")
            if actor != row["owner_id"]:
                raise HandoffError("refused: only the offered owner can accept")
            if ts >= row["due_at"]:
                raise HandoffError(
                    "refused: the due time already passed; escalate to the backup")
            conn.execute(
                "UPDATE handoffs SET state=?, actual_owner_id=?, accepted_at=?,"
                " version=version+1, updated_at=? WHERE handoff_id=?",
                (STATE_ACTIVE, actor, ts, ts, handoff_id))
            self._event(conn, handoff_id, ACTION_ACCEPTED, actor,
                        "owner_accepted", ts, {"due_action": row["due_action"],
                                               "due_at": row["due_at"]})
        return self.get(handoff_id)

    def escalate(self, handoff_id: str, *, now: Optional[float] = None,
                 reason: str = "",
                 expect_version: Optional[int] = None) -> Dict[str, Any]:
        """Offer an overdue handoff to the backup. Fence unchanged.

        An offer whose owner never accepted is reachable too: once the due
        time lapses the backup is the only route out, and the bot stays
        paused until that backup accepts and releases.

        ponytail: escalation is a caller-driven operation, never a wall-clock
        timer. The scheduler that owns handoffs calls this when it sweeps;
        upgrade to a durable timer only if handoffs must escalate with no
        process alive.
        """
        handoff_id = _text(handoff_id, "handoff_id")
        ts = _now(now)
        with self._write() as conn:
            row = self._locked(conn, handoff_id)
            self._expect_version(row, expect_version)
            if row["state"] not in (STATE_ACTIVE, STATE_OFFERED):
                raise HandoffError(
                    f"illegal_transition: escalate requires state"
                    f" {STATE_ACTIVE} or {STATE_OFFERED}, found {row['state']}")
            if ts < row["due_at"]:
                raise HandoffError("refused: the handoff is not overdue")
            if row["escalated_at"] is not None:
                raise HandoffError("illegal_transition: already escalated")
            conn.execute(
                "UPDATE handoffs SET escalated_at=?, version=version+1,"
                " updated_at=? WHERE handoff_id=?",
                (ts, ts, handoff_id))
            self._event(conn, handoff_id, ACTION_ESCALATED, "system:handoff",
                        reason or "due_action_missed", ts,
                        {"backup_owner_id": row["backup_owner_id"],
                         "actual_owner_id": row["actual_owner_id"]})
        return self.get(handoff_id)

    def backup_accept(self, handoff_id: str, *, actor: str,
                      now: Optional[float] = None,
                      expect_version: Optional[int] = None) -> Dict[str, Any]:
        """The backup accepts an escalated handoff and becomes the owner.

        Reachable from an accepted handoff and from an offer that lapsed
        unaccepted; either way the owner changes only through this call.
        """
        handoff_id = _text(handoff_id, "handoff_id")
        actor = _text(actor, "actor")
        ts = _now(now)
        with self._write() as conn:
            row = self._locked(conn, handoff_id)
            self._expect_version(row, expect_version)
            if row["state"] not in (STATE_ACTIVE, STATE_OFFERED):
                raise HandoffError(
                    "illegal_transition: backup_accept requires state"
                    f" {STATE_ACTIVE} or {STATE_OFFERED}, found {row['state']}")
            if row["escalated_at"] is None:
                raise HandoffError(
                    "refused: the handoff was not escalated to the backup")
            if actor != row["backup_owner_id"]:
                raise HandoffError("refused: only the named backup can accept")
            if row["actual_owner_id"] == row["backup_owner_id"]:
                raise HandoffError("illegal_transition: the backup already owns it")
            if row["state"] == STATE_OFFERED:
                # Nobody accepted the offer, so the backup's acceptance is
                # what makes the handoff owned at all.
                conn.execute(
                    "UPDATE handoffs SET state=?, actual_owner_id=?,"
                    " backup_accepted_at=?, version=version+1, updated_at=?"
                    " WHERE handoff_id=?",
                    (STATE_ACTIVE, actor, ts, ts, handoff_id))
            else:
                conn.execute(
                    "UPDATE handoffs SET actual_owner_id=?, backup_accepted_at=?,"
                    " version=version+1, updated_at=? WHERE handoff_id=?",
                    (actor, ts, ts, handoff_id))
            self._event(conn, handoff_id, ACTION_BACKUP_ACCEPTED, actor,
                        "backup_accepted", ts,
                        {"previous_owner_id": row["actual_owner_id"]})
        return self.get(handoff_id)

    def release(self, handoff_id: str, *, actor: str, reason: str,
                now: Optional[float] = None,
                release_key: Optional[str] = None) -> Dict[str, Any]:
        """Resume the bot. Explicit, by the actual accepted owner, only."""
        handoff_id = _text(handoff_id, "handoff_id")
        actor = _text(actor, "actor")
        reason = _text(reason, "reason")
        ts = _now(now)
        if release_key is not None:
            release_key = _text(release_key, "release_key")

        row = self.get(handoff_id)
        if row["state"] == STATE_RELEASED:
            if release_key is not None and row["release_key"] == release_key:
                if actor != row["actual_owner_id"]:
                    raise HandoffError(
                        "refused: only the actual owner can release")
                self._finish_release(row, row["release_reason"] or reason, ts)
                return self.get(handoff_id)
            raise HandoffError("illegal_transition: already released")

        with self._write() as conn:
            locked = self._locked(conn, handoff_id)
            if locked["state"] == STATE_RELEASED:
                raise HandoffError("illegal_transition: already released")
            # No accepted owner means actual_owner_id is NULL, which no actor
            # string can match: release before acceptance is refused here.
            if actor != locked["actual_owner_id"]:
                raise HandoffError("refused: only the actual owner can release")
            if release_key is not None:
                clash = conn.execute(
                    "SELECT handoff_id FROM handoffs WHERE release_key = ?",
                    (release_key,)).fetchone()
                if clash is not None and clash["handoff_id"] != handoff_id:
                    raise HandoffError("refused: release_key already used")
            conn.execute(
                "UPDATE handoffs SET state=?, released_at=?, release_reason=?,"
                " release_key=?, version=version+1, updated_at=?"
                " WHERE handoff_id=?",
                (STATE_RELEASED, ts, reason, release_key, ts, handoff_id))
            self._event(conn, handoff_id, ACTION_RELEASED, actor, reason, ts,
                        {"release_key": release_key})
        # ponytail: the released state commits before the fence release. A crash
        # between the two leaves the bot paused (safe) and a same-release_key
        # retry finishes it. Upgrade to a cross-process outbox only if the
        # stored fence ever leaves this database.
        self._finish_release(self.get(handoff_id), reason, ts)
        return self.get(handoff_id)

    # -- reads ------------------------------------------------------------

    def get(self, handoff_id: str, *,
            now: Optional[float] = None) -> Dict[str, Any]:
        handoff_id = _text(handoff_id, "handoff_id")
        ts = _now(now)
        with self._read() as conn:
            row = conn.execute(
                "SELECT * FROM handoffs WHERE handoff_id = ?",
                (handoff_id,)).fetchone()
        if row is None:
            raise HandoffError(f"unknown_handoff: {handoff_id}")
        data = dict(row)
        paused = bool(self.fence.is_paused(
            data["tenant_id"], data["canonical_contact_id"]))
        open_state = data["state"] in (STATE_ACTIVE, STATE_OFFERED)
        return {
            "handoff_id": data["handoff_id"],
            "tenant_id": data["tenant_id"],
            "canonical_contact_id": data["canonical_contact_id"],
            "context": {"ref": data["context_ref"],
                        "summary": data["context_summary"],
                        "reason": data["reason"]},
            "owner_id": data["owner_id"],
            "backup_owner_id": data["backup_owner_id"],
            "due_action": data["due_action"],
            "due_at": data["due_at"],
            "state": data["state"],
            "actual_owner_id": data["actual_owner_id"],
            "accepted": (data["accepted_at"] is not None
                         or data["backup_accepted_at"] is not None),
            "accepted_at": data["accepted_at"],
            "escalated_at": data["escalated_at"],
            "backup_accepted": data["backup_accepted_at"] is not None,
            "overdue": (open_state and ts >= data["due_at"]),
            "escalation_due": (open_state and data["escalated_at"] is None
                               and ts >= data["due_at"]),
            "released_at": data["released_at"],
            "release_reason": data["release_reason"],
            "release_key": data["release_key"],
            "version": data["version"],
            "bot_paused": paused,
        }

    def events(self, handoff_id: str) -> List[Dict[str, Any]]:
        handoff_id = _text(handoff_id, "handoff_id")
        with self._read() as conn:
            rows = conn.execute(
                "SELECT * FROM handoff_events WHERE handoff_id = ? ORDER BY seq",
                (handoff_id,)).fetchall()
        return [dict(r) for r in rows]

    def open_for_contact(self, tenant_id: str,
                         canonical_contact_id: str) -> List[Dict[str, Any]]:
        tenant_id = _text(tenant_id, "tenant_id")
        canonical_contact_id = _text(canonical_contact_id,
                                     "canonical_contact_id")
        self._verify(tenant_id, canonical_contact_id)
        with self._read() as conn:
            rows = conn.execute(
                "SELECT handoff_id FROM handoffs WHERE tenant_id=?"
                " AND canonical_contact_id=? AND state IN (?,?)"
                " ORDER BY created_at",
                (tenant_id, canonical_contact_id, STATE_OFFERED,
                 STATE_ACTIVE)).fetchall()
        return [self.get(r["handoff_id"]) for r in rows]

    def gate_decision(self, tenant_id: str,
                      canonical_contact_id: str) -> Dict[str, Any]:
        """The section 3 shape: an open handoff suppresses outbound."""
        self._verify(tenant_id, canonical_contact_id)
        open_rows = self.open_for_contact(tenant_id, canonical_contact_id)
        paused = bool(self.fence.is_paused(tenant_id, canonical_contact_id))
        if open_rows or paused:
            return {"verdict": GATE_SUPPRESSED, "reason": REASON_HUMAN,
                    "handoff_id": open_rows[0]["handoff_id"] if open_rows else None,
                    "bot_paused": paused}
        return {"verdict": GATE_ALLOW, "reason": "handoff:none",
                "handoff_id": None, "bot_paused": False}

    # -- internals --------------------------------------------------------

    def _other_open(self, tenant_id: str,
                    canonical_contact_id: str) -> bool:
        try:
            with self._read() as conn:
                row = conn.execute(
                    "SELECT 1 FROM handoffs WHERE tenant_id=?"
                    " AND canonical_contact_id=? AND state IN (?,?) LIMIT 1",
                    (tenant_id, canonical_contact_id, STATE_OFFERED,
                     STATE_ACTIVE)).fetchone()
            return row is not None
        except sqlite3.Error:
            return True  # unknown: never unpause on a failed guess

    @staticmethod
    def _locked(conn: sqlite3.Connection, handoff_id: str) -> Dict[str, Any]:
        row = conn.execute("SELECT * FROM handoffs WHERE handoff_id = ?",
                           (handoff_id,)).fetchone()
        if row is None:
            raise HandoffError(f"unknown_handoff: {handoff_id}")
        return dict(row)

    @staticmethod
    def _expect_version(row: Dict[str, Any], expected: Optional[int]) -> None:
        if expected is None:
            return
        if isinstance(expected, bool) or not isinstance(expected, int):
            raise HandoffError("bad_input: expect_version must be an integer")
        if expected != row["version"]:
            raise HandoffError(
                f"conflict: expected version {expected}, found {row['version']}")

    @staticmethod
    def _event(conn: sqlite3.Connection, handoff_id: str, action: str,
               actor: str, reason: str, at: float,
               details: Optional[Dict[str, Any]] = None) -> None:
        if action not in ACTIONS:
            raise HandoffError(f"bad_input: unknown action {action!r}")
        seq = conn.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS n FROM handoff_events"
            " WHERE handoff_id = ?", (handoff_id,)).fetchone()["n"]
        conn.execute(
            "INSERT INTO handoff_events (handoff_id, seq, action, actor,"
            " reason, at, details) VALUES (?,?,?,?,?,?,?)",
            (handoff_id, int(seq), action, actor or "", reason or "", at,
             json.dumps(details or {}, sort_keys=True)))

    def _finish_release(self, row: Dict[str, Any], reason: str, at: float) -> None:
        """Release the T-18 fence. Safe to repeat after a crash."""
        tenant_id = row["tenant_id"]
        contact = row["canonical_contact_id"]
        if not self.fence.is_paused(tenant_id, contact):
            return
        # A concurrent open handoff for the same contact keeps the fence:
        # releasing it would unpause a live one. The same guard create()'s
        # rollback path uses.
        if self._other_open(tenant_id, contact):
            return
        self.fence.release(tenant_id, contact, actor=row["actual_owner_id"],
                           reason=reason, now=at)

# ── self-check ─────────────────────────────────────────────────────────────

def _self_check() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "handoff.db")
        store = HandoffStore(db)
        store.identity.register_tenant("t1")
        contact = store.identity.bind("t1", [("email", "p@example.com", True)])
        h = store.create(
            "t1", contact, context_ref="conv-1",
            context_summary="Person asked for pricing help and a callback",
            owner_id="owner-a", backup_owner_id="owner-b",
            due_action="Call the person back with the pricing answer",
            due_at=time.time() + 3600, now=1000.0)
        assert h["state"] == STATE_OFFERED and not h["accepted"], h
        assert h["bot_paused"] is True, h
        assert store.gate_decision("t1", contact)["verdict"] == GATE_SUPPRESSED
        try:
            store.accept(h["handoff_id"], actor="owner-b", now=1001.0)
        except HandoffError as exc:
            assert str(exc).startswith("refused:"), exc
        else:  # pragma: no cover
            raise AssertionError("a non-owner accepted the handoff")
        h = store.accept(h["handoff_id"], actor="owner-a", now=1001.0)
        assert h["state"] == STATE_ACTIVE and h["accepted"], h
        assert h["bot_paused"] is True, h
        h = store.release(h["handoff_id"], actor="owner-a",
                          reason="person served; bot may reply again",
                          now=1002.0)
        assert h["state"] == STATE_RELEASED and h["bot_paused"] is False, h
        assert store.gate_decision("t1", contact)["verdict"] == GATE_ALLOW
        print("handoff self-check OK")

if __name__ == "__main__":
    _self_check()
