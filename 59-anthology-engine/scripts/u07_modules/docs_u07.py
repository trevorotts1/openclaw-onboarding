#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u07_modules/docs_u07.py
# U07 TOOLING — THE MODULE DOCSTRING / README, SHIPPED AS AN IMPORTABLE MODULE
# (MASTER-SPEC U07; the u02_modules/docs_u02.py row-54-sibling pattern — the
# U07 family ships under the ENGINE-MANIFEST.json row-59 shipping doctrine
# (provision_fields.py, stamped 2026-08-11 exactly as the U06 sibling's row
# 58 was stamped by archive_legacy_workflows.py); the manifest-pending/u07.json
# stage was the machine-readable input to the stamp; current skill-version
# 0.1.23, 2026-08-11).
# -----------------------------------------------------------------------------
# WHERE THIS SITS: scripts/u07_modules/ — the U07 tooling's documentation
# module, sibling of the field-census law fixtures and the live readers it
# documents. It is NOT a manifest row: the U07 verifier stays the family's
# single manifest surface under the delivery_report.py row-12 sibling-helper
# pattern, exactly as u02_modules/docs_u02.py documents the row-54 U02
# verifier and u03_modules/docs_u03.py / u04_modules/docs_u04.py /
# u05_modules/docs_u05.py / u06_modules/docs_u06.py document their siblings
# (U07_MANIFEST_ROW = None, recorded below — a doc that claims a manifest row
# that does not exist is drift). Imported BY NAME as u07_modules.docs_u07
# when a consumer wants the tooling's contract surfaces as DATA (module
# inventory, the five verified items, the house exit codes, the doctrine) or
# its rendered README as text.
#
# WHAT THIS OWNS:
#   1. THE README. The module docstring below IS the U07 tooling README:
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
#      clients (CafClient / InternalRailClient) — the docs record that
#      doctrine, they do not re-implement it.
#
# THE TOOLING THIS DOCUMENTS (orientation):
#   MASTER-SPEC U07 — the FIELD-CENSUS LAW of the anthology engine, the
#   fail-closed field-map doctrine (u07_modules/__init__.py: "Destructive
#   actions fail closed: any archive ACTION (delete / archive / remove /
#   deactivate / revoke / unpublish) in this package requires the caller to
#   pass --execute explicitly (Trevor-gated). Without --execute the module
#   must report what it WOULD do and exit without mutating."). Five
#   verified items in a FIXED order:
#   1. THE 38-KEY CENSUS LAW — a provisioned Convert and Flow location
#      carries EXACTLY 38 contact custom fields under config/field-map.json
#      provisioning.fields (the 19 base PRD Section 6 link/control keys +
#      4 Gap G10 chapter-rewrite-preservation keys + 5 U8 cover-style keys
#      + 10 U15-absorbed live fields;
#      the contract total, byte-pinned against provisioning.total_keys by
#      fieldmap_loader.py, the module that owns the load-and-verify law —
#      parse and return the inventory ONLY when the map satisfies its own
#      contract, refuse anything else). The census binds BY EXACT KEY: a
#      renamed or re-prefixed key is indistinguishable from an absent one
#      and BOTH refuse fail-closed.
#   2. THE ALL-PRESENT LAW — the golden state is EXACTLY 38 field rows on
#      the live listing, every one matched byte-exact by fieldKey, each
#      with its one synthetic id (fld_golden_000 .. fld_golden_037); any
#      deviation — an absent or renamed contract key, a foreign key outside
#      the contract, a wrong-size listing, a malformed listing, a
#      credential-shaped value — is a REFUSAL (golden_all_present.py, the
#      U07 all-present fixture, the anti-attack mirror of the U07 absent-key
#      fixture; FIELDS-ALL-PRESENT / FIELDS-NOT-ALL-PRESENT).
#   3. THE LIVE-READ LAW — the census is read LIVE through the PROVEN
#      public rail GET /locations/{locationId}/customFields
#      (services.leadconnectorhq.com — the exact call the engine's own
#      provision/verify path makes, W0.5-verified; live_fields_reader.py
#      owns the read and does NOTHING else). A read is a truthful snapshot:
#      an EMPTY field set is a correct answer, an unparseable body is HELD
#      (exit 3, never a verdict); a response body is never surfaced (it
#      could echo a credential); ids are MASKED on every operator surface.
#   4. THE CREATE GATE LAW — creating a missing field is a WRITE, and the
#      WRITE ACTION is Trevor-gated: WITHOUT --execute a missing field is a
#      STOP (exit 2, AF-AE-FIELD-MISSING family — creation is never
#      silent), WITH --execute each missing field is created by name
#      (create_name, the derivation-law input) and the server-returned
#      fieldKey is read back byte-for-byte against the intended key —
#      idempotent create-or-verify (missing_finder.py; a created fieldKey
#      that is NOT byte-equal is a MISMATCH, exit 5, the
#      AF-AE-FIELD-KEY-MISMATCH family). A name squat — a live field whose
#      name equals a create_name but whose key does NOT derive to the
#      intended key — is a human-fix drift, never counted missing, never
#      created.
#   5. THE TYPE LAW — every free-text key must be live LARGE_TEXT (PRD Gap
#      G11 + U8; Trevor's every-text-input-field-is-multi-line law) and the
#      ONE SINGLE_OPTIONS key (contact.anthology_cover_choice) must be live
#      with EXACTLY the four named cover-style options (Signature, Bold
#      Editorial, Fine Art, Pure Type — imported byte-exact from
#      cover_render.py COVER_STYLES/STYLE_NAMES, the engine's named style
#      law, never hardcoded), byte-exact, in order (type_checker.py); the
#      four sample-url LARGE_TEXT slots match the four style names in
#      order.
#   The live reads are RAIL-GATED (credentials BY LABEL through the house
#   labels, SET / NOT SET only — a token value is never printed); a missing
#   credential / unreachable rail / edge block / unparseable listing is
#   HELD (exit 3, never a fabricated field list); a bare 401/403 is
#   classified by body signature — a genuine scope denial is a STOP, a
#   non-matching edge block is HELD (never mislabeled as a scope problem).
#   The offline gates (the load law, the all-present law, the golden
#   surface, the missing/type law surfaces) exercise their OWN golden
#   surfaces and NEVER require a credential. The tooling ships NOW (the u07
#   package-init doctrine; the U07 manifest row IS stamped — row 59,
#   provision_fields.py, the manifest-pending/u07.json stage written by the
#   assembly after its PASS):
#   the operator executes a live read only from a session that can resolve
#   a location-scoped credential BY LABEL. The laws are pinned from the
#   SINGLE AUTHORITIES — fieldmap_loader (the load law), golden_all_present
#   (the all-present law surface + the golden 38), live_fields_reader (the
#   live read), missing_finder (the missing-field + create gate law),
#   type_checker (the type law), anthology_registry.load_field_map (the ONE
#   keying authority, never re-implemented) — never a second implementation;
#   a drift in an authority breaks the fixture's self-test FIRST
#   (fail-closed: an inconsistent law is a refusal, never a blind pass).
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE, everywhere in this tooling. The
# U07 fixtures hold NO credential surface at all (the golden all-present
# surface is pure in-memory metadata over SYNTHETIC ids — fld_golden_000 ..
# fld_golden_027 — never a live id, never a real field, never a real
# token); the family's live surfaces (live_fields_reader, missing_finder's
# read and create, type_checker's verify) resolve their credentials through
# the house labels (the client's OWN Convert and Flow private-integration
# token: CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_API_KEY /
# GOHIGHLEVEL_API_KEY / GOHIGHLEVEL_PIT / GHL_API_KEY, the pit- prefix
# validated so a placeholder is refused WITHOUT printing it; the location
# id: CONVERT_AND_FLOW_LOCATION_ID / GOHIGHLEVEL_LOCATION_ID /
# GHL_LOCATION_ID — live process env first, then the three canonical client
# env stores; SET / NOT SET only — a token value is NEVER printed). Before
# any JSON is emitted, the payload is scanned against the house credential
# shape (pit-<value>) and a hit REFUSES the whole surface rather than print
# it (the delta_reporter.py never-a-real-token doctrine). Field ids are
# MASKED to their LAST 4 characters on every operator surface (a field id
# is a tenant identifier — the masked-id policy identical to the location
# and workflow ids); full ids ride inside request URLs and the
# machine-consumed JSON payloads only; a rail response body is never
# surfaced (it could echo a credential); classification reports HTTP code
# or error CLASS only.
#
# BROWSER UA (CF 1010 LAW): every request rides reg.CafClient, which
# applies CAF_BROWSER_UA on EVERY request so the Cloudflare edge fronting
# services.leadconnectorhq.com / backend.leadconnectorhq.com never 1010s a
# verify request (CF error 1010; the W0.6 / GK-09 discipline — urllib's
# default "Python-urllib/x.y" is 403'd at the WAF edge before it ever
# reaches the API). The U07 fixtures make NO network call at all (the
# offline surfaces), so they define NO User-Agent constant of their own —
# the live modules pin the exact constant on the outbound surface (the
# registry self-test enforces it byte-equal to the Podcast gate's
# proven-live string, the GK-09 regression pin) so a registry regression is
# caught OFFLINE first, never first seen as a 1010 at runtime. Scope-vs-
# edge-block discrimination: a bare 401/403 is HELD
# (UpstreamBlockedError / CafUnreachable), a genuine scope denial (the
# body matched the Convert and Flow scope signature) is a STOP — never
# mislabeled.
#
# FAIL-CLOSED (the whole point): a missing credential / location STOPS
# (exit 2), a field-map that drifted from its own contract STOPS (the
# load law — 38-key count, total_keys mismatch, derivation law, type law,
# key law — never a silent load), a missing field WITHOUT --execute STOPS
# (exit 2, AF-AE-FIELD-MISSING family — creation is never silent, the
# Trevor gate; WITH --execute creation is idempotent create-or-verify),
# a name squat or a created fieldKey that is not byte-equal STOPS or FAILS
# (exit 5, the AF-AE-FIELD-KEY-MISMATCH family — human-fix drift, never
# created, never certified), an unreadable listing / a drifted payload /
# a foreign or wrong-size census / a credential-shaped value is a FAIL or
# HELD (exit 5 / exit 3, never a fabricated pass, never a guessed id), a
# transport / edge failure is HELD (exit 3, UNDETERMINED — never a
# verdict), the all-present fixture REFUSES every drift of the golden
# surface (exit 5) while the golden control PASSES (a gate that fails
# everything is a broken check, not a real fault), and a drifted authority
# (fieldmap_loader / golden_all_present / anthology_registry) breaks the
# fixture's self-tests FIRST (exit 4 — a tamper never masquerades as exit
# 1). A success is claimed ONLY when the census agrees with its source of
# truth AND every write step ran under its gate. Every deviation is NAMED
# with its code — never a bare "something failed".
#
# DOCTRINE (house, per anthology_registry.py / drive_adapter.py / the
# u07 __init__.py): move in silence (operator-verbose only); NOTHING
# Anthropic in any runtime file; Convert and Flow naming in every client
# surface; STDLIB ONLY; calls NO model; never a client PII; a law is read
# once, in one module (the delta_reporter.py single-implementation
# doctrine — fieldmap_loader owns the load law, golden_all_present owns
# the all-present law surface, live_fields_reader owns the live census
# read, missing_finder owns the missing-field + create gate law,
# type_checker owns the type law, anthology_registry owns the rail client
# + the browser-UA constant + load_field_map, and the fixtures derive from
# them, never re-implement). READ-ONLY by doctrine — the checkers never
# write; a WRITE ACTION (provisioning a missing field) is Trevor-gated
# (--execute) and even WITH --execute it is idempotent create-or-verify
# with a byte-exact read-back (never a blind create, never a re-type of a
# live field of the wrong type — that is a provisioning decision, never a
# silent runtime act). Self-test failures are exit 4 (enforced violation,
# the AF-AE-FIELDMAP-* / AF-AE-GOLDENALLPRESENT-* / AF-AE-MISSINGFINDER-* /
# AF-AE-FIELD-MISSING / AF-AE-FIELD-KEY-MISMATCH families) — a tamper
# never masquerades as exit 1.
#
# USAGE (this module's own machine surface — pure data, nothing to leak):
#   python3 docs_u07.py                ONE JSON catalog of the whole tooling
#   python3 docs_u07.py readme         the rendered README (markdown text)
#   python3 docs_u07.py self-test      OFFLINE drift gate over the docs vs
#                                      the shipped tree; 0 clean, 4 drift
# =============================================================================
"""docs_u07.py -- README / module docstring for the U07 tooling, as an
importable fail-closed pure-data module: the field-census law family
(fieldmap_loader / golden_all_present / live_fields_reader /
missing_finder / type_checker under the ENGINE-MANIFEST.json row-59
shipping doctrine — provision_fields.py, the family's OWN manifest row
stamped 2026-08-11), its five verified items, the u07_modules inventory,
the house exit codes, and the credential / browser-UA / doctrine contracts.
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
DOC_CONTRACT = "anthology-engine-u07-tooling-docs"
SCHEMA_VERSION = 1

# The U07 family's verifier stays the family's single manifest surface
# under the U02 row-54 shipping law; the u07_modules/ siblings ship as
# non-manifest helpers (the delivery_report.py row-12 pattern, exactly the
# docs_u02.py / docs_u03.py / docs_u04.py / docs_u05.py / docs_u06.py
# siblings). The U07 family's OWN manifest row IS stamped — row 59,
# scripts/provision_fields.py (verified 2026-08-11, exactly as the U06
# sibling's row 58 was stamped by archive_legacy_workflows.py); the
# manifest-pending/u07.json stage was the machine-readable input to the
# stamp, written by the assembly after its PASS.
U07_VERIFIER = "main_skeleton.py"  # the family's single driver, per the
                                   # u07 modules' own references
U07_MANIFEST_ROW = 59  # ENGINE-MANIFEST.json row 59: provision_fields.py
U07_SHIPPING_VERSION = "v0.1.23 (2026-08-11)"  # skill-version at ship time

# ---------------------------------------------------------------------------
# THE FIVE VERIFIED ITEMS (MASTER-SPEC U07 — the family's five gates, in
# the FIXED order the census law carries them). Item numbers are
# load-bearing (positions 1..5, exactly five — self-test pins the count);
# the title is the README heading, asserts the fail-closed claim, sources
# the engine's source of truth, and fails the operator surface on drift.
# ---------------------------------------------------------------------------
VERIFY_ITEMS = (
    {
        "item": 1,
        "title": "38-key census law — the field-map contract loads byte-exact",
        "asserts": ("a provisioned Convert and Flow location carries "
                    "EXACTLY 38 contact custom fields under "
                    "config/field-map.json provisioning.fields (the 19 "
                    "base PRD Section 6 link/control keys + 4 Gap G10 "
                    "chapter-rewrite-preservation keys + 5 U8 cover-style "
                    "keys — the contract total) and the map is loaded ONLY "
                    "when it satisfies its own contract: parse "
                    "field-map.json and return its provisioning.fields "
                    "inventory ONLY on a contract-verified load "
                    "(fieldmap_loader.py, the module that owns the "
                    "load-and-verify law); provisioning.total_keys MUST "
                    "byte-match the inventory length; every row's "
                    "create_name MUST derive back to its intended_key "
                    "byte-exact (reg.derive_field_key, the derivation "
                    "law W0.5); every free-text key is declared LARGE_TEXT "
                    "(PRD Gap G11 + U8, the multi-line law) and the ONE "
                    "SINGLE_OPTIONS key (contact.anthology_cover_choice) "
                    "carries EXACTLY the four named cover-style options "
                    "(Signature, Bold Editorial, Fine Art, Pure Type) in "
                    "order (the type law); every intended_key carries the "
                    "'contact.' prefix (the key law); a map that drifted "
                    "from its own contract is a refusal (exit 2 STOP "
                    "family), never a silent load; the census binds BY "
                    "EXACT KEY — a renamed or re-prefixed key is "
                    "indistinguishable from an absent one and BOTH refuse "
                    "fail-closed"),
        "source": "config/field-map.json (provisioning.fields + "
                  "provisioning_rule + field_key_derivation_law + "
                  "data_type_choice) read through "
                  "anthology_registry.load_field_map (the ONE keying "
                  "authority, never re-implemented); the 38-key count "
                  "pinned by the registry self-test and the U02 "
                  "golden_fields sibling",
        "fails": "FieldMapError contract refusal — 38-key count drift, "
                 "total_keys mismatch, derivation-law violation, type-law "
                 "violation, key-law violation (missing / duplicate / "
                 "wrong-prefix key), unreadable or malformed map (exit 2) "
                 "— never a silent load; an unresolved field_id slot is a "
                 "NORMAL load surfaced as per-key RESOLVED / UNRESOLVED, "
                 "the resolved value itself NEVER reaching a surface",
    },
    {
        "item": 2,
        "title": "All-present law — the golden 38 are present BY EXACT KEY",
        "asserts": ("the golden state of the U07 census is EXACTLY 38 "
                    "field rows on the listing, every one present BY "
                    "EXACT KEY — a row's fieldKey must byte-equal the "
                    "intended key, each with its one synthetic id "
                    "(fld_golden_000 .. fld_golden_037, the fixture "
                    "discipline: a fixture id is never a real field id) — "
                    "matched by the deep-frozen canonical record "
                    "GOLDEN_ALL_PRESENT (MappingProxyType, every container "
                    "a tuple — no caller can mutate it; golden_all_present() "
                    "/ golden_fields_payload() return deep copies) and "
                    "judged by the fail-closed all-present gate payload(): "
                    "ALL 38 present -> PASS exit 0 with the "
                    "dispatcher-consumed dict {'ok': True, 'count': 38, "
                    "'af_code': 'FIELDS-ALL-PRESENT', 'note': ...}; ANY "
                    "deviation — a contract key absent or renamed, a "
                    "foreign key not in the 38-key contract, a wrong-size "
                    "listing, a malformed listing, a non-object row, a "
                    "credential-shaped value — is a REFUSED exit 5 "
                    "(FIELDS-NOT-ALL-PRESENT), never a blind pass, never a "
                    "fabricated success; the 38 intended keys are NEVER "
                    "retyped here — they come byte-exact from "
                    "config/field-map.json provisioning.fields through "
                    "reg.load_field_map (the single-implementation "
                    "doctrine)"),
        "source": "golden_all_present (the U07 all-present fixture, the "
                  "anti-attack mirror of the U07 absent-key fixture) "
                  "derived from config/field-map.json provisioning.fields "
                  "via anthology_registry.load_field_map — the ONE keying "
                  "authority; GOLDEN_EXECUTE_REQUIRED = True pins the "
                  "Trevor-gated WRITE ACTION law (the gate lives in the "
                  "dispatcher, never in a fixture)",
        "fails": "FIELDS-NOT-ALL-PRESENT (exit 5) — absent / renamed / "
                 "duplicate / foreign contract key, wrong-size or "
                 "malformed listing, non-object row, credential-shaped "
                 "value; the golden control itself MUST PASS (a gate that "
                 "fails everything is a broken check, not a real fault); "
                 "a drift in the 38-key law breaks THIS fixture's "
                 "self-test first (exit 4)",
    },
    {
        "item": 3,
        "title": "Live-read law — the census is read LIVE through the PROVEN rail",
        "asserts": ("the census is read LIVE through the PROVEN public "
                    "rail GET /locations/{locationId}/customFields "
                    "(services.leadconnectorhq.com, the W0.5-verified "
                    "surface documented in "
                    "29-ghl-convert-and-flow/references/custom-fields.md "
                    "and already proven live by the engine's own "
                    "anthology_registry.CafClient.list_custom_fields — "
                    "the same call the U02 fields_check.py and the "
                    "provision path exercise) and does NOTHING else "
                    "(live_fields_reader.py, the read surface of the U07 "
                    "family — no write surface, no ACTION verb, "
                    "read-only by construction); a read is a truthful "
                    "snapshot of the live inventory: an EMPTY field set "
                    "is a correct answer (exit 0), an unparseable body is "
                    "HELD (exit 3, never a fabricated field list); a "
                    "response body is NEVER surfaced (it could echo a "
                    "credential); only parsed field records (name, "
                    "fieldKey, id, dataType) are surfaced with the id "
                    "masked to its last 4 chars (house masking "
                    "discipline; full ids ride inside request URLs only)"),
        "source": "the PROVEN public rail read of the engine's own "
                  "anthology_registry.CafClient.list_custom_fields "
                  "(services.leadconnectorhq.com — W0.5-verified, the "
                  "exact call the U02 fields_check.py and the provision "
                  "path exercise); CAF_BROWSER_UA on every request (CF "
                  "1010 law)",
        "fails": "a missing credential / location STOPS (exit 2, labels "
                 "NOT SET), an unreachable rail or edge block (CF 1010) "
                 "is HELD (exit 3, UNDETERMINED — never a verdict), an "
                 "unparseable listing is HELD (exit 3); a bare 401/403 is "
                 "classified by body signature — a genuine scope denial "
                 "is a STOP (exit 2), a non-matching edge block is HELD — "
                 "a bare status is NEVER a verdict",
    },
    {
        "item": 4,
        "title": "Create gate law — a missing field STOPS without --execute",
        "asserts": ("creating a missing field is a WRITE, and the WRITE "
                    "ACTION is Trevor-gated (the u07 package-init "
                    "doctrine; GOLDEN_EXECUTE_REQUIRED = True): WITHOUT "
                    "--execute an operator surface that lists missing "
                    "fields and stops is the DEFAULT — a missing field "
                    "STOPS setup (exit 2, AF-AE-FIELD-MISSING family), "
                    "never a silent no-op, never an auto-create, and the "
                    "list IS the payload (missing_finder.py); WITH "
                    "--execute each missing field is created by name "
                    "(create_name, the derivation-law input) via the "
                    "engine's proven create surface (reg.CafClient."
                    "create_custom_field — POST "
                    "/locations/{locationId}/customFields, with data_type "
                    "from the map and options from the map for the ONE "
                    "SINGLE_OPTIONS key) and the server-returned fieldKey "
                    "is read back byte-for-byte against the intended key — "
                    "idempotent create-or-verify: a re-run over the "
                    "healed location finds everything present and creates "
                    "nothing; a name squat — a live field whose name "
                    "equals a create_name but whose key does NOT derive "
                    "to the intended key — is a human-fix drift "
                    "(AF-AE-FIELD-KEY-MISMATCH family), never counted "
                    "missing, never silently created, with or without "
                    "--execute"),
        "source": "the u07 __init__.py fail-closed doctrine + "
                  "missing_finder (the missing-field + create gate law) + "
                  "the derivation law of config/field-map.json "
                  "(field_key_derivation_law); the create surface is the "
                  "engine's OWN proven create_custom_field "
                  "(anthology_registry) — a module never invents a "
                  "create surface",
        "fails": "a missing field WITHOUT --execute is a STOP (exit 2, "
                 "AF-AE-FIELD-MISSING) — never a silent no-op; a created "
                 "fieldKey that is NOT byte-equal to its intended key is "
                 "a MISMATCH (exit 5, AF-AE-FIELD-KEY-MISMATCH) — the "
                 "derivation law changed or the server drifted, and "
                 "NOTHING about that key is certified; a name squat is "
                 "exit 5, never created; this module NEVER stamps "
                 "field-map.json (resolved-slot stamping is "
                 "provision-fields' own duty)",
    },
    {
        "item": 5,
        "title": "Type law — every free-text key live LARGE_TEXT, the choice field exact",
        "asserts": ("every free-text field in config/field-map.json "
                    "provisioning.fields must be LIVE LARGE_TEXT (PRD Gap "
                    "G11 + U8; Trevor's every-text-input-field-is-multi-"
                    "line law — the earlier TEXT declaration was a "
                    "repo-vs-live drift the spec called out) and the ONE "
                    "SINGLE_OPTIONS field in the inventory (the U8 cover "
                    "choice, contact.anthology_cover_choice) must be live "
                    "with EXACTLY the four named cover-style options, "
                    "byte-exact, in order (type_checker.py) — the four "
                    "names are NOT hardcoded: the picklist is imported "
                    "byte-exact from scripts/cover_render.py "
                    "COVER_STYLES/STYLE_NAMES (the engine's named style "
                    "law: Signature, Bold Editorial, Fine Art, Pure Type), "
                    "and the module pins that import byte-exact against "
                    "the field-map's own declared options in order so the "
                    "two surfaces can never drift apart; the four "
                    "sample1..4 LARGE_TEXT fields match the four style "
                    "names in cover_render.py order (the sample-url slot "
                    "law); a live field of the WRONG type is NEVER "
                    "silently re-created or re-typed (changing a live "
                    "field's dataType is a provisioning decision, never a "
                    "silent runtime act; field-map resolution_rule) — it "
                    "is a FAIL; create-only-missing provision is "
                    "Trevor-gated (WITH --execute: create at the DECLARED "
                    "data_type, then RE-LIST and re-verify in the same "
                    "job, so a report never claims a type that was not "
                    "read back; the report states execute true/false "
                    "explicitly on every run)"),
        "source": "config/field-map.json data_type_choice + "
                  "scripts/cover_render.py COVER_STYLES/STYLE_NAMES (the "
                  "engine's named style law — the picklist is pinned "
                  "byte-exact, never hardcoded) + the U8 provision note; "
                  "the LARGE_TEXT law is Trevor's every-text-input-field-"
                  "is-multi-line law",
        "fails": "a live free-text field whose dataType is NOT LARGE_TEXT "
                 "(TEXT, PHONE, or any other byte) is a VIOLATION of the "
                 "multi-line law (exit 5), never a silent pass; the choice "
                 "field not SINGLE_OPTIONS or its live options not "
                 "byte-equal to the four named styles in order is a FAIL "
                 "(exit 5); any missing / extra / reordered / byte-"
                 "drifted option is a violation; a map-vs-cover_render "
                 "options mismatch STOPS (exit 2); a missing field "
                 "without --execute STOPS (exit 2); a created field read "
                 "back drifted is exit 5",
    },
)

# ---------------------------------------------------------------------------
# THE MODULE INVENTORY. `place` names the directory relative to this module
# (the u07_modules package itself); self-test proves each name exists at
# that place. `role` is the one-line contract each module owns; `offline`
# names the credential-free surface; `exit_codes` follows the house
# convention (0/1/2/3/5, 4 = self-test).
# ---------------------------------------------------------------------------
MODULES = (
    {
        "name": "__init__.py",
        "place": "scripts/u07_modules/",
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
        "name": "fieldmap_loader.py",
        "place": "scripts/u07_modules/",
        "manifest_row": None,
        "role": ("the FAIL-CLOSED FIELD-MAP LOADER AND CONTRACT GATE — "
                 "the single implementation of the field-map.json "
                 "load-and-verify law for this package: read "
                 "config/field-map.json and return its "
                 "provisioning.fields inventory (the 38 keys, with their "
                 "declared data types) ONLY when the map satisfies its "
                 "own contract (38-key count, total_keys byte-match, "
                 "derivation law via reg.derive_field_key, type law, key "
                 "law with the 'contact.' prefix) and refuse anything "
                 "else (FieldMapError, exit 2 STOP family — never a "
                 "silent load); fully OFFLINE, READ-ONLY, NETWORK-FREE — "
                 "never a token, never an env store, never the wire; "
                 "asserts reg.CAF_BROWSER_UA exists and byte-equals the "
                 "Podcast gate's proven-live string (the GK-09 regression "
                 "pin, exactly as the registry's own self-test enforces) "
                 "so a consumer wiring its OWN requests is caught OFFLINE "
                 "if the shared constant drifts — never first seen as a "
                 "1010 at runtime; the run payload carries STATUS only "
                 "for resolved slots, never the field_id VALUE (a tenant "
                 "identifier, the masked-id policy of the U06 modules)"),
        "offline": "entirely — pure loader + contract gate + self-test, "
                   "no network, no credentials (3 and 5 are reserved for "
                   "live surfaces; this module never returns them)",
        "exit_codes": "0/1/2/4",
    },
    {
        "name": "golden_all_present.py",
        "place": "scripts/u07_modules/",
        "manifest_row": None,
        "role": ("the GOLDEN ALL-38-PRESENT FIXTURE — the canonical "
                 "in-memory payload of the U07 FIELD-CENSUS law in its "
                 "GOLDEN state: ALL 38 Convert and Flow contact custom "
                 "fields a provisioned location must carry are on the "
                 "listing BY EXACT KEY, every one present — the golden "
                 "control of the U07 all-present gate (the anti-attack "
                 "mirror of the U07 absent-key fixture); owns the "
                 "deep-frozen canonical record GOLDEN_ALL_PRESENT "
                 "(MappingProxyType, every container a tuple, SYNTHETIC "
                 "ids only fld_golden_000 .. fld_golden_037), the "
                 "fail-closed all-present gate payload() "
                 "(FIELDS-ALL-PRESENT exit 0 / FIELDS-NOT-ALL-PRESENT "
                 "exit 5, the dispatcher-consumed dict surface) and "
                 "GOLDEN_EXECUTE_REQUIRED = True (the WRITE-ACTION law, "
                 "Trevor-gated — the gate lives in the dispatcher, never "
                 "in a fixture); the 38 contract keys are read ONCE from "
                 "config/field-map.json through reg.load_field_map, never "
                 "retyped here"),
        "offline": "entirely — pure data + the all-present gate + "
                   "self-test (synthetic ids only, no network, no "
                   "credentials)",
        "exit_codes": "0/1/4/5",
    },
    {
        "name": "live_fields_reader.py",
        "place": "scripts/u07_modules/",
        "manifest_row": None,
        "role": ("the LIVE CUSTOM-FIELDS READER — the read surface of the "
                 "U07 family: reads the contact custom fields of a Convert "
                 "and Flow location through the PROVEN public rail GET "
                 "/locations/{locationId}/customFields "
                 "(services.leadconnectorhq.com, the W0.5-verified surface "
                 "already proven live by anthology_registry.CafClient."
                 "list_custom_fields — the same call the U02 fields_check "
                 "and the provision path exercise) and does NOTHING else; "
                 "no write surface and no ACTION verb — read-only by "
                 "construction, there is nothing an --execute flag could "
                 "unlock; an EMPTY field set is a truthful PASS; an "
                 "unparseable body is HELD; a response body is never "
                 "surfaced (it could echo a credential); field ids masked "
                 "to last 4 chars on every operator surface; rides "
                 "reg.CafClient with CAF_BROWSER_UA on every request; a "
                 "bare 401/403 is classified by body signature — a "
                 "genuine scope denial is a STOP, a non-matching edge "
                 "block is HELD"),
        "offline": "self-test (no token, no network); the live read "
                   "needs the client's OWN pit- token BY LABEL (SET / "
                   "NOT SET only, never printed)",
        "exit_codes": "0/1/2/3/4",
    },
    {
        "name": "missing_finder.py",
        "place": "scripts/u07_modules/",
        "manifest_row": None,
        "role": ("the MISSING-FIELD FINDER — GET-check-by-name, list "
                 "missing fields, and idempotent create-or-verify: READS "
                 "the live custom-fields listing (ONE GET through the "
                 "engine's own LeadConnector client) and reports PRESENT "
                 "(byte-equal server fieldKey) / MISSING (no live field "
                 "under the derived key AND no live field under the "
                 "create name — the finder's payload) / DRIFT (a name "
                 "squat: a live name under a non-derived key — never "
                 "counted missing, never silently created, a human-fix "
                 "drift, the AF-AE-FIELD-KEY-MISMATCH family); creation "
                 "REQUIRES --execute (Trevor-gated — without it a "
                 "missing field is a STOP exit 2, AF-AE-FIELD-MISSING "
                 "family, the list IS the payload, creation is never "
                 "silent); WITH --execute creates each missing field by "
                 "name via the proven reg.CafClient.create_custom_field "
                 "surface and reads the server-returned fieldKey back "
                 "byte-for-byte against the intended key (a non-byte-"
                 "equal key is a MISMATCH exit 5); never stamps "
                 "field-map.json (resolved-slot stamping is "
                 "provision-fields' own duty); every comparison is "
                 "byte-exact — no normalization, no substring, no "
                 "similarity score (the U06 exact-name law, applied to "
                 "field names)"),
        "offline": "plan + self-test (no token, no network); the live "
                   "check needs the client's OWN Convert and Flow "
                   "private-integration token BY LABEL (resolve_pit, the "
                   "pit- prefix validated so a placeholder is refused "
                   "WITHOUT printing it)",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "type_checker.py",
        "place": "scripts/u07_modules/",
        "manifest_row": None,
        "role": ("the LIVE FIELD-TYPE CHECKER — asserts that EVERY "
                 "free-text field in config/field-map.json "
                 "provisioning.fields is LIVE LARGE_TEXT (Trevor's "
                 "every-text-input-field-is-multi-line law, PRD Gap G11 + "
                 "U8) and that the ONE SINGLE_OPTIONS field in the "
                 "inventory (the U8 cover choice, "
                 "contact.anthology_cover_choice) is live with EXACTLY "
                 "the four named cover-style options, byte-exact, in "
                 "order (the picklist imported byte-exact from "
                 "scripts/cover_render.py COVER_STYLES/STYLE_NAMES — the "
                 "engine's named style law, never hardcoded; the four "
                 "sample1..4 LARGE_TEXT fields match the four style names "
                 "in order, the sample-url slot law); a live field of the "
                 "WRONG type is NEVER silently re-created or re-typed — "
                 "it is a FAIL; create-only-missing provision is "
                 "Trevor-gated (WITH --execute: create at the DECLARED "
                 "data_type then RE-LIST and re-verify in the same job; "
                 "the report states execute true/false explicitly on "
                 "every run); READ-ONLY unless --execute"),
        "offline": "plan + self-test (no token, no network); the live "
                   "verify needs the client's OWN pit- token BY LABEL "
                   "(SET / NOT SET only, never printed)",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "docs_u07.py",
        "place": "scripts/u07_modules/",
        "manifest_row": None,
        "role": ("THIS MODULE — the U07 tooling README / catalog data + "
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
# the U07 family commits to; self-test pins all six.
# ---------------------------------------------------------------------------
EXIT_CODES = {
    0: "verified success — the census agrees with its source of truth "
       "and every write step ran under its gate (also plan / self-test; "
       "an EMPTY custom-field set is a truthful PASS; nothing missing is "
       "a clean no-op PASS)",
    1: "unexpected error (top-level guard; never a secret leak)",
    2: ("STOP refusal — label NOT SET / a non-pit- value / usage / a "
        "field-map that drifted from its own contract (FieldMapError: "
        "38-key count, total_keys mismatch, derivation law, type law, key "
        "law — never a silent load) / a map-vs-cover_render options "
        "mismatch / the cover_render style import failed / a missing "
        "field WITHOUT --execute (the Trevor gate, AF-AE-FIELD-MISSING "
        "family — creation is never silent) / a GENUINE scope denial "
        "(the response body matched the Convert and Flow scope signature)"),
    3: ("HELD — Convert and Flow unreachable (transport) or an "
        "upstream/edge block (CF error 1010, Cloudflare edge 403) / a "
        "malformed listing (UNDETERMINED, never a verdict — a bare "
        "401/403 is HELD, never mislabeled as a scope problem)"),
    4: ("self-test FAILED (AF-AE-FIELDMAP-* / AF-AE-GOLDENALLPRESENT-* / "
        "AF-AE-MISSINGFINDER-* / AF-AE-FIELD-MISSING / "
        "AF-AE-FIELD-KEY-MISMATCH / AF-AE-TEMPLATE-ATTACK family, "
        "enforced violation) — a tamper never masquerades as exit 1"),
    5: ("mismatch / fail-closed default — a contract key absent or "
        "renamed (FIELDS-NOT-ALL-PRESENT), a foreign key outside the "
        "38-key contract, a wrong-size or malformed census, a "
        "credential-shaped or full-id surface (leak-scan REFUSAL), a "
        "name-squat drift (a live name under a non-derived key), a "
        "created fieldKey that is not byte-equal to its intended key, a "
        "live field of the wrong dataType (not LARGE_TEXT / not "
        "SINGLE_OPTIONS / drifted options), a read-back mismatch, or a "
        "DEFERRED live read without --allow-deferred"),
}

# ---------------------------------------------------------------------------
# THE AF AUTOfail FAMILY of the U07 tooling — the codes the family's own
# surfaces declare. The U07-specific codes are NOT yet stamped in
# ENGINE-MANIFEST.json (the family is PENDING — verified at ship time,
# 2026-08-11); AF-AE-TEMPLATE-ATTACK and the shared AF-AE-READBACK-MISMATCH
# codes already live in the manifest. Self-test failures are exit 4, never
# 1.
# ---------------------------------------------------------------------------
AF_CODES = (
    ("AF-AE-FIELDMAP-*", 4,
     "an attack tripped the field-map loader's OFFLINE self-test "
     "(enforced violation) — a drifted map contract, a derivation-law "
     "violation, or a tampered load law was not caught HERE first"),
    ("AF-AE-GOLDENALLPRESENT-*", 4,
     "an attack tripped the all-present fixture's OFFLINE self-test "
     "(enforced violation) — an absent / renamed / duplicate / foreign "
     "contract key, a wrong-size or malformed census, or a "
     "credential-shaped value was not refused HERE first"),
    ("AF-AE-MISSINGFINDER-*", 4,
     "an attack tripped the missing-finder's OFFLINE self-test (enforced "
     "violation) — a drifted missing/create gate law was not caught HERE "
     "first"),
    ("AF-AE-FIELD-MISSING", 2,
     "a missing field was reported WITHOUT --execute — creation is "
     "Trevor-gated and never silent: the list of missing fields IS the "
     "payload, and the module STOPS (never an auto-create)"),
    ("AF-AE-FIELD-KEY-MISMATCH", 5,
     "a name squat (a live field whose name equals a create_name but "
     "whose fieldKey does NOT derive to the intended key) or a created "
     "fieldKey that is not byte-equal to its intended key — the "
     "derivation law changed or the server drifted, and NOTHING about "
     "that key is certified (human-fix drift, never created)"),
    ("AF-AE-READBACK-MISMATCH", 5,
     "a post-write read-back does not prove the fix byte-for-byte — the "
     "shared house code with the U02 / U03 / U04 / U05 / U06 families "
     "(already stamped in ENGINE-MANIFEST.json)"),
    ("AF-AE-TEMPLATE-ATTACK", 4,
     "an attack fixture tripped the OFFLINE self-test of the dispatcher "
     "or a family battery (enforced violation — the house code, shared "
     "with the U02 / U03 / U04 / U05 / U06 families)"),
)

# ---------------------------------------------------------------------------
# DOCTRINE — the house rules the whole U07 tooling commits to, as data so
# the README renders them from the same source the self-test asserts.
# ---------------------------------------------------------------------------
DOCTRINE = (
    ("Fail-closed", "a missing credential, a malformed input, an "
     "unreadable source, or a live read that cannot be completed is a "
     "REFUSAL or a recorded FAIL — never a blind pass, never a fabricated "
     "success; a map that drifted from its own contract is never loaded; "
     "a missing field WITHOUT --execute is a STOP (exit 2), never a "
     "silent no-op and never an auto-create; an id is NEVER guessed from "
     "memory"),
    ("Secrets", "credentials resolve BY LABEL only (SET / NOT SET); a "
     "token value is never printed, echoed, or reflected in any surface; "
     "the pit- prefix is validated so a placeholder is refused WITHOUT "
     "printing it; before any JSON is emitted the payload is scanned "
     "against the house credential shape (pit-<value>) and a hit REFUSES "
     "the whole surface (the delta_reporter.py never-a-real-token "
     "doctrine); field / location ids are MASKED to their last 4 "
     "characters on every operator surface (a field id is a tenant "
     "identifier) — full ids ride inside request URLs and the "
     "machine-consumed JSON payloads only; a rail response body is never "
     "surfaced (it could echo a credential)"),
    ("Browser UA", "every request to GoHighLevel / Convert and Flow "
     "(services.leadconnectorhq.com) and the internal rail "
     "(backend.leadconnectorhq.com) rides CAF_BROWSER_UA (reg.CafClient / "
     "reg.InternalRailClient) — urllib's default 'Python-urllib/x.y' is "
     "403'd at the WAF edge (CF error 1010) before it ever reaches the "
     "API (W0.6 / GK-09); the U07 fixtures make NO network call, so they "
     "define NO User-Agent constant of their own — fieldmap_loader pins "
     "the exact constant on the offline law surface (byte-equal to the "
     "Podcast gate's proven-live string, the GK-09 regression pin, "
     "exactly as the registry's own self-test enforces) so a registry "
     "regression is caught HERE first"),
    ("Scope vs edge", "a bare 401/403 is HELD (UpstreamBlockedError / "
     "CafUnreachable), never mislabeled as a scope problem — a GENUINE "
     "scope denial (the response body matched the Convert and Flow scope "
     "signature) is a STOP, UNDETERMINED is a correct answer, never a "
     "verdict"),
    ("Synthetic ids only", "the fixtures carry SYNTHETIC deterministic "
     "ids only (fld_golden_000 .. fld_golden_027 — the fixture "
     "discipline, the same synthetic id series the U02 golden_fields "
     "sibling pins) — a fixture id is never a live field id, never a "
     "real field, and never a real token"),
    ("Single authority", "a law is read once, in one module: "
     "fieldmap_loader owns the load-and-verify law, golden_all_present "
     "owns the all-present law surface (the golden 38, the gate, "
     "GOLDEN_EXECUTE_REQUIRED), live_fields_reader owns the live census "
     "read, missing_finder owns the missing-field + create gate law, "
     "type_checker owns the type law, anthology_registry owns the rail "
     "client + the browser-UA constant + load_field_map — the fixtures "
     "derive from them, never re-implement; a drift in an authority "
     "breaks the fixture's self-test FIRST"),
    ("Negative-result contract", "the all-present fixture carries its OWN "
     "golden control (the golden listing PASSES the gate), so every "
     "pass/fail split discriminates the census law and never a broken "
     "instrument — a gate that fails everything is a broken check, not a "
     "real fault; an attack fixture that PASSES any census gate is a "
     "broken gate; a negative is a claim and carries the same burden of "
     "proof as a positive one"),
    ("Gated writes", "--execute is the ONLY flag that performs a WRITE "
     "ACTION (Trevor-gated, the u07 package-init doctrine): creating a "
     "missing field without it is a STOP (exit 2, AF-AE-FIELD-MISSING) — "
     "and even WITH --execute creation is idempotent create-or-verify "
     "with a byte-exact read-back (a created fieldKey that is not "
     "byte-equal is a MISMATCH, exit 5, the AF-AE-FIELD-KEY-MISMATCH "
     "family); a live field of the wrong type is NEVER silently "
     "re-created or re-typed (changing a live field's dataType is a "
     "provisioning decision, never a silent runtime act); field-map.json "
     "is never stamped by the checkers (resolved-slot stamping is "
     "provision-fields' own duty)"),
    ("Move in silence", "operator-verbose only; NOTHING Anthropic in any "
     "runtime file; Convert and Flow naming in every client surface; "
     "STDLIB ONLY; calls NO model; never a client PII; READ-ONLY by "
     "doctrine — the checkers never write; the WRITE ACTION is the ONE "
     "gated surface"),
)

# ---------------------------------------------------------------------------
# CREDENTIAL LABELS — BY LABEL ONLY. These are the label NAMES the tooling
# resolves through anthology_registry (live process env first, then the
# three canonical client env stores). A label is a name, never a value; the
# values they resolve to are never held here and never printed anywhere.
# The U07 fixtures hold NO credential surface at all (pure in-memory
# metadata over synthetic ids); the family's live surfaces — the
# live_fields_reader / missing_finder / type_checker reads and creates —
# resolve their credentials through the house labels below.
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
}

# Pinned counts (the fixture-counting discipline of golden_fields.py: a
# drifted inventory is drift, never tolerated). Adding a module to the U07
# tooling REQUIRES adding it here AND to the README's inventory.
CONTRACT_ITEM_COUNT = 5
CONTRACT_MODULE_COUNT = 7

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
    """The U07 tooling README, rendered from the structured data above.

    One markdown document: what the tooling is, the five verified items,
    the module inventory, the house exit codes, the autofail family, the
    doctrine, and the credential labels. Because every section renders from
    the same constants the self-test asserts, a drift in the data FAILS the
    self-test before it can ship a stale README."""
    lines = [
        "# U07 tooling — field-census law gates (README)",
        "",
        "Shipped under the ENGINE-MANIFEST.json row-54 \"template live "
        "verify (U02)\" shipping doctrine (%s; the U07 family's OWN manifest "
        "row is PENDING — not yet stamped, staged under the "
        "manifest-pending/u02.json · u03.json · u04.json · u05.json "
        "pattern) — dispatched by `scripts/u07_modules/main_skeleton.py` "
        "plus the importable field-census fixtures, the live census reader, "
        "the missing-field finder, the field-type checker, and the "
        "fail-closed field-map loader in `scripts/u07_modules/` — "
        "documented machine-side by this module "
        "(`u07_modules.docs_u07`)."
        % U07_SHIPPING_VERSION,
        "",
        "The U07 family gates the FIELD-CENSUS LAW of the anthology "
        "engine (the package-init doctrine): a provisioned Convert and "
        "Flow location carries EXACTLY 38 contact custom fields under "
        "config/field-map.json provisioning.fields (the 19 base PRD "
        "Section 6 keys + 4 Gap G10 chapter-rewrite-preservation keys + 5 "
        "U8 cover-style keys + 10 U15-absorbed live keys), and the census "
        "binds BY EXACT KEY — a "
        "renamed or re-prefixed key is indistinguishable from an absent "
        "one and BOTH refuse fail-closed. The family's live surfaces "
        "read the census through the PROVEN public rail GET "
        "/locations/{locationId}/customFields — they run only from a "
        "session that can resolve a location-scoped credential BY LABEL "
        "(the client's OWN Convert and Flow private-integration token "
        "with the pit- prefix validated; the location id); the load law, "
        "the all-present law, the golden surface, and the missing/type "
        "law surfaces are OFFLINE (no token, no network). The fixtures "
        "carry SYNTHETIC ids only (fld_golden_000 .. fld_golden_027 — "
        "never a live id, never a real field); every report masks field / "
        "location ids to their last 4 characters and never echoes a "
        "credential-shaped value. A WRITE ACTION (provisioning a missing "
        "field) is Trevor-gated: WITHOUT --execute a missing field is a "
        "STOP (exit 2, AF-AE-FIELD-MISSING) — creation is never silent — "
        "and WITH --execute creation is idempotent create-or-verify with "
        "a byte-exact read-back.",
        "",
        "## The five verified items (MASTER-SPEC U07 — the family's five "
        "gates, in the FIXED order the census law carries them)",
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
    """The on-disk path a README inventory row claims. Every U07 row lives
    next to this module (scripts/u07_modules/)."""
    base = Path(__file__).resolve().parent
    if row.get("place", "").strip("/") == "scripts":
        base = base.parent
    return base / row["name"]

def _self_test_body(dev) -> None:
    dev.write("[docs-u07] pinning: %d verified items, %d modules, "
              "exit codes 0..5\n"
              % (CONTRACT_ITEM_COUNT, CONTRACT_MODULE_COUNT))

    items = VERIFY_ITEMS
    if len(items) != CONTRACT_ITEM_COUNT:
        raise AssertionError(
            "VERIFY_ITEMS carries %d rows, contract is %d — the U07 item "
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
            "MODULES carries %d rows, contract is %d — a U07 module was "
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
    dev.write("[docs-u07] PASS — README data and shipped tree agree "
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
        sys.stderr.write("[docs-u07] SELF-TEST FAILED "
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
        prog="docs_u07.py",
        description="U07 tooling documentation module — README, module "
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
            "verifier": U07_VERIFIER,
            "manifest_row": U07_MANIFEST_ROW,
            "shipping": U07_SHIPPING_VERSION,
            "verify_items": verify_items(),
            "modules": modules(),
            "exit_codes": exit_codes(),
            "af_codes": af_codes(),
            "doctrine": [{"name": n, "text": t} for n, t in DOCTRINE],
            "credential_labels": {k: list(v)
                                  for k, v in CREDENTIAL_LABELS.items()},
            "note": "pure data — no credential value is held or printed; "
                    "the U07 manifest row is PENDING",
        }, indent=2, sort_keys=True))
        return EX_OK
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[docs-u07] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR

if __name__ == "__main__":
    sys.exit(main())
