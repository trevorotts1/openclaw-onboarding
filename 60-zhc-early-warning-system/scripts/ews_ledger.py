#!/usr/bin/env python3
# =============================================================================
# SKILL 60 - ZHC EARLY WARNING SYSTEM :: ews_ledger.py
# THE SOLE STATE WRITER (spec Section 4.2)
# -----------------------------------------------------------------------------
# The durable state layer the whole sentinel stands on. NO OTHER EWS SCRIPT
# WRITES STATE: the sentinel, the snapshotter, the baseline manager, the alert
# router, the aggregator, and the cadence recommender all go THROUGH this module
# (import Ledger) or shell these subcommands. One writer = no races, no torn
# rows, no wedged pipeline.
#
# STORE: <state_dir>/ews.db (Mac ~/.openclaw/ews, VPS /data/.openclaw/ews),
# SQLite in WAL mode, owned by the box user. Tables (spec 4.2):
#   events          signal, severity, key path or file:line, class, tick ts, ack
#   offsets         config-audit byte offset + per-log scan offsets (S8 reads NEW bytes only)
#   snapshots       path, ts, sha256, trigger event id, revert command text, previousHash, argv
#   baseline_stamps S4 approval records (key path + new value hash + operator + ts)
#   digests         what was sent when, for dedup
#   meta            schema_version, platform, and bookkeeping
#
# STDLIB ONLY (sqlite3). Zero third-party deps, calls NO model, NO network.
# Runs identically on every box (operator canary or client). DOCTRINE: move in
# silence (operator-verbose only); NEVER print a secret value (this ledger stores
# HASHES and key PATHS, never a credential value); state writes run as the box
# user, never root (a root-owned file under ~/.openclaw freezes the gateway - we
# WARN loudly here; the config-touching scripts hard-refuse root).
#
# EXIT CODE CONTRACT (stable; every subcommand):
#   0  OK (including an idempotent replay no-op, and a TRUE predicate)
#   1  unexpected error
#   2  usage error
#   3  predicate FALSE / not found (has-stamp absent, recent-digest none, no such id)
# =============================================================================
"""ews_ledger.py - the sole durable-state writer for the ZHC Early Warning System."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

EX_OK = 0
EX_ERR = 1
EX_USAGE = 2
EX_FALSE = 3

SCHEMA_VERSION = "1"

VALID_SEVERITIES = ("P1", "P2", "P3", "DRILL", "INFO")
VALID_ACK = ("open", "acked", "reverted", "resolved", "escalated")


# --------------------------------------------------------------------------- #
# time / hashing helpers
# --------------------------------------------------------------------------- #
def now_utc() -> str:
    """ISO-8601 UTC, second precision, explicit offset."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso(s: str):
    if not s:
        return None
    try:
        # tolerate a trailing Z or +00:00
        s2 = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s2)
    except (ValueError, TypeError):
        return None


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# platform / path resolution (shared by the whole skill)
# --------------------------------------------------------------------------- #
def detect_platform() -> str:
    """'vps' when /data/.openclaw exists (the container data root), else 'mac'.
    Env EWS_PLATFORM overrides for tests."""
    env = os.environ.get("EWS_PLATFORM", "").strip().lower()
    if env in ("mac", "vps"):
        return env
    if Path("/data/.openclaw").is_dir():
        return "vps"
    return "mac"


def openclaw_root() -> Path:
    """The .openclaw root for this box. Env EWS_OPENCLAW_ROOT overrides for tests."""
    env = os.environ.get("EWS_OPENCLAW_ROOT", "").strip()
    if env:
        return Path(env).expanduser()
    if detect_platform() == "vps":
        return Path("/data/.openclaw")
    home = os.environ.get("HOME") or os.path.expanduser("~")
    return Path(home) / ".openclaw"


