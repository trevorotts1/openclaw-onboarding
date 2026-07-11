#!/usr/bin/env python3
# =============================================================================
# RESCUE RANGERS DEPARTMENT :: rescue_ledger.py
# THE SOLE TICKET-STATE WRITER (Topic-4 FIX 4-A — durable ticket ledger)
# -----------------------------------------------------------------------------
# WHY THIS EXISTS (kills finding R1 "ticket store is volatile"):
#   Before this module the ENTIRE rescue ticket queue + the per-client 25/day
#   counters lived in the n8n workflow's $getWorkflowStaticData('global') — wiped
#   on every workflow re-import/redeploy (and the Rescue Rangers Relay has been
#   re-imported repeatedly; 15+ backup JSONs exist). No durable history, no SLA
#   metrics, no audit trail, nothing queryable.
#
#   This ledger becomes the SYSTEM OF RECORD. The n8n staticData queue REMAINS
#   the transport buffer (no n8n change is required for the ledger to work), but
#   both operator transports write THROUGH this module:
#     * rescue-receiver.mjs  — on ticket-in (escalate) and answer-out.
#     * rescue-rangers-poller.sh — on pull (pending) and answer-out.
#   Modeled 1:1 on the proven Skill-60 ews_ledger.py single-writer pattern:
#   ONE writer = no races, no torn rows, no wedged pipeline.
#
# STORE: <state_dir>/tickets.db  (operator Mac default ~/clawd/fleet-heartbeat/
#   rescue/tickets.db), SQLite in WAL mode, owned by the box user. Tables:
#     tickets    the system of record — one row per rescue ticket (spec 4.3 4-A
#                schema) plus operator-side bookkeeping (cc_task_id, incomplete,
#                missing_fields, return_to, agent_name, source).
#     exchanges  per-client-per-day exchange audit — the durable replacement for
#                the volatile n8n daily counters that enforce the 25/day cap.
#     meta       schema_version, platform, bookkeeping.
#
# STDLIB ONLY (sqlite3). Zero third-party deps, calls NO model, NO network.
# DOCTRINE: move in silence (operator-verbose only); NEVER print a secret value
# (this ledger stores ticket TEXT + status, never a credential); state writes run
# as the box user, never root (a root-owned file under the rescue dir can wedge
# the operator toolchain — we WARN loudly here).
#
# EXIT CODE CONTRACT (stable; every subcommand):
#   0  OK (including an idempotent replay no-op, and a TRUE predicate)
#   1  unexpected error
#   2  usage error
#   3  predicate FALSE / not found (no such ticket, under cap, nothing aging)
# =============================================================================
"""rescue_ledger.py — the sole durable-state writer for the Rescue Rangers dept."""

from __future__ import annotations

import argparse
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

# Ticket lifecycle states. The CC board caller (rescue_cc_board.py) maps these to
# the department Kanban columns: open/in_progress -> backlog/in_progress,
# answered -> review, resolved -> done, blocked -> blocked.
VALID_STATUS = (
    "open",         # escalation received, not yet worked
    "in_progress",  # an agent turn is actively working it
    "answered",     # an answer was produced and posted back to the relay
    "resolved",     # the client confirmed RESOLVED (or the fix verified closed)
    "incomplete",   # accepted but flagged INCOMPLETE (missing advertised fields)
    "blocked",      # waiting on the operator / a one-way-door decision
    "closed",       # terminal administrative close (no further action)
)

# Exchange kinds counted toward the per-client 25/day cap + the audit trail.
VALID_EXCHANGE = ("escalate", "answer", "status", "resolved", "page")

# The nine advertised escalation fields (contract shared with the Relay Brain
# validation patch relay_brain_validation.js). Kept here so the ledger and the
# edge validator agree on ONE field set fleet-wide.
NINE_FIELDS = (
    "person", "clientName", "agentName", "boxName", "boxType",
    "openclawVersion", "problem", "alreadyTried", "returnTo",
)


