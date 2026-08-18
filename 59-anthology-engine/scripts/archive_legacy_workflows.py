#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: archive_legacy_workflows.py  (U06 tooling)
# LEGACY-WORKFLOW ARCHIVE DISPATCHER — the ONE CLI ASSEMBLED from the
# u06_modules files: it imports EVERY module under scripts/u06_modules/ BY
# NAME (importlib, never exec'd from a path) and wires them into ONE CLI
# whose offline self-test battery (golden found / golden absent PASS, the
# no-execute attack REFUSED) runs before any live surface. This file carries
# NO check logic itself — a check family is exercised ONLY through its module
# so `--dry-run`, `--self-test`, and the live aggregate never drift apart. It
# is the packaged sibling of scripts/live_verify_template.py (U02, row 54),
# scripts/check_pipeline_name.py (U03, row 55), scripts/fix_intake_form.py
# (U04, row 56) and scripts/check_intake_fire_scope.py (U05, row 57) under
# the ENGINE-MANIFEST row-54 shipping doctrine; its OWN manifest row is
# staged manifest-pending/u06.json (PENDING — the U06 manifest row is
# stamped by this assembly, exactly as the U05 row was stamped by
# check_intake_fire_scope.py).
#
# THE u06_modules FILES (imported by name; each is STDLIB-only and
# self-tests itself — docs_u06.py carries the module inventory as data and
# its self-test proves the tree ships together). The family's FIXED roster:
#   __init__.py            fail-closed EMPTY package init (pure namespace)
#   main_skeleton.py       the U06 archive-action dispatcher CLI (plan /
#                          self-test / live verify; the ONE entry-point
#                          contract over the check modules)
#   find_legacy.py         the legacy-find law authority + the live read of
#                          the TWO legacy Anthology workflows BY EXACT NAME
#                          on the PROVEN internal rail (LEGACY_NAMES — the
#                          U06 archive targets; read-only, NEVER archives)
#   workflow_lister.py     the live read surface of the U06 family — the
#                          workflow NAMES of a Convert and Flow location
#                          through the PROVEN internal rail (GET
#                          /workflow/{loc}/list?limit=200); its ONE ACTION
#                          verb 'archive' is Trevor-gated (--execute) and a
#                          plan only — no mutation, endpoint doctrine
#   golden_absent.py       the archive LAW authority + the golden ABSENT-
#                          state fixture: both archive targets (board /
#                          ledger — the revoke flow's R2 / R6 pair) EMPTY
#                          -> PASS (nothing to archive); the archive ACTION
#                          is --execute-gated (GOLDEN_EXECUTE_REQUIRED)
#   golden_found.py        the GOLDEN FOUND-state fixture — the canonical
#                          in-memory payload of the U06 FIND half in its
#                          FOUND state: BOTH contract workflows the archive
#                          action touches on the listing byte-exact by the
#                          golden keys (read once from
#                          find_legacy.LEGACY_NAMES), each with its one
#                          synthetic id; READ-ONLY by construction
#   attack_no_execute.py   the U06 ATTACK: the archive ACTION requested
#                          WITHOUT --execute (the Trevor gate) — the
#                          canonical no-execute record that every archive
#                          authority MUST refuse (verify_archive exit 5),
#                          with the golden execute-required dry-run control
#                          PASSING (payload_true) — the pass/fail split
#                          discriminates the missing-gate boundary
#   verify_archived.py     the ARCHIVED-STATE VERIFIER — the read-back half
#                          of the U06 archive law: re-reads the engine's
#                          TWO archive targets (board / ledger) after the
#                          archive sweep and confirms the archived status
#                          BYTE-EXACT; its check ACTION is Trevor-gated
#                          (--execute) and READ-ONLY
#   house_rules.py         the ONE canonical house-law constant surface
#                          (browser UA / version header / the AF autofail
#                          table mirrored from docs_u06.AF_CODES plus the
#                          shared rows pinned against ENGINE-MANIFEST.json)
#   example_usage.py       the fail-closed WORKED EXAMPLE of the U06
#                          dispatch (the FIND law + the golden found-state +
#                          the golden absent-state + the no-execute attack
#                          + the lister's archive ACTION)
#   test_find_legacy.py    the independent pytest battery over the find law
#                          (provenance only)
#   test_verify_archived.py  the independent pytest battery over the
#                          archived-state verifier (provenance only)
#   docs_u06.py            the U06 tooling README/catalog data + drift gate
#                          (the module inventory as DATA)
# (the assembly manifests — main_skeleton.U06_MODULES and docs_u06.MODULES —
# carry this exact roster; the self-test pins the tree ships together.)
#
# THE U06 ATTACK (the offline self-test proves it is REFUSED — golden PASS /
# attack FAIL; a tamper NEVER masquerades as exit 1):
#   attack_no_execute — the archive ACTION invoked WITHOUT --execute (the
#                       Trevor gate) must FAIL every archive authority
#                       (verify_archive exit 5, the AF-AE-ATTACKNOEXECUTE-*
#                       family) while the golden execute-required dry-run
#                       control PASSES exit 0 (payload_true) — the pass/fail
#                       split discriminates the missing-gate boundary,
#                       never a broken instrument.
#
# WHAT THIS VERIFIES (MASTER-SPEC U06 — the ARCHIVE-ACTION LAW of the
# anthology engine, the fail-closed package-init doctrine: "Destructive
# actions fail closed: any archive ACTION (delete / archive / remove /
# deactivate / revoke / unpublish) in this package requires the caller to
# pass --execute explicitly (Trevor-gated). Without --execute the module
# must report what it WOULD do and exit without mutating."). The
# dispatcher's live gates run in the FIXED order main_skeleton.LIVE_GATES
# carries them; the per-item claims live in the modules and in
# docs_u06.VERIFY_ITEMS:
#   1. THE FIND LAW — the TWO legacy engine workflows are found BY EXACT
#      NAME on the location's live internal-rail listing
#      (find_legacy.find_legacies: '00-Start Anthology Writer with Avatar
#      Alchemist' + 'Anthology Pipeline Manager and Notification System',
#      dashes -> spaces, normalized lowercase; a RENAMED legacy is
#      indistinguishable from an ABSENT one and both refuse fail-closed;
#      near-misses REPORTED as candidates; a pinned --workflow-id absent
#      from the listing is a MISMATCH — LEGACY-FOUND / -ABSENT / -PARTIAL /
#      -EMPTY / PIN-* exits 5 or 2, never a silent pass).
#   2. THE ARCHIVE GATE LAW — the archive ACTION is Trevor-gated: WITHOUT
#      the operator's explicit --execute it is a REFUSAL (STOP, exit 2,
#      AF-AE-U06-ARCHIVE-NO-EXECUTE), never a silent no-op and never a
#      mutation; an archive ACTION must ALSO name its ONE byte-exact target
#      (AF-AE-U06-ARCHIVE-NO-NAME, exit 2); a target name that resolves to
#      zero or more than one workflow STOPS (AF-AE-U06-NAME-NOT-FOUND /
#      AF-AE-U06-NAME-AMBIGUOUS). The gate is enforced in BOTH surfaces
#      (this assembler's CLI and the aggregate) and pinned by the offline
#      self-test.
#   3. THE PROVEN-WRITE LAW — even WITH --execute the archive step performs
#      NO mutation (AF-AE-U06-ARCHIVE-PLAN-ONLY is the CONTRACT, not a
#      failure): the internal rail's PROVEN surfaces are GET
#      /workflow/<loc>/list, GET /workflow/<loc>/<wid>, GET
#      /workflow/<loc>/trigger and PUT /workflow/<loc>/trigger/<trg>
#      (scope_applier.py, U05) — NO workflow archive / delete surface has
#      been proven live anywhere in this repo (Skill 44 endpoint doctrine:
#      only proven endpoints), so the archive ACTION reports exactly what
#      it WOULD archive and exits WITHOUT writing.
#   4. THE ABSENT-STATE LAW — an archive action has EXACTLY TWO targets:
#      the board footprint and the ledger rows (the revoke flow's R2 / R6
#      pair). BOTH absent -> NOTHING to archive -> PASS exit 0
#      (golden_absent.py — the engine's OWN no-op precedent, revoke R3).
#   5. THE MASKING LAW — every operator surface reports workflow / location
#      / anthology ids by MASKED MARKER only (last-4, non-reversible); the
#      full ids ride inside request URLs and the machine-consumed JSON
#      payloads only, never on an operator surface.
#   PLUS (assembled surface, exercised through the modules' own surfaces):
#   6. THE ARCHIVED-STATE READ-BACK (verify_archived — the engine's own
#      local ledger mirror + board projection, NO rail credential; its
#      check ACTION is Trevor-gated and READ-ONLY; a drift is a MISMATCH,
#      an unreadable mirror is HELD).
#   7. THE HOUSE-LAW CONSTANT SURFACE (house_rules — browser UA / version
#      header / AF autofail table as immutable constants, byte-pinned).
#   8. THE WORKED EXAMPLE (example_usage — the composition runs the SAME
#      law; its self-test pins the step order).
#
# THE ARCHIVE ACTION IS TREVOR-GATED HERE. The dispatcher NEVER archives
# without --execute: the CLI's `archive` subcommand refuses up front (exit
# 2, AF-AE-U06-ARCHIVE-NO-EXECUTE) unless --execute was passed explicitly,
# and even then the archive is a PLAN ONLY (endpoint doctrine — no
# mutation). The no-execute attack is proven REFUSED by the offline
# self-test (attack_no_execute.verify_archive on the canonical attack
# record -> exit 5; the golden execute-required control -> exit 0). The
# assembler itself carries NO write surface.
#
# THE ONE LIVE READ IS RAIL-GATED; THE TOOLING SHIPS NOW (manifest row
# doctrine). The operator executes `verify` only from a session that can
# resolve a location-scoped credential BY LABEL — the internal-rail
# Firebase refresh token (the proven workflow surface) with the Firebase
# API key. --dry-run (offline plan) and --self-test (offline, no token, no
# network) always work. The offline gates (the golden both-workflows
# fixture, the golden absent-state census, the archive gate law, the
# no-execute attack) are exercised with their own golden surfaces and
# NEVER require a credential.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. The rail refresh token + API key
# are resolved through anthology_registry (FIREBASE_REFRESH_LABELS /
# FIREBASE_API_KEY_LABELS, live process env first then the three canonical
# client env stores) and the location id through reg.resolve_location
# (CONVERT_AND_FLOW_LOCATION_ID / GOHIGHLEVEL_LOCATION_ID / GHL_LOCATION_ID)
# unless --location-id overrides. SET / NOT SET only on every operator
# surface; a token value is NEVER printed, and the location / workflow ids
# are masked on every surface.
#
# BROWSER UA: every request rides reg.InternalRailClient /
# reg._internal_request_headers, which apply CAF_BROWSER_UA on every
# request so the Cloudflare edge fronting backend.leadconnectorhq.com never
# 1010s a verify request (CF 1010 / GK-09 discipline — the house pattern
# ported byte-for-byte from the U02 / U03 / U04 / U05 families). Scope-vs-
# edge-block discrimination: a bare 401/403 is HELD (UpstreamBlockedError /
# InternalRailUnavailable), never mislabeled as a scope problem.
#
# AF CODES (fail-closed surfaces; self-test failures are exit 4, never 1;
# the family is staged under manifest-pending/u06.json, its OWN manifest
# row stamped by this assembly):
#   AF-AE-U06-ASSEMBLY-INCOMPLETE -> the U06 check-module set named in the
#          assembly roster is not fully present, or a module violates the
#          one-entry-point self_test contract. STOP (exit 2) — a check
#          family is never silently skipped.
#   AF-AE-U06-ARCHIVE-NO-EXECUTE  -> the archive ACTION was requested
#          without --execute (the Trevor gate). STOP (exit 2) — an ACTION
#          without the gate is a refusal, never a silent no-op.
#   AF-AE-U06-ARCHIVE-NO-NAME     -> the archive ACTION was requested
#          without its byte-exact target workflow name. STOP (exit 2) — a
#          nameless archive is a refusal, never a sweep.
#   AF-AE-U06-ARCHIVE-PLAN-ONLY   -> WITH --execute the archive step still
#          performs NO mutation (endpoint doctrine — no archive/delete
#          surface proven live): it reports the plan and exits without
#          writing. Plan-only is the CONTRACT, not a failure.
#   AF-AE-U06-NAME-NOT-FOUND      -> a byte-exact workflow name resolves to
#          no workflow on the live listing. exit 2 (module STOP).
#   AF-AE-U06-NAME-AMBIGUOUS      -> a workflow name is duplicated on the
#          live listing — the bind is ambiguous and MUST refuse. exit 2.
#   AF-AE-U06-LEGACY-*            -> the find-law mismatch family
#          (LEGACY-ABSENT / LEGACY-PARTIAL / LEGACY-EMPTY / PIN-MISSING /
#          PIN-ON-WRONG-NAME). exit 5.
#   AF-AE-ATTACKNOEXECUTE-*       -> an attack tripped the no-execute
#          attack fixture's OFFLINE self-test (enforced violation). exit 4.
#   AF-AE-READBACK-MISMATCH       -> a post-write read-back does not prove
#          the fix byte-for-byte (shared house code). exit 5.
#   AF-AE-TEMPLATE-ATTACK         -> an attack fixture tripped the OFFLINE
#          self-test (also the family self-test batteries). exit 4.
#
# EXIT CODES (house convention 0/1/2/3/5; 4 = enforced violation; the
# primary surface the operator consumes is 0 = PASS, 2 = STOP, 5 = mismatch):
#   0  all checks PASS (also --dry-run plan pass and self-test pass; an
#      EMPTY workflow set is a truthful PASS; nothing to archive is a
#      clean no-op PASS)
#   1  unexpected error
#   2  STOP refusal — the archive ACTION without --execute (the Trevor
#      gate, AF-AE-U06-ARCHIVE-NO-EXECUTE) or without its byte-exact target
#      name (AF-AE-U06-ARCHIVE-NO-NAME) / label NOT SET / usage / the
#      U06 check-module assembly incomplete (AF-AE-U06-ASSEMBLY-INCOMPLETE)
#      / a contract that cannot be read / a name that resolves to no
#      workflow (AF-AE-U06-NAME-NOT-FOUND) or to more than one
#      (AF-AE-U06-NAME-AMBIGUOUS) / a module STOP-family refusal
#   3  HELD — the internal rail unreachable / Cloudflare edge block /
#      Firebase exchange failure / a malformed listing (UNDETERMINED,
#      never a verdict)
#   4  self-test FAILED — an assertion in the OFFLINE self-test tripped
#      (AF-AE-TEMPLATE-ATTACK / AF-AE-U06-* / AF-AE-ATTACKNOEXECUTE-*
#      family). A tamper NEVER masquerades as exit 1.
#   5  data or read-back mismatch (a legacy absent or partially present /
#      a pinned id absent from the listing / the no-execute attack judged
#      clean / a drifted absent-state payload / a credential-shaped or
#      full-id surface / a read-back mismatch / a DEFERRED live read
#      without --allow-deferred; the fail-closed default)
#
# MANIFEST-PENDING: after a PASSING run the tool writes
# manifest-pending/u06.json — the staged U06 manifest artifact (contract,
# checks verdict, the module inventory, af-code family, exit-code
# contract, provenance) — so the manifest can be re-stamped from a
# machine-readable record once the operator approves. The write is
# fail-closed: it happens ONLY on a PASS (self-test pass or dry-run plan
# pass); a FAIL/HELD/STOP run writes nothing and removes nothing. The
# ENGINE-MANIFEST.json / ENGINE-PIN.sha256 / verify.sh are NEVER touched
# here.
#
# STDLIB ONLY (urllib + json via the registry and the check modules); calls
# NO model. DOCTRINE: move in silence; NOTHING Anthropic in any runtime file;
# Convert and Flow naming in every client surface; NEVER print a secret
# value; --dry-run and --self-test are OFFLINE; an archive ACTION requires
# --execute (Trevor-gated) and even then is a plan only — no mutation.
# =============================================================================
"""archive_legacy_workflows.py — the U06 legacy-workflow archive dispatcher
assembled from the u06_modules files: one CLI, offline self-test battery
(golden found / golden absent PASS, the no-execute attack REFUSED), JSON
output, and the manifest-pending/u06.json stage (Skill 59)."""

