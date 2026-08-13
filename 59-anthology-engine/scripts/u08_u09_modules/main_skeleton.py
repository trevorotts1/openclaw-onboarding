#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u08_u09_modules/main_skeleton.py
# U08/U09 FORM-LAW DISPATCHER — the offline-plan / offline-self-test / live
# verify driver for the U08/U09 form-and-dropdown law family under
# scripts/u08_u09_modules/ (the FAIL-CLOSED FORM-SURFACE LAW of the engine:
# the three named forms of the snapshot contract — universal-intake /
# universal-review / title-select — each carrying its byte-exact hidden-field
# contract, its exact visible field law, and its exact SINGLE_OPTIONS
# dropdown law, with every WRITE ACTION Trevor-gated by --execute per the
# package-init doctrine: "Destructive actions fail closed: any archive ACTION
# (delete / archive / remove / deactivate / revoke / unpublish) in this
# package requires the caller to pass --execute explicitly (Trevor-gated).
# Without --execute the module must report what it WOULD do and exit without
# mutating."). It imports the check modules BY NAME (importlib, never exec'd
# from a path), enforces the fail-closed one-entry-point contract, and
# resolves the aggregate exit code exactly as its U02 / U03 / U04 / U05 /
# U06 / U07 siblings (u02_modules/main_skeleton.py, u03_modules/main_skeleton.py,
# u04_modules/main_skeleton.py, u05_modules/main_skeleton.py,
# u06_modules/main_skeleton.py, u07_modules/main_skeleton.py) do. It carries
# NO check logic itself: a check module is exercised ONLY through this CLI so
# `--dry-run`, `--self-test`, and the live aggregate never drift apart.
#
# THE U08/U09 FAMILY (the modules this dispatcher aggregates; each is
# STDLIB-only, ships its own OFFLINE self-test battery (exit 0 pass / 4
# enforced violation), and exposes a thin own CLI — this skeleton is the ONE
# entry-point contract over them):
#   form_spec_loader.py   the FAIL-CLOSED 3-FORM SPEC LOADER AND CONTRACT
#                         GATE — the single implementation of the
#                         anthology-snapshot-contract.json forms load-and-
#                         verify law: read the contract (the SINGLE SOURCE
#                         OF TRUTH) and return its forms surface ONLY when
#                         it satisfies its own contract (the hidden-field
#                         law [contact_id, anthology_id, stage] byte-exact
#                         on every required and contract-bound row; the
#                         universal-review slug a NAMED form, never a count
#                         row; the pinned form ids byte-equal their live
#                         authorities) — refuse anything else
#                         (FormSpecError, STOP, exit 2), never a partial
#                         load. OFFLINE, READ-ONLY, NETWORK-FREE: no
#                         credential is ever resolved or printed; a form id
#                         is reported by masked marker only
#                         (reg._mask_location), never by value.
#   hidden_field_module.py  the HIDDEN-FIELD CREATOR — create-or-verify the
#                         universal hidden-field trio (contact_id /
#                         anthology_id / stage) on the universal author-
#                         intake form through the proven public write rail
#                         PUT /forms/{id} (Version header + CAF_BROWSER_UA on
#                         the request — the Cloudflare edge fix). The write
#                         is Trevor-gated: WITHOUT --execute it is a
#                         READ-ONLY dry-run (applied false, nothing
#                         written); WITH --execute a PUT happens and the
#                         read-back must prove the trio byte-exact
#                         (AF-AE-READBACK-MISMATCH family, exit 5). A
#                         missing / unreadable listing is FORMS-NOT-FOUND /
#                         FORMS-EMPTY (exit 2); a credential-shaped value on
#                         any surface REFUSES (exit 2, never printed).
#   title_select_builder.py  the TITLE-SELECT FORM BUILDER — the S3 gate
#                         form of the three-slug family: EXACTLY TWO routing
#                         hidden fields (anthology_id, stage — never the
#                         intake trio) plus the TWO visible multi-line
#                         REQUIRED fields (title, subtitle), built through
#                         the same proven public rail PUT /forms/{id} with a
#                         read-back. Trevor-gated exactly like the
#                         hidden-field creator; a read-back that does not
#                         prove the build is a MISMATCH (exit 5), never a
#                         reported success. The build shape is self-pinned
#                         against the golden title-select fixture
#                         (golden_title: the one-required select action,
#                         the lock a PAIR, both doors).
#   universal_review_builder.py  the UNIVERSAL-REVIEW FORM BUILDER — the
#                         decision form of the family: EXACTLY TWO hidden
#                         fields (anthology_id, stage — never contact_id),
#                         the TWO-option decision dropdown (Approve as-is /
#                         Request rewrite with notes — read once from
#                         gate_engine's action vocabulary), the multi-line
#                         notes surface, and the FOUR-option cover dropdown
#                         (the U8 style names read once from
#                         cover_render.STYLE_NAMES), built through PUT
#                         /forms/{id} with a read-back. Trevor-gated; a
#                         drifted decision / cover picklist or a read-back
#                         that cannot be proven is a MISMATCH (exit 5).
#   dropdown_module.py    the TWO-DROPDOWN CREATE-OR-VERIFY MODULE — the
#                         SINGLE_OPTIONS law of the engine's review surface:
#                         the PRD Section 4 universal-review decision field
#                         (contact.anthology_review_decision, the two gate
#                         actions approve_as_is / request_rewrite_with_notes
#                         from gate_engine) and the U8 cover-choice field
#                         (contact.anthology_cover_choice, the four named
#                         styles from cover_render.STYLE_NAMES, byte-exact
#                         against config/field-map.json choice_options).
#                         verify_live(client, location_id, field_map, *,
#                         execute=False): missing keys WITHOUT --execute are
#                         a STOP (exit 2) that lists them; WITH --execute
#                         create-only-missing at SINGLE_OPTIONS with the
#                         exact picklists then re-read (a drift is exit 5).
#                         A live field of the WRONG type is never re-created
#                         and never re-typed — it is a FAIL (exit 5).
#   golden_title.py       the GOLDEN TITLE-SELECT FIXTURE — the canonical
#                         in-memory payload of the S3 title-selection surface
#                         in its GOLDEN state: the byte-exact locked pair
#                         (title AND subtitle — the lock is a PAIR, never a
#                         title-only stamp), the composite participant_key
#                         under the KEYING LAW (read once through
#                         anthology_state.participant_key), the one-way lock
#                         truth, and the fixed two doors (nudge_link /
#                         dashboard). payload(candidate=None, *, out=None)
#                         judges a select payload fail-closed (exit 0
#                         PASS / 5 REFUSED); a live selection write is
#                         Trevor-gated (--execute) — the gate lives in this
#                         dispatcher, never in a fixture.
#   golden_review.py      the GOLDEN UNIVERSAL-REVIEW FIXTURE — the
#                         canonical in-memory payload of the universal-review
#                         decision surface in its GOLDEN state: the
#                         UNIVERSAL_REVIEW_FORM slug byte-exact (read once
#                         from u05_modules.negative_verifier), the decision
#                         present and non-empty, the keys riding the
#                         field-map authority, the cover choice (when
#                         carried) ONE of the four style names, and the
#                         golden s7_cover HOLD -> certified does-not-fire.
#                         payload(candidate, *, out=None) judges a review
#                         submission fail-closed (exit 0 PASS / 5 REFUSED).
#   attack_missing_hidden.py  the U08/U09 ATTACK: a deterministic DEEP
#                         strict-subset hidden-field container carrying only
#                         TWO of the THREE universal hidden fields (the
#                         canonical trio minus its LAST contract row by
#                         position — the stage token today) that every
#                         byte-exact hidden-field gate MUST DETECT and never
#                         pass. verify_missing_hidden(client, form_id,
#                         contract, *, out=None) FAILs the 2-of-3 read with
#                         exit 5 (missing key named) while the true 3-key
#                         control (payload_true, --execute-gated) PASSES
#                         exit 0 — the pass/fail split discriminates the
#                         deep-strict-subset boundary, never a broken
#                         instrument. The attack ships ONLY with --execute
#                         (payload / payload-true are REFUSED without it).
#   docs_forms.py         the U08/U09 tooling README / catalog data +
#                         drift gate — the three named forms and their
#                         laws, the module inventory, the house exit
#                         codes, the AF family, the doctrine, and the
#                         credential labels as DATA; readme() renders FROM
#                         the same data the self-test asserts against, so
#                         documentation and data cannot drift; its
#                         self-test is a read-only filesystem drift gate —
#                         a doc that names a module that does not ship
#                         FAILS its self-test exit 4. DATA ONLY: it
#                         carries no live gate and no write surface, so
#                         the dispatcher exercises its battery in the
#                         offline self-test and its plan surface only.
#                         (The family counts 12 shipped files incl. this
#                         dispatcher, pinned by docs_forms.CONTRACT_
#                         MODULE_COUNT.)
#   attack_bad_dropdown.py  the U08/U09 ATTACK: a deterministic wrong-
#                         option decision-dropdown picklist — the PRD
#                         Section 4 universal-review decision field's two
#                         options with the FIRST byte swapped to the repo's
#                         OWN documented drifted spelling (approved_as_is,
#                         pinned byte-exact against
#                         golden_review.GOLDEN_DECISION and proven NOT in
#                         the two gate actions) that every byte-exact
#                         picklist gate MUST DETECT and never pass.
#                         verify_options(picklist, *, out=None) FAILs the
#                         wrong-option read with exit 5 (wrong option and
#                         expected option named; reordered / extra /
#                         dropped / duplicated / blank reads FAIL with
#                         their named defect) while the true two-option
#                         golden picklist control (payload_true,
#                         --execute-gated) PASSES exit 0 — the pass/fail
#                         split discriminates the one-option-wrong
#                         boundary, never a broken instrument. The attack
#                         ships ONLY with --execute.
#   prefill_verifier.py   the U08 VALUE-SIDE GATE — the minted intake
#                         link's TWO query params (?anthology_id=<minted>
#                         &stage=<stage>) must pre-fill the form's HIDDEN
#                         anthology_id AND stage fields (the U08
#                         two-hidden-field extension of the U04 G3 value-
#                         side law). The live read is the PUBLIC hosted-form
#                         page + the PUBLIC widget build — zero credentials;
#                         a real browser render is OPTIONAL (absent runtime
#                         -> rendered check SKIPPED as undetermined, never
#                         fabricated). run_live(forms_base, form_id, probe,
#                         stage_token, *, key, stage_key, baseline,
#                         allow_render, timeout, out) -> 0 PASS / 5 MISMATCH
#                         / 3 HELD / 2 STOP. --execute is REQUIRED for the
#                         live verify (u08_u09 package doctrine);
#                         plan and self-test are OFFLINE.
#
# THE IMPORT CONTRACT (the surface the family already satisfies): one ENTRY
# POINT per module, exposed as `self_test(out=None) -> int` — exit 0 on
# pass, 4 (EX_VIOLATION, the AF-AE-TEMPLATE-ATTACK family) on failure. A
# module without a battery STOPS the dispatcher (fail-closed: no check
# family is ever skipped, and a family that cannot prove itself offline
# cannot be trusted live). The live gates are driven through each module's
# OWN documented surfaces (load_command / plan_form_build / plan_review_build
# / verify_live / payload / run_live / plan_field_create / verify_missing_
# hidden), never through a re-implementation, and their STOP-family
# exceptions are classified BY NAME (FormSpecError / FormsFixError /
# FormsBuildError / ReviewBuildError / DropdownError / StyleImportError /
# DecisionImportError / FixtureError), exactly as the U02 / U03 / U04 / U05
# / U06 / U07 siblings classify theirs.
#
# CREATION IS TREVOR-GATED HERE. The dispatcher NEVER writes without
# --execute: every create-capable sibling is exercised with execute=False by
# default (its own dry-run / no-op surface), and the live aggregate STOPS
# (exit 2, AF-AE-U08-U09-NO-EXECUTE) rather than auto-authorize any write
# the operator did not gate. The gate is enforced in BOTH surfaces (the CLI
# and the aggregate) and pinned by the offline self-test: a CREATE ACTION
# without --execute is a refusal, never a silent no-op, never a silent
# create. The family's OWN gate is re-proven HERE, never assumed: each
# write-capable module's own no-execute behavior is classified verbatim by
# running its own batteries (their self-tests assert the module-level
# no-execute STOP / dry-run / fixture-refusal laws).
#
# THE LIVE READS ARE CREDENTIAL-GATED; THE TOOLING SHIPS NOW (the
# u08_u09_modules package-init doctrine; the family is staged, never a
# manifest row). The operator executes `verify` only from a session that can
# resolve the client's OWN location-scoped private-integration token BY
# LABEL. --dry-run (offline plan) and --self-test (offline, no token, no
# network) always work. The OFFLINE gates (the form-spec contract gate, the
# golden fixtures, the attack boundary) are exercised with their own golden
# surfaces and NEVER require a credential — and the aggregate still refuses
# up front without a PIT (the live reads are PIT-gated and no gate is ever
# skipped). The ONE credential-free live gate is prefill_verifier (its live
# reads ride the PUBLIC hosted-form surface, zero credentials — but it too
# is --execute-gated by the package doctrine, so it never fires inside an
# un-gated aggregate).
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. The PIT is resolved through
# anthology_registry (CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_API_KEY /
# GOHIGHLEVEL_API_KEY / GOHIGHLEVEL_PIT / GHL_API_KEY, live process env
# first then the three canonical client env stores) and the location id
# through reg.resolve_location (CONVERT_AND_FLOW_LOCATION_ID /
# GOHIGHLEVEL_LOCATION_ID / GHL_LOCATION_ID) unless --location-id
# overrides. SET / NOT SET only on every operator surface; a token value is
# NEVER printed, and the location / form ids are masked on every surface
# (reg._mask_location / fr.mask_id / the fixtures' last-4 markers — the
# house shape). The dispatcher scans its own plan and report payloads
# against the credential shape (pit-\S+) before print — a hit REFUSES the
# surface rather than echo a token.
#
# BROWSER UA: every request rides reg.CafClient, which applies
# CAF_BROWSER_UA on every request so the Cloudflare edge fronting
# services.leadconnectorhq.com never 1010s a request (CF 1010 / GK-09
# discipline — the house pattern ported byte-for-byte from the U02..U07
# families and the Podcast gate). This dispatcher asserts the law OFFLINE
# (its self-test pins the exact constant on the registry surface) so a
# drifted UA is caught before a single live request. Scope-vs-edge-block
# discrimination: a bare 401/403 is HELD (UpstreamBlockedError /
# CafUnreachable), never mislabeled as a scope problem; a genuine scope
# denial is a STOP (exit 2).
#
# AF CODES (fail-closed surfaces; self-test failures are exit 4, never 1):
#   AF-AE-U08-U09-ASSEMBLY-INCOMPLETE -> the check-module set named in
#          U08_U09_MODULES is not fully present, or a module violates the
#          one-entry-point contract. STOP (exit 2) — a check family is
#          never silently skipped.
#   AF-AE-U08-U09-NO-EXECUTE         -> a CREATE ACTION (or the live verify
#          itself) requested without --execute (the Trevor gate, package-
#          init doctrine). STOP (exit 2) — a write is never silent, and an
#          un-gated live verify never fires.
#   AF-AE-FORMSPEC-*                 -> the 3-form spec contract gate
#          refused (missing forms block / hidden-field law drift / a
#          universal-review count-row leak / a drifted pinned id). STOP
#          (exit 2, FormSpecError).
#   AF-AE-FIELDS-* / FORMS-*         -> the live form / dropdown surface is
#          empty (FORMS-EMPTY) or absent (FORMS-NOT-FOUND), or a dropdown
#          key is missing live / of the wrong type / with a drifted
#          picklist (AF-AE-FIELDS-MISSING family). exit 5 for a mismatch,
#          exit 2 for a named refusal.
#   AF-AE-READBACK-MISMATCH          -> a PUT happened but the read-back does
#          not prove the write byte-exact. exit 5 (the shared house code,
#          stamped in ENGINE-MANIFEST.json).
#   AF-AE-REVIEW-*                   -> the golden universal-review judge
#          refused (FORM-TOKEN / STAGE-CURSOR / DECISION-DRIFT). exit 5.
#   AF-AE-GOLDENTITLE-*              -> the golden title-select judge refused
#          (a blank / drifted title or subtitle, a lock not one-way, an
#          unknown door, a non-golden participant key). exit 5.
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
#   AF-AE-TEMPLATE-ATTACK            -> an attack fixture tripped the OFFLINE
#          self-test (also the family self-test batteries). exit 4.
#
# EXIT CODES (house convention 0/1/2/3/5; 4 = enforced violation only inside
# the offline self-test batteries — the operator CLI of this dispatcher
# resolves to 0 / 2 / 5 exactly, per the U08/U09 surface contract; the
# primary surface the operator consumes is 0 = PASS, 2 = STOP, 5 = mismatch):
#   0  all checks PASS (also --dry-run plan pass and self-test pass)
#   1  unexpected error
#   2  STOP refusal — a CREATE ACTION or the live verify without --execute
#      (the Trevor gate, AF-AE-U08-U09-NO-EXECUTE) / label NOT SET / usage /
#      the check-module assembly incomplete (AF-AE-U08-U09-ASSEMBLY-
#      INCOMPLETE) / a form-spec contract refusal (AF-AE-FORMSPEC-*) / a
#      module STOP-family refusal (FormSpecError / FormsFixError /
#      FormsBuildError / ReviewBuildError / DropdownError / StyleImportError
#      / DecisionImportError / FixtureError, incl. missing dropdowns listed
#      without --execute)
#   3  HELD — Convert and Flow unreachable / Cloudflare edge block (CF
#      error 1010) / a page that cannot be fetched (UNDETERMINED, never a
#      verdict)
#   4  self-test FAILED — an assertion in an OFFLINE self-test battery
#      tripped (AF-AE-TEMPLATE-ATTACK family). A tamper NEVER masquerades
#      as exit 1. (Batteries are exercised through `--self-test` and inside
#      the aggregate's gate order; an operator CLI run never returns 4.)
#   5  data or read-back mismatch (a hidden-field strict subset, a dropdown
#      of the wrong type or a drifted picklist, a drifted locked pair, a
#      foreign review token / decision / stage cursor, a read-back that does
#      not prove the build; the fail-closed default)
#
# STDLIB ONLY (urllib + json via the registry and the check modules); calls
# NO model. Reuses anthology_registry (CafClient, resolve_pit,
# resolve_location, _stop, _mask_location, CAF_BROWSER_UA). DOCTRINE: move
# in silence; NOTHING Anthropic in any runtime file (the exact house
# doctrine string, carried verbatim so the guard scan's phrase stays
# present); Convert and Flow naming in every client surface; NEVER print a
# secret value; --dry-run and --self-test are OFFLINE; a CREATE ACTION
# requires --execute (Trevor-gated) and is create-only-missing with a
# byte-exact read-back — never a silent write.
# =============================================================================
"""main_skeleton.py — U08/U09 form-law dispatcher: offline plan / offline
self-test / live verify of the three-form, hidden-field, dropdown and
value-side laws of the Anthology engine (Skill 59, u08_u09_modules; the
packaged sibling of u02_modules/main_skeleton.py,
u03_modules/main_skeleton.py, u04_modules/main_skeleton.py,
u05_modules/main_skeleton.py, u06_modules/main_skeleton.py and
u07_modules/main_skeleton.py). Every CREATE ACTION and the live verify
itself require --execute (Trevor-gated, the package-init doctrine) — this
dispatcher never mutates without the gate, and it carries no write surface
of its own."""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry does the
# Cloudflare browser-UA wiring + the LeadConnector client, and its label
# resolution is the house credential contract. The u04 form reader owns the
# public forms rail (FORMS_LIST_PATH / mask_id / FormsReadError) the
# builders ride.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "u04_modules"))
import anthology_registry as reg  # noqa: E402
import form_reader as fr  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The u08_u09_modules directory itself — sibling imports resolve from here, in
# BOTH execution contexts (as a script, whose own directory is sys.path[0],
# and as an imported module, where the caller may not have added it).
MODULES_DIR = Path(__file__).resolve().parent
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"
PREFILL_BASELINE_PATH = SKILL_DIR / "config" / "prefill-verifier-baseline.json"

