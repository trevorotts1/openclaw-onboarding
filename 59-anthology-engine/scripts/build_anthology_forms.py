#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: build_anthology_forms.py  (U08/U09 tooling)
# U08/U09 FORMS-LAW ASSEMBLY DISPATCHER — the ONE CLI ASSEMBLED from the
# u08_u09_modules files: it imports EVERY module under scripts/u08_u09_modules/
# BY NAME (importlib, never exec'd from a path) and wires them into ONE CLI
# whose offline self-test battery (the golden title-select / golden
# universal-review fixtures PASS, the hidden-missing and bad-dropdown attacks
# REFUSED) runs before any live surface. This file carries NO check logic
# itself — a check family is exercised ONLY through its module so
# `--dry-run`, `--self-test`, and the live aggregate never drift apart. It is
# the packaged sibling of scripts/live_verify_template.py (U02, row 54),
# scripts/check_pipeline_name.py (U03, row 55), scripts/fix_intake_form.py
# (U04, row 56), scripts/check_intake_fire_scope.py (U05, row 57),
# scripts/archive_legacy_workflows.py (U06, row 58) and
# scripts/provision_fields.py (U07, row 59) under the ENGINE-MANIFEST row-54
# shipping doctrine; its OWN manifest row is staged manifest-pending/
# u08_u09.json (PENDING — the U08/U09 manifest row is stamped by this
# assembly, exactly as the U07 row was stamped by provision_fields.py).
#
# THE u08_u09_modules FILES (imported by name; each is STDLIB-only and
# self-tests itself — docs_forms.py carries the module inventory as data and
# its self-test proves the tree ships together). The family's FIXED roster —
# 16 files: the empty package init, the main_skeleton dispatcher, the eleven
# dispatch modules, and the three sibling pytest batteries (the exact
# 12-module catalog docs_forms.CONTRACT_MODULE_COUNT pins, plus the four
# non-dispatch files):
#   __init__.py            fail-closed EMPTY package init (pure namespace;
#                          records the package doctrine — every CREATE
#                          ACTION is Trevor-gated by --execute)
#   main_skeleton.py       the U08/U09 form-law dispatcher CLI (plan /
#                          self-test / live verify; the ONE entry-point
#                          contract over the check modules)
#   form_spec_loader.py    the FAIL-CLOSED THREE-FORM SPEC LOADER AND
#                          CONTRACT GATE — the single implementation of the
#                          anthology-snapshot-contract.json forms load-and-
#                          verify law: the hidden-field law [contact_id,
#                          anthology_id, stage] byte-exact on every required
#                          and contract-bound row, the universal-review slug
#                          a NAMED form never a count row, the pinned form
#                          ids byte-equal their live authorities — refuse
#                          anything else (FormSpecError, STOP, exit 2),
#                          never a partial load. OFFLINE, READ-ONLY,
#                          NETWORK-FREE; form ids by masked marker only
#   golden_title.py        the GOLDEN TITLE-SELECT FIXTURE — the canonical
#                          in-memory payload of the S3 title-selection
#                          surface in its GOLDEN state: the byte-exact
#                          locked PAIR (title AND subtitle — the lock is a
#                          PAIR, never a title-only stamp), the composite
#                          participant_key under the KEYING LAW, the
#                          one-way lock truth, the fixed two doors
#                          (nudge_link / dashboard); payload(candidate=None)
#                          judges a select payload fail-closed (exit 0 PASS
#                          / 5 REFUSED); the live selection write is
#                          Trevor-gated (--execute) — the gate lives in the
#                          dispatcher, never in a fixture
#   golden_review.py       the GOLDEN UNIVERSAL-REVIEW FIXTURE — the
#                          canonical in-memory payload of the universal-
#                          review decision surface in its GOLDEN state: the
#                          UNIVERSAL_REVIEW_FORM slug byte-exact, the
#                          decision present and non-empty, the keys riding
#                          the field-map authority, the cover choice (when
#                          carried) ONE of the four style names, and the
#                          golden s7_cover HOLD -> certified does-not-fire;
#                          payload(candidate) judges fail-closed (exit 0
#                          PASS / 5 REFUSED)
#   attack_missing_hidden.py  the U08/U09 ATTACK #1: a deterministic DEEP
#                          strict-subset hidden-field container carrying
#                          only TWO of the THREE universal hidden fields
#                          (the canonical trio minus its LAST contract row
#                          by position — the stage token today) that every
#                          byte-exact hidden-field gate MUST DETECT and
#                          never pass: verify_missing_hidden FAILs the
#                          2-of-3 read with exit 5 (missing key named)
#                          while the true 3-key control (payload_true,
#                          --execute-gated) PASSES exit 0 — the pass/fail
#                          split discriminates the deep-strict-subset
#                          boundary, never a broken instrument. The attack
#                          ships ONLY with --execute
#   attack_bad_dropdown.py the U08/U09 ATTACK #2: a deterministic wrong-
#                          option decision-dropdown picklist — the FIRST of
#                          the two gate actions byte-swapped to the repo's
#                          OWN documented drifted spelling
#                          (approved_as_is, pinned byte-exact against
#                          golden_review.GOLDEN_DECISION and proven NOT in
#                          the two gate actions) that every byte-exact
#                          picklist gate MUST DETECT and never pass:
#                          verify_options FAILs the wrong-option read with
#                          exit 5 (wrong option and expected option named)
#                          while the true two-option golden control
#                          (payload_true, --execute-gated) PASSES exit 0.
#                          The attack ships ONLY with --execute
#   hidden_field_module.py the HIDDEN-FIELD CREATOR — create-or-verify the
#                          universal hidden-field trio (contact_id /
#                          anthology_id / stage) on the universal author-
#                          intake form through the proven public write rail
#                          PUT /forms/{id} (Version header + CAF_BROWSER_UA
#                          — the Cloudflare edge fix). WITHOUT --execute a
#                          READ-ONLY dry-run (nothing written); WITH
#                          --execute a PUT and a read-back that must prove
#                          the trio byte-exact (AF-AE-READBACK-MISMATCH,
#                          exit 5); a missing / unreadable listing is
#                          FORMS-NOT-FOUND / FORMS-EMPTY (exit 2)
#   title_select_builder.py  the TITLE-SELECT FORM BUILDER — the S3 gate
#                          form of the three-slug family: EXACTLY TWO
#                          routing hidden fields (anthology_id, stage —
#                          never the intake trio) plus the TWO visible
#                          multi-line REQUIRED fields (title, subtitle),
#                          built through the proven public rail PUT
#                          /forms/{id} with a read-back; Trevor-gated; a
#                          read-back that does not prove the build is a
#                          MISMATCH (exit 5), never a reported success
#   universal_review_builder.py  the UNIVERSAL-REVIEW FORM BUILDER — the
#                          decision form of the family: EXACTLY TWO hidden
#                          fields (anthology_id, stage — never contact_id),
#                          the TWO-option decision dropdown (Approve as-is
#                          / Request rewrite with notes — read once from
#                          gate_engine's action vocabulary), the multi-line
#                          notes surface, and the FOUR-option cover
#                          dropdown (the U8 style names read once from
#                          cover_render.STYLE_NAMES), built through PUT
#                          /forms/{id} with a read-back; Trevor-gated
#   dropdown_module.py     the TWO-DROPDOWN CREATE-OR-VERIFY MODULE — the
#                          SINGLE_OPTIONS law of the review surface: the
#                          PRD Section 4 decision field
#                          (contact.anthology_review_decision — the two
#                          gate actions from gate_engine) and the U8 cover-
#                          choice field (contact.anthology_cover_choice —
#                          the four named styles from cover_render.
#                          STYLE_NAMES, byte-exact against config/
#                          field-map.json choice_options). Missing keys
#                          WITHOUT --execute are a STOP (exit 2) that lists
#                          them; WITH --execute create-only-missing at
#                          SINGLE_OPTIONS with the exact picklists then
#                          re-read (a drift is exit 5); a live field of the
#                          WRONG type is never re-created and never
#                          re-typed — it is a FAIL (exit 5)
#   prefill_verifier.py    the U08 VALUE-SIDE GATE — the minted intake
#                          link's TWO query params (?anthology_id=<minted>
#                          &stage=<stage>) must pre-fill the form's HIDDEN
#                          anthology_id AND stage fields (the U08 two-
#                          hidden-field extension of the U04 G3 value-side
#                          law); the live read is the PUBLIC hosted-form
#                          page + the PUBLIC widget build — zero
#                          credentials; a real browser render is OPTIONAL
#                          (absent runtime -> rendered check SKIPPED as
#                          undetermined, never fabricated); run_live -> 0
#                          PASS / 5 MISMATCH / 3 HELD / 2 STOP; --execute
#                          is REQUIRED for the live verify (u08_u09
#                          doctrine); NOT part of the default live
#                          aggregate — it never fires inside an un-gated
#                          run (exercised through --self-test and its own
#                          batteries)
#   docs_forms.py          the U08/U09 tooling README / catalog data +
#                          drift gate — the three named forms and their
#                          laws, the module inventory, the house exit
#                          codes, the AF family, the doctrine, and the
#                          credential labels as DATA; readme() renders FROM
#                          the same data the self-test asserts against, so
#                          documentation and data cannot drift; its
#                          self-test is a read-only filesystem drift gate —
#                          a doc that names a module that does not ship
#                          FAILS its self-test exit 4
#   test_prefill.py        the independent pytest battery over the
#                          pre-fill verifier (provenance only)
#   test_title_builder.py  the independent pytest battery over the
#                          title-select builder (provenance only)
#   test_review_builder.py the independent pytest battery over the
#                          universal-review builder (provenance only)
# (the assembly manifests — main_skeleton.U08_U09_MODULES and
# docs_forms.MODULES — carry this exact roster; the self-test pins the tree
# ships together.)
#
# THE U08/U09 ATTACKS (the offline self-test proves both are REFUSED —
# golden PASS / attack FAIL; a tamper NEVER masquerades as exit 1):
#   attack_missing_hidden — the 2-of-3 deep strict-subset hidden-field
#                           container (the universal trio minus its LAST
#                           contract row — the stage token today) MUST FAIL
#                           the byte-exact hidden-field judge
#                           (verify_missing_hidden exit 5, missing key
#                           named) while the true 3-key control
#                           (payload_true, --execute-gated) PASSES exit 0
#                           — the pass/fail split discriminates the
#                           deep-strict-subset boundary, never a broken
#                           instrument.
#   attack_bad_dropdown —   the one-option-wrong decision-dropdown picklist
#                           (the FIRST of the two gate actions byte-swapped
#                           to the repo's OWN documented drifted spelling
#                           approved_as_is — pinned byte-exact against
#                           golden_review.GOLDEN_DECISION, never invented)
#                           MUST FAIL the byte-exact picklist judge
#                           (verify_options exit 5, wrong option and
#                           expected option named) while the true two-
#                           option golden control (payload_true,
#                           --execute-gated) PASSES exit 0 — the pass/fail
#                           split discriminates the one-option-wrong
#                           boundary, never a broken instrument.
#
# WHAT THIS VERIFIES (MASTER-SPEC U08/U09 — the FAIL-CLOSED FORM-SURFACE
# LAW of the anthology engine: the three named forms of the snapshot
# contract — universal-intake / universal-review / title-select — each
# carrying its byte-exact hidden-field contract, its exact visible field
# law, and its exact SINGLE_OPTIONS dropdown law, with every WRITE ACTION
# Trevor-gated by --execute per the package-init doctrine). The
# dispatcher's live gates run in the FIXED order main_skeleton.LIVE_GATES
# carries them; the per-item claims live in the modules and in
# docs_forms.FORMS:
#   1. THE 3-FORM SPEC CONTRACT GATE — config/anthology-snapshot-contract
#      .json (the SINGLE SOURCE OF TRUTH) loads and verifies against its
#      own law: the hidden-field trio [contact_id, anthology_id, stage]
#      byte-exact on every required and contract-bound row, the
#      universal-review slug a NAMED form never a count row, the pinned
#      form ids byte-equal their live authorities (form_spec_loader.
#      load_command — OFFLINE, pure; a contract that drifted from its own
#      law is a STOP (exit 2, FormSpecError), never a blind load).
#   2. THE GOLDEN TITLE-SELECT GATE — the golden selection must PASS its
#      own fail-closed judge: the byte-exact locked PAIR (title AND
#      subtitle — the lock is a PAIR, never a title-only stamp), the
#      composite participant_key under the KEYING LAW (read once through
#      anthology_state.participant_key), the one-way lock truth, the fixed
#      two doors (nudge_link / dashboard) (golden_title.payload — exit 0,
#      never a blind pass).
#   3. THE GOLDEN UNIVERSAL-REVIEW GATE — the golden submission must PASS
#      its own fail-closed judge: the UNIVERSAL_REVIEW_FORM slug byte-
#      exact (read once from u05_modules.negative_verifier), the decision
#      present and non-empty, the keys riding the field-map authority, the
#      cover choice (when carried) ONE of the four style names, and the
#      golden s7_cover HOLD -> certified does-not-fire (golden_review.
#      payload — exit 0, never a blind pass).
#   4. THE ATTACK BOUNDARIES — the 2-of-3 deep strict-subset hidden-field
#      read MUST fail the byte-exact hidden-field judge (exit 5, missing
#      key named) with the true 3-key control PASSING exit 0
#      (attack_missing_hidden), and the one-option-wrong decision picklist
#      MUST fail the byte-exact picklist judge (exit 5, wrong option and
#      expected option named) with the true two-option golden control
#      PASSING exit 0 (attack_bad_dropdown) — every pass/fail split
#      discriminates its ONE-variable boundary, never a broken instrument.
#   5. THE DROPDOWN LAW — the review decision field (2 options) and the
#      cover-choice field (4 style names) live SINGLE_OPTIONS byte-exact
#      (dropdown_module.verify_live — missing keys WITHOUT --execute are a
#      STOP (exit 2) that lists them; a wrong-type field or a drifted
#      picklist is a MISMATCH (exit 5), never a silent pass).
#   6. THE HIDDEN-FIELD CREATOR — the universal author-intake form's
#      hidden trio byte-exact (hidden_field_module.plan_field_create —
#      without --execute a READ-ONLY dry-run over the live listing,
#      nothing written; with --execute the PUT + read-back,
#      AF-AE-READBACK-MISMATCH never reported as success).
#   7. THE TITLE-SELECT BUILDER — the S3 gate form's EXACTLY TWO routing
#      hidden fields (anthology_id, stage) + the visible multi-line
#      REQUIRED pair (title, subtitle), byte-exact (title_select_builder.
#      plan_form_build — dry-run / PUT + read-back exactly as above).
#   8. THE UNIVERSAL-REVIEW BUILDER — the decision form's hidden pair
#      (never contact_id), the TWO-option decision dropdown, the multi-line
#      notes surface, and the FOUR-option cover dropdown
#      (universal_review_builder.plan_review_build — dry-run / PUT +
#      read-back exactly as above).
#
# CREATION IS TREVOR-GATED HERE. The dispatcher NEVER writes without
# --execute: the live verify itself is an ACTION under the package-init
# doctrine — an un-gated run is refused up front (exit 2, AF-AE-U08-U09-
# NO-EXECUTE), never a silent read sweep; even WITH --execute every write
# is create-only-missing with a byte-exact read-back — a surface already
# present live is verified, never re-created; a read-back that does not
# prove the write is a MISMATCH (exit 5, AF-AE-READBACK-MISMATCH family).
# The no-execute law is proven REFUSED by the offline self-test (the
# create-capable modules' own batteries assert the module-level no-execute
# dry-run / refusal laws; attack_missing_hidden's battery asserts its
# fixtures ship ONLY with --execute; the dispatcher's OWN CLI probe refuses
# `apply` without --execute verbatim — the two-surface law). The assembler
# itself carries NO write surface.
#
# THE LIVE READS ARE CREDENTIAL-GATED; THE TOOLING SHIPS NOW (manifest row
# doctrine). The operator executes `verify` only from a session that can
# resolve the client's OWN location-scoped private-integration token BY
# LABEL (CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_API_KEY /
# GOHIGHLEVEL_API_KEY / GOHIGHLEVEL_PIT / GHL_API_KEY — live process env
# first, then the three canonical client env stores) and the location id
# through reg.resolve_location (CONVERT_AND_FLOW_LOCATION_ID /
# GOHIGHLEVEL_LOCATION_ID / GHL_LOCATION_ID) unless --location-id
# overrides. --dry-run (offline plan) and --self-test (offline, no token,
# no network) always work. The offline gates (the form-spec contract gate,
# the golden fixtures, the two attack boundaries) are exercised with their
# own golden surfaces and NEVER require a credential — and the aggregate
# still refuses up front without --execute (the package doctrine), so no
# live read ever fires inside an un-gated run. The ONE credential-free
# live gate is prefill_verifier (its live reads ride the PUBLIC hosted-
# form surface, zero credentials — but it too is --execute-gated by the
# package doctrine, and it is NOT part of the default live aggregate).
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. A token value is NEVER printed,
# and the location / form ids are masked on every surface
# (reg._mask_location / the modules' last-4 markers — the house shape).
# Every plan and report payload is scanned against the credential shape
# (pit-\S+) before print — a hit REFUSES the surface rather than echo a
# token.
#
# BROWSER UA: every request rides reg.CafClient, which applies
# CAF_BROWSER_UA on every request so the Cloudflare edge fronting
# services.leadconnectorhq.com never 1010s a request (CF 1010 / GK-09
# discipline — the house pattern ported byte-for-byte from the U02..U07
# families). The dispatcher's self-test pins the exact constant on the
# registry surface so a drifted UA is caught before a single live request.
# Scope-vs-edge-block discrimination: a bare 401/403 is HELD
# (UpstreamBlockedError / CafUnreachable), never mislabeled as a scope
# problem; a genuine scope denial is a STOP (exit 2).
#
# AF CODES (fail-closed surfaces; self-test failures are exit 4, never 1;
# the family is staged under manifest-pending/u08_u09.json, its OWN
# manifest row stamped by this assembly):
#   AF-AE-U08-U09-ASSEMBLY-INCOMPLETE -> the check-module set named in
#          U08_U09_MODULES is not fully present, or a module violates the
#          one-entry-point contract. STOP (exit 2) — a check family is
#          never silently skipped.
#   AF-AE-U08-U09-NO-EXECUTE         -> a CREATE ACTION (or the live verify
#          itself) requested without --execute (the Trevor gate,
#          package-init doctrine). STOP (exit 2) — a write is never
#          silent, and an un-gated live verify never fires.
#   AF-AE-FORMSPEC-*                 -> the 3-form spec contract gate
#          refused (missing forms block / hidden-field law drift / a
#          universal-review count-row leak / a drifted pinned id). STOP
#          (exit 2, FormSpecError).
#   AF-AE-FIELDS-* / FORMS-*         -> the live form / dropdown surface
#          is empty (FORMS-EMPTY) or absent (FORMS-NOT-FOUND), or a
#          dropdown key is missing live / of the wrong type / with a
#          drifted picklist (AF-AE-FIELDS-MISSING family). exit 5 for a
#          mismatch, exit 2 for a named refusal.
#   AF-AE-READBACK-MISMATCH          -> a PUT happened but the read-back
#          does not prove the write byte-exact. exit 5 (the shared house
#          code, already stamped in ENGINE-MANIFEST.json).
#   AF-AE-REVIEW-*                   -> the golden universal-review judge
#          refused (FORM-TOKEN / STAGE-CURSOR / DECISION-DRIFT). exit 5.
#   AF-AE-GOLDENTITLE-*              -> the golden title-select judge
#          refused (a blank / drifted title or subtitle, a lock not
#          one-way, an unknown door, a non-golden participant key).
#          exit 5.
#   AF-AE-ATTACKMISSINGHIDDEN-*      -> the hidden-field attack fixture
#          drifted, or the attack was refused without --execute. exit 5 /
#          exit 4 (self-test).
#   AF-AE-ATTACKBADDROPDOWN-*        -> the wrong-option dropdown attack
#          fixture drifted, or the attack was refused without --execute.
#          exit 5 / exit 4 (self-test).
#   AF-AE-PREFILL-*                  -> the value-side gate refused
#          (BASELINE-UNREADABLE / BASELINE-MALFORMED / EXECUTE / RENDER).
#          exit 2 STOP or 3 HELD (a page that cannot be fetched is HELD,
#          never judged).
#   AF-AE-TEMPLATE-ATTACK            -> an attack fixture tripped the
#          OFFLINE self-test (also the family self-test batteries).
#          exit 4.
#
# EXIT CODES (house convention 0/1/2/3/5; 4 = enforced violation only
# inside the offline self-test batteries — the operator CLI of this
# assembler resolves to 0 / 2 / 5 exactly, per the U08/U09 surface
# contract; the primary surface the operator consumes is 0 = PASS,
# 2 = STOP, 5 = mismatch):
#   0  all checks PASS (also --dry-run plan pass and self-test pass)
#   1  unexpected error
#   2  STOP refusal — a CREATE ACTION or the live verify without --execute
#      (the Trevor gate, AF-AE-U08-U09-NO-EXECUTE) / label NOT SET /
#      usage / the check-module assembly incomplete (AF-AE-U08-U09-
#      ASSEMBLY-INCOMPLETE) / a form-spec contract refusal (AF-AE-FORMSPEC-*)
#      / a module STOP-family refusal (FormSpecError / FormsFixError /
#      FormsBuildError / ReviewBuildError / DropdownError / StyleImportError
#      / DecisionImportError / FixtureError, incl. missing dropdowns
#      listed without --execute)
#   3  HELD — Convert and Flow unreachable / Cloudflare edge block (CF
#      error 1010) / a page that cannot be fetched (UNDETERMINED, never a
#      verdict)
#   4  self-test FAILED — an assertion in an OFFLINE self-test battery
#      tripped (AF-AE-TEMPLATE-ATTACK family). A tamper NEVER masquerades
#      as exit 1. (Batteries are exercised through `--self-test` and inside
#      the aggregate's gate order; an operator CLI run never returns 4.)
#   5  data or read-back mismatch (a hidden-field strict subset, a
#      dropdown of the wrong type or a drifted picklist, a drifted locked
#      pair, a foreign review token / decision / stage cursor, a read-back
#      that does not prove the build; the fail-closed default)
#
# STDLIB ONLY (urllib + json via the registry and the check modules); calls
# NO model. Reuses anthology_registry (CafClient, resolve_pit,
# resolve_location, _stop, _mask_location, CAF_BROWSER_UA). DOCTRINE: move
# in silence; NOTHING Anthropic in any runtime file; Convert and Flow
# naming in every client surface; NEVER print a secret value; --dry-run and
# --self-test are OFFLINE; a CREATE ACTION requires --execute
# (Trevor-gated) and is create-only-missing with a byte-exact read-back —
# never a silent write.
# =============================================================================
"""build_anthology_forms.py — the U08/U09 forms-law assembly dispatcher:
offline plan / offline self-test / live verify / the Trevor-gated CREATE
ACTION of the three-form, hidden-field, dropdown and value-side laws of the
Anthology engine (Skill 59, u08_u09_modules; the packaged sibling of
provision_fields.py (U07), archive_legacy_workflows.py (U06),
check_intake_fire_scope.py (U05), fix_intake_form.py (U04),
check_pipeline_name.py (U03) and live_verify_template.py (U02)). Every
CREATE ACTION and the live verify itself require --execute (Trevor-gated,
the u08_u09 package-init doctrine) — this dispatcher never mutates."""

