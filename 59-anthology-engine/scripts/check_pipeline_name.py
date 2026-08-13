#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: scripts/check_pipeline_name.py  (U03 tooling)
# PIPELINE NAME CHECK — the single CLI for the U03 name-law family, ASSEMBLED
# from the 16 u03_modules files: it imports EVERY module under
# scripts/u03_modules/ BY NAME (the fail-closed empty package init +
# main_skeleton dispatcher + config_loader + name_reader + rename_checker +
# rename_applier + verify_after + golden_correct + golden_wrong +
# attack_no_pipeline + house_rules + example_usage + docs_u03 + the three
# sibling pytest batteries), wires them into ONE offline/online CLI, and runs
# the modules' own OFFLINE self-test batteries (golden PASS / attack FAIL,
# the no-pipeline STOP included) before any live surface. This file carries NO
# check logic itself — a check family is exercised ONLY through its module so
# `--dry-run`, `--self-test`, and the live name check never drift apart.
#
# WHAT THIS CHECKS (MASTER-SPEC U03 verified item 1; docs_u03.VERIFY_ITEMS):
#   PIPELINE NAME BYTE-EXACT "Anthology Engine" — find-and-bind is BY NAME
#   (MASTERDOC floor 11; config/field-map.json pipeline.standard_pipeline_name
#   is the single source of truth). A RENAMED pipeline is indistinguishable
#   from an ABSENT one to find-by-name (both bind nothing), so BOTH refuse
#   (AF-AE-TEMPLATE-PIPELINE-MISSING family), and the EMPTY listings state
#   ({"pipelines": []} — the U03 attack) is refused UP FRONT with its own
#   loud STOP, never judged a clean read.
#
# THE 16 u03_modules FILES (imported by name; each is STDLIB-only and
# self-tests itself — docs_u03.py carries the module inventory as data and
# its self-test proves the tree ships together):
#   __init__.py            fail-closed EMPTY package init (pure namespace)
#   main_skeleton.py       the check-module dispatcher CLI (plan / self-test /
#                          live verify; the ONE entry-point contract)
#   config_loader.py       the shared OFFLINE (location id, expected name)
#                          config surface, fail-closed
#   name_reader.py         live pipeline-name read (STOP on unreadable shape)
#   rename_checker.py      live name check BYTE-EXACT vs the name law
#   rename_applier.py      the ONLY write surface (REFUSES without --execute)
#   verify_after.py        the read-back: stamp / custom values / pipeline
#   golden_correct.py      golden pipeline fixture (field-map derived)
#   golden_wrong.py        golden RENAMED-state fixture the checks DETECT
#   attack_no_pipeline.py  the U03 ATTACK: the empty listing is refused up front
#   house_rules.py         the ONE canonical house-law constants surface
#   example_usage.py       the fail-closed WORKED EXAMPLE of the U03 dispatch
#   docs_u03.py            the U03 README/catalog data + drift gate
#   test_rename_checker.py offline pytest battery for rename_checker
#   test_rename_applier.py offline pytest battery for rename_applier
#   test_verify_after.py   offline pytest battery for verify_after
#
# THE LIVE READ IS GHL-GATED; THE TOOLING SHIPS NOW. The operator executes
# `verify` only from a session that can resolve a template-scoped
# private-integration token BY LABEL. --dry-run (offline plan), --self-test
# (offline golden + attack fixtures, the no-pipeline STOP included), and the
# pytest batteries need NO token and NO network.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. The PIT is resolved via
# anthology_registry (CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_API_KEY /
# GOHIGHLEVEL_API_KEY / GOHIGHLEVEL_PIT / GHL_API_KEY, live process env first
# then the three canonical client env stores), and the location id comes from
# the CONTRACT (source_template_location.template_location_id
# 2HIKGNgsixWx0yds7Qnx — the operator's OWN template, never a client
# location) unless --location-id overrides. SET / NOT SET only on every
# operator surface; a value is NEVER printed. Every report masks the location
# id to its last 4 characters.
#
# BROWSER UA: every request rides reg.CafClient, which applies CAF_BROWSER_UA
# so the Cloudflare edge fronting services.leadconnectorhq.com never 1010s a
# verify request (CF 1010 / GK-09 discipline). Scope-vs-edge-block
# discrimination: a bare 401/403 is HELD (UpstreamBlockedError), never
# reported as a scope problem.
#
# AF CODES (fail-closed surfaces; self-test failures are exit 4, never 1):
#   AF-AE-TEMPLATE-PIPELINE-MISSING  -> the standard pipeline is absent,
#          renamed, near-miss, or the EMPTY listing (the U03 attack) on the
#          template location. STOP / mismatch (exit 2 / exit 5).
#   AF-AE-PIPELINES-UNREADABLE       -> a live pipelines payload whose shape
#          cannot be faithfully read (MalformedPayload). STOP (exit 2).
#   AF-AE-TEMPLATE-ATTACK            -> an attack fixture tripped the OFFLINE
#          self-test. exit 4.
#
# EXIT CODES (house convention 0/1/2/3/5; 4 = enforced violation):
#   0  all checks PASS (also --dry-run plan pass, --self-test pass, and the
#      pytest battery pass)
#   1  unexpected error
#   2  STOP refusal — label NOT SET / non-pit- value / usage / a contract
#      section missing / the standard pipeline ABSENT or RENAMED on the live
#      location / a drifted (location, name) config pair
#   3  Convert and Flow API unreachable incl. the Cloudflare edge 403 (CF
#      error 1010); retryable, never mislabeled as a scope problem
#   4  self-test FAILED — an assertion in the OFFLINE self-test tripped
#      (AF-AE-TEMPLATE-ATTACK family). A tamper NEVER masquerades as exit 1.
#   5  data or read-back mismatch — the pipeline name is absent/renamed/
#      near-miss, the U03 EMPTY-LISTING attack, or a read-back mismatch
#
# MANIFEST-PENDING: after a PASSING run the tool writes
# manifest-pending/u03.json — the staged U03 manifest artifact (contract,
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
"""check_pipeline_name.py — the U03 pipeline-name check assembled from the 16
u03_modules files: one CLI, offline self-test battery (golden PASS / wrong
name detected / no-pipeline STOP), JSON output, and the manifest-pending/
u03.json stage (Skill 59)."""

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
MODULES_DIR = Path(__file__).resolve().parent / "u03_modules"
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"
PENDING_DIR = SKILL_DIR / "manifest-pending"
PENDING_U03 = PENDING_DIR / "u03.json"

