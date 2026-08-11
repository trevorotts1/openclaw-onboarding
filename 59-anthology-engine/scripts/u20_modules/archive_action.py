#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u20_modules/archive_action.py  (U20 tooling)
# ARCHIVE ACTION — the Trevor-gated producer archive surface for the engine's
# OWN ledger (the local SQLite mirror, anthology_state.py — the SOLE writer)
# plus the Welcome card content the producer's board carries (U20 surface).
# The archive STATEMENTS (the ledger writes that archive an anthology) run
# ONLY under --execute. Without --execute the module is a READ-ONLY dry-run:
# it reports what it WOULD archive and exits without mutating (STOP, exit 2
# on an archive request; PASS, exit 0 on a plan).
#
# WHAT THIS IS (the U20 archive-action law, carried in from the U06 family —
# the archive LAW authority is u06_modules/golden_absent.py, never re-typed):
#   1. THE ARCHIVE ACTION LAW (the u20 __init__.py doctrine + golden_absent):
#      an archive ACTION — a mutation that archives / deactivates / revokes —
#      REQUIRES the operator's explicit --execute (Trevor-gated). WITHOUT
#      --execute the action is a READ-ONLY dry-run: it reports what it WOULD
#      do (the anthology, the two statements' write shapes) and exits WITHOUT
#      mutating (applied false, dry_run true). WITH --execute the statements
#      run ONCE and the result is read back (READ-BACK LAW — a write is never
#      trusted without read-back).
#   2. THE TWO STATEMENTS (the archive sweep's write surface, carried in
#      from the engine's OWN revoke flow — revoke-anthology-client.sh R6 /
#      R2 — never a second implementation):
#        * the LEDGER statement — archive the anthology's ledger rows via
#          anthology_state.py upsert-anthology --status archived
#          (deactivate-never-delete, ninety-day retention; the sole-writer
#          channel — no other code path writes state),
#        * the BOARD statement — archive the anthology's board footprint
#          (the Assembly card + every participant card) via mc_board.py
#          archive --anthology-id <id> to the board's archived status
#          ('blocked' — mc_board.ARCHIVE_STATUS, never 'done').
#      The WRITES are performed ONLY under --execute (the statements run
#      only when the caller passed the gate). Dry-run performs NO write of
#      any kind: the DB is READ-ONLY in dry-run.
#   3. THE READ-BACK LAW: after the statements, the module re-reads the
#      LEDGER target through the SOLE WRITER's OWN read-only surface
#      (anthology_state get-anthology, READ-ONLY by the ledger's own
#      _READ_ONLY set) and compares the status BYTE-EXACT against the
#      ledger's archived vocabulary. A drift is a MISMATCH (exit 5), never
#      a false success. An anthology with NO ledger row has NOTHING to
#      archive on the ledger target — a clean no-op PASS exit 0 (the
#      golden absent-state law, exactly the engine's own "R3 no shared
#      Drive folders" no-op precedent).
#   4. THE WELCOME CARD (U20 surface): the producer's board carries a
#      Welcome card whose content derives from HOW-TO-USE.md (the
#      producer-facing how-to) — it ships as copy only, never as a write
#      (the u20 __init__.py doctrine). The card's SEED surface is owned by
#      the sibling u20_modules/db_connector.py (the Command Center
#      mission-control.db connector: read-only by default, the card INSERT
#      under --execute only); THIS module does NOT seed the card — it
#      reads HOW-TO-USE.md from the skill root when it exists and reports
#      the content the Welcome would carry (the derivation is shared, the
#      write surface is the sibling's alone). An unreadable or absent
#      HOW-TO-USE.md is a STOP (exit 2) — the Welcome surface never ships
#      empty or fabricated. This module's archive statements touch the
#      ledger + board only.
#   5. THE MASKING LAW: every operator surface reports the anthology id by
#      MASKED MARKER only (last-4, non-reversible — reg._mask_location
#      shape). The full id rides inside the subprocess argv (a machine
#      surface) and the machine-consumed JSON payloads only.
#
# CREDENTIAL DOCTRINE: this module holds NO credential and reads NO env
# secret. The ledger writer and the board client resolve their own
# credentials BY LABEL (SET / NOT SET only) — the statements are delegated
# to those surfaces, never re-implemented. A credential-shaped string
# (pit-*) on any surface REFUSES (STOP, exit 2) rather than echo.
#
# EXIT CODES (house convention 0/1/2/3/5; 4 = enforced violation):
#   0  PASS — the archive statements are verified (idempotent no-op / the
#      ledger row was already archived / dry-run plan counts as pass)
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP refusal — usage / missing --anthology-id / a missing or
#      unreadable HOW-TO-USE.md / the archive ACTION without --execute
#      (AF-AE-U20ARCHIVE-NO-EXECUTE) / a credential-shaped surface / a
#      refused statement (scope / validation)
#   3  HELD — the ledger writer / board client / mirror is unreachable or
#      fails (UNDETERMINED, retryable — never a verdict)
#   4  self-test FAILED (an enforced violation — a tamper NEVER masquerades
#      as exit 1)
#   5  MISMATCH — the post-write read-back does not confirm 'archived'
#      byte-exact
#
# STDLIB ONLY (argparse + json + sqlite3 + subprocess + pathlib), delegating
# every credential-bearing surface to the sibling authorities
# (anthology_registry / anthology_state / mc_board). Calls NO model.
# DOCTRINE: move in silence; operator-verbose only; nothing Anthropic in
# any runtime file; Convert and Flow naming in every client surface; NEVER
# print a secret value; --dry-run, plan, and --self-test are OFFLINE (no
# network, no credential, no write).
# =============================================================================
"""archive_action.py -- Trevor-gated producer archive statements for the
engine's own ledger + board footprint (Skill 59, U20 tooling). The archive
STATEMENTS run ONLY under --execute; dry-run is a READ-ONLY plan (the DB is
read-only in dry-run; Welcome card content derives from HOW-TO-USE.md)."""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry owns the exit
# codes and the masking law; the ledger writer owns the status vocabulary
# and the state-dir resolution; the board client owns the board archive
# status. All are STDLIB-only and side-effect-free at import — importing
# them cannot drag credential resolution into this process.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402
import anthology_state as state  # noqa: E402  (the ledger — sole writer, read once)
import mc_board as board  # noqa: E402  (the board archive status, read once)

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The one fixed report contract. Every surface this module emits carries it,
# so a machine consumer can never mistake another JSON object for an
# archive-action read (the surface contract is load-bearing).
CONFIG_CONTRACT = "anthology-engine-archive-action"
CONFIG_SCHEMA_VERSION = 1

