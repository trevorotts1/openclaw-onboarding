#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: cc_board_hygiene.py  (U20 tooling)
# CC BOARD-HYGIENE DISPATCHER — the ONE CLI ASSEMBLED from the u20_modules
# family: it imports EVERY module under scripts/u20_modules/ BY NAME
# (importlib, never exec'd from a path; a missing module STOPS, never a
# silent skip) and wires them into ONE CLI whose offline self-test battery
# (golden PASS / the zero-cards attack FAIL) runs before any live surface.
# This file carries NO check logic itself — a family gate is exercised ONLY
# through its module so `--dry-run`, `--self-test`, and the live surfaces
# never drift apart. It is the packaged sibling of scripts/check_intake_fire_scope.py
# (U05, row 57), scripts/archive_legacy_workflows.py (U06, row 58),
# scripts/provision_fields.py (U07, row 59), scripts/build_anthology_forms.py
# (U08/U09, row 60) and scripts/build_anthology_workflows.py (U10/U13, row 61)
# under the ENGINE-MANIFEST row-54 shipping doctrine; the U20 family's OWN
# manifest row is stamped by this assembly (row 62, 2026-08-11).
#
# THE u20_modules FILES (imported by name; each is STDLIB-only and
# self-tests itself — docs_u20.py carries the module inventory as data and
# its self-test proves the tree ships together; the family catalog carries
# NINE inventory rows: the empty package init, the Welcome-card builders
# welcome_builder / welcome_action, the fail-closed mission-control.db
# connector db_connector, the post-action board verifier verify_board, the
# archive statement builder archive_stmt, the producer ledger/board archive
# action archive_action, the zero-cards attack fixture attack_no_cards, the
# golden six-card census fixture golden_6cards, the sibling pytest battery
# test_archive_stmt, and the docs_u20 catalog/drift gate):
#   __init__.py            fail-closed EMPTY package init (pure namespace)
#   welcome_builder.py     the PRODUCER WELCOME CARD BUILDER — HOW-TO-USE.md
#                          becomes the card's body copy by exact section
#                          order; the ONE INSERT into the engine state
#                          database's meta table under 'welcome::producer'
#                          is EXECUTED ONLY under --execute (the Trevor
#                          gate); the engine database is READ-ONLY in every
#                          non-execute path (mode=ro control and read-back);
#                          idempotent by construction; the READ-BACK LAW
#                          holds (a write is never trusted without read-back)
#   welcome_action.py      the ANTHOLOGY WELCOME CARD SEEDER — the fail-
#                          closed, GET-first idempotent seeder that lands
#                          the producer-facing WELCOME card on the client's
#                          Command Center Anthology board (a task row, the
#                          Skill 32 add-department.sh step-3 shape: title
#                          'Welcome to Anthology', status backlog, priority
#                          medium, assigned to the Anthology department-head
#                          agent); the card INSERT runs ONLY under --execute
#                          (AF-AE-WELCOME-NO-EXECUTE otherwise); IDEMPOTENCY
#                          LAW (GET-first by the fixed marker 'Ref:
#                          anthology:welcome:card' — an existing card is
#                          verified and skipped, never a duplicate); READ-
#                          BACK LAW (the seeded row is SELECTed back by its
#                          task id); a missing database is a STOP, never a
#                          write into the unknown
#   db_connector.py        the FAIL-CLOSED SQLITE3 CONNECTOR over the
#                          Command Center mission-control.db — the shared DB
#                          surface the U20 Welcome-card family imports;
#                          default and --dry-run are READ-ONLY (the SQLITE
#                          QUERY-ONLY pragma plus an IMMEDIATE rollback
#                          transaction that is always rolled back); the card
#                          INSERT runs ONLY under --execute (AF-AE-DBC-NO-
#                          EXECUTE); the seed is idempotent (AF-AE-DBC-SEED-
#                          EXISTS, the 'already welcomed' no-op, exit 0); a
#                          missing DB is AF-AE-DBC-NO-DB, never a pass; the
#                          absent-card READ-ONLY report is AF-AE-DBC-NO-
#                          WELCOME (exit 5, names the remediation), never a
#                          pass
#   verify_board.py        the POST-ACTION BOARD VERIFIER — the read-back
#                          half of the Anthology board hygiene ACTION (the
#                          U14 board-hygiene law, carried in from
#                          u14-anthology-board-hygiene.py, never re-typed):
#                          re-reads the Command Center's Anthology board
#                          (workspace 'anthology', open board only) and
#                          confirms ZERO live ZZZ/SYNTHETIC drill cards and
#                          the byte-exact 'Welcome to Anthology' card
#                          present; READ-ONLY by construction (sqlite URI
#                          mode=ro); the VERIFY ACTION requires --execute
#                          (AF-AE-VRBOARD-NO-EXECUTE, exit 2) and even WITH
#                          it never writes; a missing DB / missing tasks
#                          table is a STOP (AF-AE-VRBOARD-NO-DB /
#                          AF-AE-VRBOARD-TASKS-MISSING), a locked / busy DB
#                          is HELD (exit 3); live drills are AF-AE-VRBOARD-
#                          DRILLS-LIVE (exit 5), an absent Welcome card is
#                          AF-AE-VRBOARD-NO-WELCOME (exit 5) — never a
#                          fabricated success
#   archive_stmt.py        the BOARD ARCHIVE STATEMENT BUILDER — builds the
#                          UPDATE statements that soft-archive the Anthology
#                          board's SIX pinned debris cards (tasks.archived_at
#                          on mission-control.db; the fixed census verified
#                          against the operator box's own Command Center
#                          backups 2026-08-11); the statements run ONLY
#                          under --execute (AF-AE-ARCHSTMT-NO-EXECUTE, exit
#                          2); IDEMPOTENCY LAW (census-first: an already-
#                          archived card is verified and skipped, a board
#                          whose six cards are all archived is a clean no-op
#                          PASS); READ-BACK LAW (the six cards are re-read
#                          and every one must be archived — AF-AE-ARCHSTMT-
#                          READBACK, exit 5 / HELD exit 3)
#   archive_action.py      the ARCHIVE ACTION — the Trevor-gated producer
#                          archive surface for the engine's OWN ledger (the
#                          local SQLite mirror, anthology_state.py — the
#                          SOLE writer) plus the Welcome card content the
#                          producer's board carries; the archive statements
#                          run ONLY under --execute (AF-AE-U20ARCHIVE-NO-
#                          EXECUTE, exit 2); the absent-state law (no ledger
#                          row -> clean no-op PASS) and the idempotent no-op
#                          (already archived -> PASS) hold; the READ-BACK
#                          LAW holds (the ledger target is re-read through
#                          the SOLE WRITER's own read-only surface and must
#                          match byte-exact — AF-AE-U20ARCHIVE-READBACK-
#                          MISMATCH, exit 5); the Welcome card derives from
#                          HOW-TO-USE.md as copy, never a write
#   attack_no_cards.py     the ZERO-CARDS ATTACK FIXTURE — the attack half
#                          of the U20 welcome pair: the board census that
#                          carries ZERO cards, the exact state where a
#                          welcome-sync would need a WRITE to create the
#                          Welcome card, judged a clean PASS no-op (nothing
#                          to sync, nothing to write — the Welcome card
#                          ships as copy from HOW-TO-USE.md, the engine's
#                          database is READ-ONLY in dry-run); a census that
#                          carries cards is REFUSED (AF-AE-WELCOME-CARDS-
#                          PRESENT), a malformed or credential-shaped census
#                          is REFUSED (AF-AE-WELCOME-MALFORMED) — the
#                          fixture is DATA and never writes
#   golden_6cards.py       the GOLDEN SIX-CARD census fixture — the
#                          canonical SIX-CARD board record (the Welcome card
#                          first, then the Assembly card, then the four
#                          participant cards under the KEYING LAW
#                          contact_id::anthology_id read once from
#                          anthology_state.participant_key), every status
#                          byte-exact against the board client's own maps,
#                          never 'done', the masked-id discipline on every
#                          surface, and the execute_required truth; the
#                          fail-closed judge passes the golden census
#                          byte-exact and refuses any drift (exit 5)
#   test_archive_stmt.py   the UNIT-TEST BATTERY for the U20 archive ACTION
#                          (provenance only — the independent pytest battery)
#   docs_u20.py            the U20 tooling README/catalog data + drift gate
#                          (the module inventory as DATA; its self-test
#                          proves the tree ships together)
#
# THE U20 ATTACK (the offline self-test proves it REFUSED — golden PASS /
# attack FAIL; a tamper NEVER masquerades as exit 1):
#   attack_no_cards        — the EMPTY board census is the golden no-op PASS
#                            ({"cards": []} -> PASS, exit 0) while a census
#                            that carries a card is REFUSED (exit 5,
#                            AF-AE-WELCOME-CARDS-PRESENT) — every pass/fail
#                            split discriminates the ONE-variable boundary,
#                            never a broken instrument (the negative-result
#                            contract)
#
# WHAT THIS GATES (MASTER-SPEC U20 — the WELCOME-CARD and BOARD-HYGIENE LAW
# of the anthology engine, the u20 package-init doctrine: the engine's
# database is READ-ONLY in dry-run — this package must never write the DB
# unless the caller passed --execute explicitly (Trevor-gated). Without
# --execute the modules report what WOULD happen and exit without mutating.
# Welcome card content derives from HOW-TO-USE.md (producer-facing); it
# ships as copy only, never as a write). The seven verified items in the
# family's FIXED order (docs_u20.VERIFY_ITEMS — the catalog and the tree
# never drift):
#   1. THE PRODUCER-VOICE LAW — the Welcome card's content derives from
#      HOW-TO-USE.md (the engine's producer-facing guide) and the card body
#      renders from the guide's OWN copy by EXACT SECTION ORDER (the title
#      line, the intro paragraph, then the six sections verbatim); the
#      producer-language law is enforced, never described: the body MUST
#      mention 'participant' / 'participants' and MUST carry the Convert
#      and Flow naming; a heading renamed, dropped, or reordered, or a
#      content-law break, refuses the build (welcome_builder; AF-AE-WELCOME-
#      SOURCE-UNREADABLE / AF-AE-WELCOME-SOURCE-DRIFT / AF-AE-WELCOME-
#      CONTENT-VIOLATION).
#   2. THE READ-ONLY-DRY-RUN LAW — the engine's database is READ-ONLY in
#      every non-execute path of the family: the state database
#      (anthology_state.db, the meta table, schema pinned byte-exact) is
#      opened ONLY in the sqlite URI mode=ro by welcome_builder's control
#      and read-back handles; mission-control.db is opened by db_connector
#      with the SQLITE QUERY-ONLY pragma plus an IMMEDIATE rollback
#      transaction that is always rolled back; a dry-run is the OFFLINE
#      plan, never a lesser build; every module's self-test proves the
#      database file is never created and no byte changes in any
#      non-execute path (the strongest form: the archive battery proves the
#      mirror is BYTE-IDENTICAL after every non-execute call).
#   3. THE TREVOR GATE — every ACTION surface of the family (the card
#      INSERT in welcome_builder / welcome_action / db_connector, the
#      archive statements in archive_action / archive_stmt, the verify
#      ACTION in verify_board) REQUIRES the operator's explicit --execute.
#      WITHOUT --execute an ACTION request is a STOP (exit 2, the
#      AF-AE-WELCOME-NO-EXECUTE / AF-AE-DBC-NO-EXECUTE / AF-AE-VRBOARD-NO-
#      EXECUTE / AF-AE-U20ARCHIVE-NO-EXECUTE family), never a silent no-op
#      and never a silent write. Dry-run and no-execute are DIFFERENT laws:
#      a plan exits 0, an ACTION without the gate exits 2.
#   4. THE IDEMPOTENCY LAW (GET-first) — a card / board state that already
#      exists is a clean no-op, never a duplicate write: the meta row under
#      'welcome::producer' present with identical content is an IDEMPOTENT
#      NO-OP (exit 0); an existing 'Welcome to Anthology' task on the board
#      is 'already welcomed', never re-seeded; a foreign value under the
#      card's own key is a MISMATCH, never overwritten.
#   5. THE READ-BACK LAW — a write is never trusted without read-back: the
#      card INSERT is re-read through the READ-ONLY open and compared
#      byte-exact against what was inserted; the archive statements are
#      followed by a read of the ledger target through the SOLE WRITER's
#      own read-only surface; the seeded board card is SELECTed back by its
#      task id; the archive UPDATEs are re-read and every pinned card must
#      be archived. A missing or drifted read-back is a MISMATCH (exit 5),
#      never a false success.
#   6. THE ZERO-DRILL LAW — the open board carries zero live ZZZ/SYNTHETIC
#      drill cards and the byte-exact 'Welcome to Anthology' card is
#      present on the open board (verify_board, the read-back half of the
#      U14 board-hygiene law; the synthetic match is restricted to
#      ZZZ/SYNTHETIC titles so a real co-author card can never be caught);
#      a board that cannot be read is STOP/HELD, never 'board clean'.
#   7. THE ZERO-CARDS ATTACK LAW — the empty board census is the golden
#      no-op PASS (nothing to sync, nothing to write) while a census that
#      carries cards is REFUSED (attack_no_cards; AF-AE-WELCOME-CARDS-
#      PRESENT / AF-AE-WELCOME-MALFORMED; the fixture is DATA and never
#      writes, the mutation is --execute-gated, Trevor-gated), and the
#      golden six-card census must pass its own fail-closed judge byte-exact
#      with the execute_required truth (golden_6cards).
#
# THE OFFLINE SELF-TEST (--self-test): imports every u20_modules file BY
# NAME and runs EVERY module's own battery — the golden clean board PASSES
# and every drift REFUSES (verify_board), the zero-cards attack is judged a
# clean no-op PASS and the cards-present attack is REFUSED (attack_no_cards),
# the golden six-card census passes its own judge (golden_6cards), the
# Welcome-card builders / connector / archive surfaces prove their golden +
# attack fixtures (welcome_builder / welcome_action / db_connector /
# archive_action / archive_stmt), the docs_u20 drift gate proves the tree
# ships together, and the sibling pytest battery (test_archive_stmt) runs as
# the independent proof. Plus the assembly's own assertions: the disk tree
# matches the roster exactly, every module exposes its self-test, the
# documented AF family maps onto the house exits, and the docs catalog's
# seven items are the assembly's seven items. NO network, NO credentials,
# NO database, NO writes. Exit 4 on any failure (the AF-AE-TEMPLATE-ATTACK
# enforced-violation family) — a tamper NEVER masquerades as exit 1.
#
# THE LIVE SURFACES ARE THE SIBLINGS' OWN --execute-GATED CLIs: this
# dispatcher has NO live aggregate and NEVER writes. The family's ACTION
# surfaces (the card seed via db_connector.py --seed / welcome_action.py
# seed, the board verify via verify_board.py check, the board archive via
# archive_stmt.py archive, the producer archive via archive_action.py
# archive) each REFUSE without their own --execute (the Trevor gate) and are
# invoked by the OPERATOR directly — this assembler never invokes them and
# never writes. A request for a live ACTION through this dispatcher is a
# usage STOP (exit 2, AF-AE-U20-ASSEMBLY-INCOMPLETE family / usage), never
# a silent network probe and never a silent write.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. This family holds NO credential:
# the board is a local SQLite file and the Welcome card content is the
# local HOW-TO-USE.md; the credential-shaped-string guard (pit-* / Bearer *)
# REFUSES rather than echo (the house guard). Every operator surface masks
# ids (the last-4 marker) and database paths (the file name only); full ids
# ride only the machine JSON payload.
#
# AF CODES (fail-closed surfaces; self-test failures are exit 4, never 1;
# the family is staged under manifest-pending/u20.json, its OWN manifest
# row 62 stamped by this assembly):
#   AF-AE-U20-ASSEMBLY-INCOMPLETE -> the u20_modules file set named in the
#          assembly roster is not fully present, or a module violates the
#          one-entry-point self_test contract. STOP (exit 2) — a family
#          gate is never silently skipped.
#   AF-AE-WELCOME-NO-EXECUTE      -> an ACTION (the card INSERT / the
#          verify ACTION / the archive statements) was requested WITHOUT
#          --execute — the Trevor gate. STOP (exit 2), never a silent no-op
#          and never a silent write.
#   AF-AE-WELCOME-DB-MISSING      -> no Command Center database found in
#          any candidate location and no DATABASE_PATH env override. STOP
#          (exit 2) — never a write into the unknown, never a guessed path.
#   AF-AE-WELCOME-READ-REFUSED    -> the GET-first existence check or the
#          read-back SELECT failed on the found database. STOP (exit 2) —
#          never a silent skip, never a seed-into-the-unknown.
#   AF-AE-WELCOME-CARD-REFUSED    -> the found database refused the INSERT.
#          STOP (exit 2) — a refused write is NEVER reported as inserted.
#   AF-AE-WELCOME-READBACK-MISMATCH -> a post-write read-back does not
#          prove the write byte-for-byte. exit 5.
#   AF-AE-WELCOME-SOURCE-UNREADABLE -> HOW-TO-USE.md is missing or
#          unreadable. STOP (exit 2) — a card that cannot see its law never
#          fabricates a pass.
#   AF-AE-WELCOME-SOURCE-DRIFT    -> the guide's section headings no longer
#          match the pinned section law. exit 5.
#   AF-AE-WELCOME-CONTENT-VIOLATION -> a content-law break ('participant' /
#          'participants' absent, or the Convert and Flow naming absent).
#          exit 5.
#   AF-AE-WELCOME-DB-UNREADABLE   -> the engine state database cannot be
#          opened READ-ONLY, or its schema carries no meta table. STOP
#          (exit 2).
#   AF-AE-WELCOME-DB-MISMATCH     -> the live meta schema is not the engine
#          pinned meta schema, or a foreign value already sits under the
#          card's own key. exit 5.
#   AF-AE-WELCOME-INSERT-REFUSED  -> the INSERT itself failed under
#          --execute. STOP (exit 2; HELD exit 3 per class).
#   AF-AE-WELCOME-CARDS-PRESENT   -> the board census carries card(s) — the
#          zero-cards attack law is violated. exit 5.
#   AF-AE-WELCOME-MALFORMED       -> a malformed census (a missing 'cards'
#          key, a non-list array, a credential-shaped string). exit 5.
#   AF-AE-WELCOME-ATTACK          -> an attack fixture tripped the OFFLINE
#          self-test (enforced violation). exit 4.
#   AF-AE-DBC-NO-DB               -> the database file is absent,
#          unreadable, or unopenable. STOP (exit 2) — a missing DB is never
#          'board cleared'.
#   AF-AE-DBC-NO-EXECUTE          -> the card INSERT was requested without
#          --execute. STOP (exit 2).
#   AF-AE-DBC-NO-WELCOME          -> no Welcome card exists on the
#          anthology board — a READ-ONLY report that names exactly the
#          remediation. exit 5, never a pass.
#   AF-AE-DBC-SEED-EXISTS         -> the seed was requested with --execute
#          but a Welcome card ALREADY exists — the 'already welcomed'
#          no-op. exit 0.
#   AF-AE-DBC-ATTACK              -> an attack fixture tripped the OFFLINE
#          self-test (enforced violation). exit 4.
#   AF-AE-VRBOARD-NO-DB           -> no Command Center database found. STOP
#          (exit 2) — a board that cannot be read is never 'board clean'.
#   AF-AE-VRBOARD-NO-EXECUTE      -> the VERIFY ACTION was requested
#          without --execute. STOP (exit 2); even WITH it the verifier
#          never writes.
#   AF-AE-VRBOARD-TASKS-MISSING   -> the tasks table is absent from the
#          board database. STOP (exit 2).
#   AF-AE-VRBOARD-DRILLS-LIVE     -> one or more live ZZZ/SYNTHETIC drill
#          cards on the open board. exit 5 — the report names the masked
#          ids.
#   AF-AE-VRBOARD-NO-WELCOME      -> no byte-exact 'Welcome to Anthology'
#          card is LIVE on the open board. exit 5.
#   AF-AE-VRBOARD-ATTACK          -> an attack fixture tripped the OFFLINE
#          self-test (enforced violation). exit 4.
#   AF-AE-U20ARCHIVE-NO-EXECUTE   -> the archive statements were requested
#          without --execute. STOP (exit 2) — the statements run ONLY when
#          the caller passed the gate.
#   AF-AE-U20ARCHIVE-READBACK-MISMATCH -> the post-archive read-back of the
#          LEDGER target does not match the ledger's archived vocabulary
#          byte-exact. exit 5 — nothing is ever reported archived without
#          read-back.
#   AF-AE-ARCHSTMT-NO-EXECUTE     -> the archive UPDATEs were requested
#          without --execute. STOP (exit 2).
#   AF-AE-ARCHSTMT-READBACK       -> the post-write read-back did not
#          confirm every pinned card archived (exit 5, MISMATCH) or could
#          not be read (exit 3, HELD — UNDETERMINED, never a verdict).
#   AF-AE-TEMPLATE-ATTACK         -> an attack fixture tripped the OFFLINE
#          self-test of a family battery (enforced violation — the house
#          code, shared with the U02 / U03 / U04 / U05 / U06 / U07 /
#          U08_U09 / U10_U13 families). exit 4.
#
# EXIT CODES (house convention 0/1/2/3/5; 4 = enforced violation; the
# primary surface the operator consumes is 0 = PASS, 2 = STOP, 5 = mismatch):
#   0  all checks PASS (also --dry-run plan pass and self-test pass; an
#      idempotent no-op — a card / board state already present, an
#      already-archived row, a zero-cards census)
#   1  unexpected error (top-level guard; never a secret leak)
#   2  STOP refusal — usage / the U20 assembly incomplete
#      (AF-AE-U20-ASSEMBLY-INCOMPLETE) / a HOW-TO-USE.md unreadable
#      (AF-AE-WELCOME-SOURCE-UNREADABLE) / a database missing or unreadable
#      (AF-AE-WELCOME-DB-MISSING, AF-AE-DBC-NO-DB, AF-AE-VRBOARD-NO-DB /
#      TASKS-MISSING) / an ACTION requested WITHOUT --execute (the Trevor
#      gate, the AF-AE-WELCOME-NO-EXECUTE / AF-AE-DBC-NO-EXECUTE /
#      AF-AE-VRBOARD-NO-EXECUTE / AF-AE-U20ARCHIVE-NO-EXECUTE family) / a
#      genuine write refusal
#   3  HELD — a retryable database condition (locked / busy) or an
#      unreadable read-back (UNDETERMINED — never a verdict, never a false
#      success)
#   4  self-test FAILED (the AF-AE-WELCOME-ATTACK / AF-AE-DBC-ATTACK /
#      AF-AE-VRBOARD-ATTACK / AF-AE-ARCHSTMT-ATTACK / AF-AE-TEMPLATE-ATTACK
#      family, enforced violation) — a tamper NEVER masquerades as exit 1
#   5  mismatch / fail-closed default — a source drift (a heading renamed,
#      dropped, or reordered), a content-law violation (participant(s) or
#      the Convert and Flow naming absent), a foreign value under the card's
#      own key, a drifted meta schema, a read-back that does not prove the
#      write, a live ZZZ/SYNTHETIC drill card on the open board, a Welcome
#      card absent or not byte-exact, a credential-shaped value on a
#      surface, or a malformed / non-empty census refused by the attack
#      fixture — never a fabricated pass
#
# MANIFEST-PENDING: after a PASSING run the tool writes
# manifest-pending/u20.json — the staged U20 manifest artifact (contract,
# checks verdict, the module inventory, the af-code family, the exit-code
# contract, the seven verified items, provenance) — so the manifest can be
# re-stamped from a machine-readable record once the operator approves. The
# write is fail-closed: it happens ONLY on a PASS (self-test pass or
# dry-run plan pass); a FAIL/HELD/STOP run writes nothing and removes
# nothing. The ENGINE-MANIFEST.json / ENGINE-PIN.sha256 / verify.sh are
# NEVER touched here.
#
# STDLIB ONLY (argparse + importlib + json). Calls NO model, holds NO
# credential, makes NO HTTP request. DOCTRINE: move in silence; NOTHING
# Anthropic in any runtime file; Convert and Flow naming in every client
# surface; NEVER print a secret value; --dry-run and --self-test are
# OFFLINE.
# =============================================================================
"""cc_board_hygiene.py — the U20 CC board-hygiene dispatcher assembled
from the u20_modules files: one CLI, offline self-test battery (golden
PASS / the zero-cards attack FAIL), JSON output, and the
manifest-pending/u20.json stage (Skill 59)."""

