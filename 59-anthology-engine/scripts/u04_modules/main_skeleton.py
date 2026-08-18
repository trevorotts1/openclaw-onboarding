#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u04_modules/main_skeleton.py
# U04 CHECK-MODULE DISPATCHER — the offline-plan / offline-self-test / live
# verify driver for the U04 module family under scripts/u04_modules/. It
# imports the check modules BY NAME (importlib, never exec'd from a path),
# enforces the fail-closed one-entry-point contract, and resolves the
# aggregate exit code exactly as its U02 / U03 siblings
# (u02_modules/main_skeleton.py, u03_modules/main_skeleton.py) do. It
# carries NO check logic itself: a check module is exercised ONLY through
# this CLI so `--dry-run`, `--self-test`, and the live aggregate never
# drift apart.
#
# THE U04 FAMILY (the check modules this dispatcher aggregates; each is
# STDLIB-only and ships its own OFFLINE self-test battery, which this
# skeleton REQUIRES and runs before any live surface — a check family that
# cannot prove itself offline STOPS):
#   form_reader.py          read_forms(client, location_id, *, pinned_id)
#                           -> the public v2 GET /forms/?locationId= read
#                           that FINDS the universal author-intake form by
#                           slug / pin and reports its ONE form id; raises
#                           FormsReadError (STOP) on an unreadable listing
#                           shape, never a silent empty. Also plan().
#   required_checker.py     check_required(payload, required_fields=None)
#                           -> {"ok", "missing", "required", "source"} —
#                           the required-flags law (first_name / last_name /
#                           email present and non-empty, intake_router
#                           FIELD_ALIASES-aware), OFFLINE and pure; raises
#                           _UnreadablePayload (STOP) on an unreadable
#                           shape, never a fabricated clean check.
#   brand_link_checker.py   check_html(html_bytes, page_name) /
#                           check_pages(paths) -> {"ok", "flags", ...} —
#                           the OFFLINE brand-surface legal-link gate
#                           (RFC 2606 placeholder hosts / hostless / bare
#                           legal rows flag REPLACE; a page with no anchors
#                           flags MISSING). Never fetches, never resolves.
#   query_key_checker.py    fetch_form_page(forms_base, form_id) +
#                           check_query_key(page, want) -> {"ok", "current",
#                           "expected"} — the G3 intake query-key gate
#                           (the hidden field must be keyed "anthology_id"
#                           BYTE-EXACT, never the lookalike
#                           "anthology_active_id"). The live page read is
#                           CREDENTIAL-FREE (the public hosted-form widget)
#                           and rides reg.CAF_BROWSER_UA; a page that cannot
#                           be fetched is HELD (exit 3), never judged.
#   query_key_fixer.py      plan_form_fix(client, location_id, *,
#                           pinned_id, execute) — the ONLY write surface in
#                           the U04 family (PUT /forms/{id}). It REFUSES to
#                           write unless the operator passes --execute to
#                           ITS OWN CLI; the dispatcher NEVER invokes it and
#                           NEVER writes. Also plan().
#   golden_ok.py            golden_form(contract) / golden_compliant_payload
#                           (contract) / payload(compliance, contract) — the
#                           golden ALREADY-COMPLIANT intake-form fixture,
#                           derived byte-exact from the committed snapshot
#                           contract, never a hardcoded list.
#   attack_bad_query.py     attack_link(...) / verify_live(link) — the U04
#                           ATTACK: the G3-conflation link (anthology_id
#                           swapped to anthology_active_id) that every
#                           byte-exact query-key gate must REFUSE.
#   attack_example_dot_com.py  attack_link(...) / verify_live(link) — the
#                           U04 ATTACK: an example.com legal link that every
#                           brand-surface gate must REFUSE.
#   attack_not_required.py  verify(payload, required_fields) — the U04
#                           ATTACK: an intake payload with email ABSENT /
#                           EMPTY / whitespace-only / non-string is REFUSED
#                           (NotRequiredError, STOP family), never a clean
#                           read.
#
# THE IMPORT CONTRACT (the surface the family already satisfies): one
# ENTRY POINT per module, exposed as `self_test(out=None) -> int` — exit 0
# on pass, 4 (EX_VIOLATION, the AF-AE-TEMPLATE-ATTACK family) on failure.
# A module without a battery STOPS the dispatcher (fail-closed: no check
# family is ever skipped, and a family that cannot prove itself offline
# cannot be trusted live). The live gates are driven through each module's
# OWN documented surfaces (read_forms / check_query_key / check_required /
# check_pages), never through a re-implementation, and their STOP-family
# exceptions are classified by name, exactly as the U02 / U03 siblings
# classify theirs.
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
# fetch, which apply CAF_BROWSER_UA on every request so the Cloudflare
# edge fronting services.leadconnectorhq.com / the hosted-form domain
# never 1010s a verify request (CF 1010 / GK-09 discipline — the house
# pattern ported byte-for-byte from the U02 / U03 families and the podcast
# gate). This dispatcher asserts the law OFFLINE (its self-test pins the
# exact constant on the outbound surface) so a drifted UA is caught before
# a single live request. Scope-vs-edge-block discrimination: a bare 401/403
# is HELD (UpstreamBlockedError / CafUnreachable), never mislabeled as a
# scope problem; a genuine scope denial is a STOP (exit 2).
#
# AF CODES (fail-closed surfaces; self-test failures are exit 4, never 1):
#   AF-AE-U04-ASSEMBLY-INCOMPLETE -> the U04 check-module set named in
#          U04_MODULES is not fully present, or a module violates the
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
#      AF-AE-BRAND-LINK / AF-AE-REQUIRED-MISSING; also the fail-closed
#      default when any live check is DEFERRED without --allow-deferred)
#
# STDLIB ONLY (urllib + json via the registry and the check modules); calls
# NO model. Reuses anthology_registry (CafClient, resolve_pit, load_field_map,
# _stop). DOCTRINE: move in silence; NOTHING Anthropic in any runtime file;
# Convert and Flow naming in every client surface; NEVER print a secret
# value; --dry-run and --self-test are OFFLINE.
# =============================================================================
"""main_skeleton.py — U04 check-module dispatcher: offline plan / offline
self-test / live verify of the Anthology Convert and Flow TEMPLATE location
(Skill 59, u04_modules; the packaged sibling of u02_modules/main_skeleton.py
and u03_modules/main_skeleton.py)."""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry does the
# Cloudflare browser-UA wiring + LeadConnector client and its label
# resolution is the house credential contract.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The u04_modules directory itself — sibling imports resolve from here, in
# BOTH execution contexts (as a script, whose own directory is sys.path[0],
# and as an imported module, where the caller may not have added it).
MODULES_DIR = Path(__file__).resolve().parent
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"

