#!/usr/bin/env python3
"""U5 — the studio bridge's claim / replay / lease ledger.

Copied from the skill-23 `launch_ledger.py` pattern (atomic claim, time limit,
backoff) into skill 75, with two deliberate Windows corrections:

  1. `os.kill(pid, 0)` is NOT a liveness check on Windows — `os.kill` there
     calls `TerminateProcess` and KILLS the process. `pid_is_alive()` below
     never sends a signal on Windows (plan 3.12 / risk table: "Windows
     `os.kill(pid, 0)` kills instead of checking — fixed in U5").
  2. launch_ledger claims with an `O_CREAT|O_EXCL` LOCK FILE named from the
     record key. A studio key is `order:<client_id>:<order_id>`; a colon is an
     illegal filename character on Windows, so that mechanism cannot carry the
     studio keys. The claim, the replay guard and the lease are all single
     SQLite statements instead — same atomicity, no lock-file name, no colon,
     no fcntl. The write itself is the arbitration; no pre-check decides.

One authoritative SQLite store per bridge. Three guarantees:

  atomic claim   two runs can never both claim the same order. The claim is one
                 `INSERT OR IGNORE` against a UNIQUE primary key: exactly one
                 caller inserts (rowcount 1) and every other caller is refused.
  replay         every delivered message carries a message id. `UNIQUE(run_id,
                 message_id)` makes a second delivery of the same message a
                 refusal, never a duplicate send.
  lease          a time-limited ownership record owned in SQLite. Acquire is a
                 single UPSERT ... WHERE: it takes the lease when it is free or
                 expired or already ours, and is refused (rowcount 0) when a
                 live holder exists.

Stdlib only: sqlite3, os, time, ctypes, hashlib, json.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time

LEDGER_VERSION = 1
DEFAULT_LEASE_TTL_S = 120.0

#: Studio order keys and lease names are `<kind>:<client_id>:<id>`. The colon
#: is the reason this ledger is SQLite and not a lock file (see module doc).
DDL = """
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS orders(
  order_id TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  claimed_at REAL NOT NULL,
  state TEXT NOT NULL DEFAULT 'claimed');
CREATE TABLE IF NOT EXISTS messages(
  run_id TEXT NOT NULL,
  message_id TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT '',
  at REAL NOT NULL,
  PRIMARY KEY (run_id, message_id));