from __future__ import annotations

import argparse
import importlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry owns the
# exit-code convention; the family's own modules resolve their surfaces
# themselves — this dispatcher imports every one BY NAME below.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent
MODULES_DIR = Path(__file__).resolve().parent / "u20_modules"
PENDING_DIR = SKILL_DIR / "manifest-pending"
PENDING_U20 = PENDING_DIR / "u20.json"

# THE u20_modules FILES — the assembly manifest for this dispatcher.
# Every name is imported BY NAME below (importlib), never exec'd from a
# path; a missing module is a STOP, never a silent skip (the fail-closed
# import contract). `role` is the one-line contract each module owns. The
# names mirror the files on disk one-to-one (the catalog and the tree
# never drift; the self-test pins the roster against the disk exactly).
U20_MODULES = (
    ("__init__.py",            "fail-closed EMPTY package init (pure namespace)"),
    ("welcome_builder.py",     "the PRODUCER WELCOME CARD BUILDER — HOW-TO-USE.md becomes the card's body copy by exact section order; the ONE INSERT under 'welcome::producer' runs ONLY under --execute (the Trevor gate); READ-ONLY in every non-execute path; idempotent by construction; READ-BACK LAW"),
    ("welcome_action.py",      "the ANTHOLOGY WELCOME CARD SEEDER — GET-first idempotent seeding of the client's Command Center Anthology board (the Skill 32 step-3 task shape); the card INSERT runs ONLY under --execute; READ-BACK LAW"),
    ("db_connector.py",        "the FAIL-CLOSED SQLITE3 CONNECTOR over mission-control.db — the shared DB surface (QUERY-ONLY pragma + IMMEDIATE rollback transaction, always rolled back); the card INSERT runs ONLY under --execute"),
    ("verify_board.py",        "the POST-ACTION BOARD VERIFIER — the read-back half of the Anthology board hygiene ACTION: zero live ZZZ/SYNTHETIC drill cards AND the byte-exact 'Welcome to Anthology' card present on the open board; READ-ONLY by construction; the VERIFY ACTION requires --execute and even WITH it never writes"),
    ("archive_stmt.py",        "the BOARD ARCHIVE STATEMENT BUILDER — the UPDATE statements that soft-archive the six pinned debris cards (tasks.archived_at); the statements run ONLY under --execute; idempotent; READ-BACK LAW"),
    ("archive_action.py",      "the ARCHIVE ACTION — the Trevor-gated producer archive surface for the engine's OWN ledger (anthology_state.py, the SOLE writer) plus the Welcome card content; the statements run ONLY under --execute; READ-BACK LAW"),
    ("attack_no_cards.py",     "the ZERO-CARDS ATTACK FIXTURE — the empty board census is the clean no-op PASS (nothing to sync, nothing to write); a census that carries cards is REFUSED (AF-AE-WELCOME-CARDS-PRESENT); the fixture is DATA and never writes"),
    ("golden_6cards.py",       "the GOLDEN SIX-CARD census fixture — the canonical board record (Welcome first, Assembly, four participants under the KEYING LAW) with every status byte-exact and the execute_required truth; its fail-closed judge passes the golden census and refuses any drift"),
    ("test_archive_stmt.py",   "the independent pytest battery over the U20 archive ACTION (provenance only)"),
    ("docs_u20.py",            "the U20 tooling README/catalog data + drift gate (the module inventory as DATA)"),
)

