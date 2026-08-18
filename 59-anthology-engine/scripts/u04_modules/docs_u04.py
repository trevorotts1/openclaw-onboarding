#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u04_modules/docs_u04.py
# U04 TOOLING — THE MODULE DOCSTRING / README, SHIPPED AS AN IMPORTABLE MODULE
# (MASTER-SPEC U04; the u02_modules/docs_u02.py row-54-sibling pattern — the
# U04 family ships under the ENGINE-MANIFEST.json row-54 "template live
# verify (U02)" shipping doctrine, its OWN manifest row NOT yet stamped:
# PENDING, staged exactly under the manifest-pending/u02.json · u03.json
# pattern; current skill-version 0.1.23, 2026-08-11).
# -----------------------------------------------------------------------------
# WHERE THIS SITS: scripts/u04_modules/ — the U04 tooling's documentation
# module, sibling of the checkers, fixtures, and the gated fixer it
# documents. It is NOT a manifest row: the U04 check-module dispatcher
# scripts/u04_modules/main_skeleton.py stays the family's single driver (the
# delivery_report.py sibling-helper pattern under ENGINE-MANIFEST.json row
# 12, exactly as u02_modules/docs_u02.py documents the row-54 U02 verifier
# and u03_modules/docs_u03.py documents the U03 dispatcher). Imported BY
# NAME as u04_modules.docs_u04 when a consumer wants the tooling's contract
# surfaces as DATA (module inventory, the four verified items, the house
# exit codes, the doctrine) or its rendered README as text.
#
# WHAT THIS OWNS:
#   1. THE README. The module docstring below IS the U04 tooling README:
#      what the tooling verifies, the module inventory, the exit-code
#      contract, the credential / browser-UA / fail-closed doctrine. The
#      same content is carried as STRUCTURED DATA (VERIFY_ITEMS, MODULES,
#      EXIT_CODES, AF_CODES, DOCTRINE, CREDENTIAL_LABELS) so a consumer can
#      diff against it instead of parsing prose — and readme() renders the
#      README FROM that data, so the two can never drift.
#   2. THE DRIFT GATE. self_test() proves the documentation still matches
#      the shipped tree: every module the README lists exists on disk next
#      to this module, all four items are present exactly once, every house
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
#      clients (CafClient) AND by query_key_checker's credential-free
#      hosted-form fetch — the docs record that doctrine, they do not
#      re-implement it.
#
# THE TOOLING THIS DOCUMENTS (orientation):
#   MASTER-SPEC U04 — the INTAKE FRONT DOOR'S LIVE SHAPE. The U02 tooling
#   verified the ALREADY-DONE template location and the U03 family
#   re-verified its drift-prone state; the U04 family gates the ONE surface
#   every book's journey starts at: the universal author-intake form the
#   minted link rides
#   (<forms_base>/widget/form/<form_id>?anthology_id=<minted>, built by
#   scripts/anthology_book.py). Four live gates in a FIXED order
#   (dispatcher LIVE_GATES): the form is READABLE by slug + pin
#   (form_reader.py, public v2 GET /forms/?locationId=), its hidden query
#   key is "anthology_id" BYTE-EXACT on the live hosted-form page
#   (query_key_checker.py — the G3 law, CREDENTIAL-FREE by design), the
#   required intake flags are present and non-empty (required_checker.py,
#   OFFLINE and pure), and brand legal links are replacement-ready
#   (brand_link_checker.py, OFFLINE; its live read is DEFERRED until brand
#   HTML page paths are wired — never fabricated). The ONE write surface of
#   the family is query_key_fixer.py (PUT /forms/{id}) and it REFUSES to
#   write without its own --execute. Golden + attack fixtures
#   (golden_ok / attack_bad_query / attack_example_dot_com /
#   attack_not_required) plus the independent pytest battery
#   (test_checkers.py) prove the family offline before any live surface.
#   Dispatcher: scripts/u04_modules/main_skeleton.py — imports the check
#   modules BY NAME (importlib, never exec'd from a path), enforces the
#   one-entry-point contract (every module exposes self_test(out=None)
#   -> int; a family that cannot prove itself offline STOPS), and resolves
#   the aggregate exit code exactly as its U02 / U03 siblings do.
#
# THE FOUR VERIFIED ITEMS (MASTER-SPEC U04; the dispatcher's four live
# gates, in the FIXED order LIVE_GATES carries them):
#   1. UNIVERSAL AUTHOR-INTAKE FORM READABLE — the public v2 read
#      GET /forms/?locationId= (Version 2021-07-28, the path-based version
#      map proven in Skill 44's ghl_client) FINDS the universal author-
#      intake form by slug / pin and reports its ONE form id. Find-by-slug:
#      a row whose normalized name equals "universal intake"; pin-by-id:
#      DEFAULT_UNIVERSAL_INTAKE_FORM_ID (imported from form_reader, the
#      ONE owner of the pin), and a pinned id the listing does not contain
#      is a MISMATCH (exit 5), never a silent pass. A listing with NO
#      universal-intake row is a FAIL (never a silent empty); an unreadable
#      listing shape STOPS. Source of truth:
#      config/anthology-snapshot-contract.json forms block (slug
#      universal-intake, hidden fields contact_id / anthology_id / stage).
#   2. G3 INTAKE QUERY KEY BYTE-EXACT — the live hosted-form page
#      (<forms_base>/widget/form/<form_id>, the SAME public widget the
#      author's browser loads — ZERO credentials, ZERO API calls) must key
#      its hidden Book-ID field data-q EXACTLY "anthology_id" (byte-exact,
#      never a strip, never a case fold), in a HIDDEN container (the
#      d-none class), with "anthology_active_id" as that field's LABEL and
#      appearing NOWHERE as a live data-q — a wrong-keyed field is a FAIL
#      even when the right-keyed field also exists. A page that cannot be
#      fetched is HELD (exit 3), never judged. Source of truth: the G3
#      law — scripts/anthology_book.py INTAKE_QUERY_KEY / build_intake_link
#      and the snapshot contract's universal_hidden_fields.
#   3. REQUIRED INTAKE FLAGS — the three intake-required participant
#      fields first_name / last_name / email present with non-empty string
#      values, intake_router.py FIELD_ALIASES-aware (firstName /
#      lastName / customData.* / contact.firstName are the SAME field,
#      never a second column); email is a REQUIRED contact field here,
#      never a KEY — everything keys off contact_id, never email
#      (MASTERDOC floor 8). A payload whose shape cannot be read faithfully
#      is ALSO a FAIL (reading on would fabricate a clean check). Source of
#      truth: config/anthology-snapshot-contract.json forms.required +
#      scripts/intake_router.py.
#   4. BRAND LEGAL LINKS REPLACEMENT-READY — brand-marketing HTML (the
#      cover template, the announcement card, the sales and delivery
#      surfaces) must link its legal destinations to real domains: an
#      RFC 2606 placeholder host (example.com and siblings), a hostless /
#      scheme-less href, a mailto: / tel: / javascript: legal link, a
#      page with NO legal links at all, or a mislabeled anchor ("#",
#      "javascript:void(0)") is FLAGGED REPLACE, never a silent pass.
#      OFFLINE and pure (html.parser + urllib.parse): never fetches, never
#      resolves, never reads a credential; offenders are named BY KEY
#      (line, index, text) and the href is reduced to host + path — a
#      query string can carry a token, so the raw href is never echoed.
#      Live read: DEFERRED until brand HTML page paths are wired — never
#      fabricated (fail-closed without --allow-deferred).
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE, everywhere in this tooling. The
# private-integration token resolves through anthology_registry (labels:
# CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_API_KEY / GOHIGHLEVEL_API_KEY /
# GOHIGHLEVEL_PIT / GHL_API_KEY — live process env first, then the three
# canonical client env stores). SET / NOT SET only on every operator
# surface; a token value is NEVER printed. The location id is pinned to
# the contract source_template_location.template_location_id (the
# operator's OWN template location — operator infrastructure config, not a
# secret) unless --location-id overrides; the form id is pinned to
# form_reader.DEFAULT_UNIVERSAL_INTAKE_FORM_ID (the ONE owner of the pin)
# unless --form-id overrides; every report masks BOTH to their LAST 4
# characters (tenant / location identifiers, never printed in full). The
# ONE credential-free surface of the family is query_key_checker's read of
# the PUBLIC hosted-form widget — but the aggregate still refuses up front
# without a PIT, because the form_reader gate is PIT-gated and no gate is
# ever skipped.
#
# BROWSER UA: every request rides reg.CafClient / query_key_checker's own
# fetch, which apply CAF_BROWSER_UA on every request so the Cloudflare
# edge fronting services.leadconnectorhq.com / the hosted-form domain
# never 1010s a verify request (CF error 1010; the W0.6 / GK-09
# discipline — urllib's default "Python-urllib/x.y" is 403'd at the WAF
# edge before it ever reaches the API). The dispatcher asserts the law
# OFFLINE (its self-test pins the exact constant on the outbound surface)
# so a drifted UA is caught before a single live request. Scope-vs-edge-
# block discrimination: a bare 401/403 is HELD (UpstreamBlockedError /
# CafUnreachable), never mislabeled as a scope problem; a genuine scope
# denial is a STOP (exit 2, the AF-AE-PIT-SCOPE family — the code already
# stamped in ENGINE-MANIFEST.json).
#
# FAIL-CLOSED (the whole point): a missing credential STOPS (exit 2), the
# U04 check-module assembly incomplete STOPS (exit 2, AF-AE-U04-ASSEMBLY-
# INCOMPLETE — a check family is never silently skipped), a transport /
# edge failure is HELD (exit 3), a live read that cannot be performed is
# DEFERRED (never fabricated — the brand gate is DEFERRED until its HTML
# paths are wired, and the aggregate is exit 5 unless --allow-deferred,
# the operator's explicit opt-in), and ANY absent / drifted / lookalike /
# placeholder item is a FAIL (exit 5). A success is claimed ONLY when
# every requested item exists on the live surface AND agrees byte-exact
# with its source of truth. Every deviation is NAMED with its code —
# never a bare "something failed".
#
# DOCTRINE (house, per anthology_registry.py / drive_adapter.py): move in
# silence (operator-verbose only); NOTHING Anthropic in any runtime file;
# Convert and Flow naming in every client surface; STDLIB ONLY (urllib +
# json + html.parser); calls NO model; never a client PII; a law is read
# once, in one module (the delta_reporter.py single-implementation
# doctrine — form_reader owns the forms read, query_key_checker owns the
# G3 gate, query_key_fixer reuses them, never re-implements). Self-test
# failures are exit 4 (enforced violation, the AF-AE-TEMPLATE-ATTACK /
# AF-AE-*-ATTACK families) — a tamper never masquerades as exit 1.
#
# USAGE (this module's own machine surface — pure data, nothing to leak):
#   python3 docs_u04.py                ONE JSON catalog of the whole tooling
#   python3 docs_u04.py readme         the rendered README (markdown text)
#   python3 docs_u04.py self-test      OFFLINE drift gate over the docs vs
#                                      the shipped tree; 0 clean, 4 drift
# =============================================================================
"""docs_u04.py -- README / module docstring for the U04 tooling, as an
importable fail-closed pure-data module: the intake front door's live
gate family (dispatched by u04_modules/main_skeleton.py under the manifest
row-54 "template live verify (U02)" shipping doctrine — the family's OWN
manifest row PENDING), its four verified items, the u04_modules inventory,
the house exit codes, and the credential / browser-UA / doctrine
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
DOC_CONTRACT = "anthology-engine-u04-tooling-docs"
SCHEMA_VERSION = 1

# The U04 dispatcher is the family's single driver under the U02 row-54
# shipping law; the u04_modules/ siblings ship as non-manifest helpers (the
# delivery_report.py row-12 pattern, exactly the docs_u02.py / docs_u03.py
# siblings). The U04 family's OWN manifest row is NOT yet stamped in
# ENGINE-MANIFEST.json (verified at ship time, 2026-08-11): it is PENDING,
# staged under the manifest-pending/u02.json · u03.json pattern — this
# module records None rather than invent a row number (a doc that claims a
# row that does not exist is drift).
U04_VERIFIER = "main_skeleton.py"
U04_MANIFEST_ROW = None  # PENDING — the family is not yet stamped
U04_TEMPLATE_LOCATION = "2HIKGNgsixWx0yds7Qnx"  # contract
# source_template_location.template_location_id — operator infrastructure
# config, never a secret; reports mask it to the last 4 characters.
U04_FORM_ID = "U65pwoeMTy1niMqllKWG"  # pinned via form_reader
# DEFAULT_UNIVERSAL_INTAKE_FORM_ID — a location identifier, not a secret;
# masked on every surface, never printed in full.
U04_SHIPPING_VERSION = "v0.1.23 (2026-08-11)"  # skill-version at ship time

# ---------------------------------------------------------------------------
# THE FOUR VERIFIED ITEMS (MASTER-SPEC U04 — the dispatcher's four live
# gates, in the FIXED order LIVE_GATES carries them). Item numbers are
# load-bearing (positions 1..4, exactly four — self-test pins the count);
# the title is the README heading, asserts the fail-closed claim, source
# the engine's source of truth, and fails the operator surface on drift.
# ---------------------------------------------------------------------------
VERIFY_ITEMS = (
    {
        "item": 1,
        "title": "Universal author-intake form readable (slug + pin law)",
        "asserts": ("the public v2 read GET /forms/?locationId= (Version "
                    "2021-07-28) FINDS the universal author-intake form and "
                    "reports its ONE form id: find-by-slug (a row whose "
                    "normalized name equals 'universal intake') + pin-by-id "
                    "(DEFAULT_UNIVERSAL_INTAKE_FORM_ID — a pinned id the "
                    "listing does not contain is a MISMATCH, never a silent "
                    "pass); a listing with NO universal-intake row is a "
                    "FAIL — never a silent empty"),
        "source": "config/anthology-snapshot-contract.json forms block + "
                  "form_reader.DEFAULT_UNIVERSAL_INTAKE_FORM_ID (the ONE "
                  "owner of the pin)",
        "fails": "no universal-intake row / pinned id absent -> exit 5; an "
                 "unreadable listing shape STOPS (exit 2); a bare 401/403 "
                 "is HELD (exit 3), never mislabeled as scope",
    },
    {
        "item": 2,
        "title": "G3 intake query key BYTE-EXACT 'anthology_id'",
        "asserts": ("the live hosted-form page (the PUBLIC "
                    "<forms_base>/widget/form/<form_id> widget the author's "
                    "browser loads — ZERO credentials, ZERO API calls) keys "
                    "its hidden Book-ID field data-q EXACTLY 'anthology_id' "
                    "in a HIDDEN container (d-none), with "
                    "'anthology_active_id' as that field's LABEL and "
                    "appearing NOWHERE as a live data-q — a wrong-keyed "
                    "field is a FAIL even when the right-keyed field also "
                    "exists; a page that cannot be fetched is HELD (exit 3), "
                    "never judged"),
        "source": "the G3 law — scripts/anthology_book.py INTAKE_QUERY_KEY "
                  "/ build_intake_link + the snapshot contract's "
                  "universal_hidden_fields",
        "fails": "AF-AE-INTAKE-QUERY-KEY (exit 5) — the G3 defect family",
    },
    {
        "item": 3,
        "title": "Required intake flags present and non-empty",
        "asserts": ("the three intake-required participant fields "
                    "first_name / last_name / email present with non-empty "
                    "string values, intake_router.py FIELD_ALIASES-aware "
                    "(firstName / lastName / customData.* / "
                    "contact.firstName are the SAME field); email is a "
                    "REQUIRED contact field, never a KEY — everything keys "
                    "off contact_id, never email (MASTERDOC floor 8); a "
                    "payload whose shape cannot be read faithfully is ALSO "
                    "a FAIL — reading on would fabricate a clean check"),
        "source": "config/anthology-snapshot-contract.json forms.required + "
                  "scripts/intake_router.py FIELD_ALIASES",
        "fails": "AF-AE-REQUIRED-MISSING (exit 5); an unreadable payload "
                 "shape STOPS (exit 2, AF-AE-REQUIRED-PAYLOAD-UNREADABLE)",
    },
    {
        "item": 4,
        "title": "Brand legal links replacement-ready",
        "asserts": ("brand-marketing HTML must link its legal destinations "
                    "to real domains: an RFC 2606 placeholder host "
                    "(example.com and siblings), a hostless / scheme-less "
                    "href, a mailto: / tel: / javascript: legal link, a "
                    "page with NO legal links at all, or a mislabeled "
                    "anchor is FLAGGED REPLACE, never a silent pass; "
                    "OFFLINE and pure (html.parser + urllib.parse) — never "
                    "fetches, never resolves; offenders named BY KEY, the "
                    "href reduced to host + path (a query string can carry "
                    "a token — never-a-token doctrine)"),
        "source": "the cover / brand-marketing HTML family (the cover "
                  "template, the announcement card, the sales and delivery "
                  "surfaces)",
        "fails": "AF-AE-BRAND-LINK (exit 5); live read DEFERRED until brand "
                 "HTML page paths are wired — never fabricated",
    },
)

# ---------------------------------------------------------------------------
# THE MODULE INVENTORY. `place` names the directory relative to this module
# (the u04_modules package itself); self-test proves each name exists at
# that place. `role` is the one-line contract each module owns; `offline`
# names the credential-free surface; `exit_codes` follows the house
# convention (0/1/2/3/5, 4 = self-test).
# ---------------------------------------------------------------------------
MODULES = (
    {
        "name": "main_skeleton.py",
        "place": "scripts/u04_modules/",
        "manifest_row": None,
        "role": ("the U04 check-module dispatcher — the family's single "
                 "driver (sibling of u02/u03 main_skeleton.py, the "
                 "delivery_report.py sibling-helper pattern). Imports the "
                 "check modules BY NAME (importlib, never exec'd from a "
                 "path), enforces the one-entry-point contract (every "
                 "module exposes self_test(out=None) -> int — a family "
                 "that cannot prove itself offline STOPS), carries NO check "
                 "logic itself, and resolves the fail-closed aggregate "
                 "exit code exactly as its U02 / U03 siblings do; "
                 "subcommands verify / plan (offline dry-run) / self-test; "
                 "asserts the browser-UA law offline (the CAF_BROWSER_UA "
                 "constant pinned on the outbound surface)"),
        "offline": "plan / dry-run + self-test (no token, no network)",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "__init__.py",
        "place": "scripts/u04_modules/",
        "manifest_row": None,
        "role": ("fail-closed EMPTY package init — pure namespace "
                 "container, no runtime code; modules are imported BY "
                 "NAME; records the package doctrine (fail-closed, secrets "
                 "by label, browser-UA law for every GoHighLevel / Convert "
                 "and Flow surface, move in silence)"),
        "offline": "trivially — it is empty",
        "exit_codes": "n/a (no executable surface)",
    },
    {
        "name": "form_reader.py",
        "place": "scripts/u04_modules/",
        "manifest_row": None,
        "role": ("the LIVE FORM READER — the public v2 forms listing read "
                 "GET /forms/?locationId= (Version 2021-07-28, the path-"
                 "based version map proven in Skill 44's ghl_client) that "
                 "FINDS the universal author-intake form by slug / pin and "
                 "reports its ONE form id; the ONE owner of the "
                 "DEFAULT_UNIVERSAL_INTAKE_FORM_ID pin; a listing with no "
                 "universal-intake row is a FAIL (never a silent empty), "
                 "an unreadable shape raises FormsReadError (STOP); "
                 "never-a-token surface — a payload hit on the house "
                 "credential shape REFUSES the whole report"),
        "offline": "plan + self-test (no token, no network)",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "required_checker.py",
        "place": "scripts/u04_modules/",
        "manifest_row": None,
        "role": ("the REQUIRED-FLAGS LAW, applied to a payload: "
                 "first_name / last_name / email present with non-empty "
                 "string values, intake_router FIELD_ALIASES-aware; email "
                 "is a REQUIRED field, never a KEY — everything keys off "
                 "contact_id, never email (MASTERDOC floor 8); a payload "
                 "whose shape cannot be read faithfully is ALSO a FAIL "
                 "(_UnreadablePayload, STOP) — never a fabricated clean "
                 "check; holds ZERO credential surface"),
        "offline": "entirely — pure and OFFLINE",
        "exit_codes": "0/1/2/4/5",
    },
    {
        "name": "brand_link_checker.py",
        "place": "scripts/u04_modules/",
        "manifest_row": None,
        "role": ("the BRAND-SURFACE LEGAL-LINK GATE — the offline, "
                 "fail-closed tripwire over brand HTML: an RFC 2606 "
                 "placeholder host (example.com and the reserved "
                 "*.example.* family), a hostless / scheme-less href, a "
                 "mailto: / tel: / javascript: legal link, or a page with "
                 "NO legal links at all FLAGS REPLACE; offenders named BY "
                 "KEY (line / index / text), the href reduced to host + "
                 "path — never the raw query; never fetches, never "
                 "resolves, never reads a credential"),
        "offline": "entirely — pure local shape analysis (html.parser + "
                   "urllib.parse)",
        "exit_codes": "0/1/2/4/5",
    },
    {
        "name": "query_key_checker.py",
        "place": "scripts/u04_modules/",
        "manifest_row": None,
        "role": ("the G3 INTAKE QUERY-KEY GATE — reads the LIVE hosted-form "
                 "page (the PUBLIC <forms_base>/widget/form/<form_id> "
                 "surface, CREDENTIAL-FREE: zero credentials, zero API "
                 "calls) and requires the hidden Book-ID field data-q to "
                 "be 'anthology_id' BYTE-EXACT in a hidden container "
                 "(d-none), with 'anthology_active_id' as its LABEL and "
                 "NOWHERE as a live data-q; the fetch rides "
                 "CAF_BROWSER_UA; a page that cannot be fetched is HELD "
                 "(exit 3), never judged; never auto-heals a drifted form"),
        "offline": "plan + self-test (no network, no secrets)",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "query_key_fixer.py",
        "place": "scripts/u04_modules/",
        "manifest_row": None,
        "role": ("the ONLY WRITE surface of the U04 family: corrects the "
                 "universal form's query key via public v2 PUT /forms/{id} "
                 "— and REFUSES to write unless the operator passes "
                 "--execute to ITS OWN CLI (every other invocation is a "
                 "read-only DRY-RUN); the PUT body is built ONLY from the "
                 "live read-back row, never from memory; after the PUT the "
                 "form is read back and must prove the fix byte-for-byte "
                 "(AF-AE-READBACK-MISMATCH); the dispatcher NEVER invokes "
                 "it and NEVER writes"),
        "offline": "plan + self-test; the dry-run needs the PIT (the live "
                   "read is PIT-gated)",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "golden_ok.py",
        "place": "scripts/u04_modules/",
        "manifest_row": None,
        "role": ("the GOLDEN ALREADY-COMPLIANT intake-form fixture — the "
                 "canonical in-memory payload of the universal author-"
                 "intake form in its compliant state, derived BYTE-EXACT "
                 "from the committed snapshot contract (never a hardcoded "
                 "list); MappingProxyType-frozen canon (every mutation "
                 "route raises, proven by self-test) + deep-copied payload "
                 "surfaces; payload() REFUSES (exit 5) on any contract "
                 "drift — an inconsistent contract is a refusal, never a "
                 "blind pass"),
        "offline": "entirely — pure data + builders",
        "exit_codes": "0/1/5 (fixture refusal); 4 self-test",
    },
    {
        "name": "attack_bad_query.py",
        "place": "scripts/u04_modules/",
        "manifest_row": None,
        "role": ("the U04 ATTACK: the G3-conflation link — anthology_id "
                 "swapped to anthology_active_id — that every byte-exact "
                 "query-key gate must REFUSE; attack_link() + verify_live() "
                 "judge the link and payload() / payload_true() ship the "
                 "FAIL-CLOSED gates; the golden one-key control link "
                 "passes internally, the wrong-key attack link FAILS "
                 "(AF-AE-ATTACKBADQUERY-* family on a self-test tamper)"),
        "offline": "plan + self-test (no network, no token surface)",
        "exit_codes": "0/1/4/5",
    },
    {
        "name": "attack_example_dot_com.py",
        "place": "scripts/u04_modules/",
        "manifest_row": None,
        "role": ("the U04 ATTACK: an example.com legal link that every "
                 "brand-surface gate must REFUSE; attack_link() + "
                 "verify_live() judge the link and payload() / payload_true() "
                 "ship the FAIL-CLOSED gates; the golden real-host control "
                 "link passes internally, the example.com attack link FAILS "
                 "(AF-AE-ATTACKEXAMPLEDOTCOM-* family on a self-test "
                 "tamper)"),
        "offline": "plan + self-test (no network, no token surface)",
        "exit_codes": "0/1/4/5",
    },
    {
        "name": "attack_not_required.py",
        "place": "scripts/u04_modules/",
        "manifest_row": None,
        "role": ("the U04 ATTACK: an intake payload with email ABSENT / "
                 "EMPTY / whitespace-only / non-string is REFUSED "
                 "(NotRequiredError, the STOP family) — never a clean "
                 "read, never a fabricated pass; verify() applies the "
                 "required-flags law to the attack payload and the "
                 "self-test proves the pass/fail split discriminates "
                 "(AF-AE-REQUIRED-ATTACK family on a tamper)"),
        "offline": "plan + self-test (no network, no token surface)",
        "exit_codes": "0/1/2/4/5",
    },
    {
        "name": "test_checkers.py",
        "place": "scripts/u04_modules/",
        "manifest_row": None,
        "role": ("the INDEPENDENT PYTEST BATTERY of the family — offline "
                 "contract tests over the six public surfaces "
                 "(required_checker / golden_ok / brand_link_checker / "
                 "form_reader / query_key_fixer / attack_bad_query); "
                 "network-free and credential-free (the registry's "
                 "CafClient is NEVER constructed, no env var read, no "
                 "subprocess); provenance only — the dispatcher asserts "
                 "the file's presence, the tests run under pytest"),
        "offline": "entirely — pytest battery, no network, no secrets",
        "exit_codes": "n/a (pytest battery; a failing run fails the "
                      "dispatcher self-test, exit 4)",
    },
)

# ---------------------------------------------------------------------------
# HOUSE EXIT CODES (0/1/2/3/5; 4 = enforced violation). The exact contract
# every U04 checker, fixture, and the gated fixer commit to; self-test pins
# all six.
# ---------------------------------------------------------------------------
EXIT_CODES = {
    0: "verified success — all checks PASS (also plan / dry-run / self-test)",
    1: "unexpected error (top-level guard; never a secret leak)",
    2: ("STOP refusal — label NOT SET / non-pit- value / usage / the U04 "
        "check-module assembly incomplete (AF-AE-U04-ASSEMBLY-INCOMPLETE) / "
        "a contract that cannot be read / a module STOP-family refusal "
        "(unreadable payload shape, no brand pages given)"),
    3: ("HELD — Convert and Flow unreachable / Cloudflare edge block "
        "(CF error 1010) / the hosted-form page cannot be fetched "
        "(UNDETERMINED, never a verdict)"),
    4: ("self-test FAILED (AF-AE-TEMPLATE-ATTACK / AF-AE-*-ATTACK family, "
        "enforced violation) — a tamper never masquerades as exit 1"),
    5: ("mismatch / fail-closed default — drift, a lookalike query key, a "
        "placeholder legal link, a missing required flag (AF-AE-INTAKE-"
        "QUERY-KEY / AF-AE-BRAND-LINK / AF-AE-REQUIRED-MISSING), a "
        "read-back mismatch after the fix PUT, or a DEFERRED live read "
        "without --allow-deferred"),
}

# ---------------------------------------------------------------------------
# THE AF AUTOfail FAMILY of the U04 tooling — the codes the family's own
# surfaces declare (dispatcher header + the check modules). The U04-specific
# codes are NOT yet stamped in ENGINE-MANIFEST.json (the family is PENDING
# — verified at ship time, 2026-08-11); AF-AE-PIT-SCOPE and the shared
# AF-AE-TEMPLATE-ATTACK / AF-AE-READBACK-MISMATCH codes already live in the
# manifest. Self-test failures are exit 4, never 1.
# ---------------------------------------------------------------------------
AF_CODES = (
    ("AF-AE-U04-ASSEMBLY-INCOMPLETE", 2,
     "the U04 check-module set named in U04_MODULES is not fully present, "
     "or a module violates the one-entry-point self_test contract — a "
     "check family is never silently skipped (dispatcher STOP)"),
    ("AF-AE-INTAKE-QUERY-KEY", 5,
     "the live intake form's hidden query key is not 'anthology_id' "
     "byte-exact (query_key_checker), or a live field submits under the "
     "lookalike 'anthology_active_id' key — the G3 defect family"),
    ("AF-AE-BRAND-LINK", 5,
     "a brand page carries a placeholder / hostless / mislabeled legal "
     "link, or a page carries no legal links at all (brand_link_checker)"),
    ("AF-AE-REQUIRED-MISSING", 5,
     "a required intake flag (first_name / last_name / email) is absent, "
     "empty, whitespace-only, or non-string on the payload "
     "(required_checker / attack_not_required)"),
    ("AF-AE-READBACK-MISMATCH", 5,
     "the query-key fix PUT does not read back byte-for-byte in the same "
     "job — a fix is never reported without proof (query_key_fixer)"),
    ("AF-AE-PIT-SCOPE", 2,
     "a genuine location-scope denial signature on the forms read — STOP, "
     "never mislabeled as an edge block (form_reader; the code is already "
     "stamped in ENGINE-MANIFEST.json)"),
    ("AF-AE-GOLDENOK-*", 4,
     "an attack tripped the golden fixture's OFFLINE self-test (enforced "
     "violation)"),
    ("AF-AE-ATTACKBADQUERY-*", 4,
     "an attack tripped the wrong-query-key attack fixture's OFFLINE "
     "self-test (enforced violation)"),
    ("AF-AE-ATTACKEXAMPLEDOTCOM-*", 4,
     "an attack tripped the example.com attack fixture's OFFLINE "
     "self-test (enforced violation)"),
    ("AF-AE-REQUIRED-ATTACK", 4,
     "an attack payload with email ABSENT / EMPTY / whitespace-only / "
     "non-string was NOT refused by the offline gates (enforced "
     "violation)"),
    ("AF-AE-TEMPLATE-ATTACK", 4,
     "an attack fixture tripped the OFFLINE self-test of the dispatcher or "
     "a family battery (enforced violation — the house code, shared with "
     "the U02 / U03 families)"),
)

# ---------------------------------------------------------------------------
# DOCTRINE — the house rules the whole U04 tooling commits to, as data so
# the README renders them from the same source the self-test asserts.
# ---------------------------------------------------------------------------
DOCTRINE = (
    ("Fail-closed", "a missing contract section, a malformed input, an "
     "unreadable source, or a live read that cannot be completed is a "
     "REFUSAL or a recorded FAIL — never a blind pass, never a fabricated "
     "success; a strict subset is a MISSING, never a pass; a listing with "
     "no universal-intake row is a FAIL, never a silent empty; a wrong-"
     "keyed field is a FAIL even when the right-keyed field also exists"),
    ("Secrets", "credentials resolve BY LABEL only (SET / NOT SET); a token "
     "value is never printed, echoed, or reflected in any surface; the "
     "location id AND the form id are MASKED to their last 4 characters in "
     "every report; the fixer's PUT body is built ONLY from the live "
     "read-back row, never from memory; a brand href is reduced to host + "
     "path — a query string can carry a token"),
    ("Browser UA", "every request to GoHighLevel / Convert and Flow "
     "(services.leadconnectorhq.com, Cloudflare-fronted) and every "
     "hosted-form page fetch rides CAF_BROWSER_UA (reg.CafClient / "
     "query_key_checker's own fetch) — urllib's default 'Python-urllib/x.y' "
     "is 403'd at the WAF edge (CF error 1010) before it ever reaches the "
     "API (W0.6 / GK-09); the dispatcher pins the constant OFFLINE in its "
     "self-test so a drifted UA is caught before a single live request"),
    ("Scope vs edge", "a bare 401/403 is HELD (UpstreamBlockedError / "
     "CafUnreachable), never mislabeled as a scope problem; a genuine "
     "location-scope denial is a STOP (exit 2, AF-AE-PIT-SCOPE)"),
    ("Credential-free read", "query_key_checker reads the PUBLIC hosted-"
     "form widget — zero credentials, zero API calls — but the aggregate "
     "still refuses up front without a PIT: the form_reader gate is "
     "PIT-gated and no gate is ever skipped"),
    ("DEFERRED, never fabricated", "the brand legal-link live read is "
     "DEFERRED until brand HTML page paths are wired; a DEFERRED check "
     "fails the aggregate (exit 5) unless --allow-deferred (the operator's "
     "explicit opt-in) — never fabricated"),
    ("Gated writes", "--execute is the ONLY flag that performs the query-"
     "key fix PUT (query_key_fixer's OWN CLI); every other invocation is a "
     "read-only dry-run; the dispatcher NEVER invokes the fixer and NEVER "
     "writes; the POST-PUT read-back must prove the fix byte-for-byte"),
    ("Move in silence", "operator-verbose only; NOTHING Anthropic in any "
     "runtime file; Convert and Flow naming in every client surface; "
     "STDLIB ONLY (urllib + json + html.parser); calls NO model; never a "
     "client PII; a law is read once, in one module (single-implementation "
     "doctrine)"),
)

# ---------------------------------------------------------------------------
# CREDENTIAL LABELS — BY LABEL ONLY. These are the label NAMES the tooling
# resolves through anthology_registry (live process env first, then the
# three canonical client env stores). A label is a name, never a value; the
# values they resolve to are never held here and never printed anywhere.
# The U04 family has NO rail surface (no Firebase refresh token): the
# forms read is the PUBLIC v2 surface with the location PIT, and the
# query-key gate is credential-free.
# ---------------------------------------------------------------------------
CREDENTIAL_LABELS = {
    "pit": (
        "CONVERT_AND_FLOW_PIT",
        "CONVERT_AND_FLOW_API_KEY",
        "GOHIGHLEVEL_API_KEY",
        "GOHIGHLEVEL_PIT",
        "GHL_API_KEY",
    ),
}

# Pinned counts (the fixture-counting discipline of golden_fields.py: a
# drifted inventory is drift, never tolerated). Adding a module to the U04
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
    """The AF autofail family as plain (code, exit, meaning) tuples in a
    mutable list."""
    return list(AF_CODES)

# ---------------------------------------------------------------------------
# The rendered README — built FROM the data, so prose can never drift from
# the contract. This is the machine-readable form of the module docstring.
# ---------------------------------------------------------------------------
def readme() -> str:
    """The U04 tooling README, rendered from the structured data above.

    One markdown document: what the tooling is, the four verified items,
    the module inventory, the house exit codes, the autofail family, the
    doctrine, and the credential labels. Because every section renders from
    the same constants the self-test asserts, a drift in the data FAILS the
    self-test before it can ship a stale README."""
    lines = [
        "# U04 tooling — intake front door live gates (README)",
        "",
        "Shipped under the ENGINE-MANIFEST.json row-54 \"template live "
        "verify (U02)\" shipping doctrine (%s; the U04 family's OWN manifest "
        "row is PENDING — not yet stamped, staged under the "
        "manifest-pending/u02.json · u03.json pattern) — dispatched by "
        "`scripts/u04_modules/main_skeleton.py` (importing the check "
        "modules BY NAME) plus the importable sibling checkers, fixtures, "
        "the gated fixer, and the pytest battery in `scripts/u04_modules/` "
        "— documented machine-side by this module (`u04_modules.docs_u04`)."
        % U04_SHIPPING_VERSION,
        "",
        "The U04 family gates the INTAKE FRONT DOOR'S LIVE SHAPE — the "
        "universal author-intake form the minted link rides "
        "(`<forms_base>/widget/form/<form_id>?anthology_id=<minted>`, built "
        "by `scripts/anthology_book.py`). The live READ is GHL-gated; the "
        "tooling ships now. `verify` runs only from a session that can "
        "resolve a template-scoped private-integration token BY LABEL — "
        "with ONE exception: the query-key gate's read is the PUBLIC "
        "hosted-form widget, credential-free by design, yet the aggregate "
        "still refuses up front without a PIT (the form_reader gate is "
        "PIT-gated and no gate is ever skipped). `plan` / `dry-run` and "
        "`self-test` are OFFLINE (no token, no network). The template "
        "location is the contract's source_template_location (the "
        "operator's OWN template, never a client location); the form id is "
        "pinned to `form_reader.DEFAULT_UNIVERSAL_INTAKE_FORM_ID`; every "
        "report masks BOTH to the last 4 characters.",
        "",
        "## The four verified items (MASTER-SPEC U04 — the dispatcher's "
        "four live gates, in the FIXED order LIVE_GATES carries them)",
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
    """The on-disk path a README inventory row claims. Every U04 row lives
    next to this module (scripts/u04_modules/)."""
    base = Path(__file__).resolve().parent
    if row.get("place", "").strip("/") == "scripts":
        base = base.parent
    return base / row["name"]

def _self_test_body(dev) -> None:
    dev.write("[docs-u04] pinning: %d verified items, %d modules, "
              "exit codes 0..5\n"
              % (CONTRACT_ITEM_COUNT, CONTRACT_MODULE_COUNT))

    items = VERIFY_ITEMS
    if len(items) != CONTRACT_ITEM_COUNT:
        raise AssertionError(
            "VERIFY_ITEMS carries %d rows, contract is %d — the U04 item "
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
            "MODULES carries %d rows, contract is %d — a U04 module was "
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
            "AF family must map only onto STOP/self-test/mismatch exits "
            "(2/4/5), got %s" % sorted(exits))

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
    dev.write("[docs-u04] PASS — README data and shipped tree agree "
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
        sys.stderr.write("[docs-u04] SELF-TEST FAILED "
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
        prog="docs_u04.py",
        description="U04 tooling documentation module — README, module "
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
            "verifier": U04_VERIFIER,
            "manifest_row": U04_MANIFEST_ROW,
            "template_location": "%s%s" % ("...", U04_TEMPLATE_LOCATION[-4:]),
            "form_id": "%s%s" % ("...", U04_FORM_ID[-4:]),
            "shipping": U04_SHIPPING_VERSION,
            "verify_items": verify_items(),
            "modules": modules(),
            "exit_codes": exit_codes(),
            "af_codes": af_codes(),
            "doctrine": [{"name": n, "text": t} for n, t in DOCTRINE],
            "credential_labels": {k: list(v)
                                  for k, v in CREDENTIAL_LABELS.items()},
            "note": "pure data — no credential value is held or printed; "
                    "the template location and the form id are masked to "
                    "their last 4 chars; the U04 manifest row is PENDING",
        }, indent=2, sort_keys=True))
        return EX_OK
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[docs-u04] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR

if __name__ == "__main__":
    sys.exit(main())
