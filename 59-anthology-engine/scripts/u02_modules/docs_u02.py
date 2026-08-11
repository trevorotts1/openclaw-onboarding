#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u02_modules/docs_u02.py
# U02 TOOLING — THE MODULE DOCSTRING / README, SHIPPED AS AN IMPORTABLE MODULE
# (MASTER-SPEC U02; ENGINE-MANIFEST.json row 54; CHANGELOG v0.1.23,
# 2026-08-11).
# -----------------------------------------------------------------------------
# WHERE THIS SITS: scripts/u02_modules/ — the U02 tooling's documentation
# module, sibling of the checkers and fixtures it documents. It is NOT a
# manifest row: the U02 verifier scripts/live_verify_template.py stays the
# single manifest row, exactly the delivery_report.py sibling-helper pattern
# under ENGINE-MANIFEST.json row 12. Imported BY NAME as u02_modules.docs_u02
# when a consumer wants the tooling's contract surfaces as DATA (module
# inventory, the seven verified items, the house exit codes, the doctrine)
# or its rendered README as text.
#
# WHAT THIS OWNS:
#   1. THE README. The module docstring below IS the U02 tooling README:
#      what the tooling verifies, the module inventory, the exit-code
#      contract, the credential / browser-UA / fail-closed doctrine. The
#      same content is carried as STRUCTURED DATA (VERIFY_ITEMS, MODULES,
#      EXIT_CODES, AF_CODES, DOCTRINE, CREDENTIAL_LABELS) so a consumer can
#      diff against it instead of parsing prose — and readme() renders the
#      README FROM that data, so the two can never drift.
#   2. THE DRIFT GATE. self_test() proves the documentation still matches
#      the shipped tree: every module the README lists exists on disk next
#      to this module (or in scripts/ for the row-54 verifier), all seven
#      items are present exactly once, every house exit code is documented,
#      and the rendered README covers every inventory row. A doc that names
#      a module that does not ship FAILS the self-test (exit 4, the house
#      enforced-violation code) — documentation is data, and stale
#      documentation is drift.
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
#   MASTER-SPEC U02 "ALREADY DONE" list: the operator's OWN Anthology
#   Convert and Flow TEMPLATE location was provisioned by hand; the U02
#   tooling re-reads that template location live and verifies EVERY item of
#   the ALREADY-DONE list against the engine's sources of truth, documenting
#   every delta as JSON output. The live READ is GHL-gated: `verify` runs
#   only from a session that can resolve a template-scoped
#   private-integration token BY LABEL; `plan` and `self-test` are OFFLINE
#   (no token, no network) and ship now.
#   Entry point: scripts/live_verify_template.py (ENGINE-MANIFEST.json
#   row 54, authored_by U02). The u02_modules/ siblings below are its
#   importable checkers, fixtures, and reporters — imported BY NAME per the
#   package contract in __init__.py (pure namespace container).
#
# THE SEVEN VERIFIED ITEMS (MASTER-SPEC U02; every "ALREADY DONE" row):
#   1. PIPELINE name BYTE-EXACT "Anthology Engine" — find-and-bind is BY
#      NAME (MASTERDOC floor 11); a renamed pipeline silently unbinds
#      onboarding. Source of truth: config/field-map.json
#      pipeline.standard_pipeline_name.
#   2. NINE pipeline stages BY NAME, IN ORDER, contiguous positions 0..8
#      (Intake, Avatar, Tone, Title, Outline, Chapter, Cover, Delivered,
#      Assembled) — stage moves resolve BY STAGE NAME at runtime. Source of
#      truth: field-map.json pipeline.standard_stages.
#   3. FORMS count + field mapping — one REQUIRED universal author-intake
#      form (slug universal-intake) plus the engine's one client-facing
#      decision form (slug universal-review; the PRD Section 4 / U8
#      cover-choice form — a NAMED form, deliberately not a snapshot-contract
#      count row) plus the S3 title-selection form (slug title-select;
#      contract role title-subtitle-selection); the universal hidden-field
#      contract (contact_id / anthology_id / stage) on every row. Live count
#      via the internal rail only; without the Firebase refresh token BY
#      LABEL the item is DEFERRED (fail-closed, never fabricated). Source of
#      truth: config/anthology-snapshot-contract.json forms block.
#   4. WORKFLOWS count + folder — the EIGHT tag->notification release
#      workflows (contract workflows.release_notifications) present in ONE
#      workflow folder named exactly "Anthology Engine", each contract
#      workflow present BY NAME exactly once; every contract workflow's
#      trigger is type contact_tag and ACTIVE on its contract trigger_tag
#      byte-exact (trigger surface rail-provided). Rail-gated; other
#      workflows in the same folder are reported (extra_names), never
#      judged. Source of truth: anthology-snapshot-contract.json workflows
#      block.
#   5. INTAKE FIRE trigger scope — the intake front door is a WEBHOOK-TO-
#      ROUTE: config/route-template.json "/hooks/anthology-intake" mapping
#      (match.source "anthology-intake") answers ONLY through the box route,
#      and the snapshot's tag->notification workflow POSTs the intake hook
#      from the {{ custom_values.anthology_webhook_url }} merge — the webhook
#      custom VALUE must exist and hold a REPLACE-ME placeholder (never a
#      real URL), and NO live workflow may inline a real URL past the box
#      route (AF-AE-TEMPLATE-INTAKE-FIRE; never-a-real-token).
#      scope_check.py is the PAYLOAD-side gate: a submission fires the
#      Intake Fire trigger ONLY when it identifies as the universal
#      author-intake form.
#   6. CUSTOM FIELD count + dataTypes — all 28 contract fields present BY
#      KEY, BYTE-EXACT against config/field-map.json provisioning.fields
#      (19 base PRD Section 6 + 4 Gap G10 chapter-rewrite-preservation +
#      5 U8 cover-style keys; 27 LARGE_TEXT + 1 SINGLE_OPTIONS cover choice
#      with the four named options in order: Signature, Bold Editorial,
#      Fine Art, Pure Type). A strict subset is a MISSING (STOP, exit 2);
#      extra/mutated keys fail closed (exit 5).
#   7. CUSTOM VALUES — the four contract location custom values present BY
#      KEY (anthology_webhook_url / anthology_hook_secret / producer /
#      producer_email), each holding ONLY a clearly-labeled placeholder; a
#      real-looking value REFUSES the verify (never-a-real-token).
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE, everywhere in this tooling. The
# private-integration token resolves through anthology_registry (labels:
# CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_API_KEY / GOHIGHLEVEL_API_KEY /
# GOHIGHLEVEL_PIT / GHL_API_KEY — live process env first, then the three
# canonical client env stores); the optional internal-rail Firebase refresh
# token resolves through reg.resolve_firebase_refresh_token (labels:
# ANTHOLOGY_GHL_FIREBASE_REFRESH_TOKEN / GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN /
# GHL_FIREBASE_REFRESH_TOKEN). SET / NOT SET only on every operator surface;
# a token value is NEVER printed. The location id is pinned to the contract
# source_template_location.template_location_id (the operator's OWN template
# location — operator infrastructure config, not a secret) unless
# --location-id overrides, and every report masks it to its LAST 4
# characters (the location id is a tenant identifier, never printed in
# full).
#
# BROWSER UA: every request rides reg.CafClient / reg.InternalRailClient,
# which apply the CAF_BROWSER_UA constant so the Cloudflare edge fronting
# services.leadconnectorhq.com never 1010s the verify (CF error 1010; the
# W0.6 / GK-09 discipline — urllib's default "Python-urllib/x.y" is 403'd
# at the WAF edge before it ever reaches the API). Scope-vs-edge-block
# discrimination: a bare 401/403 is HELD (UpstreamBlockedError), never
# mislabeled as a scope problem; a genuine location-scope denial carrying
# the signature "does not have access to this location" is a STOP (exit 2)
# — live-verified 2026-08-11.
#
# FAIL-CLOSED (the whole point): a missing credential STOPS (exit 2), a
# transport/edge failure is HELD (exit 3), a rail read that cannot be
# performed is DEFERRED (never fabricated — snapshot-cut doctrine) and the
# aggregate is exit 5 unless --allow-deferred (the operator's explicit
# opt-in), and ANY absent / renamed / drifted / real-valued item is a FAIL
# (exit 5). A success is claimed ONLY when every requested item exists on
# the live location AND agrees byte-exact with its source of truth. Every
# deviation is NAMED with its contract path — never a bare "something
# failed".
#
# DOCTRINE (house, per anthology_registry.py / drive_adapter.py): move in
# silence (operator-verbose only); NOTHING Anthropic in any runtime file;
# Convert and Flow naming in every client surface; STDLIB ONLY (urllib +
# json); calls NO model; never a client PII. Self-test failures are exit 4
# (enforced violation, AF-AE-*-ATTACK family) — a tamper never masquerades
# as exit 1.
#
# USAGE (this module's own machine surface — pure data, nothing to leak):
#   python3 docs_u02.py                ONE JSON catalog of the whole tooling
#   python3 docs_u02.py readme         the rendered README (markdown text)
#   python3 docs_u02.py self-test      OFFLINE drift gate over the docs vs
#                                      the shipped tree; 0 clean, 4 drift
# =============================================================================
"""docs_u02.py -- README / module docstring for the U02 tooling, as an
importable fail-closed pure-data module: the GHL template live re-verify
(ENGINE-MANIFEST.json row 54), its seven verified items, the u02_modules
inventory, the house exit codes, and the credential / browser-UA / doctrine
contracts. Performs no I/O at import and holds no credential; readme() is
rendered from the same structured data the self-test asserts against, so
documentation and data cannot drift."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# The fixed report contract (mirrors the golden-fixture naming discipline).
# ---------------------------------------------------------------------------
DOC_CONTRACT = "anthology-engine-u02-tooling-docs"
SCHEMA_VERSION = 1

# The U02 verifier is the single manifest row; the u02_modules/ siblings
# ship as non-manifest helpers (the delivery_report.py row-12 pattern).
U02_VERIFIER = "live_verify_template.py"
U02_MANIFEST_ROW = 54
U02_TEMPLATE_LOCATION = "2HIKGNgsixWx0yds7Qnx"  # contract
# source_template_location.template_location_id — operator infrastructure
# config, never a secret; reports mask it to the last 4 characters.
U02_SHIPPING_VERSION = "v0.1.23 (2026-08-11)"

# ---------------------------------------------------------------------------
# THE SEVEN VERIFIED ITEMS (MASTER-SPEC U02 "ALREADY DONE" list). Item
# numbers are load-bearing (positions 1..7, exactly seven — self-test
# pins the count); the title is the README heading, asserts the fail-closed
# claim, source the engine's source of truth, and fails the operator surface
# on drift.
# ---------------------------------------------------------------------------
VERIFY_ITEMS = (
    {
        "item": 1,
        "title": "Pipeline name BYTE-EXACT 'Anthology Engine'",
        "asserts": ("find-and-bind is BY NAME (MASTERDOC floor 11); a renamed "
                    "pipeline silently unbinds onboarding"),
        "source": "config/field-map.json pipeline.standard_pipeline_name",
        "fails": "AF-AE-TEMPLATE-PIPELINE-MISSING (STOP, exit 2)",
    },
    {
        "item": 2,
        "title": "Nine stages BY NAME IN ORDER, contiguous positions 0..8",
        "asserts": ("Intake, Avatar, Tone, Title, Outline, Chapter, Cover, "
                    "Delivered, Assembled — stage moves resolve BY STAGE NAME "
                    "at runtime"),
        "source": "config/field-map.json pipeline.standard_stages",
        "fails": "AF-AE-TEMPLATE-STAGE-DRIFT (exit 5)",
    },
    {
        "item": 3,
        "title": "Forms count + field mapping",
        "asserts": ("one REQUIRED universal author-intake form (slug "
                    "universal-intake) + the engine's one client-facing "
                    "decision form (slug universal-review; the PRD Section 4 / "
                    "U8 cover-choice form — a NAMED form, deliberately not a "
                    "snapshot-contract count row) + the S3 title-selection form "
                    "(slug title-select; contract role title-subtitle-"
                    "selection); universal hidden-field contract "
                    "(contact_id / anthology_id / stage) on every row"),
        "source": "config/anthology-snapshot-contract.json forms block",
        "fails": "rail-gated: DEFERRED without the Firebase refresh token BY "
                 "LABEL — never fabricated",
    },
    {
        "item": 4,
        "title": "Workflows count + folder",
        "asserts": ("the EIGHT tag->notification release workflows "
                    "(workflows.release_notifications) in ONE folder named "
                    "exactly 'Anthology Engine', each present BY NAME exactly "
                    "once; every contract trigger type contact_tag and ACTIVE "
                    "on its contract trigger_tag byte-exact"),
        "source": "config/anthology-snapshot-contract.json workflows block",
        "fails": "rail-gated: DEFERRED without the internal rail — never "
                 "fabricated",
    },
    {
        "item": 5,
        "title": "Intake Fire trigger scope",
        "asserts": ("the intake front door is a WEBHOOK-TO-ROUTE: "
                    "config/route-template.json '/hooks/anthology-intake' "
                    "mapping (match.source 'anthology-intake') answers ONLY "
                    "through the box route; the workflow POSTs the intake hook "
                    "from the {{ custom_values.anthology_webhook_url }} merge "
                    "— the webhook custom VALUE exists and holds a REPLACE-ME "
                    "placeholder; NO live workflow inlines a real URL past the "
                    "box route"),
        "source": "config/route-template.json + anthology-snapshot-contract.json "
                  "location_custom_values",
        "fails": "AF-AE-TEMPLATE-INTAKE-FIRE (exit 5); payload side gated by "
                 "scope_check.py (form == 'universal-intake')",
    },
    {
        "item": 6,
        "title": "Custom field count + dataTypes",
        "asserts": ("all 28 contract fields present BY KEY, BYTE-EXACT "
                    "(19 base PRD Section 6 + 4 Gap G10 rewrite-preservation + "
                    "5 U8 cover-style; 27 LARGE_TEXT + 1 SINGLE_OPTIONS cover "
                    "choice with the four named options in order: Signature, "
                    "Bold Editorial, Fine Art, Pure Type); a strict subset is "
                    "a MISSING, extra/mutated keys fail closed"),
        "source": "config/field-map.json provisioning.fields",
        "fails": "AF-AE-TEMPLATE-FIELD-MISSING (STOP, exit 2) / "
                 "AF-AE-TEMPLATE-KEY-MISMATCH (exit 5)",
    },
    {
        "item": 7,
        "title": "Custom values",
        "asserts": ("the four contract location custom values present BY KEY "
                    "(anthology_webhook_url / anthology_hook_secret / producer "
                    "/ producer_email), each holding ONLY a clearly-labeled "
                    "placeholder"),
        "source": "config/anthology-snapshot-contract.json "
                  "location_custom_values.required",
        "fails": "AF-AE-TEMPLATE-CUSTOM-VALUE-REAL (exit 5) — never-a-real-token",
    },
)

# ---------------------------------------------------------------------------
# THE MODULE INVENTORY. `place` names the directory relative to this module
# (the u02_modules package itself, or scripts/ for the row-54 verifier);
# self-test proves each name exists at that place. `role` is the one-line
# contract each module owns; `offline` names the credential-free surface;
# `exit_codes` follows the house convention (0/1/2/3/5, 4 = self-test).
# ---------------------------------------------------------------------------
MODULES = (
    {
        "name": "live_verify_template.py",
        "place": "scripts/",
        "manifest_row": U02_MANIFEST_ROW,
        "role": ("the U02 verifier — the SINGLE manifest row. Full seven-item "
                 "live verify of the template location; subcommands verify / "
                 "plan / self-test; aggregate fail-closed (any FAIL -> exit 5; "
                 "DEFERRED counts as FAIL unless --allow-deferred); self-test = "
                 "golden + 16 attack fixtures, mutation proof (exit 4)"),
        "offline": "plan + self-test (no token, no network)",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "__init__.py",
        "place": "scripts/u02_modules/",
        "manifest_row": None,
        "role": ("fail-closed EMPTY package init — pure namespace container, "
                 "no runtime code; modules are imported BY NAME"),
        "offline": "trivially — it is empty",
        "exit_codes": "n/a (no executable surface)",
    },
    {
        "name": "pipeline_check.py",
        "place": "scripts/u02_modules/",
        "manifest_row": None,
        "role": ("the smallest fail-closed live probe: READS the location's "
                 "pipelines and reports whether one named BYTE-EXACT "
                 "'Anthology Engine' exists (check_pipeline_name; name only, "
                 "no stage judgment — the sibling of "
                 "live_verify_template.check_pipeline)"),
        "offline": "self-test against fixture pipeline sets",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "stages_check.py",
        "place": "scripts/u02_modules/",
        "manifest_row": None,
        "role": ("the nine-stage BY NAME IN ORDER check, positions 0..8, "
                 "fail-closed on absent/renamed/reordered/renumbered stages "
                 "(the reorder attack proves the list-order comparison); "
                 "returns the machine contract {ok, count, names}"),
        "offline": "self-test against fixture stage sets (zero writes, "
                   "mutation log)",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "fields_check.py",
        "place": "scripts/u02_modules/",
        "manifest_row": None,
        "role": ("byte-exact live field-key check: EVERY intended key in "
                 "field-map.json provisioning.fields present live with a "
                 "byte-equal server fieldKey, no contract-foreign keys, and "
                 "resolved-slot id consistency when the map is stamped; "
                 "masked-location JSON report (last 4 chars only)"),
        "offline": "self-test + plan (offline, no token)",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "golden_fields.py",
        "place": "scripts/u02_modules/",
        "manifest_row": None,
        "role": ("the golden 28-record field-list fixture, derived "
                 "BYTE-FOR-BYTE from field-map.json (never a hardcoded key "
                 "list); MappingProxyType-frozen canonical payload, tuple "
                 "options; payload() REFUSES (exit 5) on any contract drift"),
        "offline": "entirely — pure data + builders",
        "exit_codes": "0/1/5 (fixture refusal); 4 self-test",
    },
    {
        "name": "forms_check.py",
        "place": "scripts/u02_modules/",
        "manifest_row": None,
        "role": ("the three named forms check (universal-intake / "
                 "universal-review / title-select) + universal hidden-field "
                 "contract on every row, via the proven internal rail "
                 "listing (/workflow/{loc}/list?limit=200 rows of type != "
                 "'workflow'); a location-scope denial signature STOPS "
                 "(exit 2) — live-verified 2026-08-11"),
        "offline": "self-test (no network, no secrets)",
        "exit_codes": "0/1/2/3/5",
    },
    {
        "name": "golden_forms.py",
        "place": "scripts/u02_modules/",
        "manifest_row": None,
        "role": ("the golden three-form payload for the sibling self-tests — "
                 "pure data; import-time coherence gate "
                 "(validate_golden_forms) REFUSES on drift; never imports "
                 "anthology_registry (a fixture must be importable in any "
                 "process, credential-free)"),
        "offline": "entirely — pure data",
        "exit_codes": "0 clean; 4 self-test violation",
    },
    {
        "name": "workflows_check.py",
        "place": "scripts/u02_modules/",
        "manifest_row": None,
        "role": ("workflows count + folder check: the EIGHT contract "
                 "release-notification workflows in ONE folder named exactly "
                 "'Anthology Engine', each BY NAME exactly once; triggers "
                 "contact_tag and ACTIVE on their contract tags when the rail "
                 "provides the trigger surface (else HELD — never a partial "
                 "pass); other folder workflows reported (extra_names), never "
                 "judged; returns {ok, count, names}"),
        "offline": "self-test; live read rail-gated (DEFERRED without the "
                   "Firebase refresh token BY LABEL)",
        "exit_codes": "0/1/2/3/5",
    },
    {
        "name": "custom_values_check.py",
        "place": "scripts/u02_modules/",
        "manifest_row": None,
        "role": ("the four REPLACE-ME location custom values, checked "
                 "READ-ONLY both directions: a missing key is a FAIL, an "
                 "extra/renamed/REAL-valued key is a FAIL (never-a-real-"
                 "token); returns {ok, found, missing} — keys by name only, "
                 "a value is never printed"),
        "offline": "self-test",
        "exit_codes": "0/1/2/3/5",
    },
    {
        "name": "scope_check.py",
        "place": "scripts/u02_modules/",
        "manifest_row": None,
        "role": ("Intake Fire trigger scope gate — a pure, side-effect-free "
                 "predicate (no network, no writes, no registry import): the "
                 "Intake Fire trigger fires ONLY when the submission "
                 "identifies as the universal author-intake form "
                 "(form == 'universal-intake'); returns (ok, filter_set) and "
                 "never prints the payload or any field value"),
        "offline": "entirely — pure predicate",
        "exit_codes": "n/a (module returns a 2-tuple; no CLI surface)",
    },
    {
        "name": "delta_reporter.py",
        "place": "scripts/u02_modules/",
        "manifest_row": None,
        "role": ("the ONE JSON delta-report contract: per-item checks map, a "
                 "delta list that NAMES EVERY mismatch with its contract "
                 "path, the fail-closed aggregate verdict, and the "
                 "fail_closed block; secret-hygiene sanitizer REFUSES a "
                 "credential-shaped value rather than emit a redacted guess; "
                 "diff_expected_live / build_report / emit_report"),
        "offline": "self-test + plan",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "main_skeleton.py",
        "place": "scripts/u02_modules/",
        "manifest_row": None,
        "role": ("the check-module dispatcher CLI: imports the sibling check "
                 "modules BY NAME, normalizes their per-check (status, "
                 "detail, expected, live) records into ONE JSON report, and "
                 "resolves the fail-closed aggregate exit code exactly as "
                 "live_verify_template.py does — it carries NO check logic "
                 "itself"),
        "offline": "plan + self-test",
        "exit_codes": "0/1/2/3/4/5",
    },
)

# ---------------------------------------------------------------------------
# HOUSE EXIT CODES (0/1/2/3/5; 4 = enforced violation). The exact contract
# every U02 checker and fixture commits to; self-test pins all six.
# ---------------------------------------------------------------------------
EXIT_CODES = {
    0: "verified success — all checks PASS (also plan / dry-run / self-test)",
    1: "unexpected error (top-level guard; never a secret leak)",
    2: ("STOP refusal — label NOT SET / non-pit- value / usage / a contract "
        "section missing / a pipeline or field section absent live"),
    3: ("HELD — Convert and Flow API unreachable incl. the Cloudflare edge "
        "403 (CF error 1010) or the internal rail unavailable; retryable, "
        "never mislabeled as a scope problem"),
    4: ("self-test FAILED (AF-AE-*-ATTACK family, enforced violation) — a "
        "tamper never masquerades as exit 1"),
    5: ("mismatch / fail-closed default — drift, extra or mutated keys, a "
        "real-looking custom value, or a DEFERRED live check without "
        "--allow-deferred"),
}

# ---------------------------------------------------------------------------
# THE AF-AE-TEMPLATE-* AUTofail family (ENGINE-MANIFEST.json, stage
# "template live verify (U02)", enforced_by live_verify_template.py).
# ---------------------------------------------------------------------------
AF_CODES = (
    ("AF-AE-TEMPLATE-PIPELINE-MISSING", 2,
     "the standard pipeline is absent or renamed on the template location — "
     "find-and-bind would fail silently (STOP)"),
    ("AF-AE-TEMPLATE-STAGE-DRIFT", 5,
     "a present pipeline is missing a contract stage or carries an "
     "extra/renamed/out-of-order stage"),
    ("AF-AE-TEMPLATE-FIELD-MISSING", 2,
     "a contract custom-field key is absent on the live location (STOP)"),
    ("AF-AE-TEMPLATE-KEY-MISMATCH", 5,
     "the field-key set differs in any other way (extra/mutated), a "
     "dataType/options drift, or a real-looking custom value"),
    ("AF-AE-TEMPLATE-CUSTOM-VALUE-REAL", 5,
     "a custom value holds a real-looking value (never-a-real-token)"),
    ("AF-AE-TEMPLATE-INTAKE-FIRE", 5,
     "the intake-fire side drifted: the webhook custom value absent/misplaced, "
     "or a live workflow inlines an intake URL instead of the "
     "{{ custom_values.anthology_webhook_url }} merge"),
    ("AF-AE-TEMPLATE-ATTACK", 4,
     "an attack fixture tripped the OFFLINE self-test (enforced violation)"),
)

# ---------------------------------------------------------------------------
# DOCTRINE — the house rules the whole U02 tooling commits to, as data so
# the README renders them from the same source the self-test asserts.
# ---------------------------------------------------------------------------
DOCTRINE = (
    ("Fail-closed", "a missing contract section, a malformed input, an "
     "unreadable source, or a live read that cannot be completed is a "
     "REFUSAL or a recorded FAIL — never a blind pass, never a fabricated "
     "success; a strict subset is a MISSING, never a pass"),
    ("Secrets", "credentials resolve BY LABEL only (SET / NOT SET); a token "
     "value is never printed, echoed, or reflected in any surface; the "
     "location id is MASKED to its last 4 characters in every report; "
     "never-a-real-token — template custom values must hold REPLACE-ME "
     "placeholders and a real-looking value REFUSES the verify"),
    ("Browser UA", "every request to GoHighLevel / Convert and Flow "
     "(services.leadconnectorhq.com, Cloudflare-fronted) rides "
     "reg.CafClient / reg.InternalRailClient, which apply CAF_BROWSER_UA — "
     "urllib's default 'Python-urllib/x.y' is 403'd at the WAF edge "
     "(CF error 1010) before it ever reaches the API (W0.6 / GK-09)"),
    ("Scope vs edge", "a bare 401/403 is HELD (UpstreamBlockedError), never "
     "mislabeled as a scope problem; a genuine location-scope denial "
     "(\"does not have access to this location\") is a STOP (exit 2)"),
    ("DEFERRED, never fabricated", "workflow/forms live reads ride the "
     "internal rail (backend.leadconnectorhq.com /workflow/{loc}/list?limit="
     "200 — the proven surface); without the Firebase refresh token BY LABEL "
     "those items are DEFERRED and the aggregate is fail-closed (exit 5) "
     "unless --allow-deferred (the operator's explicit opt-in)"),
    ("Move in silence", "operator-verbose only; NOTHING Anthropic in any "
     "runtime file; Convert and Flow naming in every client surface; STDLIB "
     "ONLY (urllib + json); calls NO model; never a client PII"),
)

# ---------------------------------------------------------------------------
# CREDENTIAL LABELS — BY LABEL ONLY. These are the label NAMES the tooling
# resolves through anthology_registry (live process env first, then the
# three canonical client env stores). A label is a name, never a value; the
# values they resolve to are never held here and never printed anywhere.
# ---------------------------------------------------------------------------
CREDENTIAL_LABELS = {
    "pit": (
        "CONVERT_AND_FLOW_PIT",
        "CONVERT_AND_FLOW_API_KEY",
        "GOHIGHLEVEL_API_KEY",
        "GOHIGHLEVEL_PIT",
        "GHL_API_KEY",
    ),
    "firebase_refresh": (
        "ANTHOLOGY_GHL_FIREBASE_REFRESH_TOKEN",
        "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN",
        "GHL_FIREBASE_REFRESH_TOKEN",
    ),
}

# Pinned counts (the fixture-counting discipline of golden_fields.py: a
# drifted inventory is drift, never tolerated). Adding a module to the U02
# tooling REQUIRES adding it here AND to the README's inventory.
CONTRACT_ITEM_COUNT = 7
CONTRACT_MODULE_COUNT = 13


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
    """The AF-AE-TEMPLATE-* autofail family as plain (code, exit, meaning)
    tuples in a mutable list."""
    return list(AF_CODES)

# ---------------------------------------------------------------------------
# The rendered README — built FROM the data, so prose can never drift from
# the contract. This is the machine-readable form of the module docstring.
# ---------------------------------------------------------------------------
def readme() -> str:
    """The U02 tooling README, rendered from the structured data above.

    One markdown document: what the tooling is, the seven verified items,
    the module inventory, the house exit codes, the autofail family, the
    doctrine, and the credential labels. Because every section renders from
    the same constants the self-test asserts, a drift in the data FAILS the
    self-test before it can ship a stale README."""
    lines = [
        "# U02 tooling — GHL template live re-verify (README)",
        "",
        "Shipped as `scripts/live_verify_template.py` (ENGINE-MANIFEST.json "
        "row %d, authored_by U02; %s) plus the importable sibling checkers, "
        "fixtures, and reporters in `scripts/u02_modules/` — documented "
        "machine-side by this module (`u02_modules.docs_u02`)."
        % (U02_MANIFEST_ROW, U02_SHIPPING_VERSION),
        "",
        "The live READ is GHL-gated; the tooling ships now. `verify` runs "
        "only from a session that can resolve a template-scoped "
        "private-integration token BY LABEL; `plan` and `self-test` are "
        "OFFLINE (no token, no network). The template location is the "
        "contract's source_template_location (the operator's OWN template, "
        "never a client location) and every report masks it to the last 4 "
        "characters.",
        "",
        "## The seven verified items (MASTER-SPEC U02 'ALREADY DONE' list)",
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
        lines.append("- `%s` (%s) — %s Offline surface: %s. Exit codes: %s."
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
        "## AF-AE-TEMPLATE-* autofail family",
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
    """The on-disk path a README inventory row claims. u02_modules/ rows
    live next to this module; the row-54 verifier lives in scripts/."""
    base = Path(__file__).resolve().parent
    if row.get("place", "").strip("/") == "scripts":
        base = base.parent
    return base / row["name"]

def _self_test_body(dev) -> None:
    dev.write("[docs-u02] pinning: %d verified items, %d modules, "
              "exit codes 0..5\n"
              % (CONTRACT_ITEM_COUNT, CONTRACT_MODULE_COUNT))

    items = VERIFY_ITEMS
    if len(items) != CONTRACT_ITEM_COUNT:
        raise AssertionError(
            "VERIFY_ITEMS carries %d rows, contract is %d — the U02 item "
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
            "MODULES carries %d rows, contract is %d — a U02 module was "
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
    if not exits <= {2, 4, 5}:
        raise AssertionError(
            "AF_AES template family must map only onto STOP/self-test/"
            "mismatch exits (2/4/5), got %s" % sorted(exits))

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
    dev.write("[docs-u02] PASS — README data and shipped tree agree "
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
        sys.stderr.write("[docs-u02] SELF-TEST FAILED "
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
        prog="docs_u02.py",
        description="U02 tooling documentation module — README, module "
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
            "verifier": U02_VERIFIER,
            "manifest_row": U02_MANIFEST_ROW,
            "template_location": "%s%s" % ("...", U02_TEMPLATE_LOCATION[-4:]),
            "shipping": U02_SHIPPING_VERSION,
            "verify_items": verify_items(),
            "modules": modules(),
            "exit_codes": exit_codes(),
            "af_codes": af_codes(),
            "doctrine": [{"name": n, "text": t} for n, t in DOCTRINE],
            "credential_labels": {k: list(v)
                                  for k, v in CREDENTIAL_LABELS.items()},
            "note": "pure data — no credential value is held or printed; "
                    "the template location is masked to its last 4 chars",
        }, indent=2, sort_keys=True))
        return EX_OK
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[docs-u02] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR

if __name__ == "__main__":
    sys.exit(main())