from __future__ import annotations

import argparse
import importlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry does the
# Cloudflare browser-UA wiring + the internal-rail client and its label
# resolution is the house credential contract.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent
MODULES_DIR = Path(__file__).resolve().parent / "u06_modules"
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"
PENDING_DIR = SKILL_DIR / "manifest-pending"
PENDING_U06 = PENDING_DIR / "u06.json"

# The template location id is the CONTRACT's source_template_location (the
# operator's OWN template location, operator infrastructure config, not a
# secret). The dispatcher pins to it; --location-id overrides for tests.
DEFAULT_TEMPLATE_LOCATION = "2HIKGNgsixWx0yds7Qnx"

# THE u06_modules FILES — the assembly manifest for this dispatcher.
# Every name is imported BY NAME below (importlib), never exec'd from a
# path; a missing module is a STOP, never a silent skip (the fail-closed
# import contract of main_skeleton.load_modules). `role` is the one-line
# contract each module owns. The names mirror the files on disk one-to-one
# (the catalog and the tree never drift; the self-test pins the roster).
U06_MODULES = (
    ("__init__.py",            "fail-closed EMPTY package init (pure namespace)"),
    ("main_skeleton.py",       "the U06 archive-action dispatcher CLI (plan / self-test / live verify; the ONE entry-point contract over the check modules)"),
    ("find_legacy.py",         "the legacy-find law authority + the live read of the TWO legacy Anthology workflows BY EXACT NAME on the PROVEN internal rail (LEGACY_NAMES — the U06 archive targets; read-only, NEVER archives)"),
    ("workflow_lister.py",     "the live read surface of the U06 family — the workflow NAMES of a Convert and Flow location through the PROVEN internal rail (GET /workflow/{loc}/list?limit=200); its ONE ACTION verb 'archive' is Trevor-gated (--execute) and a plan only — no mutation, endpoint doctrine"),
    ("golden_absent.py",       "the archive LAW authority + the golden ABSENT-state fixture: both archive targets (board / ledger — the revoke flow's R2 / R6 pair) EMPTY -> PASS (nothing to archive); the archive ACTION is --execute-gated (GOLDEN_EXECUTE_REQUIRED)"),
    ("golden_found.py",        "the GOLDEN FOUND-state fixture — the canonical in-memory payload of the U06 FIND half in its FOUND state: BOTH contract workflows the archive action touches on the listing byte-exact by the golden keys (read once from find_legacy.LEGACY_NAMES), each with its one synthetic id; READ-ONLY by construction"),
    ("attack_no_execute.py",   "the U06 ATTACK: the archive ACTION requested WITHOUT --execute (the Trevor gate) — the canonical no-execute record that every archive authority MUST refuse (verify_archive exit 5), with the golden execute-required dry-run control PASSING (payload_true) — the pass/fail split discriminates the missing-gate boundary"),
    ("verify_archived.py",     "the ARCHIVED-STATE VERIFIER — the read-back half of the U06 archive law: re-reads the engine's TWO archive targets (board / ledger) after the archive sweep and confirms the archived status BYTE-EXACT; its check ACTION is Trevor-gated (--execute) and READ-ONLY"),
    ("house_rules.py",         "the ONE canonical house-law constant surface (browser UA / version header / the AF autofail table mirrored from docs_u06.AF_CODES plus the shared rows pinned against ENGINE-MANIFEST.json)"),
    ("example_usage.py",       "the fail-closed WORKED EXAMPLE of the U06 dispatch (the FIND law + the golden found-state + the golden absent-state + the no-execute attack + the lister's archive ACTION)"),
    ("test_find_legacy.py",    "the independent pytest battery over the find law (provenance only)"),
    ("test_verify_archived.py", "the independent pytest battery over the archived-state verifier (provenance only)"),
    ("docs_u06.py",            "the U06 tooling README/catalog data + drift gate (the module inventory as DATA)"),
)