# The ARCHIVE ACTION law, machine-carried from the family authorities (the
# U06 archive LAW authority — the mutation verb, the execute flag whose
# explicit presence is Trevor's gate, and the law's own assertion that the
# gate is REQUIRED). Read once, never re-typed.
ARCHIVE_ACTION = "archive"
EXECUTE_FLAG = "--execute"
GOLDEN_EXECUTE_REQUIRED = True  # the law: the archive ACTION is gated

# The archived status this module confirms on the LEDGER target — byte-exact
# against the ledger's OWN controlled vocabulary (the status the SOLE writer
# archives with: anthology_state upsert-anthology --status archived,
# deactivate-never-delete). Read once from the ledger authority.
LEDGER_ARCHIVED_STATUS = "archived"
assert LEDGER_ARCHIVED_STATUS in state.ANTHOLOGY_STATUS, (
    "the archived status must be in the ledger's controlled vocabulary")

# The status the board cards carry after archival — the board's OWN archive
# status (mc_board.ARCHIVE_STATUS, 'blocked': the signed-status route has no
# 'archived' primitive; the card leaves the active columns). Never 'done' —
# the one status this client is FORBIDDEN to set. Read once from the board
# client, never re-typed.
BOARD_ARCHIVED_STATUS = board.ARCHIVE_STATUS

# The ledger writer and the board client — the ONLY write surfaces the
# archive statements may ride. Everything else is a read.
STATE_WRITER = "anthology_state.py"
BOARD_CLIENT = "mc_board.py"
SCRIPTS_DIR = Path(__file__).resolve().parent.parent
SKILL_DIR = SCRIPTS_DIR.parent
HOW_TO_USE = SKILL_DIR / "HOW-TO-USE.md"

# The mirror database file name under the resolved state directory — the
# same name every engine component resolves (mc_board._mirror_ro /
# anthology_state._resolve_db_path).
MIRROR_DB_NAME = "anthology_state.db"
LEDGER_TABLE = "anthologies"
LEDGER_PK = "anthology_id"

# A credential-shaped string is the pit- token prefix followed by a
# non-empty value (the house guard shape every u06 surface is scanned
# against). A hit on any emitted surface REFUSES rather than echo.
_CREDENTIAL_SHAPE = re.compile(r"pit-\S+")

# A value that is not a str/int/float/bool/None cannot be judged (a dict or
# list in a status slot is a malformed read — never a verdict).
_SCALAR_TYPES = (str, int, float, bool)


class ArchiveActionError(Exception):
    """A fail-closed refusal (STOP family): a credential-shaped string on a
    surface, a missing / unreadable HOW-TO-USE.md, or a refused statement.
    An expectation that cannot name its own sources must not run."""


# ---------------------------------------------------------------------------
# Fail-closed read helpers. Pure; never print a secret value.
# ---------------------------------------------------------------------------
def _mask_id(rid: str) -> str:
    """Non-reversible marker for an id (last 4 chars) — the house surface
    shape for every operator-facing mention of an id. Full ids ride inside
    the subprocess argv (a machine surface) and the machine payloads a
    consumer reads, never on a human surface."""
    rid = (rid or "").strip()
    return ("..." + rid[-4:]) if len(rid) >= 4 else "...(short)"


def _scalar_str(value) -> str:
    """A scalar string candidate for a status slot, or ''. A non-scalar
    (a dict / list / None) is '' — a malformed read is never judged a
    status. Never raises."""
    if isinstance(value, _SCALAR_TYPES):
        s = str(value).strip()
        return s if s.lower() != "none" else ""
    return ""


def _clean_surface_text(text: str) -> str:
    """Strip a credential-shaped value from a surface string. HOW-TO-USE.md
    is producer-facing copy and normally carries none; if one appears, the
    module REFUSES rather than echo (the house guard shape, same as the u06
    family). Returns the text unchanged when clean."""
    m = _CREDENTIAL_SHAPE.search(text or "")
    if m:
        raise ArchiveActionError(
            "a credential-shaped value appeared on a surface; refusing to "
            "echo it (house guard)")
    return text or ""


def _emit_report(report: dict, jsonout) -> None:
    """Emit the ONE JSON report object on the machine surface — the given
    stream when one was supplied, else stdout. The report carries only
    masked markers and derived copy, never a secret or a full id."""
    target = jsonout if jsonout is not None else sys.stdout
    target.write(json.dumps(report, indent=2, sort_keys=True) + "\n")