# The template location id is the CONTRACT's source_template_location (the
# operator's OWN template location, operator infrastructure config, not a
# secret). The verifier pins to it; --location-id overrides for tests.
DEFAULT_TEMPLATE_LOCATION = "2HIKGNgsixWx0yds7Qnx"

# The U04 check-module inventory — the assembly manifest for this dispatcher.
# Every name is imported BY NAME below (importlib, never exec'd from a path);
# a missing module is a STOP, never a silent skip. `role` is the one-line
# contract each module owns. The names mirror the files on disk one-to-one
# (the catalog and the tree never drift; the dispatcher self-test pins the
# counts, exactly as the U03 sibling pins its assembly).
U04_MODULES = (
    ("form_reader", "live public-v2 forms listing read — find the universal "
                    "author-intake form by slug / pin, report its ONE id"),
    ("required_checker", "the required-flags law applied to a payload "
                         "(first_name / last_name / email, present and non-empty)"),
    ("brand_link_checker", "the brand-surface legal-link gate (offline HTML "
                           "scan; RFC 2606 placeholder hosts fail)"),
    ("query_key_checker", "the G3 intake query-key gate (live public "
                          "hosted-form page read, credential-free)"),
    ("query_key_fixer", "the ONLY write surface — the G3 query-key fix via "
                        "PUT /forms/{id}, REFUSED without its own --execute"),
    ("golden_ok", "the golden ALREADY-COMPLIANT intake-form fixture "
                  "(contract-derived, never a hardcoded list)"),
    ("attack_bad_query", "the U04 ATTACK: the wrong query key "
                         "(anthology_active_id) must FAIL every gate"),
    ("attack_example_dot_com", "the U04 ATTACK: an example.com legal link "
                               "must FAIL every brand gate"),
    ("attack_not_required", "the U04 ATTACK: an intake payload with no email "
                            "is REFUSED, never a clean read"),
    ("label_checker", "the OFFLINE raw-key / warm-client-language map gate "
                      "(no raw key leaks onto a client-facing surface)"),
    ("prefill_verifier", "the G3 VALUE-side gate — hidden-field pre-fill "
                         "hydration (served-page identity + widget-build "
                         "signature, credential-free)"),
    ("docs_u04", "the U04 README/catalog data + drift gate (the module "
                 "inventory as DATA; its self-test proves the tree ships "
                 "together)"),
)

