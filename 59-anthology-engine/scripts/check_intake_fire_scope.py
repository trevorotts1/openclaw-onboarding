#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: check_intake_fire_scope.py  (U05 tooling)
# INTAKE-FIRE SCOPE VERIFIER — the ONE CLI ASSEMBLED from the 16 u05_modules
# files: it imports EVERY module under scripts/u05_modules/ BY NAME
# (importlib, never exec'd from a path) and wires them into ONE CLI whose
# offline self-test battery (golden PASS / the TWO U05 attacks FAIL) runs
# before any live surface. This file carries NO check logic itself — a check
# family is exercised ONLY through its module so `--dry-run`, `--self-test`,
# and the live aggregate never drift apart. It is the packaged sibling of
# scripts/live_verify_template.py (U02, row 54), scripts/check_pipeline_name.py
# (U03, row 55) and scripts/fix_intake_form.py (U04, row 56) under the
# ENGINE-MANIFEST row-54 shipping doctrine.
#
# THE 16 u05_modules FILES (imported by name; each is STDLIB-only and
# self-tests itself — docs_u05.py carries the module inventory as data and
# its self-test proves the tree ships together):
#   __init__.py            fail-closed EMPTY package init (pure namespace)
#   main_skeleton.py       the check-module dispatcher CLI (plan / self-test /
#                          live verify; the ONE entry-point contract)
#   scope_checker.py       the pipeline-rule scope gate — filter == "Form is
#                          universal-intake" BYTE-EXACT, empty / wildcard /
#                          drifted filters OUT of scope (pure, never echoes
#                          the filter)
#   golden_scoped.py       the golden SCOPED-READ fixture (the canonical
#                          single-subject payload keyed by the one non-empty
#                          anthology_id filter; the KEYING LAW
#                          contact_id::anthology_id read once from
#                          anthology_state.participant_key, never hardcoded)
#                          + its fail-closed payload gate
#   attack_unscoped.py     the U05 ATTACK: the EMPTY-ANTHOLOGY-FILTER read
#                          (an unfiltered read reaches EVERY ledger row across
#                          ALL anthologies) that MUST FAIL every unscoped-read
#                          gate; the true one-anthology scoped read PASSES
#   attack_wrong_form.py   the U05 ATTACK: the WRONG FORM ON THE INTAKE
#                          FILTER (the canonical "Form is <token>" rule with
#                          the ONE form named swapped to a foreign form) that
#                          MUST FAIL every byte-exact scope gate
#   workflow_reader.py     the ONE live workflow read — find "Anthology
#                          Intake Fire" by the name law / pin on the
#                          internal-rail listing, report its ONE id
#                          (rail-gated; the ONE credential surface)
#   house_rules.py         the ONE canonical house-law constant surface
#                          (browser UA / version header ported byte-for-byte
#                          from the registry; the complete AF autofail table
#                          mirrored from ENGINE-MANIFEST.json)
#   negative_verifier.py   the NEGATIVE VERIFIER — certify, fail-closed, that
#                          a submission (the universal-review decision form)
#                          does NOT fire the Intake Fire trigger (the scope
#                          law IMPORTED from u02_modules.scope_check)
#   scope_applier.py       the U05 family's ONLY write surface — corrects the
#                          trigger scope filter of a release-notification
#                          workflow via the internal rail PUT; REFUSED unless
#                          the operator passes --execute to ITS OWN CLI (the
#                          dispatcher NEVER invokes it and NEVER writes)
#   trigger_reader.py      the OFFLINE reader of the n8n Drive-broker
#                          workflow asset's trigger filter set (the webhook
#                          gate, the Authorize & Dispatch filter law, the
#                          action allowlist pinned byte-exact to
#                          drive_adapter.BROKER_REQUIRED_ACTIONS)
#   example_usage.py       the fail-closed WORKED EXAMPLE of the U05 dispatch
#                          (front-door read + scoped law + both attacks + the
#                          negative mirror)
#   test_scope_checker.py  the independent pytest battery over the scope gate
#                          (provenance only)
#   test_negative_verifier.py  the independent pytest battery over the
#                          negative verifier (provenance only)
#   test_scope_applier.py  the independent pytest battery over the write
#                          gate of the scope applier (provenance only)
#   docs_u05.py            the U05 tooling README/catalog data + drift gate
#                          (the module inventory as DATA)
#
# THE TWO U05 ATTACKS (the offline self-test proves each is REFUSED — golden
# PASS / attack FAIL; a tamper NEVER masquerades as exit 1):
#   1. attack_unscoped     — the empty anthology filter must FAIL
#                            (AF-AE-ATTACKUNSCOPED-* family)
#   2. attack_wrong_form   — the wrong form on the intake filter must FAIL
#                            (AF-AE-ATTACKWRONGFORM-* family)
#
# WHAT THIS VERIFIES (MASTER-SPEC U05 — the SCOPED-READ and FILTER-SCOPE LAW
# of the anthology engine, SPEC 7.2 / 11.3: every participant-facing read is
# scoped to ONE subject, never an unscoped sweep; and the U05 pipeline rule
# "Form is universal-intake" gates ONLY the universal author-intake form).
# The dispatcher's live gates run in the FIXED order main_skeleton.LIVE_GATES
# carries them; the per-item claims live in the modules and in
# docs_u05.VERIFY_ITEMS:
#   1. SCOPED-READ LAW — every participant-facing read is keyed by EXACTLY
#      ONE non-empty filter value; the ledger scopes by anthology_id
#      (participant_key is the composite contact_id::anthology_id — the
#      KEYING LAW, anthology_state.participant_key); the EMPTY filter is the
#      unscoped sweep — an unfiltered read reaches EVERY ledger row and must
#      FAIL, never pass (golden_scoped payload gate + attack_unscoped).
#   2. INTAKE FIRE WORKFLOW READABLE — the "Anthology Intake Fire" front-door
#      workflow is found by NAME on the location's live internal-rail
#      listing and its ONE id reported (workflow_reader; a listing with no
#      matching row is WORKFLOWS-NOT-FOUND, a pinned id absent from the
#      listing is PIN-MISSING — exit 5, never a silent pass).
#   3. PIPELINE-RULE SCOPE — the U05 pipeline rule filter must be EXACTLY
#      "Form is universal-intake" (form == "universal-intake", byte-exact,
#      one space around "is", nothing else) to be in intake scope; anything
#      else — an EMPTY filter, a wildcard, a renamed form token, a
#      byte-drifted spelling — is OUT of scope with a typed reason
#      (scope_checker, pure, side-effect-free, never echoes the filter).
#   4. THE ATTACK BOUNDARY — the empty / unscoped filter and the wrong form
#      on the filter MUST FAIL every gate they touch, with the golden
#      controls PASSING (every pass/fail split discriminates the ONE-variable
#      boundary, never a broken instrument — the negative-result contract).
#   5. THE NEGATIVE MIRROR — a submission of the universal-review decision
#      form is CERTIFIED does-not-fire (negative_verifier; the scope law is
#      read once from u02_modules.scope_check, never re-implemented).
#   6. THE TRIGGER FILTER-SET READ — the shipped n8n Drive-broker asset's
#      trigger filter set is certified byte-exact to the engine authority
#      (trigger_reader; OFFLINE — reads the shipped asset, never the
#      network).
#   PLUS (assembled surface, exercised through the modules' own surfaces):
#   7. THE HOUSE-LAW CONSTANT SURFACE (house_rules — the browser UA / version
#      header / AF autofail table as immutable constants, byte-pinned).
#   8. THE WORKED EXAMPLE (example_usage — the composition runs the SAME
#      five-step law; its self-test pins the step order against LIVE_GATES).
#
# THE ONLY WRITE SURFACE IS THE GATED APPLIER (scope_applier.py): its PUT
# /workflow/{loc}/trigger/{id} is REFUSED unless the operator passes
# --execute to ITS OWN CLI (scripts/u05_modules/scope_applier.py --execute);
# this assembler NEVER invokes it and NEVER writes. A fix is never reported
# without the same-job read-back proving it byte-for-byte
# (AF-AE-READBACK-MISMATCH).
#
# THE ONE LIVE READ IS RAIL-GATED; THE TOOLING SHIPS NOW (manifest row 54
# doctrine). The operator executes `verify` only from a session that can
# resolve the internal-rail credential BY LABEL (Firebase refresh token
# preferred — the proven workflow surface, Skill 58 — else the template PIT
# as the rail fallback). --dry-run (offline plan) and --self-test (offline,
# no token, no network) always work; the six OFFLINE gates run without any
# credential — the ONE rail-gated live read is the workflow listing.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. The rail credential is resolved
# through anthology_registry (ANTHOLOGY_GHL_FIREBASE_REFRESH_TOKEN /
# GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN / GHL_FIREBASE_REFRESH_TOKEN, live
# process env first then the three canonical client env stores; PIT labels
# as the fallback). The location id is pinned to the contract's template
# location (2HIKGNgsixWx0yds7Qnx) unless --location-id overrides; the
# workflow id is found by the name law, never guessed from memory. SET /
# NOT SET only on every operator surface; a token value is NEVER printed,
# and the workflow / location ids are masked on every surface.
#
# BROWSER UA: every request rides reg.CafClient / reg.InternalRailClient /
# workflow_reader's rail client, which apply CAF_BROWSER_UA on every request
# so the Cloudflare edge fronting backend.leadconnectorhq.com never 1010s a
# verify request (CF 1010 / GK-09 discipline — the house pattern ported
# byte-for-byte from the U02 / U03 / U04 families). Scope-vs-edge-block
# discrimination: a bare 401/403 is HELD (UpstreamBlockedError /
# CafUnreachable), never mislabeled as a scope problem; a genuine scope
# denial is a STOP (exit 2).
#
# AF CODES (fail-closed surfaces; self-test failures are exit 4, never 1;
# the family is staged under manifest-pending/u05.json, its OWN manifest
# row stamped by this assembly):
#   AF-AE-U05-ASSEMBLY-INCOMPLETE -> the U05 check-module set named in the
#          assembly roster is not fully present, or a module violates the
#          one-entry-point contract. STOP (exit 2) — a check family is
#          never silently skipped.
#   AF-AE-SCOPED-SUBJECT-MISSING -> the scoped listing does not carry the
#          golden subject under its golden composite key. exit 5.
#   AF-AE-SCOPED-FOREIGN-ROW      -> a foreign subject leaked into the
#          one-subject read. exit 5.
#   AF-AE-SCOPED-ROW-COUNT        -> the scoped listing carries a row count
#          other than exactly one. exit 5.
#   AF-AE-NEGATIVE-INTAKE-FIRE    -> the negative verifier certified
#          does-not-fire for a submission that WOULD fire the Intake Fire
#          trigger. exit 5.
#   AF-AE-TRIGGER-SCOPE-VALIDATION -> the internal rail REFUSED the
#          trigger-scope PUT (scope_applier STOP). exit 2.
#   AF-AE-PIT-SCOPE               -> a genuine location-scope denial
#          signature on the live read — STOP, never mislabeled as an edge
#          block (workflow_reader; already stamped in ENGINE-MANIFEST.json).
#   AF-AE-TEMPLATE-ATTACK         -> an attack fixture tripped the OFFLINE
#          self-test (also the family self-test batteries). exit 4.
#
# EXIT CODES (house convention 0/1/2/3/5; 4 = enforced violation; the
# primary surface the operator consumes is 0 = PASS, 2 = STOP, 5 = mismatch):
#   0  all checks PASS (also --dry-run plan pass and self-test pass)
#   1  unexpected error
#   2  STOP refusal — label NOT SET / non-pit- value / usage / the U05
#      check-module assembly incomplete (AF-AE-U05-ASSEMBLY-INCOMPLETE) /
#      a contract that cannot be read / a module STOP-family refusal
#   3  HELD — Convert and Flow / the internal rail unreachable / Cloudflare
#      edge block (UNDETERMINED, never a verdict)
#   4  self-test FAILED — an assertion in the OFFLINE self-test tripped
#      (AF-AE-TEMPLATE-ATTACK family). A tamper NEVER masquerades as exit 1.
#   5  data or scope mismatch (AF-AE-SCOPED-* / AF-AE-ATTACKUNSCOPED-* /
#      AF-AE-ATTACKWRONGFORM-* / AF-AE-NEGATIVE-INTAKE-FIRE / the
#      WORKFLOWS-NOT-FOUND / PIN-MISSING families)
#
# MANIFEST-PENDING: after a PASSING run the tool writes
# manifest-pending/u05.json — the staged U05 manifest artifact (contract,
# checks verdict, the 16-module inventory, af-code family, exit-code
# contract, provenance) — so the manifest can be re-stamped from a
# machine-readable record once the operator approves. The write is
# fail-closed: it happens ONLY on a PASS (self-test pass or dry-run plan
# pass); a FAIL/HELD/STOP run writes nothing and removes nothing.
#
# STDLIB ONLY (urllib + json via the registry and the check modules); calls
# NO model. DOCTRINE: move in silence; NOTHING Anthropic in any runtime file;
# Convert and Flow naming in every client surface; NEVER print a secret
# value; --dry-run and --self-test are OFFLINE.
# =============================================================================
"""check_intake_fire_scope.py — the U05 intake-fire scope verifier assembled
from the 16 u05_modules files: one CLI, offline self-test battery (golden
PASS / the two U05 attacks FAIL), JSON output, and the manifest-pending/
u05.json stage (Skill 59)."""

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
# Cloudflare browser-UA wiring + the LeadConnector / internal-rail clients
# and its label resolution is the house credential contract.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent
MODULES_DIR = Path(__file__).resolve().parent / "u05_modules"
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"
PENDING_DIR = SKILL_DIR / "manifest-pending"
PENDING_U05 = PENDING_DIR / "u05.json"

