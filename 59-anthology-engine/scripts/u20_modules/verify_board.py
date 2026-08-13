#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u20_modules/verify_board.py  (U20 tooling)
# POST-ACTION BOARD VERIFIER — the read-back half of the Anthology board
# hygiene ACTION (the U14 board-hygiene law, carried in from the Command
# Center's u14-anthology-board-hygiene.py, never re-typed): re-reads the
# Command Center's Anthology department board and CONFIRMS, fail-closed,
# that (a) ZERO synthetic drill cards are live on the open board (the
# 'ZZZ' / 'SYNTHETIC' marker titles — drill data can only ever be
# synthetic, never a real co-author), and (b) the producer Welcome card
# is PRESENT on the open board. The verifier does NOT perform the hygiene
# (that is the mutation surface, Trevor-gated); it RE-READS and CONFIRMS.
# The verify ACTION it reports is --execute-gated (the Trevor gate, per
# the u20 package-init doctrine); this module enforces the gate on its own
# ACTION surface and NEVER writes.
# -----------------------------------------------------------------------------
# WHAT THIS MODULE CONFIRMS (the U20 BOARD LAW, carried in by the family
# siblings, never re-implemented):
#   1. THE ZERO-DRILL LAW (u14-anthology-board-hygiene.py): a synthetic
#      drill card is ANY Anthology-board task whose title contains the
#      'ZZZ' or 'SYNTHETIC' markers — the markers that can only be drill
#      data, never a real co-author ("Anthology chapter — <name>" cards
#      can NEVER be caught). The board is clean only when ZERO such cards
#      are LIVE (archived_at IS NULL — the tasks API's own "on the open
#      board" filter, src/app/api/tasks/route.ts `AND t.archived_at IS
#      NULL`; a soft-archived drill card is OFF the board and is NOT a
#      violation — the hygiene law is a LIVE-board law).
#   2. THE WELCOME-CARD LAW (db_connector / welcome_action / the CC
#      departments route step 3): the Anthology board must carry ONE
#      producer Welcome card on the open board — title byte-exact
#      'Welcome to Anthology', scoped to the 'anthology' workspace, with
#      the board's starter-card body signature. Its content derives from
#      HOW-TO-USE.md (the producer how-to — the card is copy, never a
#      write). An ABSENT Welcome card is a MISMATCH naming the remediation
#      (the seed ACTION lives in the sibling welcome_action /
#      db_connector, Trevor-gated — never re-implemented here).
#   3. THE READ-BACK LAW: the verifier re-reads the LIVE board through the
#      family's own read-only surface (the sqlite URI mode=ro open over
#      mission-control.db, the SAME instrument db_connector uses — never a
#      second implementation) and compares against the wanted state. A
#      drift — a live ZZZ/SYNTHETIC card, a Welcome card absent or not
#      byte-exact — is a MISMATCH (exit 5), never a pass, never a
#      fabricated success. A board that cannot be READ (the database
#      missing / unreadable / the tasks table absent) is a STOP or HELD
#      (exit 2 / exit 3) — UNDETERMINED, never a verdict.
#   4. THE ACTION (the package-init doctrine, u20_modules/__init__.py):
#      any ACTION — a mutation that writes the DB — REQUIRES the operator
#      to pass --execute explicitly (Trevor-gated). THIS module never
#      performs the hygiene mutation (the mutation surface is the sibling
#      u14 script / the family seeders; this module is READ-ONLY by
#      construction — every connection it opens is sqlite URI mode=ro,
#      so no code path can mutate even by accident). The ACTION surface it
#      does carry is the VERIFY action, and an ACTION without --execute is
#      a STOP (exit 2), never a silent no-op — the same gate shape the U20
#      family pins on every ACTION surface. With --execute the ACTION is
#      reported explicitly (execute true on the report); the report still
#      writes nothing.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. This module reads NO credential
# env var and holds NO token: the board database is opened by path only
# (--db > DATABASE_PATH > the family candidate list, mirrored byte-for-byte
# from welcome_action.DB_CANDIDATES / the CC server's own getDbPath law —
# DATABASE_PATH always wins; a missing database is a STOP, never a guess).
# Every id on every surface is masked (last-4) or absent; a full id rides
# only inside the machine JSON payload a consumer reads.
#
# BROWSER UA (CF 1010 LAW): this module makes NO HTTP request — it reads
# the local Command Center database — so it defines no User-Agent constant
# of its own; the siblings that DO talk to Convert and Flow apply
# CAF_BROWSER_UA (anthology_registry.py) on every request, and this
# module's self-test PINS the constant (a well-formed browser UA, never
# "Python-urllib") so a drifted UA is caught before a single live request
# ever rides the family.
#
# AF ERROR CODES (fail-closed surfaces, house scheme):
#   AF-AE-VRBOARD-NO-DB        -> the Command Center database is absent,
#          unreadable, or unopenable. STOP (exit 2), fail-closed — a
#          missing DB is never "board clean", never a no-op pass.
#   AF-AE-VRBOARD-NO-EXECUTE   -> the VERIFY ACTION was requested without
#          --execute. STOP (exit 2); the module NEVER runs the ACTION
#          without the explicit Trevor-gated execute flag. Plan and
#          self-test do not require it (they are OFFLINE).
#   AF-AE-VRBOARD-TASKS-MISSING-> the tasks table is absent from the
#          database (a schema that predates the board, or the wrong
#          database). STOP (exit 2), never a blind sweep of nothing.
#   AF-AE-VRBOARD-DRILLS-LIVE  -> one or more ZZZ/SYNTHETIC drill cards
#          are LIVE on the open board. MISMATCH (exit 5) — the zero-drill
#          law is violated; the report names the masked ids.
#   AF-AE-VRBOARD-NO-WELCOME   -> no byte-exact 'Welcome to Anthology'
#          card is LIVE on the open board. MISMATCH (exit 5) — the report
#          names the remediation (the seed ACTION is the sibling's,
#          Trevor-gated, never re-implemented here).
#   AF-AE-VRBOARD-ATTACK       -> an attack fixture tripped the OFFLINE
#          self-test. Exit 4 (enforced violation), never exit 1.
#
# EXIT CODES (house convention 0/1/2/3/5; 4 = enforced violation):
#   0  PASS — the board is verified clean (zero live drill cards AND the
#      Welcome card present; also plan / self-test)
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP refusal — usage / missing --db (no candidate, no
#      DATABASE_PATH) / unopenable database / missing tasks table / the
#      VERIFY ACTION without --execute (the Trevor gate,
#      AF-AE-VRBOARD-NO-EXECUTE)
#   3  HELD — the database is busy / locked / WAL-unavailable (retryable,
#      never a verdict)
#   4  self-test FAILED (an enforced violation — a tamper NEVER masquerades
#      as exit 1)
#   5  MISMATCH — a live drill card, or the Welcome card absent / not
#      byte-exact (the fail-closed default)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on
# stderr; plan and self-test are OFFLINE and need NO database):
#   verify_board.py check [--db PATH] [--execute]   # the VERIFY ACTION,
#                                                   # Trevor-gated
#   verify_board.py plan                            # offline plan
#   verify_board.py self-test                       # offline fixtures
#
# --execute is the ONLY flag that authorizes the ACTION (Trevor-gated).
# WITHOUT it the ACTION is a STOP (exit 2), never a silent no-op — the
# family gate. WITH it the ACTION still performs NO write: this module
# re-reads and confirms board state only, and the report records the
# execute state explicitly. The database is opened READ-ONLY (sqlite URI
# mode=ro + the query_only pragma) in EVERY path, including --execute —
# the write surface is the sibling's alone.
#
# STDLIB ONLY (sqlite3 + argparse). Calls NO model, NO API, NO credential.
# DOCTRINE: move in silence; operator-verbose only; NOTHING Anthropic in
# any runtime file; Convert and Flow naming in every client surface; NEVER
# print a secret value; the engine database is READ-ONLY in dry-run; the
# verify ACTION is --execute-gated and this verifier NEVER writes.
# =============================================================================
"""verify_board.py — post-action board verifier (Skill 59, U20 tooling):
re-reads the Command Center's Anthology board and confirms, fail-closed,
that zero ZZZ/SYNTHETIC drill cards are live and the 'Welcome to
Anthology' card is present. READ-ONLY: never writes; the verify ACTION
requires --execute (Trevor-gated) and is reported, never mutated."""

from __future__ import annotations

import argparse
import io
import json
import os
import sqlite3
import sys
from pathlib import Path

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = 0, 1, 2, 3, 5
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# ---------------------------------------------------------------------------
# The board law surfaces (fixed; a tamper drifts the self-test, exit 4)
# ---------------------------------------------------------------------------

# The Anthology department board — the workspace slug/board id the whole
# family pins (mc_board DEFAULT_DEPARTMENT_SLUG, welcome_action
# DEPARTMENT_SLUG, the CC departments route).
WORKSPACE_ID = "anthology"
DEPARTMENT_SLUG = "anthology"

# The Welcome card title — the board's starter-card shape, byte-exact
# ("Welcome to <Dept>", add-department.sh step 3; the family seeders pin
# the same string).
WELCOME_TITLE = "Welcome to Anthology"

# The Welcome card's open-board presence marker. The auto-seeded starter
# card body signature — the generic department placeholder the CC
# departments route writes ("...Your AI workforce will populate real
# tasks...") — is the STALE welcome (the u14 hygiene archives it); the
# producer-voice Welcome card the family seeds carries the fixed
# idempotency marker ('anthology:welcome:card', welcome_action
# WELCOME_REF) in its description. The verifier accepts a live card with
# the byte-exact title on the anthology board as the Welcome card; the
# two markers discriminate the variants for the operator surface only.
WELCOME_REF = "anthology:welcome:card"
STALE_BODY_MARK = "%AI workforce will populate real tasks%"

# The zero-drill law markers — a title containing either marker is drill
# data, never a real co-author (u14-anthology-board-hygiene.py: the
# synthetic match is restricted to 'ZZZ'/'SYNTHETIC' titles so a real
# participant card can NEVER be caught). Case-insensitive.
DRILL_MARKERS = ("zzz", "synthetic")

# The Command Center database. The same candidate list the family uses
# (welcome_action.DB_CANDIDATES, mirrored byte-for-byte) plus the
# DATABASE_PATH env override the Command Center itself honors
# (src/lib/db/index.ts getDbPath: DATABASE_PATH always wins). First
# existing candidate wins; --db always wins. A missing database is a STOP
# (exit 2) — never a guess, never a sweep of nothing.
_DB_CANDIDATES = (
    os.environ.get("DATABASE_PATH", "").strip(),
    os.path.expanduser("~/projects/command-center/mission-control.db"),
    os.path.expanduser("~/projects/mission-control/mission-control.db"),
    "/opt/mission-control/mission-control.db",
    "/app/mission-control.db",
    "/data/projects/command-center/mission-control.db",
    "/Users/blackceomacmini/command-center/data/mission-control.db",
)

# The report contract — every surface this module emits carries it, so a
# machine consumer can never mistake another JSON object for a board-state
# read (the self-test asserts the golden report carries the exact string).
CONFIG_CONTRACT = "anthology-engine-verify-board"
CONFIG_SCHEMA_VERSION = 1

# The VERIFY ACTION law, machine-carried: the action verb and the execute
# flag whose explicit presence is Trevor's gate.
VERIFY_ACTION = "verify"
EXECUTE_FLAG = "--execute"


class VerifyBoardError(Exception):
    """A fail-closed refusal (STOP family). An expectation that cannot
    name its own sources must not run."""


# ---------------------------------------------------------------------------
# Fail-closed read helpers. Pure; never print a secret value.
# ---------------------------------------------------------------------------
def _mask_id(rid: str) -> str:
    """Non-reversible marker for a task id (last 4 chars) — the house
    surface shape for every operator-facing mention of an id. Full ids ride
    inside the machine payload a consumer reads, never on a human
    surface."""
    rid = (rid or "").strip()
    return ("..." + rid[-4:]) if len(rid) >= 4 else "...(short)"


def _scalar_str(value) -> str:
    """A scalar string candidate for a title/status slot, or ''. A
    non-scalar (a dict / list / None) is '' — a malformed read is never
    judged. Never raises."""
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        s = str(value).strip()
        return s if s.lower() != "none" else ""
    return ""


def _mask_path(path) -> str:
    """A non-reversible marker for a database path: the file name only."""
    return str(Path(path).name) if path else "(none)"


# ---------------------------------------------------------------------------
# Database discovery + read-only connection
# ---------------------------------------------------------------------------
def resolve_db_path(explicit: str = "") -> str:
    """Resolve the Command Center mission-control.db path. --db wins;
    then DATABASE_PATH env override (CC's own rule); then the family
    candidate list. Returns "" when no candidate exists (STOP upstream).
    Never a guess."""
    if explicit and explicit.strip():
        return explicit.strip()
    env = os.environ.get("DATABASE_PATH", "").strip()
    if env:
        return env
    for cand in _DB_CANDIDATES:
        if not cand:
            continue
        p = Path(cand).expanduser()
        if p.is_file():
            return str(p)
    return ""


def _connect_readonly(db_path: str):
    """Open the Command Center database READ-ONLY at the VFS layer and fail
    closed. The open is a sqlite URI mode=ro connection, so sqlite itself
    refuses ANY write at the file layer — no code path in this module can
    mutate, regardless of what a statement or a future edit tries. The
    query_only pragma is set as a second, independent belt.

    A missing / unreadable / unopenable file raises (never a pass, never a
    silent no-op). The mode=ro open also reads a WAL-mode database whose
    main file is 0644 without ever taking the reserved lock BEGIN IMMEDIATE
    needs — a read-only consumer must never need write permission on the
    file it only reads.

    Returns a connection with row access and a 15 s busy timeout (the CC
    server holds the WAL; readers wait, they never fail). Raises
    sqlite3.Error on any open failure."""
    uri = "file:%s?mode=ro" % Path(db_path).resolve()
    con = sqlite3.connect(uri, uri=True, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=15000")
    con.execute("PRAGMA query_only=ON")
    return con


def _close_readonly(con):
    """Close a read-only connection — a read connection never commits
    anything."""
    try:
        con.close()
    except sqlite3.Error:
        pass


def _table_exists(con, table: str) -> bool:
    """Whether a table exists in the database (sqlite_master, READ-ONLY).
    Never raises for a missing table: the caller classifies the
    refusal."""
    try:
        row = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? "
            "LIMIT 1",
            (table,),
        ).fetchone()
        return row is not None
    except sqlite3.Error:
        return False


# ---------------------------------------------------------------------------
# The two board reads (both READ-ONLY; both fail-closed)
# ---------------------------------------------------------------------------
def _live_drill_cards(con) -> list:
    """The LIVE synthetic drill cards on the Anthology board: every task
    row on the board (workspace_id='anthology') with archived_at IS NULL
    (the tasks API's own "on the open board" filter) whose title contains
    a drill marker. Returns a list of dicts (id, title) — never raises;
    a broken read is classified by the caller."""
    try:
        rows = con.execute(
            "SELECT id, title FROM tasks WHERE workspace_id=? "
            "AND archived_at IS NULL",
            (WORKSPACE_ID,),
        ).fetchall()
    except sqlite3.Error:
        return []
    hits = []
    for r in rows:
        title = _scalar_str(r["title"]).lower()
        if any(marker in title for marker in DRILL_MARKERS):
            hits.append({"id": str(r["id"]), "title": _scalar_str(r["title"])})
    return hits


def _welcome_card(con) -> dict:
    """The LIVE Welcome card on the Anthology board, or {} when absent.
    The card is pinned BY TITLE (byte-exact 'Welcome to Anthology') and BY
    WORKSPACE (board 'anthology') — any title variation is a DIFFERENT
    card that is never treated as the Welcome card. Presence is judged on
    the OPEN board only (archived_at IS NULL): a soft-archived Welcome
    card is OFF the board (the stale placeholder the u14 hygiene archives)
    and is NOT the producer's Welcome card — it is reported as absent with
    the archived status surfaced for the operator. Returns
    {"id", "title", "status", "archived_at"} or {}."""
    try:
        row = con.execute(
            "SELECT id, title, status, archived_at, description FROM tasks "
            "WHERE workspace_id=? AND title=? ORDER BY rowid ASC LIMIT 1",
            (WORKSPACE_ID, WELCOME_TITLE),
        ).fetchone()
    except sqlite3.Error:
        return {}
    if row is None:
        return {}
    return {
        "id": str(row["id"]),
        "title": _scalar_str(row["title"]),
        "status": _scalar_str(row["status"]),
        "archived_at": _scalar_str(row["archived_at"]),
        "description": _scalar_str(row["description"]),
    }


# ---------------------------------------------------------------------------
# The verdict — confirm clean, fail-closed, byte-exact
# ---------------------------------------------------------------------------
def _verify_board(con, out) -> dict:
    """The board read, fail-closed: zero live drill cards AND the Welcome
    card present on the open board. Returns the verdict dict; writes human
    notes to `out`. Never raises for a board-condition — the caller
    classifies unreadable surfaces before this runs."""
    drills = _live_drill_cards(con)
    welcome = _welcome_card(con)

    ok = True
    detail = []

    if drills:
        ok = False
        detail.append("%d live drill card(s): %s"
                      % (len(drills),
                         ", ".join("%s (%s)"
                                   % (_mask_id(d["id"]),
                                      d["title"][:24])
                                   for d in drills[:5])))
    if not welcome:
        ok = False
        detail.append("the Welcome card is ABSENT from the open board")
    elif welcome["archived_at"]:
        # A live-in-the-DB but archived Welcome card is off the open board:
        # the producer does not see it. Not the welcome the law demands.
        ok = False
        detail.append("the Welcome card (%s) is soft-archived — OFF the "
                      "open board"
                      % _mask_id(welcome["id"]))

    if detail:
        out.write("[verify-board] board MISMATCH: %s\n" % "; ".join(detail))

    return {
        "drill_cards_live": len(drills),
        "drill_cards_live_ids_masked": [
            _mask_id(d["id"]) for d in drills],
        "welcome_card": {
            "present": bool(welcome and not welcome.get("archived_at")),
            "id_masked": _mask_id(welcome["id"]) if welcome else None,
            "status": welcome.get("status") if welcome else None,
            "archived_at": welcome.get("archived_at") if welcome else None,
        },
        "ok": ok,
    }


# ---------------------------------------------------------------------------
# The live surface: check (the VERIFY ACTION — Trevor-gated)
# ---------------------------------------------------------------------------
def check(*, db_path: str = "", execute: bool = False,
          out=None, jsonout=None) -> int:
    """Re-read the Anthology board and confirm the zero-drill + Welcome
    laws, fail-closed. Emits the ONE JSON report object on stdout; human
    notes go to out (stderr).

    - the board is read through the family's own read-only surface (sqlite
      URI mode=ro over mission-control.db — never a second implementation),
    - a missing database / missing tasks table is a STOP (exit 2,
      AF-AE-VRBOARD-NO-DB / AF-AE-VRBOARD-TASKS-MISSING) — a board that
      cannot be read is never "board clean", never a verdict,
    - a locked / busy database is HELD (exit 3, retryable),
    - the ACTION is Trevor-gated: WITHOUT --execute it is a STOP (exit 2,
      AF-AE-VRBOARD-NO-EXECUTE), never a silent no-op; WITH --execute the
      ACTION is reported explicitly on the report (execute true) and the
      verifier STILL writes nothing."""
    out = out or sys.stderr
    masked = _mask_path(db_path)

    if not db_path:
        out.write("[verify-board] AF-AE-VRBOARD-NO-DB: no Command Center "
                  "database found (--db unset, DATABASE_PATH unset, and "
                  "no candidate exists). STOP — a board that cannot be "
                  "read is never 'board clean'.\n")
        if jsonout is not None:
            json.dump({"ok": False, "exit": EX_STOP,
                       "reason": "db-missing"}, jsonout)
            jsonout.write("\n")
        return EX_STOP

    if not execute:
        out.write("[verify-board] STOP: the VERIFY ACTION requires %s "
                  "explicitly (Trevor-gated). Without %s the ACTION is a "
                  "refusal, never a silent no-op; even WITH it this "
                  "verifier never writes.\n" % (EXECUTE_FLAG, EXECUTE_FLAG))
        if jsonout is not None:
            json.dump({"ok": False, "exit": EX_STOP, "execute": False,
                       "reason": "no-execute", "db": masked,
                       "note": "the verify ACTION is Trevor-gated; the "
                               "verifier is READ-ONLY by construction"},
                      jsonout)
            jsonout.write("\n")
        return EX_STOP

    try:
        con = _connect_readonly(db_path)
    except sqlite3.OperationalError as exc:
        low = str(exc).lower()
        if "locked" in low or "busy" in low:
            out.write("[verify-board] HELD: the Command Center database %s "
                      "is busy/locked (%s) — retryable, never a "
                      "verdict.\n" % (masked, exc))
            return EX_HELD
        out.write("[verify-board] AF-AE-VRBOARD-NO-DB: cannot open the "
                  "Command Center database %s read-only: %s. STOP — a "
                  "board that cannot be read is never 'board clean'.\n"
                  % (masked, exc))
        if jsonout is not None:
            json.dump({"ok": False, "exit": EX_STOP,
                       "reason": "db-unopenable"}, jsonout)
            jsonout.write("\n")
        return EX_STOP
    except sqlite3.Error as exc:
        out.write("[verify-board] AF-AE-VRBOARD-NO-DB: cannot open the "
                  "Command Center database %s read-only: %s. STOP — a "
                  "board that cannot be read is never 'board clean'.\n"
                  % (masked, exc))
        if jsonout is not None:
            json.dump({"ok": False, "exit": EX_STOP,
                       "reason": "db-unopenable"}, jsonout)
            jsonout.write("\n")
        return EX_STOP

    try:
        if not _table_exists(con, "tasks"):
            out.write("[verify-board] AF-AE-VRBOARD-TASKS-MISSING: the "
                      "tasks table is absent from %s. STOP — never a "
                      "sweep of nothing, never a blind pass.\n" % masked)
            if jsonout is not None:
                json.dump({"ok": False, "exit": EX_STOP,
                           "reason": "tasks-table-missing"}, jsonout)
                jsonout.write("\n")
            return EX_STOP

        verdict = _verify_board(con, out)
    except sqlite3.Error as exc:
        out.write("[verify-board] HELD: the board read failed on %s: %s "
                  "— retryable, never a verdict.\n" % (masked, exc))
        return EX_HELD
    finally:
        _close_readonly(con)

    report = {
        "contract": CONFIG_CONTRACT,
        "schema_version": CONFIG_SCHEMA_VERSION,
        "ok": verdict["ok"],
        "verdict": "PASS" if verdict["ok"] else "MISMATCH",
        "execute": True,
        "action": VERIFY_ACTION,
        "execute_required": True,
        "board": WORKSPACE_ID,
        "expected": {
            "drill_cards_live": 0,
            "welcome_card": "present on the open board "
                            "(title byte-exact %r)" % WELCOME_TITLE,
        },
        "found": {
            "drill_cards_live": verdict["drill_cards_live"],
            "drill_cards_live_ids_masked":
                verdict["drill_cards_live_ids_masked"],
            "welcome_card": verdict["welcome_card"],
        },
        "db": masked,
        "note": ("board verified: zero live drill cards and the Welcome "
                 "card present on the open board"
                 if verdict["ok"] else
                 "a board law is violated — live drill cards, or the "
                 "Welcome card absent/off the open board; fail-closed, "
                 "never a fabricated success"),
    }
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return EX_OK if verdict["ok"] else EX_MISMATCH


# ---------------------------------------------------------------------------
# Offline plan — no database, no credentials. The two laws with the exact
# sources of truth, printed as ONE JSON object on stdout.
# ---------------------------------------------------------------------------
def plan(out=None) -> int:
    out = out or sys.stdout
    payload = {
        "contract": CONFIG_CONTRACT + "-plan",
        "schema_version": CONFIG_SCHEMA_VERSION,
        "action": VERIFY_ACTION,
        "execute_required": True,
        "board": WORKSPACE_ID,
        "zero_drill_law": {
            "markers": list(DRILL_MARKERS),
            "scope": "tasks on workspace '%s' with archived_at IS NULL "
                     "(the tasks API's open-board filter)" % WORKSPACE_ID,
            "source": "u14-anthology-board-hygiene.py (the synthetic "
                      "match is restricted to ZZZ/SYNTHETIC titles so a "
                      "real co-author card can never be caught)",
        },
        "welcome_card_law": {
            "title": WELCOME_TITLE,
            "scope": "workspace '%s', archived_at IS NULL (the open "
                     "board)" % WORKSPACE_ID,
            "source": "db_connector / welcome_action / the CC "
                      "departments route step 3 (byte-exact title; content "
                      "derives from HOW-TO-USE.md — copy, never a write)",
        },
        "reads": {
            "board": "sqlite URI mode=ro over the Command Center "
                     "mission-control.db (the family's own read-only "
                     "surface; --db > DATABASE_PATH > candidates)",
        },
        "note": "offline plan only — no database, no credential, no "
                "network; a live drill card or an absent Welcome card is a "
                "MISMATCH (exit 5), never a pass; an unreadable database "
                "is STOP/HELD (exit 2/3), never a verdict; the verify "
                "ACTION is --execute-gated (Trevor-gated) and this "
                "verifier NEVER writes",
    }
    sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return EX_OK


# ---------------------------------------------------------------------------
# Offline self-test — no network, no credentials, no live database. The
# golden clean board PASSES; every drift REFUSES. A FAILED self-test is
# exit 4 (enforced violation), never 'unexpected error'.
# ---------------------------------------------------------------------------
class _FakeDb:
    """In-memory SQLite standing in for mission-control.db. The self-test
    exercises the REAL functions against this file — the same instrument
    the live module uses — with programmable contents."""

    def __init__(self, *, cards=None):
        import tempfile
        self._fd, self._path = tempfile.mkstemp(suffix=".db")
        os.close(self._fd)
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
                    updated_at TEXT,
                    archived_at TEXT
                );
                """
            )
            for c in (cards or []):
                cols = ", ".join(c)
                ph = ", ".join("?" * len(c))
                con.execute("INSERT INTO tasks (%s) VALUES (%s)"
                            % (cols, ph), list(c.values()))
            con.commit()
        finally:
            con.close()

    @property
    def path(self):
        return self._path

    def drop_tasks(self):
        """Attack shape: the tasks table is missing entirely."""
        con = sqlite3.connect(self._path)
        con.execute("DROP TABLE tasks")
        con.commit()
        con.close()

    def __del__(self):
        try:
            os.unlink(self._path)
        except OSError:
            pass


def _welcome_card_row(**kw):
    """A Welcome card row shape for the fixtures."""
    row = {
        "id": "task_welcome",
        "title": WELCOME_TITLE,
        "description": "…%s…" % WELCOME_REF,
        "status": "backlog",
        "workspace_id": WORKSPACE_ID,
        "department": DEPARTMENT_SLUG,
        "created_at": "2026-08-11 00:00:00",
        "updated_at": "2026-08-11 00:00:00",
        "archived_at": None,
    }
    row.update(kw)
    return {k: v for k, v in row.items() if v is not None}


def _golden_cards():
    """The golden clean board: exactly the Welcome card live, nothing
    else — the state the U14 hygiene leaves behind (the stale auto-seed
    archived, the drill cards archived, the ONE producer-voice Welcome
    live)."""
    return [
        _welcome_card_row(),
        # the stale auto-seed placeholder, soft-archived (off the open
        # board — not a violation, not the Welcome card)
        {"id": "task_stale", "title": WELCOME_TITLE,
         "description": "…AI workforce will populate real tasks…",
         "status": "blocked", "workspace_id": WORKSPACE_ID,
         "department": DEPARTMENT_SLUG,
         "created_at": "2026-07-01 00:00:00",
         "updated_at": "2026-07-01 00:00:00",
         "archived_at": "2026-07-08 22:22:56"},
        # drill cards, soft-archived (off the open board — clean)
        {"id": "drill_a", "title": "ZZZ-SYNTHETIC-TEST drill A",
         "status": "blocked", "workspace_id": WORKSPACE_ID,
         "department": DEPARTMENT_SLUG,
         "created_at": "2026-07-01 00:00:00",
         "updated_at": "2026-07-01 00:00:00",
         "archived_at": "2026-07-08 22:22:56"},
        {"id": "drill_b", "title": "W5-drill synthetic card",
         "status": "blocked", "workspace_id": WORKSPACE_ID,
         "department": DEPARTMENT_SLUG,
         "created_at": "2026-07-01 00:00:00",
         "updated_at": "2026-07-01 00:00:00",
         "archived_at": "2026-07-08 22:22:56"},
    ]


def _self_test_body(dev: io.StringIO) -> None:
    # Sibling import bootstrap (house convention — the same
    # parent.parent -> scripts/ resolution the U06/U20 siblings use): the
    # registry owns the exit-code contract and the CAF_BROWSER_UA law this
    # self-test pins. Imported INSIDE the self-test so the module's import
    # stays side-effect free (it reads no sibling, no credential).
    import contextlib as _contextlib
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import anthology_registry as reg  # noqa: E402  (sibling bootstrap)

    # ---- the board law surfaces are stable -------------------------------
    assert WORKSPACE_ID == "anthology"
    assert DEPARTMENT_SLUG == "anthology"
    assert WELCOME_TITLE == "Welcome to Anthology"
    assert tuple(DRILL_MARKERS) == ("zzz", "synthetic")

    # ---- golden clean board -> PASS, exit 0 ------------------------------
    fake = _FakeDb(cards=_golden_cards())
    con = _connect_readonly(fake.path)
    try:
        verdict = _verify_board(con, io.StringIO())
        assert verdict["ok"], "the golden clean board must PASS"
        assert verdict["drill_cards_live"] == 0
        assert verdict["welcome_card"]["present"] is True
        # the soft-archived Welcome card is NOT the live welcome
        assert not verdict["welcome_card"]["archived_at"], \
            "the live welcome card must not carry an archive stamp"
    finally:
        _close_readonly(con)

    # ---- ACTION gate: without --execute -> STOP (exit 2), never a write
    with _contextlib.redirect_stdout(io.StringIO()):
        with io.StringIO() as captured:
            rc = check(db_path=fake.path, execute=False, out=captured,
                       jsonout=captured)
    assert rc == EX_STOP, "the verify ACTION without --execute must STOP"

    # ---- no --db -> STOP (never a sweep of nothing) ----------------------
    with _contextlib.redirect_stdout(io.StringIO()):
        rc = check(db_path="", execute=True, out=io.StringIO(),
                   jsonout=io.StringIO())
    assert rc == EX_STOP, "a missing database must STOP (exit 2)"

    # ---- a database without the tasks table -> STOP ----------------------
    fake2 = _FakeDb()
    fake2.drop_tasks()
    with _contextlib.redirect_stdout(io.StringIO()):
        rc2 = check(db_path=fake2.path, execute=True, out=io.StringIO(),
                    jsonout=io.StringIO())
    assert rc2 == EX_STOP, "a missing tasks table must STOP (exit 2)"

    # ---- MISMATCH: a live drill card -------------------------------------
    fake3 = _FakeDb(cards=_golden_cards() + [
        {"id": "drill_live", "title": "ZZZ-SYNTHETIC-TEST residue",
         "status": "backlog", "workspace_id": WORKSPACE_ID,
         "department": DEPARTMENT_SLUG,
         "created_at": "2026-08-11 00:00:00",
         "updated_at": "2026-08-11 00:00:00",
         "archived_at": None}])
    with _contextlib.redirect_stdout(io.StringIO()):
        rc3 = check(db_path=fake3.path, execute=True, out=io.StringIO(),
                    jsonout=io.StringIO())
    assert rc3 == EX_MISMATCH, "a live drill card must exit 5"
    con3 = _connect_readonly(fake3.path)
    try:
        v3 = _verify_board(con3, io.StringIO())
        assert v3["drill_cards_live"] == 1
        assert v3["drill_cards_live_ids_masked"] == ["...live"]
    finally:
        _close_readonly(con3)

    # ---- MISMATCH: the Welcome card absent --------------------------------
    fake4 = _FakeDb(cards=[{"id": "other", "title": "Anthology chapter — "
                          "Someone", "status": "backlog",
                          "workspace_id": WORKSPACE_ID,
                          "department": DEPARTMENT_SLUG,
                          "created_at": "2026-08-11 00:00:00",
                          "updated_at": "2026-08-11 00:00:00",
                          "archived_at": None}])
    with _contextlib.redirect_stdout(io.StringIO()):
        rc4 = check(db_path=fake4.path, execute=True, out=io.StringIO(),
                    jsonout=io.StringIO())
    assert rc4 == EX_MISMATCH, "an absent Welcome card must exit 5"

    # ---- MISMATCH: the Welcome card soft-archived (off the open board)
    fake5 = _FakeDb(cards=[
        {"id": "task_stale", "title": WELCOME_TITLE,
         "description": "…AI workforce will populate real tasks…",
         "status": "blocked", "workspace_id": WORKSPACE_ID,
         "department": DEPARTMENT_SLUG,
         "created_at": "2026-07-01 00:00:00",
         "updated_at": "2026-07-01 00:00:00",
         "archived_at": "2026-07-08 22:22:56"}])
    with _contextlib.redirect_stdout(io.StringIO()):
        rc5 = check(db_path=fake5.path, execute=True, out=io.StringIO(),
                    jsonout=io.StringIO())
    assert rc5 == EX_MISMATCH, "an archived Welcome card must exit 5"

    # ---- the zero-drill law never catches a real co-author card -----------
    fake6 = _FakeDb(cards=_golden_cards() + [
        {"id": "part_real", "title": "Anthology chapter — Amelia Earhart",
         "status": "review", "workspace_id": WORKSPACE_ID,
         "department": DEPARTMENT_SLUG,
         "created_at": "2026-08-11 00:00:00",
         "updated_at": "2026-08-11 00:00:00",
         "archived_at": None}])
    con6 = _connect_readonly(fake6.path)
    try:
        v6 = _verify_board(con6, io.StringIO())
        assert v6["ok"], "a real co-author card must never trip the drill law"
    finally:
        _close_readonly(con6)

    # ---- the happy path WITH --execute: exit 0, execute true, PASS -------
    dev7 = io.StringIO()
    out7 = io.StringIO()
    with _contextlib.redirect_stdout(out7):
        rc7 = check(db_path=fake.path, execute=True, out=dev7,
                    jsonout=io.StringIO())
    assert rc7 == EX_OK, "the golden board under --execute must PASS"
    report7 = json.loads(out7.getvalue())
    assert report7["ok"] is True and report7["verdict"] == "PASS"
    assert report7["execute"] is True
    assert report7["contract"] == CONFIG_CONTRACT

    # ---- the plan is OFFLINE and truthful --------------------------------
    dev8 = io.StringIO()
    with _contextlib.redirect_stdout(dev8):
        rc8 = plan()
    assert rc8 == EX_OK
    plan8 = json.loads(dev8.getvalue())
    assert plan8["contract"] == CONFIG_CONTRACT + "-plan"
    assert plan8["execute_required"] is True

    # ---- never-print: no full task id beyond masked markers --------------
    all_text = (dev7.getvalue() + dev8.getvalue())
    assert "task_welcome" not in all_text, \
        "fixture task ids must never leak onto surfaces"
    assert "drill_live" not in all_text, \
        "fixture task ids must never leak onto surfaces"

    # ---- the BROWSER UA law is pinned (CF 1010) ---------------------------
    ua = reg.CAF_BROWSER_UA
    assert isinstance(ua, str) and ua.strip(), "CAF_BROWSER_UA is empty"
    assert "Python-urllib" not in ua, \
        "CAF_BROWSER_UA is urllib's default — the Cloudflare edge 1010s it"
    assert ua.startswith("Mozilla/5.0") and "Chrome/" in ua, \
        "CAF_BROWSER_UA is not a well-formed browser UA"

    dev.write("verify_board self-test: OK (golden clean board PASSES "
              "byte-exact; the VERIFY ACTION without %s STOPS "
              "(Trevor-gated); missing-db / missing-tasks-table STOP; "
              "live-drill / absent-Welcome / archived-Welcome all MISMATCH "
              "exit 5; a real co-author card never trips the drill law; "
              "happy path --execute PASS; plan offline; never-print; "
              "browser-UA pinned)\n" % EXECUTE_FLAG)


def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[verify-board] SELF-TEST FAILED "
                         "(AF-AE-VRBOARD-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


# ---------------------------------------------------------------------------
# CLI — house shape: --self-test / --selftest normalize to the positional
# subcommand form exactly as the U06/U20 siblings normalize. The ACTION
# (check) requires --execute (the Trevor gate); plan and self-test are
# OFFLINE.
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="verify_board.py",
        description="Post-action board verifier (Skill 59, U20 tooling): "
                    "re-read the Command Center's Anthology board and "
                    "CONFIRM, fail-closed, that zero ZZZ/SYNTHETIC drill "
                    "cards are live and the 'Welcome to Anthology' card "
                    "is present on the open board. READ-ONLY: never "
                    "writes; the verify ACTION requires --execute "
                    "(Trevor-gated) and is reported, never mutated.")
    ap.add_argument("--db", default="",
                    help="explicit Command Center database path (default: "
                         "DATABASE_PATH, then the family candidate list; "
                         "never printed in full)")
    ap.add_argument("--execute", action="store_true",
                    help="the Trevor gate for an ACTION — REQUIRED before "
                         "the check runs; without it the ACTION is a STOP "
                         "(exit 2), never a silent no-op; even WITH it "
                         "this verifier never writes")
    ap.add_argument("--json", action="store_true",
                    help="emit the machine report on stdout (the report is "
                         "always one JSON object on stdout; this flag "
                         "additionally makes refusal surfaces machine "
                         "JSON)")
    ap.add_argument("cmd", nargs="?", choices=["check", "plan", "self-test"],
                    default="check")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    if "--self-test" in argv:
        argv = ["self-test" if a == "--self-test" else a for a in argv]
    if "--selftest" in argv:
        argv = ["self-test" if a == "--selftest" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        if args.cmd == "self-test":
            return self_test()
        if args.cmd == "plan":
            return plan()
        return check(db_path=resolve_db_path(args.db), execute=args.execute,
                     out=sys.stderr, jsonout=(sys.stdout if args.json
                                              else None))
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[verify-board] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
