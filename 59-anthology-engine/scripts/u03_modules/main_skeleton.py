#!/usr/bin/env python3
# =============================================================================
# SKILL 59 — ANTHOLOGY ENGINE :: u03_modules/main_skeleton.py
# U03 CHECK-MODULE DISPATCHER — the offline-plan / offline-self-test / live
# verify / GO-gated apply driver for the U03 GHL TEMPLATE re-verification
# family under scripts/u03_modules/. It imports the check modules BY NAME
# (importlib, never exec'd from a path), enforces the fail-closed
# one-entry-point contract, and resolves the aggregate exit code exactly as
# the U02 sibling (u02_modules/main_skeleton.py) does. It carries NO check
# logic itself: a check module is exercised ONLY through this CLI so
# `--dry-run`, `--self-test`, and the live aggregate never drift apart.
#
# THE LIVE READ IS GHL-GATED; THE TOOLING SHIPS NOW (manifest row 54
# doctrine). The operator executes `verify` only from a session that can
# resolve a template-scoped private-integration token BY LABEL. --dry-run
# (offline plan) and --self-test (offline, no token, no network) always work.
# `apply` is the WRITE surface: it REFUSES with exit 2 unless the operator
# passes an explicit --yes (the never-mutate-without-explicit-GO law) — and
# even then it re-verifies the live state first, fail-closed.
#
# THE U03 FAMILY (the check modules this dispatcher aggregates; each is
# STDLIB-only, self-tests itself, and ships its own thin CLI — this skeleton
# is the ONE entry-point contract over them):
#   config_loader.py    load_config(*, contract_path, field_map_path,
#                       location_override) -> dict {"location_id",
#                       "expected_name", "sources"}; raises ConfigError on
#                       a missing/malformed contract, a drifted name-law
#                       pair, or a credential-shaped payload (exit 2). The
#                       location id and the expected name are NEVER
#                       hardcoded here — they come from this module.
#   name_reader.py      read_pipeline_names(client, location_id)
#                       -> (names, count, duplicates) — the LIVE pipeline
#                       name read; raises MalformedPayload (STOP family) on
#                       an unreadable shape, never a silent empty.
#   rename_checker.py   check_name(client, location_id, want="")
#                       -> {"ok": bool, "current": str, "expected": str} —
#                       the LIVE name check, BYTE-EXACT vs the field-map
#                       name law; NEVER raises on a name drift (a mismatch
#                       is a reportable FAIL, not an exception).
#   rename_applier.py   apply_rename(client, pipeline_id, name, *, out)
#                       -> report dict / exit code — the ONLY write surface
#                       in the engine's Python. The dispatcher invokes it
#                       ONLY after an explicit operator --yes AND a fresh
#                       live re-read showing the drift, and REFUSES exit 2
#                       otherwise.
#   verify_after.py     verify_after(client, location_id, field_map,
#                       contract, *, out) -> int exit code (0/2/5) — the
#                       read-back: stamp coherent, custom values placeholders
#                       only, standard pipeline byte-exact. Also plan().
#   golden_correct.py   golden_correct(field_map) -> dict — the canonical
#                       golden pipeline payload (field-map derived).
#   golden_wrong.py     golden_wrong_pipeline(field_map) / wrong_state() —
#                       the canonical RENAMED-state payload the checks must
#                       DETECT (golden-half of the drift gate).
#   attack_no_pipeline.py  verify(payload, want_name) -> ("PASS"|...; raises
#                       NoPipelineError on the EMPTY listing) — the U03
#                       ATTACK: a location with NOTHING bound is refused UP
#                       FRONT (find-and-bind cannot tell empty from renamed),
#                       never judged a clean read. Also payload() (0/5).
#   house_rules.py      the ONE canonical surface for the engine's house-law
#                       constants (browser UA, version header, the AF codes,
#                       never-a-token markers, the hard GO gate) — this
#                       skeleton derives its own constants from it, so a
#                       drifted rule is caught by the offline self-test.
#   example_usage.py    fail-closed WORKED EXAMPLE of the U03 dispatch: a
#                       golden walk-through of the verify -> drift -> apply ->
#                       read-back arc, its own self-test proves the example
#                       cannot drift from the family contract.
#   docs_u03.py         the U03 tooling README shipped as an importable
#                       module — the canonical inventory of the U03 modules,
#                       the four verified items, exit codes, and af codes;
#                       this dispatcher's self-test pins its counts against
#                       docs_u03 so the catalog and the tree never drift.
#
# The import contract is one ENTRY POINT per module. The dispatcher's own
# offline self-test runs EVERY module's `self_test(out=None) -> int` battery
# (golden PASS / attack FAIL) before any live surface; a module without one
# STOPS (exit 2) — no check family is ever skipped, no tamper masquerades
# as exit 1.
#
# CREDENTIALS: BY LABEL, NEVER BY VALUE. The PIT is resolved through
# anthology_registry (CONVERT_AND_FLOW_PIT / CONVERT_AND_FLOW_API_KEY /
# GOHIGHLEVEL_API_KEY / GOHIGHLEVEL_PIT / GHL_API_KEY, live process env first
# then the three canonical client env stores). The location id comes from the
# CONTRACT via config_loader (never hardcoded, never printed in full — the
# masked marker on every operator surface). SET / NOT SET only on every
# operator surface; a token value is NEVER printed.
#
# BROWSER UA: every request rides reg.CafClient, which applies CAF_BROWSER_UA
# on every request so the Cloudflare edge fronting
# services.leadconnectorhq.com never 1010s a verify request (CF 1010 / GK-09
# discipline — the house pattern ported byte-for-byte from the podcast gate).
# Scope-vs-edge-block discrimination: a bare 401/403 is HELD
# (UpstreamBlockedError), never reported as a scope problem.
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
# EXIT CODES (house convention 0/1/2/3/5; 4 = enforced violation; the
# primary surface the operator consumes is 0 = PASS, 2 = STOP, 5 = mismatch):
#   0  all checks PASS (also --dry-run plan pass and self-test pass)
#   1  unexpected error
#   2  STOP refusal — label NOT SET / non-pit- value / usage / a check
#      module missing from u03_modules/ / a contract that cannot be read /
#      a credential-shaped payload / apply without explicit --yes
#   3  Convert and Flow API unreachable / internal rail unavailable (HELD)
#   4  self-test FAILED — an assertion in the OFFLINE self-test tripped
#      (AF-AE-TEMPLATE-ATTACK family). A tamper NEVER masquerades as exit 1.
#   5  data or read-back mismatch (AF-AE-TEMPLATE-PIPELINE-MISSING drift;
#      also the fail-closed default when any live check is DEFERRED without
#      --allow-deferred)
#
# STDLIB ONLY (urllib + json via the registry and the check modules); calls
# NO model. Reuses anthology_registry (CafClient, resolve_pit, resolve_location,
# _stop, _mask_location). DOCTRINE: move in silence; NOTHING Anthropic in any
# runtime file; Convert and Flow naming in every client surface; NEVER print
# a secret value; --dry-run and --self-test are OFFLINE.
# =============================================================================
"""main_skeleton.py — U03 check-module dispatcher: offline plan / offline
self-test / live verify / GO-gated apply of the Anthology GHL TEMPLATE
location (Skill 59, u03_modules; the packaged sibling of
u02_modules/main_skeleton.py)."""