# The template location id is the CONTRACT's source_template_location (the
# operator's OWN template location, operator infrastructure config, not a
# secret). The verifier pins to it; --location-id overrides for tests.
DEFAULT_TEMPLATE_LOCATION = "2HIKGNgsixWx0yds7Qnx"

# THE SIXTEEN u05_modules FILES — the assembly manifest for this verifier.
# Every name is imported BY NAME below (importlib), never exec'd from a
# path; a missing module is a STOP, never a silent skip (the fail-closed
# import contract of main_skeleton.load_modules). `role` is the one-line
# contract each module owns.
U05_MODULES = (
    ("__init__.py",            "fail-closed EMPTY package init (pure namespace)"),
    ("main_skeleton.py",       "the check-module dispatcher CLI (plan / self-test / live verify)"),
    ("scope_checker.py",       "the pipeline-rule scope gate (filter == 'Form is universal-intake' byte-exact; empty / wildcard / drifted filters are OUT of scope, never a pass)"),
    ("golden_scoped.py",       "the golden SCOPED-READ fixture (the canonical single-subject payload keyed by the one non-empty anthology_id filter; KEYING LAW read once from anthology_state.participant_key) + its fail-closed payload gate"),
    ("attack_unscoped.py",     "the U05 ATTACK: the empty-anthology-filter read that MUST FAIL every unscoped-read gate (the golden one-anthology scoped control PASSES)"),
    ("attack_wrong_form.py",   "the U05 ATTACK: the wrong form on the intake filter that MUST FAIL every byte-exact scope gate (the golden control PASSES)"),
    ("workflow_reader.py",     "the ONE live workflow read — find 'Anthology Intake Fire' by the name law / pin on the internal-rail listing, report its ONE id (rail-gated; the ONE credential surface)"),
    ("house_rules.py",         "the ONE canonical house-law constant surface (browser UA / version header ported byte-for-byte from the registry; the AF autofail table mirrored from ENGINE-MANIFEST.json)"),
    ("negative_verifier.py",   "the NEGATIVE VERIFIER — certify, fail-closed, that a submission (the universal-review decision form) does NOT fire the Intake Fire trigger (the scope law read once from u02_modules.scope_check)"),
    ("scope_applier.py",       "the ONLY write surface — the trigger-scope PUT via the internal rail, REFUSED without its own --execute (the dispatcher NEVER invokes it and NEVER writes)"),
    ("trigger_reader.py",      "the OFFLINE reader of the n8n Drive-broker trigger filter set (the webhook gate + the Authorize & Dispatch filter law + the action allowlist pinned to drive_adapter.BROKER_REQUIRED_ACTIONS)"),
    ("example_usage.py",       "the fail-closed WORKED EXAMPLE of the U05 dispatch (front-door read + scoped law + both attacks + the negative mirror)"),
    ("test_scope_checker.py",  "the independent pytest battery over the scope gate (provenance only)"),
    ("test_negative_verifier.py", "the independent pytest battery over the negative verifier (provenance only)"),
    ("test_scope_applier.py",  "the independent pytest battery over the write gate of the scope applier (provenance only)"),
    ("docs_u05.py",            "the U05 tooling README/catalog data + drift gate (the module inventory as DATA)"),
)

