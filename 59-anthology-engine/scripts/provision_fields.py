#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: provision_fields.py  (U07 tooling)
# LIVE FIELD-MAP COMPLIANCE DISPATCHER — the ONE CLI ASSEMBLED from the
# u07_modules files: it imports EVERY module under scripts/u07_modules/ BY
# NAME (importlib, never exec'd from a path) and wires them into ONE CLI
# whose offline self-test battery (the golden all-28-present census PASS, the
# missing-14 attack REFUSED, the TEXT-drift attack REFUSED) runs before any
# live surface. This file carries NO check logic itself — a check family is
# exercised ONLY through its module so `--dry-run`, `--self-test`, and the
# live aggregate never drift apart. It is the packaged sibling of
# scripts/live_verify_template.py (U02, row 54), scripts/check_pipeline_name.py
# (U03, row 55), scripts/fix_intake_form.py (U04, row 56),
# scripts/check_intake_fire_scope.py (U05, row 57) and
# scripts/archive_legacy_workflows.py (U06, row 58) under the
# ENGINE-MANIFEST row-54 shipping doctrine; its OWN manifest row is staged
# manifest-pending/u07.json (PENDING — the U07 manifest row is stamped by
# this assembly, exactly as the U06 row was stamped by
# archive_legacy_workflows.py).
#
# THE u07_modules FILES (imported by name; each is STDLIB-only and
# self-tests itself — docs_u07.py carries the module inventory as data and
# its self-test proves the tree ships together). The family's FIXED roster:
#   __init__.py            fail-closed EMPTY package init (pure namespace)
#   main_skeleton.py       the U07 live field-map compliance dispatcher CLI
#                          (plan / self-test / live verify; the ONE
#                          entry-point contract over the check modules)
#   fieldmap_loader.py     the FAIL-CLOSED FIELD-MAP LOADER AND CONTRACT
#                          GATE — the single implementation of the
#                          field-map.json load-and-verify law (read
#                          config/field-map.json and return its
#                          provisioning.fields inventory — exactly 28 keys —
#                          ONLY when the map satisfies its own contract;
#                          refuse anything else, never a partial load;
#                          OFFLINE, READ-ONLY, NETWORK-FREE)
#   live_fields_reader.py  the LIVE CUSTOM-FIELDS READER — the read surface
#                          of the U07 family: the location's contact custom
#                          fields through the PROVEN public rail GET
#                          /locations/{locationId}/customFields
#                          (reg.CafClient.list_custom_fields — the
#                          W0.5-verified surface). READ-ONLY BY
#                          CONSTRUCTION: no write surface and no ACTION
#                          verb, so no --execute exists (nothing to gate)
#   missing_finder.py      the MISSING-FIELD FINDER — the get-check-by-name
#                          half of the presence law (PRESENT / MISSING /
#                          NAME-SQUAT DRIFT); with the operator's explicit
#                          --execute (Trevor-gated) it CREATES each missing
#                          field by name via the proven create surface and
#                          reads the server-returned fieldKey back
#                          byte-for-byte against the intended key; without
#                          --execute a location with missing fields is a
#                          STOP (exit 2) that lists them
#   type_checker.py        the LIVE FIELD-TYPE CHECKER — the type-law half:
#                          every free-text key live LARGE_TEXT (the 27-key
#                          multi-line law) and the ONE SINGLE_OPTIONS
#                          choice field live with exactly the four named
#                          cover styles byte-exact in order; with --execute
#                          (Trevor-gated) missing keys are created at their
#                          declared types then RE-LISTED and re-verified; a
#                          live field of the WRONG type is never re-created
#                          and never re-typed — it is a FAIL (exit 5)
#   byte_verifier.py       the POST-CREATE READ-BACK VERIFIER — re-reads
#                          the location's custom-field inventory through
#                          the SAME live read the create used and confirms
#                          EVERY server fieldKey byte-exact against
#                          config/field-map.json provisioning.fields; the
#                          verify ACTION is Trevor-gated (--execute) and
#                          READ-ONLY (with it the ACTION is reported and
#                          nothing is mutated); a missing / mismatched /
#                          extra key is a MISMATCH (exit 5), an unreadable
#                          Convert and Flow is HELD (exit 3)
#   golden_all_present.py  the GOLDEN ALL-28-PRESENT FIXTURE — the
#                          canonical in-memory payload of the U07
#                          FIELD-CENSUS law in its GOLDEN state: ALL 28
#                          contract custom fields on the listing BY EXACT
#                          KEY (the intended keys read ONCE from
#                          config/field-map.json through
#                          reg.load_field_map, never retyped); the
#                          canonical record is mappingproxy-frozen; the
#                          payload() gate is fail-closed — an absent /
#                          renamed / duplicated / foreign / wrong-size /
#                          malformed / credential-shaped listing is REFUSED
#                          exit 5 (FIELDS-NOT-ALL-PRESENT), never a blind
#                          pass, and the WRITE ACTION (provision) is
#                          --execute-gated (GOLDEN_EXECUTE_REQUIRED — the
#                          gate lives in this dispatcher, never in a
#                          fixture)
#   attack_missing_14.py   the U07 ATTACK #1: a deterministic DEEP strict-
#                          subset customFields read carrying only FOURTEEN
#                          of the twenty-eight contract fields (the
#                          canonical census minus its fourteen
#                          even-positioned records) that every byte-exact
#                          field census MUST DETECT and refuse (the judge
#                          verify_live(...) FAILs the 14-key read with exit
#                          5, missing keys by MASKED MARKER only) while the
#                          golden 28-key control (payload_true) PASSES exit
#                          0 — the pass/fail split discriminates the
#                          deep-strict-subset boundary, never a broken
#                          instrument
#   attack_text_drift.py   the U07 ATTACK #2: a deterministic SINGLE-
#                          VARIABLE dataType drift — the canonical field
#                          inventory read once from the field-map (the
#                          dataType LAW surface: 28 keys, 27 LARGE_TEXT + 1
#                          SINGLE_OPTIONS, the cover choice with its four
#                          named options), then the ONE data_type of the
#                          first free-text key re-declared TEXT with every
#                          other field byte-for-byte preserved — that every
#                          dataType gate (the 27+1 invariant, the
#                          provision-fields exact-match verify, every U07
#                          type law) MUST FAIL, never a pass; the golden
#                          27+1 control (payload_true / GOLDEN_RECORD)
#                          PASSES exit 0 — the pass/fail split
#                          discriminates the TEXT-vs-LARGE_TEXT boundary,
#                          never a broken instrument
#   house_rules.py         the ONE canonical house-law constant surface
#                          (browser UA / version header / the AF autofail
#                          table mirrored from docs_u07.AF_CODES plus the
#                          shared rows pinned against ENGINE-MANIFEST.json)
#   docs_u07.py            the U07 tooling README/catalog data + drift gate
#                          (the module inventory as DATA)
#   example_usage.py       the fail-closed WORKED EXAMPLE of the U07
#                          dispatch (the field-map contract gate + the
#                          golden all-present census + the missing-14
#                          attack boundary + the live read + the
#                          missing-field presence law + the type law)
#   test_missing_finder.py the independent pytest battery over the
#                          missing-finder (provenance only)
#   test_type_checker.py   the independent pytest battery over the
#                          type-checker (provenance only)
#   test_byte_verifier.py  the independent pytest battery over the
#                          byte-verifier (provenance only)
# (the assembly manifests — main_skeleton.U07_MODULES and docs_u07.MODULES —
# carry this exact roster; the self-test pins the tree ships together.)
#
# THE U07 ATTACKS (the offline self-test proves both are REFUSED — golden
# PASS / attack FAIL; a tamper NEVER masquerades as exit 1):
#   attack_missing_14 — the 14-of-28 deep strict-subset census MUST FAIL
#                       the byte-exact field census judge (verify_live exit
#                       5, missing keys by MASKED MARKER only) while the
#                       golden 28-key control (payload_true) PASSES exit 0
#                       — the pass/fail split discriminates the deep-strict-
#                       subset boundary, never a broken instrument.
#   attack_text_drift — the one-TEXT-drift inventory MUST FAIL the byte-
#                       exact dataType law (verify_inventory exit 5, the
#                       drifted key by masked marker) while the golden 27+1
#                       control (GOLDEN_RECORD, payload_true) PASSES exit 0
#                       — the pass/fail split discriminates the TEXT-vs-
#                       LARGE_TEXT boundary, never a broken instrument.
#
# WHAT THIS VERIFIES (MASTER-SPEC U07 — the LIVE FIELD-MAP COMPLIANCE LAW
# of the anthology engine: every one of the field-map's 28 contact custom
# fields must be present on the Convert and Flow location by byte-exact
# derived key at its byte-exact declared data type — 27 LARGE_TEXT free-
# text fields plus the ONE SINGLE_OPTIONS cover-choice field carrying
# exactly the four named cover styles in order — and CREATION is the
# Trevor-gated --execute ACTION of the family). The dispatcher's live
# gates run in the FIXED order main_skeleton.LIVE_GATES carries them; the
# per-item claims live in the modules and in docs_u07.VERIFY_ITEMS:
#   1. THE 28-KEY CENSUS LAW — the field-map contract loads byte-exact
#      (fieldmap_loader.load_command over the committed
#      config/field-map.json — OFFLINE, pure; the 28-key count,
#      provisioning.total_keys byte-match, the derivation law via
#      reg.derive_field_key, the type law — 27 LARGE_TEXT + 1
#      SINGLE_OPTIONS with the four named cover styles in order — and the
#      'contact.' key law; a map that drifted from its own contract is a
#      STOP (exit 2, FieldMapError), never a blind load).
#   2. THE ALL-PRESENT LAW — the golden ALL-28-PRESENT census (golden_
#      all_present payload gate: the canonical 28-row listing where every
#      contract key is present BY EXACT KEY with its one synthetic id —
#      an absent, renamed, duplicated, or foreign contract key is a FAIL,
#      exit 5, FIELDS-NOT-ALL-PRESENT, never a blind pass).
#   3. THE ATTACK BOUNDARIES — the missing-14 deep strict subset MUST fail
#      the census judge (exit 5) with the golden 28-key control PASSING
#      exit 0, and the one-TEXT-drift inventory MUST fail the byte-exact
#      dataType law (exit 5) with the golden 27+1 control PASSING exit 0 —
#      the pass/fail splits discriminate the boundaries, never a broken
#      instrument.
#   4. THE LIVE-READ LAW — the census is read LIVE through the PROVEN
#      public rail GET /locations/{locationId}/customFields (live_fields_
#      reader.live_list_command — the ONE PIT-gated live read; an EMPTY
#      field set is a truthful PASS, a malformed read is HELD, exit 3).
#   5. THE MISSING-FIELD PRESENCE LAW — every intended key present live by
#      byte-exact derived key against the same field-map (missing_finder.
#      run_check — without --execute a location with missing fields is a
#      STOP, exit 2, that lists them; name-squat drift is a MISMATCH,
#      exit 5, never created, with or without --execute).
#   6. THE TYPE LAW — every free-text key live LARGE_TEXT and the ONE
#      SINGLE_OPTIONS choice field live with exactly the four named cover
#      styles byte-exact in order (type_checker.verify_live — a live field
#      of the WRONG type is never re-created and never re-typed: it is a
#      FAIL, exit 5, never a silent pass).
#   7. THE POST-CREATE READ-BACK — the SAME live read the create used,
#      re-read and confirmed byte-exact against the field-map
#      (byte_verifier.verify — the verify ACTION is Trevor-gated,
#      --execute; a missing / mismatched / extra key is a MISMATCH, exit
#      5, an unreadable Convert and Flow is HELD, exit 3).
#
# CREATION IS TREVOR-GATED HERE. The dispatcher NEVER creates a field
# without --execute: the CLI's `create` subcommand refuses up front (exit
# 2, AF-AE-U07-CREATE-NO-EXECUTE) unless --execute was passed explicitly,
# and even then creation is create-only-missing with a byte-exact read-
# back — a field already present live is verified, never re-created; a
# created fieldKey that is not byte-equal is a MISMATCH (exit 5,
# AF-AE-FIELD-KEY-MISMATCH family). The no-execute law is proven REFUSED
# by the offline self-test (the create-capable modules' own batteries
# assert the module-level no-execute STOP, exit 2, against synthetic
# missing-field locations; the dispatcher's own CLI probe refuses `create`
# without --execute verbatim). The assembler itself carries NO write
# surface.
#
# THE ONE LIVE READ IS PIT-GATED; THE TOOLING SHIPS NOW (manifest row
# doctrine). The operator executes `verify` only from a session that can
# resolve the client's OWN location-scoped private-integration token BY
# LABEL (CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_API_KEY /
# GOHIGHLEVEL_API_KEY / GOHIGHLEVEL_PIT / GHL_API_KEY — live process env
# first, then the three canonical client env stores) and the location id
# through reg.resolve_location (CONVERT_AND_FLOW_LOCATION_ID /
# GOHIGHLEVEL_LOCATION_ID / GHL_LOCATION_ID) unless --location-id
# overrides. --dry-run (offline plan) and --self-test (offline, no token,
# no network) always work. The offline gates (the field-map contract gate,
# the golden all-present census, the missing-14 and TEXT-drift attack
# boundaries) are exercised with their own golden surfaces and NEVER
# require a credential — and the aggregate still refuses up front without
# a PIT (the live reads are PIT-gated and no gate is ever skipped).
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. A token value is NEVER printed,
# and the location / field ids are masked on every surface
# (reg._mask_location / the modules' last-4 markers — the house shape).
#
# BROWSER UA: every request rides reg.CafClient, which applies
# CAF_BROWSER_UA on every request so the Cloudflare edge fronting
# services.leadconnectorhq.com never 1010s a verify request (CF 1010 /
# GK-09 discipline — the house pattern ported byte-for-byte from the U02 /
# U03 / U04 / U05 / U06 families and the podcast gate). Scope-vs-edge-block
# discrimination: a bare 401/403 is HELD (UpstreamBlockedError /
# CafUnreachable), never mislabeled as a scope problem.
#
# AF CODES (fail-closed surfaces; self-test failures are exit 4, never 1;
# the family is staged under manifest-pending/u07.json, its OWN manifest
# row stamped by this assembly):
#   AF-AE-U07-ASSEMBLY-INCOMPLETE -> the U07 check-module set named in the
#          assembly roster is not fully present, or a module violates the
#          one-entry-point self_test contract. STOP (exit 2) — a check
#          family is never silently skipped.
#   AF-AE-U07-CREATE-NO-EXECUTE  -> a CREATE ACTION was requested without
#          --execute (the Trevor gate). STOP (exit 2) — creation is never
#          silent; the missing-field list is the payload, the create is
#          the gate.
#   AF-AE-FIELDMAP-*            -> the field-map contract gate refused
#          (28-key count / total_keys mismatch / derivation law / type
#          law / key law). STOP (exit 2, FieldMapError) — never a silent
#          load.
#   FIELDS-ALL-PRESENT          -> the golden all-present census gate
#          PASSED (golden_all_present payload; the U07 all-present state
#          holds, exit 0).
#   FIELDS-NOT-ALL-PRESENT      -> the census gate REFUSED (golden_all_
#          present payload: an absent / renamed / duplicated / foreign /
#          wrong-size / malformed listing). exit 5, never a blind pass.
#   AF-AE-FIELD-MISSING         -> an intended field is absent from the
#          live listing (missing_finder; without --execute a STOP exit 2
#          that lists them, never a silent pass); the deep strict-subset
#          census (attack_missing_14: fourteen of twenty-eight fields
#          present) MUST be detected and refused exit 5, never passed.
#   AF-AE-FIELD-KEY-MISMATCH    -> a live field name carries a non-derived
#          key (name-squat drift, human-fix, never created) or a created
#          fieldKey read back NOT byte-equal to its intended key. exit 5
#          (MISMATCH family).
#   AF-AE-GOLDENALLPRESENT-*    -> an attack tripped the all-present
#          fixture's OFFLINE self-test (enforced violation). exit 4.
#   AF-AE-MISSINGFINDER-*       -> an attack tripped the missing-finder's
#          OFFLINE self-test (enforced violation). exit 4.
#   AF-AE-READBACK-MISMATCH     -> a post-write read-back does not prove
#          the fix byte-for-byte (shared house code). exit 5.
#   AF-AE-TEMPLATE-ATTACK       -> an attack fixture tripped the OFFLINE
#          self-test (also the family self-test batteries). exit 4.
#
# EXIT CODES (house convention 0/1/2/3/5; 4 = enforced violation; the
# primary surface the operator consumes is 0 = PASS, 2 = STOP, 5 = mismatch):
#   0  all checks PASS (also --dry-run plan pass and self-test pass; an
#      EMPTY custom-field set is a truthful PASS; nothing missing is a
#      clean no-op PASS)
#   1  unexpected error
#   2  STOP refusal — a CREATE ACTION without --execute (the Trevor gate,
#      AF-AE-U07-CREATE-NO-EXECUTE) / label NOT SET / a non-pit- value /
#      usage / the U07 check-module assembly incomplete
#      (AF-AE-U07-ASSEMBLY-INCOMPLETE) / a field-map that drifted from
#      its own contract (FieldMapError: 28-key count, total_keys
#      mismatch, derivation law, type law, key law — never a silent load)
#      / a map-vs-cover_render options mismatch / the cover_render style
#      import failed / a missing field WITHOUT --execute (the Trevor gate,
#      AF-AE-FIELD-MISSING family — creation is never silent) / a GENUINE
#      scope denial (the response body matched the Convert and Flow scope
#      signature) / a module STOP-family refusal
#   3  HELD — Convert and Flow unreachable (transport) or an upstream/edge
#      block (CF error 1010, Cloudflare edge 403) / a malformed listing
#      (UNDETERMINED, never a verdict — a bare 401/403 is HELD, never
#      mislabeled as a scope problem)
#   4  self-test FAILED — an assertion in the OFFLINE self-test tripped
#      (AF-AE-FIELDMAP-* / AF-AE-GOLDENALLPRESENT-* / AF-AE-MISSINGFINDER-*
#      / AF-AE-FIELD-MISSING / AF-AE-FIELD-KEY-MISMATCH /
#      AF-AE-TEMPLATE-ATTACK family). A tamper NEVER masquerades as exit 1.
#   5  data or read-back mismatch (a contract key absent or renamed —
#      FIELDS-NOT-ALL-PRESENT — a foreign key outside the 28-key contract,
#      a wrong-size or malformed census, a credential-shaped or full-id
#      surface (leak-scan REFUSAL), a name-squat drift, a created fieldKey
#      that is not byte-equal to its intended key, a live field of the
#      wrong dataType (not LARGE_TEXT / not SINGLE_OPTIONS / drifted
#      options), a read-back mismatch; the fail-closed default)
#
# MANIFEST-PENDING: after a PASSING run the tool writes
# manifest-pending/u07.json — the staged U07 manifest artifact (contract,
# checks verdict, the module inventory, af-code family, exit-code
# contract, provenance) — so the manifest can be re-stamped from a
# machine-readable record once the operator approves. The write is
# fail-closed: it happens ONLY on a PASS (self-test pass or dry-run plan
# pass); a FAIL/HELD/STOP run writes nothing and removes nothing. The
# ENGINE-MANIFEST.json / ENGINE-PIN.sha256 / verify.sh are NEVER touched
# here.
#
# STDLIB ONLY (urllib + json via the registry and the check modules); calls
# NO model. DOCTRINE: move in silence; NOTHING Anthropic in any runtime
# file; Convert and Flow naming in every client surface; NEVER print a
# secret value; --dry-run and --self-test are OFFLINE; a CREATE ACTION
# requires --execute (Trevor-gated) and is create-only-missing with a
# byte-exact read-back — never a silent write.
# =============================================================================
"""provision_fields.py — the U07 live field-map compliance dispatcher
assembled from the u07_modules files: one CLI, offline self-test battery
(golden all-present PASS, the missing-14 and TEXT-drift attacks REFUSED),
JSON output, and the manifest-pending/u07.json stage (Skill 59)."""

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
# Cloudflare browser-UA wiring + the LeadConnector client and its label
# resolution is the house credential contract.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent
MODULES_DIR = Path(__file__).resolve().parent / "u07_modules"
CONTRACT_PATH = SKILL_DIR / "config" / "field-map.json"
PENDING_DIR = SKILL_DIR / "manifest-pending"
PENDING_U07 = PENDING_DIR / "u07.json"