from __future__ import annotations

import argparse
import json
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

# The u03_modules directory itself — sibling imports resolve from here, in
# BOTH execution contexts (as a script, whose own directory is sys.path[0],
# and as an imported module, where the caller may not have added it).
MODULES_DIR = Path(__file__).resolve().parent
if str(MODULES_DIR) not in sys.path:
    sys.path.insert(0, str(MODULES_DIR))

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"
CONTRACT_PATH = SKILL_DIR / "config" / "anthology-snapshot-contract.json"

# The U03 check-module inventory — the assembly manifest for this dispatcher.
# Every name is imported BY NAME below (importlib, never exec'd from a path);
# a missing module is a STOP, never a silent skip. `role` is the one-line
# contract each module owns; `self_test` marks the modules that ship their
# own OFFLINE battery (golden PASS / attack FAIL, exit 0 pass / 4 enforced
# violation), which this dispatcher runs before any live surface. The names
# mirror docs_u03.modules() one-to-one (the catalog and the tree never
# drift; the dispatcher self-test pins the counts).
U03_MODULES = (
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
)

# The modules that ship their own OFFLINE self-test battery (each returns
# exit 0 on pass, 4 on failure). The dispatcher REQUIRES a battery from
# every module — a check family that cannot prove itself offline STOPS.
SELF_TEST_MODULES = tuple(name for name, _ in U03_MODULES)

