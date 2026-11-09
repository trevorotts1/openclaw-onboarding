#!/usr/bin/env python3
"""suppression_ledger.py - the durable suppression fence and the gated re-entry.

Contract basis: Purple-Billboard DATA-CONTRACTS section 7 (scoped refusal,
opt-out, human precedence) read together with section 3 (fresh gate before every
dispatch). Python 3 standard library only.

WHY THIS MODULE EXISTS, AND WHY IT SITS IN THE OUTBOX DATABASE.

consent_gate.py owns the DECISION: which scope is refused, and whether a send
for this channel/topic/offer/campaign/sequence is allowed. This module owns the
FENCE that makes that decision hold at the instant a send begins.

The defect it closes is a torn read, not a missing check. dispatch() evaluates
consent, gets ALLOW, and only then commits the attempt that permits a send. A
suppression committed inside that window is a suppression the send never sees,
so the message goes out AFTER the person said stop. Re-reading consent just
before the commit narrows the window but cannot close it, because the consent
tables can live in a different SQLite file from the outbox and two files have no
common serialisation point.

So the fence lives in the SAME SQLite file as outbox_actions, and carries a
monotonic epoch per contact. durable_store.begin_attempt_guarded() adds the
epoch to the INSERT that starts an attempt: the row is created only if the epoch
is still the one read before the decision was evaluated. One IMMEDIATE
transaction, one file, so the suppression writer and the dispatcher are ordered
by SQLite itself. If suppression landed first, the insert matches zero rows and
nothing is sent. If the attempt landed first, the send began before the
suppression was durable, which is the truthful order and is recorded as such.

SUPPRESSION IS DURABLE.  Both tables are ordinary rows in a WAL database with
synchronous=FULL. A suppressed contact is still suppressed after the process,
the interpreter and the machine restart, because contactability is read from
disk at the moment of the send and never cached in memory.

RE-ENTRY IS EXPLICIT AND GATED.  There is no timeout anywhere in this module:
nothing expires, nothing silently becomes contactable again. reenter() requires
a non-empty actor (who), authority (by what right) and reason (why), and writes
an append-only event. Missing any of the three is refused before any write.
A suppression without a matching reentry event is permanent.

Import:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from suppression_ledger import SuppressionLedger

Assert-based self-check:  python3 -I suppression_ledger.py
"""

from __future__ import annotations

import os
import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple

ACTION_SUPPRESS = "suppress"
ACTION_REENTER = "reenter"

# The three fields that make a re-entry an act of authority rather than an
# accident. All three are required and all three are stored.
REENTRY_REQUIRED = ("actor", "authority", "reason")

SCHEMA = """
CREATE TABLE IF NOT EXISTS suppression_epochs (
    tenant_id            TEXT NOT NULL,
    canonical_contact_id TEXT NOT NULL,
    epoch                INTEGER NOT NULL DEFAULT 0,
    last_reason          TEXT NOT NULL DEFAULT '',
    updated_at           REAL NOT NULL,
    PRIMARY KEY (tenant_id, canonical_contact_id)
);

CREATE TABLE IF NOT EXISTS suppression_events (
    tenant_id            TEXT NOT NULL,
    canonical_contact_id TEXT NOT NULL,
    seq                  INTEGER NOT NULL,
    action               TEXT NOT NULL,
    epoch                INTEGER NOT NULL,
    actor                TEXT NOT NULL DEFAULT '',
    authority            TEXT NOT NULL DEFAULT '',
    reason               TEXT NOT NULL DEFAULT '',
    at                   REAL NOT NULL,
    PRIMARY KEY (tenant_id, canonical_contact_id, seq)
);
"""


class SuppressionError(ValueError):
    """Bad input or an unauthorised re-entry. Always fail closed."""