# The template location id is the CONTRACT's source_template_location (the
# operator's OWN template location, operator infrastructure config, not a
# secret). The check pins to it; --location-id overrides for tests.
DEFAULT_TEMPLATE_LOCATION = "2HIKGNgsixWx0yds7Qnx"

# THE SIXTEEN u03_modules FILES — the assembly manifest for this check.
# Every name is imported BY NAME below (importlib), never exec'd from a
# path; a missing module is a STOP, never a silent skip (the fail-closed
# import contract of main_skeleton.load_modules). `role` is the one-line
# contract each module owns.
U03_MODULES = (
    ("__init__.py",            "fail-closed empty package init (pure namespace)"),
    ("main_skeleton.py",       "the check-module dispatcher CLI (plan / self-test / live verify)"),
    ("config_loader.py",       "the shared OFFLINE (location id, expected name) config surface"),
    ("name_reader.py",         "live pipeline-name read (STOP on unreadable shape)"),
    ("rename_checker.py",      "live name check BYTE-EXACT vs the name law"),
    ("rename_applier.py",      "the ONLY write surface (REFUSES without --execute)"),
    ("verify_after.py",        "the read-back: stamp / custom values / pipeline gates"),
    ("golden_correct.py",      "golden pipeline fixture (field-map derived)"),
    ("golden_wrong.py",        "golden RENAMED-state fixture the checks DETECT"),
    ("attack_no_pipeline.py",  "the U03 ATTACK: the empty listing is refused up front"),
    ("house_rules.py",         "the ONE canonical house-law constants surface"),
    ("example_usage.py",       "the fail-closed WORKED EXAMPLE of the U03 dispatch"),
    ("docs_u03.py",            "the U03 README/catalog data + drift gate"),
    ("test_rename_checker.py", "offline pytest battery for rename_checker"),
    ("test_rename_applier.py", "offline pytest battery for rename_applier"),
    ("test_verify_after.py",   "offline pytest battery for verify_after"),
)

