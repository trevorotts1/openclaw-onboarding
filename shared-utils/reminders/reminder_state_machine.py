#!/usr/bin/env python3
"""reminder_state_machine.py - shared reminder slots and the reserved final action.

Contract basis: Purple Billboard DATA-CONTRACTS.md section 8 ("Reminder and
final-action states") and section 3 ("fresh gate before every dispatch").

Reuses, and never re-implements, the accepted upstream modules:

  T-11  tenant_identity.TenantIdentity      tenant/contact verification
        collection_lock.CollectionLock      one collector per contact sequence
  T-12  durable_store.DurableStore          idempotent outbox + receipts
        outbound_gate.dispatch              the common fresh gate
  T-18  consent_gate.ConsentStore           STOP / opt-out / human fence
        consent_gate.make_gate_evaluator    the consent evaluator
  T-29  handoff.HandoffStore                an open human handoff suppresses

What this module adds on top of them:

  INITIAL   the invitation is recorded separately and is never one of the
            three reminder slots.
  BUDGET    at most three shared reminders. The slots belong to the contact
            sequence, not to a channel, so FB/IG/SMS share one budget.
  NO RESET  a returning or overlapping request, a restart, or a late reply
            keeps t0, the used count and the existing refusals. Capture never
            restarts once it has stopped: a late request is answered from the
            stopped sequence and never mints a fresh budget.
  SCOPE     a refusal stops only what it covers. A channel opt-out blocks that
            channel and a field refusal suppresses that ask, so the shared
            budget survives them; a global stop or a human fence stops the
            whole sequence.
  RACE      pause, the quiet window and STOP are resolved when the slot is
            reserved, and pause, human ownership, a reply and STOP are
            re-checked immediately before the dispatch call. Queue-time
            consent is never permission.
  FINAL     one reserved final action under the contact lock. Only that exact
            action may pass the ordinary gate while closing_final; siblings
            are canceled; a crash reloads the reservation and never mints a
            second final.
  STOP      provider acceptance closes stopped_final; STOP, refusal, handoff
            or a field completion closes stopped_complete; a declined
            collection closes stopped_declined; permanent nonexecution or an
            expired slot closes stopped_ineligible without ever claiming
            "sent". Provider admission is not acceptance: only a persisted ACK
            receipt proves the closing action landed, and one helper
            (_close_if_acknowledged) is the only writer of stopped_final, so
            dispatch, reconciliation and expiry share one ACK contract.
            A narrow refusal (channel opt-out, field refusal) refuses only the
            final it covers at reservation time; once a final is reserved, any
            refusal before dispatch cancels it (section 8 step 3) and the
            sequence closes stopped_complete, because a sequence has one final.

Storage is additive in the tenant identity database (the same file as
tenant_identity/collection_lock/consent_gate) so one database stays one tenant
boundary. The reminder outbox actions live in durable_store's own database.

Python 3 standard library only. Assert-based self-check:
    python3 -I reminder_state_machine.py
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# Direct-script execution (python3 -I reminder_state_machine.py) does not put
# this directory on sys.path; the accepted upstream modules must still resolve.
_UPSTREAM_TOOLS = (Path(__file__).resolve().parents[2]
                   / "38-conversational-ai-system" / "tools")
# T-29 lives beside this package under shared-utils/handoff/ and must resolve
# on the import path too, not only when this file is run directly.
_HANDOFF_TOOLS = Path(__file__).resolve().parents[1] / "handoff"
if str(_HANDOFF_TOOLS) not in sys.path:
    sys.path.insert(0, str(_HANDOFF_TOOLS))
if __package__ in (None, ""):
    if str(Path(__file__).resolve().parent) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
    if str(_UPSTREAM_TOOLS) not in sys.path:
        sys.path.insert(0, str(_UPSTREAM_TOOLS))

from collection_lock import CollectionLock, LockError  # noqa: E402
from consent_gate import (  # noqa: E402
    REASON_CHANNEL,
    REASON_FIELD,
    REASON_GLOBAL,
    REASON_HUMAN,
    ConsentStore,
    make_gate_evaluator,
)
from durable_store import (  # noqa: E402
    STATE_CANCELED,
    STATE_NOT_REQUESTED,
    STATE_QUEUED,
    DurableStore,
    DurableStoreError,
)
from handoff import HandoffError, HandoffStore  # noqa: E402
from outbound_gate import (  # noqa: E402
    ST_BLOCKED,
    ST_NOT_CLAIMED,
    ST_REFUSED_RACE,
    ST_SEND_ERROR,
    ST_SENT,
    ST_UNKNOWN,
    dispatch,
)
from tenant_identity import TenantIdentity  # noqa: E402

# ── collection states (DATA-CONTRACTS section 8) ────────────────────────────

STATE_INVITED = "invited"
STATE_AWAITING_MOBILE = "awaiting_mobile"
STATE_PREPARING_ACCESS = "preparing_access"
STATE_AWAITING_EMAIL = "awaiting_email"
STATE_PAUSED = "paused_active"
STATE_HUMAN_OWNED = "human_owned"
STATE_CLOSING_FINAL = "closing_final"
STATE_STOPPED_COMPLETE = "stopped_complete"
STATE_STOPPED_DECLINED = "stopped_declined"
STATE_STOPPED_FINAL = "stopped_final"
STATE_STOPPED_INELIGIBLE = "stopped_ineligible"

COLLECTION_STATES = (
    STATE_INVITED,
    STATE_AWAITING_MOBILE,
    STATE_PREPARING_ACCESS,
    STATE_AWAITING_EMAIL,
    STATE_PAUSED,
    STATE_HUMAN_OWNED,
    STATE_CLOSING_FINAL,
    STATE_STOPPED_COMPLETE,
    STATE_STOPPED_DECLINED,
    STATE_STOPPED_FINAL,
    STATE_STOPPED_INELIGIBLE,
)
TERMINAL_STATES = frozenset({
    STATE_STOPPED_COMPLETE,
    STATE_STOPPED_DECLINED,
    STATE_STOPPED_FINAL,
    STATE_STOPPED_INELIGIBLE,
})

# ── slot states ─────────────────────────────────────────────────────────────

SLOT_PENDING = "pending"
SLOT_SENT = "sent"
SLOT_SKIPPED = "skipped"          # budget consumed, never sent (fast-forward)
SLOT_SUPPRESSED = "suppressed"    # STOP / refusal / handoff
SLOT_CANCELED = "canceled"        # sibling of a reserved final action
SLOT_UNKNOWN = "unknown"          # send began, no verdict; reconcile first

SLOT_STATES = (SLOT_PENDING, SLOT_SENT, SLOT_SKIPPED, SLOT_SUPPRESSED,
               SLOT_CANCELED, SLOT_UNKNOWN)

MAX_REMINDERS = 3

# DATA-CONTRACTS section 8 defaults: three escalating slots and a 30-minute
# quiet interval. A policy must be adopted explicitly before activation.
DEFAULT_SLOT_OFFSETS_S: Tuple[float, ...] = (2 * 3600.0, 8 * 3600.0, 20 * 3600.0)
DEFAULT_QUIET_INTERVAL_S = 30 * 60.0
DEFAULT_FINAL_SLOT_S = 24 * 3600.0

DECISION_NONE = "none"
DECISION_DUE = "due"
DECISION_WAIT = "wait"

REASON_NO_CATCH_UP = "no_catch_up_burst"
REASON_FINAL_RESERVED = "final_reserved"
REASON_FIELD_COMPLETION = "field_completion"
REASON_DECLINED = "declined"

# DATA-CONTRACTS section 7: "channel opt-out blocks that channel; ...
# field refusal suppresses that ask ... Unknown refusal scope is not broader
# permission." So only the two refusals whose scope is narrower than the
# relationship suppress one ask; every other reason - a global stop, a human
# fence, a channel opt-out recorded without a channel, or anything this module
# does not recognise - stops the sequence. Fail closed, never broaden.
NARROW_CONSENT_REASONS = frozenset({REASON_CHANNEL, REASON_FIELD})


def _consent_is_terminal(reason: str) -> bool:
    """DATA-CONTRACTS section 7 scope. Fail closed: unknown is never broader
    permission, so only the two narrow refusals leave the sequence running."""
    return reason not in NARROW_CONSENT_REASONS


class ReminderError(Exception):
    """Base error. Every refusal here is explicit, never a silent no-op."""


class InvalidPolicy(ReminderError):
    pass


class PolicyNotAdopted(ReminderError):
    pass


class SequenceNotFound(ReminderError):
    pass


class SequenceTerminal(ReminderError):
    pass


class LockBusy(ReminderError):
    def __init__(self, reason: str) -> None:
        super().__init__("contact lock not held: " + reason)
        self.reason = reason


class FinalNotReserved(ReminderError):
    """Only the exact reserved final action may pass while closing_final."""


class FinalRefused(ReminderError):
    """STOP / refusal / human fence refused the reservation itself."""

    def __init__(self, reason: str, decision: Dict[str, Any]) -> None:
        super().__init__("final refused: " + reason)
        self.reason = reason
        self.decision = decision


# ── policy ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ReminderPolicy:
    """The exact policy adopted before activation. Never defaulted silently."""

    version: str
    slot_offsets_seconds: Tuple[float, ...] = DEFAULT_SLOT_OFFSETS_S
    quiet_interval_seconds: float = DEFAULT_QUIET_INTERVAL_S
    final_slot_seconds: float = DEFAULT_FINAL_SLOT_S

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip():
            raise InvalidPolicy("policy version is required")
        offsets = tuple(float(x) for x in self.slot_offsets_seconds)
        if not 1 <= len(offsets) <= MAX_REMINDERS:
            raise InvalidPolicy(
                "a policy carries between 1 and %d shared reminder slots"
                % MAX_REMINDERS)
        if any(x < 0 for x in offsets):
            raise InvalidPolicy("slot offsets must be >= 0")
        if list(offsets) != sorted(offsets):
            raise InvalidPolicy("slot offsets must escalate in time order")
        if float(self.quiet_interval_seconds) < 0:
            raise InvalidPolicy("quiet interval must be >= 0")
        if float(self.final_slot_seconds) <= 0:
            raise InvalidPolicy("final slot must be > 0")
        object.__setattr__(self, "slot_offsets_seconds", offsets)
        object.__setattr__(self, "quiet_interval_seconds",
                           float(self.quiet_interval_seconds))
        object.__setattr__(self, "final_slot_seconds",
                           float(self.final_slot_seconds))

    def as_json(self) -> str:
        return json.dumps({
            "version": self.version,
            "slot_offsets_seconds": list(self.slot_offsets_seconds),
            "quiet_interval_seconds": self.quiet_interval_seconds,
            "final_slot_seconds": self.final_slot_seconds,
        }, sort_keys=True, separators=(",", ":"))

    @property
    def slots(self) -> int:
        return len(self.slot_offsets_seconds)


# ── result types ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SlotDecision:
    kind: str                      # none | due | wait
    reason: str = ""
    slot_index: Optional[int] = None
    due_at: Optional[float] = None
    wait_until: Optional[float] = None

    @property
    def due(self) -> bool:
        return self.kind == DECISION_DUE


@dataclass(frozen=True)
class SendResult:
    status: str                    # sent | suppressed | wait | unknown | not_due | refused_race
    slot_index: Optional[int] = None
    action_id: Optional[str] = None
    channel: Optional[str] = None
    reason: str = ""

    @property
    def sent(self) -> bool:
        return self.status == "sent"


@dataclass(frozen=True)
class FinalReservation:
    action_id: str
    state_version: int
    reserved_at: float
    slot_expires_at: float
    created: bool

    def as_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "state_version": self.state_version,
            "reserved_at": self.reserved_at,
            "slot_expires_at": self.slot_expires_at,
            "created": self.created,
        }


@dataclass(frozen=True)
class FinalOutcome:
    status: str                    # sent | admitted | canceled | unknown | reserved | not_claimed
    action_id: str
    state: str
    reason: str = ""
    provider_receipt: Optional[Dict[str, Any]] = field(default=None)

    @property
    def sent(self) -> bool:
        return self.status == "sent"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS reminder_sequences (
  tenant_id              TEXT NOT NULL,
  canonical_contact_id   TEXT NOT NULL,
  collection_sequence_id TEXT NOT NULL,
  state                  TEXT NOT NULL,
  t0                     REAL,
  policy_version         TEXT,
  policy_json            TEXT,
  initial_invitation_id  TEXT,
  reply_eligible         INTEGER NOT NULL DEFAULT 1,
  quiet_until            REAL,
  reminders_used         INTEGER NOT NULL DEFAULT 0,
  final_action_id        TEXT,
  final_slot_expires_at  REAL,
  version                INTEGER NOT NULL DEFAULT 0,
  created_at             REAL NOT NULL,
  updated_at             REAL NOT NULL,
  PRIMARY KEY (tenant_id, canonical_contact_id, collection_sequence_id)
);
CREATE TABLE IF NOT EXISTS reminder_slots (
  tenant_id              TEXT NOT NULL,
  canonical_contact_id   TEXT NOT NULL,
  collection_sequence_id TEXT NOT NULL,
  slot_index             INTEGER NOT NULL,
  due_at                 REAL NOT NULL,
  status                 TEXT NOT NULL,
  channel                TEXT,
  action_id              TEXT,
  sent_at                REAL,
  reason                 TEXT,
  updated_at             REAL NOT NULL,
  PRIMARY KEY (tenant_id, canonical_contact_id, collection_sequence_id, slot_index)
);
CREATE TABLE IF NOT EXISTS reminder_events (
  event_id               INTEGER PRIMARY KEY AUTOINCREMENT,
  tenant_id              TEXT NOT NULL,
  canonical_contact_id   TEXT NOT NULL,
  collection_sequence_id TEXT NOT NULL,
  event                  TEXT NOT NULL,
  payload                TEXT NOT NULL,
  at                     REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS reminder_final_reservations (
  tenant_id              TEXT NOT NULL,
  canonical_contact_id   TEXT NOT NULL,
  collection_sequence_id TEXT NOT NULL,
  action_id              TEXT NOT NULL UNIQUE,
  reserved_at            REAL NOT NULL,
  state_version          INTEGER NOT NULL,
  PRIMARY KEY (tenant_id, canonical_contact_id, collection_sequence_id)
);
"""


