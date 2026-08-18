#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u03_modules/docs_u03.py
# U03 TOOLING — THE MODULE DOCSTRING / README, SHIPPED AS AN IMPORTABLE MODULE
# (MASTER-SPEC U03; the u02_modules/docs_u02.py row-54-sibling pattern —
# ENGINE-MANIFEST.json row 54 stays the single manifest row; CHANGELOG v0.1.23,
# 2026-08-11, with the U03 tooling shipping now under the same shipping law).
# -----------------------------------------------------------------------------
# WHERE THIS SITS: scripts/u03_modules/ — the U03 tooling's documentation
# module, sibling of the checkers, fixtures, and applier it documents. It is
# NOT a manifest row: the U03 verifier driver scripts/u03_modules/main_skeleton.py
# stays the single manifest row (the delivery_report.py sibling-helper pattern
# under ENGINE-MANIFEST.json row 12, exactly as u02_modules/docs_u02.py
# documents the row-54 U02 verifier). Imported BY NAME as u03_modules.docs_u03
# when a consumer wants the tooling's contract surfaces as DATA (module
# inventory, the four verified items, the house exit codes, the doctrine) or
# its rendered README as text.
#
# WHAT THIS OWNS:
#   1. THE README. The module docstring below IS the U03 tooling README:
#      what the tooling verifies, the module inventory, the exit-code
#      contract, the credential / browser-UA / fail-closed doctrine. The
#      same content is carried as STRUCTURED DATA (VERIFY_ITEMS, MODULES,
#      EXIT_CODES, AF_CODES, DOCTRINE, CREDENTIAL_LABELS) so a consumer can
#      diff against it instead of parsing prose — and readme() renders the
#      README FROM that data, so the two can never drift.
#   2. THE DRIFT GATE. self_test() proves the documentation still matches
#      the shipped tree: every module the README lists exists on disk next
#      to this module (or in scripts/ for the row-54 verifier), all four
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
#   MASTER-SPEC U03 — the template location's DRIFT-PRONE live state. The U02
#   tooling verified the ALREADY-DONE template location against the engine's
#   sources of truth; the U03 family RE-verifies the drift-prone pieces the
#   SAME template is continuously exposed to — pipeline name, stage set,
#   custom values, workflow folder, intake route — WITHOUT touching the U02
#   scope (u03_modules/__init__.py: the package is the U03 verification
#   surface for the ALREADY-DONE list's drift-prone state, read and
#   re-verified live). The same seven-item U02 contract surface is mirrored:
#   check modules are imported BY NAME per the package contract, the LIVE
#   READ is GHL-gated (`verify` runs only from a session that can resolve a
#   template-scoped private-integration token BY LABEL; `plan` / `dry-run`
#   and `self-test` are OFFLINE and ship now), and the aggregate is
#   fail-closed — the manifest row-54 shipping doctrine.
#   Dispatcher: scripts/u03_modules/main_skeleton.py (the manifest row, U03
#   shipping under the row-54 law).
#
# THE FOUR VERIFIED ITEMS (MASTER-SPEC U03 "DRIFT-PRONE" list):
#   1. PIPELINE name BYTE-EXACT "Anthology Engine" — find-and-bind is BY
#      NAME (MASTERDOC floor 11); a renamed pipeline silently unbinds
#      onboarding. Source of truth: config/field-map.json
#      pipeline.standard_pipeline_name (SPEC M8 — never hardcoded).
#   2. NINE pipeline stages BY NAME, IN ORDER, contiguous positions 0..8
#      (Intake, Avatar, Tone, Title, Outline, Chapter, Cover, Delivered,
#      Assembled) — stage moves resolve BY STAGE NAME at runtime. Source of
#      truth: field-map.json pipeline.standard_stages.
#   3. The four contract location CUSTOM VALUES (anthology_webhook_url /
#      anthology_hook_secret / producer / producer_email), present BY KEY,
#      each holding ONLY a clearly-labeled REPLACE-ME placeholder — a
#      real-looking value REFUSES the verify (never-a-real-token). Source of
#      truth: config/anthology-snapshot-contract.json
#      location_custom_values.required.
#   4. WORKFLOWS count + folder — the EIGHT tag->notification release
#      workflows (contract workflows.release_notifications) present in ONE
#      workflow folder named exactly "Anthology Engine", each contract
#      workflow present BY NAME exactly once; every contract workflow's
#      trigger is type contact_tag and ACTIVE on its contract trigger_tag
#      byte-exact. Rail-gated: without the internal rail (Firebase refresh
#      token BY LABEL) the item is DEFERRED — never fabricated. Source of
#      truth: anthology-snapshot-contract.json workflows block.
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
# location — operator infrastructure config, never a secret) unless
# --location-id overrides, and every report masks it to its LAST 4
# characters (the location id is a tenant identifier, never printed in
# full). The applier is the ONE write surface of the family, and it REFUSES
# to write without the operator's explicit --execute; without it the apply
# is a read-only dry-run.
#
# BROWSER UA: every request rides reg.CafClient / reg.InternalRailClient
# (and the applier's own v3 client reusing reg._auth_denial_kind), which
# apply the CAF_BROWSER_UA constant so the Cloudflare edge fronting
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
# performed is DEFERRED (never fabricated — snapshot-cut doctrine), and ANY
# absent / renamed / drifted / real-valued item is a FAIL (exit 5). The U03
# EMPTY-LISTING state is the family's signature attack: a pipelines listing
# that serves [] is indistinguishable from a renamed pipeline at the find
# step — BOTH bind nothing — so the empty listing is REFUSED with its own
# loud operator STOP, never a silent pass, never a fabricated success. A
# success is claimed ONLY when every requested item exists on the live
# location AND agrees byte-exact with its source of truth. Every deviation
# is NAMED with its contract path — never a bare "something failed".
#
# DOCTRINE (house, per anthology_registry.py / drive_adapter.py): move in
# silence (operator-verbose only); NOTHING Anthropic in any runtime file;
# Convert and Flow naming in every client surface; STDLIB ONLY (urllib +
# json); calls NO model; never a client PII. Self-test failures are exit 4
# (enforced violation, AF-AE-*-ATTACK family) — a tamper never masquerades
# as exit 1. The rename applier adds the write doctrine: --execute is the
# ONLY flag that performs the PUT; every other invocation is read-only.
#
# USAGE (this module's own machine surface — pure data, nothing to leak):
#   python3 docs_u03.py                ONE JSON catalog of the whole tooling
#   python3 docs_u03.py readme         the rendered README (markdown text)
#   python3 docs_u03.py self-test      OFFLINE drift gate over the docs vs
#                                      the shipped tree; 0 clean, 4 drift
# =============================================================================
"""docs_u03.py -- README / module docstring for the U03 tooling, as an
importable fail-closed pure-data module: the GHL template DRIFT-PRONE live
re-verify (ENGINE-MANIFEST.json row 54, dispatched by
u03_modules/main_skeleton.py), its four verified items, the u03_modules
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
DOC_CONTRACT = "anthology-engine-u03-tooling-docs"
SCHEMA_VERSION = 1

# The U03 dispatcher is the manifest row under the U02 row-54 shipping law;
# the u03_modules/ siblings ship as non-manifest helpers (the
# delivery_report.py row-12 pattern, exactly the docs_u02.py sibling).
U03_VERIFIER = "main_skeleton.py"
U03_MANIFEST_ROW = 54
U03_TEMPLATE_LOCATION = "2HIKGNgsixWx0yds7Qnx"  # contract
# source_template_location.template_location_id — operator infrastructure
# config, never a secret; reports mask it to the last 4 characters.
U03_SHIPPING_VERSION = "v0.1.23 (2026-08-11)"

# ---------------------------------------------------------------------------
# THE FOUR VERIFIED ITEMS (MASTER-SPEC U03 "DRIFT-PRONE" list). Item numbers
# are load-bearing (positions 1..4, exactly four — self-test pins the
# count); the title is the README heading, asserts the fail-closed claim,
# source the engine's source of truth, and fails the operator surface on
# drift. The U03 family mirrors the U02 seven-item contract surface but
# re-verifies ONLY the drift-prone subset: pipeline name, stage set, custom
# values, workflow folder (config_loader.py is the shared (location, name)
# config surface, house_rules.py the shared constants surface, and the
# applier is the gated write surface).
# ---------------------------------------------------------------------------
VERIFY_ITEMS = (
    {
        "item": 1,
        "title": "Pipeline name BYTE-EXACT 'Anthology Engine'",
        "asserts": ("find-and-bind is BY NAME (MASTERDOC floor 11; "
                    "config_loader.py pins the (location, expected name) "
                    "pair); a renamed pipeline silently unbinds onboarding — "
                    "and a RENAMED pipeline is indistinguishable from an "
                    "ABSENT one to find-by-name, so BOTH refuse"),
        "source": "config/field-map.json pipeline.standard_pipeline_name",
        "fails": "AF-AE-TEMPLATE-PIPELINE-MISSING (STOP, exit 2); the U03 "
                 "EMPTY-LISTING attack ({\"pipelines\": []}) is REFUSED with "
                 "its own loud STOP — never a silent pass",
    },
    {
        "item": 2,
        "title": "Nine stages BY NAME IN ORDER, contiguous positions 0..8",
        "asserts": ("Intake, Avatar, Tone, Title, Outline, Chapter, Cover, "
                    "Delivered, Assembled — stage moves resolve BY STAGE NAME "
                    "at runtime; a PURE RENAME keeps every stage intact, so "
                    "the drift is caught on the name, never on the stages"),
        "source": "config/field-map.json pipeline.standard_stages",
        "fails": "AF-AE-TEMPLATE-STAGE-DRIFT (exit 5)",
    },
    {
        "item": 3,
        "title": "Custom values",
        "asserts": ("the four contract location custom values present BY KEY "
                    "(anthology_webhook_url / anthology_hook_secret / producer "
                    "/ producer_email), each holding ONLY a clearly-labeled "
                    "REPLACE-ME placeholder — both key-set directions fail "
                    "closed: missing keys FAIL, extra/renamed/real-valued "
                    "keys FAIL (never-a-real-token); keys only on every "
                    "surface, a value is never printed"),
        "source": "config/anthology-snapshot-contract.json "
                  "location_custom_values.required",
        "fails": "AF-AE-TEMPLATE-CUSTOM-VALUE-REAL (exit 5) — never-a-real-token",
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
)

# ---------------------------------------------------------------------------
# THE MODULE INVENTORY. `place` names the directory relative to this module
# (the u03_modules package itself, or scripts/ for the row-54 verifier);
# self-test proves each name exists at that place. `role` is the one-line
# contract each module owns; `offline` names the credential-free surface;
# `exit_codes` follows the house convention (0/1/2/3/5, 4 = self-test).
# ---------------------------------------------------------------------------
MODULES = (
    {
        "name": "main_skeleton.py",
        "place": "scripts/u03_modules/",
        "manifest_row": U03_MANIFEST_ROW,
        "role": ("the U03 check-module dispatcher — the SINGLE manifest row "
                 "under the U02 row-54 shipping law. Imports the check "
                 "modules BY NAME, normalizes their heterogeneous surfaces "
                 "into ONE JSON report, and resolves the fail-closed "
                 "aggregate exit code exactly as the U02 sibling; carries NO "
                 "check logic itself; subcommands verify / dry-run (offline "
                 "plan) / self-test; the house_rules.py / config_loader.py "
                 "shared surfaces keep the laws single-implementation"),
        "offline": "dry-run + self-test (no token, no network)",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "__init__.py",
        "place": "scripts/u03_modules/",
        "manifest_row": None,
        "role": ("fail-closed EMPTY package init — pure namespace container, "
                 "no runtime code; modules are imported BY NAME; records the "
                 "package doctrine (fail-closed, secrets by label, browser-UA "
                 "law, move in silence)"),
        "offline": "trivially — it is empty",
        "exit_codes": "n/a (no executable surface)",
    },
    {
        "name": "config_loader.py",
        "place": "scripts/u03_modules/",
        "manifest_row": None,
        "role": ("the shared OFFLINE (location id, expected name) config "
                 "surface: contract source_template_location.template_location_"
                 "id + field-map pipeline.standard_pipeline_name cross-checked "
                 "byte-exact against the snapshot contract; a drifted pair is "
                 "REFUSED (ConfigError, exit 2); re-exports BROWSER_UA = "
                 "reg.CAF_BROWSER_UA so a caller wiring its own urllib "
                 "surface cannot forget the CF-1010 law"),
        "offline": "entirely — no network, zero token surface",
        "exit_codes": "0/1/2",
    },
    {
        "name": "name_reader.py",
        "place": "scripts/u03_modules/",
        "manifest_row": None,
        "role": ("the read companion to the U02/U03 name check: GETs the "
                 "location's pipelines through Convert and Flow (v2) with the "
                 "client's OWN token and extracts EVERY pipeline name, sorted "
                 "for deterministic diffing — NO judgment about which name is "
                 "standard (that is the checker's job); an empty list is a "
                 "valid live answer, any unreadable shape raises "
                 "MalformedPayload (STOP) — never a silent empty"),
        "offline": "plan + self-test (no token, no network)",
        "exit_codes": "0/1/2/3/4",
    },
    {
        "name": "rename_checker.py",
        "place": "scripts/u03_modules/",
        "manifest_row": None,
        "role": ("the smallest fail-closed live probe of the U03 family: "
                 "REPORTS whether a pipeline named BYTE-EXACT 'Anthology "
                 "Engine' exists (check_name -> dict); a RENAMED pipeline is "
                 "indistinguishable from an ABSENT one to find-by-name "
                 "(MASTERDOC floor 11), so BOTH refuse — the check NEVER "
                 "fails open and NEVER auto-heals a drift"),
        "offline": "plan + self-test against fixture pipeline sets",
        "exit_codes": "0/1/2/3/5",
    },
    {
        "name": "golden_correct.py",
        "place": "scripts/u03_modules/",
        "manifest_row": None,
        "role": ("the canonical in-memory payload of the engine's BYTE-EXACT "
                 "contract name, derived BYTE-FOR-BYTE from field-map.json "
                 "standard_pipeline_name (never hardcoded, SPEC M8); "
                 "mappingproxy-frozen canon + deep-copied payload surfaces; "
                 "payload() REFUSES (exit 5) on any contract drift"),
        "offline": "entirely — pure data + builders",
        "exit_codes": "0/1/5 (fixture refusal); 4 self-test",
    },
    {
        "name": "golden_wrong.py",
        "place": "scripts/u03_modules/",
        "manifest_row": None,
        "role": ("the canonical RENAMED-STATE payload of the U03 name-law "
                 "family: the standard pipeline's name overridden to the "
                 "WRONG name 'Anthology Writer' (Skill 54, the engine's "
                 "sibling skill — the most plausible drift); a PURE RENAME "
                 "keeping all nine stages; detect() REFUSES on the wrong "
                 "name ABSENT / contract name present (ambiguous both-present) "
                 "/ malformed payload"),
        "offline": "entirely — pure data + builders",
        "exit_codes": "0/1/5 (fixture refusal); 4 self-test",
    },
    {
        "name": "attack_no_pipeline.py",
        "place": "scripts/u03_modules/",
        "manifest_row": None,
        "role": ("the NO-PIPELINE ATTACK FIXTURE — the fail-closed "
                 "EMPTY-LISTING gate: ANY listing without a standard "
                 "Anthology pipeline BYTE-EXACT, above all the EMPTY listing "
                 "({\"pipelines\": []}, the exact object a live GET serves "
                 "with nothing bound), is REFUSED with a loud operator STOP "
                 "(exit 5, AF-AE-TEMPLATE-PIPELINE-MISSING) — the state a "
                 "drift could mistake for a pass"),
        "offline": "--plan + --self-test (pipes a listing in on stdin)",
        "exit_codes": "0/1/2/4/5",
    },
    {
        "name": "verify_after.py",
        "place": "scripts/u03_modules/",
        "manifest_row": None,
        "role": ("the verify-after-write READ-BACK PROVER for every "
                 "provision-time write: the resolved field-map stamp "
                 "(filesystem), the four REPLACE-ME location custom values "
                 "and the standard pipeline (Convert and Flow read-back) — "
                 "three READ-ONLY gates, all fail-closed, 'every write is "
                 "read back byte-for-byte in the same job' "
                 "(AF-AE-READBACK-MISMATCH); keys only, never a value"),
        "offline": "plan + self-test (no token, no network)",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "house_rules.py",
        "place": "scripts/u03_modules/",
        "manifest_row": None,
        "role": ("HOUSE RULES CONSTANTS — the ONE canonical surface for the "
                 "engine's fixed laws: the browser User-Agent (CAF_BROWSER_UA, "
                 "ported byte-for-byte from anthology_registry and pinned "
                 "byte-equal by self-test), the Convert and Flow Version "
                 "header, and the complete AF autofail code table mirrored "
                 "from ENGINE-MANIFEST.json autofails; a drifted law or a "
                 "code that deviates from the manifest is a REFUSAL "
                 "(HouseRulesError, exit 4)"),
        "offline": "plan + self-test (no network, no token surface)",
        "exit_codes": "0/1/2/4",
    },
    {
        "name": "example_usage.py",
        "place": "scripts/u03_modules/",
        "manifest_row": None,
        "role": ("EXAMPLE-USAGE RUNNER — a fail-closed WORKED EXAMPLE of the "
                 "U03 live surface end to end: READ the standard pipeline's "
                 "name, prove the name law with the golden fixture, prove "
                 "the empty state is REFUSED with the attack fixture, and "
                 "re-verify every provision-time write with the verify-after "
                 "re-verifier — ONE JSON report; it is NOT a gate and makes "
                 "NO judgment of its own (every law stays with its sibling), "
                 "so a STOP is never downgraded to a pass"),
        "offline": "--plan + --self-test (no token, no network)",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "rename_applier.py",
        "place": "scripts/u03_modules/",
        "manifest_row": None,
        "role": ("the ONE WRITE surface of the U03 family: applies a pipeline "
                 "NAME change via PUT /opportunities/pipelines/{id} (v3 "
                 "update semantics — the stages array is a COMPLETE "
                 "replacement, so a name-only rename echoes the live read-back "
                 "byte-for-byte); REFUSES to write without --execute — "
                 "otherwise a read-only dry-run; POST-PUT read-back must show "
                 "the new name byte-exact AND the same stage ids in order"),
        "offline": "plan + self-test; apply (dry-run included) needs the PIT",
        "exit_codes": "0/1/2/3/4/5",
    },
)

# ---------------------------------------------------------------------------
# HOUSE EXIT CODES (0/1/2/3/5; 4 = enforced violation). The exact contract
# every U03 checker, fixture, and the applier commit to; self-test pins all
# six. (The U03 EMPTY-LISTING refusal is a data mismatch: exit 5, never a
# silent 0.)
# ---------------------------------------------------------------------------
EXIT_CODES = {
    0: "verified success — all checks PASS (also plan / dry-run / self-test)",
    1: "unexpected error (top-level guard; never a secret leak)",
    2: ("STOP refusal — label NOT SET / non-pit- value / usage / a contract "
        "section missing / the standard pipeline ABSENT or RENAMED on the "
        "location / a drifted (location, name) config pair"),
    3: ("HELD — Convert and Flow API unreachable incl. the Cloudflare edge "
        "403 (CF error 1010) or the internal rail unavailable; retryable, "
        "never mislabeled as a scope problem"),
    4: ("self-test FAILED (AF-AE-*-ATTACK family, enforced violation) — a "
        "tamper never masquerades as exit 1"),
    5: ("mismatch / fail-closed default — drift, extra or mutated keys, a "
        "real-looking custom value, the U03 EMPTY-LISTING attack, or a "
        "read-back mismatch after the rename PUT"),
}

# ---------------------------------------------------------------------------
# THE AF-AE-TEMPLATE-* AUTofail family (ENGINE-MANIFEST.json, stage
# "template live verify (U02)", enforced_by live_verify_template.py) — the
# SAME family the U03 re-verification refuses (a U03 drift is the same drift
# the U02 verify would catch; the families share the autofail codes).
# ---------------------------------------------------------------------------
AF_CODES = (
    ("AF-AE-TEMPLATE-PIPELINE-MISSING", 2,
     "the standard pipeline is absent or renamed on the template location — "
     "find-and-bind would fail silently (STOP); the U03 EMPTY-LISTING attack "
     "refuses under this code at exit 5"),
    ("AF-AE-TEMPLATE-STAGE-DRIFT", 5,
     "a present pipeline is missing a contract stage or carries an "
     "extra/renamed/out-of-order stage"),
    ("AF-AE-TEMPLATE-CUSTOM-VALUE-REAL", 5,
     "a custom value holds a real-looking value (never-a-real-token)"),
    ("AF-AE-READBACK-MISMATCH", 5,
     "a Convert and Flow field write or a Drive write does not read back "
     "byte-for-byte in the same job (S8; verify_after.py is the "
     "provision-time read-back prover)"),
    ("AF-AE-TEMPLATE-ATTACK", 4,
     "an attack fixture tripped the OFFLINE self-test (enforced violation)"),
)

# ---------------------------------------------------------------------------
# DOCTRINE — the house rules the whole U03 tooling commits to, as data so
# the README renders them from the same source the self-test asserts.
# ---------------------------------------------------------------------------
DOCTRINE = (
    ("Fail-closed", "a missing contract section, a malformed input, an "
     "unreadable source, or a live read that cannot be completed is a "
     "REFUSAL or a recorded FAIL — never a blind pass, never a fabricated "
     "success; a strict subset is a MISSING, never a pass; the U03 "
     "EMPTY-LISTING state is REFUSED with its own loud STOP, never a "
     "silent 0"),
    ("Secrets", "credentials resolve BY LABEL only (SET / NOT SET); a token "
     "value is never printed, echoed, or reflected in any surface; the "
     "location id is MASKED to its last 4 characters in every report; "
     "never-a-real-token — template custom values must hold REPLACE-ME "
     "placeholders and a real-looking value REFUSES the verify"),
    ("Browser UA", "every request to GoHighLevel / Convert and Flow "
     "(services.leadconnectorhq.com, Cloudflare-fronted) rides "
     "reg.CafClient / reg.InternalRailClient (and the applier's own v3 "
     "client), which apply CAF_BROWSER_UA — urllib's default "
     "'Python-urllib/x.y' is 403'd at the WAF edge (CF error 1010) before "
     "it ever reaches the API (W0.6 / GK-09); config_loader re-exports the "
     "constant so a caller wiring its own urllib surface cannot forget the "
     "law"),
    ("Scope vs edge", "a bare 401/403 is HELD (UpstreamBlockedError), never "
     "mislabeled as a scope problem; a genuine location-scope denial "
     "(\"does not have access to this location\") is a STOP (exit 2)"),
    ("DEFERRED, never fabricated", "workflow live reads ride the internal "
     "rail (backend.leadconnectorhq.com /workflow/{loc}/list?limit=200 — "
     "the proven surface); without the Firebase refresh token BY LABEL that "
     "item is DEFERRED and the aggregate is fail-closed — never fabricated"),
    ("Gated writes", "--execute is the ONLY flag that performs the rename "
     "PUT; every other invocation of rename_applier.py is a read-only "
     "dry-run; old name == new name is an idempotent no-op; the PUT body is "
     "built ONLY from the live read-back — never from the contract's "
     "standard_stages, which carry no ids"),
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
# drifted inventory is drift, never tolerated). Adding a module to the U03
# tooling REQUIRES adding it here AND to the README's inventory.
CONTRACT_ITEM_COUNT = 4
CONTRACT_MODULE_COUNT = 12


class DocsError(Exception):
    """A fail-closed documentation refusal: the README data drifted from
    its own contract, so no catalog is shipped — wrong docs are worse than
    no docs."""


# ---------------------------------------------------------------------------
# Accessors — deep copies, so callers can never mutate the canonical data.
# ---------------------------------------------------------------------------
def verify_items() -> list:
    """The four verified items as a mutable deep copy (callers may mutate
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
    """The U03 tooling README, rendered from the structured data above.

    One markdown document: what the tooling is, the four verified items,
    the module inventory, the house exit codes, the autofail family, the
    doctrine, and the credential labels. Because every section renders from
    the same constants the self-test asserts, a drift in the data FAILS the
    self-test before it can ship a stale README."""
    lines = [
        "# U03 tooling — GHL template drift-prone live re-verify (README)",
        "",
        "Shipped under ENGINE-MANIFEST.json row %d (the U02 row-54 shipping "
        "law; %s) — dispatched by `scripts/u03_modules/main_skeleton.py` "
        "(the manifest row, importing the check modules BY NAME) plus the "
        "importable sibling checkers, fixtures, applier, and config surface "
        "in `scripts/u03_modules/` — documented machine-side by this module "
        "(`u03_modules.docs_u03`)."
        % (U03_MANIFEST_ROW, U03_SHIPPING_VERSION),
        "",
        "The U03 family re-verifies the template location's DRIFT-PRONE live "
        "state (pipeline name, stage set, custom values, workflow folder) "
        "WITHOUT touching the U02 scope. The live READ is GHL-gated; the "
        "tooling ships now. `verify` runs only from a session that can "
        "resolve a template-scoped private-integration token BY LABEL; "
        "`plan` / `dry-run` and `self-test` are OFFLINE (no token, no "
        "network). The template location is the contract's "
        "source_template_location (the operator's OWN template, never a "
        "client location) and every report masks it to the last 4 "
        "characters.",
        "",
        "## The four verified items (MASTER-SPEC U03 'DRIFT-PRONE' list)",
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
    """The on-disk path a README inventory row claims. u03_modules/ rows
    live next to this module; the row-54 verifier lives in scripts/."""
    base = Path(__file__).resolve().parent
    if row.get("place", "").strip("/") == "scripts":
        base = base.parent
    return base / row["name"]

def _self_test_body(dev) -> None:
    dev.write("[docs-u03] pinning: %d verified items, %d modules, "
              "exit codes 0..5\n"
              % (CONTRACT_ITEM_COUNT, CONTRACT_MODULE_COUNT))

    items = VERIFY_ITEMS
    if len(items) != CONTRACT_ITEM_COUNT:
        raise AssertionError(
            "VERIFY_ITEMS carries %d rows, contract is %d — the U03 item "
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
            "MODULES carries %d rows, contract is %d — a U03 module was "
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
    dev.write("[docs-u03] PASS — README data and shipped tree agree "
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
        sys.stderr.write("[docs-u03] SELF-TEST FAILED "
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
        prog="docs_u03.py",
        description="U03 tooling documentation module — README, module "
                    "inventory, four verified items, exit codes, doctrine, "
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
            "verifier": U03_VERIFIER,
            "manifest_row": U03_MANIFEST_ROW,
            "template_location": "%s%s" % ("...", U03_TEMPLATE_LOCATION[-4:]),
            "shipping": U03_SHIPPING_VERSION,
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
        sys.stderr.write("[docs-u03] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR

if __name__ == "__main__":
    sys.exit(main())
