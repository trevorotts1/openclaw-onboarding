#!/usr/bin/env python3
"""
ad_gate_integrity_check.py — GUARD A: DECLARED GATE MUST BE ENFORCED *AND* TESTED.

================================================================================
The root cause of a bypassable department is a rule that exists only as a
DESCRIPTION, never as ENFORCED + TESTED code. This guard makes that structurally
impossible for the Facebook & Instagram Ad Generator pipeline (mirrors the Movie
Producer's video_gate_integrity_check.py contract).

For EVERY autofail in AD-PIPELINE-MANIFEST.json whose enforced_by == "ad_director",
this check asserts BOTH:

  (a) ENFORCED — its py_symbol (and every secondary_py_symbol) is DEFINED in
      ad_director.py / ad_build_check.py AND is REFERENCED on an enforcement path
      (not a dead definition), AND the enforcement path NAMES the code (the AF code
      string is cited in the enforcement code OR a negative test triggers it).
  (b) TESTED  — the code appears in test_ad_preflight.py's emitted af-coverage
      (working/af-coverage.json): a deliberately-failing fixture really TRIGGERED it.

Codes NOT enforced_by == "ad_director" (e.g. enforced_by:driver for
AF-FBAD-DEP-SKIPPED) are OUT OF SCOPE for the symbol/citation half but are still
required to be TESTED (present in af-coverage) so the driver gate is provably tested.
================================================================================

ZERO third-party deps (stdlib json / re / ast / pathlib only).

EXIT CODES:
    0 — every gate is enforced (symbol referenced + code named) AND tested.
    1 — a no-op (unreferenced symbol / uncited code) or an untested gate.
    2 — could not run (missing manifest / code / af-coverage, parse error).

USAGE:
    python3 test_ad_preflight.py            # FIRST — emits working/af-coverage.json
    python3 ad_gate_integrity_check.py      # then assert integrity
    python3 ad_gate_integrity_check.py --json
"""

import ast
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AD_DIRECTOR = HERE / "ad_director.py"
BUILD_CHECK = HERE / "ad_build_check.py"
AF_COVERAGE = HERE / "working" / "af-coverage.json"
RECOVERY_COVERAGE = HERE / "working" / "recovery-coverage.json"

AF_RE = re.compile(r"AF-FBAD-[A-Z0-9]+(?:-[A-Z0-9]+)*")
DRIVER_ENFORCER = "ad_director"


def _fatal(msg):
    print(f"FATAL (ad_gate_integrity_check cannot run): {msg}", file=sys.stderr)
    sys.exit(2)


