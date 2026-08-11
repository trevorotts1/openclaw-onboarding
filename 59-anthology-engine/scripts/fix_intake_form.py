#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: fix_intake_form.py  (U04 tooling)
# INTAKE FRONT-DOOR FIXER + VERIFIER — the ONE CLI ASSEMBLED from the 16
# u04_modules files: it imports EVERY module under scripts/u04_modules/ BY
# NAME (importlib, never exec'd from a path) and wires them into ONE CLI
# whose offline self-test battery (golden PASS / the THREE U04 attacks FAIL)
# runs before any live surface. This file carries NO check logic itself — a
# check family is exercised ONLY through its module so `--dry-run`,
# `--self-test`, and the live aggregate never drift apart. It is the
# packaged sibling of scripts/live_verify_template.py (U02, row 54) and
# scripts/check_pipeline_name.py (U03, row 55) under the ENGINE-MANIFEST
# row-54 shipping doctrine.
#
# THE 16 u04_modules FILES (imported by name; each is STDLIB-only and
# self-tests itself — docs_u04.py carries the module inventory as data and
# its self-test proves the tree ships together):
#   __init__.py            fail-closed EMPTY package init (pure namespace)
#   main_skeleton.py       the check-module dispatcher CLI (plan / self-test /
#                          live verify; the ONE entry-point contract)
#   form_reader.py         live public-v2 forms listing read — find the
#                          universal author-intake form by slug / pin, report
#                          its ONE form id (the ONE owner of the form-id pin)
#   required_checker.py    the required-flags law (first_name / last_name /
#                          email present and non-empty, intake_router
#                          FIELD_ALIASES-aware), OFFLINE and pure
#   brand_link_checker.py  the OFFLINE brand-surface legal-link gate
#                          (RFC 2606 placeholder hosts / hostless / bare
#                          legal rows flag REPLACE; a page with no anchors
#                          flags MISSING); never fetches, never resolves
#   query_key_checker.py   the G3 intake query-key gate (the hidden field
#                          must be keyed "anthology_id" BYTE-EXACT, never the
#                          lookalike "anthology_active_id"); the live page
#                          read is CREDENTIAL-FREE (public hosted-form widget)
#                          and rides reg.CAF_BROWSER_UA; a page that cannot
#                          be fetched is HELD (exit 3), never judged
#   query_key_fixer.py     the ONLY write surface of the U04 family — the G3
#                          query-key fix via public v2 PUT /forms/{id},
#                          REFUSED unless the operator passes --execute to
#                          ITS OWN CLI; the dispatcher NEVER invokes it and
#                          NEVER writes; after the PUT the form is read back
#                          and must prove the fix byte-for-byte
#   golden_ok.py           the golden ALREADY-COMPLIANT intake-form fixture,
#                          derived byte-exact from the committed snapshot
#                          contract, never a hardcoded list
#   attack_bad_query.py    the U04 ATTACK: the G3-conflation link
#                          (anthology_id swapped to anthology_active_id) that
#                          every byte-exact query-key gate must REFUSE
#   attack_example_dot_com.py  the U04 ATTACK: an example.com legal link that
#                          every brand-surface gate must REFUSE
#   attack_not_required.py the U04 ATTACK: an intake payload with email
#                          ABSENT / EMPTY / whitespace-only / non-string is
#                          REFUSED (NotRequiredError, STOP family), never a
#                          clean read
#   label_checker.py       the OFFLINE raw-key / warm-client-language map
#                          gate (every raw ledger key has a warm label; no
#                          raw key leaks onto a client-facing template)
#   prefill_verifier.py    the G3 VALUE-side gate — the live form's hidden
#                          anthology_id pre-fill is hydrated from the minted
#                          link's ONE query param (served-page identity +
#                          the committed widget-build signature in
#                          config/prefill-verifier-baseline.json;
#                          credential-free, a headless render OPTIONAL)
#   test_checkers.py       the independent pytest battery over the six
#                          public check surfaces (provenance only; the
#                          dispatcher asserts the file's presence)
#   test_prefill.py        the independent pytest battery over the
#                          prefill verifier (provenance only)
#   docs_u04.py            the U04 README/catalog data + drift gate (the
#                          module inventory as DATA; its self-test proves
#                          the tree ships together)
#
# THE THREE U04 ATTACKS (the offline self-test proves each is REFUSED —
# golden PASS / attack FAIL; a tamper NEVER masquerades as exit 1):
#   1. attack_bad_query        — the wrong hidden query key must FAIL
#                                (AF-AE-ATTACKBADQUERY-* family)
#   2. attack_example_dot_com  — an example.com legal link must FAIL
#                                (AF-AE-ATTACKEXAMPLEDOTCOM-* family)
#   3. attack_not_required     — an intake payload with no email must be
#                                REFUSED, never a clean read
#                                (AF-AE-REQUIRED-ATTACK family)
#
# WHAT THIS VERIFIES (MASTER-SPEC U04; the dispatcher's four live gates in
# the FIXED order main_skeleton.LIVE_GATES carries them; the per-item claims
# live in the modules and in docs_u04.VERIFY_ITEMS):
#   1. UNIVERSAL AUTHOR-INTAKE FORM READABLE — the public v2 read
#      GET /forms/?locationId= FINDS the universal author-intake form by
#      slug / pin and reports its ONE form id (a listing with NO
#      universal-intake row is a FAIL, never a silent empty; an unreadable
#      listing shape STOPS, exit 2).
#   2. G3 INTAKE QUERY KEY BYTE-EXACT 'anthology_id' — the live hosted-form
#      page (the PUBLIC widget, credential-free) keys its hidden Book-ID
#      field data-q EXACTLY "anthology_id" in a hidden container, with
#      "anthology_active_id" NOWHERE as a live data-q (AF-AE-INTAKE-QUERY-KEY,
#      exit 5); a page that cannot be fetched is HELD (exit 3), never judged.
#   3. REQUIRED INTAKE FLAGS present and non-empty (first_name / last_name /
#      email, intake_router FIELD_ALIASES-aware; email is a REQUIRED field,
#      never a KEY — MASTERDOC floor 8). OFFLINE: the law-coherence smoke
#      over the golden compliant payload.
#   4. BRAND LEGAL LINKS replacement-ready (RFC 2606 placeholder hosts /
#      hostless / bare legal rows flag REPLACE; never fetches, never
#      resolves). Live read DEFERRED until brand HTML page paths are wired —
#      never fabricated; the DEFERRED check fails the aggregate (exit 5)
#      unless --allow-deferred.
#   PLUS (assembled surface, exercised through the module's OWN CLI):
#   5. RAW-KEY / WARM-LABEL LAW (label_checker — offline; the client-facing
#      template family never speaks a raw key).
#   6. PRE-FILL HYDRATION LAW (prefill_verifier — the value side of the G3
#      gate; served-page identity + widget-build signature; credential-free).
#
# THE ONLY WRITE SURFACE IS THE GATED FIXER (query_key_fixer.py): its PUT
# /forms/{id} is REFUSED unless the operator passes --execute to ITS OWN
# CLI (scripts/u04_modules/query_key_fixer.py --execute); this assembler
# NEVER invokes it and NEVER writes. A fix is never reported without the
# same-job read-back proving it byte-for-byte (AF-AE-READBACK-MISMATCH).
#
# THE LIVE READ IS GHL-GATED; THE TOOLING SHIPS NOW (manifest row 54
# doctrine). The operator executes `verify` only from a session that can
# resolve a template-scoped private-integration token BY LABEL. --dry-run
# (offline plan) and --self-test (offline, no token, no network) always
# work. The ONE exception: query_key_checker's live read is the PUBLIC
# hosted-form page — credential-free by design — but the aggregate still
# refuses up front without a PIT (the form_reader gate is PIT-gated and
# no gate is ever skipped).
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. The PIT is resolved through
# anthology_registry (CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_API_KEY /
# GOHIGHLEVEL_API_KEY / GOHIGHLEVEL_PIT / GHL_API_KEY, live process env
# first then the three canonical client env stores). The location id is
# pinned to the contract's template location (2HIKGNgsixWx0yds7Qnx) unless
# --location-id overrides; the form id is pinned to
# DEFAULT_UNIVERSAL_INTAKE_FORM_ID (imported from form_reader, the ONE
# owner of the pin) unless --form-id overrides. SET / NOT SET only on every
# operator surface; a token value is NEVER printed, and the form/location
# ids are masked on every surface.
#
# BROWSER UA: every request rides reg.CafClient / query_key_checker's
# fetch / prefill_verifier's fetch, which apply CAF_BROWSER_UA on every
# request so the Cloudflare edge fronting services.leadconnectorhq.com /
# the hosted-form domain never 1010s a verify request (CF 1010 / GK-09
# discipline — the house pattern ported byte-for-byte from the U02 / U03
# families and the podcast gate). Scope-vs-edge-block discrimination: a
# bare 401/403 is HELD (UpstreamBlockedError / CafUnreachable), never
# mislabeled as a scope problem; a genuine scope denial is a STOP (exit 2).
#
# AF CODES (fail-closed surfaces; self-test failures are exit 4, never 1;
# the family is staged under manifest-pending/u02.json · u03.json, its OWN
# manifest row stamped by this assembly):
#   AF-AE-U04-ASSEMBLY-INCOMPLETE -> the U04 check-module set named in the
#          assembly roster is not fully present, or a module violates the
#          one-entry-point contract. STOP (exit 2) — a check family is
#          never silently skipped.
#   AF-AE-INTAKE-QUERY-KEY       -> the live intake form's hidden query
#          key is not "anthology_id" byte-exact (query_key_checker), or a
#          live field submits under the lookalike key. exit 5.
#   AF-AE-BRAND-LINK             -> a brand page carries a placeholder /
#          hostless legal link (brand_link_checker). exit 5.
#   AF-AE-REQUIRED-MISSING       -> a required intake flag is absent or
#          empty on the payload (required_checker / attack_not_required).
#          exit 5.
#   AF-AE-READBACK-MISMATCH      -> the query-key fix PUT does not read
#          back byte-for-byte in the same job (query_key_fixer). exit 5.
#   AF-AE-PREFILL                -> the pre-fill hydration law drifted: the
#          served page differs between the bare and probe-param URLs, the
#          widget build no longer matches its committed baseline, or the
#          hydration code is absent (prefill_verifier). exit 5.
#   AF-AE-TEMPLATE-ATTACK        -> an attack fixture tripped the OFFLINE
#          self-test (also the family self-test batteries). exit 4.
#
# EXIT CODES (house convention 0/1/2/3/5; 4 = enforced violation; the
# primary surface the operator consumes is 0 = PASS, 2 = STOP, 5 = mismatch):
#   0  all checks PASS (also --dry-run plan pass and self-test pass)
#   1  unexpected error
#   2  STOP refusal — label NOT SET / non-pit- value / usage / the U04
#      check-module assembly incomplete (AF-AE-U04-ASSEMBLY-INCOMPLETE) /
#      a contract that cannot be read / a module STOP-family refusal
#   3  HELD — Convert and Flow unreachable / Cloudflare edge block / the
#      hosted-form page cannot be fetched (UNDETERMINED, never a verdict)
#   4  self-test FAILED — an assertion in the OFFLINE self-test tripped
#      (AF-AE-TEMPLATE-ATTACK family). A tamper NEVER masquerades as exit 1.
#   5  data or read-back mismatch (AF-AE-INTAKE-QUERY-KEY /
#      AF-AE-BRAND-LINK / AF-AE-REQUIRED-MISSING / AF-AE-PREFILL; also the
#      fail-closed default when any live check is DEFERRED without
#      --allow-deferred)
#
# MANIFEST-PENDING: after a PASSING run the tool writes
# manifest-pending/u04.json — the staged U04 manifest artifact (contract,
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
"""fix_intake_form.py — the U04 intake front-door fixer + verifier assembled
from the 16 u04_modules files: one CLI, offline self-test battery (golden
PASS / the three U04 attacks FAIL), JSON output, and the manifest-pending/
u04.json stage (Skill 59)."""

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
# Cloudflare browser-UA wiring + LeadConnector client and its label
# resolution is the house credential contract.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent
MODULES_DIR = Path(__file__).resolve().parent / "u04_modules"
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"
PENDING_DIR = SKILL_DIR / "manifest-pending"
PENDING_U04 = PENDING_DIR / "u04.json"