# The template location id is the CONTRACT pin (the operator's OWN template
# location, operator infrastructure config, not a secret). The dispatcher
# pins to it; --location-id overrides for tests.
DEFAULT_TEMPLATE_LOCATION = "2HIKGNgsixWx0yds7Qnx"

# THE u07_modules FILES — the assembly manifest for this dispatcher.
# Every name is imported BY NAME below (importlib), never exec'd from a
# path; a missing module is a STOP, never a silent skip (the fail-closed
# import contract of main_skeleton.load_modules). `role` is the one-line
# contract each module owns. The names mirror the files on disk one-to-one
# (the catalog and the tree never drift; the self-test pins the roster).
U07_MODULES = (
    ("__init__.py",            "fail-closed EMPTY package init (pure namespace)"),
    ("main_skeleton.py",       "the U07 live field-map compliance dispatcher CLI (plan / self-test / live verify; the ONE entry-point contract over the check modules)"),
    ("fieldmap_loader.py",     "the FAIL-CLOSED FIELD-MAP LOADER AND CONTRACT GATE — the single implementation of the field-map.json load-and-verify law: read config/field-map.json and return its provisioning.fields inventory (exactly 28 keys) ONLY when the map satisfies its own contract (28-key count, total_keys byte-match, derivation law, type law — 27 LARGE_TEXT + 1 SINGLE_OPTIONS — key law with the 'contact.' prefix) — refuse anything else (FieldMapError, exit 2 STOP family), never a partial load. OFFLINE, READ-ONLY, NETWORK-FREE; a field id is reported by status only (RESOLVED / UNRESOLVED), never by value"),
    ("live_fields_reader.py",  "the LIVE CUSTOM-FIELDS READER — the read surface of the U07 family: the location's contact custom fields through the PROVEN public rail GET /locations/{locationId}/customFields (reg.CafClient.list_custom_fields — the W0.5-verified surface the U02 fields_check gate and the provision path exercise). READ-ONLY BY CONSTRUCTION: no write surface, no ACTION verb, no --execute (nothing to gate). An EMPTY field set is a truthful PASS; a missing credential is a STOP (exit 2); an unreachable rail / edge block / unparseable listing is HELD (exit 3), never a fabricated list"),
    ("missing_finder.py",      "the MISSING-FIELD FINDER — the get-check-by-name half of the presence law: PRESENT (byte-equal server fieldKey) / MISSING (no live field under the derived key AND no live field under the create name) / NAME-SQUAT DRIFT (a live field named exactly the create_name but keyed otherwise — a human-fix drift, NEVER counted missing, NEVER created). With the operator's explicit --execute (Trevor-gated) it CREATES each missing field by name via the proven create surface (reg.CafClient.create_custom_field) and reads the server-returned fieldKey back byte-for-byte against the intended key — idempotent create-or-verify; a created fieldKey NOT byte-equal is a MISMATCH (exit 5). Without --execute a location with missing fields is a STOP (exit 2) that lists them — creation is never silent"),
    ("type_checker.py",        "the LIVE FIELD-TYPE CHECKER — the type-law half of the U07 family: asserts EVERY free-text field in the inventory is live LARGE_TEXT (the 27-key every-text-input-field-is-multi-line law, PRD Gap G11) and the ONE SINGLE_OPTIONS field (contact.anthology_cover_choice) is live with EXACTLY the four named cover-style options byte-exact in order (the picklist imported from cover_render.STYLE_NAMES, self-pinned against the field-map's own declared options so the two surfaces can never drift). With --execute (Trevor-gated) each MISSING free-text key is created at its declared LARGE_TEXT data_type and the choice field at SINGLE_OPTIONS with the four options, then the location is RE-LISTED and every created key re-verified against the read-back — a report never claims a type that was not read back. A live field of the WRONG type is NEVER re-created and never re-typed: it is a FAIL (exit 5)"),
    ("byte_verifier.py",       "the POST-CREATE READ-BACK VERIFIER — the read-back half of the U07 create law: after provisioning creates a custom field, RE-READS the location's custom-field inventory through the SAME live read surface the create used (reg.CafClient.list_custom_fields, browser UA on every request) and confirms EVERY server fieldKey byte-exact against config/field-map.json provisioning.fields (the SINGLE SOURCE OF TRUTH; each expectation derived through reg.derive_field_key, the single implementation). READ-ONLY by construction: it never creates, never stamps, never writes; the verify ACTION is Trevor-gated (--execute) — without it a STOP (exit 2, the family gate), with it the ACTION is reported and nothing is mutated; a missing / mismatched / extra key is a MISMATCH (exit 5), an unreadable Convert and Flow is HELD (exit 3)"),
    ("golden_all_present.py",  "the GOLDEN ALL-28-PRESENT FIXTURE — the canonical in-memory payload of the U07 FIELD-CENSUS law in its GOLDEN state: ALL 28 contract custom fields on the listing BY EXACT KEY (the 19 base PRD Section 6 link/control keys + 4 Gap G10 chapter-rewrite-preservation keys + 5 U8 cover-style keys, the intended keys read ONCE from config/field-map.json through reg.load_field_map, never retyped), the canonical record mappingproxy-frozen (every container a tuple, so no caller can mutate the law); the payload() gate is fail-closed — an absent / renamed / duplicated / foreign / wrong-size / malformed / credential-shaped listing is REFUSED exit 5 (FIELDS-NOT-ALL-PRESENT), never a blind pass, and the WRITE ACTION (provision) is --execute-gated (GOLDEN_EXECUTE_REQUIRED — the gate lives in this dispatcher, never in a fixture)"),
    ("attack_missing_14.py",   "the U07 ATTACK #1: a deterministic DEEP strict-subset customFields read carrying only FOURTEEN of the twenty-eight contract fields (the canonical census minus its fourteen even-positioned records — a location missing half its fields) that every byte-exact field census MUST DETECT and refuse (verify_live(...) exit 5, missing keys by MASKED MARKER only) while the golden 28-key control (payload_true) PASSES exit 0 — the pass/fail split discriminates the deep-strict-subset boundary, never a broken instrument. READ-ONLY and OFFLINE by construction: it never makes a network call"),
    ("attack_text_drift.py",   "the U07 ATTACK #2: a deterministic SINGLE-VARIABLE dataType drift — the canonical field inventory read once from the field-map (the dataType LAW surface: 28 keys, 27 LARGE_TEXT + 1 SINGLE_OPTIONS, the cover choice with its four named options), then the ONE data_type of the first free-text key re-declared TEXT with every other field byte-for-byte preserved — that every dataType gate (the 27+1 invariant, the provision-fields exact-match verify, every U07 type law) MUST FAIL, never a pass; the golden 27+1 control (GOLDEN_RECORD / payload_true) PASSES exit 0 — the pass/fail split discriminates the TEXT-vs-LARGE_TEXT boundary, never a broken instrument. READ-ONLY and OFFLINE by construction: it never makes a network call"),
    ("house_rules.py",         "the ONE canonical house-law constant surface for the U07 family (browser UA — CAF_BROWSER_UA, CF 1010 — / version header — CAF_VERSION_HEADER — / the complete AF autofail table, the manifest's 37 rows, the U07 family's authority); the offline self-test pins the UA and version header byte-exact against the registry and the AF table byte-exact against ENGINE-MANIFEST.json autofails — a tamper never masquerades as exit 1 (exit 4, the AF-AE-HASH-PIN family)"),
    ("docs_u07.py",            "the U07 tooling README/catalog data + drift gate — the module inventory, the FIVE verified items, the house exit codes and af codes as DATA (the module inventory and the shipped tree never drift; a doc that names a module that does not ship FAILS its self-test exit 4)"),
    ("example_usage.py",       "the fail-closed WORKED EXAMPLE of the U07 dispatch — the field-map contract gate + the golden all-present census + the missing-14 attack boundary with its golden control + the live read + the missing-field presence law + the type law, composed in the documented order with every sibling exit code honored verbatim (a STOP refusal is NEVER downgraded to a pass). NOT a gate and NOT a checker: it makes NO judgment of its own — every judgment is delegated to the sibling modules, which stay the single implementation of each law"),
    ("test_missing_finder.py", "the independent pytest battery over the missing-finder (provenance only)"),
    ("test_type_checker.py",   "the independent pytest battery over the type-checker (provenance only)"),
    ("test_byte_verifier.py",  "the independent pytest battery over the byte-verifier (provenance only)"),
)

