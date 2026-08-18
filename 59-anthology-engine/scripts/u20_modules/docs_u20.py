#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u20_modules/docs_u20.py
# U20 TOOLING — THE MODULE DOCSTRING / README, SHIPPED AS AN IMPORTABLE MODULE
# (MASTER-SPEC U20; the u02_modules/docs_u02.py row-54-sibling pattern — the
# U20 family ships under the U02/U07 sibling-helper doctrine; the U20 manifest
# row is PENDING, staged under the manifest-pending/u02.json .. u07.json
# pattern, exactly as the U07 family was staged before its stamp; current
# skill-version 0.1.24, 2026-08-11).
# -----------------------------------------------------------------------------
# WHERE THIS SITS: scripts/u20_modules/ — the U20 tooling's documentation
# module, sibling of the Welcome-card builders, the board verifier, the
# archive action, the zero-cards attack fixture, and the archive-statement
# battery it documents. It is NOT a manifest row: the U20 family's verifier
# stays the family's single manifest surface under the delivery_report.py
# row-12 sibling-helper pattern, exactly as u02_modules/docs_u02.py documents
# the row-54 U02 verifier and u03_modules/docs_u03.py /
# u04_modules/docs_u04.py / u05_modules/docs_u05.py /
# u06_modules/docs_u06.py / u07_modules/docs_u07.py document their siblings
# (U20_MANIFEST_ROW = None, recorded below — a doc that claims a manifest row
# that does not exist is drift). Imported BY NAME as u20_modules.docs_u20
# when a consumer wants the tooling's contract surfaces as DATA (module
# inventory, the seven verified items, the house exit codes, the doctrine)
# or its rendered README as text.
#
# WHAT THIS OWNS:
#   1. THE README. The module docstring below IS the U20 tooling README:
#      what the tooling gates, the module inventory, the exit-code
#      contract, the credential / browser-UA / fail-closed doctrine. The
#      same content is carried as STRUCTURED DATA (VERIFY_ITEMS, MODULES,
#      EXIT_CODES, AF_CODES, DOCTRINE, CREDENTIAL_LABELS) so a consumer can
#      diff against it instead of parsing prose — and readme() renders the
#      README FROM that data, so the two can never drift.
#   2. THE DRIFT GATE. self_test() proves the documentation still matches
#      the shipped tree: every module the README lists exists on disk next
#      to this module, all seven items are present exactly once, every house
#      exit code is documented, and the rendered README covers every
#      inventory row. A doc that names a module that does not ship FAILS
#      the self-test (exit 4, the house enforced-violation code) —
#      documentation is data, and stale documentation is drift.
#   3. PURE DATA, BY CONSTRUCTION. Nothing here reads an env var, opens a
#      file at import, touches the network, or holds a credential. A
#      documentation module cannot leak what it never holds. It performs NO
#      requests, so it defines NO User-Agent constant of its own: the
#      browser UA that defeats the Cloudflare edge (CF error 1010) is
#      CAF_BROWSER_UA, owned by anthology_registry.py and applied by its
#      clients (CafClient / InternalRailClient) — the docs record that
#      doctrine, they do not re-implement it.
#
# THE TOOLING THIS DOCUMENTS (orientation):
#   MASTER-SPEC U20 — the WELCOME-CARD and BOARD-HYGIENE family of the
#   anthology engine, the fail-closed board-surface doctrine
#   (u20_modules/__init__.py: "The engine's database is READ-ONLY in
#   dry-run: this package must never write the DB unless the caller passed
#   --execute explicitly (Trevor-gated). Without --execute, report what
#   WOULD happen and exit without mutating. Welcome card content derives
#   from HOW-TO-USE.md (producer-facing); it ships as copy only, never as
#   a write."). Seven verified items in a FIXED order:
#   1. THE PRODUCER-VOICE LAW — the Welcome card's content derives from
#      HOW-TO-USE.md (the engine's producer-facing guide, CHANGELOG 0.1.0:
#      "HOW-TO-USE.md (producer, Convert and Flow naming)"), rendered by
#      EXACT SECTION ORDER (title line, intro, then the six sections
#      verbatim) and checked against the producer-language law — the body
#      MUST mention 'participant' / 'participants' and MUST carry the
#      Convert and Flow naming; a heading renamed, dropped, or reordered,
#      or a content-law break, refuses the build (exit 5). The card copy
#      is NEVER authored in any module — it is the guide's own copy,
#      carried (welcome_builder.py, the family's single authority for the
#      card record).
#   2. THE READ-ONLY-DRY-RUN LAW — the engine's database is READ-ONLY in
#      every non-execute path of the family: the state database
#      (anthology_state.db, the engine's own key-value mirror) is opened
#      ONLY in the sqlite URI mode=ro by the builder's control and
#      read-back handles; the Command Center mission-control.db is opened
#      with the SQLITE QUERY-ONLY pragma plus an IMMEDIATE rollback
#      transaction by db_connector; a dry-run is the OFFLINE plan, never
#      a lesser build. Every module's self-test proves no database file is
#      created and no byte changes in any non-execute path.
#   3. THE TREVOR GATE — every ACTION surface of the family (the card
#      INSERT in welcome_builder / welcome_action / db_connector, the
#      archive statements in archive_action, the verify ACTION in
#      verify_board) REQUIRES the operator's explicit --execute. WITHOUT
#      --execute an ACTION request is a STOP (exit 2, the AF-AE-WELCOME-
#      NO-EXECUTE / AF-AE-DBC-NO-EXECUTE / AF-AE-VRBOARD-NO-EXECUTE /
#      AF-AE-U20ARCHIVE-NO-EXECUTE family), never a silent no-op and never
#      a silent write. Dry-run and no-execute are DIFFERENT laws: a plan
#      exits 0, an ACTION without the gate exits 2.
#   4. THE IDEMPOTENCY LAW (GET-first) — a card / board state that already
#      exists is a clean no-op, never a duplicate write: the meta row
#      under 'welcome::producer' present with identical content is an
#      IDEMPOTENT NO-OP (exit 0); an existing 'Welcome to Anthology' task
#      on the board is "already welcomed", never re-seeded; a foreign
#      value under the card's own key is a MISMATCH, never overwritten.
#   5. THE READ-BACK LAW — a write is never trusted without read-back: the
#      card INSERT is re-read through the READ-ONLY open and compared
#      byte-exact against what was inserted; the archive statements are
#      followed by a read of the ledger target through the SOLE WRITER's
#      own read-only surface; the seeded board card is SELECTed back by
#      its task id. A missing or drifted read-back is a MISMATCH (exit 5),
#      never a false success.
#   6. THE ZERO-DRILL LAW (board hygiene, carried in from the Command
#      Center's u14-anthology-board-hygiene.py, never re-typed) — the
#      open board must carry ZERO live synthetic drill cards (the 'ZZZ' /
#      'SYNTHETIC' marker titles — drill data can only ever be synthetic,
#      never a real co-author) AND ONE byte-exact 'Welcome to Anthology'
#      Welcome card; a live drill card or an absent / non-byte-exact
#      Welcome card is a MISMATCH (exit 5), never a pass (verify_board.py,
#      READ-ONLY by construction — every connection it opens is mode=ro).
#   7. THE ZERO-CARDS ATTACK LAW — a board census carrying ZERO cards is
#      the golden no-op (PASS exit 0 — a welcome-sync with no board to
#      sync writes NOTHING, the law the engine's database is READ-ONLY in
#      dry-run pinned in the other direction: the Welcome card is
#      copy-only, so even WITH --execute the fixture never writes); any
#      card present, a malformed census, a missing "cards" key, a
#      non-list array, or a credential-shaped string on the census is
#      REFUSED, never certified clean (attack_no_cards.py, the family's
#      attack half — the zero-cards census is the exact state where a
#      sync would need a WRITE, and the SAME gate must judge it a clean
#      PASS no-op).
#   The family's live surfaces read the Command Center board database by
#   path only (--db > DATABASE_PATH > the family candidate list, mirrored
#   byte-for-byte from welcome_action.DB_CANDIDATES / the Command Center
#   server's own getDbPath law — DATABASE_PATH always wins; a missing
#   database is a STOP, never a guess). The family holds NO credential and
#   makes NO HTTP request — the board card INSERT and the archive
#   statements are delegated to the sibling authorities' own surfaces
#   (subprocess argv / the SOLE WRITER's own upsert), never
#   re-implemented; a credential-shaped string (pit-*) on any surface
#   REFUSES rather than echo. Ids are MASKED (last-4) on every operator
#   surface; a full id rides inside the machine JSON payloads and the
#   subprocess argv only.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE, everywhere in this tooling. The
# U20 family holds NO credential surface at all (the board card is board
# copy — the card INSERT is a local sqlite statement, the archive
# statements are delegated to the ledger writer and the board client, and
# a Welcome card cannot leak a secret it never holds); the family's
# surfaces are the local databases (the engine state database
# anthology_state.db, the Command Center mission-control.db) and the local
# producer guide. No token value is ever printed; nothing is ever read
# from the process env except the path-resolution variables below, which
# are NAMES of paths, never secrets. The family performs NO HTTP request,
# so it defines NO User-Agent constant of its own: the browser UA that
# defeats the Cloudflare edge (CF error 1010) is CAF_BROWSER_UA, owned by
# anthology_registry.py and applied by its clients — verify_board's
# self-test PINS the constant (a well-formed browser UA, never
# "Python-urllib") so a drifted UA is caught before a single live request
# ever rides the family.
#
# BROWSER UA (CF 1010 LAW): every request to GoHighLevel / Convert and
# Flow rides reg.CafClient, which applies CAF_BROWSER_UA on EVERY request
# so the Cloudflare edge fronting services.leadconnectorhq.com never 1010s
# a verify request (CF error 1010; the W0.6 / GK-09 discipline — urllib's
# default "Python-urllib/x.y" is 403'd at the WAF edge before it ever
# reaches the API). The U20 family makes NO network call at all (its
# surfaces are the local databases and the local guide), so it defines NO
# User-Agent constant of its own — verify_board pins the exact constant on
# its OFFLINE self-test (the GK-09 regression pin) so a registry regression
# is caught OFFLINE first, never first seen as a 1010 at runtime.
#
# FAIL-CLOSED (the whole point): a missing database STOPS (exit 2, the
# AF-AE-WELCOME-DB-MISSING / AF-AE-DBC-NO-DB / AF-AE-VRBOARD-NO-DB family —
# a missing DB is never "board cleared", never a no-op pass), an unreadable
# or schema-less database STOPS before any write path (the read-only open
# is the gate's OWN known-good control — the write is never trusted into
# the unknown), an ACTION without --execute STOPS (exit 2 — the Trevor
# gate, never a silent no-op and never a silent write), a drifted
# HOW-TO-USE.md or a content-law break FAILS the build (exit 5, the
# AF-AE-WELCOME-SOURCE-DRIFT / AF-AE-WELCOME-CONTENT-VIOLATION family —
# a drifted guide NEVER ships a card), a foreign row under the card's own
# key is a MISMATCH never overwritten (exit 5), a refused write is a STOP
# or HELD per class (exit 2 / exit 3 — never reported inserted), a
# read-back that does not prove the write is a MISMATCH (exit 5), a live
# drill card or an absent Welcome card on the board is a MISMATCH (exit 5,
# never a pass), a board that cannot be READ is STOP or HELD (exit 2 /
# exit 3 — UNDETERMINED, never a verdict), a credential-shaped value on
# any surface REFUSES rather than echo, and a drifted authority breaks the
# family's self-tests FIRST (exit 4 — a tamper never masquerades as exit
# 1). A success is claimed ONLY when the write is read back byte-exact
# and every write step ran under its gate. Every deviation is NAMED with
# its code — never a bare "something failed".
#
# DOCTRINE (house, per anthology_registry.py / drive_adapter.py / the
# u20 __init__.py): move in silence (operator-verbose only); NOTHING
# Anthropic in any runtime file; Convert and Flow naming in every client
# surface; STDLIB ONLY; calls NO model; never a client PII; a law is read
# once, in one module (welcome_builder owns the card record + the meta
# insert, welcome_action / db_connector own the board seed, verify_board
# owns the board verification, archive_action owns the archive statements,
# attack_no_cards owns the zero-cards attack census — the fixtures derive
# from them, never re-implement). READ-ONLY by doctrine — the engine's
# database is READ-ONLY in dry-run; a WRITE ACTION (the card INSERT, the
# archive statements) is Trevor-gated (--execute) and even WITH --execute
# it is idempotent with a byte-exact read-back (never a blind insert,
# never a duplicate card, never a foreign overwrite). Self-test failures
# are exit 4 (enforced violation, the AF-AE-WELCOME-ATTACK /
# AF-AE-DBC-ATTACK / AF-AE-VRBOARD-ATTACK family) — a tamper never
# masquerades as exit 1.
#
# USAGE (this module's own machine surface — pure data, nothing to leak):
#   python3 docs_u20.py                ONE JSON catalog of the whole tooling
#   python3 docs_u20.py readme         the rendered README (markdown text)
#   python3 docs_u20.py self-test      OFFLINE drift gate over the docs vs
#                                      the shipped tree; 0 clean, 4 drift
# =============================================================================
"""docs_u20.py -- README / module docstring for the U20 tooling, as an
importable fail-closed pure-data module: the Welcome-card and board-hygiene
family (welcome_builder / welcome_action / db_connector / verify_board /
archive_action / attack_no_cards under the sibling-helper shipping doctrine
— the U20 manifest row is PENDING, staged under the manifest-pending/
pattern), its seven verified items, the u20_modules inventory, the house
exit codes, and the credential / browser-UA / doctrine contracts. Performs
no I/O at import and holds no credential; readme() is rendered from the
same structured data the self-test asserts against, so documentation and
data cannot drift."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# The fixed report contract (mirrors the golden-fixture naming discipline).
# ---------------------------------------------------------------------------
DOC_CONTRACT = "anthology-engine-u20-tooling-docs"
SCHEMA_VERSION = 1

# The U20 family's verifier stays the family's single manifest surface
# under the U02 row-54 shipping law; the u20_modules/ siblings ship as
# non-manifest helpers (the delivery_report.py row-12 pattern, exactly the
# docs_u02.py / docs_u03.py / docs_u04.py / docs_u05.py / docs_u06.py /
# docs_u07.py siblings). The U20 family's OWN manifest row is PENDING — not
# yet stamped; the manifest-pending/u20.json stage is the machine-readable
# input to the future stamp, exactly as the U07 family was staged
# (manifest-pending/u07.json) before its row-59 stamp.
U20_VERIFIER = None  # the family has no single dispatcher yet; its
                     # surfaces are the importable siblings themselves
U20_MANIFEST_ROW = None  # ENGINE-MANIFEST.json row: PENDING (staged under
                         # the manifest-pending/ pattern, never claimed)
U20_SHIPPING_VERSION = "v0.1.24 (2026-08-11)"  # skill-version at ship time

# ---------------------------------------------------------------------------
# THE SEVEN VERIFIED ITEMS (MASTER-SPEC U20 — the family's seven gates, in
# the FIXED order the doctrine carries them). Item numbers are
# load-bearing (positions 1..7, exactly seven — self-test pins the count);
# the title is the README heading, asserts the fail-closed claim, sources
# the engine's source of truth, and fails the operator surface on drift.
# ---------------------------------------------------------------------------
VERIFY_ITEMS = (
    {
        "item": 1,
        "title": "Producer-voice law — the Welcome card content derives from HOW-TO-USE.md",
        "asserts": ("the Welcome card's content derives from HOW-TO-USE.md "
                    "(the engine's producer-facing guide, CHANGELOG 0.1.0: "
                    "'HOW-TO-USE.md (producer, Convert and Flow naming)' — "
                    "the ONLY producer-language source of truth) and the "
                    "card body renders from the guide's OWN copy by EXACT "
                    "SECTION ORDER (the title line, the intro paragraph, "
                    "then the six sections verbatim with their own "
                    "headings byte-exact — the module ADDS NOTHING and "
                    "DROPS NOTHING; welcome_builder.py owns the card "
                    "record, the family's single authority); the "
                    "producer-language LAW is enforced, never described: "
                    "the body MUST mention 'participant' / 'participants' "
                    "(the producer's co-authors are participants, never "
                    "contributors, never users) and MUST carry the "
                    "Convert and Flow naming (the client-facing platform "
                    "name, the engine's standing doctrine); a heading "
                    "renamed, dropped, or reordered, or a content-law "
                    "break, refuses the build — a drifted guide NEVER "
                    "ships a card"),
        "source": "HOW-TO-USE.md at the skill root (the producer how-to), "
                  "read by welcome_builder.py at build time; the card "
                  "record's provenance markers are the guide's own sha256 "
                  "and skill-version.txt (digest only — drift is "
                  "DETECTABLE, never silent)",
        "fails": "AF-AE-WELCOME-SOURCE-UNREADABLE (exit 2 — a card that "
                 "cannot see its law never fabricates a pass), "
                 "AF-AE-WELCOME-SOURCE-DRIFT (exit 5 — a heading renamed, "
                 "dropped, or reordered, or a title line that is not the "
                 "guide's '# ' title), AF-AE-WELCOME-CONTENT-VIOLATION "
                 "(exit 5 — participant(s) or the Convert and Flow naming "
                 "absent from the body)",
    },
    {
        "item": 2,
        "title": "Read-only-dry-run law — the engine's database is READ-ONLY without --execute",
        "asserts": ("the engine's database is READ-ONLY in every "
                    "non-execute path of the family (the u20 package-init "
                    "doctrine): the state database (anthology_state.db, "
                    "the engine's own key-value mirror — the meta table, "
                    "schema pinned byte-exact) is opened ONLY in the "
                    "sqlite URI mode=ro by welcome_builder's control and "
                    "read-back handles; the Command Center "
                    "mission-control.db is opened by db_connector with "
                    "the SQLITE QUERY-ONLY pragma plus an IMMEDIATE "
                    "rollback transaction that is always rolled back; a "
                    "dry-run is the OFFLINE plan, never a lesser build — "
                    "plan reads nothing from the database at all; every "
                    "module's self-test proves the database file is never "
                    "created and no byte changes in any non-execute path "
                    "(the strongest form: the archive battery proves the "
                    "mirror is BYTE-IDENTICAL after every non-execute "
                    "call)"),
        "source": "u20_modules/__init__.py (the package doctrine: 'the "
                  "engine's database is READ-ONLY in dry-run: this "
                  "package must never write the DB unless the caller "
                  "passed --execute explicitly'); the sqlite mode=ro URI "
                  "and the QUERY-ONLY pragma are the module-level "
                  "mechanisms",
        "fails": "any module that opens a write handle outside the single "
                 "--execute-gated write path; a dry-run that touches the "
                 "database at all; the self-test asserts fail (exit 4) — "
                 "the READ-ONLY law is enforced, never described",
    },
    {
        "item": 3,
        "title": "Trevor gate — every ACTION surface requires --execute",
        "asserts": ("every ACTION surface of the family REQUIRES the "
                    "operator's explicit --execute (the Trevor gate, the "
                    "u20 package-init doctrine): the card INSERT in "
                    "welcome_builder (build) / welcome_action (seed) / "
                    "db_connector (seed), the archive statements in "
                    "archive_action (archive), and the verify ACTION in "
                    "verify_board (check); WITHOUT --execute an ACTION "
                    "request is a STOP (exit 2, the AF-AE-WELCOME-"
                    "NO-EXECUTE / AF-AE-DBC-NO-EXECUTE / "
                    "AF-AE-VRBOARD-NO-EXECUTE / AF-AE-U20ARCHIVE-"
                    "NO-EXECUTE family), never a silent no-op and never a "
                    "silent write — the module reports exactly what it "
                    "WOULD do and exits without mutating; dry-run and "
                    "no-execute are DIFFERENT laws: a plan exits 0 (the "
                    "truthful offline plan), an ACTION without the gate "
                    "exits 2; even WITH --execute the write is "
                    "idempotent and read back byte-exact — never a blind "
                    "insert, never a duplicate card, never a foreign "
                    "overwrite"),
        "source": "u20_modules/__init__.py (the fail-closed empty package "
                  "init: 'Without --execute, report what WOULD happen and "
                  "exit without mutating'); the --execute flag on every "
                  "CLI surface, pinned by each module's self-test",
        "fails": "AF-AE-WELCOME-NO-EXECUTE / AF-AE-DBC-NO-EXECUTE / "
                 "AF-AE-VRBOARD-NO-EXECUTE / AF-AE-U20ARCHIVE-NO-EXECUTE "
                 "(exit 2) — an ACTION requested without --execute; a "
                 "module that writes without the gate is a self-test "
                 "failure (exit 4)",
    },
    {
        "item": 4,
        "title": "Idempotency law — GET-first, seed only if absent",
        "asserts": ("the family seeds only what is absent (GET-first, "
                    "idempotent by construction): the meta row under "
                    "'welcome::producer' already present with identical "
                    "content is an IDEMPOTENT NO-OP (exit 0, never a "
                    "second row — the same key re-inserted is an upsert, "
                    "never a duplicate card); an existing 'Welcome to "
                    "Anthology' task on the board (any status, any "
                    "archival state — the 'already welcomed' truth is "
                    "checked as presence) is 'already welcomed', never "
                    "re-seeded and never archived; an already-archived "
                    "anthology row is an IDEMPOTENT NO-OP (exit 0, never "
                    "a second archive); a foreign value under the card's "
                    "own key is a MISMATCH (exit 5), never blindly "
                    "overwritten; a zero-cards board census is the golden "
                    "no-op (PASS exit 0 — a welcome-sync with no board to "
                    "sync writes NOTHING)"),
        "source": "welcome_builder.build_action / welcome_action."
                  "seed_welcome / db_connector / archive_action / "
                  "attack_no_cards.verify — each pins the idempotency law "
                  "on its own surface; the stable keys are 'welcome::"
                  "producer' (the meta row) and the 'Welcome to Anthology' "
                  "title byte-exact (the board task)",
        "fails": "a duplicate card, a second row, a re-seed over an "
                 "existing card, or a foreign overwrite under the card's "
                 "own key (exit 5 — AF-AE-WELCOME-DB-MISMATCH); the "
                 "idempotency no-ops themselves are the goldens the "
                 "self-tests assert",
    },
    {
        "item": 5,
        "title": "Read-back law — a write is never trusted without read-back",
        "asserts": ("a write is never trusted without read-back: the card "
                    "INSERT is re-read through the READ-ONLY open and "
                    "compared byte-exact against what was inserted (a "
                    "missing or drifted read-back is a MISMATCH, exit 5, "
                    "AF-AE-WELCOME-READBACK-MISMATCH — nothing is ever "
                    "reported inserted without read-back); the archive "
                    "statements are followed by a re-read of the LEDGER "
                    "target through the SOLE WRITER's own read-only "
                    "surface (anthology_state get-anthology, READ-ONLY by "
                    "the ledger's own _READ_ONLY set) compared BYTE-EXACT "
                    "against the ledger's archived vocabulary (a drift is "
                    "exit 5, never a false success; an unreadable "
                    "read-back is HELD, exit 3, never a verdict); the "
                    "seeded board card is SELECTed back by its task id "
                    "and confirmed present before anything claims seeded"),
        "source": "welcome_builder.build_action (step 6) / "
                  "archive_action (the read-back law) / "
                  "welcome_action.seed_welcome — the read-back open is "
                  "READ-ONLY (mode=ro) so the proof itself can never "
                  "mutate",
        "fails": "AF-AE-WELCOME-READBACK-MISMATCH / "
                 "AF-AE-DBC-READBACK-MISMATCH / the archive read-back "
                 "drift (exit 5) — a write that cannot be proved is "
                 "never reported; a read-back that cannot be read is "
                 "HELD (exit 3), never a verdict",
    },
    {
        "item": 6,
        "title": "Zero-drill law — the open board carries zero synthetic cards and the Welcome card",
        "asserts": ("the post-action board verification confirms, "
                    "fail-closed (the U14 board-hygiene law, carried in "
                    "from the Command Center's "
                    "u14-anthology-board-hygiene.py, never re-typed): (a) "
                    "ZERO synthetic drill cards are LIVE on the open board "
                    "— a drill card is ANY Anthology-board task whose "
                    "title contains the 'ZZZ' or 'SYNTHETIC' markers (the "
                    "markers that can only be drill data, never a real "
                    "co-author; 'Anthology chapter — <name>' cards can "
                    "NEVER be caught), and 'LIVE' means archived_at IS "
                    "NULL — the tasks API's own 'on the open board' "
                    "filter (src/app/api/tasks/route.ts), so a "
                    "soft-archived drill card is OFF the board and NOT a "
                    "violation; (b) ONE byte-exact 'Welcome to Anthology' "
                    "card is LIVE on the open board, scoped to the "
                    "'anthology' workspace; the verifier (verify_board.py) "
                    "is READ-ONLY by construction — every connection it "
                    "opens is sqlite URI mode=ro, so no code path can "
                    "mutate even by accident; a board that cannot be READ "
                    "is STOP or HELD (exit 2 / exit 3) — UNDETERMINED, "
                    "never a verdict"),
        "source": "u14-anthology-board-hygiene.py (the zero-drill law "
                  "authority, never re-typed) + verify_board.py (the "
                  "read-back half) + the Command Center tasks API filter "
                  "(src/app/api/tasks/route.ts `AND t.archived_at IS "
                  "NULL`)",
        "fails": "AF-AE-VRBOARD-DRILLS-LIVE (exit 5 — one or more live "
                 "ZZZ/SYNTHETIC drill cards, the report names the masked "
                 "ids), AF-AE-VRBOARD-NO-WELCOME (exit 5 — the byte-exact "
                 "Welcome card absent or non-byte-exact; the report names "
                 "the remediation: the seed ACTION is the sibling's, "
                 "Trevor-gated, never re-implemented here), "
                 "AF-AE-VRBOARD-NO-DB / AF-AE-VRBOARD-TASKS-MISSING "
                 "(exit 2), a read refusal HELD (exit 3)",
    },
    {
        "item": 7,
        "title": "Zero-cards attack law — the empty census is the golden no-op, never a write",
        "asserts": ("a board census carrying ZERO cards is the exact state "
                    "where a welcome-sync would need a WRITE to create the "
                    "Welcome card — and the SAME gate must judge it a "
                    "clean PASS no-op (exit 0), because the Welcome card "
                    "is copy that 'ships' from the manifest, never a "
                    "write the engine performs, and the engine's database "
                    "is READ-ONLY in dry-run: WITHOUT --execute no module "
                    "may write it at all (attack_no_cards.py, the attack "
                    "half of the U20 welcome pair — the fail-closed "
                    "WELCOME-CARD law over the board projection surface); "
                    "the zero-cards census is the GOLDEN no-op — a "
                    "welcome-sync with no board to sync writes NOTHING — "
                    "and the --execute law is pinned the other direction: "
                    "the Welcome card is copy-only, so even WITH "
                    "--execute the fixture never writes; ANY card present, "
                    "a malformed census, a missing 'cards' key, a "
                    "non-list array, or a credential-shaped string on the "
                    "census raises NoCardsError (STOP / mismatch family, "
                    "never a pass, never a silent fallback) — the attack "
                    "fixture is DATA, and a census that cannot be judged "
                    "is refused, never certified clean"),
        "source": "attack_no_cards.py (the zero-cards attack fixture) + "
                  "the u20 package-init doctrine (the Welcome card ships "
                  "as copy only, never as a write); the census shape is "
                  "the board projection surface ({\"cards\": [...]})",
        "fails": "AF-AE-WELCOME-CARDS-PRESENT / AF-AE-WELCOME-MALFORMED "
                 "(exit 5, the NoCardsError refusal family — never a "
                 "pass, never a silent fallback); a zero-cards census "
                 "that is judged anything but a PASS no-op is a broken "
                 "gate; the attack fixtures REFUSED with their golden "
                 "controls PASSING, and a fixture that PASSES any census "
                 "gate is a broken gate",
    },
)

# ---------------------------------------------------------------------------
# THE MODULE INVENTORY. `place` names the directory relative to this module
# (the u20_modules package itself); self-test proves each name exists at
# that place. `role` is the one-line contract each module owns; `offline`
# names the credential-free surface; `exit_codes` follows the house
# convention (0/1/2/3/5, 4 = self-test).
# ---------------------------------------------------------------------------
MODULES = (
    {
        "name": "__init__.py",
        "place": "scripts/u20_modules/",
        "manifest_row": None,
        "role": ("fail-closed EMPTY package init — pure namespace "
                 "container, no runtime code; modules are imported BY "
                 "NAME; records the package doctrine (fail-closed, secrets "
                 "by label, browser-UA law for every GoHighLevel / Convert "
                 "and Flow surface, the engine's database READ-ONLY in "
                 "dry-run, the Trevor-gated --execute ACTION, the Welcome "
                 "card as copy-only from HOW-TO-USE.md, move in silence)"),
        "offline": "trivially — it is empty",
        "exit_codes": "n/a (no executable surface)",
    },
    {
        "name": "welcome_builder.py",
        "place": "scripts/u20_modules/",
        "manifest_row": None,
        "role": ("the PRODUCER WELCOME CARD BUILDER — HOW-TO-USE.md "
                 "becomes the card's body copy by exact section order "
                 "(title line, intro, then the six sections verbatim, the "
                 "producer-language law enforced: participant(s) and the "
                 "Convert and Flow naming MUST ride the body), the card "
                 "record rides provenance markers (source sha256, "
                 "built_at, engine version), and the single INSERT into "
                 "the engine state database's meta table under the stable "
                 "key 'welcome::producer' is EXECUTED ONLY under "
                 "--execute (the Trevor gate); the engine database is "
                 "READ-ONLY in every non-execute path (mode=ro control "
                 "and read-back); idempotent by construction (a "
                 "present-and-identical card is an IDEMPOTENT NO-OP, a "
                 "foreign value under the card key is a MISMATCH never "
                 "overwritten); READ-BACK LAW (a write is never trusted "
                 "without read-back); the schema law is pinned byte-exact "
                 "and proven read-only BEFORE any write path; SQL is "
                 "never string-interpolated (named columns, one parameter "
                 "per value)"),
        "offline": "entirely — pure build + plan + self-test (the "
                   "self-test exercises --execute against a TEMP "
                   "database; no network, no credentials)",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "welcome_action.py",
        "place": "scripts/u20_modules/",
        "manifest_row": None,
        "role": ("the ANTHOLOGY WELCOME CARD SEEDER — the fail-closed, "
                 "GET-first idempotent seeder that lands the "
                 "producer-facing WELCOME card on the client's Command "
                 "Center Anthology department board (a task row, the "
                 "shape Skill 32's add-department.sh step 3 seeds: "
                 "department 'anthology', status 'backlog', assigned to "
                 "the Anthology department-head agent, priority medium); "
                 "the card INSERT runs ONLY under --execute (Trevor-gated, "
                 "AF-AE-WELCOME-NO-EXECUTE otherwise); IDEMPOTENCY LAW "
                 "(GET-first by the fixed idempotency marker 'Ref: "
                 "anthology:welcome:card' — an existing card is verified "
                 "and skipped, never a duplicate, never a second INSERT); "
                 "READ-BACK LAW (the seeded row is SELECTed back by its "
                 "task id before anything claims seeded); the target is "
                 "mission-control.db — no candidate found and no "
                 "DATABASE_PATH is a STOP, never a write into the "
                 "unknown; the engine's own anthology_state.db is NEVER "
                 "opened by this module"),
        "offline": "plan + self-test (no database I/O, no network, no "
                   "credentials)",
        "exit_codes": "0/1/2/4/5",
    },
    {
        "name": "db_connector.py",
        "place": "scripts/u20_modules/",
        "manifest_row": None,
        "role": ("the FAIL-CLOSED SQLITE3 CONNECTOR over the Command "
                 "Center mission-control.db — the shared DB surface the "
                 "U20 Welcome-card family imports; default and --dry-run "
                 "are READ-ONLY (the SQLITE QUERY-ONLY pragma plus an "
                 "IMMEDIATE rollback transaction that is always rolled "
                 "back); the card INSERT itself runs ONLY under "
                 "--execute (AF-AE-DBC-NO-EXECUTE, exit 2, otherwise); "
                 "the --execute write is IDEMPOTENT and SAFE (refuses to "
                 "run when a Welcome card already exists on the anthology "
                 "board — any status, any archival state; only ever "
                 "writes the ONE seeded card, no archive, no update, no "
                 "delete of anything); a missing / unreadable database "
                 "is a STOP (AF-AE-DBC-NO-DB, exit 2 — never 'board "
                 "cleared', never a no-op pass); the board is "
                 "workspaces.slug='anthology' and a card is 'on the open "
                 "board' only while tasks.archived_at IS NULL; never "
                 "touches the engine's own state ledger (that surface is "
                 "anthology_state.py's alone); the copy says 'editors', "
                 "never 'AI'"),
        "offline": "plan + self-test (no network, no credentials, no "
                   "write in any non-execute path)",
        "exit_codes": "0/1/2/4/5",
    },
    {
        "name": "verify_board.py",
        "place": "scripts/u20_modules/",
        "manifest_row": None,
        "role": ("the POST-ACTION BOARD VERIFIER — the read-back half of "
                 "the Anthology board hygiene ACTION (the U14 "
                 "board-hygiene law, carried in from "
                 "u14-anthology-board-hygiene.py, never re-typed): "
                 "re-reads the Command Center's Anthology department "
                 "board and CONFIRMS, fail-closed, that (a) ZERO "
                 "synthetic drill cards are LIVE on the open board (the "
                 "'ZZZ' / 'SYNTHETIC' marker titles; LIVE means "
                 "archived_at IS NULL — a soft-archived drill card is "
                 "OFF the board and NOT a violation), and (b) ONE "
                 "byte-exact 'Welcome to Anthology' card is PRESENT on "
                 "the open board (its content derives from HOW-TO-USE.md "
                 "— copy, never a write); READ-ONLY by construction "
                 "(every connection is sqlite URI mode=ro — no code path "
                 "can mutate even by accident); the VERIFY ACTION is "
                 "--execute-gated (AF-AE-VRBOARD-NO-EXECUTE, exit 2 — an "
                 "ACTION without the Trevor gate is a STOP, never a "
                 "silent no-op); a board that cannot be READ is STOP or "
                 "HELD (exit 2 / exit 3 — UNDETERMINED, never a "
                 "verdict); the database is found by path only (--db > "
                 "DATABASE_PATH > the family candidate list); the "
                 "self-test PINS CAF_BROWSER_UA (a well-formed browser "
                 "UA, never 'Python-urllib') so a drifted UA is caught "
                 "before a single live request ever rides the family"),
        "offline": "plan + self-test (the golden board fixture, no "
                   "network, no credentials, no write in any path)",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "archive_action.py",
        "place": "scripts/u20_modules/",
        "manifest_row": None,
        "role": ("the ARCHIVE ACTION — the Trevor-gated producer archive "
                 "surface for the engine's OWN ledger (the local SQLite "
                 "mirror, anthology_state.py — the SOLE writer) plus the "
                 "Welcome card content the producer's board carries; the "
                 "archive STATEMENTS (the two statements, carried in "
                 "from the engine's own revoke flow — "
                 "revoke-anthology-client.sh R6 / R2, never a second "
                 "implementation: the LEDGER statement via anthology_state "
                 "upsert-anthology --status archived, the BOARD statement "
                 "via mc_board.py archive --anthology-id <id>) run ONLY "
                 "under --execute; without --execute the module is a "
                 "READ-ONLY dry-run (reports what it WOULD archive, exits "
                 "without mutating — STOP exit 2 on an archive request, "
                 "PASS exit 0 on a plan); the READ-BACK LAW (the LEDGER "
                 "target is re-read through the SOLE WRITER's own "
                 "read-only surface and compared BYTE-EXACT against the "
                 "ledger's archived vocabulary — a drift is a MISMATCH, "
                 "exit 5); an anthology with NO ledger row has NOTHING to "
                 "archive — a clean no-op PASS exit 0 (the golden "
                 "absent-state law); reads HOW-TO-USE.md from the skill "
                 "root when it exists (an unreadable or absent guide is a "
                 "STOP, exit 2 — the Welcome surface never ships empty "
                 "or fabricated); the masking law (every operator surface "
                 "carries the anthology id by MASKED MARKER only, last-4); "
                 "a credential-shaped string (pit-*) on any surface "
                 "REFUSES rather than echo"),
        "offline": "plan + self-test (no subprocess spawns, no network, "
                   "no credentials, no write in any non-execute path)",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "attack_no_cards.py",
        "place": "scripts/u20_modules/",
        "manifest_row": None,
        "role": ("the ZERO-CARDS ATTACK FIXTURE — the attack half of the "
                 "U20 welcome pair: the board census that carries ZERO "
                 "cards, the exact state where a welcome-sync would need "
                 "a WRITE to create the Welcome card, judged a clean PASS "
                 "no-op (exit 0) by the SAME gate — because the Welcome "
                 "card is copy that ships from the manifest, never a "
                 "write the engine performs, and the engine's database is "
                 "READ-ONLY in dry-run (WITHOUT --execute no module may "
                 "write it at all); owns WELCOME_SOURCE (the path of the "
                 "Welcome card's copy source, HOW-TO-USE.md — the copy "
                 "LIVES in the guide, the fixture owns the LAW that the "
                 "card is copy-only), verify(census) (ZERO cards -> "
                 "'PASS', the golden no-op; any card present, a malformed "
                 "census, a missing 'cards' key, a non-list array, or a "
                 "credential-shaped string -> NoCardsError, refused never "
                 "certified clean), and dry_run(census) (the OFFLINE plan "
                 "body: writes_needed FALSE, would_do 'write nothing'); "
                 "even WITH --execute the fixture never writes"),
        "offline": "entirely — pure data + the census gate + self-test "
                   "(no network, no credentials, no write in any path)",
        "exit_codes": "0/1/4/5",
    },
    {
        "name": "test_archive_stmt.py",
        "place": "scripts/u20_modules/",
        "manifest_row": None,
        "role": ("the UNIT-TEST BATTERY for the U20 archive ACTION — "
                 "pins the Trevor-gated --execute law at the function "
                 "level (archive(..., execute=False) returns EX_STOP and "
                 "the mirror file is BYTE-IDENTICAL after — the strongest "
                 "form of 'the DB is read-only in dry-run') and at the "
                 "CLI level (main(['archive', ...]) without --execute is "
                 "the same STOP; main(['plan']) / --dry-run is the "
                 "truthful offline plan, exit 0 — dry-run and no-execute "
                 "are DIFFERENT laws); pins read-only-by-construction "
                 "(the mirror is opened mode=ro, the only writes anywhere "
                 "ride the sibling authorities' subprocess argv and only "
                 "under --execute); pins the two statements delegate "
                 "never re-implement (the write surface is the argv, "
                 "never a local SQL statement); pins the READ-BACK LAW "
                 "(byte-exact against the archived vocabulary; an "
                 "unreadable read-back is HELD exit 3); pins the "
                 "absent-state law (no ledger row -> clean no-op PASS "
                 "exit 0, zero statements, zero writes), the idempotent "
                 "no-op (an already-archived row is PASS exit 0, never a "
                 "second archive), the fail-closed Welcome (absent or "
                 "unreadable HOW-TO-USE.md is a STOP before anything "
                 "else runs), the board fail-soft (a declined / "
                 "unreachable board returns exit 0 and reconciles on the "
                 "daily tick — the ledger is the truth), and the masking "
                 "law (the battery proves no full id and no credential "
                 "value reaches any surface)"),
        "offline": "entirely — pytest battery over temp mirrors, no "
                   "network, no credentials, no write in any non-execute "
                   "path",
        "exit_codes": "n/a (pytest battery; assertions fail the run, "
                      "never a fabricated pass)",
    },
    {
        "name": "docs_u20.py",
        "place": "scripts/u20_modules/",
        "manifest_row": None,
        "role": ("THIS MODULE — the U20 tooling README / catalog data + "
                 "drift gate: the module inventory, the seven verified "
                 "items, the house exit codes, the AF autofail family, the "
                 "doctrine, and the credential labels as DATA; readme() "
                 "renders FROM the data and self_test() proves the tree "
                 "ships together (a doc that names a module that does not "
                 "ship FAILS, exit 4)"),
        "offline": "entirely — pure data + filesystem existence checks, "
                   "no network, no secrets",
        "exit_codes": "0/1/4",
    },
)

# ---------------------------------------------------------------------------
# HOUSE EXIT CODES (0/1/2/3/5; 4 = enforced violation). The exact contract
# the U20 family commits to; self-test pins all six.
# ---------------------------------------------------------------------------
EXIT_CODES = {
    0: "verified success — an idempotent no-op (a card / board state "
       "already present, an already-archived row, a zero-cards census), a "
       "completed dry-run / plan, an ACTION executed under --execute and "
       "read back byte-exact, or the offline self-test; an EMPTY census "
       "is a truthful PASS",
    1: "unexpected error (top-level guard; never a secret leak)",
    2: ("STOP refusal — usage error / a database missing or unreadable "
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
        "AF-AE-VRBOARD-ATTACK family, enforced violation) — a tamper "
        "never masquerades as exit 1"),
    5: ("mismatch / fail-closed default — a source drift (a heading "
        "renamed, dropped, or reordered), a content-law violation "
        "(participant(s) or the Convert and Flow naming absent), a "
        "foreign value under the card's own key, a drifted meta schema, "
        "a read-back that does not prove the write, a live "
        "ZZZ/SYNTHETIC drill card on the open board, a Welcome card "
        "absent or not byte-exact, a credential-shaped value on a "
        "surface (leak-scan REFUSAL), or a malformed / non-empty census "
        "refused by the attack fixture — never a fabricated pass"),
}

# ---------------------------------------------------------------------------
# THE AF AUTOfail FAMILY of the U20 tooling — the codes the family's own
# surfaces declare. None of the U20-specific codes are stamped in
# ENGINE-MANIFEST.json yet (the family is PENDING — verified at ship time,
# 2026-08-11, staged under the manifest-pending/ pattern); the shared
# AF-AE-READBACK-MISMATCH / AF-AE-TEMPLATE-ATTACK codes already live in
# the manifest. Self-test failures are exit 4, never 1.
# ---------------------------------------------------------------------------
AF_CODES = (
    ("AF-AE-WELCOME-NO-EXECUTE", 2,
     "an ACTION (the card INSERT / the VERIFY ACTION) was requested "
     "WITHOUT --execute — the Trevor gate: the module reports exactly "
     "what it WOULD do and exits without mutating (STOP, never a silent "
     "no-op and never a silent write)"),
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
     "the shared house code with the U02 / U03 / U04 / U05 / U06 "
     "families (already stamped in ENGINE-MANIFEST.json)"),
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
     "violation)"),
    ("AF-AE-VRBOARD-NO-DB", 2,
     "the Command Center database is absent, unreadable, or unopenable — "
     "a missing DB is never 'board clean', never a no-op pass"),
    ("AF-AE-VRBOARD-NO-EXECUTE", 2,
     "the VERIFY ACTION was requested without --execute — the module "
     "NEVER runs the ACTION without the explicit Trevor-gated execute "
     "flag (plan and self-test are OFFLINE and do not require it)"),
    ("AF-AE-VRBOARD-TASKS-MISSING", 2,
     "the tasks table is absent from the database (a schema that "
     "predates the board, or the wrong database) — never a blind sweep "
     "of nothing"),
    ("AF-AE-VRBOARD-DRILLS-LIVE", 5,
     "one or more ZZZ/SYNTHETIC drill cards are LIVE on the open board — "
     "the zero-drill law is violated; the report names the masked ids"),
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
    ("AF-AE-TEMPLATE-ATTACK", 4,
     "an attack fixture tripped the OFFLINE self-test of a family "
     "battery (enforced violation — the house code, shared with the "
     "U02 / U03 / U04 / U05 / U06 / U07 families)"),
)

# ---------------------------------------------------------------------------
# DOCTRINE — the house rules the whole U20 tooling commits to, as data so
# the README renders them from the same source the self-test asserts.
# ---------------------------------------------------------------------------
DOCTRINE = (
    ("Fail-closed", "a missing database, a malformed input, an "
     "unreadable source, or a board that cannot be read is a REFUSAL or "
     "a recorded FAIL — never a blind pass, never a fabricated success; "
     "a drifted HOW-TO-USE.md NEVER ships a card; an ACTION without "
     "--execute is a STOP (exit 2), never a silent no-op and never a "
     "silent write; an id is NEVER guessed from memory"),
    ("Read-only dry-run", "the engine's database is READ-ONLY in "
     "dry-run (the u20 package-init doctrine): the state database opens "
     "only in the sqlite URI mode=ro, the Command Center database opens "
     "with the QUERY-ONLY pragma and a rollback transaction; a dry-run "
     "is the OFFLINE plan, never a lesser build; the self-tests prove "
     "no database file is created and no byte changes in any "
     "non-execute path (the archive battery's byte-identical mirror is "
     "the strongest form)"),
    ("Trevor-gated writes", "--execute is the ONLY flag that performs "
     "a WRITE ACTION: the card INSERT (welcome_builder build / "
     "welcome_action seed / db_connector seed) and the archive "
     "statements (archive_action archive) run ONLY under the operator's "
     "explicit --execute — and even WITH --execute the write is "
     "idempotent and read back byte-exact (never a blind insert, never "
     "a duplicate card, never a foreign overwrite, never a second "
     "archive); dry-run and no-execute are DIFFERENT laws (a plan exits "
     "0, an ACTION without the gate exits 2)"),
    ("Secrets", "the family holds NO credential and resolves NONE: the "
     "board card is board copy — a Welcome card cannot leak a secret it "
     "never holds; the archive statements are delegated to the ledger "
     "writer and the board client, which resolve their own credentials "
     "BY LABEL (SET / NOT SET only); a credential-shaped string "
     "(pit-*) on any surface REFUSES rather than echo; ids are MASKED "
     "(last-4) on every operator surface — full ids ride inside the "
     "machine JSON payloads and the subprocess argv only; a response "
     "body is never surfaced (it could echo a credential)"),
    ("Browser UA", "every request to GoHighLevel / Convert and Flow "
     "(services.leadconnectorhq.com) rides CAF_BROWSER_UA "
     "(reg.CafClient) — urllib's default 'Python-urllib/x.y' is 403'd "
     "at the WAF edge (CF error 1010) before it ever reaches the API "
     "(W0.6 / GK-09); the U20 family makes NO network call (its "
     "surfaces are the local databases and the local guide), so it "
     "defines NO User-Agent constant of its own — verify_board pins the "
     "exact constant on its OFFLINE self-test (the GK-09 regression "
     "pin) so a registry regression is caught HERE first"),
    ("Delegation, never re-implementation", "the write surfaces are "
     "delegated to the sibling authorities' own channels: the card "
     "INSERT is a local sqlite statement against the engine's own meta "
     "table or the Command Center tasks table (column-intersect, the "
     "add-department.sh convention), the archive statements ride "
     "subprocess argv for anthology_state.py's OWN upsert-anthology "
     "--status archived and mc_board.py archive (never a local SQL "
     "statement, never a second implementation), the zero-drill law "
     "comes from u14-anthology-board-hygiene.py, and the card copy "
     "LIVES in HOW-TO-USE.md (the fixture owns the LAW, never a "
     "hardcoded blob)"),
    ("Negative-result contract", "the family carries its OWN golden "
     "controls (the golden card build, the golden board, the golden "
     "all-38 field census in the sibling families) so every pass/fail "
     "split discriminates the law and never a broken instrument — a "
     "gate that fails everything is a broken check, not a real fault; "
     "an attack fixture that PASSES any census gate is a broken gate; "
     "a negative is a claim and carries the same burden of proof as a "
     "positive one"),
    ("Move in silence", "operator-verbose only; NOTHING Anthropic in "
     "any runtime file; Convert and Flow naming in every client "
     "surface; STDLIB ONLY; calls NO model; never a client PII; "
     "READ-ONLY by doctrine — the WRITE ACTION is the ONE gated "
     "surface"),
)

# ---------------------------------------------------------------------------
# CREDENTIAL LABELS — BY LABEL ONLY. The U20 family holds NO credential
# and resolves NONE (the board card is board copy; the archive statements
# are delegated to the ledger writer and the board client, which resolve
# their own credentials BY LABEL through the house labels below — SET /
# NOT SET only, a token value is NEVER printed). The only process-env
# variables the family reads are path-resolution names, never secrets:
# DATABASE_PATH (the Command Center's own db path override — always
# wins), ANTHOLOGY_STATE_DIR / OPENCLAW_DATA_DIR / HOME (the engine state
# directory resolution). A label is a name, never a value.
# ---------------------------------------------------------------------------
CREDENTIAL_LABELS = {
    "token": (
        "CONVERT_AND_FLOW_PIT",
        "CONVERT_AND_FLOW_API_KEY",
        "GOHIGHLEVEL_API_KEY",
        "GOHIGHLEVEL_PIT",
        "GHL_API_KEY",
    ),
    "location": (
        "CONVERT_AND_FLOW_LOCATION_ID",
        "GOHIGHLEVEL_LOCATION_ID",
        "GHL_LOCATION_ID",
    ),
    "path_only": (
        "DATABASE_PATH",
        "ANTHOLOGY_STATE_DIR",
        "OPENCLAW_DATA_DIR",
        "HOME",
    ),
}

# Pinned counts (the fixture-counting discipline of golden_fields.py: a
# drifted inventory is drift, never tolerated). Adding a module to the U20
# tooling REQUIRES adding it here AND to the README's inventory.
CONTRACT_ITEM_COUNT = 7
CONTRACT_MODULE_COUNT = 9

class DocsError(Exception):
    """A fail-closed documentation refusal: the README data drifted from
    its own contract, so no catalog is shipped — wrong docs are worse than
    no docs."""

# ---------------------------------------------------------------------------
# Accessors — deep copies, so callers can never mutate the canonical data.
# ---------------------------------------------------------------------------
def verify_items() -> list:
    """The seven verified items as a mutable deep copy (callers may mutate
    their copy; the canonical tuple is never touched)."""
    return [dict(row) for row in VERIFY_ITEMS]

def modules() -> list:
    """The module inventory as a mutable deep copy."""
    return [dict(row) for row in MODULES]

def exit_codes() -> dict:
    """The house exit-code contract as a plain dict copy."""
    return dict(EXIT_CODES)

def af_codes() -> list:
    """The AF autofail family as plain (code, exit, meaning) tuples in a
    mutable list."""
    return list(AF_CODES)

# ---------------------------------------------------------------------------
# The rendered README — built FROM the data, so prose can never drift from
# the contract. This is the machine-readable form of the module docstring.
# ---------------------------------------------------------------------------
def readme() -> str:
    """The U20 tooling README, rendered from the structured data above.

    One markdown document: what the tooling is, the seven verified items,
    the module inventory, the house exit codes, the autofail family, the
    doctrine, and the credential labels. Because every section renders from
    the same constants the self-test asserts, a drift in the data FAILS the
    self-test before it can ship a stale README."""
    lines = [
        "# U20 tooling — Welcome-card and board-hygiene gates (README)",
        "",
        "Shipped under the ENGINE-MANIFEST.json row-54 \"template live "
        "verify (U02)\" shipping doctrine (%s; the U20 family's OWN manifest "
        "row is PENDING — not yet stamped, staged under the "
        "manifest-pending/u02.json · u03.json · u04.json · u05.json · "
        "u06.json · u07.json pattern) — the importable Welcome-card "
        "builders, the board verifier, the archive action, the zero-cards "
        "attack fixture, and the archive-statement battery in "
        "`scripts/u20_modules/` — documented machine-side by this module "
        "(`u20_modules.docs_u20`)." % U20_SHIPPING_VERSION,
        "",
        "The U20 family gates the WELCOME-CARD and BOARD-HYGIENE LAW of "
        "the anthology engine (the package-init doctrine): the engine's "
        "database is READ-ONLY in dry-run — this package must never write "
        "the DB unless the caller passed --execute explicitly "
        "(Trevor-gated). Without --execute the modules report what WOULD "
        "happen and exit without mutating. The Welcome card content "
        "derives from HOW-TO-USE.md (the producer-facing how-to — the "
        "producer owns the board, co-authors are participants, the "
        "review column is the approval queue, assembly is the producer's "
        "one-way decision, deliverables ship as BOTH a Google Doc and a "
        "designed PDF); it ships as copy only, never as a write. The "
        "card lands either in the engine state database's meta table "
        "under the stable key 'welcome::producer' (welcome_builder) or "
        "as a task row on the Command Center Anthology department board "
        "(welcome_action / db_connector — the shape Skill 32's "
        "add-department.sh step 3 seeds). The family's live surfaces "
        "read the Command Center board database by path only (--db > "
        "DATABASE_PATH > the family candidate list — a missing database "
        "is a STOP, never a guess). A WRITE ACTION (the card INSERT, "
        "the archive statements) is Trevor-gated: WITHOUT --execute an "
        "ACTION request is a STOP (exit 2) — never a silent no-op and "
        "never a silent write — and WITH --execute the write is "
        "idempotent and read back byte-exact (never a blind insert, "
        "never a duplicate card, never a foreign overwrite). The family "
        "holds NO credential and makes NO network call; a "
        "credential-shaped string (pit-*) on any surface REFUSES rather "
        "than echo.",
        "",
        "## The seven verified items (MASTER-SPEC U20 — the family's "
        "seven gates, in the FIXED order the doctrine carries them)",
        "",
    ]
    for row in VERIFY_ITEMS:
        lines.append("%d. %s — %s. Source of truth: %s. Fails: %s."
                     % (row["item"], row["title"], row["asserts"],
                        row["source"], row["fails"]))
        lines.append("")
    lines += [
        "## Module inventory",
        "",
    ]
    for row in MODULES:
        place = row["place"].rstrip("/") + "/" + row["name"]
        row_no = ("manifest row %d" % row["manifest_row"]
                  if row["manifest_row"] is not None else "sibling helper")
        lines.append("- `%s` (%s) — %s. Offline surface: %s. Exit codes: %s."
                     % (place, row_no, row["role"], row["offline"],
                        row["exit_codes"]))
    lines += [
        "",
        "## Exit codes (house convention 0/1/2/3/5; 4 = enforced violation)",
        "",
    ]
    for code in sorted(EXIT_CODES):
        lines.append("- %d — %s" % (code, EXIT_CODES[code]))
    lines += [
        "",
        "## AF autofail family",
        "",
    ]
    for code, exit_code, meaning in AF_CODES:
        lines.append("- %s (exit %d) — %s" % (code, exit_code, meaning))
    lines += [
        "",
        "## Doctrine",
        "",
    ]
    for name, text in DOCTRINE:
        lines.append("- %s: %s." % (name, text))
    lines += [
        "",
        "## Credentials — by label, never by value",
        "",
    ]
    for group, labels in CREDENTIAL_LABELS.items():
        lines.append("- %s: %s" % (group, ", ".join(labels)))
    return "\n".join(lines) + "\n"

# ---------------------------------------------------------------------------
# Self-test — OFFLINE: the documentation's drift gate. No network, no
# credentials, only read-only filesystem existence checks for the modules
# the README claims ship. A FAILED self-test is exit 4 (enforced
# violation), never 'unexpected error' — the house self-test discipline.
# ---------------------------------------------------------------------------
EX_VIOLATION = 4

def _module_file(row: dict) -> Path:
    """The on-disk path a README inventory row claims. Every U20 row lives
    next to this module (scripts/u20_modules/)."""
    base = Path(__file__).resolve().parent
    if row.get("place", "").strip("/") == "scripts":
        base = base.parent
    return base / row["name"]

def _self_test_body(dev) -> None:
    dev.write("[docs-u20] pinning: %d verified items, %d modules, "
              "exit codes 0..5\n"
              % (CONTRACT_ITEM_COUNT, CONTRACT_MODULE_COUNT))

    items = VERIFY_ITEMS
    if len(items) != CONTRACT_ITEM_COUNT:
        raise AssertionError(
            "VERIFY_ITEMS carries %d rows, contract is %d — the U20 item "
            "list drifted; refusing to ship a stale README."
            % (len(items), CONTRACT_ITEM_COUNT))
    seen_items = set()
    for row in items:
        num = row.get("item")
        if not isinstance(num, int) or num in seen_items:
            raise AssertionError(
                "VERIFY_ITEMS item numbers must be unique integers, got %r"
                % num)
        seen_items.add(num)
        for key in ("title", "asserts", "source", "fails"):
            if not isinstance(row.get(key), str) or not row[key]:
                raise AssertionError(
                    "VERIFY_ITEMS row %d lost its %r field — the item "
                    "contract is incomplete." % (num, key))
    if seen_items != set(range(1, CONTRACT_ITEM_COUNT + 1)):
        raise AssertionError(
            "VERIFY_ITEMS item numbers must be exactly 1..%d, got %s"
            % (CONTRACT_ITEM_COUNT, sorted(seen_items)))

    mods = MODULES
    if len(mods) != CONTRACT_MODULE_COUNT:
        raise AssertionError(
            "MODULES carries %d rows, contract is %d — a U20 module was "
            "added or removed without updating the inventory (and this "
            "self-test); refusing to ship a stale README."
            % (len(mods), CONTRACT_MODULE_COUNT))
    seen_names = set()
    for row in mods:
        name = row.get("name")
        if not isinstance(name, str) or not name or name in seen_names:
            raise AssertionError(
                "MODULES names must be unique non-empty strings, got %r"
                % name)
        seen_names.add(name)
        for key in ("place", "role", "offline", "exit_codes"):
            if not isinstance(row.get(key), str) or not row[key]:
                raise AssertionError(
                    "MODULES row %r lost its %r field." % (name, key))
        f = _module_file(row)
        if not f.is_file():
            raise AssertionError(
                "README inventory names %s, but that file does not ship at "
                "%s — documentation drifted from the tree (fail-closed: a "
                "doc that names a module that does not ship must never "
                "pass)." % (name, f))

    if set(EXIT_CODES) != {0, 1, 2, 3, 4, 5}:
        raise AssertionError(
            "EXIT_CODES must carry exactly 0..5 (house convention), got %s"
            % sorted(EXIT_CODES))
    for code in (0, 1, 2, 3, 4, 5):
        if not isinstance(EXIT_CODES[code], str) or not EXIT_CODES[code]:
            raise AssertionError("EXIT_CODES[%d] lost its meaning." % code)

    codes = [c for c, _, _ in AF_CODES]
    if len(codes) != len(set(codes)) or not codes:
        raise AssertionError("AF_CODES must carry unique, non-empty codes.")
    exits = {e for _, e, _ in AF_CODES}
    if not exits <= {0, 2, 4, 5}:
        raise AssertionError(
            "AF family must map only onto pass/STOP/self-test/mismatch "
            "exits (0/2/4/5), got %s" % sorted(exits))

    if not DOCTRINE or any(
            not isinstance(name, str) or not isinstance(text, str)
            or not name or not text for name, text in DOCTRINE):
        raise AssertionError("DOCTRINE must carry non-empty (name, text) rows.")

    if not CREDENTIAL_LABELS or not all(
            labels and all(isinstance(l, str) and l.isupper() and l
                           for l in labels)
            for labels in CREDENTIAL_LABELS.values()):
        raise AssertionError(
            "CREDENTIAL_LABELS must carry non-empty UPPERCASE label names "
            "only — a label is a name, never a value.")

    # The rendered README must cover the data it renders (a dropped section
    # is drift, never a silent omission).
    rendered = readme()
    for row in VERIFY_ITEMS:
        if row["title"] not in rendered:
            raise AssertionError(
                "readme() no longer renders item %d (%r) — the README "
                "drifted from VERIFY_ITEMS." % (row["item"], row["title"]))
    for row in MODULES:
        if row["name"] not in rendered:
            raise AssertionError(
                "readme() no longer renders module %r — the README drifted "
                "from MODULES." % row["name"])
    for code in sorted(EXIT_CODES):
        if str(code) + " —" not in rendered:
            raise AssertionError(
                "readme() no longer renders exit code %d." % code)
    dev.write("[docs-u20] PASS — README data and shipped tree agree "
              "(%d items, %d modules, exit 0..5, %d af codes).\n"
              % (len(items), len(mods), len(codes)))

def self_test(out=None) -> int:
    """The module's own OFFLINE self-test (no network, no credentials).
    Returns 0 on a clean pass, 4 on a detected drift — a stale README never
    masquerades as a pass."""
    import io
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        _self_test_body(dev)
    except AssertionError as exc:
        sys.stderr.write("[docs-u20] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family discipline, "
                         "enforced violation): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    return 0

# ---------------------------------------------------------------------------
# CLI — ONE JSON catalog object (default), the rendered README, or the
# offline self-test. Pure data; there is nothing secret here to leak.
# ---------------------------------------------------------------------------
EX_OK, EX_ERR = 0, 1

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="docs_u20.py",
        description="U20 tooling documentation module — README, module "
                    "inventory, seven verified items, exit codes, doctrine, "
                    "credential labels (pure data; nothing to leak).")
    parser.add_argument("cmd", nargs="?", choices=("catalog", "readme",
                                                   "self-test"),
                        default="catalog",
                        help="catalog (default): ONE JSON object; readme: "
                             "the rendered README text; self-test: offline "
                             "drift gate (0 clean, 4 drift)")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "self-test":
            return self_test()
        if args.cmd == "readme":
            sys.stdout.write(readme())
            return EX_OK
        print(json.dumps({
            "contract": DOC_CONTRACT,
            "schema_version": SCHEMA_VERSION,
            "ok": True,
            "verifier": U20_VERIFIER,
            "manifest_row": U20_MANIFEST_ROW,
            "shipping": U20_SHIPPING_VERSION,
            "verify_items": verify_items(),
            "modules": modules(),
            "exit_codes": exit_codes(),
            "af_codes": af_codes(),
            "doctrine": [{"name": n, "text": t} for n, t in DOCTRINE],
            "credential_labels": {k: list(v)
                                  for k, v in CREDENTIAL_LABELS.items()},
            "note": "pure data — no credential value is held or printed; "
                    "the U20 manifest row is PENDING (staged under the "
                    "manifest-pending/ pattern)",
        }, indent=2, sort_keys=True))
        return EX_OK
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[docs-u20] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR

if __name__ == "__main__":
    sys.exit(main())
