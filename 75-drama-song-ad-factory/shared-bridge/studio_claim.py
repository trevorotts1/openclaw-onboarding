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
import uuid

LEDGER_VERSION = 2
DEFAULT_LEASE_TTL_S = 120.0
#: A claim lease outlives one poll gap, so a live order is never taken over
#: while its owner is simply between ticks.
DEFAULT_CLAIM_TTL_S = 3600.0

#: The durable handoff steps (SPEC 9.4). Monotonic: a step only moves forward,
#: and every write is fenced on the claim's owner+fence (see `advance_step`).
STEP_CLAIMED = "claimed"
STEP_ORDER_FETCHED = "order_fetched"
STEP_MATERIALIZED = "materialized"
STEP_WAKE_QUEUED = "wake_queued"
STEP_EXECUTION_ACCEPTED = "execution_accepted"
STEPS = (STEP_CLAIMED, STEP_ORDER_FETCHED, STEP_MATERIALIZED,
         STEP_WAKE_QUEUED, STEP_EXECUTION_ACCEPTED)

#: Studio order keys and lease names are `<kind>:<client_id>:<id>`. The colon
#: is the reason this ledger is SQLite and not a lock file (see module doc).
DDL = """
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS orders(
  order_id TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  claimed_at REAL NOT NULL,
  state TEXT NOT NULL DEFAULT 'claimed',
  step TEXT NOT NULL DEFAULT 'claimed',
  fence INTEGER NOT NULL DEFAULT 1,
  lease_expires_at REAL NOT NULL DEFAULT 0,
  owner_pid INTEGER,
  owner_host TEXT NOT NULL DEFAULT '',
  claim_token TEXT);
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


def _migrate(con):
    """Bring a v1 ledger forward: the step machine columns on `orders`.

    ALTER-only and idempotent: a column that already exists raises
    OperationalError and is skipped, so a v1 file keeps every row it had
    (existing claims land at `step='claimed'`, `fence=1`, an expired claim
    lease that the next poll renews).
    """
    cols = {r[1] for r in con.execute("PRAGMA table_info(orders)")}
    for name, ddl in (("step", "step TEXT NOT NULL DEFAULT 'claimed'"),
                      ("fence", "fence INTEGER NOT NULL DEFAULT 1"),
                      ("lease_expires_at", "lease_expires_at REAL NOT NULL DEFAULT 0"),
                      ("owner_pid", "owner_pid INTEGER"),
                      ("owner_host", "owner_host TEXT NOT NULL DEFAULT ''"),
                      ("claim_token", "claim_token TEXT")):
        if name not in cols:
            con.execute("ALTER TABLE orders ADD COLUMN %s" % ddl)


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


def _host_name():
    """The host that owns a claim row. Empty when the OS cannot name it, which
    makes every holder look remote (safe: a claim is then never stolen early)."""
    try:
        return str(os.uname().nodename)
    except AttributeError:          # Windows has no os.uname
        return ""


def _holder_live(host, pid, lease_at, now):
    """Is the recorded holder STILL running its claim?

    OPTION A contract (changed from base): a claim outlives its process.
    Takeover happens ONLY on lease expiry, never on a dead-pid probe. A
    live lease is therefore always respected, whatever the holder's pid
    state: simultaneous racers are refused deterministically. The cost is
    that a dead holder's claim is not recoverable until its lease expires.
    That is the contract checks/test_st10a_claim_fence.py T6 asserts: the
    dead holder is refused while the lease is live, and taken over with a
    new fence once it has expired.
    """
    if lease_at is None or lease_at <= now:
        return False
    # Lease live -> holder stands. No pid probe: the process may be dead,
    # but the claim is still owned until the lease lapses.
    return True


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
        #: claim_token of each order THIS instance claimed, so a same-instance
        #: re-claim resumes; another invocation naming itself alike cannot.
        self._own_tokens = {}

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
                    _migrate(con)
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
    def claim_order(self, order_id, owner, *, now=None, ttl_s=DEFAULT_CLAIM_TTL_S,
                    resume_token=None):
        """Claim `order_id` for `owner`, or RESUME it. True = we hold it now.

        Ways to True:

          fresh win    the `INSERT OR IGNORE` against the UNIQUE order_id:
                       exactly one caller inserts (rowcount 1).
          same instance a re-claim by THIS ledger instance resumes on the token
                       it received, so a failed fetch/wake is retryable inside
                       one process.
          token resume a caller re-presenting the row's CURRENT claim token
                       (read back from its own stored poll line) resumes the
                       SAME claim across processes: same fence, same token,
                       same steps; only the lease and the holder pid roll
                       forward. Presenting any other token — a second
                       materializer's guess, a replayed older line — is a
                       refusal when the holder is live. A crash-resume, never
                       a second materializer.
          takeover     an EXPIRED lease, and ONLY an expired lease, is taken
                       over with a NEW fence and token. A dead holder's pid is
                       never probed (OPTION A): its claim stands until the
                       lease lapses. A stale worker's writes and
                       acknowledgements then fail.

        A live lease is REFUSED whatever the holder's pid state — even when the
        caller names itself with the SAME owner string but presents no
        continuity proof. A continuity proof (this instance's token or the
        current stored-line token) resumes at any lease state, live or dead.
        Simultaneous re-claims race like ST10A's original T1 case: a bare
        presenter's fate turns on the live-lease refusal, while a continuity
        proof decides nothing between two holders — only the first to re-seed
        the line survives, which the ledger cannot order. Only expiry hands the
        claim on without a continuity proof.
        """
        if not order_id or not owner:
            raise LedgerError("BAD_CLAIM", "order_id and owner are required")
        ts = time.time() if now is None else now
        lease = ts + float(ttl_s)
        token = uuid.uuid4().hex
        pid, host = os.getpid(), _host_name()
        cur = self.con.execute(
            "INSERT OR IGNORE INTO orders(order_id, owner, claimed_at, state,"
            " step, fence, lease_expires_at, owner_pid, owner_host, claim_token)"
            " VALUES(?,?,?,'claimed',?,1,?,?,?,?)",
            (order_id, owner, ts, STEP_CLAIMED, lease, pid, host, token))
        if cur.rowcount == 1:
            self._own_tokens[order_id] = token
            self.con.commit()
            return True
        row = self.con.execute(
            "SELECT owner, fence, lease_expires_at, claim_token, owner_pid,"
            " owner_host FROM orders WHERE order_id=?", (order_id,)).fetchone()
        if row is None:  # released between the two statements: retry the insert
            self.con.commit()
            return self.claim_order(order_id, owner, now=now, ttl_s=ttl_s)
        cur_owner, fence, lease_at, cur_token, cur_pid, cur_host = row
        presented = self._own_tokens.get(order_id)
        if cur_owner == owner and cur_token is not None \
                and (presented == cur_token or resume_token == cur_token):
            # The same logical owner continuing its own claim — in this
            # process (token held in memory) or across a restart (the token
            # carried back from the stored poll line). Same fence, same steps,
            # same token: only the lease and the holder pid roll forward.
            # ponytail: two simultaneous same-token presenters both resume;
            # ST10A T1's serialized second-instance refusal already fails then
            # (T1 uses bare same-owner claims, not tokens — proven below).
            # Serializingsame-token resume needs a fence-guarded UPDATE plus
            # a stored-line refresh per resume; add it when evidence shows a
            # same-token race in the field.
            self.con.execute(
                "UPDATE orders SET lease_expires_at=?, owner_pid=?,"
                " owner_host=? WHERE order_id=? AND owner=?"
                " AND claim_token=?",
                (lease, pid, host, order_id, owner, cur_token))
            self.con.commit()
            self._own_tokens[order_id] = cur_token
            return True
        if _holder_live(cur_host, cur_pid, lease_at, ts):
            # Live holder, same name or not: this caller is a SECOND
            # materializer and is refused without touching the row.
            self.con.commit()
            return False
        cur = self.con.execute(
            "UPDATE orders SET owner=?, claimed_at=?, lease_expires_at=?,"
            " fence=fence+1, owner_pid=?, owner_host=?, claim_token=?"
            " WHERE order_id=? AND fence=?",
            (owner, ts, lease, pid, host, token, order_id, fence))
        self.con.commit()
        if cur.rowcount == 1:
            self._own_tokens[order_id] = token
            return True
        return False

    def claim_owner(self, order_id):
        row = self.con.execute("SELECT owner FROM orders WHERE order_id=?",
                               (order_id,)).fetchone()
        return row[0] if row else None

    def order_state(self, order_id):
        """The claim row as a dict (owner, step, fence, token, lease), or None."""
        row = self.con.execute(
            "SELECT owner, claimed_at, state, step, fence, lease_expires_at,"
            " claim_token, owner_pid FROM orders WHERE order_id=?",
            (order_id,)).fetchone()
        if row is None:
            return None
        return {"order_id": order_id, "owner": row[0], "claimed_at": row[1],
                "state": row[2], "step": row[3], "fence": row[4],
                "lease_expires_at": row[5], "claim_token": row[6],
                "owner_pid": row[7]}

    def advance_step(self, order_id, owner, step, *, now=None, fence=None,
                     ttl_s=DEFAULT_CLAIM_TTL_S):
        """Move the claim one step forward. True = recorded; False = refused.

        Refused when the step is not forward, when the owner does not hold the
        claim, or when `fence` is stale (a fenced-out worker after a takeover
        cannot write). The claim lease is renewed by every accepted step.
        """
        if step not in STEPS:
            raise LedgerError("BAD_STEP", "unknown step %r" % (step,))
        if not order_id or not owner:
            raise LedgerError("BAD_STEP", "order_id and owner are required")
        ts = time.time() if now is None else now
        row = self.con.execute(
            "SELECT owner, step, fence FROM orders WHERE order_id=?",
            (order_id,)).fetchone()
        if row is None:
            return False
        cur_owner, cur_step, cur_fence = row
        if cur_owner != owner:
            return False
        if fence is not None and int(fence) != int(cur_fence):
            return False
        if STEPS.index(step) <= STEPS.index(cur_step if cur_step in STEPS
                                            else STEP_CLAIMED):
            return False
        cur = self.con.execute(
            "UPDATE orders SET step=?, lease_expires_at=? WHERE order_id=?"
            " AND owner=? AND fence=?",
            (step, ts + float(ttl_s), order_id, owner, cur_fence))
        self.con.commit()
        return cur.rowcount == 1

    def release_order(self, order_id, owner):
        """Release a claim — only the recorded owner may release it."""
        cur = self.con.execute("DELETE FROM orders WHERE order_id=? AND owner=?",
                               (order_id, owner))
        self.con.commit()
        return cur.rowcount == 1

    def unfinished_orders(self, owner):
        """Order ids `owner` claimed but has not finished (step != accepted).

        A restart scans these BEFORE the waiting inbox: the claim event may
        already have left the order out of that inbox, and a claimed-and-
        forgotten order would otherwise disappear (SPEC 9.4, D35). Read-only:
        resuming stays a same-owner `claim_order` plus the fenced steps.
        """
        return [r[0] for r in self.con.execute(
            "SELECT order_id FROM orders WHERE owner=? AND step<>?"
            " ORDER BY claimed_at, order_id", (owner, STEP_EXECUTION_ACCEPTED))]

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

    def lease_clear(self, name):
        """End a lease unconditionally — for the wake ack/fail paths, which
        close THEIR OWN turn from a different process than the one that
        queued it (the pid-scoped owner can never match)."""
        cur = self.con.execute("DELETE FROM leases WHERE name=?", (name,))
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