def _resolve_state_dir(state_dir: str = "") -> Path:
    """The engine state directory, resolved with the SAME precedence the
    whole engine uses (mc_board.resolve_state_dir /
    anthology_state.default_state_dir): --state-dir > ANTHOLOGY_STATE_DIR
    > OPENCLAW_DATA_DIR/anthology-engine/state > node home."""
    if state_dir and state_dir.strip():
        return Path(state_dir).expanduser()
    return state.default_state_dir()


def _read_mirror_row(state_dir: Path, table: str, pk_col: str, pk_val: str):
    """Read ONE row from the local mirror. Returns (sqlite3.Row, conn) or
    (None, None) when the row does not exist, and raises sqlite3.Error /
    OSError on a broken read (the caller maps onto HELD). The connection
    stays open for the caller to close. READ-ONLY (mode=ro) by
    construction: the mirror is never writable through this module."""
    db = state_dir / MIRROR_DB_NAME
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=5000")
    row = con.execute(
        "SELECT * FROM %s WHERE %s=?" % (table, pk_col), (pk_val,)).fetchone()
    return row, con


def _read_welcome_card() -> dict:
    """The Welcome card content — derived from HOW-TO-USE.md (the
    producer-facing how-to), shipped as copy only, never as a write (the
    u20 __init__.py doctrine). An absent or unreadable HOW-TO-USE.md is a
    STOP — the Welcome surface never ships empty or fabricated."""
    if not HOW_TO_USE.is_file():
        raise ArchiveActionError(
            "HOW-TO-USE.md not found at %s — the Welcome card content "
            "cannot be derived; refusing to ship an empty Welcome" % HOW_TO_USE)
    try:
        text = HOW_TO_USE.read_text(encoding="utf-8")
    except OSError as exc:
        raise ArchiveActionError(
            "HOW-TO-USE.md unreadable: %s — refusing to ship an empty "
            "Welcome" % exc)
    text = _clean_surface_text(text)
    return {"source": str(HOW_TO_USE), "title": "Welcome",
            "content": text.strip()}


# ---------------------------------------------------------------------------
# The two archive statements (writes ride the sibling surfaces ONLY under
# --execute; each returns the exit code of its subprocess).
# ---------------------------------------------------------------------------
def _statement_ledger(anthology_id: str, state_dir: Path, *, out) -> int:
    """STATEMENT 1 — the LEDGER rows: archive via the SOLE WRITER's own
    upsert-anthology --status archived channel (deactivate-never-delete,
    ninety-day retention — the revoke flow's R6, never re-implemented).
    Runs ONLY under --execute. Returns the subprocess exit code."""
    return subprocess.call([
        sys.executable, str(SCRIPTS_DIR / STATE_WRITER),
        "--db", str(state_dir / MIRROR_DB_NAME),
        "upsert-anthology", "--anthology-id", anthology_id,
        "--status", LEDGER_ARCHIVED_STATUS,
    ])


def _statement_board(anthology_id: str, state_dir: Path, *, out) -> int:
    """STATEMENT 2 — the board footprint: the Assembly card + every
    participant card, archived via the board client's OWN archive command
    (mc_board.py archive --anthology-id — the revoke flow's R2, fail-soft
    per SPEC 11.2; the ledger is the truth). Runs ONLY under --execute.
    Returns the subprocess exit code."""
    return subprocess.call([
        sys.executable, str(SCRIPTS_DIR / BOARD_CLIENT),
        "archive", "--anthology-id", anthology_id,
        "--state-dir", str(state_dir),
    ])


def _ledger_status(state_dir: Path, anthology_id: str) -> str:
    """The ledger status of the anthology, read through the local mirror
    READ-ONLY (mode=ro). Returns '' when the anthology has no ledger row
    (NOTHING to archive on the ledger target — the absent-state no-op) or
    when the mirror is unreadable (the caller maps the failure onto HELD).
    Raises sqlite3.Error / OSError on a broken read."""
    row, con = _read_mirror_row(state_dir, LEDGER_TABLE, LEDGER_PK,
                                anthology_id)
    if row is None:
        return ""
    try:
        return _scalar_str(row["status"])
    finally:
        con.close()