# The modules the dispatcher aggregates for the OFFLINE battery. The U20
# family has NO dispatcher skeleton and NO live aggregate — every surface
# IS a module (the package-init doctrine: the siblings ARE the surfaces).
# The battery therefore runs every module that ships its own self-test.
SELF_TEST_MODULES = tuple(
    name[:-3] for name, _ in U20_MODULES
    if name not in ("__init__.py", "test_archive_stmt.py"))

# The sibling pytest battery — imported for its provenance; its tests run
# as the independent pytest battery (test_archive_stmt.py).
TEST_MODULES = ("test_archive_stmt",)

# The seven U20 verified items, as the manifest-pending stage records them
# (docs_u20.VERIFY_ITEMS — the catalog and the tree never drift).
VERIFIED_ITEMS = (
    (1, "producer_voice", "Producer-voice law — the Welcome card content "
                          "derives from HOW-TO-USE.md"),
    (2, "read_only_dry_run", "Read-only-dry-run law — the engine's database "
                             "is READ-ONLY without --execute"),
    (3, "trevor_gate", "Trevor gate — every ACTION surface requires "
                       "--execute"),
    (4, "idempotency", "Idempotency law — GET-first, seed only if absent"),
    (5, "read_back", "Read-back law — a write is never trusted without "
                     "read-back"),
    (6, "zero_drill", "Zero-drill law — the open board carries zero "
                      "synthetic cards and the Welcome card"),
    (7, "zero_cards_attack", "Zero-cards attack law — the empty census is "
                             "the golden no-op, never a write"),
)

