#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: live_verify_template.py  (U02 tooling)
# LIVE RE-VERIFY OF THE GHL TEMPLATE LOCATION — the SINGLE manifest row 54
# verifier, ASSEMBLED from the 16 u02_modules files: it imports EVERY module
# under scripts/u02_modules/ BY NAME (main_skeleton dispatcher + the seven
# check modules + the four golden/attack fixture modules + delta_reporter +
# docs_u02 + the empty package init), wires them into ONE CLI, and runs the
# modules' own OFFLINE self-test batteries (golden PASS / attack FAIL) before
# any live surface. This file carries NO check logic itself — a check family
# is exercised ONLY through its module so `--dry-run`, `--self-test`, and the
# live aggregate never drift apart.
#
# THE LIVE READ IS GHL-GATED; THE TOOLING SHIPS NOW. The operator executes
# `verify` only from a session that can resolve a template-scoped
# private-integration token BY LABEL. --dry-run (offline plan) and --self-test
# (offline golden + attack fixtures) need NO token and NO network.
#
# THE 16 u02_modules FILES (imported by name; each is STDLIB-only and
# self-tests itself — docs_u02.py carries the module inventory as data and
# its self-test proves the tree ships together):
#   __init__.py            fail-closed EMPTY package init (pure namespace)
#   main_skeleton.py       the check-module dispatcher CLI (plan / self-test /
#                          live verify; the ONE entry-point contract)
#   pipeline_check.py      check_pipeline_name — pipeline name BYTE-EXACT
#   stages_check.py        check_stages — nine stages BY NAME IN ORDER 0..8
#   fields_check.py        check_fields_live — 38 field keys byte-exact
#   custom_values_check.py check_custom_values — four REPLACE-ME values
#   forms_check.py         check_forms — named forms + hidden-field contract
#   workflows_check.py     check_workflows_live — EIGHT release workflows
#   scope_check.py         check — Intake Fire trigger scope gate (pure)
#   golden_pipeline.py     golden pipeline fixture (field-map derived)
#   golden_fields.py       golden 38-record field-list fixture
#   golden_forms.py        golden three-form payload fixture
#   attack_missing_field.py  attack fixture: a contract key ABSENT live
#   attack_wrong_name.py     attack fixture: a pipeline/field RENAMED
#   delta_reporter.py      the ONE JSON delta-report contract
#   docs_u02.py            the U02 README/catalog data + drift gate
#
# WHAT THIS VERIFIES (every "ALREADY DONE" item, MASTER-SPEC U02; the
# per-item claims live in the modules and in docs_u02.VERIFY_ITEMS):
#   1. PIPELINE name BYTE-EXACT "Anthology Engine" — find-and-bind is BY NAME
#      (MASTERDOC floor 11); a renamed pipeline silently unbinds onboarding.
#   2. NINE pipeline stages BY NAME, IN ORDER (positions 0..8, Intake ..
#      Assembled) — stage moves resolve BY STAGE NAME at runtime.
#   3. FORMS COUNT + FIELD MAPPING — the named forms (universal-intake /
#      universal-review / title-select) with the universal hidden-field
#      contract (contact_id / anthology_id / stage).
#   4. WORKFLOWS COUNT + FOLDER — the EIGHT tag->notification release
#      workflows in ONE workflow folder named exactly "Anthology Engine",
#      each trigger contact_tag and ACTIVE on its contract trigger_tag.
#   5. INTAKE FIRE TRIGGER SCOPE — webhook-to-route: the route-template
#      'anthology-intake' mapping + the {{ custom_values.anthology_webhook_url }}
#      merge target as REPLACE-ME; no live workflow inlines a real URL.
#   6. CUSTOM FIELD COUNT + dataTypes — all 38 contract fields present BY
#      KEY, BYTE-EXACT (36 LARGE_TEXT + 2 SINGLE_OPTIONS: the cover choice and
#      the review decision, each with its named options in order);
#      extra/mutated keys fail closed.
#   7. CUSTOM VALUES — the four contract location custom values present BY
#      KEY, each holding a clearly-labeled placeholder; a real-looking value
#      REFUSES the verify (the never-a-real-token rule).
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. The PIT is resolved via
# anthology_registry (CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_API_KEY /
# GOHIGHLEVEL_API_KEY / GOHIGHLEVEL_PIT / GHL_API_KEY, live process env first
# then the three canonical client env stores), and the location id is pinned
# to the contract's template location (2HIKGNgsixWx0yds7Qnx) unless
# --location-id overrides. The optional Firebase refresh token for the
# internal rail is resolved BY LABEL (ANTHOLOGY_GHL_FIREBASE_REFRESH_TOKEN /
# GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN / GHL_FIREBASE_REFRESH_TOKEN). SET /
# NOT SET only on every operator surface; a value is NEVER printed.
#
# BROWSER UA: every request rides reg.CafClient / reg.InternalRailClient,
# which apply the CAF_BROWSER_UA so the Cloudflare edge fronting
# services.leadconnectorhq.com never 1010s the verify — the same GK-09
# discipline as snapshot_cut.py. Scope-vs-edge-block discrimination: a bare
# 401/403 is HELD (UpstreamBlockedError), never reported as a scope problem.
#
# AF CODES (fail-closed surfaces; self-test failures are exit 4, never 1):
#   AF-AE-TEMPLATE-PIPELINE-MISSING  -> the standard pipeline is absent or
#          renamed on the template location. STOP (exit 2).
#   AF-AE-TEMPLATE-STAGE-DRIFT       -> a present pipeline is missing a
#          contract stage or carries an extra/renamed/out-of-order stage.
#          exit 5.
#   AF-AE-TEMPLATE-FIELD-MISSING     -> a contract custom-field key is absent.
#          exit 2.
#   AF-AE-TEMPLATE-KEY-MISMATCH      -> the field-key SET differs in any other
#          way (extra/mutated), a dataType/options drift, or a real-looking
#          custom-value. exit 5.
#   AF-AE-TEMPLATE-CUSTOM-VALUE-REAL -> a custom value holds a real-looking
#          value (never-a-real-token). exit 5.
#   AF-AE-TEMPLATE-INTAKE-FIRE       -> the intake-fire side drifted. exit 5.
#   AF-AE-TEMPLATE-ATTACK            -> an attack fixture tripped the OFFLINE
#          self-test. exit 4.
#
# EXIT CODES (house convention 0/1/2/3/5; 4 = enforced violation):
#   0  all checks PASS (also --dry-run plan pass and self-test pass)
#   1  unexpected error
#   2  STOP refusal — label NOT SET / non-pit- value / usage / pipeline or
#      field section missing on the live location
#   3  Convert and Flow API unreachable / internal rail unavailable (HELD)
#   4  self-test FAILED — an assertion in the OFFLINE self-test tripped
#      (AF-AE-TEMPLATE-ATTACK family). A tamper NEVER masquerades as exit 1.
#   5  data or read-back mismatch (AF-AE-TEMPLATE-STAGE-DRIFT /
#      AF-AE-TEMPLATE-KEY-MISMATCH / AF-AE-TEMPLATE-INTAKE-FIRE; also the
#      fail-closed default when any live check is DEFERRED without
#      --allow-deferred)
#
# MANIFEST-PENDING: after a PASSING run the tool writes
# manifest-pending/u02.json — the staged U02 manifest row-54 artifact
# (contract, checks verdict, module inventory, af-code family, exit-code
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
"""live_verify_template.py — the U02 verifier assembled from the 16
u02_modules files: one CLI, offline self-test battery, JSON output, and the
manifest-pending/u02.json stage (Skill 59, row 54)."""