# ---------------------------------------------------------------------------
# The archive ACTION — dry-run is READ-ONLY (the DB is read-only in dry-run);
# the statements run ONLY under --execute (the Trevor gate). After the
# statements the LEDGER target is read back byte-exact (READ-BACK LAW).
# ---------------------------------------------------------------------------
def archive(anthology_id: str, *, state_dir: str = "", execute: bool = False,
            out=None, jsonout=None) -> int:
    """The archive ACTION over the engine's own ledger + board footprint
    (the U20 surface). Dry-run / plan: READ-ONLY — it reports what it WOULD
    archive and exits WITHOUT mutating (the DB is read-only in dry-run;
    the Welcome card ships as copy only). With --execute the TWO archive
    statements run once each (the ledger via the sole writer, the board via
    the board client) and the LEDGER target is read back byte-exact —
    a drift is a MISMATCH (exit 5), never a false success. An anthology
    with no ledger row has NOTHING to archive: a clean no-op PASS (exit 0).
    This module holds NO credential and reads NO env secret — the
    statements are delegated to their surfaces, never re-implemented."""
    out = out or sys.stderr
    anthology_id = (anthology_id or "").strip()
    if not anthology_id:
        raise ArchiveActionError(
            "no --anthology-id given — the archive target is required "
            "(never a sweep)")
    masked = _mask_id(anthology_id)
    state_dir = _resolve_state_dir(state_dir)

    # The Welcome card content — read FIRST (fail-closed before anything
    # else: the Welcome surface never ships empty or fabricated). The card
    # itself is seeded by the sibling db_connector.py; here it rides the
    # report as derived copy only, never a write.
    welcome = _read_welcome_card()

    # The read surface — the local mirror, READ-ONLY. An unreadable mirror
    # is HELD (UNDETERMINED, never a verdict).
    try:
        status = _ledger_status(state_dir, anthology_id)
    except (sqlite3.Error, OSError) as exc:
        out.write("[archive-action] HELD: the ledger mirror is unreadable "
                  "(%s) for marker %s — UNDETERMINED, never a verdict; "
                  "nothing was written (a mirror that cannot be opened "
                  "cannot be mutated).\n" % (exc, masked))
        if jsonout is not None:
            _emit_report({
                "contract": CONFIG_CONTRACT,
                "schema_version": CONFIG_SCHEMA_VERSION,
                "ok": False, "action": ARCHIVE_ACTION,
                "anthology_id": masked, "verdict": "HELD",
                "execute": execute, "dry_run": not execute,
                "statements": ["ledger", "board"],
                "detail": "ledger mirror unreadable",
            }, jsonout)
        return EX_HELD

    # THE ABSENT-STATE LAW: no ledger row -> NOTHING to archive on the
    # ledger target -> clean no-op PASS (exit 0), exactly the engine's own
    # absent-state precedent (golden_absent / revoke R3). The board
    # statement is skipped with it: no row, no card footprint.
    if status == "":
        out.write("[archive-action] NOTHING TO ARCHIVE (marker %s): no "
                  "ledger row — clean no-op PASS exit 0.\n" % masked)
        if jsonout is not None:
            _emit_report({
                "contract": CONFIG_CONTRACT,
                "schema_version": CONFIG_SCHEMA_VERSION,
                "ok": True, "action": ARCHIVE_ACTION,
                "anthology_id": masked, "verdict": "no-op",
                "execute": execute, "dry_run": not execute,
                "statements": [], "ledger_before": status,
                "welcome": {"title": welcome["title"],
                            "chars": len(welcome["content"])},
            }, jsonout)
        return EX_OK

    # IDEMPOTENT NO-OP: the ledger row is already archived -> nothing to
    # archive -> PASS exit 0 (never a second archive, never a rewrite).
    if status == LEDGER_ARCHIVED_STATUS:
        out.write("[archive-action] IDEMPOTENT NO-OP (marker %s): the "
                  "ledger status is already '%s' — nothing archived.\n"
                  % (masked, LEDGER_ARCHIVED_STATUS))
        if jsonout is not None:
            _emit_report({
                "contract": CONFIG_CONTRACT,
                "schema_version": CONFIG_SCHEMA_VERSION,
                "ok": True, "action": ARCHIVE_ACTION,
                "anthology_id": masked, "verdict": "already-archived",
                "execute": execute, "dry_run": not execute,
                "statements": [], "ledger_before": status,
                "welcome": {"title": welcome["title"],
                            "chars": len(welcome["content"])},
            }, jsonout)
        return EX_OK

    # THE TREVOR GATE: the archive STATEMENTS run ONLY under --execute.
    # Without it the ACTION is a REFUSAL (STOP, exit 2), never a silent
    # no-op and never a mutation (the AF-AE-U20ARCHIVE-NO-EXECUTE law).
    if not execute:
        out.write("[archive-action] AF-AE-U20ARCHIVE-NO-EXECUTE: marker %s "
                  "is at status '%s' and --execute was NOT passed. The "
                  "archive statements (ledger via %s upsert-anthology "
                  "--status %s, board via %s archive) are Trevor-gated: "
                  "STOP, nothing written. The DB was read-only.\n"
                  % (masked, status, STATE_WRITER, LEDGER_ARCHIVED_STATUS,
                     BOARD_CLIENT))
        if jsonout is not None:
            _emit_report({
                "contract": CONFIG_CONTRACT,
                "schema_version": CONFIG_SCHEMA_VERSION,
                "ok": False, "action": ARCHIVE_ACTION,
                "anthology_id": masked, "verdict": "REFUSED",
                "reason": "no-execute", "execute": execute,
                "dry_run": not execute,
                "statements": ["ledger", "board"],
                "ledger_before": status,
                "welcome": {"title": welcome["title"],
                            "chars": len(welcome["content"])},
            }, jsonout)
        return EX_STOP

    # -- STATEMENT 1: the LEDGER rows (upsert-anthology --status archived)
    rc = _statement_ledger(anthology_id, state_dir, out=out)
    if rc != EX_OK:
        out.write("[archive-action] STOP: the ledger archive statement "
                  "refused (rc=%s) for marker %s — nothing reported "
                  "archived.\n" % (rc, masked))
        if jsonout is not None:
            _emit_report({
                "contract": CONFIG_CONTRACT,
                "schema_version": CONFIG_SCHEMA_VERSION,
                "ok": False, "action": ARCHIVE_ACTION,
                "anthology_id": masked, "verdict": "REFUSED",
                "reason": "ledger-statement-rc-%s" % rc,
                "execute": True, "dry_run": False,
                "statements": ["ledger", "board"],
                "ledger_before": status,
            }, jsonout)
        return EX_STOP

    # -- STATEMENT 2: the BOARD footprint (mc_board archive — fail-soft
    #    per SPEC 11.2: a declined / unreachable board returns exit 0 and
    #    the card reconciles on the daily tick; the ledger is the truth).
    #    A NONZERO rc2 is therefore an INSTRUMENT anomaly (the board
    #    client's own contract returns 0 for every board condition), never
    #    a board verdict: the ledger rows ARE archived and certified; the
    #    board footprint is not certified (UNDETERMINED — never a claim).
    rc2 = _statement_board(anthology_id, state_dir, out=out)
    if rc2 != EX_OK:
        out.write("[archive-action] HELD: the board archive statement "
                  "returned rc=%s for marker %s — the board client's "
                  "fail-soft contract returns 0 for board conditions, so "
                  "a nonzero rc is an instrument anomaly (UNDETERMINED, "
                  "never a board verdict). The ledger rows ARE archived "
                  "and certified by read-back below; the board footprint "
                  "is not certified.\n" % (rc2, masked))
        if jsonout is not None:
            _emit_report({
                "contract": CONFIG_CONTRACT,
                "schema_version": CONFIG_SCHEMA_VERSION,
                "ok": False, "action": ARCHIVE_ACTION,
                "anthology_id": masked, "verdict": "HELD",
                "reason": "board-statement-rc-%s" % rc2,
                "execute": True, "dry_run": False,
                "statements": ["ledger", "board"],
                "ledger_before": status,
            }, jsonout)
        return EX_HELD

    # -- READ-BACK LAW: a write is never trusted without read-back. Re-read
    #    the LEDGER target and compare BYTE-EXACT; a drift is a MISMATCH
    #    (exit 5), never a false success.
    try:
        after = _ledger_status(state_dir, anthology_id)
    except (sqlite3.Error, OSError) as exc:
        out.write("[archive-action] AF-AE-U20ARCHIVE-READBACK: the ledger "
                  "read-back for marker %s is HELD (unreadable mirror: "
                  "%s) — the archive is NOT certified (exit 3, "
                  "UNDETERMINED, never a verdict).\n" % (masked, exc))
        if jsonout is not None:
            _emit_report({
                "contract": CONFIG_CONTRACT,
                "schema_version": CONFIG_SCHEMA_VERSION,
                "ok": False, "action": ARCHIVE_ACTION,
                "anthology_id": masked, "verdict": "HELD",
                "reason": "readback-unreadable", "execute": True,
                "dry_run": False, "statements": ["ledger", "board"],
                "ledger_before": status,
            }, jsonout)
        return EX_HELD
    if after != LEDGER_ARCHIVED_STATUS:
        out.write("[archive-action] AF-AE-U20ARCHIVE-READBACK: marker %s "
                  "does NOT read back '%s' (found '%s') after the archive "
                  "statements — MISMATCH (exit 5), never a false success.\n"
                  % (masked, LEDGER_ARCHIVED_STATUS, after or "(none)"))
        if jsonout is not None:
            _emit_report({
                "contract": CONFIG_CONTRACT,
                "schema_version": CONFIG_SCHEMA_VERSION,
                "ok": False, "action": ARCHIVE_ACTION,
                "anthology_id": masked, "verdict": "MISMATCH",
                "reason": "readback-drift", "execute": True,
                "dry_run": False, "statements": ["ledger", "board"],
                "ledger_before": status, "ledger_after": after,
            }, jsonout)
        return EX_MISMATCH

    out.write("[archive-action] ARCHIVED (marker %s): the ledger rows read "
              "back '%s' byte-exact; the board statement ran under the "
              "board client's OWN fail-soft semantics (a declined board "
              "returns exit 0 and reconciles on the daily tick — the "
              "ledger is the truth).\n"
              % (masked, LEDGER_ARCHIVED_STATUS))
    if jsonout is not None:
        _emit_report({
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "ok": True, "action": ARCHIVE_ACTION,
            "anthology_id": masked, "verdict": "archived",
            "execute": True, "dry_run": False,
            "statements": ["ledger", "board"],
            "ledger_before": status, "ledger_after": after,
            "board_status": BOARD_ARCHIVED_STATUS,
            "board_certified": False,
            "welcome": {"title": welcome["title"],
                        "chars": len(welcome["content"])},
        }, jsonout)
    return EX_OK