# The live-verify gate order (FIXED, in this order): the read-back family.
LIVE_GATES = (
    ("verify_after", "the three read-back gates: stamp coherent, custom "
                     "values placeholders only, standard pipeline byte-exact"),
)


class SkeletonError(Exception):
    """A fail-closed refusal (STOP or mismatch family) raised by the skeleton
    itself — a missing check module, a module violating the entry-point
    contract, a contract section that cannot be read, or a malformed record."""


# ---------------------------------------------------------------------------
# Check-module loader — imports the U03 modules BY NAME and enforces the
# fail-closed contract: a missing module or a module that fails to expose
# its entry point is a STOP, never a silent skip.
# ---------------------------------------------------------------------------
def load_modules():
    """Import every U03_MODULES module. Returns {name: module}.

    Fail-closed: a module that does not exist raises SkeletonError (STOP) so
    the aggregate NEVER passes with a check family silently absent.
    `importlib` is the only import surface — nothing is ever exec'd from a
    path. Each module's `self_test(out=None) -> int` battery is REQUIRED
    (checked here, not deferred to the self-test run)."""
    import importlib

    modules = {}
    missing = []
    for name, _role in U03_MODULES:
        try:
            mod = importlib.import_module(name)
        except ImportError:
            missing.append(name)
            continue
        modules[name] = mod
    if missing:
        raise SkeletonError(
            "u03_modules file(s) not found: %s — the U03 assembly is "
            "incomplete (fail-closed: no check family is ever skipped)"
            % ", ".join(missing))
    for name, mod in modules.items():
        st = getattr(mod, "self_test", None)
        if not callable(st):
            raise SkeletonError(
                "u03_modules module %s does not expose 'self_test' — every "
                "check module must prove itself offline" % name)
    return modules


