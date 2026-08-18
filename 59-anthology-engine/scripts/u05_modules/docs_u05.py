#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u05_modules/docs_u05.py
# U05 TOOLING — THE MODULE DOCSTRING / README, SHIPPED AS AN IMPORTABLE MODULE
# (MASTER-SPEC U05; the u02_modules/docs_u02.py row-54-sibling pattern — the
# U05 family ships under the ENGINE-MANIFEST.json row-54 "template live
# verify (U02)" shipping doctrine, its OWN manifest row NOT yet stamped:
# PENDING, staged exactly under the manifest-pending/u02.json · u03.json ·
# u04.json pattern; current skill-version 0.1.23, 2026-08-11).
# -----------------------------------------------------------------------------
# WHERE THIS SITS: scripts/u05_modules/ — the U05 tooling's documentation
# module, sibling of the scope gates, the fixtures, and the live workflow
# reader it documents. It is NOT a manifest row: the U05 verifier stays the
# family's single driver under the delivery_report.py row-12 sibling-helper
# pattern, exactly as u02_modules/docs_u02.py documents the row-54 U02
# verifier and u03_modules/docs_u03.py / u04_modules/docs_u04.py document
# their siblings (U05_MODULES = None, recorded below — a doc that claims a
# manifest row that does not exist is drift). Imported BY NAME as
# u05_modules.docs_u05 when a consumer wants the tooling's contract surfaces
# as DATA (module inventory, the four verified items, the house exit codes,
# the doctrine) or its rendered README as text.
#
# WHAT THIS OWNS:
#   1. THE README. The module docstring below IS the U05 tooling README:
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
#      clients (CafClient / InternalRailClient) — the docs record that
#      doctrine, they do not re-implement it.
#
# THE TOOLING THIS DOCUMENTS (orientation):
#   MASTER-SPEC U05 — the SCOPED-READ and FILTER-SCOPE LAW of the anthology
#   engine (SPEC 7.2 / 11.3): every participant-facing read is scoped to ONE
#   subject, never an unscoped sweep; and the U05 pipeline rule "Form is
#   universal-intake" gates ONLY the universal author-intake form. Four
#   gates in a FIXED order (the scope law, the live workflow read, the
#   pipeline-rule scope check, the single-filter self-discipline):
#   1. SCOPED-READ LAW — every participant-facing read is keyed by EXACTLY
#      ONE non-empty filter value; the ledger scopes by anthology_id
#      (participant_key is the composite contact_id::anthology_id — the
#      KEYING LAW, anthology_state.participant_key) and the scoped mirror
#      reads are parameterized WHERE anthology_id=? queries, never a table
#      sweep; a minted participant capability is single-gate-scoped
#      (gate_engine.mint_token payload {pk, g, iat, exp, jti},
#      HMAC-SHA256 over "v1.<payload_b64>", foreign-gate refused) and the
#      PIN binds the SAME (pk, gate, exp) material.
#   2. LIVE WORKFLOW READ — the "Anthology Intake Fire" front-door workflow
#      is found by name / pinned by id on the location's live workflow
#      listing and its ONE id reported (workflow_reader.py; the internal
#      rail GET /workflow/<loc>/list?limit=200 — the ONLY workflow surface
#      this repo has PROVEN live, Skill 58; never a fabricated id).
#   3. PIPELINE-RULE SCOPE CHECK — the U05 pipeline rule filter must be
#      EXACTLY "Form is universal-intake" (form == "universal-intake",
#      byte-exact, one space around "is", nothing else) to be in intake
#      scope; anything else — an EMPTY filter, a wildcard, a renamed form
#      token, a byte-drifted spelling — is OUT of scope (scope_checker.py,
#      pure, side-effect-free, never echoes the filter).
#   4. THE ATTACK BOUNDARY — the empty / unscoped filter (attack_unscoped.py
#      — an unfiltered read reaches EVERY ledger row across ALL anthologies
#      and must FAIL) and the wrong form on the filter (attack_wrong_form.py
#      — a submission whose form id is NOT the universal author-intake form
#      must be REFUSED at the filter, never routed into the anthology
#      ledger), with golden_scoped.py shipping the golden single-subject
#      control so every pass/fail split discriminates the ONE-variable
#      boundary and never a broken instrument (the negative-result
#      contract: a gate that fails everything is a broken check, not a real
#      fault).
#   5. THE NEGATIVE MIRROR — negative_verifier.py certifies, fail-closed,
#      that a submission (the universal-review decision form, PRD Section
#      4 / U8) does NOT fire the Intake Fire trigger: the trigger fires
#      ONLY when the submission identifies as the universal author-intake
#      form, so a payload the trigger's own gate deterministically refuses
#      (basis not_a_dict / form_token_missing / form_token_unrecognized)
#      is CERTIFIED does-not-fire; a payload that presents intake identity
#      (fires_intake True — AF-AE-NEGATIVE-INTAKE-FIRE) or whose firing is
#      INDETERMINATE (stage_token_mismatch — never blessed) is REFUSED; a
#      broken / emptied policy STOPS (exit 2 — the empty-filter attack
#      shape certifies nothing). The scope law is IMPORTED from
#      u02_modules.scope_check (read once, never re-implemented); the
#      module is pure, deterministic, credential-free, and never prints
#      the payload.
#   6. THE GATED WRITE — scope_applier.py is the U05 family's ONLY write
#      surface: it corrects the trigger SCOPE FILTER of a release-
#      notification workflow (the tag->notification automation, U02 item
#      4's contract rows) so the workflow fires ONLY on its contract
#      contact_tag trigger — and it REFUSES to write unless the operator
#      passes --execute (every other invocation is a read-only DRY-RUN
#      that prints exactly the PUT it WOULD send); the PUT rides the
#      internal Firebase rail (the ONLY trigger-write surface this repo
#      has PROVEN — Skill 44's workflow_builder) and the post-PUT read-
#      back must prove the fix byte-for-byte (AF-AE-READBACK-MISMATCH).
#   The scope law is pinned from the SINGLE AUTHORITIES — anthology_state.py
#   participant_key (the KEYING LAW), gate_engine.mint_token (the token / PIN
#   law), anthology_book._bad_id_shape (the shape law), intake_router.py
#   build_canonical + form_reader.DEFAULT_UNIVERSAL_INTAKE_FORM_ID (the form
#   law) — never a second implementation; a drift in an authority breaks the
#   fixture's self-test FIRST (fail-closed: an inconsistent law is a
#   refusal, never a blind pass).
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE, everywhere in this tooling. The
# U05 fixtures hold NO credential surface at all (the attacks, the golden
# control, the scope gate, and the negative verifier are pure in-memory
# metadata over SYNTHETIC ids — ANTH_deadbeefcafebabed00d /
# ANTH_0beefdeadbeefdeadbeef / cnt_golden / anth_golden / ptcpt_scoped_0001
# — never a live id, never a real participant, never a real token); the
# family's live surfaces (workflow_reader's rail read, scope_applier's
# apply) resolve their credentials through the house labels (PIT first:
# CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_API_KEY / GOHIGHLEVEL_API_KEY /
# GOHIGHLEVEL_PIT / GHL_API_KEY, then the internal rail:
# ANTHOLOGY_GHL_FIREBASE_REFRESH_TOKEN / GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN
# / GHL_FIREBASE_REFRESH_TOKEN + the Firebase API-key label; live process
# env first, then the three canonical client env stores; SET / NOT SET only —
# a token value is NEVER printed). Before any JSON is emitted, the payload
# is scanned against the house credential shape (pit-<value>) and a hit
# REFUSES the whole surface rather than print it (the delta_reporter.py
# never-a-real-token doctrine). The workflow id / location id are masked to
# their LAST 4 characters on every report — never printed in full; the
# filter string itself is only ever COMPARED, never echoed beyond a reason
# code; a rail response body is never surfaced (it could echo a credential).
#
# BROWSER UA (CF 1010 LAW): every request rides reg.CafClient /
# reg.InternalRailClient (and the internal-rail headers built by
# anthology_registry._internal_request_headers), which apply CAF_BROWSER_UA
# on EVERY request so the Cloudflare edge fronting services.leadconnectorhq.com /
# backend.leadconnectorhq.com never 1010s a verify request (CF error 1010;
# the W0.6 / GK-09 discipline — urllib's default "Python-urllib/x.y" is
# 403'd at the WAF edge before it ever reaches the API). The U05 fixtures
# make NO network call at all, so they define NO User-Agent constant of
# their own — house_rules.py PORTED CAF_BROWSER_UA / CAF_VERSION_HEADER
# byte-for-byte from the registry (the ONE canonical constant surface of
# the family) and the self-tests PIN the constants equal so a registry
# regression is caught HERE first. Scope-vs-edge-block discrimination: a
# bare 401/403 is HELD (UpstreamBlockedError / CafUnreachable /
# InternalRailUnavailable), never mislabeled as a scope problem; a genuine
# scope denial is a STOP (exit 2, AF-AE-PIT-SCOPE).
#
# FAIL-CLOSED (the whole point): a missing credential STOPS (exit 2), an
# empty / malformed / unrecognized filter is NOT in scope (scope_checker
# returns ok=False with a typed reason — the caller decides the consequence,
# this module NEVER fabricates a pass), an unreadable listing / a listing
# with NO "Anthology Intake Fire" row / a pinned id the listing lacks is a
# FAIL (exit 5, never a fabricated pass, never an id guessed from memory), a
# transport / edge failure is HELD (exit 3, UNDETERMINED — never a
# verdict), the wrong-form attack and the empty-filter attack MUST FAIL
# every gate they touch (exit 5), a submission that FIRES Intake Fire or is
# INDETERMINATE is never certified does-not-fire (exit 5; a broken / emptied
# policy certifies NOTHING — exit 2), a write NEVER happens without the
# operator's --execute and every write must read back byte-for-byte (exit 5,
# AF-AE-READBACK-MISMATCH), and a drifted authority (anthology_state /
# gate_engine / anthology_book / intake_router / form_reader /
# u02_modules.scope_check) breaks the fixture self-tests FIRST (exit 4 — a
# tamper never masquerades as exit 1). A success is claimed ONLY when the
# filter is byte-exact and the live surface agrees with its source of
# truth. Every deviation is NAMED with its code — never a bare "something
# failed".
#
# DOCTRINE (house, per anthology_registry.py / drive_adapter.py): move in
# silence (operator-verbose only); NOTHING Anthropic in any runtime file;
# Convert and Flow naming in every client surface; STDLIB ONLY; calls NO
# model; never a client PII; a law is read once, in one module (the
# delta_reporter.py single-implementation doctrine — anthology_state owns
# the KEYING LAW, gate_engine owns the token law, anthology_book owns the
# shape law, intake_router / form_reader own the form law,
# u02_modules.scope_check owns the Intake Fire scope law, workflow_reader
# owns the workflow read, house_rules owns the constant surface, and the
# fixtures derive from them, never re-implement). READ-ONLY by doctrine —
# the checkers never write; scope_applier is the ONE gated write surface
# (its own --execute, the dispatcher NEVER writes). Self-test failures are
# exit 4 (enforced violation, the AF-AE-TEMPLATE-ATTACK / AF-AE-GOLDENSCOPED-*
# / AF-AE-ATTACKUNSCOPED-* / AF-AE-ATTACKWRONGFORM-* / AF-AE-NEGATIVE-ATTACK
# families) — a tamper never masquerades as exit 1.
#
# USAGE (this module's own machine surface — pure data, nothing to leak):
#   python3 docs_u05.py                ONE JSON catalog of the whole tooling
#   python3 docs_u05.py readme         the rendered README (markdown text)
#   python3 docs_u05.py self-test      OFFLINE drift gate over the docs vs
#                                      the shipped tree; 0 clean, 4 drift
# =============================================================================
"""docs_u05.py -- README / module docstring for the U05 tooling, as an
importable fail-closed pure-data module: the scoped-read and filter-scope
law family (scope_checker / golden_scoped / attack_unscoped /
attack_wrong_form / workflow_reader / house_rules / negative_verifier /
scope_applier / test_scope_checker / test_negative_verifier /
example_usage under the manifest row-54 "template live
verify (U02)" shipping doctrine — the family's OWN manifest row PENDING),
its four verified items, the u05_modules inventory, the house exit codes,
and the credential / browser-UA / doctrine contracts. Performs no I/O at
import and holds no credential; readme() is rendered from the same
structured data the self-test asserts against, so documentation and data
cannot drift."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# The fixed report contract (mirrors the golden-fixture naming discipline).
# ---------------------------------------------------------------------------
DOC_CONTRACT = "anthology-engine-u05-tooling-docs"
SCHEMA_VERSION = 1

# The U05 family's driver is its verifier under the U02 row-54 shipping law;
# the u05_modules/ siblings ship as non-manifest helpers (the
# delivery_report.py row-12 pattern, exactly the docs_u02.py / docs_u03.py /
# docs_u04.py siblings). The U05 family's OWN manifest row is NOT yet
# stamped in ENGINE-MANIFEST.json (verified at ship time, 2026-08-11): it is
# PENDING, staged under the manifest-pending/u02.json · u03.json · u04.json
# pattern — this module records None rather than invent a row number (a doc
# that claims a row that does not exist is drift).
U05_VERIFIER = None  # PENDING — the family's single driver is not yet named
U05_MANIFEST_ROW = None  # PENDING — the family is not yet stamped
U05_SHIPPING_VERSION = "v0.1.23 (2026-08-11)"  # skill-version at ship time

# ---------------------------------------------------------------------------
# THE FOUR VERIFIED ITEMS (MASTER-SPEC U05 — the family's four gates, in
# the FIXED order the scope law carries them). Item numbers are load-bearing
# (positions 1..4, exactly four — self-test pins the count); the title is
# the README heading, asserts the fail-closed claim, sources the engine's
# source of truth, and fails the operator surface on drift.
# ---------------------------------------------------------------------------
VERIFY_ITEMS = (
    {
        "item": 1,
        "title": "Scoped-read law — every read scoped to ONE subject",
        "asserts": ("every participant-facing read is keyed by EXACTLY ONE "
                    "non-empty filter value: the ledger scopes by "
                    "anthology_id (participant_key is the composite "
                    "contact_id::anthology_id — the KEYING LAW, "
                    "anthology_state.participant_key), the scoped mirror "
                    "reads are parameterized WHERE anthology_id=? queries, "
                    "never a table sweep; a minted participant capability "
                    "is single-gate-scoped (gate_engine.mint_token payload "
                    "{pk, g, iat, exp, jti}, HMAC-SHA256 over "
                    "'v1.<payload_b64>', foreign-gate refused) and the PIN "
                    "binds the SAME (pk, gate, exp) material; the EMPTY "
                    "filter is the unscoped sweep — an unfiltered read "
                    "reaches EVERY ledger row and must FAIL, never pass"),
        "source": "SPEC 7.2 / 11.3 — anthology_state.participant_key (the "
                  "KEYING LAW) + gate_engine.mint_token (the token / PIN "
                  "law); mirrored in mc_board._read_participant_keys and "
                  "the anthology_state stale-cursors",
        "fails": "AF-AE-SCOPED-SUBJECT-MISSING / AF-AE-SCOPED-FOREIGN-ROW / "
                 "AF-AE-SCOPED-ROW-COUNT (exit 5); the empty-filter attack "
                 "FAILS every gate it touches (exit 5, "
                 "AF-AE-ATTACKUNSCOPED-*)",
    },
    {
        "item": 2,
        "title": "Intake Fire workflow readable (name law + pin law)",
        "asserts": ("the 'Anthology Intake Fire' front-door workflow is "
                    "found by NAME on the location's live workflow listing "
                    "(a row whose type is 'workflow' and whose normalized "
                    "name is the contract name with dashes -> spaces) and "
                    "reports its ONE id; --workflow-id PINS the id and a "
                    "pinned id the listing does not contain is a MISMATCH "
                    "(exit 5), never a silent pass; a listing with NO "
                    "'Anthology Intake Fire' row is a FAIL — never a "
                    "fabricated pass, never an id guessed from memory; "
                    "near-miss rows are REPORTED as candidates (masked), "
                    "never silently ignored"),
        "source": "the internal rail GET /workflow/<loc>/list?limit=200 "
                  "(backend.leadconnectorhq.com — the ONLY workflow surface "
                  "this repo has PROVEN live, Skill 58) with the "
                  "token-id / channel / source / version header set "
                  "reg.InternalRailClient already sends",
        "fails": "af_code WORKFLOWS-NOT-FOUND / WORKFLOWS-EMPTY / "
                 "PIN-MISSING (exit 5); an unreadable listing shape STOPS "
                 "(exit 2); a bare 401/403 is HELD (exit 3), never "
                 "mislabeled as scope",
    },
    {
        "item": 3,
        "title": "Pipeline-rule scope — filter is 'Form is universal-intake'",
        "asserts": ("the U05 pipeline rule (filter == 'Form is "
                    "universal-intake', form == 'universal-intake', "
                    "byte-exact, one space around 'is', nothing else) gates "
                    "ONLY the universal author-intake form; anything else — "
                    "an EMPTY filter, a wildcard, a renamed form token, a "
                    "byte-drifted spelling — is OUT of scope and must not "
                    "be accepted as the intake gate; the check returns "
                    "(ok, filter_set) with a typed reason and NEVER echoes "
                    "the filter string or the payload beyond a reason code"),
        "source": "config/route-template.json /hooks/anthology-intake "
                  "(match.source 'anthology-intake') + form_reader's "
                  "DEFAULT_UNIVERSAL_INTAKE_FORM_ID (the ONE owner of the "
                  "form pin)",
        "fails": "ok=False with a typed reason (never a fabricated pass); "
                 "the caller decides the consequence — a missing / "
                 "malformed / unrecognized filter is NOT in scope",
    },
    {
        "item": 4,
        "title": "Attack boundary — the FAIL paths are proven to FAIL",
        "asserts": ("the empty / unscoped anthology filter MUST FAIL every "
                    "unscoped-read gate (attack_unscoped: verify_live exit "
                    "5 on the empty / whitespace-only / shape-illegal "
                    "filter; scoped_rows REFUSES, never a verdict) and the "
                    "wrong form on the filter MUST FAIL every byte-exact "
                    "form gate (attack_wrong_form: verify_submission exit 5 "
                    "on the swapped form id, masked, naming the expected "
                    "one); golden_scoped ships the golden single-subject "
                    "control and negative_verifier's own golden battery "
                    "certifies does-not-fire while the fires-intake and "
                    "INDETERMINATE shapes are refused — so every pass/fail "
                    "split discriminates the ONE-variable boundary and "
                    "never a broken instrument — the negative-result "
                    "contract: a gate that fails everything is a broken "
                    "check, not a real fault"),
        "source": "the SINGLE AUTHORITIES — anthology_book._bad_id_shape "
                  "(the shape law), intake_router.build_canonical + "
                  "form_reader.DEFAULT_UNIVERSAL_INTAKE_FORM_ID (the form "
                  "law), u02_modules.scope_check (the Intake Fire scope "
                  "law) — never a second implementation; the attacks are "
                  "deterministic and single-variable by construction",
        "fails": "the attack fixtures' own payload() REFUSES any drift "
                 "(exit 5); a drifted authority breaks the fixture "
                 "self-tests FIRST (exit 4, AF-AE-ATTACKUNSCOPED-* / "
                 "AF-AE-ATTACKWRONGFORM-* / AF-AE-GOLDENSCOPED-* / "
                 "AF-AE-NEGATIVE-ATTACK families)",
    },
)

# ---------------------------------------------------------------------------
# THE MODULE INVENTORY. `place` names the directory relative to this module
# (the u05_modules package itself); self-test proves each name exists at
# that place. `role` is the one-line contract each module owns; `offline`
# names the credential-free surface; `exit_codes` follows the house
# convention (0/1/2/3/5, 4 = self-test).
# ---------------------------------------------------------------------------
MODULES = (
    {
        "name": "__init__.py",
        "place": "scripts/u05_modules/",
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
        "name": "scope_checker.py",
        "place": "scripts/u05_modules/",
        "manifest_row": None,
        "role": ("the PIPELINE-RULE SCOPE GATE — the pure, side-effect-"
                 "free predicate that the U05 pipeline rule (filter == "
                 "'Form is universal-intake') gates ONLY the universal "
                 "author-intake form: check(payload) returns (ok, "
                 "filter_set) — (True, {filter, form}) only when the "
                 "filter is byte-exact; ANY ambiguity (empty / wildcard / "
                 "renamed token / byte-drift) returns ok=False with a typed "
                 "reason; NEVER echoes the filter string or the payload "
                 "beyond a reason code; the caller decides the consequence "
                 "— this module NEVER fabricates a pass"),
        "offline": "entirely — pure local shape analysis, no network, no "
                   "token surface",
        "exit_codes": "0/1/2/4/5",
    },
    {
        "name": "golden_scoped.py",
        "place": "scripts/u05_modules/",
        "manifest_row": None,
        "role": ("the GOLDEN SCOPED-READ FIXTURE — the canonical in-memory "
                 "single-subject payload of the engine's scoped-read law: "
                 "GOLDEN_SCOPED = {filter_key: 'anthology_id', "
                 "filter_value: 'anth_golden', subject_key: "
                 "participant_key('cnt_golden', 'anth_golden') — the "
                 "KEYING LAW, anthology_state.participant_key, never "
                 "hardcoded —, gate_id: 's5_participant'}; "
                 "MappingProxyType-frozen canon (every mutation route "
                 "raises, proven by self-test) + deep-copied payload "
                 "surfaces; payload() REFUSES (exit 5) on an empty filter, "
                 "a foreign subject row, a foreign gate, a malformed read, "
                 "or a credential-shaped value — an inconsistent law is a "
                 "refusal, never a blind pass"),
        "offline": "entirely — pure data + builders (synthetic ids only)",
        "exit_codes": "0/1/4/5",
    },
    {
        "name": "attack_unscoped.py",
        "place": "scripts/u05_modules/",
        "manifest_row": None,
        "role": ("the U05 ATTACK: the EMPTY-ANTHOLOGY-FILTER read that "
                 "must FAIL — an unfiltered read reaches EVERY ledger row "
                 "across ALL anthologies; scoped_rows() REFUSES an empty / "
                 "whitespace-only / shape-illegal filter (FixtureError, "
                 "never a verdict), verify_live() judges the read and "
                 "exits 5 on the attack naming the defect (empty / "
                 "whitespace-only / shape-legal but present) while the "
                 "true one-anthology scoped read exits 0; payload() ships "
                 "EXACTLY the one empty-filter attack and REFUSES any "
                 "drift (exit 5); every anthology id reported by MASKED "
                 "MARKER only (last 4 chars)"),
        "offline": "plan + self-test (no network, no token surface)",
        "exit_codes": "0/1/4/5",
    },
    {
        "name": "attack_wrong_form.py",
        "place": "scripts/u05_modules/",
        "manifest_row": None,
        "role": ("the U05 ATTACK: the WRONG FORM ON THE FILTER that must "
                 "FAIL — a submission whose form id is NOT the universal "
                 "author-intake form (a legacy contact form, a cross-"
                 "location form, a lookalike 'Intake' clone) must be "
                 "REFUSED at the intake filter, never routed into the "
                 "anthology ledger; the canonical submission is built by "
                 "intake_router.build_canonical (the single authority) "
                 "then the ONE form id is swapped; verify_submission() "
                 "exits 5 on the wrong-form attack (naming the wrong id, "
                 "masked, and the expected one) and 0 on the true "
                 "canonical submission; payload() ships EXACTLY the "
                 "one-wrong-form shape and REFUSES any drift (exit 5)"),
        "offline": "plan + self-test (no network, no token surface)",
        "exit_codes": "0/1/4/5",
    },
    {
        "name": "workflow_reader.py",
        "place": "scripts/u05_modules/",
        "manifest_row": None,
        "role": ("the LIVE WORKFLOW READER — the ONE shared live surface of "
                 "the U05 family: reads the location's workflow listing "
                 "(the internal rail GET /workflow/<loc>/list?limit=200, "
                 "backend.leadconnectorhq.com — the ONLY workflow surface "
                 "this repo has PROVEN live, Skill 58; the PUBLIC v2 has "
                 "no proven workflows listing, so it is NOT used) and "
                 "FINDS 'Anthology Intake Fire' by the name law, pins by "
                 "--workflow-id, reports the ONE workflow id (found=false "
                 "carries NO id — no id, no pass), names near-miss "
                 "candidates with masked ids, and REFUSES the whole "
                 "surface on a credential-shaped payload hit; rides "
                 "reg.CafClient / reg.InternalRailClient (CAF_BROWSER_UA "
                 "on every request)" ),
        "offline": "plan + self-test (no token, no network); the live read "
                   "needs a location-scoped credential BY LABEL",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "house_rules.py",
        "place": "scripts/u05_modules/",
        "manifest_row": None,
        "role": ("the HOUSE RULES CONSTANTS MODULE — the ONE canonical "
                 "surface for the engine's fixed laws: CAF_BROWSER_UA and "
                 "CAF_VERSION_HEADER PORTED byte-for-byte from "
                 "anthology_registry (the CF-1010 browser-UA law and the "
                 "2021-07-28 version header — both public per-request "
                 "headers, neither a secret; the offline self-test pins "
                 "the copies byte-equal to the registry) plus the complete "
                 "AF autofail code table mirrored from ENGINE-MANIFEST.json "
                 "(the AF-AE-* families + AE_DEPS_MISSING) as immutable "
                 "constants so a code can never be misspelled or drifted "
                 "between a raising module and the manifest"),
        "offline": "entirely — pure constant surface; self-test asserts "
                   "byte-equality with the registry and the manifest",
        "exit_codes": "0/1/4",
    },
    {
        "name": "negative_verifier.py",
        "place": "scripts/u05_modules/",
        "manifest_row": None,
        "role": ("the NEGATIVE VERIFIER — certifies, fail-closed, that a "
                 "submission (the universal-review decision form, PRD "
                 "Section 4 / U8) does NOT fire the Intake Fire trigger; "
                 "the scope law is IMPORTED from u02_modules.scope_check "
                 "(read once, never re-implemented — the single-"
                 "implementation doctrine); a payload the trigger's own "
                 "gate deterministically refuses (basis not_a_dict / "
                 "form_token_missing / form_token_unrecognized) is "
                 "CERTIFIED does-not-fire, while a payload that presents "
                 "intake identity (fires_intake True — AF-AE-NEGATIVE-"
                 "INTAKE-FIRE) or whose firing is INDETERMINATE "
                 "(stage_token_mismatch) is REFUSED (exit 5), and a broken "
                 "/ emptied policy STOPS (exit 2 — the empty-filter attack "
                 "shape certifies nothing); pure and credential-free — "
                 "never prints the payload, never a token"),
        "offline": "entirely — pure deterministic predicate over ONE "
                   "payload (no network, no credential)",
        "exit_codes": "0/1/2/4/5",
    },
    {
        "name": "scope_applier.py",
        "place": "scripts/u05_modules/",
        "manifest_row": None,
        "role": ("the WORKFLOW TRIGGER-SCOPE APPLIER — the U05 family's "
                 "ONLY write surface: corrects the trigger SCOPE FILTER of "
                 "a release-notification workflow (the tag->notification "
                 "automation, U02 item 4's contract rows) so the workflow "
                 "fires ONLY on its contract contact_tag trigger, and "
                 "REFUSES to write unless the operator passes --execute "
                 "(every other invocation is a read-only DRY-RUN printing "
                 "exactly the PUT it WOULD send); the PUT rides the "
                 "internal Firebase rail (the ONLY trigger-write surface "
                 "this repo has PROVEN — Skill 44's workflow_builder; a "
                 "rail rejection is AF-AE-TRIGGER-SCOPE-VALIDATION, exit "
                 "2) and the post-PUT read-back must prove the fix "
                 "byte-for-byte (exit 5, AF-AE-READBACK-MISMATCH)"),
        "offline": "plan + self-test (no token, no network); apply (dry-run "
                   "included) needs the rail credentials — a truthful plan "
                   "requires the live read",
        "exit_codes": "0/1/2/3/4/5",
    },
    {
        "name": "test_scope_checker.py",
        "place": "scripts/u05_modules/",
        "manifest_row": None,
        "role": ("the INDEPENDENT PYTEST BATTERY of the scope gate — "
                 "offline contract tests over the byte-exact filter law "
                 "(the canonical top-level filter surface, the "
                 "workflow.trigger.filters row shape, the trigger.filters "
                 "shape, and the pipeline.rules row shape each carry the "
                 "SAME law, read from scope_checker.UNIVERSAL_INTAKE_FILTER "
                 "— never re-typed in the file) and the fail-closed "
                 "directions (missing / empty / whitespace-only / wildcard "
                 "/ unrelated-form / bare-token / case-drifted / spacing-"
                 "drifted filters are REFUSED with the typed reason); "
                 "network-free, credential-free, subprocess-free — "
                 "provenance only, the family's dispatcher asserts the "
                 "file's presence, the tests run under pytest"),
        "offline": "entirely — pytest battery, no network, no secrets",
        "exit_codes": "n/a (pytest battery; a failing run fails the "
                      "dispatcher self-test, exit 4)",
    },
    {
        "name": "test_negative_verifier.py",
        "place": "scripts/u05_modules/",
        "manifest_row": None,
        "role": ("the INDEPENDENT PYTEST BATTERY of the negative verifier "
                 "— offline unit tests proving the does-not-fire law from "
                 "the test side: the golden universal-review submission is "
                 "CERTIFIED does-not-fire (so a verifier that fails "
                 "EVERYTHING is never mistaken for a real discrimination), "
                 "every intake alias x intake stage-token combination "
                 "FIRES (fires_intake True — the defect the verifier "
                 "exists to catch), stage-disagreeing shapes are REFUSED "
                 "INDETERMINATE (never certified), and an EMPTIED policy "
                 "(stage_tokens / form_candidates emptied — the "
                 "attack_unscoped empty-filter shape) certifies NOTHING, "
                 "STOP exit 2; network-free and credential-free (reg."
                 "CafClient is NEVER constructed, no env var read, no "
                 "subprocess); the leak scan is re-proven here — the "
                 "'pit-' / 'Bearer' shapes never appear on any captured "
                 "surface"),
        "offline": "entirely — pytest battery, no network, no secrets",
        "exit_codes": "n/a (pytest battery; a failing run fails the "
                      "dispatcher self-test, exit 4)",
    },
    {
        "name": "example_usage.py",
        "place": "scripts/u05_modules/",
        "manifest_row": None,
        "role": ("the EXAMPLE-USAGE RUNNER — a fail-closed WORKED EXAMPLE "
                 "of the U05 live surface end to end: READ the Intake Fire "
                 "front-door workflow through the internal rail, then run "
                 "every pure sibling law over the read and the canonical "
                 "fixtures (the golden scoped gate PASSES, the empty-filter "
                 "attack FAILS as it must, the wrong-form attack FAILS as "
                 "it must, the negative verifier CERTIFIES does-not-fire) "
                 "and emit ONE JSON report; makes NO judgment of its own — "
                 "every judgment is delegated to the sibling modules "
                 "(never a second implementation of a law); an expected-"
                 "fail step that does NOT fail is a FAIL of the "
                 "composition (exit 5); the live surface unreachable is "
                 "HELD (exit 3, UNDETERMINED — never 'verified'); --plan "
                 "and --self-test are OFFLINE (AF-AE-EXAMPLE-USAGE-* on a "
                 "tamper)"),
        "offline": "plan + self-test (no token, no network); run needs "
                   "the rail credential BY LABEL",
        "exit_codes": "0/1/2/3/4/5",
    },
)

# ---------------------------------------------------------------------------
# HOUSE EXIT CODES (0/1/2/3/5; 4 = enforced violation). The exact contract
# the U05 family commits to; self-test pins all six.
# ---------------------------------------------------------------------------
EXIT_CODES = {
    0: "verified success — the filter is byte-exact and the live surface "
       "agrees with its source of truth (also plan / dry-run / self-test / "
       "a certified does-not-fire negative)",
    1: "unexpected error (top-level guard; never a secret leak)",
    2: ("STOP refusal — label NOT SET / non-pit- value / usage / a "
        "malformed listing shape that cannot be read faithfully / an "
        "empty or malformed scope policy (the empty-filter attack shape — "
        "a broken filter certifies nothing) / a module STOP-family "
        "refusal (unreadable payload, malformed filter, a genuine scope "
        "denial — AF-AE-PIT-SCOPE, a rail rejection of the PUT — "
        "AF-AE-TRIGGER-SCOPE-VALIDATION)"),
    3: ("HELD — Convert and Flow unreachable / Cloudflare edge block "
        "(CF error 1010) / the internal rail unavailable / an "
        "applied-but-unreadable PUT (UNDETERMINED, never a verdict)"),
    4: ("self-test FAILED (AF-AE-TEMPLATE-ATTACK / AF-AE-GOLDENSCOPED-* / "
        "AF-AE-ATTACKUNSCOPED-* / AF-AE-ATTACKWRONGFORM-* / "
        "AF-AE-NEGATIVE-ATTACK family, enforced violation) — a tamper "
        "never masquerades as exit 1"),
    5: ("mismatch / fail-closed default — an empty or byte-drifted "
        "filter, a wrong form on the filter, a submission that FIRES "
        "Intake Fire or is INDETERMINATE (never certified does-not-"
        "fire), no 'Anthology Intake Fire' row, a pinned id absent from "
        "the listing, a foreign subject row, a fixture payload that "
        "drifted (AF-AE-SCOPED-SUBJECT-MISSING / AF-AE-SCOPED-FOREIGN-ROW "
        "/ AF-AE-SCOPED-ROW-COUNT / AF-AE-ATTACKUNSCOPED-* / "
        "AF-AE-ATTACKWRONGFORM-* / AF-AE-NEGATIVE-INTAKE-FIRE), a "
        "read-back mismatch after the trigger PUT (AF-AE-READBACK-"
        "MISMATCH), or a DEFERRED live read without --allow-deferred"),
}

# ---------------------------------------------------------------------------
# THE AF AUTOfail FAMILY of the U05 tooling — the codes the family's own
# surfaces declare. The U05-specific codes are NOT yet stamped in
# ENGINE-MANIFEST.json (the family is PENDING — verified at ship time,
# 2026-08-11); AF-AE-PIT-SCOPE and the shared AF-AE-TEMPLATE-ATTACK /
# AF-AE-READBACK-MISMATCH codes already live in the manifest. Self-test
# failures are exit 4, never 1.
# ---------------------------------------------------------------------------
AF_CODES = (
    ("AF-AE-SCOPED-SUBJECT-MISSING", 5,
     "the scoped listing does not carry the golden subject under its "
     "golden composite key — the one-subject read lost its subject "
     "(golden_scoped payload gate)"),
    ("AF-AE-SCOPED-FOREIGN-ROW", 5,
     "the scoped listing carries a row that is NOT the golden subject — "
     "a foreign subject leaked into the one-subject read "
     "(golden_scoped payload gate)"),
    ("AF-AE-SCOPED-ROW-COUNT", 5,
     "the scoped listing carries a row count other than exactly one — "
     "the one-subject read is no longer one (golden_scoped payload "
     "gate)"),
    ("AF-AE-GOLDENSCOPED-*", 4,
     "an attack tripped the golden scoped fixture's OFFLINE self-test "
     "(enforced violation)"),
    ("AF-AE-ATTACKUNSCOPED-*", 4,
     "an attack tripped the empty-filter attack fixture's OFFLINE "
     "self-test (enforced violation) — the empty-filter attack passed a "
     "gate, or a drifted authority was not caught HERE first"),
    ("AF-AE-ATTACKWRONGFORM-*", 4,
     "an attack tripped the wrong-form attack fixture's OFFLINE "
     "self-test (enforced violation) — the wrong-form attack passed a "
     "gate, or a drifted authority was not caught HERE first"),
    ("AF-AE-NEGATIVE-INTAKE-FIRE", 5,
     "the negative verifier certified does-not-fire for a submission "
     "that IDENTIFIES as the universal author-intake form with an "
     "agreeing stage token — the Intake Fire trigger WOULD fire; the "
     "negative claim is FALSE (the FAIL the verifier exists to catch)"),
    ("AF-AE-NEGATIVE-ATTACK", 4,
     "an attack tripped the negative verifier's OFFLINE self-test "
     "(enforced violation) — a fires-intake or INDETERMINATE shape was "
     "certified, or a drifted scope_check was not caught HERE first"),
    ("AF-AE-TRIGGER-SCOPE-VALIDATION", 2,
     "the internal rail REFUSED the trigger-scope PUT — a data-contract "
     "problem to resolve in the Convert and Flow UI; the filter was NOT "
     "corrected (scope_applier STOP; not yet stamped in "
     "ENGINE-MANIFEST.json)"),
    ("AF-AE-PIT-SCOPE", 2,
     "a genuine location-scope denial signature on the live read — "
     "STOP, never mislabeled as an edge block (workflow_reader; the "
     "code is already stamped in ENGINE-MANIFEST.json)"),
    ("AF-AE-TEMPLATE-ATTACK", 4,
     "an attack fixture tripped the OFFLINE self-test of the verifier "
     "or a family battery (enforced violation — the house code, shared "
     "with the U02 / U03 / U04 families)"),
)

# ---------------------------------------------------------------------------
# DOCTRINE — the house rules the whole U05 tooling commits to, as data so
# the README renders them from the same source the self-test asserts.
# ---------------------------------------------------------------------------
DOCTRINE = (
    ("Fail-closed", "a missing credential, a malformed input, an "
     "unreadable source, or a live read that cannot be completed is a "
     "REFUSAL or a recorded FAIL — never a blind pass, never a fabricated "
     "success; a strict subset is a MISSING, never a pass; an empty / "
     "malformed / unrecognized filter is NOT in scope with a typed reason; "
     "a listing with no 'Anthology Intake Fire' row is a FAIL, never a "
     "silent empty; an id is NEVER guessed from memory"),
    ("Secrets", "credentials resolve BY LABEL only (SET / NOT SET); a "
     "token value is never printed, echoed, or reflected in any surface; "
     "before any JSON is emitted the payload is scanned against the house "
     "credential shape (pit-<value>) and a hit REFUSES the whole surface "
     "(the delta_reporter.py never-a-real-token doctrine); the workflow / "
     "location ids are MASKED to their last 4 characters in every report; "
     "the filter string is only ever COMPARED, never echoed beyond a "
     "reason code"),
    ("Browser UA", "every request to GoHighLevel / Convert and Flow "
     "(services.leadconnectorhq.com) and the internal rail "
     "(backend.leadconnectorhq.com) rides CAF_BROWSER_UA (reg.CafClient / "
     "reg.InternalRailClient) — urllib's default 'Python-urllib/x.y' is "
     "403'd at the WAF edge (CF error 1010) before it ever reaches the "
     "API (W0.6 / GK-09); the U05 fixtures make NO network call, so they "
     "define NO User-Agent constant of their own — the self-tests PIN "
     "BROWSER_UA == reg.CAF_BROWSER_UA so a registry regression is caught "
     "HERE first"),
    ("Scope vs edge", "a bare 401/403 is HELD (UpstreamBlockedError / "
     "CafUnreachable), never mislabeled as a scope problem; a genuine "
     "location-scope denial is a STOP (exit 2, AF-AE-PIT-SCOPE)"),
    ("Synthetic ids only", "the fixtures carry SYNTHETIC deterministic "
     "ids only (ANTH_deadbeefcafebabed00d / ANTH_0beefdeadbeefdeadbeef / "
     "cnt_golden / anth_golden / ptcpt_scoped_0001 — the synthetic-id "
     "discipline of the u02/u03/u04 golden siblings) — a fixture id is "
     "never a real participant, form, or anthology id, and never a real "
     "token; a capability-shaped material is a synthetic marker "
     "(cap_golden_*)"),
    ("Single authority", "a law is read once, in one module: "
     "anthology_state.participant_key owns the KEYING LAW, "
     "gate_engine.mint_token owns the token / PIN law, "
     "anthology_book._bad_id_shape owns the shape law, "
     "intake_router.build_canonical + form_reader.DEFAULT_UNIVERSAL_"
     "INTAKE_FORM_ID own the form law, u02_modules.scope_check owns the "
     "Intake Fire scope law, workflow_reader owns the workflow read, "
     "house_rules owns the constant surface (UA / version / AF codes) — "
     "the fixtures derive from them, never re-implement; a drift in an "
     "authority breaks the fixture's self-test FIRST"),
    ("Negative-result contract", "the attack fixtures carry their OWN "
     "golden controls (payload_true / the golden canonical submission / "
     "the one-anthology scoped read) and negative_verifier certifies "
     "does-not-fire ONLY on a provable basis (fires_intake True or "
     "INDETERMINATE is REFUSED, never blessed), so every pass/fail split "
     "discriminates the ONE-variable boundary and never a broken "
     "instrument — a gate that fails everything is a broken check, not a "
     "real fault; a negative is a claim and carries the same burden of "
     "proof as a positive one"),
    ("Gated writes", "--execute is the ONLY flag that performs the "
     "trigger-scope PUT (scope_applier's OWN CLI); every other "
     "invocation is a read-only dry-run that prints exactly the PUT it "
     "WOULD send; the POST-PUT read-back must prove the fix byte-for-"
     "byte (AF-AE-READBACK-MISMATCH); a rail rejection STOPS "
     "(AF-AE-TRIGGER-SCOPE-VALIDATION) and never writes"),
    ("Move in silence", "operator-verbose only; NOTHING Anthropic in any "
     "runtime file; Convert and Flow naming in every client surface; "
     "STDLIB ONLY; calls NO model; never a client PII; READ-ONLY by "
     "doctrine — the checkers never write; scope_applier is the ONE "
     "gated write surface"),
)

# ---------------------------------------------------------------------------
# CREDENTIAL LABELS — BY LABEL ONLY. These are the label NAMES the tooling
# resolves through anthology_registry (live process env first, then the
# three canonical client env stores). A label is a name, never a value; the
# values they resolve to are never held here and never printed anywhere.
# The U05 fixtures hold NO credential surface at all (pure in-memory
# metadata over synthetic ids); the family's live surfaces — the
# workflow_reader rail read and the scope_applier rail apply — resolve
# their credentials through the house labels below.
# ---------------------------------------------------------------------------
CREDENTIAL_LABELS = {
    "pit": (
        "CONVERT_AND_FLOW_PIT",
        "CONVERT_AND_FLOW_API_KEY",
        "GOHIGHLEVEL_API_KEY",
        "GOHIGHLEVEL_PIT",
        "GHL_API_KEY",
    ),
    "rail": (
        "ANTHOLOGY_GHL_FIREBASE_REFRESH_TOKEN",
        "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN",
        "GHL_FIREBASE_REFRESH_TOKEN",
    ),
}

# Pinned counts (the fixture-counting discipline of golden_fields.py: a
# drifted inventory is drift, never tolerated). Adding a module to the U05
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
    """The U05 tooling README, rendered from the structured data above.

    One markdown document: what the tooling is, the four verified items,
    the module inventory, the house exit codes, the autofail family, the
    doctrine, and the credential labels. Because every section renders from
    the same constants the self-test asserts, a drift in the data FAILS the
    self-test before it can ship a stale README."""
    lines = [
        "# U05 tooling — scoped-read and filter-scope law gates (README)",
        "",
        "Shipped under the ENGINE-MANIFEST.json row-54 \"template live "
        "verify (U02)\" shipping doctrine (%s; the U05 family's OWN manifest "
        "row is PENDING — not yet stamped, staged under the "
        "manifest-pending/u02.json · u03.json · u04.json pattern) — the "
        "U05 verifier stays the family's single driver (the delivery_"
        "report.py row-12 sibling-helper pattern) plus the importable "
        "scope gate, the golden + attack fixtures, the negative verifier, "
        "the gated scope applier, and the live workflow reader in "
        "`scripts/u05_modules/` — documented machine-side by "
        "this module (`u05_modules.docs_u05`)."
        % U05_SHIPPING_VERSION,
        "",
        "The U05 family gates the SCOPED-READ and FILTER-SCOPE LAW "
        "(SPEC 7.2 / 11.3): every participant-facing read is scoped to ONE "
        "subject, never an unscoped sweep, and the U05 pipeline rule "
        "\"Form is universal-intake\" gates ONLY the universal author-"
        "intake form. The family's live surfaces are the workflow "
        "reader's rail read and the scope applier's gated apply — they "
        "run only from a session that can resolve "
        "a location-scoped credential BY LABEL (PIT first, then the "
        "internal-rail refresh token); `plan` / `dry-run` and `self-test` "
        "are OFFLINE (no token, no network). The fixtures carry SYNTHETIC "
        "ids only (ANTH_deadbeefcafebabed00d / ANTH_0beefdeadbeefdeadbeef / "
        "cnt_golden / anth_golden — never a live id); every report masks "
        "workflow / location ids to their last 4 characters and never "
        "echoes a filter beyond a reason code.",
        "",
        "## The four verified items (MASTER-SPEC U05 — the family's four "
        "gates, in the FIXED order the scope law carries them)",
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
    """The on-disk path a README inventory row claims. Every U05 row lives
    next to this module (scripts/u05_modules/)."""
    base = Path(__file__).resolve().parent
    if row.get("place", "").strip("/") == "scripts":
        base = base.parent
    return base / row["name"]

def _self_test_body(dev) -> None:
    dev.write("[docs-u05] pinning: %d verified items, %d modules, "
              "exit codes 0..5\n"
              % (CONTRACT_ITEM_COUNT, CONTRACT_MODULE_COUNT))

    items = VERIFY_ITEMS
    if len(items) != CONTRACT_ITEM_COUNT:
        raise AssertionError(
            "VERIFY_ITEMS carries %d rows, contract is %d — the U05 item "
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
            "MODULES carries %d rows, contract is %d — a U05 module was "
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
    dev.write("[docs-u05] PASS — README data and shipped tree agree "
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
        sys.stderr.write("[docs-u05] SELF-TEST FAILED "
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
        prog="docs_u05.py",
        description="U05 tooling documentation module — README, module "
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
            "verifier": U05_VERIFIER,
            "manifest_row": U05_MANIFEST_ROW,
            "shipping": U05_SHIPPING_VERSION,
            "verify_items": verify_items(),
            "modules": modules(),
            "exit_codes": exit_codes(),
            "af_codes": af_codes(),
            "doctrine": [{"name": n, "text": t} for n, t in DOCTRINE],
            "credential_labels": {k: list(v)
                                  for k, v in CREDENTIAL_LABELS.items()},
            "note": "pure data — no credential value is held or printed; "
                    "the U05 manifest row is PENDING",
        }, indent=2, sort_keys=True))
        return EX_OK
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[docs-u05] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR

if __name__ == "__main__":
    sys.exit(main())