# The template location id is the CONTRACT's source_template_location (the
# operator's OWN template location, operator infrastructure config, not a
# secret). The verifier pins to it; --location-id overrides for tests.
DEFAULT_TEMPLATE_LOCATION = "2HIKGNgsixWx0yds7Qnx"

# THE SIXTEEN u04_modules FILES — the assembly manifest for this verifier.
# Every name is imported BY NAME below (importlib), never exec'd from a
# path; a missing module is a STOP, never a silent skip (the fail-closed
# import contract of main_skeleton.load_modules). `role` is the one-line
# contract each module owns.
U04_MODULES = (
    ("__init__.py",            "fail-closed EMPTY package init (pure namespace)"),
    ("main_skeleton.py",       "the check-module dispatcher CLI (plan / self-test / live verify)"),
    ("form_reader.py",         "live public-v2 forms listing read — find the universal author-intake form by slug / pin, report its ONE form id"),
    ("required_checker.py",    "the required-flags law applied to a payload (first_name / last_name / email, present and non-empty)"),
    ("brand_link_checker.py",  "the brand-surface legal-link gate (offline HTML scan; RFC 2606 placeholder hosts fail)"),
    ("query_key_checker.py",   "the G3 intake query-key gate (live public hosted-form page read, credential-free)"),
    ("query_key_fixer.py",     "the ONLY write surface — the G3 query-key fix via PUT /forms/{id}, REFUSED without its own --execute"),
    ("golden_ok.py",           "the golden ALREADY-COMPLIANT intake-form fixture (contract-derived, never a hardcoded list)"),
    ("attack_bad_query.py",    "the U04 ATTACK: the wrong query key (anthology_active_id) must FAIL every gate"),
    ("attack_example_dot_com.py", "the U04 ATTACK: an example.com legal link must FAIL every brand gate"),
    ("attack_not_required.py", "the U04 ATTACK: an intake payload with no email is REFUSED, never a clean read"),
    ("label_checker.py",       "the OFFLINE raw-key / warm-client-language map gate (no raw key on a client surface)"),
    ("prefill_verifier.py",    "the G3 VALUE-side gate — hidden-field pre-fill hydration (served-page identity + widget-build signature, credential-free)"),
    ("test_checkers.py",       "the independent pytest battery over the six public check surfaces"),
    ("test_prefill.py",        "the independent pytest battery over the prefill verifier"),
    ("docs_u04.py",            "the U04 README/catalog data + drift gate (the module inventory as DATA)"),
)