# The modules the dispatcher aggregates (main_skeleton.U06_MODULES — the
# check-module set named in the dispatcher's own roster; a check family
# that cannot prove itself offline STOPS).
DISPATCH_MODULE_NAMES = tuple(name for name, _ in (
    ("workflow_lister", "the live read surface of the U06 family — the "
                        "workflow NAMES of a Convert and Flow location "
                        "through the PROVEN internal rail; its ONE ACTION "
                        "verb 'archive' is Trevor-gated and a plan only"),
    ("golden_absent", "the archive LAW authority + the golden ABSENT-state "
                      "fixture (both targets EMPTY -> PASS; the archive "
                      "ACTION is --execute-gated)"),
    ("find_legacy", "the legacy-find law authority + the live read of the "
                    "TWO legacy Anthology workflows BY EXACT NAME on the "
                    "PROVEN internal rail (read-only, NEVER archives)"),
    ("attack_no_execute", "the U06 ATTACK: the archive ACTION requested "
                          "WITHOUT --execute — MUST be refused by every "
                          "archive authority (verify_archive exit 5) with "
                          "the golden execute-required control PASSING"),
    ("golden_found", "the GOLDEN FOUND-state fixture — both contract "
                     "workflows the archive action touches on the listing "
                     "byte-exact by the golden keys"),
    ("docs_u06", "the U06 tooling README/catalog data + drift gate (the "
                 "module inventory as DATA)"),
    ("verify_archived", "the ARCHIVED-STATE VERIFIER — the read-back half "
                        "of the U06 archive law (Trevor-gated, READ-ONLY)"),
    ("house_rules", "the ONE canonical house-law constant surface (browser "
                    "UA, version header, the AF autofail table mirrored "
                    "from docs_u06.AF_CODES)"),
    ("example_usage", "the fail-closed WORKED EXAMPLE of the U06 dispatch"),
))

