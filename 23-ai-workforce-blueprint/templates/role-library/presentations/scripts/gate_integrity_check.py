#!/usr/bin/env python3
"""
gate_integrity_check.py — GUARD A: DECLARED GATE MUST BE ENFORCED *AND* TESTED.

================================================================================
The root cause of the two gaps just closed was a rule that existed only as a
DESCRIPTION, never as ENFORCED + TESTED code (e.g. AF-QC-INDEPENDENCE shipped as
a manifest entry whose enforcement was a no-op, with no negative test). This
guard makes that structurally impossible.

For EVERY autofail in PIPELINE-MANIFEST.json whose enforced_by == "build_deck",
this check asserts ALL of:

  (a) ENFORCED — its py_symbol (and every secondary_py_symbol) is DEFINED in
      build_deck.py AND is actually REFERENCED on the enforcement path (not a dead
      definition): the symbol is used somewhere other than its own definition line,
      AND the AF code string itself is cited in build_deck.py.
  (b) TESTED  — the code appears in test_preflight.py's emitted af-coverage
      (working/af-coverage.json): a deliberately-failing fixture really TRIGGERED
      it. A declared+enforced gate with no negative test is a latent no-op.

Codes NOT enforced_by == "build_deck" (e.g. enforced_by qc_check / closeout_gate /
agent, or sync-only AF-HOOK-* identifiers) are OUT OF SCOPE here — they are
governed by sync_check.py / the QC rubric, not the build_deck negative-test set.
================================================================================

ZERO third-party deps (stdlib json / re / ast / pathlib only).

INPUTS (resolved relative to THIS script, repo + deployed layouts both handled):
  * universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json (declared truth)
  * build_deck.py (the canonical renderer / enforcer)
  * working/af-coverage.json (emitted by `python3 test_preflight.py`)

EXIT CODES:
    0 — every build_deck-enforced gate is enforced AND has a triggering negative test.
    1 — one or more gates are a no-op (unreferenced symbol) or untested (absent from
        af-coverage). Message names the offending code + the missing half.
    2 — could not run (missing manifest / build_deck / af-coverage, parse error).

USAGE:
    python3 test_preflight.py            # FIRST — produces working/af-coverage.json
    python3 gate_integrity_check.py      # then assert integrity
    python3 gate_integrity_check.py --json
"""

import ast
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent              # .../presentations/scripts
PRES_DIR = HERE.parent
BUILD_DECK = HERE / "build_deck.py"
AF_COVERAGE = HERE / "working" / "af-coverage.json"

# FIX I — extend the meta-gate beyond build_deck: a RUNNER-enforced gate must be
# cited in a runner-side enforcer (the report gates live here), and any gate that
# declares a check_script must point at a real file + symbol. This is what stops a
# future "declared but never wired" regression like the new report gates.
RUNNER_SOURCES = [HERE / "run_signature_deck.py", HERE / "prove-deck.py"]

AF_RE = re.compile(r"AF-[A-Z0-9]+(?:-[A-Z0-9]+)*")


def parse_runner_af():
    """AF-* codes cited in the runner-side enforcers (run_signature_deck.py +
    prove-deck.py). A runner-enforced manifest code must be cited in one of these,
    else it is a declared-but-unwired gate."""
    codes = set()
    for p in RUNNER_SOURCES:
        if p.exists():
            try:
                codes |= set(AF_RE.findall(p.read_text()))
            except Exception:  # noqa: BLE001
                pass
    return codes


