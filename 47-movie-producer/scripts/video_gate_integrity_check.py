#!/usr/bin/env python3
"""
video_gate_integrity_check.py — GUARD A: DECLARED GATE MUST BE ENFORCED *AND* TESTED.

================================================================================
The root cause of a bypassable department is a rule that exists only as a
DESCRIPTION, never as ENFORCED + TESTED code. This guard makes that structurally
impossible for the Movie Producer pipeline (mirrors the Presentations
gate_integrity_check.py contract).

For EVERY autofail in VIDEO-PIPELINE-MANIFEST.json whose enforced_by ==
"executive_producer", this check asserts BOTH:

  (a) ENFORCED — its py_symbol (and every secondary_py_symbol) is DEFINED in
      executive_producer.py / video_build_check.py AND is REFERENCED on an
      enforcement path (not a dead definition), AND the enforcement path NAMES the
      code (the AF code string is cited in the enforcement code OR a negative test
      demonstrably triggers it).
  (b) TESTED  — the code appears in test_video_preflight.py's emitted af-coverage
      (working/af-coverage.json): a deliberately-failing fixture really TRIGGERED it.

Codes NOT enforced_by == "executive_producer" (e.g. enforced_by:driver for
AF-VID-PHASE-SKIPPED) are OUT OF SCOPE for the symbol/citation half but are still
required to be TESTED (present in af-coverage) so the driver gate is provably tested.
================================================================================

ZERO third-party deps (stdlib json / re / ast / pathlib only).

EXIT CODES:
    0 — every gate is enforced (symbol referenced + code named) AND tested.
    1 — a no-op (unreferenced symbol / uncited code) or an untested gate.
    2 — could not run (missing manifest / code / af-coverage, parse error).

USAGE:
    python3 test_video_preflight.py            # FIRST — emits working/af-coverage.json
    python3 video_gate_integrity_check.py      # then assert integrity
    python3 video_gate_integrity_check.py --json
"""

import ast
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXEC_PRODUCER = HERE / "executive_producer.py"
BUILD_CHECK = HERE / "video_build_check.py"
AF_COVERAGE = HERE / "working" / "af-coverage.json"

AF_RE = re.compile(r"AF-VID-[A-Z0-9]+(?:-[A-Z0-9]+)*")


def _fatal(msg):
    print(f"FATAL (video_gate_integrity_check cannot run): {msg}", file=sys.stderr)
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
        candidates.append(repo / "universal-sops" / "video-pipeline-craft"
                          / "VIDEO-PIPELINE-MANIFEST.json")
    candidates += [
        HERE.parent / "sops" / "VIDEO-PIPELINE-MANIFEST.json",
        HERE.parent / "VIDEO-PIPELINE-MANIFEST.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def load_manifest():
    mpath = _resolve_manifest()
    if not mpath.exists():
        _fatal(f"VIDEO-PIPELINE-MANIFEST.json not found (looked at {mpath}).")
    try:
        return json.loads(mpath.read_text())
    except Exception as exc:  # noqa: BLE001
        _fatal(f"VIDEO-PIPELINE-MANIFEST.json is not valid JSON: {exc}")


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
    d1, r1, a1 = _parse(EXEC_PRODUCER)
    d2, r2, a2 = _parse(BUILD_CHECK)
    refs = dict(r1)
    for k, v in r2.items():
        refs[k] = refs.get(k, 0) + v
    return d1 | d2, refs, a1 | a2


def load_coverage():
    if not AF_COVERAGE.exists():
        _fatal(f"af-coverage.json not found (looked at {AF_COVERAGE}). Run "
               "`python3 test_video_preflight.py` FIRST to emit it.")
    try:
        cov = json.loads(AF_COVERAGE.read_text())
    except Exception as exc:  # noqa: BLE001
        _fatal(f"af-coverage.json is not valid JSON: {exc}")
    return set(cov.get("triggered", []))


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
                "declared but ABSENT from test_video_preflight.py af-coverage — no "
                "deliberately-failing fixture TRIGGERS it. Add a negative-test probe.")

        if enforced_by != "executive_producer":
            # driver / other enforcers: tested-only (already checked above).
            continue

        # --- (a) ENFORCED — symbol defined + referenced, code named. ---
        sym = a.get("py_symbol")
        secondaries = a.get("secondary_py_symbols", []) or []
        if not sym:
            add(code, "no-op",
                "declared enforced_by:executive_producer but carries NO py_symbol.")
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
                    f"AF code {code!r} is enforced_by:executive_producer but is NEITHER "
                    "cited as a string in the enforcement code NOR triggered by any "
                    "negative test — a silent no-op the manifest only describes.")

    return problems


def main():
    as_json = "--json" in sys.argv[1:]
    manifest = load_manifest()
    defined, refs, af_strings = parse_code()
    covered = load_coverage()

    in_scope = [a["code"] for a in manifest.get("autofails", [])]
    problems = run_check(manifest, defined, refs, af_strings, covered)

    if as_json:
        print(json.dumps({
            "ok": not problems,
            "manifest_autofails": sorted(in_scope),
            "af_coverage_triggered": sorted(covered),
            "problems": problems,
        }, indent=2))
    else:
        if not problems:
            print("=== video_gate_integrity_check: DECLARED == ENFORCED == TESTED (Guard A) ===")
            print(f"manifest autofails:          {len(in_scope)}")
            print(f"af-coverage triggered codes: {len(covered)}")
            print("OK — every autofail is tested (a negative fixture triggers it), and "
                  "every executive_producer-enforced gate has a referenced enforcing "
                  "symbol that names its own AF code. No no-op / untested gates.")
        else:
            print("=== video_gate_integrity_check: GATE INTEGRITY VIOLATION (Guard A) ===",
                  file=sys.stderr)
            for p in problems:
                print(f"  {p['code']} [{p['kind']}]: {p['detail']}", file=sys.stderr)
            print(f"\n{len(problems)} violation(s). A doctrine rule ships as a manifest "
                  "autofail WITH an enforcing py_symbol AND a negative test that triggers "
                  "it. A rule that is only described is not enforced.", file=sys.stderr)

    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