def _key(tenant_id: str, contact: str, seq: str) -> Tuple[str, str, str]:
    for value, name in ((tenant_id, "tenant_id"),
                        (contact, "canonical_contact_id"),
                        (seq, "collection_sequence_id")):
        if not isinstance(value, str) or not value.strip():
            raise ReminderError("%s is required" % name)
    return (tenant_id.strip(), contact.strip(), seq.strip())


def _action_id(kind: str, tenant_id: str, contact: str, seq: str,
               index: Any) -> str:
    raw = "%s|%s|%s|%s|%s" % (kind, tenant_id, contact, seq, index)
    return "%s_%s" % (kind, hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24])


class ReminderStateMachine:
    """One contact sequence: three shared reminder slots and one final action.

    identity  TenantIdentity   the tenant/contact database (verification + lock)
    store     DurableStore     the outbox (idempotent actions + receipts)
    consent   ConsentStore     optional; defaults to ConsentStore(identity)
    lock      CollectionLock   optional; defaults to CollectionLock(identity)
    """

    def __init__(self, identity: TenantIdentity, store: DurableStore,
                 consent: Optional[ConsentStore] = None,
                 lock: Optional[CollectionLock] = None) -> None:
        if not isinstance(identity, TenantIdentity):
            raise TypeError("ReminderStateMachine requires a TenantIdentity")
        if not isinstance(store, DurableStore):
            raise TypeError("ReminderStateMachine requires a DurableStore")
        self.identity = identity
        self.store = store
        self.consent = consent or ConsentStore(identity)
        self.lock = lock or CollectionLock(identity)
        self._handoffs: Optional[HandoffStore] = None
        self.init_schema()

    # ── the T-29 handoff fence ─────────────────────────────────────────────

    @property
    def handoffs(self) -> HandoffStore:
        """The T-29 handoff lifecycle over the same tenant database.

        Lazy: the store creates its two additive tables on first use, in the
        identity database, so one database stays one tenant boundary.
        """
        if self._handoffs is None:
            self._handoffs = HandoffStore(self.identity.db_path)
        return self._handoffs

    def _gate_evaluator(self) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
        """The consent evaluator with the T-29 human handoff fence in front.

        Both must ALLOW. An open handoff suppresses the send even when the
        consent fence flag is not set (gate_decision reads the handoff rows as
        well as the fence), and an unverifiable contact fails closed rather
        than sending on a guess.

        consent_guard is carried through so outbound_gate re-runs this exact
        evaluator at the point of use: a handoff opened, or a STOP recorded,
        while the first verdict was being computed still blocks the send.
        """
        consent_evaluator = make_gate_evaluator(self.consent)

        def evaluate(ctx: Dict[str, Any]) -> Dict[str, Any]:
            verdict = consent_evaluator(ctx)
            if verdict.get("verdict") != "ALLOW":
                return verdict
            action = ctx.get("action") or {}
            contact = action.get("canonical_contact_id")
            if not contact:
                return verdict
            # evaluate_gate floats checked_at, so it is never None here.
            at = ctx.get("now")
            at = time.time() if at is None else at
            try:
                decision = self.handoffs.gate_decision(
                    action.get("tenant_id"), contact)
            except HandoffError as exc:
                return {"verdict": "SUPPRESSED", "checked_at": at,
                        "evidence": {"reason": "handoff:unavailable",
                                     "error": str(exc)[:200]}}
            if decision["verdict"] == "ALLOW":
                return verdict
            return {"verdict": "SUPPRESSED", "checked_at": at,
                    "evidence": {"reason": decision["reason"],
                                 "handoff_id": decision["handoff_id"],
                                 "bot_paused": decision["bot_paused"],
                                 "source": "handoff"}}

        evaluate.consent_guard = True
        return evaluate

    # ── storage ────────────────────────────────────────────────────────────

    def init_schema(self) -> None:
        conn = self.identity.connection()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = FULL")
            conn.executescript(_SCHEMA)
        finally:
            conn.close()

    def _write(self) -> sqlite3.Connection:
        conn = self.identity.connection()
        conn.execute("BEGIN IMMEDIATE")
        return conn

    def _row(self, tenant_id: str, contact: str, seq: str) -> Optional[Dict[str, Any]]:
        conn = self.identity.connection()
        try:
            row = conn.execute(
                "SELECT * FROM reminder_sequences WHERE tenant_id=?"
                " AND canonical_contact_id=? AND collection_sequence_id=?",
                (tenant_id, contact, seq)).fetchone()
            return dict(row) if row is not None else None
        finally:
            conn.close()

    def _require_row(self, tenant_id: str, contact: str, seq: str) -> Dict[str, Any]:
        row = self._row(tenant_id, contact, seq)
        if row is None:
            raise SequenceNotFound("no reminder sequence for that contact key")
        return row

    def _event(self, conn: sqlite3.Connection, key: Tuple[str, str, str],
               event: str, payload: Dict[str, Any], at: float) -> None:
        conn.execute(
            "INSERT INTO reminder_events (tenant_id, canonical_contact_id,"
            " collection_sequence_id, event, payload, at) VALUES (?,?,?,?,?,?)",
            key + (event, json.dumps(payload, sort_keys=True,
                                     separators=(",", ":")), at))

    def _bump(self, conn: sqlite3.Connection, key: Tuple[str, str, str],
              *, state: Optional[str] = None, at: float,
              **columns: Any) -> int:
        sets: List[str] = ["version = version + 1", "updated_at = ?"]
        values: List[Any] = [at]
        if state is not None:
            sets.append("state = ?")
            values.append(state)
        for name, value in columns.items():
            sets.append("%s = ?" % name)
            values.append(value)
        values.extend(key)
        conn.execute(
            "UPDATE reminder_sequences SET %s WHERE tenant_id=?"
            " AND canonical_contact_id=? AND collection_sequence_id=?"
            % ", ".join(sets), tuple(values))
        row = conn.execute(
            "SELECT version FROM reminder_sequences WHERE tenant_id=?"
            " AND canonical_contact_id=? AND collection_sequence_id=?",
            key).fetchone()
        return int(row["version"])

    def events(self, tenant_id: str, contact: str, seq: str) -> List[Dict[str, Any]]:
        key = _key(tenant_id, contact, seq)
        conn = self.identity.connection()
        try:
            rows = conn.execute(
                "SELECT event, payload, at FROM reminder_events WHERE tenant_id=?"
                " AND canonical_contact_id=? AND collection_sequence_id=?"
                " ORDER BY event_id", key).fetchall()
            return [{"event": r["event"], "payload": json.loads(r["payload"]),
                     "at": r["at"]} for r in rows]
        finally:
            conn.close()

    # ── policy and opening a sequence ──────────────────────────────────────

    def adopt_policy(self, tenant_id: str, contact: str, seq: str,
                     policy: ReminderPolicy, *, now: Optional[float] = None
                     ) -> Dict[str, Any]:
        """Adopt the exact policy. Activation without it is refused."""
        if not isinstance(policy, ReminderPolicy):
            raise InvalidPolicy("an explicit ReminderPolicy is required")
        key = _key(tenant_id, contact, seq)
        self.identity.verify(tenant_id, contact)
        ts = time.time() if now is None else float(now)
        conn = self._write()
        try:
            self._bump(conn, key, at=ts, policy_version=policy.version,
                       policy_json=policy.as_json())
            self._event(conn, key, "policy_adopted",
                        {"policy": json.loads(policy.as_json())}, ts)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        return self._require_row(*key)

    def open_sequence(self, tenant_id: str, contact: str, seq: str, *,
                      request_id: Optional[str] = None,
                      now: Optional[float] = None) -> Dict[str, Any]:
        """Open or return the ONE sequence for this contact.

        A returning or overlapping request shares the existing sequence: its
        t0, used count and refusals are never reset. A terminal sequence is
        returned as-is; a late request may be served without restarting
        capture, and capture is not restarted here. In particular a contact
        that has already stopped keeps that stopped sequence: no second
        sequence is ever minted for them, so no fresh t0, no fresh slots and
        no fresh budget can appear behind a stopped capture.
        """
        key = _key(tenant_id, contact, seq)
        self.identity.verify(tenant_id, contact)
        ts = time.time() if now is None else float(now)
        existing = self._row(*key)
        if existing is None:
            # Overlapping requests share the sequence even when the caller
            # minted a new sequence id for the same contact.
            conn = self.identity.connection()
            try:
                row = conn.execute(
                    "SELECT * FROM reminder_sequences WHERE tenant_id=?"
                    " AND canonical_contact_id=? AND state NOT IN (%s)"
                    " ORDER BY created_at LIMIT 1"
                    % ",".join("?" * len(TERMINAL_STATES)),
                    (tenant_id, contact) + tuple(sorted(TERMINAL_STATES))
                ).fetchone()
                if row is not None:
                    existing = dict(row)
                else:
                    # Nothing live and nothing minted under this id: reuse the
                    # stopped sequence rather than reopening capture.
                    stopped = conn.execute(
                        "SELECT * FROM reminder_sequences WHERE tenant_id=?"
                        " AND canonical_contact_id=? AND state IN (%s)"
                        " ORDER BY created_at LIMIT 1"
                        % ",".join("?" * len(TERMINAL_STATES)),
                        (tenant_id, contact) + tuple(sorted(TERMINAL_STATES))
                    ).fetchone()
                    if stopped is not None:
                        existing = dict(stopped)
                if existing is not None:
                    key = (existing["tenant_id"],
                           existing["canonical_contact_id"],
                           existing["collection_sequence_id"])
            finally:
                conn.close()
        conn = self._write()
        try:
            if existing is None:
                conn.execute(
                    "INSERT INTO reminder_sequences (tenant_id,"
                    " canonical_contact_id, collection_sequence_id, state,"
                    " created_at, updated_at) VALUES (?,?,?,?,?,?)",
                    key + (STATE_INVITED, ts, ts))
                self._event(conn, key, "sequence_opened",
                            {"request_id": request_id}, ts)
            else:
                self._event(conn, key, "sequence_reused",
                            {"request_id": request_id,
                             "state": existing["state"]}, ts)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        return self._require_row(*key)

    # ── initial invitation, reply, pause ───────────────────────────────────

    def record_initial_invitation(self, tenant_id: str, contact: str, seq: str,
                                  *, invitation_id: str, channel: str = "",
                                  now: Optional[float] = None) -> Dict[str, Any]:
        """The invitation is separate. It creates t0 and the three slots once.

        A repeat invitation is recorded but changes neither t0 nor the budget:
        a returning request never restarts the sequence.
        """
        if not isinstance(invitation_id, str) or not invitation_id.strip():
            raise ReminderError("invitation_id is required")
        key = _key(tenant_id, contact, seq)
        row = self._require_row(*key)
        if row["state"] in TERMINAL_STATES or row["state"] == STATE_CLOSING_FINAL:
            raise SequenceTerminal("sequence is already %s" % row["state"])
        ts = time.time() if now is None else float(now)
        conn = self._write()
        try:
            if row["t0"] is None:
                policy = self._policy(row)
                conn.execute(
                    "UPDATE reminder_sequences SET t0=?, initial_invitation_id=?,"
                    " state=?, updated_at=? WHERE tenant_id=?"
                    " AND canonical_contact_id=? AND collection_sequence_id=?"
                    " AND t0 IS NULL",
                    (ts, invitation_id, STATE_INVITED, ts) + key)
                for index, offset in enumerate(policy.slot_offsets_seconds):
                    conn.execute(
                        "INSERT OR IGNORE INTO reminder_slots (tenant_id,"
                        " canonical_contact_id, collection_sequence_id,"
                        " slot_index, due_at, status, updated_at)"
                        " VALUES (?,?,?,?,?,?,?)",
                        key + (index, ts + offset, SLOT_PENDING, ts))
                version = self._bump(conn, key, at=ts)
                self._event(conn, key, "initial_invitation", {
                    "invitation_id": invitation_id,
                    "channel": channel,
                    "t0": ts,
                    "slots": len(policy.slot_offsets_seconds),
                    "state_version": version,
                }, ts)
            else:
                self._event(conn, key, "initial_invitation_repeated", {
                    "invitation_id": invitation_id,
                    "channel": channel,
                    "t0": row["t0"],
                    "note": "separate invitation; t0 and budget unchanged",
                }, ts)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        return self._require_row(*key)

    def record_reply(self, tenant_id: str, contact: str, seq: str, *,
                     reply_id: str = "", now: Optional[float] = None
                     ) -> Dict[str, Any]:
        """A reply changes eligibility only. t0 and the budget stay put."""
        key = _key(tenant_id, contact, seq)
        row = self._require_row(*key)
        if row["state"] in TERMINAL_STATES:
            raise SequenceTerminal("sequence is already %s" % row["state"])
        ts = time.time() if now is None else float(now)
        conn = self._write()
        try:
            self._bump(conn, key, at=ts, reply_eligible=0)
            self._event(conn, key, "reply_recorded",
                        {"reply_id": reply_id, "t0": row["t0"],
                         "reminders_used": row["reminders_used"]}, ts)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        return self._require_row(*key)

    def mark_eligible(self, tenant_id: str, contact: str, seq: str, *,
                      reason: str = "new_unresolved_action",
                      now: Optional[float] = None) -> Dict[str, Any]:
        """Eligibility returns; t0 and the used count do not move."""
        key = _key(tenant_id, contact, seq)
        row = self._require_row(*key)
        if row["state"] in TERMINAL_STATES:
            raise SequenceTerminal("sequence is already %s" % row["state"])
        ts = time.time() if now is None else float(now)
        conn = self._write()
        try:
            self._bump(conn, key, at=ts, reply_eligible=1)
            self._event(conn, key, "eligibility_restored", {"reason": reason}, ts)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        return self._require_row(*key)

    def pause(self, tenant_id: str, contact: str, seq: str, *,
              reason: str = "paused", now: Optional[float] = None
              ) -> Dict[str, Any]:
        key = _key(tenant_id, contact, seq)
        row = self._require_row(*key)
        if row["state"] in TERMINAL_STATES:
            raise SequenceTerminal("sequence is already %s" % row["state"])
        ts = time.time() if now is None else float(now)
        conn = self._write()
        try:
            self._bump(conn, key, at=ts, state=STATE_PAUSED)
            self._event(conn, key, "paused", {"reason": reason}, ts)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        return self._require_row(*key)

    def resume(self, tenant_id: str, contact: str, seq: str, *,
               state: str = STATE_INVITED, now: Optional[float] = None
               ) -> Dict[str, Any]:
        if state not in COLLECTION_STATES or state in TERMINAL_STATES:
            raise ReminderError("bad_input: %r is not a live collection state"
                                % (state,))
        key = _key(tenant_id, contact, seq)
        row = self._require_row(*key)
        if row["state"] in TERMINAL_STATES:
            raise SequenceTerminal("sequence is already %s" % row["state"])
        ts = time.time() if now is None else float(now)
        conn = self._write()
        try:
            self._bump(conn, key, at=ts, state=state)
            self._event(conn, key, "resumed", {"state": state}, ts)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        return self._require_row(*key)

    # ── slots ──────────────────────────────────────────────────────────────

    def decline(self, tenant_id: str, contact: str, seq: str, *,
                reason: str = REASON_DECLINED,
                now: Optional[float] = None) -> Dict[str, Any]:
        """The person declines the collection: it closes stopped_declined.

        DATA-CONTRACTS section 8 names `stopped_declined` as its own terminal
        state, so a declined collection must reach it through a real path and
        never be folded into stopped_complete. A decline stops what is still
        open - the pending reminders and a reserved final action - never
        un-sends anything, and never claims a send it did not make.
        """
        key = _key(tenant_id, contact, seq)
        row = self._require_row(*key)
        if row["state"] in TERMINAL_STATES:
            raise SequenceTerminal("sequence is already %s" % row["state"])
        ts = time.time() if now is None else float(now)
        conn = self._write()
        try:
            suppressed = self._cancel_siblings(conn, key, ts, reason=reason,
                                               status=SLOT_SUPPRESSED)
            self._bump(conn, key, at=ts, state=STATE_STOPPED_DECLINED)
            self._event(conn, key, "collection_declined", {
                "reason": reason,
                "suppressed_action_ids": suppressed}, ts)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        if row["final_action_id"]:
            try:
                self.store.cancel(row["final_action_id"], reason, now=ts)
            except DurableStoreError:
                # Already dispatched or canceled: never claim it was unsent.
                pass
        return self._require_row(*key)


    def _policy(self, row: Dict[str, Any]) -> ReminderPolicy:
        if not row.get("policy_json") or not row.get("policy_version"):
            raise PolicyNotAdopted(
                "adopt an explicit ReminderPolicy before activation")
        data = json.loads(row["policy_json"])
        return ReminderPolicy(
            version=data["version"],
            slot_offsets_seconds=tuple(data["slot_offsets_seconds"]),
            quiet_interval_seconds=data["quiet_interval_seconds"],
            final_slot_seconds=data["final_slot_seconds"])

    def _slots(self, key: Tuple[str, str, str]) -> List[Dict[str, Any]]:
        conn = self.identity.connection()
        try:
            rows = conn.execute(
                "SELECT * FROM reminder_slots WHERE tenant_id=?"
                " AND canonical_contact_id=? AND collection_sequence_id=?"
                " ORDER BY slot_index", key).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def _skip(self, conn: sqlite3.Connection, key: Tuple[str, str, str],
              slot_index: int, reason: str, at: float) -> None:
        conn.execute(
            "UPDATE reminder_slots SET status=?, reason=?, updated_at=?"
            " WHERE tenant_id=? AND canonical_contact_id=?"
            " AND collection_sequence_id=? AND slot_index=?"
            " AND status=?",
            (SLOT_SKIPPED, reason, at) + key + (slot_index, SLOT_PENDING))
        self._event(conn, key, "slot_skipped",
                    {"slot_index": slot_index, "reason": reason}, at)

    def due_slot(self, tenant_id: str, contact: str, seq: str, *,
                 now: Optional[float] = None) -> SlotDecision:
        """What is sendable right now, applying the contract's timing rules.

        Side effect, by contract: when a reminder actually goes out and more
        than one slot is overdue, the later ones are recorded skipped ("no
        catch-up burst; skipped slots remain recorded"). They are not
        rescheduled and no replacement slot is added. A send that is only
        DEFERRED consumes nothing: while the quiet interval holds every
        overdue slot stays pending, so the skip follows a real send and never
        a postponed one.
        """
        key = _key(tenant_id, contact, seq)
        row = self._require_row(*key)
        if row["state"] in TERMINAL_STATES:
            return SlotDecision(DECISION_NONE, "sequence_terminal")
        if row["state"] == STATE_CLOSING_FINAL:
            return SlotDecision(DECISION_NONE, "closing_final")
        if row["state"] in (STATE_PAUSED, STATE_HUMAN_OWNED):
            return SlotDecision(DECISION_NONE, row["state"])
        if not int(row["reply_eligible"]):
            return SlotDecision(DECISION_NONE, "reply_recorded")
        if row["t0"] is None:
            return SlotDecision(DECISION_NONE, "no_initial_invitation")
        self._policy(row)

        ts = time.time() if now is None else float(now)
        overdue = [s for s in self._slots(key)
                   if s["status"] == SLOT_PENDING and s["due_at"] <= ts]
        if not overdue:
            return SlotDecision(DECISION_NONE, "no_slot_due")

        slot = overdue[0]
        quiet = row["quiet_until"]
        if quiet is not None and ts < float(quiet):
            return SlotDecision(DECISION_WAIT, "quiet_interval",
                                slot_index=slot["slot_index"],
                                due_at=slot["due_at"],
                                wait_until=float(quiet))

        if len(overdue) > 1:
            conn = self._write()
            try:
                for later in overdue[1:]:
                    self._skip(conn, key, later["slot_index"],
                               REASON_NO_CATCH_UP, ts)
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

        return SlotDecision(DECISION_DUE, "due", slot_index=slot["slot_index"],
                            due_at=slot["due_at"])
    # ── sending a reminder ─────────────────────────────────────────────────

    def send_reminder(self, tenant_id: str, contact: str, seq: str,
                      sender: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]],
                      *, channel: str, worker_id: str = "reminder-worker",
                      topic: Optional[str] = None,
                      offer: Optional[str] = None,
                      campaign: Optional[str] = None,
                      now: Optional[float] = None,
                      lease_seconds: float = 60.0,
                      before_dispatch: Optional[Callable[[str], None]] = None
                      ) -> SendResult:
        """Reserve and dispatch ONE due reminder through the common gate.

        The contact lock is held for the reservation. The gate is evaluated
        fresh inside dispatch(), so a STOP, refusal or human fence recorded
        after the action was queued still blocks the send.
        """
        key = _key(tenant_id, contact, seq)
        ts = time.time() if now is None else float(now)
        lease = self.lock.acquire(tenant_id, contact, seq, worker_id,
                                  lease_seconds=lease_seconds)
        if not lease:
            raise LockBusy(lease.reason)
        if before_dispatch is not None and not callable(before_dispatch):
            raise ReminderError("bad_input: before_dispatch must be callable")
        try:
            row = self._require_row(*key)
            if row["state"] in TERMINAL_STATES:
                return SendResult("not_due", reason="sequence_terminal")
            decision = self.due_slot(tenant_id, contact, seq, now=ts)
            if decision.kind == DECISION_NONE:
                return SendResult("not_due", reason=decision.reason)
            if decision.kind == DECISION_WAIT:
                return SendResult("wait", slot_index=decision.slot_index,
                                  reason=decision.reason, channel=channel)

            slot_index = int(decision.slot_index)
            aid = _action_id("rem", tenant_id, contact, seq, slot_index)

            # Queue-time pre-check. It is NOT permission: dispatch() rechecks.
            pre = self.consent.decide(tenant_id, contact, channel=channel,
                                      topic=topic, offer=offer,
                                      campaign=campaign)
            if not pre["allowed"]:
                return self._record_refused_slot(key, slot_index, channel,
                                                 pre["reason"], ts,
                                                 source="queue")

            intent = "reminder:%s:%s:%s" % (seq, slot_index, channel)
            row_out, created = self.store.create_intent(
                logical_intent_key=intent, idempotency_key=intent,
                tenant_id=tenant_id, scope="person_directed",
                content_sha256="reminder:" + str(slot_index),
                purpose="reminder", canonical_contact_id=contact,
                action_id=aid, now=ts)
            if row_out["state"] == STATE_NOT_REQUESTED:
                self.store.queue(aid, now=ts)

            conn = self._write()
            try:
                conn.execute(
                    "UPDATE reminder_slots SET action_id=?, channel=?,"
                    " status=?, updated_at=? WHERE tenant_id=?"
                    " AND canonical_contact_id=?"
                    " AND collection_sequence_id=? AND slot_index=?",
                    (aid, channel, SLOT_PENDING, ts) + key + (slot_index,))
                self._event(conn, key, "slot_reserved", {
                    "slot_index": slot_index, "channel": channel,
                    "action_id": aid, "created": created}, ts)
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

            if before_dispatch is not None:
                before_dispatch(aid)

            # The race is re-checked here too, not only at reserve: a pause, a
            # human takeover or a reply recorded between the reservation and
            # this call must not be overtaken by the send. Nothing has been
            # sent, so the slot stays pending and the budget is untouched.
            blocked = self._block_reason(self._require_row(*key))
            if blocked is not None:
                self._event_write(key, "slot_aborted_before_dispatch", {
                    "slot_index": slot_index, "channel": channel,
                    "action_id": aid, "reason": blocked}, ts)
                return SendResult("refused_race", slot_index=slot_index,
                                  action_id=aid, channel=channel,
                                  reason=blocked)

            evaluator = self._gate_evaluator()
            outcome = dispatch(
                self.store, evaluator, sender, aid, worker_id,
                now=ts, lease_seconds=lease_seconds,
                context={"channel": channel, "topic": topic,
                         "offer": offer, "campaign": campaign})

            return self._apply_reminder_outcome(key, slot_index, channel,
                                                outcome, ts)
        finally:
            try:
                self.lock.release(tenant_id, contact, seq, worker_id,
                                  lease.fence)
            except Exception:
                # The lease expires on its own; never mask the send result.
                pass

    # ── shared race and refusal helpers ────────────────────────────────────

    @staticmethod
    def _block_reason(row: Dict[str, Any]) -> Optional[str]:
        """Why this sequence may not send right now, or None when it may.

        Read fresh at the moment of use. The consent gate re-checks STOP and
        the fences itself; this covers the state a queue-time read can miss -
        a pause, a human takeover or a reply recorded in between.
        """
        if row["state"] in TERMINAL_STATES:
            return "sequence_terminal"
        if row["state"] == STATE_CLOSING_FINAL:
            return "closing_final"
        if row["state"] in (STATE_PAUSED, STATE_HUMAN_OWNED):
            return row["state"]
        if not int(row["reply_eligible"]):
            return "reply_recorded"
        return None

    def _event_write(self, key: Tuple[str, str, str], event: str,
                     payload: Dict[str, Any], at: float) -> None:
        """Append one event in its own transaction."""
        conn = self._write()
        try:
            self._event(conn, key, event, payload, at)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def _record_refused_slot(self, key: Tuple[str, str, str], slot_index: int,
                             channel: str, reason: str, ts: float, *,
                             source: str) -> SendResult:
        """Record a reminder the consent gate refused.

        Scope follows DATA-CONTRACTS section 7: a refusal narrower than the
        relationship - a channel opt-out or a field refusal - suppresses THIS
        ask and leaves the shared budget live for the channels and asks it
        does not cover. Anything else is not broader permission, so it stops
        the sequence.
        """
        terminal = _consent_is_terminal(reason)
        # ponytail: a narrow refusal spends the slot as "suppressed" rather
        # than returning it to the pool, so a caller that only ever uses the
        # opted-out channel spends the budget on refusals instead of sends.
        # Ceiling is "at most three shared reminders" and slot order, both
        # held. Upgrade path: a channel-capable scheduler that picks another
        # eligible channel for the same slot before suppressing it.
        conn = self._write()
        try:
            conn.execute(
                "UPDATE reminder_slots SET status=?, reason=?, channel=?,"
                " updated_at=? WHERE tenant_id=? AND canonical_contact_id=?"
                " AND collection_sequence_id=? AND slot_index=? AND status=?",
                (SLOT_SUPPRESSED, reason, channel, ts)
                + key + (slot_index, SLOT_PENDING))
            if terminal:
                self._bump(conn, key, at=ts, state=STATE_STOPPED_COMPLETE)
            else:
                self._bump(conn, key, at=ts)
            self._event(conn, key, "slot_suppressed", {
                "slot_index": slot_index,
                "channel": channel,
                "reason": reason,
                "source": source,
                "scope": "sequence" if terminal else "that_ask",
            }, ts)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        return SendResult("suppressed", slot_index=slot_index, channel=channel,
                          reason=reason)

    def _apply_reminder_outcome(self, key: Tuple[str, str, str],
                                slot_index: int, channel: str,
                                outcome: Any, ts: float) -> SendResult:
        status = outcome.status
        aid = outcome.action_id
        conn = self._write()
        try:
            if status == ST_SENT:
                conn.execute(
                    "UPDATE reminder_slots SET status=?, sent_at=?,"
                    " action_id=?, channel=?, updated_at=? WHERE tenant_id=?"
                    " AND canonical_contact_id=?"
                    " AND collection_sequence_id=? AND slot_index=?",
                    (SLOT_SENT, ts, aid, channel, ts) + key + (slot_index,))
                self._bump(conn, key, at=ts,
                           quiet_until=ts + self._policy(
                               self._row(*key)).quiet_interval_seconds)
                conn.execute(
                    "UPDATE reminder_sequences SET reminders_used ="
                    " reminders_used + 1 WHERE tenant_id=?"
                    " AND canonical_contact_id=?"
                    " AND collection_sequence_id=?",
                    key)
                self._event(conn, key, "slot_sent", {
                    "slot_index": slot_index, "channel": channel,
                    "action_id": aid}, ts)
                conn.execute("COMMIT")
                return SendResult("sent", slot_index=slot_index, action_id=aid,
                                  channel=channel)

            if status == ST_BLOCKED and outcome.verdict == "SUPPRESSED":
                reason = outcome.note or "gate:suppressed"
                terminal = _consent_is_terminal(reason)
                conn.execute(
                    "UPDATE reminder_slots SET status=?, reason=?, action_id=?,"
                    " channel=?, updated_at=? WHERE tenant_id=?"
                    " AND canonical_contact_id=?"
                    " AND collection_sequence_id=? AND slot_index=?",
                    (SLOT_SUPPRESSED, reason, aid, channel, ts)
                    + key + (slot_index,))
                if terminal:
                    self._bump(conn, key, at=ts, state=STATE_STOPPED_COMPLETE)
                else:
                    self._bump(conn, key, at=ts)
                self._event(conn, key, "slot_suppressed_at_gate", {
                    "slot_index": slot_index, "channel": channel,
                    "action_id": aid, "reason": reason,
                    "scope": "sequence" if terminal else "that_ask"}, ts)
                conn.execute("COMMIT")
                return SendResult("suppressed", slot_index=slot_index,
                                  action_id=aid, channel=channel,
                                  reason=reason)

            if status == ST_BLOCKED:  # WAIT_UNTIL or RECONCILE_UNKNOWN
                self._event(conn, key, "slot_deferred_at_gate", {
                    "slot_index": slot_index, "channel": channel,
                    "action_id": aid, "verdict": outcome.verdict,
                    "note": outcome.note}, ts)
                conn.execute("COMMIT")
                return SendResult("wait", slot_index=slot_index, action_id=aid,
                                  channel=channel, reason=outcome.note or "")

            if status in (ST_SEND_ERROR, ST_UNKNOWN):
                conn.execute(
                    "UPDATE reminder_slots SET status=?, reason=?, action_id=?,"
                    " channel=?, updated_at=? WHERE tenant_id=?"
                    " AND canonical_contact_id=?"
                    " AND collection_sequence_id=? AND slot_index=?",
                    (SLOT_UNKNOWN, outcome.note or "no_verdict", aid, channel,
                     ts) + key + (slot_index,))
                self._event(conn, key, "slot_unknown", {
                    "slot_index": slot_index, "channel": channel,
                    "action_id": aid, "note": outcome.note}, ts)
                conn.execute("COMMIT")
                return SendResult("unknown", slot_index=slot_index,
                                  action_id=aid, channel=channel,
                                  reason=outcome.note or "")

            # not_claimed / refused_race: nothing was sent. Leave the slot
            # pending so the next attempt is a genuine fresh-gate decision.
            self._event(conn, key, "slot_not_sent", {
                "slot_index": slot_index, "channel": channel, "action_id": aid,
                "status": status, "note": outcome.note}, ts)
            conn.execute("COMMIT")
            return SendResult("refused_race" if status == ST_REFUSED_RACE
                              else "not_due", slot_index=slot_index,
                              action_id=aid, channel=channel,
                              reason=outcome.note or "")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    # ── the reserved final action ──────────────────────────────────────────

    def reserve_final(self, tenant_id: str, contact: str, seq: str, *,
                      channel: str, content_sha256: str,
                      worker_id: str = "final-worker",
                      topic: Optional[str] = None,
                      offer: Optional[str] = None,
                      campaign: Optional[str] = None,
                      now: Optional[float] = None,
                      lease_seconds: float = 60.0) -> FinalReservation:
        """Under the contact lock: reserve ONE final action, cancel siblings.

        Idempotent: a second call returns the SAME reservation. It never mints
        a second final. A STOP/refusal/human fence refuses the reservation
        itself, so there is no bypass-stop exception later.
        """
        key = _key(tenant_id, contact, seq)
        ts = time.time() if now is None else float(now)
        lease = self.lock.acquire(tenant_id, contact, seq, worker_id,
                                  lease_seconds=lease_seconds)
        if not lease:
            raise LockBusy(lease.reason)
        try:
            row = self._require_row(*key)
            if row["state"] in TERMINAL_STATES:
                raise SequenceTerminal("sequence is already %s" % row["state"])
            # Pause and human ownership are part of the same race as STOP: a
            # paused sequence cannot reserve a closing action, so the final
            # path cannot slip past a pause the reminder path honours.
            if row["state"] in (STATE_PAUSED, STATE_HUMAN_OWNED):
                raise FinalRefused(row["state"], {
                    "allowed": False, "reason": row["state"], "blocking": None})

            existing = self._reservation(key)
            if existing is not None:
                return FinalReservation(
                    action_id=existing["action_id"],
                    state_version=int(existing["state_version"]),
                    reserved_at=float(existing["reserved_at"]),
                    slot_expires_at=float(row["final_slot_expires_at"] or 0.0),
                    created=False)

            policy = self._policy(row)
            decision = self.consent.decide(
                tenant_id, contact, channel=channel, topic=topic,
                offer=offer, campaign=campaign)
            if not decision["allowed"]:
                # Same scope rule as a reminder (DATA-CONTRACTS s7): a channel
                # opt-out or a field refusal refuses only THIS final, so a
                # final on another channel or topic can still be reserved. A
                # global stop, a human fence or an unknown reason closes.
                terminal = _consent_is_terminal(decision["reason"])
                conn = self._write()
                try:
                    if terminal:
                        self._bump(conn, key, at=ts,
                                   state=STATE_STOPPED_COMPLETE)
                    else:
                        self._bump(conn, key, at=ts)
                    self._event(conn, key, "final_refused", {
                        "channel": channel, "reason": decision["reason"],
                        "scope": "sequence" if terminal else "that_final"},
                        ts)
                    conn.execute("COMMIT")
                except BaseException:
                    conn.execute("ROLLBACK")
                    raise
                finally:
                    conn.close()
                raise FinalRefused(decision["reason"], decision)

            aid = _action_id("fin", tenant_id, contact, seq, "final")
            intent = "final:%s" % seq
            self.store.create_intent(
                logical_intent_key=intent, idempotency_key=intent,
                tenant_id=tenant_id, scope="person_directed",
                content_sha256=content_sha256, purpose="final_action",
                canonical_contact_id=contact, action_id=aid, now=ts)
            if self.store.get_action(aid)["state"] == STATE_NOT_REQUESTED:
                self.store.queue(aid, now=ts)

            conn = self._write()
            try:
                version = self._bump(
                    conn, key, at=ts, state=STATE_CLOSING_FINAL,
                    final_action_id=aid,
                    final_slot_expires_at=ts + policy.final_slot_seconds)
                conn.execute(
                    "INSERT INTO reminder_final_reservations (tenant_id,"
                    " canonical_contact_id, collection_sequence_id, action_id,"
                    " reserved_at, state_version) VALUES (?,?,?,?,?,?)",
                    key + (aid, ts, version))
                self._event(conn, key, "final_reserved", {
                    "action_id": aid, "channel": channel,
                    "state_version": version}, ts)

                canceled = self._cancel_siblings(conn, key, ts)
                self._event(conn, key, "final_siblings_canceled",
                            {"action_ids": canceled,
                             "state_version": version}, ts)
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()

            return FinalReservation(
                action_id=aid, state_version=version, reserved_at=ts,
                slot_expires_at=ts + policy.final_slot_seconds, created=True)
        finally:
            try:
                self.lock.release(tenant_id, contact, seq, worker_id,
                                  lease.fence)
            except Exception:
                pass

    def _reservation(self, key: Tuple[str, str, str]) -> Optional[Dict[str, Any]]:
        conn = self.identity.connection()
        try:
            row = conn.execute(
                "SELECT * FROM reminder_final_reservations WHERE tenant_id=?"
                " AND canonical_contact_id=? AND collection_sequence_id=?",
                key).fetchone()
            return dict(row) if row is not None else None
        finally:
            conn.close()

    def _cancel_siblings(self, conn: sqlite3.Connection,
                         key: Tuple[str, str, str], ts: float, *,
                         reason: str = REASON_FINAL_RESERVED,
                         status: str = SLOT_CANCELED) -> List[str]:
        """Cancel every reminder that has not begun a send. Never un-sends."""
        canceled: List[str] = []
        rows = conn.execute(
            "SELECT slot_index, action_id, status FROM reminder_slots"
            " WHERE tenant_id=? AND canonical_contact_id=?"
            " AND collection_sequence_id=? AND status=?",
            key + (SLOT_PENDING,)).fetchall()
        for slot in rows:
            aid = slot["action_id"]
            if aid:
                try:
                    action = self.store.get_action(aid)
                    if action["state"] in (STATE_NOT_REQUESTED, STATE_QUEUED):
                        self.store.cancel(aid, reason, now=ts)
                        canceled.append(aid)
                except DurableStoreError:
                    # Already dispatched or unknown: never claim it was unsent.
                    pass
            conn.execute(
                "UPDATE reminder_slots SET status=?, reason=?, updated_at=?"
                " WHERE tenant_id=? AND canonical_contact_id=?"
                " AND collection_sequence_id=? AND slot_index=?",
                (status, reason, ts) + key + (int(slot["slot_index"]),))
        return canceled

    def _close_if_acknowledged(self, key: Tuple[str, str, str],
                               action_id: str, ts: float, event: str
                               ) -> Optional[FinalOutcome]:
        """The ONLY writer of stopped_final. One ACK contract for the module.

        DATA-CONTRACTS s4 "A 200 admission is not a completed reply" and
        durable_store.record_dispatch "Provider admission is NOT completion;
        ack is a separate receipt". So the closing action has landed only when
        a persisted ACK receipt says so. Dispatch, reconciliation and expiry
        all close through here; without an ACK this returns None and nothing
        is claimed.
        """
        ack = self.store.receipts(action_id).get("ack")
        if ack is None:
            return None
        conn = self._write()
        try:
            self._bump(conn, key, at=ts, state=STATE_STOPPED_FINAL)
            self._event(conn, key, event, {
                "action_id": action_id, "ack": ack["payload"]}, ts)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        return FinalOutcome("sent", action_id, STATE_STOPPED_FINAL,
                            reason="ack_receipt",
                            provider_receipt=ack["payload"])

    def _admitted(self, key: Tuple[str, str, str], action_id: str, ts: float,
                  *, source: str,
                  receipt: Optional[Dict[str, Any]]) -> FinalOutcome:
        """Record a provider ADMISSION that is not an ACK. Never claims sent.

        outbound_gate documents ST_SENT as "provider returned an admission
        receipt" and durable_store.record_dispatch as "Provider admission is
        NOT completion; ack is a separate receipt". So the sequence stays
        closing_final: it closes stopped_final only on a persisted ACK
        (_close_if_acknowledged), and stopped_ineligible without claiming sent
        when the reserved window expires first.
        """
        conn = self._write()
        try:
            self._event(conn, key, "final_admitted", {
                "action_id": action_id, "source": source,
                "provider_receipt": receipt,
                "note": "provider admission is not acceptance"}, ts)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        return FinalOutcome("admitted", action_id, STATE_CLOSING_FINAL,
                            reason="provider_admission_only",
                            provider_receipt=receipt)

    def _field_completed_after(self, key: Tuple[str, str, str],
                               since: float) -> bool:
        """A reply recorded after `since` is the contract's field completion.

        The event log is the record: eligibility can be restored afterwards,
        but the completion that happened while the final was reserved is what
        section 8 step 3 says cancels it.
        """
        conn = self.identity.connection()
        try:
            row = conn.execute(
                "SELECT 1 FROM reminder_events WHERE tenant_id=?"
                " AND canonical_contact_id=? AND collection_sequence_id=?"
                " AND event='reply_recorded' AND at > ? LIMIT 1",
                key + (float(since),)).fetchone()
            return row is not None
        finally:
            conn.close()

    def _cancel_final(self, key: Tuple[str, str, str], action_id: str,
                      reason: str, ts: float) -> FinalOutcome:
        """Cancel the reserved action and close without ever claiming a send."""
        try:
            self.store.cancel(action_id, reason, now=ts)
        except DurableStoreError:
            pass  # already dispatched or canceled: never claim it was unsent
        conn = self._write()
        try:
            self._bump(conn, key, at=ts, state=STATE_STOPPED_COMPLETE)
            self._event(conn, key, "final_canceled", {
                "action_id": action_id, "reason": reason}, ts)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        return FinalOutcome("canceled", action_id, STATE_STOPPED_COMPLETE,
                            reason=reason)

    def dispatch_final(self, tenant_id: str, contact: str, seq: str,
                       action_id: str,
                       sender: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]],
                       *, worker_id: str = "final-worker",
                       channel: Optional[str] = None,
                       topic: Optional[str] = None,
                       offer: Optional[str] = None,
                       campaign: Optional[str] = None,
                       now: Optional[float] = None,
                       lease_seconds: float = 60.0,
                       before_dispatch: Optional[Callable[[str], None]] = None
                       ) -> FinalOutcome:
        """Dispatch ONLY the reserved action, through the ordinary fresh gate.

        There is no general bypass-stop exception: the gate is the consent
        gate. STOP, field completion, refusal or handoff recorded before the
        send cancels the reserved action.
        """
        key = _key(tenant_id, contact, seq)
        row = self._require_row(*key)
        reservation = self._reservation(key)
        if reservation is None or not row["final_action_id"]:
            raise FinalNotReserved("no final action is reserved")
        if (action_id != reservation["action_id"]
                or action_id != row["final_action_id"]):
            raise FinalNotReserved(
                "only the reserved action %r may pass while closing_final"
                % reservation["action_id"])
        if row["state"] in TERMINAL_STATES:
            raise SequenceTerminal("sequence is already %s" % row["state"])
        if row["state"] in (STATE_PAUSED, STATE_HUMAN_OWNED):
            raise FinalRefused(row["state"], {
                "allowed": False, "reason": row["state"], "blocking": None})
        if row["state"] != STATE_CLOSING_FINAL:
            raise ReminderError("bad_state: final dispatch requires closing_final,"
                                " not %s" % row["state"])

        ts = time.time() if now is None else float(now)
        # If this exact action already carries a persisted ACK, it landed:
        # close through the one ACK helper and never dispatch it again.
        landed = self._close_if_acknowledged(key, action_id, ts,
                                            "final_accepted")
        if landed is not None:
            return landed
        if before_dispatch is not None:
            if not callable(before_dispatch):
                raise ReminderError("bad_input: before_dispatch must be callable")
            before_dispatch(action_id)

        # Re-read: the race is decided here, not at reserve time. A pause or a
        # human takeover refuses the dispatch, and a field completion recorded
        # since the reservation cancels the reserved action outright
        # (DATA-CONTRACTS section 8 step 3: "STOP, field completion, refusal or
        # handoff before dispatch cancels the reserved action").
        fresh = self._require_row(*key)
        if fresh["state"] in (STATE_PAUSED, STATE_HUMAN_OWNED):
            raise FinalRefused(fresh["state"], {
                "allowed": False, "reason": fresh["state"], "blocking": None})
        if self._field_completed_after(key, float(reservation["reserved_at"])):
            return self._cancel_final(key, action_id, REASON_FIELD_COMPLETION,
                                      ts)

        evaluator = self._gate_evaluator()
        outcome = dispatch(
            self.store, evaluator, sender, action_id, worker_id,
            now=ts, lease_seconds=lease_seconds,
            context={"channel": channel, "topic": topic, "offer": offer,
                     "campaign": campaign})

        if outcome.status == ST_SENT:
            # ST_SENT is a provider ADMISSION receipt only (outbound_gate:
            # "provider returned an admission receipt"). One ACK contract for
            # the module: the close runs through _close_if_acknowledged, so a
            # bare admission leaves the sequence closing_final and never
            # claims "sent" (DATA-CONTRACTS s4: "A 200 admission is not a
            # completed reply"; s8 step 4: closes without claiming sent).
            closed = self._close_if_acknowledged(key, action_id, ts,
                                                "final_accepted")
            if closed is not None:
                return closed
            return self._admitted(key, action_id, ts, source="dispatch",
                                  receipt=outcome.provider_receipt)

        conn = self._write()
        try:
            if outcome.status == ST_BLOCKED and outcome.verdict == "SUPPRESSED":
                try:
                    self.store.cancel(action_id,
                                      "final_stop:" + str(outcome.note), now=ts)
                except DurableStoreError:
                    pass
                self._bump(conn, key, at=ts, state=STATE_STOPPED_COMPLETE)
                self._event(conn, key, "final_canceled", {
                    "action_id": action_id,
                    "reason": outcome.note or "gate:suppressed"}, ts)
                conn.execute("COMMIT")
                return FinalOutcome("canceled", action_id,
                                    STATE_STOPPED_COMPLETE,
                                    reason=outcome.note or "gate:suppressed")

            if outcome.status in (ST_SEND_ERROR, ST_UNKNOWN):
                self._event(conn, key, "final_dispatch_unknown", {
                    "action_id": action_id, "note": outcome.note}, ts)
                conn.execute("COMMIT")
                return FinalOutcome("unknown", action_id, STATE_CLOSING_FINAL,
                                    reason=outcome.note or "")

            if outcome.status == ST_BLOCKED:  # WAIT_UNTIL / RECONCILE_UNKNOWN
                self._event(conn, key, "final_deferred", {
                    "action_id": action_id, "verdict": outcome.verdict,
                    "note": outcome.note}, ts)
                conn.execute("COMMIT")
                return FinalOutcome("reserved", action_id, STATE_CLOSING_FINAL,
                                    reason=outcome.note or "")

            # not_claimed: already sent, canceled, leased or unresolved.
            self._event(conn, key, "final_not_claimed", {
                "action_id": action_id, "status": outcome.status,
                "note": outcome.note}, ts)
            conn.execute("COMMIT")
            return FinalOutcome("not_claimed", action_id, STATE_CLOSING_FINAL,
                                reason=outcome.note or "")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def reconcile_final(self, tenant_id: str, contact: str, seq: str, *,
                        applied: Optional[bool],
                        receipt: Optional[Dict[str, Any]] = None,
                        now: Optional[float] = None) -> FinalOutcome:
        """After a crash: reconcile the SAME action. Never reserve another.

        applied=True  -> provider acceptance: the receipt is persisted as the
                         ACK and the close runs through the one ACK helper
                         (stopped_final). Without a receipt nothing is proven,
                         so nothing is claimed: "admitted", still closing_final.
        applied=False -> permanent nonexecution: closed, no "sent" claimed
        applied=None  -> still unknown: stays reserved and reconciling
        """
        key = _key(tenant_id, contact, seq)
        row = self._require_row(*key)
        reservation = self._reservation(key)
        if reservation is None:
            raise FinalNotReserved("no final action is reserved")
        if row["state"] in TERMINAL_STATES:
            return FinalOutcome("not_claimed", reservation["action_id"],
                                row["state"], reason="already_terminal")
        if row["state"] != STATE_CLOSING_FINAL:
            raise ReminderError("bad_state: reconcile requires closing_final,"
                                " not %s" % row["state"])
        ts = time.time() if now is None else float(now)
        aid = reservation["action_id"]

        if applied is None:
            try:
                self.store.mark_reconcile_unknown(aid, "still_unresolved",
                                                  now=ts)
            except DurableStoreError:
                pass
            conn = self._write()
            try:
                self._event(conn, key, "final_reconcile_unknown",
                            {"action_id": aid}, ts)
                conn.execute("COMMIT")
            except BaseException:
                conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()
            return FinalOutcome("unknown", aid, STATE_CLOSING_FINAL,
                                reason="still_unresolved")

        if applied:
            if receipt is not None:
                try:
                    self.store.reconcile_applied(aid, receipt, now=ts)
                except DurableStoreError:
                    pass  # already acknowledged by a previous reconciliation
            # Provider acceptance is proven the same way everywhere: the
            # receipt is persisted as the ACK and the close runs through the
            # one ACK helper. Without a receipt nothing is proven, so nothing
            # is claimed and the sequence stays closing_final.
            closed = self._close_if_acknowledged(
                key, aid, ts, "final_reconciled_accepted")
            if closed is not None:
                return closed
            return self._admitted(key, aid, ts, source="reconcile",
                                  receipt=receipt)

        # Permanent nonexecution: close without ever claiming a send.
        try:
            self.store.cancel(aid, "permanent_nonexecution", now=ts)
        except DurableStoreError:
            pass
        self.store.record_reconciliation(
            aid, "not_applied", {"reason": "permanent_nonexecution"}, now=ts)
        conn = self._write()
        try:
            self._bump(conn, key, at=ts, state=STATE_STOPPED_INELIGIBLE)
            self._event(conn, key, "final_closed_without_sent", {
                "action_id": aid}, ts)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        return FinalOutcome("canceled", aid, STATE_STOPPED_INELIGIBLE,
                            reason="permanent_nonexecution")

    def expire_final(self, tenant_id: str, contact: str, seq: str, *,
                     now: Optional[float] = None) -> FinalOutcome:
        """An expired final slot closes, without claiming it was sent.

        A closing action that earned an ACK before the deadline is accepted
        and closes stopped_final. Anything less - including a bare dispatch
        receipt, which durable_store records as "Provider admission is NOT
        completion; ack is a separate receipt" - is not acceptance, so the
        slot expires closed and never claims "sent".
        """
        key = _key(tenant_id, contact, seq)
        row = self._require_row(*key)
        reservation = self._reservation(key)
        if reservation is None:
            raise FinalNotReserved("no final action is reserved")
        if row["state"] in TERMINAL_STATES:
            return FinalOutcome("not_claimed", reservation["action_id"],
                                row["state"], reason="already_terminal")
        if row["state"] != STATE_CLOSING_FINAL:
            raise ReminderError("bad_state: expiry requires closing_final")
        ts = time.time() if now is None else float(now)
        deadline = float(row["final_slot_expires_at"] or 0.0)
        if ts < deadline:
            return FinalOutcome("reserved", reservation["action_id"],
                                STATE_CLOSING_FINAL, reason="slot_not_expired")
        # Acceptance is an ACK, never an admission, and it is proved the same
        # way here as in dispatch and reconciliation: through the one ACK
        # helper. Expiry must not promote a bare dispatch receipt into a
        # claimed send.
        closed = self._close_if_acknowledged(
            key, reservation["action_id"], ts, "final_accepted_at_expiry")
        if closed is not None:
            return closed
        try:
            self.store.cancel(reservation["action_id"], "final_slot_expired",
                              now=ts)
        except DurableStoreError:
            pass
        conn = self._write()
        try:
            self._bump(conn, key, at=ts, state=STATE_STOPPED_INELIGIBLE)
            self._event(conn, key, "final_expired_without_sent", {
                "action_id": reservation["action_id"],
                "deadline": deadline}, ts)
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        return FinalOutcome("canceled", reservation["action_id"],
                            STATE_STOPPED_INELIGIBLE, reason="final_slot_expired")

    # ── read model ─────────────────────────────────────────────────────────

    def snapshot(self, tenant_id: str, contact: str, seq: str) -> Dict[str, Any]:
        key = _key(tenant_id, contact, seq)
        row = self._require_row(*key)
        slots = self._slots(key)
        reservation = self._reservation(key)
        policy = json.loads(row["policy_json"]) if row["policy_json"] else None
        return {
            "tenant_id": row["tenant_id"],
            "canonical_contact_id": row["canonical_contact_id"],
            "collection_sequence_id": row["collection_sequence_id"],
            "state": row["state"],
            "terminal": row["state"] in TERMINAL_STATES,
            "t0": row["t0"],
            "policy_adopted": policy is not None,
            "policy": policy,
            "initial_invitation_id": row["initial_invitation_id"],
            "reply_eligible": bool(int(row["reply_eligible"])),
            "quiet_until": row["quiet_until"],
            "reminders_used": int(row["reminders_used"]),
            "reminders_total": len(slots),
            "slots": [
                {"slot_index": int(s["slot_index"]),
                 "due_at": float(s["due_at"]),
                 "status": s["status"],
                 "channel": s["channel"],
                 "action_id": s["action_id"],
                 "sent_at": s["sent_at"],
                 "reason": s["reason"]}
                for s in slots
            ],
            "final_action_id": row["final_action_id"],
            "final_slot_expires_at": row["final_slot_expires_at"],
            "final_reservation": reservation,
            "version": int(row["version"]),
        }