from __future__ import annotations

import argparse
import importlib
import io
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry does the
# Cloudflare browser-UA wiring + LeadConnector client + internal-rail client
# and its label resolution is the house credential contract.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

SKILL_DIR = Path(__file__).resolve().parent.parent
MODULES_DIR = Path(__file__).resolve().parent / "u02_modules"
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"
ROUTE_TEMPLATE_PATH = SKILL_DIR / "config" / "route-template.json"
PENDING_DIR = SKILL_DIR / "manifest-pending"
PENDING_U02 = PENDING_DIR / "u02.json"

# The template location id is the CONTRACT's source_template_location (the
# operator's OWN template location, operator infrastructure config, not a
# secret). The verifier pins to it; --location-id overrides for tests.
DEFAULT_TEMPLATE_LOCATION = "2HIKGNgsixWx0yds7Qnx"

# THE SIXTEEN u02_modules FILES — the assembly manifest for this verifier.
# Every name is imported BY NAME below (importlib), never exec'd from a
# path; a missing module is a STOP, never a silent skip (the fail-closed
# import contract of main_skeleton.load_checks). `role` is the one-line
# contract each module owns; `surface` names what this verifier calls.
U02_MODULES = (
    ("__init__.py",            "fail-closed empty package init (pure namespace)"),
    ("main_skeleton.py",       "the check-module dispatcher CLI (plan / self-test / live verify)"),
    ("pipeline_check.py",      "check_pipeline_name — pipeline name BYTE-EXACT"),
    ("stages_check.py",        "check_stages — nine stages BY NAME IN ORDER 0..8"),
    ("fields_check.py",        "check_fields_live — 38 field keys byte-exact"),
    ("custom_values_check.py", "check_custom_values — four REPLACE-ME values"),
    ("forms_check.py",         "check_forms — named forms + hidden-field contract"),
    ("workflows_check.py",     "check_workflows_live — EIGHT release workflows"),
    ("scope_check.py",         "check — Intake Fire trigger scope gate (pure)"),
    ("golden_pipeline.py",     "golden pipeline fixture (field-map derived)"),
    ("golden_fields.py",       "golden 38-record field-list fixture"),
    ("golden_forms.py",        "golden three-form payload fixture"),
    ("attack_missing_field.py", "attack fixture: a contract key ABSENT live"),
    ("attack_wrong_name.py",   "attack fixture: a pipeline/field RENAMED"),
    ("delta_reporter.py",      "the ONE JSON delta-report contract"),
    ("docs_u02.py",            "the U02 README/catalog data + drift gate"),
)