from __future__ import annotations

import argparse
import importlib
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry does the
# Cloudflare browser-UA wiring + the LeadConnector client, and its label
# resolution is the house credential contract.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "u04_modules"))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"
PENDING_DIR = SKILL_DIR / "manifest-pending"
PENDING_U08_U09 = PENDING_DIR / "u08_u09.json"

# The template location pin, imported from the contract the U02..U07
# siblings use (the snapshot contract's source_template_location). The live
# reads resolve the location BY LABEL first (resolve_location) with
# --location-id as the override; this literal is the plan/report scaffold
# marker, masked on every surface.
DEFAULT_TEMPLATE_LOCATION = "2HIKGNgsixWx0yds7Qnx"

# The u08_u09_modules directory itself — sibling imports resolve from here.
MODULES_DIR = Path(__file__).resolve().parent / "u08_u09_modules"
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

# THE u08_u09_modules FILES — the assembly manifest for this dispatcher.
# Every name is imported BY NAME below (importlib), never exec'd from a
# path; a missing module is a STOP, never a silent skip (the fail-closed
# import contract of main_skeleton.load_modules). `role` is the one-line
# contract each module owns. The names mirror the files on disk one-to-one
# (the catalog and the tree never drift; the self-test pins the roster).
U08_U09_FILES = (
    ("__init__.py",            "fail-closed EMPTY package init (pure namespace)"),
    ("main_skeleton.py",       "the U08/U09 form-law dispatcher CLI (plan / self-test / live verify; the ONE entry-point contract over the check modules)"),
    ("form_spec_loader.py",    "the FAIL-CLOSED THREE-FORM SPEC LOADER AND CONTRACT GATE — the single implementation of the anthology-snapshot-contract.json forms load-and-verify law: the hidden-field law [contact_id, anthology_id, stage] byte-exact on every required and contract-bound row, the universal-review slug a NAMED form never a count row, the pinned form ids byte-equal their live authorities — refuse anything else (FormSpecError, STOP, exit 2), never a partial load. OFFLINE, READ-ONLY, NETWORK-FREE; a form id is reported by masked marker only, never by value"),
    ("golden_title.py",        "the GOLDEN TITLE-SELECT FIXTURE — the canonical in-memory payload of the S3 title-selection surface in its GOLDEN state: the byte-exact locked PAIR (title AND subtitle — the lock is a PAIR, never a title-only stamp), the composite participant_key under the KEYING LAW (read once through anthology_state.participant_key), the one-way lock truth, the fixed two doors (nudge_link / dashboard); payload(candidate=None) judges a select payload fail-closed (exit 0 PASS / 5 REFUSED); the live selection write is Trevor-gated (--execute) — the gate lives in the dispatcher, never in a fixture"),
    ("golden_review.py",       "the GOLDEN UNIVERSAL-REVIEW FIXTURE — the canonical in-memory payload of the universal-review decision surface in its GOLDEN state: the UNIVERSAL_REVIEW_FORM slug byte-exact (read once from u05_modules.negative_verifier), the decision present and non-empty, the keys riding the field-map authority, the cover choice (when carried) ONE of the four style names, and the golden s7_cover HOLD -> certified does-not-fire; payload(candidate) judges a review submission fail-closed (exit 0 PASS / 5 REFUSED)"),
    ("attack_missing_hidden.py", "the U08/U09 ATTACK #1: a deterministic DEEP strict-subset hidden-field container carrying only TWO of the THREE universal hidden fields (the canonical trio minus its LAST contract row by position — the stage token today) that every byte-exact hidden-field gate MUST DETECT and refuse (verify_missing_hidden exit 5, missing key named) while the true 3-key control (payload_true, --execute-gated) PASSES exit 0 — the pass/fail split discriminates the deep-strict-subset boundary, never a broken instrument. The attack ships ONLY with --execute"),
    ("attack_bad_dropdown.py", "the U08/U09 ATTACK #2: a deterministic wrong-option decision-dropdown picklist — the FIRST of the two gate actions byte-swapped to the repo's OWN documented drifted spelling (approved_as_is, pinned byte-exact against golden_review.GOLDEN_DECISION and proven NOT in the two gate actions) that every byte-exact picklist gate MUST DETECT and refuse (verify_options exit 5, wrong option and expected option named) while the true two-option golden control (payload_true, --execute-gated) PASSES exit 0 — the pass/fail split discriminates the one-option-wrong boundary, never a broken instrument. The attack ships ONLY with --execute"),
    ("hidden_field_module.py", "the HIDDEN-FIELD CREATOR — create-or-verify the universal hidden-field trio (contact_id / anthology_id / stage) on the universal author-intake form through the proven public write rail PUT /forms/{id} (Version header + CAF_BROWSER_UA — the Cloudflare edge fix). WITHOUT --execute a READ-ONLY dry-run (nothing written); WITH --execute a PUT and a read-back that must prove the trio byte-exact (AF-AE-READBACK-MISMATCH, exit 5); a missing / unreadable listing is FORMS-NOT-FOUND / FORMS-EMPTY (exit 2)"),
    ("title_select_builder.py", "the TITLE-SELECT FORM BUILDER — the S3 gate form of the three-slug family: EXACTLY TWO routing hidden fields (anthology_id, stage — never the intake trio) plus the TWO visible multi-line REQUIRED fields (title, subtitle), built through the proven public rail PUT /forms/{id} with a read-back; Trevor-gated exactly like the hidden-field creator; a read-back that does not prove the build is a MISMATCH (exit 5), never a reported success"),
    ("universal_review_builder.py", "the UNIVERSAL-REVIEW FORM BUILDER — the decision form of the family: EXACTLY TWO hidden fields (anthology_id, stage — never contact_id), the TWO-option decision dropdown (Approve as-is / Request rewrite with notes — read once from gate_engine's action vocabulary), the multi-line notes surface, and the FOUR-option cover dropdown (the U8 style names read once from cover_render.STYLE_NAMES), built through PUT /forms/{id} with a read-back; Trevor-gated; a drifted decision / cover picklist or an unproven read-back is a MISMATCH (exit 5)"),
    ("dropdown_module.py",   "the TWO-DROPDOWN CREATE-OR-VERIFY MODULE — the SINGLE_OPTIONS law of the review surface: the PRD Section 4 universal-review decision field (contact.anthology_review_decision, the two gate actions approve_as_is / request_rewrite_with_notes from gate_engine) and the U8 cover-choice field (contact.anthology_cover_choice, the four named styles from cover_render.STYLE_NAMES, byte-exact against config/field-map.json choice_options). verify_live: missing keys WITHOUT --execute are a STOP (exit 2) that lists them; WITH --execute create-only-missing at SINGLE_OPTIONS with the exact picklists then re-read (a drift is exit 5); a live field of the WRONG type is never re-created and never re-typed — it is a FAIL (exit 5)"),
    ("prefill_verifier.py",  "the U08 VALUE-SIDE GATE — the minted intake link's TWO query params (?anthology_id=<minted>&stage=<stage>) must pre-fill the form's HIDDEN anthology_id AND stage fields (the U08 two-hidden-field extension of the U04 G3 value-side law); the live read is the PUBLIC hosted-form page + the PUBLIC widget build — zero credentials; a real browser render is OPTIONAL (absent runtime -> rendered check SKIPPED as undetermined, never fabricated); run_live -> 0 PASS / 5 MISMATCH / 3 HELD / 2 STOP; --execute is REQUIRED for the live verify (u08_u09 doctrine)"),
    ("docs_forms.py",        "the U08/U09 tooling README / catalog data + drift gate — the three named forms and their laws, the module inventory, the house exit codes, the AF family, the doctrine, and the credential labels as DATA; readme() renders FROM the same data the self-test asserts against, so documentation and data cannot drift; its self-test is a read-only filesystem drift gate — a doc that names a module that does not ship FAILS its self-test exit 4"),
    ("test_prefill.py",      "the independent pytest battery over the pre-fill verifier (provenance only)"),
    ("test_title_builder.py", "the independent pytest battery over the title-select builder (provenance only)"),
    ("test_review_builder.py", "the independent pytest battery over the universal-review builder (provenance only)"),
)