# The modules the dispatcher aggregates (main_skeleton.U07_MODULES — the
# check-module set named in the dispatcher's own roster; a check family
# that cannot prove itself offline STOPS).
DISPATCH_MODULE_NAMES = tuple(name for name, _ in (
    ("fieldmap_loader", "the FAIL-CLOSED FIELD-MAP LOADER AND CONTRACT GATE — the single implementation of the field-map.json load-and-verify law (28-key count, total_keys byte-match, derivation law, type law, key law); OFFLINE, READ-ONLY, NETWORK-FREE"),
    ("live_fields_reader", "the LIVE CUSTOM-FIELDS READER — the read surface of the U07 family (GET /locations/{id}/customFields on the PROVEN public rail; READ-ONLY BY CONSTRUCTION; an EMPTY field set is a truthful PASS, a malformed read is HELD)"),
    ("missing_finder", "the MISSING-FIELD FINDER — PRESENT / MISSING / NAME-SQUAT DRIFT against the byte-exact derived keys; with --execute (Trevor-gated) create-only-missing with a byte-exact read-back; without it a location with missing fields STOPS (exit 2) that lists them"),
    ("type_checker", "the LIVE FIELD-TYPE CHECKER — 27 LARGE_TEXT + the ONE SINGLE_OPTIONS choice field with the four named styles byte-exact in order; a wrong-type live field is a FAIL (exit 5), never re-created, never re-typed"),
    ("byte_verifier", "the POST-CREATE READ-BACK VERIFIER — the SAME live read the create used, re-read and confirmed byte-exact against the field-map; the verify ACTION is Trevor-gated (--execute) and READ-ONLY"),
    ("golden_all_present", "the GOLDEN ALL-28-PRESENT FIXTURE — ALL 28 contract custom fields present byte-exact by the golden keys (mappingproxy-frozen; payload() judges fail-closed, exit 0 pass / 5 refused; the WRITE ACTION is --execute-gated)"),
    ("attack_missing_14", "the U07 ATTACK #1 — the 14-of-28 deep strict-subset census that every byte-exact field census MUST DETECT and refuse (exit 5, missing keys by masked marker) with the golden 28-key control PASSING"),
    ("attack_text_drift", "the U07 ATTACK #2 — the one-TEXT-drift inventory that every byte-exact dataType gate MUST FAIL (exit 5) with the golden 27+1 control PASSING"),
    ("house_rules", "the ONE canonical house-law constant surface (browser UA, version header, the AF autofail table mirrored from docs_u07.AF_CODES)"),
    ("docs_u07", "the U07 tooling README/catalog data + drift gate (the module inventory as DATA)"),
    ("example_usage", "the fail-closed WORKED EXAMPLE of the U07 dispatch (delegates every judgment to the sibling modules)"),
))