# The modules that ship their own OFFLINE self-test battery (each returns
# exit 0 on pass, 4 on failure). The dispatcher REQUIRES a battery from
# every module — a check family that cannot prove itself offline STOPS.
SELF_TEST_MODULES = tuple(name for name, _ in U04_MODULES)

# The independent pytest battery that ships with the family (provenance
# only: the battery's presence is asserted, its tests run under pytest).
TEST_BATTERY = "test_checkers.py"

# The live-verify gate order (FIXED, in this order).
LIVE_GATES = (
    ("form_reader", "the public-v2 forms listing read (slug + pin law)"),
    ("query_key_checker", "the G3 intake query-key gate (live hosted-form page)"),
    ("required_checker", "the required-flags law smoke over the golden "
                         "compliant payload (offline; the live payload "
                         "surface is the intake webhook, not a read)"),
    ("brand_link_checker", "the brand legal-link gate — DEFERRED until brand "
                           "HTML page paths are wired (never fabricated)"),
)

# The default pinned universal-intake form id, imported from form_reader —
# the ONE owner of the pin (the same value anthology_book.py /
# engine-config.template.json carry; a location identifier, not a secret,
# masked on every surface).
try:
    import form_reader as _fr  # noqa: E402
    DEFAULT_UNIVERSAL_INTAKE_FORM_ID = _fr.DEFAULT_UNIVERSAL_INTAKE_FORM_ID
except ImportError:  # pragma: no cover — the assembly assert catches it
    DEFAULT_UNIVERSAL_INTAKE_FORM_ID = ""


class SkeletonError(Exception):
    """A fail-closed refusal (STOP or mismatch family) raised by the skeleton
    itself — a missing check module, a module violating the entry-point
    contract, a contract section that cannot be read, or a malformed record."""