# The modules the dispatcher aggregates (main_skeleton.U08_U09_MODULES —
# the check-module set named in the dispatcher's own roster; a check family
# that cannot prove itself offline STOPS).
DISPATCH_MODULE_NAMES = tuple(
    name[:-3] for name, _ in U08_U09_FILES
    if name not in ("__init__.py", "main_skeleton.py")
    and not name.startswith("test_"))

# The modules that ship their OWN offline self-test battery (golden PASS /
# attack FAIL, exit 0 pass / 4 enforced violation). Every check module ships
# a battery — the dispatcher REQUIRES a battery from every module. The
# three pytest batteries are imported for their provenance; their tests run
# as the independent pytest battery.
SELF_TEST_MODULES = tuple(
    name[:-3] for name, _ in U08_U09_FILES
    if name not in ("__init__.py", "test_prefill.py",
                    "test_title_builder.py", "test_review_builder.py",
                    "main_skeleton.py"))
TEST_MODULES = ("test_prefill", "test_title_builder", "test_review_builder")

# The live-verify gate order — the dispatcher's fixed order (mirrors
# main_skeleton.LIVE_GATES one-to-one; the self-test pins the two cannot
# drift).
LIVE_GATES = tuple(name for name, _ in (
    ("form_spec_loader", "the 3-form spec contract gate — load-and-verify config/anthology-snapshot-contract.json (the SINGLE SOURCE OF TRUTH) against its own law (the hidden-field trio byte-exact, the universal-review slug a NAMED form, the pinned ids byte-equal their live authorities); a contract that drifted is a STOP, never a blind load"),
    ("golden_title", "the golden title-select gate — the golden selection must PASS its own fail-closed judge (the byte-exact locked PAIR, the KEYING LAW key, the one-way lock, the fixed two doors; exit 0, never a blind pass)"),
    ("golden_review", "the golden universal-review gate — the golden submission must PASS its own fail-closed judge (the UNIVERSAL_REVIEW_FORM slug byte-exact, the decision present, the keys riding the field-map, the cover choice in the four style names, the s7_cover HOLD; exit 0, never a blind pass)"),
    ("attack_missing_hidden", "the hidden-field attack boundary — the 2-of-3 deep strict-subset hidden-field read MUST fail the byte-exact judge (exit 5, missing key named) while the true 3-key control PASSES exit 0 (the pass/fail split discriminates the deep-strict-subset boundary, never a broken instrument)"),
    ("attack_bad_dropdown", "the dropdown attack boundary — the one-option-wrong decision picklist MUST fail the byte-exact picklist judge (exit 5, wrong option and expected option named) while the true two-option golden control PASSES exit 0 (the pass/fail split discriminates the one-option-wrong boundary, never a broken instrument)"),
    ("dropdown_module", "the two-dropdown law — the review decision field (2 options) and the cover-choice field (4 style names) live SINGLE_OPTIONS byte-exact (missing keys WITHOUT --execute are a STOP that lists them; a wrong-type field or a drifted picklist is a MISMATCH, exit 5, never a silent pass)"),
    ("hidden_field_module", "the hidden-field creator — the universal author-intake form's hidden trio byte-exact (without --execute a READ-ONLY dry-run over the live listing, nothing written; with --execute the PUT + read-back, AF-AE-READBACK-MISMATCH never reported as success)"),
    ("title_select_builder", "the title-select builder — the S3 gate form's EXACTLY TWO routing hidden fields (anthology_id, stage) + the visible multi-line REQUIRED pair (title, subtitle), byte-exact (dry-run / PUT + read-back as above)"),
    ("universal_review_builder", "the universal-review builder — the decision form's hidden pair (never contact_id), the TWO-option decision dropdown, the multi-line notes surface, and the FOUR-option cover dropdown (dry-run / PUT + read-back as above)"),
))