# The modules the dispatcher aggregates (main_skeleton.U05_MODULES — the
# check-module set named in the dispatcher's own roster; a check family
# that cannot prove itself offline STOPS).
DISPATCH_MODULE_NAMES = tuple(name for name, _ in (
    ("scope_checker", "the pipeline-rule scope gate (filter == 'Form is "
                      "universal-intake' byte-exact)"),
    ("golden_scoped", "the golden SCOPED-READ fixture + its fail-closed "
                      "payload gate"),
    ("attack_unscoped", "the U05 ATTACK: the empty-anthology-filter read "
                        "must FAIL"),
    ("attack_wrong_form", "the U05 ATTACK: the wrong form on the intake "
                          "filter must FAIL"),
    ("workflow_reader", "the ONE live workflow read (rail-gated)"),
    ("house_rules", "the ONE canonical house-law constant surface"),
    ("negative_verifier", "the NEGATIVE VERIFIER (does-not-fire "
                          "certification)"),
    ("scope_applier", "the ONLY write surface (REFUSED without --execute)"),
    ("trigger_reader", "the OFFLINE trigger filter-set reader"),
    ("example_usage", "the fail-closed WORKED EXAMPLE of the U05 dispatch"),
    ("docs_u05", "the U05 tooling README/catalog data + drift gate"),
))

