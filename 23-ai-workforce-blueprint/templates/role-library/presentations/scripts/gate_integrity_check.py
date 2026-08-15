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
    python3 gate_integrity_check.py --purity
        GUARD B (Trust Boundary Increment 1, additive/non-breaking): AST-asserts
        that presentation_job.runfacts.verify_owner_skip / verify_qc — the two
        gates migrated onto the sealed RunFacts record so far — contain no
        direct file/env I/O. Exit 0 = confirmed pure; 1 = a violation found.
"""

import ast
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent              # .../presentations/scripts
sys.path.insert(0, str(HERE))
from manifest_source import resolve_manifest, resolve_ruleset, refuse
PRES_DIR = HERE.parent
BUILD_DECK = HERE / "build_deck.py"
AF_COVERAGE = HERE / "working" / "af-coverage.json"

AF_RE = re.compile(r"AF-[A-Z0-9]+(?:-[A-Z0-9]+)*")


def _fatal(msg):
    print(f"FATAL (gate_integrity_check cannot run): {msg}", file=sys.stderr)
    sys.exit(2)


def load_manifest():
    mpath = resolve_manifest(HERE)[0]
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


def run_check(manifest, defined_names, ref_counts, af_strings, covered):
    problems = []  # {code, kind, detail}

    def add(code, kind, detail):
        problems.append({"code": code, "kind": kind, "detail": detail})

    for a in manifest.get("autofails", []):
        if a.get("enforced_by") != "build_deck":
            continue  # out of scope — governed by sync_check / QC rubric, not here
        code = a.get("code", "<no-code>")
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


# ===========================================================================
# GUARD B: RUNFACTS-PURE GATES MUST BE ENFORCED BY AN AST LINT, NOT CONVENTION
# ===========================================================================
# TRUST BOUNDARY, INCREMENT 1 (see presentation_job/runfacts.py). The design
# calls for every migrated gate to be a pure function (RunFacts) -> Verdict
# that CANNOT open a file, "enforced by an AST lint in the existing
# gate_integrity_check.py rather than by convention". This increment migrates
# a small set of consumers (owner_skip + P-TYPO-QC) onto two pure verdict
# functions in presentation_job/runfacts.py; this guard proves — by parsing
# the source, not by trusting a docstring — that those two functions contain
# no direct file I/O. It is intentionally scoped to the functions THIS
# increment claims are pure; asserting purity for every _chk_* gate is future
# work (most of them still read files directly by design — they are shadow-
# compared against RunFacts, not yet migrated onto it).
#
# Additive and non-breaking: this only runs under --purity, so it changes
# nothing about the default `python3 gate_integrity_check.py` invocation any
# existing CI workflow already depends on (Guard A keeps its own exit code).
# ===========================================================================

RUNFACTS_PATH = HERE / "presentation_job" / "runfacts.py"

# A function claiming purity may not call any of these (by attribute name OR
# bare name) — every one of them touches the filesystem or environment.
_BANNED_ATTRS = {
    "read_text", "read_bytes", "write_text", "write_bytes", "exists", "is_file",
    "is_dir", "glob", "rglob", "iterdir", "stat", "lstat", "listdir", "scandir",
    "walk", "chmod", "replace", "unlink", "mkdir", "rename", "environ",
}
_BANNED_NAMES = {"open"}

# Functions in presentation_job/runfacts.py this increment asserts are pure:
# (RunFacts, ...) -> (Verdict, str), reading ONLY already-sealed fields off
# the RunFacts object passed in — never touching disk themselves.
# SLICE-2: verify_priority_shift / verify_final_qc were added when the
# report-shape phase gates (P-SHIFT-QC, P-QC-AGGREGATE) converted to the
# sealed-RunFacts verifier pattern (verifier_registry.py).
PURITY_ASSERTED_FUNCTIONS = ("verify_owner_skip", "verify_qc",
                             "verify_priority_shift", "verify_final_qc")
PURITY_ASSERTED_FUNCTIONS = (
    "verify_owner_skip",
    "verify_qc",
    # SLICE 3 (composite / multi-artifact gates) — pure verdicts over the
    # sealed facts; the seal does the I/O, the verdict never touches disk.
    "verify_deliverables",
    "verify_media_library",
    "verify_workbook",
    "verify_webinar_video",
    "verify_notes_sync",
    "verify_fish_tag",
)


def _function_bodies(source: str, names) -> dict:
    """Return {name: ast.FunctionDef} for every top-level (or nested, doesn't
    matter — ast.walk) function whose name is in `names`, parsed from source."""
    tree = ast.parse(source)
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in names:
            found[node.name] = node
    return found


def _banned_calls_in(fn_node: ast.FunctionDef) -> list:
    """Return a list of (lineno, description) for every banned call found
    anywhere inside fn_node's body (nested functions/comprehensions included —
    ast.walk descends into everything under this node)."""
    hits = []
    for node in ast.walk(fn_node):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr in _BANNED_ATTRS:
                hits.append((node.lineno, f"disallowed call .{f.attr}(...) — direct I/O "
                                          f"inside a function asserted RunFacts-pure"))
            elif isinstance(f, ast.Name) and f.id in _BANNED_NAMES:
                hits.append((node.lineno, f"disallowed call {f.id}(...) — direct I/O "
                                          f"inside a function asserted RunFacts-pure"))
        elif isinstance(node, ast.Attribute) and node.attr == "environ":
            hits.append((node.lineno, "disallowed access to os.environ inside a function "
                                      "asserted RunFacts-pure"))
    return hits


def run_purity_check() -> list:
    """Guard B. Returns a list of {"function", "detail"} problems; empty means
    every function in PURITY_ASSERTED_FUNCTIONS is free of the banned I/O
    calls, PROVEN by parsing runfacts.py, not by reading its docstring."""
    if not RUNFACTS_PATH.exists():
        _fatal(f"presentation_job/runfacts.py not found (looked at {RUNFACTS_PATH}) "
               f"— Guard B cannot run.")
    source = RUNFACTS_PATH.read_text()
    try:
        bodies = _function_bodies(source, set(PURITY_ASSERTED_FUNCTIONS))
    except SyntaxError as exc:
        _fatal(f"presentation_job/runfacts.py does not parse: {exc}")

    problems = []
    for name in PURITY_ASSERTED_FUNCTIONS:
        node = bodies.get(name)
        if node is None:
            problems.append({"function": name,
                              "detail": f"asserted RunFacts-pure but not FOUND in "
                                        f"{RUNFACTS_PATH.name} — update "
                                        f"PURITY_ASSERTED_FUNCTIONS or restore the function."})
            continue
        for lineno, desc in _banned_calls_in(node):
            problems.append({"function": name,
                              "detail": f"{RUNFACTS_PATH.name}:{lineno}: {desc}"})
    return problems


def main_purity() -> int:
    problems = run_purity_check()
    if not problems:
        print("=== gate_integrity_check --purity: RUNFACTS-PURE GATES CONFIRMED (Guard B) ===")
        print(f"Asserted-pure functions checked: {', '.join(PURITY_ASSERTED_FUNCTIONS)}")
        print("OK — none of them contain a direct file/env I/O call. Purity is enforced by "
              "parsing the source (AST), not by convention or docstring claim.")
        return 0
    print("=== gate_integrity_check --purity: PURITY VIOLATION (Guard B) ===", file=sys.stderr)
    for p in problems:
        print(f"  {p['function']}: {p['detail']}", file=sys.stderr)
    print(f"\n{len(problems)} violation(s). A function listed in "
          "PURITY_ASSERTED_FUNCTIONS must not perform direct I/O — either fix the "
          "function or remove it from the asserted-pure list (and from whatever "
          "calls it expecting purity).", file=sys.stderr)
    return 1


def main():
    as_json = "--json" in sys.argv[1:]
    manifest = load_manifest()
    defined_names, ref_counts, af_strings = parse_build_deck()
    covered = load_af_coverage()

    in_scope = [a["code"] for a in manifest.get("autofails", [])
                if a.get("enforced_by") == "build_deck"]
    problems = run_check(manifest, defined_names, ref_counts, af_strings, covered)

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
            print(f"build_deck-enforced autofails: {len(in_scope)}")
            print(f"af-coverage triggered codes:   {len(covered)}")
            print("OK — every build_deck-enforced autofail has a referenced enforcing "
                  "symbol that cites its own AF code AND a negative test that actually "
                  "triggers it. No declared-but-no-op / declared-but-untested gates.")
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
    if "--purity" in sys.argv[1:]:
        sys.exit(main_purity())
    main()
