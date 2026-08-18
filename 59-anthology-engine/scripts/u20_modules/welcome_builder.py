#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u20_modules/welcome_builder.py (U20 tooling)
# PRODUCER WELCOME CARD BUILDER — the producer-language Welcome card copy
# derived from HOW-TO-USE.md, built as a READY-TO-RUN sqlite INSERT, fail-
# closed: the engine database is READ-ONLY in dry-run, and the INSERT is
# EXECUTED ONLY under the operator's explicit --execute (the Trevor gate,
# u20_modules/__init__.py doctrine). This module NEVER writes in dry-run;
# without --execute it reports exactly what it WOULD insert and exits
# without mutating (STOP, exit 2).
#
# WHAT THIS IS (and is NOT):
#   HOW-TO-USE.md is the engine's producer-facing guide — the ONLY producer-
#   language source of truth (CHANGELOG 0.1.0: "HOW-TO-USE.md (producer,
#   Convert and Flow naming)"). The Welcome card that greets a producer on
#   the board must speak the producer's language: "you are the producer, the
#   owner of this Command Center", co-authors are "participants", everything
#   happens on the board and through the forms, never a script. This module
#   turns that guide into the card's body COPY — by exact section order —
#   and builds the single INSERT statement that lands it.
#
#   THE CARD (the object being built — WHAT the statement names):
#     card_type   'welcome'            — the U20 producer Welcome card type
#     card_key    'welcome::producer'  — the card's own stable id
#     title       'Welcome to the Anthology Engine'
#     body        the producer-language copy rendered from HOW-TO-USE.md
#     source_file 'HOW-TO-USE.md'      — the copy's provenance marker
#     source_sha256                   — sha256 of HOW-TO-USE.md (digest only;
#                                       drift between the card and the guide
#                                       is DETECTABLE, never silent)
#     built_at                        — UTC timestamp when the INSERT was built
#     engine_version                  — skill-version.txt at build time
#     builder       'welcome_builder.py' — the one author of the card
#
#   THE STATEMENT: a single INSERT with all columns named explicitly (never
#   a positional VALUES — a schema reorder cannot re-target a column),
#   executed against the engine's OWN state database. The write is FAIL-
#   CLOSED on both sides of the gate:
#     * The database is opened in the READ-ONLY uri mode ('mode=ro') at ALL
#       times — dry-run AND --execute — so a bug in THIS module can never
#       mutate the ledger through the control handle; under --execute the
#       write opens the database normally ONLY inside the narrowly-scoped
#       insert helper, after the read-only control has already proven the
#       schema and the key's absence (the negative-result discipline: the
#       READ-ONLY open is the KNOWN-GOOD control that proves the target
#       database is reachable and schema-consistent before any write path
#       is even considered).
#     * WITHOUT --execute the INSERT is NEVER executed: the module prints the
#       exact statement it WOULD execute (the fail-closed "report what it
#       WOULD do and exit without mutating" contract) and STOPS (exit 2,
#       AF-AE-WELCOME-NO-EXECUTE).
#   The card lands in the `meta` key-value table — the engine's OWN key-
#   value surface (anthology_state.py schema: meta(key TEXT PRIMARY KEY,
#   value TEXT); _set_meta is its sole domain writer, upserting on
#   conflict). The Welcome card is board COPY with a stable key: writing it
#   as a meta row makes the INSERT idempotent by construction — the same
#   key re-inserted is an upsert, never a duplicate card and never a second
#   row. The module proves the meta table's existence and the key's absence
#   from the READ-ONLY open BEFORE any write path; a database that cannot
#   be read is a REFUSAL, never a blind insert.
#
# THE WRITE PATH (the ONLY place this module ever mutates — --execute only):
#   1. build the INSERT from HOW-TO-USE.md (offline, pure)
#   2. READ-ONLY open of the engine state database (mode=ro) — the gate's
#      own control: if the read-only open fails, NO write is even attempted
#      (STOP, exit 2) — the write is never trusted into the unknown
#   3. the read-only control proves the meta table exists (schema pinned
#      byte-exact) and the card key is ABSENT (a card that already exists
#      is an IDEMPOTENT NO-OP, exit 0, never a duplicate write; a foreign
#      value under the card's own key is a MISMATCH, never overwritten)
#   4. only then, and ONLY under --execute, the module opens the database
#      normally and executes the single prepared statement
#   5. READ-BACK LAW — a write is never trusted without read-back: the
#      module re-opens READ-ONLY and must read back the card's key with a
#      matching value before anything is reported inserted (exit 5 on a
#      missing read-back, never a false success)
#
# WHY sqlite (not a flat file): the engine state database is the ledger's
# mirror (anthology_state.py is the SOLE domain writer; this module never
# touches a domain table — the card is a meta row). A flat file would
# sidestep the engine's own consistency surface (WAL, meta schema, the
# house mirror). The card is board copy with a stable key — meta is its
# home, and the INSERT is built the same way the house builds every
# statement: named columns, one parameter per value, never
# string-interpolated SQL.
#
# CONTENT LAW (what the card body MAY and MAY NOT say):
#   * The card body is the guide's OWN copy, rendered verbatim: the title
#     line, the intro paragraph, and the six sections IN EXACT DOCUMENT
#     ORDER, each heading byte-exact. This module ADDS NOTHING and DROPS
#     NOTHING: no section is invented, no section is elided, no word is
#     authored here. The renderer is the ONLY place a heading maps to a
#     heading, and the self-test pins the section order against the source
#     headings byte-exact.
#   * The producer-language LAW is enforced, not described — by pinning the
#     document's own producer vocabulary: the body MUST mention
#     'participant' / 'participants' (the producer's co-authors are
#     participants, never contributors, never users) and MUST carry the
#     Convert and Flow naming (the client-facing platform name, the
#     engine's standing doctrine). A source edit that breaks either pin
#     FAILS the build (exit 5), never ships.
#   * Every value that is placed into the statement is escaped by the
#     database driver itself (one parameter per value — sqlite3
#     parameterization, the house rule: SQL is never string-interpolated),
#     so a literal apostrophe in the guide's copy (e.g. "editor's
#     introduction") is DATA, never syntax.
#
# CREDENTIAL DOCTRINE: this module holds NO credential and resolves NONE.
# It reads HOW-TO-USE.md and skill-version.txt from the shipped tree and
# opens the engine state database by path only. It never reads process env
# for a secret (no PIT label, no location label, no token is ever resolved,
# printed, or held — the card is board copy; a Welcome card cannot leak a
# secret it never holds). It performs NO HTTP requests, so it defines NO
# User-Agent constant of its own: the browser UA that defeats the
# Cloudflare edge (CF error 1010) is CAF_BROWSER_UA, owned by
# anthology_registry.py and applied by ITS clients (CafClient) — this
# module's only surfaces are the local database and the local guide.
#
# AF ERROR CODES (fail-closed surfaces, house scheme):
#   AF-AE-WELCOME-SOURCE-UNREADABLE -> HOW-TO-USE.md is missing or unreadable.
#          STOP (exit 2) — a card that cannot see its law never fabricates a
#          pass. A source unreadable in DRY-RUN is the same refusal (the
#          dry-run is the offline PLAN, not a lesser build).
#   AF-AE-WELCOME-SOURCE-DRIFT      -> the guide's section headings no longer
#          match the pinned section law (a heading renamed, dropped, or
#          reordered), or the title line is not the guide's '# ' title.
#          MISMATCH (exit 5) — the card body renders from the guide BY
#          EXACT SECTION ORDER, so a drifted heading structure means the
#          card can silently contradict the guide.
#   AF-AE-WELCOME-CONTENT-VIOLATION -> a content-law break: 'participant' /
#          'participants' absent from the card body, or the Convert and
#          Flow naming absent. MISMATCH (exit 5) — the producer language
#          is enforced, never described.
#   AF-AE-WELCOME-NO-EXECUTE        -> the INSERT was requested without
#          --execute. STOP (exit 2) — the Trevor gate; never a silent no-op
#          and never a silent write.
#   AF-AE-WELCOME-DB-UNREADABLE     -> the engine state database cannot be
#          opened READ-ONLY, or its schema carries no meta table. STOP
#          (exit 2) — the gate's own control: the write is never trusted
#          into the unknown.
#   AF-AE-WELCOME-DB-MISMATCH       -> the live meta schema is not the
#          engine's pinned meta schema, or a foreign value already sits
#          under the card's own key. MISMATCH (exit 5) — never a blind
#          insert, never a blind overwrite, never a fabricated state.
#   AF-AE-WELCOME-INSERT-REFUSED    -> the INSERT itself failed under
#          --execute (read-only filesystem, locked database, schema drift).
#          STOP (exit 2) or HELD (exit 3, locked/busy) per class — a
#          refused write is NEVER reported as inserted.
#   AF-AE-WELCOME-READBACK-MISMATCH -> after a successful INSERT under
#          --execute, the read-back (the READ-ONLY re-open) did not return
#          the card's key with a matching value. MISMATCH (exit 5) —
#          nothing is ever reported inserted without read-back.
#   AF-AE-WELCOME-ATTACK            -> an attack fixture tripped the OFFLINE
#          self-test. Exit 4 (enforced violation), never exit 1.
#
# EXIT CODES (house convention; nonzero STOPS/HELDs with an operator
# surface; the engine database is READ-ONLY in every non-execute path):
#   0  verified success — idempotent no-op (card already present) / the
#      INSERT executed under --execute and read back / plan / self-test
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP refusal — usage error / HOW-TO-USE.md unreadable / the state
#      database unreadable or schema-less / a genuine scope-style refusal /
#      the INSERT without --execute (AF-AE-WELCOME-NO-EXECUTE)
#   3  HELD — a retryable database condition (locked / busy); the module
#      NEVER retries a refused write and never reports it inserted
#   4  self-test FAILED — an assertion in the OFFLINE self-test tripped
#      (AF-AE-WELCOME-* family). A tamper NEVER masquerades as exit 1
#   5  data or read-back mismatch — source drift / content-law violation /
#      a foreign row under the card key / an insert refused / a read-back
#      missing (AF-AE-WELCOME-* family); the fail-closed default
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on stderr):
#   welcome_builder.py build            # offline: build the INSERT, print the
#                                       # exact statement WITHOUT executing it
#                                       # (AF-AE-WELCOME-NO-EXECUTE, exit 2)
#   welcome_builder.py build --execute  # Trevor-gated: build, read-only
#                                       # control, execute the ONE INSERT,
#                                       # read back — all in the same run
#   welcome_builder.py plan             # offline: what build WOULD do, with
#                                       # the masked card id and the body
#                                       # fingerprint (sha256) — nothing read
#                                       # from the database, nothing written
#   welcome_builder.py self-test        # offline golden + attack battery
#
# STDLIB ONLY (sqlite3 + json + hashlib + argparse). Calls NO model, touches
# NO credential, makes NO HTTP request. DOCTRINE: move in silence; NOTHING
# Anthropic in any runtime file; Convert and Flow naming in every client
# surface; NEVER print a secret value; the engine database is READ-ONLY
# except the single --execute-gated INSERT; --dry-run and --self-test are
# OFFLINE.
# =============================================================================
"""welcome_builder.py — the producer-language Welcome card INSERT builder:
HOW-TO-USE.md becomes the card's body copy by exact section order, the card
lands in the engine state database's meta table under the stable key
'welcome::producer', and the INSERT is executed ONLY under --execute (the
Trevor gate) — the database stays READ-ONLY in every non-execute path
(Skill 59, U20 tooling)."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Layout (mirrors every sibling script's resolution; this module resolves
# NO credential — the shipped tree and the state database are its only
# surfaces).
# ---------------------------------------------------------------------------
SKILL_DIR = Path(__file__).resolve().parent.parent.parent
HOW_TO_USE = SKILL_DIR / "HOW-TO-USE.md"
SKILL_VERSION_FILE = SKILL_DIR / "skill-version.txt"

# Exit codes (house convention 0/1/2/3/5; 4 = enforced violation).
EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = 0, 1, 2, 3, 5
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# ---------------------------------------------------------------------------
# The card contract (WHAT the INSERT builds; the law this module pins).
# ---------------------------------------------------------------------------
# The card's stable id. The KEYING LAW (contact_id::anthology_id) governs
# participant keys; a BOARD card is not a ledger row — its own stable id
# carries no '::' between real subjects, so 'welcome::producer' (one token
# before the delimiter) can never collide with a participant key.
CARD_KEY = "welcome::producer"
CARD_TYPE = "welcome"
CARD_TITLE = "Welcome to the Anthology Engine"
CARD_SOURCE_FILE = "HOW-TO-USE.md"
CARD_BUILDER = "welcome_builder.py"

# The engine state database file name, agreed with anthology_state /
# gate_engine / mc_board (the sole domain writer is anthology_state.py —
# this module never touches a domain table; the card is a meta row).
STATE_DB_NAME = "anthology_state.db"

# The card's home table: the engine's OWN key-value surface. The meta table
# schema is pinned here and proven by the read-only control BEFORE any write
# path (AF-AE-WELCOME-DB-MISMATCH if the live schema disagrees).
META_TABLE = "meta"
# The meta table's shape law. sqlite stores DDL as the engine's schema
# wrote it (anthology_state.py's executescript renders the columns with
# the engine's own whitespace — verified live, 2026-08-11 — and without
# the 'IF NOT EXISTS' clause), so the pinned comparison is the shape
# NORMALIZED to a single space: the byte-exact law is the engine's OWN
# column contract (key TEXT PRIMARY KEY, value TEXT), never sqlite's
# storage formatting.
META_SCHEMA_SQL = (
    "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
META_SCHEMA_NORMALIZED = (
    "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")

def _normalize_ddl(ddl: str) -> str:
    """Normalize a DDL string to the shape-law comparison form: ALL
    whitespace is removed (both sides are stripped the same way), so the
    comparison is whitespace-agnostic. sqlite stores DDL with the author's
    own whitespace (the live engine schema renders the columns with its
    own indentation, verified 2026-08-11), so the law compares the pure
    token shape — the byte-exact law is the engine's own column contract
    (key TEXT PRIMARY KEY, value TEXT), never the formatting."""
    return "".join(ddl.split())

# The producer-language LAW the card body is checked against (enforced,
# never described): 'participant' / 'participants' MUST appear (the
# producer's co-authors are participants), and the Convert and Flow naming
# MUST ride the card body (the client-facing platform name). The words are
# matched on word boundaries — the guide's own headings can never be
# false-flagged.
REQUIRED_WORDS = ("participant", "participants")
REQUIRED_PHRASE = ("convert", "and", "flow")

# ---------------------------------------------------------------------------
# The section content law (pinned by the self-test): HOW-TO-USE.md's OWN
# headings, byte-exact, in EXACT document order. The card body renders from
# the guide in this order — title line, intro paragraph, then the six
# sections verbatim; a heading renamed, dropped, or reordered is
# AF-AE-WELCOME-SOURCE-DRIFT (exit 5).
# ---------------------------------------------------------------------------
SOURCE_HEADINGS = (
    "What the engine does for you",
    "Where you work: the Anthology board",
    "What your participants see",
    "Assembling the anthology",
    "The platform",
    "Good to know",
)

# ---------------------------------------------------------------------------
# SQL (house style: named columns, one parameter per value — the driver
# escapes every value; SQL is never string-interpolated).
# ---------------------------------------------------------------------------
INSERT_SQL = (
    "INSERT INTO meta(key, value) VALUES (?, ?) "
    "ON CONFLICT(key) DO UPDATE SET value = excluded.value")

SELECT_SQL = "SELECT value FROM meta WHERE key = ?"


# ---------------------------------------------------------------------------
# Pure build (offline: the guide and the version file are the only inputs).
# ---------------------------------------------------------------------------
def _sha256_bytes(raw: bytes) -> str:
    """Deterministic sha256 hex digest of the given bytes."""
    return hashlib.sha256(raw).hexdigest()


def _build_card_body(text: str) -> str:
    """Render the card body from HOW-TO-USE.md's own copy: the title line,
    the intro paragraph, and the document's sections verbatim, in EXACT
    order, with the document's OWN headings (verbatim, never invented).
    The producer language is the guide's own — this function only carries
    it. Raises ValueError (mapped to the AF-AE-WELCOME-SOURCE-DRIFT family
    by the caller) when the guide drifted from the pinned section law — a
    drifted guide NEVER ships a card."""
    lines = text.splitlines()
    # The title line — the guide's own first line — leads the card.
    title = lines[0].strip() if lines else ""
    if not title.startswith("# "):
        raise ValueError("first line is not the '# ' title")

    body_lines = [title]
    intro = []                # the intro paragraph (title .. first heading)
    pending_heading = None
    pending_body = []
    seen = []

    def flush():
        nonlocal pending_heading, pending_body
        if pending_heading is not None:
            body_lines.append("")
            body_lines.append("## %s" % pending_heading)
            body_lines.extend(pending_body)
            seen.append(pending_heading)
            pending_heading = None
            pending_body = []

    for ln in lines[1:]:
        stripped = ln.strip()
        if stripped.startswith("## "):
            flush()
            heading = stripped[3:].strip()
            if heading not in SOURCE_HEADINGS:
                raise ValueError("heading %r not in the pinned section "
                                 "law" % heading)
            pending_heading = heading
        elif pending_heading is None:
            # Verbatim copy between the title and the first heading (the
            # guide's intro paragraph). Rendered as-is, nothing invented.
            intro.append(ln)
        else:
            pending_body.append(ln)
    flush()

    # Render the intro verbatim (right after the title, before the
    # sections) — the document's own opening words.
    if intro:
        body_lines.append("")
        body_lines.extend(intro)

    # The section law is a FULL set, not a subset: every pinned heading must
    # be present, exactly once, in the pinned order.
    if set(seen) != set(SOURCE_HEADINGS):
        missing = sorted(set(SOURCE_HEADINGS) - set(seen))
        extra = sorted(set(seen) - set(SOURCE_HEADINGS))
        raise ValueError("section law violated: missing %s, extra %s"
                         % (missing or "[]", extra or "[]"))
    if seen != list(SOURCE_HEADINGS):
        raise ValueError("section order drifted: %s" % seen)

    return "\n".join(body_lines).rstrip() + "\n"


def _tokens(lower: str) -> list:
    """Lowercased word tokens with punctuation stripped — the surface the
    content-law checks match on (word boundaries, never substrings)."""
    return [w.strip(".,;:!?'\"()[]") for w in lower.split()]


def _check_content_law(body: str) -> None:
    """The producer-language LAW, enforced (never described): the body MUST
    mention 'participant' / 'participants' (the producer's co-authors) and
    MUST carry the Convert and Flow naming (the client-facing platform
    name). Matched on word boundaries. Raises ValueError on a violation."""
    lower = body.lower()
    words = [w for w in _tokens(lower) if w]
    if not (REQUIRED_WORDS[0] in words or REQUIRED_WORDS[1] in words):
        raise ValueError("content-law violation: the card body must mention "
                         "participant(s), the producer's co-authors")
    phrase = tuple(REQUIRED_PHRASE)
    for i in range(len(words) - len(phrase) + 1):
        if tuple(words[i:i + len(phrase)]) == phrase:
            return
    raise ValueError("content-law violation: the card body must carry the "
                     "Convert and Flow naming (the client-facing platform)")


def _read_guide() -> tuple[str, str]:
    """Read HOW-TO-USE.md (the producer guide) and skill-version.txt from
    the shipped tree. Raises OSError when either is missing or unreadable —
    a card that cannot see its law never fabricates a pass."""
    raw = HOW_TO_USE.read_bytes()
    text = raw.decode("utf-8")
    try:
        version = SKILL_VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        version = "(skill-version.txt unreadable)"
    return text, version


def build_card(guide_text: str, version: str,
               built_at: str) -> dict:
    """Build the Welcome card record from the guide's own copy. PURE and
    OFFLINE: no database, no credential, no network. The card body renders
    from HOW-TO-USE.md in its EXACT section order (the section law, pinned
    by the self-test) and the content law is enforced BEFORE any statement
    is built — a drifted guide NEVER ships a card."""
    body = _build_card_body(guide_text)
    _check_content_law(body)
    return {
        "card_type": CARD_TYPE,
        "card_key": CARD_KEY,
        "title": CARD_TITLE,
        "body": body,
        "source_file": CARD_SOURCE_FILE,
        "source_sha256": _sha256_bytes(guide_text.encode("utf-8")),
        "built_at": built_at,
        "engine_version": version,
        "builder": CARD_BUILDER,
    }


def build_insert(card: dict) -> tuple[str, tuple]:
    """The ONE statement this module ever executes: a single INSERT into the
    meta table with all columns named explicitly (never a positional
    VALUES), one parameter per value (the driver escapes every value — SQL
    is never string-interpolated). The card body ships verbatim in the
    payload; its sha256 rides the card record so a tampered body is
    detectable end-to-end."""
    payload = json.dumps(card, ensure_ascii=False, sort_keys=True)
    return INSERT_SQL, (CARD_KEY, payload)


# ---------------------------------------------------------------------------
# READ-ONLY database control (the gate's own known-good control: the write
# is never trusted into the unknown — the engine database is READ-ONLY in
# every non-execute path, and even under --execute the write is preceded by
# the read-only control and followed by the read-only read-back).
# ---------------------------------------------------------------------------
def _state_db_path(state_dir: str) -> Path:
    """The engine state database path for the given state directory."""
    return Path(state_dir).expanduser() / STATE_DB_NAME


def _open_readonly(db: Path) -> sqlite3.Connection:
    """Open the engine state database READ-ONLY (sqlite uri mode=ro — a
    bug in this module can NEVER mutate the ledger through this handle).
    Returns the connection; raises sqlite3.Error when the database is
    missing or unreadable (the caller maps that to a STOP/HELD refusal,
    never a blind insert)."""
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=5000")
    return con


def _meta_schema(con: sqlite3.Connection) -> str | None:
    """The meta table's live DDL, read from the sqlite schema (READ-ONLY).
    None when the table does not exist."""
    row = con.execute(
        "SELECT sql FROM sqlite_schema WHERE type='table' AND name=?",
        (META_TABLE,)).fetchone()
    return row["sql"] if row is not None else None


def _prove_schema(con: sqlite3.Connection, out=None) -> bool:
    """The schema control: the live meta DDL must be the engine's OWN meta
    DDL (pinned byte-exact). A missing table, or a table whose DDL drifted
    from the pinned law, is a REFUSAL (AF-AE-WELCOME-DB-MISMATCH) — the
    card is never inserted into an unknown schema. READ-ONLY."""
    out = out or sys.stderr
    ddl = _meta_schema(con)
    if ddl is None:
        out.write("[welcome-builder] AF-AE-WELCOME-DB-MISMATCH: the engine "
                  "state database has no meta table; the Welcome card's "
                  "home does not exist (the ledger mirror was never "
                  "bootstrapped). Nothing inserted.\n")
        return False
    if _normalize_ddl(ddl) != _normalize_ddl(META_SCHEMA_NORMALIZED):
        out.write("[welcome-builder] AF-AE-WELCOME-DB-MISMATCH: the live "
                  "meta schema drifted from the pinned law. Nothing "
                  "inserted.\n")
        return False
    return True


def _card_present(con: sqlite3.Connection) -> str | None:
    """READ-ONLY: the card's current stored value under CARD_KEY, or None
    when the card is absent. A present-and-identical card is the idempotent
    no-op; a present-but-foreign value under the card's own key is a
    MISMATCH (never overwritten)."""
    row = con.execute(SELECT_SQL, (CARD_KEY,)).fetchone()
    return row["value"] if row is not None else None


# ---------------------------------------------------------------------------
# The two live surfaces: build (Trevor-gated insert) and plan (offline).
# ---------------------------------------------------------------------------
def build_action(state_dir: str, *, execute: bool = False,
                 out=None, jsonout=None) -> int:
    """Build the Welcome card INSERT from HOW-TO-USE.md and — ONLY under
    --execute — execute it, then read it back. Without --execute the exact
    statement is reported and NOTHING is written (AF-AE-WELCOME-NO-EXECUTE,
    exit 2). The engine database is READ-ONLY in every non-execute path;
    even under --execute the write is preceded by the READ-ONLY control and
    followed by the READ-ONLY read-back."""
    out = out or sys.stderr
    db = _state_db_path(state_dir)

    # -- 1. build (offline, pure — the guide is the only input) -------------
    try:
        guide_text, version = _read_guide()
        card = build_card(guide_text, version, built_at=_utc_now())
    except OSError as exc:
        out.write("[welcome-builder] AF-AE-WELCOME-SOURCE-UNREADABLE: %s. "
                  "A card that cannot see its law never fabricates a "
                  "pass.\n" % exc)
        return EX_STOP
    except ValueError as exc:
        out.write("[welcome-builder] AF-AE-WELCOME-SOURCE-DRIFT: %s (the "
                  "card body renders from HOW-TO-USE.md by exact section "
                  "order; a drifted guide NEVER ships a card).\n" % exc)
        return EX_MISMATCH

    sql_stmt, sql_params = build_insert(card)

    # -- 2. Trevor-gated ACTION boundary --------------------------------------
    if not execute:
        out.write("[welcome-builder] AF-AE-WELCOME-NO-EXECUTE: the INSERT "
                  "was requested without --execute. The engine database is "
                  "READ-ONLY in dry-run: this module reports exactly what "
                  "it WOULD insert and exits WITHOUT mutating. STOP.\n")
        out.write("[welcome-builder] WOULD-INSERT %s (card key %s, title "
                  "%r, body %d chars, sha256 %s). The statement is NOT "
                  "executed.\n"
                  % (sql_stmt, CARD_KEY, card["title"], len(card["body"]),
                     card["source_sha256"]))
        if jsonout is not None:
            json.dump({"ok": False, "exit": EX_STOP, "execute": False,
                       "reason": "no-execute", "card_key": CARD_KEY,
                       "title": CARD_TITLE, "body_chars": len(card["body"]),
                       "body_sha256": _sha256_bytes(
                           card["body"].encode("utf-8")),
                       "statement": sql_stmt,
                       "note": "engine database READ-ONLY in dry-run; "
                               "nothing was written"}, jsonout)
            jsonout.write("\n")
        return EX_STOP

    # -- 3. READ-ONLY control (the gate's own known-good control) ------------
    try:
        con = _open_readonly(db)
        with con:
            if not _prove_schema(con, out=out):
                return EX_MISMATCH
            existing = _card_present(con)
    except sqlite3.Error as exc:
        out.write("[welcome-builder] AF-AE-WELCOME-DB-UNREADABLE: the "
                  "engine state database %s cannot be opened READ-ONLY "
                  "(%s). No write is attempted.\n" % (db.name, exc))
        return EX_STOP

    # -- 4. idempotency law (GET-first): a card already present is a clean
    #       no-op, never a duplicate write and never a foreign overwrite.
    if existing is not None:
        card_payload = json.dumps(card, ensure_ascii=False, sort_keys=True)
        if existing == card_payload:
            out.write("[welcome-builder] IDEMPOTENT NO-OP: the Welcome "
                      "card is already present under %s with identical "
                      "content. Nothing written.\n" % CARD_KEY)
            if jsonout is not None:
                json.dump({"ok": True, "execute": True, "inserted": False,
                           "idempotent": True, "card_key": CARD_KEY,
                           "state_dir": str(db.parent)}, jsonout)
                jsonout.write("\n")
            return EX_OK
        out.write("[welcome-builder] AF-AE-WELCOME-DB-MISMATCH: a foreign "
                  "value already sits under the card's own key %s. The "
                  "card is NEVER overwritten blindly; the mismatch is "
                  "reported and nothing is written.\n" % CARD_KEY)
        return EX_MISMATCH

    # -- 5. EXECUTE (the ONE write path; reached only under --execute after
    #        the read-only control proved the schema and the key's absence).
    try:
        con = sqlite3.connect(str(db), timeout=30)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=5000")
        try:
            with con:
                con.execute(sql_stmt, sql_params)
        finally:
            con.close()
    except sqlite3.OperationalError as exc:
        out.write("[welcome-builder] AF-AE-WELCOME-INSERT-REFUSED: %s. The "
                  "card is NEVER reported inserted when the write "
                  "refused.\n" % exc)
        if "locked" in str(exc).lower() or "busy" in str(exc).lower():
            return EX_HELD
        return EX_STOP

    # -- 6. READ-BACK (a write is never trusted without read-back) ------------
    try:
        con = _open_readonly(db)
        with con:
            got = _card_present(con)
    except sqlite3.Error as exc:
        out.write("[welcome-builder] AF-AE-WELCOME-READBACK-MISMATCH: the "
                  "read-back open failed (%s). The INSERT is NOT reported "
                  "as inserted.\n" % exc)
        return EX_MISMATCH
    if got != json.dumps(card, ensure_ascii=False, sort_keys=True):
        out.write("[welcome-builder] AF-AE-WELCOME-READBACK-MISMATCH: the "
                  "read-back under %s does not match the card that was "
                  "inserted. Nothing is reported inserted.\n" % CARD_KEY)
        return EX_MISMATCH

    out.write("[welcome-builder] INSERTED (card %s, title %r, body %d "
              "chars): executed the ONE INSERT and confirmed it by "
              "read-back.\n"
              % (CARD_KEY, card["title"], len(card["body"])))
    if jsonout is not None:
        json.dump({"ok": True, "execute": True, "inserted": True,
                   "card_key": CARD_KEY, "title": CARD_TITLE,
                   "body_chars": len(card["body"]),
                   "body_sha256": _sha256_bytes(card["body"].encode("utf-8")),
                   "source_sha256": card["source_sha256"],
                   "state_dir": str(db.parent)}, jsonout)
        jsonout.write("\n")
    return EX_OK


def plan_action(state_dir: str, *, out=None, jsonout=None) -> int:
    """OFFLINE plan: what build WOULD do — the card record and its
    statement — with NO database open (plan reads nothing from disk beyond
    the guide and the version file; the database path is reported as a
    masked file name only) and NO write. The plan is the dry-run body: the
    engine database is READ-ONLY in dry-run by construction because plan
    never opens it."""
    out = out or sys.stderr
    db = _state_db_path(state_dir)
    try:
        guide_text, version = _read_guide()
        card = build_card(guide_text, version, built_at=_utc_now())
    except OSError as exc:
        out.write("[welcome-builder] AF-AE-WELCOME-SOURCE-UNREADABLE: %s. "
                  "A card that cannot see its law never fabricates a "
                  "pass.\n" % exc)
        return EX_STOP
    except ValueError as exc:
        out.write("[welcome-builder] AF-AE-WELCOME-SOURCE-DRIFT: %s (the "
                  "card body renders from HOW-TO-USE.md by exact section "
                  "order; a drifted guide NEVER ships a card).\n" % exc)
        return EX_MISMATCH

    sql_stmt, _sql_params = build_insert(card)
    out.write("[welcome-builder] PLAN (card %s): build the Welcome card "
              "INSERT from HOW-TO-USE.md (%d chars of body copy, sha256 "
              "%s) and, with --execute, run the read-only control, execute "
              "the ONE INSERT into %s, and read it back. Dry-run: "
              "READ-ONLY, nothing written.\n"
              % (CARD_KEY, len(card["body"]), card["source_sha256"],
                 db.name))
    if jsonout is not None:
        json.dump({"ok": True, "dry_run": True, "card_key": CARD_KEY,
                   "title": CARD_TITLE, "body_chars": len(card["body"]),
                   "body_sha256": _sha256_bytes(card["body"].encode("utf-8")),
                   "source_file": CARD_SOURCE_FILE,
                   "source_sha256": card["source_sha256"],
                   "state_db": db.name,
                   "statement": sql_stmt,
                   "execute_required": True,
                   "note": "engine database READ-ONLY in dry-run; plan "
                           "never opens the database"}, jsonout)
        jsonout.write("\n")
    return EX_OK


def _utc_now() -> str:
    """The build timestamp, UTC, second precision, ISO 8601."""
    import datetime
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ")


def _default_state_dir() -> str:
    """The engine state directory resolution, agreed with anthology_state /
    gate_engine / mc_board: --state-dir > ANTHOLOGY_STATE_DIR >
    OPENCLAW_DATA_DIR/anthology-engine/state > ~/.anthology-engine/state.
    Resolved here so the sibling convention is honored without importing
    the sibling script (this module imports NO sibling — its only surfaces
    are the local guide and the local database)."""
    import os
    env = os.environ.get("ANTHOLOGY_STATE_DIR", "").strip()
    if env:
        return env
    data = os.environ.get("OPENCLAW_DATA_DIR", "").strip()
    if data:
        return str(Path(data).expanduser() / "anthology-engine" / "state")
    home = os.environ.get("HOME") or os.path.expanduser("~")
    return str(Path(home) / ".anthology-engine" / "state")


# ---------------------------------------------------------------------------
# SELF-TEST: golden + attack fixtures, zero network, zero secrets, zero
# writes (the self-test database lives in a temp dir; the --execute path is
# exercised against the temp database so NO engine state is ever touched).
# Mirrors the sibling self-tests: an assertion failure is an ENFORCED
# VIOLATION, exit 4 — a tamper never masquerades as "unexpected error"
# (exit 1).
# ---------------------------------------------------------------------------
GOLDEN_GUIDE = """\
# Anthology Engine -- Producer How-To

This is your guide to producing an anthology. You are the producer, the
owner of this Command Center. Your co-authors are your participants.

## What the engine does for you

You collect chapters from many contributors around one theme.

## Where you work: the Anthology board

Open the Anthology tile on your home screen.

## What your participants see

Your participants have no login. When it is their turn, they receive a short,
friendly email with a single link to their own private page.

## Assembling the anthology

When every participant is either approved or explicitly excluded, an
Assembly card appears with a readiness report.

## The platform

Every form, link, and field is part of Convert and Flow.

## Good to know

- There are no deadlines.
- Nothing is ever sent to a participant except the short, friendly nudges.
"""


def self_test(out=None) -> int:
    import io as _io
    import tempfile

    out = out or sys.stderr
    dev = _io.StringIO()
    try:
        # (0) the card contract is stable
        assert CARD_KEY == "welcome::producer"
        assert CARD_TYPE == "welcome"
        assert CARD_TITLE == "Welcome to the Anthology Engine"
        assert CARD_SOURCE_FILE == "HOW-TO-USE.md"
        assert CARD_BUILDER == "welcome_builder.py"
        assert len(SOURCE_HEADINGS) == 6
        assert SOURCE_HEADINGS[0] == "What the engine does for you"

        # (1) golden build: the card body carries the guide's own title,
        #     intro, and every section heading verbatim, in exact order,
        #     and the producer language holds (participant(s) present,
        #     Convert and Flow naming present)
        card = build_card(GOLDEN_GUIDE, "0.1.24-test",
                          built_at="2026-08-11T00:00:00Z")
        body = card["body"]
        assert card["card_key"] == CARD_KEY
        assert card["title"] == CARD_TITLE
        assert body.startswith("# Anthology Engine -- Producer How-To\n")
        assert "This is your guide to producing an anthology." in body
        for h in SOURCE_HEADINGS:
            assert ("## %s" % h) in body, "section %r missing from body" % h
        order = [body.index("## %s" % h) for h in SOURCE_HEADINGS]
        assert order == sorted(order), "section order drifted in the body"
        assert "participant" in body.lower()
        assert "convert and flow" in body.lower()
        # the sha256 of the source is the fingerprint the surfaces report
        assert card["source_sha256"] == _sha256_bytes(
            GOLDEN_GUIDE.encode("utf-8"))

        # (2) the INSERT names its columns and parameterizes every value
        sql_stmt, params = build_insert(card)
        assert sql_stmt.startswith("INSERT INTO meta(key, value)")
        assert "VALUES (?, ?)" in sql_stmt
        assert "ON CONFLICT(key)" in sql_stmt
        assert len(params) == 2 and params[0] == CARD_KEY
        # the payload round-trips and the card key is never interpolated
        assert json.loads(params[1])["card_key"] == CARD_KEY

        # (3) source drift is refused: a heading renamed, dropped, or
        #     reordered NEVER ships a card
        for mutation in (
            GOLDEN_GUIDE.replace("## The platform", "## The Platforms"),
            GOLDEN_GUIDE.replace("## Good to know\n", ""),
            GOLDEN_GUIDE.replace(
                "## What your participants see",
                "## What your co-authors see"),
        ):
            try:
                _build_card_body(mutation)
                raise AssertionError("drifted guide must be refused")
            except ValueError:
                pass

        # (4) the content law is enforced: participant(s) and the Convert
        #     and Flow naming are REQUIRED in the card body
        _check_content_law("Everything is part of Convert and Flow. "
                           "Your participants decide.")
        for bad in ("Everything is part of Convert and Flow.",
                    "Your participants decide.",
                    "Everything is part of the platform here."):
            try:
                _check_content_law(bad)
                raise AssertionError("content-law break must be refused: %r"
                                     % bad)
            except ValueError:
                pass

        # (5) plan is OFFLINE and READ-ONLY: no database is touched, the
        #     report is truthful about the execute gate
        dev5 = _io.StringIO()
        rc5 = plan_action(tempfile.mkdtemp(prefix="welcome-plan-"),
                          out=dev5, jsonout=dev5)
        assert rc5 == EX_OK, "plan must exit 0, got %s" % rc5
        plan_json = json.loads(dev5.getvalue().splitlines()[-1])
        assert plan_json["ok"] and plan_json["dry_run"]
        assert plan_json["execute_required"] is True

        # (6) build WITHOUT --execute STOPS (exit 2) and writes NOTHING
        #     (the engine database is READ-ONLY in dry-run)
        tmp = tempfile.mkdtemp(prefix="welcome-noexec-")
        dev6 = _io.StringIO()
        rc6 = build_action(tmp, execute=False, out=dev6, jsonout=dev6)
        assert rc6 == EX_STOP, "no-execute must STOP (exit 2), got %s" % rc6
        assert "AF-AE-WELCOME-NO-EXECUTE" in dev6.getvalue()
        assert "WOULD-INSERT" in dev6.getvalue()
        db = Path(tmp) / STATE_DB_NAME
        assert not db.exists(), "dry-run must NEVER create the database"

        # (7) the READ-ONLY control refuses an unreadable / schema-less
        #     database BEFORE any write path (never inserts into the
        #     unknown); the write path stays gated on --execute
        dev7 = _io.StringIO()
        rc7 = build_action(tmp, execute=True, out=dev7, jsonout=dev7)
        assert rc7 == EX_STOP, "missing database must STOP, got %s" % rc7
        assert "AF-AE-WELCOME-DB-UNREADABLE" in dev7.getvalue()

        # (8) golden full path under --execute against a TEMP database:
        #     the schema law is proven read-only first, the ONE INSERT
        #     executes, the read-back confirms, exit 0
        tmp8 = tempfile.mkdtemp(prefix="welcome-exec-")
        db8 = Path(tmp8) / STATE_DB_NAME
        con = sqlite3.connect(str(db8))
        con.executescript(META_SCHEMA_SQL)
        con.close()
        dev8 = _io.StringIO()
        rc8 = build_action(tmp8, execute=True, out=dev8, jsonout=dev8)
        assert rc8 == EX_OK, "golden --execute must exit 0, got %s" % rc8
        assert "INSERTED" in dev8.getvalue()
        assert "confirmed it by read-back" in dev8.getvalue()
        con = _open_readonly(db8)
        got = _card_present(con)
        con.close()
        assert got is not None, "the INSERT must be read back"
        assert json.loads(got)["card_key"] == CARD_KEY

        # (9) idempotency: a second --execute run sees the card present and
        #     is a clean NO-OP (never a second row, never a foreign
        #     overwrite)
        dev9 = _io.StringIO()
        rc9 = build_action(tmp8, execute=True, out=dev9, jsonout=dev9)
        assert rc9 == EX_OK, "re-run must exit 0, got %s" % rc9
        assert "IDEMPOTENT NO-OP" in dev9.getvalue()
        con = _open_readonly(db8)
        rows = con.execute(
            "SELECT COUNT(*) AS c FROM meta WHERE key=?",
            (CARD_KEY,)).fetchone()["c"]
        con.close()
        assert rows == 1, "the card key must exist exactly once"

        # (10) a foreign value under the card's own key is NEVER blindly
        #      overwritten
        tmp10 = tempfile.mkdtemp(prefix="welcome-foreign-")
        db10 = Path(tmp10) / STATE_DB_NAME
        con = sqlite3.connect(str(db10))
        con.executescript(META_SCHEMA_SQL)
        con.execute("INSERT INTO meta(key, value) VALUES(?, ?)",
                    (CARD_KEY, "not-the-card"))
        con.commit()
        con.close()
        dev10 = _io.StringIO()
        rc10 = build_action(tmp10, execute=True, out=dev10, jsonout=dev10)
        assert rc10 == EX_MISMATCH, "a foreign row must be a MISMATCH"
        assert "AF-AE-WELCOME-DB-MISMATCH" in dev10.getvalue()
        con = _open_readonly(db10)
        still = _card_present(con)
        con.close()
        assert still == "not-the-card", "the foreign row must stay untouched"

        # (11) the schema law refuses a drifted meta DDL (never inserts
        #      into an unknown schema)
        tmp11 = tempfile.mkdtemp(prefix="welcome-schema-")
        db11 = Path(tmp11) / STATE_DB_NAME
        con = sqlite3.connect(str(db11))
        con.executescript("CREATE TABLE meta (key TEXT PRIMARY KEY, "
                          "value TEXT, extra TEXT)")
        con.close()
        dev11 = _io.StringIO()
        rc11 = build_action(tmp11, execute=True, out=dev11, jsonout=dev11)
        assert rc11 == EX_MISMATCH, "a drifted schema must be a MISMATCH"
        assert "AF-AE-WELCOME-DB-MISMATCH" in dev11.getvalue()

        # (12) the card body rides every machine surface as a fingerprint
        #      only — the body TEXT never echoes onto the JSON surfaces
        all_json = (dev5.getvalue() + dev6.getvalue() + dev7.getvalue()
                    + dev8.getvalue() + dev9.getvalue() + dev10.getvalue()
                    + dev11.getvalue())
        for token in ("This is your guide to producing",
                      "Collect chapters from many contributors"):
            assert token not in all_json, \
                "the card body must ride as a fingerprint only, never verbatim"

        out.write("welcome_builder self-test: OK (golden guide -> card body "
                  "by exact section order, producer-language law enforced, "
                  "source-drift refusal, no-execute STOP, read-only DB "
                  "control, golden INSERT + read-back, idempotent no-op, "
                  "foreign-row mismatch, schema-law refusal, body "
                  "fingerprint-only)\n")
        return EX_OK
    except AssertionError as exc:
        sys.stderr.write("[welcome_builder] SELF-TEST FAILED "
                         "(AF-AE-WELCOME-* family): %s\n" % exc)
        return EX_VIOLATION


# ---------------------------------------------------------------------------
# CLI (house style: argparse + subcommands + --self-test/--selftest aliases)
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="welcome_builder.py",
        description="Producer Welcome card builder: HOW-TO-USE.md becomes "
                    "the card's body copy, the card lands in the engine "
                    "state database's meta table under the stable key "
                    "'welcome::producer', and the INSERT is executed ONLY "
                    "under --execute (the Trevor gate) — the engine "
                    "database is READ-ONLY in every non-execute path "
                    "(Skill 59, U20 tooling).")
    ap.add_argument("--state-dir", default="",
                    help="engine state directory holding anthology_state.db "
                    "(default: the sibling resolution — $ANTHOLOGY_STATE_DIR, "
                    "else $OPENCLAW_DATA_DIR/anthology-engine/state, else "
                    "~/.anthology-engine/state)")
    ap.add_argument("--execute", action="store_true",
                    help="Trevor-gated ACTION flag: only with this flag may "
                    "the module execute the INSERT")
    ap.add_argument("--dry-run", action="store_true",
                    help="plan without building (alias for the plan "
                    "subcommand; OFFLINE, READ-ONLY)")
    ap.add_argument("--json", action="store_true",
                    help="emit a machine-readable summary on stdout")
    ap.add_argument("cmd", choices=["build", "plan", "self-test"])

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

        if args.cmd == "plan":
            return plan_action(args.state_dir or _default_state_dir(),
                               out=sys.stderr, jsonout=jsonout)

        if args.cmd == "build":
            if args.dry_run:
                # No database in dry-run: the offline plan surface.
                return plan_action(args.state_dir or _default_state_dir(),
                                   out=sys.stderr, jsonout=jsonout)
            return build_action(args.state_dir or _default_state_dir(),
                                execute=args.execute, out=sys.stderr,
                                jsonout=jsonout)

        ap.error("unknown command %r" % args.cmd)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[welcome_builder] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
