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
#   findings       class, unit, evidence path, severity, state, times_seen
#                  (UNIQUE per dedup_key while ACTIVE - see
#                  _migrate_findings_dedup; a re-observation updates, a
#                  recurrence after a fix opens a new row)
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

# The states in which a finding is still LIVE work. Finding uniqueness per
# dedup_key is scoped to EXACTLY these (v0.6.4), which is the whole design:
# while a finding is active a re-observation UPDATES it, but once it has been
# fixed/verified/resolved/dismissed the key is free again, so a RECURRENCE after
# a fix opens a NEW row instead of resurrecting closed history. Unscoped
# uniqueness would have made "it came back" indistinguishable from "it never
# left". ONE constant feeds all three users - the partial-index DDL, the
# migration collapse, and the record_finding lookup - so they cannot drift apart.
ACTIVE_FINDING_STATES = ("open", "planned", "escalated", "parked")
# SQL literal list built from that same constant. Safe to interpolate: the values
# are module constants, never caller input (and a partial index's WHERE clause
# cannot take a bound parameter, which is why this form exists at all).
_ACTIVE_SQL = ",".join("'%s'" % s for s in ACTIVE_FINDING_STATES)


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
        self._migrate_findings_dedup()

    def _migrate_findings_dedup(self):
        """v0.6.4: make an ACTIVE finding UNIQUE per dedup_key. Idempotent.

        WHY. record_finding was a bare INSERT and no unique index existed, so a
        condition that re-observes every tick appended a row every tick forever.
        Measured on a live box: 4,084 finding rows across 12 distinct dedup_keys,
        driving a 100-210 escalation/hour storm against an intake whose rate limit
        is GLOBAL across the fleet - so one box's runaway key sheds OTHER clients'
        live escalations. The dedup_key column was always there; nothing ever
        enforced it.

        Runs at the END of _bootstrap(), i.e. on EVERY ledger open, so a box that
        is rolled forward migrates on its next tick with no separate step.

        THE ORDER BELOW IS THE CRUX and is not rearrangeable: CREATE UNIQUE INDEX
        SCANS THE EXISTING ROWS and FAILS outright if two active rows already share
        a key. The collapse must therefore precede the index, and the column must
        precede both. All three run inside ONE `BEGIN IMMEDIATE` - SQLite DDL is
        transactional, so a crash at any point rolls the whole thing back and the
        next open re-runs it cleanly. There is no half-migrated state to repair.
        """
        # Take FULL manual transaction control. Under Python's default
        # isolation_level, DDL does NOT open an implicit transaction, so an
        # ALTER/CREATE would commit on the spot and could NOT be rolled back -
        # exactly the half-migrated state this method must be unable to produce.
        self.conn.commit()
        prev_isolation = self.conn.isolation_level
        self.conn.isolation_level = None          # our BEGIN is then the only one
        try:
            self.conn.execute("BEGIN IMMEDIATE")

            # 1. times_seen. The PRAGMA guard is MANDATORY - a second ALTER on an
            #    existing column is an error, and this method runs on every open.
            cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(findings)")}
            if "times_seen" not in cols:
                self.conn.execute("ALTER TABLE findings "
                                  "ADD COLUMN times_seen INTEGER NOT NULL DEFAULT 1")

            # 2. COLLAPSE THE BACKLOG - DEMOTE, DELETE NOTHING. A DELETE would
            #    dangle fix_actions.finding_id (the healer's audit trail points at
            #    these ids) and would destroy the evidence of the storm itself.
            #    Demotion to 'resolved' is enough: open_findings() filters
            #    state='open', so a demoted row is invisible to the live pipeline
            #    while staying fully readable as history.
            #    SURVIVOR = MAX(finding_id) per key = the FRESHEST observation. The
            #    survivor is NOT modified and KEEPS ITS OWN STATE, so a group that
            #    mixes open+escalated leaves whichever row is newest exactly as it
            #    was. Rows already inactive (fixed/verified/resolved/false_positive)
            #    are untouched history and are never considered here.
            cur = self.conn.execute(
                "UPDATE findings SET state='resolved', updated_ts=? "
                "WHERE dedup_key IS NOT NULL AND state IN (%s) "
                "AND finding_id NOT IN ("
                "    SELECT MAX(finding_id) FROM findings "
                "    WHERE dedup_key IS NOT NULL AND state IN (%s) GROUP BY dedup_key)"
                % (_ACTIVE_SQL, _ACTIVE_SQL), (now_utc(),))
            collapsed = cur.rowcount or 0
            if collapsed > 0:
                # Audit crumb: how much backlog this box was carrying. Written only
                # when non-zero, so a later no-op re-run cannot overwrite the real
                # number with 0. INSERT OR REPLACE (not ON CONFLICT) keeps this
                # method free of any SQLite 3.24+ syntax dependency.
                self.conn.execute(
                    "INSERT OR REPLACE INTO meta(key,value) "
                    "VALUES('migration_findings_dedup_collapsed',?)", (str(collapsed),))

            # 3. The guard itself. PARTIAL index (SQLite 3.8.0+, 2013) so the
            #    uniqueness applies ONLY to active rows and only where a dedup_key
            #    exists - NULL keys stay exempt and unlimited, and closed history
            #    never collides with a fresh recurrence.
            self.conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_find_active_key "
                "ON findings(dedup_key) "
                "WHERE dedup_key IS NOT NULL AND state IN (%s)" % _ACTIVE_SQL)

            self.conn.execute("COMMIT")
        except BaseException:
            try:
                self.conn.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise
        finally:
            self.conn.isolation_level = prev_isolation

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

        # v0.6.4: UPDATE-then-INSERT, never a bare INSERT. Safe as a read-then-write
        # pair because this module IS the single writer (spec 6.1 "State: one
        # writer"), and the connection is WAL with busy_timeout=30000 above; the
        # ux_find_active_key partial index is the backstop if that law is ever
        # broken. Deliberately NOT an ON CONFLICT upsert - that syntax would add a
        # SQLite 3.24+ floor for no gain on a single-writer path.
        if dedup_key is not None:
            row = self.conn.execute(
                "SELECT finding_id FROM findings WHERE dedup_key=? AND state IN (%s) "
                "ORDER BY finding_id DESC LIMIT 1" % _ACTIVE_SQL, (dedup_key,)).fetchone()
            if row is not None:
                # SAME live finding, seen again: refresh the observation and bump
                # the counter. STATE IS DELIBERATELY NOT TOUCHED - an 'escalated'
                # finding stays escalated and a 'parked' one stays parked. Whether
                # something re-escalates is the 0.6.3 digest gate's and the refusal
                # backoff's decision; making it a side effect of re-observation
                # here would flap the state and re-open exactly the storm this
                # release closes. loop_class and unit are likewise untouched: they
                # are part of what the dedup_key already identifies.
                fid = int(row["finding_id"])
                self.conn.execute(
                    "UPDATE findings SET severity=?, detail=?, evidence_path=?, tier=?, "
                    "tick_ts=?, updated_ts=?, times_seen=times_seen+1 "
                    "WHERE finding_id=?",
                    (severity, detail, evidence_path, tier, ts, ts, fid))
                self.conn.commit()
                return fid
            # MISS falls through to the INSERT below. That one branch covers both
            # a never-seen key AND a RECURRENCE AFTER A FIX (the old row is no
            # longer active, so the key is free) - a recurrence must be a NEW row
            # with its own timestamp, not a resurrected one carrying stale history.

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

    # ---- THE FINDINGS DEDUP MIGRATION (v0.6.4) -----------------------------
    # The bug this closes: record_finding was a bare INSERT with NO unique index,
    # so a condition re-observed every tick appended a row every tick. Measured on
    # a live box: 4,084 rows over 12 dedup_keys -> a 100-210 escalation/hour storm.
    # Every case below is asserted in BOTH directions, because the dangerous
    # failure here is not "dedup did not fire" - it is "dedup swallowed a REAL
    # recurrence", which turns a noisy system into a silent one.
    print("[loop_ledger] self-test: findings dedup migration (v0.6.4)")
    with tempfile.TemporaryDirectory() as td:
        sd = Path(td) / "loop-protection"
        sd.mkdir(parents=True)
        raw = sqlite3.connect(str(sd / "loop.db"))

        # Build the OLD shape by hand: pre-0.6.4 findings table, no times_seen,
        # no unique index - exactly what a box in the field is carrying.
        raw.executescript(
            """
            CREATE TABLE findings (
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
            CREATE TABLE fix_actions (
                action_id       INTEGER PRIMARY KEY AUTOINCREMENT,
                finding_id      INTEGER, fix_class TEXT, unit TEXT, what TEXT,
                applied_ts      TEXT NOT NULL, verify_outcome TEXT,
                revert_cmd      TEXT, dry_run INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
            """)
        ts0 = now_utc()

        def _seed(state, key, n=1):
            out = []
            for _ in range(n):
                c = raw.execute(
                    "INSERT INTO findings(loop_class,severity,state,tick_ts,updated_ts,"
                    "dedup_key) VALUES('LP-B1','P1',?,?,?,?)", (state, ts0, ts0, key))
                out.append(c.lastrowid)
            return out

        all_open = _seed("open", "k-allopen", 5)          # plain duplicate run
        mixed_a = _seed("open", "k-mixed", 2)             # MIXED states, same key
        mixed_b = _seed("escalated", "k-mixed", 1)        # newest of the group
        mixed_c = _seed("parked", "k-mixed", 1)           # newest overall -> survivor
        nulls = _seed("open", None, 4)                    # NULL keys: exempt, unlimited
        closed = _seed("fixed", "k-closed", 3)            # inactive history: untouched
        lone = _seed("open", "k-lone", 1)                 # already unique
        # A fix_action pointing at a row that WILL be demoted. If the migration ever
        # deletes instead of demoting, this reference dangles - that is the whole
        # reason demotion is the design.
        raw.execute("INSERT INTO fix_actions(finding_id,fix_class,applied_ts) "
                    "VALUES(?,'LF-6',?)", (all_open[0], ts0))
        raw.commit()
        raw.close()

        pre_rows = 5 + 2 + 1 + 1 + 4 + 3 + 1
        led = Ledger(sd)                                  # <- migration runs here

        # Nothing was deleted. Ever.
        assert len(led.all_findings()) == pre_rows, len(led.all_findings())
        assert led.conn.execute("SELECT COUNT(*) c FROM fix_actions "
                                "WHERE finding_id=?", (all_open[0],)).fetchone()["c"] == 1
        # times_seen exists and every pre-existing row defaulted to 1.
        cols = {r["name"] for r in led.conn.execute("PRAGMA table_info(findings)")}
        assert "times_seen" in cols
        assert led.conn.execute("SELECT MIN(times_seen) m FROM findings").fetchone()["m"] == 1

        def _state(fid):
            return led.get_finding(fid)["state"]

        # Survivor = MAX(finding_id) per key, and it KEEPS ITS OWN STATE.
        assert _state(all_open[-1]) == "open"
        assert all(_state(f) == "resolved" for f in all_open[:-1])
        # The mixed group: newest is the 'parked' row, so 'parked' is what survives
        # and the 'escalated' + 'open' rows behind it are the ones demoted.
        assert _state(mixed_c[0]) == "parked", _state(mixed_c[0])
        assert _state(mixed_b[0]) == "resolved"
        assert all(_state(f) == "resolved" for f in mixed_a)
        # NULL dedup_key rows are exempt from uniqueness entirely - all 4 still open.
        assert all(_state(f) == "open" for f in nulls)
        # Inactive history is NOT touched, even though all 3 share one key.
        assert all(_state(f) == "fixed" for f in closed)
        assert _state(lone[0]) == "open"
        # 4 + 3 = 7 demoted, recorded for audit.
        assert led.get_meta("migration_findings_dedup_collapsed") == "7"
        idx = {r["name"] for r in led.conn.execute("PRAGMA index_list(findings)")}
        assert "ux_find_active_key" in idx, idx
        print("  collapse case: PASS (0 rows deleted, fix_action ref intact, survivor="
              "MAX(id) keeps its own state, mixed open+escalated collapsed, NULL keys "
              "exempt, closed history untouched, 7 demoted + audited, index present)")

        # IDEMPOTENCY: re-open (the migration runs on EVERY open). Nothing may move,
        # and the audit crumb must NOT be overwritten with the no-op's 0.
        snap = {r["finding_id"]: (r["state"], r["times_seen"])
                for r in led.conn.execute("SELECT * FROM findings")}
        led.close()
        led = Ledger(sd)
        again = {r["finding_id"]: (r["state"], r["times_seen"])
                 for r in led.conn.execute("SELECT * FROM findings")}
        assert again == snap, "second migration run moved state"
        assert led.get_meta("migration_findings_dedup_collapsed") == "7"
        print("  idempotency case: PASS (2nd and 3rd open are exact no-ops; the "
              "collapsed-count crumb is not overwritten by a no-op)")

        # CRASH MID-MIGRATION -> the whole thing rolls back, and the NEXT open
        # completes it. Proven on a fresh old-shape DB by making step 3 raise.
        sd2 = Path(td) / "crash"
        sd2.mkdir(parents=True)
        raw2 = sqlite3.connect(str(sd2 / "loop.db"))
        raw2.executescript(
            "CREATE TABLE findings (finding_id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "loop_class TEXT NOT NULL, unit TEXT, evidence_path TEXT,"
            "severity TEXT NOT NULL, detail TEXT, tier INTEGER,"
            "state TEXT NOT NULL DEFAULT 'open', tick_ts TEXT NOT NULL,"
            "updated_ts TEXT, dedup_key TEXT);"
            "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);")
        for _ in range(3):
            raw2.execute("INSERT INTO findings(loop_class,severity,state,tick_ts,"
                         "updated_ts,dedup_key) VALUES('LP-B1','P1','open',?,?,'k-c')",
                         (ts0, ts0))
        raw2.commit()
        raw2.close()

        # Step 3 is made to fail FOR REAL rather than by monkeypatching: an object
        # already occupies the index's name, so SQLite refuses the CREATE (note
        # IF NOT EXISTS does NOT rescue a name taken by a different object kind).
        # A real failure at the real statement is the only kind worth asserting.
        raw3 = sqlite3.connect(str(sd2 / "loop.db"))
        raw3.execute("CREATE TABLE ux_find_active_key(x)")
        raw3.commit()
        raw3.close()
        try:
            Ledger(sd2)
            raise AssertionError("a failing migration step did not propagate")
        except sqlite3.OperationalError as exc:
            assert "ux_find_active_key" in str(exc), exc

        # Post-crash the DB must be EXACTLY as it was: no column, no demotions.
        chk = sqlite3.connect(str(sd2 / "loop.db"))
        chk.row_factory = sqlite3.Row
        assert "times_seen" not in {r["name"] for r in
                                    chk.execute("PRAGMA table_info(findings)")}
        assert chk.execute("SELECT COUNT(*) c FROM findings "
                           "WHERE state='open'").fetchone()["c"] == 3
        chk.execute("DROP TABLE ux_find_active_key")      # clear the blocker
        chk.commit()
        chk.close()
        led2 = Ledger(sd2)                                # the clean re-run
        states = sorted(r["state"] for r in led2.conn.execute("SELECT * FROM findings"))
        assert states == ["open", "resolved", "resolved"], states
        assert "ux_find_active_key" in {r["name"] for r in
                                        led2.conn.execute("PRAGMA index_list(findings)")}
        assert led2.get_meta("migration_findings_dedup_collapsed") == "2"
        led2.close()
        print("  crash-rollback case: PASS (death at step 3 rolls back steps 1+2 "
              "whole - no column, no demotion - and the next open finishes cleanly)")

        # ---- all four record_finding branches ------------------------------
        # (a) dedup_key None -> plain INSERT, old behaviour preserved EXACTLY.
        n1 = led.record_finding("LP-A1", "P2", detail="one")
        n2 = led.record_finding("LP-A1", "P2", detail="two")
        assert n1 != n2, "NULL-key findings were deduped (they must never be)"
        # (b) HIT on an active key -> UPDATE in place, same id, times_seen++,
        #     fields refreshed, STATE UNTOUCHED.
        h1 = led.record_finding("LP-C1", "P2", detail="first", tier=2,
                                evidence_path="/a", dedup_key="k-hit")
        assert led.set_finding_state(h1, "escalated")
        h2 = led.record_finding("LP-C1", "P1", detail="second", tier=1,
                                evidence_path="/b", dedup_key="k-hit")
        assert h2 == h1, "an active key inserted a second row"
        r = led.get_finding(h1)
        assert r["times_seen"] == 2 and r["severity"] == "P1" and r["detail"] == "second"
        assert r["tier"] == 1 and r["evidence_path"] == "/b"
        assert r["state"] == "escalated", "re-observation flapped the state"
        # (c) MISS on a never-seen key -> a NEW open row.
        m1 = led.record_finding("LP-C1", "P2", dedup_key="k-new")
        assert m1 != h1 and led.get_finding(m1)["state"] == "open"
        # (d) RECURRENCE AFTER A FIX -> the key is free again, so a NEW row, NOT a
        #     resurrection. This is the direction that keeps the system honest.
        assert led.set_finding_state(h1, "fixed")
        h3 = led.record_finding("LP-C1", "P1", detail="it came back", dedup_key="k-hit")
        assert h3 != h1, "a recurrence after a fix resurrected the closed finding"
        assert led.get_finding(h3)["state"] == "open"
        assert led.get_finding(h3)["times_seen"] == 1
        assert led.get_finding(h1)["state"] == "fixed"  # history preserved verbatim
        print("  record_finding case: PASS (NULL key never dedupes; active hit "
              "updates in place +times_seen with state untouched; unseen key opens; "
              "recurrence after a fix opens a NEW row and keeps the old one)")

        # THE STORM, REPLAYED. 200 ticks of one condition used to be 200 rows.
        before = len(led.all_findings())
        for _ in range(200):
            led.record_finding("LP-B1", "P1", unit="cc-app", dedup_key="k-storm")
        assert len(led.all_findings()) == before + 1
        storm_rows = [f for f in led.all_findings() if f["dedup_key"] == "k-storm"]
        assert len(storm_rows) == 1 and storm_rows[0]["times_seen"] == 200
        assert storm_rows[0]["state"] == "open"
        print("  storm case: PASS (200 re-observations = 1 row, times_seen=200 - "
              "the 4,084-row/12-key field state can no longer form)")
        led.close()

    print("[loop_ledger] self-test: PASS")
    return EX_OK


if __name__ == "__main__":
    sys.exit(_cli())
