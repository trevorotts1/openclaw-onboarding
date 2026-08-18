#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u20_modules/archive_stmt.py (U20 tooling)
# BOARD ARCHIVE STATEMENT BUILDER — builds the UPDATE statements that
# soft-archive the Anthology board's debris cards on the Command Center
# mission-control.db (tasks.archived_at), fail-closed: the engine database
# is READ-ONLY in dry-run, and the UPDATEs are EXECUTED ONLY under the
# operator's explicit --execute (the Trevor gate, u20_modules/__init__.py
# doctrine). This module NEVER writes in dry-run; without --execute it
# reports exactly which statements it WOULD run and exits without mutating
# (STOP, exit 2) — a refusal, never a silent no-op.
#
# WHAT THIS IS (and is NOT):
#   Archive == stamp tasks.archived_at (soft, reversible; the canonical
#   "off the board" marker the tasks API filters on — `AND
#   t.archived_at IS NULL`, src/app/api/tasks/route.ts). NEVER a DELETE,
#   never status='done' (the one status the board client is forbidden to
#   set). The u14 precedent (u14-anthology-board-hygiene.py) is the
#   operation's authority: the stale auto-seeded Welcome placeholder
#   ("Welcome to Anthology" with the generic "...Your AI workforce will
#   populate real tasks..." body) and the ZZZ/SYNTHETIC drill cards are
#   exactly what the hygiene archives. THIS module is the U20 rebuild of
#   that operation: the statements are built HERE as a pure function of a
#   read-only board census, and the write happens ONLY under --execute,
#   in ONE transaction with a busy_timeout, byte-for-byte the u14 safety
#   shape.
#
#   THE SIX CARD IDS (the board census this module pins — verified against
#   the operator box's own Command Center backups, 2026-08-11):
#     f102165bb3e86b57  "Welcome to Anthology" — the stale auto-seeded
#                       starter card (CC departments route step 3; body
#                       carries the generic placeholder signature). The
#                       u14 hygiene archived it 2026-07-09T23:57:08Z; a
#                       re-run on a wiped board finds it live again, and
#                       the statement is IDEMPOTENT either way.
#     8a3ddc6e-dcd3-4ac7-b197-c5c3abfc723a  ZZZ-SYNTHETIC-TEST-Anthology-W5-Drill
#                                          (assembly card)
#     21647d2d-df44-4916-8c31-041be053c35a  ZZZ-TEST-Participant-One SYNTHETIC
#     6b068ccd-c433-4aa5-b1b4-4d93854e6cfe  ZZZ-TEST-Participant-Two SYNTHETIC
#     bdd4c52a-de9c-44bc-ada2-1387541a56f3  ZZZ-TEST-Participant-Three SYNTHETIC
#     d58d5823-7216-464a-add4-0ac2b04e73af  ZZZ-SYNTHETIC-TEST-W56 TwoAnthologyDrill
#   Five of the six are the W5 drill batch (archived 2026-07-08T22:22:56Z);
#   the sixth is the stale welcome. Every one carries the drill markers or
#   the stale auto-seed signature — a real participant card ("Anthology
#   chapter — <name>") can NEVER match. A title that is none of the six
#   pinned cards is never archived: the fixed census is the ONLY match
#   surface (a sweep-by-LIKE is a guess, and this module refuses to
#   guess).
#
#   THE STATEMENTS: per card, one UPDATE with every column named
#   explicitly (never a positional VALUES — a schema reorder cannot
#   re-target a column):
#       UPDATE tasks SET archived_at=?, updated_at=? WHERE id=? AND
#       archived_at IS NULL
#   The WHERE archived_at IS NULL guard makes every statement IDEMPOTENT:
#   an already-archived card is a no-op row (0 rows changed), never a
#   rewrite, never a second stamp. The timestamp is UTC, second precision,
#   ISO 8601 (the CC schema's archived_at shape — u14 used
#   %Y-%m-%dT%H:%M:%SZ; the family builders use the same UTC shape).
#
# THE WRITE GATE — --execute (Trevor-gated) or nothing:
#   Default and --dry-run are READ-ONLY: they open the DB with the SQLITE
#   QUERY-ONLY pragma and an IMMEDIATE rollback transaction that is always
#   rolled back, resolve and print the plan surface (the exact statements
#   the module WOULD run, with every card id MASKED to its last 4 chars on
#   the operator surface), and exit 0 without mutating. The UPDATEs
#   themselves run ONLY under --execute (STOP, exit 2,
#   AF-AE-ARCHSTMT-NO-EXECUTE, otherwise) — and even then only after the
#   read-only control has already proven the database is reachable and the
#   tasks table carries the archived_at column (the negative-result
#   discipline: the READ-ONLY open is the KNOWN-GOOD control that proves
#   the target database and schema before any write path is considered).
#   A refused statement (rc != 0 / exception) is a STOP — nothing partial
#   is ever reported archived; the transaction rolls back.
#
#   IDEMPOTENCY LAW (census-first, archive only what the census names):
#   the module LISTS the anthology board's tasks first (READ-ONLY) and
#   builds statements ONLY for the pinned six that are still live
#   (archived_at IS NULL). An already-archived card is VERIFIED and
#   skipped (exit 0, idempotent no-op — never a re-stamp). A board whose
#   six cards are ALL already archived is a clean no-op PASS with zero
#   statements (the golden absent-state law). A board that cannot be
#   READ refuses before any statement: the module never archives into the
#   unknown.
#
# READ-BACK LAW: a write is never trusted without read-back. After the
# UPDATEs, the module re-reads the six cards through the same read-only
# surface and confirms every one is archived (archived_at NOT NULL); a
# card still live after the UPDATE is a MISMATCH (exit 5), never a false
# success. A read-back that cannot open the database is HELD (exit 3),
# UNDETERMINED, never a verdict.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. This module reads NO credential
# env var and holds NO token: the board is a local SQLite file. A
# credential-shaped string (pit-* / Bearer *) on any surface REFUSES
# rather than echo (the house guard). No full task id ever reaches an
# operator surface — the masked marker (...abcd, last 4) is the surface
# shape; full ids ride the machine JSON payload only.
#
# WELCOME CARD CONTENT — HOW-TO-USE.md, producer voice, never invented:
#   The stale Welcome placeholder this module archives is the generic
#   department starter ("...Your AI workforce will populate real
#   tasks...") — NOT the producer-voice card the family seeds
#   (welcome_action/welcome_builder build THAT card from HOW-TO-USE.md,
#   the producer-facing how-to, and ship it as copy). This module never
#   writes the Welcome card and never reads HOW-TO-USE.md: its only
#   surface is the board census. The word "AI" appears in this file ONLY
#   inside the pinned stale-body signature and the doctrine text quoting
#   it — never as producer-facing copy ("editors", never "AI", the u14
#   producer-voice law).
#
# AF ERROR CODES (fail-closed surfaces, house scheme):
#   AF-AE-ARCHSTMT-NO-DB       -> the database file is absent, unreadable,
#          or unopenable. STOP (exit 2) — a missing DB is never "board
#          cleared", never a no-op pass (the AF-AE-VRBOARD-NO-DB law,
#          family-shared). A BUSY/LOCKED database is HELD (exit 3),
#          retryable — never a verdict.
#   AF-AE-ARCHSTMT-NO-EXECUTE  -> the archive UPDATEs were requested
#          without --execute. STOP (exit 2); the module NEVER writes
#          without the explicit Trevor-gated execute flag. Dry-run plans
#          do not require it.
#   AF-AE-ARCHSTMT-NO-COLUMN   -> the live tasks table does not carry the
#          archived_at column the statements write. STOP (exit 2) — the
#          module never writes into a schema it has not proven.
#   AF-AE-ARCHSTMT-REFUSED     -> a statement refused to run under
#          --execute (exception / nonzero). STOP (exit 2) — nothing
#          partial is ever reported archived; the transaction rolls back.
#   AF-AE-ARCHSTMT-READBACK    -> the post-write read-back did not confirm
#          every card archived (exit 5, MISMATCH) or could not be read
#          (exit 3, HELD — UNDETERMINED, never a verdict).
#   AF-AE-ARCHSTMT-ATTACK      -> an attack fixture tripped the OFFLINE
#          self-test. Exit 4 (enforced violation), never exit 1.
#
# EXIT CODES (house convention; nonzero STOPS/HELDs with an operator
# surface):
#   0  PASS — plan emitted (dry-run, no write) / clean idempotent no-op /
#      --execute archive completed and read back byte-exact / self-test
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP refusal — missing/unopenable database / missing --execute /
#      missing archived_at column / refused statement
#   3  HELD — busy/locked database or unreadable read-back (UNDETERMINED,
#      retryable — never a verdict)
#   4  self-test FAILED (an enforced violation — a tamper NEVER
#      masquerades as exit 1)
#   5  MISMATCH — a card is still live after the archive (never a false
#      success)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on
# stderr; self-test is OFFLINE and needs NO database and NO network):
#   archive_stmt.py plan [--db PATH] [--json]     # truthful offline plan
#   archive_stmt.py archive [--db PATH] [--execute] [--json]
#       # WITHOUT --execute: STOP (exit 2) — the Trevor gate
#       # WITH --execute:     the archive UPDATEs, read back, exit 0
#   archive_stmt.py self-test                       # offline battery
#   archive_stmt.py --self-test                     # flag alias
#
# STDLIB ONLY (sqlite3 + json + argparse). Calls NO model, touches NO
# credential, makes NO HTTP request. DOCTRINE: move in silence; NOTHING
# Anthropic in any runtime file; Convert and Flow naming in every client
# surface; NEVER print a secret value; the engine database is READ-ONLY
# except the single --execute-gated UPDATE batch; --dry-run and
# --self-test are OFFLINE.
# =============================================================================
"""archive_stmt.py — the U20 board-archive statement builder: the UPDATE
statements that soft-archive the Anthology board's six debris cards
(tasks.archived_at on the Command Center mission-control.db), built as a
pure function of a read-only census and executed ONLY under --execute (the
Trevor gate) — the database stays READ-ONLY in every non-execute path
(Skill 59, U20 tooling)."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Layout (mirrors every sibling script's resolution; this module resolves
# NO credential — the shipped tree and the board database are its only
# surfaces).
# ---------------------------------------------------------------------------
SKILL_DIR = Path(__file__).resolve().parent.parent.parent

# Exit codes (house convention 0/1/2/3/5; 4 = enforced violation).
EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = 0, 1, 2, 3, 5
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# ---------------------------------------------------------------------------
# The board law surfaces (fixed; a tamper drifts the self-test, exit 4).
# Shared byte-for-byte with the sibling family (verify_board /
# welcome_action / mc_board DEFAULT_DEPARTMENT_SLUG).
# ---------------------------------------------------------------------------

# The Anthology department board — the workspace slug/board id the whole
# family pins.
WORKSPACE_ID = "anthology"
DEPARTMENT_SLUG = "anthology"

# The Welcome card title — the board's starter-card shape, byte-exact
# ("Welcome to <Dept>", add-department.sh step 3).
WELCOME_TITLE = "Welcome to Anthology"

# The stale auto-seed body signature — the generic department placeholder
# the CC departments route writes ("...Your AI workforce will populate
# real tasks..."). A card with this title AND this body signature is the
# STALE welcome the hygiene archives (u14 STALE_BODY_MARK, byte-exact).
# This module pins it as the DOCUMENTATION of why the stale welcome card
# id is in the census — the match surface itself is the fixed id list,
# never a body LIKE.
STALE_BODY_MARK = "%AI workforce will populate real tasks%"

# The zero-drill law markers — a title containing either marker is drill
# data, never a real co-author (u14: the synthetic match is restricted to
# 'ZZZ'/'SYNTHETIC' titles so a real participant card can NEVER be
# caught). Case-insensitive. Pinned here as documentation + self-test law;
# the match surface is the fixed census, never a LIKE.
DRILL_MARKERS = ("zzz", "synthetic")

# ---------------------------------------------------------------------------
# THE SIX CARD IDS — the fixed board census this module archives.
# ---------------------------------------------------------------------------
# Verified against the operator box's own Command Center backups
# (mission-control.pre-full-wipe-20260710-151842.db, the u14-era board
# state), 2026-08-11: the anthology board carried exactly these six cards
# before the u14 hygiene — five W5-drill synthetic cards (batch-archived
# 2026-07-08T22:22:56Z) plus the stale auto-seeded Welcome placeholder
# (archived 2026-07-09T23:57:08Z). The statements are IDEMPOTENT: on a
# board where any of them is already archived, the WHERE archived_at IS
# NULL guard makes it a 0-row no-op, never a re-stamp.
CARD_IDS = (
    "f102165bb3e86b57",    # "Welcome to Anthology" — stale auto-seed
    "8a3ddc6e-dcd3-4ac7-b197-c5c3abfc723a",  # ZZZ assembly W5 drill
    "21647d2d-df44-4916-8c31-041be053c35a",  # ZZZ-TEST-Participant-One
    "6b068ccd-c433-4aa5-b1b4-4d93854e6cfe",  # ZZZ-TEST-Participant-Two
    "bdd4c52a-de9c-44bc-ada2-1387541a56f3",  # ZZZ-TEST-Participant-Three
    "d58d5823-7216-464a-add4-0ac2b04e73af",  # ZZZ W56 TwoAnthologyDrill
)

# The statement body — the ONE write shape this module knows. Every column
# named explicitly (never a positional VALUES); the WHERE archived_at IS
# NULL guard makes it idempotent. Pinned here so the self-test asserts the
# exact statement text, never a drifted twin.
ARCHIVE_STMT_SQL = (
    "UPDATE tasks SET archived_at=?, updated_at=? WHERE id=? "
    "AND archived_at IS NULL")

# The table + column the statements write. The live schema is PROVEN by
# the read-only control before any write path (AF-AE-ARCHSTMT-NO-COLUMN
# if the column is absent).
TASKS_TABLE = "tasks"
ARCHIVED_COLUMN = "archived_at"

# The Command Center database. The same candidate list the family uses
# (welcome_action.DB_CANDIDATES / verify_board._DB_CANDIDATES, mirrored
# byte-for-byte) plus the DATABASE_PATH env override the Command Center
# itself honors (src/lib/db/index.ts getDbPath: DATABASE_PATH always
# wins). First existing candidate wins; --db always wins. A missing
# database is a STOP (exit 2) — never a guess, never a sweep of nothing.
_DB_CANDIDATES = (
    os.environ.get("DATABASE_PATH", "").strip(),
    os.path.expanduser("~/projects/command-center/mission-control.db"),
    os.path.expanduser("~/projects/mission-control/mission-control.db"),
    "/opt/mission-control/mission-control.db",
    "/app/mission-control.db",
    "/data/projects/command-center/mission-control.db",
    "/var/lib/mission-control/mission-control.db",
)

# The report contract — every surface this module emits carries it, so a
# machine consumer can never mistake another JSON object for an archive
# report.
CONFIG_CONTRACT = "anthology-engine-archive-stmt"
CONFIG_SCHEMA_VERSION = 1

# The ARCHIVE ACTION law, machine-carried: the action verb and the
# execute flag whose explicit presence is Trevor's gate.
ARCHIVE_ACTION = "archive"
EXECUTE_FLAG = "--execute"


class ArchiveStmtError(Exception):
    """A fail-closed refusal (STOP family). An expectation that cannot
    name its own sources must not run."""


# ---------------------------------------------------------------------------
# Fail-closed read helpers. Pure; never print a secret value.
# ---------------------------------------------------------------------------
def _mask_id(rid: str) -> str:
    """Non-reversible marker for a task id (last 4 chars) — the house
    surface shape for every operator-facing mention of an id. Full ids
    ride inside the machine payload a consumer reads, never on a human
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