# The modules the dispatcher aggregates (main_skeleton.U04_MODULES — the
# check-module set named in the dispatcher's own roster; a check family
# that cannot prove itself offline STOPS).
DISPATCH_MODULE_NAMES = tuple(name for name, _ in (
    ("form_reader", "the public-v2 forms listing read (slug + pin law)"),
    ("required_checker", "the required-flags law (first_name / last_name / email)"),
    ("brand_link_checker", "the brand-surface legal-link gate (offline HTML scan)"),
    ("query_key_checker", "the G3 intake query-key gate (live hosted-form page)"),
    ("query_key_fixer", "the ONLY write surface (PUT /forms/{id}, REFUSED without --execute)"),
    ("golden_ok", "the golden ALREADY-COMPLIANT intake-form fixture"),
    ("attack_bad_query", "the U04 ATTACK: the wrong query key must FAIL"),
    ("attack_example_dot_com", "the U04 ATTACK: an example.com legal link must FAIL"),
    ("attack_not_required", "the U04 ATTACK: an intake payload with no email is REFUSED"),
    ("label_checker", "the OFFLINE raw-key / warm-client-language map gate "
                      "(no raw key leaks onto a client-facing surface)"),
    ("prefill_verifier", "the G3 VALUE-side gate — hidden-field pre-fill "
                         "hydration (served-page identity + widget-build "
                         "signature, credential-free)"),
    ("docs_u04", "the U04 README/catalog data + drift gate (the module "
                 "inventory as DATA)"),
))