# ── assert-based self-check ────────────────────────────────────────────────

def _selfcheck() -> int:
    import tempfile

    d = Path(tempfile.mkdtemp(prefix="reminders-selfcheck-"))
    identity = TenantIdentity(str(d / "identity.sqlite"))
    identity.register_tenant("t1", "purple billboard")
    contact = identity.bind("t1", [("sms_number", "+15550100", True)],
                            source="selfcheck")
    store = DurableStore(str(d / "outbox.sqlite"))
    machine = ReminderStateMachine(identity, store)
    passed = 0

    def ok(cond: bool, label: str) -> None:
        nonlocal passed
        if not cond:
            raise AssertionError("FAIL: " + label)
        passed += 1

    seq = "seq-1"
    machine.open_sequence("t1", contact, seq, now=1000.0)
    try:
        machine.record_initial_invitation("t1", contact, seq,
                                          invitation_id="inv-1", now=1001.0)
        raise AssertionError("activation without an adopted policy must fail")
    except PolicyNotAdopted:
        passed += 1

    policy = ReminderPolicy(version="selfcheck/1",
                            slot_offsets_seconds=(10, 25, 150),
                            quiet_interval_seconds=60, final_slot_seconds=60)
    machine.adopt_policy("t1", contact, seq, policy, now=1002.0)
    machine.record_initial_invitation("t1", contact, seq,
                                      invitation_id="inv-1", now=1010.0)
    snap = machine.snapshot("t1", contact, seq)
    ok(snap["initial_invitation_id"] == "inv-1", "invitation recorded separately")
    ok(snap["reminders_used"] == 0 and snap["reminders_total"] == 3,
       "three slots, none used")
    ok(snap["t0"] == 1010.0, "t0 from the first actionable invitation")

    again = machine.open_sequence("t1", contact, "seq-other", now=1200.0)
    ok(again["collection_sequence_id"] == seq, "overlapping request shares sequence")
    ok(again["t0"] == 1010.0, "t0 never reset")

    seen: List[str] = []

    def sender(ctx):
        seen.append(ctx["action_id"])
        return {"provider": "selfcheck", "message_id": ctx["action_id"]}

    r0 = machine.send_reminder("t1", contact, seq, sender, channel="facebook",
                               now=1020.0)
    ok(r0.sent and len(seen) == 1, "first slot sends on facebook")
    r1 = machine.send_reminder("t1", contact, seq, sender, channel="instagram",
                               now=1040.0)
    ok(r1.status == "wait", "quiet interval defers the next slot")
    r1b = machine.send_reminder("t1", contact, seq, sender, channel="instagram",
                                now=1081.0)
    ok(r1b.sent and len(seen) == 2, "shared budget continues across channels")
    r2 = machine.send_reminder("t1", contact, seq, sender, channel="sms",
                               now=1161.0)
    ok(r2.sent and len(seen) == 3, "third shared reminder sends on sms")
    r3 = machine.send_reminder("t1", contact, seq, sender, channel="sms",
                               now=1200.0)
    ok(not r3.sent and len(seen) == 3, "there is never a fourth reminder")

    final = machine.reserve_final("t1", contact, seq, channel="sms",
                                  content_sha256="sha-final", now=1300.0)
    snap = machine.snapshot("t1", contact, seq)
    ok(snap["state"] == STATE_CLOSING_FINAL, "closing_final entered")
    ok(snap["final_action_id"] == final.action_id, "reserved action recorded")
    again = machine.reserve_final("t1", contact, seq, channel="sms",
                                  content_sha256="sha-final", now=1301.0)
    ok(again.action_id == final.action_id and not again.created,
       "never reserves a second final")
    try:
        machine.dispatch_final("t1", contact, seq, "act_other", sender,
                               channel="sms", now=1302.0)
        raise AssertionError("a non-reserved action must be refused")
    except FinalNotReserved:
        passed += 1

    out = machine.dispatch_final("t1", contact, seq, final.action_id, sender,
                                 channel="sms", now=1303.0)
    ok(out.status == "admitted" and not out.sent,
       "a provider admission is not acceptance")
    ok(machine.snapshot("t1", contact, seq)["state"] == STATE_CLOSING_FINAL,
       "an admitted final stays closing_final")
    ok(store.receipts(final.action_id).get("ack") is None,
       "a bare admission carries no ack receipt")
    store.record_ack(final.action_id,
                     {"provider": "selfcheck", "message_id": "ack-1"},
                     now=1304.0)
    accepted = machine.dispatch_final("t1", contact, seq, final.action_id,
                                      sender, channel="sms", now=1305.0)
    ok(accepted.sent
       and machine.snapshot("t1", contact, seq)["state"] == STATE_STOPPED_FINAL,
       "acceptance closes stopped_final")

    contact2 = identity.bind("t1", [("sms_number", "+15550101", True)],
                             source="selfcheck")
    machine.open_sequence("t1", contact2, "seq-2", now=1400.0)
    machine.adopt_policy("t1", contact2, "seq-2", policy, now=1401.0)
    machine.record_initial_invitation("t1", contact2, "seq-2",
                                      invitation_id="inv-2", now=1402.0)
    machine.decline("t1", contact2, "seq-2", now=1403.0)
    snap2 = machine.snapshot("t1", contact2, "seq-2")
    ok(snap2["state"] == STATE_STOPPED_DECLINED,
       "a declined collection closes stopped_declined")
    ok(snap2["terminal"], "stopped_declined is terminal")

    print("reminder_state_machine self-check: %d assertions passed" % passed)
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selfcheck())