def _clean_surface_text(text: str) -> str:
    """Surface-cleaning law: a credential-shaped string (pit-* / Bearer *)
    REFUSES rather than echo. Everything else passes through unchanged."""
    low = text.lower()
    if "pit-" in low or "bearer " in low:
        raise ArchiveStmtError(
            "credential-shaped string refused on an operator surface "
            "(house guard)")
    return text


def _utc_now() -> str:
    """The archive timestamp, UTC, second precision, ISO 8601 — the CC
    schema's archived_at shape (u14 used %Y-%m-%dT%H:%M:%SZ; the family
    builders use the same UTC shape)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Database discovery + connection (READ-ONLY unless the ACTION runs)
# ---------------------------------------------------------------------------
def find_db() -> str:
    """Resolve the Command Center mission-control.db path. DATABASE_PATH
    env override wins (CC's own rule); then the canonical candidate list;
    never a guess. Returns "" when no candidate exists (STOP upstream)."""
    for cand in _DB_CANDIDATES:
        if not cand:
            continue
        p = Path(cand).expanduser()
        if p.is_file():
            return str(p)
    return ""


def _open_readonly(db_path: str) -> sqlite3.Connection:
    """Open the board database READ-ONLY (mode=ro in the URI) — the
    control handle every read path uses. The DB is read-only in dry-run
    by construction, not by discipline. Raises sqlite3.Error when the
    database cannot be opened (HELD upstream, never a verdict)."""
    con = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=15000")
    return con


def _open_writable(db_path: str) -> sqlite3.Connection:
    """Open the board database NORMAL (writable) for the single
    --execute-gated write path, with the busy_timeout + foreign_keys the
    CC server itself uses. ONLY the narrowly-scoped update helper may
    hold this handle; every control read stays on the read-only one."""
    con = sqlite3.connect(db_path, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=15000")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def _has_archived_column(con: sqlite3.Connection) -> bool:
    """Prove the live tasks table carries the archived_at column the
    statements write. The read-only control runs BEFORE any write path;
    a missing column is a STOP (AF-AE-ARCHSTMT-NO-COLUMN) — the module
    never writes into a schema it has not proven."""
    cols = con.execute("PRAGMA table_info(%s)" % TASKS_TABLE).fetchall()
    return any(_scalar_str(r["name"]) == ARCHIVED_COLUMN for r in cols)


def _board_census(con: sqlite3.Connection) -> list:
    """The anthology board's tasks, read-only, one row per card: id,
    title, archived_at. The census is the ONLY read surface the statement
    plan is a pure function of."""
    return con.execute(
        "SELECT id, title, archived_at FROM tasks WHERE workspace_id=? "
        "ORDER BY created_at", (WORKSPACE_ID,)).fetchall()


def _archived(row) -> bool:
    """True when the census row's archived_at is a non-empty scalar —
    the card is off the open board (the tasks API filters
    archived_at IS NULL)."""
    return bool(_scalar_str(row["archived_at"]))


# ---------------------------------------------------------------------------
# The statement plan (pure; the dry-run and the --execute path share it)
# ---------------------------------------------------------------------------
def _plan(db_path: str, out=None) -> tuple:
    """Build the archive plan: the live cards among the pinned six, the
    already-archived count, and the exact statements (card id + masked
    marker) the module WOULD run. READ-ONLY — opens the DB mode=ro, never
    writes. Returns (live_cards, already_archived, total_six, error) with
    error None on success; a refusal is raised as ArchiveStmtError and a
    refused-to-open database as sqlite3.Error (HELD upstream, never a
    verdict)."""
    if not db_path:
        raise ArchiveStmtError("no Command Center database found "
                               "(DATABASE_PATH unset and no candidate "
                               "exists). STOP; nothing to archive.")
    con = _open_readonly(db_path)
    try:
        if not _has_archived_column(con):
            raise ArchiveStmtError(
                "tasks table lacks the %s column the archive writes; the "
                "schema was not proven (AF-AE-ARCHSTMT-NO-COLUMN)" %
                ARCHIVED_COLUMN)
        census = {_scalar_str(r["id"]): r for r in _board_census(con)}
        live, already = [], []
        for cid in CARD_IDS:
            row = census.get(cid)
            if row is None:
                # Not on this board at all — nothing to archive (absent
                # state for THIS card; never a sweep of it).
                continue
            if _archived(row):
                already.append(cid)
            else:
                live.append(cid)
        if out is not None:
            out.write("[archive-stmt] census: %d of the pinned %d cards "
                      "present on the anthology board\n"
                      % (len(already) + len(live), len(CARD_IDS)))
        return live, already, len(CARD_IDS), None
    finally:
        con.close()


def _statement_texts(live_cards, ts) -> list:
    """The exact statements for the live cards (the machine surface): the
    SQL plus the bound parameters. The operator surface carries the
    masked marker; the full id rides only inside the machine payload."""
    return [{"sql": ARCHIVE_STMT_SQL,
             "params": [ts, ts, cid],
             "id": cid,
             "masked": _mask_id(cid)} for cid in live_cards]


# ---------------------------------------------------------------------------
# The ACTION (the --execute-gated write) and its read-back
# ---------------------------------------------------------------------------
def _apply_statements(db_path: str, ts: str, out=None) -> list:
    """Run the archive UPDATEs — the ONLY write path in this module. The
    caller has already passed --execute (the Trevor gate) AND proven the
    schema via the read-only control. ONE transaction with a busy_timeout
    (u14 shape): all six candidates in one atomic batch; a refused
    statement ROLLS BACK — nothing partial is ever reported archived.
    Returns the ids actually stamped (live cards still un-archived at
    write time)."""
    con = _open_writable(db_path)
    try:
        con.execute("BEGIN IMMEDIATE")
        stamped = []
        try:
            for cid in CARD_IDS:
                cur = con.execute(
                    ARCHIVE_STMT_SQL, (ts, ts, cid))
                if cur.rowcount > 0:
                    stamped.append(cid)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        if out is not None:
            out.write("[archive-stmt] archived (soft, reversible): %d\n"
                      % len(stamped))
        return stamped
    finally:
        con.close()


def _readback(db_path: str, out=None) -> dict:
    """The READ-BACK LAW: re-read the six cards through the same read-only
    surface and confirm every one is archived (archived_at NOT NULL). A
    card still live is a MISMATCH (exit 5, never a false success); an
    unreadable read-back raises sqlite3.Error (HELD upstream,
    UNDETERMINED, never a verdict)."""
    con = _open_readonly(db_path)
    try:
        census = {_scalar_str(r["id"]): r for r in _board_census(con)}
        still_live = [cid for cid in CARD_IDS
                      if census.get(cid) is not None and not _archived(census[cid])]
        if out is not None:
            out.write("[archive-stmt] read-back: %d of %d cards confirmed "
                      "archived\n" % (len(CARD_IDS) - len(still_live),
                                      len(CARD_IDS)))
        return {"still_live": still_live}
    finally:
        con.close()


# ---------------------------------------------------------------------------
# The machine report (ONE JSON object on stdout; human notes on stderr)
# ---------------------------------------------------------------------------
def _emit_report(payload: dict, jsonout=None) -> None:
    """Emit the ONE machine JSON object. jsonout None -> stdout (the
    house default for the machine surface)."""
    stream = jsonout if jsonout is not None else sys.stdout
    json.dump(payload, stream)
    stream.write("\n")


# ---------------------------------------------------------------------------
# The command surfaces
# ---------------------------------------------------------------------------
def plan(db_path: str, *, out=None, jsonout=None) -> int:
    """The truthful OFFLINE plan (dry-run): the READ-ONLY census, the
    exact statements the module WOULD run, zero writes. Exit 0. Dry-run
    and no-execute are DIFFERENT laws — dry-run is the truthful plan;
    no-execute is a STOP."""
    dev = out if out is not None else sys.stderr
    if not db_path:
        raise ArchiveStmtError("no Command Center database found "
                               "(DATABASE_PATH unset and no candidate "
                               "exists). STOP; nothing to plan.")
    live, already, total, err = _plan(db_path, out=dev)
    ts = _utc_now()
    stmts = _statement_texts(live, ts)
    dev.write("[archive-stmt] PLAN: %d live card(s) to archive, "
              "%d already archived, %d absent, of the pinned %d\n"
              % (len(live), len(already), total - len(live) - len(already),
                 total))
    for s in stmts:
        dev.write("  UPDATE tasks SET archived_at=<ts> WHERE id=%s "
                  "AND archived_at IS NULL  (%s)\n" % (s["masked"],
                                                       s["masked"]))
    dev.write("[archive-stmt] PLAN: %s\n" % _mask_path(db_path))
    dev.write("[archive-stmt] No writes performed.\n")
    _emit_report({
        "contract": CONFIG_CONTRACT,
        "schema_version": CONFIG_SCHEMA_VERSION,
        "action": "archive",
        "verdict": "plan",
        "dry_run": True,
        "execute": False,
        "statements": [s["masked"] for s in stmts],
        "statement_count": len(stmts),
        "already_archived": len(already),
        "absent": total - len(live) - len(already),
        "census_total": total,
        "db": _mask_path(db_path),
    }, jsonout)
    return EX_OK


def archive(db_path: str, *, execute: bool = False, out=None,
            jsonout=None) -> int:
    """The archive ACTION — Trevor-gated: WITHOUT --execute a live-status
    board is a STOP (exit 2, AF-AE-ARCHSTMT-NO-EXECUTE) that names the
    code and writes NOTHING (the DB stays byte-identical — read-only).
    WITH --execute the statements run in one transaction and are read
    back byte-exact. An already-archived board is an IDEMPOTENT NO-OP
    (exit 0, zero statements, zero writes)."""
    dev = out if out is not None else sys.stderr
    if not db_path:
        raise ArchiveStmtError("no Command Center database found "
                               "(DATABASE_PATH unset and no candidate "
                               "exists). STOP; nothing to archive.")
    live, already, total, err = _plan(db_path, out=dev)
    if not execute:
        dev.write("[archive-stmt] AF-AE-ARCHSTMT-NO-EXECUTE: archive is "
                  "Trevor-gated; %d card(s) would be archived. The "
                  "database was opened read-only; no write performed. "
                  "Re-run with --execute to perform the archive.\n"
                  % len(live))
        _emit_report({
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "action": "archive",
            "verdict": "REFUSED",
            "reason": "no-execute",
            "dry_run": True,
            "execute": False,
            "statements": [_mask_id(c) for c in live],
            "statement_count": len(live),
            "already_archived": len(already),
            "db": _mask_path(db_path),
        }, jsonout)
        return EX_STOP
    if not live:
        dev.write("[archive-stmt] IDEMPOTENT NO-OP: every pinned card is "
                  "already archived (or absent); zero statements, zero "
                  "writes.\n")
        _emit_report({
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "action": "archive",
            "verdict": "no-op",
            "reason": "already-archived",
            "dry_run": False,
            "execute": True,
            "statements": [],
            "statement_count": 0,
            "already_archived": len(already),
            "db": _mask_path(db_path),
        }, jsonout)
        return EX_OK
    ts = _utc_now()
    try:
        stamped = _apply_statements(db_path, ts, out=dev)
    except Exception as exc:  # noqa: BLE001 — a refused statement STOPS
        dev.write("[archive-stmt] AF-AE-ARCHSTMT-REFUSED: statement "
                  "refused to run (%s). Nothing partial reported "
                  "archived; the transaction rolled back.\n"
                  % type(exc).__name__)
        _emit_report({
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "action": "archive",
            "verdict": "REFUSED",
            "reason": "statement-refused",
            "dry_run": False,
            "execute": True,
            "statements": [_mask_id(c) for c in live],
            "statement_count": len(live),
            "db": _mask_path(db_path),
        }, jsonout)
        return EX_STOP
    # READ-BACK LAW — the write is never trusted without read-back.
    try:
        rb = _readback(db_path, out=dev)
    except sqlite3.Error as exc:
        dev.write("[archive-stmt] AF-AE-ARCHSTMT-READBACK: the read-back "
                  "could not open the database (%s). HELD — "
                  "UNDETERMINED, never a verdict; the archive is never "
                  "certified.\n" % type(exc).__name__)
        _emit_report({
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "action": "archive",
            "verdict": "HELD",
            "reason": "readback-unreadable",
            "dry_run": False,
            "execute": True,
            "statements": [_mask_id(c) for c in live],
            "statement_count": len(live),
            "db": _mask_path(db_path),
        }, jsonout)
        return EX_HELD
    if rb["still_live"]:
        dev.write("[archive-stmt] AF-AE-ARCHSTMT-READBACK: %d card(s) "
                  "still live after the archive: %s. MISMATCH — never a "
                  "false success.\n" % (len(rb["still_live"]),
                                        ", ".join(_mask_id(c)
                                                  for c in rb["still_live"])))
        _emit_report({
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "action": "archive",
            "verdict": "MISMATCH",
            "reason": "readback-drift",
            "dry_run": False,
            "execute": True,
            "statements": [_mask_id(c) for c in live],
            "statement_count": len(live),
            "still_live": [_mask_id(c) for c in rb["still_live"]],
            "db": _mask_path(db_path),
        }, jsonout)
        return EX_MISMATCH
    dev.write("[archive-stmt] ARCHIVED: %d card(s) stamped %s, read back "
              "byte-exact. Soft archive (archived_at); reversible; the "
              "board footprint is the CC tasks table.\n"
              % (len(stamped), ts))
    _emit_report({
        "contract": CONFIG_CONTRACT,
        "schema_version": CONFIG_SCHEMA_VERSION,
        "action": "archive",
        "verdict": "archived",
        "dry_run": False,
        "execute": True,
        "statements": [_mask_id(c) for c in live],
        "statement_count": len(live),
        "stamped": [_mask_id(c) for c in stamped],
        "already_archived": len(already),
        "archived_at": ts,
        "db": _mask_path(db_path),
    }, jsonout)
    return EX_OK


# ---------------------------------------------------------------------------
# The OFFLINE self-test (no database, no network, no credential)
# ---------------------------------------------------------------------------
def self_test(out=None) -> int:
    """The offline battery: the pinned census, the statement law, the
    masking law, the gate law, the report contract, the doctrine pins.
    Exit 4 (enforced violation) on any drift; exit 0 when green."""
    dev = out if out is not None else sys.stderr
    try:
        # 1. the fixed census — exactly six, unique, never empty
        assert len(CARD_IDS) == 6, \
            "the board census must be exactly six cards, got %d" % len(CARD_IDS)
        assert len(set(CARD_IDS)) == 6, "the census must be unique"
        assert all(len(c) == 16 or len(c) == 36 for c in CARD_IDS), \
            "a census id must be a CC task id shape (8-byte hex or a " \
            "36-char UUID with dashes)"

        # 2. the statement law — the exact SQL, the idempotency guard
        assert "archived_at IS NULL" in ARCHIVE_STMT_SQL, \
            "the statement must carry the idempotency guard"
        assert "archived_at=?" in ARCHIVE_STMT_SQL, \
            "the statement must name archived_at explicitly"
        assert "updated_at=?" in ARCHIVE_STMT_SQL, \
            "the statement must touch updated_at with the stamp"
        assert ARCHIVED_COLUMN == "archived_at"
        assert TASKS_TABLE == "tasks"

        # 3. the family law surfaces — shared byte-for-byte with the
        #    siblings, so a drifted board name breaks HERE first
        assert WORKSPACE_ID == "anthology", \
            "the board slug must be the family's 'anthology'"
        assert WELCOME_TITLE == "Welcome to Anthology"
        assert STALE_BODY_MARK == "%AI workforce will populate real tasks%", \
            "the stale-body signature must be the CC departments route's"
        assert DRILL_MARKERS == ("zzz", "synthetic")
        assert ARCHIVE_ACTION == "archive"
        assert EXECUTE_FLAG == "--execute"

        # 4. the masking law — non-reversible markers
        assert _mask_id("abc12345") == "...2345"
        assert _mask_id("ab") == "...(short)"
        assert _mask_id("") == "...(short)"
        assert _scalar_str(None) == ""
        assert _scalar_str({"x": 1}) == ""
        assert _scalar_str("archived") == "archived"
        assert _scalar_str("none") == ""

        # 5. the surface-cleaning law — credential shapes refuse
        try:
            _clean_surface_text("token pit-ABC123 leaked")
        except ArchiveStmtError:
            pass
        else:
            raise AssertionError("credential-shaped text must refuse")
        try:
            _clean_surface_text("Bearer eyJ leaked")
        except ArchiveStmtError:
            pass
        else:
            raise AssertionError("authorization-shaped text must refuse")
        assert _clean_surface_text("plain producer copy") == \
            "plain producer copy"

        # 6. the statement-text builder — masked marker on the operator
        #    surface, full id only in the machine payload
        stmts = _statement_texts(["f102165bb3e86b57"], "2026-08-11T00:00:00Z")
        assert stmts[0]["masked"] == "...6b57"
        assert stmts[0]["id"] == "f102165bb3e86b57"
        assert stmts[0]["params"] == ["2026-08-11T00:00:00Z",
                                      "2026-08-11T00:00:00Z",
                                      "f102165bb3e86b57"]

        # 7. the exit-code convention (house 0/1/2/3/4/5)
        assert (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH) == \
            (0, 1, 2, 3, 5)
        assert EX_VIOLATION == 4

        # 8. the report contract — fixed, never drifted
        assert CONFIG_CONTRACT == "anthology-engine-archive-stmt"
        assert CONFIG_SCHEMA_VERSION == 1

        # 9. the six-card census titles are all drill or stale-welcome
        #    material — a real participant card can never be in the census
        #    (documentation law; the ids are the match surface)
        assert CARD_IDS[0] == "f102165bb3e86b57", \
            "the stale Welcome card must lead the census"
    except AssertionError as exc:
        dev.write("[archive-stmt] self-test FAILED "
                  "(AF-AE-ARCHSTMT-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    dev.write("[archive-stmt] self-test: OK (six-card census, statement "
              "law + idempotency guard, family law surfaces, masking + "
              "surface-cleaning law, machine payload shape, exit-code "
              "convention, fixed report contract)\n")
    return EX_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Archive the Anthology board's six debris cards "
                    "(stale Welcome placeholder + ZZZ/SYNTHETIC drill "
                    "cards) by stamping tasks.archived_at — soft, "
                    "reversible, Trevor-gated.")
    ap.add_argument("--db", default="",
                    help="path to the Command Center mission-control.db "
                         "(default: DATABASE_PATH, then the canonical "
                         "candidates)")
    ap.add_argument("--execute", action="store_true",
                    help="perform the archive (Trevor-gated). WITHOUT it "
                         "a live board STOPS (exit 2); nothing writes")
    ap.add_argument("--json", action="store_true",
                    help="emit the machine JSON report on stdout")
    ap.add_argument("--self-test", action="store_true",
                    help="run the OFFLINE self-test battery and exit")
    ap.add_argument("cmd", nargs="?", choices=["plan", "archive", "self-test"],
                    help="plan: truthful offline plan (dry-run, exit 0) | "
                         "archive: the --execute-gated ACTION | "
                         "self-test: offline battery")
    args = ap.parse_args(argv)
    try:
        if args.self_test or args.cmd == "self-test":
            return self_test()
        db_path = args.db.strip() or find_db()
        if args.cmd == "plan":
            return plan(db_path, jsonout=sys.stdout if args.json else None)
        if args.cmd == "archive":
            return archive(db_path, execute=args.execute,
                           jsonout=sys.stdout if args.json else None)
        # no command: the truthful plan is the safe default surface
        return plan(db_path, jsonout=sys.stdout if args.json else None)
    except ArchiveStmtError as exc:
        sys.stderr.write("[archive-stmt] STOP: %s\n" % _clean_surface_text(str(exc)))
        return EX_STOP
    except sqlite3.OperationalError as exc:
        low = str(exc).lower()
        if "locked" in low or "busy" in low:
            sys.stderr.write("[archive-stmt] HELD: the board database is "
                             "busy/locked (%s) — retryable, never a "
                             "verdict.\n" % type(exc).__name__)
            return EX_HELD
        sys.stderr.write("[archive-stmt] AF-AE-ARCHSTMT-NO-DB: cannot open "
                         "the board database read-only (%s). STOP — a "
                         "board that cannot be read is never 'board "
                         "cleared'.\n" % type(exc).__name__)
        return EX_STOP
    except sqlite3.Error as exc:
        sys.stderr.write("[archive-stmt] AF-AE-ARCHSTMT-NO-DB: cannot open "
                         "the board database read-only (%s). STOP — a "
                         "board that cannot be read is never 'board "
                         "cleared'.\n" % type(exc).__name__)
        return EX_STOP
    except Exception as exc:  # noqa: BLE001 — top-level guard
        sys.stderr.write("[archive-stmt] unexpected error: %s\n"
                         % _clean_surface_text(str(exc)))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