# The template location pin, imported from the contract the U02..U07
# siblings use (the snapshot contract's source_template_location). The live
# reads resolve the location BY LABEL first (resolve_location) with
# --location-id as the override; this literal is the plan/report scaffold
# marker, masked on every surface.
DEFAULT_TEMPLATE_LOCATION = "2HIKGNgsixWx0yds7Qnx"

# The U08/U09 check-module inventory — the assembly manifest for this
# dispatcher. Every name is imported BY NAME below (importlib, never exec'd
# from a path); a missing module is a STOP, never a silent skip. `role` is
# the one-line contract each module owns. The names mirror the files on
# disk one-to-one (the catalog and the tree never drift; the dispatcher
# self-test pins the counts, exactly as the U03..U07 siblings pin theirs).
U08_U09_MODULES = (
    ("form_spec_loader", "the FAIL-CLOSED 3-FORM SPEC LOADER AND CONTRACT "
                         "GATE — the single implementation of the "
                         "anthology-snapshot-contract.json forms load-and-"
                         "verify law: the hidden-field law [contact_id, "
                         "anthology_id, stage] byte-exact on every required "
                         "and contract-bound row; the universal-review slug "
                         "a NAMED form, never a count row; the pinned form "
                         "ids byte-equal their live authorities — refuse "
                         "anything else (FormSpecError, STOP, exit 2), "
                         "never a partial load. OFFLINE, READ-ONLY, "
                         "NETWORK-FREE; a form id is reported by masked "
                         "marker only, never by value"),
    ("golden_title", "the GOLDEN TITLE-SELECT FIXTURE — the canonical "
                     "in-memory payload of the S3 title-selection surface "
                     "in its GOLDEN state: the byte-exact locked PAIR "
                     "(title AND subtitle, never a title-only stamp), the "
                     "composite participant_key under the KEYING LAW (read "
                     "once through anthology_state.participant_key), the "
                     "one-way lock truth, and the fixed two doors "
                     "(nudge_link / dashboard); payload(candidate=None, "
                     "*, out=None) judges a select payload fail-closed "
                     "(exit 0 PASS / 5 REFUSED); a live selection write is "
                     "Trevor-gated (--execute) — the gate lives in this "
                     "dispatcher, never in a fixture"),
    ("golden_review", "the GOLDEN UNIVERSAL-REVIEW FIXTURE — the canonical "
                      "in-memory payload of the universal-review decision "
                      "surface in its GOLDEN state: the "
                      "UNIVERSAL_REVIEW_FORM slug byte-exact (read once "
                      "from u05_modules.negative_verifier), the decision "
                      "present and non-empty, the keys riding the field-map "
                      "authority, the cover choice (when carried) ONE of "
                      "the four style names, and the golden s7_cover HOLD "
                      "-> certified does-not-fire; payload(candidate, *, "
                      "out=None) judges a review submission fail-closed "
                      "(exit 0 PASS / 5 REFUSED)"),
    ("attack_missing_hidden", "the U08/U09 ATTACK: a deterministic DEEP "
                              "strict-subset hidden-field container "
                              "carrying only TWO of the THREE universal "
                              "hidden fields (the canonical trio minus its "
                              "LAST contract row by position — the stage "
                              "token today) that every byte-exact hidden-"
                              "field gate MUST DETECT and never pass; "
                              "verify_missing_hidden FAILs the 2-of-3 read "
                              "with exit 5 (missing key named) while the "
                              "true 3-key control (payload_true, "
                              "--execute-gated) PASSES exit 0 — the "
                              "pass/fail split discriminates the deep-"
                              "strict-subset boundary; the attack ships "
                              "ONLY with --execute"),
    ("attack_bad_dropdown", "the U08/U09 ATTACK: a deterministic wrong-"
                            "option decision-dropdown picklist — the PRD "
                            "Section 4 universal-review decision field's "
                            "two options with the FIRST byte swapped to "
                            "the repo's OWN documented drifted spelling "
                            "(approved_as_is, pinned byte-exact against "
                            "golden_review.GOLDEN_DECISION and proven NOT "
                            "in the two gate actions) that every byte-"
                            "exact picklist gate MUST DETECT and never "
                            "pass; verify_options FAILs the wrong-option "
                            "read with exit 5 (wrong option and expected "
                            "option named; reordered / extra / dropped / "
                            "duplicated / blank reads FAIL with their "
                            "named defect) while the true two-option "
                            "golden picklist control (payload_true, "
                            "--execute-gated) PASSES exit 0 — the "
                            "pass/fail split discriminates the "
                            "one-option-wrong boundary, never a broken "
                            "instrument; the attack ships ONLY with "
                            "--execute"),
    ("hidden_field_module", "the HIDDEN-FIELD CREATOR — create-or-verify "
                            "the universal hidden-field trio on the "
                            "universal author-intake form through the "
                            "proven public write rail PUT /forms/{id} "
                            "(Version header + CAF_BROWSER_UA — the "
                            "Cloudflare edge fix); the write is "
                            "Trevor-gated: WITHOUT --execute a READ-ONLY "
                            "dry-run (nothing written), WITH --execute a "
                            "PUT and a read-back that must prove the trio "
                            "byte-exact (AF-AE-READBACK-MISMATCH, exit 5); "
                            "a missing / unreadable listing is "
                            "FORMS-NOT-FOUND / FORMS-EMPTY (exit 2)"),
    ("title_select_builder", "the TITLE-SELECT FORM BUILDER — the S3 gate "
                             "form of the three-slug family: EXACTLY TWO "
                             "routing hidden fields (anthology_id, stage — "
                             "never the intake trio) plus the TWO visible "
                             "multi-line REQUIRED fields (title, subtitle), "
                             "built through the proven public rail PUT "
                             "/forms/{id} with a read-back; Trevor-gated "
                             "exactly like the hidden-field creator; a "
                             "read-back that does not prove the build is a "
                             "MISMATCH (exit 5), never a reported success"),
    ("universal_review_builder", "the UNIVERSAL-REVIEW FORM BUILDER — the "
                                 "decision form of the family: EXACTLY TWO "
                                 "hidden fields (anthology_id, stage — "
                                 "never contact_id), the TWO-option "
                                 "decision dropdown (Approve as-is / "
                                 "Request rewrite with notes — read once "
                                 "from gate_engine's action vocabulary), "
                                 "the multi-line notes surface, and the "
                                 "FOUR-option cover dropdown (the U8 style "
                                 "names read once from "
                                 "cover_render.STYLE_NAMES), built through "
                                 "PUT /forms/{id} with a read-back; "
                                 "Trevor-gated; a drifted decision / cover "
                                 "picklist or an unproven read-back is a "
                                 "MISMATCH (exit 5)"),
    ("dropdown_module", "the TWO-DROPDOWN CREATE-OR-VERIFY MODULE — the "
                        "SINGLE_OPTIONS law of the review surface: the PRD "
                        "Section 4 universal-review decision field "
                        "(contact.anthology_review_decision, the two gate "
                        "actions approve_as_is / request_rewrite_with_notes "
                        "from gate_engine) and the U8 cover-choice field "
                        "(contact.anthology_cover_choice, the four named "
                        "styles from cover_render.STYLE_NAMES, byte-exact "
                        "against config/field-map.json choice_options); "
                        "verify_live: missing keys WITHOUT --execute are a "
                        "STOP (exit 2) that lists them; WITH --execute "
                        "create-only-missing at SINGLE_OPTIONS with the "
                        "exact picklists then re-read (a drift is exit 5); "
                        "a live field of the WRONG type is never re-created "
                        "and never re-typed — it is a FAIL (exit 5)"),
    ("prefill_verifier", "the U08 VALUE-SIDE GATE — the minted intake "
                         "link's TWO query params (?anthology_id=<minted> "
                         "&stage=<stage>) must pre-fill the form's HIDDEN "
                         "anthology_id AND stage fields (the U08 "
                         "two-hidden-field extension of the U04 G3 value-"
                         "side law); the live read is the PUBLIC hosted-"
                         "form page + the PUBLIC widget build — zero "
                         "credentials; a real browser render is OPTIONAL "
                         "(absent runtime -> rendered check SKIPPED as "
                         "undetermined, never fabricated); run_live -> 0 "
                         "PASS / 5 MISMATCH / 3 HELD / 2 STOP; --execute is "
                         "REQUIRED for the live verify (u08_u09 doctrine)"),
    ("docs_forms", "the U08/U09 tooling README / catalog data + drift "
                   "gate — the three named forms and their laws, the "
                   "module inventory, the house exit codes, the AF "
                   "family, the doctrine, and the credential labels as "
                   "DATA; readme() renders FROM the same data the "
                   "self-test asserts against, so documentation and data "
                   "cannot drift; its self-test is a read-only filesystem "
                   "drift gate — a doc that names a module that does not "
                   "ship FAILS its self-test exit 4"),
)