# The modules that ship their OWN offline self-test battery (golden PASS /
# attack FAIL, exit 0 pass / 4 enforced violation). Every check module ships
# a battery — the dispatcher REQUIRES a battery from every module. The three
# pytest batteries are imported for their provenance; their tests run as the
# independent pytest battery.
SELF_TEST_MODULES = tuple(
    name[:-3] for name, _ in U05_MODULES
    if name not in ("__init__.py", "test_scope_checker.py",
                    "test_negative_verifier.py", "test_scope_applier.py",
                    "main_skeleton.py"))
TEST_MODULES = ("test_scope_checker", "test_negative_verifier",
                "test_scope_applier")

# The live-verify gate order — the dispatcher's fixed order (mirrors
# main_skeleton.LIVE_GATES one-to-one; the self-test pins the two cannot
# drift).
LIVE_GATES = tuple(name for name, _ in (
    ("golden_scoped", "the scoped-read law — the golden single-subject "
                      "listing must pass the fail-closed payload gate"),
    ("scope_checker", "the pipeline-rule scope law — the golden rule "
                      "filter must be IN scope byte-exact"),
    ("workflow_reader", "the Intake Fire workflow read — the live "
                        "internal-rail listing must name the workflow "
                        "(rail-gated; the ONE credential surface)"),
    ("attack_unscoped", "the attack boundary — the empty-filter attack "
                        "must FAIL and the one-anthology control PASS"),
    ("attack_wrong_form", "the attack boundary — the wrong-form attack "
                          "must FAIL and the golden control PASS"),
    ("negative_verifier", "the negative mirror — the golden universal-"
                          "review submission must be CERTIFIED "
                          "does-not-fire"),
    ("trigger_reader", "the trigger filter-set read — the shipped n8n "
                       "Drive-broker asset's filter set must be certified "
                       "byte-exact to the engine authority"),
))

# The four U05 verified items, as the manifest-pending stage records them
# (docs_u05.VERIFY_ITEMS — the catalog and the tree never drift).
VERIFIED_ITEMS = (
    (1, "scoped_read", "Scoped-read law — every read scoped to ONE subject"),
    (2, "intake_fire_workflow", "Intake Fire workflow readable (name law + "
                                "pin law)"),
    (3, "pipeline_rule_scope", "Pipeline-rule scope — filter is 'Form is "
                               "universal-intake'"),
    (4, "attack_boundary", "Attack boundary — the FAIL paths are proven to "
                           "FAIL"),
)