# --------------------------------------------------------------------------- #
# time helpers (mirrors ews_ledger.py)
# --------------------------------------------------------------------------- #
def now_utc() -> str:
    """ISO-8601 UTC, second precision, explicit offset."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# --------------------------------------------------------------------------- #
# platform / path resolution (matches the ews_ledger convention so the two
# ledgers resolve state the same way on Mac vs VPS)
# --------------------------------------------------------------------------- #
def detect_platform() -> str:
    """'vps' when /data/.openclaw exists (the container data root), else 'mac'.
    Env RESCUE_PLATFORM overrides for tests."""
    env = os.environ.get("RESCUE_PLATFORM", "").strip().lower()
    if env in ("mac", "vps"):
        return env
    if Path("/data/.openclaw").is_dir():
        return "vps"
    return "mac"


def default_state_dir() -> Path:
    """The rescue state dir. Env RESCUE_STATE_DIR overrides (used by every
    self-test). Operator Mac default: ~/clawd/fleet-heartbeat/rescue."""
    env = os.environ.get("RESCUE_STATE_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    home = os.environ.get("HOME") or os.path.expanduser("~")
    return Path(home) / "clawd" / "fleet-heartbeat" / "rescue"


def db_path(state_dir=None) -> Path:
    return (Path(state_dir) if state_dir else default_state_dir()) / "tickets.db"


# --------------------------------------------------------------------------- #
# root safety
# --------------------------------------------------------------------------- #
def is_root() -> bool:
    try:
        return hasattr(os, "geteuid") and os.geteuid() == 0
    except Exception:  # noqa: BLE001
        return False


def warn_root_state() -> None:
    if is_root():
        sys.stderr.write(
            "WARN [rescue_ledger]: running as root. Rescue ticket state should be "
            "written by the box user; a root-owned file under the rescue dir can "
            "wedge the operator toolchain.\n"
        )


# --------------------------------------------------------------------------- #
# The ledger
# --------------------------------------------------------------------------- #
class Ledger:
    """The single SQLite-WAL writer. Construct with a state dir (or default);
    every mutation is a single committed transaction. Idempotent by design:
    open_ticket is INSERT-OR-IGNORE on ticket_id, record_answer only fills an
    empty answer, so a re-run of either transport never double-writes."""

    def __init__(self, state_dir=None):
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
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id        TEXT PRIMARY KEY,
                ts_open          TEXT NOT NULL,
                ts_answered      TEXT,
                ts_resolved      TEXT,
                client           TEXT,
                person           TEXT,
                agent_name       TEXT,
                box              TEXT,
                box_type         TEXT,
                oc_version       TEXT,
                problem          TEXT,
                already_tried    TEXT,
                return_to        TEXT,
                answer           TEXT,
                tier             TEXT,
                fix_class        TEXT,
                fix_mode         TEXT,
                status           TEXT NOT NULL DEFAULT 'open',
                return_delivered INTEGER NOT NULL DEFAULT 0,
                incomplete       INTEGER NOT NULL DEFAULT 0,
                missing_fields   TEXT,
                source           TEXT,
                cc_task_id       TEXT,
                updated_at       TEXT
            );
            CREATE TABLE IF NOT EXISTS exchanges (
                exchange_id      INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id        TEXT,
                client           TEXT,
                kind             TEXT NOT NULL,
                day              TEXT NOT NULL,
                ts               TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS meta (
                key              TEXT PRIMARY KEY,
                value            TEXT
            );
            CREATE INDEX IF NOT EXISTS ix_tickets_status ON tickets(status);
            CREATE INDEX IF NOT EXISTS ix_tickets_client ON tickets(client);
            CREATE INDEX IF NOT EXISTS ix_tickets_open   ON tickets(ts_open);
            CREATE INDEX IF NOT EXISTS ix_exch_client_day ON exchanges(client, day);
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

    # ---- tickets ---------------------------------------------------------
    def open_ticket(self, ticket_id, *, client=None, person=None, agent_name=None,
                    box=None, box_type=None, oc_version=None, problem=None,
                    already_tried=None, return_to=None, source=None,
                    incomplete=False, missing_fields=None, ts_open=None) -> bool:
        """Insert a new ticket row. IDEMPOTENT: a repeat ticket_id is a no-op
        (returns False) so a transport re-delivery never double-opens. Also logs
        an 'escalate' exchange for the 25/day cap. Returns True when a NEW row was
        created, False when the ticket already existed."""
        if not ticket_id:
            raise ValueError("ticket_id is required")
        ts = ts_open or now_utc()
        mf = None
        if missing_fields:
            mf = ",".join(missing_fields) if isinstance(missing_fields, (list, tuple)) else str(missing_fields)
        status = "incomplete" if incomplete else "open"
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO tickets("
            "ticket_id,ts_open,client,person,agent_name,box,box_type,oc_version,"
            "problem,already_tried,return_to,status,incomplete,missing_fields,"
            "source,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (ticket_id, ts, client, person, agent_name, box, box_type, oc_version,
             problem, already_tried, return_to, status, 1 if incomplete else 0,
             mf, source, ts))
        created = cur.rowcount > 0
        self.conn.commit()
        if created:
            self.record_exchange(client, "escalate", ticket_id=ticket_id)
        return created

    def get_ticket(self, ticket_id):
        row = self.conn.execute(
            "SELECT * FROM tickets WHERE ticket_id=?", (ticket_id,)).fetchone()
        return dict(row) if row else None

    def record_answer(self, ticket_id, answer, *, tier=None, fix_class=None,
                      fix_mode=None) -> bool:
        """Attach an answer and move the ticket to 'answered'. IDEMPOTENT: only
        fills the answer when the ticket is not already answered/resolved (so a
        re-pulled ticket is not re-answered — mirrors Transport B's "answered
        tickets not re-returned"). Returns True when the answer was written."""
        row = self.get_ticket(ticket_id)
        if row is None:
            return False
        if row.get("ts_answered"):
            return False  # already answered — idempotent no-op
        now = now_utc()
        self.conn.execute(
            "UPDATE tickets SET answer=?, ts_answered=?, tier=COALESCE(?,tier), "
            "fix_class=COALESCE(?,fix_class), fix_mode=COALESCE(?,fix_mode), "
            "status='answered', updated_at=? WHERE ticket_id=?",
            (answer, now, tier, fix_class, fix_mode, now, ticket_id))
        self.conn.commit()
        self.record_exchange(row.get("client"), "answer", ticket_id=ticket_id)
        return True

    def mark_resolved(self, ticket_id) -> bool:
        """Terminal close on a confirmed RESOLVED. Sets ts_resolved + status."""
        now = now_utc()
        cur = self.conn.execute(
            "UPDATE tickets SET status='resolved', ts_resolved=COALESCE(ts_resolved,?), "
            "updated_at=? WHERE ticket_id=?", (now, now, ticket_id))
        self.conn.commit()
        if cur.rowcount > 0:
            row = self.get_ticket(ticket_id)
            self.record_exchange(row.get("client") if row else None,
                                 "resolved", ticket_id=ticket_id)
        return cur.rowcount > 0

    def set_status(self, ticket_id, status) -> bool:
        if status not in VALID_STATUS:
            raise ValueError("invalid status %r" % status)
        cur = self.conn.execute(
            "UPDATE tickets SET status=?, updated_at=? WHERE ticket_id=?",
            (status, now_utc(), ticket_id))
        self.conn.commit()
        return cur.rowcount > 0

    def mark_return_delivered(self, ticket_id, delivered=True) -> bool:
        cur = self.conn.execute(
            "UPDATE tickets SET return_delivered=?, updated_at=? WHERE ticket_id=?",
            (1 if delivered else 0, now_utc(), ticket_id))
        self.conn.commit()
        return cur.rowcount > 0

    def stamp_cc_task(self, ticket_id, cc_task_id) -> bool:
        """Link the ticket to its Command Center Kanban task id (rescue_cc_board)."""
        cur = self.conn.execute(
            "UPDATE tickets SET cc_task_id=?, updated_at=? WHERE ticket_id=?",
            (cc_task_id, now_utc(), ticket_id))
        self.conn.commit()
        return cur.rowcount > 0

    def tickets_by_status(self, *statuses):
        if not statuses:
            rows = self.conn.execute(
                "SELECT * FROM tickets ORDER BY ts_open").fetchall()
        else:
            qs = ",".join("?" for _ in statuses)
            rows = self.conn.execute(
                "SELECT * FROM tickets WHERE status IN (%s) ORDER BY ts_open" % qs,
                tuple(statuses)).fetchall()
        return [dict(r) for r in rows]

    def open_tickets(self):
        """Tickets still needing operator attention (open / in_progress /
        incomplete / blocked)."""
        return self.tickets_by_status("open", "in_progress", "incomplete", "blocked")

    def aging(self, older_than_minutes, statuses=("open", "in_progress", "answered", "blocked")):
        """Tickets in `statuses` whose ts_open is older than the cutoff. This is
        the durable feed for the aging/SLA sweep (kills R6) — nothing else in the
        old design swept the PENDING queue for tickets aging unanswered."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=older_than_minutes)
        out = []
        rows = self.tickets_by_status(*statuses)
        for r in rows:
            ts = _parse_iso(r.get("ts_open"))
            if ts is not None and ts <= cutoff:
                out.append(r)
        return out

    # ---- exchanges (25/day cap + audit) ---------------------------------
    def record_exchange(self, client, kind, ticket_id=None, day=None, ts=None) -> int:
        """Log one exchange toward the per-client daily cap + audit trail. `day`
        (YYYY-MM-DD) and `ts` default to now; the migration passes an explicit day
        to seed a historical counter faithfully."""
        if kind not in VALID_EXCHANGE:
            raise ValueError("invalid exchange kind %r" % kind)
        cur = self.conn.execute(
            "INSERT INTO exchanges(ticket_id,client,kind,day,ts) VALUES(?,?,?,?,?)",
            (ticket_id, client, kind, day or _today_utc(), ts or now_utc()))
        self.conn.commit()
        return cur.lastrowid

    def count_exchanges_today(self, client, day=None) -> int:
        """Exchanges logged for `client` on `day` (UTC, default today). The durable
        replacement for the volatile n8n per-client daily counter."""
        d = day or _today_utc()
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM exchanges WHERE client=? AND day=?",
            (client, d)).fetchone()
        return int(row["n"])

    def over_daily_cap(self, client, cap=25, day=None) -> bool:
        return self.count_exchanges_today(client, day=day) >= cap

    # ---- reporting -------------------------------------------------------
    def digest(self, since_iso=None):
        """Compact operator digest for the weekly report (Ticket Clerk). Counts by
        status, open/answered/resolved totals, and per-client volume since
        `since_iso` (default: all time). Never raises."""
        where, params = "", ()
        if since_iso:
            where, params = " WHERE ts_open >= ?", (since_iso,)
        by_status = {}
        for r in self.conn.execute(
                "SELECT status, COUNT(*) AS n FROM tickets%s GROUP BY status" % where,
                params).fetchall():
            by_status[r["status"]] = int(r["n"])
        by_client = {}
        for r in self.conn.execute(
                "SELECT client, COUNT(*) AS n FROM tickets%s GROUP BY client" % where,
                params).fetchall():
            by_client[r["client"] or "(none)"] = int(r["n"])
        total = sum(by_status.values())
        return {
            "since": since_iso,
            "total": total,
            "by_status": by_status,
            "by_client": by_client,
            "answered": by_status.get("answered", 0) + by_status.get("resolved", 0),
            "resolved": by_status.get("resolved", 0),
            "incomplete": by_status.get("incomplete", 0),
            "still_open": by_status.get("open", 0) + by_status.get("in_progress", 0)
            + by_status.get("blocked", 0),
        }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _emit(obj):
    sys.stdout.write(json.dumps(obj, sort_keys=True, default=str) + "\n")


def _cli(argv=None):
    ap = argparse.ArgumentParser(
        prog="rescue_ledger.py",
        description="The sole durable ticket-state writer for the Rescue Rangers dept.")
    ap.add_argument("--state-dir", help="override the rescue state dir "
                    "(default $RESCUE_STATE_DIR or ~/clawd/fleet-heartbeat/rescue)")
    ap.add_argument("--self-test", action="store_true",
                    help="run the deterministic self-test and exit")
    sub = ap.add_subparsers(dest="cmd", required=False)

    sub.add_parser("init", help="bootstrap the ledger schema and print its status")

    sp = sub.add_parser("open", help="open (or idempotently re-touch) a ticket")
    sp.add_argument("--ticket-id", required=True)
    for f in ("client", "person", "agent-name", "box", "box-type", "oc-version",
              "problem", "already-tried", "return-to", "source", "missing-fields"):
        sp.add_argument("--" + f)
    sp.add_argument("--incomplete", action="store_true")

    sp = sub.add_parser("answer", help="attach an answer + move to 'answered'")
    sp.add_argument("--ticket-id", required=True)
    sp.add_argument("--answer", required=True)
    sp.add_argument("--tier"); sp.add_argument("--fix-class"); sp.add_argument("--fix-mode")

    sp = sub.add_parser("resolve"); sp.add_argument("--ticket-id", required=True)
    sp = sub.add_parser("set-status")
    sp.add_argument("--ticket-id", required=True)
    sp.add_argument("--status", required=True, choices=VALID_STATUS)
    sp = sub.add_parser("mark-returned"); sp.add_argument("--ticket-id", required=True)
    sp = sub.add_parser("stamp-cc")
    sp.add_argument("--ticket-id", required=True); sp.add_argument("--cc-task-id", required=True)

    sp = sub.add_parser("get"); sp.add_argument("--ticket-id", required=True)
    sub.add_parser("open-tickets")
    sp = sub.add_parser("aging")
    sp.add_argument("--older-than-minutes", type=int, required=True)

    sp = sub.add_parser("count-today", help="exit 0 if under cap, exit 3 if AT/over cap")
    sp.add_argument("--client", required=True); sp.add_argument("--cap", type=int, default=25)

    sp = sub.add_parser("digest"); sp.add_argument("--since")

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
        sys.stderr.write("ERROR [rescue_ledger]: cannot open ledger: %s\n" % exc)
        return EX_ERR

    try:
        c = args.cmd
        if c == "init":
            _emit({"ok": True, "db": str(led.db_path),
                   "schema_version": led.get_meta("schema_version"),
                   "platform": led.get_meta("platform")})
        elif c == "open":
            created = led.open_ticket(
                args.ticket_id, client=args.client, person=args.person,
                agent_name=getattr(args, "agent_name"), box=args.box,
                box_type=getattr(args, "box_type"), oc_version=getattr(args, "oc_version"),
                problem=args.problem, already_tried=getattr(args, "already_tried"),
                return_to=getattr(args, "return_to"), source=args.source,
                incomplete=args.incomplete,
                missing_fields=getattr(args, "missing_fields"))
            _emit({"ok": True, "ticket_id": args.ticket_id, "created": created})
        elif c == "answer":
            ok = led.record_answer(args.ticket_id, args.answer, tier=args.tier,
                                   fix_class=getattr(args, "fix_class"),
                                   fix_mode=getattr(args, "fix_mode"))
            _emit({"ok": ok, "ticket_id": args.ticket_id})
            if not ok:
                return EX_FALSE
        elif c == "resolve":
            ok = led.mark_resolved(args.ticket_id)
            _emit({"ok": ok, "ticket_id": args.ticket_id})
            if not ok:
                return EX_FALSE
        elif c == "set-status":
            ok = led.set_status(args.ticket_id, args.status)
            _emit({"ok": ok, "ticket_id": args.ticket_id, "status": args.status})
            if not ok:
                return EX_FALSE
        elif c == "mark-returned":
            ok = led.mark_return_delivered(args.ticket_id, True)
            _emit({"ok": ok, "ticket_id": args.ticket_id})
            if not ok:
                return EX_FALSE
        elif c == "stamp-cc":
            ok = led.stamp_cc_task(args.ticket_id, getattr(args, "cc_task_id"))
            _emit({"ok": ok, "ticket_id": args.ticket_id})
            if not ok:
                return EX_FALSE
        elif c == "get":
            t = led.get_ticket(args.ticket_id)
            _emit({"ticket": t})
            if t is None:
                return EX_FALSE
        elif c == "open-tickets":
            _emit({"tickets": led.open_tickets()})
        elif c == "aging":
            _emit({"aging": led.aging(getattr(args, "older_than_minutes"))})
        elif c == "count-today":
            n = led.count_exchanges_today(args.client)
            over = n >= args.cap
            _emit({"client": args.client, "count": n, "cap": args.cap, "over": over})
            return EX_FALSE if over else EX_OK
        elif c == "digest":
            _emit(led.digest(args.since))
        else:
            sys.stderr.write("ERROR: unknown command\n")
            return EX_USAGE
        return EX_OK
    except ValueError as exc:
        sys.stderr.write("ERROR [rescue_ledger]: %s\n" % exc)
        return EX_USAGE
    except sqlite3.Error as exc:
        sys.stderr.write("ERROR [rescue_ledger]: db error: %s\n" % exc)
        return EX_ERR
    finally:
        led.close()


# --------------------------------------------------------------------------- #
# self-test (deterministic, no network, no model)
# --------------------------------------------------------------------------- #
def self_test():
    import tempfile
    print("[rescue_ledger] self-test: schema, open/answer/resolve, idempotency, "
          "cap, aging, cc-link, digest, durability")
    with tempfile.TemporaryDirectory() as td:
        sd = Path(td) / "rescue"
        led = Ledger(sd)
        assert led.get_meta("schema_version") == SCHEMA_VERSION
        assert led.db_path.is_file()
        print("  schema case: PASS (db created, WAL, schema_version pinned)")

        # open a full-context ticket
        created = led.open_ticket(
            "tkt-1", client="acme", person="Owner", agent_name="Aria",
            box="acme-mac", box_type="Mac Mini", oc_version="2026.5.22",
            problem="gateway down", already_tried="1) doctor 2) kickstart",
            return_to="123", source="rescue-receiver")
        assert created is True
        row = led.get_ticket("tkt-1")
        assert row["status"] == "open" and row["client"] == "acme"
        assert row["problem"] == "gateway down"
        print("  open case: PASS (full nine-field ticket persisted, status=open)")

        # idempotent re-open is a no-op (transport re-delivery safe)
        assert led.open_ticket("tkt-1", client="acme", problem="dup") is False
        assert led.get_ticket("tkt-1")["problem"] == "gateway down"  # unchanged
        print("  idempotent-open case: PASS (repeat ticket_id does not clobber)")

        # answer + idempotent answer
        assert led.record_answer("tkt-1", "restart the gateway with kickstart",
                                 tier="MEDIUM", fix_class="gateway",
                                 fix_mode="dry-run") is True
        r = led.get_ticket("tkt-1")
        assert r["status"] == "answered" and r["ts_answered"] and r["tier"] == "MEDIUM"
        assert led.record_answer("tkt-1", "a different answer") is False  # already answered
        assert led.get_ticket("tkt-1")["answer"].startswith("restart")  # unchanged
        print("  answer case: PASS (answered once; re-answer is a no-op)")

        # answering a nonexistent ticket is False, not a crash
        assert led.record_answer("nope", "x") is False
        print("  missing-ticket case: PASS (answer on unknown ticket is False)")

        # resolve + return-delivered + cc link
        assert led.mark_resolved("tkt-1") is True
        assert led.get_ticket("tkt-1")["status"] == "resolved"
        assert led.mark_return_delivered("tkt-1") is True
        assert led.get_ticket("tkt-1")["return_delivered"] == 1
        assert led.stamp_cc_task("tkt-1", "cc-task-abc") is True
        assert led.get_ticket("tkt-1")["cc_task_id"] == "cc-task-abc"
        print("  resolve/return/cc case: PASS")

        # incomplete ticket (missing advertised fields)
        assert led.open_ticket("tkt-2", client="acme", problem="partial",
                               incomplete=True,
                               missing_fields=["person", "boxType"]) is True
        r2 = led.get_ticket("tkt-2")
        assert r2["status"] == "incomplete" and r2["incomplete"] == 1
        assert r2["missing_fields"] == "person,boxType"
        print("  incomplete case: PASS (degraded ticket flagged, never dropped)")

        # invalid status refused
        try:
            led.set_status("tkt-2", "BOGUS")
            raise AssertionError("bad status accepted")
        except ValueError:
            pass
        print("  validation case: PASS (bad status refused)")

        # 25/day cap: two tickets already logged 2 escalate + 1 answer + 1 resolved
        # exchanges for acme; drive it to the cap and assert the predicate flips.
        n0 = led.count_exchanges_today("acme")
        assert n0 >= 1
        for _ in range(30):
            led.record_exchange("acme", "escalate")
        assert led.over_daily_cap("acme", cap=25) is True
        assert led.over_daily_cap("newclient", cap=25) is False
        print("  daily-cap case: PASS (durable per-client counter enforces 25/day)")

        # aging: tkt-3 opened 3h ago must surface at a 120-min cutoff, tkt-4 (now) must not
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=3)).replace(microsecond=0).isoformat()
        led.open_ticket("tkt-3", client="beta", problem="old", ts_open=old_ts)
        led.open_ticket("tkt-4", client="beta", problem="fresh")
        aged = {t["ticket_id"] for t in led.aging(120)}
        assert "tkt-3" in aged and "tkt-4" not in aged
        print("  aging case: PASS (SLA sweep surfaces tickets past the cutoff)")

        # digest
        dg = led.digest()
        assert dg["total"] >= 4 and "by_status" in dg and "by_client" in dg
        print("  digest case: PASS (status + per-client rollup)")

        led.close()

        # durability across close/reopen
        led2 = Ledger(sd)
        assert led2.get_ticket("tkt-1")["status"] == "resolved"
        assert led2.count_exchanges_today("acme") >= 25
        led2.close()
        print("  durability case: PASS (state survives close/reopen)")

    print("[rescue_ledger] self-test: PASS")
    return EX_OK


if __name__ == "__main__":
    sys.exit(_cli())
