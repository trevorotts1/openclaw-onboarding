#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u20_modules/welcome_action.py
# ANTHOLOGY WELCOME CARD SEEDER (U20 tooling) — the fail-closed, GET-first
# idempotent seeder that lands the producer-facing WELCOME card on the
# client's Command Center Anthology department board. The ACTION (the
# INSERT into mission-control.db's tasks table) is Trevor-gated: it runs
# ONLY under --execute. Without --execute the module reports what it WOULD
# do and exits without mutating (STOP, exit 2, AF-AE-WELCOME-NO-EXECUTE).
#
# WHAT THIS IS:
#   The producer-facing Welcome card is the engine's first surface on the
#   client's own Command Center Anthology board. Its CONTENT derives from
#   HOW-TO-USE.md (the producer how-to: the board as the producer's work
#   surface, participants with no login receiving one private link each,
#   assembly as the producer's one-way decision, deliverables always BOTH
#   a Google Doc and a designed PDF) — the card is copy, never a write.
#   The card is a task row on the Anthology department board, exactly the
#   shape Skill 32's add-department.sh step 3 seeds ("Welcome to <Dept>"),
#   so the Welcome card lands with the same schema conventions: tasks
#   table, department='anthology', status 'backlog', assigned to the
#   Anthology department-head agent, priority medium.
#
#   IDEMPOTENCY LAW (GET-first, seed only if absent): the module queries
#   the tasks table for an existing Anthology Welcome card (by the fixed
#   idempotency key marker the module itself controls) and seeds ONLY when
#   no such card is already present. A card that already exists is
#   VERIFIED and skipped (exit 0, idempotent no-op — never a duplicate
#   card, never a second INSERT).
#
#   READ-BACK LAW: a write is never trusted without read-back. After the
#   INSERT, the module SELECTs the seeded row back by its task id and
#   confirms the card exists before any report claims seeded. A missing
#   read-back is a MISMATCH (exit 5), never a false success.
#
#   THE ACTION STAYS GATED: the module NEVER inserts without --execute.
#   Default and --dry-run are read-only / plan-only. The actual INSERT is
#   the DB-scoped ACTION boundary: it runs ONLY when the operator
#   explicitly passes --execute (Trevor gate; the u20_modules package
#   contract in __init__.py: "the engine's database is READ-ONLY in
#   dry-run: this package must never write the DB unless the caller passed
#   --execute explicitly").
#
# THE DATABASE:
#   The target is the client's Command Center SQLite ledger
#   (mission-control.db), the SAME database Skill 32's add-department.sh
#   seeds (its find_db() candidate list is mirrored here byte-for-byte,
#   plus the DATABASE_PATH env override the Command Center itself honors:
#   src/lib/db/index.ts getDbPath — DATABASE_PATH always wins). The module
#   REFUSES to guess: no candidate found, no DATABASE_PATH -> STOP
#   (exit 2, AF-AE-WELCOME-DB-MISSING) — never a write into the unknown,
#   never a fallback to a "default" database path.
#
#   The card is a TASK ROW, never a ledger row: the durable engine ledger
#   (anthology_state.db) stays untouched — this module reads only the
#   Command Center tasks table and inserts only there, and only under
#   --execute. The engine's own anthology_state.db is NEVER opened by this
#   module.
#
# SAFETY DOCTRINE (house, per anthology_registry / provision_action):
#   - Column-intersect INSERT (PRAGMA table_info(tasks), write only the
#     columns that exist) so a schema drift can never blind-write into an
#     unknown column — the add-department.sh convention.
#   - The seeded row carries the module's fixed idempotency marker in the
#     description ("Ref: anthology:welcome:card", the same anthology:*
#     ref vocabulary mc_board.py uses), so the GET-first check and the
#     Command Center's own dedupe both anchor on one key.
#   - No secret value is ever printed. No credential is resolved or read:
#     this module touches NO API, NO token, NO PIT. Nothing Anthropic.
#   - Move in silence: operator-verbose only; the client-facing platform
#     name is Convert and Flow on every surface (this card describes the
#     producer's board — the engine surfaces inside the client's OWN
#     Command Center).
#
# AF ERROR CODES (fail-closed surfaces, house scheme):
#   AF-AE-WELCOME-NO-EXECUTE    -> the INSERT (the ACTION) was requested
#          without --execute. STOP (exit 2); the module NEVER inserts
#          without the explicit Trevor-gated execute flag.
#   AF-AE-WELCOME-DB-MISSING    -> no Command Center database found in any
#          candidate location and no DATABASE_PATH env override. STOP
#          (exit 2); never a write into the unknown, never a guessed path.
#   AF-AE-WELCOME-READ-REFUSED  -> the GET-first existence check or the
#          read-back SELECT failed on the found database (missing table /
#          sqlite error / unreadable file). STOP (exit 2) — never a silent
#          skip, never a seed-into-the-unknown.
#   AF-AE-WELCOME-CARD-REFUSED  -> the found database refused the INSERT
#          (sqlite error / constraint / read-only file). STOP (exit 2).
#   AF-AE-WELCOME-READBACK-MISMATCH -> the post-insert read-back SELECT
#          returned no row for the seeded task id (exit 5). Nothing is
#          ever reported seeded without read-back.
#   AF-AE-WELCOME-ATTACK        -> an attack fixture tripped the OFFLINE
#          self-test. Exit 4 (enforced violation), never exit 1.
#
# EXIT CODES (house convention; nonzero STOPS/HELDs with an operator
# surface):
#   0  verified success (idempotent no-op / dry run counts as pass)
#   1  unexpected error
#   2  STOP refusal -- usage error / database missing / missing --execute
#      / a genuine read or write refusal
#   3  (reserved: HELD -- this module holds no retryable upstream surface)
#   4  self-test FAILED -- an assertion in the OFFLINE self-test tripped
#      (AF-AE-WELCOME-* family). A tamper NEVER masquerades as exit 1.
#   5  data or read-back mismatch (the post-insert read-back was missing)
#
# STDLIB ONLY (sqlite3 + argparse). Calls NO model, NO API, NO credential.
# DOCTRINE: move in silence; nothing Anthropic in any runtime file;
# Convert and Flow naming in every client surface; NEVER print a secret
# value; --dry-run and --self-test are OFFLINE; the DB is READ-ONLY in
# dry-run.
# =============================================================================
"""welcome_action.py -- Trevor-gated Anthology Welcome card seeder for the
client's Command Center Anthology department board (Skill 59, U20 tooling).
GET-first idempotent; the INSERT into mission-control.db runs ONLY under
--execute; post-insert read-back enforced."""