# The modules that ship their OWN offline self-test battery (golden PASS /
# attack FAIL, exit 0 pass / 4 enforced violation). Every check module ships
# a battery — the dispatcher REQUIRES a battery from every module. The two
# pytest batteries are imported for their provenance; their tests run as the
# independent pytest battery.
SELF_TEST_MODULES = tuple(
    name[:-3] for name, _ in U04_MODULES
    if name not in ("__init__.py", "test_checkers.py", "test_prefill.py",
                    "main_skeleton.py"))
TEST_MODULES = ("test_checkers", "test_prefill")

# The four U04 verified items, as the manifest-pending stage records them
# (docs_u04.VERIFY_ITEMS — the catalog and the tree never drift).
VERIFIED_ITEMS = (
    (1, "form", "Universal author-intake form readable (slug + pin law)"),
    (2, "query_key", "G3 intake query key BYTE-EXACT 'anthology_id'"),
    (3, "required", "Required intake flags present and non-empty"),
    (4, "brand_links", "Brand legal links replacement-ready"),
)

# The AF-AE autofail family, as the stage records it.
AF_CODES = (
    ("AF-AE-U04-ASSEMBLY-INCOMPLETE", 2,
     "the U04 check-module set named in the assembly roster is not fully "
     "present, or a module violates the one-entry-point self_test contract — "
     "a check family is never silently skipped (dispatcher STOP)"),
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
    ("AF-AE-PREFILL", 5,
     "the pre-fill hydration law drifted: the served page differs between "
     "the bare and probe-param URLs, the widget build no longer matches its "
     "committed baseline, or the hydration code is absent "
     "(prefill_verifier)"),
    ("AF-AE-PIT-SCOPE", 2,
     "a genuine location-scope denial signature on the forms read — STOP, "
     "never mislabeled as an edge block (form_reader; already stamped in "
     "ENGINE-MANIFEST.json)"),
    ("AF-AE-TEMPLATE-ATTACK", 4,
     "an attack fixture tripped the OFFLINE self-test of the dispatcher or "
     "a family battery (enforced violation — the house code, shared with "
     "the U02 / U03 families)"),
)

# House exit-code contract (docs_u04.EXIT_CODES).
EXIT_CODES = {
    0: "verified success — all checks PASS (also plan / dry-run / self-test)",
    1: "unexpected error (top-level guard; never a secret leak)",
    2: "STOP refusal — label NOT SET / non-pit- value / usage / the U04 "
       "check-module assembly incomplete (AF-AE-U04-ASSEMBLY-INCOMPLETE) / "
       "a contract that cannot be read / a module STOP-family refusal",
    3: "HELD — Convert and Flow unreachable incl. the Cloudflare edge 403 "
       "(CF error 1010) / the hosted-form page cannot be fetched "
       "(UNDETERMINED, never a verdict)",
    4: "self-test FAILED (AF-AE-TEMPLATE-ATTACK / AF-AE-*-ATTACK family, "
       "enforced violation) — a tamper never masquerades as exit 1",
    5: "mismatch / fail-closed default — drift, a lookalike query key, a "
       "placeholder legal link, a missing required flag, a pre-fill "
       "signature drift, a read-back mismatch after the fix PUT, or a "
       "DEFERRED live read without --allow-deferred",
}

# The four contract custom-value keys (checked BY KEY; a value is never
# printed — the never-a-real-token rule).
CUSTOM_VALUE_KEYS = ("anthology_webhook_url", "anthology_hook_secret",
                     "producer", "producer_email")