# The modules that ship their OWN offline self-test battery (golden PASS /
# attack FAIL, exit 0 pass / 4 enforced violation). Every check module ships
# a battery — the dispatcher REQUIRES a battery from every module. The two
# pytest batteries are imported for their provenance; their tests run as the
# independent pytest battery.
SELF_TEST_MODULES = tuple(
    name[:-3] for name, _ in U06_MODULES
    if name not in ("__init__.py", "test_find_legacy.py",
                    "test_verify_archived.py", "main_skeleton.py"))
TEST_MODULES = ("test_find_legacy", "test_verify_archived")

# The live-verify gate order — the dispatcher's fixed order (mirrors
# main_skeleton.LIVE_GATES one-to-one; the self-test pins the two cannot
# drift).
LIVE_GATES = tuple(name for name, _ in (
    ("golden_absent", "the golden ABSENT-state fixture — both archive "
                      "targets (board / ledger) EMPTY, the archive ACTION "
                      "--execute-gated; a present card or row is a FAIL, "
                      "never a blind pass"),
    ("golden_found", "the golden FOUND-state fixture — both contract "
                     "workflows the archive action touches on the listing "
                     "byte-exact by the golden keys; an absent, renamed, "
                     "or duplicated contract workflow is a FAIL, never a "
                     "blind pass"),
    ("find_legacy", "the legacy-find read — the TWO legacy workflows found "
                    "BY EXACT NAME on the live internal-rail listing "
                    "(rail-gated; LEGACY-ABSENT / LEGACY-PARTIAL is a "
                    "MISMATCH, never a half-pass)"),
    ("workflow_lister", "the live workflow list read — the location's "
                        "workflow names through the PROVEN internal rail "
                        "(rail-gated; an EMPTY workflow set is a truthful "
                        "PASS)"),
    ("verify_archived", "the archived-state read-back — the engine's own "
                        "local ledger mirror + board projection, both "
                        "targets confirmed archived byte-exact (NO rail "
                        "credential; a drift is a MISMATCH, an unreadable "
                        "mirror is HELD)"),
))

# The five U06 verified items, as the manifest-pending stage records them
# (docs_u06.VERIFY_ITEMS — the catalog and the tree never drift).
VERIFIED_ITEMS = (
    (1, "find_law", "Find law — the two legacy workflows found BY EXACT "
                    "NAME"),
    (2, "archive_gate", "Archive gate law — the ACTION is Trevor-gated "
                        "(--execute)"),
    (3, "proven_write", "Proven-write law — WITH --execute the action is a "
                        "plan only"),
    (4, "absent_state", "Absent-state law — nothing to archive is a PASS, "
                        "exit 0"),
    (5, "masking", "Masking law — ids by MASKED MARKER on operator "
                   "surfaces"),
)

# The AF-AE autofail family, as the stage records it (mirrored from
# docs_u06.AF_CODES — the family authority).
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
     "a pinned --workflow-id is absent from the live listing — a pin is a "
     "stronger contract than a name, and a mismatch is never a silent "
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

