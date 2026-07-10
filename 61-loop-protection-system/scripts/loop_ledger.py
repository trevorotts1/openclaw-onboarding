#!/usr/bin/env python3
# =============================================================================
# SKILL 61 - LOOP PROTECTION SYSTEM :: loop_ledger.py
# THE SOLE STATE WRITER (spec Section 6.1 "State: one writer")
# -----------------------------------------------------------------------------
# The durable state layer the whole watchdog stands on. NO OTHER LOOP-PROTECTION
# SCRIPT WRITES STATE: the watchdog, the detectors, the breaker, the backoff
# engine, the kill cards, and the escalator all go THROUGH this module (import
# Ledger) or shell these subcommands. One writer = no races, no torn rows, no
# wedged pipeline (the single-writer law, mirroring Skill 60's ews_ledger).
#
# STORE: <state_dir>/loop.db (Mac ~/.openclaw/loop-protection,
# VPS /data/.openclaw/loop-protection), SQLite in WAL mode, box-user-owned.
# Tables (spec 6.1):
#   findings       class, unit, evidence path, severity, state
#   fix_actions    what / when / verify outcome / revert line
#   breaker_state  per unit: window counts, tripped, parked
#   backoff_state  per job: attempt, next_at, base/cap
#   offsets        per-log byte offsets (D3 reads only NEW bytes)
#   digests        dedup (one alert per class/box per window)
#   meta           schema_version, platform, box, role, armed
#
# STDLIB ONLY (sqlite3). Zero third-party deps, calls NO model, NO network.
# DOCTRINE: operator-verbose only (never a client surface); NEVER store or print
# a secret VALUE (this ledger stores classes, unit names, key PATHS, and hashes,
# never a credential value); state writes run as the box user, never root (a
# root-owned file under .openclaw freezes the gateway - WARN loudly here; the
# config-touching kill cards hard-refuse root).
#
# EXIT CODE CONTRACT (stable; every subcommand):
#   0  OK (including an idempotent replay no-op, and a TRUE predicate)
#   1  unexpected error
#   2  usage error
#   3  predicate FALSE / not found
# =============================================================================
"""loop_ledger.py - the sole durable-state writer for the Loop Protection System."""

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

VALID_SEVERITIES = ("P1", "P2", "P3", "WARN", "DRILL", "INFO")
VALID_FINDING_STATE = ("open", "planned", "fixed", "verified", "parked",
                       "escalated", "false_positive", "resolved")


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
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# platform / path resolution (shared by the whole skill)
# --------------------------------------------------------------------------- #
def detect_platform() -> str:
    """'vps' when /data/.openclaw exists (the container data root), else 'mac'.
    Env LOOP_PLATFORM overrides for tests."""
    env = os.environ.get("LOOP_PLATFORM", "").strip().lower()
    if env in ("mac", "vps"):
        return env
    if Path("/data/.openclaw").is_dir():
        return "vps"
    return "mac"


def openclaw_root() -> Path:
    """The .openclaw root for this box. Env LOOP_OPENCLAW_ROOT overrides for tests."""
    env = os.environ.get("LOOP_OPENCLAW_ROOT", "").strip()
    if env:
        return Path(env).expanduser()
    if detect_platform() == "vps":
        return Path("/data/.openclaw")
    home = os.environ.get("HOME") or os.path.expanduser("~")
    return Path(home) / ".openclaw"