def default_state_dir() -> Path:
    """<openclaw_root>/ews. Env EWS_STATE_DIR overrides (used by every self-test)."""
    env = os.environ.get("EWS_STATE_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    return openclaw_root() / "ews"


def snapshots_dir(state_dir: Path | None = None) -> Path:
    return (state_dir or default_state_dir()) / "snapshots"


def db_path(state_dir: Path | None = None) -> Path:
    return (state_dir or default_state_dir()) / "ews.db"


# --------------------------------------------------------------------------- #
# root safety
# --------------------------------------------------------------------------- #
def is_root() -> bool:
    try:
        return hasattr(os, "geteuid") and os.geteuid() == 0
    except Exception:
        return False


def warn_root_state() -> None:
    if is_root():
        sys.stderr.write(
            "WARN [ews_ledger]: running as root. EWS state should be written by the "
            "box user; a root-owned file under .openclaw can freeze the gateway.\n"
        )


# --------------------------------------------------------------------------- #
# The ledger
# --------------------------------------------------------------------------- #
class Ledger:
    """The single SQLite-WAL writer. Construct with a state dir (or default);
    every mutation is a single committed transaction."""

    def __init__(self, state_dir: Path | None = None):
        self.state_dir = Path(state_dir) if state_dir else default_state_dir()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.state_dir, 0o700)
        except OSError:
            pass
        self.db_path = db_path(self.state_dir)
        self.conn = sqlite3.connect(str(self.db_path), timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=30000")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._bootstrap()

    def close(self):
        try:
            self.conn.close()
        except sqlite3.Error:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    # ---- schema ----------------------------------------------------------
    def _bootstrap(self):
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                event_id        INTEGER PRIMARY KEY AUTOINCREMENT,
                signal          TEXT NOT NULL,
                severity        TEXT NOT NULL,
                key_path        TEXT,
                class           TEXT,
                detail          TEXT,
                tick_ts         TEXT NOT NULL,
                ack_state       TEXT NOT NULL DEFAULT 'open',
                ack_ts          TEXT,
                dedup_key       TEXT
            );
            CREATE TABLE IF NOT EXISTS offsets (
                name            TEXT PRIMARY KEY,
                offset          INTEGER NOT NULL DEFAULT 0,
                updated_at      TEXT
            );
            CREATE TABLE IF NOT EXISTS snapshots (
                snapshot_id       INTEGER PRIMARY KEY AUTOINCREMENT,
                path              TEXT NOT NULL,
                ts                TEXT NOT NULL,
                sha256            TEXT,
                trigger_event_id  INTEGER,
                revert_cmd        TEXT,
                previous_hash     TEXT,
                argv              TEXT
            );
            CREATE TABLE IF NOT EXISTS baseline_stamps (
                stamp_id        INTEGER PRIMARY KEY AUTOINCREMENT,
                key_path        TEXT NOT NULL,
                new_value_hash  TEXT NOT NULL,
                operator        TEXT,
                ts              TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS digests (
                digest_id       INTEGER PRIMARY KEY AUTOINCREMENT,
                kind            TEXT,
                dedup_key       TEXT,
                sent_ts         TEXT NOT NULL,
                payload         TEXT
            );
            CREATE TABLE IF NOT EXISTS meta (
                key             TEXT PRIMARY KEY,
                value           TEXT
            );
            CREATE INDEX IF NOT EXISTS ix_events_open  ON events(ack_state, signal);
            CREATE INDEX IF NOT EXISTS ix_events_ts    ON events(tick_ts);
            CREATE INDEX IF NOT EXISTS ix_stamps_key   ON baseline_stamps(key_path);
            CREATE INDEX IF NOT EXISTS ix_digests_key  ON digests(dedup_key, sent_ts);
            """
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO meta(key,value) VALUES('schema_version',?)",
            (SCHEMA_VERSION,))
        self.conn.execute(
            "INSERT OR IGNORE INTO meta(key,value) VALUES('platform',?)",
            (detect_platform(),))
        self.conn.commit()

    # ---- meta ------------------------------------------------------------
    def set_meta(self, key, value):
        self.conn.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
        self.conn.commit()

    def get_meta(self, key, default=None):
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    # ---- events ----------------------------------------------------------
    def record_event(self, signal, severity, key_path=None, klass=None,
                     detail=None, tick_ts=None, dedup_key=None) -> int:
        if severity not in VALID_SEVERITIES:
            raise ValueError("invalid severity %r" % severity)
        ts = tick_ts or now_utc()
        cur = self.conn.execute(
            "INSERT INTO events(signal,severity,key_path,class,detail,tick_ts,dedup_key) "
            "VALUES(?,?,?,?,?,?,?)",
            (signal, severity, key_path, klass, detail, ts, dedup_key))
        self.conn.commit()
        return cur.lastrowid

    def ack_event(self, event_id, new_state="acked") -> bool:
        if new_state not in VALID_ACK:
            raise ValueError("invalid ack state %r" % new_state)
        cur = self.conn.execute(
            "UPDATE events SET ack_state=?, ack_ts=? WHERE event_id=?",
            (new_state, now_utc(), event_id))
        self.conn.commit()
        return cur.rowcount > 0

    def open_events(self, signal=None):
        if signal:
            rows = self.conn.execute(
                "SELECT * FROM events WHERE ack_state='open' AND signal=? ORDER BY event_id",
                (signal,)).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM events WHERE ack_state='open' ORDER BY event_id").fetchall()
        return [dict(r) for r in rows]

    def events_since(self, since_iso):
        rows = self.conn.execute(
            "SELECT * FROM events WHERE tick_ts >= ? ORDER BY event_id", (since_iso,)).fetchall()
        return [dict(r) for r in rows]

    def unacked_p1_older_than(self, minutes):
        """Open P1 events whose tick_ts is older than `minutes` and not yet escalated."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        out = []
        for r in self.conn.execute(
                "SELECT * FROM events WHERE severity='P1' AND ack_state='open' "
                "ORDER BY event_id").fetchall():
            ts = _parse_iso(r["tick_ts"])
            if ts is not None and ts <= cutoff:
                out.append(dict(r))
        return out

    # ---- offsets ---------------------------------------------------------
    def get_offset(self, name) -> int:
        row = self.conn.execute("SELECT offset FROM offsets WHERE name=?", (name,)).fetchone()
        return int(row["offset"]) if row else 0

    def set_offset(self, name, offset):
        self.conn.execute(
            "INSERT INTO offsets(name,offset,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET offset=excluded.offset, updated_at=excluded.updated_at",
            (name, int(offset), now_utc()))
        self.conn.commit()

    # ---- snapshots -------------------------------------------------------
    def record_snapshot(self, path, sha256=None, trigger_event_id=None,
                        revert_cmd=None, previous_hash=None, argv=None) -> int:
        cur = self.conn.execute(
            "INSERT INTO snapshots(path,ts,sha256,trigger_event_id,revert_cmd,previous_hash,argv) "
            "VALUES(?,?,?,?,?,?,?)",
            (str(path), now_utc(), sha256, trigger_event_id, revert_cmd, previous_hash, argv))
        self.conn.commit()
        return cur.lastrowid

    def list_snapshots(self, limit=None):
        q = "SELECT * FROM snapshots ORDER BY snapshot_id DESC"
        if limit:
            q += " LIMIT %d" % int(limit)
        return [dict(r) for r in self.conn.execute(q).fetchall()]

    def snapshot_by_ts(self, ts_token):
        """Find a snapshot by its utc-ts token embedded in the path or by ts prefix."""
        rows = self.conn.execute("SELECT * FROM snapshots ORDER BY snapshot_id DESC").fetchall()
        for r in rows:
            if ts_token in str(r["path"]) or str(r["ts"]).startswith(ts_token):
                return dict(r)
        return None

    def prune_snapshots(self, keep_count, keep_days):
        """Delete snapshot ROWS beyond the retention rule (keep the LARGER of the two
        windows, per D7). Returns the file paths of pruned rows so the caller (ews_snapshot)
        can unlink the files. The row set kept = union of (newest keep_count) and
        (all within keep_days)."""
        rows = self.list_snapshots()
        if not rows:
            return []
        cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
        keep_ids = set()
        # newest keep_count
        for r in rows[:keep_count]:
            keep_ids.add(r["snapshot_id"])
        # all within keep_days
        for r in rows:
            ts = _parse_iso(r["ts"])
            if ts is not None and ts >= cutoff:
                keep_ids.add(r["snapshot_id"])
        pruned = [r for r in rows if r["snapshot_id"] not in keep_ids]
        for r in pruned:
            self.conn.execute("DELETE FROM snapshots WHERE snapshot_id=?", (r["snapshot_id"],))
        self.conn.commit()
        return [r["path"] for r in pruned]

    # ---- baseline stamps (S4) -------------------------------------------
    def record_stamp(self, key_path, new_value_hash, operator=None) -> int:
        cur = self.conn.execute(
            "INSERT INTO baseline_stamps(key_path,new_value_hash,operator,ts) VALUES(?,?,?,?)",
            (key_path, new_value_hash, operator, now_utc()))
        self.conn.commit()
        return cur.lastrowid

    def has_stamp(self, key_path, new_value_hash) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM baseline_stamps WHERE key_path=? AND new_value_hash=? LIMIT 1",
            (key_path, new_value_hash)).fetchone()
        return row is not None

    def stamps_for(self, key_path):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM baseline_stamps WHERE key_path=? ORDER BY stamp_id", (key_path,)).fetchall()]

    # ---- digests (dedup) -------------------------------------------------
    def record_digest(self, kind, dedup_key, payload=None) -> int:
        cur = self.conn.execute(
            "INSERT INTO digests(kind,dedup_key,sent_ts,payload) VALUES(?,?,?,?)",
            (kind, dedup_key, now_utc(), payload))
        self.conn.commit()
        return cur.lastrowid

    def recent_digest(self, dedup_key, window_hours):
        """Most recent digest row for dedup_key within window_hours, else None."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        for r in self.conn.execute(
                "SELECT * FROM digests WHERE dedup_key=? ORDER BY digest_id DESC", (dedup_key,)).fetchall():
            ts = _parse_iso(r["sent_ts"])
            if ts is not None and ts >= cutoff:
                return dict(r)
        return None

    def count_digests_since(self, since_iso, kind=None):
        if kind:
            row = self.conn.execute(
                "SELECT COUNT(*) AS n FROM digests WHERE sent_ts >= ? AND kind=?",
                (since_iso, kind)).fetchone()
        else:
            row = self.conn.execute(
                "SELECT COUNT(*) AS n FROM digests WHERE sent_ts >= ?", (since_iso,)).fetchone()
        return int(row["n"])


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _emit(obj):
    sys.stdout.write(json.dumps(obj, sort_keys=True) + "\n")


def _cli(argv=None):
    ap = argparse.ArgumentParser(prog="ews_ledger.py",
                                 description="The sole state writer for the ZHC Early Warning System.")
    ap.add_argument("--state-dir", help="override the EWS state dir (default $EWS_STATE_DIR or <openclaw>/ews)")
    ap.add_argument("--self-test", action="store_true", help="run the deterministic self-test and exit")
    sub = ap.add_subparsers(dest="cmd", required=False)

    sub.add_parser("init", help="bootstrap the ledger schema and print its status")

    sp = sub.add_parser("record-event", help="insert a signal event")
    sp.add_argument("--signal", required=True)
    sp.add_argument("--severity", required=True, choices=VALID_SEVERITIES)
    sp.add_argument("--key-path")
    sp.add_argument("--class", dest="klass")
    sp.add_argument("--detail")
    sp.add_argument("--dedup-key")

    sp = sub.add_parser("ack-event", help="mark an event acked/reverted/resolved/escalated")
    sp.add_argument("--event-id", type=int, required=True)
    sp.add_argument("--state", default="acked", choices=VALID_ACK)

    sp = sub.add_parser("get-offset"); sp.add_argument("--name", required=True)
    sp = sub.add_parser("set-offset")
    sp.add_argument("--name", required=True); sp.add_argument("--offset", type=int, required=True)

    sp = sub.add_parser("record-snapshot")
    sp.add_argument("--path", required=True); sp.add_argument("--sha256")
    sp.add_argument("--trigger-event-id", type=int); sp.add_argument("--revert-cmd")
    sp.add_argument("--previous-hash"); sp.add_argument("--argv")

    sp = sub.add_parser("list-snapshots"); sp.add_argument("--limit", type=int)

    sp = sub.add_parser("record-stamp")
    sp.add_argument("--key-path", required=True); sp.add_argument("--new-value-hash", required=True)
    sp.add_argument("--operator")

    sp = sub.add_parser("has-stamp", help="exit 0 if a matching approval stamp exists, else exit 3")
    sp.add_argument("--key-path", required=True); sp.add_argument("--new-value-hash", required=True)

    sp = sub.add_parser("record-digest")
    sp.add_argument("--kind"); sp.add_argument("--dedup-key", required=True); sp.add_argument("--payload")

    sp = sub.add_parser("recent-digest", help="exit 0 if a digest for dedup-key is within the window, else 3")
    sp.add_argument("--dedup-key", required=True); sp.add_argument("--window-hours", type=float, default=6.0)

    sp = sub.add_parser("open-events"); sp.add_argument("--signal")

    args = ap.parse_args(argv)

    if getattr(args, "self_test", False):
        return self_test()
    if not args.cmd:
        ap.error("a subcommand is required (or use --self-test)")

    warn_root_state()
    state_dir = Path(args.state_dir) if args.state_dir else None
    try:
        led = Ledger(state_dir)
    except sqlite3.Error as exc:
        sys.stderr.write("ERROR [ews_ledger]: cannot open ledger: %s\n" % exc)
        return EX_ERR

    try:
        c = args.cmd
        if c == "init":
            _emit({"ok": True, "db": str(led.db_path), "schema_version": led.get_meta("schema_version"),
                   "platform": led.get_meta("platform")})
        elif c == "record-event":
            eid = led.record_event(args.signal, args.severity, args.key_path, args.klass,
                                   args.detail, dedup_key=args.dedup_key)
            _emit({"ok": True, "event_id": eid})
        elif c == "ack-event":
            ok = led.ack_event(args.event_id, args.state)
            _emit({"ok": ok, "event_id": args.event_id, "state": args.state})
            if not ok:
                return EX_FALSE
        elif c == "get-offset":
            _emit({"name": args.name, "offset": led.get_offset(args.name)})
        elif c == "set-offset":
            led.set_offset(args.name, args.offset)
            _emit({"ok": True, "name": args.name, "offset": args.offset})
        elif c == "record-snapshot":
            sid = led.record_snapshot(args.path, args.sha256, args.trigger_event_id,
                                      args.revert_cmd, args.previous_hash, args.argv)
            _emit({"ok": True, "snapshot_id": sid})
        elif c == "list-snapshots":
            _emit({"snapshots": led.list_snapshots(args.limit)})
        elif c == "record-stamp":
            sid = led.record_stamp(args.key_path, args.new_value_hash, args.operator)
            _emit({"ok": True, "stamp_id": sid})
        elif c == "has-stamp":
            present = led.has_stamp(args.key_path, args.new_value_hash)
            _emit({"present": present})
            return EX_OK if present else EX_FALSE
        elif c == "record-digest":
            did = led.record_digest(args.kind, args.dedup_key, args.payload)
            _emit({"ok": True, "digest_id": did})
        elif c == "recent-digest":
            r = led.recent_digest(args.dedup_key, args.window_hours)
            _emit({"present": r is not None, "digest": r})
            return EX_OK if r is not None else EX_FALSE
        elif c == "open-events":
            _emit({"events": led.open_events(args.signal)})
        else:
            sys.stderr.write("ERROR: unknown command\n")
            return EX_USAGE
        return EX_OK
    except ValueError as exc:
        sys.stderr.write("ERROR [ews_ledger]: %s\n" % exc)
        return EX_USAGE
    except sqlite3.Error as exc:
        sys.stderr.write("ERROR [ews_ledger]: db error: %s\n" % exc)
        return EX_ERR
    finally:
        led.close()


# --------------------------------------------------------------------------- #
# self-test (deterministic, no network, no model)
# --------------------------------------------------------------------------- #
def self_test():
    import tempfile
    print("[ews_ledger] self-test: schema, events, offsets, snapshots, stamps, digests, prune")
    with tempfile.TemporaryDirectory() as td:
        sd = Path(td) / "ews"
        led = Ledger(sd)
        assert led.get_meta("schema_version") == SCHEMA_VERSION
        assert led.db_path.is_file()
        print("  schema case: PASS (db created, WAL, schema_version pinned)")

        # events
        eid = led.record_event("S4", "P1", key_path="agents.defaults.maxConcurrent",
                               klass="cap", detail="raise 16->64")
        assert eid > 0
        assert len(led.open_events()) == 1
        assert len(led.open_events("S4")) == 1
        assert led.ack_event(eid, "reverted")
        assert len(led.open_events()) == 0
        assert not led.ack_event(999999)  # nonexistent
        print("  events case: PASS (record/query/ack, nonexistent ack is False)")

        # invalid severity is refused
        try:
            led.record_event("S1", "BOGUS")
            raise AssertionError("bad severity accepted")
        except ValueError:
            pass
        print("  validation case: PASS (bad severity refused)")

        # offsets
        assert led.get_offset("config-audit") == 0
        led.set_offset("config-audit", 4096)
        assert led.get_offset("config-audit") == 4096
        led.set_offset("config-audit", 8192)
        assert led.get_offset("config-audit") == 8192
        print("  offsets case: PASS (absent=0, upsert monotone by writer)")

        # stamps (S4 approval)
        h = sha256_hex("64")
        assert not led.has_stamp("agents.defaults.maxConcurrent", h)
        led.record_stamp("agents.defaults.maxConcurrent", h, operator="operator")
        assert led.has_stamp("agents.defaults.maxConcurrent", h)
        assert not led.has_stamp("agents.defaults.maxConcurrent", sha256_hex("128"))
        print("  stamps case: PASS (absent, then present after record; wrong hash still absent)")

        # digests (dedup)
        assert led.recent_digest("S6|acme|write", 6) is None
        led.record_digest("alert", "S6|acme|write", payload="x")
        assert led.recent_digest("S6|acme|write", 6) is not None
        assert led.recent_digest("S6|acme|write", 0) is None  # zero window excludes it
        print("  digests case: PASS (dedup window honored)")

        # snapshots + prune (D7: larger of count/days)
        for i in range(5):
            led.record_snapshot("%s/snapshots/openclaw.json.20260101T00000%d.aa" % (td, i),
                                sha256="deadbeef%d" % i)
        assert len(led.list_snapshots()) == 5
        # keep_count=2, keep_days huge -> days wins, nothing pruned (all recent)
        assert led.prune_snapshots(2, 9999) == []
        assert len(led.list_snapshots()) == 5
        # keep_count=2, keep_days=0 -> count wins, prune 3 oldest
        pruned = led.prune_snapshots(2, 0)
        assert len(pruned) == 3, pruned
        assert len(led.list_snapshots()) == 2
        print("  snapshots/prune case: PASS (D7 keeps the LARGER window)")

        # ts lookup for revert
        led.record_snapshot("%s/snapshots/openclaw.json.20260202T120000.bb" % td, sha256="cafe")
        assert led.snapshot_by_ts("20260202T120000") is not None
        assert led.snapshot_by_ts("nope") is None
        print("  snapshot_by_ts case: PASS (revert lookup by ts token)")

        led.close()

        # reopen -> durability
        led2 = Ledger(sd)
        assert led2.get_offset("config-audit") == 8192
        assert led2.has_stamp("agents.defaults.maxConcurrent", h)
        led2.close()
        print("  durability case: PASS (state survives close/reopen)")

    print("[ews_ledger] self-test: PASS")
    return EX_OK


if __name__ == "__main__":
    sys.exit(_cli())