def _id(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SuppressionError(f"bad_input: {name} must be a non-empty string")
    return value.strip()


def _ts(now: Optional[float]) -> float:
    return time.time() if now is None else float(now)


class SuppressionLedger:
    """The suppression epoch and the append-only re-entry ledger for one file."""

    def __init__(self, db_path: str) -> None:
        if not isinstance(db_path, str) or not db_path.strip():
            raise SuppressionError("bad_input: db_path must be a non-empty string")
        self.db_path = str(db_path)
        self._db = sqlite3.connect(self.db_path, timeout=30.0,
                                   isolation_level=None)  # explicit BEGIN only
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA busy_timeout=30000")
        self._retry(lambda: self._db.execute(
            "PRAGMA journal_mode=WAL").fetchone(), what="journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._retry(lambda: self._db.executescript(SCHEMA), what="schema")

    def _retry(self, fn, *, what: str, deadline_s: float = 30.0):
        deadline = time.time() + deadline_s
        while True:
            try:
                return fn()
            except sqlite3.OperationalError as exc:
                if "locked" not in str(exc) and "busy" not in str(exc):
                    raise
                if time.time() > deadline:
                    raise SuppressionError(
                        f"db_busy: {what} after {deadline_s}s") from exc
                time.sleep(0.01)

    def close(self) -> None:
        self._db.close()

    # ── the epoch ──────────────────────────────────────────────────────────

    def epoch(self, tenant_id: str, canonical_contact_id: str) -> int:
        """Current fence value. 0 means no suppression fence was ever raised."""
        tenant_id = _id(tenant_id, "tenant_id")
        canonical_contact_id = _id(canonical_contact_id, "canonical_contact_id")
        row = self._db.execute(
            "SELECT epoch FROM suppression_epochs"
            " WHERE tenant_id=? AND canonical_contact_id=?",
            (tenant_id, canonical_contact_id),
        ).fetchone()
        return int(row["epoch"]) if row is not None else 0

    def expect(self, tenant_id: str, canonical_contact_id: str
               ) -> Tuple[str, str, int]:
        """The compare-and-swap token to hand to begin_attempt_guarded().

        Read this BEFORE the gate decides. If a suppression lands after that
        read, the commit that would start the send no longer matches.
        """
        tenant_id = _id(tenant_id, "tenant_id")
        canonical_contact_id = _id(canonical_contact_id, "canonical_contact_id")
        return (tenant_id, canonical_contact_id,
                self.epoch(tenant_id, canonical_contact_id))

    # ── suppression ────────────────────────────────────────────────────────

    def suppress(self, tenant_id: str, canonical_contact_id: str, *,
                 reason: str = "", actor: str = "",
                 now: Optional[float] = None) -> Dict[str, Any]:
        """Bump the fence. Idempotent in effect, never silent in the log."""
        tenant_id = _id(tenant_id, "tenant_id")
        canonical_contact_id = _id(canonical_contact_id, "canonical_contact_id")
        reason = reason or "suppressed"
        if not isinstance(reason, str):
            raise SuppressionError("bad_input: reason must be a string")
        ts = _ts(now)
        with self._tx() as cur:
            epoch = self._bump(cur, tenant_id, canonical_contact_id, reason, ts)
            return self._event(cur, tenant_id, canonical_contact_id,
                               ACTION_SUPPRESS, epoch, actor or "", "", reason, ts)

    # ── re-entry: explicit, gated, no timeout ──────────────────────────────

    def reenter(self, tenant_id: str, canonical_contact_id: str, *,
                actor: str, authority: str, reason: str,
                now: Optional[float] = None) -> Dict[str, Any]:
        """Lift a suppression. Requires who, by what right, and why.

        There is deliberately no expires_at and no "quiet period". A suppression
        is contactable again only through this call, and this call leaves an
        append-only event naming the human and the authority behind it.
        """
        missing = [name for name, value in
                   (("actor", actor), ("authority", authority), ("reason", reason))
                   if not isinstance(value, str) or not value.strip()]
        if missing:
            raise SuppressionError(
                "reentry_requires_authority: missing " + ", ".join(missing))
        tenant_id = _id(tenant_id, "tenant_id")
        canonical_contact_id = _id(canonical_contact_id, "canonical_contact_id")
        ts = _ts(now)
        with self._tx() as cur:
            epoch = self._bump(cur, tenant_id, canonical_contact_id,
                               "reentry:" + reason.strip(), ts)
            return self._event(cur, tenant_id, canonical_contact_id,
                               ACTION_REENTER, epoch, actor, authority,
                               reason, ts)

    # ── audit ──────────────────────────────────────────────────────────────

    def events(self, tenant_id: str,
               canonical_contact_id: str) -> List[Dict[str, Any]]:
        tenant_id = _id(tenant_id, "tenant_id")
        canonical_contact_id = _id(canonical_contact_id, "canonical_contact_id")
        return [dict(r) for r in self._db.execute(
            "SELECT * FROM suppression_events WHERE tenant_id=?"
            " AND canonical_contact_id=? ORDER BY seq",
            (tenant_id, canonical_contact_id)).fetchall()]

    def last_suppression_at(self, tenant_id: str,
                            canonical_contact_id: str) -> Optional[float]:
        """When the newest suppression became durable, or None if never."""
        for event in reversed(self.events(tenant_id, canonical_contact_id)):
            if event["action"] == ACTION_SUPPRESS:
                return float(event["at"])
        return None

    # ── internals ──────────────────────────────────────────────────────────

    class _TxCtx:
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

    def _tx(self) -> "SuppressionLedger._TxCtx":
        return SuppressionLedger._TxCtx(self._db)

    @staticmethod
    def _bump(cur: sqlite3.Cursor, tenant_id: str, canonical_contact_id: str,
              reason: str, ts: float) -> int:
        cur.execute(
            "INSERT INTO suppression_epochs (tenant_id, canonical_contact_id,"
            " epoch, last_reason, updated_at) VALUES (?,?,1,?,?)"
            " ON CONFLICT(tenant_id, canonical_contact_id) DO UPDATE SET"
            " epoch=suppression_epochs.epoch+1,"
            " last_reason=excluded.last_reason,"
            " updated_at=excluded.updated_at",
            (tenant_id, canonical_contact_id, reason, ts),
        )
        return int(cur.execute(
            "SELECT epoch FROM suppression_epochs"
            " WHERE tenant_id=? AND canonical_contact_id=?",
            (tenant_id, canonical_contact_id)).fetchone()["epoch"])

    @staticmethod
    def _event(cur: sqlite3.Cursor, tenant_id: str, canonical_contact_id: str,
               action: str, epoch: int, actor: str, authority: str,
               reason: str, ts: float) -> Dict[str, Any]:
        seq = cur.execute(
            "SELECT COALESCE(MAX(seq), 0) + 1 AS n FROM suppression_events"
            " WHERE tenant_id=? AND canonical_contact_id=?",
            (tenant_id, canonical_contact_id)).fetchone()["n"]
        cur.execute(
            "INSERT INTO suppression_events (tenant_id, canonical_contact_id,"
            " seq, action, epoch, actor, authority, reason, at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (tenant_id, canonical_contact_id, int(seq), action, int(epoch),
             actor or "", authority or "", reason or "", ts),
        )
        return dict(cur.execute(
            "SELECT * FROM suppression_events WHERE tenant_id=?"
            " AND canonical_contact_id=? AND seq=?",
            (tenant_id, canonical_contact_id, int(seq))).fetchone())

    def same_file(self, other_path: str) -> bool:
        """True when other_path is this database (the fence needs one file)."""
        try:
            return os.path.realpath(str(other_path)) == os.path.realpath(self.db_path)
        except OSError:
            return False


# ── assert-based self-check (stdlib only) ──────────────────────────────────

def _selfcheck() -> int:
    import tempfile
    from pathlib import Path

    d = Path(tempfile.mkdtemp(prefix="suppression-selfcheck-"))
    path = str(d / "outbox.sqlite")
    ledger = SuppressionLedger(path)
    passed = 0

    def ok(cond: bool, label: str) -> None:
        nonlocal passed
        if not cond:
            raise AssertionError("FAIL: " + label)
        passed += 1

    t, c = "t1", "contact-1"
    ok(ledger.epoch(t, c) == 0, "no fence before any suppression")
    first = ledger.suppress(t, c, reason="customer said stop", actor="agent")
    ok(first["epoch"] == 1, "suppression raises the epoch")
    ok(ledger.epoch(t, c) == 1, "epoch is durable in this handle")

    # Re-entry without authority is refused, and writes nothing.
    for field, kwargs in (("actor", {"authority": "ops", "reason": "asked again"}),
                          ("authority", {"actor": "jill", "reason": "asked again"}),
                          ("reason", {"actor": "jill", "authority": "ops"})):
        broken = {"actor": "jill", "authority": "ops", "reason": "asked again"}
        broken.update({field: ""})
        try:
            ledger.reenter(t, c, **broken)
            raise AssertionError("FAIL: re-entry without %s was accepted" % field)
        except SuppressionError:
            passed += 1
    ok(ledger.epoch(t, c) == 1, "a refused re-entry does not move the fence")

    entry = ledger.reenter(t, c, actor="jill", authority="ops:supervisor",
                           reason="customer asked us to resume")
    ok(entry["epoch"] == 2 and entry["authority"] == "ops:supervisor",
       "an authorised re-entry is recorded with its authority")

    # Restart: a brand new handle (same file) still reports the fence.
    ledger.close()
    reopened = SuppressionLedger(path)
    ok(reopened.epoch(t, c) == 2, "the fence survives a reopen")
    ok([e["action"] for e in reopened.events(t, c)]
       == [ACTION_SUPPRESS, ACTION_REENTER], "the audit trail survives a reopen")
    ok(reopened.same_file(path), "same_file recognises its own database")
    ok(not reopened.same_file(str(d / "other.sqlite")),
       "same_file rejects a different database")
    reopened.close()

    print(f"OK {passed} PASS")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selfcheck())