def default_state_dir() -> Path:
    """<openclaw_root>/loop-protection. Env LOOP_STATE_DIR overrides (self-tests)."""
    env = os.environ.get("LOOP_STATE_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    return openclaw_root() / "loop-protection"


def db_path(state_dir: Path | None = None) -> Path:
    return (state_dir or default_state_dir()) / "loop.db"


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
            "WARN [loop_ledger]: running as root. Loop Protection state should be "
            "written by the box user; a root-owned file under .openclaw can freeze "
            "the gateway.\n")


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
            CREATE TABLE IF NOT EXISTS findings (
                finding_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                loop_class      TEXT NOT NULL,
                unit            TEXT,
                evidence_path   TEXT,
                severity        TEXT NOT NULL,
                detail          TEXT,
                tier            INTEGER,
                state           TEXT NOT NULL DEFAULT 'open',
                tick_ts         TEXT NOT NULL,
                updated_ts      TEXT,
                dedup_key       TEXT
            );
            CREATE TABLE IF NOT EXISTS fix_actions (
                action_id       INTEGER PRIMARY KEY AUTOINCREMENT,
                finding_id      INTEGER,
                fix_class       TEXT,
                unit            TEXT,
                what            TEXT,
                applied_ts      TEXT NOT NULL,
                verify_outcome  TEXT,
                revert_cmd      TEXT,
                dry_run         INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS breaker_state (
                unit            TEXT NOT NULL,
                breaker         TEXT NOT NULL,
                window_start    TEXT,
                event_count     INTEGER NOT NULL DEFAULT 0,
                day_count       INTEGER NOT NULL DEFAULT 0,
                day_start       TEXT,
                tripped         INTEGER NOT NULL DEFAULT 0,
                parked          INTEGER NOT NULL DEFAULT 0,
                updated_ts      TEXT,
                PRIMARY KEY (unit, breaker)
            );
            CREATE TABLE IF NOT EXISTS backoff_state (
                job             TEXT PRIMARY KEY,
                attempt         INTEGER NOT NULL DEFAULT 0,
                base_seconds    INTEGER NOT NULL,
                cap_seconds     INTEGER NOT NULL,
                next_at         TEXT,
                last_at         TEXT,
                escalated       INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS offsets (
                name            TEXT PRIMARY KEY,
                offset          INTEGER NOT NULL DEFAULT 0,
                updated_at      TEXT
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
            CREATE INDEX IF NOT EXISTS ix_find_open ON findings(state, loop_class);
            CREATE INDEX IF NOT EXISTS ix_find_ts   ON findings(tick_ts);
            CREATE INDEX IF NOT EXISTS ix_dig_key   ON digests(dedup_key, sent_ts);
            """
        )
        self.conn.execute(
            "INSERT OR IGNORE INTO meta(key,value) VALUES('schema_version',?)",
            (SCHEMA_VERSION,))
        self.conn.execute(
            "INSERT OR IGNORE INTO meta(key,value) VALUES('platform',?)",
            (detect_platform(),))
        # DRY_RUN / observe-only burn-in is the DEFAULT on any fresh box (spec 6.1).
        self.conn.execute(
            "INSERT OR IGNORE INTO meta(key,value) VALUES('armed','false')")
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

    def is_armed(self) -> bool:
        """True only when the operator has explicitly armed this box (spec 6.1:
        DRY_RUN observe-only is the default for the first 7 days)."""
        return str(self.get_meta("armed", "false")).lower() == "true"

    # ---- findings --------------------------------------------------------
    def record_finding(self, loop_class, severity, unit=None, evidence_path=None,
                       detail=None, tier=None, tick_ts=None, dedup_key=None) -> int:
        if severity not in VALID_SEVERITIES:
            raise ValueError("invalid severity %r" % severity)
        ts = tick_ts or now_utc()
        cur = self.conn.execute(
            "INSERT INTO findings(loop_class,unit,evidence_path,severity,detail,tier,"
            "tick_ts,updated_ts,dedup_key) VALUES(?,?,?,?,?,?,?,?,?)",
            (loop_class, unit, evidence_path, severity, detail, tier, ts, ts, dedup_key))
        self.conn.commit()
        return cur.lastrowid

    def set_finding_state(self, finding_id, state) -> bool:
        if state not in VALID_FINDING_STATE:
            raise ValueError("invalid finding state %r" % state)
        cur = self.conn.execute(
            "UPDATE findings SET state=?, updated_ts=? WHERE finding_id=?",
            (state, now_utc(), finding_id))
        self.conn.commit()
        return cur.rowcount > 0

    def open_findings(self, loop_class=None):
        if loop_class:
            rows = self.conn.execute(
                "SELECT * FROM findings WHERE state='open' AND loop_class=? "
                "ORDER BY finding_id", (loop_class,)).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM findings WHERE state='open' ORDER BY finding_id").fetchall()
        return [dict(r) for r in rows]

    def all_findings(self, limit=None):
        q = "SELECT * FROM findings ORDER BY finding_id DESC"
        if limit:
            q += " LIMIT %d" % int(limit)
        return [dict(r) for r in self.conn.execute(q).fetchall()]

    def get_finding(self, finding_id):
        """One finding by id (read-only). The finding->unit lookup the operator
        one-line revert (`unpark --finding <id>`) and `fix <id>` both stand on."""
        row = self.conn.execute(
            "SELECT * FROM findings WHERE finding_id=?", (finding_id,)).fetchone()
        return dict(row) if row else None

    def unacked_p1_older_than(self, minutes):
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        out = []
        for r in self.conn.execute(
                "SELECT * FROM findings WHERE severity='P1' AND state='open' "
                "ORDER BY finding_id").fetchall():
            ts = _parse_iso(r["tick_ts"])
            if ts is not None and ts <= cutoff:
                out.append(dict(r))
        return out

    # ---- fix actions -----------------------------------------------------
    def record_fix(self, finding_id, fix_class, unit=None, what=None,
                   verify_outcome=None, revert_cmd=None, dry_run=True) -> int:
        cur = self.conn.execute(
            "INSERT INTO fix_actions(finding_id,fix_class,unit,what,applied_ts,"
            "verify_outcome,revert_cmd,dry_run) VALUES(?,?,?,?,?,?,?,?)",
            (finding_id, fix_class, unit, what, now_utc(), verify_outcome,
             revert_cmd, 1 if dry_run else 0))
        self.conn.commit()
        return cur.lastrowid

    def fixes_for_target_since(self, unit, hours):
        """Count fix_actions applied to `unit` within the window (healer breaker)."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        n = 0
        for r in self.conn.execute(
                "SELECT applied_ts FROM fix_actions WHERE unit=?", (unit,)).fetchall():
            ts = _parse_iso(r["applied_ts"])
            if ts is not None and ts >= cutoff:
                n += 1
        return n

    def list_fixes(self, limit=None):
        q = "SELECT * FROM fix_actions ORDER BY action_id DESC"
        if limit:
            q += " LIMIT %d" % int(limit)
        return [dict(r) for r in self.conn.execute(q).fetchall()]

    # ---- breaker state ---------------------------------------------------
    def get_breaker(self, unit, breaker):
        row = self.conn.execute(
            "SELECT * FROM breaker_state WHERE unit=? AND breaker=?",
            (unit, breaker)).fetchone()
        return dict(row) if row else None

    def upsert_breaker(self, unit, breaker, **fields):
        cur = self.get_breaker(unit, breaker) or {
            "unit": unit, "breaker": breaker, "window_start": None,
            "event_count": 0, "day_count": 0, "day_start": None,
            "tripped": 0, "parked": 0}
        cur.update(fields)
        cur["updated_ts"] = now_utc()
        self.conn.execute(
            "INSERT INTO breaker_state(unit,breaker,window_start,event_count,day_count,"
            "day_start,tripped,parked,updated_ts) VALUES(?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(unit,breaker) DO UPDATE SET window_start=excluded.window_start,"
            "event_count=excluded.event_count,day_count=excluded.day_count,"
            "day_start=excluded.day_start,tripped=excluded.tripped,"
            "parked=excluded.parked,updated_ts=excluded.updated_ts",
            (unit, breaker, cur["window_start"], int(cur["event_count"]),
             int(cur["day_count"]), cur["day_start"], int(cur["tripped"]),
             int(cur["parked"]), cur["updated_ts"]))
        self.conn.commit()
        return cur

    def parked_units(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM breaker_state WHERE parked=1 ORDER BY unit").fetchall()]

    def tripped_breakers(self):
        return [dict(r) for r in self.conn.execute(
            "SELECT * FROM breaker_state WHERE tripped=1 ORDER BY unit").fetchall()]

    # ---- backoff state ---------------------------------------------------
    def get_backoff(self, job):
        row = self.conn.execute(
            "SELECT * FROM backoff_state WHERE job=?", (job,)).fetchone()
        return dict(row) if row else None

    def upsert_backoff(self, job, attempt, base_seconds, cap_seconds,
                       next_at=None, escalated=0):
        self.conn.execute(
            "INSERT INTO backoff_state(job,attempt,base_seconds,cap_seconds,next_at,"
            "last_at,escalated) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(job) DO UPDATE SET attempt=excluded.attempt,"
            "base_seconds=excluded.base_seconds,cap_seconds=excluded.cap_seconds,"
            "next_at=excluded.next_at,last_at=excluded.last_at,"
            "escalated=excluded.escalated",
            (job, int(attempt), int(base_seconds), int(cap_seconds), next_at,
             now_utc(), int(escalated)))
        self.conn.commit()
        return self.get_backoff(job)

    # ---- offsets ---------------------------------------------------------
    def get_offset(self, name) -> int:
        row = self.conn.execute("SELECT offset FROM offsets WHERE name=?", (name,)).fetchone()
        return int(row["offset"]) if row else 0

    def set_offset(self, name, offset):
        self.conn.execute(
            "INSERT INTO offsets(name,offset,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(name) DO UPDATE SET offset=excluded.offset,"
            "updated_at=excluded.updated_at", (name, int(offset), now_utc()))
        self.conn.commit()

    # ---- digests (dedup) -------------------------------------------------
    def record_digest(self, kind, dedup_key, payload=None) -> int:
        cur = self.conn.execute(
            "INSERT INTO digests(kind,dedup_key,sent_ts,payload) VALUES(?,?,?,?)",
            (kind, dedup_key, now_utc(), payload))
        self.conn.commit()
        return cur.lastrowid

    def recent_digest(self, dedup_key, window_hours):
        cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        for r in self.conn.execute(
                "SELECT * FROM digests WHERE dedup_key=? ORDER BY digest_id DESC",
                (dedup_key,)).fetchall():
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
                "SELECT COUNT(*) AS n FROM digests WHERE sent_ts >= ?",
                (since_iso,)).fetchone()
        return int(row["n"])


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _emit(obj):
    sys.stdout.write(json.dumps(obj, sort_keys=True) + "\n")


def _cli(argv=None):
    ap = argparse.ArgumentParser(
        prog="loop_ledger.py",
        description="The sole state writer for the Loop Protection System.")
    ap.add_argument("--state-dir", help="override the state dir (default $LOOP_STATE_DIR)")
    ap.add_argument("--self-test", action="store_true", help="run the self-test and exit")
    sub = ap.add_subparsers(dest="cmd", required=False)

    sub.add_parser("init", help="bootstrap the ledger schema and print its status")

    sp = sub.add_parser("record-finding", help="insert a loop finding")
    sp.add_argument("--loop-class", required=True)
    sp.add_argument("--severity", required=True, choices=VALID_SEVERITIES)
    sp.add_argument("--unit")
    sp.add_argument("--evidence-path")
    sp.add_argument("--detail")
    sp.add_argument("--tier", type=int)
    sp.add_argument("--dedup-key")

    sp = sub.add_parser("set-finding-state")
    sp.add_argument("--finding-id", type=int, required=True)
    sp.add_argument("--state", required=True, choices=VALID_FINDING_STATE)

    sub.add_parser("open-findings").add_argument("--loop-class")

    sp = sub.add_parser("arm", help="arm this box (Tier 1 auto-fix leaves DRY_RUN)")
    sp = sub.add_parser("disarm", help="return this box to DRY_RUN observe-only")

    sp = sub.add_parser("get-offset"); sp.add_argument("--name", required=True)
    sp = sub.add_parser("set-offset")
    sp.add_argument("--name", required=True); sp.add_argument("--offset", type=int, required=True)

    sp = sub.add_parser("recent-digest",
                        help="exit 0 if a digest for dedup-key is within the window, else 3")
    sp.add_argument("--dedup-key", required=True)
    sp.add_argument("--window-hours", type=float, default=6.0)

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
        sys.stderr.write("ERROR [loop_ledger]: cannot open ledger: %s\n" % exc)
        return EX_ERR

    try:
        c = args.cmd
        if c == "init":
            _emit({"ok": True, "db": str(led.db_path),
                   "schema_version": led.get_meta("schema_version"),
                   "platform": led.get_meta("platform"), "armed": led.is_armed()})
        elif c == "record-finding":
            fid = led.record_finding(args.loop_class, args.severity, args.unit,
                                     args.evidence_path, args.detail, args.tier,
                                     dedup_key=args.dedup_key)
            _emit({"ok": True, "finding_id": fid})
        elif c == "set-finding-state":
            ok = led.set_finding_state(args.finding_id, args.state)
            _emit({"ok": ok})
            if not ok:
                return EX_FALSE
        elif c == "open-findings":
            _emit({"findings": led.open_findings(args.loop_class)})
        elif c == "arm":
            led.set_meta("armed", "true")
            _emit({"ok": True, "armed": True})
        elif c == "disarm":
            led.set_meta("armed", "false")
            _emit({"ok": True, "armed": False})
        elif c == "get-offset":
            _emit({"name": args.name, "offset": led.get_offset(args.name)})
        elif c == "set-offset":
            led.set_offset(args.name, args.offset)
            _emit({"ok": True, "name": args.name, "offset": args.offset})
        elif c == "recent-digest":
            r = led.recent_digest(args.dedup_key, args.window_hours)
            _emit({"present": r is not None})
            return EX_OK if r is not None else EX_FALSE
        else:
            sys.stderr.write("ERROR: unknown command\n")
            return EX_USAGE
        return EX_OK
    except ValueError as exc:
        sys.stderr.write("ERROR [loop_ledger]: %s\n" % exc)
        return EX_USAGE
    except sqlite3.Error as exc:
        sys.stderr.write("ERROR [loop_ledger]: db error: %s\n" % exc)
        return EX_ERR
    finally:
        led.close()


# --------------------------------------------------------------------------- #
# self-test (deterministic, no network, no model)
# --------------------------------------------------------------------------- #
def self_test():
    import tempfile
    print("[loop_ledger] self-test: schema, findings, fixes, breakers, backoff, offsets, digests")
    with tempfile.TemporaryDirectory() as td:
        sd = Path(td) / "loop-protection"
        led = Ledger(sd)
        assert led.get_meta("schema_version") == SCHEMA_VERSION
        assert led.db_path.is_file()
        assert led.is_armed() is False  # DRY_RUN observe-only is the default
        print("  schema case: PASS (db created, WAL, armed defaults FALSE)")

        fid = led.record_finding("LP-B1", "P1", unit="cc-app",
                                 evidence_path="/x/boot.log", detail="12 restarts/tick", tier=1)
        assert fid > 0
        assert len(led.open_findings()) == 1
        assert len(led.open_findings("LP-B1")) == 1
        assert led.set_finding_state(fid, "parked")
        assert len(led.open_findings()) == 0
        assert not led.set_finding_state(999999, "open")
        print("  findings case: PASS (record/query/state, nonexistent update False)")

        try:
            led.record_finding("LP-A1", "BOGUS")
            raise AssertionError("bad severity accepted")
        except ValueError:
            pass
        print("  validation case: PASS (bad severity refused)")

        led.record_fix(fid, "LF-6", unit="cc-app", what="park unit",
                       verify_outcome="parked", revert_cmd="unpark cc-app", dry_run=False)
        led.record_fix(fid, "LF-6", unit="cc-app", what="retry", dry_run=False)
        assert led.fixes_for_target_since("cc-app", 24) == 2
        assert led.fixes_for_target_since("other", 24) == 0
        print("  fix_actions case: PASS (healer-breaker count works)")

        b = led.upsert_breaker("cc-app", "process", event_count=10, tripped=1, parked=1)
        assert b["tripped"] == 1
        assert len(led.parked_units()) == 1
        assert len(led.tripped_breakers()) == 1
        led.upsert_breaker("cc-app", "process", parked=0, tripped=0)
        assert len(led.parked_units()) == 0
        print("  breaker case: PASS (upsert, park/unpark, tripped listing)")

        led.upsert_backoff("redispatch-x", attempt=1, base_seconds=7200,
                           cap_seconds=86400, next_at=now_utc())
        bo = led.get_backoff("redispatch-x")
        assert bo["attempt"] == 1 and bo["base_seconds"] == 7200
        led.upsert_backoff("redispatch-x", attempt=2, base_seconds=7200, cap_seconds=86400)
        assert led.get_backoff("redispatch-x")["attempt"] == 2
        print("  backoff case: PASS (persisted per job, survives update)")

        assert led.get_offset("gateway.log") == 0
        led.set_offset("gateway.log", 4096)
        assert led.get_offset("gateway.log") == 4096
        print("  offsets case: PASS (absent=0, upsert)")

        assert led.recent_digest("LP-B1|box|unit", 6) is None
        led.record_digest("alert", "LP-B1|box|unit", payload="x")
        assert led.recent_digest("LP-B1|box|unit", 6) is not None
        assert led.recent_digest("LP-B1|box|unit", 0) is None
        print("  digests case: PASS (dedup window honored)")

        led.set_meta("armed", "true")
        led.close()
        led2 = Ledger(sd)
        assert led2.get_offset("gateway.log") == 4096
        assert led2.is_armed() is True
        led2.close()
        print("  durability case: PASS (state survives close/reopen)")

    print("[loop_ledger] self-test: PASS")
    return EX_OK


if __name__ == "__main__":
    sys.exit(_cli())