# The modules that ship their OWN offline self-test battery (golden PASS /
# attack FAIL, exit 0 pass / 4 enforced violation). Every check module ships
# a battery — the dispatcher REQUIRES a battery from every module. The three
# pytest batteries are imported for their provenance; their tests run as the
# independent pytest battery.
SELF_TEST_MODULES = tuple(
    name[:-3] for name, _ in U07_MODULES
    if name not in ("__init__.py", "test_missing_finder.py",
                    "test_type_checker.py", "test_byte_verifier.py",
                    "main_skeleton.py"))
TEST_MODULES = ("test_missing_finder", "test_type_checker",
                "test_byte_verifier")

# The live-verify gate order — the dispatcher's fixed order (mirrors
# main_skeleton.LIVE_GATES one-to-one; the self-test pins the two cannot
# drift).
LIVE_GATES = tuple(name for name, _ in (
    ("fieldmap_loader", "the field-map contract gate — load-and-verify config/field-map.json (the SINGLE SOURCE OF TRUTH) against its own 28-key contract; a map that drifted is a STOP, never a blind load"),
    ("golden_all_present", "the golden all-present census — ALL 28 contract fields present byte-exact by the golden keys (an absent / renamed / duplicated / foreign key is a FAIL, exit 5, never a blind pass)"),
    ("attack_missing_14", "the attack boundary #1 — the 14-of-28 deep strict-subset census MUST fail the byte-exact census judge (exit 5) while the golden 28-key control PASSES exit 0"),
    ("attack_text_drift", "the attack boundary #2 — the one-TEXT-drift inventory MUST fail the byte-exact dataType law (exit 5) while the golden 27+1 control PASSES exit 0"),
    ("live_fields_reader", "the live custom-field read — the location's contact custom fields through the PROVEN public rail GET /locations/{id}/customFields (PIT-gated; an EMPTY field set is a truthful PASS, a malformed read is HELD)"),
    ("missing_finder", "the missing-field presence law — every intended key present live by byte-exact derived key against the same field-map (missing without --execute is a STOP that lists them; name-squat drift is a MISMATCH, exit 5, never created)"),
    ("type_checker", "the live type law — every free-text key live LARGE_TEXT and the ONE SINGLE_OPTIONS choice field live with exactly the four named cover styles byte-exact in order (a wrong-type live field is a FAIL, exit 5, never a silent pass)"),
    ("byte_verifier", "the post-create read-back — the SAME live read the create used, re-read and confirmed byte-exact against the field-map (the verify ACTION is Trevor-gated, --execute; a missing / mismatched / extra key is a MISMATCH, exit 5)"),
))