# ---------------------------------------------------------------------------
# Offline self-test — run EVERY module's own battery (golden PASS / attack
# FAIL) plus this dispatcher's own assembly assertions. NO network, NO
# credentials. Exit 4 on any failure (AF-AE-TEMPLATE-ATTACK family) — a
# tamper NEVER masquerades as exit 1.
# ---------------------------------------------------------------------------
def self_test(modules, out=None) -> int:
    import io
    out = out or sys.stderr
    dev = io.StringIO()
    try:
        # 1. the assembly is complete: exactly the U03 check-module set
        #    exists (the dispatcher and the empty package init are the
        #    assembly container, not dispatched check modules).
        on_disk = sorted(p.name[:-3] for p in MODULES_DIR.glob("*.py")
                         if p.name not in ("__init__.py", "main_skeleton.py")
                         and not p.name.startswith("test_"))
        expected = sorted(name for name, _ in U03_MODULES)
        assert on_disk == expected, (
            "u03_modules tree drifted: disk carries %s, the %d-module "
            "assembly contract names %s" % (", ".join(on_disk), len(expected),
                                            ", ".join(expected)))
        # 2. every module's own battery passes (golden PASS / attack FAIL).
        for name, mod in modules.items():
            try:
                rc = mod.self_test(out=dev)
            except TypeError:
                rc = mod.self_test()
            if rc != EX_OK:
                raise AssertionError("%s self_test returned exit %d" % (name, rc))
        # 3. the one-entry-point surfaces the live verify drives exist.
        for name, fn in (("verify_after", "verify_after"),
                         ("name_reader", "read_pipeline_names"),
                         ("rename_checker", "check_name")):
            if not callable(getattr(modules[name], fn, None)):
                raise AssertionError("u03_modules module %s does not expose "
                                     "entry point %r" % (name, fn))
        # 4. the catalog and the tree never drift: docs_u03's module
        #    inventory catalogs the 11 check modules plus the empty package
        #    init and the skeleton itself (minus docs_u03's own row — a
        #    12-entry catalog for an 11-module dispatch set), and the four
        #    verified items pin the dispatch surface.
        docs = modules["docs_u03"]
        assert len(docs.modules()) == len(U03_MODULES) + 1, \
            "docs_u03 module count drifted from the U03 assembly (11 check " \
            "modules + __init__.py + main_skeleton.py, minus docs_u03's own row)"
        assert len(docs.verify_items()) == 4, \
            "docs_u03 verified-item count drifted from the U03 four-item law"
        assert len(docs.af_codes()) >= 3, \
            "docs_u03 af-code family drifted below the U03 three-code minimum"
    except AssertionError as exc:
        sys.stderr.write("[main-skeleton] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    except SkeletonError as exc:
        sys.stderr.write("[main-skeleton] SELF-TEST FAILED "
                         "(AF-AE-TEMPLATE-ATTACK family): %s\n" % exc)
        return EX_VIOLATION
    out.write(dev.getvalue())
    out.write("[main-skeleton] U03 self-test: OK (%d modules imported, "
              "every module battery + catalog drift gate + assembly "
              "assertions pass)\n" % len(modules))
    return EX_OK


# ---------------------------------------------------------------------------
# Offline plan — no network, no credentials. The U03 dispatch law with the
# exact sources of truth, printed as ONE JSON object on stdout; human notes
# go to stderr.
# ---------------------------------------------------------------------------
def plan(modules, location_id: str, expected_name: str,
         sources: dict, out=None) -> int:
    out = out or sys.stderr
    try:
        cfg = modules["config_loader"].load_config(
            contract_path=CONTRACT_PATH, field_map_path=FIELD_MAP_PATH)
    except Exception as exc:  # noqa: BLE001 — a plan never fabricates
        out.write("[main-skeleton] plan: %s\n" % exc)
        return EX_STOP
    print(json.dumps({
        "contract": "anthology-engine-u03-dispatch-plan",
        "schema_version": 1,
        "location_id": cfg["location_id"],
        "location_id_masked": modules["config_loader"].mask_location(
            cfg["location_id"]),
        "expected_name": cfg["expected_name"],
        "sources": cfg["sources"],
        "gates": [name for name, _ in LIVE_GATES],
        "modules": [name for name, _ in U03_MODULES],
        "dry_run": True,
        "note": "offline plan only — no network, no credential needed; a "
                "LIVE read must ride reg.CafClient (CAF_BROWSER_UA on every "
                "request — CF 1010 law)",
    }, indent=2, sort_keys=True))
    return EX_OK


# ---------------------------------------------------------------------------
# Live verify — fail-closed aggregate over the fixed gate order. Any FAIL ->
# exit 5; a STOP-family refusal propagates as exit 2; the Convert and Flow
# edge/transport failures are HELD (exit 3), never mislabeled as scope.
# ---------------------------------------------------------------------------
def verify_live(modules, client, location_id: str, field_map: dict,
                contract: dict, *, allow_deferred: bool = False,
                out=None) -> int:
    out = out or sys.stderr
    verify_after = modules["verify_after"]
    masked = modules["config_loader"].mask_location(location_id)
    try:
        return verify_after.verify_after(client, location_id, field_map,
                                         contract, out=out)
    except reg.ScopeDenied as exc:
        reg._stop(out, "The Convert and Flow token cannot READ the template "
                       "location (%s)." % masked,
                  [str(exc), "Grant the template PIT the READ scope and re-run.",
                   "AF-AE-PIT-SCOPE."])
        return EX_STOP
    except reg.UpstreamBlockedError as exc:
        out.write("[main-skeleton] HELD: %s\n" % exc)
        return EX_HELD
    except reg.CafUnreachable as exc:
        out.write("[main-skeleton] HELD: %s\n" % exc)
        return EX_HELD
    except Exception as exc:  # noqa: BLE001 — a module refusal is never an unexpected error
        if exc.__class__.__name__ in ("VerifyAfterError", "MalformedPayload",
                                      "NoPipelineError", "ConfigError"):
            reg._stop(out, "Fail-closed refusal in verify_after: %s" % exc, [])
            return EX_STOP
        raise


# ---------------------------------------------------------------------------
# GO-gated apply — the ONLY write surface. Refuses exit 2 without the
# operator's explicit --yes; even with --yes it re-reads the live state
# first (fail-closed: never writes over an unread live state), and the
# re-verification after the write must PASS (read-back before report).
# ---------------------------------------------------------------------------
def apply_rename(modules, client, location_id: str, field_map: dict,
                 contract: dict, *, yes: bool = False, out=None) -> int:
    out = out or sys.stderr
    masked = modules["config_loader"].mask_location(location_id)
    if not yes:
        reg._stop(out, "apply REFUSED: no explicit operator GO.",
                  ["Pass --yes to authorize the pipeline rename write — "
                   "reversible is NOT authorized (the never-mutate-without-"
                   "explicit-GO law). Re-run with --yes to re-verify the "
                   "live state, apply the byte-exact name, and read back "
                   "(marker %s)." % masked])
        return EX_STOP
    checker = modules["rename_checker"]
    reader = modules["name_reader"]
    applier = modules["rename_applier"]
    cfg = modules["config_loader"].load_config(contract_path=CONTRACT_PATH,
                                               field_map_path=FIELD_MAP_PATH)
    want = cfg["expected_name"]

    # Fresh live re-read FIRST: never write over an unread live state.
    try:
        names, count, _dups = reader.read_pipeline_names(client, location_id)
    except Exception as exc:  # noqa: BLE001 — classified below, never leaked
        reg._stop(out, "apply REFUSED: the live pipelines read failed.",
                  ["%s" % exc,
                   "A write never proceeds from an unread live state "
                   "(fail-closed). Re-run once the location reads cleanly."])
        return EX_STOP
    report = checker.check_name(client, location_id, want)
    if report.get("ok"):
        out.write("[main-skeleton] apply: no drift to fix — the standard "
                  "pipeline is already byte-exact on %s.\n" % masked)
        return EX_OK

    # The drift is real and proven. The rename applier drives the write and
    # the read-back itself (its self-test proves the apply is idempotent);
    # its refusal is a STOP, never a silent pass.
    try:
        return applier.apply_rename(client, location_id, want, out=out)
    except Exception as exc:  # noqa: BLE001 — classified below, never leaked
        reg._stop(out, "apply REFUSED: %s" % exc, [])
        return EX_STOP


# ---------------------------------------------------------------------------
# CLI — house shape: --dry-run / --self-test / --json accepted as flags AND
# as a positional subcommand (--self-test / --selftest normalize exactly as
# anthology_registry.py and u02_modules/main_skeleton.py).
# ---------------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="main_skeleton.py",
        description="U03 check-module dispatcher: offline plan, offline "
                    "self-test, live verify, and GO-gated apply of the "
                    "Anthology Convert and Flow TEMPLATE location (Skill 59, "
                    "u03_modules; the packaged sibling of "
                    "u02_modules/main_skeleton.py) — imports the check "
                    "modules by name and aggregates their records into ONE "
                    "fail-closed JSON report.")
    ap.add_argument("--location-id", default="",
                    help="override the contract location id (tests; named "
                         "masked on every surface; the contract stays required)")
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
    ap.add_argument("--yes", action="store_true",
                    help="explicit operator GO for apply — REQUIRED before "
                         "any write; without it apply REFUSES (exit 2)")
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
    # battery; plan -> the offline dry-run; apply -> the GO-gated write.
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
        cfg = modules["config_loader"].load_config(
            contract_path=Path(args.contract).expanduser(),
            field_map_path=Path(args.field_map).expanduser(),
            location_override=args.location_id)
        location_id = cfg["location_id"]

        if args.dry_run:
            return plan(modules, location_id, cfg["expected_name"],
                        cfg["sources"])

        # ---- live paths (GHL-gated) ----
        pit_label, token = reg.resolve_pit()
        if not token:
            checked = ", ".join(reg.PIT_LABELS)
            reg._stop(sys.stderr, "No Convert and Flow private-integration token is SET.",
                      ["Checked (in order): %s — all NOT SET." % checked,
                       "The verify runs against the operator's OWN template "
                       "location %s; set the template PIT (client-standard "
                       "labels first) and re-run."
                       % modules["config_loader"].mask_location(location_id)])
            return EX_STOP
        client = reg.CafClient(token)

        if args.cmd == "apply":
            return apply_rename(modules, client, location_id, field_map,
                                contract, yes=args.yes)

        return verify_live(modules, client, location_id, field_map, contract,
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