CREATE TABLE IF NOT EXISTS leases(
  name TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  acquired_at REAL NOT NULL,
  expires_at REAL NOT NULL,
  host TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS records(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  payload TEXT NOT NULL,
  at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS notices(
  order_id TEXT PRIMARY KEY,
  nudged_at REAL NOT NULL,
  reminded_at REAL);
"""


class LedgerError(Exception):
    """Refusals and hard errors carry a stable code; never a silent blank."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


# --- Windows-safe liveness ---------------------------------------------------

def _win_pid_alive(pid):  # pragma: no cover - exercised only on Windows
    """OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION) handle == alive.

    Query-only rights: the handle can never terminate the process. Fail
    closed — any failure to probe reports "not alive" rather than risk a kill.
    """
    import ctypes
    from ctypes import wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return False
    try:
        kernel32.CloseHandle(wintypes.HANDLE(handle))
        return True
    except Exception:  # noqa: BLE001 - never raise out of a liveness probe
        return False


def pid_is_alive(pid, *, os_name=None, kill=None, win_probe=None):
    """True when `pid` is a live process — WITHOUT signalling it on Windows.

    `os_name`/`kill`/`win_probe` are injectable so the Windows branch is
    provable on any host: a check can assert `os.kill` is never reached when
    os_name == "nt".
    """
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False
    name = os.name if os_name is None else os_name
    if name == "nt":
        probe = win_probe or _win_pid_alive
        try:
            return bool(probe(pid))
        except Exception:  # noqa: BLE001
            return False
    posix_kill = kill or os.kill
    try:
        posix_kill(pid, 0)  # POSIX only: signal 0 is never delivered
        return True
    except OSError:
        return False


# --- the ledger --------------------------------------------------------------

class ClaimLedger:
    """Atomic claim + replay guard + Windows-safe lease over one SQLite file."""

    def __init__(self, db_path):
        if isinstance(db_path, bool) or not isinstance(db_path, (str, bytes, os.PathLike)):
            raise LedgerError("BAD_PATH", "db path must be a filesystem path")
        self.path = os.fspath(db_path)
        parent = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(parent, exist_ok=True)
        self.con = self._connect(self.path)

    @staticmethod
    def _connect(path):
        """Open and initialise, retrying through a first-open WAL race.

        Two bridge processes starting at once both try to switch a brand-new
        file to WAL; the switch needs a brief exclusive lock and the loser
        would see `database is locked` before any claim is even attempted.
        busy_timeout covers steady-state contention; this bounded retry covers
        the initialisation itself, so the RACE decides the claim, never a
        spurious OperationalError.
        """
        last = None
        for _ in range(100):
            con = None
            try:
                con = sqlite3.connect(path, timeout=30)
                con.execute("PRAGMA busy_timeout=30000")
                con.execute("PRAGMA journal_mode=WAL")
                with con:
                    con.executescript(DDL)
                    con.execute("INSERT OR IGNORE INTO meta(k, v) VALUES('version', ?)",
                                (str(LEDGER_VERSION),))
                return con
            except sqlite3.OperationalError as e:
                last = e
                if con is not None:
                    try:
                        con.close()
                    except sqlite3.Error:
                        pass
                time.sleep(0.05)
        raise LedgerError("DB_BUSY", "could not initialise ledger: %s" % last)

    def close(self):
        self.con.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- claim ------------------------------------------------------------
    def claim_order(self, order_id, owner, *, now=None):
        """Claim `order_id` for `owner`. Returns True to the ONE winner only.

        The `INSERT OR IGNORE` against the UNIQUE order_id is the whole
        arbitration: the database decides, so two runs racing the same order
        cannot both return True. Every other caller (including a re-claim by a
        holder that already won) is refused.
        """
        if not order_id or not owner:
            raise LedgerError("BAD_CLAIM", "order_id and owner are required")
        ts = time.time() if now is None else now
        cur = self.con.execute(
            "INSERT OR IGNORE INTO orders(order_id, owner, claimed_at)"
            " VALUES(?,?,?)", (order_id, owner, ts))
        self.con.commit()
        return cur.rowcount == 1

    def claim_owner(self, order_id):
        row = self.con.execute("SELECT owner FROM orders WHERE order_id=?",
                               (order_id,)).fetchone()
        return row[0] if row else None

    def release_order(self, order_id, owner):
        """Release a claim — only the recorded owner may release it."""
        cur = self.con.execute("DELETE FROM orders WHERE order_id=? AND owner=?",
                               (order_id, owner))
        self.con.commit()
        return cur.rowcount == 1

    # -- replay -----------------------------------------------------------
    def record_message(self, run_id, message_id, *, kind="", now=None):
        """True when this message is NEW; False when it is a replay.

        A caller that gets False must not send — the message id was already
        delivered for this run.
        """
        if not run_id or not message_id:
            raise LedgerError("BAD_MESSAGE", "run_id and message_id are required")
        ts = time.time() if now is None else now
        cur = self.con.execute(
            "INSERT OR IGNORE INTO messages(run_id, message_id, kind, at)"
            " VALUES(?,?,?,?)", (run_id, message_id, kind, ts))
        self.con.commit()
        return cur.rowcount == 1

    # -- lease ------------------------------------------------------------
    def lease_acquire(self, name, owner, ttl_s=DEFAULT_LEASE_TTL_S, *,
                      now=None, host=""):
        """Take the lease. True = held by us, False = a live holder refuses us.

        One atomic UPSERT with a WHERE: it takes a free, expired, or
        already-ours lease and is a no-op (rowcount 0) for a live holder.
        """
        if not name or not owner:
            raise LedgerError("BAD_LEASE", "name and owner are required")
        ts = time.time() if now is None else now
        cur = self.con.execute(
            "INSERT INTO leases(name, owner, acquired_at, expires_at, host)"
            " VALUES(?,?,?,?,?)"
            " ON CONFLICT(name) DO UPDATE SET"
            "   owner=excluded.owner, acquired_at=excluded.acquired_at,"
            "   expires_at=excluded.expires_at, host=excluded.host"
            " WHERE leases.expires_at <= ? OR leases.owner = ?",
            (name, owner, ts, ts + float(ttl_s), host, ts, owner))
        self.con.commit()
        return cur.rowcount == 1

    def lease_holder(self, name, *, now=None):
        """The live holder of `name`, or None when free/expired."""
        ts = time.time() if now is None else now
        row = self.con.execute("SELECT owner, expires_at FROM leases WHERE name=?",
                               (name,)).fetchone()
        if not row or row[1] <= ts:
            return None
        return row[0]

    def lease_release(self, name, owner):
        cur = self.con.execute("DELETE FROM leases WHERE name=? AND owner=?",
                               (name, owner))
        self.con.commit()
        return cur.rowcount == 1

    # -- receipts ---------------------------------------------------------
    def write_receipt(self, run_id, kind, payload, *, now=None):
        """Append an owned-run receipt row and return its id."""
        ts = time.time() if now is None else now
        cur = self.con.execute(
            "INSERT INTO records(run_id, kind, payload, at) VALUES(?,?,?,?)",
            (run_id, kind, json.dumps(payload, sort_keys=True), ts))
        self.con.commit()
        return cur.lastrowid

    def receipts(self, run_id):
        return [
            {"kind": r[0], "payload": json.loads(r[1]), "at": r[2]}
            for r in self.con.execute(
                "SELECT kind, payload, at FROM records WHERE run_id=? ORDER BY id",
                (run_id,))
        ]


    # -- notices (the quiet board) ---------------------------------------
    def notice_gate(self, order_id, *, now=None, reminder_after_s=86400.0):
        """ONE approval nudge, then at most one reminder, then silence.

        Returns "nudge" | "reminder" | None. `None` means this order gets no
        notice this time — the caller must stay silent, not re-word it.
        After the reminder, every later call returns `None` forever: the
        studio page's own chip is the only remaining signal. The `INSERT OR
        IGNORE` makes a concurrent double-nudge impossible.
        """
        if not order_id:
            raise LedgerError("BAD_NOTICE", "order_id is required")
        ts = time.time() if now is None else now
        cur = self.con.execute(
            "INSERT OR IGNORE INTO notices(order_id, nudged_at, reminded_at)"
            " VALUES(?,?,NULL)", (order_id, ts))
        self.con.commit()
        if cur.rowcount == 1:
            return "nudge"
        row = self.con.execute(
            "SELECT nudged_at, reminded_at FROM notices WHERE order_id=?",
            (order_id,)).fetchone()
        if row is None or row[1] is not None:
            return None
        if ts - row[0] >= float(reminder_after_s):
            upd = self.con.execute(
                "UPDATE notices SET reminded_at=? WHERE order_id=? AND reminded_at IS NULL",
                (ts, order_id))
            self.con.commit()
            return "reminder" if upd.rowcount == 1 else None
        return None


def fingerprint(value):
    """A stable short digest — used for a message id, never for a secret."""
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:16]


def message_id(order_id, stage, seq):
    return "%s:%s:%s" % (order_id, stage, seq)