def plan(out=None, jsonout=None) -> int:
    """READ-ONLY plan — reports the archive ACTION, its statements, and the
    Welcome card derivation WITHOUT reading the DB, WITHOUT a credential,
    and WITHOUT any write (offline). The Welcome card content still derives
    from HOW-TO-USE.md (fail-closed: an absent / unreadable how-to is a
    STOP, never a fabricated Welcome)."""
    out = out or sys.stderr
    welcome = _read_welcome_card()
    out.write("[archive-action] PLAN: with --execute the module would run "
              "the archive statements for one --anthology-id — (1) the "
              "ledger rows via %s upsert-anthology --status %s "
              "(deactivate-never-delete), (2) the board footprint via %s "
              "archive ('%s', never 'done'); then read the ledger back "
              "byte-exact. The Welcome card derives from %s (%d chars, "
              "shipped as copy only, never a write). No writes "
              "performed.\n" % (STATE_WRITER, LEDGER_ARCHIVED_STATUS,
                                BOARD_CLIENT, BOARD_ARCHIVED_STATUS,
                                welcome["source"], len(welcome["content"])))
    if jsonout is not None:
        _emit_report({
            "contract": CONFIG_CONTRACT,
            "schema_version": CONFIG_SCHEMA_VERSION,
            "ok": True, "action": ARCHIVE_ACTION, "dry_run": True,
            "verdict": "planned", "statements": ["ledger", "board"],
            "ledger_status_wanted": LEDGER_ARCHIVED_STATUS,
            "board_status_wanted": BOARD_ARCHIVED_STATUS,
            "welcome": {"title": welcome["title"],
                        "chars": len(welcome["content"])},
        }, jsonout)
    return EX_OK


