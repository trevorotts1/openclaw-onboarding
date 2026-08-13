#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u02_modules/main_skeleton.py
# U02 CHECK-MODULE DISPATCHER — the offline-plan / offline-self-test / live
# verify driver for the U02 GHL TEMPLATE live re-verifier check modules under
# scripts/u02_modules/. It imports the check modules BY NAME, normalizes their
# heterogeneous surfaces (tuple records, dict reports, direct exit codes)
# into ONE JSON report, and resolves the fail-closed aggregate exit code
# exactly as live_verify_template.py does. It carries NO check logic itself:
# a check module is exercised ONLY through this CLI so `--dry-run`,
# `--self-test`, and the live aggregate never drift apart.
#
# THE LIVE READ IS GHL-GATED; THE TOOLING SHIPS NOW (manifest row 54 doctrine).
# The operator executes `verify` only from a session that can resolve a
# template-scoped private-integration token BY LABEL. --dry-run (offline plan)
# and --self-test (offline, no token, no network) always work.
#
# CHECK MODULES (imported by name; each is STDLIB-only and self-tests itself):
#   pipeline_check.py      check_pipeline_name(client, location_id, ...)
#                          -> ("PASS"|"FAIL", detail, name, stage_count);
#                          raises PipelineMissing on absent/renamed (STOP)
#   stages_check.py        check_stages(client, location_id, field_map)
#                          -> {"ok": bool, "count": int, "names": [str]};
#                          never raises for a data mismatch
#   fields_check.py        check_fields_live(client, location_id, field_map)
#                          -> report dict {"ok": bool, "verdict": "PASS"|"FAIL",
#                          ...}; raises FieldsCheckError (STOP) on a strict
#                          subset, a self-contradicting map, or an unread shape
#   custom_values_check.py check_custom_values(client, location_id, contract,
#                          *, out=None, jsonout=None) -> int exit code
#                          (0/2/3/5); writes its own JSON to jsonout
#   forms_check.py         check_forms(location_id, contract, *, rail=None)
#                          -> {"ok": bool, "found": [str], "missing": [str],
#                          "deferred": bool} — DEFERRED never fabricates
#   workflows_check.py     check_workflows_live(rail, location_id, contract)
#                          -> {"ok": bool, "count": int, "names": [str], ...};
#                          raises WorkflowsCheckError (STOP) on a malformed
#                          listing; reg.InternalRailUnavailable propagates
#   scope_check.py         check(payload, *, stage_tokens=..., form_candidates=...)
#                          -> (ok, filter_set) — the INTAKE FIRE trigger scope
#                          gate. FAIL-CLOSED: any ambiguity is (False, reason);
#                          never fabricates a pass, never prints the payload
#
# The import contract is one ENTRY POINT per module, exposed as `check`:
#   * a callable `check` is required (fail-closed: a module without one STOPS
#     the dispatcher — no check family is ever skipped), and
#   * every module's OFFLINE self-test is `self_test(out=None) -> int`, exit 0
#     on pass, 4 (EX_VIOLATION, the AF-AE-TEMPLATE-ATTACK family) on failure.
# Each entry point takes its contract arguments POSITIONALLY (with the same
# defaults the module itself documents) so the module bodies never need an
# adapter to be driven from here. A module may additionally expose
# `plan(field_map, contract)` / `verify_exit(...)` / `run_live(...)` — when
# present they are used, when absent the dispatcher derives the same surface
# from `check` (exact-count reads become DEFERRED, never fabricated; exit
# codes are classified fail-closed).
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. The PIT is resolved through
# anthology_registry (CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_API_KEY /
# GOHIGHLEVEL_API_KEY / GOHIGHLEVEL_PIT / GHL_API_KEY, live process env first
# then the three canonical client env stores). The location id is pinned to
# the contract's template location (2HIKGNgsixWx0yds7Qnx) unless
# --location-id overrides. The optional Firebase refresh token for the
# internal rail is resolved BY LABEL (ANTHOLOGY_GHL_FIREBASE_REFRESH_TOKEN /
# GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN / GHL_FIREBASE_REFRESH_TOKEN). SET /
# NOT SET only on every operator surface; a value is NEVER printed.
#
# BROWSER UA: every request rides reg.CafClient / reg.InternalRailClient,
# which apply the CAF_BROWSER_UA so the Cloudflare edge fronting
# services.leadconnectorhq.com never 1010s a verify request (CF 1010 / GK-09
# discipline). Scope-vs-edge-block discrimination: a bare 401/403 is HELD
# (UpstreamBlockedError), never reported as a scope problem.
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
#   AF-AE-TEMPLATE-INTAKE-FIRE       -> the intake-fire side drifted: the
#          webhook custom value absent/misplaced, or a live workflow inlines
#          an intake URL instead of the merge. exit 5.
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
# STDLIB ONLY (urllib + json via the registry and the check modules); calls
# NO model. Reuses anthology_registry (CafClient, InternalRailClient,
# resolve_pit, resolve_firebase_refresh_token, _stop). DOCTRINE: move in
# silence; NOTHING Anthropic in any runtime file; Convert and Flow naming in
# every client surface; NEVER print a secret value; --dry-run and --self-test
# are OFFLINE.
# =============================================================================
"""main_skeleton.py — U02 check-module dispatcher: offline plan / offline
self-test / live verify of the GHL TEMPLATE location (Skill 59, row 54)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Sibling import bootstrap (house convention): the registry does the
# Cloudflare browser-UA wiring + LeadConnector client + internal-rail client
# and its label resolution is the house credential contract.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import anthology_registry as reg  # noqa: E402

EX_OK, EX_ERR, EX_STOP, EX_HELD, EX_MISMATCH = (
    reg.EX_OK, reg.EX_ERR, reg.EX_STOP, reg.EX_HELD, reg.EX_MISMATCH)
EX_VIOLATION = 4  # enforced violation detected (self-test FAILED)

# The u02_modules directory itself — sibling imports resolve from here.
MODULES_DIR = Path(__file__).resolve().parent

# ENGINE-MANIFEST.json row 54 / AF-AE-TEMPLATE-* rows bind each check family
# to a py_symbol in live_verify_template.py; the check modules mirror that
# naming ONE-TO-ONE so the manifest rows and the dispatcher never drift.
# Each entry names the module's one required entry point (`check`) and the
# positional contract arguments the dispatcher hands it.
CHECK_MODULES = (
    ("pipeline_check", "check_pipeline_name"),
    ("stages_check", "check_stages"),
    ("fields_check", "check_fields_live"),
    ("custom_values_check", "check_custom_values"),
    ("forms_check", "check_forms"),
    ("workflows_check", "check_workflows_live"),
    ("scope_check", "check"),
)

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"
ROUTE_TEMPLATE_PATH = SKILL_DIR / "config" / "route-template.json"

# The template location id is the CONTRACT's source_template_location (the
# operator's OWN template location, operator infrastructure config, not a
# secret). The verifier pins to it; --location-id overrides for tests.
DEFAULT_TEMPLATE_LOCATION = "2HIKGNgsixWx0yds7Qnx"

# scope_check is a pure payload gate, not a Convert and Flow read. There is
# nothing to DEFER for it: the payload-filter contract can always be asserted
# offline. It is run in verify mode only as a smoke pass.
_SCOPE_MODULE = "scope_check"

# The check modules that need the internal rail (a Firebase refresh token BY
# LABEL) for their live read. Without the rail their live read is DEFERRED
# (never fabricated) and the aggregate is fail-closed unless --allow-deferred.
_RAIL_GATED = ("forms_check", "workflows_check")

# The check modules whose live read rides the Convert and Flow REST client.
# scope_check is excluded: it inspects a payload, never the location.
_REST_GATED = ("pipeline_check", "stages_check", "fields_check",
               "custom_values_check")

# Each module's OWN fail-closed exception classes (STOP family): a module
# raises these for an absent pipeline / drifted contract / malformed listing
# — exactly the semantics live_verify_template.py's TemplateVerifyError
# carries. The dispatcher classifies them as STOP (exit 2) with the module's
# message on the operator surface, NEVER as an unexpected error. The class
# objects are resolved from the module at run time (a module that renames
# its class stays mapped by name and is simply not raised anymore).
_MODULE_STOP_EXCEPTIONS = {
    "pipeline_check": ("PipelineMissing",),
    "stages_check": ("StagesCheckError",),
    "fields_check": ("FieldsCheckError",),
    "custom_values_check": (),
    "forms_check": ("FormsCheckError",),
    "workflows_check": ("WorkflowsCheckError",),
    "scope_check": (),
}


class SkeletonError(Exception):
    """A fail-closed refusal (STOP or mismatch family) raised by the skeleton
    itself — a missing check module, a module violating the entry-point
    contract, a contract section that cannot be read, or a malformed record."""


# ---------------------------------------------------------------------------
# Check-module loader — imports the check modules BY NAME and enforces the
# one-entry-point contract. A missing module or a module that fails to expose
# its entry point is a STOP, never a silent skip.
# ---------------------------------------------------------------------------
def load_checks():
    """Import every CHECK_MODULES module. Returns {name: module}.

    Fail-closed: a module that does not exist or does not expose its documented
    `check` entry point raises SkeletonError (STOP) so the aggregate NEVER
    passes with a check family silently absent. `importlib` is the only import
    surface — nothing is ever exec'd from a path.
    """
    import importlib

    checks = {}
    missing = []
    for name, entry in CHECK_MODULES:
        try:
            mod = importlib.import_module(name)
        except ImportError:
            missing.append("%s (entry %s)" % (name, entry))
            continue
        fn = getattr(mod, entry, None)
        if not callable(fn):
            raise SkeletonError(
                "check module %s does not expose its entry point %r — "
                "the import contract is one entry point per module" % (name, entry))
        checks[name] = mod
    if missing:
        raise SkeletonError(
            "check module(s) not found: %s — install them under u02_modules/ "
            "before running (fail-closed: no check family is ever skipped)"
            % ", ".join(missing))
    return checks


def _entry(mod):
    """The module's documented check entry point. The roster uses bare names
    (``pipeline_check``); an importer may hand us the dotted identity
    (``u02_modules.pipeline_check``) when the package is on sys.path, so
    match on the final component too."""
    for name, entry in CHECK_MODULES:
        if name == mod.__name__ or name == mod.__name__.split(".")[-1]:
            return getattr(mod, entry)
    return getattr(mod, "check", None)


# ---------------------------------------------------------------------------
# Record normalization — each check module's surface is reduced to the
# (status, detail, expected, live) record live_verify_template.py emits.
# Exit codes classify fail-closed; dict reports map verdict->status; a check
# that returns nothing readable is a STOP, never a silent pass.
# ---------------------------------------------------------------------------
def _entry_rc_to_record(rc, name):
    if rc == EX_OK:
        return ("PASS", "ok", None, None)
    if rc in (EX_STOP, EX_ERR):
        return ("FAIL", "%s exit %d (STOP)" % (name, rc), None, None)
    if rc == EX_HELD:
        return ("FAIL", "%s exit %d (HELD)" % (name, rc), None, None)
    if rc == EX_MISMATCH:
        return ("FAIL", "%s exit %d (mismatch)" % (name, rc), None, None)
    return ("FAIL", "%s exit %d (unknown)" % (name, rc), None, None)


def _dict_to_record(report, name):
    if not isinstance(report, dict):
        raise SkeletonError(
            "check module %s returned %r instead of a record/report"
            % (name, type(report).__name__))
    verdict = report.get("verdict") or ("PASS" if report.get("ok") else "FAIL")
    status = "PASS" if verdict == "PASS" else ("FAIL" if verdict == "FAIL"
                                               else "FAIL")
    detail = report.get("detail") or report.get("note") or ""
    if report.get("deferred") is True:
        status = "DEFERRED"
    if report.get("fail_closed") and status == "PASS" and not report.get("ok"):
        status = "FAIL"
    return (status, detail, report.get("expected"), report.get("live"))


def _tuple_to_record(record, name):
    if (not isinstance(record, tuple)) or len(record) != 4:
        raise SkeletonError(
            "check module %s returned %r instead of a (status, detail, "
            "expected, live) 4-tuple" % (name, type(record).__name__))
    status, detail, expected, live = record
    if status not in ("PASS", "FAIL", "DEFERRED"):
        raise SkeletonError(
            "check module %s returned unknown status %r (PASS / FAIL / DEFERRED)"
            % (name, status))
    return (status, detail, expected, live)


def _normalize(rc_or_report, name):
    """One record from any check surface — an exit code, a report dict, or a
    4-tuple. Anything else is a STOP (never a silent pass)."""
    if isinstance(rc_or_report, int):
        return _entry_rc_to_record(rc_or_report, name)
    if isinstance(rc_or_report, dict):
        return _dict_to_record(rc_or_report, name)
    if isinstance(rc_or_report, tuple):
        return _tuple_to_record(rc_or_report, name)
    raise SkeletonError(
        "check module %s returned %r — expected an exit code, a report dict, "
        "or a (status, detail, expected, live) 4-tuple"
        % (name, type(rc_or_report).__name__))


# ---------------------------------------------------------------------------
# Per-module invocation — the argument lists are the modules' OWN contract
# signatures, positional with their documented defaults. Additive arguments
# (--location-id / --field-map / --contract) are always handed through so the
# exact templates the operator pinned in the CLI are the exact ones the
# modules assert.
# ---------------------------------------------------------------------------
def _invoke(mod, name, client, rail, location_id, contract, field_map,
            route, *, allow_deferred):
    fn = _entry(mod)
    if name == "pipeline_check":
        return fn(client, location_id)  # name law read from the field-map itself
    if name == "stages_check":
        return fn(client, location_id, field_map)
    if name == "fields_check":
        return fn(client, location_id, field_map)
    if name == "custom_values_check":
        return fn(client, location_id, contract)  # writes its own jsonout surface
    if name == "forms_check":
        return fn(location_id, contract, rail=rail)
    if name == "workflows_check":
        # The module's live read is rail-only and it has NO no-rail path of
        # its own (unlike forms_check, which defers internally): without the
        # rail the dispatcher returns the DEFERRED record itself — never
        # fabricated, and --allow-deferred only relaxes the AGGREGATE exit,
        # it never fabricates a read.
        if rail is None:
            return ("DEFERRED",
                    "live workflow read needs the internal rail (Firebase "
                    "refresh token BY LABEL) — never fabricated",
                    {"count": "not read"}, {"count": "not read"})
        return fn(rail, location_id, contract)
    if name == _SCOPE_MODULE:
        # Pure payload gate: assert the intake-fire filter contract on the
        # GOLDEN submission (offline) as a smoke pass.
        golden = {"source": "anthology-intake", "location": "LOC-synthetic-AAA",
                  "form": "universal-intake", "contact_id": "C-0001",
                  "anthology_id": "A-0001", "stage": "s0_intake"}
        ok, flt = fn(golden)
        return ("PASS" if ok else "FAIL", "intake-fire scope gate", None, flt)
    raise SkeletonError("dispatcher has no invocation for check module %r"
                        % name)


# ---------------------------------------------------------------------------
# Offline plan — no network, no credentials. Prints ONE JSON object on
# stdout; human notes go to stderr.
# ---------------------------------------------------------------------------
def plan(location_id: str, checks, field_map: dict, contract: dict) -> int:
    out = {}
    for name, mod in checks.items():
        try:
            if hasattr(mod, "plan"):
                meta = mod.plan(field_map, contract) if _entry(mod) else {}
            else:
                meta = {}
        except Exception:  # noqa: BLE001 — a plan is never fatal; record it
            meta = {}
        out[name] = meta
    print(json.dumps({
        "contract": "anthology-engine-template-live-verify-plan",
        "schema_version": 1,
        "template_location_id": location_id,
        "check_modules": [name for name, _ in CHECK_MODULES],
        "checks": out,
        "dry_run": True,
        "note": "offline plan only — no network, no credential needed",
    }, indent=2, sort_keys=True))
    return EX_OK


# ---------------------------------------------------------------------------
# Offline self-test — golden + attack fixtures, mutation proof, exit 4 on
# failure (a tamper NEVER masquerades as exit 1).
#
# custom_values_check ships NO offline self-test of its own (it is the
# read-only live probe over reg.CafClient; its logic is exercised by the
# pipeline/stages/fields self-tests against the same fake client seams) — so
# the skeleton's own OFFLINE battery covers its pure placeholder classifier,
# and a module that has a self_test is REQUIRED to pass it.
# ---------------------------------------------------------------------------
def self_test(checks) -> int:
    import io
    dev = io.StringIO()
    try:
        for name, mod in checks.items():
            st = getattr(mod, "self_test", None)
            if callable(st):
                try:
                    rc = st(out=dev)
                except TypeError:
                    rc = st()
                if rc != EX_OK:
                    raise AssertionError("%s self_test returned exit %d"
                                         % (name, rc))
            elif name == "custom_values_check":
                from custom_values_check import is_placeholder
                assert is_placeholder("") is True, "empty value is a placeholder"
                assert is_placeholder("REPLACE-ME") is True
                assert is_placeholder("https://hooks.example.com/x") is False, \
                    "a real-looking value must be refused (never-a-real-token)"
            else:
                raise SkeletonError(
                    "check module %s does not expose 'self_test' — every check "
                    "module must prove itself offline" % name)
    except AssertionError as exc:
        sys.stderr.write("[main-skeleton] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    except SkeletonError as exc:
        sys.stderr.write("[main-skeleton] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    sys.stderr.write(dev.getvalue())
    return EX_OK


# ---------------------------------------------------------------------------
# Live verify — fail-closed aggregate. Any FAIL -> exit 5; any DEFERRED live
# check (missing rail credential) keeps the exit at 5 unless --allow-deferred
# (the operator's explicit opt-in, documented in the report).
# ---------------------------------------------------------------------------
def verify_live(checks, client, rail, location_id: str, contract: dict,
                field_map: dict, route: dict, *, allow_deferred: bool = False,
                out=None) -> int:
    out = out or sys.stderr
    report = {"checks": {}, "delta": [], "fail_closed": True}

    def _stop_classes(mod):
        classes = []
        for cname in _MODULE_STOP_EXCEPTIONS.get(mod.__name__, ()):
            cls = getattr(mod, cname, None)
            if isinstance(cls, type) and issubclass(cls, Exception):
                classes.append(cls)
        return tuple(classes)

    def _run(name, mod):
        try:
            rc_or_report = _invoke(mod, name, client, rail, location_id,
                                   contract, field_map, route,
                                   allow_deferred=allow_deferred)
            return _normalize(rc_or_report, name), None
        except reg.ScopeDenied as exc:
            reg._stop(out, "The Convert and Flow token cannot READ the "
                           "template location (%s)." % name,
                      [str(exc), "Grant the template PIT the READ scope and re-run.",
                       "AF-AE-PIT-SCOPE."])
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
        except _stop_classes(mod) as exc:
            reg._stop(out, "Fail-closed refusal in %s: %s" % (name, exc), [])
            return None, EX_STOP
        except SkeletonError as exc:
            reg._stop(out, "Fail-closed refusal in %s: %s" % (name, exc), [])
            return None, EX_STOP
        return None, None

    for name, mod in checks.items():
        record, rc = _run(name, mod)
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
        out.write("[main-skeleton] internal-rail refresh token NOT SET — "
                  "rail-gated checks DEFERRED (fail-closed, never fabricated). "
                  "Set one of %s to read the live workflow list.\n"
                  % ", ".join(reg.FIREBASE_REFRESH_LABELS))
        if not allow_deferred:
            report["delta"].append({
                "check": "aggregate",
                "detail": "%d check(s) DEFERRED without --allow-deferred "
                          "(fail-closed): %s" % (len(deferred), ", ".join(deferred)),
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
# anthology_registry.py and live_verify_template.py).
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="main_skeleton.py",
        description="U02 check-module dispatcher: offline plan, offline "
                    "self-test, and live verify of the Anthology Convert and "
                    "Flow TEMPLATE location (Skill 59, ENGINE-MANIFEST row 54) "
                    "— imports the check modules by name and aggregates their "
                    "records into ONE fail-closed JSON report.")
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

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    # Normalize --self-test / --selftest -> --self-test so the flag form never
    # collides with the positional subcommand form.
    if "--self-test" in argv and "--selftest" not in argv:
        argv = ["--self-test" if a == "--self-test" else a for a in argv]
    args = ap.parse_args(argv)

    try:
        checks = load_checks()
        if args.self_test:
            return self_test(checks)

        field_map = reg.load_field_map(Path(args.field_map).expanduser())
        contract = _read_json(Path(args.contract).expanduser(), "anthology-snapshot-contract.json")
        route = _read_json(Path(args.route_template).expanduser(), "route-template.json")
        location_id = (args.location_id.strip() or
                       (contract.get("source_template_location") or {}).get("template_location_id")
                       or DEFAULT_TEMPLATE_LOCATION)

        if args.dry_run:
            return plan(location_id, checks, field_map, contract)

        # ---- live verify ----
        pit_label, token = reg.resolve_pit()
        if not token:
            checked = ", ".join(reg.PIT_LABELS)
            reg._stop(sys.stderr, "No Convert and Flow private-integration token is SET.",
                      ["Checked (in order): %s — all NOT SET." % checked,
                       "The verify runs against the operator's OWN template location %s; "
                       "set the template PIT (client-standard labels first) and re-run."
                       % location_id])
            return EX_STOP
        client = reg.CafClient(token)

        # READ probe FIRST: a token that cannot READ the template location STOPS
        # (AF-AE-PIT-SCOPE family) instead of a mid-verify surprise.
        try:
            probe = client.list_custom_fields(location_id)
        except reg.ScopeDenied as exc:
            reg._stop(sys.stderr, "The Convert and Flow token lacks READ scope on the template location.",
                      [str(exc), "Grant the template PIT the customFields READ scope and re-run."])
            return EX_STOP
        except reg.UpstreamBlockedError as exc:
            sys.stderr.write("[main-skeleton] HELD: %s\n" % exc)
            return EX_HELD
        except reg.CafUnreachable as exc:
            sys.stderr.write("[main-skeleton] HELD: %s\n" % exc)
            return EX_HELD
        if not isinstance(probe, list):
            sys.stderr.write("[main-skeleton] unexpected customFields read shape\n")
            return EX_ERR

        # Internal rail (optional): without a Firebase refresh token the workflow /
        # forms / intake-fire-workflow-half reads are DEFERRED (never fabricated)
        # and the aggregate is fail-closed unless --allow-deferred.
        rail = None
        rlabel, rtoken = reg.resolve_firebase_refresh_token()
        if rtoken:
            _, api_key = reg._resolve_firebase_api_key() or (None, "")
            rail = reg.InternalRailClient(rtoken, api_key) if api_key else None

        return verify_live(checks, client, rail, location_id, contract, field_map,
                           route, allow_deferred=args.allow_deferred, out=sys.stderr)

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
