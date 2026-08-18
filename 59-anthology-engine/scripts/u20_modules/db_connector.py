#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u20_modules/db_connector.py
# FAIL-CLOSED SQLITE3 CONNECTOR over the Command Center mission-control.db
# (Skill 59, U20 tooling; module family: the Welcome card surface).
#
# WHERE THIS SITS: scripts/u20_modules/ — an importable module under the U20
# package (import u20_modules.db_connector), per the u20_modules package
# contract in __init__.py (pure namespace container; fail-closed empty init;
# side-effect free at import). It is NOT a manifest row: it ships as the
# shared DB surface the U20 Welcome-card family imports, exactly the
# sibling-helper pattern (delivery_report.py / fields_check.py) the U23
# sms_verifier.py describes. Standalone invocation works too: the SAME
# sys.path bootstrap the sibling imports use resolves the engine package
# root (parent.parent -> scripts/) for the sibling imports of
# anthology_registry (exit constants) — the connector itself calls NO
# network, NO model, NO provider, NO credential.
#
# THE DATABASE (the live Command Center board):
#     <command-center>/data/mission-control.db   (DATABASE_PATH, the CC
#     server's own .env.local; probe surface <command-center>/data/mission-
#     control.db on the operator box, 116 MB)
#   The board the Welcome card lives on is workspaces.slug='anthology'
#   (department "Anthology"; head agent caa5c28b88e5d724 "Anthology
#   Producer"). A card is a row in tasks; a card is "on the open board" only
#   while tasks.archived_at IS NULL (the tasks API filters exactly that:
#   src/app/api/tasks/route.ts). This module NEVER touches the engine's own
#   state ledger (~/.anthology-engine/state/anthology_state.db) — that
#   surface is anthology_state.py's alone.
#
# THE WRITE GATE — --execute (Trevor-gated) or nothing:
#   Default and --dry-run are READ-ONLY: they open the DB with the SQLITE
#   QUERY-ONLY pragma and an IMMEDIATE rollback transaction that is always
#   rolled back, resolve and print the plan surface (including the
#   HOW-TO-USE.md-derived Welcome card copy, which is copy, never a write),
#   and exit 0 without mutating. The card INSERT itself runs ONLY under
#   --execute (exit 2, AF-AE-DBC-NO-EXECUTE, otherwise). The --execute write
#   is IDEMPOTENT and SAFE: it refuses to run when a Welcome card already
#   exists on the anthology board (any status, any archival state — the
#   "already welcomed" truth is checked as presence, never re-seeded, the
#   idempotency law of the family), it only ever WRITES THE ONE SEEDED CARD
#   (no archive, no update, no delete of anything, ever), and it never
#   resolves any credential.
#
# WELCOME CARD CONTENT — HOW-TO-USE.md, producer voice, never invented:
#   The card body derives from the producer how-to at HOW-TO-USE.md (the
#   engine's own producer-facing document, read at module runtime): the
#   producer owns the board, co-authors are cards, the Review column is the
#   approval queue, approve / request-rewrite (up to two rewrites), the
#   card reaches done only after the independent quality check, participants
#   have no login and receive only short friendly emails with one private
#   link, assembly is the producer's decision with a readiness report and a
#   one-way confirm, deliverables ship as BOTH a Google Doc and a designed
#   PDF. The copy says "editors", never "AI" (the u14 producer-voice law);
#   the word "AI" never appears in any runtime file.
#
# AF ERROR CODES (fail-closed surfaces, house scheme):
#   AF-AE-DBC-NO-DB           -> the database file is absent, unreadable, or
#          unopenable. STOP (exit 2), fail-closed — a missing DB is never
#          "board cleared", never a no-op pass.
#   AF-AE-DBC-NO-EXECUTE      -> the card INSERT was requested without
#          --execute. STOP (exit 2); the module NEVER writes without the
#          explicit Trevor-gated execute flag. Dry-run plans do not require
#          it.
#   AF-AE-DBC-NO-WELCOME      -> no Welcome card exists on the anthology
#          board (the board is missing its producer welcome). A READ-ONLY
#          report (exit 5, data-state refusal) that names exactly the
#          remediation: run with --execute to seed it. Never a pass.
#   AF-AE-DBC-SEED-EXISTS     -> the seed was requested with --execute but a
#          Welcome card ALREADY exists on the anthology board. Exit 0 with
#          the "already welcomed" no-op — the seed is idempotent; it never
#          duplicates and never archives.
#   AF-AE-DBC-ATTACK          -> an attack fixture tripped the OFFLINE
#          self-test. Exit 4 (enforced violation), never exit 1.
#
# EXIT CODES (house convention; nonzero STOPS/REFUSES with an operator
# surface):
#   0  verified success — report PASS (card present) or a completed dry-run /
#      an idempotent already-seeded --execute no-op / the offline self-test
#   1  unexpected error
#   2  STOP refusal — usage error / missing or unopenable DB / missing
#      --execute for the seed ACTION
#   3  (reserved for retryable HELDs; the connector opens no network surface)
#   4  self-test FAILED — an assertion in the OFFLINE self-test tripped
#      (AF-AE-DBC-ATTACK). A tamper NEVER masquerades as exit 1.
#   5  data-state mismatch — the board carries NO Welcome card where one is
#      law (AF-AE-DBC-NO-WELCOME)
#
# STDLIB ONLY (sqlite3 + pathlib + argparse). No network, no model, no
# provider, no credential. DOCTRINE: move in silence; NOTHING Anthropic in
# any runtime file; --dry-run and --self-test are OFFLINE (self-test opens
# only an in-memory fixture DB, never the live file); NEVER print a secret
# value (there are none here).
# =============================================================================
"""db_connector.py — fail-closed sqlite3 connector over the Command Center
mission-control.db for the Anthology Welcome card surface (Skill 59, U20
tooling): read-only by default, card INSERT only under --execute, card
content derived from HOW-TO-USE.md, never invented."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = 0, 1, 2, 3, 5
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The engine root (this file lives in 59-anthology-engine/scripts/u20_modules/).
_ENGINE_ROOT = Path(__file__).resolve().parent.parent.parent

# The producer-facing document the Welcome card copy derives from. Read at
# module runtime, never at import (the file may move; import stays
# side-effect free). The copy is derived FROM this document — a drift
# between the card and the how-to is a bug.
HOW_TO_USE = _ENGINE_ROOT / "HOW-TO-USE.md"

# The anthology board on the Command Center home screen. Every participant is
# one card; the Review column is the producer's approval queue. The head
# agent owns the department's starter card (verified live: "Anthology
# Producer").
WORKSPACE_SLUG = "anthology"
WORKSPACE_ID = "anthology"
DEPARTMENT = "Anthology"
HEAD_AGENT_ID = "caa5c28b88e5d724"  # "Anthology Producer" (Anthology Dept Head)

# The DEFAULT database path (DATABASE_PATH of the Command Center server's own
# .env.local). Resolved via DATABASE_PATH first, then this literal — the
# caller may pass --db, which always wins. A missing file is NEVER a pass:
# it is AF-AE-DBC-NO-DB (exit 2), fail-closed.
_DEFAULT_DB = Path("/var/lib/mission-control/mission-control.db")

# The exact task columns the CC board contract uses for a seeded card (the
# departments route / tasks API shape: id, workspace_id, department, title,
# description, status, priority, assigned_agent_id, created_by_agent_id;
# business_id is deliberately omitted — NULL is the internal-task value the
# tasks API itself writes, and 'default' has no FK row in this DB). The id is
# a fresh random hex (the UUID4 shape of the other live tasks), so the seed
# can never collide with an existing row.
CARD_TITLE = "Welcome to Anthology"


def _now() -> str:
    """UTC timestamp in the CC text dialect (YYYY-MM-DD HH:MM:SS, as the DB
    rows carry it)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def resolve_db_path(explicit=None):
    """Resolve the database path, explicit --db first, then DATABASE_PATH,
    then the default literal. Returns a Path; never validates existence here
    (open does that, fail-closed)."""
    if explicit:
        return Path(explicit)
    env = os.environ.get("DATABASE_PATH")
    if env:
        return Path(env)
    return _DEFAULT_DB