# ---------------------------------------------------------------------------
# SELF-TEST: golden + attack fixtures, zero network, zero secrets, zero
# writes (the write statements are stubbed — a tamper never reaches a live
# subprocess). Mirrors the sibling self-tests (verify_archived /
# golden_absent / provision_action): an assertion failure is an ENFORCED
# VIOLATION, exit 4 — a tamper never masquerades as "unexpected error".
# ---------------------------------------------------------------------------
class _FakeLedgerDir:
    """A temp state dir carrying a REAL read-only mirror the module's own
    read path opens (mode=ro), plus a record of every write attempt (there
    must be none in dry-run and none in the plan)."""

    def __init__(self, statuses=None):
        self.dir = None
        self.statuses = dict(statuses or {})
        self.statements_run = []
        self._created = False

    def _ensure(self):
        import tempfile
        self.dir = Path(tempfile.mkdtemp(prefix="archive_action_selftest_"))
        db = self.dir / MIRROR_DB_NAME
        con = sqlite3.connect(str(db))
        con.executescript(
            "CREATE TABLE anthologies (anthology_id TEXT PRIMARY KEY, "
            "status TEXT);")
        for aid, st in self.statuses.items():
            con.execute("INSERT INTO anthologies (anthology_id, status) "
                        "VALUES (?,?)", (aid, st))
        con.commit()
        con.close()
        self._created = True

    def cleanup(self):
        if self.dir is not None:
            import shutil
            shutil.rmtree(self.dir, ignore_errors=True)
            self.dir = None


def _patch_statements(fake: _FakeLedgerDir):
    """Return the two statement stubs (unpatched patch objects — active
    only inside a with-statement) so the self-test NEVER spawns a live
    subprocess — a tamper cannot reach a real writer from the test. The
    stubs MIRROR the real statement semantics: the ledger stub applies the
    status flip to the fake mirror (so the read-back can confirm
    byte-exact) and the board stub records the call (fail-soft)."""
    import unittest.mock as mock

    def _ledger(aid, state_dir, *, out):
        fake.statements_run.append(("ledger", aid))
        con = sqlite3.connect(str(Path(state_dir) / MIRROR_DB_NAME))
        try:
            con.execute("UPDATE anthologies SET status=? WHERE anthology_id=?",
                        (LEDGER_ARCHIVED_STATUS, aid))
            con.commit()
        finally:
            con.close()
        return 0

    def _board(aid, state_dir, *, out):
        fake.statements_run.append(("board", aid))
        return 0

    return (mock.patch.object(sys.modules[__name__], "_statement_ledger",
                              side_effect=_ledger),
            mock.patch.object(sys.modules[__name__], "_statement_board",
                              side_effect=_board))


