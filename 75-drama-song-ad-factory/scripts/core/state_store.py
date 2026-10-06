"""Per-run transactional stage store. Directive sections 22, 24.4. Stdlib only.

Owns stage states, expected-version compare-and-set, worker leases, events.
Uses SQLite WAL; JSON checkpoints are projections, never authorities here.

Every mutation validates against a fresh read, then writes with a single
UPDATE predicated on the row version (rowcount 0 = lost race). The write
itself is the atomic compare-and-set; pre-checks only pick error codes.

Never imports artifact_graph. Only state this module ever sets on an
upstream change is STALE (via mark_stale).
"""
from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path

SCHEMA_VERSION = "1.0.0"
DB_SCHEMA_VERSION = 1

STATES = frozenset({
    "NOT_STARTED", "READY", "RUNNING", "WAITING_PROVIDER",
    "WAITING_APPROVAL", "QC", "FAILED_RETRYABLE", "FAILED_BLOCKED",
    "PARKED", "COMPLETE", "STALE",
})

# ponytail: fixed table, no per-campaign override; add when directive names one.
TRANSITIONS = {
    "NOT_STARTED": {"READY"},
    "READY": {"RUNNING", "PARKED"},
    "RUNNING": {"WAITING_PROVIDER", "WAITING_APPROVAL", "QC",
                "FAILED_RETRYABLE", "FAILED_BLOCKED", "PARKED", "COMPLETE"},
    "WAITING_PROVIDER": {"RUNNING", "FAILED_RETRYABLE", "FAILED_BLOCKED", "PARKED"},
    "WAITING_APPROVAL": {"RUNNING", "QC", "FAILED_BLOCKED", "PARKED"},
    "QC": {"COMPLETE", "FAILED_RETRYABLE", "FAILED_BLOCKED", "RUNNING"},
    "FAILED_RETRYABLE": {"READY", "RUNNING", "PARKED"},
    "FAILED_BLOCKED": {"READY", "PARKED"},
    "PARKED": {"READY"},
    "COMPLETE": set(),  # out only via mark_stale
    "STALE": {"READY", "RUNNING"},
}

CLAIMABLE = ("READY", "STALE", "FAILED_RETRYABLE", "RUNNING")
TERMINAL_OWNER_CLEAR = {"READY", "COMPLETE", "FAILED_RETRYABLE",
                        "FAILED_BLOCKED", "PARKED", "STALE"}
REASON_REQUIRED = {"FAILED_BLOCKED", "PARKED"}


class StoreError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def needs_recovery(db_path):
    """(bool, str): True when the DB must be reconciled before use."""
    p = Path(db_path)
    if not p.exists():
        return False, "fresh"
    try:
        con = sqlite3.connect("file:%s?mode=ro" % p, uri=True, timeout=5)
        try:
            row = con.execute("PRAGMA integrity_check").fetchone()
            if not row or row[0] != "ok":
                return True, "corrupt: integrity_check failed"
            tables = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if not {"meta", "stages", "events"} <= tables:
                return True, "corrupt: missing tables"
            flag = con.execute(
                "SELECT v FROM meta WHERE k='db_version'").fetchone()
            if flag is None or flag[0] != str(DB_SCHEMA_VERSION):
                return True, "incompatible: schema drift, migrate first"
            return False, "clean"
        finally:
            con.close()
    except sqlite3.DatabaseError as e:
        return True, "corrupt: %s" % e