# The live-verify gate order (FIXED, in this order) — the U08/U09 family's
# verified surfaces:
#   1. the 3-form spec contract gate (form_spec_loader load_command over the
#      committed config/anthology-snapshot-contract.json — OFFLINE, pure,
#      the hidden-field law + the pinned ids; a contract that drifted from
#      its own law is a STOP, never a blind load),
#   2. the golden title-select gate (golden_title payload over the GOLDEN
#      select payload — OFFLINE by construction; the golden selection must
#      PASS its own judge, exit 0),
#   3. the golden universal-review gate (golden_review payload over the
#      GOLDEN review payload — OFFLINE; the golden submission must PASS its
#      own judge, exit 0),
#   4. the hidden-field attack boundary (attack_missing_hidden — the 2-of-3
#      deep strict subset MUST fail the hidden-field judge (exit 5) with the
#      true 3-key control PASSING: the pass/fail split discriminates the
#      boundary, never a broken instrument),
#   5. the dropdown attack boundary (attack_bad_dropdown — the wrong-option
#      decision picklist MUST fail the byte-exact picklist judge (exit 5)
#      with the true two-option golden control PASSING: the pass/fail split
#      discriminates the one-option-wrong boundary, never a broken
#      instrument),
#   6. the dropdown law (dropdown_module verify_live over the live listing —
#      the two SINGLE_OPTIONS fields byte-exact; missing keys WITHOUT
#      --execute are a STOP, a wrong-type field or a drifted picklist is a
#      MISMATCH, exit 5),
#   7. the hidden-field creator (hidden_field_module plan_field_create — the
#      universal-intake form's hidden trio; WITHOUT --execute a READ-ONLY
#      dry-run over the live listing, WITH --execute the PUT + read-back),
#   8. the title-select builder (title_select_builder plan_form_build — the
#      S3 gate form's two routing hidden fields + the visible multi-line
#      required pair; dry-run / PUT + read-back exactly as above),
#   9. the universal-review builder (universal_review_builder
#      plan_review_build — the decision form's hidden pair + decision
#      dropdown + notes + cover dropdown; dry-run / PUT + read-back).
# The prefill_verifier value-side gate is NOT part of the default live
# aggregate (its live read is a PUBLIC page fetch, but it is still
# --execute-gated by the package doctrine; it is exercised through
# `--self-test`, its offline batteries, and its OWN CLI — never fired
# inside an un-gated aggregate).
LIVE_GATES = (
    ("form_spec_loader", "the 3-form spec contract gate — load-and-verify "
                         "config/anthology-snapshot-contract.json forms "
                         "against its own law (the hidden-field trio "
                         "byte-exact, the universal-review slug a NAMED "
                         "form, the pinned ids byte-equal their live "
                         "authorities); a contract that drifted is a STOP, "
                         "never a blind load"),
    ("golden_title", "the golden title-select gate — the golden selection "
                     "must PASS its own fail-closed judge (the byte-exact "
                     "locked PAIR, the KEYING LAW key, the one-way lock, "
                     "the fixed two doors; exit 0, never a blind pass)"),
    ("golden_review", "the golden universal-review gate — the golden "
                      "submission must PASS its own fail-closed judge (the "
                      "UNIVERSAL_REVIEW_FORM slug byte-exact, the decision "
                      "present, the keys riding the field-map, the cover "
                      "choice in the four style names, the s7_cover HOLD; "
                      "exit 0, never a blind pass)"),
    ("attack_missing_hidden", "the hidden-field attack boundary — the "
                              "2-of-3 deep strict-subset hidden-field read "
                              "MUST fail the byte-exact judge (exit 5, "
                              "missing key named) while the true 3-key "
                              "control PASSES exit 0 (the pass/fail split "
                              "discriminates the deep-strict-subset "
                              "boundary, never a broken instrument)"),
    ("attack_bad_dropdown", "the dropdown attack boundary — the "
                            "one-option-wrong decision picklist MUST fail "
                            "the byte-exact picklist judge (exit 5, wrong "
                            "option and expected option named) while the "
                            "true two-option golden control PASSES exit 0 "
                            "(the pass/fail split discriminates the "
                            "one-option-wrong boundary, never a broken "
                            "instrument)"),
    ("dropdown_module", "the two-dropdown law — the review decision field "
                        "(2 options) and the cover-choice field (4 style "
                        "names) live SINGLE_OPTIONS byte-exact (missing "
                        "keys WITHOUT --execute are a STOP that lists them; "
                        "a wrong-type field or a drifted picklist is a "
                        "MISMATCH, exit 5, never a silent pass)"),
    ("hidden_field_module", "the hidden-field creator — the universal "
                            "author-intake form's hidden trio byte-exact "
                            "(without --execute a READ-ONLY dry-run over "
                            "the live listing, nothing written; with "
                            "--execute the PUT + read-back, "
                            "AF-AE-READBACK-MISMATCH never reported as "
                            "success)"),
    ("title_select_builder", "the title-select builder — the S3 gate "
                             "form's EXACTLY TWO routing hidden fields "
                             "(anthology_id, stage) + the visible multi-"
                             "line REQUIRED pair (title, subtitle), "
                             "byte-exact (dry-run / PUT + read-back as "
                             "above)"),
    ("universal_review_builder", "the universal-review builder — the "
                                 "decision form's hidden pair (never "
                                 "contact_id), the TWO-option decision "
                                 "dropdown, the multi-line notes surface, "
                                 "and the FOUR-option cover dropdown "
                                 "(dry-run / PUT + read-back as above)"),
)