# The AF-AE autofail family, as the stage records it.
AF_CODES = (
    ("AF-AE-U05-ASSEMBLY-INCOMPLETE", 2,
     "the U05 check-module set named in the assembly roster is not fully "
     "present, or a module violates the one-entry-point self_test contract — "
     "a check family is never silently skipped (dispatcher STOP)"),
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
     "the one-subject read is no longer one (golden_scoped payload gate)"),
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
     "negative claim is FALSE"),
    ("AF-AE-TRIGGER-SCOPE-VALIDATION", 2,
     "the internal rail REFUSED the trigger-scope PUT — a data-contract "
     "problem to resolve in the Convert and Flow UI; the filter was NOT "
     "corrected (scope_applier STOP; not yet stamped in "
     "ENGINE-MANIFEST.json)"),
    ("AF-AE-PIT-SCOPE", 2,
     "a genuine location-scope denial signature on the live read — STOP, "
     "never mislabeled as an edge block (workflow_reader; already stamped "
     "in ENGINE-MANIFEST.json)"),
    ("AF-AE-TEMPLATE-ATTACK", 4,
     "an attack fixture tripped the OFFLINE self-test of the dispatcher "
     "or a family battery (enforced violation — the house code, shared "
     "with the U02 / U03 / U04 families)"),
)

# House exit-code contract (docs_u05.EXIT_CODES).
EXIT_CODES = {
    0: "verified success — the filter is byte-exact and the live surface "
       "agrees with its source of truth (also plan / dry-run / self-test / "
       "a certified does-not-fire negative)",
    1: "unexpected error (top-level guard; never a secret leak)",
    2: "STOP refusal — label NOT SET / non-pit- value / usage / the U05 "
       "check-module assembly incomplete (AF-AE-U05-ASSEMBLY-INCOMPLETE) / "
       "a contract that cannot be read / an empty or malformed scope "
       "policy / a module STOP-family refusal (incl. AF-AE-PIT-SCOPE)",
    3: "HELD — Convert and Flow unreachable / Cloudflare edge block "
       "(CF error 1010) / the internal rail unavailable (UNDETERMINED, "
       "never a verdict)",
    4: "self-test FAILED (AF-AE-TEMPLATE-ATTACK / AF-AE-GOLDENSCOPED-* / "
       "AF-AE-ATTACKUNSCOPED-* / AF-AE-ATTACKWRONGFORM-* / "
       "AF-AE-NEGATIVE-ATTACK family, enforced violation) — a tamper "
       "never masquerades as exit 1",
    5: "mismatch / fail-closed default — an empty or byte-drifted filter, "
       "a wrong form on the filter, a submission that FIRES Intake Fire "
       "or is INDETERMINATE, no 'Anthology Intake Fire' row, a pinned id "
       "absent from the listing, a foreign subject row, a fixture payload "
       "that drifted, or a DEFERRED live read without --allow-deferred",
}

class AssembleError(Exception):
    """A fail-closed refusal raised by the assembly itself — a missing
    u05_modules file, a module violating the entry-point contract, or a
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
# The 16-file assembly — import EVERY u05_modules file BY NAME. The empty
# package init is imported for the namespace guarantee (importing the
# package succeeds only if __init__.py is intact); the check modules come
# through main_skeleton.load_modules (the ONE entry-point contract); the
# fixture / checker / docs modules are imported for their surfaces and
# their self-test batteries; the three pytest batteries are imported for
# their provenance (their tests run as the independent pytest battery).
# ---------------------------------------------------------------------------
def _load_package() -> None:
    """Prove the package namespace container imports clean."""
    importlib.import_module("u05_modules")

def load_skeleton() -> object:
    """The main_skeleton dispatcher module (imported BY NAME)."""
    return importlib.import_module("u05_modules.main_skeleton")

def load_all_modules(out=None) -> dict:
    """Import every one of the 16 u05_modules files. Returns
    {name: module}. Fail-closed: a missing file or a module violating its
    contract raises AssembleError (STOP) — the aggregate NEVER passes with
    a module silently absent.

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
            modules[name] = importlib.import_module("u05_modules." + name)
        except ImportError:
            missing.append(name)
    for name in TEST_MODULES:
        try:
            modules[name] = importlib.import_module("u05_modules." + name)
        except ImportError:
            missing.append(name)
    if missing:
        raise AssembleError(
            "u05_modules file(s) not found: %s — the 16-file assembly is "
            "incomplete (fail-closed: no module is ever skipped)"
            % ", ".join(missing))
    if len(modules) != 15:
        raise AssembleError(
            "assembly loaded %d modules, expected 15 (main_skeleton + 11 "
            "dispatch modules + 3 pytest batteries)" % len(modules))
    return modules