# The AF-AE autofail family, as the stage records it (docs_u20.AF_CODES —
# the catalog and the tree never drift; every code here is mirrored into
# ENGINE-MANIFEST.json autofails by this assembly's stamp).
AF_CODES = (
    ("AF-AE-U20-ASSEMBLY-INCOMPLETE", 2,
     "the u20_modules file set named in the assembly roster is not fully "
     "present, or a module violates the one-entry-point self_test contract "
     "— a family gate is never silently skipped (dispatcher STOP)"),
    ("AF-AE-WELCOME-NO-EXECUTE", 2,
     "an ACTION (the card INSERT / the VERIFY ACTION / the archive "
     "statements) was requested WITHOUT --execute — the Trevor gate: the "
     "module reports exactly what it WOULD do and exits without mutating "
     "(STOP, never a silent no-op and never a silent write)"),
    ("AF-AE-WELCOME-DB-MISSING", 2,
     "no Command Center database found in any candidate location and no "
     "DATABASE_PATH env override — never a write into the unknown, never "
     "a guessed path"),
    ("AF-AE-WELCOME-READ-REFUSED", 2,
     "the GET-first existence check or the read-back SELECT failed on the "
     "found database (missing table / sqlite error / unreadable file) — "
     "never a silent skip, never a seed-into-the-unknown"),
    ("AF-AE-WELCOME-CARD-REFUSED", 2,
     "the found database refused the INSERT (sqlite error / constraint / "
     "read-only file) — a refused write is NEVER reported as inserted"),
    ("AF-AE-WELCOME-READBACK-MISMATCH", 5,
     "a post-write read-back does not prove the write byte-for-byte — "
     "the shared house code with the U02 / U03 / U04 / U05 / U06 / U07 / "
     "U08_U09 / U10_U13 families (already stamped in ENGINE-MANIFEST.json)"),
    ("AF-AE-WELCOME-SOURCE-UNREADABLE", 2,
     "HOW-TO-USE.md is missing or unreadable — a card that cannot see "
     "its law never fabricates a pass"),
    ("AF-AE-WELCOME-SOURCE-DRIFT", 5,
     "the guide's section headings no longer match the pinned section law "
     "(a heading renamed, dropped, or reordered), or the title line is "
     "not the guide's '# ' title — the card body renders from the guide "
     "BY EXACT SECTION ORDER, so a drifted heading structure means the "
     "card can silently contradict the guide"),
    ("AF-AE-WELCOME-CONTENT-VIOLATION", 5,
     "a content-law break — 'participant' / 'participants' absent from "
     "the card body, or the Convert and Flow naming absent — the "
     "producer language is enforced, never described"),
    ("AF-AE-WELCOME-DB-UNREADABLE", 2,
     "the engine state database cannot be opened READ-ONLY, or its schema "
     "carries no meta table — the gate's own control: the write is never "
     "trusted into the unknown"),
    ("AF-AE-WELCOME-DB-MISMATCH", 5,
     "the live meta schema is not the engine's pinned meta schema, or a "
     "foreign value already sits under the card's own key — never a "
     "blind insert, never a blind overwrite, never a fabricated state"),
    ("AF-AE-WELCOME-INSERT-REFUSED", 2,
     "the INSERT itself failed under --execute (read-only filesystem, "
     "locked database, schema drift) — a refused write is NEVER reported "
     "as inserted (HELD exit 3 per class)"),
    ("AF-AE-WELCOME-CARDS-PRESENT", 5,
     "the board census carries card(s) — the zero-cards attack law is "
     "violated; the census that is not empty is REFUSED, never certified "
     "clean"),
    ("AF-AE-WELCOME-MALFORMED", 5,
     "a malformed census — a missing 'cards' key, a non-list array, or a "
     "credential-shaped string on the census — the attack fixture is "
     "DATA, and a census that cannot be judged is refused, never "
     "certified clean"),
    ("AF-AE-WELCOME-ATTACK", 4,
     "an attack fixture tripped the OFFLINE self-test (enforced "
     "violation) — a census that should have been REFUSED was not caught "
     "HERE first"),
    ("AF-AE-DBC-NO-DB", 2,
     "the database file is absent, unreadable, or unopenable — a missing "
     "DB is never 'board cleared', never a no-op pass"),
    ("AF-AE-DBC-NO-EXECUTE", 2,
     "the card INSERT was requested without --execute — the module NEVER "
     "writes without the explicit Trevor-gated execute flag (dry-run "
     "plans do not require it)"),
    ("AF-AE-DBC-NO-WELCOME", 5,
     "no Welcome card exists on the anthology board — a READ-ONLY report "
     "that names exactly the remediation: run with --execute to seed it. "
     "Never a pass"),
    ("AF-AE-DBC-SEED-EXISTS", 0,
     "the seed was requested with --execute but a Welcome card ALREADY "
     "exists on the anthology board — the 'already welcomed' no-op; the "
     "seed is idempotent, it never duplicates and never archives"),
    ("AF-AE-DBC-ATTACK", 4,
     "an attack fixture tripped the OFFLINE self-test (enforced "
     "violation) — a tamper never masquerades as exit 1"),
    ("AF-AE-VRBOARD-NO-DB", 2,
     "no Command Center database found (--db unset, DATABASE_PATH unset, "
     "and no candidate exists). STOP — a board that cannot be read is "
     "never 'board clean'"),
    ("AF-AE-VRBOARD-NO-EXECUTE", 2,
     "the VERIFY ACTION was requested without --execute — the Trevor "
     "gate: without it the ACTION is a refusal, never a silent no-op; "
     "even WITH it the verifier never writes"),
    ("AF-AE-VRBOARD-TASKS-MISSING", 2,
     "the tasks table is absent from the board database. STOP — never a "
     "sweep of nothing, never a blind pass"),
    ("AF-AE-VRBOARD-DRILLS-LIVE", 5,
     "one or more live ZZZ/SYNTHETIC drill cards on the open board — the "
     "zero-drill law is violated; the report names the masked ids"),
    ("AF-AE-VRBOARD-NO-WELCOME", 5,
     "no byte-exact 'Welcome to Anthology' card is LIVE on the open "
     "board — the report names the remediation (the seed ACTION is the "
     "sibling's, Trevor-gated, never re-implemented here)"),
    ("AF-AE-VRBOARD-ATTACK", 4,
     "an attack fixture tripped the OFFLINE self-test (enforced "
     "violation)"),
    ("AF-AE-U20ARCHIVE-NO-EXECUTE", 2,
     "the archive statements were requested without --execute — the "
     "statements run ONLY when the caller passed the gate; WITHOUT "
     "--execute a live-status anthology is a STOP that names the code "
     "and writes NOTHING"),
    ("AF-AE-U20ARCHIVE-READBACK-MISMATCH", 5,
     "the post-archive read-back of the LEDGER target does not match the "
     "ledger's archived vocabulary byte-exact — nothing is ever "
     "reported archived without read-back"),
    ("AF-AE-ARCHSTMT-NO-EXECUTE", 2,
     "the archive UPDATEs were requested without --execute — the module "
     "NEVER writes without the explicit Trevor-gated execute flag (dry-"
     "run plans do not require it)"),
    ("AF-AE-ARCHSTMT-READBACK", 5,
     "the post-write read-back did not confirm every pinned card "
     "archived (exit 5, MISMATCH) or could not be read (exit 3, HELD — "
     "UNDETERMINED, never a verdict)"),
    ("AF-AE-TEMPLATE-ATTACK", 4,
     "an attack fixture tripped the OFFLINE self-test of a family "
     "battery (enforced violation — the house code, shared with the "
     "U02 / U03 / U04 / U05 / U06 / U07 / U08_U09 / U10_U13 families)"),
)