# The independent pytest batteries that ship with the family (provenance
# only: each battery's presence is asserted, its tests run under pytest).
TEST_BATTERIES = ("test_prefill.py",)


class SkeletonError(Exception):
    """A fail-closed refusal (STOP or mismatch family) raised by the skeleton
    itself — a missing check module, a module violating the entry-point
    contract, a contract section that cannot be read, or a malformed record."""


_CREDENTIAL_SHAPE = re.compile(r"pit-\S+")


def _mask_id(fid: str) -> str:
    """Mask a form / location id for every operator surface — a tenant
    identifier, not a secret, but never printed in full (house pattern,
    mirrored from the u04 form reader's mask_id and the family fixtures'
    last-4 markers)."""
    fid = (fid or "").strip()
    if len(fid) <= 8:
        return "***"
    return "%s***%s" % (fid[:4], fid[-4:])


# ---------------------------------------------------------------------------
# Check-module loader — imports the U08/U09 modules BY NAME and enforces the
# fail-closed contract: a missing module or a module that fails to expose
# its entry point is a STOP, never a silent skip.
# ---------------------------------------------------------------------------
def load_modules():
    """Import every U08_U09_MODULES module. Returns {name: module}.

    Fail-closed: a module that does not exist raises SkeletonError (STOP) so
    the aggregate NEVER passes with a check family silently absent.
    `importlib` is the only import surface — nothing is ever exec'd from a
    path. Each module's `self_test(out=None) -> int` battery is REQUIRED
    (checked here, not deferred to the self-test run)."""
    import importlib

    modules = {}
    missing = []
    for name, _role in U08_U09_MODULES:
        try:
            mod = importlib.import_module(name)
        except ImportError:
            missing.append(name)
            continue
        modules[name] = mod
    if missing:
        raise SkeletonError(
            "u08_u09_modules file(s) not found: %s — the U08/U09 assembly is "
            "incomplete (fail-closed: no check family is ever skipped)"
            % ", ".join(missing))
    for name, mod in modules.items():
        st = getattr(mod, "self_test", None)
        if not callable(st):
            raise SkeletonError(
                "u08_u09_modules module %s does not expose 'self_test' — every "
                "check module must prove itself offline" % name)
    return modules