class Store:
    def __init__(self, db_path):
        bad, why = needs_recovery(db_path)
        if bad:
            raise StoreError("NEEDS_RECOVERY", why)
        self.path = Path(db_path)
        self.con = sqlite3.connect(self.path, timeout=30)
        self.con.execute("PRAGMA journal_mode=WAL")
        with self.con:
            self.con.executescript(
                "CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);"
                "CREATE TABLE IF NOT EXISTS stages(run_id TEXT, stage TEXT,"
                " state TEXT, version INTEGER, owner TEXT, lease_expires REAL,"
                " reason TEXT, updated_at REAL,"
                " PRIMARY KEY(run_id, stage));"
                "CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY,"
                " run_id TEXT, stage TEXT, kind TEXT, detail TEXT, at REAL);"
                "INSERT OR IGNORE INTO meta(k, v)"
                " VALUES('db_version', '%d');" % DB_SCHEMA_VERSION)
        mode = self.con.execute("PRAGMA journal_mode").fetchone()[0]
        # memory: :memory: DBs report mode=memory and cannot do WAL;
        # nothing to crash-recover there, so accept it.
        if mode.lower() not in ("wal", "memory"):
            raise StoreError("NEEDS_RECOVERY",
                             "WAL unavailable (mode=%s)" % mode)

    def close(self):
        self.con.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- internals --
    def _row(self, run_id, stage):
        r = self.con.execute(
            "SELECT state, version, owner, lease_expires, reason"
            " FROM stages WHERE run_id=? AND stage=?",
            (run_id, stage)).fetchone()
        if r is None:
            raise StoreError("NOT_FOUND", "%s/%s" % (run_id, stage))
        return {"run_id": run_id, "stage": stage, "state": r[0],
                "version": r[1], "owner": r[2], "lease_expires": r[3],
                "reason": r[4]}

    def _event(self, run_id, stage, kind, detail=""):
        self.con.execute(
            "INSERT INTO events(id, run_id, stage, kind, detail, at)"
            " VALUES(?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, run_id, stage, kind, detail, time.time()))

    @staticmethod
    def _lease_live(row, now=None):
        now = time.time() if now is None else now
        return bool(row["owner"]) and row["lease_expires"] \
            and row["lease_expires"] > now

    def _cas(self, run_id, stage, version, set_clause, params):
        """Version-predicated write. Returns fresh row or raises."""
        cur = self.con.execute(
            "UPDATE stages SET %s WHERE run_id=? AND stage=? AND version=?"
            % set_clause, params + (run_id, stage, version))
        if cur.rowcount == 0:
            raise StoreError("VERSION_MISMATCH",
                             "lost race on %s/%s" % (run_id, stage))
        return self._row(run_id, stage)

    # -- API --
    def init_run(self, run_id, stages):
        with self.con:
            for s in stages:
                self.con.execute(
                    "INSERT OR IGNORE INTO stages(run_id, stage, state,"
                    " version, owner, lease_expires, reason, updated_at)"
                    " VALUES(?, ?, 'NOT_STARTED', 1, NULL, NULL, NULL, ?)",
                    (run_id, s, time.time()))
            self._event(run_id, "", "init", ",".join(stages))

    def get(self, run_id, stage):
        return self._row(run_id, stage)

    def claim(self, run_id, stage, owner, lease_s=300, expected_version=None):
        """Claim a stage. Re-claim on an expired lease takes over."""
        now = time.time()
        with self.con:
            row = self._row(run_id, stage)
            if expected_version is not None \
                    and expected_version != row["version"]:
                raise StoreError("VERSION_MISMATCH",
                                 "expected %s have %s"
                                 % (expected_version, row["version"]))
            if row["state"] not in CLAIMABLE:
                raise StoreError("ILLEGAL_TRANSITION",
                                 "claim from %s" % row["state"])
            if self._lease_live(row, now) and row["owner"] != owner:
                raise StoreError("NOT_OWNER",
                                 "lease held by %s" % row["owner"])
            fresh = self._cas(
                run_id, stage, row["version"],
                "state='RUNNING', version=version+1, owner=?,"
                " lease_expires=?, reason=NULL, updated_at=?",
                (owner, now + lease_s, now))
            self._event(run_id, stage, "claim", owner)
        return fresh

    def heartbeat(self, run_id, stage, owner, lease_s=300):
        now = time.time()
        with self.con:
            row = self._row(run_id, stage)
            if row["owner"] != owner:
                raise StoreError("NOT_OWNER",
                                 "lease held by %s" % row["owner"])
            if row["lease_expires"] and row["lease_expires"] <= now:
                raise StoreError("STALE_LEASE", "lease expired; re-claim")
            self.con.execute(
                "UPDATE stages SET lease_expires=? WHERE run_id=? AND stage=?",
                (now + lease_s, run_id, stage))
        return self._row(run_id, stage)

    def transition(self, run_id, stage, to_state, actor,
                   expected_version=None, reason=None):
        """Guarded transition: legal edge + lease held + version CAS."""
        if to_state not in STATES:
            raise StoreError("ILLEGAL_TRANSITION", "unknown %s" % to_state)
        if to_state == "STALE":
            raise StoreError("ILLEGAL_TRANSITION", "use mark_stale")
        if to_state in REASON_REQUIRED and not reason:
            raise StoreError("MISSING_REASON", "%s needs reason" % to_state)
        now = time.time()
        with self.con:
            row = self._row(run_id, stage)
            if expected_version is not None \
                    and expected_version != row["version"]:
                raise StoreError("VERSION_MISMATCH",
                                 "expected %s have %s"
                                 % (expected_version, row["version"]))
            if to_state not in TRANSITIONS[row["state"]]:
                raise StoreError("ILLEGAL_TRANSITION",
                                 "%s -> %s" % (row["state"], to_state))
            if self._lease_live(row, now) and row["owner"] != actor:
                raise StoreError("NOT_OWNER",
                                 "lease held by %s" % row["owner"])
            if row["owner"] == actor and row["lease_expires"] \
                    and row["lease_expires"] <= now:
                raise StoreError("STALE_LEASE", "lease expired; re-claim")
            owner, lease = row["owner"], row["lease_expires"]
            if to_state in TERMINAL_OWNER_CLEAR:
                owner, lease = None, None
            fresh = self._cas(
                run_id, stage, row["version"],
                "state=?, version=version+1, owner=?, lease_expires=?,"
                " reason=?, updated_at=?",
                (to_state, owner, lease, reason, now))
            self._event(run_id, stage, "transition",
                        "%s->%s %s" % (row["state"], to_state, reason or ""))
        return fresh

    def mark_stale(self, run_id, stage, reason):
        """Only STALE this module ever sets on upstream change."""
        if not reason:
            raise StoreError("MISSING_REASON", "stale needs reason")
        with self.con:
            row = self._row(run_id, stage)
            if row["state"] == "STALE":
                return row
            fresh = self._cas(
                run_id, stage, row["version"],
                "state='STALE', version=version+1, owner=NULL,"
                " lease_expires=NULL, reason=?, updated_at=?",
                (reason, time.time()))
            self._event(run_id, stage, "stale", reason)
        return fresh

    def events(self, run_id):
        return self.con.execute(
            "SELECT stage, kind, detail, at FROM events WHERE run_id=?"
            " ORDER BY at", (run_id,)).fetchall()