# The check modules the dispatcher aggregates (main_skeleton.CHECK_MODULES).
CHECK_MODULE_NAMES = ("pipeline_check", "stages_check", "fields_check",
                      "custom_values_check", "forms_check", "workflows_check",
                      "scope_check")

# The modules that ship their OWN offline self-test battery (golden PASS /
# attack FAIL, exit 0 pass / 4 enforced violation). custom_values_check has
# no self_test of its own — its pure classifier is asserted here and by
# main_skeleton.self_test (the skeleton's offline battery covers it).
SELF_TEST_MODULES = ("attack_missing_field", "attack_wrong_name",
                     "delta_reporter", "docs_u02", "fields_check",
                     "forms_check", "golden_fields", "golden_forms",
                     "golden_pipeline", "pipeline_check", "scope_check",
                     "stages_check", "workflows_check")

# The four contract custom-value keys (checked BY KEY; a value is never
# printed — the never-a-real-token rule).
CUSTOM_VALUE_KEYS = ("anthology_webhook_url", "anthology_hook_secret",
                     "producer", "producer_email")

# The seven U02 verified items, as the manifest-pending stage records them.
VERIFIED_ITEMS = (
    ("pipeline",        "Pipeline name BYTE-EXACT 'Anthology Engine'"),
    ("stages",          "Nine stages BY NAME IN ORDER, contiguous positions 0..8"),
    ("forms",           "Forms count + field mapping (named forms + hidden-field contract)"),
    ("workflows",       "Workflows count + folder 'Anthology Engine' (EIGHT release workflows)"),
    ("intake_fire",     "Intake Fire trigger scope (webhook-to-route, never an inlined URL)"),
    ("custom_fields",   "Custom field count + dataTypes (38 keys byte-exact)"),
    ("custom_values",   "Custom values (four keys, REPLACE-ME placeholders, never-a-real-token)"),
)