# ---------------------------------------------------------------------------
# Offline self-test — run EVERY module's own battery (golden PASS / attack
# FAIL), plus this dispatcher's own assembly and house-law assertions. NO
# network, NO credentials. Exit 4 on any failure (AF-AE-TEMPLATE-ATTACK
# family) — a tamper NEVER masquerades as exit 1.
# ---------------------------------------------------------------------------
def self_test(modules, out=None) -> int:
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        # 1. the assembly is complete: exactly the U08/U09 check-module set
        #    exists (the dispatcher and the empty package init are the
        #    assembly container, not dispatched modules).
        on_disk = sorted(p.name[:-3] for p in MODULES_DIR.glob("*.py")
                         if p.name not in ("__init__.py", "main_skeleton.py")
                         and not p.name.startswith("test_"))
        expected = sorted(name for name, _ in U08_U09_MODULES)
        assert on_disk == expected, (
            "u08_u09_modules tree drifted: disk carries %s, the %d-module "
            "assembly contract names %s" % (", ".join(on_disk), len(expected),
                                            ", ".join(expected)))
        for battery in TEST_BATTERIES:
            assert (MODULES_DIR / battery).is_file(), _battery_exc(battery)
        # 2. every module's own battery passes (golden PASS / attack FAIL).
        for name, mod in modules.items():
            try:
                rc = mod.self_test(out=dev)
            except TypeError:
                rc = mod.self_test()
            if rc != EX_OK:
                raise AssertionError("%s self_test returned exit %d" % (name, rc))
        # 3. the house exit-code law is the manifest convention
        #    (0/1/2/3/4/5): the skeleton's constants never drifted from the
        #    registry's, which the manifest pins.
        assert (EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH) == (0, 1, 2, 3, 5), \
            "house exit-code law drifted: registry constants are not 0/1/2/3/5"
        assert EX_VIOLATION == 4, "house exit-code law drifted: EX_VIOLATION is not 4"
        # 4. BROWSER UA LAW (CF 1010 / GK-09): the CAF_BROWSER_UA constant is
        #    a well-formed browser UA (never urllib's "Python-urllib/x.y"
        #    default, which the Cloudflare edge fronting the Convert and Flow
        #    / internal-rail hosts 403s as error 1010 before the request is
        #    ever scope-checked).
        ua = reg.CAF_BROWSER_UA
        assert isinstance(ua, str) and ua.strip(), "CAF_BROWSER_UA is empty"
        assert "Python-urllib" not in ua, \
            "CAF_BROWSER_UA is urllib's default — the Cloudflare edge 1010s it"
        assert ua.startswith("Mozilla/5.0") and "Chrome/" in ua, \
            "CAF_BROWSER_UA is not a well-formed browser UA"
        # 5. THE CREATE GATE LAW — the heart of the U08/U09 family: the
        #    package-init doctrine pins --execute as the ONLY gate for every
        #    write, and the family's own batteries prove it OFFLINE (the
        #    builders' self-tests assert the module-level no-execute
        #    dry-run / refusal laws; attack_missing_hidden's self-test
        #    asserts its fixtures ship ONLY with --execute) — and the gate
        #    flag itself is never a silent write: a CREATE ACTION without
        #    --execute is refused here (the CLI surface) with a typed
        #    reason, exit 2.
        assert _create_gate(modules) == EX_OK, \
            "the dispatcher create gate must pass its own offline law"
        # 6. CREDENTIAL LAW: the PIT labels are the house standard set and
        #    resolve to SET / NOT SET only — never a printed value. The
        #    resolver refuses a non-pit- value (a placeholder or a mis-set
        #    value must not silently ride as a token).
        assert tuple(reg.PIT_LABELS) == (
            "CONVERT_AND_FLOW_PIT", "CONVERT_AND_FLOW_API_KEY",
            "GOHIGHLEVEL_API_KEY", "GOHIGHLEVEL_PIT", "GHL_API_KEY"), \
            "PIT label set drifted from the house credential law"
        _label, token = reg.resolve_pit()
        assert token is None or str(token).startswith("pit-"), \
            "resolve_pit returned a non-pit- token (would be refused)"
        # 7. NEVER-A-TOKEN LAW on the skeleton's OWN surfaces: the plan
        #    payload (the same builder the --dry-run prints) and the report
        #    scaffold carry labels and SET / NOT SET states only — a
        #    credential-shaped string (pit- followed by a value) can never
        #    leak through them.
        contract = _read_json(CONTRACT_PATH,
                              "config/anthology-snapshot-contract.json")
        plan_blob = json.dumps(_build_plan(modules, DEFAULT_TEMPLATE_LOCATION,
                                           contract),
                               indent=2, sort_keys=True)
        assert not _CREDENTIAL_SHAPE.search(plan_blob), \
            "the plan surface must never carry a credential-shaped string"
        report_blob = json.dumps(_build_report(modules), indent=2, sort_keys=True)
        assert not _CREDENTIAL_SHAPE.search(report_blob), \
            "the report surface must never carry a credential-shaped string"
    except AssertionError as exc:
        sys.stderr.write("[main-skeleton] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    except SkeletonError as exc:
        sys.stderr.write("[main-skeleton] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    out.write("[main-skeleton] U08/U09 self-test: OK (%d modules imported, "
              "every module battery + assembly assertions + exit-code law + "
              "browser-UA law + create-gate law + credential law pass)\n"
              % len(modules))
    return EX_OK


def _battery_exc(battery: str) -> str:
    """The one-line failure note for a missing battery — a pytest battery is
    provenance (its tests run under pytest), never a dispatched module."""
    return "the U08/U09 pytest battery %s is missing from u08_u09_modules/" % battery


# ---------------------------------------------------------------------------
# The Trevor gate — the CREATE ACTION law, enforced by this dispatcher in
# BOTH surfaces (the CLI and the aggregate). Fail-closed and pure: the
# family's own no-execute laws are re-proven here, never assumed.
# ---------------------------------------------------------------------------
def _create_gate(modules, out=None) -> int:
    """The CREATE ACTION law, offline and pure. A CREATE ACTION without
    --execute is a STOP (exit 2, AF-AE-U08-U09-NO-EXECUTE) — creation is
    never silent. The law is proven OFFLINE with the family's own batteries:
    every write-capable module's self-test asserts its module-level
    no-execute behavior (the builders' read-only dry-runs, the attack
    fixture's --execute-only shipping), so the gate is certified by the same
    batteries the self-test runs — and the dispatcher's OWN CLI surface
    refuses `apply` without --execute verbatim (proven here: the gate is
    enforced in BOTH surfaces, exactly the U06 sibling's two-surface law)."""
    out = out or sys.stderr
    # 1. the dispatcher's OWN CLI surface refuses `apply` without --execute
    #    (the Trevor gate) — the two-surface law, proven here offline (this
    #    probe never touches a credential or the network: the refusal holds
    #    before any resolution work).
    try:
        rc = main(["apply", "--location-id", "loc_fx"])
    except SystemExit as exc:
        if exc.code not in (EX_STOP, 2):
            raise SkeletonError(
                "the dispatcher's own 'apply' CLI exited %r during the "
                "no-execute probe (the Trevor gate cannot be proven)"
                % (exc.code,))
        return EX_OK
    if rc != EX_STOP:
        raise SkeletonError(
            "the dispatcher's own 'apply' CLI without --execute returned "
            "exit %d, want %d (AF-AE-U08-U09-NO-EXECUTE — the Trevor gate "
            "drifted; a CREATE ACTION without the gate must STOP)"
            % (rc, EX_STOP))
    # 2. the family batteries prove the module-level no-execute laws (the
    #    builders' dry-run / the attack's --execute-only fixtures) — those
    #    batteries ran in step 2 of the self-test; the assertions they pin
    #    are re-confirmed here by re-running them and demanding exit 0.
    for name in ("hidden_field_module", "title_select_builder",
                 "universal_review_builder", "dropdown_module",
                 "attack_missing_hidden", "attack_bad_dropdown"):
        mod = modules[name]
        try:
            rc = mod.self_test(out=out)
        except TypeError:
            rc = mod.self_test()
        if rc != EX_OK:
            raise SkeletonError(
                "the %s battery FAILED during the create-gate proof "
                "(exit %d) — the no-execute law cannot be certified"
                % (name, rc))
    return EX_OK


# ---------------------------------------------------------------------------
# Offline plan — no network, no credentials. The U08/U09 dispatch law with
# the exact sources of truth, printed as ONE JSON object on stdout; human
# notes go to stderr. Each module's own plan surface (where it ships one) is
# collected by name; a module plan that cannot be produced is recorded as
# an error, never fabricated. The payload is scanned against the credential
# shape before print — a hit REFUSES the surface rather than echo a token.
# ---------------------------------------------------------------------------
def _module_plan(modules, name, location_id, contract):
    """One module's plan record. Uses the module's OWN plan surface when it
    ships one; otherwise derives the offline law from the module's
    documented constants / functions. A module plan is never fatal — an
    error is recorded, never a fabricated law."""
    mod = modules[name]
    try:
        if name == "form_spec_loader":
            return {
                "load": "config/anthology-snapshot-contract.json (the "
                        "SINGLE SOURCE OF TRUTH) — the fail-closed contract "
                        "gate: the forms block with the hidden-field law "
                        "[contact_id, anthology_id, stage] byte-exact on "
                        "every required and contract-bound row, the "
                        "universal-review slug a NAMED form, the pinned "
                        "form ids byte-equal their live authorities",
                "hidden_law": "contact_id / anthology_id / stage",
                "note": "offline plan only — no network, no credential "
                        "needed; a contract that drifted from its own law "
                        "is a STOP (exit 2), never a blind load",
            }
        if name == "golden_title":
            return {
                "fixture": "the GOLDEN TITLE-SELECT fixture — the "
                           "byte-exact locked PAIR ('The Ledger Cannot Say' "
                           "/ 'A Chapter in Two Books'), the composite "
                           "participant_key under the KEYING LAW, the "
                           "one-way lock, the fixed doors nudge_link / "
                           "dashboard",
                "judge": "payload(candidate=None) — the golden selection "
                         "itself judged offline, exit 0 PASS / 5 REFUSED",
                "write_gate": "a live selection write is Trevor-gated "
                              "(--execute) — the gate lives in this "
                              "dispatcher, never in a fixture",
                "note": "offline plan only — synthetic fixture ids, no "
                        "network, no credential needed",
            }
        if name == "golden_review":
            return {
                "fixture": "the GOLDEN UNIVERSAL-REVIEW fixture — the "
                           "universal-review decision submission in its "
                           "GOLDEN state (slug byte-exact, decision "
                           "approved_as_is, stage s7_cover HOLD -> "
                           "certified does-not-fire)",
                "judge": "payload(candidate) — fail-closed, exit 0 PASS / "
                         "5 REFUSED",
                "write_gate": "a live submission write is Trevor-gated "
                              "(--execute) — the gate lives in this "
                              "dispatcher, never in a fixture",
                "note": "offline plan only — synthetic fixture ids, no "
                        "network, no credential needed",
            }
        if name == "attack_missing_hidden":
            return {
                "attack": "the 2-of-3 deep strict-subset hidden-field "
                          "container (the universal trio minus its LAST "
                          "contract row — the stage token) that every "
                          "byte-exact hidden-field gate MUST DETECT and "
                          "refuse (exit 5, missing key named)",
                "control": "the true 3-key golden container PASSES exit 0 "
                           "(payload_true — the pass/fail split "
                           "discriminates the deep-strict-subset "
                           "boundary, never a broken instrument)",
                "ship_gate": "the attack ships ONLY with --execute (the "
                             "Trevor gate) — payload / payload-true are "
                             "REFUSED without it",
                "note": "offline attack fixture — no network, no "
                        "credential needed; synthetic values only",
            }
        if name == "attack_bad_dropdown":
            return {
                "attack": "the one-option-wrong decision-dropdown picklist "
                          "(the FIRST of the two gate actions swapped to "
                          "the repo's OWN documented drifted spelling "
                          "approved_as_is — pinned byte-exact against "
                          "golden_review.GOLDEN_DECISION, never invented) "
                          "that every byte-exact picklist gate MUST FAIL, "
                          "never a pass",
                "control": "the true two-option golden picklist PASSES "
                           "exit 0 (payload_true — the pass/fail split "
                           "discriminates the one-option-wrong boundary, "
                           "never a broken instrument)",
                "ship_gate": "the attack ships ONLY with --execute (the "
                             "Trevor gate) — payload / payload-true are "
                             "REFUSED without it",
                "note": "offline attack fixture — no network, no "
                        "credential needed; the law is read once from "
                        "dropdown_module (itself byte-derived from "
                        "gate_engine), never a hardcoded list",
            }
        if name == "hidden_field_module":
            return {
                "write": "public v2 PUT /forms/{id} (Version %s; "
                         "CAF_BROWSER_UA on the request — CF 1010 law) — "
                         "the universal author-intake form's hidden trio "
                         "(contact_id / anthology_id / stage) byte-exact; "
                         "REFUSED without --execute"
                         % reg.CAF_VERSION_HEADER,
                "read": "public v2 GET %s?locationId=<loc> (Version %s; "
                        "CAF_BROWSER_UA — CF 1010 law)"
                        % (fr.FORMS_LIST_PATH, reg.CAF_VERSION_HEADER),
                "create_gate": "without --execute a READ-ONLY dry-run "
                               "(applied false, nothing written); with it, "
                               "a PUT + read-back that must prove the trio "
                               "byte-exact (AF-AE-READBACK-MISMATCH, "
                               "exit 5); FORMS-NOT-FOUND / FORMS-EMPTY "
                               "(exit 2)",
                "note": "offline plan only — no network, no credential "
                        "needed; a credential-shaped value on any surface "
                        "REFUSES (exit 2, never printed)",
            }
        if name == "title_select_builder":
            return {
                "shape": "EXACTLY TWO routing hidden fields (anthology_id, "
                         "stage — never the intake trio) + the TWO visible "
                         "multi-line REQUIRED fields (title, subtitle), "
                         "byte-exact (self-pinned against the golden "
                         "title-select fixture)",
                "write": "public v2 PUT /forms/{id} (Version %s; "
                         "CAF_BROWSER_UA — CF 1010 law) — REFUSED without "
                         "--execute" % reg.CAF_VERSION_HEADER,
                "read": "public v2 GET %s?locationId=<loc> (Version %s; "
                        "CAF_BROWSER_UA — CF 1010 law)"
                        % (fr.FORMS_LIST_PATH, reg.CAF_VERSION_HEADER),
                "create_gate": "without --execute a READ-ONLY dry-run; "
                               "with it, a PUT + read-back that must prove "
                               "the build byte-exact (a drift is exit 5, "
                               "never a reported success)",
                "note": "offline plan only — no network, no credential "
                        "needed; the intake trio NEVER satisfies the "
                        "two-hidden shape",
            }
        if name == "universal_review_builder":
            return {
                "shape": "EXACTLY TWO hidden fields (anthology_id, stage — "
                         "never contact_id), the TWO-option decision "
                         "dropdown (Approve as-is / Request rewrite with "
                         "notes), the multi-line notes surface, and the "
                         "FOUR-option cover dropdown (the U8 style names "
                         "from cover_render.STYLE_NAMES)",
                "write": "public v2 PUT /forms/{id} (Version %s; "
                         "CAF_BROWSER_UA — CF 1010 law) — REFUSED without "
                         "--execute" % reg.CAF_VERSION_HEADER,
                "read": "public v2 GET %s?locationId=<loc> (Version %s; "
                        "CAF_BROWSER_UA — CF 1010 law)"
                        % (fr.FORMS_LIST_PATH, reg.CAF_VERSION_HEADER),
                "create_gate": "without --execute a READ-ONLY dry-run; "
                               "with it, a PUT + read-back that must prove "
                               "the build byte-exact (a drifted decision / "
                               "cover picklist or an unproven read-back is "
                               "exit 5)",
                "note": "offline plan only — no network, no credential "
                        "needed",
            }
        if name == "dropdown_module":
            return {
                "dropdowns": "the PRD Section 4 universal-review decision "
                             "field (contact.anthology_review_decision — "
                             "the two gate actions approve_as_is / "
                             "request_rewrite_with_notes from gate_engine) "
                             "and the U8 cover-choice field "
                             "(contact.anthology_cover_choice — the four "
                             "named styles from cover_render.STYLE_NAMES, "
                             "byte-exact against config/field-map.json "
                             "choice_options)",
                "create_gate": "missing keys WITHOUT --execute are a STOP "
                               "(exit 2) that lists them; WITH --execute "
                               "create-only-missing at SINGLE_OPTIONS with "
                               "the exact picklists then re-read (a drift "
                               "is exit 5); a live field of the WRONG type "
                               "is never re-created and never re-typed — it "
                               "is a FAIL (exit 5)",
                "note": "offline plan only — no network, no credential "
                        "needed; read once from config/field-map.json "
                        "(the SINGLE SOURCE OF TRUTH), never a hardcoded "
                        "list",
            }
        if name == "prefill_verifier":
            return {
                "value_law": "the minted intake link's TWO query params "
                             "(?anthology_id=<minted>&stage=<stage>) must "
                             "pre-fill the form's HIDDEN anthology_id AND "
                             "stage fields (the U08 two-hidden-field "
                             "extension of the U04 G3 value-side law)",
                "live_surface": "the PUBLIC hosted-form page + the PUBLIC "
                                "widget build — zero credentials; a real "
                                "browser render is OPTIONAL (absent runtime "
                                "-> rendered check SKIPPED as "
                                "undetermined, never fabricated)",
                "execute_gate": "--execute is REQUIRED for the live verify "
                                "(u08_u09 package doctrine); plan and "
                                "self-test are OFFLINE",
                "note": "offline plan only — no fetch, no credential "
                        "needed; a page that cannot be fetched is HELD "
                        "(exit 3), never judged; this gate is NOT part of "
                        "the default live aggregate (it never fires inside "
                        "an un-gated run)",
            }
        if name == "docs_forms":
            return {
                "catalog": "the U08/U09 tooling README / catalog data — "
                           "the three named forms and their laws, the "
                           "module inventory (%d rows incl. this "
                           "dispatcher), the house exit codes, the AF "
                           "family, the doctrine, and the credential "
                           "labels as DATA" % len(mod.MODULES),
                "drift_gate": "readme() renders FROM the same data the "
                              "self-test asserts against; a doc that names "
                              "a module that does not ship FAILS its "
                              "self-test exit 4",
                "note": "offline documentation data — no network, no "
                        "credential needed; form ids by masked marker "
                        "only, never by value",
            }
        return {"note": "no plan surface for %s" % name}
    except Exception as exc:  # noqa: BLE001 — a plan is never fatal
        return {"error": "%s: %s" % (type(exc).__name__, exc)}


def _build_plan(modules, location_id: str, contract: dict) -> dict:
    """The ONE offline plan payload (shared by --dry-run and the self-test's
    never-a-token scan, so the two can never drift)."""
    plans = {}
    for name, _role in U08_U09_MODULES:
        plans[name] = _module_plan(modules, name, location_id, contract)
    return {
        "contract": "anthology-engine-u08-u09-dispatch-plan",
        "schema_version": 1,
        "template_location_id": location_id,
        "template_location_id_masked": _mask_id(location_id),
        "gates": [name for name, _ in LIVE_GATES],
        "modules": [name for name, _ in U08_U09_MODULES],
        "plans": plans,
        "create_gate": "every CREATE ACTION (and the live verify itself) "
                       "requires --execute (Trevor-gated, the u08_u09 "
                       "package-init doctrine); without --execute a write "
                       "is REFUSED (exit 2, AF-AE-U08-U09-NO-EXECUTE) — "
                       "never a silent no-op, never a silent create; even "
                       "WITH --execute every write is create-only-missing "
                       "with a byte-exact read-back",
        "dry_run": True,
        "note": "offline plan only — no network, no credential needed; the "
                "live form reads ride the public v2 rail with CAF_BROWSER_UA "
                "on every request — CF 1010 law",
    }


def plan(modules, location_id: str, contract: dict, out=None) -> int:
    out = out or sys.stderr
    payload = _build_plan(modules, location_id, contract)
    dumped = json.dumps(payload, indent=2, sort_keys=True)
    if _CREDENTIAL_SHAPE.search(dumped):
        raise SkeletonError(
            "plan payload carries a credential-shaped string — REFUSED "
            "without printing it")
    print(dumped)
    return EX_OK


def _build_report(modules) -> dict:
    """The empty report scaffold (labels and states only — the never-a-token
    law is pinned on this exact surface in the self-test)."""
    return {
        "contract": "anthology-engine-u08-u09-verify",
        "schema_version": 1,
        "template_location_id": DEFAULT_TEMPLATE_LOCATION,
        "template_location_id_masked": _mask_id(DEFAULT_TEMPLATE_LOCATION),
        "pit_label": ("SET" if reg.resolve_pit()[1]
                      else "NOT SET"),
        "checks": {},
        "delta": [],
        "fail_closed": True,
    }


# ---------------------------------------------------------------------------
# Live verify — fail-closed aggregate over the fixed gate order. Any FAIL ->
# exit 5; a STOP-family refusal propagates as exit 2; a transport / edge
# failure is HELD (exit 3), never mislabeled as scope. The form-spec
# contract gate runs FIRST (its golden surface needs no credential), the
# golden + attack fixtures are OFFLINE by construction, then the PIT-gated
# live reads. The CREATE ACTION is never a gate: it is the family's gated
# ACTION surface, refused without --execute (the Trevor gate) and
# create-only-missing with a byte-exact read-back even with it — this
# dispatcher never mutates.
# ---------------------------------------------------------------------------
def _stop_classes(mod):
    """The STOP-family exception classes a module may raise, resolved BY
    NAME so a module that stops defining one fails the self-test, not the
    live path."""
    return tuple(cls for cname in ("FormSpecError", "FormsFixError",
                                   "FormsBuildError", "ReviewBuildError",
                                   "DropdownError", "StyleImportError",
                                   "DecisionImportError", "FixtureError",
                                   "FormsReadError")
                 if isinstance(cls := getattr(mod, cname, None), type)
                 and issubclass(cls, Exception))


def _pit_client(out):
    """Resolve the LeadConnector client for the live reads, BY LABEL,
    exactly as the u08_u09 modules' own CLIs resolve it: the client's OWN
    location-scoped private-integration token (pit- prefix validated so a
    placeholder is refused). NEVER prints a value; a missing credential is
    a STOP (the caller returns it)."""
    pit_label, token = reg.resolve_pit()
    if token:
        return reg.CafClient(token), None
    reg._stop(out,
              "No Convert and Flow private-integration token is SET.",
              ["Checked (in order): %s — all NOT SET."
               % ", ".join(reg.PIT_LABELS),
               "The U08/U09 live reads (hidden_field_module / "
               "title_select_builder / universal_review_builder / "
               "dropdown_module) ride the client's OWN pit- token with "
               "CAF_BROWSER_UA on every request — CF 1010 law; set the "
               "client's OWN location-scoped token and re-run."])
    return None, EX_STOP


def _capture_sibling(out, call):
    """Run a sibling module surface that prints its OWN gate document to
    stdout by contract, capturing that stdout into the human channel so the
    dispatcher's stdout stays exactly its ONE JSON report object (the u04
    skeleton's plan-capture pattern, applied to the live gates). Returns
    the call's return value."""
    import contextlib as _contextlib
    cap = io.StringIO()
    with _contextlib.redirect_stdout(cap):
        rc = call()
    if cap.getvalue().strip():
        out.write(cap.getvalue())
    return rc


def verify_live(modules, location_id: str, contract: dict, field_map: dict, *,
                execute: bool = False, out=None) -> int:
    out = out or sys.stderr
    masked = _mask_id(location_id)
    report = _build_report(modules)
    report["template_location_id_masked"] = masked

    def _run(name, mod):
        try:
            if name == "form_spec_loader":
                # OFFLINE: the fail-closed 3-form spec contract gate — the
                # load-and-verify law over the committed config copy (the
                # SINGLE SOURCE OF TRUTH). A contract that drifted from its
                # own law is a STOP (FormSpecError), never a blind load.
                result = _capture_sibling(
                    out, lambda: mod.load_command(CONTRACT_PATH,
                                                  out=io.StringIO()))
                if result == EX_OK:
                    return ("PASS",
                            "anthology-snapshot-contract.json forms loaded "
                            "and verified against their own law (the "
                            "hidden-field trio byte-exact, the "
                            "universal-review slug a named form, the "
                            "pinned ids byte-equal their authorities)",
                            {"spec": 3}, {"spec": 3}), None
                return ("FAIL",
                        "the 3-form spec contract gate returned exit %d — "
                        "the contract drifted from its own law" % result,
                        {"spec": 3}, {"spec": "?"}), None
            if name == "golden_title":
                # OFFLINE: the golden title-select gate — the golden
                # selection must PASS its own fail-closed judge (exit 0).
                result = _capture_sibling(
                    out, lambda: mod.payload(None, out=io.StringIO()))
                if result == EX_OK:
                    return ("PASS",
                            "the golden title-select selection passes its "
                            "own fail-closed judge — the byte-exact locked "
                            "pair under the KEYING LAW, the one-way lock, "
                            "the fixed two doors",
                            {"golden": True},
                            {"golden": True}), None
                return ("FAIL",
                        "the golden title-select judge returned exit %d — "
                        "the golden fixture drifted (AF-AE-GOLDENTITLE-*)"
                        % result,
                        {"golden": True},
                        {"golden": False}), None
            if name == "golden_review":
                # OFFLINE: the golden universal-review gate — the golden
                # submission must PASS its own fail-closed judge (exit 0).
                result = _capture_sibling(
                    out, lambda: mod.payload(mod.golden_review_payload(),
                                             out=io.StringIO()))
                if result == EX_OK:
                    return ("PASS",
                            "the golden universal-review submission passes "
                            "its own fail-closed judge — the review slug "
                            "byte-exact, the decision present, the keys "
                            "riding the field-map, the s7_cover HOLD "
                            "certified does-not-fire",
                            {"golden": True},
                            {"golden": True}), None
                return ("FAIL",
                        "the golden universal-review judge returned exit "
                        "%d — the golden fixture drifted (AF-AE-REVIEW-*)"
                        % result,
                        {"golden": True},
                        {"golden": False}), None
            if name == "attack_missing_hidden":
                # OFFLINE: the hidden-field attack boundary — the 2-of-3
                # deep strict subset MUST fail the byte-exact judge (exit
                # 5, missing key named) while the true 3-key control PASSES
                # exit 0. The judge is READ-ONLY and OFFLINE by construction
                # (the surface is the in-memory ATTACK_HIDDEN_FIELDS
                # fixture, never a network call).
                result = _capture_sibling(
                    out, lambda: mod.verify_missing_hidden(
                        mod._FixtureReader(), "form_piped_fx", contract,
                        out=io.StringIO()))
                if result == EX_MISMATCH:
                    control = _capture_sibling(
                        out, lambda: mod.payload_true(contract=contract,
                                                      execute=True,
                                                      out=io.StringIO()))
                    if control == EX_OK:
                        return ("PASS",
                                "the 2-of-3 deep strict-subset hidden-field "
                                "read is DETECTED and refused (exit 5, "
                                "missing key named) with the true 3-key "
                                "control PASSING exit 0 — the pass/fail "
                                "split discriminates the deep-strict-subset "
                                "boundary",
                                {"attack_refused": True},
                                {"attack_refused": True,
                                 "control": "PASS"}), None
                    return ("FAIL",
                            "the attack judge refused the 2-of-3 read "
                            "(exit 5) but the true 3-key control did NOT "
                            "pass (exit %d) — a broken instrument is never "
                            "a real discrimination" % control,
                            {"attack_refused": True},
                            {"attack_refused": True,
                             "control": "FAIL"}), None
                if result == EX_OK:
                    return ("FAIL",
                            "the 2-of-3 attack hidden-field read was "
                            "ACCEPTED (exit 0) — a deep strict subset "
                            "passed the byte-exact hidden-field judge; the "
                            "attack boundary drifted",
                            {"attack_refused": True},
                            {"attack_refused": False}), None
                return ("FAIL",
                        "the hidden-field attack judge returned exit %d — "
                        "the U08/U09 attack fixture drifted" % result,
                        {"attack_refused": True},
                        {"attack_refused": None}), None
            if name == "attack_bad_dropdown":
                # OFFLINE: the dropdown attack boundary — the
                # one-option-wrong decision picklist MUST fail the
                # byte-exact picklist judge (exit 5, wrong option and
                # expected option named) while the true two-option golden
                # control PASSES exit 0. The judge is READ-ONLY and OFFLINE
                # by construction (the surface is the in-memory attack
                # picklist, never a network call).
                result = _capture_sibling(
                    out, lambda: mod.verify_options(list(mod.ATTACK_OPTIONS),
                                                    out=io.StringIO()))
                if result == EX_MISMATCH:
                    control = _capture_sibling(
                        out, lambda: mod.payload_true(execute=True,
                                                      out=io.StringIO()))
                    if control == EX_OK:
                        return ("PASS",
                                "the one-option-wrong decision picklist is "
                                "DETECTED and refused (exit 5, wrong option "
                                "and expected option named) with the true "
                                "two-option golden control PASSING exit 0 "
                                "— the pass/fail split discriminates the "
                                "one-option-wrong boundary",
                                {"attack_refused": True},
                                {"attack_refused": True,
                                 "control": "PASS"}), None
                    return ("FAIL",
                            "the picklist attack judge refused the "
                            "wrong-option read (exit 5) but the golden "
                            "two-option control did NOT pass (exit %d) — "
                            "a broken instrument is never a real "
                            "discrimination" % control,
                            {"attack_refused": True},
                            {"attack_refused": True,
                             "control": "FAIL"}), None
                if result == EX_OK:
                    return ("FAIL",
                            "the one-option-wrong attack picklist was "
                            "ACCEPTED (exit 0) — a drifted decision option "
                            "passed the byte-exact picklist judge; the "
                            "attack boundary drifted",
                            {"attack_refused": True},
                            {"attack_refused": False}), None
                return ("FAIL",
                        "the dropdown attack judge returned exit %d — the "
                        "U08/U09 attack fixture drifted" % result,
                        {"attack_refused": True},
                        {"attack_refused": None}), None
            if name == "dropdown_module":
                # The two-dropdown law over the live listing: the review
                # decision field (2 options) and the cover-choice field (4
                # style names) live SINGLE_OPTIONS byte-exact. Missing keys
                # WITHOUT --execute are a STOP (exit 2) that lists them;
                # a wrong-type field or a drifted picklist is a MISMATCH
                # (exit 5), never a silent pass.
                client, rc = _pit_client(out)
                if rc is not None:
                    return None, rc
                result = _capture_sibling(
                    out, lambda: mod.verify_live(client, location_id,
                                                 field_map,
                                                 execute=execute,
                                                 out=io.StringIO()))
                if result == EX_OK:
                    return ("PASS",
                            "both dropdowns live SINGLE_OPTIONS byte-exact "
                            "— the review decision with its two options "
                            "and the cover choice with its four style "
                            "names (marker %s)" % masked,
                            {"dropdowns": 2}, {"dropdowns": 2}), None
                if result == EX_STOP:
                    out.write("[main-skeleton] STOP: dropdown key(s) "
                              "missing live and --execute was not given — "
                              "the CREATE ACTION is Trevor-gated; the "
                              "missing-key list is the payload (marker "
                              "%s).\n" % masked)
                    return None, EX_STOP
                if result == EX_HELD:
                    out.write("[main-skeleton] HELD: the dropdown read was "
                              "HELD (marker %s) — UNDETERMINED, never a "
                              "verdict.\n" % masked)
                    return None, EX_HELD
                return ("FAIL",
                        "the dropdown law returned exit %d — a wrong-type "
                        "field or a drifted picklist (marker %s)"
                        % (result, masked),
                        {"dropdowns": 2}, {"dropdowns": "?"}), None
            if name == "hidden_field_module":
                # The hidden-field creator over the live listing — the
                # universal author-intake form's hidden trio byte-exact.
                # WITHOUT --execute a READ-ONLY dry-run (nothing written);
                # WITH --execute the PUT + read-back (a read-back that does
                # not prove the trio is a MISMATCH, exit 5). A credential-
                # shaped value on any surface REFUSES, never echoes.
                client, rc = _pit_client(out)
                if rc is not None:
                    return None, rc
                result = mod.plan_field_create(
                    client, location_id, execute=execute)
                report["checks"][name] = {
                    "status": "PASS" if result.get("ok") else "FAIL",
                    "detail": ("applied" if result.get("applied")
                               else "verified / dry-run") + ": " + result.get(
                                   "note", ""),
                    "expected": {"hidden_trio": True},
                    "live": {"applied": result.get("applied", False),
                             "ok": result.get("ok", False)},
                }
                if result.get("af_code"):
                    report["delta"].append(
                        {"check": name,
                         "expected": {"hidden_trio": True},
                         "live": {"af_code": result.get("af_code")},
                         "detail": result.get("note", "")})
                if not result.get("ok"):
                    return None, EX_MISMATCH
                return None, None
            if name == "title_select_builder":
                # The title-select builder — the S3 gate form's EXACTLY TWO
                # routing hidden fields (anthology_id, stage) + the visible
                # multi-line REQUIRED pair (title, subtitle), byte-exact.
                # Dry-run / PUT + read-back exactly as the hidden-field
                # creator.
                client, rc = _pit_client(out)
                if rc is not None:
                    return None, rc
                result = mod.plan_form_build(
                    client, location_id, execute=execute)
                report["checks"][name] = {
                    "status": "PASS" if result.get("ok") else "FAIL",
                    "detail": ("applied" if result.get("applied")
                               else "verified / dry-run") + ": " + result.get(
                                   "note", ""),
                    "expected": {"two_hidden": True,
                                 "visible_pair": True},
                    "live": {"applied": result.get("applied", False),
                             "ok": result.get("ok", False)},
                }
                if result.get("af_code"):
                    report["delta"].append(
                        {"check": name,
                         "expected": {"two_hidden": True,
                                      "visible_pair": True},
                         "live": {"af_code": result.get("af_code")},
                         "detail": result.get("note", "")})
                if not result.get("ok"):
                    return None, EX_MISMATCH
                return None, None
            if name == "universal_review_builder":
                # The universal-review builder — the decision form's hidden
                # pair (never contact_id), the TWO-option decision dropdown,
                # the multi-line notes surface, and the FOUR-option cover
                # dropdown. Dry-run / PUT + read-back exactly as above.
                client, rc = _pit_client(out)
                if rc is not None:
                    return None, rc
                result = mod.plan_review_build(
                    client, location_id, execute=execute)
                report["checks"][name] = {
                    "status": "PASS" if result.get("ok") else "FAIL",
                    "detail": ("applied" if result.get("applied")
                               else "verified / dry-run") + ": " + result.get(
                                   "note", ""),
                    "expected": {"hidden_pair": True,
                                 "decision_options": 2,
                                 "cover_options": 4},
                    "live": {"applied": result.get("applied", False),
                             "ok": result.get("ok", False)},
                }
                if result.get("af_code"):
                    report["delta"].append(
                        {"check": name,
                         "expected": {"hidden_pair": True,
                                      "decision_options": 2,
                                      "cover_options": 4},
                         "live": {"af_code": result.get("af_code")},
                         "detail": result.get("note", "")})
                if not result.get("ok"):
                    return None, EX_MISMATCH
                return None, None
            raise SkeletonError("dispatcher has no live gate for module %r"
                                % name)
        except reg.ScopeDenied as exc:
            reg._stop(out, "The Convert and Flow token cannot READ the "
                           "template location (%s)." % masked,
                      [str(exc), "Grant the template PIT the READ scope and "
                                 "re-run.", "AF-AE-PIT-SCOPE."])
            return None, EX_STOP
        except reg.UpstreamBlockedError as exc:
            out.write("[main-skeleton] HELD: %s\n" % exc)
            return None, EX_HELD
        except reg.CafUnreachable as exc:
            out.write("[main-skeleton] HELD: %s\n" % exc)
            return None, EX_HELD
        except reg.InternalRailUnavailable as exc:
            out.write("[main-skeleton] HELD (internal rail): %s\n" % exc)
            return None, EX_HELD
        except fr.FormsReadError as exc:
            reg._stop(out, "Fail-closed refusal in %s: %s" % (name, exc), [])
            return None, EX_STOP
        except _stop_classes(mod) as exc:
            reg._stop(out, "Fail-closed refusal in %s: %s" % (name, exc), [])
            return None, EX_STOP
        except SkeletonError as exc:
            reg._stop(out, "Fail-closed refusal in %s: %s" % (name, exc), [])
            return None, EX_STOP
        except Exception as exc:  # noqa: BLE001 — a module refusal is never an unexpected error
            if exc.__class__.__name__ in ("FormSpecError", "FormsFixError",
                                          "FormsBuildError", "ReviewBuildError",
                                          "DropdownError", "StyleImportError",
                                          "DecisionImportError", "FixtureError",
                                          "FormsReadError"):
                reg._stop(out, "Fail-closed refusal in %s: %s" % (name, exc), [])
                return None, EX_STOP
            raise

    # ---- the CREATE ACTION (Trevor-gated) -------------------------------
    # The gate holds HERE, before any check runs: the live verify itself is
    # an ACTION on the client's own location and the aggregate refuses to
    # fire it without --execute (AF-AE-U08-U09-NO-EXECUTE, the package-init
    # doctrine) — never a silent read sweep. WITH --execute the family's
    # create-only-missing contract holds — the modules write only what is
    # missing and read it back byte-exact; a drift is a MISMATCH. The
    # dispatcher itself never mutates.
    if execute:
        report["create"] = {
            "status": "AUTHORIZED",
            "execute": True,
            "note": "the CREATE ACTION is authorized by --execute "
                    "(Trevor-gated, the u08_u09 package-init doctrine) and "
                    "is create-only-missing with a byte-exact read-back — "
                    "a surface already present live is verified, never "
                    "re-created; a read-back that does not prove the write "
                    "is a MISMATCH (exit 5, AF-AE-READBACK-MISMATCH "
                    "family)",
            "af_code": "AF-AE-U08-U09-NO-EXECUTE",
        }

    for name, _role in LIVE_GATES:
        record, rc = _run(name, modules[name])
        if rc is not None:
            return rc
        if record is None:
            continue  # the module recorded its own check row
        status, detail, expected, live = record
        report["checks"][name] = {
            "status": status,
            "detail": detail,
            "expected": expected,
            "live": live,
        }
        if status == "FAIL":
            report["delta"].append(
                {"check": name, "expected": expected, "live": live,
                 "detail": detail})

    failures = [n for n, c in report["checks"].items()
                if c.get("status") == "FAIL"]
    report["verdict"] = "PASS" if not failures else "FAIL"
    print(json.dumps(report, indent=2, sort_keys=True))
    return EX_OK if not failures else EX_MISMATCH


# ---------------------------------------------------------------------------
# CLI — house shape: --dry-run / --self-test / --json accepted as flags AND
# as a positional subcommand (--self-test / --selftest normalize exactly as
# anthology_registry.py and the U02..U07 skeletons). The CREATE ACTION is a
# positional subcommand ('apply') that REQUIRES --execute (the Trevor gate);
# the default `verify` also REQUIRES --execute (the live aggregate is an
# ACTION under the package-init doctrine — an un-gated run is refused, never
# a silent read sweep; --dry-run and --self-test stay OFFLINE and free).
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="main_skeleton.py",
        description="U08/U09 form-law dispatcher: offline plan, offline "
                    "self-test, live verify, and the Trevor-gated CREATE "
                    "ACTION of the Anthology form-surface law family (Skill "
                    "59, u08_u09_modules; the packaged sibling of "
                    "u02_modules/main_skeleton.py, u03_modules/main_skeleton.py, "
                    "u04_modules/main_skeleton.py, u05_modules/main_skeleton.py, "
                    "u06_modules/main_skeleton.py and "
                    "u07_modules/main_skeleton.py) — imports the check "
                    "modules by name and aggregates their records into ONE "
                    "fail-closed JSON report. Every CREATE ACTION and the "
                    "live verify itself require --execute (Trevor-gated, "
                    "the u08_u09 package-init doctrine) — this dispatcher "
                    "never mutates.")
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
                    help="offline plan only — no network, no credential (default: live verify)")
    ap.add_argument("--json", action="store_true",
                    help="emit a machine-readable summary on stdout (default on for verify/plan)")
    ap.add_argument("--execute", action="store_true",
                    help="the Trevor gate (u08_u09 package doctrine): "
                         "REQUIRED before ANY write AND before the live "
                         "verify itself; without it a CREATE ACTION is a "
                         "STOP (exit 2) and the live aggregate is refused "
                         "up front (AF-AE-U08-U09-NO-EXECUTE); with it, "
                         "every write is create-only-missing with a "
                         "byte-exact read-back")
    ap.add_argument("--selftest", "--self-test", dest="self_test", action="store_true",
                    help="run the offline self-test (golden + attack fixtures) and exit")
    ap.add_argument("cmd", nargs="?", choices=["verify", "plan", "apply", "self-test"],
                    help="positional subcommand form (verify / plan / apply / self-test)")

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> --self-test so the flag form never
    # collides with the positional subcommand form.
    if "--self-test" in argv and "--selftest" not in argv:
        argv = ["--self-test" if a == "--self-test" else a for a in argv]
    args = ap.parse_args(argv)
    # Positional subcommand form (house shape): self-test -> the offline
    # battery; plan -> the offline dry-run.
    if args.cmd == "self-test":
        args.self_test = True
    elif args.cmd == "plan":
        args.dry_run = True

    try:
        modules = load_modules()

        if args.self_test:
            return self_test(modules)

        contract = _read_json(Path(args.contract).expanduser(),
                              "config/anthology-snapshot-contract.json")
        field_map = _read_json(Path(args.field_map).expanduser(),
                               "config/field-map.json")
        location_id = args.location_id.strip() or DEFAULT_TEMPLATE_LOCATION

        if args.dry_run:
            return plan(modules, location_id, contract)

        if args.cmd == "apply":
            # The Trevor gate, enforced at the CLI surface: a CREATE ACTION
            # without --execute is a STOP (exit 2), never a silent no-op and
            # never a silent create. WITH --execute it is create-only-
            # missing with a byte-exact read-back — the dispatcher never
            # mutates.
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
            return verify_live(modules, location_id, contract, field_map,
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
        return verify_live(modules, location_id, contract, field_map,
                           execute=True,
                           out=sys.stderr)

    except reg.ScopeDenied as exc:
        sys.stderr.write("[main-skeleton] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[main-skeleton] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[main-skeleton] HELD: %s\n" % exc)
        return EX_HELD
    except reg.InternalRailUnavailable as exc:
        sys.stderr.write("[main-skeleton] HELD: %s\n" % exc)
        return EX_HELD
    except SkeletonError as exc:
        sys.stderr.write("[main-skeleton] STOP/FAIL: %s\n" % exc)
        return EX_STOP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[main-skeleton] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


def _read_json(path: Path, what: str) -> dict:
    """Fail-closed contract reader — a missing section is never a blind pass."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SkeletonError("cannot read %s: %s" % (what, exc)) from exc
    except ValueError as exc:
        raise SkeletonError("%s is not valid JSON: %s" % (what, exc)) from exc
    if not isinstance(data, dict):
        raise SkeletonError("%s does not parse to a JSON object" % what)
    return data


if __name__ == "__main__":
    sys.exit(main())