# The three U08/U09 verified items, as the manifest-pending stage records
# them (docs_forms.FORMS — the catalog and the tree never drift).
VERIFIED_ITEMS = (
    (1, "form_spec_law", "3-form spec law — the snapshot contract loads "
                         "and verifies against its own law (the hidden-"
                         "field trio, the named review slug, the pinned "
                         "ids)"),
    (2, "golden_fixtures", "Golden fixtures law — the golden title-select "
                           "PAIR and the golden universal-review "
                           "submission PASS their own fail-closed judges"),
    (3, "attack_boundaries", "Attack boundaries law — the 2-of-3 hidden "
                             "strict subset and the one-option-wrong "
                             "dropdown are REFUSED with their golden "
                             "controls PASSING"),
    (4, "dropdown_law", "Dropdown law — the decision field (2 options) "
                        "and the cover-choice field (4 style names) live "
                        "SINGLE_OPTIONS byte-exact"),
    (5, "create_gate", "Create gate law — every CREATE ACTION (and the "
                       "live verify) STOPS without --execute"),
)

# The AF-AE autofail family, as the stage records it (mirrored from
# docs_forms.AF_CODES — the family authority).
AF_CODES = (
    ("AF-AE-U08-U09-NO-EXECUTE", 2,
     "an ACTION (a form create / build / write, or the live verify itself) "
     "was requested without the operator's explicit --execute (the Trevor "
     "gate, u08_u09_modules/__init__.py doctrine) — a refusal, never a "
     "silent no-op and never a silent write; an un-gated live verify never "
     "fires (not yet stamped in ENGINE-MANIFEST.json)"),
    ("AF-AE-READBACK-MISMATCH", 5,
     "a PUT returned success but the read-back in the SAME job does not "
     "prove the build byte-exact — never reported as built (the house "
     "code, already stamped in ENGINE-MANIFEST.json)"),
    ("AF-AE-PREFILL-EXECUTE", 2,
     "the pre-fill live verify was requested without --execute — an "
     "operator-gated live action in this package (background or accidental "
     "invocations must never even probe the live surface)"),
    ("AF-AE-PREFILL-BASELINE-UNREADABLE", 2,
     "the committed pre-fill widget-build baseline "
     "(config/prefill-verifier-baseline.json) is missing or unreadable — "
     "a check that cannot see its law never fabricates a pass"),
    ("AF-AE-PREFILL-BASELINE-MALFORMED", 2,
     "the committed pre-fill baseline is malformed (not a JSON object / "
     "drifted structure) — the hydration law became unverifiable, never a "
     "silent pass"),
    ("AF-AE-PREFILL-RENDER", 5,
     "a headless-Chromium render observed a probe value rendered non-exact "
     "or onto the wrong field, or a prefill rendered with its param "
     "absent — the rendered hidden-field values must be exact (the render "
     "is OPTIONAL — absent runtime is SKIPPED-as-undetermined, never "
     "fabricated)"),
    ("AF-AE-TEMPLATE-ATTACK", 4,
     "an attack fixture tripped the OFFLINE self-test of a family module "
     "or battery (enforced violation — the house code, shared with the "
     "U02 / U03 / U04 / U05 / U06 / U07 families)"),
)