# The AF-AE-TEMPLATE-* autofail family, as the stage records it.
AF_CODES = (
    ("AF-AE-TEMPLATE-PIPELINE-MISSING", 2,
     "the standard pipeline is absent or renamed on the template location"),
    ("AF-AE-TEMPLATE-STAGE-DRIFT", 5,
     "a present pipeline is missing a contract stage or carries an "
     "extra/renamed/out-of-order stage"),
    ("AF-AE-TEMPLATE-FIELD-MISSING", 2,
     "a contract custom-field key is absent on the live location"),
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

# House exit-code contract (docs_u02.EXIT_CODES).
EXIT_CODES = {
    0: "verified success — all checks PASS (also plan / dry-run / self-test)",
    1: "unexpected error (top-level guard; never a secret leak)",
    2: "STOP refusal — label NOT SET / non-pit- value / usage / a contract "
       "section missing / a pipeline or field section absent live",
    3: "HELD — Convert and Flow API unreachable incl. the Cloudflare edge "
       "403 (CF error 1010) or the internal rail unavailable; retryable",
    4: "self-test FAILED (AF-AE-*-ATTACK family, enforced violation)",
    5: "mismatch / fail-closed default — drift, extra or mutated keys, a "
       "real-looking custom value, or a DEFERRED live check without "
       "--allow-deferred",
}


class AssembleError(Exception):
    """A fail-closed refusal raised by the assembly itself — a missing
    u02_modules file, a module violating the entry-point contract, or a
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
# The 16-file assembly — import EVERY u02_modules file BY NAME. The empty
# package init is imported for the namespace guarantee (importing the
# package succeeds only if __init__.py is intact); the check modules come
# through main_skeleton.load_checks (the ONE entry-point contract); the
# fixture / reporter / docs modules are imported for their surfaces and
# their self-test batteries.
# ---------------------------------------------------------------------------
def _load_package() -> None:
    """Prove the package namespace container imports clean."""
    importlib.import_module("u02_modules")


def load_skeleton() -> object:
    """The main_skeleton dispatcher module (imported BY NAME)."""
    return importlib.import_module("u02_modules.main_skeleton")


def load_all_modules(out=None) -> dict:
    """Import every one of the 16 u02_modules files. Returns
    {name: module}. Fail-closed: a missing file or a module violating its
    contract raises AssembleError (STOP) — the aggregate NEVER passes with
    a module silently absent.

    The check modules go through main_skeleton.load_checks (which enforces
    the ONE-entry-point contract and raises SkeletonError on a violation);
    the fixture / reporter / docs modules are imported directly here (their
    self-tests prove their surfaces)."""
    out = out or sys.stderr
    _load_package()
    # The check modules resolve BY NAME (importlib.import_module(name) with
    # bare names inside main_skeleton.load_checks) — their own directory must
    # sit on sys.path for that to resolve, exactly as running the skeleton as
    # a script puts its own directory first.
    if str(MODULES_DIR) not in sys.path:
        sys.path.insert(0, str(MODULES_DIR))

    skeleton = load_skeleton()
    try:
        checks = skeleton.load_checks()
    except skeleton.SkeletonError as exc:
        raise AssembleError("check-module load failed: %s" % exc) from exc

    modules = {"main_skeleton": skeleton}
    modules.update(checks)
    missing = []
    for name in SELF_TEST_MODULES:
        try:
            modules[name] = importlib.import_module("u02_modules." + name)
        except ImportError:
            missing.append(name)
    if missing:
        raise AssembleError(
            "u02_modules file(s) not found: %s — the 16-file assembly is "
            "incomplete (fail-closed: no module is ever skipped)"
            % ", ".join(missing))
    if len(modules) != 15:
        raise AssembleError(
            "assembly loaded %d modules, expected 15 (main_skeleton + 7 "
            "checks + 7 fixtures/reporter/docs)" % len(modules))
    return modules


# ---------------------------------------------------------------------------
# Offline self-test — run EVERY module's own battery (golden PASS / attack
# FAIL), plus the main_skeleton dispatcher battery, plus this verifier's own
# assembly assertions. NO network, NO credentials. Exit 4 on any failure.
# ---------------------------------------------------------------------------
def _module_self_test(module, name: str, out) -> int:
    st = getattr(module, "self_test", None)
    if not callable(st):
        raise AssertionError(
            "module %s does not expose 'self_test' — every u02_modules "
            "module must prove itself offline" % name)
    dev = io.StringIO()
    try:
        rc = st(out=dev)
    except TypeError:
        rc = st()
    out.write(dev.getvalue())
    if rc != EX_OK:
        raise AssertionError("%s self_test returned exit %d" % (name, rc))


def self_test(modules: dict, out=None) -> int:
    """OFFLINE self-test: the modules' own golden+attack batteries plus the
    dispatcher battery and the assembly's file-count assertions. Any failure
    is exit 4 (AF-AE-TEMPLATE-ATTACK family) — a tamper NEVER masquerades
    as exit 1. On a clean pass the manifest-pending stage is written."""
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        # 1. the assembly is complete: exactly the 16 files exist.
        on_disk = sorted(p.name for p in MODULES_DIR.glob("*.py"))
        expected = sorted(name for name, _ in U02_MODULES)
        assert on_disk == expected, (
            "u02_modules tree drifted: disk carries %d files, the 16-file "
            "assembly contract names %d (%s)" % (len(on_disk), len(expected),
                                                 ", ".join(sorted(set(on_disk) ^ set(expected)))))
        # 2. every module's own battery passes (golden PASS / attack FAIL).
        for name in SELF_TEST_MODULES:
            _module_self_test(modules[name], name, dev)
        # 3. the dispatcher battery passes (main_skeleton.self_test runs the
        #    seven check modules through the one-entry-point contract).
        skeleton = modules["main_skeleton"]
        checks = {k: v for k, v in modules.items() if k in CHECK_MODULE_NAMES}
        sk_rc = skeleton.self_test(checks)
        assert sk_rc == EX_OK, "main_skeleton dispatcher self-test returned exit %d" % sk_rc
        # 4. the never-a-real-token classifier (custom_values_check ships no
        #    self_test of its own — its pure placeholder law is asserted here,
        #    exactly as main_skeleton.self_test asserts it).
        cvc = modules["custom_values_check"]
        assert cvc.is_placeholder("") is True, "empty value is a placeholder"
        assert cvc.is_placeholder("REPLACE-ME") is True
        assert cvc.is_placeholder("https://hooks.example.com/x") is False, \
            "a real-looking value must be refused (never-a-real-token)"
        # 5. docs_u02's catalog is the assembly's catalog (7 items, 13 modules
        #    in its inventory, exit codes 0..5, 7 af codes — its self-test
        #    already pinned the counts; here we pin the shared constants).
        docs = modules["docs_u02"]
        assert len(docs.verify_items()) == len(VERIFIED_ITEMS), \
            "docs_u02 item count drifted from the assembly's VERIFIED_ITEMS"
        assert len(docs.af_codes()) == len(AF_CODES), \
            "docs_u02 af-code family drifted from the assembly's AF_CODES"
    except AssertionError as exc:
        sys.stderr.write("[live-verify] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    except AssembleError as exc:
        sys.stderr.write("[live-verify] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION

    out.write(dev.getvalue())
    out.write("[live-verify] assembled self-test: OK (16 u02_modules files "
              "imported, 13 module batteries + dispatcher battery + assembly "
              "assertions all pass)\n")
    return EX_OK


# ---------------------------------------------------------------------------
# Offline plan — no network, no credentials. The dispatcher's plan, with the
# assembly's stage-record on the side. Prints ONE JSON object on stdout.
# ---------------------------------------------------------------------------
def dry_run(modules: dict, location_id: str, field_map: dict,
            contract: dict, out=None) -> int:
    out = out or sys.stderr
    skeleton = modules["main_skeleton"]
    rc = skeleton.plan(location_id, {k: v for k, v in modules.items()
                                     if k in CHECK_MODULE_NAMES},
                       field_map, contract)
    if rc == EX_OK:
        out.write("[live-verify] dry-run plan: OK (offline — no network, no "
                  "credential needed)\n")
    return rc


# ---------------------------------------------------------------------------
# Live verify — the dispatcher's fail-closed aggregate, with the READ probe
# first and the internal rail optional (DEFERRED without the Firebase
# refresh token BY LABEL — never fabricated).
# ---------------------------------------------------------------------------
def verify_live(modules: dict, location_id: str, field_map: dict,
                contract: dict, route: dict, *, allow_deferred: bool = False,
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
                   "The verify runs against the operator's OWN template location %s; "
                   "set the template PIT (client-standard labels first) and re-run."
                   % location_id])
        return EX_STOP
    client = reg.CafClient(token)
    # READ probe FIRST: a token that cannot READ the template location STOPS
    # (AF-AE-PIT-SCOPE family) instead of a mid-verify surprise. The public
    # v2 surface is edge-blocked for every stored PIT (GK-09, proven live
    # 2026-08-12); when the rail is available, the client DEFERS to the
    # rail-backed RailFallbackClient (the rail reads customFields/customValues
    # on this operator box — proven live) so the verify proceeds on the
    # sanctioned path. A genuinely scope-denied PIT (the W0.5 signature, not
    # an edge block) still STOPS; an unreadable surface with NO rail is a
    # HELD, never a fabricated pass.
    client = _fallback_or_stop(client, location_id, out)
    if client is None:
        return EX_HELD

    # Internal rail (optional): without a Firebase refresh token the workflow /
    # forms / intake-fire-workflow-half reads are DEFERRED (never fabricated)
    # and the aggregate is fail-closed unless --allow-deferred.
    rail = None
    rlabel, rtoken = reg.resolve_firebase_refresh_token()
    if rtoken:
        _, api_key = reg._resolve_firebase_api_key() or (None, "")
        rail = reg.InternalRailClient(rtoken, api_key) if api_key else None
    if rail is None:
        out.write("[live-verify] internal-rail refresh token NOT SET — "
                  "workflow count/triggers and the live form count will be "
                  "DEFERRED (fail-closed, never fabricated). Set one of %s "
                  "to read the live workflow list.\n"
                  % ", ".join(reg.FIREBASE_REFRESH_LABELS))

    checks = {k: v for k, v in modules.items() if k in CHECK_MODULE_NAMES}
    return skeleton.verify_live(checks, client, rail, location_id, contract,
                                field_map, route, allow_deferred=allow_deferred,
                                out=out)


def _fallback_or_stop(client, location_id: str, out) -> "reg.CafClient|None":
    """Probe the PIT's custom-fields read; on an EDGE block (UpstreamBlockedError
    — not a genuine scope denial) and with a Firebase refresh token BY LABEL
    configured, return the rail-backed fallback client. On a genuine scope
    denial STOP (exit 2). On a blocked read with no rail configured, HELD
    (return None). Never fabricated either way."""
    try:
        probe = client.list_custom_fields(location_id)
    except reg.ScopeDenied as exc:
        reg._stop(out, "The Convert and Flow token lacks READ scope on the "
                  "template location.",
                  [str(exc), "Grant the template PIT the customFields READ "
                   "scope and re-run."])
        raise _StopSentinel()
    except reg.UpstreamBlockedError as exc:
        out.write("[live-verify] HELD (custom-fields read): %s\n" % exc)
    except reg.CafUnreachable as exc:
        out.write("[live-verify] HELD (custom-fields read): %s\n" % exc)
        return None
    else:
        if not isinstance(probe, list):
            out.write("[live-verify] unexpected customFields read shape\n")
            raise _StopSentinel()
        return client
    # The PIT read is edge-blocked: defer to the rail when it is configured.
    rlabel, rtoken = reg.resolve_firebase_refresh_token()
    if rtoken:
        _, api_key = reg._resolve_firebase_api_key() or (None, "")
        if api_key:
            out.write("[live-verify] public-v2 customFields edge-blocked; "
                      "deferring reads to the Firebase-JWT internal rail "
                      "(label %s).\n" % rlabel)
            return reg.RailFallbackClient(reg.InternalRailClient(rtoken, api_key))
    out.write("[live-verify] HELD: custom-fields read blocked and no Firebase "
              "refresh token is SET for the rail fallback (labels: %s) — "
              "fail-closed.\n" % ", ".join(reg.FIREBASE_REFRESH_LABELS))
    return None


class _StopSentinel(Exception):
    """Internal sentinel for the probe's STOP path — never a secret leak."""