# House exit-code contract (docs_u06.EXIT_CODES).
EXIT_CODES = {
    0: "verified success — the find law agrees with its source of truth "
       "and every archive step ran under its gate (also plan / dry-run / "
       "self-test; an EMPTY workflow set is a truthful PASS; nothing to "
       "archive is a clean no-op PASS)",
    1: "unexpected error (top-level guard; never a secret leak)",
    2: "STOP refusal — the archive ACTION without --execute (the Trevor "
       "gate, AF-AE-U06-ARCHIVE-NO-EXECUTE) or without its byte-exact "
       "target name (AF-AE-U06-ARCHIVE-NO-NAME) / label NOT SET / usage / "
       "the U06 check-module assembly incomplete "
       "(AF-AE-U06-ASSEMBLY-INCOMPLETE) / a name that resolves to no "
       "workflow (AF-AE-U06-NAME-NOT-FOUND) or to more than one "
       "(AF-AE-U06-NAME-AMBIGUOUS) / a contract that cannot be read / a "
       "module STOP-family refusal",
    3: "HELD — the internal rail unreachable / Cloudflare edge block "
       "(CF error 1010) / Firebase exchange failure / a malformed listing "
       "(UNDETERMINED, never a verdict — a bare 401/403 is HELD, never "
       "mislabeled as a find or scope problem)",
    4: "self-test FAILED (AF-AE-TEMPLATE-ATTACK / AF-AE-U06-* / "
       "AF-AE-ATTACKNOEXECUTE-* family, enforced violation) — a tamper "
       "never masquerades as exit 1",
    5: "mismatch / fail-closed default — a legacy absent or partially "
       "present (LEGACY-ABSENT / LEGACY-PARTIAL / LEGACY-EMPTY), a "
       "pinned id absent from the listing (PIN-MISSING / "
       "PIN-ON-WRONG-NAME), a no-execute attack record judged clean "
       "(verify_archive FAIL), a drifted absent-state payload, a "
       "credential-shaped or full-id surface (leak-scan REFUSAL), a "
       "read-back mismatch, or a DEFERRED live read without "
       "--allow-deferred",
}

class AssembleError(Exception):
    """A fail-closed refusal raised by the assembly itself — a missing
    u06_modules file, a module violating the entry-point contract, or a
    manifest-pending stage that cannot be written."""