# The five U07 verified items, as the manifest-pending stage records them
# (docs_u07.VERIFY_ITEMS — the catalog and the tree never drift).
VERIFIED_ITEMS = (
    (1, "census_law", "28-key census law — the field-map contract loads "
                      "byte-exact"),
    (2, "all_present", "All-present law — the golden 28 are present BY "
                       "EXACT KEY"),
    (3, "live_read", "Live-read law — the census is read LIVE through the "
                     "PROVEN rail"),
    (4, "create_gate", "Create gate law — a missing field STOPS without "
                       "--execute"),
    (5, "type_law", "Type law — every free-text key live LARGE_TEXT, the "
                    "choice field exact"),
)

# The AF-AE autofail family, as the stage records it (mirrored from
# docs_u07.AF_CODES — the family authority).
AF_CODES = (
    ("AF-AE-U07-ASSEMBLY-INCOMPLETE", 2,
     "the U07 check-module set named in U07_MODULES is not fully present, "
     "or a module violates the one-entry-point self_test contract — a "
     "check family is never silently skipped (dispatcher STOP)"),
    ("AF-AE-U07-CREATE-NO-EXECUTE", 2,
     "a CREATE ACTION was requested without --execute (the Trevor gate) — "
     "creation is never silent; the missing-field list is the payload, the "
     "create is the gate"),
    ("AF-AE-FIELDMAP-*", 2,
     "the field-map contract gate refused (28-key count / total_keys "
     "mismatch / derivation law / type law / key law — never a silent "
     "load); an attack tripped the loader's OFFLINE self-test (exit 4)"),
    ("FIELDS-ALL-PRESENT", 0,
     "the golden all-present census gate PASSED (golden_all_present "
     "payload; the U07 all-present state holds)"),
    ("FIELDS-NOT-ALL-PRESENT", 5,
     "the census gate REFUSED (golden_all_present payload: an absent / "
     "renamed / duplicated / foreign / wrong-size / malformed listing — "
     "never a blind pass)"),
    ("AF-AE-FIELD-MISSING", 2,
     "an intended field is absent from the live listing (missing_finder; "
     "without --execute a STOP exit 2 that lists them, never a silent "
     "pass); the deep strict-subset census (attack_missing_14: fourteen "
     "of twenty-eight fields present) MUST be detected and refused exit "
     "5, never passed"),
    ("AF-AE-FIELD-KEY-MISMATCH", 5,
     "a live field name carries a non-derived key (name-squat drift, "
     "human-fix, never created) or a created fieldKey read back NOT "
     "byte-equal to its intended key — the derivation law changed or the "
     "server drifted, and NOTHING about that key is certified"),
    ("AF-AE-GOLDENALLPRESENT-*", 4,
     "an attack tripped the all-present fixture's OFFLINE self-test "
     "(enforced violation) — an absent / renamed / duplicate / foreign "
     "contract key, a wrong-size or malformed census, or a credential-"
     "shaped value was not refused HERE first"),
    ("AF-AE-MISSINGFINDER-*", 4,
     "an attack tripped the missing-finder's OFFLINE self-test (enforced "
     "violation) — a drifted missing/create gate law was not caught HERE "
     "first"),
    ("AF-AE-READBACK-MISMATCH", 5,
     "a post-write read-back does not prove the fix byte-for-byte — the "
     "shared house code with the U02 / U03 / U04 / U05 / U06 families "
     "(already stamped in ENGINE-MANIFEST.json)"),
    ("AF-AE-TEMPLATE-ATTACK", 4,
     "an attack fixture tripped the OFFLINE self-test of the dispatcher "
     "or a family battery (enforced violation — the house code, shared "
     "with the U02 / U03 / U04 / U05 / U06 families)"),
)