# House exit-code contract (docs_forms.EXIT_CODES).
EXIT_CODES = {
    0: "verified success — the live form carries its law byte-exact (also "
       "plan / dry-run / self-test / a documented PASS)",
    1: "unexpected error (top-level guard; never a secret leak)",
    2: ("STOP refusal — label NOT SET / non-pit- value / usage / the "
        "--execute gate withheld (AF-AE-U08-U09-NO-EXECUTE: an ACTION "
        "without the gate is a refusal, never a silent write) / the "
        "pre-fill live verify without --execute (AF-AE-PREFILL-EXECUTE) / "
        "the U08/U09 check-module assembly incomplete "
        "(AF-AE-U08-U09-ASSEMBLY-INCOMPLETE) / a form-spec contract "
        "refusal (AF-AE-FORMSPEC-*) / an unreadable listing shape / a "
        "genuine location-scope denial / a module STOP-family refusal "
        "(FormSpecError / FormsFixError / FormsBuildError / "
        "ReviewBuildError / DropdownError / StyleImportError / "
        "DecisionImportError / FixtureError)"),
    3: ("HELD — Convert and Flow unreachable / Cloudflare edge block "
        "(CF error 1010) / an applied-but-unreadable PUT (the live state "
        "is UNDETERMINED, never reported as built) / a pre-fill fetch or "
        "render that cannot complete"),
    4: ("self-test FAILED (the AF-AE-* enforced-violation family — a "
        "tamper never masquerades as exit 1)"),
    5: ("mismatch / fail-closed default — a form row absent (FORMS-EMPTY / "
        "FORMS-NOT-FOUND), a pinned id absent from the listing, a "
        "byte-drifted hidden-field law (including a strict subset), a "
        "drifted decision or cover option set, a pre-fill page that is "
        "not byte-identical or a drifted widget-build signature "
        "(AF-AE-PREFILL-*), a read-back that does not prove the build "
        "(AF-AE-READBACK-MISMATCH), or a fixture payload that drifted"),
}