# ---------------------------------------------------------------------------
# Offline self-test — run EVERY module's own battery (golden PASS / the
# two U05 attacks FAIL), plus the main_skeleton dispatcher battery, plus
# this verifier's own assembly assertions, plus the three sibling pytest
# batteries. NO network, NO credentials. Exit 4 on any failure.
# ---------------------------------------------------------------------------
def _module_self_test(module, name: str, out) -> None:
    st = getattr(module, "self_test", None)
    if not callable(st):
        raise AssertionError(
            "module %s does not expose 'self_test' — every u05_modules "
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
    scope-law family (the scope gate + the negative verifier + the applier
    write gate) is pinned offline. A failed battery is an enforced
    violation, never a silent skip."""
    pkg = Path(modules["test_scope_checker"].__file__).resolve().parent
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
    two U05 attacks MUST FAIL), the dispatcher battery, the assembly's
    file-count assertions, the scope-law gate (golden PASS / attacks FAIL
    / the does-not-fire certification), and the sibling pytest batteries.
    Any failure is exit 4 (AF-AE-TEMPLATE-ATTACK family) — a tamper NEVER
    masquerades as exit 1. On a clean pass the manifest-pending stage is
    written by the CLI."""
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        # 1. the assembly is complete: exactly the 16 files exist.
        on_disk = sorted(p.name for p in MODULES_DIR.glob("*.py"))
        expected = sorted(name for name, _ in U05_MODULES)
        assert on_disk == expected, (
            "u05_modules tree drifted: disk carries %d files, the 16-file "
            "assembly contract names %d (%s)"
            % (len(on_disk), len(expected),
               ", ".join(sorted(set(on_disk) ^ set(expected)))))
        # 2. every module's own battery passes (golden PASS / attack FAIL).
        for name in SELF_TEST_MODULES:
            _module_self_test(modules[name], name, dev)
        # 3. the dispatcher battery passes (main_skeleton.self_test runs the
        #    eleven check modules through the one-entry-point contract and
        #    pins the browser-UA / credential / exit-code laws). The
        #    dispatcher's own battery is run by itself: it iterates ITS OWN
        #    dispatch set (self_test(modules)), and this assembly already
        #    ran every module battery above — so here the dispatcher battery
        #    runs over ITS dispatch modules only, never over this assembler
        #    (which would recurse).
        skeleton = modules["main_skeleton"]
        dispatch_only = {k: v for k, v in modules.items()
                         if k in DISPATCH_MODULE_NAMES}
        sk_rc = skeleton.self_test(dispatch_only, out=dev)
        assert sk_rc == EX_OK, \
            "main_skeleton dispatcher self-test returned exit %d" % sk_rc
        # 3b. the dispatcher's live-gate order is this assembly's live-gate
        #     order (the two can never drift — the aggregate runs the gates
        #     in the FIXED order the scope law carries them).
        assert tuple(name for name, _ in skeleton.LIVE_GATES) == LIVE_GATES, \
            "the dispatcher's LIVE_GATES drifted from the assembly's order"
        # 4. the scope-law gate, exercised through the modules' own
        #    surfaces — the GOLDEN states PASS and the TWO U05 ATTACKS FAIL
        #    (never a silent pass, never a blind refusal):
        # 4a. the golden pipeline-rule filter is IN scope byte-exact, and
        #     the golden single-subject listing passes the fail-closed
        #     scoped gate (KEYING LAW contact_id::anthology_id, exactly one
        #     row).
        sc = modules["scope_checker"]
        golden = modules["golden_scoped"]
        ok, flt = sc.check({"source": "anthology-intake",
                            "location": "LOC-synthetic-AAA",
                            "filter": sc.UNIVERSAL_INTAKE_FILTER})
        assert ok, "the golden rule filter must be IN scope: %s" % flt
        assert flt.get("form") == sc.UNIVERSAL_INTAKE_FORM, \
            "the golden filter must gate the universal-intake form"
        assert sc.UNIVERSAL_INTAKE_FILTER == "Form is universal-intake", \
            "the pipeline-rule filter law drifted from the U05 contract"
        assert sc.UNIVERSAL_INTAKE_FORM == "universal-intake", \
            "the universal-intake form token drifted from the U05 contract"
        listing = golden.golden_listing_payload()
        assert golden.FILTER_KEY == "anthology_id", \
            "the filter key drifted from the KEYING LAW"
        assert golden.GOLDEN_ANTHOLOGY_ID == "anth_golden", \
            "the golden anthology id drifted from the fixture contract"
        rc = golden.payload(listing, out=io.StringIO())
        assert rc == EX_OK, \
            "the golden single-subject listing must pass the scoped gate"
        # 4b. ATTACK 1 — the EMPTY anthology filter FAILS every unscoped-read
        #     gate AND the attack fixture's own fail-closed surface refuses
        #     it (AF-AE-ATTACKUNSCOPED family). The law is read from the
        #     owning modules: the attack fixture's own judge and ledger, the
        #     golden one-anthology control from the fixture (the pass side of
        #     the split — a gate that fails everything is a broken
        #     instrument).
        au = modules["attack_unscoped"]
        fail_rc = au.verify_live("", au.ATTACK_LEDGER, out=io.StringIO())
        assert fail_rc == EX_MISMATCH, \
            "ATTACK 1 (empty anthology filter) was NOT refused (exit %s)" % fail_rc
        pass_rc = au.verify_live(au.SCOPED_BOOK_ID, au.ATTACK_LEDGER,
                                 out=io.StringIO())
        assert pass_rc == EX_OK, \
            "the golden one-anthology scoped control must PASS (exit %s)" % pass_rc
        # 4c. ATTACK 2 — the WRONG FORM on the intake filter FAILS every
        #     byte-exact scope gate AND the attack fixture's own fail-closed
        #     surface refuses it (AF-AE-ATTACKWRONGFORM family). The law is
        #     read from the owning modules: the swapped form from the
        #     fixture's own attacker, the gate from the fixture's own
        #     fail-closed surface, the golden control from the fixture (the
        #     pass side of the split).
        awf = modules["attack_wrong_form"]
        assert awf.ATTACK_FORM != awf.u05scope.UNIVERSAL_INTAKE_FORM, \
            "the wrong-form attack must name a FOREIGN form"
        fail_rc = awf.verify_rule(awf.ATTACK_RULE, out=io.StringIO())
        assert fail_rc == EX_MISMATCH, \
            "ATTACK 2 (wrong form on the filter) was NOT refused (exit %s)" % fail_rc
        pass_rc = awf.verify_rule(awf.GOLDEN_RULE_CANONICAL, out=io.StringIO())
        assert pass_rc == EX_OK, \
            "the golden rule control must PASS the byte-exact gate (exit %s)" % pass_rc
        # 4d. the NEGATIVE MIRROR — the golden universal-review submission is
        #     CERTIFIED does-not-fire (the negative-result contract: a
        #     verifier that fails EVERYTHING is never mistaken for a real
        #     discrimination).
        nv = modules["negative_verifier"]
        golden_negative = {"source": "anthology-intake",
                           "location": "LOC-synthetic-RVW",
                           "form": nv.UNIVERSAL_REVIEW_FORM,
                           "contact_id": "C-9001",
                           "anthology_id": "A-9001",
                           "stage": "s7_cover"}
        nreport = nv.check(golden_negative)
        assert nreport.get("ok") and nreport.get("verified"), \
            "the golden universal-review submission must be CERTIFIED " \
            "does-not-fire: %s" % nreport.get("note")
        assert nreport.get("fires_intake") is False, \
            "the does-not-fire certification must carry fires_intake False"
        # 4e. the OFFLINE trigger filter-set read certifies the shipped n8n
        #     Drive-broker asset byte-exact (the front door's filter set
        #     must be certified; never the network).
        tr = modules["trigger_reader"]
        tres = tr.read_trigger()
        assert tres.get("ok"), \
            "the Drive-broker trigger filter set must be certified: %s" \
            % tres.get("af_code", "?")
        # 5. docs_u05's catalog is the assembly's catalog (4 items, 12
        #    modules in its inventory, exit codes 0..5 — its self-test
        #    already pinned the counts; here we pin the shared constants).
        docs = modules["docs_u05"]
        assert len(docs.verify_items()) == len(VERIFIED_ITEMS), \
            "docs_u05 item count drifted from the assembly's VERIFIED_ITEMS"
        # 6. the sibling pytest batteries (the independent proof).
        if run_pytest:
            _run_pytest(modules, dev)
    except AssertionError as exc:
        sys.stderr.write("[check-intake-fire-scope] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    except AssembleError as exc:
        sys.stderr.write("[check-intake-fire-scope] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION

    out.write(dev.getvalue())
    out.write("[check-intake-fire-scope] assembled self-test: OK (16 "
              "u05_modules files imported, 11 module batteries + dispatcher "
              "battery + scope-law gate with the 2 U05 attacks REFUSED + %s "
              "+ assembly assertions all pass)\n"
              % ("3 pytest batteries" if run_pytest else
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
        "contract": "anthology-engine-u05-dispatch-plan",
        "schema_version": 1,
        "kind": "dry-run",
        "template_location_id": location_id,
        "template_location_id_masked": _mask_id(location_id),
        "gates": list(LIVE_GATES),
        "modules": [name for name, _ in U05_MODULES],
        "dry_run": True,
        "note": "offline plan only — no network, no credential needed; a "
                "LIVE read must ride reg.InternalRailClient / reg.CafClient "
                "(CAF_BROWSER_UA on every request — CF 1010 law); the "
                "applier writes ONLY with its own --execute",
    }, indent=2, sort_keys=True))
    out.write("[check-intake-fire-scope] dry-run plan: OK (offline — no "
              "network, no credential needed)\n")
    return EX_OK

def _mask_id(fid: str) -> str:
    """Mask a workflow / location id for every operator surface — a location
    identifier, not a secret, but never printed in full (house pattern,
    mirrored from workflow_reader.mask_id)."""
    fid = (fid or "").strip()
    if len(fid) <= 8:
        return "***"
    return "%s***%s" % (fid[:4], fid[-4:])

# ---------------------------------------------------------------------------
# Live verify — the dispatcher's fail-closed aggregate over the gates in
# the FIXED order. Any FAIL -> exit 5; a STOP-family refusal propagates as
# exit 2; a transport / edge failure is HELD (exit 3), never mislabeled as
# scope. The six OFFLINE gates run first (no credential); the ONE rail-
# gated live read (workflow_reader) resolves its credential BY LABEL inside
# the dispatcher. This assembler NEVER invokes the applier and NEVER
# writes — the ONLY write surface is scope_applier.py's own CLI with
# --execute.
# ---------------------------------------------------------------------------
def verify_live(modules: dict, location_id: str, contract: dict, *,
                allow_deferred: bool = False, out=None) -> int:
    out = out or sys.stderr
    skeleton = modules["main_skeleton"]
    return skeleton.verify_live(modules, location_id, contract,
                                allow_deferred=allow_deferred, out=out)

# ---------------------------------------------------------------------------
# Manifest-pending stage — manifest-pending/u05.json. Written ONLY after a
# PASS (self-test pass or dry-run plan pass); a FAIL/HELD/STOP run writes
# nothing. The record is the machine-readable input to a later manifest
# re-stamp — the ENGINE-MANIFEST.json / ENGINE-PIN.sha256 / verify.sh are
# NEVER touched here.
# ---------------------------------------------------------------------------
def _pending_payload(kind: str, location_id: str, *,
                     verdict: str = "PASS") -> dict:
    return {
        "contract": "anthology-engine-u05-intake-fire-scope",
        "schema_version": 1,
        "kind": kind,  # "self-test" | "dry-run" | "verify"
        "verdict": verdict,
        "script": "check_intake_fire_scope.py",
        "authored_by": "U05",
        "template_location_id": location_id,
        "u05_modules": [
            {"name": name, "role": role} for name, role in U05_MODULES
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
            "note": "the ONE live read (workflow_reader) is rail-gated "
                    "(Firebase refresh token BY LABEL preferred, PIT "
                    "fallback) and HELD (exit 3) when the rail is "
                    "unreachable — never a fabricated pass; the applier "
                    "(scope_applier.py) is the ONLY write surface and "
                    "REFUSES without its own --execute — this assembler "
                    "never writes.",
        },
    }

def write_pending(payload: dict, *, mode: str = "self-test", out=None) -> None:
    """Write manifest-pending/u05.json (fail-closed: only after a PASS).

    The directory is created if absent; the file is written atomically
    (temp + rename) so a crash mid-write never leaves a partial stage. The
    ENGINE-MANIFEST.json / ENGINE-PIN.sha256 / verify.sh are NEVER touched."""
    out = out or sys.stderr
    try:
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        tmp = PENDING_DIR / ("u05.json.tmp-%d" % os.getpid())
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
        tmp.replace(PENDING_U05)
    except OSError as exc:
        raise AssembleError("cannot write %s: %s" % (PENDING_U05, exc)) from exc
    out.write("[check-intake-fire-scope] manifest-pending stage written: %s "
              "(%s)\n" % (PENDING_U05, mode))

# ---------------------------------------------------------------------------
# CLI — house shape: --dry-run / --self-test / --json accepted as flags AND
# as a positional subcommand (--self-test / --selftest normalize exactly as
# anthology_registry.py, u02_modules/main_skeleton.py, and
# u03_modules/main_skeleton.py).
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="check_intake_fire_scope.py",
        description="The U05 intake-fire scope verifier assembled from the "
                    "16 u05_modules files: offline self-test battery (golden "
                    "PASS / the two U05 attacks FAIL), offline plan, and "
                    "live verify of the SCOPED-READ and FILTER-SCOPE LAW "
                    "family on the Anthology TEMPLATE location (Skill 59) — "
                    "every delta documented as JSON, the manifest-pending "
                    "stage written after a PASS. The ONLY write surface is "
                    "scope_applier.py's own CLI with --execute; this tool "
                    "never writes.")
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
    ap.add_argument("--no-pytest", action="store_true",
                    help="skip the sibling pytest batteries inside "
                         "--self-test (dispatch self-test only; the offline "
                         "batteries still run)")
    ap.add_argument("--selftest", "--self-test", dest="self_test",
                    action="store_true",
                    help="run the offline self-test (golden PASS / the two "
                         "U05 attacks FAIL + the dispatcher battery + the "
                         "pytest batteries) and exit")
    ap.add_argument("cmd", nargs="?", choices=["verify", "plan", "self-test"],
                    help="positional subcommand form (verify / plan / "
                         "self-test)")

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

        rc = verify_live(modules, location_id, contract,
                         allow_deferred=args.allow_deferred,
                         out=sys.stderr)
        if rc == EX_OK:
            write_pending(_pending_payload("verify", location_id),
                          mode="verify")
        return rc

    except reg.ScopeDenied as exc:
        sys.stderr.write("[check-intake-fire-scope] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[check-intake-fire-scope] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[check-intake-fire-scope] HELD: %s\n" % exc)
        return EX_HELD
    except reg.InternalRailUnavailable as exc:
        sys.stderr.write("[check-intake-fire-scope] HELD (internal rail): "
                         "%s\n" % exc)
        return EX_HELD
    except AssembleError as exc:
        sys.stderr.write("[check-intake-fire-scope] STOP/FAIL: %s\n" % exc)
        return EX_STOP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[check-intake-fire-scope] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR

if __name__ == "__main__":
    sys.exit(main())
