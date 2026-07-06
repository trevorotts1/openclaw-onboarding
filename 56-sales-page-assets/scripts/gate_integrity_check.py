#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gate_integrity_check.py — GUARD A for the Sales Page Assets engine (FIX-XC-05a).

DECLARED == ENFORCED == TESTED. Ported from the presentation department's
gate_integrity_check.py (the enforcement TEMPLATE, FIX-XC-05). A rule that ships
only as a manifest DESCRIPTION — enforced by a no-op and triggered by no negative
test — is a latent bypass. This guard makes that structurally impossible for Skill 56.

For EVERY python-enforced autofail in SALESPAGE-MANIFEST.json (py_symbol of the form
`module.symbol`, where module is a prover in scripts/ or the run_sales_page_assets.py
orchestrator) it asserts BOTH:

  (a) ENFORCED — the py_symbol is DEFINED in its named module AND actually
      REFERENCED on an enforcement path (not a dead definition), AND the enforcement
      module NAMES the code (the AF code string is cited verbatim in that module OR a
      negative test in af-coverage triggers it).
  (b) TESTED  — the code appears in `working/af-coverage.json` "triggered": a
      deliberately-failing fixture (test_sp_gate_coverage.py) really RAISED it.

Shell-enforced front-door codes (py_symbol `sales-page-assets-entry.sh:*`) are OUT
OF SCOPE for the python symbol/coverage halves — bash guards proven by the entry
shell's own hash-pin + bypass-scan self-checks and the end-to-end
REJECTION-RESULTS E-variant. Reported for visibility, never a violation.

ZERO third-party deps (stdlib ast / json / re / pathlib only).

EXIT CODES:
    0 — every in-scope autofail is enforced (symbol referenced + code named) AND tested.
    1 — a no-op (unreferenced symbol / uncited & untriggered code) or an untested gate.
    2 — could not run (missing manifest / module / af-coverage, parse error) — fail-closed.

USAGE:
    python3 test_sp_gate_coverage.py      # FIRST — (re)emit working/af-coverage.json
    python3 gate_integrity_check.py       # then assert integrity
    python3 gate_integrity_check.py --json
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

HERE = Path(__file__).resolve().parent            # 56-sales-page-assets/scripts
SKILL_DIR = HERE.parent                            # 56-sales-page-assets
MANIFEST = SKILL_DIR / "SALESPAGE-MANIFEST.json"
AF_COVERAGE = HERE / "working" / "af-coverage.json"

AF_RE = re.compile(r"AF-SP56-[A-Z0-9]+(?:-[A-Z0-9]+)*")


def _fatal(msg: str) -> "None":
    print(f"FATAL (gate_integrity_check cannot run): {msg}", file=sys.stderr)
    sys.exit(2)


def load_manifest() -> Dict:
    if not MANIFEST.exists():
        _fatal(f"SALESPAGE-MANIFEST.json not found (looked at {MANIFEST}).")
    try:
        return json.loads(MANIFEST.read_text())
    except Exception as exc:  # noqa: BLE001
        _fatal(f"SALESPAGE-MANIFEST.json is not valid JSON: {exc}")
        return {}


def _resolve_module(mod: str) -> Optional[Path]:
    for cand in (HERE / f"{mod}.py", SKILL_DIR / f"{mod}.py"):
        if cand.is_file():
            return cand
    return None


_MODULE_CACHE: Dict[str, Tuple[Set[str], Dict[str, int], Set[str]]] = {}