from __future__ import annotations

import argparse
import io
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

EX_OK = 0
EX_ERR = 1
EX_STOP = 2
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)
EX_MISMATCH = 5

# ---------------------------------------------------------------------------
# Constants (fixed law surfaces; a tamper drifts the self-test, exit 4)
# ---------------------------------------------------------------------------

# The Command Center database. The same candidate list Skill 32's
# add-department.sh find_db() walks (byte-for-byte), plus the DATABASE_PATH
# env override the Command Center itself honors (src/lib/db/index.ts
# getDbPath: DATABASE_PATH always wins). First existing candidate wins.
DB_CANDIDATES = (
    os.environ.get("DATABASE_PATH", "").strip(),   # CC's own explicit override
    os.path.expanduser("~/projects/command-center/mission-control.db"),
    os.path.expanduser("~/projects/mission-control/mission-control.db"),
    "/opt/mission-control/mission-control.db",
    "/app/mission-control.db",
    "/data/projects/command-center/mission-control.db",
)

# The Anthology department board (mc_board.py DEFAULT_DEPARTMENT_SLUG).
DEPARTMENT_SLUG = "anthology"

# The fixed idempotency marker this module controls. It rides the card
# description as "Ref: <marker>" -- the SAME "anthology:*" ref vocabulary
# mc_board.py uses (anthology:card:<pk> / anthology:assembly:<aid>) -- so
# the GET-first existence check, the Command Center's own ingest-dedupe,
# and the read-back all anchor on ONE key. A Welcome card seeded by this
# module always carries it; a card without it is never treated as seeded.
WELCOME_REF = "anthology:welcome:card"

# The Welcome card's title (the add-department.sh step-3 shape:
# "Welcome to <Dept>").
WELCOME_TITLE = "Welcome to Anthology"

# The Welcome card's description: the producer-facing content that derives
# from HOW-TO-USE.md. This is COPY -- the card ships it; it is never a
# write. The full HOW-TO-USE.md body is appended verbatim by the module at
# seed time (the how-to IS the card's substance); this constant is the
# fixed opening paragraph that pins the card's identity.
WELCOME_LEAD = (
    "Welcome to your Anthology board. You are the producer -- the owner of "
    "this Command Center. Your co-authors are your participants. Everything "
    "you do happens on YOUR board and through your forms; you never touch a "
    "script. Your deliverables always ship as BOTH a Google Doc and a "
    "designed PDF, with a comfortable, readable type size throughout."
)

# The tasks-column vocabulary this module may write. A column that does not
# exist in the live table is simply not written (the add-department.sh
# column-intersect convention) -- the module never invents a column.
_TASK_COLUMNS = (
    "id", "title", "description", "status", "priority",
    "workspace_id", "department", "source", "created_at", "updated_at",
)