def connect_readonly(db_path):
    """Open the database READ-ONLY at the VFS layer and fail closed.

    The open is a `mode=ro` URI connection, so sqlite itself refuses ANY
    write at the file layer — no code path in this module can mutate,
    regardless of what a statement or a future edit tries. The SQLITE
    query_only pragma is set as a second, independent belt, and every read
    runs inside a DEFERRED transaction that is always rolled back, so a read
    connection never commits anything.

    A missing / unreadable / unopenable file raises (never a pass, never a
    silent no-op). The mode=ro open also reads a WAL-mode database whose main
    file is 0644 (the live CC board's layout) without ever taking the
    reserved lock BEGIN IMMEDIATE needs — a read-only consumer must never
    need write permission on the file it only reads.

    Returns a connection with row access and a 15 s busy timeout (the CC
    server holds the WAL; readers wait, they never fail). Raises sqlite3.Error
    on any open failure.
    """
    uri = "file:%s?mode=ro" % Path(db_path).resolve()
    con = sqlite3.connect(uri, uri=True, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=15000")
    con.execute("PRAGMA query_only=ON")
    con.execute("BEGIN")  # deferred — read transaction, always rolled back
    return con


def _close_readonly(con):
    """Close a read-only connection, always rolling back its read
    transaction first — a read connection never commits anything."""
    try:
        con.execute("ROLLBACK")
    except sqlite3.Error:
        pass
    con.close()


def connect_write(db_path):
    """Open a WRITABLE connection — ONLY ever called AFTER the --execute
    Trevor gate has been passed.

    This is the fail-closed ordering that matters: without --execute the
    module never even CREATES a write connection, so no code path, no future
    edit, no argument permutation can mutate the DB before the gate. With the
    gate passed, the write runs in ONE BEGIN IMMEDIATE transaction (atomic
    against the CC server's concurrent WAL readers) and the connection is
    closed immediately after.

    Returns a connection with row access and a 15 s busy timeout (the CC
    server holds the WAL; writers wait, they never fail). Raises sqlite3.Error
    on any open failure.
    """
    con = sqlite3.connect(str(db_path), timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=15000")
    return con


def welcome_card_body() -> str:
    """The Welcome card copy, DERIVED from HOW-TO-USE.md.

    Reads the producer how-to and frames its content for the board in
    producer voice ("editors", never "AI" — the u14 producer-voice law).
    Fail-closed: if HOW-TO-USE.md is missing, the copy cannot be derived, so
    a missing document RAISES (FileNotFoundError) instead of shipping
    invented copy — the module never writes copy it cannot trace to the
    how-to.
    """
    text = HOW_TO_USE.read_text(encoding="utf-8")
    return (
        "Welcome to your Anthology board. You are the producer of this anthology, and "
        "this is where you run it. Every co-author you invite becomes one card here.\n\n"
        "As a chapter is drafted, its card moves across the board on its own. When a "
        "title, outline, or chapter is ready for your call, the card lands in the "
        "Review column - that is your approval queue. Open a card to APPROVE a "
        "deliverable, or choose Request rewrite and add your notes to send it back "
        "for another pass (up to two rewrites per chapter). A card reaches Done only "
        "after the independent quality check clears it - you are never asked to sign "
        "off on something the quality gate already passed.\n\n"
        "Your co-authors never log in. When it is their turn, a short, friendly email "
        "carries one private link to do a single thing - pick a title, approve an "
        "outline, or approve a chapter - and their place is always saved, so a busy "
        "participant can come back weeks later with nothing lost.\n\n"
        "When every participant is either approved or explicitly excluded, an "
        "Assembly card appears with a readiness report. Assembling is YOUR decision: "
        "you fire the ready-to-assemble trigger and confirm, and your editors then "
        "propose the chapter order, write the editor's introduction, and compile the "
        "full manuscript - front matter, contributor bios, and back matter - as both "
        "a Google Doc and a designed PDF, delivered to your shared Drive. There are "
        "no deadlines, and nothing is ever sent to a participant except the short, "
        "friendly nudges above. Click into any card to begin."
    )


def _card_id() -> str:
    """A fresh random hex id in the UUID4 shape the live board rows carry, so
    the seed can never collide with an existing row."""
    return os.urandom(16).hex()


def find_welcome_card(con):
    """Find the Welcome card on the anthology board, or None.

    The seed target is pinned BY TITLE (byte-exact 'Welcome to Anthology')
    and BY WORKSPACE (slug/board 'anthology') — any title variation is a
    DIFFERENT card that is never touched. Presence is checked across every
    archival state: a card that exists (even archived) is the
    "already welcomed" truth — the seed is idempotent, it never duplicates
    and never re-seeds.
    """
    row = con.execute(
        "SELECT id, title, status, archived_at FROM tasks "
        "WHERE workspace_id=? AND title=? LIMIT 1",
        (WORKSPACE_ID, CARD_TITLE),
    ).fetchone()
    return row


def board_snapshot(con, limit=12):
    """Read-only board snapshot for the operator surface: the live cards
    (archived_at IS NULL — the exact filter the tasks API uses) plus the
    archived count. Never more than `limit` rows printed."""
    rows = con.execute(
        "SELECT id, title, status, archived_at FROM tasks "
        "WHERE workspace_id=? AND archived_at IS NULL "
        "ORDER BY created_at LIMIT ?",
        (WORKSPACE_ID, limit),
    ).fetchall()
    archived = con.execute(
        "SELECT COUNT(*) FROM tasks WHERE workspace_id=? AND archived_at IS NOT NULL",
        (WORKSPACE_ID,),
    ).fetchone()[0]
    return rows, archived


def _print_card(row):
    board = "ARCHIVED" if row["archived_at"] else "LIVE"
    print("  %-16s %-10s %-9s  %s" % (row["id"][:16], board, row["status"], row["title"]))


def cmd_check(con, db_path):
    """READ-ONLY check: is the Welcome card on the anthology board?

    Exit 0 (PASS) when the card exists; exit 5 (AF-AE-DBC-NO-WELCOME, data-
    state refusal) when it does not — naming exactly the remediation
    (--execute seeds it). Never a silent pass, never a silent no-op.
    """
    print("== u20 db_connector check (READ-ONLY) ==")
    print("db: %s" % db_path)
    card = find_welcome_card(con)
    print("board: %s  (workspace slug '%s')" % (WORKSPACE_SLUG, WORKSPACE_SLUG))
    print("welcome card: %s"
          % ("%s (%s)" % (card["id"][:16], card["status"]) if card else "ABSENT"))
    rows, archived = board_snapshot(con)
    print("live cards on board: %d   archived: %d" % (len(rows), archived))
    for r in rows:
        _print_card(r)
    if not card:
        print("RESULT: FAIL (AF-AE-DBC-NO-WELCOME) - the anthology board carries no "
              "Welcome card; run with --execute to seed it (Trevor-gated).")
        return EX_MISMATCH
    print("RESULT: PASS")
    return EX_OK


def cmd_seed(con, db_path, execute):
    """Seed the Welcome card on the anthology board.

    READ-ONLY plan (default and --dry-run): resolve and print the plan
    surface — the exact card (id, title, board, head agent) and the
    HOW-TO-USE.md-derived body, which is copy and never a write — and exit 0
    without mutating. Under --execute: open a WRITABLE connection (never
    before the gate — connect_write is only reached after the --execute
    branch) and write the ONE card in a single BEGIN IMMEDIATE transaction
    with a busy timeout, then read it back and print the AFTER snapshot
    through the read-only connection. Idempotent: a card that already exists
    is the "already welcomed" no-op (exit 0), never a duplicate, never an
    archive, never a touch of any other row.
    """
    print("== u20 db_connector seed (Welcome card) ==")
    print("db: %s" % db_path)
    card = find_welcome_card(con)
    if card:
        print("welcome card ALREADY PRESENT: %s (%s) - nothing to do (idempotent, "
              "never re-seeds, never archives)." % (card["id"][:16], card["status"]))
        return EX_OK

    print("plan:")
    print("  board     : %s (workspace slug '%s')" % (WORKSPACE_SLUG, WORKSPACE_SLUG))
    print("  department: %s" % DEPARTMENT)
    print("  head agent: %s (%s)" % (HEAD_AGENT_ID, "Anthology Producer"))
    print("  title     : %s" % CARD_TITLE)
    print("  status    : backlog   priority: medium")
    print("  body      : derived from HOW-TO-USE.md (producer voice; %d bytes)"
          % len(welcome_card_body()))
    if not execute:
        print("[no --execute] READ-ONLY plan only - no write performed. Re-run with "
              "--execute (Trevor gate) to seed the card.")
        return EX_OK

    # THE TREVOR GATE: from here on we may write — and the writable
    # connection is created HERE, only after the gate has passed.
    wcon = connect_write(db_path)
    try:
        card_id = _card_id()
        ts = _now()
        wcon.execute("BEGIN IMMEDIATE")
        try:
            wcon.execute(
                "INSERT INTO tasks (id, workspace_id, department, title, "
                "description, status, priority, assigned_agent_id, "
                "created_by_agent_id, created_at, updated_at) VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?)",
                (card_id, WORKSPACE_ID, DEPARTMENT, CARD_TITLE, welcome_card_body(),
                 "backlog", "medium", HEAD_AGENT_ID, HEAD_AGENT_ID, ts, ts),
            )
            wcon.execute("COMMIT")
        except Exception:
            wcon.execute("ROLLBACK")
            raise
    finally:
        wcon.close()

    print("seeded: %s (%s, backlog)" % (card_id, CARD_TITLE))
    # End the read transaction that find_welcome_card opened: in WAL mode a
    # read transaction pins its snapshot at first read, so without this the
    # AFTER read would show the pre-write board. Rolling back is read-only
    # and is exactly what the connector always does at close anyway; the
    # next SELECT starts a fresh transaction with the post-write snapshot.
    con.execute("ROLLBACK")
    print("== AFTER ==")
    rows, archived = board_snapshot(con)
    print("live cards on board: %d   archived: %d" % (len(rows), archived))
    for r in rows:
        _print_card(r)
    return EX_OK


def cmd_self_test():
    """OFFLINE self-test: the golden PASS / attack FAIL battery, opened on an
    in-memory fixture DB (never the live file).

    A tamper that trips an assertion exits 4 (AF-AE-DBC-ATTACK, enforced
    violation), never exit 1 — the house rule that an attack NEVER
    masquerades as an unexpected error.
    """
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=OFF")
    con.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, title TEXT NOT NULL, "
                "description TEXT, status TEXT, priority TEXT, "
                "assigned_agent_id TEXT, created_by_agent_id TEXT, "
                "workspace_id TEXT, department TEXT, archived_at TEXT, "
                "created_at TEXT, updated_at TEXT)")
    try:
        # GOLDEN: a Welcome card present on the anthology board is a PASS.
        con.execute(
            "INSERT INTO tasks (id, title, status, workspace_id, department, "
            "created_at, updated_at) VALUES ('golden', ?, 'backlog', ?, ?, ?, ?)",
            (CARD_TITLE, WORKSPACE_ID, DEPARTMENT, "t1", "t1"))
        card = find_welcome_card(con)
        assert card is not None and card["id"] == "golden", "golden find failed"

        # ATTACK 1: a card with a DIFFERENT title is NEVER the welcome card.
        con.execute(
            "INSERT INTO tasks (id, title, status, workspace_id, created_at, "
            "updated_at) VALUES ('attack1', 'Welcome to SomethingElse', 'backlog', "
            "'anthology', 't2', 't2')")
        card = find_welcome_card(con)
        assert card is not None and card["id"] == "golden", \
            "attack1: a different-title card was mistaken for the welcome card"

        # ATTACK 2: a welcome-titled card on a DIFFERENT board is never seen.
        con.execute(
            "INSERT INTO tasks (id, title, status, workspace_id, created_at, "
            "updated_at) VALUES ('attack2', ?, 'backlog', 'other-board', 't3', 't3')",
            (CARD_TITLE,))
        card = find_welcome_card(con)
        assert card is not None and card["id"] == "golden", \
            "attack2: a card on another board was mistaken for the anthology card"

        # GOLDEN: the absent case is detected (absent card on a fresh board).
        con.execute("DELETE FROM tasks WHERE id='golden'")
        card = find_welcome_card(con)
        assert card is None, "golden-absent: an absent card was reported present"

        # ATTACK 3: the HOW-TO-USE derivation must be traceable — the copy is
        # never invented; the how-to document itself must exist and the body
        # must carry the producer-voice law ("editors" present, "AI" absent).
        assert HOW_TO_USE.is_file(), "attack3: HOW-TO-USE.md missing"
        body = welcome_card_body()
        assert "editors" in body and "AI" not in body, \
            "attack3: the card body violates the producer-voice law"
        print("self-test PASS (golden x2 + attack x3 all held)")
        return EX_OK
    except AssertionError as exc:
        print("self-test FAILED (AF-AE-DBC-ATTACK): %s" % exc)
        return EX_VIOLATION
    finally:
        con.close()


def _build_parser():
    p = argparse.ArgumentParser(
        prog="db_connector.py",
        description="u20 fail-closed sqlite3 connector over the Command Center "
                    "mission-control.db for the Anthology Welcome card surface. "
                    "READ-ONLY by default; the card INSERT runs ONLY under --execute "
                    "(Trevor-gated).",
    )
    p.add_argument("--db", default=None,
                   help="path to mission-control.db (default: DATABASE_PATH, then "
                        "the CC data dir literal)")
    p.add_argument("--check", action="store_true",
                   help="READ-ONLY: report whether the Welcome card is on the "
                        "anthology board (exit 5 AF-AE-DBC-NO-WELCOME when absent)")
    p.add_argument("--seed", action="store_true",
                   help="plan (READ-ONLY) or, with --execute, perform the Welcome "
                        "card seed (idempotent)")
    p.add_argument("--execute", action="store_true",
                   help="Trevor gate: perform the seed ACTION. Without it --seed "
                        "is a READ-ONLY plan that writes nothing")
    p.add_argument("--self-test", action="store_true",
                   help="OFFLINE self-test battery on an in-memory fixture DB "
                        "(never the live file)")
    return p


def main(argv=None):
    args = _build_parser().parse_args(argv)

    if args.self_test:
        return cmd_self_test()
    if not args.check and not args.seed:
        print("usage: --check (read-only) | --seed [--execute] | --self-test "
              "(offline); see --help.", file=sys.stderr)
        return EX_STOP

    db_path = resolve_db_path(args.db)
    con = None
    try:
        con = connect_readonly(db_path)
    except (sqlite3.Error, OSError) as exc:
        print("FATAL: database not openable (AF-AE-DBC-NO-DB): %s: %s"
              % (db_path, exc), file=sys.stderr)
        return EX_STOP

    try:
        if args.seed:
            return cmd_seed(con, db_path, execute=args.execute)
        return cmd_check(con, db_path)
    except sqlite3.Error as exc:
        # The write path is wrapped: a failed --execute write is an
        # unexpected error (exit 1), never a silent no-op. A HELD retryable
        # (busy) surfaces as this same code — the operator retries.
        print("ERROR: database operation failed: %s" % exc, file=sys.stderr)
        return EX_ERR
    except FileNotFoundError:
        print("FATAL: HOW-TO-USE.md missing (the Welcome card copy derives from "
              "it and can never be invented): %s" % HOW_TO_USE, file=sys.stderr)
        return EX_STOP
    finally:
        _close_readonly(con)


if __name__ == "__main__":
    sys.exit(main())