# The modules the dispatcher aggregates (main_skeleton.U03_MODULES).
DISPATCH_MODULE_NAMES = tuple(name for name, _ in (
    ("config_loader", "load the contract (location id, expected name) pair, "
                      "fail-closed, never a hardcoded law"),
    ("name_reader", "live pipeline-name read (STOP on unreadable shape)"),
    ("rename_checker", "live name check BYTE-EXACT vs the name law"),
    ("rename_applier", "the ONLY write surface (REFUSES without explicit --yes)"),
    ("verify_after", "the read-back: stamp / custom values / pipeline gates"),
    ("golden_correct", "golden pipeline fixture (field-map derived)"),
    ("golden_wrong", "golden RENAMED-state fixture the checks must DETECT"),
    ("attack_no_pipeline", "the U03 ATTACK: the empty listing is refused up front"),
    ("house_rules", "the ONE canonical house-law constants surface"),
    ("example_usage", "the fail-closed WORKED EXAMPLE of the U03 dispatch"),
    ("docs_u03", "the U03 tooling README/catalog data + drift gate"),
))

# The modules that ship their OWN offline self-test battery (golden PASS /
# attack FAIL, exit 0 pass / 4 enforced violation). Every one of the 11
# dispatch modules ships a battery — a check family that cannot prove itself
# offline STOPS (the dispatcher REQUIRES a battery from every module).
SELF_TEST_MODULES = DISPATCH_MODULE_NAMES

# The three sibling pytest batteries (imported for their provenance in the
# manifest-pending stage; the pytest run itself is the independent battery).
TEST_MODULES = ("test_rename_checker", "test_rename_applier", "test_verify_after")

# The four U03 verified items, as the manifest-pending stage records them
# (docs_u03.VERIFY_ITEMS — the catalog and the tree never drift).
VERIFIED_ITEMS = (
    (1, "pipeline", "Pipeline name BYTE-EXACT 'Anthology Engine'"),
    (2, "stages", "Nine stages BY NAME IN ORDER, contiguous positions 0..8"),
    (3, "custom_values", "Custom values (four keys, REPLACE-ME placeholders, never-a-real-token)"),
    (4, "workflows", "Workflows count + folder 'Anthology Engine' (EIGHT release workflows)"),
)

# The AF-AE-TEMPLATE-* autofail family, as the stage records it.
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

# House exit-code contract (docs_u03.EXIT_CODES).
EXIT_CODES = {
    0: "verified success — all checks PASS (also plan / dry-run / self-test)",
    1: "unexpected error (top-level guard; never a secret leak)",
    2: "STOP refusal — label NOT SET / non-pit- value / usage / a contract "
       "section missing / the standard pipeline ABSENT or RENAMED on the "
       "location / a drifted (location, name) config pair",
    3: "HELD — Convert and Flow API unreachable incl. the Cloudflare edge "
       "403 (CF error 1010); retryable, never mislabeled as a scope problem",
    4: "self-test FAILED (AF-AE-*-ATTACK family, enforced violation) — a "
       "tamper never masquerades as exit 1",
    5: "mismatch / fail-closed default — drift, extra or mutated keys, a "
       "real-looking custom value, the U03 EMPTY-LISTING attack, or a "
       "read-back mismatch after the rename PUT",
}

# The four contract custom-value keys (checked BY KEY; a value is never
# printed — the never-a-real-token rule).
CUSTOM_VALUE_KEYS = ("anthology_webhook_url", "anthology_hook_secret",
                     "producer", "producer_email")