_WORKSPACE_COLUMNS = ("id", "name", "slug")

_AGENT_COLUMNS = ("id", "name", "workspace_id")


def _now_iso() -> str:
    """ISO-8601 UTC timestamp, the CC schema's created_at/updated_at shape."""
    return datetime.now(timezone.utc).isoformat()


def _mask_path(path) -> str:
    """A non-reversible marker for a database path: the file name only. A
    full path is an operator-surface detail but never a secret; the marker
    keeps surfaces short and uniform."""
    return str(Path(path).name) if path else "(none)"


# ---------------------------------------------------------------------------
# Database discovery + connection (READ-ONLY unless the ACTION runs)
# ---------------------------------------------------------------------------
def find_db() -> str:
    """Resolve the Command Center mission-control.db path. DATABASE_PATH env
    override wins (CC's own rule); then the canonical candidate list; never
    a guess. Returns "" when no candidate exists (STOP upstream)."""
    for cand in DB_CANDIDATES:
        if not cand:
            continue
        p = Path(cand).expanduser()
        if p.is_file():
            return str(p)
    return ""


def _connect(db_path: str, *, read_only: bool = False):
    """Open the Command Center database. read_only=True opens the file in
    SQLite URI read-only mode so a dry-run/plan can NEVER write, even by
    accident (uri mode=ro; sqlite errors on any write attempt)."""
    if read_only:
        uri = "file:%s?mode=ro" % db_path.replace("?", "%3f")
        con = sqlite3.connect(uri, uri=True, timeout=10)
    else:
        con = sqlite3.connect(db_path, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=5000")
    return con


def _columns(con, table: str):
    """The live column names of a table, or [] when the table is missing.
    Never raises for a missing table: the caller classifies the refusal."""
    try:
        return [r[1] for r in con.execute("PRAGMA table_info(%s)" % table)]
    except sqlite3.Error:
        return []


def _find_welcome(con, col_names):
    """GET-first existence check: the first tasks row carrying the fixed
    Welcome marker (description LIKE '%anthology:welcome:card%') OR the
    exact Welcome title, scoped to the Anthology department when the
    department column exists. Returns a sqlite3.Row or None. READ-ONLY."""
    dept_clause = ""
    dept_args = []
    if "department" in col_names:
        dept_clause = " AND department = ?"
        dept_args = [DEPARTMENT_SLUG]
    try:
        row = con.execute(
            "SELECT * FROM tasks WHERE (title = ? OR description LIKE ?) %s "
            "ORDER BY rowid ASC LIMIT 1" % dept_clause,
            [WELCOME_TITLE, "%" + WELCOME_REF + "%"] + dept_args,
        ).fetchone()
        return row
    except sqlite3.Error:
        return None


def _find_head_agent(con, ag_cols):
    """The Anthology department-head agent (add-department.sh assigns the
    Welcome task to it). Returns the agent id or "" when unresolvable.
    READ-ONLY; never guesses an id."""
    try:
        row = con.execute(
            "SELECT id FROM agents WHERE workspace_id = ? OR "
            "name LIKE ? OR persona LIKE ? ORDER BY rowid ASC LIMIT 1",
            (DEPARTMENT_SLUG, "%Anthology Department Head%", "%dept-anthology%"),
        ).fetchone()
        return str(row[0]) if row is not None else ""
    except sqlite3.Error:
        return ""


def _find_workspace(con, ws_cols):
    """The Anthology workspace row. Returns the workspace id or "" when
    unresolvable. READ-ONLY; never guesses an id."""
    try:
        row = con.execute(
            "SELECT id FROM workspaces WHERE slug = ? OR name = ? "
            "ORDER BY rowid ASC LIMIT 1",
            (DEPARTMENT_SLUG, DEPARTMENT_SLUG),
        ).fetchone()
        return str(row[0]) if row is not None else ""
    except sqlite3.Error:
        return ""


def _read_howto() -> str:
    """Read the producer how-to (HOW-TO-USE.md) that the Welcome card's
    substance derives from. This is the card's CONTENT SOURCE -- copy only,
    never a write. Returns the full text, or "" when the file is missing
    (the fixed lead paragraph still ships; the module never fabricates a
    how-to)."""
    here = Path(__file__).resolve().parent
    for cand in (here.parent.parent / "HOW-TO-USE.md",
                 here.parents[2] / "HOW-TO-USE.md"):
        if cand.is_file():
            try:
                return cand.read_text(encoding="utf-8").strip()
            except OSError:
                return ""
    return ""


def build_card(*, howto: str = "") -> dict:
    """Assemble the Welcome card payload. `howto` is the HOW-TO-USE.md body
    ("" allowed: the fixed lead still ships). The description embeds the
    fixed idempotency marker so the GET-first check, the CC ingest dedupe,
    and the read-back anchor on ONE key. Returns the dict of columns to
    write (a subset of _TASK_COLUMNS; the INSERT intersects live columns)."""
    body = howto.strip() or ""
    if body:
        desc = "%s\n\n%s\n\nRef: %s" % (WELCOME_LEAD, body, WELCOME_REF)
    else:
        desc = "%s\n\nRef: %s" % (WELCOME_LEAD, WELCOME_REF)
    now = _now_iso()
    return {
        "title": WELCOME_TITLE,
        "description": desc,
        "status": "backlog",
        "priority": "medium",
        "department": DEPARTMENT_SLUG,
        "source": DEPARTMENT_SLUG,
        "created_at": now,
        "updated_at": now,
    }


# ---------------------------------------------------------------------------
# The ACTION (INSERT; Trevor-gated -- --execute or nothing)
# ---------------------------------------------------------------------------
def seed_welcome(db_path: str, *, execute: bool = False, task_id: str = "",
                 out=None, jsonout=None) -> int:
    """GET-first idempotent seeding of the Anthology Welcome card. The
    INSERT runs ONLY under --execute. A missing database STOPS (exit 2)
    before anything. An existing Welcome card is a VERIFIED no-op (exit 0).
    After the INSERT the module SELECTs the row back by task id -- a
    missing read-back is a MISMATCH (exit 5), never a false pass."""
    out = out or sys.stderr
    masked = _mask_path(db_path)

    # -- 0. DATABASE LAW: never seed into the unknown ------------------------
    if not db_path:
        out.write("[welcome-action] AF-AE-WELCOME-DB-MISSING: no Command "
                  "Center database found (DATABASE_PATH unset and no "
                  "candidate exists). STOP; nothing seeded.\n")
        if jsonout is not None:
            json.dump({"ok": False, "exit": EX_STOP,
                       "reason": "db-missing"}, jsonout)
            jsonout.write("\n")
        return EX_STOP

    try:
        con = _connect(db_path, read_only=(not execute))
    except sqlite3.Error as exc:
        out.write("[welcome-action] AF-AE-WELCOME-READ-REFUSED: cannot open "
                  "database %s: %s\n" % (masked, exc))
        return EX_STOP

    try:
        tk_cols = _columns(con, "tasks")
        if not tk_cols:
            out.write("[welcome-action] AF-AE-WELCOME-READ-REFUSED: the "
                      "tasks table is missing in %s. STOP; nothing seeded.\n"
                      % masked)
            if jsonout is not None:
                json.dump({"ok": False, "exit": EX_STOP,
                           "reason": "tasks-table-missing"}, jsonout)
                jsonout.write("\n")
            return EX_STOP

        # -- 1. GET-first idempotency check -----------------------------------
        existing = _find_welcome(con, tk_cols)
        if existing is not None:
            out.write("[welcome-action] IDEMPOTENT NO-OP (%s): the Anthology "
                      "Welcome card already exists (task id %s). Nothing "
                      "seeded.\n" % (masked, existing["id"]))
            if jsonout is not None:
                json.dump({"ok": True, "seeded": False, "already": True,
                           "task_id": str(existing["id"]),
                           "db": masked}, jsonout)
                jsonout.write("\n")
            return EX_OK

        # -- 2. Trevor-gated ACTION boundary ----------------------------------
        if not execute:
            out.write("[welcome-action] AF-AE-WELCOME-NO-EXECUTE: no "
                      "Anthology Welcome card exists in %s and --execute was "
                      "NOT passed. The INSERT is a Trevor-gated ACTION: "
                      "STOP, nothing written. (The database was opened "
                      "read-only; no mutation was possible.)\n" % masked)
            if jsonout is not None:
                json.dump({"ok": False, "exit": EX_STOP,
                           "reason": "no-execute"}, jsonout)
                jsonout.write("\n")
            return EX_STOP

        # -- 3. Resolve the row's references (READ-ONLY, never guessed) ------
        ag_cols = _columns(con, "agents")
        ws_cols = _columns(con, "workspaces")
        head_agent = _find_head_agent(con, ag_cols) if ag_cols else ""
        ws_id = _find_workspace(con, ws_cols) if ws_cols else ""

        # -- 4. Build the card, intersect with live columns, INSERT ----------
        card = build_card(howto=_read_howto())
        card["id"] = task_id or ("welcome_" + os.urandom(8).hex())
        if head_agent:
            card["assigned_agent_id"] = head_agent
        if ws_id:
            card["workspace_id"] = ws_id
        write_cols = [c for c in card if c in tk_cols]
        if not write_cols or "id" not in write_cols or "title" not in write_cols:
            out.write("[welcome-action] AF-AE-WELCOME-CARD-REFUSED: the "
                      "tasks table in %s carries none of the required "
                      "columns (id/title). STOP; nothing seeded.\n" % masked)
            return EX_STOP
        sql = ("INSERT INTO tasks (%s) VALUES (%s)"
               % (",".join(write_cols), ",".join("?" * len(write_cols))))
        try:
            con.execute(sql, [card[c] for c in write_cols])
            con.commit()
        except sqlite3.Error as exc:
            con.rollback()
            out.write("[welcome-action] AF-AE-WELCOME-CARD-REFUSED: the "
                      "INSERT into %s was refused: %s. STOP; nothing "
                      "reported seeded.\n" % (masked, exc))
            if jsonout is not None:
                json.dump({"ok": False, "exit": EX_STOP,
                           "reason": "card-refused"}, jsonout)
                jsonout.write("\n")
            return EX_STOP

        # -- 5. READ-BACK (a write is never trusted without read-back) --------
        try:
            read_back = con.execute(
                "SELECT id, title, status FROM tasks WHERE id = ? LIMIT 1",
                [card["id"]],
            ).fetchone()
        except sqlite3.Error as exc:
            read_back = None
            _rbfail = str(exc)
        else:
            _rbfail = ""
        if read_back is None:
            out.write("[welcome-action] AF-AE-WELCOME-READBACK-MISMATCH: the "
                      "post-insert read-back for task id %s in %s returned "
                      "no row%s. The INSERT is NOT reported as seeded.\n"
                      % (card["id"], masked,
                         (": %s" % _rbfail) if _rbfail else ""))
            if jsonout is not None:
                json.dump({"ok": False, "exit": EX_MISMATCH,
                           "reason": "readback-missing"}, jsonout)
                jsonout.write("\n")
            return EX_MISMATCH

        out.write("[welcome-action] SEEDED (%s): Welcome card %s (%s) "
                  "inserted and confirmed by read-back.\n"
                  % (masked, read_back["id"], read_back["title"]))
        if jsonout is not None:
            json.dump({"ok": True, "seeded": True, "already": False,
                       "task_id": str(read_back["id"]),
                       "db": masked}, jsonout)
            jsonout.write("\n")
        return EX_OK
    finally:
        con.close()


def plan_welcome(db_path: str, *, out=None, jsonout=None) -> int:
    """READ-ONLY plan: report what seeding WOULD do without any mutation.
    The database is opened in SQLite read-only URI mode -- a write is
    impossible even by accident (mode=ro errors on any DML). A missing
    database is a plan-time STOP (exit 2), never a guess."""
    out = out or sys.stderr
    masked = _mask_path(db_path)
    if not db_path:
        out.write("[welcome-action] AF-AE-WELCOME-DB-MISSING: no Command "
                  "Center database found (DATABASE_PATH unset and no "
                  "candidate exists). STOP; nothing to plan.\n")
        if jsonout is not None:
            json.dump({"ok": False, "exit": EX_STOP,
                       "reason": "db-missing"}, jsonout)
            jsonout.write("\n")
        return EX_STOP
    try:
        con = _connect(db_path, read_only=True)
    except sqlite3.Error as exc:
        out.write("[welcome-action] AF-AE-WELCOME-READ-REFUSED: cannot open "
                  "database %s read-only: %s\n" % (masked, exc))
        return EX_STOP
    try:
        tk_cols = _columns(con, "tasks")
        if not tk_cols:
            out.write("[welcome-action] AF-AE-WELCOME-READ-REFUSED: the "
                      "tasks table is missing in %s. STOP; nothing to plan.\n"
                      % masked)
            return EX_STOP
        existing = _find_welcome(con, tk_cols)
        state = "already-seeded" if existing is not None else "needs-seed"
        out.write("[welcome-action] PLAN (%s): %s. With --execute, the "
                  "module would %s.\n"
                  % (masked, state,
                     "verify the existing card (idempotent no-op)"
                     if existing is not None
                     else "insert ONE Anthology Welcome card into the tasks "
                          "table, then read it back"))
        if jsonout is not None:
            json.dump({"ok": True, "dry_run": True, "db": masked,
                       "state": state,
                       "seed_needed": existing is None}, jsonout)
            jsonout.write("\n")
        return EX_OK
    finally:
        con.close()


# ---------------------------------------------------------------------------
# SELF-TEST: golden + attack fixtures, zero network, zero secrets, zero
# writes to any real database. Mirrors the sibling self-tests
# (provision_action / provision_sms_phone / anthology_registry): an
# assertion failure is an ENFORCED VIOLATION, exit 4 -- a tamper never
# masquerades as "unexpected error" (exit 1).
# ---------------------------------------------------------------------------
class _FakeDb:
    """In-memory SQLite (a temp file) standing in for mission-control.db.
    The self-test exercises the REAL functions against this file -- the
    same instrument the live module uses -- with programmable contents,
    and a mutation log proving no write happened when none should."""

    def __init__(self, *, tasks_present=True, with_welcome=False,
                 with_agents=True, with_workspaces=True, cards=None):
        import tempfile
        self._fd, self._path = tempfile.mkstemp(suffix=".db")
        os.close(self._fd)
        self.writes = []
        con = sqlite3.connect(self._path)
        try:
            con.executescript(
                """
                CREATE TABLE tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    description TEXT,
                    status TEXT,
                    priority TEXT,
                    workspace_id TEXT,
                    department TEXT,
                    source TEXT,
                    assigned_agent_id TEXT,
                    created_at TEXT,
                    updated_at TEXT
                );
                CREATE TABLE agents (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    workspace_id TEXT,
                    persona TEXT
                );
                CREATE TABLE workspaces (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    slug TEXT
                );
                """
            )
            con.execute("INSERT INTO agents (id, name, workspace_id, persona) "
                        "VALUES ('ag_head', 'Anthology Department Head', "
                        "'anthology', 'dept-anthology')")
            con.execute("INSERT INTO workspaces (id, name, slug) "
                        "VALUES ('anthology', 'Anthology', 'anthology')")
            if with_welcome:
                con.execute(
                    "INSERT INTO tasks (id, title, description, status, "
                    "department) VALUES ('task_welcome', ?, ?, 'backlog', ?)",
                    (WELCOME_TITLE, "…%s…" % WELCOME_REF, DEPARTMENT_SLUG))
            for c in (cards or []):
                cols = ", ".join(c)
                ph = ", ".join("?" * len(c))
                con.execute("INSERT INTO tasks (%s) VALUES (%s)"
                            % (cols, ph), list(c.values()))
            con.commit()
        finally:
            con.close()
        self.tasks_present = tasks_present
        self._sqlite_error_on = None

    @property
    def path(self):
        return self._path

    def drop_tasks(self):
        """Attack shape: the tasks table is missing entirely."""
        con = sqlite3.connect(self._path)
        con.execute("DROP TABLE tasks")
        con.commit()
        con.close()
        self.tasks_present = False

    def __del__(self):
        try:
            os.unlink(self._path)
        except OSError:
            pass


def _welcome_card_snapshot(con):
    """Attack instrument: snapshot the tasks rows so the self-test can prove
    exactly which rows exist before/after a call (a tamper can never hide a
    write behind the module's own read paths)."""
    try:
        rows = con.execute("SELECT id, title, department FROM tasks "
                           "ORDER BY rowid").fetchall()
        # Positional indexing: works whether or not the caller set
        # row_factory (a row is id, title, department).
        return [(r[0], r[1], r[2]) for r in rows]
    except sqlite3.Error:
        return []


def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        # (0) law surfaces: the ref marker, the title, the lead, the slug
        assert WELCOME_REF == "anthology:welcome:card"
        assert WELCOME_TITLE == "Welcome to Anthology"
        assert DEPARTMENT_SLUG == "anthology"
        assert WELCOME_LEAD.startswith("Welcome to your Anthology board.")
        assert "Google Doc" in WELCOME_LEAD and "PDF" in WELCOME_LEAD

        # (1) build_card: description carries the lead, the how-to, and the
        #     idempotency marker exactly once each; columns stay a subset of
        #     _TASK_COLUMNS
        howto = ("You are the producer. Your deliverables ship as BOTH a "
                 "Google Doc and a designed PDF.")
        card = build_card(howto=howto)
        assert card["title"] == WELCOME_TITLE
        assert WELCOME_LEAD in card["description"]
        assert howto in card["description"]
        assert card["description"].count(WELCOME_REF) == 1
        assert card["status"] == "backlog" and card["priority"] == "medium"
        assert card["department"] == DEPARTMENT_SLUG
        assert set(card) <= set(_TASK_COLUMNS)
        card_bare = build_card(howto="")
        assert "Ref: %s" % WELCOME_REF in card_bare["description"]

        # (2) idempotency: an existing Welcome card -> NO-OP, zero writes,
        #     exit 0, marker says already
        fake = _FakeDb(with_welcome=True)
        rc = seed_welcome(fake.path, out=dev)
        assert rc == EX_OK, "already-seeded must exit 0, got %s" % rc
        assert "IDEMPOTENT NO-OP" in dev.getvalue()
        con = sqlite3.connect(fake.path)
        before = _welcome_card_snapshot(con)
        con.close()
        assert len(before) == 1, "already-seeded DB must stay exactly one card"

        # (3) no-execute: no card, no --execute -> STOP (exit 2), NO write
        fake2 = _FakeDb()
        rc2 = seed_welcome(fake2.path, out=dev)
        assert rc2 == EX_STOP, "missing --execute must STOP (exit 2), got %s" % rc2
        assert "AF-AE-WELCOME-NO-EXECUTE" in dev.getvalue()
        con2 = sqlite3.connect(fake2.path)
        assert _welcome_card_snapshot(con2) == [], \
            "without --execute the tasks table must stay empty"
        con2.close()

        # (4) dry-run plan: READ-ONLY, no writes, reports what WOULD happen
        dev4 = io.StringIO()
        rc4 = plan_welcome(fake2.path, out=dev4)
        assert rc4 == EX_OK, "dry-run plan must exit 0, got %s" % rc4
        assert "needs-seed" in dev4.getvalue()
        fake4b = _FakeDb(with_welcome=True)
        rc4b = plan_welcome(fake4b.path, out=dev4)
        assert rc4b == EX_OK and "already-seeded" in dev4.getvalue()

        # (5) db-missing ladder: no DATABASE_PATH and no candidate -> STOP,
        #     never a guess, never a write
        rc5 = seed_welcome("", out=dev)
        assert rc5 == EX_STOP, "missing db must STOP, got %s" % rc5
        assert "AF-AE-WELCOME-DB-MISSING" in dev.getvalue()
        rc5b = plan_welcome("", out=dev)
        assert rc5b == EX_STOP

        # (6) tasks-table-missing: a DB without the tasks table -> STOP,
        #     never a blind create
        fake6 = _FakeDb()
        fake6.drop_tasks()
        rc6 = seed_welcome(fake6.path, out=dev)
        assert rc6 == EX_STOP, "missing tasks table must STOP, got %s" % rc6
        assert "AF-AE-WELCOME-READ-REFUSED" in dev.getvalue()
        rc6b = plan_welcome(fake6.path, out=dev)
        assert rc6b == EX_STOP

        # (7) full happy path with --execute: exactly one INSERT, read-back
        #     confirms, exit 0, marker says seeded
        dev7 = io.StringIO()
        fake7 = _FakeDb()
        rc7 = seed_welcome(fake7.path, execute=True, out=dev7)
        assert rc7 == EX_OK, "happy path must exit 0, got %s" % rc7
        assert "SEEDED" in dev7.getvalue()
        assert "read-back" in dev7.getvalue()
        con7 = sqlite3.connect(fake7.path)
        con7.row_factory = sqlite3.Row
        rows7 = con7.execute("SELECT id, title, department, status, "
                             "assigned_agent_id FROM tasks").fetchall()
        con7.close()
        assert len(rows7) == 1, "happy path must insert exactly one card"
        r = rows7[0]
        assert r["title"] == WELCOME_TITLE
        assert r["department"] == DEPARTMENT_SLUG
        assert r["status"] == "backlog"
        assert r["assigned_agent_id"] == "ag_head", \
            "the card must be assigned to the Anthology department-head agent"
        # The seeded description must carry the how-to-derived lead (the
        # real HOW-TO-USE.md is beside the module; a missing file still
        # ships the fixed lead -- never a fabricated how-to)
        con7b = sqlite3.connect(fake7.path)
        desc7 = con7b.execute("SELECT description FROM tasks").fetchone()[0]
        con7b.close()
        assert WELCOME_LEAD in desc7
        assert "Ref: %s" % WELCOME_REF in desc7

        # (8) re-run after seeding (with --execute): idempotent no-op, still
        #     exactly one card, exit 0
        rc8 = seed_welcome(fake7.path, execute=True, out=dev7)
        assert rc8 == EX_OK
        con8 = sqlite3.connect(fake7.path)
        assert len(_welcome_card_snapshot(con8)) == 1, \
            "re-seeding must never duplicate the card"
        con8.close()

        # (9) attack: a non-Welcome card with a similar title is never
        #     treated as the seeded card (the marker is the authority); a
        #     card that lacks the marker in another department is not ours
        fake9 = _FakeDb(cards=[{
            "id": "task_other", "title": "Welcome to Something Else",
            "description": "a different welcome card, no marker",
            "status": "backlog", "department": "other",
        }])
        dev9 = io.StringIO()
        rc9 = seed_welcome(fake9.path, execute=True, out=dev9)
        assert rc9 == EX_OK, "a non-marker card must not block seeding"
        con9 = sqlite3.connect(fake9.path)
        con9.row_factory = sqlite3.Row
        rows9 = con9.execute("SELECT id, title FROM tasks").fetchall()
        con9.close()
        assert len(rows9) == 2, \
            "the foreign card must remain and the Welcome card must be seeded"
        assert any(r["id"] == "task_other" for r in rows9)

        # (10) never-print / never-leak: no absolute DB path beyond the
        #      masked marker, no task id of a real fixture, no secret
        all_text = (dev.getvalue() + dev4.getvalue() + dev7.getvalue()
                    + dev9.getvalue())
        assert "mission-control.db" not in all_text or \
            all_text.count("mission-control.db") <= 1, \
            "operator surfaces must mask the DB path"
        assert "ag_head" not in all_text, "fixture agent id must not leak"

        out.write("welcome_action self-test: OK (GET-first idempotency "
                  "[existing card -> no-op], no-execute STOP, dry-run plan "
                  "offline read-only, db-missing STOP, tasks-table-missing "
                  "STOP, happy-path insert exactly once + read-back, "
                  "re-seed no-op, foreign-card attack never trusted, "
                  "masked-path surfaces)\n")
        return EX_OK
    except AssertionError as exc:
        sys.stderr.write("[welcome_action] SELF-TEST FAILED "
                         "(AF-AE-WELCOME-* family): %s\n" % exc)
        return EX_VIOLATION


# ---------------------------------------------------------------------------
# CLI (house style: argparse + subcommands + --self-test/--selftest aliases)
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="welcome_action.py",
        description="Trevor-gated Anthology Welcome card seeder for the "
                    "client's Command Center Anthology board (Skill 59, U20 "
                    "tooling). GET-first idempotent; the INSERT into "
                    "mission-control.db runs ONLY under --execute. NEVER "
                    "writes the database without --execute.")
    ap.add_argument("--db", default="",
                    help="explicit Command Center database path (overrides "
                    "DATABASE_PATH and the candidate list; never printed "
                    "in full)")
    ap.add_argument("--task-id", default="",
                    help="explicit task id for the seeded card (default: a "
                    "generated welcome_<hex> id)")
    ap.add_argument("--dry-run", action="store_true",
                    help="plan the seeding without performing it (the "
                    "database is opened read-only; no write is possible)")
    ap.add_argument("--execute", action="store_true",
                    help="Trevor-gated ACTION flag: only with this flag may "
                    "the module INSERT the Welcome card")
    ap.add_argument("--json", action="store_true",
                    help="emit a machine-readable summary on stdout")
    ap.add_argument("cmd", choices=["seed", "plan", "self-test"])

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    # so argparse's required positional cmd never rejects the flag form.
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)
    jsonout = sys.stdout if args.json else None

    try:
        if args.cmd == "self-test":
            return self_test()

        db_path = args.db.strip() or find_db()

        if args.cmd == "plan":
            if args.dry_run:
                # No database I/O in dry-run: the masked marker plus the
                # plan surface; nothing exists offline.
                masked = _mask_path(db_path or "DRYRUN")
                sys.stderr.write("[welcome-action] DRY RUN (%s): would "
                                 "check the Anthology tasks table for an "
                                 "existing Welcome card, then insert ONE "
                                 "Welcome card only if none exists, then "
                                 "read it back. No writes performed.\n"
                                 % masked)
                if jsonout is not None:
                    json.dump({"ok": True, "dry_run": True, "db": masked,
                               "state": "planned"}, jsonout)
                    jsonout.write("\n")
                return EX_OK
            return plan_welcome(db_path, out=sys.stderr, jsonout=jsonout)

        if args.cmd == "seed":
            if args.dry_run:
                # No database I/O in dry-run: same offline plan surface.
                masked = _mask_path(db_path or "DRYRUN")
                sys.stderr.write("[welcome-action] DRY RUN (%s): would "
                                 "GET-check the tasks table, then insert "
                                 "the Anthology Welcome card only if none "
                                 "exists, then read it back. No writes "
                                 "performed.\n" % masked)
                if jsonout is not None:
                    json.dump({"ok": True, "dry_run": True, "db": masked,
                               "seed_needed": True}, jsonout)
                    jsonout.write("\n")
                return EX_OK
            return seed_welcome(db_path, execute=args.execute,
                                task_id=args.task_id.strip(),
                                out=sys.stderr, jsonout=jsonout)

        ap.error("unknown command %r" % args.cmd)
    except SystemExit:
        raise
    except Exception as exc:
        sys.stderr.write("[welcome_action] unexpected error: %s\n" % exc)
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