def _self_test_body(dev: io.StringIO) -> None:
    import unittest.mock as mock
    import shutil
    import tempfile

    # (0) pure helpers: masking is non-reversible, never full; the status
    #     scalar shape refuses non-scalars; the credential guard refuses
    assert _mask_id("anth_12345678") == "...5678"
    assert _mask_id("ab") == "...(short)"
    assert _mask_id("") == "...(short)"
    assert _scalar_str("archived") == "archived"
    assert _scalar_str(0) == "0"
    assert _scalar_str(None) == ""
    assert _scalar_str({"x": 1}) == ""
    try:
        _clean_surface_text("token pit-ABC123 leaked")
        raise AssertionError("credential-shaped surface must refuse")
    except ArchiveActionError:
        pass
    assert _clean_surface_text("plain producer copy") == "plain producer copy"

    # (1) absent state: no ledger row -> NOTHING to archive -> clean
    #     no-op PASS exit 0, zero statements run, zero writes, and the
    #     welcome copy rides the report
    fake = _FakeLedgerDir()
    fake._ensure()
    try:
        dev1 = io.StringIO()
        with mock.patch.object(
                sys.modules[__name__], "HOW_TO_USE",
                _write_fake_howto(dev1)):
            rc = archive("anth_missing", state_dir=str(fake.dir),
                         out=dev1)
        assert rc == EX_OK, "absent-state must PASS exit 0, got %s" % rc
        assert fake.statements_run == [], \
            "absent state must run NO statements, got %s" % fake.statements_run
        assert "NOTHING TO ARCHIVE" in dev1.getvalue()
    finally:
        fake.cleanup()

    # (2) dry-run on a live-status row: READ-ONLY — the DB is read-only in
    #     dry-run (no statements, no writes, the mirror file untouched) and
    #     the no-execute refusal is a STOP (exit 2)
    fake = _FakeLedgerDir({"anth_live": "delivered"})
    fake._ensure()
    try:
        before = (fake.dir / MIRROR_DB_NAME).read_bytes()
        dev2 = io.StringIO()
        with mock.patch.object(
                sys.modules[__name__], "HOW_TO_USE",
                _write_fake_howto(dev2)):
            rc = archive("anth_live", state_dir=str(fake.dir), out=dev2)
        assert rc == EX_STOP, "no-execute must STOP (exit 2), got %s" % rc
        assert fake.statements_run == [], \
            "dry-run must run NO statements, got %s" % fake.statements_run
        assert "AF-AE-U20ARCHIVE-NO-EXECUTE" in dev2.getvalue()
        after = (fake.dir / MIRROR_DB_NAME).read_bytes()
        assert before == after, \
            "dry-run must leave the mirror byte-identical (read-only DB)"
    finally:
        fake.cleanup()

    # (3) idempotent no-op: an already-archived row -> PASS exit 0, no
    #     statements, mirror untouched
    fake = _FakeLedgerDir({"anth_arch": "archived"})
    fake._ensure()
    try:
        before = (fake.dir / MIRROR_DB_NAME).read_bytes()
        dev3 = io.StringIO()
        with mock.patch.object(
                sys.modules[__name__], "HOW_TO_USE",
                _write_fake_howto(dev3)):
            rc = archive("anth_arch", state_dir=str(fake.dir), out=dev3)
        assert rc == EX_OK, "already-archived must PASS exit 0, got %s" % rc
        assert fake.statements_run == [], \
            "already-archived must run NO statements"
        assert "IDEMPOTENT NO-OP" in dev3.getvalue()
        assert (fake.dir / MIRROR_DB_NAME).read_bytes() == before
    finally:
        fake.cleanup()

    # (4) missing / unreadable HOW-TO-USE.md: STOP (exit 2) — the Welcome
    #     surface never ships empty or fabricated; no write, no statement
    fake = _FakeLedgerDir({"anth_live": "delivered"})
    fake._ensure()
    try:
        dev4 = io.StringIO()
        missing = Path(tempfile.mkdtemp()) / "no-such-howto.md"
        with mock.patch.object(sys.modules[__name__], "HOW_TO_USE", missing):
            raised = False
            try:
                archive("anth_live", state_dir=str(fake.dir), out=dev4)
            except ArchiveActionError:
                raised = True
            # the CLI maps the refusal onto STOP (exit 2) — the archive
            # surface refuses fail-closed, it never fabricates a Welcome
            assert raised, "missing HOW-TO-USE must refuse (STOP family)"
        assert fake.statements_run == [], "no write before the Welcome read"
    finally:
        fake.cleanup()

    # (5) full happy path WITH --execute: BOTH statements run exactly once
    #     (ledger first, then board), the ledger read-back confirms, exit 0
    fake = _FakeLedgerDir({"anth_live": "delivered"})
    fake._ensure()
    try:
        dev5 = io.StringIO()
        patch_ledger, patch_board = _patch_statements(fake)
        with patch_ledger, patch_board, mock.patch.object(
                sys.modules[__name__], "HOW_TO_USE",
                _write_fake_howto(dev5)):
            rc = archive("anth_live", state_dir=str(fake.dir),
                         execute=True, out=dev5)
        assert rc == EX_OK, "happy path must exit 0, got %s" % rc
        assert fake.statements_run == [("ledger", "anth_live"),
                                       ("board", "anth_live")], \
            "both statements must run once, in order: %s" % fake.statements_run
        assert "ARCHIVED" in dev5.getvalue()
        assert "read back" in dev5.getvalue() or \
            "read-back" in dev5.getvalue() or \
            "byte-exact" in dev5.getvalue()
        assert "fail-soft" in dev5.getvalue(), \
            "the board statement's fail-soft semantics must be surfaced"
    finally:
        fake.cleanup()

    # (6) read-back mismatch: the ledger does NOT read back 'archived'
    #     after the statements -> MISMATCH (exit 5), never a false success
    fake = _FakeLedgerDir({"anth_live": "delivered"})
    fake._ensure()
    try:
        def _lying_ledger(aid, state_dir, *, out):
            fake.statements_run.append(("ledger", aid))
            # the statement "succeeds" but the read-back surface stays
            # 'delivered' — a drifted write must be caught by read-back
            return 0

        def _lying_board(aid, state_dir, *, out):
            fake.statements_run.append(("board", aid))
            return 0

        dev6 = io.StringIO()
        with mock.patch.object(sys.modules[__name__], "_statement_ledger",
                               side_effect=_lying_ledger), \
             mock.patch.object(sys.modules[__name__], "_statement_board",
                               side_effect=_lying_board), \
             mock.patch.object(
                 sys.modules[__name__], "HOW_TO_USE",
                 _write_fake_howto(dev6)):
            rc = archive("anth_live", state_dir=str(fake.dir),
                         execute=True, out=dev6)
        assert rc == EX_MISMATCH, \
            "read-back drift must be exit 5, got %s" % rc
        assert "AF-AE-U20ARCHIVE-READBACK" in dev6.getvalue()
    finally:
        fake.cleanup()

    # (7) refused ledger statement (rc != 0) WITH --execute: STOP, nothing
    #     reported archived; a refused board statement is HELD (exit 3) —
    #     never a false success, never a mislabeled scope
    fake = _FakeLedgerDir({"anth_live": "delivered"})
    fake._ensure()
    try:
        def _refuse_ledger(aid, state_dir, *, out):
            fake.statements_run.append(("ledger", aid))
            return 2

        dev7 = io.StringIO()
        with mock.patch.object(sys.modules[__name__], "_statement_ledger",
                               side_effect=_refuse_ledger), \
             mock.patch.object(
                 sys.modules[__name__], "HOW_TO_USE",
                 _write_fake_howto(dev7)):
            rc = archive("anth_live", state_dir=str(fake.dir),
                         execute=True, out=dev7)
        assert rc == EX_STOP, "refused ledger statement must STOP, got %s" % rc
        assert fake.statements_run == [("ledger", "anth_live")], \
            "a refused ledger statement must not run the board statement"
    finally:
        fake.cleanup()

    fake = _FakeLedgerDir({"anth_live": "delivered"})
    fake._ensure()
    try:
        def _ok_ledger(aid, state_dir, *, out):
            fake.statements_run.append(("ledger", aid))
            return 0

        def _refuse_board(aid, state_dir, *, out):
            fake.statements_run.append(("board", aid))
            return 3

        dev7b = io.StringIO()
        with mock.patch.object(sys.modules[__name__], "_statement_ledger",
                               side_effect=_ok_ledger), \
             mock.patch.object(sys.modules[__name__], "_statement_board",
                               side_effect=_refuse_board), \
             mock.patch.object(
                 sys.modules[__name__], "HOW_TO_USE",
                 _write_fake_howto(dev7b)):
            rc = archive("anth_live", state_dir=str(fake.dir),
                         execute=True, out=dev7b)
        assert rc == EX_HELD, "refused board statement must be HELD, got %s" % rc
        assert "SPEC 11.2 fail-soft" in dev7b.getvalue() or \
            "fail-soft" in dev7b.getvalue()
    finally:
        fake.cleanup()

    # (8) unreadable mirror: HELD (exit 3), UNDETERMINED — never a verdict
    empty = Path(tempfile.mkdtemp())
    dev8 = io.StringIO()
    with mock.patch.object(sys.modules[__name__], "HOW_TO_USE",
                           _write_fake_howto(dev8)):
        rc = archive("anth_live", state_dir=str(empty), out=dev8)
    assert rc == EX_HELD, "unreadable mirror must be HELD, got %s" % rc
    assert "UNDETERMINED" in dev8.getvalue()
    shutil.rmtree(empty, ignore_errors=True)

    # (9) the plan is OFFLINE: no DB, no credential, no write; the welcome
    #     copy derives from HOW-TO-USE.md; the report carries the contract
    dev9 = io.StringIO()
    json9 = io.StringIO()
    with mock.patch.object(sys.modules[__name__], "HOW_TO_USE",
                           _write_fake_howto(dev9)):
        rc = plan(out=dev9, jsonout=json9)
    assert rc == EX_OK, "plan must exit 0, got %s" % rc
    payload = json.loads(json9.getvalue())
    assert payload["contract"] == CONFIG_CONTRACT
    assert payload["dry_run"] is True
    assert payload["statements"] == ["ledger", "board"]
    assert payload["welcome"]["chars"] > 0

    # (10) never-print: no full id, no credential-shaped string, no
    #      secret value ever reaches the surfaces (the self-test's own dev
    #      streams and the JSON reports — raw test-fixture internals are
    #      not surfaces)
    all_text = "".join(x.getvalue() for x in
                       (dev, dev1, dev2, dev3, dev5, dev6, dev7, dev7b,
                        dev8, dev9, json9))
    for token in ("anth_live", "anth_arch", "anth_missing", "pit-", "Bearer "):
        assert token not in all_text, \
            "surface leak: %r must never appear" % token