# House exit-code contract (docs_u07.EXIT_CODES).
EXIT_CODES = {
    0: "verified success — the census agrees with its source of truth and "
       "every write step ran under its gate (also plan / self-test; an "
       "EMPTY custom-field set is a truthful PASS; nothing missing is a "
       "clean no-op PASS)",
    1: "unexpected error (top-level guard; never a secret leak)",
    2: "STOP refusal — a CREATE ACTION without --execute (the Trevor gate, "
       "AF-AE-U07-CREATE-NO-EXECUTE) / label NOT SET / a non-pit- value / "
       "usage / the U07 check-module assembly incomplete "
       "(AF-AE-U07-ASSEMBLY-INCOMPLETE) / a field-map that drifted from "
       "its own contract (FieldMapError: 28-key count, total_keys "
       "mismatch, derivation law, type law, key law — never a silent "
       "load) / a map-vs-cover_render options mismatch / the cover_render "
       "style import failed / a missing field WITHOUT --execute (the "
       "Trevor gate, AF-AE-FIELD-MISSING family — creation is never "
       "silent) / a GENUINE scope denial (the response body matched the "
       "Convert and Flow scope signature) / a module STOP-family refusal",
    3: "HELD — Convert and Flow unreachable (transport) or an "
       "upstream/edge block (CF error 1010, Cloudflare edge 403) / a "
       "malformed listing (UNDETERMINED, never a verdict — a bare 401/403 "
       "is HELD, never mislabeled as a scope problem)",
    4: "self-test FAILED (AF-AE-FIELDMAP-* / AF-AE-GOLDENALLPRESENT-* / "
       "AF-AE-MISSINGFINDER-* / AF-AE-FIELD-MISSING / AF-AE-FIELD-KEY-"
       "MISMATCH / AF-AE-TEMPLATE-ATTACK family, enforced violation) — a "
       "tamper never masquerades as exit 1",
    5: "mismatch / fail-closed default — a contract key absent or renamed "
       "(FIELDS-NOT-ALL-PRESENT), a foreign key outside the 28-key "
       "contract, a wrong-size or malformed census, a credential-shaped "
       "or full-id surface (leak-scan REFUSAL), a name-squat drift (a "
       "live name under a non-derived key), a created fieldKey that is "
       "not byte-equal to its intended key, a live field of the wrong "
       "dataType (not LARGE_TEXT / not SINGLE_OPTIONS / drifted options), "
       "a read-back mismatch; the fail-closed default",
}

class AssembleError(Exception):
    """A fail-closed refusal raised by the assembly itself — a missing
    u07_modules file, a module violating the entry-point contract, or a
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
# The file assembly — import EVERY u07_modules file BY NAME. The empty
# package init is imported for the namespace guarantee (importing the
# package succeeds only if __init__.py is intact); the check modules come
# through main_skeleton.load_modules (the ONE entry-point contract); the
# fixture / checker / docs modules are imported for their surfaces and
# their self-test batteries; the three pytest batteries are imported for
# their provenance (their tests run as the independent pytest battery).
# ---------------------------------------------------------------------------
def _load_package() -> None:
    """Prove the package namespace container imports clean."""
    importlib.import_module("u07_modules")

def load_skeleton() -> object:
    """The main_skeleton dispatcher module (imported BY NAME)."""
    return importlib.import_module("u07_modules.main_skeleton")

def load_all_modules(out=None) -> dict:
    """Import every one of the u07_modules files. Returns {name: module}.
    Fail-closed: a missing file or a module violating its contract raises
    AssembleError (STOP) — the aggregate NEVER passes with a module
    silently absent.

    The check modules go through main_skeleton.load_modules (which enforces
    the ONE-entry-point contract and raises SkeletonError on a violation);
    the fixture / checker / docs modules and the three pytest batteries are
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
            modules[name] = importlib.import_module("u07_modules." + name)
        except ImportError:
            missing.append(name)
    for name in TEST_MODULES:
        try:
            modules[name] = importlib.import_module("u07_modules." + name)
        except ImportError:
            missing.append(name)
    if missing:
        raise AssembleError(
            "u07_modules file(s) not found: %s — the assembly is "
            "incomplete (fail-closed: no module is ever skipped)"
            % ", ".join(missing))
    if len(modules) != 15:
        raise AssembleError(
            "assembly loaded %d modules, expected 15 (main_skeleton + 11 "
            "dispatch modules + 3 pytest batteries)" % len(modules))
    return modules

# ---------------------------------------------------------------------------
# Offline self-test — run EVERY module's own battery (golden all-present
# PASS, the missing-14 and TEXT-drift attacks REFUSED), plus the
# main_skeleton dispatcher battery, plus this assembler's own assembly
# assertions (including the two attack boundaries driven through the
# fixtures' OWN surfaces), plus the three sibling pytest batteries. NO
# network, NO credentials. Exit 4 on any failure.
# ---------------------------------------------------------------------------
def _module_self_test(module, name: str, out) -> None:
    st = getattr(module, "self_test", None)
    if not callable(st):
        raise AssertionError(
            "module %s does not expose 'self_test' — every u07_modules "
            "module must prove itself offline" % name)
    dev = io.StringIO()
    try:
        rc = st(out=dev)
    except TypeError:
        try:
            rc = st()
        except TypeError:
            rc = st(field_map_path=CONTRACT_PATH, out=dev)
    out.write(dev.getvalue())
    if rc != EX_OK:
        raise AssertionError("%s self_test returned exit %d" % (name, rc))