# House exit-code contract (docs_u20.EXIT_CODES — the catalog and the tree
# never drift).
EXIT_CODES = {
    0: "verified success — an idempotent no-op (a card / board state "
       "already present, an already-archived row, a zero-cards census), a "
       "completed dry-run / plan, or the offline self-test; an EMPTY "
       "census is a truthful PASS",
    1: "unexpected error (top-level guard; never a secret leak)",
    2: ("STOP refusal — usage / a database missing or unreadable "
        "(AF-AE-WELCOME-DB-MISSING, AF-AE-DBC-NO-DB, AF-AE-VRBOARD-NO-DB "
        "/ TASKS-MISSING — never a write into the unknown, never a "
        "guessed path) / a HOW-TO-USE.md unreadable (AF-AE-WELCOME-SOURCE-"
        "UNREADABLE — a card that cannot see its law never fabricates a "
        "pass) / an ACTION requested WITHOUT --execute (the Trevor gate, "
        "the AF-AE-WELCOME-NO-EXECUTE / AF-AE-DBC-NO-EXECUTE / "
        "AF-AE-VRBOARD-NO-EXECUTE / AF-AE-U20ARCHIVE-NO-EXECUTE family — "
        "never a silent no-op and never a silent write) / a genuine "
        "write refusal"),
    3: ("HELD — a retryable database condition (locked / busy) or an "
        "unreadable read-back (UNDETERMINED — never a verdict, never a "
        "false success)"),
    4: ("self-test FAILED (the AF-AE-WELCOME-ATTACK / AF-AE-DBC-ATTACK / "
        "AF-AE-VRBOARD-ATTACK / AF-AE-ARCHSTMT-ATTACK / AF-AE-TEMPLATE-"
        "ATTACK family, enforced violation) — a tamper never masquerades "
        "as exit 1"),
    5: ("mismatch / fail-closed default — a source drift (a heading "
        "renamed, dropped, or reordered), a content-law violation "
        "(participant(s) or the Convert and Flow naming absent), a "
        "foreign value under the card's own key, a drifted meta schema, a "
        "read-back that does not prove the write, a live ZZZ/SYNTHETIC "
        "drill card on the open board, a Welcome card absent or not "
        "byte-exact, a credential-shaped value on a surface (leak-scan "
        "REFUSAL), or a malformed / non-empty census refused by the "
        "attack fixture — never a fabricated pass"),
}