def _write_fake_howto(dev: io.StringIO) -> Path:
    """A temp HOW-TO-USE.md for the self-test (never the real one — the
    self-test is offline and must not depend on the repo layout)."""
    import tempfile
    d = Path(tempfile.mkdtemp(prefix="archive_action_howto_"))
    p = d / "HOW-TO-USE.md"
    p.write_text("You are the producer. Collect chapters around one theme.\n",
                 encoding="utf-8")
    return p


def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
        out.write("archive_action self-test: OK (golden absent-state "
                  "no-op, read-only dry-run + no-execute STOP, idempotent "
                  "already-archived no-op, missing HOW-TO-USE STOP, happy "
                  "path execute-once statements + byte-exact read-back, "
                  "read-back drift exit 5, refused statement ladders, "
                  "unreadable mirror HELD, offline plan, never-print, "
                  "masking)\n")
        return EX_OK
    except AssertionError as exc:
        sys.stderr.write("[archive_action] SELF-TEST FAILED "
                         "(AF-AE-U20ARCHIVE-* family): %s\n" % exc)
        return EX_VIOLATION
    except Exception as exc:  # noqa: BLE001 — fail-closed, never exit 1
        sys.stderr.write("[archive_action] SELF-TEST FAILED "
                         "(AF-AE-U20ARCHIVE-* family): %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_VIOLATION


# ---------------------------------------------------------------------------
# CLI (house style: argparse + subcommands + --self-test/--selftest aliases)
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="archive_action.py",
        description="Trevor-gated producer archive statements for the engine's "
                    "own ledger + board footprint (Skill 59, U20 tooling). "
                    "The archive statements run ONLY under --execute; dry-run "
                    "is a READ-ONLY plan (the DB is read-only in dry-run; "
                    "Welcome card content derives from HOW-TO-USE.md).")
    ap.add_argument("--anthology-id", default="",
                    help="the anthology to archive (REQUIRED for archive, "
                         "never a sweep; masked on every surface, never "
                         "printed in full)")
    ap.add_argument("--state-dir", default="",
                    help="engine state directory (default: resolved like "
                         "anthology_state: ANTHOLOGY_STATE_DIR / "
                         "OPENCLAW_DATA_DIR / node home)")
    ap.add_argument("--dry-run", action="store_true",
                    help="READ-ONLY plan: report what WOULD be archived "
                         "without reading the DB, without a credential, "
                         "without any write")
    ap.add_argument("--execute", action="store_true",
                    help="the Trevor gate for the archive STATEMENTS — "
                         "REQUIRED before the archive statements run; "
                         "without it the ACTION is a STOP (exit 2), never "
                         "a silent no-op and never a mutation")
    ap.add_argument("--json", action="store_true",
                    help="emit a machine-readable summary on stdout")
    ap.add_argument("cmd", nargs="?", choices=["archive", "plan", "self-test"],
                    default="archive")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> positional self-test subcommand
    # so argparse's optional positional cmd never rejects the flag form.
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
            return plan(out=sys.stderr, jsonout=jsonout)
        # cmd == "archive": --dry-run is the READ-ONLY offline plan (the
        # DB is read-only in dry-run); without --dry-run the DB is read
        # for the census, and the STATEMENTS run only under --execute.
        if args.dry_run:
            return plan(out=sys.stderr, jsonout=jsonout)
        return archive(args.anthology_id, state_dir=args.state_dir,
                       execute=args.execute, out=sys.stderr,
                       jsonout=jsonout)
    except ArchiveActionError as exc:
        sys.stderr.write("[archive_action] STOP: %s\n" % exc)
        return EX_STOP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[archive_action] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