def parse_module(mod: str) -> Optional[Tuple[Set[str], Dict[str, int], Set[str]]]:
    """(defined names, LOAD-reference counts, AF code strings) for one module file."""
    if mod in _MODULE_CACHE:
        return _MODULE_CACHE[mod]
    path = _resolve_module(mod)
    if path is None:
        return None
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        _fatal(f"{path.name} does not parse: {exc}")
    defined: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id.isupper():
                    defined.add(tgt.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id.isupper():
                defined.add(node.target.id)
    refs: Dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            refs[node.id] = refs.get(node.id, 0) + 1
        elif isinstance(node, ast.Attribute):
            refs[node.attr] = refs.get(node.attr, 0) + 1
    af = set(AF_RE.findall(src))
    result = (defined, refs, af)
    _MODULE_CACHE[mod] = result
    return result


def load_coverage() -> Set[str]:
    if not AF_COVERAGE.exists():
        _fatal(f"af-coverage.json not found (looked at {AF_COVERAGE}). Run "
               "`python3 test_sp_gate_coverage.py` FIRST to emit it (fail-closed).")
    try:
        cov = json.loads(AF_COVERAGE.read_text())
    except Exception as exc:  # noqa: BLE001
        _fatal(f"af-coverage.json is not valid JSON: {exc}")
        return set()
    return set(cov.get("triggered", []))


def _split_symbol(py_symbol: str) -> Tuple[str, str]:
    mod, _, sym = py_symbol.partition(".")
    return mod, sym


def run_check(manifest: Dict, covered: Set[str]):
    problems: List[Dict[str, str]] = []
    shell_scoped: List[str] = []

    def add(code: str, kind: str, detail: str) -> None:
        problems.append({"code": code, "kind": kind, "detail": detail})

    codes = manifest.get("autofail_codes", {})
    in_scope: List[str] = []
    for code, meta in codes.items():
        sym = str((meta or {}).get("py_symbol", ""))
        if ".sh:" in sym or sym.endswith(".sh"):
            shell_scoped.append(code)
            continue
        in_scope.append(code)

        mod, symbol = _split_symbol(sym)
        parsed = parse_module(mod)
        if parsed is None:
            add(code, "no-op", f"py_symbol module {mod!r} resolves to no .py file (cannot enforce).")
            continue
        defined, refs, af_strings = parsed

        # ---- (a) ENFORCED ----
        if not symbol:
            add(code, "no-op", f"py_symbol {sym!r} names no symbol.")
        elif symbol not in defined:
            add(code, "no-op",
                f"py_symbol {symbol!r} is not DEFINED in {mod}.py — the gate cannot enforce.")
        elif refs.get(symbol, 0) < 1:
            add(code, "no-op",
                f"symbol {symbol!r} is defined in {mod}.py but NEVER REFERENCED on any "
                "enforcement path (dead definition / no-op).")
        if code not in af_strings and code not in covered:
            add(code, "no-op",
                f"AF code {code!r} is NEITHER cited as a string in {mod}.py NOR triggered by "
                "any negative test (af-coverage) — a silent no-op the manifest only describes.")

        # ---- (b) TESTED ----
        if code not in covered:
            add(code, "untested",
                "declared+enforced but ABSENT from test_sp_gate_coverage.py af-coverage — no "
                "deliberately-failing fixture triggers it. Add a probe in test_sp_gate_coverage.py.")

    return problems, in_scope, shell_scoped


def main() -> int:
    as_json = "--json" in sys.argv[1:]
    manifest = load_manifest()
    covered = load_coverage()
    problems, in_scope, shell_scoped = run_check(manifest, covered)

    if as_json:
        print(json.dumps({
            "ok": not problems,
            "in_scope_python_codes": sorted(in_scope),
            "shell_enforced_out_of_scope": sorted(shell_scoped),
            "af_coverage_triggered": sorted(covered),
            "problems": problems,
        }, indent=2))
    elif not problems:
        print("=== gate_integrity_check (Skill 56): DECLARED == ENFORCED == TESTED (Guard A) ===")
        print(f"python-enforced autofails: {len(in_scope)}")
        print(f"af-coverage triggered:     {len(covered)}")
        print(f"shell-enforced (scoped out): {len(shell_scoped)} -> {sorted(shell_scoped)}")
        print("OK — every python-enforced autofail has a referenced enforcing symbol that names "
              "its own AF code AND a negative test that actually triggers it. No no-op / untested gates.")
    else:
        print("=== gate_integrity_check (Skill 56): GATE INTEGRITY VIOLATION (Guard A) ===",
              file=sys.stderr)
        for p in problems:
            print(f"  {p['code']} [{p['kind']}]: {p['detail']}", file=sys.stderr)
        print(f"\n{len(problems)} violation(s). A doctrine rule ships as a manifest autofail WITH "
              "an enforcing py_symbol AND a negative test that triggers it.", file=sys.stderr)

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