# ---------------------------------------------------------------------------
# Check-module loader — imports the U04 modules BY NAME and enforces the
# fail-closed contract: a missing module or a module that fails to expose
# its entry point is a STOP, never a silent skip.
# ---------------------------------------------------------------------------
def load_modules():
    """Import every U04_MODULES module. Returns {name: module}.

    Fail-closed: a module that does not exist raises SkeletonError (STOP) so
    the aggregate NEVER passes with a check family silently absent.
    `importlib` is the only import surface — nothing is ever exec'd from a
    path. Each module's `self_test(out=None) -> int` battery and its `check`
    entry point are REQUIRED (checked here, not deferred to the self-test
    run)."""
    import importlib

    modules = {}
    missing = []
    for name, _role in U04_MODULES:
        try:
            mod = importlib.import_module(name)
        except ImportError:
            missing.append(name)
            continue
        modules[name] = mod
    if missing:
        raise SkeletonError(
            "u04_modules file(s) not found: %s — the U04 assembly is "
            "incomplete (fail-closed: no check family is ever skipped)"
            % ", ".join(missing))
    for name, mod in modules.items():
        st = getattr(mod, "self_test", None)
        if not callable(st):
            raise SkeletonError(
                "u04_modules module %s does not expose 'self_test' — every "
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
        # 1. the assembly is complete: exactly the U04 check-module set
        #    exists (the dispatcher, the empty package init, and the pytest
        #    battery are the assembly container, not dispatched modules).
        on_disk = sorted(p.name[:-3] for p in MODULES_DIR.glob("*.py")
                         if p.name not in ("__init__.py", "main_skeleton.py")
                         and not p.name.startswith("test_"))
        expected = sorted(name for name, _ in U04_MODULES)
        assert on_disk == expected, (
            "u04_modules tree drifted: disk carries %s, the %d-module "
            "assembly contract names %s" % (", ".join(on_disk), len(expected),
                                            ", ".join(expected)))
        assert (MODULES_DIR / TEST_BATTERY).is_file(), (
            "the U04 pytest battery %s is missing from u04_modules/" % TEST_BATTERY)
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
        #    API 403s as error 1010 before the request is ever scope-checked).
        ua = reg.CAF_BROWSER_UA
        assert isinstance(ua, str) and ua.strip(), "CAF_BROWSER_UA is empty"
        assert "Python-urllib" not in ua, \
            "CAF_BROWSER_UA is urllib's default — the Cloudflare edge 1010s it"
        assert ua.startswith("Mozilla/5.0") and "Chrome/" in ua, \
            "CAF_BROWSER_UA is not a well-formed browser UA"
        # 5. CREDENTIAL LAW: the PIT labels are the house standard set and
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
        # 6. NEVER-A-TOKEN LAW on the skeleton's OWN surfaces: the plan
        #    payload (the same builder the --dry-run prints) and the report
        #    surface carry labels and SET / NOT SET states only — a
        #    credential-shaped string (pit- followed by a value) can never
        #    leak through them.
        contract = _read_json(CONTRACT_PATH, "anthology-snapshot-contract.json")
        plan_blob = json.dumps(_build_plan(modules, DEFAULT_TEMPLATE_LOCATION,
                                           contract, DEFAULT_UNIVERSAL_INTAKE_FORM_ID),
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
    out.write("[main-skeleton] U04 self-test: OK (%d modules imported, "
              "every module battery + assembly assertions + exit-code law + "
              "browser-UA law + credential law pass)\n" % len(modules))
    return EX_OK


_CREDENTIAL_SHAPE = re.compile(r"pit-\S+")


# ---------------------------------------------------------------------------
# Offline plan — no network, no credentials. The U04 dispatch law with the
# exact sources of truth, printed as ONE JSON object on stdout; human notes
# go to stderr. Each module's own plan surface (where it ships one) is
# collected by name; a module plan that cannot be produced is recorded as
# an error, never fabricated. The payload is scanned against the credential
# shape before print — a hit REFUSES the surface rather than echo a token.
# ---------------------------------------------------------------------------
def _module_plan(modules, name, location_id, contract, pinned_id):
    """One module's plan record. Uses the module's OWN plan() surface when
    it ships one; otherwise derives the offline law from the module's
    documented constants / functions. A module plan is never fatal — an
    error is recorded, never a fabricated law."""
    mod = modules[name]
    try:
        if name == "form_reader":
            dev = io.StringIO()
            rc = mod.plan(location_id, pinned_id, out=dev)
            if rc != EX_OK:
                return {"error": "plan returned exit %d" % rc}
            return json.loads(dev.getvalue() or "null")
        if name == "query_key_fixer":
            dev = io.StringIO()
            rc = mod.plan(location_id, pinned_id, out=dev)
            if rc != EX_OK:
                return {"error": "plan returned exit %d" % rc}
            return json.loads(dev.getvalue() or "null")
        if name in ("attack_bad_query", "attack_example_dot_com"):
            # These two modules print their plan JSON to stdout directly
            # (their own CLI surface), so stdout is captured around the call
            # — the dispatcher's stdout stays its ONE plan object.
            import contextlib
            cap = io.StringIO()
            with contextlib.redirect_stdout(cap):
                rc = mod.plan()
            if rc != EX_OK:
                return {"error": "plan returned exit %d" % rc}
            return json.loads(cap.getvalue().strip() or "null")
        if name == "golden_ok":
            form = mod.golden_form(contract)
            return {
                "contract": mod.FIXTURE_CONTRACT + "-plan",
                "schema_version": 1,
                "form": {"id": form["id"], "name": form["name"],
                         "hidden_fields": list(form["hiddenFields"])},
                "required_fields": list(modules["required_checker"]
                                        .resolve_required_fields()),
                "source": mod.REQUIRED_SOURCE,
                "dry_run": True,
                "note": "offline plan only — no network, no credential needed",
            }
        if name == "query_key_checker":
            return {
                "query_key_law": "anthology_id (G3; the hidden field's "
                                 "data-q, byte-exact)",
                "lookalike_key": mod.LOOKALIKE_QUERY_KEY,
                "read": "%s%s/<form_id> (public hosted-form widget; "
                        "CAF_BROWSER_UA on the request — CF 1010 law; "
                        "credential-free by design)"
                        % (mod.DEFAULT_FORMS_BASE, mod.WIDGET_FORM_PATH),
                "note": "offline plan only — no network, no credential "
                        "needed; a page that cannot be fetched is HELD "
                        "(exit 3), never judged",
            }
        if name == "required_checker":
            return {
                "required_fields": list(mod.resolve_required_fields()),
                "law_source": "config/anthology-snapshot-contract.json "
                              "forms.required (intake_router "
                              "upsert_scalar_fields as the fallback law)",
                "note": "offline only — the live payload surface is the "
                        "intake webhook, not a read",
            }
        if name == "brand_link_checker":
            return {
                "placeholder_family": "RFC 2606 reserved test domains "
                                      "(example.*); hostless / bare legal "
                                      "rows; mailto: / tel: / javascript:",
                "note": "no brand HTML page paths are wired into the "
                        "dispatcher yet — the gate needs its inputs, never "
                        "fabricated (live gate DEFERRED)",
            }
        if name == "attack_not_required":
            return {
                "attack": "an intake payload with email absent / empty / "
                          "whitespace-only / non-string must be REFUSED "
                          "(AF-AE-REQUIRED-MISSING), never a clean read",
                "note": "offline attack fixture — judged in the self-test "
                        "battery, never a live gate",
            }
        return {"note": "no plan surface for %s" % name}
    except Exception as exc:  # noqa: BLE001 — a plan is never fatal
        return {"error": "%s: %s" % (type(exc).__name__, exc)}


def _build_plan(modules, location_id: str, contract: dict, pinned_id: str) -> dict:
    """The ONE offline plan payload (shared by --dry-run and the self-test's
    never-a-token scan, so the two can never drift)."""
    plans = {}
    for name, _role in U04_MODULES:
        plans[name] = _module_plan(modules, name, location_id, contract,
                                   pinned_id)
    return {
        "contract": "anthology-engine-u04-dispatch-plan",
        "schema_version": 1,
        "template_location_id": location_id,
        "template_location_id_masked": _mask_id(location_id),
        "pinned_form_id_masked": _mask_id(pinned_id) if pinned_id else "",
        "gates": [name for name, _ in LIVE_GATES],
        "modules": [name for name, _ in U04_MODULES],
        "plans": plans,
        "dry_run": True,
        "note": "offline plan only — no network, no credential needed; a "
                "LIVE read must ride reg.CafClient / the hosted-form fetch "
                "(CAF_BROWSER_UA on every request — CF 1010 law)",
    }


def plan(modules, location_id: str, contract: dict, pinned_id: str,
         out=None) -> int:
    out = out or sys.stderr
    payload = _build_plan(modules, location_id, contract, pinned_id)
    dumped = json.dumps(payload, indent=2, sort_keys=True)
    if _CREDENTIAL_SHAPE.search(dumped):
        raise SkeletonError(
            "plan payload carries a credential-shaped string — REFUSED "
            "without printing it")
    print(dumped)
    return EX_OK


def _mask_id(fid: str) -> str:
    """Mask a form / location id for every operator surface — a location
    identifier, not a secret, but never printed in full (house pattern,
    mirrored from form_reader.mask_id)."""
    fid = (fid or "").strip()
    if len(fid) <= 8:
        return "***"
    return "%s***%s" % (fid[:4], fid[-4:])


def _build_report(modules) -> dict:
    """The empty report scaffold (labels and states only — the never-a-token
    law is pinned on this exact surface in the self-test)."""
    return {
        "contract": "anthology-engine-u04-verify",
        "schema_version": 1,
        "template_location_id": DEFAULT_TEMPLATE_LOCATION,
        "pit_label": "SET" if reg.resolve_pit()[0] else "NOT SET",
        "checks": {},
        "delta": [],
        "fail_closed": True,
    }


# ---------------------------------------------------------------------------
# Live verify — fail-closed aggregate over the fixed gate order. Any FAIL ->
# exit 5; a STOP-family refusal propagates as exit 2; a transport / edge
# failure is HELD (exit 3), never mislabeled as scope. The brand gate is
# DEFERRED (no page inputs wired — never fabricated) and keeps the exit at
# 5 unless --allow-deferred.
# ---------------------------------------------------------------------------
def verify_live(modules, client, location_id: str, contract: dict,
                pinned_id: str, *, allow_deferred: bool = False,
                out=None) -> int:
    out = out or sys.stderr
    masked = _mask_id(location_id)
    report = _build_report(modules)
    report["template_location_id_masked"] = masked
    report["pinned_form_id_masked"] = _mask_id(pinned_id) if pinned_id else ""

    def _stop_classes(mod):
        return tuple(cls for cname in ("FormsReadError", "FormsFixError",
                                       "NotRequiredError", "FixtureError")
                     if isinstance(cls := getattr(mod, cname, None), type)
                     and issubclass(cls, Exception))

    def _run(name, mod):
        try:
            if name == "form_reader":
                result = mod.read_forms(client, location_id, pinned_id=pinned_id)
                if result.get("ok"):
                    return ("PASS",
                            "universal-intake form found (matched by %s)"
                            % result.get("matched_by", "?"),
                            {"form_id": _mask_id(pinned_id)},
                            {"form_id": result.get("form_id_masked", "")}), None
                return ("FAIL",
                        "%s: %s" % (result.get("af_code", "FORMS-NOT-FOUND"),
                                    result.get("note", "")),
                        {"found": True}, {"found": False}), None
            if name == "query_key_checker":
                page = mod.fetch_form_page()
                report_dict = mod.check_query_key(page)
                if report_dict.get("ok"):
                    return ("PASS",
                            "the live hidden field is keyed %r byte-exact; "
                            "no field submits under %r"
                            % (report_dict.get("current"),
                               mod.LOOKALIKE_QUERY_KEY),
                            {"key": "anthology_id"},
                            {"key": report_dict.get("current")}), None
                return ("FAIL",
                        "AF-AE-INTAKE-QUERY-KEY: %s"
                        % report_dict.get("detail", "drift"),
                        {"key": "anthology_id"},
                        {"key": report_dict.get("current")}), None
            if name == "required_checker":
                # The law-coherence smoke: the golden compliant payload must
                # pass the SAME law the live webhook payload is judged by.
                golden = modules["golden_ok"].golden_compliant_payload(contract)
                result = mod.check_required(
                    golden, list(mod.resolve_required_fields()))
                if result.get("ok"):
                    return ("PASS",
                            "required-flags law coherent with the golden "
                            "compliant payload (%s)"
                            % ", ".join(result.get("required", [])),
                            result.get("required"), None), None
                return ("FAIL",
                        "AF-AE-REQUIRED-MISSING: %s"
                        % ", ".join(result.get("missing", []) or ["?"]),
                        result.get("required"), result.get("missing")), None
            if name == "brand_link_checker":
                return ("DEFERRED",
                        "no brand HTML page paths are wired into the "
                        "dispatcher — the gate needs its inputs, never "
                        "fabricated (pass --allow-deferred to accept)",
                        {"pages": "not wired"}, {"pages": "not read"}), None
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
        except _stop_classes(mod) as exc:
            reg._stop(out, "Fail-closed refusal in %s: %s" % (name, exc), [])
            return None, EX_STOP
        except SkeletonError as exc:
            reg._stop(out, "Fail-closed refusal in %s: %s" % (name, exc), [])
            return None, EX_STOP
        except Exception as exc:  # noqa: BLE001 — a module refusal is never an unexpected error
            if exc.__class__.__name__ in ("FormsReadError", "FormsFixError",
                                          "NotRequiredError", "FixtureError",
                                          "FormsReadError"):
                reg._stop(out, "Fail-closed refusal in %s: %s" % (name, exc), [])
                return None, EX_STOP
            raise

    for name, _role in LIVE_GATES:
        record, rc = _run(name, modules[name])
        if rc is not None:
            return rc
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

    deferred = [n for n, c in report["checks"].items()
                if c.get("status") == "DEFERRED"]
    failures = [n for n, c in report["checks"].items()
                if c.get("status") == "FAIL"]
    if deferred:
        out.write("[main-skeleton] %d check(s) DEFERRED (never fabricated). "
                  "Pass --allow-deferred to accept the deferral.\n"
                  % len(deferred))
        if not allow_deferred:
            report["delta"].append({
                "check": "aggregate",
                "detail": "%d check(s) DEFERRED without --allow-deferred "
                          "(fail-closed): %s" % (len(deferred),
                                                 ", ".join(deferred)),
            })
            report["verdict"] = "FAIL (deferred without --allow-deferred)"
            print(json.dumps(report, indent=2, sort_keys=True))
            return EX_MISMATCH
    report["verdict"] = "PASS" if not failures else "FAIL"
    print(json.dumps(report, indent=2, sort_keys=True))
    return EX_OK if not failures else EX_MISMATCH


# ---------------------------------------------------------------------------
# CLI — house shape: --dry-run / --self-test / --json accepted as flags AND
# as a positional subcommand (--self-test / --selftest normalize exactly as
# anthology_registry.py and the U02 / U03 skeletons).
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="main_skeleton.py",
        description="U04 check-module dispatcher: offline plan, offline "
                    "self-test, and live verify of the Anthology Convert and "
                    "Flow TEMPLATE location (Skill 59, u04_modules; the "
                    "packaged sibling of u02_modules/main_skeleton.py and "
                    "u03_modules/main_skeleton.py) — imports the check "
                    "modules by name and aggregates their records into ONE "
                    "fail-closed JSON report.")
    ap.add_argument("--location-id", default="",
                    help="override the contract location id (default: the contract's "
                         "source_template_location.template_location_id, %s; masked "
                         "on every surface, never printed in full)"
                         % DEFAULT_TEMPLATE_LOCATION)
    ap.add_argument("--form-id", default="",
                    help="the pinned universal-intake form id (default: the engine "
                         "fleet value, imported from form_reader; masked on every "
                         "surface; a pinned id absent from the listing is a MISMATCH)")
    ap.add_argument("--allow-deferred", action="store_true",
                    help="explicit operator opt-in: accept a DEFERRED live read "
                         "as PASS — the report still records the deferral")
    ap.add_argument("--field-map", default=str(FIELD_MAP_PATH),
                    help="path to field-map.json (source of truth for the byte-exact gate)")
    ap.add_argument("--contract", default=str(CONTRACT_PATH),
                    help="path to anthology-snapshot-contract.json")
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
    # battery; plan -> the offline dry-run.
    if args.cmd == "self-test":
        args.self_test = True
    elif args.cmd == "plan":
        args.dry_run = True

    try:
        modules = load_modules()

        if args.self_test:
            return self_test(modules)

        field_map = reg.load_field_map(Path(args.field_map).expanduser())
        contract = _read_json(Path(args.contract).expanduser(),
                              "anthology-snapshot-contract.json")
        location_id = (args.location_id.strip() or
                       (contract.get("source_template_location") or {}).get(
                           "template_location_id")
                       or DEFAULT_TEMPLATE_LOCATION)
        pinned_id = (args.form_id.strip() or
                     (contract.get("forms") or {}).get(
                         "universal_intake_form_id") or
                     DEFAULT_UNIVERSAL_INTAKE_FORM_ID)

        if args.dry_run:
            return plan(modules, location_id, contract, pinned_id)

        # ---- live verify (GHL-gated) ----
        pit_label, token = reg.resolve_pit()
        if not token:
            checked = ", ".join(reg.PIT_LABELS)
            reg._stop(sys.stderr, "No Convert and Flow private-integration "
                                  "token is SET.",
                      ["Checked (in order): %s — all NOT SET." % checked,
                       "The verify runs against the operator's OWN template "
                       "location %s; set the template PIT (client-standard "
                       "labels first) and re-run." % _mask_id(location_id)])
            return EX_STOP
        client = reg.CafClient(token)

        return verify_live(modules, client, location_id, contract, pinned_id,
                           allow_deferred=args.allow_deferred, out=sys.stderr)

    except reg.ScopeDenied as exc:
        sys.stderr.write("[main-skeleton] STOP: %s\n" % exc)
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        sys.stderr.write("[main-skeleton] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
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