def _read_json(path: Path, what: str) -> dict:
    """Fail-closed contract reader — a missing section is never a blind pass."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AssembleError("cannot read %s: %s" % (what, exc)) from exc
    except ValueError as exc:
        raise AssembleError("%s is not valid JSON: %s" % (what, exc)) from exc
    if not isinstance(data, dict):
        raise AssembleError("%s does not parse to a JSON object" % what)
    return data

# ---------------------------------------------------------------------------
# The file assembly — import EVERY u06_modules file BY NAME. The empty
# package init is imported for the namespace guarantee (importing the
# package succeeds only if __init__.py is intact); the check modules come
# through main_skeleton.load_modules (the ONE entry-point contract); the
# fixture / checker / docs modules are imported for their surfaces and
# their self-test batteries; the two pytest batteries are imported for
# their provenance (their tests run as the independent pytest battery).
# ---------------------------------------------------------------------------
def _load_package() -> None:
    """Prove the package namespace container imports clean."""
    importlib.import_module("u06_modules")

def load_skeleton() -> object:
    """The main_skeleton dispatcher module (imported BY NAME)."""
    return importlib.import_module("u06_modules.main_skeleton")

def load_all_modules(out=None) -> dict:
    """Import every one of the u06_modules files. Returns {name: module}.
    Fail-closed: a missing file or a module violating its contract raises
    AssembleError (STOP) — the aggregate NEVER passes with a module
    silently absent.

    The check modules go through main_skeleton.load_modules (which enforces
    the ONE-entry-point contract and raises SkeletonError on a violation);
    the fixture / checker / docs modules and the two pytest batteries are
    imported directly here (their self-tests prove their surfaces)."""
    out = out or sys.stderr
    _load_package()
    # The check modules resolve BY NAME (importlib.import_module(name) with
    # bare names inside main_skeleton.load_modules) — their own directory must
    # sit on sys.path for that to resolve, exactly as running the skeleton as
    # a script puts its own directory first.
    if str(MODULES_DIR) not in sys.path:
        sys.path.insert(0, str(MODULES_DIR))

    skeleton = load_skeleton()
    try:
        dispatched = skeleton.load_modules()
    except skeleton.SkeletonError as exc:
        raise AssembleError("check-module load failed: %s" % exc) from exc

    modules = {"main_skeleton": skeleton}
    modules.update(dispatched)
    missing = []
    for name in SELF_TEST_MODULES:
        if name in modules:
            continue
        try:
            modules[name] = importlib.import_module("u06_modules." + name)
        except ImportError:
            missing.append(name)
    for name in TEST_MODULES:
        try:
            modules[name] = importlib.import_module("u06_modules." + name)
        except ImportError:
            missing.append(name)
    if missing:
        raise AssembleError(
            "u06_modules file(s) not found: %s — the assembly is "
            "incomplete (fail-closed: no module is ever skipped)"
            % ", ".join(missing))
    if len(modules) != 12:
        raise AssembleError(
            "assembly loaded %d modules, expected 12 (main_skeleton + 9 "
            "dispatch modules + 2 pytest batteries)" % len(modules))
    return modules

# ---------------------------------------------------------------------------
# Offline self-test — run EVERY module's own battery (golden found / golden
# absent PASS, the no-execute attack REFUSED), plus the main_skeleton
# dispatcher battery, plus this assembler's own assembly assertions, plus
# the two sibling pytest batteries. NO network, NO credentials. Exit 4 on
# any failure.
# ---------------------------------------------------------------------------
def _module_self_test(module, name: str, out) -> None:
    st = getattr(module, "self_test", None)
    if not callable(st):
        raise AssertionError(
            "module %s does not expose 'self_test' — every u06_modules "
            "module must prove itself offline" % name)
    dev = io.StringIO()
    try:
        rc = st(out=dev)
    except TypeError:
        rc = st()
    out.write(dev.getvalue())
    if rc != EX_OK:
        raise AssertionError("%s self_test returned exit %d" % (name, rc))

def _run_pytest(modules: dict, out) -> None:
    """The two sibling pytest batteries — the independent proof that the
    archive-law family (the find law + the archived-state verifier) is
    pinned offline. A failed battery is an enforced violation, never a
    silent skip."""
    pkg = Path(modules["test_find_legacy"].__file__).resolve().parent
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
    """OFFLINE self-test: the modules' own golden+attack batteries (the
    no-execute attack MUST FAIL), the dispatcher battery, the assembly's
    file-count assertions, the archive-law gate (golden found PASS / golden
    absent PASS / no-execute attack REFUSED), and the sibling pytest
    batteries. Any failure is exit 4 (AF-AE-TEMPLATE-ATTACK family) — a
    tamper NEVER masquerades as exit 1. On a clean pass the manifest-pending
    stage is written by the CLI."""
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        # 1. the assembly is complete: exactly the U06 file set exists.
        on_disk = sorted(p.name for p in MODULES_DIR.glob("*.py"))
        expected = sorted(name for name, _ in U06_MODULES)
        assert on_disk == expected, (
            "u06_modules tree drifted: disk carries %d files, the %d-file "
            "assembly contract names %d (%s)"
            % (len(on_disk), len(expected),
               len(set(on_disk) ^ set(expected)),
               ", ".join(sorted(set(on_disk) ^ set(expected)))))
        # 2. every module's own battery passes (golden PASS / attack FAIL).
        for name in SELF_TEST_MODULES:
            _module_self_test(modules[name], name, dev)
        # 3. the dispatcher battery passes (main_skeleton.self_test runs the
        #    nine check modules through the one-entry-point contract and
        #    pins the browser-UA / credential / exit-code / archive-gate
        #    laws). The dispatcher's own battery is run by itself: it
        #    iterates ITS OWN dispatch set (self_test(modules)), and this
        #    assembly already ran every module battery above — so here the
        #    dispatcher battery runs over ITS dispatch modules only, never
        #    over this assembler (which would recurse).
        skeleton = modules["main_skeleton"]
        dispatch_only = {k: v for k, v in modules.items()
                         if k in DISPATCH_MODULE_NAMES}
        sk_rc = skeleton.self_test(dispatch_only, out=dev)
        assert sk_rc == EX_OK, \
            "main_skeleton dispatcher self-test returned exit %d" % sk_rc
        # 3b. the dispatcher's live-gate order is this assembly's live-gate
        #     order (the two can never drift — the aggregate runs the gates
        #     in the FIXED order the archive law carries them).
        assert tuple(name for name, _ in skeleton.LIVE_GATES) == LIVE_GATES, \
            "the dispatcher's LIVE_GATES drifted from the assembly's order"
        # 4. the archive-law gate, exercised through the modules' own
        #    surfaces — the GOLDEN states PASS and the U06 ATTACK FAILS
        #    (never a silent pass, never a blind refusal):
        # 4a. the golden ABSENT-state census PASSES the fail-closed payload
        #     gate (both archive targets — board / ledger, the revoke
        #     flow's R2 / R6 pair — EMPTY -> nothing to archive -> clean
        #     no-op PASS; the archive ACTION is --execute-gated).
        ga = modules["golden_absent"]
        assert ga.GOLDEN_EXECUTE_REQUIRED is True, \
            "the archive LAW must assert GOLDEN_EXECUTE_REQUIRED"
        assert ga.ARCHIVE_ACTION == "archive", \
            "the archive ACTION verb drifted from the U06 contract"
        assert ga.EXECUTE_FLAG == "--execute", \
            "the Trevor gate flag drifted from the U06 contract"
        rc_abs = ga.payload(ga.golden_absent_payload(), out=io.StringIO())
        assert rc_abs == EX_OK, \
            "the golden ABSENT-state census must pass the payload gate"
        # 4b. the golden FOUND-state listing PASSES the fail-closed payload
        #     gate (both contract workflows the archive action touches are
        #     present byte-exact by the golden keys, read once from
        #     find_legacy.LEGACY_NAMES — the find law authority).
        gf = modules["golden_found"]
        fnd = modules["find_legacy"]
        assert tuple(gf.GOLDEN_WORKFLOW_KEYS) == tuple(fnd.LEGACY_NAMES.keys()), \
            "the golden found-state keys drifted from the find law authority"
        found = gf.payload(None, out=io.StringIO())
        assert isinstance(found, dict) and found.get("ok"), \
            "the golden FOUND-state listing must pass the payload gate: %s" \
            % (found.get("af_code", "?") if isinstance(found, dict) else "?")
        # 4c. ATTACK — the archive ACTION WITHOUT --execute (the Trevor
        #     gate) FAILS every archive authority AND the attack fixture's
        #     own fail-closed surface refuses it (AF-AE-ATTACKNOEXECUTE
        #     family). The golden execute-required dry-run control PASSES —
        #     the pass/fail split discriminates the missing-gate boundary,
        #     never a broken instrument.
        ane = modules["attack_no_execute"]
        assert ane.EXECUTE_FLAG == "--execute", \
            "the attack's gate flag drifted from the archive law"
        fail_rc = ane.verify_archive(ane.ATTACK_RECORD, out=io.StringIO())
        assert fail_rc == EX_MISMATCH, \
            "ATTACK (no-execute archive) was NOT refused (exit %s)" % fail_rc
        pass_rc = ane.payload_true(out=io.StringIO())
        assert pass_rc == EX_OK, \
            "the golden execute-required dry-run control must PASS (exit %s)" \
            % pass_rc
        # 4d. the archive gate law at the dispatcher surface: the family's
        #     verbatim no-execute STOP (workflow_lister's OWN CLI archive
        #     without --execute -> exit 2) — the Trevor gate holds in the
        #     module, never only in this assembler.
        wl = modules["workflow_lister"]
        gate_rc = wl.main(["archive", "--name", "Anthology Intake Fire"],
                          environ={})
        assert gate_rc == EX_STOP, \
            ("workflow_lister's CLI archive without --execute must STOP "
             "(exit 2), got %r" % gate_rc)
        # 5. docs_u06's catalog is the assembly's catalog (5 items, exit
        #    codes 0..5 — its self-test already pinned the counts; here we
        #    pin the shared constants).
        docs = modules["docs_u06"]
        assert len(docs.VERIFY_ITEMS) == len(VERIFIED_ITEMS), \
            "docs_u06 item count drifted from the assembly's VERIFIED_ITEMS"
        # 6. the sibling pytest batteries (the independent proof).
        if run_pytest:
            _run_pytest(modules, dev)
    except AssertionError as exc:
        sys.stderr.write("[archive-legacy-workflows] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    except AssembleError as exc:
        sys.stderr.write("[archive-legacy-workflows] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION

    out.write(dev.getvalue())
    out.write("[archive-legacy-workflows] assembled self-test: OK (%d "
              "u06_modules files imported, 9 module batteries + dispatcher "
              "battery + archive-law gate with the no-execute attack "
              "REFUSED + %s + assembly assertions all pass)\n"
              % (len(U06_MODULES),
                 "2 pytest batteries" if run_pytest else
                 "pytest batteries skipped (--no-pytest)"))
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
# Offline plan — no network, no credentials. The dispatcher's plan, with the
# assembly's stage-record on the side. Prints ONE JSON object on stdout.
# ---------------------------------------------------------------------------
def dry_run(modules: dict, location_id: str, contract: dict,
            out=None) -> int:
    out = out or sys.stderr
    skeleton = modules["main_skeleton"]
    # The dispatcher's own plan (the ONE JSON object on stdout, captured
    # into the human channel — the machine surface is this assembler's plan
    # object, so stdout stays ONE JSON document).
    with _redirect_stdout(io.StringIO()):
        rc = skeleton.plan(modules, location_id, contract, out=out)
    if rc != EX_OK:
        return rc
    print(json.dumps({
        "contract": "anthology-engine-u06-dispatch-plan",
        "schema_version": 1,
        "kind": "dry-run",
        "template_location_id": location_id,
        "template_location_id_masked": _mask_id(location_id),
        "gates": list(LIVE_GATES),
        "modules": [name for name, _ in U06_MODULES],
        "dry_run": True,
        "archive_gate": "the archive ACTION requires --execute (Trevor-"
                        "gated); even WITH --execute it is a plan only — "
                        "no mutation (endpoint doctrine)",
        "note": "offline plan only — no network, no credential needed; a "
                "LIVE read must ride reg.InternalRailClient "
                "(CAF_BROWSER_UA on every request — CF 1010 law); the "
                "archive ACTION writes ONLY with its own --execute",
    }, indent=2, sort_keys=True))
    out.write("[archive-legacy-workflows] dry-run plan: OK (offline — no "
              "network, no credential needed)\n")
    return EX_OK

def _mask_id(fid: str) -> str:
    """Mask a workflow / location id for every operator surface — a location
    identifier, not a secret, but never printed in full (house pattern,
    mirrored from workflow_lister._mask_id)."""
    fid = (fid or "").strip()
    if len(fid) <= 8:
        return "***"
    return "%s***%s" % (fid[:4], fid[-4:])

# ---------------------------------------------------------------------------
# Live verify — the dispatcher's fail-closed aggregate over the gates in
# the FIXED order. Any FAIL -> exit 5; a STOP-family refusal propagates as
# exit 2; a transport / edge failure is HELD (exit 3), never mislabeled as
# scope. The two golden fixtures run first (their golden surfaces need no
# credential), then the ONE rail-gated live read, then the local read-back.
# This assembler NEVER performs an archive ACTION itself — the gated ACTION
# surface is workflow_lister's own CLI with --execute, and this assembler's
# CLI refuses the ACTION without --execute (the Trevor gate) and passes the
# operator-gate status INTO the module's surface (which re-proves its own
# no-execute STOP verbatim).
# ---------------------------------------------------------------------------
def verify_live(modules: dict, location_id: str, contract: dict, *,
                allow_deferred: bool = False, archive: bool = False,
                archive_name: str = "", archive_anthology_id: str = "",
                archive_state_dir: str = "", out=None) -> int:
    out = out or sys.stderr
    skeleton = modules["main_skeleton"]
    return skeleton.verify_live(
        modules, location_id, contract, allow_deferred=allow_deferred,
        archive=archive, archive_name=archive_name,
        archive_anthology_id=archive_anthology_id,
        archive_state_dir=archive_state_dir, out=out)

# ---------------------------------------------------------------------------
# Manifest-pending stage — manifest-pending/u06.json. Written ONLY after a
# PASS (self-test pass or dry-run plan pass); a FAIL/HELD/STOP run writes
# nothing. The record is the machine-readable input to a later manifest
# re-stamp — the ENGINE-MANIFEST.json / ENGINE-PIN.sha256 / verify.sh are
# NEVER touched here.
# ---------------------------------------------------------------------------
def _pending_payload(kind: str, location_id: str, *,
                     verdict: str = "PASS") -> dict:
    return {
        "contract": "anthology-engine-u06-archive-action",
        "schema_version": 1,
        "kind": kind,  # "self-test" | "dry-run" | "verify"
        "verdict": verdict,
        "script": "archive_legacy_workflows.py",
        "authored_by": "U06",
        "template_location_id": location_id,
        "u06_modules": [
            {"name": name, "role": role} for name, role in U06_MODULES
        ],
        "check_modules": list(DISPATCH_MODULE_NAMES),
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
            "note": "the ONE live read (find_legacy / workflow_lister) is "
                    "rail-gated (Firebase refresh token BY LABEL with the "
                    "Firebase API key) and HELD (exit 3) when the rail is "
                    "unreachable — never a fabricated pass; the archive "
                    "ACTION is Trevor-gated (--execute) and a plan only — "
                    "this assembler never writes.",
        },
    }

def write_pending(payload: dict, *, mode: str = "self-test", out=None) -> None:
    """Write manifest-pending/u06.json (fail-closed: only after a PASS).

    The directory is created if absent; the file is written atomically
    (temp + rename) so a crash mid-write never leaves a partial stage. The
    ENGINE-MANIFEST.json / ENGINE-PIN.sha256 / verify.sh are NEVER touched."""
    out = out or sys.stderr
    try:
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        tmp = PENDING_DIR / ("u06.json.tmp-%d" % os.getpid())
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
        tmp.replace(PENDING_U06)
    except OSError as exc:
        raise AssembleError("cannot write %s: %s" % (PENDING_U06, exc)) from exc
    out.write("[archive-legacy-workflows] manifest-pending stage written: %s "
              "(%s)\n" % (PENDING_U06, mode))

# ---------------------------------------------------------------------------
# CLI — house shape: --dry-run / --self-test / --json accepted as flags AND
# as a positional subcommand (--self-test / --selftest normalize exactly as
# anthology_registry.py and the U02 / U03 / U04 / U05 skeletons). The
# archive ACTION is a positional subcommand ('archive') that REQUIRES
# --execute (the Trevor gate) — without it the ACTION is a STOP (exit 2),
# never a silent no-op; even WITH --execute it is a plan only (no mutation,
# endpoint doctrine).
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="archive_legacy_workflows.py",
        description="The U06 legacy-workflow archive dispatcher assembled "
                    "from the u06_modules files: offline self-test battery "
                    "(golden found / golden absent PASS, the no-execute "
                    "attack REFUSED), offline plan, and live verify of the "
                    "ARCHIVE-ACTION LAW family on the Anthology TEMPLATE "
                    "location (Skill 59) — every delta documented as JSON, "
                    "the manifest-pending stage written after a PASS. The "
                    "archive ACTION requires --execute (Trevor-gated) and "
                    "is a plan only; this tool never writes.")
    ap.add_argument("--location-id", default="",
                    help="override the template location id (default: the "
                         "contract's source_template_location."
                         "template_location_id, %s; never printed)"
                         % DEFAULT_TEMPLATE_LOCATION)
    ap.add_argument("--allow-deferred", action="store_true",
                    help="explicit operator opt-in: accept a DEFERRED live "
                         "read as PASS — the report still records the "
                         "deferral")
    ap.add_argument("--contract", default=str(CONTRACT_PATH),
                    help="path to anthology-snapshot-contract.json")
    ap.add_argument("--dry-run", action="store_true",
                    help="offline plan only — no network, no credential "
                         "(default: live verify)")
    ap.add_argument("--json", action="store_true",
                    help="emit a machine-readable summary on stdout (default "
                         "on for verify/plan)")
    ap.add_argument("--execute", action="store_true",
                    help="the Trevor gate for the archive ACTION — REQUIRED "
                         "before any archive; without it the ACTION is a "
                         "STOP (exit 2); even WITH it the archive is a plan "
                         "only (no mutation, endpoint doctrine)")
    ap.add_argument("--name", default="",
                    help="the byte-exact target workflow name (archive "
                         "ACTION; REQUIRED for archive, never a nameless "
                         "sweep)")
    ap.add_argument("--anthology-id", default="",
                    help="the read-back target anthology id (verify_archived "
                         "gate; masked on every surface, never printed in "
                         "full; REQUIRED for the archived-state gate, never "
                         "a sweep)")
    ap.add_argument("--state-dir", default="",
                    help="engine state directory for the archived-state "
                         "read-back (default: the engine's own resolution — "
                         "ANTHOLOGY_STATE_DIR / OPENCLAW_DATA_DIR / node "
                         "home)")
    ap.add_argument("--no-pytest", action="store_true",
                    help="skip the sibling pytest batteries inside "
                         "--self-test (dispatch self-test only; the offline "
                         "batteries still run)")
    ap.add_argument("--selftest", "--self-test", dest="self_test",
                    action="store_true",
                    help="run the offline self-test (golden found / golden "
                         "absent PASS, the no-execute attack REFUSED + the "
                         "dispatcher battery + the pytest batteries) and "
                         "exit")
    ap.add_argument("cmd", nargs="?", choices=["verify", "plan", "archive",
                                               "self-test"],
                    help="positional subcommand form (verify / plan / "
                         "archive / self-test)")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> --self-test so the flag form never
    # collides with the positional subcommand form.
    if "--self-test" in argv and "--selftest" not in argv:
        argv = ["--self-test" if a == "--self-test" else a for a in argv]
    args = ap.parse_args(argv)
    # Positional subcommand form (house shape): self-test -> the offline
    # battery; plan -> the offline dry-run; verify -> the live read.
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
                write_pending(_pending_payload("self-test",
                                               DEFAULT_TEMPLATE_LOCATION),
                              mode="self-test")
            return rc

        contract = _read_json(Path(args.contract).expanduser(),
                              "anthology-snapshot-contract.json")
        location_id = (args.location_id.strip() or
                       (contract.get("source_template_location") or {}).get("template_location_id")
                       or DEFAULT_TEMPLATE_LOCATION)

        if args.dry_run:
            rc = dry_run(modules, location_id, contract, out=sys.stderr)
            if rc == EX_OK:
                write_pending(_pending_payload("dry-run", location_id),
                              mode="dry-run")
            return rc

        if args.cmd == "archive":
            # The Trevor gate, enforced at the CLI surface: an archive
            # ACTION without --execute is a STOP (exit 2), never a silent
            # no-op. WITH --execute it is a plan only — the dispatcher
            # never mutates.
            if not args.execute:
                reg._stop(sys.stderr,
                          "archive REFUSED: no --execute (the Trevor gate).",
                          ["An archive ACTION without --execute is a STOP "
                           "(AF-AE-U06-ARCHIVE-NO-EXECUTE), never a silent "
                           "no-op. Re-run with --execute to authorize the "
                           "ACTION — it is a plan only (no mutation, "
                           "endpoint doctrine) and the report records it "
                           "explicitly (marker %s)." % _mask_id(location_id)])
                return EX_STOP
            return verify_live(modules, location_id, contract,
                               allow_deferred=args.allow_deferred,
                               archive=True, archive_name=args.name,
                               archive_anthology_id=args.anthology_id,
                               archive_state_dir=args.state_dir,
                               out=sys.stderr)

        rc = verify_live(modules, location_id, contract,
                         allow_deferred=args.allow_deferred,
                         archive_anthology_id=args.anthology_id,
                         archive_state_dir=args.state_dir,
                         out=sys.stderr)
        if rc == EX_OK:
            write_pending(_pending_payload("verify", location_id),
                          mode="verify")
        return rc

    except reg.ScopeDenied as exc:
        sys.stderr.write("[archive-legacy-workflows] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[archive-legacy-workflows] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[archive-legacy-workflows] HELD: %s\n" % exc)
        return EX_HELD
    except reg.InternalRailUnavailable as exc:
        sys.stderr.write("[archive-legacy-workflows] HELD (internal rail): "
                         "%s\n" % exc)
        return EX_HELD
    except AssembleError as exc:
        sys.stderr.write("[archive-legacy-workflows] STOP/FAIL: %s\n" % exc)
        return EX_STOP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[archive-legacy-workflows] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR

if __name__ == "__main__":
    sys.exit(main())