def _find_repo_root(start: Path):
    cur = start
    for _ in range(12):
        if (cur / "universal-sops").is_dir():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def _resolve_manifest():
    repo = _find_repo_root(HERE)
    candidates = []
    if repo:
        candidates.append(repo / "universal-sops" / "fb-ad-craft"
                          / "AD-PIPELINE-MANIFEST.json")
    candidates += [
        HERE.parent / "sops" / "AD-PIPELINE-MANIFEST.json",
        HERE.parent / "AD-PIPELINE-MANIFEST.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def load_manifest():
    mpath = _resolve_manifest()
    if not mpath.exists():
        _fatal(f"AD-PIPELINE-MANIFEST.json not found (looked at {mpath}).")
    try:
        return json.loads(mpath.read_text())
    except Exception as exc:  # noqa: BLE001
        _fatal(f"AD-PIPELINE-MANIFEST.json is not valid JSON: {exc}")


def _parse(path: Path):
    if not path.exists():
        _fatal(f"{path.name} not found (looked at {path}).")
    src = path.read_text()
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        _fatal(f"{path.name} does not parse: {exc}")
    defined = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            defined.add(node.name)
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id.isupper():
                    defined.add(tgt.id)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            defined.add(node.name)
    refs = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            refs[node.id] = refs.get(node.id, 0) + 1
        elif isinstance(node, ast.Attribute):
            refs[node.attr] = refs.get(node.attr, 0) + 1
    af = set(AF_RE.findall(src))
    return defined, refs, af


def parse_code():
    d1, r1, a1 = _parse(AD_DIRECTOR)
    d2, r2, a2 = _parse(BUILD_CHECK)
    refs = dict(r1)
    for k, v in r2.items():
        refs[k] = refs.get(k, 0) + v
    return d1 | d2, refs, a1 | a2


def load_coverage():
    if not AF_COVERAGE.exists():
        _fatal(f"af-coverage.json not found (looked at {AF_COVERAGE}). Run "
               "`python3 test_ad_preflight.py` FIRST to emit it.")
    try:
        cov = json.loads(AF_COVERAGE.read_text())
    except Exception as exc:  # noqa: BLE001
        _fatal(f"af-coverage.json is not valid JSON: {exc}")
    return set(cov.get("triggered", []))


def load_recovery_coverage():
    if not RECOVERY_COVERAGE.exists():
        _fatal(f"recovery-coverage.json not found (looked at {RECOVERY_COVERAGE}). Run "
               "`python3 test_ad_recovery.py` FIRST to emit it.")
    try:
        cov = json.loads(RECOVERY_COVERAGE.read_text())
    except Exception as exc:  # noqa: BLE001
        _fatal(f"recovery-coverage.json is not valid JSON: {exc}")
    return ({"auto_redo": set(cov.get("auto_redo", [])),
             "auto_budget_park": set(cov.get("auto_budget_park", [])),
             "park_immediate": set(cov.get("park_immediate", []))})


def check_recovery(manifest, rcov, problems):
    """Extend 'declared==enforced==tested' to the recovery policy: every autofail's
    recovery class must be PROVEN by a recovery-path test. auto => a REDO probe AND a
    budget->PARK probe tripped; park => an immediate-park-no-retry probe tripped."""
    for a in manifest.get("autofails", []):
        code = a.get("code", "<no-code>")
        recovery = a.get("recovery")
        if recovery == "auto":
            if code not in rcov["auto_redo"]:
                problems.append({"code": code, "kind": "recovery-untested",
                                 "detail": "recovery:auto but no REDO probe in "
                                           "recovery-coverage.auto_redo."})
            if code not in rcov["auto_budget_park"]:
                problems.append({"code": code, "kind": "recovery-untested",
                                 "detail": "recovery:auto but no budget->PARK probe in "
                                           "recovery-coverage.auto_budget_park."})
        elif recovery == "park":
            if code not in rcov["park_immediate"]:
                problems.append({"code": code, "kind": "recovery-untested",
                                 "detail": "recovery:park but no immediate-park probe in "
                                           "recovery-coverage.park_immediate."})
        else:
            problems.append({"code": code, "kind": "recovery-undeclared",
                             "detail": f"recovery is {recovery!r}; must be 'auto' or 'park'."})


def run_check(manifest, defined, refs, af_strings, covered):
    problems = []

    def add(code, kind, detail):
        problems.append({"code": code, "kind": kind, "detail": detail})

    for a in manifest.get("autofails", []):
        code = a.get("code", "<no-code>")
        enforced_by = a.get("enforced_by")

        # --- (b) TESTED — applies to EVERY autofail (including the driver gate). ---
        if code not in covered:
            add(code, "untested",
                "declared but ABSENT from test_ad_preflight.py af-coverage — no "
                "deliberately-failing fixture TRIGGERS it. Add a negative-test probe.")

        if enforced_by != DRIVER_ENFORCER:
            # driver / other enforcers: tested-only (already checked above).
            continue

        # --- (a) ENFORCED — symbol defined + referenced, code named. ---
        sym = a.get("py_symbol")
        secondaries = a.get("secondary_py_symbols", []) or []
        if not sym:
            add(code, "no-op",
                f"declared enforced_by:{DRIVER_ENFORCER} but carries NO py_symbol.")
        else:
            for s in [sym] + list(secondaries):
                if s not in defined:
                    add(code, "no-op",
                        f"py_symbol {s!r} is not DEFINED in the enforcement code.")
                elif refs.get(s, 0) < 1:
                    add(code, "no-op",
                        f"symbol {s!r} is defined but NEVER REFERENCED on any "
                        "enforcement path (dead definition / no-op).")
            if code not in af_strings and code not in covered:
                add(code, "no-op",
                    f"AF code {code!r} is enforced_by:{DRIVER_ENFORCER} but is NEITHER "
                    "cited as a string in the enforcement code NOR triggered by any "
                    "negative test — a silent no-op the manifest only describes.")

    return problems


def main():
    as_json = "--json" in sys.argv[1:]
    manifest = load_manifest()
    defined, refs, af_strings = parse_code()
    covered = load_coverage()
    rcov = load_recovery_coverage()

    in_scope = [a["code"] for a in manifest.get("autofails", [])]
    problems = run_check(manifest, defined, refs, af_strings, covered)
    check_recovery(manifest, rcov, problems)

    if as_json:
        print(json.dumps({
            "ok": not problems,
            "manifest_autofails": sorted(in_scope),
            "af_coverage_triggered": sorted(covered),
            "problems": problems,
        }, indent=2))
    else:
        if not problems:
            print("=== ad_gate_integrity_check: DECLARED == ENFORCED == TESTED (Guard A) ===")
            print(f"manifest autofails:          {len(in_scope)}")
            print(f"af-coverage triggered codes: {len(covered)}")
            print(f"recovery-coverage: auto-redo={len(rcov['auto_redo'])} "
                  f"auto-budget-park={len(rcov['auto_budget_park'])} "
                  f"park-immediate={len(rcov['park_immediate'])}")
            print("OK — every autofail is tested (a negative fixture triggers it), every "
                  "ad_director-enforced gate has a referenced enforcing symbol that names "
                  "its own AF code, AND every recovery class is proven by a recovery-path "
                  "test. No no-op / untested / recovery-untested gates.")
        else:
            print("=== ad_gate_integrity_check: GATE INTEGRITY VIOLATION (Guard A) ===",
                  file=sys.stderr)
            for p in problems:
                print(f"  {p['code']} [{p['kind']}]: {p['detail']}", file=sys.stderr)
            print(f"\n{len(problems)} violation(s). A doctrine rule ships as a manifest "
                  "autofail WITH an enforcing py_symbol AND a negative test that triggers "
                  "it. A rule that is only described is not enforced.", file=sys.stderr)

    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