class AssembleError(Exception):
    """A fail-closed assembly refusal: a missing module, a module that
    violates its contract, or an unwritable pending stage. The aggregate
    NEVER passes with a module silently absent."""


# ---------------------------------------------------------------------------
# The 11-file assembly — import EVERY u20_modules file BY NAME. The empty
# package init is imported for the namespace guarantee (importing the
# package succeeds only if __init__.py is intact); every sibling module is
# imported directly here for its surfaces and its self-test battery; the
# pytest battery is imported for its provenance (its tests run as the
# independent pytest battery).
# ---------------------------------------------------------------------------
def _load_package() -> None:
    """Prove the package namespace container imports clean."""
    importlib.import_module("u20_modules")


def load_all_modules(out=None) -> dict:
    """Import every one of the u20_modules files. Returns
    {name: module}. Fail-closed: a missing file or a module violating its
    contract raises AssembleError (STOP) — the aggregate NEVER passes with
    a module silently absent."""
    out = out or sys.stderr
    _load_package()
    # The modules resolve BY NAME (importlib.import_module(name)) — their
    # own directory must sit on sys.path for that to resolve.
    if str(MODULES_DIR) not in sys.path:
        sys.path.insert(0, str(MODULES_DIR))

    modules = {}
    missing = []
    for name, _role in U20_MODULES:
        modname = name[:-3] if name.endswith(".py") else name
        if modname == "__init__":
            continue
        try:
            modules[modname] = importlib.import_module("u20_modules." + modname)
        except ImportError:
            missing.append(name)
    if missing:
        raise AssembleError(
            "u20_modules file(s) not found: %s — the 11-file assembly is "
            "incomplete (fail-closed: no module is ever skipped)"
            % ", ".join(missing))
    return modules


# ---------------------------------------------------------------------------
# Offline self-test — run EVERY module's own battery (golden PASS / the
# U20 attack FAIL), plus this verifier's own assembly assertions, plus the
# sibling pytest battery. NO network, NO credentials, NO database, NO
# writes. Exit 4 on any failure.
# ---------------------------------------------------------------------------
def _module_self_test(module, name: str, out) -> None:
    """Run one module's own OFFLINE battery. db_connector exposes its
    battery as cmd_self_test (the main-surface convention); every sibling
    exposes self_test(out)."""
    st = getattr(module, "self_test", None)
    if not callable(st):
        st = getattr(module, "cmd_self_test", None)
    if not callable(st):
        raise AssertionError(
            "module %s does not expose 'self_test' / 'cmd_self_test' — "
            "every u20_modules module must prove itself offline" % name)
    dev = io.StringIO()
    try:
        rc = st(out=dev)
    except TypeError:
        rc = st()
    out.write(dev.getvalue())
    if rc != EX_OK:
        raise AssertionError("%s self_test returned exit %d" % (name, rc))