class AssembleError(Exception):
    """A fail-closed refusal raised by the assembly itself — a missing
    u04_modules file, a module violating the entry-point contract, or a
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
# The 16-file assembly — import EVERY u04_modules file BY NAME. The empty
# package init is imported for the namespace guarantee (importing the
# package succeeds only if __init__.py is intact); the check modules come
# through main_skeleton.load_modules (the ONE entry-point contract); the
# fixture / checker / docs modules are imported for their surfaces and
# their self-test batteries; the two pytest batteries are imported for
# their provenance (their tests run as the independent pytest battery).
# ---------------------------------------------------------------------------
def _load_package() -> None:
    """Prove the package namespace container imports clean."""
    importlib.import_module("u04_modules")


def load_skeleton() -> object:
    """The main_skeleton dispatcher module (imported BY NAME)."""
    return importlib.import_module("u04_modules.main_skeleton")


def load_all_modules(out=None) -> dict:
    """Import every one of the 16 u04_modules files. Returns
    {name: module}. Fail-closed: a missing file or a module violating its
    contract raises AssembleError (STOP) — the aggregate NEVER passes with
    a module silently absent.

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
            modules[name] = importlib.import_module("u04_modules." + name)
        except ImportError:
            missing.append(name)
    for name in TEST_MODULES:
        try:
            modules[name] = importlib.import_module("u04_modules." + name)
        except ImportError:
            missing.append(name)
    if missing:
        raise AssembleError(
            "u04_modules file(s) not found: %s — the 16-file assembly is "
            "incomplete (fail-closed: no module is ever skipped)"
            % ", ".join(missing))
    if len(modules) != 15:
        raise AssembleError(
            "assembly loaded %d modules, expected 15 (main_skeleton + 9 "
            "dispatch modules + 3 checkers/fixtures/docs + 2 pytest "
            "batteries)" % len(modules))
    return modules