def _run_pytest(modules: dict, out) -> None:
    """The three sibling pytest batteries — the independent proof that the
    field-census family (the missing-finder + the type-checker + the
    byte-verifier) is pinned offline. A failed battery is an enforced
    violation, never a silent skip."""
    pkg = Path(modules["test_missing_finder"].__file__).resolve().parent
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
    missing-14 and TEXT-drift attacks MUST FAIL), the dispatcher battery,
    the assembly's file-count assertions, the field-census law gate (golden
    all-present PASS / missing-14 REFUSED / TEXT-drift REFUSED), and the
    sibling pytest batteries. Any failure is exit 4 (AF-AE-TEMPLATE-ATTACK
    family) — a tamper NEVER masquerades as exit 1. On a clean pass the
    manifest-pending stage is written by the CLI."""
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        # 1. the assembly is complete: exactly the U07 file set exists.
        on_disk = sorted(p.name for p in MODULES_DIR.glob("*.py"))
        expected = sorted(name for name, _ in U07_MODULES)
        assert on_disk == expected, (
            "u07_modules tree drifted: disk carries %d files, the %d-file "
            "assembly contract names %d (%s)"
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
        #     in the FIXED order the field-census law carries them).
        assert tuple(name for name, _ in skeleton.LIVE_GATES) == LIVE_GATES, \
            "the dispatcher's LIVE_GATES drifted from the assembly's order"
        # 4. the field-census law gate, exercised through the modules' own
        #    surfaces — the GOLDEN states PASS and the U07 ATTACKS FAIL
        #    (never a silent pass, never a blind refusal):
        # 4a. the golden ALL-28-PRESENT census PASSES the fail-closed payload
        #     gate (all 28 contract custom fields present byte-exact by the
        #     golden keys, read once from config/field-map.json; the WRITE
        #     ACTION — provision — is --execute-gated).
        ga = modules["golden_all_present"]
        assert ga.GOLDEN_EXECUTE_REQUIRED is True, \
            "the all-present law must assert GOLDEN_EXECUTE_REQUIRED"
        assert ga.EXECUTE_FLAG == "--execute", \
            "the Trevor gate flag drifted from the U07 contract"
        golden_result = ga.payload(None, out=io.StringIO())
        assert isinstance(golden_result, dict) and golden_result.get("ok"), \
            "the golden ALL-28-PRESENT census must pass the payload gate: %s" \
            % (golden_result.get("af_code", "?")
               if isinstance(golden_result, dict) else "?")
        assert golden_result.get("count") == 28, \
            "the golden census must carry exactly 28 rows, got %r" \
            % golden_result.get("count")
        # 4b. ATTACK #1 — the missing-14 deep strict-subset read (fourteen
        #     of the twenty-eight contract fields — the canonical census
        #     minus its fourteen even-positioned records) FAILS the byte-
        #     exact field-census judge (exit 5, missing keys by MASKED
        #     MARKER only) while the golden 28-key control PASSES — the
        #     pass/fail split discriminates the deep-strict-subset
        #     boundary, never a broken instrument. The judge consumes the
        #     fixture's OWN canonical ATTACK_FIELDS payload through the
        #     in-memory read surface the fixture ships for it.
        a14 = modules["attack_missing_14"]
        attack_list = list(a14.attack_fields())
        assert len(attack_list) == 14, \
            "the missing-14 attack must carry exactly 14 rows, got %d" \
            % len(attack_list)
        attack_rc = a14.verify_live(_ATTACK_SURFACE14(), "loc_fx",
                                    _attack_field_map(modules),
                                    out=io.StringIO())
        assert attack_rc == EX_MISMATCH, \
            "ATTACK #1 (14 of 28 fields present) was NOT refused (exit %s)" \
            % attack_rc
        control_rc = a14.payload_true(out=io.StringIO())
        assert control_rc == EX_OK, \
            "the golden 28-key control must PASS (exit %s)" % control_rc
        # 4c. ATTACK #2 — the one-TEXT-drift inventory (the canonical field
        #     inventory with the ONE data_type of the first free-text key
        #     re-declared TEXT, every other field byte-for-byte preserved)
        #     FAILS the byte-exact dataType law (exit 5, the drifted key by
        #     MASKED MARKER) while the golden 27+1 control PASSES — the
        #     pass/fail split discriminates the TEXT-vs-LARGE_TEXT
        #     boundary, never a broken instrument.
        atd = modules["attack_text_drift"]
        drift_rc = atd.verify_inventory(atd.ATTACK_RECORD,
                                        out=io.StringIO())
        assert drift_rc == EX_MISMATCH, \
            "ATTACK #2 (one TEXT drift) was NOT refused (exit %s)" % drift_rc
        control_rc = atd.verify_inventory(atd.GOLDEN_RECORD,
                                          out=io.StringIO())
        assert control_rc == EX_OK, \
            "the golden 27+1 control must PASS (exit %s)" % control_rc
        # 4d. the create gate law at the dispatcher surface: the family's
        #     own batteries (missing_finder / type_checker / byte_verifier)
        #     each assert the module-level no-execute STOP (a missing field
        #     without --execute -> exit 2, AF-AE-FIELD-MISSING family; the
        #     verifier ACTION without --execute -> exit 2) — those batteries
        #     ran in step 2 above and each pins its no-execute assertion
        #     verbatim (missing_finder._self_test_body asserts rc == EX_STOP
        #     on the no-execute run; type_checker asserts missing-field-
        #     without-execute exits 2; byte_verifier asserts an ACTION
        #     without --execute STOPS). The dispatcher's OWN CLI-surface
        #     refusal of `create` without --execute is proven separately in
        #     the skeleton's create-gate law (main_skeleton._create_gate —
        #     step 3 above ran it).
        # 5. docs_u07's catalog is the assembly's catalog (5 items, exit
        #    codes 0..5 — its self-test already pinned the counts; here we
        #    pin the shared constants).
        docs = modules["docs_u07"]
        assert len(docs.VERIFY_ITEMS) == len(VERIFIED_ITEMS), \
            "docs_u07 item count drifted from the assembly's VERIFIED_ITEMS"
        # 6. the sibling pytest batteries (the independent proof).
        if run_pytest:
            _run_pytest(modules, dev)
    except AssertionError as exc:
        sys.stderr.write("[provision-fields] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    except AssembleError as exc:
        sys.stderr.write("[provision-fields] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION

    out.write(dev.getvalue())
    out.write("[provision-fields] assembled self-test: OK (%d "
              "u07_modules files imported, 10 module batteries + dispatcher "
              "battery + field-census law gate with the missing-14 and "
              "TEXT-drift attacks REFUSED + %s + assembly assertions all "
              "pass)\n"
              % (len(U07_MODULES),
                 "3 pytest batteries" if run_pytest else
                 "pytest batteries skipped (--no-pytest)"))
    return EX_OK

class _ATTACK_SURFACE14:
    """The in-memory read surface the attack_missing_14 judge consumes —
    the fixture stays OFFLINE (the surface returns the module's canonical
    ATTACK_FIELDS payload, never a network call; reg.CafClient is the only
    thing that ever talks to Convert and Flow, and it sends CAF_BROWSER_UA
    on every request — the proven CF-1010 edge fix)."""

    def list_custom_fields(self, location_id):
        import attack_missing_14 as _attack
        return list(_attack.attack_fields())

def _attack_field_map(modules):
    """The field-map the OFFLINE attack judge judges against — the
    committed config copy read through the family's OWN loader surface
    (the fail-closed contract gate): load_field_map returns the verified
    provisioning.fields INVENTORY (the list of row dicts), so the raw map
    object is reconstructed with the verified inventory in place for the
    judges that consume the full map (field_map.get("provisioning")). A
    map that drifted from its own contract refuses the judge instead of
    shipping a wrong verdict."""
    try:
        inventory = modules["fieldmap_loader"].load_field_map(CONTRACT_PATH)
        raw = _read_json(CONTRACT_PATH, "config/field-map.json")
        raw["provisioning"]["fields"] = inventory
        return raw
    except Exception as exc:  # noqa: BLE001 — the caller STOPs on a refusal
        raise AssembleError(
            "the attack judge cannot load config/field-map.json through "
            "the family loader: %s: %s" % (type(exc).__name__, exc)) from exc

def _mask_id(fid: str) -> str:
    """Mask a field / location id for every operator surface — a tenant
    identifier, not a secret, but never printed in full (house pattern,
    mirrored from the u07 modules' own masking)."""
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
def dry_run(modules: dict, location_id: str, field_map: dict,
            out=None) -> int:
    out = out or sys.stderr
    skeleton = modules["main_skeleton"]
    # The dispatcher's own plan (the ONE JSON object on stdout, captured
    # into the human channel — the machine surface is this assembler's plan
    # object, so stdout stays ONE JSON document).
    with _redirect_stdout(io.StringIO()):
        rc = skeleton.plan(modules, location_id, field_map, out=out)
    if rc != EX_OK:
        return rc
    payload = {
        "contract": "anthology-engine-u07-dispatch-plan",
        "schema_version": 1,
        "kind": "dry-run",
        "template_location_id": location_id,
        "template_location_id_masked": _mask_id(location_id),
        "gates": list(LIVE_GATES),
        "modules": [name for name, _ in U07_MODULES],
        "dry_run": True,
        "create_gate": "a CREATE ACTION requires --execute (Trevor-gated); "
                       "without --execute missing fields are a STOP (exit 2) "
                       "that lists them — creation is never silent; even "
                       "WITH --execute creation is create-only-missing with "
                       "a byte-exact read-back",
        "note": "offline plan only — no network, no credential needed; the "
                "ONE live read (live_fields_reader) must ride the PROVEN "
                "public rail GET /locations/{id}/customFields with "
                "CAF_BROWSER_UA on every request — CF 1010 law",
    }
    dumped = json.dumps(payload, indent=2, sort_keys=True)
    if _CREDENTIAL_SHAPE.search(dumped):
        raise AssembleError(
            "plan payload carries a credential-shaped string — REFUSED "
            "without printing it")
    print(dumped)
    out.write("[provision-fields] dry-run plan: OK (offline — no "
              "network, no credential needed)\n")
    return EX_OK

# ---------------------------------------------------------------------------
# Live verify — the dispatcher's fail-closed aggregate over the gates in
# the FIXED order. Any FAIL -> exit 5; a STOP-family refusal propagates as
# exit 2; a transport / edge failure is HELD (exit 3), never mislabeled as
# scope. The offline gates (field-map contract, golden census, both attack
# boundaries) run first — their golden surfaces need no credential — then
# the ONE PIT-gated live read, then the presence / type / read-back laws.
# This assembler NEVER performs a CREATE ACTION itself — the gated ACTION
# surface is the family's create path with --execute, and this assembler's
# CLI refuses the ACTION without --execute (the Trevor gate) and passes
# the operator-gate status INTO the module surfaces (which re-prove their
# own no-execute STOPs verbatim).
# ---------------------------------------------------------------------------
def verify_live(modules: dict, location_id: str, field_map: dict, *,
                execute: bool = False, out=None) -> int:
    out = out or sys.stderr
    skeleton = modules["main_skeleton"]
    return skeleton.verify_live(modules, location_id, field_map,
                                execute=execute, out=out)

# ---------------------------------------------------------------------------
# Manifest-pending stage — manifest-pending/u07.json. Written ONLY after a
# PASS (self-test pass or dry-run plan pass); a FAIL/HELD/STOP run writes
# nothing. The record is the machine-readable input to a later manifest
# re-stamp — the ENGINE-MANIFEST.json / ENGINE-PIN.sha256 / verify.sh are
# NEVER touched here.
# ---------------------------------------------------------------------------
def _pending_payload(kind: str, location_id: str, *,
                     verdict: str = "PASS") -> dict:
    return {
        "contract": "anthology-engine-u07-field-map-compliance",
        "schema_version": 1,
        "kind": kind,  # "self-test" | "dry-run" | "verify"
        "verdict": verdict,
        "script": "provision_fields.py",
        "authored_by": "U07",
        "template_location_id": location_id,
        "u07_modules": [
            {"name": name, "role": role} for name, role in U07_MODULES
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
            "note": "the ONE live read (live_fields_reader) is PIT-gated "
                    "(the client's OWN location-scoped private-integration "
                    "token BY LABEL) and HELD (exit 3) when the rail is "
                    "unreachable — never a fabricated pass; the CREATE "
                    "ACTION is Trevor-gated (--execute) and is "
                    "create-only-missing with a byte-exact read-back — "
                    "this assembler never writes.",
        },
    }

def write_pending(payload: dict, *, mode: str = "self-test", out=None) -> None:
    """Write manifest-pending/u07.json (fail-closed: only after a PASS).

    The directory is created if absent; the file is written atomically
    (temp + rename) so a crash mid-write never leaves a partial stage. The
    ENGINE-MANIFEST.json / ENGINE-PIN.sha256 / verify.sh are NEVER touched."""
    out = out or sys.stderr
    try:
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        tmp = PENDING_DIR / ("u07.json.tmp-%d" % os.getpid())
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
        tmp.replace(PENDING_U07)
    except OSError as exc:
        raise AssembleError("cannot write %s: %s" % (PENDING_U07, exc)) from exc
    out.write("[provision-fields] manifest-pending stage written: %s "
              "(%s)\n" % (PENDING_U07, mode))

# ---------------------------------------------------------------------------
# CLI — house shape: --dry-run / --self-test / --json accepted as flags AND
# as a positional subcommand (--self-test / --selftest normalize exactly as
# anthology_registry.py and the U02 / U03 / U04 / U05 / U06 skeletons). The
# CREATE ACTION is a positional subcommand ('create') that REQUIRES
# --execute (the Trevor gate) — without it the ACTION is a STOP (exit 2),
# never a silent no-op and never a silent create; even WITH --execute
# creation is create-only-missing with a byte-exact read-back (this
# dispatcher never mutates on its own).
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="provision_fields.py",
        description="The U07 live field-map compliance dispatcher assembled "
                    "from the u07_modules files: offline self-test battery "
                    "(golden all-present PASS, the missing-14 and TEXT-drift "
                    "attacks REFUSED), offline plan, and live verify of the "
                    "28-key custom-field inventory law on the Convert and "
                    "Flow location (Skill 59) — every delta documented as "
                    "JSON, the manifest-pending stage written after a PASS. "
                    "Field creation requires --execute (Trevor-gated) and "
                    "is create-only-missing with a byte-exact read-back; "
                    "this tool never writes on its own.")
    ap.add_argument("--location-id", default="",
                    help="override the Convert and Flow location id "
                         "(default: the CLIENT-standard location labels "
                         "CONVERT_AND_FLOW_LOCATION_ID / "
                         "GOHIGHLEVEL_LOCATION_ID / GHL_LOCATION_ID, %s; "
                         "masked on every surface, never printed in full)"
                         % DEFAULT_TEMPLATE_LOCATION)
    ap.add_argument("--field-map", default=str(CONTRACT_PATH),
                    help="path to config/field-map.json (the single source "
                         "of truth)")
    ap.add_argument("--dry-run", action="store_true",
                    help="offline plan only — no network, no credential "
                         "(default: live verify)")
    ap.add_argument("--json", action="store_true",
                    help="emit a machine-readable summary on stdout (default "
                         "on for verify/plan)")
    ap.add_argument("--execute", action="store_true",
                    help="the Trevor gate for the CREATE ACTION — REQUIRED "
                         "before any field is created; without it missing "
                         "fields are a STOP (exit 2) that lists them; with "
                         "it, creation is create-only-missing with a "
                         "byte-exact read-back")
    ap.add_argument("--no-pytest", action="store_true",
                    help="skip the sibling pytest batteries inside "
                         "--self-test (dispatch self-test only; the offline "
                         "batteries still run)")
    ap.add_argument("--selftest", "--self-test", dest="self_test",
                    action="store_true",
                    help="run the offline self-test (golden all-present "
                         "PASS, the missing-14 and TEXT-drift attacks "
                         "REFUSED + the dispatcher battery + the pytest "
                         "batteries) and exit")
    ap.add_argument("cmd", nargs="?", choices=["verify", "plan", "create",
                                               "self-test"],
                    help="positional subcommand form (verify / plan / "
                         "create / self-test)")

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

        field_map = _read_json(Path(args.field_map).expanduser(),
                               "config/field-map.json")
        location_id = args.location_id.strip() or DEFAULT_TEMPLATE_LOCATION

        if args.dry_run:
            rc = dry_run(modules, location_id, field_map, out=sys.stderr)
            if rc == EX_OK:
                write_pending(_pending_payload("dry-run", location_id),
                              mode="dry-run")
            return rc

        if args.cmd == "create":
            # The Trevor gate, enforced at the CLI surface: a CREATE ACTION
            # without --execute is a STOP (exit 2), never a silent no-op and
            # never a silent create. WITH --execute it is create-only-missing
            # with a byte-exact read-back — the dispatcher never mutates.
            if not args.execute:
                reg._stop(sys.stderr,
                          "create REFUSED: no --execute (the Trevor gate).",
                          ["A CREATE ACTION without --execute is a STOP "
                           "(AF-AE-U07-CREATE-NO-EXECUTE), never a silent "
                           "create. Re-run with --execute to authorize the "
                           "ACTION — it is create-only-missing with a "
                           "byte-exact read-back (marker %s)."
                           % _mask_id(location_id)])
                return EX_STOP
            return verify_live(modules, location_id, field_map,
                               execute=True,
                               out=sys.stderr)

        rc = verify_live(modules, location_id, field_map,
                         execute=False,
                         out=sys.stderr)
        if rc == EX_OK:
            write_pending(_pending_payload("verify", location_id),
                          mode="verify")
        return rc

    except reg.ScopeDenied as exc:
        sys.stderr.write("[provision-fields] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[provision-fields] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[provision-fields] HELD: %s\n" % exc)
        return EX_HELD
    except reg.InternalRailUnavailable as exc:
        sys.stderr.write("[provision-fields] HELD (internal rail): %s\n" % exc)
        return EX_HELD
    except AssembleError as exc:
        sys.stderr.write("[provision-fields] STOP/FAIL: %s\n" % exc)
        return EX_STOP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[provision-fields] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR

if __name__ == "__main__":
    sys.exit(main())