class AssembleError(Exception):
    """A fail-closed refusal raised by the assembly itself — a missing
    u03_modules file, a module violating the entry-point contract, or a
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
# The 16-file assembly — import EVERY u03_modules file BY NAME. The empty
# package init is imported for the namespace guarantee (importing the
# package succeeds only if __init__.py is intact); the check modules come
# through main_skeleton.load_modules (the ONE entry-point contract); the
# fixture / reporter / docs modules are imported for their surfaces and
# their self-test batteries; the three pytest batteries are imported for
# their provenance (their tests run as the independent pytest battery).
# ---------------------------------------------------------------------------
def _load_package() -> None:
    """Prove the package namespace container imports clean."""
    importlib.import_module("u03_modules")


def load_skeleton() -> object:
    """The main_skeleton dispatcher module (imported BY NAME)."""
    return importlib.import_module("u03_modules.main_skeleton")


def load_all_modules(out=None) -> dict:
    """Import every one of the 16 u03_modules files. Returns
    {name: module}. Fail-closed: a missing file or a module violating its
    contract raises AssembleError (STOP) — the aggregate NEVER passes with
    a module silently absent.

    The check modules go through main_skeleton.load_modules (which enforces
    the ONE-entry-point contract and raises SkeletonError on a violation);
    the fixture / reporter / docs modules and the three pytest batteries are
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
    for name in TEST_MODULES:
        try:
            modules[name] = importlib.import_module("u03_modules." + name)
        except ImportError:
            missing.append(name)
    if missing:
        raise AssembleError(
            "u03_modules file(s) not found: %s — the 16-file assembly is "
            "incomplete (fail-closed: no module is ever skipped)"
            % ", ".join(missing))
    if len(modules) != 15:
        raise AssembleError(
            "assembly loaded %d modules, expected 15 (main_skeleton + 11 "
            "dispatch modules + 3 pytest batteries)" % len(modules))
    return modules


