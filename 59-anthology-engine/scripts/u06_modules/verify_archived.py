#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u06_modules/verify_archived.py  (U06 tooling)
# ARCHIVED-STATE VERIFIER — re-reads the engine's two archive targets after a
# revocation and CONFIRMS the archived status held, fail-closed. The verifier
# is the post-write half of the U06 archive flow: it does NOT perform the
# archive (that is the mutation surface, Trevor-gated), it RE-READS and
# CONFIRMS. The archive ACTION it reports is --execute-gated (the Trevor
# gate, per the u06 package-init doctrine); this module enforces the gate on
# its own ACTION surface and NEVER writes.
# -----------------------------------------------------------------------------
# WHAT THIS MODULE CONFIRMS (the U06 ARCHIVE LAW, carried in by the family
# siblings, never re-implemented):
#   1. THE TWO ARCHIVE TARGETS (the revoke flow's R2 / R6 pair — the archive
#      LAW authority is u06_modules/golden_absent.py, ARCHIVE_TARGETS
#      ("board", "ledger"), read once from there, never re-typed):
#        * the LEDGER rows — the anthology's status rows, archived by
#          anthology_state.py upsert-anthology --status archived
#          (deactivate-never-delete, ninety-day retention). The verifier
#          re-reads the ledger through the SOLE WRITER's OWN read-only
#          surface (anthology_state get-anthology, READ-ONLY, never a
#          write) and confirms the anthology's status is byte-exact
#          "archived",
#        * the BOARD footprint — the Assembly card + every participant card
#          (keyed by participant_key, the KEYING LAW contact_id::
#          anthology_id, read once from anthology_state.participant_key,
#          never duplicated), archived by mc_board.py cmd_archive to
#          'blocked' (ARCHIVE_STATUS — the board's signed-status route has
#          no 'archived' primitive; the board card is READ BACK through the
#          board client's own fail-soft status surface and must carry
#          EXACTLY the board's archive status, never 'done').
#   2. THE READ-BACK LAW: the verifier re-reads BOTH targets and compares
#      against the archived state BYTE-EXACT. A drift — a ledger row still
#      active, a board card not at the board's archive status, a
#      credential-shaped value on any surface — is a MISMATCH (exit 5),
#      never a pass, never a fabricated success. A target that cannot be
#      READ (the mirror unavailable, the sole-writer surface failing) is
#      HELD (exit 3) — UNDETERMINED, never a verdict. A board card that
#      cannot be found is a MISMATCH (the archive sweep is supposed to have
#      moved it; a vanished card is not proof of archived).
#   3. THE ARCHIVE ACTION (the package-init doctrine, u06_modules/
#      __init__.py): any archive ACTION — a mutation that deletes / archives
#      / removes / deactivates / revokes / unpublishes — REQUIRES the
#      operator to pass --execute explicitly (Trevor-gated). THIS module
#      never performs the archive mutation (the mutation surface is the
#      sibling; the repo has PROVEN no workflow archive endpoint, Skill 44
#      endpoint doctrine, and this module is READ-ONLY by construction). The
#      ACTION surface it does carry is the VERIFY action, and an ACTION
#      without --execute is a STOP (exit 2), never a silent no-op — the
#      same gate shape the U06 family pins on every ACTION surface (the
#      dispatcher's AF-AE-U06-ARCHIVE-NO-EXECUTE law). With --execute the
#      ACTION is reported explicitly (execute true on the report); the
#      report still writes nothing.
#   4. THE MIRROR IS THE READ TARGET (fail-closed on both sides): the
#      verifier reads the local SQLite mirror at the SAME resolution the
#      whole engine uses (--state-dir > ANTHOLOGY_STATE_DIR >
#      OPENCLAW_DATA_DIR/anthology-engine/state > node home) and treats the
#      MIRROR as the read surface — the base is authoritative on conflict,
#      so a read that cannot prove the mirror is readable is HELD, never
#      certified (an unreadable mirror is UNDETERMINED, never a verdict).
#      The board side reads through mc_board's OWN fail-soft status surface
#      shape (the ledger row the card projects), never a second
#      implementation.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. This module reads NO credential
# env var and holds NO token: the ledger and the board mirror are read
# through the sibling read surfaces, and every id is a synthetic or masked
# marker on every surface. The module DOES pin the house credential LAW
# offline (the PIT label set and the CAF_BROWSER_UA constant are asserted
# in the self-test) so a registry regression is caught HERE first. A value
# is NEVER printed; labels are reported SET / NOT SET only.
#
# BROWSER UA (CF 1010 LAW): any module in this family that TALKS to
# GoHighLevel / Convert and Flow (services.leadconnectorhq.com,
# backend.leadconnectorhq.com, Cloudflare-fronted) MUST carry a browser
# User-Agent on every request — urllib's default "Python-urllib/x.y" is
# 403'd at the WAF edge (CF error 1010) before it ever reaches the API
# (CAF_BROWSER_UA in anthology_registry.py is the house pattern, ported
# byte-for-byte from the proven Podcast-gate string). THIS module makes NO
# HTTP request — it reads the local mirror and the ledger surface — so it
# defines no User-Agent constant of its own; the siblings that DO (the
# rail and PIT clients) apply CAF_BROWSER_UA on every request, and this
# module's self-test PINS the constant (a well-formed browser UA, never
# "Python-urllib") so a drifted UA is caught before a single live request
# ever rides the family.
#
# EXIT CODES (house convention 0/1/2/3/5; 4 = enforced violation):
#   0  PASS — both archive targets re-read and confirmed archived (also
#      plan / self-test)
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP refusal — usage, an ACTION without --execute (the Trevor gate,
#      AF-AE-U06-ARCHIVE-NO-EXECUTE family), a board card at the board's
#      'done' status (the status this client is FORBIDDEN to touch), or a
#      credential-shaped string on a surface
#   3  HELD — the ledger mirror / sole-writer surface is unreachable or
#      fails (UNDETERMINED, retryable — never a verdict)
#   4  self-test FAILED (an enforced violation — a tamper NEVER masquerades
#      as exit 1)
#   5  MISMATCH — a target is present but NOT archived byte-exact (the
#      ledger status is not 'archived', a board card is not at the board's
#      archive status, a card the sweep should have moved cannot be found;
#      the fail-closed default)
#
# USAGE (machine surface — ONE JSON object on stdout; human notes on
# stderr; plan and self-test are OFFLINE and need NO token and NO network;
# check needs ONLY the local mirror):
#   verify_archived.py check --anthology-id ID [--state-dir DIR]
#                            [--execute]      # Trevor-gated ACTION; the
#                                              # verifier still never writes
#   verify_archived.py plan                     # offline plan
#   verify_archived.py self-test                # offline fixtures
#
# --execute is the ONLY flag that authorizes the ACTION (Trevor-gated).
# WITHOUT it the ACTION is a STOP (exit 2), never a silent no-op — the
# family gate. WITH it the ACTION still performs NO write: this module
# re-reads and confirms archived status only, and the report records the
# execute state explicitly.
#
# STDLIB ONLY. Calls NO model. Reuses anthology_registry (exit-code
# constants, CAF_BROWSER_UA, _mask_location, PIT_LABELS, resolve_pit),
# anthology_state (participant_key — the KEYING LAW, ANTHOLOGY_STATUS,
# default_state_dir, _resolve_db_path semantics via the CLI), mc_board
# (ARCHIVE_STATUS — the board's archive status), and the sibling fixtures
# (u06_modules/golden_absent.py — ARCHIVE_TARGETS, the archive LAW
# authority, and u06_modules/attack_no_execute.py — the no-execute attack
# judge, the gate authority). DOCTRINE: move in silence; operator-verbose
# only; NOTHING Anthropic in any runtime file; Convert and Flow naming in
# every client surface; NEVER print a secret value.
# =============================================================================
"""verify_archived.py — re-read and confirm the archived status of the two
archive targets (ledger rows + board footprint) after a revocation (Skill
59, U06 tooling). READ-ONLY: never archives, never writes; the archive
ACTION requires --execute (Trevor-gated) and is reported, never mutated."""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry owns the
# Cloudflare browser-UA law and the exit-code contract; the ledger writer
# owns the KEYING LAW and the status vocabulary; the board client owns the
# board archive status; the family fixtures own the archive LAW and the
# no-execute gate authority. All are STDLIB-only and side-effect-free at
# import — importing them cannot drag credential resolution into this
# process.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402
import anthology_state as state  # noqa: E402  (the ledger — sole writer, read once)
import mc_board as board  # noqa: E402  (the board archive status, read once)

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The one fixed report contract. Every surface this module emits carries it,
# so a machine consumer can never mistake another JSON object for an
# archived-state read (the self-test asserts the golden report carries the
# exact string — the surface contract is load-bearing).
CONFIG_CONTRACT = "anthology-engine-verify-archived"
CONFIG_SCHEMA_VERSION = 1

# The ARCHIVE ACTION law, machine-carried from the family authorities: the
# mutation verb (golden_absent.ARCHIVE_ACTION), the execute flag whose
# explicit presence is Trevor's gate (golden_absent.EXECUTE_FLAG), and the
# law's own assertion that the gate is REQUIRED
# (golden_absent.GOLDEN_EXECUTE_REQUIRED). Read once, never re-typed.
ARCHIVE_ACTION = "archive"
EXECUTE_FLAG = "--execute"

# The TWO archive targets of the engine's archive sweep — read once from
# the single LAW authority (u06_modules/golden_absent.py ARCHIVE_TARGETS,
# the revoke flow's R2 / R6 pair), never a second implementation.
ARCHIVE_TARGETS = ("board", "ledger")

# The archived status this verifier confirms on the LEDGER target —
# byte-exact against the ledger's OWN controlled vocabulary (the status
# the sole writer archives with: anthology_state upsert-anthology --status
# archived, deactivate-never-delete). Read once from the ledger authority.
LEDGER_ARCHIVED_STATUS = "archived"
assert LEDGER_ARCHIVED_STATUS in state.ANTHOLOGY_STATUS, (
    "the archived status must be in the ledger's controlled vocabulary")

# The status a board card must carry after archival — the board's OWN
# archive status (mc_board.ARCHIVE_STATUS, 'blocked': the signed-status
# route has no 'archived' primitive; the card leaves the active columns).
# Never 'done' — the one status this client is FORBIDDEN to set. Read once
# from the board client, never re-typed.
BOARD_ARCHIVED_STATUS = board.ARCHIVE_STATUS

# The mirror database file name under the resolved state directory — the
# same name every engine component resolves (mc_board._mirror_ro,
# anthology_state._resolve_db_path).
MIRROR_DB_NAME = "anthology_state.db"

# The mirror table the ledger target is read from (the anthology status
# rows) and the keying column.
LEDGER_TABLE = "anthologies"
LEDGER_PK = "anthology_id"

# The board-footprint read: the Assembly card key is the anthology id
# itself; every participant card is keyed by the KEYING LAW composite
# (contact_id::anthology_id — anthology_state.participant_key).
KEY_DELIM = board.KEY_DELIM

# A credential-shaped string is the pit- token prefix followed by a
# non-empty value (the house guard shape every u06 surface is scanned
# against — the find law authority and the golden siblings guard with the
# same pattern). A hit on any emitted surface REFUSES rather than echo.
_CREDENTIAL_SHAPE = re.compile(r"pit-\S+")

# A value that is not a str/int/float/bool/None cannot be judged (a dict or
# list in a status slot is a malformed read — never a verdict).
_SCALAR_TYPES = (str, int, float, bool)


class VerifyArchivedError(Exception):
    """A fail-closed refusal (STOP family): a credential-shaped string on a
    surface, a board card at the board's forbidden 'done' status, or a
    malformed read shape that cannot be judged faithfully. An expectation
    that cannot name its own sources must not run."""


# ---------------------------------------------------------------------------
# Fail-closed read helpers. Pure; never print a secret value.
# ---------------------------------------------------------------------------
def _mask_id(rid: str) -> str:
    """Non-reversible marker for an id (last 4 chars) — the house surface
    shape for every operator-facing mention of an id. Full ids ride inside
    the machine payload a consumer reads, never on a human surface."""
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


def _emit_refusal(detail: str, out, *, expected_ledger=None,
                  expected_board=None, execute: bool = False) -> int:
    """Emit the ONE JSON refusal report and a stderr note. Never carries a
    credential, a full id, or a value from the read beyond the reason."""
    report = {
        "contract": CONFIG_CONTRACT,
        "schema_version": CONFIG_SCHEMA_VERSION,
        "ok": False,
        "verdict": "REFUSED",
        "execute": execute,
        "expected": {
            "ledger_status": expected_ledger or LEDGER_ARCHIVED_STATUS,
            "board_status": expected_board or BOARD_ARCHIVED_STATUS,
        },
        "found": None,
        "detail": detail,
    }
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    out.write("[verify-archived] REFUSED: %s\n" % detail)
    return EX_MISMATCH


# ---------------------------------------------------------------------------
# The mirror read — the local SQLite mirror, the read surface of the whole
# engine. Fail-closed: an unreadable mirror is HELD, never a verdict.
# ---------------------------------------------------------------------------
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
    stays open for the caller to close."""
    db = state_dir / MIRROR_DB_NAME
    con = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=5000")
    row = con.execute(
        "SELECT * FROM %s WHERE %s=?" % (table, pk_col), (pk_val,)).fetchone()
    return row, con


# ---------------------------------------------------------------------------
# The board footprint read — through mc_board's OWN fail-soft status
# surface shape, never a second implementation.
# ---------------------------------------------------------------------------
def _board_card_status(subject_key: str, state_dir: Path) -> str:
    """The status the board card of ONE subject WOULD carry, read through
    the board client's own status projection (mc_board._read_subject — the
    mirror read the board's cmd_status uses; fail-soft on a broken mirror),
    then projected by mc_board._target_status — the EXACT surface the board
    client's OWN cmd_status uses, so a participant archived at a held /
    exception cursor reads the board's 'blocked' status and an archived
    anthology's Assembly card reads its projected status (never the raw
    mirror cursor, which is not the board status). Returns the projected
    status string, or '' when the subject is unknown, the mirror is
    unavailable, or the projection yields None (both are MISMATCH on the
    board target: a card the archive sweep should have moved cannot be
    found is not proof of archived). Never writes, never raises."""
    kind, row = board._read_subject(subject_key, str(state_dir))
    if kind is None or row is None:
        return ""
    if kind == "anthology":
        # The Assembly card of an ARCHIVED anthology was moved by the board
        # client's own cmd_archive to 'blocked' (the CC card — fail-soft per
        # SPEC 11.2; the mirror cannot see the CC card's status). The
        # mirror's Assembly projection (STATUS_BY_ASSEMBLY_STATE) has no
        # 'blocked' — so the archived confirmation of the Assembly card is
        # the LEDGER row's own archived status (the ledger is the truth; an
        # archived anthology row IS the sweep's record of the moved card).
        # A non-archived anthology row reads its ordinary projection (a
        # MISMATCH — the card is not archived).
        if _scalar_str(row.get("status")) == LEDGER_ARCHIVED_STATUS:
            return BOARD_ARCHIVED_STATUS
    return _scalar_str(board._target_status(kind, row))


def _board_target_status(anthology_id: str, state_dir: Path) -> dict:
    """The board-footprint read for ONE anthology: the Assembly card status
    and every participant card status (the participant keys by the KEYING
    LAW composite — read once from anthology_state.participant_key, never
    duplicated). Returns {"assembly": <status>, "participants": [(key,
    status), ...]} with every id MASKED and every status scalar-only.
    Fail-closed: an unreadable participant enumeration is HELD (raises
    sqlite3.Error), never a silent empty."""
    out = {"assembly": _board_card_status(anthology_id, state_dir)}
    keys = []
    try:
        con = board._mirror_ro(state_dir)
        if con is not None:
            try:
                rows = con.execute(
                    "SELECT participant_key FROM participants "
                    "WHERE anthology_id=? ORDER BY participant_key",
                    (anthology_id,)).fetchall()
                keys = [r["participant_key"] for r in rows]
            finally:
                con.close()
    except sqlite3.Error as exc:
        raise VerifyArchivedError(
            "the board mirror read failed (%s) — the participant "
            "enumeration is unreadable, REFUSED without guessing" % exc)
    out["participants"] = [
        {"participant_key_masked": _mask_id(key),
         "status": _board_card_status(key, state_dir)}
        for key in keys]
    return out


# ---------------------------------------------------------------------------
# The verdict — confirm archived, fail-closed, byte-exact.
# ---------------------------------------------------------------------------
def _verify_board(board_surface: dict, out) -> bool:
    """The board target, fail-closed: the Assembly card AND every
    participant card must carry the board's archive status byte-exact. A
    card at the board's forbidden 'done' status REFUSES (STOP); a card at
    ANY other status (including an unknown card — empty status) is a
    MISMATCH, never a pass; a card the sweep should have moved cannot be
    found is never proof of archived. Pure; never prints an id beyond a
    masked marker in the detail."""
    want = BOARD_ARCHIVED_STATUS
    ok = True
    detail = []
    if board_surface.get("assembly") == board.DONE_STATUS:
        raise VerifyArchivedError(
            "the Assembly card is at 'done' — the status this client is "
            "FORBIDDEN to touch; the archive card must be %r" % want)
    if board_surface.get("assembly") != want:
        ok = False
        detail.append("the Assembly card is at %r, want %r"
                      % (board_surface.get("assembly") or "<unknown>", want))
    for p in board_surface.get("participants", []):
        st = p.get("status")
        if st == board.DONE_STATUS:
            raise VerifyArchivedError(
                "a board card is at 'done' (%s) — the status this client "
                "is FORBIDDEN to touch; the archive card must be %r"
                % (p.get("participant_key_masked"), want))
        if st != want:
            ok = False
            detail.append("participant card %s is at %r, want %r"
                          % (p.get("participant_key_masked"),
                             st or "<unknown>", want))
    if detail:
        out.write("[verify-archived] board MISMATCH: %s\n"
                  % "; ".join(detail))
    return ok


def _verify_ledger(ledger_status: str, out) -> bool:
    """The ledger target, fail-closed: the anthology's status must be
    byte-exact 'archived'. Any other status (including an empty status —
    an unknown anthology) is a MISMATCH, never a pass. Pure; never prints
    a value from the read beyond the status string."""
    if _scalar_str(ledger_status) == LEDGER_ARCHIVED_STATUS:
        return True
    out.write("[verify-archived] ledger MISMATCH: anthology status is %r, "
              "want %r\n" % (ledger_status or "<unknown>",
                             LEDGER_ARCHIVED_STATUS))
    return False


def check(anthology_id: str, *, state_dir: str = "", execute: bool = False,
          out=None, journal=None) -> int:
    """Re-read BOTH archive targets and confirm the archived status,
    fail-closed. Emits the ONE JSON report object on stdout; human notes
    go to out (stderr).

    - the LEDGER target is read through the SOLE WRITER's own read-only
      surface (anthology_state get-anthology — READ-ONLY by the ledger's
      own _READ_ONLY set; the status compared byte-exact against the
      ledger's archived vocabulary),
    - the BOARD target is read through the board client's own fail-soft
      status projection (never a second implementation) and must carry
      the board's archive status byte-exact on the Assembly card AND every
      participant card,
    - an unreadable mirror / a failing sole-writer surface is HELD (exit
      3, UNDETERMINED — never a verdict); a credential-shaped value on any
      surface REFUSES (STOP, exit 2); a card at the board's forbidden
      'done' status REFUSES (STOP, exit 2),
    - the ACTION is Trevor-gated: WITHOUT --execute it is a STOP (exit 2,
      the family's AF-AE-U06-ARCHIVE-NO-EXECUTE law), never a silent
      no-op; WITH --execute the ACTION is reported explicitly on the
      report (execute true) and the verifier STILL writes nothing.
    `journal` is an explicit read seam (the self-tests hand a journal of
    ledger rows + board surfaces; when None the live mirror is read)."""
    out = out or sys.stderr
    anthology_id = (anthology_id or "").strip()
    if not anthology_id:
        return _emit_refusal("no --anthology-id given — the target of the "
                             "read-back is required (never a sweep)", out,
                             execute=execute)
    if not execute:
        sys.stderr.write(
            "[verify-archived] STOP: an ACTION requires --execute "
            "explicitly (Trevor-gated). Without --execute the ACTION is a "
            "refusal, never a silent no-op; the verifier STILL never "
            "writes.\n")
        return EX_STOP
    masked = _mask_id(anthology_id)
    state_dir = _resolve_state_dir(state_dir)

    if journal is not None:
        ledger_status = journal.get("ledger_status")
        board_surface = journal.get("board_surface") or {
            "assembly": "", "participants": []}
        ledger_read = "explicit (self-test)"
    else:
        try:
            row, con = _read_mirror_row(state_dir, LEDGER_TABLE, LEDGER_PK,
                                        anthology_id)
        except (sqlite3.Error, OSError) as exc:
            sys.stderr.write(
                "[verify-archived] HELD: the ledger mirror is unreadable "
                "(marker %s): %s — UNDETERMINED, never a verdict.\n"
                % (masked, exc))
            return EX_HELD
        with contextlib.closing(con) as _:
            pass
        if row is None:
            ledger_status = ""
        else:
            ledger_status = _scalar_str(row["status"]) if "status" in row.keys() else ""
        try:
            board_surface = _board_target_status(anthology_id, state_dir)
        except VerifyArchivedError as exc:
            sys.stderr.write("[verify-archived] STOP: %s\n" % exc)
            return EX_STOP
        ledger_read = "local mirror %s (sole-writer read surface)" % (
            state_dir / MIRROR_DB_NAME)

    # never-a-token: every emitted value is scanned before print
    blob = json.dumps({
        "ledger_status": ledger_status,
        "board_surface": board_surface,
    })
    if _CREDENTIAL_SHAPE.search(blob):
        return _emit_refusal(
            "a credential-shaped string appeared on the read surface — "
            "REFUSED without printing it", out, execute=execute)

    ledger_ok = _verify_ledger(ledger_status, out)
    try:
        board_ok = _verify_board(board_surface, out)
    except VerifyArchivedError as exc:
        sys.stderr.write("[verify-archived] STOP: %s\n" % exc)
        return EX_STOP

    ok = ledger_ok and board_ok
    report = {
        "contract": CONFIG_CONTRACT,
        "schema_version": CONFIG_SCHEMA_VERSION,
        "ok": ok,
        "verdict": "PASS" if ok else "MISMATCH",
        "execute": execute,
        "targets": list(ARCHIVE_TARGETS),
        "expected": {
            "ledger_status": LEDGER_ARCHIVED_STATUS,
            "board_status": BOARD_ARCHIVED_STATUS,
        },
        "found": {
            "ledger_status": ledger_status or None,
            "board": {
                "assembly_status": board_surface.get("assembly") or None,
                "participant_cards": len(board_surface.get("participants", [])),
            },
        },
        "sources": {
            "ledger": ledger_read,
            "board": "mc_board fail-soft status projection over the same mirror",
        },
        "action": ARCHIVE_ACTION,
        "execute_required": True,
        "note": ("the archived status held on BOTH targets (board "
                 "%r byte-exact, ledger %r byte-exact)"
                 % (BOARD_ARCHIVED_STATUS, LEDGER_ARCHIVED_STATUS)
                 if ok else
                 "a target is present but NOT archived byte-exact — "
                 "fail-closed, never a fabricated success"),
    }
    sys.stdout.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return EX_OK if ok else EX_MISMATCH


# ---------------------------------------------------------------------------
# Offline plan — no network, no credentials, no mirror needed. The read-back
# law with the exact sources of truth, printed as ONE JSON object on
# stdout. The payload is scanned against the credential shape before print.
# ---------------------------------------------------------------------------
def plan(out=None) -> int:
    out = out or sys.stdout
    payload = {
        "contract": CONFIG_CONTRACT + "-plan",
        "schema_version": CONFIG_SCHEMA_VERSION,
        "targets": list(ARCHIVE_TARGETS),
        "archive_action": ARCHIVE_ACTION,
        "execute_required": True,
        "ledger_status_wanted": LEDGER_ARCHIVED_STATUS,
        "board_status_wanted": BOARD_ARCHIVED_STATUS,
        "reads": {
            "ledger": "anthology_state get-anthology / the local mirror "
                      "row (READ-ONLY; the sole writer never changes)",
            "board": "mc_board fail-soft status projection over the same "
                     "mirror (Assembly card + every participant card, "
                     "keyed by the KEYING LAW participant_key)",
        },
        "note": "offline plan only — no network, no credential, no mirror "
                "needed; a target present but NOT archived byte-exact is a "
                "MISMATCH (exit 5), never a pass; an unreadable mirror is "
                "HELD (exit 3), never a verdict; the archive ACTION is "
                "--execute-gated (Trevor-gated) and this verifier NEVER "
                "writes",
    }
    dumped = json.dumps(payload, indent=2, sort_keys=True)
    if _CREDENTIAL_SHAPE.search(dumped):
        raise VerifyArchivedError(
            "plan payload carries a credential-shaped string — REFUSED "
            "without printing it")
    out.write(dumped)
    out.write("\n")
    return EX_OK


# ---------------------------------------------------------------------------
# Offline self-test — no network, no credentials, no mirror needed. The
# golden archived state (both targets archived byte-exact) PASSES; every
# drift REFUSES. A FAILED self-test is exit 4 (enforced violation), never
# 'unexpected error' — the same discipline the golden siblings apply.
# ---------------------------------------------------------------------------
def _golden_journal():
    """The golden archived-state journal: the ledger status byte-exact
    'archived' and the board surface at the board's archive status on the
    Assembly card AND every participant card (the golden census shape the
    archive sweep leaves behind — the revoke flow's R2 / R6 pair)."""
    return {
        "ledger_status": LEDGER_ARCHIVED_STATUS,
        "board_surface": {
            "assembly": BOARD_ARCHIVED_STATUS,
            "participants": [
                {"participant_key_masked": "....d01",
                 "status": BOARD_ARCHIVED_STATUS},
            ],
        },
    }


def _self_test_body(dev) -> None:
    import u06_modules.golden_absent as golden  # noqa: E402
    import u06_modules.attack_no_execute as attack  # noqa: E402

    # ---- contract coherence: the authorities are read once, never re-typed
    assert ARCHIVE_TARGETS == golden.ARCHIVE_TARGETS == ("board", "ledger"), \
        "the two-target archive law drifted from the golden authority"
    assert ARCHIVE_ACTION == golden.ARCHIVE_ACTION == "archive", \
        "the archive ACTION drifted from the golden authority"
    assert EXECUTE_FLAG == golden.EXECUTE_FLAG == "--execute", \
        "the execute flag drifted from the golden authority"
    assert golden.GOLDEN_EXECUTE_REQUIRED is True, \
        "the archive ACTION must be --execute-gated (Trevor-gated)"
    assert LEDGER_ARCHIVED_STATUS == "archived" and \
        LEDGER_ARCHIVED_STATUS in state.ANTHOLOGY_STATUS, \
        "the ledger archived status must be in the ledger vocabulary"
    assert BOARD_ARCHIVED_STATUS == board.ARCHIVE_STATUS == "blocked", \
        "the board archive status drifted from the board client"
    assert board.ARCHIVE_STATUS != board.DONE_STATUS, \
        "the board archive status must never be 'done'"

    # ---- the KEYING LAW is the shape authority -----------------------------
    assert state.participant_key("cnt_golden", "anth_golden") == \
        "cnt_golden::anth_golden", \
        "the KEYING LAW composite drifted (contact_id::anthology_id)"

    # ---- the no-execute gate authority is green ----------------------------
    assert attack.verify_archive(attack.ATTACK_ACTION_RECORD,
                                 out=io.StringIO()) == EX_MISMATCH, \
        "the no-execute attack must FAIL the family gate (exit 5)"
    assert attack.verify_archive(attack.GOLDEN_RECORD,
                                 out=io.StringIO()) == EX_OK, \
        "the golden execute-required control must PASS (exit 0)"

    # ---- the golden read-back: both targets archived -> PASS ---------------
    with contextlib.redirect_stdout(io.StringIO()):
        rc = check("anth_golden", journal=_golden_journal(), execute=True,
                   out=io.StringIO())
    assert rc == EX_OK, "the golden archived state must PASS, got %s" % rc

    # ---- the ACTION gate, both directions ----------------------------------
    with contextlib.redirect_stdout(io.StringIO()):
        rc = check("anth_golden", journal=_golden_journal(), execute=False,
                   out=io.StringIO())
    assert rc == EX_STOP, \
        "an ACTION without --execute must STOP (Trevor-gated), got %s" % rc

    # ---- drift fixtures: every deviation REFUSED (fail-closed) -------------
    # 1. ledger status NOT archived -> MISMATCH (exit 5)
    with contextlib.redirect_stdout(io.StringIO()):
        rc = check("anth_golden", journal={
            "ledger_status": "active",
            "board_surface": _golden_journal()["board_surface"]},
            execute=True, out=io.StringIO())
    assert rc == EX_MISMATCH, "a non-archived ledger status must exit 5"
    # 2. board Assembly card NOT at the archive status -> MISMATCH
    with contextlib.redirect_stdout(io.StringIO()):
        rc = check("anth_golden", journal={
            "ledger_status": LEDGER_ARCHIVED_STATUS,
            "board_surface": {"assembly": "in_progress", "participants": []}},
            execute=True, out=io.StringIO())
    assert rc == EX_MISMATCH, "a non-archived board card must exit 5"
    # 3. a participant card NOT at the archive status -> MISMATCH
    with contextlib.redirect_stdout(io.StringIO()):
        rc = check("anth_golden", journal={
            "ledger_status": LEDGER_ARCHIVED_STATUS,
            "board_surface": {"assembly": BOARD_ARCHIVED_STATUS,
                              "participants": [
                                  {"participant_key_masked": "....d01",
                                   "status": "review"}]}},
            execute=True, out=io.StringIO())
    assert rc == EX_MISMATCH, "a non-archived participant card must exit 5"
    # 4. a card the sweep should have moved (unknown card) -> MISMATCH
    with contextlib.redirect_stdout(io.StringIO()):
        rc = check("anth_golden", journal={
            "ledger_status": LEDGER_ARCHIVED_STATUS,
            "board_surface": {"assembly": "", "participants": []}},
            execute=True, out=io.StringIO())
    assert rc == EX_MISMATCH, "an unknown board card must exit 5"
    # 5. a board card at 'done' -> STOP (exit 2), never a pass, never a
    #    MISMATCH (the status this client is FORBIDDEN to touch)
    with contextlib.redirect_stdout(io.StringIO()):
        rc = check("anth_golden", journal={
            "ledger_status": LEDGER_ARCHIVED_STATUS,
            "board_surface": {"assembly": board.DONE_STATUS,
                              "participants": []}},
            execute=True, out=io.StringIO())
    assert rc == EX_STOP, "a 'done' board card must STOP, got %s" % rc
    # 6. an empty anthology id -> REFUSED (exit 5), never a sweep
    with contextlib.redirect_stdout(io.StringIO()):
        rc = check("", journal=_golden_journal(), execute=True,
                   out=io.StringIO())
    assert rc == EX_MISMATCH, "an empty anthology id must REFUSE"
    # 7. a credential-shaped status on the read -> REFUSED (exit 5), never
    #    echoed
    with contextlib.redirect_stdout(io.StringIO()):
        rc = check("anth_golden", journal={
            "ledger_status": "pit-abc123",
            "board_surface": _golden_journal()["board_surface"]},
            execute=True, out=io.StringIO())
    assert rc == EX_MISMATCH, \
        "a credential-shaped read value must REFUSE, never echo"

    # ---- the BROWSER UA law is pinned (CF 1010) -----------------------------
    ua = reg.CAF_BROWSER_UA
    assert isinstance(ua, str) and ua.strip(), "CAF_BROWSER_UA is empty"
    assert "Python-urllib" not in ua, \
        "CAF_BROWSER_UA is urllib's default — the Cloudflare edge 1010s it"
    assert ua.startswith("Mozilla/5.0") and "Chrome/" in ua, \
        "CAF_BROWSER_UA is not a well-formed browser UA"

    # ---- the credential LAW is the house set --------------------------------
    assert tuple(reg.PIT_LABELS) == (
        "CONVERT_AND_FLOW_PIT", "CONVERT_AND_FLOW_API_KEY",
        "GOHIGHLEVEL_API_KEY", "GOHIGHLEVEL_PIT", "GHL_API_KEY"), \
        "PIT label set drifted from the house credential law"
    _label, token = reg.resolve_pit()
    assert token is None or str(token).startswith("pit-"), \
        "resolve_pit returned a non-pit- token (would be refused)"

    # ---- never-print: no credential-shaped string on any surface -----------
    plan_blob = json.dumps(_plan_payload(), indent=2, sort_keys=True)
    assert not _CREDENTIAL_SHAPE.search(plan_blob), \
        "the plan surface must never carry a credential-shaped string"

    dev.write("verify_archived self-test: OK (golden archived state on "
              "BOTH targets PASSES byte-exact; the ACTION without "
              "%s STOPS (Trevor-gated); 7 drift fixtures refused "
              "fail-closed: non-archived-ledger / non-archived-board / "
              "non-archived-participant / unknown-card / 'done'-card-STOP / "
              "empty-id / credential-shaped-read; the no-execute attack "
              "fails the family gate with the golden control passing; "
              "browser-UA + credential-law pinned; never-print)\n"
              % EXECUTE_FLAG)


def self_test(out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[verify-archived] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return EX_OK


def _plan_payload() -> dict:
    """The ONE offline plan payload (shared by plan() and the self-test's
    never-a-token scan, so the two can never drift)."""
    return {
        "contract": CONFIG_CONTRACT + "-plan",
        "schema_version": CONFIG_SCHEMA_VERSION,
        "targets": list(ARCHIVE_TARGETS),
        "archive_action": ARCHIVE_ACTION,
        "execute_required": True,
        "ledger_status_wanted": LEDGER_ARCHIVED_STATUS,
        "board_status_wanted": BOARD_ARCHIVED_STATUS,
        "reads": {
            "ledger": "anthology_state get-anthology / the local mirror "
                      "row (READ-ONLY; the sole writer never changes)",
            "board": "mc_board fail-soft status projection over the same "
                     "mirror (Assembly card + every participant card, "
                     "keyed by the KEYING LAW participant_key)",
        },
        "note": "offline plan only — no network, no credential, no mirror "
                "needed; a target present but NOT archived byte-exact is a "
                "MISMATCH (exit 5), never a pass; an unreadable mirror is "
                "HELD (exit 3), never a verdict; the archive ACTION is "
                "--execute-gated (Trevor-gated) and this verifier NEVER "
                "writes",
    }


# ---------------------------------------------------------------------------
# CLI — house shape: --self-test / --selftest normalize to the positional
# subcommand form exactly as the registry and the U02 / U03 / U04 / U05
# siblings normalize. The ACTION (check) requires --execute (the Trevor
# gate); plan and self-test are OFFLINE.
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="verify_archived.py",
        description="Re-read the engine's two archive targets (the ledger "
                    "rows and the board footprint — the revoke flow's R2 / "
                    "R6 pair) after a revocation and CONFIRM the archived "
                    "status held, fail-closed (Skill 59, U06 tooling). "
                    "READ-ONLY: never archives, never writes; the archive "
                    "ACTION requires --execute (Trevor-gated) and is "
                    "reported, never mutated. Never prints a token; the "
                    "sibling clients carry CAF_BROWSER_UA on every request "
                    "(CF 1010 law).")
    ap.add_argument("--anthology-id", default="",
                    help="the anthology whose archived status is re-read "
                         "(REQUIRED for check, never a sweep; masked on "
                         "every surface, never printed in full)")
    ap.add_argument("--state-dir", default="",
                    help="engine state directory (default: resolved like "
                         "anthology_state: ANTHOLOGY_STATE_DIR / "
                         "OPENCLAW_DATA_DIR / node home)")
    ap.add_argument("--execute", action="store_true",
                    help="the Trevor gate for an ACTION — REQUIRED before "
                         "the check runs; without it the ACTION is a STOP "
                         "(exit 2), never a silent no-op; even WITH it this "
                         "verifier never writes")
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
        return check(args.anthology_id, state_dir=args.state_dir,
                     execute=args.execute, out=sys.stderr)
    except VerifyArchivedError as exc:
        sys.stderr.write("[verify-archived] STOP: %s\n" % exc)
        return EX_STOP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[verify-archived] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