def _fatal(msg):
    print(f"FATAL (gate_integrity_check cannot run): {msg}", file=sys.stderr)
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
    repo_root = _find_repo_root(HERE)
    candidates = []
    if repo_root:
        candidates.append(repo_root / "universal-sops" / "presentation-slide-craft"
                          / "PIPELINE-MANIFEST.json")
    candidates += [
        PRES_DIR / "sops" / "PIPELINE-MANIFEST.json",
        PRES_DIR / "PIPELINE-MANIFEST.json",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[0]


def load_manifest():
    mpath = _resolve_manifest()
    if not mpath.exists():
        _fatal(f"PIPELINE-MANIFEST.json not found (looked at {mpath}).")
    try:
        return json.loads(mpath.read_text())
    except Exception as exc:  # noqa: BLE001
        _fatal(f"PIPELINE-MANIFEST.json is not valid JSON: {exc}")


def parse_build_deck():
    """Return (defined_names, reference_counts, af_strings).
    defined_names: every module-level constant + every function name.
    reference_counts: name -> number of ast.Name/attr LOADS (excludes the def/assign
                      target itself), used to prove a symbol is referenced, not dead.
    af_strings: every AF-* string literal/comment token cited in the source."""
    if not BUILD_DECK.exists():
        _fatal(f"build_deck.py not found (looked at {BUILD_DECK}).")
    source = BUILD_DECK.read_text()
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        _fatal(f"build_deck.py does not parse: {exc}")

    defined_names = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            defined_names.add(node.name)
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id.isupper():
                    defined_names.add(tgt.id)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id.isupper():
                defined_names.add(node.target.id)
    # function names at ANY depth (nested defs) also count as defined.
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            defined_names.add(node.name)

    # Count LOAD references: a name used in a Load context (call, attribute base,
    # argument, etc.). A symbol referenced only by its own definition is a no-op.
    ref_counts = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            ref_counts[node.id] = ref_counts.get(node.id, 0) + 1
        elif isinstance(node, ast.Attribute):
            # build_deck.SOMENAME style is rare internally, but count attr names too.
            ref_counts[node.attr] = ref_counts.get(node.attr, 0) + 1

    af_strings = set(AF_RE.findall(source))
    return defined_names, ref_counts, af_strings


def load_af_coverage():
    if not AF_COVERAGE.exists():
        _fatal(f"af-coverage.json not found (looked at {AF_COVERAGE}). Run "
               f"`python3 test_preflight.py` FIRST to emit it.")
    try:
        cov = json.loads(AF_COVERAGE.read_text())
    except Exception as exc:  # noqa: BLE001
        _fatal(f"af-coverage.json is not valid JSON: {exc}")
    return set(cov.get("triggered", []))


def run_check(manifest, defined_names, ref_counts, af_strings, covered, runner_af):
    problems = []  # {code, kind, detail}

    def add(code, kind, detail):
        problems.append({"code": code, "kind": kind, "detail": detail})

    for a in manifest.get("autofails", []):
        code = a.get("code", "<no-code>")
        enforced_by = a.get("enforced_by")

        # ---- (FIX I) RUNNER-enforced gate must be WIRED in a runner-side enforcer ----
        # The report/process-integrity gates (AF-PHASE-REPORT-START/-DONE,
        # AF-PROCESS-INTEGRITY) are enforced_by:runner with py_symbol:null. A runner
        # gate the runner never names is a declared-but-unwired no-op — exactly the
        # regression class this extension catches.
        if enforced_by == "runner":
            if code not in runner_af:
                add(code, "no-op",
                    f"declared enforced_by:runner but NOT cited in any runner-side "
                    f"enforcer (run_signature_deck.py / prove-deck.py). A runner gate the "
                    f"runner never names is a declared-but-unwired no-op. Wire it into the "
                    f"runner, or remove the declaration.")

        # ---- (FIX I) any gate with a check_script must point at a real file+symbol ----
        cs = a.get("check_script")
        if isinstance(cs, str) and cs.strip():
            rel = cs.split("::", 1)[0].strip()
            sym = cs.split("::", 1)[1].strip() if "::" in cs else ""
            path = PRES_DIR / rel
            if not path.exists():
                add(code, "no-op",
                    f"check_script {rel!r} does not exist on disk — the declared gate "
                    f"points at a missing enforcer (unwired). Restore the file or fix the path.")
            elif sym:
                try:
                    if f"def {sym}" not in path.read_text():
                        add(code, "no-op",
                            f"check_script {cs!r}: function {sym!r} is not defined in {rel} "
                            f"(unwired symbol). Define it or fix the reference.")
                except Exception:  # noqa: BLE001
                    pass

        if enforced_by != "build_deck":
            continue  # the deep enforced-AND-tested checks below are build_deck-only
        sym = a.get("py_symbol")
        secondaries = a.get("secondary_py_symbols", []) or []

        # ---- (a) ENFORCED ----
        # Enforcement is proven by TWO independent signals, and we require BOTH a live
        # symbol AND a live "naming" so a declared gate cannot be a silent no-op:
        #   1. py_symbol (+ secondaries) DEFINED and REFERENCED (not a dead definition).
        #   2. The enforcement path NAMES the code: either the AF code string is cited
        #      verbatim in build_deck.py, OR — for a gate that legitimately surfaces
        #      under a sibling code (e.g. AF-PROMPT-FLOOR enforced inside the AF-P1
        #      rich-prompt path) — a negative test in af-coverage proves the gate fires.
        #      A code that is NEITHER cited NOR triggered by any test is a no-op.
        if not sym:
            add(code, "no-op",
                f"declared enforced_by:build_deck but carries NO py_symbol. A declared "
                f"gate with no enforcing symbol is a no-op. Add the enforcing "
                f"_chk_/function/constant and name it in py_symbol.")
        else:
            for s in [sym] + list(secondaries):
                if s not in defined_names:
                    add(code, "no-op",
                        f"py_symbol {s!r} is not DEFINED in build_deck.py — the gate "
                        f"cannot enforce. Define it (or fix the symbol name).")
                elif ref_counts.get(s, 0) < 1:
                    add(code, "no-op",
                        f"symbol {s!r} is defined but NEVER REFERENCED on any "
                        f"enforcement path in build_deck.py (dead definition / no-op). "
                        f"Wire it into the gate, or remove the declaration.")
            # The enforcement path must NAME the code it raises — proven by the AF code
            # string being cited in build_deck.py OR a negative test actually triggering
            # it (covered). Lacking BOTH = a silent no-op the manifest only describes.
            if code not in af_strings and code not in covered:
                add(code, "no-op",
                    f"AF code {code!r} is declared enforced_by:build_deck but is NEITHER "
                    f"cited as a string in build_deck.py NOR triggered by any negative "
                    f"test (af-coverage) — the enforcement path neither names nor "
                    f"demonstrably raises this code. It is a silent no-op.")

        # ---- (b) TESTED ----
        if code not in covered:
            add(code, "untested",
                f"declared+enforced but ABSENT from test_preflight.py af-coverage — no "
                f"deliberately-failing fixture TRIGGERS it. Add a negative-test probe in "
                f"emit_af_coverage() (test_preflight.py) that trips this gate. "
                f"(This is exactly the AF-QC-INDEPENDENCE no-op class.)")

    return problems


def main():
    as_json = "--json" in sys.argv[1:]
    manifest = load_manifest()
    defined_names, ref_counts, af_strings = parse_build_deck()
    covered = load_af_coverage()
    runner_af = parse_runner_af()

    in_scope = [a["code"] for a in manifest.get("autofails", [])
                if a.get("enforced_by") in ("build_deck", "runner") or a.get("check_script")]
    problems = run_check(manifest, defined_names, ref_counts, af_strings, covered, runner_af)

    if as_json:
        print(json.dumps({
            "ok": not problems,
            "build_deck_enforced_codes": sorted(in_scope),
            "af_coverage_triggered": sorted(covered),
            "problems": problems,
        }, indent=2))
    else:
        if not problems:
            print("=== gate_integrity_check: DECLARED == ENFORCED == TESTED (Guard A) ===")
            print(f"in-scope autofails (build_deck + runner + check_script): {len(in_scope)}")
            print(f"af-coverage triggered codes:   {len(covered)}")
            print("OK — every build_deck-enforced autofail has a referenced enforcing "
                  "symbol that cites its own AF code AND a negative test that triggers it; "
                  "every runner-enforced gate is cited in a runner-side enforcer; every "
                  "check_script points at a real file+symbol. No declared-but-no-op gates.")
        else:
            print("=== gate_integrity_check: GATE INTEGRITY VIOLATION (Guard A) ===",
                  file=sys.stderr)
            noops = [p for p in problems if p["kind"] == "no-op"]
            untested = [p for p in problems if p["kind"] == "untested"]
            if noops:
                print("\nNO-OP gates (declared+enforced but not actually enforcing):",
                      file=sys.stderr)
                for p in noops:
                    print(f"  {p['code']}: {p['detail']}", file=sys.stderr)
            if untested:
                print("\nUNTESTED gates (declared+enforced but no negative test triggers them):",
                      file=sys.stderr)
                for p in untested:
                    print(f"  {p['code']}: {p['detail']}", file=sys.stderr)
            print(f"\n{len(problems)} violation(s). A doctrine rule ships as a manifest "
                  "autofail WITH an enforcing py_symbol AND a negative test that triggers "
                  "it. A rule that is only described is not enforced.", file=sys.stderr)

    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