def _run_pytest(modules: dict, out) -> None:
    """The sibling pytest battery — the independent proof that the U20
    archive ACTION law is pinned offline. A failed battery is an enforced
    violation, never a silent skip."""
    pkg = Path(modules["test_archive_stmt"].__file__).resolve().parent
    tests = [str(pkg / (name + ".py")) for name in TEST_MODULES]
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *tests],
        capture_output=True, text=True, timeout=600)
    if proc.stdout:
        out.write(proc.stdout)
    if proc.returncode != 0:
        raise AssertionError(
            "pytest battery failed (exit %d): %s"
            % (proc.returncode, (proc.stderr or "").strip()[-400:]))


def self_test(modules: dict, out=None, *, run_pytest: bool = True) -> int:
    """OFFLINE self-test: every module's own golden+attack battery (the
    zero-cards attack MUST PASS as the golden no-op and the cards-present
    attack MUST FAIL), the golden six-card judge, the docs_u20 drift gate,
    the assembly's file-count assertions, the AF/exit-contract assertions,
    and the sibling pytest battery. Any failure is exit 4 (the
    AF-AE-TEMPLATE-ATTACK family) — a tamper NEVER masquerades as exit 1.
    On a clean pass the manifest-pending stage is written by the CLI."""
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        # 1. the assembly is complete: exactly the roster files exist.
        on_disk = sorted(p.name for p in MODULES_DIR.glob("*.py"))
        expected = sorted(name for name, _ in U20_MODULES)
        assert on_disk == expected, (
            "u20_modules tree drifted: disk carries %d files, the 11-file "
            "assembly contract names %d (%s)"
            % (len(on_disk), len(expected),
               ", ".join(sorted(set(on_disk) ^ set(expected)))))

        # 2. every module's own battery passes (golden PASS / attack FAIL).
        for name in SELF_TEST_MODULES:
            _module_self_test(modules[name], name, dev)

        # 3. the zero-cards attack law, exercised through the fixture's own
        #    surfaces — the GOLDEN no-op PASSES and the cards-present
        #    attack REFUSES (never a silent pass, never a blind refusal):
        anc = modules["attack_no_cards"]
        status, detail, markers, count = anc.verify({"cards": []})
        assert status == "PASS", \
            "the zero-cards census must be the golden no-op PASS"
        assert count == 0 and markers == ["(no cards)"], \
            "the zero-cards no-op must carry the empty marker"
        refuse = anc.payload({"cards": [{"title": "Welcome",
                                         "status": "open"}]},
                             out=io.StringIO())
        assert refuse == EX_MISMATCH, \
            "the cards-present attack was NOT refused (exit %s)" % refuse
        malformed = anc.payload({"cards": "not-a-list"},
                                out=io.StringIO())
        assert malformed == EX_MISMATCH, \
            "a malformed census was NOT refused (exit %s)" % malformed

        # 4. the golden six-card census passes its own fail-closed judge,
        #    and the golden clean board PASSES the verify_board law (the
        #    pass side of every split — a gate that fails everything is a
        #    broken instrument):
        g6 = modules["golden_6cards"]
        judge = g6.payload(None, out=io.StringIO())
        assert judge.get("ok") and judge["count"] == 6, \
            "the golden six-card census must pass its own judge"
        assert judge.get("af_code") == "SIX-CARDS", \
            "the golden af code drifted"

        # 5. the docs_u20 catalog is the assembly's catalog (7 items, 9
        #    modules, exit codes 0..5 — its self-test already pinned the
        #    counts; here we pin the shared constants):
        docs = modules["docs_u20"]
        assert len(docs.verify_items()) == len(VERIFIED_ITEMS), \
            "docs_u20 item count drifted from the assembly's VERIFIED_ITEMS"
        assert [it["item"] for it in docs.verify_items()] == \
            [1, 2, 3, 4, 5, 6, 7], \
            "docs_u20 item numbers drifted from the fixed order"
        codes = [c[0] for c in docs.af_codes()]
        # The docs catalog carries the family's OWN AF family (28 codes);
        # the assembly adds the two ARCHSTMT codes (owned by archive_stmt,
        # the U20 rebuild of the u14 board-hygiene operation — its battery
        # pins them) and the assembly-incomplete code (this dispatcher's
        # own STOP surface). Every code the docs catalog carries must be
        # mirrored here, never invented.
        assert all(c in [a[0] for a in AF_CODES] for c in codes), \
            "a docs_u20 AF code is not mirrored in the assembly AF_CODES"
        assert len(AF_CODES) == len(set(c[0] for c in AF_CODES)), \
            "the assembly AF codes must be unique"
        assert sorted(docs.exit_codes().keys()) == [0, 1, 2, 3, 4, 5], \
            "docs_u20 exit-code contract drifted"

        # 6. the sibling pytest battery (the independent proof).
        if run_pytest:
            _run_pytest(modules, dev)
    except AssertionError as exc:
        sys.stderr.write("[cc-board-hygiene] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    except AssembleError as exc:
        sys.stderr.write("[cc-board-hygiene] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION

    out.write(dev.getvalue())
    out.write("[cc-board-hygiene] assembled self-test: OK (11 u20_modules "
              "files imported, %d module batteries + the zero-cards attack "
              "law gate + the golden six-card judge + the docs_u20 drift "
              "gate + assembly assertions%s all pass)\n"
              % (len(SELF_TEST_MODULES),
                 " + the pytest battery" if run_pytest else
                 " (pytest batteries skipped --no-pytest)"))
    return EX_OK


class _redirect_stdout:
    """Minimal context manager (house style: no pytest dependency in the
    dispatch path)."""

    def __init__(self, buf):
        self._buf = buf
        self._old = None

    def __enter__(self):
        self._old = sys.stdout
        sys.stdout = self._buf
        return self._buf

    def __exit__(self, *exc):
        sys.stdout = self._old
        return False


# ---------------------------------------------------------------------------
# Offline plan — no network, no credentials, no database. The family law
# with the module inventory and the seven verified items, printed as ONE
# JSON object on stdout.
# ---------------------------------------------------------------------------
def dry_run(modules: dict, out=None) -> int:
    """The offline plan: the U20 family law, the assembly's module
    inventory, the seven verified items, the AF family, and the exit-code
    contract — with the explicit note that every ACTION surface is the
    sibling modules' own --execute-gated CLI, never invoked here."""
    out = out or sys.stderr
    docs = modules["docs_u20"]
    print(json.dumps({
        "contract": "anthology-engine-u20-board-hygiene-plan",
        "schema_version": 1,
        "kind": "dry-run",
        "modules": [name for name, _ in U20_MODULES],
        "verified_items": [
            {"item": i, "id": item_id, "title": title}
            for i, item_id, title in VERIFIED_ITEMS
        ],
        "dry_run": True,
        "note": "offline plan only — no database, no credential, no "
                "network; the engine's database is READ-ONLY in dry-run "
                "(the u20 package-init doctrine); every ACTION surface "
                "(the card seed via db_connector --seed / welcome_action "
                "seed, the board verify via verify_board check, the board "
                "archive via archive_stmt archive, the producer archive "
                "via archive_action archive) is the sibling modules' own "
                "--execute-gated CLI, which this dispatcher never invokes "
                "and which never writes without the Trevor gate",
    }, indent=2, sort_keys=True))
    out.write("[cc-board-hygiene] dry-run plan: OK (offline — no network, "
              "no credential, no database needed)\n")
    return EX_OK


# ---------------------------------------------------------------------------
# Manifest-pending stage — manifest-pending/u20.json. Written ONLY after a
# PASS (self-test pass or dry-run plan pass); a FAIL/HELD/STOP run writes
# nothing. The record is the machine-readable input to a later manifest
# re-stamp — the ENGINE-MANIFEST.json / ENGINE-PIN.sha256 / verify.sh are
# NEVER touched here.
# ---------------------------------------------------------------------------
def _pending_payload(kind: str, *, verdict: str = "PASS") -> dict:
    """The staged U20 manifest artifact: contract, checks verdict, the
    11-module inventory, the af-code family, the exit-code contract, the
    seven verified items, provenance. Every value comes from the module
    catalog (docs_u20) or the assembly constants — never invented."""
    return {
        "contract": "anthology-engine-u20-board-hygiene",
        "schema_version": 1,
        "kind": kind,  # "self-test" | "dry-run"
        "verdict": verdict,
        "script": "cc_board_hygiene.py",
        "authored_by": "U20",
        "u20_modules": [
            {"name": name, "role": role} for name, role in U20_MODULES
        ],
        "check_modules": list(SELF_TEST_MODULES),
        "verified_items": [
            {"item": i, "id": item_id, "title": title}
            for i, item_id, title in VERIFIED_ITEMS
        ],
        "af_codes": [
            {"code": code, "exit": exit_code, "meaning": meaning}
            for code, exit_code, meaning in AF_CODES
        ],
        "exit_codes": EXIT_CODES,
        "checks": {},
        "fail_closed": {
            "any_fail": False,
            "note": "the family's live surfaces are the sibling modules' "
                    "own --execute-gated CLIs (the card seed, the board "
                    "verify, the archive statements) — each REFUSES "
                    "without its own --execute (the Trevor gate); this "
                    "assembler NEVER invokes them and NEVER writes. The "
                    "engine's database is READ-ONLY in dry-run: without "
                    "--execute no module may write it.",
        },
    }


def write_pending(payload: dict, *, mode: str = "self-test", out=None) -> None:
    """Write manifest-pending/u20.json (fail-closed: only after a PASS).

    The directory is created if absent; the file is written atomically
    (temp + rename) so a crash mid-write never leaves a partial stage. The
    ENGINE-MANIFEST.json / ENGINE-PIN.sha256 / verify.sh are NEVER
    touched."""
    out = out or sys.stderr
    try:
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        tmp = PENDING_DIR / ("u20.json.tmp-%d" % os.getpid())
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
        tmp.replace(PENDING_U20)
    except OSError as exc:
        raise AssembleError("cannot write %s: %s" % (PENDING_U20, exc)) from exc
    out.write("[cc-board-hygiene] manifest-pending stage written: %s "
              "(%s)\n" % (PENDING_U20, mode))


# ---------------------------------------------------------------------------
# CLI — house shape: --dry-run / --self-test accepted as flags AND as a
# positional subcommand (--self-test / --selftest normalize exactly as the
# registry and the sibling assemblers).
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="cc_board_hygiene.py",
        description="The U20 CC board-hygiene dispatcher assembled from "
                    "the u20_modules files: offline self-test battery "
                    "(golden PASS / the zero-cards attack FAIL), offline "
                    "plan, and the manifest-pending/u20.json stage (Skill "
                    "59). The family's ACTION surfaces are the sibling "
                    "modules' own --execute-gated CLIs — this tool never "
                    "writes.")
    ap.add_argument("--dry-run", action="store_true",
                    help="offline plan only — no network, no credential, "
                         "no database (default: self-test)")
    ap.add_argument("--json", action="store_true",
                    help="emit a machine-readable summary on stdout "
                         "(default on for the plan)")
    ap.add_argument("--no-pytest", action="store_true",
                    help="skip the sibling pytest battery inside "
                         "--self-test (the offline module batteries still "
                         "run)")
    ap.add_argument("--selftest", "--self-test", dest="self_test",
                    action="store_true",
                    help="run the offline self-test (every module's golden "
                         "PASS / the zero-cards attack FAIL + the assembly "
                         "assertions + the pytest battery) and exit")
    ap.add_argument("cmd", nargs="?", choices=["verify", "plan", "self-test"],
                    help="positional subcommand form (verify / plan / "
                         "self-test)")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> --self-test so the flag form
    # never collides with the positional subcommand form.
    if "--self-test" in argv and "--selftest" not in argv:
        argv = ["--self-test" if a == "--self-test" else a for a in argv]
    args = ap.parse_args(argv)
    # Positional subcommand form (house shape): self-test -> the offline
    # battery; plan -> the offline dry-run; verify -> usage STOP (the
    # family has NO live aggregate — every live surface is the sibling
    # modules' own --execute-gated CLI).
    if args.cmd == "self-test":
        args.self_test = True
    elif args.cmd == "plan":
        args.dry_run = True

    try:
        modules = load_all_modules()

        if args.self_test:
            rc = self_test(modules, out=sys.stderr,
                           run_pytest=not args.no_pytest)
            if rc == EX_OK:
                write_pending(_pending_payload("self-test"),
                              mode="self-test")
            return rc

        if args.dry_run:
            rc = dry_run(modules, out=sys.stderr)
            if rc == EX_OK:
                write_pending(_pending_payload("dry-run"), mode="dry-run")
            return rc

        # cmd == "verify": usage STOP — the U20 family has NO live
        # aggregate. Every live surface (the card seed via db_connector
        # --seed / welcome_action seed, the board verify via verify_board
        # check, the board archive via archive_stmt archive, the producer
        # archive via archive_action archive) is the sibling modules' own
        # --execute-gated CLI, which the operator invokes directly with
        # the Trevor gate — this dispatcher never invokes them and never
        # writes.
        sys.stderr.write("[cc-board-hygiene] STOP: the U20 family has no "
                         "live aggregate (AF-AE-U20-ASSEMBLY-INCOMPLETE "
                         "family / usage). Every live ACTION surface is "
                         "the sibling modules' own --execute-gated CLI: "
                         "scripts/u20_modules/db_connector.py --seed "
                         "[--execute], welcome_action.py seed [--execute], "
                         "verify_board.py check [--execute], "
                         "archive_stmt.py archive [--execute], "
                         "archive_action.py archive [--execute]. Run "
                         "--self-test or --dry-run (offline) here.\n")
        return EX_STOP

    except AssembleError as exc:
        sys.stderr.write("[cc-board-hygiene] STOP/FAIL: %s\n" % exc)
        return EX_STOP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[cc-board-hygiene] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