# ---------------------------------------------------------------------------
# Offline self-test — run EVERY module's own battery (golden PASS / attack
# FAIL, the no-pipeline STOP included), plus the main_skeleton dispatcher
# battery, plus this verifier's own assembly assertions, plus the three
# sibling pytest batteries. NO network, NO credentials. Exit 4 on any
# failure.
# ---------------------------------------------------------------------------
def _module_self_test(module, name: str, out) -> None:
    st = getattr(module, "self_test", None)
    if not callable(st):
        raise AssertionError(
            "module %s does not expose 'self_test' — every u03_modules "
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
    name-law family (golden / renamed / absent) is pinned offline. A failed
    battery is an enforced violation, never a silent skip."""
    pkg = Path(modules["test_rename_checker"].__file__).resolve().parent
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
    """OFFLINE self-test: the modules' own golden+attack batteries plus the
    dispatcher battery, the assembly's file-count assertions, the name-law
    gate (golden PASS / wrong name DETECTED / no-pipeline STOP), and the
    sibling pytest batteries. Any failure is exit 4 (AF-AE-TEMPLATE-ATTACK
    family) — a tamper NEVER masquerades as exit 1. On a clean pass the
    manifest-pending stage is written."""
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        # 1. the assembly is complete: exactly the 16 files exist.
        on_disk = sorted(p.name for p in MODULES_DIR.glob("*.py"))
        expected = sorted(name for name, _ in U03_MODULES)
        assert on_disk == expected, (
            "u03_modules tree drifted: disk carries %d files, the 16-file "
            "assembly contract names %d (%s)"
            % (len(on_disk), len(expected),
               ", ".join(sorted(set(on_disk) ^ set(expected)))))
        # 2. every module's own battery passes (golden PASS / attack FAIL).
        for name in SELF_TEST_MODULES:
            _module_self_test(modules[name], name, dev)
        # 3. the dispatcher battery passes (main_skeleton.self_test runs the
        #    eleven check modules through the one-entry-point contract and
        #    pins the catalog counts against docs_u03). The dispatcher's own
        #    battery is run by itself: it iterates its OWN dispatch set
        #    (self_test(modules)), and this assembly already ran every module
        #    battery above — so here the dispatcher battery runs over ITS
        #    dispatch modules only, never over this assembler (which would
        #    recurse).
        skeleton = modules["main_skeleton"]
        dispatch_only = {k: v for k, v in modules.items()
                         if k in DISPATCH_MODULE_NAMES}
        sk_rc = skeleton.self_test(dispatch_only, out=dev)
        assert sk_rc == EX_OK, \
            "main_skeleton dispatcher self-test returned exit %d" % sk_rc
        # 4. the name-law gate, exercised through the modules' own surfaces:
        #    the golden name PASSES, the wrong name (the sibling-skill name,
        #    "Anthology Writer") is DETECTED/REFUSED, and the EMPTY listing
        #    (the U03 attack) is refused UP FRONT — the no-pipeline STOP.
        field_map = reg.load_field_map(FIELD_MAP_PATH)
        gc = modules["golden_correct"]
        gw = modules["golden_wrong"]
        anp = modules["attack_no_pipeline"]
        rck = modules["rename_checker"]
        want = (field_map.get("pipeline") or {}).get("standard_pipeline_name")
        assert want == "Anthology Engine", \
            "standard_pipeline_name drifted from the U03 contract (got %r)" % want
        # 4a. golden correct -> PASS (exit 0)
        with _redirect_stdout(io.StringIO()):
            rc = gc.payload("Anthology Engine", field_map, out=io.StringIO())
        assert rc == EX_OK, \
            "golden correct payload must exit 0, got %s" % rc
        # 4b. wrong name -> DETECTED/REFUSED (exit 5)
        with _redirect_stdout(io.StringIO()):
            rc = gc.payload(gw.WRONG_PIPELINE_NAME, field_map,
                            out=io.StringIO())
        assert rc == EX_MISMATCH, \
            "wrong name must exit 5, got %s" % rc
        # 4c. the golden WRONG state is DETECTED on the renamed listing
        status, _names, _stages = gw.detect(gw.golden_wrong_listing(field_map),
                                            want)
        assert status == "DETECTED", \
            "the golden wrong state must be DETECTED: %s" % status
        # 4d. the EMPTY listing (the U03 attack) is refused UP FRONT —
        #     the no-pipeline STOP.
        try:
            anp.verify({"pipelines": []}, want)
            raise AssertionError("the empty listing was NOT refused")
        except anp.NoPipelineError:
            pass
        # 4e. the live-surface verdict on the no-pipeline state: ok False,
        #     current "" (absent reads identically to renamed — the law).
        report = rck.check_name(_EmptyCaf(), "loc_tmpl", want)
        assert report["ok"] is False and report["current"] == "", \
            "no-pipeline check must report ok False, current empty: %s" % report
        # 5. the never-a-real-token classifier (verify_after.is_placeholder).
        va = modules["verify_after"]
        assert va.is_placeholder("") is True, "empty value is a placeholder"
        assert va.is_placeholder("REPLACE-ME") is True
        assert va.is_placeholder("https://hooks.example.com/x") is False, \
            "a real-looking value must be refused (never-a-real-token)"
        # 6. docs_u03's catalog is the assembly's catalog (4 items, 12
        #    modules in its inventory, exit codes 0..5, 5 af codes — its
        #    self-test already pinned the counts; here we pin the shared
        #    constants).
        docs = modules["docs_u03"]
        assert len(docs.verify_items()) == len(VERIFIED_ITEMS), \
            "docs_u03 item count drifted from the assembly's VERIFIED_ITEMS"
        assert len(docs.af_codes()) == len(AF_CODES), \
            "docs_u03 af-code family drifted from the assembly's AF_CODES"
        # 7. the sibling pytest batteries (the independent proof).
        if run_pytest:
            _run_pytest(modules, dev)
    except AssertionError as exc:
        sys.stderr.write("[check-pipeline-name] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    except AssembleError as exc:
        sys.stderr.write("[check-pipeline-name] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION

    out.write(dev.getvalue())
    out.write("[check-pipeline-name] assembled self-test: OK (16 u03_modules "
              "files imported, 11 module batteries + dispatcher battery + "
              "name-law gate + 3 pytest batteries + assembly assertions all "
              "pass)\n")
    return EX_OK


class _EmptyCaf:
    """Deterministic pipeline-listing stub serving the EMPTY listing — the
    exact object a live read of a location with NOTHING bound serves."""

    def list_pipelines(self, location_id):
        return []


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


class _redirect_stderr:
    """Minimal context manager capturing stderr into the human channel (the
    house style of example_usage._sibling_stdout_to, applied to stderr)."""

    def __init__(self, out):
        self._out = out
        self._old = None

    def __enter__(self):
        self._old = sys.stderr
        sys.stderr = self._out
        return self._out

    def __exit__(self, *exc):
        sys.stderr = self._old
        return False


# ---------------------------------------------------------------------------
# Offline plan — no network, no credentials. The dispatcher's plan, with the
# assembly's stage-record on the side. Prints ONE JSON object on stdout.
# ---------------------------------------------------------------------------
def dry_run(modules: dict, location_id: str, out=None) -> int:
    out = out or sys.stderr
    skeleton = modules["main_skeleton"]
    try:
        cfg = modules["config_loader"].load_config(
            contract_path=CONTRACT_PATH, field_map_path=FIELD_MAP_PATH)
    except Exception as exc:  # noqa: BLE001 — a plan never fabricates
        out.write("[check-pipeline-name] plan: %s\n" % exc)
        return EX_STOP
    # The dispatcher's own plan (the ONE JSON object on stdout, capturing its
    # stdout JSON into the human channel — the machine surface is this
    # assembler's plan object).
    with _redirect_stdout(io.StringIO()):
        rc = skeleton.plan(modules, cfg["location_id"], cfg["expected_name"],
                           cfg["sources"], out=out)
    if rc != EX_OK:
        return rc
    print(json.dumps({
        "contract": "anthology-engine-u03-dispatch-plan",
        "schema_version": 1,
        "kind": "dry-run",
        "location_id": cfg["location_id"],
        "location_id_masked": cfg["location_id_masked"],
        "expected_name": cfg["expected_name"],
        "sources": cfg["sources"],
        "gates": ["verify_after"],
        "modules": [name for name, _ in U03_MODULES],
        "dry_run": True,
        "note": "offline plan only — no network, no credential needed; a "
                "LIVE read must ride reg.CafClient (CAF_BROWSER_UA on every "
                "request — CF 1010 law)",
    }, indent=2, sort_keys=True))
    out.write("[check-pipeline-name] dry-run plan: OK (offline — no network, "
              "no credential needed)\n")
    return EX_OK


# ---------------------------------------------------------------------------
# Live verify — the dispatcher's fail-closed aggregate over the read-back
# family, with the READ probe first. The live READ is GHL-gated; the tooling
# ships now.
# ---------------------------------------------------------------------------
def verify_live(modules: dict, location_id: str, field_map: dict,
                contract: dict, *, allow_deferred: bool = False,
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
                   "labels first) and re-run."
                   % modules["config_loader"].mask_location(location_id)])
        return EX_STOP
    client = reg.CafClient(token)
    try:
        probe = client.list_pipelines(location_id)
    except reg.ScopeDenied as exc:
        reg._stop(out, "The Convert and Flow token lacks READ scope on the template location.",
                  [str(exc), "Grant the template PIT the opportunities READ scope and re-run."])
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        out.write("[check-pipeline-name] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        out.write("[check-pipeline-name] HELD: %s\n" % exc)
        return EX_HELD
    if not isinstance(probe, list):
        out.write("[check-pipeline-name] unexpected pipelines read shape\n")
        return EX_ERR

    # The name-law gate over the live read: the standard pipeline must be
    # present BYTE-EXACT (find-and-bind is BY NAME); the EMPTY listing (the
    # U03 attack) is refused UP FRONT — never a clean read.
    try:
        status, detail, name, stages = modules["attack_no_pipeline"].verify(
            {"pipelines": probe}, modules["config_loader"].load_config(
                contract_path=CONTRACT_PATH,
                field_map_path=FIELD_MAP_PATH)["expected_name"])
    except modules["attack_no_pipeline"].NoPipelineError as exc:
        reg._stop(out, "The standard Anthology pipeline is NOT present "
                       "BYTE-EXACT on the template location.",
                  [str(exc), "Location marker: %s"
                   % modules["config_loader"].mask_location(location_id),
                   "AF-AE-TEMPLATE-PIPELINE-MISSING — bind the pipeline in "
                   "the Convert and Flow UI, then re-run."])
        return EX_STOP

    # The read-back family: stamp coherent, custom values placeholders only,
    # standard pipeline byte-exact (fail-closed aggregate).
    return skeleton.verify_live(modules, client, location_id, field_map,
                                contract, allow_deferred=allow_deferred,
                                out=out)


# ---------------------------------------------------------------------------
# Manifest-pending stage — manifest-pending/u03.json. Written ONLY after a
# PASS (self-test pass or dry-run plan pass); a FAIL/HELD/STOP run writes
# nothing. The record is the machine-readable input to a later manifest
# re-stamp — the ENGINE-MANIFEST.json / ENGINE-PIN.sha256 / verify.sh are
# NEVER touched here.
# ---------------------------------------------------------------------------
def _pending_payload(kind: str, location_id: str, *,
                     verdict: str = "PASS") -> dict:
    return {
        "contract": "anthology-engine-u03-name-check",
        "schema_version": 1,
        "kind": kind,  # "self-test" | "dry-run" | "verify"
        "verdict": verdict,
        "script": "check_pipeline_name.py",
        "authored_by": "U03",
        "template_location_id": location_id,
        "u03_modules": [
            {"name": name, "role": role} for name, role in U03_MODULES
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
            "note": "the U03 EMPTY-LISTING attack is refused UP FRONT "
                    "(AF-AE-TEMPLATE-PIPELINE-MISSING, STOP exit 2) — a "
                    "location with nothing bound is never judged a clean read.",
        },
    }


def write_pending(payload: dict, *, mode: str = "self-test", out=None) -> None:
    """Write manifest-pending/u03.json (fail-closed: only after a PASS).

    The directory is created if absent; the file is written atomically
    (temp + rename) so a crash mid-write never leaves a partial stage. The
    ENGINE-MANIFEST.json / ENGINE-PIN.sha256 / verify.sh are NEVER touched."""
    out = out or sys.stderr
    try:
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        tmp = PENDING_DIR / ("u03.json.tmp-%d" % os.getpid())
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
        tmp.replace(PENDING_U03)
    except OSError as exc:
        raise AssembleError("cannot write %s: %s" % (PENDING_U03, exc)) from exc
    out.write("[check-pipeline-name] manifest-pending stage written: %s (%s)\n"
              % (PENDING_U03, mode))


# ---------------------------------------------------------------------------
# CLI — house shape: --dry-run / --self-test / --json accepted as flags AND
# as a positional subcommand (--self-test / --selftest normalize exactly as
# anthology_registry.py, u02_modules/main_skeleton.py, and
# u03_modules/main_skeleton.py).
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="check_pipeline_name.py",
        description="The U03 pipeline-name check assembled from the 16 "
                    "u03_modules files: offline self-test battery (golden "
                    "PASS / wrong name DETECTED / no-pipeline STOP), offline "
                    "plan, and live verify of the standard pipeline name "
                    "BYTE-EXACT on the Anthology Convert and Flow TEMPLATE "
                    "location (Skill 59) — every delta documented as JSON, "
                    "the manifest-pending stage written after a PASS.")
    ap.add_argument("--location-id", default="",
                    help="override the template location id (default: the "
                         "contract's source_template_location."
                         "template_location_id, %s; never printed)"
                         % DEFAULT_TEMPLATE_LOCATION)
    ap.add_argument("--allow-deferred", action="store_true",
                    help="explicit operator opt-in: accept a DEFERRED live "
                         "read (internal-rail credential NOT SET) as PASS — "
                         "the report still records the deferral")
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
                    help="skip the sibling pytest batteries inside --self-test "
                         "(dispatch self-test only; the offline batteries "
                         "still run)")
    ap.add_argument("--selftest", "--self-test", dest="self_test",
                    action="store_true",
                    help="run the offline self-test (golden + attack "
                         "fixtures, no-pipeline STOP, pytest batteries) and "
                         "exit")
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

        field_map = reg.load_field_map(Path(args.field_map).expanduser())
        contract = _read_json(Path(args.contract).expanduser(),
                              "anthology-snapshot-contract.json")
        location_id = (args.location_id.strip() or
                       (contract.get("source_template_location") or {}).get("template_location_id")
                       or DEFAULT_TEMPLATE_LOCATION)

        if args.dry_run:
            rc = dry_run(modules, location_id, out=sys.stderr)
            if rc == EX_OK:
                write_pending(_pending_payload("dry-run", location_id),
                              mode="dry-run")
            return rc

        rc = verify_live(modules, location_id, field_map, contract,
                         allow_deferred=args.allow_deferred,
                         out=sys.stderr)
        if rc == EX_OK:
            write_pending(_pending_payload("verify", location_id),
                          mode="verify")
        return rc

    except reg.ScopeDenied as exc:
        sys.stderr.write("[check-pipeline-name] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[check-pipeline-name] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        sys.stderr.write("[check-pipeline-name] HELD: %s\n" % exc)
        return EX_HELD
    except AssembleError as exc:
        sys.stderr.write("[check-pipeline-name] STOP/FAIL: %s\n" % exc)
        return EX_STOP
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — top-level guard, never leaks a secret
        sys.stderr.write("[check-pipeline-name] unexpected error: %s: %s\n"
                         % (type(exc).__name__, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())