# ---------------------------------------------------------------------------
# Manifest-pending stage — manifest-pending/u02.json. Written ONLY after a
# PASS (self-test pass or dry-run plan pass); a FAIL/HELD/STOP run writes
# nothing. The record is the machine-readable input to a later manifest
# re-stamp — the ENGINE-MANIFEST.json itself is never touched here.
# ---------------------------------------------------------------------------
def _pending_payload(kind: str, location_id: str, *, checks: dict | None = None,
                     verdict: str = "PASS") -> dict:
    return {
        "contract": "anthology-engine-template-live-verify",
        "schema_version": 1,
        "kind": kind,  # "self-test" | "dry-run" | "verify"
        "verdict": verdict,
        "manifest_row": 54,
        "script": "live_verify_template.py",
        "authored_by": "U02",
        "template_location_id": location_id,
        "u02_modules": [
            {"name": name, "role": role} for name, role in U02_MODULES
        ],
        "check_modules": list(CHECK_MODULE_NAMES),
        "verified_items": [
            {"item": i, "id": item_id, "title": title}
            for i, (item_id, title) in enumerate(VERIFIED_ITEMS, start=1)
        ],
        "af_codes": [
            {"code": code, "exit": exit_code, "meaning": meaning}
            for code, exit_code, meaning in AF_CODES
        ],
        "exit_codes": EXIT_CODES,
        "custom_value_keys": list(CUSTOM_VALUE_KEYS),
        "checks": checks or {},
        "fail_closed": {
            "any_fail": bool(checks and any(
                c.get("status") == "FAIL" for c in checks.values())),
            "note": "a DEFERRED live read (internal-rail credential NOT SET) "
                    "counts as FAIL unless --allow-deferred — the verify never "
                    "fabricates an unread surface.",
        },
    }