# ---------------------------------------------------------------------------
# Offline self-test — run EVERY module's own battery (golden PASS / the
# three U04 attacks FAIL), plus the main_skeleton dispatcher battery, plus
# this verifier's own assembly assertions, plus the two sibling pytest
# batteries. NO network, NO credentials. Exit 4 on any failure.
# ---------------------------------------------------------------------------
def _module_self_test(module, name: str, out) -> None:
    st = getattr(module, "self_test", None)
    if not callable(st):
        raise AssertionError(
            "module %s does not expose 'self_test' — every u04_modules "
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
    intake-family laws (checkers + the prefill verifier) are pinned offline.
    A failed battery is an enforced violation, never a silent skip."""
    pkg = Path(modules["test_checkers"].__file__).resolve().parent
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
    three U04 attacks MUST FAIL), the dispatcher battery, the assembly's
    file-count assertions, the intake-law gate (golden PASS / attacks FAIL
    / the not-required refusal), and the sibling pytest batteries. Any
    failure is exit 4 (AF-AE-TEMPLATE-ATTACK family) — a tamper NEVER
    masquerades as exit 1. On a clean pass the manifest-pending stage is
    written by the CLI."""
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        # 1. the assembly is complete: exactly the 16 files exist.
        on_disk = sorted(p.name for p in MODULES_DIR.glob("*.py"))
        expected = sorted(name for name, _ in U04_MODULES)
        assert on_disk == expected, (
            "u04_modules tree drifted: disk carries %d files, the 16-file "
            "assembly contract names %d (%s)"
            % (len(on_disk), len(expected),
               ", ".join(sorted(set(on_disk) ^ set(expected)))))
        # 2. every module's own battery passes (golden PASS / attack FAIL).
        for name in SELF_TEST_MODULES:
            _module_self_test(modules[name], name, dev)
        # 3. the dispatcher battery passes (main_skeleton.self_test runs the
        #    nine check modules through the one-entry-point contract and
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
        # 4. the intake-law gate, exercised through the modules' own
        #    surfaces — the GOLDEN states PASS and the THREE U04 ATTACKS
        #    FAIL (never a silent pass, never a blind refusal):
        # 4a. the golden compliant payload PASSES the required-flags law
        #     and the golden intake form carries the byte-exact query key.
        contract = _read_json(CONTRACT_PATH, "anthology-snapshot-contract.json")
        golden = modules["golden_ok"]
        rck = modules["required_checker"]
        qkc = modules["query_key_checker"]
        anr = modules["attack_not_required"]
        abq = modules["attack_bad_query"]
        aed = modules["attack_example_dot_com"]
        compl = golden.golden_compliant_payload(contract)
        required = list(rck.resolve_required_fields())
        assert required == ["first_name", "last_name", "email"], (
            "the required-fields law drifted from the U04 contract: %r"
            % required)
        # The golden payload nests the participant fields under the
        # "participant" container (the fixture's listing-row shape); the
        # required-flags law reads DIRECT keys / customData.* / contact.*
        # aliases (intake_router FIELD_ALIASES), never a "participant"
        # wrapper — so the smoke unwraps the fixture to the law's surface,
        # exactly as the live intake extractor's output is judged.
        law_payload = dict(compl.get("participant") or compl)
        report = rck.check_required(law_payload, required)
        assert report["ok"] is True, \
            "the golden compliant payload must pass: %r" % report["missing"]
        golden_form = golden.golden_form(contract)
        hidden = golden_form.get("hiddenFields") or golden_form.get(
            "hidden_fields") or []
        # The golden fixture's hidden-field container is a tuple of field
        # NAMES (the contract's universal hidden fields); the byte-exact
        # query-key law lives in the checkers (query_key_checker's golden
        # page, pinned to the SAME INTAKE_QUERY_KEY constant the minted link
        # rides) — the law is read from the owning module, never hardcoded
        # here.
        assert "anthology_id" in hidden, \
            "the golden intake form must carry the universal hidden fields"
        assert qkc._resolve_intake_key() == "anthology_id", \
            "the G3 intake query key drifted from anthology_book"
        # 4b. ATTACK 1 — the wrong query key (anthology_active_id) FAILS
        #     the query-key gate AND the attack fixture's own fail-closed
        #     surface refuses it (AF-AE-ATTACKBADQUERY family). The law is
        #     read from the owning modules: the LOOKALIKE key from
        #     query_key_checker (the same constant its gate refuses), the
        #     wrong-key link from attack_bad_query's OWN attacker (the same
        #     authority the minted link rides).
        assert qkc.LOOKALIKE_QUERY_KEY == "anthology_active_id", \
            "the lookalike key drifted from the G3 contract"
        attack_page = qkc.parse_form_fields(
            qkc._golden_page(field=qkc.LOOKALIKE_QUERY_KEY))
        qk_report = qkc.check_query_key(attack_page)
        assert qk_report["ok"] is False, \
            "ATTACK 1 (wrong query key) was NOT failed by the query-key gate"
        assert abq.ATTACK_QUERY_KEY == qkc.LOOKALIKE_QUERY_KEY, \
            "the attack fixture and the gate disagree on the wrong key"
        rc = abq.verify_live(abq.ATTACK_LINK, out=io.StringIO())
        assert rc == EX_MISMATCH, \
            "ATTACK 1 (wrong query key) was NOT refused (exit %s)" % rc
        rc = abq.verify_live(abq.GOLDEN_LINK, out=io.StringIO())
        assert rc == EX_OK, \
            "the golden one-key control link must PASS the judge (exit %s)" % rc
        # 4c. ATTACK 2 — an example.com legal link FAILS the brand gate AND
        #     the attack fixture's own fail-closed surface refuses it
        #     (AF-AE-ATTACKEXAMPLEDOTCOM family). The law is read from the
        #     owning modules: the attack host from the fixture's own
        #     attacker, the judge from the fixture's own fail-closed surface,
        #     the golden real-host control from the fixture (the pass side of
        #     the split — a gate that fails everything is a broken
        #     instrument).
        blc = modules["brand_link_checker"]
        assert aed.ATTACK_HOST == "example.com", \
            "the example.com attack host drifted from the fixture"
        assert aed.GOLDEN_HOST != aed.ATTACK_HOST, \
            "the golden host conflated with the adversarial host"
        legal = ("<html><body><footer><a href=\"%s\">Privacy Policy</a>"
                 "</footer></body></html>" % aed.ATTACK_LINK)
        brand_report = blc.check_html(legal.encode("utf-8"), "attack-2")
        assert brand_report["ok"] is False, \
            "ATTACK 2 (example.com legal link) was NOT failed by the brand gate"
        rc = aed.verify_live(aed.ATTACK_LINK, out=io.StringIO())
        assert rc == EX_MISMATCH, \
            "ATTACK 2 (example.com legal link) was NOT refused (exit %s)" % rc
        rc = aed.verify_live(aed.GOLDEN_LINK, out=io.StringIO())
        assert rc == EX_OK, \
            "the golden real-host control link must PASS the judge (exit %s)" % rc
        # 4d. ATTACK 3 — an intake payload with email ABSENT / EMPTY /
        #     whitespace-only / non-string is REFUSED by the required-flags
        #     gate (NotRequiredError, the STOP family), never a clean read
        #     (AF-AE-REQUIRED-ATTACK family).
        for mutation in (
                {"email": None}, {"email": ""}, {"email": "   "},
                {"email": 42}, {"email": []}, {"email": "not-an-email"}):
            payload = dict(compl)
            payload.update(mutation)
            if mutation == {"email": None}:
                payload.pop("email")
            try:
                anr.verify(payload, required)
                raise AssertionError(
                    "ATTACK 3 (email %r) was NOT refused by the required "
                    "gate" % mutation)
            except anr.NotRequiredError:
                pass
        rc = anr.payload(dict(compl, email=""), out=io.StringIO())
        assert rc == EX_MISMATCH, \
            "ATTACK 3 (empty email payload) was NOT refused (exit %s)" % rc
        # 5. the never-a-real-token classifier (query_key_fixer refuses a
        #    credential-shaped query key — the plan surface is scanned, and
        #    an idempotent no-op never writes, even with --execute).
        qkf = modules["query_key_fixer"]
        assert qkf._CREDENTIAL_SHAPE.search("pit-abc123") is not None, \
            "the credential shape regex drifted from the pit- law"
        assert qkf.QUERY_KEY_LAW == "anthology_id", \
            "the G3 query-key law drifted from the U04 contract"
        # 6. docs_u04's catalog is the assembly's catalog (4 items, 12
        #    modules in its inventory, exit codes 0..5, 11 af codes — its
        #    self-test already pinned the counts; here we pin the shared
        #    constants).
        docs = modules["docs_u04"]
        assert len(docs.verify_items()) == len(VERIFIED_ITEMS), \
            "docs_u04 item count drifted from the assembly's VERIFIED_ITEMS"
        assert docs.U04_VERIFIER == "main_skeleton.py", \
            "docs_u04 verifier pointer drifted"
        assert docs.U04_TEMPLATE_LOCATION == DEFAULT_TEMPLATE_LOCATION, \
            "docs_u04 template location drifted from the assembly pin"
        # 7. the sibling pytest batteries (the independent proof).
        if run_pytest:
            _run_pytest(modules, dev)
    except AssertionError as exc:
        sys.stderr.write("[fix-intake-form] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    except AssembleError as exc:
        sys.stderr.write("[fix-intake-form] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION

    out.write(dev.getvalue())
    out.write("[fix-intake-form] assembled self-test: OK (16 u04_modules "
              "files imported, 13 module batteries + dispatcher battery + "
              "intake-law gate with the 3 U04 attacks REFUSED + %s + "
              "assembly assertions all pass)\n"
              % ("2 pytest batteries" if run_pytest else
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
            pinned_id: str, out=None) -> int:
    out = out or sys.stderr
    skeleton = modules["main_skeleton"]
    # The dispatcher's own plan (the ONE JSON object on stdout, captured
    # into the human channel — the machine surface is this assembler's plan
    # object, so stdout stays ONE JSON document).
    with _redirect_stdout(io.StringIO()):
        rc = skeleton.plan(modules, location_id, contract, pinned_id,
                           out=out)
    if rc != EX_OK:
        return rc
    print(json.dumps({
        "contract": "anthology-engine-u04-dispatch-plan",
        "schema_version": 1,
        "kind": "dry-run",
        "template_location_id": location_id,
        "template_location_id_masked": _mask_id(location_id),
        "pinned_form_id_masked": _mask_id(pinned_id) if pinned_id else "",
        "gates": [name for name, _ in skeleton.LIVE_GATES],
        "modules": [name for name, _ in U04_MODULES],
        "dry_run": True,
        "note": "offline plan only — no network, no credential needed; a "
                "LIVE read must ride reg.CafClient / query_key_checker's "
                "fetch (CAF_BROWSER_UA on every request — CF 1010 law); the "
                "fixer writes ONLY with its own --execute",
    }, indent=2, sort_keys=True))
    out.write("[fix-intake-form] dry-run plan: OK (offline — no network, "
              "no credential needed)\n")
    return EX_OK


def _mask_id(fid: str) -> str:
    """Mask a form / location id for every operator surface — a location
    identifier, not a secret, but never printed in full (house pattern,
    mirrored from form_reader.mask_id)."""
    fid = (fid or "").strip()
    if len(fid) <= 8:
        return "***"
    return "%s***%s" % (fid[:4], fid[-4:])


# ---------------------------------------------------------------------------
# Live verify — the dispatcher's fail-closed aggregate over the four gates
# in the FIXED order, with the READ probe first. Any FAIL -> exit 5; a
# STOP-family refusal propagates as exit 2; a transport / edge failure is
# HELD (exit 3), never mislabeled as scope. The brand gate is DEFERRED (no
# page inputs wired — never fabricated) and keeps the exit at 5 unless
# --allow-deferred. This assembler NEVER invokes the fixer and NEVER
# writes — the ONLY write surface is query_key_fixer.py's own CLI with
# --execute.
# ---------------------------------------------------------------------------
def verify_live(modules: dict, location_id: str, contract: dict,
                pinned_id: str, *, allow_deferred: bool = False,
                out=None) -> int:
    out = out or sys.stderr
    skeleton = modules["main_skeleton"]

    # READ probe FIRST: a token that cannot READ the template location STOPS
    # (AF-AE-PIT-SCOPE family) instead of a mid-verify surprise.
    pit_label, token = reg.resolve_pit()
    if not token:
        checked = ", ".join(reg.PIT_LABELS)
        reg._stop(out, "No Convert and Flow private-integration token is SET.",
                  ["Checked (in order): %s — all NOT SET." % checked,
                   "The verify runs against the operator's OWN template "
                   "location %s; set the template PIT (client-standard "
                   "labels first) and re-run." % _mask_id(location_id)])
        return EX_STOP
    client = reg.CafClient(token)
    try:
        probe = client._request(
            "GET", modules["form_reader"].FORMS_LIST_PATH,
            query={"locationId": location_id, "limit": 200})
    except reg.ScopeDenied as exc:
        reg._stop(out, "The Convert and Flow token lacks READ scope on the template location.",
                  [str(exc), "Grant the template PIT the forms READ scope and re-run."])
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        out.write("[fix-intake-form] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        out.write("[fix-intake-form] HELD: %s\n" % exc)
        return EX_HELD

    return skeleton.verify_live(modules, client, location_id, contract,
                                pinned_id, allow_deferred=allow_deferred,
                                out=out)


# ---------------------------------------------------------------------------
# Manifest-pending stage — manifest-pending/u04.json. Written ONLY after a
# PASS (self-test pass or dry-run plan pass); a FAIL/HELD/STOP run writes
# nothing. The record is the machine-readable input to a later manifest
# re-stamp — the ENGINE-MANIFEST.json / ENGINE-PIN.sha256 / verify.sh are
# NEVER touched here.
# ---------------------------------------------------------------------------
def _pending_payload(kind: str, location_id: str, *,
                     verdict: str = "PASS") -> dict:
    return {
        "contract": "anthology-engine-u04-intake-form",
        "schema_version": 1,
        "kind": kind,  # "self-test" | "dry-run" | "verify"
        "verdict": verdict,
        "script": "fix_intake_form.py",
        "authored_by": "U04",
        "template_location_id": location_id,
        "u04_modules": [
            {"name": name, "role": role} for name, role in U04_MODULES
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
        "custom_value_keys": list(CUSTOM_VALUE_KEYS),
        "checks": {},
        "fail_closed": {
            "any_fail": False,
            "note": "the dispatcher's brand gate is DEFERRED (no brand HTML "
                    "page paths wired — never fabricated) and counts as FAIL "
                    "unless --allow-deferred; the fixer (query_key_fixer.py) "
                    "is the ONLY write surface and REFUSES without its own "
                    "--execute — this assembler never writes.",
        },
    }


def write_pending(payload: dict, *, mode: str = "self-test", out=None) -> None:
    """Write manifest-pending/u04.json (fail-closed: only after a PASS).

    The directory is created if absent; the file is written atomically
    (temp + rename) so a crash mid-write never leaves a partial stage. The
    ENGINE-MANIFEST.json / ENGINE-PIN.sha256 / verify.sh are NEVER touched."""
    out = out or sys.stderr
    try:
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        tmp = PENDING_DIR / ("u04.json.tmp-%d" % os.getpid())
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
        tmp.replace(PENDING_U04)
    except OSError as exc:
        raise AssembleError("cannot write %s: %s" % (PENDING_U04, exc)) from exc
    out.write("[fix-intake-form] manifest-pending stage written: %s (%s)\n"
              % (PENDING_U04, mode))


# ---------------------------------------------------------------------------
# CLI — house shape: --dry-run / --self-test / --json accepted as flags AND
# as a positional subcommand (--self-test / --selftest normalize exactly as
# anthology_registry.py, u02_modules/main_skeleton.py, and
# u03_modules/main_skeleton.py).
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="fix_intake_form.py",
        description="The U04 intake front-door fixer + verifier assembled "
                    "from the 16 u04_modules files: offline self-test "
                    "battery (golden PASS / the three U04 attacks FAIL), "
                    "offline plan, and live verify of the universal "
                    "author-intake form on the Anthology Convert and Flow "
                    "TEMPLATE location (Skill 59) — every delta documented "
                    "as JSON, the manifest-pending stage written after a "
                    "PASS. The ONLY write surface is query_key_fixer.py's "
                    "own CLI with --execute; this tool never writes.")
    ap.add_argument("--location-id", default="",
                    help="override the template location id (default: the "
                         "contract's source_template_location."
                         "template_location_id, %s; never printed)"
                         % DEFAULT_TEMPLATE_LOCATION)
    ap.add_argument("--form-id", default="",
                    help="the pinned universal-intake form id (default: the "
                         "engine fleet value, imported from form_reader; "
                         "masked on every surface; a pinned id absent from "
                         "the listing is a MISMATCH)")
    ap.add_argument("--allow-deferred", action="store_true",
                    help="explicit operator opt-in: accept a DEFERRED live "
                         "read (brand pages not wired) as PASS — the report "
                         "still records the deferral")
    ap.add_argument("--field-map", default=str(FIELD_MAP_PATH),
                    help="path to field-map.json (source of truth for the "
                         "byte-exact gate)")
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
                    help="run the offline self-test (golden PASS / the three "
                         "U04 attacks FAIL + the dispatcher battery + the "
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
        pinned_id = (args.form_id.strip() or
                     (contract.get("forms") or {}).get("universal_intake_form_id") or
                     modules["form_reader"].DEFAULT_UNIVERSAL_INTAKE_FORM_ID)

        if args.dry_run:
            rc = dry_run(modules, location_id, contract, pinned_id,
                         out=sys.stderr)
            if rc == EX_OK:
                write_pending(_pending_payload("dry-run", location_id),
                              mode="dry-run")
            return rc

        rc = verify_live(modules, location_id, contract, pinned_id,
                         allow_deferred=args.allow_deferred,
                         out=sys.stderr)
        if rc == EX_OK:
            write_pending(_pending_payload("verify", location_id),
                          mode="verify")
        return rc

    except reg.ScopeDenied as exc:
        sys.stderr.write("[fix-intake-form] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[fix-intake-form] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[fix-intake-form] HELD: %s\n" % exc)
        return EX_HELD
    except AssembleError as exc:
        sys.stderr.write("[fix-intake-form] STOP/FAIL: %s\n" % exc)
        return EX_STOP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[fix-intake-form] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