class AssembleError(Exception):
    """A fail-closed refusal raised by the assembly itself — a missing
    u08_u09_modules file, a module violating the entry-point contract, or a
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
# The file assembly — import EVERY u08_u09_modules file BY NAME. The empty
# package init is imported for the namespace guarantee (importing the
# package succeeds only if __init__.py is intact); the check modules come
# through main_skeleton.load_modules (the ONE entry-point contract); the
# fixture / docs modules are imported for their surfaces and their
# self-test batteries; the three pytest batteries are imported for their
# provenance (their tests run as the independent pytest battery).
# ---------------------------------------------------------------------------
def _load_package() -> None:
    """Prove the package namespace container imports clean."""
    importlib.import_module("u08_u09_modules")


def load_skeleton() -> object:
    """The main_skeleton dispatcher module (imported BY NAME)."""
    return importlib.import_module("u08_u09_modules.main_skeleton")


def load_all_modules(out=None) -> dict:
    """Import every one of the u08_u09_modules files. Returns {name: module}.
    Fail-closed: a missing file or a module violating its contract raises
    AssembleError (STOP) — the aggregate NEVER passes with a module
    silently absent.

    The check modules go through main_skeleton.load_modules (which enforces
    the ONE-entry-point contract and raises SkeletonError on a violation);
    the fixture / docs modules and the three pytest batteries are imported
    directly here (their self-tests prove their surfaces)."""
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
            modules[name] = importlib.import_module("u08_u09_modules." + name)
        except ImportError:
            missing.append(name)
    for name in TEST_MODULES:
        try:
            modules[name] = importlib.import_module("u08_u09_modules." + name)
        except ImportError:
            missing.append(name)
    if missing:
        raise AssembleError(
            "u08_u09_modules file(s) not found: %s — the assembly is "
            "incomplete (fail-closed: no module is ever skipped)"
            % ", ".join(missing))
    if len(modules) != 15:
        raise AssembleError(
            "assembly loaded %d modules, expected 15 (main_skeleton + 11 "
            "dispatch modules + 3 pytest batteries)" % len(modules))
    return modules


# ---------------------------------------------------------------------------
# Offline self-test — run EVERY module's own battery (golden title-select /
# golden universal-review PASS, the hidden-missing and bad-dropdown attacks
# REFUSED), plus the main_skeleton dispatcher battery, plus this assembler's
# own assembly assertions (including the two attack boundaries driven
# through the fixtures' OWN surfaces), plus the three sibling pytest
# batteries. NO network, NO credentials. Exit 4 on any failure.
# ---------------------------------------------------------------------------
def _module_self_test(module, name: str, out) -> None:
    st = getattr(module, "self_test", None)
    if not callable(st):
        raise AssertionError(
            "module %s does not expose 'self_test' — every u08_u09_modules "
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
    """The three sibling pytest batteries — the independent proof that the
    U08/U09 family (the pre-fill verifier + the title-select builder + the
    universal-review builder) is pinned offline. A failed battery is an
    enforced violation, never a silent skip."""
    pkg = Path(modules["test_prefill"].__file__).resolve().parent
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


class _FORM_SPEC_READER:
    """The in-memory read surface the hidden-field attack judge consumes —
    the fixture stays OFFLINE (the surface hands back the contract's forms
    block, never a network call)."""

    def list_forms(self, location_id=None):
        import u08_u09_modules.attack_missing_hidden as _attack
        return _attack._FixtureReader().list_forms(location_id)


def _contract_for_attack() -> dict:
    """The snapshot contract the OFFLINE attack judge judges against — the
    committed config copy read through the family's OWN loader surface (the
    fail-closed contract gate): load_form_spec returns the verified forms
    surface, so the contract object is reconstructed with the verified forms
    in place for the judge that consumes it. A contract that drifted from
    its own law refuses the judge instead of shipping a wrong verdict."""
    try:
        forms = _contract_forms()
        contract = _read_json(CONTRACT_PATH,
                              "config/anthology-snapshot-contract.json")
        contract["forms"] = forms
        return contract
    except Exception as exc:  # noqa: BLE001 — the caller STOPs on a refusal
        raise AssembleError(
            "the attack judge cannot load config/anthology-snapshot-"
            "contract.json through the family loader: %s: %s"
            % (type(exc).__name__, exc)) from exc


def _contract_forms():
    """The snapshot contract's forms surface, loaded through the family's
    OWN fail-closed loader (the single implementation of the load-and-verify
    law). A contract that drifted from its own law raises FormSpecError —
    the caller STOPs."""
    try:
        sys.path.insert(0, str(MODULES_DIR))
        import form_spec_loader as fsl  # noqa: E402
    except ImportError as exc:
        raise AssembleError("form_spec_loader cannot be imported: %s" % exc)
    return fsl.load_form_spec(str(CONTRACT_PATH))


def self_test(modules: dict, out=None, *, run_pytest: bool = True) -> int:
    """OFFLINE self-test: the modules' own golden+attack batteries (the
    hidden-missing and bad-dropdown attacks MUST FAIL), the dispatcher
    battery, the assembly's file-count assertions, the form-surface law gate
    (golden fixtures PASS / both attacks REFUSED), and the sibling pytest
    batteries. Any failure is exit 4 (AF-AE-TEMPLATE-ATTACK family) — a
    tamper NEVER masquerades as exit 1. On a clean pass the manifest-pending
    stage is written by the CLI."""
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        # 1. the assembly is complete: exactly the U08/U09 file set exists.
        on_disk = sorted(p.name for p in MODULES_DIR.glob("*.py"))
        expected = sorted(name for name, _ in U08_U09_FILES)
        assert on_disk == expected, (
            "u08_u09_modules tree drifted: disk carries %d files, the "
            "%d-file assembly contract names %d (%s)"
            % (len(on_disk), len(expected),
               len(set(on_disk) ^ set(expected)),
               ", ".join(sorted(set(on_disk) ^ set(expected)))))
        # 2. every module's own battery passes (golden PASS / attack FAIL).
        for name in SELF_TEST_MODULES:
            _module_self_test(modules[name], name, dev)
        # 3. the dispatcher battery passes (main_skeleton.self_test runs the
        #    eleven check modules through the one-entry-point contract and
        #    pins the browser-UA / credential / exit-code / create-gate
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
        #     in the FIXED order the form-surface law carries them).
        assert tuple(name for name, _ in skeleton.LIVE_GATES) == LIVE_GATES, \
            "the dispatcher's LIVE_GATES drifted from the assembly's order"
        # 4. the form-surface law gate, exercised through the modules' own
        #    surfaces — the GOLDEN states PASS and the U08/U09 ATTACKS FAIL
        #    (never a silent pass, never a blind refusal):
        # 4a. the golden TITLE-SELECT selection PASSES the fail-closed
        #     payload gate (the byte-exact locked PAIR — title AND
        #     subtitle — the KEYING LAW key, the one-way lock, the fixed
        #     two doors; synthetic ids only).
        gt = modules["golden_title"]
        golden_title_rc = gt.payload(None, out=io.StringIO())
        assert golden_title_rc == EX_OK, \
            "the golden title-select selection must pass its own judge " \
            "(exit %s)" % golden_title_rc
        # 4b. the golden UNIVERSAL-REVIEW submission PASSES the fail-closed
        #     payload gate (the UNIVERSAL_REVIEW_FORM slug byte-exact, the
        #     decision present, the keys riding the field-map, the cover
        #     choice in the four style names, the s7_cover HOLD certified
        #     does-not-fire).
        gr = modules["golden_review"]
        golden_review_rc = gr.payload(gr.golden_review_payload(),
                                      out=io.StringIO())
        assert golden_review_rc == EX_OK, \
            "the golden universal-review submission must pass its own " \
            "judge (exit %s)" % golden_review_rc
        # 4c. ATTACK #1 — the 2-of-3 deep strict-subset hidden-field
        #     container (the universal trio minus its LAST contract row —
        #     the stage token) FAILS the byte-exact hidden-field judge
        #     (exit 5, missing key named) while the true 3-key control
        #     PASSES — the pass/fail split discriminates the deep-strict-
        #     subset boundary, never a broken instrument. The judge consumes
        #     the fixture's OWN canonical ATTACK_HIDDEN_FIELDS payload
        #     through the in-memory read surface the fixture ships for it.
        amh = modules["attack_missing_hidden"]
        attack_rc = amh.verify_missing_hidden(
            amh._FixtureReader(), "form_piped_fx", _contract_for_attack(),
            out=io.StringIO())
        assert attack_rc == EX_MISMATCH, \
            "ATTACK #1 (2-of-3 hidden fields present) was NOT refused " \
            "(exit %s)" % attack_rc
        control_rc = amh.payload_true(contract=_contract_for_attack(),
                                      execute=True, out=io.StringIO())
        assert control_rc == EX_OK, \
            "the true 3-key control must PASS (exit %s)" % control_rc
        # 4d. ATTACK #2 — the one-option-wrong decision-dropdown picklist
        #     (the FIRST of the two gate actions byte-swapped to the repo's
        #     OWN documented drifted spelling approved_as_is) FAILS the
        #     byte-exact picklist judge (exit 5, wrong option and expected
        #     option named) while the true two-option golden control PASSES
        #     — the pass/fail split discriminates the one-option-wrong
        #     boundary, never a broken instrument.
        abd = modules["attack_bad_dropdown"]
        drift_rc = abd.verify_options(list(abd.ATTACK_OPTIONS),
                                      out=io.StringIO())
        assert drift_rc == EX_MISMATCH, \
            "ATTACK #2 (one wrong decision option) was NOT refused " \
            "(exit %s)" % drift_rc
        control_rc = abd.payload_true(execute=True, out=io.StringIO())
        assert control_rc == EX_OK, \
            "the golden two-option control must PASS (exit %s)" % control_rc
        # 4e. the create gate law at the dispatcher surface: the family's
        #     own batteries (hidden_field_module / title_select_builder /
        #     universal_review_builder / dropdown_module / the two attack
        #     fixtures) each assert the module-level no-execute laws — those
        #     batteries ran in step 2 above and each pins its no-execute
        #     assertion verbatim (the builders' read-only dry-runs, the
        #     attack fixtures' --execute-only shipping). The dispatcher's
        #     OWN CLI-surface refusal of `apply` without --execute is proven
        #     separately in the skeleton's create-gate law
        #     (main_skeleton._create_gate — step 3 above ran it).
        # 5. docs_forms's catalog is the assembly's catalog (12 modules, 3
        #    forms, exit codes 0..5 — its self-test already pinned the
        #    counts; here we pin the shared constants).
        docs = modules["docs_forms"]
        assert docs.CONTRACT_FORM_COUNT == 3, \
            "the 3-form law drifted from the family catalog"
        assert docs.CONTRACT_MODULE_COUNT == 12, \
            "the 12-module catalog count drifted from the family catalog"
        # 6. the sibling pytest batteries (the independent proof).
        if run_pytest:
            _run_pytest(modules, dev)
    except AssertionError as exc:
        sys.stderr.write("[build-anthology-forms] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    except AssembleError as exc:
        sys.stderr.write("[build-anthology-forms] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION

    out.write(dev.getvalue())
    out.write("[build-anthology-forms] assembled self-test: OK (%d "
              "u08_u09_modules files imported, 12 module batteries + "
              "dispatcher battery + form-surface law gate with the "
              "hidden-missing and bad-dropdown attacks REFUSED + %s + "
              "assembly assertions all pass)\n"
              % (len(U08_U09_FILES),
                 "3 pytest batteries" if run_pytest else
                 "pytest batteries skipped (--no-pytest)"))
    return EX_OK


def _mask_id(fid: str) -> str:
    """Mask a form / location id for every operator surface — a tenant
    identifier, not a secret, but never printed in full (house pattern,
    mirrored from the u08_u09 modules' own masking)."""
    fid = (fid or "").strip()
    if len(fid) <= 8:
        return "***"
    return "%s***%s" % (fid[:4], fid[-4:])


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


_CREDENTIAL_SHAPE = re.compile(r"pit-\S+")


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
    payload = {
        "contract": "anthology-engine-u08-u09-dispatch-plan",
        "schema_version": 1,
        "kind": "dry-run",
        "template_location_id": location_id,
        "template_location_id_masked": _mask_id(location_id),
        "gates": list(LIVE_GATES),
        "modules": [name for name, _ in U08_U09_FILES],
        "dry_run": True,
        "create_gate": "every CREATE ACTION (and the live verify itself) "
                       "requires --execute (Trevor-gated, the u08_u09 "
                       "package-init doctrine); without --execute a write "
                       "is REFUSED (exit 2, AF-AE-U08-U09-NO-EXECUTE) — "
                       "never a silent no-op, never a silent create; even "
                       "WITH --execute every write is create-only-missing "
                       "with a byte-exact read-back",
        "note": "offline plan only — no network, no credential needed; the "
                "live form reads ride the public v2 rail with CAF_BROWSER_UA "
                "on every request — CF 1010 law",
    }
    dumped = json.dumps(payload, indent=2, sort_keys=True)
    if _CREDENTIAL_SHAPE.search(dumped):
        raise AssembleError(
            "plan payload carries a credential-shaped string — REFUSED "
            "without printing it")
    print(dumped)
    out.write("[build-anthology-forms] dry-run plan: OK (offline — no "
              "network, no credential needed)\n")
    return EX_OK


# ---------------------------------------------------------------------------
# Live verify — the dispatcher's fail-closed aggregate over the gates in
# the FIXED order. Any FAIL -> exit 5; a STOP-family refusal propagates as
# exit 2; a transport / edge failure is HELD (exit 3), never mislabeled as
# scope. The offline gates (form-spec contract, golden fixtures, both
# attack boundaries) run first — their golden surfaces need no credential —
# then the PIT-gated live form / dropdown reads and the gated build
# surfaces. This assembler NEVER performs a CREATE ACTION itself — the
# gated ACTION surface is the family's apply path with --execute, and this
# assembler's CLI refuses the ACTION without --execute (the Trevor gate)
# and passes the operator-gate status INTO the module surfaces (which
# re-prove their own no-execute STOPs verbatim).
# ---------------------------------------------------------------------------
def verify_live(modules: dict, location_id: str, contract: dict, *,
                execute: bool = False, out=None) -> int:
    out = out or sys.stderr
    skeleton = modules["main_skeleton"]
    return skeleton.verify_live(modules, location_id, contract,
                                field_map=_read_json(
                                    FIELD_MAP_PATH,
                                    "config/field-map.json"),
                                execute=execute, out=out)


# ---------------------------------------------------------------------------
# Manifest-pending stage — manifest-pending/u08_u09.json. Written ONLY after
# a PASS (self-test pass or dry-run plan pass); a FAIL/HELD/STOP run writes
# nothing. The record is the machine-readable input to a later manifest
# re-stamp — the ENGINE-MANIFEST.json / ENGINE-PIN.sha256 / verify.sh are
# NEVER touched here.
# ---------------------------------------------------------------------------
def _pending_payload(kind: str, location_id: str, *,
                     verdict: str = "PASS") -> dict:
    return {
        "contract": "anthology-engine-u08-u09-forms-law",
        "schema_version": 1,
        "kind": kind,  # "self-test" | "dry-run" | "verify"
        "verdict": verdict,
        "script": "build_anthology_forms.py",
        "authored_by": "U08/U09",
        "template_location_id": location_id,
        "u08_u09_modules": [
            {"name": name, "role": role} for name, role in U08_U09_FILES
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
            "note": "every CREATE ACTION (and the live verify itself) is "
                    "Trevor-gated (--execute, the u08_u09 package-init "
                    "doctrine) — without --execute a write is a STOP "
                    "(exit 2, AF-AE-U08-U09-NO-EXECUTE), never a silent "
                    "no-op and never a silent create; even WITH --execute "
                    "every write is create-only-missing with a byte-exact "
                    "read-back — this assembler never writes.",
        },
    }


def write_pending(payload: dict, *, mode: str = "self-test", out=None) -> None:
    """Write manifest-pending/u08_u09.json (fail-closed: only after a PASS).

    The directory is created if absent; the file is written atomically
    (temp + rename) so a crash mid-write never leaves a partial stage. The
    ENGINE-MANIFEST.json / ENGINE-PIN.sha256 / verify.sh are NEVER touched."""
    out = out or sys.stderr
    try:
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        tmp = PENDING_DIR / ("u08_u09.json.tmp-%d" % os.getpid())
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
        tmp.replace(PENDING_U08_U09)
    except OSError as exc:
        raise AssembleError("cannot write %s: %s" % (PENDING_U08_U09, exc)) from exc
    out.write("[build-anthology-forms] manifest-pending stage written: %s "
              "(%s)\n" % (PENDING_U08_U09, mode))


# ---------------------------------------------------------------------------
# CLI — house shape: --dry-run / --self-test / --json accepted as flags AND
# as a positional subcommand (--self-test / --selftest normalize exactly as
# anthology_registry.py and the U02..U07 siblings). The CREATE ACTION is a
# positional subcommand ('apply') that REQUIRES --execute (the Trevor
# gate); the default `verify` also REQUIRES --execute (the live aggregate
# is an ACTION under the package-init doctrine — an un-gated run is
# refused, never a silent read sweep; --dry-run and --self-test stay
# OFFLINE and free).
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="build_anthology_forms.py",
        description="The U08/U09 forms-law dispatcher assembled from the "
                    "u08_u09_modules files: offline self-test battery "
                    "(golden title-select / golden universal-review PASS, "
                    "the hidden-missing and bad-dropdown attacks REFUSED), "
                    "offline plan, and live verify of the three-form, "
                    "hidden-field, dropdown and value-side laws on the "
                    "Convert and Flow location (Skill 59) — every delta "
                    "documented as JSON, the manifest-pending stage written "
                    "after a PASS. Every CREATE ACTION and the live verify "
                    "itself require --execute (Trevor-gated, the u08_u09 "
                    "package-init doctrine); this tool never writes on its "
                    "own.")
    ap.add_argument("--location-id", default="",
                    help="override the Convert and Flow location id "
                         "(default: the CLIENT-standard location labels "
                         "CONVERT_AND_FLOW_LOCATION_ID / "
                         "GOHIGHLEVEL_LOCATION_ID / GHL_LOCATION_ID, %s; "
                         "masked on every surface, never printed in full)"
                         % DEFAULT_TEMPLATE_LOCATION)
    ap.add_argument("--contract", default=str(CONTRACT_PATH),
                    help="path to config/anthology-snapshot-contract.json "
                         "(the single source of truth)")
    ap.add_argument("--field-map", default=str(FIELD_MAP_PATH),
                    help="path to config/field-map.json (the single source "
                         "of truth for the dropdown keys)")
    ap.add_argument("--dry-run", action="store_true",
                    help="offline plan only — no network, no credential "
                         "(default: live verify)")
    ap.add_argument("--json", action="store_true",
                    help="emit a machine-readable summary on stdout (default "
                         "on for verify/plan)")
    ap.add_argument("--execute", action="store_true",
                    help="the Trevor gate (u08_u09 package doctrine): "
                         "REQUIRED before ANY write AND before the live "
                         "verify itself; without it a CREATE ACTION is a "
                         "STOP (exit 2) and the live aggregate is refused "
                         "up front (AF-AE-U08-U09-NO-EXECUTE); with it, "
                         "every write is create-only-missing with a "
                         "byte-exact read-back")
    ap.add_argument("--no-pytest", action="store_true",
                    help="skip the sibling pytest batteries inside "
                         "--self-test (dispatch self-test only; the offline "
                         "batteries still run)")
    ap.add_argument("--selftest", "--self-test", dest="self_test",
                    action="store_true",
                    help="run the offline self-test (golden fixtures PASS, "
                         "the hidden-missing and bad-dropdown attacks "
                         "REFUSED + the dispatcher battery + the pytest "
                         "batteries) and exit")
    ap.add_argument("cmd", nargs="?", choices=["verify", "plan", "apply",
                                               "self-test"],
                    help="positional subcommand form (verify / plan / "
                         "apply / self-test)")

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
                              "config/anthology-snapshot-contract.json")
        location_id = args.location_id.strip() or DEFAULT_TEMPLATE_LOCATION

        if args.dry_run:
            rc = dry_run(modules, location_id, contract, out=sys.stderr)
            if rc == EX_OK:
                write_pending(_pending_payload("dry-run", location_id),
                              mode="dry-run")
            return rc

        if args.cmd == "apply":
            # The Trevor gate, enforced at the CLI surface: a CREATE ACTION
            # without --execute is a STOP (exit 2), never a silent no-op and
            # never a silent create. WITH --execute it is create-only-missing
            # with a byte-exact read-back — the dispatcher never mutates.
            if not args.execute:
                reg._stop(sys.stderr,
                          "apply REFUSED: no --execute (the Trevor gate).",
                          ["A CREATE ACTION without --execute is a STOP "
                           "(AF-AE-U08-U09-NO-EXECUTE), never a silent "
                           "create. Re-run with --execute to authorize the "
                           "ACTION — it is create-only-missing with a "
                           "byte-exact read-back (marker %s)."
                           % _mask_id(location_id)])
                return EX_STOP
            return verify_live(modules, location_id, contract,
                               execute=True,
                               out=sys.stderr)

        # ---- live verify (the aggregate is itself an ACTION: the gate
        #      holds up front — an un-gated run is refused, never a silent
        #      read sweep) ----
        if not args.execute:
            reg._stop(sys.stderr,
                      "verify REFUSED: no --execute (the Trevor gate).",
                      ["The live verify is itself an ACTION under the "
                       "u08_u09 package-init doctrine — it reads the "
                       "client's OWN location and runs the family's "
                       "CREATE surfaces in their dry-run shape. Without "
                       "--execute it is a STOP (AF-AE-U08-U09-NO-EXECUTE), "
                       "never a silent read sweep. Run `--dry-run` for the "
                       "offline plan or `--self-test` for the offline "
                       "battery (both are OFFLINE and free); re-run with "
                       "--execute to authorize the live verify (marker "
                       "%s)." % _mask_id(location_id)])
            return EX_STOP
        rc = verify_live(modules, location_id, contract,
                         execute=True,
                         out=sys.stderr)
        if rc == EX_OK:
            write_pending(_pending_payload("verify", location_id),
                          mode="verify")
        return rc

    except reg.ScopeDenied as exc:
        sys.stderr.write("[build-anthology-forms] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[build-anthology-forms] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[build-anthology-forms] HELD: %s\n" % exc)
        return EX_HELD
    except reg.InternalRailUnavailable as exc:
        sys.stderr.write("[build-anthology-forms] HELD (internal rail): %s\n" % exc)
        return EX_HELD
    except AssembleError as exc:
        sys.stderr.write("[build-anthology-forms] STOP/FAIL: %s\n" % exc)
        return EX_STOP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[build-anthology-forms] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