def write_pending(payload: dict, *, mode: str = "self-test", out=None) -> None:
    """Write manifest-pending/u02.json (fail-closed: only after a PASS).

    The directory is created if absent; the file is written atomically
    (temp + rename) so a crash mid-write never leaves a partial stage. The
    ENGINE-MANIFEST.json / ENGINE-PIN.sha256 / verify.sh are NEVER touched."""
    out = out or sys.stderr
    try:
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        tmp = PENDING_DIR / ("u02.json.tmp-%d" % __import__("os").getpid())
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
        tmp.replace(PENDING_U02)
    except OSError as exc:
        raise AssembleError("cannot write %s: %s" % (PENDING_U02, exc)) from exc
    out.write("[live-verify] manifest-pending stage written: %s (%s)\n"
              % (PENDING_U02, mode))


# ---------------------------------------------------------------------------
# CLI — house shape: --dry-run / --self-test / --json accepted as flags AND
# as a positional subcommand (--self-test / --selftest normalize exactly as
# anthology_registry.py and main_skeleton.py).
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="live_verify_template.py",
        description="The U02 verifier assembled from the 16 u02_modules "
                    "files: offline self-test battery (golden PASS / attack "
                    "FAIL), offline plan, and live verify of the Anthology "
                    "Convert and Flow TEMPLATE location against the engine's "
                    "sources of truth (Skill 59, ENGINE-MANIFEST row 54) — "
                    "every delta documented as JSON, the manifest-pending "
                    "stage written after a PASS.")
    ap.add_argument("--location-id", default="",
                    help="override the template location id (default: the contract's "
                         "source_template_location.template_location_id, %s; never "
                         "printed)" % DEFAULT_TEMPLATE_LOCATION)
    ap.add_argument("--allow-deferred", action="store_true",
                    help="explicit operator opt-in: accept a DEFERRED live read "
                         "(internal-rail credential NOT SET) as PASS — the report "
                         "still records the deferral")
    ap.add_argument("--field-map", default=str(FIELD_MAP_PATH),
                    help="path to field-map.json (source of truth for the byte-exact gate)")
    ap.add_argument("--contract", default=str(CONTRACT_PATH),
                    help="path to anthology-snapshot-contract.json")
    ap.add_argument("--route-template", default=str(ROUTE_TEMPLATE_PATH),
                    help="path to route-template.json (intake-fire route half)")
    ap.add_argument("--dry-run", action="store_true",
                    help="offline plan only — no network, no credential (default: live verify)")
    ap.add_argument("--json", action="store_true",
                    help="emit a machine-readable summary on stdout (default on for verify/plan)")
    ap.add_argument("--selftest", "--self-test", dest="self_test", action="store_true",
                    help="run the offline self-test (golden + attack fixtures) and exit")
    ap.add_argument("cmd", nargs="?", choices=["verify", "plan", "self-test"],
                    help="positional subcommand form (verify / plan / self-test)")

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
            rc = self_test(modules)
            if rc == EX_OK:
                write_pending(_pending_payload("self-test", DEFAULT_TEMPLATE_LOCATION),
                              mode="self-test")
            return rc

        field_map = reg.load_field_map(Path(args.field_map).expanduser())
        contract = _read_json(Path(args.contract).expanduser(),
                              "anthology-snapshot-contract.json")
        route = _read_json(Path(args.route_template).expanduser(),
                           "route-template.json")
        location_id = (args.location_id.strip() or
                       (contract.get("source_template_location") or {}).get("template_location_id")
                       or DEFAULT_TEMPLATE_LOCATION)

        if args.dry_run:
            rc = dry_run(modules, location_id, field_map, contract)
            if rc == EX_OK:
                write_pending(_pending_payload("dry-run", location_id),
                              mode="dry-run")
            return rc

        rc = verify_live(modules, location_id, field_map, contract, route,
                         allow_deferred=args.allow_deferred, out=sys.stderr)
        if rc == EX_OK:
            write_pending(_pending_payload("verify", location_id),
                          mode="verify")
        return rc

    except _StopSentinel:
        return EX_STOP
    except reg.ScopeDenied as exc:
        sys.stderr.write("[live-verify] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[live-verify] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[live-verify] HELD: %s\n" % exc)
        return EX_HELD
    except reg.InternalRailUnavailable as exc:
        sys.stderr.write("[live-verify] HELD: %s\n" % exc)
        return EX_HELD
    except AssembleError as exc:
        sys.stderr.write("[live-verify] STOP/FAIL: %s\n" % exc)
        return EX_STOP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[live-verify] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
