"""governor_store.py -- the SHARED, DURABLE admission state for one host.

[PRES-004] The defect this module removes: presentation_job.governor keeps
tokens, in-flight counts, day counters and rate-scale penalty in PROCESS-LOCAL
dicts (governor._state) guarded by a process-local RLock. Every presentation
run auto-spawns its own dispatcher process (autospawn.py), so two jobs each
consumed the FULL account/provider cap at the same time -- 2x the operator's
OpenRouter 100, 2x Ollama's 3 -- and a restart silently reset the daily
budget. The QC contract says it plainly: "SQLite WAL with a single
lock/transaction authority on one host" and "Counters persist restart."

WHAT LIVES HERE:
  - ONE SQLite database (WAL mode) at the department config dir, shared by
    every governor process on the same host. A single writer transaction per
    admission decision makes the store the ONE lock authority on this host;
    SQLite's own file lock serialises the rest.
  - Per (account_binding, provider) state rows: tokens, window events,
    inflight, day_count, rate_scale, rate_scale_until, fencing seq.
  - Opaque ACCOUNT BINDING ids [PRES-004]: the row key is an opaque string
    like ``co-<hex8>-cred-<hex8>`` derived from company_id + a salted hash of
    the credential. NEVER the raw token, never the model spelling -- hashing
    (not storing) the credential means the DB never holds a secret and two
    keys on one account still cannot be told apart by value, which is the
    point: they share the account's bucket by binding, not by key text.
  - Circuit / penalty state [PRES-016]: report_429's halving and report_ok's
    doubling PERSIST across processes and restarts; cooldown is shared so a
    second job does not plough into the same 429 storm.

CONCURRENCY CONTRACT: one connection per thread, WAL journal mode,
``BEGIN IMMEDIATE`` transactions -- readers never block writers, and exactly
one writer commits at a time. Every store error DEGRADES to in-process
behaviour (the caller keeps its module-local dict); a broken store must never
fail an admission decision open or closed, and must never crash a run.

The row shape is an internal detail of governor.py's facade; only governor.py
imports this module.

100% stdlib (sqlite3, hashlib, os, time). Database never contains secrets:
the binding id is a hash, and no field ever carries a token or key.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

__all__ = [
    "GovernorStoreError",
    "account_binding_id",
    "GovernorStore",
    "shared_store",
    "store_path",
]

_SCHEMA_VERSION = 1

_DDL = """
CREATE TABLE IF NOT EXISTS governor_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS governor_state (
    binding TEXT NOT NULL,            -- opaque account binding id (hashed)
    provider TEXT NOT NULL,           -- canonical provider id
    tokens REAL NOT NULL DEFAULT 0.0,
    last_refill REAL NOT NULL DEFAULT 0.0,
    inflight INTEGER NOT NULL DEFAULT 0,
    max_inflight_seen INTEGER NOT NULL DEFAULT 0,
    rate_scale REAL NOT NULL DEFAULT 1.0,
    rate_scale_until REAL NOT NULL DEFAULT 0.0,
    day TEXT NOT NULL DEFAULT '',
    day_count INTEGER NOT NULL DEFAULT 0,
    seq INTEGER NOT NULL DEFAULT 0,   -- fencing token, monotone per row
    PRIMARY KEY (binding, provider)
);
CREATE TABLE IF NOT EXISTS governor_events (
    binding TEXT NOT NULL,
    provider TEXT NOT NULL,
    ts REAL NOT NULL,
    kind TEXT NOT NULL,
    n INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_governor_events_ts
    ON governor_events (binding, provider, ts);
CREATE TABLE IF NOT EXISTS governor_leases (
    seq INTEGER NOT NULL,             -- the row's fencing seq at acquire time
    binding TEXT NOT NULL,
    provider TEXT NOT NULL,
    owner TEXT NOT NULL,              -- owner instance id (pid+boot-unique)
    n INTEGER NOT NULL,
    acquired_at REAL NOT NULL,
    heartbeat_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    paid_task_id TEXT,                -- PRES-004: recorded paid task ids, no replay
    released INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (seq, binding, provider)
);
CREATE INDEX IF NOT EXISTS idx_governor_leases_expiry
    ON governor_leases (binding, provider, expires_at);
"""

# Window events live in memory in governor.py (hot path); the store persists
# them ONLY for restart reconciliation of the 10 s window proof and prunes
# hard. Keep the durable history short: this is a limiter, not an audit log.
_EVENT_RETENTION_S = 120.0

# A lease without a heartbeat for longer than this is DEAD: its slots are
# reclaimable (kill -9 of a worker process must not leak an in-flight slot
# forever). Generous enough that a slow HTTP call is never stolen alive.
_LEASE_EXPIRY_S = float(os.environ.get(
    "PRESENTATION_GOVERNOR_LEASE_EXPIRY_S", "600"))

_HEARTBEAT_S = 60.0

# How long a crash-shadow binding row may keep an inflight count before the
# restart reconciliation may zero it: inflight truth is the SUM of live lease
# rows, so a plain counter is always derived, never authoritative.
_STATE_TTL_S = 86400.0 * 30


class GovernorStoreError(Exception):
    """Raised by the store for DURABLE failures the caller must surface
    (corrupt DB, unwritable path). governor.py catches it and degrades to
    process-local state -- the degradation is itself logged, never silent."""


def store_path(config_dir: Optional[Path] = None) -> Path:
    """Where the shared governor DB lives.

    $PRESENTATION_GOVERNOR_DB wins (tests, multi-container deployments that
    mount one shared volume). Otherwise the department config dir -- the same
    directory capacity_override.json and resource_profile.json live in, so
    one host = one store by construction. [PRES-004 isolation note] The
    department dir resolution honours the SAME env redirects every other
    presentation_job store honours ($PRESENTATION_CAPACITY_CONFIG_DIR, then
    the secrets-adjacent default), so a test or client box that redirects the
    profile stores automatically isolates the governor store too."""
    env = os.environ.get("PRESENTATION_GOVERNOR_DB")
    if env:
        return Path(env).expanduser()
    if config_dir is not None:
        return Path(config_dir) / "governor_state.sqlite3"
    for env_name in ("PRESENTATION_CAPACITY_CONFIG_DIR",
                     "PRESENTATION_RESOURCE_PROFILE_DIR"):
        d = os.environ.get(env_name)
        if d:
            return Path(d).expanduser() / "governor_state.sqlite3"
    try:
        from . import capacity as _cap  # package-relative (python3 -m)
    except ImportError:  # pragma: no cover - direct file run
        try:
            from presentation_job import capacity as _cap
        except ImportError:
            _cap = None
    if _cap is not None:
        try:
            return Path(_cap.department_config_dir()) / "governor_state.sqlite3"
        except Exception:  # noqa: BLE001 -- fall through to a tmp default
            pass
    return Path("/tmp") / "presentation_governor_state.sqlite3"


def account_binding_id(company_id: str, credential: str) -> str:
    """Opaque binding id for one ACCOUNT [PRES-004].

    ``co-<hex10>-cred-<hex12>``: the company id survives in readable form (it
    is not a secret and two separate client bindings must never share a
    bucket); the credential is HASHED, never stored. The hash is salted so
    the same key in two different company bindings cannot collide, and
    truncated so no rainbow-table surface exists. Two keys on the SAME
    provider account deliberately get DIFFERENT binding rows only if the
    deployment passes different credentials -- when an operator enrols
    multiple keys for one account they should enrol them as one binding
    (pass the account id, not each key); provider quota is account-wide, and
    the caller (governor.py) owns that decision via GOVERNOR_ACCOUNT_BINDING.
    """
    comp = str(company_id or "").strip().lower()
    cred = str(credential or "").strip()
    if not comp and not cred:
        return "shared-default"
    digest = hashlib.sha256(
        (comp + "\x00" + cred).encode("utf-8")).hexdigest()[:12]
    return f"co-{comp or 'none'}-{digest}" if comp else f"cred-{digest}"


_OWNER_LOCK = threading.Lock()
_OWNER = ""


def _owner_id() -> str:
    """Owner instance id for lease rows: pid + process boot nonce, written
    once per process. Distinguishes a restarted process from the dead one it
    replaced (PID reuse does not prove original ownership)."""
    global _OWNER
    with _OWNER_LOCK:
        if not _OWNER:
            _OWNER = f"pid{os.getpid()}-{os.urandom(4).hex()}"
        return _OWNER


class GovernorStore:
    """One shared-state authority on this host. A thread-local connection
    pool over ONE sqlite file in WAL mode."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path is not None else store_path()
        self._tls = threading.local()
        self._init_lock = threading.Lock()
        self._ready = False

    # -- connection -----------------------------------------------------
    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._tls, "conn", None)
        if conn is not None:
            return conn
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=30000")
        self._tls.conn = conn
        return conn

    def _ensure_schema(self) -> None:
        if self._ready:
            return
        with self._init_lock:
            if self._ready:
                return
            conn = self._conn()
            conn.executescript(_DDL)
            conn.execute(
                "INSERT INTO governor_meta (key, value) VALUES ('schema_version', ?) "
                "ON CONFLICT(key) DO NOTHING", (str(_SCHEMA_VERSION),))
            self._ready = True

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _now() -> float:
        return time.time()

    # -- state read/write ------------------------------------------------
    def load_state(self, binding: str, provider: str) -> Optional[dict]:
        """Row for (binding, provider), or None. Every failure -> None
        (degrade to process-local)."""
        try:
            self._ensure_schema()
            row = self._conn().execute(
                "SELECT tokens, last_refill, inflight, max_inflight_seen, "
                "rate_scale, rate_scale_until, day, day_count, seq "
                "FROM governor_state WHERE binding=? AND provider=?",
                (binding, provider)).fetchone()
        except Exception:  # noqa: BLE001 -- degrade, never crash the call path
            return None
        if row is None:
            return None
        return dict(row)

    def write_state(self, binding: str, provider: str, fields: dict) -> bool:
        """Upsert the durable fields of one row. Returns False on any store
        failure (caller keeps its in-memory copy)."""
        cols = ("tokens", "last_refill", "inflight", "max_inflight_seen",
                "rate_scale", "rate_scale_until", "day", "day_count", "seq")
        sets = [c for c in cols if c in fields]
        if not sets:
            return False
        try:
            self._ensure_schema()
            conn = self._conn()
            with self._txn(conn):
                conn.execute(
                    f"INSERT INTO governor_state (binding, provider) VALUES (?,?) "
                    f"ON CONFLICT(binding, provider) DO NOTHING",
                    (binding, provider))
                for c in sets:
                    conn.execute(
                        f"UPDATE governor_state SET {c}=? WHERE binding=? AND provider=?",
                        (fields[c], binding, provider))
            return True
        except Exception:  # noqa: BLE001
            return False


    @staticmethod
    def _rollback_quiet(conn: Optional[sqlite3.Connection]) -> None:
        if conn is None:
            return
        try:
            conn.execute("ROLLBACK")
        except Exception:  # noqa: BLE001
            pass

    @classmethod
    def _txn(cls, conn: sqlite3.Connection):
        """One write transaction with a GUARANTEED terminal state [PRES-004].

        sqlite3 connections in autocommit mode (isolation_level=None) keep a
        leaked txn open forever if an exception escapes between BEGIN
        IMMEDIATE and COMMIT -- every other thread's next write then blocks
        on the write lock until busy_timeout (measured: 20 s stalls inside a
        4-unit wave). This helper commits on success, rolls back on ANY
        exception, and clears a leaked txn from this thread's connection
        before opening a new one."""
        try:
            conn.execute("ROLLBACK")  # clear any leaked txn (no-op if none)
        except sqlite3.OperationalError:
            pass
        except Exception:  # noqa: BLE001
            pass

        class _Txn:
            def __enter__(self):
                conn.execute("BEGIN IMMEDIATE")
                return conn

            def __exit__(self, et, ev, tb):
                if et is None:
                    conn.execute("COMMIT")
                else:
                    try:
                        conn.execute("ROLLBACK")
                    except Exception:  # noqa: BLE001
                        pass
                return False  # never swallow: caller logs

        return _Txn()


    # -- events (restart reconciliation of the 10 s window) ---------------
    def record_event(self, binding: str, provider: str, kind: str,
                     n: int) -> bool:
        now = self._now()
        try:
            self._ensure_schema()
            conn = self._conn()
            with self._txn(conn):
                conn.execute(
                    "INSERT INTO governor_events (binding, provider, ts, kind, n) "
                    "VALUES (?,?,?,?,?)", (binding, provider, now, kind, n))
                conn.execute(
                    "DELETE FROM governor_events WHERE ts < ?",
                    (now - _EVENT_RETENTION_S,))
            return True
        except Exception:  # noqa: BLE001
            return False

    def load_events(self, binding: str, provider: str,
                    window_s: float) -> List[Tuple[float, str, int]]:
        try:
            self._ensure_schema()
            rows = self._conn().execute(
                "SELECT ts, kind, n FROM governor_events "
                "WHERE binding=? AND provider=? AND ts >= ? ORDER BY ts",
                (binding, provider, self._now() - window_s)).fetchall()
            return [(r["ts"], r["kind"], r["n"]) for r in rows]
        except Exception:  # noqa: BLE001
            return []

    # -- leases: fencing, heartbeat, expiry, restart reconciliation --------
    def record_lease(self, binding: str, provider: str, seq: int, n: int,
                     expires_s: float = _LEASE_EXPIRY_S,
                     paid_task_id: Optional[str] = None) -> bool:
        """Persist one live lease with fencing seq + expiry. Called AFTER the
        in-memory admission commits; a failure here is survivable (the
        in-memory lease is still valid for its own process) but logged by the
        caller."""
        now = self._now()
        try:
            self._ensure_schema()
            conn = self._conn()
            with self._txn(conn):
                conn.execute(
                    "INSERT INTO governor_leases (seq, binding, provider, owner, n, "
                    "acquired_at, heartbeat_at, expires_at, paid_task_id, released) "
                    "VALUES (?,?,?,?,?,?,?,?,?,0)",
                    (seq, binding, provider, _owner_id(), n, now, now,
                     now + expires_s, paid_task_id))
            return True
        except Exception:  # noqa: BLE001
            return False

    def heartbeat_lease(self, binding: str, provider: str, seq: int,
                        expires_s: float = _LEASE_EXPIRY_S) -> bool:
        try:
            self._ensure_schema()
            conn = self._conn()
            with self._txn(conn):
                cur = conn.execute(
                    "UPDATE governor_leases SET heartbeat_at=?, expires_at=? "
                    "WHERE binding=? AND provider=? AND seq=? AND owner=? AND released=0",
                    (self._now(), self._now() + expires_s, binding, provider,
                     seq, _owner_id()))
            return cur.rowcount > 0
        except Exception:  # noqa: BLE001
            return False

    def mark_released(self, binding: str, provider: str, seq: int) -> bool:
        try:
            self._ensure_schema()
            conn = self._conn()
            with self._txn(conn):
                cur = conn.execute(
                    "UPDATE governor_leases SET released=1, heartbeat_at=heartbeat_at "
                    "WHERE binding=? AND provider=? AND seq=? AND owner=?",
                    (binding, provider, seq, _owner_id()))
            return cur.rowcount > 0
        except Exception:  # noqa: BLE001
            return False

    def reconcile_inflight(self, binding: str, provider: str,
                           memory_inflight: int) -> int:
        """Restart reconciliation [PRES-004]: the AUTHORITATIVE inflight for
        this (binding, provider) is the number of UNRELEASED, UNEXPIRED lease
        rows. Expired rows (a worker was killed -9, its heartbeat stopped)
        are marked released so their slots are reclaimed. Returns the
        authoritative count; the caller reconciles its memory to it.

        ``memory_inflight`` counts this process's live leases; rows owned by
        OTHER processes are returned on top of it."""
        try:
            self._ensure_schema()
            conn = self._conn()
            now = self._now()
            # FAST PATH (read-only): the common case is an empty/clean lease
            # table; one indexed SELECT answers in microseconds so a timed
            # acquire's first touch never pays a write transaction for
            # nothing [PRES-004]. The write path runs only on real reclaim.
            fast = conn.execute(
                "SELECT "
                "  COALESCE(SUM(CASE WHEN released=0 AND expires_at < ? "
                "                    THEN n ELSE 0 END), 0) AS expired_n, "
                "  COALESCE(SUM(CASE WHEN released=0 AND owner != ? "
                "                    THEN n ELSE 0 END), 0) AS other_n "
                "FROM governor_leases WHERE binding=? AND provider=?",
                (now, _owner_id(), binding, provider)).fetchone()
            expired_n = int(fast["expired_n"] or 0)
            other_int = int(fast["other_n"] or 0)
            if expired_n == 0 and other_int == 0:
                return memory_inflight
            with self._txn(conn):
                # Reclaim: any unreleased row past expiry is dead (crash
                # shadow).
                if expired_n:
                    conn.execute(
                        "UPDATE governor_leases SET released=1 "
                        "WHERE binding=? AND provider=? AND released=0 AND expires_at < ?",
                        (binding, provider, now))
            # This owner's durable rows that memory does not know about are
            # crash shadows of an EARLIER boot sharing this pid (rare); when
            # the durable rows for this owner exceed what memory holds, reap
            # the surplus newest-first so the store matches memory.
            mine_rows = conn.execute(
                "SELECT seq, n FROM governor_leases "
                "WHERE binding=? AND provider=? AND released=0 AND owner = ? "
                "ORDER BY seq ASC",
                (binding, provider, _owner_id())).fetchall()
            mine_n = sum(int(r["n"] or 0) for r in mine_rows)
            if mine_n > memory_inflight:
                surplus = mine_n - memory_inflight
                to_release: List[int] = []
                for r in reversed(mine_rows):  # newest first
                    if surplus <= 0:
                        break
                    to_release.append(int(r["seq"]))
                    surplus -= int(r["n"] or 0)
                with self._txn(conn):
                    for seq in to_release:
                        conn.execute(
                            "UPDATE governor_leases SET released=1 "
                            "WHERE binding=? AND provider=? AND owner=? AND seq=?",
                            (binding, provider, _owner_id(), seq))
                mine_n = memory_inflight
            return memory_inflight + other_int
        except Exception:  # noqa: BLE001
            return memory_inflight

    def record_paid_task(self, binding: str, provider: str,
                         paid_task_id: str) -> bool:
        """Record one paid task id [PRES-004] so a restart cannot replay a
        bill. Dedup by (binding, provider, task id)."""
        if not str(paid_task_id or "").strip():
            return False
        try:
            self._ensure_schema()
            conn = self._conn()
            with self._txn(conn):
                conn.execute(
                    "INSERT OR IGNORE INTO governor_leases (seq, binding, provider, "
                    "owner, n, acquired_at, heartbeat_at, expires_at, paid_task_id, "
                    "released) VALUES (-1, ?, ?, 'paid-task', 0, ?, ?, ?, ?, 1)",
                    (binding, provider, self._now(), self._now(),
                     self._now() + _STATE_TTL_S, str(paid_task_id).strip()))
            return True
        except Exception:  # noqa: BLE001
            return False

    def has_paid_task(self, binding: str, provider: str,
                      paid_task_id: str) -> bool:
        try:
            self._ensure_schema()
            row = self._conn().execute(
                "SELECT 1 FROM governor_leases WHERE binding=? AND provider=? "
                "AND paid_task_id=? LIMIT 1",
                (binding, provider, str(paid_task_id).strip())).fetchone()
            return row is not None
        except Exception:  # noqa: BLE001
            return False

    # -- diagnostics ------------------------------------------------------
    def snapshot(self) -> dict:
        try:
            self._ensure_schema()
            conn = self._conn()
            rows = conn.execute(
                "SELECT binding, provider, tokens, inflight, day, day_count, "
                "rate_scale, rate_scale_until, seq FROM governor_state "
                "ORDER BY binding, provider").fetchall()
            return {
                "path": str(self.path),
                "schema_version": _SCHEMA_VERSION,
                "rows": [dict(r) for r in rows],
            }
        except Exception as exc:  # noqa: BLE001
            return {"path": str(self.path), "error": str(exc)}


_STORE_LOCK = threading.Lock()
_STORE: Optional[GovernorStore] = None


def shared_store() -> Optional[GovernorStore]:
    """The ONE store instance per process, or None when the DB cannot open
    (read-only volume, corrupt file): a process that cannot share falls back
    to its own dict rather than pretending it did."""
    global _STORE
    with _STORE_LOCK:
        if _STORE is not None:
            return _STORE
        try:
            store = GovernorStore()
            store._ensure_schema()
            _STORE = store
        except Exception:  # noqa: BLE001 -- no shared store on this host
            _STORE = None
        return _STORE