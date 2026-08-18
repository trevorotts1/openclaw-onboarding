#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u06_modules/docs_u06.py
# U06 TOOLING — THE MODULE DOCSTRING / README, SHIPPED AS AN IMPORTABLE MODULE
# (MASTER-SPEC U06; the u02_modules/docs_u02.py row-54-sibling pattern — the
# U06 family ships under the ENGINE-MANIFEST.json row-54 "template live
# verify (U02)" shipping doctrine, its OWN manifest row NOT yet stamped:
# PENDING, staged exactly under the manifest-pending/u02.json · u03.json ·
# u04.json · u05.json pattern; current skill-version 0.1.23, 2026-08-11).
# -----------------------------------------------------------------------------
# WHERE THIS SITS: scripts/u06_modules/ — the U06 tooling's documentation
# module, sibling of the archive-action law fixtures and the rail read it
# documents. It is NOT a manifest row: the U06 dispatcher
# scripts/u06_modules/main_skeleton.py stays the family's single driver
# under the delivery_report.py row-12 sibling-helper pattern, exactly as
# u02_modules/docs_u02.py documents the row-54 U02 verifier and
# u03_modules/docs_u03.py / u04_modules/docs_u04.py / u05_modules/docs_u05.py
# document their siblings (U06_MANIFEST_ROW = None, recorded below — a doc
# that claims a manifest row that does not exist is drift). Imported BY
# NAME as u06_modules.docs_u06 when a consumer wants the tooling's contract
# surfaces as DATA (module inventory, the five verified items, the house
# exit codes, the doctrine) or its rendered README as text.
#
# WHAT THIS OWNS:
#   1. THE README. The module docstring below IS the U06 tooling README:
#      what the tooling verifies, the module inventory, the exit-code
#      contract, the credential / browser-UA / fail-closed doctrine. The
#      same content is carried as STRUCTURED DATA (VERIFY_ITEMS, MODULES,
#      EXIT_CODES, AF_CODES, DOCTRINE, CREDENTIAL_LABELS) so a consumer can
#      diff against it instead of parsing prose — and readme() renders the
#      README FROM that data, so the two can never drift.
#   2. THE DRIFT GATE. self_test() proves the documentation still matches
#      the shipped tree: every module the README lists exists on disk next
#      to this module, all five items are present exactly once, every house
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
#      clients (InternalRailClient / CafClient) — the docs record that
#      doctrine, they do not re-implement it.
#
# THE TOOLING THIS DOCUMENTS (orientation):
#   MASTER-SPEC U06 — the ARCHIVE-ACTION LAW of the anthology engine, the
#   fail-closed package-init doctrine (u06_modules/__init__.py: "Destructive
#   actions fail closed: any archive ACTION (delete / archive / remove /
#   deactivate / revoke / unpublish) in this package requires the caller to
#   pass --execute explicitly (Trevor-gated). Without --execute the module
#   must report what it WOULD do and exit without mutating."). Five
#   verified items in a FIXED order:
#   1. THE FIND LAW — find_legacy.py finds the TWO legacy engine workflows
#      on a Convert and Flow location BY EXACT NAME ("00-Start Anthology
#      Writer with Avatar Alchemist" and "Anthology Pipeline Manager and
#      Notification System", dashes -> spaces, normalized lowercase) and
#      reports their ONE workflow id each — the id is the handle every
#      later archive / verify step binds to; the FIND half never archives;
#      a RENAMED legacy is indistinguishable from an ABSENT one and both
#      refuse fail-closed; near-misses are REPORTED (candidates), never
#      silently accepted; a pinned --workflow-id the listing does not carry
#      is a MISMATCH (exit 5), never a silent pass. The live rows are read
#      with ONE GET against the PROVEN internal rail
#      (backend.leadconnectorhq.com /workflow/<loc>/list?limit=200 — the
#      ONLY workflow surface this repo has PROVEN live, Skill 58; the
#      PUBLIC v2 has no proven workflows listing, so it is NOT used).
#   2. THE ARCHIVE GATE LAW — the archive ACTION (delete / archive /
#      remove / deactivate / revoke / unpublish of an archive target) is
#      Trevor-gated: WITHOUT the operator's explicit --execute it is a
#      REFUSAL (STOP, exit 2, AF-AE-U06-ARCHIVE-NO-EXECUTE), never a
#      silent no-op and never a mutation; an archive ACTION must ALSO name
#      its ONE byte-exact target (a nameless archive is a refusal,
#      AF-AE-U06-ARCHIVE-NO-NAME, never a sweep); a target name that
#      resolves to zero or to more than one workflow is a STOP
#      (AF-AE-U06-NAME-NOT-FOUND / AF-AE-U06-NAME-AMBIGUOUS). The gate is
#      enforced in BOTH surfaces (the dispatcher's CLI and its aggregate)
#      and pinned by the offline self-test — and the no-execute attack
#      fixture (attack_no_execute.py) ships the ONE-variable FAIL shape so
#      every pass/fail split discriminates the execute gate and never a
#      broken instrument (the negative-result contract: an attack fixture
#      that PASSES any archive gate is a broken gate).
#   3. THE PROVEN-WRITE LAW — even WITH --execute the archive step
#      performs NO mutation (AF-AE-U06-ARCHIVE-PLAN-ONLY is the CONTRACT,
#      not a failure): the internal rail's PROVEN surfaces are GET
#      /workflow/<loc>/list, GET /workflow/<loc>/<wid>, GET
#      /workflow/<loc>/trigger, and PUT /workflow/<loc>/trigger/<trg>
#      (scope_applier.py, U05) — NO workflow archive / delete surface has
#      been proven live anywhere in this repo (Skill 44 endpoint doctrine:
#      only proven endpoints), so the archive ACTION is a structured PLAN
#      that reports exactly what it WOULD archive and exits WITHOUT
#      writing; a module must never invent an archive surface and never
#      pretend a delete ran.
#   4. THE ABSENT-STATE LAW — an archive action has EXACTLY TWO targets:
#      the board footprint (the Assembly card + every participant card,
#      keyed by participant_key — the KEYING LAW,
#      anthology_state.participant_key, contact_id::anthology_id) and the
#      ledger rows (the anthology's status rows, deactivate-never-delete,
#      ninety-day retention — the revoke flow's R2 / R6 pair). BOTH absent
#      -> NOTHING to archive -> PASS exit 0 (golden_absent.py — the engine's
#      OWN precedent: the golden "R3 no shared Drive folders" no-op in
#      revoke-anthology-client.sh; nothing to do is a PASS, never an
#      error). The golden surface carries BOTH targets absent and the
#      dry-run report contract {"action": "archive", "applied": false,
#      "dry_run": true, "execute_required": true} every mutation surface
#      MUST emit without --execute; synthetic ids only, never a live id.
#   5. THE MASKING LAW — every operator surface reports workflow /
#      location / anthology ids by MASKED MARKER only (last 4 characters,
#      non-reversible); the full ids ride inside request URLs and the
#      machine-consumed JSON payloads only, never on an operator surface;
#      the full workflow id is a handle, never a credential.
#   The live read is RAIL-GATED (the location's workflow names through the
#   PROVEN internal rail, workflow_lister.py); an EMPTY workflow set is a
#   truthful PASS; a missing credential / unreachable rail / edge block /
#   unparseable listing is HELD (exit 3, never a fabricated list). The
#   offline gates (the find law, the archive gate law, the golden absent
#   state, the no-execute attack) are exercised with their OWN golden
#   surfaces and NEVER require a credential. The tooling ships NOW (the
#   u06 package-init doctrine; the U06 manifest row PENDING, staged under
#   the manifest-pending/u02.json · u03.json · u04.json · u05.json
#   pattern): the operator executes the live read only from a session that
#   can resolve a location-scoped credential BY LABEL. The laws are pinned
#   from the SINGLE AUTHORITIES — find_legacy.LEGACY_NAMES (the find law),
#   golden_absent (the archive LAW surface: the two targets, the dry-run
#   report contract, GOLDEN_EXECUTE_REQUIRED), anthology_state.
#   participant_key (the KEYING LAW), anthology_registry (the rail client
#   + CAF_BROWSER_UA) — never a second implementation; a drift in an
#   authority breaks the fixture's self-test FIRST (fail-closed: an
#   inconsistent law is a refusal, never a blind pass).
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE, everywhere in this tooling. The
# U06 fixtures hold NO credential surface at all (the golden absent state
# and the no-execute attack are pure in-memory metadata over SYNTHETIC ids
# — anth_golden / cnt_golden / wfLegacyStart01 / wfLegacyPipe02 — never a
# live id, never a live workflow, never a real participant, never a real
# token); the family's live surface (workflow_lister's rail read,
# find_legacy's rail read) resolves its credentials through the house
# labels (the internal rail: ANTHOLOGY_GHL_FIREBASE_REFRESH_TOKEN /
# GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN / GHL_FIREBASE_REFRESH_TOKEN + the
# Firebase API-key labels; the location id:
# CONVERT_AND_FLOW_LOCATION_ID / GOHIGHLEVEL_LOCATION_ID / GHL_LOCATION_ID;
# live process env first, then the three canonical client env stores; SET /
# NOT SET only — a token value is NEVER printed). Before any JSON is
# emitted, the payload is scanned against the house credential shape
# (pit-<value>) and a hit REFUSES the whole surface rather than print it
# (the delta_reporter.py never-a-real-token doctrine). The workflow /
# location ids are MASKED to their LAST 4 characters on every operator
# surface — never printed in full; a rail response body is never surfaced
# (it could echo a credential); classification reports HTTP code or error
# CLASS only.
#
# BROWSER UA (CF 1010 LAW): every request rides reg.InternalRailClient /
# reg.CafClient (and the internal-rail headers built by
# anthology_registry._internal_request_headers), which apply CAF_BROWSER_UA
# on EVERY request so the Cloudflare edge fronting
# backend.leadconnectorhq.com / services.leadconnectorhq.com never 1010s a
# verify request (CF error 1010; the W0.6 / GK-09 discipline — urllib's
# default "Python-urllib/x.y" is 403'd at the WAF edge before it ever
# reaches the API). The U06 fixtures make NO network call at all, so they
# define NO User-Agent constant of their own — the dispatcher's self-test
# PINS the exact constant on the outbound surface so a registry regression
# is caught HERE first. Scope-vs-edge-block discrimination: a bare 401/403
# is HELD (UpstreamBlockedError / CafUnreachable / InternalRailUnavailable),
# never mislabeled as a scope problem.
#
# FAIL-CLOSED (the whole point): a missing credential STOPS (exit 2), a
# no-execute archive ACTION STOPS (exit 2, AF-AE-U06-ARCHIVE-NO-EXECUTE —
# never a silent no-op), a nameless archive STOPS (AF-AE-U06-ARCHIVE-NO-NAME),
# a byte-exact name that resolves to zero or to more than one workflow
# STOPS (AF-AE-U06-NAME-NOT-FOUND / AF-AE-U06-NAME-AMBIGUOUS — an ACTION
# bound to the wrong record must be impossible), an unreadable listing / a
# missing legacy row / a pinned id the listing lacks is a FAIL or HELD
# (exit 5 / exit 3, never a fabricated pass, never an id guessed from
# memory), a transport / edge failure is HELD (exit 3, UNDETERMINED —
# never a verdict), the no-execute attack MUST FAIL every archive gate it
# touches (exit 2 / exit 5) while the golden execute-required control
# PASSES (a gate that fails everything is a broken check, not a real
# fault), and a drifted authority (golden_absent / find_legacy /
# anthology_state.participant_key / anthology_registry) breaks the
# fixture's self-tests FIRST (exit 4 — a tamper never masquerades as exit
# 1). A success is claimed ONLY when the find law agrees with its source
# of truth AND every archive step ran under its gate. Every deviation is
# NAMED with its code — never a bare "something failed".
#
# DOCTRINE (house, per anthology_registry.py / drive_adapter.py): move in
# silence (operator-verbose only); NOTHING Anthropic in any runtime file;
# Convert and Flow naming in every client surface; STDLIB ONLY; calls NO
# model; never a client PII; a law is read once, in one module (the
# delta_reporter.py single-implementation doctrine — find_legacy owns the
# find law, golden_absent owns the archive LAW surface, anthology_state
# owns the KEYING LAW, anthology_registry owns the rail client + the
# browser-UA constant, workflow_lister owns the live workflow read, and
# the fixtures derive from them, never re-implement). READ-ONLY by
# doctrine — the checkers never write; the archive ACTION is Trevor-gated
# (--execute) and a plan-only contract even with the gate (the dispatcher
# NEVER mutates — it carries no write surface). Self-test failures are
# exit 4 (enforced violation, the AF-AE-TEMPLATE-ATTACK / AF-AE-U06-* /
# AF-AE-ATTACKNOEXECUTE-* families) — a tamper never masquerades as exit 1.
#
# USAGE (this module's own machine surface — pure data, nothing to leak):
#   python3 docs_u06.py                ONE JSON catalog of the whole tooling
#   python3 docs_u06.py readme         the rendered README (markdown text)
#   python3 docs_u06.py self-test      OFFLINE drift gate over the docs vs
#                                      the shipped tree; 0 clean, 4 drift
# =============================================================================
"""docs_u06.py -- README / module docstring for the U06 tooling, as an
importable fail-closed pure-data module: the archive-action law family
(golden_absent / attack_no_execute / find_legacy / workflow_lister /
test_find_legacy / main_skeleton under the ENGINE-MANIFEST.json row-54
"template live verify (U02)" shipping doctrine — the family's OWN manifest
row PENDING), its five verified items, the u06_modules inventory, the
house exit codes, and the credential / browser-UA / doctrine contracts.
Performs no I/O at import and holds no credential; readme() is rendered
from the same structured data the self-test asserts against, so
documentation and data cannot drift."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# The fixed report contract (mirrors the golden-fixture naming discipline).
# ---------------------------------------------------------------------------
DOC_CONTRACT = "anthology-engine-u06-tooling-docs"
SCHEMA_VERSION = 1

# The U06 family's driver is its dispatcher under the U02 row-54 shipping
# law; the u06_modules/ siblings ship as non-manifest helpers (the
# delivery_report.py row-12 pattern, exactly the docs_u02.py / docs_u03.py /
# docs_u04.py / docs_u05.py siblings). The U06 family's OWN manifest row is
# NOT yet stamped in ENGINE-MANIFEST.json (verified at ship time,
# 2026-08-11): it is PENDING, staged under the manifest-pending/u02.json ·
# u03.json · u04.json · u05.json pattern — this module records None rather
# than invent a row number (a doc that claims a row that does not exist is
# drift).
U06_VERIFIER = "main_skeleton.py"
U06_MANIFEST_ROW = None  # PENDING — the family is not yet stamped
U06_SHIPPING_VERSION = "v0.1.23 (2026-08-11)"  # skill-version at ship time

# ---------------------------------------------------------------------------
# THE FIVE VERIFIED ITEMS (MASTER-SPEC U06 — the family's five gates, in
# the FIXED order the archive law carries them). Item numbers are
# load-bearing (positions 1..5, exactly five — self-test pins the count);
# the title is the README heading, asserts the fail-closed claim, sources
# the engine's source of truth, and fails the operator surface on drift.
# ---------------------------------------------------------------------------
VERIFY_ITEMS = (
    {
        "item": 1,
        "title": "Find law — the two legacy workflows found BY EXACT NAME",
        "asserts": ("the TWO legacy engine workflows a location can still "
                    "carry are found BY EXACT NAME — '00-Start Anthology "
                    "Writer with Avatar Alchemist' and 'Anthology Pipeline "
                    "Manager and Notification System', dashes -> spaces, "
                    "normalized lowercase, byte-exact against the module's "
                    "ONE pinned table (the find law, find_legacy.py) — "
                    "workflow-typed rows only, never a substring match, "
                    "never a similarity score; a RENAMED legacy is "
                    "indistinguishable from an ABSENT one and both refuse "
                    "fail-closed; near-miss rows are REPORTED as "
                    "candidates, never silently ignored; each legacy's ONE "
                    "workflow id is reported MASKED on every operator "
                    "surface and in full only inside the JSON payload a "
                    "machine consumer reads"),
        "source": "find_legacy.LEGACY_NAMES (the ONE pinned table) over "
                  "the internal rail GET /workflow/<loc>/list?limit=200 "
                  "(backend.leadconnectorhq.com — the ONLY workflow surface "
                  "this repo has PROVEN live, Skill 58); a pinned "
                  "--workflow-id must be present in the listing (a pin is "
                  "a stronger contract than a name)",
        "fails": "LEGACY-ABSENT / LEGACY-PARTIAL / LEGACY-EMPTY / "
                 "PIN-MISSING / PIN-ON-WRONG-NAME (exit 5); an unreadable "
                 "listing shape STOPS (exit 2); a bare 401/403 is HELD "
                 "(exit 3), never mislabeled as a find problem",
    },
    {
        "item": 2,
        "title": "Archive gate law — the ACTION is Trevor-gated (--execute)",
        "asserts": ("any archive ACTION (delete / archive / remove / "
                    "deactivate / revoke / unpublish — ANY mutation of an "
                    "archive target) REQUIRES the operator's explicit "
                    "--execute (the package-init doctrine); WITHOUT "
                    "--execute the action is a REFUSAL (STOP, exit 2, "
                    "AF-AE-U06-ARCHIVE-NO-EXECUTE), never a silent no-op "
                    "and never a mutation — the module reports what it "
                    "WOULD do (the action, the target ids by masked "
                    "marker, the write shape) and exits WITHOUT mutating; "
                    "the gate is enforced in BOTH surfaces (the CLI and "
                    "the aggregate) and pinned by the offline self-test"),
        "source": "u06_modules/__init__.py (the fail-closed archive "
                  "doctrine) + golden_absent.GOLDEN_EXECUTE_REQUIRED (the "
                  "archive LAW surface); the no-execute attack "
                  "(attack_no_execute.py) ships the ONE-variable FAIL "
                  "shape while the golden execute-required dry-run "
                  "control PASSES — the negative-result contract: an "
                  "attack fixture that PASSES any archive gate is a "
                  "broken gate",
        "fails": "AF-AE-U06-ARCHIVE-NO-EXECUTE (exit 2) / "
                 "AF-AE-ATTACKNOEXECUTE-* (exit 4); the attack record is "
                 "FAIL (exit 5, verify_archive) — never a blind pass",
    },
    {
        "item": 3,
        "title": "Proven-write law — WITH --execute the action is a plan only",
        "asserts": ("even WITH --execute the archive step performs NO "
                    "mutation (AF-AE-U06-ARCHIVE-PLAN-ONLY is the "
                    "CONTRACT, not a failure): the internal rail's PROVEN "
                    "surfaces are GET /workflow/<loc>/list, GET "
                    "/workflow/<loc>/<wid>, GET /workflow/<loc>/trigger "
                    "and PUT /workflow/<loc>/trigger/<trg> "
                    "(scope_applier.py, U05) — NO workflow archive / "
                    "delete surface has been proven live anywhere in this "
                    "repo (Skill 44 endpoint doctrine: only proven "
                    "endpoints), so the archive ACTION reports exactly "
                    "what it WOULD archive and exits WITHOUT writing; a "
                    "module never invents an archive surface and never "
                    "pretends a delete ran"),
        "source": "the endpoint doctrine of Skill 44 + the proven-surface "
                  "record of the U02/U05 tooling (workflow_lister "
                  "ARCHIVE_NOTE; find_legacy's proven-write law; "
                  "scope_applier's PUT /workflow/<loc>/trigger/<trg>)",
        "fails": "a plan that could be mistaken for an executed archive "
                 "is impossible (the plan reports execute explicitly and "
                 "carries the endpoint-doctrine note); a write surface "
                 "outside the proven set is a drift, caught HERE first "
                 "(exit 4)",
    },
    {
        "item": 4,
        "title": "Absent-state law — nothing to archive is a PASS, exit 0",
        "asserts": ("an archive action has EXACTLY TWO targets — the "
                    "board footprint (the Assembly card + every "
                    "participant card, keyed by participant_key — the "
                    "KEYING LAW, anthology_state.participant_key, "
                    "contact_id::anthology_id) and the ledger rows (the "
                    "anthology's status rows, deactivate-never-delete, "
                    "ninety-day retention — the revoke flow's R2 / R6 "
                    "pair); BOTH absent -> NOTHING to archive -> clean "
                    "no-op PASS exit 0 (the engine's OWN precedent: the "
                    "golden 'R3 no shared Drive folders' no-op in "
                    "revoke-anthology-client.sh); the golden absent-state "
                    "surface carries BOTH targets absent and the dry-run "
                    "report contract {'action': 'archive', 'applied': "
                    "false, 'dry_run': true, 'execute_required': true} "
                    "every mutation surface MUST emit without --execute"),
        "source": "golden_absent (the archive LAW surface) derived from "
                  "the revoke flow's archive surfaces — mc_board.py "
                  "cmd_archive (board cards, fail-soft, SPEC 11.2) and "
                  "anthology_state.py upsert-anthology --status archived "
                  "(ledger rows) — over SYNTHETIC ids only (anth_golden / "
                  "cnt_golden, never a live id)",
        "fails": "ANY deviation — a board card present, a ledger row "
                 "present, a malformed census, a missing target key, a "
                 "credential-shaped value — is REFUSED exit 5, never a "
                 "blind pass (golden_absent payload gate)",
    },
    {
        "item": 5,
        "title": "Masking law — ids by MASKED MARKER on operator surfaces",
        "asserts": ("every operator surface reports workflow / location / "
                    "anthology ids by MASKED MARKER only (last 4 "
                    "characters, non-reversible); the full ids ride inside "
                    "request URLs and the machine-consumed JSON payloads "
                    "only, never on an operator surface; the full workflow "
                    "id is a handle, never a credential — a surface that "
                    "echoes a full id (or a credential-shaped value) is a "
                    "REFUSAL, and the fixtures' payload gates scan every "
                    "report against the house credential shape "
                    "(pit-<value>) before it is emitted"),
        "source": "the house masking discipline (reg._mask_location / the "
                  "u06 last-4 marker shape) pinned by the fixtures' "
                  "self-tests (a full id on a captured surface is a "
                  "leak-scan FAIL); the delta_reporter.py "
                  "never-a-real-token doctrine",
        "fails": "the leak scan REFUSES the whole surface (exit 5) — a "
                 "full id or a pit-/Bearer-shaped string on any captured "
                 "surface is never shipped",
    },
)

# ---------------------------------------------------------------------------
# THE MODULE INVENTORY. `place` names the directory relative to this module
# (the u06_modules package itself); self-test proves each name exists at
# that place. `role` is the one-line contract each module owns; `offline`
# names the credential-free surface; `exit_codes` follows the house
# convention (0/1/2/3/5, 4 = self-test).
# ---------------------------------------------------------------------------
MODULES = (
    {
        "name": "__init__.py",
        "place": "scripts/u06_modules/",
        "manifest_row": None,
        "role": ("fail-closed EMPTY package init — pure namespace "
                 "container, no runtime code; modules are imported BY "
                 "NAME; records the package doctrine (fail-closed, secrets "
                 "by label, browser-UA law for every GoHighLevel / Convert "
                 "and Flow surface, the Trevor-gated archive ACTION, move "
                 "in silence)"),
        "offline": "trivially — it is empty",
        "exit_codes": "n/a (no executable surface)",
    },
    {
        "name": "find_legacy.py",
        "place": "scripts/u06_modules/",
        "manifest_row": None,
        "role": ("the LEGACY WORKFLOW FINDER — the U06 FIND half of "
                 "find-then-archive: FINDS the two legacy engine workflows "
                 "on a Convert and Flow location BY EXACT NAME "
                 "('00-Start Anthology Writer with Avatar Alchemist' and "
                 "'Anthology Pipeline Manager and Notification System') "
                 "and reports their ONE workflow id each; NEVER archives — "
                 "an archive ACTION is a separate Trevor-gated surface; a "
                 "RENAMED legacy is indistinguishable from an ABSENT one "
                 "and both refuse fail-closed; near-misses REPORTED as "
                 "candidates; --workflow-id PINS the id (a pin is a "
                 "stronger contract than a name; a pinned id absent from "
                 "the listing is a MISMATCH, exit 5); rides the PROVEN "
                 "internal rail (CAF_BROWSER_UA on every request)"),
        "offline": "plan + self-test (no token, no network); the live "
                   "find needs a location-scoped credential BY LABEL",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "workflow_lister.py",
        "place": "scripts/u06_modules/",
        "manifest_row": None,
        "role": ("the LIVE WORKFLOW LISTER — the read surface of the U06 "
                 "family: lists the workflow NAMES of a Convert and Flow "
                 "location through the PROVEN internal rail (GET "
                 "/workflow/<loc>/list?limit=200) and does NOTHING else; "
                 "an EMPTY workflow set is a truthful PASS (exit 0); its "
                 "ONE ACTION verb 'archive' is Trevor-gated (--execute "
                 "required — WITHOUT it a STOP, exit 2, never a silent "
                 "no-op) and a PLAN ONLY even WITH --execute (no "
                 "archive/delete surface proven live — endpoint "
                 "doctrine; the note rides the plan); a byte-exact name "
                 "that resolves to zero or to more than one workflow "
                 "REFUSES (an ACTION bound to the wrong record must be "
                 "impossible)"),
        "offline": "plan + self-test (no token, no network); the live "
                   "read needs the client's OWN Firebase refresh token BY "
                   "LABEL (SET / NOT SET only, never printed)",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "golden_absent.py",
        "place": "scripts/u06_modules/",
        "manifest_row": None,
        "role": ("the GOLDEN ABSENT-STATE ARCHIVE FIXTURE — the canonical "
                 "in-memory payload of the engine's ARCHIVE ACTION in its "
                 "ABSENT state: BOTH archive targets (the board footprint "
                 "and the ledger rows) are absent, so there is NOTHING to "
                 "archive and the action is a clean PASS exit 0 (the "
                 "engine's OWN no-op precedent, revoke R3); owns the "
                 "archive LAW surface — the two targets, the dry-run "
                 "report contract {'action': 'archive', 'applied': false, "
                 "'dry_run': true, 'execute_required': true} a mutation "
                 "surface MUST emit without --execute, and "
                 "GOLDEN_EXECUTE_REQUIRED; deep-frozen canonical record "
                 "(MappingProxyType) + fail-closed payload gate; "
                 "SYNTHETIC ids only, never a live id"),
        "offline": "entirely — pure data + builders (synthetic ids only)",
        "exit_codes": "0/1/4/5",
    },
    {
        "name": "attack_no_execute.py",
        "place": "scripts/u06_modules/",
        "manifest_row": None,
        "role": ("the U06 ATTACK: the archive ACTION requested WITHOUT "
                 "--execute (the Trevor gate) that MUST FAIL — the ONE "
                 "execute-gate flag of the canonical archive ACTION record "
                 "is dropped; every no-execute surface of the family MUST "
                 "refuse it (exit 2, AF-AE-U06-ARCHIVE-NO-EXECUTE), never "
                 "a silent no-op; verify_archive() exits 5 on the attack "
                 "naming the missing gate, the action, and the masked "
                 "target markers, and 0 on the golden execute-required "
                 "dry-run control; payload() ships EXACTLY the one-"
                 "no-execute shape and REFUSES any drift (exit 5); the "
                 "WITH-gate plan-only surface is the golden control — a "
                 "pass/fail split that discriminates the execute gate and "
                 "never a broken instrument"),
        "offline": "plan + self-test (no network, no token surface)",
        "exit_codes": "0/1/4/5",
    },
    {
        "name": "main_skeleton.py",
        "place": "scripts/u06_modules/",
        "manifest_row": None,
        "role": ("the U06 ARCHIVE-ACTION DISPATCHER — the family's single "
                 "driver: imports the check modules BY NAME (importlib, "
                 "never exec'd from a path), enforces the fail-closed "
                 "one-entry-point self_test contract, and resolves the "
                 "aggregate exit code exactly as its U02 / U03 / U04 / "
                 "U05 siblings; THE ARCHIVE ACTION IS TREVOR-GATED HERE — "
                 "verify refuses the archive step up front without "
                 "--execute (exit 2, AF-AE-U06-ARCHIVE-NO-EXECUTE) and a "
                 "nameless archive is a refusal (AF-AE-U06-ARCHIVE-NO-NAME), "
                 "never a sweep; carries NO write surface — it never "
                 "mutates"),
        "offline": "entirely — assembly + self-test battery aggregation, "
                   "no network, no credentials",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "test_find_legacy.py",
        "place": "scripts/u06_modules/",
        "manifest_row": None,
        "role": ("the INDEPENDENT PYTEST BATTERY of the legacy workflow "
                 "finder — offline contract tests over the exact-name law "
                 "(the two legacy names pinned in find_legacy.LEGACY_NAMES, "
                 "never re-typed in the file; case / spacing drift "
                 "resolves through the normalization law; a RENAMED legacy "
                 "is indistinguishable from an ABSENT one; alternative "
                 "container keys resolve the same law; non-dict rows are "
                 "skipped, never counted), the not-found paths each NAMED "
                 "(LEGACY-EMPTY / LEGACY-ABSENT / LEGACY-PARTIAL — no id "
                 "for the absent keys, never an id guessed from memory), "
                 "the pin law, the masking law (a full id on any captured "
                 "surface is a leak-scan FAIL), the archive-ACTION gate "
                 "(--execute required, Trevor-gated — the sibling "
                 "surfaces agree on the gate), and the sibling family "
                 "batteries green; network-free and credential-free"),
        "offline": "entirely — pytest battery, no network, no secrets",
        "exit_codes": "n/a (pytest battery; a failing run fails the "
                      "dispatcher self-test, exit 4)",
    },
    {
        "name": "docs_u06.py",
        "place": "scripts/u06_modules/",
        "manifest_row": None,
        "role": ("THIS MODULE — the U06 tooling README / catalog data + "
                 "drift gate: the module inventory, the five verified "
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
# the U06 family commits to; self-test pins all six.
# ---------------------------------------------------------------------------
EXIT_CODES = {
    0: "verified success — the find law agrees with its source of truth "
       "and every archive step ran under its gate (also plan / dry-run / "
       "self-test; an EMPTY workflow set is a truthful PASS; nothing to "
       "archive is a clean no-op PASS)",
    1: "unexpected error (top-level guard; never a secret leak)",
    2: ("STOP refusal — the archive ACTION without --execute (the Trevor "
        "gate, AF-AE-U06-ARCHIVE-NO-EXECUTE) or without its byte-exact "
        "target name (AF-AE-U06-ARCHIVE-NO-NAME) / label NOT SET / usage / "
        "the U06 check-module assembly incomplete (AF-AE-U06-ASSEMBLY-"
        "INCOMPLETE) / a name that resolves to no workflow "
        "(AF-AE-U06-NAME-NOT-FOUND) or to more than one "
        "(AF-AE-U06-NAME-AMBIGUOUS) / a contract that cannot be read / a "
        "module STOP-family refusal"),
    3: ("HELD — the internal rail unreachable / Cloudflare edge block "
        "(CF error 1010) / Firebase exchange failure / a malformed "
        "listing (UNDETERMINED, never a verdict — a bare 401/403 is HELD, "
        "never mislabeled as a find or scope problem)"),
    4: ("self-test FAILED (AF-AE-TEMPLATE-ATTACK / AF-AE-U06-* / "
        "AF-AE-ATTACKNOEXECUTE-* family, enforced violation) — a tamper "
        "never masquerades as exit 1"),
    5: ("mismatch / fail-closed default — a legacy absent or partially "
        "present (LEGACY-ABSENT / LEGACY-PARTIAL / LEGACY-EMPTY), a "
        "pinned id absent from the listing (PIN-MISSING / "
        "PIN-ON-WRONG-NAME), a no-execute attack record judged clean "
        "(verify_archive FAIL), a drifted absent-state payload, a "
        "credential-shaped or full-id surface (leak-scan REFUSAL), a "
        "read-back mismatch, or a DEFERRED live read without "
        "--allow-deferred"),
}

# ---------------------------------------------------------------------------
# THE AF AUTOfail FAMILY of the U06 tooling — the codes the family's own
# surfaces declare. The U06-specific codes are NOT yet stamped in
# ENGINE-MANIFEST.json (the family is PENDING — verified at ship time,
# 2026-08-11); AF-AE-TEMPLATE-ATTACK and the shared AF-AE-READBACK-MISMATCH
# codes already live in the manifest. Self-test failures are exit 4, never
# 1.
# ---------------------------------------------------------------------------
AF_CODES = (
    ("AF-AE-U06-ASSEMBLY-INCOMPLETE", 2,
     "the U06 check-module set named in U06_MODULES is not fully present, "
     "or a module violates the one-entry-point self_test contract — a "
     "check family is never silently skipped (dispatcher STOP)"),
    ("AF-AE-U06-ARCHIVE-NO-EXECUTE", 2,
     "the archive ACTION was requested without --execute (the Trevor "
     "gate) — an ACTION without the gate is a refusal, never a silent "
     "no-op"),
    ("AF-AE-U06-ARCHIVE-NO-NAME", 2,
     "the archive ACTION was requested without its byte-exact target "
     "workflow name — a nameless archive is a refusal, never a sweep"),
    ("AF-AE-U06-ARCHIVE-PLAN-ONLY", 0,
     "WITH --execute the archive step still performs NO mutation "
     "(endpoint doctrine — no archive/delete surface proven live): it "
     "reports the plan and exits without writing. Plan-only is the "
     "CONTRACT, not a failure"),
    ("AF-AE-U06-NAME-NOT-FOUND", 2,
     "a byte-exact workflow name resolves to no workflow on the live "
     "listing (module STOP)"),
    ("AF-AE-U06-NAME-AMBIGUOUS", 2,
     "a workflow name is duplicated on the live listing — the bind is "
     "ambiguous and MUST refuse (module STOP)"),
    ("AF-AE-U06-LEGACY-ABSENT", 5,
     "a non-empty listing carries neither legacy workflow — the find law "
     "refuses, never an id guessed from memory (find_legacy)"),
    ("AF-AE-U06-LEGACY-PARTIAL", 5,
     "one legacy workflow is found and the other is absent — a partial "
     "result, surfaced with the found id and the absent name, never a "
     "silent half-pass (find_legacy)"),
    ("AF-AE-U06-LEGACY-EMPTY", 5,
     "the live listing is empty — there is nothing to find, and the "
     "not-found surface carries NO id (find_legacy)"),
    ("AF-AE-U06-PIN-MISSING", 5,
     "a pinned --workflow-id is absent from the live listing — a pin is "
     "a stronger contract than a name, and a mismatch is never a silent "
     "pass (find_legacy)"),
    ("AF-AE-U06-PIN-ON-WRONG-NAME", 5,
     "a pinned id resolves to a row under a DIFFERENT legacy name — a pin "
     "can never point the archive at the wrong legacy (find_legacy)"),
    ("AF-AE-ATTACKNOEXECUTE-*", 4,
     "an attack tripped the no-execute attack fixture's OFFLINE self-test "
     "(enforced violation) — the no-execute attack passed a gate, or a "
     "drifted authority (golden_absent / find_legacy) was not caught HERE "
     "first"),
    ("AF-AE-READBACK-MISMATCH", 5,
     "a post-write read-back does not prove the fix byte-for-byte — the "
     "shared house code with the U02 / U03 / U04 / U05 families (already "
     "stamped in ENGINE-MANIFEST.json)"),
    ("AF-AE-TEMPLATE-ATTACK", 4,
     "an attack fixture tripped the OFFLINE self-test of the dispatcher "
     "or a family battery (enforced violation — the house code, shared "
     "with the U02 / U03 / U04 / U05 families)"),
)

# ---------------------------------------------------------------------------
# DOCTRINE — the house rules the whole U06 tooling commits to, as data so
# the README renders them from the same source the self-test asserts.
# ---------------------------------------------------------------------------
DOCTRINE = (
    ("Fail-closed", "a missing credential, a malformed input, an "
     "unreadable source, or a live read that cannot be completed is a "
     "REFUSAL or a recorded FAIL — never a blind pass, never a fabricated "
     "success; a no-execute archive ACTION is a STOP (exit 2), never a "
     "silent no-op; a strict subset is a MISSING, never a pass; a legacy "
     "row absent from the listing is a FAIL, never a silent empty; an id "
     "is NEVER guessed from memory"),
    ("Secrets", "credentials resolve BY LABEL only (SET / NOT SET); a "
     "token value is never printed, echoed, or reflected in any surface; "
     "before any JSON is emitted the payload is scanned against the house "
     "credential shape (pit-<value>) and a hit REFUSES the whole surface "
     "(the delta_reporter.py never-a-real-token doctrine); the workflow / "
     "location / anthology ids are MASKED to their last 4 characters on "
     "every operator surface — the full workflow id is a handle, never a "
     "credential; a rail response body is never surfaced (it could echo a "
     "credential)"),
    ("Browser UA", "every request to GoHighLevel / Convert and Flow "
     "(services.leadconnectorhq.com) and the internal rail "
     "(backend.leadconnectorhq.com) rides CAF_BROWSER_UA (reg.CafClient / "
     "reg.InternalRailClient) — urllib's default 'Python-urllib/x.y' is "
     "403'd at the WAF edge (CF error 1010) before it ever reaches the "
     "API (W0.6 / GK-09); the U06 fixtures make NO network call, so they "
     "define NO User-Agent constant of their own — the dispatcher's "
     "self-test PINS the exact constant on the outbound surface so a "
     "registry regression is caught HERE first"),
    ("Scope vs edge", "a bare 401/403 is HELD (UpstreamBlockedError / "
     "CafUnreachable / InternalRailUnavailable), never mislabeled as a "
     "find or scope problem — UNDETERMINED is a correct answer, never a "
     "verdict"),
    ("Synthetic ids only", "the fixtures carry SYNTHETIC deterministic "
     "ids only (anth_golden / cnt_golden / wfLegacyStart01 / "
     "wfLegacyPipe02 — the synthetic-id discipline of the u02/u03/u04/u05 "
     "golden siblings) — a fixture id is never a live id, never a live "
     "workflow, never a real participant, and never a real token"),
    ("Single authority", "a law is read once, in one module: "
     "find_legacy.LEGACY_NAMES owns the find law, golden_absent owns the "
     "archive LAW surface (the two targets, the dry-run report contract, "
     "GOLDEN_EXECUTE_REQUIRED), anthology_state.participant_key owns the "
     "KEYING LAW, anthology_registry owns the rail client + the "
     "browser-UA constant, workflow_lister owns the live workflow read — "
     "the fixtures derive from them, never re-implement; a drift in an "
     "authority breaks the fixture's self-test FIRST"),
    ("Negative-result contract", "the no-execute attack fixture carries "
     "its OWN golden control (the execute-required dry-run report "
     "PASSES), so every pass/fail split discriminates the execute gate "
     "and never a broken instrument — a gate that fails everything is a "
     "broken check, not a real fault; an attack fixture that PASSES any "
     "archive gate is a broken gate; a negative is a claim and carries "
     "the same burden of proof as a positive one"),
    ("Gated writes", "--execute is the ONLY flag that performs an "
     "archive ACTION (Trevor-gated), and even WITH --execute the action "
     "is a PLAN ONLY (AF-AE-U06-ARCHIVE-PLAN-ONLY is the CONTRACT, not a "
     "failure): no archive/delete surface for workflows has been proven "
     "live anywhere in this repo (Skill 44 endpoint doctrine — only "
     "proven endpoints), so the archive step reports exactly what it "
     "WOULD archive and exits WITHOUT mutating; the dispatcher NEVER "
     "mutates — it carries no write surface"),
    ("Move in silence", "operator-verbose only; NOTHING Anthropic in any "
     "runtime file; Convert and Flow naming in every client surface; "
     "STDLIB ONLY; calls NO model; never a client PII; READ-ONLY by "
     "doctrine — the checkers never write; the archive ACTION is the ONE "
     "gated surface"),
)

# ---------------------------------------------------------------------------
# CREDENTIAL LABELS — BY LABEL ONLY. These are the label NAMES the tooling
# resolves through anthology_registry (live process env first, then the
# three canonical client env stores). A label is a name, never a value; the
# values they resolve to are never held here and never printed anywhere.
# The U06 fixtures hold NO credential surface at all (pure in-memory
# metadata over synthetic ids); the family's live surface — the
# workflow_lister / find_legacy rail reads — resolves its credentials
# through the house labels below.
# ---------------------------------------------------------------------------
CREDENTIAL_LABELS = {
    "rail": (
        "ANTHOLOGY_GHL_FIREBASE_REFRESH_TOKEN",
        "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN",
        "GHL_FIREBASE_REFRESH_TOKEN",
    ),
    "location": (
        "CONVERT_AND_FLOW_LOCATION_ID",
        "GOHIGHLEVEL_LOCATION_ID",
        "GHL_LOCATION_ID",
    ),
}

# Pinned counts (the fixture-counting discipline of golden_fields.py: a
# drifted inventory is drift, never tolerated). Adding a module to the U06
# tooling REQUIRES adding it here AND to the README's inventory.
CONTRACT_ITEM_COUNT = 5
CONTRACT_MODULE_COUNT = 8

class DocsError(Exception):
    """A fail-closed documentation refusal: the README data drifted from
    its own contract, so no catalog is shipped — wrong docs are worse than
    no docs."""

# ---------------------------------------------------------------------------
# Accessors — deep copies, so callers can never mutate the canonical data.
# ---------------------------------------------------------------------------
def verify_items() -> list:
    """The five verified items as a mutable deep copy (callers may mutate
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
    """The U06 tooling README, rendered from the structured data above.

    One markdown document: what the tooling is, the five verified items,
    the module inventory, the house exit codes, the autofail family, the
    doctrine, and the credential labels. Because every section renders from
    the same constants the self-test asserts, a drift in the data FAILS the
    self-test before it can ship a stale README."""
    lines = [
        "# U06 tooling — archive-action law gates (README)",
        "",
        "Shipped under the ENGINE-MANIFEST.json row-54 \"template live "
        "verify (U02)\" shipping doctrine (%s; the U06 family's OWN manifest "
        "row is PENDING — not yet stamped, staged under the "
        "manifest-pending/u02.json · u03.json · u04.json · u05.json "
        "pattern) — dispatched by `scripts/u06_modules/main_skeleton.py` "
        "plus the importable archive-law fixtures, the legacy finder, the "
        "live workflow lister, and the independent pytest battery in "
        "`scripts/u06_modules/` — documented machine-side by "
        "this module (`u06_modules.docs_u06`)."
        % U06_SHIPPING_VERSION,
        "",
        "The U06 family gates the ARCHIVE-ACTION LAW of the anthology "
        "engine (the package-init doctrine): any archive ACTION (delete / "
        "archive / remove / deactivate / revoke / unpublish — ANY mutation "
        "of an archive target) requires the operator's explicit --execute "
        "(Trevor-gated), and even WITH --execute the archive step performs "
        "NO mutation (no archive/delete surface for workflows has been "
        "proven live — Skill 44 endpoint doctrine: only proven endpoints; "
        "plan-only is the CONTRACT). The family's live surface is the "
        "workflow-list read through the PROVEN internal rail — it runs "
        "only from a session that can resolve a location-scoped credential "
        "BY LABEL (the internal-rail Firebase refresh token + API key; the "
        "location id); the find law, the archive gate law, the golden "
        "absent state, and the no-execute attack are OFFLINE (no token, no "
        "network). The fixtures carry SYNTHETIC ids only (anth_golden / "
        "cnt_golden / wfLegacyStart01 / wfLegacyPipe02 — never a live id, "
        "never a live workflow); every report masks workflow / location / "
        "anthology ids to their last 4 characters and never echoes a "
        "credential-shaped value.",
        "",
        "## The five verified items (MASTER-SPEC U06 — the family's five "
        "gates, in the FIXED order the archive law carries them)",
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
    """The on-disk path a README inventory row claims. Every U06 row lives
    next to this module (scripts/u06_modules/)."""
    base = Path(__file__).resolve().parent
    if row.get("place", "").strip("/") == "scripts":
        base = base.parent
    return base / row["name"]

def _self_test_body(dev) -> None:
    dev.write("[docs-u06] pinning: %d verified items, %d modules, "
              "exit codes 0..5\n"
              % (CONTRACT_ITEM_COUNT, CONTRACT_MODULE_COUNT))

    items = VERIFY_ITEMS
    if len(items) != CONTRACT_ITEM_COUNT:
        raise AssertionError(
            "VERIFY_ITEMS carries %d rows, contract is %d — the U06 item "
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
            "MODULES carries %d rows, contract is %d — a U06 module was "
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
    dev.write("[docs-u06] PASS — README data and shipped tree agree "
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
        sys.stderr.write("[docs-u06] SELF-TEST FAILED "
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
        prog="docs_u06.py",
        description="U06 tooling documentation module — README, module "
                    "inventory, five verified items, exit codes, doctrine, "
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
            "verifier": U06_VERIFIER,
            "manifest_row": U06_MANIFEST_ROW,
            "shipping": U06_SHIPPING_VERSION,
            "verify_items": verify_items(),
            "modules": modules(),
            "exit_codes": exit_codes(),
            "af_codes": af_codes(),
            "doctrine": [{"name": n, "text": t} for n, t in DOCTRINE],
            "credential_labels": {k: list(v)
                                  for k, v in CREDENTIAL_LABELS.items()},
            "note": "pure data — no credential value is held or printed; "
                    "the U06 manifest row is PENDING",
        }, indent=2, sort_keys=True))
        return EX_OK
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[docs-u06] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR

if __name__ == "__main__":
    sys.exit(main())
